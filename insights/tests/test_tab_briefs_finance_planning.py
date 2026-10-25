import unittest

from insights.ml.tab_briefs.finance_planning import briefs, lazy_beoverview, lazy_budget
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def setUp(self):
        self.p = load("finance_planning")
        self.b = briefs(self.p)

    def test_tabs(self):
        self.assertEqual(set(self.b), {"working", "capital", "scenarios", "comparison", "efficiency", "cashoutlook"})

    def test_working(self):
        b = self.b["working"]
        self.assertEqual(b["severity"], "low")
        self.assertIn("the lowest over 12 months was 1.58× in Mar 2026", b["headline"])
        self.p["working_capital"]["current_ratio"] = 0.8
        self.assertEqual(briefs(self.p)["working"]["severity"], "high")

    def test_capital_flags_register_gap(self):
        self.assertIn("₹1,251,458 less than the ledger", self.b["capital"]["headline"])

    def test_scenarios_uses_simulation_count_from_payload(self):
        b = self.b["scenarios"]
        self.assertEqual(b["severity"], "high")
        self.assertIn("46.1% of 1,000 simulated outcomes", b["headline"])
        self.assertIn("assumed 40% fixed-cost share", b["headline"])

    def test_comparison_handles_signs(self):
        self.assertIn("Revenue down 16.5% and net income up 32%", self.b["comparison"]["headline"])

    def test_efficiency_ignores_unavailable_ratios(self):
        b = self.b["efficiency"]
        self.assertEqual(b["severity"], "medium")
        self.assertIn("6 of 6 measurable ratios", b["headline"])
        self.assertIn("gross margin 7.5% against 35%", b["headline"])
        self.assertIn("asset turnover 0.68 against 1.2", b["headline"])

    def test_cashoutlook_negative_base_is_high(self):
        b = self.b["cashoutlook"]
        self.assertEqual(b["severity"], "high")
        self.assertIn("from ₹424,273 to -₹65,785", b["headline"])
        self.assertIn("opens at ₹683,637 and ends at ₹16,588,177", b["headline"])
        self.p["cash_forecast"]["end_of_period"]["base"] = 10
        self.assertEqual(briefs(self.p)["cashoutlook"]["severity"], "medium")


class TestLazy(unittest.TestCase):
    def test_budget_missing(self):
        b = lazy_budget({"has_budget": False, "period_info": {"fiscal_year": "2627"}})
        self.assertEqual(b, {"severity": "medium", "headline": "No submitted Budget exists for fiscal year 2627; variance cannot be computed."})

    def test_budget_variance_bands(self):
        p = {"has_budget": True, "base_currency": "INR", "summary": {"total_budget": 1000, "total_variance": 250, "variance_percentage": 25}}
        self.assertEqual(lazy_budget(p)["severity"], "high")
        p["summary"]["variance_percentage"] = 5
        self.assertEqual(lazy_budget(p)["severity"], "low")

    def test_breakeven_unconfigured(self):
        b = lazy_beoverview({"configured": False, "actual_revenue": 79215801.9, "base_currency": "INR"})
        self.assertEqual(b["severity"], "none")
        self.assertIn("revenue for the period is ₹79,215,802", b["headline"])

    def test_breakeven_rag(self):
        p = {"configured": True, "be_revenue": 100, "actual_revenue": 90, "safety_margin": -11.1, "rag": "red", "base_currency": "INR"}
        self.assertEqual(lazy_beoverview(p)["severity"], "high")
