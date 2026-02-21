# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
import json
from typing import Dict, Any, List
from insights.ai_reasoning.model_router import AIModelRouter, TaskRequest, TaskComplexity
from insights.cache_management.cache_manager import CacheManager
from insights.processing.processing_pipeline import ProcessingPipeline, ProcessingMode, Priority
from insights.integrations.erpnext_v15_integrator import ERPNextV15Integrator


@frappe.whitelist()
def get_ai_insights(query: str, context: str = None, complexity: str = "simple") -> Dict[str, Any]:
    """
    Get AI-powered insights for a natural language query
    
    Args:
        query: Natural language question
        context: Optional context (doctype, filters, etc.)
        complexity: Task complexity (simple, medium, complex)
    
    Returns:
        Dict with AI response, processing time, and metadata
    """
    
    try:
        # Validate user permissions
        if not frappe.has_permission("Insights AI Query", "create"):
            frappe.throw(_("You don't have permission to use AI features"))
        
        # Initialize components
        model_router = AIModelRouter()
        cache_manager = CacheManager()
        pipeline = ProcessingPipeline()
        
        # Parse complexity
        task_complexity = TaskComplexity(complexity.lower())
        
        # Check cache first
        cache_key = f"ai_query:{frappe.session.user}:{hash(query + (context or ''))}"
        cached_result = cache_manager.get(cache_key)
        
        if cached_result:
            return {
                "success": True,
                "response": cached_result,
                "cached": True,
                "processing_time": 0
            }
        
        # Create task request
        task_request = TaskRequest(
            query=query,
            complexity=task_complexity,
            context=json.loads(context) if context else {},
            user_id=frappe.session.user
        )
        
        # Process through AI router
        start_time = frappe.utils.now()
        result = model_router.process_task(task_request)
        processing_time = frappe.utils.time_diff_in_seconds(frappe.utils.now(), start_time)
        
        # Cache result if successful
        if result.get("success"):
            cache_manager.set(cache_key, result, ttl=3600)  # Cache for 1 hour
        
        return {
            "success": True,
            "response": result,
            "cached": False,
            "processing_time": processing_time,
            "model_used": result.get("model_used"),
            "tokens_used": result.get("tokens_used")
        }
        
    except Exception as e:
        frappe.log_error(f"AI Insights Error: {str(e)}", "AI Insights")
        return {
            "success": False,
            "error": str(e),
            "processing_time": 0
        }


@frappe.whitelist()
def get_business_intelligence_insights(module: str, doctype: str = None, filters: str = None) -> Dict[str, Any]:
    """
    Get business intelligence insights for specific ERPNext modules
    
    Args:
        module: ERPNext module (accounts, selling, buying, etc.)
        doctype: Specific doctype (optional)
        filters: JSON string of filters (optional)
    
    Returns:
        Dict with business intelligence insights
    """
    
    try:
        # Validate permissions
        if not frappe.has_permission("Insights Dashboard v3", "read"):
            frappe.throw(_("You don't have permission to view insights"))
        
        # Initialize ERPNext integrator
        integrator = ERPNextV15Integrator()
        
        # Parse filters
        filter_dict = json.loads(filters) if filters else {}
        
        # Generate insights based on module
        if module.lower() == "accounts":
            insights = integrator.get_financial_insights(filter_dict)
        elif module.lower() == "selling":
            insights = integrator.get_sales_insights(filter_dict)
        elif module.lower() == "buying":
            insights = integrator.get_procurement_insights(filter_dict)
        elif module.lower() == "stock":
            insights = integrator.get_inventory_insights(filter_dict)
        elif module.lower() == "projects":
            insights = integrator.get_project_insights(filter_dict)
        elif module.lower() == "crm":
            insights = integrator.get_crm_insights(filter_dict)
        elif module.lower() == "hr":
            insights = integrator.get_hr_insights(filter_dict)
        else:
            insights = integrator.get_general_insights(module, filter_dict)
        
        return {
            "success": True,
            "module": module,
            "insights": insights,
            "generated_at": frappe.utils.now(),
            "data_points": len(insights.get("data", []))
        }
        
    except Exception as e:
        frappe.log_error(f"BI Insights Error: {str(e)}", "Business Intelligence")
        return {
            "success": False,
            "error": str(e),
            "module": module
        }


