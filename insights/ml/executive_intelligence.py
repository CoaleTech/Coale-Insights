"""
Executive Intelligence Module

Aggregates top KPIs from all departmental intelligence modules to provide
a unified C-suite dashboard with RAG status indicators and trend analysis.
"""

import frappe
from frappe import _
from frappe.utils import nowdate, add_months, add_days, flt, cstr
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
import logging
from insights.utils import guarded_task

from .strategic_finance_intelligence import StrategicFinanceIntelligence
from .sales_intelligence import SalesIntelligence
from .customer_intelligence import CustomerIntelligence
from .inventory_intelligence import InventoryIntelligence
from .procurement_intelligence import ProcurementIntelligence
from .risk_intelligence import RiskIntelligence
from .financial_intelligence import FinancialIntelligence
from .tax_intelligence import TaxIntelligence
from .hr_intelligence import HRIntelligence
logger = logging.getLogger(__name__)


class ExecutiveIntelligence:
    """
    Executive Intelligence aggregates KPIs from all departmental modules
    to provide a unified C-suite view with RAG status and AI narratives.
    """
    
    def __init__(self):
        self.today = nowdate()
        self.current_month_start = datetime.now().replace(day=1).date()
        self.current_quarter_start = self._get_quarter_start()
        self.current_year_start = datetime.now().replace(month=1, day=1).date()
        
        # Initialize departmental intelligence modules
        self._init_intelligence_modules()

        # Company default currency
        try:
            self.company_currency = frappe.db.get_default("currency") or "KES"
        except Exception:
            self.company_currency = "KES"
    
    def _init_intelligence_modules(self):
        """Initialize all departmental intelligence modules"""
        try:
            self.strategic_finance = StrategicFinanceIntelligence()
            self.sales_intel = SalesIntelligence()
            self.customer_intel = CustomerIntelligence()
            self.inventory_intel = InventoryIntelligence()
            self.procurement_intel = ProcurementIntelligence()
            self.risk_intel = RiskIntelligence()
            self.financial_intel = FinancialIntelligence()
            self.tax_intel = TaxIntelligence()
            self.hr_intel = HRIntelligence()
        except Exception as e:
            logger.error(f"Error initializing intelligence modules: {e}")
            frappe.log_error(f"Executive Intelligence init error: {e}")
    
    def _get_quarter_start(self) -> date:
        """Get the start date of current quarter"""
        current_month = datetime.now().month
        quarter_start_month = ((current_month - 1) // 3) * 3 + 1
        return datetime.now().replace(month=quarter_start_month, day=1).date()
    
    def get_executive_summary(self, period: str = "YTD") -> Dict[str, Any]:
        """
        Generate comprehensive executive summary with top KPIs from all departments
        
        Args:
            period: One of MTD, QTD, YTD, TTM (Month/Quarter/Year/Twelve Month)
        """
        try:
            summary = {
                "period": period,
                "generated_at": datetime.now().isoformat(),
                "currency": self.company_currency,
                "kpis": {
                    "financial": self._get_financial_kpis(period),
                    "sales": self._get_sales_kpis(period),
                    "customer": self._get_customer_kpis(period),
                    "operations": self._get_operations_kpis(period),
                    "risk": self._get_risk_kpis(period),
                    "hr": self._get_hr_kpis(period),
                },
                "alerts": self._get_executive_alerts(),
                "trends": self._get_trend_sparklines(period),
                "narrative": self._generate_executive_narrative(period)
            }
            
            # Calculate overall business health score
            summary["business_health_score"] = self._calculate_business_health_score(summary["kpis"])
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating executive summary: {e}")
            return {
                "error": str(e),
                "period": period,
                "generated_at": datetime.now().isoformat()
            }
    
    def _get_financial_kpis(self, period: str) -> Dict[str, Any]:
        """Extract top 3 financial KPIs with RAG status"""
        try:
            strategic_data = self.strategic_finance.get_executive_kpis()
            financial_data = self.financial_intel.get_financial_overview()
            
            # Revenue metrics
            revenue = strategic_data.get("revenue", {})
            revenue_actual = flt(revenue.get("actual", 0))
            revenue_target = flt(revenue.get("target", 0))
            revenue_variance = ((revenue_actual / revenue_target) - 1) * 100 if revenue_target else 0
            
            # Profitability metrics  
            net_margin = flt(strategic_data.get("net_margin", {}).get("current", 0))
            
            # Cash metrics
            cash_runway = flt(strategic_data.get("cash_runway_weeks", 0))
            
            return {
                "revenue": {
                    "value": revenue_actual,
                    "target": revenue_target,
                    "variance_pct": revenue_variance,
                    "rag_status": self._get_rag_status(revenue_variance, thresholds={"green": 5, "amber": -5}),
                    "label": f"Revenue ({period})",
                    "format": "currency"
                },
                "net_margin": {
                    "value": net_margin,
                    "target": 10.0,  # Default 10% target
                    "variance_pct": (net_margin - 10.0),
                    "rag_status": self._get_rag_status(net_margin, thresholds={"green": 10, "amber": 5}),
                    "label": "Net Margin %",
                    "format": "percentage"
                },
                "cash_runway": {
                    "value": cash_runway, 
                    "target": 13,  # 13 weeks target
                    "variance_weeks": cash_runway - 13,
                    "rag_status": self._get_rag_status(cash_runway, thresholds={"green": 13, "amber": 8}),
                    "label": "Cash Runway (Weeks)",
                    "format": "decimal"
                }
            }
        
        except Exception as e:
            logger.error(f"Error getting financial KPIs: {e}")
            return self._get_error_kpis("Financial")
    
    def _get_sales_kpis(self, period: str) -> Dict[str, Any]:
        """Extract top 3 sales KPIs with RAG status"""
        try:
            sales_data = self.sales_intel.get_sales_overview()
            
            # Sales growth
            growth_rate = flt(sales_data.get("growth_rate", 0))
            
            # Conversion metrics
            conversion_rate = flt(sales_data.get("conversion_rate", 0))
            
            # Pipeline health
            pipeline_value = flt(sales_data.get("pipeline_value", 0))
            
            return {
                "growth_rate": {
                    "value": growth_rate,
                    "target": 15.0,  # 15% growth target
                    "variance_pct": growth_rate - 15.0,
                    "rag_status": self._get_rag_status(growth_rate, thresholds={"green": 15, "amber": 5}),
                    "label": f"Sales Growth ({period})",
                    "format": "percentage"
                },
                "conversion_rate": {
                    "value": conversion_rate,
                    "target": 25.0,  # 25% conversion target
                    "variance_pct": conversion_rate - 25.0,
                    "rag_status": self._get_rag_status(conversion_rate, thresholds={"green": 25, "amber": 15}),
                    "label": "Lead Conversion %",
                    "format": "percentage"
                },
                "pipeline_value": {
                    "value": pipeline_value,
                    "target": 1000000,  # 1M pipeline target
                    "variance_pct": ((pipeline_value / 1000000) - 1) * 100 if pipeline_value else 0,
                    "rag_status": self._get_rag_status(pipeline_value, thresholds={"green": 1000000, "amber": 750000}),
                    "label": "Sales Pipeline",
                    "format": "currency"
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting sales KPIs: {e}")
            return self._get_error_kpis("Sales")
    
    def _get_customer_kpis(self, period: str) -> Dict[str, Any]:
        """Extract top 3 customer KPIs with RAG status"""
        try:
            customer_data = self.customer_intel.get_customer_overview()
            
            # Customer metrics
            churn_rate = flt(customer_data.get("churn_rate", 0))
            nps_score = flt(customer_data.get("nps_score", 0))
            ltv_cac = flt(customer_data.get("ltv_cac_ratio", 0))
            
            return {
                "churn_rate": {
                    "value": churn_rate,
                    "target": 5.0,  # 5% churn target
                    "variance_pct": churn_rate - 5.0,
                    "rag_status": self._get_rag_status(churn_rate, thresholds={"green": 5, "amber": 8}, reverse=True),
                    "label": f"Customer Churn ({period})",
                    "format": "percentage"
                },
                "nps_score": {
                    "value": nps_score,
                    "target": 50,  # NPS 50 target
                    "variance_points": nps_score - 50,
                    "rag_status": self._get_rag_status(nps_score, thresholds={"green": 50, "amber": 30}),
                    "label": "Net Promoter Score",
                    "format": "decimal"
                },
                "ltv_cac": {
                    "value": ltv_cac,
                    "target": 3.0,  # 3:1 LTV:CAC target
                    "variance_ratio": ltv_cac - 3.0,
                    "rag_status": self._get_rag_status(ltv_cac, thresholds={"green": 3, "amber": 2}),
                    "label": "LTV:CAC Ratio",
                    "format": "ratio"
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting customer KPIs: {e}")
            return self._get_error_kpis("Customer")
    
    def _get_operations_kpis(self, period: str) -> Dict[str, Any]:
        """Extract top 3 operations KPIs (inventory + procurement)"""
        try:
            inventory_data = self.inventory_intel.get_inventory_overview()
            procurement_data = self.procurement_intel.get_procurement_overview() 
            
            # Inventory metrics
            stockout_rate = flt(inventory_data.get("stockout_rate", 0))
            inventory_turns = flt(inventory_data.get("inventory_turnover", 0))
            
            # Procurement metrics
            supplier_performance = flt(procurement_data.get("supplier_performance_score", 0))
            
            return {
                "stockout_rate": {
                    "value": stockout_rate,
                    "target": 2.0,  # 2% stockout target
                    "variance_pct": stockout_rate - 2.0,
                    "rag_status": self._get_rag_status(stockout_rate, thresholds={"green": 2, "amber": 5}, reverse=True),
                    "label": "Stockout Rate %",
                    "format": "percentage"
                },
                "inventory_turns": {
                    "value": inventory_turns,
                    "target": 6.0,  # 6 turns per year target
                    "variance_turns": inventory_turns - 6.0,
                    "rag_status": self._get_rag_status(inventory_turns, thresholds={"green": 6, "amber": 4}),
                    "label": "Inventory Turns (Annual)",
                    "format": "decimal"
                },
                "supplier_performance": {
                    "value": supplier_performance,
                    "target": 85,  # 85% performance target
                    "variance_points": supplier_performance - 85,
                    "rag_status": self._get_rag_status(supplier_performance, thresholds={"green": 85, "amber": 70}),
                    "label": "Supplier Performance %",
                    "format": "percentage"
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting operations KPIs: {e}")
            return self._get_error_kpis("Operations")
    
    def _get_risk_kpis(self, period: str) -> Dict[str, Any]:
        """Extract top 3 risk KPIs"""
        try:
            risk_data = self.risk_intel.get_risk_overview()
            
            # Risk scores
            credit_risk = flt(risk_data.get("credit_risk_score", 0))
            operational_risk = flt(risk_data.get("operational_risk_score", 0)) 
            compliance_risk = flt(risk_data.get("compliance_risk_score", 0))
            
            return {
                "credit_risk": {
                    "value": credit_risk,
                    "target": 25,  # Low risk target (0-100 scale)
                    "variance_points": credit_risk - 25,
                    "rag_status": self._get_rag_status(credit_risk, thresholds={"green": 25, "amber": 50}, reverse=True),
                    "label": "Credit Risk Score",
                    "format": "risk_score"
                },
                "operational_risk": {
                    "value": operational_risk,
                    "target": 25,
                    "variance_points": operational_risk - 25,
                    "rag_status": self._get_rag_status(operational_risk, thresholds={"green": 25, "amber": 50}, reverse=True),
                    "label": "Operational Risk Score", 
                    "format": "risk_score"
                },
                "compliance_risk": {
                    "value": compliance_risk,
                    "target": 15,  # Very low compliance risk target
                    "variance_points": compliance_risk - 15,
                    "rag_status": self._get_rag_status(compliance_risk, thresholds={"green": 15, "amber": 30}, reverse=True),
                    "label": "Compliance Risk Score",
                    "format": "risk_score"
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting risk KPIs: {e}")
            return self._get_error_kpis("Risk")
    
    def _get_rag_status(self, value: float, thresholds: Dict[str, float], reverse: bool = False) -> str:
        """
        Calculate RAG (Red/Amber/Green) status based on value and thresholds
        
        Args:
            value: The metric value
            thresholds: Dict with 'green' and 'amber' threshold values
            reverse: If True, lower values are better (for risk metrics)
        """
        if not value:
            return "red"
            
        green_threshold = thresholds.get("green", 0)
        amber_threshold = thresholds.get("amber", 0)
        
        if reverse:
            # Lower values are better
            if value <= green_threshold:
                return "green"
            elif value <= amber_threshold:
                return "amber"
            else:
                return "red"
        else:
            # Higher values are better
            if value >= green_threshold:
                return "green"
            elif value >= amber_threshold:
                return "amber"
            else:
                return "red"
    
    def _get_error_kpis(self, domain: str) -> Dict[str, Any]:
        """Return error placeholder KPIs when data is unavailable"""
        return {
            "error": f"Unable to load {domain} KPIs",
            "status": "unavailable"
        }
    
    def _get_executive_alerts(self) -> List[Dict[str, Any]]:
        """Get top priority alerts across all departments"""
        alerts = []
        
        try:
            # Financial alerts
            strategic_data = self.strategic_finance.get_executive_kpis()
            cash_runway = flt(strategic_data.get("cash_runway_weeks", 0))
            if cash_runway < 8:
                alerts.append({
                    "priority": "critical",
                    "department": "Finance",
                    "message": f"Cash runway below 8 weeks: {cash_runway:.1f} weeks remaining",
                    "rag_status": "red"
                })
            
            # Sales alerts  
            sales_data = self.sales_intel.get_sales_overview()
            conversion_rate = flt(sales_data.get("conversion_rate", 0))
            if conversion_rate < 10:
                alerts.append({
                    "priority": "high",
                    "department": "Sales",
                    "message": f"Lead conversion rate critical: {conversion_rate:.1f}%",
                    "rag_status": "red"
                })
            
            # Customer alerts
            customer_data = self.customer_intel.get_customer_overview()
            churn_rate = flt(customer_data.get("churn_rate", 0))
            if churn_rate > 10:
                alerts.append({
                    "priority": "high", 
                    "department": "Customer",
                    "message": f"Customer churn elevated: {churn_rate:.1f}%",
                    "rag_status": "red"
                })
            
            # Inventory alerts
            inventory_data = self.inventory_intel.get_inventory_overview()
            stockout_rate = flt(inventory_data.get("stockout_rate", 0))
            if stockout_rate > 8:
                alerts.append({
                    "priority": "high",
                    "department": "Operations", 
                    "message": f"Stockout rate critical: {stockout_rate:.1f}%",
                    "rag_status": "red"
                })
            
            # Risk alerts
            risk_data = self.risk_intel.get_risk_overview()
            compliance_risk = flt(risk_data.get("compliance_risk_score", 0))
            if compliance_risk > 50:
                alerts.append({
                    "priority": "critical",
                    "department": "Risk",
                    "message": f"Compliance risk elevated: {compliance_risk:.0f}/100",
                    "rag_status": "red"
                })
            
            # Sort by priority (critical > high > medium > low)
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            alerts.sort(key=lambda x: priority_order.get(x["priority"], 4))
            
            return alerts[:5]  # Return top 5 alerts
            
        except Exception as e:
            logger.error(f"Error getting executive alerts: {e}")
            return [{
                "priority": "low",
                "department": "System",
                "message": "Unable to load alerts",
                "rag_status": "amber"
            }]
    
    def _get_trend_sparklines(self, period: str) -> Dict[str, List[float]]:
        """Get trend data for sparkline charts from real database queries"""
        try:
            trends = {}

            # Revenue trend: Monthly GL Entry sum for Income accounts over last 12 months
            revenue_data = frappe.db.sql("""
                SELECT YEAR(posting_date) as yr, MONTH(posting_date) as mo,
                       SUM(credit - debit) as amount
                FROM `tabGL Entry`
                WHERE account IN (SELECT name FROM `tabAccount` WHERE root_type='Income')
                  AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                  AND is_cancelled = 0
                GROUP BY YEAR(posting_date), MONTH(posting_date)
                ORDER BY YEAR(posting_date), MONTH(posting_date)
            """, as_dict=1)
            trends["revenue"] = [flt(r.amount) for r in revenue_data] if revenue_data else []

            # Margin trend: (Income - Expense) / Income per month
            margin_data = frappe.db.sql("""
                SELECT yr, mo,
                       CASE WHEN income > 0 THEN ((income - expense) / income) * 100 ELSE 0 END as margin_pct
                FROM (
                    SELECT YEAR(posting_date) as yr, MONTH(posting_date) as mo,
                           SUM(CASE WHEN account IN (SELECT name FROM `tabAccount` WHERE root_type='Income')
                               THEN credit - debit ELSE 0 END) as income,
                           SUM(CASE WHEN account IN (SELECT name FROM `tabAccount` WHERE root_type='Expense')
                               THEN debit - credit ELSE 0 END) as expense
                    FROM `tabGL Entry`
                    WHERE posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                      AND is_cancelled = 0
                    GROUP BY YEAR(posting_date), MONTH(posting_date)
                ) t
                ORDER BY yr, mo
            """, as_dict=1)
            trends["margin"] = [flt(r.margin_pct) for r in margin_data] if margin_data else []

            # Sales growth: Monthly Sales Invoice totals
            sales_data = frappe.db.sql("""
                SELECT YEAR(posting_date) as yr, MONTH(posting_date) as mo,
                       SUM(grand_total) as total
                FROM `tabSales Invoice`
                WHERE posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                  AND docstatus = 1
                GROUP BY YEAR(posting_date), MONTH(posting_date)
                ORDER BY YEAR(posting_date), MONTH(posting_date)
            """, as_dict=1)
            sales_totals = [flt(r.total) for r in sales_data] if sales_data else []
            # Convert to MoM growth percentages
            sales_growth = []
            for i, total in enumerate(sales_totals):
                if i == 0 or sales_totals[i - 1] == 0:
                    sales_growth.append(0)
                else:
                    sales_growth.append(((total - sales_totals[i - 1]) / sales_totals[i - 1]) * 100)
            trends["sales_growth"] = sales_growth

            # Churn rate: Customers with no Sales Invoice in last 90d vs prior, monthly proxy
            churn_data = frappe.db.sql("""
                SELECT YEAR(month_start) as yr, MONTH(month_start) as mo,
                       CASE WHEN total_customers > 0
                           THEN (inactive_customers / total_customers) * 100 ELSE 0 END as churn_pct
                FROM (
                    SELECT DATE_FORMAT(m.month_start, '%%Y-%%m-01') as month_start,
                           COUNT(DISTINCT c.name) as total_customers,
                           SUM(CASE WHEN c.name NOT IN (
                               SELECT DISTINCT customer FROM `tabSales Invoice`
                               WHERE docstatus = 1
                                 AND posting_date BETWEEN DATE_SUB(m.month_start, INTERVAL 90 DAY) AND m.month_start
                           ) THEN 1 ELSE 0 END) as inactive_customers
                    FROM (
                        SELECT DATE_SUB(CURDATE(), INTERVAL n MONTH) as month_start
                        FROM (SELECT 0 n UNION SELECT 1 UNION SELECT 2 UNION SELECT 3
                              UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7
                              UNION SELECT 8 UNION SELECT 9 UNION SELECT 10 UNION SELECT 11) nums
                    ) m
                    CROSS JOIN `tabCustomer` c
                    WHERE c.disabled = 0
                    GROUP BY m.month_start
                ) sub
                ORDER BY yr, mo
            """, as_dict=1)
            trends["churn_rate"] = [flt(r.churn_pct) for r in churn_data] if churn_data else []

            # Inventory turns: Monthly COGS / Avg inventory from Stock Ledger
            inv_data = frappe.db.sql("""
                SELECT YEAR(posting_date) as yr, MONTH(posting_date) as mo,
                       SUM(ABS(actual_qty) * valuation_rate) as turnover_value
                FROM `tabStock Ledger Entry`
                WHERE posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                  AND is_cancelled = 0
                  AND actual_qty < 0
                GROUP BY YEAR(posting_date), MONTH(posting_date)
                ORDER BY YEAR(posting_date), MONTH(posting_date)
            """, as_dict=1)

            avg_stock = frappe.db.sql("""
                SELECT SUM(stock_value) as total_value
                FROM `tabBin`
                WHERE stock_value > 0
            """, as_dict=1)
            avg_stock_value = flt(avg_stock[0].total_value) if avg_stock else 0
            monthly_avg = avg_stock_value or 1  # avoid division by zero

            trends["inventory_turns"] = [
                round(flt(r.turnover_value) / monthly_avg * 12, 2) for r in inv_data
            ] if inv_data else []

            # Credit risk trend: Monthly average overdue ratio
            risk_data = frappe.db.sql("""
                SELECT YEAR(posting_date) as yr, MONTH(posting_date) as mo,
                       CASE WHEN SUM(grand_total) > 0
                           THEN (SUM(CASE WHEN due_date < posting_date THEN outstanding_amount ELSE 0 END)
                                 / SUM(grand_total)) * 100
                           ELSE 0 END as risk_pct
                FROM `tabSales Invoice`
                WHERE posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                  AND docstatus = 1
                GROUP BY YEAR(posting_date), MONTH(posting_date)
                ORDER BY YEAR(posting_date), MONTH(posting_date)
            """, as_dict=1)
            trends["credit_risk"] = [flt(r.risk_pct) for r in risk_data] if risk_data else []

            # Headcount trend: Monthly active employee count
            headcount_data = frappe.db.sql("""
                SELECT YEAR(m.month_start) as yr, MONTH(m.month_start) as mo,
                       COUNT(e.name) as headcount
                FROM (
                    SELECT DATE_SUB(CURDATE(), INTERVAL n MONTH) as month_start
                    FROM (SELECT 0 n UNION SELECT 1 UNION SELECT 2 UNION SELECT 3
                          UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7
                          UNION SELECT 8 UNION SELECT 9 UNION SELECT 10 UNION SELECT 11) nums
                ) m
                LEFT JOIN `tabEmployee` e ON e.date_of_joining <= LAST_DAY(m.month_start)
                    AND (e.relieving_date IS NULL OR e.relieving_date > m.month_start)
                    AND e.status = 'Active'
                GROUP BY m.month_start
                ORDER BY yr, mo
            """, as_dict=1)
            trends["headcount"] = [flt(r.headcount) for r in headcount_data] if headcount_data else []

            # OEE trend: Monthly work order completion rate as proxy
            oee_data = frappe.db.sql("""
                SELECT YEAR(planned_start_date) as yr, MONTH(planned_start_date) as mo,
                       CASE WHEN COUNT(*) > 0
                           THEN (SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) / COUNT(*)) * 100
                           ELSE 0 END as oee_pct
                FROM `tabWork Order`
                WHERE planned_start_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                  AND docstatus = 1
                GROUP BY YEAR(planned_start_date), MONTH(planned_start_date)
                ORDER BY YEAR(planned_start_date), MONTH(planned_start_date)
            """, as_dict=1)
            trends["oee"] = [flt(r.oee_pct) for r in oee_data] if oee_data else []

            return trends

        except Exception as e:
            logger.error(f"Error getting trend sparklines: {e}")
            return {}
    
    def _generate_executive_narrative(self, period: str) -> str:
        """Generate AI-powered executive narrative summary"""
        try:
            kpi_context = self._build_narrative_context(period)

            # Try AI-generated narrative via ExecutiveIntelligenceAgent
            try:
                from insights.agents.executive_agent import ExecutiveIntelligenceAgent
                agent = ExecutiveIntelligenceAgent()
                result = agent.execute(
                    query=f"Generate a 2-3 sentence executive summary for {period} based on these KPIs: {kpi_context}",
                    session_id="narrative-generation",
                )
                narrative = result.get("response", "")
                if narrative and len(narrative) > 20:
                    return narrative
            except Exception as ai_err:
                logger.warning(f"AI narrative generation unavailable: {ai_err}")

            # Fallback to data-driven narrative
            return self._build_fallback_narrative(period)

        except Exception as e:
            logger.error(f"Error generating executive narrative: {e}")
            return "Unable to generate executive summary narrative."

    def _build_narrative_context(self, period: str) -> str:
        """Build a KPI context string for AI narrative generation"""
        try:
            parts = []
            fin = self._get_financial_kpis(period)
            rev = fin.get("revenue", {})
            if rev.get("value"):
                parts.append(f"Revenue: {rev['value']:,.0f} (target {rev.get('target', 0):,.0f}, {rev.get('variance_pct', 0):+.1f}%)")
            margin = fin.get("net_margin", {})
            if margin.get("value"):
                parts.append(f"Net Margin: {margin['value']:.1f}%")
            cash = fin.get("cash_runway", {})
            if cash.get("value"):
                parts.append(f"Cash Runway: {cash['value']:.1f} weeks")

            sales = self._get_sales_kpis(period)
            growth = sales.get("growth_rate", {})
            if growth.get("value"):
                parts.append(f"Sales Growth: {growth['value']:.1f}%")

            cust = self._get_customer_kpis(period)
            churn = cust.get("churn_rate", {})
            if churn.get("value"):
                parts.append(f"Churn Rate: {churn['value']:.1f}%")

            return "; ".join(parts) if parts else "KPI data unavailable"
        except Exception:
            return "KPI data unavailable"

    def _build_fallback_narrative(self, period: str) -> str:
        """Build a data-driven narrative from actual KPI values when AI is unavailable"""
        try:
            parts = []
            fin = self._get_financial_kpis(period)
            rev = fin.get("revenue", {})
            if rev.get("value") and rev.get("target"):
                variance = rev.get("variance_pct", 0)
                direction = "above" if variance >= 0 else "below"
                parts.append(
                    f"Revenue is at {self.company_currency} {rev['value']:,.0f} vs target "
                    f"{self.company_currency} {rev['target']:,.0f} ({abs(variance):.1f}% {direction} target)."
                )
            cash = fin.get("cash_runway", {})
            if cash.get("value"):
                parts.append(f"Cash runway stands at {cash['value']:.1f} weeks.")

            sales = self._get_sales_kpis(period)
            growth = sales.get("growth_rate", {})
            if growth.get("value") is not None:
                parts.append(f"Sales growth is {growth['value']:.1f}%.")

            cust = self._get_customer_kpis(period)
            churn = cust.get("churn_rate", {})
            if churn.get("value") is not None:
                status = "elevated" if churn["value"] > 8 else "within target"
                parts.append(f"Customer churn at {churn['value']:.1f}% is {status}.")

            if parts:
                return " ".join(parts)
            return f"Business performance data for {period} is being compiled."
        except Exception:
            return f"Business performance summary for {period} is being compiled."
    
    def _get_hr_kpis(self, period: str) -> Dict[str, Any]:
        """Extract top 3 HR KPIs with RAG status"""
        try:
            hr_data = self.hr_intel.get_hr_overview(period)

            headcount_metrics = hr_data.get("headcount_metrics", {})
            attrition_metrics = hr_data.get("attrition_metrics", {})
            engagement_data = hr_data.get("engagement_indicators", {})

            total_employees = flt(headcount_metrics.get("total_employees", 0))
            net_change = flt(headcount_metrics.get("net_change", 0))
            attrition_rate = flt(attrition_metrics.get("attrition_rate", 0))
            engagement_score = flt(engagement_data.get("engagement_score", 0))

            return {
                "headcount": {
                    "value": total_employees,
                    "net_change": net_change,
                    "variance_pct": (net_change / total_employees * 100) if total_employees else 0,
                    "rag_status": self._get_rag_status(
                        total_employees, thresholds={"green": 1, "amber": 1}
                    ) if total_employees > 0 else "amber",
                    "label": f"Headcount ({period})",
                    "format": "decimal"
                },
                "attrition_rate": {
                    "value": attrition_rate,
                    "target": 10.0,
                    "variance_pct": attrition_rate - 10.0,
                    "rag_status": self._get_rag_status(
                        attrition_rate, thresholds={"green": 10, "amber": 15}, reverse=True
                    ),
                    "label": "Attrition Rate %",
                    "format": "percentage"
                },
                "engagement_score": {
                    "value": engagement_score,
                    "target": 75,
                    "variance_pct": engagement_score - 75,
                    "rag_status": self._get_rag_status(
                        engagement_score, thresholds={"green": 75, "amber": 50}
                    ),
                    "label": "Engagement Score",
                    "format": "decimal"
                }
            }

        except Exception as e:
            logger.error(f"Error getting HR KPIs: {e}")
            return self._get_error_kpis("HR")

    def _calculate_business_health_score(self, kpis: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall business health score from departmental KPIs"""
        try:
            total_score = 0
            total_weight = 0
            department_scores = {}
            
            # Weight each department's contribution to overall score
            weights = {
                "financial": 0.27,
                "sales": 0.22,
                "customer": 0.17,
                "operations": 0.14,
                "risk": 0.09,
                "hr": 0.11
            }
            
            for department, weight in weights.items():
                if department in kpis and "error" not in kpis[department]:
                    # Calculate department score from RAG status
                    dept_kpis = kpis[department]
                    rag_scores = []
                    
                    for kpi_name, kpi_data in dept_kpis.items():
                        if isinstance(kpi_data, dict) and "rag_status" in kpi_data:
                            rag_status = kpi_data["rag_status"]
                            if rag_status == "green":
                                rag_scores.append(100)
                            elif rag_status == "amber":
                                rag_scores.append(70)
                            else:  # red
                                rag_scores.append(30)
                    
                    if rag_scores:
                        dept_score = np.mean(rag_scores)
                        department_scores[department] = dept_score
                        total_score += dept_score * weight
                        total_weight += weight
            
            overall_score = total_score / total_weight if total_weight > 0 else 50
            
            # Determine overall RAG status
            if overall_score >= 80:
                overall_rag = "green"
            elif overall_score >= 60:
                overall_rag = "amber"
            else:
                overall_rag = "red"
            
            return {
                "overall_score": round(overall_score, 1),
                "overall_rag": overall_rag,
                "department_scores": department_scores,
                "score_breakdown": {
                    "excellent": sum(1 for score in department_scores.values() if score >= 80),
                    "good": sum(1 for score in department_scores.values() if 60 <= score < 80),
                    "needs_attention": sum(1 for score in department_scores.values() if score < 60)
                }
            }
            
        except Exception as e:
            logger.error(f"Error calculating business health score: {e}")
            return {
                "overall_score": 50,
                "overall_rag": "amber",
                "error": "Unable to calculate health score"
            }
    
    def get_department_deep_dive(self, department: str, period: str = "YTD") -> Dict[str, Any]:
        """Get detailed metrics for a specific department"""
        try:
            if department == "financial":
                return self.strategic_finance.get_executive_kpis()
            elif department == "sales":
                return self.sales_intel.get_sales_overview()
            elif department == "customer":
                return self.customer_intel.get_customer_overview()
            elif department == "operations":
                inventory_data = self.inventory_intel.get_inventory_overview()
                procurement_data = self.procurement_intel.get_procurement_overview()
                return {**inventory_data, **procurement_data}
            elif department == "risk":
                return self.risk_intel.get_risk_overview()
            else:
                return {"error": f"Unknown department: {department}"}
                
        except Exception as e:
            logger.error(f"Error getting {department} deep dive: {e}")
            return {"error": str(e)}


# API functions for Frappe
@frappe.whitelist()
def get_executive_summary(period="YTD"):
    """API endpoint for executive summary"""
    try:
        executive = ExecutiveIntelligence()
        return executive.get_executive_summary(period)
    except Exception as e:
        frappe.log_error(f"Executive summary API error: {e}")
        return {"error": str(e)}


@frappe.whitelist()
def get_department_deep_dive(department, period="YTD"):
    """API endpoint for department deep dive"""
    try:
        executive = ExecutiveIntelligence()
        return executive.get_department_deep_dive(department, period)
    except Exception as e:
        frappe.log_error(f"Department deep dive API error: {e}")
        return {"error": str(e)}


@frappe.whitelist()  
def get_business_health_dashboard():
    """API endpoint for business health dashboard"""
    try:
        executive = ExecutiveIntelligence()
        summary = executive.get_executive_summary("YTD")
        return {
            "health_score": summary.get("business_health_score", {}),
            "alerts": summary.get("alerts", []),
            "kpi_summary": summary.get("kpis", {}),
            "narrative": summary.get("narrative", "")
        }
    except Exception as e:
        frappe.log_error(f"Business health dashboard API error: {e}")
        return {"error": str(e)}


@guarded_task
def update_executive_dashboard():
    """
    Scheduler function to update executive dashboard data daily.
    This caches the latest executive summary for faster dashboard loading.
    """
    try:
        logger.info("Starting executive dashboard update...")

        executive = ExecutiveIntelligence()
        cache = frappe.cache()

        # Generate fresh executive summary for all periods
        periods = ["MTD", "QTD", "YTD", "TTM"]

        for period in periods:
            summary = executive.get_executive_summary(period)

            # Cache the summary for 24 hours
            cache_key = f"executive_summary_{period}"
            cache.set_value(cache_key, summary, expires_in_sec=86400)

            logger.info(f"Updated executive summary for period: {period}")

        # Also update business health specifically
        health_data = get_business_health_dashboard()
        cache.set_value("business_health_dashboard", health_data, expires_in_sec=86400)

        logger.info("Executive dashboard update completed successfully")

        # Send alerts if business health is critical
        overall_score = health_data.get("health_score", {}).get("overall_score", 50)
        if overall_score < 40:
            _send_critical_health_alert(overall_score, health_data.get("alerts", []))

    except Exception as e:
        logger.error(f"Error updating executive dashboard: {e}")
        frappe.log_error(f"Executive dashboard update error: {e}")


def _send_critical_health_alert(health_score, alerts):
    """Send alert when business health score is critically low"""
    try:
        # Get CEO/executive email addresses from User doctype
        # This would need to be configured based on roles
        executives = frappe.get_all("User", 
            filters={
                "enabled": 1,
                "has_desk_access": 1
            },
            fields=["email", "full_name"]
        )
        
        # For now, we'll log the alert. In production, this would send emails
        alert_message = f"""
        CRITICAL BUSINESS HEALTH ALERT
        
        Overall Business Health Score: {health_score}%
        
        Critical Issues:
        """
        
        for alert in alerts[:3]:  # Top 3 alerts
            if alert.get("priority") == "critical":
                alert_message += f"- {alert.get('department')}: {alert.get('message')}\n"
        
        logger.warning(f"Critical business health alert: {alert_message}")
        
        # TODO: Implement actual email sending to executives
        # for executive in executives:
        #     frappe.sendmail(
        #         recipients=[executive.email],
        #         subject="Critical Business Health Alert",
        #         message=alert_message
        #     )
        
    except Exception as e:
        logger.error(f"Error sending critical health alert: {e}")