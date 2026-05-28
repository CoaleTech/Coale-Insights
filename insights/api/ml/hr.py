# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
HR Intelligence API Endpoints
"""

import frappe
from typing import Dict, Any
from insights.api.response import success, error


@frappe.whitelist()
def get_hr_overview(period: str = "YTD") -> Dict[str, Any]:
    """Get HR overview"""
    try:
        from insights.ml.hr_intelligence import HRIntelligence
        model = HRIntelligence()
        result = model.get_hr_overview(period)
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_headcount_analytics(period: str = "YTD") -> Dict[str, Any]:
    """Get headcount analytics"""
    try:
        from insights.ml.hr_intelligence import get_headcount_analytics as _get_headcount
        result = _get_headcount(period)
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_attrition_analytics(period: str = "YTD") -> Dict[str, Any]:
    """Get attrition analytics"""
    try:
        from insights.ml.hr_intelligence import get_attrition_prediction
        result = get_attrition_prediction()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_payroll_analytics(period: str = "YTD") -> Dict[str, Any]:
    """Get payroll analytics"""
    try:
        from insights.ml.hr_intelligence import HRIntelligence
        model = HRIntelligence()
        overview = model.get_hr_overview(period)
        payroll = overview.get("payroll", overview)
        return success(payroll)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_workforce_planning() -> Dict[str, Any]:
    """Get workforce planning insights"""
    try:
        from insights.ml.hr_intelligence import HRIntelligence
        model = HRIntelligence()
        overview = model.get_hr_overview("YTD")
        planning = overview.get("workforce_planning", overview.get("predictions", {}))
        return success(planning)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_hr_insights(query: str, complexity: str = "Medium") -> Dict[str, Any]:
    """Get HR insights based on query"""
    try:
        from insights.ml.hr_intelligence import HRIntelligence
        model = HRIntelligence()
        result = model.get_hr_overview("YTD")
        return success({"query": query, "complexity": complexity, "insights": result})
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_talent_analytics(focus_area: str = "retention") -> Dict[str, Any]:
    """Get talent analytics"""
    try:
        from insights.ml.hr_intelligence import get_hr_recommendations
        result = get_hr_recommendations()
        return success({"focus_area": focus_area, "analytics": result})
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def analyze_hr_query(query: str) -> Dict[str, Any]:
    """Analyze HR query"""
    try:
        from insights.ml.hr_intelligence import HRIntelligence
        model = HRIntelligence()
        result = model.get_hr_overview("YTD")
        return success({"query": query, "analysis": result})
    except Exception as e:
        return error(str(e))

# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_hr_detail(metric: str, filters: str) -> dict:
    """
    Returns raw ERPNext records for the clicked HR metric.

    metric keys:
      total_employees   — all active employees
      recent_exits      — employees relieved in the period
      dept_employees    — employees filtered by department
      employment_type   — employees filtered by employment_type
      dept_composition  — employees by department (breakdown click)
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
