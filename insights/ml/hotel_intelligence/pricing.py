# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Hotel Intelligence - Dynamic Pricing Suggestions

Analyzes historical demand patterns, occupancy rates, and revenue data
to suggest optimal room rates by room type and date.

Outputs:
- Pricing recommendations per room type
- Demand-based rate multipliers
- Day-of-week pricing patterns
- Revenue optimization opportunities
"""

import frappe
from frappe.utils import nowdate, getdate
from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import defaultdict

import numpy as np

from insights.api.ml import parse_date_filter
from . import data as hotel_data


class DynamicPricing:
    """Suggests optimal room rates based on demand, occupancy, and seasonality."""

    def __init__(self, date_filter: str = '12m'):
        self.date_filter = date_filter
        start, end = parse_date_filter(date_filter)
        self.start_date = start.strftime('%Y-%m-%d') if start else '2020-01-01'
        self.end_date = end.strftime('%Y-%m-%d') if end else nowdate()

    def compute(self, forecast_days: int = 14) -> Dict[str, Any]:
        """Run pricing analysis and return recommendations."""
        rooms = hotel_data.get_rooms()
        reservations = hotel_data.get_reservations(self.start_date, self.end_date)
        reservation_rooms = hotel_data.get_reservation_rooms(self.start_date, self.end_date)

        if not rooms or not reservations:
            return self._empty_result()

        # Current base rates by room type
        base_rates = self._get_base_rates(rooms)

        # Historical rate and occupancy by room type
        historical = self._analyze_historical_rates(reservations, reservation_rooms)

        # Day-of-week demand patterns
        dow_patterns = self._compute_dow_demand(reservations)

        # Generate pricing recommendations for next N days
        recommendations = self._generate_recommendations(
            base_rates, historical, dow_patterns, forecast_days, rooms
        )

        # Revenue optimization opportunities
        opportunities = self._find_opportunities(base_rates, historical)

        return {
            "status": "success",
            "base_rates": base_rates,
            "historical_analysis": historical,
            "dow_patterns": dow_patterns,
            "recommendations": recommendations,
            "opportunities": opportunities,
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "status": "no_data",
            "base_rates": [],
            "historical_analysis": [],
            "dow_patterns": [],
            "recommendations": [],
            "opportunities": [],
        }

    # ------------------------------------------------------------------
    # Base Rates
    # ------------------------------------------------------------------

    def _get_base_rates(self, rooms: List[Dict]) -> List[Dict]:
        """Get current base rate per room type from Hotel Room records."""
        type_rates = defaultdict(list)
        for r in rooms:
            rt = r.get("room_type") or "Unknown"
            rate = float(r.get("base_rate") or r.get("room_rate") or 0)
            if rate > 0:
                type_rates[rt].append(rate)

        result = []
        for rt, rates in sorted(type_rates.items()):
            result.append({
                "room_type": rt,
                "base_rate": round(np.mean(rates), 2),
                "min_rate": round(min(rates), 2),
                "max_rate": round(max(rates), 2),
                "room_count": len(rates),
            })

        return result

    # ------------------------------------------------------------------
    # Historical Rate Analysis
    # ------------------------------------------------------------------

    def _analyze_historical_rates(
        self, reservations: List[Dict], reservation_rooms: List[Dict]
    ) -> List[Dict]:
        """Analyze historical achieved rates vs base rates."""
        type_data = defaultdict(lambda: {"rates": [], "occupancy_days": 0, "revenue": 0})

        # From reservation rooms (more granular)
        if reservation_rooms:
            for rr in reservation_rooms:
                rt = rr.get("room_type") or "Unknown"
                rate = float(rr.get("room_rate") or 0)
                if rate > 0:
                    type_data[rt]["rates"].append(rate)
                    type_data[rt]["revenue"] += rate * int(rr.get("nights") or 1)
                    type_data[rt]["occupancy_days"] += int(rr.get("nights") or 1)
        else:
            # Fallback to reservation level
            for r in reservations:
                rt = r.get("room_type") or "Unknown"
                rate = float(r.get("room_rate") or 0)
                nights = int(r.get("nights") or 1)
                if rate > 0:
                    type_data[rt]["rates"].append(rate)
                    type_data[rt]["revenue"] += float(r.get("total_amount") or 0)
                    type_data[rt]["occupancy_days"] += nights

        result = []
        for rt, stats in sorted(type_data.items()):
            rates = stats["rates"]
            if not rates:
                continue
            result.append({
                "room_type": rt,
                "avg_achieved_rate": round(np.mean(rates), 2),
                "median_rate": round(float(np.median(rates)), 2),
                "min_achieved": round(min(rates), 2),
                "max_achieved": round(max(rates), 2),
                "total_revenue": round(stats["revenue"], 2),
                "room_nights": stats["occupancy_days"],
                "rate_std_dev": round(float(np.std(rates)), 2),
            })

        return result

    # ------------------------------------------------------------------
    # Day-of-Week Demand Patterns
    # ------------------------------------------------------------------

    def _compute_dow_demand(self, reservations: List[Dict]) -> List[Dict]:
        """Compute average demand by day of week."""
        dow_counts = defaultdict(list)

        # Count reservations overlapping each day-of-week
        for r in reservations:
            arrival = r.get("arrival_date")
            departure = r.get("departure_date")
            if not arrival or not departure:
                continue
            try:
                start = getdate(str(arrival))
                end = getdate(str(departure))
                current = start
                while current < end:
                    dow_counts[current.weekday()].append(1)
                    current += timedelta(days=1)
            except (ValueError, TypeError):
                continue

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        overall_avg = sum(len(v) for v in dow_counts.values()) / 7 if dow_counts else 1

        result = []
        for dow in range(7):
            count = len(dow_counts.get(dow, []))
            demand_index = round(count / overall_avg, 2) if overall_avg else 1.0
            result.append({
                "day": day_names[dow],
                "day_of_week": dow,
                "room_nights": count,
                "demand_index": demand_index,  # >1 = high demand, <1 = low demand
                "suggested_multiplier": self._demand_to_multiplier(demand_index),
            })

        return result

    def _demand_to_multiplier(self, demand_index: float) -> float:
        """Convert demand index to rate multiplier."""
        if demand_index >= 1.3:
            return 1.15  # 15% premium
        elif demand_index >= 1.1:
            return 1.08  # 8% premium
        elif demand_index >= 0.9:
            return 1.00  # standard rate
        elif demand_index >= 0.7:
            return 0.92  # 8% discount
        else:
            return 0.85  # 15% discount

    # ------------------------------------------------------------------
    # Pricing Recommendations
    # ------------------------------------------------------------------

    def _generate_recommendations(
        self,
        base_rates: List[Dict],
        historical: List[Dict],
        dow_patterns: List[Dict],
        forecast_days: int,
        rooms: List[Dict],
    ) -> List[Dict]:
        """Generate pricing recommendations for next N days."""
        # Build lookup maps
        base_rate_map = {r["room_type"]: r["base_rate"] for r in base_rates}
        dow_multiplier_map = {d["day_of_week"]: d["suggested_multiplier"] for d in dow_patterns}

        # Get current occupancy to assess demand pressure
        total_sellable = len([
            r for r in rooms if r.get("status") not in ("Out of Order", "Maintenance")
        ])
        current_occupied = len([
            r for r in rooms if r.get("status") in ("Occupied", "Partially Occupied")
        ])
        current_occ_rate = current_occupied / total_sellable if total_sellable else 0

        # Occupancy-based multiplier
        if current_occ_rate >= 0.9:
            occ_multiplier = 1.20  # Very high demand
        elif current_occ_rate >= 0.75:
            occ_multiplier = 1.10  # High demand
        elif current_occ_rate >= 0.5:
            occ_multiplier = 1.00  # Normal
        elif current_occ_rate >= 0.3:
            occ_multiplier = 0.90  # Low demand
        else:
            occ_multiplier = 0.80  # Very low demand

        today = getdate(nowdate())
        recommendations = []

        for i in range(forecast_days):
            target_date = today + timedelta(days=i)
            dow = target_date.weekday()
            dow_mult = dow_multiplier_map.get(dow, 1.0)

            day_recs = []
            for rt, base in base_rate_map.items():
                combined_mult = dow_mult * occ_multiplier
                suggested = round(base * combined_mult, 2)

                day_recs.append({
                    "room_type": rt,
                    "base_rate": base,
                    "suggested_rate": suggested,
                    "multiplier": round(combined_mult, 2),
                    "change_pct": round((combined_mult - 1) * 100, 1),
                })

            recommendations.append({
                "date": target_date.strftime('%Y-%m-%d'),
                "day_name": target_date.strftime('%A'),
                "dow_multiplier": dow_mult,
                "occupancy_multiplier": occ_multiplier,
                "room_types": day_recs,
            })

        return recommendations

    # ------------------------------------------------------------------
    # Revenue Opportunities
    # ------------------------------------------------------------------

    def _find_opportunities(
        self, base_rates: List[Dict], historical: List[Dict]
    ) -> List[Dict]:
        """Identify revenue optimization opportunities."""
        opportunities = []
        historical_map = {h["room_type"]: h for h in historical}

        for br in base_rates:
            rt = br["room_type"]
            hist = historical_map.get(rt)
            if not hist:
                continue

            avg_achieved = hist["avg_achieved_rate"]
            base = br["base_rate"]

            # Opportunity: consistently achieving above base rate
            if avg_achieved > base * 1.05:
                opportunities.append({
                    "room_type": rt,
                    "type": "rate_increase",
                    "message": f"Average achieved rate ({avg_achieved:,.0f}) is {((avg_achieved/base - 1)*100):.0f}% above base rate ({base:,.0f}). Consider increasing base rate.",
                    "current_base": base,
                    "suggested_base": round(avg_achieved * 0.95, 2),  # Suggest 95% of avg achieved
                    "potential_impact_per_night": round(avg_achieved * 0.95 - base, 2),
                })

            # Opportunity: high rate variance suggests dynamic pricing potential
            if hist["rate_std_dev"] > base * 0.2:
                opportunities.append({
                    "room_type": rt,
                    "type": "dynamic_pricing",
                    "message": f"High rate variance ({hist['rate_std_dev']:,.0f}) for {rt}. Dynamic pricing could optimize revenue.",
                    "rate_range": f"{hist['min_achieved']:,.0f} - {hist['max_achieved']:,.0f}",
                    "std_dev": hist["rate_std_dev"],
                })

        return opportunities
