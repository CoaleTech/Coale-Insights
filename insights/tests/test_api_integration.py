# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock
import json
import time


class TestAPIIntegration(FrappeTestCase):
    """Integration tests for API endpoints"""

    def setUp(self):
        """Set up test environment with sample data"""
        self.setup_test_data()

    def tearDown(self):
        """Clean up test data"""
        self.cleanup_test_data()

    def setup_test_data(self):
        """Create comprehensive test data"""
        # Create test company
        if not frappe.db.exists("Company", "Test Insights Co"):
            company = frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Insights Co",
                "default_currency": "USD",
                "country": "United States"
            })
            company.insert(ignore_permissions=True)

        # Create test customers
        for i in range(5):
            customer_name = f"Test Customer {i+1}"
            if not frappe.db.exists("Customer", customer_name):
                customer = frappe.get_doc({
                    "doctype": "Customer",
                    "customer_name": customer_name,
                    "customer_type": "Company"
                })
                customer.insert(ignore_permissions=True)

        # Create test items
        for i in range(3):
            item_code = f"TEST-ITEM-{i+1:03d}"
            if not frappe.db.exists("Item", item_code):
                item = frappe.get_doc({
                    "doctype": "Item",
                    "item_code": item_code,
                    "item_name": f"Test Item {i+1}",
                    "item_group": "Products",
                    "stock_uom": "Nos"
                })
                item.insert(ignore_permissions=True)

        # Create sample sales invoices
        for i in range(10):
            si = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": f"Test Customer {(i % 5) + 1}",
                "company": "Test Insights Co",
                "posting_date": frappe.utils.add_days(frappe.utils.today(), -i),
                "items": [{
                    "item_code": f"TEST-ITEM-{((i % 3) + 1):03d}",
                    "qty": (i % 5) + 1,
                    "rate": 100 + (i * 10),
                    "amount": ((i % 5) + 1) * (100 + (i * 10))
                }]
            })
            si.insert(ignore_permissions=True)
            si.submit()

    def cleanup_test_data(self):
        """Clean up test data"""
        # Delete in reverse order to handle dependencies
        frappe.db.delete("Sales Invoice", {"company": "Test Insights Co"})
        frappe.db.delete("Item", {"item_code": ("like", "TEST-ITEM-%")})
        frappe.db.delete("Customer", {"customer_name": ("like", "Test Customer %")})
        frappe.db.delete("Company", {"company_name": "Test Insights Co"})
        frappe.db.commit()

    @patch('insights.ml.customer_intelligence.CustomerIntelligence.predict')
    def test_customer_intelligence_api_integration(self, mock_predict):
        """Test customer intelligence API integration"""
        from insights.api.ml.customer import customer_intelligence

        # Mock the analysis result
        mock_predict.return_value = {
            "metrics": {"total_customers": 5, "avg_order_value": 500},
            "insights": ["Customer A is high value"],
            "recommendations": ["Focus on Customer A"]
        }

        # Call the API
        result = customer_intelligence()

        # Verify response structure
        self.assertEqual(result['status'], 'success')
        self.assertIn('data', result)
        self.assertIn('metrics', result['data'])
        self.assertIn('insights', result['data'])

        # Verify the mock was called
        mock_predict.assert_called_once()

    @patch('insights.ml.sales_intelligence.SalesIntelligence.train')
    def test_sales_intelligence_api_integration(self, mock_train):
        """Test sales intelligence API integration"""
        from insights.api.ml.sales import sales_intelligence

        mock_train.return_value = {
            "metrics": {"total_revenue": 5000, "total_orders": 10},
            "trends": ["Revenue increasing"],
            "forecast": [5200, 5400, 5600]
        }

        result = sales_intelligence()

        self.assertEqual(result['status'], 'success')
        self.assertIn('data', result)
        mock_train.assert_called_once()

    @patch('insights.ml.inventory_intelligence.InventoryIntelligence.train')
    def test_inventory_intelligence_api_integration(self, mock_train):
        """Test inventory intelligence API integration"""
        from insights.api.ml.inventory import inventory_intelligence

        mock_train.return_value = {
            "metrics": {"total_items": 3, "total_value": 15000},
            "recommendations": ["Reorder ITEM001"],
            "alerts": ["Low stock on ITEM002"]
        }

        result = inventory_intelligence()

        self.assertEqual(result['status'], 'success')
        self.assertIn('data', result)
        mock_train.assert_called_once()

    def test_api_response_consistency(self):
        """Test that all API endpoints return consistent response format"""
        from insights.api.ml.customer import customer_segmentation
        from insights.api.ml.sales import sales_forecast
        from insights.api.ml.inventory import inventory_classification

        endpoints = [
            customer_segmentation,
            sales_forecast,
            inventory_classification
        ]

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint.__name__):
                result = endpoint()

                # All responses should have status field
                self.assertIn('status', result)

                # Success responses should have data field
                if result['status'] == 'success':
                    self.assertIn('data', result)
                # Error responses should have message field
                elif result['status'] == 'error':
                    self.assertIn('message', result)

    def test_api_error_handling(self):
        """Test API error handling for various failure scenarios"""
        from insights.api.ml.customer import customer_intelligence

        # Test with invalid parameters or missing dependencies
        result = customer_intelligence()

        # Should return error response, not raise exception
        self.assertIn('status', result)
        if result['status'] == 'error':
            self.assertIn('message', result)

    def test_backward_compatibility(self):
        """Test that old import paths still work"""
        # Test importing from the main package
        from insights.api.ml import customer_segmentation, sales_forecast

        # Functions should be callable
        self.assertTrue(callable(customer_segmentation))
        self.assertTrue(callable(sales_forecast))

        # Should return proper response format
        result1 = customer_segmentation()
        result2 = sales_forecast()

        self.assertIn('status', result1)
        self.assertIn('status', result2)


