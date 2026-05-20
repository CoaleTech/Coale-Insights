# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Customer Intelligence API Endpoints
"""

import frappe
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