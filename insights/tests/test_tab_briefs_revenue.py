import unittest

from insights.ml.tab_briefs.revenue import briefs, lazy_rev_sources
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def setUp(self):
        self.b = briefs(load("revenue"))

    def test_every_brief_has_a_severity_and_a_headline(self):
        self.assertEqual(len(self.b), 4)
        for tab, b in self.b.items():
            self.assertIn(b["severity"], {"critical", "high", "medium", "low", "none"}, tab)
            self.assertTrue(b["headline"].strip(), tab)
            self.assertNotIn("—", b["headline"], tab)
            self.assertNotIn("nan", b["headline"].lower(), tab)

    def test_rev_payment(self):
        b = self.b["rev-payment"]
        self.assertEqual(b["severity"], "high")  # DSO 67.2 > 60, same cut as the DSO card
        for token in ("₹19,713,840", "67.2 days", "14.2%"):
            self.assertIn(token, b["headline"])

    def test_rev_reps(self):
        b = self.b["rev-reps"]
        self.assertEqual(b["severity"], "medium")
        for token in ("94.7%", "5.3%", "₹149,257,108", "19.6%", "0.01%"):
            self.assertIn(token, b["headline"])

    def test_rev_margins(self):
        b = self.b["rev-margins"]
        for token in ("12.9%", "6.8%", "7.7%", "54.4%", "1.9%", "5.9%", "6.1pp"):
            self.assertIn(token, b["headline"])

    def test_rev_forecasts(self):
        b = self.b["rev-forecasts"]
        self.assertEqual(b["severity"], "medium")
        for token in ("₹16,843,643", "68.5%", "38 days"):
            self.assertIn(token, b["headline"])

    def test_missing_blocks_omit_the_brief(self):
        self.assertEqual(briefs({"base_currency": "INR"}), {})

    def test_lazy_sources(self):
        q = {"total": 10, "won": 3, "lost": 5, "pending": 2, "conversion_rate": 30.0,
             "lost_reasons": [{"order_lost_reason": "Price", "count": 4}, {"order_lost_reason": "Sample", "count": 1}]}
        h = lazy_rev_sources(q)["headline"]
        self.assertIn("30.0%", h)
        self.assertIn("Price (4)", h)
        self.assertIn("Lead Source", lazy_rev_sources({"total": 0})["headline"])


class TestDetailsAndActions(unittest.TestCase):
    """Figures in details/actions are arithmetic on the payload, never invented."""

    def setUp(self):
        self.p = load("revenue")
        self.b = briefs(self.p)

    def test_payment_excess_receivables_is_ar_less_target_days_of_daily_sales(self):
        ful = self.p["fulfillment"]
        excess = ful["total_receivables"] - 30 * ful["avg_daily_sales"]
        act = self.b["rev-payment"]["actions"][0]
        self.assertEqual(act["impact"], f"₹{round(excess):,}")

    def test_payment_without_dso_gap_has_no_working_capital_action(self):
        self.p["fulfillment"]["dso"] = 25
        acts = briefs(self.p)["rev-payment"].get("actions", [])
        self.assertFalse([a for a in acts if "DSO" in a["title"]])

    def test_reps_hhi_matches_shares(self):
        reps, team = self.p["sales_reps"]["reps"], self.p["sales_reps"]["total_team_revenue"]
        hhi = sum((r["total_revenue"] / team * 100) ** 2 for r in reps)
        self.assertIn(f"{hhi:,.0f}", self.b["rev-reps"]["details"][0]["text"])

    def test_forecast_actions_report_payload_sums(self):
        rows = self.p["forecasts"]["sales_forecast"]["forecast"]
        up = sum(r["yhat_upper"] for r in rows)
        text = next(a["text"] for a in self.b["rev-forecasts"]["actions"] if "range" in a["title"])
        self.assertIn(f"₹{round(up):,}", text)

    def test_no_estimate_words_or_em_dashes(self):
        for tab, b in self.b.items():
            blob = " ".join([b["headline"]] + [d["text"] for d in b.get("details", [])] + [a["text"] for a in b.get("actions", [])])
            self.assertNotIn("—", blob, tab)
            for word in ("approximately", "about ", "~"):
                self.assertNotIn(word, blob, tab)
