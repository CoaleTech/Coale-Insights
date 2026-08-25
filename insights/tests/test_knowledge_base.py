# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Coverage for the AI Knowledge Base feature added this session:
- `insights.ai.knowledge_base`: dependency-free chunking (no
  `langchain_text_splitters` in this bench) and the Chroma collection-name
  contract (`KnowledgeBaseStore`/`_collection_name`).
- `TaxIntelligenceAgent._get_grounding_context`: the first dashboard wired
  to ground answers in an uploaded Knowledge Base instead of only the
  model's training data (`insights.agents.tax_agent`).
- `insights.api.knowledge_base.reindex_knowledge_base`: the one whitelisted
  endpoint the feature needs beyond the native Desk grid upload.

Uses mocks for anything touching embeddings/Chroma/AI providers -- this
bench's only site (jkm) carries live production data, so tests avoid
Frappe's test-user/test-record bootstrap (see test_ml_permission_gates.py).
"""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from insights.ai.knowledge_base import _collection_name, chunk_text


class TestChunkText(FrappeTestCase):
	"""`chunk_text` stands in for langchain's RecursiveCharacterTextSplitter
	(not installed in this bench -- see the module docstring)."""

	def test_empty_text_returns_no_chunks(self):
		self.assertEqual(chunk_text(""), [])
		self.assertEqual(chunk_text("   "), [])

	def test_short_text_returns_single_unchanged_chunk(self):
		text = "GST rate for textiles is 5%."
		self.assertEqual(chunk_text(text, chunk_size=1000), [text])

	def test_long_text_keeps_paragraphs_intact(self):
		para_a = "A" * 60
		para_b = "B" * 60
		chunks = chunk_text(f"{para_a}\n\n{para_b}", chunk_size=70, chunk_overlap=0)
		self.assertGreaterEqual(len(chunks), 2)
		self.assertTrue(any(para_a in c for c in chunks))
		self.assertTrue(any(para_b in c for c in chunks))

	def test_overlap_prevents_context_loss_at_a_boundary(self):
		"""A phrase straddling where a hard cut would otherwise fall must
		still appear intact in at least one chunk, thanks to overlap."""
		text = ("x" * 40) + " CRITICAL_PHRASE " + ("y" * 40)
		chunks = chunk_text(text, chunk_size=45, chunk_overlap=20)
		self.assertTrue(any("CRITICAL_PHRASE" in c for c in chunks))

	def test_overlap_larger_than_chunk_size_is_clamped(self):
		"""chunk_overlap is clamped to chunk_size // 2 so a caller-supplied
		overlap >= chunk_size can't make `current` un-shrinkable, which
		would otherwise grow every chunk without bound."""
		text = "word " * 200
		chunks = chunk_text(text, chunk_size=100, chunk_overlap=10_000)
		self.assertTrue(chunks)
		self.assertTrue(all(len(c) <= 150 for c in chunks))  # generous: never runaway


class TestCollectionName(FrappeTestCase):
	"""Chroma requires collection names to be 3-512 chars from
	[a-zA-Z0-9._-], starting and ending with an alnum."""

	def test_sanitizes_invalid_characters(self):
		name = _collection_name("GST Circulars (2026)!")
		self.assertRegex(name, r"^[a-zA-Z0-9._-]+$")

	def test_always_starts_with_kb_prefix(self):
		self.assertTrue(_collection_name("Anything").startswith("kb_"))

	def test_title_that_sanitizes_to_nothing_still_meets_minimum_length(self):
		"""Regression: a title of only separator characters (e.g. "---")
		used to sanitize away to an empty slug, collapsing the whole name
		to the 2-char "kb" -- below Chroma's documented 3-char minimum."""
		name = _collection_name("___---...")
		self.assertGreaterEqual(len(name), 3)
		self.assertTrue(name[-1].isalnum())

	def test_truncation_boundary_is_trimmed_back_to_alnum(self):
		"""A title long enough that `[:512]` truncation lands on an
		interior separator run must still end alphanumeric."""
		long_name = ("A" * 508) + "_" + ("C" * 100)
		name = _collection_name(long_name)
		self.assertLessEqual(len(name), 512)
		self.assertTrue(name[-1].isalnum())


