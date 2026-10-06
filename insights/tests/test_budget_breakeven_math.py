"""Pure-function checks for the budget-variance and break-even maths (no DB, no fixtures)."""

import unittest
from datetime import date

from insights.ml.breakeven_engine import BreakevenEngine, _be_revenue, _polynomial_irr
from insights.ml.budget_variance_intelligence import (
    BudgetVarianceIntelligence,
    _is_favorable,
    _prorated_amount,
)


class TestBudgetMath(unittest.TestCase):
    def test_favorable_follows_root_type(self):
        self.assertTrue(_is_favorable("Income", 120, 100))
        self.assertFalse(_is_favorable("Income", 80, 100))
        self.assertTrue(_is_favorable("Expense", 80, 100))
        self.assertTrue(_is_favorable("Expense", 100, 100))
        self.assertFalse(_is_favorable("Expense", 120, 100))

    def test_favorable_is_none_without_budget(self):
        self.assertIsNone(_is_favorable("Expense", 50, 0))
        self.assertIsNone(_is_favorable("Income", 50, None))

    def test_prorated_amount_is_inclusive_and_clipped(self):
        # 365-day budget; Apr 1 - Jun 30 is 91 days
        self.assertAlmostEqual(
            _prorated_amount(365, date(2026, 4, 1), date(2027, 3, 31), date(2026, 4, 1), date(2026, 6, 30)), 91
        )
        # window entirely outside the budget
        self.assertEqual(_prorated_amount(100, date(2026, 4, 1), date(2026, 4, 30), date(2026, 6, 1), date(2026, 6, 30)), 0.0)

    def test_period_budget_follows_distribution_rows(self):
        row = {
            "budget_amount": 1200.0,
            "start": date(2026, 4, 1),
            "end": date(2027, 3, 31),
            # front-loaded: all in April, nothing else -> even pro-rating would give ~100/month
            "distribution": [{"amount": 1200.0, "start_date": date(2026, 4, 1), "end_date": date(2026, 4, 30)}],
        }
        period = BudgetVarianceIntelligence._period_budget
        self.assertAlmostEqual(period(row, date(2026, 4, 1), date(2026, 4, 30)), 1200.0)
        self.assertEqual(period(row, date(2026, 5, 1), date(2026, 5, 31)), 0.0)

    def test_period_budget_prorates_without_distribution(self):
        row = {"budget_amount": 365.0, "start": date(2026, 4, 1), "end": date(2027, 3, 31), "distribution": []}
        self.assertAlmostEqual(
            BudgetVarianceIntelligence._period_budget(row, date(2026, 4, 1), date(2026, 4, 30)), 30
        )


class TestBreakevenMath(unittest.TestCase):
    def test_be_revenue_uses_contribution_margin_ratio(self):
        # revenue 1000, variable 600 -> CM ratio 0.4; fixed 200 -> BE revenue 500
        self.assertEqual(_be_revenue(200, 600, 1000), 500.0)

    def test_be_revenue_is_none_when_no_break_even_exists(self):
        self.assertIsNone(_be_revenue(200, 600, 0))
        self.assertIsNone(_be_revenue(200, 1000, 1000))  # CM ratio 0
        self.assertIsNone(_be_revenue(200, 1200, 1000))  # negative CM

    def test_roce_rag_compares_decimals_against_decimal_target(self):
        engine = BreakevenEngine.__new__(BreakevenEngine)
        engine.roce_target = 0.15  # Insights Settings 15 (percent) converted once at load
        self.assertEqual(engine._rag_roce(0.2008), "green")
        self.assertEqual(engine._rag_roce(0.13), "amber")
        self.assertEqual(engine._rag_roce(0.05), "red")
        self.assertIsNone(engine._rag_roce(None))

    def test_coverage_rag_is_none_when_not_computable(self):
        engine = BreakevenEngine.__new__(BreakevenEngine)
        self.assertIsNone(engine._rag_coverage(None))
        self.assertEqual(engine._rag_coverage(1.5), "green")
        self.assertEqual(engine._rag_coverage(1.1), "amber")
        self.assertEqual(engine._rag_coverage(0.9), "red")

    def test_irr_requires_an_initial_outlay(self):
        self.assertAlmostEqual(_polynomial_irr([-100, 110]), 0.10, places=6)
        self.assertIsNone(_polynomial_irr([100, 50, -10]))  # starts positive: no investment profile
        self.assertIsNone(_polynomial_irr([0, 0, 0]))
        self.assertIsNone(_polynomial_irr([-100, -50]))  # never recovered
