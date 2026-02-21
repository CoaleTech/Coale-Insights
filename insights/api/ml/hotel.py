# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Hotel Intelligence API Endpoints
"""

import frappe
from typing import Dict, Any
from insights.api.response import success, error


@frappe.whitelist()
def hotel_intelligence(refresh: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Get comprehensive hotel intelligence"""
    try:
        from insights.ml.hotel_intelligence import HotelIntelligence
        model = HotelIntelligence(date_filter=date_filter)
        if not refresh:
            cached = model.get_cached_results("hotel_intelligence")
            if cached:
                return success(cached)
        result = model.train()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def occupancy_forecast(periods: int = 30, date_filter: str = '12m') -> Dict[str, Any]:
    """Get occupancy forecast for next N days using Holt-Winters method"""
    try:
        from insights.ml.hotel_intelligence.demand import RoomDemandForecasting
        model = RoomDemandForecasting(date_filter=date_filter)
        result = model.compute(forecast_days=int(periods))
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def hotel_revenue_breakdown(date_filter: str = '12m') -> Dict[str, Any]:
    """Get hotel revenue breakdown by source (rooms, F&B, events)"""
    try:
        from insights.ml.hotel_intelligence import HotelIntelligence
        model = HotelIntelligence(date_filter=date_filter)
        cached = model.get_cached_results("hotel_intelligence")
        if cached:
            return success(cached.get("revenue_breakdown", {}))
        result = model.train()
        return success(result.get("revenue_breakdown", {}))
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def guest_analytics(date_filter: str = '12m') -> Dict[str, Any]:
    """Get guest intelligence metrics"""
    try:
        from insights.ml.hotel_intelligence.guest_analytics import GuestAnalytics
        model = GuestAnalytics(date_filter=date_filter)
        result = model.compute()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def restaurant_intelligence(date_filter: str = '12m') -> Dict[str, Any]:
    """Get restaurant analytics: RevPASH, table turnover, peak hours"""
    try:
        from insights.ml.hotel_intelligence.restaurant import RestaurantAnalytics
        model = RestaurantAnalytics(date_filter=date_filter)
        result = model.compute()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def menu_engineering(date_filter: str = '12m') -> Dict[str, Any]:
    """Get menu engineering matrix (Stars/Puzzles/Plowhorses/Dogs)"""
    try:
        from insights.ml.hotel_intelligence.restaurant import RestaurantAnalytics
        model = RestaurantAnalytics(date_filter=date_filter)
        result = model.compute()
        return success(result.get("menu_engineering", {}))
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def consumption_forecast(periods: int = 14, date_filter: str = '12m') -> Dict[str, Any]:
    """Get occupancy-driven F&B inventory prediction"""
    try:
        from insights.ml.hotel_intelligence.consumption import ConsumptionForecasting
        model = ConsumptionForecasting(date_filter=date_filter)
        result = model.compute(forecast_days=int(periods))
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def event_intelligence(date_filter: str = '12m') -> Dict[str, Any]:
    """Get events/banquet analytics"""
    try:
        from insights.ml.hotel_intelligence.events import EventAnalytics
        model = EventAnalytics(date_filter=date_filter)
        result = model.compute()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def pricing_recommendations(forecast_days: int = 14, date_filter: str = '12m') -> Dict[str, Any]:
    """Get dynamic pricing recommendations per room type"""
    try:
        from insights.ml.hotel_intelligence.pricing import DynamicPricing
        model = DynamicPricing(date_filter=date_filter)
        result = model.compute(forecast_days=int(forecast_days))
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def cost_analytics(date_filter: str = '12m') -> Dict[str, Any]:
    """Get cost analytics: CPOR, cost breakdown, profit margins, KPI targets"""
    try:
        from insights.ml.hotel_intelligence.cost_analytics import CostAnalytics
        result = CostAnalytics(date_filter=date_filter).compute()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def operations_analytics(date_filter: str = '12m') -> Dict[str, Any]:
    """Get operations: GoPAR, check-in/checkout, room utilization, booking patterns"""
    try:
        from insights.ml.hotel_intelligence.operations import OperationsAnalytics
        result = OperationsAnalytics(date_filter=date_filter).compute()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def kitchen_fb_analytics(date_filter: str = '12m') -> Dict[str, Any]:
    """Get kitchen/F&B: prep times, food cost %, waiter performance, bar analytics"""
    try:
        from insights.ml.hotel_intelligence.kitchen_analytics import KitchenFBAnalytics
        result = KitchenFBAnalytics(date_filter=date_filter).compute()
        return success(result)
    except Exception as e:
        return error(str(e))
