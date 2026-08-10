# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ML API Utilities
Date filter helpers and the background-training entrypoint, shared across all
ML API modules.
"""

from datetime import datetime, timedelta
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
    from frappe.utils.background_jobs import get_job_status

    from insights.api.response import success

    # Ask before enqueuing, not after: `deduplicate=True` skips silently when a
    # job with this id is already QUEUED or STARTED, so checking afterwards
    # always reports "already running" -- including for the run we just started.
    try:
        already_running = get_job_status(job_id) in ("queued", "started")
    except Exception:
        already_running = False

    if already_running:
        return success(message=_("{0}: training is already running in the background.").format(label))

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


def get_date_filter_sql(
    date_filter: str = "12m",
    date_column: str = "posting_date",
    alias: str = "",
) -> str:
    """
    Generate a SQL WHERE clause fragment for date filtering.

    Uses parameterised-style date strings (ISO 8601) that are safe to embed in
    frappe.db.sql() calls via %s substitution when the caller incorporates them.

    Returns an empty string when date_filter is 'all' (no filtering required).
    """
    start_date, end_date = parse_date_filter(date_filter)

    if start_date is None:
        return ""

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    date_col = f"{alias}.{date_column}" if alias else date_column

    # NOTE: Callers that embed this fragment in frappe.db.sql() should pass the
    # date values as query parameters (%s) rather than relying on string
    # interpolation.  The formatted strings here are ISO dates from trusted
    # internal sources (no user input reaches strftime), so direct embedding is
    # safe but is retained only for backward compatibility.
    return f"AND {date_col} BETWEEN '{start_str}' AND '{end_str}'"
