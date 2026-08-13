# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Compute one dashboard payload in a process of its own.

`insights.api.ml.utils.compute_dashboard` runs as an RQ job, and unless the
bench sets `FRAPPE_BACKGROUND_WORKERS_NOFORK` an RQ job runs in a work-horse
the worker made with `os.fork()` (`frappe.utils.background_jobs`: the default
`worker_klass` is `FrappeWorker`, and the pool sets the `fork` start method
explicitly). Forking a multi-threaded parent -- RQ's heartbeat thread,
Python's GC thread, whatever BLAS/OpenMP pool the worker touched last -- and
then doing pandas/numpy work in the child is undefined behaviour per POSIX.
This app has the scars: on Frappe Cloud it segfaulted the ML endpoints with
"waitpid returned 139 (signal 11)" reliably enough that the fix was to stop
using background jobs at all (see `insights.api.ml.ibis_source`).

Those endpoints are Ibis-backed now -- the aggregation happens inside MariaDB
-- but a dashboard payload still fans out to dozens of queries and spends tens
of seconds in Python assembling them, which is more than a request can hold
and more than a forked horse can be trusted with.

So the horse spawns this instead: a fresh interpreter (`python -m`, not a
fork), which boots frappe, computes one payload, leaves it in the cache and
exits. The horse's only job is to wait for the exit status, so a compute that
dies says so -- as a signal number the parent can report -- rather than
presenting as a dashboard that warms forever. Exiting also hands the payload's
pandas working set straight back to the OS instead of leaving it in a
long-lived worker.

The status is about the payload, not about this process getting through its
own code: 0 only if a payload is now in the cache, 2 if the endpoint answered
an error envelope, 3 if it claimed success but left nothing at the key, 1 on
an unhandled exception, and negative (a signal) if something killed it.

Not a public entry point: argv is built by `compute_dashboard`.
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    site, sites_path, endpoint, params_json, user = argv[1:6]
    key = argv[6] if len(argv) > 6 else ""

    import frappe

    frappe.init(site=site, sites_path=sites_path)
    frappe.connect()
    try:
        frappe.set_user(user)
        # Off-request, so `cached_run` computes inline and writes the cache.
        # `insights_ml_refresh` makes it recompute rather than hand back
        # whatever is already there -- this process only ever runs because
        # something wanted a fresh payload.
        frappe.local.insights_ml_refresh = True
        result = frappe.call(endpoint, **(json.loads(params_json) or {}))
        frappe.db.commit()

        # Exiting 0 on an endpoint that returned an error envelope would tell
        # the parent the payload is warm when the cache is still empty, and the
        # next request would queue the same failing compute again -- forever,
        # without ever showing anyone the error. So the exit status tracks the
        # one thing that matters: whether a payload is now there to serve.
        status = result.get("status") if isinstance(result, dict) else None
        if status != "success":
            message = result.get("message") if isinstance(result, dict) else result
            sys.stderr.write(f"{endpoint} returned status={status}: {message}\n")
            return 2

        if key and frappe.cache.get_value(key) is None:
            sys.stderr.write(f"{endpoint} succeeded but left no payload at {key}\n")
            return 3
    finally:
        frappe.destroy()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
