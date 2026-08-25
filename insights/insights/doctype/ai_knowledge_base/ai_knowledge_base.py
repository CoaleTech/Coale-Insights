# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""AI Knowledge Base: chunk + embed + upsert source documents into a
per-KB Chroma collection, so dashboard AI agents can ground answers in
uploaded reference material instead of guessing (see insights.ai.knowledge_base).
"""

import io
import zipfile
from typing import cast
from xml.etree import ElementTree

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import encode, now_datetime

STATUS_QUEUE = "Queue"
STATUS_IN_PROGRESS = "In Progress"
STATUS_COMPLETED = "Completed"
STATUS_FAILED = "Failed"
_PENDING_STATUSES = (STATUS_QUEUE, STATUS_FAILED, None, "")
_DOCX_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class AIKnowledgeBase(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from insights.insights.doctype.ai_knowledge_document.ai_knowledge_document import AIKnowledgeDocument

		chunk_overlap: DF.Int
		chunk_size: DF.Int
		description: DF.SmallText | None
		documents: DF.Table[AIKnowledgeDocument]
		error: DF.SmallText | None
		last_processed: DF.Datetime | None
		status: DF.Literal["Queue", "In Progress", "Completed"]
		title: DF.Data
	# end: auto-generated types

	def on_update(self):
		"""Delete vectors for rows removed since the last save, requeue rows
		whose file was re-attached, then enqueue processing for any row still
		queued or previously failed."""
		self._delete_removed_rows()
		self._requeue_reattached_rows()
		if any(row.status in _PENDING_STATUSES for row in self.documents):
			frappe.enqueue(
				"insights.insights.doctype.ai_knowledge_base.ai_knowledge_base.process_knowledge_base",
				queue="long",
				timeout=1500,
				kb_name=self.name,
				enqueue_after_commit=True,
			)

	def on_trash(self):
		"""Drop the whole vector collection; nothing else references it."""
		from insights.ai.knowledge_base import get_store

		try:
			get_store(str(self.name)).collection.delete()
		except Exception:
			# collection may never have been created (KB queued but never processed)
			pass

	def _delete_removed_rows(self):
		from insights.ai.knowledge_base import get_store

		before = self.get_doc_before_save()
		if not before:
			return
		removed = {str(row.name) for row in before.documents} - {str(row.name) for row in self.documents}
		if not removed:
			return
		store = get_store(str(self.name))
		for source_id in removed:
			store.delete(source_id)

	def _requeue_reattached_rows(self):
		"""Re-attaching a new `file` onto an existing Completed/Failed row
		otherwise keeps its old status forever -- nothing else compares old vs
		new `file`, so the row silently serves stale embeddings. Drop its old
		chunks and reset it to Queue so the enqueue check above (and
		process_knowledge_base's per-row skip) re-embeds it."""
		from insights.ai.knowledge_base import get_store

		before = self.get_doc_before_save()
		if not before:
			return
		old_files = {str(row.name): row.file for row in before.documents}
		changed = [
			row
			for row in self.documents
			if str(row.name) in old_files
			and old_files[str(row.name)] != row.file
			and row.status != STATUS_QUEUE
		]
		if not changed:
			return
		store = get_store(str(self.name))
		for row in changed:
			store.delete(str(row.name))
			row.db_set({"status": STATUS_QUEUE, "chunk_count": 0, "error": ""}, update_modified=False)


def process_knowledge_base(kb_name: str):
	"""Chunk, embed, and upsert every Queue/Failed document row on `kb_name`.
	Runs on the `long` queue via `AIKnowledgeBase.on_update`; safe to call
	directly (e.g. from the console) to force a retry."""
	from insights.ai.knowledge_base import chunk_text, embed_texts, get_store

	kb = cast(AIKnowledgeBase, frappe.get_doc("AI Knowledge Base", kb_name))
	store = get_store(kb_name)
	any_failed = False

	for row in kb.documents:
		if row.status not in _PENDING_STATUSES:
			continue
		row.db_set("status", STATUS_IN_PROGRESS, update_modified=False)
		try:
			chunks = _chunk_document(row.file, kb.chunk_size, kb.chunk_overlap, chunk_text)
			embeddings = embed_texts(chunks)
			store.upsert(
				ids=[f"{row.name}::{i}" for i in range(len(chunks))],
				embeddings=embeddings,
				documents=chunks,
				metadatas=[{"source_id": row.name, "title": row.title, "chunk_index": i} for i in range(len(chunks))],
			)
			row.db_set({"status": STATUS_COMPLETED, "chunk_count": len(chunks), "error": ""}, update_modified=False)
		except Exception as e:
			any_failed = True
			frappe.log_error(title=f"AI Knowledge Base chunking failed: {kb.name}/{row.name}", message=str(e))
			row.db_set({"status": STATUS_FAILED, "error": str(e)[:500]}, update_modified=False)

	kb.db_set(
		{
			"status": STATUS_QUEUE if any_failed else STATUS_COMPLETED,
			"last_processed": now_datetime(),
			"error": _("One or more documents failed to process; see row-level errors.") if any_failed else "",
		},
		update_modified=False,
	)
	frappe.db.commit()


def _chunk_document(file_url: str, chunk_size: int, chunk_overlap: int, chunk_text) -> list:
	text = _extract_text(file_url)
	chunks = chunk_text(text, chunk_size, chunk_overlap)
	if not chunks:
		frappe.throw(_("No extractable text found in the attached file."))
	return chunks


def _extract_text(file_url: str) -> str:
	"""Read raw bytes ourselves (never `get_file`'s auto-decode guess, which
	is ambiguous for binary formats) and extract text per extension."""
	from frappe.utils.file_manager import get_file_path

	file_path = get_file_path(file_url)
	if not file_path:
		frappe.throw(_("Could not resolve the attached file's path."))
		raise frappe.ValidationError  # unreachable: narrows file_path to str for pyright
	ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
	with open(cast(bytes, encode(file_path)), mode="rb") as f:
		content = f.read()

	if ext == "pdf":
		return _extract_pdf_text(content)
	if ext == "docx":
		return _extract_docx_text(content)
	if ext in ("txt", "md", "markdown"):
		return content.decode("utf-8", errors="replace")
	frappe.throw(_("Unsupported file type '.{0}'. Upload a .txt, .md, .pdf, or .docx file.").format(ext))
	raise frappe.ValidationError  # unreachable: satisfies -> str


def _extract_pdf_text(content: bytes) -> str:
	import fitz

	with fitz.open(stream=content, filetype="pdf") as doc:
		return "\n".join(cast(str, page.get_text("text")) for page in doc)


def _extract_docx_text(content: bytes) -> str:
	"""Minimal, dependency-free .docx reader: a .docx is a zip archive and
	its body text lives in `word/document.xml` as a sequence of `<w:t>` runs
	grouped into `<w:p>` paragraphs. Covers the common case (paragraph text);
	does not read tables, headers, or footers."""
	with zipfile.ZipFile(io.BytesIO(content)) as zf:
		xml_bytes = zf.read("word/document.xml")
	root = ElementTree.fromstring(xml_bytes)
	paragraphs = []
	for p in root.iter(f"{{{_DOCX_W_NS}}}p"):
		paragraphs.append("".join(node.text or "" for node in p.iter(f"{{{_DOCX_W_NS}}}t")))
	return "\n".join(paragraphs)
