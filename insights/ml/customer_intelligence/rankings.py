from __future__ import annotations
# insights/ml/customer_intelligence/rankings.py
"""Customer ranking calculations."""

import frappe
from typing import Dict, Any, List, TYPE_CHECKING
if TYPE_CHECKING:
    import numpy as np


def get_customer_rankings(intelligence, limit: int = 20) -> Dict[str, List]:
    """Get top customer rankings by multiple dimensions."""
    period_start = intelligence.period_start
    period_end = intelligence.period_end

    # Top by Revenue
    revenue_query = """
        SELECT si.customer, si.customer_name,
               SUM(si.grand_total) as revenue
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
        AND si.posting_date BETWEEN %s AND %s
        GROUP BY si.customer
        ORDER BY revenue DESC
        LIMIT %s
    """
    top_revenue = frappe.db.sql(revenue_query, (period_start, period_end, limit), as_dict=True)

    # Top by Gross Profit (item-level)
    profit_query = """
        SELECT si.customer, si.customer_name,
               SUM(sii.net_amount - (sii.qty * COALESCE(sii.incoming_rate, 0))) as gross_profit,
               SUM(sii.amount) as revenue
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.docstatus = 1
        AND si.posting_date BETWEEN %s AND %s
        GROUP BY si.customer
        ORDER BY gross_profit DESC
        LIMIT %s
    """
    top_profit = frappe.db.sql(profit_query, (period_start, period_end, limit), as_dict=True)

    # Top by Margin %
    margin_query = """
        SELECT si.customer, si.customer_name,
               SUM(sii.net_amount - (sii.qty * COALESCE(sii.incoming_rate, 0))) as gross_profit,
               SUM(sii.amount) as revenue,
               ROUND(SUM(sii.net_amount - (sii.qty * COALESCE(sii.incoming_rate, 0))) / NULLIF(SUM(sii.amount), 0) * 100, 1) as margin_pct
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.docstatus = 1
        AND si.posting_date BETWEEN %s AND %s
        GROUP BY si.customer
        HAVING revenue > 0
        ORDER BY margin_pct DESC
        LIMIT %s
    """
    top_margin = frappe.db.sql(margin_query, (period_start, period_end, limit), as_dict=True)

    # Top Consistent (composite score)
    top_consistent = _calculate_consistency_scores(period_start, period_end, limit)

    return {
        "top_revenue": [dict(r) for r in top_revenue],
        "top_profit": [dict(r) for r in top_profit],
        "top_margin": [dict(r) for r in top_margin],
        "top_consistent": top_consistent,
    }


def _calculate_consistency_scores(period_start, period_end, limit: int) -> List[Dict]:
    """
    Composite consistency = 0.5 * frequency_score + 0.5 * spend_stability_score
    frequency_score = months_with_orders / total_months_in_period
    spend_stability_score = 1 - coefficient_of_variation(monthly_spend)
    """
    import numpy as np
    monthly_query = """
        SELECT si.customer, si.customer_name,
               DATE_FORMAT(si.posting_date, '%%Y-%%m') as month,
               SUM(si.grand_total) as monthly_spend
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
        AND si.posting_date BETWEEN %s AND %s
        GROUP BY si.customer, month
    """
    rows = frappe.db.sql(monthly_query, (period_start, period_end), as_dict=True)
    if not rows:
        return []

    # Calculate total months in period
    from dateutil.relativedelta import relativedelta
    from datetime import datetime
    start = datetime.strptime(str(period_start), "%Y-%m-%d")
    end = datetime.strptime(str(period_end), "%Y-%m-%d")
    total_months = max((end.year - start.year) * 12 + (end.month - start.month), 1)

    # Group by customer
    customer_months = {}
    for row in rows:
        cust = row["customer"]
        if cust not in customer_months:
            customer_months[cust] = {
                "customer_name": row["customer_name"],
                "spends": [],
            }
        customer_months[cust]["spends"].append(float(row["monthly_spend"]))

    results = []
    for customer, data in customer_months.items():
        spends = data["spends"]
        months_active = len(spends)

        frequency_score = months_active / total_months

        mean_spend = float(np.mean(spends))
        std_spend = float(np.std(spends))
        cv = std_spend / mean_spend if mean_spend > 0 else 1.0
        stability_score = max(0.0, 1.0 - cv)

        composite = round(0.5 * frequency_score + 0.5 * stability_score, 3)

        results.append({
            "customer": customer,
            "customer_name": data["customer_name"],
            "months_active": months_active,
            "total_months": total_months,
            "frequency_score": round(frequency_score, 3),
            "stability_score": round(stability_score, 3),
            "consistency_score": composite,
            "avg_monthly_spend": round(mean_spend, 2),
        })

    results.sort(key=lambda x: x["consistency_score"], reverse=True)
    return results[:limit]
