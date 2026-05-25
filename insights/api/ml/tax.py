# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence API — GST, ITC, TDS, e-Invoice, e-Waybill, HSN, compliance."""

import frappe
from typing import Dict, Any
from insights.api.response import success, error


def _get_model():
    """Return an IndiaTaxIntelligence instance."""
    from insights.ml.india_tax_intelligence.model import IndiaTaxIntelligence
    return IndiaTaxIntelligence()


def _get_section(key: str, default=None):
    """Predict (or hit cache) and return one section of the result."""
    return _get_model().predict().get(key, default if default is not None else {})


# ── Primary endpoint ──────────────────────────────────────────────────────────

@frappe.whitelist()
def tax_intelligence(refresh: bool = False) -> Dict[str, Any]:
    """Full India tax intelligence: GST, ITC, TDS, e-Invoice, filing, reconciliation."""
    try:
        model = _get_model()
        result = model.train() if refresh else model.predict()
        return success(data=result)
    except Exception as e:
        return error("Failed to load tax intelligence", exc=e)


@frappe.whitelist()
def tax_intelligence_status() -> Dict[str, Any]:
    """Return cached result if available (called by polling after a refresh)."""
    try:
        model = _get_model()
        cached = model.get_cached_results("india_tax_intelligence")
        if cached:
            return success(data={"status": "completed", "result": cached})
        return success(data={"status": "not_found"})
    except Exception as e:
        return error("Failed to check status", exc=e)


# ── Supplementary section endpoints ──────────────────────────────────────────

@frappe.whitelist()
def gst_summary() -> Dict[str, Any]:
    """Monthly CGST / SGST / IGST output tax summary."""
    try:
        return success(data=_get_section("gst_summary", []))
    except Exception as e:
        return error("Failed to load GST summary", exc=e)


@frappe.whitelist()
def itc_health() -> Dict[str, Any]:
    """ITC availability, claims, ineligible credits and utilisation %."""
    try:
        return success(data=_get_section("itc_health"))
    except Exception as e:
        return error("Failed to load ITC health", exc=e)


@frappe.whitelist()
def tds_summary() -> Dict[str, Any]:
    """TDS payable by section, total payable, receivable, net position."""
    try:
        return success(data=_get_section("tds_summary"))
    except Exception as e:
        return error("Failed to load TDS summary", exc=e)
