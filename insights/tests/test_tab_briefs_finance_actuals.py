import unittest

from insights.ml.tab_briefs.finance_actuals import briefs
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def setUp(self):
        self.p = load("finance_actuals")
        self.b = briefs(self.p)

    def test_tabs(self):
        self.assertEqual(set(self.b), {"cashflow", "receivables", "payables", "forex"})

    def test_cashflow_counts_complete_months_only(self):
        b = self.b["cashflow"]
        self.assertEqual(b["severity"], "medium")
        self.assertIn("Liquid cash is -₹246,351 with ₹9,821,496 held in fixed deposits", b["headline"])
        self.assertIn("fell in 2 of the last 6 complete months", b["headline"])
        self.assertIn("Aug 2026 (-₹2,494,406)", b["headline"])
        # net comes from the ledger (net_burn_rate), not payments in minus payments out
        self.assertIn("net cash movement on the ledger ₹86,963", b["details"][1]["text"])

    def test_receivables_severity_follows_dso_cutpoints(self):
        self.assertEqual(self.b["receivables"]["severity"], "medium")
        self.assertIn("31-60 Days, holds ₹8,227,825 (41.7%", self.b["receivables"]["headline"])
        self.p["receivables"]["current_dso"] = 75
        self.assertEqual(briefs(self.p)["receivables"]["severity"], "high")

    def test_payables_high_when_due_exceeds_cash(self):
        b = self.b["payables"]
        self.assertEqual(b["severity"], "high")
        self.assertIn("6 invoices totalling ₹1,234,428", b["headline"])
        self.assertIn("PI26271361 (₹247,800) on 24 Oct 2026", b["headline"])
        self.p["cash_flow"]["liquid_cash"] = 5_000_000
        self.assertEqual(briefs(self.p)["payables"]["severity"], "medium")

    def test_payables_nothing_due(self):
        self.p["payables"]["upcoming_payments"] = []
        self.assertEqual(briefs(self.p)["payables"]["severity"], "none")

    def test_missing_data_omits_tab(self):
        self.assertEqual(briefs({"base_currency": "INR"}), {})

    def test_forex_is_an_honest_empty_state_without_foreign_invoices(self):
        b = self.b["forex"]
        self.assertEqual(b["severity"], "none")
        self.assertIn("No foreign currency exposure", b["headline"])
        self.assertIn("Realised forex nets ₹22,873 across 3 months", b["headline"])

    def test_forex_flags_at_risk_foreign_invoices(self):
        self.p["forex"]["exposure_summary"] = [{"currency": "USD"}]
        self.p["forex"]["net_exposure_base"] = 8300000
        self.p["forex"]["at_risk_invoices"] = [{"name": "SI-1"}]
        b = briefs(self.p)["forex"]
        self.assertEqual(b["severity"], "medium")
        self.assertIn("₹8,300,000 across 1 currency. 1 foreign currency invoice at risk.", b["headline"])

    def test_payables_due_date_strips_time_component(self):
        """Ibis returns due_date as a pandas Timestamp with 00:00:00; the
        brief must emit only the date portion, never "24 Oct 2026 00:00:00"."""
        import copy
        p2 = copy.deepcopy(self.p)
        # Simulate the Timestamp shape: a string with time appended (same
        # str() rendering as pandas Timestamp in an f-string).
        for u in p2["payables"]["upcoming_payments"]:
            u["due_date"] = str(u["due_date"]) + " 00:00:00"
        headline = briefs(p2)["payables"]["headline"]
        self.assertNotIn("00:00:00", headline)
        self.assertRegex(headline, r"on \d{2} [A-Z][a-z]{2} \d{4}[^:]")
