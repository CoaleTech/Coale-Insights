# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Production Data Collector - Work orders, efficiency, workstation utilization"""

import frappe
from frappe.query_builder import DocType, Order
from frappe.query_builder.functions import Count, DateFormat, Sum
from frappe.utils import flt
from typing import Dict, Any, List

from insights.analytics.collectors.base import BaseCollector


class ProductionDataCollector(BaseCollector):
    """Collect production data from Manufacturing module"""

    def collect(self) -> Dict[str, Any]:
        return {
            "summary": self._get_production_summary(),
            "work_orders": self._get_work_order_status(),
            "efficiency": self._get_production_efficiency(),
            "top_items": self._get_top_produced_items(),
            "completed_order_count": self._get_completed_order_count(),
            "monthly_trend": self._get_monthly_trend(),
            "workstation_utilization": self._get_workstation_utilization()
        }

    def _get_production_summary(self) -> Dict[str, Any]:
        """Get production summary"""
        WorkOrder = DocType("Work Order")
        result = (
            frappe.qb.from_(WorkOrder)
            .select(
                Count("*").as_("total_orders"),
                Sum(WorkOrder.qty).as_("planned_qty"),
                Sum(WorkOrder.produced_qty).as_("produced_qty"),
            )
            .where(WorkOrder.planned_start_date.between(self.from_date, self.to_date))
            .where(WorkOrder.company == self.company)
            .where(WorkOrder.docstatus == 1)
            .run(as_dict=True)
        )

        return result[0] if result else {}

    def _get_work_order_status(self) -> List[Dict]:
        """Get work order status breakdown"""
        WorkOrder = DocType("Work Order")
        return (
            frappe.qb.from_(WorkOrder)
            .select(
                WorkOrder.status,
                Count("*").as_("count"),
                Sum(WorkOrder.qty).as_("total_qty"),
            )
            .where(WorkOrder.company == self.company)
            .where(WorkOrder.docstatus == 1)
            .groupby(WorkOrder.status)
            .run(as_dict=True)
        )

    def _get_production_efficiency(self) -> Dict[str, Any]:
        """Calculate production efficiency"""
        WorkOrder = DocType("Work Order")
        result = (
            frappe.qb.from_(WorkOrder)
            .select(
                Sum(WorkOrder.produced_qty).as_("produced"),
                Sum(WorkOrder.qty).as_("planned"),
            )
            .where(WorkOrder.planned_start_date.between(self.from_date, self.to_date))
            .where(WorkOrder.company == self.company)
            .where(WorkOrder.docstatus == 1)
            .where(WorkOrder.status == "Completed")
            .run(as_dict=True)
        )

        produced = flt(result[0].get("produced")) if result else 0
        planned = flt(result[0].get("planned")) if result else 0
        efficiency = round(produced / planned * 100, 2) if planned else None

        return {
            "produced_qty": produced,
            "planned_qty": planned,
            # None (not 0) when nothing was planned: a 0% efficiency score on
            # an empty period reads as "everything failed" on a severity-
            # coloured KPI card, when the truth is there was nothing to measure.
            "efficiency_percent": efficiency
        }

    def _get_completed_order_count(self) -> int:
        """Count Work Orders completed within the period (for completion-rate metrics)."""
        WorkOrder = DocType("Work Order")
        result = (
            frappe.qb.from_(WorkOrder)
            .select(Count("*").as_("completed"))
            .where(WorkOrder.planned_start_date.between(self.from_date, self.to_date))
            .where(WorkOrder.company == self.company)
            .where(WorkOrder.docstatus == 1)
            .where(WorkOrder.status == "Completed")
            .run(as_dict=True)
        )

        return int(result[0].get("completed") or 0) if result else 0

    def _get_top_produced_items(self, limit: int = 10) -> List[Dict]:
        """Get top produced items"""
        WorkOrder = DocType("Work Order")
        return (
            frappe.qb.from_(WorkOrder)
            .select(
                WorkOrder.production_item.as_("item_code"),
                WorkOrder.item_name,
                Sum(WorkOrder.produced_qty).as_("total_produced"),
            )
            .where(WorkOrder.planned_start_date.between(self.from_date, self.to_date))
            .where(WorkOrder.company == self.company)
            .where(WorkOrder.docstatus == 1)
            .groupby(WorkOrder.production_item, WorkOrder.item_name)
            .orderby(Sum(WorkOrder.produced_qty), order=Order.desc)
            .limit(limit)
            .run(as_dict=True)
        )

    def _get_monthly_trend(self) -> List[Dict]:
        """Get monthly production trend"""
        WorkOrder = DocType("Work Order")
        month = DateFormat(WorkOrder.planned_start_date, "%Y-%m").as_("month")
        return (
            frappe.qb.from_(WorkOrder)
            .select(
                month,
                Sum(WorkOrder.qty).as_("planned_qty"),
                Sum(WorkOrder.produced_qty).as_("produced_qty"),
            )
            .where(WorkOrder.planned_start_date.between(self.from_date, self.to_date))
            .where(WorkOrder.company == self.company)
            .where(WorkOrder.docstatus == 1)
            .groupby(month)
            .orderby(month)
            .run(as_dict=True)
        )

    def _get_workstation_utilization(self) -> List[Dict]:
        """Get workstation utilization"""
        JobCard = DocType("Job Card")
        return (
            frappe.qb.from_(JobCard)
            .select(
                JobCard.workstation,
                Count("*").as_("job_count"),
                Sum(JobCard.total_time_in_mins).as_("total_minutes"),
            )
            .where(JobCard.posting_date.between(self.from_date, self.to_date))
            .where(JobCard.company == self.company)
            .where(JobCard.docstatus == 1)
            .groupby(JobCard.workstation)
            .orderby(Sum(JobCard.total_time_in_mins), order=Order.desc)
            .run(as_dict=True)
        )
