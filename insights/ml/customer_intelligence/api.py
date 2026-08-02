# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Customer Intelligence - API Functions
All standalone whitelisted wrapper functions for the customer intelligence module.
"""

import frappe
import pandas as pd
from typing import Dict, Any, List


@frappe.whitelist()
def run_customer_intelligence(update_customers: bool = True, async_mode: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Run comprehensive customer intelligence analysis"""
    from insights.ml.customer_intelligence import CustomerIntelligence

    # Check customer count for async decision
    customer_count = frappe.db.count("Customer", {"disabled": 0})

    if async_mode or customer_count > CustomerIntelligence.CUSTOMER_THRESHOLD:
        # Run async via background job
        job = frappe.enqueue(
            "insights.ml.customer_intelligence.api._run_customer_intelligence_job",
            queue="long",
            timeout=3600,
            update_customers=update_customers,
            date_filter=date_filter
        )
        return {
            "status": "queued",
            "message": f"Analysis queued for {customer_count} customers",
            "job_id": job.id if hasattr(job, 'id') else str(job)
        }

    model = CustomerIntelligence(date_filter=date_filter)
    return model.train(update_customers=update_customers)


def _run_customer_intelligence_job(update_customers: bool = True, date_filter: str = '12m'):
    """Background job for customer intelligence"""
    from insights.ml.customer_intelligence import CustomerIntelligence

    try:
        model = CustomerIntelligence(date_filter=date_filter)
        result = model.train(update_customers=update_customers)

        # Store job result
        frappe.cache.set_value(
            f"customer_intelligence_job_result_{date_filter}",
            {"status": "completed", "result": result},
            expires_in_sec=3600
        )

        frappe.logger().info(f"Customer intelligence completed: {result.get('summary', {}).get('total_customers', 0)} customers")
        return result
    except Exception as e:
        frappe.log_error(f"Customer intelligence job failed: {str(e)}", "ML Scheduler")
        frappe.cache.set_value(
            "customer_intelligence_job_result",
            {"status": "error", "message": str(e)},
            expires_in_sec=3600
        )
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_customer_intelligence() -> Dict[str, Any]:
    """Get cached customer intelligence or run if not available"""
    from insights.ml.customer_intelligence import CustomerIntelligence

    model = CustomerIntelligence()
    cached = model.get_cached_results("customer_intelligence")

    if cached:
        return cached

    return model.train()


@frappe.whitelist()
def get_customer_intelligence_status() -> Dict[str, Any]:
    """Check status of async customer intelligence job"""
    result = frappe.cache.get_value("customer_intelligence_job_result")
    if result:
        return result
    return {"status": "not_found", "message": "No recent job found"}


@frappe.whitelist()
def get_customer_360_detail(customer_id: str, include_purchases: bool = True, include_recommendations: bool = True) -> Dict[str, Any]:
    """
    Get comprehensive 360-degree view of a specific customer
    Includes purchase history, cross-sell recommendations, and purchase patterns
    """
    from insights.ml.customer_intelligence import CustomerIntelligence

    try:
        # Only use cached results -- don't trigger a full train() inline
        # as it can crash the worker with large datasets
        model = CustomerIntelligence()
        result = model.get_cached_results("customer_intelligence")

        if not result or result.get('status') != 'success':
            # Fall back to a lightweight direct DB lookup instead of full pipeline
            return _get_customer_360_lightweight(customer_id, include_purchases, include_recommendations)

        customers = result.get('customers', [])
        customer = next((c for c in customers if c['customer_id'] == customer_id), None)

        if not customer:
            # Customer not in cached results -- fall back to lightweight lookup
            return _get_customer_360_lightweight(customer_id, include_purchases, include_recommendations)

        response = {
            "status": "success",
            "customer": customer,
        }

        # Get purchase history
        if include_purchases:
            purchase_history = _get_customer_purchase_history(customer_id)
            response["purchase_history"] = purchase_history
            response["purchase_patterns"] = _analyze_customer_purchase_patterns(purchase_history)

        # Get cross-sell recommendations
        if include_recommendations:
            cross_sell = _get_customer_cross_sell(customer_id, customer.get('clv_tier', 'Bronze'))
            response["cross_sell"] = cross_sell

        # Get next best actions
        actions = [a for a in result.get('next_best_actions', []) if a['customer_id'] == customer_id]
        if actions:
            response["customer"]["recommendations"] = actions[0].get('recommendations', [])

        return response

    except Exception as e:
        frappe.log_error(f"Customer 360 Detail Error: {str(e)[:500]}", "Customer Intelligence")
        return _get_customer_360_lightweight(customer_id, include_purchases, include_recommendations)


