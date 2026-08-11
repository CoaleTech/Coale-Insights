from __future__ import annotations
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Customer Intelligence - Analytics
CLV calculation, RFM segmentation, churn risk prediction, and health scoring.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, TYPE_CHECKING
if TYPE_CHECKING:
    import pandas as pd
    import numpy as np


def calculate_clv(intelligence, customer_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Customer Lifetime Value using historical + predictive methods

    Components:
    - Historical CLV: Total revenue to date
    - Predictive CLV: Based on purchase patterns (BG/NBD simplified)
    - CLV Tier: Bronze/Silver/Gold/Platinum/Diamond
    """
    import pandas as pd
    import numpy as np
    # Calculate overdue count per customer before aggregation
    if 'payment_status' in customer_df.columns:
        overdue_df = customer_df[customer_df['payment_status'] == 'Overdue'].groupby('customer_id').size().reset_index(name='overdue_count')
    else:
        overdue_df = pd.DataFrame(columns=['customer_id', 'overdue_count'])

    # Group by customer
    clv_data = customer_df.groupby('customer_id').agg({
        'grand_total': ['sum', 'mean', 'count'],
        'posting_date': ['min', 'max'],
        'customer_name': 'first',
        'customer_group': 'first',
        'territory': 'first',
        'outstanding_amount': 'sum'
    }).reset_index()

    clv_data.columns = [
        'customer_id', 'historical_clv', 'avg_order_value', 'order_count',
        'first_purchase', 'last_purchase', 'customer_name', 'customer_group',
        'territory', 'outstanding_amount'
    ]

    # Merge overdue count
    clv_data = clv_data.merge(overdue_df, on='customer_id', how='left')
    clv_data['overdue_count'] = clv_data['overdue_count'].fillna(0).astype(int)

    # Handle NaN values
    clv_data['historical_clv'] = clv_data['historical_clv'].fillna(0)
    clv_data['avg_order_value'] = clv_data['avg_order_value'].fillna(0)
    clv_data['order_count'] = clv_data['order_count'].fillna(0)
    clv_data['outstanding_amount'] = clv_data['outstanding_amount'].fillna(0)

    # Calculate customer lifespan in months
    clv_data['first_purchase'] = pd.to_datetime(clv_data['first_purchase'])
    clv_data['last_purchase'] = pd.to_datetime(clv_data['last_purchase'])

    # Handle customers with no purchases
    now = pd.Timestamp.now()
    clv_data['first_purchase'] = clv_data['first_purchase'].fillna(now)
    clv_data['last_purchase'] = clv_data['last_purchase'].fillna(now)

    clv_data['lifespan_months'] = (
        (clv_data['last_purchase'] - clv_data['first_purchase']).dt.days / 30.44
    ).clip(lower=1)

    # Purchase frequency (orders per month)
    clv_data['purchase_frequency'] = clv_data['order_count'] / clv_data['lifespan_months']

    # Recency (days since last purchase)
    clv_data['recency_days'] = (now - clv_data['last_purchase']).dt.days

    # Predictive CLV (simplified BG/NBD: project 12 months forward)
    clv_data['predicted_12m_clv'] = (
        clv_data['purchase_frequency'] * 12 * clv_data['avg_order_value']
    )

    # Customer tenure factor (longer customers get loyalty boost)
    tenure_months = (now - clv_data['first_purchase']).dt.days / 30.44
    clv_data['tenure_factor'] = np.minimum(tenure_months / 24, 1.5)

    # Adjusted predictive CLV
    clv_data['adjusted_predicted_clv'] = (
        clv_data['predicted_12m_clv'] * clv_data['tenure_factor']
    )

    # Total CLV (historical + predicted)
    clv_data['total_clv'] = clv_data['historical_clv'] + clv_data['adjusted_predicted_clv']

    # CLV Score (normalized 0-100)
    max_clv = clv_data['total_clv'].quantile(0.99) or 1
    clv_data['clv_score'] = (clv_data['total_clv'] / max_clv * 100).clip(0, 100)

    # CLV Tier - use score-based assignment to handle edge cases
    def assign_clv_tier(score):
        if score >= 80:
            return 'Diamond'
        elif score >= 60:
            return 'Platinum'
        elif score >= 40:
            return 'Gold'
        elif score >= 20:
            return 'Silver'
        else:
            return 'Bronze'

    clv_data['clv_tier'] = clv_data['clv_score'].apply(assign_clv_tier)

    # ==================== CLV COMPONENT SCORES ====================
    # Calculate individual component scores (0-100 scale) for the CLV breakdown
    clv_data = _calculate_clv_components(clv_data, tenure_months)

    # ==================== RFM SEGMENTATION ====================
    # Calculate RFM scores using quintiles (1-5)
    clv_data = _calculate_rfm_segment(clv_data)

    return clv_data


def _calculate_clv_components(df: pd.DataFrame, tenure_months: pd.Series) -> pd.DataFrame:
    """
    Calculate CLV component scores for detailed breakdown:
    - Revenue Score: Based on historical revenue relative to peers
    - Engagement Score: Based on order frequency and recency
    - Longevity Score: Based on customer tenure/relationship length
    - Growth Score: Based on predicted CLV growth potential
    """
    if df.empty:
        return df

    # Revenue Score (0-100): Percentile rank of historical CLV
    max_revenue = df['historical_clv'].quantile(0.99) or 1
    df['revenue_score'] = (df['historical_clv'] / max_revenue * 100).clip(0, 100)

    # Engagement Score (0-100): Combination of frequency and recency
    # Higher frequency = better, Lower recency = better
    max_freq = df['purchase_frequency'].quantile(0.99) or 1
    freq_score = (df['purchase_frequency'] / max_freq * 50).clip(0, 50)

    # Recency score: inverse - more recent (lower days) = higher score
    max_recency = df['recency_days'].quantile(0.99) or 365
    recency_score = ((max_recency - df['recency_days'].clip(0, max_recency)) / max_recency * 50).clip(0, 50)

    df['engagement_score'] = (freq_score + recency_score).clip(0, 100)

    # Longevity Score (0-100): Based on customer tenure
    # Cap at 24 months for 100% score
    df['longevity_score'] = (tenure_months / 24 * 100).clip(0, 100)

    # Growth Score (0-100): Predicted CLV relative to historical
    # Shows growth potential - higher predicted vs historical = higher growth
    # Use ratio of predicted to historical, capped
    historical_safe = df['historical_clv'].replace(0, 1)
    growth_ratio = df['predicted_12m_clv'] / historical_safe
    # Scale: ratio of 1 = 50%, ratio of 2+ = 100%
    df['growth_score'] = ((growth_ratio - 0.5) * 50).clip(0, 100)

    return df


def _calculate_rfm_segment(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate RFM (Recency, Frequency, Monetary) segment for each customer

    Segments:
    - Champions: Best customers (R>=4, F>=4, M>=4)
    - Loyal Customers: Regular high-value buyers
    - Potential Loyalists: Recent with medium engagement
    - New Customers: Very recent, low frequency
    - Promising: Recent, low frequency
    - Need Attention: Medium across all metrics
    - About to Sleep: Declining engagement
    - At Risk: Were good, haven't bought recently
    - Can't Lose: High value but inactive
    - Hibernating: Low activity all around
    - Lost: Haven't purchased in a long time
    """
    import pandas as pd
    if df.empty:
        return df

    # RFM Segment mapping
    RFM_SEGMENTS = {
        (5, 5, 5): "Champions", (5, 5, 4): "Champions", (5, 4, 5): "Champions",
        (5, 4, 4): "Champions", (4, 5, 5): "Champions",
        (4, 5, 4): "Loyal Customers", (4, 4, 5): "Loyal Customers", (4, 4, 4): "Loyal Customers",
        (5, 3, 3): "Potential Loyalists", (5, 3, 4): "Potential Loyalists",
        (5, 2, 3): "Potential Loyalists", (4, 3, 3): "Potential Loyalists",
        (5, 1, 1): "New Customers", (5, 1, 2): "New Customers",
        (5, 2, 1): "New Customers", (5, 2, 2): "New Customers",
        (4, 1, 1): "Promising", (4, 1, 2): "Promising", (4, 2, 1): "Promising",
        (3, 3, 3): "Need Attention", (3, 3, 4): "Need Attention",
        (3, 4, 3): "Need Attention", (3, 4, 4): "Need Attention",
        (3, 2, 2): "About to Sleep", (3, 2, 3): "About to Sleep", (3, 1, 2): "About to Sleep",
        (2, 5, 5): "At Risk", (2, 5, 4): "At Risk", (2, 4, 5): "At Risk", (2, 4, 4): "At Risk",
        (1, 5, 5): "Can't Lose", (1, 5, 4): "Can't Lose", (1, 4, 5): "Can't Lose",
        (2, 2, 2): "Hibernating", (2, 2, 3): "Hibernating", (2, 3, 2): "Hibernating", (1, 2, 2): "Hibernating",
        (1, 1, 1): "Lost", (1, 1, 2): "Lost", (1, 2, 1): "Lost", (2, 1, 1): "Lost",
    }

    def get_rfm_segment(r: int, f: int, m: int) -> str:
        """Get segment name from RFM scores"""
        segment = RFM_SEGMENTS.get((r, f, m))
        if segment:
            return segment
        # Fallback logic
        if r >= 4 and f >= 4 and m >= 4:
            return "Champions"
        elif r >= 4 and f >= 3:
            return "Loyal Customers"
        elif r >= 4 and f <= 2:
            return "New Customers"
        elif r == 3 and f >= 3:
            return "Need Attention"
        elif r <= 2 and f >= 4:
            return "At Risk"
        elif r <= 2 and f >= 3 and m >= 4:
            return "Can't Lose"
        elif r <= 2 and f <= 2:
            return "Hibernating"
        else:
            return "Need Attention"

    try:
        # Calculate R score (Recency) - lower recency_days is better = higher score
        df['R'] = pd.qcut(
            df['recency_days'].rank(method='first'),
            q=5, labels=[5, 4, 3, 2, 1], duplicates='drop'
        ).astype(int)
    except ValueError:
        # Not enough unique values for 5 bins
        df['R'] = 3

    try:
        # Calculate F score (Frequency) - higher order_count is better
        df['F'] = pd.qcut(
            df['order_count'].rank(method='first'),
            q=5, labels=[1, 2, 3, 4, 5], duplicates='drop'
        ).astype(int)
    except ValueError:
        df['F'] = 3

    try:
        # Calculate M score (Monetary) - higher historical_clv is better
        df['M'] = pd.qcut(
            df['historical_clv'].rank(method='first'),
            q=5, labels=[1, 2, 3, 4, 5], duplicates='drop'
        ).astype(int)
    except ValueError:
        df['M'] = 3

    # Calculate RFM Score string (e.g., "555" for Champions)
    df['rfm_score'] = df['R'].astype(str) + df['F'].astype(str) + df['M'].astype(str)

    # Assign RFM Segment
    df['rfm_segment'] = df.apply(
        lambda x: get_rfm_segment(int(x['R']), int(x['F']), int(x['M'])),
        axis=1
    )

    return df


def calculate_churn_risk(intelligence, customer_df: pd.DataFrame, clv_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate churn risk score based on behavioral indicators

    Indicators:
    - Declining order frequency
    - Increasing order gaps
    - Reduced order values
    - Outstanding receivables
    - Recency vs. typical purchase cycle
    """
    import pandas as pd
    import numpy as np
    churn_data = clv_df.copy()

    # Get recent vs. historical patterns per customer
    customer_trends = []

    for customer_id in clv_df['customer_id'].unique():
        cust_txns = customer_df[customer_df['customer_id'] == customer_id].copy()

        if len(cust_txns) < 2 or cust_txns['invoice_id'].isna().all():
            customer_trends.append({
                'customer_id': customer_id,
                'frequency_trend': 0,
                'value_trend': 0,
                'gap_increasing': 0
            })
            continue

        cust_txns = cust_txns[cust_txns['invoice_id'].notna()].sort_values('posting_date')
        cust_txns['posting_date'] = pd.to_datetime(cust_txns['posting_date'])

        if len(cust_txns) < 2:
            customer_trends.append({
                'customer_id': customer_id,
                'frequency_trend': 0,
                'value_trend': 0,
                'gap_increasing': 0
            })
            continue

        # Split into recent (last 3 months) vs historical
        cutoff = datetime.now() - timedelta(days=90)
        recent = cust_txns[cust_txns['posting_date'] >= cutoff]
        historical = cust_txns[cust_txns['posting_date'] < cutoff]

        # Frequency trend (negative = declining)
        recent_freq = len(recent) / 3 if len(recent) > 0 else 0
        hist_months = max(1, (cutoff - cust_txns['posting_date'].min()).days / 30)
        hist_freq = len(historical) / hist_months if len(historical) > 0 else recent_freq
        freq_trend = (recent_freq - hist_freq) / max(hist_freq, 0.1) if hist_freq > 0 else 0

        # Value trend
        recent_aov = recent['grand_total'].mean() if len(recent) > 0 else 0
        hist_aov = historical['grand_total'].mean() if len(historical) > 0 else recent_aov
        value_trend = (recent_aov - hist_aov) / max(hist_aov, 1) if hist_aov > 0 else 0

        # Gap analysis
        cust_txns['days_between'] = cust_txns['posting_date'].diff().dt.days
        avg_gap = cust_txns['days_between'].mean() or 30
        recent_gaps = cust_txns.tail(3)['days_between'].mean() or avg_gap
        gap_increasing = 1 if recent_gaps > avg_gap * 1.5 else 0

        customer_trends.append({
            'customer_id': customer_id,
            'frequency_trend': float(freq_trend) if not pd.isna(freq_trend) else 0,
            'value_trend': float(value_trend) if not pd.isna(value_trend) else 0,
            'gap_increasing': gap_increasing
        })

    trends_df = pd.DataFrame(customer_trends)
    churn_data = churn_data.merge(trends_df, on='customer_id', how='left')

    # Fill NaN values
    churn_data['frequency_trend'] = churn_data['frequency_trend'].fillna(0)
    churn_data['value_trend'] = churn_data['value_trend'].fillna(0)
    churn_data['gap_increasing'] = churn_data['gap_increasing'].fillna(0)

    # Calculate churn risk score (0-100)
    churn_data['churn_score'] = 50.0

    # Recency factor (more days = higher risk)
    avg_purchase_cycle = 30
    if churn_data['order_count'].sum() > 0:
        avg_purchase_cycle = max(30, churn_data['lifespan_months'].mean() * 30 / max(1, churn_data['order_count'].mean()))

    churn_data['recency_risk'] = np.minimum(
        (churn_data['recency_days'] / max(avg_purchase_cycle, 30)) * 20, 30
    )
    churn_data['churn_score'] += churn_data['recency_risk']

    # Frequency trend (declining = higher risk)
    churn_data['churn_score'] -= churn_data['frequency_trend'].clip(-2, 2) * 10

    # Value trend (declining = higher risk)
    churn_data['churn_score'] -= churn_data['value_trend'].clip(-2, 2) * 10

    # Gap increasing = higher risk
    churn_data['churn_score'] += churn_data['gap_increasing'] * 15

    # Outstanding receivables impact
    receivables_ratio = churn_data['outstanding_amount'] / (churn_data['historical_clv'] + 1)
    churn_data['churn_score'] += np.minimum(receivables_ratio * 10, 15)

    # Clip to 0-100
    churn_data['churn_score'] = churn_data['churn_score'].clip(0, 100)

    # Churn risk category
    churn_data['churn_risk'] = pd.cut(
        churn_data['churn_score'],
        bins=[-np.inf, 30, 50, 70, np.inf],
        labels=['Low', 'Medium', 'High', 'Critical']
    )

    return churn_data


def calculate_health_score(intelligence, churn_df: pd.DataFrame, payment_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate composite customer health score

    Components:
    - Revenue contribution (20%)
    - Purchase engagement (20%)
    - Payment behavior (20%)
    - Relationship longevity (20%)
    - Growth potential (20%)
    """
    import pandas as pd
    import numpy as np
    health_data = churn_df.copy()

    # Payment behavior scores
    if not payment_df.empty:
        payment_metrics = payment_df.groupby('customer_id').agg({
            'days_to_pay': ['mean', 'std'],
            'paid_amount': 'count'
        }).reset_index()
        payment_metrics.columns = ['customer_id', 'avg_days_to_pay', 'payment_std', 'payment_count']
        health_data = health_data.merge(payment_metrics, on='customer_id', how='left')
    else:
        health_data['avg_days_to_pay'] = 30
        health_data['payment_std'] = 0
        health_data['payment_count'] = 0

    health_data['avg_days_to_pay'] = health_data['avg_days_to_pay'].fillna(30)
    health_data['payment_std'] = health_data['payment_std'].fillna(0)
    health_data['payment_count'] = health_data['payment_count'].fillna(0)

    # 1. Revenue contribution (percentile rank)
    health_data['revenue_score'] = (
        health_data['historical_clv'].rank(pct=True) * 100
    )

    # 2. Purchase engagement (frequency + recency)
    freq_rank = health_data['purchase_frequency'].rank(pct=True) * 50
    recency_rank = (1 - health_data['recency_days'].rank(pct=True)) * 50
    health_data['engagement_score'] = freq_rank + recency_rank

    # 3. Payment behavior (faster = better)
    max_days = max(health_data['avg_days_to_pay'].max(), 60)
    health_data['payment_score'] = (
        (1 - health_data['avg_days_to_pay'] / max_days) * 100
    ).clip(0, 100)

    # 4. Relationship longevity
    tenure_days = (pd.Timestamp.now() - health_data['first_purchase']).dt.days
    health_data['longevity_score'] = (
        tenure_days.rank(pct=True) * 100
    )

    # 5. Growth potential (positive trends)
    health_data['growth_score'] = (
        50 +
        health_data['frequency_trend'].clip(-2, 2) * 15 +
        health_data['value_trend'].clip(-2, 2) * 10
    ).clip(0, 100)

    # Composite health score
    health_data['health_score'] = (
        health_data['revenue_score'] * 0.20 +
        health_data['engagement_score'] * 0.20 +
        health_data['payment_score'] * 0.20 +
        health_data['longevity_score'] * 0.20 +
        health_data['growth_score'] * 0.20
    )

    # Health category
    health_data['health_status'] = pd.cut(
        health_data['health_score'],
        bins=[-np.inf, 40, 60, 80, np.inf],
        labels=['Critical', 'At Risk', 'Healthy', 'Excellent']
    )

    return health_data
