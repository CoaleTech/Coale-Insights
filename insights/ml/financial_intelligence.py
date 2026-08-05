# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Financial Intelligence Model
Comprehensive financial analytics with ML-powered insights for:
- P&L analysis and profitability
- Cash flow management and forecasting
- Accounts receivable and payable
- Forex exposure analysis

Financial ratios and budget variance analysis have moved to the Strategic
Finance engine (insights.ml.strategic_finance) to keep one canonical
computation per metric; see FinancialRatiosTab.vue / BudgetVarianceTab.vue.
"""

import frappe
from datetime import datetime
from typing import Dict, Any
from insights.ml.base import BaseMLModel
from insights.api.ml import get_date_filter_sql
from insights.ml.strategic_finance.data import get_current_fiscal_year


class FinancialIntelligence(BaseMLModel):
    """
    Comprehensive Financial Intelligence Model
    
    Features:
    - P&L analysis with trends
    - Cash position and runway
    - Receivables and payables analytics
    - Forex exposure analysis

    Financial ratios and budget variance analysis live in the Strategic
    Finance engine (see module docstring above); tax filing/GST analytics
    live in insights.ml.india_tax_intelligence.
    """
    
    def __init__(self, date_filter: str = '12m'):
        super().__init__()
        self.model_name = "FinancialIntelligence"
        self.date_filter = date_filter
        self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
        self.base_currency = (
            frappe.db.get_value("Company", self.company, "default_currency")
            or frappe.db.get_single_value("System Settings", "default_currency")
            or "USD"
        )
        # Generate SQL date filter
        self.date_filter_sql = get_date_filter_sql(date_filter, 'posting_date', '')
        # Resolve fiscal year once; used by _calculate_financial_overview for the
        # YTD start date (fiscal, not calendar).  Same source as
        # strategic_finance/model.py → get_current_fiscal_year().
        self.fiscal_year = get_current_fiscal_year(self)
    
    def train(self) -> Dict[str, Any]:
        """Generate comprehensive financial intelligence"""
        try:
            overview = self._calculate_financial_overview()
            cash_flow = self._calculate_cash_flow()
            receivables = self._analyze_receivables()
            payables = self._analyze_payables()
            forex = self._analyze_forex_exposure()
            
            result = {
                "status": "success",
                "generated_at": datetime.now().isoformat(),
                "company": self.company,
                "base_currency": self.base_currency,
                "overview": overview,
                "cash_flow": cash_flow,
                "receivables": receivables,
                "payables": payables,
                "forex": forex,
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
        # Fiscal YTD start: resolved from the Fiscal Year doctype, same source as
        # strategic_finance/summary.py (intelligence.fiscal_year["start_date"]).
        # Falls back to calendar year start only when no Fiscal Year record covers
        # today (the fallback is inside get_current_fiscal_year()).
        ytd_start = self.fiscal_year["start_date"]
        
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
        # net_margin: net profit after all expenses as a % of revenue — the correct
        # definition.  gross_margin requires querying COGS (account_type = 'Cost of
        # Goods Sold') which this function does not do; return None rather than
        # aliasing net to gross (see strategic_finance/summary.py for COGS-based
        # gross margin).
        net_margin = round((ytd_profit / ytd_revenue * 100), 1) if ytd_revenue > 0 else None
        gross_margin = None  # COGS not queried here; see strategic_finance/summary.py
        
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
        
        # DSO = (total outstanding AR / trailing-12m credit sales) × 366 days.
        # Trailing 12 months is the conventional DSO basis; the fiscal-YTD window
        # (used for revenue/profit above) is deliberately different — it is too
        # short (4 months today) when outstanding receivables include invoices
        # predating the current fiscal year.  None when denominator is zero: a
        # DSO of 0 would falsely imply instant collection.
        dso_ar_total = float(frappe.db.sql("""
            SELECT COALESCE(SUM(outstanding_amount), 0) as total
            FROM `tabSales Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND company = %s
        """, (self.company,), as_dict=True)[0].get('total') or 0)

        dso_sales_12m = float(frappe.db.sql("""
            SELECT COALESCE(SUM(base_grand_total), 0) as total
            FROM `tabSales Invoice`
            WHERE docstatus = 1
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND company = %s
        """, (self.company,), as_dict=True)[0].get('total') or 0)

        current_dso = round(dso_ar_total / dso_sales_12m * 366, 1) if dso_sales_12m > 0 else None

        # Old metric preserved under an honest name: average calendar age of all
        # open receivables (not a DSO).
        avg_open_receivable_age_data = frappe.db.sql("""
            SELECT AVG(DATEDIFF(CURDATE(), posting_date)) as avg_age
            FROM `tabSales Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND company = %s
        """, (self.company,), as_dict=True)[0]
        avg_open_receivable_age_days = round(float(avg_open_receivable_age_data.get('avg_age') or 0), 1)
        
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
            "avg_open_receivable_age_days": avg_open_receivable_age_days,
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
        
        # DPO = (total outstanding AP / trailing-12m credit purchases) × 366 days.
        # Trailing 12 months is the conventional DPO basis; the fiscal-YTD window
        # (used for revenue/profit above) is deliberately different — it is too
        # short (4 months today) when outstanding payables include invoices
        # predating the current fiscal year, which would inflate DPO artificially.
        # None when denominator is zero: 0 would falsely imply instant payment.
        dpo_ap_total = float(frappe.db.sql("""
            SELECT COALESCE(SUM(outstanding_amount), 0) as total
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND company = %s
        """, (self.company,), as_dict=True)[0].get('total') or 0)

        dpo_purchases_12m = float(frappe.db.sql("""
            SELECT COALESCE(SUM(base_grand_total), 0) as total
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND company = %s
        """, (self.company,), as_dict=True)[0].get('total') or 0)

        current_dpo = round(dpo_ap_total / dpo_purchases_12m * 366, 1) if dpo_purchases_12m > 0 else None

        # Old metric preserved under an honest name: average calendar age of all
        # open payables (not a DPO).
        avg_open_payable_age_data = frappe.db.sql("""
            SELECT AVG(DATEDIFF(CURDATE(), posting_date)) as avg_age
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND company = %s
        """, (self.company,), as_dict=True)[0]
        avg_open_payable_age_days = round(float(avg_open_payable_age_data.get('avg_age') or 0), 1)
        
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
            "avg_open_payable_age_days": avg_open_payable_age_days,
            "upcoming_payments": upcoming_payments,
            "top_suppliers": top_suppliers,
            "payment_schedule": payment_schedule
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


def run_financial_intelligence(refresh: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Run financial intelligence analysis"""
    model = FinancialIntelligence(date_filter=date_filter)
    if not refresh:
        cached = model.get_cached_results(f"financial_intelligence_{date_filter}")
        if cached:
            return cached
    return model.train()
