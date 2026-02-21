# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
General Intelligence Agent
AI agent for the AI Insights page — handles cross-module queries
and routes to specialized agents when appropriate.
"""

from typing import Dict, List, Optional

from insights.agents import BaseIntelligenceAgent, AgentRegistry


@AgentRegistry.register("General")
class GeneralIntelligenceAgent(BaseIntelligenceAgent):
    """AI agent for the general AI Insights page — covers all ERPNext modules"""

    dashboard_type = "General"
    agent_name = "General Intelligence Agent"
    description = "AI assistant for cross-module business intelligence and ERPNext analytics"

    def compress_context(self, full_context: Dict) -> Dict:
        """Compress general context — keep it minimal since General queries are broad"""
        compressed = {
            "summary": self._extract_summary(full_context),
            "kpis": self._extract_key_kpis(full_context),
            "alerts": self._extract_alerts(full_context),
        }
        return compressed

    def _get_default_system_prompt(self, context: Optional[Dict] = None) -> str:
        """System prompt for the general-purpose AI insights agent"""
        import json

        ctx_str = ""
        if context:
            ctx_str = json.dumps(context, indent=2, default=str)

        return f"""You are an expert business intelligence AI assistant for ERPNext ERP system.

## Your Expertise:
You can answer questions across ALL ERPNext modules:
- **Finance & Accounting**: Revenue, expenses, cash flow, profitability, outstanding invoices, financial ratios
- **Sales**: Sales performance, top products, customer trends, pipeline, forecasting
- **Procurement**: Supplier performance, purchase trends, cost analysis, vendor evaluation
- **Inventory**: Stock levels, turnover rates, reorder points, dead stock, ABC analysis
- **CRM**: Lead conversion, customer journey, opportunity tracking, campaign effectiveness
- **HR**: Attendance, headcount, payroll, leave management, workforce analytics
- **Projects**: Project performance, resource allocation, timelines, budgets

{f"## Available Context Data:{chr(10)}{ctx_str}" if ctx_str else ""}

## Response Guidelines:
1. **Be specific and data-driven** — reference actual numbers when available
2. **Use markdown formatting** — headers, bullet points, bold for emphasis, tables for comparisons
3. **Provide actionable recommendations** — 2-3 concrete next steps when appropriate
4. **Acknowledge limitations** — if data is insufficient, say so clearly
5. **Use code blocks** for any SQL queries, formulas, or technical references
6. **Structure longer responses** with clear sections and headers
7. **For numerical data** — consider suggesting a chart format when helpful

## Chart Data Format:
When presenting data that would benefit from visualization, include a chart block:
```chart
{{"type": "bar", "title": "Example", "labels": ["A", "B"], "datasets": [{{"name": "Values", "values": [10, 20]}}]}}
```

## Response Format:
- Start with a direct, concise answer
- Support with specific data points
- Add actionable recommendations when relevant
- Keep responses focused — avoid unnecessary preamble"""

    def _get_default_quick_actions(self) -> List[Dict]:
        """Quick actions for the general AI insights page"""
        return [
            {
                "label": "📊 Business Overview",
                "prompt_template": "Give me a high-level overview of the business health — revenue, cash flow, and key alerts.",
                "icon": "activity",
            },
            {
                "label": "💰 Financial Summary",
                "prompt_template": "Summarize our financial position — revenue trends, outstanding amounts, and profitability.",
                "icon": "dollar-sign",
            },
            {
                "label": "📈 Sales Performance",
                "prompt_template": "How are sales performing this month? Show top products and growth trends.",
                "icon": "trending-up",
            },
            {
                "label": "📦 Stock Alerts",
                "prompt_template": "Are there any inventory items that need attention — low stock, slow movers, or reorder needs?",
                "icon": "package",
            },
            {
                "label": "⚠️ Risk & Alerts",
                "prompt_template": "What are the key business risks and alerts I should be aware of right now?",
                "icon": "alert-triangle",
            },
        ]

    def _get_default_routing_keywords(self) -> List[str]:
        """General agent matches broadly — all common business terms"""
        return [
            "overview", "summary", "dashboard", "report", "analysis",
            "business", "company", "performance", "metrics", "kpi",
            "compare", "trend", "forecast", "growth", "decline",
            "help", "explain", "what is", "how to", "show me",
        ]