class TestTaxAgentGrounding(FrappeTestCase):
	"""`TaxIntelligenceAgent._get_grounding_context` (insights/agents/tax_agent.py),
	called from `BaseIntelligenceAgent.execute` right after the system
	prompt, before conversation history and the user's query."""

	def _get_agent(self):
		import insights.agents.tax_agent  # noqa: F401 -- trigger @AgentRegistry.register
		from insights.agents.registry import AgentRegistry

		agent = AgentRegistry.get_agent("Tax")
		assert agent is not None, "Tax agent must be registered"
		assert agent.config is not None, "Tax agent must load a Dashboard AI Agent Config"
		return agent

	def test_no_grounding_when_no_knowledge_base_configured(self):
		agent = self._get_agent()
		assert agent.config is not None
		agent.config.knowledge_base = None
		self.assertEqual(agent._get_grounding_context("What is my GST liability?"), "")

	def test_grounding_formats_top_matches_with_source_titles(self):
		agent = self._get_agent()
		assert agent.config is not None
		agent.config.knowledge_base = "GST Circulars"
		matches = [
			{"text": "Rule 86B restricts ITC utilisation to 99%.", "metadata": {"title": "CGST Circular 231"}},
			{"text": "e-Invoicing mandatory above Rs 5 crore turnover.", "metadata": {"title": "Notification 10/2026"}},
		]

		with patch("insights.ai.knowledge_base.embed_texts", return_value=[[0.1, 0.2]]) as mock_embed, patch(
			"insights.ai.knowledge_base.get_store"
		) as mock_get_store:
			mock_get_store.return_value.query.return_value = matches
			result = agent._get_grounding_context("Can I claim full ITC?")

		mock_embed.assert_called_once_with(["Can I claim full ITC?"])
		mock_get_store.assert_called_once_with("GST Circulars")
		mock_get_store.return_value.query.assert_called_once_with([0.1, 0.2], n_results=5)
		self.assertIn("GST Circulars", result)
		self.assertIn("CGST Circular 231", result)
		self.assertIn("Rule 86B restricts ITC", result)
		self.assertIn("Notification 10/2026", result)

	def test_grounding_returns_empty_string_when_no_matches(self):
		agent = self._get_agent()
		assert agent.config is not None
		agent.config.knowledge_base = "GST Circulars"
		with patch("insights.ai.knowledge_base.embed_texts", return_value=[[0.1]]), patch(
			"insights.ai.knowledge_base.get_store"
		) as mock_get_store:
			mock_get_store.return_value.query.return_value = []
			result = agent._get_grounding_context("Unrelated question")
		self.assertEqual(result, "")

	def test_grounding_swallows_retrieval_errors(self):
		"""A broken/misconfigured Knowledge Base (e.g. embedding API down)
		must degrade the chat turn silently, not break the whole response --
		grounding is an optional augmentation, not a hard dependency."""
		agent = self._get_agent()
		assert agent.config is not None
		agent.config.knowledge_base = "GST Circulars"
		with patch("insights.ai.knowledge_base.embed_texts", side_effect=RuntimeError("embedding API down")):
			result = agent._get_grounding_context("Can I claim full ITC?")
		self.assertEqual(result, "")


