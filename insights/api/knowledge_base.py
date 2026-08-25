# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Whitelisted endpoints for the AI Knowledge Base.

Upload itself needs no API: the "Documents" child grid's Attach field
handles that natively, and `AIKnowledgeBase.on_update` auto-enqueues any
Queue/Failed row. This module covers the one thing the native grid can't:
forcing a full reindex (e.g. after changing Chunk Size/Overlap, or the
embedding model) without manually blanking and re-attaching every row.
"""

from typing import Any

import frappe
from frappe import _


@frappe.whitelist()
def reindex_knowledge_base(kb_name: str) -> dict[str, Any]:
	"""Requeue every document on `kb_name` and re-run the chunk/embed/upsert
	pipeline, regardless of its current status."""
	frappe.has_permission("AI Knowledge Base", "write", throw=True)

	from insights.insights.doctype.ai_knowledge_base.ai_knowledge_base import STATUS_QUEUE

	kb = frappe.get_doc("AI Knowledge Base", kb_name)
	documents = kb.get("documents") or []
	for row in documents:
		row.db_set("status", STATUS_QUEUE, update_modified=False)
	frappe.db.set_value("AI Knowledge Base", kb_name, "status", STATUS_QUEUE)

	frappe.enqueue(
		"insights.insights.doctype.ai_knowledge_base.ai_knowledge_base.process_knowledge_base",
		queue="long",
		timeout=1500,
		kb_name=kb_name,
		enqueue_after_commit=True,
	)
	return {"success": True, "message": _("Reindexing {0} document(s).").format(len(documents))}
