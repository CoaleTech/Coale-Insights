# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch


class TestMLDomainIntelligence(FrappeTestCase):
    """End-to-end smoke tests for the Ibis-computed intelligence domains.

    This used to be five classes (``TestMLModelBase``, ``TestCustomerIntelligence``,
    ``TestSalesIntelligence``, ``TestInventoryIntelligence``, ``TestFinancialIntelligence``)
    that patched private methods (``_get_sales_data``, ``_calculate_inventory_metrics``, ...)
    on per-domain ``BaseMLModel`` subclasses. ``BaseMLModel`` and every subclass were removed
    in the pure-Ibis rewrite (see ``insights/ml/base.py``): each domain now computes fresh
    via Ibis on every request instead of training and caching a pandas model, so those
    classes and methods no longer exist to mock. These call the real top-level entry point
    for each domain against this site's data and assert on the response envelope every
    dashboard endpoint depends on.
    """

    def setUp(self):
        """Guard against a real cross-test hazard, not a production one.

        ``TestAPIDefensiveProgramming`` patches ``sys.modules`` for
        ``pandas``/``sklearn``/``prophet`` to test graceful degradation; on
        exit that can leave the interpreter's sqlglot dialect registry in a
        different state than when an *earlier* test cached an ibis
        connection on ``frappe.local`` (verified: the cached connection's
        compiler dialect class stops matching the live registry). Production
        never sees this -- every request/job gets a fresh ``frappe.local``
        via ``frappe.init()``/``frappe.destroy()`` -- but ``bench run-tests``
        runs every test in one process with no such reset between them.
        Clearing the cache here forces each test in this class to build its
        own connection against whatever dialect state is currently live.
        """
        frappe.local.insights_ml_ibis_conn = None

    def test_ensure_dependencies_reports_versions(self):
        """`model_health` reads this to show what's importable on this site."""
        from insights.ml.base import ensure_dependencies

        result = ensure_dependencies()

        self.assertIsInstance(result, dict)
        for label in ("pandas", "numpy", "scikit-learn", "statsmodels", "prophet"):
            self.assertIn(label, result)

    def test_compute_customer_intelligence(self):
        """CLV/RFM/churn/health rollup (insights/ml/customer.py)."""
        from insights.ml.customer import compute_customer_intelligence

        result = compute_customer_intelligence()

        self.assertEqual(result.get("status"), "success")
        self.assertIn("summary", result)
        self.assertIn("customers", result)

    def test_run_sales_intelligence(self):
        """Revenue/margins/forecast rollup (insights/ml/sales_intelligence.py)."""
        from insights.ml.sales_intelligence import run_sales_intelligence

        result = run_sales_intelligence()

        self.assertEqual(result.get("status"), "success")
        self.assertIn("revenue_metrics", result)
        self.assertIn("forecasts", result)

    def test_run_inventory_intelligence(self):
        """Stock/turnover/dead-stock rollup (insights/ml/inventory_intelligence.py)."""
        from insights.ml.inventory_intelligence import run_inventory_intelligence

        result = run_inventory_intelligence()

        self.assertEqual(result.get("status"), "success")
        self.assertIn("stock_overview", result)
        self.assertIn("turnover_analysis", result)

    def test_run_financial_intelligence(self):
        """P&L/cash-flow/receivables rollup (insights/ml/financial_intelligence.py)."""
        from insights.ml.financial_intelligence import run_financial_intelligence

        result = run_financial_intelligence()

        self.assertEqual(result.get("status"), "success")
        self.assertIn("overview", result)
        self.assertIn("cash_flow", result)


