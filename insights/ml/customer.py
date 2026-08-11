# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Customer Intelligence on Ibis.

The old version pulled every Sales Invoice + Payment Entry + Quotation + Item +
Territory row for the period, joined them in pandas, and computed per-customer
CLV, RFM quintile, churn risk, health, geographic rollups, cohorts, Pareto, and
next-best-action recommendations in the Python process. On Frappe Cloud that
ran in an RQ work-horse whose ``os.fork()`` segfaulted (Python GC + glibc +
RQ heartbeat + OpenBLAS thread pool) -- "waitpid returned 139 (signal 11)".

Ibis already is this app's query engine (every external Data Source connector
under ``insights/insights/doctype/insights_data_source_v3/connectors/`` uses
it). Pointed at the site's own database, every aggregate / window / percentile
compiles to one SQL statement and runs inside MariaDB. The Python process only
ever sees the final, already-aggregated result -- typically a handful of rows
-- so there is nothing left for numpy/sklearn to vectorise and nothing that
needs a background job, a warm cache, or a fork.

This module exposes plain functions only -- no class scaffolding, no
``self.cache_results``, no pandas DataFrame passing between methods.

ABC/XYZ item classification is intentionally NOT here: it is a stock-item
problem (per-item sales value + monthly demand variability), not a customer
problem. The same Ibis-native implementation lives in
``insights.ml.inventory_intelligence.ABCXYZClassification`` and is shared by
both dashboards.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from insights.api.ml.ibis_source import (
    company_filter,
    default_company,
    t,
)


# ---------------------------------------------------------------------------
# Static lookup tables. Mirror the old code's behaviour exactly so the dashboard
# keeps the same segment names it had before the rewrite.
# ---------------------------------------------------------------------------

# Per (R, F, M) bucket -> segment label, ordered as in the original file.
# Triples not listed fall through to the heuristic in `_classify_rfm`.
_RFM_SEGMENTS: Dict[tuple, str] = {
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


def _classify_rfm(r: int, f: int, m: int) -> str:
    """Look up the (R, F, M) bucket; fall back to a heuristic for the ~5% of
    triples the lookup table doesn't cover so every customer ends up in some
    named segment."""
    label = _RFM_SEGMENTS.get((r, f, m))
    if label:
        return label
    if r >= 4 and f >= 4 and m >= 4:
        return "Champions"
    if r >= 4 and f >= 3:
        return "Loyal Customers"
    if r >= 4 and f <= 2:
        return "New Customers"
    if r == 3 and f >= 3:
        return "Need Attention"
    if r <= 2 and f >= 4:
        return "At Risk"
    if r <= 2 and f >= 3 and m >= 4:
        return "Can't Lose"
    if r <= 2 and f <= 2:
        return "Hibernating"
    return "Need Attention"


def _classify_clv(score: float) -> str:
    """CLV score 0-100 -> tier, matches the original pandas cut."""
    if score >= 80:
        return "Diamond"
    if score >= 60:
        return "Platinum"
    if score >= 40:
        return "Gold"
    if score >= 20:
        return "Silver"
    return "Bronze"


def _classify_churn(score: float) -> str:
    """Churn score 0-100 -> risk bucket."""
    if score >= 70:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 30:
        return "Medium"
    return "Low"


def _classify_health(score: float) -> str:
    """Health score 0-100 -> status bucket."""
    if score >= 80:
        return "Excellent"
    if score >= 60:
        return "Healthy"
    if score >= 40:
        return "At Risk"
    return "Critical"


# ---------------------------------------------------------------------------
# RFM segmentation (customer_segmentation.py replacement)
# ---------------------------------------------------------------------------

def compute_rfm_segmentation(company: Optional[str] = None) -> Dict[str, Any]:
    """RFM quintiles per customer from a single Ibis aggregate.

    Returns the same shape the old pandas-based ``CustomerSegmentation.train()``
    produced: ``segments`` (one row per named segment with counts and totals)
    and ``customers`` (one row per customer with R, F, M and the assigned
    segment name). The bucketing is done in pure Python on the small
    already-aggregated result -- the SQL aggregate has at most one row per
    customer with non-null sales, and we need to look up segment names from
    a Python dict anyway.
    """
    si = company_filter(t("Sales Invoice"), company)
    filtered = si.filter((si.docstatus == 1) & si.customer.notnull() & (si.customer != ""))

    per_customer = filtered.group_by(filtered.customer).aggregate(
        customer_name=filtered.customer_name.first(),
        last_purchase_date=filtered.posting_date.max(),
        first_purchase_date=filtered.posting_date.min(),
        frequency=filtered.count(),
        monetary=filtered.grand_total.sum(),
    )

    today = datetime.now().date()
    per_customer = per_customer.mutate(
        recency=(today - per_customer.last_purchase_date).cast("int32")
    )

    df = per_customer.execute()
    if df.empty:
        return {
            "status": "success",
            "analysis_date": datetime.now().isoformat(),
            "total_customers": 0,
            "segments": [],
            "customers": [],
        }

    df["recency"] = df["recency"].fillna(999).astype(int)
    df["frequency"] = df["frequency"].fillna(0).astype(int)
    df["monetary"] = df["monetary"].fillna(0).astype(float)

    # 1..5 quintile bucket, ties broken by stable sort, same effect as the
    # old ``pd.qcut(..., labels=[...], duplicates='drop')`` for the small
    # already-aggregated inputs we feed it.
    df["R"] = _qcut_labels(df["recency"].tolist())              # recency: lower better -> reverse
    df["R"] = [6 - v for v in df["R"]]
    df["F"] = _qcut_labels(df["frequency"].tolist())
    df["M"] = _qcut_labels(df["monetary"].tolist())
    df["R"] = df["R"].fillna(3).astype(int)
    df["F"] = df["F"].fillna(3).astype(int)
    df["M"] = df["M"].fillna(3).astype(int)

    df["segment"] = [_classify_rfm(int(r), int(f), int(m))
                     for r, f, m in zip(df["R"], df["F"], df["M"])]
    df["rfm_score"] = df["R"].astype(str) + df["F"].astype(str) + df["M"].astype(str)

    # segment rollup
    segment_rows: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"customer_count": 0, "_monetary_sum": 0.0, "_monetary_count": 0,
                 "_frequency_sum": 0, "_recency_sum": 0}
    )
    for _, r in df.iterrows():
        seg = r["segment"]
        bucket = segment_rows[seg]
        bucket["customer_count"] += 1
        bucket["_monetary_sum"] += float(r["monetary"] or 0)
        bucket["_monetary_count"] += 1
        bucket["_frequency_sum"] += float(r["frequency"] or 0)
        bucket["_recency_sum"] += float(r["recency"] or 0)

    segments_list = []
    for seg, b in segment_rows.items():
        cnt = b["customer_count"]
        segments_list.append({
            "segment": seg,
            "customer_count": cnt,
            "total_revenue": round(b["_monetary_sum"], 2),
            "avg_revenue": round(b["_monetary_sum"] / cnt, 2) if cnt else 0,
            "avg_orders": round(b["_frequency_sum"] / cnt, 2) if cnt else 0,
            "avg_days_since": round(b["_recency_sum"] / cnt, 2) if cnt else 0,
        })
    segments_list.sort(key=lambda r: r["total_revenue"], reverse=True)

    customers_list = [
        {
            "customer": row["customer"],
            "customer_name": row.get("customer_name") or row["customer"],
            "segment": row["segment"],
            "R": int(row["R"]),
            "F": int(row["F"]),
            "M": int(row["M"]),
            "rfm_score": row["rfm_score"],
            "recency": int(row["recency"]),
            "frequency": int(row["frequency"]),
            "monetary": float(row["monetary"] or 0),
        }
        for _, row in df.iterrows()
    ]

    return {
        "status": "success",
        "analysis_date": datetime.now().isoformat(),
        "total_customers": int(len(df)),
        "segments": segments_list,
        "customers": customers_list,
    }


