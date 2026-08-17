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

The job computes in its own work-horse process -- the same one RQ already
forks per job for every background task in this app, including Frappe's own
(`insights.insights.doctype.insights_data_source_v3.data_warehouse.
execute_warehouse_table_import` runs ibis/pandas there too, with no extra
isolation layer). This app used to spawn a second, `subprocess.run`-exec'd
interpreter per compute (`insights.api.ml.compute_child`) to route around a
pandas/numpy datetime-conversion segfault; the crash traced to a wheel-ABI
mismatch (unpinned numpy against a pandas cp314 aarch64 build), not to the
work-horse fork itself, and is closed by pinning `pandas`/`numpy`/
`ibis-framework` in `pyproject.toml` plus the PyArrow materialisation escape
hatch (`insights.api.ml.ibis_source.use_pyarrow_materialization`, applied by
`_compute` below) -- so the extra process is gone.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import datetime, timedelta

import frappe
from frappe import _

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

# The last compute attempt per payload: {ts, job_id, fails, error}. Tracked
# here rather than read back out of RQ because the interesting failures leave
# nothing in RQ to read: a work-horse the platform kills (OOM, or a native
# extension fault) never runs an exception handler, and a job left in
# `started` by a dead worker would otherwise deduplicate every retry away for
# as long as it sat there.
_ATTEMPT_KEY = "insights_ml_attempt"

# Longest an attempt may claim to be in flight. One dashboard mount can queue
# nine payloads that wait behind each other on a single worker, and the
# slowest here is a couple of minutes, so this sits far above the honest worst
# case: it exists to break a lock, not to time a compute.
_ATTEMPT_MAX_AGE = 30 * 60
_MAX_ATTEMPTS = 3

# The whole background job's ceiling -- computing a payload runs directly in
# this job now, with nothing else to time out underneath it.
_JOB_TIMEOUT = 1200

# What one dashboard mount asks for. Only used by `warm_all` on a bench where
# nobody has opened a dashboard yet; everywhere else the demand registry is
# the authority, because it carries the filters people actually chose.
_DASHBOARD_ENDPOINTS = (
    "insights.api.ml.financial_intelligence",
    "insights.api.ml.strategic_finance_intelligence",
    "insights.api.ml.sales_intelligence",
    "insights.api.ml.customer_intelligence",
    "insights.api.ml.inventory_intelligence",
    "insights.api.ml.procurement_intelligence",
    "insights.api.ml.risk_intelligence",
    "insights.api.ml.tax_intelligence",
    "insights.api.ml.get_marketing_overview",
    "insights.api.ml.get_hr_overview",
)


def run(fn: Callable[[], object], label: str) -> dict:
    """Execute `fn` synchronously and wrap the result in the standard
    response envelope. `fn` should return JSON-native data (dicts/lists/
    scalars) -- typically the output of `.execute()` on an Ibis expression,
    reshaped with `.to_dict()`."""
    try:
        result = fn()
    except frappe.PermissionError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Insights ML: {label}")
        return error(str(e), exc=e)

    # Several domain classes (Procurement/Inventory/Risk/BreakevenEngine/
    # LeadConversion/GLAnomaly/ProductRecommendations/CrossDashboardSearch/
    # the ML scheduler entry points) catch their own exceptions internally
    # and return ``{"status": "error", "message": ...}`` as an ordinary
    # value instead of raising -- so the `except Exception` above never
    # sees them and this function would otherwise wrap the error dict in
    # `success(data=...)`. That matters beyond cosmetics: `cached_run`
    # decides whether to cache a payload by checking the *outer* envelope's
    # `status`, and its docstring promises "errors are never cached" -- if
    # we always returned `success(data=result)` here, an internally-caught
    # error would look exactly like a good payload to `cached_run`, get
    # cached for the full `CACHE_TTL` (24h), and keep being served to every
    # viewer even after the underlying bug is fixed on disk, since the
    # hourly `refresh_dashboard_caches` recompute hits the same bug and
    # re-caches the same error every time it runs. Recognise the shape and
    # propagate it as a real error instead, so `cached_run` skips caching
    # it, exactly as it does for a raised exception.
    if (
        isinstance(result, dict)
        and result.get("status") == "error"
        and isinstance(result.get("message"), str)
    ):
        return error(result["message"])

    return success(data=result)


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

    # Same pyarrow bypass the child process uses. Inline computes (scheduler,
    # warm_all, bench execute) run in this process, not a child, so the patch
    # has to happen here too.
    from insights.api.ml.ibis_source import use_pyarrow_materialization

    use_pyarrow_materialization()

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
    if cached is not None and not _refresh_requested():
        return cached

    if _refresh_requested():
        # Someone who can see the error and asks anyway gets a fresh retry
        # budget; otherwise one bad compute would disable the button.
        _clear_attempt(key)

    failure = _ensure_compute(key)
    if cached is not None:
        return cached
    return error(failure) if failure else {"status": "warming"}


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


