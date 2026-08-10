# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Production Data Collector - Work orders, efficiency, workstation utilization"""

import frappe
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
            "monthly_trend": self._get_monthly_trend(),
            "workstation_utilization": self._get_workstation_utilization()
        }

    def _get_production_summary(self) -> Dict[str, Any]:
        """Get production summary"""
        result = frappe.db.sql("""
            SELECT
                COUNT(*) as total_orders,
                SUM(qty) as planned_qty,
                SUM(produced_qty) as produced_qty
            FROM `tabWork Order`
            WHERE planned_start_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
        """, (self.from_date, self.to_date, self.company), as_dict=True)

        return result[0] if result else {}

    def _get_work_order_status(self) -> List[Dict]:
        """Get work order status breakdown"""
        return frappe.db.sql("""
            SELECT
                status,
                COUNT(*) as count,
                SUM(qty) as total_qty
            FROM `tabWork Order`
            WHERE company = %s
            AND docstatus = 1
            GROUP BY status
        """, (self.company,), as_dict=True)

    def _get_production_efficiency(self) -> Dict[str, Any]:
        """Calculate production efficiency"""
        result = frappe.db.sql("""
            SELECT
                SUM(produced_qty) as produced,
                SUM(qty) as planned
            FROM `tabWork Order`
            WHERE planned_start_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
            AND status = 'Completed'
        """, (self.from_date, self.to_date, self.company), as_dict=True)

        produced = flt(result[0].get("produced")) if result else 0
        planned = flt(result[0].get("planned")) if result else 0
        efficiency = (produced / planned * 100) if planned else 0

        return {
            "produced_qty": produced,
            "planned_qty": planned,
            "efficiency_percent": round(efficiency, 2)
        }

    def _get_top_produced_items(self, limit: int = 10) -> List[Dict]:
        """Get top produced items"""
        return frappe.db.sql("""
            SELECT
                production_item as item_code,
                item_name,
                SUM(produced_qty) as total_produced
            FROM `tabWork Order`
            WHERE planned_start_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
            GROUP BY production_item, item_name
            ORDER BY total_produced DESC
            LIMIT %s
        """, (self.from_date, self.to_date, self.company, limit), as_dict=True)

    def _get_monthly_trend(self) -> List[Dict]:
        """Get monthly production trend"""
        return frappe.db.sql("""
            SELECT
                DATE_FORMAT(planned_start_date, '%%Y-%%m') as month,
                SUM(qty) as planned_qty,
                SUM(produced_qty) as produced_qty
            FROM `tabWork Order`
            WHERE planned_start_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
            GROUP BY month
            ORDER BY month
        """, (self.from_date, self.to_date, self.company), as_dict=True)

    def _get_workstation_utilization(self) -> List[Dict]:
        """Get workstation utilization"""
        return frappe.db.sql("""
            SELECT
                workstation,
                COUNT(*) as job_count,
                SUM(total_time_in_mins) as total_minutes
            FROM `tabJob Card`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
            GROUP BY workstation
            ORDER BY total_minutes DESC
        """, (self.from_date, self.to_date, self.company), as_dict=True)
