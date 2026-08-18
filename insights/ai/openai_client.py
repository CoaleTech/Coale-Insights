# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
OpenAI Client for AI Analytics
Supports direct OpenAI API with OpenAI-compatible endpoint
"""

import os
import json
import uuid
import requests
import frappe
from frappe.utils import cint
from typing import Dict, List, Optional, Any
from insights.ai.base_provider import BaseAIProvider
from insights.ai.openai_codex_auth import SUBSCRIPTION_MODELS


class OpenAIClient(BaseAIProvider):
	"""OpenAI client for GPT models"""

	provider_name = "OpenAI"
	# Default endpoint. Overridable per-site so the provider can target any
	# OpenAI-compatible gateway (e.g. an omp auth-gateway fronting a ChatGPT
	# Plus/Pro subscription) instead of the metered api.openai.com key path.
	BASE_URL = "https://api.openai.com/v1"
	# ChatGPT Plus/Pro subscription traffic goes to the ChatGPT backend instead;
	# api.openai.com does not accept subscription OAuth tokens.
	CHATGPT_BACKEND = "https://chatgpt.com/backend-api/codex"

	# Current OpenAI catalog, verified against platform.openai.com (Aug 2026).
	# Order matters: first is the recommended default.
	MODELS = [
		"gpt-5.6-terra",
		"gpt-5.6-sol",
		"gpt-5.6-luna",
		"gpt-5.5",
		"gpt-5.4",
		"gpt-5.4-mini",
		"gpt-5.4-nano",
		"gpt-4.1",
		"gpt-4.1-mini",
		"gpt-4o",
		"gpt-4o-mini",
	]

	# GPT-5.x / o-series bill hidden reasoning tokens against the output budget
	# and reject `temperature` + `max_tokens` on Chat Completions.
	REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")
	# OpenAI recommends reserving >=25k tokens for reasoning plus visible output.
	REASONING_MIN_OUTPUT_TOKENS = 25000

	DEFAULT_MODEL = "gpt-5.6-terra"
	DEFAULT_FALLBACK = "gpt-5.6-luna"

	def __init__(self, provider: Optional[str] = None):
		self.settings = frappe.get_single("Insights Settings")
		self.auth_mode = getattr(self.settings, "openai_auth_mode", None) or "API Key"
		self.is_subscription = self.auth_mode == "ChatGPT Subscription"
		self.account_id = ""

		if self.is_subscription:
			from insights.ai.openai_codex_auth import get_access_token

			self.BASE_URL = self.CHATGPT_BACKEND
			self.api_key = get_access_token(self.settings)
			self.account_id = getattr(self.settings, "openai_oauth_account_id", "") or ""
		else:
			self.BASE_URL = (
				getattr(self.settings, "openai_base_url", None)
				or os.environ.get("OPENAI_BASE_URL")
				or self.BASE_URL
			).rstrip("/")
			self.api_key = (
				self.settings.get_password("openai_api_key") if getattr(self.settings, "openai_api_key", None)
				else os.environ.get("OPENAI_API_KEY")
			)

		self.primary_model = getattr(self.settings, "openai_model", None) or self.DEFAULT_MODEL
		self.fallback_model = self.DEFAULT_FALLBACK
		if self.is_subscription:
			# Coerce to what the Codex backend will actually serve, here at the
			# single place both models are set: callers build their own candidate
			# list by prepending `primary_model`/`fallback_model` before they ever
			# consult get_available_models(), so filtering only the getter leaks
			# an unsupported id straight into the first request.
			if self.primary_model not in SUBSCRIPTION_MODELS:
				self.primary_model = SUBSCRIPTION_MODELS[0]
			if self.fallback_model not in SUBSCRIPTION_MODELS:
				self.fallback_model = SUBSCRIPTION_MODELS[-1]

	def _get_headers(self) -> Dict[str, str]:
		headers = {
			"Authorization": f"Bearer {self.api_key}",
			"Content-Type": "application/json",
		}
		if self.is_subscription:
			# Header contract taken from the Codex client: the backend keys quota
			# off the account id and gates /responses behind a beta flag.
			headers["chatgpt-account-id"] = self.account_id
			headers["OpenAI-Beta"] = "responses=experimental"
			headers["originator"] = "insights"
			headers["session_id"] = str(uuid.uuid4())
		return headers

	def is_enabled(self) -> bool:
		provider = getattr(self.settings, "ai_provider", None)
		return bool(
			getattr(self.settings, "enable_ai_analytics", False)
			and provider == "openai"
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
		"""Ordered fallback candidates for the active auth mode."""
		if self.is_subscription:
			# Offering the full catalog to a subscription spends one doomed
			# round-trip per gated id and then reports "tried 11 models" when
			# only four of them could ever have answered.
			models = [self.primary_model] if self.primary_model in SUBSCRIPTION_MODELS else []
			for m in SUBSCRIPTION_MODELS:
				if m not in models:
					models.append(m)
			return models

		models = [self.primary_model]
		if self.fallback_model and self.fallback_model not in models:
			models.append(self.fallback_model)
		for m in self.MODELS:
			if m not in models:
				models.append(m)
		return models

	def _is_reasoning_model(self, model: str) -> bool:
		return str(model or "").startswith(self.REASONING_PREFIXES)

	def _build_payload(self, messages: List[Dict], model: str,
					   temperature: float, max_tokens: int) -> Dict[str, Any]:
		payload: Dict[str, Any] = {
			"model": model,
			"messages": messages,
			"stream": False,
		}
		if self._is_reasoning_model(model):
			# Reasoning tokens are charged as output, so a 2k cap returns an
			# empty message with finish_reason=length. Reserve headroom, and
			# keep effort low: dashboard narratives are not deep-reasoning work.
			payload["max_completion_tokens"] = max(max_tokens, self.REASONING_MIN_OUTPUT_TOKENS)
			payload["reasoning_effort"] = "low"
		else:
			payload["temperature"] = temperature
			payload["max_tokens"] = max_tokens
		return payload

	def _to_responses_input(self, messages: List[Dict]) -> Dict[str, Any]:
		"""Fold chat messages into the Responses API shape.

		System turns become `instructions`; every other turn stays its own
		role-tagged item, so conversation history survives as turns instead of
		being flattened into one `role: text` blob.

		`input` must be a **list**: unlike api.openai.com, this backend answers a
		bare string with "Input must be a list". Each item carries plain-string
		content, which the backend accepts for every role -- typed parts would
		work too but must pair `output_text` with assistant turns and
		`input_text` with user turns, and mismatching them is a hard 400.
		"""
		instructions = "\n\n".join(
			str(m.get("content") or "") for m in messages if m.get("role") == "system"
		)
		items = [
			{"role": m.get("role") or "user", "content": str(m.get("content") or "")}
			for m in messages
			if m.get("role") != "system"
		]
		return {"instructions": instructions, "input": items}

	def _parse_responses_sse(self, raw: str) -> str:
		"""Accumulate output text from a Responses API SSE stream."""
		chunks: List[str] = []
		completed = ""
		for line in raw.splitlines():
			if not line.startswith("data:"):
				continue
			data = line[5:].strip()
			if not data or data == "[DONE]":
				continue
			try:
				event = json.loads(data)
			except ValueError:
				continue
			etype = event.get("type") or ""
			if etype == "response.output_text.delta":
				chunks.append(str(event.get("delta") or ""))
			elif etype in ("response.completed", "response.done"):
				for item in (event.get("response") or {}).get("output") or []:
					for part in item.get("content") or []:
						if part.get("type") in ("output_text", "text"):
							completed += str(part.get("text") or "")
		return "".join(chunks) or completed

	def _codex_request(self, messages: List[Dict], model: str) -> Optional[Dict]:
		"""Call the ChatGPT backend on behalf of a Plus/Pro subscription."""
		if not self.account_id:
			return {"request_error": "ChatGPT subscription is not connected. Sign in from Insights Settings."}

		# `stream` must be true and `max_output_tokens` must be absent -- the
		# backend rejects either with "Stream must be set to true" /
		# "Unsupported parameter: max_output_tokens". There is no output cap to
		# set here; reasoning effort is the only length control it accepts.
		payload: Dict[str, Any] = {
			"model": model,
			"stream": True,
			"store": False,
			**self._to_responses_input(messages),
		}
		if self._is_reasoning_model(model):
			payload["reasoning"] = {"effort": "low"}

		response = requests.post(
			f"{self.BASE_URL}/responses",
			headers=self._get_headers(),
			json=payload,
			timeout=180,
		)

		if response.status_code == 401:
			return {"request_error": "ChatGPT subscription token was rejected. Reconnect from Insights Settings."}
		if response.status_code == 429:
			return {"request_error": "ChatGPT subscription rate limit reached.", "rate_limited": True}
		if response.status_code != 200:
			# Surface the upstream body verbatim: this is where an attestation
			# or plan-entitlement refusal shows up, and it is not guessable.
			return {
				"request_error": (
					f"ChatGPT backend error (HTTP {response.status_code}): "
					f"{(response.text or '')[:300]}"
				)
			}

		content = self._parse_responses_sse(response.text)
		if not content.strip():
			return {"request_error": f"Empty response from {model}"}

		return {
			"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
			"model": model,
		}

	def make_request(self, messages: List[Dict], model: str,
					 temperature: float = 0.7, max_tokens: int = 2000) -> Optional[Dict]:
		try:
			if self.is_subscription:
				return self._codex_request(messages, model)

			payload = self._build_payload(messages, model, temperature, max_tokens)
			response = requests.post(
				f"{self.BASE_URL}/chat/completions",
				headers=self._get_headers(),
				json=payload,
				timeout=120
			)

			# Older snapshots may not accept every tuning param; retry once bare
			# rather than surfacing a 400 the operator cannot act on.
			if response.status_code == 400 and "reasoning_effort" in payload:
				payload.pop("reasoning_effort", None)
				response = requests.post(
					f"{self.BASE_URL}/chat/completions",
					headers=self._get_headers(),
					json=payload,
					timeout=120
				)

			if response.status_code == 401:
				return {"request_error": "Invalid OpenAI API key. Please check your configuration."}

			if response.status_code == 429:
				return {"request_error": "OpenAI rate limit exceeded. Please wait a moment.", "rate_limited": True}

			if response.status_code != 200:
				error_text = response.text[:500] if response.text else "No response"
				return {"request_error": f"OpenAI error (HTTP {response.status_code}): {error_text[:200]}"}

			result = response.json()

			if "error" in result:
				error_msg = result.get("error", {}).get("message", "Unknown error")
				return {"request_error": f"OpenAI error: {str(error_msg)[:200]}"}

			# Validate content
			choices = result.get("choices", [])
			if choices:
				content = (choices[0].get("message") or {}).get("content", "")
				if not content or not content.strip():
					return {"request_error": f"Empty response from {model}"}

			return result

		except requests.exceptions.ConnectionError:
			return {"request_error": "Cannot connect to OpenAI API. Check your network."}
		except requests.exceptions.Timeout:
			return {"request_error": f"OpenAI timeout for model {model}. Try again later."}
		except Exception as e:
			return {"request_error": f"OpenAI error: {str(e)[:200]}"}

	def test_connection(self) -> Dict[str, Any]:
		try:
			if not self.api_key:
				return {
					"success": False,
					"error": (
						"ChatGPT subscription is not connected"
						if self.is_subscription
						else "OpenAI API key not configured"
					),
				}

			if self.is_subscription:
				result = self._codex_request(
					[{"role": "user", "content": "ping"}], self.primary_model
				)
				if result and result.get("request_error"):
					return {"success": False, "error": result["request_error"]}
				return {
					"success": True,
					"message": f"ChatGPT subscription active ({self.primary_model})",
				}

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
					"message": "OpenAI connection successful",
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
