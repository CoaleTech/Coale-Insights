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

from insights.api.ml.ibis_source import company_filter, default_company, dn_cost, line_cogs, t
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
    si_weekly = si.mutate(year_week=si.posting_date.strftime("%x-W%v")).filter(
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

    # Line-level cost of sales and gross profit per period. Cost is COGS from
    # the linked Delivery Note (sii.dn_detail) when the Sales Invoice ran with
    # update_stock=0, else the reposted SII incoming_rate -- see line_cogs.
    # GP = sum(net_amount) - cost. net_amount is pre-tax, so gross margin % is
    # on net sales (the Margins/rankings convention), not the tax-inclusive
    # grand_total shown in the Revenue row.
    sii = t("Sales Invoice Item")
    dn = dn_cost()
    line_cost = line_cogs(sii, dn.dn_rate).sum()
    line_profit = sii.net_amount.sum() - line_cost

    def _merge_gp(series: list[dict[str, Any]], gp_map: dict[str, tuple[float, float]], key: str) -> None:
        for row in series:
            cost, gp = gp_map.get(row[key], (0.0, 0.0))
            row["cost_of_sales"] = round(cost, 2)
            row["gross_profit"] = round(gp, 2)

    base_daily = si_daily.inner_join(sii, sii.parent == si_daily.name).left_join(dn, sii.dn_detail == dn.dn_name)
    gp_daily = {
        str(r["posting_date"]): (float(r["cost"] or 0), float(r["gross_profit"] or 0))
        for _, r in base_daily.group_by(base_daily.posting_date)
        .aggregate(cost=line_cost, gross_profit=line_profit)
        .execute()
        .iterrows()
    }
    _merge_gp(daily_sales, gp_daily, "date")

    base_weekly = si_weekly.inner_join(sii, sii.parent == si_weekly.name).left_join(dn, sii.dn_detail == dn.dn_name)
    gp_weekly = {
        r["year_week"]: (float(r["cost"] or 0), float(r["gross_profit"] or 0))
        for _, r in base_weekly.group_by(base_weekly.year_week)
        .aggregate(cost=line_cost, gross_profit=line_profit)
        .execute()
        .iterrows()
    }
    _merge_gp(weekly_sales, gp_weekly, "year_week")

    base_monthly = si_monthly.inner_join(sii, sii.parent == si_monthly.name).left_join(dn, sii.dn_detail == dn.dn_name)
    gp_monthly = {
        r["period"]: (float(r["cost"] or 0), float(r["gross_profit"] or 0))
        for _, r in base_monthly.group_by(base_monthly.period)
        .aggregate(cost=line_cost, gross_profit=line_profit)
        .execute()
        .iterrows()
    }
    _merge_gp(monthly_sales, gp_monthly, "period")

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
        pd = r["posting_date"]
        sale_date = pd.date().isoformat() if hasattr(pd, "date") else str(pd)[:10]
        daily_mix.append(
            {
                "sale_date": sale_date,
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
    """Per-sales-person performance via the `Sales Team` child table.

    ERPNext attributes a Sales Invoice to whoever actually sold it through
    the `Sales Team` child table: `allocated_amount` is that rep's share of
    the invoice (a sale can be split across reps), `incentives` is a real
    per-rep figure. The previous version grouped by `Sales Invoice.owner`
    -- the Frappe document *creator*, e.g. an accounts/billing mailbox that
    keys invoices into the system -- a different person from whoever sold
    the order. On this site that made "billing@jkmchemtrade.com" (1,452
    invoices) the #1 "sales rep" and never surfaced any of the 6 real
    Sales Person records (Milan Mavani, Khushboo, Roja, ...) at all.
    On this site the `Sales Team` child table itself is unreliable at the
    row level: 2,220 of 2,229 invoices in a trailing-12m sample have an
    `allocated_amount` sum that does not reconcile to the invoice's
    `grand_total` (stale carry-over amounts on credit notes, partial/
    rounded splits, zeroed rows) -- so summing it, while still the best
    available per-rep signal, understates true revenue by ~14%
    (₹157.4M allocated vs ₹182.1M invoiced in that sample). Rather than
    guess a reallocation, `unattributed_revenue` reports the shortfall
    directly, mirroring the `uncosted_revenue` transparency pattern in
    `analyze_margins` below.
    """
    si = company_filter(t("Sales Invoice"), company or default_company()).filter(
        t("Sales Invoice").docstatus == 1
    ).filter(t("Sales Invoice").is_return == 0)
    start, _ = parse_date_filter(date_filter)
    if start is not None:
        si = si.filter(si.posting_date >= start.date())

    total_invoice_revenue = float(si.grand_total.sum().execute() or 0)

    si_p = si.select(invoice=si["name"], customer=si.customer)

    team = t("Sales Team")
    team_p = team.filter(team.parenttype == "Sales Invoice").select(
        parent=team.parent,
        sales_person=team.sales_person,
        allocated_amount=team.allocated_amount.fill_null(0),
        incentives=team.incentives.fill_null(0),
    )

    expr = (
        si_p.inner_join(team_p, team_p.parent == si_p.invoice)
        .group_by(team_p.sales_person)
        .aggregate(
            total_revenue=team_p.allocated_amount.sum(),
            total_incentives=team_p.incentives.sum(),
            total_orders=si_p.invoice.nunique(),
            unique_customers=si_p.customer.nunique(),
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
            "unattributed_revenue": round(total_invoice_revenue, 2),
            "unattributed_revenue_pct": 100.0 if total_invoice_revenue > 0 else 0,
        }

    # Per-rep gross profit, allocated to each sales person by their share of
    # the invoice (allocated_amount / grand_total), so margin reconciles with
    # the allocated revenue shown. Line-level GP = net_amount - COGS, cost from
    # the linked Delivery Note or reposted SII incoming_rate (see line_cogs).
    sii = t("Sales Invoice Item")
    dn = dn_cost()
    inv_gp_df = (
        si.inner_join(sii, sii.parent == si.name)
        .left_join(dn, sii.dn_detail == dn.dn_name)
        .group_by(invoice=si.name)
        .aggregate(
            invoice_gp=sii.net_amount.sum() - line_cogs(sii, dn.dn_rate).sum(),
            grand_total=si.grand_total.max(),
        )
        .execute()
    )
    team_df = team_p.execute()
    gp_by_rep: dict[str, float] = {}
    if not inv_gp_df.empty and not team_df.empty:
        m = team_df.merge(inv_gp_df, left_on="parent", right_on="invoice", how="inner")
        gt = m["grand_total"].astype(float)
        frac = (m["allocated_amount"].astype(float) / gt).where(gt != 0, 0.0)
        m["rep_gp"] = m["invoice_gp"].astype(float).fillna(0.0) * frac
        gp_by_rep = m.groupby("sales_person")["rep_gp"].sum().to_dict()

    reps: list[dict[str, Any]] = []
    for idx, (_, r) in enumerate(df.iterrows(), start=1):
        name = str(r["sales_person"])
        total_rev = float(r["total_revenue"] or 0)
        total_orders = int(r["total_orders"] or 0)
        unique = int(r["unique_customers"] or 0)
        aov = round(total_rev / total_orders, 2) if total_orders else 0
        gp = float(gp_by_rep.get(name, 0.0))
        margin = round(gp / total_rev * 100, 1) if total_rev else 0
        reps.append(
            {
                "sales_person": name,
                "sales_person_name": name,
                "rank": idx,
                "total_revenue": total_rev,
                "total_orders": total_orders,
                "unique_customers": unique,
                "avg_order_value": aov,
                "total_incentives": float(r["total_incentives"] or 0),
                "gross_profit": round(gp, 2),
                "margin_pct": margin,
                "trend": [],
            }
        )

    total_team_revenue = sum(r["total_revenue"] for r in reps)
    unattributed = max(0.0, total_invoice_revenue - total_team_revenue)
    return {
        "reps": reps,
        "top_performer": reps[0] if reps else None,
        "total_reps": len(reps),
        "total_team_revenue": round(total_team_revenue, 2),
        "unattributed_revenue": round(unattributed, 2),
        "unattributed_revenue_pct": (
            round(unattributed / total_invoice_revenue * 100, 1) if total_invoice_revenue > 0 else 0
        ),
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

    The YoY slice is by definition outside the user's date filter
    window (e.g. a 12m filter ends ~today-360d, but the same month
    last year starts ~today-1y). Applying the filter to it forces
    `last_year_revenue = 0` and `yoy_growth = 0` even when there is
    real data -- previously the dashboard silently reported "0% YoY
    growth" whenever the 12m date filter was selected. The MoM slice
    is inside the window and the filter is still applied to it.
    """
    # Base set (submitted, non-return, company-scoped) reused for both
    # slices below and for anchoring the "current" period.
    base = company_filter(t("Sales Invoice"), company or default_company()).filter(
        t("Sales Invoice").docstatus == 1
    ).filter(t("Sales Invoice").is_return == 0)

    # Anchor "current" to the latest month that actually has sales, not the
    # calendar month. A no-op when the ledger is current (max posting date is
    # in this month); when data lags -- e.g. the last invoice is weeks old --
    # it stops the still-empty calendar month from reporting -100% MoM/YoY
    # growth against a fully-populated prior month.
    import pandas as pd
    today = datetime.now().date()
    max_posting = base.aggregate(m=base.posting_date.max()).execute().iloc[0]["m"]
    if max_posting is not None and not pd.isna(max_posting):
        anchor = pd.Timestamp(max_posting).date()
        if anchor < today:
            today = anchor

    current_month_start = today.replace(day=1)
    last_month_final_day = current_month_start - timedelta(days=1)
    last_month_start = last_month_final_day.replace(day=1)
    last_month_end = min(
        last_month_start + timedelta(days=today.day - 1),
        last_month_final_day,
    )
    last_year_month_start = current_month_start.replace(year=current_month_start.year - 1)
    last_year_month_end = last_year_month_start.replace(day=min(today.day, 28))

    # MoM slice: subject to the user's date filter (both endpoints
    # live inside the window).
    si = base
    start, _ = parse_date_filter(date_filter)
    if start is not None:
        si = si.filter(si.posting_date >= start.date())

    # YoY slice: skips the user's `date_filter` (which would push the cutoff
    # past the YoY window's start). Date filter is still respected for the
    # day-of-month comparison to stay apples-to-apples.
    si_yoy = base

    def _slice(si_base, start_d, end_d):
        si_period = si_base.filter(si_base.posting_date.between(start_d, end_d))
        return si_period.aggregate(
            revenue=si_period.grand_total.sum(),
            transactions=si_period.count(),
        ).execute().iloc[0]

    cur = _slice(si, current_month_start, today)
    last = _slice(si, last_month_start, last_month_end)
    last_year = _slice(si_yoy, last_year_month_start, last_year_month_end)

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
    #
    # We previously did ONE group-by on (customer_group, territory) and
    # combined rows in Python via `customers = max(per-combo count)`.
    # That was wrong: a segment that has 100 customers in Surat and 50
    # in Vadodara was reported as 100 (max), and a customer who buys in
    # both territories would have been double-counted in either count.
    # Two separate group-bys (one per dimension) give the true unique
    # customer count for each.
    seg_df = (
        si.group_by(si.customer_group.fill_null("Uncategorized").name("customer_group"))
        .aggregate(
            revenue=si.grand_total.sum(),
            transactions=si.count(),
            unique_customers=si.customer.nunique(),
        )
        .order_by(ibis.desc("revenue"))
        .execute()
    )
    terr_df = (
        si.group_by(si.territory.fill_null("Unassigned").name("territory"))
        .aggregate(
            revenue=si.grand_total.sum(),
            transactions=si.count(),
            unique_customers=si.customer.nunique(),
        )
        .order_by(ibis.desc("revenue"))
        .execute()
    )
    if seg_df.empty:
        return {
            "by_product_group": [],
            "by_customer_segment": [],
            "by_territory": [],
            "total_revenue": 0,
        }

    total_revenue = float(seg_df["revenue"].sum())
    by_segment = [
        {
            "customer_group": str(r["customer_group"]),
            "revenue": round(float(r["revenue"] or 0), 2),
            "transactions": int(r["transactions"] or 0),
            "customers": int(r["unique_customers"] or 0),
            "pct": round(float(r["revenue"] or 0) / total_revenue * 100, 1) if total_revenue > 0 else 0,
        }
        for _, r in seg_df.iterrows()
    ]
    by_segment.sort(key=lambda x: x["revenue"], reverse=True)

    by_territory = [
        {
            "territory": str(r["territory"]),
            "revenue": round(float(r["revenue"] or 0), 2),
            "transactions": int(r["transactions"] or 0),
            "customers": int(r["unique_customers"] or 0),
            "pct": round(float(r["revenue"] or 0) / total_revenue * 100, 1) if total_revenue > 0 else 0,
        }
        for _, r in terr_df.iterrows()
    ]
    by_territory.sort(key=lambda x: x["revenue"], reverse=True)

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

    Gross profit per line = `net_amount - line_cogs(...)`, where cost is the
    linked Delivery Note Item rate when the invoice ran with update_stock=0,
    else the reposted SII incoming_rate (see `line_cogs`). A line whose cost
    still resolves to zero is treated as uncosted, not a genuine full margin.
    """
    si = company_filter(t("Sales Invoice"), company or default_company()).filter(
        t("Sales Invoice").docstatus == 1
    ).filter(t("Sales Invoice").is_return == 0)
    sii = t("Sales Invoice Item")
    start, _ = parse_date_filter(date_filter)
    if start is not None:
        si = si.filter(si.posting_date >= start.date())

    dn = dn_cost()
    line_cost = line_cogs(sii, dn.dn_rate).sum()
    line_profit = sii.net_amount.sum() - line_cost

    base = si.inner_join(sii, sii.parent == si.name).left_join(
        dn, sii.dn_detail == dn.dn_name
    )

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
            # Revenue from lines where the cost could not be measured
            # (incoming_rate NULL or 0) -- surfaced per-group so a
            # 100% margin row visibly reflects a costing gap, not a
            # genuine 100% margin product. Mirrors the
            # `uncosted_items_excluded` accounting the per-item
            # leaderboard already does.
            uncosted_revenue=(
                ibis.ifelse(
                    (sii.incoming_rate.fill_null(0) == 0) & (dn.dn_rate.fill_null(0) == 0),
                    sii.net_amount,
                    0,
                ).sum()
            ),
        )
        .order_by(ibis.desc("revenue"))
        .execute()
    )
    by_product_group: list[dict[str, Any]] = []
    for _, r in pg_df.iterrows():
        rev = float(r["revenue"] or 0)
        profit = float(r["gross_profit"] or 0)
        uncosted_rev = float(r.get("uncosted_revenue") or 0)
        by_product_group.append(
            {
                "item_group": str(r["item_group"]),
                "revenue": round(rev, 2),
                "gross_profit": round(profit, 2),
                "qty_sold": float(r["qty_sold"] or 0),
                "unique_items": int(r["unique_items"] or 0),
                "margin_pct": round(profit / rev * 100, 1) if rev > 0 else 0,
                "uncosted_revenue": round(uncosted_rev, 2),
                "uncosted_revenue_pct": (
                    round(uncosted_rev / rev * 100, 1) if rev > 0 else 0
                ),
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
        # gross_profit >= revenue means the line carried no incoming_rate at
        # all (see the NULL-cost note above), not a genuine 100% margin. Left
        # in, these costing gaps swamp the "top margin" leaderboard instead
        # of real top performers, so they are excluded from that ranking
        # pool; the count/value is still reported so the gap stays visible.
        uncosted_mask = significant["gross_profit"] >= significant["revenue"]
        uncosted_items_excluded = int(uncosted_mask.sum())
        uncosted_revenue = round(float(significant.loc[uncosted_mask, "revenue"].sum()), 2)
        costed = significant[~uncosted_mask]
        top_margin = costed.nlargest(10, "margin_pct")
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
        uncosted_items_excluded = 0
        uncosted_revenue = 0.0

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
        "uncosted_items_excluded": uncosted_items_excluded,
        "uncosted_revenue": uncosted_revenue,
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
