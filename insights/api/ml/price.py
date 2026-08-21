# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Price Intelligence API Endpoints.

Same shape as the other endpoints in this package: each builds one Ibis
expression, executes it inside MariaDB, and returns the standard envelope via
``insights.api.ml.utils.run``.

``price_forecast`` is deliberately *not* cached. It is called on every keystroke
of a pricing request (debounced 300 ms by the ``price-intelligence`` Desk page)
with a different item each time, so a per-item cache would be mostly misses,
and a stale price band is worse than a slightly slower one: it is the number a
salesperson quotes against. The underlying query is one grouped aggregate over
a year of one item's invoice lines.

``get_price_intelligence`` is the full dashboard payload and does go through
``cached_run``, like every other dashboard mount in this package.
"""

from typing import Any

import frappe

from insights.api.ml.utils import cached_run, run


@frappe.whitelist()
def price_forecast(item_code: str, horizon_days: int = 30) -> dict[str, Any]:
    """Selling-price band for one item.

    Permission is checked against ``Sales Invoice``, not ``Item``: the payload
    is derived entirely from invoiced prices, so read access to the invoices is
    the access that actually matters.
    """
    frappe.has_permission("Sales Invoice", "read", throw=True)
    from insights.ml.price_intelligence import price_forecast as _forecast

    if not item_code:
        frappe.throw(frappe._("An item is required to forecast a price."))

    return run(
        lambda: _forecast(item_code=item_code, horizon_days=int(horizon_days)),
        f"price_forecast:{item_code}",
    )


@frappe.whitelist()
def get_selling_price_intelligence() -> dict[str, Any]:
    """Price Intelligence dashboard payload."""
    frappe.has_permission("Sales Invoice", "read", throw=True)
    from insights.ml.price_intelligence import get_selling_price_intelligence as _payload

    return cached_run(lambda: run(_payload, "selling_price_intelligence"), "selling_price_intelligence")
