# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Regression tests for the IDOR fix in search.py / cross_dashboard_search.py
(plan-eng-review D-IDOR, 2026-08-04). Before the fix, get_search_history and
save_search_favorite accepted a caller-supplied `user` parameter that
overrode frappe.session.user with no ownership check -- any logged-in user
could read or write another user's search history/favorites.

The fix removes the `user` parameter from the whitelisted API surface
entirely (not just at the service layer), so the strongest guarantee is a
TypeError on the old call shape, not just "the value is ignored".

Note: "Search Activity Log" / "Search Favorite" doctypes do not exist in
this bench (see plan-eng-review code-quality finding 2 -- a separate,
pre-existing gap), so these tests mock the DB layer rather than round-trip
through real records.
"""

import inspect
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from insights.api.ml import search as search_api
from insights.ml.cross_dashboard_search import CrossDashboardSearchService


class TestSearchHistoryIDORFix(FrappeTestCase):
    def test_api_signature_no_longer_accepts_user_param(self):
        """The strongest guarantee: the whitelisted API surface cannot even
        be called with a user override -- it's not just ignored at runtime,
        it's a TypeError at the call site."""
        history_params = list(inspect.signature(search_api.get_search_history).parameters)
        favorite_params = list(inspect.signature(search_api.save_search_favorite).parameters)
        self.assertNotIn("user", history_params)
        self.assertNotIn("user", favorite_params)

    def test_get_search_history_uses_session_user_not_injected_value(self):
        """Even if a caller could smuggle a user kwarg into the service layer
        directly (bypassing the API signature fix), the service itself must
        never accept a caller-controlled user for the query."""
        service = CrossDashboardSearchService()
        with patch.object(frappe, "session") as mock_session, \
             patch.object(frappe.db, "get_list", return_value=[]) as mock_get_list:
            mock_session.user = "victim@example.com"
            service.get_search_history(limit=5)
            _, kwargs = mock_get_list.call_args
            self.assertEqual(kwargs["filters"], {"user": "victim@example.com"})

    def test_save_search_favorite_attributes_to_session_user_not_injected_value(self):
        service = CrossDashboardSearchService()
        with patch.object(frappe, "session") as mock_session, \
             patch("frappe.get_doc") as mock_get_doc:
            mock_session.user = "victim@example.com"
            mock_doc = mock_get_doc.return_value
            service.save_search_favorite(query="revenue", title="My Search")
            created_with = mock_get_doc.call_args[0][0]
            self.assertEqual(created_with["user"], "victim@example.com")
            mock_doc.insert.assert_called_once()

    def test_api_wrapper_calls_service_without_user_kwarg(self):
        """API layer -> service layer call must not pass any user value through."""
        with patch.object(CrossDashboardSearchService, "get_search_history", return_value=[]) as mock_method:
            search_api.get_search_history(limit=10)
            mock_method.assert_called_once_with(10)
