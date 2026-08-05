# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
OpenRouter API Client for AI Analytics
Supports request queuing, model fallback, and response caching
"""

import json
import time
import os
import frappe
import requests
from frappe import _
from frappe.utils import cint, now_datetime, get_datetime
from collections import deque
from typing import Optional, Dict, Any, List


def _safe_log_error(message: str, title: str = "AI Analytics"):
    """Safely log an error, truncating to avoid CharacterLengthExceededError"""
    try:
        # Truncate title to max 100 chars (field limit is 140)
        safe_title = str(title)[:100] if title else "AI Analytics"
        # Truncate message to prevent huge error logs
        safe_message = str(message)[:5000] if message else "No message"
        frappe.log_error(title=safe_title, message=safe_message)
    except Exception:
        # If logging itself fails, just print to console
        print(f"[{title}] {message[:200]}..." if len(str(message)) > 200 else f"[{title}] {message}")


class OpenRouterClient:
    """OpenRouter API client with queuing, fallback, and caching.

    Implements BaseAIProvider interface while maintaining backward compatibility.
    """

    # Import-safe: avoid circular import at class level
    # BaseAIProvider methods are duck-typed via the same method signatures

    BASE_URL = "https://openrouter.ai/api/v1"

    provider_name = "OpenRouter"
    
    # Verified live against GET https://openrouter.ai/api/v1/models (Aug 2026).
    # The previous Jul-2025 list was almost entirely delisted upstream.
    FREE_MODELS = [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "inclusionai/ling-3.0-flash:free",
        "cohere/north-mini-code:free",
        "openai/gpt-oss-20b:free",
        "nvidia/nemotron-nano-9b-v2:free",
    ]

    # Paid models (fallback)
    PAID_MODELS = [
        "openai/gpt-5.6-terra",
        "openai/gpt-5.6-luna",
        "openai/gpt-5.6-sol",
        "anthropic/claude-sonnet-5",
        "anthropic/claude-haiku-4.5",
        "google/gemini-3.5-flash",
        "moonshotai/kimi-k3",
        "deepseek/deepseek-v4-pro",
    ]
    
    def __init__(self, provider: Optional[str] = None):
        self.settings = frappe.get_single("Insights Settings")
        self.api_key = (
            self.settings.get_password("openrouter_api_key") if self.settings.openrouter_api_key
            else os.environ.get("OPENROUTER_API_KEY")
        )
        self.primary_model = self.settings.ai_model or self.FREE_MODELS[0]
        self.fallback_model = self.settings.ai_model_fallback or self.FREE_MODELS[1]
        self.request_queue = deque()
        self.rate_limit_reset = None
        
    def is_enabled(self) -> bool:
        """Check if AI analytics is enabled and configured"""
        return bool(self.settings.enable_ai_analytics and self.api_key)
    
    def check_quota(self) -> bool:
        """Check if daily quota is available"""
        daily_quota = cint(self.settings.daily_ai_quota) or 100
        quota_used = cint(self.settings.ai_quota_used) or 0
        return quota_used < daily_quota
    
    def increment_quota(self):
        """Increment the daily quota usage"""
        frappe.db.set_single_value(
            "Insights Settings", 
            "ai_quota_used", 
            cint(self.settings.ai_quota_used) + 1
        )
        frappe.db.commit()
    
    def reset_daily_quota(self):
        """Reset daily quota (called by scheduler)"""
        frappe.db.set_single_value("Insights Settings", "ai_quota_used", 0)
        frappe.db.commit()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": frappe.utils.get_url(),
            "X-Title": "Frappe Insights AI Analytics"
        }
    
    def _make_request(self, messages: List[Dict], model: str, temperature: float = 0.7) -> Optional[Dict]:
        """Make API request to OpenRouter.

        Returns response dict with 'choices' on success, or dict with
        'request_error' key on failure.  Rate-limit (429) errors are
        returned immediately so the caller's model-fallback loop can
        move on to the next model without blocking.
        """
        try:
            response = requests.post(
                f"{self.BASE_URL}/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 2000
                },
                timeout=30
            )

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 10))
                self.rate_limit_reset = time.time() + retry_after
                return {"request_error": f"Rate limited on {model.split('/')[-1]}. Retry after {retry_after}s.",
                        "rate_limited": True}

            if response.status_code != 200:
                error_text = response.text[:500] if response.text else "No response"
                _safe_log_error(f"API Error {response.status_code}: {error_text}", "AI API Error")
                return {"request_error": f"OpenRouter API error (HTTP {response.status_code}): {error_text[:200]}"}

            result = response.json()

            # Check for error in response body
            if "error" in result:
                error_msg = result.get('error', {})
                if isinstance(error_msg, dict):
                    code = error_msg.get('code')
                    error_msg = error_msg.get('message', str(error_msg))
                    # Upstream 429 returned as JSON error
                    if code == 429:
                        return {"request_error": f"Upstream rate limit on {model.split('/')[-1]}.",
                                "rate_limited": True}
                error_msg = str(error_msg)[:500]
                _safe_log_error(f"API returned error: {error_msg}", "AI API Error")
                return {"request_error": f"OpenRouter error: {error_msg[:200]}"}

            # Validate that the response actually contains content
            choices = result.get("choices", [])
            if choices:
                content = (choices[0].get("message") or {}).get("content", "")
                if not content or not content.strip():
                    return {"request_error": f"Empty response from {model.split('/')[-1]}"}

            return result

        except requests.exceptions.Timeout:
            return {"request_error": f"Timeout calling {model.split('/')[-1]}"}
        except requests.exceptions.RequestException as e:
            _safe_log_error(f"Request Error: {str(e)[:300]}", "AI Request Error")
            return {"request_error": f"Network error: {str(e)[:200]}"}
        except Exception as e:
            _safe_log_error(f"Unexpected Error: {str(e)[:300]}", "AI Error")
            return {"request_error": f"Unexpected error: {str(e)[:200]}"}
    
    def chat(self, prompt: str, context: Optional[str] = None, use_cache: bool = True) -> Dict[str, Any]:
        """
        Send a chat request with automatic model fallback
        
        Args:
            prompt: The user prompt
            context: Optional context data (dashboard data, metrics, etc.)
            use_cache: Whether to use cached responses
            
        Returns:
            Dict with 'response', 'model_used', 'cached', 'error' keys
        """
        if not self.is_enabled():
            return {
                "response": None,
                "model_used": None,
                "cached": False,
                "error": "AI Analytics is not enabled or API key is missing"
            }
        
        if not self.check_quota():
            return {
                "response": None,
                "model_used": None,
                "cached": False,
                "error": "Daily AI quota exceeded"
            }
        
        # Check rate limit — wait it out if short, otherwise return error
        if self.rate_limit_reset and time.time() < self.rate_limit_reset:
            wait_secs = int(self.rate_limit_reset - time.time())
            if wait_secs <= 15:
                time.sleep(wait_secs + 1)
                self.rate_limit_reset = None
            else:
                return {
                    "response": None,
                    "model_used": None,
                    "cached": False,
                    "error": f"Rate limited. Please retry in {wait_secs} seconds."
                }
        
        # Build cache key (unified via CacheManager)
        from insights.cache_management.cache_manager import get_cached_data, cache_data as cm_cache_data
        cache_key = f"ai_analytics:{frappe.generate_hash(prompt + (context or ''), 10)}"
        
        # Check cache (CacheManager tiers)
        if use_cache:
            cached_response = get_cached_data(cache_key)
            if cached_response:
                return {
                    "response": cached_response.get("response"),
                    "model_used": cached_response.get("model"),
                    "cached": True,
                    "error": None
                }
        
        # Build messages
        messages = []
        if context:
            messages.append({
                "role": "system",
                "content": f"""You are an AI analytics assistant for business intelligence. 
