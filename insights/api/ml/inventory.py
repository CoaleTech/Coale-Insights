# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Inventory Intelligence API Endpoints — Ibis rewrite.

Each endpoint builds one or two Ibis expressions (which compile to SQL
and execute inside MariaDB) and wraps the result in the standard
`success` envelope via `insights.api.ml.utils.run`. There is no cache,
no background job, no fork. `refresh` is accepted but ignored; the
query is always fresh.

Drill-down endpoints (`get_inventory_detail`) are unchanged -- they
already use `frappe.get_list` and don't touch the ML stack.
"""

from typing import Any, Dict, List

import frappe
from frappe import _
from frappe.query_builder import functions as qb_functions

from insights.api.ml.utils import run


# ---------------------------------------------------------------------------
# Composite endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist()
def inventory_intelligence(date_filter: str = "12m", refresh: bool = False) -> Dict[str, Any]:
    """Get comprehensive inventory intelligence."""
    frappe.has_permission("Item", "read", throw=True)
    return run(
        lambda: _inventory_intelligence(date_filter, refresh),
        "inventory_intelligence",
    )


def _inventory_intelligence(date_filter: str, refresh: bool) -> Dict[str, Any]:
    from insights.ml.inventory_intelligence import (
        InventoryIntelligence,
        ABCXYZClassification,
        DemandForecasting,
    )

    inv = InventoryIntelligence(date_filter=date_filter)
    base = inv.train()
    if base.get("status") != "success":
        return base

    # ABC/XYZ + demand-forecast are nested computations the old code
    # included in the inventory payload. They are now plain in-process
    # calls (no cache, no training) and run in a few seconds each.
    try:
        abc_xyz = ABCXYZClassification().train()
        base["abc_xyz"] = {
            "classification_date": abc_xyz.get("analysis_date"),
            "total_items": abc_xyz.get("total_items", 0),
            "summary": abc_xyz.get("summary", {}),
            "abc_summary": abc_xyz.get("abc_summary", []),
            "xyz_summary": abc_xyz.get("xyz_summary", []),
            "matrix": abc_xyz.get("combined_summary", []),
            "top_items": abc_xyz.get("top_items", []),
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "abc_xyz in inventory_intelligence")
        base["abc_xyz"] = None

    try:
        demand = DemandForecasting().train()
        base["demand_planning"] = {
            "forecast_date": demand.get("forecast_date"),
            "reorder_alerts": demand.get("reorder_alerts", []),
            "summary": {
                "total_items": demand.get("total_items_analyzed", 0),
                "reorder_now_count": demand.get("reorder_now_count", 0),
                "monitor_count": demand.get("monitor_count", 0),
                "adequate_count": demand.get("adequate_count", 0),
            },
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "demand in inventory_intelligence")
        base["demand_planning"] = None

    return base


@frappe.whitelist()
def train_inventory_intelligence() -> Dict[str, Any]:
    """Synchronously re-compute inventory intelligence. No 'training'."""
    frappe.has_permission("Item", "read", throw=True)
    return run(
        lambda: _inventory_intelligence("12m", True),
        "train_inventory_intelligence",
    )


# ---------------------------------------------------------------------------
# Granular endpoints (one per sub-section)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_stock_overview() -> Dict[str, Any]:
    """Get stock overview and key metrics."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import InventoryIntelligence

    return run(
        lambda: InventoryIntelligence()._stock_overview(),
        "get_stock_overview",
    )


@frappe.whitelist()
def get_turnover_analysis() -> Dict[str, Any]:
    """Get inventory turnover analysis."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import InventoryIntelligence

    return run(
        lambda: InventoryIntelligence()._turnover_analysis(),
        "get_turnover_analysis",
    )


@frappe.whitelist()
def get_aging_analysis() -> Dict[str, Any]:
    """Get inventory aging analysis."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import InventoryIntelligence

    return run(
        lambda: InventoryIntelligence()._aging_analysis(),
        "get_aging_analysis",
    )


@frappe.whitelist()
def get_warehouse_analysis() -> Dict[str, Any]:
    """Get warehouse performance analysis."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import InventoryIntelligence

    return run(
        lambda: InventoryIntelligence()._warehouse_analysis(),
        "get_warehouse_analysis",
    )


@frappe.whitelist()
def get_transfer_recommendations() -> Dict[str, Any]:
    """Get stock transfer recommendations."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import InventoryIntelligence

    return run(
        lambda: InventoryIntelligence()._transfer_recommendations(),
        "get_transfer_recommendations",
    )


@frappe.whitelist()
def get_dead_stock() -> Dict[str, Any]:
    """Identify dead-stock items."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import InventoryIntelligence

    return run(
        lambda: InventoryIntelligence()._dead_stock(),
        "get_dead_stock",
    )


# ---------------------------------------------------------------------------
# ABC/XYZ classification
# ---------------------------------------------------------------------------


@frappe.whitelist()
def inventory_classification(refresh: bool = False) -> Dict[str, Any]:
    """Classify inventory using ABC/XYZ analysis."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import ABCXYZClassification

    return run(
        lambda: ABCXYZClassification().train(),
        "inventory_classification",
    )


@frappe.whitelist()
def get_inventory_recommendations() -> Dict[str, Any]:
    """Get inventory optimization recommendations (reorder alerts).

    Delegates to the same canonical demand-forecast payload as
    ``insights.api.ml.general.get_reorder_alerts`` -- there is no
    separate "recommendations" model, ABC/XYZ classification has no
    ``get_reorder_recommendations`` method.
    """
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.demand_forecasting import get_reorder_alerts

    return run(get_reorder_alerts, "get_inventory_recommendations")


# ---------------------------------------------------------------------------
# Item breakeven (delegated to breakeven engine; unchanged contract)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def item_breakeven(period: str = "Quarterly", fiscal_year: str = None, item_group: str = None) -> Dict[str, Any]:
    """Get item-level break-even analysis."""
    try:
        frappe.has_permission("Item", "read", throw=True)
    except frappe.PermissionError:
        raise
    from insights.ml.breakeven_engine import BreakevenEngine

    engine = BreakevenEngine(period=period, fiscal_year=fiscal_year)
    return run(
        lambda: engine.calculate_item_breakeven(item_group=item_group),
        "item_breakeven",
    )


# ---------------------------------------------------------------------------
# Drill-down (unchanged — uses frappe.get_list, not the ML stack)
# ---------------------------------------------------------------------------


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
            .select(qb_functions.Count("*").as_("total"))
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