class TestReindexKnowledgeBaseAPI(FrappeTestCase):
	"""insights.api.knowledge_base.reindex_knowledge_base -- the one
	whitelisted endpoint the feature needs beyond the native Desk grid
	upload (see the module docstring for why)."""

	def test_checks_write_permission_before_touching_documents(self):
		import frappe

		from insights.api.knowledge_base import reindex_knowledge_base

		with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError) as mock_has_perm, patch.object(
			frappe, "get_doc"
		) as mock_get_doc:
			with self.assertRaises(frappe.PermissionError):
				reindex_knowledge_base("GST Circulars")
			mock_has_perm.assert_called_once_with("AI Knowledge Base", "write", throw=True)
			mock_get_doc.assert_not_called()

	def test_requeues_every_row_and_enqueues_processing(self):
		import frappe

		from insights.api.knowledge_base import reindex_knowledge_base
		from insights.insights.doctype.ai_knowledge_base.ai_knowledge_base import STATUS_QUEUE

		row_a, row_b = MagicMock(), MagicMock()
		mock_kb = MagicMock()
		mock_kb.get.return_value = [row_a, row_b]

		with patch.object(frappe, "has_permission"), patch.object(
			frappe, "get_doc", return_value=mock_kb
		), patch.object(frappe.db, "set_value") as mock_set_value, patch.object(frappe, "enqueue") as mock_enqueue:
			result = reindex_knowledge_base("GST Circulars")

		row_a.db_set.assert_called_once_with("status", STATUS_QUEUE, update_modified=False)
		row_b.db_set.assert_called_once_with("status", STATUS_QUEUE, update_modified=False)
		mock_set_value.assert_called_once_with("AI Knowledge Base", "GST Circulars", "status", STATUS_QUEUE)
		mock_enqueue.assert_called_once()
		self.assertEqual(mock_enqueue.call_args.kwargs["kb_name"], "GST Circulars")
		self.assertTrue(result["success"])


class TestProcessKnowledgeBase(FrappeTestCase):
	"""insights.insights.doctype.ai_knowledge_base.ai_knowledge_base.process_knowledge_base
	-- the chunk+embed+upsert pipeline queued from `AIKnowledgeBase.on_update`.
	Mocks the file-read, embedding, and vector-store boundaries; the real
	`chunk_text` runs so the chunking step stays covered end-to-end too."""

	def _make_row(self, name, status, text):
		row = MagicMock()
		row.name = name
		row.status = status
		row.file = f"/files/{name}.txt"
		row.title = name
		row.extracted_text = text
		return row

	def test_all_rows_succeed_marks_kb_and_row_completed(self):
		import frappe

		from insights.insights.doctype.ai_knowledge_base.ai_knowledge_base import (
			STATUS_COMPLETED,
			STATUS_IN_PROGRESS,
			STATUS_QUEUE,
			process_knowledge_base,
		)

		row = self._make_row("row-1", STATUS_QUEUE, "GST rate for textiles is 5%.")
		kb = MagicMock(documents=[row], chunk_size=1000, chunk_overlap=200)
		kb.name = "GST Circulars"

		with patch.object(frappe, "get_doc", return_value=kb), patch.object(
			frappe.db, "commit"
		), patch(
			"insights.insights.doctype.ai_knowledge_base.ai_knowledge_base._extract_text",
			return_value=row.extracted_text,
		), patch(
			"insights.ai.knowledge_base.embed_texts", return_value=[[0.1, 0.2]]
		), patch("insights.ai.knowledge_base.get_store") as mock_get_store:
			process_knowledge_base("GST Circulars")

		row.db_set.assert_any_call("status", STATUS_IN_PROGRESS, update_modified=False)
		final_row_update = row.db_set.call_args_list[-1].args[0]
		self.assertEqual(final_row_update["status"], STATUS_COMPLETED)
		self.assertEqual(final_row_update["chunk_count"], 1)
		self.assertEqual(final_row_update["error"], "")
		mock_get_store.return_value.upsert.assert_called_once()
		self.assertEqual(kb.db_set.call_args.args[0]["status"], STATUS_COMPLETED)

	def test_one_failing_row_logs_error_and_kb_falls_back_to_queue(self):
		"""A failing row must not block its siblings, and the KB as a whole
		must go back to Queue (not Completed) so a retry picks it up."""
		import frappe

		from insights.insights.doctype.ai_knowledge_base.ai_knowledge_base import (
			STATUS_COMPLETED,
			STATUS_FAILED,
			STATUS_QUEUE,
			process_knowledge_base,
		)

		good_row = self._make_row("row-good", STATUS_QUEUE, "Rule 86B restricts ITC to 99%.")
		bad_row = self._make_row("row-bad", STATUS_QUEUE, "irrelevant")
		kb = MagicMock(documents=[good_row, bad_row], chunk_size=1000, chunk_overlap=200)
		kb.name = "GST Circulars"

		def extract_side_effect(file_url):
			if file_url == bad_row.file:
				raise RuntimeError("corrupt file")
			return good_row.extracted_text

		with patch.object(frappe, "get_doc", return_value=kb), patch.object(
			frappe.db, "commit"
		), patch.object(frappe, "log_error") as mock_log_error, patch(
			"insights.insights.doctype.ai_knowledge_base.ai_knowledge_base._extract_text",
			side_effect=extract_side_effect,
		), patch(
			"insights.ai.knowledge_base.embed_texts", return_value=[[0.1]]
		), patch("insights.ai.knowledge_base.get_store"):
			process_knowledge_base("GST Circulars")

		good_final = good_row.db_set.call_args_list[-1].args[0]
		self.assertEqual(good_final["status"], STATUS_COMPLETED)

		bad_final = bad_row.db_set.call_args_list[-1].args[0]
		self.assertEqual(bad_final["status"], STATUS_FAILED)
		self.assertIn("corrupt file", bad_final["error"])
		mock_log_error.assert_called_once()

		self.assertEqual(kb.db_set.call_args.args[0]["status"], STATUS_QUEUE)

	def test_rows_not_pending_are_skipped(self):
		"""Rows already `Completed` (e.g. after a partial retry) must not
		be re-embedded -- only Queue/Failed/blank rows are pending."""
		import frappe

		from insights.insights.doctype.ai_knowledge_base.ai_knowledge_base import (
			STATUS_COMPLETED,
			process_knowledge_base,
		)

		done_row = self._make_row("row-done", STATUS_COMPLETED, "already indexed")
		kb = MagicMock(documents=[done_row], chunk_size=1000, chunk_overlap=200)
		kb.name = "GST Circulars"

		with patch.object(frappe, "get_doc", return_value=kb), patch.object(
			frappe.db, "commit"
		), patch(
			"insights.insights.doctype.ai_knowledge_base.ai_knowledge_base._extract_text"
		) as mock_extract, patch(
			"insights.ai.knowledge_base.embed_texts"
		) as mock_embed, patch("insights.ai.knowledge_base.get_store"):
			process_knowledge_base("GST Circulars")

		mock_extract.assert_not_called()
		mock_embed.assert_not_called()
		done_row.db_set.assert_not_called()
		self.assertEqual(kb.db_set.call_args.args[0]["status"], STATUS_COMPLETED)


