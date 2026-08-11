# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Search Intelligence API Endpoints
"""

import frappe
from typing import Dict, Any, List
from insights.api.response import success, error


@frappe.whitelist()
def perform_cross_dashboard_search(query: str, filters: Dict[str, Any] = None, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Perform cross-dashboard search"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService
        service = CrossDashboardSearchService()
        result = service.perform_global_search(query, filters, context)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_search_suggestions(partial_query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get search suggestions"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService
        service = CrossDashboardSearchService()
        result = service.get_search_suggestions(partial_query, context)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_search_history(limit: int = 20) -> Dict[str, Any]:
    """Get search history"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService
        service = CrossDashboardSearchService()
        result = service.get_search_history(limit)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def save_search_favorite(query: str, title: str = None) -> Dict[str, Any]:
    """Save search favorite"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService
        service = CrossDashboardSearchService()
        result = service.save_search_favorite(query, title)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_cross_dashboard_navigation(current_context: Dict[str, Any], target_query: str) -> Dict[str, Any]:
    """Get cross-dashboard navigation"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService
        service = CrossDashboardSearchService()
        result = service.get_cross_dashboard_navigation(current_context, target_query)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_search_help() -> Dict[str, Any]:
    """Get search help"""
    try:
        return success({
            "tips": [
                "Search by customer name, item code, or invoice number",
                "Use filters to narrow results by domain",
                "Recent searches are saved for quick access",
            ],
            "domains": ["customers", "sales", "inventory", "financial", "hr"]
        })
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def search_domain_data(domain_id: str, query: str, filters: Dict[str, Any] = None) -> Dict[str, Any]:
    """Search domain data"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService
        service = CrossDashboardSearchService()
        result = service.perform_global_search(query, filters, {"domain": domain_id})
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_available_search_filters() -> Dict[str, Any]:
    """Get available search filters"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        return success({
            "filters": [
                {"name": "domain", "label": "Domain", "options": ["customers", "sales", "inventory", "financial", "hr"]},
                {"name": "date_range", "label": "Date Range", "type": "date"},
            ]
        })
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))
