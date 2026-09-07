# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Sales Intelligence Report -- pure ``frappe.qb`` aggregations, no pandas/numpy/ibis.

This replaces the ibis-backed `insights.ml.sales_intelligence` module. Every
aggregation is pushed to MariaDB via the PyPika ``frappe.qb`` query builder;
Python only formats the small result sets into the dict shape the Revenue
dashboard already consumes.
"""

from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Any

import frappe
from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import Coalesce, Count, DateFormat, Max, Min, NullIf, Sum



from insights.api.ml.utils import parse_date_filter


# ---------------------------------------------------------------------------
# Filter helpers -- return (PyPika criterion, params) instead of SQL fragments.
# Keeping them isolated lets every query below share identical semantics with
# the original ``frappe.db.sql`` implementation.
# ---------------------------------------------------------------------------


def _date_filter(date_filter: str, column=None):
    """Return (criterion, params) for ``column >= start_date``.

    ``column`` may be a string column name (resolved against the caller's
    DocType) or a PyPika field object. Returns ``(None, {})`` when no lower
    bound applies.
    """
    start, _ = parse_date_filter(date_filter)
    if start is None:
        return None, {}
    field = column if column is not None else DocType("Sales Invoice").posting_date
    return field >= start.date(), {"start_date": start.date()}


def _company_filter(company: str | None, table=None):
    """Return (criterion, params) for an optional ``company = ...`` filter."""
    if not company:
        return None, {}
    field = (table.company if table is not None else DocType("Sales Invoice").company)
    return field == company, {"company": company}


def _apply_common(q, date_filter: str, company: str | None, *, date_table=None, company_table=None):
    """Apply the standard docstatus / is_return / date / company filters."""
    table = date_table or company_table or DocType("Sales Invoice")
    q = q.where(table.docstatus == 1).where(table.is_return == 0)
    crit, params = _date_filter(date_filter, table.posting_date)
    if crit is not None:
        q = q.where(crit)
    crit, params_c = _company_filter(company, company_table or table)
    if crit is not None:
        q = q.where(crit)
    return q, {**params, **params_c}


def _headline(date_filter: str, company: str | None) -> dict[str, Any]:
    si = DocType("Sales Invoice")
    q = (
        frappe.qb.from_(si)
        .select(
            Coalesce(Sum(si.grand_total), 0).as_("total_revenue"),
            Count("*").as_("total_transactions"),
            Count(si.customer).distinct().as_("unique_customers"),
        )
    )
    q, _ = _apply_common(q, date_filter, company)
    row = q.run(as_dict=True)[0]
    total_revenue = float(row.total_revenue or 0)
    total_transactions = int(row.total_transactions or 0)
    unique_customers = int(row.unique_customers or 0)
    return {
        "total_revenue": total_revenue,
        "total_transactions": total_transactions,
        "unique_customers": unique_customers,
        "avg_order_value": round(total_revenue / total_transactions, 2) if total_transactions else 0,
    }


def _daily_sales(date_filter: str, company: str | None) -> list[dict[str, Any]]:
    si = DocType("Sales Invoice")
    daily_cutoff = (datetime.now() - timedelta(days=30)).date()
    q = (
        frappe.qb.from_(si)
        .select(
            si.posting_date,
            Coalesce(Sum(si.grand_total), 0).as_("revenue"),
            Count("*").as_("transactions"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .where(si.posting_date >= daily_cutoff)
        .groupby(si.posting_date)
        .orderby(si.posting_date)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        q = q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        q = q.where(crit)
    rows = q.run(as_dict=True)
    return [
        {
            "date": str(r.posting_date),
            "revenue": float(r.revenue or 0),
            "transactions": int(r.transactions or 0),
        }
        for r in rows
    ]


def _weekly_sales(date_filter: str, company: str | None) -> list[dict[str, Any]]:
    si = DocType("Sales Invoice")
    weekly_cutoff = (datetime.now() - timedelta(weeks=12)).date()
    year_week = DateFormat(si.posting_date, "%x-W%v").as_("year_week")
    q = (
        frappe.qb.from_(si)
        .select(
            year_week,
            Coalesce(Sum(si.grand_total), 0).as_("revenue"),
            Count("*").as_("transactions"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .where(si.posting_date >= weekly_cutoff)
        .groupby(year_week)
        .orderby(year_week)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        q = q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        q = q.where(crit)
    rows = q.run(as_dict=True)
    return [
        {
            "year_week": r.year_week,
            "revenue": float(r.revenue or 0),
            "transactions": int(r.transactions or 0),
        }
        for r in rows
    ]


def _monthly_sales(date_filter: str, company: str | None) -> list[dict[str, Any]]:
    si = DocType("Sales Invoice")
    period = DateFormat(si.posting_date, "%Y-%m").as_("period")
    q = (
        frappe.qb.from_(si)
        .select(
            period,
            Coalesce(Sum(si.grand_total), 0).as_("revenue"),
            Count("*").as_("transactions"),
            Count(si.customer).distinct().as_("unique_customers"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .groupby(period)
        .orderby(period)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        q = q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        q = q.where(crit)
    rows = q.run(as_dict=True)
    return [
        {
            "period": r.period,
            "revenue": float(r.revenue or 0),
            "transactions": int(r.transactions or 0),
            "unique_customers": int(r.unique_customers or 0),
        }
        for r in rows
    ]


def _avg_days_between_orders(date_filter: str, company: str | None) -> float:
    si = DocType("Sales Invoice")
    q = (
        frappe.qb.from_(si)
        .select(
            si.customer,
            Min(si.posting_date).as_("first_sale"),
            Max(si.posting_date).as_("last_sale"),
            Count("*").as_("order_count"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .groupby(si.customer)
        .having(Count("*") > 1)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        q = q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        q = q.where(crit)
    rows = q.run(as_dict=True)
    total_days = 0
    total_orders_minus_1 = 0
    for r in rows:
        span = (r.last_sale - r.first_sale).days
        total_days += span
        total_orders_minus_1 += int(r.order_count or 0) - 1
    return round(total_days / total_orders_minus_1, 1) if total_orders_minus_1 > 0 else 0


def calculate_revenue_metrics(date_filter: str = "12m", company: str | None = None) -> dict[str, Any]:
    headline = _headline(date_filter, company)
    return {
        **headline,
        "avg_days_between_orders": _avg_days_between_orders(date_filter, company),
        "daily_sales": _daily_sales(date_filter, company),
        "weekly_sales": _weekly_sales(date_filter, company),
        "monthly_sales": _monthly_sales(date_filter, company),
    }


def calculate_payment_mix(date_filter: str = "12m", company: str | None = None) -> dict[str, Any]:
    si = DocType("Sales Invoice")
    base = (
        frappe.qb.from_(si)
        .select(
            Coalesce(Sum(si.grand_total), 0).as_("total"),
            Coalesce(
                Sum(
                    Case()
                    .when(si.outstanding_amount == 0, si.grand_total)
                    .else_(0)
                ),
                0,
            ).as_("cash_total"),
            Coalesce(
                Sum(
                    Case()
                    .when(si.outstanding_amount != 0, si.grand_total)
                    .else_(0)
                ),
                0,
            ).as_("credit_total"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        base = base.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        base = base.where(crit)
    overall = base.run(as_dict=True)[0]
    total = float(overall.total or 0)
    cash_total = float(overall.cash_total or 0)
    credit_total = float(overall.credit_total or 0)

    daily_cutoff = (datetime.now() - timedelta(days=30)).date()
    daily_q = (
        frappe.qb.from_(si)
        .select(
            si.posting_date.as_("sale_date"),
            Coalesce(
                Sum(
                    Case()
                    .when(si.outstanding_amount == 0, si.grand_total)
                    .else_(0)
                ),
                0,
            ).as_("Cash"),
            Coalesce(
                Sum(
                    Case()
                    .when(si.outstanding_amount != 0, si.grand_total)
                    .else_(0)
                ),
                0,
            ).as_("Credit"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .where(si.posting_date >= daily_cutoff)
        .groupby(si.posting_date)
        .orderby(si.posting_date)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        daily_q = daily_q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        daily_q = daily_q.where(crit)
    daily_rows = daily_q.run(as_dict=True)
    daily_mix = []
    for r in daily_rows:
        cash = float(r.Cash or 0)
        credit = float(r.Credit or 0)
        total_d = cash + credit
        daily_mix.append(
            {
                "sale_date": str(r.sale_date),
                "Cash": cash,
                "Credit": credit,
                "total": total_d,
                "cash_pct": round(cash / total_d * 100, 1) if total_d > 0 else 0,
            }
        )

    period_m = DateFormat(si.posting_date, "%Y-%m").as_("period")
    monthly_q = (
        frappe.qb.from_(si)
        .select(
            period_m,
            Coalesce(
                Sum(
                    Case()
                    .when(si.outstanding_amount == 0, si.grand_total)
                    .else_(0)
                ),
                0,
            ).as_("Cash"),
            Coalesce(
                Sum(
                    Case()
                    .when(si.outstanding_amount != 0, si.grand_total)
                    .else_(0)
                ),
                0,
            ).as_("Credit"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .groupby(period_m)
        .orderby(period_m)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        monthly_q = monthly_q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        monthly_q = monthly_q.where(crit)
    monthly_rows = monthly_q.run(as_dict=True)
    monthly_mix = []
    for r in monthly_rows:
        cash = float(r.Cash or 0)
        credit = float(r.Credit or 0)
        total_p = cash + credit
        monthly_mix.append(
            {
                "period": r.period,
                "Cash": cash,
                "Credit": credit,
                "total": total_p,
                "cash_pct": round(cash / total_p * 100, 1) if total_p > 0 else 0,
            }
        )

    today = date.today().isoformat()
    today_total = next((d["total"] for d in daily_mix if d["sale_date"] == today), 0)
    today_cash = next((d["Cash"] for d in daily_mix if d["sale_date"] == today), 0)

    return {
        "cash_ratio": round(cash_total / total * 100, 1) if total > 0 else 0,
        "credit_ratio": round(credit_total / total * 100, 1) if total > 0 else 0,
        "cash_total": cash_total,
        "credit_total": credit_total,
        "today_cash_pct": round(today_cash / today_total * 100, 1) if today_total > 0 else 0,
        "today_total": today_total,
        "daily_mix": daily_mix,
        "monthly_mix": monthly_mix,
    }


def analyze_sales_reps(date_filter: str = "12m", company: str | None = None) -> dict[str, Any]:
    si = DocType("Sales Invoice")
    u = DocType("User")
    q = (
        frappe.qb.from_(si)
        .left_join(u)
        .on(u.name == si.owner)
        .select(
            si.owner.as_("sales_person"),
            Coalesce(u.full_name, si.owner).as_("full_name"),
            Coalesce(Sum(si.grand_total), 0).as_("total_revenue"),
            Count(si.name).distinct().as_("total_orders"),
            Count(si.customer).distinct().as_("unique_customers"),
        )
        .where(si.docstatus == 1)
        .groupby(si.owner, u.full_name)
        .orderby(Count(si.name).distinct(), order=frappe.qb.desc)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        q = q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        q = q.where(crit)
    rows = q.run(as_dict=True)
    # Preserve original ordering: by total_revenue DESC (use Python sort since
    # the qb aggregate-in-orderby is verbose; data volume is small).
    rows.sort(key=lambda r: float(r.total_revenue or 0), reverse=True)
    reps = []
    for idx, r in enumerate(rows, start=1):
        total_rev = float(r.total_revenue or 0)
        total_orders = int(r.total_orders or 0)
        unique = int(r.unique_customers or 0)
        reps.append(
            {
                "sales_person": r.sales_person,
                "sales_person_name": r.full_name or r.sales_person,
                "rank": idx,
                "total_revenue": total_rev,
                "total_orders": total_orders,
                "unique_customers": unique,
                "avg_order_value": round(total_rev / total_orders, 2) if total_orders else 0,
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


def calculate_comparisons(date_filter: str = "12m", company: str | None = None) -> dict[str, Any]:
    si = DocType("Sales Invoice")
    today = date.today()
    current_month_start = today.replace(day=1)
    last_month_final = current_month_start - timedelta(days=1)
    last_month_start = last_month_final.replace(day=1)
    last_month_end = min(
        last_month_start + timedelta(days=today.day - 1),
        last_month_final,
    )
    last_year_start = current_month_start.replace(year=current_month_start.year - 1)
    last_year_end = last_year_start.replace(day=min(today.day, 28))

    def _slice(start_d: date, end_d: date) -> dict[str, Any]:
        q = (
            frappe.qb.from_(si)
            .select(
                Coalesce(Sum(si.grand_total), 0).as_("revenue"),
                Count("*").as_("transactions"),
            )
            .where(si.docstatus == 1)
            .where(si.is_return == 0)
            .where(si.posting_date.between(start_d, end_d))
        )
        if company:
            q = q.where(si.company == company)
        row = q.run(as_dict=True)[0]
        return {
            "revenue": float(row.revenue or 0),
            "transactions": int(row.transactions or 0),
        }

    cur = _slice(current_month_start, today)
    last = _slice(last_month_start, last_month_end)
    last_year = _slice(last_year_start, last_year_end)

    current_revenue = cur["revenue"]
    last_month_revenue = last["revenue"]
    last_year_revenue = last_year["revenue"]
    current_txns = cur["transactions"]
    last_txns = last["transactions"]
    last_year_txns = last_year["transactions"]

    def _pct(now, prev):
        return round((now - prev) / prev * 100, 1) if prev > 0 else 0

    period_m = DateFormat(si.posting_date, "%Y-%m").as_("period")
    monthly_q = (
        frappe.qb.from_(si)
        .select(
            period_m,
            Coalesce(Sum(si.grand_total), 0).as_("revenue"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .groupby(period_m)
        .orderby(period_m)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        monthly_q = monthly_q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        monthly_q = monthly_q.where(crit)
    monthly_rows = monthly_q.run(as_dict=True)
    monthly_trend = []
    for i, r in enumerate(monthly_rows):
        prev = float(monthly_rows[i - 1].revenue or 0) if i > 0 else 0
        curr = float(r.revenue or 0)
        monthly_trend.append(
            {
                "period": r.period,
                "revenue": round(curr, 2),
                "mom_pct": round((curr - prev) / prev * 100, 1) if prev > 0 else 0,
            }
        )
    monthly_trend = monthly_trend[-12:]

    return {
        "current_month": {
            "revenue": current_revenue,
            "transactions": current_txns,
            "aov": round(current_revenue / current_txns, 2) if current_txns else 0,
            "period": current_month_start.strftime("%Y-%m"),
        },
        "last_month": {
            "revenue": last_month_revenue,
            "transactions": last_txns,
            "aov": round(last_month_revenue / last_txns, 2) if last_txns else 0,
            "period": last_month_start.strftime("%Y-%m"),
        },
        "last_year_same_month": {
            "revenue": last_year_revenue,
            "transactions": last_year_txns,
            "aov": round(last_year_revenue / last_year_txns, 2) if last_year_txns else 0,
            "period": last_year_start.strftime("%Y-%m"),
        },
        "mom_growth": _pct(current_revenue, last_month_revenue),
        "yoy_growth": _pct(current_revenue, last_year_revenue),
        "mom_txn_growth": _pct(current_txns, last_txns),
        "yoy_txn_growth": _pct(current_txns, last_year_txns),
        "monthly_trend": monthly_trend,
    }


def analyze_by_dimensions(date_filter: str = "12m", company: str | None = None) -> dict[str, Any]:
    si = DocType("Sales Invoice")
    customer_group = Coalesce(NullIf(si.customer_group, ""), "Uncategorized").as_("customer_group")
    territory = Coalesce(NullIf(si.territory, ""), "Unassigned").as_("territory")
    rows_q = (
        frappe.qb.from_(si)
        .select(
            customer_group,
            territory,
            Coalesce(Sum(si.grand_total), 0).as_("revenue"),
            Count("*").as_("transactions"),
            Count(si.customer).distinct().as_("unique_customers"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .groupby(si.customer_group, si.territory)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        rows_q = rows_q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        rows_q = rows_q.where(crit)
    rows = rows_q.run(as_dict=True)
    by_segment_map: dict[str, dict[str, Any]] = {}
    by_territory_map: dict[str, dict[str, Any]] = {}
    total_revenue = 0.0
    for r in rows:
        rev = float(r.revenue or 0)
        txns = int(r.transactions or 0)
        uniq = int(r.unique_customers or 0)
        total_revenue += rev
        seg = r.customer_group
        terr = r.territory
        by_segment_map[seg] = by_segment_map.get(seg, {"revenue": 0, "transactions": 0, "customers": 0})
        by_segment_map[seg]["revenue"] += rev
        by_segment_map[seg]["transactions"] += txns
        by_segment_map[seg]["customers"] = max(by_segment_map[seg]["customers"], uniq)

        by_territory_map[terr] = by_territory_map.get(terr, {"revenue": 0, "transactions": 0, "customers": 0})
        by_territory_map[terr]["revenue"] += rev
        by_territory_map[terr]["transactions"] += txns
        by_territory_map[terr]["customers"] = max(by_territory_map[terr]["customers"], uniq)

    by_segment = [
        {"customer_group": k, "revenue": round(v["revenue"], 2), "transactions": v["transactions"], "customers": v["customers"], "pct": round(v["revenue"] / total_revenue * 100, 1) if total_revenue > 0 else 0}
        for k, v in sorted(by_segment_map.items(), key=lambda x: x[1]["revenue"], reverse=True)
    ]
    by_territory = [
        {"territory": k, "revenue": round(v["revenue"], 2), "transactions": v["transactions"], "customers": v["customers"], "pct": round(v["revenue"] / total_revenue * 100, 1) if total_revenue > 0 else 0}
        for k, v in sorted(by_territory_map.items(), key=lambda x: x[1]["revenue"], reverse=True)
    ]

    sii = DocType("Sales Invoice Item")
    revenue_expr = Coalesce(
        Sum(
            Case()
            .when(si.base_net_total == 0, sii.base_net_amount)
            .else_(sii.base_net_amount / si.base_net_total * si.base_grand_total)
        ),
        0,
    ).as_("revenue")
    pg_q = (
        frappe.qb.from_(si)
        .inner_join(sii)
        .on(sii.parent == si.name)
        .select(
            sii.item_group,
            revenue_expr,
            Coalesce(Sum(sii.qty), 0).as_("qty_sold"),
            Count(si.name).distinct().as_("transactions"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .where(sii.item_group.notnull())
        .where(sii.item_group != "")
        .orderby(revenue_expr, order=frappe.qb.desc)
        .limit(20)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        pg_q = pg_q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        pg_q = pg_q.where(crit)
    pg_rows = pg_q.run(as_dict=True)
    pg_total = sum(float(r.revenue or 0) for r in pg_rows)
    by_product_group = [
        {
            "item_group": r.item_group,
            "revenue": round(float(r.revenue or 0), 2),
            "qty_sold": float(r.qty_sold or 0),
            "transactions": int(r.transactions or 0),
            "pct": round(float(r.revenue or 0) / pg_total * 100, 1) if pg_total > 0 else 0,
        }
        for r in pg_rows
    ]

    return {
        "by_product_group": by_product_group,
        "by_customer_segment": by_segment,
        "by_territory": by_territory,
        "total_revenue": total_revenue,
    }


def analyze_margins(date_filter: str = "12m", company: str | None = None) -> dict[str, Any]:
    si = DocType("Sales Invoice")
    sii = DocType("Sales Invoice Item")
    profit_expr = sii.net_amount - sii.qty * Coalesce(sii.incoming_rate, 0)
    overall_q = (
        frappe.qb.from_(si)
        .inner_join(sii)
        .on(sii.parent == si.name)
        .select(
            Coalesce(Sum(sii.net_amount), 0).as_("total_revenue"),
            Coalesce(Sum(profit_expr), 0).as_("total_profit"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        overall_q = overall_q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        overall_q = overall_q.where(crit)
    overall = overall_q.run(as_dict=True)[0]
    total_revenue = float(overall.total_revenue or 0)
    total_profit = float(overall.total_profit or 0)
    overall_margin = round(total_profit / total_revenue * 100, 1) if total_revenue > 0 else 0

    pg_q = (
        frappe.qb.from_(si)
        .inner_join(sii)
        .on(sii.parent == si.name)
        .select(
            sii.item_group,
            Coalesce(Sum(sii.net_amount), 0).as_("revenue"),
            Coalesce(Sum(profit_expr), 0).as_("gross_profit"),
            Coalesce(Sum(sii.qty), 0).as_("qty_sold"),
            Count(sii.item_code).distinct().as_("unique_items"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .where(sii.item_group.notnull())
        .groupby(sii.item_group)
        .orderby(Coalesce(Sum(sii.net_amount), 0), order=frappe.qb.desc)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        pg_q = pg_q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        pg_q = pg_q.where(crit)
    pg_rows = pg_q.run(as_dict=True)
    by_product_group = []
    for r in pg_rows:
        rev = float(r.revenue or 0)
        profit = float(r.gross_profit or 0)
        by_product_group.append(
            {
                "item_group": r.item_group,
                "revenue": round(rev, 2),
                "gross_profit": round(profit, 2),
                "qty_sold": float(r.qty_sold or 0),
                "unique_items": int(r.unique_items or 0),
                "margin_pct": round(profit / rev * 100, 1) if rev > 0 else 0,
            }
        )

    item_q = (
        frappe.qb.from_(si)
        .inner_join(sii)
        .on(sii.parent == si.name)
        .select(
            sii.item_code,
            sii.item_name,
            sii.item_group,
            Coalesce(Sum(sii.net_amount), 0).as_("revenue"),
            Coalesce(Sum(profit_expr), 0).as_("gross_profit"),
            Coalesce(Sum(sii.qty), 0).as_("qty_sold"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .where(sii.item_code.notnull())
        .groupby(sii.item_code, sii.item_name, sii.item_group)
        .orderby(Coalesce(Sum(sii.net_amount), 0), order=frappe.qb.desc)
        .limit(500)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        item_q = item_q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        item_q = item_q.where(crit)
    item_rows = item_q.run(as_dict=True)
    top_margin_items = []
    low_margin_items = []
    if item_rows:
        revenues = [float(r.revenue or 0) for r in item_rows]
        threshold = sorted(revenues)[len(revenues) // 2] if revenues else 0
        significant = []
        for r in item_rows:
            rev = float(r.revenue or 0)
            if rev < threshold:
                continue
            profit = float(r.gross_profit or 0)
            margin_pct = round(profit / rev * 100, 1) if rev > 0 else 0
            significant.append(
                {
                    "item_code": r.item_code,
                    "item_name": r.item_name,
                    "item_group": r.item_group,
                    "revenue": round(rev, 2),
                    "gross_profit": round(profit, 2),
                    "qty_sold": float(r.qty_sold or 0),
                    "margin_pct": margin_pct,
                }
            )
        significant.sort(key=lambda x: x["margin_pct"], reverse=True)
        top_margin_items = significant[:10]
        significant_pos = [s for s in significant if s["revenue"] > 0]
        low_margin_items = sorted(significant_pos, key=lambda x: x["margin_pct"])[:10]

    period_t = DateFormat(si.posting_date, "%Y-%m").as_("period")
    trend_q = (
        frappe.qb.from_(si)
        .inner_join(sii)
        .on(sii.parent == si.name)
        .select(
            period_t,
            Coalesce(Sum(sii.net_amount), 0).as_("revenue"),
            Coalesce(Sum(profit_expr), 0).as_("gross_profit"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .groupby(period_t)
        .orderby(period_t)
    )
    crit, _ = _date_filter(date_filter, si.posting_date)
    if crit is not None:
        trend_q = trend_q.where(crit)
    crit, _ = _company_filter(company, si)
    if crit is not None:
        trend_q = trend_q.where(crit)
    trend_rows = trend_q.run(as_dict=True)
    margin_trend = [
        {
            "period": r.period,
            "revenue": round(float(r.revenue or 0), 2),
            "gross_profit": round(float(r.gross_profit or 0), 2),
            "margin_pct": round(float(r.gross_profit or 0) / float(r.revenue or 0) * 100, 1) if float(r.revenue or 0) > 0 else 0,
        }
        for r in trend_rows
    ]
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


def analyze_fulfillment(date_filter: str = "12m", company: str | None = None) -> dict[str, Any]:
    so = DocType("Sales Order")
    status_expr = (
        Case()
        .when(so.per_delivered >= 100, "Fulfilled")
        .when(so.per_delivered > 0, "Partial")
        .else_("Pending")
    ).as_("status")
    status_q = (
        frappe.qb.from_(so)
        .select(
            status_expr,
            Count("*").as_("count"),
            Coalesce(Sum(so.grand_total), 0).as_("value"),
        )
        .where(so.docstatus == 1)
        .groupby(status_expr)
    )
    crit, _ = _date_filter(date_filter, so.transaction_date)
    if crit is not None:
        status_q = status_q.where(crit)
    crit, _ = _company_filter(company, so)
    if crit is not None:
        status_q = status_q.where(crit)
    status_rows = status_q.run(as_dict=True)
    total_orders = 0
    fulfilled = 0
    partial = 0
    pending = 0
    by_status = []
    for r in status_rows:
        cnt = int(r.count or 0)
        total_orders += cnt
        by_status.append({"status": r.status, "count": cnt, "value": float(r.value or 0)})
        if r.status == "Fulfilled":
            fulfilled = cnt
        elif r.status == "Partial":
            partial = cnt
        elif r.status == "Pending":
            pending = cnt
    fulfillment_rate = round(fulfilled / total_orders * 100, 1) if total_orders > 0 else 0

    backlog_q = (
        frappe.qb.from_(so)
        .select(
            Coalesce(Sum(so.grand_total * (1 - so.per_delivered / 100)), 0).as_("backlog_value")
        )
        .where(so.docstatus == 1)
        .where(so.per_delivered < 100)
    )
    crit, _ = _date_filter(date_filter, so.transaction_date)
    if crit is not None:
        backlog_q = backlog_q.where(crit)
    crit, _ = _company_filter(company, so)
    if crit is not None:
        backlog_q = backlog_q.where(crit)
    backlog = backlog_q.run(as_dict=True)[0]
    backlog_value = float(backlog.backlog_value or 0)

    si = DocType("Sales Invoice")
    recv_q = (
        frappe.qb.from_(si)
        .select(
            Coalesce(Sum(si.outstanding_amount), 0).as_("total"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
    )
    if company:
        recv_q = recv_q.where(si.company == company)
    receivables = recv_q.run(as_dict=True)[0]
    total_receivables = float(receivables.total or 0)

    cutoff_90 = (datetime.now() - timedelta(days=90)).date()
    last90_q = (
        frappe.qb.from_(si)
        .select(
            Coalesce(Sum(si.grand_total), 0).as_("total"),
        )
        .where(si.docstatus == 1)
        .where(si.is_return == 0)
        .where(si.posting_date >= cutoff_90)
    )
    if company:
        last90_q = last90_q.where(si.company == company)
    last_90 = last90_q.run(as_dict=True)[0]
    last_90_total = float(last_90.total or 0)
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


def aggregate_forecasts() -> dict[str, Any]:
    from insights.ml.inventory_intelligence import DemandForecasting
    from insights.ml.sales_forecasting import get_sales_forecast

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


def run_sales_intelligence(date_filter: str = "12m", company: str | None = None) -> dict[str, Any]:
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


def get_sales_intelligence(date_filter: str = "12m", company: str | None = None) -> dict[str, Any]:
    """Backward-compatible: every call computes fresh (no cache)."""
    return run_sales_intelligence(date_filter=date_filter, company=company)
