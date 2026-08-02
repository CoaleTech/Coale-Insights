# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Inventory Intelligence API Endpoints
"""

import frappe
from frappe import _
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

# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_inventory_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")

    if metric == "total_skus":
        frappe.has_permission("Item", throw=True)
        db_filters = {"disabled": 0, "is_stock_item": 1}
        rows = frappe.get_list(
            "Item",
            filters=db_filters,
            fields=["name", "item_name", "item_group", "stock_uom", "valuation_method"],
            start=start, page_length=page_size, order_by="item_name asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Item Code", "fieldname": "name", "fieldtype": "Link", "options": "Item"},
                {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data"},
                {"label": "Item Group", "fieldname": "item_group", "fieldtype": "Data"},
                {"label": "UOM", "fieldname": "stock_uom", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Item", filters=db_filters),
        }

    if metric == "low_stock_items":
        frappe.has_permission("Bin", throw=True)
        # reorder_level does not exist on Bin; it lives in the
        # "Item Reorder" child table as warehouse_reorder_level.
        # Join Bin ↔ Item Reorder on (item_code, warehouse).
        Bin = frappe.qb.DocType("Bin")
        ItemReorder = frappe.qb.DocType("Item Reorder")
        join_cond = (Bin.item_code == ItemReorder.parent) & (Bin.warehouse == ItemReorder.warehouse)
        base_q = (
            frappe.qb.from_(Bin)
            .join(ItemReorder).on(join_cond)
            .where(ItemReorder.warehouse_reorder_level > 0)
            .where(Bin.actual_qty <= ItemReorder.warehouse_reorder_level)
        )
        rows = (
            base_q
            .select(
                Bin.item_code,
                Bin.warehouse,
                Bin.actual_qty,
                Bin.projected_qty,
                ItemReorder.warehouse_reorder_level.as_("reorder_level"),
            )
            .orderby(Bin.actual_qty)
            .offset(start)
            .limit(page_size)
            .run(as_dict=True)
        )
        total_result = (
            base_q
            .select(frappe.qb.functions.Count("*").as_("total"))
            .run()
        )
        total = total_result[0][0] if total_result else 0
        return {
            "columns": [
                {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item"},
                {"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse"},
                {"label": "Actual Qty", "fieldname": "actual_qty", "fieldtype": "Float"},
                {"label": "Reorder Level", "fieldname": "reorder_level", "fieldtype": "Float"},
            ],
            "rows": rows,
            "total": total,
        }

    if metric == "warehouse_stock":
        frappe.has_permission("Bin", throw=True)
        warehouse = f.get("warehouse")
        db_filters = {"actual_qty": (">", 0)}
        if warehouse:
            db_filters["warehouse"] = warehouse
        rows = frappe.get_list(
            "Bin",
            filters=db_filters,
            fields=["item_code", "warehouse", "actual_qty", "reserved_qty", "ordered_qty"],
            start=start, page_length=page_size, order_by="actual_qty desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item"},
                {"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse"},
                {"label": "Actual Qty", "fieldname": "actual_qty", "fieldtype": "Float"},
                {"label": "Reserved", "fieldname": "reserved_qty", "fieldtype": "Float"},
            ],
            "rows": rows,
            "total": frappe.db.count("Bin", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)