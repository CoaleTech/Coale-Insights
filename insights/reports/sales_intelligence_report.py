# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Sales Intelligence Report -- pure SQL, no pandas/numpy/ibis.

This replaces the ibis-backed `insights.ml.sales_intelligence` module. Every
aggregation is pushed to MariaDB via `frappe.db.sql`; Python only formats the
small result sets into the dict shape the Revenue dashboard already consumes.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import frappe

from insights.api.ml.utils import parse_date_filter


def _date_filter_sql(date_filter: str, column: str = "posting_date") -> tuple[str, dict]:
    """Return (SQL predicate, params) for the standard date filter.

    The predicate is empty when no lower bound applies, otherwise
    ``AND column >= %(start_date)s``. The caller is responsible for the
    leading ``WHERE``/``AND`` context.
    """
    start, _ = parse_date_filter(date_filter)
    if start is None:
        return "", {}
    return f"AND `{column}` >= %(start_date)s", {"start_date": start.date()}


def _company_sql(company: str | None) -> tuple[str, dict]:
    if not company:
        return "", {}
    return "AND company = %(company)s", {"company": company}


def _base_params(date_filter: str, company: str | None) -> dict:
    params: dict = {}
    _, p = _date_filter_sql(date_filter)
    params.update(p)
    _, p = _company_sql(company)
    params.update(p)
    return params


def _headline(date_filter: str, company: str | None) -> dict[str, Any]:
    date_sql, _ = _date_filter_sql(date_filter)
    company_sql, _ = _company_sql(company)
    row = frappe.db.sql(
        f"""
        SELECT
            COALESCE(SUM(grand_total), 0) AS total_revenue,
            COUNT(*) AS total_transactions,
            COUNT(DISTINCT customer) AS unique_customers
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0
        {company_sql}
        {date_sql}
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )[0]
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
    date_sql, _ = _date_filter_sql(date_filter)
    company_sql, _ = _company_sql(company)
    daily_cutoff = (datetime.now() - timedelta(days=30)).date()
    rows = frappe.db.sql(
        f"""
        SELECT
            posting_date,
            COALESCE(SUM(grand_total), 0) AS revenue,
            COUNT(*) AS transactions
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0
            AND posting_date >= %(daily_cutoff)s
            {company_sql}
            {date_sql}
        GROUP BY posting_date
        ORDER BY posting_date
        """,
        {"daily_cutoff": daily_cutoff, **_base_params(date_filter, company)},
        as_dict=True,
    )
    return [
        {
            "date": str(r.posting_date),
            "revenue": float(r.revenue or 0),
            "transactions": int(r.transactions or 0),
        }
        for r in rows
    ]


def _weekly_sales(date_filter: str, company: str | None) -> list[dict[str, Any]]:
    date_sql, _ = _date_filter_sql(date_filter)
    company_sql, _ = _company_sql(company)
    weekly_cutoff = (datetime.now() - timedelta(weeks=12)).date()
    rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(posting_date, '%%x-W%%v') AS year_week,
            COALESCE(SUM(grand_total), 0) AS revenue,
            COUNT(*) AS transactions
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0
            AND posting_date >= %(weekly_cutoff)s
            {company_sql}
            {date_sql}
        GROUP BY year_week
        ORDER BY year_week
        """,
        {"weekly_cutoff": weekly_cutoff, **_base_params(date_filter, company)},
        as_dict=True,
    )
    return [
        {
            "year_week": r.year_week,
            "revenue": float(r.revenue or 0),
            "transactions": int(r.transactions or 0),
        }
        for r in rows
    ]


