import unittest
from datetime import date
from unittest.mock import patch

from insights.ml.tab_briefs.tax import briefs
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def setUp(self):
        self.b = briefs(load("tax"))

    def test_gst(self):
        b = self.b["gst"]
        self.assertEqual(b["severity"], "high")
        self.assertEqual(
            b["headline"],
            "2A/2B match rate is 49%. ₹2,429,335 of ITC is at risk across 211 invoices from suppliers that have not filed. 1,807 rows unactioned.",
        )

    def test_compliance_lists_problem_areas_and_idle_area(self):
        b = self.b["compliance"]
        self.assertEqual(b["severity"], "high")
        self.assertIn("78.4% across 6 areas", b["headline"])
        self.assertIn("GST Overdue, ITC At Risk, e-Waybill Action Required", b["headline"])
        self.assertIn("Customs / Import has no activity", b["headline"])

    def test_tds(self):
        b = self.b["tds"]
        self.assertEqual(b["severity"], "medium")
        for fig in ("₹81,809", "₹93,277", "₹11,468", "₹82,434", "6 periods overdue"):
            self.assertIn(fig, b["headline"])

    def test_planning_counts_instalments_from_today(self):
        with patch("insights.ml.tab_briefs.tax._today", return_value=date(2026, 10, 22)):
            b = briefs(load("tax"))["planning"]
        self.assertIn("2 of 4 advance tax instalments have passed", b["headline"])
        self.assertIn("3rd Instalment, cumulative 75%, due 15 Dec 2026 (54 days)", b["headline"])
        self.assertIn("R² 0.27", b["headline"])

    def test_actions_names_queue_gaps(self):
        b = self.b["actions"]
        self.assertEqual(b["severity"], "high")
        self.assertIn("1 action open with ₹28,138,169 exposure", b["headline"])
        self.assertIn("ITC, e-Waybill are flagged with no action", b["headline"])
        self.assertIn("TDS overdue is ₹82,434", b["headline"])

    def test_legal_and_customs_are_separate_tabs(self):
        self.assertEqual(self.b["legal"]["severity"], "none")
        self.assertEqual(self.b["legal"]["headline"], "0 legal matters open with ₹0 exposure.")
        self.assertEqual(self.b["customs"]["severity"], "none")
        self.assertEqual(self.b["customs"]["headline"], "0 Bills of Entry recorded.")

    def test_no_dash_or_nan(self):
        for tab, b in self.b.items():
            self.assertNotIn("—", b["headline"], tab)
            self.assertNotIn("nan", b["headline"].lower(), tab)
