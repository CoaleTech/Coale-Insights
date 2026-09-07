# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Sales Data Collector - Sales summaries, top customers, conversion rates"""

import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Avg, Count, DateFormat, Sum
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
        si = DocType("Sales Invoice")
        q = (
            frappe.qb.from_(si)
            .select(
                Count("*").as_("total_orders"),
                Sum(si.grand_total).as_("total_revenue"),
                Sum(si.net_total).as_("net_revenue"),
                Avg(si.grand_total).as_("avg_order_value"),
            )
            .where(si.posting_date.between(self.from_date, self.to_date))
            .where(si.company == self.company)
            .where(si.docstatus == 1)
        )
        rows = q.run(as_dict=True)
        return rows[0] if rows else {}

    def _get_top_customers(self, limit: int = 10) -> List[Dict]:
        """Get top customers by revenue"""
        si = DocType("Sales Invoice")
        total_revenue = Sum(si.grand_total).as_("total_revenue")
        q = (
            frappe.qb.from_(si)
            .select(
                si.customer,
                si.customer_name,
                total_revenue,
                Count("*").as_("order_count"),
            )
            .where(si.posting_date.between(self.from_date, self.to_date))
            .where(si.company == self.company)
            .where(si.docstatus == 1)
            .groupby(si.customer, si.customer_name)
            .orderby(total_revenue, order=frappe.qb.desc)
            .limit(limit)
        )
        return q.run(as_dict=True)

    def _get_top_items(self, limit: int = 10) -> List[Dict]:
        """Get top selling items"""
        si = DocType("Sales Invoice")
        sii = DocType("Sales Invoice Item")
        total_revenue = Sum(sii.amount).as_("total_revenue")
        q = (
            frappe.qb.from_(sii)
            .join(si)
            .on(sii.parent == si.name)
            .select(
                sii.item_code,
                sii.item_name,
                Sum(sii.qty).as_("total_qty"),
                total_revenue,
            )
            .where(si.posting_date.between(self.from_date, self.to_date))
            .where(si.company == self.company)
            .where(si.docstatus == 1)
            .groupby(sii.item_code, sii.item_name)
            .orderby(total_revenue, order=frappe.qb.desc)
            .limit(limit)
        )
        return q.run(as_dict=True)

    def _get_sales_by_territory(self) -> List[Dict]:
        """Get sales by territory"""
        si = DocType("Sales Invoice")
        total_revenue = Sum(si.grand_total).as_("total_revenue")
        q = (
            frappe.qb.from_(si)
            .select(
                si.territory,
                total_revenue,
                Count("*").as_("order_count"),
            )
            .where(si.posting_date.between(self.from_date, self.to_date))
            .where(si.company == self.company)
            .where(si.docstatus == 1)
            .where(si.territory.isnotnull())
            .groupby(si.territory)
            .orderby(total_revenue, order=frappe.qb.desc)
        )
        return q.run(as_dict=True)

    def _get_monthly_trend(self) -> List[Dict]:
        """Get monthly sales trend"""
        si = DocType("Sales Invoice")
        month = DateFormat(si.posting_date, "%Y-%m").as_("month")
        q = (
            frappe.qb.from_(si)
            .select(
                month,
                Sum(si.grand_total).as_("revenue"),
                Count("*").as_("orders"),
            )
            .where(si.posting_date.between(self.from_date, self.to_date))
            .where(si.company == self.company)
            .where(si.docstatus == 1)
            .groupby(month)
            .orderby(month)
        )
        return q.run(as_dict=True)

    def _get_conversion_rate(self) -> Dict[str, Any]:
        """Get quotation to order conversion rate"""
        qoutation = DocType("Quotation")
        base_filters = (
            (qoutation.transaction_date.between(self.from_date, self.to_date))
            & (qoutation.company == self.company)
            & (qoutation.docstatus == 1)
        )

        q = (
            frappe.qb.from_(qoutation)
            .select(Count("*").as_("c"))
            .where(base_filters)
        )
        quotations = q.run(as_dict=True)[0].c or 0

        q = (
            frappe.qb.from_(qoutation)
            .select(Count("*").as_("c"))
            .where(base_filters)
            .where(qoutation.status == "Ordered")
        )
        converted = q.run(as_dict=True)[0].c or 0

        rate = (converted / quotations * 100) if quotations else 0

        return {
            "total_quotations": quotations,
            "converted": converted,
            "conversion_rate": round(rate, 2)
        }

    def _get_aov(self) -> float:
        """Get average order value"""
        si = DocType("Sales Invoice")
        q = (
            frappe.qb.from_(si)
            .select(Avg(si.grand_total).as_("aov"))
            .where(si.posting_date.between(self.from_date, self.to_date))
            .where(si.company == self.company)
            .where(si.docstatus == 1)
        )
        rows = q.run(as_dict=True)
        return flt(rows[0].get("aov")) if rows else 0