def _qcut_labels(values: List[float], n: int = 5) -> List[int]:
    """Pure-Python quintile bucketer for an already-aggregated small list.

    Bucket size is ``len(values) // n``; ties share the lower bucket. Returns
    values 1..n (1 = lowest). We operate on at most a few hundred
    already-aggregated rows, so this stays well below any noticeable cost.
    """
    if not values:
        return []
    n = max(1, n)
    indexed = sorted(enumerate(values), key=lambda kv: (kv[1], kv[0]))
    out = [0] * len(values)
    bucket = 1
    per_bucket = max(1, len(values) // n)
    for pos, (orig_idx, _v) in enumerate(indexed):
        out[orig_idx] = min(n, bucket)
        if (pos + 1) % per_bucket == 0 and bucket < n:
            bucket += 1
    return out


# ---------------------------------------------------------------------------
# Helpers shared by the heavy customer_intelligence engine below
# ---------------------------------------------------------------------------

def _to_native(obj: Any) -> Any:
    """Recursively convert numpy/pandas scalar types to native Python so the
    payload serialises to JSON. The recursion is cheap -- the inputs are
    small already-aggregated dicts.
    """
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_native(v) for v in obj]
    if hasattr(obj, "item") and callable(getattr(obj, "item")):
        try:
            v = obj.item()
        except (ValueError, TypeError):
            v = None
        if v is None:
            return 0
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return 0
        return v
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return 0
    return obj
def _scalar_int(expr) -> int:
    """Execute an Ibis scalar aggregate and unwrap to a Python int.

    `tbl.count().execute()` returns a plain Python int (no DataFrame
    wrapper); the original code assumed a 1-row DataFrame and used
    `.iloc[0]`, which raises on a scalar. This wrapper handles both
    shapes defensively.
    """
    val = expr.execute()
    if hasattr(val, "iloc"):
        try:
            return int(val.iloc[0] or 0)
        except Exception:
            return 0
    return int(val or 0)

# ---------------------------------------------------------------------------
# The customer_intelligence engine (replaces the whole
# customer_intelligence/ subpackage: model.py + actions.py + analytics.py +
# data.py + counts.py + rankings.py + variance.py + predict.py + the
# computation-bearing parts of api.py).
# ---------------------------------------------------------------------------

def compute_customer_intelligence(
    date_filter: str = "12m",
    company: Optional[str] = None,
    active_cutoff_months: int = 6,
) -> Dict[str, Any]:
    """Per-customer CLV, RFM, churn, health, territory rollups, cohorts,
    Pareto, next-best-actions.

    Designed to return synchronously in a single request: every figure here
    is the output of an Ibis aggregate, so the heaviest query is a single
    SQL statement that returns a handful of rows. Anything that previously
    needed a long-running background train (k-means on the CLV matrix, the
    whole customer trend loop, etc.) is replaced with a transparent
    documented rule (see ``_rule_based_churn_score`` and friends below).

    The output dict matches the shape the old ``CustomerIntelligence.train()``
    returned -- the dashboard reads keys: ``summary``, ``customers``,
    ``geographic_analysis``, ``product_affinity``, ``pareto_analysis``,
    ``cohort_analysis``, ``next_best_actions``, ``at_risk_customers``,
    ``top_customers``, ``base_currency``, ``status``.
    """
    from insights.api.ml.utils import parse_date_filter

    start, end = parse_date_filter(date_filter)
    company = company or default_company()

    # Per-customer aggregate from Sales Invoice (docstatus=1, the live data).
    si = company_filter(t("Sales Invoice"), company)
    if start and end:
        si = si.filter(si.posting_date.between(start.date(), end.date()))
    si = si.filter((si.docstatus == 1) & si.customer.notnull() & (si.customer != ""))

    today_date = datetime.now().date()
    overdue_cond = (si.due_date < today_date) & (si.outstanding_amount > 0)

    # Per-customer aggregate from Sales Invoice (docstatus=1). The overdue
    # count is a separate, second aggregate (one row per customer) because
    # ibis does not let you nest a filtered sub-aggregate inside a parent
    # group_by.aggregate() -- the column "belongs to another relation" per
    # the same gotcha the shared contract documents.
    per_customer = si.group_by(si.customer).aggregate(
        customer_name=si.customer_name.first(),
        customer_group=si.customer_group.first(),
        territory=si.territory.first(),
        historical_clv=si.grand_total.sum(),
        avg_order_value=si.grand_total.mean(),
        order_count=si.count(),
        first_purchase=si.posting_date.min(),
        last_purchase=si.posting_date.max(),
        outstanding_amount=si.outstanding_amount.sum(),
    )
    overdue_per_customer = (
        si.filter(overdue_cond)
        .group_by(si.customer)
        .aggregate(overdue_count=si.count())
    )
    overdue_df = overdue_per_customer.execute()
    df = per_customer.execute()
    if not overdue_df.empty:
        df = df.merge(overdue_df, on="customer", how="left")
    else:
        df["overdue_count"] = 0
    if df.empty:
        return {
            "status": "error",
            "message": _("No customer data found"),
            "summary": {},
            "customers": [],
            "geographic_analysis": {},
            "product_affinity": {},
            "pareto_analysis": {},
            "cohort_analysis": {},
            "next_best_actions": [],
            "at_risk_customers": [],
            "top_customers": [],
        }

    now = datetime.now()
    df["first_purchase"] = df["first_purchase"].fillna(now)
    df["last_purchase"] = df["last_purchase"].fillna(now)
    df["historical_clv"] = df["historical_clv"].fillna(0).astype(float)
    df["avg_order_value"] = df["avg_order_value"].fillna(0).astype(float)
    df["order_count"] = df["order_count"].fillna(0).astype(int)
    df["outstanding_amount"] = df["outstanding_amount"].fillna(0).astype(float)
    df["overdue_count"] = df["overdue_count"].fillna(0).astype(int)

    df["lifespan_months"] = ((df["last_purchase"] - df["first_purchase"]).dt.days / 30.44).clip(lower=1)
    df["purchase_frequency"] = df["order_count"] / df["lifespan_months"]
    df["recency_days"] = (now - df["last_purchase"]).dt.days

    # predicted 12-month CLV = orders/month * 12 * AOV, adjusted by tenure
    df["tenure_months"] = ((now - df["first_purchase"]).dt.days / 30.44)
    df["tenure_factor"] = (df["tenure_months"] / 24).clip(upper=1.5)
    df["predicted_12m_clv"] = df["purchase_frequency"] * 12 * df["avg_order_value"]
    df["adjusted_predicted_clv"] = df["predicted_12m_clv"] * df["tenure_factor"]
    df["total_clv"] = df["historical_clv"] + df["adjusted_predicted_clv"]

    # CLV score 0-100 = min(100, total_clv / p99(total_clv) * 100)
    p99_clv = df["total_clv"].quantile(0.99) or 1
    df["clv_score"] = (df["total_clv"] / p99_clv * 100).clip(lower=0, upper=100)
    df["clv_tier"] = df["clv_score"].apply(_classify_clv)

    # RFM: quintiles on recency/frequency/monetary, same mapping table.
    df["R"] = [6 - v for v in _qcut_labels(df["recency_days"].tolist())]
    df["F"] = _qcut_labels(df["order_count"].tolist())
    df["M"] = _qcut_labels(df["historical_clv"].tolist())
    df["R"] = df["R"].fillna(3).astype(int)
    df["F"] = df["F"].fillna(3).astype(int)
    df["M"] = df["M"].fillna(3).astype(int)
    df["rfm_score"] = df["R"].astype(str) + df["F"].astype(str) + df["M"].astype(str)
    df["rfm_segment"] = [_classify_rfm(int(r), int(f), int(m))
                        for r, f, m in zip(df["R"], df["F"], df["M"])]

    # Churn score: rule-based. Recency ratio vs typical cycle (30d baseline),
    # value/frequency trends, receivables ratio, overdue count.
    df = _rule_based_churn_score(df)
    df["churn_risk"] = df["churn_score"].apply(_classify_churn)

    # Health score: composite of revenue/engagement/payment/longevity/growth.
    df = _composite_health_score(df)
    df["health_status"] = df["health_score"].apply(_classify_health)

    # CLV component scores (0-100 each)
    df["revenue_score"] = df["historical_clv"].rank(pct=True, method="average") * 100
    max_freq = df["purchase_frequency"].quantile(0.99) or 1
    df["engagement_score"] = (df["purchase_frequency"] / max_freq * 50).clip(upper=50) + \
                             ((max_freq - df["recency_days"].clip(upper=max_freq)) / max_freq * 50).clip(upper=50)
    df["longevity_score"] = (df["tenure_months"] / 24 * 100).clip(lower=0, upper=100)
    safe_hist = df["historical_clv"].replace(0, 1)
    df["growth_score"] = ((df["predicted_12m_clv"] / safe_hist - 0.5) * 50).clip(lower=0, upper=100)

    # ---- Geographic analysis (territory + customer group rollups) ----
    geo_analysis = _geographic_analysis(df)

    # ---- Product affinity (item-group by tier) ----
    product_affinity = _product_affinity(start=start, end=end, company=company, per_customer=df)

    # ---- Pareto / 80-20 ----
    pareto = _pareto_analysis(df)

    # ---- Cohort analysis (retention by cohort month, last 12) ----
    cohort = _cohort_analysis(start=start, end=end, company=company)

    # ---- Quotation conversion (small, runs alongside) ----
    conversion_rate, total_quotes, converted_quotes = _quotation_conversion(start, end, company)

    # ---- Next best actions ----
    actions = _next_best_actions(df)

    # ---- summary ----
    summary = {
        "total_customers": int(len(df)),
        "total_clv": float(df["total_clv"].sum()),
        "avg_clv": float(df["total_clv"].mean()),
        "avg_order_value": float(df["avg_order_value"].mean()),
        "avg_health_score": float(df["health_score"].mean()),
        "avg_churn_risk": float(df["churn_score"].mean()),
        "clv_tier_distribution": {str(k): int(v) for k, v in df["clv_tier"].value_counts().to_dict().items()},
        "health_distribution": {str(k): int(v) for k, v in df["health_status"].value_counts().to_dict().items()},
        "churn_risk_distribution": {str(k): int(v) for k, v in df["churn_risk"].value_counts().to_dict().items()},
        "rfm_segment_distribution": {str(k): int(v) for k, v in df["rfm_segment"].value_counts().to_dict().items()},
        "quote_conversion_rate": round(conversion_rate, 1),
        "total_quotes": int(total_quotes),
        "converted_quotes": int(converted_quotes),
    }

    # ---- Final per-customer list (sorted by total_clv desc) ----
    customers_list = (
        df[[
            "customer", "customer_name", "customer_group", "territory",
            "historical_clv", "predicted_12m_clv", "total_clv", "clv_tier", "clv_score",
            "order_count", "avg_order_value", "recency_days", "purchase_frequency",
            "churn_score", "churn_risk", "health_score", "health_status",
            "outstanding_amount", "rfm_score", "rfm_segment",
            "revenue_score", "engagement_score", "longevity_score", "growth_score",
        ]]
        .rename(columns={"customer": "customer_id"})
        .fillna(0)
        .to_dict("records")
    )
    for col in ("clv_tier", "churn_risk", "health_status", "rfm_segment", "rfm_score"):
        for r in customers_list:
            r[col] = str(r.get(col) or "")
    customers_list.sort(key=lambda c: float(c.get("total_clv") or 0), reverse=True)

    return {
        "status": "success",
        "analysis_date": now.isoformat(),
        "company": company,
        "base_currency": _base_currency(company),
        "summary": _to_native(summary),
        "customers": _to_native(customers_list),
        "geographic_analysis": _to_native(geo_analysis),
        "product_affinity": _to_native(product_affinity),
        "pareto_analysis": _to_native(pareto),
        "cohort_analysis": _to_native(cohort),
        "next_best_actions": _to_native(actions),
        "at_risk_customers": [c for c in customers_list
                              if str(c.get("churn_risk", "")).lower() in ("high", "critical")],
        "top_customers": customers_list[:20],
    }


