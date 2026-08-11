from __future__ import annotations
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Data collection helpers for Strategic Finance Intelligence.
All _get_*() methods, _format_currency(), and sanitize_for_json().
"""

import frappe
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np



def sanitize_for_json(obj):
    """Convert numpy types to native Python types for JSON serialization"""
    import numpy as np
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return sanitize_for_json(obj.tolist())
    else:
        return obj


def format_currency(intelligence, value: float) -> str:
    """Helper to format currency for insights"""
    currency = getattr(intelligence, 'base_currency', 'USD')
    if abs(value) >= 1000000:
        return f"{currency} {value/1000000:.1f}M"
    elif abs(value) >= 1000:
        return f"{currency} {value/1000:.0f}K"
    return f"{currency} {value:.0f}"


def get_current_fiscal_year(intelligence) -> Dict[str, Any]:
    """Get current fiscal year for the company"""
    today = datetime.now().date()
    fy = frappe.db.sql("""
        SELECT name, year_start_date, year_end_date
        FROM `tabFiscal Year`
        WHERE %s BETWEEN year_start_date AND year_end_date
        ORDER BY year_start_date DESC
        LIMIT 1
    """, (today,), as_dict=True)

    if fy:
        return {
            "name": fy[0].name,
            "start_date": str(fy[0].year_start_date),
            "end_date": str(fy[0].year_end_date)
        }

    # Default to calendar year if no fiscal year found
    return {
        "name": str(today.year),
        "start_date": f"{today.year}-01-01",
        "end_date": f"{today.year}-12-31"
    }


def get_cash_balance(intelligence) -> float:
    """Get current cash and bank balance"""
    cash = frappe.db.sql("""
        SELECT COALESCE(SUM(debit - credit), 0) as balance
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE acc.account_type IN ('Cash', 'Bank')
            AND gle.company = %s
            AND gle.is_cancelled = 0
    """, (intelligence.company,), as_dict=True)[0].balance or 0
    return cash


def get_monthly_financial_trends(intelligence) -> List[Dict]:
    """Get monthly revenue/expense trends for last 12 months"""
    trends = frappe.db.sql("""
        SELECT
            DATE_FORMAT(gle.posting_date, '%%Y-%%m') as period,
            SUM(CASE WHEN acc.root_type = 'Income' THEN ABS(credit - debit) ELSE 0 END) as revenue,
            SUM(CASE WHEN acc.root_type = 'Expense' THEN ABS(debit - credit) ELSE 0 END) as expenses
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE gle.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            AND gle.company = %s
            AND gle.is_cancelled = 0
            AND acc.root_type IN ('Income', 'Expense')
        GROUP BY DATE_FORMAT(gle.posting_date, '%%Y-%%m')
        ORDER BY period
    """, (intelligence.company,), as_dict=True)

    result = []
    for t in trends:
        revenue = float(t.revenue or 0)
        expenses = float(t.expenses or 0)
        result.append({
            "period": t.period,
            "revenue": revenue,
            "expenses": expenses,
            "net_income": revenue - expenses,
            "margin": round((revenue - expenses) / revenue * 100, 1) if revenue > 0 else 0
        })
    return result


def get_expense_breakdown(intelligence) -> List[Dict[str, Any]]:
    """Get expense breakdown by category for current fiscal year"""
    fy_start = intelligence.fiscal_year["start_date"]
    today = datetime.now().strftime('%Y-%m-%d')

    # Get expense accounts with their totals
    expenses = frappe.db.sql("""
        SELECT
            acc.account_name as category,
            acc.parent_account,
            COALESCE(SUM(ABS(gle.debit - gle.credit)), 0) as amount
        FROM `tabAccount` acc
        LEFT JOIN `tabGL Entry` gle ON gle.account = acc.name
            AND gle.is_cancelled = 0
            AND gle.posting_date BETWEEN %s AND %s
        WHERE acc.root_type = 'Expense'
            AND acc.is_group = 0
            AND acc.company = %s
        GROUP BY acc.name
        HAVING amount > 0
        ORDER BY amount DESC
        LIMIT 10
    """, (fy_start, today, intelligence.company), as_dict=True)

    # Calculate total and percentages
    total = sum(e.get('amount', 0) for e in expenses)

    result = []
    for exp in expenses:
        amount = float(exp.get('amount', 0))
        pct = round((amount / total * 100), 1) if total > 0 else 0
        result.append({
            "category": exp.get('category', 'Unknown'),
            "amount": amount,
            "percentage": pct
        })

    return result


def get_historical_cash_transactions(intelligence, start_date: datetime, end_date: datetime) -> Dict[str, Dict]:
    """Get categorized historical cash transactions by week"""
    transactions = frappe.db.sql("""
        SELECT
            gle.posting_date,
            gle.account,
            acc.account_type,
            acc.root_type,
            acc.parent_account,
            (gle.debit - gle.credit) as amount,
            gle.voucher_type,
            gle.voucher_no,
            gle.against
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE gle.company = %s
            AND gle.posting_date BETWEEN %s AND %s
            AND acc.account_type IN ('Cash', 'Bank')
            AND gle.is_cancelled = 0
        ORDER BY gle.posting_date
    """, (intelligence.company, start_date, end_date), as_dict=True)

    weeks_data = {}

    for txn in transactions:
        posting_date = txn.posting_date
        if isinstance(posting_date, str):
            posting_date = datetime.strptime(posting_date, '%Y-%m-%d').date()

        # Find week start (Monday)
        days_since_monday = posting_date.weekday()
        week_start = posting_date - timedelta(days=days_since_monday)
        week_key = str(week_start)

        if week_key not in weeks_data:
            weeks_data[week_key] = {
                'inflows': {'ar_collections': 0, 'other_receipts': 0, 'total': 0},
                'outflows': {'ap_payments': 0, 'payroll': 0, 'operating_expenses': 0, 'taxes': 0, 'total': 0},
                'net_flow': 0
            }

        amount = float(txn.amount or 0)
        voucher_type = txn.voucher_type or ''
        against = txn.against or ''

        if amount > 0:  # Inflow (debit to cash)
            if voucher_type == 'Sales Invoice' or 'receivable' in against.lower():
                weeks_data[week_key]['inflows']['ar_collections'] += amount
            else:
                weeks_data[week_key]['inflows']['other_receipts'] += amount
            weeks_data[week_key]['inflows']['total'] += amount
        else:  # Outflow (credit from cash)
            abs_amount = abs(amount)
            if voucher_type == 'Purchase Invoice' or 'payable' in against.lower():
                weeks_data[week_key]['outflows']['ap_payments'] += abs_amount
            elif 'salary' in against.lower() or 'payroll' in against.lower() or 'wages' in against.lower():
                weeks_data[week_key]['outflows']['payroll'] += abs_amount
            elif 'tax' in against.lower() or 'vat' in against.lower() or 'paye' in against.lower():
                weeks_data[week_key]['outflows']['taxes'] += abs_amount
            else:
                weeks_data[week_key]['outflows']['operating_expenses'] += abs_amount
            weeks_data[week_key]['outflows']['total'] += abs_amount

        weeks_data[week_key]['net_flow'] = (
            weeks_data[week_key]['inflows']['total'] -
            weeks_data[week_key]['outflows']['total']
        )

    return weeks_data


def get_ar_collections_by_week(intelligence, start_date: datetime, end_date: datetime) -> Dict[str, Dict]:
    """Get expected AR collections by week based on due dates"""
    receivables = frappe.db.sql("""
        SELECT
            si.name,
            si.due_date,
            si.outstanding_amount,
            si.customer
        FROM `tabSales Invoice` si
        WHERE si.company = %s
            AND si.docstatus = 1
            AND si.outstanding_amount > 0
            AND si.due_date BETWEEN %s AND %s
        ORDER BY si.due_date
    """, (intelligence.company, start_date, end_date), as_dict=True)

    weeks = {}

    for inv in receivables:
        due_date = inv.due_date
        if isinstance(due_date, str):
            due_date = datetime.strptime(due_date, '%Y-%m-%d').date()

        # Find week start
        days_since_monday = due_date.weekday()
        week_start = due_date - timedelta(days=days_since_monday)
        week_key = str(week_start)

        if week_key not in weeks:
            weeks[week_key] = {'amount': 0, 'count': 0, 'invoices': []}

        weeks[week_key]['amount'] += float(inv.outstanding_amount or 0)
        weeks[week_key]['count'] += 1
        weeks[week_key]['invoices'].append(inv.name)

    # Also add overdue receivables to week 0 (current week)
    overdue = frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0) as total
        FROM `tabSales Invoice`
        WHERE company = %s
            AND docstatus = 1
            AND outstanding_amount > 0
            AND due_date < %s
    """, (intelligence.company, start_date), as_dict=True)[0].total or 0

    # Distribute overdue across first 4 weeks (assume gradual collection)
    if overdue > 0:
        weekly_overdue = overdue / 4
        for week_offset in range(4):
            week_date = start_date + timedelta(weeks=week_offset)
            if hasattr(week_date, 'date') and callable(week_date.date):
                week_date = week_date.date()
            # If it's already a date object, use as-is
            days_since_monday = week_date.weekday()
            week_start = week_date - timedelta(days=days_since_monday)
            week_key = str(week_start)

            if week_key not in weeks:
                weeks[week_key] = {'amount': 0, 'count': 0, 'invoices': []}
            weeks[week_key]['amount'] += weekly_overdue

    return weeks


