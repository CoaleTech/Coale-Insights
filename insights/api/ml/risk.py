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
    """Risk intelligence: served from cache, recomputed in the background."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.risk_intelligence import run_risk_intelligence
        return cached_run(
            lambda: sanitize_for_json(run_risk_intelligence(refresh=refresh)),
            cache_key="insights_ml_risk_intelligence",
        )
    except (frappe.PermissionError, frappe.ServiceUnavailableError):
        raise
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Drill-Down ───────────────────────────────────────────────────────────────

def _due_date_window(f: dict, today: str) -> list[list]:
    """`due_date` conditions for whichever figure the drill was launched from.

    Three callers, three shapes, one field:

    * ``aging_bucket`` -- a label from ``AGING_BUCKETS``. Translated back into
      the day window that produced the bucket, so "90+ Days" opens only the
      invoices counted in that bar. Without this the aging tiles all passed
      *no* bucket filter and every one of the five opened the same
      all-overdue list, which is the same figure five times over.
    * ``overdue_days`` -- a minimum, used by the Overview credit alerts, which
      count only invoices more than 60 days late.
    * neither -- everything overdue today.

    Day windows map to dates inverted: more days overdue means an *earlier*
    ``due_date``, so the bucket's minimum becomes the upper date bound.
    Null ``due_date`` is not handled because neither ledger has any (checked
    live); the aggregate treats those as Current.
    """
    bucket = f.get("aging_bucket")
    if bucket:
        # Imported here, not at module scope: `risk_intelligence` pulls in ibis,
        # which the cached read path deliberately defers (see `risk_intelligence`
        # below) so a warm request never pays for it.
        from insights.ml.risk_intelligence import AGING_BUCKETS

        for name, lo, hi in AGING_BUCKETS:
            if name != bucket:
                continue
            window = []
            if lo is not None:
                window.append(["due_date", "<=", frappe.utils.add_days(today, -lo)])
            if hi is not None:
                window.append(["due_date", ">=", frappe.utils.add_days(today, -hi)])
            return window
        frappe.throw(_("Unknown aging bucket: {0}").format(bucket), frappe.ValidationError)
    return [["due_date", "<", frappe.utils.add_days(today, -int(f.get("overdue_days") or 0))]]


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
        db_filters = [
            ["docstatus", "=", 1],
            ["outstanding_amount", ">", 0],
            *_due_date_window(f, today),
        ]
        if company:
            db_filters.append(["company", "=", company])
        if f.get("customer"):
            db_filters.append(["customer", "=", f["customer"]])
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
        db_filters = [
            ["docstatus", "=", 1],
            ["outstanding_amount", ">", 0],
            *_due_date_window(f, today),
        ]
        if company:
            db_filters.append(["company", "=", company])
        if f.get("supplier"):
            db_filters.append(["supplier", "=", f["supplier"]])
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
