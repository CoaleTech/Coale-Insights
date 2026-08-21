# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
The two coercions the Price Intelligence payload cannot get wrong.

Both are money-correctness paths, and both were real defects caught by driving
the dashboard rather than by reading the code:

1. A left join with no match yields ``NaN``, not ``None``. ``NaN`` is not valid
   JSON, and it is not ``null`` to the frontend either, so a missing stock
   valuation rendered as "NaN" instead of a dash.
2. Coercing that missing valuation to ``0`` reported a **100% margin on an
   unknown cost** - the single most misleading number this dashboard could
   show, and indistinguishable on screen from a genuinely costless sale.

No fixtures and no site data: these are pure transforms over a DataFrame, so
the test states the contract directly.
"""

from decimal import Decimal

import pandas as pd
from frappe.tests.utils import FrappeTestCase

from insights.ml.price_intelligence import _margin_columns, _to_records


class TestToRecords(FrappeTestCase):
    def test_decimal_becomes_float(self):
        """MariaDB DECIMAL aggregates arrive as `decimal.Decimal`, which the
        JSON layer either stringifies or rejects."""
        rows = _to_records(pd.DataFrame([{"revenue": Decimal("105.85")}]))
        self.assertIsInstance(rows[0]["revenue"], float)
        self.assertEqual(rows[0]["revenue"], 105.85)

    def test_nan_becomes_none(self):
        """An unmatched left join must read as "no data", not as NaN."""
        rows = _to_records(pd.DataFrame([{"valuation_rate": float("nan")}]))
        self.assertIsNone(rows[0]["valuation_rate"])

    def test_infinity_becomes_none(self):
        """A division by a zero qty is also not a number anyone can quote."""
        rows = _to_records(pd.DataFrame([{"rate": float("inf")}]))
        self.assertIsNone(rows[0]["rate"])

    def test_real_values_survive(self):
        rows = _to_records(pd.DataFrame([{"qty": 0, "name": "2-EH", "ok": True}]))
        self.assertEqual(rows[0], {"qty": 0, "name": "2-EH", "ok": True})


class TestMarginColumns(FrappeTestCase):
    def test_unknown_valuation_yields_unknown_margin(self):
        """The defect this whole module guards: no cost means no margin, not a
        100% one."""
        row = {"revenue": 12200550.0, "qty": 348100.0, "valuation_rate": None}
        _margin_columns(row)
        self.assertEqual(row["avg_rate"], 35.05)
        self.assertIsNone(row["margin_per_unit"])
        self.assertIsNone(row["margin_pct"])

    def test_negative_margin_is_reported_signed(self):
        """Sold under stock cost - the strongest single signal on the page."""
        row = {"revenue": 11550175.0, "qty": 130025.0, "valuation_rate": 105.85}
        _margin_columns(row)
        self.assertEqual(row["avg_rate"], 88.83)
        self.assertEqual(row["margin_per_unit"], -17.02)
        self.assertEqual(row["margin_pct"], -19.2)

    def test_zero_qty_never_divides(self):
        row = {"revenue": 500.0, "qty": 0, "valuation_rate": 10.0}
        _margin_columns(row)
        self.assertEqual(row["avg_rate"], 0.0)
        self.assertIsNone(row["margin_pct"])
