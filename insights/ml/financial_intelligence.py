# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Financial Intelligence Model
Comprehensive financial analytics with ML-powered insights for:
- P&L analysis and profitability
- Cash flow management and forecasting
- Financial ratios and health metrics
- Budget variance analysis
- KRA Tax forecasting (16% VAT, 2% VAT Withholding)
- Forex exposure analysis
"""

import frappe
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from insights.ml.base import BaseMLModel
from insights.api.ml import get_date_filter_sql


class FinancialIntelligence(BaseMLModel):
    """
    Comprehensive Financial Intelligence Model (Kenya Edition)
    
    Features:
    - P&L analysis with trends
    - Cash position and runway
    - Financial ratios (liquidity, profitability, efficiency)
    - Receivables and payables analytics
    - Budget variance tracking
    - KRA Tax analysis (16% VAT, 2% VAT WHT)
    - Forex exposure analysis
    """
    
    VAT_RATE = 16.0  # Kenya standard VAT rate
    VAT_WHT_RATE = 2.0  # VAT Withholding rate
    
    def __init__(self, date_filter: str = '12m'):
        super().__init__()
        self.model_name = "FinancialIntelligence"
        self.date_filter = date_filter
        self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
        self.base_currency = frappe.db.get_value("Company", self.company, "default_currency") or "KES"
        # Generate SQL date filter
        self.date_filter_sql = get_date_filter_sql(date_filter, 'posting_date', '')
    
    def train(self) -> Dict[str, Any]:
        """Generate comprehensive financial intelligence"""
        try:
            overview = self._calculate_financial_overview()
            cash_flow = self._calculate_cash_flow()
            receivables = self._analyze_receivables()
            payables = self._analyze_payables()
            budget = self._analyze_budget_variance()
            ratios = self._calculate_financial_ratios()
            kra_tax = self._analyze_kra_tax()
            forex = self._analyze_forex_exposure()
            forecasts = self._generate_financial_forecasts()
            
            result = {
                "status": "success",
                "generated_at": datetime.now().isoformat(),
                "company": self.company,
                "base_currency": self.base_currency,
                "overview": overview,
                "cash_flow": cash_flow,
                "receivables": receivables,
                "payables": payables,
                "budget": budget,
                "ratios": ratios,
                "kra_tax": kra_tax,
                "forex": forex,
                "forecasts": forecasts
            }
            
            self.cache_results("financial_intelligence", result)
            return result
            
        except Exception as e:
            frappe.log_error(f"Financial Intelligence failed: {str(e)}", "ML Financial")
            return {"status": "error", "message": str(e)}
    
    def predict(self) -> Dict[str, Any]:
        """Return cached results or generate new ones"""
        cached = self.get_cached_results("financial_intelligence")
        if cached:
            return cached
        return self.train()
    
    def _calculate_financial_overview(self) -> Dict[str, Any]:
        """Calculate P&L overview and key metrics"""
        current_month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        ytd_start = datetime.now().replace(month=1, day=1).strftime('%Y-%m-%d')
        
        # MTD Revenue
        mtd_revenue_data = frappe.db.sql("""
            SELECT COALESCE(SUM(ABS(credit - debit)), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type = 'Income'
                AND gle.posting_date >= %s
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (current_month_start, self.company), as_dict=True)[0]
        mtd_revenue = float(mtd_revenue_data.get('amount') or 0)
        
        # MTD Expenses
        mtd_expense_data = frappe.db.sql("""
            SELECT COALESCE(SUM(ABS(debit - credit)), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type = 'Expense'
                AND gle.posting_date >= %s
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (current_month_start, self.company), as_dict=True)[0]
        mtd_expenses = float(mtd_expense_data.get('amount') or 0)
        mtd_profit = mtd_revenue - mtd_expenses
        
        # YTD figures
        ytd_revenue_data = frappe.db.sql("""
            SELECT COALESCE(SUM(ABS(credit - debit)), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type = 'Income'
                AND gle.posting_date >= %s
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (ytd_start, self.company), as_dict=True)[0]
        
        ytd_expense_data = frappe.db.sql("""
            SELECT COALESCE(SUM(ABS(debit - credit)), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type = 'Expense'
                AND gle.posting_date >= %s
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (ytd_start, self.company), as_dict=True)[0]
        
        ytd_revenue = float(ytd_revenue_data.get('amount') or 0)
        ytd_expenses = float(ytd_expense_data.get('amount') or 0)
        ytd_profit = ytd_revenue - ytd_expenses
        
        # Monthly P&L trend
        monthly_pl = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(gle.posting_date, '%%Y-%%m') as period,
                SUM(CASE WHEN acc.root_type = 'Income' THEN ABS(gle.credit - gle.debit) ELSE 0 END) as revenue,
                SUM(CASE WHEN acc.root_type = 'Expense' THEN ABS(gle.debit - gle.credit) ELSE 0 END) as expenses
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type IN ('Income', 'Expense')
                AND gle.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND gle.is_cancelled = 0
                AND gle.company = %s
            GROUP BY DATE_FORMAT(gle.posting_date, '%%Y-%%m')
            ORDER BY period
        """, (self.company,), as_dict=True)
        
        for row in monthly_pl:
            row['revenue'] = float(row.get('revenue') or 0)
            row['expenses'] = float(row.get('expenses') or 0)
            row['profit'] = row['revenue'] - row['expenses']
            row['margin'] = round((row['profit'] / row['revenue'] * 100), 1) if row['revenue'] > 0 else 0
        
        # Revenue breakdown by category
        revenue_breakdown = frappe.db.sql("""
            SELECT 
                COALESCE(acc.parent_account, acc.name) as category,
                SUM(ABS(gle.credit - gle.debit)) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type = 'Income'
                AND gle.posting_date >= %s
                AND gle.is_cancelled = 0
                AND gle.company = %s
            GROUP BY COALESCE(acc.parent_account, acc.name)
            ORDER BY amount DESC
            LIMIT 10
        """, (ytd_start, self.company), as_dict=True)
        
        for item in revenue_breakdown:
            item['amount'] = float(item['amount'] or 0)
            item['pct'] = round((item['amount'] / ytd_revenue * 100), 1) if ytd_revenue > 0 else 0
        
        # Expense breakdown
        expense_breakdown = frappe.db.sql("""
            SELECT 
                COALESCE(acc.parent_account, acc.name) as category,
                SUM(ABS(gle.debit - gle.credit)) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type = 'Expense'
                AND gle.posting_date >= %s
                AND gle.is_cancelled = 0
                AND gle.company = %s
            GROUP BY COALESCE(acc.parent_account, acc.name)
            ORDER BY amount DESC
            LIMIT 10
        """, (ytd_start, self.company), as_dict=True)
        
        for item in expense_breakdown:
            item['amount'] = float(item['amount'] or 0)
            item['pct'] = round((item['amount'] / ytd_expenses * 100), 1) if ytd_expenses > 0 else 0
        
        # Margins
        gross_margin = round((ytd_profit / ytd_revenue * 100), 1) if ytd_revenue > 0 else 0
        net_margin = gross_margin  # Simplified - same as gross for now
        
        return {
            "mtd_revenue": mtd_revenue,
            "mtd_expenses": mtd_expenses,
            "mtd_profit": mtd_profit,
            "ytd_revenue": ytd_revenue,
            "ytd_expenses": ytd_expenses,
            "ytd_profit": ytd_profit,
            "gross_margin": gross_margin,
            "net_margin": net_margin,
            "monthly_trend": monthly_pl,
            "revenue_breakdown": revenue_breakdown,
            "expense_breakdown": expense_breakdown
        }
    
    def _calculate_cash_flow(self) -> Dict[str, Any]:
        """Calculate cash flow metrics and position"""
        # Current cash position
        cash_position = frappe.db.sql("""
            SELECT 
                acc.account_type,
                acc.name as account,
                acc.account_name,
                SUM(gle.debit - gle.credit) as balance
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.account_type IN ('Bank', 'Cash')
                AND gle.is_cancelled = 0
                AND gle.company = %s
            GROUP BY acc.name, acc.account_type, acc.account_name
            HAVING balance != 0
        """, (self.company,), as_dict=True)
        
        total_cash = sum(float(c.get('balance') or 0) for c in cash_position)
        
        # Monthly cash flows
        cash_inflows = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(posting_date, '%%Y-%%m') as period,
                SUM(paid_amount) as amount
            FROM `tabPayment Entry`
            WHERE payment_type = 'Receive'
                AND docstatus = 1
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                AND company = %s
            GROUP BY DATE_FORMAT(posting_date, '%%Y-%%m')
            ORDER BY period
        """, (self.company,), as_dict=True)
        
        cash_outflows = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(posting_date, '%%Y-%%m') as period,
                SUM(paid_amount) as amount
            FROM `tabPayment Entry`
            WHERE payment_type = 'Pay'
                AND docstatus = 1
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                AND company = %s
            GROUP BY DATE_FORMAT(posting_date, '%%Y-%%m')
            ORDER BY period
        """, (self.company,), as_dict=True)
        
        # Calculate averages and runway
        avg_outflow = sum(float(o.get('amount') or 0) for o in cash_outflows) / max(len(cash_outflows), 1)
        avg_inflow = sum(float(i.get('amount') or 0) for i in cash_inflows) / max(len(cash_inflows), 1)
        net_burn = avg_outflow - avg_inflow
        
        runway_months = round(total_cash / net_burn, 1) if net_burn > 0 else 999
        
        # Cash flow by source
        inflow_by_source = frappe.db.sql("""
            SELECT 
                COALESCE(party_type, 'Other') as source,
                SUM(paid_amount) as amount
            FROM `tabPayment Entry`
            WHERE payment_type = 'Receive'
                AND docstatus = 1
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
                AND company = %s
            GROUP BY party_type
            ORDER BY amount DESC
        """, (self.company,), as_dict=True)
        
        outflow_by_use = frappe.db.sql("""
            SELECT 
                COALESCE(party_type, 'Other') as category,
                SUM(paid_amount) as amount
            FROM `tabPayment Entry`
            WHERE payment_type = 'Pay'
                AND docstatus = 1
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
                AND company = %s
            GROUP BY party_type
            ORDER BY amount DESC
        """, (self.company,), as_dict=True)
        
        # Large transactions
        large_transactions = frappe.db.sql("""
            SELECT 
                name,
                posting_date,
                payment_type,
                party_type,
                party,
                paid_amount,
                reference_no
            FROM `tabPayment Entry`
            WHERE docstatus = 1
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)
                AND company = %s
            ORDER BY paid_amount DESC
            LIMIT 15
        """, (self.company,), as_dict=True)
        
        return {
            "total_cash": total_cash,
            "cash_accounts": cash_position,
            "avg_monthly_inflow": round(avg_inflow, 2),
            "avg_monthly_outflow": round(avg_outflow, 2),
            "net_burn_rate": round(net_burn, 2),
            "runway_months": runway_months,
            "monthly_inflows": cash_inflows,
            "monthly_outflows": cash_outflows,
            "inflow_by_source": inflow_by_source,
            "outflow_by_use": outflow_by_use,
            "large_transactions": large_transactions
        }
    
    def _analyze_receivables(self) -> Dict[str, Any]:
        """Analyze accounts receivable"""
        # Total outstanding
        ar_total = frappe.db.sql("""
            SELECT 
                COALESCE(SUM(outstanding_amount), 0) as total,
                COUNT(*) as invoice_count
            FROM `tabSales Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND company = %s
        """, (self.company,), as_dict=True)[0]
        
        # AR aging buckets
        aging_buckets = frappe.db.sql("""
            SELECT 
                CASE 
                    WHEN DATEDIFF(CURDATE(), due_date) <= 0 THEN 'Current'
                    WHEN DATEDIFF(CURDATE(), due_date) BETWEEN 1 AND 30 THEN '1-30 Days'
                    WHEN DATEDIFF(CURDATE(), due_date) BETWEEN 31 AND 60 THEN '31-60 Days'
                    WHEN DATEDIFF(CURDATE(), due_date) BETWEEN 61 AND 90 THEN '61-90 Days'
                    ELSE '90+ Days'
                END as bucket,
                COUNT(*) as count,
                SUM(outstanding_amount) as amount
            FROM `tabSales Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND company = %s
            GROUP BY bucket
            ORDER BY FIELD(bucket, 'Current', '1-30 Days', '31-60 Days', '61-90 Days', '90+ Days')
        """, (self.company,), as_dict=True)
        
        # DSO calculation
        dso_data = frappe.db.sql("""
            SELECT 
                AVG(DATEDIFF(CURDATE(), posting_date)) as avg_dso
            FROM `tabSales Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND company = %s
        """, (self.company,), as_dict=True)[0]
        
        current_dso = round(float(dso_data.get('avg_dso') or 0), 1)
        
        # Top overdue customers
        overdue_customers = frappe.db.sql("""
            SELECT 
                customer,
                customer_name,
                COUNT(*) as invoice_count,
                SUM(outstanding_amount) as total_outstanding,
                MIN(due_date) as oldest_due_date,
                MAX(DATEDIFF(CURDATE(), due_date)) as max_overdue_days
            FROM `tabSales Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND due_date < CURDATE()
                AND company = %s
            GROUP BY customer, customer_name
            ORDER BY total_outstanding DESC
            LIMIT 15
        """, (self.company,), as_dict=True)
        
        # Collection trend
        collections = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(pe.posting_date, '%%Y-%%m') as period,
                SUM(per.allocated_amount) as collected
            FROM `tabPayment Entry` pe
            JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
            WHERE pe.payment_type = 'Receive'
                AND pe.docstatus = 1
                AND per.reference_doctype = 'Sales Invoice'
                AND pe.posting_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                AND pe.company = %s
            GROUP BY DATE_FORMAT(pe.posting_date, '%%Y-%%m')
            ORDER BY period
        """, (self.company,), as_dict=True)
        
        return {
            "total_outstanding": float(ar_total.get('total') or 0),
            "invoice_count": int(ar_total.get('invoice_count') or 0),
            "aging_buckets": aging_buckets,
            "current_dso": current_dso,
            "overdue_customers": overdue_customers,
            "collection_trend": collections
        }
    
    def _analyze_payables(self) -> Dict[str, Any]:
        """Analyze accounts payable"""
        # Total outstanding
        ap_total = frappe.db.sql("""
            SELECT 
                COALESCE(SUM(outstanding_amount), 0) as total,
                COUNT(*) as invoice_count
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND company = %s
        """, (self.company,), as_dict=True)[0]
        
        # AP aging buckets
        aging_buckets = frappe.db.sql("""
            SELECT 
                CASE 
                    WHEN DATEDIFF(CURDATE(), due_date) <= 0 THEN 'Current'
                    WHEN DATEDIFF(CURDATE(), due_date) BETWEEN 1 AND 30 THEN '1-30 Days'
                    WHEN DATEDIFF(CURDATE(), due_date) BETWEEN 31 AND 60 THEN '31-60 Days'
                    WHEN DATEDIFF(CURDATE(), due_date) BETWEEN 61 AND 90 THEN '61-90 Days'
                    ELSE '90+ Days'
                END as bucket,
                COUNT(*) as count,
                SUM(outstanding_amount) as amount
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND company = %s
            GROUP BY bucket
            ORDER BY FIELD(bucket, 'Current', '1-30 Days', '31-60 Days', '61-90 Days', '90+ Days')
        """, (self.company,), as_dict=True)
        
        # DPO calculation
        dpo_data = frappe.db.sql("""
            SELECT 
                AVG(DATEDIFF(CURDATE(), posting_date)) as avg_dpo
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND company = %s
        """, (self.company,), as_dict=True)[0]
        
        current_dpo = round(float(dpo_data.get('avg_dpo') or 0), 1)
        
        # Upcoming payments
        upcoming_payments = frappe.db.sql("""
            SELECT 
                name,
                supplier,
                supplier_name,
                posting_date,
                due_date,
                outstanding_amount,
                DATEDIFF(due_date, CURDATE()) as days_until_due
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND due_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
                AND company = %s
            ORDER BY due_date
            LIMIT 20
        """, (self.company,), as_dict=True)
        
        # Top suppliers by payable
        top_suppliers = frappe.db.sql("""
            SELECT 
                supplier,
                supplier_name,
                COUNT(*) as invoice_count,
                SUM(outstanding_amount) as total_outstanding
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND company = %s
            GROUP BY supplier, supplier_name
            ORDER BY total_outstanding DESC
            LIMIT 10
        """, (self.company,), as_dict=True)
        
        # Payment schedule
        payment_schedule = frappe.db.sql("""
            SELECT 
                CASE 
                    WHEN due_date < CURDATE() THEN 'Overdue'
                    WHEN due_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY) THEN 'This Week'
                    WHEN due_date BETWEEN DATE_ADD(CURDATE(), INTERVAL 8 DAY) AND DATE_ADD(CURDATE(), INTERVAL 14 DAY) THEN 'Next Week'
                    WHEN due_date BETWEEN DATE_ADD(CURDATE(), INTERVAL 15 DAY) AND DATE_ADD(CURDATE(), INTERVAL 30 DAY) THEN 'This Month'
                    ELSE 'Later'
                END as period,
                COUNT(*) as count,
                SUM(outstanding_amount) as amount
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND company = %s
            GROUP BY period
            ORDER BY FIELD(period, 'Overdue', 'This Week', 'Next Week', 'This Month', 'Later')
        """, (self.company,), as_dict=True)
        
        return {
            "total_outstanding": float(ap_total.get('total') or 0),
            "invoice_count": int(ap_total.get('invoice_count') or 0),
            "aging_buckets": aging_buckets,
            "current_dpo": current_dpo,
            "upcoming_payments": upcoming_payments,
            "top_suppliers": top_suppliers,
            "payment_schedule": payment_schedule
        }
    
    def _analyze_budget_variance(self) -> Dict[str, Any]:
        """Analyze budget vs actual variance"""
        budget_exists = frappe.db.exists("Budget", {"company": self.company, "docstatus": 1})
        
        if not budget_exists:
            return {
                "status": "no_budgets",
                "message": "No budgets configured for this company",
                "variance_items": [],
                "summary": {}
            }
        
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        # Budget vs actual
        budget_variance = frappe.db.sql("""
            SELECT 
                ba.account,
                acc.account_name,
                COALESCE(acc.parent_account, 'Uncategorized') as category,
                SUM(ba.budget_amount) as budget_amount,
                (
                    SELECT COALESCE(SUM(ABS(gle.debit - gle.credit)), 0)
                    FROM `tabGL Entry` gle
                    WHERE gle.account = ba.account
                        AND gle.is_cancelled = 0
                        AND YEAR(gle.posting_date) = %s
                        AND gle.company = %s
                ) as actual_amount
            FROM `tabBudget Account` ba
            JOIN `tabBudget` b ON ba.parent = b.name
            JOIN `tabAccount` acc ON ba.account = acc.name
            WHERE b.docstatus = 1
                AND b.company = %s
            GROUP BY ba.account, acc.account_name, acc.parent_account
            HAVING budget_amount > 0 OR actual_amount > 0
        """, (current_year, self.company, self.company), as_dict=True)
        
        total_budget = 0
        total_actual = 0
        over_budget_items = []
        
        for item in budget_variance:
            budget = float(item.get('budget_amount') or 0)
            actual = float(item.get('actual_amount') or 0)
            prorated_budget = budget * (current_month / 12)
            
            item['budget_amount'] = budget
            item['prorated_budget'] = round(prorated_budget, 2)
            item['actual_amount'] = actual
            item['variance'] = round(prorated_budget - actual, 2)
            item['variance_pct'] = round(((actual - prorated_budget) / prorated_budget * 100), 1) if prorated_budget > 0 else 0
            item['utilization_pct'] = round((actual / prorated_budget * 100), 1) if prorated_budget > 0 else 0
            
            total_budget += prorated_budget
            total_actual += actual
            
            if item['variance_pct'] > 10:
                over_budget_items.append(item)
        
        budget_variance.sort(key=lambda x: x['variance_pct'], reverse=True)
        over_budget_items.sort(key=lambda x: x['variance_pct'], reverse=True)
        
        # Cost center spending
        cost_center_spending = frappe.db.sql("""
            SELECT 
                COALESCE(gle.cost_center, 'Unallocated') as cost_center,
                SUM(ABS(gle.debit - gle.credit)) as actual_amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type = 'Expense'
                AND gle.is_cancelled = 0
                AND YEAR(gle.posting_date) = %s
                AND gle.company = %s
            GROUP BY gle.cost_center
            ORDER BY actual_amount DESC
            LIMIT 10
        """, (current_year, self.company), as_dict=True)
        
        return {
            "status": "success",
            "total_budget": round(total_budget, 2),
            "total_actual": round(total_actual, 2),
            "total_variance": round(total_budget - total_actual, 2),
            "overall_utilization": round((total_actual / total_budget * 100), 1) if total_budget > 0 else 0,
            "variance_items": budget_variance[:20],
            "over_budget_items": over_budget_items[:10],
            "cost_center_spending": cost_center_spending
        }
    
    def _calculate_financial_ratios(self) -> Dict[str, Any]:
        """Calculate key financial ratios"""
        # Current Assets (Bank, Cash, Receivable, Stock)
        current_assets = frappe.db.sql("""
            SELECT COALESCE(SUM(gle.debit - gle.credit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type = 'Asset'
                AND acc.account_type IN ('Bank', 'Cash', 'Receivable', 'Stock')
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (self.company,), as_dict=True)[0]
        
        # Current Liabilities (all short-term liabilities including Payable, Taxes, etc.)
        current_liabilities = frappe.db.sql("""
            SELECT COALESCE(SUM(gle.credit - gle.debit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type = 'Liability'
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (self.company,), as_dict=True)[0]
        
        # Total Assets
        total_assets = frappe.db.sql("""
            SELECT COALESCE(SUM(gle.debit - gle.credit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type = 'Asset'
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (self.company,), as_dict=True)[0]
        
        # Inventory
        inventory_value = frappe.db.sql("""
            SELECT COALESCE(SUM(gle.debit - gle.credit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.account_type = 'Stock'
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (self.company,), as_dict=True)[0]
        
        # Cash
        cash_value = frappe.db.sql("""
            SELECT COALESCE(SUM(gle.debit - gle.credit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.account_type IN ('Bank', 'Cash')
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (self.company,), as_dict=True)[0]
        
        # YTD Revenue and Profit
        ytd_start = datetime.now().replace(month=1, day=1).strftime('%Y-%m-%d')
        
        ytd_pl = frappe.db.sql("""
            SELECT 
                SUM(CASE WHEN acc.root_type = 'Income' THEN ABS(gle.credit - gle.debit) ELSE 0 END) as revenue,
                SUM(CASE WHEN acc.root_type = 'Expense' THEN ABS(gle.debit - gle.credit) ELSE 0 END) as expenses
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type IN ('Income', 'Expense')
                AND gle.posting_date >= %s
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (ytd_start, self.company), as_dict=True)[0]
        
        ca = float(current_assets.get('amount') or 0)
        cl = max(float(current_liabilities.get('amount') or 0), 1)
        ta = float(total_assets.get('amount') or 0)
        inv = float(inventory_value.get('amount') or 0)
        cash = float(cash_value.get('amount') or 0)
        revenue = float(ytd_pl.get('revenue') or 0)
        expenses = float(ytd_pl.get('expenses') or 0)
        profit = revenue - expenses
        
        # Calculate ratios
        current_ratio = round(ca / cl, 2)
        quick_ratio = round((ca - inv) / cl, 2)
        cash_ratio = round(cash / cl, 2)
        net_margin = round((profit / revenue * 100), 1) if revenue > 0 else 0
        roa = round((profit / ta * 100), 1) if ta > 0 else 0
        asset_turnover = round(revenue / ta, 2) if ta > 0 else 0
        working_capital = ca - cl
        
        def assess_ratio(name, value):
            thresholds = {
                'current_ratio': {'good': 2.0, 'warning': 1.5},
                'quick_ratio': {'good': 1.0, 'warning': 0.8},
                'cash_ratio': {'good': 0.5, 'warning': 0.3},
                'net_margin': {'good': 15, 'warning': 10},
            }
            if name not in thresholds:
                return 'neutral'
            t = thresholds[name]
            if value >= t['good']:
                return 'good'
            elif value >= t['warning']:
                return 'warning'
            return 'critical'
        
        # Calculate equity and additional ratios
        equity = ta - cl - (ta - ca)  # Simplified: Assets - Liabilities
        total_liabilities = frappe.db.sql("""
            SELECT COALESCE(SUM(gle.credit - gle.debit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type = 'Liability'
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (self.company,), as_dict=True)[0]
        total_liab = float(total_liabilities.get('amount') or 0)
        equity = max(ta - total_liab, 1)
        
        # Gross Profit (Revenue - COGS)
        cogs = frappe.db.sql("""
            SELECT COALESCE(SUM(ABS(gle.debit - gle.credit)), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.account_type = 'Cost of Goods Sold'
                AND gle.posting_date >= %s
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (ytd_start, self.company), as_dict=True)[0]
        cogs_amount = float(cogs.get('amount') or 0)
        gross_profit = revenue - cogs_amount
        gross_margin = round((gross_profit / revenue * 100), 1) if revenue > 0 else 0
        roe = round((profit / equity * 100), 1) if equity > 0 else 0
        
        # Leverage ratios
        debt_ratio = round((total_liab / ta * 100), 1) if ta > 0 else 0
        debt_to_equity = round(total_liab / equity, 2) if equity > 0 else 0
        equity_ratio = round((equity / ta * 100), 1) if ta > 0 else 0
        
        # Efficiency ratios (DSO, DPO) - get from receivables/payables data already calculated
        dso = 0
        dpo = 0
        try:
            # Get DSO from receivables analysis
            receivables = self._analyze_receivables()
            dso = receivables.get('current_dso', 0)
        except Exception:
            pass
        try:
            # Get DPO from payables analysis
            payables = self._analyze_payables()
            dpo = payables.get('current_dpo', 0)
        except Exception:
            pass
        cash_conversion_cycle = dso - dpo
        
        # Get monthly trend for ratios (same as overview)
        monthly_trend = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(gle.posting_date, '%%Y-%%m') as period,
                SUM(CASE WHEN acc.root_type = 'Income' THEN ABS(gle.credit - gle.debit) ELSE 0 END) as revenue,
                SUM(CASE WHEN acc.root_type = 'Expense' THEN ABS(gle.debit - gle.credit) ELSE 0 END) as expenses
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type IN ('Income', 'Expense')
                AND gle.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND gle.is_cancelled = 0
                AND gle.company = %s
            GROUP BY DATE_FORMAT(gle.posting_date, '%%Y-%%m')
            ORDER BY period
        """, (self.company,), as_dict=True)
        
        for row in monthly_trend:
            row['revenue'] = float(row.get('revenue') or 0)
            row['expenses'] = float(row.get('expenses') or 0)
            row['profit'] = row['revenue'] - row['expenses']
            row['margin'] = round((row['profit'] / row['revenue'] * 100), 1) if row['revenue'] > 0 else 0
        
        return {
            "liquidity": {
                "current_ratio": current_ratio,
                "quick_ratio": quick_ratio,
                "cash_ratio": cash_ratio,
                "working_capital": working_capital,
                "status": {
                    "current_ratio": assess_ratio('current_ratio', current_ratio),
                    "quick_ratio": assess_ratio('quick_ratio', quick_ratio),
                    "cash_ratio": assess_ratio('cash_ratio', cash_ratio),
                }
            },
            "profitability": {
                "gross_margin": gross_margin,
                "net_margin": net_margin,
                "roa": roa,
                "roe": roe,
                "status": {
                    "net_margin": assess_ratio('net_margin', net_margin),
                }
            },
            "efficiency": {
                "asset_turnover": asset_turnover,
                "dso": round(dso),
                "dpo": round(dpo),
                "cash_conversion_cycle": round(cash_conversion_cycle),
            },
            "leverage": {
                "debt_ratio": debt_ratio,
                "debt_to_equity": debt_to_equity,
                "equity_ratio": equity_ratio,
            },
            "working_capital_details": {
                "current_assets": ca,
                "current_liabilities": cl,
                "total_assets": ta,
                "total_liabilities": total_liab,
                "equity": equity,
                "inventory": inv,
                "cash": cash
            },
            "trends": monthly_trend
        }
    
    def _analyze_kra_tax(self) -> Dict[str, Any]:
        """Analyze KRA tax obligations (16% VAT, 2% VAT Withholding)"""
        current_month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        
        # Output VAT (16% on sales)
        output_vat = frappe.db.sql("""
            SELECT COALESCE(SUM(stc.tax_amount), 0) as amount
            FROM `tabSales Taxes and Charges` stc
            JOIN `tabSales Invoice` si ON stc.parent = si.name
            WHERE si.docstatus = 1
                AND si.posting_date >= %s
                AND si.company = %s
                AND stc.rate = 16
        """, (current_month_start, self.company), as_dict=True)[0]
        
        # Input VAT (16% on purchases)
        input_vat = frappe.db.sql("""
            SELECT COALESCE(SUM(ptc.tax_amount), 0) as amount
            FROM `tabPurchase Taxes and Charges` ptc
            JOIN `tabPurchase Invoice` pi ON ptc.parent = pi.name
            WHERE pi.docstatus = 1
                AND pi.posting_date >= %s
                AND pi.company = %s
                AND ptc.rate = 16
        """, (current_month_start, self.company), as_dict=True)[0]
        
        output_vat_amount = abs(float(output_vat.get('amount') or 0))
        input_vat_amount = abs(float(input_vat.get('amount') or 0))
        net_vat_payable = output_vat_amount - input_vat_amount
        
        # VAT Withholding (2% of VAT amount withheld by appointed agents)
        # This would typically be tracked via a custom field or separate doctype
        vat_wht = frappe.db.sql("""
            SELECT COALESCE(SUM(stc.tax_amount * 0.02 / 0.16), 0) as amount
            FROM `tabSales Taxes and Charges` stc
            JOIN `tabSales Invoice` si ON stc.parent = si.name
            WHERE si.docstatus = 1
                AND si.posting_date >= %s
                AND si.company = %s
                AND stc.rate = 16
        """, (current_month_start, self.company), as_dict=True)[0]
        
        vat_wht_amount = abs(float(vat_wht.get('amount') or 0))
        
        # Monthly VAT trend (last 12 months)
        monthly_vat = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(si.posting_date, '%%Y-%%m') as period,
                COALESCE(SUM(stc.tax_amount), 0) as output_vat
            FROM `tabSales Taxes and Charges` stc
            JOIN `tabSales Invoice` si ON stc.parent = si.name
            WHERE si.docstatus = 1
                AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND si.company = %s
                AND stc.rate = 16
            GROUP BY DATE_FORMAT(si.posting_date, '%%Y-%%m')
            ORDER BY period
        """, (self.company,), as_dict=True)
        
        monthly_input_vat = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(pi.posting_date, '%%Y-%%m') as period,
                COALESCE(SUM(ptc.tax_amount), 0) as input_vat
            FROM `tabPurchase Taxes and Charges` ptc
            JOIN `tabPurchase Invoice` pi ON ptc.parent = pi.name
            WHERE pi.docstatus = 1
                AND pi.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND pi.company = %s
                AND ptc.rate = 16
            GROUP BY DATE_FORMAT(pi.posting_date, '%%Y-%%m')
            ORDER BY period
        """, (self.company,), as_dict=True)
        
        # Combine into monthly trend
        input_vat_dict = {r['period']: abs(float(r['input_vat'])) for r in monthly_input_vat}
        
        vat_trend = []
        for row in monthly_vat:
            period = row['period']
            output = abs(float(row['output_vat']))
            input_v = input_vat_dict.get(period, 0)
            vat_trend.append({
                'period': period,
                'output_vat': output,
                'input_vat': input_v,
                'net_vat': output - input_v
            })
        
        # VAT forecast (next 3 months based on average)
        if len(vat_trend) >= 3:
            avg_output = sum(v['output_vat'] for v in vat_trend[-6:]) / min(len(vat_trend), 6)
            avg_input = sum(v['input_vat'] for v in vat_trend[-6:]) / min(len(vat_trend), 6)
            avg_net = avg_output - avg_input
            
            vat_forecast = []
            today = datetime.now()
            for i in range(1, 4):
                future_date = today + timedelta(days=30*i)
                vat_forecast.append({
                    'period': future_date.strftime('%Y-%m'),
                    'predicted_output_vat': round(avg_output, 2),
                    'predicted_input_vat': round(avg_input, 2),
                    'predicted_net_vat': round(avg_net, 2)
                })
        else:
            vat_forecast = []
        
        # KRA deadlines
        today = datetime.now()
        current_day = today.day
        
        # VAT is due by 20th of following month
        if current_day <= 20:
            vat_due_date = today.replace(day=20)
        else:
            next_month = today.replace(day=1) + timedelta(days=32)
            vat_due_date = next_month.replace(day=20)
        
        days_to_vat_deadline = (vat_due_date - today).days
        
        return {
            "output_vat_mtd": output_vat_amount,
            "input_vat_mtd": input_vat_amount,
            "net_vat_payable": net_vat_payable,
            "vat_wht_mtd": vat_wht_amount,
            "vat_rate": self.VAT_RATE,
            "vat_wht_rate": self.VAT_WHT_RATE,
            "monthly_trend": vat_trend,
            "forecast": vat_forecast,
            "vat_due_date": vat_due_date.strftime('%Y-%m-%d'),
            "days_to_deadline": days_to_vat_deadline
        }
    
    def _analyze_forex_exposure(self) -> Dict[str, Any]:
        """Analyze foreign currency exposure"""
        # Foreign currency receivables
        fx_receivables = frappe.db.sql("""
            SELECT 
                si.currency,
                COUNT(*) as invoice_count,
                SUM(si.outstanding_amount) as outstanding_foreign,
                SUM(si.outstanding_amount * si.conversion_rate) as outstanding_base,
                AVG(si.conversion_rate) as avg_rate
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1
                AND si.outstanding_amount > 0
                AND si.currency != %s
                AND si.company = %s
            GROUP BY si.currency
        """, (self.base_currency, self.company), as_dict=True)
        
        # Foreign currency payables
        fx_payables = frappe.db.sql("""
            SELECT 
                pi.currency,
                COUNT(*) as invoice_count,
                SUM(pi.outstanding_amount) as outstanding_foreign,
                SUM(pi.outstanding_amount * pi.conversion_rate) as outstanding_base,
                AVG(pi.conversion_rate) as avg_rate
            FROM `tabPurchase Invoice` pi
            WHERE pi.docstatus = 1
                AND pi.outstanding_amount > 0
                AND pi.currency != %s
                AND pi.company = %s
            GROUP BY pi.currency
        """, (self.base_currency, self.company), as_dict=True)
        
        # Get current exchange rates
        currencies = set([r['currency'] for r in fx_receivables] + [p['currency'] for p in fx_payables])
        current_rates = {}
        
        for currency in currencies:
            rate = frappe.db.sql("""
                SELECT exchange_rate
                FROM `tabCurrency Exchange`
                WHERE from_currency = %s
                    AND to_currency = %s
                    AND date <= CURDATE()
                ORDER BY date DESC
                LIMIT 1
            """, (currency, self.base_currency), as_dict=True)
            
            if rate:
                current_rates[currency] = float(rate[0]['exchange_rate'])
        
        # Calculate unrealized gain/loss
        total_receivable_foreign = 0
        total_receivable_base = 0
        total_unrealized_ar = 0
        
        for r in fx_receivables:
            r['outstanding_foreign'] = float(r['outstanding_foreign'] or 0)
            r['outstanding_base'] = float(r['outstanding_base'] or 0)
            r['avg_rate'] = float(r['avg_rate'] or 0)
            
            current_rate = current_rates.get(r['currency'], r['avg_rate'])
            r['current_rate'] = current_rate
            r['current_value'] = r['outstanding_foreign'] * current_rate
            r['unrealized_gain_loss'] = r['current_value'] - r['outstanding_base']
            
            total_receivable_foreign += r['outstanding_foreign']
            total_receivable_base += r['outstanding_base']
            total_unrealized_ar += r['unrealized_gain_loss']
        
        total_payable_foreign = 0
        total_payable_base = 0
        total_unrealized_ap = 0
        
        for p in fx_payables:
            p['outstanding_foreign'] = float(p['outstanding_foreign'] or 0)
            p['outstanding_base'] = float(p['outstanding_base'] or 0)
            p['avg_rate'] = float(p['avg_rate'] or 0)
            
            current_rate = current_rates.get(p['currency'], p['avg_rate'])
            p['current_rate'] = current_rate
            p['current_value'] = p['outstanding_foreign'] * current_rate
            p['unrealized_gain_loss'] = p['current_value'] - p['outstanding_base']
            
            total_payable_foreign += p['outstanding_foreign']
            total_payable_base += p['outstanding_base']
            total_unrealized_ap += p['unrealized_gain_loss']
        
        # Net exposure by currency
        net_exposure = {}
        for r in fx_receivables:
            currency = r['currency']
            if currency not in net_exposure:
                net_exposure[currency] = {'receivable': 0, 'payable': 0, 'current_rate': r.get('current_rate', 0)}
            net_exposure[currency]['receivable'] = r['outstanding_foreign']
        
        for p in fx_payables:
            currency = p['currency']
            if currency not in net_exposure:
                net_exposure[currency] = {'receivable': 0, 'payable': 0, 'current_rate': p.get('current_rate', 0)}
            net_exposure[currency]['payable'] = p['outstanding_foreign']
        
        exposure_summary = []
        for currency, data in net_exposure.items():
            net = data['receivable'] - data['payable']
            exposure_summary.append({
                'currency': currency,
                'receivable': data['receivable'],
                'payable': data['payable'],
                'net_exposure': net,
                'current_rate': data['current_rate'],
                'net_exposure_base': net * data['current_rate'],
                'position': 'Long' if net > 0 else 'Short'
            })
        
        # At-risk invoices (large forex exposure nearing due date)
        at_risk_invoices = frappe.db.sql("""
            SELECT 
                'Sales Invoice' as doctype,
                si.name,
                si.customer as party,
                si.currency,
                si.outstanding_amount,
                si.conversion_rate,
                si.due_date,
                DATEDIFF(si.due_date, CURDATE()) as days_to_due
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1
                AND si.outstanding_amount > 0
                AND si.currency != %s
                AND si.company = %s
            UNION ALL
            SELECT 
                'Purchase Invoice' as doctype,
                pi.name,
                pi.supplier as party,
                pi.currency,
                pi.outstanding_amount,
                pi.conversion_rate,
                pi.due_date,
                DATEDIFF(pi.due_date, CURDATE()) as days_to_due
            FROM `tabPurchase Invoice` pi
            WHERE pi.docstatus = 1
                AND pi.outstanding_amount > 0
                AND pi.currency != %s
                AND pi.company = %s
            ORDER BY outstanding_amount DESC
            LIMIT 20
        """, (self.base_currency, self.company, self.base_currency, self.company), as_dict=True)
        
        # Realized forex gains/losses (from journal entries)
        realized_forex = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(je.posting_date, '%%Y-%%m') as period,
                SUM(CASE WHEN jea.credit > jea.debit THEN jea.credit - jea.debit ELSE 0 END) as forex_gain,
                SUM(CASE WHEN jea.debit > jea.credit THEN jea.debit - jea.credit ELSE 0 END) as forex_loss
            FROM `tabJournal Entry` je
            JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
            JOIN `tabAccount` acc ON jea.account = acc.name
            WHERE je.docstatus = 1
                AND je.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND je.company = %s
                AND (acc.account_name LIKE '%%Exchange Gain%%' OR acc.account_name LIKE '%%Exchange Loss%%'
                     OR acc.account_name LIKE '%%Forex%%')
            GROUP BY DATE_FORMAT(je.posting_date, '%%Y-%%m')
            ORDER BY period
        """, (self.company,), as_dict=True)
        
        return {
            "base_currency": self.base_currency,
            "receivables_by_currency": fx_receivables,
            "payables_by_currency": fx_payables,
            "exposure_summary": exposure_summary,
            "total_receivable_base": total_receivable_base,
            "total_payable_base": total_payable_base,
            "net_exposure_base": total_receivable_base - total_payable_base,
            "total_unrealized_ar": round(total_unrealized_ar, 2),
            "total_unrealized_ap": round(total_unrealized_ap, 2),
            "net_unrealized": round(total_unrealized_ar - total_unrealized_ap, 2),
            "at_risk_invoices": at_risk_invoices,
            "realized_forex_trend": realized_forex
        }
    
    def _generate_financial_forecasts(self) -> Dict[str, Any]:
        """Generate financial forecasts"""
        # Historical data
        historical = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(gle.posting_date, '%%Y-%%m') as period,
                SUM(CASE WHEN acc.root_type = 'Income' THEN ABS(gle.credit - gle.debit) ELSE 0 END) as revenue,
                SUM(CASE WHEN acc.root_type = 'Expense' THEN ABS(gle.debit - gle.credit) ELSE 0 END) as expenses
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.root_type IN ('Income', 'Expense')
                AND gle.posting_date >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
                AND gle.is_cancelled = 0
                AND gle.company = %s
            GROUP BY DATE_FORMAT(gle.posting_date, '%%Y-%%m')
            ORDER BY period
        """, (self.company,), as_dict=True)
        
        if len(historical) < 6:
            return {
                "status": "insufficient_data",
                "message": "Need at least 6 months of data for forecasting",
                "historical": [dict(h) for h in historical] if historical else []
            }
        
        # Convert frappe dicts to regular dicts for pandas compatibility
        historical_data = [{'period': h['period'], 'revenue': float(h['revenue'] or 0), 'expenses': float(h['expenses'] or 0)} for h in historical]
        df = pd.DataFrame(historical_data)
        df['revenue'] = pd.to_numeric(df['revenue'])
        df['expenses'] = pd.to_numeric(df['expenses'])
        df['profit'] = df['revenue'] - df['expenses']
        
        # Calculate trends
        revenue_avg = float(df['revenue'].tail(6).mean())
        expense_avg = float(df['expenses'].tail(6).mean())
        revenue_trend = float((df['revenue'].tail(3).mean() - df['revenue'].head(3).mean()) / 3)
        expense_trend = float((df['expenses'].tail(3).mean() - df['expenses'].head(3).mean()) / 3)
        
        # Generate forecast
        forecasts = []
        today = datetime.now()
        
        for i in range(1, 4):
            future_date = today + timedelta(days=30*i)
            period = future_date.strftime('%Y-%m')
            
            predicted_revenue = revenue_avg + (revenue_trend * i)
            predicted_expenses = expense_avg + (expense_trend * i)
            
            forecasts.append({
                'period': period,
                'predicted_revenue': float(round(max(0, predicted_revenue), 2)),
                'predicted_expenses': float(round(max(0, predicted_expenses), 2)),
                'predicted_profit': float(round(predicted_revenue - predicted_expenses, 2)),
                'confidence': 'Medium' if i <= 2 else 'Low'
            })
        
        # Cash flow forecast
        current_cash = frappe.db.sql("""
            SELECT COALESCE(SUM(gle.debit - gle.credit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE acc.account_type IN ('Bank', 'Cash')
                AND gle.is_cancelled = 0
                AND gle.company = %s
        """, (self.company,), as_dict=True)[0]
        
        cash_position = float(current_cash.get('amount') or 0)
        
        # Expected collections/payments
        expected_collections = frappe.db.sql("""
            SELECT 
                CASE 
                    WHEN due_date <= DATE_ADD(CURDATE(), INTERVAL 30 DAY) THEN 'Month 1'
                    WHEN due_date <= DATE_ADD(CURDATE(), INTERVAL 60 DAY) THEN 'Month 2'
                    ELSE 'Month 3'
                END as period,
                SUM(outstanding_amount) as amount
            FROM `tabSales Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND due_date <= DATE_ADD(CURDATE(), INTERVAL 90 DAY)
                AND company = %s
            GROUP BY period
        """, (self.company,), as_dict=True)
        
        expected_payments = frappe.db.sql("""
            SELECT 
                CASE 
                    WHEN due_date <= DATE_ADD(CURDATE(), INTERVAL 30 DAY) THEN 'Month 1'
                    WHEN due_date <= DATE_ADD(CURDATE(), INTERVAL 60 DAY) THEN 'Month 2'
                    ELSE 'Month 3'
                END as period,
                SUM(outstanding_amount) as amount
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND due_date <= DATE_ADD(CURDATE(), INTERVAL 90 DAY)
                AND company = %s
            GROUP BY period
        """, (self.company,), as_dict=True)
        
        collections_by_month = {c['period']: float(c['amount']) for c in expected_collections}
        payments_by_month = {p['period']: float(p['amount']) for p in expected_payments}
        
        cash_forecast = []
        running_cash = cash_position
        
        for month in ['Month 1', 'Month 2', 'Month 3']:
            inflow = collections_by_month.get(month, 0)
            outflow = payments_by_month.get(month, 0)
            running_cash = running_cash + inflow - outflow
            cash_forecast.append({
                'period': month,
                'expected_collections': inflow,
                'expected_payments': outflow,
                'projected_balance': round(running_cash, 2)
            })
        
        return {
            "status": "success",
            "historical": historical,
            "pl_forecasts": forecasts,
            "cash_forecasts": cash_forecast,
            "current_cash_position": cash_position,
            "revenue_trend": "up" if revenue_trend > 0 else "down",
            "expense_trend": "up" if expense_trend > 0 else "down"
        }


def run_financial_intelligence(refresh: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Run financial intelligence analysis"""
    model = FinancialIntelligence(date_filter=date_filter)
    if not refresh:
        cached = model.get_cached_results(f"financial_intelligence_{date_filter}")
        if cached:
            return cached
    return model.train()
