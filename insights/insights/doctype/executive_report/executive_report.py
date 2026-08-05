# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import now_datetime


class ExecutiveReport(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		report_type: DF.Literal["daily", "weekly", "monthly"]
		report_date: DF.Date
		status: DF.Literal["Generated", "Failed"]
		period_covered: DF.Data | None
		generated_at: DF.Datetime | None
		report_data: DF.JSON | None
		pdf_file: DF.Attach | None
		error_message: DF.SmallText | None
	# end: auto-generated types

	def before_insert(self):
		if not self.generated_at:
			self.generated_at = now_datetime()
		if not self.status:
			self.status = "Generated"
