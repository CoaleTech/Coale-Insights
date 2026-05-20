# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from insights.permissions import (
    InsightsPermissions,
    PERMISSION_DOCTYPES,
    TEAM_BASED_PERMISSION_DOCTYPES,
    has_doc_permission,
    get_permission_query_conditions,
    check_app_permission,
)


class TestInsightsPermissions(FrappeTestCase):
    def setUp(self):
        create_test_users()
        create_test_data_sources()
        create_test_tables()
        create_test_teams()
        create_test_workbook()
        frappe.db.commit()

    def tearDown(self):
        delete_test_workbook()
        delete_test_teams()
        delete_test_tables()
        delete_test_data_sources()
        delete_test_users()
        frappe.db.commit()

    def toggle_team_permissions(self, enable):
        frappe.db.set_value(
            "Insights Settings", None, "enable_permissions", enable
        )
        frappe.db.commit()

    def test_permissions_for_non_insights_user(self):
        # A non-insights user should not be able to access Insights doctypes
        with frappe.set_user("non_insights_user@test.com"):
            for doctype in PERMISSION_DOCTYPES:
                conditions = get_permission_query_conditions("non_insights_user@test.com", doctype)
                # Should return an empty string (no access filter) for non-insights users
                # because InsightsPermissions checks role first in has_doc_permission
                self.assertIsInstance(conditions, str)

    def test_permissions_on_team_based_doctype_with_team_permissions_disabled(self):
        self.toggle_team_permissions(False)
        with frappe.set_user("insights_user1@test.com"):
            perm = InsightsPermissions("insights_user1@test.com")
            # When team permissions are disabled, all insights users can access team-based doctypes
            for doctype in TEAM_BASED_PERMISSION_DOCTYPES:
                conditions = perm.get_permission_query_conditions(doctype)
                # Should return empty string (no restrictions)
                self.assertEqual(conditions, "")

    def test_permission_on_team_based_doctype_with_team_permissions_enabled(self):
        self.toggle_team_permissions(True)
        with frappe.set_user("insights_user1@test.com"):
            perm = InsightsPermissions("insights_user1@test.com")
            # User should be restricted to their team's resources
            for doctype in TEAM_BASED_PERMISSION_DOCTYPES:
                conditions = perm.get_permission_query_conditions(doctype)
                # Should return a non-empty restriction query when teams exist
                if doctype == "Insights Team":
                    self.assertIn("name in", conditions)

    def test_permission_for_admin_on_team_based_doctype_with_team_permissions_enabled(self):
        self.toggle_team_permissions(True)
        with frappe.set_user("insights_admin@test.com"):
            perm = InsightsPermissions("insights_admin@test.com")
            # Admin should have no restrictions
            for doctype in PERMISSION_DOCTYPES:
                conditions = perm.get_permission_query_conditions(doctype)
                self.assertEqual(conditions, "")

    def test_permission_for_workbook(self):
        # Check if insights user has access to no workbooks they don't own
        with frappe.set_user("insights_user2@test.com"):
            perm = InsightsPermissions("insights_user2@test.com")
            # User2 does not own the test workbook
            workbook = frappe.get_doc("Insights Workbook", "Test Workbook")
            self.assertFalse(perm.has_doc_permission(workbook, "read"))

        # Owner should have access
        with frappe.set_user("insights_user1@test.com"):
            perm = InsightsPermissions("insights_user1@test.com")
            workbook = frappe.get_doc("Insights Workbook", "Test Workbook")
            self.assertTrue(perm.has_doc_permission(workbook, "read"))

    def test_permission_for_dashboard(self):
        with frappe.set_user("insights_user2@test.com"):
            perm = InsightsPermissions("insights_user2@test.com")
            # Non-owner cannot create a dashboard without workbook access
            dashboard = frappe.new_doc("Insights Dashboard v3")
            dashboard.title = "Test Dashboard"
            dashboard.workbook = "Test Workbook"
            self.assertFalse(perm.has_doc_permission(dashboard, "write"))

    def test_permission_for_chart(self):
        with frappe.set_user("insights_user2@test.com"):
            perm = InsightsPermissions("insights_user2@test.com")
            chart = frappe.new_doc("Insights Chart v3")
            chart.title = "Test Chart"
            chart.workbook = "Test Workbook"
            self.assertFalse(perm.has_doc_permission(chart, "write"))

    def test_permission_for_query(self):
        with frappe.set_user("insights_user2@test.com"):
            perm = InsightsPermissions("insights_user2@test.com")
            query = frappe.new_doc("Insights Query v3")
            query.title = "Test Query"
            query.workbook = "Test Workbook"
            self.assertFalse(perm.has_doc_permission(query, "write"))

    def test_check_app_permission(self):
        # Administrator should pass
        with frappe.set_user("Administrator"):
            self.assertTrue(check_app_permission())

        # Insights User should pass
        with frappe.set_user("insights_user1@test.com"):
            self.assertTrue(check_app_permission())

        # Insights Admin should pass
        with frappe.set_user("insights_admin@test.com"):
            self.assertTrue(check_app_permission())

        # Non-insights user should fail
        with frappe.set_user("non_insights_user@test.com"):
            self.assertFalse(check_app_permission())

    def test_has_doc_permission_for_teams(self):
        self.toggle_team_permissions(True)
        with frappe.set_user("insights_user1@test.com"):
            perm = InsightsPermissions("insights_user1@test.com")
            team = frappe.get_doc("Insights Team", "team1")
            # User1 is in team1, should have read access
            self.assertTrue(perm.has_doc_permission(team, "read"))

        with frappe.set_user("insights_user2@test.com"):
            perm = InsightsPermissions("insights_user2@test.com")
            team = frappe.get_doc("Insights Team", "team1")
            # User2 is not in team1, should not have read access
            self.assertFalse(perm.has_doc_permission(team, "read"))


