# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
HR Intelligence API Endpoints.

Pure-Ibis rewrite of the HR surface. Every aggregate compiles to one SQL
statement and runs inside MariaDB; the Python process only materialises the
final, already-aggregated result (a handful of rows in the worst case).

Permission gates:
    get_hr_overview gates on BOTH ``Employee`` AND ``Salary Slip`` because
    the underlying payroll aggregates touch Salary Slip; an Employee-read
    user must not be able to see payroll. Enforced by
    test_ml_permission_gates.test_hr_overview_checks_employee_and_salary_slip_permission.
    Other endpoints gate on Employee read (the doctype they actually read).
"""

from __future__ import annotations

from typing import Any, Dict

import frappe
from frappe import _

from insights.api.ml.utils import cached_run, run

# ────────────────────────────────────────────────────────────────────────────
# Whitelisted endpoints
# ────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_hr_overview(period: str = "YTD") -> Dict[str, Any]:
    """Comprehensive HR overview -- headcount, attrition, payroll, comp.
    Cached for 1 hour per period.

    Permission: BOTH ``Employee`` AND ``Salary Slip`` (see module docstring).
    """
    frappe.has_permission("Employee", "read", throw=True)
    frappe.has_permission("Salary Slip", "read", throw=True)

    def _compute() -> Dict[str, Any]:
        from insights.ml.hr_intelligence import HRIntelligence

        result = run(lambda: HRIntelligence(period=period).train(), "HR overview")
        if result.get("status") == "success":
            company = frappe.defaults.get_user_default("Company")
            result.setdefault("data", {})
            result["data"]["currency"] = (
                frappe.db.get_value("Company", company, "default_currency") if company else None
            ) or frappe.db.get_default("currency") or ""
        return result

    return cached_run(_compute, cache_key=f"insights_ml_hr_overview:{period}")


@frappe.whitelist()
def get_headcount_analytics(period: str = "YTD") -> Dict[str, Any]:
    """Headcount slice of the HR overview."""
    frappe.has_permission("Employee", "read", throw=True)
    from insights.ml.hr_intelligence import HRIntelligence

    return run(
        lambda: HRIntelligence(period=period)._analyze_headcount(),
        "HR headcount analytics",
    )


@frappe.whitelist()
def get_attrition_analytics(period: str = "YTD") -> Dict[str, Any]:
    """Attrition slice of the HR overview (rate + voluntary/involuntary split)."""
    frappe.has_permission("Employee", "read", throw=True)
    from insights.ml.hr_intelligence import HRIntelligence

    return run(
        lambda: HRIntelligence(period=period)._analyze_attrition(),
        "HR attrition analytics",
    )


@frappe.whitelist()
def get_payroll_analytics(period: str = "YTD") -> Dict[str, Any]:
    """Payroll slice -- total cost, average salary, deduction rate, by dept."""
    frappe.has_permission("Salary Slip", "read", throw=True)
    from insights.ml.hr_intelligence import HRIntelligence

    return run(
        lambda: HRIntelligence(period=period)._analyze_payroll(),
        "HR payroll analytics",
    )


@frappe.whitelist()
def get_workforce_planning() -> Dict[str, Any]:
    """Hiring-forecast + department composition for the planning tab."""
    frappe.has_permission("Employee", "read", throw=True)
    from insights.ml.hr_intelligence import HRIntelligence

    return run(
        lambda: HRIntelligence(period="YTD")._forecast_hiring_needs(),
        "HR workforce planning",
    )


@frappe.whitelist()
def get_hr_insights(query: str, complexity: str = "Medium") -> Dict[str, Any]:
    """Free-text HR query -- returns the standard overview so the chat agent
    has the same numbers as the dashboard."""
    frappe.has_permission("Employee", "read", throw=True)
    from insights.ml.hr_intelligence import HRIntelligence

    return run(
        lambda: {
            "query": query,
            "complexity": complexity,
            "insights": HRIntelligence(period="YTD")._compress_for_chat(),
        },
        "HR insights",
    )


@frappe.whitelist()
def get_talent_analytics(focus_area: str = "retention") -> Dict[str, Any]:
    """Talent / retention focus area. ``focus_area`` is accepted for backward
    compatibility and ignored: the only supported panel today is retention,
    which the overview's attrition and engagement slices already cover."""
    frappe.has_permission("Employee", "read", throw=True)
    from insights.ml.hr_intelligence import HRIntelligence

    return run(
        lambda: {"focus_area": focus_area, "analytics": HRIntelligence(period="YTD")._analyze_attrition()},
        "HR talent analytics",
    )


