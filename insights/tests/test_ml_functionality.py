# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock, mock_open
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class TestMLModelBase(FrappeTestCase):
    """Test suite for ML model base functionality"""

    def setUp(self):
        """Set up test environment"""
        self.test_data = {
            'customer_name': ['Customer A', 'Customer B', 'Customer C'],
            'total_sales': [1000, 2000, 1500],
            'posting_date': [datetime.now() - timedelta(days=i) for i in range(3)]
        }
        self.df = pd.DataFrame(self.test_data)

    def test_base_model_initialization(self):
        """Test base ML model initialization"""
        from insights.ml.base import BaseMLModel

        model = BaseMLModel()
        self.assertIsNotNone(model.model_name)
        self.assertIsNotNone(model.cache_timeout)

    @patch('insights.ml.base.frappe.cache')
    def test_cache_operations(self, mock_cache):
        """Test caching functionality"""
        from insights.ml.base import BaseMLModel

        model = BaseMLModel()
        test_key = "test_key"
        test_data = {"result": "test"}

        # Test cache set
        model.set_cache(test_key, test_data)
        mock_cache.set_value.assert_called_with(test_key, test_data, expires_in_seconds=model.cache_timeout)

        # Test cache get
        mock_cache.get_value.return_value = test_data
        result = model.get_cache(test_key)
        self.assertEqual(result, test_data)

    def test_cached_results_operations(self):
        """Test cached results database operations"""
        from insights.ml.base import BaseMLModel

        model = BaseMLModel()

        # Mock frappe.db operations
        with patch('frappe.db.get_value') as mock_get, \
             patch('frappe.db.set_value') as mock_set:

            mock_get.return_value = None  # No cached result

            # Test get_cached_results when no cache exists
            result = model.get_cached_results("test_model")
            self.assertIsNone(result)

            # Test set_cached_results
            test_data = {"status": "completed"}
            model.set_cached_results("test_model", test_data)
            mock_set.assert_called()


class TestCustomerIntelligence(FrappeTestCase):
    """Test suite for customer intelligence functionality"""

    def setUp(self):
        """Set up test data"""
        # Create test company
        if not frappe.db.exists("Company", "Test Company"):
            company = frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "default_currency": "USD"
            })
            company.insert(ignore_permissions=True)

        # Create test customers
        for i in range(3):
            customer_name = f"Test Customer {i+1}"
            if not frappe.db.exists("Customer", customer_name):
                customer = frappe.get_doc({
                    "doctype": "Customer",
                    "customer_name": customer_name,
                    "customer_type": "Company"
                })
                customer.insert(ignore_permissions=True)

    @patch('insights.ml.customer_intelligence.CustomerIntelligence._get_customer_transactions')
    def test_customer_intelligence_initialization(self, mock_get_data):
        """Test customer intelligence model initialization"""
        from insights.ml.customer_intelligence import CustomerIntelligence

        mock_get_data.return_value = pd.DataFrame({
            'customer_name': ['Customer A'],
            'total_sales': [1000]
        })

        model = CustomerIntelligence()
        self.assertEqual(model.model_name, "CustomerIntelligence")
        self.assertIsNotNone(model.date_filter_sql)

    @patch('insights.ml.customer_intelligence.frappe.db.sql')
    def test_get_customer_transactions(self, mock_sql):
        """Test customer transaction data retrieval"""
        from insights.ml.customer_intelligence import CustomerIntelligence

        # Mock SQL result
        mock_sql.return_value = [
            ['Customer A', 1000.0, '2024-01-01'],
            ['Customer B', 2000.0, '2024-01-02']
        ]

        model = CustomerIntelligence()
        df = model._get_customer_transactions()

        self.assertIsInstance(df, pd.DataFrame)
        self.assertIn('customer_name', df.columns)
        self.assertIn('total_sales', df.columns)

    def test_calculate_customer_metrics(self):
        """Test customer metrics calculation"""
        from insights.ml.customer_intelligence import CustomerIntelligence

        test_data = pd.DataFrame({
            'customer_name': ['A', 'B', 'A', 'C'],
            'total_sales': [100, 200, 150, 300],
            'posting_date': pd.date_range('2024-01-01', periods=4)
        })

        model = CustomerIntelligence()
        metrics = model._calculate_customer_metrics(test_data)

        self.assertIsInstance(metrics, dict)
        self.assertIn('total_customers', metrics)
        self.assertIn('avg_order_value', metrics)

    @patch('insights.ml.customer_intelligence.CustomerIntelligence._get_customer_transactions')
    @patch('insights.ml.customer_intelligence.CustomerIntelligence._calculate_customer_metrics')
    def test_analyze_customer_data(self, mock_calculate, mock_get_data):
        """Test customer data analysis"""
        from insights.ml.customer_intelligence import CustomerIntelligence

        mock_get_data.return_value = pd.DataFrame({'customer_name': ['A'], 'total_sales': [1000]})
        mock_calculate.return_value = {'total_customers': 1, 'avg_order_value': 1000}

        model = CustomerIntelligence()
        result = model.analyze_customer_data()

        self.assertIsInstance(result, dict)
        self.assertIn('metrics', result)
        self.assertIn('insights', result)


