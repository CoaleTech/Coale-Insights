# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.tests.utils import FrappeTestCase
import time


class TestAPIIntegration(FrappeTestCase):
    """Integration tests for API endpoints"""

    @classmethod
    def setUpClass(cls):
        """Build the shared fixture once for the whole class.

        None of the test methods below mutate this data -- they only call
        read-oriented API endpoints and assert on the response shape -- so
        building it once per class instead of once per test is safe and
        much cheaper. ``FrappeTestCase.setUpClass`` registers an automatic
        ``frappe.db.rollback()`` via ``addClassCleanup`` that fires once
        every test in this class has run (see
        ``frappe.deprecation_dumpster.FrappeTestCase``); since nothing
        below ever calls ``frappe.db.commit()``, that single rollback
        undoes the whole fixture -- Company, Fiscal Year, Customers,
        Items, Sales Person, Sales Invoices -- in one shot. That replaces
        six repeats (one per test method) of ``Company.on_trash``, which
        cascades to Account/Cost Center/Budget/Party Account/Warehouse and
        contends with this dev site's live background workers/scheduler
        writing to the same globally-shared ``tabDefaultValue`` table.
        """
        super().setUpClass()
        cls.setup_test_data()

    @classmethod
    def setup_test_data(cls):
        """Create comprehensive test data"""
        # Create test company
        if not frappe.db.exists("Company", "Test Insights Co"):
            company = frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Insights Co",
                "default_currency": "USD",
                "country": "United States",
                "custom_lut_no": "TEST-LUT-001",
            })
            company.insert(ignore_permissions=True)
        # ``Company.on_update`` runs ``create_default_cost_center()`` (which
        # stamps "Main - {abbr}" onto ``Company.cost_center``) only when no
        # non-group Cost Center exists yet for this company. A stale Cost
        # Center can survive across test runs -- e.g. an earlier process
        # that was killed before ``setUpClass``'s automatic rollback could
        # fire, leaving this Company (and its Cost Center) committed --
        # leaving ``Company.cost_center`` NULL despite the Cost Center
        # existing. Query Cost Center directly instead -- it's the value
        # ``create_default_cost_center`` actually guarantees, and
        # self-heals regardless of whether ``on_update`` re-ran. Item rows
        # built via raw ``get_doc().insert()`` don't run the desk form's
        # cost-center default fetch, and some other default (this site's
        # real company's cost center) can otherwise leak in.
        cls.cost_center = frappe.db.get_value(
            "Cost Center", {"company": "Test Insights Co", "is_group": 0}, "name"
        )
        # ``create_default_cost_center`` also stamps this same "Main -
        # {abbr}" cost center onto ``Company.round_off_cost_center`` --
        # skipped by the same stale-Cost-Center guard above, and separately
        # required because ``AccountsController.make_precision_loss_gl_entry``
        # hardcodes ``voucher_type="Purchase Invoice"`` when looking up a
        # parent cost center override (a pre-existing core quirk that never
        # matches this Sales Invoice), so it always falls back to the
        # company-level value on submit. Stamp it directly so submission
        # doesn't depend on either mechanism actually having run.
        frappe.db.set_value("Company", "Test Insights Co", "round_off_cost_center", cls.cost_center)

        # Same ``on_update`` guard pattern as cost center above: a stale
        # Chart of Accounts surviving Company recreation leaves
        # ``Company.default_receivable_account`` NULL. Query the Receivable
        # account directly so Sales Invoice creation below can set
        # ``debit_to`` explicitly -- raw ``get_doc().insert()`` skips the
        # desk form's ``get_party_details``/``set_missing_values`` account
        # resolution, and without it ``debit_to`` stays unset and
        # ``validate_party_account_currency`` throws (None currency !=
        # USD).
        cls.debit_to = frappe.db.get_value(
            "Account",
            {"company": "Test Insights Co", "account_type": "Receivable", "is_group": 0},
            "name",
        )

        # Fiscal Year for the new company. This site's real Fiscal Year
        # records are scoped per-company via the ``Fiscal Year Company``
        # child table (``_get_fiscal_years`` only matches a FY that is either
        # unscoped or explicitly lists the company), so a brand-new company
        # has no coverage until one is created for it.
        if not frappe.db.exists("Fiscal Year", "Test Insights Co FY"):
            # Frappe requires an exact 1-year span
            # (``year_end_date == year_start_date + 1yr - 1day``); start
            # 30 days back to safely cover every posting date this fixture
            # writes (today down to today - 9 days).
            fy_start = frappe.utils.add_days(frappe.utils.today(), -30)
            fy_end = frappe.utils.add_days(frappe.utils.add_years(fy_start, 1), -1)
            fiscal_year = frappe.get_doc({
                "doctype": "Fiscal Year",
                "year": "Test Insights Co FY",
                "year_start_date": fy_start,
                "year_end_date": fy_end,
                "companies": [{"company": "Test Insights Co"}],
            })
            fiscal_year.insert(ignore_permissions=True)

        # Create test customers. Customer.name is NOT guaranteed to equal
        # customer_name -- this site's Selling Settings has
        # ``cust_master_name = "Naming Series"``, so the real primary key is
        # an autogenerated series value. Resolve/capture the real name for
        # every customer instead of assuming the two are identical.
        cls.customer_names = []
        for i in range(5):
            customer_name = f"Test Customer {i+1}"
            existing = frappe.db.get_value("Customer", {"customer_name": customer_name}, "name")
            if existing:
                cls.customer_names.append(existing)
            else:
                customer = frappe.get_doc({
                    "doctype": "Customer",
                    "customer_name": customer_name,
                    "customer_type": "Company"
                })
                customer.insert(ignore_permissions=True)
                cls.customer_names.append(customer.name)

        # Create test items
        for i in range(3):
            item_code = f"TEST-ITEM-{i+1:03d}"
            if not frappe.db.exists("Item", item_code):
                item = frappe.get_doc({
                    "doctype": "Item",
                    "item_code": item_code,
                    "item_name": f"Test Item {i+1}",
                    "item_group": "Products",
                    "stock_uom": "Nos",
                    "gst_hsn_code": "38089349",
                })
                item.insert(ignore_permissions=True)

        # Create a sales person for the mandatory ``sales_team`` row below.
        # This site has a Property Setter making Sales Invoice's
        # ``sales_team`` (and ``vehicle_no``) mandatory for every company;
        # a dedicated test fixture avoids depending on this site's real
        # sales staff.
        if not frappe.db.exists("Sales Person", "Test Sales Person"):
            sales_person = frappe.get_doc({
                "doctype": "Sales Person",
                "sales_person_name": "Test Sales Person",
            })
            sales_person.insert(ignore_permissions=True)

        # Create sample sales invoices
        for i in range(10):
            si = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": cls.customer_names[i % 5],
                "company": "Test Insights Co",
                # Explicit: this site has a Property Setter defaulting the
                # Sales Invoice ``cost_center`` *field itself* to
                # "Main - JKM" (this site's real company). Frappe applies
                # DocField defaults for any key missing from a raw
                # ``get_doc({...})`` dict, so every fresh Sales Invoice
                # otherwise gets that cross-company default regardless of
                # ``cls.company`` -- caught by
                # ``validate_company_in_accounting_dimension`` before the
                # item-level ``cost_center`` below is ever reached.
                "cost_center": cls.cost_center,
                # Explicit: raw ``get_doc().insert()`` skips the desk form's
                # ``get_party_details`` currency fetch, so this can otherwise
                # resolve to the site's real default (INR) instead of this
                # test company's own USD.
                "currency": "USD",
                # Explicit: raw insert skips the desk form's account
                # resolution too, leaving ``debit_to`` unset -- which fails
                # ``validate_party_account_currency`` (None currency !=
                # USD).
                "debit_to": cls.debit_to,
                # Explicit: this site's Property Setters also make these
                # two fields mandatory on every Sales Invoice.
                "vehicle_no": "TEST-VEH-01",
                "sales_team": [{"sales_person": "Test Sales Person", "allocated_percentage": 100}],
                "posting_date": frappe.utils.add_days(frappe.utils.today(), -i),
                "items": [{
                    "item_code": f"TEST-ITEM-{((i % 3) + 1):03d}",
                    "cost_center": cls.cost_center,
                    "qty": (i % 5) + 1,
                    "rate": 100 + (i * 10),
                    "amount": ((i % 5) + 1) * (100 + (i * 10))
                }]
            })
            si.insert(ignore_permissions=True)
            si.submit()

    def test_customer_intelligence_api_integration(self):
        """Customer intelligence API integration: real endpoint, real Ibis
        compute, against this class's own fixture data (no ``CustomerIntelligence``
        class exists to mock -- ``insights.ml.customer.compute_customer_intelligence``
        is a plain function, computed fresh on every call)."""
        from insights.api.ml.customer import customer_intelligence

        result = customer_intelligence(company="Test Insights Co")

        self.assertEqual(result["status"], "success")
        self.assertIn("data", result)
        self.assertIn("summary", result["data"])
        self.assertIn("customers", result["data"])

    def test_sales_intelligence_api_integration(self):
        """Sales intelligence API integration: real endpoint, real Ibis
        compute (no ``SalesIntelligence`` class exists to mock --
        ``insights.ml.sales_intelligence.run_sales_intelligence`` is a plain
        function, computed fresh on every call)."""
        from insights.api.ml.sales import sales_intelligence

        result = sales_intelligence()

        self.assertEqual(result["status"], "success")
        self.assertIn("data", result)
        self.assertIn("summary", result["data"])

    def test_inventory_intelligence_api_integration(self):
        """Inventory intelligence API integration: real endpoint, real Ibis
        compute (``InventoryIntelligence.train()`` still exists but is no
        longer cache-backed -- there is nothing left to mock, it just runs)."""
        from insights.api.ml.inventory import inventory_intelligence

        result = inventory_intelligence()

        self.assertEqual(result["status"], "success")
        self.assertIn("data", result)
        self.assertIn("stock_overview", result["data"])

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

    # ``test_caching_performance`` (mocked ``BaseMLModel.get_cache``/``set_cache``)
    # was removed 2026-08-11 alongside ``BaseMLModel`` itself. Every ML endpoint
    # now computes fresh from Ibis on each call -- see ``sales_intelligence``'s
    # own docstring: "every call computes fresh (no cache, no fork)". There is
    # no cache left whose performance benefit this test could demonstrate.


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

    # ``test_sql_injection_prevention`` (``get_date_filter_sql`` with
    # attacker-controlled ``date_column``/``alias`` strings) was removed
    # 2026-08-11. ``get_date_filter_sql`` -- which built a raw SQL fragment by
    # string-formatting a column name and table alias into ``BETWEEN`` -- no
    # longer exists. Its replacement, ``parse_date_filter``, takes only a
    # ``date_filter`` string and returns ``(start_date, end_date)`` as Python
    # ``datetime`` objects; every call site binds them through Ibis
    # (``table.filter(table.posting_date.between(start, end))``), which
    # compiles to a parameterized query. There is no longer a code path that
    # interpolates a caller-supplied identifier into SQL text, so the
    # injection this test guarded against is structurally impossible now,
    # not just tested-for.

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