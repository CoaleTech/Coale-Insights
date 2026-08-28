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
            period: One of MTD, QTD, YTD, TTM, or a `custom:<start>:<end>`
                range (see `insights.api.ml.utils.parse_custom_range`)
        """
        try:
            from insights.api.ml.utils import parse_custom_range

            custom = parse_custom_range(period)
            if custom:
                from_date, to_date = custom[0].date(), custom[1].date()
            else:
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
            
            # Normalize the collector's separate `summary`/`efficiency`/
            # `completed_order_count` blocks into the `work_order_summary`
            # shape every analysis method below expects. Before this, every
            # `.get("work_order_summary", {})` call silently fell back to
            # `{}` (the key was never populated by the collector), so
            # completion rate, quantity achievement, OEE performance,
            # on-time completion, and the completion-rate recommendation
            # were all unconditionally zero regardless of real Work Order
            # data.
            _summary = production_data.get("summary", {}) or {}
            _efficiency = production_data.get("efficiency", {}) or {}
            production_data["work_order_summary"] = {
                "total_orders": _summary.get("total_orders", 0),
                "completed_orders": production_data.get("completed_order_count", 0),
                "total_qty_produced": _efficiency.get("produced_qty", 0),
                "total_qty_planned": _efficiency.get("planned_qty", 0),
            }
            
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
            monthly_trend = production_data.get("monthly_trend", [])
            
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
                latest_month = monthly_trend[-1].get("produced_qty", 0)
                prev_month = monthly_trend[-2].get("produced_qty", 0)
                growth_rate = ((latest_month - prev_month) / prev_month * 100) if prev_month else 0

            # Pending Material Requests: same filter as get_manufacturing_detail's
            # `material_requests` drill-down (insights/api/ml/manufacturing.py), so
            # this count and that record list always agree.
            pending_material_requests = frappe.db.count(
                "Material Request",
                filters={"docstatus": 1, "status": ("in", ["Pending", "Partially Ordered"])},
            )

            return {
                "total_work_orders": total_orders,
                "completed_orders": completed_orders,
                "open_work_orders": max(0, total_orders - completed_orders),
                "completion_rate_pct": round(completion_rate, 2),
                "total_production_qty": total_qty_produced,
                "planned_production_qty": total_qty_planned,
                "quantity_achievement_pct": round(quantity_achievement, 2),
                "monthly_growth_rate": round(growth_rate, 2),
                "pending_material_requests": pending_material_requests,
                # Health label is meaningless on a 0/0 site (completion_rate
                # is 0 because there's no denominator, not because the
                # 0-completion rate is bad). Leave it null when there
                # are no Work Orders to evaluate.
                "production_health": (
                    "excellent" if completion_rate > 90
                    else "good" if completion_rate > 80
                    else "needs_improvement"
                ) if total_orders > 0 else None,
            }
        except Exception as e:
            logger.error(f"Error analyzing production metrics: {e}")
            return {"error": str(e)}
    
    def _calculate_oee(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate Overall Equipment Effectiveness (OEE).

        Only performance (produced qty vs planned qty) is real. Availability
        and quality are not computed rather than estimated:
        - availability needs workstation capacity_mins, which nothing in
          this app queries yet (Workstation working hours + holiday list +
          production_capacity -- see TODOS.md).
        - quality needs QC data, which doesn't exist on this site (same gap
          as quality_metrics.first_pass_yield_pct/defect_rate_ppm above;
          this used to be a hardcoded 95% constant).
        A composite oee_score_pct/oee_rating built from two fabricated
        factors would be a fake number dressed up as measured, so both are
        left unset rather than computed from partial data.
        """
        try:
            workstation_util = production_data.get("workstation_utilization", [])
            work_order_summary = production_data.get("work_order_summary", {})

            if not workstation_util:
                return {"message": _("No workstation data available for OEE calculation")}

            # Performance = Actual Output / Maximum Possible Output
            total_qty_produced = work_order_summary.get("total_qty_produced", 0)
            total_qty_planned = work_order_summary.get("total_qty_planned", 0)
            performance = (total_qty_produced / total_qty_planned * 100) if total_qty_planned else 0

            return {
                "oee_score_pct": None,
                "availability_pct": None,
                "performance_pct": round(performance, 2),
                "quality_pct": None,
                "oee_rating": None,
                "benchmark_comparison": None,
                "oee_data_note": _(
                    "Availability (workstation capacity) and quality (QC data) are not "
                    "available on this site; only performance (production qty vs. plan) is measured."
                ),
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
        """Analyze production efficiency metrics.

        `average_efficiency_pct` is real (produced/planned qty, from the
        collector's `efficiency` block). Per-workstation efficiency
        variance and best/worst-workstation ranking are not computed: both
        need a workstation capacity (available minutes) denominator that
        isn't sourced yet (see `_analyze_capacity`). This used to divide by
        a phantom `capacity_mins` key that is never populated, which made
        every workstation's efficiency tie at 0 and best/worst collapse to
        whichever workstation happened to be first in the list.
        """
        try:
            production_eff = production_data.get("efficiency", {})
            avg_efficiency = production_eff.get("efficiency_percent", 0)

            return {
                "average_efficiency_pct": avg_efficiency,
                "efficiency_variance": None,
                "efficiency_std_dev": None,
                "consistency_rating": None,
                "best_workstation": None,
                "worst_workstation": None,
                "efficiency_trend": "improving" if avg_efficiency > 75 else "stable" if avg_efficiency > 60 else "declining",
                "efficiency_data_note": _(
                    "Per-workstation efficiency variance and best/worst "
                    "ranking require workstation capacity data not sourced "
                    "yet; see workstation_performance for actual hours worked."
                ),
            }

        except Exception as e:
            logger.error(f"Error analyzing efficiency: {e}")
            return {"error": str(e)}
    
    def _analyze_capacity(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze capacity utilization and planning.

        Utilization needs a capacity (available working minutes) denominator
        per workstation. Only actual time worked (Job Card
        `actual_operating_time`, collected as `total_minutes`) is sourced;
        no workstation capacity/available-hours source is wired in, so a
        utilization percentage would be fabricated. Honest stub instead,
        matching the OEE availability gap in `_calculate_oee`. The real
        signal that does exist -- total hours actually worked -- is still
        surfaced.
        """
        try:
            workstation_util = production_data.get("workstation_utilization", [])

            if not workstation_util:
                return {"message": _("No workstation capacity data available")}

            total_worked_mins = sum(ws.get("total_minutes", 0) or 0 for ws in workstation_util)

            return {
                "overall_utilization_pct": None,
                "available_capacity_pct": None,
                "available_capacity_hours": None,
                "capacity_constrained_stations": None,
                "underutilized_stations": None,
                "capacity_planning_status": None,
                "total_worked_hours": round(total_worked_mins / 60, 1),
                "workstation_count": len(workstation_util),
                "capacity_data_note": _(
                    "Capacity utilization requires each workstation's available "
                    "working hours, which is not sourced yet; only actual time "
                    "worked is measured."
                ),
            }

        except Exception as e:
            logger.error(f"Error analyzing capacity: {e}")
            return {"error": str(e)}

    def _analyze_workstations(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze individual workstation activity.

        Reports actual time worked and job count per workstation (real,
        from Job Card). Utilization percentage and "optimal/overloaded"
        status are not computed here: both require a capacity/available-
        hours denominator that isn't sourced yet (see `_analyze_capacity`).
        """
        try:
            workstation_util = production_data.get("workstation_utilization", [])

            if not workstation_util:
                return {"message": _("No workstation performance data available")}

            workstation_metrics = []
            for ws in workstation_util:
                minutes = ws.get("total_minutes", 0) or 0
                workstation_metrics.append({
                    "workstation": ws.get("workstation", "Unknown"),
                    "job_count": ws.get("job_count", 0) or 0,
                    "worked_hours": round(minutes / 60, 1),
                    "utilization_pct": None,
                    "status": None,
                })

            # Sort by actual time worked -- the only real signal available.
            workstation_metrics.sort(key=lambda x: x["worked_hours"], reverse=True)

            return {
                "workstation_count": len(workstation_metrics),
                "workstation_performance": workstation_metrics,
                "top_performer": workstation_metrics[0]["workstation"] if workstation_metrics else "N/A",
                "bottom_performer": workstation_metrics[-1]["workstation"] if workstation_metrics else "N/A",
                "capacity_data_note": _(
                    "Ranked by actual hours worked; utilization percentage "
                    "requires workstation capacity data not sourced yet."
                ),
            }

        except Exception as e:
            logger.error(f"Error analyzing workstations: {e}")
            return {"error": str(e)}

    def _identify_bottlenecks(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Identify production bottlenecks.

        Bottleneck severity here was based on utilization vs. capacity
        (>80%/>90% thresholds), which needs workstation available-hours
        data not sourced yet (see `_analyze_capacity`). Honest stub instead
        of a fabricated severity ranking.
        """
        try:
            workstation_util = production_data.get("workstation_utilization", [])

            if not workstation_util:
                return {"message": _("No data available for bottleneck analysis")}

            return {
                "bottleneck_count": None,
                "bottlenecks": [],
                "priority_bottleneck": None,
                "total_improvement_hours": None,
                "bottleneck_data_note": _(
                    "Bottleneck severity is based on utilization vs. capacity, "
                    "which is not sourced yet; see workstation_performance for "
                    "actual hours worked per workstation."
                ),
            }

        except Exception as e:
            logger.error(f"Error identifying bottlenecks: {e}")
            return {"error": str(e)}
    
    def _analyze_production_costs(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze production costs.

        Not computed: there is no real per-unit costing source wired here
        (no Job Card operating-cost or BOM valuation query). This used to
        multiply produced qty by hardcoded $15/$25-per-unit estimates --
        a plausible-looking but fabricated dollar figure once qty is real.
        Honest stub instead, matching quality_metrics/oee_analysis above.
        """
        try:
            return {
                "total_production_cost": None,
                "cost_per_unit": None,
                "labor_cost_pct": None,
                "material_cost_pct": None,
                "overhead_cost_pct": None,
                "cost_efficiency": None,
                "cost_data_note": _(
                    "Production costing requires real per-unit cost data (Job Card "
                    "operating cost or BOM valuation), which is not sourced yet."
                ),
            }
        except Exception as e:
            logger.error(f"Error analyzing production costs: {e}")
            return {"error": str(e)}
    
    def _forecast_production(self, production_data: Dict[str, Any]) -> Dict[str, Any]:
        """Forecast future production based on trends"""
        import numpy as np
        try:
            monthly_trend = production_data.get("monthly_trend", [])
            
            if len(monthly_trend) < 3:
                return {"message": _("Insufficient data for production forecasting")}
            
            # Calculate simple trend
            quantities = [month.get("produced_qty", 0) for month in monthly_trend[-6:]]  # Last 6 months
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
        """Analyze maintenance needs based on utilization.

        Maintenance priority here was derived entirely from a utilization
        percentage that requires capacity data not sourced yet (see
        `_analyze_capacity`), on top of an "utilization / 20" hours
        estimate that was itself a fabricated rough guess. Honest stub
        instead of compounding two fabricated numbers.
        """
        try:
            workstation_util = production_data.get("workstation_utilization", [])

            if not workstation_util:
                return {"message": _("No workstation data for maintenance analysis")}

            return {
                "maintenance_requirements": [],
                "high_priority_count": None,
                "total_maintenance_hours": None,
                "maintenance_urgency": None,
                "maintenance_data_note": _(
                    "Maintenance priority requires utilization vs. capacity "
                    "and real maintenance-hours estimates, neither of which "
                    "is sourced yet."
                ),
            }

        except Exception as e:
            logger.error(f"Error analyzing maintenance needs: {e}")
            return {"error": str(e)}
    
    def _generate_manufacturing_recommendations(self, production_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate actionable manufacturing recommendations.

        Only emit findings the underlying `production_data` actually supports.
        Previously this method (a) computed completion_rate with
        `max(total_orders, 1)` so a 0-order site yielded 0.0% and then
        emitted a high-priority "below target" alert — pure noise on a
        site that doesn't track Work Orders, which the live jkm site is
        today (zero Work Order / Job Card / BOM rows), and (b) appended an
        unconditional "Implement Quality Monitoring" recommendation on
        every call regardless of data (static template, not driven by
        anything in `production_data`). Both now gate on having real
        underlying data: a recommendation only fires when its source
        signal exists and meaningfully deviates.
        """
        try:
            recommendations = []
            work_order_summary = production_data.get("work_order_summary", {})

            total_orders = int(work_order_summary.get("total_orders") or 0)
            completed_orders = int(work_order_summary.get("completed_orders") or 0)

            # Only fire a completion-rate finding when there's a real
            # Work Order population to evaluate; a 0/0 site should not
            # get a "0.0% is below target" alert -- it's a different
            # problem (no production data, not a 0% completion rate).
            if total_orders > 0:
                completion_rate = (completed_orders / total_orders * 100)
                if completion_rate < 80:
                    recommendations.append({
                        "priority": "high",
                        "category": "Production Efficiency",
                        "title": "Improve Work Order Completion Rate",
                        "description": f"Current completion rate of {completion_rate:.1f}% is below target.",
                        "actions": ["Review scheduling process", "Identify bottlenecks", "Improve resource allocation"]
                    })

            # Quality improvement recommendation -- only fire if there's
            # a real production data source to act on. Without any
            # Work Orders, recommending SPC installation is pure
            # boilerplate that doesn't reflect anything in `production_data`.
            quality_metrics = production_data.get("quality_metrics", {}) or {}
            has_quality_data = (
                total_orders > 0
                or bool(production_data.get("workstation_utilization"))
                or any(quality_metrics.get(k) is not None for k in ("first_pass_yield_pct", "defect_rate_ppm"))
            )
            if has_quality_data:
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