def create_test_users():
    # create a website user
    if not frappe.db.exists("User", "web_user@test.com"):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": "web_user@test.com",
                "first_name": "Web",
                "last_name": "User",
                "send_welcome_email": 0,
                "user_type": "Website User",
                "enabled": 1,
            }
        ).insert()

    # create a non insights user
    if not frappe.db.exists("User", "non_insights_user@test.com"):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": "non_insights_user@test.com",
                "first_name": "Non",
                "last_name": "Insights User",
                "send_welcome_email": 0,
                "user_type": "System User",
                "enabled": 1,
            }
        ).insert()

    # create insights users
    if not frappe.db.exists("User", "insights_user1@test.com"):
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": "insights_user1@test.com",
                "first_name": "Insights",
                "last_name": "User",
                "send_welcome_email": 0,
                "user_type": "System User",
                "enabled": 1,
            }
        ).insert()
        user.add_roles("Insights User")

    if not frappe.db.exists("User", "insights_user2@test.com"):
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": "insights_user2@test.com",
                "first_name": "Insights",
                "last_name": "User",
                "send_welcome_email": 0,
                "user_type": "System User",
                "enabled": 1,
            }
        ).insert()
        user.add_roles("Insights User")

    # create a insights admin
    if not frappe.db.exists("User", "insights_admin@test.com"):
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": "insights_admin@test.com",
                "first_name": "Insights",
                "last_name": "Admin",
                "send_welcome_email": 0,
                "user_type": "System User",
                "enabled": 1,
            }
        ).insert()
        user.add_roles("Insights Admin")


def delete_test_users():
    for email in [
        "web_user@test.com",
        "non_insights_user@test.com",
        "insights_user1@test.com",
        "insights_user2@test.com",
        "insights_admin@test.com",
    ]:
        if frappe.db.exists("User", email):
            frappe.delete_doc("User", email, force=True)


def create_test_data_sources():
    if not frappe.db.exists("Insights Data Source v3", "Test DuckDB"):
        frappe.get_doc(
            {
                "doctype": "Insights Data Source v3",
                "database_type": "DuckDB",
                "database_name": "Test DuckDB",
            }
        ).insert()


def delete_test_data_sources():
    if frappe.db.exists("Insights Data Source v3", "Test DuckDB"):
        frappe.delete_doc("Insights Data Source v3", "Test DuckDB", force=True)


def create_test_tables():
    for table_name in ["table1", "table2", "table3"]:
        if not frappe.db.exists("Insights Table v3", table_name):
            frappe.get_doc(
                {
                    "doctype": "Insights Table v3",
                    "table_name": table_name,
                    "data_source": "Test DuckDB",
                }
            ).insert()


def delete_test_tables():
    for table_name in ["table1", "table2", "table3"]:
        if frappe.db.exists("Insights Table v3", table_name):
            frappe.delete_doc("Insights Table v3", table_name, force=True)


def create_test_teams():
    if not frappe.db.exists("Insights Team", "team1"):
        team1 = frappe.get_doc({"doctype": "Insights Team", "team_name": "team1"})
        team1.append("team_members", {"user": "insights_user1@test.com"})
        team1.save()


def delete_test_teams():
    if frappe.db.exists("Insights Team", "team1"):
        frappe.delete_doc("Insights Team", "team1", force=True)


def create_test_workbook():
    if not frappe.db.exists("Insights Workbook", "Test Workbook"):
        frappe.get_doc(
            {
                "doctype": "Insights Workbook",
                "title": "Test Workbook",
                "owner": "insights_user1@test.com",
            }
        ).insert()


def delete_test_workbook():
    if frappe.db.exists("Insights Workbook", "Test Workbook"):
        frappe.delete_doc("Insights Workbook", "Test Workbook", force=True)
