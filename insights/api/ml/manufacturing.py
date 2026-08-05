# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Manufacturing Intelligence API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any
from insights.api.response import success, error


@frappe.whitelist()
def get_manufacturing_overview(period: str = "YTD") -> Dict[str, Any]:
    """Get manufacturing overview"""
    try:
        frappe.has_permission("Work Order", "read", throw=True)
        from insights.ml.manufacturing_intelligence import (
            get_manufacturing_overview as _get_manufacturing_overview,
        )
    
        result = _get_manufacturing_overview(period=period)
        return success(result) if isinstance(result, dict) and "status" not in result else result
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_oee_analysis(period: str = "YTD") -> Dict[str, Any]:
    """Get OEE analysis"""
    try:
        frappe.has_permission("Work Order", "read", throw=True)
        from insights.ml.manufacturing_intelligence import (
            get_oee_analysis as _get_oee_analysis,
        )
    
        result = _get_oee_analysis(period=period)
        return success(result) if isinstance(result, dict) and "status" not in result else result
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_capacity_analysis() -> Dict[str, Any]:
    """Get capacity analysis"""
    try:
        frappe.has_permission("Work Order", "read", throw=True)
        from insights.ml.manufacturing_intelligence import (
            get_capacity_analysis as _get_capacity_analysis,
        )
    
        result = _get_capacity_analysis()
        return success(result) if isinstance(result, dict) and "status" not in result else result
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_production_forecast() -> Dict[str, Any]:
    """Get production forecast"""
    try:
        frappe.has_permission("Work Order", "read", throw=True)
        from insights.ml.manufacturing_intelligence import (
            get_production_forecast as _get_production_forecast,
        )
    
        result = _get_production_forecast()
        return success(result) if isinstance(result, dict) and "status" not in result else result
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_manufacturing_recommendations() -> Dict[str, Any]:
    """Get manufacturing recommendations"""
    try:
        frappe.has_permission("Work Order", "read", throw=True)
        from insights.ml.manufacturing_intelligence import (
            get_manufacturing_recommendations as _get_manufacturing_recommendations,
        )
    
        result = _get_manufacturing_recommendations()
        return success(result) if isinstance(result, dict) and "status" not in result else result
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_manufacturing_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")

    if metric == "open_work_orders":
        frappe.has_permission("Work Order", throw=True)
        db_filters = {"docstatus": 1, "status": ("not in", ["Completed", "Cancelled", "Stopped"])}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Work Order",
            filters=db_filters,
            fields=["name", "production_item", "qty", "produced_qty", "planned_start_date", "planned_end_date", "status"],
            start=start, page_length=page_size, order_by="planned_start_date asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Work Order", "fieldname": "name", "fieldtype": "Link", "options": "Work Order"},
                {"label": "Item", "fieldname": "production_item", "fieldtype": "Link", "options": "Item"},
                {"label": "Qty", "fieldname": "qty", "fieldtype": "Float"},
                {"label": "Produced", "fieldname": "produced_qty", "fieldtype": "Float"},
                {"label": "Start", "fieldname": "planned_start_date", "fieldtype": "Date"},
                {"label": "End", "fieldname": "planned_end_date", "fieldtype": "Date"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Work Order", filters=db_filters),
        }

    if metric == "completed_work_orders":
        frappe.has_permission("Work Order", throw=True)
        period = f.get("period", "30d")
        days = {"7d": 7, "30d": 30, "90d": 90, "12m": 365}.get(period, 30)
        cutoff = frappe.utils.add_days(frappe.utils.today(), -days)
        db_filters = {"docstatus": 1, "status": "Completed", "modified": (">=", cutoff)}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Work Order",
            filters=db_filters,
            fields=["name", "production_item", "qty", "produced_qty", "planned_end_date"],
            start=start, page_length=page_size, order_by="modified desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Work Order", "fieldname": "name", "fieldtype": "Link", "options": "Work Order"},
                {"label": "Item", "fieldname": "production_item", "fieldtype": "Link", "options": "Item"},
                {"label": "Qty", "fieldname": "qty", "fieldtype": "Float"},
                {"label": "Produced", "fieldname": "produced_qty", "fieldtype": "Float"},
                {"label": "End Date", "fieldname": "planned_end_date", "fieldtype": "Date"},
            ],
            "rows": rows,
            "total": frappe.db.count("Work Order", filters=db_filters),
        }

    if metric == "material_requests":
        frappe.has_permission("Material Request", throw=True)
        db_filters = {"docstatus": 1, "status": ("in", ["Pending", "Partially Ordered"])}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Material Request",
            filters=db_filters,
            fields=["name", "material_request_type", "transaction_date", "schedule_date", "status"],
            start=start, page_length=page_size, order_by="schedule_date asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Request", "fieldname": "name", "fieldtype": "Link", "options": "Material Request"},
                {"label": "Type", "fieldname": "material_request_type", "fieldtype": "Data"},
                {"label": "Date", "fieldname": "transaction_date", "fieldtype": "Date"},
                {"label": "Required By", "fieldname": "schedule_date", "fieldtype": "Date"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Material Request", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