def get_ap_payments_by_week(intelligence, start_date: datetime, end_date: datetime) -> Dict[str, Dict]:
    """Get expected AP payments by week based on due dates"""
    payables = frappe.db.sql("""
        SELECT
            pi.name,
            pi.due_date,
            pi.outstanding_amount,
            pi.supplier
        FROM `tabPurchase Invoice` pi
        WHERE pi.company = %s
            AND pi.docstatus = 1
            AND pi.outstanding_amount > 0
            AND pi.due_date BETWEEN %s AND %s
        ORDER BY pi.due_date
    """, (intelligence.company, start_date, end_date), as_dict=True)

    weeks = {}

    for inv in payables:
        due_date = inv.due_date
        if isinstance(due_date, str):
            due_date = datetime.strptime(due_date, '%Y-%m-%d').date()

        # Find week start
        days_since_monday = due_date.weekday()
        week_start = due_date - timedelta(days=days_since_monday)
        week_key = str(week_start)

        if week_key not in weeks:
            weeks[week_key] = {'amount': 0, 'count': 0, 'invoices': []}

        weeks[week_key]['amount'] += float(inv.outstanding_amount or 0)
        weeks[week_key]['count'] += 1
        weeks[week_key]['invoices'].append(inv.name)

    return weeks


def get_payroll_for_week(intelligence, week_start, payroll_pattern: Dict) -> float:
    """Get expected payroll amount for a specific week"""
    if not payroll_pattern.get('detected'):
        return 0

    if isinstance(week_start, str):
        week_start = datetime.strptime(week_start, '%Y-%m-%d').date()
    elif hasattr(week_start, 'date') and callable(week_start.date):
        week_start = week_start.date()
    # If it's already a date object, use as-is

    week_end = week_start + timedelta(days=6)
    next_payroll = payroll_pattern.get('next_date')

    if not next_payroll:
        return 0

    next_payroll_date = datetime.strptime(next_payroll, '%Y-%m-%d').date()
    frequency = payroll_pattern.get('frequency', 'monthly')
    typical_amount = payroll_pattern.get('typical_amount', 0)

    # Check if payroll falls in this week
    payroll_in_week = week_start <= next_payroll_date <= week_end

    if payroll_in_week:
        return typical_amount

    # For weekly/bi-weekly, check recurring dates
    if frequency == 'weekly':
        interval = 7
    elif frequency == 'bi-weekly':
        interval = 14
    elif frequency == 'semi-monthly':
        interval = 15
    else:  # monthly
        interval = 30

    # Check if any subsequent payroll dates fall in this week
    check_date = next_payroll_date
    max_iterations = 20  # Safety limit
    iteration = 0

    while check_date <= week_end and iteration < max_iterations:
        if week_start <= check_date <= week_end:
            return typical_amount
        check_date += timedelta(days=interval)
        iteration += 1

    return 0