class TestRequeueReattachedRows(FrappeTestCase):
	"""AIKnowledgeBase._requeue_reattached_rows (ai_knowledge_base.py) --
	re-attaching a new `file` onto an existing row must drop its stale
	vectors and reset it to Queue, or it silently keeps serving embeddings
	of whatever was uploaded first."""

	def _make_row(self, name, status, file):
		row = MagicMock()
		row.name = name
		row.status = status
		row.file = file
		return row

	def test_changed_file_on_completed_row_requeues_and_drops_old_vectors(self):
		from insights.insights.doctype.ai_knowledge_base.ai_knowledge_base import (
			STATUS_COMPLETED,
			STATUS_QUEUE,
			AIKnowledgeBase,
		)

		old_row = self._make_row("row-1", STATUS_COMPLETED, "/files/old.pdf")
		new_row = self._make_row("row-1", STATUS_COMPLETED, "/files/new.pdf")
		before = MagicMock(documents=[old_row])
		kb = MagicMock(documents=[new_row])
		kb.name = "GST Circulars"
		kb.get_doc_before_save.return_value = before

		with patch("insights.ai.knowledge_base.get_store") as mock_get_store:
			AIKnowledgeBase._requeue_reattached_rows(kb)

		mock_get_store.return_value.delete.assert_called_once_with("row-1")
		update = new_row.db_set.call_args.args[0]
		self.assertEqual(update["status"], STATUS_QUEUE)
		self.assertEqual(update["chunk_count"], 0)
		self.assertEqual(update["error"], "")

	def test_unchanged_file_is_left_alone(self):
		from insights.insights.doctype.ai_knowledge_base.ai_knowledge_base import (
			STATUS_COMPLETED,
			AIKnowledgeBase,
		)

		old_row = self._make_row("row-1", STATUS_COMPLETED, "/files/same.pdf")
		new_row = self._make_row("row-1", STATUS_COMPLETED, "/files/same.pdf")
		before = MagicMock(documents=[old_row])
		kb = MagicMock(documents=[new_row])
		kb.name = "GST Circulars"
		kb.get_doc_before_save.return_value = before

		with patch("insights.ai.knowledge_base.get_store") as mock_get_store:
			AIKnowledgeBase._requeue_reattached_rows(kb)

		mock_get_store.return_value.delete.assert_not_called()
		new_row.db_set.assert_not_called()

	def test_new_row_is_not_requeued_twice(self):
		"""A brand-new row (not present in the pre-save doc) is already
		Queue by field default -- must not be treated as 'changed'."""
		from insights.insights.doctype.ai_knowledge_base.ai_knowledge_base import (
			STATUS_QUEUE,
			AIKnowledgeBase,
		)

		new_row = self._make_row("row-new", STATUS_QUEUE, "/files/brand-new.pdf")
		before = MagicMock(documents=[])
		kb = MagicMock(documents=[new_row])
		kb.name = "GST Circulars"
		kb.get_doc_before_save.return_value = before

		with patch("insights.ai.knowledge_base.get_store") as mock_get_store:
			AIKnowledgeBase._requeue_reattached_rows(kb)

		mock_get_store.return_value.delete.assert_not_called()
		new_row.db_set.assert_not_called()

	def test_no_doc_before_save_is_a_noop(self):
		"""First-ever save (or a KB fetched outside a save cycle) has no
		before-save snapshot -- must not raise."""
		from insights.insights.doctype.ai_knowledge_base.ai_knowledge_base import AIKnowledgeBase

		row = self._make_row("row-1", "Completed", "/files/x.pdf")
		kb = MagicMock(documents=[row])
		kb.get_doc_before_save.return_value = None

		with patch("insights.ai.knowledge_base.get_store") as mock_get_store:
			AIKnowledgeBase._requeue_reattached_rows(kb)

		mock_get_store.assert_not_called()
		row.db_set.assert_not_called()

