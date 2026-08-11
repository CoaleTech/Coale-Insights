# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence API — GST, ITC, TDS, e-Invoice, e-Waybill, HSN, compliance.

Pure-Ibis: every endpoint runs synchronously and returns the same shape
the legacy `tax_intelligence` model emitted. No more warming/polling
contract; no background training; no fork into RQ.
"""

import frappe
from frappe import _
from typing import Any, Dict

from insights.api.response import success, error
from insights.api.ml.utils import run


# `period` is one of `3m` / `6m` / `12m` / `fy` and is resolved inside the
# model. Both names (`date_filter` and `period`) are accepted so callers
# that use either form continue to work without modification.
_PERIOD_KEYS = ("3m", "6m", "12m", "fy")


def _coerce_period(period: str | None) -> str:
    if not period:
        return "fy"
    p = str(period).strip().lower()
    return p if p in _PERIOD_KEYS else "fy"


def _compute(period: str) -> Dict[str, Any]:
    """Single synchronous compute. Returns the full payload."""
    from insights.ml.india_tax_intelligence.model import IndiaTaxIntelligence
    return IndiaTaxIntelligence(period=period).train()


def _section(period: str, key: str, default):
    payload = _compute(period)
    return payload.get(key, default if default is not None else {})


# ── Primary endpoint ──────────────────────────────────────────────────────────

@frappe.whitelist()
def tax_intelligence(refresh: bool = False, period: str = "fy") -> Dict[str, Any]:
    """Full India tax intelligence: GST, ITC, TDS, e-Invoice, filing, reconciliation.

    `period` is one of `3m` / `6m` / `12m` / `fy` and selects the reporting
    window. `refresh` is accepted for API compatibility but no longer has
    any side effect — the result is always fresh because there is no
    cache to invalidate.
    """
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        return run(lambda: _compute(_coerce_period(period)), "Tax intelligence")
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error("Failed to load tax intelligence", exc=e)


# ── Supplementary section endpoints ──────────────────────────────────────────

@frappe.whitelist()
def gst_summary(period: str = "fy") -> Dict[str, Any]:
    """Monthly CGST / SGST / IGST output-tax summary."""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        return success(_section(_coerce_period(period), "gst_summary", []))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error("Failed to load GST summary", exc=e)


@frappe.whitelist()
def itc_health(period: str = "fy") -> Dict[str, Any]:
    """ITC availability, claims, ineligible credits and utilisation %."""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        return success(_section(_coerce_period(period), "itc_health", {}))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error("Failed to load ITC health", exc=e)


@frappe.whitelist()
def tds_summary(period: str = "fy") -> Dict[str, Any]:
    """TDS payable by section, total payable, receivable, net position."""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        return success(_section(_coerce_period(period), "tds_summary", {}))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error("Failed to load TDS summary", exc=e)


# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_tax_detail(metric: str, filters: str) -> dict:
    """Row-level detail behind a tax metric, for the drill-down panel.

    Kept on the same dotted path (`insights.api.ml.tax.get_tax_detail`)
    because the Tax Intelligence dashboard's drill-down opens this URL
    directly. The handler reads Sales Invoice rows in the period of the
    dashboard view, optionally filtered to a single HSN code. This uses
    `frappe.db.sql` with bound parameters — the values come from the
    dashboard, not user-supplied SQL.
    """
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")
    hsn_code = f.get("hsn_code")
    period = _coerce_period(f.get("period") or "fy")

    if metric == "tax_invoices":
        frappe.has_permission("Sales Invoice", throw=True)

        # Built as bound parameters rather than escaped interpolation so the
        # query carries no formatting at all.
        conditions = ["si.docstatus = 1", "si.total_taxes_and_charges > 0"]
        params: Dict[str, Any] = {}
        if company:
            conditions.append("si.company = %(company)s")
            params["company"] = company

        # Scoped to the same window the dashboard is showing.
        from insights.ml.india_tax_intelligence.model import IndiaTaxIntelligence
        win = IndiaTaxIntelligence(period=period)._window()
        conditions.append("si.posting_date BETWEEN %(start_date)s AND %(end_date)s")
        params["start_date"] = str(win.get("start"))
        params["end_date"] = str(win.get("end"))
        if hsn_code:
            conditions.append(
                "EXISTS (SELECT 1 FROM `tabSales Invoice Item` sii "
                "WHERE sii.parent = si.name AND sii.gst_hsn_code = %(hsn_code)s)"
            )
            params["hsn_code"] = hsn_code

        where = " AND ".join(conditions)

        # `where` joins only the literal fragments appended above; every
        # value is a bound parameter in `params`, so nothing caller-
        # supplied reaches the SQL text.
        rows = frappe.db.sql(
            f"""
            SELECT si.name, si.customer, si.posting_date, si.grand_total,
                   si.total_taxes_and_charges
            FROM `tabSales Invoice` si
            WHERE {where}
            ORDER BY si.posting_date DESC, si.name DESC
            LIMIT %(page_size)s OFFSET %(start)s
            """,
            {**params, "page_size": page_size, "start": start},
            as_dict=True,
        )
        total = frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabSales Invoice` si WHERE {where}",
            params,
        )[0][0]

        return {
            "columns": [
                {"label": _("Invoice"), "fieldname": "name", "fieldtype": "Link",
                 "options": "Sales Invoice"},
                {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link",
                 "options": "Customer"},
                {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": _("Tax Amount"), "fieldname": "total_taxes_and_charges",
                 "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": total,
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
