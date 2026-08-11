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
"""

import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import frappe
from frappe import _


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

    When the cache is cold or the caller forced a refresh, enqueue the
    trainer on the ``long`` queue so the next page load gets data.
    ``deduplicate=True`` in ``enqueue_training`` collapses concurrent
    opens onto one job.
    """
    is_warming = isinstance(result, dict) and result.get("status") == "warming"
    if force or is_warming:
        enqueue_training(trainer, job_id=job_id, label=label)
    return result


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
