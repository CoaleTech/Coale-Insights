# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Risk Intelligence API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any
from insights.api.ml.utils import cached_run
from insights.api.serialization import sanitize_for_json


@frappe.whitelist()
def risk_intelligence(refresh: bool = False, date_filter: str = "12m") -> Dict[str, Any]:
    """Get risk intelligence analysis, cached for 1 hour."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.risk_intelligence import run_risk_intelligence
        return cached_run(
            lambda: sanitize_for_json(run_risk_intelligence(refresh=refresh)),
            cache_key="insights_ml_risk_intelligence",
        )
    except frappe.PermissionError:
        raise
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_risk_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")
    today = frappe.utils.today()

    if metric == "overdue_invoices":
        frappe.has_permission("Sales Invoice", throw=True)
        db_filters = {
            "docstatus": 1,
            "outstanding_amount": (">", 0),
            "due_date": ("<", today),
        }
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "customer", "posting_date", "due_date", "outstanding_amount"],
            start=start, page_length=page_size, order_by="due_date asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Posted", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Due", "fieldname": "due_date", "fieldtype": "Date"},
                {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Invoice", filters=db_filters),
        }

    if metric == "overdue_payables":
        frappe.has_permission("Purchase Invoice", throw=True)
        db_filters = {
            "docstatus": 1,
            "outstanding_amount": (">", 0),
            "due_date": ("<", today),
        }
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Purchase Invoice",
            filters=db_filters,
            fields=["name", "supplier", "posting_date", "due_date", "outstanding_amount"],
            start=start, page_length=page_size, order_by="due_date asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Bill", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Invoice"},
                {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
                {"label": "Posted", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Due", "fieldname": "due_date", "fieldtype": "Date"},
                {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Purchase Invoice", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
