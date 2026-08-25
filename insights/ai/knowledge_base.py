# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Chunking, embeddings, and vector storage backing the AI Knowledge Base doctype.

Chroma (local, on-disk, zero extra service) is the only vector store. Embeddings
route through whichever chat provider Insights Settings has configured via
`AIProviderFactory` (litellm-backed by default) -- the KB does not need a
dedicated OpenAI key, and it does not need a second provider configuration.
"""

import re
from pathlib import Path
from typing import Any, Dict, List

import frappe


def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[str]:
	"""Split text into overlapping chunks close to `chunk_size` characters,
	preferring paragraph / line / sentence / word boundaries over a hard cut.

	Thin wrapper over `langchain_text_splitters.RecursiveCharacterTextSplitter`,
	which already does this same job with the same priority list of separators
	and is in this bench's deps (`pyproject.toml` core `dependencies`).
	"""
	text = (text or "").strip()
	if not text:
		return []
	chunk_size = max(int(chunk_size or 1000), 1)
	# `RecursiveCharacterTextSplitter` raises ValueError when chunk_overlap
	# >= chunk_size, so clamp here the same way the previous hand-rolled
	# implementation did (`chunk_size // 2`).
	chunk_overlap = max(min(int(chunk_overlap or 0), chunk_size // 2), 0)

	# Imported lazily so import order stays the same as the previous dependency-
	# free version -- keeps `from insights.ai.knowledge_base import chunk_text`
	# cheap at module load (and avoids loading langchain at all for callers that
	# only need `_collection_name`/`embed_texts`).
	from langchain_text_splitters import RecursiveCharacterTextSplitter

	splitter = RecursiveCharacterTextSplitter(
		chunk_size=chunk_size, chunk_overlap=chunk_overlap
	)
	return splitter.split_text(text)


def embed_texts(texts: List[str]) -> List[List[float]]:
	"""Embed a batch of texts via the currently configured AI provider.

	Routes through `AIProviderFactory.get_client()` so the KB uses whatever
	provider Insights Settings has configured (openai, ollama, ollama_cloud,
	openrouter, nvidia, moonshot). Moonshot has no public embeddings API, so
	the factory's `embed_documents` will raise a clear NotImplementedError in
	that case -- callers (KB controller, tax agent grounding) already catch
	`Exception` broadly and degrade to empty grounding, so the propagation is
	safe.
	"""
	from insights.ai.provider_factory import AIProviderFactory

	if not texts:
		return []
	return AIProviderFactory.get_client().embed_documents(texts)


def _collection_name(kb_name: str) -> str:
	"""Chroma collection names must be 3-512 chars from [a-zA-Z0-9._-],
	starting and ending with an alnum. `kb_` guarantees a valid prefix;
	`or "default"` guarantees a non-empty slug even for a title that
	sanitizes away to nothing (e.g. "---"), which otherwise collapsed to
	the 2-char "kb" below Chroma's 3-char minimum; the trailing strip
	guarantees a valid suffix even when `[:512]` truncation lands on a
	separator run."""
	slug = re.sub(r"[^a-zA-Z0-9._-]", "_", kb_name).strip("_-.") or "default"
	name = f"kb_{slug}"[:512]
	while name and not name[-1].isalnum():
		name = name[:-1]
	return name


class KnowledgeBaseStore:
	"""Thin wrapper around one Chroma collection per Knowledge Base. All KBs on
	a site share one persistent Chroma client under `private/chroma_kb`."""

	def __init__(self, kb_name: str):
		import chromadb

		self.kb_name = kb_name
		db_path = Path(frappe.get_site_path("private", "chroma_kb"))
		db_path.mkdir(parents=True, exist_ok=True)
		client = chromadb.PersistentClient(path=str(db_path))
		self.collection = client.get_or_create_collection(name=_collection_name(kb_name))

	def upsert(
		self,
		ids: List[str],
		embeddings: List[List[float]],
		documents: List[str],
		metadatas: List[Dict[str, Any]],
	):
		# chromadb's stubs type embeddings/metadatas against its own internal
		# aliases rather than plain list/dict -- verified at runtime against
		# the installed chromadb 1.5.9 that plain lists/dicts work correctly.
		self.collection.upsert(
			ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas  # type: ignore[arg-type]
		)

	def delete(self, source_id: str):
		"""Delete every chunk belonging to one source document row."""
		self.collection.delete(where={"source_id": source_id})

	def query(self, query_embedding: List[float], n_results: int = 5) -> List[Dict[str, Any]]:
		result = self.collection.query(query_embeddings=[query_embedding], n_results=n_results)
		ids = (result.get("ids") or [[]])[0]
		documents = (result.get("documents") or [[]])[0]
		metadatas = (result.get("metadatas") or [[]])[0]
		distances = (result.get("distances") or [[]])[0]
		return [
			{"id": ids[i], "text": documents[i], "metadata": metadatas[i], "distance": distances[i]}
			for i in range(len(ids))
		]


def get_store(kb_name: str) -> "KnowledgeBaseStore":
	return KnowledgeBaseStore(kb_name)
