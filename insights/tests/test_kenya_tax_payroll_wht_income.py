# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Pure-logic checks for the Kenya payroll, withholding and income-tax sections (no site needed)."""

import unittest
from datetime import date

from insights.ml.kenya_tax_intelligence import income, payroll, rules, wht


def _slip(emp, gross, on, **kw):
    row = {"slip": f"SAL-{emp}", "employee": emp, "employee_name": emp, "gross": gross, "paye": 0.0, "nssf": 0.0, "shif": 0.0,
           "ahl": 0.0, "pension": 0.0, "mortgage": 0.0, "nonres": False, "pin": "A001"}
    row.update(kw)
    return payroll.enrich(row, on)


class TestPayroll(unittest.TestCase):
    on = date(2026, 10, 31)

    def test_residency_polarity(self):
        self.assertTrue(payroll.is_non_resident("custom_non_resident", "1"))
        self.assertFalse(payroll.is_non_resident("custom_non_resident", 0))
        self.assertTrue(payroll.is_non_resident("custom_is_resident", 0))
        self.assertFalse(payroll.is_non_resident("custom_is_resident", "Yes"))
        self.assertTrue(payroll.is_non_resident("custom_residency", "Non-Resident"))
        self.assertIsNone(payroll.is_non_resident("custom_residency", ""))

    def test_band_headcount(self):
        bands = payroll.band_headcount([10_000, 24_000, 30_000, 100_000, 600_000, 900_000])
        self.assertEqual([b["headcount"] for b in bands], [2, 1, 1, 1, 1])
        self.assertEqual(bands[0]["rate"], 10.0)

    def test_exceptions(self):
        ok = _slip("OK", 100_000, self.on, nssf=6_000.0, shif=2_750.0, ahl=1_500.0)
        bad_nssf = _slip("NSSF", 100_000, self.on, nssf=6_480.0, shif=2_750.0, ahl=1_500.0, pin="")
        relief = _slip("NR", 100_000, self.on, nssf=6_000.0, shif=2_750.0, ahl=1_500.0, nonres=True)
        relief["paye"] = relief["exp"]["paye"] - 2_400.0  # relief wrongly applied
        found = payroll.find_exceptions([ok, bad_nssf, relief], {"OK": 10_000.0}, {"paye", "nssf", "shif", "ahl"}, True, True)
        self.assertEqual([r["employee"] for r in found["payroll_nssf_mismatch"]], ["NSSF"])
        self.assertEqual(found["payroll_nssf_mismatch"][0]["difference"], 480.0)
        self.assertEqual([r["employee"] for r in found["payroll_relief_nonresident"]], ["NR"])
        self.assertEqual(found["payroll_relief_nonresident"][0]["difference"], 2_400.0)
        self.assertEqual([r["employee"] for r in found["payroll_missing_pin"]], ["NSSF"])
        self.assertNotIn("payroll_shif_mismatch", found)
        # OK's PAYE is 0 on the slip against 10,000 last month: moved more than 5%
        self.assertEqual([r["employee"] for r in found["payroll_paye_movement"]], ["OK"])

    def test_remit_chip(self):
        due, today = date(2026, 11, 9), date(2026, 10, 22)
        self.assertEqual(payroll.remit_chip(due, today, 100.0, 100.0)["label"], "Paid")
        self.assertEqual(payroll.remit_chip(due, today, 100.0, 40.0)["label"], "Part-paid")
        self.assertEqual(payroll.remit_chip(due, today, 100.0, 0.0)["label"], "Due in 18 d")
        self.assertEqual(payroll.remit_chip(date(2026, 10, 9), today, 100.0, 0.0)["label"], "Overdue 13 d")
        self.assertEqual(payroll.remit_chip(date(2026, 10, 9), today, 100.0, None)["tone"], "mut")

    def test_nssf_year(self):
        self.assertEqual(payroll.nssf_year(date(2026, 10, 1)), 4)
        self.assertEqual(payroll.nssf_year(date(2023, 2, 1)), 1)


