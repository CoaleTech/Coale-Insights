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

from frappe.utils import add_months

from .data import get_cash_balance, get_monthly_financial_trends, _gl_daily_cache, _gl_sum_period, _gl_cumulative


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

    expr = gle.debit - gle.credit
    amount = Coalesce(Sum(expr), 0)
    if apply_abs:
        amount = Abs(amount)
    query = (
        frappe.qb.from_(gle)
        .join(acc)
        .on(gle.account == acc.name)
        .select(amount.as_("amount"))
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
    """Calculate executive-level KPIs and trends.

    All GL aggregations read from _gl_daily_cache (one DB scan shared with
    ratio_trends, working_capital, compare_periods, scenario_analysis).
    """
    fy_start = intelligence.fiscal_year["start_date"]
    today    = datetime.now().strftime('%Y-%m-%d')
    company  = intelligence.company

    gl = _gl_daily_cache(intelligence)

    # ── YTD P&L ───────────────────────────────────────────────────────────
    ytd_revenue          = abs(_gl_sum_period(gl, fy_start, today, "income"))
    ytd_expenses         = abs(_gl_sum_period(gl, fy_start, today, "expense"))
    ytd_net_income       = ytd_revenue - ytd_expenses
    net_margin = (ytd_net_income / ytd_revenue * 100) if ytd_revenue > 0 else None

    # EBITDA add-backs: interest by name, depreciation by account_type —
    # same account-matching convention as calculate_ratio_trends.
    ytd_interest_expense = abs(_gl_sum_period(gl, fy_start, today, "interest"))
    ytd_depreciation     = abs(_gl_sum_period(gl, fy_start, today, "dep"))

    ytd_ebit   = ytd_net_income + ytd_interest_expense
    ytd_ebitda = ytd_ebit + ytd_depreciation
    ebitda_margin = (ytd_ebitda / ytd_revenue * 100) if ytd_revenue > 0 else None

    # Gross profit from Sales Invoice (ibis, one query shared globally via
    # the same ibis cache — not duplicated by this call).
    from insights.ml.sales_intelligence import gross_margin_totals

    gm = gross_margin_totals(fy_start, today, company)
    if gm["total_revenue"] > 0:
        ytd_cogs     = gm["total_revenue"] - gm["total_profit"]
        gross_profit = gm["total_profit"]
        gross_margin = gm["overall_margin"]
    else:
        ytd_cogs     = 0.0
        gross_profit = None
        gross_margin = None

    # ── YoY growth ────────────────────────────────────────────────────────
    prior_fy_start = add_months(fy_start, -12)
    prior_today    = add_months(today,    -12)
    prior_revenue  = abs(_gl_sum_period(gl, str(prior_fy_start), str(prior_today), "income"))

    if prior_revenue > 0 and prior_revenue >= ytd_revenue * 0.10:
        revenue_growth = (ytd_revenue - prior_revenue) / prior_revenue * 100
    else:
        revenue_growth = None

    # ── Cash & runway ─────────────────────────────────────────────────────
    cash_balance = get_cash_balance(intelligence)  # already cached on intelligence

    three_months_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    monthly_expenses_total = abs(_gl_sum_period(gl, three_months_ago, today, "expense"))
    monthly_expenses   = monthly_expenses_total / 3 if monthly_expenses_total else 0
    cash_runway_months = (cash_balance / monthly_expenses) if monthly_expenses > 0 else None

    # ── Balance sheet (cumulative to today, leaf accounts only) ───────────
    # asset_leaf / liability_leaf exclude group-account double-counts;
    # equity uses all accounts (same as the original call with no is_group filter).
    total_assets      = _gl_cumulative(gl, today, "asset_leaf")
    total_liabilities = _gl_cumulative(gl, today, "liability_leaf")
    total_equity      = _gl_cumulative(gl, today, "equity")

    roe = (ytd_net_income / total_equity     * 100) if total_equity     > 0 else None
    roa = (ytd_net_income / total_assets     * 100) if total_assets     > 0 else None
    debt_to_equity = (max(0.0, total_liabilities) / total_equity) if total_equity > 0 else None

    # ── Trends (also reads _gl_daily_cache internally, zero extra query) ──
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
        "net_margin": round(net_margin, 2) if net_margin is not None else None,
        "ytd_ebitda": round(ytd_ebitda, 2),
        "ebitda_margin": round(ebitda_margin, 2) if ebitda_margin is not None else None,
        "ebitda_addbacks": {"interest": ytd_interest_expense, "depreciation": ytd_depreciation},
        "revenue_growth_yoy": round(revenue_growth, 2) if revenue_growth is not None else None,
        "revenue_growth": round(revenue_growth, 2) if revenue_growth is not None else None,
        "prior_period_revenue": prior_revenue,
        "prior_period_start": prior_fy_start,
        "cash_balance": cash_balance,
        "cash_runway_months": round(cash_runway_months, 1) if cash_runway_months is not None else None,
        "monthly_burn_rate": monthly_expenses,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "roe": round(roe, 2) if roe is not None else None,
        "roa": round(roa, 2) if roa is not None else None,
        "debt_to_equity": round(debt_to_equity, 2) if debt_to_equity is not None else None,
        "monthly_trends": monthly_trends,
        "health_scores": health_scores,
        "key_insights": key_insights,
        "kpis": [
            {"label": "Total Revenue",    "value": ytd_revenue,    "format": "currency", "subtitle": "Year to Date",
             "trend": round(revenue_growth, 1) if revenue_growth is not None else None},
            {"label": "Net Profit",       "value": ytd_net_income, "format": "currency",
             "subtitle": f"{net_margin:.1f}% margin" if net_margin is not None else "Year to Date"},
            {"label": "EBITDA",           "value": ytd_ebitda,     "format": "currency",
             "subtitle": f"{ebitda_margin:.1f}% margin" if ebitda_margin is not None else "Year to Date"},
            {"label": "Gross Margin",     "value": gross_margin,   "format": "percent",  "subtitle": "Revenue - COGS"},
            {"label": "Revenue Growth",   "value": revenue_growth, "format": "percent",  "subtitle": "YoY"},
            {"label": "Cash Position",    "value": cash_balance,   "format": "currency",
             "subtitle": f"{cash_runway_months:.0f} months runway" if cash_runway_months is not None else "No recent expenses"},
            {"label": "ROE",              "value": roe,            "format": "percent",
             "subtitle": "Return on Equity" if roe is not None else "No equity recorded"},
        ]
    }



