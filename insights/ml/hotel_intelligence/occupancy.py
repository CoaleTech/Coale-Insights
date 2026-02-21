# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Hotel Intelligence - Occupancy Analytics

Computes:
- Occupancy Rate (room-level and per-bed)
- ADR (Average Daily Rate)
- RevPAR (Revenue Per Available Room)
- Daily occupancy trends
- Occupancy by room type
- Today's snapshot (arrivals, departures, in-house, available)
- Average Length of Stay
"""

import frappe
from frappe.utils import nowdate, getdate, add_days
from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import defaultdict

from insights.api.ml import parse_date_filter
from . import data as hotel_data


class OccupancyAnalytics:
    """Occupancy rate, ADR, RevPAR, and related room metrics."""

    def __init__(self, date_filter: str = '12m'):
        self.date_filter = date_filter
        start, end = parse_date_filter(date_filter)
        self.start_date = start.strftime('%Y-%m-%d') if start else '2020-01-01'
        self.end_date = end.strftime('%Y-%m-%d') if end else nowdate()

    def compute(self) -> Dict[str, Any]:
        """Run all occupancy computations and return aggregated results."""
        rooms = hotel_data.get_rooms()
        reservations = hotel_data.get_reservations(self.start_date, self.end_date)
        reservation_rooms = hotel_data.get_reservation_rooms(self.start_date, self.end_date)

        if not rooms:
            return self._empty_result()

        total_rooms = len(rooms)

        # Current occupancy from room status
        occupancy_rate = self._compute_occupancy_rate(rooms)
        bed_occupancy = self._compute_bed_occupancy(rooms)

        # ADR & RevPAR from checked-out reservations
        adr = self._compute_adr(reservations)
        revpar = round(adr * (occupancy_rate / 100), 2) if occupancy_rate else 0.0

        # Total room revenue from all non-cancelled reservations
        total_room_revenue = sum(
            float(r.get("total_amount") or 0) for r in reservations
        )

        # Today's snapshot
        today_snapshot = self._compute_today_snapshot(rooms, reservations)

        # Occupancy by room type
        by_room_type = self._compute_by_room_type(rooms)

        # Daily occupancy trend (last 30 days)
        daily_trend = self._compute_daily_trend(rooms)

        # Average length of stay
        avg_los = self._compute_avg_length_of_stay(reservations)

        # Housekeeping summary
        housekeeping = self._compute_housekeeping_summary()

        return {
            "occupancy_rate": occupancy_rate,
            "bed_occupancy_rate": bed_occupancy,
            "adr": adr,
            "revpar": revpar,
            "total_rooms": total_rooms,
            "total_room_revenue": round(total_room_revenue, 2),
            "avg_length_of_stay": avg_los,
            "today_snapshot": today_snapshot,
            "by_room_type": by_room_type,
            "daily_trend": daily_trend,
            "housekeeping": housekeeping,
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "occupancy_rate": 0,
            "bed_occupancy_rate": 0,
            "adr": 0,
            "revpar": 0,
            "total_rooms": 0,
            "total_room_revenue": 0,
            "avg_length_of_stay": 0,
            "today_snapshot": {},
            "by_room_type": [],
            "daily_trend": [],
            "housekeeping": {},
        }

    # ------------------------------------------------------------------
    # Occupancy Rate
    # ------------------------------------------------------------------

    def _compute_occupancy_rate(self, rooms: List[Dict]) -> float:
        """
        Occupancy Rate = Rooms with status 'Occupied' or 'Partially Occupied' / Total rooms
        Excludes rooms that are 'Out of Order' or 'Maintenance' from total.
        """
        sellable_rooms = [
            r for r in rooms
            if r.get("status") not in ("Out of Order", "Maintenance")
        ]
        if not sellable_rooms:
            return 0.0

        occupied = sum(
            1 for r in sellable_rooms
            if r.get("status") in ("Occupied", "Partially Occupied")
        )
        return round(occupied / len(sellable_rooms) * 100, 1)

    def _compute_bed_occupancy(self, rooms: List[Dict]) -> float:
        """
        Per-bed occupancy = Total beds_occupied / Total total_beds
        Only for rooms with total_beds > 1 (per-bed mode).
        """
        total_beds = sum(int(r.get("total_beds") or 1) for r in rooms)
        beds_occupied = sum(int(r.get("beds_occupied") or 0) for r in rooms)

        if total_beds == 0:
            return 0.0
        return round(beds_occupied / total_beds * 100, 1)

    # ------------------------------------------------------------------
    # ADR (Average Daily Rate)
    # ------------------------------------------------------------------

    def _compute_adr(self, reservations: List[Dict]) -> float:
        """
        ADR = Total Room Revenue / Number of Room Nights Sold
        Uses checked-out reservations for accuracy.
        """
        checked_out = [
            r for r in reservations
            if r.get("status") == "Checked Out"
        ]
        if not checked_out:
            # Fall back to all non-cancelled reservations if no checkouts yet
            checked_out = [r for r in reservations if r.get("status") != "Cancelled"]

        if not checked_out:
            return 0.0

        total_revenue = sum(float(r.get("total_amount") or 0) for r in checked_out)
        total_nights = sum(int(r.get("nights") or 1) for r in checked_out)

        if total_nights == 0:
            return 0.0
        return round(total_revenue / total_nights, 2)

    # ------------------------------------------------------------------
    # Today's Snapshot
    # ------------------------------------------------------------------

    def _compute_today_snapshot(
        self, rooms: List[Dict], reservations: List[Dict]
    ) -> Dict[str, Any]:
        """
        Today's operational snapshot:
        - arrivals_today: reservations arriving today
        - departures_today: reservations departing today
        - in_house_guests: currently checked-in guest count
        - available_rooms: rooms with status 'Available'
        - occupied_rooms: rooms with status 'Occupied' or 'Partially Occupied'
        - out_of_order: rooms under maintenance/out of order
        """
        today = nowdate()

        arrivals_today = sum(
            1 for r in reservations
            if str(r.get("arrival_date")) == today
        )
        departures_today = sum(
            1 for r in reservations
            if str(r.get("departure_date")) == today
        )

        # In-house guests from checked-in reservations
        in_house = [
            r for r in reservations
            if r.get("status") in ("Checked In", "Check In Arrival")
            and str(r.get("arrival_date")) <= today
            and str(r.get("departure_date")) > today
        ]
        in_house_guests = sum(
            int(r.get("adults") or 0) + int(r.get("children") or 0)
            for r in in_house
        )

        available_rooms = sum(1 for r in rooms if r.get("status") == "Available")
        occupied_rooms = sum(
            1 for r in rooms
            if r.get("status") in ("Occupied", "Partially Occupied")
        )
        out_of_order = sum(
            1 for r in rooms
            if r.get("status") in ("Out of Order", "Maintenance")
        )

        return {
            "arrivals_today": arrivals_today,
            "departures_today": departures_today,
            "in_house_guests": in_house_guests,
            "in_house_reservations": len(in_house),
            "available_rooms": available_rooms,
            "occupied_rooms": occupied_rooms,
            "out_of_order": out_of_order,
        }

    # ------------------------------------------------------------------
    # Occupancy by Room Type
    # ------------------------------------------------------------------

    def _compute_by_room_type(self, rooms: List[Dict]) -> List[Dict]:
        """Breakdown of occupancy per room type."""
        type_stats = defaultdict(lambda: {"total": 0, "occupied": 0, "available": 0})

        for r in rooms:
            rt = r.get("room_type") or "Unknown"
            status = r.get("status")

            if status in ("Out of Order", "Maintenance"):
                continue

            type_stats[rt]["total"] += 1
            if status in ("Occupied", "Partially Occupied"):
                type_stats[rt]["occupied"] += 1
            elif status == "Available":
                type_stats[rt]["available"] += 1

        result = []
        for rt, stats in sorted(type_stats.items()):
            total = stats["total"]
            occupied = stats["occupied"]
            result.append({
                "room_type": rt,
                "total_rooms": total,
                "occupied": occupied,
                "available": stats["available"],
                "occupancy_rate": round(occupied / total * 100, 1) if total else 0,
            })

        return result

    # ------------------------------------------------------------------
    # Daily Occupancy Trend (last 30 days)
    # ------------------------------------------------------------------

    def _compute_daily_trend(self, rooms: List[Dict], days: int = 30) -> List[Dict]:
        """
        Daily occupancy rates for the last N days.
        Uses reservation overlap to determine occupied rooms per day.
        """
        total_sellable = len([
            r for r in rooms
            if r.get("status") not in ("Out of Order", "Maintenance")
        ])
        if total_sellable == 0:
            return []

        today = getdate(nowdate())
        trend = []

        for i in range(days, 0, -1):
            target = today - timedelta(days=i)
            target_str = target.strftime('%Y-%m-%d')

            # Count reservations overlapping this date
            overlapping = hotel_data.get_reservations_for_date(target_str)
            occupied_count = 0
            for res in overlapping:
                occupied_count += int(res.get("total_rooms") or 1)

            occ_rate = round(min(occupied_count / total_sellable * 100, 100), 1)
            trend.append({
                "date": target_str,
                "occupancy_rate": occ_rate,
                "rooms_occupied": min(occupied_count, total_sellable),
            })

        return trend

    # ------------------------------------------------------------------
    # Average Length of Stay
    # ------------------------------------------------------------------

    def _compute_avg_length_of_stay(self, reservations: List[Dict]) -> float:
        """Average Length of Stay from reservation nights field."""
        nights_list = [
            int(r.get("nights") or 0)
            for r in reservations
            if r.get("status") in ("Checked Out", "Checked In", "Check In Arrival")
            and int(r.get("nights") or 0) > 0
        ]
        if not nights_list:
            return 0.0
        return round(sum(nights_list) / len(nights_list), 1)

    # ------------------------------------------------------------------
    # Housekeeping Summary
    # ------------------------------------------------------------------

    def _compute_housekeeping_summary(self) -> Dict[str, Any]:
        """Summary of housekeeping task completion rates."""
        tasks = hotel_data.get_housekeeping_tasks(self.start_date, self.end_date)
        if not tasks:
            return {
                "total_tasks": 0,
                "completed": 0,
                "pending": 0,
                "in_progress": 0,
                "completion_rate": 0,
                "avg_quality_rating": 0,
            }

        total = len(tasks)
        completed = sum(
            1 for t in tasks
            if t.get("status") in ("Completed", "Verified")
        )
        pending = sum(1 for t in tasks if t.get("status") == "Pending")
        in_progress = sum(1 for t in tasks if t.get("status") == "In Progress")

        # Average quality rating from verified tasks
        rated_tasks = [
            int(t.get("quality_rating") or 0)
            for t in tasks
            if t.get("status") == "Verified" and int(t.get("quality_rating") or 0) > 0
        ]
        avg_rating = round(sum(rated_tasks) / len(rated_tasks), 1) if rated_tasks else 0

        return {
            "total_tasks": total,
            "completed": completed,
            "pending": pending,
            "in_progress": in_progress,
            "completion_rate": round(completed / total * 100, 1) if total else 0,
            "avg_quality_rating": avg_rating,
        }