class TestWht(unittest.TestCase):
    def test_fifo(self):
        w = [(date(2026, 10, 12), "C", 62.0), (date(2026, 10, 8), "A", 148.0), (date(2026, 10, 9), "B", 96.0)]
        self.assertEqual(wht.fifo_outstanding(w, 200.0), [(date(2026, 10, 9), "B", 44.0), (date(2026, 10, 12), "C", 62.0)])
        self.assertEqual(wht.fifo_outstanding(w, 1_000.0), [])
        self.assertEqual(len(wht.fifo_outstanding(w, 0.0)), 3)

    def test_rate_check(self):
        self.assertEqual(wht.rate_check("management_professional", False, 100_000, 0.0), (5.0, 0.0))
        self.assertIsNone(wht.rate_check("management_professional", False, 100_000, 5_000.0))
        self.assertEqual(wht.rate_check("management_professional", True, 100_000, 5_000.0), (20.0, 5.0))  # non-resident at resident rate
        self.assertIsNone(wht.rate_check("management_professional", True, 100_000, 20_000.0))
        self.assertIsNone(wht.rate_check("unknown_kind", False, 100_000, 0.0))
        self.assertIsNone(wht.rate_check("rent", False, 0, 0.0))

    def test_residency_and_kind(self):
        self.assertFalse(wht.is_non_resident_country("Kenya"))
        self.assertFalse(wht.is_non_resident_country(""))
        self.assertTrue(wht.is_non_resident_country("United Kingdom"))
        items = [
            {"item_name": "Audit fees", "expense_account": "Professional Fees - X", "base_net_amount": 400.0},
            {"item_name": "Stationery", "expense_account": "Office - X", "base_net_amount": 900.0},
            {"item_name": "Legal advice", "expense_account": "", "base_net_amount": 100.0},
        ]
        self.assertEqual(wht.invoice_kind(items), ("management_professional", 500.0))
        self.assertIsNone(wht.invoice_kind([items[1]]))


class TestIncome(unittest.TestCase):
    def test_loss_ledger(self):
        # 2021 loss 100 usable through 2026; 2022 profit 30 absorbs 30 of it; 2023 loss 50; current profit 90
        ledger, absorbed = income.simulate_losses([(2021, -100.0), (2022, 30.0), (2023, -50.0)], 2026, 90.0)
        self.assertEqual(absorbed, 90.0)
        self.assertEqual([(x["year"], x["used"], x["remaining"]) for x in ledger], [(2021, 100.0, 0.0), (2023, 20.0, 30.0)])

    def test_loss_lapses_after_five_years(self):
        ledger, absorbed = income.simulate_losses([(2020, -100.0)], 2026, 50.0)  # usable through 2025
        self.assertEqual(absorbed, 0.0)
        self.assertEqual(ledger[0]["remaining"], 100.0)

    def test_instalment_chip_and_underpayment(self):
        today = date(2026, 10, 22)
        self.assertEqual(income.instalment_chip(date(2026, 9, 20), today, 100.0, 100.0)["label"], "Paid")
        self.assertEqual(income.instalment_chip(date(2026, 9, 20), today, 100.0, 80.0)["label"], "Part-paid")
        self.assertEqual(income.instalment_chip(date(2026, 9, 20), today, 100.0, 0.0)["label"], "Unpaid")
        self.assertEqual(income.instalment_chip(date(2026, 12, 20), today, 100.0, 0.0)["label"], "Due in 59 d")
        self.assertEqual(income.instalment_chip(date(2026, 9, 20), today, None, 0.0)["label"], "No estimate")
        rows = [
            {"due_date": "2026-04-20", "required": 100.0, "paid": 100.0},
            {"due_date": "2026-09-20", "required": 100.0, "paid": 60.0},
            {"due_date": "2026-12-20", "required": 100.0, "paid": 0.0},  # not due yet: ignored
        ]
        self.assertEqual(income.underpayment(rows, today), round(40.0 * rules.INSTALMENT_PENALTY, 2))
        rows[1]["paid"] = None
        self.assertIsNone(income.underpayment(rows, today))
