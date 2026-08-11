from __future__ import annotations
"""
Marketing Intelligence Module

Provides comprehensive marketing and CRM analytics including pipeline analysis,
campaign effectiveness, lead quality scoring, and marketing ROI optimization.
"""

import frappe
from frappe import _
from frappe.utils import nowdate, add_months, add_days, flt, cint, date_diff
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    import numpy as np

import logging

logger = logging.getLogger(__name__)


class MarketingIntelligence:
    """
    Marketing Intelligence provides comprehensive marketing and CRM analytics
    including pipeline management, campaign analysis, and lead optimization.
    """
    
    def __init__(self):
        self.today = nowdate()
        self.current_month_start = datetime.now().replace(day=1).date()
        self.current_quarter_start = self._get_quarter_start()
        self.current_year_start = datetime.now().replace(month=1, day=1).date()
        
    def _get_quarter_start(self) -> date:
        """Get the start date of current quarter"""
        current_month = datetime.now().month
        quarter_start_month = ((current_month - 1) // 3) * 3 + 1
        return datetime.now().replace(month=quarter_start_month, day=1).date()
    
    def get_marketing_overview(self, period: str = "YTD") -> Dict[str, Any]:
        """
        Get comprehensive marketing overview with key metrics
        
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
            
            # Collect marketing data
            marketing_data = self._collect_marketing_data(from_date, to_date)
            
            # Generate insights
            insights = {
                "period": period,
                "generated_at": datetime.now().isoformat(),
                
                # Core marketing metrics
                "pipeline_metrics": self._analyze_pipeline(marketing_data),
                "lead_metrics": self._analyze_leads(marketing_data),
                "campaign_metrics": self._analyze_campaigns(marketing_data),
                "conversion_metrics": self._analyze_conversions(marketing_data),
                
                # Advanced analytics
                "lead_quality_score": self._score_lead_quality(marketing_data),
                "customer_acquisition": self._analyze_customer_acquisition(marketing_data),
                "marketing_roi": self._calculate_marketing_roi(marketing_data),
                "channel_performance": self._analyze_channels(marketing_data),
                
                # Predictive insights
                "pipeline_forecast": self._forecast_pipeline(marketing_data),
                "lead_scoring": self._advanced_lead_scoring(marketing_data),
                
                # Recommendations
                "recommendations": self._generate_marketing_recommendations(marketing_data),
                
                # Raw data for further analysis
                "raw_data": marketing_data
            }
            
            return insights
            
        except Exception as e:
            logger.error(f"Error generating marketing overview: {e}")
            return {
                "error": str(e),
                "period": period,
                "generated_at": datetime.now().isoformat()
            }
    
    def _collect_marketing_data(self, from_date: date, to_date: date) -> Dict[str, Any]:
        """Collect comprehensive marketing data from ERPNext"""
        try:
            data = {}
            
            # Leads data. `custom_lead_score` is an optional custom field —
            # not installed on every site — so it's only selected when present
            # rather than always assumed, which previously raised
            # "Unknown column 'custom_lead_score'" and dropped lead data from
            # every caller (marketing overview, executive reports) on sites
            # without it. Downstream code already treats a missing score as
            # "no custom score" via `.get("custom_lead_score", 0)`.
            has_lead_score = frappe.db.has_column("Lead", "custom_lead_score")
            leads_query = f"""
                SELECT 
                    name, lead_name, company_name, status, source, territory,
                    lead_owner, creation, modified{", custom_lead_score" if has_lead_score else ""}
                FROM `tabLead`
                WHERE creation BETWEEN %s AND %s
                ORDER BY creation DESC
            """
            leads = frappe.db.sql(leads_query, (from_date, to_date), as_dict=True)
            data["leads"] = leads
            
            # Opportunities data. `weighted_amount` isn't a stored ERPNext
            # column (Opportunity only has `opportunity_amount`); computed
            # here as the standard probability-weighted pipeline value
            # instead of assumed, which previously raised "Unknown column
            # 'weighted_amount'" and dropped every opportunity from both the
            # marketing overview and executive reports.
            opportunities_query = """
                SELECT 
                    name, opportunity_from, party_name, opportunity_amount,
                    status, sales_stage, source, territory, contact_person,
                    expected_closing, probability,
                    (opportunity_amount * COALESCE(probability, 0) / 100) AS weighted_amount,
                    creation, modified
                FROM `tabOpportunity`
                WHERE creation BETWEEN %s AND %s
                ORDER BY creation DESC
            """
            opportunities = frappe.db.sql(opportunities_query, (from_date, to_date), as_dict=True)
            data["opportunities"] = opportunities
            
            # Customer data (newly acquired)
            customers_query = """
                SELECT 
                    name, customer_name, customer_type, territory, 
                    customer_group, default_currency, creation
                FROM `tabCustomer`
                WHERE creation BETWEEN %s AND %s
                ORDER BY creation DESC
            """
            customers = frappe.db.sql(customers_query, (from_date, to_date), as_dict=True)
            data["customers"] = customers
            
            # Sales orders for conversion tracking
            sales_orders_query = """
                SELECT 
                    so.name, so.customer, so.grand_total, so.status,
                    so.delivery_date, so.creation,
                    c.territory, c.customer_group
                FROM `tabSales Order` so
                LEFT JOIN `tabCustomer` c ON so.customer = c.name
                WHERE so.creation BETWEEN %s AND %s
                ORDER BY so.creation DESC
            """
            sales_orders = frappe.db.sql(sales_orders_query, (from_date, to_date), as_dict=True)
            data["sales_orders"] = sales_orders
            
            # Campaign data (if Campaign module is used)
            try:
                campaigns_query = """
                    SELECT 
                        name, campaign_name, description, start_date, end_date,
                        budget, actual_cost, expected_revenue, creation
                    FROM `tabCampaign`
                    WHERE start_date <= %s AND (end_date >= %s OR end_date IS NULL)
                """
                campaigns = frappe.db.sql(campaigns_query, (to_date, from_date), as_dict=True)
                data["campaigns"] = campaigns
            except:
                data["campaigns"] = []
            
            # Email marketing metrics (if Email Campaign exists)
            try:
                email_campaigns_query = """
                    SELECT 
                        name, subject, status, start_date, end_date,
                        total_recipients, delivered, opened, clicked,
                        unsubscribed, creation
                    FROM `tabEmail Campaign`
                    WHERE start_date BETWEEN %s AND %s
                """
                email_campaigns = frappe.db.sql(email_campaigns_query, (from_date, to_date), as_dict=True)
                data["email_campaigns"] = email_campaigns
            except:
                data["email_campaigns"] = []
            
            return data
            
        except Exception as e:
            logger.error(f"Error collecting marketing data: {e}")
            return {}
    
    def _analyze_pipeline(self, marketing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze sales pipeline metrics"""
        try:
            opportunities = marketing_data.get("opportunities", [])
            
            if not opportunities:
                return {"message": _("No opportunities data available")}
            
            total_opportunities = len(opportunities)
            total_pipeline_value = sum(opp.get("opportunity_amount", 0) for opp in opportunities)
            total_weighted_value = sum(opp.get("weighted_amount", 0) for opp in opportunities)
            
            # Status breakdown
            status_breakdown = {}
            for opp in opportunities:
                status = opp.get("status", "Unknown")
                status_breakdown[status] = status_breakdown.get(status, 0) + 1
            
            # Sales stage analysis
            stage_breakdown = {}  
            stage_values = {}
            for opp in opportunities:
                stage = opp.get("sales_stage", "Unknown")
                stage_breakdown[stage] = stage_breakdown.get(stage, 0) + 1
                stage_values[stage] = stage_values.get(stage, 0) + opp.get("opportunity_amount", 0)
            
            # Average deal size
            avg_deal_size = total_pipeline_value / total_opportunities if total_opportunities else 0
            
            # Won opportunities
            won_opportunities = [opp for opp in opportunities if opp.get("status") == "Open" and opp.get("probability", 0) > 80]
            won_count = len(won_opportunities)
            won_value = sum(opp.get("opportunity_amount", 0) for opp in won_opportunities)
            
            # Calculate conversion rate (opportunities to won)
            conversion_rate = (won_count / total_opportunities * 100) if total_opportunities else 0
            
            return {
                "total_opportunities": total_opportunities,
                "total_pipeline_value": total_pipeline_value,
                "total_weighted_value": total_weighted_value,
                "average_deal_size": round(avg_deal_size, 2),
                "conversion_rate_pct": round(conversion_rate, 2),
                "won_opportunities": won_count,
                "won_value": won_value,
                "status_breakdown": status_breakdown,
                "stage_breakdown": stage_breakdown,
                "stage_values": stage_values,
                "pipeline_health": "excellent" if conversion_rate > 25 else "good" if conversion_rate > 15 else "needs_improvement"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing pipeline: {e}")
            return {"error": str(e)}
    
    def _analyze_leads(self, marketing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze lead generation and quality metrics"""
        try:
            leads = marketing_data.get("leads", [])
            
            if not leads:
                return {"message": _("No leads data available")}
            
            total_leads = len(leads)
            
            # Lead status breakdown
            status_breakdown = {}
            for lead in leads:
                status = lead.get("status", "Unknown")
                status_breakdown[status] = status_breakdown.get(status, 0) + 1
            
            # Lead source analysis
            source_breakdown = {}
            for lead in leads:
                source = lead.get("source", "Unknown")
                source_breakdown[source] = source_breakdown.get(source, 0) + 1
            
            # Territory analysis
            territory_breakdown = {}
            for lead in leads:
                territory = lead.get("territory", "Unknown")
                territory_breakdown[territory] = territory_breakdown.get(territory, 0) + 1
            
            # Qualified leads (converted or interested)
            qualified_statuses = ["Converted", "Interested", "Quotation"]
            qualified_leads = [lead for lead in leads if lead.get("status") in qualified_statuses]
            qualified_count = len(qualified_leads)
            
            # Lead qualification rate
            qualification_rate = (qualified_count / total_leads * 100) if total_leads else 0
            
            # Average lead score (if available)
            scored_leads = [lead for lead in leads if lead.get("custom_lead_score")]
            avg_lead_score = 0
            if scored_leads:
                avg_lead_score = sum(lead.get("custom_lead_score", 0) for lead in scored_leads) / len(scored_leads)
            
            # Monthly trend
            monthly_leads = {}
            for lead in leads:
                creation_date = lead.get("creation")
                if creation_date:
                    month_key = creation_date.strftime("%Y-%m")
                    monthly_leads[month_key] = monthly_leads.get(month_key, 0) + 1
            
            return {
                "total_leads": total_leads,
                "qualified_leads": qualified_count,
                "qualification_rate_pct": round(qualification_rate, 2),
                "average_lead_score": round(avg_lead_score, 2),
                "status_breakdown": status_breakdown,
                "source_breakdown": source_breakdown,
                "territory_breakdown": territory_breakdown,
                "monthly_trend": monthly_leads,
                "lead_quality": "excellent" if qualification_rate > 30 else "good" if qualification_rate > 20 else "needs_improvement"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing leads: {e}")
            return {"error": str(e)}
    
    def _analyze_campaigns(self, marketing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze marketing campaign effectiveness"""
        try:
            campaigns = marketing_data.get("campaigns", [])
            email_campaigns = marketing_data.get("email_campaigns", [])
            
            campaign_metrics = {
                "total_campaigns": len(campaigns),
                "active_campaigns": 0,
                "total_budget": 0,
                "total_spent": 0,
                "expected_revenue": 0
            }
            
            # Traditional campaigns
            for campaign in campaigns:
                campaign_metrics["total_budget"] += campaign.get("budget", 0)
                campaign_metrics["total_spent"] += campaign.get("actual_cost", 0)
                campaign_metrics["expected_revenue"] += campaign.get("expected_revenue", 0)
                
                # Check if active (simplified check)
                end_date = campaign.get("end_date")
                if not end_date or end_date >= date.today():
                    campaign_metrics["active_campaigns"] += 1
            
            # Email campaign metrics
            email_metrics = {
                "total_email_campaigns": len(email_campaigns),
                "total_recipients": 0,
                "total_delivered": 0,
                "total_opened": 0,
                "total_clicked": 0,
                "total_unsubscribed": 0
            }
            
            for email_camp in email_campaigns:
                email_metrics["total_recipients"] += email_camp.get("total_recipients", 0)
                email_metrics["total_delivered"] += email_camp.get("delivered", 0)
                email_metrics["total_opened"] += email_camp.get("opened", 0)
                email_metrics["total_clicked"] += email_camp.get("clicked", 0)
                email_metrics["total_unsubscribed"] += email_camp.get("unsubscribed", 0)
            
            # Calculate email campaign rates
            if email_metrics["total_recipients"] > 0:
                email_metrics["delivery_rate_pct"] = (email_metrics["total_delivered"] / email_metrics["total_recipients"]) * 100
            else:
                email_metrics["delivery_rate_pct"] = 0
                
            if email_metrics["total_delivered"] > 0:
                email_metrics["open_rate_pct"] = (email_metrics["total_opened"] / email_metrics["total_delivered"]) * 100
                email_metrics["click_rate_pct"] = (email_metrics["total_clicked"] / email_metrics["total_delivered"]) * 100
            else:
                email_metrics["open_rate_pct"] = 0
                email_metrics["click_rate_pct"] = 0
            
            # Campaign ROI calculation
            campaign_roi = 0
            if campaign_metrics["total_spent"] > 0:
                campaign_roi = ((campaign_metrics["expected_revenue"] - campaign_metrics["total_spent"]) / campaign_metrics["total_spent"]) * 100
            
            return {
                "campaign_overview": campaign_metrics,
                "email_campaign_metrics": email_metrics,
                "campaign_roi_pct": round(campaign_roi, 2),
                "campaign_effectiveness": "excellent" if campaign_roi > 200 else "good" if campaign_roi > 100 else "needs_improvement"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing campaigns: {e}")
            return {"error": str(e)}
    
    def _analyze_conversions(self, marketing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze conversion funnel and customer acquisition"""
        try:
            leads = marketing_data.get("leads", [])
            opportunities = marketing_data.get("opportunities", [])
            customers = marketing_data.get("customers", [])
            sales_orders = marketing_data.get("sales_orders", [])
            
            # Funnel metrics
            lead_count = len(leads)
            opportunity_count = len(opportunities)
            customer_count = len(customers)
            sales_order_count = len(sales_orders)
            
            # Conversion rates
            lead_to_opportunity = (opportunity_count / lead_count * 100) if lead_count else 0
            opportunity_to_customer = (customer_count / opportunity_count * 100) if opportunity_count else 0
            customer_to_order = (sales_order_count / customer_count * 100) if customer_count else 0
            
            # Overall lead to sale conversion
            lead_to_sale = (sales_order_count / lead_count * 100) if lead_count else 0
            
            # Revenue metrics
            total_sales_value = sum(order.get("grand_total", 0) for order in sales_orders)
            avg_order_value = total_sales_value / sales_order_count if sales_order_count else 0
            
            # Customer acquisition cost requires campaign cost data linked to
            # customers, which doesn't exist on this site. Was previously a
            # flat 150 for every customer regardless of actual spend — worse
            # than no number since it implies uniform cost. See D3.8.
            estimated_cac = None
            
            # Customer lifetime value (simplified)
            estimated_clv = avg_order_value * 3  # Simplified estimate
            
            return {
                "funnel_metrics": {
                    "leads": lead_count,
                    "opportunities": opportunity_count,
                    "customers": customer_count,
                    "sales_orders": sales_order_count
                },
                "conversion_rates": {
                    "lead_to_opportunity_pct": round(lead_to_opportunity, 2),
                    "opportunity_to_customer_pct": round(opportunity_to_customer, 2),
                    "customer_to_order_pct": round(customer_to_order, 2),
                    "lead_to_sale_pct": round(lead_to_sale, 2)
                },
                "revenue_metrics": {
                    "total_sales_value": total_sales_value,
                    "average_order_value": round(avg_order_value, 2),
                    "estimated_cac": estimated_cac,
                    "estimated_clv": round(estimated_clv, 2),
                    "clv_cac_ratio": round(estimated_clv / estimated_cac, 2) if estimated_cac else None,
                },
                "conversion_health": "excellent" if lead_to_sale > 10 else "good" if lead_to_sale > 5 else "needs_improvement"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing conversions: {e}")
            return {"error": str(e)}
    
    def _score_lead_quality(self, marketing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Score lead quality based on various factors"""
        try:
            leads = marketing_data.get("leads", [])
            opportunities = marketing_data.get("opportunities", [])
            
            if not leads:
                return {"message": _("No leads data for quality scoring")}
            
            # Create lead quality scoring
            quality_scores = []
            
            for lead in leads:
                score = 0
                factors = []
                
                # Company name provided (higher quality)
                if lead.get("company_name"):
                    score += 20
                    factors.append("Company provided")
                
                # High-value sources
                source = lead.get("source", "").lower()
                if "referral" in source or "existing customer" in source:
                    score += 25
                    factors.append("High-value source")
                elif "website" in source or "campaign" in source:
                    score += 15
                    factors.append("Digital source")
                
                # Lead status quality
                status = lead.get("status", "").lower()
                if "converted" in status:
                    score += 30
                    factors.append("Converted")
                elif "interested" in status or "qualified" in status:
                    score += 20
                    factors.append("Qualified")
                
                # Custom lead score (if available)
                custom_score = lead.get("custom_lead_score", 0)
                if custom_score:
                    score += min(custom_score / 10, 25)  # Scale to max 25 points
                    factors.append(f"Custom score: {custom_score}")
                
                quality_scores.append({
                    "lead": lead.get("name"),
                    "score": min(score, 100),  # Cap at 100
                    "grade": "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D",
                    "factors": factors
                })
            
            # Calculate averages and distribution
            avg_score = sum(ls["score"] for ls in quality_scores) / len(quality_scores)
            
            grade_distribution = {"A": 0, "B": 0, "C": 0, "D": 0}
            for ls in quality_scores:
                grade_distribution[ls["grade"]] += 1
            
            # High-quality leads percentage
            high_quality_pct = (grade_distribution["A"] + grade_distribution["B"]) / len(quality_scores) * 100
            
            return {
                "average_lead_score": round(avg_score, 2),
                "grade_distribution": grade_distribution,
                "high_quality_percentage": round(high_quality_pct, 2),
                "total_scored_leads": len(quality_scores),
                "quality_assessment": "excellent" if high_quality_pct > 60 else "good" if high_quality_pct > 40 else "needs_improvement",
                "top_leads": sorted(quality_scores, key=lambda x: x["score"], reverse=True)[:10]
            }
            
        except Exception as e:
            logger.error(f"Error scoring lead quality: {e}")
            return {"error": str(e)}
    
    def _analyze_customer_acquisition(self, marketing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze customer acquisition patterns and costs"""
        try:
            customers = marketing_data.get("customers", [])
            campaigns = marketing_data.get("campaigns", [])
            
            if not customers:
                return {"message": _("No customer acquisition data available")}
            
            total_customers = len(customers)
            
            # Customer type breakdown
            type_breakdown = {}
            for customer in customers:
                ctype = customer.get("customer_type", "Unknown")
                type_breakdown[ctype] = type_breakdown.get(ctype, 0) + 1
            
            # Territory breakdown
            territory_breakdown = {}
            for customer in customers:
                territory = customer.get("territory", "Unknown")
                territory_breakdown[territory] = territory_breakdown.get(territory, 0) + 1
            
            # Customer group analysis
            group_breakdown = {}
            for customer in customers:
                group = customer.get("customer_group", "Unknown")
                group_breakdown[group] = group_breakdown.get(group, 0) + 1
            
            # Monthly acquisition trend
            monthly_acquisition = {}
            for customer in customers:
                creation_date = customer.get("creation")
                if creation_date:
                    month_key = creation_date.strftime("%Y-%m")
                    monthly_acquisition[month_key] = monthly_acquisition.get(month_key, 0) + 1
            
            # Calculate acquisition cost (if campaign data available)
            total_campaign_cost = sum(camp.get("actual_cost", 0) for camp in campaigns)
            acquisition_cost_per_customer = total_campaign_cost / total_customers if total_customers and total_campaign_cost else 0
            
            return {
                "total_new_customers": total_customers,
                "customer_type_breakdown": type_breakdown,
                "territory_breakdown": territory_breakdown,
                "customer_group_breakdown": group_breakdown,
                "monthly_acquisition_trend": monthly_acquisition,
                "acquisition_cost_per_customer": round(acquisition_cost_per_customer, 2),
                "acquisition_efficiency": "excellent" if acquisition_cost_per_customer < 100 else "good" if acquisition_cost_per_customer < 250 else "needs_improvement"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing customer acquisition: {e}")
            return {"error": str(e)}
    
    def _calculate_marketing_roi(self, marketing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate marketing ROI and attribution"""
        try:
            campaigns = marketing_data.get("campaigns", [])
            sales_orders = marketing_data.get("sales_orders", [])
            
            total_marketing_spend = sum(camp.get("actual_cost", 0) for camp in campaigns)
            total_attributed_revenue = sum(order.get("grand_total", 0) for order in sales_orders)
            
            # Calculate ROI
            if total_marketing_spend > 0:
                roi = ((total_attributed_revenue - total_marketing_spend) / total_marketing_spend) * 100
                roas = total_attributed_revenue / total_marketing_spend  # Return on Ad Spend
            else:
                roi = 0
                roas = 0
            
            # Cost per acquisition
            customer_count = len(marketing_data.get("customers", []))
            cpa = total_marketing_spend / customer_count if customer_count else 0
            
            # Revenue per customer
            rpc = total_attributed_revenue / customer_count if customer_count else 0
            
            return {
                "total_marketing_spend": total_marketing_spend,
                "total_attributed_revenue": total_attributed_revenue,
                "marketing_roi_pct": round(roi, 2),
                "return_on_ad_spend": round(roas, 2),
                "cost_per_acquisition": round(cpa, 2),
                "revenue_per_customer": round(rpc, 2),
                "roi_assessment": "excellent" if roi > 300 else "good" if roi > 150 else "needs_improvement"
            }
            
        except Exception as e:
            logger.error(f"Error calculating marketing ROI: {e}")
            return {"error": str(e)}
    
    def _analyze_channels(self, marketing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze performance across marketing channels"""
        try:
            leads = marketing_data.get("leads", [])
            opportunities = marketing_data.get("opportunities", [])
            
            # Channel performance tracking
            channel_performance = {}
            
            # Lead sources as channels
            for lead in leads:
                source = lead.get("source", "Unknown")
                if source not in channel_performance:
                    channel_performance[source] = {
                        "leads": 0,
                        "opportunities": 0,
                        "conversion_rate": 0,
                        "qualified_leads": 0
                    }
                
                channel_performance[source]["leads"] += 1 
                
                # Check if qualified
                if lead.get("status") in ["Converted", "Interested", "Quotation"]:
                    channel_performance[source]["qualified_leads"] += 1
            
            # Add opportunity data
            for opp in opportunities:
                source = opp.get("source", "Unknown")
                if source in channel_performance:
                    channel_performance[source]["opportunities"] += 1
            
            # Calculate conversion rates
            for channel, metrics in channel_performance.items():
                if metrics["leads"] > 0:
                    metrics["conversion_rate"] = (metrics["qualified_leads"] / metrics["leads"]) * 100
            
            # Sort channels by performance
            sorted_channels = sorted(
                channel_performance.items(),
                key=lambda x: (x[1]["conversion_rate"], x[1]["leads"]),
                reverse=True
            )
            
            return {
                "channel_performance": dict(sorted_channels),
                "top_performing_channel": sorted_channels[0][0] if sorted_channels else "None",
                "total_channels": len(channel_performance),
                "channel_diversity": "high" if len(channel_performance) > 5 else "medium" if len(channel_performance) > 3 else "low"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing channels: {e}")
            return {"error": str(e)}
    
    def _forecast_pipeline(self, marketing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Forecast pipeline development and revenue"""
        try:
            opportunities = marketing_data.get("opportunities", [])
            
            if not opportunities:
                return {"message": _("Insufficient data for pipeline forecasting")}
            
            # Current pipeline analysis
            total_pipeline = sum(opp.get("opportunity_amount", 0) for opp in opportunities)
            weighted_pipeline = sum(opp.get("weighted_amount", 0) for opp in opportunities)
            
            # Forecast based on probability
            high_prob_opps = [opp for opp in opportunities if opp.get("probability", 0) > 70]
            medium_prob_opps = [opp for opp in opportunities if 30 <= opp.get("probability", 0) <= 70]
            low_prob_opps = [opp for opp in opportunities if opp.get("probability", 0) < 30]
            
            high_prob_value = sum(opp.get("opportunity_amount", 0) for opp in high_prob_opps)
            medium_prob_value = sum(opp.get("opportunity_amount", 0) for opp in medium_prob_opps)
            low_prob_value = sum(opp.get("opportunity_amount", 0) for opp in low_prob_opps)
            
            # Revenue forecast (conservative, optimistic, pessimistic)
            conservative_forecast = high_prob_value * 0.8 + medium_prob_value * 0.4
            optimistic_forecast = high_prob_value * 0.9 + medium_prob_value * 0.6 + low_prob_value * 0.2
            pessimistic_forecast = high_prob_value * 0.6 + medium_prob_value * 0.2
            
            return {
                "current_pipeline_value": total_pipeline,
                "weighted_pipeline_value": weighted_pipeline,
                "probability_breakdown": {
                    "high_probability": {"count": len(high_prob_opps), "value": high_prob_value},
                    "medium_probability": {"count": len(medium_prob_opps), "value": medium_prob_value},
                    "low_probability": {"count": len(low_prob_opps), "value": low_prob_value}
                },
                "revenue_forecast": {
                    "conservative": round(conservative_forecast, 2),
                    "optimistic": round(optimistic_forecast, 2), 
                    "pessimistic": round(pessimistic_forecast, 2)
                },
                "forecast_confidence": "high" if len(opportunities) > 20 else "medium" if len(opportunities) > 10 else "low"
            }
            
        except Exception as e:
            logger.error(f"Error forecasting pipeline: {e}")
            return {"error": str(e)}
    
    def _advanced_lead_scoring(self, marketing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Advanced lead scoring using multiple factors"""
        try:
            leads = marketing_data.get("leads", [])
            
            if not leads:
                return {"message": _("No leads available for scoring")}
            
            # Scoring model
            scoring_model = {
                "source_scores": {
                    "Referral": 30, "Existing Customer": 25, "Website": 20,
                    "Campaign": 15, "Email": 12, "Social Media": 10,
                    "Advertisement": 8, "Conference": 15, "Cold Call": 5
                },
                "status_scores": {
                    "Converted": 40, "Interested": 30, "Qualified": 25,
                    "Open": 15, "Replied": 20, "Opportunity": 35
                },
                "company_bonus": 15,
                "territory_scores": {
                    # Can be customized based on business priorities
                    "All Territories": 10  # Default
                }
            }
            
            scored_leads = []
            
            for lead in leads:
                score = 0
                scoring_details = []
                
                # Source scoring
                source = lead.get("source", "")
                source_score = scoring_model["source_scores"].get(source, 5)
                score += source_score
                scoring_details.append(f"Source ({source}): {source_score}")
                
                # Status scoring
                status = lead.get("status", "")
                status_score = scoring_model["status_scores"].get(status, 5)
                score += status_score
                scoring_details.append(f"Status ({status}): {status_score}")
                
                # Company name bonus
                if lead.get("company_name"):
                    score += scoring_model["company_bonus"]
                    scoring_details.append(f"Company provided: {scoring_model['company_bonus']}")
                
                # Territory scoring
                territory = lead.get("territory", "All Territories")
                territory_score = scoring_model["territory_scores"].get(territory, 10)
                score += territory_score
                scoring_details.append(f"Territory ({territory}): {territory_score}")
                
                # Custom lead score integration
                custom_score = lead.get("custom_lead_score", 0)
                if custom_score:
                    score += min(custom_score, 20)  # Cap at 20 additional points
                    scoring_details.append(f"Custom score: {custom_score}")
                
                # Final grade assignment
                final_score = min(score, 100)
                if final_score >= 80:
                    grade = "Hot"
                elif final_score >= 60:
                    grade = "Warm"
                elif final_score >= 40:
                    grade = "Cold"
                else:
                    grade = "Ice"
                
                scored_leads.append({
                    "lead": lead.get("name"),
                    "lead_name": lead.get("lead_name"),
                    "company": lead.get("company_name", ""),
                    "score": final_score,
                    "grade": grade,
                    "priority": "High" if grade in ["Hot", "Warm"] else "Medium" if grade == "Cold" else "Low",
                    "scoring_details": scoring_details
                })
            
            # Sort by score
            scored_leads.sort(key=lambda x: x["score"], reverse=True)
            
            # Calculate grade distribution
            grade_distribution = {"Hot": 0, "Warm": 0, "Cold": 0, "Ice": 0}
            for lead in scored_leads:
                grade_distribution[lead["grade"]] += 1
            
            average_score = sum(lead["score"] for lead in scored_leads) / len(scored_leads)
            
            return {
                "total_scored_leads": len(scored_leads),
                "average_score": round(average_score, 2),
                "grade_distribution": grade_distribution,
                "high_priority_leads": len([l for l in scored_leads if l["priority"] == "High"]),
                "scored_leads": scored_leads,
                "top_leads": scored_leads[:20],  # Top 20 leads
                "scoring_effectiveness": "excellent" if average_score > 65 else "good" if average_score > 50 else "needs_improvement"
            }
            
        except Exception as e:
            logger.error(f"Error in advanced lead scoring: {e}")
            return {"error": str(e)}
    
    def _generate_marketing_recommendations(self, marketing_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate actionable marketing recommendations"""
        try:
            recommendations = []
            
            # Analyze lead metrics for recommendations
            lead_metrics = self._analyze_leads(marketing_data)
            pipeline_metrics = self._analyze_pipeline(marketing_data)
            conversion_metrics = self._analyze_conversions(marketing_data)
            
            # Lead generation recommendations
            qualification_rate = lead_metrics.get("qualification_rate_pct", 0)
            if qualification_rate < 20:
                recommendations.append({
                    "priority": "high",
                    "category": "Lead Generation",
                    "title": "Improve Lead Qualification Process",
                    "description": f"Lead qualification rate of {qualification_rate}% is below benchmark (25%+)",
                    "actions": ["Implement lead scoring system", "Improve lead capture forms", "Enhance pre-qualification criteria"]
                })
            
            # Pipeline recommendations
            conversion_rate = pipeline_metrics.get("conversion_rate_pct", 0)
            if conversion_rate < 15:
                recommendations.append({
                    "priority": "high",
                    "category": "Sales Pipeline",
                    "title": "Enhance Pipeline Conversion",
                    "description": f"Pipeline conversion rate of {conversion_rate}% needs improvement",
                    "actions": ["Improve sales follow-up process", "Provide better sales training", "Optimize sales stages"]
                })
            
            # Channel optimization
            channel_data = self._analyze_channels(marketing_data)
            if channel_data.get("channel_diversity") == "low":
                recommendations.append({
                    "priority": "medium",
                    "category": "Channel Optimization",
                    "title": "Diversify Marketing Channels",
                    "description": "Limited marketing channel diversity increases risk",
                    "actions": ["Explore new lead sources", "Test additional marketing channels", "Implement multi-channel strategy"]
                })
            
            # ROI optimization
            roi_data = self._calculate_marketing_roi(marketing_data)
            roi = roi_data.get("marketing_roi_pct", 0)
            if roi < 150:
                recommendations.append({
                    "priority": "medium",
                    "category": "ROI Optimization",
                    "title": "Improve Marketing ROI",
                    "description": f"Marketing ROI of {roi}% is below target (200%+)",
                    "actions": ["Optimize campaign targeting", "Reduce acquisition costs", "Focus on high-converting channels"]
                })
            
             # Lead nurturing recommendation
            total_leads = lead_metrics.get("total_leads", 0)
            qualified_leads = lead_metrics.get("qualified_leads", 0)
            if total_leads > qualified_leads * 2:  # Many unqualified leads
                recommendations.append({
                    "priority": "medium",
                    "category": "Lead Nurturing",
                    "title": "Implement Lead Nurturing Program",
                    "description": "Large number of unqualified leads suggest need for nurturing",
                    "actions": ["Create email nurturing sequences", "Develop content marketing strategy", "Implement marketing automation"]
                })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating marketing recommendations: {e}")
            return [{"error": str(e)}]

    # ==================== SOURCE METRICS ====================

    def get_source_metrics(self, period_start: str, period_end: str) -> Dict[str, Any]:
        """Get lead source metrics including cost per lead."""
        from insights.ml.marketing_source_metrics import (
            get_leads_by_source,
            get_hot_leads_by_source,
            get_cost_per_lead,
            get_territory_leads,
        )
        return {
            "leads_by_source": get_leads_by_source(period_start, period_end),
            "hot_leads_by_source": get_hot_leads_by_source(period_start, period_end),
            "cost_per_lead": get_cost_per_lead(period_start, period_end),
            "territory_leads": get_territory_leads(period_start, period_end),
        }


# API functions for Frappe
def get_marketing_overview(period="YTD"):
    """API endpoint for marketing overview"""
    try:
        marketing_intel = MarketingIntelligence()
        return marketing_intel.get_marketing_overview(period)
    except Exception as e:
        frappe.log_error(f"Marketing overview API error: {e}")
        return {"error": str(e)}


def get_pipeline_analysis(period="YTD"):
    """API endpoint for pipeline analysis"""
    try:
        marketing_intel = MarketingIntelligence()
        data = marketing_intel.get_marketing_overview(period)
        return {
            "pipeline_metrics": data.get("pipeline_metrics", {}),
            "pipeline_forecast": data.get("pipeline_forecast", {}),
            "conversion_metrics": data.get("conversion_metrics", {})
        }
    except Exception as e:
        frappe.log_error(f"Pipeline analysis API error: {e}")
        return {"error": str(e)}


def get_lead_analytics():
    """API endpoint for lead analytics"""
    try:
        marketing_intel = MarketingIntelligence()
        data = marketing_intel.get_marketing_overview("YTD")
        return {
            "lead_metrics": data.get("lead_metrics", {}),
            "lead_quality_score": data.get("lead_quality_score", {}),
            "lead_scoring": data.get("lead_scoring", {})
        }
    except Exception as e:
        frappe.log_error(f"Lead analytics API error: {e}")
        return {"error": str(e)}


def get_campaign_performance():
    """API endpoint for campaign performance"""
    try:
        marketing_intel = MarketingIntelligence()
        data = marketing_intel.get_marketing_overview("YTD")
        return {
            "campaign_metrics": data.get("campaign_metrics", {}),
            "marketing_roi": data.get("marketing_roi", {}),
            "channel_performance": data.get("channel_performance", {})
        }
    except Exception as e:
        frappe.log_error(f"Campaign performance API error: {e}")
        return {"error": str(e)}


def get_marketing_recommendations():
    """API endpoint for marketing recommendations"""
    try:
        marketing_intel = MarketingIntelligence()
        data = marketing_intel.get_marketing_overview("YTD")
        return data.get("recommendations", [])
    except Exception as e:
        frappe.log_error(f"Marketing recommendations API error: {e}")
        return {"error": str(e)}


def update_marketing_intelligence():
    """
    Scheduler function to update marketing intelligence daily
    """
    try:
        logger.info("Starting marketing intelligence update...")
        
        marketing_intel = MarketingIntelligence()
        
        # Generate fresh data for all periods
        periods = ["MTD", "QTD", "YTD", "TTM"]
        
        for period in periods:
            overview = marketing_intel.get_marketing_overview(period)
            
            # Cache the overview for 24 hours
            cache_key = f"marketing_overview_{period}"
            frappe.cache().set_value(cache_key, overview, expires_in_sec=86400)
            
            logger.info(f"Updated marketing intelligence for period: {period}")
        
        logger.info("Marketing intelligence update completed successfully")
        
    except Exception as e:
        logger.error(f"Error updating marketing intelligence: {e}")
        frappe.log_error(f"Marketing intelligence update error: {e}")


def get_source_metrics(period: str = "YTD"):
    """API endpoint for lead source metrics"""
    try:
        from insights.ml.marketing_source_metrics import (
            get_leads_by_source,
            get_hot_leads_by_source,
            get_cost_per_lead,
            get_territory_leads,
        )
        from frappe.utils import nowdate, add_months
        from datetime import datetime

        end_date = nowdate()
        if period == "MTD":
            start_date = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        elif period == "QTD":
            current_month = datetime.now().month
            quarter_start_month = ((current_month - 1) // 3) * 3 + 1
            start_date = datetime.now().replace(month=quarter_start_month, day=1).strftime("%Y-%m-%d")
        elif period == "YTD":
            start_date = datetime.now().replace(month=1, day=1).strftime("%Y-%m-%d")
        else:  # TTM
            start_date = add_months(end_date, -12)

        return {
            "leads_by_source": get_leads_by_source(start_date, end_date),
            "hot_leads_by_source": get_hot_leads_by_source(start_date, end_date),
            "cost_per_lead": get_cost_per_lead(start_date, end_date),
            "territory_leads": get_territory_leads(start_date, end_date),
        }
    except Exception as e:
        frappe.log_error(f"Source metrics API error: {e}")
        return {"error": str(e)}