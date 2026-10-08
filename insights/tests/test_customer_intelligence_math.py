# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Customer intelligence reconciles with the ledger.

The pure tests pin the shared RFM definition; the DB tests compare the payload
against an independent frappe.qb read of the same Sales Invoices (skipped when
the site has no sales to compare).
"""

from unittest.mock import patch

import frappe
import pandas as pd
from frappe.query_builder.functions import Count, Sum
from frappe.tests.utils import FrappeTestCase

from insights.ml import customer as cust


class TestSharedRfm(FrappeTestCase):
    def test_rfm_assign_extremes(self):
        df = pd.DataFrame({
            "customer": [f"C{i}" for i in range(10)],
            "recency_days": [1, 5, 10, 20, 40, 80, 120, 200, 300, 400],
            "order_count": [50, 40, 30, 20, 10, 8, 6, 4, 2, 1],
            "historical_clv": [1e6, 9e5, 8e5, 7e5, 6e5, 5e5, 4e5, 3e5, 2e5, 1e5],
        })
        out = cust._rfm_assign(df)
        self.assertEqual(out.loc[0, "rfm_score"], "555")
        self.assertEqual(out.loc[0, "rfm_segment"], "Champions")
        self.assertEqual(out.loc[9, "rfm_score"], "111")
        self.assertEqual(out.loc[9, "rfm_segment"], "Lost")

    def test_customer_rfm_reads_the_population_segment(self):
        pop = {"customers": [{"customer": "A", "segment": "Champions", "rfm_score": "555"}]}
        with patch.object(cust, "compute_rfm_segmentation", return_value=pop) as m:
            self.assertEqual(cust._customer_rfm("A", "12m", "Co"), ("Champions", "555"))
            self.assertEqual(cust._customer_rfm("nobody", "12m", "Co"), (None, None))
        m.assert_called_with("12m", "Co")


class TestCustomerLedgerReconciliation(FrappeTestCase):
    def _intel(self):
        payload = cust.compute_customer_intelligence("12m")
        if payload.get("status") != "success":
            self.skipTest("no customer sales on this site")
        return payload

    def _window(self):
        from insights.api.ml.utils import parse_date_filter

        start, end = parse_date_filter("12m")
        return start.date(), end.date()

    def _invoices(self):
        SI = frappe.qb.DocType("Sales Invoice")
        start, end = self._window()
        return SI, (
            (SI.docstatus == 1) & (SI.is_return == 0) & (SI.customer != "")
            & SI.posting_date.between(start, end)
        )

    def test_revenue_is_net_of_tax_and_excludes_returns(self):
        payload = self._intel()
        SI, cond = self._invoices()
        revenue, orders = frappe.qb.from_(SI).select(Sum(SI.base_net_total), Count("*")).where(cond).run()[0]
        self.assertEqual(payload["revenue_basis"], "net_of_tax")
        self.assertAlmostEqual(payload["pareto_analysis"]["total_revenue"], float(revenue or 0), places=1)
        self.assertEqual(sum(c["order_count"] for c in payload["customers"]), orders)

    def test_geography_sums_to_pareto_and_counts_customers_once(self):
        payload = self._intel()
        cov = payload["geographic_analysis"]["coverage"]
        self.assertAlmostEqual(cov["total_revenue"], payload["pareto_analysis"]["total_revenue"], places=1)
        self.assertEqual(cov["total_customers"], len(payload["customers"]))
        territory_total = sum(r["total_revenue"] for r in payload["geographic_analysis"]["territory_analysis"])
        if len(payload["geographic_analysis"]["territory_analysis"]) < 50:
            self.assertAlmostEqual(territory_total, cov["total_revenue"], places=1)

    def test_active_customers_are_distinct_across_orders_and_invoices(self):
        counts = cust.compute_customer_counts("12m")
        cutoff = frappe.utils.add_days(frappe.utils.today(), -counts["active_cutoff_months"] * 30)
        SO = frappe.qb.DocType("Sales Order")
        SI = frappe.qb.DocType("Sales Invoice")
        so = {r[0] for r in frappe.qb.from_(SO).select(SO.customer).where(
            (SO.docstatus == 1) & (SO.transaction_date >= cutoff)).run()}
        si = {r[0] for r in frappe.qb.from_(SI).select(SI.customer).where(
            (SI.docstatus == 1) & (SI.is_return == 0) & (SI.customer != "")
            & (SI.posting_date >= cutoff)).run()}
        self.assertEqual(counts["active"], len(so | si))

    def test_reactivated_bought_in_window_after_a_gap(self):
        start, end = self._window()
        counts = cust.compute_customer_counts("12m")
        gap_start = frappe.utils.add_days(start, -counts["active_cutoff_months"] * 30)
        SI = frappe.qb.DocType("Sales Invoice")
        base = (SI.docstatus == 1) & (SI.is_return == 0) & (SI.customer != "")

        def buyers(cond):
            return {r[0] for r in frappe.qb.from_(SI).select(SI.customer).distinct().where(base & cond).run()}

        in_window = buyers(SI.posting_date.between(start, end))
        reactivated = (
            in_window & buyers(SI.posting_date < gap_start)
        ) - buyers(SI.posting_date.between(gap_start, frappe.utils.add_days(start, -1)))
        self.assertEqual(counts["reactivated"], len(reactivated))
        self.assertEqual(counts["transacting"], len(in_window))

    def test_counts_by_period_reconcile_with_window_counts(self):
        counts = cust.compute_customer_counts("12m")
        for g in ("week", "month"):
            periods = cust.compute_customer_counts_by_period("12m", g)["periods"]
            self.assertEqual(sum(p["new"] for p in periods), counts["new_by_first_txn"])
            for p in periods:
                self.assertEqual(p["buyers"], p["new"] + p["repeat"])
                self.assertLessEqual(p["reactivated"], p["repeat"])

    def test_segmentation_matches_intelligence_rfm(self):
        payload = self._intel()
        seg = cust.compute_rfm_segmentation("12m")
        by_customer = {c["customer"]: c["segment"] for c in seg["customers"]}
        self.assertEqual(
            {c["customer_id"]: c["rfm_segment"] for c in payload["customers"]}, by_customer
        )

    def test_next_best_actions_total_is_true_count(self):
        payload = self._intel()
        self.assertLessEqual(len(payload["next_best_actions"]), 100)
        self.assertGreaterEqual(payload["next_best_actions_total"], len(payload["next_best_actions"]))
