# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Sales Forecasting using Time Series Analysis
Supports Prophet, ARIMA, and Exponential Smoothing methods
"""

import frappe
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from insights.ml.base import BaseMLModel, get_date_range


class SalesForecasting(BaseMLModel):
    """
    Time Series Sales Forecasting
    
    Methods:
    - Prophet: Best for data with strong seasonality
    - Exponential Smoothing: Good for trending data
    - Simple Moving Average: Baseline method
    
    Forecasts:
    - Daily sales
    - Weekly sales
    - Monthly sales
    - By customer group
    - By item group
    """
    
    def __init__(self, method: str = "auto"):
        super().__init__()
        self.model_name = "SalesForecasting"
        self.method = method
        self.prophet_available = self._check_prophet()
        
    def _check_prophet(self) -> bool:
        """Check if Prophet is available"""
        try:
            from prophet import Prophet
            return True
        except ImportError:
            return False
    
    def _get_daily_sales(self) -> pd.DataFrame:
        """Get daily sales data (excluding returns)"""
        query = """
            SELECT 
                posting_date as ds,
                SUM(CASE WHEN is_return = 0 THEN grand_total ELSE 0 END) as y,
                COUNT(CASE WHEN is_return = 0 THEN 1 END) as order_count
            FROM `tabSales Invoice`
            WHERE docstatus = 1
            GROUP BY posting_date
            HAVING y > 0
            ORDER BY posting_date
        """
        return self.get_training_data(query)
    
    def _get_sales_by_group(self, group_by: str) -> pd.DataFrame:
        """Get sales grouped by customer_group or item_group"""
        if group_by == "customer_group":
            query = """
                SELECT 
                    posting_date as ds,
                    c.customer_group as group_name,
                    SUM(si.grand_total) as y
                FROM `tabSales Invoice` si
                LEFT JOIN `tabCustomer` c ON si.customer = c.name
                WHERE si.docstatus = 1
                GROUP BY posting_date, c.customer_group
                ORDER BY posting_date, c.customer_group
            """
        else:  # item_group
            query = """
                SELECT 
                    si.posting_date as ds,
                    i.item_group as group_name,
                    SUM(sii.amount) as y
                FROM `tabSales Invoice Item` sii
                JOIN `tabSales Invoice` si ON sii.parent = si.name
                LEFT JOIN `tabItem` i ON sii.item_code = i.name
                WHERE si.docstatus = 1
                GROUP BY si.posting_date, i.item_group
                ORDER BY si.posting_date, i.item_group
            """
        return self.get_training_data(query)
    
    def _forecast_prophet(self, df: pd.DataFrame, periods: int = 30) -> Dict[str, Any]:
        """Forecast using Prophet with intelligent floor handling"""
        try:
            from prophet import Prophet
            
            # Prepare data
            df = df[['ds', 'y']].copy()
            df['ds'] = pd.to_datetime(df['ds'])
            
            # Calculate key statistics for floor handling
            historical_mean = df['y'].mean()
            historical_median = df['y'].median()
            historical_max = df['y'].max()
            
            # Use last 30 days average as a baseline (more recent/relevant)
            recent_30d_mean = df['y'].tail(30).mean() if len(df) >= 30 else historical_mean
            
            # Set minimum floor at 20% of recent average (sales unlikely to drop more than 80%)
            min_floor = max(recent_30d_mean * 0.2, historical_median * 0.1)
            df['floor'] = min_floor
            
            # Set cap based on historical max with buffer
            df['cap'] = historical_max * 1.5
            
            # Initialize model with logistic growth
            model = Prophet(
                growth='logistic',
                yearly_seasonality=True,
                weekly_seasonality=True,
                daily_seasonality=False,
                changepoint_prior_scale=0.05,  # Allow some trend flexibility
                seasonality_prior_scale=10.0,  # Strong seasonality
                changepoint_range=0.8  # Consider changepoints in first 80% of data
            )
            model.fit(df)
            
            # Make future dataframe with floor and cap
            future = model.make_future_dataframe(periods=periods)
            future['floor'] = min_floor
            future['cap'] = historical_max * 1.5
            
            # Predict
            forecast = model.predict(future)
            
            # Get forecast for future periods only
            future_forecast = forecast[forecast['ds'] > df['ds'].max()].copy()
            
            # Validate forecast quality BEFORE clipping - check if forecast drops too much
            raw_avg_forecast = future_forecast['yhat'].mean()
            raw_last_30_forecast = future_forecast['yhat'].tail(30).mean() if len(future_forecast) >= 30 else raw_avg_forecast
            
            # Also check how many values are below the floor (indicating model is predicting unrealistic values)
            below_floor_count = (future_forecast['yhat'] < min_floor).sum()
            below_floor_pct = below_floor_count / len(future_forecast) if len(future_forecast) > 0 else 0
            
            # If raw forecast is declining too much, fall back to day-of-week weighted average
            # Condition: avg < 70% of recent mean OR last 30 days < 50% of recent mean OR >50% of values below floor
            use_dow_fallback = (
                (raw_avg_forecast < recent_30d_mean * 0.7) or 
                (raw_last_30_forecast < recent_30d_mean * 0.5) or
                (below_floor_pct > 0.5)
            )
            
            # Apply clipping for values that will be returned
            future_forecast['yhat'] = future_forecast['yhat'].clip(lower=min_floor)
            future_forecast['yhat_lower'] = future_forecast['yhat_lower'].clip(lower=0)
            future_forecast['yhat_upper'] = future_forecast['yhat_upper'].clip(lower=min_floor)
            
            if use_dow_fallback:
                # Use weighted moving average with seasonality
                # Get day-of-week pattern from recent data
                df['dow'] = df['ds'].dt.dayofweek
                dow_pattern = df.groupby('dow')['y'].mean()
                
                # Generate forecast using recent average with day-of-week seasonality
                future_forecast['dow'] = pd.to_datetime(future_forecast['ds']).dt.dayofweek
                future_forecast['yhat'] = future_forecast['dow'].map(dow_pattern)
                
                # If dow_pattern is empty, fall back to recent average
                if future_forecast['yhat'].isna().any():
                    future_forecast['yhat'] = recent_30d_mean
                
                future_forecast['yhat_lower'] = future_forecast['yhat'] * 0.7
                future_forecast['yhat_upper'] = future_forecast['yhat'] * 1.3
                future_forecast = future_forecast.drop(columns=['dow'])
                method_name = "prophet_dow_adjusted"
            else:
                method_name = "prophet"
            
            return {
                "method": method_name,
                "forecast": future_forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].to_dict('records'),
                "model_components": {
                    "trend": forecast['trend'].tolist()[-periods:],
                    "weekly": forecast['weekly'].tolist()[-periods:] if 'weekly' in forecast else [],
                    "yearly": forecast['yearly'].tolist()[-periods:] if 'yearly' in forecast else []
                }
            }
        except Exception as e:
            frappe.log_error(f"Prophet forecast failed: {str(e)}", "Sales Forecasting")
            return None
    
    def _forecast_exponential_smoothing(self, df: pd.DataFrame, periods: int = 30) -> Dict[str, Any]:
        """Forecast using Exponential Smoothing"""
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            
            # Prepare data
            df = df[['ds', 'y']].copy()
            df['ds'] = pd.to_datetime(df['ds'])
            df = df.set_index('ds')
            df = df.asfreq('D', fill_value=0)
            
            # Fit model
            model = ExponentialSmoothing(
                df['y'],
                seasonal_periods=7,  # Weekly seasonality
                trend='add',
                seasonal='add'
            ).fit()
            
            # Forecast
            forecast = model.forecast(periods)
            
            # Create forecast dataframe
            future_dates = pd.date_range(
                start=df.index.max() + timedelta(days=1),
                periods=periods,
                freq='D'
            )
            
            forecast_df = pd.DataFrame({
                'ds': future_dates,
                'yhat': forecast.values,
                'yhat_lower': forecast.values * 0.9,  # Simple confidence interval
                'yhat_upper': forecast.values * 1.1
            })
            
            return {
                "method": "exponential_smoothing",
                "forecast": forecast_df.to_dict('records')
            }
        except Exception as e:
            frappe.log_error(f"Exponential smoothing failed: {str(e)}", "Sales Forecasting")
            return None
    
    def _forecast_moving_average(self, df: pd.DataFrame, periods: int = 30, window: int = 7) -> Dict[str, Any]:
        """Forecast using Simple Moving Average"""
        df = df[['ds', 'y']].copy()
        df['ds'] = pd.to_datetime(df['ds'])
        
        # Calculate moving average
        ma = df['y'].rolling(window=window).mean().iloc[-1]
        std = df['y'].rolling(window=window).std().iloc[-1]
        
        # Generate forecast
        future_dates = pd.date_range(
            start=df['ds'].max() + timedelta(days=1),
            periods=periods,
            freq='D'
        )
        
        # Add some trend based on recent data
        recent_trend = (df['y'].iloc[-1] - df['y'].iloc[-window]) / window if len(df) > window else 0
        
        forecast_values = []
        for i in range(periods):
            forecast_values.append(ma + recent_trend * i)
        
        forecast_df = pd.DataFrame({
            'ds': future_dates,
            'yhat': forecast_values,
            'yhat_lower': [v - 1.96 * std for v in forecast_values],
            'yhat_upper': [v + 1.96 * std for v in forecast_values]
        })
        
        return {
            "method": "moving_average",
            "forecast": forecast_df.to_dict('records'),
            "params": {"window": window, "base_ma": ma, "trend": recent_trend}
        }
    
    def train(self, periods: int = 30, group_by: str = None) -> Dict[str, Any]:
        """Train forecasting model and generate predictions"""
        # Get data
        if group_by:
            df = self._get_sales_by_group(group_by)
            return self._train_grouped(df, periods, group_by)
        else:
            df = self._get_daily_sales()
        
        if df.empty or len(df) < 14:  # Need at least 2 weeks of data
            return {
                "status": "error",
                "message": "Insufficient data for forecasting (need at least 14 days)"
            }
        
        # Select method
        forecast_result = None
        
        if self.method == "auto":
            # Try Prophet first, then fallback
            if self.prophet_available and len(df) >= 30:
                forecast_result = self._forecast_prophet(df, periods)
            
            if not forecast_result:
                forecast_result = self._forecast_exponential_smoothing(df, periods)
            
            if not forecast_result:
                forecast_result = self._forecast_moving_average(df, periods)
        
        elif self.method == "prophet":
            if not self.prophet_available:
                return {
                    "status": "error",
                    "message": "Prophet not installed. Run: pip install insights[ml]"
                }
            forecast_result = self._forecast_prophet(df, periods)
        
        elif self.method == "exponential_smoothing":
            forecast_result = self._forecast_exponential_smoothing(df, periods)
        
        else:
            forecast_result = self._forecast_moving_average(df, periods)
        
        if not forecast_result:
            forecast_result = self._forecast_moving_average(df, periods)
        
        # Calculate accuracy metrics on historical data
        metrics = self._calculate_metrics(df)
        
        # Prepare results
        results = {
            "status": "success",
            "forecast_date": datetime.now().isoformat(),
            "data_range": {
                "start": df['ds'].min().isoformat() if hasattr(df['ds'].min(), 'isoformat') else str(df['ds'].min()),
                "end": df['ds'].max().isoformat() if hasattr(df['ds'].max(), 'isoformat') else str(df['ds'].max()),
                "days": len(df)
            },
            "historical_summary": {
                "total_sales": float(df['y'].sum()),
                "avg_daily_sales": float(df['y'].mean()),
                "max_daily_sales": float(df['y'].max()),
                "min_daily_sales": float(df['y'].min())
            },
            "metrics": metrics,
            **forecast_result,
            "forecast_summary": self._summarize_forecast(forecast_result['forecast'])
        }
        
        # Cache results
        self.cache_results("sales_forecast", results, expires_in_hours=12)
        
        # Log training
        self.log_training({
            "method": forecast_result['method'],
            "periods": periods,
            "data_points": len(df),
            "metrics": metrics
        })
        
        return results
    
    def _train_grouped(self, df: pd.DataFrame, periods: int, group_by: str) -> Dict[str, Any]:
        """Train forecasts for each group"""
        groups = df['group_name'].dropna().unique()
        group_forecasts = {}
        
        for group in groups:
            group_df = df[df['group_name'] == group][['ds', 'y']].copy()
            
            if len(group_df) < 7:
                continue
            
            # Use simple moving average for grouped data
            forecast = self._forecast_moving_average(group_df, periods)
            group_forecasts[group] = {
                "forecast": forecast['forecast'],
                "historical_avg": float(group_df['y'].mean())
            }
        
        return {
            "status": "success",
            "group_by": group_by,
            "groups": group_forecasts
        }
    
    def _calculate_metrics(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate forecast accuracy metrics"""
        if len(df) < 14:
            return {}
        
        # Use last 7 days as test set
        train = df.iloc[:-7]
        test = df.iloc[-7:]
        
        # Simple forecast: average of training data
        pred = train['y'].mean()
        actual = test['y'].values
        
        # Calculate metrics
        mae = np.mean(np.abs(actual - pred))
        mape = np.mean(np.abs((actual - pred) / (actual + 0.0001))) * 100
        rmse = np.sqrt(np.mean((actual - pred) ** 2))
        
        return {
            "mae": round(float(mae), 2),
            "mape": round(float(mape), 2),
            "rmse": round(float(rmse), 2)
        }
    
    def _summarize_forecast(self, forecast: List[Dict]) -> Dict[str, Any]:
        """Summarize forecast results"""
        if not forecast:
            return {}
        
        values = [f['yhat'] for f in forecast]
        
        # Weekly summary
        weekly_totals = []
        for i in range(0, len(values), 7):
            week_values = values[i:i+7]
            weekly_totals.append(sum(week_values))
        
        return {
            "total_forecast": round(sum(values), 2),
            "avg_daily_forecast": round(np.mean(values), 2),
            "weekly_totals": [round(w, 2) for w in weekly_totals],
            "trend": "up" if values[-1] > values[0] else "down" if values[-1] < values[0] else "stable"
        }
    
    def predict(self, periods: int = 30) -> Dict[str, Any]:
        """Get forecast predictions"""
        cached = self.get_cached_results("sales_forecast")
        
        if cached and len(cached.get('forecast', [])) >= periods:
            return cached
        
        return self.train(periods)


# API Functions
def run_sales_forecast(periods: int = 30, method: str = "auto") -> Dict[str, Any]:
    """Run sales forecasting"""
    model = SalesForecasting(method=method)
    return model.train(periods=int(periods))


def get_sales_forecast(periods: int = 30) -> Dict[str, Any]:
    """Get sales forecast"""
    model = SalesForecasting()
    return model.predict(periods=int(periods))


def get_grouped_forecast(group_by: str = "item_group", periods: int = 30) -> Dict[str, Any]:
    """Get forecast by group"""
    model = SalesForecasting()
    return model.train(periods=int(periods), group_by=group_by)
