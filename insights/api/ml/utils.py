# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ML API utilities.

``serve_or_warm`` is the main entry point: it returns cached ML results
immediately or enqueues a background training job and returns a
``{status: "warming"}`` placeholder.  The frontend shows a spinner for
the warming state and renders data when it arrives.

Caching is handled by ``BaseMLModel.get_cached_results`` (Redis, 24h TTL)
with ``BaseMLModel.get_last_good_results`` (disk snapshot) as fallback.

Sync fallback
~~~~~~~~~~~~~
On Frappe Cloud the RQ worker uses ``bench worker`` which always forks.
If ``os.fork()`` hits a multi-threaded parent (OpenBLAS, GC threads),
the work-horse dies with signal 11 (SIGSEGV) and the cache stays cold
forever.  After ``SYNC_THRESHOLD`` consecutive warming responses without
data, ``serve_or_warm`` runs the trainer **synchronously in the web
worker** (gunicorn).  Gunicorn workers are already forked from the
master — no second fork happens — so numpy/OpenBLAS loads safely.  The
``@_single_threaded`` decorator on each trainer pins BLAS to one thread
as belt-and-suspenders.

This fallback is **not** a substitute for the Procfile NOFORK fix.  It
is a safety net so dashboards render data while the worker command is
still ``bench worker`` instead of ``bench worker-pool --nofork``.
"""

import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import frappe
from frappe import _


# After this many consecutive warming responses, run the trainer
# synchronously in the web worker instead of enqueuing to RQ.
SYNC_THRESHOLD = 3


def enqueue_training(method: str, job_id: str, label: str, **kwargs) -> Dict[str, Any]:
    """Enqueue an ML training job on the ``long`` queue.

    Uses ``deduplicate=True`` so concurrent dashboard opens collapse onto
    a single job instead of stacking heavy trains that OOM the worker.
    """
    from insights.api.response import success

    frappe.enqueue(
        method,
        queue="long",
        timeout=1500,
        job_id=job_id,
        deduplicate=True,
        **kwargs,
    )
    return success(
        message=_("{0}: training started in the background. Refresh in a few minutes.").format(label)
    )


def _warming_counter_key(job_id: str) -> str:
    return f"insights_ml_warm:{job_id}"


def _increment_warming(job_id: str) -> int:
    """Increment warming counter in Redis; returns new count."""
    try:
        from frappe.utils.background_jobs import get_redis_conn

        conn = get_redis_conn()
        key = _warming_counter_key(job_id)
        raw_count: Any = conn.incr(key)
        count = int(raw_count)
        conn.expire(key, 3600)  # 1-hour TTL — resets naturally
        return count
    except Exception:
        return 0


def _reset_warming(job_id: str) -> None:
    """Reset warming counter after cache is filled."""
    try:
        from frappe.utils.background_jobs import get_redis_conn

        conn = get_redis_conn()
        conn.delete(_warming_counter_key(job_id))
    except Exception:
        pass


def serve_or_warm(
    result: Dict[str, Any],
    trainer: str,
    job_id: str,
    label: str,
    force: bool = False,
) -> Dict[str, Any]:
    """Return a dashboard payload, healing a cold cache on a worker.

    ``result`` comes from ``predict(allow_train=False)``, so it is one of:

    - A warm cache hit (Redis, < 24h old)
    - A stale on-disk snapshot (last successful training, any age)
    - A ``{"status": "warming"}`` placeholder (nothing cached anywhere)

    Flow::

        Cache warm?  → return data, reset warming counter
        Cache cold?  → increment warming counter
                       If counter < SYNC_THRESHOLD → enqueue RQ job, return warming
                       If counter >= SYNC_THRESHOLD → run trainer synchronously
                         Success → return real data, reset counter
                         Failure → return warming, keep counter
    """
    is_warming = isinstance(result, dict) and result.get("status") == "warming"

    # Cache hit — reset the failure counter and return data.
    if not is_warming and not force:
        _reset_warming(job_id)
        return result

    # Cache cold (or forced refresh).  Count consecutive warming responses.
    count = _increment_warming(job_id)

    if count >= SYNC_THRESHOLD:
        # The RQ worker has failed to fill the cache after multiple attempts.
        # Run the trainer synchronously in the web worker (safe — no fork).
        sync_result = _run_sync(trainer, job_id, label)
        if sync_result is not None:
            return sync_result
        # Sync run failed — fall through to enqueue and return warming.

    enqueue_training(trainer, job_id=job_id, label=label)
    return result


def _run_sync(trainer: str, job_id: str, label: str) -> Optional[Dict[str, Any]]:
    """Run the trainer synchronously in the web worker.

    Returns the cached result on success, None on failure.  Resets the
    warming counter so subsequent requests serve from cache.
    """
    try:
        frappe.logger().info(
            f"Sync fallback: running {label} in web worker "
            f"(RQ job {job_id} failed {SYNC_THRESHOLD}+ times)"
        )

        # Import and call the trainer function directly.
        module_path, func_name = trainer.rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        fn = getattr(module, func_name)
        train_result = fn()

        if isinstance(train_result, dict) and train_result.get("status") == "success":
            _reset_warming(job_id)
            frappe.logger().info(
                f"Sync fallback: {label} completed successfully in web worker"
            )
            return train_result

        # Training returned but wasn't successful — still useful data?
        if isinstance(train_result, dict) and train_result.get("status") != "error":
            _reset_warming(job_id)
            return train_result

        frappe.logger().warning(
            f"Sync fallback: {label} returned error: "
            f"{train_result.get('message', 'unknown') if isinstance(train_result, dict) else train_result}"
        )
        return None

    except Exception as e:
        frappe.log_error(
            f"Sync fallback failed for {label}: {e}",
            "ML Sync Fallback",
        )
        return None


def parse_date_filter(date_filter: str = "12m") -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Parse a date filter string into start_date and end_date.

    Supported formats:
    - "3m", "6m", "12m" - months back from now
    - "1y", "2y", "3y"  - years back from now
    - "ytd"              - year to date
    - "all"              - no date filter (returns None, None)

    Returns:
        Tuple of (start_date, end_date) or (None, None) for "all"
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


# A bare SQL identifier.  Anything else in ``date_column``/``alias`` is a
# programming error, and the only route by which this helper could inject.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def get_date_filter_sql(
    date_filter: str = "12m",
    date_column: str = "posting_date",
    alias: str = "",
) -> str:
    """Generate a SQL WHERE-clause fragment for date filtering.

    Returns a string like::

        AND si.posting_date BETWEEN '2025-08-01' AND '2026-08-01'

    Both ``date_column`` and ``alias`` are validated as bare identifiers
    to prevent SQL injection.

    Args:
        date_filter: Duration string (``"3m"``, ``"12m"``, ``"ytd"``, …)
        date_column: Column name to filter on
        alias: Optional table alias (e.g. ``"si"``)

    Returns:
        SQL fragment starting with ``AND`` — returns ``""`` for ``"all"``.
    """
    start_date, end_date = parse_date_filter(date_filter)
    if not start_date or not end_date:
        return ""

    # Validate identifiers to prevent injection.
    if not _IDENTIFIER.match(date_column):
        frappe.throw(f"Invalid date_column identifier: {date_column}")
    if alias and not _IDENTIFIER.match(alias):
        frappe.throw(f"Invalid alias identifier: {alias}")

    date_col = f"{alias}.{date_column}" if alias else date_column
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    return f"AND {date_col} BETWEEN '{start_str}' AND '{end_str}'"
