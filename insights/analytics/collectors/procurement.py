# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Procurement Data Collector - Supplier spend, performance, pending orders

All aggregations are pushed to MariaDB via the ``frappe.qb`` query builder;
Python only formats the small result sets into the dict shape callers already
expect. See ``insights.reports.sales_intelligence_report`` for the canonical
``Case``/``DateFormat``/``Coalesce`` pattern that this module mirrors.
"""

from typing import Any, Dict, List

import frappe
from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import (
    Avg,
    Count,
    DateFormat,
    Min,
    Round,
    Sum,
)

from insights.analytics.collectors.base import BaseCollector

# Statuses that mean "no longer actionable" for pending Purchase Orders.
_CLOSED_PO_STATUSES = ("Completed", "Closed", "Cancelled")


class ProcurementDataCollector(BaseCollector):
    """Collect procurement data from Buying module"""

    def collect(self) -> Dict[str, Any]:
        return {
            "summary": self._get_procurement_summary(),
            "top_suppliers": self._get_top_suppliers(),
            "top_items": self._get_top_items(),
            "monthly_trend": self._get_monthly_trend(),
            "supplier_performance": self._get_supplier_performance(),
            "pending_orders": self._get_pending_orders(),
        }

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def _get_procurement_summary(self) -> Dict[str, Any]:
        """Get procurement summary"""
        pi = DocType("Purchase Invoice")
        q = (
            frappe.qb.from_(pi)
            .select(
                Count("*").as_("total_orders"),
                Sum(pi.grand_total).as_("total_spend"),
                Avg(pi.grand_total).as_("avg_order_value"),
            )
            .where(pi.posting_date.between(self.from_date, self.to_date))
            .where(pi.company == self.company)
            .where(pi.docstatus == 1)
        )
        rows = q.run(as_dict=True)
        return rows[0] if rows else {}

    # ------------------------------------------------------------------
    # Top suppliers
    # ------------------------------------------------------------------
    def _get_top_suppliers(self, limit: int = 10) -> List[Dict]:
        """Get top suppliers by spend"""
        pi = DocType("Purchase Invoice")
        total_spend = Sum(pi.grand_total).as_("total_spend")
        q = (
            frappe.qb.from_(pi)
            .select(
                pi.supplier,
                pi.supplier_name,
                total_spend,
                Count("*").as_("order_count"),
            )
            .where(pi.posting_date.between(self.from_date, self.to_date))
            .where(pi.company == self.company)
            .where(pi.docstatus == 1)
            .groupby(pi.supplier, pi.supplier_name)
            .orderby(total_spend, order=frappe.qb.desc)
            .limit(limit)
        )
        return q.run(as_dict=True)

    # ------------------------------------------------------------------
    # Top items
    # ------------------------------------------------------------------
    def _get_top_items(self, limit: int = 10) -> List[Dict]:
        """Get top purchased items"""
        pii = DocType("Purchase Invoice Item")
        pi = DocType("Purchase Invoice")
        total_spend = Sum(pii.amount).as_("total_spend")
        q = (
            frappe.qb.from_(pii)
            .join(pi)
            .on(pii.parent == pi.name)
            .select(
                pii.item_code,
                pii.item_name,
                Sum(pii.qty).as_("total_qty"),
                total_spend,
            )
            .where(pi.posting_date.between(self.from_date, self.to_date))
            .where(pi.company == self.company)
            .where(pi.docstatus == 1)
            .groupby(pii.item_code, pii.item_name)
            .orderby(total_spend, order=frappe.qb.desc)
            .limit(limit)
        )
        return q.run(as_dict=True)

    # ------------------------------------------------------------------
    # Monthly trend
    # ------------------------------------------------------------------
    def _get_monthly_trend(self) -> List[Dict]:
        """Get monthly procurement trend"""
        pi = DocType("Purchase Invoice")
        month_expr = DateFormat(pi.posting_date, "%Y-%m").as_("month")
        q = (
            frappe.qb.from_(pi)
            .select(
                month_expr,
                Sum(pi.grand_total).as_("spend"),
                Count("*").as_("orders"),
            )
            .where(pi.posting_date.between(self.from_date, self.to_date))
            .where(pi.company == self.company)
            .where(pi.docstatus == 1)
            .groupby(month_expr)
            .orderby(month_expr)
        )
        return q.run(as_dict=True)

    # ------------------------------------------------------------------
    # Supplier performance (on-time delivery)
    # ------------------------------------------------------------------
    def _get_supplier_performance(self) -> List[Dict]:
        """Get supplier delivery performance.

        Purchase Receipt has no parent-level ``purchase_order`` column; the PO
        link lives on Purchase Receipt Item. Resolve each receipt to the
        earliest required-by date among its linked POs, then aggregate at
        receipt grain.
        """
        pr = DocType("Purchase Receipt")
        pri = DocType("Purchase Receipt Item")
        po = DocType("Purchase Order")

        # Subquery: one row per receipt, with the earliest PO schedule_date.
        receipt_subq = (
            frappe.qb.from_(pr)
            .join(pri)
            .on(pri.parent == pr.name)
            .join(po)
            .on(pri.purchase_order == po.name)
            .select(
                pr.name.as_("name"),
                pr.supplier.as_("supplier"),
                pr.supplier_name.as_("supplier_name"),
                pr.posting_date.as_("posting_date"),
                # MIN(po.schedule_date) is mapped to MariaDB via PyPika's Min.
                # We use a field reference and aggregate it with the explicit
                # ``MIN`` function on the joined PO table.
                Min(po.schedule_date).as_("schedule_date"),
            )
            .where(pr.posting_date.between(self.from_date, self.to_date))
            .where(pr.company == self.company)
            .where(pr.docstatus == 1)
            .where(pri.purchase_order.notnull())
            .where(pri.purchase_order != "")
            .groupby(pr.name, pr.supplier, pr.supplier_name, pr.posting_date)
        )
        # Alias the subquery so outer FROM can reference its columns.
        r = receipt_subq.as_("r")

        on_time_flag = Case().when(r.posting_date <= r.schedule_date, 1).else_(0)

        on_time_pct = Round(Sum(on_time_flag) / Count("*") * 100, 2).as_("on_time_percent")
        q = (
            frappe.qb.from_(r)
            .select(
                r.supplier,
                r.supplier_name,
                Count("*").as_("total_receipts"),
                Sum(on_time_flag).as_("on_time"),
                on_time_pct,
            )
            .groupby(r.supplier, r.supplier_name)
            .having(Count("*") >= 3)
            .orderby(on_time_pct, order=frappe.qb.desc)
            .limit(10)
        )
        return q.run(as_dict=True)

    # ------------------------------------------------------------------
    # Pending orders
    # ------------------------------------------------------------------
    def _get_pending_orders(self) -> Dict[str, Any]:
        """Get pending purchase orders"""
        po = DocType("Purchase Order")
        q = (
            frappe.qb.from_(po)
            .select(
                Count("*").as_("count"),
                Sum(po.grand_total).as_("total_value"),
            )
            .where(po.company == self.company)
            .where(po.docstatus == 1)
            .where(po.status.notin(_CLOSED_PO_STATUSES))
        )
        rows = q.run(as_dict=True)
        return rows[0] if rows else {}
