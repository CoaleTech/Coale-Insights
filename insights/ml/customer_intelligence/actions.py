# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Customer Intelligence - Actions
Geographic analysis, next best actions, customer score updates,
product affinity, pareto analysis, and cohort analysis.
"""

import frappe
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List

from insights.ml.territory_geo_mapper import map_territories_bulk


def analyze_geography(intelligence, health_df: pd.DataFrame, territory_df: pd.DataFrame) -> Dict[str, Any]:
    """Geographic distribution analysis using ERPNext territories"""
    # Territory-level analysis
    territory_analysis = health_df.groupby('territory').agg({
        'customer_id': 'count',
        'historical_clv': 'sum',
        'avg_order_value': 'mean',
        'churn_score': 'mean',
        'health_score': 'mean',
        'order_count': 'sum'
    }).reset_index()
    territory_analysis.columns = [
        'territory', 'customer_count', 'total_revenue', 'avg_order_value',
        'avg_churn_risk', 'avg_health_score', 'total_orders'
    ]
    territory_analysis = territory_analysis.sort_values('total_revenue', ascending=False)

    # Merge with territory hierarchy
    if not territory_df.empty:
        territory_analysis = territory_analysis.merge(
            territory_df[['territory', 'parent_territory', 'territory_manager']],
            on='territory',
            how='left'
        )

    # Customer group analysis
    group_analysis = health_df.groupby('customer_group').agg({
        'customer_id': 'count',
        'historical_clv': 'sum',
        'avg_order_value': 'mean',
        'health_score': 'mean'
    }).reset_index()
    group_analysis.columns = [
        'customer_group', 'customer_count', 'total_revenue', 'avg_order_value', 'avg_health_score'
    ]
    group_analysis = group_analysis.sort_values('total_revenue', ascending=False)

    # Territory performance metrics
    total_revenue = territory_analysis['total_revenue'].sum()
    territory_analysis['revenue_share'] = (
        territory_analysis['total_revenue'] / total_revenue * 100
    ).round(2) if total_revenue > 0 else 0

    # Penetration rate
    total_customers = territory_analysis['customer_count'].sum()
    territory_analysis['customer_share'] = (
        territory_analysis['customer_count'] / total_customers * 100
    ).round(2) if total_customers > 0 else 0

    # Map data for frontend
    map_data = territory_analysis[[
        'territory', 'customer_count', 'total_revenue', 'avg_health_score', 'revenue_share'
    ]].to_dict('records')

    # Geo projection for the choropleth. `map_data` is territory rows keyed by the
    # ERPNext territory name, which no map can render; the mapper resolves each to
    # an ISO country code or an India state and reports what it could not place.
    # Without this the map component received empty arrays and painted every
    # country the same grey with a 0-1 legend.
    territory_geo = map_territories_bulk(
        map_data, territory_field='territory', value_field='customer_count'
    )

    return {
        'territory_analysis': territory_analysis.to_dict('records'),
        'customer_group_analysis': group_analysis.to_dict('records'),
        'map_data': map_data,
        'territory_geo': territory_geo,
        'top_territories': territory_analysis.head(10).to_dict('records'),
        'coverage': {
            'territories_covered': len(territory_analysis),
            'customer_groups_covered': len(group_analysis),
            'total_revenue': float(total_revenue),
            'total_customers': int(total_customers)
        }
    }


def analyze_product_affinity(intelligence, items_df: pd.DataFrame, health_df: pd.DataFrame) -> Dict[str, Any]:
    """Product category preferences by customer segment"""
    if items_df.empty:
        return {'tier_preferences': [], 'top_categories': [], 'brand_analysis': []}

    # Merge with customer segments
    affinity_data = items_df.merge(
        health_df[['customer_id', 'clv_tier', 'health_status']],
        on='customer_id',
        how='left'
    )

    # Category preferences by CLV tier
    tier_preferences = affinity_data.groupby(['clv_tier', 'item_group']).agg({
        'total_amount': 'sum',
        'customer_id': 'nunique',
        'order_count': 'sum'
    }).reset_index()
    tier_preferences.columns = ['clv_tier', 'item_group', 'total_revenue', 'customer_count', 'order_count']

    # Top categories overall
    top_categories = affinity_data.groupby('item_group').agg({
        'total_amount': 'sum',
        'customer_id': 'nunique'
    }).reset_index()
    top_categories.columns = ['item_group', 'total_revenue', 'customer_count']
    top_categories = top_categories.sort_values('total_revenue', ascending=False)

    # Brand preferences
    brand_analysis = affinity_data.groupby('brand').agg({
        'total_amount': 'sum',
        'customer_id': 'nunique'
    }).reset_index()
    brand_analysis.columns = ['brand', 'total_revenue', 'customer_count']
    brand_analysis = brand_analysis.sort_values('total_revenue', ascending=False)

    return {
        'tier_preferences': tier_preferences.to_dict('records'),
        'top_categories': top_categories.head(20).to_dict('records'),
        'brand_analysis': brand_analysis.head(20).to_dict('records')
    }


def pareto_analysis(intelligence, health_df: pd.DataFrame) -> Dict[str, Any]:
    """80/20 analysis - identify top customers by revenue contribution"""
    if health_df.empty or health_df['historical_clv'].sum() == 0:
        return {
            'total_customers': 0, 'total_revenue': 0, 'top_80_percent_customers': 0,
            'top_10_percent_contribute': 0, 'top_20_percent_contribute': 0,
            'top_customers': [], 'pareto_curve': []
        }

    # Sort by revenue
    sorted_df = health_df.sort_values('historical_clv', ascending=False).copy()
    sorted_df['cumulative_revenue'] = sorted_df['historical_clv'].cumsum()
    total_revenue = sorted_df['historical_clv'].sum()
    sorted_df['cumulative_percent'] = (sorted_df['cumulative_revenue'] / total_revenue) * 100

    # Find 80% cutoff
    top_80 = sorted_df[sorted_df['cumulative_percent'] <= 80]
    top_80_percent = (len(top_80) / len(sorted_df)) * 100 if len(sorted_df) > 0 else 0

    # Revenue concentration
    n_10 = max(1, int(len(sorted_df) * 0.1))
    n_20 = max(1, int(len(sorted_df) * 0.2))
    top_10_revenue = sorted_df.head(n_10)['historical_clv'].sum()
    top_20_revenue = sorted_df.head(n_20)['historical_clv'].sum()

    return {
        'total_customers': len(sorted_df),
        'total_revenue': float(total_revenue),
        'top_80_percent_customers': round(top_80_percent, 1),
        'top_10_percent_contribute': round((top_10_revenue / total_revenue) * 100, 1) if total_revenue > 0 else 0,
        'top_20_percent_contribute': round((top_20_revenue / total_revenue) * 100, 1) if total_revenue > 0 else 0,
        'top_customers': sorted_df.head(20)[[
            'customer_id', 'customer_name', 'historical_clv', 'order_count',
            'avg_order_value', 'clv_tier', 'health_status'
        ]].assign(cumulative_percent=sorted_df.head(20)['cumulative_percent']).to_dict('records'),
        'pareto_curve': sorted_df[['customer_name', 'historical_clv', 'cumulative_percent']].head(50).to_dict('records')
    }


def cohort_analysis(intelligence, customer_df: pd.DataFrame) -> Dict[str, Any]:
    """Customer retention cohort analysis"""
    df = customer_df[customer_df['invoice_id'].notna()].copy()

    if df.empty:
        return {'cohort_retention': [], 'average_retention': {}, 'cohort_count': 0}

    df['posting_date'] = pd.to_datetime(df['posting_date'])

    # Get first purchase date per customer (cohort)
    first_purchase = df.groupby('customer_id')['posting_date'].min().reset_index()
    first_purchase.columns = ['customer_id', 'first_purchase']
    first_purchase['cohort_month'] = first_purchase['first_purchase'].dt.to_period('M')

    df = df.merge(first_purchase[['customer_id', 'cohort_month']], on='customer_id')
    df['transaction_month'] = df['posting_date'].dt.to_period('M')

    # Calculate period number
    df['period_number'] = (
        df['transaction_month'].astype('int64') - df['cohort_month'].astype('int64')
    )

    # Cohort matrix
    cohort_data = df.groupby(['cohort_month', 'period_number']).agg({
        'customer_id': 'nunique'
    }).reset_index()
    cohort_data.columns = ['cohort_month', 'period_number', 'customers']

    # Pivot for retention matrix
    cohort_pivot = cohort_data.pivot(
        index='cohort_month', columns='period_number', values='customers'
    ).fillna(0)

    # Calculate retention percentages
    cohort_sizes = cohort_pivot.iloc[:, 0] if len(cohort_pivot.columns) > 0 else pd.Series([0])
    retention_matrix = cohort_pivot.divide(cohort_sizes.replace(0, 1), axis=0) * 100

    # Convert to serializable format
    cohort_result = []
    for idx, row in retention_matrix.iterrows():
        cohort_result.append({
            'cohort': str(idx),
            'size': int(cohort_sizes.get(idx, 0)),
            'retention': {int(k): round(v, 1) for k, v in row.items() if not pd.isna(v)}
        })

    # Average retention by period
    avg_retention = retention_matrix.mean().to_dict()
    avg_retention = {int(k): round(v, 1) for k, v in avg_retention.items() if not pd.isna(v)}

    return {
        'cohort_retention': cohort_result[-12:],
        'average_retention': avg_retention,
        'cohort_count': len(cohort_result)
    }


def get_next_best_actions(intelligence, health_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """AI-driven next best action recommendations per customer"""
    actions = []

    for _, customer in health_df.iterrows():
        customer_actions = {
            'customer_id': customer['customer_id'],
            'customer_name': customer['customer_name'],
            'clv_tier': str(customer['clv_tier']) if pd.notna(customer['clv_tier']) else 'Unknown',
            'health_status': str(customer['health_status']) if pd.notna(customer['health_status']) else 'Unknown',
            'churn_risk': str(customer['churn_risk']) if pd.notna(customer['churn_risk']) else 'Unknown',
            'recommendations': []
        }

        churn_risk = str(customer.get('churn_risk', ''))
        clv_tier = str(customer.get('clv_tier', ''))
        health_status = str(customer.get('health_status', ''))
        recency_days = customer.get('recency_days', 0) or 0
        outstanding = customer.get('outstanding_amount', 0) or 0
        aov = customer.get('avg_order_value', 0) or 0
        freq_trend = customer.get('frequency_trend', 0) or 0
        value_trend = customer.get('value_trend', 0) or 0

        # Churn prevention
        if churn_risk in ['High', 'Critical']:
            customer_actions['recommendations'].append({
                'action': 'CHURN_PREVENTION',
                'priority': 'High',
                'description': f"Customer at {churn_risk} churn risk. Last purchase {int(recency_days)} days ago.",
                'suggestion': "Schedule personal outreach call, offer loyalty discount, or exclusive preview of new products."
            })

        # Upsell opportunity
        if clv_tier in ['Gold', 'Platinum', 'Diamond'] and health_status in ['Healthy', 'Excellent']:
            customer_actions['recommendations'].append({
                'action': 'UPSELL_OPPORTUNITY',
                'priority': 'Medium',
                'description': f"High-value customer with strong engagement. AOV: {aov:,.0f}",
                'suggestion': "Introduce premium product lines, volume discounts, or exclusive partnerships."
            })

        # Payment follow-up
        if outstanding > 0:
            priority = 'High' if outstanding > aov * 2 else 'Medium'
            customer_actions['recommendations'].append({
                'action': 'PAYMENT_FOLLOW_UP',
                'priority': priority,
                'description': f"Outstanding balance: {outstanding:,.0f}",
                'suggestion': "Send payment reminder, offer payment plan if needed."
            })

        # Re-engagement
        if recency_days > 60 and clv_tier in ['Silver', 'Gold', 'Platinum', 'Diamond']:
            customer_actions['recommendations'].append({
                'action': 'RE_ENGAGEMENT',
                'priority': 'High',
                'description': f"Valuable customer inactive for {int(recency_days)} days.",
                'suggestion': "Send 'We miss you' campaign with personalized offer based on past purchases."
            })

        # Growth opportunity
        if freq_trend > 0.2 and value_trend > 0.1:
            customer_actions['recommendations'].append({
                'action': 'GROWTH_OPPORTUNITY',
                'priority': 'Medium',
                'description': "Customer showing positive growth trends in frequency and order value.",
                'suggestion': "Consider for VIP program, early access to new products, or referral program."
            })

        # New customer nurturing
        if customer.get('order_count', 0) <= 2 and recency_days < 60:
            customer_actions['recommendations'].append({
                'action': 'NEW_CUSTOMER_NURTURE',
                'priority': 'Medium',
                'description': "New customer - critical period for relationship building.",
                'suggestion': "Send welcome series, offer first-time buyer discount on next purchase, request feedback."
            })

        if customer_actions['recommendations']:
            actions.append(customer_actions)

    # Sort by priority
    actions.sort(key=lambda x: (
        0 if any(r['priority'] == 'High' for r in x['recommendations']) else 1,
        -len(x['recommendations'])
    ))

    return actions[:100]


def update_customer_scores(intelligence, health_df: pd.DataFrame) -> Dict[str, Any]:
    """Write calculated scores back to Customer doctype custom fields.

    Uses bulk SQL UPDATE with CASE statements instead of row-by-row
    frappe.db.set_value() to avoid N+1 update pattern (was thousands of
    UPDATE queries for large customer bases).
    """
    updated = 0
    errors = []

    if health_df.empty:
        return {"status": "skipped", "message": "No data to update"}

    # Check if custom fields exist (only once, not per-row)
    if not frappe.db.exists("Custom Field", {"dt": "Customer", "fieldname": "custom_clv_tier"}):
        return {
            "status": "skipped",
            "message": "Custom fields not installed. Run 'bench migrate' to create them."
        }

    # Process in batches of 500 to avoid overly large SQL statements
    BATCH_SIZE = 500
    rows = list(health_df.iterrows())

    for batch_start in range(0, len(rows), BATCH_SIZE):
        batch = rows[batch_start:batch_start + BATCH_SIZE]
        customer_ids = []
        clv_tier_cases = []
        clv_score_cases = []
        churn_risk_cases = []
        churn_score_cases = []
        health_score_cases = []
        health_status_cases = []

        for _, row in batch:
            try:
                cid = row['customer_id']
                customer_ids.append(cid)

                clv_tier = str(row['clv_tier']) if pd.notna(row.get('clv_tier')) else None
                clv_score = float(row['clv_score']) if pd.notna(row.get('clv_score')) else 0
                churn_risk = str(row['churn_risk']) if pd.notna(row.get('churn_risk')) else None
                churn_score = float(row['churn_score']) if pd.notna(row.get('churn_score')) else 0
                health_score = float(row['health_score']) if pd.notna(row.get('health_score')) else 0
                health_status = str(row['health_status']) if pd.notna(row.get('health_status')) else None

                clv_tier_cases.append((cid, clv_tier))
                clv_score_cases.append((cid, clv_score))
                churn_risk_cases.append((cid, churn_risk))
                churn_score_cases.append((cid, churn_score))
                health_score_cases.append((cid, health_score))
                health_status_cases.append((cid, health_status))
            except Exception as e:
                errors.append(f"{row.get('customer_id', '?')}: {str(e)}")

        if not customer_ids:
            continue

        # Build bulk UPDATE with CASE WHEN
        def build_case(cases, default="NULL"):
            parts = []
            params = []
            for cid, val in cases:
                parts.append("WHEN %s THEN %s")
                params.extend([cid, val])
            return "CASE `name` " + " ".join(parts) + f" ELSE {default} END", params

        clv_tier_sql, clv_tier_params = build_case(clv_tier_cases)
        clv_score_sql, clv_score_params = build_case(clv_score_cases, "0")
        churn_risk_sql, churn_risk_params = build_case(churn_risk_cases)
        churn_score_sql, churn_score_params = build_case(churn_score_cases, "0")
        health_score_sql, health_score_params = build_case(health_score_cases, "0")
        health_status_sql, health_status_params = build_case(health_status_cases)

        placeholders = ", ".join(["%s"] * len(customer_ids))

        sql = f"""
            UPDATE `tabCustomer`
            SET
                custom_clv_tier = {clv_tier_sql},
                custom_clv_score = {clv_score_sql},
                custom_churn_risk = {churn_risk_sql},
                custom_churn_score = {churn_score_sql},
                custom_health_score = {health_score_sql},
                custom_health_status = {health_status_sql},
                custom_last_ml_update = %s
            WHERE `name` IN ({placeholders})
        """

        all_params = (
            clv_tier_params + clv_score_params + churn_risk_params +
            churn_score_params + health_score_params + health_status_params +
            [datetime.now()] + customer_ids
        )

        try:
            frappe.db.sql(sql, tuple(all_params))
            updated += len(customer_ids)
        except Exception as e:
            errors.append(f"Batch update failed: {str(e)}")

    if updated > 0:
        frappe.db.commit()

    return {
        "status": "success",
        "updated": updated,
        "errors": errors[:10] if errors else []
    }
