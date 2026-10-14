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

from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import Abs, DateFormat, Sum
from frappe.utils import add_months, get_first_day, getdate

from .cost_ratios import _get_fixed_cost
from .data import _gl_daily_cache, _gl_sum_period


if TYPE_CHECKING:
    import numpy as np



def _period_root_type_breakdown(company: str, start: str, end: str,
                                intelligence=None) -> Dict[str, float]:
    """Revenue and expenses for the period.

    When `intelligence` is supplied, reads the _gl_daily_cache (zero extra
    DB queries).  Falls back to a direct GL query when called standalone.
    """
    start, end = str(start), str(end)
    if intelligence is not None:
        gl = _gl_daily_cache(intelligence)
        revenue  = abs(_gl_sum_period(gl, start, end, "income"))
        expenses = abs(_gl_sum_period(gl, start, end, "expense"))
        return {"revenue": revenue, "expenses": expenses}

    # ── standalone fallback (e.g. tests or direct calls) ──────────────────
    gle = DocType("GL Entry")
    acc = DocType("Account")
    revenue_expr = Abs(Sum(Case().when(acc.root_type == "Income",  gle.credit - gle.debit).else_(0))).as_("revenue")
    expense_expr = Abs(Sum(Case().when(acc.root_type == "Expense", gle.debit - gle.credit).else_(0))).as_("expenses")
    rows = (
        frappe.qb.from_(gle)
        .join(acc).on(gle.account == acc.name)
        .select(revenue_expr, expense_expr)
        .where(gle.posting_date.between(start, end))
        .where(gle.company == company)
        .where(gle.is_cancelled == 0)
        .run(as_dict=True)
    )
    if not rows:
        return {"revenue": 0.0, "expenses": 0.0}
    return {"revenue": float(rows[0].revenue or 0), "expenses": float(rows[0].expenses or 0)}



