# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Hotel Intelligence - Restaurant Analytics

Computes:
- RevPASH (Revenue Per Available Seat Hour) per section
- Menu Engineering Matrix (Stars / Puzzles / Plowhorses / Dogs)
- Table Turnover rate
- Peak Hours (hourly order distribution)
- Total restaurant revenue
"""

import frappe
from frappe.utils import nowdate
from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import defaultdict

from insights.api.ml import parse_date_filter
from . import data as hotel_data


class RestaurantAnalytics:
    """Restaurant performance: RevPASH, menu engineering, turnover, peak hours."""

    def __init__(self, date_filter: str = '12m'):
        self.date_filter = date_filter
        start, end = parse_date_filter(date_filter)
        self.start_date = start.strftime('%Y-%m-%d') if start else '2020-01-01'
        self.end_date = end.strftime('%Y-%m-%d') if end else nowdate()

    def compute(self) -> Dict[str, Any]:
        """Run all restaurant analytics and return aggregated results."""
        orders = hotel_data.get_restaurant_orders(self.start_date, self.end_date)
        order_items = hotel_data.get_restaurant_order_items(self.start_date, self.end_date)
        sections = hotel_data.get_restaurant_sections()

        if not orders:
            return self._empty_result()

        total_revenue = sum(float(o.get("grand_total") or 0) for o in orders)
        total_orders = len(orders)

        # RevPASH per section
        revpash_data = self._compute_revpash(orders, sections)
        avg_revpash = self._safe_avg([s.get("revpash", 0) for s in revpash_data])

        # Menu Engineering Matrix
        menu_matrix = self._compute_menu_engineering(order_items)

        # Table Turnover
        table_turnover = self._compute_table_turnover(orders)

        # Peak Hours
        peak_hours = self._compute_peak_hours(orders)

        # Daily revenue trend
        daily_revenue = self._compute_daily_revenue(orders)

        return {
            "total_revenue": round(total_revenue, 2),
            "total_orders": total_orders,
            "avg_order_value": round(total_revenue / total_orders, 2) if total_orders else 0,
            "avg_revpash": round(avg_revpash, 2),
            "revpash_by_section": revpash_data,
            "menu_engineering": menu_matrix,
            "table_turnover": table_turnover,
            "peak_hours": peak_hours,
            "daily_revenue": daily_revenue,
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "total_revenue": 0,
            "total_orders": 0,
            "avg_order_value": 0,
            "avg_revpash": 0,
            "revpash_by_section": [],
            "menu_engineering": {
                "stars": [], "plowhorses": [], "puzzles": [], "dogs": [],
                "summary": {}
            },
            "table_turnover": {"avg_daily_orders": 0, "avg_orders_per_table": 0},
            "peak_hours": [],
            "daily_revenue": [],
        }

    # ------------------------------------------------------------------
    # RevPASH (Revenue Per Available Seat Hour)
    # ------------------------------------------------------------------

    def _compute_revpash(
        self, orders: List[Dict], sections: List[Dict]
    ) -> List[Dict]:
        """
        RevPASH = Revenue / (Available Seats x Operating Hours)

        Per section, using section capacity and opening/closing times.
        Revenue is allocated proportionally if no section-level linkage exists.
        """
        if not sections:
            return []

        total_revenue = sum(float(o.get("grand_total") or 0) for o in orders)

        # Calculate number of operating days in the period
        start = datetime.strptime(self.start_date, '%Y-%m-%d')
        end = datetime.strptime(self.end_date, '%Y-%m-%d')
        total_days = max((end - start).days, 1)

        result = []
        total_capacity = sum(int(s.get("capacity") or 0) for s in sections)

        for section in sections:
            capacity = int(section.get("capacity") or 0)
            if capacity == 0:
                continue

            # Calculate operating hours per day
            opening = section.get("opening_time")
            closing = section.get("closing_time")
            operating_hours = self._calculate_operating_hours(opening, closing)

            if operating_hours == 0:
                operating_hours = 12  # default assumption

            # Allocate revenue proportionally by capacity share
            if total_capacity > 0:
                section_revenue = total_revenue * (capacity / total_capacity)
            else:
                section_revenue = total_revenue / len(sections)

            # RevPASH = Revenue / (Seats x Hours x Days)
            available_seat_hours = capacity * operating_hours * total_days
            revpash = round(section_revenue / available_seat_hours, 2) if available_seat_hours else 0

            result.append({
                "section": str(section.get("section_name") or section.get("name")),
                "capacity": capacity,
                "operating_hours": operating_hours,
                "allocated_revenue": round(section_revenue, 2),
                "revpash": revpash,
            })

        return result

    def _calculate_operating_hours(self, opening, closing) -> float:
        """Calculate hours between opening and closing times."""
        if not opening or not closing:
            return 0

        try:
            if isinstance(opening, str):
                open_dt = datetime.strptime(str(opening), '%H:%M:%S')
            else:
                open_dt = datetime.combine(datetime.today(), opening)

            if isinstance(closing, str):
                close_dt = datetime.strptime(str(closing), '%H:%M:%S')
            else:
                close_dt = datetime.combine(datetime.today(), closing)

            diff = (close_dt - open_dt).total_seconds() / 3600
            return round(max(diff, 0), 1)
        except (ValueError, TypeError):
            return 0

    # ------------------------------------------------------------------
    # Menu Engineering Matrix
    # ------------------------------------------------------------------

    def _compute_menu_engineering(self, order_items: List[Dict]) -> Dict[str, Any]:
        """
        Menu Engineering Matrix classifies items into four categories:
        - Stars: High popularity + High margin
        - Plowhorses: High popularity + Low margin
        - Puzzles: Low popularity + High margin
        - Dogs: Low popularity + Low margin

        Uses median popularity (qty sold) and median contribution margin as thresholds.
        """
        if not order_items:
            return {
                "stars": [], "plowhorses": [], "puzzles": [], "dogs": [],
                "summary": {}
            }

        # Aggregate item-level metrics
        item_stats = defaultdict(lambda: {
            "item_code": "", "item_name": "", "item_group": "",
            "total_qty": 0, "total_revenue": 0, "avg_price": 0,
        })

        for item in order_items:
            code = item.get("item_code")
            if not code:
                continue
            stats = item_stats[code]
            stats["item_code"] = str(code)
            stats["item_name"] = str(item.get("item_name") or code)
            stats["item_group"] = str(item.get("item_group") or "")
            stats["total_qty"] += int(item.get("qty") or 0)
            stats["total_revenue"] += float(item.get("amount") or 0)

        if not item_stats:
            return {
                "stars": [], "plowhorses": [], "puzzles": [], "dogs": [],
                "summary": {}
            }

        # Calculate average selling price
        for code, stats in item_stats.items():
            if stats["total_qty"] > 0:
                stats["avg_price"] = round(stats["total_revenue"] / stats["total_qty"], 2)

        # Get cost prices for contribution margin
        item_codes = list(item_stats.keys())
        costs = hotel_data.get_item_costs(item_codes)
        cost_map = {c.get("item_code"): float(c.get("cost_price") or 0) for c in costs}

        # Calculate contribution margin per item
        items_list = []
        for code, stats in item_stats.items():
            cost = cost_map.get(code, 0)
            margin = stats["avg_price"] - cost
            items_list.append({
                "item_code": stats["item_code"],
                "item_name": stats["item_name"],
                "item_group": stats["item_group"],
                "total_qty": int(stats["total_qty"]),
                "total_revenue": round(stats["total_revenue"], 2),
                "avg_price": stats["avg_price"],
                "cost_price": round(cost, 2),
                "contribution_margin": round(margin, 2),
            })

        if not items_list:
            return {
                "stars": [], "plowhorses": [], "puzzles": [], "dogs": [],
                "summary": {}
            }

        # Calculate medians for thresholds
        sorted_by_qty = sorted(items_list, key=lambda x: x["total_qty"])
        sorted_by_margin = sorted(items_list, key=lambda x: x["contribution_margin"])

        median_popularity = sorted_by_qty[len(sorted_by_qty) // 2]["total_qty"]
        median_margin = sorted_by_margin[len(sorted_by_margin) // 2]["contribution_margin"]

        # Classify items
        stars = []
        plowhorses = []
        puzzles = []
        dogs = []

        for item in items_list:
            high_pop = item["total_qty"] >= median_popularity
            high_margin = item["contribution_margin"] >= median_margin

            item["category"] = ""
            if high_pop and high_margin:
                item["category"] = "Star"
                stars.append(item)
            elif high_pop and not high_margin:
                item["category"] = "Plowhorse"
                plowhorses.append(item)
            elif not high_pop and high_margin:
                item["category"] = "Puzzle"
                puzzles.append(item)
            else:
                item["category"] = "Dog"
                dogs.append(item)

        # Sort each category by revenue descending
        for cat in [stars, plowhorses, puzzles, dogs]:
            cat.sort(key=lambda x: x["total_revenue"], reverse=True)

        return {
            "stars": stars,
            "plowhorses": plowhorses,
            "puzzles": puzzles,
            "dogs": dogs,
            "summary": {
                "total_items": len(items_list),
                "stars_count": len(stars),
                "plowhorses_count": len(plowhorses),
                "puzzles_count": len(puzzles),
                "dogs_count": len(dogs),
                "median_popularity": int(median_popularity),
                "median_margin": round(median_margin, 2),
                "stars_revenue_share": round(
                    sum(i["total_revenue"] for i in stars) /
                    sum(i["total_revenue"] for i in items_list) * 100, 1
                ) if items_list else 0,
            },
        }

    # ------------------------------------------------------------------
    # Table Turnover
    # ------------------------------------------------------------------

    def _compute_table_turnover(self, orders: List[Dict]) -> Dict[str, Any]:
        """
        Average orders per day and estimated orders per table per day.
        Uses POS order count as proxy for table usage.
        """
        if not orders:
            return {"avg_daily_orders": 0, "avg_orders_per_table": 0}

        # Count orders per day
        daily_counts = defaultdict(int)
        for o in orders:
            date_str = str(o.get("posting_date"))
            daily_counts[date_str] += 1

        num_days = max(len(daily_counts), 1)
        total_orders = len(orders)
        avg_daily = round(total_orders / num_days, 1)

        # Get total section capacity as proxy for table count
        sections = hotel_data.get_restaurant_sections()
        total_capacity = sum(int(s.get("capacity") or 0) for s in sections)

        # Estimate ~4 seats per table
        estimated_tables = max(total_capacity // 4, 1) if total_capacity else 10
        avg_per_table = round(avg_daily / estimated_tables, 2)

        return {
            "avg_daily_orders": avg_daily,
            "avg_orders_per_table": avg_per_table,
            "estimated_tables": int(estimated_tables),
            "total_operating_days": num_days,
        }

    # ------------------------------------------------------------------
    # Peak Hours
    # ------------------------------------------------------------------

    def _compute_peak_hours(self, orders: List[Dict]) -> List[Dict]:
        """
        Hourly order count distribution from Sales Invoice creation times.
        Returns 24-hour distribution.
        """
        hourly = defaultdict(int)

        for o in orders:
            creation = o.get("creation")
            if creation:
                try:
                    if isinstance(creation, str):
                        dt = datetime.strptime(str(creation)[:19], '%Y-%m-%d %H:%M:%S')
                    else:
                        dt = creation
                    hourly[dt.hour] += 1
                except (ValueError, TypeError):
                    pass

        if not hourly:
            return []

        total = sum(hourly.values())
        result = []
        for hour in range(24):
            count = hourly.get(hour, 0)
            result.append({
                "hour": hour,
                "hour_label": f"{hour:02d}:00",
                "order_count": int(count),
                "percentage": round(count / total * 100, 1) if total else 0,
            })

        return result

    # ------------------------------------------------------------------
    # Daily Revenue Trend
    # ------------------------------------------------------------------

    def _compute_daily_revenue(self, orders: List[Dict]) -> List[Dict]:
        """Daily restaurant revenue for trend charting."""
        daily = defaultdict(float)
        daily_count = defaultdict(int)

        for o in orders:
            date_str = str(o.get("posting_date"))
            daily[date_str] += float(o.get("grand_total") or 0)
            daily_count[date_str] += 1

        result = []
        for date_str in sorted(daily.keys()):
            result.append({
                "date": date_str,
                "revenue": round(daily[date_str], 2),
                "orders": int(daily_count[date_str]),
            })

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_avg(values: List) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)
