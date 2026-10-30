import unittest

from insights.ml.tab_briefs.risk import briefs
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def setUp(self):
        self.b = briefs(load("risk"))

    def test_one_brief_per_tab(self):
        self.assertEqual(set(self.b), {"credit", "payables", "cashflow", "operational", "compliance", "predictive", "ledger"})

    def test_cashflow(self):
        b = self.b["cashflow"]
        self.assertEqual(b["severity"], "high")  # overview.risk_components.cashflow_risk = High
        self.assertEqual(
            b["headline"],
            "Cash position is -₹246,351. Invoices raised in Oct 2025 ran 351.6 days late on average, those raised in Sep 2026 36.1. The top customer is 12.47% of revenue.",
        )

    def test_forecast_pace_reads_as_above_or_below(self):
        # The model reports the last week's pace as a signed % of the 30-day pace; "-73.9%" alone reads as a rate.
        for sign, word in (("-73.9%", "73.9% below"), ("12.5%", "12.5% above")):
            p = load("risk")
            p["predictive_analytics"]["cash_flow_forecast"]["model_performance"]["trend"] = sign
            text = next(d["text"] for d in briefs(p)["predictive"]["details"] if d["label"] == "Forecast model")
            self.assertIn(f"runs {word} the 30-day pace", text)

    def test_operational_takes_the_worst_category(self):
        b = self.b["operational"]
        self.assertEqual(b["severity"], "critical")  # component is Medium, top inventory risk is Critical
        self.assertIn("95.1% of active stock items are in stockout (548 of 576)", b["headline"])
        self.assertIn("All 20 tracked suppliers deliver early on average", b["headline"])

    def test_compliance_overdue_filings_are_high(self):
        p = load("risk")
        p["compliance_risk"]["gst_status"].update(gstr1_overdue=1, gstr3b_overdue=2)
        b = briefs(p)["compliance"]
        self.assertEqual(b["severity"], "high")  # component is Low, filings are Overdue
        self.assertIn("GSTR-1 has 1 overdue period and GSTR-3B has 2 overdue periods", b["headline"])
        self.assertIn("e-Invoice coverage is 100%", b["headline"])
        self.assertIn("9,497 of 9,497 documents are complete", b["headline"])

    def test_compliance_clean(self):
        p = load("risk")
        p["compliance_risk"]["gst_status"].update(gstr1_status="Compliant", gstr3b_status="Not Due")
        b = briefs(p)["compliance"]
        self.assertEqual(b["severity"], "low")
        self.assertTrue(b["headline"].startswith("GST filings are up to date."))

    def test_credit_is_receivables_only(self):
        b = self.b["credit"]
        self.assertEqual(b["severity"], "medium")  # credit component Medium, 43.2 avg days overdue
        self.assertIn("93% of receivables (₹18,311,406 of ₹19,714,214) is past payment terms", b["headline"])
        self.assertIn("38 customers rated high risk", b["headline"])
        self.assertNotIn("supplier", b["headline"].lower())

    def test_payables_takes_the_worst_supplier_category(self):
        b = self.b["payables"]
        self.assertEqual(b["severity"], "critical")  # the largest balances are rated Critical
        self.assertEqual(
            b["headline"],
            "₹19,069,276 is owed to suppliers, 86% of it (₹16,417,303) past terms; 32 suppliers rated high risk.",
        )

    def test_predictive(self):
        b = self.b["predictive"]
        self.assertEqual(b["severity"], "critical")  # the payload's own early warning
        self.assertEqual(
            b["headline"],
            "30-day cash forecast: -₹60,403 on 7 Dec 2026. 10 customers flagged for payment delay risk.",
        )

    def test_ledger_clean_and_flagged(self):
        self.assertEqual(self.b["ledger"]["severity"], "none")
        p = load("risk")
        p["predictive_analytics"]["anomalies"] = [{"severity": "high", "type": "round_amount", "description": "Invoice X is a round 1,000,000", "date": "2026-10-01"}]
        b = briefs(p)["ledger"]
        self.assertEqual(b["severity"], "high")
        self.assertEqual(b["headline"], "1 ledger anomaly detected by the model.")
        self.assertEqual(b["details"][0]["label"], "Round amount")
