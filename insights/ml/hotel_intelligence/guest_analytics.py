# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Hotel Intelligence - Guest Analytics

Computes:
- Repeat Guest Rate (guests with total_stays > 1)
- Average Guest Spend
- Nationality Distribution (top nationalities)
- VIP Guest Count and proportion
- Booking Source Distribution
- Guest Segments (New, Returning, Loyal)
- Top Guests by spend
"""

import frappe
from frappe.utils import nowdate
from typing import Dict, Any, List
from collections import Counter

from insights.api.ml import parse_date_filter
from . import data as hotel_data


class GuestAnalytics:
    """Guest intelligence: repeat rates, segmentation, nationality, VIP analysis."""

    def __init__(self, date_filter: str = '12m'):
        self.date_filter = date_filter
        start, end = parse_date_filter(date_filter)
        self.start_date = start.strftime('%Y-%m-%d') if start else '2020-01-01'
        self.end_date = end.strftime('%Y-%m-%d') if end else nowdate()

    def compute(self) -> Dict[str, Any]:
        """Run all guest analytics and return aggregated results."""
        guests = hotel_data.get_all_guests()
        reservations = hotel_data.get_reservations(self.start_date, self.end_date)

        if not guests:
            return self._empty_result()

        total_guests = len(guests)

        # Repeat Guest Rate
        repeat_rate = self._compute_repeat_guest_rate(guests)

        # Average Guest Spend
        avg_spend = self._compute_avg_guest_spend(guests)

        # Nationality Distribution
        nationalities = self._compute_nationality_distribution(guests)

        # VIP Analysis
        vip_count, vip_pct = self._compute_vip_stats(guests)

        # Booking Source Distribution (from reservations)
        booking_sources = self._compute_booking_source_distribution(reservations)

        # Guest Segments
        segments = self._compute_guest_segments(guests)

        # Top Guests by spend
        top_guests = self._compute_top_guests(guests)

        # Average stays and nights
        avg_stays = self._safe_avg([int(g.get("total_stays") or 0) for g in guests])
        avg_nights = self._safe_avg([int(g.get("total_nights") or 0) for g in guests])

        return {
            "total_guests": total_guests,
            "repeat_guest_rate": repeat_rate,
            "avg_guest_spend": avg_spend,
            "avg_stays_per_guest": round(avg_stays, 1),
            "avg_nights_per_guest": round(avg_nights, 1),
            "vip_count": vip_count,
            "vip_percentage": vip_pct,
            "nationality_distribution": nationalities,
            "booking_source_distribution": booking_sources,
            "guest_segments": segments,
            "top_guests": top_guests,
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "total_guests": 0,
            "repeat_guest_rate": 0,
            "avg_guest_spend": 0,
            "avg_stays_per_guest": 0,
            "avg_nights_per_guest": 0,
            "vip_count": 0,
            "vip_percentage": 0,
            "nationality_distribution": [],
            "booking_source_distribution": [],
            "guest_segments": {},
            "top_guests": [],
        }

    # ------------------------------------------------------------------
    # Repeat Guest Rate
    # ------------------------------------------------------------------

    def _compute_repeat_guest_rate(self, guests: List[Dict]) -> float:
        """Repeat Guest Rate = Guests with total_stays > 1 / Total guests"""
        total = len(guests)
        if total == 0:
            return 0.0

        repeat = sum(1 for g in guests if int(g.get("total_stays") or 0) > 1)
        return round(repeat / total * 100, 1)

    # ------------------------------------------------------------------
    # Average Guest Spend
    # ------------------------------------------------------------------

    def _compute_avg_guest_spend(self, guests: List[Dict]) -> float:
        """Average of total_spent across all guests."""
        spends = [float(g.get("total_spent") or 0) for g in guests]
        if not spends:
            return 0.0
        return round(sum(spends) / len(spends), 2)

    # ------------------------------------------------------------------
    # Nationality Distribution
    # ------------------------------------------------------------------

    def _compute_nationality_distribution(
        self, guests: List[Dict], top_n: int = 15
    ) -> List[Dict]:
        """Top nationalities by guest count."""
        nationalities = [
            g.get("nationality") for g in guests
            if g.get("nationality")
        ]
        if not nationalities:
            return []

        counter = Counter(nationalities)
        total = len(nationalities)

        result = []
        for nationality, count in counter.most_common(top_n):
            result.append({
                "nationality": str(nationality),
                "count": int(count),
                "percentage": round(count / total * 100, 1),
            })

        return result

    # ------------------------------------------------------------------
    # VIP Analysis
    # ------------------------------------------------------------------

    def _compute_vip_stats(self, guests: List[Dict]) -> tuple:
        """VIP guest count and percentage."""
        total = len(guests)
        if total == 0:
            return 0, 0.0

        vip_count = sum(1 for g in guests if g.get("vip_status"))
        vip_pct = round(vip_count / total * 100, 1)
        return int(vip_count), vip_pct

    # ------------------------------------------------------------------
    # Booking Source Distribution
    # ------------------------------------------------------------------

    def _compute_booking_source_distribution(
        self, reservations: List[Dict]
    ) -> List[Dict]:
        """Distribution of reservations by booking_source."""
        sources = [
            r.get("booking_source") or "Unknown"
            for r in reservations
        ]
        if not sources:
            return []

        counter = Counter(sources)
        total = len(sources)

        result = []
        for source, count in counter.most_common():
            result.append({
                "source": str(source),
                "count": int(count),
                "percentage": round(count / total * 100, 1),
            })

        return result

    # ------------------------------------------------------------------
    # Guest Segments
    # ------------------------------------------------------------------

    def _compute_guest_segments(self, guests: List[Dict]) -> Dict[str, Any]:
        """
        Segment guests by loyalty:
        - New: 1 stay
        - Returning: 2-4 stays
        - Loyal: 5+ stays
        """
        new_guests = 0
        returning = 0
        loyal = 0

        for g in guests:
            stays = int(g.get("total_stays") or 0)
            if stays <= 1:
                new_guests += 1
            elif stays <= 4:
                returning += 1
            else:
                loyal += 1

        total = len(guests) or 1  # avoid division by zero
        return {
            "new": {
                "count": new_guests,
                "percentage": round(new_guests / total * 100, 1),
            },
            "returning": {
                "count": returning,
                "percentage": round(returning / total * 100, 1),
            },
            "loyal": {
                "count": loyal,
                "percentage": round(loyal / total * 100, 1),
            },
        }

    # ------------------------------------------------------------------
    # Top Guests by Spend
    # ------------------------------------------------------------------

    def _compute_top_guests(
        self, guests: List[Dict], top_n: int = 20
    ) -> List[Dict]:
        """Top N guests by total_spent."""
        sorted_guests = sorted(
            guests,
            key=lambda g: float(g.get("total_spent") or 0),
            reverse=True,
        )[:top_n]

        return [
            {
                "guest": str(g.get("name")),
                "guest_name": str(g.get("guest_name") or ""),
                "total_stays": int(g.get("total_stays") or 0),
                "total_nights": int(g.get("total_nights") or 0),
                "total_spent": float(g.get("total_spent") or 0),
                "vip_status": bool(g.get("vip_status")),
                "nationality": str(g.get("nationality") or ""),
                "last_visit_date": str(g.get("last_visit_date") or ""),
            }
            for g in sorted_guests
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_avg(values: List) -> float:
        """Safe average that handles empty lists."""
        if not values:
            return 0.0
        return sum(values) / len(values)
