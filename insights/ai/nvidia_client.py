# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
NVIDIA NIM Client for AI Analytics
Supports NVIDIA's OpenAI-compatible inference API (build.nvidia.com)
"""

import os
import requests
import frappe
from frappe.utils import cint
from typing import Dict, List, Optional, Any
from insights.ai.base_provider import BaseAIProvider


class NvidiaClient(BaseAIProvider):
	"""NVIDIA NIM client for Llama / Nemotron models"""

	provider_name = "NVIDIA"
	BASE_URL = "https://integrate.api.nvidia.com/v1"

	# Verified live against GET https://integrate.api.nvidia.com/v1/models (Aug 2026).
	# First entry is the recommended default.
	MODELS = [
		"nvidia/nemotron-3-super-120b-a12b",
		"nvidia/nemotron-3-ultra-550b-a55b",
		"nvidia/nemotron-3-nano-30b-a3b",
		"nvidia/llama-3.3-nemotron-super-49b-v1.5",
		"meta/llama-3.3-70b-instruct",
		"deepseek-ai/deepseek-v4-pro",
		"minimaxai/minimax-m3",
		"moonshotai/kimi-k2.6",
		"openai/gpt-oss-120b",
		"mistralai/mistral-nemotron",
	]

	DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
	DEFAULT_FALLBACK = "nvidia/nemotron-3-nano-30b-a3b"

	def __init__(self, provider: Optional[str] = None):
		self.settings = frappe.get_single("Insights Settings")
		self.api_key = (
			self.settings.get_password("nvidia_api_key") if getattr(self.settings, "nvidia_api_key", None)
			else os.environ.get("NVIDIA_API_KEY")
		)
		self.primary_model = getattr(self.settings, "nvidia_model", None) or self.DEFAULT_MODEL
		self.fallback_model = self.DEFAULT_FALLBACK

	def _get_headers(self) -> Dict[str, str]:
		return {
			"Authorization": f"Bearer {self.api_key}",
			"Content-Type": "application/json"
		}

	def is_enabled(self) -> bool:
		provider = getattr(self.settings, "ai_provider", None)
		return bool(
			getattr(self.settings, "enable_ai_analytics", False)
			and provider == "nvidia"
			and self.api_key
		)

	def check_quota(self) -> bool:
		daily_quota = cint(getattr(self.settings, "daily_ai_quota", 0)) or 100
		quota_used = cint(getattr(self.settings, "ai_quota_used", 0)) or 0
		return quota_used < daily_quota

	def increment_quota(self):
		frappe.db.set_single_value(
			"Insights Settings", "ai_quota_used",
			cint(getattr(self.settings, "ai_quota_used", 0)) + 1
		)
		frappe.db.commit()

	def get_available_models(self) -> List[str]:
		models = [self.primary_model]
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
				return {"request_error": "Invalid NVIDIA API key. Please check your configuration."}

			if response.status_code == 429:
				return {"request_error": "NVIDIA rate limit exceeded. Please wait a moment.", "rate_limited": True}

			if response.status_code != 200:
				error_text = response.text[:500] if response.text else "No response"
				return {"request_error": f"NVIDIA error (HTTP {response.status_code}): {error_text[:200]}"}

			result = response.json()

			if "error" in result:
				error_msg = result.get("error", {}).get("message", "Unknown error")
				return {"request_error": f"NVIDIA error: {str(error_msg)[:200]}"}

			# Validate content
			choices = result.get("choices", [])
			if choices:
				content = (choices[0].get("message") or {}).get("content", "")
				if not content or not content.strip():
					return {"request_error": f"Empty response from {model}"}

			return result

		except requests.exceptions.ConnectionError:
			return {"request_error": "Cannot connect to NVIDIA API. Check your network."}
		except requests.exceptions.Timeout:
			return {"request_error": f"NVIDIA timeout for model {model}. Try again later."}
		except Exception as e:
			return {"request_error": f"NVIDIA error: {str(e)[:200]}"}

	def test_connection(self) -> Dict[str, Any]:
		try:
			if not self.api_key:
				return {"success": False, "error": "NVIDIA API key not configured"}

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
					"message": "NVIDIA connection successful",
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
