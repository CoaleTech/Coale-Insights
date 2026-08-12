# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Off-request cache warming for the intelligence dashboards.

A cold dashboard endpoint costs tens of seconds against a ledger this size,
and gunicorn runs with `-t 120` behind `proxy_read_timeout 120`. A cold
compute that overruns that is killed mid-flight: the browser gets an
empty-bodied 502 *and* nothing is written to the cache, so the next request
starts from cold and repeats it. The cache cannot be filled by the only path
that ever asks for it.

This module is the path that can. It runs the very same whitelisted endpoint,
as the very same user, from a worker -- where `insights.api.ml.utils
._off_request()` is true, so `cached_run` computes inline and stores the
result instead of deferring again. No second implementation to drift out of
sync with the endpoints, and the payload is filtered by that user's own
permissions, matching the key it is stored under.
"""

from __future__ import annotations

import frappe


def warm_key(endpoint: str, kwargs: dict, lock: str) -> None:
    """Compute one dashboard payload and leave it in the cache.

    Enqueued by `insights.api.ml.utils._request_warm`. `endpoint` is the
    dotted path of the whitelisted function and `kwargs` reproduces the call
    that missed -- those arguments are part of the cache key, so warming the
    defaults would leave every other filter cold and polling forever.

    The user is not a parameter: `frappe.enqueue` records the requesting
    session's user and `execute_job` restores it before calling this, so the
    endpoint re-derives the same per-user key it was asked for.
    """
    try:
        frappe.get_attr(endpoint)(**(kwargs or {}))
    except frappe.PermissionError:
        # Access was lost between asking and being served. Nothing to warm,
        # and nothing worth raising to Error Log over.
        pass
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Insights ML: warming {endpoint}")
    finally:
        # Release even on failure, so the next request re-enqueues rather
        # than waiting out the lock's full TTL.
        frappe.cache.delete_value(lock)
