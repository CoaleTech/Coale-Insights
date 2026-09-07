# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Executive summary and key insights generation for Strategic Finance Intelligence.
"""

import frappe
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from frappe.query_builder import DocType
from frappe.query_builder.functions import Abs, Coalesce, Sum

from .data import get_cash_balance, get_monthly_financial_trends


def _gl_account_root_type_total(
    company: str,
    root_type: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    extra_account_filter=None,
    apply_abs: bool = True,
) -> float:
    """Sum GL Entry postings against accounts of the given root_type.

    `extra_account_filter` is an optional PyPika criterion applied to the
    Account table (e.g. for COGS or interest matches). When `apply_abs` is
    True, the result is `ABS(debit - credit)`, matching the legacy raw-SQL
    convention; otherwise the raw signed sum is returned.
    """
    gle = DocType("GL Entry")
    acc = DocType("Account")

    expr = Abs(gle.debit - gle.credit) if apply_abs else (gle.debit - gle.credit)
    query = (
        frappe.qb.from_(gle)
        .join(acc)
        .on(gle.account == acc.name)
        .select(Coalesce(Sum(expr), 0).as_("amount"))
        .where(acc.root_type == root_type)
        .where(gle.company == company)
        .where(gle.is_cancelled == 0)
    )
    if start_date and end_date:
        query = query.where(gle.posting_date.between(start_date, end_date))
    elif start_date:
        query = query.where(gle.posting_date >= start_date)
    elif end_date:
        query = query.where(gle.posting_date <= end_date)
    if extra_account_filter is not None:
        query = query.where(extra_account_filter)

    rows = query.run(as_dict=True)
    return float(rows[0].amount or 0) if rows else 0.0


def calculate_executive_summary(intelligence) -> Dict[str, Any]:
    """Calculate executive-level KPIs and trends"""
    fy_start = intelligence.fiscal_year["start_date"]
    today = datetime.now().strftime('%Y-%m-%d')
    company = intelligence.company

    # YTD Revenue
    ytd_revenue = _gl_account_root_type_total(
        company=company, root_type="Income", start_date=fy_start, end_date=today
    )

    # YTD Expenses
    ytd_expenses = _gl_account_root_type_total(
        company=company, root_type="Expense", start_date=fy_start, end_date=today
    )

    # YTD Net Income
    ytd_net_income = ytd_revenue - ytd_expenses
    net_margin = (ytd_net_income / ytd_revenue * 100) if ytd_revenue > 0 else 0

    # YTD Interest and Depreciation for EBITDA. Same account-matching
    # convention as `calculate_ratio_trends` (analysis.py) -- interest by
    # name (this CoA tags no account_type for borrowing costs), depreciation
    # by `account_type = 'Depreciation'` -- so EBITDA means the same thing
    # on the Executive Summary as it does on the Ratios tab. No tax
    # add-back: this CoA carries no income-tax / provision-for-tax account
    # distinct from indirect taxes (customs duty, GST) that are real
    # operating costs.
    acc = DocType("Account")
    ytd_interest_expense = _gl_account_root_type_total(
        company=company,
        root_type="Expense",
        start_date=fy_start,
        end_date=today,
        extra_account_filter=acc.name.like("%Interest%"),
    )

    gle = DocType("GL Entry")
    dep_rows = (
        frappe.qb.from_(gle)
        .join(acc)
        .on(gle.account == acc.name)
        .select(Coalesce(Sum(Abs(gle.debit - gle.credit)), 0).as_("amount"))
        .where(acc.account_type == "Depreciation")
        .where(gle.posting_date.between(fy_start, today))
        .where(gle.company == company)
        .where(gle.is_cancelled == 0)
        .run(as_dict=True)
    )
    ytd_depreciation = float(dep_rows[0].amount or 0) if dep_rows else 0.0

    ytd_ebit = ytd_net_income + ytd_interest_expense
    ytd_ebitda = ytd_ebit + ytd_depreciation
    ebitda_margin = (ytd_ebitda / ytd_revenue * 100) if ytd_revenue > 0 else None

    # YTD Cost of Goods Sold (COGS) for Gross Margin calculation
    cogs_filter = (
        (acc.account_type == "Cost of Goods Sold")
        | acc.name.like("%Cost of Goods%")
        | acc.name.like("%COGS%")
    ) & (acc.root_type == "Expense")
    ytd_cogs = _gl_account_root_type_total(
        company=company,
        root_type="Expense",
        start_date=fy_start,
        end_date=today,
        extra_account_filter=cogs_filter,
    )

    # Gross Margin = (Revenue - COGS) / Revenue * 100
    # When COGS is zero or no COGS accounts post entries, both figures are absent —
    # never estimate (removing the previous "* 0.7" fallback which invented a 70% margin).
    if ytd_cogs > 0 and ytd_revenue > 0:
        gross_profit = ytd_revenue - ytd_cogs
        gross_margin = gross_profit / ytd_revenue * 100
    else:
        gross_profit = None
        gross_margin = None

    # Prior Year Same Period for Growth
    prior_fy_start = (datetime.strptime(fy_start, '%Y-%m-%d') - timedelta(days=365)).strftime('%Y-%m-%d')
    prior_today = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    prior_revenue = _gl_account_root_type_total(
        company=company, root_type="Income", start_date=prior_fy_start, end_date=prior_today
    )

    # Return None when the YoY comparison is not meaningful:
    #   - prior_revenue == 0: division undefined, currently returns 0 which reads as "flat"
    #   - prior_revenue < 10% of ytd_revenue: base is too small for the ratio to be informative
    #     (e.g. ≥900% growth); such extremes usually reflect incomplete prior-year data rather
    #     than real performance — a governance dashboard must not show them as facts.
    if prior_revenue > 0 and prior_revenue >= ytd_revenue * 0.10:
        revenue_growth = (ytd_revenue - prior_revenue) / prior_revenue * 100
    else:
        revenue_growth = None

    # Cash Position
    cash_balance = get_cash_balance(intelligence)

    # Monthly Burn Rate (average of last 3 months expenses)
    three_months_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    monthly_expenses_total = _gl_account_root_type_total(
        company=company, root_type="Expense", start_date=three_months_ago
    )
    monthly_expenses = monthly_expenses_total / 3 if monthly_expenses_total else 0

    # Cash Runway
    cash_runway_months = (cash_balance / monthly_expenses) if monthly_expenses > 0 else 999

    # Total Assets, Liabilities, Equity from GL Entry (balance-sheet items
    # are point-in-time balances, not period-scoped; no `posting_date`
    # filter, but cancelled entries excluded). Filter to leaf accounts
    # (`is_group = 0`) -- otherwise the parent "Current Assets" / "Fixed
    # Liabilities" totals double-count their own children's balances (the
    # parent's `debit - credit` IS the sum of its leaves'). The previous
    # code used `tabAsset.purchase_amount` for assets (gross book value
    # only, and missing entirely on benches where the Asset doctype isn't
    # used -- e.g. this `jkm` bench shows `total_assets: 0` despite ~3.4
    # Cr of leaf-account assets in GL) and `SUM(ABS(credit - debit))` for
    # liabilities/equity (which sums gross activity on each row rather
    # than the actual balance; on `jkm` the liability total was inflated
    # ~31x to ~94 Cr when the real leaf-account balance is ~3 Cr).
    total_assets = _gl_account_root_type_total(
        company=company, root_type="Asset", extra_account_filter=acc.is_group == 0, apply_abs=False
    )

    # Total Liabilities (credit-normal balance: credit - debit). The shared
    # helper's non-abs branch always computes debit - credit (correct for
    # debit-normal Assets); negate it here for this credit-normal root type.
    total_liabilities = -_gl_account_root_type_total(
        company=company, root_type="Liability", extra_account_filter=acc.is_group == 0, apply_abs=False
    )

    # Equity (credit-normal balance, same shape as liabilities).
    total_equity = -_gl_account_root_type_total(
        company=company, root_type="Equity", apply_abs=False
    )

    # ROE and ROA. Use max(0, balance) so a contra-balance (negative
    # liabilities/equity) reads as zero rather than a negative ratio --
    # e.g. an over-paid supplier with `credit - debit = -50000` for that
    # account would otherwise show negative liabilities and a negative
    # debt/equity ratio, both nonsensical.
    roe = (ytd_net_income / max(0.0, total_equity) * 100) if max(0.0, total_equity) > 0 else 0
    roa = (ytd_net_income / max(0.0, total_assets) * 100) if max(0.0, total_assets) > 0 else 0

    # Debt to Equity
    debt_to_equity = (max(0.0, total_liabilities) / max(0.0, total_equity)) if max(0.0, total_equity) > 0 else 0


    # Monthly trends (last 12 months)
    monthly_trends = get_monthly_financial_trends(intelligence)

    # Calculate Health Scores
    health_scores = calculate_health_scores(
        intelligence,
        net_margin=net_margin,
        roe=roe,
        roa=roa,
        debt_to_equity=debt_to_equity,
        cash_runway_months=cash_runway_months,
        revenue_growth=revenue_growth
    )

    # Generate Key Executive Insights
    key_insights = generate_key_insights(
        intelligence,
        ytd_revenue=ytd_revenue,
        ytd_net_income=ytd_net_income,
        net_margin=net_margin,
        revenue_growth=revenue_growth,
        cash_runway_months=cash_runway_months,
        debt_to_equity=debt_to_equity,
        roe=roe,
        health_scores=health_scores
    )

    return {
        "ytd_revenue": ytd_revenue,
        "ytd_expenses": ytd_expenses,
        "ytd_cogs": ytd_cogs,
        "gross_profit": gross_profit,
        "gross_margin": round(gross_margin, 2) if gross_margin is not None else None,
        "ytd_net_income": ytd_net_income,
        "net_margin": round(net_margin, 2),
        "ytd_ebitda": round(ytd_ebitda, 2),
        "ebitda_margin": round(ebitda_margin, 2) if ebitda_margin is not None else None,
        "revenue_growth_yoy": round(revenue_growth, 2) if revenue_growth is not None else None,
        "revenue_growth": round(revenue_growth, 2) if revenue_growth is not None else None,  # alias for frontend compatibility
        # Exposed so a suppressed percentage is disclosed rather than concealed.
        # Withholding the ratio is right -- 1554% off a 6% base is not a
        # performance signal -- but hiding the change altogether would be its own
        # form of under-reporting. The frontend states the base instead, and the
        # reader discounts it themselves.
        "prior_period_revenue": prior_revenue,
        "prior_period_start": prior_fy_start,
        "cash_balance": cash_balance,
        "cash_runway_months": round(cash_runway_months, 1),
        "monthly_burn_rate": monthly_expenses,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "roe": round(roe, 2),
        "roa": round(roa, 2),
        "debt_to_equity": round(debt_to_equity, 2),
        "monthly_trends": monthly_trends,
        "health_scores": health_scores,
        "key_insights": key_insights,
        "kpis": [
            {"label": "Total Revenue", "value": ytd_revenue, "format": "currency", "subtitle": "Year to Date", "trend": round(revenue_growth, 1) if revenue_growth is not None else None},
            {"label": "Net Profit", "value": ytd_net_income, "format": "currency", "subtitle": f"{net_margin:.1f}% margin"},
            {"label": "EBITDA", "value": ytd_ebitda, "format": "currency", "subtitle": f"{ebitda_margin:.1f}% margin" if ebitda_margin is not None else "Year to Date"},
            {"label": "Gross Margin", "value": gross_margin, "format": "percent", "subtitle": "Revenue - COGS"},
            {"label": "Revenue Growth", "value": revenue_growth, "format": "percent", "subtitle": "YoY"},
            {"label": "Cash Position", "value": cash_balance, "format": "currency", "subtitle": f"{cash_runway_months:.0f} months runway"},
            {"label": "ROE", "value": roe, "format": "percent", "subtitle": "Return on Equity"}
        ]
    }


def calculate_health_scores(intelligence, net_margin: float, roe: float, roa: float,
                            debt_to_equity: float, cash_runway_months: float,
                            revenue_growth: Optional[float]) -> Dict[str, Any]:
    """Calculate financial health scores (0-100) for liquidity, profitability, and efficiency"""

    # Liquidity Score (based on cash runway and debt ratio)
    liquidity_score = 0
    if cash_runway_months >= 12:
        liquidity_score = 90
    elif cash_runway_months >= 6:
        liquidity_score = 70
    elif cash_runway_months >= 3:
        liquidity_score = 50
    else:
        liquidity_score = 30

    # Adjust for debt level
    if debt_to_equity < 0.5:
        liquidity_score = min(100, liquidity_score + 10)
    elif debt_to_equity > 2:
        liquidity_score = max(0, liquidity_score - 20)

    liquidity_status = "Excellent" if liquidity_score >= 80 else "Good" if liquidity_score >= 60 else "Fair" if liquidity_score >= 40 else "Poor"

    # Profitability Score (based on net margin and ROE)
    profitability_score = 0
    if net_margin >= 20:
        profitability_score = 90
    elif net_margin >= 10:
        profitability_score = 70
    elif net_margin >= 5:
        profitability_score = 55
    elif net_margin > 0:
        profitability_score = 40
    else:
        profitability_score = 20

    # Boost for strong ROE
    if roe >= 15:
        profitability_score = min(100, profitability_score + 10)
    elif roe < 5:
        profitability_score = max(0, profitability_score - 10)

    profitability_status = "Excellent" if profitability_score >= 80 else "Good" if profitability_score >= 60 else "Fair" if profitability_score >= 40 else "Poor"

    # Efficiency Score (based on ROA and revenue growth)
    efficiency_score = 0
    if roa >= 10:
        efficiency_score = 85
    elif roa >= 5:
        efficiency_score = 65
    elif roa >= 2:
        efficiency_score = 50
    else:
        efficiency_score = 35

    # Boost for revenue growth
    if revenue_growth is not None:
        if revenue_growth >= 20:
            efficiency_score = min(100, efficiency_score + 10)
        elif revenue_growth < 0:
            efficiency_score = max(0, efficiency_score - 10)

    efficiency_status = "Excellent" if efficiency_score >= 80 else "Good" if efficiency_score >= 60 else "Fair" if efficiency_score >= 40 else "Poor"

    overall_score = round((liquidity_score + profitability_score + efficiency_score) / 3, 1)

    return {
        "overall_score": overall_score,
        "liquidity": {"score": liquidity_score, "status": liquidity_status},
        "profitability": {"score": profitability_score, "status": profitability_status},
        "efficiency": {"score": efficiency_score, "status": efficiency_status},
    }


def generate_key_insights(intelligence, ytd_revenue: float, ytd_net_income: float,
                          net_margin: float, revenue_growth: Optional[float],
                          cash_runway_months: float, debt_to_equity: float,
                          roe: float, health_scores: Dict) -> List[Dict]:
    """Generate actionable executive insights based on financial metrics"""
    insights = []

    # Revenue insights
    if revenue_growth is not None and revenue_growth > 20:
        insights.append({
            "type": "positive",
            "category": "revenue",
            "title": "Strong Revenue Growth",
            "description": f"Revenue grew {revenue_growth:.1f}% year-over-year",
            "recommendation": "Scale operations to capture growth momentum",
            "priority": "high"
        })
    elif revenue_growth is not None and revenue_growth < -10:
        insights.append({
            "type": "negative",
            "category": "revenue",
            "title": "Declining Revenue",
            "description": f"Revenue declined {abs(revenue_growth):.1f}% year-over-year",
            "recommendation": "Investigate root causes and develop recovery plan",
            "priority": "high"
        })

    # Profitability insights
    if net_margin < 0:
        insights.append({
            "type": "negative",
            "category": "profitability",
            "title": "Operating at a Loss",
            "description": f"Net margin is {net_margin:.1f}%",
            "recommendation": "Review cost structure and pricing strategy urgently",
            "priority": "high"
        })
    elif net_margin > 15:
        insights.append({
            "type": "positive",
            "category": "profitability",
            "title": "Strong Profitability",
            "description": f"Net margin is {net_margin:.1f}%",
            "recommendation": "Reinvest profits for sustainable growth",
            "priority": "medium"
        })

    # Cash runway insights
    if cash_runway_months < 3:
        insights.append({
            "type": "negative",
            "category": "liquidity",
            "title": "Critical Cash Position",
            "description": f"Only {cash_runway_months:.1f} months of cash runway",
            "recommendation": "Secure additional funding or accelerate collections immediately",
            "priority": "high"
        })
    elif cash_runway_months < 6:
        insights.append({
            "type": "warning",
            "category": "liquidity",
            "title": "Limited Cash Runway",
            "description": f"Cash runway is {cash_runway_months:.1f} months",
            "recommendation": "Monitor cash flow closely and plan for contingencies",
            "priority": "medium"
        })
    elif cash_runway_months > 12:
        insights.append({
            "type": "positive",
            "category": "liquidity",
            "title": "Strong Cash Position",
            "description": f"Cash runway exceeds {cash_runway_months:.0f} months",
            "recommendation": "Consider strategic investments or expansion",
            "priority": "low"
        })

    # Debt insights
    if debt_to_equity > 2:
        insights.append({
            "type": "negative",
            "category": "leverage",
            "title": "High Debt Levels",
            "description": f"Debt-to-equity ratio is {debt_to_equity:.2f}",
            "recommendation": "Focus on debt reduction to improve financial stability",
            "priority": "high"
        })

    # ROE insights
    if roe < 5:
        insights.append({
            "type": "warning",
            "category": "efficiency",
            "title": "Low Return on Equity",
            "description": f"ROE is {roe:.1f}%",
            "recommendation": "Improve operational efficiency and profit margins",
            "priority": "medium"
        })

    return insights[:5]  # Limit to top 5 insights
