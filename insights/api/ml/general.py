# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
General ML API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any
from insights.api.response import success, error


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
    """Train every ML model, on a worker.

    Ran `run_all_ml_models()` inline: eight models fitted while the browser held
    the connection. Guaranteed to outlive any gateway read timeout.
    """
    try:
        frappe.has_permission("Sales Invoice", "write", throw=True)
        from insights.api.ml.utils import enqueue_training

        return enqueue_training(
            "insights.ml.scheduler.run_all_ml_models",
            job_id="insights_train_all_models",
            label=_("All ML models"),
        )
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def payment_risk_analysis(refresh: bool = False) -> Dict[str, Any]:
    """Analyze payment risks. `refresh` retrains on a worker."""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.payment_prediction import PaymentPrediction

        if refresh:
            from insights.api.ml.utils import enqueue_training

            return enqueue_training(
                "insights.ml.scheduler.train_payment_prediction",
                job_id="insights_train_payment_prediction",
                label=_("Payment prediction"),
            )

        result = PaymentPrediction().predict()
        return success(result)
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
    """Generate demand forecast. `refresh` retrains on a worker.

    Retraining fits Holt-Winters for up to `top_items` items -- 100 model fits,
    measured at 5.5s on a development dataset and unbounded on a real ledger.
    """
    try:
        frappe.has_permission("Item", "read", throw=True)
        from insights.ml.demand_forecasting import DemandForecasting

        if refresh:
            from insights.api.ml.utils import enqueue_training

            return enqueue_training(
                "insights.ml.scheduler.train_demand_forecast",
                job_id="insights_train_demand_forecast",
                label=_("Demand forecast"),
            )

        return success(DemandForecasting().predict())
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
    """Get product recommendations"""
    try:
        frappe.has_permission("Item", "read", throw=True)
        from insights.ml.product_recommendations import ProductRecommendations
        model = ProductRecommendations()
        if refresh:
            result = model.train()
        else:
            cached = model.get_cached_results("product_recommendations")
            result = cached if cached else model.train()
        return success(result)
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