# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Procurement Intelligence API Endpoints
"""

import frappe
from typing import Dict, Any
from insights.api.response import success, error
from insights.ml.base import sanitize_for_json


@frappe.whitelist()
def get_procurement_insights() -> Dict[str, Any]:
    """Get procurement insights overview"""
    try:
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model.predict()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def procurement_intelligence(refresh: bool = False) -> Dict[str, Any]:
    """Get comprehensive procurement intelligence"""
    try:
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model.train() if refresh else model.predict()
        return sanitize_for_json(result)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def train_procurement_intelligence() -> Dict[str, Any]:
    """Train procurement intelligence models"""
    try:
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model.train()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_spend_overview() -> Dict[str, Any]:
    """Get procurement spend overview"""
    try:
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model._calculate_spend_overview()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_supplier_performance() -> Dict[str, Any]:
    """Get supplier performance analysis"""
    try:
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model._calculate_supplier_performance()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_purchase_analytics() -> Dict[str, Any]:
    """Get purchase analytics"""
    try:
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model._analyze_purchase_cycles()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_price_intelligence() -> Dict[str, Any]:
    """Get price intelligence analysis"""
    try:
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model._calculate_price_intelligence()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_procurement_risks() -> Dict[str, Any]:
    """Get procurement risk analysis"""
    try:
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model._assess_procurement_risks()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_procurement_forecast() -> Dict[str, Any]:
    """Get procurement forecasting"""
    try:
        from insights.ml.procurement_intelligence import ProcurementIntelligence
        model = ProcurementIntelligence()
        result = model._generate_procurement_forecast()
        return success(result)
    except Exception as e:
        return error(str(e))
