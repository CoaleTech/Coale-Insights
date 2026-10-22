# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Whose permissions filter the rows an execution returns.

Three executions have no caller whose permissions decide the rows: a public
link (Guest), a dashboard preview (Guest with a minted key), and the alert
scheduler (Administrator). Each names a user recorded at the moment the
privileged act happened — publishing a chart, cutting a preview key, enabling
an alert. The engine filters rows and columns by that user. The session user
is never changed.

This answers "whose rows", never "may this caller act".  An authorisation
check still reads `frappe.session.user`.
"""

from contextlib import contextmanager

import frappe


def get_permission_user() -> str:
	"""The user whose permissions the engine applies to the rows it fetches."""
	return getattr(frappe.local, "insights_permission_user", None) or frappe.session.user


@contextmanager
def permission_user(user: str):
	"""Run the enclosed execution under `user`.

	Refuses an empty user: content that predates the field is backfilled by
	`insights.patches.backfill_permission_user`.
	"""
	if not user:
		frappe.throw(
			frappe._("This content does not name a user to run as."),
			frappe.PermissionError,
		)

	previous = getattr(frappe.local, "insights_permission_user", None)
	frappe.local.insights_permission_user = user
	try:
		yield user
	finally:
		frappe.local.insights_permission_user = previous
