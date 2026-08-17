# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Sales Intelligence API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any, List
from insights.api.response import success, error
from insights.api.ml.utils import cached_run, run, parse_date_filter


@frappe.whitelist()
def sales_forecast(periods: int = 30, refresh: bool = False) -> Dict[str, Any]:
    """Get the sales forecast.

    `refresh` is kept for backward compatibility with older frontend
    callers; every call computes fresh from MariaDB (one grouped SQL
    query, no cache, no background job, no fork).
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_forecasting import get_sales_forecast

        return success(get_sales_forecast(periods=periods))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_forecast_chart_data() -> Dict[str, Any]:
    """Get forecast data formatted for charts"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_forecasting import get_sales_forecast

        return success(get_sales_forecast())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def sales_intelligence(refresh: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Comprehensive sales intelligence, served from cache and recomputed in
    the background per date_filter.

    `refresh` queues a recompute and keeps serving the payload it already
    has; the hourly scheduler pass keeps it fresh without anyone asking --
    see `insights.api.ml.utils.cached_run`.

    Routes to the Ibis-native `insights.ml.sales_intelligence` module,
    not the legacy raw-SQL `insights.reports.sales_intelligence_report`.
    The legacy module's `analyze_sales_reps` groups by `Sales Invoice.owner`
    (the Frappe document creator) and reports the `billing@` accounts
    mailbox as the #1 "sales rep" with 1,111 invoices, never surfacing
    any of the 6 real Sales Person records on the Sales Team child
    table (Milan Mavani 1,851, Khushboo 207, Roja 87, Priyanka 48).
    The Ibis version fixes that, and the dashboard's only caller is
    this endpoint, so the routing switch is what actually surfaces the
    real sales rep rankings to the Revenue dashboard.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import get_sales_intelligence

        return cached_run(
            lambda: run(lambda: get_sales_intelligence(date_filter=date_filter), "sales_intelligence"),
            cache_key=f"insights_ml_sales_intelligence:{date_filter}",
        )
    except (frappe.PermissionError, frappe.ServiceUnavailableError):
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def payment_mix() -> Dict[str, Any]:
    """Analyze payment method mix"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import calculate_payment_mix

        return success(calculate_payment_mix())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def sales_rep_performance() -> Dict[str, Any]:
    """Get sales representative performance analysis"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import analyze_sales_reps

        return success(analyze_sales_reps())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def revenue_breakdown() -> Dict[str, Any]:
    """Get revenue breakdown by various dimensions"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import analyze_by_dimensions

        return success(analyze_by_dimensions())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def margin_analysis() -> Dict[str, Any]:
    """Analyze profit margins"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import analyze_margins

        return success(analyze_margins())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def sales_comparisons() -> Dict[str, Any]:
    """Compare sales across periods and dimensions"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import calculate_comparisons

        return success(calculate_comparisons())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def train_forecast_models(model_type: str = 'all') -> Dict[str, Any]:
    """Recompute the sales forecast.

    `model_type` is kept for backward compatibility and ignored -- there
    is only one forecast model now. Every call computes fresh from
    MariaDB (no cache to invalidate, no background job, no fork).
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_forecasting import run_sales_forecast

        return success(run_sales_forecast())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_historical_and_forecast_by_dimension(dimension: str = 'product_group') -> Dict[str, Any]:
    """Monthly actuals plus a short projection, by product group and territory.

    `dimension` is accepted for backward compatibility and ignored: the Revenue
    dashboard's only caller passes 'both' and renders both tables from one
    response, so splitting the query would just double the round trips.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_forecasting import get_dimensional_history_and_forecast

        return success(get_dimensional_history_and_forecast())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def source_attributed_sales(date_filter: str = '12m') -> Dict[str, Any]:
    """Get revenue attributed to lead sources."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_source_analytics import get_source_attributed_sales
        from insights.api.ml.utils import parse_date_filter
        start_dt, end_dt = parse_date_filter(date_filter)
        start = start_dt.strftime("%Y-%m-%d") if start_dt else "2000-01-01"
        end = end_dt.strftime("%Y-%m-%d") if end_dt else frappe.utils.nowdate()
        return success(get_source_attributed_sales(start, end))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def quotation_analytics(date_filter: str = '12m') -> Dict[str, Any]:
    """Get quotation funnel analytics."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_source_analytics import get_quotation_analytics
        from insights.api.ml.utils import parse_date_filter
        start_dt, end_dt = parse_date_filter(date_filter)
        start = start_dt.strftime("%Y-%m-%d") if start_dt else "2000-01-01"
        end = end_dt.strftime("%Y-%m-%d") if end_dt else frappe.utils.nowdate()
        return success(get_quotation_analytics(start, end))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def territory_sales_performance(date_filter: str = '12m') -> Dict[str, Any]:
    """Get sales performance by territory."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_source_analytics import get_territory_performance
        from insights.api.ml.utils import parse_date_filter
        start_dt, end_dt = parse_date_filter(date_filter)
        start = start_dt.strftime("%Y-%m-%d") if start_dt else "2000-01-01"
        end = end_dt.strftime("%Y-%m-%d") if end_dt else frappe.utils.nowdate()
        return success(get_territory_performance(start, end))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def territory_performance(date_filter: str = '12m') -> Dict[str, Any]:
    """Alias for territory_sales_performance."""
    return territory_sales_performance(date_filter=date_filter)

# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_sales_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")
    period = f.get("period", "30d")

    def _period_bound(period_value: str):
        """A `frappe.get_list` filter-tuple for `period_value`, or ``None`` for
        "all"/unbounded. Uses the same `parse_date_filter` as the KPI-card
        payloads (`sales_intelligence`, `quotation_analytics`, ...) so a
        drill-down's row count always matches the number the user clicked --
        the old hardcoded `{"7d":7,...}` map silently fell back to 30 days for
        "6m" and "all" (both real options on the shared date filter), which
        would have shown a 30-day list under a 6-month or all-time total.
        """
        start_dt, _end_dt = parse_date_filter(period_value)
        if start_dt is None:
            return None
        return (">=", start_dt.strftime("%Y-%m-%d"))

    if metric == "total_orders":
        frappe.has_permission("Sales Invoice", throw=True)
        db_filters: Dict[str, Any] = {"docstatus": 1}
        bound = _period_bound(period)
        if bound:
            db_filters["posting_date"] = bound
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "customer", "posting_date", "grand_total", "currency", "territory"],
            start=start, page_length=page_size, order_by="posting_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Territory", "fieldname": "territory", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Invoice", filters=db_filters),
        }

    if metric == "pending_orders":
        frappe.has_permission("Sales Order", throw=True)
        db_filters = {"docstatus": 1, "status": ("not in", ["Completed", "Cancelled", "Closed"])}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Sales Order",
            filters=db_filters,
            fields=["name", "customer", "transaction_date", "delivery_date", "grand_total", "status"],
            start=start, page_length=page_size, order_by="transaction_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Order", "fieldname": "name", "fieldtype": "Link", "options": "Sales Order"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Date", "fieldname": "transaction_date", "fieldtype": "Date"},
                {"label": "Delivery", "fieldname": "delivery_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Order", filters=db_filters),
        }

    if metric == "sales_by_territory":
        frappe.has_permission("Sales Invoice", throw=True)
        territory = f.get("territory")
        db_filters: Dict[str, Any] = {"docstatus": 1}
        bound = _period_bound(period)
        if bound:
            db_filters["posting_date"] = bound
        if company:
            db_filters["company"] = company
        if territory:
            db_filters["territory"] = territory
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "customer", "territory", "posting_date", "grand_total"],
            start=start, page_length=page_size, order_by="posting_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Territory", "fieldname": "territory", "fieldtype": "Data"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Invoice", filters=db_filters),
        }

    if metric == "quotations":
        frappe.has_permission("Quotation", throw=True)
        bucket = f.get("bucket", "all")
        db_filters: Dict[str, Any] = {"docstatus": 1}
        bound = _period_bound(period)
        if bound:
            db_filters["transaction_date"] = bound
        if company:
            db_filters["company"] = company
        if bucket == "won":
            db_filters["status"] = "Ordered"
        elif bucket == "lost":
            db_filters["status"] = "Lost"
        elif bucket == "pending":
            # Mirrors `get_quotation_analytics`'s definition: total - won - lost.
            db_filters["status"] = ("not in", ["Ordered", "Lost"])
        rows = frappe.get_list(
            "Quotation",
            filters=db_filters,
            fields=["name", "party_name", "transaction_date", "grand_total", "status", "order_lost_reason"],
            start=start, page_length=page_size, order_by="transaction_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Quotation", "fieldname": "name", "fieldtype": "Link", "options": "Quotation"},
                {"label": "Party", "fieldname": "party_name", "fieldtype": "Data"},
                {"label": "Date", "fieldname": "transaction_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
                {"label": "Lost Reason", "fieldname": "order_lost_reason", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Quotation", filters=db_filters),
        }

    if metric == "sales_by_source":
        frappe.has_permission("Sales Invoice", throw=True)
        source = f.get("source")
        if not source:
            frappe.throw(_("Source is required"), frappe.ValidationError)
        from insights.ml.source_attribution import build_source_attribution_map
        bound = _period_bound(period)
        start_iso = bound[1] if bound else "2000-01-01"
        end_iso = frappe.utils.nowdate()
        attr_map = build_source_attribution_map(start_iso, end_iso)
        db_filters: Dict[str, Any] = {"docstatus": 1, "is_return": 0}
        if bound:
            db_filters["posting_date"] = bound
        if company:
            db_filters["company"] = company
        if source == "Unattributed":
            excluded = list(attr_map.keys())
            if excluded:
                db_filters["name"] = ("not in", excluded)
        else:
            matching = [name for name, src in attr_map.items() if src == source]
            db_filters["name"] = ("in", matching or ["__none__"])
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "customer", "posting_date", "grand_total", "territory"],
            start=start, page_length=page_size, order_by="posting_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Territory", "fieldname": "territory", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Invoice", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