class TestBaseProviderEmbedDocuments(FrappeTestCase):
	"""`BaseAIProvider.embed_documents` default implementation -- routes
	through litellm.embedding() instead of unconditionally raising. The
	Knowledge Base must work for any provider Insights Settings has
	configured (openai, ollama local, ollama cloud, openrouter, nvidia)
	without requiring a second OpenAI key.
	"""

	def _make_provider(self, provider_name, **attrs):
		"""Build a `BaseAIProvider` subclass that overrides every
		abstract method with a no-op, so the default `embed_documents`
		can be exercised against just the attributes we care about.
		`Mock(spec=BaseAIProvider)` would auto-Mock `_EMBEDDING_MODELS` /
		`_NO_EMBEDDING_PROVIDERS` on the instance and shadow the real
		class-level lookup the production code uses."""
		from insights.ai.base_provider import BaseAIProvider

		class _Stub(BaseAIProvider):
			def is_enabled(self):
				return True

			def check_quota(self):
				return True

			def increment_quota(self):
				pass

			def get_available_models(self):
				return []

			def make_request(self, messages, model, temperature=0.7, max_tokens=2000):
				return None

			def test_connection(self):
				return {"success": True}

		stub = _Stub()
		stub.provider_name = provider_name
		for k, v in attrs.items():
			setattr(stub, k, v)
		return stub

	def test_openai_provider_routes_through_litellm_with_canonical_model(self):
		provider = self._make_provider("OpenAI", api_key="sk-test")
		with patch("insights.ai.base_provider.litellm.embedding") as mock_embed:
			mock_embed.return_value = self._litellm_response([[0.1, 0.2], [0.3, 0.4]])
			result = provider.embed_documents(["hello", "world"])
		mock_embed.assert_called_once()
		kwargs = mock_embed.call_args.kwargs
		self.assertEqual(kwargs["model"], "text-embedding-3-small")
		self.assertEqual(kwargs["input"], ["hello", "world"])
		self.assertEqual(kwargs["api_key"], "sk-test")
		self.assertEqual(kwargs["max_retries"], 3)
		self.assertEqual(result, [[0.1, 0.2], [0.3, 0.4]])

	def test_ollama_provider_uses_local_base_url_and_no_api_key(self):
		# Ollama local rejects Authorization headers, so the default must
		# NOT forward the loopback API key (if any) to the daemon.
		provider = self._make_provider(
			"Ollama", api_key="should-be-dropped", base_url="http://localhost:11434"
		)
		with patch("insights.ai.base_provider.litellm.embedding") as mock_embed:
			mock_embed.return_value = self._litellm_response([[0.5]])
			provider.embed_documents(["hi"])
		kwargs = mock_embed.call_args.kwargs
		self.assertIsNone(kwargs["api_key"])
		self.assertEqual(kwargs["api_base"], "http://localhost:11434")
		self.assertEqual(kwargs["model"], "nomic-embed-text")

	def test_ollama_cloud_provider_forwards_api_key(self):
		# Ollama Cloud is the same `provider_name` ("Ollama") as local, only
		# distinguished by `is_cloud` (see OllamaClient.__init__). Unlike
		# local, the cloud endpoint authenticates with a real bearer token,
		# so the default must NOT null it out just because provider_key ==
		# "ollama" -- regression test for the bug where the ollama branch
		# unconditionally zeroed `api_key` for both local and cloud alike.
		provider = self._make_provider(
			"Ollama",
			api_key="cloud-token",
			is_cloud=True,
			base_url="https://ollama.com",
		)
		with patch("insights.ai.base_provider.litellm.embedding") as mock_embed:
			mock_embed.return_value = self._litellm_response([[0.5]])
			provider.embed_documents(["hi"])
		kwargs = mock_embed.call_args.kwargs
		self.assertEqual(kwargs["api_key"], "cloud-token")
		self.assertEqual(kwargs["api_base"], "https://ollama.com")

	def test_openrouter_provider_prefixes_model_with_openrouter(self):
		provider = self._make_provider("OpenRouter", api_key="or-key")
		with patch("insights.ai.base_provider.litellm.embedding") as mock_embed:
			mock_embed.return_value = self._litellm_response([[0.0]])
			provider.embed_documents(["x"])
		self.assertEqual(
			mock_embed.call_args.kwargs["model"], "openai/text-embedding-3-small"
		)

	def test_nvidia_provider_uses_nvidia_prefix(self):
		provider = self._make_provider("NVIDIA", api_key="nv-key")
		with patch("insights.ai.base_provider.litellm.embedding") as mock_embed:
			mock_embed.return_value = self._litellm_response([[0.0]])
			provider.embed_documents(["x"])
		self.assertEqual(
			mock_embed.call_args.kwargs["model"], "nvidia/nv-embed-v1"
		)

	def test_moonshot_provider_raises_clear_not_implemented(self):
		"""Moonshot / Kimi has no public embeddings API -- the default
		must raise a normal `NotImplementedError` naming the provider, so
		callers that catch `Exception` broadly can degrade cleanly."""
		provider = self._make_provider("Moonshot", api_key="ms-key")
		with self.assertRaises(NotImplementedError) as ctx:
			provider.embed_documents(["x"])
		self.assertIn("Moonshot", str(ctx.exception))
		self.assertIn("does not support embeddings", str(ctx.exception))

	def test_unknown_provider_raises_clear_not_implemented(self):
		provider = self._make_provider("BrandNewProvider")
		with self.assertRaises(NotImplementedError):
			provider.embed_documents(["x"])

	def test_empty_input_returns_empty_list_without_calling_litellm(self):
		provider = self._make_provider("OpenAI", api_key="sk-test")
		with patch("insights.ai.base_provider.litellm.embedding") as mock_embed:
			result = provider.embed_documents([])
		mock_embed.assert_not_called()
		self.assertEqual(result, [])

	def test_caller_supplied_model_overrides_default(self):
		provider = self._make_provider("OpenAI", api_key="sk-test")
		with patch("insights.ai.base_provider.litellm.embedding") as mock_embed:
			mock_embed.return_value = self._litellm_response([[0.0]])
			provider.embed_documents(["x"], model="text-embedding-3-large")
		self.assertEqual(
			mock_embed.call_args.kwargs["model"], "text-embedding-3-large"
		)

	@staticmethod
	def _litellm_response(embeddings):
		"""Build a duck-typed `litellm.EmbeddingResponse` the default impl
		can read: `.data` is a real list of dicts, since the production
		code calls `sorted(data, key=...)` and `data[i]['embedding']` --
		which a `MagicMock` fakes by returning Mock objects, not the
		values the test set."""
		class _Resp:
			pass

		resp = _Resp()
		resp.data = [
			{"object": "embedding", "index": i, "embedding": list(emb)}
			for i, emb in enumerate(embeddings)
		]
		return resp


