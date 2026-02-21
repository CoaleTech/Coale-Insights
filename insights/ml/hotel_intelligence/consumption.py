# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Hotel Intelligence - Consumption Forecasting

Predicts F&B inventory needs based on:
- Forecasted occupancy (from RoomDemandForecasting)
- Historical per-guest consumption patterns
- Meal plan distribution from Hotel Reservation
- Day-of-week consumption variation

Outputs:
- Expected consumption per ingredient for next N days
- Meal plan adjusted predictions
- Per-item daily forecast
- Procurement suggestions
"""

import frappe
from frappe.utils import nowdate, getdate
from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import defaultdict

import numpy as np

from insights.api.ml import parse_date_filter
from . import data as hotel_data


class ConsumptionForecasting:
    """Predicts F&B inventory needs based on occupancy and historical patterns."""

    def __init__(self, date_filter: str = '12m'):
        self.date_filter = date_filter
        start, end = parse_date_filter(date_filter)
        self.start_date = start.strftime('%Y-%m-%d') if start else '2020-01-01'
        self.end_date = end.strftime('%Y-%m-%d') if end else nowdate()

    def compute(self, forecast_days: int = 14) -> Dict[str, Any]:
        """Run consumption forecast and return results."""
        rooms = hotel_data.get_rooms()
        reservations = hotel_data.get_reservations(self.start_date, self.end_date)
        restaurant_items = hotel_data.get_restaurant_order_items(self.start_date, self.end_date)
        restaurant_orders = hotel_data.get_restaurant_orders(self.start_date, self.end_date)

        if not rooms or not restaurant_items:
            return self._empty_result()

        # Compute historical avg consumption per guest per day
        per_guest_consumption = self._compute_per_guest_consumption(
            reservations, restaurant_items, restaurant_orders
        )

        # Meal plan distribution
        meal_plan_dist = self._compute_meal_plan_distribution(reservations)

        # Forecast guest counts for next N days
        guest_forecast = self._forecast_guest_counts(rooms, reservations, forecast_days)

        # Generate item-level consumption forecast
        item_forecast = self._generate_item_forecast(
            per_guest_consumption, guest_forecast, meal_plan_dist
        )

        # Procurement suggestions
        procurement = self._generate_procurement_suggestions(item_forecast)

        return {
            "status": "success",
            "forecast_days": forecast_days,
            "per_guest_consumption": per_guest_consumption[:20],  # Top 20 items
            "meal_plan_distribution": meal_plan_dist,
            "guest_forecast": guest_forecast,
            "item_forecast": item_forecast[:30],  # Top 30 items
            "procurement_suggestions": procurement[:20],  # Top 20
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "status": "no_data",
            "per_guest_consumption": [],
            "meal_plan_distribution": [],
            "guest_forecast": [],
            "item_forecast": [],
            "procurement_suggestions": [],
        }

    # ------------------------------------------------------------------
    # Per-Guest Consumption
    # ------------------------------------------------------------------

    def _compute_per_guest_consumption(
        self,
        reservations: List[Dict],
        restaurant_items: List[Dict],
        restaurant_orders: List[Dict],
    ) -> List[Dict]:
        """
        Compute average consumption per guest per day for each menu item.
        Uses: total qty sold / total guest-days in the period.
        """
        # Total guest-days: sum of (adults + children) * nights for all reservations
        total_guest_days = 0
        for r in reservations:
            adults = int(r.get("adults") or 1)
            children = int(r.get("children") or 0)
            nights = int(r.get("nights") or 1)
            if r.get("status") in ("Checked In", "Checked Out", "Check In Arrival"):
                total_guest_days += (adults + children) * nights

        if total_guest_days == 0:
            # Fallback: estimate from restaurant order count
            total_days = max(
                (datetime.strptime(self.end_date, '%Y-%m-%d') -
                 datetime.strptime(self.start_date, '%Y-%m-%d')).days, 1
            )
            total_guest_days = len(restaurant_orders) * 2  # Rough estimate: 2 covers per order

        if total_guest_days == 0:
            return []

        # Aggregate item consumption
        item_totals = defaultdict(lambda: {"qty": 0, "amount": 0, "order_count": 0})
        for item in restaurant_items:
            key = item.get("item_code") or item.get("item_name")
            if not key:
                continue
            item_totals[key]["qty"] += float(item.get("qty") or 0)
            item_totals[key]["amount"] += float(item.get("amount") or 0)
            item_totals[key]["order_count"] += 1
            item_totals[key]["item_name"] = item.get("item_name") or key
            item_totals[key]["item_group"] = item.get("item_group") or ""

        result = []
        for item_code, stats in item_totals.items():
            qty_per_guest_day = stats["qty"] / total_guest_days
            result.append({
                "item_code": item_code,
                "item_name": stats["item_name"],
                "item_group": stats["item_group"],
                "total_qty": round(stats["qty"], 2),
                "total_amount": round(stats["amount"], 2),
                "qty_per_guest_day": round(qty_per_guest_day, 4),
                "daily_avg": round(stats["qty"] / max(
                    (datetime.strptime(self.end_date, '%Y-%m-%d') -
                     datetime.strptime(self.start_date, '%Y-%m-%d')).days, 1
                ), 2),
            })

        # Sort by qty_per_guest_day descending
        result.sort(key=lambda x: x["qty_per_guest_day"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # Meal Plan Distribution
    # ------------------------------------------------------------------

    def _compute_meal_plan_distribution(self, reservations: List[Dict]) -> List[Dict]:
        """
        Distribution of meal plans from Hotel Reservation.meal_plan field.
        Common values: Room Only, B&B, Half Board, Full Board.
        """
        plan_counts = defaultdict(int)
        total = 0

        for r in reservations:
            plan = r.get("meal_plan") or "Room Only"
            if r.get("status") not in ("Cancelled",):
                plan_counts[plan] += 1
                total += 1

        # Meal multipliers: how much F&B consumption relative to Full Board
        meal_multipliers = {
            "Room Only": 0.3,      # Only a la carte / minibar
            "Bed and Breakfast": 0.5,  # Breakfast included
            "B&B": 0.5,
            "Half Board": 0.7,     # Breakfast + lunch or dinner
            "Full Board": 1.0,     # All meals
            "All Inclusive": 1.2,   # All meals + snacks/drinks
        }

        result = []
        for plan, count in sorted(plan_counts.items(), key=lambda x: x[1], reverse=True):
            # Match meal multiplier (fuzzy)
            multiplier = 0.5  # default
            for key, mult in meal_multipliers.items():
                if key.lower() in plan.lower():
                    multiplier = mult
                    break

            result.append({
                "meal_plan": plan,
                "count": count,
                "percentage": round(count / total * 100, 1) if total else 0,
                "consumption_multiplier": multiplier,
            })

        return result

    # ------------------------------------------------------------------
    # Guest Count Forecast
    # ------------------------------------------------------------------

    def _forecast_guest_counts(
        self, rooms: List[Dict], reservations: List[Dict], forecast_days: int
    ) -> List[Dict]:
        """
        Forecast guest counts for next N days based on:
        - Current confirmed/checked-in reservations
        - Historical average for unbooked days
        """
        today = getdate(nowdate())
        total_rooms = len([
            r for r in rooms if r.get("status") not in ("Out of Order", "Maintenance")
        ])

        # Historical avg guests per day
        hist_guest_days = []
        for r in reservations:
            adults = int(r.get("adults") or 1)
            children = int(r.get("children") or 0)
            if r.get("status") in ("Checked In", "Checked Out", "Check In Arrival"):
                hist_guest_days.append(adults + children)

        avg_guests_per_reservation = np.mean(hist_guest_days) if hist_guest_days else 2

        forecast = []
        for i in range(forecast_days):
            target_date = today + timedelta(days=i)
            date_str = target_date.strftime('%Y-%m-%d')

            # Count confirmed/checked-in reservations for this date
            confirmed_guests = 0
            confirmed_reservations = 0
            for r in reservations:
                arrival = str(r.get("arrival_date") or "")
                departure = str(r.get("departure_date") or "")
                status = r.get("status") or ""
                if (status in ("Confirmed", "Checked In", "Check In Arrival")
                        and arrival <= date_str < departure):
                    confirmed_reservations += 1
                    confirmed_guests += int(r.get("adults") or 1) + int(r.get("children") or 0)

            # Estimate additional walk-ins/unbooked based on historical patterns
            estimated_additional = max(0, round(
                avg_guests_per_reservation * 0.1 * total_rooms  # ~10% walk-in factor
            )) if i > 3 else 0  # Only add walk-in buffer for dates > 3 days out

            total_guests = confirmed_guests + estimated_additional

            forecast.append({
                "date": date_str,
                "day_name": target_date.strftime('%A'),
                "confirmed_guests": confirmed_guests,
                "confirmed_reservations": confirmed_reservations,
                "estimated_additional": estimated_additional,
                "total_forecast_guests": total_guests,
            })

        return forecast

    # ------------------------------------------------------------------
    # Item-Level Consumption Forecast
    # ------------------------------------------------------------------

    def _generate_item_forecast(
        self,
        per_guest_consumption: List[Dict],
        guest_forecast: List[Dict],
        meal_plan_dist: List[Dict],
    ) -> List[Dict]:
        """Generate per-item consumption forecast for the forecast period."""
        if not per_guest_consumption or not guest_forecast:
            return []

        # Weighted meal plan consumption multiplier
        weighted_multiplier = 0
        total_weight = 0
        for mp in meal_plan_dist:
            weighted_multiplier += mp["consumption_multiplier"] * mp["count"]
            total_weight += mp["count"]
        avg_meal_multiplier = weighted_multiplier / total_weight if total_weight else 0.5

        # Total forecasted guest-days
        total_forecast_guests = sum(g["total_forecast_guests"] for g in guest_forecast)

        result = []
        for item in per_guest_consumption:
            qty_per_guest = item["qty_per_guest_day"]
            if qty_per_guest <= 0:
                continue

            # Adjusted for meal plan mix
            adjusted_qty = qty_per_guest * avg_meal_multiplier
            forecast_qty = round(adjusted_qty * total_forecast_guests, 2)

            if forecast_qty < 0.1:
                continue

            # Daily breakdown
            daily = []
            for g in guest_forecast:
                day_qty = round(adjusted_qty * g["total_forecast_guests"], 2)
                daily.append({
                    "date": g["date"],
                    "forecast_qty": day_qty,
                })

            result.append({
                "item_code": item["item_code"],
                "item_name": item["item_name"],
                "item_group": item["item_group"],
                "qty_per_guest_day": round(adjusted_qty, 4),
                "total_forecast_qty": forecast_qty,
                "forecast_days": len(guest_forecast),
                "daily_avg_forecast": round(forecast_qty / len(guest_forecast), 2),
                "daily_breakdown": daily,
            })

        # Sort by total_forecast_qty descending
        result.sort(key=lambda x: x["total_forecast_qty"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # Procurement Suggestions
    # ------------------------------------------------------------------

    def _generate_procurement_suggestions(
        self, item_forecast: List[Dict]
    ) -> List[Dict]:
        """Generate procurement suggestions based on consumption forecast."""
        suggestions = []

        for item in item_forecast:
            total_qty = item["total_forecast_qty"]
            if total_qty <= 0:
                continue

            # Get current stock if available
            try:
                bin_data = frappe.db.sql("""
                    SELECT SUM(actual_qty) as stock
                    FROM `tabBin`
                    WHERE item_code = %s
                """, item["item_code"], as_dict=True)
                current_stock = float(bin_data[0].get("stock") or 0) if bin_data else 0
            except Exception:
                current_stock = 0

            # Safety buffer: 20% over forecast
            required = round(total_qty * 1.2, 2)
            shortfall = max(0, round(required - current_stock, 2))

            if shortfall > 0 or current_stock < total_qty:
                urgency = "high" if current_stock < total_qty * 0.3 else (
                    "medium" if current_stock < total_qty else "low"
                )

                suggestions.append({
                    "item_code": item["item_code"],
                    "item_name": item["item_name"],
                    "item_group": item["item_group"],
                    "forecast_qty": total_qty,
                    "current_stock": current_stock,
                    "required_qty": required,
                    "shortfall": shortfall,
                    "urgency": urgency,
                    "days_of_stock": round(
                        current_stock / item["daily_avg_forecast"], 1
                    ) if item["daily_avg_forecast"] > 0 else 999,
                })

        # Sort by urgency then shortfall
        urgency_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda x: (urgency_order.get(x["urgency"], 3), -x["shortfall"]))
        return suggestions
