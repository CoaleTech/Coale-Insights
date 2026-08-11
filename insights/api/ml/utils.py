# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ML API Utilities
Date filter helpers and the background-training entrypoint, shared across all
ML API modules.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import frappe
from frappe import _


def enqueue_training(method: str, job_id: str, label: str, **kwargs) -> Dict[str, Any]:
    """Fit a model on a worker and tell the caller it started.

    Frappe's contract for long work is a background job, and these are the only
    endpoints that fit a model rather than aggregate SQL: a Prophet or
    Holt-Winters pass held inside a gunicorn worker outlives the gateway read
    timeout and reaches the browser as an HTML 502 with no Error Log entry.

    Returns the ordinary `{"status": "success", "message": ...}` envelope, so
    callers need no queued/polling special case.
    """
    from insights.api.response import success

    # A work-horse killed by OOM, SIGSEGV, or a deploy leaves its RQ job STARTED
    # in redis with no worker running it. `deduplicate=True` then silently skips
    # every later enqueue, so the queue stays empty and the dashboard warms
    # forever -- the exact "workers idle, nothing queued" wedge. Delete that
    # corpse first, mirroring migrate._enqueue_once, so this enqueue takes.
    _reap_dead_job(job_id)

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


def _reap_dead_job(job_id: str) -> None:
    """Delete a job wedged STARTED in redis by a killed work-horse.

    A STARTED job that no live worker is running is a corpse: a work-horse
    killed by a signal, OOM, or a deploy never marked it finished. Leaving it
    makes `deduplicate=True` skip every future enqueue for this id. A genuinely
    running job (a live worker owns it) and a still-pending QUEUED job are both
    left untouched, so this never kills real work.
    """
    try:
        from frappe.utils.background_jobs import get_job

        job = get_job(job_id)
    except Exception:
        return
    if not job:
        return
    try:
        if job.get_status(refresh=True) != "started":
            return
        if _job_has_no_live_worker(job):
            job.delete()
    except Exception:
        pass


def _job_has_no_live_worker(job) -> bool:
    """True when no live RQ worker is executing `job` -- i.e. it is a corpse.

    A worker killed by a signal only leaves the worker registry once its
    heartbeat TTL lapses, so a freshly dead job can still look owned; fall back
    to age, since a STARTED job older than its own timeout cannot still be
    running.
    """
    try:
        from frappe.utils.background_jobs import get_redis_conn
        from rq import Worker

        conn = get_redis_conn()
        for worker in Worker.all(connection=conn):
            try:
                if worker.get_current_job_id() == job.id:
                    return False
            except Exception:
                continue
        return True
    except Exception:
        try:
            started = job.started_at
            if not started:
                return True
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - started).total_seconds()
            return age > 1500
        except Exception:
            return False


def serve_or_warm(
    result: Dict[str, Any],
    trainer: str,
    job_id: str,
    label: str,
    force: bool = False,
) -> Dict[str, Any]:
    """Return a dashboard payload, healing a cold cache on a worker.

    `result` comes from `predict(allow_train=False)`, so it is one of: a warm
    cache hit, a stale on-disk snapshot, or a `{"status": "warming"}`
    placeholder -- never a fresh inline training pass. Fitting Prophet or
    Holt-Winters, or running the heavy analytics SQL, inside the gunicorn
    worker outlives the gateway read timeout and reaches the browser as an
    HTML 502; that is the bug this avoids.

    Enqueue the worker-side trainer when the caller forced a refresh or when
    nothing warm exists yet, so opening the dashboard on a cold cache kicks the
    background fit instead of blocking the request. `deduplicate=True` in
    `enqueue_training` collapses concurrent opens onto one job.
    """
    is_warming = isinstance(result, dict) and result.get("status") == "warming"
    if force or is_warming:
        enqueue_training(trainer, job_id=job_id, label=label)
    return result


def parse_date_filter(date_filter: str = "12m") -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Parse a date filter string into start_date and end_date.

    Args:
        date_filter: Filter string like '7d', '30d', '90d', '6m', '12m', '24m', 'all'

    Returns:
        Tuple of (start_date, end_date) where end_date is always today.
        Returns (None, None) for 'all' to indicate no date filtering.

    Raises:
        ValueError: If the filter string has an unrecognised suffix.
    """
    if not date_filter or date_filter == "all":
        return None, None

    end_date = datetime.now()

    if date_filter.endswith("d"):
        days = int(date_filter[:-1])
        start_date = end_date - timedelta(days=days)
    elif date_filter.endswith("m"):
        months = int(date_filter[:-1])
        start_date = end_date - timedelta(days=months * 30)
    elif date_filter.endswith("y"):
        years = int(date_filter[:-1])
        start_date = end_date - timedelta(days=years * 365)
    else:
        # Default to 12 months for unrecognised format
        start_date = end_date - timedelta(days=365)

    return start_date, end_date


# A bare SQL identifier. Anything else in `date_column`/`alias` is a
# programming error, and the only route by which this helper could inject.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def get_date_filter_sql(
    date_filter: str = "12m",
    date_column: str = "posting_date",
    alias: str = "",
) -> str:
    """Generate a SQL WHERE-clause fragment for date filtering.

    Returns an empty string when `date_filter` is 'all' (no filtering required).

    `date_column` and `alias` become SQL identifiers, which cannot be bound as
    parameters, so they are validated against `_IDENTIFIER` and rejected
    otherwise. Every caller in this app passes a literal, so a non-identifier
    means the code is wrong -- not that a user typed something odd. Rejecting is
    the only safe answer: returning "" instead would silently drop the date
    filter and hand back the entire history as though it were the window asked
    for, which is a worse failure than an exception.

    The dates themselves are `strftime` output from datetimes this module
    computed, so they cannot carry a quote and are embedded directly.
    """
    for label, value in (("date_column", date_column), ("alias", alias)):
        if value and not _IDENTIFIER.match(value):
            frappe.throw(
                _("Invalid SQL identifier passed as {0}: {1}").format(label, value),
                frappe.ValidationError,
            )

    start_date, end_date = parse_date_filter(date_filter)
    if start_date is None or end_date is None:
        return ""

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    date_col = f"{alias}.{date_column}" if alias else date_column
    return f"AND {date_col} BETWEEN '{start_str}' AND '{end_str}'"
