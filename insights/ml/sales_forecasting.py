# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Sales Forecasting using Time Series Analysis
Supports Prophet, ARIMA, and Exponential Smoothing methods
"""
import frappe
from frappe import _
import importlib.util
import pandas as pd
import numpy as np
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from insights.ml.base import BaseMLModel, get_date_range

# Prophet estimates a yearly seasonal component. Fitting one from a single
# observed year is interpolation dressed as inference, so it stays off until
# there are two cycles of daily history. Frappe Cloud installs the library
# either way (pyproject `dependencies`) -- availability is an install concern,
# applicability is a data one, and they are decided separately.
PROPHET_MIN_DAYS = 730


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

    @staticmethod
    def _check_prophet() -> bool:
        """Report whether Prophet is installed without importing it.

        ``from prophet import Prophet`` loads cmdstanpy, which links Intel TBB
        (libtbb). That native thread pool cannot survive ``rq``'s per-job
        ``fork()`` -- the work-horse dies as ``waitpid returned 139 (signal 11)``
        with no Python traceback. Constructing a ``SalesForecasting`` to read a
        cache key (which the scheduler, the warm-up, and the dashboard all do)
        used to import Prophet in the worker *parent*, so the next fork segfaulted.
        ``find_spec`` answers "is it installed?" without executing the import,
        so Prophet stays out of the parent. The only code that imports it is
        ``_forecast_prophet``, which runs in the forked child after BLAS is
        pinned, and never re-forks.
        """
        return importlib.util.find_spec("prophet") is not None
    
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
            # Prophet first, but only once the history can support it.
            if self.prophet_available and len(df) >= PROPHET_MIN_DAYS:
                forecast_result = self._forecast_prophet(df, periods)

            if not forecast_result:
                forecast_result = self._forecast_exponential_smoothing(df, periods)

            if not forecast_result:
                forecast_result = self._forecast_moving_average(df, periods)

        elif self.method == "prophet":
            if not self.prophet_available:
                return {
                    "status": "error",
                    "message": _("Prophet is not installed on this bench."),
                }
            if len(df) < PROPHET_MIN_DAYS:
                return {
                    "status": "error",
                    "message": _(
                        "Prophet needs at least {0} days of history to estimate yearly "
                        "seasonality; this site has {1}. Use exponential smoothing until then."
                    ).format(PROPHET_MIN_DAYS, len(df)),
                }
            forecast_result = self._forecast_prophet(df, periods)
        
        elif self.method == "exponential_smoothing":
            forecast_result = self._forecast_exponential_smoothing(df, periods)
        
        else:
            forecast_result = self._forecast_moving_average(df, periods)
        
        if not forecast_result:
            forecast_result = self._forecast_moving_average(df, periods)
        
        # Accuracy of the method actually used, measured on a held-out tail.
        metrics = self._backtest(df, forecast_result.get("method"))
        
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
    
    def _backtest(self, df: pd.DataFrame, method: Optional[str]) -> Dict[str, float]:
        """Hold out the last 14 days, re-forecast them, and score the result.

        Replaces a metric that never touched the model: it compared the *mean of
        the training set* against the last 7 days, so the number reported as the
        forecast's accuracy was the error of a flat constant. On this site that
        surfaced as "MAPE 244.18%" for a forecast that was not being measured.

        MAPE is also the wrong metric for this series. Daily sales is zero on
        non-trading days -- `_forecast_exponential_smoothing` calls
        `asfreq('D', fill_value=0)` -- and dividing by a zero actual makes the
        percentage explode regardless of how good the forecast is. The old code
        papered over it with `actual + 0.0001`, which turns a division by zero
        into a division by almost zero and reports thousands of percent.

        So: sMAPE, which is bounded at 200% and defined when an actual is zero,
        plus MAE and RMSE in the series' own units. MAPE is still reported, but
        only over the non-zero actuals where it means something.
        """
        horizon = 14
        if len(df) < horizon * 3:
            return {}

        train, test = df.iloc[:-horizon], df.iloc[-horizon:]

        forecaster = {
            "prophet": self._forecast_prophet,
            "exponential_smoothing": self._forecast_exponential_smoothing,
        }.get(method or "", self._forecast_moving_average)

        try:
            backtest = forecaster(train, horizon)
        except Exception:
            backtest = None
        if not backtest or not backtest.get("forecast"):
            return {}

        predicted = np.array(
            [float(point.get("yhat", 0)) for point in backtest["forecast"][:horizon]], dtype=float
        )
        actual = np.asarray(test["y"].values, dtype=float)[: len(predicted)]
        predicted = predicted[: len(actual)]
        if not len(actual):
            return {}

        error = actual - predicted
        denominator = (np.abs(actual) + np.abs(predicted)) / 2
        smape = float(np.mean(np.where(denominator > 0, np.abs(error) / np.where(denominator > 0, denominator, 1), 0)) * 100)

        nonzero = actual != 0
        mape = (
            float(np.mean(np.abs(error[nonzero] / actual[nonzero])) * 100) if nonzero.any() else None
        )

        metrics = {
            "method_tested": method or "moving_average",
            "horizon_days": int(len(actual)),
            "mae": round(float(np.mean(np.abs(error))), 2),
            "rmse": round(float(np.sqrt(np.mean(error**2))), 2),
            "smape": round(smape, 2),
        }
        if mape is not None:
            metrics["mape"] = round(mape, 2)
            metrics["mape_basis_days"] = int(nonzero.sum())
        return metrics
    
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


# Periods the Revenue "Forecasts" tab shows: a year of actuals, a quarter ahead.
_DIM_HISTORY_MONTHS = 12
_DIM_FORECAST_MONTHS = 3
# Below this many observed months a group has no trend worth extrapolating;
# it still contributes its history, just no forecast rows.
_DIM_MIN_MONTHS = 3


def _rows(raw: List[Dict[str, Any]], alias: str) -> List[Dict[str, Any]]:
    return [
        {
            "period": r["period"],
            alias: r["bucket"],
            "revenue": float(r["revenue"] or 0),
            "transactions": int(r["transactions"] or 0),
            "is_forecast": False,
        }
        for r in raw
    ]


def _monthly_by_territory(months: int) -> List[Dict[str, Any]]:
    """Monthly revenue per territory.

    Territory is a Sales Invoice header field, so the invoice total can be
    summed directly -- one row per invoice, no fan-out.
    """
    raw = frappe.db.sql(
        """
        SELECT
            DATE_FORMAT(si.posting_date, '%%Y-%%m') AS period,
            COALESCE(NULLIF(si.territory, ''), 'Unknown') AS bucket,
            SUM(si.base_grand_total) AS revenue,
            COUNT(*) AS transactions
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.is_return = 0
          AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL %(months)s MONTH)
        GROUP BY period, bucket
        ORDER BY period
        """,
        {"months": months},
        as_dict=True,
    )
    return _rows(raw, "territory")


def _monthly_by_item_group(months: int) -> List[Dict[str, Any]]:
    """Monthly revenue per item group.

    Item group lives on the invoice *lines*, so this has to join -- and that is
    where the naive version was wrong. Summing `si.base_grand_total` across the
    join counts the whole invoice once per line, which inflated this site's
    product-group revenue by 42% (17.4M against a true 12.2M for 2025-08).

    Summing `sii.base_net_amount` instead attributes correctly but reports net,
    so the table would not tie to the grand-total figure in the header KPI.
    Allocating the invoice total across its lines in proportion to their net
    amount gives both: correct attribution that still sums to revenue. Invoices
    with a zero net total (fully discounted) fall back to the line amount rather
    than dividing by zero.
    """
    raw = frappe.db.sql(
        """
        SELECT
            DATE_FORMAT(si.posting_date, '%%Y-%%m') AS period,
            COALESCE(NULLIF(sii.item_group, ''), 'Unknown') AS bucket,
            SUM(
                CASE
                    WHEN IFNULL(si.base_net_total, 0) = 0 THEN sii.base_net_amount
                    ELSE sii.base_net_amount / si.base_net_total * si.base_grand_total
                END
            ) AS revenue,
            COUNT(DISTINCT si.name) AS transactions
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.docstatus = 1
          AND si.is_return = 0
          AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL %(months)s MONTH)
        GROUP BY period, bucket
        ORDER BY period
        """,
        {"months": months},
        as_dict=True,
    )
    return _rows(raw, "product_group")


def _extend_with_forecast(history: List[Dict[str, Any]], alias: str) -> List[Dict[str, Any]]:
    """Append forecast months per group, using its own recent average.

    A weighted mean of the last three observed months, not a fitted model: these
    per-group monthly series are 12 points long at best and frequently sparse,
    which is below what Holt-Winters needs for a seasonal fit and well below
    Prophet's floor. Reporting a mean as a mean is honest; dressing it up as a
    model would repeat the failure the health page exists to catch.
    """
    if not history:
        return []

    by_group: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in history:
        by_group[row[alias]].append(row)

    last_period = max(row["period"] for row in history)
    year, month = (int(part) for part in last_period.split("-"))

    future_periods = []
    for step in range(1, _DIM_FORECAST_MONTHS + 1):
        total = month + step
        future_periods.append(f"{year + (total - 1) // 12}-{(total - 1) % 12 + 1:02d}")

    projected = []
    for group, rows in by_group.items():
        rows.sort(key=lambda r: r["period"])
        if len(rows) < _DIM_MIN_MONTHS:
            continue
        recent = rows[-3:]
        # Weight the most recent month heaviest: 1, 2, 3 over the last three.
        weights = list(range(1, len(recent) + 1))
        divisor = sum(weights)
        revenue = sum(r["revenue"] * w for r, w in zip(recent, weights)) / divisor
        transactions = sum(r["transactions"] * w for r, w in zip(recent, weights)) / divisor
        for period in future_periods:
            projected.append(
                {
                    "period": period,
                    alias: group,
                    "revenue": round(revenue, 2),
                    "transactions": int(round(transactions)),
                    "is_forecast": True,
                }
            )

    return history + projected


def get_dimensional_history_and_forecast(months: int = _DIM_HISTORY_MONTHS) -> Dict[str, Any]:
    """Monthly actuals plus a short projection, by product group and territory.

    Shaped for the Revenue dashboard's "Forecasts" tab, which transposes these
    into a period-by-group table. It reads `combined_product_group` and
    `combined_territory`; the endpoint previously returned
    `SalesForecasting.train(group_by=...)`, whose shape is
    `{status, group_by, groups}` and carries neither key -- so the tab rendered
    "No product group data available" while the request came back 200 with a
    full payload. The two sides had never agreed.
    """
    product_group = _monthly_by_item_group(months)
    territory = _monthly_by_territory(months)

    return {
        "status": "success",
        "months": months,
        "horizon_months": _DIM_FORECAST_MONTHS,
        "combined_product_group": _extend_with_forecast(product_group, "product_group"),
        "combined_territory": _extend_with_forecast(territory, "territory"),
    }
