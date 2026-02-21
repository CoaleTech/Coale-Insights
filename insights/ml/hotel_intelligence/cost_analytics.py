# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Cost Analytics Module

Calls Hoteli's get_cost_analytics() and get_kpi_data() to provide:
- CPOR (Cost Per Occupied Room)
- Cost breakdown by category (room supplies, breakfast, staff)
- Revenue vs cost analysis with profit margins
- KPI targets and performance scoring
"""

import frappe
from frappe.utils import add_days, nowdate, getdate
from insights.api.ml import get_date_filter_sql


class CostAnalytics:
    def __init__(self, date_filter: str = '12m'):
        self.date_filter = date_filter

    def _get_date_range(self):
        today = getdate(nowdate())
        mapping = {
            '7d': 7, '30d': 30, '90d': 90,
            '6m': 180, '12m': 365,
        }
        days = mapping.get(self.date_filter, 365)
        return str(add_days(today, -days)), str(today)

    def compute(self) -> dict:
        from_date, to_date = self._get_date_range()
        result = {
            "cost_analytics": {},
            "kpi_data": {},
        }

        try:
            from hoteli.hoteli.api.public_api import get_cost_analytics
            result["cost_analytics"] = get_cost_analytics(
                from_date=from_date, to_date=to_date
            ) or {}
        except Exception as e:
            frappe.log_error(f"Cost analytics failed: {e}", "Hotel Intelligence")
            result["cost_analytics"] = {"error": str(e)}

        try:
            from hoteli.hoteli.api.public_api import get_kpi_data
            result["kpi_data"] = get_kpi_data(
                from_date=from_date, to_date=to_date
            ) or {}
        except Exception as e:
            frappe.log_error(f"KPI data failed: {e}", "Hotel Intelligence")
            result["kpi_data"] = {"error": str(e)}

        return result
