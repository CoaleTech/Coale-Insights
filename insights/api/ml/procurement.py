# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Procurement Intelligence API Endpoints — Ibis rewrite.

Each endpoint builds one or two Ibis expressions (which compile to SQL
and execute inside MariaDB) and wraps the result in the standard
`success` envelope via `insights.api.ml.utils.run`. No background job, no
fork. `procurement_intelligence` (the full dashboard payload) is cached
for 1 hour via `insights.api.ml.utils.cached_run`; everything else here
has no cache. `refresh` is accepted but ignored.

Drill-down endpoints (`get_procurement_detail`) are unchanged — they
already use `frappe.get_list` and don't touch the ML stack.
"""

from typing import Any, Dict

import frappe
from frappe import _

from insights.api.ml.utils import cached_run, run


# ---------------------------------------------------------------------------
# Composite endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist()
def procurement_intelligence(refresh: bool = False) -> Dict[str, Any]:
    """Get comprehensive procurement intelligence, cached for 1 hour."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return cached_run(
        lambda: run(lambda: ProcurementIntelligence().train(), "procurement_intelligence"),
        cache_key="insights_ml_procurement_intelligence",
    )


@frappe.whitelist()
def train_procurement_intelligence() -> Dict[str, Any]:
    """Synchronously re-compute procurement intelligence. No 'training'."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence().train(),
        "train_procurement_intelligence",
    )


@frappe.whitelist()
def get_procurement_insights() -> Dict[str, Any]:
    """Get procurement insights overview (top-level summary only)."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: {
            "spend_overview": ProcurementIntelligence()._spend_overview(),
            "supplier_performance": ProcurementIntelligence()._supplier_performance(),
            "risk_analysis": ProcurementIntelligence()._procurement_risks(),
        },
        "get_procurement_insights",
    )


# ---------------------------------------------------------------------------
# Granular endpoints (one per sub-section)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_spend_overview() -> Dict[str, Any]:
    """Get procurement spend overview."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence()._spend_overview(),
        "get_spend_overview",
    )


@frappe.whitelist()
def get_supplier_performance() -> Dict[str, Any]:
    """Get supplier performance analysis."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence()._supplier_performance(),
        "get_supplier_performance",
    )


@frappe.whitelist()
def get_purchase_analytics() -> Dict[str, Any]:
    """Get purchase cycle / analytics."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence()._purchase_cycles(),
        "get_purchase_analytics",
    )


@frappe.whitelist()
def get_price_intelligence() -> Dict[str, Any]:
    """Get price intelligence analysis."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence()._price_intelligence(),
        "get_price_intelligence",
    )


@frappe.whitelist()
def get_procurement_risks() -> Dict[str, Any]:
    """Get procurement risk analysis."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence()._procurement_risks(),
        "get_procurement_risks",
    )


@frappe.whitelist()
def get_procurement_forecast() -> Dict[str, Any]:
    """Get procurement forecasting."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence()._forecast(),
        "get_procurement_forecast",
    )


# Local import to avoid module-level circular
def ProcurementIntelligence():
    from insights.ml.procurement_intelligence import ProcurementIntelligence as _PI

    return _PI()


# ---------------------------------------------------------------------------
# Drill-down (unchanged — uses frappe.get_list, not the ML stack)
# ---------------------------------------------------------------------------


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
