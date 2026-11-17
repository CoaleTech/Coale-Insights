from __future__ import annotations
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Analysis functions for Strategic Finance Intelligence.
Includes variance analysis, payroll pattern detection, capital planning,
working capital analysis, and financial ratio trends.
"""

import frappe
from frappe.utils import add_months, get_first_day, getdate
from datetime import datetime, timedelta
from typing import Dict, Any, List, TYPE_CHECKING

from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import Abs, Coalesce, DateFormat, Max, Sum

if TYPE_CHECKING:
    import numpy as np


from .data import format_currency, get_cash_total, _gl_daily_cache, _gl_sum_period, _gl_cumulative


def _cash_like(acc):
    """Cash / Bank by account_type plus name-matched Fixed Deposit accounts.

    ERPNext has no term-deposit account_type, so an FD is identifiable only by
    name -- same convention as `financial_intelligence.FD_PREFIX`, which the
    Cash tab uses; keeping both on one definition stops the tabs disagreeing.
    """
    return acc.account_type.isin(["Cash", "Bank"]) | acc.account_name.like("Fixed Deposit%")


def generate_variance_analysis(intelligence, weeks: List[Dict]) -> Dict[str, Any]:
    """
    Generate variance analysis comparing actual vs forecast for historical weeks
    """
    actual_weeks = [w for w in weeks if w.get('is_actual') and w.get('variance')]

    if not actual_weeks:
        return {
            'has_variance_data': False,
            'weeks_analyzed': 0,
            'summary': {},
            'insights': [],
            'weekly_details': []
        }

    # Calculate aggregate variances
    total_inflow_variance = sum(w['variance'].get('inflows', 0) for w in actual_weeks)
    total_outflow_variance = sum(w['variance'].get('outflows', 0) for w in actual_weeks)
    total_net_variance = sum(w['variance'].get('net', 0) for w in actual_weeks)

    avg_inflow_variance = total_inflow_variance / len(actual_weeks)
    avg_outflow_variance = total_outflow_variance / len(actual_weeks)
    avg_net_variance = total_net_variance / len(actual_weeks)

    # Calculate forecast accuracy
    total_forecast_inflows = sum(
        w['inflows']['total'] - w['variance'].get('inflows', 0)
        for w in actual_weeks
    )
    total_actual_inflows = sum(w['inflows']['total'] for w in actual_weeks)

    inflow_accuracy = ((1 - abs(total_inflow_variance) / total_forecast_inflows) * 100) if total_forecast_inflows > 0 else 100

    total_forecast_outflows = sum(
        w['outflows']['total'] - w['variance'].get('outflows', 0)
        for w in actual_weeks
    )
    total_actual_outflows = sum(w['outflows']['total'] for w in actual_weeks)

    outflow_accuracy = ((1 - abs(total_outflow_variance) / total_forecast_outflows) * 100) if total_forecast_outflows > 0 else 100

    # Generate insights
    insights = []

    if avg_inflow_variance > 0:
        insights.append({
            'type': 'positive',
            'category': 'inflows',
            'title': 'Collections Better Than Expected',
            'description': f'Actual inflows exceeded forecast by avg {format_currency(intelligence, avg_inflow_variance)}/week',
            'recommendation': 'Consider revising forecast model upward'
        })
    elif avg_inflow_variance < 0:
        insights.append({
            'type': 'negative',
            'category': 'inflows',
            'title': 'Collections Below Forecast',
            'description': f'Actual inflows fell short of forecast by avg {format_currency(intelligence, abs(avg_inflow_variance))}/week',
            'recommendation': 'Review AR collection processes and customer payment terms'
        })

    if avg_outflow_variance > 0:
        insights.append({
            'type': 'negative',
            'category': 'outflows',
            'title': 'Spending Higher Than Forecast',
            'description': f'Actual outflows exceeded forecast by avg {format_currency(intelligence, avg_outflow_variance)}/week',
            'recommendation': 'Review expense controls and budget adherence'
        })
    elif avg_outflow_variance < 0:
        insights.append({
            'type': 'positive',
            'category': 'outflows',
            'title': 'Spending Below Forecast',
            'description': f'Actual outflows were below forecast by avg {format_currency(intelligence, abs(avg_outflow_variance))}/week',
            'recommendation': 'Verify if delayed payments or deferred expenses'
        })

    # Net position insight
    if total_net_variance > 0:
        insights.append({
            'type': 'positive',
            'category': 'net',
            'title': 'Net Cash Position Better',
            'description': f'Cumulative net cash {format_currency(intelligence, total_net_variance)} better than forecast',
            'recommendation': 'Good performance - consider investment opportunities'
        })
    elif total_net_variance < 0:
        insights.append({
            'type': 'negative',
            'category': 'net',
            'title': 'Net Cash Position Worse',
            'description': f'Cumulative net cash {format_currency(intelligence, abs(total_net_variance))} below forecast',
            'recommendation': 'Monitor closely and review upcoming large payments'
        })

    # Weekly details with trend
    weekly_details = []
    for w in actual_weeks:
        weekly_details.append({
            'week_number': w['week_number'],
            'week_label': w['week_label'],
            'inflow_variance': round(w['variance'].get('inflows', 0), 2),
            'outflow_variance': round(w['variance'].get('outflows', 0), 2),
            'net_variance': round(w['variance'].get('net', 0), 2),
            'inflow_variance_pct': round(
                w['variance'].get('inflows', 0) / (w['inflows']['total'] - w['variance'].get('inflows', 0)) * 100, 1
            ) if (w['inflows']['total'] - w['variance'].get('inflows', 0)) > 0 else 0,
            'outflow_variance_pct': round(
                w['variance'].get('outflows', 0) / (w['outflows']['total'] - w['variance'].get('outflows', 0)) * 100, 1
            ) if (w['outflows']['total'] - w['variance'].get('outflows', 0)) > 0 else 0
        })

    return {
        'has_variance_data': True,
        'weeks_analyzed': len(actual_weeks),
        'summary': {
            'total_inflow_variance': round(total_inflow_variance, 2),
            'total_outflow_variance': round(total_outflow_variance, 2),
            'total_net_variance': round(total_net_variance, 2),
            'avg_inflow_variance': round(avg_inflow_variance, 2),
            'avg_outflow_variance': round(avg_outflow_variance, 2),
            'avg_net_variance': round(avg_net_variance, 2),
            'inflow_forecast_accuracy': round(max(0, min(100, inflow_accuracy)), 1),
            'outflow_forecast_accuracy': round(max(0, min(100, outflow_accuracy)), 1)
        },
        'insights': insights,
        'weekly_details': weekly_details
    }


def _fetch_payroll_entries(intelligence, six_months_ago: str) -> List[Dict[str, Any]]:
    """Fetch payment-entry + journal-entry payroll rows matching the salary /
    payroll / wages keyword set. Returns rows as a list of dicts with at
    least `posting_date` and `paid_amount` populated.

    The legacy SQL used a UNION ALL of two SELECTs plus a correlated subquery
    on `Journal Entry Account`. The query builder does not support UNION ALL
    directly, so we issue two separate `frappe.qb` queries and concatenate
    the result rows (PyPika preserves ORDER BY semantics once we sort the
    merged list ourselves).
    """
    pe = DocType("Payment Entry")
    jea = DocType("Journal Entry Account")
    je = DocType("Journal Entry")

    # Payment Entry rows: salary/payroll/wages in reference_no or remarks.
    keyword_filter_pe = (
        pe.reference_no.like("%salary%")
        | pe.reference_no.like("%payroll%")
        | pe.reference_no.like("%wages%")
        | pe.remarks.like("%salary%")
        | pe.remarks.like("%payroll%")
    )
    pe_rows = (
        frappe.qb.from_(pe)
        .select(
            pe.posting_date,
            pe.paid_amount,
            pe.reference_no,
        )
        .where(pe.company == intelligence.company)
        .where(pe.docstatus == 1)
        .where(pe.posting_date.between(six_months_ago, datetime.now().strftime('%Y-%m-%d')))
        .where(pe.payment_type == "Pay")
        .where(keyword_filter_pe)
        .run(as_dict=True)
    )
    for row in pe_rows:
        row["doctype"] = "Payment Entry"

    # Journal Entry rows: a correlated subquery computes the paid amount.
    # Subqueries in PyPika are emitted as bound SELECTs by the query builder;
    # we replicate the same shape with a grouped join and a post-filter in
    # Python (semantically identical: same set of rows, same aggregation).
    keyword_filter_je = (
        je.user_remark.like("%salary%")
        | je.user_remark.like("%payroll%")
        | je.user_remark.like("%wages%")
        | je.cheque_no.like("%salary%")
    )
    # Aggregate debit per journal entry (only positive debit rows).
    je_debits = (
        frappe.qb.from_(jea)
        .select(
            jea.parent,
            Coalesce(Sum(Abs(jea.debit_in_account_currency)), 0).as_("paid_amount"),
        )
        .where(jea.debit_in_account_currency > 0)
        .groupby(jea.parent)
    )
    je_rows = (
        frappe.qb.from_(je)
        .join(je_debits)
        .on(je_debits.parent == je.name)
        .select(
            je.posting_date,
            je_debits.paid_amount,
            je.cheque_no.as_("reference_no"),
        )
        .where(je.company == intelligence.company)
        .where(je.docstatus == 1)
        .where(je.posting_date.between(six_months_ago, datetime.now().strftime('%Y-%m-%d')))
        .where(keyword_filter_je)
        .run(as_dict=True)
    )
    for row in je_rows:
        row["doctype"] = "Journal Entry"

    # Combined result, ordered by posting_date DESC to match the legacy
    # UNION ALL tail ORDER BY.
    combined = pe_rows + je_rows
    combined.sort(key=lambda r: r["posting_date"], reverse=True)
    return combined


def _fetch_gl_payroll_entries(intelligence, six_months_ago: str) -> List[Dict[str, Any]]:
    """Fallback query: GL Entry rows on accounts whose name contains
    Salary / Payroll / Wages, with `paid_amount = ABS(debit - credit)` and
    filtered above 10,000 (currency-units threshold from the legacy SQL)."""
    gle = DocType("GL Entry")
    acc = DocType("Account")
    name_filter = (
        acc.name.like("%Salary%")
        | acc.name.like("%Payroll%")
        | acc.name.like("%Wages%")
    )
    return (
        frappe.qb.from_(gle)
        .join(acc)
        .on(gle.account == acc.name)
        .select(
            gle.posting_date,
            Abs(gle.debit - gle.credit).as_("paid_amount"),
        )
        .where(gle.company == intelligence.company)
        .where(gle.posting_date.between(six_months_ago, datetime.now().strftime('%Y-%m-%d')))
        .where(gle.is_cancelled == 0)
        .where(name_filter)
        .where(Abs(gle.debit - gle.credit) > 10000)
        .orderby(gle.posting_date, order=frappe.qb.desc)
        .run(as_dict=True)
    )


def _payroll_runs(rows) -> List[Dict[str, Any]]:
    """One payroll run is many same-day entries (a Journal Entry per employee
    here); sum them so the typical amount is the run, not one employee."""
    runs: Dict[Any, float] = {}
    for r in rows or []:
        runs[r["posting_date"]] = runs.get(r["posting_date"], 0.0) + float(r["paid_amount"] or 0)
    return [frappe._dict(posting_date=d, paid_amount=a) for d, a in sorted(runs.items(), reverse=True)]


def detect_payroll_pattern(intelligence) -> Dict[str, Any]:
    """
    Auto-detect payroll schedule from historical Journal Entry and Payment Entry
    containing salary/payroll/wages keywords
    """
    import numpy as np
    six_months_ago = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')

    # Search for payroll-related payments
    payroll_entries = _payroll_runs(_fetch_payroll_entries(intelligence, six_months_ago))

    if len(payroll_entries) < 2:
        # Not enough data, check salary account directly
        payroll_entries = _payroll_runs(_fetch_gl_payroll_entries(intelligence, six_months_ago))

    if not payroll_entries or len(payroll_entries) < 2:
        return {
            'detected': False,
            'frequency': 'unknown',
            'typical_amount': 0,
            'next_date': None,
            'confidence': 0,
            'day_of_month': None
        }

    # Analyze patterns
    dates = [datetime.strptime(str(e.posting_date), '%Y-%m-%d') if isinstance(e.posting_date, str)
             else e.posting_date for e in payroll_entries]
    amounts = [float(e.paid_amount or 0) for e in payroll_entries]

    # Calculate intervals between payments
    intervals = []
    for i in range(1, len(dates)):
        interval = (dates[i-1] - dates[i]).days
        if 5 <= interval <= 35:  # Reasonable payroll interval
            intervals.append(interval)

    if not intervals:
        return {
            'detected': False,
            'frequency': 'unknown',
            'typical_amount': float(np.mean(amounts)) if amounts else 0,
            'next_date': None,
            'confidence': 0,
            'day_of_month': None
        }

    avg_interval = float(np.mean(intervals))
    std_interval = float(np.std(intervals)) if len(intervals) > 1 else 10

    # Determine frequency
    if avg_interval <= 9:
        frequency = 'weekly'
        expected_interval = 7
    elif avg_interval <= 17:
        frequency = 'bi-weekly'
        expected_interval = 14
    elif avg_interval <= 20:
        frequency = 'semi-monthly'
        expected_interval = 15
    else:
        frequency = 'monthly'
        expected_interval = 30

    # Calculate confidence based on consistency
    consistency = 1 - (std_interval / avg_interval) if avg_interval > 0 else 0
    confidence = min(0.95, max(0.3, consistency))

    # Typical amount (median to reduce outlier effect)
    typical_amount = float(np.median(amounts)) if amounts else 0

    # Detect day of month for monthly payroll
    day_of_month = None
    if frequency == 'monthly':
        days = [d.day for d in dates]
        day_counts = {}
        for d in days:
            day_counts[d] = day_counts.get(d, 0) + 1
        if day_counts:
            day_of_month = max(day_counts, key=day_counts.get)

    # Calculate next expected payroll date
    last_payroll = dates[0] if dates else datetime.now()

    # Get the date part for comparison
    def get_date(d):
        if hasattr(d, 'date') and callable(d.date):
            return d.date()
        return d

    # Roll forward to the first date on or after today. Monthly steps by
    # calendar month from the last payroll: a flat 30 days drifts a day early
    # whenever the payroll is posted on the 31st.
    today = datetime.now().date()
    if frequency == 'monthly':
        k = 1
        next_date = add_months(get_date(last_payroll), k)
        while get_date(next_date) < today:
            k += 1
            next_date = add_months(get_date(last_payroll), k)
    else:
        next_date = last_payroll + timedelta(days=expected_interval)
        while get_date(next_date) < today:
            next_date += timedelta(days=expected_interval)

    return {
        'detected': True,
        'frequency': frequency,
        'typical_amount': round(typical_amount, 2),
        'next_date': str(get_date(next_date)),
        'confidence': round(confidence, 2),
        'day_of_month': day_of_month,
        'avg_interval_days': round(avg_interval, 1),
        'entries_analyzed': len(payroll_entries)
    }


def analyze_capital_planning(intelligence) -> Dict[str, Any]:
    """Analyze capital assets and CAPEX planning"""
    # Get all assets
    Asset = DocType("Asset")
    # ERPNext v15 stores the cost in `gross_purchase_amount` (labelled "Net Purchase
    # Amount"); v16 renamed the same column to `net_purchase_amount`.
    cost = getattr(
        Asset, "net_purchase_amount" if frappe.db.has_column("Asset", "net_purchase_amount") else "gross_purchase_amount"
    )
    DepSchedule = DocType("Depreciation Schedule")

    # Subquery: accumulated depreciation per asset as of today. The legacy
    # SQL used `WHERE schedule_date <= CURDATE()`; resolve that to a Python
    # date so PyPika emits a literal bound parameter.
    today_str = datetime.now().strftime('%Y-%m-%d')
    ads_subq = (
        frappe.qb.from_(DepSchedule)
        .select(
            DepSchedule.parent,
            Sum(DepSchedule.depreciation_amount).as_("accumulated_depreciation"),
        )
        .where(DepSchedule.schedule_date <= today_str)
        .groupby(DepSchedule.parent)
    )

    assets = (
        frappe.qb.from_(Asset)
        .left_join(ads_subq)
        .on(ads_subq.parent == Asset.name)
        .select(
            Asset.name,
            Asset.asset_name,
            Asset.asset_category,
            cost.as_("net_purchase_amount"),
            Asset.purchase_date,
            Asset.available_for_use_date,
            Asset.status,
            Asset.value_after_depreciation,
            Asset.total_number_of_depreciations,
            Asset.frequency_of_depreciation,
            Coalesce(ads_subq.accumulated_depreciation, 0).as_("accumulated_depreciation"),
        )
        .where(Asset.company == intelligence.company)
        .where(Asset.docstatus == 1)
        .where(Asset.status.notin(["Sold", "Scrapped"]))
        .orderby(cost, order=frappe.qb.desc)
        .run(as_dict=True)
    )

    # Summarize by category
    category_summary = {}
    total_gross = 0
    total_net = 0
    total_depreciation = 0

    for asset in assets:
        cat = asset.asset_category or "Uncategorized"
        if cat not in category_summary:
            category_summary[cat] = {
                "category": cat,
                "asset_count": 0,
                "gross_value": 0,
                "net_value": 0,
                "accumulated_depreciation": 0
            }

        gross = float(asset.net_purchase_amount or 0)
        net = float(asset.value_after_depreciation or gross)
        dep = float(asset.accumulated_depreciation or 0)

        category_summary[cat]["asset_count"] += 1
        category_summary[cat]["gross_value"] += gross
        category_summary[cat]["net_value"] += net
        category_summary[cat]["accumulated_depreciation"] += dep

        total_gross += gross
        total_net += net
        total_depreciation += dep

    # CAPEX this year
    fy_start = intelligence.fiscal_year["start_date"]
    ytd_capex_rows = (
        frappe.qb.from_(Asset)
        .select(Coalesce(Sum(cost), 0).as_("amount"))
        .where(Asset.company == intelligence.company)
        .where(Asset.docstatus == 1)
        .where(Asset.purchase_date.between(fy_start, today_str))
        .run(as_dict=True)
    )
    ytd_capex = float(ytd_capex_rows[0].amount or 0) if ytd_capex_rows else 0.0

    # Prior year CAPEX for comparison: the same stretch of the prior year, since
    # this year's figure is year-to-date (7 months against 12 read as a -88% drop).
    prior_fy_start = add_months(fy_start, -12)
    prior_end = add_months(today_str, -12)
    prior_capex_rows = (
        frappe.qb.from_(Asset)
        .select(Coalesce(Sum(cost), 0).as_("amount"))
        .where(Asset.company == intelligence.company)
        .where(Asset.docstatus == 1)
        .where(Asset.purchase_date >= prior_fy_start)
        .where(Asset.purchase_date <= prior_end)
        .run(as_dict=True)
    )
    prior_capex = float(prior_capex_rows[0].amount or 0) if prior_capex_rows else 0.0

    # Fixed Asset / Accumulated Depreciation accounts are the book of record.
    # The Asset register can lag it (opening balances, assets never registered),
    # so the headline comes from GL when GL has any fixed assets; the register
    # only supplies the category / top-asset detail and its coverage is exposed.
    register_gross = total_gross
    gle = DocType("GL Entry")
    acc = DocType("Account")
    fa = acc.account_type == "Fixed Asset"
    ad = acc.account_type == "Accumulated Depreciation"
    net_dr = gle.debit - gle.credit
    row = (
        frappe.qb.from_(gle)
        .join(acc)
        .on(gle.account == acc.name)
        .select(
            Coalesce(Sum(Case().when(fa, net_dr).else_(0)), 0).as_("gross"),
            Coalesce(Sum(Case().when(ad, -net_dr).else_(0)), 0).as_("accdep"),
            Coalesce(Sum(Case().when(fa & (gle.posting_date >= fy_start), gle.debit).else_(0)), 0).as_("ytd"),
            Coalesce(Sum(Case().when(fa & (gle.posting_date >= prior_fy_start) & (gle.posting_date <= prior_end), gle.debit).else_(0)), 0).as_("prior"),
        )
        .where(gle.company == intelligence.company)
        .where(gle.is_cancelled == 0)
        .where(gle.posting_date <= today_str)
        .where(acc.account_type.isin(["Fixed Asset", "Accumulated Depreciation"]))
        .run(as_dict=True)
    )[0]
    if float(row.gross) > 0:
        total_gross = float(row.gross)
        total_depreciation = float(row.accdep)
        total_net = total_gross - total_depreciation
        ytd_capex = float(row.ytd)
        prior_capex = float(row.prior)

    # Upcoming depreciation (next 12 months). Legacy SQL bounded with
    # `BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 12 MONTH)`;
    # resolve to literal dates.
    twelve_months_ahead = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
    period_expr = DateFormat(DepSchedule.schedule_date, "%Y-%m").as_("period")
    upcoming_depreciation = (
        frappe.qb.from_(DepSchedule)
        .join(Asset)
        .on(DepSchedule.parent == Asset.name)
        .select(
            period_expr,
            Sum(DepSchedule.depreciation_amount).as_("amount"),
        )
        .where(Asset.company == intelligence.company)
        .where(Asset.docstatus == 1)
        .where(Asset.status.notin(["Sold", "Scrapped"]))
        .where(DepSchedule.schedule_date.between(today_str, twelve_months_ahead))
        .groupby(period_expr)
        .orderby(period_expr)
        .run(as_dict=True)
    )

    return {
        "total_gross_assets": total_gross,
        "register_gross_assets": register_gross,
        "total_net_assets": total_net,
        "total_accumulated_depreciation": total_depreciation,
        "asset_count": len(assets),
        "ytd_capex": float(ytd_capex),
        "prior_year_capex": float(prior_capex),
        "capex_change_pct": round(((float(ytd_capex) - float(prior_capex)) / float(prior_capex) * 100), 1) if prior_capex > 0 else None,
        "category_summary": list(category_summary.values()),
        "upcoming_depreciation": [{"period": d.period, "amount": float(d.amount)} for d in upcoming_depreciation],
        "top_assets": [
            {
                "name": a.name,
                "asset_name": a.asset_name,
                "category": a.asset_category,
                "gross_value": float(a.net_purchase_amount or 0),
                "net_value": float(a.value_after_depreciation or a.net_purchase_amount or 0),
                "status": a.status
            }
            for a in assets[:10]
        ]
    }


def analyze_working_capital(intelligence) -> Dict[str, Any]:
    """Analyze working capital metrics and trends — reads _gl_daily_cache."""
    today_str = getdate().strftime('%Y-%m-%d')

    # ── Point-in-time balances from the shared GL daily cache ─────────────
    # Replaces 1 current-assets query + 1 current-liabilities query +
    # 1 monthly-trends GL query (3 DB round-trips → 0).
    gl = _gl_daily_cache(intelligence)
    # Book balance, same as the Cash Position card: post-dated payments already
    # reduce cash (see data._load_cash_breakdown).
    cash        = get_cash_total(intelligence)
    post_dated  = cash - _gl_cumulative(gl, today_str, "cash")
    receivables = _gl_cumulative(gl, today_str, "receivable")
    inventory   = _gl_cumulative(gl, today_str, "inventory")
    total_current_assets      = cash + receivables + inventory
    total_current_liabilities = abs(_gl_cumulative(gl, today_str, "payable"))
    current_liabilities       = total_current_liabilities  # signed alias for DSO/DPO

    working_capital = total_current_assets - total_current_liabilities
    current_ratio = min(round(total_current_assets / total_current_liabilities, 2), 10.0) if total_current_liabilities > 1000 else None
    quick_ratio   = min(round((cash + receivables) / total_current_liabilities, 2), 10.0) if total_current_liabilities > 1000 else None

    # ── DSO / DPO / DIO (Sales Invoice + Purchase Invoice — unchanged) ────
    today_bound = datetime.now().strftime('%Y-%m-%d')

    def _window(doctype: str):
        # 90 days ending at the LAST posted document, not at today: when the
        # ledger runs behind the calendar, a window anchored on today counts
        # empty days and inflates DSO/DPO (45 live days / 90 halved the average).
        t = DocType(doctype)
        base = (
            frappe.qb.from_(t)
            .where(t.company == intelligence.company)
            .where(t.docstatus == 1)
            .where(t.posting_date <= today_bound)
        )
        last = base.select(Max(t.posting_date)).run()[0][0]
        if not last:
            return None
        return base, getdate(last) - timedelta(days=89), last  # BETWEEN is inclusive: 90 days, matching the /90 below

    def _daily_avg(doctype: str) -> float:
        w = _window(doctype)
        if not w:
            return 1.0
        base, start, last = w
        total = base.select(Coalesce(Sum(DocType(doctype).grand_total), 0)).where(DocType(doctype).posting_date.between(start, last)).run()[0][0]
        return float(total or 0) / 90 or 1.0

    avg_daily_revenue = _daily_avg("Sales Invoice")
    avg_daily_purchases = _daily_avg("Purchase Invoice")
    # DIO is stock held against cost of goods SOLD, taken from the ledger over the
    # sales window. Purchase invoices are tax-inclusive and are not what left stock
    # (₹41.4M vs ₹34.9M here). Without a COGS account (no perpetual inventory) fall
    # back to purchases rather than reporting 0 days.
    sw = _window("Sales Invoice")
    avg_daily_cogs = (_gl_sum_period(gl, str(sw[1]), str(sw[2]), "cogs") / 90 if sw else 0) or avg_daily_purchases

    dso = min(receivables / float(avg_daily_revenue), 365) if avg_daily_revenue > 0 else 0
    dpo = min(abs(float(current_liabilities)) / float(avg_daily_purchases), 365) if avg_daily_purchases > 0 else 0
    dio = min(inventory / float(avg_daily_cogs), 365) if avg_daily_cogs > 0 else 0
    ccc = max(min(dso + dio - dpo, 365), -365)

    # ── Monthly working capital trends (from GL daily cache) ──────────────
    # Running balance at each month-end: cumulate _gl_daily rows month by month.
    periods = [add_months(get_first_day(today_str), -n).strftime('%Y-%m') for n in range(11, -1, -1)]

    # Group _gl_daily rows by month (all rows up to today_str are already in cache)
    from collections import defaultdict
    month_ca: dict = defaultdict(float)
    month_cl: dict = defaultdict(float)
    for r in gl:
        pd = r['_pd']
        if pd > today_str:
            continue
        m = pd[:7]
        month_ca[m] += (float(r.cash or 0)
                        + float(r.receivable or 0)
                        + float(r.inventory or 0))
        month_cl[m] += float(r.payable or 0)

    sorted_months = sorted(set(month_ca.keys()) | set(month_cl.keys()))
    month_idx = 0
    trends = []
    ca = cl = 0.0
    for period in periods:
        while month_idx < len(sorted_months) and sorted_months[month_idx] <= period:
            m = sorted_months[month_idx]
            ca += month_ca.get(m, 0.0)
            cl += month_cl.get(m, 0.0)
            month_idx += 1
        trends.append({
            "period": period,
            "current_assets": ca,
            "current_liabilities": cl,
            "working_capital": ca - cl,
            "current_ratio": round(ca / cl, 2) if cl > 0 else None,
        })
    if trends:  # latest point is today's book position, matching the headline
        trends[-1]["current_assets"] += post_dated
        trends[-1]["working_capital"] += post_dated
        trends[-1]["current_ratio"] = round(trends[-1]["current_assets"] / trends[-1]["current_liabilities"], 2) if trends[-1]["current_liabilities"] > 0 else None


    return {
        "cash": cash,
        "receivables": receivables,
        "inventory": inventory,
        "total_current_assets": total_current_assets,
        "total_current_liabilities": total_current_liabilities,
        "working_capital": working_capital,
        "current_ratio": current_ratio,
        "quick_ratio": quick_ratio,
        "dso": round(dso, 1),
        "dpo": round(dpo, 1),
        "dio": round(dio, 1),
        "cash_conversion_cycle": round(ccc, 1),
        "trends": trends
    }


def _rolling_90_day_windows(now, count: int = 8) -> list:
    """`count` contiguous 90-day windows, newest ending `now`, as dicts with
    start/end (ISO) and a label.

    Windows are inclusive at both ends, so each starts 89 days before its end
    and a day is never counted in two windows. They are not calendar quarters,
    so each is labelled by the date it ends on (a quarter label put "Q3 2026" on
    May-Jul and could repeat for two windows)."""
    windows = []
    for q in range(count):
        end_date = now - timedelta(days=q * 90)
        start_date = end_date - timedelta(days=89)
        windows.append({
            "start": start_date.strftime('%Y-%m-%d'),
            "end": end_date.strftime('%Y-%m-%d'),
            "label": end_date.strftime('%d %b %Y'),
        })
    return windows


def calculate_ratio_trends(intelligence) -> Dict[str, Any]:
    """Calculate financial ratio trends over time"""
    from insights.ml.sales_intelligence import gross_margin_totals

    quarters = _rolling_90_day_windows(datetime.now())

    ratio_trends = []
    # Each window is 90 days of flow over a point-in-time balance; the benchmarks
    # for ROE/ROA/ROCE/turnover are yearly, so scale those by 365/90.
    ann = 365 / 90
    # Loan-type liability balance as of the *previous* (older) iteration's
    # quarter-end, which is exactly this quarter's start balance: the 90-day
    # windows built above are contiguous (quarter q's start == quarter q+1's
    # end) and this walk runs oldest-to-newest. Recomputed fresh every call,
    # never cached, so a mid-quarter repayment shows up the same day.
    prev_loan_balance = None

    # One GL scan for all 8 quarters (period P&L + cumulative balance sheet).
    # Replaces 8 × period query + 8 × cumulative query = 16 DB round-trips.
    gl = _gl_daily_cache(intelligence)

    for q in reversed(quarters):
        # ── Period P&L ────────────────────────────────────────────────────
        revenue          = abs(_gl_sum_period(gl, q["start"], q["end"], "income"))
        expenses         = abs(_gl_sum_period(gl, q["start"], q["end"], "expense"))
        depreciation     = abs(_gl_sum_period(gl, q["start"], q["end"], "dep"))
        interest_expense = abs(_gl_sum_period(gl, q["start"], q["end"], "interest"))

        # ── Cumulative balance sheet as of quarter end ────────────────────
        assets      = abs(_gl_cumulative(gl, q["end"], "asset"))
        liabilities = abs(_gl_cumulative(gl, q["end"], "liability"))
        equity      = abs(_gl_cumulative(gl, q["end"], "equity"))
        # Latest window uses book cash (post-dated payments already out), like the
        # Working Capital tab and Cash Position card; older windows have no such split.
        cash        = get_cash_total(intelligence) if q is quarters[0] else _gl_cumulative(gl, q["end"], "cash")
        receivables = _gl_cumulative(gl, q["end"], "receivable")
        inventory   = _gl_cumulative(gl, q["end"], "inventory")
        payables    = abs(_gl_cumulative(gl, q["end"], "payable"))
        loan_balance = abs(_gl_cumulative(gl, q["end"], "loan"))

        gm = gross_margin_totals(q["start"], q["end"], intelligence.company)
        net_income = revenue - expenses

        current_assets      = cash + receivables + inventory
        current_liabilities = payables
        working_capital     = current_assets - current_liabilities

        # ── Derived metrics ───────────────────────────────────────────────
        # Only a *reduction* counts as debt service; a rise in balance is
        # financing inflow (new borrowing), not an outflow DSCR should penalise.
        principal_repaid = max(0.0, prev_loan_balance - loan_balance) if prev_loan_balance is not None else 0.0
        prev_loan_balance = loan_balance

        # Capital employed = total assets - current liabilities (trade payables,
        # the same current-liability definition the Current Ratio uses). Taken
        # before the asset floor below so a tiny balance cannot inflate ROCE.
        capital_employed = assets - payables
        # Avoid division issues - use reasonable defaults
        assets = assets if assets > 1000 else 1
        equity = equity if equity > 1000 else 1

        # EBIT/EBITDA add back interest and D&A, both already netted into
        # `expenses` above. No tax add-back: this CoA carries no income-tax /
        # provision-for-tax account distinct from indirect taxes (customs
        # duty, GST) that are real operating costs and must stay expensed.
        ebit = net_income + interest_expense
        ebitda = ebit + depreciation
        total_debt_service = interest_expense + principal_repaid

        ratio_trends.append({
            "period": q["label"],
            "gross_margin": gm["overall_margin"] if gm["total_revenue"] > 0 else None,
            "net_margin": round(net_income / revenue * 100, 1) if revenue > 0 else None,
            "roe": round(net_income * ann / equity * 100, 1) if equity > 1000 else None,
            "roa": round(net_income * ann / assets * 100, 1) if assets > 1000 else None,
            "debt_to_equity": round(liabilities / equity, 2) if equity > 1000 else None,
            "asset_turnover": round(revenue * ann / assets, 2) if assets > 1000 else None,
            "ebitda": round(ebitda, 2),
            "ebit": round(ebit, 2),
            "roce": round(ebit * ann / capital_employed * 100, 1) if capital_employed > 1000 else None,
            "ebitda_margin": round(ebitda / revenue * 100, 1) if revenue > 0 else None,
            # Capped like `current_ratio`/`dso`/`ccc` above: a turnover or
            # coverage ratio computed from a denominator just over the 1000
            # epsilon (e.g. working capital of 1,050 against six-figure
            # revenue) explodes into triple digits that are a threshold
            # artifact, not a business signal.
            "working_capital_turnover": max(-20.0, min(20.0, round(revenue * ann / working_capital, 2))) if working_capital > 1000 else None,
            "interest_coverage": max(-20.0, min(20.0, round(ebit / interest_expense, 2))) if interest_expense > 1000 else None,
            "dscr": max(-10.0, min(10.0, round(ebitda / total_debt_service, 2))) if total_debt_service > 1000 else None,
        })

    # Current period ratios
    current = ratio_trends[-1] if ratio_trends else {}

    # Industry benchmarks (Kenya SME averages - indicative)
    benchmarks = {
        "gross_margin": 35.0,
        "net_margin": 10.0,
        "roe": 15.0,
        "roa": 8.0,
        "debt_to_equity": 1.5,
        "asset_turnover": 1.2,
        "ebitda_margin": 15.0,
        "working_capital_turnover": 4.0,
        "interest_coverage": 3.0,
        "dscr": 1.25,
        # Same target the Break-Even tab uses (Insights Settings, default 15).
        "roce": float(frappe.db.get_single_value("Insights Settings", "roce_target") or 15),
    }

    def _status(value, benchmark, higher_is_better=True):
        """'unavailable' (neutral, not a red flag) when the ratio has no
        meaningful denominator -- e.g. no equity or no debt to service --
        rather than forcing it through the good/warning split with a
        fabricated 0."""
        if value is None:
            return "unavailable"
        ok = value >= benchmark if higher_is_better else value <= benchmark
        return "good" if ok else "warning"

    def _card(name, key, higher_is_better=True):
        value = current.get(key)
        return {
            "name": name,
            "value": value,
            "benchmark": benchmarks[key],
            "status": _status(value, benchmarks[key], higher_is_better),
        }

    return {
        "current_ratios": current,
        "trends": ratio_trends,
        "benchmarks": benchmarks,
        "ratio_cards": [
            _card("Gross Margin", "gross_margin"),
            _card("Net Margin", "net_margin"),
            _card("ROE", "roe"),
            _card("ROA", "roa"),
            _card("Debt/Equity", "debt_to_equity", higher_is_better=False),
            _card("Asset Turnover", "asset_turnover"),
            _card("EBITDA Margin", "ebitda_margin"),
            _card("Working Capital Turnover", "working_capital_turnover"),
            _card("Interest Coverage", "interest_coverage"),
            _card("DSCR", "dscr"),
            _card("ROCE", "roce"),
        ]
    }
