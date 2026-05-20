# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Ollama Local AI Client for AI Analytics
Supports local LLM inference via Ollama API
"""

import os
import json
import requests
import frappe
from frappe.utils import cint
from typing import Dict, List, Optional, Any
from insights.ai.base_provider import BaseAIProvider


def _safe_log_error(message: str, title: str = "Ollama Client"):
    try:
        frappe.log_error(title=str(title)[:100], message=str(message)[:5000])
    except Exception:
        print(f"[{title}] {str(message)[:200]}")


class OllamaClient(BaseAIProvider):
    """Ollama local AI client for local LLM inference"""

    provider_name = "Ollama"

    DEFAULT_MODELS = [
        "llama3.1",
        "llama3.1:70b",
        "mistral",
        "codellama",
        "gemma2",
    ]
    # Aliases for compatibility with agents/__init__.py which references FREE_MODELS
    FREE_MODELS = DEFAULT_MODELS
    PAID_MODELS: list = []

    def __init__(self):
        self.settings = frappe.get_single("Insights Settings")
        provider = getattr(self.settings, "ai_provider", None)
        self.is_cloud = provider == "ollama_cloud"
        # Cloud default differs from local default
        default_url = "https://ollama.com" if self.is_cloud else "http://localhost:11434"
        self.base_url = (
            getattr(self.settings, "ollama_base_url", None)
            or os.environ.get("OLLAMA_BASE_URL")
            or default_url
        ).rstrip("/")
        # API key is only required for Ollama Cloud (bearer auth on ollama.com)
        self.api_key = None
        if self.is_cloud:
            self.api_key = (
                self.settings.get_password("ollama_api_key", raise_exception=False)
                if getattr(self.settings, "ollama_api_key", None)
                else None
            ) or os.environ.get("OLLAMA_API_KEY")
        self.default_model = getattr(self.settings, "ollama_model", None) or "llama3.1"
        # Compatibility attrs expected by agents/__init__.py and dashboard_chat.py
        self.primary_model = self.default_model
        self.fallback_model = None
        # Compatibility for dashboard_chat.py streaming (uses OpenAI-compatible endpoint)
        self.BASE_URL = f"{self.base_url}/v1"
        # Discover installed models so FREE_MODELS only contains pullable models
        self._installed_models = self._discover_models()
        self.FREE_MODELS = self._installed_models or [self.default_model]

    def _get_headers(self) -> Dict[str, str]:
        """Returns request headers including bearer auth for Ollama Cloud."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _discover_models(self) -> List[str]:
        """Probe /api/tags to list installed Ollama models. Returns [] on any error."""
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                headers=self._get_headers(),
                timeout=5,
            )
            if response.status_code != 200:
                return []
            return [m.get("name", "") for m in response.json().get("models", []) if m.get("name")]
        except Exception:
            return []

    def _make_request(self, messages: List[Dict], model: str, temperature: float = 0.7) -> Optional[Dict]:
        """Compatibility alias - agents/__init__.py calls _make_request directly"""
        return self.make_request(messages, model, temperature)

    def is_enabled(self) -> bool:
        provider = getattr(self.settings, "ai_provider", None)
        return bool(
            self.settings.enable_ai_analytics
            and provider in ("ollama", "ollama_cloud")
        )

    def check_quota(self) -> bool:
        """Ollama is local - quota is optional but we still track usage"""
        daily_quota = cint(self.settings.daily_ai_quota) or 100
        quota_used = cint(self.settings.ai_quota_used) or 0
        return quota_used < daily_quota

    def increment_quota(self):
        frappe.db.set_single_value(
            "Insights Settings", "ai_quota_used",
            cint(self.settings.ai_quota_used) + 1
        )
        frappe.db.commit()

    def get_available_models(self) -> List[str]:
        """Get available Ollama models - tries to discover from API first"""
        models = [self.default_model]

        try:
            response = requests.get(f"{self.base_url}/api/tags", headers=self._get_headers(), timeout=5)
            if response.status_code == 200:
                data = response.json()
                for m in data.get("models", []):
                    name = m.get("name", "")
                    if name and name not in models:
                        models.append(name)
        except Exception:
            pass

        # Add defaults as fallback
        for m in self.DEFAULT_MODELS:
            if m not in models:
                models.append(m)

        return models

    def make_request(self, messages: List[Dict], model: str,
                     temperature: float = 0.7, max_tokens: int = 2000) -> Optional[Dict]:
        """Make request to Ollama. Tries OpenAI-compatible endpoint first,
        falls back to native /api/chat if content is empty (e.g. thinking models)."""
        try:
            # Try OpenAI-compatible endpoint first
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False
                },
                timeout=180
            )

            if response.status_code == 404:
                return {"request_error": f"Model '{model}' not found. Pull it with: ollama pull {model}"}

            if response.status_code != 200:
                error_text = response.text[:500] if response.text else "No response"
                _safe_log_error(f"Ollama API Error {response.status_code}: {error_text}", "Ollama API Error")
                return {"request_error": f"Ollama error (HTTP {response.status_code}): {error_text[:200]}"}

            result = response.json()

            if "error" in result:
                error_msg = result.get("error", "Unknown error")
                return {"request_error": f"Ollama error: {str(error_msg)[:200]}"}

            # Check if we got content
            choices = result.get("choices", [])
            if choices:
                content = (choices[0].get("message") or {}).get("content", "")
                if content and content.strip():
                    return result

            # Empty content - fall back to native Ollama API (handles thinking models)
            return self._native_chat(messages, model, temperature)

        except requests.exceptions.ConnectionError:
            return {"request_error": f"Cannot connect to Ollama at {self.base_url}. Is Ollama running?"}
        except requests.exceptions.Timeout:
            return {"request_error": f"Ollama timeout for model {model}. Try a smaller model."}
        except Exception as e:
            _safe_log_error(f"Ollama Error: {str(e)[:300]}", "Ollama Error")
            return {"request_error": f"Ollama error: {str(e)[:200]}"}

    def _native_chat(self, messages: List[Dict], model: str,
                     temperature: float = 0.7) -> Optional[Dict]:
        """Fallback to native Ollama /api/chat for models that return empty via OpenAI endpoint."""
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                headers=self._get_headers(),
                json={
                    "model": model,
                    "messages": messages,
                    "options": {"temperature": temperature},
                    "stream": False
                },
                timeout=180
            )

            if response.status_code != 200:
                return {"request_error": f"Ollama native API error (HTTP {response.status_code})"}

            data = response.json()
            content = data.get("message", {}).get("content", "")

            if not content or not content.strip():
                return {"request_error": f"Empty response from Ollama {model}"}

            # Convert to OpenAI-compatible format
            return {
                "choices": [{
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop"
                }],
                "model": model
            }

        except requests.exceptions.Timeout:
            return {"request_error": f"Ollama timeout for model {model}. Try a smaller model."}
        except Exception as e:
            return {"request_error": f"Ollama native API error: {str(e)[:200]}"}

    def test_connection(self) -> Dict[str, Any]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", headers=self._get_headers(), timeout=10)

            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                return {
                    "success": True,
                    "message": f"Ollama connected at {self.base_url}",
                    "data": {
                        "models": models,
                        "model_count": len(models)
                    }
                }
            else:
                return {"success": False, "error": f"Ollama returned status {response.status_code}"}

        except requests.exceptions.ConnectionError:
            return {"success": False, "error": f"Cannot connect to Ollama at {self.base_url}. Is Ollama running?"}
        except requests.exceptions.Timeout:
            return {"success": False, "error": "Ollama connection timed out"}
        except Exception as e:
            return {"success": False, "error": f"Ollama connection failed: {str(e)[:200]}"}
