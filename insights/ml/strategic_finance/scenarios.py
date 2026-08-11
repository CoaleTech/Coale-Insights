from __future__ import annotations
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Scenario analysis and period comparison for Strategic Finance Intelligence.
Includes sensitivity analysis, Monte Carlo simulation, and period-over-period comparison.
"""

import frappe
from datetime import datetime, timedelta
from typing import Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np



def generate_scenario_analysis(intelligence) -> Dict[str, Any]:
    """Generate scenario analysis with sensitivity and Monte Carlo"""
    import numpy as np
    # Get baseline metrics
    fy_start = intelligence.fiscal_year["start_date"]
    today = datetime.now().strftime('%Y-%m-%d')

    baseline = frappe.db.sql("""
        SELECT
            SUM(CASE WHEN acc.root_type = 'Income' THEN ABS(credit - debit) ELSE 0 END) as revenue,
            SUM(CASE WHEN acc.root_type = 'Expense' THEN ABS(debit - credit) ELSE 0 END) as expenses
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE gle.posting_date BETWEEN %s AND %s
            AND gle.company = %s
            AND gle.is_cancelled = 0
    """, (fy_start, today, intelligence.company), as_dict=True)[0]

    base_revenue = float(baseline.revenue or 0)
    base_expenses = float(baseline.expenses or 0)
    base_net_income = base_revenue - base_expenses
    base_tax = base_net_income * (intelligence.CORPORATE_TAX_RATE / 100) if base_net_income > 0 else 0
    base_net_after_tax = base_net_income - base_tax

    # =====================
    # SENSITIVITY ANALYSIS
    # =====================
    sensitivity_scenarios = []
    revenue_changes = [-30, -20, -10, 0, 10, 20, 30]
    expense_changes = [-20, -10, 0, 10, 20]

    for rev_change in revenue_changes:
        for exp_change in expense_changes:
            adj_revenue = base_revenue * (1 + rev_change / 100)
            adj_expenses = base_expenses * (1 + exp_change / 100)
            adj_net = adj_revenue - adj_expenses
            adj_tax = adj_net * (intelligence.CORPORATE_TAX_RATE / 100) if adj_net > 0 else 0
            adj_net_after_tax = adj_net - adj_tax

            sensitivity_scenarios.append({
                "revenue_change": rev_change,
                "expense_change": exp_change,
                "revenue": adj_revenue,
                "expenses": adj_expenses,
                "net_income": adj_net,
                "net_after_tax": adj_net_after_tax,
                "margin": round(adj_net / adj_revenue * 100, 1) if adj_revenue > 0 else 0
            })

    # Break-even analysis
    fixed_costs_ratio = 0.4  # Assume 40% of expenses are fixed
    fixed_costs = base_expenses * fixed_costs_ratio
    variable_cost_ratio = (base_expenses * (1 - fixed_costs_ratio)) / base_revenue if base_revenue > 0 else 0.5
    contribution_margin = 1 - variable_cost_ratio
    break_even_revenue = fixed_costs / contribution_margin if contribution_margin > 0 else 0

    # =====================
    # MONTE CARLO SIMULATION
    # =====================
    num_simulations = 1000

    # Historical volatility (simplified - using last 12 months std dev)
    monthly_revenues = frappe.db.sql("""
        SELECT
            DATE_FORMAT(gle.posting_date, '%%Y-%%m') as period,
            SUM(ABS(credit - debit)) as revenue
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE acc.root_type = 'Income'
            AND gle.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            AND gle.company = %s
            AND gle.is_cancelled = 0
        GROUP BY DATE_FORMAT(gle.posting_date, '%%Y-%%m')
    """, (intelligence.company,), as_dict=True)

    if monthly_revenues and len(monthly_revenues) > 1:
        rev_values = [float(r.revenue or 0) for r in monthly_revenues]
        rev_mean = np.mean(rev_values)
        rev_std = np.std(rev_values)
        rev_volatility = rev_std / rev_mean if rev_mean > 0 else 0.15
    else:
        rev_volatility = 0.15  # Default 15% volatility

    exp_volatility = rev_volatility * 0.7  # Expenses less volatile

    # Run simulations
    np.random.seed(42)  # For reproducibility
    simulated_revenues = np.random.normal(base_revenue, base_revenue * rev_volatility, num_simulations)
    simulated_expenses = np.random.normal(base_expenses, base_expenses * exp_volatility, num_simulations)
    simulated_net_income = simulated_revenues - simulated_expenses
    simulated_net_after_tax = np.where(
        simulated_net_income > 0,
        simulated_net_income * (1 - intelligence.CORPORATE_TAX_RATE / 100),
        simulated_net_income
    )

    # Calculate percentiles
    percentiles = [5, 10, 25, 50, 75, 90, 95]
    net_income_percentiles = {
        f"p{p}": float(np.percentile(simulated_net_after_tax, p))
        for p in percentiles
    }

    # Probability of outcomes
    prob_loss = float(np.sum(simulated_net_income < 0) / num_simulations * 100)
    prob_exceed_base = float(np.sum(simulated_net_after_tax > base_net_after_tax) / num_simulations * 100)

    # Distribution histogram data
    hist_bins = 20
    hist_counts, hist_edges = np.histogram(simulated_net_after_tax, bins=hist_bins)
    histogram_data = [
        {
            "bin_start": float(hist_edges[i]),
            "bin_end": float(hist_edges[i + 1]),
            "count": int(hist_counts[i]),
            "probability": float(hist_counts[i] / num_simulations * 100)
        }
        for i in range(len(hist_counts))
    ]

    # Named scenarios
    named_scenarios = [
        {
            "name": "Best Case (P95)",
            "description": "95th percentile outcome",
            "net_income": net_income_percentiles["p95"],
            "probability": 5
        },
        {
            "name": "Optimistic (P75)",
            "description": "75th percentile outcome",
            "net_income": net_income_percentiles["p75"],
            "probability": 25
        },
        {
            "name": "Base Case (P50)",
            "description": "Median expected outcome",
            "net_income": net_income_percentiles["p50"],
            "probability": 50
        },
        {
            "name": "Pessimistic (P25)",
            "description": "25th percentile outcome",
            "net_income": net_income_percentiles["p25"],
            "probability": 25
        },
        {
            "name": "Worst Case (P5)",
            "description": "5th percentile outcome",
            "net_income": net_income_percentiles["p5"],
            "probability": 5
        }
    ]

    return {
        "baseline": {
            "revenue": base_revenue,
            "expenses": base_expenses,
            "net_income": base_net_income,
            "tax": base_tax,
            "net_after_tax": base_net_after_tax,
            "margin": round(base_net_income / base_revenue * 100, 1) if base_revenue > 0 else 0
        },
        "sensitivity": {
            "scenarios": sensitivity_scenarios,
            "revenue_changes": revenue_changes,
            "expense_changes": expense_changes
        },
        "break_even": {
            "revenue": break_even_revenue,
            "current_revenue": base_revenue,
            "margin_of_safety": round((base_revenue - break_even_revenue) / base_revenue * 100, 1) if base_revenue > 0 else 0,
            "fixed_costs": fixed_costs,
            "contribution_margin": round(contribution_margin * 100, 1)
        },
        "monte_carlo": {
            "simulations": num_simulations,
            "revenue_volatility": round(rev_volatility * 100, 1),
            "expense_volatility": round(exp_volatility * 100, 1),
            "percentiles": net_income_percentiles,
            "mean": float(np.mean(simulated_net_after_tax)),
            "std": float(np.std(simulated_net_after_tax)),
            "probability_of_loss": round(prob_loss, 1),
            "probability_exceed_base": round(prob_exceed_base, 1),
            "histogram": histogram_data,
            "named_scenarios": named_scenarios
        }
    }


def compare_periods(intelligence) -> Dict[str, Any]:
    """Compare financial performance across periods"""
    today = datetime.now()

    # Define periods
    periods = {
        "current_month": {
            "start": today.replace(day=1).strftime('%Y-%m-%d'),
            "end": today.strftime('%Y-%m-%d'),
            "label": today.strftime('%b %Y')
        },
        "prior_month": {
            "start": (today.replace(day=1) - timedelta(days=1)).replace(day=1).strftime('%Y-%m-%d'),
            "end": (today.replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d'),
            "label": (today.replace(day=1) - timedelta(days=1)).strftime('%b %Y')
        },
        "current_quarter": {
            "start": datetime(today.year, ((today.month - 1) // 3) * 3 + 1, 1).strftime('%Y-%m-%d'),
            "end": today.strftime('%Y-%m-%d'),
            "label": f"Q{((today.month - 1) // 3) + 1} {today.year}"
        },
        "prior_quarter": {
            "start": (datetime(today.year, ((today.month - 1) // 3) * 3 + 1, 1) - timedelta(days=1)).replace(day=1).strftime('%Y-%m-%d'),
            "end": (datetime(today.year, ((today.month - 1) // 3) * 3 + 1, 1) - timedelta(days=1)).strftime('%Y-%m-%d'),
            "label": f"Q{(((today.month - 1) // 3) or 4)} {today.year if (today.month - 1) // 3 > 0 else today.year - 1}"
        },
        "current_ytd": {
            "start": intelligence.fiscal_year["start_date"],
            "end": today.strftime('%Y-%m-%d'),
            "label": f"YTD {today.year}"
        },
        "prior_ytd": {
            "start": (datetime.strptime(intelligence.fiscal_year["start_date"], '%Y-%m-%d') - timedelta(days=365)).strftime('%Y-%m-%d'),
            "end": (today - timedelta(days=365)).strftime('%Y-%m-%d'),
            "label": f"YTD {today.year - 1}"
        }
    }

    def get_period_financials(start, end):
        result = frappe.db.sql("""
            SELECT
                SUM(CASE WHEN acc.root_type = 'Income' THEN ABS(credit - debit) ELSE 0 END) as revenue,
                SUM(CASE WHEN acc.root_type = 'Expense' THEN ABS(debit - credit) ELSE 0 END) as expenses
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.posting_date BETWEEN %s AND %s
                AND gle.company = %s
                AND gle.is_cancelled = 0
        """, (start, end, intelligence.company), as_dict=True)[0]

        revenue = float(result.revenue or 0)
        expenses = float(result.expenses or 0)
        return {
            "revenue": revenue,
            "expenses": expenses,
            "net_income": revenue - expenses,
            "margin": round((revenue - expenses) / revenue * 100, 1) if revenue > 0 else 0
        }

    # Calculate for each period
    period_data = {}
    for key, period in periods.items():
        period_data[key] = {
            **get_period_financials(period["start"], period["end"]),
            "label": period["label"]
        }

    # Calculate comparisons
    def calc_change(current, prior):
        if prior == 0:
            return 100 if current > 0 else 0
        return round((current - prior) / abs(prior) * 100, 1)

    mom_comparison = {
        "current": period_data["current_month"],
        "prior": period_data["prior_month"],
        "revenue_change": calc_change(period_data["current_month"]["revenue"], period_data["prior_month"]["revenue"]),
        "expense_change": calc_change(period_data["current_month"]["expenses"], period_data["prior_month"]["expenses"]),
        "net_income_change": calc_change(period_data["current_month"]["net_income"], period_data["prior_month"]["net_income"])
    }

    qoq_comparison = {
        "current": period_data["current_quarter"],
        "prior": period_data["prior_quarter"],
        "revenue_change": calc_change(period_data["current_quarter"]["revenue"], period_data["prior_quarter"]["revenue"]),
        "expense_change": calc_change(period_data["current_quarter"]["expenses"], period_data["prior_quarter"]["expenses"]),
        "net_income_change": calc_change(period_data["current_quarter"]["net_income"], period_data["prior_quarter"]["net_income"])
    }

    yoy_comparison = {
        "current": period_data["current_ytd"],
        "prior": period_data["prior_ytd"],
        "revenue_change": calc_change(period_data["current_ytd"]["revenue"], period_data["prior_ytd"]["revenue"]),
        "expense_change": calc_change(period_data["current_ytd"]["expenses"], period_data["prior_ytd"]["expenses"]),
        "net_income_change": calc_change(period_data["current_ytd"]["net_income"], period_data["prior_ytd"]["net_income"])
    }

    return {
        "period_data": period_data,
        "mom": mom_comparison,
        "qoq": qoq_comparison,
        "yoy": yoy_comparison,
        "summary": [
            {
                "comparison": "Month over Month",
                "revenue_change": mom_comparison["revenue_change"],
                "expense_change": mom_comparison["expense_change"],
                "net_income_change": mom_comparison["net_income_change"]
            },
            {
                "comparison": "Quarter over Quarter",
                "revenue_change": qoq_comparison["revenue_change"],
                "expense_change": qoq_comparison["expense_change"],
                "net_income_change": qoq_comparison["net_income_change"]
            },
            {
                "comparison": "Year over Year",
                "revenue_change": yoy_comparison["revenue_change"],
                "expense_change": yoy_comparison["expense_change"],
                "net_income_change": yoy_comparison["net_income_change"]
            }
        ]
    }
