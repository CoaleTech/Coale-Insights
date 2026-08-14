from __future__ import annotations

# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Sales Intelligence -- Ibis-native rewrite.

Was a `BaseMLModel` subclass that ran ~10 pandas-heavy sub-analyses on
~50,000-row DataFrames materialised in the web worker (24 months of
Sales Invoices), then cached the result in Redis and pre-warmed it via
the scheduler. On Frappe Cloud the work-horse's ``fork()`` segfaulted
(see ``insights.api.ml.ibis_source`` for the long version).

Every sub-analysis is now a small Ibis expression that compiles to one
SQL statement and runs inside MariaDB. Each returns at most a few
hundred rows, which the Python side reshapes into the dict the Revenue
dashboard already consumes. No cache, no background job, no fork.

`BaseMLModel` is not used (it is being deleted centrally after every
domain lands). The class wrapper is gone too -- the public surface is a
small set of module-level functions returning the same shapes the
frontend already destructures. The aggregate ``train()`` / ``predict()``
shape the old class returned is still produced by ``run_sales_intelligence``
and ``get_sales_intelligence`` for backward compatibility.
"""

from datetime import datetime, timedelta
from typing import Any

import ibis

from insights.api.ml.ibis_source import company_filter, default_company, t
from insights.api.ml.utils import parse_date_filter
from insights.ml.inventory_intelligence import DemandForecasting
from insights.ml.sales_forecasting import get_sales_forecast

# ---------------------------------------------------------------------------
# Revenue metrics
# ---------------------------------------------------------------------------


def calculate_revenue_metrics(
    date_filter: str = "12m",
    company: str | None = None,
) -> dict[str, Any]:
    """Total revenue, AOV, customer frequency, daily/weekly/monthly series.

    All three series are aggregated inside MariaDB; the post-aggregate
    size is at most ~365 rows for daily, ~52 for weekly, ~24 for monthly.
    """
    si = company_filter(t("Sales Invoice"), company or default_company()).filter(
        t("Sales Invoice").docstatus == 1
    ).filter(t("Sales Invoice").is_return == 0)
    start, _ = parse_date_filter(date_filter)
    if start is not None:
        si = si.filter(si.posting_date >= start.date())

    # One aggregate for the headline numbers.
    overall_df = si.aggregate(
        total_revenue=si.grand_total.sum(),
        total_transactions=si.count(),
        unique_customers=si.customer.nunique(),
    ).execute()
    overall = overall_df.iloc[0]
    total_revenue = float(overall["total_revenue"] or 0)
    total_transactions = int(overall["total_transactions"] or 0)
    unique_customers = int(overall["unique_customers"] or 0)
    avg_order_value = round(total_revenue / total_transactions, 2) if total_transactions else 0

    # Daily series (last 30 days).
    daily_cutoff = (datetime.now() - timedelta(days=30)).date()
    si_daily = si.filter(si.posting_date >= daily_cutoff)
    daily_df = (
        si_daily.group_by(si_daily.posting_date)
        .aggregate(
            revenue=si_daily.grand_total.sum(),
            transactions=si_daily.count(),
        )
        .order_by("posting_date")
        .execute()
    )
    daily_sales: list[dict[str, Any]] = [
        {
            "date": str(r["posting_date"]),
            "revenue": float(r["revenue"] or 0),
            "transactions": int(r["transactions"] or 0),
        }
        for _, r in daily_df.iterrows()
    ]

    # Weekly series (ISO week, last 12 weeks).
    si_weekly = si.mutate(year_week=si.posting_date.strftime("%x-W%V")).filter(
        si.posting_date >= (datetime.now() - timedelta(weeks=12)).date()
    )
    weekly_df = (
        si_weekly.group_by(["year_week"])
        .aggregate(
            revenue=si_weekly.grand_total.sum(),
            transactions=si_weekly.count(),
        )
        .order_by("year_week")
        .execute()
    )
    weekly_sales: list[dict[str, Any]] = [
        {
            "year_week": r["year_week"],
            "revenue": float(r["revenue"] or 0),
            "transactions": int(r["transactions"] or 0),
        }
        for _, r in weekly_df.iterrows()
    ]

    # Monthly series (last 24 months).
    si_monthly = si.mutate(period=si.posting_date.strftime("%Y-%m"))
    monthly_df = (
        si_monthly.group_by("period")
        .aggregate(
            revenue=si_monthly.grand_total.sum(),
            transactions=si_monthly.count(),
            unique_customers=si_monthly.customer.nunique(),
        )
        .order_by("period")
        .execute()
    )
    monthly_sales: list[dict[str, Any]] = [
        {
            "period": r["period"],
            "revenue": float(r["revenue"] or 0),
            "transactions": int(r["transactions"] or 0),
            "unique_customers": int(r["unique_customers"] or 0),
        }
        for _, r in monthly_df.iterrows()
    ]

    # Average days between orders per customer -- a small per-customer
    # aggregate. We compute the span = max(posting_date) - min(posting_date)
    # and the order count; the answer is mean(span) / mean(orders - 1)
    # restricted to customers with > 1 order.
    per_customer_df = (
        si.group_by(si.customer)
        .aggregate(
            first_sale=si.posting_date.min(),
            last_sale=si.posting_date.max(),
            order_count=si.count(),
        )
        .execute()
    )
    repeat = per_customer_df[per_customer_df["order_count"] > 1]
    if len(repeat) > 0:
        repeat = repeat.copy()
        # With the PyArrow execute path these are object-dtype date/datetime
        # objects, not datetime64, so .dt.days is unavailable.
        repeat["days_span"] = (repeat["last_sale"] - repeat["first_sale"]).apply(lambda x: x.days)
        total_days = float(repeat["days_span"].sum())
        total_orders_minus_1 = float((repeat["order_count"] - 1).sum())
        avg_days_between_orders = round(
            total_days / total_orders_minus_1, 1
        ) if total_orders_minus_1 > 0 else 0
    else:
        avg_days_between_orders = 0

    return {
        "total_revenue": total_revenue,
        "total_transactions": total_transactions,
        "avg_order_value": avg_order_value,
        "avg_days_between_orders": avg_days_between_orders,
        "unique_customers": unique_customers,
        "daily_sales": daily_sales,
        "weekly_sales": weekly_sales,
        "monthly_sales": monthly_sales,
    }


# ---------------------------------------------------------------------------
# Payment mix (cash vs credit)
# ---------------------------------------------------------------------------


def calculate_payment_mix(
    date_filter: str = "12m",
    company: str | None = None,
) -> dict[str, Any]:
    """Cash (outstanding == 0) vs Credit (outstanding > 0) by period.

    `outstanding_amount` and `grand_total` are computed via two
    conditional aggregate measures in one query; the bucket split is
    built in SQL, not in Python.
    """
    si = company_filter(t("Sales Invoice"), company or default_company()).filter(
        t("Sales Invoice").docstatus == 1
    ).filter(t("Sales Invoice").is_return == 0)
    start, _ = parse_date_filter(date_filter)
    if start is not None:
        si = si.filter(si.posting_date >= start.date())

    is_cash = si.outstanding_amount == 0
    overall_df = si.aggregate(
        total=si.grand_total.sum(),
        cash_total=ibis.ifelse(is_cash, si.grand_total, 0).sum(),
        credit_total=ibis.ifelse(is_cash, 0, si.grand_total).sum(),
    ).execute().iloc[0]
    total = float(overall_df["total"] or 0)
    cash_total = float(overall_df["cash_total"] or 0)
    credit_total = float(overall_df["credit_total"] or 0)

    cash_ratio = round(cash_total / total * 100, 1) if total > 0 else 0
    credit_ratio = round(credit_total / total * 100, 1) if total > 0 else 0

    # Daily mix (last 30 days). Each day gets its own cash/credit row.
    daily_cutoff = (datetime.now() - timedelta(days=30)).date()
    si_daily = si.filter(si.posting_date >= daily_cutoff)
    is_cash_daily = si_daily.outstanding_amount == 0
    daily_df = (
        si_daily.group_by(si_daily.posting_date)
        .aggregate(
            Cash=ibis.ifelse(is_cash_daily, si_daily.grand_total, 0).sum(),
            Credit=ibis.ifelse(is_cash_daily, 0, si_daily.grand_total).sum(),
        )
        .order_by("posting_date")
        .execute()
    )
    daily_mix: list[dict[str, Any]] = []
    for _, r in daily_df.iterrows():
        cash = float(r["Cash"] or 0)
        credit = float(r["Credit"] or 0)
        total_d = cash + credit
        daily_mix.append(
            {
                "sale_date": str(r["posting_date"]),
                "Cash": cash,
                "Credit": credit,
                "total": total_d,
                "cash_pct": round(cash / total_d * 100, 1) if total_d > 0 else 0,
            }
        )

    # Monthly mix.
    si_monthly = si.mutate(period=si.posting_date.strftime("%Y-%m"))
    is_cash_monthly = si_monthly.outstanding_amount == 0
    monthly_df = (
        si_monthly.group_by("period")
        .aggregate(
            Cash=ibis.ifelse(is_cash_monthly, si_monthly.grand_total, 0).sum(),
            Credit=ibis.ifelse(is_cash_monthly, 0, si_monthly.grand_total).sum(),
        )
        .order_by("period")
        .execute()
    )
    monthly_mix: list[dict[str, Any]] = []
    for _, r in monthly_df.iterrows():
        cash = float(r["Cash"] or 0)
        credit = float(r["Credit"] or 0)
        total_p = cash + credit
        monthly_mix.append(
            {
                "period": r["period"],
                "Cash": cash,
                "Credit": credit,
                "total": total_p,
                "cash_pct": round(cash / total_p * 100, 1) if total_p > 0 else 0,
            }
        )
    # Today's numbers.
    today = datetime.now().date().isoformat()
    today_total = next((d["total"] for d in daily_mix if d["sale_date"] == today), 0)
    today_cash = next((d["Cash"] for d in daily_mix if d["sale_date"] == today), 0)
    today_cash_pct = round(today_cash / today_total * 100, 1) if today_total > 0 else 0

    return {
        "cash_ratio": cash_ratio,
        "credit_ratio": credit_ratio,
        "cash_total": cash_total,
        "credit_total": credit_total,
        "today_cash_pct": today_cash_pct,
        "today_total": today_total,
        "daily_mix": daily_mix,
        "monthly_mix": monthly_mix,
    }


# ---------------------------------------------------------------------------
# Sales rep performance
# ---------------------------------------------------------------------------


def analyze_sales_reps(
    date_filter: str = "12m",
    company: str | None = None,
) -> dict[str, Any]:
    """Per-owner (the Sales Invoice's `owner` field) performance.

    The previous implementation used a LEFT JOIN to `tabUser` to get a
    friendly name. We do the same in one query.
    """
    si = company_filter(t("Sales Invoice"), company or default_company()).filter(
        t("Sales Invoice").docstatus == 1
    )
    start, _ = parse_date_filter(date_filter)
    if start is not None:
        si = si.filter(si.posting_date >= start.date())

    # Project to only the columns we need to avoid name collisions.
    si_p = si.select(
        sales_person=si.owner,
        invoice=si["name"],
        customer=si.customer,
        posting_date=si.posting_date,
        grand_total=si.grand_total,
    )
    user_p = t("User").select(
        user_name=t("User")["name"],
        full_name=t("User").full_name,
    )

    expr = (
        si_p.left_join(user_p, user_p.user_name == si_p.sales_person)
        .group_by(si_p.sales_person, user_p.full_name)
        .aggregate(
            total_revenue=si_p.grand_total.sum(),
            total_orders=si_p.invoice.nunique(),
            unique_customers=si_p.customer.nunique(),
            first_sale=si_p.posting_date.min(),
            last_sale=si_p.posting_date.max(),
        )
        .order_by(ibis.desc("total_revenue"))
    )
    df = expr.execute()
    if df.empty:
        return {
            "reps": [],
            "top_performer": None,
            "total_reps": 0,
            "total_team_revenue": 0,
        }

    reps: list[dict[str, Any]] = []
    for idx, (_, r) in enumerate(df.iterrows(), start=1):
        email = str(r["sales_person"])
        name = (str(r["full_name"]) if r["full_name"] else email) if "full_name" in df.columns else email
        total_rev = float(r["total_revenue"] or 0)
        total_orders = int(r["total_orders"] or 0)
        unique = int(r["unique_customers"] or 0)
        aov = round(total_rev / total_orders, 2) if total_orders else 0
        reps.append(
            {
                "sales_person": email,
                "sales_person_name": name,
                "rank": idx,
                "total_revenue": total_rev,
                "total_orders": total_orders,
                "unique_customers": unique,
                "avg_order_value": aov,
                "total_incentives": 0,
                "trend": [],
            }
        )

    total_team_revenue = sum(r["total_revenue"] for r in reps)
    return {
        "reps": reps,
        "top_performer": reps[0] if reps else None,
        "total_reps": len(reps),
        "total_team_revenue": round(total_team_revenue, 2),
    }


# ---------------------------------------------------------------------------
# MoM and YoY comparisons
# ---------------------------------------------------------------------------


def calculate_comparisons(
    date_filter: str = "12m",
    company: str | None = None,
) -> dict[str, Any]:
    """Month-over-month and year-over-year revenue and AOV comparison.

    The current month is compared against:
      * the same day-of-month slice of the previous month (avoids
        reporting -98% growth on day 6 against a 31-day prior month)
      * the same day-of-month slice of the same month last year
    """
    si = company_filter(t("Sales Invoice"), company or default_company()).filter(
        t("Sales Invoice").docstatus == 1
    ).filter(t("Sales Invoice").is_return == 0)
    start, _ = parse_date_filter(date_filter)
    if start is not None:
        si = si.filter(si.posting_date >= start.date())

    today = datetime.now().date()
    current_month_start = today.replace(day=1)
    last_month_final_day = current_month_start - timedelta(days=1)
    last_month_start = last_month_final_day.replace(day=1)
    last_month_end = min(
        last_month_start + timedelta(days=today.day - 1),
        last_month_final_day,
    )
    last_year_month_start = current_month_start.replace(year=current_month_start.year - 1)
    last_year_month_end = last_year_month_start.replace(day=min(today.day, 28))

    def _slice(start_d, end_d):
        si_period = si.filter(si.posting_date.between(start_d, end_d))
        return si_period.aggregate(
            revenue=si_period.grand_total.sum(),
            transactions=si_period.count(),
        ).execute().iloc[0]

    cur = _slice(current_month_start, today)
    last = _slice(last_month_start, last_month_end)
    last_year = _slice(last_year_month_start, last_year_month_end)

    current_revenue = float(cur["revenue"] or 0)
    last_month_revenue = float(last["revenue"] or 0)
    last_year_revenue = float(last_year["revenue"] or 0)
    current_txns = int(cur["transactions"] or 0)
    last_txns = int(last["transactions"] or 0)
    last_year_txns = int(last_year["transactions"] or 0)
    current_aov = round(current_revenue / current_txns, 2) if current_txns else 0
    last_aov = round(last_month_revenue / last_txns, 2) if last_txns else 0
    last_year_aov = round(last_year_revenue / last_year_txns, 2) if last_year_txns else 0

    mom_growth = round((current_revenue - last_month_revenue) / last_month_revenue * 100, 1) if last_month_revenue > 0 else 0
    yoy_growth = round((current_revenue - last_year_revenue) / last_year_revenue * 100, 1) if last_year_revenue > 0 else 0
    mom_txn_growth = round((current_txns - last_txns) / last_txns * 100, 1) if last_txns > 0 else 0
    yoy_txn_growth = round((current_txns - last_year_txns) / last_year_txns * 100, 1) if last_year_txns > 0 else 0

    # Monthly trend (last 13 months for MoM).
    si_monthly = si.mutate(period=si.posting_date.strftime("%Y-%m"))
    monthly_df = (
        si_monthly.group_by("period")
        .aggregate(revenue=si_monthly.grand_total.sum())
        .order_by("period")
        .execute()
    )
    monthly_trend: list[dict[str, Any]] = []
    rows = list(monthly_df.to_dict(orient="records"))
    for i, r in enumerate(rows):
        if i == 0:
            mom_pct = 0
        else:
            prev = float(rows[i - 1]["revenue"] or 0)
            curr = float(r["revenue"] or 0)
            mom_pct = round((curr - prev) / prev * 100, 1) if prev > 0 else 0
        monthly_trend.append(
            {
                "period": r["period"],
                "revenue": round(float(r["revenue"] or 0), 2),
                "mom_pct": mom_pct,
            }
        )
    # Last 12 months.
    monthly_trend = monthly_trend[-12:]

    return {
        "current_month": {
            "revenue": current_revenue,
            "transactions": current_txns,
            "aov": current_aov,
            "period": current_month_start.strftime("%Y-%m"),
        },
        "last_month": {
            "revenue": last_month_revenue,
            "transactions": last_txns,
            "aov": last_aov,
            "period": last_month_start.strftime("%Y-%m"),
        },
        "last_year_same_month": {
            "revenue": last_year_revenue,
            "transactions": last_year_txns,
            "aov": last_year_aov,
            "period": last_year_month_start.strftime("%Y-%m"),
        },
        "mom_growth": mom_growth,
        "yoy_growth": yoy_growth,
        "mom_txn_growth": mom_txn_growth,
        "yoy_txn_growth": yoy_txn_growth,
        "monthly_trend": monthly_trend,
    }


# ---------------------------------------------------------------------------
# Dimensional breakdown
# ---------------------------------------------------------------------------


def analyze_by_dimensions(
    date_filter: str = "12m",
    company: str | None = None,
) -> dict[str, Any]:
    """Revenue by customer_group, territory, and product_group."""
    si = company_filter(t("Sales Invoice"), company or default_company()).filter(
        t("Sales Invoice").docstatus == 1
    ).filter(t("Sales Invoice").is_return == 0)
    start, _ = parse_date_filter(date_filter)
    if start is not None:
        si = si.filter(si.posting_date >= start.date())

    # By customer_group / territory -- header fields, no fan-out.
    dim_df = (
        si.group_by([si.customer_group.fill_null("Uncategorized").name("customer_group"),
                     si.territory.fill_null("Unassigned").name("territory")])
        .aggregate(
            revenue=si.grand_total.sum(),
            transactions=si.count(),
            unique_customers=si.customer.nunique(),
        )
        .order_by(ibis.desc("revenue"))
        .execute()
    )
    if dim_df.empty:
        return {
            "by_product_group": [],
            "by_customer_segment": [],
            "by_territory": [],
            "total_revenue": 0,
        }

    total_revenue = float(dim_df["revenue"].sum())
    by_segment_map: dict[str, dict[str, Any]] = {}
    by_territory_map: dict[str, dict[str, Any]] = {}
    for _, r in dim_df.iterrows():
        seg = str(r["customer_group"])
        terr = str(r["territory"])
        rev = float(r["revenue"] or 0)
        txns = int(r["transactions"] or 0)
        uniq = int(r["unique_customers"] or 0)
        by_segment_map[seg] = by_segment_map.get(seg, {"revenue": 0, "transactions": 0, "customers": 0})
        by_segment_map[seg]["revenue"] += rev
        by_segment_map[seg]["transactions"] += txns
        by_segment_map[seg]["customers"] = max(by_segment_map[seg]["customers"], uniq)

        by_territory_map[terr] = by_territory_map.get(terr, {"revenue": 0, "transactions": 0, "customers": 0})
        by_territory_map[terr]["revenue"] += rev
        by_territory_map[terr]["transactions"] += txns
        by_territory_map[terr]["customers"] = max(by_territory_map[terr]["customers"], uniq)

    by_segment = [
        {
            "customer_group": k,
            "revenue": round(v["revenue"], 2),
            "transactions": v["transactions"],
            "customers": v["customers"],
            "pct": round(v["revenue"] / total_revenue * 100, 1) if total_revenue > 0 else 0,
        }
        for k, v in sorted(by_segment_map.items(), key=lambda x: x[1]["revenue"], reverse=True)
    ]
    by_territory = [
        {
            "territory": k,
            "revenue": round(v["revenue"], 2),
            "transactions": v["transactions"],
            "customers": v["customers"],
            "pct": round(v["revenue"] / total_revenue * 100, 1) if total_revenue > 0 else 0,
        }
        for k, v in sorted(by_territory_map.items(), key=lambda x: x[1]["revenue"], reverse=True)
    ]

    # By product_group -- from the item-level join, allocating invoice
    # total to lines in proportion to their net amount (no double-count).
    sii = t("Sales Invoice Item")
    base = si.inner_join(sii, sii.parent == si.name)
    if start is not None:
        base = base.filter(base.posting_date >= start.date())
    allocated = ibis.ifelse(
        si.base_net_total == 0,
        sii.base_net_amount,
        sii.base_net_amount / si.base_net_total * si.base_grand_total,
    )
    pg_df = (
        base.filter(sii.item_group.notnull())
        .filter(sii.item_group != ibis.literal(""))
        .group_by(sii.item_group)
        .aggregate(
            revenue=allocated.sum(),
            qty_sold=sii.qty.sum(),
            transactions=si.name.nunique(),
        )
        .order_by(ibis.desc("revenue"))
        .execute()
    )
    pg_total = float(pg_df["revenue"].sum()) if not pg_df.empty else 0
    by_product_group = []
    for _, r in pg_df.iterrows():
        rev = float(r["revenue"] or 0)
        by_product_group.append(
            {
                "item_group": str(r["item_group"]),
                "revenue": round(rev, 2),
                "qty_sold": float(r["qty_sold"] or 0),
                "transactions": int(r["transactions"] or 0),
                "pct": round(rev / pg_total * 100, 1) if pg_total > 0 else 0,
            }
        )
    by_product_group = by_product_group[:20]

    return {
        "by_product_group": by_product_group,
        "by_customer_segment": by_segment,
        "by_territory": by_territory,
        "total_revenue": total_revenue,
    }


# ---------------------------------------------------------------------------
# Margin analysis
# ---------------------------------------------------------------------------


def analyze_margins(
    date_filter: str = "12m",
    company: str | None = None,
) -> dict[str, Any]:
    """Per-product-group and per-item gross margin analysis.

    Gross profit per line = `net_amount - qty * incoming_rate`. A line
    with a NULL `incoming_rate` is treated as zero cost (conservative
    on the margin percentage).
    """
    si = company_filter(t("Sales Invoice"), company or default_company()).filter(
        t("Sales Invoice").docstatus == 1
    ).filter(t("Sales Invoice").is_return == 0)
    sii = t("Sales Invoice Item")
    start, _ = parse_date_filter(date_filter)
    if start is not None:
        si = si.filter(si.posting_date >= start.date())

    line_cost = (sii.qty * sii.incoming_rate.fill_null(0)).sum()
    line_profit = sii.net_amount.sum() - line_cost

    base = si.inner_join(sii, sii.parent == si.name)

    overall_df = base.aggregate(
        total_revenue=sii.net_amount.sum(),
        total_profit=line_profit,
    ).execute().iloc[0]
    total_revenue = float(overall_df["total_revenue"] or 0)
    total_profit = float(overall_df["total_profit"] or 0)
    overall_margin = round(total_profit / total_revenue * 100, 1) if total_revenue > 0 else 0

    pg_df = (
        base.filter(sii.item_group.notnull())
        .group_by(sii.item_group)
        .aggregate(
            revenue=sii.net_amount.sum(),
            gross_profit=line_profit,
            qty_sold=sii.qty.sum(),
            unique_items=sii.item_code.nunique(),
        )
        .order_by(ibis.desc("revenue"))
        .execute()
    )
    by_product_group: list[dict[str, Any]] = []
    for _, r in pg_df.iterrows():
        rev = float(r["revenue"] or 0)
        profit = float(r["gross_profit"] or 0)
        by_product_group.append(
            {
                "item_group": str(r["item_group"]),
                "revenue": round(rev, 2),
                "gross_profit": round(profit, 2),
                "qty_sold": float(r["qty_sold"] or 0),
                "unique_items": int(r["unique_items"] or 0),
                "margin_pct": round(profit / rev * 100, 1) if rev > 0 else 0,
            }
        )

    # Per-item -- top 10 by margin % and bottom 10 by margin % (over items
    # with revenue above the median, so we do not list a single 1-unit
    # item at -100% or +100% margin).
    item_df = (
        base.filter(sii.item_code.notnull())
        .group_by([sii.item_code, sii.item_name, sii.item_group])
        .aggregate(
            revenue=sii.net_amount.sum(),
            gross_profit=line_profit,
            qty_sold=sii.qty.sum(),
        )
        .order_by(ibis.desc("revenue"))
        .limit(500)
        .execute()
    )
    if not item_df.empty:
        # MariaDB SUM() returns Decimal; pandas .quantile()/.std() use numpy
        # interpolation internals that raise TypeError when mixed with float.
        # Cast once, up front.
        item_df["revenue"] = item_df["revenue"].astype(float)
        item_df["gross_profit"] = item_df["gross_profit"].astype(float)
        threshold = float(item_df["revenue"].quantile(0.5))
        significant = item_df[item_df["revenue"] >= threshold].copy()
        significant["margin_pct"] = (significant["gross_profit"] / significant["revenue"] * 100).fillna(0).round(1)
        top_margin = significant.nlargest(10, "margin_pct")
        low_margin = significant[significant["revenue"] > 0].nsmallest(10, "margin_pct")
        top_margin_items = [
            {
                "item_code": str(r["item_code"]),
                "item_name": str(r["item_name"]),
                "item_group": str(r["item_group"]),
                "revenue": round(float(r["revenue"] or 0), 2),
                "gross_profit": round(float(r["gross_profit"] or 0), 2),
                "qty_sold": float(r["qty_sold"] or 0),
                "margin_pct": float(r["margin_pct"]),
            }
            for _, r in top_margin.iterrows()
        ]
        low_margin_items = [
            {
                "item_code": str(r["item_code"]),
                "item_name": str(r["item_name"]),
                "item_group": str(r["item_group"]),
                "revenue": round(float(r["revenue"] or 0), 2),
                "gross_profit": round(float(r["gross_profit"] or 0), 2),
                "qty_sold": float(r["qty_sold"] or 0),
                "margin_pct": float(r["margin_pct"]),
            }
            for _, r in low_margin.iterrows()
        ]
    else:
        top_margin_items = []
        low_margin_items = []

    # Margin trend (last 12 months).
    trend_df = (
        base.mutate(period=base.posting_date.strftime("%Y-%m"))
        .group_by("period")
        .aggregate(
            revenue=sii.net_amount.sum(),
            gross_profit=line_profit,
        )
        .order_by("period")
        .execute()
    )
    margin_trend: list[dict[str, Any]] = []
    for _, r in trend_df.iterrows():
        rev = float(r["revenue"] or 0)
        profit = float(r["gross_profit"] or 0)
        margin_trend.append(
            {
                "period": r["period"],
                "revenue": round(rev, 2),
                "gross_profit": round(profit, 2),
                "margin_pct": round(profit / rev * 100, 1) if rev > 0 else 0,
            }
        )
    margin_trend = margin_trend[-12:]

    return {
        "overall_margin": overall_margin,
        "total_revenue": round(total_revenue, 2),
        "total_profit": round(total_profit, 2),
        "by_product_group": by_product_group,
        "top_margin_items": top_margin_items,
        "low_margin_items": low_margin_items,
        "margin_trend": margin_trend,
    }


# ---------------------------------------------------------------------------
# Fulfillment / DSO
# ---------------------------------------------------------------------------


def analyze_fulfillment(
    date_filter: str = "12m",
    company: str | None = None,
) -> dict[str, Any]:
    """Order fulfillment rate and Days Sales Outstanding.

    The previous version used a raw `tabSales Order` query. Same here,
    in Ibis terms.
    """
    so = company_filter(t("Sales Order"), company or default_company()).filter(
        t("Sales Order").docstatus == 1
    )
    start, _ = parse_date_filter(date_filter)
    if start is not None:
        so = so.filter(so.transaction_date >= start.date())

    by_status_df = (
        so.mutate(
            fulfillment_status=ibis.ifelse(
                so.per_delivered >= 100,
                ibis.literal("Fulfilled"),
                ibis.ifelse(
                    so.per_delivered > 0,
                    ibis.literal("Partial"),
                    ibis.literal("Pending"),
                ),
            )
        )
        .group_by("fulfillment_status")
        .aggregate(
            count=so.name.count(),
            value=so.grand_total.sum(),
        )
        .execute()
    )
    total_orders = int(by_status_df["count"].sum()) if not by_status_df.empty else 0
    fulfilled = 0
    partial = 0
    pending = 0
    by_status: list[dict[str, Any]] = []
    for _, r in by_status_df.iterrows():
        cnt = int(r["count"] or 0)
        by_status.append(
            {
                "status": str(r["fulfillment_status"]),
                "count": cnt,
                "value": float(r["value"] or 0),
            }
        )
        if r["fulfillment_status"] == "Fulfilled":
            fulfilled = cnt
        elif r["fulfillment_status"] == "Partial":
            partial = cnt
        elif r["fulfillment_status"] == "Pending":
            pending = cnt
    fulfillment_rate = round(fulfilled / total_orders * 100, 1) if total_orders > 0 else 0

    # Backlog value: outstanding partial/pending grand_total * (1 - per_delivered/100)
    backlog_df = (
        so.filter(so.per_delivered < 100)
        .select(
            grand_total=so.grand_total,
            per_delivered=so.per_delivered.fill_null(0),
        )
        .execute()
    )
    if len(backlog_df) > 0:
        backlog_value = float(
            (backlog_df["grand_total"] * (1 - backlog_df["per_delivered"] / 100)).sum()
        )
    else:
        backlog_value = 0.0

    # DSO = total_receivables / avg_daily_sales (last 90 days).
    si = company_filter(t("Sales Invoice"), company or default_company()).filter(
        t("Sales Invoice").docstatus == 1
    ).filter(t("Sales Invoice").is_return == 0)
    cutoff_90 = (datetime.now() - timedelta(days=90)).date()
    receivables_df = si.aggregate(total=si.outstanding_amount.sum()).execute().iloc[0]
    total_receivables = float(receivables_df["total"] or 0)
    last_90_df = (
        si.filter(si.posting_date >= cutoff_90)
        .aggregate(
            total=si.grand_total.sum(),
            days=ibis.literal(90),
        )
        .execute()
    )
    last_90_total = float(last_90_df["total"].iloc[0] or 0) if not last_90_df.empty else 0
    avg_daily_sales = last_90_total / 90 if last_90_total > 0 else 0
    dso = round(total_receivables / avg_daily_sales, 1) if avg_daily_sales > 0 else 0

    return {
        "fulfillment_rate": fulfillment_rate,
        "backlog_value": backlog_value,
        "dso": dso,
        "by_status": by_status,
        "total_orders": total_orders,
        "fulfilled": fulfilled,
        "partial": partial,
        "pending": pending,
        "total_receivables": round(total_receivables, 2),
        "avg_daily_sales": round(avg_daily_sales, 2),
    }


# ---------------------------------------------------------------------------
# Aggregate payload -- the full `sales_intelligence` response
# ---------------------------------------------------------------------------


def aggregate_forecasts() -> dict[str, Any]:
    """Sales forecast + demand forecast / reorder alerts, computed fresh.

    No cache. Every call rebuilds the sales forecast (a single SQL
    aggregate + a small Python trend fit) and the demand forecast (the
    canonical `DemandForecasting.train()` from inventory_intelligence).
    Both are cheap enough to run inline; the dashboard already shows a
    "Refresh" button if the user wants fresher numbers.
    """
    sales = get_sales_forecast(periods=30)
    demand_payload = DemandForecasting().train()
    demand_alerts = demand_payload.get("reorder_alerts", [])

    return {
        "sales_forecast": {
            "forecast": sales.get("forecast", []),
            "forecast_summary": sales.get("forecast_summary", {}),
            "method": sales.get("method", "linear_trend"),
            "metrics": sales.get("metrics", {}),
            "data_range": sales.get("data_range", {}),
        },
        "demand_forecast": {
            "summary": {
                "total_items_analyzed": demand_payload.get("total_items_analyzed", 0),
                "reorder_now_count": demand_payload.get("reorder_now_count", 0),
                "monitor_count": demand_payload.get("monitor_count", 0),
                "adequate_count": demand_payload.get("adequate_count", 0),
            },
            "reorder_alerts": demand_alerts[:20],
            "total_items": len(demand_alerts),
        },
    }


def run_sales_intelligence(
    date_filter: str = "12m",
    company: str | None = None,
) -> dict[str, Any]:
    """Run the full sales intelligence payload synchronously."""
    revenue_metrics = calculate_revenue_metrics(date_filter, company)
    payment_mix = calculate_payment_mix(date_filter, company)
    sales_reps = analyze_sales_reps(date_filter, company)
    comparisons = calculate_comparisons(date_filter, company)
    dimensions = analyze_by_dimensions(date_filter, company)
    margins = analyze_margins(date_filter, company)
    fulfillment = analyze_fulfillment(date_filter, company)
    forecasts = aggregate_forecasts()

    summary = {
        "total_revenue": revenue_metrics["total_revenue"],
        "total_transactions": revenue_metrics["total_transactions"],
        "avg_order_value": revenue_metrics["avg_order_value"],
        "unique_customers": revenue_metrics["unique_customers"],
        "cash_ratio": payment_mix["cash_ratio"],
        "credit_ratio": payment_mix["credit_ratio"],
        "mom_growth": comparisons["mom_growth"],
        "yoy_growth": comparisons["yoy_growth"],
        "overall_margin": margins["overall_margin"],
        "fulfillment_rate": fulfillment["fulfillment_rate"],
        "dso": fulfillment["dso"],
        "total_sales_reps": sales_reps["total_reps"],
    }

    return {
        "status": "success",
        "analysis_date": datetime.now().isoformat(),
        "summary": summary,
        "revenue_metrics": revenue_metrics,
        "payment_mix": payment_mix,
        "sales_reps": sales_reps,
        "comparisons": comparisons,
        "dimensions": dimensions,
        "margins": margins,
        "fulfillment": fulfillment,
        "forecasts": forecasts,
    }


def get_sales_intelligence(
    date_filter: str = "12m",
    company: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible: every call computes fresh (no cache)."""
    return run_sales_intelligence(date_filter=date_filter, company=company)
