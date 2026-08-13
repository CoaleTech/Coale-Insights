# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ML Analytics Engine
Combines data collectors with AI analysis for intelligent insights
"""

import frappe
from frappe.utils import now_datetime, cint, flt
from typing import Dict, Any, List, Optional

from insights.ai.provider_factory import AIProviderFactory
from insights.analytics.data_collectors import get_collector


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
            or frappe.db.get_single_value("Global Defaults", "default_currency")
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
        """Get ML model predictions based on dashboard type.

        Every domain below computes fresh (no ``BaseMLModel``/
        ``get_cached_results`` -- that pattern was removed 2026-08-11
        when every ML module was rewritten onto pure Ibis). Each branch
        is independently wrapped so one failing domain does not blank
        the rest of the panel.
        """
        predictions = {
            "available": False,
            "models": {}
        }
        
        try:
            if dashboard_type == "customer":
                # Customer Segmentation (RFM)
                try:
                    from insights.ml.customer import compute_rfm_segmentation

                    company = frappe.defaults.get_user_default("Company") or None
                    result = compute_rfm_segmentation(company=company)
                    if result.get('status') == 'success':
                        predictions["available"] = True
                        segments = {
                            s["segment"]: {**s, "count": s["customer_count"]}
                            for s in result.get('segments', [])
                        }
                        predictions["models"]["customer_segmentation"] = {
                            "status": "ready",
                            "total_customers": result.get('total_customers', 0),
                            "segments": segments,
                            "last_trained": result.get('analysis_date'),
                            "top_segments": list(segments.keys())[:5]
                        }
                    else:
                        predictions["models"]["customer_segmentation"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["customer_segmentation"] = {"status": "error", "error": str(e)}
                    
            elif dashboard_type == "sales":
                # Sales Forecasting
                try:
                    from insights.ml.sales_forecasting import get_sales_forecast

                    result = get_sales_forecast(periods=30)
                    if result.get('status') == 'success':
                        predictions["available"] = True
                        predictions["models"]["sales_forecast"] = {
                            "status": "ready",
                            "method": result.get('method', 'linear_trend'),
                            "forecast_summary": result.get('forecast_summary', {}),
                            "next_30_days": result.get('forecast', [])[:30],
                            "last_trained": result.get('forecast_date')
                        }
                    else:
                        predictions["models"]["sales_forecast"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["sales_forecast"] = {"status": "error", "error": str(e)}
                    
            elif dashboard_type == "financial":
                # Payment Prediction
                try:
                    from insights.ml.payment_prediction import get_payment_predictions

                    result = get_payment_predictions()
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
                    
            elif dashboard_type == "procurement":
                # ABC/XYZ Classification
                try:
                    from insights.ml.inventory_intelligence import run_abc_xyz_classification

                    result = run_abc_xyz_classification()
                    if result.get('status') == 'success':
                        predictions["available"] = True
                        class_distribution = {
                            c["class"]: c["item_count"] for c in result.get('combined_summary', [])
                        }
                        predictions["models"]["abc_xyz_classification"] = {
                            "status": "ready",
                            "total_items": result.get('total_items', 0),
                            "class_distribution": class_distribution,
                            "last_trained": result.get('analysis_date')
                        }
                    else:
                        predictions["models"]["abc_xyz_classification"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["abc_xyz_classification"] = {"status": "error", "error": str(e)}
                
                # Demand Forecasting / reorder alerts
                try:
                    from insights.ml.demand_forecasting import get_demand_forecast

                    result = get_demand_forecast()
                    if result.get('status') == 'success':
                        predictions["available"] = True
                        alerts = [
                            a for a in result.get('reorder_alerts', [])
                            if a.get('status') == 'reorder_now'
                        ]
                        item_names = {}
                        if alerts:
                            item_names = {
                                d.name: d.item_name
                                for d in frappe.get_all(
                                    "Item",
                                    filters={"name": ["in", [a["item_code"] for a in alerts]]},
                                    fields=["name", "item_name"],
                                )
                            }
                        reorder_items = [
                            {**a, "item_name": item_names.get(a["item_code"], a["item_code"])}
                            for a in alerts
                        ]
                        predictions["models"]["reorder_recommendations"] = {
                            "status": "ready",
                            "reorder_now_count": result.get('reorder_now_count', 0),
                            "reorder_items": reorder_items[:15],
                            "last_trained": result.get('forecast_date')
                        }
                    else:
                        predictions["models"]["reorder_recommendations"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["reorder_recommendations"] = {"status": "error", "error": str(e)}
                    
            elif dashboard_type == "production":
                # Demand Forecasting for production planning
                try:
                    from insights.ml.demand_forecasting import get_demand_forecast

                    result = get_demand_forecast()
                    if result.get('status') == 'success':
                        predictions["available"] = True
                        predictions["models"]["production_demand"] = {
                            "status": "ready",
                            "total_items": result.get('total_items_analyzed', 0),
                            "forecasts": result.get('reorder_alerts', [])[:20],
                            "last_trained": result.get('forecast_date')
                        }
                    else:
                        predictions["models"]["production_demand"] = {"status": "not_trained"}
                except Exception as e:
                    predictions["models"]["production_demand"] = {"status": "error", "error": str(e)}
                    
            # Product Recommendations (available for sales, customer dashboards)
            if dashboard_type in ["sales", "customer"]:
                try:
                    from insights.ml.product_recommendations import ProductRecommendations

                    result = ProductRecommendations().train()
                    if result.get('status') == 'success':
                        predictions["available"] = True
                        predictions["models"]["product_recommendations"] = {
                            "status": "ready",
                            "total_rules": result.get('association_rules', {}).get('total_rules', 0),
                            "frequently_bought_together": result.get('frequently_bought_together', [])[:10],
                            "last_trained": result.get('training_date')
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
    """Daily: warm the AI-insight tier behind `get_dashboard`.

    Distinct from `insights.api.ml.utils.refresh_dashboard_caches`, which runs
    hourly and warms the intelligence dashboards' own payload cache. This pass
    fills the CacheManager tier instead -- collector aggregates plus one
    OpenRouter call per dashboard type -- and neither writes the other's keys,
    so the two do not duplicate work. No-op unless AI analytics is enabled.
    """
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

    Synchronous on purpose: both callers are buttons with a spinner
    (`Dashboard.vue` "Refresh with AI", `AIInsights.vue` module tiles), not
    part of the fan-out a dashboard fires on mount, so this does not need the
    background-compute contract in `insights.api.ml.utils`. Measured at ~17s
    per call on the jkm dataset, most of it collector SQL and the model call.

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
        except Exception:
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
        except Exception:
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
        except Exception:
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
