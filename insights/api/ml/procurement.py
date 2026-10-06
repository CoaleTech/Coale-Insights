# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Procurement Intelligence API Endpoints — Ibis rewrite.

Each endpoint builds one or two Ibis expressions (which compile to SQL
and execute inside MariaDB) and wraps the result in the standard
`success` envelope via `insights.api.ml.utils.run`. No background job, no
fork. `procurement_intelligence` (the full dashboard payload) is the one
exception: served from cache and recomputed by a background job
(`insights.api.ml.utils.cached_run`), with `refresh` queueing a recompute
while the payload it already has keeps being served.

Drill-down endpoints (`get_procurement_detail`) use `frappe.get_list` (so row
permissions apply) and don't touch the ML stack. `total_pos`,
`supplier_performance`, `supplier_invoices` and `item_purchases` honour an
optional `filters.date_filter` (same grammar as the dashboard window).
"""

from typing import Any, Dict, Optional

import frappe
from frappe import _

from insights.api.ml.utils import cached_run, parse_date_filter, run


# ---------------------------------------------------------------------------
# Composite endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist()
def procurement_intelligence(date_filter: str = "12m", refresh: bool = False) -> Dict[str, Any]:
    """Comprehensive procurement intelligence: served from cache, recomputed
    in the background per date_filter."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return cached_run(
        lambda: run(lambda: ProcurementIntelligence(date_filter).train(), "procurement_intelligence"),
        cache_key=f"insights_ml_procurement_intelligence:{date_filter}",
    )


@frappe.whitelist()
def train_procurement_intelligence(date_filter: str = "12m") -> Dict[str, Any]:
    """Synchronously re-compute procurement intelligence. No 'training'."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence(date_filter).train(),
        "train_procurement_intelligence",
    )


@frappe.whitelist()
def get_procurement_insights(date_filter: str = "12m") -> Dict[str, Any]:
    """Get procurement insights overview (top-level summary only)."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    model = ProcurementIntelligence(date_filter)
    return run(
        lambda: {
            "spend_overview": model._spend_overview(),
            "supplier_performance": model._supplier_performance(),
            "risk_analysis": model._procurement_risks(),
        },
        "get_procurement_insights",
    )


# ---------------------------------------------------------------------------
# Granular endpoints (one per sub-section)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_spend_overview(date_filter: str = "12m") -> Dict[str, Any]:
    """Get procurement spend overview."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence(date_filter)._spend_overview(),
        "get_spend_overview",
    )


@frappe.whitelist()
def get_supplier_performance(date_filter: str = "12m") -> Dict[str, Any]:
    """Get supplier performance analysis."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence(date_filter)._supplier_performance(),
        "get_supplier_performance",
    )


@frappe.whitelist()
def get_purchase_analytics(date_filter: str = "12m") -> Dict[str, Any]:
    """Get purchase cycle / analytics."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence(date_filter)._purchase_cycles(),
        "get_purchase_analytics",
    )


@frappe.whitelist()
def get_price_intelligence(date_filter: str = "12m") -> Dict[str, Any]:
    """Get price intelligence analysis."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence(date_filter)._price_intelligence(),
        "get_price_intelligence",
    )