def calculate_health_scores(intelligence, net_margin: Optional[float], roe: Optional[float], roa: Optional[float],
                            debt_to_equity: Optional[float], cash_runway_months: Optional[float],
                            revenue_growth: Optional[float]) -> Dict[str, Any]:
    """Calculate financial health scores (0-100) for liquidity, profitability, and efficiency"""

    # Liquidity Score (based on cash runway and debt ratio)
    liquidity_score = 0
    # No burn (None) means no liquidity pressure, same as the old 999 score.
    if cash_runway_months is None or cash_runway_months >= 12:
        liquidity_score = 90
    elif cash_runway_months >= 6:
        liquidity_score = 70
    elif cash_runway_months >= 3:
        liquidity_score = 50
    else:
        liquidity_score = 30

    # Adjust for debt level
    if debt_to_equity is None:
        pass  # no equity -> leverage unavailable, no adjustment
    elif debt_to_equity < 0.5:
        liquidity_score = min(100, liquidity_score + 10)
    elif debt_to_equity > 2:
        liquidity_score = max(0, liquidity_score - 20)

    liquidity_status = "Excellent" if liquidity_score >= 80 else "Good" if liquidity_score >= 60 else "Fair" if liquidity_score >= 40 else "Poor"

    # Profitability Score (based on net margin and ROE)
    profitability_score = 0
    net_margin = net_margin or 0  # unavailable (no revenue) scores as no profit
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
    if roe is None:
        pass  # no equity -> ROE unavailable, neither boost nor penalty
    elif roe >= 15:
        profitability_score = min(100, profitability_score + 10)
    elif roe < 5:
        profitability_score = max(0, profitability_score - 10)

    profitability_status = "Excellent" if profitability_score >= 80 else "Good" if profitability_score >= 60 else "Fair" if profitability_score >= 40 else "Poor"

    # Efficiency Score (based on ROA and revenue growth)
    efficiency_score = 0
    if roa is not None and roa >= 10:
        efficiency_score = 85
    elif roa is not None and roa >= 5:
        efficiency_score = 65
    elif roa is not None and roa >= 2:
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

    return {
        "liquidity": liquidity_score,
        "liquidity_status": liquidity_status,
        "profitability": profitability_score,
        "profitability_status": profitability_status,
        "efficiency": efficiency_score,
        "efficiency_status": efficiency_status,
    }


def generate_key_insights(intelligence, ytd_revenue: float, ytd_net_income: float,
                          net_margin: Optional[float], revenue_growth: Optional[float],
                          cash_runway_months: Optional[float], debt_to_equity: Optional[float],
                          roe: Optional[float], health_scores: Dict) -> List[Dict]:
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
    if net_margin is not None and net_margin < 0:
        insights.append({
            "type": "negative",
            "category": "profitability",
            "title": "Operating at a Loss",
            "description": f"Net margin is {net_margin:.1f}%",
            "recommendation": "Review cost structure and pricing strategy urgently",
            "priority": "high"
        })
    elif net_margin is not None and net_margin > 15:
        insights.append({
            "type": "positive",
            "category": "profitability",
            "title": "Strong Profitability",
            "description": f"Net margin is {net_margin:.1f}%",
            "recommendation": "Reinvest profits for sustainable growth",
            "priority": "medium"
        })

    # Cash runway insights
    if cash_runway_months is None:
        pass  # no burn -> runway is not a meaningful metric
    elif cash_runway_months < 3:
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
    if debt_to_equity is not None and debt_to_equity > 2:
        insights.append({
            "type": "negative",
            "category": "leverage",
            "title": "High Debt Levels",
            "description": f"Debt-to-equity ratio is {debt_to_equity:.2f}",
            "recommendation": "Focus on debt reduction to improve financial stability",
            "priority": "high"
        })

    # ROE insights
    if roe is not None and roe < 5:
        insights.append({
            "type": "warning",
            "category": "efficiency",
            "title": "Low Return on Equity",
            "description": f"ROE is {roe:.1f}%",
            "recommendation": "Improve operational efficiency and profit margins",
            "priority": "medium"
        })

    return insights[:5]  # Limit to top 5 insights
