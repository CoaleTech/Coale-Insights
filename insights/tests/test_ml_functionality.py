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


class TestInventoryAPIDrillDown(FrappeTestCase):
    """Test suite for inventory drill-down API endpoints"""

    @patch('insights.api.ml.inventory.frappe.has_permission')
    @patch('insights.api.ml.inventory.frappe.get_list')
    @patch('insights.api.ml.inventory.frappe.db.count')
    def test_get_inventory_detail_total_skus(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test total_skus drill-down returns active stock items"""
        from insights.api.ml.inventory import get_inventory_detail

        mock_get_list.return_value = [
            {
                'name': 'ITEM-001',
                'item_name': 'Test Item 1',
                'item_group': 'Raw Material',
                'stock_uom': 'Nos',
                'valuation_method': 'FIFO'
            }
        ]
        mock_db_count.return_value = 1

        result = get_inventory_detail('total_skus', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(len(result['data']['rows']), 1)
        self.assertEqual(result['data']['total'], 1)
        self.assertEqual(result['data']['columns'][0]['fieldname'], 'name')
        mock_has_permission.assert_called_with('Item', throw=True)
        mock_get_list.assert_called_once()
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters'], {'disabled': 0, 'is_stock_item': 1})

    @patch('insights.api.ml.inventory.frappe.has_permission')
    @patch('insights.api.ml.inventory.frappe.get_list')
    @patch('insights.api.ml.inventory.frappe.db.count')
    def test_get_inventory_detail_warehouse_stock(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test warehouse_stock drill-down with warehouse filter"""
        from insights.api.ml.inventory import get_inventory_detail

        mock_get_list.return_value = [
            {
                'item_code': 'ITEM-001',
                'warehouse': 'Stores - TC',
                'actual_qty': 100.0,
                'reserved_qty': 10.0,
                'ordered_qty': 5.0
            }
        ]
        mock_db_count.return_value = 1

        result = get_inventory_detail('warehouse_stock', '{"warehouse": "Stores - TC", "page": 1}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(len(result['data']['rows']), 1)
        self.assertEqual(result['data']['rows'][0]['warehouse'], 'Stores - TC')
        mock_has_permission.assert_called_with('Bin', throw=True)
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters'], {'actual_qty': ('>', 0), 'warehouse': 'Stores - TC'})

    @patch('insights.api.ml.inventory.frappe.has_permission')
    @patch('insights.api.ml.inventory.frappe.qb')
    def test_get_inventory_detail_low_stock_items(self, mock_qb, mock_has_permission):
        """Test low_stock_items drill-down joins Bin with Item Reorder"""
        from insights.api.ml.inventory import get_inventory_detail

        # Build a chainable Query Builder mock
        mock_query = MagicMock()
        mock_query.join.return_value = mock_query
        mock_query.on.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.select.return_value = mock_query
        mock_query.orderby.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.run.side_effect = [
            [
                {
                    'item_code': 'ITEM-001',
                    'warehouse': 'Stores - TC',
                    'actual_qty': 5.0,
                    'projected_qty': 5.0,
                    'reorder_level': 10.0
                }
            ],
            [(1,)]
        ]
        mock_qb.from_.return_value = mock_query
        mock_qb.DocType.return_value = MagicMock()
        mock_qb.functions.Count.return_value.as_.return_value = 'total_count'

        result = get_inventory_detail('low_stock_items', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(len(result['data']['rows']), 1)
        self.assertEqual(result['data']['total'], 1)
        self.assertEqual(result['data']['rows'][0]['item_code'], 'ITEM-001')
        self.assertEqual(result['data']['rows'][0]['reorder_level'], 10.0)
        mock_has_permission.assert_called_with('Bin', throw=True)

    def test_get_inventory_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.inventory import get_inventory_detail

        with self.assertRaises(frappe.ValidationError):
            get_inventory_detail('unknown_metric', '{}')

    @patch('insights.api.ml.inventory.frappe.has_permission')
    def test_get_inventory_detail_permission_error(self, mock_has_permission):
        """Test permission error is propagated"""
        from insights.api.ml.inventory import get_inventory_detail

        mock_has_permission.side_effect = frappe.PermissionError('No permission')

        with self.assertRaises(frappe.PermissionError):
            get_inventory_detail('total_skus', '{}')


class TestSalesAPIDrillDown(FrappeTestCase):
    """Test suite for sales drill-down API endpoints"""

    @patch('insights.api.ml.sales.frappe.has_permission')
    @patch('insights.api.ml.sales.frappe.get_list')
    @patch('insights.api.ml.sales.frappe.db.count')
    def test_get_sales_detail_total_orders(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test total_orders drill-down returns sales invoices"""
        from insights.api.ml.sales import get_sales_detail

        mock_get_list.return_value = [
            {
                'name': 'SINV-001',
                'customer': 'Customer A',
                'posting_date': '2024-01-15',
                'grand_total': 1000.0,
                'currency': 'KES',
                'territory': 'Nairobi'
            }
        ]
        mock_db_count.return_value = 1

        result = get_sales_detail('total_orders', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(len(result['data']['rows']), 1)
        self.assertEqual(result['data']['total'], 1)
        self.assertEqual(result['data']['columns'][0]['fieldname'], 'name')
        mock_has_permission.assert_called_with('Sales Invoice', throw=True)
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['docstatus'], 1)
        self.assertIn('posting_date', kwargs['filters'])

    @patch('insights.api.ml.sales.frappe.has_permission')
    @patch('insights.api.ml.sales.frappe.get_list')
    @patch('insights.api.ml.sales.frappe.db.count')
    def test_get_sales_detail_pending_orders(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test pending_orders drill-down returns open sales orders"""
        from insights.api.ml.sales import get_sales_detail

        mock_get_list.return_value = [
            {
                'name': 'SO-001',
                'customer': 'Customer A',
                'transaction_date': '2024-01-10',
                'delivery_date': '2024-01-20',
                'grand_total': 500.0,
                'status': 'To Deliver and Bill'
            }
        ]
        mock_db_count.return_value = 1

        result = get_sales_detail('pending_orders', '{"company": "Test Company"}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['name'], 'SO-001')
        self.assertEqual(result['data']['columns'][0]['options'], 'Sales Order')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['company'], 'Test Company')
        self.assertEqual(kwargs['filters']['status']['not_in'], ['Completed', 'Cancelled', 'Closed'])

    @patch('insights.api.ml.sales.frappe.has_permission')
    @patch('insights.api.ml.sales.frappe.get_list')
    @patch('insights.api.ml.sales.frappe.db.count')
    def test_get_sales_detail_sales_by_territory(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test sales_by_territory drill-down filters by territory"""
        from insights.api.ml.sales import get_sales_detail

        mock_get_list.return_value = [
            {
                'name': 'SINV-002',
                'customer': 'Customer B',
                'territory': 'Mombasa',
                'posting_date': '2024-02-01',
                'grand_total': 2000.0
            }
        ]
        mock_db_count.return_value = 1

        result = get_sales_detail('sales_by_territory', '{"territory": "Mombasa"}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['territory'], 'Mombasa')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['territory'], 'Mombasa')

    def test_get_sales_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.sales import get_sales_detail

        with self.assertRaises(frappe.ValidationError):
            get_sales_detail('unknown_metric', '{}')


class TestFinancialAPIDrillDown(FrappeTestCase):
    """Test suite for financial drill-down API endpoints"""

    @patch('insights.api.ml.financial.frappe.has_permission')
    @patch('insights.api.ml.financial.frappe.get_list')
    @patch('insights.api.ml.financial.frappe.db.count')
    def test_get_finance_detail_outstanding_ar(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test outstanding_ar drill-down returns open sales invoices"""
        from insights.api.ml.financial import get_finance_detail

        mock_get_list.return_value = [
            {
                'name': 'SINV-003',
                'customer': 'Customer C',
                'posting_date': '2024-01-01',
                'due_date': '2024-02-01',
                'grand_total': 3000.0,
                'outstanding_amount': 1500.0,
                'currency': 'KES'
            }
        ]
        mock_db_count.return_value = 1

        result = get_finance_detail('outstanding_ar', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['outstanding_amount'], 1500.0)
        self.assertEqual(result['data']['columns'][0]['options'], 'Sales Invoice')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['outstanding_amount'], ('>', 0))

    @patch('insights.api.ml.financial.frappe.has_permission')
    @patch('insights.api.ml.financial.frappe.get_list')
    @patch('insights.api.ml.financial.frappe.db.count')
    def test_get_finance_detail_overdue_ar_90(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test overdue_ar_90 drill-down applies 90-day cutoff"""
        from insights.api.ml.financial import get_finance_detail

        mock_get_list.return_value = [
            {
                'name': 'SINV-004',
                'customer': 'Customer D',
                'posting_date': '2023-01-01',
                'due_date': '2023-02-01',
                'grand_total': 5000.0,
                'outstanding_amount': 5000.0
            }
        ]
        mock_db_count.return_value = 1

        result = get_finance_detail('overdue_ar_90', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['name'], 'SINV-004')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['outstanding_amount'], ('>', 0))
        self.assertIn('due_date', kwargs['filters'])

    @patch('insights.api.ml.financial.frappe.has_permission')
    @patch('insights.api.ml.financial.frappe.get_list')
    @patch('insights.api.ml.financial.frappe.db.count')
    def test_get_finance_detail_outstanding_ap(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test outstanding_ap drill-down returns open purchase invoices"""
        from insights.api.ml.financial import get_finance_detail

        mock_get_list.return_value = [
            {
                'name': 'PINV-001',
                'supplier': 'Supplier A',
                'posting_date': '2024-01-05',
                'due_date': '2024-02-05',
                'grand_total': 2500.0,
                'outstanding_amount': 1000.0
            }
        ]
        mock_db_count.return_value = 1

        result = get_finance_detail('outstanding_ap', '{"company": "Test Company"}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['columns'][0]['options'], 'Purchase Invoice')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['company'], 'Test Company')

    @patch('insights.api.ml.financial.frappe.has_permission')
    @patch('insights.api.ml.financial.frappe.get_list')
    @patch('insights.api.ml.financial.frappe.db.count')
    def test_get_finance_detail_cash_accounts(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test cash_accounts drill-down returns bank/cash accounts"""
        from insights.api.ml.financial import get_finance_detail

        mock_get_list.return_value = [
            {
                'name': 'Cash - TC',
                'account_name': 'Cash',
                'account_type': 'Cash',
                'account_currency': 'KES'
            }
        ]
        mock_db_count.return_value = 1

        result = get_finance_detail('cash_accounts', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['account_type'], 'Cash')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['account_type']['in'], ['Cash', 'Bank'])
        self.assertEqual(kwargs['filters']['is_group'], 0)

    def test_get_finance_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.financial import get_finance_detail

        with self.assertRaises(frappe.ValidationError):
            get_finance_detail('unknown_metric', '{}')


class TestCustomerAPIDrillDown(FrappeTestCase):
    """Test suite for customer drill-down API endpoints"""

    @patch('insights.api.ml.customer.frappe.has_permission')
    @patch('insights.api.ml.customer.frappe.get_list')
    @patch('insights.api.ml.customer.frappe.db.count')
    def test_get_customer_detail_total_customers(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test total_customers drill-down returns active customers"""
        from insights.api.ml.customer import get_customer_detail

        mock_get_list.return_value = [
            {
                'name': 'CUST-001',
                'customer_name': 'Customer A',
                'customer_group': 'Commercial',
                'territory': 'Nairobi',
                'customer_type': 'Company'
            }
        ]
        mock_db_count.return_value = 1

        result = get_customer_detail('total_customers', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['name'], 'CUST-001')
        self.assertEqual(result['data']['columns'][0]['options'], 'Customer')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters'], {'disabled': 0})

    @patch('insights.api.ml.customer.frappe.has_permission')
    @patch('insights.api.ml.customer.frappe.get_list')
    @patch('insights.api.ml.customer.frappe.db.count')
    def test_get_customer_detail_top_customers(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test top_customers drill-down returns customer invoices"""
        from insights.api.ml.customer import get_customer_detail

        mock_get_list.return_value = [
            {
                'name': 'SINV-005',
                'customer': 'CUST-001',
                'posting_date': '2024-01-15',
                'grand_total': 5000.0,
                'outstanding_amount': 0.0
            }
        ]
        mock_db_count.return_value = 1

        result = get_customer_detail('top_customers', '{"company": "Test Company"}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['customer'], 'CUST-001')
        self.assertEqual(result['data']['columns'][0]['options'], 'Sales Invoice')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['company'], 'Test Company')
        self.assertEqual(kwargs['filters']['docstatus'], 1)

    @patch('insights.api.ml.customer.frappe.has_permission')
    @patch('insights.api.ml.customer.frappe.get_list')
    @patch('insights.api.ml.customer.frappe.db.count')
    @patch('insights.api.ml.customer.frappe.utils')
    def test_get_customer_detail_new_customers(self, mock_utils, mock_db_count, mock_get_list, mock_has_permission):
        """Test new_customers drill-down applies creation cutoff"""
        from insights.api.ml.customer import get_customer_detail

        mock_utils.today.return_value = '2024-06-17'
        mock_utils.add_days.return_value = '2024-05-18'
        mock_get_list.return_value = [
            {
                'name': 'CUST-002',
                'customer_name': 'Customer B',
                'customer_group': 'Individual',
                'territory': 'Mombasa',
                'creation': '2024-06-01'
            }
        ]
        mock_db_count.return_value = 1

        result = get_customer_detail('new_customers', '{"period": "30d"}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['name'], 'CUST-002')
        _, kwargs = mock_get_list.call_args
        self.assertIn('creation', kwargs['filters'])

    def test_get_customer_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.customer import get_customer_detail

        with self.assertRaises(frappe.ValidationError):
            get_customer_detail('unknown_metric', '{}')


class TestProcurementAPIDrillDown(FrappeTestCase):
    """Test suite for procurement drill-down API endpoints"""

    @patch('insights.api.ml.procurement.frappe.has_permission')
    @patch('insights.api.ml.procurement.frappe.get_list')
    @patch('insights.api.ml.procurement.frappe.db.count')
    def test_get_procurement_detail_total_pos(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test total_pos drill-down returns submitted purchase orders"""
        from insights.api.ml.procurement import get_procurement_detail

        mock_get_list.return_value = [
            {
                'name': 'PO-001',
                'supplier': 'Supplier A',
                'transaction_date': '2024-01-10',
                'schedule_date': '2024-01-20',
                'grand_total': 3000.0,
                'status': 'To Receive and Bill'
            }
        ]
        mock_db_count.return_value = 1

        result = get_procurement_detail('total_pos', '{"company": "Test Company"}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['name'], 'PO-001')
        self.assertEqual(result['data']['columns'][0]['options'], 'Purchase Order')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['company'], 'Test Company')
        self.assertEqual(kwargs['filters']['docstatus'], 1)

    @patch('insights.api.ml.procurement.frappe.has_permission')
    @patch('insights.api.ml.procurement.frappe.get_list')
    @patch('insights.api.ml.procurement.frappe.db.count')
    def test_get_procurement_detail_pending_pos(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test pending_pos drill-down excludes completed/cancelled/closed"""
        from insights.api.ml.procurement import get_procurement_detail

        mock_get_list.return_value = [
            {
                'name': 'PO-002',
                'supplier': 'Supplier B',
                'transaction_date': '2024-02-01',
                'schedule_date': '2024-02-10',
                'grand_total': 1500.0,
                'status': 'To Receive',
                'per_received': 0.0
            }
        ]
        mock_db_count.return_value = 1

        result = get_procurement_detail('pending_pos', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertIn('per_received', [c['fieldname'] for c in result['data']['columns']])
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['status']['not_in'], ['Completed', 'Cancelled', 'Closed'])

    @patch('insights.api.ml.procurement.frappe.has_permission')
    @patch('insights.api.ml.procurement.frappe.get_list')
    @patch('insights.api.ml.procurement.frappe.db.count')
    def test_get_procurement_detail_supplier_performance(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test supplier_performance drill-down filters by supplier"""
        from insights.api.ml.procurement import get_procurement_detail

        mock_get_list.return_value = [
            {
                'name': 'PO-003',
                'supplier': 'Supplier C',
                'transaction_date': '2024-03-01',
                'schedule_date': '2024-03-10',
                'grand_total': 2000.0,
                'status': 'Completed'
            }
        ]
        mock_db_count.return_value = 1

        result = get_procurement_detail('supplier_performance', '{"supplier": "Supplier C"}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['supplier'], 'Supplier C')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['supplier'], 'Supplier C')

    def test_get_procurement_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.procurement import get_procurement_detail

        with self.assertRaises(frappe.ValidationError):
            get_procurement_detail('unknown_metric', '{}')


class TestHRAPIDrillDown(FrappeTestCase):
    """Test suite for HR drill-down API endpoints"""

    @patch('insights.api.ml.hr.frappe.has_permission')
    @patch('insights.api.ml.hr.frappe.get_list')
    @patch('insights.api.ml.hr.frappe.db.count')
    def test_get_hr_detail_total_employees(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test total_employees drill-down returns active employees"""
        from insights.api.ml.hr import get_hr_detail

        mock_get_list.return_value = [
            {
                'name': 'EMP-001',
                'employee_name': 'John Doe',
                'department': 'Sales',
                'designation': 'Manager',
                'status': 'Active'
            }
        ]
        mock_db_count.return_value = 1

        result = get_hr_detail('total_employees', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['name'], 'EMP-001')
        self.assertEqual(result['data']['columns'][0]['options'], 'Employee')

    @patch('insights.api.ml.hr.frappe.has_permission')
    @patch('insights.api.ml.hr.frappe.get_list')
    @patch('insights.api.ml.hr.frappe.db.count')
    def test_get_hr_detail_dept_employees(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test dept_employees drill-down filters by department"""
        from insights.api.ml.hr import get_hr_detail

        mock_get_list.return_value = [
            {
                'name': 'EMP-002',
                'employee_name': 'Jane Smith',
                'department': 'Engineering',
                'designation': 'Developer'
            }
        ]
        mock_db_count.return_value = 1

        result = get_hr_detail('dept_employees', '{"department": "Engineering"}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['department'], 'Engineering')

    @patch('insights.api.ml.hr.frappe.has_permission')
    @patch('insights.api.ml.hr.frappe.get_list')
    @patch('insights.api.ml.hr.frappe.db.count')
    def test_get_hr_detail_employment_type(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test employment_type drill-down filters by employment type"""
        from insights.api.ml.hr import get_hr_detail

        mock_get_list.return_value = [
            {
                'name': 'EMP-003',
                'employee_name': 'Contractor A',
                'department': 'Operations',
                'employment_type': 'Contract'
            }
        ]
        mock_db_count.return_value = 1

        result = get_hr_detail('employment_type', '{"employment_type": "Contract"}')

        self.assertEqual(result['status'], 'success')
        self.assertIn('Contract', result['data']['rows'][0].values())

    def test_get_hr_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.hr import get_hr_detail

        with self.assertRaises(frappe.ValidationError):
            get_hr_detail('unknown_metric', '{}')


class TestRiskAPIDrillDown(FrappeTestCase):
    """Test suite for risk drill-down API endpoints"""

    @patch('insights.api.ml.risk.frappe.has_permission')
    @patch('insights.api.ml.risk.frappe.get_list')
    @patch('insights.api.ml.risk.frappe.db.count')
    def test_get_risk_detail_overdue_invoices(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test overdue_invoices drill-down returns past-due sales invoices"""
        from insights.api.ml.risk import get_risk_detail

        mock_get_list.return_value = [
            {
                'name': 'SINV-005',
                'customer': 'Customer E',
                'posting_date': '2024-01-01',
                'due_date': '2024-01-15',
                'outstanding_amount': 2500.0
            }
        ]
        mock_db_count.return_value = 1

        result = get_risk_detail('overdue_invoices', '{"company": "Test Company"}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['name'], 'SINV-005')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['outstanding_amount'], ('>', 0))
        self.assertEqual(kwargs['filters']['company'], 'Test Company')

    @patch('insights.api.ml.risk.frappe.has_permission')
    @patch('insights.api.ml.risk.frappe.get_list')
    @patch('insights.api.ml.risk.frappe.db.count')
    def test_get_risk_detail_overdue_payables(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test overdue_payables drill-down returns past-due purchase invoices"""
        from insights.api.ml.risk import get_risk_detail

        mock_get_list.return_value = [
            {
                'name': 'PINV-002',
                'supplier': 'Supplier D',
                'posting_date': '2024-01-01',
                'due_date': '2024-01-15',
                'outstanding_amount': 1200.0
            }
        ]
        mock_db_count.return_value = 1

        result = get_risk_detail('overdue_payables', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['columns'][0]['options'], 'Purchase Invoice')

    def test_get_risk_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.risk import get_risk_detail

        with self.assertRaises(frappe.ValidationError):
            get_risk_detail('unknown_metric', '{}')


class TestExecutiveAPIDrillDown(FrappeTestCase):
    """Test suite for executive drill-down API endpoints"""

    @patch('insights.api.ml.executive.frappe.has_permission')
    @patch('insights.api.ml.executive.frappe.get_list')
    @patch('insights.api.ml.executive.frappe.db.count')
    def test_get_executive_detail_revenue_invoices(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test revenue_invoices drill-down returns submitted invoices"""
        from insights.api.ml.executive import get_executive_detail

        mock_get_list.return_value = [
            {
                'name': 'SINV-006',
                'customer': 'Customer F',
                'posting_date': '2024-01-20',
                'grand_total': 8000.0
            }
        ]
        mock_db_count.return_value = 1

        result = get_executive_detail('revenue_invoices', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['grand_total'], 8000.0)

    @patch('insights.api.ml.executive.frappe.has_permission')
    @patch('insights.api.ml.executive.frappe.get_list')
    @patch('insights.api.ml.executive.frappe.db.count')
    def test_get_executive_detail_active_employees(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test active_employees drill-down returns active employees"""
        from insights.api.ml.executive import get_executive_detail

        mock_get_list.return_value = [
            {
                'name': 'EMP-004',
                'employee_name': 'Executive A',
                'department': 'Leadership',
                'designation': 'CEO'
            }
        ]
        mock_db_count.return_value = 1

        result = get_executive_detail('active_employees', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['columns'][0]['options'], 'Employee')

    def test_get_executive_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.executive import get_executive_detail

        with self.assertRaises(frappe.ValidationError):
            get_executive_detail('unknown_metric', '{}')


class TestManufacturingAPIDrillDown(FrappeTestCase):
    """Test suite for manufacturing drill-down API endpoints"""

    @patch('insights.api.ml.manufacturing.frappe.has_permission')
    @patch('insights.api.ml.manufacturing.frappe.get_list')
    @patch('insights.api.ml.manufacturing.frappe.db.count')
    def test_get_manufacturing_detail_open_work_orders(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test open_work_orders drill-down excludes completed/cancelled/stopped"""
        from insights.api.ml.manufacturing import get_manufacturing_detail

        mock_get_list.return_value = [
            {
                'name': 'WO-001',
                'production_item': 'ITEM-A',
                'qty': 100.0,
                'produced_qty': 20.0,
                'planned_start_date': '2024-01-01',
                'planned_end_date': '2024-01-10',
                'status': 'In Process'
            }
        ]
        mock_db_count.return_value = 1

        result = get_manufacturing_detail('open_work_orders', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['columns'][0]['options'], 'Work Order')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['status']['not_in'], ['Completed', 'Cancelled', 'Stopped'])

    @patch('insights.api.ml.manufacturing.frappe.has_permission')
    @patch('insights.api.ml.manufacturing.frappe.get_list')
    @patch('insights.api.ml.manufacturing.frappe.db.count')
    @patch('insights.api.ml.manufacturing.frappe.utils')
    def test_get_manufacturing_detail_completed_work_orders(self, mock_utils, mock_db_count, mock_get_list, mock_has_permission):
        """Test completed_work_orders drill-down applies period cutoff"""
        from insights.api.ml.manufacturing import get_manufacturing_detail

        mock_utils.today.return_value = '2024-06-17'
        mock_utils.add_days.return_value = '2024-05-18'
        mock_get_list.return_value = [
            {
                'name': 'WO-002',
                'production_item': 'ITEM-B',
                'qty': 50.0,
                'produced_qty': 50.0,
                'planned_end_date': '2024-05-20'
            }
        ]
        mock_db_count.return_value = 1

        result = get_manufacturing_detail('completed_work_orders', '{"period": "30d"}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['qty'], 50.0)
        _, kwargs = mock_get_list.call_args
        self.assertIn('modified', kwargs['filters'])

    def test_get_manufacturing_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.manufacturing import get_manufacturing_detail

        with self.assertRaises(frappe.ValidationError):
            get_manufacturing_detail('unknown_metric', '{}')


class TestMarketingAPIDrillDown(FrappeTestCase):
    """Test suite for marketing/CRM drill-down API endpoints"""

    @patch('insights.api.ml.marketing.frappe.has_permission')
    @patch('insights.api.ml.marketing.frappe.get_list')
    @patch('insights.api.ml.marketing.frappe.db.count')
    def test_get_crm_detail_leads(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test leads drill-down returns open leads"""
        from insights.api.ml.marketing import get_crm_detail

        mock_get_list.return_value = [
            {
                'name': 'LEAD-001',
                'lead_name': 'Lead A',
                'company_name': 'Company A',
                'status': 'Open',
                'source': 'Website',
                'lead_owner': 'user@example.com',
                'creation': '2024-06-01'
            }
        ]
        mock_db_count.return_value = 1

        result = get_crm_detail('leads', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['columns'][0]['options'], 'Lead')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters'], {'docstatus': 0})

    @patch('insights.api.ml.marketing.frappe.has_permission')
    @patch('insights.api.ml.marketing.frappe.get_list')
    @patch('insights.api.ml.marketing.frappe.db.count')
    def test_get_crm_detail_opportunities(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test opportunities drill-down returns open opportunities"""
        from insights.api.ml.marketing import get_crm_detail

        mock_get_list.return_value = [
            {
                'name': 'OPP-001',
                'opportunity_from': 'Lead',
                'party_name': 'Lead A',
                'opportunity_amount': 10000.0,
                'expected_closing': '2024-07-01',
                'status': 'Open',
                'sales_stage': 'Proposal'
            }
        ]
        mock_db_count.return_value = 1

        result = get_crm_detail('opportunities', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['columns'][0]['options'], 'Opportunity')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['status']['not_in'], ['Closed', 'Lost'])

    def test_get_crm_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.marketing import get_crm_detail

        with self.assertRaises(frappe.ValidationError):
            get_crm_detail('unknown_metric', '{}')


class TestTaxAPIDrillDown(FrappeTestCase):
    """Test suite for tax drill-down API endpoints"""

    @patch('insights.api.ml.tax.frappe.has_permission')
    @patch('insights.api.ml.tax.frappe.db.sql')
    def test_get_tax_detail_tax_invoices(self, mock_sql, mock_has_permission):
        """Test tax_invoices drill-down returns invoices with tax rows"""
        from insights.api.ml.tax import get_tax_detail

        mock_sql.side_effect = [
            [
                {
                    'name': 'SINV-007',
                    'customer': 'Customer G',
                    'posting_date': '2024-01-15',
                    'grand_total': 1180.0,
                    'total_taxes_and_charges': 180.0
                }
            ],
            [(1,)]
        ]

        result = get_tax_detail('tax_invoices', '{"company": "Test Company"}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['total_taxes_and_charges'], 180.0)
        self.assertEqual(result['data']['total'], 1)
        calls = [c[0] for c in mock_sql.call_args_list]
        self.assertTrue(any('Test Company' in str(c) for c in calls))

    def test_get_tax_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.tax import get_tax_detail

        with self.assertRaises(frappe.ValidationError):
            get_tax_detail('unknown_metric', '{}')


class TestStrategicFinanceAPIDrillDown(FrappeTestCase):
    """Test suite for strategic finance drill-down API endpoints"""

    @patch('insights.api.ml.strategic_finance.frappe.has_permission')
    @patch('insights.api.ml.strategic_finance.frappe.get_list')
    @patch('insights.api.ml.strategic_finance.frappe.db.count')
    def test_get_strategic_detail_revenue_invoices(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test revenue_invoices drill-down returns submitted sales invoices"""
        from insights.api.ml.strategic_finance import get_strategic_detail

        mock_get_list.return_value = [
            {
                'name': 'SINV-008',
                'customer': 'Customer H',
                'posting_date': '2024-01-15',
                'grand_total': 5000.0,
                'outstanding_amount': 0.0
            }
        ]
        mock_db_count.return_value = 1

        result = get_strategic_detail('revenue_invoices', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['rows'][0]['name'], 'SINV-008')
        self.assertEqual(result['data']['columns'][0]['options'], 'Sales Invoice')

    @patch('insights.api.ml.strategic_finance.frappe.has_permission')
    @patch('insights.api.ml.strategic_finance.frappe.get_list')
    @patch('insights.api.ml.strategic_finance.frappe.db.count')
    def test_get_strategic_detail_expense_entries(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test expense_entries drill-down returns submitted purchase invoices"""
        from insights.api.ml.strategic_finance import get_strategic_detail

        mock_get_list.return_value = [
            {
                'name': 'PINV-003',
                'supplier': 'Supplier E',
                'posting_date': '2024-01-10',
                'grand_total': 2000.0,
                'outstanding_amount': 500.0
            }
        ]
        mock_db_count.return_value = 1

        result = get_strategic_detail('expense_entries', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['columns'][0]['options'], 'Purchase Invoice')

    def test_get_strategic_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.strategic_finance import get_strategic_detail

        with self.assertRaises(frappe.ValidationError):
            get_strategic_detail('unknown_metric', '{}')


class TestESGAPIDrillDown(FrappeTestCase):
    """Test suite for ESG drill-down API endpoints"""

    @patch('insights.api.ml.esg.frappe.has_permission')
    @patch('insights.api.ml.esg.frappe.get_list')
    @patch('insights.api.ml.esg.frappe.db.count')
    def test_get_esg_detail_employees_diversity(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test employees_diversity drill-down returns active employees"""
        from insights.api.ml.esg import get_esg_detail

        mock_get_list.return_value = [
            {
                'name': 'EMP-005',
                'employee_name': 'Diverse Employee',
                'department': 'HR',
                'gender': 'Female',
                'date_of_joining': '2023-01-01'
            }
        ]
        mock_db_count.return_value = 1

        result = get_esg_detail('employees_diversity', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['columns'][3]['fieldname'], 'gender')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters'], {'status': 'Active'})

    @patch('insights.api.ml.esg.frappe.has_permission')
    @patch('insights.api.ml.esg.frappe.get_list')
    @patch('insights.api.ml.esg.frappe.db.count')
    def test_get_esg_detail_supplier_count(self, mock_db_count, mock_get_list, mock_has_permission):
        """Test supplier_count drill-down returns active suppliers"""
        from insights.api.ml.esg import get_esg_detail

        mock_get_list.return_value = [
            {
                'name': 'SUP-001',
                'supplier_name': 'Supplier A',
                'supplier_group': 'Raw Material',
                'supplier_type': 'Company',
                'country': 'Kenya'
            }
        ]
        mock_db_count.return_value = 1

        result = get_esg_detail('supplier_count', '{}')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['columns'][0]['options'], 'Supplier')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters'], {'disabled': 0})

    def test_get_esg_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.esg import get_esg_detail

        with self.assertRaises(frappe.ValidationError):
            get_esg_detail('unknown_metric', '{}')


if __name__ == '__main__':
    unittest.main()