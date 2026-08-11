# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Shared helpers for the ML / intelligence API endpoints.

Historically these endpoints fetched rows with `frappe.db.sql`, materialised
them as a pandas DataFrame, and trained a scikit-learn / statsmodels model
in-process on every cold cache -- work slow enough to need a Redis cache, a
background RQ job to fill it, a warming/polling contract with the frontend,
and (on Frappe Cloud) a fork() in the RQ work-horse that reliably crashed
with signal 11. All of that machinery is gone.

Every endpoint below now builds an Ibis expression (see
`insights.api.ml.ibis_source`) that compiles to one SQL statement and
executes inside MariaDB. That is a request the database answers in low
hundreds of milliseconds -- the same latency budget as any other Insights
query -- so it runs synchronously in the web worker, like any other
`@frappe.whitelist()` method. No cache, no background job, no fork.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import frappe

from insights.api.response import error, success


def run(fn: Callable[[], object], label: str) -> dict:
    """Execute `fn` synchronously and wrap the result in the standard
    response envelope. `fn` should return JSON-native data (dicts/lists/
    scalars) -- typically the output of `.execute()` on an Ibis expression,
    reshaped with `.to_dict()`."""
    try:
        return success(data=fn())
    except frappe.PermissionError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Insights ML: {label}")
        return error(str(e), exc=e)


def parse_date_filter(date_filter: str = "12m") -> tuple[datetime | None, datetime | None]:
    """Parse a date filter string into (start_date, end_date).

    Supported: ``"7d"``/``"30d"``/``"90d"`` (days), ``"3m"``-``"24m"``
    (months, x30d), ``"1y"``-``"3y"`` (years, x365d), ``"ytd"``, ``"all"``.
    """
    if not date_filter or date_filter == "all":
        return None, None

    end_date = datetime.now()

    if date_filter == "ytd":
        start_date = datetime(end_date.year, 1, 1)
    elif date_filter.endswith("d") and date_filter[:-1].isdigit():
        start_date = end_date - timedelta(days=int(date_filter[:-1]))
    elif date_filter.endswith("m") and date_filter[:-1].isdigit():
        start_date = end_date - timedelta(days=int(date_filter[:-1]) * 30)
    elif date_filter.endswith("y") and date_filter[:-1].isdigit():
        start_date = end_date - timedelta(days=int(date_filter[:-1]) * 365)
    else:
        start_date = end_date - timedelta(days=365)

    return start_date, end_date
