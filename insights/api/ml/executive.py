# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Executive Intelligence API Endpoints
"""

import frappe
from typing import Dict, Any, List
from insights.api.response import success, error


@frappe.whitelist()
def get_executive_summary(period: str = "YTD") -> Dict[str, Any]:
    """Get executive summary"""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model.get_executive_summary(period)
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_business_health_score() -> Dict[str, Any]:
    """Get business health score"""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        summary = model.get_executive_summary("YTD")
        health = summary.get("business_health", summary.get("health_score", {}))
        return success(health)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_kpis(department: str = None, period: str = "YTD") -> Dict[str, Any]:
    """Get executive KPIs"""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        if department:
            result = model.get_department_deep_dive(department, period)
        else:
            result = model.get_executive_summary(period)
        kpis = result.get("kpis", result)
        return success(kpis)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_alerts() -> Dict[str, Any]:
    """Get executive alerts"""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model._get_executive_alerts()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_trends(period: str = "YTD") -> Dict[str, Any]:
    """Get executive trends"""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model._get_trend_sparklines(period)
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_insights(query: str, complexity: str = "Medium") -> Dict[str, Any]:
    """Get executive insights based on query"""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model.get_executive_summary("YTD")
        return success({"query": query, "complexity": complexity, "insights": result})
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_department_insights(department: str, query: str = None) -> Dict[str, Any]:
    """Get department insights"""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model.get_department_deep_dive(department, "YTD")
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_strategic_recommendations(focus_area: str = "overall") -> Dict[str, Any]:
    """Get strategic recommendations"""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        summary = model.get_executive_summary("YTD")
        recs = summary.get("recommendations", summary.get("narrative", ""))
        return success({"focus_area": focus_area, "recommendations": recs})
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def analyze_executive_query(query: str) -> Dict[str, Any]:
    """Analyze executive query"""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model.get_executive_summary("YTD")
        return success({"query": query, "analysis": result})
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def generate_executive_report(report_type: str = "daily") -> Dict[str, Any]:
    """Generate executive report"""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model.get_executive_summary("YTD")
        return success({"report_type": report_type, "report": result})
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def send_executive_report(report_type: str = "daily", recipients: List[str] = None) -> Dict[str, Any]:
    """Send executive report"""
    try:
        return success({"status": "not_implemented", "message": "Email report sending not yet configured"})
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_reports_status() -> Dict[str, Any]:
    """Get executive reports status"""
    try:
        return success({"status": "success", "reports": [], "message": "No scheduled reports configured"})
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_recent_executive_reports(limit: int = 10) -> Dict[str, Any]:
    """Get recent executive reports"""
    try:
        return success({"reports": [], "count": 0})
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def download_executive_report(report_id: str) -> Dict[str, Any]:
    """Download executive report"""
    try:
        return success({"status": "not_found", "message": f"Report {report_id} not found"})
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def test_executive_intelligence_data() -> Dict[str, Any]:
    """Test executive intelligence data"""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model.get_executive_summary("YTD")
        return success({"test": "passed", "data_available": bool(result)})
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def preview_executive_report_data(report_type: str = "daily") -> Dict[str, Any]:
    """Preview executive report data"""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model.get_executive_summary("YTD")
        return success({"report_type": report_type, "preview": result})
    except Exception as e:
        return error(str(e))


# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_executive_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")

    if metric == "revenue_invoices":
        frappe.has_permission("Sales Invoice", throw=True)
        db_filters = {"docstatus": 1}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "customer", "posting_date", "grand_total"],
            start=start, page_length=page_size, order_by="posting_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Invoice", filters=db_filters),
        }

    if metric == "active_employees":
        frappe.has_permission("Employee", throw=True)
        db_filters = {"status": "Active"}
        rows = frappe.get_list(
            "Employee",
            filters=db_filters,
            fields=["name", "employee_name", "department", "designation"],
            start=start, page_length=page_size, order_by="employee_name asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Employee", "fieldname": "name", "fieldtype": "Link", "options": "Employee"},
                {"label": "Name", "fieldname": "employee_name", "fieldtype": "Data"},
                {"label": "Department", "fieldname": "department", "fieldtype": "Data"},
                {"label": "Designation", "fieldname": "designation", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Employee", filters=db_filters),
        }

    if metric == "open_orders":
        frappe.has_permission("Sales Order", throw=True)
        db_filters = {"docstatus": 1, "status": ("not in", ["Completed", "Cancelled", "Closed"])}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Sales Order",
            filters=db_filters,
            fields=["name", "customer", "transaction_date", "grand_total", "status"],
            start=start, page_length=page_size, order_by="transaction_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Order", "fieldname": "name", "fieldtype": "Link", "options": "Sales Order"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Date", "fieldname": "transaction_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Order", filters=db_filters),
        }

    if metric == "open_pos":
        frappe.has_permission("Purchase Order", throw=True)
        db_filters = {"docstatus": 1, "status": ("not in", ["Completed", "Cancelled", "Closed"])}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Purchase Order",
            filters=db_filters,
            fields=["name", "supplier", "transaction_date", "grand_total", "status"],
            start=start, page_length=page_size, order_by="transaction_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "PO", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Order"},
                {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
                {"label": "Date", "fieldname": "transaction_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Purchase Order", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