def _get_customer_360_lightweight(customer_id: str, include_purchases: bool = True, include_recommendations: bool = True) -> Dict[str, Any]:
    """
    Lightweight fallback for customer 360 detail when the full ML pipeline
    hasn't been run or cached results aren't available.
    """
    try:
        cust = frappe.db.get_value(
            "Customer", customer_id,
            ["name", "customer_name", "customer_group", "territory"],
            as_dict=True,
        )
        if not cust:
            return {"status": "error", "message": f"Customer '{customer_id}' not found"}

        # Basic stats from Sales Invoice
        stats = frappe.db.sql("""
            SELECT
                COUNT(*) as order_count,
                IFNULL(SUM(grand_total), 0) as total_revenue,
                IFNULL(AVG(grand_total), 0) as avg_order_value,
                IFNULL(SUM(outstanding_amount), 0) as outstanding,
                MAX(posting_date) as last_purchase,
                DATEDIFF(CURDATE(), MAX(posting_date)) as recency_days
            FROM `tabSales Invoice`
            WHERE customer = %(cid)s AND docstatus = 1
        """, {"cid": customer_id}, as_dict=True)

        s = stats[0] if stats else {}
        customer = {
            "customer_id": cust.name,
            "customer_name": cust.customer_name,
            "customer_group": cust.customer_group,
            "territory": cust.territory,
            "order_count": int(s.get("order_count") or 0),
            "historical_clv": float(s.get("total_revenue") or 0),
            "avg_order_value": float(s.get("avg_order_value") or 0),
            "outstanding": float(s.get("outstanding") or 0),
            "recency_days": int(s.get("recency_days") or 0),
            "clv_tier": "N/A",
            "health_status": "N/A",
            "health_score": 0,
            "churn_risk": "N/A",
            "churn_score": 0,
            "_lightweight": True,
        }

        response = {"status": "success", "customer": customer}

        if include_purchases:
            purchase_history = _get_customer_purchase_history(customer_id)
            response["purchase_history"] = purchase_history
            response["purchase_patterns"] = _analyze_customer_purchase_patterns(purchase_history)

        if include_recommendations:
            response["cross_sell"] = []

        return response

    except Exception as e:
        frappe.log_error(f"Lightweight 360 Error: {str(e)[:300]}", "Customer Intelligence")
        return {"status": "error", "message": str(e)[:200]}


def _get_customer_purchase_history(customer_id: str) -> List[Dict[str, Any]]:
    """Get detailed purchase history for a customer"""
    query = """
        SELECT
            si.name as invoice_id,
            si.posting_date,
            si.due_date,
            si.grand_total,
            si.net_total,
            si.outstanding_amount,
            si.status,
            CASE
                WHEN si.outstanding_amount = 0 THEN 'Paid'
                WHEN si.due_date < CURDATE() THEN 'Overdue'
                ELSE 'Outstanding'
            END as payment_status
        FROM `tabSales Invoice` si
        WHERE si.customer = %(customer_id)s
        AND si.docstatus = 1
        ORDER BY si.posting_date DESC
        LIMIT 50
    """
    try:
        results = frappe.db.sql(query, {"customer_id": customer_id}, as_dict=True)
        # Plain dicts, not frappe._dict. `_dict.__getattr__` answers ANY attribute,
        # so numpy's `__array_struct__` probe succeeds spuriously and pandas then
        # fails with "invalid __array_struct__" under numpy 2.4. Same conversion
        # `BaseMLModel.get_training_data` already applies for this reason.
        return [dict(row) for row in results] if results else []
    except Exception:
        return []


