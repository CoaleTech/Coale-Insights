# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Repoint AI Analytics at models that still exist upstream.

Sites configured before Aug 2026 hold model ids that providers have since
delisted, so every AI request fails with an upstream 404/400:

- OpenRouter delisted 11 of the 13 free models we shipped, including the
  stored default ``meta-llama/llama-3.3-70b-instruct:free``.
- Moonshot discontinued the whole ``kimi-k2-*-preview`` family on 2026-05-25,
  and sunsets ``kimi-k2.5`` plus the ``moonshot-v1`` series on 2026-08-31.
- Several NVIDIA NIM ids we listed are no longer served.
- OpenAI's o1 previews are gone.

Changing the DocType Select options does not rewrite stored values, so this
patch rewrites any value that is no longer selectable onto the current default
for that field. Values that are still valid are left untouched.
"""

import frappe

# Keep in sync with the provider clients in insights/ai/.
VALID_MODELS = {
	"ai_model": [
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
		"openai/gpt-5.6-terra",
		"openai/gpt-5.6-luna",
		"openai/gpt-5.6-sol",
		"anthropic/claude-sonnet-5",
		"anthropic/claude-haiku-4.5",
		"google/gemini-3.5-flash",
		"moonshotai/kimi-k3",
		"deepseek/deepseek-v4-pro",
	],
	"openai_model": [
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
	],
	"nvidia_model": [
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
	],
	"moonshot_model": [
		"kimi-k3",
		"kimi-k2.7-code",
		"kimi-k2.7-code-highspeed",
		"kimi-k2.6",
	],
}

# `ai_model_fallback` shares OpenRouter's option list but defaults to the
# second entry so primary and fallback are not the same model.
VALID_MODELS["ai_model_fallback"] = VALID_MODELS["ai_model"]

REPLACEMENTS = {
	"ai_model": "nvidia/nemotron-3-super-120b-a12b:free",
	"ai_model_fallback": "nvidia/nemotron-3-ultra-550b-a55b:free",
	"openai_model": "gpt-5.6-terra",
	"nvidia_model": "nvidia/nemotron-3-super-120b-a12b",
	"moonshot_model": "kimi-k3",
}


def execute():
	settings = frappe.get_single("Insights Settings")

	for fieldname, replacement in REPLACEMENTS.items():
		current = (getattr(settings, fieldname, None) or "").strip()
		# An unset field already falls through to the DocType default.
		if not current or current in VALID_MODELS[fieldname]:
			continue

		frappe.db.set_single_value("Insights Settings", fieldname, replacement)
		frappe.log_error(
			title="Insights AI model migrated",
			message=(
				f"{fieldname}: {current!r} is no longer served by its provider "
				f"and was repointed to {replacement!r}."
			),
		)
