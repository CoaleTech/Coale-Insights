# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Executive Intelligence API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any, List
from insights.api.response import success, error


def _compute_executive_summary(period: str = "YTD") -> Dict[str, Any]:
    """Worker-side computation. Measured at ~23s, so never run in a request."""
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        return success(model.get_executive_summary(period))
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_summary(period: str = "YTD") -> Dict[str, Any]:
    """Get executive summary, computing on a worker when the cache is cold."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.api.ml import async_compute

        return async_compute.serve(
            key=f"executive_summary:{period}",
            method="insights.api.ml.executive._compute_executive_summary",
            kwargs={"period": period},
            permission=("Sales Invoice", "read"),
        )
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_business_health_score() -> Dict[str, Any]:
    """Get business health score"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        summary = model.get_executive_summary("YTD")
        health = summary.get("business_health", summary.get("health_score", {}))
        return success(health)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_kpis(department: str = None, period: str = "YTD") -> Dict[str, Any]:
    """Get executive KPIs"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        if department:
            result = model.get_department_deep_dive(department, period)
        else:
            result = model.get_executive_summary(period)
        kpis = result.get("kpis", result)
        return success(kpis)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_alerts() -> Dict[str, Any]:
    """Get executive alerts"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model._get_executive_alerts()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_trends(period: str = "YTD") -> Dict[str, Any]:
    """Get executive trends"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model._get_trend_sparklines(period)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_insights(query: str, complexity: str = "Medium") -> Dict[str, Any]:
    """Get executive insights based on query"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model.get_executive_summary("YTD")
        return success({"query": query, "complexity": complexity, "insights": result})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_department_insights(department: str, query: str = None) -> Dict[str, Any]:
    """Get department insights"""
    try:
        # `department` selects which domain's data comes back (see
        # ExecutiveIntelligence.get_department_deep_dive) — a single fixed
        # "Sales Invoice" gate let a Sales-only user pass department="hr" and
        # read payroll data. Gate on the doctype the requested department
        # actually exposes. See outside-voice finding 2.
        _DEPARTMENT_DOCTYPE = {
            "financial": "GL Entry",
            "sales": "Sales Invoice",
            "customer": "Customer",
            "operations": "Purchase Order",
            "risk": "Sales Invoice",
            "hr": "Salary Slip",
            "manufacturing": "Work Order",
        }
        frappe.has_permission(_DEPARTMENT_DOCTYPE.get(department, "Sales Invoice"), "read", throw=True)
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model.get_department_deep_dive(department, "YTD")
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_strategic_recommendations(focus_area: str = "overall") -> Dict[str, Any]:
    """Get strategic recommendations"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        summary = model.get_executive_summary("YTD")
        recs = summary.get("recommendations", summary.get("narrative", ""))
        return success({"focus_area": focus_area, "recommendations": recs})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def analyze_executive_query(query: str) -> Dict[str, Any]:
    """Analyze executive query"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model.get_executive_summary("YTD")
        return success({"query": query, "analysis": result})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def generate_executive_report(report_type: str = "daily") -> Dict[str, Any]:
    """Generate and persist a real executive report (data + PDF + DB record).

    Previously computed a live summary and returned it without saving
    anything -- the button showed a success toast but nothing appeared in
    the reports list, because nothing was ever written to the database.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.reports.executive_reports import ExecutiveReports
        reports = ExecutiveReports()
        if report_type == "daily":
            result = reports.generate_daily_executive_report()
        elif report_type == "weekly":
            result = reports.generate_weekly_executive_report()
        elif report_type == "monthly":
            result = reports.generate_monthly_executive_report()
        else:
            return error(f"Unknown report type: {report_type}")
        if not result.get("success"):
            return error(result.get("error") or "Report generation failed")
        return success({"report_name": result["report_name"], "report_type": report_type})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def send_executive_report(report_type: str = "daily", recipients: List[str] = None) -> Dict[str, Any]:
    """Generate a fresh report and email it.

    Delegates to the real `send_executive_report_email`, which previously
    was never called -- this endpoint always returned "not yet configured"
    regardless of whether email was actually set up, and the frontend didn't
    check the response, so it showed a green success toast either way.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.reports.executive_reports import send_executive_report_email
        if not recipients:
            # The current user, not a placeholder inbox: the real function's
            # own default was ["ceo@company.com", "coo@company.com"], which
            # cannot exist on any real deployment.
            recipients = [frappe.session.user] if frappe.session.user != "Guest" else []
        result = send_executive_report_email(report_type=report_type, recipients=recipients)
        if result.get("error"):
            return error(result["error"])
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_reports_status() -> Dict[str, Any]:
    """Get executive reports status: the real schedule from `hooks.py`."""
    try:
        from insights.reports.executive_reports import ExecutiveReports
        return success(ExecutiveReports().schedule_automated_reports())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_recent_executive_reports(limit: int = 10) -> Dict[str, Any]:
    """Get recent executive reports from the real `Executive Report` doctype."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        rows = frappe.get_all(
            "Executive Report",
            fields=["name as id", "report_type", "report_date", "status", "creation as created"],
            order_by="creation desc",
            limit_page_length=int(limit),
        )
        return success({"reports": rows, "count": len(rows)})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def download_executive_report(report_id: str) -> Dict[str, Any]:
    """Return the real download URL for a generated report's PDF."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        if not frappe.db.exists("Executive Report", report_id):
            return error(f"Report {report_id} not found")
        pdf_file = frappe.db.get_value("Executive Report", report_id, "pdf_file")
        if not pdf_file:
            return error("No PDF is attached to this report")
        return success({"download_url": pdf_file})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def test_executive_intelligence_data() -> Dict[str, Any]:
    """Test executive intelligence data"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.executive_intelligence import ExecutiveIntelligence
        model = ExecutiveIntelligence()
        result = model.get_executive_summary("YTD")
        return success({"test": "passed", "data_available": bool(result)})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def preview_executive_report_data(report_type: str = "daily") -> Dict[str, Any]:
    """Preview the most recent generated report of this type.

    Previously returned `{report_type, preview: <live executive summary>}`,
    a shape the frontend never read -- it reads `executive_summary`,
    `key_metrics`, `alerts`, `modules_with_data` directly on the response,
    so the preview modal always rendered empty. Generates one on demand if
    none exists yet, rather than re-running the pipeline on every preview.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        import json
        existing = frappe.get_all(
            "Executive Report",
            filters={"report_type": report_type, "status": "Generated"},
            fields=["name"],
            order_by="creation desc",
            limit_page_length=1,
        )
        if existing:
            raw = frappe.db.get_value("Executive Report", existing[0].name, "report_data")
            report_data = json.loads(raw) if raw else {}
        else:
            from insights.reports.executive_reports import ExecutiveReports
            reports = ExecutiveReports()
            if report_type == "daily":
                result = reports.generate_daily_executive_report()
            elif report_type == "weekly":
                result = reports.generate_weekly_executive_report()
            elif report_type == "monthly":
                result = reports.generate_monthly_executive_report()
            else:
                return error(f"Unknown report type: {report_type}")
            if not result.get("success"):
                return error(result.get("error") or "Could not generate preview")
            report_data = result["report_data"]

        modules_with_data = [
            module for module, data in (report_data.get("detailed_data") or {}).items() if data
        ]
        from frappe.defaults import get_user_default
        company = get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
        currency = (
            frappe.db.get_value("Company", company, "default_currency")
            or frappe.db.get_single_value("System Settings", "default_currency")
            or "USD"
        )
        return success({
            "executive_summary": report_data.get("executive_summary", ""),
            "key_metrics": report_data.get("key_metrics", {}),
            "alerts": report_data.get("alerts", []),
            "modules_with_data": modules_with_data,
            "currency": currency,
        })
    except frappe.PermissionError:
        raise
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