@frappe.whitelist()
def get_realtime_dashboard_data(dashboard_id: str, widgets: str = None) -> Dict[str, Any]:
    """
    Get real-time data for dashboard widgets
    
    Args:
        dashboard_id: Dashboard identifier
        widgets: JSON string of widget configurations
    
    Returns:
        Dict with real-time widget data
    """
    
    try:
        # Validate permissions
        if not frappe.has_permission("Insights Dashboard v3", "read"):
            frappe.throw(_("You don't have permission to view dashboards"))
        
        # Initialize components
        cache_manager = CacheManager()
        pipeline = ProcessingPipeline()
        
        # Parse widget configurations
        widget_configs = json.loads(widgets) if widgets else []
        
        dashboard_data = {}
        
        for widget in widget_configs:
            widget_id = widget.get("id")
            widget_type = widget.get("type", "chart")
            
            # Check cache for widget data
            cache_key = f"widget:{dashboard_id}:{widget_id}"
            cached_data = cache_manager.get(cache_key)
            
            if cached_data:
                dashboard_data[widget_id] = cached_data
                continue
            
            # Generate widget data based on type
            if widget_type == "kpi":
                widget_data = _get_kpi_widget_data(widget)
            elif widget_type == "chart":
                widget_data = _get_chart_widget_data(widget)
            elif widget_type == "table":
                widget_data = _get_table_widget_data(widget)
            else:
                widget_data = {"error": f"Unknown widget type: {widget_type}"}
            
            # Cache widget data
            if not widget_data.get("error"):
                cache_manager.set(cache_key, widget_data, ttl=300)  # Cache for 5 minutes
            
            dashboard_data[widget_id] = widget_data
        
        return {
            "success": True,
            "dashboard_id": dashboard_id,
            "data": dashboard_data,
            "updated_at": frappe.utils.now()
        }
        
    except Exception as e:
        frappe.log_error(f"Dashboard Data Error: {str(e)}", "Real-time Dashboard")
        return {
            "success": False,
            "error": str(e),
            "dashboard_id": dashboard_id
        }


@frappe.whitelist()
def get_ai_model_status() -> Dict[str, Any]:
    """
    Get current AI model status and usage statistics
    
    Returns:
        Dict with model status, quotas, and performance metrics
    """
    
    try:
        # Check admin permissions
        if "System Manager" not in frappe.get_roles():
            frappe.throw(_("You don't have permission to view AI model status"))
        
        # Initialize model router
        model_router = AIModelRouter()
        
        # Get model status
        status = model_router.get_model_status()
        
        return {
            "success": True,
            "status": status,
            "updated_at": frappe.utils.now()
        }
        
    except Exception as e:
        frappe.log_error(f"AI Model Status Error: {str(e)}", "AI Model Status")
        return {
            "success": False,
            "error": str(e)
        }