def _monthly_sales(date_filter: str, company: str | None) -> list[dict[str, Any]]:
    date_sql, _ = _date_filter_sql(date_filter)
    company_sql, _ = _company_sql(company)
    rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(posting_date, '%%Y-%%m') AS period,
            COALESCE(SUM(grand_total), 0) AS revenue,
            COUNT(*) AS transactions,
            COUNT(DISTINCT customer) AS unique_customers
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0
            {company_sql}
            {date_sql}
        GROUP BY period
        ORDER BY period
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )
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
    date_sql, _ = _date_filter_sql(date_filter)
    company_sql, _ = _company_sql(company)
    rows = frappe.db.sql(
        f"""
        SELECT
            customer,
            MIN(posting_date) AS first_sale,
            MAX(posting_date) AS last_sale,
            COUNT(*) AS order_count
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0
            {company_sql}
            {date_sql}
        GROUP BY customer
        HAVING order_count > 1
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )
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
    date_sql, _ = _date_filter_sql(date_filter)
    company_sql, _ = _company_sql(company)
    overall = frappe.db.sql(
        f"""
        SELECT
            COALESCE(SUM(grand_total), 0) AS total,
            COALESCE(SUM(CASE WHEN outstanding_amount = 0 THEN grand_total ELSE 0 END), 0) AS cash_total,
            COALESCE(SUM(CASE WHEN outstanding_amount != 0 THEN grand_total ELSE 0 END), 0) AS credit_total
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0
            {company_sql}
            {date_sql}
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )[0]
    total = float(overall.total or 0)
    cash_total = float(overall.cash_total or 0)
    credit_total = float(overall.credit_total or 0)

    daily_cutoff = (datetime.now() - timedelta(days=30)).date()
    daily_rows = frappe.db.sql(
        f"""
        SELECT
            posting_date AS sale_date,
            COALESCE(SUM(CASE WHEN outstanding_amount = 0 THEN grand_total ELSE 0 END), 0) AS Cash,
            COALESCE(SUM(CASE WHEN outstanding_amount != 0 THEN grand_total ELSE 0 END), 0) AS Credit
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0
            AND posting_date >= %(daily_cutoff)s
            {company_sql}
            {date_sql}
        GROUP BY posting_date
        ORDER BY posting_date
        """,
        {"daily_cutoff": daily_cutoff, **_base_params(date_filter, company)},
        as_dict=True,
    )
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

    monthly_rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(posting_date, '%%Y-%%m') AS period,
            COALESCE(SUM(CASE WHEN outstanding_amount = 0 THEN grand_total ELSE 0 END), 0) AS Cash,
            COALESCE(SUM(CASE WHEN outstanding_amount != 0 THEN grand_total ELSE 0 END), 0) AS Credit
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0
            {company_sql}
            {date_sql}
        GROUP BY period
        ORDER BY period
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )
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
    date_sql, _ = _date_filter_sql(date_filter)
    company_sql, _ = _company_sql(company)
    rows = frappe.db.sql(
        f"""
        SELECT
            si.owner AS sales_person,
            COALESCE(u.full_name, si.owner) AS full_name,
            COALESCE(SUM(si.grand_total), 0) AS total_revenue,
            COUNT(DISTINCT si.name) AS total_orders,
            COUNT(DISTINCT si.customer) AS unique_customers
        FROM `tabSales Invoice` si
        LEFT JOIN `tabUser` u ON u.name = si.owner
        WHERE si.docstatus = 1
            {company_sql}
            {date_sql}
        GROUP BY si.owner, u.full_name
        ORDER BY total_revenue DESC
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )
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
    date_sql, _ = _date_filter_sql(date_filter)
    company_sql, _ = _company_sql(company)
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
        row = frappe.db.sql(
            f"""
            SELECT
                COALESCE(SUM(grand_total), 0) AS revenue,
                COUNT(*) AS transactions
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND is_return = 0
                AND posting_date BETWEEN %(start_d)s AND %(end_d)s
                {company_sql}
            """,
            {"start_d": start_d, "end_d": end_d, **_company_filter_params(company)},
            as_dict=True,
        )[0]
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

    monthly_rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(posting_date, '%%Y-%%m') AS period,
            COALESCE(SUM(grand_total), 0) AS revenue
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0
            {company_sql}
            {date_sql}
        GROUP BY period
        ORDER BY period
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )
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


def _company_filter_params(company: str | None) -> dict:
    _, p = _company_sql(company)
    return p


def analyze_by_dimensions(date_filter: str = "12m", company: str | None = None) -> dict[str, Any]:
    date_sql, _ = _date_filter_sql(date_filter)
    company_sql, _ = _company_sql(company)
    rows = frappe.db.sql(
        f"""
        SELECT
            COALESCE(NULLIF(customer_group, ''), 'Uncategorized') AS customer_group,
            COALESCE(NULLIF(territory, ''), 'Unassigned') AS territory,
            COALESCE(SUM(grand_total), 0) AS revenue,
            COUNT(*) AS transactions,
            COUNT(DISTINCT customer) AS unique_customers
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0
            {company_sql}
            {date_sql}
        GROUP BY customer_group, territory
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )
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

    def _to_list(m):
        return [
            {
                "customer_group" if "customer_group" in k else "territory": k,
                "revenue": round(v["revenue"], 2),
                "transactions": v["transactions"],
                "customers": v["customers"],
                "pct": round(v["revenue"] / total_revenue * 100, 1) if total_revenue > 0 else 0,
            }
            for k, v in sorted(m.items(), key=lambda x: x[1]["revenue"], reverse=True)
        ]

    by_segment = [
        {"customer_group": k, "revenue": round(v["revenue"], 2), "transactions": v["transactions"], "customers": v["customers"], "pct": round(v["revenue"] / total_revenue * 100, 1) if total_revenue > 0 else 0}
        for k, v in sorted(by_segment_map.items(), key=lambda x: x[1]["revenue"], reverse=True)
    ]
    by_territory = [
        {"territory": k, "revenue": round(v["revenue"], 2), "transactions": v["transactions"], "customers": v["customers"], "pct": round(v["revenue"] / total_revenue * 100, 1) if total_revenue > 0 else 0}
        for k, v in sorted(by_territory_map.items(), key=lambda x: x[1]["revenue"], reverse=True)
    ]

    pg_rows = frappe.db.sql(
        f"""
        SELECT
            sii.item_group,
            COALESCE(SUM(
                CASE
                    WHEN si.base_net_total = 0 THEN sii.base_net_amount
                    ELSE sii.base_net_amount / si.base_net_total * si.base_grand_total
                END
            ), 0) AS revenue,
            COALESCE(SUM(sii.qty), 0) AS qty_sold,
            COUNT(DISTINCT si.name) AS transactions
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.docstatus = 1 AND si.is_return = 0
            AND sii.item_group IS NOT NULL AND sii.item_group != ''
            {company_sql}
            {date_sql}
        GROUP BY sii.item_group
        ORDER BY revenue DESC
        LIMIT 20
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )
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
    date_sql, _ = _date_filter_sql(date_filter)
    company_sql, _ = _company_sql(company)
    overall = frappe.db.sql(
        f"""
        SELECT
            COALESCE(SUM(sii.net_amount), 0) AS total_revenue,
            COALESCE(SUM(sii.net_amount - sii.qty * COALESCE(sii.incoming_rate, 0)), 0) AS total_profit
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.docstatus = 1 AND si.is_return = 0
            {company_sql}
            {date_sql}
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )[0]
    total_revenue = float(overall.total_revenue or 0)
    total_profit = float(overall.total_profit or 0)
    overall_margin = round(total_profit / total_revenue * 100, 1) if total_revenue > 0 else 0

    pg_rows = frappe.db.sql(
        f"""
        SELECT
            sii.item_group,
            COALESCE(SUM(sii.net_amount), 0) AS revenue,
            COALESCE(SUM(sii.net_amount - sii.qty * COALESCE(sii.incoming_rate, 0)), 0) AS gross_profit,
            COALESCE(SUM(sii.qty), 0) AS qty_sold,
            COUNT(DISTINCT sii.item_code) AS unique_items
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.docstatus = 1 AND si.is_return = 0
            AND sii.item_group IS NOT NULL
            {company_sql}
            {date_sql}
        GROUP BY sii.item_group
        ORDER BY revenue DESC
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )
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

    item_rows = frappe.db.sql(
        f"""
        SELECT
            sii.item_code,
            sii.item_name,
            sii.item_group,
            COALESCE(SUM(sii.net_amount), 0) AS revenue,
            COALESCE(SUM(sii.net_amount - sii.qty * COALESCE(sii.incoming_rate, 0)), 0) AS gross_profit,
            COALESCE(SUM(sii.qty), 0) AS qty_sold
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.docstatus = 1 AND si.is_return = 0
            AND sii.item_code IS NOT NULL
            {company_sql}
            {date_sql}
        GROUP BY sii.item_code, sii.item_name, sii.item_group
        ORDER BY revenue DESC
        LIMIT 500
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )
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

    trend_rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(si.posting_date, '%%Y-%%m') AS period,
            COALESCE(SUM(sii.net_amount), 0) AS revenue,
            COALESCE(SUM(sii.net_amount - sii.qty * COALESCE(sii.incoming_rate, 0)), 0) AS gross_profit
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.docstatus = 1 AND si.is_return = 0
            {company_sql}
            {date_sql}
        GROUP BY period
        ORDER BY period
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )
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
    date_sql, _ = _date_filter_sql(date_filter, "transaction_date")
    company_sql, _ = _company_sql(company)
    status_rows = frappe.db.sql(
        f"""
        SELECT
            CASE
                WHEN per_delivered >= 100 THEN 'Fulfilled'
                WHEN per_delivered > 0 THEN 'Partial'
                ELSE 'Pending'
            END AS status,
            COUNT(*) AS count,
            COALESCE(SUM(grand_total), 0) AS value
        FROM `tabSales Order`
        WHERE docstatus = 1
            {company_sql}
            {date_sql}
        GROUP BY status
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )
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

    backlog = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(grand_total * (1 - per_delivered / 100)), 0) AS backlog_value
        FROM `tabSales Order`
        WHERE docstatus = 1 AND per_delivered < 100
            {company_sql}
            {date_sql}
        """,
        _base_params(date_filter, company),
        as_dict=True,
    )[0]
    backlog_value = float(backlog.backlog_value or 0)

    si_company_sql, si_params = _company_sql(company)
    receivables = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(outstanding_amount), 0) AS total
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0
            {si_company_sql}
        """,
        si_params,
        as_dict=True,
    )[0]
    total_receivables = float(receivables.total or 0)

    cutoff_90 = (datetime.now() - timedelta(days=90)).date()
    last_90 = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(grand_total), 0) AS total
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0
            AND posting_date >= %(cutoff_90)s
            {si_company_sql}
        """,
        {"cutoff_90": cutoff_90, **si_params},
        as_dict=True,
    )[0]
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
