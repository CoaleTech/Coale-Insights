# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Sales Data Collector - Sales summaries, top customers, conversion rates"""

import frappe
from frappe.utils import flt
from typing import Dict, Any, List

from insights.analytics.collectors.base import BaseCollector


class SalesDataCollector(BaseCollector):
    """Collect sales data from Selling module"""

    def collect(self) -> Dict[str, Any]:
        return {
            "summary": self._get_sales_summary(),
            "top_customers": self._get_top_customers(),
            "top_items": self._get_top_items(),
            "sales_by_territory": self._get_sales_by_territory(),
            "monthly_trend": self._get_monthly_trend(),
            "conversion_rate": self._get_conversion_rate(),
            "average_order_value": self._get_aov()
        }

    def _get_sales_summary(self) -> Dict[str, Any]:
        """Get overall sales summary"""
        result = frappe.db.sql("""
            SELECT
                COUNT(*) as total_orders,
                SUM(grand_total) as total_revenue,
                SUM(net_total) as net_revenue,
                AVG(grand_total) as avg_order_value
            FROM `tabSales Invoice`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
        """, (self.from_date, self.to_date, self.company), as_dict=True)

        return result[0] if result else {}

    def _get_top_customers(self, limit: int = 10) -> List[Dict]:
        """Get top customers by revenue"""
        return frappe.db.sql("""
            SELECT
                customer,
                customer_name,
                SUM(grand_total) as total_revenue,
                COUNT(*) as order_count
            FROM `tabSales Invoice`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
            GROUP BY customer, customer_name
            ORDER BY total_revenue DESC
            LIMIT %s
        """, (self.from_date, self.to_date, self.company, limit), as_dict=True)

    def _get_top_items(self, limit: int = 10) -> List[Dict]:
        """Get top selling items"""
        return frappe.db.sql("""
            SELECT
                sii.item_code,
                sii.item_name,
                SUM(sii.qty) as total_qty,
                SUM(sii.amount) as total_revenue
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.posting_date BETWEEN %s AND %s
            AND si.company = %s
            AND si.docstatus = 1
            GROUP BY sii.item_code, sii.item_name
            ORDER BY total_revenue DESC
            LIMIT %s
        """, (self.from_date, self.to_date, self.company, limit), as_dict=True)

    def _get_sales_by_territory(self) -> List[Dict]:
        """Get sales by territory"""
        return frappe.db.sql("""
            SELECT
                territory,
                SUM(grand_total) as total_revenue,
                COUNT(*) as order_count
            FROM `tabSales Invoice`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
            AND territory IS NOT NULL
            GROUP BY territory
            ORDER BY total_revenue DESC
        """, (self.from_date, self.to_date, self.company), as_dict=True)

    def _get_monthly_trend(self) -> List[Dict]:
        """Get monthly sales trend"""
        return frappe.db.sql("""
            SELECT
                DATE_FORMAT(posting_date, '%%Y-%%m') as month,
                SUM(grand_total) as revenue,
                COUNT(*) as orders
            FROM `tabSales Invoice`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
            GROUP BY month
            ORDER BY month
        """, (self.from_date, self.to_date, self.company), as_dict=True)

    def _get_conversion_rate(self) -> Dict[str, Any]:
        """Get quotation to order conversion rate"""
        quotations = frappe.db.count("Quotation", {
            "transaction_date": ["between", [self.from_date, self.to_date]],
            "company": self.company,
            "docstatus": 1
        })

        converted = frappe.db.count("Quotation", {
            "transaction_date": ["between", [self.from_date, self.to_date]],
            "company": self.company,
            "docstatus": 1,
            "status": "Ordered"
        })

        rate = (converted / quotations * 100) if quotations else 0

        return {
            "total_quotations": quotations,
            "converted": converted,
            "conversion_rate": round(rate, 2)
        }

    def _get_aov(self) -> float:
        """Get average order value"""
        result = frappe.db.sql("""
            SELECT AVG(grand_total) as aov
            FROM `tabSales Invoice`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
        """, (self.from_date, self.to_date, self.company), as_dict=True)

        return flt(result[0].get("aov")) if result else 0
