import unittest

from insights.ml.tab_briefs.manufacturing import briefs
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def test_empty_site_collapses_into_production_with_payload_notes(self):
        p = load("manufacturing")
        b = briefs(p)["production"]
        self.assertEqual(b["severity"], "medium")
        self.assertNotIn("—", b["headline"])
        self.assertIn("0 Work Orders", b["headline"])
        self.assertIn(p["oee_analysis"]["message"], b["headline"])
        self.assertIn("QC doctype", b["headline"])
        self.assertIn("2 material requests pending", b["headline"])
        self.assertTrue(set(["oee", "capacity", "forecast", "recommendations"]).isdisjoint(briefs(p)))

    def test_no_production_brief_once_work_orders_exist(self):
        p = load("manufacturing")
        p["production_metrics"]["total_work_orders"] = 3
        self.assertEqual(briefs(p), {})
