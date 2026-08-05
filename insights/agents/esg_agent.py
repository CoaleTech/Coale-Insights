"""
ESG Intelligence Agent

AI agent specialized in Environmental, Social, and Governance (ESG)
sustainability metrics, compliance, and corporate responsibility insights.

Extends BaseIntelligenceAgent for consistent behavior with all other
dashboard agents (model fallback, quota, config, etc.).
"""

from typing import Dict, List, Optional

from insights.agents.base import BaseIntelligenceAgent
from insights.agents.registry import AgentRegistry


@AgentRegistry.register("ESG")
class ESGIntelligenceAgent(BaseIntelligenceAgent):
    """AI agent specialized for ESG Intelligence dashboard"""

    dashboard_type = "ESG"
    agent_name = "ESG Intelligence Agent"
    description = "AI assistant for ESG sustainability metrics, compliance, and corporate responsibility"

    def __init__(self):
        super().__init__()
        # ESGIntelligence.get_esg_overview() returns fabricated data (hardcoded
        # scores, synthetic trends) rather than measured metrics — see
        # plan-eng-review D3.1. Disabled until the module computes real data;
        # execute() below falls back to empty context, and the base agent
        # answers from conversation history / general knowledge only.
        self.esg_intel = None

    def execute(self, query, session_id, context=None, conversation_history=None):
        """Gather fresh ESG data if no context provided, then delegate to base."""
        if not context and self.esg_intel:
            try:
                esg_data = self.esg_intel.get_esg_overview("YTD")
                if not isinstance(esg_data, dict) or "error" in esg_data:
                    context = {}
                else:
                    context = self.compress_context(esg_data)
            except Exception:
                context = {}
        return super().execute(query, session_id, context, conversation_history)

    def compress_context(self, full_context: Dict) -> Dict:
        """Compress ESG-specific context for token optimization."""
        environmental = full_context.get("environmental_metrics", {})
        social = full_context.get("social_metrics", {})
        governance = full_context.get("governance_metrics", {})
        esg_score = full_context.get("esg_score", {})

        key_metrics = {
            "overall_esg_score": esg_score.get("overall_score", 0),
            "environmental_score": esg_score.get("environmental_score", 0),
            "social_score": esg_score.get("social_score", 0),
            "governance_score": esg_score.get("governance_score", 0),
            "carbon_emissions": environmental.get("carbon_emissions", 0),
            "energy_consumption": environmental.get("energy_consumption", 0),
            "renewable_energy_pct": environmental.get("renewable_energy_pct", 0),
            "waste_recycling_pct": environmental.get("waste_recycling_pct", 0),
            "diversity_index": social.get("diversity_index", 0),
            "employee_safety_score": social.get("safety_score", 0),
            "compliance_rate_pct": governance.get("compliance_rate_pct", 0),
            "board_diversity_pct": governance.get("board_diversity_pct", 0),
        }

        return {
            "summary": f"ESG Score: {key_metrics['overall_esg_score']}/100 "
                       f"(E:{key_metrics['environmental_score']}, "
                       f"S:{key_metrics['social_score']}, "
                       f"G:{key_metrics['governance_score']})",
            "key_metrics": key_metrics,
            "environmental_highlights": {
                k: v for k, v in environmental.items()
                if isinstance(v, (int, float, str)) and len(str(k)) < 40
            },
            "social_highlights": {
                k: v for k, v in social.items()
                if isinstance(v, (int, float, str)) and len(str(k)) < 40
            },
            "governance_highlights": {
                k: v for k, v in governance.items()
                if isinstance(v, (int, float, str)) and len(str(k)) < 40
            },
            "initiatives": full_context.get("active_initiatives", [])[:5],
            "period": full_context.get("period", "YTD"),
        }

    def _get_default_system_prompt(self, context: Optional[Dict] = None) -> str:
        ctx_str = ""
        if context:
            import json
            ctx_str = json.dumps(context, indent=2, default=str)

        return f"""You are an ESG Intelligence AI assistant for ERPNext. Your expertise includes:

## Your Expertise:
- Environmental impact analysis (carbon emissions, energy, waste, water)
- Social responsibility metrics (diversity, safety, community engagement)
- Governance compliance tracking (board oversight, ethics, transparency)
- ESG scoring and benchmarking
- Sustainability reporting and frameworks (GRI, SASB, TCFD)
- Corporate responsibility insights and strategy

## Current Dashboard Data:
{ctx_str if ctx_str else "No data available"}

## Guidelines:
- Provide specific ESG insights with metrics and scores
- Reference environmental, social, and governance indicators
- Identify compliance gaps and improvement opportunities
- Suggest strategies for improving ESG performance
- Consider industry benchmarks and reporting frameworks
- Use markdown formatting with bullet points for clarity

## Response Format:
- Start with overall ESG performance assessment
- Break down Environmental, Social, and Governance scores
- Highlight key initiatives and their progress
- Identify risks and areas for improvement
- Recommend 2-3 specific actions for ESG improvement"""

    def _get_default_quick_actions(self) -> List[Dict]:
        return [
            {
                "label": "ESG Score",
                "prompt_template": "What is our current ESG performance score and trend?",
                "icon": "leaf",
            },
            {
                "label": "Environmental Impact",
                "prompt_template": "Analyze our environmental impact metrics and carbon footprint.",
                "icon": "globe",
            },
            {
                "label": "Social Responsibility",
                "prompt_template": "How are we performing on social responsibility indicators?",
                "icon": "users",
            },
            {
                "label": "Governance Compliance",
                "prompt_template": "What is our governance compliance status?",
                "icon": "clipboard",
            },
        ]

    def _get_default_routing_keywords(self) -> List[str]:
        return [
            "esg", "esg score", "esg rating", "sustainability", "sustainable",
            "environment", "environmental", "carbon", "emissions", "greenhouse gas",
            "energy", "renewable", "solar", "wind", "green", "eco", "waste",
            "recycling", "pollution", "footprint", "water", "conservation",
            "climate", "biodiversity", "social", "diversity", "inclusion",
            "equity", "wellbeing", "safety", "health", "community",
            "human rights", "labor", "ethics", "stakeholder",
            "governance", "board", "compliance", "audit", "transparency",
            "accountability", "regulation", "policy", "control", "oversight",
            "reporting", "disclosure", "corporate responsibility", "csr",
        ]
