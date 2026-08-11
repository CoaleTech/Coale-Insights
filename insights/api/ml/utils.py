# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ML API utilities — compute-on-request with aggressive caching.

Every intelligence dashboard calls ``compute_or_cache`` which:

1. Returns a Redis-cached result if warm (< 24 h old).
2. If cache is cold **and** this is a web request, spawns a daemon thread
   to train in the background and immediately returns
   ``{"status": "warming"}``.  The frontend already handles this state.
3. If cache is cold **and** this is a CLI call (``bench execute``), trains
   synchronously and returns the result.

No RQ.  No fork.  No SIGSEGV.

Why threads, not RQ?  Frappe's RQ worker (``bench worker``) forks each
job via ``os.fork()``.  When numpy/OpenBLAS is loaded in the parent
(via ibis-framework dependency chain), the forked child inherits
corrupted thread state → SIGSEGV (signal 11).  The Procfile NOFORK
fix (``bench worker-pool``) requires Procfile access, which Frappe
Cloud does not expose.  Daemon threads avoid fork entirely.
"""

import re
import threading
from datetime import datetime
from collections.abc import Callable
from typing import Any, Dict, Optional, Tuple

import frappe
from frappe import _


# Redis cache TTL — results are valid for 24 hours.
CACHE_TTL = 86400  # 24 h

# Training lock TTL — prevents concurrent training.  If a train takes
# longer than this, the lock expires and another request can retry.
LOCK_TTL = 300  # 5 min


def compute_or_cache(
    trainer: Callable[[], Dict[str, Any]],
    cache_key: str,
    label: str,
) -> Dict[str, Any]:
    """Return cached ML results, or start background computation.

    Web requests return ``{"status": "warming"}`` immediately and train
    in a daemon thread.  CLI calls (``bench execute``) train synchronously.

    Args:
        trainer:   Zero-arg callable that trains the model and returns a
                   result dict.
        cache_key: Redis key for the result.
        label:     Human label for log messages.
    """
    cache = frappe.cache()

    # 1. Cache hit — fast path (< 1 ms).
    cached = cache.get_value(cache_key)  # type: ignore[union-attr]
    if cached and isinstance(cached, dict) and cached.get("status") != "error":
        return cached

    # 2. Another thread is already training.
    lock_key = f"{cache_key}:lock"
    if cache.get_value(lock_key):  # type: ignore[union-attr]
        return {"status": "warming", "message": _("{0} is being computed. Refresh in a moment.").format(label)}

    # 3. CLI (bench execute) — train synchronously so the caller gets data.
    if not getattr(frappe.local, "request", None):
        return _train_sync(trainer, cache_key, lock_key, label, cache)

    # 4. Web request — train in a background thread, return immediately.
    _train_in_thread(
        trainer, cache_key, lock_key, label,
        site=frappe.local.site,
        sites_path=getattr(frappe.local, "sites_path", None) or ".",
    )
    return {"status": "warming", "message": _("{0} is being computed. Refresh in a moment.").format(label)}


def _train_sync(
    trainer: Callable[[], Dict[str, Any]],
    cache_key: str,
    lock_key: str,
    label: str,
    cache: Any,
) -> Dict[str, Any]:
    """Train synchronously — used by ``bench execute`` and CLI calls."""
    cache.set_value(lock_key, "1", expires_in_sec=LOCK_TTL)  # type: ignore[union-attr]
    try:
        result = trainer()
        if isinstance(result, dict) and result.get("status") != "error":
            cache.set_value(cache_key, result, expires_in_sec=CACHE_TTL)  # type: ignore[union-attr]
        return result
    except Exception as e:
        frappe.log_error(f"ML compute failed for {label}: {e}", "ML Analytics")
        return {"status": "error", "message": str(e)}
    finally:
        cache.delete_value(lock_key)  # type: ignore[union-attr]


def _train_in_thread(
    trainer: Callable[[], Dict[str, Any]],
    cache_key: str,
    lock_key: str,
    label: str,
    site: str,
    sites_path: str | None,
) -> None:
    """Spawn a daemon thread that trains the model and caches the result.

    Each thread gets its own ``frappe.local`` and DB connection — no
    shared state with the web-request thread.  The thread is a daemon so
    it won't prevent gunicorn worker shutdown.
    """

    def _run() -> None:
        try:
            frappe.init(site=site, sites_path=sites_path)
            frappe.connect()

            cache = frappe.cache()
            cache.set_value(lock_key, "1", expires_in_sec=LOCK_TTL)  # type: ignore[union-attr]

            result = trainer()

            if isinstance(result, dict) and result.get("status") != "error":
                cache.set_value(cache_key, result, expires_in_sec=CACHE_TTL)  # type: ignore[union-attr]
                frappe.logger("ML Analytics").info(f"Computed {label} in background thread")

        except Exception:
            frappe.log_error(f"ML background compute failed for {label}", "ML Analytics")
        finally:
            try:
                cache = frappe.cache()
                cache.delete_value(lock_key)  # type: ignore[union-attr]
            except Exception:
                pass
            frappe.destroy()

    thread = threading.Thread(target=_run, daemon=True, name=f"ml-{cache_key}")
    thread.start()


def parse_date_filter(date_filter: str = "12m") -> Tuple[Optional[datetime], Optional[datetime]]:
    """Parse a date filter string into (start_date, end_date).

    Supported: ``"3m"``, ``"6m"``, ``"12m"``, ``"1y"``-``"3y"``, ``"ytd"``, ``"all"``.
    """
    from datetime import timedelta

    if not date_filter or date_filter == "all":
        return None, None

    end_date = datetime.now()

    if date_filter == "ytd":
        start_date = datetime(end_date.year, 1, 1)
    elif date_filter.endswith("m"):
        months = int(date_filter[:-1])
        start_date = end_date - timedelta(days=months * 30)
    elif date_filter.endswith("y"):
        years = int(date_filter[:-1])
        start_date = end_date - timedelta(days=years * 365)
    else:
        start_date = end_date - timedelta(days=365)

    return start_date, end_date


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def get_date_filter_sql(
    date_filter: str = "12m",
    date_column: str = "posting_date",
    alias: str = "",
) -> str:
    """SQL WHERE fragment for date filtering.  Returns ``""`` for ``"all"``."""
    start_date, end_date = parse_date_filter(date_filter)
    if not start_date or not end_date:
        return ""

    if not _IDENTIFIER.match(date_column):
        frappe.throw(f"Invalid date_column identifier: {date_column}")
    if alias and not _IDENTIFIER.match(alias):
        frappe.throw(f"Invalid alias identifier: {alias}")

    date_col = f"{alias}.{date_column}" if alias else date_column
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    return f"AND {date_col} BETWEEN '{start_str}' AND '{end_str}'"
