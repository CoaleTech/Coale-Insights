# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Base AI Provider Interface
Abstract base for all AI providers (OpenRouter, Ollama)
"""

import litellm
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class BaseAIProvider(ABC):
    """Abstract base for all AI providers"""

    provider_name: str = ""

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if this provider is enabled and configured"""
        pass

    @abstractmethod
    def check_quota(self) -> bool:
        """Check if daily quota is available"""
        pass

    @abstractmethod
    def increment_quota(self):
        """Increment the daily quota usage"""
        pass

    @abstractmethod
    def get_available_models(self) -> List[str]:
        """Get list of available models for this provider"""
        pass

    @abstractmethod
    def make_request(self, messages: List[Dict], model: str,
                     temperature: float = 0.7, max_tokens: int = 2000) -> Optional[Dict]:
        """Make a chat completion request.

        Returns response dict with 'choices' on success, or dict with
        'request_error' key on failure.
        """
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Test the provider connection"""
        pass

    # OpenAI's /v1/embeddings hard cap is 2048 inputs per request (verified
    # against platform.openai.com/docs/api-reference/embeddings). Stay well
    # under that to keep per-request token cost predictable across providers.
    _EMBED_BATCH_SIZE = 256

    # litellm `model=` routing strings verified against the installed
    # litellm 1.98.0 via `litellm.get_llm_provider` -- a `custom_llm_provider`
    # that litellm doesn't recognise falls back to the OpenAI provider, which
    # then 401s, so these are the canonical prefixes.
    _EMBEDDING_MODELS = {
        # `openai/` is litellm's default, but be explicit so a copy-paste
        # mistake doesn't silently route OpenAI traffic elsewhere.
        "openai": "text-embedding-3-small",
        # Ollama's local daemon serves any model the operator has pulled;
        # nomic-embed-text is the canonical embedding model in their library.
        "ollama": "nomic-embed-text",
        "ollama_cloud": "nomic-embed-text",
        # OpenRouter forwards to upstream providers; the OpenAI embedding
        # model is the most reliable choice on their catalog.
        "openrouter": "openai/text-embedding-3-small",
        # NVIDIA's NIM catalog serves nv-embed-v1; litellm needs the
        # `nvidia/` prefix to pick the right provider.
        "nvidia": "nvidia/nv-embed-v1",
    }
    _NO_EMBEDDING_PROVIDERS = frozenset({"moonshot"})

    def embed_documents(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """Embed a batch of texts for the Knowledge Base vector store.

        Default implementation routes through `litellm.embedding(...)` so the
        Knowledge Base uses whichever chat provider Insights Settings has
        configured (openai, ollama local, ollama cloud, openrouter, nvidia).

        Splits `texts` into `_EMBED_BATCH_SIZE`-sized chunks to stay under
        OpenAI's per-request 2048-input cap and litellm's per-call timeout,
        and lets litellm's own `max_retries` handle transient 429/5xx
        (litellm 1.98.0 only retries on the `**kwargs` path; the function
        signature has no explicit `num_retries` parameter).
        """
        if not texts:
            return []

        provider_key = (self.provider_name or "").strip().lower()
        if provider_key in self._NO_EMBEDDING_PROVIDERS:
            raise NotImplementedError(
                f"{self.provider_name} does not support embeddings. "
                "Switch 'AI Provider' in Insights Settings to one of: "
                + ", ".join(sorted(self._EMBEDDING_MODELS)) + "."
            )
        if provider_key not in self._EMBEDDING_MODELS:
            raise NotImplementedError(
                f"{self.provider_name} has no configured embedding model. "
                "Pass `model=` to override the default, or add an entry to "
                "BaseAIProvider._EMBEDDING_MODELS."
            )

        chosen_model = model or self._EMBEDDING_MODELS[provider_key]
        api_key = getattr(self, "api_key", None)
        api_base = (
            getattr(self, "base_url", None)
            or getattr(self, "BASE_URL", None)
        )
        if provider_key == "ollama":
            api_base = api_base or "http://localhost:11434"
            if not getattr(self, "is_cloud", False):
                # Local Ollama rejects Authorization headers -- never
                # forward a stray api_key to the unauthenticated daemon,
                # even if one is set on this instance. Ollama Cloud sets a
                # real bearer token (self.is_cloud, see
                # OllamaClient.__init__), which must survive so cloud
                # embeddings still authenticate.
                api_key = None

        embeddings: List[List[float]] = []
        for start in range(0, len(texts), self._EMBED_BATCH_SIZE):
            batch = texts[start : start + self._EMBED_BATCH_SIZE]
            response = litellm.embedding(
                model=chosen_model,
                input=batch,
                api_key=api_key,
                api_base=api_base,
                # litellm 1.98.0 retries on 429/5xx/timeouts when this is set;
                # default None means zero retries, which masks transient blips.
                max_retries=3,
            )
            data = response.data if hasattr(response, "data") else response["data"]
            # Preserve input order -- some providers (OpenRouter in particular)
            # don't guarantee response order, so sort by `index` defensively.
            ordered = sorted(data, key=lambda d: d["index"])
            embeddings.extend(item["embedding"] for item in ordered)
        return embeddings

    def chat(self, prompt: str, context: Optional[str] = None, use_cache: bool = True) -> Dict[str, Any]:
        """Send a chat request with automatic model fallback.

        Default implementation with model fallback cascade.
        Providers can override for custom behavior.
        """
        if not self.is_enabled():
            return {
                "response": None, "model_used": None, "cached": False,
                "error": f"{self.provider_name} is not enabled or not configured"
            }

        if not self.check_quota():
            return {
                "response": None, "model_used": None, "cached": False,
                "error": "Daily AI quota exceeded"
            }

        # Check cache
        import frappe
        from insights.cache_management.cache_manager import get_cached_data, cache_data as cm_cache_data
        cache_key = f"ai_analytics:{frappe.generate_hash(prompt + (context or ''), 10)}"

        if use_cache:
            cached_response = get_cached_data(cache_key)
            if cached_response:
                return {
                    "response": cached_response.get("response"),
                    "model_used": cached_response.get("model"),
                    "cached": True, "error": None
                }

        # Build messages
        messages = []
        if context:
            messages.append({
                "role": "system",
                "content": f"You are an AI analytics assistant for business intelligence.\nAnalyze the following data and provide actionable insights.\nBe concise, specific, and focus on business value.\nFormat your response with clear sections using markdown.\n\nContext Data:\n{context}"
            })
        else:
            messages.append({
                "role": "system",
                "content": "You are an AI analytics assistant for business intelligence.\nProvide concise, actionable insights focused on business value.\nFormat your response with clear sections using markdown."
            })
        messages.append({"role": "user", "content": prompt})

        # Try models with fallback
        models = self.get_available_models()
        consecutive_rate_limits = 0
        last_error = None

        for model in models:
            result = self.make_request(messages, model)
            if result and "choices" in result:
                response_text = result["choices"][0]["message"]["content"]
                cm_cache_data(cache_key, {"response": response_text, "model": model}, level="hot", ttl=86400)
                self.increment_quota()
                return {
                    "response": response_text, "model_used": model,
                    "cached": False, "error": None
                }
            elif isinstance(result, dict):
                last_error = result.get("request_error")
                if result.get("rate_limited"):
                    consecutive_rate_limits += 1
                    if consecutive_rate_limits >= 3:
                        return {
                            "response": None, "model_used": None, "cached": False,
                            "error": "All AI models are currently rate-limited. Please wait a few minutes."
                        }
                else:
                    consecutive_rate_limits = 0

        return {
            "response": None, "model_used": None, "cached": False,
            "error": last_error or "All models failed to respond."
        }

    def chat_completion(self, messages: List[Dict], complexity: str = "Medium", **kwargs) -> str:
        """Generate a chat completion from messages. Returns response text or error string."""
        if not self.is_enabled():
            return f"{self.provider_name} is not enabled. Please configure it in Insights Settings."
        if not self.check_quota():
            return "Daily AI quota exceeded. Please try again tomorrow."

        models = self.get_available_models()
        consecutive_rate_limits = 0
        last_error = None

        for model in models:
            result = self.make_request(messages, model)
            if result and "choices" in result:
                self.increment_quota()
                return result["choices"][0]["message"]["content"]
            elif isinstance(result, dict):
                last_error = result.get("request_error")
                if result.get("rate_limited"):
                    consecutive_rate_limits += 1
                    if consecutive_rate_limits >= 3:
                        return "All AI models are currently rate-limited. Please wait a few minutes."
                else:
                    consecutive_rate_limits = 0

        return last_error or "All AI models are temporarily unavailable."

    def generate_response(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        """Generate AI response from a prompt string."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat_completion(messages)

    def is_available(self) -> bool:
        """Check if AI is available (enabled + has quota)."""
        return self.is_enabled() and self.check_quota()

    def get_insights(self, prompt: str = None, query: str = None, context: str = None, **kwargs) -> Dict[str, Any]:
        """Generate insights from a prompt. Compatibility method for ESG agent."""
        import json
        actual_prompt = query or prompt or ""
        messages = [{"role": "system", "content": "You are an AI analytics assistant. Provide detailed, actionable insights."}]
        if context:
            messages[0]["content"] += f"\n\nContext:\n{context}"
        messages.append({"role": "user", "content": actual_prompt})
        response_text = self.chat_completion(messages)
        return {"status": "success", "insights": response_text}

    def analyze_data(self, data: Dict[str, Any], analysis_type: str) -> Dict[str, Any]:
        """Analyze data with AI based on analysis type."""
        import json
        prompts = {
            "financial": "Analyze this financial data and provide:\n1. Key Financial Health Indicators\n2. Cash Flow Analysis\n3. Profitability Trends\n4. Risk Areas and Recommendations\n5. Actionable Next Steps",
            "sales": "Analyze this sales data and provide:\n1. Sales Performance Summary\n2. Top Performing Products/Customers\n3. Sales Trends and Patterns\n4. Growth Opportunities\n5. Actionable Recommendations",
            "procurement": "Analyze this procurement data and provide:\n1. Spending Analysis Summary\n2. Supplier Performance Overview\n3. Cost Optimization Opportunities\n4. Risk Areas (dependency, pricing)\n5. Strategic Recommendations",
            "inventory": "Analyze this inventory data and provide:\n1. Stock Health Summary\n2. Slow Moving & Dead Stock Analysis\n3. Reorder Recommendations\n4. Storage Optimization Tips\n5. Demand Forecasting Insights",
            "production": "Analyze this production data and provide:\n1. Production Efficiency Summary\n2. Bottleneck Identification\n3. Quality Metrics Analysis\n4. Resource Utilization Insights\n5. Improvement Recommendations",
            "customer": "Analyze this customer data and provide:\n1. Customer Segmentation Summary\n2. Retention & Churn Analysis\n3. Customer Lifetime Value Insights\n4. Engagement Patterns\n5. Growth Strategies"
        }
        prompt = prompts.get(analysis_type, prompts["financial"])
        context = json.dumps(data, indent=2, default=str)
        return self.chat(prompt, context)
