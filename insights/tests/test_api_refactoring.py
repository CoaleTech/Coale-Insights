# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import unittest
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch


class TestAPIResponseHelpers(FrappeTestCase):
    """Test suite for API response standardization"""

    def test_success_response_with_data(self):
        """Test success response with data"""
        from insights.api.response import success

        data = {"key": "value", "number": 42}
        result = success(data)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"], data)
        self.assertNotIn("message", result)

    def test_success_response_with_message(self):
        """Test success response with message"""
        from insights.api.response import success

        data = {"result": "ok"}
        message = "Operation completed"
        result = success(data, message)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"], data)
        self.assertEqual(result["message"], message)

    def test_success_response_no_data(self):
        """Test success response without data -- the key is omitted
        entirely, not set to ``None`` (mirrors ``test_success_response_with_message``
        omitting ``"message"`` when none is given)."""
        from insights.api.response import success

        result = success()

        self.assertEqual(result["status"], "success")
        self.assertNotIn("data", result)
        self.assertNotIn("message", result)

    def test_error_response_with_message(self):
        """Test error response with message"""
        from insights.api.response import error

        message = "Something went wrong"
        result = error(message)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], message)
        self.assertIn("timestamp", result)

    def test_error_response_with_exception(self):
        """Test error response with exception"""
        from insights.api.response import error

        message = "Database error"
        exc = ValueError("Invalid value")

        with patch('frappe.log_error') as mock_log:
            result = error(message, exc)

            mock_log.assert_called_once()
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["message"], message)
            self.assertIn("timestamp", result)

    def test_error_response_structure(self):
        """Test error response has required fields"""
        from insights.api.response import error

        result = error("Test error")

        required_fields = ["status", "message", "timestamp"]
        for field in required_fields:
            self.assertIn(field, result)

        self.assertEqual(result["status"], "error")


class TestModularAPIImports(FrappeTestCase):
    """Test suite for modular API structure"""

    def test_customer_api_imports(self):
        """Test customer API functions can be imported"""
        try:
            from insights.api.ml.customer import (
                customer_segmentation,
                customer_intelligence,
                customer_360,
                at_risk_customers
            )
            # Functions should be importable without errors
            self.assertTrue(callable(customer_segmentation))
            self.assertTrue(callable(customer_intelligence))
        except ImportError as e:
            self.fail(f"Failed to import customer API functions: {e}")

    def test_sales_api_imports(self):
        """Test sales API functions can be imported"""
        try:
            from insights.api.ml.sales import (
                sales_forecast,
                sales_intelligence,
                revenue_breakdown
            )
            self.assertTrue(callable(sales_forecast))
            self.assertTrue(callable(sales_intelligence))
        except ImportError as e:
            self.fail(f"Failed to import sales API functions: {e}")

    def test_inventory_api_imports(self):
        """Test inventory API functions can be imported"""
        try:
            from insights.api.ml.inventory import (
                inventory_classification,
                inventory_intelligence,
                get_stock_overview
            )
            self.assertTrue(callable(inventory_classification))
            self.assertTrue(callable(inventory_intelligence))
        except ImportError as e:
            self.fail(f"Failed to import inventory API functions: {e}")

    def test_financial_api_imports(self):
        """Test financial API functions can be imported"""
        try:
            from insights.api.ml.financial import (
                financial_intelligence,
                get_financial_overview,
                get_cash_flow_analysis
            )
            self.assertTrue(callable(financial_intelligence))
            self.assertTrue(callable(get_financial_overview))
        except ImportError as e:
            self.fail(f"Failed to import financial API functions: {e}")

    def test_backward_compatibility_imports(self):
        """Test backward compatibility through main package"""
        try:
            from insights.api.ml import (
                customer_segmentation,
                sales_forecast,
                inventory_classification,
                financial_intelligence
            )
            self.assertTrue(callable(customer_segmentation))
            self.assertTrue(callable(sales_forecast))
            self.assertTrue(callable(inventory_classification))
            self.assertTrue(callable(financial_intelligence))
        except ImportError as e:
            self.fail(f"Backward compatibility imports failed: {e}")

    def test_shared_utilities_import(self):
        """Test shared utilities are accessible"""
        try:
            from insights.api.ml import parse_date_filter
            self.assertTrue(callable(parse_date_filter))
        except ImportError as e:
            self.fail(f"Failed to import shared utilities: {e}")


class TestDateFilterUtilities(FrappeTestCase):
    """Test suite for date filtering utilities"""

    def test_parse_date_filter_months(self):
        """Test parsing month-based date filters"""
        from insights.api.ml import parse_date_filter

        start_date, end_date = parse_date_filter('12m')
        self.assertIsNotNone(start_date)
        self.assertIsNotNone(end_date)
        self.assertLess(start_date, end_date)

    def test_parse_date_filter_days(self):
        """Test parsing day-based date filters"""
        from insights.api.ml import parse_date_filter

        start_date, end_date = parse_date_filter('30d')
        self.assertIsNotNone(start_date)
        self.assertIsNotNone(end_date)
        self.assertLess(start_date, end_date)

    def test_parse_date_filter_all(self):
        """Test parsing 'all' date filter"""
        from insights.api.ml import parse_date_filter

        start_date, end_date = parse_date_filter('all')
        self.assertIsNone(start_date)
        self.assertIsNone(end_date)

    # ``test_get_date_filter_sql_with_dates/_all_dates/_with_alias`` were
    # removed 2026-08-11. ``get_date_filter_sql`` no longer exists -- see
    # ``TestDataValidation.test_sql_injection_prevention``'s removal note in
    # ``test_api_integration.py`` for why: its replacement, ``parse_date_filter``,
    # returns ``(start_date, end_date)`` as ``datetime`` objects (tested above
    # by ``test_parse_date_filter_months/_days/_all``) and every call site
    # binds them through Ibis instead of formatting SQL text.


if __name__ == '__main__':
    unittest.main()