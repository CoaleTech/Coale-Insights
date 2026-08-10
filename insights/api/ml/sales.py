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
    """Get sales forecast"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_forecasting import SalesForecasting
        model = SalesForecasting()
        if not refresh:
            cached = model.get_cached_results("sales_forecast")
            if cached:
                return success(cached)
        result = model.train(periods=int(periods))
        return success(result)
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


def _compute_sales_intelligence(refresh: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Worker-side computation; too slow for the request path on a cold cache."""
    try:
        from insights.ml.sales_intelligence import SalesIntelligence
        model = SalesIntelligence(date_filter=date_filter)
        # allow_train: worker-side, so paying the training cost here is correct.
        return success(model.train() if refresh else model.predict(allow_train=True))
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def sales_intelligence(refresh: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Get comprehensive sales intelligence, computing on a worker when cold."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.api.ml import async_compute

        key = f"sales_intelligence:{date_filter}"
        if refresh:
            async_compute.invalidate(key)

        return async_compute.serve(
            key=key,
            method="insights.api.ml.sales._compute_sales_intelligence",
            kwargs={"refresh": refresh, "date_filter": date_filter},
            permission=("Sales Invoice", "read"),
        )
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
    """Train forecasting models"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_forecasting import SalesForecasting
        model = SalesForecasting()
        result = model.train()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_historical_and_forecast_by_dimension(dimension: str = 'product_group') -> Dict[str, Any]:
    """Get historical and forecast data by dimension"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.sales_forecasting import get_grouped_forecast
        result = get_grouped_forecast(group_by=dimension)
        return success(result)
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
