import unittest

from insights.ml.tab_briefs.inventory import briefs, lazy_itemwise_be
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def setUp(self):
        self.b = briefs(load("inventory"))

    def test_warehouses(self):
        b = self.b["warehouses"]
        self.assertEqual(b["severity"], "low")
        self.assertEqual(
            b["headline"],
            "₹1,025,946 of stock sits across 2 warehouses; Warehouse - JKM holds 72.8% of it. "
            "Reserved demand of 132,145 units is 11.8× the 11,185 units on hand.",
        )
        self.assertFalse(b.get("actions"))

    def test_warehouses_uncovered_reserved_demand_is_flagged(self):
        p = load("inventory")
        for w in p["warehouse_analysis"]["by_warehouse"]:
            w["ordered_qty"] = "0"
        b = briefs(p)["warehouses"]
        self.assertEqual(b["severity"], "medium")
        self.assertIn("120,960 uncovered", b["actions"][0]["text"])

    def test_turnover_names_the_slowest_group(self):
        b = self.b["turnover"]
        self.assertEqual(b["severity"], "medium")
        self.assertEqual(
            b["headline"],
            "Food & Beverages , Cleaning, Industrial turns at 14× against 133.3× overall, holding ₹443,088 of stock for 26 days of sales.",
        )

    def test_abc_xyz(self):
        b = self.b["abc-xyz"]
        self.assertEqual(b["severity"], "none")
        self.assertIn("48 A-class items of 309 classified carry 79.8% of ₹148,059,819", b["headline"])
        self.assertIn("9 AZ items", b["headline"])

    def test_aging(self):
        b = self.b["aging"]
        self.assertEqual(b["severity"], "medium")
        self.assertIn("4 items older than 180 days hold ₹88,091", b["headline"])
        self.assertIn("Sodium Benzoate is 353 days old and reaches 365 days in 12 days", b["headline"])

    def test_aging_past_365_is_high(self):
        p = load("inventory")
        p["aging_analysis"]["age_buckets"]["365+ days"] = {"count": 1, "value": 10.0}
        self.assertEqual(briefs(p)["aging"]["severity"], "high")

    def test_procurement_counts_only_listed_stale_orders(self):
        b = self.b["procurement"]
        self.assertEqual(b["severity"], "high")
        self.assertIn("30 purchase orders open; 20 of the 20 oldest are over 90 days", b["headline"])
        self.assertIn("the oldest 586 days", b["headline"])
        self.assertIn("287 items below reorder level", b["headline"])

    def test_lazy_itemwise_be(self):
        empty = {"period": "Quarterly", "date_range": {"start": "2026-07-01", "end": "2026-09-30"}, "items": []}
        self.assertEqual(lazy_itemwise_be(empty)["severity"], "none")
        some = {"period": "Quarterly", "items": [{"coverage": 0.5}, {"coverage": 2.0}, {"coverage": None}]}
        b = lazy_itemwise_be(some)
        self.assertEqual(b["severity"], "high")
        self.assertIn("3 items analyzed for Quarterly; 1 sell below", b["headline"])
        self.assertIsNone(lazy_itemwise_be({}))
