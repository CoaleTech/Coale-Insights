# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence API Endpoints"""

import frappe
from typing import Dict, Any
from insights.api.response import success, error


@frappe.whitelist()
def tax_intelligence(refresh: bool = False) -> Dict[str, Any]:
    """Get full tax intelligence analysis."""
    try:
        from insights.ml.tax_intelligence import TaxIntelligence
        model = TaxIntelligence()
        if refresh:
            result = model.train()
        else:
            result = model.predict()
        return success(data=result)
    except Exception as e:
        return error("Failed to load tax intelligence", exc=e)


@frappe.whitelist()
def gst_summary() -> Dict[str, Any]:
    """Return tax overview section."""
    try:
        from insights.ml.tax_intelligence import TaxIntelligence
        model = TaxIntelligence()
        full = model.predict()
        return success(data=full.get("tax_overview", {}))
    except Exception as e:
        return error("Failed to load tax overview", exc=e)


@frappe.whitelist()
def itc_health() -> Dict[str, Any]:
    """Return WHT analysis section."""
    try:
        from insights.ml.tax_intelligence import TaxIntelligence
        model = TaxIntelligence()
        full = model.predict()
        return success(data=full.get("wht_analysis", {}))
    except Exception as e:
        return error("Failed to load WHT analysis", exc=e)


@frappe.whitelist()
def tds_summary() -> Dict[str, Any]:
    """Return KRA instalment schedule section."""
    try:
        from insights.ml.tax_intelligence import TaxIntelligence
        model = TaxIntelligence()
        full = model.predict()
        return success(data=full.get("kra_schedule", {}))
    except Exception as e:
        return error("Failed to load KRA schedule", exc=e)
