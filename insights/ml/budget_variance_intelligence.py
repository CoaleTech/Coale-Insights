"""
Budget Variance Intelligence Module

This module provides comprehensive budget variance analysis capabilities including:
- Budget vs Actual analysis with detailed variance reporting
- Forecast accuracy tracking and improvement recommendations
- Department-wise budget performance analytics
- Automated variance alerts and notifications
- Budget planning optimization with predictive insights
- Cash flow variance analysis and trend identification

Author: AI Assistant
Version: 1.0.0
"""

import frappe
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
import numpy as np
import json
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class BudgetVarianceIntelligence:
    """
    Advanced budget variance analysis system providing:
    - Comprehensive budget vs actual tracking
    - Variance analysis across multiple dimensions 
    - Forecast accuracy measurement
    - Automated budget performance alerts
    - Predictive budget optimization
    """
    
    def __init__(self, company: str = None, fiscal_year: str = None, 
                 budget_period: str = "monthly"):
        """
        Initialize Budget Variance Intelligence
        
        Args:
            company: Company for budget analysis
            fiscal_year: Fiscal year for budget tracking
            budget_period: Budget period granularity (monthly/quarterly)
        """
        self.company = company or frappe.defaults.get_user_default("Company")
        self.fiscal_year = fiscal_year or frappe.defaults.get_user_default("fiscal_year")
        self.budget_period = budget_period
        self.base_currency = frappe.db.get_value("Company", self.company, "default_currency") or "KES"
        
        # Get fiscal year dates
        fy_doc = frappe.get_doc("Fiscal Year", self.fiscal_year)
        self.fy_start_date = fy_doc.year_start_date
        self.fy_end_date = fy_doc.year_end_date
        
        # Initialize cache
        self.cache_timeout = 3600  # 1 hour
        
    def get_budget_variance_overview(self) -> Dict[str, Any]:
        """
        Get comprehensive budget variance overview
        
        Returns:
            Dict containing complete budget variance analysis
        """
        try:
            logger.info("Generating budget variance overview")
            
            # Get budget vs actual analysis
            variance_summary = self._get_variance_summary()
            
            # Get departmental analysis
            dept_analysis = self._get_departmental_variance()
            
            # Get account-wise analysis
            account_analysis = self._get_account_variance()
            
            # Get forecast accuracy metrics
            forecast_accuracy = self._get_forecast_accuracy()
            
            # Get variance trends
            variance_trends = self._get_variance_trends()
            
            # Get budget alerts
            alerts = self._get_variance_alerts()
            
            # Get performance metrics
            performance_metrics = self._get_budget_performance_metrics()
            
            # Get improvement recommendations
            recommendations = self._get_variance_recommendations()
            
            return {
                "summary": variance_summary,
                "departmental_analysis": dept_analysis,
                "account_analysis": account_analysis,
                "forecast_accuracy": forecast_accuracy,
                "variance_trends": variance_trends,
                "alerts": alerts,
                "performance_metrics": performance_metrics,
                "recommendations": recommendations,
                "last_updated": frappe.utils.now(),
                "base_currency": self.base_currency,
                "period_info": {
                    "fiscal_year": self.fiscal_year,
                    "start_date": str(self.fy_start_date),
                    "end_date": str(self.fy_end_date),
                    "budget_period": self.budget_period
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating budget variance overview: {e}")
            frappe.log_error(f"Budget Variance Overview Error: {str(e)}", "Budget Variance Intelligence")
            return {}
    
    def _get_variance_summary(self) -> Dict[str, Any]:
        """Get high-level budget variance summary"""
        try:
            # Get budget data
            budget_data = self._fetch_budget_data()
            actual_data = self._fetch_actual_data()
            
            if not budget_data or not actual_data:
                return {}
            
            # Calculate overall variances
            total_budget = sum(item.get('budget_amount', 0) for item in budget_data)
            total_actual = sum(item.get('actual_amount', 0) for item in actual_data)
            
            total_variance = total_actual - total_budget
            variance_percentage = (total_variance / total_budget * 100) if total_budget != 0 else 0
            
            # Calculate variance categories
            favorable_variance = sum(
                max(0, item.get('actual_amount', 0) - item.get('budget_amount', 0))
                for item in self._merge_budget_actual(budget_data, actual_data)
                if item.get('account_type') == 'Income Account'
            ) + sum(
                max(0, item.get('budget_amount', 0) - item.get('actual_amount', 0))
                for item in self._merge_budget_actual(budget_data, actual_data)
                if item.get('account_type') == 'Expense Account'
            )
            
            adverse_variance = abs(total_variance) - favorable_variance
            
            # Get variance trend
            variance_trend = self._calculate_variance_trend()
            
            return {
                "total_budget": total_budget,
                "total_actual": total_actual,
                "total_variance": total_variance,
                "variance_percentage": variance_percentage,
                "favorable_variance": favorable_variance,
                "adverse_variance": adverse_variance,
                "variance_trend": variance_trend,
                "budget_utilization": (total_actual / total_budget * 100) if total_budget != 0 else 0,
                "status": self._get_variance_status(variance_percentage),
                "ytd_performance": self._get_ytd_performance()
            }
            
        except Exception as e:
            logger.error(f"Error calculating variance summary: {e}")
            return {}
    
    def _get_departmental_variance(self) -> List[Dict[str, Any]]:
        """Get department-wise budget variance analysis"""
        try:
            departments = self._get_active_departments()
            dept_variances = []
            
            for dept in departments:
                dept_budget = self._get_department_budget(dept.name)
                dept_actual = self._get_department_actual(dept.name)
                
                if dept_budget or dept_actual:
                    variance = dept_actual - dept_budget
                    variance_pct = (variance / dept_budget * 100) if dept_budget != 0 else 0
                    
                    dept_variances.append({
                        "department": dept.name,
                        "budget": dept_budget,
                        "actual": dept_actual,
                        "variance": variance,
                        "variance_percentage": variance_pct,
                        "status": self._get_variance_status(variance_pct),
                        "trend": self._get_department_trend(dept.name),
                        "key_accounts": self._get_department_key_accounts(dept.name)
                    })
            
            # Sort by absolute variance
            dept_variances.sort(key=lambda x: abs(x['variance']), reverse=True)
            return dept_variances
            
        except Exception as e:
            logger.error(f"Error calculating departmental variance: {e}")
            return []
    
    def _get_account_variance(self) -> List[Dict[str, Any]]:
        """Get account-wise budget variance analysis"""
        try:
            # Get all accounts with budget allocations
            budget_accounts = frappe.db.sql("""
                SELECT DISTINCT account
                FROM `tabBudget Account`
                WHERE parent IN (
                    SELECT name FROM `tabBudget`
                    WHERE company = %s 
                    AND fiscal_year = %s
                    AND docstatus = 1
                )
            """, (self.company, self.fiscal_year), as_dict=True)
            
            account_variances = []
            
            for acc in budget_accounts:
                account = acc.account
                
                # Get budget amount for account
                budget_amount = self._get_account_budget(account)
                
                # Get actual amount for account
                actual_amount = self._get_account_actual(account)
                
                if budget_amount != 0 or actual_amount != 0:
                    variance = actual_amount - budget_amount
                    variance_pct = (variance / budget_amount * 100) if budget_amount != 0 else 0
                    
                    account_info = frappe.get_doc("Account", account)
                    
                    account_variances.append({
                        "account": account,
                        "account_type": account_info.account_type,
                        "root_type": account_info.root_type,
                        "budget": budget_amount,
                        "actual": actual_amount,
                        "variance": variance,
                        "variance_percentage": variance_pct,
                        "status": self._get_variance_status(variance_pct),
                        "monthly_breakdown": self._get_account_monthly_breakdown(account),
                        "impact_level": self._get_variance_impact_level(abs(variance), budget_amount)
                    })
            
            # Sort by absolute variance
            account_variances.sort(key=lambda x: abs(x['variance']), reverse=True)
            return account_variances[:20]  # Top 20 accounts by variance
            
        except Exception as e:
            logger.error(f"Error calculating account variance: {e}")
            return []
    
    def _get_forecast_accuracy(self) -> Dict[str, Any]:
        """Calculate forecast accuracy metrics"""
        try:
            # Get historical forecast vs actual data
            forecast_data = self._get_historical_forecasts()
            
            if not forecast_data:
                return {}
            
            accuracies = []
            for item in forecast_data:
                forecast_amount = item.get('forecast_amount', 0)
                actual_amount = item.get('actual_amount', 0)
                
                if forecast_amount != 0:
                    accuracy = 100 - abs((actual_amount - forecast_amount) / forecast_amount * 100)
                    accuracies.append(max(0, accuracy))  # Ensure non-negative
            
            if not accuracies:
                return {}
            
            avg_accuracy = sum(accuracies) / len(accuracies)
            
            # Calculate accuracy by period
            monthly_accuracy = self._get_monthly_forecast_accuracy()
            
            # Get forecast improvement trends
            accuracy_trend = self._calculate_forecast_accuracy_trend()
            
            return {
                "overall_accuracy": avg_accuracy,
                "accuracy_grade": self._get_accuracy_grade(avg_accuracy),
                "monthly_accuracy": monthly_accuracy,
                "accuracy_trend": accuracy_trend,
                "forecast_bias": self._calculate_forecast_bias(forecast_data),
                "improvement_recommendations": self._get_forecast_improvement_tips(avg_accuracy)
            }
            
        except Exception as e:
            logger.error(f"Error calculating forecast accuracy: {e}")
            return {}
    
    def _get_variance_trends(self) -> Dict[str, Any]:
        """Get budget variance trends over time"""
        try:
            # Get monthly variance data
            monthly_variances = self._get_monthly_variances()
            
            # Calculate trend metrics
            trend_direction = self._calculate_trend_direction(monthly_variances)
            volatility = self._calculate_variance_volatility(monthly_variances)
            seasonality = self._detect_variance_seasonality(monthly_variances)
            
            # Get rolling averages
            rolling_avg_3m = self._get_rolling_average(monthly_variances, 3)
            rolling_avg_6m = self._get_rolling_average(monthly_variances, 6)
            
            return {
                "monthly_variances": monthly_variances,
                "trend_direction": trend_direction,
                "volatility": volatility,
                "seasonality": seasonality,
                "rolling_average_3m": rolling_avg_3m,
                "rolling_average_6m": rolling_avg_6m,
                "variance_prediction": self._predict_next_period_variance()
            }
            
        except Exception as e:
            logger.error(f"Error calculating variance trends: {e}")
            return {}
    
    def _get_variance_alerts(self) -> List[Dict[str, Any]]:
        """Generate automated variance alerts"""
        try:
            alerts = []
            
            # Check for significant variances
            variance_summary = self._get_variance_summary()
            if variance_summary:
                variance_pct = variance_summary.get('variance_percentage', 0)
                
                if abs(variance_pct) > 15:  # Alert for variances over 15%
                    alerts.append({
                        "type": "high_variance",
                        "severity": "high" if abs(variance_pct) > 25 else "medium",
                        "title": f"High Budget Variance: {variance_pct:.1f}%",
                        "description": f"Overall budget variance of {variance_pct:.1f}% exceeds acceptable threshold",
                        "action": "Review budget assumptions and actual spending patterns"
                    })
            
            # Check for department variances
            dept_variances = self._get_departmental_variance()
            for dept in dept_variances[:5]:  # Top 5 departments
                if abs(dept['variance_percentage']) > 20:
                    alerts.append({
                        "type": "department_variance",
                        "severity": "medium",
                        "title": f"Department Alert: {dept['department']}",
                        "description": f"{dept['department']} has {dept['variance_percentage']:.1f}% variance",
                        "action": f"Review {dept['department']} spending and budget allocation"
                    })
            
            # Check for forecast accuracy issues
            forecast_accuracy = self._get_forecast_accuracy()
            if forecast_accuracy and forecast_accuracy.get('overall_accuracy', 100) < 70:
                alerts.append({
                    "type": "forecast_accuracy",
                    "severity": "medium",
                    "title": "Low Forecast Accuracy",
                    "description": f"Forecast accuracy at {forecast_accuracy['overall_accuracy']:.1f}%",
                    "action": "Review forecasting methodology and assumptions"
                })
            
            # Check for cash flow issues
            cash_flow_variance = self._get_cash_flow_variance()
            if cash_flow_variance and abs(cash_flow_variance.get('variance_percentage', 0)) > 30:
                alerts.append({
                    "type": "cash_flow",
                    "severity": "high",
                    "title": "Cash Flow Variance Alert",
                    "description": f"Cash flow variance of {cash_flow_variance['variance_percentage']:.1f}%",
                    "action": "Review cash flow projections and working capital management"
                })
            
            return sorted(alerts, key=lambda x: {'high': 3, 'medium': 2, 'low': 1}[x['severity']], reverse=True)
            
        except Exception as e:
            logger.error(f"Error generating variance alerts: {e}")
            return []
    
    def _get_budget_performance_metrics(self) -> Dict[str, Any]:
        """Calculate comprehensive budget performance metrics"""
        try:
            # Budget accuracy metrics
            budget_accuracy = self._calculate_budget_accuracy()
            
            # Budget efficiency metrics  
            budget_efficiency = self._calculate_budget_efficiency()
            
            # Variance control metrics
            variance_control = self._calculate_variance_control()
            
            # Budget planning quality
            planning_quality = self._assess_budget_planning_quality()
            
            # Overall budget score
            overall_score = self._calculate_overall_budget_score(
                budget_accuracy, budget_efficiency, variance_control, planning_quality
            )
            
            return {
                "overall_score": overall_score,
                "budget_accuracy": budget_accuracy,
                "budget_efficiency": budget_efficiency,
                "variance_control": variance_control,
                "planning_quality": planning_quality,
                "benchmarks": self._get_industry_benchmarks(),
                "improvement_areas": self._identify_improvement_areas(overall_score)
            }
            
        except Exception as e:
            logger.error(f"Error calculating budget performance metrics: {e}")
            return {}
    
    def _get_variance_recommendations(self) -> List[Dict[str, Any]]:
        """Generate AI-powered variance improvement recommendations"""
        try:
            recommendations = []
            
            # Analyze variance patterns
            variance_summary = self._get_variance_summary()
            if not variance_summary:
                return recommendations
            
            variance_pct = variance_summary.get('variance_percentage', 0)
            
            # High-level recommendations based on overall variance
            if abs(variance_pct) > 20:
                recommendations.append({
                    "category": "budget_planning",
                    "priority": "high",
                    "title": "Improve Budget Planning Process",
                    "description": "Significant variance indicates issues with budget assumptions",
                    "actions": [
                        "Review historical data and trends more thoroughly",
                        "Implement rolling forecasts",
                        "Increase stakeholder involvement in budget planning",
                        "Consider zero-based budgeting approach"
                    ],
                    "impact": "High",
                    "effort": "Medium"
                })
            
            # Department-specific recommendations
            dept_variances = self._get_departmental_variance()
            for dept in dept_variances[:3]:  # Top 3 problematic departments
                if abs(dept['variance_percentage']) > 15:
                    recommendations.append({
                        "category": "department_control",
                        "priority": "medium",
                        "title": f"Enhance {dept['department']} Budget Control",
                        "description": f"{dept['department']} shows consistent variance patterns",
                        "actions": [
                            f"Implement monthly budget reviews for {dept['department']}",
                            "Provide budget management training",
                            "Set up automated spending alerts",
                            "Review budget allocation methodology"
                        ],
                        "impact": "Medium",
                        "effort": "Low"
                    })
            
            # Forecast accuracy recommendations
            forecast_accuracy = self._get_forecast_accuracy()
            if forecast_accuracy and forecast_accuracy.get('overall_accuracy', 100) < 80:
                recommendations.append({
                    "category": "forecasting",
                    "priority": "medium",
                    "title": "Enhance Forecasting Accuracy",
                    "description": "Forecast accuracy below optimal levels",
                    "actions": [
                        "Implement predictive analytics tools",
                        "Create scenario-based forecasting models",
                        "Increase forecast review frequency",
                        "Train team on advanced forecasting techniques"
                    ],
                    "impact": "Medium", 
                    "effort": "Medium"
                })
            
            # Process improvement recommendations
            if self._needs_process_improvement():
                recommendations.append({
                    "category": "process",
                    "priority": "low",
                    "title": "Automate Budget Monitoring",
                    "description": "Implement automated budget tracking and alerts",
                    "actions": [
                        "Set up automated variance reports",
                        "Create budget dashboard for real-time monitoring",
                        "Implement approval workflows for budget changes",
                        "Establish variance investigation procedures"
                    ],
                    "impact": "High",
                    "effort": "High"
                })
                
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating variance recommendations: {e}")
            return []
    
    # Helper methods for data fetching and calculations
    
    def _fetch_budget_data(self) -> List[Dict[str, Any]]:
        """Fetch budget data for the fiscal year"""
        try:
            return frappe.db.sql("""
                SELECT 
                    b.name as budget_name,
                    b.cost_center,
                    ba.account,
                    ba.budget_amount,
                    b.monthly_distribution
                FROM `tabBudget` b
                JOIN `tabBudget Account` ba ON ba.parent = b.name
                WHERE b.company = %s 
                AND b.fiscal_year = %s
                AND b.docstatus = 1
                ORDER BY ba.budget_amount DESC
            """, (self.company, self.fiscal_year), as_dict=True)
            
        except Exception as e:
            logger.error(f"Error fetching budget data: {e}")
            return []
    
    def _fetch_actual_data(self) -> List[Dict[str, Any]]:
        """Fetch actual expense data for comparison"""
        try:
            return frappe.db.sql("""
                SELECT 
                    gle.account,
                    gle.cost_center,
                    SUM(gle.debit - gle.credit) as actual_amount
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON acc.name = gle.account
                WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.account_type IN ('Expense Account', 'Income Account')
                GROUP BY gle.account, gle.cost_center
                HAVING SUM(gle.debit - gle.credit) != 0
                ORDER BY SUM(ABS(gle.debit - gle.credit)) DESC
            """, (self.company, self.fy_start_date, self.fy_end_date), as_dict=True)
            
        except Exception as e:
            logger.error(f"Error fetching actual data: {e}")
            return []
    
    def _merge_budget_actual(self, budget_data: List, actual_data: List) -> List[Dict[str, Any]]:
        """Merge budget and actual data for comparison"""
        try:
            merged_data = []
            
            # Create lookup for actual data
            actual_lookup = {}
            for item in actual_data:
                key = f"{item.get('account', '')}|{item.get('cost_center', '')}"
                actual_lookup[key] = item.get('actual_amount', 0)
            
            # Merge with budget data
            for budget_item in budget_data:
                key = f"{budget_item.get('account', '')}|{budget_item.get('cost_center', '')}"
                actual_amount = actual_lookup.get(key, 0)
                
                # Get account info
                account_info = frappe.get_cached_doc("Account", budget_item.get('account'))
                
                merged_data.append({
                    "account": budget_item.get('account'),
                    "cost_center": budget_item.get('cost_center'),
                    "budget_amount": budget_item.get('budget_amount', 0),
                    "actual_amount": actual_amount,
                    "variance": actual_amount - budget_item.get('budget_amount', 0),
                    "account_type": account_info.account_type,
                    "root_type": account_info.root_type
                })
            
            return merged_data
            
        except Exception as e:
            logger.error(f"Error merging budget and actual data: {e}")
            return []
    
    def _calculate_variance_trend(self) -> str:
        """Calculate overall variance trend direction"""
        try:
            # Get last 6 months of variance data
            monthly_variances = self._get_monthly_variances()
            
            if len(monthly_variances) < 3:
                return "insufficient_data"
            
            recent_variances = [item['variance_percentage'] for item in monthly_variances[-3:]]
            
            if len(recent_variances) >= 2:
                if recent_variances[-1] > recent_variances[0]:
                    return "improving" if recent_variances[-1] > 0 else "deteriorating"
                elif recent_variances[-1] < recent_variances[0]:
                    return "deteriorating" if recent_variances[-1] < 0 else "improving"
                else:
                    return "stable"
            
            return "stable"
            
        except Exception as e:
            logger.error(f"Error calculating variance trend: {e}")
            return "unknown"
    
    def _get_ytd_performance(self) -> Dict[str, Any]:
        """Get year-to-date budget performance"""
        try:
            current_date = frappe.utils.today()
            ytd_end = min(frappe.utils.getdate(current_date), self.fy_end_date)
            
            # Calculate YTD budget and actual
            ytd_budget = self._get_ytd_budget_amount(ytd_end)
            ytd_actual = self._get_ytd_actual_amount(ytd_end)
            
            ytd_variance = ytd_actual - ytd_budget
            ytd_variance_pct = (ytd_variance / ytd_budget * 100) if ytd_budget != 0 else 0
            
            # Calculate run rate
            days_elapsed = (ytd_end - self.fy_start_date).days
            days_total = (self.fy_end_date - self.fy_start_date).days
            expected_completion = (days_elapsed / days_total * 100) if days_total > 0 else 0
            
            actual_completion = (ytd_actual / ytd_budget * 100) if ytd_budget != 0 else 0
            
            return {
                "ytd_budget": ytd_budget,
                "ytd_actual": ytd_actual,
                "ytd_variance": ytd_variance,
                "ytd_variance_percentage": ytd_variance_pct,
                "expected_completion": expected_completion,
                "actual_completion": actual_completion,
                "run_rate_status": self._assess_run_rate(expected_completion, actual_completion)
            }
            
        except Exception as e:
            logger.error(f"Error calculating YTD performance: {e}")
            return {}
    
    def _get_variance_status(self, variance_percentage: float) -> str:
        """Determine variance status based on percentage"""
        abs_variance = abs(variance_percentage)
        
        if abs_variance <= 5:
            return "excellent"
        elif abs_variance <= 10:
            return "good"
        elif abs_variance <= 15:
            return "acceptable"
        elif abs_variance <= 25:
            return "poor"
        else:
            return "critical"
    
    def _get_active_departments(self) -> List:
        """Get list of active departments"""
        try:
            return frappe.get_all(
                "Department",
                filters={"disabled": 0},
                fields=["name", "department_name"]
            )
        except Exception as e:
            logger.error(f"Error fetching departments: {e}")
            return []
    
    def _get_department_budget(self, department: str) -> float:
        """Get total budget amount for a department"""
        try:
            # Get cost centers for department
            cost_centers = frappe.get_all(
                "Cost Center",
                filters={"department": department, "disabled": 0},
                fields=["name"]
            )
            
            if not cost_centers:
                return 0
            
            cost_center_names = [cc.name for cc in cost_centers]
            
            result = frappe.db.sql("""
                SELECT SUM(ba.budget_amount) as total_budget
                FROM `tabBudget` b
                JOIN `tabBudget Account` ba ON ba.parent = b.name
                WHERE b.company = %s 
                AND b.fiscal_year = %s
                AND b.cost_center IN ({}...)
                AND b.docstatus = 1
            """.format(','.join(['%s'] * len(cost_center_names))), 
            [self.company, self.fiscal_year] + cost_center_names)
            
            return result[0][0] if result and result[0][0] else 0
            
        except Exception as e:
            logger.error(f"Error getting department budget for {department}: {e}")
            return 0
    
    def _get_department_actual(self, department: str) -> float:
        """Get total actual amount for a department"""
        try:
            # Get cost centers for department
            cost_centers = frappe.get_all(
                "Cost Center",
                filters={"department": department, "disabled": 0},
                fields=["name"]
            )
            
            if not cost_centers:
                return 0
                
            cost_center_names = [cc.name for cc in cost_centers]
            
            result = frappe.db.sql("""
                SELECT SUM(gle.debit - gle.credit) as total_actual
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON acc.name = gle.account
                WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.cost_center IN ({}...)
                AND gle.is_cancelled = 0
                AND acc.account_type IN ('Expense Account', 'Income Account')
            """.format(','.join(['%s'] * len(cost_center_names))),
            [self.company, self.fy_start_date, self.fy_end_date] + cost_center_names)
            
            return result[0][0] if result and result[0][0] else 0
            
        except Exception as e:
            logger.error(f"Error getting department actual for {department}: {e}")
            return 0
    
    def _get_department_trend(self, department: str) -> str:
        """Get variance trend for a department"""
        try:
            # Get last 3 months data for trend analysis
            monthly_data = []
            current_date = frappe.utils.today()
            
            for i in range(3):
                month_end = frappe.utils.add_months(current_date, -i)
                month_start = frappe.utils.get_first_day(month_end)
                
                month_actual = self._get_department_actual_for_period(department, month_start, month_end)
                month_budget = self._get_department_budget_for_period(department, month_start, month_end)
                
                if month_budget != 0:
                    variance_pct = ((month_actual - month_budget) / month_budget) * 100
                    monthly_data.append(variance_pct)
            
            if len(monthly_data) >= 2:
                if monthly_data[0] < monthly_data[-1]:  # Getting better (more recent is better)
                    return "improving"
                elif monthly_data[0] > monthly_data[-1]:
                    return "deteriorating"
                else:
                    return "stable"
            
            return "insufficient_data"
            
        except Exception as e:
            logger.error(f"Error calculating department trend: {e}")
            return "unknown"
    
    def _get_department_key_accounts(self, department: str) -> List[Dict[str, Any]]:
        """Get key accounts contributing to department variance"""
        try:
            # Get cost centers for department
            cost_centers = frappe.get_all(
                "Cost Center",
                filters={"department": department, "disabled": 0},
                fields=["name"]
            )
            
            if not cost_centers:
                return []
            
            cost_center_names = [cc.name for cc in cost_centers]
            
            # Get account-wise data for department
            account_data = frappe.db.sql("""
                SELECT 
                    gle.account,
                    SUM(gle.debit - gle.credit) as actual_amount,
                    acc.account_type
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON acc.name = gle.account
                WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.cost_center IN ({}...)
                AND gle.is_cancelled = 0
                GROUP BY gle.account
                ORDER BY ABS(SUM(gle.debit - gle.credit)) DESC
                LIMIT 5
            """.format(','.join(['%s'] * len(cost_center_names))),
            [self.company, self.fy_start_date, self.fy_end_date] + cost_center_names, as_dict=True)
            
            return account_data
            
        except Exception as e:
            logger.error(f"Error getting department key accounts: {e}")
            return []
    
    def _get_account_budget(self, account: str) -> float:
        """Get budget amount for specific account"""
        try:
            result = frappe.db.sql("""
                SELECT SUM(ba.budget_amount) as total_budget
                FROM `tabBudget` b
                JOIN `tabBudget Account` ba ON ba.parent = b.name
                WHERE b.company = %s 
                AND b.fiscal_year = %s
                AND ba.account = %s
                AND b.docstatus = 1
            """, (self.company, self.fiscal_year, account))
            
            return result[0][0] if result and result[0][0] else 0
            
        except Exception as e:
            logger.error(f"Error getting account budget: {e}")
            return 0
    
    def _get_account_actual(self, account: str) -> float:
        """Get actual amount for specific account"""
        try:
            result = frappe.db.sql("""
                SELECT SUM(gle.debit - gle.credit) as total_actual
                FROM `tabGL Entry` gle
                WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.account = %s
                AND gle.is_cancelled = 0
            """, (self.company, self.fy_start_date, self.fy_end_date, account))
            
            return result[0][0] if result and result[0][0] else 0
            
        except Exception as e:
            logger.error(f"Error getting account actual: {e}")
            return 0
    
    def _get_account_monthly_breakdown(self, account: str) -> List[Dict[str, Any]]:
        """Get monthly breakdown for account"""
        try:
            monthly_data = []
            current_date = self.fy_start_date
            
            while current_date <= self.fy_end_date:
                month_start = current_date
                month_end = min(
                    frappe.utils.get_last_day(current_date),
                    self.fy_end_date
                )
                
                # Get actual for the month
                result = frappe.db.sql("""
                    SELECT SUM(gle.debit - gle.credit) as monthly_actual
                    FROM `tabGL Entry` gle
                    WHERE gle.company = %s
                    AND gle.posting_date BETWEEN %s AND %s
                    AND gle.account = %s
                    AND gle.is_cancelled = 0
                """, (self.company, month_start, month_end))
                
                monthly_actual = result[0][0] if result and result[0][0] else 0
                
                monthly_data.append({
                    "month": month_start.strftime("%Y-%m"),
                    "actual": monthly_actual
                })
                
                current_date = frappe.utils.add_months(current_date, 1)
            
            return monthly_data
            
        except Exception as e:
            logger.error(f"Error getting account monthly breakdown: {e}")
            return []
    
    def _get_variance_impact_level(self, variance_amount: float, budget_amount: float) -> str:
        """Determine impact level of variance"""
        if budget_amount == 0:
            return "low"
        
        variance_pct = (variance_amount / budget_amount) * 100
        
        if variance_pct < 5:
            return "low"
        elif variance_pct < 15:
            return "medium"
        elif variance_pct < 30:
            return "high"
        else:
            return "critical"
    
    def _get_historical_forecasts(self) -> List[Dict[str, Any]]:
        """Get historical forecast data for accuracy calculation"""
        try:
            # This would typically come from a custom doctype for forecasts
            # For now, returning empty list as example structure
            return []
            
        except Exception as e:
            logger.error(f"Error getting historical forecasts: {e}")
            return []
    
    def _get_monthly_forecast_accuracy(self) -> List[Dict[str, Any]]:
        """Get monthly forecast accuracy breakdown"""
        try:
            # Placeholder for monthly forecast accuracy calculation
            return []
            
        except Exception as e:
            logger.error(f"Error calculating monthly forecast accuracy: {e}")
            return []
    
    def _calculate_forecast_accuracy_trend(self) -> str:
        """Calculate forecast accuracy trend"""
        try:
            # Placeholder for forecast accuracy trend calculation
            return "stable"
            
        except Exception as e:
            logger.error(f"Error calculating forecast accuracy trend: {e}")
            return "unknown"
    
    def _calculate_forecast_bias(self, forecast_data: List) -> Dict[str, Any]:
        """Calculate forecast bias metrics"""
        try:
            if not forecast_data:
                return {}
            
            total_forecast = sum(item.get('forecast_amount', 0) for item in forecast_data)
            total_actual = sum(item.get('actual_amount', 0) for item in forecast_data)
            
            bias = total_actual - total_forecast
            bias_percentage = (bias / total_forecast * 100) if total_forecast != 0 else 0
            
            return {
                "bias_amount": bias,
                "bias_percentage": bias_percentage,
                "bias_direction": "over_forecast" if bias < 0 else "under_forecast"
            }
            
        except Exception as e:
            logger.error(f"Error calculating forecast bias: {e}")
            return {}
    
    def _get_accuracy_grade(self, accuracy: float) -> str:
        """Get accuracy grade based on percentage"""
        if accuracy >= 90:
            return "A+"
        elif accuracy >= 85:
            return "A"
        elif accuracy >= 80:
            return "B+"
        elif accuracy >= 75:
            return "B"
        elif accuracy >= 70:
            return "C+"
        elif accuracy >= 65:
            return "C"
        else:
            return "D"
    
    def _get_forecast_improvement_tips(self, accuracy: float) -> List[str]:
        """Get forecast improvement recommendations"""
        tips = []
        
        if accuracy < 70:
            tips.extend([
                "Review historical data patterns more thoroughly",
                "Implement scenario-based forecasting",
                "Increase forecast review frequency",
                "Consider external market factors"
            ])
        elif accuracy < 80:
            tips.extend([
                "Fine-tune forecasting models",
                "Incorporate leading indicators",
                "Improve data quality processes"
            ])
        elif accuracy < 90:
            tips.append("Consider advanced analytics and machine learning")
        
        return tips
    
    def _get_monthly_variances(self) -> List[Dict[str, Any]]:
        """Get monthly budget variances"""
        try:
            monthly_data = []
            current_date = self.fy_start_date
            
            while current_date <= min(frappe.utils.today(), self.fy_end_date):
                month_start = current_date
                month_end = min(
                    frappe.utils.get_last_day(current_date),
                    self.fy_end_date,
                    frappe.utils.today()
                )
                
                # Get monthly budget (proportional)
                monthly_budget = self._get_monthly_budget_amount(month_start, month_end)
                
                # Get monthly actual
                monthly_actual = self._get_monthly_actual_amount(month_start, month_end)
                
                variance = monthly_actual - monthly_budget
                variance_pct = (variance / monthly_budget * 100) if monthly_budget != 0 else 0
                
                monthly_data.append({
                    "month": month_start.strftime("%Y-%m"),
                    "budget": monthly_budget,
                    "actual": monthly_actual,
                    "variance": variance,
                    "variance_percentage": variance_pct
                })
                
                current_date = frappe.utils.add_months(current_date, 1)
            
            return monthly_data
            
        except Exception as e:
            logger.error(f"Error getting monthly variances: {e}")
            return []
    
    def _calculate_trend_direction(self, monthly_data: List) -> str:
        """Calculate overall trend direction from monthly data"""
        try:
            if len(monthly_data) < 3:
                return "insufficient_data"
            
            variances = [item['variance_percentage'] for item in monthly_data[-3:]]
            
            if len(variances) >= 2:
                avg_early = sum(variances[:len(variances)//2]) / (len(variances)//2)
                avg_late = sum(variances[len(variances)//2:]) / (len(variances) - len(variances)//2)
                
                if avg_late > avg_early:
                    return "deteriorating"
                elif avg_late < avg_early:
                    return "improving"
                else:
                    return "stable"
            
            return "stable"
            
        except Exception as e:
            logger.error(f"Error calculating trend direction: {e}")
            return "unknown"
    
    def _calculate_variance_volatility(self, monthly_data: List) -> float:
        """Calculate variance volatility (standard deviation)"""
        try:
            if len(monthly_data) < 2:
                return 0
            
            variances = [item['variance_percentage'] for item in monthly_data]
            mean_variance = sum(variances) / len(variances)
            
            variance = sum((x - mean_variance) ** 2 for x in variances) / len(variances)
            return variance ** 0.5
            
        except Exception as e:
            logger.error(f"Error calculating variance volatility: {e}")
            return 0
    
    def _detect_variance_seasonality(self, monthly_data: List) -> Dict[str, Any]:
        """Detect seasonal patterns in variance"""
        try:
            if len(monthly_data) < 12:
                return {"seasonal": False, "pattern": "insufficient_data"}
            
            # Group by month number (1-12)
            monthly_patterns = {}
            for item in monthly_data:
                month_num = int(item['month'].split('-')[1])
                if month_num not in monthly_patterns:
                    monthly_patterns[month_num] = []
                monthly_patterns[month_num].append(item['variance_percentage'])
            
            # Calculate average variance by month
            monthly_averages = {}
            for month, variances in monthly_patterns.items():
                monthly_averages[month] = sum(variances) / len(variances)
            
            # Check for significant seasonal variation
            if len(monthly_averages) >= 12:
                values = list(monthly_averages.values())
                avg_variance = sum(values) / len(values)
                variance_range = max(values) - min(values)
                
                is_seasonal = variance_range > (avg_variance * 0.5)  # 50% of average
                
                return {
                    "seasonal": is_seasonal,
                    "pattern": "significant" if is_seasonal else "minimal",
                    "peak_month": max(monthly_averages, key=monthly_averages.get),
                    "low_month": min(monthly_averages, key=monthly_averages.get),
                    "variance_range": variance_range
                }
            
            return {"seasonal": False, "pattern": "insufficient_data"}
            
        except Exception as e:
            logger.error(f"Error detecting seasonality: {e}")
            return {"seasonal": False, "pattern": "error"}
    
    def _get_rolling_average(self, monthly_data: List, period: int) -> List[Dict[str, Any]]:
        """Calculate rolling average for variance data"""
        try:
            if len(monthly_data) < period:
                return []
            
            rolling_data = []
            for i in range(period - 1, len(monthly_data)):
                window_data = monthly_data[i - period + 1:i + 1]
                avg_variance = sum(item['variance_percentage'] for item in window_data) / period
                
                rolling_data.append({
                    "month": monthly_data[i]['month'],
                    "rolling_average": avg_variance
                })
            
            return rolling_data
            
        except Exception as e:
            logger.error(f"Error calculating rolling average: {e}")
            return []
    
    def _predict_next_period_variance(self) -> Dict[str, Any]:
        """Predict next period variance using simple linear regression"""
        try:
            monthly_data = self._get_monthly_variances()
            
            if len(monthly_data) < 3:
                return {"prediction": None, "confidence": "low"}
            
            # Simple linear trend calculation
            variances = [item['variance_percentage'] for item in monthly_data[-6:]]  # Last 6 months
            
            if len(variances) < 2:
                return {"prediction": None, "confidence": "low"}
            
            # Calculate trend
            x_values = list(range(len(variances)))
            n = len(variances)
            
            sum_x = sum(x_values)
            sum_y = sum(variances)
            sum_xy = sum(x * y for x, y in zip(x_values, variances))
            sum_x2 = sum(x * x for x in x_values)
            
            # Linear regression slope
            if n * sum_x2 - sum_x * sum_x != 0:
                slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
                intercept = (sum_y - slope * sum_x) / n
                
                # Predict next period
                next_x = len(variances)
                predicted_variance = slope * next_x + intercept
                
                # Calculate confidence based on trend consistency
                recent_trend = variances[-1] - variances[0]
                predicted_trend = predicted_variance - variances[-1]
                
                confidence = "high" if abs(recent_trend - predicted_trend) < 5 else "medium"
                
                return {
                    "prediction": predicted_variance,
                    "confidence": confidence,
                    "trend": "improving" if slope < 0 else "deteriorating" if slope > 0 else "stable"
                }
            
            return {"prediction": variances[-1], "confidence": "low"}
            
        except Exception as e:
            logger.error(f"Error predicting variance: {e}")
            return {"prediction": None, "confidence": "low"}
    
    def _get_cash_flow_variance(self) -> Dict[str, Any]:
        """Get cash flow variance analysis"""
        try:
            # Get cash and bank accounts
            cash_accounts = frappe.get_all(
                "Account",
                filters={
                    "company": self.company,
                    "account_type": ["in", ["Cash", "Bank"]],
                    "disabled": 0
                },
                fields=["name"]
            )
            
            if not cash_accounts:
                return {}
            
            account_names = [acc.name for acc in cash_accounts]
            
            # Calculate cash flow for the period
            result = frappe.db.sql("""
                SELECT SUM(gle.debit - gle.credit) as net_cash_flow
                FROM `tabGL Entry` gle
                WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.account IN ({}...)
                AND gle.is_cancelled = 0
            """.format(','.join(['%s'] * len(account_names))),
            [self.company, self.fy_start_date, self.fy_end_date] + account_names)
            
            actual_cash_flow = result[0][0] if result and result[0][0] else 0
            
            # For this example, assume budgeted cash flow is 80% of revenue budget
            # In practice, this should come from a proper cash flow budget
            revenue_budget = self._get_revenue_budget()
            budgeted_cash_flow = revenue_budget * 0.8  # Simplified assumption
            
            variance = actual_cash_flow - budgeted_cash_flow
            variance_pct = (variance / budgeted_cash_flow * 100) if budgeted_cash_flow != 0 else 0
            
            return {
                "budgeted_cash_flow": budgeted_cash_flow,
                "actual_cash_flow": actual_cash_flow,
                "variance": variance,
                "variance_percentage": variance_pct,
                "status": self._get_variance_status(variance_pct)
            }
            
        except Exception as e:
            logger.error(f"Error calculating cash flow variance: {e}")
            return {}
    
    # Additional helper methods continue...
    
    def _calculate_budget_accuracy(self) -> Dict[str, Any]:
        """Calculate overall budget accuracy metrics"""
        try:
            variance_summary = self._get_variance_summary()
            if not variance_summary:
                return {}
            
            variance_pct = abs(variance_summary.get('variance_percentage', 0))
            accuracy = max(0, 100 - variance_pct)
            
            return {
                "accuracy_percentage": accuracy,
                "grade": self._get_accuracy_grade(accuracy),
                "benchmark": 85,  # Industry benchmark
                "performance": "above" if accuracy >= 85 else "below"
            }
            
        except Exception as e:
            logger.error(f"Error calculating budget accuracy: {e}")
            return {}
    
    def _calculate_budget_efficiency(self) -> Dict[str, Any]:
        """Calculate budget efficiency metrics"""
        try:
            # Budget efficiency = Actual performance / Budget allocation
            performance_metrics = self._get_performance_metrics()
            budget_metrics = self._get_budget_allocation_metrics()
            
            # Simplified efficiency calculation
            efficiency_score = 75  # Default score
            
            return {
                "efficiency_score": efficiency_score,
                "resource_utilization": self._calculate_resource_utilization(),
                "cost_effectiveness": self._calculate_cost_effectiveness()
            }
            
        except Exception as e:
            logger.error(f"Error calculating budget efficiency: {e}")
            return {}
    
    def _calculate_variance_control(self) -> Dict[str, Any]:
        """Calculate variance control effectiveness"""
        try:
            monthly_variances = self._get_monthly_variances()
            
            if not monthly_variances:
                return {}
            
            # Calculate control metrics
            avg_variance = sum(abs(item['variance_percentage']) for item in monthly_variances) / len(monthly_variances)
            variance_volatility = self._calculate_variance_volatility(monthly_variances)
            
            control_score = max(0, 100 - (avg_variance + variance_volatility) / 2)
            
            return {
                "control_score": control_score,
                "average_variance": avg_variance,
                "volatility": variance_volatility,
                "control_level": "excellent" if control_score >= 90 else "good" if control_score >= 75 else "needs_improvement"
            }
            
        except Exception as e:
            logger.error(f"Error calculating variance control: {e}")
            return {}
    
    def _assess_budget_planning_quality(self) -> Dict[str, Any]:
        """Assess overall budget planning quality"""
        try:
            # Assess various quality factors
            accuracy = self._calculate_budget_accuracy()
            completeness = self._assess_budget_completeness()
            timeliness = self._assess_budget_timeliness()
            stakeholder_involvement = self._assess_stakeholder_involvement()
            
            # Calculate overall quality score
            quality_factors = [
                accuracy.get('accuracy_percentage', 0) * 0.4,
                completeness.get('completeness_score', 0) * 0.3,
                timeliness.get('timeliness_score', 0) * 0.2,
                stakeholder_involvement.get('involvement_score', 0) * 0.1
            ]
            
            overall_quality = sum(quality_factors)
            
            return {
                "overall_quality": overall_quality,
                "accuracy": accuracy,
                "completeness": completeness,
                "timeliness": timeliness,
                "stakeholder_involvement": stakeholder_involvement,
                "grade": self._get_quality_grade(overall_quality)
            }
            
        except Exception as e:
            logger.error(f"Error assessing planning quality: {e}")
            return {}
    
    def _get_quality_grade(self, score: float) -> str:
        """Get quality grade based on score"""
        if score >= 90:
            return "Excellent"
        elif score >= 80:
            return "Good"
        elif score >= 70:
            return "Satisfactory"
        elif score >= 60:
            return "Needs Improvement"
        else:
            return "Poor"
    
    def _calculate_overall_budget_score(self, accuracy: Dict, efficiency: Dict, control: Dict, quality: Dict) -> float:
        """Calculate overall budget management score"""
        try:
            accuracy_score = accuracy.get('accuracy_percentage', 0) * 0.3
            efficiency_score = efficiency.get('efficiency_score', 0) * 0.25
            control_score = control.get('control_score', 0) * 0.25
            quality_score = quality.get('overall_quality', 0) * 0.2
            
            return accuracy_score + efficiency_score + control_score + quality_score
            
        except Exception as e:
            logger.error(f"Error calculating overall score: {e}")
            return 0
    
    # Additional utility methods
    
    def _get_revenue_budget(self) -> float:
        """Get total revenue budget"""
        try:
            result = frappe.db.sql("""
                SELECT SUM(ba.budget_amount) as revenue_budget
                FROM `tabBudget` b
                JOIN `tabBudget Account` ba ON ba.parent = b.name
                JOIN `tabAccount` acc ON acc.name = ba.account
                WHERE b.company = %s 
                AND b.fiscal_year = %s
                AND acc.root_type = 'Income'
                AND b.docstatus = 1
            """, (self.company, self.fiscal_year))
            
            return result[0][0] if result and result[0][0] else 0
            
        except Exception as e:
            logger.error(f"Error getting revenue budget: {e}")
            return 0
    
    def _needs_process_improvement(self) -> bool:
        """Determine if process improvement recommendations are needed"""
        try:
            variance_summary = self._get_variance_summary()
            
            if not variance_summary:
                return True
            
            # Check multiple criteria
            high_variance = abs(variance_summary.get('variance_percentage', 0)) > 20
            poor_trend = variance_summary.get('variance_trend') == 'deteriorating'
            
            return high_variance or poor_trend
            
        except Exception as e:
            logger.error(f"Error assessing process improvement needs: {e}")
            return True
    
    # Final utility and validation methods
    
    def _get_ytd_budget_amount(self, end_date) -> float:
        """Get year-to-date budget amount"""
        try:
            # Calculate proportional budget based on elapsed time
            days_elapsed = (end_date - self.fy_start_date).days
            days_total = (self.fy_end_date - self.fy_start_date).days
            
            if days_total == 0:
                return 0
            
            proportion = days_elapsed / days_total
            total_budget = sum(item.get('budget_amount', 0) for item in self._fetch_budget_data())
            
            return total_budget * proportion
            
        except Exception as e:
            logger.error(f"Error calculating YTD budget: {e}")
            return 0
    
    def _get_ytd_actual_amount(self, end_date) -> float:
        """Get year-to-date actual amount"""
        try:
            result = frappe.db.sql("""
                SELECT SUM(gle.debit - gle.credit) as ytd_actual
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON acc.name = gle.account
                WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.account_type IN ('Expense Account', 'Income Account')
            """, (self.company, self.fy_start_date, end_date))
            
            return result[0][0] if result and result[0][0] else 0
            
        except Exception as e:
            logger.error(f"Error calculating YTD actual: {e}")
            return 0
    
    def _assess_run_rate(self, expected: float, actual: float) -> str:
        """Assess budget run rate status"""
        variance = abs(actual - expected)
        
        if variance <= 5:
            return "on_track"
        elif variance <= 15:
            return "slight_deviation"
        elif variance <= 30:
            return "significant_deviation"
        else:
            return "major_deviation"
    
    def _get_department_actual_for_period(self, department: str, start_date, end_date) -> float:
        """Get department actual for specific period"""
        try:
            cost_centers = frappe.get_all(
                "Cost Center",
                filters={"department": department, "disabled": 0},
                fields=["name"]
            )
            
            if not cost_centers:
                return 0
                
            cost_center_names = [cc.name for cc in cost_centers]
            
            result = frappe.db.sql("""
                SELECT SUM(gle.debit - gle.credit) as period_actual
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON acc.name = gle.account
                WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.cost_center IN ({}...)
                AND gle.is_cancelled = 0
                AND acc.account_type IN ('Expense Account', 'Income Account')
            """.format(','.join(['%s'] * len(cost_center_names))),
            [self.company, start_date, end_date] + cost_center_names)
            
            return result[0][0] if result and result[0][0] else 0
            
        except Exception as e:
            logger.error(f"Error getting department actual for period: {e}")
            return 0
    
    def _get_department_budget_for_period(self, department: str, start_date, end_date) -> float:
        """Get department budget for specific period"""
        try:
            # Get total department budget and calculate proportional amount
            total_budget = self._get_department_budget(department)
            
            if total_budget == 0:
                return 0
            
            # Calculate proportion of fiscal year
            period_days = (end_date - start_date).days
            fy_days = (self.fy_end_date - self.fy_start_date).days
            
            if fy_days == 0:
                return 0
            
            proportion = period_days / fy_days
            return total_budget * proportion
            
        except Exception as e:
            logger.error(f"Error getting department budget for period: {e}")
            return 0
    
    def _get_monthly_budget_amount(self, start_date, end_date) -> float:
        """Get proportional budget amount for month"""
        try:
            total_budget = sum(item.get('budget_amount', 0) for item in self._fetch_budget_data())
            
            if total_budget == 0:
                return 0
                
            # Calculate proportion
            period_days = (end_date - start_date).days + 1
            fy_days = (self.fy_end_date - self.fy_start_date).days + 1
            
            proportion = period_days / fy_days
            return total_budget * proportion
            
        except Exception as e:
            logger.error(f"Error getting monthly budget: {e}")
            return 0
    
    def _get_monthly_actual_amount(self, start_date, end_date) -> float:
        """Get actual amount for month"""
        try:
            result = frappe.db.sql("""
                SELECT SUM(gle.debit - gle.credit) as monthly_actual
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON acc.name = gle.account
                WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.account_type IN ('Expense Account', 'Income Account')
            """, (self.company, start_date, end_date))
            
            return result[0][0] if result and result[0][0] else 0
            
        except Exception as e:
            logger.error(f"Error getting monthly actual: {e}")
            return 0
    
    def _get_performance_metrics(self) -> Dict[str, Any]:
        """Get general performance metrics"""
        try:
            # Placeholder for performance metrics
            return {
                "revenue_growth": 0,
                "cost_efficiency": 0,
                "profit_margin": 0
            }
            
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {}
    
    def _get_budget_allocation_metrics(self) -> Dict[str, Any]:
        """Get budget allocation metrics"""
        try:
            # Placeholder for allocation metrics
            return {
                "allocation_efficiency": 0,
                "resource_distribution": {}
            }
            
        except Exception as e:
            logger.error(f"Error getting allocation metrics: {e}")
            return {}
    
    def _calculate_resource_utilization(self) -> float:
        """Calculate resource utilization efficiency"""
        try:
            # Simplified calculation
            return 80  # Default utilization score
            
        except Exception as e:
            logger.error(f"Error calculating resource utilization: {e}")
            return 0
    
    def _calculate_cost_effectiveness(self) -> float:
        """Calculate cost effectiveness"""
        try:
            # Simplified calculation
            return 75  # Default cost effectiveness score
            
        except Exception as e:
            logger.error(f"Error calculating cost effectiveness: {e}")
            return 0
    
    def _assess_budget_completeness(self) -> Dict[str, Any]:
        """Assess budget completeness"""
        try:
            # Check if all major accounts have budgets
            total_accounts = frappe.db.count("Account", {
                "company": self.company,
                "disabled": 0,
                "account_type": ["in", ["Income Account", "Expense Account"]]
            })
            
            budgeted_accounts = frappe.db.sql("""
                SELECT COUNT(DISTINCT ba.account) 
                FROM `tabBudget Account` ba
                JOIN `tabBudget` b ON b.name = ba.parent
                WHERE b.company = %s 
                AND b.fiscal_year = %s
                AND b.docstatus = 1
            """, (self.company, self.fiscal_year))
            
            budgeted_count = budgeted_accounts[0][0] if budgeted_accounts else 0
            completeness = (budgeted_count / total_accounts * 100) if total_accounts > 0 else 0
            
            return {
                "completeness_score": completeness,
                "total_accounts": total_accounts,
                "budgeted_accounts": budgeted_count
            }
            
        except Exception as e:
            logger.error(f"Error assessing budget completeness: {e}")
            return {"completeness_score": 0}
    
    def _assess_budget_timeliness(self) -> Dict[str, Any]:
        """Assess budget preparation timeliness"""
        try:
            # Check when budgets were created relative to fiscal year start
            budget_creation_dates = frappe.db.sql("""
                SELECT creation
                FROM `tabBudget`
                WHERE company = %s 
                AND fiscal_year = %s
                AND docstatus = 1
                ORDER BY creation
                LIMIT 1
            """, (self.company, self.fiscal_year))
            
            if budget_creation_dates:
                creation_date = budget_creation_dates[0][0]
                days_before_fy = (self.fy_start_date - creation_date.date()).days
                
                if days_before_fy >= 30:
                    timeliness_score = 100
                elif days_before_fy >= 0:
                    timeliness_score = 80
                else:
                    timeliness_score = max(0, 60 + days_before_fy)  # Penalty for late budgets
            else:
                timeliness_score = 0
            
            return {
                "timeliness_score": timeliness_score,
                "assessment": "excellent" if timeliness_score >= 90 else "good" if timeliness_score >= 70 else "needs_improvement"
            }
            
        except Exception as e:
            logger.error(f"Error assessing budget timeliness: {e}")
            return {"timeliness_score": 50}
    
    def _assess_stakeholder_involvement(self) -> Dict[str, Any]:
        """Assess stakeholder involvement in budgeting"""
        try:
            # Check number of people involved in budget creation/approval
            budget_count = frappe.db.count("Budget", {
                "company": self.company,
                "fiscal_year": self.fiscal_year,
                "docstatus": 1
            })
            
            # Simplified assessment
            involvement_score = min(100, budget_count * 10)  # More budgets = more involvement
            
            return {
                "involvement_score": involvement_score,
                "budget_documents": budget_count
            }
            
        except Exception as e:
            logger.error(f"Error assessing stakeholder involvement: {e}")
            return {"involvement_score": 50}
    
    def _get_industry_benchmarks(self) -> Dict[str, Any]:
        """Get industry budget management benchmarks"""
        return {
            "budget_accuracy": 85,
            "variance_threshold": 10,
            "forecast_accuracy": 80,
            "budget_cycle_time": 45,  # days
            "stakeholder_satisfaction": 75
        }
    
    def _identify_improvement_areas(self, overall_score: float) -> List[str]:
        """Identify key areas for budget management improvement"""
        improvement_areas = []
        
        if overall_score < 70:
            improvement_areas.extend([
                "Overall budget management process needs significant enhancement",
                "Implement comprehensive budget training program",
                "Review and redesign budget planning methodology"
            ])
        elif overall_score < 80:
            improvement_areas.extend([
                "Budget accuracy needs improvement",
                "Enhance variance monitoring and control",
                "Implement more frequent budget reviews"
            ])
        elif overall_score < 90:
            improvement_areas.append("Fine-tune budget forecasting models")
        
        return improvement_areas
    
    # Export and reporting methods
    
    def export_variance_report(self, format="json") -> Dict[str, Any]:
        """Export comprehensive variance report"""
        try:
            report_data = self.get_budget_variance_overview()
            
            if format == "json":
                return report_data
            elif format == "summary":
                return self._create_executive_summary(report_data)
            else:
                return report_data
                
        except Exception as e:
            logger.error(f"Error exporting variance report: {e}")
            return {}
    
    def _create_executive_summary(self, data: Dict) -> Dict[str, Any]:
        """Create executive summary of variance analysis"""
        try:
            summary = data.get('summary', {})
            alerts = data.get('alerts', [])
            
            return {
                "executive_summary": {
                    "overall_variance": f"{summary.get('variance_percentage', 0):.1f}%",
                    "budget_status": summary.get('status', 'unknown'),
                    "key_alerts": len([a for a in alerts if a.get('severity') == 'high']),
                    "top_recommendations": [r['title'] for r in data.get('recommendations', [])[:3]],
                    "budget_utilization": f"{summary.get('budget_utilization', 0):.1f}%",
                    "forecast_accuracy": f"{data.get('forecast_accuracy', {}).get('overall_accuracy', 0):.1f}%"
                },
                "generated_at": frappe.utils.now(),
                "period": data.get('period_info', {})
            }
            
        except Exception as e:
            logger.error(f"Error creating executive summary: {e}")
            return {}