def _analyze_customer_purchase_patterns(purchase_history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze purchase patterns from history"""
    if not purchase_history or len(purchase_history) < 2:
        return None

    try:
        df = pd.DataFrame(purchase_history)
        df['posting_date'] = pd.to_datetime(df['posting_date'])

        # Calculate average frequency
        df_sorted = df.sort_values('posting_date')
        if len(df_sorted) >= 2:
            date_diffs = df_sorted['posting_date'].diff().dropna()
            avg_frequency = date_diffs.dt.days.mean()
        else:
            avg_frequency = None

        # Preferred day of week
        df['day_of_week'] = df['posting_date'].dt.day_name()
        preferred_day = df['day_of_week'].mode().iloc[0] if len(df) > 0 else None

        # Peak month
        df['month'] = df['posting_date'].dt.month_name()
        month_totals = df.groupby('month')['grand_total'].sum()
        peak_month = month_totals.idxmax() if len(month_totals) > 0 else None

        return {
            "avg_frequency": round(avg_frequency, 1) if avg_frequency else None,
            "preferred_day": preferred_day,
            "peak_month": peak_month,
            "total_purchases": len(df),
            "total_value": float(df['grand_total'].sum())
        }
    except Exception:
        return None


def _normalize_confidence(raw_confidence: float, tier: int) -> float:
    """Normalize confidence to 0-1 range with tier discount.

    Tier 1 (Association Rules): up to 1.0
    Tier 2 (Frequently Bought Together): up to 0.85
    Tier 3 (Category Popular): up to 0.65
    Tier 4 (Expansion): up to 0.45
    Tier 0 (Seasonal): up to 0.95
    """
    tier_ceilings = {0: 0.95, 1: 1.0, 2: 0.85, 3: 0.65, 4: 0.45}
    ceiling = tier_ceilings.get(tier, 0.5)
    normalized = min(max(float(raw_confidence or 0), 0), 1.0)
    return round(normalized * ceiling, 3)


def _get_seasonal_recommendations(customer_id: str, purchased_set: set) -> List[Dict[str, Any]]:
    """Get items this customer typically buys in the current quarter but hasn't bought recently"""
    from datetime import datetime
    current_quarter = (datetime.now().month - 1) // 3 + 1

    try:
        seasonal_items = frappe.db.sql("""
            SELECT sii.item_code, i.item_name, i.item_group,
                   COUNT(*) as seasonal_frequency
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            JOIN `tabItem` i ON sii.item_code = i.name
            WHERE si.customer = %(customer_id)s
              AND si.docstatus = 1
              AND QUARTER(si.posting_date) = %(quarter)s
              AND sii.item_code NOT IN (
                  SELECT DISTINCT sii2.item_code
                  FROM `tabSales Invoice Item` sii2
                  JOIN `tabSales Invoice` si2 ON sii2.parent = si2.name
                  WHERE si2.customer = %(customer_id)s AND si2.docstatus = 1
                    AND si2.posting_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
              )
            GROUP BY sii.item_code
            HAVING seasonal_frequency >= 2
            ORDER BY seasonal_frequency DESC
            LIMIT 5
        """, {"customer_id": customer_id, "quarter": current_quarter}, as_dict=True)

        recommendations = []
        for item in seasonal_items:
            if item['item_code'] not in purchased_set:
                recommendations.append({
                    "item_code": item['item_code'],
                    "item_name": item.get('item_name', item['item_code']),
                    "item_group": item.get('item_group', ''),
                    "confidence": _normalize_confidence(
                        min(item.get('seasonal_frequency', 2) / 5.0, 1.0), tier=0
                    ),
                    "lift": 1.0,
                    "reason": f"Seasonal favorite (Q{current_quarter})",
                    "recommendation_tier": 0
                })
        return recommendations
    except Exception:
        return []


def _get_customer_cross_sell(customer_id: str, clv_tier: str) -> List[Dict[str, Any]]:
    """Get cross-sell recommendations for a customer"""
    try:
        from insights.ml.product_recommendations import ProductRecommendations

        model = ProductRecommendations()
        cached = model.get_cached_results("product_recommendations")

        if not cached:
            # Run recommendations if not cached
            cached = model.train()

        if cached.get('status') != 'success':
            return []

        # Get items this customer has purchased
        purchased_items = frappe.db.sql("""
            SELECT DISTINCT sii.item_code
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.customer = %(customer_id)s AND si.docstatus = 1
        """, {"customer_id": customer_id}, as_dict=True)

        purchased_set = {item['item_code'] for item in purchased_items}

        if not purchased_set:
            return []

        # Priority: Seasonal recommendations first
        seasonal_recs = _get_seasonal_recommendations(customer_id, purchased_set)

        # Get recommendations based on association rules
        recommendations = []
        rules_data = cached.get('association_rules', {})

        # Handle both dict and list formats
        if isinstance(rules_data, dict):
            rules = rules_data.get('top_rules', [])
        elif isinstance(rules_data, list):
            rules = rules_data
        else:
            rules = []

        # Ensure rules is a list
        if not isinstance(rules, list):
            rules = []

        for rule in rules[:50]:  # Check top 50 rules
            antecedent = set(rule.get('antecedent', []))
            consequent = rule.get('consequent', [])

            # If customer has bought antecedent items
            if antecedent.issubset(purchased_set):
                for item_code in consequent:
                    if item_code not in purchased_set:
                        # Get item details
                        item_info = frappe.db.get_value(
                            "Item",
                            item_code,
                            ["item_name", "item_group"],
                            as_dict=True
                        )
                        if item_info:
                            recommendations.append({
                                "item_code": item_code,
                                "item_name": item_info.get('item_name', item_code),
                                "item_group": item_info.get('item_group', ''),
                                "confidence": _normalize_confidence(rule.get('confidence', 0), tier=1),
                                "lift": rule.get('lift', 0),
                                "reason": "Frequently bought together",
                                "recommendation_tier": 1
                            })

        # Remove duplicates and sort by confidence
        seen = set()
        unique_recs = []

        # Add seasonal recommendations first (highest priority)
        for rec in seasonal_recs:
            if rec['item_code'] not in seen:
                seen.add(rec['item_code'])
                unique_recs.append(rec)

        for rec in recommendations:
            if rec['item_code'] not in seen:
                seen.add(rec['item_code'])
                unique_recs.append(rec)

        # If no recommendations from rules, try frequently bought together
        if not unique_recs:
            fbt_pairs = cached.get('frequently_bought_together', [])
            for pair in fbt_pairs[:30]:
                item1, item2 = pair.get('item1'), pair.get('item2')
                # Recommend the item they haven't bought
                if item1 in purchased_set and item2 not in purchased_set:
                    if item2 not in seen:
                        seen.add(item2)
                        unique_recs.append({
                            "item_code": item2,
                            "item_name": pair.get('item2_name', item2),
                            "item_group": "",
                            "confidence": _normalize_confidence(pair.get('support', 0), tier=2),
                            "lift": pair.get('lift', 0),
                            "reason": "Frequently bought together",
                            "recommendation_tier": 2
                        })
                elif item2 in purchased_set and item1 not in purchased_set:
                    if item1 not in seen:
                        seen.add(item1)
                        unique_recs.append({
                            "item_code": item1,
                            "item_name": pair.get('item1_name', item1),
                            "item_group": "",
                            "confidence": _normalize_confidence(pair.get('support', 0), tier=2),
                            "lift": pair.get('lift', 0),
                            "reason": "Frequently bought together",
                            "recommendation_tier": 2
                        })

        # If still no recommendations, suggest popular items from customer's item groups
        if not unique_recs:
            # Get item groups customer buys from
            customer_groups = frappe.db.sql("""
                SELECT DISTINCT i.item_group, COUNT(*) as cnt
                FROM `tabSales Invoice Item` sii
                JOIN `tabSales Invoice` si ON sii.parent = si.name
                JOIN `tabItem` i ON sii.item_code = i.name
                WHERE si.customer = %(customer_id)s AND si.docstatus = 1
                GROUP BY i.item_group
                ORDER BY cnt DESC
                LIMIT 5
            """, {"customer_id": customer_id}, as_dict=True)

            if customer_groups:
                group_names = [g['item_group'] for g in customer_groups if g['item_group']]
                if group_names:
                    # Build placeholders for IN clause
                    placeholders = ', '.join(['%s'] * len(group_names))

                    # Get popular items in those groups that customer hasn't bought
                    popular = frappe.db.sql(f"""
                        SELECT sii.item_code, i.item_name, i.item_group,
                               COUNT(*) as popularity, SUM(sii.qty) as total_qty
                        FROM `tabSales Invoice Item` sii
                        JOIN `tabSales Invoice` si ON sii.parent = si.name
                        JOIN `tabItem` i ON sii.item_code = i.name
                        WHERE si.docstatus = 1
                          AND i.item_group IN ({placeholders})
                          AND sii.item_code NOT IN (
                              SELECT DISTINCT sii2.item_code
                              FROM `tabSales Invoice Item` sii2
                              JOIN `tabSales Invoice` si2 ON sii2.parent = si2.name
                              WHERE si2.customer = %s AND si2.docstatus = 1
                          )
                        GROUP BY sii.item_code
                        ORDER BY popularity DESC
                        LIMIT 10
                    """, tuple(group_names) + (customer_id,), as_dict=True)

                    for item in popular:
                        if item['item_code'] not in seen:
                            seen.add(item['item_code'])
                            unique_recs.append({
                                "item_code": item['item_code'],
                                "item_name": item.get('item_name', item['item_code']),
                                "item_group": item.get('item_group', ''),
                                "confidence": _normalize_confidence(min(item.get('popularity', 1) / 10.0, 1.0), tier=3),
                                "lift": 1.0,
                                "reason": f"Popular in {item.get('item_group', 'category')}",
                                "recommendation_tier": 3
                            })

        # Final fallback: recommend from popular item groups customer doesn't buy from
        if not unique_recs:
            # Get all item groups customer buys from
            all_customer_groups = frappe.db.sql("""
                SELECT DISTINCT i.item_group
                FROM `tabSales Invoice Item` sii
                JOIN `tabSales Invoice` si ON sii.parent = si.name
                JOIN `tabItem` i ON sii.item_code = i.name
                WHERE si.customer = %(customer_id)s AND si.docstatus = 1
            """, {"customer_id": customer_id})
            customer_group_names = set(g[0] for g in all_customer_groups if g[0])

            # Get top selling item groups overall
            top_groups = frappe.db.sql("""
                SELECT i.item_group, COUNT(*) as cnt
                FROM `tabSales Invoice Item` sii
                JOIN `tabSales Invoice` si ON sii.parent = si.name
                JOIN `tabItem` i ON sii.item_code = i.name
                WHERE si.docstatus = 1 AND i.item_group IS NOT NULL
                GROUP BY i.item_group
                ORDER BY cnt DESC
                LIMIT 20
            """, as_dict=True)

            # Find groups customer doesn't buy from
            new_groups = [g['item_group'] for g in top_groups if g['item_group'] not in customer_group_names][:5]

            if new_groups:
                placeholders = ', '.join(['%s'] * len(new_groups))
                new_group_items = frappe.db.sql(f"""
                    SELECT sii.item_code, i.item_name, i.item_group,
                           COUNT(*) as popularity
                    FROM `tabSales Invoice Item` sii
                    JOIN `tabSales Invoice` si ON sii.parent = si.name
                    JOIN `tabItem` i ON sii.item_code = i.name
                    WHERE si.docstatus = 1
                      AND i.item_group IN ({placeholders})
                    GROUP BY sii.item_code
                    ORDER BY popularity DESC
                    LIMIT 10
                """, tuple(new_groups), as_dict=True)

                for item in new_group_items:
                    if item['item_code'] not in seen:
                        seen.add(item['item_code'])
                        unique_recs.append({
                            "item_code": item['item_code'],
                            "item_name": item.get('item_name', item['item_code']),
                            "item_group": item.get('item_group', ''),
                            "confidence": _normalize_confidence(min(item.get('popularity', 1) / 100.0, 1.0), tier=4),
                            "lift": 1.0,
                            "reason": f"Explore {item.get('item_group', 'new category')}",
                            "recommendation_tier": 4
                        })

        unique_recs.sort(key=lambda x: x['confidence'], reverse=True)
        return unique_recs[:10]

    except Exception as e:
        frappe.log_error(f"Cross-sell error: {str(e)}", "Customer Intelligence")
        return []


@frappe.whitelist()
def get_purchase_patterns(top_percentile: int = 20, tier_filter: str = None) -> Dict[str, Any]:
    """
    Get purchase patterns for top customers by CLV
    Analyzes day-of-week, monthly, and seasonal patterns
    """
    result = get_customer_intelligence()

    if result.get('status') != 'success':
        return result

    customers = result.get('customers', [])
    if not customers:
        return {"status": "error", "message": "No customer data available"}

    # Filter customers by tier or top percentile by CLV
    if tier_filter:
        tiers = [t.strip() for t in tier_filter.split(',')]
        top_customers = [c for c in customers if c.get('clv_tier') in tiers]
    else:
        customers_sorted = sorted(customers, key=lambda x: x.get('historical_clv', 0), reverse=True)
        top_count = max(1, int(len(customers_sorted) * top_percentile / 100))
        top_customers = customers_sorted[:top_count]

    top_customer_ids = [c['customer_id'] for c in top_customers]

    # Get transactions for top customers
    placeholders = ', '.join(['%s'] * len(top_customer_ids))
    query = f"""
        SELECT
            si.customer,
            si.posting_date,
            si.grand_total,
            DAYNAME(si.posting_date) as day_name,
            DAYOFWEEK(si.posting_date) as day_of_week,
            MONTH(si.posting_date) as month_num,
            MONTHNAME(si.posting_date) as month_name,
            QUARTER(si.posting_date) as quarter,
            HOUR(si.creation) as hour_of_day
        FROM `tabSales Invoice` si
        WHERE si.customer IN ({placeholders})
        AND si.docstatus = 1
        AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
        ORDER BY si.posting_date
    """

    try:
        transactions = frappe.db.sql(query, tuple(top_customer_ids), as_dict=True)

        if not transactions:
            return {"status": "success", "message": "No transaction data", "patterns": None}

        # Plain dicts, not frappe._dict, or pandas raises
        # "invalid __array_struct__" under numpy 2.4 and this whole tab renders
        # an unpopulated template. See `_get_customer_purchase_history`.
        df = pd.DataFrame([dict(row) for row in transactions])

        # Day of week analysis
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_analysis = df.groupby('day_name').agg({
            'grand_total': ['count', 'sum', 'mean']
        }).round(2)
        day_analysis.columns = ['order_count', 'total_revenue', 'avg_order_value']
        day_analysis = day_analysis.reindex(day_order).fillna(0)

        # Monthly analysis
        month_order = ['January', 'February', 'March', 'April', 'May', 'June',
                       'July', 'August', 'September', 'October', 'November', 'December']
        month_analysis = df.groupby('month_name').agg({
            'grand_total': ['count', 'sum', 'mean']
        }).round(2)
        month_analysis.columns = ['order_count', 'total_revenue', 'avg_order_value']
        month_analysis = month_analysis.reindex(month_order).fillna(0)

        # Quarterly/Seasonal analysis
        quarter_analysis = df.groupby('quarter').agg({
            'grand_total': ['count', 'sum', 'mean']
        }).round(2)
        quarter_analysis.columns = ['order_count', 'total_revenue', 'avg_order_value']
        quarter_names = {1: 'Q1 (Jan-Mar)', 2: 'Q2 (Apr-Jun)', 3: 'Q3 (Jul-Sep)', 4: 'Q4 (Oct-Dec)'}

        # Peak analysis
        peak_day = day_analysis['order_count'].idxmax() if not day_analysis.empty else None
        peak_month = month_analysis['total_revenue'].idxmax() if not month_analysis.empty else None
        peak_quarter = quarter_analysis['total_revenue'].idxmax() if not quarter_analysis.empty else None

        return {
            "status": "success",
            "analysis_scope": {
                "top_percentile": top_percentile,
                "customer_count": len(top_customers),
                "transaction_count": len(transactions),
                "date_range": "Last 12 months"
            },
            "day_of_week": {
                "data": day_analysis.reset_index().to_dict('records'),
                "peak_day": peak_day,
                "heatmap": day_analysis['order_count'].to_dict()
            },
            "monthly": {
                "data": month_analysis.reset_index().to_dict('records'),
                "peak_month": peak_month,
                "trend": month_analysis['total_revenue'].to_dict()
            },
            "seasonal": {
                "data": [
                    {
                        "quarter": quarter_names.get(int(idx), f"Q{int(idx)}"),
                        **row.to_dict()
                    }
                    for idx, row in quarter_analysis.iterrows()
                ],
                "peak_quarter": quarter_names.get(peak_quarter, None)
            },
            "summary": {
                "total_orders": len(transactions),
                "total_revenue": float(df['grand_total'].sum()),
                "avg_order_value": float(df['grand_total'].mean()),
                "peak_day": peak_day,
                "peak_month": peak_month
            }
        }

    except Exception as e:
        frappe.log_error(f"Purchase patterns error: {str(e)}", "Customer Intelligence")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_cross_sell_opportunities(tier_filter: str = "Diamond,Platinum,Gold") -> Dict[str, Any]:
    """
    Get cross-sell opportunities for customers in specified CLV tiers
    """
    result = get_customer_intelligence()

    if result.get('status') != 'success':
        return result

    # Filter customers by tier
    tiers = [t.strip() for t in tier_filter.split(',')]
    customers = [c for c in result.get('customers', []) if c.get('clv_tier') in tiers]

    if not customers:
        return {"status": "success", "message": "No customers in specified tiers", "opportunities": []}

    # Get cross-sell for each customer
    opportunities = []
    for customer in customers[:50]:  # Limit to top 50
        cross_sell = _get_customer_cross_sell(customer['customer_id'], customer.get('clv_tier', 'Bronze'))
        if cross_sell:
            opportunities.append({
                "customer_id": customer['customer_id'],
                "customer_name": customer.get('customer_name', ''),
                "clv_tier": customer.get('clv_tier', ''),
                "historical_clv": customer.get('historical_clv', 0),
                "health_status": customer.get('health_status', ''),
                "recommendations": cross_sell[:5]  # Top 5 per customer
            })

    # Sort by CLV
    opportunities.sort(key=lambda x: x['historical_clv'], reverse=True)

    return {
        "status": "success",
        "tier_filter": tiers,
        "customer_count": len(opportunities),
        "opportunities": opportunities
    }


@frappe.whitelist()
def get_at_risk_customers() -> Dict[str, Any]:
    """Get customers at high churn risk"""
    result = get_customer_intelligence()

    if result.get('status') != 'success':
        return result

    return {
        "status": "success",
        "at_risk_count": len(result.get('at_risk_customers', [])),
        "customers": result.get('at_risk_customers', [])
    }


@frappe.whitelist()
def get_geographic_insights() -> Dict[str, Any]:
    """Get geographic analysis"""
    result = get_customer_intelligence()

    if result.get('status') != 'success':
        return result

    return {
        "status": "success",
        "geographic_analysis": result.get('geographic_analysis', {})
    }


@frappe.whitelist()
def get_next_actions() -> Dict[str, Any]:
    """Get next best action recommendations"""
    result = get_customer_intelligence()

    if result.get('status') != 'success':
        return result

    return {
        "status": "success",
        "total_actions": len(result.get('next_best_actions', [])),
        "actions": result.get('next_best_actions', [])
    }


@frappe.whitelist()
def get_pareto_analysis() -> Dict[str, Any]:
    """Get 80/20 Pareto analysis"""
    result = get_customer_intelligence()

    if result.get('status') != 'success':
        return result

    return {
        "status": "success",
        "pareto_analysis": result.get('pareto_analysis', {})
    }


@frappe.whitelist()
def get_cohort_analysis() -> Dict[str, Any]:
    """Get cohort retention analysis"""
    result = get_customer_intelligence()

    if result.get('status') != 'success':
        return result

    return {
        "status": "success",
        "cohort_analysis": result.get('cohort_analysis', {})
    }


@frappe.whitelist()
def refresh_customer_scores() -> Dict[str, Any]:
    """Force refresh and update all customer scores"""
    from insights.ml.customer_intelligence import CustomerIntelligence

    model = CustomerIntelligence()
    return model.train(update_customers=True)
