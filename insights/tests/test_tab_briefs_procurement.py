import unittest

from insights.ml.tab_briefs.procurement import briefs
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def setUp(self):
        self.b = briefs(load("procurement"))

    def test_suppliers_follow_the_vue_rate_thresholds(self):
        b = self.b["suppliers"]
        self.assertEqual(b["severity"], "medium")  # 74.6 is between 70 and 90
        self.assertIn("on-time rate is 74.6%, quality 99.9%", b["headline"])
        self.assertIn("4 suppliers at 0% on-time account for ₹5,155,066 of spend", b["headline"])

    def test_suppliers_skip_zero_sentence_when_the_list_is_partial(self):
        p = load("procurement")
        p["supplier_performance"]["total_suppliers"] = 400
        self.assertNotIn("0% on-time", briefs(p)["suppliers"]["headline"])

    def test_analytics(self):
        b = self.b["analytics"]
        self.assertEqual(b["severity"], "high")
        self.assertEqual(
            b["headline"],
            "30 purchase orders pending, worth ₹15,974,584, the oldest 586 days. PO to GRN 1.1 days and GRN to invoice 0.1 days on average.",
        )

    def test_pricing(self):
        b = self.b["pricing"]
        self.assertIn("82 of 120 items analyzed (68%)", b["headline"])
        self.assertIn("₹21,479,946", b["headline"])

    def test_risks(self):
        b = self.b["risks"]
        self.assertEqual(b["severity"], "low")
        self.assertIn("Low at 12.2/100", b["headline"])
        self.assertIn("7.8%", b["headline"])
        self.assertIn("75 items have a single supplier, ₹42,714,078", b["headline"])

    def test_forecasts(self):
        b = self.b["forecasts"]
        self.assertEqual(b["severity"], "low")
        self.assertIn("trending down by ₹84,722 a month", b["headline"])
        self.assertIn("₹41,582,180: Nov 2026 ₹13,945,449, Dec 2026 ₹13,860,727, Jan 2027 ₹13,776,005", b["headline"])
