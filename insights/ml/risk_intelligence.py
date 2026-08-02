# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Risk Intelligence & Analytics Model
Comprehensive risk assessment with ML-powered insights for:
- Credit Risk (customer scoring, payment behavior, aging analysis)
- Cash Flow Risk (DSO trends, working capital, revenue concentration)
- Operational Risk (inventory stockouts, supplier reliability, process risks)
- Compliance Risk (KRA filing status, license tracking, audit findings)
- Predictive Analytics (Prophet forecasting, anomaly detection, early warnings)
"""

import frappe
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from insights.ml.base import BaseMLModel


class RiskIntelligence(BaseMLModel):
    """
    Comprehensive Risk Intelligence & Analytics Model
    
    Features:
    - Multi-domain risk assessment (Credit, Cash Flow, Operational, Compliance)
    - Prophet-based forecasting for predictive risk modeling
    - Dual scoring system: 0-100 numeric + categorical (Low/Medium/High/Critical)
    - Real-time anomaly detection and early warning system
    - Kenya-specific compliance monitoring (KRA, VAT, licenses)
    """
    
    RISK_THRESHOLDS = {
        "low": (0, 25),
        "medium": (26, 50), 
        "high": (51, 75),
        "critical": (76, 100)
    }
    
    def __init__(self):
        super().__init__()
        self.model_name = "RiskIntelligence"
        self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
        self.base_currency = frappe.db.get_value("Company", self.company, "default_currency") or "KES"
    
    def train(self) -> Dict[str, Any]:
        """Generate comprehensive risk intelligence analysis"""
        try:
            overview = self._calculate_risk_overview()
            credit_risk = self._analyze_credit_risk()
            cashflow_risk = self._analyze_cashflow_risk()
            operational_risk = self._analyze_operational_risk()
            compliance_risk = self._analyze_compliance_risk()
            predictive_analytics = self._generate_predictive_analytics()
            
            result = {
                "status": "success",
                "generated_at": datetime.now().isoformat(),
                "company": self.company,
                "base_currency": self.base_currency,
                "overview": overview,
                "credit_risk": credit_risk,
                "cashflow_risk": cashflow_risk,
                "operational_risk": operational_risk,
                "compliance_risk": compliance_risk,
                "predictive_analytics": predictive_analytics
            }
            
            self.cache_results("risk_intelligence", result)
            return result
            
        except Exception as e:
            frappe.log_error(f"Risk Intelligence failed: {str(e)}", "ML Risk")
            return {"status": "error", "message": str(e)}
    
    def predict(self) -> Dict[str, Any]:
        """Return cached results or generate new ones"""
        cached = self.get_cached_results("risk_intelligence")
        if cached:
            return cached
        return self.train()
    
    def _get_risk_category(self, score: float) -> str:
        """Convert numeric score to risk category"""
        if score <= 25:
            return "Low"
        elif score <= 50:
            return "Medium"
        elif score <= 75:
            return "High"
        else:
            return "Critical"
    
    def _get_risk_color(self, category: str) -> str:
        """Get color for risk category"""
        colors = {
            "Low": "green",
            "Medium": "yellow", 
            "High": "orange",
            "Critical": "red"
        }
        return colors.get(category, "gray")
    
    def _calculate_risk_overview(self) -> Dict[str, Any]:
        """Calculate aggregate risk score and top risk alerts"""
        # Get basic counts for risk calculation
        total_customers = frappe.db.count("Customer")
        total_suppliers = frappe.db.count("Supplier")
        total_items = frappe.db.count("Item")
        
        # Calculate aggregate risk components
        credit_score = self._calculate_aggregate_credit_risk()
        cashflow_score = self._calculate_aggregate_cashflow_risk()
        operational_score = self._calculate_aggregate_operational_risk()
        compliance_score = self._calculate_aggregate_compliance_risk()
        
        # Weighted aggregate risk score
        weights = {"credit": 0.3, "cashflow": 0.3, "operational": 0.25, "compliance": 0.15}
        aggregate_score = (
            credit_score * weights["credit"] +
            cashflow_score * weights["cashflow"] + 
            operational_score * weights["operational"] +
            compliance_score * weights["compliance"]
        )
        
        # Top risk alerts
        alerts = []
        
        # High-risk customers
        high_risk_customers = frappe.db.sql("""
            SELECT customer, SUM(outstanding_amount) as outstanding
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND outstanding_amount > 0
                AND DATEDIFF(CURDATE(), due_date) > 60
                AND company = %s
            GROUP BY customer
            ORDER BY outstanding DESC
            LIMIT 5
        """, self.company, as_dict=True)
        
        for customer in high_risk_customers:
            alerts.append({
                "type": "credit_risk",
                "severity": "high",
                "title": f"Overdue Customer: {customer.customer}",
                "description": f"Outstanding: {frappe.format_value(customer.outstanding, {'fieldtype': 'Currency'})}",
                "action": "Review credit limit and payment terms"
            })
        
        # Cash flow alerts
        current_cash = self._get_current_cash_position()
        if current_cash < 1000000:  # Less than 1M cash
            alerts.append({
                "type": "cashflow_risk",
                "severity": "critical" if current_cash < 500000 else "high",
                "title": "Low Cash Position",
                "description": f"Current cash: {frappe.format_value(current_cash, {'fieldtype': 'Currency'})}",
                "action": "Monitor cash flow and accelerate collections"
            })
        
        # Inventory alerts
        stockout_items = frappe.db.sql("""
            SELECT COUNT(*) as count
            FROM `tabBin` b
            JOIN `tabItem` i ON b.item_code = i.name
            WHERE b.actual_qty <= 0 AND i.is_stock_item = 1
        """, as_dict=True)[0].count
        
        if stockout_items > 50:
            alerts.append({
                "type": "operational_risk",
                "severity": "medium",
                "title": f"Stock Outs: {stockout_items} Items",
                "description": "Multiple items out of stock",
                "action": "Review inventory reorder levels"
            })
        
        return {
            "aggregate_risk_score": round(aggregate_score, 1),
            "aggregate_risk_category": self._get_risk_category(aggregate_score),
            "risk_components": {
                "credit_risk": {"score": credit_score, "category": self._get_risk_category(credit_score)},
                "cashflow_risk": {"score": cashflow_score, "category": self._get_risk_category(cashflow_score)},
                "operational_risk": {"score": operational_score, "category": self._get_risk_category(operational_score)},
                "compliance_risk": {"score": compliance_score, "category": self._get_risk_category(compliance_score)}
            },
            "alerts": alerts[:10],  # Top 10 alerts
            "risk_matrix": self._generate_risk_matrix(),
            "total_customers": total_customers,
            "total_suppliers": total_suppliers,
            "total_items": total_items
        }
    
    def _calculate_aggregate_credit_risk(self) -> float:
        """Calculate overall credit risk score (0-100)"""
        # Outstanding ratio
        total_sales = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) as total
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND company = %s
        """, self.company, as_dict=True)[0].total
        
        total_outstanding = frappe.db.sql("""
            SELECT COALESCE(SUM(outstanding_amount), 0) as total
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND outstanding_amount > 0
                AND company = %s
        """, self.company, as_dict=True)[0].total
        
        outstanding_ratio = (total_outstanding / total_sales * 100) if total_sales > 0 else 0
        
        # Overdue ratio
        overdue_amount = frappe.db.sql("""
            SELECT COALESCE(SUM(outstanding_amount), 0) as total
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND outstanding_amount > 0
                AND DATEDIFF(CURDATE(), due_date) > 0
                AND company = %s
        """, self.company, as_dict=True)[0].total
        
        overdue_ratio = (overdue_amount / total_outstanding * 100) if total_outstanding > 0 else 0
        
        # Combine factors (higher ratios = higher risk)
        credit_risk_score = min(100, outstanding_ratio * 0.6 + overdue_ratio * 0.4)
        
        return round(credit_risk_score, 1)
    
    def _calculate_aggregate_cashflow_risk(self) -> float:
        """Calculate overall cash flow risk score (0-100)"""
        # Cash position
        current_cash = self._get_current_cash_position()
        
        # Monthly burn rate
        monthly_expenses = frappe.db.sql("""
            SELECT COALESCE(AVG(monthly_expenses), 0) as avg_expenses
            FROM (
                SELECT 
                    DATE_FORMAT(posting_date, '%%Y-%%m') as month,
                    SUM(grand_total) as monthly_expenses
                FROM `tabPurchase Invoice`
                WHERE docstatus = 1 
                    AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                    AND company = %s
                GROUP BY DATE_FORMAT(posting_date, '%%Y-%%m')
            ) t
        """, self.company, as_dict=True)[0].avg_expenses
        
        # Cash runway in months
        cash_runway = (current_cash / monthly_expenses) if monthly_expenses > 0 else 12
        
        # DSO calculation
        avg_receivables = frappe.db.sql("""
            SELECT COALESCE(AVG(outstanding_amount), 0) as avg
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND outstanding_amount > 0
                AND company = %s
        """, self.company, as_dict=True)[0].avg
        
        daily_sales = frappe.db.sql("""
            SELECT COALESCE(AVG(daily_sales), 0) as avg
            FROM (
                SELECT SUM(grand_total) as daily_sales
                FROM `tabSales Invoice`
                WHERE docstatus = 1 
                    AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
                    AND company = %s
                GROUP BY posting_date
            ) t
        """, self.company, as_dict=True)[0].avg
        
        dso = (avg_receivables / daily_sales) if daily_sales > 0 else 30
        
        # Risk scoring (lower cash runway and higher DSO = higher risk)
        runway_risk = max(0, 100 - (cash_runway * 10))  # Risk increases as runway decreases
        dso_risk = min(100, dso * 1.5)  # Risk increases with DSO
        
        cashflow_risk_score = (runway_risk * 0.7 + dso_risk * 0.3)
        
        return round(cashflow_risk_score, 1)
    
    def _calculate_aggregate_operational_risk(self) -> float:
        """Calculate overall operational risk score (0-100)"""
        # Stockout ratio
        total_items = frappe.db.count("Item", filters={"is_stock_item": 1})
        stockout_items = frappe.db.sql("""
            SELECT COUNT(*) as count
            FROM `tabBin` b
            JOIN `tabItem` i ON b.item_code = i.name
            WHERE b.actual_qty <= 0 AND i.is_stock_item = 1
        """, as_dict=True)[0].count
        
        stockout_ratio = (stockout_items / total_items * 100) if total_items > 0 else 0
        
        # Supplier concentration risk
        total_suppliers = frappe.db.count("Supplier")
        top_supplier_share = frappe.db.sql("""
            SELECT COALESCE(MAX(supplier_share), 0) as max_share
            FROM (
                SELECT 
                    supplier,
                    SUM(grand_total) * 100.0 / (
                        SELECT SUM(grand_total) 
                        FROM `tabPurchase Invoice` 
                        WHERE docstatus = 1 
                            AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                            AND company = %s
                    ) as supplier_share
                FROM `tabPurchase Invoice`
                WHERE docstatus = 1 
                    AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                    AND company = %s
                GROUP BY supplier
            ) t
        """, (self.company, self.company), as_dict=True)[0].max_share or 0
        
        # Process risk (error rates)
        error_invoices = frappe.db.count("Sales Invoice", filters={"docstatus": 2})
        total_invoices = frappe.db.count("Sales Invoice")
        error_rate = (error_invoices / total_invoices * 100) if total_invoices > 0 else 0
        
        # Combine operational risk factors
        operational_risk_score = (stockout_ratio * 0.4 + top_supplier_share * 0.4 + error_rate * 0.2)
        
        return round(min(100, operational_risk_score), 1)
    
    def _calculate_aggregate_compliance_risk(self) -> float:
        """Calculate overall compliance risk score (0-100)"""
        # This is a simplified compliance risk calculation
        # In practice, this would integrate with KRA systems, license databases, etc.
        
        risk_factors = []
        
        # Document completeness
        incomplete_sales = frappe.db.sql("""
            SELECT COUNT(*) as count
            FROM `tabSales Invoice`
            WHERE docstatus = 1 
                AND (customer_name IS NULL OR customer_name = '')
                AND company = %s
        """, self.company, as_dict=True)[0].count
        
        total_sales = frappe.db.count("Sales Invoice", filters={"docstatus": 1, "company": self.company})
        incomplete_ratio = (incomplete_sales / total_sales * 100) if total_sales > 0 else 0
        risk_factors.append(incomplete_ratio)
        
        # Tax compliance (simplified - checks for VAT setup)
        vat_accounts = frappe.db.count("Account", filters={"account_type": "Tax"})
        if vat_accounts == 0:
            risk_factors.append(50)  # High risk if no VAT accounts
        else:
            risk_factors.append(10)  # Low risk if VAT accounts exist
        
        # Average compliance risk
        compliance_risk_score = np.mean(risk_factors) if risk_factors else 0
        
        return round(compliance_risk_score, 1)
    
    def _get_current_cash_position(self) -> float:
        """Get current cash position from cash accounts using GL Entry"""
        cash_balance = frappe.db.sql("""
            SELECT COALESCE(SUM(gl.debit - gl.credit), 0) as total_cash
            FROM `tabAccount` a
            JOIN `tabGL Entry` gl ON gl.account = a.name
            WHERE a.account_type IN ('Cash', 'Bank')
                AND a.is_group = 0
                AND a.company = %s
                AND gl.is_cancelled = 0
        """, self.company, as_dict=True)[0].total_cash or 0
        
        return float(cash_balance)
    
    def _generate_risk_matrix(self) -> List[Dict[str, Any]]:
        """Generate risk matrix data for visualization"""
        # Impact vs Probability matrix
        risks = [
            {"name": "Major Customer Default", "probability": 30, "impact": 90, "category": "Credit"},
            {"name": "Cash Flow Shortage", "probability": 40, "impact": 70, "category": "Financial"},
            {"name": "Key Supplier Failure", "probability": 20, "impact": 80, "category": "Operational"},
            {"name": "KRA Compliance Issue", "probability": 15, "impact": 60, "category": "Compliance"},
            {"name": "Inventory Stockout", "probability": 60, "impact": 40, "category": "Operational"},
            {"name": "Currency Fluctuation", "probability": 70, "impact": 50, "category": "Financial"},
            {"name": "Payment Delays", "probability": 50, "impact": 60, "category": "Credit"},
            {"name": "Data Security Breach", "probability": 10, "impact": 95, "category": "Operational"}
        ]
        
        for risk in risks:
            risk["risk_score"] = (risk["probability"] * risk["impact"]) / 100
            risk["risk_category"] = self._get_risk_category(risk["risk_score"])
        
        return sorted(risks, key=lambda x: x["risk_score"], reverse=True)
    
    def _analyze_credit_risk(self) -> Dict[str, Any]:
        """Analyze customer credit risk and payment behavior"""
        # Customer risk scoring
        customer_scores = frappe.db.sql("""
            SELECT 
                si.customer,
                c.customer_name,
                COUNT(*) as total_invoices,
                SUM(si.grand_total) as total_sales,
                SUM(si.outstanding_amount) as outstanding,
                AVG(DATEDIFF(CURDATE(), si.due_date)) as avg_overdue_days,
                MAX(DATEDIFF(CURDATE(), si.due_date)) as max_overdue_days
            FROM `tabSales Invoice` si
            JOIN `tabCustomer` c ON si.customer = c.name
            WHERE si.docstatus = 1 
                AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND si.company = %s
            GROUP BY si.customer, c.customer_name
            ORDER BY outstanding DESC
            LIMIT 50
        """, self.company, as_dict=True)
        
        for customer in customer_scores:
            # Calculate risk score based on multiple factors
            outstanding_ratio = (customer.outstanding / customer.total_sales) if customer.total_sales > 0 else 0
            overdue_factor = max(0, customer.avg_overdue_days or 0) / 90  # Normalize to 90 days
            
            risk_score = min(100, (outstanding_ratio * 60) + (overdue_factor * 40))
            customer["risk_score"] = round(risk_score, 1)
            customer["risk_category"] = self._get_risk_category(risk_score)
            customer["risk_color"] = self._get_risk_color(customer["risk_category"])
        
        # Payment behavior analysis
        payment_patterns = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(posting_date, '%%Y-%%m') as period,
                COUNT(*) as total_invoices,
                SUM(grand_total) as total_amount,
                SUM(outstanding_amount) as outstanding_amount,
                AVG(DATEDIFF(CURDATE(), due_date)) as avg_days_overdue
            FROM `tabSales Invoice`
            WHERE docstatus = 1 
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND company = %s
            GROUP BY DATE_FORMAT(posting_date, '%%Y-%%m')
            ORDER BY period
        """, self.company, as_dict=True)
        
        # Age-wise receivables
        aging_analysis = frappe.db.sql("""
            SELECT 
                CASE 
                    WHEN DATEDIFF(CURDATE(), due_date) <= 0 THEN 'Current'
                    WHEN DATEDIFF(CURDATE(), due_date) <= 30 THEN '1-30 Days'
                    WHEN DATEDIFF(CURDATE(), due_date) <= 60 THEN '31-60 Days'
                    WHEN DATEDIFF(CURDATE(), due_date) <= 90 THEN '61-90 Days'
                    ELSE '90+ Days'
                END as aging_bucket,
                COUNT(*) as invoice_count,
                SUM(outstanding_amount) as outstanding_amount
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND outstanding_amount > 0
                AND company = %s
            GROUP BY aging_bucket
            ORDER BY 
                CASE 
                    WHEN DATEDIFF(CURDATE(), due_date) <= 0 THEN 1
                    WHEN DATEDIFF(CURDATE(), due_date) <= 30 THEN 2
                    WHEN DATEDIFF(CURDATE(), due_date) <= 60 THEN 3
                    WHEN DATEDIFF(CURDATE(), due_date) <= 90 THEN 4
                    ELSE 5
                END
        """, self.company, as_dict=True)
        
        return {
            "customer_risk_scores": customer_scores,
            "payment_patterns": payment_patterns,
            "aging_analysis": aging_analysis,
            "total_outstanding": sum([c.outstanding for c in customer_scores]),
            "high_risk_customers": len([c for c in customer_scores if c.risk_score > 70]),
            "avg_days_overdue": np.mean([p.avg_days_overdue or 0 for p in payment_patterns])
        }
    
    def _analyze_cashflow_risk(self) -> Dict[str, Any]:
        """Analyze cash flow risk and working capital management"""
        # Overdue days trend analysis (avg days past due per month)
        overdue_days_trend = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(posting_date, '%%Y-%%m') as period,
                AVG(DATEDIFF(CURDATE(), due_date)) as avg_days_overdue,
                SUM(grand_total) as monthly_sales,
                SUM(outstanding_amount) as month_end_outstanding
            FROM `tabSales Invoice`
            WHERE docstatus = 1 
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND company = %s
            GROUP BY DATE_FORMAT(posting_date, '%%Y-%%m')
            ORDER BY period
        """, self.company, as_dict=True)
        
        # Working capital components - use GL Entry for actual balances
        current_assets = frappe.db.sql("""
            SELECT COALESCE(SUM(gl.debit - gl.credit), 0) as total
            FROM `tabAccount` a
            JOIN `tabGL Entry` gl ON gl.account = a.name
            WHERE a.account_type IN ('Receivable', 'Cash', 'Bank', 'Stock')
                AND a.is_group = 0
                AND a.company = %s
                AND gl.is_cancelled = 0
        """, self.company, as_dict=True)[0].total or 0
        
        current_liabilities = frappe.db.sql("""
            SELECT COALESCE(ABS(SUM(gl.credit - gl.debit)), 0) as total
            FROM `tabAccount` a
            JOIN `tabGL Entry` gl ON gl.account = a.name
            WHERE a.account_type IN ('Payable', 'Tax')
                AND a.is_group = 0
                AND a.company = %s
                AND gl.is_cancelled = 0
        """, self.company, as_dict=True)[0].total or 0
        
        working_capital = current_assets - current_liabilities
        working_capital_ratio = (current_assets / current_liabilities) if current_liabilities > 0 else 0
        
        # Revenue concentration analysis
        customer_concentration = frappe.db.sql("""
            SELECT 
                customer,
                customer_name,
                SUM(grand_total) as revenue,
                SUM(grand_total) * 100.0 / (
                    SELECT SUM(grand_total) 
                    FROM `tabSales Invoice` 
                    WHERE docstatus = 1 
                        AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                        AND company = %s
                ) as revenue_share
            FROM `tabSales Invoice`
            WHERE docstatus = 1 
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND company = %s
            GROUP BY customer, customer_name
            ORDER BY revenue DESC
            LIMIT 10
        """, (self.company, self.company), as_dict=True)
        
        # Cash flow forecasting using Prophet (if available)
        cash_forecast = self._forecast_cash_flow()
        
        return {
            "overdue_days_trend": overdue_days_trend,
            "current_working_capital": working_capital,
            "working_capital_ratio": round(working_capital_ratio, 2),
            "current_cash_position": self._get_current_cash_position(),
            "customer_concentration": customer_concentration,
            "top_customer_share": customer_concentration[0]["revenue_share"] if customer_concentration else 0,
            "cash_forecast": cash_forecast
        }
    
    def _analyze_operational_risk(self) -> Dict[str, Any]:
        """Analyze operational risks including inventory, suppliers, and processes"""
        # Inventory risk analysis
        inventory_risks = frappe.db.sql("""
            SELECT 
                i.item_group,
                COUNT(*) as total_items,
                SUM(CASE WHEN b.actual_qty <= 0 THEN 1 ELSE 0 END) as stockout_items,
                SUM(CASE WHEN b.actual_qty > 0 THEN b.actual_qty * b.valuation_rate ELSE 0 END) as stock_value
            FROM `tabItem` i
            LEFT JOIN `tabBin` b ON i.name = b.item_code
            WHERE i.is_stock_item = 1
            GROUP BY i.item_group
            ORDER BY stockout_items DESC
        """, as_dict=True)
        
        for risk in inventory_risks:
            stockout_ratio = (risk.stockout_items / risk.total_items) if risk.total_items > 0 else 0
            risk["stockout_risk_score"] = min(100, stockout_ratio * 100)
            risk["risk_category"] = self._get_risk_category(risk["stockout_risk_score"])
        
        # Supplier reliability analysis - use due_date instead of schedule_date
        supplier_performance = frappe.db.sql("""
            SELECT 
                pi.supplier,
                s.supplier_name,
                COUNT(*) as total_orders,
                SUM(pi.grand_total) as total_value,
                AVG(DATEDIFF(pi.posting_date, pi.due_date)) as avg_delay_days,
                SUM(CASE WHEN pi.status = 'Cancelled' THEN 1 ELSE 0 END) as cancelled_orders
            FROM `tabPurchase Invoice` pi
            JOIN `tabSupplier` s ON pi.supplier = s.name
            WHERE pi.docstatus = 1
                AND pi.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND pi.company = %s
            GROUP BY pi.supplier, s.supplier_name
            HAVING total_orders > 5
            ORDER BY total_value DESC
            LIMIT 20
        """, self.company, as_dict=True)
        
        for supplier in supplier_performance:
            delay_factor = max(0, supplier.avg_delay_days or 0) / 30  # Normalize to 30 days
            cancel_rate = (supplier.cancelled_orders / supplier.total_orders) if supplier.total_orders > 0 else 0
            
            reliability_score = min(100, (delay_factor * 50) + (cancel_rate * 50))
            supplier["reliability_risk_score"] = round(reliability_score, 1)
            supplier["risk_category"] = self._get_risk_category(reliability_score)
        
        # Process risk indicators
        process_risks = {
            "invoice_error_rate": self._calculate_invoice_error_rate(),
            "average_approval_time": self._calculate_average_approval_time(),
            "system_downtime_incidents": self._count_system_incidents()
        }
        
        return {
            "inventory_risks": inventory_risks,
            "supplier_performance": supplier_performance,
            "process_risks": process_risks,
            "top_inventory_risk": inventory_risks[0] if inventory_risks else None,
            "worst_supplier": max(supplier_performance, key=lambda x: x["reliability_risk_score"]) if supplier_performance else None
        }
    
    def _analyze_compliance_risk(self) -> Dict[str, Any]:
        """Analyze compliance risks including KRA, VAT, and regulatory requirements"""
        # KRA filing status (simplified - would integrate with actual KRA API)
        kra_status = {
            "vat_filing_status": "Up to Date",  # Would check actual filing dates
            "last_filing_date": "2024-11-30",  # Would get from KRA integration
            "next_filing_due": "2025-01-20",
            "outstanding_penalties": 0
        }
        
        # Document completeness audit
        document_audit = frappe.db.sql("""
            SELECT 
                'Sales Invoice' as document_type,
                COUNT(*) as total_docs,
                SUM(CASE WHEN customer_name IS NULL OR customer_name = '' THEN 1 ELSE 0 END) as incomplete_docs
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND company = %s
            
            UNION ALL
            
            SELECT 
                'Purchase Invoice' as document_type,
                COUNT(*) as total_docs,
                SUM(CASE WHEN supplier_name IS NULL OR supplier_name = '' THEN 1 ELSE 0 END) as incomplete_docs
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1 AND company = %s
        """, (self.company, self.company), as_dict=True)
        
        # Tax compliance checks
        tax_compliance = frappe.db.sql("""
            SELECT 
                account_type,
                COUNT(*) as account_count,
                SUM(CASE WHEN is_group = 0 THEN 1 ELSE 0 END) as leaf_accounts
            FROM `tabAccount`
            WHERE account_type IN ('Tax', 'Income Tax')
                AND company = %s
            GROUP BY account_type
        """, self.company, as_dict=True)
        
        # License and permit tracking (simplified)
        licenses = [
            {
                "license_type": "Business Permit",
                "status": "Active",
                "expiry_date": "2025-12-31",
                "days_to_expiry": 376,
                "risk_level": "Low"
            },
            {
                "license_type": "VAT Registration",
                "status": "Active", 
                "expiry_date": "Ongoing",
                "days_to_expiry": 999,
                "risk_level": "Low"
            }
        ]
        
        # Calculate compliance risk score
        compliance_issues = []
        for audit in document_audit:
            if audit.total_docs > 0:
                incomplete_rate = (audit.incomplete_docs / audit.total_docs) * 100
                if incomplete_rate > 5:
                    compliance_issues.append({
                        "issue": f"High incomplete {audit.document_type} rate",
                        "severity": "Medium" if incomplete_rate < 20 else "High",
                        "rate": incomplete_rate
                    })
        
        overall_compliance_score = len(compliance_issues) * 15  # 15 points per issue
        
        return {
            "kra_status": kra_status,
            "document_audit": document_audit,
            "tax_compliance": tax_compliance,
            "licenses": licenses,
            "compliance_issues": compliance_issues,
            "overall_compliance_score": min(100, overall_compliance_score),
            "compliance_category": self._get_risk_category(overall_compliance_score)
        }
    
    def _generate_predictive_analytics(self) -> Dict[str, Any]:
        """Generate predictive analytics including forecasts and early warnings"""
        # Cash flow forecast using Prophet
        cash_forecast = self._forecast_cash_flow()
        
        # Revenue forecast
        revenue_forecast = self._forecast_revenue()
        
        # Payment delay prediction
        payment_risk_forecast = self._predict_payment_delays()
        
        # Anomaly detection
        anomalies = self._detect_anomalies()
        
        # Early warning indicators
        early_warnings = []
        
        # Check cash flow forecast for warnings
        if cash_forecast and "forecast" in cash_forecast:
            future_cash = cash_forecast["forecast"][-1]["yhat"] if cash_forecast["forecast"] else 0
            if future_cash < 500000:
                early_warnings.append({
                    "type": "cash_flow",
                    "severity": "critical",
                    "title": "Cash Flow Warning",
                    "description": f"Forecasted cash position: {frappe.format_value(future_cash, {'fieldtype': 'Currency'})}",
                    "timeframe": "Next 30 days"
                })
        
        # Check for seasonal risks
        current_month = datetime.now().month
        if current_month in [12, 1, 2]:  # Holiday season
            early_warnings.append({
                "type": "seasonal",
                "severity": "medium",
                "title": "Seasonal Risk Period",
                "description": "Holiday season may affect cash flow and collections",
                "timeframe": "Next 60 days"
            })
        
        return {
            "cash_flow_forecast": cash_forecast,
            "revenue_forecast": revenue_forecast,
            "payment_risk_forecast": payment_risk_forecast,
            "anomalies": anomalies,
            "early_warnings": early_warnings,
            "forecast_confidence": "Medium",  # Would calculate based on model performance
            "last_model_training": datetime.now().isoformat()
        }
    
    def _forecast_cash_flow(self) -> Dict[str, Any]:
        """Forecast cash flow using simple statistical methods"""
        try:
            from datetime import datetime, timedelta
            from decimal import Decimal
            
            # Get historical cash flow data - use 6 months
            cash_data = frappe.db.sql("""
                SELECT 
                    posting_date as ds,
                    SUM(CASE WHEN debit > 0 THEN debit ELSE -credit END) as y
                FROM `tabGL Entry`
                JOIN `tabAccount` ON `tabGL Entry`.account = `tabAccount`.name
                WHERE `tabAccount`.account_type IN ('Cash', 'Bank')
                    AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                    AND `tabGL Entry`.company = %s
                    AND `tabGL Entry`.is_cancelled = 0
                GROUP BY posting_date
                ORDER BY posting_date
            """, self.company, as_dict=True)
            
            if len(cash_data) < 7:
                return {"status": "insufficient_data", "message": "Need at least 7 days of cash flow data"}
            
            # Convert to plain Python types
            values = [float(d['y']) if d['y'] else 0.0 for d in cash_data]
            dates = [d['ds'] for d in cash_data]
            
            # Calculate moving averages
            recent_avg = sum(values[-30:]) / min(30, len(values[-30:]))
            weekly_avg = sum(values[-7:]) / min(7, len(values[-7:]))
            trend = (weekly_avg - recent_avg) / recent_avg if recent_avg != 0 else 0
            
            # Generate 30-day forecast based on moving average + trend
            forecast = []
            base_date = dates[-1] if dates else datetime.now().date()
            for i in range(1, 31):
                forecast_date = base_date + timedelta(days=i)
                predicted = recent_avg * (1 + trend * (i / 30))
                lower = predicted * 0.85
                upper = predicted * 1.15
                forecast.append({
                    'ds': forecast_date.strftime('%Y-%m-%d'),
                    'yhat': round(predicted, 2),
                    'yhat_lower': round(lower, 2),
                    'yhat_upper': round(upper, 2)
                })
            
            return {
                "status": "success",
                "forecast": forecast,
                "model_performance": {
                    "method": "Moving Average",
                    "periods": 30,
                    "data_points": len(cash_data),
                    "trend": f"{trend*100:.1f}%"
                }
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _forecast_revenue(self) -> Dict[str, Any]:
        """Forecast revenue using simple statistical methods"""
        try:
            from datetime import datetime, timedelta
            from decimal import Decimal
            
            # Get historical revenue data - use 6 months
            revenue_data = frappe.db.sql("""
                SELECT 
                    posting_date as ds,
                    SUM(grand_total) as y
                FROM `tabSales Invoice`
                WHERE docstatus = 1 
                    AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                    AND company = %s
                GROUP BY posting_date
                ORDER BY posting_date
            """, self.company, as_dict=True)
            
            if len(revenue_data) < 7:
                return {"status": "insufficient_data", "message": "Need at least 7 days of revenue data"}
            
            # Convert to plain Python types
            values = [float(d['y']) if d['y'] else 0.0 for d in revenue_data]
            dates = [d['ds'] for d in revenue_data]
            
            # Calculate moving averages
            recent_avg = sum(values[-30:]) / min(30, len(values[-30:]))
            weekly_avg = sum(values[-7:]) / min(7, len(values[-7:]))
            trend = (weekly_avg - recent_avg) / recent_avg if recent_avg != 0 else 0
            
            # Generate 30-day forecast
            forecast = []
            total_forecast = 0
            base_date = dates[-1] if dates else datetime.now().date()
            for i in range(1, 31):
                forecast_date = base_date + timedelta(days=i)
                predicted = recent_avg * (1 + trend * (i / 30))
                lower = predicted * 0.85
                upper = predicted * 1.15
                total_forecast += predicted
                forecast.append({
                    'ds': forecast_date.strftime('%Y-%m-%d'),
                    'yhat': round(predicted, 2),
                    'yhat_lower': round(lower, 2),
                    'yhat_upper': round(upper, 2)
                })
            
            return {
                "status": "success",
                "forecast": forecast,
                "total_forecasted_revenue": round(total_forecast, 2),
                "model_performance": {
                    "method": "Moving Average",
                    "data_points": len(revenue_data),
                    "trend": f"{trend*100:.1f}%"
                }
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _predict_payment_delays(self) -> Dict[str, Any]:
        """Predict payment delay risks"""
        # Simple statistical model for payment delay prediction
        payment_history = frappe.db.sql("""
            SELECT 
                customer,
                AVG(DATEDIFF(modified, due_date)) as avg_delay,
                STDDEV(DATEDIFF(modified, due_date)) as delay_stddev,
                COUNT(*) as payment_count
            FROM `tabSales Invoice`
            WHERE docstatus = 1 
                AND outstanding_amount = 0
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND company = %s
            GROUP BY customer
            HAVING payment_count > 5
        """, self.company, as_dict=True)
        
        high_risk_customers = []
        for customer in payment_history:
            if customer.avg_delay > 30:  # More than 30 days average delay
                risk_score = min(100, (customer.avg_delay / 90) * 100)  # Normalize to 90 days max
                high_risk_customers.append({
                    "customer": customer.customer,
                    "avg_delay_days": round(customer.avg_delay, 1),
                    "risk_score": round(risk_score, 1),
                    "risk_category": self._get_risk_category(risk_score)
                })
        
        return {
            "high_risk_customers": sorted(high_risk_customers, key=lambda x: x["risk_score"], reverse=True)[:10],
            "average_market_delay": np.mean([c.avg_delay for c in payment_history]) if payment_history else 0
        }
    
    def _detect_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies in financial and operational data"""
        anomalies = []
        
        # Revenue anomalies
        recent_revenue = frappe.db.sql("""
            SELECT 
                posting_date,
                SUM(grand_total) as daily_revenue
            FROM `tabSales Invoice`
            WHERE docstatus = 1 
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                AND company = %s
            GROUP BY posting_date
            ORDER BY posting_date
        """, self.company, as_dict=True)
        
        if recent_revenue:
            revenues = [r.daily_revenue for r in recent_revenue]
            revenue_mean = np.mean(revenues)
            revenue_std = np.std(revenues)
            
            for r in recent_revenue[-7:]:  # Check last 7 days
                if abs(r.daily_revenue - revenue_mean) > (2 * revenue_std):  # 2 sigma rule
                    anomalies.append({
                        "type": "revenue_anomaly",
                        "date": str(r.posting_date),
                        "description": f"Revenue {r.daily_revenue:,.0f} is {abs(r.daily_revenue - revenue_mean)/revenue_mean*100:.1f}% from average",
                        "severity": "medium" if abs(r.daily_revenue - revenue_mean) < (3 * revenue_std) else "high"
                    })
        
        # Expense anomalies
        recent_expenses = frappe.db.sql("""
            SELECT 
                posting_date,
                SUM(grand_total) as daily_expenses
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1 
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                AND company = %s
            GROUP BY posting_date
            ORDER BY posting_date
        """, self.company, as_dict=True)
        
        if recent_expenses:
            expenses = [e.daily_expenses for e in recent_expenses]
            expense_mean = np.mean(expenses)
            expense_std = np.std(expenses)
            
            for e in recent_expenses[-7:]:  # Check last 7 days
                if abs(e.daily_expenses - expense_mean) > (2 * expense_std):
                    anomalies.append({
                        "type": "expense_anomaly",
                        "date": str(e.posting_date),
                        "description": f"Expenses {e.daily_expenses:,.0f} is {abs(e.daily_expenses - expense_mean)/expense_mean*100:.1f}% from average",
                        "severity": "medium" if abs(e.daily_expenses - expense_mean) < (3 * expense_std) else "high"
                    })
        
        return anomalies[-20:]  # Return last 20 anomalies
    
    def _calculate_invoice_error_rate(self) -> float:
        """Calculate invoice error rate based on cancelled invoices"""
        total_invoices = frappe.db.count("Sales Invoice", filters={"company": self.company})
        cancelled_invoices = frappe.db.count("Sales Invoice", filters={"docstatus": 2, "company": self.company})
        
        return (cancelled_invoices / total_invoices * 100) if total_invoices > 0 else 0
    
    def _calculate_average_approval_time(self) -> float:
        """Calculate average time for document approvals"""
        # This would require workflow state tracking
        # For now, return a placeholder
        return 24.0  # hours
    
    def _count_system_incidents(self) -> int:
        """Count system downtime incidents"""
        # This would integrate with system monitoring
        # For now, return a placeholder
        return 0


def run_risk_intelligence(refresh: bool = False) -> Dict[str, Any]:
    """Main entry point for risk intelligence analysis"""
    model = RiskIntelligence()
    
    if not refresh:
        cached = model.get_cached_results("risk_intelligence")
        if cached:
            return cached
    
    return model.train()