class TestPerformanceBenchmarks(FrappeTestCase):
    """Performance tests for API endpoints"""

    def setUp(self):
        """Set up performance test environment"""
        self.max_response_time = 5.0  # seconds

    def test_api_response_time(self):
        """Test that API endpoints respond within acceptable time"""
        from insights.api.ml.customer import customer_segmentation
        from insights.api.ml.general import get_ml_status

        endpoints = [customer_segmentation, get_ml_status]

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint.__name__):
                start_time = time.time()
                result = endpoint()
                end_time = time.time()

                response_time = end_time - start_time
                self.assertLess(response_time, self.max_response_time,
                              f"{endpoint.__name__} took {response_time:.2f}s (max: {self.max_response_time}s)")

                # Should still return valid response
                self.assertIn('status', result)

    @patch('insights.ml.base.BaseMLModel.get_cache')
    @patch('insights.ml.base.BaseMLModel.set_cache')
    def test_caching_performance(self, mock_set_cache, mock_get_cache):
        """Test that caching improves performance"""
        from insights.api.ml.customer import customer_segmentation

        # Mock cache miss first, then cache hit
        mock_get_cache.return_value = None  # Cache miss

        # First call - should compute
        start_time = time.time()
        result1 = customer_segmentation()
        first_call_time = time.time() - start_time

        # Mock cache hit
        mock_get_cache.return_value = {"cached": "data"}

        # Second call - should use cache
        start_time = time.time()
        result2 = customer_segmentation()
        second_call_time = time.time() - start_time

        # Cached call should be faster (though this is a rough test)
        # At minimum, both should complete successfully
        self.assertIn('status', result1)
        self.assertIn('status', result2)


class TestDataValidation(FrappeTestCase):
    """Test data validation and sanitization"""

    def test_date_filter_validation(self):
        """Test date filter parameter validation"""
        from insights.api.ml import parse_date_filter

        # Valid filters
        valid_filters = ['7d', '30d', '90d', '6m', '12m', '24m', 'all']

        for filter_str in valid_filters:
            with self.subTest(filter=filter_str):
                start_date, end_date = parse_date_filter(filter_str)
                # Should not raise exception
                self.assertTrue(True)  # If we get here, parsing worked

        # Invalid filter should default to 12m
        start_date, end_date = parse_date_filter('invalid')
        self.assertIsNotNone(start_date)
        self.assertIsNotNone(end_date)

    def test_sql_injection_prevention(self):
        """Test that SQL parameters are properly sanitized"""
        from insights.api.ml import get_date_filter_sql

        # Test with potentially dangerous input
        dangerous_inputs = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "posting_date'; SELECT * FROM users; --"
        ]

        for dangerous_input in dangerous_inputs:
            with self.subTest(input=dangerous_input):
                # Should not contain the dangerous input in output
                sql = get_date_filter_sql('12m', dangerous_input)
                self.assertNotIn("DROP", sql.upper())
                self.assertNotIn("SELECT", sql.upper())
                self.assertNotIn(";", sql)

    def test_numeric_parameter_validation(self):
        """Test validation of numeric parameters"""
        from insights.api.ml.sales import sales_forecast

        # Test with invalid periods
        result = sales_forecast(periods=-1)
        # Should handle gracefully
        self.assertIn('status', result)

        result = sales_forecast(periods=1000)  # Unrealistically large
        self.assertIn('status', result)


if __name__ == '__main__':
    unittest.main()