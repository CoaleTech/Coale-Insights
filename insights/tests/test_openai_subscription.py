"""Contract tests for the ChatGPT (Codex) subscription path of OpenAIClient.

Every assertion here encodes a rule the live `chatgpt.com/backend-api/codex`
backend enforces and which `api.openai.com` does not. Each was established by
sweeping the real backend on 2026-08-18; a regression in any of them makes the
dashboard AI widget fail with "(tried N models)" and no usable diagnosis:

- ``input`` MUST be a list. A bare string is refused with
  ``{"detail":"Input must be a list"}``.
- ``stream`` MUST be true (``"Stream must be set to true"``).
- ``max_output_tokens`` is refused outright
  (``"Unsupported parameter: max_output_tokens"``).
- Only a subset of the platform catalog is served; every other id -- including
  the API-only ``gpt-4o`` family and even the ``-codex`` ids the Codex CLI
  itself runs -- is refused with "The 'X' model is not supported when using
The tests are pure unit contract tests: they touch no database, and
``requests.post`` is patched so the payload is captured rather than sent. They
use plain ``unittest.TestCase`` rather than ``FrappeTestCase`` deliberately --
nothing here needs a site, and the integration base class drags in ERPNext's
global test-record bootstrap for no benefit.
"""

import unittest
from unittest.mock import MagicMock, patch

from insights.ai import openai_client as oc
from insights.ai.openai_codex_auth import SUBSCRIPTION_MODELS


def _settings(model="gpt-5.6-terra", auth_mode="ChatGPT Subscription"):
	s = MagicMock()
	s.openai_auth_mode = auth_mode
	s.openai_model = model
	s.openai_oauth_account_id = "acct-123"
	s.openai_base_url = None
	s.openai_api_key = None
	s.enable_ai_analytics = 1
	s.ai_provider = "openai"
	s.get_password.return_value = "sk-test"
	return s


def _client(model="gpt-5.6-terra", auth_mode="ChatGPT Subscription"):
	"""Build a client without touching the site's real Insights Settings."""
	with patch.object(oc.frappe, "get_single", return_value=_settings(model, auth_mode)), patch(
		"insights.ai.openai_codex_auth.get_access_token", return_value="tok-abc"
	):
		return oc.OpenAIClient()


class _Resp:
	"""Minimal stand-in for a streamed 200 from /responses."""

	status_code = 200
	text = (
		'data: {"type":"response.output_text.delta","delta":"hi"}\n'
		"data: [DONE]\n"
	)


class TestSubscriptionModelGate(unittest.TestCase):
	def test_served_settings_model_is_honoured(self):
		self.assertEqual(_client("gpt-5.5").primary_model, "gpt-5.5")

	def test_gated_settings_model_is_coerced(self):
		# `gpt-4o-mini` is in the platform catalog but refused by this backend.
		# Coercion must happen in __init__, not only in get_available_models():
		# callers prepend primary_model to their own candidate list.
		c = _client("gpt-4o-mini")
		self.assertIn(c.primary_model, SUBSCRIPTION_MODELS)

	def test_codex_ids_are_gated_too(self):
		# The Codex CLI runs gpt-5.1-codex-max, but the ChatGPT-account path
		# refuses every `-codex` id. Selecting one must not reach the wire.
		self.assertIn(_client("gpt-5.1-codex-max").primary_model, SUBSCRIPTION_MODELS)

	def test_fallback_model_is_served(self):
		self.assertIn(_client().fallback_model, SUBSCRIPTION_MODELS)

	def test_candidates_are_exactly_the_served_set(self):
		models = _client().get_available_models()
		self.assertEqual(sorted(set(models)), sorted(SUBSCRIPTION_MODELS))

	def test_candidates_have_no_duplicates(self):
		models = _client().get_available_models()
		self.assertEqual(len(models), len(set(models)))

	def test_honoured_model_is_tried_first(self):
		self.assertEqual(_client("gpt-5.5").get_available_models()[0], "gpt-5.5")

	def test_api_key_mode_keeps_the_full_catalog(self):
		# The gate is subscription-only; an API key can still reach every model.
		c = _client("gpt-4o-mini", auth_mode="API Key")
		self.assertEqual(c.primary_model, "gpt-4o-mini")
		self.assertGreater(len(c.get_available_models()), len(SUBSCRIPTION_MODELS))


