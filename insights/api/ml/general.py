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
        from insights.ml.model_manager import ModelManager

        manager = ModelManager()
        result = manager.get_status()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def run_all_models() -> Dict[str, Any]:
    """Run all ML models"""
    try:
        from insights.ml.model_manager import ModelManager

        manager = ModelManager()
        result = manager.run_all()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def payment_risk_analysis(refresh: bool = False) -> Dict[str, Any]:
    """Analyze payment risks"""
    try:
        from insights.ml.payment_prediction import PaymentPrediction

        model = PaymentPrediction()
        result = model.analyze_risks()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_high_risk_invoices() -> Dict[str, Any]:
    """Get high risk invoices"""
    try:
        from insights.ml.payment_prediction import PaymentPrediction

        model = PaymentPrediction()
        result = model.get_high_risk_invoices()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def demand_forecast(periods: int = 4, top_items: int = 100, refresh: bool = False) -> Dict[str, Any]:
    """Generate demand forecast"""
    try:
        from insights.ml.demand_forecasting import DemandForecasting

        model = DemandForecasting()
        if refresh:
            result = model.train(periods, top_items)
        else:
            result = model.predict()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_reorder_alerts() -> Dict[str, Any]:
    """Get reorder alerts"""
    try:
        from insights.ml.demand_forecasting import DemandForecasting

        model = DemandForecasting()
        result = model.get_reorder_alerts()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def product_recommendations(refresh: bool = False) -> Dict[str, Any]:
    """Get product recommendations"""
    try:
        from insights.ml.recommendation_engine import RecommendationEngine

        model = RecommendationEngine()
        result = model.get_recommendations()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def recommend_for_item(item_code: str) -> Dict[str, Any]:
    """Get recommendations for item"""
    try:
        from insights.ml.recommendation_engine import RecommendationEngine

        model = RecommendationEngine()
        result = model.recommend_for_item(item_code)
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def recommend_for_customer(customer: str) -> Dict[str, Any]:
    """Get recommendations for customer"""
    try:
        from insights.ml.recommendation_engine import RecommendationEngine

        model = RecommendationEngine()
        result = model.recommend_for_customer(customer)
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def recommend_for_cart(items: str) -> Dict[str, Any]:
    """Get recommendations for cart"""
    try:
        from insights.ml.recommendation_engine import RecommendationEngine

        model = RecommendationEngine()
        result = model.recommend_for_cart(items)
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_dashboard_data(dashboard_type: str) -> Dict[str, Any]:
    """Get dashboard data"""
    try:
        from insights.ml.dashboard_analytics import DashboardAnalytics

        model = DashboardAnalytics()
        result = model.get_data(dashboard_type)
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_ml_insights_summary() -> Dict[str, Any]:
    """Get ML insights summary"""
    try:
        from insights.ml.insights_summary import InsightsSummary

        model = InsightsSummary()
        result = model.get_summary()
        return success(result)
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def generate_presentation_data(dashboard_type: str, dashboard_data=None, presentation_type: str = "executive") -> Dict[str, Any]:
    """Generate board-ready presentation data for intelligence dashboards"""
    try:
        import json as _json
        from insights.ml.presentation_service import PresentationModeService

        if isinstance(dashboard_data, str):
            dashboard_data = _json.loads(dashboard_data)

        service = PresentationModeService()
        result = service.generate_presentation_data(dashboard_type, dashboard_data or {}, presentation_type)
        return result
    except Exception as e:
        return {"error": str(e)}