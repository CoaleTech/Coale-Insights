# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Moonshot AI (Kimi) Client for AI Analytics
Supports direct Moonshot API with OpenAI-compatible endpoint
"""

import os
import requests
import frappe
from frappe.utils import cint
from typing import Dict, List, Optional, Any
from insights.ai.base_provider import BaseAIProvider


class MoonshotClient(BaseAIProvider):
    """Moonshot AI client for Kimi models"""

    provider_name = "Moonshot"
    BASE_URL = "https://api.moonshot.cn/v1"

    # Kimi K2 (default) plus legacy Moonshot v1 models for backwards-compat.
    # Order matters — first entry is the recommended default.
    MODELS = [
        "kimi-k2-0905-preview",
        "kimi-k2-0711-preview",
        "kimi-k2-turbo-preview",
        "moonshot-v1-8k",
        "moonshot-v1-32k",
        "moonshot-v1-128k",
        "moonshot-v1-auto",
    ]

    DEFAULT_MODEL = "kimi-k2-0905-preview"

    def __init__(self):
        self.settings = frappe.get_single("Insights Settings")
        self.api_key = (
            getattr(self.settings, "moonshot_api_key", None)
            or os.environ.get("MOONSHOT_API_KEY")
        )
        self.default_model = getattr(self.settings, "moonshot_model", None) or self.DEFAULT_MODEL
        self.primary_model = self.default_model
        # Fallback to the older K2 preview (still K2 family) before auto
        self.fallback_model = "kimi-k2-0711-preview"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def is_enabled(self) -> bool:
        provider = getattr(self.settings, "ai_provider", None)
        return bool(
            self.settings.enable_ai_analytics
            and provider == "moonshot"
            and self.api_key
        )

    def check_quota(self) -> bool:
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
        models = [self.default_model]
        if self.fallback_model and self.fallback_model not in models:
            models.append(self.fallback_model)
        for m in self.MODELS:
            if m not in models:
                models.append(m)
        return models

    def make_request(self, messages: List[Dict], model: str,
                     temperature: float = 0.7, max_tokens: int = 2000) -> Optional[Dict]:
        try:
            response = requests.post(
                f"{self.BASE_URL}/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False
                },
                timeout=120
            )

            if response.status_code == 401:
                return {"request_error": "Invalid Moonshot API key. Please check your configuration."}

            if response.status_code == 429:
                return {"request_error": "Moonshot rate limit exceeded. Please wait a moment.", "rate_limited": True}

            if response.status_code != 200:
                error_text = response.text[:500] if response.text else "No response"
                return {"request_error": f"Moonshot error (HTTP {response.status_code}): {error_text[:200]}"}

            result = response.json()

            if "error" in result:
                error_msg = result.get("error", {}).get("message", "Unknown error")
                return {"request_error": f"Moonshot error: {str(error_msg)[:200]}"}

            return result

        except requests.exceptions.ConnectionError:
            return {"request_error": "Cannot connect to Moonshot API. Check your network."}
        except requests.exceptions.Timeout:
            return {"request_error": f"Moonshot timeout for model {model}. Try again later."}
        except Exception as e:
            return {"request_error": f"Moonshot error: {str(e)[:200]}"}

    def test_connection(self) -> Dict[str, Any]:
        try:
            if not self.api_key:
                return {"success": False, "error": "Moonshot API key not configured"}

            response = requests.get(
                f"{self.BASE_URL}/models",
                headers=self._get_headers(),
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                models = [m.get("id", "") for m in data.get("data", [])]
                return {
                    "success": True,
                    "message": "Moonshot connection successful",
                    "data": {
                        "models": models,
                        "model_count": len(models)
                    }
                }
            elif response.status_code == 401:
                return {"success": False, "error": "Invalid API key"}
            else:
                return {"success": False, "error": f"API returned status {response.status_code}"}

        except requests.exceptions.Timeout:
            return {"success": False, "error": "Connection timed out"}
        except Exception as e:
            return {"success": False, "error": f"Connection failed: {str(e)[:200]}"}