# ``TestAPIDefensiveProgramming`` (sklearn/prophet/pandas-unavailable fallback
# tests) was removed 2026-08-11 alongside ``BaseMLModel``. It tested optional-
# dependency fallback chains that no longer exist: ``compute_rfm_segmentation``
# and the synchronous ``sales_forecast`` path are pure Ibis + stdlib now (no
# sklearn/prophet import in either), and pandas is a hard, non-optional
# transitive dependency of ibis's own MySQL backend (every ``.execute()`` call
# does ``import pandas`` inside ``ibis/backends/mysql/__init__.py``, with no
# fallback) -- there is no app-level "gracefully degrade without pandas" path
# left to test. Simulating absence via ``mock.patch.dict('sys.modules', {lib:
# None})`` also proved actively harmful on this interpreter: it corrupted
# process-wide numpy/pandas state (``ImportError: numpy: cannot load module
# more than once per process``), breaking every later test in the same
# ``bench run-tests`` process that needed a real Ibis ``.execute()`` --
# confirmed by isolating each of the three tests alone in a fresh console.
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


        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['columns'][0]['fieldname'], 'name')
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


        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['warehouse'], 'Stores - TC')
        mock_has_permission.assert_called_with('Bin', throw=True)
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters'], {'actual_qty': ('>', 0), 'warehouse': 'Stores - TC'})

    @patch('insights.api.ml.inventory.frappe.has_permission')
    def test_get_inventory_detail_low_stock_items(self, mock_has_permission):
        """Test low_stock_items drill-down joins Bin with Item Reorder"""
        from insights.api.ml.inventory import get_inventory_detail

        result = get_inventory_detail('low_stock_items', '{}')

        self.assertEqual(sorted(result.keys()), ['columns', 'rows', 'total'])
        self.assertIsInstance(result['rows'], list)
        self.assertIsInstance(result['total'], int)
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


        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['columns'][0]['fieldname'], 'name')
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


        self.assertEqual(result['rows'][0]['name'], 'SO-001')
        self.assertEqual(result['columns'][0]['options'], 'Sales Order')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['company'], 'Test Company')
        self.assertEqual(kwargs['filters']['status'], ('not in', ['Completed', 'Cancelled', 'Closed']))

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


        self.assertEqual(result['rows'][0]['territory'], 'Mombasa')
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


        self.assertEqual(result['rows'][0]['outstanding_amount'], 1500.0)
        self.assertEqual(result['columns'][0]['options'], 'Sales Invoice')
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


        self.assertEqual(result['rows'][0]['name'], 'SINV-004')
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


        self.assertEqual(result['columns'][0]['options'], 'Purchase Invoice')
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


        self.assertEqual(result['rows'][0]['account_type'], 'Cash')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['account_type'], ('in', ['Cash', 'Bank']))
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


        self.assertEqual(result['rows'][0]['name'], 'CUST-001')
        self.assertEqual(result['columns'][0]['options'], 'Customer')
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


        self.assertEqual(result['rows'][0]['customer'], 'CUST-001')
        self.assertEqual(result['columns'][0]['options'], 'Sales Invoice')
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


        self.assertEqual(result['rows'][0]['name'], 'CUST-002')
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


        self.assertEqual(result['rows'][0]['name'], 'PO-001')
        self.assertEqual(result['columns'][0]['options'], 'Purchase Order')
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


        self.assertIn('per_received', [c['fieldname'] for c in result['columns']])
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['status'], ('not in', ['Completed', 'Cancelled', 'Closed']))

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


        self.assertEqual(result['rows'][0]['supplier'], 'Supplier C')
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


        self.assertEqual(result['rows'][0]['name'], 'EMP-001')
        self.assertEqual(result['columns'][0]['options'], 'Employee')

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


        self.assertEqual(result['rows'][0]['department'], 'Engineering')

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


        self.assertIn('Contract', result['rows'][0].values())

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


        self.assertEqual(result['rows'][0]['name'], 'SINV-005')
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


        self.assertEqual(result['columns'][0]['options'], 'Purchase Invoice')

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


        self.assertEqual(result['rows'][0]['grand_total'], 8000.0)

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


        self.assertEqual(result['columns'][0]['options'], 'Employee')

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


        self.assertEqual(result['columns'][0]['options'], 'Work Order')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['status'], ('not in', ['Completed', 'Cancelled', 'Stopped']))

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


        self.assertEqual(result['rows'][0]['qty'], 50.0)
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


        self.assertEqual(result['columns'][0]['options'], 'Lead')
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


        self.assertEqual(result['columns'][0]['options'], 'Opportunity')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters']['status'], ('not in', ['Closed', 'Lost']))

    def test_get_crm_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.marketing import get_crm_detail

        with self.assertRaises(frappe.ValidationError):
            get_crm_detail('unknown_metric', '{}')