class TestSalesIntelligence(FrappeTestCase):
    """Test suite for sales intelligence functionality"""

    @patch('insights.ml.sales_intelligence.SalesIntelligence._get_sales_data')
    def test_sales_intelligence_initialization(self, mock_get_data):
        """Test sales intelligence model initialization"""
        from insights.ml.sales_intelligence import SalesIntelligence

        mock_get_data.return_value = pd.DataFrame({
            'item_code': ['ITEM001'],
            'total_sales': [1000]
        })

        model = SalesIntelligence()
        self.assertEqual(model.model_name, "SalesIntelligence")
        self.assertIsNotNone(model.DATE_FILTER_24M)

    @patch('insights.ml.sales_intelligence.frappe.db.sql')
    def test_get_sales_data(self, mock_sql):
        """Test sales data retrieval"""
        from insights.ml.sales_intelligence import SalesIntelligence

        mock_sql.return_value = [
            ['ITEM001', 1000.0, '2024-01-01'],
            ['ITEM002', 2000.0, '2024-01-02']
        ]

        model = SalesIntelligence()
        df = model._get_sales_data()

        self.assertIsInstance(df, pd.DataFrame)
        self.assertIn('item_code', df.columns)

    def test_calculate_sales_metrics(self):
        """Test sales metrics calculation"""
        from insights.ml.sales_intelligence import SalesIntelligence

        test_data = pd.DataFrame({
            'item_code': ['A', 'B', 'A'],
            'qty': [10, 20, 15],
            'amount': [100, 200, 150],
            'posting_date': pd.date_range('2024-01-01', periods=3)
        })

        model = SalesIntelligence()
        metrics = model._calculate_sales_metrics(test_data)

        self.assertIsInstance(metrics, dict)
        self.assertIn('total_revenue', metrics)
        self.assertIn('total_quantity', metrics)


class TestInventoryIntelligence(FrappeTestCase):
    """Test suite for inventory intelligence functionality"""

    @patch('insights.ml.inventory_intelligence.InventoryIntelligence._get_inventory_data')
    def test_inventory_intelligence_initialization(self, mock_get_data):
        """Test inventory intelligence model initialization"""
        from insights.ml.inventory_intelligence import InventoryIntelligence

        mock_get_data.return_value = pd.DataFrame({
            'item_code': ['ITEM001'],
            'actual_qty': [100]
        })

        model = InventoryIntelligence()
        self.assertEqual(model.model_name, "InventoryIntelligence")
        self.assertIsNotNone(model.date_filter_sql)

    @patch('insights.ml.inventory_intelligence.frappe.db.sql')
    def test_get_inventory_data(self, mock_sql):
        """Test inventory data retrieval"""
        from insights.ml.inventory_intelligence import InventoryIntelligence

        mock_sql.return_value = [
            ['ITEM001', 100.0, 50.0, 'WAREHOUSE001'],
            ['ITEM002', 200.0, 75.0, 'WAREHOUSE002']
        ]

        model = InventoryIntelligence()
        df = model._get_inventory_data()

        self.assertIsInstance(df, pd.DataFrame)
        self.assertIn('item_code', df.columns)
        self.assertIn('actual_qty', df.columns)

    def test_calculate_inventory_metrics(self):
        """Test inventory metrics calculation"""
        from insights.ml.inventory_intelligence import InventoryIntelligence

        test_data = pd.DataFrame({
            'item_code': ['A', 'B'],
            'actual_qty': [100, 200],
            'reserved_qty': [10, 20],
            'valuation_rate': [50, 75]
        })

        model = InventoryIntelligence()
        metrics = model._calculate_inventory_metrics(test_data)

        self.assertIsInstance(metrics, dict)
        self.assertIn('total_items', metrics)
        self.assertIn('total_value', metrics)


