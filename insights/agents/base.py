# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Base Intelligence Agent
Abstract base class for all dashboard AI agents.
"""

import json
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

import frappe
from frappe.utils import now_datetime


def _safe_log_error(message: str, title: str = "Intelligence Agent"):
    """Safely log an error, truncating to avoid CharacterLengthExceededError"""
    try:
        safe_title = str(title)[:100] if title else "Intelligence Agent"
        safe_message = str(message)[:5000] if message else "No message"
        frappe.log_error(title=safe_title, message=safe_message)
    except Exception:
        print(f"[{title}] {message[:200]}..." if len(str(message)) > 200 else f"[{title}] {message}")


class BaseIntelligenceAgent(ABC):
    """
    Abstract base class for dashboard intelligence agents.
    Each dashboard type has a specialized agent that extends this class.
    """

    # Override in subclasses
    dashboard_type: str = ""
    agent_name: str = "Intelligence Agent"
    description: str = "AI-powered dashboard assistant"

    def __init__(self):
        self.context: Dict = {}
        self.compressed_context: Dict = {}
        self.config = None
        self._load_config()

    def _load_config(self):
        """Load agent configuration from DocType"""
        try:
            from insights.insights.doctype.dashboard_ai_agent_config.dashboard_ai_agent_config import (
                DashboardAIAgentConfig,
            )
            self.config = DashboardAIAgentConfig.get_config(self.dashboard_type)
        except Exception as e:
            _safe_log_error(f"Failed to load agent config: {e}", "Agent Config")
            self.config = None

    def set_context(self, dashboard_data: Dict) -> None:
        """
        Set the full dashboard context for the agent.
        Also generates compressed context for token optimization.
        """
        self.context = dashboard_data
        self.compressed_context = self.compress_context(dashboard_data)

    def compress_context(self, full_context: Dict) -> Dict:
        """
        Compress context to reduce token usage while preserving key information.
        Override in subclasses for dashboard-specific compression.

        Returns:
            Compressed context dict (max ~10KB)
        """
        compressed = {
            "summary": self._extract_summary(full_context),
            "kpis": self._extract_key_kpis(full_context),
            "trends": self._summarize_trends(full_context),
            "top_items": self._get_top_n(full_context, n=5),
            "alerts": self._extract_alerts(full_context),
            "date_range": full_context.get("filters", {}).get("date_range", "Not specified"),
        }

        compressed_str = json.dumps(compressed)
        if len(compressed_str) > 10000:  # Max 10KB — further truncate
            compressed["top_items"] = self._get_top_n(full_context, n=3)
            compressed["trends"] = compressed.get("trends", [])[:3]
            compressed["alerts"] = compressed.get("alerts", [])[:3]

        return compressed

    def _extract_summary(self, context: Dict) -> str:
        """Extract a one-line summary from context"""
        if "summary" in context:
            return context["summary"]
        return f"{self.dashboard_type} Intelligence Dashboard"

    def _extract_key_kpis(self, context: Dict) -> Dict:
        """Extract key KPIs from context — override in subclasses"""
        kpis = {}
        for key in ["total", "count", "amount", "value", "revenue", "profit"]:
            for ctx_key, ctx_value in context.items():
                if key in ctx_key.lower() and isinstance(ctx_value, (int, float)):
                    kpis[ctx_key] = ctx_value
        return dict(list(kpis.items())[:10])

    def _summarize_trends(self, context: Dict) -> List[Dict]:
        """Summarize trends from context — override in subclasses"""
        trends = []
        if "trends" in context:
            trend_data = context["trends"]
            if isinstance(trend_data, list):
                trends = trend_data[:5]
            elif isinstance(trend_data, dict):
                trends = [{"metric": k, "value": v} for k, v in list(trend_data.items())[:5]]
        return trends

    def _get_top_n(self, context: Dict, n: int = 5) -> Dict:
        """Get top N items from various categories — override in subclasses"""
        top_items = {}
        for key in ["top_products", "top_customers", "top_suppliers", "top_items"]:
            if key in context:
                items = context[key]
                if isinstance(items, list):
                    top_items[key] = items[:n]
        return top_items

    def _extract_alerts(self, context: Dict) -> List[Dict]:
        """Extract alerts and warnings from context"""
        alerts = []
        for key in ["alerts", "warnings", "anomalies", "risks", "issues"]:
            if key in context:
                alert_data = context[key]
                if isinstance(alert_data, list):
                    alerts.extend(alert_data[:3])
        return alerts[:5]

    def build_system_prompt(self, context: Optional[Dict] = None) -> str:
        """Build the system prompt, plus the playbook for the active surface."""
        from insights.agents.skills import skill_prompt_for

        ctx = context or self.compressed_context
        if self.config:
            prompt = self.config.get_system_prompt(ctx)
        else:
            prompt = self._get_default_system_prompt(ctx)

        # The skill tells the model which questions this tab exists to answer,
        # so it stops describing what a dashboard "usually" shows.
        skill = skill_prompt_for(self.dashboard_type, ctx)
        return f"{prompt}\n\n{skill}" if skill else prompt

    @abstractmethod
    def _get_default_system_prompt(self, context: Optional[Dict] = None) -> str:
        """Get default system prompt — must be implemented by subclasses"""
        pass

    def get_quick_actions(self) -> List[Dict]:
        """Get quick action buttons for the chat interface"""
        if self.config:
            return self.config.get_quick_actions()
        return self._get_default_quick_actions()

    @abstractmethod
    def _get_default_quick_actions(self) -> List[Dict]:
        """Get default quick actions — must be implemented by subclasses"""
        pass

    def get_routing_keywords(self) -> List[str]:
        """Get keywords that identify queries for this dashboard"""
        if self.config:
            return self.config.get_routing_keywords()
        return self._get_default_routing_keywords()

    @abstractmethod
    def _get_default_routing_keywords(self) -> List[str]:
        """Get default routing keywords — must be implemented by subclasses"""
        pass

    def execute(
        self,
        query: str,
        session_id: str,
        context: Optional[Dict] = None,
        conversation_history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a query against the AI model with dashboard context.

        Args:
            query: User's question
            session_id: Chat session ID for tracking
            context: Optional additional context
            conversation_history: Previous messages in conversation

        Returns:
            Dict with response, metadata, and any redirect info
        """
        from insights.ai.provider_factory import AIProviderFactory

        ctx = context or self.compressed_context

        messages = []
        system_prompt = self.build_system_prompt(ctx)
        messages.append({"role": "system", "content": system_prompt})

        if conversation_history and self.config and self.config.include_conversation_history:
            for msg in conversation_history[-5:]:
                messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

        messages.append({"role": "user", "content": query})

        model = None
        temperature = 0.7
        if self.config:
            if self.config.model_preference != "auto":
                model = self.config.model_preference
            temperature = self.config.temperature or 0.7

        client = AIProviderFactory.get_client()

        if not client.is_enabled():
            return {
                "success": False,
                "error": "AI Analytics is not enabled. Please configure your API key in Insights Settings.",
                "dashboard_type": self.dashboard_type,
                "session_id": session_id,
            }

        if not client.check_quota():
            return {
                "success": False,
                "error": "Daily AI quota exceeded. Please try again tomorrow or increase your quota in Insights Settings.",
                "dashboard_type": self.dashboard_type,
                "session_id": session_id,
            }

        try:
            import time as _time

            _start = _time.time()
            _last_error = None
            _rl_count = 0

            models_to_try = []
            preferred = model or client.primary_model
            models_to_try.append(preferred)
            if client.fallback_model and client.fallback_model != preferred:
                models_to_try.append(client.fallback_model)
            # get_available_models() is the BaseAIProvider contract every client
            # implements; FREE_MODELS only exists on OpenRouter and Ollama.
            for m in client.get_available_models():
                if m not in models_to_try:
                    models_to_try.append(m)

            for try_model in models_to_try:
                result = client.make_request(
                    messages=messages,
                    model=try_model,
                    temperature=temperature,
                )

                if result and "choices" in result:
                    response_text = (result["choices"][0]["message"].get("content") or "").strip()
                    if not response_text:
                        # A reasoning model can burn the whole output budget and
                        # return a blank message. Reporting that as success shows
                        # the user an empty bubble; try the next model instead.
                        _last_error = f"{try_model} returned an empty response"
                        continue

                    client.increment_quota()
                    _elapsed = round(_time.time() - _start, 2)
                    _tokens = result.get("usage", {}).get("total_tokens")

                    return {
                        "success": True,
                        "response": response_text,
                        "model_used": try_model,
                        "dashboard_type": self.dashboard_type,
                        "session_id": session_id,
                        "timestamp": now_datetime().isoformat(),
                        "processing_time": _elapsed,
                        "tokens_used": _tokens,
                    }
                else:
                    if isinstance(result, dict):
                        _last_error = result.get("request_error", _last_error)
                        if result.get("rate_limited"):
                            _rl_count += 1
                            if _rl_count >= 3:
                                return {
                                    "success": False,
                                    "error": "All free AI models are currently rate-limited. Please wait a few minutes and try again.",
                                    "dashboard_type": self.dashboard_type,
                                    "session_id": session_id,
                                }
                        else:
                            _rl_count = 0

            tried_names = ", ".join(models_to_try[:3])
            _safe_log_error(
                f"All AI models failed ({len(models_to_try)} tried). Models: {tried_names}...",
                "AI Model Failure",
            )
            error_detail = _last_error or "AI models are temporarily unavailable."
            return {
                "success": False,
                "error": f"{error_detail} (tried {len(models_to_try)} models)",
                "dashboard_type": self.dashboard_type,
                "session_id": session_id,
            }

        except Exception as e:
            _safe_log_error(f"Agent error: {str(e)[:300]}", "Agent Error")
            return {
                "success": False,
                "error": f"An error occurred while processing your request: {str(e)[:200]}",
                "dashboard_type": self.dashboard_type,
                "session_id": session_id,
            }

    def format_context_for_display(self) -> str:
        """Format compressed context as readable markdown for debugging"""
        if not self.compressed_context:
            return "No context available"

        lines = [f"## {self.dashboard_type} Dashboard Context\n"]

        if self.compressed_context.get("summary"):
            lines.append(f"**Summary:** {self.compressed_context['summary']}\n")

        if self.compressed_context.get("kpis"):
            lines.append("### Key Metrics")
            for key, value in self.compressed_context["kpis"].items():
                lines.append(f"- **{key}:** {value}")
            lines.append("")

        if self.compressed_context.get("alerts"):
            lines.append("### Alerts")
            for alert in self.compressed_context["alerts"]:
                if isinstance(alert, dict):
                    lines.append(f"- {alert.get('message', alert)}")
                else:
                    lines.append(f"- {alert}")
            lines.append("")

        return "\n".join(lines)
