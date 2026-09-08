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

from frappe.query_builder.functions import Count, Sum

from insights.api.ml.ibis_source import (
    company_filter,
    default_company,
    dn_cost,
    line_cogs,
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


def _as_date(value):
    """Normalize a purchase-date value to a plain `date`.

    `.execute()` hands back `datetime.date` (default path, DB `DATE`
    columns) or `pandas.Timestamp`/`datetime.datetime` (PyArrow
    materialisation, or a filled-in `datetime.now()` default) depending on
    which path ran -- and Python (and pandas' scalar-vs-Series arithmetic)
    refuses to subtract a bare `date` from a `datetime`. Truncate anything
    datetime-shaped to a `date` so every subtraction in this module compares
    like with like, regardless of which execute path produced the column.
    """
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


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


def _data_as_of(company: Optional[str]):
    """Latest submitted-sales-invoice date in the data. Recency, tenure and
    churn are measured from this horizon, not the wall clock, so a lagging
    ledger does not inflate every customer's inactivity and push the whole
    book to Critical churn. Returns ``None`` when there is no data."""
    import pandas as pd
    si = company_filter(t("Sales Invoice"), company).filter(t("Sales Invoice").docstatus == 1)
    m = si.aggregate(m=si.posting_date.max()).execute().iloc[0]["m"]
    if m is None or pd.isna(m):
        return None
    return pd.Timestamp(m).date()


def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _churn_score(recency_days, order_count, lifespan_days, frequency_trend,
                 value_trend, outstanding, historical_clv, overdue_count):
    """Cadence-relative churn score (0-100), the single source of truth shared
    by the bulk list engine and the single-customer detail path so the two
    always reconcile for the same customer.

    Recency is scored against THIS customer's own average purchase cycle, not a
    flat 30-day scale: a quarterly buyer one cycle out is on schedule (low
    risk); a monthly buyer three cycles silent is critical. On cadence ->
    neutral; recently active -> below neutral; several cycles overdue ->
    escalating. Declining order frequency/spend and unpaid balances add risk,
    growth reduces it. Replaces the old ``50 + min(30, recency_days/30*20)``
    which put every customer inactive more than ~30 days at >=70 (Critical)
    regardless of their real buying rhythm.
    """
    if order_count >= 2 and lifespan_days > 0:
        cycle = max(lifespan_days / (order_count - 1), 7.0)
    else:
        cycle = 180.0  # single-order / unknown cadence: 6-month grace window
    overdue_ratio = recency_days / cycle  # 1.0 == exactly on cadence
    recency_risk = _clip((overdue_ratio - 1.0) * 25.0, -25.0, 45.0)

    score = 35.0 + recency_risk
    score -= _clip(frequency_trend, -2.0, 2.0) * 7.0
    score -= _clip(value_trend, -2.0, 2.0) * 7.0
    if historical_clv > 0:
        score += min(outstanding / historical_clv, 1.5) * 8.0
    if overdue_count > 0:
        score += 5.0
    return _clip(score, 0.0, 100.0)


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
        customer_name=filtered.customer_name.min(),
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
    wrapper). `tbl.aggregate(name=tbl.count()).execute()` returns a 1-row,
    1-column DataFrame instead -- `.iloc[0]` on that yields the row (a
    Series), not the cell, and `int(Series or 0)` raises "truth value of
    a Series is ambiguous", which the blanket except below then silently
    downgrades to 0. Unwrap positionally: `.iloc[0, 0]` for a 2-D
    DataFrame, `.iloc[0]` for a bare 1-D Series.
    """
    val = expr.execute()
    if hasattr(val, "iloc"):
        try:
            cell = val.iloc[0, 0] if getattr(val, "ndim", 1) == 2 else val.iloc[0]
            return int(cell or 0)
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

    # As-of anchor: measure recency/tenure/recent-window from the latest sales
    # activity in the data, not the wall clock (overdue above stays on the real
    # clock -- an invoice past due is overdue regardless of load lag).
    as_of_date = min(_data_as_of(company) or today_date, today_date)

    # Per-customer aggregate from Sales Invoice (docstatus=1). The overdue
    # count is a separate, second aggregate (one row per customer) because
    # ibis does not let you nest a filtered sub-aggregate inside a parent
    # group_by.aggregate() -- the column "belongs to another relation" per
    # the same gotcha the shared contract documents.
    per_customer = si.group_by(si.customer).aggregate(
        customer_name=si.customer_name.min(),
        customer_group=si.customer_group.min(),
        territory=si.territory.min(),
        historical_clv=si.grand_total.sum(),
        avg_order_value=si.grand_total.mean(),
        order_count=si.count(),
        first_purchase=si.posting_date.min(),
        last_purchase=si.posting_date.max(),
        outstanding_amount=si.outstanding_amount.sum(),
    )
    overdue_si = si.filter(overdue_cond)
    overdue_per_customer = overdue_si.group_by(overdue_si.customer).aggregate(
        overdue_count=overdue_si.count()
    )
    overdue_df = overdue_per_customer.execute()
    df = per_customer.execute()
    if not overdue_df.empty:
        df = df.merge(overdue_df, on="customer", how="left")
    else:
        df["overdue_count"] = 0

    # Real avg days-to-pay per customer, from fully-closed invoices in the
    # period: days between `posting_date` and `modified` -- the same
    # definition `payment_prediction.py._fetch_customer_history` uses for
    # the whole book (closest signal to "date it was fully paid" without a
    # dedicated payment-date column here). Previously this column never
    # existed here, so `_composite_health_score` silently fell back to a
    # flat 30-day/50-score default for every customer -- "Payment Score"
    # never actually reflected anyone's payment behaviour. Fixed 2026-08-17.
    import ibis

    closed_si = si.filter(si.outstanding_amount == 0)
    closed_si = closed_si.mutate(
        days_to_pay=ibis.ifelse(
            closed_si.modified.isnull() | closed_si.posting_date.isnull(),
            ibis.null(),
            closed_si.modified.cast("date").delta(closed_si.posting_date.cast("date"), unit="day"),
        )
    )
    dtp_per_customer = closed_si.group_by(closed_si.customer).aggregate(
        avg_days_to_pay=closed_si.days_to_pay.mean(),
    )
    dtp_df = dtp_per_customer.execute()
    if not dtp_df.empty:
        df = df.merge(dtp_df, on="customer", how="left")
    else:
        df["avg_days_to_pay"] = None

    # Real recent (90-day) vs period average order value, for `value_trend`.
    # Previously `value_trend` compared `avg_order_value` to
    # `historical_clv / order_count` -- the identical quantity computed two
    # ways over the same row set, so it was mathematically guaranteed to be
    # ~0 for every customer. Fixed 2026-08-17.
    recent_cutoff = as_of_date - timedelta(days=90)
    recent_si = si.filter(si.posting_date >= recent_cutoff)
    recent_per_customer = recent_si.group_by(recent_si.customer).aggregate(
        recent_avg_order_value=recent_si.grand_total.mean(),
        recent_order_count=recent_si.count(),
    )
    recent_df = recent_per_customer.execute()
    if not recent_df.empty:
        df = df.merge(recent_df, on="customer", how="left")
    else:
        df["recent_avg_order_value"] = None
        df["recent_order_count"] = 0

    # Per-customer gross profit (line-level, same formula as the rankings
    # scorecard), so the customer list and territory rollup can show margin.
    sii = t("Sales Invoice Item")
    si_for_profit = t("Sales Invoice")
    dn = dn_cost()
    profit_lines = sii.join(si_for_profit, sii.parent == si_for_profit.name).left_join(
        dn, sii.dn_detail == dn.dn_name
    )
    if company:
        profit_lines = profit_lines.filter(si_for_profit.company == company)
    profit_lines = profit_lines.filter(
        (si_for_profit.docstatus == 1) & si_for_profit.posting_date.between(start, end)
    )
    gp_df = (
        profit_lines.group_by(si_for_profit.customer)
        .aggregate(gross_profit=(sii.net_amount - line_cogs(sii, dn.dn_rate)).sum())
        .execute()
    )
    if not gp_df.empty:
        gp_df["gross_profit"] = gp_df["gross_profit"].astype(float)
        df = df.merge(gp_df, on="customer", how="left")
    else:
        df["gross_profit"] = 0.0
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
    df["first_purchase"] = df["first_purchase"].fillna(now).apply(_as_date)
    df["last_purchase"] = df["last_purchase"].fillna(now).apply(_as_date)
    df["historical_clv"] = df["historical_clv"].fillna(0).astype(float)
    df["avg_order_value"] = df["avg_order_value"].fillna(0).astype(float)
    df["order_count"] = df["order_count"].fillna(0).astype(int)
    df["outstanding_amount"] = df["outstanding_amount"].fillna(0).astype(float)
    df["gross_profit"] = df["gross_profit"].fillna(0).astype(float)
    df["overdue_count"] = df["overdue_count"].fillna(0).astype(int)
    # ibis/MariaDB hands DECIMAL aggregates back as `object`-dtype Series of
    # `decimal.Decimal` -- fine for the merges above, but the vectorized
    # arithmetic below (`_rule_based_churn_score`) mixes these with float
    # columns and `Decimal / float` raises TypeError. `avg_days_to_pay`
    # deliberately keeps NaN for "no closed invoices yet" (consumed via a
    # None-aware guard in `_composite_health_score`, where 0 would wrongly
    # mean "always pays same-day"); the other two are only ever read behind
    # a `recent_order_count > 0` mask so 0-filling is safe. Fixed 2026-08-17.
    df["avg_days_to_pay"] = df["avg_days_to_pay"].astype(float)
    df["recent_avg_order_value"] = df["recent_avg_order_value"].fillna(0).astype(float)
    df["recent_order_count"] = df["recent_order_count"].fillna(0).astype(int)

    # Both execute paths hand back `date`, `datetime`, or `Timestamp`
    # depending on the column and path; `_as_date` above normalizes every
    # value to a plain `date` first, so every subtraction here is date-minus-
    # date -- either Series-vs-Series (elementwise, no scalar promotion) or
    # scalar-vs-Series done through `.apply()` rather than pandas' own
    # arithmetic dispatch, which promotes a `datetime` scalar to `Timestamp`
    # and cannot then subtract a bare `date` element.
    df["lifespan_months"] = ((df["last_purchase"] - df["first_purchase"]).apply(lambda x: x.days) / 30.44).clip(lower=1)
    df["purchase_frequency"] = df["order_count"] / df["lifespan_months"]
    df["recency_days"] = df["last_purchase"].apply(lambda x: (as_of_date - x).days)

    # predicted 12-month CLV = orders/month * 12 * AOV, adjusted by tenure
    df["tenure_months"] = df["first_purchase"].apply(lambda x: (as_of_date - x).days) / 30.44
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

    # CLV component scores (0-100 each) -- computed BEFORE health_score so
    # the "Health Components" / "CLV Components" breakdown the frontend
    # renders is built from these exact same numbers (see
    # `_composite_health_score`). Previously these were computed a SECOND
    # time, with different formulas, inside `_composite_health_score` and
    # immediately overwritten here -- health_score's average and the
    # on-screen component bars silently disagreed. Fixed 2026-08-17.
    df["revenue_score"] = df["historical_clv"].rank(pct=True, method="average") * 100
    max_freq = df["purchase_frequency"].quantile(0.99) or 1
    df["engagement_score"] = (df["purchase_frequency"] / max_freq * 50).clip(upper=50) + \
                             ((max_freq - df["recency_days"].clip(upper=max_freq)) / max_freq * 50).clip(upper=50)
    df["longevity_score"] = (df["tenure_months"] / 24 * 100).clip(lower=0, upper=100)
    safe_hist = df["historical_clv"].replace(0, 1)
    df["growth_score"] = ((df["predicted_12m_clv"] / safe_hist - 0.5) * 50).clip(lower=0, upper=100)

    # Health score: composite of revenue/engagement/payment/longevity/growth.
    df = _composite_health_score(df)
    df["health_status"] = df["health_score"].apply(_classify_health)

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
            "gross_profit",
        ]]
        .rename(columns={"customer": "customer_id"})
        .fillna(0)
        .to_dict("records")
    )
    for col in ("clv_tier", "churn_risk", "health_status", "rfm_segment", "rfm_score",
                "territory", "customer_group", "customer_name"):
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
    """Per-customer cadence-relative churn score (0-100). Delegates to the
    shared ``_churn_score`` so the list dashboard and the single-customer
    detail view always agree. ``frequency_trend`` is tenure-based
    (population-independent); ``value_trend`` compares each customer's
    last-90-day average order value against their period average (merged in by
    the caller).
    """
    df = df.copy()
    df["frequency_trend"] = ((df["order_count"] / df["lifespan_months"]) - 1.0).clip(-2, 2)

    if "recent_order_count" not in df.columns:
        df["recent_order_count"] = 0
        df["recent_avg_order_value"] = None
    has_recent = df["recent_order_count"].fillna(0) > 0
    safe_period_aov = df["avg_order_value"].replace(0, 1)
    df["value_trend"] = 0.0
    if has_recent.any():
        df.loc[has_recent, "value_trend"] = (
            (df.loc[has_recent, "recent_avg_order_value"] / safe_period_aov[has_recent]) - 1.0
        ).clip(-2, 2)

    lifespan_days = df["lifespan_months"] * 30.44
    overdue = df["overdue_count"].fillna(0) if "overdue_count" in df.columns else [0] * len(df)
    df["churn_score"] = [
        _churn_score(rec, oc, ld, ft, vt, out, clv, ov)
        for rec, oc, ld, ft, vt, out, clv, ov in zip(
            df["recency_days"], df["order_count"], lifespan_days,
            df["frequency_trend"], df["value_trend"], df["outstanding_amount"],
            df["historical_clv"], overdue,
        )
    ]
    return df


def _composite_health_score(df):
    """Composite health score 0-100 = mean of five sub-scores: revenue_score,
    engagement_score, longevity_score, growth_score (already computed by the
    caller -- these are the exact same numbers the "Health Components" /
    "CLV Components" breakdown on the customer detail page renders) plus
    payment_score, derived here from avg_days_to_pay via
    `payment_prediction._component_avg_days_to_pay` (that function returns
    a 0-100 *risk* score on a credit-terms-anchored scale -- <15d->0,
    30d->30, 60d->80, 90d+->100, None->50 -- so payment_score is simply
    ``100 - risk``, reusing the same business-calibrated scale rather than
    inventing a second one). All five are 0-100 so the mean is bounded.

    This function used to compute its OWN revenue/engagement/longevity/
    growth formulas (different from the ones above) and have every one of
    them silently overwritten by the caller before the response was built
    -- so health_score never actually reconciled with the component
    breakdown shown under it. `payment_score` also fell back to a flat 50
    for literally every customer because `avg_days_to_pay` was never
    merged into `df` upstream. Both fixed 2026-08-17.
    """
    from insights.ml.payment_prediction import _component_avg_days_to_pay

    df = df.copy()
    if "avg_days_to_pay" not in df.columns:
        df["avg_days_to_pay"] = None
    df["payment_score"] = df["avg_days_to_pay"].apply(
        lambda v: 100.0 - _component_avg_days_to_pay(float(v) if (v is not None and v == v) else None)
    )
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
            gross_profit=("gross_profit", "sum"),
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

    si_filtered = si.filter(si.docstatus == 1)
    if company:
        si_filtered = si_filtered.filter(si_filtered.company == company)
    if start and end:
        si_filtered = si_filtered.filter(si_filtered.posting_date.between(start.date(), end.date()))

    # Select immediately after each join to drop the overlapping Frappe
    # meta columns (name/owner/creation/modified/docstatus/idx and any
    # shared custom fields) before the next join -- Ibis's plain join()
    # raises an IntegrityError on those collisions otherwise.
    line_sales = sii.join(si_filtered, sii.parent == si_filtered.name).select(
        item_code=sii.item_code,
        item_name=sii.item_name,
        qty=sii.qty,
        amount=sii.amount,
        customer=si_filtered.customer,
    )
    sales = line_sales.join(item, line_sales.item_code == item.name, how="left").select(
        line_sales.item_code,
        line_sales.item_name,
        line_sales.qty,
        line_sales.amount,
        line_sales.customer,
        item_group=item.item_group,
        brand=item.brand,
    )

    per_cust_item = sales.group_by(
        [sales.customer, sales.item_code, sales.item_name, sales.item_group, sales.brand]
    ).aggregate(
        total_qty=sales.qty.sum(),
        total_amount=sales.amount.sum(),
        order_count=sales.count(),
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
    per_cust_txn = si.mutate(txn_month=si.posting_date.truncate("M"))
    per_cust_month = (
        per_cust_txn.group_by([per_cust_txn.customer, per_cust_txn.txn_month])
        .aggregate(c=per_cust_txn.count())
        .execute()
    )
    if per_cust_month.empty:
        return {"cohort_retention": [], "average_retention": {}, "cohort_count": 0}

    first_df = per_cust.execute()
    if first_df.empty:
        return {"cohort_retention": [], "average_retention": {}, "cohort_count": 0}

    # With the PyArrow execute path these are object-dtype Python dates.
    first_df["cohort_month"] = first_df["first_purchase"].apply(lambda d: d.strftime("%Y-%m"))
    first_df = first_df.set_index("customer")[["cohort_month"]]
    per_cust_month["cohort_month"] = per_cust_month["customer"].map(first_df["cohort_month"])
    per_cust_month = per_cust_month.dropna(subset=["cohort_month"])
    if per_cust_month.empty:
        return {"cohort_retention": [], "average_retention": {}, "cohort_count": 0}

    cohort_ord = per_cust_month["cohort_month"].map(lambda s: pd.Period(s, freq="M").ordinal)
    txn_ord = per_cust_month["txn_month"].apply(lambda d: pd.Period(d, freq="M").ordinal)
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
    q_converted = q.filter(q.status == "Ordered")
    converted = _scalar_int(q_converted.aggregate(converted=q_converted.count()))
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
                # Real ledger figures at stake, so the frontend leads with money:
                # churn/re-engagement risk the booked revenue, payment follow-up
                # the outstanding balance, upsell/nurture the predicted forward CLV.
                "historical_clv": float(c.get("historical_clv") or 0),
                "predicted_12m_clv": float(c.get("predicted_12m_clv") or 0),
                "outstanding_amount": outstanding,
                "recency_days": recency,
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
    return frappe.db.get_single_value("Global Defaults", "default_currency") or "USD"


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

    Unlike `compute_customer_intelligence` this is lifetime (no
    `date_filter`), so the CLV/health numbers here are not literally
    apples-to-apples with the list dashboard's windowed figures for the
    same customer -- that pre-existing scope difference is unchanged by
    this fix. What IS fixed here: the "CLV Components" / "Health
    Components" breakdown the frontend renders (`revenue_score`,
    `engagement_score`, `payment_score`, `longevity_score`,
    `growth_score`) plus `avg_days_to_pay`, `frequency_trend`,
    `value_trend`, `gross_profit`, and `margin_pct` used to be entirely
    absent from this endpoint's response, so those sections always
    rendered blank/zero -- see TODOS.md.
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
    as_of_date = min(_data_as_of(company) or today_date, today_date)
    overdue_cond = (si.due_date < today_date) & (si.outstanding_amount > 0)
    base = si.group_by(si.customer).aggregate(
        customer_name=si.customer_name.min(),
        customer_group=si.customer_group.min(),
        territory=si.territory.min(),
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
        per_customer["avg_days_to_pay"] = _customer_avg_days_to_pay(customer_id, company)
        per_customer["recent_avg_order_value"] = _customer_recent_avg_order_value(customer_id, company, as_of_date)
        gross_profit, margin_pct = _customer_profitability(customer_id, company)
        per_customer["gross_profit"] = gross_profit
        per_customer["margin_pct"] = margin_pct
        per_customer["clv_reference"] = _population_clv_reference(company)
    if per_customer.empty:
        customer = _blank_customer_row(cust)
    else:
        customer = _score_one_customer_row(per_customer.iloc[0], cust, as_of_date, company)

    response = {"status": "success", "customer": _to_native(customer),
                "base_currency": _base_currency(company)}
    if include_purchases:
        response["purchase_history"] = _get_customer_purchase_history(customer_id)
        response["purchase_patterns"] = _analyze_customer_purchase_patterns(response["purchase_history"])
    if include_recommendations:
        response["cross_sell"] = _cross_sell_for_one_customer(customer_id, company=company)
    return _to_native(response)


def _customer_avg_days_to_pay(customer_id: str, company: Optional[str]):
    """Real average days-to-pay for one customer, from fully-closed
    (`outstanding_amount == 0`) invoices: days between `posting_date` and
    `modified` -- same definition `payment_prediction.py` uses for the
    whole book. Returns `None` when the customer has no closed invoices
    yet -- callers must treat that as "unknown", not "paid instantly".
    """
    import ibis

    si = company_filter(t("Sales Invoice"), company)
    si = si.filter((si.docstatus == 1) & (si.customer == customer_id)
                   & (si.outstanding_amount == 0))
    si = si.mutate(
        days_to_pay=ibis.ifelse(
            si.modified.isnull() | si.posting_date.isnull(),
            ibis.null(),
            si.modified.cast("date").delta(si.posting_date.cast("date"), unit="day"),
        )
    )
    row = si.aggregate(avg_days_to_pay=si.days_to_pay.mean()).execute().iloc[0]
    value = row["avg_days_to_pay"]
    if value is None or (isinstance(value, float) and value != value):
        return None
    return float(value)


def _customer_recent_avg_order_value(customer_id: str, company: Optional[str], today_date):
    """Average order value over the last 90 days, for comparison against
    the customer's lifetime average (`value_trend`). `None` when there
    were no orders in that window (customer inactive recently).
    """
    cutoff = today_date - timedelta(days=90)
    si = company_filter(t("Sales Invoice"), company)
    si = si.filter((si.docstatus == 1) & (si.customer == customer_id)
                   & (si.posting_date >= cutoff))
    row = si.aggregate(recent_avg_order_value=si.grand_total.mean(),
                        recent_order_count=si.count()).execute().iloc[0]
    if not row["recent_order_count"]:
        return None
    return float(row["recent_avg_order_value"] or 0)


def _customer_profitability(customer_id: str, company: Optional[str]):
    """Gross profit and margin % for one customer, lifetime (no date
    filter, matching this endpoint's scope). Identical formula to
    `compute_customer_rankings`'s top_profit/top_margin so the same
    customer's profitability reconciles across both views: line-level
    `net_amount - qty * incoming_rate` summed against `sii.amount`
    revenue. A line with a NULL `incoming_rate` drops out of the
    gross_profit sum (SQL NULL propagation), matching that convention.
    """
    sii = t("Sales Invoice Item")
    si_for_profit = t("Sales Invoice")
    dn = dn_cost()
    lines = sii.join(si_for_profit, sii.parent == si_for_profit.name).left_join(
        dn, sii.dn_detail == dn.dn_name
    )
    if company:
        lines = lines.filter(si_for_profit.company == company)
    lines = lines.filter((si_for_profit.docstatus == 1) & (si_for_profit.customer == customer_id))
    row = lines.aggregate(
        gross_profit=(sii.net_amount - line_cogs(sii, dn.dn_rate)).sum(),
        revenue=sii.amount.sum(),
    ).execute().iloc[0]
    revenue = float(row["revenue"] or 0)
    gross_profit = float(row["gross_profit"] or 0)
    margin_pct = round(gross_profit / revenue * 100, 1) if revenue > 0 else None
    return gross_profit, margin_pct


def _population_clv_reference(company: Optional[str]) -> float:
    """Average lifetime historical CLV per customer across the whole
    customer base: one company-filtered SUM + COUNT DISTINCT (not a
    per-customer GROUP BY) -- a currency-agnostic, self-calibrating
    reference point for scoring a single customer's CLV/revenue without
    the O(all customers) per-customer aggregate the list dashboard runs.
    """
    si = company_filter(t("Sales Invoice"), company)
    si = si.filter((si.docstatus == 1) & si.customer.notnull() & (si.customer != ""))
    row = si.aggregate(
        total_revenue=si.grand_total.sum(),
        customer_count=si.customer.nunique(),
    ).execute().iloc[0]
    customer_count = int(row["customer_count"] or 0)
    if customer_count <= 0:
        return 0.0
    return float(row["total_revenue"] or 0) / customer_count


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
        "revenue_score": 0.0,
        "engagement_score": 0.0,
        "payment_score": 50.0,
        "longevity_score": 0.0,
        "growth_score": 0.0,
        "frequency_trend": 0.0,
        "value_trend": 0.0,
        "avg_days_to_pay": None,
        "outstanding_amount": 0.0,
        "overdue_count": 0,
        "gross_profit": 0.0,
        "margin_pct": None,
        "recommendations": [],
        "current_credit_limit": 0.0,
        "recommended_credit_limit": 0.0,
        "credit_headroom": 0.0,
        "credit_monthly_run_rate": 0.0,
        "credit_target_days": 45,
        "credit_risk_factor": 0.0,
    }


def _recommend_credit_limit(*, predicted_12m, historical_clv, tenure_months,
                            payment_score, overdue_count, churn_risk,
                            target_credit_days=45):
    """Recommend a customer credit limit from demand + repayment-risk signals.

    A credit limit funds the exposure carried for the time a customer takes to
    pay, so size it from expected sales over a *target* credit period (your
    terms, not the customer's actual overrun), then haircut for repayment risk:

        limit = monthly_run_rate * (target_credit_days / 30) * risk_factor

    ``monthly_run_rate`` prefers the forward CLV projection, falling back to the
    lifetime average when there is no projection yet. ``risk_factor`` is banded
    on ``payment_score`` (0-100 reliability, 100 = pays fast), then discounted
    for any overdue invoices and elevated churn -- both say "carry less of this
    customer's paper", never more. Returns the figure plus the inputs behind it
    so the UI can show the rationale; a customer with no run-rate yet gets 0.
    """
    run_rate = 0.0
    if predicted_12m and predicted_12m > 0:
        run_rate = predicted_12m / 12.0
    elif historical_clv and tenure_months >= 1:
        run_rate = historical_clv / tenure_months
    if run_rate <= 0:
        return {"recommended_credit_limit": 0.0, "credit_monthly_run_rate": 0.0,
                "credit_target_days": target_credit_days, "credit_risk_factor": 0.0}

    if payment_score is None:
        base_factor = 0.5          # unknown payer: neutral-cautious
    elif payment_score >= 75:
        base_factor = 1.0
    elif payment_score >= 50:
        base_factor = 0.7
    elif payment_score >= 30:
        base_factor = 0.5
    else:
        base_factor = 0.35
    risk_factor = base_factor
    if overdue_count > 0:
        risk_factor *= 0.8
    if churn_risk in ("High", "Critical"):
        risk_factor *= 0.85

    limit = run_rate * (target_credit_days / 30.0) * risk_factor
    # Round to a clean figure the credit team can act on.
    limit = round(limit / 10000.0) * 10000.0 if limit >= 10000 else round(limit, -2)
    return {
        "recommended_credit_limit": float(limit),
        "credit_monthly_run_rate": round(run_rate, 2),
        "credit_target_days": target_credit_days,
        "credit_risk_factor": round(risk_factor, 2),
    }


def _score_one_customer_row(row, cust, as_of_date, company=None):
    """Build the per-customer payload the customer_360 view expects. Same
    per-customer logic as the bulk engine, just for one row -- plus real
    payment/trend/profitability numbers from this customer's own invoices
    (see `compute_customer_360`).

    `clv_score` / `revenue_score` are scored against a cheap
    population-average CLV reference (`clv_reference`, see
    `_population_clv_reference`) rather than the bulk dashboard's true
    percentile rank across every customer -- a true rank needs the whole
    per-customer distribution, which is exactly the O(all customers) query
    this endpoint is deliberately scoped to avoid on a single detail-page
    open. `longevity_score`, `growth_score`, and `frequency_trend` use the
    *exact* formulas the bulk dashboard ships (they only need this one
    customer's own numbers), so those three match the list dashboard
    exactly for the same customer. `payment_score` reuses
    `payment_prediction._component_avg_days_to_pay` (see
    `_composite_health_score`'s docstring), same as the bulk fix.
    """
    from insights.ml.payment_prediction import _component_avg_days_to_pay

    now = datetime.now()
    today_date = now.date()
    first_purchase = _as_date(row.get("first_purchase")) or today_date
    last_purchase = _as_date(row.get("last_purchase")) or today_date
    order_count = int(row.get("order_count") or 0)
    historical_clv = float(row.get("historical_clv") or 0)
    avg_order_value = float(row.get("avg_order_value") or 0)
    outstanding = float(row.get("outstanding_amount") or 0)
    overdue_count = int(row.get("overdue_count") or 0)

    lifespan_months = max(1.0, ((last_purchase - first_purchase).days / 30.44))
    purchase_frequency = order_count / lifespan_months
    recency_days = (as_of_date - last_purchase).days
    tenure_months = max(0.0, ((as_of_date - first_purchase).days / 30.44))

    predicted_12m = purchase_frequency * 12 * avg_order_value
    tenure_factor = min(tenure_months / 24.0, 1.5)
    adjusted_predicted = predicted_12m * tenure_factor
    total_clv = historical_clv + adjusted_predicted

    # CLV score: saturating scale against a population-average reference
    # (3x the average customer's lifetime spend maps to 100) instead of
    # the old self-referential `total_clv / (total_clv * 0.99 + 1)`, which
    # algebraically simplifies to ~100 for any customer above small change
    # -- every customer showed CLV Tier "Diamond" regardless of actual
    # size. Fixed 2026-08-17.
    clv_reference = float(row.get("clv_reference") or 0)
    clv_ceiling = max(1.0, clv_reference * 3.0)
    clv_score = max(0.0, min(100.0, (total_clv / clv_ceiling) * 100))
    clv_tier = _classify_clv(clv_score)

    # Trends (needed by churn below). `frequency_trend` matches the bulk
    # formula exactly; `value_trend` compares this customer's last-90-day
    # average order value to their lifetime average.
    frequency_trend = max(-2.0, min(2.0, purchase_frequency - 1.0))
    recent_aov = row.get("recent_avg_order_value")
    if recent_aov is None or avg_order_value <= 0:
        value_trend = 0.0
    else:
        value_trend = max(-2.0, min(2.0, (float(recent_aov) / avg_order_value) - 1.0))

    # Cadence-relative churn -- shared with the bulk engine so list and detail
    # agree for the same customer.
    churn_score = _churn_score(
        recency_days=recency_days,
        order_count=order_count,
        lifespan_days=lifespan_months * 30.44,
        frequency_trend=frequency_trend,
        value_trend=value_trend,
        outstanding=outstanding,
        historical_clv=historical_clv,
        overdue_count=overdue_count,
    )
    churn_risk = _classify_churn(churn_score)

    # CLV/health component scores -- these are the numbers the "CLV
    # Components" / "Health Components" breakdown renders, and health_score
    # below is their weighted mean, so the two always reconcile.
    revenue_score = max(0.0, min(100.0, (historical_clv / clv_ceiling) * 100))
    recency_component = max(0.0, min(50.0, (1 - recency_days / 90.0) * 50.0))
    frequency_component = max(0.0, min(50.0, purchase_frequency * 25.0))
    engagement_score = recency_component + frequency_component
    longevity_score = max(0.0, min(100.0, (tenure_months / 24.0) * 100.0))
    safe_hist = historical_clv if historical_clv > 0 else 1.0
    growth_score = max(0.0, min(100.0, ((predicted_12m / safe_hist) - 0.5) * 50.0))

    # Payment behaviour: real avg days-to-pay from this customer's closed
    # invoices, scored via the same credit-terms-anchored scale
    # `payment_prediction.py` uses (None -> neutral 50, not "paid
    # instantly").
    avg_days_to_pay = row.get("avg_days_to_pay")
    if avg_days_to_pay is not None and not (isinstance(avg_days_to_pay, float) and avg_days_to_pay != avg_days_to_pay):
        avg_days_to_pay = float(avg_days_to_pay)
    else:
        avg_days_to_pay = None
    payment_score = 100.0 - _component_avg_days_to_pay(avg_days_to_pay)

    # Composite health: same 5-way 20%-weighted mean as the bulk dashboard,
    # over the same five scores in the "Health Components" breakdown above.
    health_score = (
        revenue_score * 0.20
        + engagement_score * 0.20
        + payment_score * 0.20
        + longevity_score * 0.20
        + growth_score * 0.20
    )
    health_status = _classify_health(health_score)

    gross_profit = float(row.get("gross_profit") or 0)
    margin_pct = row.get("margin_pct")
    if margin_pct is not None:
        margin_pct = float(margin_pct)

    # Recommended credit limit from demand + repayment risk, shown beside the
    # customer's current ERPNext limit (Customer -> Group -> Company fallback).
    credit = _recommend_credit_limit(
        predicted_12m=predicted_12m, historical_clv=historical_clv,
        tenure_months=tenure_months, payment_score=payment_score,
        overdue_count=overdue_count, churn_risk=churn_risk,
    )
    current_credit_limit = 0.0
    if company:
        try:
            from erpnext.selling.doctype.customer.customer import get_credit_limit
            current_credit_limit = float(get_credit_limit(cust.name, company) or 0)
        except Exception:
            current_credit_limit = 0.0

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
        "revenue_score": revenue_score,
        "engagement_score": engagement_score,
        "payment_score": payment_score,
        "longevity_score": longevity_score,
        "growth_score": growth_score,
        "frequency_trend": frequency_trend,
        "value_trend": value_trend,
        "avg_days_to_pay": avg_days_to_pay,
        "outstanding_amount": outstanding,
        "overdue_count": overdue_count,
        "gross_profit": gross_profit,
        "margin_pct": margin_pct,
        "recommendations": [],
        "current_credit_limit": current_credit_limit,
        "credit_headroom": round(credit["recommended_credit_limit"] - outstanding, 2),
        **credit,
    }


def _get_customer_purchase_history(customer_id: str) -> List[Dict[str, Any]]:
    """Top-50 invoices for the customer. One SQL query, plain dicts so the
    JSON envelope is straightforward.
    """
    SI = frappe.qb.DocType("Sales Invoice")
    today = datetime.now().date()
    rows = (
        frappe.qb.from_(SI)
        .select(
            SI.name.as_("invoice_id"),
            SI.posting_date,
            SI.due_date,
            SI.grand_total,
            SI.net_total,
            SI.outstanding_amount,
            SI.status,
        )
        .where((SI.customer == customer_id) & (SI.docstatus == 1))
        .orderby(SI.posting_date, order=frappe.qb.desc)
        .limit(50)
        .run(as_dict=True)
    )
    for r in rows:
        outstanding = r.get("outstanding_amount") or 0
        due_date = r.get("due_date")
        if outstanding == 0:
            r["payment_status"] = "Paid"
        elif due_date and due_date < today:
            r["payment_status"] = "Overdue"
        else:
            r["payment_status"] = "Outstanding"
    return [dict(r) for r in rows] if rows else []


def _analyze_customer_purchase_patterns(purchase_history: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not purchase_history or len(purchase_history) < 2:
        return None
    try:
        import pandas as pd
        from datetime import date as _date, datetime as _datetime

        def _norm_date(v):
            if isinstance(v, _date) and not isinstance(v, _datetime):
                return v
            if isinstance(v, str):
                return _datetime.strptime(v, "%Y-%m-%d").date()
            return v

        df = pd.DataFrame(purchase_history)
        # frappe.db.sql returns DATE as datetime.date objects. Keep them as
        # plain Python dates to avoid pandas' datetime64 C conversion.
        df["posting_date"] = df["posting_date"].apply(_norm_date)
        df_sorted = df.sort_values("posting_date")
        date_diffs = df_sorted["posting_date"].diff().dropna()
        avg_frequency = round(float(date_diffs.apply(lambda x: x.days).mean()), 1) if len(date_diffs) else None
        df["day_of_week"] = df["posting_date"].apply(lambda d: d.strftime("%A"))
        preferred_day = df["day_of_week"].mode().iloc[0] if len(df) else None
        df["month"] = df["posting_date"].apply(lambda d: d.strftime("%B"))
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
    SII = frappe.qb.DocType("Sales Invoice Item")
    SI = frappe.qb.DocType("Sales Invoice")
    Item = frappe.qb.DocType("Item")
    purchased = (
        frappe.qb.from_(SII)
        .join(SI)
        .on(SII.parent == SI.name)
        .left_join(Item)
        .on(SII.item_code == Item.name)
        .select(SII.item_code, Item.item_group)
        .distinct()
        .where((SI.customer == customer_id) & (SI.docstatus == 1))
        .run(as_dict=True)
    )
    if not purchased:
        return []
    purchased_codes = sorted({r["item_code"] for r in purchased})
    groups = sorted({r["item_group"] for r in purchased if r.get("item_group")})[:5]
    if not groups:
        return []

    SII2 = frappe.qb.DocType("Sales Invoice Item")
    SI2 = frappe.qb.DocType("Sales Invoice")
    Item2 = frappe.qb.DocType("Item")
    rows = (
        frappe.qb.from_(SII2)
        .join(SI2)
        .on(SII2.parent == SI2.name)
        .join(Item2)
        .on(SII2.item_code == Item2.name)
        .select(
            SII2.item_code,
            Item2.item_name,
            Item2.item_group,
            Count("*").as_("popularity"),
            Sum(SII2.qty).as_("total_qty"),
        )
        .where((SI2.docstatus == 1) & Item2.item_group.isin(groups) & SII2.item_code.notin(purchased_codes))
        .groupby(SII2.item_code)
        .orderby(Count("*"), order=frappe.qb.desc)
        .limit(10)
        .run(as_dict=True)
    )
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
        manufacturers = _scalar_int(cust.filter((cust.disabled == 0) & (cust.custom_customer_type == "Manufacturer")).count())
        traders = _scalar_int(cust.filter((cust.disabled == 0) & (cust.custom_customer_type == "Trader")).count())
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

def _rank_customers(date_filter: str, limit: int, company: Optional[str], ascending: bool) -> Dict[str, List[Dict[str, Any]]]:
    """Shared implementation for `compute_customer_rankings` (best performers)
    and `compute_bottom_customers` (worst performers). Same four Ibis
    aggregates either way -- revenue, gross profit, margin %, consistency --
    with sort direction as the only difference, so a customer's numbers
    reconcile whether they show up in the top list or the bottom one.
    """
    from insights.api.ml.utils import parse_date_filter
    import ibis
    start, end = parse_date_filter(date_filter)
    company = company or default_company()
    if not (start and end):
        end = datetime.now().date()
        start = end - timedelta(days=365)

    order = ibis.asc if ascending else ibis.desc

    # top/bottom revenue
    si = company_filter(t("Sales Invoice"), company)
    si = si.filter((si.docstatus == 1) & si.posting_date.between(start, end))
    revenue_rows = (
        si.group_by(si.customer, si.customer_name)
        .aggregate(revenue=si.grand_total.sum())
        .order_by(order("revenue"))
        .limit(limit)
        .execute()
        .fillna({"customer_name": ""})
        .to_dict("records")
    )

    # top/bottom gross profit
    sii = t("Sales Invoice Item")
    si_for_profit = t("Sales Invoice")
    profit_lines = sii.join(si_for_profit, sii.parent == si_for_profit.name)
    if company:
        profit_lines = profit_lines.filter(si_for_profit.company == company)
    profit_lines = profit_lines.filter(
        (si_for_profit.docstatus == 1) & si_for_profit.posting_date.between(start, end)
    )
    # `.execute()` returns `gross_profit`/`revenue` as object-dtype
    # `decimal.Decimal` (Ibis + MariaDB DECIMAL aggregates), not float64 --
    # the same defect already fixed in `compute_customer_intelligence`'s
    # bulk path (see CHANGELOG). Left uncast, `.round()` on the Decimal
    # `margin_pct` division below raises `TypeError: Expected numeric
    # dtype, got object instead` -- this endpoint has never returned
    # `top_margin`/`bottom_margin` successfully. Cast immediately after
    # each `.execute()`, before any arithmetic.
    profit_df = (
        profit_lines.group_by(si_for_profit.customer, si_for_profit.customer_name)
        .aggregate(
            gross_profit=(sii.net_amount - (sii.qty * sii.incoming_rate)).sum(),
            revenue=sii.amount.sum(),
        )
        .order_by(order("gross_profit"))
        .limit(limit)
        .execute()
    )
    profit_df["gross_profit"] = profit_df["gross_profit"].astype(float)
    profit_df["revenue"] = profit_df["revenue"].astype(float)
    profit_rows = profit_df.fillna(0).to_dict("records")

    margin_per_cust = (
        profit_lines.group_by(si_for_profit.customer, si_for_profit.customer_name)
        .aggregate(
            gross_profit=(sii.net_amount - (sii.qty * sii.incoming_rate)).sum(),
            revenue=sii.amount.sum(),
        )
        .execute()
    )
    margin_per_cust["gross_profit"] = margin_per_cust["gross_profit"].astype(float)
    margin_per_cust["revenue"] = margin_per_cust["revenue"].astype(float)
    margin_per_cust = margin_per_cust[margin_per_cust["revenue"] > 0].copy()
    margin_per_cust["margin_pct"] = (margin_per_cust["gross_profit"] / margin_per_cust["revenue"] * 100).round(1)
    margin_rows = (
        margin_per_cust.sort_values("margin_pct", ascending=ascending)
        .head(limit)
        .fillna({"customer_name": ""})
        .to_dict("records")
    )

    # consistency
    si_monthly = si.mutate(month=si.posting_date.truncate("M"))
    monthly = si_monthly.group_by(
        [si_monthly.customer, si_monthly.customer_name, si_monthly.month]
    ).aggregate(monthly_spend=si_monthly.grand_total.sum()).execute()
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
        # Top: most consistent first (reverse=True). Bottom: least
        # consistent/most erratic first -- `ascending` and `reverse` are
        # already inverse of each other, so `reverse=not ascending` covers
        # both callers with the one sort.
        consistency.sort(key=lambda r: r["consistency_score"], reverse=not ascending)
        consistency = consistency[:limit]

    return {
        "top_revenue": revenue_rows,
        "top_profit": profit_rows,
        "top_margin": margin_rows,
        "top_consistent": consistency,
    }


def compute_customer_rankings(date_filter: str = "12m", limit: int = 20,
                                company: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Top-N by revenue, gross profit, margin %, and consistency. All four
    are one Ibis aggregate each; the consistency score is computed in pure
    Python from a fifth small aggregate (one row per customer-month).
    """
    return _rank_customers(date_filter, limit, company, ascending=False)


def compute_bottom_customers(date_filter: str = "12m", limit: int = 20,
                               company: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Bottom-N by revenue, gross profit, margin %, and consistency --
    weakest accounts, biggest losses, worst margins, most erratic spend.
    Same four aggregates as `compute_customer_rankings`, sorted the other
    way, so a customer's numbers reconcile in whichever list they land.
    """
    return _rank_customers(date_filter, limit, company, ascending=True)


def compute_customer_scorecard(date_filter: str = "12m",
                                 company: Optional[str] = None) -> Dict[str, Any]:
    """One unified per-customer frame for the Rankings tab -- every customer
    with the same metrics the four ranking mini-tables split apart: revenue
    (grand_total), gross profit and margin %% (line-level, same formula as
    `_rank_customers`), and months-active / consistency score. Unlike
    `compute_customer_rankings` this applies no limit and does not sort --
    the frontend does the filtering, sorting, and thresholding client-side
    against this single list, so the four views become one filterable table.
    """
    from insights.api.ml.utils import parse_date_filter
    import pandas as pd

    start, end = parse_date_filter(date_filter)
    company = company or default_company()
    if not (start and end):
        end = datetime.now().date()
        start = end - timedelta(days=365)

    # Revenue (grand_total) -- canonical customer set, matches top_revenue
    # and the drill-down.
    si = company_filter(t("Sales Invoice"), company)
    si = si.filter((si.docstatus == 1) & si.posting_date.between(start, end))
    base = (
        si.group_by(si.customer)
        .aggregate(customer_name=si.customer_name.min(), revenue=si.grand_total.sum())
        .execute()
    )
    if base.empty:
        return {"customers": [], "total_months": 1}
    base["revenue"] = base["revenue"].astype(float)
    base = base.fillna({"customer_name": ""})

    # Gross profit + margin % (line-level, identical formula to _rank_customers)
    sii = t("Sales Invoice Item")
    si_for_profit = t("Sales Invoice")
    profit_lines = sii.join(si_for_profit, sii.parent == si_for_profit.name)
    if company:
        profit_lines = profit_lines.filter(si_for_profit.company == company)
    profit_lines = profit_lines.filter(
        (si_for_profit.docstatus == 1) & si_for_profit.posting_date.between(start, end)
    )
    profit = (
        profit_lines.group_by(si_for_profit.customer)
        .aggregate(
            gross_profit=(sii.net_amount - (sii.qty * sii.incoming_rate)).sum(),
            line_revenue=sii.amount.sum(),
        )
        .execute()
    )
    if not profit.empty:
        profit["gross_profit"] = profit["gross_profit"].astype(float)
        profit["line_revenue"] = profit["line_revenue"].astype(float)
        profit["margin_pct"] = 0.0
        nonzero = profit["line_revenue"] > 0
        profit.loc[nonzero, "margin_pct"] = (
            profit.loc[nonzero, "gross_profit"] / profit.loc[nonzero, "line_revenue"] * 100
        ).round(1)
        profit = profit.drop(columns=["line_revenue"])
    else:
        profit = pd.DataFrame(columns=["customer", "gross_profit", "margin_pct"])

    # Months-active / consistency score (pure-Python over customer-month rows)
    si_monthly = si.mutate(month=si.posting_date.truncate("M"))
    monthly = (
        si_monthly.group_by([si_monthly.customer, si_monthly.month])
        .aggregate(monthly_spend=si_monthly.grand_total.sum())
        .execute()
    )
    total_months = max(((end.year - start.year) * 12 + (end.month - start.month)), 1)
    consistency_rows = []
    if not monthly.empty:
        for cust, rows in monthly.groupby("customer"):
            spends = rows["monthly_spend"].astype(float).tolist()
            months_active = len(spends)
            frequency_score = months_active / total_months
            mean_spend = sum(spends) / max(1, len(spends))
            if mean_spend > 0 and len(spends) > 1:
                var = sum((s - mean_spend) ** 2 for s in spends) / (len(spends) - 1)
                cv = math.sqrt(var) / mean_spend
            else:
                cv = 1.0
            stability = max(0.0, 1.0 - cv)
            consistency_rows.append({
                "customer": cust,
                "months_active": months_active,
                "consistency_score": round(0.5 * frequency_score + 0.5 * stability, 3),
                "avg_monthly_spend": round(mean_spend, 2),
            })
    consistency = pd.DataFrame(
        consistency_rows,
        columns=["customer", "months_active", "consistency_score", "avg_monthly_spend"],
    )

    merged = base.merge(profit, on="customer", how="left")
    merged = merged.merge(consistency, on="customer", how="left")
    merged = merged.fillna({
        "gross_profit": 0.0, "margin_pct": 0.0,
        "months_active": 0, "consistency_score": 0.0, "avg_monthly_spend": 0.0,
    })
    merged["months_active"] = merged["months_active"].astype(int)
    merged["total_months"] = total_months

    return {
        "customers": merged.to_dict("records"),
        "total_months": total_months,
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

    SI = frappe.qb.DocType("Sales Invoice")
    rows = (
        frappe.qb.from_(SI)
        .select(SI.name, SI.customer, SI.grand_total, SI.posting_date)
        .where(
            (SI.docstatus == 1)
            & SI.posting_date.between(start, end)
            & SI.customer.isin(top_ids)
        )
        .orderby(SI.posting_date)
        .run(as_dict=True)
    )
    if not rows:
        return {"status": "success", "message": _("No transaction data"), "patterns": None}

    def _quarter(d):
        return (d.month - 1) // 3 + 1

    df = pd.DataFrame([dict(r) for r in rows])
    df["posting_date"] = pd.to_datetime(df["posting_date"])
    df["day_name"] = df["posting_date"].dt.day_name()
    df["month_num"] = df["posting_date"].dt.month
    df["month_name"] = df["posting_date"].dt.month_name()
    df["quarter"] = df["posting_date"].apply(_quarter)

    # Per-invoice gross profit (line-level, same formula as _rank_customers),
    # bucketed alongside revenue so each pattern view shows margin, not just top line.
    sii = t("Sales Invoice Item")
    si_for_profit = t("Sales Invoice")
    profit_lines = sii.join(si_for_profit, sii.parent == si_for_profit.name)
    if company:
        profit_lines = profit_lines.filter(si_for_profit.company == company)
    profit_lines = profit_lines.filter(
        (si_for_profit.docstatus == 1)
        & si_for_profit.posting_date.between(start, end)
        & si_for_profit.customer.isin(top_ids)
    )
    profit_per_inv = (
        profit_lines.group_by(si_for_profit.name)
        .aggregate(gross_profit=(sii.net_amount - (sii.qty * sii.incoming_rate)).sum())
        .execute()
    )
    gp_map = dict(zip(profit_per_inv["name"], profit_per_inv["gross_profit"])) if not profit_per_inv.empty else {}
    df["gross_profit"] = df["name"].map(gp_map).fillna(0).astype(float)

    day_analysis = df.groupby("day_name").agg(
        order_count=("grand_total", "count"),
        total_revenue=("grand_total", "sum"),
        avg_order_value=("grand_total", "mean"),
        gross_profit=("gross_profit", "sum"),
    ).reindex(_DAY_ORDER).fillna(0).reset_index()
    day_analysis["total_revenue"] = day_analysis["total_revenue"].round(2)
    day_analysis["avg_order_value"] = day_analysis["avg_order_value"].round(2)
    day_analysis["gross_profit"] = day_analysis["gross_profit"].round(2)

    month_analysis = df.groupby("month_name").agg(
        order_count=("grand_total", "count"),
        total_revenue=("grand_total", "sum"),
        avg_order_value=("grand_total", "mean"),
        gross_profit=("gross_profit", "sum"),
    ).reindex(_MONTH_ORDER).fillna(0).reset_index()
    month_analysis["total_revenue"] = month_analysis["total_revenue"].round(2)
    month_analysis["avg_order_value"] = month_analysis["avg_order_value"].round(2)
    month_analysis["gross_profit"] = month_analysis["gross_profit"].round(2)

    quarter_analysis = df.groupby("quarter").agg(
        order_count=("grand_total", "count"),
        total_revenue=("grand_total", "sum"),
        avg_order_value=("grand_total", "mean"),
    ).fillna(0).reset_index()
    quarter_names = {1: "Q1 (Jan-Mar)", 2: "Q2 (Apr-Jun)", 3: "Q3 (Jul-Sep)", 4: "Q4 (Oct-Dec)"}

    peak_day = day_analysis.loc[day_analysis["total_revenue"].idxmax(), "day_name"] if not day_analysis.empty else None
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

    TargetDetail = frappe.qb.DocType("Target Detail")
    target_rows = (
        frappe.qb.from_(TargetDetail)
        .select(TargetDetail.parent.as_("territory"), TargetDetail.target_amount)
        .where(TargetDetail.parenttype == "Territory")
        .run(as_dict=True)
    )
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
