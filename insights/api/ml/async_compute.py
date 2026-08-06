# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Serve expensive dashboard payloads without blocking a web worker.

The intelligence endpoints compute from scratch on a cache miss. Executive
summary measured 23.4s and customer intelligence produces a 1.4MB payload; on a
cold site that runs inside the request and the gateway gives up long before the
work finishes, so the browser sees 502 Bad Gateway.

`serve()` inverts that: it answers from cache when it can, and otherwise hands
the work to a background worker and returns `{"status": "queued"}` immediately.
The client polls `async_status` until the result lands.

Permission is enforced twice on purpose. The calling endpoint checks before
queueing, and the key's required permission is recorded so `async_status` can
re-check it — otherwise polling would be an unauthenticated read of any cached
dashboard by anyone who can guess a key.
"""

from typing import Any, Dict, Optional, Tuple

import frappe

RESULT_KEY = "insights_async:result:{key}"
STATE_KEY = "insights_async:state:{key}"
META_KEY = "insights_async:meta:{key}"

DEFAULT_TTL = 24 * 3600
JOB_TIMEOUT = 3600
# A work-horse that dies (OOM, SIGABRT) never reaches `run`'s finally block, so
# the running flag would otherwise wedge the key until it expired. rq's own
# job_id + deduplicate already prevents genuine double-queueing, so this flag is
# only a cheap short-circuit and can expire well before the job timeout.
STATE_TTL = 900
ERROR_TTL = 300


def _cache():
	return frappe.cache()


def _require(permission: Optional[Tuple[str, str]]):
	if not permission:
		return
	doctype, ptype = permission
	frappe.has_permission(doctype, ptype, throw=True)


def serve(
	key: str,
	method: str,
	kwargs: Optional[Dict[str, Any]] = None,
	permission: Optional[Tuple[str, str]] = None,
	ttl: int = DEFAULT_TTL,
) -> Dict[str, Any]:
	"""Return the cached payload, or queue the work and report `queued`.

	`method` is a dotted path called on a worker; whatever it returns is cached
	verbatim, so it should produce the same envelope the endpoint used to return.
	"""
	cached = _cache().get_value(RESULT_KEY.format(key=key))
	if cached is not None:
		return cached

	if permission:
		_cache().set_value(
			META_KEY.format(key=key),
			{"doctype": permission[0], "ptype": permission[1]},
			expires_in_sec=ttl,
		)

	if _cache().get_value(STATE_KEY.format(key=key)) != "running":
		_cache().set_value(STATE_KEY.format(key=key), "running", expires_in_sec=STATE_TTL)
		frappe.enqueue(
			"insights.api.ml.async_compute.run",
			queue="long",
			timeout=JOB_TIMEOUT,
			job_id=f"insights_async_{key}",
			deduplicate=True,
			key=key,
			# Not `method`: frappe.enqueue's own first parameter is called that,
			# so passing it as a job kwarg raises "already assigned".
			compute_method=method,
			compute_kwargs=kwargs or {},
			ttl=ttl,
		)

	return {"status": "queued", "key": key}


def run(key: str, compute_method: str, compute_kwargs: Dict[str, Any], ttl: int):
	"""Worker entrypoint: compute and cache, then clear the running flag."""
	try:
		result = frappe.get_attr(compute_method)(**(compute_kwargs or {}))
		_cache().set_value(RESULT_KEY.format(key=key), result, expires_in_sec=ttl)
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"insights async compute: {key}")
		# Cache the failure briefly so the client stops polling and sees why,
		# but retries reasonably soon rather than being stuck for the full TTL.
		_cache().set_value(
			RESULT_KEY.format(key=key),
			{"status": "error", "message": str(e)[:500]},
			expires_in_sec=ERROR_TTL,
		)
	finally:
		_cache().delete_value(STATE_KEY.format(key=key))


@frappe.whitelist()
def async_status(key: str) -> Dict[str, Any]:
	"""Poll a queued computation. Re-checks the permission recorded at queue time."""
	if not key or not str(key).strip():
		frappe.throw(frappe._("A key is required."))

	meta = _cache().get_value(META_KEY.format(key=key))
	if isinstance(meta, dict) and meta.get("doctype"):
		_require((meta["doctype"], meta.get("ptype") or "read"))
	else:
		# No recorded permission means the key was never queued through serve();
		# refuse rather than reading arbitrary cache entries.
		frappe.throw(frappe._("Unknown or expired job key."), frappe.PermissionError)

	cached = _cache().get_value(RESULT_KEY.format(key=key))
	if cached is not None:
		return cached
	return {"status": "queued", "key": key}


def invalidate(key: str):
	"""Drop a cached payload so the next request recomputes it."""
	_cache().delete_value(RESULT_KEY.format(key=key))
	_cache().delete_value(STATE_KEY.format(key=key))
