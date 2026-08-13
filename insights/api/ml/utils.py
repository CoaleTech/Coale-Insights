# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Shared helpers for the ML / intelligence API endpoints.

Every endpoint builds an Ibis expression (see `insights.api.ml.ibis_source`)
that compiles to one SQL statement and executes inside MariaDB. Most of them
run in low hundreds of milliseconds and answer straight out of the web
worker with no cache at all.

A handful fan out to dozens of those pipelines to assemble one dashboard
payload, and take tens of seconds on a full ledger. Those go through
`cached_run`, which follows the ordinary Frappe contract for work that does
not fit inside a request: the web worker only ever *reads* the cache, a miss
enqueues a background job (`frappe.enqueue`, deduplicated by `job_id`) and
answers `{"status": "warming"}` -- a shape the frontend already understands
and polls on (`helpers/api.readInsightsEnvelope`,
`useIntelligenceDashboard`). `refresh_dashboard_caches`, an hourly scheduler
event, recomputes whatever people actually opened, so in steady state a user
request never computes anything.

This replaces computing inline in the web worker under a concurrency cap.
That design failed in both directions on a cold cache: callers past the cap
got an immediate 503 (`ServiceUnavailableError: Server is busy`), and a
compute that outran gunicorn's `-t 120` was SIGKILLed into an empty-bodied
502 with the cache still unwritten -- so the next request repeated it, for
every dashboard, forever.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import datetime, timedelta

import frappe

from insights.api.response import error, success

# How long a computed payload stays servable. `refresh_dashboard_caches`
# rewrites it every hour, so this is only the backstop for a bench whose
# scheduler is paused -- deliberately far longer than the refresh interval,
# because serving a payload a few hours old beats making someone wait for a
# 30s compute.
CACHE_TTL = 24 * 3600

# What to keep warm: scoped cache key -> {endpoint, params, user, ts}. One
# entry per (user, endpoint, filter) that someone has actually opened.
_DEMAND_KEY = "insights_ml_demand"
_DEMAND_MAX_AGE = 3 * 86400
_WARM_BATCH = 40


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


def _in_request() -> bool:
    """True inside a web request.

    Off-request -- background job, scheduler, `bench execute`, tests --
    nothing is timing the caller out and there is no worker pool to protect,
    so the compute runs inline. This is also what stops `compute_dashboard`
    from recursing: the job calls the same endpoint, which takes this branch
    and computes instead of enqueueing itself again.
    """
    return getattr(frappe.local, "request", None) is not None


def _refresh_requested() -> bool:
    """Whether this call was asked to recompute rather than take what is cached.

    Set on `frappe.local` by `compute_dashboard` for the background pass, and
    by the dashboards' own Refresh button, which sends `refresh=1`. The button
    used to be accepted and then quietly ignored -- endpoints forward it into
    their compute, but `cached_run` returned the cached payload before the
    compute ever ran, so Refresh was a no-op for the full TTL.
    """
    if getattr(frappe.local, "insights_ml_refresh", False):
        return True
    if not _in_request():
        return False
    return str(frappe.local.form_dict.get("refresh", "")).lower() in ("1", "true", "yes")


def _endpoint_params() -> dict:
    """The current RPC call's own arguments, minus the transport's fields.

    `refresh` is dropped on purpose: it describes one click, not the payload,
    and the background pass forces a recompute anyway.
    """
    skip = {"cmd", "csrf_token", "refresh", "_"}
    return {k: v for k, v in frappe.local.form_dict.items() if k not in skip}


# `threadpool_limits(1)` pins every native thread pool BLAS/OpenMP hands out
# for this call (OpenBLAS, MKL, the sklearn/scipy OpenMP pool) to one thread.
# The Procfile already pins the RQ workers via the environment, but the
# scheduler and `bench execute` do not, and an unpinned OpenBLAS pool per
# compute oversubscribes the host's cores under concurrent load -- both a
# slowdown and a known OpenBLAS crash surface. Verified locally: pinning made
# sales and customer intelligence *faster*, not slower (35.2s -> 26.2s,
# 6.7s -> 5.0s) -- these are groupby/window bound, not matrix-multiply bound,
# so multi-threaded BLAS was pure coordination overhead here.
def _compute(fn: Callable[[], dict]) -> dict:
    import threadpoolctl

    with threadpoolctl.threadpool_limits(1):
        return fn()


