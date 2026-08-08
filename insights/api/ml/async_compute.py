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
import os

# BLAS fork-safety: rq forks a work-horse for every job, and Apple's Accelerate
# (numpy's BLAS on macOS) is not fork-safe — its thread pools corrupt in the child,
# causing SIGSEGV on the first BLAS call. Pin every BLAS backend to a single thread
# before numpy is imported, so no thread pools are created for fork to inherit.
# On Linux with OpenBLAS/MKL the same env vars prevent the same class of crash.
# This is belt-and-braces with the Procfile; the Procfile covers `bench worker`
# and supervisor, this covers any path that imports this module first.
for _v in ("VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
	os.environ.setdefault(_v, "1")

import re
from typing import Any, Dict, Optional, Tuple

import frappe
from frappe import _

RESULT_KEY = "insights_async:result:{key}"
STATE_KEY = "insights_async:state:{key}"
META_KEY = "insights_async:meta:{key}"
ATTEMPT_KEY = "insights_async:attempts:{key}"
# A work-horse killed by a signal never reaches `run`'s except/finally, so no error
# is ever cached and the client's retry queues another one. Count enqueues instead,
# and clear the count on the first success: under normal operation a key goes 1 ->
# cleared, so only a genuinely crashing computation ever reaches the ceiling.
MAX_ATTEMPTS = 3
ATTEMPT_TTL = 900

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

# Permission required to read each cached payload, keyed by the prefix before the
# first ':' in the cache key.
#
# This used to live *only* in a Redis META entry written by `serve()`. That made a
# key's permission ephemeral: any path that filled RESULT without going through
# `serve()` -- notably the scheduler's `warm_dashboard_caches`, which calls `run()`
# directly -- left a perfectly good payload that `async_status` then refused with
# "Unknown or expired job key". The same happened once META's TTL lapsed while the
# daily warm kept RESULT fresh indefinitely.
#
# Which doctype guards a dashboard is a static property of that dashboard, not
# cache state, so it belongs in code. META is still honoured as a fallback for keys
# an extension may register at runtime.
KEY_PERMISSIONS = {
	"sales_intelligence": ("Sales Invoice", "read"),
	"customer_intelligence": ("Customer", "read"),
	"executive_summary": ("Sales Invoice", "read"),
	"procurement_intelligence": ("Purchase Order", "read"),
}
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


def _attempts(key: str) -> int:
	try:
		return int(_cache().get_value(ATTEMPT_KEY.format(key=key)) or 0)
	except (TypeError, ValueError):
		return 0


def _bump_attempts(key: str) -> int:
	count = _attempts(key) + 1
	_cache().set_value(ATTEMPT_KEY.format(key=key), count, expires_in_sec=ATTEMPT_TTL)
	return count


def clear_attempts(key: str):
	_cache().delete_value(ATTEMPT_KEY.format(key=key))


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

	deaths = _attempts(key)
	if deaths >= MAX_ATTEMPTS:
		# The work-horse keeps dying without ever reaching `run`'s handler -- a
		# native crash (SIGSEGV/OOM) rather than a Python exception, so nothing
		# was cached and every retry queues another one. Park a terminal error so
		# the page stops thrashing the worker pool.
		terminal = {
			"status": "error",
			"message": _(
				"This dashboard's computation crashed the background worker {0} times "
				"(no Python error -- the process was killed). It will not be retried for "
				"a few minutes. Check the worker log for a segfault or out-of-memory kill."
			).format(deaths),
		}
		_cache().set_value(RESULT_KEY.format(key=key), terminal, expires_in_sec=ERROR_TTL)
		_cache().delete_value(STATE_KEY.format(key=key))
		return terminal

	if _cache().get_value(STATE_KEY.format(key=key)) != "running":
		# A job wedged in STARTED/QUEUED makes `deduplicate=True` return without
		# enqueueing anything, silently. Clear the corpse first.
		_reap_dead_job(key)

		_bump_attempts(key)
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

		# `frappe.enqueue` returns None when deduplication skipped it. If no job
		# exists afterwards, nothing is going to compute this key and the client
		# would poll into the void for the full 5 minutes. Say so instead.
		if _job_status(key) is None:
			_cache().delete_value(STATE_KEY.format(key=key))
			return {
				"status": "error",
				"message": _(
					"Could not queue the computation for this dashboard. "
					"Check that background workers are running and the queue is reachable."
				),
			}

	return {"status": "queued", "key": key}


def _job_status(key: str):
	"""rq status for this key's job, or None when no job exists."""
	try:
		from frappe.utils.background_jobs import get_job_status

		return get_job_status(_job_name(key))
	except Exception:
		return None


def _live_worker_names() -> set:
	try:
		from rq import Worker

		from frappe.utils.background_jobs import get_redis_conn

		return {w.name for w in Worker.all(connection=get_redis_conn())}
	except Exception:
		return set()


def reap_dead_job(job_id: str, queue_name: Optional[str] = None) -> bool:
	"""Delete a job whose worker is gone so a fresh one can be enqueued.

	rq keeps a STARTED job in redis when its work-horse dies without unwinding
	(OOM kill, supervisor restart, deploy). `frappe.enqueue(deduplicate=True)`
	then refuses to queue a replacement -- it returns silently -- so that job id
	can never run again until the job's own TTL lapses. Ask rq to run its own
	registry maintenance first, then delete anything still claiming to run on a
	worker that no longer exists.

	Takes a raw job id so callers outside this module (the migrate hook) can
	protect their own long-lived, deduplicated jobs the same way.
	"""
	try:
		from rq.job import JobStatus

		from frappe.utils.background_jobs import get_job, get_queue

		queue = get_queue(queue_name or resolve_queue())
		# rq's own reaper: moves started jobs past their heartbeat into failed.
		try:
			queue.started_job_registry.cleanup()
		except Exception:
			pass

		job = get_job(job_id)
		if job is None:
			return False

		status = job.get_status(refresh=True)
		if status == JobStatus.STARTED and job.worker_name not in _live_worker_names():
			job.delete()
			return True
	except Exception:
		return False
	return False


def _reap_dead_job(key: str) -> bool:
	"""Reap the job backing a cache key."""
	return reap_dead_job(_job_name(key))


MEMORY_KEY = "insights_async:memory:{key}"


def _sample_memory(conn, redis_key: bytes, stop):
	"""Record this process's RSS every second until told to stop.

	The work-horse is the process that dies, but a signal leaves nothing behind
	to inspect. Writing its own RSS to redis as it runs means a later crash can
	report how far memory had climbed -- the one measurement that separates an
	out-of-memory death from a native fork/BLAS fault. `_record_crash_forensics`
	previously reported `RUSAGE_SELF` from the *web* process handling the poll,
	which describes an entirely different process.

	Takes an already-resolved connection and key: `frappe.local` is thread-local,
	so calling `frappe.cache()` in here silently fails to find a site and the
	thread dies on its first tick.
	"""
	import resource
	import sys

	divisor = 1024 * 1024 if sys.platform == "darwin" else 1024  # macOS bytes, Linux KB
	peak = 0.0
	while not stop.wait(1.0):
		try:
			rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / divisor
			peak = max(peak, rss)
			conn.setex(redis_key, 900, str(round(peak, 1)))
		except Exception:
			return


def _read_memory_sample(key: str):
	"""Last RSS the work-horse reported, in MB, or None if it never ticked.

	Read with the raw connection because the sampler writes a bare string via
	`setex`; `get_value` would try to deserialize it.
	"""
	try:
		cache = _cache()
		raw = cache.get(cache.make_key(MEMORY_KEY.format(key=key)))
		if raw is None:
			return None
		return float(raw.decode() if isinstance(raw, bytes) else raw)
	except Exception:
		return None


def run(key: str, compute_method: str, compute_kwargs: Dict[str, Any], ttl: int):
	"""Worker entrypoint: compute and cache, then clear the running flag."""
	import threading

	cache = _cache()
	stop = threading.Event()
	sampler = None
	try:
		# Resolve the namespaced key on this thread, where the site context exists.
		redis_key = cache.make_key(MEMORY_KEY.format(key=key))
		sampler = threading.Thread(target=_sample_memory, args=(cache, redis_key, stop), daemon=True)
		sampler.start()
	except Exception:
		pass
	try:
		result = frappe.get_attr(compute_method)(**(compute_kwargs or {}))
		_cache().set_value(RESULT_KEY.format(key=key), result, expires_in_sec=ttl)
		# Reached the end without the process being killed: the key is healthy, so
		# the crash counter must not carry over into the next cold cache.
		clear_attempts(key)
		_cache().delete_value(MEMORY_KEY.format(key=key))
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"insights async compute: {key}")
		# Cache the failure briefly so the client stops polling and sees why,
		# but retries reasonably soon rather than being stuck for the full TTL.
		_cache().set_value(
			RESULT_KEY.format(key=key),
			{"status": "error", "message": str(e)[:500]},
			expires_in_sec=ERROR_TTL,
		)
		# A Python-level failure is reported and self-limiting via ERROR_TTL; it is
		# not a work-horse death, so it should not count toward the crash ceiling.
		clear_attempts(key)
	finally:
		stop.set()
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



