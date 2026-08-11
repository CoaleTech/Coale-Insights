# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Cross-Dashboard Search API Endpoints.

All whitelisted functions are thin wrappers over
`insights.ml.cross_dashboard_search.CrossDashboardSearchService`. That service
itself was rewritten to use pure-Python keyword matching + Ibis-flavoured
``frappe.get_all`` calls instead of pandas/sklearn — search is intrinsically a
"query by string, rank by simple score" workload, not a vectorised ML
workload, so the rewrite is largely the removal of an in-memory DataFrame.
"""

from __future__ import annotations

from typing import Any, Dict

import frappe

from insights.api.response import error, success


@frappe.whitelist()
def perform_cross_dashboard_search(
    query: str,
    filters: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Perform a cross-dashboard search.

    The frontend (``CrossDashboardSearch.vue``) reads the result with::

        response.search_results        -> top-level search results + nav
        response.search_results.results.top_results
        response.search_results.results.by_category
        response.search_results.navigation
        response.agent_response         -> text summary
        response.navigation_recommendations

    The service is responsible for producing that exact envelope.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService

        service = CrossDashboardSearchService()
        return success(service.perform_global_search(query, filters, context))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_search_suggestions(
    partial_query: str,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Get search suggestions for autocomplete."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService

        service = CrossDashboardSearchService()
        return success(service.get_search_suggestions(partial_query, context))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_search_history(limit: int = 20) -> Dict[str, Any]:
    """Return search history for the current session user.

    NB: the ``user`` parameter is intentionally NOT in the signature — it
    was an IDOR vector and was removed (plan-eng-review D-IDOR). Always
    reads `frappe.session.user` server-side.

    The frontend assigns the unwrapped result to `searchHistory.value` and
    iterates it directly, so the response must be a list, not a dict. The
    "Search Activity Log" DocType is not in this bench (plan-eng-review
    code-quality finding 2), so we return an empty list when it does not
    exist rather than fabricating rows.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService

        service = CrossDashboardSearchService()
        return success(service.get_search_history(int(limit)))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def save_search_favorite(query: str, title: str | None = None) -> Dict[str, Any]:
    """Save a search as a favorite for the current session user.

    Same `user` parameter IDOR fix as ``get_search_history`` — the user is
    always taken from `frappe.session.user`, never from the caller.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService

        service = CrossDashboardSearchService()
        return success(service.save_search_favorite(query, title))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_cross_dashboard_navigation(
    current_context: Dict[str, Any],
    target_query: str,
) -> Dict[str, Any]:
    """Get cross-dashboard navigation suggestions for a target query."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService

        service = CrossDashboardSearchService()
        return success(service.get_cross_dashboard_navigation(current_context, target_query))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_search_help() -> Dict[str, Any]:
    """Return help content for the search UI.

    The frontend reads ``result.help_content`` (sub-object with
    ``capabilities`` / ``sample_queries`` / ``tips``), so the response is
    wrapped in that key.
    """
    try:
        return success({
            "help_content": {
                "capabilities": [
                    "Search across customers, sales, inventory, financial, and HR dashboards",
                    "Use natural language: 'top customers this quarter' or 'overdue invoices'",
                    "Filter by domain, date range, and result category",
                    "Save frequently used searches as favorites",
                    "Get context-aware suggestions based on your current dashboard",
                ],
                "sample_queries": [
                    "Top customers by revenue",
                    "Overdue invoices this month",
                    "Inventory items low on stock",
                    "Sales performance this quarter",
                    "Employee headcount by department",
                ],
                "tips": [
                    "Search by customer name, item code, or invoice number",
                    "Use filters to narrow results by domain",
                    "Recent searches are saved for quick access",
                ],
            }
        })
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def search_domain_data(
    domain_id: str,
    query: str,
    filters: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Search within a single dashboard domain."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService

        service = CrossDashboardSearchService()
        return success(service.perform_global_search(query, filters, {"domain": domain_id}))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_available_search_filters() -> Dict[str, Any]:
    """Return the filter options the search UI can present."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        return success({
            "filters": [
                {"name": "domain", "label": "Domain", "options": [
                    "executive", "financial", "sales", "customer",
                    "operations", "hr", "manufacturing", "marketing",
                ]},
                {"name": "date_range", "label": "Date Range", "type": "date"},
                {"name": "priority", "label": "Priority", "options": ["high", "medium", "low"]},
            ]
        })
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))