def _ensure_compute(key: str) -> str | None:
    """Make sure a compute for `key` is on its way; report one that wasn't.

    Returns `None` while a payload is genuinely coming, or a message for the
    user when it is not: the last attempt failed and said why, the last
    attempt vanished without saying anything, or there is no worker to run it.
    """
    attempt = frappe.cache.hget(_ATTEMPT_KEY, key)
    attempt = attempt if isinstance(attempt, dict) else {}

    if _attempt_in_flight(attempt):
        return None

    fails = int(attempt.get("fails") or 0)
    failure = attempt.get("error")

    if attempt and not failure:
        # It was recorded as in flight and RQ has no live job for it now, so
        # it died between the two without running its own error handler.
        fails += 1
        failure = _(
            "The background compute for this dashboard stopped without reporting an error"
            " -- its worker process was killed. Check the bench's worker logs."
        )

    if fails >= _MAX_ATTEMPTS:
        return failure

    if _long_queue_is_unattended():
        return _(
            "No background worker is consuming the long queue, so dashboards cannot be"
            " computed. Start the workers, or run"
            " `bench --site SITE execute insights.api.ml.utils.warm_all`."
        )

    _enqueue_current_request(key, fails)
    return None


def _attempt_in_flight(attempt: dict) -> bool:
    """Whether the compute recorded in `attempt` is still coming."""
    if not attempt or attempt.get("error"):
        return False

    if time.time() - float(attempt.get("ts") or 0) > _ATTEMPT_MAX_AGE:
        # RQ holds a job in `started` indefinitely when the worker running it
        # died with it. Take the payload back, and drop the job so the retry
        # is not deduplicated against a corpse.
        _drop_job(attempt.get("job_id"))
        return False

    from frappe.utils.background_jobs import get_job_status
    from rq.job import JobStatus

    return get_job_status(attempt.get("job_id") or "") in (JobStatus.QUEUED, JobStatus.STARTED)


def _long_queue_is_unattended() -> bool:
    """Whether nothing is consuming the queue dashboards are computed on.

    Worth a Redis read on the slow path: with no worker the payload is never
    coming, and every dashboard would sit on "Preparing your dashboard" until
    somebody thought to go and look at the bench.
    """
    try:
        from frappe.utils.background_jobs import get_queue
        from rq import Worker

        queue = get_queue("long")
        return Worker.count(connection=queue.connection, queue=queue) == 0
    except Exception:
        # A diagnostic must never be the reason a dashboard fails to compute.
        frappe.logger("insights").debug("worker check failed", exc_info=True)
        return False


def _record_attempt(key: str, job_id: str, fails: int) -> None:
    frappe.cache.hset(_ATTEMPT_KEY, key, {"ts": time.time(), "job_id": job_id, "fails": fails})


def _record_failure(key: str, message: str) -> None:
    attempt = frappe.cache.hget(_ATTEMPT_KEY, key)
    fails = int(attempt.get("fails") or 0) if isinstance(attempt, dict) else 0
    frappe.cache.hset(_ATTEMPT_KEY, key, {"ts": time.time(), "fails": fails + 1, "error": message})


def _clear_attempt(key: str) -> None:
    frappe.cache.hdel(_ATTEMPT_KEY, key)


def _drop_job(job_id: str | None) -> None:
    """Forget an RQ job so `deduplicate=True` cannot block its replacement."""
    if not job_id:
        return
    try:
        from frappe.utils.background_jobs import get_job

        if job := get_job(job_id):
            job.delete()
    except Exception:
        frappe.logger("insights").debug(f"could not drop job {job_id}", exc_info=True)


def _enqueue_current_request(key: str, fails: int = 0) -> None:
    """Queue the endpoint this request is already calling.

    Taken from `frappe.form_dict.cmd` rather than passed in by each of the
    fifteen call sites: the RPC layer already knows which method it dispatched
    and with what arguments, so there is nothing to keep in sync.
    """
    endpoint = frappe.local.form_dict.get("cmd")
    if not endpoint:
        return
    enqueue_dashboard_compute(endpoint, _endpoint_params(), str(frappe.session.user), key, fails)


