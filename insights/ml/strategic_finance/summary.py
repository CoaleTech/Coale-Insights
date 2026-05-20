# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Executive summary and key insights generation for Strategic Finance Intelligence.
"""

import frappe
from datetime import datetime, timedelta
from typing import Dict, Any, List

from .data import get_cash_balance, get_monthly_financial_trends


def calculate_executive_summary(intelligence) -> Dict[str, Any]:
    """Calculate executive-level KPIs and trends"""
    fy_start = intelligence.fiscal_year["start_date"]
    today = datetime.now().strftime('%Y-%m-%d')

    # YTD Revenue
    ytd_revenue = frappe.db.sql("""
        SELECT COALESCE(SUM(ABS(credit - debit)), 0) as amount
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE acc.root_type = 'Income'
            AND gle.posting_date BETWEEN %s AND %s
            AND gle.company = %s
            AND gle.is_cancelled = 0
    """, (fy_start, today, intelligence.company), as_dict=True)[0].amount or 0

    # YTD Expenses
    ytd_expenses = frappe.db.sql("""
        SELECT COALESCE(SUM(ABS(debit - credit)), 0) as amount
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE acc.root_type = 'Expense'
            AND gle.posting_date BETWEEN %s AND %s
            AND gle.company = %s
            AND gle.is_cancelled = 0
    """, (fy_start, today, intelligence.company), as_dict=True)[0].amount or 0

    # YTD Net Income
    ytd_net_income = ytd_revenue - ytd_expenses
    net_margin = (ytd_net_income / ytd_revenue * 100) if ytd_revenue > 0 else 0

    # YTD Cost of Goods Sold (COGS) for Gross Margin calculation
    ytd_cogs = frappe.db.sql("""
        SELECT COALESCE(SUM(ABS(debit - credit)), 0) as amount
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE (acc.account_type = 'Cost of Goods Sold'
               OR acc.name LIKE '%%Cost of Goods%%'
               OR acc.name LIKE '%%COGS%%')
            AND acc.root_type = 'Expense'
            AND gle.posting_date BETWEEN %s AND %s
            AND gle.company = %s
            AND gle.is_cancelled = 0
    """, (fy_start, today, intelligence.company), as_dict=True)[0].amount or 0

    # Gross Margin = (Revenue - COGS) / Revenue * 100
    # If no COGS accounts found, fall back to a reasonable estimate (70% of revenue)
    gross_profit = ytd_revenue - ytd_cogs if ytd_cogs > 0 else ytd_revenue * 0.7
    gross_margin = (gross_profit / ytd_revenue * 100) if ytd_revenue > 0 else 0

    # Prior Year Same Period for Growth
    prior_fy_start = (datetime.strptime(fy_start, '%Y-%m-%d') - timedelta(days=365)).strftime('%Y-%m-%d')
    prior_today = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    prior_revenue = frappe.db.sql("""
        SELECT COALESCE(SUM(ABS(credit - debit)), 0) as amount
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE acc.root_type = 'Income'
            AND gle.posting_date BETWEEN %s AND %s
            AND gle.company = %s
            AND gle.is_cancelled = 0
    """, (prior_fy_start, prior_today, intelligence.company), as_dict=True)[0].amount or 0

    revenue_growth = ((ytd_revenue - prior_revenue) / prior_revenue * 100) if prior_revenue > 0 else 0

    # Cash Position
    cash_balance = get_cash_balance(intelligence)

    # Monthly Burn Rate (average of last 3 months expenses)
    three_months_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    monthly_expenses = frappe.db.sql("""
        SELECT COALESCE(SUM(ABS(debit - credit)), 0) / 3 as avg_monthly
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE acc.root_type = 'Expense'
            AND gle.posting_date >= %s
            AND gle.company = %s
            AND gle.is_cancelled = 0
    """, (three_months_ago, intelligence.company), as_dict=True)[0].avg_monthly or 0

    # Cash Runway
    cash_runway_months = (cash_balance / monthly_expenses) if monthly_expenses > 0 else 999

    # Total Assets (from Asset doctype)
    total_assets = frappe.db.sql("""
        SELECT COALESCE(SUM(purchase_amount), 0) as total
        FROM `tabAsset`
        WHERE company = %s
            AND docstatus = 1
            AND status NOT IN ('Sold', 'Scrapped')
    """, (intelligence.company,), as_dict=True)[0].total or 0

    # Total Debt (Liabilities)
    total_liabilities = frappe.db.sql("""
        SELECT COALESCE(SUM(ABS(credit - debit)), 0) as amount
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE acc.root_type = 'Liability'
            AND gle.company = %s
            AND gle.is_cancelled = 0
    """, (intelligence.company,), as_dict=True)[0].amount or 0

    # Equity
    total_equity = frappe.db.sql("""
        SELECT COALESCE(SUM(ABS(credit - debit)), 0) as amount
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE acc.root_type = 'Equity'
            AND gle.company = %s
            AND gle.is_cancelled = 0
    """, (intelligence.company,), as_dict=True)[0].amount or 0

    # ROE and ROA
    roe = (ytd_net_income / total_equity * 100) if total_equity > 0 else 0
    roa = (ytd_net_income / total_assets * 100) if total_assets > 0 else 0

    # Debt to Equity
    debt_to_equity = (total_liabilities / total_equity) if total_equity > 0 else 0

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
        "gross_margin": round(gross_margin, 2),
        "ytd_net_income": ytd_net_income,
        "net_margin": round(net_margin, 2),
        "revenue_growth_yoy": round(revenue_growth, 2),
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
            {"label": "Total Revenue", "value": ytd_revenue, "format": "currency", "subtitle": "Year to Date", "trend": round(revenue_growth, 1)},
            {"label": "Net Profit", "value": ytd_net_income, "format": "currency", "subtitle": f"{net_margin:.1f}% margin"},
            {"label": "Gross Margin", "value": gross_margin, "format": "percent", "subtitle": "Revenue - COGS"},
            {"label": "Revenue Growth", "value": revenue_growth, "format": "percent", "subtitle": "YoY"},
            {"label": "Cash Position", "value": cash_balance, "format": "currency", "subtitle": f"{cash_runway_months:.0f} months runway"},
            {"label": "ROE", "value": roe, "format": "percent", "subtitle": "Return on Equity"}
        ]
    }


def calculate_health_scores(intelligence, net_margin: float, roe: float, roa: float,
                            debt_to_equity: float, cash_runway_months: float,
                            revenue_growth: float) -> Dict[str, Any]:
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
    if revenue_growth >= 20:
        efficiency_score = min(100, efficiency_score + 15)
    elif revenue_growth >= 10:
        efficiency_score = min(100, efficiency_score + 10)
    elif revenue_growth < 0:
        efficiency_score = max(0, efficiency_score - 10)

    efficiency_status = "Excellent" if efficiency_score >= 80 else "Good" if efficiency_score >= 60 else "Fair" if efficiency_score >= 40 else "Poor"

    return {
        "liquidity": round(liquidity_score),
        "liquidity_status": liquidity_status,
        "profitability": round(profitability_score),
        "profitability_status": profitability_status,
        "efficiency": round(efficiency_score),
        "efficiency_status": efficiency_status,
        "overall": round((liquidity_score + profitability_score + efficiency_score) / 3),
        "overall_status": "Excellent" if (liquidity_score + profitability_score + efficiency_score) / 3 >= 80 else "Good" if (liquidity_score + profitability_score + efficiency_score) / 3 >= 60 else "Fair"
    }


def generate_key_insights(intelligence, ytd_revenue: float, ytd_net_income: float,
                          net_margin: float, revenue_growth: float,
                          cash_runway_months: float, debt_to_equity: float,
                          roe: float, health_scores: Dict) -> List[Dict]:
    """Generate actionable executive insights based on financial metrics"""
    insights = []

    # Revenue performance insight
    if revenue_growth > 15:
        insights.append({
            "type": "success",
            "title": "Strong Revenue Growth",
            "description": f"Revenue is growing at {revenue_growth:.1f}% YoY, outpacing industry averages. Consider reinvesting in growth initiatives."
        })
    elif revenue_growth > 0:
        insights.append({
            "type": "info",
            "title": "Moderate Revenue Growth",
            "description": f"Revenue growth of {revenue_growth:.1f}% YoY is positive but below optimal targets. Review sales strategies for acceleration."
        })
    else:
        insights.append({
            "type": "danger",
            "title": "Revenue Declining",
            "description": f"Revenue has declined {abs(revenue_growth):.1f}% YoY. Immediate attention needed on sales pipeline and market positioning."
        })

    # Profitability insight
    if net_margin >= 15:
        insights.append({
            "type": "success",
            "title": "Excellent Profit Margins",
            "description": f"Net margin of {net_margin:.1f}% demonstrates strong operational efficiency and pricing power."
        })
    elif net_margin >= 5:
        insights.append({
            "type": "info",
            "title": "Healthy Profit Margins",
            "description": f"Net margin of {net_margin:.1f}% is acceptable. Look for cost optimization opportunities to improve profitability."
        })
    elif net_margin > 0:
        insights.append({
            "type": "warning",
            "title": "Thin Profit Margins",
            "description": f"Net margin of {net_margin:.1f}% is below target. Review expense structure and pricing strategy."
        })
    else:
        insights.append({
            "type": "danger",
            "title": "Operating at Loss",
            "description": f"Negative net margin of {net_margin:.1f}%. Urgent cost reduction and revenue improvement measures needed."
        })

    # Cash runway insight
    if cash_runway_months < 3:
        insights.append({
            "type": "danger",
            "title": "Critical Cash Position",
            "description": f"Only {cash_runway_months:.1f} months of cash runway remaining. Immediate action required on cash conservation or funding."
        })
    elif cash_runway_months < 6:
        insights.append({
            "type": "warning",
            "title": "Limited Cash Runway",
            "description": f"{cash_runway_months:.1f} months of cash runway. Begin planning for additional funding or cost reductions."
        })
    elif cash_runway_months >= 12:
        insights.append({
            "type": "success",
            "title": "Strong Cash Position",
            "description": f"{cash_runway_months:.1f}+ months of runway provides flexibility for strategic investments."
        })

    # Leverage insight
    if debt_to_equity > 2:
        insights.append({
            "type": "warning",
            "title": "High Leverage",
            "description": f"Debt-to-equity ratio of {debt_to_equity:.2f} indicates high leverage. Consider debt reduction strategies."
        })
    elif debt_to_equity < 0.3:
        insights.append({
            "type": "info",
            "title": "Conservative Capital Structure",
            "description": f"Low debt-to-equity of {debt_to_equity:.2f} may indicate opportunity for strategic debt financing."
        })

    # Overall health insight
    overall_score = health_scores.get('overall', 0)
    if overall_score >= 75:
        insights.append({
            "type": "success",
            "title": "Excellent Financial Health",
            "description": f"Overall financial health score of {overall_score}/100 indicates a strong position for growth."
        })
    elif overall_score < 50:
        insights.append({
            "type": "warning",
            "title": "Financial Health Needs Attention",
            "description": f"Overall score of {overall_score}/100 suggests focus needed on improving key financial metrics."
        })

    return insights[:5]  # Limit to top 5 insights
