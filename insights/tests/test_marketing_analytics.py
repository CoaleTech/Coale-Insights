# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Tests for the marketing funnel and alert generation logic extracted from
get_marketing_overview (plan-eng-review code-quality finding 1). These are
pure functions of already-fetched query results -- no DB access needed.
"""

from frappe.tests.utils import FrappeTestCase

from insights.api.ml.marketing import _build_marketing_funnel, _generate_marketing_alerts


class TestBuildMarketingFunnel(FrappeTestCase):
    def test_funnel_stage_counts_and_values(self):
        lead_totals = {"at_opportunity": 10, "at_quotation": 5, "converted": 3}
        quote_totals = [{"count": 8}, {"count": 4}]
        won = {"count": 3}
        funnel = _build_marketing_funnel(
            lead_totals=lead_totals,
            quote_totals=quote_totals,
            won=won,
            open_value=1000.0,
            decided_value=2000.0,
            won_value=1500.0,
            total=100,
            converted=3,
        )
        self.assertEqual(len(funnel), 4)
        self.assertEqual(funnel[0]["count"], 100)
        self.assertEqual(funnel[1]["count"], 10 + 5 + 3)
        self.assertEqual(funnel[2]["count"], 12)
        self.assertEqual(funnel[2]["value"], 3000.0)
        self.assertEqual(funnel[3]["count"], 3)
        self.assertEqual(funnel[3]["value"], 1500.0)

    def test_conversion_from_prev_only_on_comparable_stages(self):
        """Stage 0 and stage 2 have no comparable prior stage (documented in
        the source: stage 1->2 crosses from leads to quotation records)."""
        lead_totals = {"at_opportunity": 0, "at_quotation": 0, "converted": 0}
        quote_totals = [{"count": 10}]
        won = {"count": 5}
        funnel = _build_marketing_funnel(
            lead_totals=lead_totals,
            quote_totals=quote_totals,
            won=won,
            open_value=0.0,
            decided_value=0.0,
            won_value=0.0,
            total=20,
            converted=0,
        )
        self.assertIsNone(funnel[0]["conversion_from_prev"])
        self.assertIsNone(funnel[2]["conversion_from_prev"])
        # Stage 1 is comparable to stage 0 (both Lead.status-derived).
        self.assertEqual(funnel[1]["conversion_from_prev"], 0.0)
        # Stage 3 is comparable to stage 2 (both Quotation-derived): 5/10 = 50%.
        self.assertEqual(funnel[3]["conversion_from_prev"], 50.0)

    def test_conversion_from_prev_is_none_when_prior_stage_is_zero(self):
        """Guards the division; a zero prior count must not raise ZeroDivisionError."""
        lead_totals = {"at_opportunity": 0, "at_quotation": 0, "converted": 0}
        quote_totals = []
        won = {"count": 0}
        funnel = _build_marketing_funnel(
            lead_totals=lead_totals,
            quote_totals=quote_totals,
            won=won,
            open_value=0.0,
            decided_value=0.0,
            won_value=0.0,
            total=0,
            converted=0,
        )
        self.assertIsNone(funnel[1]["conversion_from_prev"])
        self.assertIsNone(funnel[3]["conversion_from_prev"])


class TestGenerateMarketingAlerts(FrappeTestCase):
    def test_no_alerts_on_healthy_funnel(self):
        alerts = _generate_marketing_alerts(
            total=100,
            open_leads=20,
            expired_value=0,
            won_value=1000,
            trend=[{"leads": 10}] * 6,
            source_rows=[{"source": "A", "leads": 30}, {"source": "B", "leads": 30}, {"source": "C", "leads": 40}],
            days_stale=5,
        )
        self.assertEqual(alerts, [])

    def test_intake_bottleneck_alert(self):
        alerts = _generate_marketing_alerts(
            total=100, open_leads=60, expired_value=0, won_value=0,
            trend=[], source_rows=[], days_stale=None,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "high")

    def test_expired_exceeds_won_alert(self):
        alerts = _generate_marketing_alerts(
            total=0, open_leads=0, expired_value=5000, won_value=1000,
            trend=[], source_rows=[], days_stale=None,
        )
        self.assertTrue(any(a["severity"] == "critical" for a in alerts))

    def test_lead_volume_collapse_alert(self):
        # earlier avg = 30, recent avg = 5 -> recent < earlier * 0.5
        trend = [{"leads": 30}, {"leads": 30}, {"leads": 30}, {"leads": 5}, {"leads": 5}, {"leads": 5}]
        alerts = _generate_marketing_alerts(
            total=0, open_leads=0, expired_value=0, won_value=0,
            trend=trend, source_rows=[], days_stale=None,
        )
        self.assertTrue(any("collapsed" in a["title"] for a in alerts))

    def test_source_concentration_alert(self):
        source_rows = [{"source": "Only Channel", "leads": 90}, {"source": "Other", "leads": 10}]
        alerts = _generate_marketing_alerts(
            total=0, open_leads=0, expired_value=0, won_value=0,
            trend=[], source_rows=source_rows, days_stale=None,
        )
        self.assertTrue(any("concentrated" in a["title"] for a in alerts))

    def test_stale_data_alert_is_inserted_first(self):
        """Stale-data alert must be the operator's first read -- it explains
        why every other panel may show empty/zero figures."""
        source_rows = [{"source": "Only Channel", "leads": 90}, {"source": "Other", "leads": 10}]
        alerts = _generate_marketing_alerts(
            total=0, open_leads=0, expired_value=0, won_value=0,
            trend=[], source_rows=source_rows, days_stale=90,
        )
        self.assertEqual(alerts[0]["title"], "CRM data is not being maintained")

    def test_no_stale_alert_within_threshold(self):
        alerts = _generate_marketing_alerts(
            total=0, open_leads=0, expired_value=0, won_value=0,
            trend=[], source_rows=[], days_stale=59,
        )
        self.assertEqual(alerts, [])