def _record_crash_forensics(key: str, job, reason: str):
	"""Write everything needed to diagnose a work-horse death to the Error Log.

	A process killed by a signal leaves no Python traceback, so the usual
	`frappe.log_error(frappe.get_traceback())` records nothing useful. rq still
	holds the job's identity and arguments, and the site can report its own
	resource state -- capture both while they exist, because rq expires the job
	shortly after. Without this the only evidence is a line in worker.error.log
	on a machine the developer may not have shell access to.
	"""
	try:
		kwargs = dict(job.kwargs or {})
		inner = dict(kwargs.get("kwargs") or {})
		details = {
			"cache_key": key,
			"compute_method": inner.get("compute_method"),
			"compute_kwargs": inner.get("compute_kwargs"),
			"ran_as_user": kwargs.get("user"),
			"queue": resolve_queue(),
			"timeout": resolve_timeout(),
			"attempts": _attempts(key),
			"enqueued_at": str(getattr(job, "enqueued_at", None)),
			"started_at": str(getattr(job, "started_at", None)),
			"worker_name": getattr(job, "worker_name", None),
			"worker_health": worker_health(),
			"reason": reason,
		}
		# The work-horse samples its own RSS into redis while it runs. That is the
		# process that died; `RUSAGE_SELF` here would describe the web process
		# handling this poll, which is a different process entirely and was
		# previously reported as if it were relevant.
		horse_mb = _read_memory_sample(key)
		details["workhorse_peak_rss_mb"] = horse_mb if horse_mb is not None else "not sampled"
		details["verdict_hint"] = (
			"memory exhaustion likely — RSS was still climbing"
			if isinstance(horse_mb, (int, float)) and horse_mb > 1500
			else "not memory-bound at last sample; suspect a native fault (BLAS/fork)"
			if isinstance(horse_mb, (int, float))
			else "no sample — the horse died before the first 1s tick"
		)

		body = "\n".join(f"{k}: {v}" for k, v in details.items())
		if job.exc_info:
			body += "\n\n--- rq exc_info ---\n" + str(job.exc_info)[-2000:]
		frappe.log_error(body, f"insights work-horse died: {key}")
	except Exception:
		# Forensics must never mask the failure it is describing.
		pass