class TestResponsesInputShape(unittest.TestCase):
	def test_input_is_a_list(self):
		out = _client()._to_responses_input([{"role": "user", "content": "hi"}])
		self.assertIsInstance(out["input"], list)

	def test_system_turns_fold_into_instructions(self):
		out = _client()._to_responses_input(
			[{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}]
		)
		self.assertEqual(out["instructions"], "be terse")
		self.assertEqual([i["role"] for i in out["input"]], ["user"])

	def test_history_survives_as_separate_turns(self):
		msgs = [
			{"role": "system", "content": "sys"},
			{"role": "user", "content": "q1"},
			{"role": "assistant", "content": "a1"},
			{"role": "user", "content": "q2"},
		]
		out = _client()._to_responses_input(msgs)
		self.assertEqual([i["role"] for i in out["input"]], ["user", "assistant", "user"])
		self.assertEqual([i["content"] for i in out["input"]], ["q1", "a1", "q2"])

	def test_assistant_and_user_content_are_plain_strings(self):
		# Typed parts are accepted but must pair output_text with assistant and
		# input_text with user turns; mismatching them is a hard 400. Plain
		# strings sidestep that entirely -- keep them plain.
		out = _client()._to_responses_input(
			[{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
		)
		for item in out["input"]:
			self.assertIsInstance(item["content"], str)


class TestCodexPayloadContract(unittest.TestCase):
	def _capture(self, model="gpt-5.6-terra"):
		c = _client(model)
		with patch.object(oc.requests, "post", return_value=_Resp()) as post:
			c._codex_request([{"role": "user", "content": "hi"}], c.primary_model)
		self.assertTrue(post.called, "no request was issued")
		args = post.call_args
		assert args is not None
		return args

	def test_posts_to_responses_endpoint(self):
		args = self._capture()
		self.assertTrue(args[0][0].endswith("/responses"))

	def test_stream_is_true(self):
		self.assertIs(self._capture()[1]["json"]["stream"], True)

	def test_no_max_output_tokens(self):
		payload = self._capture()[1]["json"]
		self.assertNotIn("max_output_tokens", payload)
		self.assertNotIn("max_tokens", payload)

	def test_payload_input_is_a_list(self):
		self.assertIsInstance(self._capture()[1]["json"]["input"], list)

	def test_store_is_false(self):
		self.assertIs(self._capture()[1]["json"]["store"], False)

	def test_account_header_is_sent(self):
		headers = self._capture()[1]["headers"]
		self.assertEqual(headers["chatgpt-account-id"], "acct-123")
		self.assertEqual(headers["OpenAI-Beta"], "responses=experimental")

	def test_make_request_passes_no_token_cap(self):
		# make_request's max_tokens argument must not reach the subscription
		# path -- the backend rejects any output cap.
		c = _client()
		with patch.object(c, "_codex_request", return_value={"choices": []}) as codex:
			c.make_request([{"role": "user", "content": "hi"}], c.primary_model, max_tokens=999)
		call = codex.call_args
		assert call is not None
		self.assertEqual(call[0][1], c.primary_model)
		self.assertEqual(len(call[0]), 2, "a token cap leaked into _codex_request")
		self.assertEqual(call[1], {})

	def test_test_connection_passes_no_token_cap(self):
		c = _client()
		with patch.object(c, "_codex_request", return_value={"choices": []}) as codex:
			c.test_connection()
		call = codex.call_args
		assert call is not None
		self.assertEqual(len(call[0]), 2, "a token cap leaked into _codex_request")

	def test_missing_account_is_reported_not_posted(self):
		c = _client()
		c.account_id = ""
		with patch.object(oc.requests, "post") as post:
			out = c._codex_request([{"role": "user", "content": "hi"}], c.primary_model)
		self.assertFalse(post.called)
		self.assertIsNotNone(out)
		self.assertIn("not connected", (out or {})["request_error"])


class TestSubscriptionModelList(unittest.TestCase):
	def test_list_is_non_empty_and_unique(self):
		self.assertTrue(SUBSCRIPTION_MODELS)
		self.assertEqual(len(SUBSCRIPTION_MODELS), len(set(SUBSCRIPTION_MODELS)))

	def test_no_codex_id_is_listed(self):
		# Every `-codex` id is refused on a ChatGPT account, so none may appear
		# here even though the Codex CLI itself uses them.
		self.assertEqual([m for m in SUBSCRIPTION_MODELS if "codex" in m], [])

	def test_no_api_only_family_is_listed(self):
		self.assertEqual([m for m in SUBSCRIPTION_MODELS if m.startswith("gpt-4")], [])


if __name__ == "__main__":
	unittest.main()
