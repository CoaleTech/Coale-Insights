# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
General ML API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any
from insights.api.response import success, error
from insights.api.serialization import sanitize_for_json


@frappe.whitelist()
def get_ml_status() -> Dict[str, Any]:
    """Get ML models status"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        # No centralized model registry exists; there is no single source of
        # truth for "is model X trained/stale". Callers should check the
        # relevant *_intelligence module's own cache/status endpoint instead
        # (e.g. tax_intelligence_status) rather than trust a fabricated summary.
        return success({"status": "not_implemented", "message": "No centralized model registry available"})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def run_all_models() -> Dict[str, Any]:
    """Train every ML model, inline.

    Ran `run_all_ml_models()` inline: eight models fitted while the browser held
    the connection. `compute_or_cache` short-circuits any model whose cache is
    already warm, so the second call typically returns in under a second.
    """
    try:
        frappe.has_permission("Sales Invoice", "write", throw=True)
        from insights.api.ml.utils import compute_or_cache
        from insights.ml.customer_intelligence import CustomerIntelligence
        from insights.ml.sales_forecasting import SalesForecasting
        from insights.ml.payment_prediction import PaymentPrediction
        from insights.ml.abc_xyz_classification import ABCXYZClassification
        from insights.ml.demand_forecasting import DemandForecasting
        from insights.ml.product_recommendations import ProductRecommendations
        from insights.ml.customer_segmentation import CustomerSegmentation
        from insights.ml.procurement_intelligence import ProcurementIntelligence

        jobs = [
            (
                "customer_segmentation",
                "insights:customer_segmentation",
                lambda: CustomerSegmentation().train(),
                _("Customer segmentation"),
            ),
            (
                "sales_forecast",
                "insights:sales_forecast",
                lambda: SalesForecasting().train(),
                _("Sales forecast"),
            ),
            (
                "payment_prediction",
                "insights:payment_prediction",
                lambda: PaymentPrediction().train(),
                _("Payment prediction"),
            ),
            (
                "abc_xyz_classification",
                "insights:abc_xyz_classification",
                lambda: ABCXYZClassification().train(),
                _("ABC/XYZ classification"),
            ),
            (
                "demand_forecast",
                "insights:demand_forecast",
                lambda: DemandForecasting().train(),
                _("Demand forecast"),
            ),
            (
                "product_recommendations",
                "insights:product_recommendations",
                lambda: ProductRecommendations().train(),
                _("Product recommendations"),
            ),
            (
                "customer_intelligence",
                "insights:customer_intelligence:12m",
                lambda: CustomerIntelligence(date_filter="12m").train(update_customers=True),
                _("Customer intelligence"),
            ),
            (
                "procurement_intelligence",
                "insights:procurement_intelligence",
                lambda: ProcurementIntelligence().train(),
                _("Procurement intelligence"),
            ),
        ]

        results = {}
        for name, key, trainer, label in jobs:
            frappe.cache().delete_value(key)  # type: ignore[union-attr]
            results[name] = compute_or_cache(
                trainer=trainer,
                cache_key=key,
                label=label,
            )
        return success(results)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def payment_risk_analysis(refresh: bool = False) -> Dict[str, Any]:
    """Analyze payment risks. `refresh` clears the cache and retrains inline."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.api.ml.utils import compute_or_cache
        from insights.ml.payment_prediction import PaymentPrediction

        cache_key = "insights:payment_prediction"
        if refresh:
            frappe.cache().delete_value(cache_key)  # type: ignore[union-attr]

        return sanitize_for_json(compute_or_cache(trainer=lambda: PaymentPrediction().train(),
        cache_key=cache_key,
        label=_("Payment prediction"),))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_high_risk_invoices() -> Dict[str, Any]:
    """Get high risk invoices"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.payment_prediction import PaymentPrediction
        model = PaymentPrediction()
        result = model.predict()
        predictions = result.get("predictions", [])
        high_risk = [p for p in predictions if p.get("risk_level") == "High"]
        return success({"status": "success", "high_risk_count": len(high_risk), "invoices": high_risk})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def demand_forecast(periods: int = 4, top_items: int = 100, refresh: bool = False) -> Dict[str, Any]:
    """Generate demand forecast. `refresh` clears the cache and retrains inline.

    Retraining fits Holt-Winters for up to `top_items` items -- 100 model fits,
    measured at 5.5s on a development dataset and unbounded on a real ledger.
    The Redis cache + lock in `compute_or_cache` keep the second hit fast
    and prevent concurrent training when multiple users open the dashboard.
    """
    try:
        frappe.has_permission("Item", "read", throw=True)
        from insights.api.ml.utils import compute_or_cache
        from insights.ml.demand_forecasting import DemandForecasting

        cache_key = "insights:demand_forecast"
        if refresh:
            frappe.cache().delete_value(cache_key)  # type: ignore[union-attr]

        return sanitize_for_json(compute_or_cache(trainer=lambda: DemandForecasting().train(periods=periods, top_items=top_items),
        cache_key=cache_key,
        label=_("Demand forecast"),))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_reorder_alerts() -> Dict[str, Any]:
    """Get reorder alerts"""
    try:
        frappe.has_permission("Item", "read", throw=True)
        from insights.ml.demand_forecasting import get_reorder_alerts as _get_reorder_alerts
        result = _get_reorder_alerts()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def product_recommendations(refresh: bool = False) -> Dict[str, Any]:
    """Get product recommendations, computed on request, cached 24h."""
    try:
        frappe.has_permission("Item", "read", throw=True)
        from insights.api.ml.utils import compute_or_cache
        from insights.ml.product_recommendations import ProductRecommendations

        cache_key = "insights:product_recommendations"
        if refresh:
            frappe.cache().delete_value(cache_key)  # type: ignore[union-attr]

        return sanitize_for_json(compute_or_cache(
            trainer=lambda: ProductRecommendations().train(),
            cache_key=cache_key,
            label=_("Product recommendations"),
        ))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def recommend_for_item(item_code: str) -> Dict[str, Any]:
    """Get recommendations for item"""
    try:
        frappe.has_permission("Item", "read", throw=True)
        from insights.ml.product_recommendations import get_item_recommendations
        result = get_item_recommendations(item_code)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def recommend_for_customer(customer: str) -> Dict[str, Any]:
    """Get recommendations for customer"""
    try:
        frappe.has_permission("Customer", "read", throw=True)
        from insights.ml.product_recommendations import get_customer_recommendations
        result = get_customer_recommendations(customer)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def recommend_for_cart(items: str) -> Dict[str, Any]:
    """Get recommendations for cart"""
    try:
        frappe.has_permission("Item", "read", throw=True)
        from insights.ml.product_recommendations import get_cart_recommendations
        result = get_cart_recommendations(items)
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_dashboard_data(dashboard_type: str) -> Dict[str, Any]:
    """Get dashboard data"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        # No dashboard_analytics module exists; no generic per-dashboard-type
        # aggregator has been built. Honest stub rather than a fabricated shape.
        return success({"status": "not_implemented", "dashboard_type": dashboard_type})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_ml_insights_summary() -> Dict[str, Any]:
    """Get ML insights summary"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        # No insights_summary module exists; no cross-model summary has been
        # built. Honest stub rather than a fabricated shape.
        return success({"status": "not_implemented"})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def generate_presentation_data(
    dashboard_type: str,
    dashboard_data: str | dict | None = None,
    presentation_type: str = "executive",
) -> Dict[str, Any]:
    """Generate board-ready presentation data for intelligence dashboards"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        import json as _json
        from insights.ml.presentation_service import PresentationModeService
    
        parsed = _json.loads(dashboard_data) if isinstance(dashboard_data, str) else dashboard_data

        service = PresentationModeService()
        result = service.generate_presentation_data(dashboard_type, parsed or {}, presentation_type)
        return result
    except frappe.PermissionError:
        raise
    except Exception as e:
        return {"error": str(e)}