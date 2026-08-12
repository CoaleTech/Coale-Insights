# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Turn on `apply_user_permissions` for sites that already exist.

The field shipped with no `default`, so it read as unchecked everywhere and
`insights_table_v3.apply_user_permissions()` returned every table unfiltered.
User Permissions -- the mechanism a Frappe administrator uses to say "this
person sees only their territory" -- were configured, respected everywhere
else, and ignored by the BI tool reading the same tables.

Changing the field default only helps new sites: `tabSingles` already holds a
row for existing ones. This writes the value those sites would have had.

It is a deliberate re-grant, not a preference reset. Nobody chose the old
value: an unchecked box that was never presented as a choice is not consent,
and the sites most affected are the ones that never opened this page. An
administrator who genuinely wants unfiltered reporting can uncheck it, and
that is then a decision with a name against it.
"""

import frappe


def execute():
    frappe.db.set_single_value("Insights Settings", "apply_user_permissions", 1)
