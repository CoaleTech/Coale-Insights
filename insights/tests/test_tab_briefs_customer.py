import unittest

from insights.ml.tab_briefs.customer import briefs, lazy_cust_patterns
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def setUp(self):
        self.b = briefs(load("customer"))

    def test_every_brief_has_a_severity_and_a_headline(self):
        self.assertEqual(set(self.b), {"cust-list", "cust-geography", "cust-actions", "cust-cohorts", "cust-rankings"})
        for tab, b in self.b.items():
            self.assertIn(b["severity"], {"critical", "high", "medium", "low", "none"}, tab)
            self.assertTrue(b["headline"].strip(), tab)
            self.assertNotIn("—", b["headline"], tab)
            self.assertNotIn("nan", b["headline"].lower(), tab)

    def test_cust_list(self):
        b = self.b["cust-list"]
        self.assertEqual(b["severity"], "high")
        for token in ("78.5%", "456 of 581", "214 accounts", "101 of them Critical", "top 51"):
            self.assertIn(token, b["headline"])

    def test_cust_geography(self):
        b = self.b["cust-geography"]
        self.assertEqual(b["severity"], "medium")
        for token in ("Surat", "48.9%", "38.0%", "9.7%", "12.4%", "3 customers", "67.2%"):
            self.assertIn(token, b["headline"])

    def test_cust_actions_uses_summary_not_the_capped_list(self):
        b = self.b["cust-actions"]
        self.assertEqual(b["severity"], "high")
        self.assertIn("307 customers", b["headline"])
        self.assertIn("214", b["headline"])

    def test_cust_cohorts(self):
        b = self.b["cust-cohorts"]
        self.assertEqual(b["severity"], "high")
        for token in ("17.5%", "10.8%"):
            self.assertIn(token, b["headline"])

    def test_cust_rankings(self):
        self.assertIn(self.b["cust-rankings"]["severity"], {"medium", "none"})

    def test_lazy_patterns(self):
        r = {
            "day_of_week": {"peak_day": "Thursday", "data": [{"day_name": "Thursday", "total_revenue": 25.0}]},
            "monthly": {"peak_month": "March"},
            "seasonal": {"peak_quarter": "Q1 (Jan-Mar)"},
            "summary": {"total_revenue": 100.0, "total_orders": 40},
            "analysis_scope": {"transaction_count": 40},
        }
        h = lazy_cust_patterns(r)["headline"]
        for token in ("Thursday (25.0% of revenue)", "March", "Q1 (Jan-Mar)", "40 transactions"):
            self.assertIn(token, h)
        self.assertIn("no purchase patterns", lazy_cust_patterns({"patterns": None})["headline"])
