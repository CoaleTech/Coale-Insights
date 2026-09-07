# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Avg, Count, DateFormat, Sum
from typing import Dict, Any, List, Optional
import json
from datetime import datetime, timedelta


class ERPNextV15Integrator:
    """Enhanced integration with ERPNext v15 for comprehensive business intelligence"""
    
    def __init__(self):
        self.supported_modules = {
            "accounts": {
                "doctypes": ["Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry", "GL Entry"],
                "features": ["financial_analysis", "cash_flow", "profit_loss", "balance_sheet"]
            },
            "selling": {
                "doctypes": ["Sales Order", "Sales Invoice", "Customer", "Quotation", "Delivery Note"],
                "features": ["sales_analytics", "customer_insights", "sales_forecasting"]
            },
            "buying": {
                "doctypes": ["Purchase Order", "Purchase Invoice", "Supplier", "Purchase Receipt"],
                "features": ["procurement_analytics", "supplier_performance", "cost_analysis"]
            },
            "stock": {
                "doctypes": ["Stock Entry", "Item", "Stock Ledger Entry", "Warehouse", "Item Group"],
                "features": ["inventory_optimization", "stock_analysis", "reorder_planning"]
            },
            "manufacturing": {
                "doctypes": ["Work Order", "BOM", "Item", "Production Plan", "Job Card"],
                "features": ["production_analytics", "efficiency_analysis", "resource_planning"]
            },
            "projects": {
                "doctypes": ["Project", "Task", "Timesheet", "Project Update"],
                "features": ["project_tracking", "resource_utilization", "timeline_analysis"]
            },
            "crm": {
                "doctypes": ["Lead", "Opportunity", "Customer", "Contact", "Communication"],
                "features": ["lead_scoring", "conversion_analysis", "customer_journey"]
            },
            "hr": {
                "doctypes": ["Employee", "Attendance", "Leave Application", "Salary Slip", "Employee Checkin"],
                "features": ["workforce_analytics", "performance_metrics", "attendance_patterns"]
            },
            "assets": {
                "doctypes": ["Asset", "Asset Movement", "Asset Maintenance", "Location"],
                "features": ["asset_utilization", "maintenance_scheduling", "depreciation_analysis"]
            },
            "support": {
                "doctypes": ["Issue", "Communication", "HD Ticket", "Service Level Agreement"],
                "features": ["support_metrics", "resolution_analysis", "customer_satisfaction"]
            }
        }
    
    def get_financial_insights(self, company: str = None, from_date: str = None, to_date: str = None) -> Dict[str, Any]:
        """Get comprehensive financial insights from Accounts module"""
        
        try:
            company = company or frappe.defaults.get_user_default("Company")
            from_date = from_date or frappe.utils.get_first_day_of_week(frappe.utils.today())
            to_date = to_date or frappe.utils.today()
            
            # Revenue Analysis
            revenue_data = self._get_revenue_analysis(company, from_date, to_date)
            
            # Cash Flow Analysis  
            cash_flow_data = self._get_cash_flow_analysis(company, from_date, to_date)
            
            # Profitability Analysis
            profitability_data = self._get_profitability_analysis(company, from_date, to_date)
            
            # Outstanding Analysis
            outstanding_data = self._get_outstanding_analysis(company)
            
            # Key Financial Ratios
            ratios_data = self._get_financial_ratios(company, from_date, to_date)
            
            return {
                "period": {"from": from_date, "to": to_date},
                "revenue_analysis": revenue_data,
                "cash_flow": cash_flow_data, 
                "profitability": profitability_data,
                "outstanding": outstanding_data,
                "financial_ratios": ratios_data,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            frappe.log_error(f"Financial insights failed: {str(e)}")
            raise
    
    def get_sales_insights(self, territory: str = None, sales_person: str = None, 
                          from_date: str = None, to_date: str = None) -> Dict[str, Any]:
        """Get comprehensive sales analytics and insights"""
        
        try:
            from_date = from_date or frappe.utils.add_months(frappe.utils.today(), -3)
            to_date = to_date or frappe.utils.today()
            
            # Sales Performance
            sales_performance = self._get_sales_performance(territory, sales_person, from_date, to_date)
            
            # Customer Analysis
            customer_analysis = self._get_customer_analysis(from_date, to_date)
            
            # Product Performance
            product_performance = self._get_product_performance(from_date, to_date)
            
            # Sales Pipeline
            pipeline_analysis = self._get_sales_pipeline_analysis()
            
            # Sales Forecasting
            forecast_data = self._get_sales_forecast(from_date, to_date)
            
            return {
                "period": {"from": from_date, "to": to_date},
                "sales_performance": sales_performance,
                "customer_analysis": customer_analysis,
                "product_performance": product_performance,
                "pipeline_analysis": pipeline_analysis,
                "forecast": forecast_data,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            frappe.log_error(f"Sales insights failed: {str(e)}")
            raise
    
    def get_inventory_insights(self, warehouse: str = None, item_group: str = None) -> Dict[str, Any]:
        """Get comprehensive inventory and stock insights"""
        
        try:
            # Current Stock Levels
            stock_levels = self._get_current_stock_levels(warehouse, item_group)
            
            # Stock Movement Analysis
            movement_analysis = self._get_stock_movement_analysis(warehouse, item_group)
            
            # Reorder Analysis
            reorder_analysis = self._get_reorder_analysis(warehouse)
            
            # ABC Analysis
            abc_analysis = self._get_abc_analysis(item_group)
            
            # Stock Aging
            aging_analysis = self._get_stock_aging_analysis(warehouse)
            
            # Inventory Turnover
            turnover_analysis = self._get_inventory_turnover_analysis(warehouse, item_group)
            
            return {
                "stock_levels": stock_levels,
                "movement_analysis": movement_analysis,
                "reorder_analysis": reorder_analysis,
                "abc_analysis": abc_analysis,
                "aging_analysis": aging_analysis,
                "turnover_analysis": turnover_analysis,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            frappe.log_error(f"Inventory insights failed: {str(e)}")
            raise
    
    def get_manufacturing_insights(self, from_date: str = None, to_date: str = None) -> Dict[str, Any]:
        """Get manufacturing and production insights"""
        
        try:
            from_date = from_date or frappe.utils.add_months(frappe.utils.today(), -1)
            to_date = to_date or frappe.utils.today()
            
            # Production Performance
            production_performance = self._get_production_performance(from_date, to_date)
            
            # Work Order Analysis
            work_order_analysis = self._get_work_order_analysis(from_date, to_date)
            
            # Resource Utilization
            resource_utilization = self._get_resource_utilization(from_date, to_date)
            
            # Quality Analysis
            quality_analysis = self._get_quality_analysis(from_date, to_date)
            
            # Efficiency Metrics
            efficiency_metrics = self._get_efficiency_metrics(from_date, to_date)
            
            return {
                "period": {"from": from_date, "to": to_date},
                "production_performance": production_performance,
                "work_order_analysis": work_order_analysis,
                "resource_utilization": resource_utilization,
                "quality_analysis": quality_analysis,
                "efficiency_metrics": efficiency_metrics,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            frappe.log_error(f"Manufacturing insights failed: {str(e)}")
            raise
    
    def get_hr_insights(self, department: str = None, from_date: str = None, to_date: str = None) -> Dict[str, Any]:
        """Get HR and workforce analytics"""
        
        try:
            from_date = from_date or frappe.utils.add_months(frappe.utils.today(), -3)
            to_date = to_date or frappe.utils.today()
            
            # Attendance Analysis
            attendance_analysis = self._get_attendance_analysis(department, from_date, to_date)
            
            # Performance Metrics
            performance_metrics = self._get_employee_performance_metrics(department, from_date, to_date)
            
            # Leave Analysis
            leave_analysis = self._get_leave_analysis(department, from_date, to_date)
            
            # Workforce Demographics
            demographics = self._get_workforce_demographics(department)
            
            # Payroll Analysis
            payroll_analysis = self._get_payroll_analysis(department, from_date, to_date)
            
            return {
                "period": {"from": from_date, "to": to_date},
                "attendance_analysis": attendance_analysis,
                "performance_metrics": performance_metrics,
                "leave_analysis": leave_analysis,
                "demographics": demographics,
                "payroll_analysis": payroll_analysis,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            frappe.log_error(f"HR insights failed: {str(e)}")
            raise
    
    def get_customer_insights(self, customer: str = None, customer_group: str = None) -> Dict[str, Any]:
        """Get comprehensive customer analytics and insights"""
        
        try:
            # Customer Behavior Analysis
            behavior_analysis = self._get_customer_behavior_analysis(customer, customer_group)
            
            # Purchase Patterns
            purchase_patterns = self._get_purchase_patterns(customer, customer_group)
            
            # Customer Lifetime Value
            clv_analysis = self._get_clv_analysis(customer, customer_group)
            
            # Segmentation Analysis
            segmentation = self._get_customer_segmentation(customer_group)
            
            # Churn Risk Analysis
            churn_analysis = self._get_churn_risk_analysis(customer_group)
            
            return {
                "behavior_analysis": behavior_analysis,
                "purchase_patterns": purchase_patterns,
                "clv_analysis": clv_analysis,
                "segmentation": segmentation,
                "churn_analysis": churn_analysis,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            frappe.log_error(f"Customer insights failed: {str(e)}")
            raise
    
    def get_project_insights(self, project: str = None, project_type: str = None) -> Dict[str, Any]:
        """Get project management and tracking insights"""
        
        try:
            # Project Performance
            project_performance = self._get_project_performance(project, project_type)
            
            # Resource Allocation
            resource_allocation = self._get_project_resource_allocation(project)
            
            # Timeline Analysis
            timeline_analysis = self._get_project_timeline_analysis(project, project_type)
            
            # Budget Analysis
            budget_analysis = self._get_project_budget_analysis(project)
            
            # Task Analysis
            task_analysis = self._get_project_task_analysis(project)
            
            return {
                "project_performance": project_performance,
                "resource_allocation": resource_allocation,
                "timeline_analysis": timeline_analysis,
                "budget_analysis": budget_analysis,
                "task_analysis": task_analysis,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            frappe.log_error(f"Project insights failed: {str(e)}")
            raise
    
    def get_comprehensive_dashboard_data(self, modules: List[str] = None) -> Dict[str, Any]:
        """Get comprehensive dashboard data across all modules"""
        
        try:
            modules = modules or list(self.supported_modules.keys())
            dashboard_data = {}
            
            for module in modules:
                if module in self.supported_modules:
                    try:
                        if module == "accounts":
                            dashboard_data[module] = self.get_financial_insights()
                        elif module == "selling":
                            dashboard_data[module] = self.get_sales_insights()
                        elif module == "stock":
                            dashboard_data[module] = self.get_inventory_insights()
                        elif module == "manufacturing":
                            dashboard_data[module] = self.get_manufacturing_insights()
                        elif module == "hr":
                            dashboard_data[module] = self.get_hr_insights()
                        elif module == "crm":
                            dashboard_data[module] = self.get_customer_insights()
                        elif module == "projects":
                            dashboard_data[module] = self.get_project_insights()
                    except Exception as e:
                        frappe.log_error(f"Failed to get {module} data: {str(e)}")
                        dashboard_data[module] = {"error": str(e)}

            return {
                "modules": dashboard_data,
                "summary": self._generate_cross_module_summary(dashboard_data),
                "generated_at": datetime.now().isoformat()
            }

        except Exception as e:
            frappe.log_error(f"Comprehensive dashboard failed: {str(e)}")
            raise

    def _get_revenue_analysis(self, company: str, from_date: str, to_date: str) -> Dict[str, Any]:
        """Get detailed revenue analysis"""

        SI = frappe.qb.DocType("Sales Invoice")

        # Current period revenue
        current_revenue = (
            frappe.qb.from_(SI)
            .select(
                Sum(SI.grand_total).as_("total_revenue"),
                Avg(SI.grand_total).as_("avg_invoice_value"),
                Count("*").as_("invoice_count"),
            )
            .where(
                (SI.company == company)
                & SI.posting_date.between(from_date, to_date)
                & (SI.docstatus == 1)
            )
            .run(as_dict=True)[0]
        )

        # Previous period comparison
        prev_from = frappe.utils.add_days(from_date, -30)
        prev_to = frappe.utils.add_days(to_date, -30)

        previous_revenue = (
            frappe.qb.from_(SI)
            .select(Sum(SI.grand_total).as_("total_revenue"))
            .where(
                (SI.company == company)
                & SI.posting_date.between(prev_from, prev_to)
                & (SI.docstatus == 1)
            )
            .run(as_dict=True)[0]
        )

        # Monthly trend
        month_expr = DateFormat(SI.posting_date, "%Y-%m").as_("month")
        monthly_trend = (
            frappe.qb.from_(SI)
            .select(month_expr, Sum(SI.grand_total).as_("revenue"))
            .where(
                (SI.company == company)
                & (SI.posting_date >= frappe.utils.add_months(from_date, -6))
                & (SI.docstatus == 1)
            )
            .groupby(month_expr)
            .orderby(month_expr)
            .run(as_dict=True)
        )

        return {
            "current_period": current_revenue,
            "previous_period": previous_revenue,
            "monthly_trend": monthly_trend,
            "growth_rate": self._calculate_growth_rate(
                current_revenue.get("total_revenue", 0),
                previous_revenue.get("total_revenue", 0)
            )
        }

    def _get_cash_flow_analysis(self, company: str, from_date: str, to_date: str) -> Dict[str, Any]:
        """Get cash flow analysis"""

        PE = frappe.qb.DocType("Payment Entry")

        # Incoming cash (payments received)
        incoming_cash = (
            frappe.qb.from_(PE)
            .select(
                Sum(PE.paid_amount).as_("total_received"),
                Count("*").as_("payment_count"),
            )
            .where(
                (PE.company == company)
                & PE.posting_date.between(from_date, to_date)
                & (PE.payment_type == "Receive")
                & (PE.docstatus == 1)
            )
            .run(as_dict=True)[0]
        )

        # Outgoing cash (payments made)
        outgoing_cash = (
            frappe.qb.from_(PE)
            .select(
                Sum(PE.paid_amount).as_("total_paid"),
                Count("*").as_("payment_count"),
            )
            .where(
                (PE.company == company)
                & PE.posting_date.between(from_date, to_date)
                & (PE.payment_type == "Pay")
                & (PE.docstatus == 1)
            )
            .run(as_dict=True)[0]
        )

        # Cash flow by week
        week_expr = DateFormat(PE.posting_date, "%u").as_("week_num")
        inflow_expr = Sum(Case().when(PE.payment_type == "Receive", PE.paid_amount).else_(0)).as_("inflow")
        outflow_expr = Sum(Case().when(PE.payment_type == "Pay", PE.paid_amount).else_(0)).as_("outflow")
        weekly_cash_flow = (
            frappe.qb.from_(PE)
            .select(week_expr, inflow_expr, outflow_expr)
            .where(
                (PE.company == company)
                & PE.posting_date.between(from_date, to_date)
                & (PE.docstatus == 1)
            )
            .groupby(week_expr)
            .orderby(week_expr)
            .run(as_dict=True)
        )

        return {
            "incoming": incoming_cash,
            "outgoing": outgoing_cash,
            "net_cash_flow": (incoming_cash.get("total_received", 0) - outgoing_cash.get("total_paid", 0)),
            "weekly_trend": weekly_cash_flow
        }

    def _get_profitability_analysis(self, company: str, from_date: str, to_date: str) -> Dict[str, Any]:
        """Get profitability analysis"""

        SI = frappe.qb.DocType("Sales Invoice")
        PI = frappe.qb.DocType("Purchase Invoice")

        # Gross profit calculation
        profit_data = (
            frappe.qb.from_(SI)
            .select(
                Sum(SI.grand_total).as_("total_revenue"),
                Sum(SI.total_taxes_and_charges).as_("total_taxes"),
                Sum(SI.net_total).as_("net_revenue"),
            )
            .where(
                (SI.company == company)
                & SI.posting_date.between(from_date, to_date)
                & (SI.docstatus == 1)
            )
            .run(as_dict=True)[0]
        )

        # Cost calculation (simplified)
        cost_data = (
            frappe.qb.from_(PI)
            .select(Sum(PI.grand_total).as_("total_costs"))
            .where(
                (PI.company == company)
                & PI.posting_date.between(from_date, to_date)
                & (PI.docstatus == 1)
            )
            .run(as_dict=True)[0]
        )

        total_revenue = profit_data.get("total_revenue", 0)
        total_costs = cost_data.get("total_costs", 0)
        gross_profit = total_revenue - total_costs

        return {
            "revenue": total_revenue,
            "costs": total_costs,
            "gross_profit": gross_profit,
            "profit_margin": (gross_profit / total_revenue * 100) if total_revenue > 0 else 0
        }
    
    def _calculate_growth_rate(self, current: float, previous: float) -> float:
        """Calculate growth rate percentage"""
        if previous == 0:
            return 100 if current > 0 else 0
        return ((current - previous) / previous) * 100
    
    def _generate_cross_module_summary(self, dashboard_data: Dict) -> Dict[str, Any]:
        """Generate summary across all modules"""
        
        summary = {
            "total_modules": len(dashboard_data),
            "successful_modules": len([m for m in dashboard_data.values() if "error" not in m]),
            "key_metrics": {},
            "alerts": []
        }
        
        # Extract key metrics from each module
        for module, data in dashboard_data.items():
            if "error" not in data:
                if module == "accounts" and "revenue_analysis" in data:
                    revenue = data["revenue_analysis"]["current_period"].get("total_revenue", 0)
                    summary["key_metrics"]["total_revenue"] = revenue
                
                # Add more cross-module metric extraction as needed
        
        return summary


# Global integrator instance
erpnext_integrator = ERPNextV15Integrator()


# Convenience functions for external use
def get_financial_insights(**kwargs) -> Dict[str, Any]:
    """Get financial insights from ERPNext"""
    return erpnext_integrator.get_financial_insights(**kwargs)


def get_sales_insights(**kwargs) -> Dict[str, Any]:
    """Get sales insights from ERPNext"""
    return erpnext_integrator.get_sales_insights(**kwargs)


def get_inventory_insights(**kwargs) -> Dict[str, Any]:
    """Get inventory insights from ERPNext"""
    return erpnext_integrator.get_inventory_insights(**kwargs)


def get_manufacturing_insights(**kwargs) -> Dict[str, Any]:
    """Get manufacturing insights from ERPNext"""
    return erpnext_integrator.get_manufacturing_insights(**kwargs)


def get_hr_insights(**kwargs) -> Dict[str, Any]:
    """Get HR insights from ERPNext"""
    return erpnext_integrator.get_hr_insights(**kwargs)


def get_comprehensive_dashboard(**kwargs) -> Dict[str, Any]:
    """Get comprehensive dashboard data"""
    return erpnext_integrator.get_comprehensive_dashboard_data(**kwargs)