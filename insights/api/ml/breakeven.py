# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Break-Even Analysis API Endpoints
"""

import frappe
from typing import Dict, Any
from insights.api.response import success, error


@frappe.whitelist()
def item_breakeven(period: str = "Quarterly", fiscal_year: str = None, item_group: str = None) -> Dict[str, Any]:
    """Get item-level break-even analysis."""
    try:
        # calculate_item_breakeven also reads Item (master) and, via
        # _get_fixed_costs, GL Entry -- Sales Invoice alone under-covers it.
        frappe.has_permission("Sales Invoice", "read", throw=True)
        frappe.has_permission("Item", "read", throw=True)
        frappe.has_permission("GL Entry", "read", throw=True)
        from insights.ml.breakeven_engine import BreakevenEngine
        engine = BreakevenEngine(period=period, fiscal_year=fiscal_year)
        result = engine.calculate_item_breakeven(item_group=item_group)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e), exc=e)


@frappe.whitelist()
def predict_breakeven_scenario(
    period: str = "Quarterly", fiscal_year: str = None, scenario: str = None
) -> Dict[str, Any]:
    """Recompute item and overall break-even under a hypothetical cost/price/volume scenario."""
    try:
        # predict() calls calculate_item_breakeven + _get_variable_costs,
        # same read surface as item_breakeven above (Item, GL Entry too).
        frappe.has_permission("Sales Invoice", "read", throw=True)
        frappe.has_permission("Item", "read", throw=True)
        frappe.has_permission("GL Entry", "read", throw=True)
        from insights.ml.breakeven_engine import BreakevenEngine
        engine = BreakevenEngine(period=period, fiscal_year=fiscal_year)
        scenario_data = frappe.parse_json(scenario) if scenario else {}
        result = engine.predict(scenario_data)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e), exc=e)


@frappe.whitelist()
def employee_breakeven(period: str = "Quarterly", fiscal_year: str = None) -> Dict[str, Any]:
    """Get employee/department-level break-even analysis."""
    try:
        # calculate_employee_breakeven also reads Sales Order (order counts)
        # and GL Entry (COGS ratio) -- Salary Slip alone under-covers it.
        frappe.has_permission("Salary Slip", "read", throw=True)
        frappe.has_permission("Sales Order", "read", throw=True)
        frappe.has_permission("GL Entry", "read", throw=True)
        from insights.ml.breakeven_engine import BreakevenEngine
        engine = BreakevenEngine(period=period, fiscal_year=fiscal_year)
        result = engine.calculate_employee_breakeven()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e), exc=e)


@frappe.whitelist()
def cash_flow_breakeven(period: str = "Quarterly", fiscal_year: str = None) -> Dict[str, Any]:
    """Get cash flow break-even analysis."""
    try:
        frappe.has_permission("Payment Entry", "read", throw=True)
        from insights.ml.breakeven_engine import BreakevenEngine
        engine = BreakevenEngine(period=period, fiscal_year=fiscal_year)
        result = engine.calculate_cash_flow_breakeven()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e), exc=e)


@frappe.whitelist()
def capital_efficiency(period: str = "Quarterly", fiscal_year: str = None) -> Dict[str, Any]:
    """Get capital efficiency metrics (ROCE and IRR)."""
    try:
        # calculate_irr reads Payment Entry -- GL Entry alone (ROCE's source)
        # under-covers it.
        frappe.has_permission("GL Entry", "read", throw=True)
        frappe.has_permission("Payment Entry", "read", throw=True)
        from insights.ml.breakeven_engine import BreakevenEngine
        engine = BreakevenEngine(period=period, fiscal_year=fiscal_year)
        return success({
            "roce": engine.calculate_roce(),
            "irr": engine.calculate_irr(),
        })
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e), exc=e)


@frappe.whitelist()
def breakeven_summary(period: str = "Quarterly", fiscal_year: str = None) -> Dict[str, Any]:
    """Get complete break-even summary including all sub-analyses."""
    try:
        # Aggregates every sub-analysis below it (item/employee/cash-flow/
        # ROCE/IRR breakeven) -- a Sales-Invoice-only gate let any user with
        # just Sales Invoice read pull full company payroll-by-department
        # (calculate_employee_breakeven -> Salary Slip), GL-derived ROCE, and
        # cash-flow/IRR (Payment Entry) with no permission on any of those
        # doctypes. Gate on the full read surface, matching item_breakeven,
        # employee_breakeven, and capital_efficiency above.
        frappe.has_permission("Sales Invoice", "read", throw=True)
        frappe.has_permission("Item", "read", throw=True)
        frappe.has_permission("GL Entry", "read", throw=True)
        frappe.has_permission("Salary Slip", "read", throw=True)
        frappe.has_permission("Sales Order", "read", throw=True)
        frappe.has_permission("Payment Entry", "read", throw=True)
        from insights.ml.breakeven_engine import BreakevenEngine
        engine = BreakevenEngine(period=period, fiscal_year=fiscal_year)
        result = engine.get_breakeven_summary()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e), exc=e)


@frappe.whitelist()
def item_lead_breakeven_ratio(period: str = "Quarterly", fiscal_year: str = None) -> Dict[str, Any]:
    """Get leads needed per item based on break-even quantity and conversion rate."""
    try:
        # get_item_lead_breakeven_ratio calls calculate_item_breakeven (Item,
        # GL Entry too) and reads Lead directly for conversion rate.
        frappe.has_permission("Sales Invoice", "read", throw=True)
        frappe.has_permission("Item", "read", throw=True)
        frappe.has_permission("GL Entry", "read", throw=True)
        frappe.has_permission("Lead", "read", throw=True)
        from insights.ml.breakeven_engine import BreakevenEngine
        engine = BreakevenEngine(period=period, fiscal_year=fiscal_year)
        result = engine.get_item_lead_breakeven_ratio()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e), exc=e)
