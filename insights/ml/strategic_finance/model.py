# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Strategic Finance Intelligence Model
Houses the StrategicFinanceIntelligence class (formerly in __init__.py).
"""

from datetime import datetime
from typing import Any

import frappe

from insights.ml.strategic_finance.analysis import (
    analyze_capital_planning,
    analyze_working_capital,
    calculate_ratio_trends,
)
from insights.ml.strategic_finance.cost_ratios import (
    calculate_cost_structure_ratios,
    forecast_expenses,
)
from insights.ml.strategic_finance.data import (
    get_current_fiscal_year,
    get_expense_breakdown,
    sanitize_for_json,
)
from insights.ml.strategic_finance.forecast import (
    forecast_cash_flow,
    generate_thirteen_week_forecast,
)
from insights.ml.strategic_finance.scenarios import (
    compare_periods,
    generate_scenario_analysis,
)
from insights.ml.strategic_finance.summary import calculate_executive_summary


class StrategicFinanceIntelligence:
    """
    Strategic Finance Intelligence Model

    Differentiates from Financial Intelligence by focusing on:
    - FORWARD-LOOKING analytics (forecasts, projections, scenarios)
    - STRATEGIC planning (capital allocation, runway, what-if)
    - DECISION SUPPORT (scenario modeling, sensitivity analysis)

    While Financial Intelligence focuses on:
    - HISTORICAL reporting (P&L, cash flow, ratios)
    - COMPLIANCE (tax, receivables, payables)
    - OPERATIONAL metrics (DSO, DPO, aging)

    Computed fresh on every call - no training, no caching (matches every
    other intelligence domain in this app).
    """

    CORPORATE_TAX_RATE = 30  # 30% — used as percentage (divide by 100 for decimal)

    def __init__(self):
        self.model_name = "StrategicFinanceIntelligence"
        self.company = (
            frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        self.base_currency = (
            frappe.db.get_value("Company", self.company, "default_currency")
            or frappe.db.get_single_value("System Settings", "default_currency")
            or "USD"
        )
        self.fiscal_year = get_current_fiscal_year(self)

    def train(self) -> dict[str, Any]:
        """Generate comprehensive strategic finance intelligence"""
        executive_summary = calculate_executive_summary(self)
        cash_forecast = forecast_cash_flow(self)
        thirteen_week_forecast = generate_thirteen_week_forecast(self)
        capital_planning = analyze_capital_planning(self)
        working_capital = analyze_working_capital(self)
        ratio_trends = calculate_ratio_trends(self)
        scenario_analysis = generate_scenario_analysis(self)
        period_comparison = compare_periods(self)
        expense_breakdown = get_expense_breakdown(self)
        cost_structure = calculate_cost_structure_ratios(self)
        expense_forecast = forecast_expenses(self)

        return {
            "status": "success",
            "generated_at": datetime.now().isoformat(),
            "company": self.company,
            "base_currency": self.base_currency,
            "fiscal_year": self.fiscal_year,
            "executive_summary": executive_summary,
            "cash_forecast": cash_forecast,
            "thirteen_week_forecast": thirteen_week_forecast,
            "capital_planning": capital_planning,
            "working_capital": working_capital,
            "ratio_trends": ratio_trends,
            "scenario_analysis": scenario_analysis,
            "period_comparison": period_comparison,
            "expense_breakdown": expense_breakdown,
            "cost_structure": cost_structure,
            "expense_forecast": expense_forecast,
        }

    def predict(self) -> dict[str, Any]:
        """Same as train: every call is computed fresh, no stale cache."""
        return self.train()


def run_strategic_finance_intelligence(refresh: bool = False) -> dict[str, Any]:
    """Run strategic finance intelligence analysis (computed fresh, no cache).

    `refresh` is accepted for API backward-compatibility; every call already
    computes fresh, so there is nothing to force-refresh.
    """
    return sanitize_for_json(StrategicFinanceIntelligence().train())
