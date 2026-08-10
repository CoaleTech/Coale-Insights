# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Sales Intelligence API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any, List
from insights.api.response import success, error


@frappe.whitelist()
def sales_forecast(periods: int = 30, refresh: bool = False) -> Dict[str, Any]:
    """Get the cached sales forecast; `refresh` retrains on a worker.

    `SalesForecasting.train()` fits Holt-Winters over the full daily series --
    14.1s on a development dataset. Never on the request path.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_forecasting import SalesForecasting

        if not refresh:
            cached = SalesForecasting().get_cached_results("sales_forecast")
            if cached:
                return success(cached)

        from insights.api.ml.utils import enqueue_training

        return enqueue_training(
            "insights.ml.scheduler.train_sales_forecast",
            job_id="insights_train_sales_forecast",
            label=_("Sales forecast"),
        )
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
    """Get comprehensive sales intelligence, computed inline on this request.

    `refresh_forecasts=False` on both branches: everything else here is SQL and
    pandas aggregation, but `aggregate_forecasts(refresh=True)` fits a Prophet
    model and up to 100 Holt-Winters models when their caches are cold. That is
    the only unbounded work in the endpoint, and it drags prophet, cmdstanpy and
    matplotlib into the web worker — which on a memory-capped host is enough to
    get the worker killed, and whichever way it ends (timeout, a hung cmdstanpy
    subprocess, or an OOM kill) the browser sees a non-JSON 502.

    Those two models have their own scheduled trainers
    (`scheduler.train_sales_forecast`, `scheduler.train_demand_forecast`) and an
    explicit "ML Forecast Training" button on the dashboard, which already warns
    that training "may take several minutes". Until one of those has run,
    `aggregate_forecasts` leaves the forecast keys null and the section hides
    itself (`RevenueSections.vue:904`).
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_intelligence import SalesIntelligence

        model = SalesIntelligence(date_filter=date_filter)
        if refresh:
            return success(model.train(refresh_forecasts=False))
        return success(model.predict(allow_train=True))
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
    """Train forecasting models, on a worker.

    The dashboard's own button already warns this "may take several minutes",
    which is precisely why it cannot run in the request that triggered it.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.api.ml.utils import enqueue_training

        return enqueue_training(
            "insights.ml.scheduler.train_sales_forecast",
            job_id="insights_train_sales_forecast",
            label=_("Sales forecast"),
        )
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
