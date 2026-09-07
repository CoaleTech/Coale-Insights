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
from frappe.query_builder.functions import Coalesce, Count
from typing import Any, Dict

from insights.api.response import success, error
from insights.api.ml.utils import cached_run, run


# `period` is one of `3m` / `6m` / `12m` / `fy`, or a `custom:<start>:<end>`
# range (see `insights.api.ml.utils.parse_custom_range`), and is resolved
# inside the model. Anything else -- including an unset value -- coerces to
# `fy`; see `_coerce_period`. `date_filter` is a different endpoint family's
# param name (see `insights.api.ml.utils.parse_date_filter`) and is not
# accepted here.
_PERIOD_KEYS = ("3m", "6m", "12m", "fy")


def _coerce_period(period: str | None) -> str:
    if not period:
        return "fy"
    p = str(period).strip().lower()
    if p in _PERIOD_KEYS:
        return p
    from insights.api.ml.utils import parse_custom_range
    return p if parse_custom_range(p) else "fy"


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
    dashboard view, optionally filtered to a single HSN code. Built with
    `frappe.qb`; values are bound parameters, not interpolated SQL.
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

        from insights.ml.india_tax_intelligence.model import IndiaTaxIntelligence
        win = IndiaTaxIntelligence(period=period)._window()

        SI = frappe.qb.DocType("Sales Invoice")
        SII = frappe.qb.DocType("Sales Invoice Item")
        query = (
            frappe.qb.from_(SI)
            .select(
                SI.name,
                SI.customer,
                SI.posting_date,
                SI.grand_total,
                SI.total_taxes_and_charges,
            )
            .where(
                (SI.docstatus == 1)
                & (SI.total_taxes_and_charges > 0)
                & (SI.posting_date.between(win.get("start"), win.get("end")))
            )
        )
        if company:
            query = query.where(SI.company == company)
        if hsn_code:
            hsn_subquery = (
                frappe.qb.from_(SII)
                .select(SII.parent)
                .where((SII.parent == SI.name) & (SII.gst_hsn_code == hsn_code))
            )
            query = query.where(SI.name.isin(hsn_subquery))

        rows = (
            query.orderby(SI.posting_date, order=frappe.qb.desc)
            .orderby(SI.name, order=frappe.qb.desc)
            .limit(page_size)
            .offset(start)
            .run(as_dict=True)
        )
        total = query.select(Count("*").as_("total")).run(as_dict=True)[0].get("total", 0)

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
        needs_irn_categories = [
            "Registered Regular", "Registered Composition",
            "SEZ supply with payment of tax", "SEZ supply without payment of tax",
            "Deemed Export", "Overseas", "SEZ",
        ]

        from insights.ml.india_tax_intelligence.model import IndiaTaxIntelligence
        win = IndiaTaxIntelligence(period=period)._window()

        SI = frappe.qb.DocType("Sales Invoice")
        query = (
            frappe.qb.from_(SI)
            .select(SI.name, SI.customer, SI.posting_date, SI.gst_category, SI.grand_total)
            .where(
                (SI.docstatus == 1)
                & SI.gst_category.isin(needs_irn_categories)
                & ((SI.irn.isnull()) | (SI.irn == ""))
                & SI.posting_date.between(win.get("start"), win.get("end"))
            )
        )
        if company:
            query = query.where(SI.company == company)

        rows = (
            query.orderby(SI.posting_date, order=frappe.qb.desc)
            .orderby(SI.name, order=frappe.qb.desc)
            .limit(page_size)
            .offset(start)
            .run(as_dict=True)
        )
        total = query.select(Count("*").as_("total")).run(as_dict=True)[0].get("total", 0)

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

        from insights.ml.india_tax_intelligence.model import IndiaTaxIntelligence
        win = IndiaTaxIntelligence(period=period)._window()

        SI = frappe.qb.DocType("Sales Invoice")
        query = (
            frappe.qb.from_(SI)
            .select(SI.name, SI.customer, SI.posting_date, SI.grand_total)
            .where(
                (SI.docstatus == 1)
                & (SI.e_waybill_status == "Pending")
                & SI.posting_date.between(win.get("start"), win.get("end"))
            )
        )
        if company:
            query = query.where(SI.company == company)

        rows = (
            query.orderby(SI.posting_date, order=frappe.qb.desc)
            .orderby(SI.name, order=frappe.qb.desc)
            .limit(page_size)
            .offset(start)
            .run(as_dict=True)
        )
        total = query.select(Count("*").as_("total")).run(as_dict=True)[0].get("total", 0)

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

        GIS = frappe.qb.DocType("GST Inward Supply")
        query = (
            frappe.qb.from_(GIS)
            .select(
                GIS.name,
                GIS.supplier_name,
                GIS.supplier_gstin,
                GIS.bill_no,
                GIS.bill_date,
                GIS.taxable_value,
                GIS.match_status,
            )
            .where((GIS.action.isnull()) | (GIS.action == "No Action"))
        )
        if company:
            query = query.where(GIS.company == company)

        rows = (
            query.orderby(GIS.bill_date, order=frappe.qb.desc)
            .orderby(GIS.name, order=frappe.qb.desc)
            .limit(page_size)
            .offset(start)
            .run(as_dict=True)
        )
        total = query.select(Count("*").as_("total")).run(as_dict=True)[0].get("total", 0)

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

        GIS = frappe.qb.DocType("GST Inward Supply")
        at_risk_tax = (
            Coalesce(GIS.igst, 0)
            + Coalesce(GIS.cgst, 0)
            + Coalesce(GIS.sgst, 0)
            + Coalesce(GIS.cess, 0)
        ).as_("at_risk_tax")
        query = (
            frappe.qb.from_(GIS)
            .select(
                GIS.name,
                GIS.supplier_name,
                GIS.supplier_gstin,
                GIS.bill_no,
                GIS.bill_date,
                GIS.taxable_value,
                at_risk_tax,
            )
            .where((GIS.gstr_1_filled.isnull()) | (GIS.gstr_1_filled == 0))
        )
        if company:
            query = query.where(GIS.company == company)

        rows = (
            query.orderby(GIS.bill_date, order=frappe.qb.desc)
            .orderby(GIS.name, order=frappe.qb.desc)
            .limit(page_size)
            .offset(start)
            .run(as_dict=True)
        )
        total = query.select(Count("*").as_("total")).run(as_dict=True)[0].get("total", 0)

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
