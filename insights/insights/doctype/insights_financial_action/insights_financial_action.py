# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class InsightsFinancialAction(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		assigned_to: DF.Link | None
		department: DF.Literal["Financial", "Sales", "Customer", "Operations", "Risk", "HR", "Manufacturing"]
		description: DF.SmallText | None
		due_date: DF.Date | None
		priority: DF.Literal["Low", "Medium", "High", "Urgent"]
		resolved_by: DF.Link | None
		resolved_on: DF.Datetime | None
		source_alert: DF.Data | None
		status: DF.Literal["Open", "In Progress", "Resolved", "Dismissed"]
		title: DF.Data
	# end: auto-generated types

	def validate(self):
		# `resolved_on`/`resolved_by` are read-only fields the UI never sets
		# directly -- they are stamped here the moment `status` transitions
		# into a terminal state, and cleared if a resolved action is reopened
		# (e.g. moved back to "In Progress" after the fix didn't hold).
		if self.status in ("Resolved", "Dismissed"):
			if not self.resolved_on:
				self.resolved_on = now_datetime()
			if not self.resolved_by:
				self.resolved_by = frappe.session.user
		else:
			self.resolved_on = None
			self.resolved_by = None