class TestFinancialIntelligence(FrappeTestCase):
    """Test suite for financial intelligence functionality"""

    def setUp(self):
        """Set up test company data"""
        if not frappe.db.exists("Company", "Test Company"):
            company = frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "default_currency": "USD"
            })
            company.insert(ignore_permissions=True)

    @patch('insights.ml.financial_intelligence.FinancialIntelligence._get_financial_data')
    def test_financial_intelligence_initialization(self, mock_get_data):
        """Test financial intelligence model initialization"""
        from insights.ml.financial_intelligence import FinancialIntelligence

        mock_get_data.return_value = pd.DataFrame({
            'account': ['Sales Account'],
            'debit': [1000],
            'credit': [0]
        })

        model = FinancialIntelligence()
        self.assertEqual(model.model_name, "FinancialIntelligence")
        self.assertIsNotNone(model.company)
        self.assertIsNotNone(model.base_currency)

    @patch('insights.ml.financial_intelligence.frappe.db.sql')
    def test_get_financial_data(self, mock_sql):
        """Test financial data retrieval"""
        from insights.ml.financial_intelligence import FinancialIntelligence

        mock_sql.return_value = [
            ['Sales', 1000.0, 0.0, '2024-01-01'],
            ['Cost of Goods Sold', 0.0, 600.0, '2024-01-01']
        ]

        model = FinancialIntelligence()
        df = model._get_financial_data()

        self.assertIsInstance(df, pd.DataFrame)
        self.assertIn('account', df.columns)
        self.assertIn('debit', df.columns)
        self.assertIn('credit', df.columns)

    def test_calculate_financial_ratios(self):
        """Test financial ratios calculation"""
        from insights.ml.financial_intelligence import FinancialIntelligence

        test_data = pd.DataFrame({
            'account': ['Revenue', 'COGS', 'Assets', 'Liabilities'],
            'amount': [1000, 600, 2000, 800]
        })

        model = FinancialIntelligence()
        ratios = model._calculate_financial_ratios(test_data)

        self.assertIsInstance(ratios, dict)
        # Should contain common financial ratios
        self.assertTrue(any('ratio' in key.lower() or 'margin' in key.lower()
                          for key in ratios.keys()))


class TestAPIDefensiveProgramming(FrappeTestCase):
    """Test suite for API defensive programming (optional dependencies)"""

    @patch.dict('sys.modules', {'sklearn': None})
    def test_customer_segmentation_without_sklearn(self):
        """Test customer segmentation handles missing sklearn gracefully"""
        from insights.api.ml.customer import customer_segmentation

        # This should not raise an exception, but return an error response
        result = customer_segmentation()

        self.assertEqual(result['status'], 'error')
        self.assertIn('not available', result['message'].lower())

    @patch.dict('sys.modules', {'prophet': None})
    def test_sales_forecast_without_prophet(self):
        """Test sales forecast handles missing prophet gracefully"""
        from insights.api.ml.sales import sales_forecast

        result = sales_forecast()

        self.assertEqual(result['status'], 'error')
        self.assertIn('not available', result['message'].lower())

    @patch.dict('sys.modules', {'pandas': None})
    def test_inventory_intelligence_without_pandas(self):
        """Test inventory intelligence handles missing pandas gracefully"""
        from insights.api.ml.inventory import inventory_intelligence

        result = inventory_intelligence()

        self.assertEqual(result['status'], 'error')
        self.assertIn('not available', result['message'].lower())


if __name__ == '__main__':
    unittest.main()