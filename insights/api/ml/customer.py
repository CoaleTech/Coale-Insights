# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Customer Intelligence API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any, List
from insights.api.response import success, error


@frappe.whitelist()
def customer_segmentation(refresh: bool = False) -> Dict[str, Any]:
    """Get customer segmentation results"""
    try:
        from insights.ml.customer_segmentation import CustomerSegmentation

        model = CustomerSegmentation()

        if not refresh:
            cached = model.get_cached_results("customer_segmentation")
            if cached:
                return success(cached)

        result = model.train()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_segment_summary() -> Dict[str, Any]:
    """Get summary of customer segments"""
    try:
        result = customer_segmentation()

        if result.get('status') != 'success':
            return result

        summary = result.get('segment_summary', {})

        return success({
            "segments": [
                {
                    "segment": seg,
                    "customer_count": data.get('count', 0),
                    "total_revenue": data.get('total_revenue', 0),
                    "avg_revenue": data.get('avg_revenue', 0)
                }
                for seg, data in summary.items()
            ]
        })
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def customer_intelligence(refresh: bool = False, async_mode: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Get comprehensive customer intelligence"""
    try:
        from insights.ml.customer_intelligence import CustomerIntelligence

        model = CustomerIntelligence(date_filter=date_filter)
        if refresh:
            return success(model.train())
        return success(model.predict())
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "customer_intelligence error")
        return error(str(e))


@frappe.whitelist()
def customer_intelligence_status() -> Dict[str, Any]:
    """Get customer intelligence processing status"""
    try:
        # Implementation would check async processing status
        return success({"status": "completed", "last_run": None})
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def customer_360(customer_id: str) -> Dict[str, Any]:
    """Get 360-degree customer view"""
    try:
        from insights.ml.customer_intelligence import get_customer_360_detail

        result = get_customer_360_detail(customer_id)
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def customer_360_detail(customer_id: str, include_purchases: bool = True, include_recommendations: bool = True) -> Dict[str, Any]:
    """Get detailed 360-degree customer view"""
    try:
        from insights.ml.customer_intelligence import get_customer_360_detail

        result = get_customer_360_detail(customer_id, include_purchases, include_recommendations)
        # The payload carries its own currency so the detail view never has to
        # guess. Without it the frontend fell back to a hardcoded default and
        # rendered INR figures with a Kenyan Shilling symbol.
        if isinstance(result, dict):
            result.setdefault(
                "base_currency",
                frappe.get_cached_value(
                    "Company",
                    frappe.defaults.get_user_default("company")
                    or frappe.db.get_single_value("Global Defaults", "default_company"),
                    "default_currency",
                ),
            )
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def purchase_patterns(top_percentile: int = 20) -> Dict[str, Any]:
    """Analyze customer purchase patterns"""
    try:
        from insights.ml.customer_intelligence import get_purchase_patterns

        result = get_purchase_patterns(top_percentile)
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def cross_sell_opportunities(tier_filter: str = "Diamond,Platinum") -> Dict[str, Any]:
    """Identify cross-sell opportunities"""
    try:
        from insights.ml.customer_intelligence import get_cross_sell_opportunities

        result = get_cross_sell_opportunities(tier_filter)
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def at_risk_customers() -> Dict[str, Any]:
    """Identify customers at risk of churning"""
    try:
        from insights.ml.customer_intelligence import get_at_risk_customers

        result = get_at_risk_customers()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def geographic_insights() -> Dict[str, Any]:
    """Get geographic customer insights"""
    try:
        from insights.ml.customer_intelligence import get_geographic_insights

        result = get_geographic_insights()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def next_best_actions() -> Dict[str, Any]:
    """Get next best actions for customers"""
    try:
        from insights.ml.customer_intelligence import get_next_actions

        result = get_next_actions()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def refresh_scores() -> Dict[str, Any]:
    """Refresh customer intelligence scores"""
    try:
        from insights.ml.customer_intelligence import refresh_customer_scores as _refresh

        result = _refresh()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def customer_counts(date_filter: str = '12m', active_cutoff_months: int = 6) -> Dict[str, Any]:
    """Get customer count metrics."""
    try:
        from insights.ml.customer_intelligence import CustomerIntelligence
        model = CustomerIntelligence(date_filter=date_filter)
        return success(model.get_customer_counts(int(active_cutoff_months)))
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def customer_revenue_split(date_filter: str = '12m') -> Dict[str, Any]:
    """Get revenue split between new and existing customers."""
    try:
        from insights.ml.customer_intelligence import CustomerIntelligence
        model = CustomerIntelligence(date_filter=date_filter)
        return success(model.get_customer_revenue_split())
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def customer_rankings(date_filter: str = '12m', limit: int = 20) -> Dict[str, Any]:
    """Get customer rankings by revenue, profit, margin, consistency."""
    try:
        from insights.ml.customer_intelligence import CustomerIntelligence
        model = CustomerIntelligence(date_filter=date_filter)
        return success(model.get_customer_rankings(int(limit)))
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "customer_rankings error")
        return error(str(e))


@frappe.whitelist()
def customer_variance(date_filter: str = '12m') -> Dict[str, Any]:
    """Get customer target vs actual variance."""
    try:
        from insights.ml.customer_intelligence import CustomerIntelligence
        model = CustomerIntelligence(date_filter=date_filter)
        return success(model.get_customer_variance())
    except Exception as e:
        return error(str(e))


# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_customer_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")

    if metric == "total_customers":
        frappe.has_permission("Customer", throw=True)
        db_filters = {"disabled": 0}
        rows = frappe.get_list(
            "Customer",
            filters=db_filters,
            fields=["name", "customer_name", "customer_group", "territory", "customer_type"],
            start=start, page_length=page_size, order_by="customer_name asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Customer", "fieldname": "name", "fieldtype": "Link", "options": "Customer"},
                {"label": "Name", "fieldname": "customer_name", "fieldtype": "Data"},
                {"label": "Group", "fieldname": "customer_group", "fieldtype": "Data"},
                {"label": "Territory", "fieldname": "territory", "fieldtype": "Data"},
                {"label": "Type", "fieldname": "customer_type", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Customer", filters=db_filters),
        }

    if metric == "top_customers":
        frappe.has_permission("Sales Invoice", throw=True)
        db_filters = {"docstatus": 1}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "customer", "posting_date", "grand_total", "outstanding_amount"],
            start=start, page_length=page_size, order_by="grand_total desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Invoice", filters=db_filters),
        }

    if metric == "new_customers":
        frappe.has_permission("Customer", throw=True)
        period = f.get("period", "30d")
        days = {"7d": 7, "30d": 30, "90d": 90, "12m": 365}.get(period, 30)
        cutoff = frappe.utils.add_days(frappe.utils.today(), -days)
        db_filters = {"disabled": 0, "creation": (">=", cutoff)}
        rows = frappe.get_list(
            "Customer",
            filters=db_filters,
            fields=["name", "customer_name", "customer_group", "territory", "creation"],
            start=start, page_length=page_size, order_by="creation desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Customer", "fieldname": "name", "fieldtype": "Link", "options": "Customer"},
                {"label": "Name", "fieldname": "customer_name", "fieldtype": "Data"},
                {"label": "Group", "fieldname": "customer_group", "fieldtype": "Data"},
                {"label": "Created", "fieldname": "creation", "fieldtype": "Date"},
            ],
            "rows": rows,
            "total": frappe.db.count("Customer", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)