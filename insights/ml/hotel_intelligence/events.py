# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Hotel Intelligence - Event Analytics

Computes:
- Total Events and revenue from Event Booking
- Events by type distribution
- Average Revenue Per Event
- Upcoming Events pipeline
- Banquet Hall Utilization rate
- Monthly event trends
"""

import frappe
from frappe.utils import nowdate, getdate
from datetime import datetime
from typing import Dict, Any, List
from collections import defaultdict, Counter

from insights.api.ml import parse_date_filter
from . import data as hotel_data


class EventAnalytics:
    """Event analytics: revenue, type distribution, hall utilization, trends."""

    def __init__(self, date_filter: str = '12m'):
        self.date_filter = date_filter
        start, end = parse_date_filter(date_filter)
        self.start_date = start.strftime('%Y-%m-%d') if start else '2020-01-01'
        self.end_date = end.strftime('%Y-%m-%d') if end else nowdate()

    def compute(self) -> Dict[str, Any]:
        """Run all event analytics and return aggregated results."""
        bookings = hotel_data.get_event_bookings(self.start_date, self.end_date)
        event_days = hotel_data.get_event_days(self.start_date, self.end_date)
        halls = hotel_data.get_banquet_halls()

        if not bookings:
            return self._empty_result()

        total_events = len(bookings)
        total_revenue = sum(float(b.get("grand_total") or b.get("total_amount") or 0) for b in bookings)
        avg_revenue = round(total_revenue / total_events, 2) if total_events else 0

        # Events by type
        by_type = self._compute_by_type(bookings)

        # Events by status
        by_status = self._compute_by_status(bookings)

        # Upcoming events pipeline
        upcoming = self._compute_upcoming_events(bookings, event_days)

        # Banquet Hall Utilization
        hall_utilization = self._compute_hall_utilization(event_days, halls)

        # Monthly event trends
        monthly_trends = self._compute_monthly_trends(bookings, event_days)

        # Average guests per event
        total_expected = sum(int(b.get("total_expected_guests") or 0) for b in bookings)
        total_actual = sum(int(b.get("total_actual_guests") or 0) for b in bookings)
        avg_guests = round(total_expected / total_events, 0) if total_events else 0

        return {
            "total_events": total_events,
            "total_revenue": round(total_revenue, 2),
            "avg_revenue_per_event": avg_revenue,
            "total_expected_guests": total_expected,
            "total_actual_guests": total_actual,
            "avg_guests_per_event": int(avg_guests),
            "by_type": by_type,
            "by_status": by_status,
            "upcoming_events": upcoming,
            "hall_utilization": hall_utilization,
            "monthly_trends": monthly_trends,
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "total_events": 0,
            "total_revenue": 0,
            "avg_revenue_per_event": 0,
            "total_expected_guests": 0,
            "total_actual_guests": 0,
            "avg_guests_per_event": 0,
            "by_type": [],
            "by_status": [],
            "upcoming_events": [],
            "hall_utilization": [],
            "monthly_trends": [],
        }

    # ------------------------------------------------------------------
    # Events by Type
    # ------------------------------------------------------------------

    def _compute_by_type(self, bookings: List[Dict]) -> List[Dict]:
        """Distribution of events by event_type."""
        types = [b.get("event_type") or "Other" for b in bookings]
        counter = Counter(types)
        total = len(types)

        # Also compute revenue by type
        revenue_by_type = defaultdict(float)
        for b in bookings:
            t = b.get("event_type") or "Other"
            revenue_by_type[t] += float(b.get("grand_total") or b.get("total_amount") or 0)

        result = []
        for event_type, count in counter.most_common():
            result.append({
                "event_type": str(event_type),
                "count": int(count),
                "percentage": round(count / total * 100, 1) if total else 0,
                "total_revenue": round(revenue_by_type[event_type], 2),
            })

        return result

    # ------------------------------------------------------------------
    # Events by Status
    # ------------------------------------------------------------------

    def _compute_by_status(self, bookings: List[Dict]) -> List[Dict]:
        """Distribution of events by status."""
        statuses = [b.get("status") or "Unknown" for b in bookings]
        counter = Counter(statuses)
        total = len(statuses)

        result = []
        for status, count in counter.most_common():
            result.append({
                "status": str(status),
                "count": int(count),
                "percentage": round(count / total * 100, 1) if total else 0,
            })

        return result

    # ------------------------------------------------------------------
    # Upcoming Events Pipeline
    # ------------------------------------------------------------------

    def _compute_upcoming_events(
        self, bookings: List[Dict], event_days: List[Dict]
    ) -> List[Dict]:
        """
        Events with future event days (upcoming pipeline).
        Returns up to 20 upcoming events sorted by nearest date.
        """
        today = nowdate()

        # Find bookings with upcoming days
        upcoming_booking_ids = set()
        booking_next_date = {}

        for day in event_days:
            event_date = str(day.get("event_date") or "")
            if event_date >= today:
                bid = day.get("event_booking")
                upcoming_booking_ids.add(bid)
                if bid not in booking_next_date or event_date < booking_next_date[bid]:
                    booking_next_date[bid] = event_date

        # Also check bookings in confirmed/preparation status
        for b in bookings:
            if b.get("status") in ("Confirmed", "Preparation", "Draft"):
                upcoming_booking_ids.add(b.get("name"))

        result = []
        for b in bookings:
            if b.get("name") in upcoming_booking_ids:
                result.append({
                    "name": str(b.get("name")),
                    "event_name": str(b.get("event_name") or ""),
                    "event_type": str(b.get("event_type") or ""),
                    "status": str(b.get("status") or ""),
                    "banquet_hall": str(b.get("banquet_hall_name") or b.get("banquet_hall") or ""),
                    "expected_guests": int(b.get("total_expected_guests") or 0),
                    "grand_total": float(b.get("grand_total") or b.get("total_amount") or 0),
                    "next_date": booking_next_date.get(b.get("name"), ""),
                })

        # Sort by nearest date
        result.sort(key=lambda x: x.get("next_date") or "9999-99-99")
        return result[:20]

    # ------------------------------------------------------------------
    # Banquet Hall Utilization
    # ------------------------------------------------------------------

    def _compute_hall_utilization(
        self, event_days: List[Dict], halls: List[Dict]
    ) -> List[Dict]:
        """
        Banquet Hall Utilization = Days with events / Total days in period per hall.
        """
        if not halls:
            return []

        # Calculate total days in period
        start = datetime.strptime(self.start_date, '%Y-%m-%d')
        end = datetime.strptime(self.end_date, '%Y-%m-%d')
        total_days = max((end - start).days, 1)

        # Count unique event days per hall
        hall_days = defaultdict(set)
        for day in event_days:
            hall = day.get("banquet_hall")
            event_date = str(day.get("event_date") or "")
            if hall and event_date:
                hall_days[hall].add(event_date)

        result = []
        for h in halls:
            hall_name = h.get("name") or h.get("hall_name")
            days_used = len(hall_days.get(hall_name, set()))
            utilization = round(days_used / total_days * 100, 1)

            result.append({
                "hall": str(h.get("hall_name") or hall_name),
                "hall_type": str(h.get("hall_type") or ""),
                "capacity": int(h.get("capacity") or 0),
                "days_used": int(days_used),
                "total_days": int(total_days),
                "utilization_rate": utilization,
            })

        # Sort by utilization descending
        result.sort(key=lambda x: x["utilization_rate"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # Monthly Event Trends
    # ------------------------------------------------------------------

    def _compute_monthly_trends(
        self, bookings: List[Dict], event_days: List[Dict]
    ) -> List[Dict]:
        """Monthly event count and revenue trends."""
        monthly = defaultdict(lambda: {"events": set(), "revenue": 0, "event_days": 0, "guests": 0})

        # From event days for accurate date-based trending
        for day in event_days:
            event_date = day.get("event_date")
            if not event_date:
                continue
            month_key = str(event_date)[:7]  # YYYY-MM
            monthly[month_key]["event_days"] += 1
            monthly[month_key]["events"].add(day.get("event_booking"))
            monthly[month_key]["guests"] += int(day.get("expected_guests") or 0)

        # Add revenue from bookings (use creation month as fallback)
        for b in bookings:
            creation = b.get("creation")
            if creation:
                month_key = str(creation)[:7]
                monthly[month_key]["revenue"] += float(
                    b.get("grand_total") or b.get("total_amount") or 0
                )

        result = []
        for month_key in sorted(monthly.keys()):
            data = monthly[month_key]
            result.append({
                "month": month_key,
                "event_count": len(data["events"]),
                "event_days": int(data["event_days"]),
                "revenue": round(data["revenue"], 2),
                "total_guests": int(data["guests"]),
            })

        return result