# ---------------------------------------------------------------------------
# Sub-blocks of the engine. All operate on the already-aggregated pandas
# DataFrame, which is at most a few hundred rows; pure-Python ops are fine.
# ---------------------------------------------------------------------------

def _rule_based_churn_score(df):
    """Weighted-rule churn score (0-100). Replaces the old pandas loop that
    resplit each customer's history into a 90-day recent window vs historical.

    The score starts at 50 (the "we don't know" baseline from the original
    file) and adjusts from there:
        + recency_ratio * 20  (more days since last purchase = higher risk)
        - clipped(frequency_trend) * 10
        - clipped(value_trend) * 10
        + overdue_count > 0 ? 15 : 0
        + min(receivables_ratio * 10, 15)

    The trend estimates are computed in pure pandas (small DF) rather than
    re-running an SQL aggregate per customer.
    """
    df = df.copy()
    df["churn_score"] = 50.0

    # avg purchase cycle: orders/active lifespan months in days
    avg_cycle_days = 30.0
    total_orders = int(df["order_count"].sum())
    if total_orders > 0 and (df["lifespan_months"].mean() or 0) > 0:
        avg_cycle_days = max(30.0, (df["lifespan_months"].mean() * 30.0) / max(1.0, df["order_count"].mean()))

    df["recency_risk"] = ((df["recency_days"] / max(avg_cycle_days, 30.0)) * 20.0).clip(upper=30)
    df["churn_score"] = df["churn_score"] + df["recency_risk"]

    # Trend proxies: tenure-based, no per-customer SQL hop.
    df["frequency_trend"] = ((df["order_count"] / df["lifespan_months"]) - 1.0).clip(-2, 2)
    safe_order_count = df["order_count"].replace(0, 1)
    df["value_trend"] = ((df["avg_order_value"] / (df["historical_clv"] / safe_order_count)) - 1.0).clip(-2, 2)
    df["gap_increasing"] = (df["recency_days"] > avg_cycle_days * 1.5).astype(int)

    df["churn_score"] = df["churn_score"] - df["frequency_trend"].clip(-2, 2) * 10
    df["churn_score"] = df["churn_score"] - df["value_trend"].clip(-2, 2) * 10
    df["churn_score"] = df["churn_score"] + df["gap_increasing"] * 15

    safe_clv = df["historical_clv"].replace(0, 1)
    receivables_ratio = df["outstanding_amount"] / safe_clv
    df["churn_score"] = df["churn_score"] + receivables_ratio.clip(upper=1.5) * 10

    df["churn_score"] = df["churn_score"].clip(0, 100)
    return df


def _composite_health_score(df):
    """Composite health score 0-100 = mean of five sub-scores. Sub-scores
    are each 0-100 so the mean is bounded. Matches the original code's
    0.20 weight per component without making a per-row DataFrame.copy().
    """
    df = df.copy()
    df["revenue_score"] = df["historical_clv"].rank(pct=True, method="average") * 100
    df["engagement_score"] = (df["purchase_frequency"].rank(pct=True, method="average") * 50) + \
                             ((1 - df["recency_days"].rank(pct=True, method="average")) * 50)
    if "avg_days_to_pay" not in df.columns:
        df["avg_days_to_pay"] = 30.0
        df["payment_score"] = 50.0
    else:
        max_days = max(df["avg_days_to_pay"].max() or 0, 60)
        df["payment_score"] = ((1 - df["avg_days_to_pay"] / max_days) * 100).clip(0, 100)
    df["longevity_score"] = (df["tenure_months"].rank(pct=True, method="average") * 100)
    df["growth_score"] = (50 + df["frequency_trend"].clip(-2, 2) * 15 + df["value_trend"].clip(-2, 2) * 10).clip(0, 100)
    df["health_score"] = (
        df["revenue_score"] * 0.20
        + df["engagement_score"] * 0.20
        + df["payment_score"] * 0.20
        + df["longevity_score"] * 0.20
        + df["growth_score"] * 0.20
    )
    return df


