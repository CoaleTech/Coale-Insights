"""
Advanced Predictive Analytics Agent

Intelligent agent for handling predictive analytics queries and providing insights.
Provides conversational interface for forecasting, anomaly detection, and predictive intelligence.

Features:
- Natural language query processing for predictive analytics
- Intelligent forecasting assistance and interpretation
- Anomaly detection and risk assessment guidance
- Pattern recognition and trend analysis
- Predictive recommendations and strategic insights
- Model performance monitoring and optimization suggestions

Author: AI Assistant
Version: 1.0.0
"""

import frappe
from typing import Dict, List, Any, Optional
import json
import logging
from datetime import datetime, timedelta
import re

# Import our predictive analytics service
from insights.ml.advanced_predictive_analytics import advanced_predictive_engine

logger = logging.getLogger(__name__)

class AdvancedPredictiveAnalyticsAgent:
    """
    Intelligent agent for advanced predictive analytics
    
    Handles natural language queries for forecasting, anomaly detection,
    pattern analysis, and provides strategic predictive insights.
    """
    
    def __init__(self):
        self.agent_name = "Advanced Predictive Analytics Agent"
        self.agent_type = "predictive_analytics"
        self.analytics_engine = advanced_predictive_engine
        
        # Query classification patterns
        self.query_patterns = {
            "forecasting": [
                "forecast", "predict", "projection", "future", "trend", "what will",
                "expected", "outlook", "anticipated", "estimate", "next quarter",
                "next month", "next year"
            ],
            "anomaly_detection": [
                "anomaly", "anomalies", "unusual", "abnormal", "outlier", "strange",
                "unexpected", "irregular", "suspicious", "risk", "problem", "issue"
            ],
            "pattern_analysis": [
                "pattern", "patterns", "correlation", "relationship", "seasonal",
                "cyclical", "trends", "behavior", "recurring", "regular", "systematic"
            ],
            "real_time": [
                "now", "current", "today", "latest", "real-time", "immediate",
                "present", "current status", "right now", "this moment"
            ],
            "optimization": [
                "optimize", "improve", "enhance", "better", "performance", "efficiency",
                "accuracy", "tune", "refine", "upgrade", "boost"
            ],
            "risk_assessment": [
                "risk", "risks", "danger", "threat", "warning", "alert", "concern",
                "vulnerable", "exposure", "likelihood", "probability", "chance"
            ],
            "comparison": [
                "compare", "vs", "versus", "against", "difference", "better", "worse",
                "higher", "lower", "relative", "benchmark"
            ]
        }
        
        # Response templates
        self.response_templates = {
            "forecast_results": "Based on my analysis of {domains} domains over {horizon} periods, here are the key forecasting insights:",
            "anomaly_findings": "I detected {count} anomalies across {domains} domains with {severity} severity patterns:",
            "pattern_insights": "I identified {count} significant patterns across your business domains:",
            "real_time_predictions": "Current real-time predictions show {status} across monitored metrics:",
            "optimization_results": "Model optimization analysis shows potential {improvement}% performance gains:",
            "risk_assessment": "Risk assessment indicates {level} risk levels with {concerns} key concerns:",
            "no_data": "I need more data to provide accurate predictions for {domain}. Consider expanding the analysis timeframe."
        }
        
        # Domain expertise mappings
        self.domain_expertise = {
            "financial": {
                "key_metrics": ["revenue", "profit", "cash_flow", "expenses"],
                "typical_patterns": ["seasonal revenue cycles", "quarterly profit patterns"],
                "risk_indicators": ["declining cash flow", "increasing expenses", "profit margin compression"]
            },
            "sales": {
                "key_metrics": ["total_sales", "conversion_rate", "pipeline_value", "deal_size"],
                "typical_patterns": ["monthly sales cycles", "seasonal demand patterns"],
                "risk_indicators": ["declining conversion rates", "shrinking pipeline", "deal size reduction"]
            },
            "hr": {
                "key_metrics": ["retention_rate", "satisfaction_score", "productivity", "headcount"],
                "typical_patterns": ["seasonal hiring patterns", "performance review cycles"],
                "risk_indicators": ["high turnover", "declining satisfaction", "productivity drops"]
            },
            "manufacturing": {
                "key_metrics": ["production_volume", "oee", "quality_score", "efficiency"],
                "typical_patterns": ["production cycles", "seasonal demand variations"],
                "risk_indicators": ["declining oee", "quality issues", "efficiency drops"]
            }
        }
    
    def can_handle_query(self, query: str, context: Dict = None) -> bool:
        """
        Determine if this agent can handle the given query
        
        Args:
            query: User query string
            context: Query context
            
        Returns:
            Boolean indicating if agent can handle the query
        """
        try:
            query_lower = query.lower()
            
            # Check for predictive analytics keywords
            predictive_indicators = [
                "predict", "forecast", "trend", "future", "anomaly", "pattern",
                "correlation", "risk", "probability", "likelihood", "projection",
                "expected", "anticipated", "optimize", "model", "analytics"
            ]
            
            # Check for time-related terms
            time_indicators = [
                "next", "future", "tomorrow", "week", "month", "quarter", "year",
                "upcoming", "coming", "ahead", "forward", "later"
            ]
            
            # Agent can handle if query contains predictive indicators
            if any(indicator in query_lower for indicator in predictive_indicators):
                return True
            
            # Also handle time-based questions with business context
            if any(time_term in query_lower for time_term in time_indicators):
                business_terms = ["sales", "revenue", "profit", "performance", "growth"]
                if any(term in query_lower for term in business_terms):
                    return True
            
            # Handle if context suggests predictive analytics
            if context and context.get("intent") in ["forecasting", "prediction", "analytics"]:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error in can_handle_query: {e}")
            return False
    
    def get_insights(self, query: str, context: Dict = None) -> Dict[str, Any]:
        """
        Process predictive analytics query and return intelligent insights.

        Disabled 2026-08-04: this agent's entire analytics_engine
        (AdvancedPredictiveAnalyticsEngine) generates simulated historical
        data in _get_domain_historical_data instead of querying it, so every
        forecast/anomaly/pattern result it produces is fabricated. Returns an
        honest not_implemented status until the underlying engine is backed
        by real data. See plan-eng-review D3.2.

        Args:
            query: Predictive analytics query string
            context: Query context and parameters

        Returns:
            Comprehensive predictive analytics insights
        """
        return {
            "status": "not_implemented",
            "message": "Predictive analytics is not yet backed by real historical data",
        }

    def _disabled_get_insights(self, query: str, context: Dict = None) -> Dict[str, Any]:
        """Former get_insights body, retained for when the engine is fixed. Never called."""
        try:
            logger.info(f"Processing predictive analytics query: {query}")
            
            # Classify query type
            query_type = self._classify_query(query)
            
            # Extract parameters from query
            query_params = self._extract_query_parameters(query, context)
            
            # Handle different query types
            if query_type == "forecasting":
                return self._handle_forecasting_query(query, query_params)
            elif query_type == "anomaly_detection":
                return self._handle_anomaly_query(query, query_params)
            elif query_type == "pattern_analysis":
                return self._handle_pattern_query(query, query_params)
            elif query_type == "real_time":
                return self._handle_real_time_query(query, query_params)
            elif query_type == "optimization":
                return self._handle_optimization_query(query, query_params)
            elif query_type == "risk_assessment":
                return self._handle_risk_query(query, query_params)
            elif query_type == "comparison":
                return self._handle_comparison_query(query, query_params)
            else:
                # Default to general forecasting
                return self._handle_forecasting_query(query, query_params)
            
        except Exception as e:
            logger.error(f"Error processing predictive analytics query: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "I encountered an error while processing your predictive analytics request. Please try again."
            }
    
    def _classify_query(self, query: str) -> str:
        """Classify the type of predictive analytics query"""
        query_lower = query.lower()
        
        # Score each query type
        type_scores = {}
        for query_type, patterns in self.query_patterns.items():
            score = sum(1 for pattern in patterns if pattern in query_lower)
            if score > 0:
                type_scores[query_type] = score
        
        # Return type with highest score
        if type_scores:
            return max(type_scores.items(), key=lambda x: x[1])[0]
        
        return "forecasting"  # Default
    
    def _extract_query_parameters(self, query: str, context: Dict = None) -> Dict[str, Any]:
        """Extract parameters from query and context"""
        params = {
            "domain": "all",
            "horizon": 12,
            "include_scenarios": False,
            "sensitivity": "medium",
            "confidence_threshold": 0.7,
            "lookback_months": 24
        }
        
        # Update with context if provided
        if context:
            params.update(context.get("parameters", {}))
        
        # Extract domain from query
        query_lower = query.lower()
        domain_keywords = {
            "financial": ["financial", "finance", "revenue", "profit", "cash"],
            "sales": ["sales", "selling", "deals", "pipeline", "customers"],
            "hr": ["hr", "human resources", "employees", "staff", "workforce"],
            "manufacturing": ["manufacturing", "production", "factory", "oee"],
            "customer": ["customer", "client", "churn", "retention", "satisfaction"],
            "esg": ["esg", "environmental", "sustainability", "carbon", "green"]
        }
        
        for domain_id, keywords in domain_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                params["domain"] = domain_id
                break
        
        # Extract time horizon
        horizon_patterns = {
            r"(\d+)\s*(month|months)": lambda m: int(m.group(1)),
            r"(\d+)\s*(quarter|quarters)": lambda m: int(m.group(1)) * 3,
            r"(\d+)\s*(year|years)": lambda m: int(m.group(1)) * 12,
            r"next\s*(\d+)": lambda m: int(m.group(1)),
            r"(\d+)\s*period": lambda m: int(m.group(1))
        }
        
        for pattern, extractor in horizon_patterns.items():
            match = re.search(pattern, query_lower)
            if match:
                params["horizon"] = extractor(match)
                break
        
        # Extract sensitivity for anomaly detection
        if "high sensitivity" in query_lower:
            params["sensitivity"] = "high"
        elif "low sensitivity" in query_lower:
            params["sensitivity"] = "low"
        
        # Check for scenario analysis
        if any(term in query_lower for term in ["scenario", "scenarios", "what if", "optimistic", "pessimistic"]):
            params["include_scenarios"] = True
        
        return params
    
    def _handle_forecasting_query(self, query: str, params: Dict) -> Dict[str, Any]:
        """Handle forecasting-specific queries"""
        try:
            # Generate comprehensive forecasts
            forecast_results = self.analytics_engine.generate_comprehensive_forecasts(
                domain=params.get("domain", "all"),
                forecast_horizon=params.get("horizon", 12),
                include_scenarios=params.get("include_scenarios", False)
            )
            
            # Generate conversational response
            response = self._generate_forecast_response(query, forecast_results, params)
            
            # Extract key insights
            key_insights = self._extract_forecast_insights(forecast_results)
            
            # Generate recommendations
            recommendations = forecast_results.get("recommendations", [])
            
            return {
                "success": True,
                "query_type": "forecasting",
                "agent_response": response,
                "forecast_data": forecast_results,
                "key_insights": key_insights,
                "recommendations": recommendations,
                "conversation_context": {
                    "last_query": query,
                    "parameters": params,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error handling forecasting query: {e}")
            return {
                "success": False,
                "message": "I had trouble generating forecasts. Please check your query parameters and try again."
            }
    
    def _handle_anomaly_query(self, query: str, params: Dict) -> Dict[str, Any]:
        """Handle anomaly detection queries"""
        try:
            # Detect anomalies and risks
            anomaly_results = self.analytics_engine.detect_anomalies_and_risks(
                domain=params.get("domain", "all"),
                sensitivity=params.get("sensitivity", "medium")
            )
            
            # Generate conversational response
            response = self._generate_anomaly_response(query, anomaly_results, params)
            
            # Extract critical findings
            critical_findings = self._extract_anomaly_insights(anomaly_results)
            
            # Get recommended actions
            recommended_actions = anomaly_results.get("recommended_actions", [])
            
            return {
                "success": True,
                "query_type": "anomaly_detection",
                "agent_response": response,
                "anomaly_data": anomaly_results,
                "critical_findings": critical_findings,
                "recommended_actions": recommended_actions,
                "early_warnings": anomaly_results.get("early_warnings", [])
            }
            
        except Exception as e:
            logger.error(f"Error handling anomaly query: {e}")
            return {
                "success": False,
                "message": "I encountered an issue while detecting anomalies. Please try again."
            }
    
    def _handle_pattern_query(self, query: str, params: Dict) -> Dict[str, Any]:
        """Handle pattern analysis queries"""
        try:
            # Analyze predictive patterns
            pattern_results = self.analytics_engine.analyze_predictive_patterns(
                lookback_months=params.get("lookback_months", 24),
                include_correlations=True
            )
            
            # Generate conversational response
            response = self._generate_pattern_response(query, pattern_results, params)
            
            # Extract significant patterns
            significant_patterns = self._extract_pattern_insights(pattern_results)
            
            return {
                "success": True,
                "query_type": "pattern_analysis",
                "agent_response": response,
                "pattern_data": pattern_results,
                "significant_patterns": significant_patterns,
                "pattern_insights": pattern_results.get("pattern_insights", [])
            }
            
        except Exception as e:
            logger.error(f"Error handling pattern query: {e}")
            return {
                "success": False,
                "message": "I had trouble analyzing patterns. Please try again."
            }
    
    def _handle_real_time_query(self, query: str, params: Dict) -> Dict[str, Any]:
        """Handle real-time prediction queries"""
        try:
            # Get real-time predictions
            prediction_results = self.analytics_engine.get_real_time_predictions(
                confidence_threshold=params.get("confidence_threshold", 0.7)
            )
            
            # Generate conversational response
            response = self._generate_real_time_response(query, prediction_results, params)
            
            # Extract current status
            current_status = self._extract_real_time_insights(prediction_results)
            
            return {
                "success": True,
                "query_type": "real_time",
                "agent_response": response,
                "prediction_data": prediction_results,
                "current_status": current_status,
                "alerts": prediction_results.get("alerts", [])
            }
            
        except Exception as e:
            logger.error(f"Error handling real-time query: {e}")
            return {
                "success": False,
                "message": "I couldn't get real-time predictions. Please try again."
            }
    
    def _handle_optimization_query(self, query: str, params: Dict) -> Dict[str, Any]:
        """Handle model optimization queries"""
        try:
            # Optimize prediction models
            optimization_results = self.analytics_engine.optimize_prediction_models(
                domain=params.get("domain", "all"),
                optimization_metric=params.get("metric", "rmse")
            )
            
            # Generate conversational response
            response = self._generate_optimization_response(query, optimization_results, params)
            
            # Extract optimization insights
            optimization_insights = self._extract_optimization_insights(optimization_results)
            
            return {
                "success": True,
                "query_type": "optimization",
                "agent_response": response,
                "optimization_data": optimization_results,
                "optimization_insights": optimization_insights
            }
            
        except Exception as e:
            logger.error(f"Error handling optimization query: {e}")
            return {
                "success": False,
                "message": "I couldn't optimize the models. Please try again."
            }
    
    def _handle_risk_query(self, query: str, params: Dict) -> Dict[str, Any]:
        """Handle risk assessment queries"""
        try:
            # Perform comprehensive analysis for risk assessment
            forecast_results = self.analytics_engine.generate_comprehensive_forecasts(
                domain=params.get("domain", "all"),
                forecast_horizon=params.get("horizon", 12)
            )
            
            anomaly_results = self.analytics_engine.detect_anomalies_and_risks(
                domain=params.get("domain", "all")
            )
            
            # Generate risk-focused response
            response = self._generate_risk_response(query, forecast_results, anomaly_results, params)
            
            # Extract risk insights
            risk_insights = self._extract_risk_insights(forecast_results, anomaly_results)
            
            return {
                "success": True,
                "query_type": "risk_assessment",
                "agent_response": response,
                "risk_assessment": forecast_results.get("risk_assessment", {}),
                "anomaly_risks": anomaly_results.get("risk_patterns", {}),
                "risk_insights": risk_insights
            }
            
        except Exception as e:
            logger.error(f"Error handling risk query: {e}")
            return {
                "success": False,
                "message": "I couldn't complete the risk assessment. Please try again."
            }
    
    def _handle_comparison_query(self, query: str, params: Dict) -> Dict[str, Any]:
        """Handle comparison queries"""
        try:
            # Extract comparison entities from query
            entities = self._extract_comparison_entities(query)
            
            comparison_data = {}
            
            # Generate forecasts for each entity
            for entity in entities:
                if entity in self.analytics_engine.prediction_domains:
                    forecast_results = self.analytics_engine.generate_comprehensive_forecasts(
                        domain=entity,
                        forecast_horizon=params.get("horizon", 12)
                    )
                    comparison_data[entity] = forecast_results
            
            # Generate comparison response
            response = self._generate_comparison_response(query, comparison_data, params)
            
            # Extract comparison insights
            comparison_insights = self._extract_comparison_insights(comparison_data)
            
            return {
                "success": True,
                "query_type": "comparison",
                "agent_response": response,
                "comparison_data": comparison_data,
                "comparison_insights": comparison_insights
            }
            
        except Exception as e:
            logger.error(f"Error handling comparison query: {e}")
            return {
                "success": False,
                "message": "I couldn't complete the comparison analysis. Please try again."
            }
    
    # Helper methods for response generation
    
    def _generate_forecast_response(self, query: str, forecast_results: Dict, params: Dict) -> str:
        """Generate conversational response for forecasting"""
        try:
            summary = forecast_results.get("summary", {})
            domains_count = summary.get("total_domains", 0)
            horizon = summary.get("forecast_horizon", 12)
            
            response = self.response_templates["forecast_results"].format(
                domains=domains_count,
                horizon=horizon
            )
            
            # Add key findings
            domain_forecasts = forecast_results.get("domain_forecasts", {})
            if domain_forecasts:
                response += "\n\nKey forecasting findings:"
                
                for domain_id, forecast_data in list(domain_forecasts.items())[:3]:
                    metrics = forecast_data.get("metric_forecasts", {})
                    if metrics:
                        first_metric = list(metrics.keys())[0]
                        predictions = metrics[first_metric]
                        if predictions and len(predictions) > 1:
                            trend = "increasing" if predictions[-1] > predictions[0] else "decreasing"
                            response += f"\n• {domain_id.title()}: {first_metric} showing {trend} trend"
            
            # Add risk assessment if available
            risk_assessment = forecast_results.get("risk_assessment", {})
            overall_risk = risk_assessment.get("overall_risk_score", 0)
            if overall_risk > 0.5:
                response += f"\n\n⚠️ Risk Alert: Overall risk score is {overall_risk:.1%} - consider reviewing the recommendations."
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating forecast response: {e}")
            return "I've completed the forecast analysis. Please check the detailed results."
    
    def _generate_anomaly_response(self, query: str, anomaly_results: Dict, params: Dict) -> str:
        """Generate conversational response for anomaly detection"""
        try:
            summary = anomaly_results.get("summary", {})
            total_anomalies = summary.get("total_anomalies", 0)
            domains_analyzed = summary.get("domains_analyzed", 0)
            
            # Determine severity distribution
            domain_anomalies = anomaly_results.get("domain_anomalies", {})
            high_severity_count = sum(
                domain_data.get("severity_distribution", {}).get("high", 0) 
                for domain_data in domain_anomalies.values()
            )
            
            severity_status = "high" if high_severity_count > 3 else "medium" if total_anomalies > 10 else "low"
            
            response = self.response_templates["anomaly_findings"].format(
                count=total_anomalies,
                domains=domains_analyzed,
                severity=severity_status
            )
            
            # Add critical findings
            if high_severity_count > 0:
                response += f"\n\n🚨 Critical: {high_severity_count} high-severity anomalies detected requiring immediate attention."
            
            # Add early warnings
            early_warnings = anomaly_results.get("early_warnings", [])
            if early_warnings:
                response += "\n\nEarly warning signals:"
                for warning in early_warnings[:3]:
                    response += f"\n• {warning.get('message', 'Unknown warning')}"
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating anomaly response: {e}")
            return "I've completed the anomaly detection analysis."
    
    def _generate_pattern_response(self, query: str, pattern_results: Dict, params: Dict) -> str:
        """Generate conversational response for pattern analysis"""
        try:
            summary = pattern_results.get("analysis_summary", {})
            patterns_count = summary.get("patterns_identified", 0)
            
            response = self.response_templates["pattern_insights"].format(
                count=patterns_count
            )
            
            # Add significant patterns
            domain_patterns = pattern_results.get("domain_patterns", {})
            if domain_patterns:
                response += "\n\nSignificant patterns identified:"
                
                for domain_id, domain_data in list(domain_patterns.items())[:3]:
                    patterns = domain_data.get("identified_patterns", [])
                    for pattern in patterns[:2]:
                        response += f"\n• {domain_id.title()}: {pattern.get('description', 'Pattern detected')}"
            
            # Add correlation insights
            correlation_matrix = pattern_results.get("correlation_matrix", {})
            strong_correlations = [
                corr for corr in correlation_matrix.values() 
                if corr.get("strength") == "strong"
            ]
            
            if strong_correlations:
                response += f"\n\n🔗 Found {len(strong_correlations)} strong correlations between business domains."
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating pattern response: {e}")
            return "I've completed the pattern analysis."
    
    def _generate_real_time_response(self, query: str, prediction_results: Dict, params: Dict) -> str:
        """Generate conversational response for real-time predictions"""
        try:
            real_time_predictions = prediction_results.get("real_time_predictions", {})
            alerts = prediction_results.get("alerts", [])
            
            status = "concerning" if len(alerts) > 3 else "stable" if len(alerts) == 0 else "mixed"
            
            response = self.response_templates["real_time_predictions"].format(
                status=status
            )
            
            # Add current predictions summary
            if real_time_predictions:
                response += "\n\nCurrent predictions across domains:"
                
                for domain_id, domain_predictions in list(real_time_predictions.items())[:3]:
                    for metric, prediction_data in list(domain_predictions.items())[:2]:
                        predicted_value = prediction_data.get("predicted_value", 0)
                        confidence = prediction_data.get("confidence", 0)
                        trend = prediction_data.get("trend", "stable")
                        
                        response += f"\n• {domain_id.title()} {metric}: {trend} trend (confidence: {confidence:.1%})"
            
            # Add alerts
            if alerts:
                urgent_alerts = [alert for alert in alerts if alert.get("type") == "concerning_prediction"]
                if urgent_alerts:
                    response += f"\n\n⚠️ {len(urgent_alerts)} concerning prediction(s) detected - review immediately."
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating real-time response: {e}")
            return "I've generated current real-time predictions."
    
    def _generate_optimization_response(self, query: str, optimization_results: Dict, params: Dict) -> str:
        """Generate conversational response for optimization"""
        try:
            model_improvements = optimization_results.get("model_improvements", {})
            
            # Calculate average improvement
            total_improvement = 0
            improvement_count = 0
            
            for domain_improvements in model_improvements.values():
                for improvement in domain_improvements:
                    total_improvement += improvement.get("improvement_percent", 0)
                    improvement_count += 1
            
            avg_improvement = total_improvement / improvement_count if improvement_count > 0 else 0
            
            response = self.response_templates["optimization_results"].format(
                improvement=f"{avg_improvement:.1f}"
            )
            
            # Add specific improvements
            if model_improvements:
                response += "\n\nOptimization opportunities identified:"
                
                for domain_id, improvements in list(model_improvements.items())[:3]:
                    for improvement in improvements[:2]:
                        metric = improvement.get("metric", "unknown")
                        percent = improvement.get("improvement_percent", 0)
                        model = improvement.get("best_model", "unknown")
                        
                        response += f"\n• {domain_id.title()} {metric}: {percent:.1f}% improvement with {model}"
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating optimization response: {e}")
            return "I've completed the optimization analysis."
    
    def _generate_risk_response(self, query: str, forecast_results: Dict, 
                               anomaly_results: Dict, params: Dict) -> str:
        """Generate conversational response for risk assessment"""
        try:
            # Get risk data
            risk_assessment = forecast_results.get("risk_assessment", {})
            overall_risk = risk_assessment.get("overall_risk_score", 0)
            critical_alerts = risk_assessment.get("critical_alerts", [])
            
            early_warnings = anomaly_results.get("early_warnings", [])
            
            risk_level = "high" if overall_risk > 0.7 else "medium" if overall_risk > 0.4 else "low"
            concerns_count = len(critical_alerts) + len(early_warnings)
            
            response = self.response_templates["risk_assessment"].format(
                level=risk_level,
                concerns=concerns_count
            )
            
            # Add critical risks
            if critical_alerts:
                response += "\n\nCritical risk alerts:"
                for alert in critical_alerts[:3]:
                    response += f"\n• {alert.get('message', 'Risk detected')}"
            
            # Add early warnings
            if early_warnings:
                response += "\n\nEarly warning signals:"
                for warning in early_warnings[:3]:
                    response += f"\n• {warning.get('message', 'Warning signal detected')}"
            
            # Add risk score interpretation
            response += f"\n\nOverall risk score: {overall_risk:.1%}"
            if overall_risk > 0.7:
                response += " (High - Immediate action required)"
            elif overall_risk > 0.4:
                response += " (Medium - Monitor closely)"
            else:
                response += " (Low - Routine monitoring)"
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating risk response: {e}")
            return "I've completed the risk assessment."
    
    def _generate_comparison_response(self, query: str, comparison_data: Dict, params: Dict) -> str:
        """Generate conversational response for comparisons"""
        try:
            entities = list(comparison_data.keys())
            
            response = f"I compared {' and '.join(entities)} using predictive analytics:\n"
            
            # Compare key metrics across entities
            for entity in entities:
                entity_data = comparison_data.get(entity, {})
                risk_assessment = entity_data.get("risk_assessment", {})
                overall_risk = risk_assessment.get("overall_risk_score", 0)
                
                risk_level = "high risk" if overall_risk > 0.7 else "medium risk" if overall_risk > 0.4 else "low risk"
                
                response += f"\n• {entity.title()}: {risk_level} (score: {overall_risk:.1%})"
                
                # Add trend information if available
                domain_forecasts = entity_data.get("domain_forecasts", {})
                if domain_forecasts:
                    entity_forecast = list(domain_forecasts.values())[0]
                    metric_forecasts = entity_forecast.get("metric_forecasts", {})
                    if metric_forecasts:
                        first_metric = list(metric_forecasts.keys())[0]
                        predictions = metric_forecasts[first_metric]
                        if predictions and len(predictions) > 1:
                            trend = "growing" if predictions[-1] > predictions[0] else "declining"
                            response += f" - {trend} trend"
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating comparison response: {e}")
            return "I've completed the comparison analysis."
    
    # Helper methods for insight extraction
    
    def _extract_forecast_insights(self, forecast_results: Dict) -> List[Dict[str, Any]]:
        """Extract key insights from forecast results"""
        insights = []
        
        try:
            domain_forecasts = forecast_results.get("domain_forecasts", {})
            
            for domain_id, forecast_data in domain_forecasts.items():
                metric_forecasts = forecast_data.get("metric_forecasts", {})
                
                for metric, predictions in metric_forecasts.items():
                    if predictions and len(predictions) > 1:
                        # Analyze trend
                        change_percent = ((predictions[-1] - predictions[0]) / predictions[0] * 100) if predictions[0] != 0 else 0
                        
                        if abs(change_percent) > 10:  # Significant change
                            insights.append({
                                "domain": domain_id,
                                "metric": metric,
                                "type": "trend",
                                "description": f"{metric} predicted to change by {change_percent:.1f}%",
                                "significance": "high" if abs(change_percent) > 20 else "medium"
                            })
            
            return insights[:10]  # Limit to top 10
            
        except Exception as e:
            logger.error(f"Error extracting forecast insights: {e}")
            return []
    
    def _extract_anomaly_insights(self, anomaly_results: Dict) -> List[Dict[str, Any]]:
        """Extract critical findings from anomaly results"""
        findings = []
        
        try:
            domain_anomalies = anomaly_results.get("domain_anomalies", {})
            
            for domain_id, anomaly_data in domain_anomalies.items():
                anomalies = anomaly_data.get("anomalies", [])
                high_severity = [a for a in anomalies if a.get("severity") == "high"]
                
                if high_severity:
                    findings.append({
                        "domain": domain_id,
                        "type": "high_severity_anomalies",
                        "count": len(high_severity),
                        "description": f"{len(high_severity)} high-severity anomalies in {domain_id}",
                        "urgency": "critical"
                    })
            
            return findings
            
        except Exception as e:
            logger.error(f"Error extracting anomaly insights: {e}")
            return []
    
    def _extract_comparison_entities(self, query: str) -> List[str]:
        """Extract entities to compare from query"""
        query_lower = query.lower()
        entities = []
        
        # Check for explicit domain mentions
        for domain_id in self.analytics_engine.prediction_domains.keys():
            if domain_id in query_lower:
                entities.append(domain_id)
        
        # If no specific domains found, extract from common patterns
        if not entities:
            if "vs" in query_lower or "versus" in query_lower:
                parts = re.split(r"\s+vs\s+|\s+versus\s+", query_lower)
                entities.extend([part.strip() for part in parts if part.strip()])
        
        # Remove duplicates and clean
        entities = [e for e in set(entities) if e in self.analytics_engine.prediction_domains]
        
        # Default comparison if none found
        if not entities and "compare" in query_lower:
            entities = ["financial", "sales"]  # Default comparison
        
        return entities[:4]  # Limit to 4 entities


# Agent instance
advanced_predictive_analytics_agent = AdvancedPredictiveAnalyticsAgent()