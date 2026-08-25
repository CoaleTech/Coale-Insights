# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AIKnowledgeDocument(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		chunk_count: DF.Int
		error: DF.SmallText | None
		file: DF.Attach
		status: DF.Literal["Queue", "In Progress", "Completed", "Failed"]
		title: DF.Data
	# end: auto-generated types
