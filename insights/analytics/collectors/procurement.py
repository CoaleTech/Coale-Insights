# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Procurement Data Collector - Supplier spend, performance, pending orders"""

import frappe
from frappe.utils import flt
from typing import Dict, Any, List

from insights.analytics.collectors.base import BaseCollector


class ProcurementDataCollector(BaseCollector):
    """Collect procurement data from Buying module"""

    def collect(self) -> Dict[str, Any]:
        return {
            "summary": self._get_procurement_summary(),
            "top_suppliers": self._get_top_suppliers(),
            "top_items": self._get_top_items(),
            "monthly_trend": self._get_monthly_trend(),
            "supplier_performance": self._get_supplier_performance(),
            "pending_orders": self._get_pending_orders()
        }

    def _get_procurement_summary(self) -> Dict[str, Any]:
        """Get procurement summary"""
        result = frappe.db.sql("""
            SELECT
                COUNT(*) as total_orders,
                SUM(grand_total) as total_spend,
                AVG(grand_total) as avg_order_value
            FROM `tabPurchase Invoice`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
        """, (self.from_date, self.to_date, self.company), as_dict=True)

        return result[0] if result else {}

    def _get_top_suppliers(self, limit: int = 10) -> List[Dict]:
        """Get top suppliers by spend"""
        return frappe.db.sql("""
            SELECT
                supplier,
                supplier_name,
                SUM(grand_total) as total_spend,
                COUNT(*) as order_count
            FROM `tabPurchase Invoice`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
            GROUP BY supplier, supplier_name
            ORDER BY total_spend DESC
            LIMIT %s
        """, (self.from_date, self.to_date, self.company, limit), as_dict=True)

    def _get_top_items(self, limit: int = 10) -> List[Dict]:
        """Get top purchased items"""
        return frappe.db.sql("""
            SELECT
                pii.item_code,
                pii.item_name,
                SUM(pii.qty) as total_qty,
                SUM(pii.amount) as total_spend
            FROM `tabPurchase Invoice Item` pii
            JOIN `tabPurchase Invoice` pi ON pii.parent = pi.name
            WHERE pi.posting_date BETWEEN %s AND %s
            AND pi.company = %s
            AND pi.docstatus = 1
            GROUP BY pii.item_code, pii.item_name
            ORDER BY total_spend DESC
            LIMIT %s
        """, (self.from_date, self.to_date, self.company, limit), as_dict=True)

    def _get_monthly_trend(self) -> List[Dict]:
        """Get monthly procurement trend"""
        return frappe.db.sql("""
            SELECT
                DATE_FORMAT(posting_date, '%%Y-%%m') as month,
                SUM(grand_total) as spend,
                COUNT(*) as orders
            FROM `tabPurchase Invoice`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
            GROUP BY month
            ORDER BY month
        """, (self.from_date, self.to_date, self.company), as_dict=True)

    def _get_supplier_performance(self) -> List[Dict]:
        """Get supplier delivery performance"""
        # Purchase Receipt has no parent-level purchase_order column; the PO link
        # lives on Purchase Receipt Item. Resolve each receipt to the earliest
        # required-by date among its linked POs, then aggregate at receipt grain.
        return frappe.db.sql("""
            SELECT
                r.supplier,
                r.supplier_name,
                COUNT(*) as total_receipts,
                SUM(CASE WHEN r.posting_date <= r.schedule_date THEN 1 ELSE 0 END) as on_time,
                ROUND(SUM(CASE WHEN r.posting_date <= r.schedule_date THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) as on_time_percent
            FROM (
                SELECT
                    pr.name,
                    pr.supplier,
                    pr.supplier_name,
                    pr.posting_date,
                    MIN(po.schedule_date) as schedule_date
                FROM `tabPurchase Receipt` pr
                JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
                JOIN `tabPurchase Order` po ON pri.purchase_order = po.name
                WHERE pr.posting_date BETWEEN %s AND %s
                AND pr.company = %s
                AND pr.docstatus = 1
                AND pri.purchase_order IS NOT NULL AND pri.purchase_order != ''
                GROUP BY pr.name, pr.supplier, pr.supplier_name, pr.posting_date
            ) r
            GROUP BY r.supplier, r.supplier_name
            HAVING total_receipts >= 3
            ORDER BY on_time_percent DESC
            LIMIT 10
        """, (self.from_date, self.to_date, self.company), as_dict=True)

    def _get_pending_orders(self) -> Dict[str, Any]:
        """Get pending purchase orders"""
        result = frappe.db.sql("""
            SELECT
                COUNT(*) as count,
                SUM(grand_total) as total_value
            FROM `tabPurchase Order`
            WHERE company = %s
            AND docstatus = 1
            AND status NOT IN ('Completed', 'Closed', 'Cancelled')
        """, (self.company,), as_dict=True)

        return result[0] if result else {}