def estimate_other_receipts(intelligence, week_start: datetime) -> float:
    """Estimate other receipts (non-AR) based on historical average"""
    # Get average weekly other receipts from last 12 weeks
    twelve_weeks_ago = (datetime.now() - timedelta(weeks=12)).strftime('%Y-%m-%d')

    other_receipts = frappe.db.sql("""
        SELECT COALESCE(SUM(gle.debit - gle.credit), 0) / 12 as weekly_avg
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE gle.company = %s
            AND gle.posting_date >= %s
            AND acc.account_type IN ('Cash', 'Bank')
            AND gle.is_cancelled = 0
            AND (gle.debit - gle.credit) > 0
            AND gle.voucher_type NOT IN ('Sales Invoice', 'Payment Entry')
    """, (intelligence.company, twelve_weeks_ago), as_dict=True)[0].weekly_avg or 0

    return float(other_receipts)


def estimate_operating_expenses(intelligence, week_start: datetime) -> float:
    """Estimate operating expenses based on historical average"""
    twelve_weeks_ago = (datetime.now() - timedelta(weeks=12)).strftime('%Y-%m-%d')

    operating_exp = frappe.db.sql("""
        SELECT COALESCE(ABS(SUM(gle.debit - gle.credit)), 0) / 12 as weekly_avg
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE gle.company = %s
            AND gle.posting_date >= %s
            AND acc.account_type IN ('Cash', 'Bank')
            AND gle.is_cancelled = 0
            AND (gle.debit - gle.credit) < 0
            AND gle.voucher_type NOT IN ('Purchase Invoice', 'Payment Entry')
            AND gle.against NOT LIKE '%%Salary%%'
            AND gle.against NOT LIKE '%%Payroll%%'
            AND gle.against NOT LIKE '%%Tax%%'
            AND gle.against NOT LIKE '%%VAT%%'
    """, (intelligence.company, twelve_weeks_ago), as_dict=True)[0].weekly_avg or 0

    return abs(float(operating_exp))


