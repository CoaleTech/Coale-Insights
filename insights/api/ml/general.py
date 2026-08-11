# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
General ML API Endpoints
"""

import frappe
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
    """Train/recompute every ML model, inline.

    Every domain below is a pure Ibis rewrite -- one or two SQL
    aggregates materialized as a pandas DataFrame, with no cache to
    warm and nothing to fork. All eight calls typically finish in
    under two seconds combined.
    """
    try:
        frappe.has_permission("Sales Invoice", "write", throw=True)
        from insights.ml.customer import compute_rfm_segmentation, compute_customer_intelligence
        from insights.ml.sales_forecasting import run_sales_forecast
        from insights.ml.payment_prediction import PaymentPrediction
        # Canonical home of these classes: insights.ml.inventory_intelligence
        from insights.ml.inventory_intelligence import (
            ABCXYZClassification,
            DemandForecasting,
        )
        from insights.ml.product_recommendations import ProductRecommendations
        from insights.ml.procurement_intelligence import ProcurementIntelligence

        jobs = [
            ("customer_segmentation", lambda: compute_rfm_segmentation()),
            ("sales_forecast", lambda: run_sales_forecast()),
            ("payment_prediction", lambda: PaymentPrediction().train()),
            ("abc_xyz_classification", lambda: ABCXYZClassification().train()),
            ("demand_forecast", lambda: DemandForecasting().train()),
            ("product_recommendations", lambda: ProductRecommendations().train()),
            ("customer_intelligence", lambda: compute_customer_intelligence(date_filter="12m")),
            ("procurement_intelligence", lambda: ProcurementIntelligence().train()),
        ]

        results = {}
        for name, trainer in jobs:
            try:
                results[name] = trainer()
            except Exception as job_error:
                results[name] = {"status": "error", "message": str(job_error)}
        return success(results)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def payment_risk_analysis(refresh: bool = False) -> Dict[str, Any]:
    """Analyze payment risks.

    ``refresh`` is kept for backward compatibility with older frontend
    callers; the analysis is always computed live, so it has no effect.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.payment_prediction import PaymentPrediction

        return success(PaymentPrediction().predict())
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
    """Generate demand forecast.

    `refresh` is kept for backward compatibility; every call computes
    fresh from MariaDB (no cache, no background job, no fork).
    """
    try:
        frappe.has_permission("Item", "read", throw=True)
        from insights.ml.demand_forecasting import run_demand_forecast

        return success(run_demand_forecast(periods=periods, top_items=top_items))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_reorder_alerts() -> Dict[str, Any]:
    """Get reorder alerts (top-10 slice of the demand forecast)."""
    try:
        frappe.has_permission("Item", "read", throw=True)
        from insights.ml.demand_forecasting import get_reorder_alerts as _get_reorder_alerts

        return success(_get_reorder_alerts())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def product_recommendations(refresh: bool = False) -> Dict[str, Any]:
    """Get product recommendations.

    `refresh` is kept for backward compatibility; every call computes
    fresh (the pair table is a single grouped SQL query, no cache).
    """
    try:
        frappe.has_permission("Item", "read", throw=True)
        from insights.ml.product_recommendations import run_recommendation_training

        return success(run_recommendation_training())
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
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def export_presentation_powerpoint(
    presentation_data: str | dict,
    export_options: str | dict | None = None,
) -> Dict[str, Any]:
    """Export presentation data in PowerPoint-oriented structured form.

    Thin wrapper over ``PresentationModeService.generate_powerpoint_export``,
    which already returns a ``{status, data, message}`` envelope (including
    an honest ``data.download_ready: False`` -- no python-pptx binary is
    generated) -- returned as-is rather than double-wrapped in ``success()``.
    ``export_options`` is accepted for forward compatibility with the
    frontend's export dialog but is not yet applied to the output.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        import json as _json
        from insights.ml.presentation_service import PresentationModeService

        parsed = _json.loads(presentation_data) if isinstance(presentation_data, str) else presentation_data
        return PresentationModeService().generate_powerpoint_export(parsed or {})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def export_presentation_pdf(
    presentation_data: str | dict,
    export_options: str | dict | None = None,
) -> Dict[str, Any]:
    """Export presentation data in PDF-oriented structured form.

    Thin wrapper over ``PresentationModeService.generate_pdf_export``, same
    pass-through-envelope and forward-compatible ``export_options`` note as
    ``export_presentation_powerpoint`` above.
    """
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        import json as _json
        from insights.ml.presentation_service import PresentationModeService

        parsed = _json.loads(presentation_data) if isinstance(presentation_data, str) else presentation_data
        return PresentationModeService().generate_pdf_export(parsed or {})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))