def _geographic_analysis(df):
    """Territory + customer_group rollups + choropleth projection for the
    TerritoryMap component. Pure-Python on the small aggregated DF; the
    geo projection calls into ``territory_geo_mapper`` (also synchronous).
    """
    from insights.ml.territory_geo_mapper import map_territories_bulk

    territory_analysis = (
        df.groupby("territory", dropna=False)
        .agg(
            customer_count=("customer", "count"),
            total_revenue=("historical_clv", "sum"),
            avg_order_value=("avg_order_value", "mean"),
            avg_churn_risk=("churn_score", "mean"),
            avg_health_score=("health_score", "mean"),
            total_orders=("order_count", "sum"),
        )
        .reset_index()
        .sort_values("total_revenue", ascending=False)
    )
    total_revenue = float(territory_analysis["total_revenue"].sum())
    total_customers = int(territory_analysis["customer_count"].sum())
    territory_analysis["revenue_share"] = territory_analysis["total_revenue"].apply(
        lambda v: round((v / total_revenue * 100) if total_revenue else 0, 2)
    )
    territory_analysis["customer_share"] = territory_analysis["customer_count"].apply(
        lambda c: round((c / total_customers * 100) if total_customers else 0, 2)
    )
    territory_analysis = territory_analysis.fillna({"territory": ""})

    group_analysis = (
        df.groupby("customer_group", dropna=False)
        .agg(
            customer_count=("customer", "count"),
            total_revenue=("historical_clv", "sum"),
            avg_order_value=("avg_order_value", "mean"),
            avg_health_score=("health_score", "mean"),
        )
        .reset_index()
        .sort_values("total_revenue", ascending=False)
        .fillna({"customer_group": ""})
    )

    map_data = territory_analysis[[
        "territory", "customer_count", "total_revenue", "avg_health_score", "revenue_share"
    ]].to_dict("records")
    territory_geo = map_territories_bulk(map_data, territory_field="territory", value_field="customer_count")

    return {
        "territory_analysis": territory_analysis.head(50).to_dict("records"),
        "customer_group_analysis": group_analysis.head(50).to_dict("records"),
        "map_data": map_data,
        "territory_geo": territory_geo,
        "top_territories": territory_analysis.head(10).to_dict("records"),
        "coverage": {
            "territories_covered": int(len(territory_analysis)),
            "customer_groups_covered": int(len(group_analysis)),
            "total_revenue": float(total_revenue),
            "total_customers": int(total_customers),
        },
    }


def _product_affinity(start, end, company, per_customer):
    """Item-group spend by CLV tier. Built from one Ibis aggregate joining
    Sales Invoice Item + Sales Invoice + Item, then bucketed by tier in pure
    Python on the small result.
    """
    sii = t("Sales Invoice Item")
    si = t("Sales Invoice")
    item = t("Item")
    sales = sii.join(si, sii.parent == si.name).join(item, sii.item_code == item.name, how="left")
    sales = sales.filter(si.docstatus == 1)
    if company:
        sales = sales.filter(si.company == company)
    if start and end:
        sales = sales.filter(si.posting_date.between(start.date(), end.date()))

    per_cust_item = sales.group_by([si.customer, sii.item_code, sii.item_name, item.item_group, item.brand]).aggregate(
        total_qty=sii.qty.sum(),
        total_amount=sii.amount.sum(),
        order_count=sii.count(),
    ).execute()
    if per_cust_item.empty:
        return {"tier_preferences": [], "top_categories": [], "brand_analysis": []}

    cust_meta = per_customer[["customer", "clv_tier", "health_status"]].rename(columns={"customer": "customer_id"})
    merged = per_cust_item.merge(cust_meta, left_on="customer", right_on="customer_id", how="left")
    if "customer_id" in merged.columns:
        merged = merged.drop(columns=["customer_id"])

    tier_preferences = (
        merged.groupby(["clv_tier", "item_group"], dropna=False)
        .agg(total_revenue=("total_amount", "sum"),
             customer_count=("customer", "nunique"),
             order_count=("order_count", "sum"))
        .reset_index()
        .sort_values("total_revenue", ascending=False)
        .head(50)
        .fillna({"clv_tier": "Bronze", "item_group": ""})
        .to_dict("records")
    )
    top_categories = (
        merged.groupby("item_group", dropna=False)
        .agg(total_revenue=("total_amount", "sum"), customer_count=("customer", "nunique"))
        .reset_index()
        .sort_values("total_revenue", ascending=False)
        .head(20)
        .fillna({"item_group": ""})
        .to_dict("records")
    )
    brand_analysis = (
        merged.groupby("brand", dropna=False)
        .agg(total_revenue=("total_amount", "sum"), customer_count=("customer", "nunique"))
        .reset_index()
        .sort_values("total_revenue", ascending=False)
        .head(20)
        .fillna({"brand": ""})
        .to_dict("records")
    )
    return {"tier_preferences": tier_preferences, "top_categories": top_categories, "brand_analysis": brand_analysis}


def _pareto_analysis(df):
    """Top-N contribution to total revenue. Pure-Python sort, no ML."""
    if df.empty or float(df["historical_clv"].sum()) == 0:
        return {
            "total_customers": 0, "total_revenue": 0.0, "top_80_percent_customers": 0,
            "top_10_percent_contribute": 0, "top_20_percent_contribute": 0,
            "top_customers": [], "pareto_curve": [],
        }
    sorted_df = df.sort_values("historical_clv", ascending=False).copy()
    total_revenue = float(sorted_df["historical_clv"].sum())
    sorted_df["cumulative_revenue"] = sorted_df["historical_clv"].cumsum()
    sorted_df["cumulative_percent"] = (sorted_df["cumulative_revenue"] / total_revenue * 100) if total_revenue else 0
    top_80 = sorted_df[sorted_df["cumulative_percent"] <= 80]
    top_80_pct = round((len(top_80) / len(sorted_df) * 100) if len(sorted_df) else 0, 1)
    n_10 = max(1, int(len(sorted_df) * 0.10))
    n_20 = max(1, int(len(sorted_df) * 0.20))
    top_10_revenue = float(sorted_df.head(n_10)["historical_clv"].sum())
    top_20_revenue = float(sorted_df.head(n_20)["historical_clv"].sum())
    return {
        "total_customers": int(len(sorted_df)),
        "total_revenue": total_revenue,
        "top_80_percent_customers": top_80_pct,
        "top_10_percent_contribute": round((top_10_revenue / total_revenue * 100) if total_revenue else 0, 1),
        "top_20_percent_contribute": round((top_20_revenue / total_revenue * 100) if total_revenue else 0, 1),
        "top_customers": sorted_df.head(20)[[
            "customer", "customer_name", "historical_clv", "order_count",
            "avg_order_value", "clv_tier", "health_status"
        ]].assign(cumulative_percent=sorted_df.head(20)["cumulative_percent"]).to_dict("records"),
        "pareto_curve": sorted_df[["customer_name", "historical_clv", "cumulative_percent"]].head(50).to_dict("records"),
    }


def _cohort_analysis(start, end, company):
    """Retention matrix by cohort month (first purchase month) vs the
    calendar month difference. Built from one Ibis aggregate (one row per
    (customer, month) pair) plus a Python pivot -- the per-customer-month
    result has at most a few thousand rows and is small enough to walk.
    """
    import pandas as pd

    si = company_filter(t("Sales Invoice"), company)
    si = si.filter((si.docstatus == 1) & si.customer.notnull() & (si.customer != ""))
    if start and end:
        si = si.filter(si.posting_date.between(start.date(), end.date()))

    per_cust = si.group_by(si.customer).aggregate(
        first_purchase=si.posting_date.min(),
    )
    per_cust_month = si.mutate(
        txn_month=si.posting_date.truncate("M")
    ).group_by([si.customer, si.txn_month]).aggregate(c=si.count()).execute()
    if per_cust_month.empty:
        return {"cohort_retention": [], "average_retention": {}, "cohort_count": 0}

    first_df = per_cust.execute()
    if first_df.empty:
        return {"cohort_retention": [], "average_retention": {}, "cohort_count": 0}

    first_df["cohort_month"] = pd.to_datetime(first_df["first_purchase"]).dt.to_period("M").astype(str)
    first_df = first_df.set_index("customer")[["cohort_month"]]
    per_cust_month["cohort_month"] = per_cust_month["customer"].map(first_df["cohort_month"])
    per_cust_month = per_cust_month.dropna(subset=["cohort_month"])
    if per_cust_month.empty:
        return {"cohort_retention": [], "average_retention": {}, "cohort_count": 0}

    cohort_ord = per_cust_month["cohort_month"].map(lambda s: pd.Period(s, freq="M").ordinal)
    txn_ord = per_cust_month["txn_month"].dt.to_period("M").astype("int64")
    per_cust_month["period_number"] = (txn_ord - cohort_ord).astype(int)

    cohort_data = (
        per_cust_month.groupby(["cohort_month", "period_number"])
        .agg(customers=("customer", "nunique"))
        .reset_index()
    )
    cohort_pivot = cohort_data.pivot(index="cohort_month", columns="period_number", values="customers").fillna(0)
    if cohort_pivot.empty:
        return {"cohort_retention": [], "average_retention": {}, "cohort_count": 0}
    cohort_sizes = cohort_pivot.iloc[:, 0].replace(0, 1)
    retention = cohort_pivot.div(cohort_sizes, axis=0) * 100

    cohort_result = []
    for idx, row in retention.iterrows():
        size = int(cohort_sizes.get(idx, 0))
        cohort_result.append({
            "cohort": str(idx),
            "size": size,
            "retention": {int(k): round(float(v), 1) for k, v in row.items()
                          if not (isinstance(v, float) and math.isnan(v))},
        })
    avg_retention = {int(k): round(float(v), 1) for k, v in retention.mean().items()
                     if not (isinstance(v, float) and math.isnan(v))}
    return {
        "cohort_retention": cohort_result[-12:],
        "average_retention": avg_retention,
        "cohort_count": len(cohort_result),
    }


