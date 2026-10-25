import unittest

from insights.ml.tab_briefs.risk import briefs
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def setUp(self):
        self.b = briefs(load("risk"))

    def test_merged_tabs_replace_their_parts(self):
        self.assertEqual(set(self.b), {"cashflow", "operational", "compliance", "counterparty", "signals"})

    def test_cashflow(self):
        b = self.b["cashflow"]
        self.assertEqual(b["severity"], "high")  # overview.risk_components.cashflow_risk = High
        self.assertEqual(
            b["headline"],
            "Cash position is -₹246,351. Average overdue days went from 351.6 in Oct 2025 to 36.1 in Sep 2026. The top customer is 12.47% of revenue.",
        )

    def test_operational_takes_the_worst_category(self):
        b = self.b["operational"]
        self.assertEqual(b["severity"], "critical")  # component is Medium, top inventory risk is Critical
        self.assertIn("96.7% of stock items are in stockout (467 of 483)", b["headline"])
        self.assertIn("All 20 tracked suppliers deliver early on average", b["headline"])

    def test_compliance_overdue_filings_are_high(self):
        b = self.b["compliance"]
        self.assertEqual(b["severity"], "high")  # component is Low, filings are Overdue
        self.assertIn("GSTR-1 and GSTR-3B for Oct 2026 are overdue", b["headline"])
        self.assertIn("e-Invoice coverage is 100%", b["headline"])
        self.assertIn("9,497 of 9,497 documents are complete", b["headline"])

    def test_compliance_clean(self):
        p = load("risk")
        p["compliance_risk"]["gst_status"].update(gstr1_status="Compliant", gstr3b_status="Not Due")
        b = briefs(p)["compliance"]
        self.assertEqual(b["severity"], "low")
        self.assertTrue(b["headline"].startswith("GST filings are up to date."))

    def test_counterparty_leads_with_receivables(self):
        b = self.b["counterparty"]
        self.assertEqual(b["severity"], "medium")  # credit component Medium, 43.2 avg days overdue
        self.assertIn("93% of receivables (₹18,311,406 of ₹19,714,214) is past payment terms", b["headline"])
        self.assertIn("38 customers rated high risk", b["headline"])
        self.assertNotIn("payable", b["headline"].lower())

    def test_signals(self):
        b = self.b["signals"]
        self.assertEqual(b["severity"], "critical")  # the payload's own early warning
        self.assertEqual(
            b["headline"],
            "30-day cash forecast: -₹60,403 on 7 Dec 2026. 10 customers flagged for payment delay risk. 0 ledger anomalies detected.",
        )
