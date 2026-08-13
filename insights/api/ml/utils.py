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
envelope. Those wrap their compute in `cached_run` instead of `run`, which
caches the response and caps how many such computes run at once.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import frappe

from insights.api.response import error, success
from insights.concurrency_lease import concurrent_limit_lease


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


def _scoped(cache_key: str) -> str:
    """Cache keys are per-user.

    `insights.api.ml.permissions.permitted()` filters rows out of every read
    according to the caller's User Permissions, so two users can compute
    materially different payloads from byte-identical arguments -- on this
    ledger a salesperson scoped to their own invoices totals 6.7M where a
    manager totals 182M. A cache keyed only on the arguments hands whichever
    figure landed first to everyone who asks next, in both directions: the
    salesperson reads the manager's ledger, and the manager reads a number
    that is quietly 27x too small. The row filter is only a boundary if the
    cache in front of it keeps the same shape.
    """
    return f"{cache_key}::u={frappe.session.user}"


# Standard Insights caps live-query concurrency exactly this way (see
# `ibis_utils._execute_live_query`): reject immediately instead of waiting for a
# slot, because a request blocked on a semaphore still holds a web thread, and
# holding threads is what starves the pool when several heavy dashboards land at
# once -- which is how one slow endpoint took the cheap ones down with it.
# Rejected callers retry client-side.
#
# The limiter disengages off-request (scheduler, `bench execute`, tests), where
# `frappe.local.request` is None and nothing is timing the caller out.
#
# `limit` is set rather than left to default. The default is derived from
# gunicorn's worker count, which measures how many *cheap* requests can be in
# flight; these computes are three orders of magnitude slower, so that number is
# the wrong denominator -- on this bench it would allow 16. What bounds it is the
# gateway: gunicorn runs `-t 120` behind `proxy_read_timeout 120`, and a compute
# killed at 120s returns an empty-bodied 502 *and* leaves the cache unwritten, so
# the next request repeats it forever. Measured cold against the JKM ledger as a
# row-filtered (non-Administrator) user: 46s alone, 65s with two in flight. Two
# therefore keeps ~55s of headroom; three would start spending it.
#
# Uses the insights-local lease-based limiter, not `frappe.concurrent_limit`:
# core's version leaks a token on every gunicorn SIGKILL (see
# `insights.concurrency_lease` for why) and this endpoint is exactly the kind
# of compute that gets killed at 120s.
#
# `threadpool_limits(1)` pins every native thread pool BLAS/OpenMP hands out
# for this call (OpenBLAS, MKL, the sklearn/scipy OpenMP pool) to one thread.
# These computes used to run inside the RQ worker, which pins
# `OPENBLAS_NUM_THREADS=1` etc. via the Procfile -- but the Ibis rewrite made
# them synchronous, so they now run inside gunicorn, which has no such
# pinning. gunicorn runs many worker processes (33 on this bench); each one
# spawning an unpinned OpenBLAS thread pool per compute oversubscribes the
# host's cores under concurrent load, which both slows every compute down
# and is a known OpenBLAS crash surface -- indistinguishable from this
# app's history of fork-related segfaults, but this path never forks.
# Verified locally: pinning made both sales and customer intelligence
# *faster*, not slower (35.2s -> 26.2s, 6.7s -> 5.0s, Administrator/full
# dataset) -- these are groupby/rolling-window bound, not matrix-multiply
# bound, so multi-threaded BLAS was pure coordination overhead here.
@concurrent_limit_lease(limit=2)
def _compute(fn: Callable[[], dict]) -> dict:
    import threadpoolctl

    with threadpoolctl.threadpool_limits(1):
        return fn()


def cached_run(fn: Callable[[], dict], cache_key: str, ttl: int = 3600) -> dict:
    """Read-through Redis cache around a whitelisted endpoint's full response.

    `fn` must return the final response dict already in the standard
    envelope (e.g. the output of `run(...)`, or any dict carrying a
    top-level `"status"` key) -- this does not wrap it again, so it composes
    with either `run()`-based endpoints or ones that build their own
    envelope (e.g. `sanitize_for_json(some_model.train())`).

    Call `frappe.has_permission(...)` *before* calling this, not inside
    `fn` -- a cache hit must still be gated by a fresh permission check on
    every request. That check answers "may you call this endpoint", which is
    not the same question as "whose rows are in this payload"; `_scoped`
    answers the second.

    Errors are never cached: a transient failure retries fresh on the next
    request instead of serving (or locking in) an error for the full TTL.
    """
    key = _scoped(cache_key)
    cached = frappe.cache.get_value(key)
    if cached is not None:
        return cached

    result = _compute(fn)
    if isinstance(result, dict) and result.get("status") == "success":
        frappe.cache.set_value(key, result, expires_in_sec=ttl)
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
