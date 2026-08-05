"""
Executive Intelligence Module

Aggregates top KPIs from all departmental intelligence modules to provide
a unified C-suite dashboard with RAG status indicators and trend analysis.
"""

import frappe
from frappe import _
from frappe.utils import nowdate, add_months, add_days, flt, cstr
from datetime import datetime, date, timedelta
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
from .manufacturing_intelligence import ManufacturingIntelligence

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
            self.company_currency = (
                frappe.db.get_default("currency")
                or frappe.db.get_single_value("System Settings", "default_currency")
                or "USD"
            )
        except Exception:
            self.company_currency = "USD"

        # Cache for module data to avoid repeated predict() calls
        self._cache = {}

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
            self.manufacturing_intel = ManufacturingIntelligence()
        except Exception as e:
            logger.error(f"Error initializing intelligence modules: {e}")
            frappe.log_error(f"Executive Intelligence init error: {e}")

    def _get_module_data(self, key, getter):
        """Get cached module data from Redis or fetch it"""
        cache_key = f"exec_module_data:{key}"
        cached = frappe.cache.get_value(cache_key)
        if cached and isinstance(cached, dict) and "data" in cached:
            cached_time = cached.get("cached_at")
            if cached_time:
                age = datetime.now() - datetime.fromisoformat(cached_time)
                if age.total_seconds() < 7200:  # 2 hour TTL
                    return cached["data"]

        try:
            data = getter() or {}
            frappe.cache.set_value(
                cache_key,
                {"data": data, "cached_at": datetime.now().isoformat()},
                expires_in_sec=7200
            )
            return data
        except Exception as e:
            logger.error(f"Error fetching {key}: {e}")
            return {}

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
        # Check Redis cache first
        cache_key = f"executive_summary:{period}"
        cached = frappe.cache.get_value(cache_key)
        if cached and isinstance(cached, dict) and "data" in cached:
            cached_time = cached.get("cached_at")
            if cached_time:
                age = datetime.now() - datetime.fromisoformat(cached_time)
                if age.total_seconds() < 3600:  # 1 hour TTL
                    return cached["data"]

        try:
            # Build KPIs first so narrative can reference them
            kpis = {
                "financial": self._get_financial_kpis(period),
                "sales": self._get_sales_kpis(period),
                "customer": self._get_customer_kpis(period),
                "operations": self._get_operations_kpis(period),
                "risk": self._get_risk_kpis(period),
                "hr": self._get_hr_kpis(period),
                "manufacturing": self._get_manufacturing_kpis(period)
            }

            summary = {
                "period": period,
                "generated_at": datetime.now().isoformat(),
                "currency": self.company_currency,
                "kpis": kpis,
                "alerts": self._get_executive_alerts(kpis),
                "trends": self._get_trend_sparklines(period),
                "narrative": self._generate_executive_narrative(kpis, period),
                "business_health_score": self._calculate_business_health_score(kpis),
            }

            # Cache the result before returning
            frappe.cache.set_value(
                cache_key,
                {"data": summary, "cached_at": datetime.now().isoformat()},
                expires_in_sec=3600
            )
            return summary

        except Exception as e:
            logger.error(f"Error generating executive summary: {e}")
            return {
                "error": str(e),
                "period": period,
                "generated_at": datetime.now().isoformat()
            }

    def _get_financial_kpis(self, period: str) -> Dict[str, Any]:
        """Extract top 3 financial KPIs from financial_intel.predict() and strategic_finance.predict()"""
        try:
            fin_data = self._get_module_data("financial", self.financial_intel.predict)
            overview = fin_data.get("overview", {})
            cash_flow = fin_data.get("cash_flow", {})

            # Revenue from financial overview
            ytd_revenue = flt(overview.get("ytd_revenue", 0))
            ytd_target = flt(overview.get("ytd_budget", 0))
            revenue_variance = ((ytd_revenue / ytd_target) - 1) * 100 if ytd_target else 0

            # Net margin
            net_margin = flt(overview.get("net_margin", 0))

            # Cash runway
            runway_months = flt(cash_flow.get("runway_months", 0))
            cash_runway_weeks = runway_months * 4.33

            # RAG: compare variance if target exists, else use revenue presence
            revenue_rag = (
                self._get_rag_status(revenue_variance, thresholds={"green": 5, "amber": -5})
                if ytd_target else ("green" if ytd_revenue > 0 else "amber")
            )

            return {
                "revenue": {
                    "value": ytd_revenue,
                    "target": ytd_target,
                    "variance_pct": revenue_variance,
                    "rag_status": revenue_rag,
                    "label": f"Revenue ({period})",
                    "format": "currency"
                },
                "net_margin": {
                    "value": net_margin,
                    "target": 10.0,
                    "variance_pct": (net_margin - 10.0),
                    "rag_status": self._get_rag_status(net_margin, thresholds={"green": 10, "amber": 5}),
                    "label": "Net Margin %",
                    "format": "percentage"
                },
                "cash_runway": {
                    "value": round(cash_runway_weeks, 1),
                    "target": 13,
                    "variance_weeks": cash_runway_weeks - 13,
                    "rag_status": self._get_rag_status(cash_runway_weeks, thresholds={"green": 13, "amber": 8}),
                    "label": "Cash Runway (Weeks)",
                    "format": "decimal"
                }
            }

        except Exception as e:
            logger.error(f"Error getting financial KPIs: {e}")
            return self._get_error_kpis("Financial")

    def _get_sales_kpis(self, period: str) -> Dict[str, Any]:
        """Extract top 3 sales KPIs from sales_intel.predict()"""
        try:
            sales_data = self._get_module_data("sales", self.sales_intel.predict)
            revenue = sales_data.get("revenue_metrics", sales_data.get("summary", {}))
            pipeline = sales_data.get("pipeline", {})
            comparisons = sales_data.get("comparisons", {})

            # Sales growth (MoM)
            mom = comparisons.get("mom", {})
            growth_rate = flt(mom.get("growth_pct", revenue.get("mom_growth", 0)))

            # Conversion rate from pipeline
            conversion_rate = flt(pipeline.get("conversion_rate", 0))

            # Pipeline value
            pipeline_value = flt(pipeline.get("total_value", 0))

            return {
                "growth_rate": {
                    "value": growth_rate,
                    "target": 15.0,
                    "variance_pct": growth_rate - 15.0,
                    "rag_status": self._get_rag_status(growth_rate, thresholds={"green": 15, "amber": 5}),
                    "label": f"Sales Growth ({period})",
                    "format": "percentage"
                },
                "conversion_rate": {
                    "value": conversion_rate,
                    "target": 25.0,
                    "variance_pct": conversion_rate - 25.0,
                    "rag_status": self._get_rag_status(conversion_rate, thresholds={"green": 25, "amber": 15}),
                    "label": "Lead Conversion %",
                    "format": "percentage"
                },
                "pipeline_value": {
                    "value": pipeline_value,
                    "target": 1000000,
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
        """Extract top 3 customer KPIs from customer_intel.predict()"""
        try:
            cust_data = self._get_module_data("customer", self.customer_intel.predict)
            summary = cust_data.get("summary", {})

            raw_churn = flt(summary.get("avg_churn_risk", 0))
            # Value may be 0-1 ratio or 0-100 score; normalize to 0-100
            avg_churn_risk = raw_churn * 100 if raw_churn < 1 else min(raw_churn, 100)
            avg_health = flt(summary.get("avg_health_score", 0))
            total_clv = flt(summary.get("total_clv", 0))
            total_customers = flt(summary.get("total_customers", 0))
            avg_clv = flt(summary.get("avg_clv", total_clv / total_customers if total_customers else 0))

            return {
                "churn_risk": {
                    "value": avg_churn_risk,
                    "target": 5.0,
                    "variance_pct": avg_churn_risk - 5.0,
                    "rag_status": self._get_rag_status(avg_churn_risk, thresholds={"green": 5, "amber": 8}, reverse=True),
                    "label": f"Avg Churn Risk ({period})",
                    "format": "percentage"
                },
                "health_score": {
                    "value": avg_health,
                    "target": 75,
                    "variance_pct": avg_health - 75,
                    "rag_status": self._get_rag_status(avg_health, thresholds={"green": 75, "amber": 50}),
                    "label": "Avg Customer Health",
                    "format": "decimal"
                },
                "avg_clv": {
                    "value": avg_clv,
                    "target": 100000,
                    "variance_pct": ((avg_clv / 100000) - 1) * 100 if avg_clv else 0,
                    "rag_status": self._get_rag_status(avg_clv, thresholds={"green": 100000, "amber": 50000}),
                    "label": "Avg Customer LTV",
                    "format": "currency"
                }
            }

        except Exception as e:
            logger.error(f"Error getting customer KPIs: {e}")
            return self._get_error_kpis("Customer")

    def _get_operations_kpis(self, period: str) -> Dict[str, Any]:
        """Extract top 3 operations KPIs - uses cache or lightweight SQL fallback"""
        try:
            # Try cached data first (fast path)
            inv_data = self.inventory_intel.get_cached_results("inventory_intelligence") or {}
            proc_data = self.procurement_intel.get_cached_results("procurement_intelligence") or {}

            if inv_data:
                stock_overview = inv_data.get("stock_overview", {})
                turnover = inv_data.get("turnover_analysis", {})
                total_items = flt(stock_overview.get("total_items", 0))
                out_of_stock = flt(stock_overview.get("out_of_stock_count", 0))
                inventory_turns = flt(turnover.get("overall_turnover_ratio", 0))
            else:
                # Lightweight SQL fallback instead of full train()
                stock = frappe.db.sql("""
                    SELECT COUNT(DISTINCT item_code) as total_items,
                           SUM(CASE WHEN actual_qty <= 0 THEN 1 ELSE 0 END) as out_of_stock
                    FROM `tabBin` WHERE actual_qty != 0 OR reserved_qty != 0 OR ordered_qty != 0
                """, as_dict=True)[0]
                total_items = flt(stock.total_items)
                out_of_stock = flt(stock.out_of_stock)
                # Simple annual turnover estimate
                cogs = frappe.db.sql("""
                    SELECT SUM(ABS(actual_qty) * valuation_rate) as cogs
                    FROM `tabStock Ledger Entry`
                    WHERE posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                      AND is_cancelled = 0 AND actual_qty < 0
                """, as_dict=True)[0]
                avg_stock = frappe.db.sql(
                    "SELECT SUM(stock_value) as v FROM `tabBin` WHERE stock_value > 0", as_dict=True
                )[0]
                inventory_turns = flt(cogs.cogs) / flt(avg_stock.v) if flt(avg_stock.v) else 0

            stockout_rate = (out_of_stock / total_items * 100) if total_items else 0

            if proc_data:
                supplier_perf = proc_data.get("supplier_performance", {})
                supplier_score = flt(supplier_perf.get("avg_score", 0))
            else:
                # Lightweight: average supplier rating
                rating = frappe.db.sql("""
                    SELECT AVG(
                        (CASE WHEN on_time_delivery_pct IS NOT NULL THEN on_time_delivery_pct ELSE 80 END +
                         CASE WHEN quality_score IS NOT NULL THEN quality_score ELSE 80 END) / 2
                    ) as avg_score
                    FROM (
                        SELECT s.name,
                            (SELECT AVG(CASE WHEN pr.posting_date <= po.schedule_date THEN 100 ELSE 0 END)
                             FROM `tabPurchase Receipt` pr
                             JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
                             JOIN `tabPurchase Order` po ON pri.purchase_order = po.name
                             WHERE pr.supplier = s.name AND pr.docstatus = 1
                               AND pri.purchase_order IS NOT NULL AND pri.purchase_order != ''
                               AND pr.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                            ) as on_time_delivery_pct,
                            NULL as quality_score
                        FROM `tabSupplier` s WHERE s.disabled = 0
                        LIMIT 100
                    ) sub
                """, as_dict=True)[0]
                supplier_score = flt(rating.avg_score) if rating.avg_score else 75

            return {
                "stockout_rate": {
                    "value": round(stockout_rate, 1),
                    "target": 2.0,
                    "variance_pct": stockout_rate - 2.0,
                    "rag_status": self._get_rag_status(stockout_rate, thresholds={"green": 2, "amber": 5}, reverse=True),
                    "label": "Stockout Rate %",
                    "format": "percentage"
                },
                "inventory_turns": {
                    "value": inventory_turns,
                    "target": 6.0,
                    "variance_turns": inventory_turns - 6.0,
                    "rag_status": self._get_rag_status(inventory_turns, thresholds={"green": 6, "amber": 4}),
                    "label": "Inventory Turns (Annual)",
                    "format": "decimal"
                },
                "supplier_performance": {
                    "value": supplier_score,
                    "target": 85,
                    "variance_points": supplier_score - 85,
                    "rag_status": self._get_rag_status(supplier_score, thresholds={"green": 85, "amber": 70}),
                    "label": "Supplier Performance %",
                    "format": "percentage"
                }
            }

        except Exception as e:
            logger.error(f"Error getting operations KPIs: {e}")
            return self._get_error_kpis("Operations")

    def _get_risk_kpis(self, period: str) -> Dict[str, Any]:
        """Extract top 3 risk KPIs - uses cache or lightweight SQL fallback"""
        try:
            risk_data = self.risk_intel.get_cached_results("risk_intelligence") or {}

            if risk_data:
                overview = risk_data.get("overview", {})
                components = overview.get("risk_components", {})
                credit_risk = flt(components.get("credit", {}).get("score", 0))
                operational_risk = flt(components.get("operational", {}).get("score", 0))
                compliance_risk = flt(components.get("compliance", {}).get("score", 0))
            else:
                # Lightweight SQL fallback: credit risk from overdue receivables
                overdue = frappe.db.sql("""
                    SELECT SUM(outstanding_amount) as overdue, SUM(grand_total) as total
                    FROM `tabSales Invoice`
                    WHERE docstatus = 1 AND outstanding_amount > 0
                      AND due_date < CURDATE()
                """, as_dict=True)[0]
                total_receivable = flt(overdue.total) or 1
                credit_risk = min(100, (flt(overdue.overdue) / total_receivable) * 100)

                # Operational risk: late work orders / purchase orders
                late_ops = frappe.db.sql("""
                    SELECT
                        (SELECT COUNT(*) FROM `tabWork Order`
                         WHERE docstatus = 1 AND status NOT IN ('Completed', 'Stopped', 'Cancelled')
                           AND expected_delivery_date < CURDATE()) as late_wo,
                        (SELECT COUNT(*) FROM `tabWork Order`
                         WHERE docstatus = 1 AND status NOT IN ('Completed', 'Stopped', 'Cancelled')) as total_wo
                """, as_dict=True)[0]
                total_wo = flt(late_ops.total_wo) or 1
                operational_risk = min(100, (flt(late_ops.late_wo) / total_wo) * 100)

                # Compliance risk is NOT a measured metric — no compliance
                # doctype/tracking exists. This is a heuristic proxy (30% of
                # credit risk) documented as such in the label below. See
                # plan-eng-review D3.6.
                compliance_risk = min(100, credit_risk * 0.3)

            return {
                "credit_risk": {
                    "value": credit_risk,
                    "target": 25,
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
                    "target": 15,
                    "variance_points": compliance_risk - 15,
                    "rag_status": self._get_rag_status(compliance_risk, thresholds={"green": 15, "amber": 30}, reverse=True),
                    "label": "Compliance Risk Score (estimated from credit risk)",
                    "format": "risk_score"
                }
            }

        except Exception as e:
            logger.error(f"Error getting risk KPIs: {e}")
            return self._get_error_kpis("Risk")

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

    def _get_manufacturing_kpis(self, period: str) -> Dict[str, Any]:
        """Extract top 3 Manufacturing KPIs with RAG status"""
        try:
            mfg_data = self.manufacturing_intel.get_manufacturing_overview(period)

            oee_data = mfg_data.get("oee_analysis", {})
            production_data = mfg_data.get("production_metrics", {})
            capacity_data = mfg_data.get("capacity_utilization", {})

            oee_score = flt(oee_data.get("oee_score_pct", 0))
            completion_rate = flt(production_data.get("completion_rate_pct", 0))
            capacity_util = flt(capacity_data.get("overall_utilization_pct", 0))

            return {
                "oee": {
                    "value": oee_score,
                    "target": 85.0,
                    "variance_pct": oee_score - 85.0,
                    "rag_status": self._get_rag_status(
                        oee_score, thresholds={"green": 85, "amber": 60}
                    ),
                    "label": "OEE %",
                    "format": "percentage"
                },
                "on_time_completion": {
                    "value": completion_rate,
                    "target": 90.0,
                    "variance_pct": completion_rate - 90.0,
                    "rag_status": self._get_rag_status(
                        completion_rate, thresholds={"green": 90, "amber": 80}
                    ),
                    "label": "On-time Completion %",
                    "format": "percentage"
                },
                "capacity_utilization": {
                    "value": capacity_util,
                    "target": 80.0,
                    "variance_pct": capacity_util - 80.0,
                    "rag_status": self._get_rag_status(
                        capacity_util, thresholds={"green": 80, "amber": 60}
                    ),
                    "label": "Capacity Utilization %",
                    "format": "percentage"
                }
            }

        except Exception as e:
            logger.error(f"Error getting Manufacturing KPIs: {e}")
            return self._get_error_kpis("Manufacturing")

    def _get_rag_status(self, value: float, thresholds: Dict[str, float], reverse: bool = False) -> str:
        """Calculate RAG (Red/Amber/Green) status based on value and thresholds"""
        if not value:
            return "red"

        green_threshold = thresholds.get("green", 0)
        amber_threshold = thresholds.get("amber", 0)

        if reverse:
            if value <= green_threshold:
                return "green"
            elif value <= amber_threshold:
                return "amber"
            else:
                return "red"
        else:
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

    def _get_executive_alerts(self, kpis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate alerts from already-computed KPIs (no extra API calls)"""
        alerts = []

        try:
            # Financial alerts
            fin = kpis.get("financial", {})
            if not fin.get("error"):
                cash = fin.get("cash_runway", {})
                if cash.get("value") and cash["value"] < 8:
                    alerts.append({
                        "priority": "critical",
                        "department": "Finance",
                        "message": f"Cash runway below 8 weeks: {cash['value']:.1f} weeks remaining",
                        "rag_status": "red"
                    })
                rev = fin.get("revenue", {})
                if rev.get("rag_status") == "red":
                    alerts.append({
                        "priority": "high",
                        "department": "Finance",
                        "message": f"Revenue significantly below target ({rev.get('variance_pct', 0):.1f}%)",
                        "rag_status": "red"
                    })

            # Sales alerts
            sales = kpis.get("sales", {})
            if not sales.get("error"):
                conv = sales.get("conversion_rate", {})
                if conv.get("value") and conv["value"] < 10:
                    alerts.append({
                        "priority": "high",
                        "department": "Sales",
                        "message": f"Lead conversion rate critical: {conv['value']:.1f}%",
                        "rag_status": "red"
                    })

            # Customer alerts
            cust = kpis.get("customer", {})
            if not cust.get("error"):
                churn = cust.get("churn_risk", {})
                if churn.get("value") and churn["value"] > 10:
                    alerts.append({
                        "priority": "high",
                        "department": "Customer",
                        "message": f"Customer churn risk elevated: {churn['value']:.1f}%",
                        "rag_status": "red"
                    })

            # Operations alerts
            ops = kpis.get("operations", {})
            if not ops.get("error"):
                stockout = ops.get("stockout_rate", {})
                if stockout.get("value") and stockout["value"] > 8:
                    alerts.append({
                        "priority": "high",
                        "department": "Operations",
                        "message": f"Stockout rate critical: {stockout['value']:.1f}%",
                        "rag_status": "red"
                    })

            # Risk alerts
            risk = kpis.get("risk", {})
            if not risk.get("error"):
                comp = risk.get("compliance_risk", {})
                if comp.get("value") and comp["value"] > 50:
                    alerts.append({
                        "priority": "critical",
                        "department": "Risk",
                        "message": f"Compliance risk elevated: {comp['value']:.0f}/100",
                        "rag_status": "red"
                    })

            # Sort by priority
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            alerts.sort(key=lambda x: priority_order.get(x["priority"], 4))

            return alerts[:5]

        except Exception as e:
            logger.error(f"Error getting executive alerts: {e}")
            return []

    def _get_trend_sparklines(self, period: str) -> Dict[str, List[float]]:
        """Get trend data for sparkline charts from real database queries"""
        cache_key = f"executive_sparklines:{period}"
        cached = frappe.cache.get_value(cache_key)
        if cached and isinstance(cached, dict) and "data" in cached:
            cached_time = cached.get("cached_at")
            if cached_time:
                age = datetime.now() - datetime.fromisoformat(cached_time)
                if age.total_seconds() < 7200:  # 2 hours
                    return cached["data"]
        try:
            trends = {}

            # Single GL Entry query for revenue + margin
            gl_data = frappe.db.sql("""
                SELECT YEAR(ge.posting_date) as yr, MONTH(ge.posting_date) as mo,
                       SUM(CASE WHEN a.root_type='Income' THEN ge.credit - ge.debit ELSE 0 END) as income,
                       SUM(CASE WHEN a.root_type='Expense' THEN ge.debit - ge.credit ELSE 0 END) as expense
                FROM `tabGL Entry` ge
                JOIN `tabAccount` a ON ge.account = a.name
                WHERE ge.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                  AND ge.is_cancelled = 0
                  AND a.root_type IN ('Income', 'Expense')
                GROUP BY YEAR(ge.posting_date), MONTH(ge.posting_date)
                ORDER BY yr, mo
            """, as_dict=1)
            trends["revenue"] = [flt(r.income) for r in gl_data] if gl_data else []
            trends["margin"] = [
                round(((flt(r.income) - flt(r.expense)) / flt(r.income)) * 100, 2) if flt(r.income) > 0 else 0
                for r in gl_data
            ] if gl_data else []

            # Single Sales Invoice query for sales growth + churn + credit risk
            si_data = frappe.db.sql("""
                SELECT YEAR(posting_date) as yr, MONTH(posting_date) as mo,
                       SUM(grand_total) as total,
                       COUNT(DISTINCT customer) as active_customers,
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

            # Sales growth
            sales_totals = [flt(r.total) for r in si_data] if si_data else []
            sales_growth = []
            for i, total in enumerate(sales_totals):
                if i == 0 or sales_totals[i - 1] == 0:
                    sales_growth.append(0)
                else:
                    sales_growth.append(((total - sales_totals[i - 1]) / sales_totals[i - 1]) * 100)
            trends["sales_growth"] = sales_growth

            # Churn rate
            total_customers = frappe.db.count("Customer", {"disabled": 0}) or 1
            trends["churn_rate"] = [
                round(max(0, (1 - flt(r.active_customers) / total_customers) * 100), 1)
                for r in si_data
            ] if si_data else []

            # Inventory turns
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
            monthly_avg = avg_stock_value or 1

            trends["inventory_turns"] = [
                round(flt(r.turnover_value) / monthly_avg * 12, 2) for r in inv_data
            ] if inv_data else []

            # Credit risk (from consolidated Sales Invoice query above)
            trends["credit_risk"] = [flt(r.risk_pct) for r in si_data] if si_data else []

            # Headcount trend
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

            # OEE trend
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

            # Cache before returning
            frappe.cache.set_value(
                cache_key,
                {"data": trends, "cached_at": datetime.now().isoformat()},
                expires_in_sec=7200
            )
            return trends

        except Exception as e:
            logger.error(f"Error getting trend sparklines: {e}")
            return {}

    def _generate_executive_narrative(self, kpis: Dict[str, Any], period: str) -> str:
        """Generate narrative from KPIs - uses AI when enabled, falls back to templates"""
        try:
            settings = frappe.get_single("Insights Settings")
            if settings.enable_ai_analytics:
                ai_narrative = self._generate_ai_narrative(kpis, period)
                if ai_narrative:
                    return ai_narrative
        except Exception as e:
            logger.warning(f"AI narrative generation failed, using fallback: {e}")

        try:
            return self._build_fallback_from_kpis(kpis, period)
        except Exception as e:
            logger.error(f"Error generating executive narrative: {e}")
            return "Unable to generate executive summary narrative."

    def _generate_ai_narrative(self, kpis: Dict[str, Any], period: str) -> Optional[str]:
        """Generate AI-powered executive narrative. Returns None on failure."""
        try:
            from insights.ai.provider_factory import AIProviderFactory
            client = AIProviderFactory.get_client()
            if not client.is_enabled() or not client.check_quota():
                return None

            # Build concise KPI context (no recursion - does not call get_executive_summary)
            context = self._build_narrative_from_kpis(kpis, period)
            if not context or context == "KPI data unavailable":
                return None

            prompt = (
                f"Write a concise 3-sentence executive summary for the {period} period. "
                f"Focus on the most critical business insights and any items needing attention. "
                f"KPI data: {context}"
            )
            result = client.chat(prompt, use_cache=True)

            if isinstance(result, dict) and result.get("response"):
                return result["response"]
            elif isinstance(result, str) and len(result) > 20:
                return result
            return None
        except Exception as e:
            logger.warning(f"AI narrative error: {e}")
            return None

    def _build_narrative_from_kpis(self, kpis: Dict[str, Any], period: str) -> str:
        """Build context string from already-computed KPIs"""
        parts = []
        fin = kpis.get("financial", {})
        if not fin.get("error"):
            rev = fin.get("revenue", {})
            if rev.get("value"):
                parts.append(f"Revenue: {rev['value']:,.0f} ({rev.get('variance_pct', 0):+.1f}% vs target)")
            margin = fin.get("net_margin", {})
            if margin.get("value"):
                parts.append(f"Net Margin: {margin['value']:.1f}%")
            cash = fin.get("cash_runway", {})
            if cash.get("value"):
                parts.append(f"Cash Runway: {cash['value']:.1f} weeks")

        sales = kpis.get("sales", {})
        if not sales.get("error"):
            growth = sales.get("growth_rate", {})
            if growth.get("value"):
                parts.append(f"Sales Growth: {growth['value']:.1f}%")

        cust = kpis.get("customer", {})
        if not cust.get("error"):
            churn = cust.get("churn_risk", {})
            if churn.get("value"):
                parts.append(f"Churn Risk: {churn['value']:.1f}%")

        return "; ".join(parts) if parts else "KPI data unavailable"

    def _build_fallback_from_kpis(self, kpis: Dict[str, Any], period: str) -> str:
        """Build data-driven narrative from already-computed KPIs"""
        parts = []
        fin = kpis.get("financial", {})
        if not fin.get("error"):
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

        sales = kpis.get("sales", {})
        if not sales.get("error"):
            growth = sales.get("growth_rate", {})
            if growth.get("value") is not None:
                parts.append(f"Sales growth is {growth['value']:.1f}%.")

        cust = kpis.get("customer", {})
        if not cust.get("error"):
            churn = cust.get("churn_risk", {})
            if churn.get("value") is not None:
                status = "elevated" if churn["value"] > 8 else "within target"
                parts.append(f"Customer churn risk at {churn['value']:.1f}% is {status}.")

        if parts:
            return " ".join(parts)
        return f"Business performance data for {period} is being compiled."

    def _calculate_business_health_score(self, kpis: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall business health score from departmental KPIs"""
        try:
            total_score = 0
            total_weight = 0
            department_scores = {}

            weights = {
                "financial": 0.25,
                "sales": 0.20,
                "customer": 0.15,
                "operations": 0.12,
                "risk": 0.08,
                "hr": 0.10,
                "manufacturing": 0.10
            }

            for department, weight in weights.items():
                if department in kpis and "error" not in kpis[department]:
                    dept_kpis = kpis[department]
                    rag_scores = []

                    for kpi_name, kpi_data in dept_kpis.items():
                        if isinstance(kpi_data, dict) and "rag_status" in kpi_data:
                            rag_status = kpi_data["rag_status"]
                            if rag_status == "green":
                                rag_scores.append(100)
                            elif rag_status == "amber":
                                rag_scores.append(70)
                            else:
                                rag_scores.append(30)

                    if rag_scores:
                        dept_score = np.mean(rag_scores)
                        department_scores[department] = round(float(dept_score), 1)
                        total_score += dept_score * weight
                        total_weight += weight

            overall_score = total_score / total_weight if total_weight > 0 else 50

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
                return self.financial_intel.predict()
            elif department == "sales":
                return self.sales_intel.predict()
            elif department == "customer":
                return self.customer_intel.predict()
            elif department == "operations":
                inv = self.inventory_intel.predict()
                proc = self.procurement_intel.predict()
                return {**inv, **proc}
            elif department == "risk":
                return self.risk_intel.predict()
            elif department == "hr":
                return self.hr_intel.get_hr_overview(period)
            elif department == "manufacturing":
                return self.manufacturing_intel.get_manufacturing_overview(period)
            else:
                return {"error": f"Unknown department: {department}"}

        except Exception as e:
            logger.error(f"Error getting {department} deep dive: {e}")
            return {"error": str(e)}


# API functions for Frappe
def get_executive_summary(period="YTD"):
    """API endpoint for executive summary"""
    try:
        executive = ExecutiveIntelligence()
        return executive.get_executive_summary(period)
    except Exception as e:
        frappe.log_error(f"Executive summary API error: {e}")
        return {"error": str(e)}


def get_department_deep_dive(department, period="YTD"):
    """API endpoint for department deep dive"""
    try:
        executive = ExecutiveIntelligence()
        return executive.get_department_deep_dive(department, period)
    except Exception as e:
        frappe.log_error(f"Department deep dive API error: {e}")
        return {"error": str(e)}


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

        periods = ["MTD", "QTD", "YTD", "TTM"]

        for period in periods:
            summary = executive.get_executive_summary(period)
            cache_key = f"executive_summary_{period}"
            cache.set_value(cache_key, summary, expires_in_sec=86400)
            logger.info(f"Updated executive summary for period: {period}")

        health_data = get_business_health_dashboard()
        cache.set_value("business_health_dashboard", health_data, expires_in_sec=86400)

        logger.info("Executive dashboard update completed successfully")

        overall_score = health_data.get("health_score", {}).get("overall_score", 50)
        if overall_score < 40:
            _send_critical_health_alert(overall_score, health_data.get("alerts", []))

    except Exception as e:
        logger.error(f"Error updating executive dashboard: {e}")
        frappe.log_error(f"Executive dashboard update error: {e}")


def _send_critical_health_alert(health_score, alerts):
    """Send alert when business health score is critically low"""
    try:
        alert_message = f"CRITICAL BUSINESS HEALTH ALERT - Score: {health_score}%\n"
        for alert in alerts[:3]:
            if alert.get("priority") == "critical":
                alert_message += f"- {alert.get('department')}: {alert.get('message')}\n"

        logger.warning(alert_message)

    except Exception as e:
        logger.error(f"Error sending critical health alert: {e}")
