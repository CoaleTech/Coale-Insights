import unittest

from insights.ml.tab_briefs.finance_planning import briefs, lazy_beoverview, lazy_budget
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def setUp(self):
        self.p = load("finance_planning")
        self.b = briefs(self.p)

    def test_tabs(self):
        self.assertEqual(set(self.b), {"working", "capital", "scenarios", "comparison", "ratios", "cost", "cashforecast", "cashflow13"})

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
        self.assertIn("47.4% of 1,000 simulated outcomes", b["headline"])
        self.assertIn("assumed 40% fixed-cost share", b["headline"])

    def test_comparison_handles_signs(self):
        self.assertIn("Revenue down 16.5% and net income up 32%", self.b["comparison"]["headline"])

    def test_ratios_ignores_unavailable_ratios(self):
        b = self.b["ratios"]
        self.assertEqual(b["severity"], "medium")
        self.assertIn("6 of 6 measurable ratios", b["headline"])
        self.assertIn("gross margin 7.5% against 35%", b["headline"])
        self.assertIn("asset turnover 0.68 against 1.2", b["headline"])

    def test_cost_states_margins_and_ungradable_ratios(self):
        b = self.b["cost"]
        self.assertEqual(b["severity"], "low")
        self.assertIn("Gross profit is 8.7% of revenue", b["headline"])
        self.assertIn("net profit is 4.3%", b["headline"])
        self.assertIn("have no data", b["headline"])
        self.p["cost_structure"]["overall_status"] = "risky"
        self.assertEqual(briefs(self.p)["cost"]["severity"], "high")

    def test_cost_omitted_without_revenue(self):
        self.p["cost_structure"]["figures"]["revenue"] = 0
        self.assertNotIn("cost", briefs(self.p))

    def test_cashforecast_negative_base_is_high(self):
        b = self.b["cashforecast"]
        self.assertEqual(b["severity"], "high")
        self.assertIn("from ₹424,273 to -₹65,785", b["headline"])
        self.assertNotIn("13-week model opens", b["headline"])
        self.p["cash_forecast"]["end_of_period"]["base"] = 10
        self.assertEqual(briefs(self.p)["cashforecast"]["severity"], "medium")

    def test_cashforecast_runway_wording(self):
        def runway(base, pess):
            self.p["cash_forecast"].update(base_runway_days=base, pessimistic_runway_days=pess)
            return next(d["text"] for d in briefs(self.p)["cashforecast"]["details"] if d["label"] == "Runway")

        self.assertEqual(runway(0, 0), "Base case is already at or below zero; pessimistic case is already at or below zero.")
        self.assertEqual(runway(None, 12), "Base case stays positive for 90 days; pessimistic case runs out in 12 days.")
        self.assertEqual(runway(40, None), "Base case runs out in 40 days; pessimistic case stays positive for 90 days.")

    def test_cashflow13_reads_the_weekly_model(self):
        b = self.b["cashflow13"]
        self.assertIn("opens at ₹683,637 and ends at ₹16,588,177", b["headline"])
        self.assertIn("lowest balance of", b["headline"])
        self.p["thirteen_week_forecast"]["summary"]["minimum_balance"] = -5
        self.assertEqual(briefs(self.p)["cashflow13"]["severity"], "high")

    def test_cashflow13_dates_read_like_the_page(self):
        self.p["thirteen_week_forecast"]["summary"]["minimum_balance_date"] = "2026-10-26"
        self.p["thirteen_week_forecast"]["payroll_detection"] = {"detected": True, "frequency": "monthly", "typical_amount": 100, "next_date": "2026-10-30"}
        b = briefs(self.p)["cashflow13"]
        self.assertIn("(26 Oct 2026)", b["headline"])
        self.assertIn("next 30 Oct 2026.", next(d["text"] for d in b["details"] if d["label"] == "Payroll"))


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
