# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from typing import Dict, Any, List, Optional
import json
import time
from datetime import datetime
from insights.ai_reasoning.model_router import AIModelRouter, TaskComplexity
from insights.cache_management.cache_manager import CacheManager, CacheLevel


class TaskProcessor:
    """Task processor for executing various types of analytics and AI tasks"""
    
    def __init__(self):
        self.model_router = AIModelRouter()
        self.cache_manager = CacheManager()
        
    def process_dashboard_refresh(self, payload: Dict[str, Any], user_id: str) -> Any:
        """Process dashboard widget refresh"""
        
        dashboard_id = payload.get("dashboard_id")
        widget_id = payload.get("widget_id")
        
        try:
            # Try cache first
            cache_key = f"dashboard:{dashboard_id}:widget:{widget_id}"
            cached_data = self.cache_manager.get_cached_data(cache_key)
            
            if cached_data:
                return cached_data
            
            # Execute dashboard query
            from insights.queries.dashboard_queries import DashboardQueries
            query_engine = DashboardQueries()
            
            result = query_engine.get_widget_data(dashboard_id, widget_id)
            
            # Cache for quick access
            self.cache_manager.cache_data(
                cache_key, 
                result, 
                cache_level=CacheLevel.HOT,
                ttl=300  # 5 minutes
            )
            
            return result
            
        except Exception as e:
            frappe.log_error(f"Dashboard refresh failed: {str(e)}")
            raise
    
    def process_simple_query(self, payload: Dict[str, Any], user_id: str) -> Any:
        """Process simple data queries"""
        
        query_config = payload.get("query")
        
        try:
            # Build cache key from query
            cache_key = f"simple_query:{frappe.utils.md5(json.dumps(query_config, sort_keys=True))}"
            
            # Check cache
            cached_result = self.cache_manager.get_cached_data(cache_key)
            if cached_result:
                return cached_result
            
            # Execute query
            from insights.queries.query_engine import QueryEngine
            engine = QueryEngine()
            
            result = engine.execute_simple_query(query_config)
            
            # Cache result
            self.cache_manager.cache_data(
                cache_key,
                result,
                cache_level=CacheLevel.WARM,
                ttl=600  # 10 minutes
            )
            
            return result
            
        except Exception as e:
            frappe.log_error(f"Simple query failed: {str(e)}")
            raise
    
    def process_user_question(self, payload: Dict[str, Any], user_id: str) -> Any:
        """Process natural language questions using AI"""
        
        question = payload.get("question")
        context = payload.get("context", {})
        
        try:
            # Determine question complexity
            complexity = self._analyze_question_complexity(question)
            
            # Build enhanced context
            enhanced_context = self._build_question_context(question, context, user_id)
            
            # Route to appropriate AI model
            response = self.model_router.route_task(
                task_type="natural_language_query",
                complexity=complexity,
                payload={
                    "question": question,
                    "context": enhanced_context,
                    "user_id": user_id
                }
            )
            
            return {
                "answer": response.get("answer"),
                "confidence": response.get("confidence", 0.8),
                "sources": response.get("sources", []),
                "processing_time": response.get("processing_time", 0)
            }
            
        except Exception as e:
            frappe.log_error(f"User question processing failed: {str(e)}")
            raise
    
    def process_sales_alert(self, payload: Dict[str, Any], user_id: str) -> Any:
        """Process sales-related alerts"""
        
        alert_type = payload.get("alert_type")
        
        try:
            if alert_type == "order_threshold":
                return self._process_sales_order_alert(payload)
            elif alert_type == "revenue_drop":
                return self._process_revenue_alert(payload)
            elif alert_type == "customer_risk":
                return self._process_customer_risk_alert(payload)
            else:
                return self._process_generic_sales_alert(payload)
                
        except Exception as e:
            frappe.log_error(f"Sales alert processing failed: {str(e)}")
            raise
    
    def process_inventory_alert(self, payload: Dict[str, Any], user_id: str) -> Any:
        """Process inventory-related alerts"""
        
        alert_type = payload.get("alert_type")
        
        try:
            if alert_type == "stock_shortage":
                return self._process_stock_shortage_alert(payload)
            elif alert_type == "reorder_point":
                return self._process_reorder_alert(payload)
            elif alert_type == "excess_stock":
                return self._process_excess_stock_alert(payload)
            else:
                return self._process_generic_inventory_alert(payload)
                
        except Exception as e:
            frappe.log_error(f"Inventory alert processing failed: {str(e)}")
            raise
    
    def process_customer_insight(self, payload: Dict[str, Any], user_id: str) -> Any:
        """Process customer insight requests"""
        
        customer_id = payload.get("customer_id")
        insight_type = payload.get("insight_type", "general")
        
        try:
            # Get customer data from ERPNext
            customer_data = self._get_customer_data(customer_id)
            
            # Analyze customer patterns using AI
            insight_request = {
                "customer_data": customer_data,
                "insight_type": insight_type,
                "analysis_period": payload.get("period", "last_6_months")
            }
            
            # Route to AI for analysis
            response = self.model_router.route_task(
                task_type="customer_analysis",
                complexity=TaskComplexity.MEDIUM,
                payload=insight_request
            )
            
            return {
                "customer_id": customer_id,
                "insights": response.get("insights"),
                "recommendations": response.get("recommendations"),
                "risk_score": response.get("risk_score"),
                "growth_potential": response.get("growth_potential")
            }
            
        except Exception as e:
            frappe.log_error(f"Customer insight processing failed: {str(e)}")
            raise
    
    def process_medium_query(self, payload: Dict[str, Any], user_id: str) -> Any:
        """Process medium complexity queries"""
        
        query_config = payload.get("query")
        
        try:
            # Build cache key
            cache_key = f"medium_query:{frappe.utils.md5(json.dumps(query_config, sort_keys=True))}"
            
            # Check cache
            cached_result = self.cache_manager.get_cached_data(cache_key)
            if cached_result:
                return cached_result
            
            # Execute complex query
            from insights.queries.query_engine import QueryEngine
            engine = QueryEngine()
            
            result = engine.execute_complex_query(query_config)
            
            # Cache with longer TTL
            self.cache_manager.cache_data(
                cache_key,
                result,
                cache_level=CacheLevel.WARM,
                ttl=1800  # 30 minutes
            )
            
            return result
            
        except Exception as e:
            frappe.log_error(f"Medium query failed: {str(e)}")
            raise
    
    def process_chart_generation(self, payload: Dict[str, Any], user_id: str) -> Any:
        """Process chart and visualization generation"""
        
        chart_config = payload.get("chart_config")
        data_source = payload.get("data_source")
        
        try:
            # Generate chart data
            from insights.visualizations.chart_generator import ChartGenerator
            generator = ChartGenerator()
            
            result = generator.generate_chart(chart_config, data_source)
            
            return {
                "chart_data": result.get("chart_data"),
                "chart_options": result.get("chart_options"),
                "metadata": result.get("metadata")
            }
            
        except Exception as e:
            frappe.log_error(f"Chart generation failed: {str(e)}")
            raise
    
    def process_sales_forecast(self, payload: Dict[str, Any], user_id: str) -> Any:
        """Process sales forecasting (batch operation)"""
        
        forecast_config = payload.get("forecast_config")
        
        try:
            # Get historical sales data
            sales_data = self._get_historical_sales_data(forecast_config)
            
            # Use AI for forecasting
            forecast_request = {
                "historical_data": sales_data,
                "forecast_period": forecast_config.get("period", 90),
                "confidence_level": forecast_config.get("confidence", 0.95)
            }
            
            response = self.model_router.route_task(
                task_type="sales_forecasting",
                complexity=TaskComplexity.COMPLEX,
                payload=forecast_request
            )
            
            return {
                "forecast_data": response.get("forecast"),
                "confidence_intervals": response.get("confidence_intervals"),
                "key_factors": response.get("factors"),
                "accuracy_metrics": response.get("accuracy")
            }
            
        except Exception as e:
            frappe.log_error(f"Sales forecast failed: {str(e)}")
            raise
    
    def process_customer_segmentation(self, payload: Dict[str, Any], user_id: str) -> Any:
        """Process customer segmentation analysis"""
        
        segmentation_config = payload.get("segmentation_config")
        
        try:
            # Get customer data for segmentation
            customer_data = self._get_customer_segmentation_data(segmentation_config)
            
            # Use AI for segmentation
            segmentation_request = {
                "customer_data": customer_data,
                "segmentation_criteria": segmentation_config.get("criteria"),
                "number_of_segments": segmentation_config.get("segments", 5)
            }
            
            response = self.model_router.route_task(
                task_type="customer_segmentation",
                complexity=TaskComplexity.COMPLEX,
                payload=segmentation_request
            )
            
            return {
                "segments": response.get("segments"),
                "segment_characteristics": response.get("characteristics"),
                "recommendations": response.get("recommendations")
            }
            
        except Exception as e:
            frappe.log_error(f"Customer segmentation failed: {str(e)}")
            raise
    
    def process_trend_analysis(self, payload: Dict[str, Any], user_id: str) -> Any:
        """Process multi-period trend analysis"""
        
        analysis_config = payload.get("analysis_config")
        
        try:
            # Get trend data
            trend_data = self._get_trend_data(analysis_config)
            
            # Use AI for trend analysis
            trend_request = {
                "time_series_data": trend_data,
                "analysis_type": analysis_config.get("type", "comprehensive"),
                "detect_seasonality": analysis_config.get("seasonality", True)
            }
            
            response = self.model_router.route_task(
                task_type="trend_analysis",
                complexity=TaskComplexity.COMPLEX,
                payload=trend_request
            )
            
            return {
                "trends": response.get("trends"),
                "patterns": response.get("patterns"),
                "predictions": response.get("predictions"),
                "insights": response.get("insights")
            }
            
        except Exception as e:
            frappe.log_error(f"Trend analysis failed: {str(e)}")
            raise
    
    def process_generic(self, task_type: str, payload: Dict[str, Any], user_id: str) -> Any:
        """Generic processor for unknown task types"""
        
        try:
            # Determine complexity based on payload size and structure
            complexity = self._determine_generic_complexity(payload)
            
            # Route to AI with generic processing
            response = self.model_router.route_task(
                task_type="generic_processing",
                complexity=complexity,
                payload={
                    "task_type": task_type,
                    "payload": payload,
                    "user_id": user_id
                }
            )
            
            return response
            
        except Exception as e:
            frappe.log_error(f"Generic processing failed: {str(e)}")
            raise
    
    # Helper methods
    
    def _analyze_question_complexity(self, question: str) -> TaskComplexity:
        """Analyze complexity of natural language question"""
        
        # Simple heuristics for complexity detection
        question_lower = question.lower()
        
        # Complex indicators
        complex_keywords = ["compare", "analyze", "predict", "forecast", "correlation", "trend"]
        medium_keywords = ["calculate", "sum", "average", "count", "group"]
        
        if any(keyword in question_lower for keyword in complex_keywords):
            return TaskComplexity.COMPLEX
        elif any(keyword in question_lower for keyword in medium_keywords):
            return TaskComplexity.MEDIUM
        else:
            return TaskComplexity.SIMPLE
    
    def _build_question_context(self, question: str, context: Dict, user_id: str) -> Dict[str, Any]:
        """Build enhanced context for question answering"""
        
        enhanced_context = {
            "question": question,
            "user_context": context,
            "user_id": user_id,
            "company": frappe.defaults.get_user_default("Company", user_id),
            "fiscal_year": frappe.defaults.get_user_default("fiscal_year"),
            "available_data": self._get_available_data_summary(),
            "user_permissions": self._get_user_permissions(user_id)
        }
        
        return enhanced_context
    
    def _get_customer_data(self, customer_id: str) -> Dict[str, Any]:
        """Get comprehensive customer data from ERPNext"""
        
        try:
            # Customer basic info
            customer = frappe.get_doc("Customer", customer_id)
            
            # Sales data
            sales_invoices = frappe.get_all(
                "Sales Invoice",
                filters={"customer": customer_id, "docstatus": 1},
                fields=["name", "posting_date", "grand_total", "outstanding_amount"],
                order_by="posting_date desc",
                limit=50
            )
            
            # Sales orders
            sales_orders = frappe.get_all(
                "Sales Order",
                filters={"customer": customer_id, "docstatus": 1},
                fields=["name", "transaction_date", "grand_total", "delivery_status"],
                order_by="transaction_date desc",
                limit=20
            )

            return {
                "customer_info": customer.as_dict(),
                "sales_invoices": sales_invoices,
                "sales_orders": sales_orders,
                "total_revenue": sum(inv.get("grand_total", 0) for inv in sales_invoices),
                "outstanding_amount": sum(inv.get("outstanding_amount", 0) for inv in sales_invoices)
            }

        except Exception as e:
            frappe.log_error(f"Failed to get customer data: {str(e)}")
            return {}

    def _get_available_data_summary(self) -> Dict[str, Any]:
        """Get summary of available data for context.

        Uses sequential COUNT queries via the ORM so no raw SQL is needed.
        """

        try:
            doctypes_to_check = [
                "Sales Invoice", "Sales Order", "Purchase Order", "Purchase Invoice",
                "Item", "Customer", "Supplier", "Stock Entry", "Delivery Note"
            ]

            summary = {}
            for dt in doctypes_to_check:
                key = dt.lower().replace(" ", "_")
                summary[key] = frappe.db.count(dt, {"docstatus": 1})

            return summary

        except Exception as e:
            return {}
    
    def _get_user_permissions(self, user_id: str) -> List[str]:
        """Get user permissions for data access"""
        
        try:
            user_roles = frappe.get_roles(user_id)
            return user_roles
        except:
            return ["Guest"]
    
    def _process_sales_order_alert(self, payload: Dict) -> Dict[str, Any]:
        """Process sales order threshold alerts"""
        
        threshold = payload.get("threshold", 100000)
        
        # Get recent large orders
        large_orders = frappe.get_all(
            "Sales Order",
            filters={
                "grand_total": [">", threshold],
                "transaction_date": [">=", frappe.utils.add_days(frappe.utils.today(), -7)],
                "docstatus": 1
            },
            fields=["name", "customer", "grand_total", "transaction_date"]
        )
        
        return {
            "alert_type": "large_sales_orders",
            "orders": large_orders,
            "count": len(large_orders),
            "total_value": sum(order.get("grand_total", 0) for order in large_orders)
        }
    
    def _process_revenue_alert(self, payload: Dict) -> Dict[str, Any]:
        """Process revenue drop alerts"""
        
        # Compare current period vs previous period
        current_revenue = self._get_period_revenue("current")
        previous_revenue = self._get_period_revenue("previous")
        
        drop_percentage = ((previous_revenue - current_revenue) / previous_revenue * 100) if previous_revenue > 0 else 0
        
        return {
            "alert_type": "revenue_drop",
            "current_revenue": current_revenue,
            "previous_revenue": previous_revenue,
            "drop_percentage": drop_percentage,
            "is_significant": drop_percentage > 10
        }

    def _process_customer_risk_alert(self, payload: Dict) -> Dict[str, Any]:
        """Process customer risk alerts"""

        SI = frappe.qb.DocType("Sales Invoice")
        threshold = payload.get("risk_threshold", 50000)
        outstanding_sum = Sum(SI.outstanding_amount).as_("outstanding")
        high_risk_customers = (
            frappe.qb.from_(SI)
            .select(SI.customer, outstanding_sum)
            .where((SI.docstatus == 1) & (SI.outstanding_amount > 0))
            .groupby(SI.customer)
            .having(outstanding_sum > threshold)
            .orderby(outstanding_sum, order=frappe.qb.desc)
            .run(as_dict=True)
        )

        return {
            "alert_type": "customer_risk",
            "high_risk_customers": high_risk_customers,
            "total_outstanding": sum(c.get("outstanding", 0) for c in high_risk_customers)
        }

    def _get_period_revenue(self, period: str) -> float:
        """Get revenue for specified period"""

        if period == "current":
            start_date = frappe.utils.get_first_day_of_week(frappe.utils.today())
            end_date = frappe.utils.today()
        else:  # previous
            start_date = frappe.utils.add_days(frappe.utils.get_first_day_of_week(frappe.utils.today()), -7)
            end_date = frappe.utils.add_days(frappe.utils.get_first_day_of_week(frappe.utils.today()), -1)

        SI = frappe.qb.DocType("Sales Invoice")
        result = (
            frappe.qb.from_(SI)
            .select(Sum(SI.grand_total).as_("revenue"))
            .where(
                (SI.posting_date.between(start_date, end_date))
                & (SI.docstatus == 1)
            )
            .run(as_dict=True)
        )
        revenue = result[0].get("revenue") or 0 if result else 0

        return float(revenue)
    
    def _determine_generic_complexity(self, payload: Dict) -> TaskComplexity:
        """Determine complexity for generic tasks"""
        
        # Simple heuristics based on payload structure
        payload_str = json.dumps(payload)
        
        if len(payload_str) > 5000 or len(payload.keys()) > 10:
            return TaskComplexity.COMPLEX
        elif len(payload_str) > 1000 or len(payload.keys()) > 5:
            return TaskComplexity.MEDIUM
        else:
            return TaskComplexity.SIMPLE