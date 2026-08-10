# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Inventory Data Collector - Stock levels, slow-moving items, turnover analysis"""

import frappe
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

        result = frappe.db.sql("""
            SELECT
                COUNT(DISTINCT item_code) as items_in_stock,
                SUM(actual_qty) as total_qty
            FROM `tabBin`
            WHERE actual_qty > 0
        """, as_dict=True)

        return {
            "total_items": total_items,
            "items_in_stock": cint(result[0].get("items_in_stock")) if result else 0,
            "total_qty": flt(result[0].get("total_qty")) if result else 0
        }

    def _get_stock_value(self) -> Dict[str, Any]:
        """Get total stock value"""
        result = frappe.db.sql("""
            SELECT
                SUM(stock_value) as total_value
            FROM `tabBin`
            WHERE actual_qty > 0
        """, as_dict=True)

        return {
            "total_value": flt(result[0].get("total_value")) if result else 0
        }

    def _get_low_stock_items(self, limit: int = 20) -> List[Dict]:
        """Get items below reorder level"""
        return frappe.db.sql("""
            SELECT
                b.item_code,
                i.item_name,
                b.actual_qty,
                i.safety_stock,
                ir.warehouse_reorder_level as reorder_level
            FROM `tabBin` b
            JOIN `tabItem` i ON b.item_code = i.name
            LEFT JOIN `tabItem Reorder` ir ON i.name = ir.parent AND b.warehouse = ir.warehouse
            WHERE b.actual_qty <= COALESCE(ir.warehouse_reorder_level, i.safety_stock, 0)
            AND COALESCE(ir.warehouse_reorder_level, i.safety_stock, 0) > 0
            ORDER BY (COALESCE(ir.warehouse_reorder_level, i.safety_stock, 0) - b.actual_qty) DESC
            LIMIT %s
        """, (limit,), as_dict=True)

    def _get_slow_moving_items(self, days: int = 90, limit: int = 20) -> List[Dict]:
        """Get slow moving items (no movement in X days)"""
        cutoff_date = add_days(nowdate(), -days)

        return frappe.db.sql("""
            SELECT
                b.item_code,
                i.item_name,
                b.actual_qty,
                b.stock_value,
                MAX(sle.posting_date) as last_movement
            FROM `tabBin` b
            JOIN `tabItem` i ON b.item_code = i.name
            LEFT JOIN `tabStock Ledger Entry` sle ON b.item_code = sle.item_code AND b.warehouse = sle.warehouse
            WHERE b.actual_qty > 0
            GROUP BY b.item_code, i.item_name, b.actual_qty, b.stock_value
            HAVING last_movement < %s OR last_movement IS NULL
            ORDER BY b.stock_value DESC
            LIMIT %s
        """, (cutoff_date, limit), as_dict=True)

    def _get_dead_stock(self, days: int = 180, limit: int = 20) -> List[Dict]:
        """Get dead stock (no movement in 6+ months)"""
        return self._get_slow_moving_items(days=days, limit=limit)

    def _get_warehouse_distribution(self) -> List[Dict]:
        """Get stock distribution by warehouse"""
        return frappe.db.sql("""
            SELECT
                warehouse,
                COUNT(DISTINCT item_code) as item_count,
                SUM(actual_qty) as total_qty,
                SUM(stock_value) as total_value
            FROM `tabBin`
            WHERE actual_qty > 0
            GROUP BY warehouse
            ORDER BY total_value DESC
        """, as_dict=True)

    def _get_inventory_turnover(self) -> Dict[str, Any]:
        """Calculate inventory turnover ratio"""
        # Cost of goods sold (approximation using delivery notes)
        cogs = frappe.db.sql("""
            SELECT SUM(dni.amount) as total
            FROM `tabDelivery Note Item` dni
            JOIN `tabDelivery Note` dn ON dni.parent = dn.name
            WHERE dn.posting_date BETWEEN %s AND %s
            AND dn.company = %s
            AND dn.docstatus = 1
        """, (self.from_date, self.to_date, self.company), as_dict=True)

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
