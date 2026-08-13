# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Crash-safe replacement for `frappe.concurrent_limit`.

Core's decorator hands out tokens from a Redis LIST (`RedisSemaphore`) and
returns them in a `finally` block. gunicorn kills a request that overruns
`-t 120` with SIGKILL, which cannot be caught -- the `finally` never runs,
the token is never returned, and `RedisSemaphore.CAPACITY_TTL` (1 hour,
hardcoded in core) is the only thing that reclaims it. Two such kills at
limit=2 zero the pool and 503 every caller for up to an hour with no load
on the system at all. Confirmed against both call sites that used to carry
`@frappe.concurrent_limit` in this app: `execute_live_query` (every
workbook/chart query) and the ML dashboard computes.

This counts holders in a single Redis INCR'd key instead of a token LIST,
and self-heals within `lease_seconds` of a leak (default: just past the
gateway timeout) instead of inheriting core's 3600s TTL. A leaked slot
over-admits one extra caller for the rest of the lease window rather than
locking every caller out -- fails toward "briefly a bit more load", not
"nobody gets served for an hour".

Only the reject-immediately contract (`wait_timeout=0`) is implemented,
because that is the only mode either caller uses: blocking on a slot would
hold the same web thread it's trying to protect the pool from.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

import frappe

# gunicorn's request timeout plus margin for the kill to land and the
# counter to be observed -- how long a leaked slot can stay stuck for.
_LEASE_SECONDS_DEFAULT = 150


def _default_limit() -> int:
    """Mirror core's `concurrent_limit()` default when the caller doesn't
    pass one, without depending on its private `_default_limit`."""
    try:
        from frappe.concurrency_limiter import gunicorn_max_concurrency

        return max(1, gunicorn_max_concurrency() // 2)
    except Exception:
        return 8


def concurrent_limit_lease(
    limit: int | None = None,
    retry_after: int = 1,
    lease_seconds: int = _LEASE_SECONDS_DEFAULT,
):
    """Decorator: cap simultaneous in-flight calls to the wrapped function.

    Same reject-immediately contract as `frappe.concurrent_limit(wait_timeout=0)`:
    callers over the limit get a `ServiceUnavailableError` (503) with a
    `Retry-After` header instead of queuing. Disengages off-request
    (scheduler, `bench execute`, tests), matching core -- `frappe.local.request`
    is None there and nothing is timing the caller out.
    """

    def decorator(fn: Callable) -> Callable:
        key = f"insights_inflight:{fn.__module__}.{fn.__qualname__}"

        @wraps(fn)
        def wrapper(*args, **kwargs):
            if getattr(frappe.local, "request", None) is None:
                return fn(*args, **kwargs)

            from frappe.utils.background_jobs import get_redis_conn

            _limit = limit if limit is not None else _default_limit()
            conn = get_redis_conn()
            count: int = int(conn.incr(key))  # type: ignore[arg-type]
            ttl: Any = conn.ttl(key)
            if ttl < 0:
                conn.expire(key, lease_seconds)

            if count > _limit:
                conn.decr(key)
                retry = max(1, int(retry_after))
                exc = frappe.exceptions.ServiceUnavailableError(
                    frappe._("Server is busy. Please try again in a few seconds.")
                )
                if (headers := getattr(frappe.local, "response_headers", None)) is not None:
                    headers.set("Retry-After", str(retry))
                raise exc

            try:
                return fn(*args, **kwargs)
            finally:
                conn.decr(key)

        return wrapper

    return decorator
