from __future__ import annotations
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Inventory Intelligence Model
Comprehensive inventory analytics with ML-powered insights for:
- Stock analysis and health monitoring
- Turnover metrics and optimization
- Multi-warehouse management with transfer recommendations
- Aging analysis with FIFO valuation
- Demand planning and procurement optimization
"""

import frappe
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    import numpy as np

from insights.ml.base import BaseMLModel
from insights.api.ml import get_date_filter_sql


class InventoryIntelligence(BaseMLModel):
    """
    Comprehensive Inventory Intelligence Model
    
    Integrates with:
    - ABCXYZClassification for item prioritization
    - DemandForecasting for reorder planning
    
    Features:
    - Multi-warehouse stock analysis
    - FIFO-based aging and valuation
    - Transfer recommendations between warehouses
    - Turnover analysis by product group
    - Dead stock identification
    - Procurement optimization
    """
    
    def __init__(self, date_filter: str = '12m'):
        super().__init__()
        self.model_name = "InventoryIntelligence"
        self.date_filter = date_filter
        # Generate SQL date filter
        self.date_filter_sql = get_date_filter_sql(date_filter, 'posting_date', '')
    
    def train(self, include_abc_xyz: bool = True, include_demand: bool = True) -> Dict[str, Any]:
        """Generate comprehensive inventory intelligence"""
        try:
            stock_overview = self._calculate_stock_overview()
            turnover_analysis = self._calculate_turnover_analysis()
            aging_analysis = self._calculate_aging_analysis()
            warehouse_analysis = self._calculate_warehouse_analysis()
            procurement_insights = self._calculate_procurement_insights()
            dead_stock = self._identify_dead_stock()
            transfer_recommendations = self._generate_transfer_recommendations()
            
            abc_xyz_data = None
            if include_abc_xyz:
                abc_xyz_data = self._get_abc_xyz_data()
            
            demand_data = None
            if include_demand:
                demand_data = self._get_demand_forecast_data()
            
            result = {
                "status": "success",
                "generated_at": datetime.now().isoformat(),
                "stock_overview": stock_overview,
                "turnover_analysis": turnover_analysis,
                "aging_analysis": aging_analysis,
                "warehouse_analysis": warehouse_analysis,
                "procurement_insights": procurement_insights,
                "dead_stock": dead_stock,
                "transfer_recommendations": transfer_recommendations,
                "abc_xyz": abc_xyz_data,
                "demand_planning": demand_data
            }
            
            self.cache_results("inventory_intelligence", result)
            return result
            
        except Exception as e:
            frappe.log_error(f"Inventory Intelligence failed: {str(e)}", "ML Inventory")
            return {"status": "error", "message": str(e)}
    
    def predict(self) -> Dict[str, Any]:
        """Return cached results or generate new ones"""
        cached = self.get_cached_results("inventory_intelligence")
        if cached:
            return cached
        return self.train()
    
    def _calculate_stock_overview(self) -> Dict[str, Any]:
        """Calculate overall stock health metrics"""
        stock_summary = frappe.db.sql("""
            SELECT 
                COUNT(DISTINCT b.item_code) as total_skus,
                SUM(b.actual_qty) as total_qty,
                SUM(b.actual_qty * b.valuation_rate) as total_value,
                SUM(CASE WHEN b.actual_qty <= 0 THEN 1 ELSE 0 END) as out_of_stock_count,
                COUNT(DISTINCT b.warehouse) as warehouse_count
            FROM `tabBin` b
            WHERE b.actual_qty != 0 OR b.reserved_qty != 0 OR b.ordered_qty != 0
        """, as_dict=True)[0]
        
        overstock_query = frappe.db.sql("""
            SELECT COUNT(DISTINCT b.item_code) as overstock_count
            FROM `tabBin` b
            LEFT JOIN (
                SELECT sii.item_code, 
                       SUM(sii.qty) / GREATEST(DATEDIFF(CURDATE(), MIN(si.posting_date)), 30) as avg_daily_sales
                FROM `tabSales Invoice Item` sii
                JOIN `tabSales Invoice` si ON sii.parent = si.name
                WHERE si.docstatus = 1 AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
                GROUP BY sii.item_code
            ) sales ON b.item_code = sales.item_code
            WHERE b.actual_qty > COALESCE(sales.avg_daily_sales * 90, 0)
                AND b.actual_qty > 0
                AND COALESCE(sales.avg_daily_sales, 0) > 0
        """, as_dict=True)[0]
        
        low_stock_query = frappe.db.sql("""
            SELECT COUNT(DISTINCT b.item_code) as low_stock_count
            FROM `tabBin` b
            LEFT JOIN (
                SELECT sii.item_code, 
                       SUM(sii.qty) / GREATEST(DATEDIFF(CURDATE(), MIN(si.posting_date)), 30) as avg_daily_sales
                FROM `tabSales Invoice Item` sii
                JOIN `tabSales Invoice` si ON sii.parent = si.name
                WHERE si.docstatus = 1 AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
                GROUP BY sii.item_code
            ) sales ON b.item_code = sales.item_code
            WHERE b.actual_qty > 0 
                AND b.actual_qty < COALESCE(sales.avg_daily_sales * 14, 0)
                AND COALESCE(sales.avg_daily_sales, 0) > 0
        """, as_dict=True)[0]
        
        stock_by_group = frappe.db.sql("""
            SELECT 
                COALESCE(i.item_group, 'Uncategorized') as item_group,
                COUNT(DISTINCT b.item_code) as item_count,
                SUM(b.actual_qty) as total_qty,
                SUM(b.actual_qty * b.valuation_rate) as stock_value
            FROM `tabBin` b
            LEFT JOIN `tabItem` i ON b.item_code = i.name
            WHERE b.actual_qty > 0
            GROUP BY i.item_group
            ORDER BY stock_value DESC
            LIMIT 15
        """, as_dict=True)
        
        return {
            "total_skus": int(stock_summary.get('total_skus') or 0),
            "total_qty": float(stock_summary.get('total_qty') or 0),
            "total_value": float(stock_summary.get('total_value') or 0),
            "out_of_stock_count": int(stock_summary.get('out_of_stock_count') or 0),
            "overstock_count": int(overstock_query.get('overstock_count') or 0),
            "low_stock_count": int(low_stock_query.get('low_stock_count') or 0),
            "warehouse_count": int(stock_summary.get('warehouse_count') or 0),
            "by_item_group": stock_by_group,
            "health_score": self._calculate_health_score(stock_summary, overstock_query, low_stock_query)
        }
    
    def _calculate_health_score(self, summary: Dict, overstock: Dict, low_stock: Dict) -> float:
        """Calculate overall inventory health score (0-100)"""
        total_skus = summary.get('total_skus') or 1
        out_of_stock = summary.get('out_of_stock_count') or 0
        overstock_count = overstock.get('overstock_count') or 0
        low_stock_count = low_stock.get('low_stock_count') or 0
        
        out_of_stock_penalty = (out_of_stock / total_skus) * 30
        overstock_penalty = (overstock_count / total_skus) * 20
        low_stock_penalty = (low_stock_count / total_skus) * 20
        
        score = 100 - out_of_stock_penalty - overstock_penalty - low_stock_penalty
        return round(max(0, min(100, score)), 1)
    
    def _calculate_turnover_analysis(self) -> Dict[str, Any]:
        """Calculate inventory turnover metrics"""
        turnover_data = frappe.db.sql("""
            SELECT 
                COALESCE(SUM(sii.amount), 0) as cogs_12m,
                (SELECT SUM(actual_qty * valuation_rate) FROM `tabBin` WHERE actual_qty > 0) as avg_inventory
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.docstatus = 1 
                AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
        """, as_dict=True)[0]
        
        cogs = float(turnover_data.get('cogs_12m') or 0)
        avg_inventory = float(turnover_data.get('avg_inventory') or 1)
        turnover_ratio = cogs / avg_inventory if avg_inventory > 0 else 0
        days_sales_inventory = 365 / turnover_ratio if turnover_ratio > 0 else 0
        
        turnover_by_group = frappe.db.sql("""
            SELECT 
                COALESCE(i.item_group, 'Uncategorized') as item_group,
                SUM(sii.amount) as sales_12m,
                (
                    SELECT SUM(b.actual_qty * b.valuation_rate) 
                    FROM `tabBin` b 
                    LEFT JOIN `tabItem` it ON b.item_code = it.name
                    WHERE it.item_group = i.item_group AND b.actual_qty > 0
                ) as current_stock_value
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            LEFT JOIN `tabItem` i ON sii.item_code = i.name
            WHERE si.docstatus = 1 
                AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY i.item_group
            ORDER BY sales_12m DESC
            LIMIT 10
        """, as_dict=True)
        
        for group in turnover_by_group:
            stock_val = float(group.get('current_stock_value') or 0)
            sales = float(group.get('sales_12m') or 0)
            # Only calculate turnover if we have actual stock value
            if stock_val > 0:
                group['turnover_ratio'] = round(sales / stock_val, 2)
                group['dsi'] = round(365 / group['turnover_ratio'], 0) if group['turnover_ratio'] > 0 else 999
            else:
                group['turnover_ratio'] = 0
                group['dsi'] = 999
        
        fast_moving = frappe.db.sql("""
            SELECT 
                sii.item_code,
                sii.item_name,
                SUM(sii.qty) as qty_sold,
                SUM(sii.amount) as sales_value,
                COALESCE((SELECT SUM(actual_qty) FROM `tabBin` WHERE item_code = sii.item_code), 0) as current_stock
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.docstatus = 1 
                AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
            GROUP BY sii.item_code, sii.item_name
            ORDER BY qty_sold DESC
            LIMIT 10
        """, as_dict=True)
        
        slow_moving = frappe.db.sql("""
            SELECT 
                b.item_code,
                i.item_name,
                b.actual_qty as current_stock,
                b.actual_qty * b.valuation_rate as stock_value,
                COALESCE(sales.qty_sold, 0) as qty_sold_90d
            FROM `tabBin` b
            LEFT JOIN `tabItem` i ON b.item_code = i.name
            LEFT JOIN (
                SELECT sii.item_code, SUM(sii.qty) as qty_sold
                FROM `tabSales Invoice Item` sii
                JOIN `tabSales Invoice` si ON sii.parent = si.name
                WHERE si.docstatus = 1 
                    AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
                GROUP BY sii.item_code
            ) sales ON b.item_code = sales.item_code
            WHERE b.actual_qty > 0
            ORDER BY COALESCE(sales.qty_sold, 0) ASC, stock_value DESC
            LIMIT 10
        """, as_dict=True)
        
        return {
            "overall_turnover_ratio": round(turnover_ratio, 2),
            "days_sales_inventory": round(days_sales_inventory, 0),
            "cogs_12m": cogs,
            "avg_inventory_value": avg_inventory,
            "by_product_group": turnover_by_group,
            "fast_moving": fast_moving,
            "slow_moving": slow_moving
        }
    
    def _calculate_aging_analysis(self) -> Dict[str, Any]:
        """Calculate stock aging with FIFO valuation"""
        aging_data = frappe.db.sql("""
            SELECT 
                sle.item_code,
                i.item_name,
                i.item_group,
                sle.warehouse,
                sle.posting_date,
                sle.actual_qty,
                sle.valuation_rate,
                DATEDIFF(CURDATE(), sle.posting_date) as age_days
            FROM `tabStock Ledger Entry` sle
            LEFT JOIN `tabItem` i ON sle.item_code = i.name
            WHERE sle.actual_qty > 0 
                AND sle.is_cancelled = 0
            ORDER BY sle.item_code, sle.posting_date ASC
        """, as_dict=True)
        
        item_aging = {}
        for entry in aging_data:
            item_code = entry['item_code']
            if item_code not in item_aging:
                item_aging[item_code] = {
                    'item_code': item_code,
                    'item_name': entry['item_name'],
                    'item_group': entry['item_group'],
                    'total_qty': 0,
                    'total_value': 0,
                    'weighted_age': 0
                }
            
            qty = float(entry['actual_qty'] or 0)
            rate = float(entry['valuation_rate'] or 0)
            age = int(entry['age_days'] or 0)
            
            item_aging[item_code]['total_qty'] += qty
            item_aging[item_code]['total_value'] += qty * rate
            item_aging[item_code]['weighted_age'] += age * qty
        
        for item in item_aging.values():
            if item['total_qty'] > 0:
                item['avg_age_days'] = round(item['weighted_age'] / item['total_qty'], 0)
            else:
                item['avg_age_days'] = 0
        
        age_buckets = {
            '0-30 days': {'count': 0, 'value': 0},
            '31-60 days': {'count': 0, 'value': 0},
            '61-90 days': {'count': 0, 'value': 0},
            '91-180 days': {'count': 0, 'value': 0},
            '181-365 days': {'count': 0, 'value': 0},
            '365+ days': {'count': 0, 'value': 0}
        }
        
        for item in item_aging.values():
            avg_age = item['avg_age_days']
            value = item['total_value']
            
            if avg_age <= 30:
                age_buckets['0-30 days']['count'] += 1
                age_buckets['0-30 days']['value'] += value
            elif avg_age <= 60:
                age_buckets['31-60 days']['count'] += 1
                age_buckets['31-60 days']['value'] += value
            elif avg_age <= 90:
                age_buckets['61-90 days']['count'] += 1
                age_buckets['61-90 days']['value'] += value
            elif avg_age <= 180:
                age_buckets['91-180 days']['count'] += 1
                age_buckets['91-180 days']['value'] += value
            elif avg_age <= 365:
                age_buckets['181-365 days']['count'] += 1
                age_buckets['181-365 days']['value'] += value
            else:
                age_buckets['365+ days']['count'] += 1
                age_buckets['365+ days']['value'] += value
        
        aging_by_group = {}
        for item in item_aging.values():
            group = item['item_group'] or 'Uncategorized'
            if group not in aging_by_group:
                aging_by_group[group] = {
                    'item_group': group,
                    'item_count': 0,
                    'total_value': 0,
                    'total_weighted_age': 0,
                    'total_qty': 0
                }
            aging_by_group[group]['item_count'] += 1
            aging_by_group[group]['total_value'] += item['total_value']
            aging_by_group[group]['total_weighted_age'] += item['weighted_age']
            aging_by_group[group]['total_qty'] += item['total_qty']
        
        aging_by_group_list = []
        for group in aging_by_group.values():
            if group['total_qty'] > 0:
                group['avg_age_days'] = round(group['total_weighted_age'] / group['total_qty'], 0)
            else:
                group['avg_age_days'] = 0
            aging_by_group_list.append(group)
        
        aging_by_group_list.sort(key=lambda x: x['total_value'], reverse=True)
        
        oldest_items = sorted(item_aging.values(), key=lambda x: x['avg_age_days'], reverse=True)[:10]
        for item in oldest_items:
            del item['weighted_age']
        
        return {
            "age_buckets": age_buckets,
            "by_product_group": aging_by_group_list[:10],
            "oldest_items": oldest_items,
            "total_items_analyzed": len(item_aging)
        }
    
    def _calculate_warehouse_analysis(self) -> Dict[str, Any]:
        """Analyze inventory across warehouses"""
        warehouse_stock = frappe.db.sql("""
            SELECT 
                b.warehouse,
                COUNT(DISTINCT b.item_code) as item_count,
                SUM(b.actual_qty) as total_qty,
                SUM(b.actual_qty * b.valuation_rate) as stock_value,
                SUM(b.reserved_qty) as reserved_qty,
                SUM(b.ordered_qty) as ordered_qty
            FROM `tabBin` b
            WHERE b.actual_qty > 0 OR b.reserved_qty > 0 OR b.ordered_qty > 0
            GROUP BY b.warehouse
            ORDER BY stock_value DESC
        """, as_dict=True)
        
        total_value = sum(float(w.get('stock_value') or 0) for w in warehouse_stock)
        for w in warehouse_stock:
            w['pct_of_total'] = round((float(w.get('stock_value') or 0) / total_value * 100), 1) if total_value > 0 else 0
        
        multi_warehouse_items = frappe.db.sql("""
            SELECT 
                b.item_code,
                i.item_name,
                COUNT(DISTINCT b.warehouse) as warehouse_count,
                SUM(b.actual_qty) as total_qty,
                GROUP_CONCAT(CONCAT(b.warehouse, ':', ROUND(b.actual_qty, 0)) SEPARATOR ', ') as distribution
            FROM `tabBin` b
            LEFT JOIN `tabItem` i ON b.item_code = i.name
            WHERE b.actual_qty > 0
            GROUP BY b.item_code, i.item_name
            HAVING warehouse_count > 1
            ORDER BY total_qty DESC
            LIMIT 20
        """, as_dict=True)
        
        return {
            "by_warehouse": warehouse_stock,
            "total_warehouses": len(warehouse_stock),
            "total_stock_value": total_value,
            "multi_warehouse_items": multi_warehouse_items
        }
    
    def _generate_transfer_recommendations(self) -> List[Dict[str, Any]]:
        """Generate stock transfer recommendations between warehouses"""
        recommendations = []
        
        imbalanced_items = frappe.db.sql("""
            SELECT 
                b.item_code,
                i.item_name,
                b.warehouse,
                b.actual_qty,
                b.valuation_rate,
                COALESCE(sales.avg_daily_sales, 0) as warehouse_daily_demand
            FROM `tabBin` b
            LEFT JOIN `tabItem` i ON b.item_code = i.name
            LEFT JOIN (
                SELECT 
                    sii.item_code,
                    si.set_warehouse as warehouse,
                    SUM(sii.qty) / 90 as avg_daily_sales
                FROM `tabSales Invoice Item` sii
                JOIN `tabSales Invoice` si ON sii.parent = si.name
                WHERE si.docstatus = 1 
                    AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
                GROUP BY sii.item_code, si.set_warehouse
            ) sales ON b.item_code = sales.item_code AND b.warehouse = sales.warehouse
            WHERE b.actual_qty > 0
            ORDER BY b.item_code, b.warehouse
        """, as_dict=True)
        
        item_warehouses = {}
        for row in imbalanced_items:
            item_code = row['item_code']
            if item_code not in item_warehouses:
                item_warehouses[item_code] = {
                    'item_code': item_code,
                    'item_name': row['item_name'],
                    'warehouses': []
                }
            daily_demand = float(row['warehouse_daily_demand'] or 0.01)
            item_warehouses[item_code]['warehouses'].append({
                'warehouse': row['warehouse'],
                'qty': float(row['actual_qty'] or 0),
                'daily_demand': daily_demand,
                'days_of_supply': float(row['actual_qty'] or 0) / daily_demand
            })
        
        for item in item_warehouses.values():
            if len(item['warehouses']) < 2:
                continue
            
            sorted_wh = sorted(item['warehouses'], key=lambda x: x['days_of_supply'])
            low_stock_wh = [w for w in sorted_wh if w['days_of_supply'] < 14 and w['daily_demand'] > 0.01]
            high_stock_wh = [w for w in sorted_wh if w['days_of_supply'] > 60]
            
            for low in low_stock_wh:
                for high in high_stock_wh:
                    target_days = 30
                    needed_qty = (target_days * low['daily_demand']) - low['qty']
                    available_qty = high['qty'] - (30 * high['daily_demand'])
                    transfer_qty = min(needed_qty, available_qty)
                    
                    if transfer_qty > 0:
                        recommendations.append({
                            'item_code': item['item_code'],
                            'item_name': item['item_name'],
                            'from_warehouse': high['warehouse'],
                            'to_warehouse': low['warehouse'],
                            'recommended_qty': round(transfer_qty, 0),
                            'reason': f"Low stock ({round(low['days_of_supply'], 0)} days) at destination, excess ({round(high['days_of_supply'], 0)} days) at source",
                            'priority': 'High' if low['days_of_supply'] < 7 else 'Medium'
                        })
        
        recommendations.sort(key=lambda x: (0 if x['priority'] == 'High' else 1, -x['recommended_qty']))
        return recommendations[:20]
    
    def _identify_dead_stock(self) -> Dict[str, Any]:
        """Identify dead/obsolete stock with no sales in 180+ days"""
        dead_stock = frappe.db.sql("""
            SELECT 
                b.item_code,
                i.item_name,
                i.item_group,
                b.warehouse,
                b.actual_qty,
                b.actual_qty * b.valuation_rate as stock_value,
                COALESCE(last_sale.last_sale_date, '1900-01-01') as last_sale_date,
                DATEDIFF(CURDATE(), COALESCE(last_sale.last_sale_date, '1900-01-01')) as days_since_last_sale
            FROM `tabBin` b
            LEFT JOIN `tabItem` i ON b.item_code = i.name
            LEFT JOIN (
                SELECT sii.item_code, MAX(si.posting_date) as last_sale_date
                FROM `tabSales Invoice Item` sii
                JOIN `tabSales Invoice` si ON sii.parent = si.name
                WHERE si.docstatus = 1
                GROUP BY sii.item_code
            ) last_sale ON b.item_code = last_sale.item_code
            WHERE b.actual_qty > 0
                AND (last_sale.last_sale_date IS NULL 
                     OR DATEDIFF(CURDATE(), last_sale.last_sale_date) > 180)
            ORDER BY stock_value DESC
            LIMIT 50
        """, as_dict=True)
        
        total_dead_stock_value = sum(float(item.get('stock_value') or 0) for item in dead_stock)
        
        dead_by_group = {}
        for item in dead_stock:
            group = item.get('item_group') or 'Uncategorized'
            if group not in dead_by_group:
                dead_by_group[group] = {'item_group': group, 'count': 0, 'value': 0}
            dead_by_group[group]['count'] += 1
            dead_by_group[group]['value'] += float(item.get('stock_value') or 0)
        
        return {
            "total_items": len(dead_stock),
            "total_value": total_dead_stock_value,
            "items": dead_stock[:20],
            "by_product_group": sorted(dead_by_group.values(), key=lambda x: x['value'], reverse=True)
        }
    
    def _calculate_procurement_insights(self) -> Dict[str, Any]:
        """Calculate procurement and supplier insights"""
        supplier_performance = frappe.db.sql("""
            SELECT 
                po.supplier,
                s.supplier_name,
                COUNT(DISTINCT po.name) as order_count,
                SUM(po.grand_total) as total_value,
                AVG(DATEDIFF(COALESCE(pr.posting_date, CURDATE()), po.transaction_date)) as avg_lead_time
            FROM `tabPurchase Order` po
            LEFT JOIN `tabSupplier` s ON po.supplier = s.name
            LEFT JOIN `tabPurchase Receipt` pr ON pr.supplier = po.supplier AND pr.docstatus = 1
            WHERE po.docstatus = 1
                AND po.transaction_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY po.supplier, s.supplier_name
            ORDER BY total_value DESC
            LIMIT 15
        """, as_dict=True)
        
        pending_orders = frappe.db.sql("""
            SELECT 
                po.name,
                po.supplier,
                po.transaction_date,
                po.grand_total,
                DATEDIFF(CURDATE(), po.transaction_date) as days_pending,
                po.status
            FROM `tabPurchase Order` po
            WHERE po.docstatus = 1
                AND po.status NOT IN ('Completed', 'Closed', 'Cancelled')
            ORDER BY days_pending DESC
            LIMIT 20
        """, as_dict=True)
        
        reorder_needed = frappe.db.sql("""
            SELECT 
                i.item_code,
                i.item_name,
                i.item_group,
                COALESCE(SUM(b.actual_qty), 0) as current_stock,
                COALESCE(i.safety_stock, 0) as safety_stock,
                COALESCE(MAX(ir.warehouse_reorder_level), 0) as reorder_level,
                COALESCE(MAX(sales.avg_daily_sales), 0) as avg_daily_demand
            FROM `tabItem` i
            LEFT JOIN `tabBin` b ON i.item_code = b.item_code
            LEFT JOIN (
                SELECT parent as item_code, MAX(warehouse_reorder_level) as warehouse_reorder_level
                FROM `tabItem Reorder`
                GROUP BY parent
            ) ir ON i.item_code = ir.item_code
            LEFT JOIN (
                SELECT sii.item_code, SUM(sii.qty) / 90 as avg_daily_sales
                FROM `tabSales Invoice Item` sii
                JOIN `tabSales Invoice` si ON sii.parent = si.name
                WHERE si.docstatus = 1 
                    AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
                GROUP BY sii.item_code
            ) sales ON i.item_code = sales.item_code
            WHERE i.is_stock_item = 1 AND i.disabled = 0
            GROUP BY i.item_code, i.item_name, i.item_group, i.safety_stock
            HAVING current_stock <= COALESCE(reorder_level, avg_daily_demand * 14)
                AND avg_daily_demand > 0
            ORDER BY avg_daily_demand DESC
            LIMIT 20
        """, as_dict=True)
        
        return {
            "supplier_performance": supplier_performance,
            "pending_orders": pending_orders,
            "pending_orders_count": len(pending_orders),
            "reorder_needed": reorder_needed,
            "reorder_count": len(reorder_needed)
        }
    
    def _get_abc_xyz_data(self) -> Optional[Dict[str, Any]]:
        """Get ABC/XYZ classification data - runs automatically if no cache"""
        try:
            from insights.ml.abc_xyz_classification import ABCXYZClassification
            model = ABCXYZClassification()
            cached = model.get_cached_results("abc_xyz_classification")
            
            # If no cached results, run the classification
            if not cached:
                frappe.log_error("Running ABC/XYZ Classification automatically", "ML Inventory")
                result = model.train()
                if result.get('status') == 'success':
                    cached = result
            
            if cached and cached.get('status') == 'success':
                # Sanitize top_items to remove Infinity values (not JSON-serializable)
                top_items = []
                for item in cached.get('items', [])[:50]:
                    sanitized = dict(item)
                    # Replace Infinity with 999 for cv field
                    if sanitized.get('cv') is not None:
                        import math
                        if math.isinf(sanitized['cv']) or math.isnan(sanitized['cv']):
                            sanitized['cv'] = 999
                    top_items.append(sanitized)
                
                return {
                    "classification_date": cached.get('analysis_date'),
                    "total_items": cached.get('total_items', 0),
                    "summary": {
                        "a_count": sum(1 for i in cached.get('items', []) if i.get('abc_class') == 'A'),
                        "b_count": sum(1 for i in cached.get('items', []) if i.get('abc_class') == 'B'),
                        "c_count": sum(1 for i in cached.get('items', []) if i.get('abc_class') == 'C'),
                        "x_count": sum(1 for i in cached.get('items', []) if i.get('xyz_class') == 'X'),
                        "y_count": sum(1 for i in cached.get('items', []) if i.get('xyz_class') == 'Y'),
                        "z_count": sum(1 for i in cached.get('items', []) if i.get('xyz_class') == 'Z'),
                    },
                    "abc_summary": cached.get('abc_summary', []),
                    "xyz_summary": cached.get('xyz_summary', []),
                    "matrix": cached.get('combined_summary', []),
                    "top_items": top_items
                }
            return None
        except Exception as e:
            frappe.log_error(f"ABC/XYZ Classification error: {str(e)}", "ML Inventory")
            return None
    
    def _get_demand_forecast_data(self) -> Optional[Dict[str, Any]]:
        """Get demand forecasting data"""
        try:
            from insights.ml.demand_forecasting import DemandForecasting
            model = DemandForecasting()
            cached = model.get_cached_results("demand_forecast")
            if cached:
                return {
                    "forecast_date": cached.get('forecast_date'),
                    "reorder_alerts": cached.get('reorder_alerts', [])[:10],
                    "summary": {
                        "total_items": cached.get('total_items_analyzed', 0),
                        "reorder_now_count": cached.get('reorder_now_count', 0),
                        "monitor_count": cached.get('monitor_count', 0),
                        "adequate_count": cached.get('adequate_count', 0)
                    }
                }
            return None
        except Exception as e:
            return None


def run_inventory_intelligence(refresh: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Run inventory intelligence analysis"""
    model = InventoryIntelligence(date_filter=date_filter)
    if not refresh:
        cached = model.get_cached_results(f"inventory_intelligence_{date_filter}")
        if cached:
            return cached
    return model.train()
