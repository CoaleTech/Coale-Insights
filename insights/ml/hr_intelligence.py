"""
HR Intelligence Module

Provides comprehensive HR analytics including headcount analysis, attrition prediction,
payroll optimization, and workforce planning with AI-powered insights.
"""

import frappe
from frappe import _
from frappe.utils import nowdate, add_months, add_days, flt, cint, date_diff
from frappe.defaults import get_user_default
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
import logging

from ..analytics.data_collectors import HRDataCollector

logger = logging.getLogger(__name__)


class HRIntelligence:
    """
    HR Intelligence provides comprehensive workforce analytics and insights
    including headcount optimization, attrition prediction, and compensation analysis.
    """
    
    def __init__(self):
        self.today = nowdate()
        self.current_month_start = datetime.now().replace(day=1).date()
        self.current_quarter_start = self._get_quarter_start()
        self.current_year_start = datetime.now().replace(month=1, day=1).date()
        # Payroll figures are money, so the frontend needs the company's currency
        # to label them. Without this the HR dashboard hardcoded "KES" in nine
        # places, which is wrong on any site whose company reports in anything
        # else. Same resolution order as the other seven intelligence modules,
        # but importing `get_user_default` directly: `frappe.defaults` is not
        # re-exported on the package, so attribute access on it does not resolve.
        company = get_user_default("Company") or frappe.db.get_single_value(
            "Global Defaults", "default_company"
        )
        self.company = str(company) if company else None
        self.base_currency = (
            (
                frappe.db.get_value("Company", self.company, "default_currency")
                if self.company
                else None
            )
            or frappe.db.get_single_value("System Settings", "default_currency")
            or "USD"
        )
        
    def _get_quarter_start(self) -> date:
        """Get the start date of current quarter"""
        current_month = datetime.now().month
        quarter_start_month = ((current_month - 1) // 3) * 3 + 1
        return datetime.now().replace(month=quarter_start_month, day=1).date()
    
    def get_hr_overview(self, period: str = "YTD") -> Dict[str, Any]:
        """
        Get comprehensive HR overview with key metrics
        
        Args:
            period: One of MTD, QTD, YTD, TTM
        """
        try:
            # Set date range based on period
            if period == "MTD":
                from_date = self.current_month_start
            elif period == "QTD":
                from_date = self.current_quarter_start
            elif period == "YTD":
                from_date = self.current_year_start
            else:  # TTM
                from_date = add_months(self.today, -12)
            
            to_date = self.today
            
            # Collect HR data
            collector = HRDataCollector({
                "from_date": from_date,
                "to_date": to_date
            })
            hr_data = collector.collect()
            
            # Generate insights
            insights = {
                "period": period,
                "generated_at": datetime.now().isoformat(),
                "company": self.company,
                "base_currency": self.base_currency,
                
                # Key metrics
                "headcount_metrics": self._analyze_headcount(hr_data.get("headcount", {})),
                "attrition_metrics": self._analyze_attrition(hr_data.get("attrition", {})),
                "payroll_metrics": self._analyze_payroll(hr_data.get("payroll", {})),
                "attendance_metrics": self._analyze_attendance(hr_data.get("attendance", {})),
                "leave_metrics": self._analyze_leave(hr_data.get("leave", {})),
                
                # Advanced analytics
                "workforce_composition": self._analyze_workforce_composition(hr_data),
                "department_health": self._analyze_department_health(hr_data),
                "compensation_analysis": self._analyze_compensation(hr_data),
                "engagement_indicators": self._analyze_engagement(hr_data),
                
                # Predictive insights
                "attrition_risk": self._predict_attrition_risk(hr_data),
                "hiring_forecast": self._forecast_hiring_needs(hr_data),
                
                # Recommendations
                "recommendations": self._generate_hr_recommendations(hr_data),
                
                # Raw data for further analysis
                "raw_data": hr_data
            }
            
            return insights
            
        except Exception as e:
            logger.error(f"Error generating HR overview: {e}")
            return {
                "error": str(e),
                "period": period,
                "generated_at": datetime.now().isoformat()
            }
    
    def _analyze_headcount(self, headcount_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze headcount metrics and trends"""
        try:
            total_active = headcount_data.get("total_active", 0)
            new_hires = headcount_data.get("new_hires", 0)
            exits = headcount_data.get("exits", 0)
            net_change = headcount_data.get("net_change", 0)
            
            # Calculate key metrics
            growth_rate = (net_change / total_active * 100) if total_active else 0
            turnover_rate = (exits / total_active * 100) if total_active else 0
            hire_rate = (new_hires / total_active * 100) if total_active else 0
            
            # Department analysis
            dept_breakdown = headcount_data.get("department_breakdown", [])
            largest_dept = max(dept_breakdown, key=lambda x: x["count"]) if dept_breakdown else {}
            smallest_dept = min(dept_breakdown, key=lambda x: x["count"]) if dept_breakdown else {}
            
            return {
                "total_employees": total_active,
                "new_hires": new_hires,
                "exits": exits,
                "net_growth": net_change,
                "growth_rate_pct": round(growth_rate, 2),
                "turnover_rate_pct": round(turnover_rate, 2),
                "hire_rate_pct": round(hire_rate, 2),
                "largest_department": largest_dept.get("department", "N/A"),
                "smallest_department": smallest_dept.get("department", "N/A"),
                "department_count": len(dept_breakdown),
                "headcount_health": "healthy" if growth_rate >= 0 and turnover_rate < 15 else "needs_attention"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing headcount: {e}")
            return {"error": str(e)}
    
    def _analyze_attrition(self, attrition_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze attrition patterns and risk factors"""
        try:
            attrition_rate = attrition_data.get("attrition_rate", 0)
            total_exits = attrition_data.get("total_exits", 0)
            voluntary_exits = attrition_data.get("voluntary_exits", 0)
            involuntary_exits = attrition_data.get("involuntary_exits", 0)
            
            voluntary_rate = (voluntary_exits / total_exits * 100) if total_exits else 0
            involuntary_rate = (involuntary_exits / total_exits * 100) if total_exits else 0
            
            # Risk assessment
            attrition_risk = "low"
            if attrition_rate > 20:
                attrition_risk = "high"
            elif attrition_rate > 12:
                attrition_risk = "medium"
            
            return {
                "attrition_rate_pct": round(attrition_rate, 2),
                "total_exits": total_exits,
                "voluntary_exits": voluntary_exits,
                "involuntary_exits": involuntary_exits,
                "voluntary_rate_pct": round(voluntary_rate, 2),
                "involuntary_rate_pct": round(involuntary_rate, 2),
                "attrition_risk_level": attrition_risk,
                "benchmark_comparison": "above_average" if attrition_rate > 15 else "below_average"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing attrition: {e}")
            return {"error": str(e)}
    
    def _analyze_payroll(self, payroll_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze payroll costs and trends"""
        try:
            total_gross_pay = payroll_data.get("total_gross_pay", 0)
            total_net_pay = payroll_data.get("total_net_pay", 0)
            average_gross_pay = payroll_data.get("average_gross_pay", 0)
            employees_paid = payroll_data.get("employees_paid", 0)
            
            # Calculate ratios
            cost_per_employee = total_gross_pay / employees_paid if employees_paid else 0
            deduction_rate = ((total_gross_pay - total_net_pay) / total_gross_pay * 100) if total_gross_pay else 0
            
            return {
                "total_payroll_cost": total_gross_pay,
                "average_salary": average_gross_pay,
                "cost_per_employee": cost_per_employee,
                "employees_on_payroll": employees_paid,
                "deduction_rate_pct": round(deduction_rate, 2),
                "payroll_efficiency": "optimal" if deduction_rate < 25 else "review_needed"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing payroll: {e}")
            return {"error": str(e)}
    
    def _analyze_attendance(self, attendance_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze attendance patterns and productivity indicators"""
        try:
            attendance_rate = attendance_data.get("attendance_rate", 0)
            late_arrivals = attendance_data.get("late_arrivals", 0)
            total_records = attendance_data.get("total_attendance_records", 0)
            
            late_arrival_rate = (late_arrivals / total_records * 100) if total_records else 0
            
            # Attendance health assessment
            attendance_health = "excellent"
            if attendance_rate < 85:
                attendance_health = "poor"
            elif attendance_rate < 92:
                attendance_health = "needs_improvement"
            elif attendance_rate < 96:
                attendance_health = "good"
            
            return {
                "attendance_rate_pct": round(attendance_rate, 2),
                "late_arrivals": late_arrivals,
                "late_arrival_rate_pct": round(late_arrival_rate, 2),
                "attendance_health": attendance_health,
                "productivity_indicator": "high" if attendance_rate > 95 else "medium" if attendance_rate > 90 else "low"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing attendance: {e}")
            return {"error": str(e)}
    
    def _analyze_leave(self, leave_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze leave patterns and utilization"""
        try:
            total_applications = leave_data.get("total_applications", 0)
            total_days = leave_data.get("total_leave_days", 0)
            avg_days = leave_data.get("avg_days_per_application", 0)
            
            return {
                "total_leave_applications": total_applications,
                "total_leave_days": total_days,
                "average_days_per_application": round(avg_days, 1),
                "leave_utilization": "normal" if avg_days < 5 else "high",
                "leave_pattern": "healthy" if total_applications > 0 else "low_utilization"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing leave: {e}")
            return {"error": str(e)}
    
    def _analyze_workforce_composition(self, hr_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze workforce composition and diversity"""
        try:
            headcount_data = hr_data.get("headcount", {})
            planning_data = hr_data.get("workforce_planning", {})
            
            dept_breakdown = headcount_data.get("department_breakdown", [])
            emp_type_breakdown = headcount_data.get("employment_type_breakdown", [])
            diversity = planning_data.get("workforce_diversity", {})
            
            # Calculate diversity ratios
            gender_dist = diversity.get("gender_distribution", [])
            total_employees = sum(item["count"] for item in gender_dist)
            
            gender_ratios = {}
            for item in gender_dist:
                gender_ratios[item["gender"]] = round(item["count"] / total_employees * 100, 1) if total_employees else 0
            
            return {
                "department_distribution": dept_breakdown,
                "employment_type_distribution": emp_type_breakdown,
                "gender_ratios": gender_ratios,
                "diversity_score": self._calculate_diversity_score(gender_dist),
                "composition_balance": "balanced" if len(dept_breakdown) > 3 else "concentrated"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing workforce composition: {e}")
            return {"error": str(e)}
    
    def _analyze_department_health(self, hr_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze department-level HR health metrics"""
        try:
            headcount_data = hr_data.get("headcount", {})
            payroll_data = hr_data.get("payroll", {})
            
            dept_breakdown = headcount_data.get("department_breakdown", [])
            dept_payroll = payroll_data.get("department_breakdown", [])
            
            # Combine headcount and payroll data by department
            dept_health = {}
            for dept_hc in dept_breakdown:
                dept_name = dept_hc["department"]
                dept_health[dept_name] = {
                    "headcount": dept_hc["count"],
                    "payroll_cost": 0,
                    "cost_per_employee": 0
                }
            
            for dept_pr in dept_payroll:
                dept_name = dept_pr["department"]
                if dept_name in dept_health:
                    dept_health[dept_name]["payroll_cost"] = dept_pr["total_cost"]
                    dept_health[dept_name]["cost_per_employee"] = dept_pr["avg_cost"]
            
            # Identify highest cost and largest departments
            if dept_health:
                highest_cost_dept = max(dept_health.items(), key=lambda x: x[1]["payroll_cost"])
                largest_dept = max(dept_health.items(), key=lambda x: x[1]["headcount"])
                
                return {
                    "department_metrics": dept_health,
                    "highest_cost_department": highest_cost_dept[0],
                    "largest_department": largest_dept[0],
                    "total_departments": len(dept_health)
                }
            else:
                return {"message": "No department data available"}
                
        except Exception as e:
            logger.error(f"Error analyzing department health: {e}")
            return {"error": str(e)}
    
    def _analyze_compensation(self, hr_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze compensation competitiveness and equity"""
        try:
            payroll_data = hr_data.get("payroll", {})
            dept_payroll = payroll_data.get("department_breakdown", [])
            
            if not dept_payroll:
                return {"message": "No payroll data available"}
            
            # Calculate compensation metrics
            all_avg_salaries = [dept["avg_cost"] for dept in dept_payroll]
            overall_median = np.median(all_avg_salaries) if all_avg_salaries else 0
            salary_variance = np.var(all_avg_salaries) if all_avg_salaries else 0
            
            # Identify high and low paying departments
            highest_paying = max(dept_payroll, key=lambda x: x["avg_cost"])
            lowest_paying = min(dept_payroll, key=lambda x: x["avg_cost"])
            
            pay_ratio = (highest_paying["avg_cost"] / lowest_paying["avg_cost"]) if lowest_paying["avg_cost"] else 0
            
            return {
                "median_salary": overall_median,
                "salary_variance": salary_variance,
                "highest_paying_dept": highest_paying["department"],
                "lowest_paying_dept": lowest_paying["department"],
                "pay_ratio": round(pay_ratio, 2),
                "pay_equity_status": "good" if pay_ratio < 3 else "needs_review"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing compensation: {e}")
            return {"error": str(e)}
    
    def _analyze_engagement(self, hr_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze employee engagement indicators"""
        try:
            attendance_data = hr_data.get("attendance", {})
            attrition_data = hr_data.get("attrition", {})
            leave_data = hr_data.get("leave", {})
            
            # Calculate engagement score based on available metrics
            attendance_rate = attendance_data.get("attendance_rate", 0)
            attrition_rate = attrition_data.get("attrition_rate", 0)
            leave_pattern = leave_data.get("avg_days_per_application", 0)
            
            # Simple engagement scoring (can be enhanced with survey data)
            engagement_score = 0
            
            # Attendance contribution (40%)
            if attendance_rate > 95:
                engagement_score += 40
            elif attendance_rate > 90:
                engagement_score += 30
            elif attendance_rate > 85:
                engagement_score += 20
            else:
                engagement_score += 10
            
            # Attrition contribution (40%) - inverse correlation
            if attrition_rate < 5:
                engagement_score += 40
            elif attrition_rate < 10:
                engagement_score += 30
            elif attrition_rate < 15:
                engagement_score += 20
            else:
                engagement_score += 10
            
            # Leave pattern contribution (20%)
            if leave_pattern < 3:
                engagement_score += 20
            elif leave_pattern < 5:
                engagement_score += 15
            else:
                engagement_score += 10
            
            engagement_level = "high"
            if engagement_score < 50:
                engagement_level = "low"
            elif engagement_score < 75:
                engagement_level = "medium"
            
            return {
                "engagement_score": engagement_score,
                "engagement_level": engagement_level,
                "key_indicators": {
                    "attendance_contribution": attendance_rate,
                    "retention_contribution": 100 - attrition_rate,
                    "leave_pattern_score": 100 - (leave_pattern * 10)
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing engagement: {e}")
            return {"error": str(e)}
    
    def _predict_attrition_risk(self, hr_data: Dict[str, Any]) -> Dict[str, Any]:
        """Predict attrition risk using simple heuristics"""
        try:
            attrition_data = hr_data.get("attrition", {})
            attendance_data = hr_data.get("attendance", {})
            
            current_attrition = attrition_data.get("attrition_rate", 0)
            attendance_rate = attendance_data.get("attendance_rate", 0)
            
            # Simple risk prediction
            risk_factors = []
            risk_score = 0
            
            if current_attrition > 15:
                risk_factors.append("High current attrition rate")
                risk_score += 30
            
            if attendance_rate < 90:
                risk_factors.append("Low attendance rate")
                risk_score += 20
            
            if current_attrition > 20:
                risk_factors.append("Critical attrition levels")
                risk_score += 25
            
            # Predict next period attrition
            predicted_attrition = current_attrition
            if risk_score > 50:
                predicted_attrition *= 1.2
            elif risk_score > 30:
                predicted_attrition *= 1.1
            
            risk_level = "low"
            if risk_score > 50:
                risk_level = "high"
            elif risk_score > 30:
                risk_level = "medium"
            
            return {
                "risk_level": risk_level,
                "risk_score": risk_score,
                "risk_factors": risk_factors,
                "predicted_attrition_rate": round(predicted_attrition, 2),
                "recommended_actions": self._get_attrition_recommendations(risk_level)
            }
            
        except Exception as e:
            logger.error(f"Error predicting attrition risk: {e}")
            return {"error": str(e)}
    
    def _forecast_hiring_needs(self, hr_data: Dict[str, Any]) -> Dict[str, Any]:
        """Forecast hiring needs based on growth and attrition trends"""
        try:
            headcount_data = hr_data.get("headcount", {})
            attrition_data = hr_data.get("attrition", {})
            
            current_headcount = headcount_data.get("total_active", 0)
            net_growth = headcount_data.get("net_change", 0)
            attrition_rate = attrition_data.get("attrition_rate", 0)
            
            # Forecast for next quarter
            quarterly_attrition = (attrition_rate / 4) / 100 * current_headcount
            projected_exits = int(quarterly_attrition)
            
            # Assume continued growth trajectory
            projected_growth_hires = max(0, int(net_growth))
            
            total_hiring_need = projected_exits + projected_growth_hires
            
            return {
                "projected_exits_next_quarter": projected_exits,
                "growth_based_hiring": projected_growth_hires,
                "total_hiring_need": total_hiring_need,
                "hiring_urgency": "high" if total_hiring_need > current_headcount * 0.1 else "normal"
            }
            
        except Exception as e:
            logger.error(f"Error forecasting hiring needs: {e}")
            return {"error": str(e)}
    
    def _generate_hr_recommendations(self, hr_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate actionable HR recommendations"""
        try:
            recommendations = []
            
            # Analyze each area and generate recommendations
            attrition_data = hr_data.get("attrition", {})
            attendance_data = hr_data.get("attendance", {})
            headcount_data = hr_data.get("headcount", {})
            
            if attrition_data.get("attrition_rate", 0) > 15:
                recommendations.append({
                    "priority": "high",
                    "category": "Retention",
                    "title": "Address High Attrition Rate",
                    "description": f"Current attrition rate of {attrition_data.get('attrition_rate', 0)}% is above industry average. Implement retention programs.",
                    "actions": ["Conduct exit interviews", "Review compensation", "Improve management training"]
                })
            
            if attendance_data.get("attendance_rate", 0) < 92:
                recommendations.append({
                    "priority": "medium",
                    "category": "Engagement",
                    "title": "Improve Attendance Rates",
                    "description": f"Attendance rate of {attendance_data.get('attendance_rate', 0)}% indicates engagement issues.",
                    "actions": ["Review attendance policy", "Address work-life balance", "Implement flexible working"]
                })
            
            if headcount_data.get("net_change", 0) < 0:
                recommendations.append({
                    "priority": "medium",
                    "category": "Growth",
                    "title": "Address Negative Headcount Growth",
                    "description": "Net headcount reduction may impact business growth.",
                    "actions": ["Accelerate hiring", "Improve retention", "Review workforce planning"]
                })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating HR recommendations: {e}")
            return [{"error": str(e)}]
    
    def _get_attrition_recommendations(self, risk_level: str) -> List[str]:
        """Get specific recommendations based on attrition risk level"""
        if risk_level == "high":
            return [
                "Implement immediate retention bonuses",
                "Conduct urgent employee satisfaction survey",
                "Review and improve management practices",
                "Accelerate career development programs"
            ]
        elif risk_level == "medium":
            return [
                "Enhance employee engagement initiatives",
                "Review compensation competitiveness",
                "Improve internal communication",
                "Strengthen performance management"
            ]
        else:
            return [
                "Maintain current retention strategies",
                "Continue monitoring engagement metrics",
                "Regular check-ins with high performers"
            ]
    
    def _calculate_diversity_score(self, gender_dist: List[Dict]) -> float:
        """Calculate a simple diversity score"""
        if not gender_dist or len(gender_dist) < 2:
            return 0
        
        total = sum(item["count"] for item in gender_dist)
        if total == 0:
            return 0
        
        # Shannon diversity index simplified
        proportions = [item["count"] / total for item in gender_dist]
        diversity = -sum(p * np.log2(p) for p in proportions if p > 0)
        
        # Normalize to 0-100 scale
        max_diversity = np.log2(len(gender_dist))
        return round((diversity / max_diversity * 100), 1) if max_diversity > 0 else 0


# API functions for Frappe
def get_hr_overview(period="YTD"):
    """API endpoint for HR overview"""
    try:
        hr_intel = HRIntelligence()
        return hr_intel.get_hr_overview(period)
    except Exception as e:
        frappe.log_error(f"HR overview API error: {e}")
        return {"error": str(e)}


def get_headcount_analytics(period="YTD"):
    """API endpoint for headcount analytics"""
    try:
        hr_intel = HRIntelligence()
        data = hr_intel.get_hr_overview(period)
        return data.get("headcount_metrics", {})
    except Exception as e:
        frappe.log_error(f"Headcount analytics API error: {e}")
        return {"error": str(e)}


def get_attrition_prediction():
    """API endpoint for attrition prediction"""
    try:
        hr_intel = HRIntelligence()
        data = hr_intel.get_hr_overview("TTM")  # Use trailing 12 months for prediction
        return data.get("attrition_risk", {})
    except Exception as e:
        frappe.log_error(f"Attrition prediction API error: {e}")
        return {"error": str(e)}


def get_hr_recommendations():
    """API endpoint for HR recommendations"""
    try:
        hr_intel = HRIntelligence()
        data = hr_intel.get_hr_overview("YTD")
        return data.get("recommendations", [])
    except Exception as e:
        frappe.log_error(f"HR recommendations API error: {e}")
        return {"error": str(e)}


def update_hr_intelligence():
    """
    Scheduler function to update HR intelligence daily
    """
    try:
        logger.info("Starting HR intelligence update...")
        
        hr_intel = HRIntelligence()
        
        # Generate fresh data for all periods
        periods = ["MTD", "QTD", "YTD", "TTM"]
        
        for period in periods:
            overview = hr_intel.get_hr_overview(period)
            
            # Cache the overview for 24 hours
            cache_key = f"hr_overview_{period}"
            frappe.cache().set_value(cache_key, overview, expires_in_sec=86400)
            
            logger.info(f"Updated HR intelligence for period: {period}")
        
        logger.info("HR intelligence update completed successfully")
        
    except Exception as e:
        logger.error(f"Error updating HR intelligence: {e}")
        frappe.log_error(f"HR intelligence update error: {e}")