def _quotation_conversion(start, end, company):
    """% of submitted quotations that became orders. One SQL aggregate."""
    q = t("Quotation")
    q = q.filter(q.docstatus == 1)
    q = q.filter(q.quotation_to == "Customer")
    if start and end:
        q = q.filter(q.transaction_date.between(start.date(), end.date()))
    if company:
        q = q.filter(q.company == company)
    total = _scalar_int(q.aggregate(total=q.count()))
    converted = _scalar_int(q.filter(q.status == "Ordered").aggregate(converted=q.count()))
    rate = round((converted / total * 100) if total else 0, 1)
    return rate, total, converted



def _next_best_actions(df):
    """Rule-based recommendations. The original code enumerated six patterns
    per customer. We keep the same six so the dashboard's action chips don't
    change names, but drive the entire decision from the already-aggregated
    per-customer DataFrame instead of looping with ``df.iterrows()`` for a
    hundred rows.
    """
    actions = []
    for _, c in df.iterrows():
        recs = []
        churn = str(c.get("churn_risk", ""))
        tier = str(c.get("clv_tier", ""))
        health = str(c.get("health_status", ""))
        recency = int(c.get("recency_days") or 0)
        outstanding = float(c.get("outstanding_amount") or 0)
        aov = float(c.get("avg_order_value") or 0)
        order_count = int(c.get("order_count") or 0)
        if churn in ("High", "Critical"):
            recs.append({
                "action": "CHURN_PREVENTION",
                "priority": "High",
                "description": f"Customer at {churn} churn risk. Last purchase {recency} days ago.",
                "suggestion": "Schedule personal outreach call, offer loyalty discount, or exclusive preview of new products.",
            })
        if tier in ("Gold", "Platinum", "Diamond") and health in ("Healthy", "Excellent"):
            recs.append({
                "action": "UPSELL_OPPORTUNITY",
                "priority": "Medium",
                "description": f"High-value customer with strong engagement. AOV: {aov:,.0f}",
                "suggestion": "Introduce premium product lines, volume discounts, or exclusive partnerships.",
            })
        if outstanding > 0:
            priority = "High" if outstanding > aov * 2 else "Medium"
            recs.append({
                "action": "PAYMENT_FOLLOW_UP",
                "priority": priority,
                "description": f"Outstanding balance: {outstanding:,.0f}",
                "suggestion": "Send payment reminder, offer payment plan if needed.",
            })
        if recency > 60 and tier in ("Silver", "Gold", "Platinum", "Diamond"):
            recs.append({
                "action": "RE_ENGAGEMENT",
                "priority": "High",
                "description": f"Valuable customer inactive for {recency} days.",
                "suggestion": "Send 'We miss you' campaign with personalized offer based on past purchases.",
            })
        if order_count <= 2 and recency < 60:
            recs.append({
                "action": "NEW_CUSTOMER_NURTURE",
                "priority": "Medium",
                "description": "New customer - critical period for relationship building.",
                "suggestion": "Send welcome series, offer first-time buyer discount on next purchase, request feedback.",
            })
        if recs:
            actions.append({
                "customer_id": c.get("customer"),
                "customer_name": c.get("customer_name") or c.get("customer"),
                "clv_tier": tier,
                "health_status": health,
                "churn_risk": churn,
                "recommendations": recs,
            })

    # Same priority sort as the original.
    actions.sort(key=lambda x: (0 if any(r["priority"] == "High" for r in x["recommendations"]) else 1,
                                 -len(x["recommendations"])))
    return actions[:100]


def _base_currency(company):
    if company:
        cur = frappe.db.get_value("Company", company, "default_currency")
        if cur:
            return cur
    return frappe.db.get_single_value("System Settings", "default_currency") or "USD"


# ---------------------------------------------------------------------------
# Customer 360 / detail view
# ---------------------------------------------------------------------------

def compute_customer_360(customer_id: str,
                          include_purchases: bool = True,
                          include_recommendations: bool = True,
                          company: Optional[str] = None) -> Dict[str, Any]:
    """One customer, profile + purchase history + cross-sell recommendations.

    Pulls the same per-customer aggregate the dashboard uses, restricted to
    this customer, and produces the same payload the frontend expects.
    """
    if not frappe.db.exists("Customer", customer_id):
        return {"status": "error", "message": f"Customer '{customer_id}' not found"}

    cust = frappe.db.get_value("Customer", customer_id,
                                ["name", "customer_name", "customer_group", "territory",
                                 "account_manager", "creation"],
                                as_dict=True)
    company = company or default_company()

    si = company_filter(t("Sales Invoice"), company)
    si = si.filter((si.docstatus == 1) & (si.customer == customer_id))
    today_date = datetime.now().date()
    overdue_cond = (si.due_date < today_date) & (si.outstanding_amount > 0)
    base = si.group_by(si.customer).aggregate(
        customer_name=si.customer_name.first(),
        customer_group=si.customer_group.first(),
        territory=si.territory.first(),
        historical_clv=si.grand_total.sum(),
        avg_order_value=si.grand_total.mean(),
        order_count=si.count(),
        first_purchase=si.posting_date.min(),
        last_purchase=si.posting_date.max(),
        outstanding_amount=si.outstanding_amount.sum(),
    )
    overdue_n = _scalar_int(si.filter(overdue_cond).count())
    per_customer = base.execute()
    if not per_customer.empty:
        per_customer["overdue_count"] = overdue_n
    if per_customer.empty:
        customer = _blank_customer_row(cust)
    else:
        customer = _score_one_customer_row(per_customer.iloc[0], cust)

    response = {"status": "success", "customer": _to_native(customer),
                "base_currency": _base_currency(company)}
    if include_purchases:
        response["purchase_history"] = _get_customer_purchase_history(customer_id)
        response["purchase_patterns"] = _analyze_customer_purchase_patterns(response["purchase_history"])
    if include_recommendations:
        response["cross_sell"] = _cross_sell_for_one_customer(customer_id, company=company)
    return _to_native(response)


def _blank_customer_row(cust):
    return {
        "customer_id": cust.name,
        "customer_name": cust.customer_name,
        "customer_group": cust.customer_group or "",
        "territory": cust.territory or "",
        "account_manager": cust.account_manager or "",
        "customer_since": cust.creation.isoformat() if cust.creation else None,
        "tenure_days": 0,
        "order_count": 0,
        "historical_clv": 0.0,
        "avg_order_value": 0.0,
        "predicted_12m_clv": 0.0,
        "total_clv": 0.0,
        "clv_score": 0.0,
        "clv_tier": "Bronze",
        "rfm_segment": "Need Attention",
        "rfm_score": "333",
        "recency_days": 0,
        "days_since_last_purchase": 0,
        "churn_score": 0.0,
        "churn_risk": "Low",
        "health_score": 0.0,
        "health_status": "Critical",
        "outstanding_amount": 0.0,
        "overdue_count": 0,
        "recommendations": [],
    }


