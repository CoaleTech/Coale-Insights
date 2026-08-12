# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Analytics Data Collectors API
Whitelisted endpoints to fetch aggregated ERPNext module data.
"""

from typing import Dict, Any, Optional

import frappe

from insights.analytics.collectors.base import BaseCollector
from insights.analytics.collectors.financial import FinancialDataCollector
from insights.analytics.collectors.sales import SalesDataCollector
from insights.analytics.collectors.procurement import ProcurementDataCollector
from insights.analytics.collectors.inventory import InventoryDataCollector
from insights.analytics.collectors.production import ProductionDataCollector
from insights.analytics.collectors.customer import CustomerDataCollector
from insights.analytics.collectors.hr import HRDataCollector
from insights.api.ml.permissions import authorize_dashboard

_COLLECTORS: Dict[str, type] = {
    "financial": FinancialDataCollector,
    "sales": SalesDataCollector,
    "procurement": ProcurementDataCollector,
    "inventory": InventoryDataCollector,
    "production": ProductionDataCollector,
    "customer": CustomerDataCollector,
    "hr": HRDataCollector,
}


def get_collector(collector_type: str, filters: Optional[Dict] = None) -> BaseCollector:
    """Return an instantiated collector for the given type.

    Every dashboard path reaches its data through here -- `get_analytics_data`
    and `get_all_analytics_data` below, and `MLAnalyticsEngine.get_dashboard_data`
    -- so this is where the caller is asked whether they may read what the
    collector is about to read. Asking in the endpoints instead would mean six
    copies of the same question, and six copies can disagree.
    """
    collector_class = _COLLECTORS.get(collector_type)
    if not collector_class:
        raise ValueError(f"Unknown collector type: {collector_type}")
    authorize_dashboard(collector_type)
    return collector_class(filters)


@frappe.whitelist()
def get_analytics_data(analytics_type: str, filters: str = None) -> Dict[str, Any]:
    """
    Collect and return analytics data for a single ERPNext module.

    Args:
        analytics_type: One of financial, sales, procurement, inventory,
                        production, customer, hr.
        filters: Optional JSON string of date/company filters.
    """
    filter_dict = {}
    if filters:
        try:
            filter_dict = frappe.parse_json(filters)
        except Exception:
            pass  # Use empty filters rather than failing the request

    collector = get_collector(analytics_type, filter_dict)
    return collector.collect()


@frappe.whitelist()
def get_all_analytics_data(filters: str = None) -> Dict[str, Any]:
    """
    Collect and return analytics data for all ERPNext modules.

    Errors in individual collectors are logged and surfaced per-key
    without failing the entire response.
    """
    filter_dict = {}
    if filters:
        try:
            filter_dict = frappe.parse_json(filters)
        except Exception:
            pass

    result: Dict[str, Any] = {}
    for analytics_type in _COLLECTORS:
        try:
            collector = get_collector(analytics_type, filter_dict)
            result[analytics_type] = collector.collect()
        except Exception as e:
            frappe.log_error(
                f"Error collecting {analytics_type} data: {str(e)}",
                "Analytics Collector",
            )
            result[analytics_type] = {"error": str(e)}

    return result
