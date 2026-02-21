# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Operations Analytics Module

Calls Hoteli's existing API functions for:
- GoPAR, RPG, operational metrics
- Check-in/checkout analytics with overstay tracking
- Room utilization by floor/wing
- Booking patterns by day of week
"""

import frappe
from frappe.utils import add_days, nowdate, getdate


class OperationsAnalytics:
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
            "operational_metrics": {},
            "checkin_checkout": {},
            "room_utilization": {},
            "booking_patterns": {},
        }

        try:
            from hoteli.hoteli.api.public_api import get_occupancy_operational_metrics
            result["operational_metrics"] = get_occupancy_operational_metrics() or {}
        except Exception as e:
            frappe.log_error(f"Operational metrics failed: {e}", "Hotel Intelligence")
            result["operational_metrics"] = {"error": str(e)}

        try:
            from hoteli.hoteli.api.public_api import get_checkin_checkout_analytics
            result["checkin_checkout"] = get_checkin_checkout_analytics() or {}
        except Exception as e:
            frappe.log_error(f"Check-in/checkout analytics failed: {e}", "Hotel Intelligence")
            result["checkin_checkout"] = {"error": str(e)}

        try:
            from hoteli.hoteli.api.public_api import get_room_utilization_analytics
            result["room_utilization"] = get_room_utilization_analytics() or {}
        except Exception as e:
            frappe.log_error(f"Room utilization failed: {e}", "Hotel Intelligence")
            result["room_utilization"] = {"error": str(e)}

        try:
            from hoteli.hoteli.api.public_api import get_booking_patterns_by_day
            result["booking_patterns"] = get_booking_patterns_by_day(
                from_date=from_date, to_date=to_date
            ) or {}
        except Exception as e:
            frappe.log_error(f"Booking patterns failed: {e}", "Hotel Intelligence")
            result["booking_patterns"] = {"error": str(e)}

        return result
