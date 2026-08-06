# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Sales Intelligence Analytics
Comprehensive sales analytics including revenue metrics, payment mix, rep performance, 
dimensional analysis, and margin tracking
"""

import frappe
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict
from insights.api.ml import get_date_filter_sql
from insights.ml.base import BaseMLModel
from insights.ml.sales_source_analytics import (
    get_source_attributed_sales,
    get_quotation_analytics,
    get_territory_performance,
)


class SalesIntelligence(BaseMLModel):
    """
    Sales Intelligence Analytics Engine
    
    Provides:
    - Revenue Metrics (daily/weekly/monthly, AOV, transaction frequency)
    - Cash vs Credit Payment Mix Analysis
    - Individual Sales Rep Performance
    - Month-over-Month and Year-over-Year Comparisons
    - Revenue by Product Group, Customer Segment, Territory
    - Gross Margin Analysis by Product Group
    - Pipeline Analytics (Quote-to-Order Conversion)
    - Fulfillment Metrics (DSO, Backlog)
    - Integration with existing ML forecasts
    """
    
    def __init__(self, date_filter: str = '12m'):
        super().__init__()
        self.model_name = "SalesIntelligence"
        self.date_filter = date_filter
        # Generate SQL date filters based on the date_filter parameter
        self.DATE_FILTER_24M = get_date_filter_sql('24m', 'posting_date', 'si')
        self.DATE_FILTER_12M = get_date_filter_sql(date_filter, 'posting_date', 'si')
        
    # ==================== DATA COLLECTION ====================
    
    def _get_sales_transactions(self) -> pd.DataFrame:
        """Get sales invoice data with payment mode detection"""
        query = f"""
            SELECT 
                si.name as invoice_id,
                si.posting_date,
                si.customer,
                si.customer_name,
                si.customer_group,
                si.territory,
                si.grand_total,
                si.net_total,
                si.base_grand_total,
                si.total_qty,
                si.outstanding_amount,
                si.status,
                si.is_return,
                si.sales_partner,
                si.total_commission,
                si.conversion_rate,
                CASE 
                    WHEN si.outstanding_amount = 0 AND si.grand_total > 0 THEN 'Cash'
                    WHEN si.outstanding_amount > 0 THEN 'Credit'
                    ELSE 'Other'
                END as payment_mode,
                YEAR(si.posting_date) as year,
                MONTH(si.posting_date) as month,
                WEEK(si.posting_date) as week,
                DAYOFWEEK(si.posting_date) as day_of_week,
                DATE(si.posting_date) as sale_date
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1
                {self.DATE_FILTER_24M}
            ORDER BY si.posting_date DESC
        """
        return self.get_training_data(query)
    
    def _get_sales_invoice_items(self) -> pd.DataFrame:
        """Get item-level sales data with gross profit"""
        query = f"""
            SELECT 
                sii.parent as invoice_id,
                si.posting_date,
                si.customer,
                si.customer_group,
                si.territory,
                sii.item_code,
                sii.item_name,
                sii.item_group,
                sii.brand,
                sii.qty,
                sii.rate,
                sii.amount,
                sii.net_amount,
                (sii.net_amount - (sii.qty * COALESCE(sii.incoming_rate, 0))) as gross_profit,
                YEAR(si.posting_date) as year,
                MONTH(si.posting_date) as month
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.docstatus = 1 AND si.is_return = 0
                {self.DATE_FILTER_24M}
        """
        return self.get_training_data(query)
    
    def _get_sales_team_data(self) -> pd.DataFrame:
        """Get sales rep performance data from invoice owner field"""
        # Use owner field as sales rep (not Sales Team child table)
        query = f"""
            SELECT 
                si.owner as sales_person,
                COALESCE(u.full_name, si.owner) as sales_person_name,
                100.0 as allocated_percentage,
                si.grand_total as allocated_amount,
                0.0 as commission_rate,
                0.0 as incentives,
                si.name as invoice_id,
                si.posting_date,
                si.grand_total,
                si.customer,
                YEAR(si.posting_date) as year,
                MONTH(si.posting_date) as month
            FROM `tabSales Invoice` si
            LEFT JOIN `tabUser` u ON si.owner = u.name
            WHERE si.docstatus = 1
                {self.DATE_FILTER_12M}
        """
        return self.get_training_data(query)
    
    def _get_quotation_data(self) -> pd.DataFrame:
        """Get quotation data for pipeline analysis"""
        query = """
            SELECT 
                q.name as quotation_id,
                q.transaction_date,
                q.valid_till,
                q.party_name as customer,
                q.grand_total,
                q.status,
                q.order_type,
                CASE WHEN q.status = 'Ordered' THEN 1 ELSE 0 END as converted,
                CASE WHEN q.status = 'Lost' THEN 1 ELSE 0 END as lost,
                DATEDIFF(CURDATE(), q.transaction_date) as age_days,
                YEAR(q.transaction_date) as year,
                MONTH(q.transaction_date) as month
            FROM `tabQuotation` q
            WHERE q.docstatus = 1 
                AND q.quotation_to = 'Customer'
                AND q.transaction_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
        """
        return self.get_training_data(query)
    
    def _get_sales_orders(self) -> pd.DataFrame:
        """Get sales order data for fulfillment metrics"""
        query = """
            SELECT 
                so.name as order_id,
                so.transaction_date,
                so.delivery_date,
                so.customer,
                so.grand_total,
                so.status,
                so.per_delivered,
                so.per_billed,
                so.delivery_status,
                so.billing_status,
                CASE 
                    WHEN so.per_delivered >= 100 THEN 'Fulfilled'
                    WHEN so.per_delivered > 0 THEN 'Partial'
                    ELSE 'Pending'
                END as fulfillment_status,
                YEAR(so.transaction_date) as year,
                MONTH(so.transaction_date) as month
            FROM `tabSales Order` so
            WHERE so.docstatus = 1
                AND so.transaction_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
        """
        return self.get_training_data(query)
    
    # ==================== REVENUE METRICS ====================
    
    def calculate_revenue_metrics(self, sales_df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate comprehensive revenue metrics"""
        if sales_df.empty:
            return self._empty_revenue_metrics()
        
        # Filter out returns for revenue calculations
        revenue_df = sales_df[sales_df['is_return'] == 0].copy()
        
        # Convert posting_date to datetime
        revenue_df['posting_date'] = pd.to_datetime(revenue_df['posting_date'])
        revenue_df['sale_date'] = pd.to_datetime(revenue_df['sale_date'])
        
        # Current period metrics
        today = datetime.now().date()
        current_month_start = today.replace(day=1)
        last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
        last_year_same_month = current_month_start.replace(year=current_month_start.year - 1)
        
        # Total metrics
        total_revenue = float(revenue_df['grand_total'].sum())
        total_transactions = len(revenue_df)
        avg_order_value = float(revenue_df['grand_total'].mean()) if total_transactions > 0 else 0
        
        # Daily sales (last 30 days)
        last_30_days = revenue_df[revenue_df['sale_date'] >= (pd.Timestamp(today) - timedelta(days=30))]
        daily_sales = last_30_days.groupby('sale_date').agg({
            'grand_total': 'sum',
            'invoice_id': 'count'
        }).reset_index()
        daily_sales.columns = ['date', 'revenue', 'transactions']
        daily_sales['date'] = daily_sales['date'].astype(str)
        
        # Weekly sales (last 12 weeks)
        revenue_df['year_week'] = revenue_df['posting_date'].dt.isocalendar().week.astype(str) + '-' + revenue_df['posting_date'].dt.isocalendar().year.astype(str)
        weekly_sales = revenue_df.groupby(['year', 'week']).agg({
            'grand_total': 'sum',
            'invoice_id': 'count'
        }).reset_index().tail(12)
        weekly_sales.columns = ['year', 'week', 'revenue', 'transactions']
        
        # Monthly sales (last 24 months)
        monthly_sales = revenue_df.groupby(['year', 'month']).agg({
            'grand_total': 'sum',
            'invoice_id': 'count',
            'customer': 'nunique'
        }).reset_index()
        monthly_sales.columns = ['year', 'month', 'revenue', 'transactions', 'unique_customers']
        monthly_sales['period'] = monthly_sales.apply(lambda x: f"{int(x['year'])}-{int(x['month']):02d}", axis=1)
        
        # Transaction frequency (average days between purchases per customer)
        customer_frequency = revenue_df.groupby('customer').agg({
            'posting_date': ['min', 'max', 'count']
        })
        customer_frequency.columns = ['first_purchase', 'last_purchase', 'order_count']
        customer_frequency['days_span'] = (customer_frequency['last_purchase'] - customer_frequency['first_purchase']).dt.days
        repeat_customers = customer_frequency[customer_frequency['order_count'] > 1]
        avg_days_between_orders = float(repeat_customers['days_span'].sum() / repeat_customers['order_count'].sum()) if len(repeat_customers) > 0 else 0
        
        return {
            'total_revenue': total_revenue,
            'total_transactions': total_transactions,
            'avg_order_value': round(avg_order_value, 2),
            'avg_days_between_orders': round(avg_days_between_orders, 1),
            'unique_customers': int(revenue_df['customer'].nunique()),
            'daily_sales': daily_sales.to_dict('records'),
            'weekly_sales': weekly_sales.to_dict('records'),
            'monthly_sales': monthly_sales.to_dict('records'),
        }
    
    def _empty_revenue_metrics(self) -> Dict[str, Any]:
        return {
            'total_revenue': 0,
            'total_transactions': 0,
            'avg_order_value': 0,
            'avg_days_between_orders': 0,
            'unique_customers': 0,
            'daily_sales': [],
            'weekly_sales': [],
            'monthly_sales': [],
        }
    
    # ==================== PAYMENT MIX ANALYSIS ====================
    
    def calculate_payment_mix(self, sales_df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze cash vs credit payment ratios"""
        if sales_df.empty:
            return {'cash_ratio': 0, 'credit_ratio': 0, 'daily_mix': [], 'monthly_mix': []}
        
        revenue_df = sales_df[sales_df['is_return'] == 0].copy()
        revenue_df['sale_date'] = pd.to_datetime(revenue_df['sale_date'])
        
        # Overall mix
        total = revenue_df['grand_total'].sum()
        cash_total = revenue_df[revenue_df['payment_mode'] == 'Cash']['grand_total'].sum()
        credit_total = revenue_df[revenue_df['payment_mode'] == 'Credit']['grand_total'].sum()
        
        cash_ratio = (cash_total / total * 100) if total > 0 else 0
        credit_ratio = (credit_total / total * 100) if total > 0 else 0
        
        # Daily mix (last 30 days)
        today = datetime.now().date()
        last_30 = revenue_df[revenue_df['sale_date'] >= (pd.Timestamp(today) - timedelta(days=30))]
        daily_mix = last_30.groupby(['sale_date', 'payment_mode'])['grand_total'].sum().unstack(fill_value=0).reset_index()
        if 'Cash' not in daily_mix.columns:
            daily_mix['Cash'] = 0
        if 'Credit' not in daily_mix.columns:
            daily_mix['Credit'] = 0
        daily_mix['total'] = daily_mix['Cash'] + daily_mix['Credit']
        daily_mix['cash_pct'] = (daily_mix['Cash'] / daily_mix['total'] * 100).fillna(0)
        daily_mix['sale_date'] = daily_mix['sale_date'].astype(str)
        
        # Monthly mix
        monthly_mix = revenue_df.groupby(['year', 'month', 'payment_mode'])['grand_total'].sum().unstack(fill_value=0).reset_index()
        if 'Cash' not in monthly_mix.columns:
            monthly_mix['Cash'] = 0
        if 'Credit' not in monthly_mix.columns:
            monthly_mix['Credit'] = 0
        monthly_mix['total'] = monthly_mix['Cash'] + monthly_mix['Credit']
        monthly_mix['cash_pct'] = (monthly_mix['Cash'] / monthly_mix['total'] * 100).fillna(0)
        monthly_mix['period'] = monthly_mix.apply(lambda x: f"{int(x['year'])}-{int(x['month']):02d}", axis=1)
        
        # Today's mix
        today_df = revenue_df[revenue_df['sale_date'] == pd.Timestamp(today)]
        today_total = today_df['grand_total'].sum()
        today_cash = today_df[today_df['payment_mode'] == 'Cash']['grand_total'].sum()
        today_cash_pct = (today_cash / today_total * 100) if today_total > 0 else 0
        
        return {
            'cash_ratio': round(cash_ratio, 1),
            'credit_ratio': round(credit_ratio, 1),
            'cash_total': float(cash_total),
            'credit_total': float(credit_total),
            'today_cash_pct': round(today_cash_pct, 1),
            'today_total': float(today_total),
            'daily_mix': daily_mix[['sale_date', 'Cash', 'Credit', 'total', 'cash_pct']].to_dict('records'),
            'monthly_mix': monthly_mix[['period', 'Cash', 'Credit', 'total', 'cash_pct']].to_dict('records'),
        }
    
    # ==================== SALES REP PERFORMANCE ====================
    
    def analyze_sales_reps(self, sales_team_df: pd.DataFrame, quotation_df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze individual sales rep performance"""
        if sales_team_df.empty:
            return {'reps': [], 'top_performer': None, 'total_reps': 0}
        
        sales_team_df['posting_date'] = pd.to_datetime(sales_team_df['posting_date'])
        
        # Build sales_person to full_name mapping
        name_mapping = {}
        if 'sales_person_name' in sales_team_df.columns:
            name_df = sales_team_df.drop_duplicates('sales_person')[['sales_person', 'sales_person_name']]
            name_mapping = dict(zip(name_df['sales_person'], name_df['sales_person_name']))
        
        # Aggregate by sales person
        rep_metrics = sales_team_df.groupby('sales_person').agg({
            'allocated_amount': 'sum',
            'invoice_id': 'nunique',
            'customer': 'nunique',
            'incentives': 'sum',
            'posting_date': ['min', 'max']
        })
        rep_metrics.columns = ['total_revenue', 'total_orders', 'unique_customers', 'total_incentives', 'first_sale', 'last_sale']
        rep_metrics = rep_metrics.reset_index()
        
        # Calculate AOV
        rep_metrics['avg_order_value'] = (rep_metrics['total_revenue'] / rep_metrics['total_orders']).fillna(0)
        
        # Monthly trend per rep (last 6 months)
        rep_monthly = sales_team_df.groupby(['sales_person', 'year', 'month']).agg({
            'allocated_amount': 'sum',
            'invoice_id': 'nunique'
        }).reset_index()
        rep_monthly.columns = ['sales_person', 'year', 'month', 'revenue', 'orders']
        rep_monthly['period'] = rep_monthly.apply(lambda x: f"{int(x['year'])}-{int(x['month']):02d}", axis=1)
        
        # Build rep trends dict
        rep_trends = {}
        for rep in rep_metrics['sales_person'].unique():
            rep_data = rep_monthly[rep_monthly['sales_person'] == rep].tail(6)
            rep_trends[rep] = rep_data[['period', 'revenue', 'orders']].to_dict('records')
        
        # Rank reps
        rep_metrics = rep_metrics.sort_values('total_revenue', ascending=False)
        rep_metrics['rank'] = range(1, len(rep_metrics) + 1)
        
        # Convert to records
        reps_list = []
        for _, row in rep_metrics.iterrows():
            sales_person_email = row['sales_person']
            full_name = name_mapping.get(sales_person_email, sales_person_email)
            reps_list.append({
                'sales_person': sales_person_email,
                'sales_person_name': full_name,
                'rank': int(row['rank']),
                'total_revenue': float(row['total_revenue']),
                'total_orders': int(row['total_orders']),
                'unique_customers': int(row['unique_customers']),
                'avg_order_value': round(float(row['avg_order_value']), 2),
                'total_incentives': float(row['total_incentives']),
                'trend': rep_trends.get(row['sales_person'], [])
            })
        
        top_performer = reps_list[0] if reps_list else None
        
        return {
            'reps': reps_list,
            'top_performer': top_performer,
            'total_reps': len(reps_list),
            'total_team_revenue': float(rep_metrics['total_revenue'].sum()),
        }
    
    # ==================== MOM & YOY COMPARISONS ====================
    
    def calculate_comparisons(self, sales_df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate month-over-month and year-over-year comparisons"""
        if sales_df.empty:
            return self._empty_comparisons()
        
        revenue_df = sales_df[sales_df['is_return'] == 0].copy()
        revenue_df['posting_date'] = pd.to_datetime(revenue_df['posting_date'])
        
        today = datetime.now().date()
        
        # Current month
        current_month_start = today.replace(day=1)
        current_month_end = today
        
        # Last month, aligned to the same day-of-month.
        #
        # Comparing an elapsed-so-far current month against a *complete*
        # previous month reported -98.3% growth on the 6th of August: 6 days of
        # trading measured against 31. Month-to-date must be compared with the
        # same slice of the previous month for the number to mean anything.
        last_month_final_day = current_month_start - timedelta(days=1)
        last_month_start = last_month_final_day.replace(day=1)
        last_month_end = min(
            last_month_start + timedelta(days=today.day - 1),
            last_month_final_day,
        )
        
        # Same month last year
        last_year_month_start = current_month_start.replace(year=current_month_start.year - 1)
        last_year_month_end = last_year_month_start.replace(day=min(today.day, 28))  # Safe day
        
        # Calculate metrics
        current_month = revenue_df[
            (revenue_df['posting_date'].dt.date >= current_month_start) & 
            (revenue_df['posting_date'].dt.date <= current_month_end)
        ]
        last_month = revenue_df[
            (revenue_df['posting_date'].dt.date >= last_month_start) & 
            (revenue_df['posting_date'].dt.date <= last_month_end)
        ]
        last_year_month = revenue_df[
            (revenue_df['posting_date'].dt.date >= last_year_month_start) & 
            (revenue_df['posting_date'].dt.date <= last_year_month_end)
        ]
        
        current_revenue = float(current_month['grand_total'].sum())
        last_month_revenue = float(last_month['grand_total'].sum())
        last_year_revenue = float(last_year_month['grand_total'].sum())
        
        # Calculate growth rates
        mom_growth = ((current_revenue - last_month_revenue) / last_month_revenue * 100) if last_month_revenue > 0 else 0
        yoy_growth = ((current_revenue - last_year_revenue) / last_year_revenue * 100) if last_year_revenue > 0 else 0
        
        # Transaction counts
        current_txns = len(current_month)
        last_month_txns = len(last_month)
        last_year_txns = len(last_year_month)
        
        mom_txn_growth = ((current_txns - last_month_txns) / last_month_txns * 100) if last_month_txns > 0 else 0
        yoy_txn_growth = ((current_txns - last_year_txns) / last_year_txns * 100) if last_year_txns > 0 else 0
        
        # AOV comparison
        current_aov = float(current_month['grand_total'].mean()) if current_txns > 0 else 0
        last_month_aov = float(last_month['grand_total'].mean()) if last_month_txns > 0 else 0
        last_year_aov = float(last_year_month['grand_total'].mean()) if last_year_txns > 0 else 0
        
        # Monthly trend (last 12 months)
        monthly_revenue = revenue_df.groupby(['year', 'month']).agg({
            'grand_total': 'sum'
        }).reset_index()
        monthly_revenue['period'] = monthly_revenue.apply(lambda x: f"{int(x['year'])}-{int(x['month']):02d}", axis=1)
        monthly_revenue = monthly_revenue.sort_values('period').tail(13)
        
        # Calculate MoM for each month
        monthly_revenue['prev_revenue'] = monthly_revenue['grand_total'].shift(1)
        monthly_revenue['mom_pct'] = ((monthly_revenue['grand_total'] - monthly_revenue['prev_revenue']) / monthly_revenue['prev_revenue'] * 100).fillna(0)
        
        return {
            'current_month': {
                'revenue': current_revenue,
                'transactions': current_txns,
                'aov': round(current_aov, 2),
                'period': current_month_start.strftime('%Y-%m')
            },
            'last_month': {
                'revenue': last_month_revenue,
                'transactions': last_month_txns,
                'aov': round(last_month_aov, 2),
                'period': last_month_start.strftime('%Y-%m')
            },
            'last_year_same_month': {
                'revenue': last_year_revenue,
                'transactions': last_year_txns,
                'aov': round(last_year_aov, 2),
                'period': last_year_month_start.strftime('%Y-%m')
            },
            'mom_growth': round(mom_growth, 1),
            'yoy_growth': round(yoy_growth, 1),
            'mom_txn_growth': round(mom_txn_growth, 1),
            'yoy_txn_growth': round(yoy_txn_growth, 1),
            'monthly_trend': monthly_revenue[['period', 'grand_total', 'mom_pct']].tail(12).rename(
                columns={'grand_total': 'revenue'}
            ).to_dict('records'),
        }
    
    def _empty_comparisons(self) -> Dict[str, Any]:
        return {
            'current_month': {'revenue': 0, 'transactions': 0, 'aov': 0, 'period': ''},
            'last_month': {'revenue': 0, 'transactions': 0, 'aov': 0, 'period': ''},
            'last_year_same_month': {'revenue': 0, 'transactions': 0, 'aov': 0, 'period': ''},
            'mom_growth': 0, 'yoy_growth': 0, 'mom_txn_growth': 0, 'yoy_txn_growth': 0,
            'monthly_trend': [],
        }
    
    # ==================== DIMENSIONAL ANALYSIS ====================
    
    def analyze_by_dimensions(self, sales_df: pd.DataFrame, items_df: pd.DataFrame) -> Dict[str, Any]:
        """Revenue breakdown by product group, customer segment, territory"""
        if sales_df.empty:
            return {'by_product_group': [], 'by_customer_segment': [], 'by_territory': []}
        
        revenue_df = sales_df[sales_df['is_return'] == 0].copy()
        
        # Calculate total revenue first (used for all percentage calculations)
        total_revenue = float(revenue_df['grand_total'].sum())
        
        # Fill NULL values in grouping columns to include them in aggregations
        revenue_df['customer_group'] = revenue_df['customer_group'].fillna('Uncategorized')
        revenue_df['territory'] = revenue_df['territory'].fillna('Unassigned')
        
        # By Customer Group (Segment)
        by_segment = revenue_df.groupby('customer_group').agg({
            'grand_total': 'sum',
            'invoice_id': 'count',
            'customer': 'nunique'
        }).reset_index()
        by_segment.columns = ['customer_group', 'revenue', 'transactions', 'customers']
        by_segment = by_segment.sort_values('revenue', ascending=False)
        by_segment['pct'] = (by_segment['revenue'] / total_revenue * 100).round(1)
        
        # By Territory
        by_territory = revenue_df.groupby('territory').agg({
            'grand_total': 'sum',
            'invoice_id': 'count',
            'customer': 'nunique'
        }).reset_index()
        by_territory.columns = ['territory', 'revenue', 'transactions', 'customers']
        by_territory = by_territory.sort_values('revenue', ascending=False)
        by_territory['pct'] = (by_territory['revenue'] / total_revenue * 100).round(1)
        
        # By Product Group (from items)
        by_product_group = []
        if not items_df.empty:
            pg_data = items_df.groupby('item_group').agg({
                'amount': 'sum',
                'qty': 'sum',
                'invoice_id': 'nunique',
                'item_code': 'nunique'
            }).reset_index()
            pg_data.columns = ['item_group', 'revenue', 'qty_sold', 'transactions', 'unique_items']
            pg_data = pg_data.sort_values('revenue', ascending=False)
            items_total = pg_data['revenue'].sum()
            pg_data['pct'] = (pg_data['revenue'] / items_total * 100).round(1)
            by_product_group = pg_data.head(20).to_dict('records')
        
        return {
            'by_product_group': by_product_group,
            'by_customer_segment': by_segment.to_dict('records'),
            'by_territory': by_territory.to_dict('records'),
            'total_revenue': float(total_revenue),
        }
    
    # ==================== MARGIN ANALYSIS ====================
    
    def analyze_margins(self, items_df: pd.DataFrame) -> Dict[str, Any]:
        """Gross margin analysis by product group and item"""
        if items_df.empty:
            return {'overall_margin': 0, 'by_product_group': [], 'top_margin_items': [], 'low_margin_items': []}
        
        # Overall margin
        total_revenue = items_df['amount'].sum()
        total_profit = items_df['gross_profit'].sum()
        overall_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        # By Product Group
        pg_margin = items_df.groupby('item_group').agg({
            'amount': 'sum',
            'gross_profit': 'sum',
            'qty': 'sum',
            'item_code': 'nunique'
        }).reset_index()
        pg_margin.columns = ['item_group', 'revenue', 'gross_profit', 'qty_sold', 'unique_items']
        pg_margin['margin_pct'] = (pg_margin['gross_profit'] / pg_margin['revenue'] * 100).fillna(0).round(1)
        pg_margin = pg_margin.sort_values('revenue', ascending=False)
        
        # By Item (for top/bottom margin items)
        item_margin = items_df.groupby(['item_code', 'item_name', 'item_group']).agg({
            'amount': 'sum',
            'gross_profit': 'sum',
            'qty': 'sum'
        }).reset_index()
        item_margin.columns = ['item_code', 'item_name', 'item_group', 'revenue', 'gross_profit', 'qty_sold']
        item_margin['margin_pct'] = (item_margin['gross_profit'] / item_margin['revenue'] * 100).fillna(0).round(1)
        
        # Filter items with meaningful revenue (top 50% by revenue)
        revenue_threshold = item_margin['revenue'].quantile(0.5)
        significant_items = item_margin[item_margin['revenue'] >= revenue_threshold]
        
        # Top margin items (highest margin %)
        top_margin = significant_items.nlargest(10, 'margin_pct')
        
        # Low margin items (lowest margin %, but positive revenue)
        low_margin = significant_items[significant_items['revenue'] > 0].nsmallest(10, 'margin_pct')
        
        # Margin by month trend
        items_df['period'] = items_df.apply(lambda x: f"{int(x['year'])}-{int(x['month']):02d}", axis=1)
        monthly_margin = items_df.groupby('period').agg({
            'amount': 'sum',
            'gross_profit': 'sum'
        }).reset_index()
        monthly_margin['margin_pct'] = (monthly_margin['gross_profit'] / monthly_margin['amount'] * 100).fillna(0).round(1)
        
        return {
            'overall_margin': round(overall_margin, 1),
            'total_revenue': float(total_revenue),
            'total_profit': float(total_profit),
            'by_product_group': pg_margin.to_dict('records'),
            'top_margin_items': top_margin.to_dict('records'),
            'low_margin_items': low_margin.to_dict('records'),
            'margin_trend': monthly_margin.tail(12).to_dict('records'),
        }
    
    # ==================== PIPELINE ANALYSIS ====================
    
    def analyze_pipeline(self, quotation_df: pd.DataFrame) -> Dict[str, Any]:
        """Quotation-to-order conversion and pipeline analysis"""
        if quotation_df.empty:
            return {'conversion_rate': 0, 'pipeline_value': 0, 'quotes': [], 'by_status': []}
        
        total_quotes = len(quotation_df)
        converted = int(quotation_df['converted'].sum())
        lost = int(quotation_df['lost'].sum())
        open_quotes = total_quotes - converted - lost
        
        conversion_rate = (converted / total_quotes * 100) if total_quotes > 0 else 0
        loss_rate = (lost / total_quotes * 100) if total_quotes > 0 else 0
        
        # Pipeline value (open quotes)
        pipeline_value = float(quotation_df[quotation_df['status'].isin(['Open', 'Submitted'])]['grand_total'].sum())
        
        # Average quote value
        avg_quote_value = float(quotation_df['grand_total'].mean())
        
        # By status
        by_status = quotation_df.groupby('status').agg({
            'quotation_id': 'count',
            'grand_total': 'sum'
        }).reset_index()
        by_status.columns = ['status', 'count', 'value']
        
        # Monthly conversion trend
        monthly_conversion = quotation_df.groupby(['year', 'month']).agg({
            'quotation_id': 'count',
            'converted': 'sum',
            'grand_total': 'sum'
        }).reset_index()
        monthly_conversion.columns = ['year', 'month', 'total_quotes', 'converted', 'total_value']
        monthly_conversion['conversion_rate'] = (monthly_conversion['converted'] / monthly_conversion['total_quotes'] * 100).fillna(0).round(1)
        monthly_conversion['period'] = monthly_conversion.apply(lambda x: f"{int(x['year'])}-{int(x['month']):02d}", axis=1)
        
        return {
            'total_quotes': total_quotes,
            'converted': converted,
            'lost': lost,
            'open_quotes': open_quotes,
            'conversion_rate': round(conversion_rate, 1),
            'loss_rate': round(loss_rate, 1),
            'pipeline_value': pipeline_value,
            'avg_quote_value': round(avg_quote_value, 2),
            'by_status': by_status.to_dict('records'),
            'monthly_trend': monthly_conversion[['period', 'total_quotes', 'converted', 'conversion_rate']].tail(12).to_dict('records'),
        }
    
    # ==================== FULFILLMENT METRICS ====================
    
    def analyze_fulfillment(self, orders_df: pd.DataFrame, sales_df: pd.DataFrame) -> Dict[str, Any]:
        """Order fulfillment and DSO analysis"""
        result = {
            'fulfillment_rate': 0,
            'backlog_value': 0,
            'dso': 0,
            'by_status': [],
            'fulfillment_trend': []
        }
        
        if not orders_df.empty:
            total_orders = len(orders_df)
            fulfilled = len(orders_df[orders_df['fulfillment_status'] == 'Fulfilled'])
            partial = len(orders_df[orders_df['fulfillment_status'] == 'Partial'])
            pending = len(orders_df[orders_df['fulfillment_status'] == 'Pending'])
            
            fulfillment_rate = (fulfilled / total_orders * 100) if total_orders > 0 else 0
            
            # Backlog (unfulfilled orders value)
            backlog_df = orders_df[orders_df['fulfillment_status'].isin(['Pending', 'Partial'])]
            backlog_value = float(backlog_df['grand_total'].sum() * (1 - backlog_df['per_delivered'].mean() / 100)) if len(backlog_df) > 0 else 0
            
            result['fulfillment_rate'] = round(fulfillment_rate, 1)
            result['backlog_value'] = backlog_value
            result['total_orders'] = total_orders
            result['fulfilled'] = fulfilled
            result['partial'] = partial
            result['pending'] = pending
            
            # By status
            by_status = orders_df.groupby('fulfillment_status').agg({
                'order_id': 'count',
                'grand_total': 'sum'
            }).reset_index()
            by_status.columns = ['status', 'count', 'value']
            result['by_status'] = by_status.to_dict('records')
        
        # DSO (Days Sales Outstanding)
        if not sales_df.empty:
            revenue_df = sales_df[sales_df['is_return'] == 0].copy()
            total_receivables = float(revenue_df['outstanding_amount'].sum())
            
            # Average daily sales (last 90 days)
            revenue_df['posting_date'] = pd.to_datetime(revenue_df['posting_date'])
            last_90 = revenue_df[revenue_df['posting_date'] >= (datetime.now() - timedelta(days=90))]
            avg_daily_sales = float(last_90['grand_total'].sum() / 90) if len(last_90) > 0 else 0
            
            dso = (total_receivables / avg_daily_sales) if avg_daily_sales > 0 else 0
            
            result['dso'] = round(dso, 1)
            result['total_receivables'] = total_receivables
            result['avg_daily_sales'] = round(avg_daily_sales, 2)
        
        return result

    # ==================== SOURCE ATTRIBUTION ====================

    def get_source_attributed_sales(self, period_start: str, period_end: str) -> List[Dict[str, Any]]:
        """Get revenue, orders, and profit attributed to each lead source."""
        return get_source_attributed_sales(period_start, period_end)

    def get_quotation_analytics(self, period_start: str, period_end: str) -> Dict[str, Any]:
        """Get quotation funnel analytics."""
        return get_quotation_analytics(period_start, period_end)

    def get_territory_performance(self, period_start: str, period_end: str) -> List[Dict[str, Any]]:
        """Get sales performance by territory."""
        return get_territory_performance(period_start, period_end)

    # ==================== AGGREGATE FORECASTS ====================

    def aggregate_forecasts(self, refresh: bool = False) -> Dict[str, Any]:
        """Pull forecasts from existing ML models: Sales Forecasting and Demand Forecasting
        
        Args:
            refresh: If True, retrain forecasts if cache is empty or stale
        """
        forecasts = {
            'sales_forecast': None,
            'demand_forecast': None
        }
        
        try:
            # Sales Forecast (90 days)
            from insights.ml.sales_forecasting import SalesForecasting
            sf_model = SalesForecasting()
            sf_cached = sf_model.get_cached_results("sales_forecast")
            
            # Auto-train if refresh requested and no cache
            if not sf_cached and refresh:
                frappe.logger().info("Auto-training sales forecast...")
                sf_cached = sf_model.train()
            
            if sf_cached:
                forecast_data = sf_cached.get('forecast', [])[:90]  # Next 90 days
                # Calculate 90-day total
                total_90d = sum(f.get('yhat', 0) for f in forecast_data) if forecast_data else 0
                forecasts['sales_forecast'] = {
                    'forecast_summary': {
                        'total_forecast': total_90d,
                        'days': len(forecast_data)
                    },
                    'forecast': forecast_data,
                    'method': sf_cached.get('method', ''),
                    'metrics': sf_cached.get('metrics', {})
                }
        except Exception as e:
            frappe.logger().warning(f"Could not load sales forecast: {e}")
        
        try:
            # Demand Forecast
            from insights.ml.demand_forecasting import DemandForecasting
            df_model = DemandForecasting()
            df_cached = df_model.get_cached_results("demand_forecast")
            
            # Auto-train if refresh requested and no cache
            if not df_cached and refresh:
                frappe.logger().info("Auto-training demand forecast...")
                df_cached = df_model.train()
            
            if df_cached:
                # Get reorder alerts
                forecasts_list = df_cached.get('forecasts', [])
                reorder_alerts = [f for f in forecasts_list if f.get('stock_status') in ['Reorder Now', 'Monitor']]
                forecasts['demand_forecast'] = {
                    'summary': df_cached.get('summary', {}),
                    'reorder_alerts': reorder_alerts[:20],  # Top 20 alerts
                    'total_items': len(forecasts_list)
                }
        except Exception as e:
            frappe.logger().warning(f"Could not load demand forecast: {e}")
        
        return forecasts
    
    # ==================== MAIN TRAINING METHOD ====================
    
    def train(self, refresh_forecasts: bool = True) -> Dict[str, Any]:
        """Run complete sales intelligence analysis
        
        Args:
            refresh_forecasts: If True, auto-train forecasts if not cached
        """
        # Collect data
        sales_df = self._get_sales_transactions()
        items_df = self._get_sales_invoice_items()
        sales_team_df = self._get_sales_team_data()
        quotation_df = self._get_quotation_data()
        orders_df = self._get_sales_orders()
        
        if sales_df.empty:
            return {"status": "error", "message": "No sales data found"}
        
        # Run all analytics
        revenue_metrics = self.calculate_revenue_metrics(sales_df)
        payment_mix = self.calculate_payment_mix(sales_df)
        sales_reps = self.analyze_sales_reps(sales_team_df, quotation_df)
        comparisons = self.calculate_comparisons(sales_df)
        dimensions = self.analyze_by_dimensions(sales_df, items_df)
        margins = self.analyze_margins(items_df)
        pipeline = self.analyze_pipeline(quotation_df)
        fulfillment = self.analyze_fulfillment(orders_df, sales_df)
        forecasts = self.aggregate_forecasts(refresh=refresh_forecasts)
        
        # Build summary
        summary = {
            'total_revenue': revenue_metrics['total_revenue'],
            'total_transactions': revenue_metrics['total_transactions'],
            'avg_order_value': revenue_metrics['avg_order_value'],
            'unique_customers': revenue_metrics['unique_customers'],
            'cash_ratio': payment_mix['cash_ratio'],
            'credit_ratio': payment_mix['credit_ratio'],
            'mom_growth': comparisons['mom_growth'],
            'yoy_growth': comparisons['yoy_growth'],
            'overall_margin': margins['overall_margin'],
            'conversion_rate': pipeline['conversion_rate'],
            'fulfillment_rate': fulfillment['fulfillment_rate'],
            'dso': fulfillment['dso'],
            'total_sales_reps': sales_reps['total_reps'],
        }
        
        # Clean results for JSON
        def clean_for_json(obj):
            if isinstance(obj, dict):
                return {k: clean_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_for_json(item) for item in obj]
            elif isinstance(obj, (np.integer, np.floating)):
                return float(obj) if np.isfinite(obj) else 0
            elif isinstance(obj, float) and (pd.isna(obj) or not np.isfinite(obj)):
                return 0
            elif pd.isna(obj):
                return None
            return obj
        
        results = {
            "status": "success",
            "analysis_date": datetime.now().isoformat(),
            "summary": clean_for_json(summary),
            "revenue_metrics": clean_for_json(revenue_metrics),
            "payment_mix": clean_for_json(payment_mix),
            "sales_reps": clean_for_json(sales_reps),
            "comparisons": clean_for_json(comparisons),
            "dimensions": clean_for_json(dimensions),
            "margins": clean_for_json(margins),
            "pipeline": clean_for_json(pipeline),
            "fulfillment": clean_for_json(fulfillment),
            "forecasts": clean_for_json(forecasts),
        }
        
        # Cache results
        self.cache_results("sales_intelligence", results, expires_in_hours=6)
        
        # Log training
        self.log_training({
            "total_transactions": revenue_metrics['total_transactions'],
            "total_revenue": revenue_metrics['total_revenue'],
            "sales_reps_analyzed": sales_reps['total_reps'],
        })
        
        return results
    
    def predict(self, metric: str = None) -> Dict[str, Any]:
        """Get cached or fresh analysis"""
        cached = self.get_cached_results("sales_intelligence")
        if not cached:
            cached = self.train()
        
        if metric and metric in cached:
            return {"status": "success", metric: cached[metric]}
        
        return cached


# ==================== API FUNCTIONS ====================

def run_sales_intelligence(refresh: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Run sales intelligence analysis"""
    model = SalesIntelligence(date_filter=date_filter)
    
    if not refresh:
        cached = model.get_cached_results(f"sales_intelligence_{date_filter}")
        if cached:
            return cached
    
    return model.train()


def get_sales_intelligence() -> Dict[str, Any]:
    """Get cached sales intelligence or run if not available"""
    model = SalesIntelligence()
    cached = model.get_cached_results("sales_intelligence")
    
    if cached:
        return cached
    
    return model.train()


def get_payment_mix() -> Dict[str, Any]:
    """Get cash vs credit payment mix"""
    result = get_sales_intelligence()
    if result.get('status') != 'success':
        return result
    return {"status": "success", "payment_mix": result.get('payment_mix', {})}


def get_sales_rep_performance() -> Dict[str, Any]:
    """Get individual sales rep performance metrics"""
    result = get_sales_intelligence()
    if result.get('status') != 'success':
        return result
    return {"status": "success", "sales_reps": result.get('sales_reps', {})}


def get_revenue_breakdown() -> Dict[str, Any]:
    """Get revenue by product group, segment, territory"""
    result = get_sales_intelligence()
    if result.get('status') != 'success':
        return result
    return {"status": "success", "dimensions": result.get('dimensions', {})}


def get_margin_analysis() -> Dict[str, Any]:
    """Get gross margin analysis by product group"""
    result = get_sales_intelligence()
    if result.get('status') != 'success':
        return result
    return {"status": "success", "margins": result.get('margins', {})}


def get_sales_comparisons() -> Dict[str, Any]:
    """Get MoM and YoY comparisons"""
    result = get_sales_intelligence()
    if result.get('status') != 'success':
        return result
    return {"status": "success", "comparisons": result.get('comparisons', {})}
