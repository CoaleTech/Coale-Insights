"""
Executive Reports Module

Provides automated executive report generation and delivery system
with PDF export, email scheduling, and customizable report templates.
"""

import frappe
from frappe.utils import nowdate, now_datetime
from frappe.defaults import get_user_default
from weasyprint import HTML
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
import logging
from jinja2 import Template

logger = logging.getLogger(__name__)


class ExecutiveReports:
    """
    Executive Reports system for automated generation and delivery
    of C-suite level business intelligence reports.
    """
    
    def __init__(self):
        self.today = nowdate()
        self.current_month_start = datetime.now().replace(day=1).date()
        self.current_quarter_start = self._get_quarter_start()
        self.current_year_start = datetime.now().replace(month=1, day=1).date()
        company = get_user_default("Company") or frappe.db.get_single_value(
            "Global Defaults", "default_company"
        )
        self.currency = (
            frappe.db.get_value("Company", company, "default_currency")
            or frappe.db.get_single_value("System Settings", "default_currency")
            or "USD"
        )
        
    def _get_quarter_start(self) -> date:
        """Get the start date of current quarter"""
        current_month = datetime.now().month
        quarter_start_month = ((current_month - 1) // 3) * 3 + 1
        return datetime.now().replace(month=quarter_start_month, day=1).date()
    
    def generate_daily_executive_report(self) -> Dict[str, Any]:
        """Generate daily executive summary report"""
        try:
            logger.info("Generating daily executive report...")
            
            # Collect data from all intelligence modules
            report_data = self._collect_daily_intelligence_data()
            
            # Generate report content
            report_content = {
                "report_type": "Daily Executive Summary",
                "generated_at": now_datetime(),
                "report_date": self.today,
                "period_covered": "Yesterday & Today",
                
                # Executive summary
                "executive_summary": self._generate_daily_executive_summary(report_data),
                
                # Key metrics snapshot
                "key_metrics": self._extract_daily_key_metrics(report_data),
                
                # Alerts and exceptions
                "alerts": self._identify_daily_alerts(report_data),
                
                # Action items
                "action_items": self._generate_daily_action_items(report_data),
                
                # Performance highlights
                "performance_highlights": self._extract_performance_highlights(report_data),
                
                # Raw data for detailed analysis
                "detailed_data": report_data
            }
            
            # Generate PDF report
            pdf_path = self._generate_pdf_report(report_content, "daily")
            
            # Store report record
            report_record = self._save_report_record(report_content, pdf_path, "daily")
            
            logger.info(f"Daily executive report generated successfully: {report_record.name}")
            
            return {
                "success": True,
                "report_name": report_record.name,
                "report_path": pdf_path,
                "report_data": report_content
            }
            
        except Exception as e:
            logger.error(f"Error generating daily executive report: {e}")
            return {"success": False, "error": str(e)}
    
    def generate_weekly_executive_report(self) -> Dict[str, Any]:
        """Generate weekly executive summary report"""
        try:
            logger.info("Generating weekly executive report...")
            
            # Get week boundaries
            week_end = datetime.now().date()
            week_start = week_end - timedelta(days=7)
            
            # Collect weekly data
            report_data = self._collect_weekly_intelligence_data(week_start, week_end)
            
            # Generate report content
            report_content = {
                "report_type": "Weekly Executive Summary",
                "generated_at": now_datetime(),
                "report_date": week_end,
                "period_covered": f"{week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}",
                
                # Executive summary
                "executive_summary": self._generate_weekly_executive_summary(report_data),
                
                # Weekly performance analysis
                "weekly_performance": self._analyze_weekly_performance(report_data),
                
                # Trends and insights
                "trends_analysis": self._analyze_weekly_trends(report_data),
                
                # Strategic recommendations
                "strategic_recommendations": self._generate_weekly_recommendations(report_data),
                
                # Department highlights
                "department_highlights": self._extract_department_highlights(report_data),
                
                # Goals and targets review
                "goals_review": self._review_weekly_goals(report_data),
                
                # Detailed data
                "detailed_data": report_data
            }
            
            # Generate PDF report
            pdf_path = self._generate_pdf_report(report_content, "weekly")
            
            # Store report record
            report_record = self._save_report_record(report_content, pdf_path, "weekly")
            
            logger.info(f"Weekly executive report generated successfully: {report_record.name}")
            
            return {
                "success": True,
                "report_name": report_record.name,
                "report_path": pdf_path,
                "report_data": report_content
            }
            
        except Exception as e:
            logger.error(f"Error generating weekly executive report: {e}")
            return {"success": False, "error": str(e)}
    
    def generate_monthly_executive_report(self) -> Dict[str, Any]:
        """Generate monthly executive summary report"""
        try:
            logger.info("Generating monthly executive report...")
            
            # Get month boundaries
            month_end = datetime.now().date()
            month_start = month_end.replace(day=1)
            
            # Collect monthly data
            report_data = self._collect_monthly_intelligence_data(month_start, month_end)
            
            # Generate comprehensive report content
            report_content = {
                "report_type": "Monthly Executive Summary",
                "generated_at": now_datetime(),
                "report_date": month_end,
                "period_covered": f"{month_start.strftime('%B %Y')}",
                
                # Executive summary
                "executive_summary": self._generate_monthly_executive_summary(report_data),
                
                # Business health assessment
                "business_health": self._assess_monthly_business_health(report_data),
                
                # Financial performance
                "financial_performance": self._analyze_monthly_financial_performance(report_data),
                
                # Operational excellence
                "operational_excellence": self._analyze_monthly_operations(report_data),
                
                # Strategic initiatives progress
                "strategic_progress": self._review_strategic_initiatives(report_data),
                
                # Market position and competitive analysis
                "market_analysis": self._analyze_market_position(report_data),
                
                # Risk assessment
                "risk_assessment": self._assess_monthly_risks(report_data),
                
                # Forward-looking insights
                "forward_outlook": self._generate_forward_outlook(report_data),
                
                # Board-ready summary
                "board_summary": self._generate_board_summary(report_data),
                
                # Detailed data
                "detailed_data": report_data
            }
            
            # Generate PDF report  
            pdf_path = self._generate_pdf_report(report_content, "monthly")
            
            # Store report record
            report_record = self._save_report_record(report_content, pdf_path, "monthly")
            
            logger.info(f"Monthly executive report generated successfully: {report_record.name}")
            
            return {
                "success": True,
                "report_name": report_record.name,
                "report_path": pdf_path,
                "report_data": report_content
            }
            
        except Exception as e:
            logger.error(f"Error generating monthly executive report: {e}")
            return {"success": False, "error": str(e)}
    
    def _collect_daily_intelligence_data(self) -> Dict[str, Any]:
        """Collect daily intelligence data from all modules"""
        try:
            data = {}
            
            # Executive intelligence
            try:
                from insights.ml.executive_intelligence import ExecutiveIntelligence
                exec_intel = ExecutiveIntelligence()
                data["executive"] = exec_intel.get_executive_summary("MTD")
            except Exception as e:
                logger.warning(f"Could not load executive intelligence: {e}")
                data["executive"] = {}
            
            # Sales intelligence
            try:
                from insights.ml.sales_intelligence import SalesIntelligence
                sales_intel = SalesIntelligence()
                data["sales"] = sales_intel.predict()
            except Exception as e:
                logger.warning(f"Could not load sales intelligence: {e}")
                data["sales"] = {}
            
            # Financial intelligence
            try:
                from insights.ml.financial_intelligence import FinancialIntelligence
                fin_intel = FinancialIntelligence()
                data["financial"] = fin_intel.predict()
            except Exception as e:
                logger.warning(f"Could not load financial intelligence: {e}")
                data["financial"] = {}
            
            # HR intelligence
            try:
                from insights.ml.hr_intelligence import HRIntelligence
                hr_intel = HRIntelligence()
                data["hr"] = hr_intel.get_hr_overview("MTD")
            except Exception as e:
                logger.warning(f"Could not load HR intelligence: {e}")
                data["hr"] = {}
            
            # Manufacturing intelligence
            try:
                from insights.ml.manufacturing_intelligence import ManufacturingIntelligence
                mfg_intel = ManufacturingIntelligence()
                data["manufacturing"] = mfg_intel.get_manufacturing_overview("MTD")
            except Exception as e:
                logger.warning(f"Could not load manufacturing intelligence: {e}")
                data["manufacturing"] = {}
            
            # Marketing intelligence
            try:
                from insights.ml.marketing_intelligence import MarketingIntelligence
                mkt_intel = MarketingIntelligence()
                data["marketing"] = mkt_intel.get_marketing_overview("MTD")
            except Exception as e:
                logger.warning(f"Could not load marketing intelligence: {e}")
                data["marketing"] = {}
            
            return data
            
        except Exception as e:
            logger.error(f"Error collecting daily intelligence data: {e}")
            return {}
    
    def _collect_weekly_intelligence_data(self, week_start: date, week_end: date) -> Dict[str, Any]:
        """Collect weekly intelligence data"""
        # For weekly reports, use QTD data
        return self._collect_intelligence_data_for_period("QTD")
    
    def _collect_monthly_intelligence_data(self, month_start: date, month_end: date) -> Dict[str, Any]:
        """Collect monthly intelligence data"""
        # For monthly reports, use YTD data
        return self._collect_intelligence_data_for_period("YTD")
    
    def _collect_intelligence_data_for_period(self, period: str) -> Dict[str, Any]:
        """Helper method to collect intelligence data for a specific period"""
        try:
            data = {}
            
            # Executive intelligence
            try:
                from insights.ml.executive_intelligence import ExecutiveIntelligence
                exec_intel = ExecutiveIntelligence()
                data["executive"] = exec_intel.get_executive_summary(period)
            except:
                data["executive"] = {}
            
            # Sales intelligence
            try:
                from insights.ml.sales_intelligence import SalesIntelligence
                sales_intel = SalesIntelligence()
                data["sales"] = sales_intel.predict()
            except:
                data["sales"] = {}
            
            # Financial intelligence
            try:
                from insights.ml.financial_intelligence import FinancialIntelligence
                fin_intel = FinancialIntelligence()
                data["financial"] = fin_intel.predict()
            except:
                data["financial"] = {}
            
            # HR intelligence
            try:
                from insights.ml.hr_intelligence import HRIntelligence
                hr_intel = HRIntelligence()
                data["hr"] = hr_intel.get_hr_overview(period)
            except:
                data["hr"] = {}
            
            # Manufacturing intelligence
            try:
                from insights.ml.manufacturing_intelligence import ManufacturingIntelligence
                mfg_intel = ManufacturingIntelligence()
                data["manufacturing"] = mfg_intel.get_manufacturing_overview(period)
            except:
                data["manufacturing"] = {}
            
            # Marketing intelligence
            try:
                from insights.ml.marketing_intelligence import MarketingIntelligence
                mkt_intel = MarketingIntelligence()
                data["marketing"] = mkt_intel.get_marketing_overview(period)
            except:
                data["marketing"] = {}
            
            return data
            
        except Exception as e:
            logger.error(f"Error collecting intelligence data for period {period}: {e}")
            return {}
    
    def _generate_daily_executive_summary(self, report_data: Dict[str, Any]) -> str:
        """Generate executive summary for daily report"""
        try:
            summary_points = []
            
            # Business health score
            exec_data = report_data.get("executive", {})
            business_health = exec_data.get("business_health_score", {})
            if business_health:
                score = business_health.get("overall_score", 0)
                summary_points.append(f"Business health score: {score}/100")
            
            # Sales performance
            sales_data = report_data.get("sales", {})
            sales_metrics = sales_data.get("sales_metrics", {})
            if sales_metrics:
                revenue = sales_metrics.get("total_revenue", 0)
                summary_points.append(f"Daily revenue: {self.currency} {revenue:,.0f}")
            
            # Financial status
            fin_data = report_data.get("financial", {})
            if fin_data:
                cash_flow = fin_data.get("cash_flow", {})
                if cash_flow:
                    net_flow = cash_flow.get("net_burn_rate", 0)
                    summary_points.append(f"Net cash flow: {self.currency} {net_flow:,.0f}")
            
            # Manufacturing efficiency
            mfg_data = report_data.get("manufacturing", {})
            oee_data = mfg_data.get("oee_analysis", {})
            if oee_data:
                oee_score = oee_data.get("oee_score_pct", 0)
                summary_points.append(f"Manufacturing OEE: {oee_score}%")
            
            # Create summary
            if summary_points:
                summary = "Daily Business Snapshot: " + " | ".join(summary_points)
            else:
                summary = "Daily executive report generated with available business intelligence data."
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating daily executive summary: {e}")
            return "Daily executive summary generated."
    
    def _generate_weekly_executive_summary(self, report_data: Dict[str, Any]) -> str:
        """Generate executive summary for weekly report from real report_data figures."""
        try:
            summary_points = []

            exec_data = report_data.get("executive", {})
            business_health = exec_data.get("business_health_score", {})
            if business_health:
                score = business_health.get("overall_score", 0)
                summary_points.append(f"Business health score: {score}/100")

            sales_data = report_data.get("sales", {})
            sales_summary = sales_data.get("summary", {})
            if sales_summary:
                revenue = sales_summary.get("total_revenue", 0)
                summary_points.append(f"Period revenue: {self.currency} {revenue:,.0f}")

            fin_data = report_data.get("financial", {})
            if fin_data:
                cash_flow = fin_data.get("cash_flow", {})
                if cash_flow:
                    net_flow = cash_flow.get("net_burn_rate", 0)
                    summary_points.append(f"Net cash flow: {self.currency} {net_flow:,.0f}")

            mfg_data = report_data.get("manufacturing", {})
            oee_data = mfg_data.get("oee_analysis", {})
            if oee_data and "oee_score_pct" in oee_data:
                oee_score = oee_data.get("oee_score_pct", 0)
                summary_points.append(f"Manufacturing OEE: {oee_score}%")

            if summary_points:
                summary = "Weekly Business Snapshot: " + " | ".join(summary_points)
            else:
                summary = "Weekly executive report generated with available business intelligence data."

            return summary

        except Exception as e:
            logger.error(f"Error generating weekly executive summary: {e}")
            return "Weekly executive summary covering business performance, trends, and strategic insights."

    def _generate_monthly_executive_summary(self, report_data: Dict[str, Any]) -> str:
        """Generate executive summary for monthly report from real report_data figures."""
        try:
            summary_points = []

            exec_data = report_data.get("executive", {})
            business_health = exec_data.get("business_health_score", {})
            if business_health:
                score = business_health.get("overall_score", 0)
                summary_points.append(f"Business health score: {score}/100")

            sales_data = report_data.get("sales", {})
            sales_summary = sales_data.get("summary", {})
            if sales_summary:
                revenue = sales_summary.get("total_revenue", 0)
                summary_points.append(f"YTD revenue: {self.currency} {revenue:,.0f}")

            fin_data = report_data.get("financial", {})
            if fin_data:
                cash_flow = fin_data.get("cash_flow", {})
                if cash_flow:
                    net_flow = cash_flow.get("net_burn_rate", 0)
                    summary_points.append(f"Net cash flow: {self.currency} {net_flow:,.0f}")

            mfg_data = report_data.get("manufacturing", {})
            oee_data = mfg_data.get("oee_analysis", {})
            if oee_data and "oee_score_pct" in oee_data:
                oee_score = oee_data.get("oee_score_pct", 0)
                summary_points.append(f"Manufacturing OEE: {oee_score}%")

            if summary_points:
                summary = "Monthly Business Snapshot: " + " | ".join(summary_points)
            else:
                summary = "Monthly executive report generated with available business intelligence data."

            return summary

        except Exception as e:
            logger.error(f"Error generating monthly executive summary: {e}")
            return "Monthly executive summary providing comprehensive business performance analysis and strategic recommendations."
    
    def _extract_daily_key_metrics(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key daily metrics across all departments"""
        try:
            key_metrics = {
                "business_health_score": 0,
                "revenue": 0,
                "cash_flow": 0,
                "oee_score": 0,
                "lead_count": 0,
                "employee_count": 0,
                "critical_alerts": 0
            }
            
            # Extract metrics from each module
            exec_data = report_data.get("executive", {})
            if exec_data:
                health_score = exec_data.get("business_health_score", {})
                key_metrics["business_health_score"] = health_score.get("overall_score", 0)
            
            sales_data = report_data.get("sales", {})
            if sales_data:
                sales_metrics = sales_data.get("sales_metrics", {})
                key_metrics["revenue"] = sales_metrics.get("total_revenue", 0)
            
            fin_data = report_data.get("financial", {})
            if fin_data:
                cash_flow = fin_data.get("cash_flow", {})
                key_metrics["cash_flow"] = cash_flow.get("net_burn_rate", 0)
            
            mfg_data = report_data.get("manufacturing", {})
            if mfg_data:
                oee_data = mfg_data.get("oee_analysis", {})
                key_metrics["oee_score"] = oee_data.get("oee_score_pct", 0)
            
            mkt_data = report_data.get("marketing", {})
            if mkt_data:
                lead_metrics = mkt_data.get("lead_metrics", {})
                key_metrics["lead_count"] = lead_metrics.get("total_leads", 0)
            
            hr_data = report_data.get("hr", {})
            if hr_data:
                headcount = hr_data.get("headcount_metrics", {})
                key_metrics["employee_count"] = headcount.get("total_employees", 0)
            
            return key_metrics
            
        except Exception as e:
            logger.error(f"Error extracting daily key metrics: {e}")
            return {}
    
    def _identify_daily_alerts(self, report_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify alerts and exceptions that need attention"""
        try:
            alerts = []
            
            # Check business health score
            exec_data = report_data.get("executive", {})
            health_score = exec_data.get("business_health_score", {})
            if health_score:
                overall_score = health_score.get("overall_score", 0)
                if overall_score < 70:
                    alerts.append({
                        "priority": "high",
                        "type": "Business Health",
                        "message": f"Business health score has dropped to {overall_score}/100",
                        "action_required": "Review departmental performance metrics"
                    })
            
            # Check cash flow
            fin_data = report_data.get("financial", {})
            cash_flow = fin_data.get("cash_flow", {})
            if cash_flow:
                net_flow = cash_flow.get("net_burn_rate", 0)
                if net_flow < 0:
                    alerts.append({
                        "priority": "high",
                        "type": "Cash Flow",
                        "message": f"Negative cash flow: {self.currency} {net_flow:,.0f}",
                        "action_required": "Review receivables and payables"
                    })
            
            # Check manufacturing efficiency
            mfg_data = report_data.get("manufacturing", {})
            oee_data = mfg_data.get("oee_analysis", {})
            if oee_data:
                oee_score = oee_data.get("oee_score_pct", 0)
                if oee_score < 60:
                    alerts.append({
                        "priority": "medium",
                        "type": "Manufacturing",
                        "message": f"Low OEE score: {oee_score}%",
                        "action_required": "Review production efficiency"
                    })
            
            # Check sales performance
            sales_data = report_data.get("sales", {})
            sales_metrics = sales_data.get("sales_metrics", {})
            if sales_metrics:
                growth_rate = sales_metrics.get("revenue_growth_rate", 0)
                if growth_rate < -10:  # Decline > 10%
                    alerts.append({
                        "priority": "high",
                        "type": "Sales",
                        "message": f"Revenue declining: {growth_rate}%",
                        "action_required": "Investigate sales performance"
                    })
            
            return alerts
            
        except Exception as e:
            logger.error(f"Error identifying daily alerts: {e}")
            return []
    
    def _generate_daily_action_items(self, report_data: Dict[str, Any]) -> List[str]:
        """Generate action items based on daily performance"""
        try:
            action_items = []
            
            # Add action items based on performance analysis
            alerts = self._identify_daily_alerts(report_data)
            
            for alert in alerts:
                if alert.get("priority") == "high":
                    action_items.append(f"URGENT: {alert.get('action_required')}")
                else:
                    action_items.append(alert.get("action_required"))
            
            # Add routine action items
            if not action_items:
                action_items.append("Review daily performance metrics")
                action_items.append("Monitor key business indicators")
                action_items.append("Prepare for team check-ins")
            
            return action_items
            
        except Exception as e:
            logger.error(f"Error generating daily action items: {e}")
            return ["Review daily business performance"]
    
    def _extract_performance_highlights(self, report_data: Dict[str, Any]) -> List[str]:
        """Extract performance highlights from daily data"""
        try:
            highlights = []
            
            # Business health highlights
            exec_data = report_data.get("executive", {})
            health_score = exec_data.get("business_health_score", {})
            if health_score:
                score = health_score.get("overall_score", 0)
                if score >= 80:
                    highlights.append(f"Strong business health score: {score}/100")
            
            # Sales highlights
            sales_data = report_data.get("sales", {})
            if sales_data.get("sales_metrics", {}):
                highlights.append("Sales performance tracking on target")
            
            # Manufacturing highlights  
            mfg_data = report_data.get("manufacturing", {})
            oee_data = mfg_data.get("oee_analysis", {})
            if oee_data:
                oee_score = oee_data.get("oee_score_pct", 0)
                if oee_score >= 85:
                    highlights.append(f"Excellent manufacturing efficiency: {oee_score}% OEE")
            
            # Default highlight if none found
            if not highlights:
                highlights.append("Business operations running smoothly")
            
            return highlights
            
        except Exception as e:
            logger.error(f"Error extracting performance highlights: {e}")
            return ["Daily business operations completed"]
    
    def _analyze_weekly_performance(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze weekly performance trends from real report data."""
        try:
            sales = report_data.get("sales", {})
            sales_summary = sales.get("summary", {}) or sales.get("revenue_metrics", {})
            revenue = sales_summary.get("total_revenue", 0) or 0
            revenue_growth = sales_summary.get("revenue_growth_rate", 0) or 0

            fin = report_data.get("financial", {})
            fin_overview = fin.get("overview", {})
            net_margin = fin_overview.get("net_margin")
            ytd_profit = fin_overview.get("ytd_profit", 0) or 0

            mfg = report_data.get("manufacturing", {})
            oee = mfg.get("oee_analysis", {})
            oee_score = oee.get("oee_score_pct", 0) or 0
            prod = mfg.get("production_metrics", {})
            prod_growth = prod.get("monthly_growth_rate", 0) or 0

            def trend(value: float, good: float = 5, bad: float = -5) -> str:
                if value > good:
                    return "positive"
                if value < bad:
                    return "negative"
                return "stable"

            return {
                "revenue_trend": trend(revenue_growth, 10, -5),
                "efficiency_trend": trend(prod_growth, 5, -5) if prod else "no_data",
                "cost_trend": "stable" if net_margin is None else trend(net_margin, 15, 5),
                "overall_assessment": trend(revenue_growth, 10, -10),
                "revenue": revenue,
                "revenue_growth_rate": revenue_growth,
                "oee_score": oee_score,
                "net_margin": net_margin,
                "ytd_profit": ytd_profit,
            }
        except Exception as e:
            logger.error(f"Error analyzing weekly performance: {e}")
            return {"revenue_trend": "stable", "efficiency_trend": "no_data", "cost_trend": "stable", "overall_assessment": "stable"}

    def _analyze_weekly_trends(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze weekly business trends from real data."""
        try:
            key_trends = []
            opportunities = []
            risks = []

            sales = report_data.get("sales", {})
            sales_summary = sales.get("summary", {}) or sales.get("revenue_metrics", {})
            revenue = sales_summary.get("total_revenue", 0) or 0
            revenue_growth = sales_summary.get("revenue_growth_rate", 0) or 0
            if revenue:
                key_trends.append(f"Period revenue: {self.currency} {revenue:,.0f}")
            if revenue_growth:
                direction = "up" if revenue_growth > 0 else "down"
                key_trends.append(f"Revenue growth {direction} {revenue_growth:.1f}%")

            fin = report_data.get("financial", {})
            fin_overview = fin.get("overview", {})
            monthly_trend = fin_overview.get("monthly_trend", [])
            if len(monthly_trend) >= 2:
                latest = monthly_trend[-1]
                prior = monthly_trend[-2]
                latest_revenue = latest.get("revenue", 0) or 0
                prior_revenue = prior.get("revenue", 0) or 0
                if prior_revenue:
                    mom = ((latest_revenue - prior_revenue) / prior_revenue) * 100
                    key_trends.append(f"Month-over-month revenue {mom:+.1f}%")
                    if mom > 10:
                        opportunities.append("Revenue momentum accelerating")
                    elif mom < -10:
                        risks.append("Revenue declining month-over-month")

            cash_flow = fin.get("cash_flow", {})
            net_burn = cash_flow.get("net_burn_rate", 0) or 0
            if net_burn < 0:
                risks.append(f"Negative cash flow: {self.currency} {net_burn:,.0f}")
            elif net_burn > 0:
                opportunities.append("Positive net cash flow")

            mfg = report_data.get("manufacturing", {})
            oee = mfg.get("oee_analysis", {})
            oee_score = oee.get("oee_score_pct", 0) or 0
            if oee_score:
                key_trends.append(f"Manufacturing OEE: {oee_score}%")
                if oee_score < 60:
                    risks.append("Manufacturing OEE below target")
                elif oee_score >= 85:
                    opportunities.append("World-class manufacturing OEE")

            hr = report_data.get("hr", {})
            headcount = hr.get("headcount_metrics", {})
            total_employees = headcount.get("total_employees", 0) or 0
            turnover = headcount.get("turnover_rate_pct", 0) or 0
            if total_employees:
                key_trends.append(f"Headcount: {total_employees} employees")
            if turnover > 12:
                risks.append(f"Turnover rate elevated at {turnover:.1f}%")

            if not key_trends:
                key_trends.append("Insufficient historical data for trend analysis")

            return {
                "key_trends": key_trends,
                "emerging_opportunities": opportunities or ["No clear opportunities identified from available data"],
                "risk_factors": risks or ["No significant risks flagged from available data"],
            }
        except Exception as e:
            logger.error(f"Error analyzing weekly trends: {e}")
            return {"key_trends": [], "emerging_opportunities": [], "risk_factors": []}

    def _generate_weekly_recommendations(self, report_data: Dict[str, Any]) -> List[str]:
        """Generate weekly recommendations from real signals in report_data."""
        try:
            recommendations = []

            fin = report_data.get("financial", {})
            cash_flow = fin.get("cash_flow", {})
            net_burn = cash_flow.get("net_burn_rate", 0) or 0
            if net_burn < 0:
                recommendations.append(f"Review receivables and payables: negative cash flow {self.currency} {net_burn:,.0f}")

            mfg = report_data.get("manufacturing", {})
            oee = mfg.get("oee_analysis", {})
            oee_score = oee.get("oee_score_pct", 0) or 0
            if oee_score and oee_score < 60:
                recommendations.append(f"Review production efficiency: OEE at {oee_score}%")

            hr = report_data.get("hr", {})
            attrition = hr.get("attrition_metrics", {})
            attrition_rate = attrition.get("attrition_rate_pct", 0) or 0
            attrition_risk = attrition.get("attrition_risk", "low")
            if attrition_rate > 12 or attrition_risk in ("medium", "high"):
                recommendations.append(f"Review HR retention: attrition rate {attrition_rate:.1f}% (risk: {attrition_risk})")

            sales = report_data.get("sales", {})
            sales_summary = sales.get("summary", {}) or sales.get("revenue_metrics", {})
            revenue_growth = sales_summary.get("revenue_growth_rate", 0) or 0
            if revenue_growth < -10:
                recommendations.append("Investigate sales decline and pipeline coverage")

            if not recommendations:
                recommendations.append("Review weekly performance metrics and maintain current operational focus")

            return recommendations
        except Exception as e:
            logger.error(f"Error generating weekly recommendations: {e}")
            return ["Review weekly business performance"]

    def _extract_department_highlights(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract real highlights from each department, or mark data unavailable."""
        try:
            highlights = {}

            sales = report_data.get("sales", {})
            sales_summary = sales.get("summary", {}) or sales.get("revenue_metrics", {})
            revenue = sales_summary.get("total_revenue", 0)
            highlights["sales"] = f"Period revenue: {self.currency} {revenue:,.0f}" if revenue else "No sales data available"

            mfg = report_data.get("manufacturing", {})
            oee = mfg.get("oee_analysis", {})
            oee_score = oee.get("oee_score_pct", 0)
            if oee_score:
                highlights["manufacturing"] = f"OEE: {oee_score}% ({oee.get('oee_rating', 'N/A')})"
            else:
                highlights["manufacturing"] = "No manufacturing data available"

            hr = report_data.get("hr", {})
            headcount = hr.get("headcount_metrics", {})
            total_employees = headcount.get("total_employees", 0)
            if total_employees:
                highlights["hr"] = f"Headcount: {total_employees} (turnover {headcount.get('turnover_rate_pct', 0):.1f}%)"
            else:
                highlights["hr"] = "No HR data available"

            fin = report_data.get("financial", {})
            fin_overview = fin.get("overview", {})
            ytd_profit = fin_overview.get("ytd_profit", 0)
            net_margin = fin_overview.get("net_margin")
            if ytd_profit or net_margin is not None:
                margin_text = f", net margin {net_margin:.1f}%" if net_margin is not None else ""
                highlights["finance"] = f"YTD profit: {self.currency} {ytd_profit:,.0f}{margin_text}"
            else:
                highlights["finance"] = "No financial data available"

            mkt = report_data.get("marketing", {})
            lead_metrics = mkt.get("lead_metrics", {})
            total_leads = lead_metrics.get("total_leads", 0)
            if total_leads:
                highlights["marketing"] = f"Leads: {total_leads} (conversion {lead_metrics.get('conversion_rate', 0):.1f}%)"
            else:
                highlights["marketing"] = "No marketing data available"

            return highlights
        except Exception as e:
            logger.error(f"Error extracting department highlights: {e}")
            return {k: "No data available" for k in ["sales", "manufacturing", "hr", "finance", "marketing"]}

    def _review_weekly_goals(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Review progress against weekly goals. Goal tracking is not configured in this system, so report real metrics honestly."""
        try:
            exec_data = report_data.get("executive", {})
            health = exec_data.get("business_health_score", {})
            score = health.get("overall_score", 0)

            sales = report_data.get("sales", {})
            sales_summary = sales.get("summary", {}) or sales.get("revenue_metrics", {})
            revenue = sales_summary.get("total_revenue", 0) or 0

            fin = report_data.get("financial", {})
            fin_overview = fin.get("overview", {})
            ytd_revenue = fin_overview.get("ytd_revenue", 0) or 0

            return {
                "goals_on_track": None,
                "goals_behind": None,
                "goals_exceeded": None,
                "overall_progress": "Goal tracking not configured",
                "available_metrics": {
                    "business_health_score": score,
                    "period_revenue": revenue,
                    "ytd_revenue": ytd_revenue,
                },
                "note": "Goal tracking is not yet configured. Use available metrics above for manual review.",
            }
        except Exception as e:
            logger.error(f"Error reviewing weekly goals: {e}")
            return {"goals_on_track": None, "goals_behind": None, "goals_exceeded": None, "overall_progress": "Not configured", "note": "Goal tracking not available"}

    def _health_category(self, score: float) -> str:
        if score >= 75:
            return "strong"
        if score >= 50:
            return "moderate"
        return "needs_attention"

    def _assess_monthly_business_health(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess monthly business health from real report data."""
        try:
            exec_data = report_data.get("executive", {})
            health = exec_data.get("business_health_score", {})
            score = health.get("overall_score", 0) or 0

            fin = report_data.get("financial", {})
            fin_overview = fin.get("overview", {})
            net_margin = fin_overview.get("net_margin")
            ytd_profit = fin_overview.get("ytd_profit", 0) or 0

            mfg = report_data.get("manufacturing", {})
            oee = mfg.get("oee_analysis", {})
            oee_score = oee.get("oee_score_pct", 0) or 0

            financial_health = self._health_category(net_margin if net_margin is not None else score)
            operational_health = self._health_category(oee_score) if oee_score else "no_data"
            strategic_health = self._health_category(score)

            return {
                "overall_health": self._health_category(score),
                "financial_health": financial_health,
                "operational_health": operational_health,
                "strategic_health": strategic_health,
                "overall_score": score,
                "net_margin": net_margin,
                "oee_score": oee_score,
                "ytd_profit": ytd_profit,
            }
        except Exception as e:
            logger.error(f"Error assessing monthly business health: {e}")
            return {"overall_health": "unknown", "financial_health": "unknown", "operational_health": "unknown", "strategic_health": "unknown"}

    def _analyze_monthly_financial_performance(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze monthly financial performance from real data."""
        try:
            fin = report_data.get("financial", {})
            fin_overview = fin.get("overview", {})
            ytd_revenue = fin_overview.get("ytd_revenue", 0) or 0
            ytd_expenses = fin_overview.get("ytd_expenses", 0) or 0
            ytd_profit = fin_overview.get("ytd_profit", 0) or 0
            net_margin = fin_overview.get("net_margin")
            monthly_trend = fin_overview.get("monthly_trend", [])

            revenue_growth = 0
            if len(monthly_trend) >= 2:
                latest = monthly_trend[-1].get("revenue", 0) or 0
                prior = monthly_trend[-2].get("revenue", 0) or 0
                if prior:
                    revenue_growth = ((latest - prior) / prior) * 100

            cash_flow = fin.get("cash_flow", {})
            net_burn = cash_flow.get("net_burn_rate", 0) or 0

            def categorize(growth: float, margin: Optional[float]) -> str:
                if growth > 10:
                    return "positive"
                if growth < -10:
                    return "negative"
                return "stable"

            return {
                "revenue_growth": categorize(revenue_growth, net_margin),
                "profitability": "positive" if ytd_profit > 0 else "negative" if ytd_profit < 0 else "break_even",
                "cash_management": "concerning" if net_burn < 0 else "healthy",
                "cost_control": "on_target" if ytd_expenses <= ytd_revenue * 0.85 else "needs_attention",
                "ytd_revenue": ytd_revenue,
                "ytd_profit": ytd_profit,
                "net_margin": net_margin,
                "month_over_month_revenue_growth": round(revenue_growth, 2),
                "net_burn_rate": net_burn,
            }
        except Exception as e:
            logger.error(f"Error analyzing monthly financial performance: {e}")
            return {"revenue_growth": "stable", "profitability": "stable", "cash_management": "stable", "cost_control": "stable"}

    def _analyze_monthly_operations(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze monthly operational performance from real manufacturing data."""
        try:
            mfg = report_data.get("manufacturing", {})
            oee = mfg.get("oee_analysis", {})
            oee_score = oee.get("oee_score_pct", 0) or 0
            prod = mfg.get("production_metrics", {})
            completion_rate = prod.get("completion_rate_pct", 0) or 0
            prod_growth = prod.get("monthly_growth_rate", 0) or 0
            quality = mfg.get("quality_metrics", {})
            on_time = quality.get("on_time_completion_pct", 0) or 0

            def efficiency_cat(score: float, growth: float) -> str:
                if score >= 85 and growth >= 0:
                    return "improving"
                if score >= 60:
                    return "stable"
                return "needs_improvement"

            return {
                "efficiency_metrics": efficiency_cat(oee_score, prod_growth),
                "quality_metrics": "stable" if on_time >= 80 else "needs_improvement" if on_time else "no_data",
                "capacity_utilization": "optimal" if completion_rate >= 80 else "underutilized" if completion_rate else "no_data",
                "innovation_progress": "on_track" if prod_growth >= 0 else "declining",
                "oee_score": oee_score,
                "completion_rate_pct": completion_rate,
                "production_growth_rate": prod_growth,
                "on_time_completion_pct": on_time,
            }
        except Exception as e:
            logger.error(f"Error analyzing monthly operations: {e}")
            return {"efficiency_metrics": "no_data", "quality_metrics": "no_data", "capacity_utilization": "no_data", "innovation_progress": "no_data"}

    def _review_strategic_initiatives(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Review strategic initiatives progress. Initiative tracking is not configured; report honestly."""
        try:
            exec_data = report_data.get("executive", {})
            health = exec_data.get("business_health_score", {})
            score = health.get("overall_score", 0) or 0

            sales = report_data.get("sales", {})
            sales_summary = sales.get("summary", {}) or sales.get("revenue_metrics", {})
            revenue_growth = sales_summary.get("revenue_growth_rate", 0) or 0

            mfg = report_data.get("manufacturing", {})
            oee = mfg.get("oee_analysis", {})
            oee_score = oee.get("oee_score_pct", 0) or 0

            return {
                "initiatives_completed": None,
                "initiatives_in_progress": None,
                "initiatives_delayed": None,
                "overall_progress": "Strategic initiative tracking not configured",
                "available_indicators": {
                    "business_health_score": score,
                    "revenue_growth_rate": revenue_growth,
                    "oee_score": oee_score,
                },
                "note": "Strategic initiative tracking is not yet configured. Use the indicators above as proxies.",
            }
        except Exception as e:
            logger.error(f"Error reviewing strategic initiatives: {e}")
            return {"initiatives_completed": None, "initiatives_in_progress": None, "initiatives_delayed": None, "overall_progress": "Not configured", "note": "Strategic tracking not available"}

    def _analyze_market_position(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze market position. No external market/competitive data source exists; report internal concentration only."""
        try:
            sales = report_data.get("sales", {})
            dimensions = sales.get("dimensions", {})
            by_territory = dimensions.get("by_territory", [])
            by_segment = dimensions.get("by_customer_segment", [])

            def concentration(rows: List[Dict[str, Any]], key: str = "revenue") -> Dict[str, Any]:
                if not rows:
                    return {"top_share_pct": None, "top_item": None}
                total = sum(float(r.get(key, 0) or 0) for r in rows)
                if not total:
                    return {"top_share_pct": None, "top_item": None}
                top = max(rows, key=lambda r: float(r.get(key, 0) or 0))
                top_value = float(top.get(key, 0) or 0)
                return {
                    "top_share_pct": round((top_value / total) * 100, 1),
                    "top_item": top.get("territory") or top.get("segment") or top.get("customer_group") or "Unknown",
                }

            territory_concentration = concentration(by_territory, "revenue")
            segment_concentration = concentration(by_segment, "revenue")

            return {
                "market_share": "not_available",
                "competitive_position": "not_available",
                "market_trends": "not_available",
                "growth_opportunities": "identified" if territory_concentration.get("top_share_pct", 100) and territory_concentration["top_share_pct"] < 50 else "concentrated",
                "internal_concentration": {
                    "territory": territory_concentration,
                    "customer_segment": segment_concentration,
                },
                "note": "External market share and competitor data are not available. Internal concentration metrics are shown instead.",
            }
        except Exception as e:
            logger.error(f"Error analyzing market position: {e}")
            return {"market_share": "not_available", "competitive_position": "not_available", "market_trends": "not_available", "growth_opportunities": "unknown", "note": "Market data unavailable"}

    def _assess_monthly_risks(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess monthly risk factors from real signals in report_data."""
        try:
            fin = report_data.get("financial", {})
            cash_flow = fin.get("cash_flow", {})
            net_burn = cash_flow.get("net_burn_rate", 0) or 0
            fin_overview = fin.get("overview", {})
            ytd_profit = fin_overview.get("ytd_profit", 0) or 0

            mfg = report_data.get("manufacturing", {})
            oee = mfg.get("oee_analysis", {})
            oee_score = oee.get("oee_score_pct", 0) or 0
            prod = mfg.get("production_metrics", {})
            completion_rate = prod.get("completion_rate_pct", 0) or 0

            hr = report_data.get("hr", {})
            attrition = hr.get("attrition_metrics", {})
            attrition_rate = attrition.get("attrition_rate_pct", 0) or 0
            attrition_risk = attrition.get("attrition_risk", "low")

            sales = report_data.get("sales", {})
            sales_summary = sales.get("summary", {}) or sales.get("revenue_metrics", {})
            revenue_growth = sales_summary.get("revenue_growth_rate", 0) or 0

            def risk_level(value: float, high: float, medium: float) -> str:
                if value >= high or value < 0:
                    return "high" if value < 0 else "medium"
                if value >= medium:
                    return "medium"
                return "low"

            financial_risk = "high" if net_burn < 0 or ytd_profit < 0 else "low"
            operational_risk = "high" if (oee_score and oee_score < 60) or (completion_rate and completion_rate < 60) else "medium" if (oee_score and oee_score < 80) else "low"
            people_risk = "high" if attrition_rate > 20 or attrition_risk == "high" else "medium" if attrition_rate > 12 or attrition_risk == "medium" else "low"
            market_risk = "high" if revenue_growth < -10 else "medium" if revenue_growth < 0 else "low"

            return {
                "financial_risks": financial_risk,
                "operational_risks": operational_risk,
                "market_risks": market_risk,
                "strategic_risks": people_risk,
                "net_burn_rate": net_burn,
                "ytd_profit": ytd_profit,
                "attrition_rate_pct": attrition_rate,
                "revenue_growth_rate": revenue_growth,
            }
        except Exception as e:
            logger.error(f"Error assessing monthly risks: {e}")
            return {"financial_risks": "low", "operational_risks": "low", "market_risks": "low", "strategic_risks": "low"}

    def _generate_forward_outlook(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate forward-looking outlook from real trends."""
        try:
            sales = report_data.get("sales", {})
            sales_summary = sales.get("summary", {}) or sales.get("revenue_metrics", {})
            revenue_growth = sales_summary.get("revenue_growth_rate", 0) or 0

            mfg = report_data.get("manufacturing", {})
            prod = mfg.get("production_metrics", {})
            prod_growth = prod.get("monthly_growth_rate", 0) or 0

            fin = report_data.get("financial", {})
            cash_flow = fin.get("cash_flow", {})
            net_burn = cash_flow.get("net_burn_rate", 0) or 0

            if revenue_growth > 10 and prod_growth >= 0 and net_burn >= 0:
                outlook = "positive"
            elif revenue_growth < -10 or net_burn < 0:
                outlook = "caution"
            else:
                outlook = "stable"

            priorities = []
            if net_burn < 0:
                priorities.append("Improve cash flow: review receivables and payables")
            if revenue_growth < 0:
                priorities.append("Stabilize revenue: review pipeline and sales coverage")
            if prod_growth < 0:
                priorities.append("Improve production momentum")
            if not priorities:
                priorities.append("Maintain operational momentum")
                priorities.append("Monitor key risk indicators")

            return {
                "next_month_outlook": outlook,
                "quarterly_forecast": outlook,
                "key_priorities": priorities,
                "revenue_growth_rate": revenue_growth,
                "production_growth_rate": prod_growth,
                "net_burn_rate": net_burn,
            }
        except Exception as e:
            logger.error(f"Error generating forward outlook: {e}")
            return {"next_month_outlook": "stable", "quarterly_forecast": "stable", "key_priorities": ["Maintain business performance"]}

    def _generate_board_summary(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate board-ready summary from real achievements and challenges."""
        try:
            exec_data = report_data.get("executive", {})
            health = exec_data.get("business_health_score", {})
            score = health.get("overall_score", 0) or 0

            fin = report_data.get("financial", {})
            fin_overview = fin.get("overview", {})
            ytd_profit = fin_overview.get("ytd_profit", 0) or 0
            net_margin = fin_overview.get("net_margin")
            cash_flow = fin.get("cash_flow", {})
            net_burn = cash_flow.get("net_burn_rate", 0) or 0

            mfg = report_data.get("manufacturing", {})
            oee = mfg.get("oee_analysis", {})
            oee_score = oee.get("oee_score_pct", 0) or 0

            sales = report_data.get("sales", {})
            sales_summary = sales.get("summary", {}) or sales.get("revenue_metrics", {})
            revenue = sales_summary.get("total_revenue", 0) or 0
            revenue_growth = sales_summary.get("revenue_growth_rate", 0) or 0

            achievements = []
            challenges = []
            recommendations = []

            if score >= 75:
                achievements.append(f"Strong business health score: {score}/100")
            if ytd_profit > 0:
                achievements.append(f"YTD profit: {self.currency} {ytd_profit:,.0f}")
            if net_margin is not None and net_margin >= 15:
                achievements.append(f"Healthy net margin: {net_margin:.1f}%")
            if oee_score >= 85:
                achievements.append(f"World-class manufacturing OEE: {oee_score}%")
            if revenue > 0 and revenue_growth > 0:
                achievements.append(f"Revenue growth: {revenue_growth:.1f}%")
            if net_burn >= 0:
                achievements.append("Positive net cash flow")

            if score and score < 50:
                challenges.append(f"Business health score low: {score}/100")
            if net_burn < 0:
                challenges.append(f"Negative cash flow: {self.currency} {net_burn:,.0f}")
            if oee_score and oee_score < 60:
                challenges.append(f"Low OEE: {oee_score}%")
            if revenue_growth < -10:
                challenges.append(f"Revenue declining: {revenue_growth:.1f}%")

            if not achievements:
                achievements.append("Business operations continuing")
            if not challenges:
                challenges.append("No major challenges flagged from available data")

            if net_burn < 0:
                recommendations.append("Approve cash-flow improvement plan")
            if revenue_growth < -10:
                recommendations.append("Review sales strategy and pipeline coverage")
            if not recommendations:
                recommendations.append("Continue monitoring key performance indicators")
                recommendations.append("Review quarterly targets against actuals")

            executive_summary = f"Business health {score}/100"
            if revenue:
                executive_summary += f" | Revenue: {self.currency} {revenue:,.0f}"
            if ytd_profit:
                executive_summary += f" | YTD profit: {self.currency} {ytd_profit:,.0f}"
            if net_burn < 0:
                executive_summary += f" | Negative cash flow: {self.currency} {net_burn:,.0f}"

            return {
                "executive_summary": executive_summary,
                "key_achievements": achievements,
                "key_challenges": challenges,
                "board_recommendations": recommendations,
            }
        except Exception as e:
            logger.error(f"Error generating board summary: {e}")
            return {"executive_summary": "Monthly business performance review", "key_achievements": [], "key_challenges": [], "board_recommendations": ["Review monthly performance metrics"]}
    
    def _generate_pdf_report(self, report_content: Dict[str, Any], report_type: str) -> str:
        """Generate PDF report from content"""
        try:
            # Create HTML template
            html_template = self._get_report_template(report_type)
            
            # Render template with data
            template = Template(html_template)
            html_content = template.render(**report_content)
            
            # Generate PDF
            pdf_content = HTML(string=html_content).write_pdf()
            
            # Save PDF to file system
            report_name = f"executive_report_{report_type}_{report_content['report_date']}"
            pdf_path = f"/tmp/{report_name}.pdf"
            
            with open(pdf_path, "wb") as f:
                f.write(pdf_content)
            
            return pdf_path
            
        except Exception as e:
            logger.error(f"Error generating PDF report: {e}")
            return ""
    
    def _get_report_template(self, report_type: str) -> str:
        """Get HTML template for report type"""
        if report_type == "daily":
            return self._get_daily_report_template()
        elif report_type == "weekly":
            return self._get_weekly_report_template()
        else:  # monthly
            return self._get_monthly_report_template()
    
    def _get_daily_report_template(self) -> str:
        """Get daily report HTML template"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>{{ report_type }}</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .header { text-align: center; margin-bottom: 30px; border-bottom: 2px solid #333; padding-bottom: 20px; }
                .section { margin-bottom: 25px; }
                .section h2 { color: #2c3e50; border-left: 4px solid #3498db; padding-left: 10px; }
                .metric { display: inline-block; margin: 10px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
                .alert { background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 10px; margin: 5px 0; border-radius: 4px; }
                .highlight { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 10px; margin: 5px 0; border-radius: 4px; }
                .footer { margin-top: 40px; text-align: center; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{{ report_type }}</h1>
                <p>{{ period_covered }} | Generated: {{ generated_at.strftime('%B %d, %Y at %I:%M %p') }}</p>
            </div>
            
            <div class="section">
                <h2>Executive Summary</h2>
                <p>{{ executive_summary }}</p>
            </div>
            
            <div class="section">
                <h2>Key Metrics</h2>
                {% for metric, value in key_metrics.items() %}
                    <div class="metric">
                        <strong>{{ metric.replace('_', ' ').title() }}:</strong> {{ value }}
                    </div>
                {% endfor %}
            </div>
            
            {% if alerts %}
            <div class="section">
                <h2>Alerts & Exceptions</h2>
                {% for alert in alerts %}
                    <div class="alert">
                        <strong>{{ alert.type }} ({{ alert.priority.upper() }}):</strong> {{ alert.message }}
                        <br><em>Action Required:</em> {{ alert.action_required }}
                    </div>
                {% endfor %}
            </div>
            {% endif %}
            
            <div class="section">
                <h2>Action Items</h2>
                <ul>
                {% for item in action_items %}
                    <li>{{ item }}</li>
                {% endfor %}
                </ul>
            </div>
            
            <div class="section">
                <h2>Performance Highlights</h2>
                {% for highlight in performance_highlights %}
                    <div class="highlight">{{ highlight }}</div>
                {% endfor %}
            </div>
            
            <div class="footer">
                <p>This report was automatically generated by the Insights Executive Reporting System</p>
            </div>
        </body>
        </html>
        """
    
    def _get_weekly_report_template(self) -> str:
        """Get weekly report HTML template"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>{{ report_type }}</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .header { text-align: center; margin-bottom: 30px; border-bottom: 2px solid #333; padding-bottom: 20px; }
                .section { margin-bottom: 25px; page-break-inside: avoid; }
                .section h2 { color: #2c3e50; border-left: 4px solid #3498db; padding-left: 10px; }
                .trend-positive { color: #27ae60; }
                .trend-negative { color: #e74c3c; }
                .recommendation { background-color: #e8f4f8; border-left: 4px solid #3498db; padding: 10px; margin: 5px 0; }
                .footer { margin-top: 40px; text-align: center; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{{ report_type }}</h1>
                <p>{{ period_covered }} | Generated: {{ generated_at.strftime('%B %d, %Y at %I:%M %p') }}</p>
            </div>
            
            <div class="section">
                <h2>Executive Summary</h2>
                <p>{{ executive_summary }}</p>
            </div>
            
            <div class="section">
                <h2>Weekly Performance Analysis</h2>
                <p><strong>Revenue Trend:</strong> {{ weekly_performance.revenue_trend }}</p>
                <p><strong>Efficiency Trend:</strong> {{ weekly_performance.efficiency_trend }}</p>
                <p><strong>Cost Management:</strong> {{ weekly_performance.cost_trend }}</p>
                <p><strong>Overall Assessment:</strong> {{ weekly_performance.overall_assessment }}</p>
            </div>
            
            <div class="section">
                <h2>Strategic Recommendations</h2>
                {% for rec in strategic_recommendations %}
                    <div class="recommendation">{{ rec }}</div>
                {% endfor %}
            </div>
            
            <div class="footer">
                <p>Weekly Executive Report - Insights Intelligence System</p>
            </div>
        </body>
        </html>
        """
    
    def _get_monthly_report_template(self) -> str:
        """Get monthly report HTML template"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>{{ report_type }}</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
                .header { text-align: center; margin-bottom: 30px; border-bottom: 2px solid #333; padding-bottom: 20px; }
                .section { margin-bottom: 30px; page-break-inside: avoid; }
                .section h2 { color: #2c3e50; border-left: 4px solid #3498db; padding-left: 10px; }
                .board-summary { background-color: #f8f9fa; border: 2px solid #dee2e6; padding: 20px; margin: 20px 0; }
                .achievement { color: #27ae60; margin: 5px 0; }
                .challenge { color: #e74c3c; margin: 5px 0; }
                .footer { margin-top: 40px; text-align: center; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{{ report_type }}</h1>
                <p>{{ period_covered }} | Generated: {{ generated_at.strftime('%B %d, %Y at %I:%M %p') }}</p>
            </div>
            
            <div class="section">
                <h2>Executive Summary</h2>
                <p>{{ executive_summary }}</p>
            </div>
            
            <div class="section board-summary">
                <h2>Board Summary</h2>
                <p><strong>Executive Summary:</strong> {{ board_summary.executive_summary }}</p>
                <h3>Key Achievements:</h3>
                <ul>
                {% for achievement in board_summary.key_achievements %}
                    <li class="achievement">{{ achievement }}</li>
                {% endfor %}
                </ul>
                <h3>Key Challenges:</h3>
                <ul>
                {% for challenge in board_summary.key_challenges %}
                    <li class="challenge">{{ challenge }}</li>
                {% endfor %}
                </ul>
                <h3>Board Recommendations:</h3>
                <ul>
                {% for rec in board_summary.board_recommendations %}
                    <li>{{ rec }}</li>
                {% endfor %}
                </ul>
            </div>
            
            <div class="section">
                <h2>Business Health Assessment</h2>
                <p><strong>Overall Health:</strong> {{ business_health.overall_health }}</p>
                <p><strong>Financial Health:</strong> {{ business_health.financial_health }}</p>
                <p><strong>Operational Health:</strong> {{ business_health.operational_health }}</p>
                <p><strong>Strategic Health:</strong> {{ business_health.strategic_health }}</p>
            </div>
            
            <div class="section">
                <h2>Forward Outlook</h2>
                <p><strong>Next Month Outlook:</strong> {{ forward_outlook.next_month_outlook }}</p>
                <p><strong>Quarterly Forecast:</strong> {{ forward_outlook.quarterly_forecast }}</p>
                <h3>Key Priorities:</h3>
                <ul>
                {% for priority in forward_outlook.key_priorities %}
                    <li>{{ priority }}</li>
                {% endfor %}
                </ul>
            </div>
            
            <div class="footer">
                <p>Monthly Executive Report - Comprehensive Business Intelligence Analysis</p>
            </div>
        </body>
        </html>
        """
    
    def _save_report_record(self, report_content: Dict[str, Any], pdf_path: str, report_type: str):
        """Save report record to database.

        Creates an `Executive Report` doc holding the full report content
        (so preview/list never need to re-run the ML pipeline) and attaches
        the PDF to it via the standard file-manager, which creates the File
        record with a valid `attached_to_doctype`/`attached_to_name` and
        needs no pre-existing folder -- the earlier version pointed at a
        `Home/Executive Reports` folder and an `Executive Report` doctype
        that did not exist, so every report failed to save.
        """
        try:
            import json
            report_doc = frappe.get_doc({
                "doctype": "Executive Report",
                "report_type": report_type,
                "report_date": report_content["report_date"],
                "period_covered": report_content.get("period_covered", ""),
                "generated_at": report_content.get("generated_at") or now_datetime(),
                # `report_content` carries real `datetime`/`date` objects
                # (`generated_at`, `report_date`, and any date inside
                # `detailed_data`) that plain `json.dumps` cannot serialize.
                # Pre-serializing with `default=str` here, rather than letting
                # the JSON fieldtype's own `json.dumps(value)` run on the raw
                # dict, is what actually failed on every prior save attempt.
                "report_data": json.dumps(report_content, default=str),
                "status": "Generated",
            })
            report_doc.insert(ignore_permissions=True)

            if pdf_path:
                from frappe.utils.file_manager import save_file
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()
                file_doc = save_file(
                    fname=f"executive_report_{report_type}_{report_content['report_date']}.pdf",
                    content=pdf_bytes,
                    dt="Executive Report",
                    dn=report_doc.name,
                    is_private=1,
                )
                report_doc.pdf_file = file_doc.file_url
                report_doc.save(ignore_permissions=True)

            return report_doc

        except Exception as e:
            logger.error(f"Error saving report record: {e}")
            return None
    
    def send_report_via_email(self, report_path: str, recipients: List[str], report_type: str, report_date: str):
        """Send report via email to recipients"""
        try:
            subject = f"Executive Report - {report_type.title()} | {report_date}"
            
            message = f"""
            Dear Executive Team,
            
            Please find attached the {report_type} executive report for {report_date}.
            
            This report provides a comprehensive overview of business performance and includes:
            - Key performance metrics
            - Business health assessment
            - Strategic recommendations
            - Action items requiring attention
            
            The report has been automatically generated by the Insights Intelligence System.
            
            Best regards,
            Business Intelligence Team
            """
            
            # Send email with attachment
            frappe.sendmail(
                recipients=recipients,
                subject=subject,
                message=message,
                attachments=[{
                    "fname": f"executive_report_{report_type}_{report_date}.pdf",
                    "fcontent": open(report_path, "rb").read()
                }]
            )
            
            logger.info(f"Executive report sent to {len(recipients)} recipients")
            
        except Exception as e:
            logger.error(f"Error sending report via email: {e}")
    
    def schedule_automated_reports(self):
        """Describe the real automated report schedule.

        Reports are scheduled via `hooks.py`'s `scheduler_events` buckets
        (`daily`/`weekly`/`monthly`), not a fixed clock time this class
        configures -- the exact run time depends on Frappe's scheduler tick
        and site config. Previously returned invented times ("6:00 AM daily",
        "Monday 7:00 AM", "1st of month 8:00 AM") that did not match
        `hooks.py` and could not be changed by anything that read them.
        """
        try:
            return {
                "daily_reports": "Runs daily via the site scheduler",
                "weekly_reports": "Runs weekly via the site scheduler (Monday bucket)",
                "monthly_reports": "Runs monthly via the site scheduler (1st of month bucket)",
            }

        except Exception as e:
            logger.error(f"Error reading automated report schedule: {e}")
            return {"error": str(e)}


# API functions for Frappe
@frappe.whitelist()
def generate_executive_report(report_type: str = "daily"):
    """API endpoint to generate executive report"""
    try:
        reports_system = ExecutiveReports()
        
        if report_type == "daily":
            result = reports_system.generate_daily_executive_report()
        elif report_type == "weekly":
            result = reports_system.generate_weekly_executive_report()
        elif report_type == "monthly":
            result = reports_system.generate_monthly_executive_report()
        else:
            return {"error": "Invalid report type. Use 'daily', 'weekly', or 'monthly'"}
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Executive report generation API error: {e}")
        return {"error": str(e)}


@frappe.whitelist()
def send_executive_report_email(report_type: str = "daily", recipients: str | list | None = None):
    """API endpoint to send executive report via email"""
    try:
        if not recipients:
            recipients = ["ceo@company.com", "coo@company.com"]  # Default recipients
        
        reports_system = ExecutiveReports()
        
        # Generate report
        if report_type == "daily":
            result = reports_system.generate_daily_executive_report()
        elif report_type == "weekly":
            result = reports_system.generate_weekly_executive_report()
        elif report_type == "monthly":
            result = reports_system.generate_monthly_executive_report()
        else:
            return {"error": "Invalid report type"}
        
        if result.get("success"):
            # Send email
            reports_system.send_report_via_email(
                result["report_path"],
                recipients,
                report_type,
                str(result["report_data"]["report_date"])
            )
            
            return {
                "success": True,
                "message": f"Executive report sent to {len(recipients)} recipients",
                "report_path": result["report_path"]
            }
        else:
            return {"error": "Failed to generate report"}
        
    except Exception as e:
        frappe.log_error(f"Executive report email API error: {e}")
        return {"error": str(e)}


@frappe.whitelist()
def get_report_scheduling_status():
    """API endpoint to get report scheduling status"""
    try:
        reports_system = ExecutiveReports()
        return reports_system.schedule_automated_reports()
    except Exception as e:
        frappe.log_error(f"Report scheduling status API error: {e}")
        return {"error": str(e)}


# Scheduler functions
def generate_daily_executive_report():
    """Scheduler function for daily executive reports"""
    try:
        logger.info("Starting automated daily executive report generation...")
        
        reports_system = ExecutiveReports()
        result = reports_system.generate_daily_executive_report()
        
        if result.get("success"):
            # Send to default recipients
            recipients = frappe.get_list("User", filters={"role_profile_name": "Executive"}, pluck="email")
            if not recipients:
                recipients = ["admin@company.com"]  # Fallback
            
            reports_system.send_report_via_email(
                result["report_path"],
                recipients,
                "daily", 
                str(result["report_data"]["report_date"])
            )
            
            logger.info("Daily executive report generated and sent successfully")
        else:
            logger.error(f"Failed to generate daily executive report: {result.get('error')}")
        
    except Exception as e:
        logger.error(f"Error in automated daily executive report: {e}")
        frappe.log_error(f"Daily executive report automation error: {e}")


def generate_weekly_executive_report():
    """Scheduler function for weekly executive reports"""
    try:
        logger.info("Starting automated weekly executive report generation...")
        
        reports_system = ExecutiveReports()
        result = reports_system.generate_weekly_executive_report()
        
        if result.get("success"):
            # Send to executive recipients
            recipients = frappe.get_list("User", filters={"role_profile_name": "Executive"}, pluck="email")
            if not recipients:
                recipients = ["admin@company.com"]
            
            reports_system.send_report_via_email(
                result["report_path"],
                recipients,
                "weekly",
                str(result["report_data"]["report_date"])
            )
            
            logger.info("Weekly executive report generated and sent successfully")
        else:
            logger.error(f"Failed to generate weekly executive report: {result.get('error')}")
        
    except Exception as e:
        logger.error(f"Error in automated weekly executive report: {e}")
        frappe.log_error(f"Weekly executive report automation error: {e}")


def generate_monthly_executive_report():
    """Scheduler function for monthly executive reports"""
    try:
        logger.info("Starting automated monthly executive report generation...")
        
        reports_system = ExecutiveReports()
        result = reports_system.generate_monthly_executive_report()
        
        if result.get("success"):
            # Send to all executives and board members
            exec_recipients = frappe.get_list("User", filters={"role_profile_name": "Executive"}, pluck="email")
            board_recipients = frappe.get_list("User", filters={"role_profile_name": "Board Member"}, pluck="email")
            
            all_recipients = list(set(exec_recipients + board_recipients))
            if not all_recipients:
                all_recipients = ["admin@company.com"]
            
            reports_system.send_report_via_email(
                result["report_path"],
                all_recipients,
                "monthly",
                str(result["report_data"]["report_date"])
            )
            
            logger.info("Monthly executive report generated and sent successfully")
        else:
            logger.error(f"Failed to generate monthly executive report: {result.get('error')}")
        
    except Exception as e:
        logger.error(f"Error in automated monthly executive report: {e}")
        frappe.log_error(f"Monthly executive report automation error: {e}")