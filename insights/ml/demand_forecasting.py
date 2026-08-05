# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Demand Forecasting Model
Predicts future demand for items to optimize inventory
"""

import frappe
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from insights.ml.base import BaseMLModel


class DemandForecasting(BaseMLModel):
    """
    Item-Level Demand Forecasting
    
    Uses historical consumption data to predict:
    - Future demand per item
    - Reorder points
    - Safety stock levels
    - Stock-out probability
    
    Features:
    - Time series analysis per item
    - Seasonal decomposition
    - Trend detection
    - Lead time consideration
    """
    
    def __init__(self, method: str = "auto"):
        super().__init__()
        self.model_name = "DemandForecasting"
        self.method = method
        
    def _get_demand_history(self) -> pd.DataFrame:
        """Get historical demand (sales) data by item"""
        query = """
            SELECT 
                sii.item_code,
                i.item_name,
                i.item_group,
                i.stock_uom,
                si.posting_date,
                SUM(sii.qty) as qty_sold,
                SUM(sii.amount) as amount
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            LEFT JOIN `tabItem` i ON sii.item_code = i.name
            WHERE si.docstatus = 1
            GROUP BY sii.item_code, si.posting_date
            ORDER BY sii.item_code, si.posting_date
        """
        return self.get_training_data(query)
    
    def _get_stock_levels(self) -> pd.DataFrame:
        """Get current stock levels"""
        query = """
            SELECT 
                item_code,
                warehouse,
                SUM(actual_qty) as actual_qty,
                SUM(reserved_qty) as reserved_qty,
                SUM(ordered_qty) as ordered_qty
            FROM `tabBin`
            GROUP BY item_code, warehouse
        """
        return self.get_training_data(query)
    
    def _get_item_lead_times(self) -> pd.DataFrame:
        """Get average lead times from purchase orders"""
        query = """
            SELECT 
                poi.item_code,
                AVG(DATEDIFF(pr.posting_date, po.transaction_date)) as avg_lead_time,
                COUNT(*) as order_count
            FROM `tabPurchase Order Item` poi
            JOIN `tabPurchase Order` po ON poi.parent = po.name
            LEFT JOIN `tabPurchase Receipt Item` pri ON pri.purchase_order = po.name 
                AND pri.item_code = poi.item_code
            LEFT JOIN `tabPurchase Receipt` pr ON pri.parent = pr.name
            WHERE po.docstatus = 1 AND pr.docstatus = 1
            GROUP BY poi.item_code
        """
        return self.get_training_data(query)
    
    def _aggregate_to_weekly(self, df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate daily data to weekly"""
        df = df.copy()
        df['posting_date'] = pd.to_datetime(df['posting_date'])
        df['week'] = df['posting_date'].dt.to_period('W').dt.start_time
        
        weekly = df.groupby(['item_code', 'week']).agg({
            'qty_sold': 'sum',
            'amount': 'sum',
            'item_name': 'first',
            'item_group': 'first',
            'stock_uom': 'first'
        }).reset_index()
        
        return weekly
    
    def _calculate_demand_stats(self, item_df: pd.DataFrame) -> Dict[str, float]:
        """Calculate demand statistics for an item"""
        if item_df.empty or len(item_df) < 2:
            return {
                "avg_demand": 0,
                "std_demand": 0,
                "cv": 0,
                "trend": 0,
                "seasonality_strength": 0
            }
        
        qty = item_df['qty_sold'].values
        
        # Basic stats
        avg_demand = float(np.mean(qty))
        std_demand = float(np.std(qty))
        cv = std_demand / avg_demand if avg_demand > 0 else 0
        
        # Trend (simple linear regression coefficient)
        x = np.arange(len(qty))
        if len(qty) > 1:
            trend = float(np.polyfit(x, qty, 1)[0])
        else:
            trend = 0
        
        # Seasonality strength (if enough data)
        seasonality_strength = 0
        if len(qty) >= 8:  # At least 8 weeks
            try:
                # Compare weekly patterns
                weeks_per_pattern = min(4, len(qty) // 2)
                first_half = qty[:weeks_per_pattern]
                second_half = qty[-weeks_per_pattern:]
                correlation = np.corrcoef(first_half, second_half)[0, 1]
                seasonality_strength = float(correlation) if not np.isnan(correlation) else 0
            except:
                pass
        
        return {
            "avg_demand": round(avg_demand, 2),
            "std_demand": round(std_demand, 2),
            "cv": round(cv, 3),
            "trend": round(trend, 4),
            "seasonality_strength": round(seasonality_strength, 3)
        }
    
    def _forecast_item(self, item_df: pd.DataFrame, periods: int = 4) -> Dict[str, Any]:
        """Forecast demand for a single item"""
        if len(item_df) < 3:
            # Not enough data - use simple average
            avg = item_df['qty_sold'].mean() if not item_df.empty else 0
            return {
                "method": "simple_average",
                "forecast": [{"week": i+1, "predicted_qty": float(avg)} for i in range(periods)]
            }
        
        qty = item_df['qty_sold'].values
        
        # Try different methods based on data availability
        if len(qty) >= 12 and self.method in ["auto", "prophet"]:
            # Try exponential smoothing
            forecast = self._forecast_holt_winters(item_df, periods)
            if forecast:
                return forecast
        
        # Fallback to weighted moving average
        return self._forecast_weighted_average(qty, periods)
    
    def _forecast_holt_winters(self, item_df: pd.DataFrame, periods: int) -> Optional[Dict[str, Any]]:
        """Holt-Winters exponential smoothing"""
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            
            qty = item_df['qty_sold'].values
            
            # Fit model
            model = ExponentialSmoothing(
                qty,
                seasonal_periods=4,  # Monthly seasonality in weekly data
                trend='add',
                seasonal='add' if len(qty) >= 8 else None
            ).fit()
            
            # Forecast
            forecast = model.forecast(periods)
            
            return {
                "method": "holt_winters",
                "forecast": [
                    {"week": i+1, "predicted_qty": max(0, float(forecast[i]))}
                    for i in range(periods)
                ]
            }
        except Exception as e:
            return None
    
    def _forecast_weighted_average(self, qty: np.ndarray, periods: int) -> Dict[str, Any]:
        """Weighted moving average forecast"""
        # More weight to recent data
        if len(qty) >= 4:
            weights = [0.1, 0.2, 0.3, 0.4]
            recent = qty[-4:]
            weighted_avg = np.average(recent, weights=weights)
        else:
            weighted_avg = np.mean(qty)
        
        # Simple trend adjustment
        if len(qty) >= 2:
            trend = (qty[-1] - qty[0]) / len(qty)
        else:
            trend = 0
        
        forecast = []
        for i in range(periods):
            pred = max(0, weighted_avg + trend * (i + 1))
            forecast.append({"week": i+1, "predicted_qty": round(float(pred), 2)})
        
        return {
            "method": "weighted_average",
            "forecast": forecast
        }
    
    def _calculate_reorder_point(
        self, 
        avg_demand: float, 
        std_demand: float, 
        lead_time: float,
        service_level: float = 0.95
    ) -> Dict[str, float]:
        """Calculate reorder point and safety stock"""
        # Z-score for service level
        z_scores = {0.90: 1.28, 0.95: 1.65, 0.99: 2.33}
        z = z_scores.get(service_level, 1.65)
        
        # Safety stock = Z * σ * √(lead_time)
        safety_stock = z * std_demand * np.sqrt(lead_time) if lead_time > 0 else z * std_demand
        
        # Reorder point = (avg_demand * lead_time) + safety_stock
        reorder_point = (avg_demand * lead_time) + safety_stock
        
        # Economic Order Quantity (simplified)
        # Assuming holding cost = 20% of value, ordering cost = fixed
        eoq = np.sqrt((2 * avg_demand * 52 * 100) / (0.2 * 100)) if avg_demand > 0 else 0
        
        return {
            "safety_stock": round(float(safety_stock), 0),
            "reorder_point": round(float(reorder_point), 0),
            "eoq": round(float(eoq), 0)
        }
    
    def train(self, periods: int = 4, top_items: int = 100) -> Dict[str, Any]:
        """Generate demand forecasts for items"""
        # Get data
        demand_df = self._get_demand_history()
        
        if demand_df.empty:
            return {
                "status": "error",
                "message": "No demand history found"
            }
        
        # Get stock levels and lead times
        stock_df = self._get_stock_levels()
        lead_times_df = self._get_item_lead_times()
        
        # Aggregate to weekly
        weekly_df = self._aggregate_to_weekly(demand_df)
        
        # Get top items by volume
        item_totals = weekly_df.groupby('item_code')['qty_sold'].sum().nlargest(top_items)
        top_item_codes = item_totals.index.tolist()
        
        # Generate forecasts for each item
        forecasts = []
        
        for item_code in top_item_codes:
            item_df = weekly_df[weekly_df['item_code'] == item_code].copy()
            item_df = item_df.sort_values('week')
            
            if item_df.empty:
                continue
            
            # Get item info
            item_info = item_df.iloc[0]
            
            # Calculate demand statistics
            stats = self._calculate_demand_stats(item_df)
            
            # Generate forecast
            forecast_result = self._forecast_item(item_df, periods)
            
            # Get lead time
            item_lead_time = lead_times_df[
                lead_times_df['item_code'] == item_code
            ]['avg_lead_time'].values
            lead_time_weeks = item_lead_time[0] / 7 if len(item_lead_time) > 0 else 2
            
            # Calculate reorder point
            inventory_params = self._calculate_reorder_point(
                stats['avg_demand'],
                stats['std_demand'],
                lead_time_weeks
            )
            
            # Get current stock
            current_stock = stock_df[stock_df['item_code'] == item_code]['actual_qty'].sum()
            
            # Calculate weeks of supply
            weeks_of_supply = current_stock / stats['avg_demand'] if stats['avg_demand'] > 0 else 999
            
            # Determine stock status
            if current_stock <= inventory_params['reorder_point']:
                stock_status = "Reorder Now"
            elif current_stock <= inventory_params['reorder_point'] * 1.5:
                stock_status = "Monitor"
            else:
                stock_status = "Adequate"
            
            forecast_entry = {
                "item_code": item_code,
                "item_name": item_info['item_name'],
                "item_group": item_info['item_group'],
                "uom": item_info['stock_uom'],
                "demand_stats": stats,
                "forecast": forecast_result['forecast'],
                "forecast_method": forecast_result['method'],
                "total_forecast_qty": sum(f['predicted_qty'] for f in forecast_result['forecast']),
                "inventory_params": inventory_params,
                "current_stock": float(current_stock),
                "weeks_of_supply": round(weeks_of_supply, 1),
                "stock_status": stock_status,
                "lead_time_weeks": round(lead_time_weeks, 1)
            }
            
            forecasts.append(forecast_entry)
        
        # Sort by stock status urgency
        status_order = {"Reorder Now": 0, "Monitor": 1, "Adequate": 2}
        forecasts.sort(key=lambda x: (status_order.get(x['stock_status'], 3), -x['current_stock']))
        
        # Summary statistics
        summary = {
            "total_items_analyzed": len(forecasts),
            "reorder_now_count": len([f for f in forecasts if f['stock_status'] == "Reorder Now"]),
            "monitor_count": len([f for f in forecasts if f['stock_status'] == "Monitor"]),
            "adequate_count": len([f for f in forecasts if f['stock_status'] == "Adequate"]),
            "forecast_periods": periods,
            "data_period": {
                "start": str(weekly_df['week'].min()),
                "end": str(weekly_df['week'].max()),
                "weeks": weekly_df['week'].nunique()
            }
        }
        
        results = {
            "status": "success",
            "forecast_date": datetime.now().isoformat(),
            "summary": summary,
            "forecasts": forecasts
        }
        
        # Cache results
        self.cache_results("demand_forecast", results, expires_in_hours=12)
        
        # Log training
        self.log_training({
            "items_analyzed": len(forecasts),
            "periods": periods,
            "reorder_alerts": summary['reorder_now_count']
        })
        
        return results
    
    def predict_item(self, item_code: str, periods: int = 4) -> Dict[str, Any]:
        """Get demand forecast for a specific item"""
        demand_df = self._get_demand_history()
        demand_df = demand_df[demand_df['item_code'] == item_code]
        
        if demand_df.empty:
            return {
                "status": "error",
                "message": f"No demand history for item {item_code}"
            }
        
        weekly_df = self._aggregate_to_weekly(demand_df)
        weekly_df = weekly_df.sort_values('week')
        
        stats = self._calculate_demand_stats(weekly_df)
        forecast_result = self._forecast_item(weekly_df, periods)
        
        return {
            "status": "success",
            "item_code": item_code,
            "item_name": weekly_df.iloc[0]['item_name'],
            "demand_stats": stats,
            "forecast": forecast_result['forecast'],
            "method": forecast_result['method']
        }
    
    def predict(self, data: Any = None) -> Dict[str, Any]:
        """
        Make predictions - required by BaseMLModel abstract class.
        
        Args:
            data: Optional item_code or dict with item_code and periods
            
        Returns:
            Demand forecast for item(s)
        """
        if data is None:
            # Return cached or generate new forecast
            cached = self.get_cached_results("demand_forecast")
            if cached:
                return cached
            return self.train()
        
        # If data is a string, treat as item_code
        if isinstance(data, str):
            return self.predict_item(data)
        
        # If data is a dict, extract parameters
        if isinstance(data, dict):
            item_code = data.get('item_code')
            periods = data.get('periods', 4)
            if item_code:
                return self.predict_item(item_code, periods)
        
        # Default: return full forecast
        return self.train()


# API Functions
def run_demand_forecast(periods: int = 4, top_items: int = 100) -> Dict[str, Any]:
    """Run demand forecasting"""
    model = DemandForecasting()
    return model.train(periods=int(periods), top_items=int(top_items))


def get_demand_forecast() -> Dict[str, Any]:
    """Get cached demand forecast"""
    model = DemandForecasting()
    cached = model.get_cached_results("demand_forecast")
    
    if cached:
        return cached
    
    return model.train()


def get_item_demand_forecast(item_code: str, periods: int = 4) -> Dict[str, Any]:
    """Get demand forecast for specific item"""
    model = DemandForecasting()
    return model.predict_item(item_code, int(periods))


def get_reorder_alerts() -> Dict[str, Any]:
    """Get items that need to be reordered"""
    model = DemandForecasting()
    forecast = model.train()
    
    if forecast['status'] != 'success':
        return forecast
    
    alerts = [f for f in forecast['forecasts'] if f['stock_status'] == "Reorder Now"]
    
    return {
        "status": "success",
        "alert_count": len(alerts),
        "alerts": alerts
    }