class TestEmbedDocumentsBatching(FrappeTestCase):
	"""`BaseAIProvider.embed_documents` must split large `texts` into
	`_EMBED_BATCH_SIZE`-sized chunks, concatenate in input order, and let
	litellm's own `max_retries` handle transient 429/5xx."""

	def _make_provider(self):
		from insights.ai.base_provider import BaseAIProvider

		class _Stub(BaseAIProvider):
			def is_enabled(self):
				return True

			def check_quota(self):
				return True

			def increment_quota(self):
				pass

			def get_available_models(self):
				return []

			def make_request(self, messages, model, temperature=0.7, max_tokens=2000):
				return None

			def test_connection(self):
				return {"success": True}

		stub = _Stub()
		stub.provider_name = "OpenAI"
		stub.api_key = "sk-test"
		return stub

	@staticmethod
	def _resp(embs):
		class _R:
			pass

		r = _R()
		r.data = [
			{"object": "embedding", "index": i, "embedding": list(emb)}
			for i, emb in enumerate(embs)
		]
		return r

	def test_large_batch_is_split_into_multiple_calls_in_order(self):
		provider = self._make_provider()
		# Three full batches + a tail (default 256 per call) -> 4 calls.
		texts = [f"text-{i}" for i in range(3 * 256 + 17)]

		call_log = []
		texts_seen = []

		def fake_embed(model, input, **kwargs):
			call_log.append(list(input))
			# Index the embeddings by ABSOLUTE text position so the
			# production code's per-batch sort by `index` (which the
			# test fake re-numbers from 0 in each call) still yields a
			# result ordered by original input position.
			batch_start = len(texts_seen)
			texts_seen.extend(input)
			return self._resp(
				[[float(batch_start + i)] for i in range(len(input))]
			)

		with patch(
			"insights.ai.base_provider.litellm.embedding", side_effect=fake_embed
		):
			result = provider.embed_documents(texts)

		# Each batch under the cap; tail carried in a smaller final call.
		self.assertEqual(len(call_log), 4)
		for batch in call_log[:3]:
			self.assertEqual(len(batch), 256)
		self.assertEqual(len(call_log[3]), 17)

		# Concatenation must match input order, not call order.
		self.assertEqual(len(result), len(texts))
		self.assertEqual([v[0] for v in result], [float(i) for i in range(len(texts))])

	def test_response_out_of_order_is_resorted_by_index(self):
		"""Some litellm providers (OpenRouter in particular) return
		embeddings in non-deterministic order -- the default impl must
		trust `index`, not response position."""
		provider = self._make_provider()
		texts = ["a", "b", "c", "d", "e"]

		# Build the fake response with shuffled order: index i carries
		# embedding value `i`, but the data list is in REVERSE order so a
		# naive positional concat would emit [4, 3, 2, 1, 0]. The
		# production code must sort by `index` to recover [0, 1, 2, 3, 4].
		def fake_embed(model, input, **kwargs):
			class _R:
				pass

			r = _R()
			r.data = [
				{"index": i, "embedding": [float(i)]}
				for i in reversed(range(len(input)))
			]
			return r

		with patch(
			"insights.ai.base_provider.litellm.embedding", side_effect=fake_embed
		):
			result = provider.embed_documents(texts)

		self.assertEqual([v[0] for v in result], [0.0, 1.0, 2.0, 3.0, 4.0])
	def test_max_retries_is_passed_to_litellm(self):
		"""litellm 1.98.0's retry behavior is gated on the `max_retries`
		kwarg; passing None means zero retries. The default impl must
		pass an int so transient 429/5xx actually back off."""
		provider = self._make_provider()
		with patch("insights.ai.base_provider.litellm.embedding") as mock_embed:
			mock_embed.return_value = self._resp([[0.0]])
			provider.embed_documents(["x"])
		self.assertEqual(mock_embed.call_args.kwargs["max_retries"], 3)

	def test_embed_texts_calls_factory_get_client(self):
		with patch(
			"insights.ai.provider_factory.AIProviderFactory.get_client"
		) as mock_get_client:
			fake_client = MagicMock()
			fake_client.embed_documents.return_value = [[0.0]]
			mock_get_client.return_value = fake_client
			from insights.ai.knowledge_base import embed_texts

			result = embed_texts(["x"])
		mock_get_client.assert_called_once()
		fake_client.embed_documents.assert_called_once_with(["x"])
		self.assertEqual(result, [[0.0]])

	def test_embed_texts_short_circuits_on_empty_input(self):
		with patch(
			"insights.ai.provider_factory.AIProviderFactory.get_client"
		) as mock_get_client:
			from insights.ai.knowledge_base import embed_texts

			result = embed_texts([])
		mock_get_client.assert_not_called()
		self.assertEqual(result, [])


