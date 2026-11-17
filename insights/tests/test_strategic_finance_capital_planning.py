# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Capital planning must read depreciation through the Asset Depreciation Schedule.

Since ERPNext v15 a `Depreciation Schedule` row's `parent` is the Asset
Depreciation Schedule document, not the asset, so joining `parent == Asset.name`
returns nothing: accumulated and upcoming depreciation were always 0. This runs
the real query against the site's schema.

Rows are inserted inside a transaction under a company that does not exist, so
no real data is read, and the transaction is rolled back after every test --
nothing here commits, which is what makes it safe on a site with live data.
"""

from types import SimpleNamespace

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, getdate, nowdate

from insights.ml.strategic_finance.analysis import analyze_capital_planning

COMPANY = "ZZ Insights Capital Planning Test"
PREFIX = "ZZ-TMP-"


class TestCapitalPlanningDepreciation(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.today = getdate(nowdate())
		self.cost_field = (
			"net_purchase_amount" if frappe.db.has_column("Asset", "net_purchase_amount") else "gross_purchase_amount"
		)

	def _asset(self, suffix, status="Submitted", company=COMPANY):
		name = f"{PREFIX}{suffix}"
		frappe.get_doc(
			{
				"doctype": "Asset",
				"name": name,
				"asset_name": name,
				"asset_category": "ZZ Category",
				"company": company,
				"docstatus": 1,
				"status": status,
				"purchase_date": self.today,
				self.cost_field: 1000,
			}
		).db_insert()
		return name

	def _schedule(self, asset, suffix, status, finance_book_id, rows):
		"""rows: [(months from today, amount)]"""
		name = f"{PREFIX}ADS-{suffix}"
		frappe.get_doc(
			{
				"doctype": "Asset Depreciation Schedule",
				"name": name,
				"asset": asset,
				"status": status,
				"finance_book_id": finance_book_id,
				"docstatus": 1,
			}
		).db_insert()
		for idx, (months, amount) in enumerate(rows, start=1):
			frappe.get_doc(
				{
					"doctype": "Depreciation Schedule",
					"name": f"{name}-{idx}",
					"parent": name,
					"parenttype": "Asset Depreciation Schedule",
					"parentfield": "depreciation_schedule",
					"idx": idx,
					"schedule_date": add_months(self.today, months),
					"depreciation_amount": amount,
				}
			).db_insert()

	def _run(self):
		return analyze_capital_planning(
			SimpleNamespace(company=COMPANY, fiscal_year={"start_date": add_months(self.today, -6)})
		)

	def test_depreciation_comes_from_the_active_first_book_schedule(self):
		asset = self._asset("A1")
		self._schedule(asset, "1", "Active", 1, [(-2, 100), (-1, 75), (1, 60), (2, 40)])

		# None of these may be counted: a second finance book, a Draft schedule, a Sold asset
		self._schedule(asset, "2", "Active", 2, [(-1, 999), (1, 999)])
		self._schedule(asset, "3", "Draft", 1, [(-1, 999), (1, 999)])
		sold = self._asset("A2", status="Sold")
		self._schedule(sold, "4", "Active", 1, [(-1, 999), (1, 999)])

		result = self._run()

		self.assertEqual(result["asset_count"], 1)
		self.assertEqual(result["total_accumulated_depreciation"], 175)
		self.assertEqual(result["category_summary"][0]["accumulated_depreciation"], 175)
		self.assertEqual(
			result["upcoming_depreciation"],
			[
				{"period": add_months(self.today, 1).strftime("%Y-%m"), "amount": 60.0},
				{"period": add_months(self.today, 2).strftime("%Y-%m"), "amount": 40.0},
			],
		)

	def test_asset_without_a_schedule_has_no_depreciation(self):
		self._asset("A3")

		result = self._run()

		self.assertEqual(result["asset_count"], 1)
		self.assertEqual(result["total_accumulated_depreciation"], 0)
		self.assertEqual(result["upcoming_depreciation"], [])
