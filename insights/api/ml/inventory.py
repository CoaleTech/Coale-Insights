# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Inventory Intelligence API Endpoints
"""

import frappe
from typing import Dict, Any, List
from insights.api.response import success, error


@frappe.whitelist()
def inventory_classification(refresh: bool = False) -> Dict[str, Any]:
    """Classify inventory using ABC/XYZ analysis"""
    try:
        from insights.ml.abc_xyz_classification import ABCXYZClassification

        model = ABCXYZClassification()

        if not refresh:
            cached = model.get_cached_results("inventory_classification")
            if cached:
                return success(cached)

        result = model.train()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_inventory_recommendations() -> Dict[str, Any]:
    """Get inventory optimization recommendations"""
    try:
        from insights.ml.abc_xyz_classification import ABCXYZClassification

        model = ABCXYZClassification()
        result = model.get_reorder_recommendations()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def inventory_intelligence(refresh: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Get comprehensive inventory intelligence"""
    try:
        from insights.ml.inventory_intelligence import InventoryIntelligence

        model = InventoryIntelligence(date_filter=date_filter)

        if not refresh:
            cached = model.get_cached_results("inventory_intelligence")
            if cached:
                return success(cached)

        result = model.train()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def train_inventory_intelligence() -> Dict[str, Any]:
    """Train inventory intelligence models"""
    try:
        from insights.ml.inventory_intelligence import InventoryIntelligence

        model = InventoryIntelligence()
        result = model.train()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_stock_overview() -> Dict[str, Any]:
    """Get stock overview and key metrics"""
    try:
        from insights.ml.inventory_intelligence import InventoryIntelligence

        model = InventoryIntelligence()
        result = model._calculate_stock_overview()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_turnover_analysis() -> Dict[str, Any]:
    """Get inventory turnover analysis"""
    try:
        from insights.ml.inventory_intelligence import InventoryIntelligence

        model = InventoryIntelligence()
        result = model._calculate_turnover_analysis()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_aging_analysis() -> Dict[str, Any]:
    """Get inventory aging analysis"""
    try:
        from insights.ml.inventory_intelligence import InventoryIntelligence

        model = InventoryIntelligence()
        result = model._calculate_aging_analysis()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_warehouse_analysis() -> Dict[str, Any]:
    """Get warehouse performance analysis"""
    try:
        from insights.ml.inventory_intelligence import InventoryIntelligence

        model = InventoryIntelligence()
        result = model._calculate_warehouse_analysis()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_transfer_recommendations() -> Dict[str, Any]:
    """Get stock transfer recommendations"""
    try:
        from insights.ml.inventory_intelligence import InventoryIntelligence

        model = InventoryIntelligence()
        result = model._generate_transfer_recommendations()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_dead_stock() -> Dict[str, Any]:
    """Identify dead stock items"""
    try:
        from insights.ml.inventory_intelligence import InventoryIntelligence

        model = InventoryIntelligence()
        result = model._identify_dead_stock()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def item_breakeven(period: str = "Quarterly", fiscal_year: str = None, item_group: str = None) -> Dict[str, Any]:
    """Get item-level break-even analysis."""
    try:
        from insights.ml.breakeven_engine import BreakevenEngine

        engine = BreakevenEngine(period=period, fiscal_year=fiscal_year)
        result = engine.calculate_item_breakeven(item_group=item_group)
        return success(result)
    except Exception as e:
        return error(str(e), exc=e)