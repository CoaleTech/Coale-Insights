# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Coverage for the KB-grounding generalization added this session:

- `BaseIntelligenceAgent._get_grounding_context` (insights/agents/base.py) is
  the single default implementation all 13 dashboard agents inherit. The
  TaxIntelligenceAgent used to override it; that override has been deleted
  in favour of the base default, so every dashboard's `Dashboard AI Agent
  Config.knowledge_base` field now actually does what it advertises.
- A non-Tax agent (GeneralIntelligenceAgent) -- which never had an override
  of its own -- returns grounded context when its config's `knowledge_base`
  is set, and `""` when it isn't. This proves the base default works for
  every dashboard type, not just Tax.

Mirrors the structure of `test_knowledge_base.py` (license header, mocks
for the embedding+Chroma surface, `FrappeTestCase` subclasses, and a
`run()` entrypoint that drives `unittest.TextTestRunner` directly). This
file is invokable as:

    bench --site <site> execute insights.tests.test_agent_grounding.run

Uses mocks for anything touching embeddings/Chroma/AI providers -- this
bench's only site (jkm) carries live production data, so tests avoid
Frappe's test-user/test-record bootstrap (see test_ml_permission_gates.py).
"""

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from insights.agents.base import BaseIntelligenceAgent

class TestNonTaxAgentGrounding(FrappeTestCase):
	"""`BaseIntelligenceAgent._get_grounding_context` (insights/agents/base.py)
	inherited by every dashboard agent. The GeneralIntelligenceAgent never
	had its own override, so its behavior here is the unfiltered base-class
	default: when the agent's loaded `Dashboard AI Agent Config` has a
	`knowledge_base` link set, retrieval-augmented grounding kicks in; when
	it doesn't, the method is a no-op."""

	def _get_agent(self):
		import insights.agents.general_agent  # noqa: F401 -- trigger @AgentRegistry.register
		from insights.agents.registry import AgentRegistry

		agent = AgentRegistry.get_agent("General")
		assert agent is not None, "General agent must be registered"
		assert agent.config is not None, "General agent must load a Dashboard AI Agent Config"
		# The base default -- not a subclass override -- is what we're proving.
		assert type(agent)._get_grounding_context is BaseIntelligenceAgent._get_grounding_context, (
			"GeneralIntelligenceAgent must not override _get_grounding_context; "
			"it should inherit the base default"
		)
		return agent

	def test_no_grounding_when_no_knowledge_base_configured(self):
		"""No KB link on the agent's config -> base default returns empty string
		without ever calling the embedding/retrieval layer."""
		agent = self._get_agent()
		assert agent.config is not None
		agent.config.knowledge_base = None

		with patch("insights.ai.knowledge_base.embed_texts") as mock_embed, patch(
			"insights.ai.knowledge_base.get_store"
		) as mock_get_store:
			result = agent._get_grounding_context("What was revenue last quarter?")

		self.assertEqual(result, "")
		mock_embed.assert_not_called()
		mock_get_store.assert_not_called()

	def test_grounding_formats_top_matches_with_source_titles(self):
		"""With a KB set, base default embeds the query, retrieves top-N, and
		returns a single string that quotes every match's source title + body
		-- the same contract Tax used to implement in its own override."""
		agent = self._get_agent()
		assert agent.config is not None
		agent.config.knowledge_base = "ERPNext SOPs"
		matches = [
			{"text": "Reorder point = (avg daily usage * lead time) + safety stock.", "metadata": {"title": "Inventory Playbook"}},
			{"text": "Run the AR aging report weekly; escalate invoices >60d.", "metadata": {"title": "Collections SOP"}},
		]

		with patch("insights.ai.knowledge_base.embed_texts", return_value=[[0.3, 0.4]]) as mock_embed, patch(
			"insights.ai.knowledge_base.get_store"
		) as mock_get_store:
			mock_get_store.return_value.query.return_value = matches
			result = agent._get_grounding_context("When should I reorder?")

		mock_embed.assert_called_once_with(["When should I reorder?"])
		mock_get_store.assert_called_once_with("ERPNext SOPs")
		mock_get_store.return_value.query.assert_called_once_with([0.3, 0.4], n_results=5)
		self.assertIn("ERPNext SOPs", result)
		self.assertIn("Inventory Playbook", result)
		self.assertIn("Reorder point =", result)
		self.assertIn("Collections SOP", result)
		self.assertIn("AR aging", result)

	def test_grounding_returns_empty_string_when_no_matches(self):
		"""A KB with nothing relevant returns "" rather than an empty doc list --
		preserves the silent-degradation contract the Tax agent used to
		guarantee."""
		agent = self._get_agent()
		assert agent.config is not None
		agent.config.knowledge_base = "ERPNext SOPs"

		with patch("insights.ai.knowledge_base.embed_texts", return_value=[[0.1]]), patch(
			"insights.ai.knowledge_base.get_store"
		) as mock_get_store:
			mock_get_store.return_value.query.return_value = []
			result = agent._get_grounding_context("unrelated question")

		self.assertEqual(result, "")

	def test_grounding_swallows_retrieval_errors(self):
		"""A broken embedding API or missing Chroma collection must degrade
		the chat turn silently. Same error-swallowing contract Tax enforced
		before its override was deleted."""
		agent = self._get_agent()
		assert agent.config is not None
		agent.config.knowledge_base = "ERPNext SOPs"

		with patch("insights.ai.knowledge_base.embed_texts", side_effect=RuntimeError("embedding API down")):
			result = agent._get_grounding_context("When should I reorder?")
		self.assertEqual(result, "")

	def test_every_registered_agent_inherits_the_base_grounding(self):
		"""The whole point of the move: of all 13 registered agents, NONE
		may override `_get_grounding_context` anymore. If this regresses,
		we're back to the 1-of-14 situation the workstream fixed."""
		import insights.agents.customer_agent
		import insights.agents.esg_agent
		import insights.agents.executive_agent
		import insights.agents.financial_agent
		import insights.agents.general_agent
		import insights.agents.hr_agent
		import insights.agents.inventory_agent
		import insights.agents.manufacturing_agent
		import insights.agents.marketing_agent
		import insights.agents.procurement_agent
		import insights.agents.risk_agent
		import insights.agents.sales_agent
		import insights.agents.tax_agent  # noqa: F401 -- last import in block rebinds `insights`; ruff's F401 checks only the final binding

		from insights.agents.base import BaseIntelligenceAgent
		from insights.agents.registry import AgentRegistry

		for dashboard_type in AgentRegistry.get_all_dashboard_types():
			agent = AgentRegistry.get_agent(dashboard_type)
			assert agent is not None, f"{dashboard_type} agent must be registered"
			self.assertIs(
				type(agent)._get_grounding_context,
				BaseIntelligenceAgent._get_grounding_context,
				f"{dashboard_type} must inherit _get_grounding_context from the base class",
			)


def run():
	"""Manual entrypoint: `bench --site <site> execute insights.tests.test_agent_grounding.run`.

	`bench run-tests` walks every test_*.py in the app upfront to preload
	dependency test records (frappe/deprecation_dumpster.py
	compat_preload_test_records_upfront); on this bench that chain reaches
	erpnext's Company/Fiscal Year bootstrap and collides with jkm's real
	Fiscal Year 22-23 (reproduces on test_ml_permission_gates.py too, so
	it is pre-existing and app-wide, not specific to this module). Running
	via `bench execute` reuses the site connection `bench execute` already
	sets up and calls unittest directly, skipping that CLI-only phase.
	"""
	import sys
	import unittest

	suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
	result = unittest.TextTestRunner(verbosity=2).run(suite)
	if not result.wasSuccessful():
		sys.exit(1)
