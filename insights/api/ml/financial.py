# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Financial Intelligence API Endpoints
"""

import frappe
from typing import Dict, Any
from insights.api.response import success, error


@frappe.whitelist()
def financial_intelligence(refresh: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Get comprehensive financial intelligence"""
    try:
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence(date_filter=date_filter)
        if refresh:
            return model.train()
        return model.predict()
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def train_financial_intelligence() -> Dict[str, Any]:
    """Train financial intelligence models"""
    try:
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model.train()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_financial_overview() -> Dict[str, Any]:
    """Get financial overview"""
    try:
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._calculate_financial_overview()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_cash_flow_analysis() -> Dict[str, Any]:
    """Get cash flow analysis"""
    try:
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._calculate_cash_flow()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_receivables_analysis() -> Dict[str, Any]:
    """Get receivables analysis"""
    try:
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._analyze_receivables()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_payables_analysis() -> Dict[str, Any]:
    """Get payables analysis"""
    try:
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._analyze_payables()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_budget_analysis() -> Dict[str, Any]:
    """Get budget analysis"""
    try:
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._analyze_budget_variance()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_financial_ratios() -> Dict[str, Any]:
    """Get financial ratios analysis"""
    try:
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._calculate_financial_ratios()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_tax_analysis() -> Dict[str, Any]:
    """Get tax analysis"""
    try:
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._analyze_kra_tax()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_forex_exposure() -> Dict[str, Any]:
    """Get forex exposure analysis"""
    try:
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._analyze_forex_exposure()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_financial_forecasts() -> Dict[str, Any]:
    """Get financial forecasts"""
    try:
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._generate_financial_forecasts()
        return success(result)
    except Exception as e:
        return error(str(e))
