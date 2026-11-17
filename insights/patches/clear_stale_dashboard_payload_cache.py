# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Drop cached Risk and Strategic Finance payloads built before 2026-11-17.

`cached_run` serves a payload for up to 24 hours, so a site migrated onto this
release would keep showing the old shapes until they age out:

- Risk still carried the India-era `gst_status` block. The page now reads
  `vat_status`, so its VAT / PIN tiles would render empty.
- Strategic Finance still held the capital-planning figures computed with the
  broken depreciation join (accumulated and upcoming depreciation of 0).

Deleting the entries is safe: the next request recomputes, and the hourly pass
keeps them warm afterwards.
"""

import frappe

# One entry per user (`_scoped` appends `::u=<user>`), so match by prefix.
CACHE_KEY_PREFIXES = (
	"insights_ml_risk_intelligence",
	"insights_ml_strategic_finance_intelligence",
)


def execute():
	for prefix in CACHE_KEY_PREFIXES:
		frappe.cache.delete_keys(prefix)
