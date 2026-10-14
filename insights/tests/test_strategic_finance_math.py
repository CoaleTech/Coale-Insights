# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Pure-function tests for strategic finance math (no DB)."""

import unittest
from datetime import date
from types import SimpleNamespace

from insights.ml.strategic_finance.cost_ratios import _get_fixed_cost
from insights.ml.strategic_finance.forecast import _shift_weeks, apply_scenario
from insights.ml.strategic_finance.scenarios import build_periods, calc_change
from insights.ml.strategic_finance.summary import calculate_health_scores, generate_key_insights
from insights.ml.strategic_finance.data import (
    _combined_weekly_estimates,
    estimate_other_receipts,
    estimate_operating_expenses,
    get_cash_balance,
    _weeks_of_history,
)


def _weeks(ar):
    return [
        {
            "opening_balance": 100.0,
            "inflows": {"ar_collections": a, "other_receipts": 0},
            "outflows": {"ap_payments": 0, "payroll": 0, "operating_expenses": 0, "taxes": 0},
        }
        for a in ar
    ]


class TestStrategicFinanceMath(unittest.TestCase):
    def test_calc_change(self):
        self.assertIsNone(calc_change(50, 0))
        self.assertEqual(calc_change(150, 100), 50.0)
        self.assertEqual(calc_change(50, -100), 150.0)

    def test_prior_quarter_is_full_quarter(self):
        p = build_periods(date(2026, 10, 6), date(2026, 4, 1), date(2027, 3, 31))
        self.assertEqual((p["prior_quarter"]["start"], p["prior_quarter"]["end"]), (date(2026, 7, 1), date(2026, 9, 30)))
        self.assertEqual(p["prior_quarter"]["label"], "Q3 2026")
        self.assertEqual((p["prior_month"]["start"], p["prior_month"]["end"]), (date(2026, 9, 1), date(2026, 9, 30)))

    def test_prior_quarter_year_rollover(self):
        p = build_periods(date(2026, 1, 10), date(2025, 4, 1), date(2026, 3, 31))
        self.assertEqual((p["prior_quarter"]["start"], p["prior_quarter"]["end"]), (date(2025, 10, 1), date(2025, 12, 31)))
        self.assertEqual(p["prior_quarter"]["label"], "Q4 2025")

    def test_fiscal_labels_and_leap_safe_prior_ytd(self):
        p = build_periods(date(2028, 2, 29), date(2027, 4, 1), date(2028, 3, 31))
        self.assertEqual(p["current_ytd"]["label"], "YTD FY27-28")
        self.assertEqual(p["prior_ytd"]["label"], "YTD FY26-27")
        self.assertEqual((p["prior_ytd"]["start"], p["prior_ytd"]["end"]), (date(2026, 4, 1), date(2027, 2, 28)))

    def test_partial_flag(self):
        fy = (date(2026, 4, 1), date(2027, 3, 31))
        self.assertTrue(build_periods(date(2026, 10, 6), *fy)["current_month"]["partial"])
        self.assertFalse(build_periods(date(2026, 10, 20), *fy)["current_month"]["partial"])
        self.assertTrue(build_periods(date(2026, 10, 6), *fy)["current_quarter"]["partial"])

    def test_shift_weeks_preserves_total_within_horizon(self):
        self.assertEqual(_shift_weeks([10, 20, 30, 0, 0], 2), [0, 0, 10, 20, 30])
        self.assertEqual(_shift_weeks([10, 20, 30], -1), [30, 30, 0])

    def test_ar_delay_is_timing_not_loss(self):
        weeks = _weeks([100, 100, 0, 0, 0, 0])
        base = apply_scenario(None, weeks)
        delayed = apply_scenario(None, weeks, ar_delay_weeks=2)
        self.assertEqual(base["ending_balance"], delayed["ending_balance"])
        self.assertLess(delayed["min_balance"], base["min_balance"] + 1e-9)

    def test_threshold_is_explicit(self):
        weeks = _weeks([0, 0, 0])
        self.assertEqual(apply_scenario(None, weeks, threshold=500)["weeks_below_threshold"], 3)
        self.assertEqual(apply_scenario(None, weeks)["weeks_below_threshold"], 0)

    def test_unconfigured_fixed_cost_is_none(self):
        self.assertIsNone(_get_fixed_cost("c", "2026-04-01", "2026-10-06", SimpleNamespace(fixed_cost_centers="  ")))

    def test_none_ratios_do_not_crash_or_skew_scores(self):
        hs = calculate_health_scores(None, net_margin=None, roe=None, roa=None,
                                     debt_to_equity=None, cash_runway_months=None, revenue_growth=None)
        self.assertEqual(hs["liquidity"], 90)
        self.assertEqual(hs["profitability"], 20)
        insights = generate_key_insights(None, 0, 0, net_margin=None, revenue_growth=None,
                                         cash_runway_months=None, debt_to_equity=None, roe=None, health_scores=hs)
        self.assertEqual(insights, [])

    def test_get_cash_balance_cached(self):
        """get_cash_balance returns cached value without hitting DB."""
        intel = SimpleNamespace(company="X", _cash_balance=42.0)
        self.assertEqual(get_cash_balance(intel), 42.0)

    def test_weeks_of_history_cached(self):
        """_weeks_of_history returns cached value without hitting DB."""
        intel = SimpleNamespace(company="X", _woh=7)
        self.assertEqual(_weeks_of_history(intel, "2026-10-14"), 7)

    def test_combined_weekly_estimates_cached(self):
        """estimate_* wrappers return from _weekly_estimates cache by index."""
        intel = SimpleNamespace(company="X", _weekly_estimates=(12.5, 8.3))
        self.assertAlmostEqual(estimate_other_receipts(intel, None), 12.5)
        self.assertAlmostEqual(estimate_operating_expenses(intel, None), 8.3)

    def test_combined_weekly_estimates_result_is_stored(self):
        """_combined_weekly_estimates returns the cached tuple when pre-set."""
        intel = SimpleNamespace(company="X", _weekly_estimates=(5.0, 3.0))
        result = _combined_weekly_estimates(intel)
        self.assertEqual(result, (5.0, 3.0))
