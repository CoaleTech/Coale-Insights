# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ESG Intelligence API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any
from insights.api.response import success, error


@frappe.whitelist()
def get_esg_overview(period: str = "YTD") -> Dict[str, Any]:
    """Get ESG intelligence overview.

    Removed 2026-08-04: esg_intelligence.py's ESGIntelligence.get_esg_overview
    returned fabricated data (hardcoded board/ethics/risk/transparency/audit
    scores weighted into a fake overall score; synthetic trend lines; fake
    targets and board composition). Returns an explicit not_implemented status
    until the module computes real metrics from source doctypes. See
    plan-eng-review D3.1.
    """
    return success({"status": "not_implemented", "message": "ESG intelligence is not yet backed by real data"})


@frappe.whitelist()
def export_esg_report(format: str = "pdf") -> Dict[str, Any]:
    """Export ESG report. Removed 2026-08-04 alongside get_esg_overview — see above."""
    return success({"status": "not_implemented", "message": "ESG intelligence is not yet backed by real data"})


# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_esg_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size

    if metric == "employees_diversity":
        frappe.has_permission("Employee", throw=True)
        db_filters = {"status": "Active"}
        rows = frappe.get_list(
            "Employee",
            filters=db_filters,
            fields=["name", "employee_name", "department", "gender", "date_of_joining"],
            start=start, page_length=page_size, order_by="department asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Employee", "fieldname": "name", "fieldtype": "Link", "options": "Employee"},
                {"label": "Name", "fieldname": "employee_name", "fieldtype": "Data"},
                {"label": "Department", "fieldname": "department", "fieldtype": "Data"},
                {"label": "Gender", "fieldname": "gender", "fieldtype": "Data"},
                {"label": "Joined", "fieldname": "date_of_joining", "fieldtype": "Date"},
            ],
            "rows": rows,
            "total": frappe.db.count("Employee", filters=db_filters),
        }

    if metric == "supplier_count":
        frappe.has_permission("Supplier", throw=True)
        db_filters = {"disabled": 0}
        rows = frappe.get_list(
            "Supplier",
            filters=db_filters,
            fields=["name", "supplier_name", "supplier_group", "supplier_type", "country"],
            start=start, page_length=page_size, order_by="supplier_name asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Supplier", "fieldname": "name", "fieldtype": "Link", "options": "Supplier"},
                {"label": "Name", "fieldname": "supplier_name", "fieldtype": "Data"},
                {"label": "Group", "fieldname": "supplier_group", "fieldtype": "Data"},
                {"label": "Country", "fieldname": "country", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Supplier", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
