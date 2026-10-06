# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Inventory Intelligence API Endpoints — Ibis rewrite.

Each endpoint builds one or two Ibis expressions (which compile to SQL
and execute inside MariaDB) and wraps the result in the standard
`success` envelope via `insights.api.ml.utils.run`. No background job, no
fork; the query is always fresh. `inventory_intelligence` (the full
dashboard payload) fans out to three such computations, so it is the one
exception: served from cache and recomputed by a background job per
date_filter (`insights.api.ml.utils.cached_run`).

Drill-down endpoints (`get_inventory_detail`) use `frappe.get_list`/`frappe.qb`
or the same InventoryIntelligence helpers as the KPI they explain.
"""

from typing import Any, Dict, Optional

import frappe
from frappe import _
from frappe.query_builder import functions as qb_functions

from insights.api.ml.utils import cached_run, run


# ---------------------------------------------------------------------------
# Composite endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist()
def inventory_intelligence(date_filter: str = "12m", refresh: bool = False) -> Dict[str, Any]:
    """Comprehensive inventory intelligence: served from cache, recomputed in
    the background per date_filter."""
    frappe.has_permission("Item", "read", throw=True)
    return cached_run(
        lambda: run(lambda: _inventory_intelligence(date_filter, refresh), "inventory_intelligence"),
        cache_key=f"insights_ml_inventory_intelligence:{date_filter}",
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
        abc_xyz = ABCXYZClassification(date_filter=date_filter).train()
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
        demand = DemandForecasting(date_filter=date_filter).train()
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
def train_inventory_intelligence(date_filter: str = "12m") -> Dict[str, Any]:
    """Synchronously re-compute inventory intelligence. No 'training'."""
    frappe.has_permission("Item", "read", throw=True)
    return run(
        lambda: _inventory_intelligence(date_filter, True),
        "train_inventory_intelligence",
    )


# ---------------------------------------------------------------------------
# Granular endpoints (one per sub-section)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_stock_overview(date_filter: str = "12m") -> Dict[str, Any]:
    """Get stock overview and key metrics."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import InventoryIntelligence

    return run(
        lambda: InventoryIntelligence(date_filter=date_filter)._stock_overview(),
        "get_stock_overview",
    )


@frappe.whitelist()
def get_turnover_analysis(date_filter: str = "12m") -> Dict[str, Any]:
    """Get inventory turnover analysis."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import InventoryIntelligence

    return run(
        lambda: InventoryIntelligence(date_filter=date_filter)._turnover_analysis(),
        "get_turnover_analysis",
    )


@frappe.whitelist()
def get_aging_analysis(date_filter: str = "12m") -> Dict[str, Any]:
    """Get inventory aging analysis."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import InventoryIntelligence

    return run(
        lambda: InventoryIntelligence(date_filter=date_filter)._aging_analysis(),
        "get_aging_analysis",
    )


@frappe.whitelist()
def get_warehouse_analysis(date_filter: str = "12m") -> Dict[str, Any]:
    """Get warehouse performance analysis."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import InventoryIntelligence

    return run(
        lambda: InventoryIntelligence(date_filter=date_filter)._warehouse_analysis(),
        "get_warehouse_analysis",
    )


@frappe.whitelist()
def get_transfer_recommendations(date_filter: str = "12m") -> Dict[str, Any]:
    """Get stock transfer recommendations."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import InventoryIntelligence

    return run(
        lambda: InventoryIntelligence(date_filter=date_filter)._transfer_recommendations(),
        "get_transfer_recommendations",
    )