def generate_scenario_analysis(intelligence) -> Dict[str, Any]:
    """Generate scenario analysis with sensitivity and Monte Carlo"""
    import numpy as np
    # Get baseline metrics
    fy_start = intelligence.fiscal_year["start_date"]
    today = datetime.now().strftime('%Y-%m-%d')

    baseline = _period_root_type_breakdown(intelligence.company, fy_start, today, intelligence)

    base_revenue = float(baseline["revenue"] or 0)
    base_expenses = float(baseline["expenses"] or 0)
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
                "margin": round(adj_net / adj_revenue * 100, 1) if adj_revenue > 0 else None
            })

    # Break-even: configured fixed cost centers when available, else assume
    # 40% of expenses are fixed (reported via `fixed_cost_basis`).
    configured_fixed = _get_fixed_cost(
        intelligence.company, fy_start, today, frappe.get_cached_doc("Insights Settings")
    )
    fixed_cost_basis = "assumed_40pct" if configured_fixed is None else "configured"
    fixed_costs = base_expenses * 0.4 if configured_fixed is None else configured_fixed
    if base_revenue > 0:
        contribution_margin = 1 - max(base_expenses - fixed_costs, 0) / base_revenue
        break_even_revenue = fixed_costs / contribution_margin if contribution_margin > 0 else None
    else:
        contribution_margin = break_even_revenue = None

    # =====================
    # MONTE CARLO SIMULATION
    # =====================
    num_simulations = 1000

    # Historical volatility (simplified - using last 12 months std dev).
    # The legacy SQL used DATE_SUB(CURDATE(), INTERVAL 12 MONTH); we
    # resolve the boundary on the Python side so PyPika emits a literal
    # bound parameter.
    # Last 12 complete months (current month is partial and would inflate
    # the std dev); lower bound is the 1st of a month, upper bound <= today.
    month_start = get_first_day(getdate())
    twelve_months_ago = add_months(month_start, -12).strftime('%Y-%m-%d')
    last_month_end = (month_start - timedelta(days=1)).strftime('%Y-%m-%d')
    gle = DocType("GL Entry")
    acc = DocType("Account")
    month_expr = DateFormat(gle.posting_date, "%Y-%m").as_("period")
    monthly_revenues = (
        frappe.qb.from_(gle)
        .join(acc)
        .on(gle.account == acc.name)
        .select(
            month_expr,
            Abs(Sum(gle.credit - gle.debit)).as_("revenue"),
        )
        .where(acc.root_type == "Income")
        .where(gle.posting_date.between(twelve_months_ago, last_month_end))
        .where(gle.company == intelligence.company)
        .where(gle.is_cancelled == 0)
        .groupby(month_expr)
        .run(as_dict=True)
    )

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
            "margin": round(base_net_income / base_revenue * 100, 1) if base_revenue > 0 else None
        },
        "sensitivity": {
            "scenarios": sensitivity_scenarios,
            "revenue_changes": revenue_changes,
            "expense_changes": expense_changes
        },
        "break_even": {
            "revenue": break_even_revenue,
            "current_revenue": base_revenue,
            "margin_of_safety": round((base_revenue - break_even_revenue) / base_revenue * 100, 1) if (base_revenue > 0 and break_even_revenue is not None) else None,
            "fixed_costs": fixed_costs,
            "fixed_cost_basis": fixed_cost_basis,
            "contribution_margin": round(contribution_margin * 100, 1) if contribution_margin is not None else None
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


def calc_change(current: float, prior: float):
    """Percent change; None when there is no prior base (not a fake 100/0)."""
    if not prior:
        return None
    return round((current - prior) / abs(prior) * 100, 1)


def _fy_label(start, end) -> str:
    return f"FY{start.year % 100:02d}-{end.year % 100:02d}" if end.year != start.year else f"FY{start.year}"


def build_periods(today, fy_start, fy_end) -> Dict[str, Dict[str, Any]]:
    """Period windows (date objects) keyed like `period_data`. `partial` marks
    a still-open current period that started <15 days ago. The prior quarter
    is the full previous calendar quarter, not 'the month before the quarter'."""
    month_start = today.replace(day=1)
    q_start = month_start.replace(month=(today.month - 1) // 3 * 3 + 1)
    pq_start = add_months(q_start, -3)
    pm_start = add_months(month_start, -1)
    pfy_start, pfy_end = add_months(fy_start, -12), add_months(fy_end, -12)
    return {
        "current_month": {"start": month_start, "end": today, "label": today.strftime('%b %Y'),
                          "partial": (today - month_start).days < 15},
        "prior_month": {"start": pm_start, "end": month_start - timedelta(days=1), "label": pm_start.strftime('%b %Y'),
                        "partial": False},
        "current_quarter": {"start": q_start, "end": today, "label": f"Q{(today.month - 1) // 3 + 1} {today.year}",
                            "partial": (today - q_start).days < 15},
        "prior_quarter": {"start": pq_start, "end": q_start - timedelta(days=1),
                          "label": f"Q{(pq_start.month - 1) // 3 + 1} {pq_start.year}", "partial": False},
        "current_ytd": {"start": fy_start, "end": today, "label": f"YTD {_fy_label(fy_start, fy_end)}",
                        "partial": False},
        "prior_ytd": {"start": pfy_start, "end": add_months(today, -12), "label": f"YTD {_fy_label(pfy_start, pfy_end)}",
                      "partial": False},
    }


def compare_periods(intelligence) -> Dict[str, Any]:
    """Compare financial performance across periods"""
    periods = build_periods(
        getdate(),
        getdate(intelligence.fiscal_year["start_date"]),
        getdate(intelligence.fiscal_year["end_date"]),
    )

    period_data = {}
    for key, p in periods.items():
        breakdown = _period_root_type_breakdown(intelligence.company, p["start"].isoformat(), p["end"].isoformat(), intelligence)
        revenue, expenses = breakdown["revenue"], breakdown["expenses"]
        period_data[key] = {
            "revenue": revenue,
            "expenses": expenses,
            "net_income": revenue - expenses,
            "margin": round((revenue - expenses) / revenue * 100, 1) if revenue > 0 else None,
            "label": p["label"],
            # An open period with a few days (or no postings) must not be
            # read as a real decline against a full prior period.
            "is_partial": key.startswith("current") and (p["partial"] or not (revenue or expenses)),
        }

    def comparison(cur_key, prior_key, null_if_partial):
        cur, prior = period_data[cur_key], period_data[prior_key]
        skip = null_if_partial and cur["is_partial"]
        return {
            "current": cur,
            "prior": prior,
            **{key: None if skip else calc_change(cur[f], prior[f])
               for key, f in (("revenue_change", "revenue"), ("expense_change", "expenses"),
                              ("net_income_change", "net_income"))},
        }

    mom_comparison = comparison("current_month", "prior_month", True)
    qoq_comparison = comparison("current_quarter", "prior_quarter", True)
    yoy_comparison = comparison("current_ytd", "prior_ytd", False)

    return {
        "period_data": period_data,
        "mom": mom_comparison,
        "qoq": qoq_comparison,
        "yoy": yoy_comparison,
        "summary": [
            {
                "comparison": name,
                "revenue_change": c["revenue_change"],
                "expense_change": c["expense_change"],
                "net_income_change": c["net_income_change"],
            }
            for name, c in (
                ("Month over Month", mom_comparison),
                ("Quarter over Quarter", qoq_comparison),
                ("Year over Year", yoy_comparison),
            )
        ]
    }
