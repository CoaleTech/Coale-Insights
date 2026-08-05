# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ML Analytics Engine
Combines data collectors with AI analysis for intelligent insights
"""

import json
import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime, cint, flt
from typing import Dict, Any, List, Optional

from insights.ai.provider_factory import AIProviderFactory
from insights.ai.openrouter_client import get_ai_status
from insights.analytics.data_collectors import get_collector, get_all_analytics_data


class MLAnalyticsEngine:
    """Main engine for ML-powered analytics"""
    
    DASHBOARD_TYPES = {
        "financial": {
            "title": "Financial Analytics",
            "description": "Revenue, expenses, profit/loss, cash flow analysis",
            "icon": "dollar-sign",
            "color": "#10B981"
        },
        "sales": {
            "title": "Sales Intelligence",
            "description": "Sales performance, customer insights, conversion analysis",
            "icon": "trending-up",
            "color": "#3B82F6"
        },
        "procurement": {
            "title": "Procurement Analytics",
            "description": "Supplier performance, spend analysis, cost optimization",
            "icon": "shopping-cart",
            "color": "#8B5CF6"
        },
        "inventory": {
            "title": "Inventory Insights",
            "description": "Stock levels, turnover, slow-moving analysis",
            "icon": "package",
            "color": "#F59E0B"
        },
        "production": {
            "title": "Production Analytics",
            "description": "Manufacturing efficiency, work order analysis",
            "icon": "settings",
            "color": "#EF4444"
        },
        "customer": {
            "title": "Customer Intelligence",
            "description": "Customer segmentation, retention, lifetime value",
            "icon": "users",
            "color": "#EC4899"
        }
    }
    
    def __init__(self, filters: Optional[Dict] = None):
        self.filters = filters or {}
        self.ai_client = AIProviderFactory.get_client()
        
    def get_dashboard_data(self, dashboard_type: str) -> Dict[str, Any]:
        """
        Get complete dashboard data with AI insights and ML predictions
        
        Args:
            dashboard_type: Type of dashboard (financial, sales, etc.)
            
        Returns:
            Dashboard data with KPIs, charts, AI insights, and ML predictions
        """
        # Get raw data from collector
        collector = get_collector(dashboard_type, self.filters)
        raw_data = collector.collect()
        
        # Calculate KPIs
        kpis = self._calculate_kpis(dashboard_type, raw_data)
        
        # Get AI insights
        ai_insights = self._get_ai_insights(dashboard_type, raw_data)
        
        # Prepare chart data
        charts = self._prepare_charts(dashboard_type, raw_data)
        
        # Get ML predictions based on dashboard type
        ml_predictions = self._get_ml_predictions(dashboard_type)
        
        # Get company default currency
        company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
        base_currency = (
            frappe.db.get_value("Company", company, "default_currency")
            or frappe.db.get_single_value("System Settings", "default_currency")
            or "USD"
        )
        
        return {
            "type": dashboard_type,
            "meta": self.DASHBOARD_TYPES.get(dashboard_type, {}),
            "kpis": kpis,
            "charts": charts,
            "raw_data": raw_data,
            "ai_insights": ai_insights,
            "ml_predictions": ml_predictions,
            "last_updated": now_datetime(),
            "filters": self.filters,
            "base_currency": base_currency
        }
    
    def _calculate_kpis(self, dashboard_type: str, data: Dict) -> List[Dict]:
        """Calculate KPIs based on dashboard type"""
        kpis = []
        
        if dashboard_type == "financial":
            revenue = data.get("revenue", {})
            profit = data.get("profit_loss", {})
            receivables = data.get("receivables", {})
            cash = data.get("cash_flow", {})
            
            kpis = [
                {
                    "label": "Total Revenue",
                    "value": flt(revenue.get("total", 0)),
                    "format": "currency",
                    "change": flt(revenue.get("growth_percent", 0)),
                    "change_type": "percent"
                },
                {
                    "label": "Net Profit",
                    "value": flt(profit.get("net_profit", 0)),
                    "format": "currency",
                    "change": flt(profit.get("profit_margin", 0)),
                    "change_type": "percent",
                    "change_label": "Margin"
                },
                {
                    "label": "Outstanding Receivables",
                    "value": flt(receivables.get("total_outstanding", 0)),
                    "format": "currency",
                    "subtitle": f"{cint(receivables.get('invoice_count', 0))} invoices"
                },
                {
                    "label": "Net Cash Flow",
                    "value": flt(cash.get("net_cash_flow", 0)),
                    "format": "currency"
                }
            ]
            
        elif dashboard_type == "sales":
            summary = data.get("summary", {})
            conversion = data.get("conversion_rate", {})
            
            kpis = [
                {
                    "label": "Total Revenue",
                    "value": flt(summary.get("total_revenue", 0)),
                    "format": "currency"
                },
                {
                    "label": "Total Orders",
                    "value": cint(summary.get("total_orders", 0)),
                    "format": "number"
                },
                {
                    "label": "Avg Order Value",
                    "value": flt(summary.get("avg_order_value", 0)),
                    "format": "currency"
                },
                {
                    "label": "Conversion Rate",
                    "value": flt(conversion.get("conversion_rate", 0)),
                    "format": "percent",
                    "subtitle": f"{cint(conversion.get('converted', 0))}/{cint(conversion.get('total_quotations', 0))} quotes"
                }
            ]
            
        elif dashboard_type == "procurement":
            summary = data.get("summary", {})
            pending = data.get("pending_orders", {})
            
            kpis = [
                {
                    "label": "Total Spend",
                    "value": flt(summary.get("total_spend", 0)),
                    "format": "currency"
                },
                {
                    "label": "Total Orders",
                    "value": cint(summary.get("total_orders", 0)),
                    "format": "number"
                },
                {
                    "label": "Avg Order Value",
                    "value": flt(summary.get("avg_order_value", 0)),
                    "format": "currency"
                },
                {
                    "label": "Pending Orders",
                    "value": cint(pending.get("count", 0)),
                    "format": "number",
                    "subtitle": f"Value: {flt(pending.get('total_value', 0)):,.0f}"
                }
            ]
            
        elif dashboard_type == "inventory":
            summary = data.get("summary", {})
            stock_value = data.get("stock_value", {})
            turnover = data.get("turnover", {})
            low_stock = data.get("low_stock", [])
            
            kpis = [
                {
                    "label": "Stock Value",
                    "value": flt(stock_value.get("total_value", 0)),
                    "format": "currency"
                },
                {
                    "label": "Items in Stock",
                    "value": cint(summary.get("items_in_stock", 0)),
                    "format": "number",
                    "subtitle": f"of {cint(summary.get('total_items', 0))} total"
                },
                {
                    "label": "Turnover Ratio",
                    "value": flt(turnover.get("turnover_ratio", 0)),
                    "format": "decimal",
                    "subtitle": f"{cint(turnover.get('days_to_sell', 0))} days to sell"
                },
                {
                    "label": "Low Stock Items",
                    "value": len(low_stock),
                    "format": "number",
                    "status": "warning" if len(low_stock) > 0 else "success"
                }
            ]
            
        elif dashboard_type == "production":
            summary = data.get("summary", {})
            efficiency = data.get("efficiency", {})
            
            kpis = [
                {
                    "label": "Total Work Orders",
                    "value": cint(summary.get("total_orders", 0)),
                    "format": "number"
                },
                {
                    "label": "Planned Qty",
                    "value": flt(summary.get("planned_qty", 0)),
                    "format": "number"
                },
                {
                    "label": "Produced Qty",
                    "value": flt(summary.get("produced_qty", 0)),
                    "format": "number"
                },
                {
                    "label": "Efficiency",
                    "value": flt(efficiency.get("efficiency_percent", 0)),
                    "format": "percent"
                }
            ]
            
        elif dashboard_type == "customer":
            summary = data.get("summary", {})
            new_customers = data.get("new_customers", {})
            retention = data.get("retention", {})
            
            kpis = [
                {
                    "label": "Total Customers",
                    "value": cint(summary.get("total_customers", 0)),
                    "format": "number"
                },
                {
                    "label": "Active Customers",
                    "value": cint(summary.get("active_customers", 0)),
                    "format": "number"
                },
                {
                    "label": "New Customers",
                    "value": cint(new_customers.get("total_new", 0)),
                    "format": "number"
                },
                {
                    "label": "Retention Rate",
                    "value": flt(retention.get("retention_rate", 0)),
                    "format": "percent",
                    "subtitle": f"Churn: {flt(retention.get('churn_rate', 0))}%"
                }
            ]
        
        return kpis
    
    def _prepare_charts(self, dashboard_type: str, data: Dict) -> List[Dict]:
        """Prepare chart configurations"""
        charts = []
        
        if dashboard_type == "financial":
            # Monthly trend chart
            monthly_trend = data.get("monthly_trend", [])
            if monthly_trend:
                charts.append({
                    "type": "line",
                    "title": "Revenue vs Expenses Trend",
                    "data": {
                        "labels": [r.get("month") for r in monthly_trend],
                        "datasets": [
                            {
                                "label": "Revenue",
                                "data": [flt(r.get("revenue", 0)) for r in monthly_trend],
                                "color": "#10B981"
                            },
                            {
                                "label": "Expenses",
                                "data": [flt(r.get("expense", 0)) for r in monthly_trend],
                                "color": "#EF4444"
                            }
                        ]
                    }
                })
            
            # Receivables aging
            aging = data.get("receivables", {}).get("aging", [])
            if aging:
                charts.append({
                    "type": "bar",
                    "title": "Receivables Aging",
                    "data": {
                        "labels": [r.get("aging_bucket") for r in aging],
                        "datasets": [{
                            "label": "Amount",
                            "data": [flt(r.get("amount", 0)) for r in aging],
                            "color": "#3B82F6"
                        }]
                    }
                })
                
        elif dashboard_type == "sales":
            # Monthly sales trend
            monthly_trend = data.get("monthly_trend", [])
            if monthly_trend:
                charts.append({
                    "type": "bar",
                    "title": "Monthly Sales",
                    "data": {
                        "labels": [r.get("month") for r in monthly_trend],
                        "datasets": [{
                            "label": "Revenue",
                            "data": [flt(r.get("revenue", 0)) for r in monthly_trend],
                            "color": "#3B82F6"
                        }]
                    }
                })
            
            # Top customers pie
            top_customers = data.get("top_customers", [])[:5]
            if top_customers:
                charts.append({
                    "type": "pie",
                    "title": "Top 5 Customers",
                    "data": {
                        "labels": [r.get("customer_name") for r in top_customers],
                        "values": [flt(r.get("total_revenue", 0)) for r in top_customers]
                    }
                })
                
        elif dashboard_type == "inventory":
            # Warehouse distribution
            warehouse_data = data.get("warehouse_wise", [])
            if warehouse_data:
                charts.append({
                    "type": "pie",
                    "title": "Stock Value by Warehouse",
                    "data": {
                        "labels": [r.get("warehouse") for r in warehouse_data],
                        "values": [flt(r.get("total_value", 0)) for r in warehouse_data]
                    }
                })
        
        return charts
    
    def _get_ai_insights(self, dashboard_type: str, data: Dict) -> Dict[str, Any]:
        """Get AI-generated insights for the data"""
        if not self.ai_client.is_enabled():
            return {
                "available": False,
                "message": "AI Analytics is not enabled",
                "insights": None
            }
        
        result = self.ai_client.analyze_data(data, dashboard_type)
        
        return {
            "available": True,
            "insights": result.get("response"),
            "model_used": result.get("model_used"),
            "cached": result.get("cached", False),
            "error": result.get("error")
        }
    
    def _get_ml_predictions(self, dashboard_type: str) -> Dict[str, Any]:
        """Get ML model predictions based on dashboard type"""
        predictions = {
            "available": False,
            "models": {}
        }
        
        try:
            if dashboard_type == "customer":
                # Customer Segmentation (RFM)
                try:
                    from insights.ml.customer_segmentation import CustomerSegmentation
                    model = CustomerSegmentation()
                    cached = model.get_cached_results("customer_segmentation")
                    if cached and cached.get('status') == 'success':
                        predictions["available"] = True
                        predictions["models"]["customer_segmentation"] = {
                            "status": "ready",
                            "total_customers": cached.get('total_customers', 0),
                            "segments": cached.get('segment_summary', {}),
                            "last_trained": cached.get('segmentation_date'),
                            "top_segments": list(cached.get('segment_summary', {}).keys())[:5]
                        }
                    else:
                        predictions["models"]["customer_segmentation"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["customer_segmentation"] = {"status": "error", "error": str(e)}
                    
            elif dashboard_type == "sales":
                # Sales Forecasting
                try:
                    from insights.ml.sales_forecasting import SalesForecasting
                    model = SalesForecasting()
                    cached = model.get_cached_results("sales_forecast")
                    if cached and cached.get('status') == 'success':
                        predictions["available"] = True
                        predictions["models"]["sales_forecast"] = {
                            "status": "ready",
                            "method": cached.get('method', 'unknown'),
                            "forecast_summary": cached.get('forecast_summary', {}),
                            "next_30_days": cached.get('forecast', [])[:30],
                            "last_trained": cached.get('forecast_date')
                        }
                    else:
                        predictions["models"]["sales_forecast"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["sales_forecast"] = {"status": "error", "error": str(e)}
                    
            elif dashboard_type == "financial":
                # Payment Prediction
                try:
                    from insights.ml.payment_prediction import PaymentPrediction
                    model = PaymentPrediction()
                    result = model.predict()
                    if result and result.get('status') == 'success':
                        predictions["available"] = True
                        predictions["models"]["payment_prediction"] = {
                            "status": "ready",
                            "summary": result.get('summary', {}),
                            "high_risk_invoices": [p for p in result.get('predictions', []) if p.get('risk_level') == 'High'][:10],
                            "last_predicted": result.get('prediction_date')
                        }
                    else:
                        predictions["models"]["payment_prediction"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["payment_prediction"] = {"status": "error", "error": str(e)}
                    
            elif dashboard_type == "inventory":
                # ABC/XYZ Classification + Demand Forecasting
                try:
                    from insights.ml.abc_xyz_classification import ABCXYZClassification
                    model = ABCXYZClassification()
                    cached = model.get_cached_results("abc_xyz_classification")
                    if cached and cached.get('status') == 'success':
                        predictions["available"] = True
                        predictions["models"]["abc_xyz_classification"] = {
                            "status": "ready",
                            "total_items": cached.get('total_items', 0),
                            "class_distribution": cached.get('class_distribution', {}),
                            "last_trained": cached.get('classification_date')
                        }
                    else:
                        predictions["models"]["abc_xyz_classification"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["abc_xyz_classification"] = {"status": "error", "error": str(e)}
                
                try:
                    from insights.ml.demand_forecasting import DemandForecasting
                    model = DemandForecasting()
                    cached = model.get_cached_results("demand_forecast")
                    if cached and cached.get('status') == 'success':
                        predictions["available"] = True
                        reorder_items = [f for f in cached.get('forecasts', []) if f.get('stock_status') == 'Reorder Now']
                        predictions["models"]["demand_forecast"] = {
                            "status": "ready",
                            "total_items_analyzed": cached.get('summary', {}).get('total_items_analyzed', 0),
                            "reorder_now_count": len(reorder_items),
                            "reorder_items": reorder_items[:10],
                            "last_trained": cached.get('forecast_date')
                        }
                    else:
                        predictions["models"]["demand_forecast"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["demand_forecast"] = {"status": "error", "error": str(e)}
                    
            elif dashboard_type == "procurement":
                # Demand Forecasting for procurement
                try:
                    from insights.ml.demand_forecasting import DemandForecasting
                    model = DemandForecasting()
                    cached = model.get_cached_results("demand_forecast")
                    if cached and cached.get('status') == 'success':
                        predictions["available"] = True
                        reorder_items = [f for f in cached.get('forecasts', []) if f.get('stock_status') == 'Reorder Now']
                        predictions["models"]["reorder_recommendations"] = {
                            "status": "ready",
                            "reorder_now_count": len(reorder_items),
                            "items": reorder_items[:15],
                            "last_trained": cached.get('forecast_date')
                        }
                    else:
                        predictions["models"]["reorder_recommendations"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["reorder_recommendations"] = {"status": "error", "error": str(e)}
                    
            elif dashboard_type == "production":
                # Demand Forecasting for production planning
                try:
                    from insights.ml.demand_forecasting import DemandForecasting
                    model = DemandForecasting()
                    cached = model.get_cached_results("demand_forecast")
                    if cached and cached.get('status') == 'success':
                        predictions["available"] = True
                        predictions["models"]["production_demand"] = {
                            "status": "ready",
                            "total_items": cached.get('summary', {}).get('total_items_analyzed', 0),
                            "forecasts": cached.get('forecasts', [])[:20],
                            "last_trained": cached.get('forecast_date')
                        }
                    else:
                        predictions["models"]["production_demand"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["production_demand"] = {"status": "error", "error": str(e)}
                    
            # Product Recommendations (available for sales, customer dashboards)
            if dashboard_type in ["sales", "customer"]:
                try:
                    from insights.ml.product_recommendations import ProductRecommendations
                    model = ProductRecommendations()
                    cached = model.get_cached_results("product_recommendations")
                    if cached and cached.get('status') == 'success':
                        predictions["available"] = True
                        predictions["models"]["product_recommendations"] = {
                            "status": "ready",
                            "total_rules": cached.get('association_rules', {}).get('total_rules', 0),
                            "frequently_bought_together": cached.get('frequently_bought_together', [])[:10],
                            "last_trained": cached.get('training_date')
                        }
                    else:
                        predictions["models"]["product_recommendations"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["product_recommendations"] = {"status": "error", "error": str(e)}
                    
        except Exception as e:
            predictions["error"] = str(e)
            frappe.log_error(f"Error getting ML predictions: {str(e)}", "ML Engine")
        
        return predictions
    
    def refresh_all_dashboards(self) -> Dict[str, Any]:
        """Refresh all dashboard data and AI insights"""
        results = {}
        
        for dashboard_type in self.DASHBOARD_TYPES.keys():
            try:
                results[dashboard_type] = self.get_dashboard_data(dashboard_type)
            except Exception as e:
                frappe.log_error(f"Error refreshing {dashboard_type} dashboard: {str(e)}", "ML Analytics")
                results[dashboard_type] = {"error": str(e)}
        
        # Update last refresh time
        frappe.db.set_single_value("Insights Settings", "last_ai_refresh", now_datetime())
        frappe.db.commit()
        
        return results


# Scheduler functions
def refresh_all_dashboards():
    """Scheduled task to refresh all dashboards"""
    settings = frappe.get_single("Insights Settings")
    
    if not settings.enable_ai_analytics:
        return
    
    if settings.refresh_schedule == "Disabled":
        return
    
    engine = MLAnalyticsEngine()
    engine.refresh_all_dashboards()
    
    # Reset daily quota
    from insights.ai.openrouter_client import OpenRouterClient
    client = OpenRouterClient()  # Reset quota uses OpenRouter directly (settings writer)
    client.reset_daily_quota()


def reset_ai_quota():
    """Reset daily AI quota (runs at midnight)"""
    frappe.db.set_single_value("Insights Settings", "ai_quota_used", 0)
    frappe.db.commit()


# API endpoints
@frappe.whitelist()
def get_dashboard(dashboard_type: str, filters: str = None) -> Dict[str, Any]:
    """
    Get dashboard data with AI insights
    
    Args:
        dashboard_type: Type of dashboard
        filters: JSON string of filters
        
    Returns:
        Complete dashboard data
    """
    filter_dict = {}
    if filters:
        try:
            filter_dict = frappe.parse_json(filters)
        except:
            pass
    
    engine = MLAnalyticsEngine(filter_dict)
    return engine.get_dashboard_data(dashboard_type)


@frappe.whitelist()
def get_all_dashboards(filters: str = None) -> Dict[str, Any]:
    """
    Get all dashboard data
    
    Args:
        filters: JSON string of filters
        
    Returns:
        All dashboard data
    """
    filter_dict = {}
    if filters:
        try:
            filter_dict = frappe.parse_json(filters)
        except:
            pass
    
    engine = MLAnalyticsEngine(filter_dict)
    results = {}
    
    for dashboard_type in MLAnalyticsEngine.DASHBOARD_TYPES.keys():
        try:
            results[dashboard_type] = engine.get_dashboard_data(dashboard_type)
        except Exception as e:
            results[dashboard_type] = {"error": str(e)}
    
    return results


@frappe.whitelist()
def refresh_dashboard(dashboard_type: str = None, filters: str = None) -> Dict[str, Any]:
    """
    Refresh dashboard data (bypasses cache)
    
    Args:
        dashboard_type: Type of dashboard (or None for all)
        filters: JSON string of filters
        
    Returns:
        Refreshed dashboard data
    """
    filter_dict = {}
    if filters:
        try:
            filter_dict = frappe.parse_json(filters)
        except:
            pass
    
    engine = MLAnalyticsEngine(filter_dict)
    
    if dashboard_type:
        return engine.get_dashboard_data(dashboard_type)
    else:
        return engine.refresh_all_dashboards()


@frappe.whitelist()
def get_dashboard_types() -> Dict[str, Dict]:
    """Get available dashboard types with metadata"""
    return MLAnalyticsEngine.DASHBOARD_TYPES
