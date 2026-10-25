import unittest

from insights.ml.tab_briefs.marketing import briefs, lazy_winprob
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def test_channels_brief(self):
        b = briefs(load("marketing"))["channels"]
        self.assertEqual(b["severity"], "high")
        self.assertEqual(
            b["headline"],
            "Existing Customer wins ₹174,485 per lead against ₹1,487 for IndiaMart (117×), yet supplies 1.2% of leads.",
        )

    def test_trend_brief(self):
        b = briefs(load("marketing"))["trend"]
        self.assertEqual(b["severity"], "high")
        self.assertIn("82% below its Mar 2025 peak: 58 a month", b["headline"])
        self.assertIn("against 329 at peak", b["headline"])

    def test_coverage_brief(self):
        b = briefs(load("marketing"))["coverage"]
        self.assertEqual(b["severity"], "medium")
        self.assertIn("Mumbai, Ahmedabad and Hyderabad hold 432 leads", b["headline"])
        self.assertIn("2.5% to 4.3% conversion, below the 8.8% average", b["headline"])
        self.assertIn("admin@jkmchemtrade.com converts at 37.7%, 4.3× the average", b["headline"])

    def test_no_text_has_dash_or_nan(self):
        for tab, b in briefs(load("marketing")).items():
            self.assertNotIn("—", b["headline"], tab)
            self.assertNotIn("nan", b["headline"].lower(), tab)

    def test_winprob_states_it_is_not_a_trained_model(self):
        r = {"status": "success", "training": {"closed_total": 20, "won": 12, "lost": 8}}
        found = lazy_winprob(r)
        assert found
        self.assertIn("not a trained model", found["headline"])
        self.assertIsNone(lazy_winprob({"status": "insufficient_data"}))
