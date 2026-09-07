# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Inventory Data Collector - Stock levels, slow-moving items, turnover analysis"""

import frappe
from frappe.query_builder.functions import Count, IfNull, Max, Sum
from frappe.utils import add_days, nowdate, flt, cint
from typing import Dict, Any, List

from insights.analytics.collectors.base import BaseCollector


class InventoryDataCollector(BaseCollector):
    """Collect inventory data from Stock module"""

    def collect(self) -> Dict[str, Any]:
        return {
            "summary": self._get_inventory_summary(),
            "stock_value": self._get_stock_value(),
            "low_stock": self._get_low_stock_items(),
            "slow_moving": self._get_slow_moving_items(),
            "dead_stock": self._get_dead_stock(),
            "warehouse_wise": self._get_warehouse_distribution(),
            "turnover": self._get_inventory_turnover()
        }

    def _get_inventory_summary(self) -> Dict[str, Any]:
        """Get inventory summary"""
        total_items = frappe.db.count("Item", {"disabled": 0, "is_stock_item": 1})

        Bin = frappe.qb.DocType("Bin")
        query = (
            frappe.qb.from_(Bin)
            .select(
                Count(Bin.item_code).distinct().as_("items_in_stock"),
                Sum(Bin.actual_qty).as_("total_qty"),
            )
            .where(Bin.actual_qty > 0)
        )
        result = query.run(as_dict=True)

        return {
            "total_items": total_items,
            "items_in_stock": cint(result[0].get("items_in_stock")) if result else 0,
            "total_qty": flt(result[0].get("total_qty")) if result else 0
        }

    def _get_stock_value(self) -> Dict[str, Any]:
        """Get total stock value"""
        Bin = frappe.qb.DocType("Bin")
        query = (
            frappe.qb.from_(Bin)
            .select(Sum(Bin.stock_value).as_("total_value"))
            .where(Bin.actual_qty > 0)
        )
        result = query.run(as_dict=True)

        return {
            "total_value": flt(result[0].get("total_value")) if result else 0
        }

    def _get_low_stock_items(self, limit: int = 20) -> List[Dict]:
        """Get items below reorder level"""
        Bin = frappe.qb.DocType("Bin")
        Item = frappe.qb.DocType("Item")
        ItemReorder = frappe.qb.DocType("Item Reorder")

        # COALESCE(ir.warehouse_reorder_level, i.safety_stock, 0) expressed as
        # a PyPika IfNull chain; PyPika flattens these into nested IFNULL() calls.
        reorder_or_safety = IfNull(
            IfNull(ItemReorder.warehouse_reorder_level, Item.safety_stock), 0
        )
        threshold_gap = reorder_or_safety - Bin.actual_qty

        query = (
            frappe.qb.from_(Bin)
            .join(Item).on(Bin.item_code == Item.name)
            .left_join(ItemReorder).on(
                (Item.name == ItemReorder.parent) & (Bin.warehouse == ItemReorder.warehouse)
            )
            .select(
                Bin.item_code,
                Item.item_name,
                Bin.actual_qty,
                Item.safety_stock,
                ItemReorder.warehouse_reorder_level.as_("reorder_level"),
            )
            .where(Bin.actual_qty <= reorder_or_safety)
            .where(reorder_or_safety > 0)
            .orderby(threshold_gap, order=frappe.qb.desc)
            .limit(limit)
        )
        return query.run(as_dict=True)

    def _get_slow_moving_items(self, days: int = 90, limit: int = 20) -> List[Dict]:
        """Get slow moving items (no movement in X days)"""
        cutoff_date = add_days(nowdate(), -days)

        Bin = frappe.qb.DocType("Bin")
        Item = frappe.qb.DocType("Item")
        SLE = frappe.qb.DocType("Stock Ledger Entry")

        last_movement = Max(SLE.posting_date).as_("last_movement")

        query = (
            frappe.qb.from_(Bin)
            .join(Item).on(Bin.item_code == Item.name)
            .left_join(SLE).on(
                (Bin.item_code == SLE.item_code) & (Bin.warehouse == SLE.warehouse)
            )
            .select(
                Bin.item_code,
                Item.item_name,
                Bin.actual_qty,
                Bin.stock_value,
                last_movement,
            )
            .where(Bin.actual_qty > 0)
            .groupby(Bin.item_code, Item.item_name, Bin.actual_qty, Bin.stock_value)
            .having((last_movement < cutoff_date) | (last_movement.isnull()))
            .orderby(Bin.stock_value, order=frappe.qb.desc)
            .limit(limit)
        )
        return query.run(as_dict=True)

    def _get_dead_stock(self, days: int = 180, limit: int = 20) -> List[Dict]:
        """Get dead stock (no movement in 6+ months)"""
        return self._get_slow_moving_items(days=days, limit=limit)

    def _get_warehouse_distribution(self) -> List[Dict]:
        """Get stock distribution by warehouse"""
        Bin = frappe.qb.DocType("Bin")

        query = (
            frappe.qb.from_(Bin)
            .select(
                Bin.warehouse,
                Count(Bin.item_code).distinct().as_("item_count"),
                Sum(Bin.actual_qty).as_("total_qty"),
                Sum(Bin.stock_value).as_("total_value"),
            )
            .where(Bin.actual_qty > 0)
            .groupby(Bin.warehouse)
            .orderby(Sum(Bin.stock_value), order=frappe.qb.desc)
        )
        return query.run(as_dict=True)

    def _get_inventory_turnover(self) -> Dict[str, Any]:
        """Calculate inventory turnover ratio"""
        # Cost of goods sold (approximation using delivery notes)
        DNI = frappe.qb.DocType("Delivery Note Item")
        DN = frappe.qb.DocType("Delivery Note")

        cogs = (
            frappe.qb.from_(DNI)
            .join(DN).on(DNI.parent == DN.name)
            .select(Sum(DNI.amount).as_("total"))
            .where(DN.posting_date.between(self.from_date, self.to_date))
            .where(DN.company == self.company)
            .where(DN.docstatus == 1)
            .run(as_dict=True)
        )

        cogs_value = flt(cogs[0].get("total")) if cogs else 0

        # Average inventory
        stock_value = self._get_stock_value()
        avg_inventory = stock_value.get("total_value", 0)

        turnover = (cogs_value / avg_inventory) if avg_inventory else 0
        days_to_sell = (365 / turnover) if turnover else 0

        return {
            "cogs": cogs_value,
            "avg_inventory": avg_inventory,
            "turnover_ratio": round(turnover, 2),
            "days_to_sell": round(days_to_sell, 0)
        }