def cached_run(fn: Callable[[], dict], cache_key: str, ttl: int = CACHE_TTL) -> dict:
    """Serve a dashboard payload from cache, computing it in a background job.

    `fn` must return the final response dict already in the standard envelope
    (e.g. the output of `run(...)`, or any dict carrying a top-level
    `"status"` key) -- this does not wrap it again.

    Call `frappe.has_permission(...)` *before* calling this, not inside `fn`
    -- a cache hit must still be gated by a fresh permission check on every
    request. That check answers "may you call this endpoint", which is not
    the same question as "whose rows are in this payload"; `_scoped` answers
    the second, and the background job recomputes as the same user so the two
    stay in agreement.

    Errors are never cached: a transient failure retries fresh on the next
    pass instead of locking in an error for the full TTL.
    """
    key = _scoped(cache_key)

    if not _in_request():
        # A background job, the scheduler or `bench execute`. Nothing is timing
        # this out, so compute inline -- this is the only branch that ever runs
        # `fn`, and the only one that writes the cache.
        if not _refresh_requested():
            cached = frappe.cache.get_value(key)
            if cached is not None:
                return cached

        result = _compute(fn)
        if isinstance(result, dict) and result.get("status") == "success":
            frappe.cache.set_value(key, result, expires_in_sec=ttl)
        return result

    _record_demand(key)
    cached = frappe.cache.get_value(key)

    # Refresh keeps serving the payload it has while the new one is computed:
    # returning `warming` instead would blank a dashboard the user is looking
    # at, and -- because every poll would carry `refresh` again -- would never
    # stop asking for a fresh compute.
    if cached is None or _refresh_requested():
        _enqueue_current_request()

    return cached if cached is not None else {"status": "warming"}


def is_cached(cache_key: str) -> bool:
    """Whether `cached_run` can answer `cache_key` for the caller right now,
    without waiting on a background compute."""
    return frappe.cache.get_value(_scoped(cache_key)) is not None


def _record_demand(key: str) -> None:
    """Note that someone opened this dashboard, so the hourly pass knows it is
    worth recomputing. Recorded on hits too, so a dashboard in daily use never
    ages out of the registry."""
    if not _in_request():
        return

    endpoint = frappe.local.form_dict.get("cmd")
    if not endpoint:
        return

    frappe.cache.hset(
        _DEMAND_KEY,
        key,
        {
            "endpoint": endpoint,
            "params": _endpoint_params(),
            "user": frappe.session.user,
            "ts": time.time(),
        },
    )


def _enqueue_current_request() -> None:
    """Queue the endpoint this request is already calling.

    Taken from `frappe.form_dict.cmd` rather than passed in by each of the
    fifteen call sites: the RPC layer already knows which method it dispatched
    and with what arguments, so there is nothing to keep in sync.
    """
    endpoint = frappe.local.form_dict.get("cmd")
    if not endpoint:
        return
    enqueue_dashboard_compute(endpoint, _endpoint_params(), str(frappe.session.user))


def enqueue_dashboard_compute(endpoint: str, params: dict, user: str) -> None:
    """Queue one dashboard compute, at most one in flight per payload.

    The `job_id` covers user and arguments as well as the endpoint: two people
    on the same dashboard, or one person on two date filters, are different
    payloads and must not deduplicate into each other.
    """
    digest = hashlib.sha1(
        json.dumps([endpoint, params, user], sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    frappe.enqueue(
        "insights.api.ml.utils.compute_dashboard",
        queue="long",
        timeout=1200,
        deduplicate=True,
        job_id=f"insights_ml_dashboard:{digest}",
        endpoint=endpoint,
        params=params,
        user=user,
    )


def compute_dashboard(endpoint: str, params: dict | None = None, user: str | None = None) -> None:
    """Background job: compute one dashboard payload and leave it in the cache.

    Runs the whitelisted endpoint itself rather than a copy of its body, so
    there is one definition of what a dashboard returns. Permissions are
    enforced normally, as the user the payload is cached for.
    """
    if user and user != frappe.session.user:
        frappe.set_user(user)

    frappe.local.insights_ml_refresh = True
    frappe.call(endpoint, **(params or {}))


def refresh_dashboard_caches() -> None:
    """Hourly scheduler event: recompute the dashboards people actually use.

    In steady state this is the only thing that computes a dashboard at all --
    every user request finds the payload already cached. Entries nobody has
    opened in `_DEMAND_MAX_AGE` are dropped, so the background load tracks
    real usage instead of growing forever.
    """
    demand = frappe.cache.hgetall(_DEMAND_KEY) or {}
    if not demand:
        return

    cutoff = time.time() - _DEMAND_MAX_AGE
    stale, live = [], []
    for field, entry in demand.items():
        if not isinstance(entry, dict) or not entry.get("endpoint") or entry.get("ts", 0) < cutoff:
            stale.append(field)
        else:
            live.append(entry)

    if stale:
        frappe.cache.hdel(_DEMAND_KEY, stale)

    live.sort(key=lambda e: e.get("ts", 0), reverse=True)
    for entry in live[:_WARM_BATCH]:
        enqueue_dashboard_compute(entry["endpoint"], entry.get("params") or {}, entry["user"])


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