Analyze the following data and provide actionable insights.
Be concise, specific, and focus on business value.
Format your response with clear sections using markdown.

Context Data:
{context}"""
            })
        else:
            messages.append({
                "role": "system",
                "content": """You are an AI analytics assistant for business intelligence.
Provide concise, actionable insights focused on business value.
Format your response with clear sections using markdown."""
            })
        
        messages.append({"role": "user", "content": prompt})
        
        # Try primary model first
        models_to_try = [self.primary_model, self.fallback_model]
        
        # Add additional fallbacks if both primary and fallback fail
        for model in self.FREE_MODELS + self.PAID_MODELS:
            if model not in models_to_try:
                models_to_try.append(model)
        
        consecutive_rate_limits = 0
        last_error = None
        for model in models_to_try:
            result = self._make_request(messages, model)
            if result and "choices" in result:
                response_text = result["choices"][0]["message"]["content"]
                
                # Cache the response (24 hours) via CacheManager
                cm_cache_data(cache_key, {"response": response_text, "model": model}, level="hot", ttl=86400)
                
                # Increment quota
                self.increment_quota()
                
                return {
                    "response": response_text,
                    "model_used": model,
                    "cached": False,
                    "error": None
                }
            elif isinstance(result, dict):
                last_error = result.get("request_error")
                if result.get("rate_limited"):
                    consecutive_rate_limits += 1
                    # If 3+ consecutive rate limits, likely a global account limit
                    if consecutive_rate_limits >= 3:
                        return {
                            "response": None,
                            "model_used": None,
                            "cached": False,
                            "error": "All free AI models are currently rate-limited. Please wait a few minutes and try again."
                        }
                else:
                    consecutive_rate_limits = 0
        
        return {
            "response": None,
            "model_used": None,
            "cached": False,
            "error": last_error or "All models failed to respond. Please try again shortly."
        }
    
    def chat_completion(self, messages: List[Dict], complexity: str = "Medium", **kwargs) -> str:
        """
        Generate a chat completion from a list of messages.
        Compatibility method used by standalone agents (HR, Executive, etc.).
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            complexity: Query complexity hint (unused, kept for API compat)
            
        Returns:
            The AI response text, or an error description string
        """
        if not self.is_enabled():
            return "AI Analytics is not enabled. Please configure your OpenRouter API key."
        
        if not self.check_quota():
            return "Daily AI quota exceeded. Please try again tomorrow."

        # Build model list
        models_to_try = [self.primary_model, self.fallback_model]
        for m in self.FREE_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        consecutive_rate_limits = 0
        last_error = None
        for model in models_to_try:
            result = self._make_request(messages, model)
            if result and "choices" in result:
                self.increment_quota()
                return result["choices"][0]["message"]["content"]
            elif isinstance(result, dict):
                last_error = result.get("request_error")
                if result.get("rate_limited"):
                    consecutive_rate_limits += 1
                    if consecutive_rate_limits >= 3:
                        return "All free AI models are currently rate-limited. Please wait a few minutes and try again."
                else:
                    consecutive_rate_limits = 0

        return last_error or "All AI models are temporarily unavailable. Please try again later."

    def generate_response(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        """
        Generate AI response from a prompt string.
        Compatibility method used by Marketing and Manufacturing agents.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            
        Returns:
            The AI response text
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat_completion(messages)

    def is_available(self) -> bool:
        """Check if AI is available (enabled + has API key + has quota).
        Compatibility method used by ESG agent."""
        return self.is_enabled() and self.check_quota()

    def get_available_models(self) -> List[str]:
        """Get ordered list of models to try (BaseAIProvider interface)"""
        models = [self.primary_model, self.fallback_model]
        for m in self.FREE_MODELS + self.PAID_MODELS:
            if m not in models:
                models.append(m)
        return models

    def make_request(self, messages: List[Dict], model: str,
                     temperature: float = 0.7, max_tokens: int = 2000) -> Optional[Dict]:
        """BaseAIProvider interface - delegates to _make_request"""
        return self._make_request(messages, model, temperature)

    def test_connection(self) -> Dict[str, Any]:
        """Test the OpenRouter API connection"""
        try:
            if not self.api_key:
                return {"success": False, "error": "OpenRouter API key not configured"}

            response = requests.get(
                f"{self.BASE_URL}/auth/key",
                headers=self._get_headers(),
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "message": "OpenRouter connection successful",
                    "data": {
                        "credits": data.get("data", {}).get("credits", 0),
                        "usage": data.get("data", {}).get("usage", 0)
                    }
                }
            else:
                return {"success": False, "error": f"API returned status {response.status_code}"}
        except requests.exceptions.Timeout:
            return {"success": False, "error": "Connection timed out"}
        except Exception as e:
            return {"success": False, "error": f"Connection failed: {str(e)[:200]}"}

    def get_insights(self, prompt: str = None, query: str = None, context: str = None, **kwargs) -> Dict[str, Any]:
        """
        Generate insights from a prompt with optional context.
        Compatibility method used by ESG agent.
        
        Args:
            prompt: Analysis prompt (positional usage)
            query: Analysis prompt (keyword usage by ESG agent)
            context: Optional context data
            **kwargs: Extra args like context_type, max_tokens (ignored)
            
        Returns:
            Dict with 'status' and 'insights' keys for compatibility
        """
        actual_prompt = query or prompt or ""
        messages = [
            {
                "role": "system",
                "content": "You are an AI analytics assistant. Provide detailed, actionable insights."
            }
        ]
        if context:
            messages[0]["content"] += f"\n\nContext:\n{context}"
        messages.append({"role": "user", "content": actual_prompt})
        response_text = self.chat_completion(messages)
        # Return in dict format expected by ESG agent
        return {
            "status": "success",
            "insights": response_text
        }

    def analyze_data(self, data: Dict[str, Any], analysis_type: str) -> Dict[str, Any]:
        """
        Analyze data with AI based on analysis type
        
        Args:
            data: The data to analyze (metrics, KPIs, trends)
            analysis_type: Type of analysis (financial, sales, inventory, etc.)
            
        Returns:
            AI analysis result
        """
        prompts = {
            "financial": """Analyze this financial data and provide:
1. Key Financial Health Indicators
2. Cash Flow Analysis
3. Profitability Trends
4. Risk Areas and Recommendations
5. Actionable Next Steps""",
            
            "sales": """Analyze this sales data and provide:
1. Sales Performance Summary
2. Top Performing Products/Customers
3. Sales Trends and Patterns
4. Growth Opportunities
5. Actionable Recommendations""",
            
            "procurement": """Analyze this procurement data and provide:
1. Spending Analysis Summary
2. Supplier Performance Overview
3. Cost Optimization Opportunities
4. Risk Areas (dependency, pricing)
5. Strategic Recommendations""",
            
            "inventory": """Analyze this inventory data and provide:
1. Stock Health Summary
2. Slow Moving & Dead Stock Analysis
3. Reorder Recommendations
4. Storage Optimization Tips
5. Demand Forecasting Insights""",
            
            "production": """Analyze this production data and provide:
1. Production Efficiency Summary
2. Bottleneck Identification
3. Quality Metrics Analysis
4. Resource Utilization Insights
5. Improvement Recommendations""",
            
            "customer": """Analyze this customer data and provide:
1. Customer Segmentation Summary
2. Retention & Churn Analysis
3. Customer Lifetime Value Insights
4. Engagement Patterns
5. Growth Strategies"""
        }
        
        prompt = prompts.get(analysis_type, prompts["financial"])
        context = json.dumps(data, indent=2, default=str)
        
        return self.chat(prompt, context)