def _diagnose(key: str) -> Optional[Dict[str, Any]]:
	"""Explain a missing result, or None when it is legitimately still running.

	A work-horse killed by OOM or a signal never reaches `run`'s handler, so no
	error is ever cached and the client would poll until it times out. rq still
	knows what happened, so ask it rather than leaving the user guessing.
	"""
	try:
		from frappe.utils.background_jobs import get_job

		job = get_job(_job_name(key))
	except Exception:
		return None

	def give_up(message: str) -> Dict[str, Any]:
		# Let the next request re-queue instead of waiting out the flag.
		_cache().delete_value(STATE_KEY.format(key=key))
		return {"status": "error", "message": message}

	if job is None:
		health = worker_health()
		if health.get("workers") == 0:
			return give_up(
				_(
					"No background worker is consuming the '{0}' queue, so this dashboard "
					"cannot be computed. Start the workers (bench worker / supervisor)."
				).format(resolve_queue())
			)
		# Nothing queued and workers exist: the enqueue was lost. Re-queue next poll.
		_cache().delete_value(STATE_KEY.format(key=key))
		return None

	try:
		status = job.get_status(refresh=True)
	except Exception:
		return None

	if status == "failed":
		reason = _("the background job failed")
		if job.exc_info:
			reason = str(job.exc_info).strip().splitlines()[-1][:300]
		_record_crash_forensics(key, job, reason)
		return give_up(_("Computation failed on the server: {0}").format(reason))

	if status == "started" and job.worker_name not in _live_worker_names():
		# The work-horse died without unwinding. rq keeps the job STARTED forever,
		# and `deduplicate=True` then refuses to queue a replacement, so this key
		# could never recover on its own.
		try:
			job.delete()
		except Exception:
			pass
		return give_up(
			_("The worker computing this dashboard stopped unexpectedly. Retry to recompute it.")
		)

	if status == "queued" and worker_health().get("workers") == 0:
		return give_up(
			_(
				"The computation is queued on '{0}' but no worker is consuming it. "
				"Start the workers (bench worker / supervisor)."
			).format(resolve_queue())
		)

	return None


def permission_for(key: str) -> Optional[Tuple[str, str]]:
	"""Permission guarding `key`: the static registry first, cached META as fallback."""
	prefix = str(key).split(":", 1)[0]
	static = KEY_PERMISSIONS.get(prefix)
	if static:
		return static

	meta = _cache().get_value(META_KEY.format(key=key))
	if isinstance(meta, dict) and meta.get("doctype"):
		return (meta["doctype"], meta.get("ptype") or "read")
	return None


