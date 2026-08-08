# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Procurement Intelligence API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any
from insights.api.response import success, error
from insights.ml.base import sanitize_for_json


@frappe.whitelist()
def get_procurement_insights() -> Dict[str, Any]:
    """Get procurement insights overview"""
    try:
        frappe.has_permission("Purchase Order", "read", throw=True)
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model.predict()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def procurement_intelligence(refresh: bool = False) -> Dict[str, Any]:
    """Get comprehensive procurement intelligence, computed inline on this request.

    Returns the flat `{status, spend_overview, supplier_performance, ...}` envelope
    the frontend decoder expects. Runs in the gunicorn web worker; a cold cache can
    outlive a gateway read timeout and reach the browser as a 502.
    """
    try:
        frappe.has_permission("Purchase Order", "read", throw=True)
        from insights.ml.procurement_intelligence import ProcurementIntelligence

        model = ProcurementIntelligence()
        result = model.train() if refresh else model.predict(allow_train=True)
        return sanitize_for_json(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "procurement_intelligence error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def train_procurement_intelligence() -> Dict[str, Any]:
    """Train procurement intelligence models"""
    try:
        frappe.has_permission("Purchase Order", "read", throw=True)
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model.train()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_spend_overview() -> Dict[str, Any]:
    """Get procurement spend overview"""
    try:
        frappe.has_permission("Purchase Order", "read", throw=True)
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model._calculate_spend_overview()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_supplier_performance() -> Dict[str, Any]:
    """Get supplier performance analysis"""
    try:
        frappe.has_permission("Purchase Order", "read", throw=True)
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model._calculate_supplier_performance()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_purchase_analytics() -> Dict[str, Any]:
    """Get purchase analytics"""
    try:
        frappe.has_permission("Purchase Order", "read", throw=True)
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model._analyze_purchase_cycles()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_price_intelligence() -> Dict[str, Any]:
    """Get price intelligence analysis"""
    try:
        frappe.has_permission("Purchase Order", "read", throw=True)
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model._calculate_price_intelligence()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_procurement_risks() -> Dict[str, Any]:
    """Get procurement risk analysis"""
    try:
        frappe.has_permission("Purchase Order", "read", throw=True)
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model._assess_procurement_risks()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_procurement_forecast() -> Dict[str, Any]:
    """Get procurement forecasting"""
    try:
        frappe.has_permission("Purchase Order", "read", throw=True)
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model._generate_procurement_forecast()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_procurement_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")

    if metric == "total_pos":
        frappe.has_permission("Purchase Order", throw=True)
        db_filters = {"docstatus": 1}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Purchase Order",
            filters=db_filters,
            fields=["name", "supplier", "transaction_date", "schedule_date", "grand_total", "status"],
            start=start, page_length=page_size, order_by="transaction_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "PO", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Order"},
                {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
                {"label": "Date", "fieldname": "transaction_date", "fieldtype": "Date"},
                {"label": "Expected", "fieldname": "schedule_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Purchase Order", filters=db_filters),
        }

    if metric == "pending_pos":
        frappe.has_permission("Purchase Order", throw=True)
        db_filters = {"docstatus": 1, "status": ("not in", ["Completed", "Cancelled", "Closed"])}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Purchase Order",
            filters=db_filters,
            fields=["name", "supplier", "transaction_date", "schedule_date", "grand_total", "status", "per_received"],
            start=start, page_length=page_size, order_by="schedule_date asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "PO", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Order"},
                {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
                {"label": "Expected", "fieldname": "schedule_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
                {"label": "% Received", "fieldname": "per_received", "fieldtype": "Percent"},
            ],
            "rows": rows,
            "total": frappe.db.count("Purchase Order", filters=db_filters),
        }

    if metric == "overdue_pos":
        frappe.has_permission("Purchase Order", throw=True)
        db_filters = {
            "docstatus": 1,
            "schedule_date": ("<", frappe.utils.today()),
            "status": ("not in", ["Completed", "Cancelled", "Closed"]),
        }
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Purchase Order",
            filters=db_filters,
            fields=["name", "supplier", "transaction_date", "schedule_date", "grand_total", "per_received"],
            start=start, page_length=page_size, order_by="schedule_date asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "PO", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Order"},
                {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
                {"label": "Expected", "fieldname": "schedule_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "% Received", "fieldname": "per_received", "fieldtype": "Percent"},
            ],
            "rows": rows,
            "total": frappe.db.count("Purchase Order", filters=db_filters),
        }

    if metric == "supplier_performance":
        frappe.has_permission("Purchase Order", throw=True)
        supplier = f.get("supplier")
        db_filters = {"docstatus": 1}
        if company:
            db_filters["company"] = company
        if supplier:
            db_filters["supplier"] = supplier
        rows = frappe.get_list(
            "Purchase Order",
            filters=db_filters,
            fields=["name", "supplier", "transaction_date", "schedule_date", "grand_total", "status"],
            start=start, page_length=page_size, order_by="transaction_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "PO", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Order"},
                {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
                {"label": "Date", "fieldname": "transaction_date", "fieldtype": "Date"},
                {"label": "Expected", "fieldname": "schedule_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Purchase Order", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
