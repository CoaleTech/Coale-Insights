from __future__ import annotations
# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Cost structure ratios and expense forecasting for Strategic Finance
Intelligence.

Grades salary, fixed-cost, and named opex categories (Marketing, Training &
Development, Incentives/Increment/Appraisal, Rent, Electricity) against
configurable ideal/risky thresholds from `Insights Settings`, and forecasts
total monthly expenses from a simple linear trend.

Every figure is queried fresh from GL Entry per call; nothing is cached or
estimated. A ratio that cannot be computed (e.g. no COGS accounts posted this
period, so gross profit is unknown) is reported as such rather than guessed —
matching the convention in `summary.py`'s gross margin calculation.
"""

import frappe
from frappe import _
from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import Abs, Coalesce, DateFormat, Sum
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Dict, Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np



# ─── Account category matching ─────────────────────────────────────────────

def _parse_keywords(raw: Optional[str], default: List[str]) -> List[str]:
    """One keyword per line in the Settings field; falls back to `default`
    when the admin has not configured (or has cleared) the field."""
    if not raw or not str(raw).strip():
        return default
    return [line.strip() for line in str(raw).split("\n") if line.strip()]


def _category_total(company: str, start: str, end: str, keywords: List[str]) -> float:
    """Sum GL Entry postings to Expense accounts whose name matches any
    keyword (case-insensitive substring), for the given period."""
    if not keywords:
        return 0.0
    gle = DocType("GL Entry")
    acc = DocType("Account")

    # Build an OR-combined name-LIKE filter for each keyword.
    combined_filter = acc.name.like(f"%{keywords[0]}%")
    for kw in keywords[1:]:
        combined_filter = combined_filter | acc.name.like(f"%{kw}%")

    rows = (
        frappe.qb.from_(gle)
        .join(acc)
        .on(gle.account == acc.name)
        .select(Coalesce(Sum(Abs(gle.debit - gle.credit)), 0).as_("amount"))
        .where(acc.root_type == "Expense")
        .where(gle.company == company)
        .where(gle.posting_date.between(start, end))
        .where(gle.is_cancelled == 0)
        .where(combined_filter)
        .run(as_dict=True)
    )
    return float(rows[0].amount or 0) if rows else 0.0


def _get_fixed_cost(company: str, start: str, end: str, settings) -> float:
    """Sum GL Entry postings against the cost centers the admin has marked
    Fixed in Insights Settings (same field `breakeven_engine.py` uses)."""
    raw = getattr(settings, "fixed_cost_centers", None)
    if not raw or not str(raw).strip():
        return 0.0
    centers = [c.strip() for c in str(raw).split("\n") if c.strip()]
    if not centers:
        return 0.0
    gle = DocType("GL Entry")
    acc = DocType("Account")
    rows = (
        frappe.qb.from_(gle)
        .join(acc)
        .on(gle.account == acc.name)
        .select(Coalesce(Sum(Abs(gle.debit - gle.credit)), 0).as_("amount"))
        .where(acc.root_type == "Expense")
        .where(gle.company == company)
        .where(gle.posting_date.between(start, end))
        .where(gle.is_cancelled == 0)
        .where(gle.cost_center.isin(centers))
        .run(as_dict=True)
    )
    return float(rows[0].amount or 0) if rows else 0.0


def _root_type_sum(company: str, start: str, end: str, root_type: str) -> float:
    """Sum of GL Entry postings against accounts of a given root_type
    (Income or Expense) for the period. Mirrors the legacy SQL
    `COALESCE(SUM(ABS(credit - debit)), 0)` for Income (credit-normal)
    and `COALESCE(SUM(ABS(debit - credit)), 0)` for Expense (debit-normal)."""
    gle = DocType("GL Entry")
    acc = DocType("Account")
    expr = (
        Abs(gle.credit - gle.debit)
        if root_type == "Income"
        else Abs(gle.debit - gle.credit)
    )
    rows = (
        frappe.qb.from_(gle)
        .join(acc)
        .on(gle.account == acc.name)
        .select(Coalesce(Sum(expr), 0).as_("amount"))
        .where(acc.root_type == root_type)
        .where(gle.posting_date.between(start, end))
        .where(gle.company == company)
        .where(gle.is_cancelled == 0)
        .run(as_dict=True)
    )
    return float(rows[0].amount or 0) if rows else 0.0


def _cogs_total(company: str, start: str, end: str) -> float:
    """Same shape as `_root_type_sum` for Expense, restricted to COGS
    accounts (by `account_type = 'Cost of Goods Sold'` or by name match)."""
    gle = DocType("GL Entry")
    acc = DocType("Account")
    name_filter = acc.name.like("%Cost of Goods%") | acc.name.like("%COGS%")
    type_filter = acc.account_type == "Cost of Goods Sold"
    rows = (
        frappe.qb.from_(gle)
        .join(acc)
        .on(gle.account == acc.name)
        .select(Coalesce(Sum(Abs(gle.debit - gle.credit)), 0).as_("amount"))
        .where((type_filter | name_filter) & (acc.root_type == "Expense"))
        .where(gle.posting_date.between(start, end))
        .where(gle.company == company)
        .where(gle.is_cancelled == 0)
        .run(as_dict=True)
    )
    return float(rows[0].amount or 0) if rows else 0.0


def _revenue_and_profit(company: str, start: str, end: str) -> tuple:
    """Revenue, gross profit (None if no COGS accounts posted), net profit —
    same GL convention as `summary.py:calculate_executive_summary`."""
    revenue = _root_type_sum(company, start, end, "Income")
    expenses = _root_type_sum(company, start, end, "Expense")
    cogs = _cogs_total(company, start, end)
    net_profit = revenue - expenses
    gross_profit = (revenue - cogs) if (cogs > 0 and revenue > 0) else None
    return revenue, gross_profit, net_profit


# ─── Classification + recommendations ──────────────────────────────────────

def _classify(value: float, ideal: float, risky: float, higher_is_better: bool) -> str:
    if higher_is_better:
        if value >= ideal:
            return "good"
        if value < risky:
            return "risky"
        return "moderate"
    if value <= ideal:
        return "good"
    if value > risky:
        return "risky"
    return "moderate"


# Plain-English action per ratio per status. `{value}`/`{ideal}`/`{risky}` are
# formatted by `_build_card` to match the card's unit (x or %).
_RECOMMENDATIONS = {
    "gp_salary": {
        "good": "Gross profit comfortably covers salary costs ({value}, target \u2265{ideal}). Payroll is sustainable at current margins.",
        "moderate": "Gross profit covers salary at {value}, below the {ideal} target but above the {risky} risk line. Watch margin trends before adding headcount.",
        "risky": "Gross profit only covers salary {value}, under the {risky} risk threshold. Salary is consuming too much of gross margin \u2014 review pricing, COGS, or staffing levels before the next hire or increment.",
    },
    "np_salary": {
        "good": "Net profit is {value} salary (target \u2265{ideal}) \u2014 payroll is well within what the business earns after all costs.",
        "moderate": "Net profit covers salary at {value}, below the {ideal} target. Profitability is thin relative to payroll \u2014 monitor before further pay increases.",
        "risky": "Net profit covers salary only {value}, below the {risky} risk line. The business is not generating enough bottom-line profit to sustain current payroll \u2014 freeze increments and review cost structure.",
    },
    "fixed_cost_np": {
        "good": "Fixed costs are {value} net profit (target \u2264{ideal}) \u2014 overhead is well covered by earnings.",
        "moderate": "Fixed costs are {value} net profit, above the {ideal} target. Overhead is starting to crowd out profit \u2014 review recurring commitments.",
        "risky": "Fixed costs are {value} net profit, above the {risky} risk line. Overhead is disproportionate to earnings \u2014 renegotiate leases/contracts or grow margin before adding fixed commitments.",
    },
    "fixed_cost_gp": {
        "good": "Fixed costs are {value} gross profit (target \u2264{ideal}) \u2014 healthy buffer between overhead and gross margin.",
        "moderate": "Fixed costs are {value} gross profit, above the {ideal} target. Gross margin is being eroded by overhead faster than ideal.",
        "risky": "Fixed costs are {value} gross profit, above the {risky} risk line. Overhead is consuming most of the gross margin \u2014 cut discretionary fixed spend or raise prices.",
    },
    "marketing": {
        "good": "Marketing spend is {value} of revenue (target \u2264{ideal}) \u2014 within a healthy range.",
        "moderate": "Marketing spend is {value} of revenue, above the {ideal} target. Review channel ROI before the next campaign.",
        "risky": "Marketing spend is {value} of revenue, above the {risky} risk line. Spend is outpacing what revenue supports \u2014 audit campaign ROI and reallocate budget to the best-converting channels.",
    },
    "training": {
        "good": "Training & development spend is {value} of revenue (target \u2264{ideal}) \u2014 sustainable investment level.",
        "moderate": "Training spend is {value} of revenue, above the {ideal} target. Confirm the training calendar is tied to measurable skill or output gains.",
        "risky": "Training spend is {value} of revenue, above the {risky} risk line. Re-scope the training budget against actual ROI before committing further spend.",
    },
    "incentive": {
        "good": "Incentives, increments & appraisals cost {value} of revenue (target \u2264{ideal}) \u2014 compensation growth is in line with revenue.",
        "moderate": "Incentive/increment spend is {value} of revenue, above the {ideal} target. Tie the next appraisal cycle to performance metrics before approving further increases.",
        "risky": "Incentive/increment spend is {value} of revenue, above the {risky} risk line. Compensation growth is outpacing revenue \u2014 freeze discretionary increments until margins recover.",
    },
    "rent": {
        "good": "Rent is {value} of revenue (target \u2264{ideal}) \u2014 occupancy cost is under control.",
        "moderate": "Rent is {value} of revenue, above the {ideal} target. Evaluate space utilisation before the next lease renewal.",
        "risky": "Rent is {value} of revenue, above the {risky} risk line. Occupancy cost is a significant drag \u2014 renegotiate the lease or consider relocating/downsizing.",
    },
    "electricity": {
        "good": "Electricity is {value} of revenue (target \u2264{ideal}) \u2014 utility cost is efficient.",
        "moderate": "Electricity is {value} of revenue, above the {ideal} target. Audit peak-demand usage and equipment efficiency.",
        "risky": "Electricity is {value} of revenue, above the {risky} risk line. Utility cost is eating into margin \u2014 investigate an energy audit or tariff renegotiation.",
    },
}


def _fmt(value: float, unit: str) -> str:
    return f"{value:.1f}%" if unit == "%" else f"{value:.2f}x"


def _build_card(
    key: str, name: str, value: Optional[float],
    ideal: float, risky: float, higher_is_better: bool, unit: str,
) -> Dict[str, Any]:
    if value is None:
        return {
            "key": key, "name": name, "value": None,
            "ideal": ideal, "risky": risky, "unit": unit,
            "higher_is_better": higher_is_better, "status": "unknown",
            "recommendation": "Not enough data to assess \u2014 no activity recorded against the underlying accounts for this period.",
        }
    status = _classify(value, ideal, risky, higher_is_better)
    recommendation = _RECOMMENDATIONS[key][status].format(
        value=_fmt(value, unit), ideal=_fmt(ideal, unit), risky=_fmt(risky, unit),
    )
    return {
        "key": key, "name": name, "value": round(value, 2),
        "ideal": ideal, "risky": risky, "unit": unit,
        "higher_is_better": higher_is_better, "status": status,
        "recommendation": recommendation,
    }


# ─── Main entry point ───────────────────────────────────────────────────────

def calculate_cost_structure_ratios(intelligence) -> Dict[str, Any]:
    """Cost structure ratios for the current fiscal year to date: salary,
    fixed cost, and five named opex categories, each graded good/moderate/
    risky against `Insights Settings` thresholds with a plain-English action."""
    fy_start = intelligence.fiscal_year["start_date"]
    today = datetime.now().strftime('%Y-%m-%d')
    company = intelligence.company

    settings = frappe.get_cached_doc("Insights Settings")

    def threshold(fieldname: str, default: float) -> float:
        val = getattr(settings, fieldname, None)
        try:
            return float(val) if val not in (None, "") else default
        except (TypeError, ValueError):
            return default

    revenue, gross_profit, net_profit = _revenue_and_profit(company, fy_start, today)

    salary_kw = _parse_keywords(getattr(settings, "salary_cost_keywords", None), ["Salary", "Payroll", "Wages"])
    marketing_kw = _parse_keywords(getattr(settings, "marketing_cost_keywords", None), ["Marketing", "Advertising", "Promotion", "Branding"])
    training_kw = _parse_keywords(getattr(settings, "training_cost_keywords", None), ["Training", "Development", "Learning"])
    incentive_kw = _parse_keywords(getattr(settings, "incentive_cost_keywords", None), ["Incentive", "Bonus", "Commission", "Appraisal", "Increment"])
    rent_kw = _parse_keywords(getattr(settings, "rent_cost_keywords", None), ["Rent", "Lease"])
    electricity_kw = _parse_keywords(getattr(settings, "electricity_cost_keywords", None), ["Electricity", "Power", "Utilities", "Utility"])

    salary_cost = _category_total(company, fy_start, today, salary_kw)
    marketing_cost = _category_total(company, fy_start, today, marketing_kw)
    training_cost = _category_total(company, fy_start, today, training_kw)
    incentive_cost = _category_total(company, fy_start, today, incentive_kw)
    rent_cost = _category_total(company, fy_start, today, rent_kw)
    electricity_cost = _category_total(company, fy_start, today, electricity_kw)
    fixed_cost = _get_fixed_cost(company, fy_start, today, settings)

    cards = [
        _build_card(
            "gp_salary", "Gross Profit / Salary",
            (gross_profit / salary_cost) if (gross_profit is not None and salary_cost > 0) else None,
            threshold("gp_salary_ideal", 3.0), threshold("gp_salary_risky", 1.5),
            higher_is_better=True, unit="x",
        ),
        _build_card(
            "np_salary", "Net Profit / Salary",
            (net_profit / salary_cost) if salary_cost > 0 else None,
            threshold("np_salary_ideal", 1.0), threshold("np_salary_risky", 0.3),
            higher_is_better=True, unit="x",
        ),
        _build_card(
            "fixed_cost_np", "Fixed Cost / Net Profit",
            (fixed_cost / net_profit) if net_profit > 0 else None,
            threshold("fixed_cost_np_ideal", 0.5), threshold("fixed_cost_np_risky", 1.5),
            higher_is_better=False, unit="x",
        ),
        _build_card(
            "fixed_cost_gp", "Fixed Cost / Gross Profit",
            (fixed_cost / gross_profit) if (gross_profit is not None and gross_profit > 0) else None,
            threshold("fixed_cost_gp_ideal", 0.4), threshold("fixed_cost_gp_risky", 0.8),
            higher_is_better=False, unit="x",
        ),
        _build_card(
            "marketing", "Marketing Cost % of Revenue",
            (marketing_cost / revenue * 100) if revenue > 0 else None,
            threshold("marketing_pct_ideal", 8.0), threshold("marketing_pct_risky", 15.0),
            higher_is_better=False, unit="%",
        ),
        _build_card(
            "training", "Training & Development % of Revenue",
            (training_cost / revenue * 100) if revenue > 0 else None,
            threshold("training_pct_ideal", 3.0), threshold("training_pct_risky", 6.0),
            higher_is_better=False, unit="%",
        ),
        _build_card(
            "incentive", "Incentives/Increment/Appraisal % of Revenue",
            (incentive_cost / revenue * 100) if revenue > 0 else None,
            threshold("incentive_pct_ideal", 5.0), threshold("incentive_pct_risky", 10.0),
            higher_is_better=False, unit="%",
        ),
        _build_card(
            "rent", "Rent % of Revenue",
            (rent_cost / revenue * 100) if revenue > 0 else None,
            threshold("rent_pct_ideal", 8.0), threshold("rent_pct_risky", 15.0),
            higher_is_better=False, unit="%",
        ),
        _build_card(
            "electricity", "Electricity % of Revenue",
            (electricity_cost / revenue * 100) if revenue > 0 else None,
            threshold("electricity_pct_ideal", 3.0), threshold("electricity_pct_risky", 6.0),
            higher_is_better=False, unit="%",
        ),
    ]

    overall_status = "good"
    for c in cards:
        if c["status"] == "risky":
            overall_status = "risky"
            break
        if c["status"] == "moderate" and overall_status == "good":
            overall_status = "moderate"

    return {
        "period": {"start": fy_start, "end": today},
        "figures": {
            "revenue": revenue,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "fixed_cost": fixed_cost,
            "salary_cost": salary_cost,
            "marketing_cost": marketing_cost,
            "training_cost": training_cost,
            "incentive_cost": incentive_cost,
            "rent_cost": rent_cost,
            "electricity_cost": electricity_cost,
        },
        "overall_status": overall_status,
        "ratio_cards": cards,
    }


# ─── Expense forecast ───────────────────────────────────────────────────────

def forecast_expenses(intelligence, periods: int = 3) -> Dict[str, Any]:
    """Linear-trend forecast of total monthly expenses for the next
    `periods` months, from the trailing complete months (up to 6) of GL
    actuals. Returns `status: "insufficient_data"` rather than fabricating a
    trend from fewer than 3 complete months — the current, still-open month
    is always excluded so a partial month never drags the trend down."""
    import numpy as np
    company = intelligence.company

    gle = DocType("GL Entry")
    acc = DocType("Account")
    # Anchor on a Python-side date so PyPika emits a literal bound parameter
    # rather than DATE_SUB(CURDATE(), INTERVAL ...) server-side, which is
    # not expressible in the query builder. Equivalent semantics.
    thirteen_months_ago = (datetime.now() - timedelta_weeks(13 * 4 + 1)).strftime('%Y-%m-%d')
    month_expr = DateFormat(gle.posting_date, "%Y-%m").as_("month")

    rows = (
        frappe.qb.from_(gle)
        .join(acc)
        .on(gle.account == acc.name)
        .select(
            month_expr,
            Coalesce(Sum(Abs(gle.debit - gle.credit)), 0).as_("amount"),
        )
        .where(acc.root_type == "Expense")
        .where(gle.company == company)
        .where(gle.posting_date >= thirteen_months_ago)
        .where(gle.is_cancelled == 0)
        .groupby(month_expr)
        .orderby(month_expr)
        .run(as_dict=True)
    )

    current_month = datetime.now().strftime('%Y-%m')
    history = [{"month": r.month, "amount": float(r.amount or 0)} for r in rows if r.month != current_month]

    if len(history) < 3:
        return {
            "status": "insufficient_data",
            "message": _("Need at least 3 complete months of expense history to forecast."),
            "history": history,
        }

    window = history[-6:]
    x = np.arange(len(window))
    y = np.array([h["amount"] for h in window])
    slope, intercept = np.polyfit(x, y, 1)

    last_month = datetime.strptime(window[-1]["month"], '%Y-%m')
    forecast = []
    for i in range(1, periods + 1):
        fx = len(window) - 1 + i
        projected = max(0.0, float(slope * fx + intercept))
        target_month = last_month + relativedelta(months=i)
        forecast.append({
            "month": target_month.strftime('%Y-%m'),
            "projected_amount": round(projected, 2),
        })

    avg_recent = float(np.mean(y)) or 1.0
    if slope > avg_recent * 0.02:
        trend_direction = "rising"
    elif slope < -avg_recent * 0.02:
        trend_direction = "falling"
    else:
        trend_direction = "flat"

    return {
        "status": "success",
        "method": "linear_trend",
        "window_months": len(window),
        "history": history,
        "forecast": forecast,
        "trend_direction": trend_direction,
        "monthly_change": round(float(slope), 2),
        "note": f"Projected from a linear trend over the last {len(window)} complete months. Not seasonally adjusted.",
    }


def timedelta_weeks(weeks: int):
    """Local helper — equivalent to datetime.timedelta(weeks=...)."""
    from datetime import timedelta
    return timedelta(weeks=weeks)