@frappe.whitelist()
def get_procurement_risks(date_filter: str = "12m") -> Dict[str, Any]:
    """Get procurement risk analysis."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence(date_filter)._procurement_risks(),
        "get_procurement_risks",
    )


@frappe.whitelist()
def get_procurement_forecast(date_filter: str = "12m") -> Dict[str, Any]:
    """Get procurement forecasting."""
    frappe.has_permission("Purchase Order", "read", throw=True)
    return run(
        lambda: ProcurementIntelligence(date_filter)._forecast(),
        "get_procurement_forecast",
    )


# Local import to avoid module-level circular
def ProcurementIntelligence(date_filter: str = "12m"):
    from insights.ml.procurement_intelligence import ProcurementIntelligence as _PI

    return _PI(date_filter=date_filter)


# ---------------------------------------------------------------------------
# Drill-down (uses frappe.get_list, not the ML stack)
# ---------------------------------------------------------------------------

_PO = {"label": "PO", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Order"}
_PO_SUPPLIER = {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"}
_PO_DATE = {"label": "Date", "fieldname": "transaction_date", "fieldtype": "Date"}
_PO_EXPECTED = {"label": "Expected", "fieldname": "schedule_date", "fieldtype": "Date"}
_PO_TOTAL = {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"}
_PO_STATUS = {"label": "Status", "fieldname": "status", "fieldtype": "Data"}
_PO_RECEIVED = {"label": "% Received", "fieldname": "per_received", "fieldtype": "Percent"}

_INV = {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Invoice"}
_INV_DATE = {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"}


def _MONEY(label, fieldname):
    return {"label": label, "fieldname": fieldname, "fieldtype": "Currency"}


def _detail(doctype, filters, fields, columns, order_by, start, page_size=50):
    """One drill-down page: `{columns, rows, total}`. `get_list` enforces row
    and field permissions; `filters` may be a dict or a list of filter rows."""
    return {
        "columns": columns,
        "rows": frappe.get_list(
            doctype,
            filters=filters,
            fields=fields,
            start=start,
            page_length=page_size,
            order_by=order_by,
            ignore_permissions=False,
        ),
        "total": frappe.db.count(doctype, filters=filters),
    }


def _window(date_filter: Optional[str]) -> Optional[list]:
    """`["between", [start, end]]` for a dashboard `date_filter`; None when the
    filter is absent or open-ended (all time)."""
    if not date_filter:
        return None
    start, end = parse_date_filter(str(date_filter))
    if start is None or end is None:
        return None
    return ["between", [start.date(), end.date()]]


@frappe.whitelist()
def get_procurement_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")
    window = _window(f.get("date_filter"))

    if metric in ("total_pos", "supplier_performance"):
        frappe.has_permission("Purchase Order", throw=True)
        db_filters = {"docstatus": 1}
        if company:
            db_filters["company"] = company
        if window:
            db_filters["transaction_date"] = window
        if metric == "supplier_performance" and f.get("supplier"):
            db_filters["supplier"] = f["supplier"]
        return _detail(
            "Purchase Order", db_filters,
            ["name", "supplier", "transaction_date", "schedule_date", "grand_total", "status"],
            [_PO, _PO_SUPPLIER, _PO_DATE, _PO_EXPECTED, _PO_TOTAL, _PO_STATUS],
            "transaction_date desc", start,
        )

    if metric == "pending_pos":
        frappe.has_permission("Purchase Order", throw=True)
        db_filters = {"docstatus": 1, "status": ("not in", ["Completed", "Cancelled", "Closed"])}
        if company:
            db_filters["company"] = company
        return _detail(
            "Purchase Order", db_filters,
            ["name", "supplier", "transaction_date", "schedule_date", "grand_total", "status", "per_received"],
            [_PO, _PO_SUPPLIER, _PO_EXPECTED, _PO_TOTAL, _PO_STATUS, _PO_RECEIVED],
            "schedule_date asc", start,
        )

    if metric == "overdue_pos":
        frappe.has_permission("Purchase Order", throw=True)
        db_filters = {
            "docstatus": 1,
            "schedule_date": ("<", frappe.utils.today()),
            "status": ("not in", ["Completed", "Cancelled", "Closed"]),
        }
        if company:
            db_filters["company"] = company
        return _detail(
            "Purchase Order", db_filters,
            ["name", "supplier", "transaction_date", "schedule_date", "grand_total", "per_received"],
            [_PO, _PO_SUPPLIER, _PO_EXPECTED, _PO_TOTAL, _PO_RECEIVED],
            "schedule_date asc", start,
        )

    if metric in ("supplier_invoices", "overdue_invoices"):
        frappe.has_permission("Purchase Invoice", throw=True)
        db_filters = {"docstatus": 1}
        if company:
            db_filters["company"] = company
        if metric == "supplier_invoices":
            supplier = f.get("supplier")
            if not isinstance(supplier, str) or not supplier:
                frappe.throw(_("Supplier is required"), frappe.ValidationError)
            db_filters["supplier"] = supplier
            if window:
                db_filters["posting_date"] = window
            order_by = "posting_date desc"
        else:
            db_filters["outstanding_amount"] = (">", 0)
            db_filters["due_date"] = ("<", frappe.utils.today())
            order_by = "due_date asc"
        columns = [
            _INV, _INV_DATE,
            {"label": "Due", "fieldname": "due_date", "fieldtype": "Date"},
            _MONEY("Total", "base_grand_total"),
            _MONEY("Outstanding", "outstanding_amount"),
            {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
        ]
        fields = ["name", "posting_date", "due_date", "base_grand_total", "outstanding_amount", "status"]
        if metric == "overdue_invoices":
            columns.insert(1, _PO_SUPPLIER)
            fields.insert(1, "supplier")
        return _detail("Purchase Invoice", db_filters, fields, columns, order_by, start)

    if metric == "item_purchases":
        # Purchase Invoice Item is a child table: query it through its parent so
        # get_list applies Purchase Invoice permissions to every row.
        frappe.has_permission("Purchase Invoice", throw=True)
        item_code = f.get("item_code")
        if not isinstance(item_code, str) or not item_code:
            frappe.throw(_("Item is required"), frappe.ValidationError)
        child = "`tabPurchase Invoice Item`"
        db_filters = [
            ["Purchase Invoice", "docstatus", "=", 1],
            ["Purchase Invoice Item", "item_code", "=", item_code],
        ]
        if company:
            db_filters.append(["Purchase Invoice", "company", "=", company])
        if window:
            db_filters.append(["Purchase Invoice", "posting_date", *window])
        return _detail(
            "Purchase Invoice", db_filters,
            ["name", "supplier", "posting_date", f"{child}.qty as qty", f"{child}.uom as uom",
             f"{child}.base_rate as rate", f"{child}.base_amount as base_amount"],
            [
                _INV, _PO_SUPPLIER, _INV_DATE,
                {"label": "Qty", "fieldname": "qty", "fieldtype": "Float"},
                {"label": "UOM", "fieldname": "uom", "fieldtype": "Link", "options": "UOM"},
                _MONEY("Rate", "rate"),
                _MONEY("Amount", "base_amount"),
            ],
            "posting_date desc", start,
        )

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