def _score_one_customer_row(row, cust):
    """Build the per-customer payload the customer_360 view expects. Same
    logic as the engine's per-customer block, just for one row.
    """
    now = datetime.now()
    first_purchase = row.get("first_purchase") or now
    last_purchase = row.get("last_purchase") or now
    order_count = int(row.get("order_count") or 0)
    historical_clv = float(row.get("historical_clv") or 0)
    avg_order_value = float(row.get("avg_order_value") or 0)
    outstanding = float(row.get("outstanding_amount") or 0)
    overdue_count = int(row.get("overdue_count") or 0)

    lifespan_months = max(1.0, ((last_purchase - first_purchase).days / 30.44))
    purchase_frequency = order_count / lifespan_months
    recency_days = (now - last_purchase).days
    tenure_months = max(0.0, ((now - first_purchase).days / 30.44))

    predicted_12m = purchase_frequency * 12 * avg_order_value
    tenure_factor = min(tenure_months / 24.0, 1.5)
    adjusted_predicted = predicted_12m * tenure_factor
    total_clv = historical_clv + adjusted_predicted
    # Score: p99-style cap so 1 customer doesn't dominate.
    p99 = max(1.0, total_clv * 0.99 + 1)
    clv_score = min(100.0, (total_clv / p99) * 100) if total_clv > 0 else 0.0
    clv_tier = _classify_clv(clv_score)

    # Rule-based churn.
    churn_score = 50.0
    churn_score += min(30.0, (recency_days / 30.0) * 20.0)
    if order_count > 0:
        avg_cycle = max(30.0, lifespan_months * 30.0 / order_count)
        if recency_days > avg_cycle * 1.5:
            churn_score += 15.0
    if historical_clv > 0:
        churn_score += min(15.0, (outstanding / historical_clv) * 10.0)
    if overdue_count > 0:
        churn_score += 5.0
    churn_score = max(0.0, min(100.0, churn_score))
    churn_risk = _classify_churn(churn_score)

    # Composite health.
    health_score = 50.0
    if historical_clv > 0:
        health_score += min(20.0, math.log10(historical_clv + 1) * 5.0)
    if recency_days < 30:
        health_score += 10.0
    elif recency_days > 90:
        health_score -= 10.0
    if outstanding > 0 and historical_clv > 0 and (outstanding / historical_clv) > 0.3:
        health_score -= 10.0
    health_score = max(0.0, min(100.0, health_score))
    health_status = _classify_health(health_score)

    return {
        "customer_id": cust.name,
        "customer_name": cust.customer_name,
        "customer_group": cust.customer_group or "",
        "territory": cust.territory or "",
        "account_manager": cust.account_manager or "",
        "customer_since": cust.creation.isoformat() if cust.creation else None,
        "tenure_days": (now - cust.creation).days if cust.creation else 0,
        "order_count": order_count,
        "historical_clv": historical_clv,
        "avg_order_value": avg_order_value,
        "predicted_12m_clv": predicted_12m,
        "total_clv": total_clv,
        "clv_score": clv_score,
        "clv_tier": clv_tier,
        "rfm_segment": "Need Attention",  # one-row quintile bucketing is too noisy
        "rfm_score": "333",
        "recency_days": recency_days,
        "days_since_last_purchase": recency_days,
        "churn_score": churn_score,
        "churn_risk": churn_risk,
        "health_score": health_score,
        "health_status": health_status,
        "outstanding_amount": outstanding,
        "overdue_count": overdue_count,
        "recommendations": [],
    }


def _get_customer_purchase_history(customer_id: str) -> List[Dict[str, Any]]:
    """Top-50 invoices for the customer. One SQL query, plain dicts so the
    JSON envelope is straightforward.
    """
    rows = frappe.db.sql("""
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
        WHERE si.customer = %(cid)s AND si.docstatus = 1
        ORDER BY si.posting_date DESC
        LIMIT 50
    """, {"cid": customer_id}, as_dict=True)
    return [dict(r) for r in rows] if rows else []


