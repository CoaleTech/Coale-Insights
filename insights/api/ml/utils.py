# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ML API utilities — compute-on-request with aggressive caching.

Every intelligence dashboard calls ``compute_or_cache`` which:

1. Returns a Redis-cached result if warm (< 24 h old).
2. Otherwise trains the model **synchronously in the web worker**
   (gunicorn — no fork, so numpy/OpenBLAS loads safely), caches the
   result, and returns it.  First load takes 5-12 s; subsequent loads
   are < 100 ms.

No background jobs.  No RQ.  No fork.  No SIGSEGV.

A Redis lock prevents concurrent training when multiple users open the
same dashboard at once: the first request trains, the rest get a
``{status: "computing"}`` placeholder and refresh to find the cache warm.
"""

import re
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
    """Return cached ML results, or compute them synchronously.

    Args:
        trainer:   Zero-arg callable that trains the model and returns a
                   result dict (e.g. ``lambda: SalesIntelligence(date_filter='12m').train()``).
        cache_key: Redis key for the result (e.g. ``"insights:sales_intelligence:12m"``).
        label:     Human label for log messages (e.g. ``"Sales intelligence"``).

    Returns:
        The model result dict (from cache or freshly computed).
    """
    # 1. Cache hit - fast path.
    cache = frappe.cache()
    cached = cache.get_value(cache_key)  # type: ignore[union-attr]
    if cached and isinstance(cached, dict) and cached.get("status") != "error":
        return cached

    # 2. Another request is already training — return computing placeholder.
    lock_key = f"{cache_key}:lock"
    if cache.get_value(lock_key):  # type: ignore[union-attr]
        return {"status": "warming", "message": _("{0} is being computed. Refresh in a moment.").format(label)}

    # 3. Train synchronously in the web worker.
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