def enqueue_dashboard_compute(endpoint: str, params: dict, user: str, key: str, fails: int = 0) -> None:
    """Queue one dashboard compute, at most one in flight per payload.

    The `job_id` covers user and arguments as well as the endpoint: two people
    on the same dashboard, or one person on two date filters, are different
    payloads and must not deduplicate into each other. `key` is that payload's
    cache key, which the job clears on success and marks on failure.
    """
    digest = hashlib.sha1(
        json.dumps([endpoint, params, user], sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    job_id = f"insights_ml_dashboard:{digest}"

    frappe.enqueue(
        "insights.api.ml.utils.compute_dashboard",
        queue="long",
        timeout=_JOB_TIMEOUT,
        deduplicate=True,
        job_id=job_id,
        endpoint=endpoint,
        params=params,
        user=user,
        key=key,
    )

    # After the enqueue, not before: a failed enqueue must not leave a payload
    # looking like it is being computed. A poll that races us in the gap just
    # enqueues again, which `deduplicate` collapses.
    _record_attempt(key, job_id, fails)


def compute_dashboard(
    endpoint: str, params: dict | None = None, user: str | None = None, key: str | None = None
) -> None:
    """Background job: compute one dashboard payload and leave it in the cache.

    Runs the whitelisted endpoint itself, in this job's own work-horse
    process -- RQ already forks one per job, the same isolation every other
    background task in this app (and in stock Insights' own
    `execute_warehouse_table_import`) computes ibis/pandas in directly. The
    endpoint's own `cached_run` call does the actual work and writes the
    cache; this function's job is to run it as the right user and turn a
    raised exception or a non-success envelope into a recorded failure, so a
    compute that dies is reported to whoever is waiting for it instead of
    leaving "Preparing your dashboard" on screen indefinitely.
    """
    user = user or str(frappe.session.user)
    caller = str(frappe.session.user)
    failure = None

    try:
        frappe.set_user(user)
        frappe.local.insights_ml_refresh = True
        result = frappe.call(endpoint, **(params or {}))
        if not (isinstance(result, dict) and result.get("status") == "success"):
            message = result.get("message") if isinstance(result, dict) else None
            failure = message or _("Dashboard compute returned an unexpected response.")
    except Exception as e:
        failure = str(e)
    finally:
        frappe.local.insights_ml_refresh = False
        frappe.set_user(caller)
        frappe.db.commit()

    if not failure:
        if key:
            _clear_attempt(key)
        return

    if key:
        _record_failure(key, failure)
    frappe.log_error(f"Insights ML: {endpoint}", failure)
    raise RuntimeError(f"{endpoint}: {failure}")


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
            live.append((field, entry))

    if stale:
        frappe.cache.hdel(_DEMAND_KEY, stale)

    live.sort(key=lambda pair: pair[1].get("ts", 0), reverse=True)
    for field, entry in live[:_WARM_BATCH]:
        enqueue_dashboard_compute(entry["endpoint"], entry.get("params") or {}, entry["user"], field)


def warm_all(users: str | None = None) -> dict:
    """Compute every dashboard payload people have asked for, in this process.

    The manual way to fill the cache: after a release that flushed Redis, or on
    a bench where the background pass cannot run at all -- no worker, or a
    compute that keeps dying. Off-request, so `cached_run` computes inline:
    no gunicorn timeout, no queue, no child process, nothing to go wrong
    quietly.

        bench --site SITE execute insights.api.ml.utils.warm_all
        bench --site SITE execute insights.api.ml.utils.warm_all --kwargs "{'users': 'a@x.com'}"

    Run it from `bench execute`, never through `frappe.enqueue`: this loop
    calls `frappe.call` off-request per payload, same as `compute_dashboard`
    does inside a queued job -- the only difference is that here nothing is
    consuming a queue on your behalf, so run it by hand when there is no
    worker, or after a release that flushed Redis.

    Payloads are per user (`_scoped`), so what gets warmed is the exact
    (user, endpoint, filter) triples in the demand registry -- what people
    actually opened, including the filters they chose. With `users` given and
    nothing in the registry for them, falls back to the default view of every
    dashboard for those users.
    """
    wanted = [u.strip() for u in (users or "").split(",") if u.strip()]

    queue: list[tuple[str | None, dict]] = []
    for field, entry in (frappe.cache.hgetall(_DEMAND_KEY) or {}).items():
        if not isinstance(entry, dict) or not entry.get("endpoint"):
            continue
        if wanted and entry.get("user") not in wanted:
            continue
        queue.append((field, entry))

    if not queue and wanted:
        queue = [
            (None, {"endpoint": endpoint, "params": {}, "user": user})
            for user in wanted
            for endpoint in _DASHBOARD_ENDPOINTS
        ]

    caller, computed, failed = str(frappe.session.user), [], []
    for field, entry in queue:
        started = time.time()
        record = {"endpoint": entry["endpoint"], "user": entry["user"]}
        try:
            frappe.set_user(entry["user"])
            frappe.local.insights_ml_refresh = True
            result = frappe.call(entry["endpoint"], **(entry.get("params") or {}))
            record["status"] = result.get("status") if isinstance(result, dict) else None
        except Exception as e:
            record["status"] = "error"
            record["error"] = str(e)
        finally:
            frappe.local.insights_ml_refresh = False

        record["seconds"] = round(time.time() - started, 1)
        if record["status"] == "success":
            computed.append(record)
            if field:
                _clear_attempt(field)
        else:
            failed.append(record)
        # `bench execute` prints only the return value, and this runs for
        # minutes: say what is happening while it happens.
        print(f"{record['status']:>8}  {record['seconds']:>6}s  {entry['endpoint']}  {entry['user']}")

    frappe.set_user(caller)
    frappe.db.commit()
    return {"computed": computed, "failed": failed}


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
