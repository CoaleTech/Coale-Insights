import unittest
from datetime import date

from insights.ml.kenya_tax_intelligence import customs, etims, vat


class TestKenyaTaxPureLogic(unittest.TestCase):
    def test_classify_queue_error(self):
        c = etims.classify_queue_error
        self.assertEqual(c("Connection timeout"), "Transmission timeout")
        self.assertEqual(c("Invalid customer PIN"), "Invalid PIN")
        self.assertEqual(c("item code not registered"), "Item code")
        self.assertEqual(c("tax type invalid"), "Tax code")
        self.assertEqual(c(None), "No error recorded")

    def test_week_label(self):
        self.assertEqual(etims.week_label(date(2026, 1, 1)), "2026-W01")

    def test_supply_kind(self):
        self.assertEqual(vat.supply_kind(16, None, None), "standard")
        self.assertEqual(vat.supply_kind(0, "VAT Exempt", 16), "exempt")
        self.assertEqual(vat.supply_kind(None, None, None), "out_of_scope")
        self.assertEqual(vat.supply_kind(None, "", 0), "zero")

    def test_is_blocked_and_window_chip(self):
        self.assertTrue(vat.is_blocked("Entertainment Expenses"))
        self.assertFalse(vat.is_blocked("Stationery"))
        self.assertEqual(vat.window_chip(10)["tone"], "neg")
        self.assertEqual(vat.window_chip(25)["tone"], "warn")
        self.assertEqual(vat.window_chip(None)["tone"], "mut")

    def test_customs(self):
        self.assertEqual(customs.landed_line_kind("Import Duty"), "duty")
        self.assertIsNone(customs.landed_line_kind("Freight"))
        t = customs.entry_taxes(1_000_000, {"duty": 250_000})
        self.assertEqual((t["idf"], t["rdl"]), (35_000.0, 20_000.0))
        self.assertEqual(t["computed"], ["idf", "rdl", "vat"])
        self.assertIsNone(customs.entry_taxes(1_000_000, {})["vat"])

    def test_build_series_no_data_is_none(self):
        months = [date(2026, 8, 1), date(2026, 9, 1)]
        empty = vat.build_series(months, {}, {})
        self.assertEqual([(r["output"], r["input"], r["net"]) for r in empty], [(None, None, None)] * 2)
        some = vat.build_series(months, {date(2026, 9, 5): 160.0}, {date(2026, 9, 6): 16.0})
        self.assertEqual((some[0]["output"], some[0]["net"]), (0.0, 0.0))  # VAT site, quiet month stays 0
        self.assertEqual(some[1]["net"], 144.0)
