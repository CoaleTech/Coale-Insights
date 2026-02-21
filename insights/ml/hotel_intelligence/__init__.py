# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Hotel Intelligence Analytics Engine

Provides comprehensive hotel analytics including occupancy metrics, guest intelligence,
restaurant performance (RevPASH, menu engineering), and event analytics.

This package integrates with the Hoteli app's DocTypes:
- Hotel Reservation, Hotel Room, Hotel Guest
- Reservation Room, Event Booking, Banquet Hall
- Restaurant Section, Housekeeping Task
- Sales Invoice (POS orders)

Sub-modules:
- data.py            : Centralized SQL queries against Hoteli DocTypes
- occupancy.py       : Occupancy rate, ADR, RevPAR, daily trends
- guest_analytics.py : Repeat guest rate, segmentation, nationality distribution
- restaurant.py      : RevPASH, menu engineering matrix, table turnover
- events.py          : Event revenue, type distribution, hall utilization
- demand.py          : Room demand forecasting (Holt-Winters)
- pricing.py         : Dynamic pricing suggestions per room type
- consumption.py     : F&B consumption forecasting (occupancy-driven)
"""

import frappe
from datetime import datetime
from typing import Dict, Any

from insights.ml.base import BaseMLModel


class HotelIntelligence(BaseMLModel):
    """
    Hotel Intelligence Analytics Engine

    Provides:
    - Occupancy Analytics (occupancy rate, ADR, RevPAR, trends)
    - Guest Intelligence (repeat rate, segments, nationality, VIP)
    - Restaurant Analytics (RevPASH, menu engineering, peak hours)
    - Event Analytics (revenue, type distribution, hall utilization)
    - Revenue Breakdown across all departments
    - Executive Summary with key KPIs
    - Room Demand Forecasting (Holt-Winters exponential smoothing)
    - Dynamic Pricing Recommendations
    - F&B Consumption Forecasting
    """

    def __init__(self, date_filter: str = '12m'):
        super().__init__()
        self.model_name = "HotelIntelligence"
        self.date_filter = date_filter

    def train(self) -> Dict[str, Any]:
        """Compute all hotel KPIs and cache results"""
        # Check if hoteli app is installed
        if not frappe.db.exists("DocType", "Hotel Reservation"):
            return {"status": "error", "message": "Hoteli app not installed"}

        # Import sub-modules and aggregate results
        from .occupancy import OccupancyAnalytics
        from .guest_analytics import GuestAnalytics
        from .restaurant import RestaurantAnalytics
        from .events import EventAnalytics
        from .demand import RoomDemandForecasting
        from .pricing import DynamicPricing
        from .consumption import ConsumptionForecasting

        occupancy = OccupancyAnalytics(self.date_filter)
        guests = GuestAnalytics(self.date_filter)
        restaurant = RestaurantAnalytics(self.date_filter)
        events = EventAnalytics(self.date_filter)

        occupancy_data = occupancy.compute()
        guest_data = guests.compute()
        restaurant_data = restaurant.compute()
        event_data = events.compute()

        # Advanced forecasting modules
        demand_data = {}
        pricing_data = {}
        consumption_data = {}
        try:
            demand_data = RoomDemandForecasting(self.date_filter).compute(forecast_days=30)
        except Exception as e:
            frappe.log_error(f"Demand forecasting failed: {e}", "Hotel Intelligence")
            demand_data = {"status": "error", "message": str(e)}

        try:
            pricing_data = DynamicPricing(self.date_filter).compute(forecast_days=14)
        except Exception as e:
            frappe.log_error(f"Dynamic pricing failed: {e}", "Hotel Intelligence")
            pricing_data = {"status": "error", "message": str(e)}

        try:
            consumption_data = ConsumptionForecasting(self.date_filter).compute(forecast_days=14)
        except Exception as e:
            frappe.log_error(f"Consumption forecasting failed: {e}", "Hotel Intelligence")
            consumption_data = {"status": "error", "message": str(e)}

        # Extended analytics from Hoteli app
        from .cost_analytics import CostAnalytics
        from .operations import OperationsAnalytics
        from .kitchen_analytics import KitchenFBAnalytics

        cost_data = {}
        operations_data = {}
        kitchen_fb_data = {}

        try:
            cost_data = CostAnalytics(self.date_filter).compute()
        except Exception as e:
            frappe.log_error(f"Cost analytics failed: {e}", "Hotel Intelligence")
            cost_data = {"error": str(e)}

        try:
            operations_data = OperationsAnalytics(self.date_filter).compute()
        except Exception as e:
            frappe.log_error(f"Operations analytics failed: {e}", "Hotel Intelligence")
            operations_data = {"error": str(e)}

        try:
            kitchen_fb_data = KitchenFBAnalytics(self.date_filter).compute()
        except Exception as e:
            frappe.log_error(f"Kitchen/F&B analytics failed: {e}", "Hotel Intelligence")
            kitchen_fb_data = {"error": str(e)}

        result = {
            "status": "success",
            "analysis_date": datetime.now().isoformat(),
            "date_filter": self.date_filter,
            "occupancy": occupancy_data,
            "guest_analytics": guest_data,
            "restaurant": restaurant_data,
            "events": event_data,
            "demand_forecast": demand_data,
            "pricing": pricing_data,
            "consumption_forecast": consumption_data,
            "revenue_breakdown": self._compute_revenue_breakdown(
                occupancy_data, restaurant_data, event_data
            ),
            "summary": self._compute_summary(
                occupancy_data, guest_data, restaurant_data, event_data
            ),
            # Extended analytics
            "cost_analytics": cost_data.get("cost_analytics", {}),
            "kpi_data": cost_data.get("kpi_data", {}),
            "operational_metrics": operations_data.get("operational_metrics", {}),
            "checkin_checkout": operations_data.get("checkin_checkout", {}),
            "room_utilization": operations_data.get("room_utilization", {}),
            "booking_patterns": operations_data.get("booking_patterns", {}),
            "kitchen_analytics": kitchen_fb_data.get("kitchen", {}),
            "restaurant_extended": kitchen_fb_data.get("restaurant_extended", {}),
            "event_extended": kitchen_fb_data.get("event_extended", {}),
        }

        # Cache results
        self.cache_results("hotel_intelligence", result, expires_in_hours=12)

        # Log training
        self.log_training({
            "occupancy_rate": occupancy_data.get("occupancy_rate", 0),
            "adr": occupancy_data.get("adr", 0),
            "total_guests": guest_data.get("total_guests", 0),
            "total_events": event_data.get("total_events", 0),
        })

        return result

    def predict(self, data=None) -> Dict[str, Any]:
        """Return cached hotel intelligence results"""
        return self.get_cached_results("hotel_intelligence") or {}

    def _compute_revenue_breakdown(
        self,
        occupancy_data: Dict,
        restaurant_data: Dict,
        event_data: Dict,
    ) -> Dict[str, Any]:
        """Compute revenue breakdown across all hotel departments"""
        room_revenue = float(occupancy_data.get("total_room_revenue", 0))
        restaurant_revenue = float(restaurant_data.get("total_revenue", 0))
        event_revenue = float(event_data.get("total_revenue", 0))
        total = room_revenue + restaurant_revenue + event_revenue

        other_revenue = 0  # Placeholder for ancillary services (spa, minibar, etc.)

        breakdown = {
            "rooms_revenue": room_revenue,
            "fnb_revenue": restaurant_revenue,
            "events_revenue": event_revenue,
            "other_revenue": other_revenue,
            "total_revenue": total,
            "rooms_share_pct": round(room_revenue / total * 100, 1) if total else 0,
            "fnb_share_pct": round(restaurant_revenue / total * 100, 1) if total else 0,
            "events_share_pct": round(event_revenue / total * 100, 1) if total else 0,
            "other_share_pct": round(other_revenue / total * 100, 1) if total else 0,
        }

        return breakdown

    def _compute_summary(
        self,
        occupancy_data: Dict,
        guest_data: Dict,
        restaurant_data: Dict,
        event_data: Dict,
    ) -> Dict[str, Any]:
        """Compute executive summary with key KPIs"""
        return {
            # Occupancy KPIs
            "occupancy_rate": occupancy_data.get("occupancy_rate", 0),
            "adr": occupancy_data.get("adr", 0),
            "revpar": occupancy_data.get("revpar", 0),
            "available_rooms": occupancy_data.get("today_snapshot", {}).get("available_rooms", 0),
            "in_house_guests": occupancy_data.get("today_snapshot", {}).get("in_house_guests", 0),

            # Guest KPIs
            "total_guests": guest_data.get("total_guests", 0),
            "repeat_guest_rate": guest_data.get("repeat_guest_rate", 0),
            "avg_guest_spend": guest_data.get("avg_guest_spend", 0),
            "vip_count": guest_data.get("vip_count", 0),

            # Restaurant KPIs
            "restaurant_revenue": restaurant_data.get("total_revenue", 0),
            "avg_revpash": restaurant_data.get("avg_revpash", 0),

            # Event KPIs
            "total_events": event_data.get("total_events", 0),
            "event_revenue": event_data.get("total_revenue", 0),
            "avg_revenue_per_event": event_data.get("avg_revenue_per_event", 0),
        }