def get_scheduled_taxes(intelligence, week_start, week_end) -> float:
    """Get scheduled tax payments for a specific week: GST (GSTR-3B) and TDS.

    Due dates and amounts are the same real ones
    insights.ml.india_tax_intelligence uses, not a flat percentage guess:

    - GST: GSTR-3B monthly due date (20th) — the actual payment date, since
      GSTR-1 (11th) carries no tax payment. QRMP (quarterly) filers are due
      the 22nd/24th depending on state group; that split is not applied here
      because this codebase has no verified state-to-group source, and on
      this site GST Return Log shows the company filing GSTR-3B monthly
      (consecutive month-over-month periods), the more common case above the
      QRMP turnover threshold. Amount is net GST (output tax − input tax
      credit) actually posted for the prior calendar month, floored at 0 —
      a negative position is ITC carried forward, not a cash inflow.
    - TDS: due the 7th of the following month (Sec 200(1), Income Tax Act,
      non-government deductors). The March-deducted-TDS exception (due 30
      April, not 7 April) is not modelled — a single month a year in a
      rolling forecast. Amount is the real TDS payable-by-section total for
      the prior calendar month.

    Returns 0 if india_compliance is not installed, rather than falling back
    to an estimate with no real filing/ledger data behind it.
    """
    if isinstance(week_start, str):
        week_start = datetime.strptime(week_start, '%Y-%m-%d').date()
    elif hasattr(week_start, 'date') and callable(week_start.date):
        week_start = week_start.date()
    if isinstance(week_end, str):
        week_end = datetime.strptime(week_end, '%Y-%m-%d').date()
    elif hasattr(week_end, 'date') and callable(week_end.date):
        week_end = week_end.date()

    from insights.ml.india_tax_intelligence.data import (
        check_india_compliance_installed,
        get_gst_output_tax,
        get_gst_input_tax,
        get_tds_summary,
        GST_DUE_DATES,
    )

    if not check_india_compliance_installed():
        return 0.0

    gst_due_day = GST_DUE_DATES.get("gstr3b_monthly_day", 20)
    tds_due_day = 7

    tax_amount = 0.0

    for day in range((week_end - week_start).days + 1):
        check_date = week_start + timedelta(days=day)
        prev_month_end = check_date.replace(day=1) - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)

        if check_date.day == gst_due_day:
            output_rows = get_gst_output_tax(intelligence, str(prev_month_start), str(prev_month_end))
            input_rows = get_gst_input_tax(intelligence, str(prev_month_start), str(prev_month_end))
            output_total = sum(
                float(r.get(c, 0) or 0) for r in output_rows for c in ('cgst', 'sgst', 'igst', 'cess')
            )
            input_total = sum(
                float(r.get(c, 0) or 0) for r in input_rows for c in ('cgst', 'sgst', 'igst', 'cess')
            )
            tax_amount += max(0.0, output_total - input_total)

        if check_date.day == tds_due_day:
            tds = get_tds_summary(intelligence, str(prev_month_start), str(prev_month_end))
            tax_amount += float(tds.get('total_payable', 0) or 0)

    return round(tax_amount, 2)


def get_original_forecast_for_week(intelligence, week_key: str) -> Optional[Dict]:
    """Get the original forecast for a week (for variance calculation)"""
    # This would typically come from a stored forecast
    # For now, return None as we don't have historical forecasts stored
    cache_key = f"thirteen_week_forecast_{intelligence.company}_{week_key}"
    cached = frappe.cache().get_value(cache_key)
    return cached


def get_week_label(intelligence, week_start: datetime, week_num: int) -> str:
    """Generate a readable label for the week"""
    if isinstance(week_start, str):
        week_start = datetime.strptime(week_start, '%Y-%m-%d')
    elif isinstance(week_start, datetime):
        pass
    else:
        week_start = datetime.combine(week_start, datetime.min.time())

    if week_num == -1:
        return "Last Week"
    elif week_num == 0:
        return "This Week"
    elif week_num == 1:
        return "Next Week"
    else:
        return week_start.strftime('%b %d')