class TestTaxAPIDrillDown(FrappeTestCase):
    """Test suite for tax drill-down API endpoints"""

    @patch('insights.api.ml.tax.frappe.has_permission')
    @patch('insights.ml.india_tax_intelligence.model.IndiaTaxIntelligence')
    def test_get_tax_detail_tax_invoices(self, mock_intelligence, mock_has_permission):
        """Test tax_invoices drill-down returns invoices with tax rows"""
        from insights.api.ml.tax import get_tax_detail
        from unittest.mock import MagicMock, patch

        mock_intelligence.return_value._window.return_value = {
            'name': 'FY2024', 'start': '2024-04-01', 'end': '2025-03-31'
        }

        # Build a chainable mock query builder whose .run() returns the page
        # rows on the first call and the total count on the second.
        mock_query = MagicMock()
        mock_query.run.side_effect = [
            [
                {
                    'name': 'SINV-007',
                    'customer': 'Customer G',
                    'posting_date': '2024-01-15',
                    'grand_total': 1180.0,
                    'total_taxes_and_charges': 180.0
                }
            ],
            [{'total': 1}]
        ]
        for attr in ['select', 'where', 'orderby', 'limit', 'offset', 'inner_join', 'left_join', 'join', 'on', 'groupby', 'having']:
            getattr(mock_query, attr).return_value = mock_query

        # DocType fields must support comparison, arithmetic, and logical operators.
        class _FakeField:
            def __lt__(self, other): return self
            def __le__(self, other): return self
            def __gt__(self, other): return self
            def __ge__(self, other): return self
            def __eq__(self, other): return self
            def __ne__(self, other): return self
            def __add__(self, other): return self
            def __sub__(self, other): return self
            def __mul__(self, other): return self
            def __truediv__(self, other): return self
            def __and__(self, other): return self
            def __rand__(self, other): return self
            def __or__(self, other): return self
            def __ror__(self, other): return self
            def between(self, *args): return self
            def isin(self, *args): return self
            def notin(self, *args): return self
            def isnull(self): return self
        class _FakeDocType:
            def __getattr__(self, name): return _FakeField()
        mock_qb = MagicMock()
        mock_qb.from_.return_value = mock_query
        mock_qb.DocType.return_value = _FakeDocType()

        with patch('insights.api.ml.tax.frappe.qb', mock_qb):
            result = get_tax_detail('tax_invoices', '{"company": "Test Company"}')

        self.assertEqual(result['rows'][0]['total_taxes_and_charges'], 180.0)
        self.assertEqual(result['total'], 1)

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


        self.assertEqual(result['rows'][0]['name'], 'SINV-008')
        self.assertEqual(result['columns'][0]['options'], 'Sales Invoice')

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


        self.assertEqual(result['columns'][0]['options'], 'Purchase Invoice')

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


        self.assertEqual(result['columns'][3]['fieldname'], 'gender')
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


        self.assertEqual(result['columns'][0]['options'], 'Supplier')
        _, kwargs = mock_get_list.call_args
        self.assertEqual(kwargs['filters'], {'disabled': 0})

    def test_get_esg_detail_unknown_metric(self):
        """Test unknown metric raises ValidationError"""
        from insights.api.ml.esg import get_esg_detail

        with self.assertRaises(frappe.ValidationError):
            get_esg_detail('unknown_metric', '{}')


if __name__ == '__main__':
    unittest.main()