# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Risk Intelligence API Endpoints
"""

import frappe
from typing import Dict, Any
from insights.api.response import success, error
from insights.ml.base import sanitize_for_json


@frappe.whitelist()
def risk_intelligence(refresh: bool = False, date_filter: str = "12m") -> Dict[str, Any]:
    """Get risk intelligence analysis"""
    try:
        from insights.ml.risk_intelligence import run_risk_intelligence
        return sanitize_for_json(run_risk_intelligence(refresh=refresh))
    except Exception as e:
        return {"status": "error", "message": str(e)}