@frappe.whitelist()
def async_status(key: str) -> Dict[str, Any]:
	"""Poll a queued computation. Re-checks the permission guarding that key."""
	if not key or not str(key).strip():
		frappe.throw(frappe._("A key is required."))

	permission = permission_for(key)
	if not permission:
		# Genuinely unknown key — refuse rather than reading arbitrary cache entries.
		frappe.throw(frappe._("Unknown or expired job key."), frappe.PermissionError)
	_require(permission)

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



def environment_report() -> Dict[str, Any]:
	"""Diagnose a work-horse that dies by signal, from inside the affected host.

	A SIGSEGV leaves no traceback, so the cause has to be inferred from the
	environment. This runs the checks that discriminate between the plausible
	causes -- ABI mismatch, BLAS fork-safety, thread pinning -- and, critically,
	reproduces the fork the way rq does so a crash can be observed directly
	rather than deduced.

	Run it on the host that crashes:
	    bench --site <site> execute insights.api.ml.async_compute.environment_report
	"""
	import os
	import platform
	import subprocess
	import sys

	report: Dict[str, Any] = {
		"platform": platform.platform(),
		"python": sys.version.split()[0],
		"thread_env": {
			v: os.environ.get(v, "<unset>")
			for v in (
				"OPENBLAS_NUM_THREADS",
				"OMP_NUM_THREADS",
				"MKL_NUM_THREADS",
				"VECLIB_MAXIMUM_THREADS",
			)
		},
	}

	try:
		import numpy
		import pandas

		report["numpy"] = numpy.__version__
		report["pandas"] = pandas.__version__
		# pandas carries the numpy version it was *compiled* against. A major-version
		# disagreement here is a segfault waiting for the first interop call, because
		# numpy 2.x changed the C ABI.
		built = getattr(getattr(pandas, "compat", None), "_optional", None)
		report["numpy_major_matches_pandas_build"] = (
			"check manually: pip show pandas | grep -i requires" if built is None else "see below"
		)
		blas = numpy.show_config("dicts").get("Build Dependencies", {}).get("blas", {})
		report["blas"] = {"name": blas.get("name"), "version": blas.get("version")}
	except Exception as e:
		report["import_error"] = f"{type(e).__name__}: {e}"
		return {"status": "success", "data": report}

	# The decisive test: does a *forked* child survive a real numpy/pandas
	# workload? This is exactly what rq does to run a job. Run it out-of-process
	# so a segfault is reported rather than taking this process down too.
	probe = """
import os, sys
import numpy as np, pandas as pd
np.dot(np.random.rand(200,200), np.random.rand(200,200))   # initialise BLAS in the parent
pid = os.fork()
if pid == 0:
    try:
        np.dot(np.random.rand(200,200), np.random.rand(200,200))
        df = pd.DataFrame({"a": np.random.rand(5000), "b": np.random.rand(5000)})
        df.groupby((df.a * 10).astype(int)).agg({"b": ["mean", "sum", "std"]})
        os._exit(0)
    except Exception:
        os._exit(2)
else:
    _, status = os.waitpid(pid, 0)
    if os.WIFSIGNALED(status):
        print("FORK_CHILD_KILLED_BY_SIGNAL", os.WTERMSIG(status))
    else:
        print("FORK_CHILD_EXIT", os.WEXITSTATUS(status))
"""
	try:
		out = subprocess.run(
			[sys.executable, "-c", probe], capture_output=True, text=True, timeout=120
		)
		verdict = (out.stdout or "").strip().splitlines()[-1] if out.stdout.strip() else ""
		if "KILLED_BY_SIGNAL" in verdict:
			sig = verdict.rsplit(" ", 1)[-1]
			report["fork_probe"] = f"CRASHED: child killed by signal {sig}"
			report["verdict"] = (
				"Reproduced. numpy/pandas cannot survive fork() on this host. "
				"Set OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 in the "
				"WORKER's environment (Procfile / supervisor), which must be set before "
				"the worker imports numpy. If that does not help, rebuild pandas against "
				"the installed numpy: pip install --force-reinstall --no-binary pandas pandas"
			)
		elif verdict.startswith("FORK_CHILD_EXIT 0"):
			report["fork_probe"] = "survived"
			report["verdict"] = (
				"fork+numpy is healthy here, so the crash is not generic fork-unsafety. "
				"Suspect the specific computation: run it inline with "
				"`bench --site <site> execute "
				"insights.api.ml.sales._compute_sales_intelligence` and see whether it "
				"segfaults outside a work-horse."
			)
		else:
			report["fork_probe"] = f"inconclusive: {verdict or out.stderr[-300:]}"
	except Exception as e:
		report["fork_probe"] = f"probe failed: {type(e).__name__}: {e}"

	return {"status": "success", "data": report}