@frappe.whitelist()
def get_dead_stock(date_filter: str = "12m") -> Dict[str, Any]:
    """Identify dead-stock items."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import InventoryIntelligence

    return run(
        lambda: InventoryIntelligence(date_filter=date_filter)._dead_stock(),
        "get_dead_stock",
    )


# ---------------------------------------------------------------------------
# ABC/XYZ classification
# ---------------------------------------------------------------------------


@frappe.whitelist()
def inventory_classification(refresh: bool = False, date_filter: str = "12m") -> Dict[str, Any]:
    """Classify inventory using ABC/XYZ analysis."""
    frappe.has_permission("Item", "read", throw=True)
    from insights.ml.inventory_intelligence import ABCXYZClassification

    return run(
        lambda: ABCXYZClassification(date_filter=date_filter).train(),
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
def item_breakeven(period: str = "Quarterly", fiscal_year: Optional[str] = None, item_group: Optional[str] = None) -> Dict[str, Any]:
    """Get item-level break-even analysis."""
    # BreakevenEngine.calculate_item_breakeven reads Item, Sales Invoice
    # (+ its Sales Invoice Item child), GL Entry (fixed-cost centers), Bin
    # and Stock Ledger Entry -- all via raw frappe.qb, which applies no
    # row-level check. Gate on every parent doctype it reads, not just Item.
    frappe.has_permission("Item", "read", throw=True)
    frappe.has_permission("Sales Invoice", "read", throw=True)
    frappe.has_permission("GL Entry", "read", throw=True)
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
        # KpiCard label is "Active SKUs" and its value comes from
        # `InventoryIntelligence._stock_overview` -- Bin.item_code.nunique()
        # filtered to rows with any actual/reserved/ordered qty (e.g. 64
        # items on jkm). This branch used to ignore Bin entirely and list
        # every disabled=0/is_stock_item=1 Item master row (556 on jkm) --
        # clicking the "64" KPI opened a drill-down with 556 unrelated
        # rows. Join through Bin so the drill-down population matches the
        # KPI it was opened from.
        frappe.has_permission("Item", throw=True)
        frappe.has_permission("Bin", throw=True)
        Item = frappe.qb.DocType("Item")
        Bin = frappe.qb.DocType("Bin")
        active_item_codes = (
            frappe.qb.from_(Bin)
            .where((Bin.actual_qty != 0) | (Bin.reserved_qty != 0) | (Bin.ordered_qty != 0))
            .select(Bin.item_code)
            .distinct()
        )
        base_q = (
            frappe.qb.from_(Item)
            .where(Item.disabled == 0)
            .where(Item.is_stock_item == 1)
            .where(Item.name.isin(active_item_codes))
        )
        rows = (
            base_q
            .select(Item.name, Item.item_name, Item.item_group, Item.stock_uom, Item.valuation_method)
            .orderby(Item.item_name)
            .offset(start)
            .limit(page_size)
            .run(as_dict=True)
        )
        total_result = base_q.select(qb_functions.Count("*").as_("total")).run()
        total = total_result[0][0] if total_result else 0
        return {
            "columns": [
                {"label": "Item Code", "fieldname": "name", "fieldtype": "Link", "options": "Item"},
                {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data"},
                {"label": "Item Group", "fieldname": "item_group", "fieldtype": "Data"},
                {"label": "UOM", "fieldname": "stock_uom", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": total,
        }

    if metric in ("low_stock_items", "overstock_items"):
        # KpiCards "Low Stock" / "Overstock" come from
        # `InventoryIntelligence._stock_overview` -- sales-velocity based:
        # positive stock and avg daily sales (over the selected window) > 0,
        # then actual_qty < 14 days of sales (low) or > 90 days (overstock).
        # Reuse the KPI's own velocity definition so the drill-down always
        # explains the number shown.
        frappe.has_permission("Bin", throw=True)
        frappe.has_permission("Sales Invoice", throw=True)
        bins = _velocity_bins(f.get("date_filter") or "12m")
        if metric == "low_stock_items":
            candidates = [b for b in bins if float(b["actual_qty"]) < b["avg_daily_sales"] * 14]
            candidates.sort(key=lambda r: r["days_of_supply"])
        else:
            candidates = [b for b in bins if float(b["actual_qty"]) > b["avg_daily_sales"] * 90]
            candidates.sort(key=lambda r: -r["days_of_supply"])
        total = len(candidates)
        rows = candidates[start:start + page_size]
        return {
            "columns": [
                {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item"},
                {"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse"},
                {"label": "Actual Qty", "fieldname": "actual_qty", "fieldtype": "Float"},
                {"label": "Days of Supply", "fieldname": "days_of_supply", "fieldtype": "Float"},
            ],
            "rows": rows,
            "total": total,
        }

    if metric == "out_of_stock_items":
        # KPI "Out of Stock": distinct items with a Bin (any actual/reserved/
        # ordered qty) whose actual_qty <= 0. One row per item.
        frappe.has_permission("Bin", throw=True)
        frappe.has_permission("Item", throw=True)
        Bin = frappe.qb.DocType("Bin")
        Item = frappe.qb.DocType("Item")
        bins = (
            frappe.qb.from_(Bin)
            .left_join(Item)
            .on(Bin.item_code == Item.name)
            .where((Bin.actual_qty != 0) | (Bin.reserved_qty != 0) | (Bin.ordered_qty != 0))
            .where(Bin.actual_qty <= 0)
            .select(Bin.item_code, Item.item_name, Bin.warehouse, Bin.actual_qty, Bin.reserved_qty, Bin.ordered_qty)
            .orderby(Bin.item_code)
            .run(as_dict=True)
        )
        per_item: Dict[str, Dict[str, Any]] = {}
        for b in bins:
            r = per_item.setdefault(
                b.item_code,
                {"item_code": b.item_code, "item_name": b.item_name, "warehouse": [], "actual_qty": 0.0,
                 "reserved_qty": 0.0, "ordered_qty": 0.0},
            )
            r["warehouse"].append(b.warehouse)
            r["actual_qty"] += float(b.actual_qty or 0)
            r["reserved_qty"] += float(b.reserved_qty or 0)
            r["ordered_qty"] += float(b.ordered_qty or 0)
        candidates = [{**r, "warehouse": ", ".join(r["warehouse"])} for r in per_item.values()]
        return {
            "columns": [
                {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item"},
                {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data"},
                {"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Data"},
                {"label": "Actual Qty", "fieldname": "actual_qty", "fieldtype": "Float"},
                {"label": "Reserved", "fieldname": "reserved_qty", "fieldtype": "Float"},
                {"label": "On Order", "fieldname": "ordered_qty", "fieldtype": "Float"},
            ],
            "rows": candidates[start:start + page_size],
            "total": len(candidates),
        }

    if metric == "dead_stock_items":
        # KPI "Dead Stock" value: every positive-stock Bin row whose item has
        # not sold in 180 days (or ever) -- the same rows `_dead_stock` totals.
        frappe.has_permission("Bin", throw=True)
        frappe.has_permission("Item", throw=True)
        frappe.has_permission("Sales Invoice", throw=True)
        from insights.ml.inventory_intelligence import InventoryIntelligence

        candidates = InventoryIntelligence()._dead_stock_rows()
        return {
            "columns": [
                {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item"},
                {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data"},
                {"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse"},
                {"label": "Actual Qty", "fieldname": "actual_qty", "fieldtype": "Float"},
                {"label": "Stock Value", "fieldname": "stock_value", "fieldtype": "Currency"},
                {"label": "Days Since Last Sale", "fieldname": "days_since_last_sale", "fieldtype": "Int"},
            ],
            "rows": candidates[start:start + page_size],
            "total": len(candidates),
        }

    if metric == "pending_orders":
        # KPI "Pending Orders": submitted POs not Completed/Closed/Cancelled
        # in the selected window (same helper the KPI uses).
        frappe.has_permission("Purchase Order", throw=True)
        frappe.has_permission("Supplier", throw=True)
        from insights.ml.inventory_intelligence import InventoryIntelligence

        _, candidates = InventoryIntelligence(date_filter=f.get("date_filter") or "12m")._pending_orders()
        return {
            "columns": [
                {"label": "Purchase Order", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Order"},
                {"label": "Supplier", "fieldname": "supplier_name", "fieldtype": "Data"},
                {"label": "Date", "fieldname": "transaction_date", "fieldtype": "Date"},
                {"label": "Amount", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
                {"label": "Days Pending", "fieldname": "days_pending", "fieldtype": "Int"},
            ],
            "rows": candidates[start:start + page_size],
            "total": len(candidates),
        }

    if metric == "reorder_items":
        # KPI "Reorder": items with demand in the window whose stock is at or
        # below max(reorder level, 14 days of demand).
        frappe.has_permission("Item", throw=True)
        frappe.has_permission("Bin", throw=True)
        frappe.has_permission("Sales Invoice", throw=True)
        from insights.ml.inventory_intelligence import InventoryIntelligence

        candidates = InventoryIntelligence(date_filter=f.get("date_filter") or "12m")._reorder_candidates()
        return {
            "columns": [
                {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item"},
                {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data"},
                {"label": "Current Stock", "fieldname": "current_stock", "fieldtype": "Float"},
                {"label": "Reorder Level", "fieldname": "reorder_level", "fieldtype": "Float"},
                {"label": "Avg Daily Demand", "fieldname": "avg_daily_demand", "fieldtype": "Float"},
            ],
            "rows": candidates[start:start + page_size],
            "total": len(candidates),
        }

    if metric == "warehouse_stock":
        # `_warehouse_analysis`'s "Items" count (the KpiCard this drill-down
        # opens from) is Bin.item_code.nunique() filtered to actual_qty>0
        # OR reserved_qty>0 OR ordered_qty>0 -- items with pending
        # reservations/POs but zero on-hand stock still count. This branch
        # filtered actual_qty>0 only, so a warehouse showing "60 Items"
        # opened a drill-down listing 28 rows. Match the same filter.
        frappe.has_permission("Bin", throw=True)
        warehouse = f.get("warehouse")
        Bin = frappe.qb.DocType("Bin")
        base_q = frappe.qb.from_(Bin).where(
            (Bin.actual_qty > 0) | (Bin.reserved_qty > 0) | (Bin.ordered_qty > 0)
        )
        if warehouse:
            base_q = base_q.where(Bin.warehouse == warehouse)
        rows = (
            base_q
            .select(Bin.item_code, Bin.warehouse, Bin.actual_qty, Bin.reserved_qty, Bin.ordered_qty)
            .orderby(Bin.actual_qty, order=frappe.qb.desc)
            .offset(start)
            .limit(page_size)
            .run(as_dict=True)
        )
        total_result = base_q.select(qb_functions.Count("*").as_("total")).run()
        total = total_result[0][0] if total_result else 0
        return {
            "columns": [
                {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item"},
                {"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse"},
                {"label": "Actual Qty", "fieldname": "actual_qty", "fieldtype": "Float"},
                {"label": "Reserved", "fieldname": "reserved_qty", "fieldtype": "Float"},
            ],
            "rows": rows,
            "total": total,
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)


def _velocity_bins(date_filter: str) -> list:
    """Positive-stock Bin rows whose item sold in the window, each with
    `avg_daily_sales` (stock-UOM qty/day) and `days_of_supply` -- the
    population `_stock_overview` derives Low Stock / Overstock from."""
    from insights.ml.inventory_intelligence import resolve_window

    window_start, window_end, days = resolve_window(date_filter)
    SalesInvoiceItem = frappe.qb.DocType("Sales Invoice Item")
    SalesInvoice = frappe.qb.DocType("Sales Invoice")
    q = (
        frappe.qb.from_(SalesInvoiceItem)
        .join(SalesInvoice)
        .on(SalesInvoiceItem.parent == SalesInvoice.name)
        .where(SalesInvoice.docstatus == 1)
        .where(SalesInvoice.posting_date <= window_end)
        .groupby(SalesInvoiceItem.item_code)
        .select(SalesInvoiceItem.item_code, qb_functions.Sum(SalesInvoiceItem.stock_qty).as_("qty_window"))
    )
    if window_start:
        q = q.where(SalesInvoice.posting_date >= window_start)
    avg_daily_sales = {r.item_code: float(r.qty_window or 0) / days for r in q.run(as_dict=True)}

    Bin = frappe.qb.DocType("Bin")
    bins = (
        frappe.qb.from_(Bin)
        .where(Bin.actual_qty > 0)
        .select(Bin.item_code, Bin.warehouse, Bin.actual_qty, Bin.projected_qty)
        .run(as_dict=True)
    )
    out = []
    for b in bins:
        daily = avg_daily_sales.get(b.item_code, 0.0)
        if daily > 0:
            out.append(
                {
                    "item_code": b.item_code,
                    "warehouse": b.warehouse,
                    "actual_qty": b.actual_qty,
                    "projected_qty": b.projected_qty,
                    "avg_daily_sales": daily,
                    "days_of_supply": round(float(b.actual_qty) / daily, 1),
                }
            )
    return out