def _get_kpi_widget_data(widget_config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate KPI widget data"""
    try:
        # Implementation for KPI widget data generation
        return {
            "type": "kpi",
            "value": 0,
            "change": 0,
            "trend": "up"
        }
    except Exception as e:
        return {"error": str(e)}


def _get_chart_widget_data(widget_config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate chart widget data"""
    try:
        # Implementation for chart widget data generation
        return {
            "type": "chart",
            "data": [],
            "labels": []
        }
    except Exception as e:
        return {"error": str(e)}


def _get_table_widget_data(widget_config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate table widget data"""
    try:
        # Implementation for table widget data generation
        return {
            "type": "table",
            "columns": [],
            "rows": []
        }
    except Exception as e:
        return {"error": str(e)}


@frappe.whitelist()
def refresh_dashboard_analytics(dashboard_type: str, filters: str = None) -> Dict[str, Any]:
    """
    Refresh ML analytics for a specific dashboard type
    
    Args:
        dashboard_type: Type of dashboard (financial, sales, procurement, inventory, production, customer)
        filters: JSON string of filters
    
    Returns:
        Dict with refreshed analytics data and AI insights
    """
    try:
        from insights.analytics.ml_engine import MLAnalyticsEngine
        
        filter_dict = json.loads(filters) if filters else {}
        engine = MLAnalyticsEngine(filter_dict)
        
        result = engine.get_dashboard_data(dashboard_type)
        
        return {
            "success": True,
            "dashboard_type": dashboard_type,
            "data": result,
            "refreshed_at": frappe.utils.now()
        }
        
    except Exception as e:
        frappe.log_error(f"Dashboard Analytics Refresh Error: {str(e)}", "ML Analytics")
        return {
            "success": False,
            "error": str(e),
            "dashboard_type": dashboard_type
        }


@frappe.whitelist()
def get_dashboard_context(dashboard_type: str = None) -> Dict[str, Any]:
    """
    Get dashboard context for AI chat conversations
    
    Args:
        dashboard_type: Optional specific dashboard type, or None for all
    
    Returns:
        Dict with aggregated context data for AI chat
    """
    try:
        from insights.analytics.data_collectors import get_all_analytics_data, get_collector
        from insights.analytics.ml_engine import MLAnalyticsEngine
        
        context = {
            "company": frappe.defaults.get_user_default("Company"),
            "user": frappe.session.user,
            "timestamp": frappe.utils.now()
        }
        
        if dashboard_type:
            # Get specific dashboard data
            collector = get_collector(dashboard_type)
            context["data"] = collector.collect()
            context["dashboard_type"] = dashboard_type
        else:
            # Get summary from all dashboards
            context["data"] = get_all_analytics_data()
            context["dashboard_type"] = "all"
        
        # Add KPI summary
        engine = MLAnalyticsEngine()
        context["available_dashboards"] = list(engine.DASHBOARD_TYPES.keys())
        
        return {
            "success": True,
            "context": context
        }
        
    except Exception as e:
        frappe.log_error(f"Dashboard Context Error: {str(e)}", "AI Chat Context")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def get_cached_insights(dashboard_type: str, include_stale: bool = True) -> Dict[str, Any]:
    """
    Get cached AI insights with stale data indicator
    
    Args:
        dashboard_type: Type of dashboard
        include_stale: Whether to return stale cached data if fresh not available
    
    Returns:
        Dict with cached insights, staleness indicator, and cache age
    """
    try:
        cache_key = f"ai_dashboard_insights:{dashboard_type}"
        cached_data = frappe.cache.get_value(cache_key)
        
        if cached_data:
            # Calculate cache age
            cached_at = cached_data.get("cached_at")
            if cached_at:
                from frappe.utils import time_diff_in_hours, get_datetime
                cache_age_hours = time_diff_in_hours(frappe.utils.now(), cached_at)
                is_stale = cache_age_hours > 24  # Stale after 24 hours
            else:
                cache_age_hours = 0
                is_stale = False
            
            return {
                "success": True,
                "insights": cached_data.get("insights"),
                "cached": True,
                "is_stale": is_stale,
                "cache_age_hours": round(cache_age_hours, 1),
                "cached_at": cached_at,
                "model_used": cached_data.get("model_used")
            }
        
        # No cached data - optionally trigger refresh
        if include_stale:
            # Return empty with indicator to fetch fresh
            return {
                "success": True,
                "insights": None,
                "cached": False,
                "is_stale": True,
                "cache_age_hours": None,
                "cached_at": None,
                "message": "No cached data available. Please refresh."
            }
        
        return {
            "success": False,
            "error": "No cached insights available",
            "cached": False
        }
        
    except Exception as e:
        frappe.log_error(f"Cached Insights Error: {str(e)}", "AI Cache")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def cache_dashboard_insights(dashboard_type: str, insights: str, model_used: str = None) -> Dict[str, Any]:
    """
    Cache AI-generated insights for a dashboard
    
    Args:
        dashboard_type: Type of dashboard
        insights: JSON string of insights to cache
        model_used: AI model that generated the insights
    
    Returns:
        Dict with cache confirmation
    """
    try:
        cache_key = f"ai_dashboard_insights:{dashboard_type}"
        
        insights_data = json.loads(insights) if isinstance(insights, str) else insights
        
        cache_data = {
            "insights": insights_data,
            "cached_at": frappe.utils.now(),
            "model_used": model_used,
            "cached_by": frappe.session.user
        }
        
        # Cache for 24 hours
        frappe.cache.set_value(cache_key, cache_data, expires_in_sec=86400)
        
        return {
            "success": True,
            "message": f"Insights cached for {dashboard_type}",
            "cached_at": cache_data["cached_at"]
        }
        
    except Exception as e:
        frappe.log_error(f"Cache Insights Error: {str(e)}", "AI Cache")
        return {
            "success": False,
            "error": str(e)
        }