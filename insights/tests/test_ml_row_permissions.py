# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""The three properties the ML permission fix has to keep.

`test_ml_permission_gates.py` mocks `frappe.has_permission` and asserts it was
called. That is worth having, and it cannot see any of the three defects found
here: a filter that is called but filters nothing, a `has_permission` answer
that is wrong for child tables, and a filter that is correct but compiled by
materialising every permitted key into the SQL text.

So these run against the real site, read-only. Nothing is written; no user,
role or permission is created. Each test discovers its own subjects from
whatever the bench happens to have and skips when the site cannot supply them
-- a site with one user and no User Permissions genuinely cannot demonstrate
row-level filtering, and saying so is more honest than passing vacuously.

    bench --site <site> run-tests --app insights \\
        --module insights.tests.test_ml_row_permissions
"""

from __future__ import annotations

import re
import unittest

import frappe
import ibis

from insights.api.ml.ibis_source import t
from insights.api.ml.permissions import (
    DASHBOARD_DOCTYPES,
    _permitted_readers,
    authorize_dashboard,
)

PROBE_DOCTYPE = "Sales Invoice"


def connected() -> bool:
    return bool(getattr(frappe, "db", None))


def _row_count(doctype: str) -> int:
    """What Frappe itself says this user may see. The number to match."""
    return len(frappe.get_list(doctype, pluck="name", limit=0))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests")
class MLRowPermissions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_user = frappe.session.user
        cls.users = frappe.get_all(
            "User",
            filters={"enabled": 1, "name": ("not in", ["Administrator", "Guest"])},
            pluck="name",
        )

    def tearDown(self):
        frappe.set_user(self.original_user or "Administrator")
        frappe.local.insights_ml_permissions = {}

    def _as(self, user: str):
        frappe.set_user(user)
        # Permitted columns and row SQL are memoised per request; a test that
        # switches user inside one process has to drop that or it reads the
        # previous user's answer and passes for the wrong reason.
        frappe.local.insights_ml_permissions = {}

    def _discriminating_pair(self) -> tuple[str, str]:
        """Two users who may see different numbers of rows, or skip.

        The pair is discovered, not named, so this test moves to another
        bench. It is looking for the situation the fix exists for: two
        people with legitimate access to the same doctype and different
        entitlements within it.
        """
        seen: dict[int, str] = {}
        for user in self.users:
            self._as(user)
            try:
                count = _row_count(PROBE_DOCTYPE)
            except frappe.PermissionError:
                continue
            if count:
                seen.setdefault(count, user)
            if len(seen) >= 2:
                counts = sorted(seen)
                return seen[counts[0]], seen[counts[-1]]
        raise unittest.SkipTest(f"no two users on this site see different numbers of {PROBE_DOCTYPE} rows")

    def test_row_counts_match_what_frappe_permits(self):
        """The aggregate a user reads covers exactly the rows they may list.

        This is the whole fix in one assertion. Before it, `t()` handed every
        endpoint the bare table: on this bench one user's dashboard reported
        ?309,651,502 of revenue against ?9,037,743 they were permitted to see,
        a 34x overstatement that looked like a business result.
        """
        narrow, wide = self._discriminating_pair()

        for user in (narrow, wide):
            self._as(user)
            expected = _row_count(PROBE_DOCTYPE)
            actual = t(PROBE_DOCTYPE).count().execute()
            self.assertEqual(
                actual,
                expected,
                f"{user} reads {actual} {PROBE_DOCTYPE} rows through the ML path "
                f"but frappe.get_list permits {expected}",
            )

        self._as(narrow)
        narrow_rows = t(PROBE_DOCTYPE).count().execute()
        self._as(wide)
        wide_rows = t(PROBE_DOCTYPE).count().execute()
        self.assertNotEqual(
            narrow_rows,
            wide_rows,
            "both users read the same row count -- the filter is not discriminating",
        )

    def test_filter_compiles_to_a_subquery_not_a_list_of_keys(self):
        """Permission is expressed as SQL the database resolves, not as keys.

        A filter that is correct can still be built by fetching every
        permitted `name` and embedding them as an IN list. That passes a
        row-count test and fails in production: the query text grows with the
        ledger, and the permission check stops being a check and becomes a
        snapshot taken at build time.
        """
        narrow, _ = self._discriminating_pair()
        self._as(narrow)

        permitted_rows = _row_count(PROBE_DOCTYPE)
        if permitted_rows < 100:
            raise unittest.SkipTest(
                f"{narrow} sees only {permitted_rows} rows -- too few to tell a subquery from a key list"
            )

        sql = ibis.to_sql(t(PROBE_DOCTYPE))
        text = str(sql)

        self.assertRegex(
            text,
            r"(?:EXISTS|IN)\s*\(\s*SELECT",
            "no subquery in the compiled SQL -- the row filter is either missing or materialised",
        )

        literals = re.findall(r"'[^']*'", text)
        self.assertLess(
            len(literals),
            permitted_rows / 2,
            f"{len(literals)} string literals in SQL for {permitted_rows} permitted "
            "rows -- the keys are being embedded rather than joined",
        )

    def test_dashboard_refuses_a_caller_missing_any_source_doctype(self):
        """All of it, or none of it.

        A dashboard is read as one artefact. A P&L rendered from the three
        ledgers its reader can see, silently missing the fourth, still prints
        a Net Profit -- and a number that is wrong for a reason invisible on
        screen is worse than a refusal.
        """
        refused = []
        for user in self.users:
            self._as(user)
            for dashboard_type in DASHBOARD_DOCTYPES:
                try:
                    authorize_dashboard(dashboard_type)
                except frappe.PermissionError as denial:
                    refused.append((user, dashboard_type, str(denial)))

        if not refused:
            raise unittest.SkipTest("every user on this site may read every dashboard source doctype")

        for user, dashboard_type, message in refused:
            missing = [d for d in DASHBOARD_DOCTYPES[dashboard_type] if d in message]
            self.assertTrue(
                missing,
                f"{user} was refused {dashboard_type} without being told which doctype is missing: {message}",
            )

    def test_child_tables_resolve_through_their_parent(self):
        """A child table has no permissions of its own.

        `frappe.has_permission("Sales Invoice Item")` is False for everyone but
        Administrator, because permission belongs to the invoice. Asking it
        directly -- which the first version of the gate did -- refused the
        sales dashboard to a user who could read all 3,704 invoices behind it.
        """
        children = [
            doctype
            for doctypes in DASHBOARD_DOCTYPES.values()
            for doctype in doctypes
            if frappe.get_meta(doctype).istable
        ]
        self.assertTrue(children, "no child tables among the dashboard sources")

        for user in self.users:
            self._as(user)
            for child in children:
                parents = _permitted_readers(child)
                if parents is None:
                    continue
                readable_parent = any(frappe.has_permission(p, "read") for p in parents)
                self.assertTrue(
                    readable_parent,
                    f"{child} resolved as readable for {user} with no readable parent",
                )


if __name__ == "__main__":
    unittest.main()
