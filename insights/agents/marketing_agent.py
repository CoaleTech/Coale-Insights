"""
Marketing Intelligence Agent

AI agent specialized in marketing analytics, campaign optimization,
and lead management insights.

Extends BaseIntelligenceAgent for consistent behavior with all other
dashboard agents (model fallback, quota, config, etc.).
"""

from typing import Dict, List, Optional

from insights.agents.base import BaseIntelligenceAgent
from insights.agents.registry import AgentRegistry


@AgentRegistry.register("Marketing")
class MarketingIntelligenceAgent(BaseIntelligenceAgent):
    """AI agent specialized for Marketing Intelligence dashboard"""

    dashboard_type = "Marketing"
    agent_name = "Marketing Intelligence Agent"
    description = "AI assistant for marketing analytics, campaign optimization, and lead management"

    def __init__(self):
        super().__init__()
        try:
            from insights.ml.marketing_intelligence import MarketingIntelligence
            self.marketing_intel = MarketingIntelligence()
        except Exception:
            self.marketing_intel = None

    def execute(self, query, session_id, context=None, conversation_history=None):
        """Gather fresh marketing data if no context provided, then delegate to base."""
        if not context and self.marketing_intel:
            try:
                marketing_data = self.marketing_intel.get_marketing_overview("YTD")
                context = self.compress_context(marketing_data)
            except Exception:
                context = {}
        return super().execute(query, session_id, context, conversation_history)

    def compress_context(self, full_context: Dict) -> Dict:
        """Compress marketing-specific context for token optimization."""
        campaign_metrics = full_context.get("campaign_metrics", {})
        lead_metrics = full_context.get("lead_metrics", {})
        pipeline_metrics = full_context.get("pipeline_metrics", {})
        # Bug fix 2026-08-17: `get_marketing_overview` returns this
        # section under `channel_performance` (see marketing_intelligence.py
        # docstring); `channel_metrics` never existed, so `top_channels`
        # below was silently always empty.
        channel_metrics = full_context.get("channel_performance", {})

        campaign_overview = campaign_metrics.get("campaign_overview", {})
        # May be None: Campaign has no cost columns on this site, so ROI
        # is unmeasurable rather than 0 (see _analyze_campaigns).
        campaign_roi = campaign_metrics.get("campaign_roi_pct")

        key_metrics = {
            "total_campaigns": campaign_overview.get("total_campaigns", 0),
            "active_campaigns": campaign_overview.get("active_campaigns", 0),
            "campaign_roi_pct": campaign_roi,
            "total_leads": lead_metrics.get("total_leads", 0),
            "qualified_leads": lead_metrics.get("qualified_leads", 0),
            "lead_conversion_rate": lead_metrics.get("conversion_rate_pct", 0),
            "pipeline_value": pipeline_metrics.get("total_pipeline_value", 0),
            "pipeline_opportunities": pipeline_metrics.get("total_opportunities", 0),
            "win_rate_pct": pipeline_metrics.get("win_rate_pct", 0),
        }

        # Top channels by performance
        top_channels = {}
        if isinstance(channel_metrics, dict):
            for channel, data in list(channel_metrics.items())[:5]:
                if isinstance(data, dict):
                    top_channels[channel] = {
                        k: v for k, v in data.items()
                        if isinstance(v, (int, float)) and len(str(k)) < 30
                    }

        return {
            "summary": f"Marketing: {key_metrics['active_campaigns']} active campaigns, "
                       f"ROI {campaign_roi if campaign_roi is not None else 'n/a'}%, "
                       f"{key_metrics['total_leads']} leads ({key_metrics['lead_conversion_rate']}% conversion)",
            "key_metrics": key_metrics,
            "email_metrics": campaign_metrics.get("email_campaign_metrics", {}),
            "top_channels": top_channels,
            # Bug fix 2026-08-17: `_analyze_leads` returns this section
            # under `source_breakdown`; `lead_sources` never existed, so
            # this was silently always empty.
            "lead_sources": lead_metrics.get("source_breakdown", {}),
            "period": full_context.get("period", "YTD"),
        }

    def _get_default_system_prompt(self, context: Optional[Dict] = None) -> str:
        ctx_str = ""
        if context:
            import json
            ctx_str = json.dumps(context, indent=2, default=str)

        return f"""You are a Marketing Intelligence AI assistant for ERPNext. Your expertise includes:

## Your Expertise:
- Campaign performance analysis and optimization
- Lead generation and scoring
- Sales pipeline and opportunity management
- Conversion funnel analysis
- Marketing ROI and attribution
- Channel performance analysis
- Customer acquisition cost (CAC) and lifetime value (CLV)

## Current Dashboard Data:
{ctx_str if ctx_str else "No data available"}

## Guidelines:
- Provide specific marketing insights with metrics
- Reference campaign ROI, lead conversion rates, and pipeline values
- Identify high-performing and underperforming channels
- Suggest strategies for improving marketing effectiveness
- Include actionable recommendations with expected impact
- Use markdown formatting with bullet points for clarity

## Response Format:
- Start with overall marketing performance assessment
- Highlight key metrics and their implications
- Identify opportunities and areas of concern
- Recommend 2-3 specific actions for improvement"""

    def _get_default_quick_actions(self) -> List[Dict]:
        return [
            {
                "label": "Campaign Performance",
                "prompt_template": "How are our marketing campaigns performing?",
                "icon": "megaphone",
            },
            {
                "label": "Lead Pipeline",
                "prompt_template": "Analyze our current lead pipeline and conversion rates.",
                "icon": "users",
            },
            {
                "label": "Customer Acquisition",
                "prompt_template": "What is our customer acquisition cost and how can we optimize it?",
                "icon": "dollar-sign",
            },
            {
                "label": "CRM Insights",
                "prompt_template": "Give me key CRM insights and opportunity analysis.",
                "icon": "bar-chart-2",
            },
        ]

    def _get_default_routing_keywords(self) -> List[str]:
        return [
            "campaign", "marketing", "advertising", "promotion", "digital marketing",
            "content marketing", "social media", "seo", "sem", "ppc", "ad spend",
            "lead", "lead generation", "lead scoring", "lead quality", "prospect",
            "lead conversion", "qualification", "pipeline", "opportunity", "deal",
            "sales funnel", "conversion rate", "win rate", "close rate",
            "customer acquisition", "cac", "clv", "roi", "roas",
            "channel", "attribution", "traffic sources",
        ]
