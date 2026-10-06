# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Financial intelligence reconciles with the ledger.

Pure tests pin the window/decimal helpers; the DB tests check the payload
invariants (no future periods, breakdowns tie to YTD, floats only) against the
live site and skip when it has no postings.
"""

import unittest
from datetime import date
from decimal import Decimal

import pandas as pd
from frappe.tests import IntegrationTestCase

from insights.ml import financial_intelligence as fi


def _bare(date_filter: str = "12m") -> fi.FinancialIntelligence:
    """Instance without the company/fiscal-year lookups of __init__."""
    obj = fi.FinancialIntelligence.__new__(fi.FinancialIntelligence)
    obj.date_filter = date_filter
    return obj


class _Expr:
    def __init__(self, df):
        self._df = df

    def execute(self):
        return self._df


class TestWindowAndRows(unittest.TestCase):
    def test_rows_decimal_becomes_float(self):
        df = pd.DataFrame({"amount": [Decimal("12.50")], "name": ["x"]})
        rows = _bare()._rows(_Expr(df))
        self.assertIsInstance(rows[0]["amount"], float)
        self.assertEqual(rows[0]["amount"], 12.5)
        self.assertEqual(rows[0]["name"], "x")

    def test_window_starts_on_first_of_month_and_ends_today(self):
        start, end = _bare("12m")._window()
        self.assertTrue(start.endswith("-01"))
        self.assertEqual(end, fi._today())
        self.assertEqual(start, fi._months_ago(12))

    def test_window_custom_range_clamped_to_today(self):
        start, end = _bare("custom:2025-05-17:2999-01-01")._window()
        self.assertEqual((start, end), ("2025-05-01", fi._today()))
        self.assertEqual(_bare("custom:2025-05-17:2025-08-02")._window(), ("2025-05-01", "2025-08-02"))

    def test_window_all_is_unbounded_below(self):
        self.assertEqual(_bare("all")._window()[0], "1900-01-01")


class TestPayloadInvariants(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fin = fi.FinancialIntelligence()
        if not cls.fin.company:
            raise unittest.SkipTest("no company")
        cls.ov = cls.fin._calculate_financial_overview()
        if not cls.ov["ytd_revenue"]:
            raise unittest.SkipTest("no postings this fiscal year")

    def test_no_future_periods(self):
        this_month = date.today().isoformat()[:7]
        self.assertTrue(all(r["period"] <= this_month for r in self.ov["monthly_trend"]))

    def test_breakdowns_tie_to_ytd(self):
        for rows, total in (
            (self.ov["revenue_breakdown"], self.ov["ytd_revenue"]),
            (self.ov["expense_breakdown"], self.ov["ytd_expenses"]),
        ):
            if len(rows) < 10:  # top-10 only reconciles when nothing was cut off
                self.assertAlmostEqual(sum(r["amount"] for r in rows), total, places=1)
            self.assertTrue(all(r["pct"] <= 100 for r in rows))

    def test_cash_flow_runway_is_null_when_not_burning(self):
        cf = self.fin._calculate_cash_flow()
        if cf["net_burn_rate"] <= 0:
            self.assertIsNone(cf["runway_months"])
        else:
            self.assertGreater(cf["runway_months"], 0)

    def test_no_decimal_or_numeric_string_reaches_the_ui(self):
        # `reference` (bank receipt number) and `fiscal_year` ("2627") are identifiers.
        identifiers = {"reference", "fiscal_year"}

        def walk(o, key=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield from walk(v, k)
            elif isinstance(o, list):
                for v in o:
                    yield from walk(v, key)
            elif isinstance(o, Decimal):
                yield key
            elif isinstance(o, str) and key not in identifiers:
                try:
                    float(o)
                except ValueError:
                    return
                yield key

        payload = self.fin.train()
        self.assertEqual(list(walk(payload)), [])
        self.assertEqual(payload["date_filter"], "12m")