class TestChunkTextNewSplitter(FrappeTestCase):
	"""`chunk_text` now delegates to `RecursiveCharacterTextSplitter` --
	these tests pin the public contract the doctype controller and the
	tax agent's grounding path both rely on."""

	def test_respects_chunk_size_and_overlap_on_realistic_text(self):
		paragraphs = [
			"GST rate for cotton textiles is 5% under HSN 5201 to 5212. "
			"This rate was unchanged in the 2026 budget and applies to "
			"both job-work and forward supply chains.",
			"Input tax credit (ITC) for textile manufacturers is "
			"restricted under Section 17(5) for items used to make "
			"exempt supplies -- this remains a frequent audit finding.",
			"Job workers in the textile supply chain must register "
			"under GST even when turnover is below the general threshold, "
			"because textile processing is a notified service.",
		]
		text = "\n\n".join(paragraphs)
		chunks = chunk_text(text, chunk_size=200, chunk_overlap=50)
		self.assertGreater(len(chunks), 1)
		# Every chunk fits inside chunk_size + a small overhead for the
		# carried-over characters from overlap (RecursiveCharacterTextSplitter
		# can produce chunks up to chunk_size + overlap, not chunk_size alone).
		for c in chunks:
			self.assertLessEqual(len(c), 250)
		# Concatenation of chunk texts covers the source.
		for p in paragraphs:
			self.assertTrue(any(p[i : i + 40] in c for c in chunks for i in range(0, len(p), 30)))

	def test_overlap_prevents_context_loss_at_a_boundary(self):
		text = ("x" * 40) + " CRITICAL_PHRASE " + ("y" * 40)
		chunks = chunk_text(text, chunk_size=45, chunk_overlap=20)
		self.assertTrue(any("CRITICAL_PHRASE" in c for c in chunks))

	def test_overlap_larger_than_chunk_size_is_clamped(self):
		"""RecursiveCharacterTextSplitter raises ValueError when
		chunk_overlap >= chunk_size. The KB wrapper must clamp the same
		way the previous hand-rolled implementation did (`chunk_size // 2`).
		"""
		text = "word " * 200
		chunks = chunk_text(text, chunk_size=100, chunk_overlap=10_000)
		self.assertTrue(chunks)
		for c in chunks:
			self.assertLessEqual(len(c), 150)

	def test_empty_text_returns_no_chunks(self):
		self.assertEqual(chunk_text(""), [])
		self.assertEqual(chunk_text("   "), [])

	def test_short_text_returns_single_unchanged_chunk(self):
		text = "GST rate for textiles is 5%."
		self.assertEqual(chunk_text(text, chunk_size=1000), [text])

	def test_long_text_keeps_paragraphs_intact(self):
		para_a = "A" * 60
		para_b = "B" * 60
		chunks = chunk_text(f"{para_a}\n\n{para_b}", chunk_size=70, chunk_overlap=0)
		self.assertGreaterEqual(len(chunks), 2)
		self.assertTrue(any(para_a in c for c in chunks))
		self.assertTrue(any(para_b in c for c in chunks))


def run():
	"""Manual entrypoint: `bench --site <site> execute insights.tests.test_knowledge_base.run`.

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