@frappe.whitelist()
def analyze_hr_query(query: str) -> Dict[str, Any]:
    """Free-text HR query -- same body as ``get_hr_insights`` today (the chat
    agent runs both paths through the same code)."""
    frappe.has_permission("Employee", "read", throw=True)
    from insights.ml.hr_intelligence import HRIntelligence

    return run(
        lambda: {"query": query, "analysis": HRIntelligence(period="YTD")._compress_for_chat()},
        "HR query analysis",
    )


# ────────────────────────────────────────────────────────────────────────────
# Drill-Down
# ────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_hr_detail(metric: str, filters: str) -> dict:
    """
    Returns raw ERPNext records for the clicked HR metric.

    metric keys:
      total_employees   -- all active employees
      recent_exits      -- employees relieved in the period
      dept_employees    -- employees filtered by department
      employment_type   -- employees filtered by employment_type
      dept_composition  -- employees by department (breakdown click)
    """
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size

    if metric == "total_employees":
        return _hr_employee_list({"status": "Active"}, start, page_size)

    if metric == "recent_exits":
        company = f.get("company") or frappe.defaults.get_user_default("company")
        db_filters = {"docstatus": 1, "status": "Left"}
        if company:
            db_filters["company"] = company
        return _hr_employee_list(db_filters, start, page_size)

    if metric == "dept_employees":
        dept = f.get("department")
        db_filters = {"status": "Active"}
        if dept:
            db_filters["department"] = dept
        return _hr_employee_list(db_filters, start, page_size)

    if metric == "employment_type":
        emp_type = f.get("employment_type")
        db_filters = {"status": "Active"}
        if emp_type:
            db_filters["employment_type"] = emp_type
        return _hr_employee_list(db_filters, start, page_size)

    if metric == "dept_composition":
        dept = f.get("department")
        db_filters = {"status": "Active"}
        if dept:
            db_filters["department"] = dept
        return _hr_employee_list(db_filters, start, page_size)

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)


def _hr_employee_list(db_filters: dict, start: int, page_size: int) -> dict:
    """Fetch employees with permission-safe get_list."""
    frappe.has_permission("Employee", throw=True)

    rows = frappe.get_list(
        "Employee",
        filters=db_filters,
        fields=[
            "name",
            "employee_name",
            "department",
            "designation",
            "employment_type",
            "date_of_joining",
            "status",
        ],
        start=start,
        page_length=page_size,
        order_by="employee_name asc",
        ignore_permissions=False,
    )
    total = frappe.db.count("Employee", filters=db_filters)

    return {
        "columns": [
            {"label": "ID", "fieldname": "name", "fieldtype": "Link", "options": "Employee"},
            {"label": "Name", "fieldname": "employee_name", "fieldtype": "Data"},
            {"label": "Department", "fieldname": "department", "fieldtype": "Data"},
            {"label": "Designation", "fieldname": "designation", "fieldtype": "Data"},
            {"label": "Employment Type", "fieldname": "employment_type", "fieldtype": "Data"},
            {"label": "Joined", "fieldname": "date_of_joining", "fieldtype": "Date"},
            {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
        ],
        "rows": rows,
        "total": total,
    }
