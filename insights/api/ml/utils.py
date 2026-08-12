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
executes inside MariaDB. Most of these run in low hundreds of milliseconds
and compute fresh on every call, synchronously in the web worker, with no
cache. A handful fan out to several such pipelines in one request (see
`cached_run` below) and are slow enough on a full-size ledger to approach a
gateway/reverse-proxy read timeout -- a cold call that outlives the proxy's
timeout reaches the browser as an empty-bodied HTTP 502, not a Frappe error
envelope. Those wrap their compute in `cached_run` instead of `run`.
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


def cached_run(fn: Callable[[], dict], cache_key: str, ttl: int = 3600) -> dict:
    """Read-through Redis cache around a whitelisted endpoint's full response.

    `fn` must return the final response dict already in the standard
    envelope (e.g. the output of `run(...)`, or any dict carrying a
    top-level `"status"` key) -- this does not wrap it again, so it composes
    with either `run()`-based endpoints or ones that build their own
    envelope (e.g. `sanitize_for_json(some_model.train())`).

    Call `frappe.has_permission(...)` *before* calling this, not inside
    `fn` -- a cache hit must still be gated by a fresh permission check on
    every request; only the expensive compute is skipped.

    A cache hit returns instantly. A miss computes `fn()` inline (still no
    background job, no fork) and, only on `"status": "success"`, caches the
    result for `ttl` seconds. Errors are never cached: a transient failure
    retries fresh on the next request instead of serving (or locking in) an
    error for the full TTL. See `insights.ml.executive_intelligence.
    get_executive_summary` for the ~60s fan-out that first surfaced this
    class of bug as a production 502.
    """
    cached = frappe.cache.get_value(cache_key)
    if cached is not None:
        return cached
    result = fn()
    if isinstance(result, dict) and result.get("status") == "success":
        frappe.cache.set_value(cache_key, result, expires_in_sec=ttl)
    return result


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
