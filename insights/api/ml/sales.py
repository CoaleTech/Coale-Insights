# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Sales Intelligence API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any, List
from insights.api.response import success, error
from insights.api.serialization import sanitize_for_json


@frappe.whitelist()
def sales_forecast(periods: int = 30, refresh: bool = False) -> Dict[str, Any]:
    """Get the cached sales forecast; `refresh` retrains inline.

    `SalesForecasting.train()` fits Holt-Winters over the full daily series --
    14.1s on a development dataset. The Redis cache + lock in
    `compute_or_cache` keep the second hit at < 100 ms and prevent
    concurrent training when multiple users open the dashboard at once.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.api.ml.utils import compute_or_cache
        from insights.ml.sales_forecasting import SalesForecasting

        cache_key = "insights:sales_forecast"
        if refresh:
            frappe.cache().delete_value(cache_key)  # type: ignore[union-attr]

        return sanitize_for_json(compute_or_cache(trainer=lambda: SalesForecasting().train(periods=periods),
        cache_key=cache_key,
        label=_("Sales forecast"),))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_forecast_chart_data() -> Dict[str, Any]:
    """Get forecast data formatted for charts"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_forecasting import SalesForecasting
        model = SalesForecasting()
        result = model.predict()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def sales_intelligence(refresh: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Comprehensive sales intelligence — computed on request, cached 24h."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import SalesIntelligence
        from insights.api.ml.utils import compute_or_cache

        cache_key = f"insights:sales_intelligence:{date_filter}"
        if refresh:
            frappe.cache().delete_value(cache_key)  # type: ignore[union-attr]

        return sanitize_for_json(compute_or_cache(trainer=lambda: SalesIntelligence(date_filter=date_filter).train(refresh_forecasts=False),
        cache_key=cache_key,
        label=_("Sales intelligence"),))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def payment_mix() -> Dict[str, Any]:
    """Analyze payment method mix"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import SalesIntelligence
        model = SalesIntelligence()
        full_result = model.predict()
        result = full_result.get("payment_mix", full_result)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def sales_rep_performance() -> Dict[str, Any]:
    """Get sales representative performance analysis"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import SalesIntelligence
        model = SalesIntelligence()
        full_result = model.predict()
        result = full_result.get("sales_reps", full_result)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def revenue_breakdown() -> Dict[str, Any]:
    """Get revenue breakdown by various dimensions"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import SalesIntelligence
        model = SalesIntelligence()
        full_result = model.predict()
        result = full_result.get("dimensions", full_result)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def margin_analysis() -> Dict[str, Any]:
    """Analyze profit margins"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import SalesIntelligence
        model = SalesIntelligence()
        full_result = model.predict()
        result = full_result.get("margins", full_result)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def sales_comparisons() -> Dict[str, Any]:
    """Compare sales across periods and dimensions"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import SalesIntelligence
        model = SalesIntelligence()
        full_result = model.predict()
        result = full_result.get("comparisons", full_result)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def train_forecast_models(model_type: str = 'all') -> Dict[str, Any]:
    """Train forecasting models, inline.

    The dashboard's own button already warns this "may take several minutes";
    `compute_or_cache` returns the cached result if warm, otherwise fits the
    model in the request and caches it for the next call. `model_type` is
    accepted for backward compatibility — only the sales forecast model is
    trained from this endpoint today.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.api.ml.utils import compute_or_cache
        from insights.ml.sales_forecasting import SalesForecasting

        cache_key = "insights:sales_forecast"
        frappe.cache().delete_value(cache_key)  # type: ignore[union-attr]

        return sanitize_for_json(compute_or_cache(trainer=lambda: SalesForecasting().train(),
        cache_key=cache_key,
        label=_("Sales forecast"),))
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
        start, end = [d.strftime("%Y-%m-%d") for d in parse_date_filter(date_filter)]
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
        start, end = [d.strftime("%Y-%m-%d") for d in parse_date_filter(date_filter)]
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
        start, end = [d.strftime("%Y-%m-%d") for d in parse_date_filter(date_filter)]
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

    def _date_filter():
        days = {"7d": 7, "30d": 30, "90d": 90, "12m": 365, "24m": 730}.get(period, 30)
        return frappe.utils.add_days(frappe.utils.today(), -days)

    if metric == "total_orders":
        frappe.has_permission("Sales Invoice", throw=True)
        db_filters = {"docstatus": 1, "posting_date": (">=", _date_filter())}
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
        db_filters = {"docstatus": 1, "posting_date": (">=", _date_filter())}
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

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
