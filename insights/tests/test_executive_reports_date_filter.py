# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Regression test for the Executive Reports sales-intelligence date-filter bug.

`_collect_daily_intelligence_data` / `_collect_intelligence_data_for_period`
called `sales_intelligence.get_sales_intelligence()` with no `date_filter` at
all, so every cadence (daily/weekly/monthly) silently got the function's own
default (trailing 12 months) instead of the MTD/QTD/YTD window the report
claims to cover -- "Daily revenue" and "Period revenue" were both actually
12-month revenue, identical to the monthly report's YTD figure.
`_sales_date_filter` maps the executive-report period tokens to a
`get_sales_intelligence`-understood `date_filter` (custom:start:end, or its
"ytd" preset); this locks that mapping down and catches a regression back to
the un-scoped call.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from insights.reports.executive_reports import ExecutiveReports


class TestExecutiveReportsSalesDateFilter(FrappeTestCase):
    def test_period_tokens_map_to_distinct_windows(self):
        er = ExecutiveReports()
        mtd = er._sales_date_filter("MTD")
        qtd = er._sales_date_filter("QTD")
        ytd = er._sales_date_filter("YTD")

        self.assertEqual(mtd, f"custom:{er.current_month_start}:{er.today}")
        self.assertEqual(qtd, f"custom:{er.current_quarter_start}:{er.today}")
        self.assertEqual(ytd, "ytd")
        # The whole point of the fix: three different tokens must not collapse
        # into the same window.
        self.assertEqual(len({mtd, qtd, ytd}), 3)

    def test_daily_and_period_collectors_pass_a_date_filter(self):
        """The un-scoped `get_sales_intelligence()` call is the exact
        regression this guards: assert every call site now passes
        date_filter explicitly."""
        with patch(
            "insights.ml.sales_intelligence.get_sales_intelligence",
            return_value={"summary": {}},
        ) as mock_sales:
            er = ExecutiveReports()
            er._collect_daily_intelligence_data()
            er._collect_intelligence_data_for_period("QTD")

        self.assertEqual(mock_sales.call_count, 2)
        for call in mock_sales.call_args_list:
            self.assertIn("date_filter", call.kwargs)
            self.assertTrue(call.kwargs["date_filter"])
