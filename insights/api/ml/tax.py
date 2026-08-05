# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence API — GST, ITC, TDS, e-Invoice, e-Waybill, HSN, compliance."""

import frappe
from frappe import _
from typing import Dict, Any
from insights.api.response import success, error


def _get_model(period: str = "fy"):
    """Return an IndiaTaxIntelligence instance for the requested window."""
    from insights.ml.india_tax_intelligence.model import IndiaTaxIntelligence
    return IndiaTaxIntelligence(period=period)


def _get_section(key: str, default=None, period: str = "fy"):
    """Predict (or hit cache) and return one section of the result."""
    return _get_model(period).predict().get(key, default if default is not None else {})


# ── Primary endpoint ──────────────────────────────────────────────────────────

@frappe.whitelist()
def tax_intelligence(refresh: bool = False, period: str = "fy") -> Dict[str, Any]:
    """Full India tax intelligence: GST, ITC, TDS, e-Invoice, filing, reconciliation.

    `period` is one of 3m / 6m / 12m / fy and selects the reporting window. It
    used to be absent, so the dashboard's period selector re-fetched and redrew
    the fiscal year every time, appearing to work while ignoring the choice.
    """
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        model = _get_model(period)
        result = model.train() if refresh else model.predict()
        return success(data=result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error("Failed to load tax intelligence", exc=e)


@frappe.whitelist()
def tax_intelligence_status(period: str = "fy") -> Dict[str, Any]:
    """Return cached result if available (called by polling after a refresh)."""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        model = _get_model(period)
        cached = model.get_cached_results(f"india_tax_intelligence:{model.period}")
        if cached:
            return success(data={"status": "completed", "result": cached})
        return success(data={"status": "not_found"})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error("Failed to check status", exc=e)


# ── Supplementary section endpoints ──────────────────────────────────────────

@frappe.whitelist()
def gst_summary() -> Dict[str, Any]:
    """Monthly CGST / SGST / IGST output tax summary."""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        return success(data=_get_section("gst_summary", []))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error("Failed to load GST summary", exc=e)


@frappe.whitelist()
def itc_health() -> Dict[str, Any]:
    """ITC availability, claims, ineligible credits and utilisation %."""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        return success(data=_get_section("itc_health"))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error("Failed to load ITC health", exc=e)


@frappe.whitelist()
def tds_summary() -> Dict[str, Any]:
    """TDS payable by section, total payable, receivable, net position."""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        return success(data=_get_section("tds_summary"))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error("Failed to load TDS summary", exc=e)


# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_tax_detail(metric: str, filters: str) -> dict:
    """Row-level detail behind a tax metric, for the drill-down panel."""
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")
    hsn_code = f.get("hsn_code")
    period = f.get("period") or "fy"

    if metric == "tax_invoices":
        frappe.has_permission("Sales Invoice", throw=True)

        # Built as bound parameters rather than escaped interpolation so the
        # query carries no formatting at all.
        conditions = ["si.docstatus = 1", "si.total_taxes_and_charges > 0"]
        params: Dict[str, Any] = {}
        if company:
            conditions.append("si.company = %(company)s")
            params["company"] = company

        # Scoped to the same window the dashboard is showing. Without this the
        # panel listed every invoice for the HSN back to 2024 while the row above
        # it reported one fiscal year, so the two disagreed.
        window = _get_model(period)._get_fiscal_dates()
        conditions.append("si.posting_date BETWEEN %(start_date)s AND %(end_date)s")
        params["start_date"] = str(window["year_start_date"])
        params["end_date"] = str(window["year_end_date"])
        if hsn_code:
            # Previously ignored: the dashboard names the HSN in the drill-down
            # title, so listing every invoice regardless of HSN made the title
            # describe something other than the rows underneath it.
            conditions.append(
                "EXISTS (SELECT 1 FROM `tabSales Invoice Item` sii "
                "WHERE sii.parent = si.name AND sii.gst_hsn_code = %(hsn_code)s)"
            )
            params["hsn_code"] = hsn_code

        where = " AND ".join(conditions)

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
