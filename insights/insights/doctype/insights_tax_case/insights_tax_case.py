# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class InsightsTaxCase(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amnesty_eligible: DF.Check
		case_ref: DF.Data
		company: DF.Link | None
		decision_date: DF.Date | None
		hearing_date: DF.Date | None
		notes: DF.SmallText | None
		notice_date: DF.Date | None
		objection_date: DF.Date | None
		penalty_interest: DF.Currency
		period_label: DF.Data | None
		principal: DF.Currency
		stage: DF.Literal[
			"Assessment received", "Objection lodged", "Appeal to Tribunal", "High Court", "Settled", "Closed"
		]
		tax_type: DF.Literal["VAT", "PAYE", "CIT", "WHT", "Excise", "Customs", "TOT", "Other"]
		tribunal_date: DF.Date | None
	# end: auto-generated types

	pass
