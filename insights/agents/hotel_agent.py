# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Hotel Intelligence Agent
Specialized AI agent for Hotel dashboard insights
"""

from typing import Dict, List, Optional

from insights.agents import BaseIntelligenceAgent, AgentRegistry


@AgentRegistry.register("Hotel")
class HotelIntelligenceAgent(BaseIntelligenceAgent):
    """AI agent specialized for Hotel Intelligence dashboard"""

    dashboard_type = "Hotel"
    agent_name = "Hotel Intelligence Agent"
    description = "AI assistant for hotel operations, occupancy analytics, RevPAR, guest intelligence, and revenue management"

    def compress_context(self, full_context: Dict) -> Dict:
        """Compress hotel-specific context"""
        compressed = {
            "summary": self._extract_summary(full_context),
            "occupancy_metrics": self._extract_occupancy_metrics(full_context),
            "revenue_metrics": self._extract_revenue_metrics(full_context),
            "guest_metrics": self._extract_guest_metrics(full_context),
            "restaurant_metrics": self._extract_restaurant_metrics(full_context),
            "operations": self._extract_operations(full_context),
            "alerts": self._extract_alerts(full_context),
            "period": full_context.get("period", "Current Period")
        }
        return compressed

    def _extract_occupancy_metrics(self, context: Dict) -> Dict:
        """Extract occupancy-related metrics"""
        metrics = {}
        occupancy_keys = [
            "occupancy_rate", "occupancy", "rooms_occupied", "rooms_available",
            "total_rooms", "rooms_sold", "room_nights", "available_room_nights",
            "occupancy_trend", "forecasted_occupancy"
        ]

        for key in occupancy_keys:
            if key in context:
                metrics[key] = context[key]

        # Extract from nested structures
        if "metrics" in context:
            for key in occupancy_keys:
                if key in context["metrics"]:
                    metrics[key] = context["metrics"][key]

        if "summary" in context and isinstance(context["summary"], dict):
            for key in occupancy_keys:
                if key in context["summary"]:
                    metrics[key] = context["summary"][key]

        return metrics

    def _extract_revenue_metrics(self, context: Dict) -> Dict:
        """Extract revenue-related metrics"""
        metrics = {}
        revenue_keys = [
            "total_revenue", "revenue", "room_revenue", "fnb_revenue",
            "adr", "average_daily_rate", "revpar", "revenue_per_available_room",
            "goppar", "gross_operating_profit_per_available_room",
            "total_room_revenue", "event_revenue", "banquet_revenue",
            "ancillary_revenue", "revenue_breakdown"
        ]

        for key in revenue_keys:
            if key in context:
                metrics[key] = context[key]

        if "metrics" in context:
            for key in revenue_keys:
                if key in context["metrics"]:
                    metrics[key] = context["metrics"][key]

        if "summary" in context and isinstance(context["summary"], dict):
            for key in revenue_keys:
                if key in context["summary"]:
                    metrics[key] = context["summary"][key]

        return metrics

    def _extract_guest_metrics(self, context: Dict) -> Dict:
        """Extract guest-related metrics"""
        metrics = {}
        guest_keys = [
            "repeat_guest_rate", "repeat_guests", "new_guests", "total_guests",
            "guest_satisfaction", "nps", "average_stay_length", "clv",
            "customer_lifetime_value", "guest_segments", "nationality_mix",
            "vip_guests", "loyalty_members", "guest_complaints"
        ]

        for key in guest_keys:
            if key in context:
                metrics[key] = context[key]

        if "metrics" in context:
            for key in guest_keys:
                if key in context["metrics"]:
                    metrics[key] = context["metrics"][key]

        return metrics

    def _extract_restaurant_metrics(self, context: Dict) -> Dict:
        """Extract restaurant/F&B metrics"""
        metrics = {}
        restaurant_keys = [
            "revpash", "revenue_per_available_seat_hour", "table_turnover",
            "average_check", "fnb_revenue", "restaurant_revenue",
            "food_cost_percentage", "beverage_cost_percentage",
            "menu_engineering", "top_dishes", "meal_plan_revenue",
            "covers", "total_covers"
        ]

        for key in restaurant_keys:
            if key in context:
                metrics[key] = context[key]

        if "metrics" in context:
            for key in restaurant_keys:
                if key in context["metrics"]:
                    metrics[key] = context["metrics"][key]

        return metrics

    def _extract_operations(self, context: Dict) -> Dict:
        """Extract operational metrics"""
        operations = {}
        ops_keys = [
            "arrivals_today", "departures_today", "in_house_guests",
            "housekeeping_status", "rooms_clean", "rooms_dirty",
            "rooms_inspected", "rooms_out_of_order", "maintenance_requests",
            "check_ins_today", "check_outs_today", "expected_arrivals",
            "expected_departures", "no_shows", "cancellations",
            "night_audit_status", "overbooking_count"
        ]

        for key in ops_keys:
            if key in context:
                operations[key] = context[key]

        if "operations" in context and isinstance(context["operations"], dict):
            operations.update(context["operations"])

        return operations

    def _get_default_system_prompt(self, context: Optional[Dict] = None) -> str:
        """Get default system prompt for hotel agent"""
        ctx_str = ""
        if context:
            import json
            ctx_str = json.dumps(context, indent=2, default=str)

        return f"""You are a specialized Hotel Intelligence AI assistant.