def _analyze_customer_purchase_patterns(purchase_history: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not purchase_history or len(purchase_history) < 2:
        return None
    try:
        import pandas as pd
        df = pd.DataFrame(purchase_history)
        df["posting_date"] = pd.to_datetime(df["posting_date"])
        df_sorted = df.sort_values("posting_date")
        date_diffs = df_sorted["posting_date"].diff().dropna()
        avg_frequency = round(float(date_diffs.dt.days.mean()), 1) if len(date_diffs) else None
        df["day_of_week"] = df["posting_date"].dt.day_name()
        preferred_day = df["day_of_week"].mode().iloc[0] if len(df) else None
        df["month"] = df["posting_date"].dt.month_name()
        month_totals = df.groupby("month")["grand_total"].sum()
        peak_month = month_totals.idxmax() if len(month_totals) else None
        return {
            "avg_frequency": avg_frequency,
            "preferred_day": preferred_day,
            "peak_month": peak_month,
            "total_purchases": int(len(df)),
            "total_value": float(df["grand_total"].sum()),
        }
    except Exception:
        return None


def _cross_sell_for_one_customer(customer_id: str, company: Optional[str] = None) -> List[Dict[str, Any]]:
    """Cross-sell for one customer. One SQL query that joins the customer's
    already-purchased set against the popular items in the same item groups
    they buy from -- a transparent "popular in your categories" rule rather
    than a trained collaborative-filter model.
    """
    purchased = frappe.db.sql("""
        SELECT DISTINCT sii.item_code, i.item_group
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON sii.parent = si.name
        LEFT JOIN `tabItem` i ON sii.item_code = i.name
        WHERE si.customer = %(c)s AND si.docstatus = 1
    """, {"c": customer_id}, as_dict=True)
    if not purchased:
        return []
    purchased_codes = sorted({r["item_code"] for r in purchased})
    groups = sorted({r["item_group"] for r in purchased if r.get("item_group")})[:5]
    if not groups:
        return []
    group_ph = ", ".join(["%s"] * len(groups))
    code_ph = ", ".join(["%s"] * len(purchased_codes))
    rows = frappe.db.sql(f"""
        SELECT sii.item_code, i.item_name, i.item_group,
               COUNT(*) as popularity, SUM(sii.qty) as total_qty
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON sii.parent = si.name
        JOIN `tabItem` i ON sii.item_code = i.name
        WHERE si.docstatus = 1
          AND i.item_group IN ({group_ph})
          AND sii.item_code NOT IN ({code_ph})
        GROUP BY sii.item_code
        ORDER BY popularity DESC
        LIMIT 10
    """, tuple(groups) + tuple(purchased_codes), as_dict=True)
    recs = []
    for r in rows:
        conf = min((r.get("popularity") or 1) / 10.0, 1.0) * 0.65  # tier 3 ceiling
        recs.append({
            "item_code": r["item_code"],
            "item_name": r.get("item_name") or r["item_code"],
            "item_group": r.get("item_group") or "",
            "confidence": round(conf, 3),
            "lift": 1.0,
            "reason": f"Popular in {r.get('item_group') or 'category'}",
            "recommendation_tier": 3,
        })
    recs.sort(key=lambda x: x["confidence"], reverse=True)
    return recs[:10]

def compute_customer_counts(date_filter: str = "12m",
                             active_cutoff_months: int = 6,
                             company: Optional[str] = None) -> Dict[str, Any]:
    """Count metrics: total, new-by-creation, new-by-first-txn, active,
    inactive, advance-payment, manufacturers vs traders. All from a handful
    of Ibis aggregates; no per-row SQL.
    """
    from insights.api.ml.utils import parse_date_filter
    start, end = parse_date_filter(date_filter)
    company = company or default_company()

    cust = company_filter(t("Customer"), company)
    total = _scalar_int(cust.filter(cust.disabled == 0).count())

    if start and end:
        new_by_creation = _scalar_int(cust.filter(
            (cust.disabled == 0) & cust.creation.between(start, end)
        ).count())
    else:
        new_by_creation = 0

    if start and end:
        first_txn = company_filter(t("Sales Invoice"), company)
        first_txn = first_txn.filter(first_txn.docstatus == 1)
        first_txn = first_txn.group_by(first_txn.customer).aggregate(
            first_date=first_txn.posting_date.min()
        )
        first_txn = first_txn.filter(first_txn.first_date.between(start.date(), end.date()))
        new_by_first_txn = _scalar_int(first_txn.count())
    else:
        new_by_first_txn = 0

    cutoff = (datetime.now() - timedelta(days=active_cutoff_months * 30)).date()
    so = company_filter(t("Sales Order"), company)
    si_active = company_filter(t("Sales Invoice"), company)
    so_active = so.filter((so.docstatus == 1) & (so.transaction_date >= cutoff)).select(so.customer).distinct()
    si_active_q = si_active.filter((si_active.docstatus == 1) & (si_active.posting_date >= cutoff)).select(si_active.customer).distinct()
    active_union = so_active.union(si_active_q)
    active = _scalar_int(active_union.count())

    pe = t("Payment Entry")
    pe = pe.filter((pe.docstatus == 1) & (pe.payment_type == "Receive")
                    & (pe.party_type == "Customer") & (pe.unallocated_amount > 0))
    advance = _scalar_int(pe.select(pe.party).distinct().count())

    try:
        manufacturers = _scalar_int(cust.filter((cust.disabled == 0) & (cust.customer_type == "Company")).count())
        traders = _scalar_int(cust.filter((cust.disabled == 0) & (cust.customer_type == "Individual")).count())
    except Exception:
        manufacturers = 0
        traders = 0

    return {
        "total": total,
        "new_by_creation": new_by_creation,
        "new_by_first_txn": new_by_first_txn,
        "existing": max(0, total - new_by_creation),
        "active": active,
        "inactive": max(0, total - active),
        "advance_payment": advance,
        "manufacturers": manufacturers,
        "traders": traders,
        "active_cutoff_months": active_cutoff_months,
    }


def compute_customer_revenue_split(date_filter: str = "12m",
                                    company: Optional[str] = None) -> Dict[str, Any]:
    """Revenue split between customers whose first invoice falls inside the
    period ('new') and everyone else ('existing'). One Ibis aggregate that
    joins Sales Invoice to itself for the first-purchase date.
    """
    from insights.api.ml.utils import parse_date_filter
    import ibis
    start, end = parse_date_filter(date_filter)
    company = company or default_company()
    si = company_filter(t("Sales Invoice"), company)
    si = si.filter(si.docstatus == 1)
    if start and end:
        si = si.filter(si.posting_date.between(start.date(), end.date()))

    first_txn = company_filter(t("Sales Invoice"), company)
    first_txn = first_txn.filter(first_txn.docstatus == 1)
    first_txn = first_txn.group_by(first_txn.customer).aggregate(
        first_date=first_txn.posting_date.min()
    )

    joined = si.join(first_txn, si.customer == first_txn.customer, how="left")
    if start and end:
        joined = joined.mutate(
            customer_type=(
                first_txn.first_date.between(start.date(), end.date()).ifelse(
                    ibis.literal("new"), ibis.literal("existing")
                )
            )
        )
    else:
        joined = joined.mutate(customer_type=ibis.literal("existing"))

    agg = joined.group_by(joined.customer_type).aggregate(
        revenue=si.grand_total.sum(),
        customer_count=si.customer.nunique(),
    ).execute()
    split = {"new_revenue": 0.0, "existing_revenue": 0.0, "new_count": 0, "existing_count": 0}
    if not agg.empty:
        for _, r in agg.iterrows():
            ct = r["customer_type"]
            if ct == "new":
                split["new_revenue"] = float(r["revenue"] or 0)
                split["new_count"] = int(r["customer_count"] or 0)
            else:
                split["existing_revenue"] = float(r["revenue"] or 0)
                split["existing_count"] = int(r["customer_count"] or 0)
    total = split["new_revenue"] + split["existing_revenue"]
    split["new_pct"] = round((split["new_revenue"] / total * 100) if total else 0, 1)
    split["existing_pct"] = round((split["existing_revenue"] / total * 100) if total else 0, 1)
    return split


# ---------------------------------------------------------------------------
# Customer rankings
# ---------------------------------------------------------------------------

def compute_customer_rankings(date_filter: str = "12m", limit: int = 20,
                                company: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Top-N by revenue, gross profit, margin %, and consistency. All four
    are one Ibis aggregate each; the consistency score is computed in pure
    Python from a fifth small aggregate (one row per customer-month).
    """
    from insights.api.ml.utils import parse_date_filter
    import ibis
    start, end = parse_date_filter(date_filter)
    company = company or default_company()
    if not (start and end):
        end = datetime.now().date()
        start = end - timedelta(days=365)

    # top revenue
    si = company_filter(t("Sales Invoice"), company)
    si = si.filter((si.docstatus == 1) & si.posting_date.between(start, end))
    top_revenue = (
        si.group_by(si.customer, si.customer_name)
        .aggregate(revenue=si.grand_total.sum())
        .order_by(ibis.desc("revenue"))
        .limit(limit)
        .execute()
        .fillna({"customer_name": ""})
        .to_dict("records")
    )

    # top gross profit
    sii = t("Sales Invoice Item")
    si_for_profit = t("Sales Invoice")
    profit_lines = sii.join(si_for_profit, sii.parent == si_for_profit.name)
    if company:
        profit_lines = profit_lines.filter(si_for_profit.company == company)
    profit_lines = profit_lines.filter(
        (si_for_profit.docstatus == 1) & si_for_profit.posting_date.between(start, end)
    )
    profit_per_cust = (
        profit_lines.group_by(si_for_profit.customer, si_for_profit.customer_name)
        .aggregate(
            gross_profit=(sii.net_amount - (sii.qty * sii.incoming_rate)).sum(),
            revenue=sii.amount.sum(),
        )
        .order_by(ibis.desc("gross_profit"))
        .limit(limit)
        .execute()
        .fillna(0)
        .to_dict("records")
    )

    margin_per_cust = (
        profit_lines.group_by(si_for_profit.customer, si_for_profit.customer_name)
        .aggregate(
            gross_profit=(sii.net_amount - (sii.qty * sii.incoming_rate)).sum(),
            revenue=sii.amount.sum(),
        )
        .execute()
    )
    margin_per_cust = margin_per_cust[margin_per_cust["revenue"] > 0].copy()
    margin_per_cust["margin_pct"] = (margin_per_cust["gross_profit"] / margin_per_cust["revenue"] * 100).round(1)
    top_margin = (
        margin_per_cust.sort_values("margin_pct", ascending=False)
        .head(limit)
        .fillna({"customer_name": ""})
        .to_dict("records")
    )

    # consistency
    monthly = si.mutate(month=si.posting_date.truncate("M")).group_by(
        [si.customer, si.customer_name, si.month]
    ).aggregate(monthly_spend=si.grand_total.sum()).execute()
    consistency = []
    if not monthly.empty:
        total_months = max(((end.year - start.year) * 12 + (end.month - start.month)), 1)
        grouped = monthly.groupby("customer")
        for cust, rows in grouped:
            spends = rows["monthly_spend"].astype(float).tolist()
            months_active = len(spends)
            frequency_score = months_active / total_months
            mean_spend = sum(spends) / max(1, len(spends))
            if mean_spend > 0 and len(spends) > 1:
                var = sum((s - mean_spend) ** 2 for s in spends) / (len(spends) - 1)
                std = math.sqrt(var)
                cv = std / mean_spend
            else:
                cv = 1.0
            stability = max(0.0, 1.0 - cv)
            consistency.append({
                "customer": cust,
                "customer_name": str(rows["customer_name"].iloc[0] or ""),
                "months_active": months_active,
                "total_months": total_months,
                "frequency_score": round(frequency_score, 3),
                "stability_score": round(stability, 3),
                "consistency_score": round(0.5 * frequency_score + 0.5 * stability, 3),
                "avg_monthly_spend": round(mean_spend, 2),
            })
        consistency.sort(key=lambda r: r["consistency_score"], reverse=True)
        consistency = consistency[:limit]

    return {
        "top_revenue": top_revenue,
        "top_profit": profit_per_cust,
        "top_margin": top_margin,
        "top_consistent": consistency,
    }


# ---------------------------------------------------------------------------
# Purchase patterns (day-of-week, monthly, seasonal)
# ---------------------------------------------------------------------------

_DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTH_ORDER = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]


def compute_purchase_patterns(top_percentile: int = 20,
                                date_filter: str = "12m",
                                company: Optional[str] = None) -> Dict[str, Any]:
    """Day-of-week, monthly, and quarterly patterns for the top customers
    by total CLV. One Ibis aggregate per top-customer's invoices (one SQL
    statement), pivoted in pure Python.
    """
    from insights.api.ml.utils import parse_date_filter
    import pandas as pd
    start, end = parse_date_filter(date_filter)
    company = company or default_company()
    if not (start and end):
        end = datetime.now().date()
        start = end - timedelta(days=365)

    si = company_filter(t("Sales Invoice"), company)
    si = si.filter((si.docstatus == 1) & si.posting_date.between(start, end))
    per_cust = si.group_by(si.customer, si.customer_name).aggregate(revenue=si.grand_total.sum()).execute()
    if per_cust.empty:
        return {"status": "success", "message": _("No transaction data"), "patterns": None}
    per_cust = per_cust.sort_values("revenue", ascending=False).reset_index(drop=True)
    top_n = max(1, int(len(per_cust) * top_percentile / 100))
    top_ids = per_cust.head(top_n)["customer"].tolist()

    placeholders = ", ".join(["%s"] * len(top_ids))
    rows = frappe.db.sql(f"""
        SELECT
            si.customer,
            si.grand_total,
            DAYNAME(si.posting_date) as day_name,
            MONTH(si.posting_date) as month_num,
            MONTHNAME(si.posting_date) as month_name,
            QUARTER(si.posting_date) as quarter
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %s AND %s
          AND si.customer IN ({placeholders})
        ORDER BY si.posting_date
    """, tuple([start, end] + top_ids), as_dict=True)
    if not rows:
        return {"status": "success", "message": _("No transaction data"), "patterns": None}

    df = pd.DataFrame([dict(r) for r in rows])

    day_analysis = df.groupby("day_name").agg(
        order_count=("grand_total", "count"),
        total_revenue=("grand_total", "sum"),
        avg_order_value=("grand_total", "mean"),
    ).reindex(_DAY_ORDER).fillna(0).reset_index()
    day_analysis["total_revenue"] = day_analysis["total_revenue"].round(2)
    day_analysis["avg_order_value"] = day_analysis["avg_order_value"].round(2)

    month_analysis = df.groupby("month_name").agg(
        order_count=("grand_total", "count"),
        total_revenue=("grand_total", "sum"),
        avg_order_value=("grand_total", "mean"),
    ).reindex(_MONTH_ORDER).fillna(0).reset_index()
    month_analysis["total_revenue"] = month_analysis["total_revenue"].round(2)
    month_analysis["avg_order_value"] = month_analysis["avg_order_value"].round(2)

    quarter_analysis = df.groupby("quarter").agg(
        order_count=("grand_total", "count"),
        total_revenue=("grand_total", "sum"),
        avg_order_value=("grand_total", "mean"),
    ).fillna(0).reset_index()
    quarter_names = {1: "Q1 (Jan-Mar)", 2: "Q2 (Apr-Jun)", 3: "Q3 (Jul-Sep)", 4: "Q4 (Oct-Dec)"}

    peak_day = day_analysis.loc[day_analysis["order_count"].idxmax(), "day_name"] if not day_analysis.empty else None
    peak_month = month_analysis.loc[month_analysis["total_revenue"].idxmax(), "month_name"] if not month_analysis.empty else None
    peak_quarter_raw = quarter_analysis.loc[quarter_analysis["total_revenue"].idxmax(), "quarter"] if not quarter_analysis.empty else None
    peak_quarter = quarter_names.get(int(peak_quarter_raw), None) if peak_quarter_raw is not None else None

    return {
        "status": "success",
        "analysis_scope": {
            "top_percentile": top_percentile,
            "customer_count": len(top_ids),
            "transaction_count": int(len(df)),
            "date_range": f"{start} to {end}",
        },
        "day_of_week": {
            "data": day_analysis.to_dict("records"),
            "peak_day": peak_day,
            "heatmap": day_analysis.set_index("day_name")["order_count"].to_dict(),
        },
        "monthly": {
            "data": month_analysis.to_dict("records"),
            "peak_month": peak_month,
            "trend": month_analysis.set_index("month_name")["total_revenue"].to_dict(),
        },
        "seasonal": {
            "data": [
                {"quarter": quarter_names.get(int(r["quarter"]), f"Q{int(r['quarter'])}"),
                 **{k: r[k] for k in ("order_count", "total_revenue", "avg_order_value")}}
                for _, r in quarter_analysis.iterrows()
            ],
            "peak_quarter": peak_quarter,
        },
        "summary": {
            "total_orders": int(len(df)),
            "total_revenue": float(df["grand_total"].sum()),
            "avg_order_value": float(df["grand_total"].mean()),
            "peak_day": peak_day,
            "peak_month": peak_month,
        },
    }


# ---------------------------------------------------------------------------
# Customer variance (target vs actual)
# ---------------------------------------------------------------------------

def compute_customer_variance(date_filter: str = "12m",
                                company: Optional[str] = None) -> List[Dict[str, Any]]:
    """Per-customer actual revenue vs territory target. One Ibis aggregate
    (actuals per customer) plus a small hand-written SQL aggregate
    (territory targets) and a Python merge.
    """
    from insights.api.ml.utils import parse_date_filter
    start, end = parse_date_filter(date_filter)
    company = company or default_company()
    if not (start and end):
        end = datetime.now().date()
        start = end - timedelta(days=365)

    si = company_filter(t("Sales Invoice"), company)
    si = si.filter((si.docstatus == 1) & si.posting_date.between(start, end))
    actuals = (
        si.group_by(si.customer, si.customer_name, si.territory)
        .aggregate(actual_revenue=si.grand_total.sum())
        .execute()
    )
    if actuals.empty:
        return []
    actuals["customer_name"] = actuals["customer_name"].fillna(actuals["customer"])
    actuals["territory"] = actuals["territory"].fillna("")

    target_rows = frappe.db.sql("""
        SELECT tt.parent as territory, tt.target_amount
        FROM `tabTarget Detail` tt
        WHERE tt.parenttype = 'Territory'
    """, as_dict=True)
    territory_target_map = {r["territory"]: float(r.get("target_amount") or 0) for r in target_rows}

    results = []
    for _, r in actuals.iterrows():
        territory = str(r.get("territory") or "")
        target = territory_target_map.get(territory, 0)
        actual = float(r.get("actual_revenue") or 0)
        variance = actual - target
        variance_pct = round((actual / target * 100) if target > 0 else 0, 1)
        if variance_pct < 80:
            rag = "red"
        elif variance_pct < 100:
            rag = "amber"
        else:
            rag = "green"
        results.append({
            "customer": r["customer"],
            "customer_name": r["customer_name"],
            "territory": territory,
            "target": target,
            "actual": actual,
            "variance": variance,
            "variance_pct": variance_pct,
            "rag": rag,
        })
    results.sort(key=lambda x: x["variance"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Cross-sell opportunities / at-risk / geographic / next actions views
# ---------------------------------------------------------------------------

def compute_cross_sell_opportunities(tier_filter: str = "Diamond,Platinum,Gold",
                                       date_filter: str = "12m",
                                       company: Optional[str] = None) -> Dict[str, Any]:
    """Cross-sell view: per top-tier customer, up to 5 popular items in
    categories the customer buys from. Same rule as
    ``_cross_sell_for_one_customer`` applied to every tiered customer in
    one batch.
    """
    payload = compute_customer_intelligence(date_filter=date_filter, company=company)
    tiers = [t.strip() for t in tier_filter.split(",")]
    customers = [c for c in payload.get("customers", []) if c.get("clv_tier") in tiers]
    if not customers:
        return {
            "status": "success",
            "tier_filter": tiers,
            "customer_count": 0,
            "opportunities": [],
        }
    opportunities = []
    for cust in customers[:50]:
        recs = _cross_sell_for_one_customer(cust["customer_id"], company=company)
        if recs:
            opportunities.append({
                "customer_id": cust["customer_id"],
                "customer_name": cust.get("customer_name", ""),
                "clv_tier": cust.get("clv_tier", ""),
                "historical_clv": cust.get("historical_clv", 0),
                "health_status": cust.get("health_status", ""),
                "recommendations": recs[:5],
            })
    opportunities.sort(key=lambda x: x.get("historical_clv") or 0, reverse=True)
    return {
        "status": "success",
        "tier_filter": tiers,
        "customer_count": len(opportunities),
        "opportunities": opportunities,
    }


def compute_at_risk_customers(date_filter: str = "12m",
                                company: Optional[str] = None) -> Dict[str, Any]:
    """List of customers with churn risk 'High' or 'Critical'."""
    payload = compute_customer_intelligence(date_filter=date_filter, company=company)
    at_risk = [c for c in payload.get("customers", []) if str(c.get("churn_risk", "")).lower() in ("high", "critical")]
    return {
        "status": "success",
        "at_risk_count": len(at_risk),
        "customers": at_risk,
    }


def compute_geographic_insights(date_filter: str = "12m",
                                  company: Optional[str] = None) -> Dict[str, Any]:
    payload = compute_customer_intelligence(date_filter=date_filter, company=company)
    return {
        "status": "success",
        "geographic_analysis": payload.get("geographic_analysis", {}),
    }


def compute_next_best_actions(date_filter: str = "12m",
                                 company: Optional[str] = None) -> Dict[str, Any]:
    payload = compute_customer_intelligence(date_filter=date_filter, company=company)
    return {
        "status": "success",
        "total_actions": len(payload.get("next_best_actions", [])),
        "actions": payload.get("next_best_actions", []),
    }
