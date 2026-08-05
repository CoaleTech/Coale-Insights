# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ABC/XYZ Inventory Classification
- ABC: Classification by value (Pareto 80/20)
- XYZ: Classification by demand variability
- Combined matrix for inventory management strategy
"""

import frappe
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from insights.ml.base import BaseMLModel, get_date_range


class ABCXYZClassification(BaseMLModel):
    """
    ABC/XYZ Inventory Classification
    
    ABC Categories (by cumulative value):
    - A: Top 80% of value (typically 20% of items) - High value
    - B: Next 15% of value (typically 30% of items) - Medium value  
    - C: Bottom 5% of value (typically 50% of items) - Low value
    
    XYZ Categories (by coefficient of variation):
    - X: CV < 0.5 - Stable demand, easy to forecast
    - Y: 0.5 <= CV < 1.0 - Variable demand, harder to forecast
    - Z: CV >= 1.0 - Highly irregular, difficult to forecast
    
    Combined Strategy Matrix:
    - AX: High value, stable - JIT inventory, tight control
    - AY: High value, variable - Safety stock, close monitoring
    - AZ: High value, irregular - Make to order where possible
    - BX: Medium value, stable - Moderate stock levels
    - BY: Medium value, variable - Regular review
    - BZ: Medium value, irregular - Safety stock
    - CX: Low value, stable - Simple reorder rules
    - CY: Low value, variable - Periodic review
    - CZ: Low value, irregular - Consider discontinuing
    """
    
    ABC_THRESHOLDS = {
        'A': 0.80,  # Top 80% of value
        'B': 0.95,  # Next 15% (80-95%)
        'C': 1.00   # Bottom 5%
    }
    
    XYZ_THRESHOLDS = {
        'X': 0.5,   # CV < 0.5
        'Y': 1.0,   # 0.5 <= CV < 1.0
        'Z': float('inf')  # CV >= 1.0
    }
    
    def __init__(self):
        super().__init__()
        self.model_name = "ABCXYZClassification"
        
    def _get_item_sales_data(self) -> pd.DataFrame:
        """Get item-wise sales data with monthly breakdown"""
        query = """
            SELECT 
                sii.item_code,
                sii.item_name,
                i.item_group,
                DATE_FORMAT(si.posting_date, '%Y-%m') as month,
                SUM(sii.qty) as qty,
                SUM(sii.amount) as amount
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            LEFT JOIN `tabItem` i ON sii.item_code = i.name
            WHERE si.docstatus = 1
            GROUP BY sii.item_code, sii.item_name, i.item_group, DATE_FORMAT(si.posting_date, '%Y-%m')
            ORDER BY sii.item_code, month
        """
        return self.get_training_data(query)
    
    def _get_item_stock_data(self) -> pd.DataFrame:
        """Get current stock levels"""
        query = """
            SELECT 
                item_code,
                SUM(actual_qty) as stock_qty,
                SUM(actual_qty * valuation_rate) as stock_value
            FROM `tabBin`
            WHERE actual_qty > 0
            GROUP BY item_code
        """
        return self.get_training_data(query)
    
    def _calculate_abc(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate ABC classification based on total value"""
        # Aggregate total value per item
        item_totals = df.groupby(['item_code', 'item_name', 'item_group']).agg({
            'amount': 'sum',
            'qty': 'sum'
        }).reset_index()
        
        item_totals.columns = ['item_code', 'item_name', 'item_group', 'total_value', 'total_qty']
        
        # Sort by value descending
        item_totals = item_totals.sort_values('total_value', ascending=False)
        
        # Calculate cumulative percentage
        total_value = item_totals['total_value'].sum()
        item_totals['cumulative_value'] = item_totals['total_value'].cumsum()
        item_totals['cumulative_pct'] = item_totals['cumulative_value'] / total_value
        
        # Assign ABC category
        def assign_abc(pct):
            if pct <= self.ABC_THRESHOLDS['A']:
                return 'A'
            elif pct <= self.ABC_THRESHOLDS['B']:
                return 'B'
            else:
                return 'C'
        
        item_totals['abc_class'] = item_totals['cumulative_pct'].apply(assign_abc)
        
        return item_totals
    
    def _calculate_xyz(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate XYZ classification based on demand variability"""
        # Calculate monthly statistics per item
        monthly_stats = df.groupby('item_code').agg({
            'qty': ['mean', 'std', 'count']
        }).reset_index()
        
        monthly_stats.columns = ['item_code', 'avg_monthly_qty', 'std_monthly_qty', 'months_sold']
        
        # Calculate Coefficient of Variation (CV)
        # CV = standard deviation / mean
        monthly_stats['cv'] = monthly_stats.apply(
            lambda x: x['std_monthly_qty'] / x['avg_monthly_qty'] 
            if x['avg_monthly_qty'] > 0 else float('inf'),
            axis=1
        )
        
        # Handle NaN and infinity
        monthly_stats['cv'] = monthly_stats['cv'].fillna(float('inf'))
        
        # Assign XYZ category
        def assign_xyz(cv):
            if cv < self.XYZ_THRESHOLDS['X']:
                return 'X'
            elif cv < self.XYZ_THRESHOLDS['Y']:
                return 'Y'
            else:
                return 'Z'
        
        monthly_stats['xyz_class'] = monthly_stats['cv'].apply(assign_xyz)
        
        return monthly_stats
    
    def train(self) -> Dict[str, Any]:
        """Run ABC/XYZ classification"""
        # Get sales data
        df = self._get_item_sales_data()
        
        if df.empty:
            return {
                "status": "error",
                "message": "No sales data available",
                "classifications": []
            }
        
        # Calculate ABC
        abc_df = self._calculate_abc(df)
        
        # Calculate XYZ
        xyz_df = self._calculate_xyz(df)
        
        # Merge ABC and XYZ
        result_df = abc_df.merge(xyz_df, on='item_code', how='left')
        
        # Fill missing XYZ (items with single sale)
        result_df['xyz_class'] = result_df['xyz_class'].fillna('Z')
        result_df['cv'] = result_df['cv'].fillna(float('inf'))
        
        # Create combined classification
        result_df['abc_xyz_class'] = result_df['abc_class'] + result_df['xyz_class']
        
        # Get stock data
        stock_df = self._get_item_stock_data()
        if not stock_df.empty:
            result_df = result_df.merge(stock_df, on='item_code', how='left')
            result_df['stock_qty'] = result_df['stock_qty'].fillna(0)
            result_df['stock_value'] = result_df['stock_value'].fillna(0)
        else:
            result_df['stock_qty'] = 0
            result_df['stock_value'] = 0
        
        # Add strategy recommendations
        result_df['strategy'] = result_df['abc_xyz_class'].apply(self._get_strategy)
        
        # Sanitize cv values for JSON compatibility (replace inf with 999)
        result_df['cv'] = result_df['cv'].replace([float('inf'), float('-inf')], 999)
        result_df['cv'] = result_df['cv'].fillna(0)
        
        # Summary statistics
        abc_summary = result_df.groupby('abc_class').agg({
            'item_code': 'count',
            'total_value': 'sum'
        }).reset_index()
        abc_summary.columns = ['class', 'item_count', 'total_value']
        
        xyz_summary = result_df.groupby('xyz_class').agg({
            'item_code': 'count'
        }).reset_index()
        xyz_summary.columns = ['class', 'item_count']
        
        combined_summary = result_df.groupby('abc_xyz_class').agg({
            'item_code': 'count',
            'total_value': 'sum',
            'stock_value': 'sum'
        }).reset_index()
        combined_summary.columns = ['class', 'item_count', 'sales_value', 'stock_value']
        
        # Update item records
        self._update_item_classifications(result_df)
        
        # Prepare results
        results = {
            "status": "success",
            "analysis_date": datetime.now().isoformat(),
            "total_items": len(result_df),
            "abc_summary": abc_summary.to_dict('records'),
            "xyz_summary": xyz_summary.to_dict('records'),
            "combined_summary": combined_summary.to_dict('records'),
            "items": result_df[[
                'item_code', 'item_name', 'item_group',
                'total_value', 'total_qty', 'abc_class', 'xyz_class', 
                'abc_xyz_class', 'cv', 'avg_monthly_qty', 'stock_qty',
                'stock_value', 'strategy'
            ]].to_dict('records')
        }
        
        # Cache results
        self.cache_results("abc_xyz_classification", results, expires_in_hours=24)
        
        # Log training
        self.log_training({
            "total_items": len(result_df),
            "abc_distribution": abc_summary.to_dict('records'),
            "xyz_distribution": xyz_summary.to_dict('records')
        })
        
        return results
    
    def _get_strategy(self, abc_xyz: str) -> str:
        """Get inventory strategy for ABC/XYZ class"""
        strategies = {
            'AX': "JIT inventory, tight control, frequent review, accurate forecasting",
            'AY': "Safety stock needed, demand sensing, close supplier relationships",
            'AZ': "Make-to-order preferred, vendor managed inventory, buffer stock",
            'BX': "Moderate stock levels, periodic review, standard ordering",
            'BY': "Regular safety stock review, demand monitoring",
            'BZ': "Higher safety stock, flexible supply chain",
            'CX': "Simple reorder rules, bulk ordering, low handling priority",
            'CY': "Periodic batch review, consider consignment",
            'CZ': "Consider discontinuing, minimal stock, opportunistic buying"
        }
        return strategies.get(abc_xyz, "Standard inventory management")
    
    def _update_item_classifications(self, df: pd.DataFrame):
        """Update Item doctype with classification"""
        for _, row in df.iterrows():
            try:
                if frappe.db.exists("Item", row['item_code']):
                    frappe.db.set_value(
                        "Item",
                        row['item_code'],
                        {
                            "custom_abc_class": row['abc_class'],
                            "custom_xyz_class": row['xyz_class'],
                            "custom_abc_xyz_class": row['abc_xyz_class'],
                            "custom_demand_cv": round(row['cv'], 4) if row['cv'] != float('inf') else 999,
                            "custom_classification_updated": frappe.utils.now()
                        },
                        update_modified=False
                    )
            except Exception as e:
                # Skip if custom fields don't exist
                pass
        frappe.db.commit()
    
    def predict(self, item_code: str = None) -> Dict[str, Any]:
        """Get classification for specific item or all"""
        cached = self.get_cached_results("abc_xyz_classification")
        
        if not cached:
            cached = self.train()
        
        if item_code:
            items = cached.get("items", [])
            for item in items:
                if item['item_code'] == item_code:
                    return {"status": "success", "item": item}
            return {"status": "error", "message": "Item not found"}
        
        return cached
    
    def get_reorder_recommendations(self) -> Dict[str, Any]:
        """Get reorder recommendations based on ABC/XYZ"""
        cached = self.get_cached_results("abc_xyz_classification")
        
        if not cached:
            cached = self.train()
        
        items = cached.get("items", [])
        
        recommendations = {
            "critical_reorder": [],  # A items with low stock
            "review_needed": [],     # B items needing attention
            "consider_discontinue": []  # CZ items
        }
        
        for item in items:
            stock_months = (item['stock_qty'] / item['avg_monthly_qty'] 
                          if item['avg_monthly_qty'] > 0 else float('inf'))
            
            if item['abc_class'] == 'A' and stock_months < 2:
                recommendations["critical_reorder"].append({
                    **item,
                    "stock_months": round(stock_months, 1),
                    "urgency": "HIGH"
                })
            elif item['abc_class'] == 'B' and stock_months < 1:
                recommendations["review_needed"].append({
                    **item,
                    "stock_months": round(stock_months, 1),
                    "urgency": "MEDIUM"
                })
            elif item['abc_xyz_class'] == 'CZ':
                recommendations["consider_discontinue"].append(item)
        
        return recommendations


# API Functions
def run_abc_xyz_classification() -> Dict[str, Any]:
    """Run ABC/XYZ classification"""
    model = ABCXYZClassification()
    return model.train()


def get_item_classification(item_code: str = None) -> Dict[str, Any]:
    """Get item classification"""
    model = ABCXYZClassification()
    return model.predict(item_code)


def get_reorder_recommendations() -> Dict[str, Any]:
    """Get reorder recommendations"""
    model = ABCXYZClassification()
    return model.get_reorder_recommendations()
