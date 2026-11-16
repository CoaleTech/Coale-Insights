import unittest

from insights.ml.tab_briefs.manufacturing import briefs
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def test_empty_site_gives_each_tab_its_own_payload_note(self):
        p = load("manufacturing")
        b = briefs(p)
        self.assertEqual(set(b), {"oee", "capacity", "forecast", "recommendations"})
        self.assertIn("0 Work Orders", b["oee"]["headline"])
        self.assertIn(p["oee_analysis"]["message"], b["oee"]["headline"])
        self.assertIn("QC doctype", b["oee"]["headline"])
        self.assertIn("2 material requests pending", b["oee"]["headline"])
        self.assertIn(p["capacity_utilization"]["message"], b["capacity"]["headline"])
        self.assertIn(p["production_forecast"]["message"], b["forecast"]["headline"])
        self.assertIn("not an all clear", b["recommendations"]["headline"])
        for v in b.values():
            self.assertNotIn("\u2014", v["headline"])
            self.assertEqual(v["severity"], "medium")

    def test_measured_figures_replace_gap_notes_once_work_orders_exist(self):
        p = load("manufacturing")
        p["production_metrics"].update(total_work_orders=3, total_production_qty=1200, monthly_growth_rate=4.5)
        p["oee_analysis"] = {"oee_score_pct": 72, "availability_pct": 90, "performance_pct": 85, "quality_pct": 94}
        p["capacity_utilization"] = {"overall_utilization_pct": 71}
        p["bottleneck_analysis"] = {"bottleneck_count": 1}
        b = briefs(p)
        self.assertEqual(b["oee"]["headline"], "OEE is 72%, availability 90%, performance 85%, quality 94%.")
        self.assertEqual(b["oee"]["severity"], "medium")
        self.assertEqual(b["capacity"]["headline"], "Overall utilization is 71% with 1 bottleneck.")
        self.assertEqual(b["capacity"]["severity"], "high")
        self.assertEqual(b["forecast"]["headline"], "1,200 units produced, monthly growth 4.5%.")
