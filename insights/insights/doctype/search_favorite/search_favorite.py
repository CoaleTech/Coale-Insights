# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class SearchFavorite(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		created_at: DF.Datetime | None
		query: DF.Data
		title: DF.Data | None
		user: DF.Link | None
	# end: auto-generated types

	def before_insert(self):
		if not self.user:
			self.user = frappe.session.user
		if not self.created_at:
			self.created_at = now_datetime()
