# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence API — GST, ITC, TDS, e-Invoice, e-Waybill, HSN, compliance.

Pure-Ibis: every endpoint returns the same shape the legacy
`tax_intelligence` model emitted, with no model training and no fork into
RQ. The full `tax_intelligence` payload is served from cache and recomputed
by a background job per period; the slices below compute per call.
"""

import frappe
from frappe import _
from typing import Any, Dict

from insights.api.response import success, error
from insights.api.ml.utils import cached_run, run


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
    window. `refresh` queues a recompute and keeps serving the payload it
    already has. Served from cache, recomputed in the background per period
    -- see `insights.api.ml.utils.cached_run`.
    """
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        coerced = _coerce_period(period)
        return cached_run(
            lambda: run(lambda: _compute(coerced), "Tax intelligence"),
            cache_key=f"insights_ml_tax_intelligence:{coerced}",
        )
    except (frappe.PermissionError, frappe.ServiceUnavailableError):
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

    if metric == "irn_missing":
        frappe.has_permission("Sales Invoice", throw=True)
        # Mirrors `get_einvoice_status`'s `needs_irn & (~has_irn)` filter exactly
        # (insights/ml/india_tax_intelligence/data.py) so the drill-down list
        # count matches the KPI card it opens from.
        needs_irn_categories = [
            "Registered Regular", "Registered Composition",
            "SEZ supply with payment of tax", "SEZ supply without payment of tax",
            "Deemed Export", "Overseas", "SEZ",
        ]
        conditions = [
            "si.docstatus = 1",
            "si.gst_category IN %(needs_irn)s",
            "(si.irn IS NULL OR si.irn = '')",
        ]
        params: Dict[str, Any] = {"needs_irn": needs_irn_categories}
        if company:
            conditions.append("si.company = %(company)s")
            params["company"] = company
        from insights.ml.india_tax_intelligence.model import IndiaTaxIntelligence
        win = IndiaTaxIntelligence(period=period)._window()
        conditions.append("si.posting_date BETWEEN %(start_date)s AND %(end_date)s")
        params["start_date"] = str(win.get("start"))
        params["end_date"] = str(win.get("end"))
        where = " AND ".join(conditions)
        rows = frappe.db.sql(
            f"""
            SELECT si.name, si.customer, si.posting_date, si.gst_category, si.grand_total
            FROM `tabSales Invoice` si
            WHERE {where}
            ORDER BY si.posting_date DESC, si.name DESC
            LIMIT %(page_size)s OFFSET %(start)s
            """,
            {**params, "page_size": page_size, "start": start},
            as_dict=True,
        )
        total = frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabSales Invoice` si WHERE {where}", params
        )[0][0]
        return {
            "columns": [
                {"label": _("Invoice"), "fieldname": "name", "fieldtype": "Link",
                 "options": "Sales Invoice"},
                {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link",
                 "options": "Customer"},
                {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": _("GST Category"), "fieldname": "gst_category", "fieldtype": "Data"},
                {"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": total,
        }

    if metric == "ewaybill_pending":
        frappe.has_permission("Sales Invoice", throw=True)
        # Mirrors `get_ewaybill_status`'s `e_waybill_status == "Pending"` bucket.
        conditions = ["si.docstatus = 1", "si.e_waybill_status = 'Pending'"]
        params = {}
        if company:
            conditions.append("si.company = %(company)s")
            params["company"] = company
        from insights.ml.india_tax_intelligence.model import IndiaTaxIntelligence
        win = IndiaTaxIntelligence(period=period)._window()
        conditions.append("si.posting_date BETWEEN %(start_date)s AND %(end_date)s")
        params["start_date"] = str(win.get("start"))
        params["end_date"] = str(win.get("end"))
        where = " AND ".join(conditions)
        rows = frappe.db.sql(
            f"""
            SELECT si.name, si.customer, si.posting_date, si.grand_total
            FROM `tabSales Invoice` si
            WHERE {where}
            ORDER BY si.posting_date DESC, si.name DESC
            LIMIT %(page_size)s OFFSET %(start)s
            """,
            {**params, "page_size": page_size, "start": start},
            as_dict=True,
        )
        total = frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabSales Invoice` si WHERE {where}", params
        )[0][0]
        return {
            "columns": [
                {"label": _("Invoice"), "fieldname": "name", "fieldtype": "Link",
                 "options": "Sales Invoice"},
                {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link",
                 "options": "Customer"},
                {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": total,
        }

    if metric == "reconciliation_unactioned":
        frappe.has_permission("GST Inward Supply", throw=True)
        # Mirrors `get_reconciliation_score`'s `unactioned_count`: rows whose
        # `action` is still the "No Action" default (fill_null included).
        conditions = ["(gis.action IS NULL OR gis.action = 'No Action')"]
        params = {}
        if company:
            conditions.append("gis.company = %(company)s")
            params["company"] = company
        where = " AND ".join(conditions)
        rows = frappe.db.sql(
            f"""
            SELECT gis.name, gis.supplier_name, gis.supplier_gstin, gis.bill_no,
                   gis.bill_date, gis.taxable_value, gis.match_status
            FROM `tabGST Inward Supply` gis
            WHERE {where}
            ORDER BY gis.bill_date DESC, gis.name DESC
            LIMIT %(page_size)s OFFSET %(start)s
            """,
            {**params, "page_size": page_size, "start": start},
            as_dict=True,
        )
        total = frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabGST Inward Supply` gis WHERE {where}", params
        )[0][0]
        return {
            "columns": [
                {"label": _("Supplier"), "fieldname": "supplier_name", "fieldtype": "Data"},
                {"label": _("GSTIN"), "fieldname": "supplier_gstin", "fieldtype": "Data"},
                {"label": _("Bill No"), "fieldname": "bill_no", "fieldtype": "Data"},
                {"label": _("Bill Date"), "fieldname": "bill_date", "fieldtype": "Date"},
                {"label": _("Taxable Value"), "fieldname": "taxable_value", "fieldtype": "Currency"},
                {"label": _("Match Status"), "fieldname": "match_status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": total,
        }

    if metric == "itc_at_risk":
        frappe.has_permission("GST Inward Supply", throw=True)
        # Mirrors `get_itc_health`'s Sec 16(2)(aa) `at_risk_supplier_unfiled`
        # bucket (insights/ml/india_tax_intelligence/data.py): inward supply
        # rows where the supplier has not filed GSTR-1, so the credit is not
        # yet supported by GSTR-2B and is exposed on reversal.
        conditions = ["(gis.gstr_1_filled IS NULL OR gis.gstr_1_filled = 0)"]
        params = {}
        if company:
            conditions.append("gis.company = %(company)s")
            params["company"] = company
        where = " AND ".join(conditions)
        rows = frappe.db.sql(
            f"""
            SELECT gis.name, gis.supplier_name, gis.supplier_gstin, gis.bill_no,
                   gis.bill_date, gis.taxable_value,
                   (COALESCE(gis.igst, 0) + COALESCE(gis.cgst, 0)
                    + COALESCE(gis.sgst, 0) + COALESCE(gis.cess, 0)) AS at_risk_tax
            FROM `tabGST Inward Supply` gis
            WHERE {where}
            ORDER BY gis.bill_date DESC, gis.name DESC
            LIMIT %(page_size)s OFFSET %(start)s
            """,
            {**params, "page_size": page_size, "start": start},
            as_dict=True,
        )
        total = frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabGST Inward Supply` gis WHERE {where}", params
        )[0][0]
        return {
            "columns": [
                {"label": _("Supplier"), "fieldname": "supplier_name", "fieldtype": "Data"},
                {"label": _("GSTIN"), "fieldname": "supplier_gstin", "fieldtype": "Data"},
                {"label": _("Bill No"), "fieldname": "bill_no", "fieldtype": "Data"},
                {"label": _("Bill Date"), "fieldname": "bill_date", "fieldtype": "Date"},
                {"label": _("Taxable Value"), "fieldname": "taxable_value", "fieldtype": "Currency"},
                {"label": _("ITC At Risk"), "fieldname": "at_risk_tax", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": total,
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
