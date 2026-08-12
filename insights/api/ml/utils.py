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

import time
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


def _off_request() -> bool:
    """True when no reverse proxy is waiting on this call.

    The scheduler, a background job, `bench execute` and the test runner all
    reach these endpoints with `frappe.local.request` unset. Those callers
    have no gateway read timeout over them, so they -- and only they -- may
    pay the cold compute.
    """
    return getattr(frappe.local, "request", None) is None


def cached_run(
    fn: Callable[[], dict],
    cache_key: str,
    ttl: int = 3600,
    *,
    warm: tuple[str, dict] | None = None,
) -> dict:
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

    A hit returns instantly. On a miss the caller decides who pays:

    * Off-request (scheduler, background job, CLI, tests) -- compute inline
      and cache the result. Nothing is timing this caller out.
    * In a web request -- a cold compute here is measured in tens of seconds
      and gunicorn is started with `-t 120` behind `proxy_read_timeout 120`.
      Exceeding that kills the worker mid-compute, so the browser gets an
      empty-bodied 502 *and* the cache is never written -- the next request
      repeats it, forever. A cache that can only be filled by a request that
      dies before filling it never populates. So when `warm` names the
      endpoint that can refill this key, hand the work to a job that has no
      gateway over it and answer `{"status": "warming"}`, which the frontend
      already renders as "Preparing your dashboard" and re-polls.

    `warm` is `(dotted_path, kwargs)` reproducing *this* call -- the params
    are part of the key, so warming defaults would leave any other filter
    cold and polling forever. Omitting `warm` keeps the old inline
    behaviour, so a call site that has not opted in cannot strand a client.

    Errors are never cached: a transient failure retries fresh on the next
    request instead of serving (or locking in) an error for the full TTL.
    """
    key = _scoped(cache_key)
    cached = frappe.cache.get_value(key)
    if cached is not None:
        return cached

    if warm is not None and not _off_request() and _worth_waiting(key):
        _request_warm(key, warm)
        return {"status": "warming"}

    result = fn()
    if isinstance(result, dict) and result.get("status") == "success":
        frappe.cache.set_value(key, result, expires_in_sec=ttl)
    return result


# A warm job that segfaults, is never picked up, or dies mid-compute must not
# strand the client on a spinner forever. Once a key has been warming this
# long without filling, the next request pays inline instead. That may still
# outrun the gateway and 502 -- exactly today's behaviour -- but it is only
# reached once warming has demonstrably failed, so a broken worker degrades
# the dashboard instead of removing it.
#
# Measured against the JKM ledger, the slowest of these endpoints computes
# cold in ~24s with no gateway over it, so this leaves a wide margin for a
# loaded host before assuming the job is lost.
_WARM_PATIENCE_SECS = 180

# Cleared when the job finishes. If the work-horse dies without running the
# `finally`, this expiring on its own is what lets a later request re-enqueue.
_WARM_LOCK_TTL = 900


def _worth_waiting(key: str) -> bool:
    """False once this key has been warming longer than we are willing to wait.

    Timed from the first cold miss rather than counted in polls: the browser
    stops polling when the tab is backgrounded, and a poll count would then
    measure how long the dashboard was *watched* instead of how long the job
    has had.
    """
    since = f"{key}::since"
    try:
        first = frappe.cache.get_value(since)
        if first is None:
            frappe.cache.set_value(since, time.time(), expires_in_sec=_WARM_LOCK_TTL)
            return True
        return (time.time() - float(first)) < _WARM_PATIENCE_SECS
    except Exception:
        # Never let the cache's own failure mode block the dashboard: fall
        # through to computing inline, which is what happens without `warm`.
        return False


def _request_warm(key: str, warm: tuple[str, dict]) -> None:
    """Hand this key's compute to a worker, at most one job per key in flight.

    The lock is what makes this safe to call from every poll: the frontend
    re-asks every 4s while warming, and each of those is a fresh cold miss.
    `deduplicate` covers the queue, the lock covers the window before the
    job is visible to it.
    """
    endpoint, kwargs = warm
    lock = f"{key}::warming"
    if frappe.cache.get_value(lock):
        return

    frappe.cache.set_value(lock, 1, expires_in_sec=_WARM_LOCK_TTL)
    try:
        frappe.enqueue(
            "insights.api.ml.warm.warm_key",
            queue="long",
            timeout=1800,
            job_id=f"insights_ml_warm::{key}",
            deduplicate=True,
            # `enqueue`'s own first parameter is `method`, so the endpoint to
            # warm has to travel under a name that does not collide with it.
            endpoint=endpoint,
            kwargs=kwargs,
            lock=lock,
            # `user` is not passed: `enqueue` already records the calling
            # session's user and `execute_job` restores it before dispatch,
            # so the job re-derives the very same `_scoped` key.
        )
    except Exception:
        # Never leave the lock held for a job that was not queued.
        frappe.cache.delete_value(lock)
        frappe.log_error(frappe.get_traceback(), "Insights ML: warm enqueue failed")


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
