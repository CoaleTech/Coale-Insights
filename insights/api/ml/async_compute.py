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

import re
from typing import Any, Dict, Optional, Tuple

import frappe

RESULT_KEY = "insights_async:result:{key}"
STATE_KEY = "insights_async:state:{key}"
META_KEY = "insights_async:meta:{key}"

# Queue selection follows Frappe's own contract rather than hardcoding a name.
#
# `frappe.utils.background_jobs.get_queues_timeout()` budgets short=300, default=300,
# long=1500, and merges any custom queues declared in common_site_config.json under
# `workers`. Two constraints follow from that:
#
#   * `default` is wrong. Its workers are provisioned for <=300s work; parking a
#     multi-minute dashboard compute there starves Frappe's own default-queue jobs
#     (emails, notifications, doc events).
#   * bare `long` is wrong too. `insights.ml.scheduler.run_daily_intelligence` lives
#     there, and with one worker per queue a dashboard request lands behind the whole
#     nightly training pass.
#
# So: prefer a dedicated `insights` queue when the operator has declared one, and fall
# back to `long` when they have not. Resolving against the live registry means an
# undeclared queue can never silently swallow jobs — the failure mode that would take
# every dashboard down at once.
PREFERRED_QUEUE = "insights"
FALLBACK_QUEUE = "long"
DEFAULT_TTL = 24 * 3600
# A work-horse that dies (OOM, SIGABRT) never reaches `run`'s finally block, so
# the running flag would otherwise wedge the key until it expired. rq's own
# job_id + deduplicate already prevents genuine double-queueing, so this flag is
# only a cheap short-circuit and can expire well before the job timeout.
STATE_TTL = 900
ERROR_TTL = 300


def resolve_queue() -> str:
	"""The queue to run dashboard computes on, per Frappe's configured registry."""
	from frappe.utils.background_jobs import get_queues_timeout

	try:
		return PREFERRED_QUEUE if PREFERRED_QUEUE in get_queues_timeout() else FALLBACK_QUEUE
	except Exception:
		return FALLBACK_QUEUE


def resolve_timeout() -> int:
	"""Honour the queue's configured budget instead of inventing one."""
	from frappe.utils.background_jobs import get_queues_timeout

	try:
		return int(get_queues_timeout().get(resolve_queue()) or 1500)
	except Exception:
		return 1500
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
			queue=resolve_queue(),
			timeout=resolve_timeout(),
			job_id=_job_name(key),
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


def _job_name(key: str) -> str:
	"""Job id for `key`.

	Only word characters: rq composes its redis keys with ':' separators, so a
	colon in the id does not round-trip and `get_job_status` then fails to find
	the job — which silently disabled failure detection.
	"""
	safe = re.sub(r"\W+", "_", key)
	return f"insights_async_{safe}"


def worker_health() -> Dict[str, Any]:
	"""Are there workers listening on our queue, and how deep is it?"""
	qname = resolve_queue()
	info: Dict[str, Any] = {
		"queue": qname,
		"workers": None,
		"pending": None,
		# Surface whether the operator declared a dedicated queue or we fell back,
		# so `queue_health` answers "is this configured?" and not just "is it busy?".
		"dedicated": qname == PREFERRED_QUEUE,
	}
	try:
		from rq import Worker

		from frappe.utils.background_jobs import get_queue

		queue = get_queue(qname)
		info["pending"] = queue.count
		info["workers"] = Worker.count(queue=queue)
	except Exception as e:
		info["error"] = str(e)[:200]
	return info


def _diagnose(key: str) -> Optional[Dict[str, Any]]:
	"""Explain a missing result, or None when it is legitimately still running.

	A work-horse killed by OOM or a signal never reaches `run`'s handler, so no
	error is ever cached and the client would poll until it times out. rq still
	knows the job failed, so ask it rather than leaving the user guessing.
	"""
	try:
		from frappe.utils.background_jobs import create_job_id, get_job_status

		status = get_job_status(create_job_id(_job_name(key)))
	except Exception:
		return None

	if status == "failed":
		reason = "the background job failed"
		try:
			from frappe.utils.background_jobs import get_queue

			job = get_queue(resolve_queue()).fetch_job(create_job_id(_job_name(key)))
			if job is not None and job.exc_info:
				reason = str(job.exc_info).strip().splitlines()[-1][:300]
		except Exception:
			pass
		# Let the next request re-queue instead of waiting out the flag.
		_cache().delete_value(STATE_KEY.format(key=key))
		return {"status": "error", "message": f"Computation failed on the server: {reason}"}

	if status is None:
		health = worker_health()
		if health.get("workers") == 0:
			_cache().delete_value(STATE_KEY.format(key=key))
			return {
				"status": "error",
				"message": (
					f"No background worker is consuming the '{resolve_queue()}' queue, so this "
					"dashboard cannot be computed. Start the workers (bench worker / supervisor)."
				),
			}

	return None


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

	problem = _diagnose(key)
	if problem:
		return problem

	return {"status": "queued", "key": key}


@frappe.whitelist()
def queue_health() -> Dict[str, Any]:
	"""Operator diagnostic: is the background queue actually being served?"""
	frappe.has_permission("Insights Settings", "read", throw=True)
	return {"status": "success", "data": worker_health()}


def invalidate(key: str):
	"""Drop a cached payload so the next request recomputes it."""
	_cache().delete_value(RESULT_KEY.format(key=key))
	_cache().delete_value(STATE_KEY.format(key=key))