# API endpoints for frontend
@frappe.whitelist()
def get_ai_analysis(dashboard_type: str, data: str = None) -> Dict[str, Any]:
    """
    Get AI analysis for a dashboard
    
    Args:
        dashboard_type: Type of analysis (financial, sales, etc.)
        data: JSON string of data to analyze
        
    Returns:
        AI analysis result
    """
    client = OpenRouterClient()
    
    if data:
        try:
            data_dict = json.loads(data)
        except json.JSONDecodeError:
            data_dict = {}
    else:
        data_dict = {}
    
    return client.analyze_data(data_dict, dashboard_type)


@frappe.whitelist()
def chat_with_ai(prompt: str, context: str = None) -> Dict[str, Any]:
    """
    Chat with AI using dashboard context
    
    Args:
        prompt: User's question or prompt
        context: Optional JSON context data
        
    Returns:
        AI response
    """
    client = OpenRouterClient()
    return client.chat(prompt, context)


@frappe.whitelist()
def get_ai_status() -> Dict[str, Any]:
    """Get AI analytics status and quota information"""
    settings = frappe.get_single("Insights Settings")
    provider = getattr(settings, "ai_provider", "openrouter")

    configured = False
    primary_model = ""
    fallback_model = ""

    if provider == "openrouter":
        configured = bool(settings.openrouter_api_key)
        primary_model = settings.ai_model
        fallback_model = settings.ai_model_fallback
    elif provider in ("ollama", "ollama_cloud"):
        configured = bool(getattr(settings, "ollama_base_url", ""))
        primary_model = getattr(settings, "ollama_model", "")
    elif provider == "moonshot":
        configured = bool(getattr(settings, "moonshot_api_key", ""))
        primary_model = getattr(settings, "moonshot_model", "")
    elif provider == "openai":
        configured = bool(getattr(settings, "openai_api_key", ""))
        primary_model = getattr(settings, "openai_model", "")
    elif provider == "nvidia":
        configured = bool(getattr(settings, "nvidia_api_key", ""))
        primary_model = getattr(settings, "nvidia_model", "")

    return {
        "enabled": bool(settings.enable_ai_analytics),
        "configured": configured,
        "provider": provider,
        "primary_model": primary_model,
        "fallback_model": fallback_model,
        "daily_quota": cint(settings.daily_ai_quota) or 100,
        "quota_used": cint(settings.ai_quota_used) or 0,
        "quota_remaining": max(0, (cint(settings.daily_ai_quota) or 100) - (cint(settings.ai_quota_used) or 0)),
        "last_refresh": settings.last_ai_refresh,
        "refresh_schedule": settings.refresh_schedule
    }


@frappe.whitelist()
def test_connection(provider: str = None) -> Dict[str, Any]:
    """Test AI provider connection. Pass provider to test a specific one
    without needing to save settings first."""
    try:
        from insights.ai.provider_factory import AIProviderFactory
        if provider and provider in ("openrouter", "ollama", "ollama_cloud", "moonshot", "openai", "nvidia"):
            client = AIProviderFactory.get_provider(provider)
        else:
            client = AIProviderFactory.get_client()
        return client.test_connection()
    except Exception as e:
        return {
            "success": False,
            "error": f"Connection test failed: {str(e)}"
        }
