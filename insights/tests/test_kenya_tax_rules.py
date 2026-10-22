# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import unittest
from datetime import date

from insights.ml.kenya_tax_intelligence import rules as r


class TestKenyaTaxRules(unittest.TestCase):
    def test_nssf_year4(self):
        on = date(2026, 10, 1)
        self.assertEqual(r.nssf(100_000, on), {"tier1": 540.0, "tier2": 5_460.0, "employee": 6_000.0})
        self.assertEqual(r.nssf(500_000, on)["employee"], 6_480.0)
        self.assertEqual(r.nssf(5_000, on)["employee"], 300.0)  # below LEL: 6% of gross, no tier II

    def test_nssf_year_selected_by_date(self):
        self.assertEqual(r.nssf_limits(date(2024, 1, 31)), (6_000.0, 18_000.0))
        self.assertEqual(r.nssf_limits(date(2025, 2, 1)), (8_000.0, 72_000.0))

    def test_shif_floor(self):
        self.assertEqual(r.shif(100_000), 2_750.0)
        self.assertEqual(r.shif(5_000), 300.0)
        self.assertEqual(r.shif(0), 0.0)

    def test_paye_bands(self):
        self.assertEqual(r.paye_before_relief(24_000), 2_400.0)
        self.assertEqual(r.paye_before_relief(32_333), 2_400.0 + 8_333 * 0.25)
        self.assertEqual(r.paye_before_relief(600_000), 2_400 + 2_083.25 + (500_000 - 32_333) * 0.30 + 100_000 * 0.325)

    def test_paye_full(self):
        p = r.paye(100_000, date(2026, 10, 1))
        self.assertEqual(p["taxable"], 100_000 - 6_000 - 2_750 - 1_500)
        self.assertEqual(p["paye"], round(r.paye_before_relief(p["taxable"]) - 2_400, 2))
        # relief never drives PAYE negative
        self.assertEqual(r.paye(20_000, date(2026, 10, 1))["paye"], 0.0)

    def test_due_dates_2026_oct(self):
        d = r.monthly_due_dates(date(2026, 10, 31))
        self.assertEqual(d["paye"], date(2026, 11, 9))
        self.assertEqual(d["vat"], date(2026, 11, 20))
        self.assertEqual(d["ahl"], date(2026, 11, 12))  # 9th working day after 31 Oct (Sat)
        # nominal date kept even when it falls on a weekend (20 Dec 2026 is a Sunday)
        self.assertEqual(r.monthly_due_dates(date(2026, 11, 30))["vat"], date(2026, 12, 20))

    def test_working_days_and_wht(self):
        self.assertEqual(r.wht_due_date(date(2026, 10, 22)), date(2026, 10, 29))
        self.assertEqual(r.wht_due_date(date(2026, 10, 22), [date(2026, 10, 27)]), date(2026, 10, 30))
        self.assertEqual(r.working_days_between(date(2026, 10, 22), date(2026, 10, 29)), 5)

    def test_cit_dates(self):
        self.assertEqual(r.instalment_dates(date(2026, 1, 1)), [date(2026, 4, 20), date(2026, 6, 20), date(2026, 9, 20), date(2026, 12, 20)])
        self.assertEqual(r.cit_balance_due(date(2026, 12, 31)), date(2027, 4, 30))
        self.assertEqual(r.cit_return_due(date(2026, 12, 31)), date(2027, 6, 30))

    def test_late_payment_interest_cap(self):
        c = r.late_payment_cost(1000, date(2026, 1, 20), date(2026, 3, 25))
        self.assertEqual((c["penalty"], c["interest"]), (50.0, 30.0))  # 3 part-months
        self.assertEqual(r.late_payment_cost(1000, date(2010, 1, 20), date(2026, 3, 25))["interest"], 1000.0)
        self.assertEqual(r.late_payment_cost(1000, date(2026, 5, 1), date(2026, 3, 25))["total"], 0.0)

    def test_customs_and_wht(self):
        t = r.landed_import_taxes(1_000_000, 250_000)
        self.assertEqual((t["idf"], t["rdl"], t["vat"]), (35_000.0, 20_000.0, 200_000.0))
        self.assertEqual(r.wht_rate("management_professional", True), 0.05)
        self.assertEqual(r.wht_rate("management_professional", False), 0.20)
        self.assertIsNone(r.wht_rate("nonsense", True))
        self.assertEqual(r.classify_wht_text("Consultancy fees"), "management_professional")
        self.assertEqual(r.classify_wht_text("Office rent"), "rent")

    def test_loss_and_instalment(self):
        self.assertEqual(r.loss_lapse_date(2023), date(2028, 12, 31))
        self.assertEqual(r.instalment_required(1_000, 1_200), 1_100.0)
        self.assertEqual(r.instalment_required(None, 900), 900)
        self.assertIsNone(r.instalment_required(None, None))
