# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Hotel Intelligence - Room Demand Forecasting

Predicts future room demand using historical reservation data.
Uses Holt-Winters exponential smoothing for seasonal patterns.

Outputs:
- Daily occupancy forecast for next N days
- Demand by room type
- Seasonal patterns (day-of-week, monthly)
- Booking pace analysis
"""

import frappe
from frappe.utils import nowdate, getdate, add_days
from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import defaultdict

import numpy as np

from insights.api.ml import parse_date_filter
from . import data as hotel_data


class RoomDemandForecasting:
    """Forecasts room demand using historical reservation patterns."""

    def __init__(self, date_filter: str = '12m'):
        self.date_filter = date_filter
        start, end = parse_date_filter(date_filter)
        self.start_date = start.strftime('%Y-%m-%d') if start else '2020-01-01'
        self.end_date = end.strftime('%Y-%m-%d') if end else nowdate()

    def compute(self, forecast_days: int = 30) -> Dict[str, Any]:
        """Run demand forecast and return results."""
        rooms = hotel_data.get_rooms()
        reservations = hotel_data.get_reservations(self.start_date, self.end_date)

        if not rooms or not reservations:
            return self._empty_result()

        total_rooms = len([
            r for r in rooms
            if r.get("status") not in ("Out of Order", "Maintenance")
        ])

        # Build historical daily occupancy series
        daily_series = self._build_daily_series(total_rooms)

        if len(daily_series) < 14:
            return {
                "status": "insufficient_data",
                "message": f"Need at least 14 days of data, have {len(daily_series)}",
                "forecast": [],
                "seasonal_patterns": {},
                "booking_pace": {},
            }

        # Forecast using exponential smoothing
        forecast = self._forecast_occupancy(daily_series, forecast_days, total_rooms)

        # Seasonal patterns
        seasonal = self._compute_seasonal_patterns(daily_series)

        # Demand by room type
        by_room_type = self._compute_demand_by_room_type(reservations, rooms)

        # Booking pace (lead time analysis)
        booking_pace = self._compute_booking_pace(reservations)

        return {
            "status": "success",
            "total_rooms": total_rooms,
            "historical_days": len(daily_series),
            "forecast_days": forecast_days,
            "forecast": forecast,
            "seasonal_patterns": seasonal,
            "demand_by_room_type": by_room_type,
            "booking_pace": booking_pace,
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "status": "no_data",
            "forecast": [],
            "seasonal_patterns": {},
            "demand_by_room_type": [],
            "booking_pace": {},
        }

    # ------------------------------------------------------------------
    # Build daily occupancy time series
    # ------------------------------------------------------------------

    def _build_daily_series(self, total_rooms: int) -> List[Dict]:
        """Build daily occupied room count from reservation overlaps."""
        start = datetime.strptime(self.start_date, '%Y-%m-%d').date()
        end = datetime.strptime(self.end_date, '%Y-%m-%d').date()
        today = getdate(nowdate())

        # Don't include future dates in historical data
        if end > today:
            end = today

        series = []
        current = start
        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            overlapping = hotel_data.get_reservations_for_date(date_str)
            occupied = sum(int(r.get("total_rooms") or 1) for r in overlapping)
            occ_rate = min(occupied / total_rooms * 100, 100) if total_rooms else 0

            series.append({
                "date": date_str,
                "occupied": min(occupied, total_rooms),
                "occupancy_rate": round(occ_rate, 1),
                "day_of_week": current.weekday(),  # 0=Monday
                "month": current.month,
            })
            current += timedelta(days=1)

        return series

    # ------------------------------------------------------------------
    # Exponential Smoothing Forecast
    # ------------------------------------------------------------------

    def _forecast_occupancy(
        self, daily_series: List[Dict], forecast_days: int, total_rooms: int
    ) -> List[Dict]:
        """
        Simple exponential smoothing with trend (Holt's method).
        Uses day-of-week seasonal adjustment.
        """
        values = [d["occupancy_rate"] for d in daily_series]
        n = len(values)

        # Compute day-of-week averages for seasonal adjustment
        dow_sums = defaultdict(list)
        for d in daily_series:
            dow_sums[d["day_of_week"]].append(d["occupancy_rate"])
        dow_avg = {dow: np.mean(vals) for dow, vals in dow_sums.items()}
        overall_avg = np.mean(values) if values else 0

        # Seasonal indices (multiplicative)
        seasonal_idx = {}
        for dow in range(7):
            if dow in dow_avg and overall_avg > 0:
                seasonal_idx[dow] = dow_avg[dow] / overall_avg
            else:
                seasonal_idx[dow] = 1.0

        # Holt's method parameters
        alpha = 0.3  # level smoothing
        beta = 0.1   # trend smoothing

        # Initialize
        level = values[0]
        trend = (values[-1] - values[0]) / max(n - 1, 1)

        # Fit to historical data
        for i in range(1, n):
            new_level = alpha * values[i] + (1 - alpha) * (level + trend)
            new_trend = beta * (new_level - level) + (1 - beta) * trend
            level = new_level
            trend = new_trend

        # Generate forecast
        today = getdate(nowdate())
        forecast = []
        for i in range(1, forecast_days + 1):
            target_date = today + timedelta(days=i)
            dow = target_date.weekday()

            # Base forecast
            base = level + trend * i
            # Apply seasonal adjustment
            adjusted = base * seasonal_idx.get(dow, 1.0)
            # Clamp to 0-100
            adjusted = max(0, min(100, adjusted))

            # Confidence interval widens with forecast horizon
            margin = min(15, 5 + i * 0.3)  # starts at ~5%, grows slowly

            forecast.append({
                "date": target_date.strftime('%Y-%m-%d'),
                "day_of_week": dow,
                "day_name": target_date.strftime('%A'),
                "forecast_occupancy": round(adjusted, 1),
                "forecast_rooms": round(adjusted / 100 * total_rooms),
                "lower_bound": round(max(0, adjusted - margin), 1),
                "upper_bound": round(min(100, adjusted + margin), 1),
            })

        return forecast

    # ------------------------------------------------------------------
    # Seasonal Patterns
    # ------------------------------------------------------------------

    def _compute_seasonal_patterns(self, daily_series: List[Dict]) -> Dict[str, Any]:
        """Compute day-of-week and monthly seasonal patterns."""
        # Day of week
        dow_data = defaultdict(list)
        for d in daily_series:
            dow_data[d["day_of_week"]].append(d["occupancy_rate"])

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        by_day_of_week = []
        for dow in range(7):
            vals = dow_data.get(dow, [])
            by_day_of_week.append({
                "day": day_names[dow],
                "day_of_week": dow,
                "avg_occupancy": round(np.mean(vals), 1) if vals else 0,
                "sample_count": len(vals),
            })

        # Monthly
        month_data = defaultdict(list)
        for d in daily_series:
            month_data[d["month"]].append(d["occupancy_rate"])

        month_names = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        by_month = []
        for m in range(1, 13):
            vals = month_data.get(m, [])
            if vals:
                by_month.append({
                    "month": month_names[m],
                    "month_number": m,
                    "avg_occupancy": round(np.mean(vals), 1),
                    "sample_days": len(vals),
                })

        return {
            "by_day_of_week": by_day_of_week,
            "by_month": by_month,
        }

    # ------------------------------------------------------------------
    # Demand by Room Type
    # ------------------------------------------------------------------

    def _compute_demand_by_room_type(
        self, reservations: List[Dict], rooms: List[Dict]
    ) -> List[Dict]:
        """Analyze demand distribution by room type."""
        # Count rooms by type
        room_type_total = defaultdict(int)
        for r in rooms:
            if r.get("status") not in ("Out of Order", "Maintenance"):
                room_type_total[r.get("room_type") or "Unknown"] += 1

        # Count reservations by room type (from reservation_rooms or room_type field)
        reservation_rooms = hotel_data.get_reservation_rooms(self.start_date, self.end_date)
        type_demand = defaultdict(lambda: {"count": 0, "revenue": 0, "nights": 0})

        for rr in reservation_rooms:
            rt = rr.get("room_type") or "Unknown"
            type_demand[rt]["count"] += 1
            type_demand[rt]["revenue"] += float(rr.get("room_rate") or 0)
            type_demand[rt]["nights"] += int(rr.get("nights") or 1)

        # If no reservation_rooms data, fallback to reservation-level
        if not reservation_rooms:
            for r in reservations:
                rt = r.get("room_type") or "Unknown"
                type_demand[rt]["count"] += 1
                type_demand[rt]["revenue"] += float(r.get("total_amount") or 0)
                type_demand[rt]["nights"] += int(r.get("nights") or 1)

        result = []
        total_res = sum(d["count"] for d in type_demand.values())
        for rt, stats in sorted(type_demand.items(), key=lambda x: x[1]["count"], reverse=True):
            inventory = room_type_total.get(rt, 0)
            result.append({
                "room_type": rt,
                "reservation_count": stats["count"],
                "demand_share_pct": round(stats["count"] / total_res * 100, 1) if total_res else 0,
                "total_revenue": round(stats["revenue"], 2),
                "total_nights": stats["nights"],
                "inventory": inventory,
            })

        return result

    # ------------------------------------------------------------------
    # Booking Pace (Lead Time Analysis)
    # ------------------------------------------------------------------

    def _compute_booking_pace(self, reservations: List[Dict]) -> Dict[str, Any]:
        """
        Analyze booking lead times to understand booking pace.
        Lead time = arrival_date - creation_date (when booking was made).
        """
        lead_times = []
        for r in reservations:
            creation = r.get("creation")
            arrival = r.get("arrival_date")
            if creation and arrival:
                try:
                    created = getdate(str(creation)[:10])
                    arrive = getdate(str(arrival))
                    lead = (arrive - created).days
                    if 0 <= lead <= 365:
                        lead_times.append(lead)
                except (ValueError, TypeError):
                    continue

        if not lead_times:
            return {"avg_lead_time": 0, "median_lead_time": 0, "distribution": []}

        lead_arr = np.array(lead_times)

        # Distribution buckets
        buckets = [
            ("Same day", 0, 0),
            ("1-3 days", 1, 3),
            ("4-7 days", 4, 7),
            ("1-2 weeks", 8, 14),
            ("2-4 weeks", 15, 28),
            ("1-3 months", 29, 90),
            ("3+ months", 91, 365),
        ]

        distribution = []
        total = len(lead_times)
        for label, low, high in buckets:
            count = int(np.sum((lead_arr >= low) & (lead_arr <= high)))
            distribution.append({
                "bucket": label,
                "count": count,
                "percentage": round(count / total * 100, 1) if total else 0,
            })

        return {
            "avg_lead_time": round(float(np.mean(lead_arr)), 1),
            "median_lead_time": int(np.median(lead_arr)),
            "min_lead_time": int(np.min(lead_arr)),
            "max_lead_time": int(np.max(lead_arr)),
            "distribution": distribution,
        }