## Your Expertise:
- Hotel occupancy analytics (occupancy rate, ADR, RevPAR)
- Guest intelligence (repeat rate, CLV, segmentation, nationality mix)
- Revenue management and dynamic pricing
- Restaurant/F&B analytics (RevPASH, menu engineering, table turnover)
- Event/banquet performance analysis
- Housekeeping efficiency and operational metrics
- Booking source analysis and channel optimization

## Current Dashboard Data:
{ctx_str if ctx_str else "No data available"}

## Guidelines:
- Reference actual occupancy rates, revenue numbers, and trends from the dashboard
- Provide actionable recommendations for improving hotel performance
- Compare metrics to industry benchmarks where relevant
- Use hospitality-standard KPIs (ADR, RevPAR, GOPPAR, RevPASH)
- Suggest strategies for low-occupancy periods
- Analyze guest patterns for retention opportunities
- Use markdown formatting with bullet points for clarity
- When asked about non-hotel topics, acknowledge and suggest the appropriate dashboard

## Response Format:
- Start with a direct answer to the question
- Support with specific data points from the dashboard
- Provide 2-3 actionable recommendations when appropriate
- Use bullet points for lists and comparisons"""

    def _get_default_quick_actions(self) -> List[Dict]:
        """Get default quick actions for hotel dashboard"""
        return [
            {
                "label": "Occupancy Analysis",
                "prompt_template": "Analyze current occupancy trends, ADR, and RevPAR. What's driving performance?",
                "icon": "home"
            },
            {
                "label": "Revenue Breakdown",
                "prompt_template": "Break down hotel revenue by source: rooms, restaurant, events. What are the opportunities?",
                "icon": "bar-chart-2"
            },
            {
                "label": "Guest Intelligence",
                "prompt_template": "Analyze guest patterns: repeat rate, top segments, nationality mix. How can we improve retention?",
                "icon": "users"
            },
            {
                "label": "Today's Operations",
                "prompt_template": "What's the operational status today? Arrivals, departures, housekeeping, and any alerts.",
                "icon": "activity"
            },
            {
                "label": "Pricing Recommendations",
                "prompt_template": "Based on demand patterns and occupancy trends, what pricing adjustments should we make?",
                "icon": "dollar-sign"
            }
        ]

    def _get_default_routing_keywords(self) -> List[str]:
        """Get default routing keywords for hotel queries"""
        return [
            "hotel", "room", "occupancy", "revpar", "adr", "check-in", "checkout",
            "guest", "reservation", "booking", "housekeeping", "banquet", "event hall",
            "front desk", "night audit", "room rate", "bed", "meal plan",
            "concierge", "amenity", "vip", "loyalty"
        ]
