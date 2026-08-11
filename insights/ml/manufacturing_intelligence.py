from __future__ import annotations
"""
Manufacturing Intelligence Module

Provides comprehensive manufacturing analytics including production efficiency,
OEE tracking, quality metrics, and manufacturing optimization insights.
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

from ..analytics.data_collectors import ProductionDataCollector

logger = logging.getLogger(__name__)


class ManufacturingIntelligence:
    """
    Manufacturing Intelligence provides comprehensive production analytics
    including OEE analysis, capacity planning, and quality optimization.
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
    
    def get_manufacturing_overview(self, period: str = "YTD") -> Dict[str, Any]:
        """
        Get comprehensive manufacturing overview with key metrics
        
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
            
            # Collect production data
            collector = ProductionDataCollector({
                "from_date": from_date,
                "to_date": to_date
            })
            production_data = collector.collect()
            
            # Generate insights
            insights = {
                "period": period,
                "generated_at": datetime.now().isoformat(),
                
                # Core production metrics
                "production_metrics": self._analyze_production(production_data),
                "oee_analysis": self._calculate_oee(production_data),
                "quality_metrics": self._analyze_quality(production_data),
                "efficiency_metrics": self._analyze_efficiency(production_data),
                
                # Advanced analytics
                "capacity_utilization": self._analyze_capacity(production_data),
                "workstation_performance": self._analyze_workstations(production_data),
                "bottleneck_analysis": self._identify_bottlenecks(production_data),
                "cost_analysis": self._analyze_production_costs(production_data),
                
                # Predictive insights
                "production_forecast": self._forecast_production(production_data),
                "maintenance_insights": self._analyze_maintenance_needs(production_data),
                
                # Recommendations
                "recommendations": self._generate_manufacturing_recommendations(production_data),
                
                # Raw data for further analysis
                "raw_data": production_data
            }
            
            return insights
            
        except Exception as e:
            logger.error(f"Error generating manufacturing overview: {e}")
            return {
                "error": str(e),
                "period": period,
                "generated_at": datetime.now().isoformat()
            }
    
    def _analyze_production(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze core production metrics"""
        try:
            # Extract work order summary
            work_order_summary = production_data.get("work_order_summary", {})
            status_breakdown = production_data.get("status_breakdown", {})
            monthly_trend = production_data.get("monthly_production_trend", [])
            
            total_orders = work_order_summary.get("total_orders", 0)
            completed_orders = work_order_summary.get("completed_orders", 0)
            total_qty_produced = work_order_summary.get("total_qty_produced", 0)
            total_qty_planned = work_order_summary.get("total_qty_planned", 0)
            
            # Calculate key metrics
            completion_rate = (completed_orders / total_orders * 100) if total_orders else 0
            quantity_achievement = (total_qty_produced / total_qty_planned * 100) if total_qty_planned else 0
            
            # Calculate trend from monthly data
            growth_rate = 0
            if len(monthly_trend) >= 2:
                latest_month = monthly_trend[-1].get("total_qty", 0)
                prev_month = monthly_trend[-2].get("total_qty", 0)
                growth_rate = ((latest_month - prev_month) / prev_month * 100) if prev_month else 0
            
            return {
                "total_work_orders": total_orders,
                "completed_orders": completed_orders,
                "completion_rate_pct": round(completion_rate, 2),
                "total_production_qty": total_qty_produced,
                "planned_production_qty": total_qty_planned,
                "quantity_achievement_pct": round(quantity_achievement, 2),
                "monthly_growth_rate": round(growth_rate, 2),
                "production_health": "excellent" if completion_rate > 90 else "good" if completion_rate > 80 else "needs_improvement"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing production metrics: {e}")
            return {"error": str(e)}
    
    def _calculate_oee(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate Overall Equipment Effectiveness (OEE)"""
        try:
            # Get workstation utilization data
            workstation_util = production_data.get("workstation_utilization", [])
            work_order_summary = production_data.get("work_order_summary", {})
            
            if not workstation_util:
                return {"message": _("No workstation data available for OEE calculation")}
            
            # Calculate OEE components
            total_workstations = len(workstation_util)
            total_capacity_mins = sum(ws.get("capacity_mins", 0) for ws in workstation_util)
            total_utilized_mins = sum(ws.get("utilized_mins", 0) for ws in workstation_util)
            
            # Availability = Actual Operating Time / Planned Production Time
            availability = (total_utilized_mins / total_capacity_mins * 100) if total_capacity_mins else 0
            
            # Performance = Actual Output / Maximum Possible Output
            total_qty_produced = work_order_summary.get("total_qty_produced", 0)
            total_qty_planned = work_order_summary.get("total_qty_planned", 0)
            performance = (total_qty_produced / total_qty_planned * 100) if total_qty_planned else 0
            
            # Quality = Good Output / Total Output (simplified - assume 95% if no quality data)
            quality = 95.0  # This would need quality data from QC module
            
            # OEE = Availability × Performance × Quality
            oee_score = (availability * performance * quality) / 10000
            
            # Determine OEE rating
            oee_rating = "world_class"
            if oee_score < 40:
                oee_rating = "poor"
            elif oee_score < 60:
                oee_rating = "fair"  
            elif oee_score < 85:
                oee_rating = "good"
            
            return {
                "oee_score_pct": round(oee_score, 2),
                "availability_pct": round(availability, 2),
                "performance_pct": round(performance, 2),
                "quality_pct": round(quality, 2),
                "oee_rating": oee_rating,
                "benchmark_comparison": "above_average" if oee_score > 60 else "below_average"
            }
            
        except Exception as e:
            logger.error(f"Error calculating OEE: {e}")
            return {"error": str(e)}
    
    def _analyze_quality(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze quality metrics and defect rates.

        first_pass_yield_pct / defect_rate_ppm / quality_trends require QC
        doctype data that doesn't exist on this site — they are returned as
        null with a data-source note rather than the previous 3-bucket lookup
        table dressed up as measured yield/defect figures. See plan-eng-review
        D3.7. on_time_completion_pct is real (computed from Work Order data).
        """
        try:
            work_order_summary = production_data.get("work_order_summary", {})
            completed_orders = work_order_summary.get("completed_orders", 0)
            total_orders = work_order_summary.get("total_orders", 0)

            on_time_completion = (completed_orders / total_orders * 100) if total_orders else 0

            return {
                "first_pass_yield_pct": None,
                "on_time_completion_pct": round(on_time_completion, 2),
                "defect_rate_ppm": None,
                "quality_status": None,
                "quality_trends": None,
                "quality_data_note": "First pass yield, defect rate, and quality trends require a QC doctype not present on this site",
            }

        except Exception as e:
            logger.error(f"Error analyzing quality metrics: {e}")
            return {"error": str(e)}
    
    def _analyze_efficiency(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze production efficiency metrics"""
        import numpy as np
        try:
            production_eff = production_data.get("production_efficiency", {})
            workstation_util = production_data.get("workstation_utilization", [])
            
            avg_efficiency = production_eff.get("average_efficiency_pct", 0)
            
            # Calculate workstation efficiency variance
            efficiencies = []
            for ws in workstation_util:
                if ws.get("capacity_mins", 0) > 0:
                    eff = (ws.get("utilized_mins", 0) / ws.get("capacity_mins", 0) * 100)
                    efficiencies.append(eff)
            
            efficiency_variance = np.var(efficiencies) if efficiencies else 0
            efficiency_std = np.std(efficiencies) if efficiencies else 0
            
            # Identify best and worst performing workstations
            best_ws = max(workstation_util, key=lambda x: x.get("utilized_mins", 0) / max(x.get("capacity_mins", 1), 1)) if workstation_util else {}
            worst_ws = min(workstation_util, key=lambda x: x.get("utilized_mins", 0) / max(x.get("capacity_mins", 1), 1)) if workstation_util else {}
            
            return {
                "average_efficiency_pct": avg_efficiency,
                "efficiency_variance": round(efficiency_variance, 2),
                "efficiency_std_dev": round(efficiency_std, 2),
                "consistency_rating": "high" if efficiency_std < 10 else "medium" if efficiency_std < 20 else "low",
                "best_workstation": best_ws.get("workstation", "N/A"),
                "worst_workstation": worst_ws.get("workstation", "N/A"),
                "efficiency_trend": "improving" if avg_efficiency > 75 else "stable" if avg_efficiency > 60 else "declining"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing efficiency: {e}")
            return {"error": str(e)}
    
    def _analyze_capacity(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze capacity utilization and planning"""
        try:
            workstation_util = production_data.get("workstation_utilization", [])
            
            if not workstation_util:
                return {"message": _("No workstation capacity data available")}
            
            # Calculate overall capacity utilization
            total_capacity = sum(ws.get("capacity_mins", 0) for ws in workstation_util)
            total_utilized = sum(ws.get("utilized_mins", 0) for ws in workstation_util)
            
            overall_utilization = (total_utilized / total_capacity * 100) if total_capacity else 0
            
            # Identify capacity constraints
            high_util_workstations = [ws for ws in workstation_util 
                                    if (ws.get("utilized_mins", 0) / max(ws.get("capacity_mins", 1), 1)) > 0.85]
            
            low_util_workstations = [ws for ws in workstation_util 
                                   if (ws.get("utilized_mins", 0) / max(ws.get("capacity_mins", 1), 1)) < 0.50]
            
            # Calculate available capacity
            available_capacity_mins = total_capacity - total_utilized
            available_capacity_pct = (available_capacity_mins / total_capacity * 100) if total_capacity else 0
            
            return {
                "overall_utilization_pct": round(overall_utilization, 2),
                "available_capacity_pct": round(available_capacity_pct, 2),
                "available_capacity_hours": round(available_capacity_mins / 60, 1),
                "capacity_constrained_stations": len(high_util_workstations),
                "underutilized_stations": len(low_util_workstations),
                "capacity_planning_status": "optimal" if 70 <= overall_utilization <= 85 else "over_utilized" if overall_utilization > 85 else "under_utilized"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing capacity: {e}")
            return {"error": str(e)}
    
    def _analyze_workstations(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze individual workstation performance"""
        try:
            workstation_util = production_data.get("workstation_utilization", [])
            
            if not workstation_util:
                return {"message": _("No workstation performance data available")}
            
            # Calculate performance metrics for each workstation
            workstation_metrics = []
            for ws in workstation_util:
                utilization = (ws.get("utilized_mins", 0) / max(ws.get("capacity_mins", 1), 1) * 100)
                status = "optimal" if 70 <= utilization <= 85 else "overloaded" if utilization > 85 else "underutilized"
                
                workstation_metrics.append({
                    "workstation": ws.get("workstation", "Unknown"),
                    "utilization_pct": round(utilization, 2),
                    "capacity_hours": round(ws.get("capacity_mins", 0) / 60, 1),
                    "utilized_hours": round(ws.get("utilized_mins", 0) / 60, 1), 
                    "status": status
                })
            
            # Sort by utilization
            workstation_metrics.sort(key=lambda x: x["utilization_pct"], reverse=True)
            
            return {
                "workstation_count": len(workstation_metrics),
                "workstation_performance": workstation_metrics,
                "top_performer": workstation_metrics[0]["workstation"] if workstation_metrics else "N/A",
                "bottom_performer": workstation_metrics[-1]["workstation"] if workstation_metrics else "N/A"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing workstations: {e}")
            return {"error": str(e)}
    
    def _identify_bottlenecks(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Identify production bottlenecks and constraints"""
        try:
            workstation_util = production_data.get("workstation_utilization", [])
            
            if not workstation_util:
                return {"message": _("No data available for bottleneck analysis")}
            
            # Find bottlenecks (high utilization workstations)
            bottlenecks = []
            for ws in workstation_util:
                utilization = (ws.get("utilized_mins", 0) / max(ws.get("capacity_mins", 1), 1) * 100)
                if utilization > 90:
                    severity = "critical"
                elif utilization > 80:
                    severity = "high"
                else:
                    continue
                    
                bottlenecks.append({
                    "workstation": ws.get("workstation", "Unknown"),
                    "utilization_pct": round(utilization, 2),
                    "severity": severity,
                    "improvement_potential": round((utilization - 85), 2)
                })
            
            # Sort by severity (critical first)
            bottlenecks.sort(key=lambda x: (x["severity"] == "critical", x["utilization_pct"]), reverse=True)
            
            return {
                "bottleneck_count": len(bottlenecks),
                "bottlenecks": bottlenecks,
                "priority_bottleneck": bottlenecks[0]["workstation"] if bottlenecks else "None",
                "total_improvement_hours": sum(b["improvement_potential"] for b in bottlenecks)
            }
            
        except Exception as e:
            logger.error(f"Error identifying bottlenecks: {e}")
            return {"error": str(e)}
    
    def _analyze_production_costs(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze production costs and efficiency"""
        try:
            # This would be enhanced with actual costing data
            # For now, provide basic cost indicators
            
            work_order_summary = production_data.get("work_order_summary", {})
            total_qty_produced = work_order_summary.get("total_qty_produced", 0)
            
            # Estimated costs (would need actual cost data)
            estimated_labor_cost = total_qty_produced * 15  # $15 per unit estimate
            estimated_material_cost = total_qty_produced * 25  # $25 per unit estimate
            estimated_overhead = (estimated_labor_cost + estimated_material_cost) * 0.20
            
            total_cost = estimated_labor_cost + estimated_material_cost + estimated_overhead
            cost_per_unit = total_cost / total_qty_produced if total_qty_produced else 0
            
            return {
                "total_production_cost": round(total_cost, 2),
                "cost_per_unit": round(cost_per_unit, 2),
                "labor_cost_pct": round((estimated_labor_cost / total_cost * 100), 1) if total_cost else 0,
                "material_cost_pct": round((estimated_material_cost / total_cost * 100), 1) if total_cost else 0,
                "overhead_cost_pct": round((estimated_overhead / total_cost * 100), 1) if total_cost else 0,
                "cost_efficiency": "good" if cost_per_unit < 50 else "average" if cost_per_unit < 75 else "needs_improvement"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing production costs: {e}")
            return {"error": str(e)}
    
    def _forecast_production(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Forecast future production based on trends"""
        import numpy as np
        try:
            monthly_trend = production_data.get("monthly_production_trend", [])
            
            if len(monthly_trend) < 3:
                return {"message": _("Insufficient data for production forecasting")}
            
            # Calculate simple trend
            quantities = [month.get("total_qty", 0) for month in monthly_trend[-6:]]  # Last 6 months
            if not quantities:
                return {"message": _("No quantity data available")}
            
            # Simple linear trend calculation
            avg_monthly_production = np.mean(quantities)
            if len(quantities) >= 2:
                growth_rate = (quantities[-1] - quantities[0]) / len(quantities)
            else:
                growth_rate = 0
            
            # Forecast next 3 months
            forecasts = []
            for i in range(1, 4):
                forecast_qty = avg_monthly_production + (growth_rate * i)
                forecasts.append({
                    "month": i,
                    "forecasted_quantity": max(0, round(forecast_qty, 0)),
                    "confidence": "medium" if abs(growth_rate) < avg_monthly_production * 0.1 else "low"
                })
            
            return {
                "current_monthly_avg": round(avg_monthly_production, 0),
                "trend_direction": "increasing" if growth_rate > 0 else "decreasing" if growth_rate < 0 else "stable",
                "monthly_growth_rate": round(growth_rate, 1),
                "quarterly_forecast": forecasts,
                "forecast_reliability": "medium"
            }
            
        except Exception as e:
            logger.error(f"Error forecasting production: {e}")
            return {"error": str(e)}
    
    def _analyze_maintenance_needs(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze maintenance needs based on utilization"""
        try:
            workstation_util = production_data.get("workstation_utilization", [])
            
            if not workstation_util:
                return {"message": _("No workstation data for maintenance analysis")}
            
            # Identify high-utilization workstations needing maintenance
            maintenance_priorities = []
            for ws in workstation_util:
                utilization = (ws.get("utilized_mins", 0) / max(ws.get("capacity_mins", 1), 1) * 100)
                
                priority = "low"
                if utilization > 85:
                    priority = "high"
                elif utilization > 70:
                    priority = "medium"
                
                maintenance_priorities.append({
                    "workstation": ws.get("workstation", "Unknown"),
                    "utilization_pct": round(utilization, 2),
                    "maintenance_priority": priority,
                    "estimated_maintenance_hours": round(utilization / 20, 1)  # Rough estimate
                })
            
            # Sort by maintenance priority
            maintenance_priorities.sort(key=lambda x: (x["maintenance_priority"] == "high", x["utilization_pct"]), reverse=True)
            
            high_priority_count = sum(1 for ws in maintenance_priorities if ws["maintenance_priority"] == "high")
            
            return {
                "maintenance_requirements": maintenance_priorities,
                "high_priority_count": high_priority_count,
                "total_maintenance_hours": sum(ws["estimated_maintenance_hours"] for ws in maintenance_priorities),
                "maintenance_urgency": "immediate" if high_priority_count > 2 else "scheduled"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing maintenance needs: {e}")
            return {"error": str(e)}
    
    def _generate_manufacturing_recommendations(self, production_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate actionable manufacturing recommendations"""
        try:
            recommendations = []
            
            # Analyze production data for recommendations
            work_order_summary = production_data.get("work_order_summary", {})
            workstation_util = production_data.get("workstation_utilization", [])
            
            completion_rate = (work_order_summary.get("completed_orders", 0) / 
                             max(work_order_summary.get("total_orders", 1), 1) * 100)
            
            if completion_rate < 80:
                recommendations.append({
                    "priority": "high",
                    "category": "Production Efficiency", 
                    "title": "Improve Work Order Completion Rate",
                    "description": f"Current completion rate of {completion_rate:.1f}% is below target.",
                    "actions": ["Review scheduling process", "Identify bottlenecks", "Improve resource allocation"]
                })
            
            # Check for capacity issues
            if workstation_util:
                high_util_count = sum(1 for ws in workstation_util 
                                    if (ws.get("utilized_mins", 0) / max(ws.get("capacity_mins", 1), 1)) > 0.85)
                
                if high_util_count > len(workstation_util) * 0.3:  # More than 30% overutilized
                    recommendations.append({
                        "priority": "medium",
                        "category": "Capacity Management",
                        "title": "Address Capacity Constraints",
                        "description": f"{high_util_count} workstations are operating above 85% capacity.",
                        "actions": ["Consider additional shifts", "Invest in equipment", "Optimize scheduling"]
                    })
            
            # Quality improvement recommendation
            recommendations.append({
                "priority": "medium",
                "category": "Quality Management",
                "title": "Implement Quality Monitoring",
                "description": "Establish real-time quality metrics and monitoring systems.",
                "actions": ["Install quality sensors", "Train operators", "Implement SPC"]
            })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating manufacturing recommendations: {e}")
            return [{"error": str(e)}]


# API functions for Frappe
def get_manufacturing_overview(period="YTD"):
    """API endpoint for manufacturing overview"""
    try:
        mfg_intel = ManufacturingIntelligence()
        return mfg_intel.get_manufacturing_overview(period)
    except Exception as e:
        frappe.log_error(f"Manufacturing overview API error: {e}")
        return {"error": str(e)}


def get_oee_analysis(period="YTD"):
    """API endpoint for OEE analysis"""
    try:
        mfg_intel = ManufacturingIntelligence()
        data = mfg_intel.get_manufacturing_overview(period)
        return data.get("oee_analysis", {})
    except Exception as e:
        frappe.log_error(f"OEE analysis API error: {e}")
        return {"error": str(e)}


def get_capacity_analysis():
    """API endpoint for capacity analysis"""
    try:
        mfg_intel = ManufacturingIntelligence()
        data = mfg_intel.get_manufacturing_overview("YTD")
        return {
            "capacity_utilization": data.get("capacity_utilization", {}),
            "bottleneck_analysis": data.get("bottleneck_analysis", {}),
            "workstation_performance": data.get("workstation_performance", {})
        }
    except Exception as e:
        frappe.log_error(f"Capacity analysis API error: {e}")
        return {"error": str(e)}


def get_production_forecast():
    """API endpoint for production forecasting"""
    try:
        mfg_intel = ManufacturingIntelligence()
        data = mfg_intel.get_manufacturing_overview("TTM")  # Use trailing 12 months
        return data.get("production_forecast", {})
    except Exception as e:
        frappe.log_error(f"Production forecast API error: {e}")
        return {"error": str(e)}


def get_manufacturing_recommendations():
    """API endpoint for manufacturing recommendations"""
    try:
        mfg_intel = ManufacturingIntelligence()
        data = mfg_intel.get_manufacturing_overview("YTD")
        return data.get("recommendations", [])
    except Exception as e:
        frappe.log_error(f"Manufacturing recommendations API error: {e}")
        return {"error": str(e)}


def update_manufacturing_intelligence():
    """
    Scheduler function to update manufacturing intelligence daily
    """
    try:
        logger.info("Starting manufacturing intelligence update...")
        
        mfg_intel = ManufacturingIntelligence()
        
        # Generate fresh data for all periods
        periods = ["MTD", "QTD", "YTD", "TTM"]
        
        for period in periods:
            overview = mfg_intel.get_manufacturing_overview(period)
            
            # Cache the overview for 24 hours
            cache_key = f"manufacturing_overview_{period}"
            frappe.cache().set_value(cache_key, overview, expires_in_sec=86400)
            
            logger.info(f"Updated manufacturing intelligence for period: {period}")
        
        logger.info("Manufacturing intelligence update completed successfully")
        
    except Exception as e:
        logger.error(f"Error updating manufacturing intelligence: {e}")
        frappe.log_error(f"Manufacturing intelligence update error: {e}")