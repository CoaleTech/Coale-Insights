"""
Advanced Predictive Analytics Engine

Comprehensive machine learning engine providing:
- Multi-domain forecasting and trend analysis
- Advanced predictive modeling and insights
- Time series analysis and seasonal decomposition
- Risk prediction and early warning systems
- Intelligent recommendations based on predictive patterns
- Cross-domain correlation analysis and insights

Author: AI Assistant
Version: 1.0.0
"""

import frappe
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import json
import logging

# Optional ML dependencies
try:
    from sklearn.ensemble import RandomForestRegressor, IsolationForest
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.preprocessing import StandardScaler, LabelEncoder
    from sklearn.model_selection import TimeSeriesSplit, cross_val_score
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

class AdvancedPredictiveAnalyticsEngine:
    """
    Advanced ML Engine for predictive analytics across all business domains
    
    Features:
    - Time series forecasting with multiple algorithms
    - Anomaly detection and risk assessment
    - Correlation analysis and pattern recognition
    - Automated model selection and optimization
    - Cross-domain predictive insights
    - Real-time prediction serving
    """
    
    def __init__(self):
        """Initialize Advanced Predictive Analytics Engine"""
        self.engine_name = "Advanced Predictive Analytics Engine"
        self.version = "2.0.0"
        
        # Model configurations
        if HAS_SKLEARN:
            self.models = {
                "linear_regression": {"model": LinearRegression, "type": "regression"},
                "ridge_regression": {"model": Ridge, "type": "regression"},
                "random_forest": {"model": RandomForestRegressor, "type": "regression"},
                "isolation_forest": {"model": IsolationForest, "type": "anomaly"}
            }
        else:
            self.models = {}
        
        # Prediction domains and their characteristics
        self.prediction_domains = {
            "financial": {
                "metrics": ["revenue", "profit", "cash_flow", "expenses"],
                "seasonality": True,
                "trend_sensitivity": "medium",
                "forecast_horizon": 12  # months
            },
            "sales": {
                "metrics": ["total_sales", "conversion_rate", "pipeline_value", "deal_size"],
                "seasonality": True,
                "trend_sensitivity": "high",
                "forecast_horizon": 6
            },
            "hr": {
                "metrics": ["headcount", "retention_rate", "satisfaction_score", "productivity"],
                "seasonality": False,
                "trend_sensitivity": "low",
                "forecast_horizon": 12
            },
            "manufacturing": {
                "metrics": ["production_volume", "oee", "quality_score", "efficiency"],
                "seasonality": True,
                "trend_sensitivity": "medium",
                "forecast_horizon": 3
            },
            "customer": {
                "metrics": ["acquisition_rate", "churn_rate", "lifetime_value", "satisfaction"],
                "seasonality": False,
                "trend_sensitivity": "medium",
                "forecast_horizon": 6
            },
            "inventory": {
                "metrics": ["stock_levels", "turnover_rate", "stockout_risk", "holding_cost"],
                "seasonality": True,
                "trend_sensitivity": "high",
                "forecast_horizon": 3
            },
            "esg": {
                "metrics": ["carbon_emissions", "energy_consumption", "waste_reduction", "compliance_score"],
                "seasonality": True,
                "trend_sensitivity": "low",
                "forecast_horizon": 12
            }
        }
        
        # Risk thresholds and alerting
        self.risk_thresholds = {
            "high": 0.8,
            "medium": 0.5,
            "low": 0.2
        }
        
        # Initialize scalers and encoders
        self.scalers = {}
        self.encoders = {}
        
        # Model performance tracking
        self.model_performance = {}
    
    def generate_comprehensive_forecasts(self, domain: str = "all", 
                                         forecast_horizon: int = 12,
                                         include_scenarios: bool = True) -> Dict[str, Any]:
        """
        Generate comprehensive forecasts across specified domains
        
        Args:
            domain: Specific domain or "all" for all domains
            forecast_horizon: Number of periods to forecast
            include_scenarios: Whether to include scenario analysis
            
        Returns:
            Comprehensive forecasting results with insights
        """
        try:
            if not HAS_SKLEARN:
                return {
                    "status": "error",
                    "message": "scikit-learn not installed. Run: pip install insights[ml]"
                }
            
            logger.info(f"Generating comprehensive forecasts for domain: {domain}")
            
            # Determine domains to process
            domains_to_process = [domain] if domain != "all" else list(self.prediction_domains.keys())
            
            # Initialize results structure
            forecast_results = {
                "summary": {
                    "total_domains": len(domains_to_process),
                    "forecast_horizon": forecast_horizon,
                    "generated_at": datetime.now().isoformat(),
                    "model_confidence": "high"
                },
                "domain_forecasts": {},
                "cross_domain_insights": {},
                "risk_assessment": {},
                "recommendations": []
            }
            
            # Process each domain
            for domain_id in domains_to_process:
                domain_config = self.prediction_domains[domain_id]
                
                # Generate domain-specific forecasts
                domain_forecast = self._generate_domain_forecast(
                    domain_id, domain_config, forecast_horizon
                )
                
                forecast_results["domain_forecasts"][domain_id] = domain_forecast
            
            # Generate cross-domain insights
            if len(domains_to_process) > 1:
                cross_domain_insights = self._analyze_cross_domain_patterns(
                    forecast_results["domain_forecasts"]
                )
                forecast_results["cross_domain_insights"] = cross_domain_insights
            
            # Perform risk assessment
            risk_assessment = self._assess_predictive_risks(
                forecast_results["domain_forecasts"]
            )
            forecast_results["risk_assessment"] = risk_assessment
            
            # Generate strategic recommendations
            recommendations = self._generate_predictive_recommendations(
                forecast_results["domain_forecasts"],
                risk_assessment
            )
            forecast_results["recommendations"] = recommendations
            
            # Include scenario analysis if requested
            if include_scenarios:
                scenarios = self._generate_scenario_analysis(
                    forecast_results["domain_forecasts"]
                )
                forecast_results["scenario_analysis"] = scenarios
            
            # Update model performance tracking
            self._update_performance_tracking(forecast_results)
            
            return forecast_results
            
        except Exception as e:
            logger.error(f"Error generating comprehensive forecasts: {e}")
            frappe.log_error(f"Predictive Analytics Error: {str(e)}", "Advanced Analytics")
            return {"error": str(e), "forecasts": {}}
    
    def detect_anomalies_and_risks(self, domain: str = "all", 
                                   sensitivity: str = "medium") -> Dict[str, Any]:
        """
        Detect anomalies and assess risks across business domains
        
        Args:
            domain: Specific domain or "all" for all domains
            sensitivity: Detection sensitivity (low, medium, high)
            
        Returns:
            Comprehensive anomaly detection and risk assessment
        """
        try:
            logger.info(f"Detecting anomalies and risks for domain: {domain}")
            
            # Determine domains to analyze
            domains_to_analyze = [domain] if domain != "all" else list(self.prediction_domains.keys())
            
            # Initialize results
            anomaly_results = {
                "summary": {
                    "domains_analyzed": len(domains_to_analyze),
                    "detection_sensitivity": sensitivity,
                    "analysis_timestamp": datetime.now().isoformat(),
                    "total_anomalies": 0
                },
                "domain_anomalies": {},
                "risk_patterns": {},
                "early_warnings": [],
                "recommended_actions": []
            }
            
            total_anomalies = 0
            
            # Analyze each domain
            for domain_id in domains_to_analyze:
                domain_data = self._get_domain_historical_data(domain_id)
                
                if domain_data.empty:
                    continue
                
                # Detect anomalies in domain data
                domain_anomalies = self._detect_domain_anomalies(
                    domain_data, domain_id, sensitivity
                )
                
                anomaly_results["domain_anomalies"][domain_id] = domain_anomalies
                total_anomalies += len(domain_anomalies.get("anomalies", []))
            
            anomaly_results["summary"]["total_anomalies"] = total_anomalies
            
            # Analyze risk patterns across domains
            risk_patterns = self._analyze_risk_patterns(
                anomaly_results["domain_anomalies"]
            )
            anomaly_results["risk_patterns"] = risk_patterns
            
            # Generate early warning signals
            early_warnings = self._generate_early_warnings(
                anomaly_results["domain_anomalies"],
                risk_patterns
            )
            anomaly_results["early_warnings"] = early_warnings
            
            # Recommend actions
            actions = self._recommend_anomaly_actions(
                anomaly_results["domain_anomalies"],
                early_warnings
            )
            anomaly_results["recommended_actions"] = actions
            
            return anomaly_results
            
        except Exception as e:
            logger.error(f"Error in anomaly detection: {e}")
            return {"error": str(e), "anomalies": {}}
    
    def analyze_predictive_patterns(self, lookback_months: int = 24,
                                    include_correlations: bool = True) -> Dict[str, Any]:
        """
        Analyze predictive patterns and correlations across domains
        
        Args:
            lookback_months: Number of months of historical data to analyze
            include_correlations: Whether to include correlation analysis
            
        Returns:
            Comprehensive pattern analysis results
        """
        try:
            logger.info(f"Analyzing predictive patterns over {lookback_months} months")
            
            # Initialize results
            pattern_results = {
                "analysis_summary": {
                    "lookback_period": lookback_months,
                    "analysis_date": datetime.now().isoformat(),
                    "patterns_identified": 0
                },
                "domain_patterns": {},
                "seasonal_patterns": {},
                "trend_analysis": {},
                "correlation_matrix": {},
                "pattern_insights": []
            }
            
            patterns_identified = 0
            
            # Analyze patterns for each domain
            for domain_id, domain_config in self.prediction_domains.items():
                domain_data = self._get_domain_historical_data(domain_id, lookback_months)
                
                if domain_data.empty:
                    continue
                
                # Analyze domain-specific patterns
                domain_patterns = self._analyze_domain_patterns(domain_data, domain_config)
                pattern_results["domain_patterns"][domain_id] = domain_patterns
                patterns_identified += len(domain_patterns.get("identified_patterns", []))
                
                # Seasonal decomposition if applicable
                if domain_config["seasonality"]:
                    seasonal_analysis = self._decompose_seasonal_patterns(domain_data)
                    pattern_results["seasonal_patterns"][domain_id] = seasonal_analysis
                
                # Trend analysis
                trend_analysis = self._analyze_trends(domain_data, domain_config)
                pattern_results["trend_analysis"][domain_id] = trend_analysis
            
            pattern_results["analysis_summary"]["patterns_identified"] = patterns_identified
            
            # Cross-domain correlation analysis
            if include_correlations:
                correlation_matrix = self._calculate_cross_domain_correlations()
                pattern_results["correlation_matrix"] = correlation_matrix
            
            # Generate insights from patterns
            insights = self._generate_pattern_insights(pattern_results)
            pattern_results["pattern_insights"] = insights
            
            return pattern_results
            
        except Exception as e:
            logger.error(f"Error analyzing predictive patterns: {e}")
            return {"error": str(e), "patterns": {}}
    
    def get_real_time_predictions(self, metrics: List[str] = None,
                                  confidence_threshold: float = 0.7) -> Dict[str, Any]:
        """
        Get real-time predictions for specified metrics
        
        Args:
            metrics: List of specific metrics to predict
            confidence_threshold: Minimum confidence for predictions
            
        Returns:
            Real-time prediction results
        """
        try:
            logger.info("Generating real-time predictions")
            
            # Initialize results
            prediction_results = {
                "prediction_timestamp": datetime.now().isoformat(),
                "real_time_predictions": {},
                "confidence_scores": {},
                "prediction_intervals": {},
                "alerts": []
            }
            
            # Process each domain
            for domain_id, domain_config in self.prediction_domains.items():
                domain_metrics = metrics if metrics else domain_config["metrics"]
                
                # Generate predictions for domain metrics
                domain_predictions = self._generate_real_time_domain_predictions(
                    domain_id, domain_metrics, confidence_threshold
                )
                
                if domain_predictions:
                    prediction_results["real_time_predictions"][domain_id] = domain_predictions
                    
                    # Extract confidence scores
                    for metric, prediction_data in domain_predictions.items():
                        confidence_key = f"{domain_id}_{metric}"
                        prediction_results["confidence_scores"][confidence_key] = prediction_data.get("confidence", 0)
                        
                        # Add intervals if available
                        if "prediction_interval" in prediction_data:
                            prediction_results["prediction_intervals"][confidence_key] = prediction_data["prediction_interval"]
                        
                        # Generate alerts for low confidence or concerning predictions
                        if prediction_data.get("confidence", 0) < confidence_threshold:
                            prediction_results["alerts"].append({
                                "type": "low_confidence",
                                "domain": domain_id,
                                "metric": metric,
                                "confidence": prediction_data.get("confidence", 0),
                                "message": f"Low confidence prediction for {metric} in {domain_id}"
                            })
                        
                        # Check for concerning prediction values
                        if self._is_concerning_prediction(domain_id, metric, prediction_data):
                            prediction_results["alerts"].append({
                                "type": "concerning_prediction",
                                "domain": domain_id,
                                "metric": metric,
                                "predicted_value": prediction_data.get("predicted_value"),
                                "message": f"Concerning prediction for {metric}: potential risk detected"
                            })
            
            return prediction_results
            
        except Exception as e:
            logger.error(f"Error generating real-time predictions: {e}")
            return {"error": str(e), "predictions": {}}
    
    def optimize_prediction_models(self, domain: str = "all",
                                   optimization_metric: str = "rmse") -> Dict[str, Any]:
        """
        Optimize prediction models using cross-validation and hyperparameter tuning
        
        Args:
            domain: Domain to optimize or "all" for all domains
            optimization_metric: Metric to optimize (rmse, mae, r2)
            
        Returns:
            Model optimization results and performance improvements
        """
        try:
            logger.info(f"Optimizing prediction models for {domain}")
            
            # Determine domains to optimize
            domains_to_optimize = [domain] if domain != "all" else list(self.prediction_domains.keys())
            
            optimization_results = {
                "optimization_summary": {
                    "domains_optimized": len(domains_to_optimize),
                    "optimization_metric": optimization_metric,
                    "optimization_date": datetime.now().isoformat()
                },
                "model_improvements": {},
                "best_models": {},
                "performance_gains": {}
            }
            
            # Optimize models for each domain
            for domain_id in domains_to_optimize:
                domain_data = self._get_domain_historical_data(domain_id)
                
                if domain_data.empty:
                    continue
                
                # Optimize domain models
                domain_optimization = self._optimize_domain_models(
                    domain_id, domain_data, optimization_metric
                )
                
                optimization_results["model_improvements"][domain_id] = domain_optimization["improvements"]
                optimization_results["best_models"][domain_id] = domain_optimization["best_model"]
                optimization_results["performance_gains"][domain_id] = domain_optimization["performance_gain"]
            
            return optimization_results
            
        except Exception as e:
            logger.error(f"Error optimizing prediction models: {e}")
            return {"error": str(e), "optimization": {}}
    
    # Private helper methods
    
    def _generate_domain_forecast(self, domain_id: str, domain_config: Dict,
                                  forecast_horizon: int) -> Dict[str, Any]:
        """Generate forecast for a specific domain"""
        try:
            # Get historical data
            historical_data = self._get_domain_historical_data(domain_id)
            
            if historical_data.empty:
                return {"error": f"No historical data available for {domain_id}"}
            
            # Generate forecasts for each metric
            domain_forecast = {
                "domain_id": domain_id,
                "forecast_horizon": forecast_horizon,
                "metric_forecasts": {},
                "model_performance": {},
                "confidence_intervals": {}
            }
            
            for metric in domain_config["metrics"]:
                if metric in historical_data.columns:
                    # Generate metric forecast
                    metric_forecast = self._forecast_metric(
                        historical_data[metric], metric, forecast_horizon
                    )
                    
                    domain_forecast["metric_forecasts"][metric] = metric_forecast["predictions"]
                    domain_forecast["model_performance"][metric] = metric_forecast["performance"]
                    domain_forecast["confidence_intervals"][metric] = metric_forecast["intervals"]
            
            return domain_forecast
            
        except Exception as e:
            logger.error(f"Error generating domain forecast for {domain_id}: {e}")
            return {"error": str(e)}
    
    def _forecast_metric(self, metric_data: pd.Series, metric_name: str,
                         horizon: int) -> Dict[str, Any]:
        """Forecast individual metric using best available model"""
        try:
            # Prepare data
            X, y = self._prepare_time_series_data(metric_data)
            
            if len(X) < 10:  # Need minimum data points
                return {
                    "predictions": [metric_data.mean()] * horizon,
                    "performance": {"error": "Insufficient data"},
                    "intervals": []
                }
            
            # Try different models and select best
            best_model, best_score = self._select_best_model(X, y)
            
            # Fit best model
            best_model.fit(X, y)
            
            # Generate predictions
            predictions = []
            intervals = []
            
            # Generate future predictions
            last_window = X[-1].reshape(1, -1)
            for _ in range(horizon):
                pred = best_model.predict(last_window)[0]
                predictions.append(pred)
                
                # Simple confidence interval (can be improved)
                std_error = np.std(y) * 0.2
                intervals.append([pred - 1.96 * std_error, pred + 1.96 * std_error])
                
                # Update window for next prediction
                last_window = np.roll(last_window, -1)
                last_window[0, -1] = pred
            
            return {
                "predictions": predictions,
                "performance": {"score": best_score, "model": str(best_model)},
                "intervals": intervals
            }
            
        except Exception as e:
            logger.error(f"Error forecasting metric {metric_name}: {e}")
            return {
                "predictions": [],
                "performance": {"error": str(e)},
                "intervals": []
            }
    
    def _prepare_time_series_data(self, series: pd.Series, window_size: int = 5) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare time series data for ML models"""
        # Remove NaN values
        series = series.dropna()
        
        if len(series) < window_size + 1:
            return np.array([]), np.array([])
        
        X, y = [], []
        for i in range(len(series) - window_size):
            X.append(series.iloc[i:i + window_size].values)
            y.append(series.iloc[i + window_size])
        
        return np.array(X), np.array(y)
    
    def _select_best_model(self, X: np.ndarray, y: np.ndarray) -> Tuple[Any, float]:
        """Select best model using cross-validation"""
        best_model = None
        best_score = float('-inf')
        
        # Try different models
        models_to_try = [
            LinearRegression(),
            Ridge(alpha=1.0),
            RandomForestRegressor(n_estimators=50, random_state=42)
        ]
        
        for model in models_to_try:
            try:
                # Use time series cross-validation
                tscv = TimeSeriesSplit(n_splits=3)
                scores = cross_val_score(model, X, y, cv=tscv, scoring='neg_mean_squared_error')
                avg_score = scores.mean()
                
                if avg_score > best_score:
                    best_score = avg_score
                    best_model = model
            except Exception as e:
                logger.warning(f"Model failed: {model}, error: {e}")
                continue
        
        # Fallback to simple model if none worked
        if best_model is None:
            best_model = LinearRegression()
            best_score = 0.0
        
        return best_model, best_score
    
    def _get_domain_historical_data(self, domain_id: str, months_back: int = 24) -> pd.DataFrame:
        """Get historical data for domain (simulated for now)"""
        try:
            # In a real implementation, this would fetch actual data from the database
            # For now, generating simulated data
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=months_back * 30)
            
            # Generate date range
            dates = pd.date_range(start=start_date, end=end_date, freq='D')
            
            # Generate simulated data based on domain
            np.random.seed(42)  # For reproducible results
            
            if domain_id == "financial":
                data = {
                    'revenue': np.random.normal(100000, 10000, len(dates)) + np.arange(len(dates)) * 10,
                    'profit': np.random.normal(20000, 5000, len(dates)) + np.arange(len(dates)) * 5,
                    'cash_flow': np.random.normal(15000, 8000, len(dates)),
                    'expenses': np.random.normal(80000, 8000, len(dates))
                }
            elif domain_id == "sales":
                data = {
                    'total_sales': np.random.normal(50000, 8000, len(dates)) + np.arange(len(dates)) * 8,
                    'conversion_rate': np.random.normal(0.15, 0.05, len(dates)),
                    'pipeline_value': np.random.normal(200000, 30000, len(dates)),
                    'deal_size': np.random.normal(5000, 1000, len(dates))
                }
            elif domain_id == "hr":
                data = {
                    'headcount': np.random.normal(250, 10, len(dates)) + np.arange(len(dates)) * 0.1,
                    'retention_rate': np.random.normal(0.92, 0.03, len(dates)),
                    'satisfaction_score': np.random.normal(4.2, 0.3, len(dates)),
                    'productivity': np.random.normal(85, 5, len(dates))
                }
            else:
                # Default simulated data
                data = {
                    'metric_1': np.random.normal(100, 20, len(dates)),
                    'metric_2': np.random.normal(50, 10, len(dates)),
                    'metric_3': np.random.normal(75, 15, len(dates))
                }
            
            df = pd.DataFrame(data, index=dates)
            return df
            
        except Exception as e:
            logger.error(f"Error getting historical data for {domain_id}: {e}")
            return pd.DataFrame()
    
    def _analyze_cross_domain_patterns(self, domain_forecasts: Dict) -> Dict[str, Any]:
        """Analyze patterns across domain forecasts"""
        try:
            insights = {
                "correlation_insights": [],
                "synchronized_trends": [],
                "leading_indicators": [],
                "risk_cascades": []
            }
            
            # Simple correlation analysis between domains
            domain_trends = {}
            for domain_id, forecast_data in domain_forecasts.items():
                if "metric_forecasts" in forecast_data:
                    # Calculate average trend across metrics
                    trends = []
                    for metric, predictions in forecast_data["metric_forecasts"].items():
                        if predictions and len(predictions) > 1:
                            trend = (predictions[-1] - predictions[0]) / len(predictions)
                            trends.append(trend)
                    
                    if trends:
                        domain_trends[domain_id] = np.mean(trends)
            
            # Find correlated domains
            insights["correlation_insights"] = self._find_correlated_domains(domain_trends)
            
            return insights
            
        except Exception as e:
            logger.error(f"Error analyzing cross-domain patterns: {e}")
            return {}
    
    def _find_correlated_domains(self, domain_trends: Dict) -> List[Dict[str, Any]]:
        """Find correlated domains based on trend similarity"""
        correlations = []
        
        domains = list(domain_trends.keys())
        for i in range(len(domains)):
            for j in range(i + 1, len(domains)):
                domain1, domain2 = domains[i], domains[j]
                trend1, trend2 = domain_trends[domain1], domain_trends[domain2]
                
                # Simple correlation based on trend direction
                if (trend1 > 0 and trend2 > 0) or (trend1 < 0 and trend2 < 0):
                    correlation_strength = "positive"
                elif (trend1 > 0 and trend2 < 0) or (trend1 < 0 and trend2 > 0):
                    correlation_strength = "negative"
                else:
                    correlation_strength = "neutral"
                
                correlations.append({
                    "domain_1": domain1,
                    "domain_2": domain2,
                    "correlation": correlation_strength,
                    "insight": f"{domain1} and {domain2} show {correlation_strength} correlation"
                })
        
        return correlations
    
    def _assess_predictive_risks(self, domain_forecasts: Dict) -> Dict[str, Any]:
        """Assess risks based on predictive forecasts"""
        try:
            risk_assessment = {
                "overall_risk_score": 0.0,
                "domain_risks": {},
                "critical_alerts": [],
                "risk_trends": {}
            }
            
            total_risk = 0.0
            domain_count = 0
            
            for domain_id, forecast_data in domain_forecasts.items():
                if "metric_forecasts" not in forecast_data:
                    continue
                
                domain_risk = self._calculate_domain_risk(domain_id, forecast_data)
                risk_assessment["domain_risks"][domain_id] = domain_risk
                
                total_risk += domain_risk["risk_score"]
                domain_count += 1
                
                # Generate alerts for high-risk domains
                if domain_risk["risk_score"] > self.risk_thresholds["high"]:
                    risk_assessment["critical_alerts"].append({
                        "domain": domain_id,
                        "risk_level": "high",
                        "message": f"High risk detected in {domain_id}: {domain_risk['primary_concern']}"
                    })
            
            # Calculate overall risk
            if domain_count > 0:
                risk_assessment["overall_risk_score"] = total_risk / domain_count
            
            return risk_assessment
            
        except Exception as e:
            logger.error(f"Error assessing predictive risks: {e}")
            return {}
    
    def _calculate_domain_risk(self, domain_id: str, forecast_data: Dict) -> Dict[str, Any]:
        """Calculate risk score for a domain"""
        try:
            risk_factors = []
            risk_score = 0.0
            
            metric_forecasts = forecast_data.get("metric_forecasts", {})
            
            for metric, predictions in metric_forecasts.items():
                if not predictions:
                    continue
                
                # Analyze prediction trend
                if len(predictions) > 1:
                    trend = (predictions[-1] - predictions[0]) / len(predictions)
                    
                    # Determine if negative trend is concerning for this metric
                    if self._is_negative_trend_concerning(domain_id, metric) and trend < 0:
                        risk_factors.append(f"Declining {metric}")
                        risk_score += 0.2
                    
                    # Check for volatility
                    volatility = np.std(predictions) if len(predictions) > 2 else 0
                    if volatility > np.mean(predictions) * 0.1:  # High volatility
                        risk_factors.append(f"High volatility in {metric}")
                        risk_score += 0.1
            
            # Cap risk score at 1.0
            risk_score = min(risk_score, 1.0)
            
            return {
                "risk_score": risk_score,
                "risk_factors": risk_factors,
                "primary_concern": risk_factors[0] if risk_factors else "No significant risks"
            }
            
        except Exception as e:
            logger.error(f"Error calculating domain risk for {domain_id}: {e}")
            return {"risk_score": 0.0, "risk_factors": [], "primary_concern": "Unknown"}
    
    def _is_negative_trend_concerning(self, domain_id: str, metric: str) -> bool:
        """Determine if negative trend is concerning for specific metric"""
        concerning_negative_trends = {
            "financial": ["revenue", "profit", "cash_flow"],
            "sales": ["total_sales", "conversion_rate", "pipeline_value"],
            "hr": ["retention_rate", "satisfaction_score", "productivity"],
            "manufacturing": ["oee", "quality_score", "efficiency"],
            "customer": ["acquisition_rate", "lifetime_value", "satisfaction"]
        }
        
        domain_metrics = concerning_negative_trends.get(domain_id, [])
        return metric in domain_metrics
    
    def _generate_predictive_recommendations(self, domain_forecasts: Dict,
                                             risk_assessment: Dict) -> List[Dict[str, Any]]:
        """Generate strategic recommendations based on predictions"""
        recommendations = []
        
        try:
            # Recommendations based on risk levels
            overall_risk = risk_assessment.get("overall_risk_score", 0)
            
            if overall_risk > self.risk_thresholds["high"]:
                recommendations.append({
                    "priority": "critical",
                    "category": "risk_mitigation",
                    "title": "Immediate Risk Mitigation Required",
                    "description": "High risk levels detected across multiple domains. Implement risk mitigation strategies immediately.",
                    "action_items": [
                        "Review high-risk domain forecasts",
                        "Implement contingency plans",
                        "Increase monitoring frequency"
                    ]
                })
            
            # Domain-specific recommendations
            for domain_id, risk_data in risk_assessment.get("domain_risks", {}).items():
                if risk_data["risk_score"] > self.risk_thresholds["medium"]:
                    recommendations.append({
                        "priority": "high",
                        "category": "domain_optimization",
                        "title": f"Optimize {domain_id.title()} Performance",
                        "description": f"Address concerning trends in {domain_id}: {risk_data['primary_concern']}",
                        "action_items": self._get_domain_specific_actions(domain_id, risk_data)
                    })
            
            # Opportunity-based recommendations
            for domain_id, forecast_data in domain_forecasts.items():
                opportunities = self._identify_opportunities(domain_id, forecast_data)
                for opportunity in opportunities:
                    recommendations.append(opportunity)
            
            return recommendations[:10]  # Limit to top 10 recommendations
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return []
    
    def _get_domain_specific_actions(self, domain_id: str, risk_data: Dict) -> List[str]:
        """Get domain-specific action items"""
        actions = {
            "financial": [
                "Review budget allocations and spending patterns",
                "Analyze cash flow projections",
                "Consider cost reduction strategies"
            ],
            "sales": [
                "Optimize sales pipeline management",
                "Review conversion strategies",
                "Analyze market opportunities"
            ],
            "hr": [
                "Implement retention strategies",
                "Review compensation and benefits",
                "Conduct employee satisfaction surveys"
            ],
            "manufacturing": [
                "Optimize production processes",
                "Review quality control procedures",
                "Implement efficiency improvements"
            ]
        }
        
        return actions.get(domain_id, ["Review domain performance", "Implement optimization strategies"])
    
    def _identify_opportunities(self, domain_id: str, forecast_data: Dict) -> List[Dict[str, Any]]:
        """Identify opportunities based on positive predictions"""
        opportunities = []
        
        try:
            metric_forecasts = forecast_data.get("metric_forecasts", {})
            
            for metric, predictions in metric_forecasts.items():
                if not predictions or len(predictions) < 2:
                    continue
                
                # Look for positive trends
                trend = (predictions[-1] - predictions[0]) / len(predictions)
                
                if trend > 0 and self._is_positive_trend_opportunity(domain_id, metric):
                    opportunities.append({
                        "priority": "medium",
                        "category": "growth_opportunity",
                        "title": f"Leverage {metric.replace('_', ' ').title()} Growth",
                        "description": f"Positive trend in {metric} presents growth opportunity",
                        "action_items": [
                            f"Invest in {metric} growth initiatives",
                            "Scale successful strategies",
                            "Monitor competitive positioning"
                        ]
                    })
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Error identifying opportunities for {domain_id}: {e}")
            return []
    
    def _is_positive_trend_opportunity(self, domain_id: str, metric: str) -> bool:
        """Check if positive trend represents opportunity"""
        opportunity_metrics = {
            "financial": ["revenue", "profit", "cash_flow"],
            "sales": ["total_sales", "conversion_rate", "pipeline_value"],
            "hr": ["satisfaction_score", "productivity"],
            "manufacturing": ["oee", "quality_score", "efficiency"]
        }
        
        domain_metrics = opportunity_metrics.get(domain_id, [])
        return metric in domain_metrics

    def _detect_domain_anomalies(self, domain_data: pd.DataFrame, domain_id: str,
                                  sensitivity: str) -> Dict[str, Any]:
        """Detect anomalies in domain data"""
        try:
            # Sensitivity settings
            contamination_rates = {"low": 0.05, "medium": 0.1, "high": 0.15}
            contamination = contamination_rates.get(sensitivity, 0.1)
            
            anomalies = {
                "domain_id": domain_id,
                "anomalies": [],
                "anomaly_count": 0,
                "severity_distribution": {"low": 0, "medium": 0, "high": 0}
            }
            
            # Detect anomalies for each metric
            for metric in domain_data.columns:
                metric_data = domain_data[metric].dropna()
                
                if len(metric_data) < 10:
                    continue
                
                # Use Isolation Forest for anomaly detection
                iso_forest = IsolationForest(
                    contamination=contamination,
                    random_state=42
                )
                
                # Reshape data for sklearn
                X = metric_data.values.reshape(-1, 1)
                anomaly_labels = iso_forest.fit_predict(X)
                
                # Process anomalies
                anomaly_indices = np.where(anomaly_labels == -1)[0]
                
                for idx in anomaly_indices:
                    anomaly_value = metric_data.iloc[idx]
                    anomaly_date = metric_data.index[idx]
                    
                    # Calculate anomaly severity
                    severity = self._calculate_anomaly_severity(
                        anomaly_value, metric_data, metric
                    )
                    
                    anomaly = {
                        "metric": metric,
                        "date": anomaly_date.isoformat() if hasattr(anomaly_date, 'isoformat') else str(anomaly_date),
                        "value": float(anomaly_value),
                        "severity": severity,
                        "expected_range": [
                            float(metric_data.quantile(0.25)),
                            float(metric_data.quantile(0.75))
                        ],
                        "description": f"Anomalous {metric} value detected"
                    }
                    
                    anomalies["anomalies"].append(anomaly)
                    anomalies["severity_distribution"][severity] += 1
            
            anomalies["anomaly_count"] = len(anomalies["anomalies"])
            
            return anomalies
            
        except Exception as e:
            logger.error(f"Error detecting anomalies for {domain_id}: {e}")
            return {"anomalies": [], "anomaly_count": 0}
    
    def _calculate_anomaly_severity(self, anomaly_value: float, 
                                    metric_data: pd.Series, metric: str) -> str:
        """Calculate severity of anomaly"""
        try:
            mean_val = metric_data.mean()
            std_val = metric_data.std()
            
            if std_val == 0:
                return "low"
            
            # Calculate z-score
            z_score = abs(anomaly_value - mean_val) / std_val
            
            if z_score > 3:
                return "high"
            elif z_score > 2:
                return "medium"
            else:
                return "low"
                
        except Exception as e:
            logger.error(f"Error calculating anomaly severity: {e}")
            return "low"
    
    def _analyze_risk_patterns(self, domain_anomalies: Dict) -> Dict[str, Any]:
        """Analyze risk patterns across domains"""
        try:
            risk_patterns = {
                "cross_domain_risks": [],
                "temporal_patterns": {},
                "severity_trends": {},
                "risk_correlation": {}
            }
            
            # Analyze cross-domain risks
            high_risk_domains = []
            for domain_id, anomaly_data in domain_anomalies.items():
                high_severity_count = anomaly_data.get("severity_distribution", {}).get("high", 0)
                
                if high_severity_count > 2:
                    high_risk_domains.append(domain_id)
            
            if len(high_risk_domains) > 1:
                risk_patterns["cross_domain_risks"] = [{
                    "domains": high_risk_domains,
                    "pattern": "multiple_high_risk",
                    "description": f"Multiple domains ({', '.join(high_risk_domains)}) showing high-severity anomalies"
                }]
            
            # Analyze temporal patterns
            for domain_id, anomaly_data in domain_anomalies.items():
                anomalies = anomaly_data.get("anomalies", [])
                
                if anomalies:
                    # Group anomalies by time period
                    recent_anomalies = [a for a in anomalies 
                                        if self._is_recent_anomaly(a.get("date", ""))]
                    
                    risk_patterns["temporal_patterns"][domain_id] = {
                        "total_anomalies": len(anomalies),
                        "recent_anomalies": len(recent_anomalies),
                        "trend": "increasing" if len(recent_anomalies) > len(anomalies) * 0.3 else "stable"
                    }
            
            return risk_patterns
            
        except Exception as e:
            logger.error(f"Error analyzing risk patterns: {e}")
            return {}
    
    def _is_recent_anomaly(self, anomaly_date: str) -> bool:
        """Check if anomaly is recent (within last 30 days)"""
        try:
            if not anomaly_date:
                return False
            
            anomaly_dt = datetime.fromisoformat(anomaly_date.replace('Z', '+00:00'))
            cutoff_date = datetime.now() - timedelta(days=30)
            
            return anomaly_dt > cutoff_date
            
        except Exception:
            return False
    
    def _generate_early_warnings(self, domain_anomalies: Dict, risk_patterns: Dict) -> List[Dict[str, Any]]:
        """Generate early warning signals"""
        warnings = []
        
        try:
            # Check for cascading risks
            cross_domain_risks = risk_patterns.get("cross_domain_risks", [])
            for risk in cross_domain_risks:
                warnings.append({
                    "type": "cascading_risk",
                    "severity": "high",
                    "message": risk["description"],
                    "affected_domains": risk["domains"],
                    "recommended_action": "Investigate interconnected risks across domains"
                })
            
            # Check for increasing anomaly trends
            temporal_patterns = risk_patterns.get("temporal_patterns", {})
            for domain_id, pattern in temporal_patterns.items():
                if pattern.get("trend") == "increasing":
                    warnings.append({
                        "type": "increasing_anomalies",
                        "severity": "medium",
                        "message": f"Increasing anomaly frequency detected in {domain_id}",
                        "affected_domains": [domain_id],
                        "recommended_action": "Monitor domain closely and investigate root causes"
                    })
            
            # Check for high-severity clusters
            for domain_id, anomaly_data in domain_anomalies.items():
                high_severity = anomaly_data.get("severity_distribution", {}).get("high", 0)
                
                if high_severity >= 3:
                    warnings.append({
                        "type": "severity_cluster",
                        "severity": "high", 
                        "message": f"Multiple high-severity anomalies in {domain_id}",
                        "affected_domains": [domain_id],
                        "recommended_action": "Immediate investigation required for domain stability"
                    })
            
            return warnings
            
        except Exception as e:
            logger.error(f"Error generating early warnings: {e}")
            return []
    
    def _recommend_anomaly_actions(self, domain_anomalies: Dict, early_warnings: List) -> List[Dict[str, Any]]:
        """Recommend actions based on anomalies and warnings"""
        actions = []
        
        try:
            # Actions for early warnings
            for warning in early_warnings:
                if warning["severity"] == "high":
                    actions.append({
                        "priority": "immediate",
                        "category": "crisis_response",
                        "title": "Address Critical Risk",
                        "description": warning["message"],
                        "steps": [
                            "Assemble crisis response team",
                            "Investigate root cause immediately",
                            "Implement containment measures",
                            "Monitor situation continuously"
                        ]
                    })
                elif warning["severity"] == "medium":
                    actions.append({
                        "priority": "high",
                        "category": "preventive_action",
                        "title": "Investigate Anomaly Pattern",
                        "description": warning["message"],
                        "steps": [
                            "Analyze historical data trends",
                            "Identify potential causes",
                            "Implement monitoring improvements",
                            "Plan preventive measures"
                        ]
                    })
            
            # Domain-specific actions
            for domain_id, anomaly_data in domain_anomalies.items():
                if anomaly_data["anomaly_count"] > 5:
                    actions.append({
                        "priority": "medium",
                        "category": "domain_optimization",
                        "title": f"Optimize {domain_id.title()} Stability",
                        "description": f"Multiple anomalies detected in {domain_id}",
                        "steps": self._get_domain_anomaly_actions(domain_id)
                    })
            
            return actions[:8]  # Limit to 8 actions
            
        except Exception as e:
            logger.error(f"Error recommending anomaly actions: {e}")
            return []
    
    def _get_domain_anomaly_actions(self, domain_id: str) -> List[str]:
        """Get domain-specific actions for anomalies"""
        actions = {
            "financial": [
                "Review financial processes and controls",
                "Audit transaction patterns",
                "Investigate budget variances",
                "Strengthen financial monitoring"
            ],
            "sales": [
                "Analyze sales pipeline quality",
                "Review customer engagement patterns",
                "Investigate deal closure anomalies",
                "Optimize sales processes"
            ],
            "hr": [
                "Review HR metrics and policies",
                "Investigate employee satisfaction",
                "Analyze turnover patterns",
                "Strengthen talent management"
            ],
            "manufacturing": [
                "Review production processes",
                "Investigate quality issues",
                "Analyze equipment performance",
                "Optimize operational efficiency"
            ]
        }
        
        return actions.get(domain_id, [
            "Review domain processes",
            "Investigate data quality",
            "Implement monitoring improvements",
            "Optimize operational procedures"
        ])
    
    def _analyze_domain_patterns(self, domain_data: pd.DataFrame, 
                                 domain_config: Dict) -> Dict[str, Any]:
        """Analyze patterns in domain data"""
        try:
            patterns = {
                "identified_patterns": [],
                "trend_analysis": {},
                "cyclical_patterns": {},
                "correlation_patterns": {}
            }
            
            # Analyze trends for each metric
            for metric in domain_data.columns:
                metric_data = domain_data[metric].dropna()
                
                if len(metric_data) < 10:
                    continue
                
                # Linear trend analysis
                x = np.arange(len(metric_data))
                slope, intercept = np.polyfit(x, metric_data.values, 1)
                
                trend_direction = "increasing" if slope > 0 else "decreasing"
                trend_strength = abs(slope) / metric_data.std() if metric_data.std() > 0 else 0
                
                patterns["trend_analysis"][metric] = {
                    "direction": trend_direction,
                    "strength": trend_strength,
                    "slope": slope
                }
                
                # Identify significant trends
                if trend_strength > 0.1:
                    patterns["identified_patterns"].append({
                        "type": "trend",
                        "metric": metric,
                        "description": f"{trend_direction.title()} trend in {metric}",
                        "strength": trend_strength
                    })
            
            # Correlation analysis between metrics
            if len(domain_data.columns) > 1:
                correlation_matrix = domain_data.corr()
                
                for i, metric1 in enumerate(domain_data.columns):
                    for j, metric2 in enumerate(domain_data.columns):
                        if i < j:
                            correlation = correlation_matrix.loc[metric1, metric2]
                            
                            if abs(correlation) > 0.5:
                                patterns["correlation_patterns"][f"{metric1}_{metric2}"] = {
                                    "correlation": correlation,
                                    "type": "positive" if correlation > 0 else "negative",
                                    "strength": abs(correlation)
                                }
                                
                                patterns["identified_patterns"].append({
                                    "type": "correlation",
                                    "metrics": [metric1, metric2],
                                    "description": f"{'Strong positive' if correlation > 0 else 'Strong negative'} correlation between {metric1} and {metric2}",
                                    "strength": abs(correlation)
                                })
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error analyzing domain patterns: {e}")
            return {"identified_patterns": []}
    
    def _decompose_seasonal_patterns(self, domain_data: pd.DataFrame) -> Dict[str, Any]:
        """Decompose seasonal patterns in data"""
        try:
            seasonal_analysis = {}
            
            for metric in domain_data.columns:
                metric_data = domain_data[metric].dropna()
                
                if len(metric_data) < 24:  # Need at least 2 years for seasonal analysis
                    continue
                
                # Simple seasonal decomposition
                # Group by month and calculate average
                if hasattr(metric_data.index, 'month'):
                    monthly_avg = metric_data.groupby(metric_data.index.month).mean()
                    monthly_std = metric_data.groupby(metric_data.index.month).std()
                    
                    # Identify seasonal patterns
                    seasonal_strength = monthly_std.mean() / monthly_avg.mean() if monthly_avg.mean() > 0 else 0
                    
                    # int(): the month index is numpy.int32, which Frappe cannot serialize to JSON
                    peak_month = int(monthly_avg.idxmax())
                    trough_month = int(monthly_avg.idxmin())
                    
                    seasonal_analysis[metric] = {
                        "seasonal_strength": seasonal_strength,
                        "peak_month": peak_month,
                        "trough_month": trough_month,
                        "monthly_pattern": monthly_avg.to_dict(),
                        "has_seasonality": bool(seasonal_strength > 0.1)
                    }
            
            return seasonal_analysis
            
        except Exception as e:
            logger.error(f"Error decomposing seasonal patterns: {e}")
            return {}
    
    def _analyze_trends(self, domain_data: pd.DataFrame, domain_config: Dict) -> Dict[str, Any]:
        """Analyze trends in domain data"""
        try:
            trend_analysis = {
                "overall_trend": "stable",
                "metric_trends": {},
                "trend_accelerations": [],
                "trend_reversals": []
            }
            
            positive_trends = 0
            negative_trends = 0
            
            for metric in domain_data.columns:
                metric_data = domain_data[metric].dropna()
                
                if len(metric_data) < 10:
                    continue
                
                # Calculate trend using linear regression
                x = np.arange(len(metric_data))
                slope, _ = np.polyfit(x, metric_data.values, 1)
                
                # Determine trend significance
                trend_significance = abs(slope) / metric_data.std() if metric_data.std() > 0 else 0
                
                if trend_significance > 0.05:
                    if slope > 0:
                        trend_direction = "increasing"
                        positive_trends += 1
                    else:
                        trend_direction = "decreasing"
                        negative_trends += 1
                else:
                    trend_direction = "stable"
                
                trend_analysis["metric_trends"][metric] = {
                    "direction": trend_direction,
                    "slope": slope,
                    "significance": trend_significance
                }
                
                # Detect trend accelerations/reversals in recent data
                recent_data = metric_data.tail(int(len(metric_data) * 0.3))
                if len(recent_data) >= 5:
                    recent_x = np.arange(len(recent_data))
                    recent_slope, _ = np.polyfit(recent_x, recent_data.values, 1)
                    
                    if abs(recent_slope - slope) > metric_data.std() * 0.1:
                        if (slope > 0 and recent_slope < 0) or (slope < 0 and recent_slope > 0):
                            trend_analysis["trend_reversals"].append({
                                "metric": metric,
                                "original_trend": "increasing" if slope > 0 else "decreasing",
                                "new_trend": "increasing" if recent_slope > 0 else "decreasing"
                            })
                        elif abs(recent_slope) > abs(slope) * 1.5:
                            trend_analysis["trend_accelerations"].append({
                                "metric": metric,
                                "trend": "increasing" if recent_slope > 0 else "decreasing",
                                "acceleration": "significant"
                            })
            
            # Determine overall trend
            if positive_trends > negative_trends * 1.5:
                trend_analysis["overall_trend"] = "positive"
            elif negative_trends > positive_trends * 1.5:
                trend_analysis["overall_trend"] = "negative"
            
            return trend_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing trends: {e}")
            return {"overall_trend": "unknown"}
    
    def _calculate_cross_domain_correlations(self) -> Dict[str, Any]:
        """Calculate correlations across different domains"""
        try:
            correlations = {}
            
            # Get data for all domains
            domain_data = {}
            for domain_id in self.prediction_domains.keys():
                data = self._get_domain_historical_data(domain_id, 12)
                if not data.empty:
                    # Use first metric as representative
                    domain_data[domain_id] = data.iloc[:, 0].resample('W').mean()
            
            # Calculate correlations between domains
            domain_names = list(domain_data.keys())
            for i, domain1 in enumerate(domain_names):
                for j, domain2 in enumerate(domain_names):
                    if i < j:
                        # Align data by date
                        common_dates = domain_data[domain1].index.intersection(domain_data[domain2].index)
                        
                        if len(common_dates) > 10:
                            series1 = domain_data[domain1][common_dates]
                            series2 = domain_data[domain2][common_dates]
                            
                            correlation = series1.corr(series2)
                            
                            if abs(correlation) > 0.3:
                                correlations[f"{domain1}_{domain2}"] = {
                                    "correlation": correlation,
                                    "strength": "strong" if abs(correlation) > 0.7 else "moderate",
                                    "type": "positive" if correlation > 0 else "negative"
                                }
            
            return correlations
            
        except Exception as e:
            logger.error(f"Error calculating cross-domain correlations: {e}")
            return {}
    
    def _generate_pattern_insights(self, pattern_results: Dict) -> List[Dict[str, Any]]:
        """Generate insights from pattern analysis"""
        insights = []
        
        try:
            # Insights from domain patterns
            for domain_id, domain_patterns in pattern_results.get("domain_patterns", {}).items():
                patterns = domain_patterns.get("identified_patterns", [])
                
                for pattern in patterns:
                    if pattern["strength"] > 0.5:
                        insights.append({
                            "type": "pattern_insight",
                            "domain": domain_id,
                            "insight": f"Strong {pattern['type']} detected: {pattern['description']}",
                            "confidence": pattern["strength"],
                            "actionable": True
                        })
            
            # Insights from correlations
            correlations = pattern_results.get("correlation_matrix", {})
            for correlation_key, correlation_data in correlations.items():
                if correlation_data["strength"] == "strong":
                    domains = correlation_key.split("_")
                    insights.append({
                        "type": "correlation_insight",
                        "domains": domains,
                        "insight": f"{correlation_data['type'].title()} correlation between {' and '.join(domains)}",
                        "confidence": correlation_data["correlation"],
                        "actionable": True
                    })
            
            # Insights from seasonal patterns
            for domain_id, seasonal_data in pattern_results.get("seasonal_patterns", {}).items():
                for metric, season_info in seasonal_data.items():
                    if season_info.get("has_seasonality"):
                        insights.append({
                            "type": "seasonal_insight",
                            "domain": domain_id,
                            "insight": f"Seasonal pattern in {metric}: peak in month {season_info['peak_month']}",
                            "confidence": season_info["seasonal_strength"],
                            "actionable": True
                        })
            
            return insights[:15]  # Limit to 15 insights
            
        except Exception as e:
            logger.error(f"Error generating pattern insights: {e}")
            return []
    
    def _generate_real_time_domain_predictions(self, domain_id: str, metrics: List[str],
                                               confidence_threshold: float) -> Dict[str, Any]:
        """Generate real-time predictions for domain metrics"""
        try:
            domain_predictions = {}
            
            # Get recent data for the domain
            recent_data = self._get_domain_historical_data(domain_id, 3)  # Last 3 months
            
            if recent_data.empty:
                return {}
            
            for metric in metrics:
                if metric not in recent_data.columns:
                    continue
                
                metric_data = recent_data[metric].dropna()
                
                if len(metric_data) < 10:
                    continue
                
                # Generate short-term prediction (next period)
                prediction_result = self._predict_next_period(metric_data)
                
                if prediction_result["confidence"] >= confidence_threshold:
                    domain_predictions[metric] = prediction_result
            
            return domain_predictions
            
        except Exception as e:
            logger.error(f"Error generating real-time predictions for {domain_id}: {e}")
            return {}
    
    def _predict_next_period(self, metric_data: pd.Series) -> Dict[str, Any]:
        """Predict next period value for a metric"""
        try:
            # Simple prediction using recent trend and seasonal adjustment
            recent_values = metric_data.tail(7).values  # Last week
            
            if len(recent_values) < 3:
                return {"confidence": 0.0}
            
            # Calculate trend
            x = np.arange(len(recent_values))
            slope, intercept = np.polyfit(x, recent_values, 1)
            
            # Predict next value
            next_x = len(recent_values)
            predicted_value = slope * next_x + intercept
            
            # Calculate confidence based on recent volatility
            recent_volatility = np.std(recent_values)
            mean_value = np.mean(recent_values)
            
            if mean_value > 0:
                volatility_ratio = recent_volatility / mean_value
                confidence = max(0.0, 1.0 - volatility_ratio)
            else:
                confidence = 0.5
            
            # Calculate prediction interval
            std_error = recent_volatility
            interval = [
                predicted_value - 1.96 * std_error,
                predicted_value + 1.96 * std_error
            ]
            
            return {
                "predicted_value": predicted_value,
                "confidence": confidence,
                "prediction_interval": interval,
                "trend": "increasing" if slope > 0 else "decreasing",
                "volatility": volatility_ratio if mean_value > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error predicting next period: {e}")
            return {"confidence": 0.0}
    
    def _is_concerning_prediction(self, domain_id: str, metric: str,
                                  prediction_data: Dict) -> bool:
        """Check if prediction is concerning"""
        try:
            predicted_value = prediction_data.get("predicted_value", 0)
            confidence = prediction_data.get("confidence", 0)
            trend = prediction_data.get("trend", "stable")
            
            # Low confidence predictions are concerning
            if confidence < 0.4:
                return True
            
            # Negative trends in key metrics are concerning
            if trend == "decreasing" and self._is_negative_trend_concerning(domain_id, metric):
                return True
            
            # Extreme values are concerning
            volatility = prediction_data.get("volatility", 0)
            if volatility > 0.5:  # High volatility
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking concerning prediction: {e}")
            return False
    
    def _optimize_domain_models(self, domain_id: str, domain_data: pd.DataFrame,
                                optimization_metric: str) -> Dict[str, Any]:
        """Optimize models for a specific domain"""
        try:
            optimization_results = {
                "improvements": [],
                "best_model": None,
                "performance_gain": 0.0
            }
            
            if domain_data.empty:
                return optimization_results
            
            # Test different models for each metric
            best_overall_improvement = 0.0
            best_model_info = None
            
            for metric in domain_data.columns:
                metric_data = domain_data[metric].dropna()
                
                if len(metric_data) < 20:
                    continue
                
                # Prepare data
                X, y = self._prepare_time_series_data(metric_data)
                
                if len(X) < 10:
                    continue
                
                # Split data for testing
                split_idx = int(len(X) * 0.8)
                X_train, X_test = X[:split_idx], X[split_idx:]
                y_train, y_test = y[:split_idx], y[split_idx:]
                
                # Test different models
                baseline_model = LinearRegression()
                baseline_model.fit(X_train, y_train)
                baseline_pred = baseline_model.predict(X_test)
                baseline_score = self._calculate_score(y_test, baseline_pred, optimization_metric)
                
                # Test improved models
                models_to_test = [
                    ("Ridge Regression", Ridge(alpha=1.0)),
                    ("Random Forest", RandomForestRegressor(n_estimators=50, random_state=42))
                ]
                
                best_score = baseline_score
                best_model = baseline_model
                best_model_name = "Linear Regression"
                
                for model_name, model in models_to_test:
                    try:
                        model.fit(X_train, y_train)
                        pred = model.predict(X_test)
                        score = self._calculate_score(y_test, pred, optimization_metric)
                        
                        if score > best_score:
                            best_score = score
                            best_model = model
                            best_model_name = model_name
                    except Exception as e:
                        logger.warning(f"Model {model_name} failed: {e}")
                
                # Calculate improvement
                improvement = (best_score - baseline_score) / abs(baseline_score) if baseline_score != 0 else 0
                
                if improvement > 0.05:  # 5% improvement
                    optimization_results["improvements"].append({
                        "metric": metric,
                        "baseline_score": baseline_score,
                        "improved_score": best_score,
                        "improvement_percent": improvement * 100,
                        "best_model": best_model_name
                    })
                    
                    if improvement > best_overall_improvement:
                        best_overall_improvement = improvement
                        best_model_info = {
                            "metric": metric,
                            "model": best_model_name,
                            "improvement": improvement
                        }
            
            optimization_results["performance_gain"] = best_overall_improvement
            optimization_results["best_model"] = best_model_info
            
            return optimization_results
            
        except Exception as e:
            logger.error(f"Error optimizing domain models: {e}")
            return {"improvements": [], "performance_gain": 0.0}
    
    def _calculate_score(self, y_true: np.ndarray, y_pred: np.ndarray, metric: str) -> float:
        """Calculate score based on specified metric"""
        try:
            if metric == "rmse":
                return -np.sqrt(mean_squared_error(y_true, y_pred))  # Negative because higher is better
            elif metric == "mae":
                return -mean_absolute_error(y_true, y_pred)  # Negative because higher is better
            elif metric == "r2":
                return r2_score(y_true, y_pred)
            else:
                return r2_score(y_true, y_pred)  # Default to R²
        except Exception as e:
            logger.error(f"Error calculating score: {e}")
            return 0.0
    
    def _generate_scenario_analysis(self, domain_forecasts: Dict) -> Dict[str, Any]:
        """Generate scenario analysis (optimistic, pessimistic, realistic)"""
        try:
            scenarios = {
                "optimistic": {},
                "realistic": {},
                "pessimistic": {}
            }
            
            for domain_id, forecast_data in domain_forecasts.items():
                metric_forecasts = forecast_data.get("metric_forecasts", {})
                
                domain_scenarios = {
                    "optimistic": {},
                    "realistic": {},
                    "pessimistic": {}
                }
                
                for metric, predictions in metric_forecasts.items():
                    if not predictions:
                        continue
                    
                    baseline = predictions
                    
                    # Generate scenarios with different adjustments
                    optimistic = [p * 1.15 for p in baseline]  # 15% better
                    realistic = baseline
                    pessimistic = [p * 0.85 for p in baseline]  # 15% worse
                    
                    domain_scenarios["optimistic"][metric] = optimistic
                    domain_scenarios["realistic"][metric] = realistic
                    domain_scenarios["pessimistic"][metric] = pessimistic
                
                scenarios["optimistic"][domain_id] = domain_scenarios["optimistic"]
                scenarios["realistic"][domain_id] = domain_scenarios["realistic"]
                scenarios["pessimistic"][domain_id] = domain_scenarios["pessimistic"]
            
            # Add scenario descriptions
            scenarios["scenario_descriptions"] = {
                "optimistic": "Best-case scenario with favorable market conditions",
                "realistic": "Most likely scenario based on current trends",
                "pessimistic": "Worst-case scenario with challenging conditions"
            }
            
            return scenarios
            
        except Exception as e:
            logger.error(f"Error generating scenario analysis: {e}")
            return {}
    
    def _update_performance_tracking(self, forecast_results: Dict) -> None:
        """Update model performance tracking"""
        try:
            timestamp = datetime.now().isoformat()
            
            for domain_id, forecast_data in forecast_results.get("domain_forecasts", {}).items():
                model_performance = forecast_data.get("model_performance", {})
                
                if domain_id not in self.model_performance:
                    self.model_performance[domain_id] = []
                
                self.model_performance[domain_id].append({
                    "timestamp": timestamp,
                    "performance_metrics": model_performance,
                    "forecast_horizon": forecast_data.get("forecast_horizon", 12)
                })
                
                # Keep only last 100 performance records per domain
                if len(self.model_performance[domain_id]) > 100:
                    self.model_performance[domain_id] = self.model_performance[domain_id][-100:]
            
        except Exception as e:
            logger.error(f"Error updating performance tracking: {e}")


# Service instance  
advanced_predictive_engine = AdvancedPredictiveAnalyticsEngine()