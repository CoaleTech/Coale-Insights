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

Every phase is announced on stderr first, because a signal leaves no other
trace: the parent keeps this whole stream, so a fault with no Python frames of
its own is still read against the last phase reached here.

Not a public entry point: argv is built by `compute_dashboard`.
"""

from __future__ import annotations

import json
import sys

SAYS = "insights-child: "


def _say(message: str) -> None:
    """Announce one step on stderr, ahead of taking it."""
    sys.stderr.write(f"{SAYS}{message}\n")
    sys.stderr.flush()


def main(argv: list[str]) -> int:
    site, sites_path = argv[1], argv[2]
    rest = argv[3:]

    import frappe

    _say(f"phase=init site={site}")
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect()
    try:
        return selftest() if rest[:1] == ["--selftest"] else compute(rest)
    finally:
        frappe.destroy()


def compute(args: list[str]) -> int:
    """Compute one payload and leave it in the cache."""
    import frappe

    endpoint, params_json, user = args[0], args[1], args[2]
    key = args[3] if len(args) > 3 else ""

    frappe.set_user(user)
    # Off-request, so `cached_run` computes inline and writes the cache.
    # `insights_ml_refresh` makes it recompute rather than hand back
    # whatever is already there -- this process only ever runs because
    # something wanted a fresh payload.
    frappe.local.insights_ml_refresh = True

    _say(f"phase=call endpoint={endpoint} user={user}")
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
        _say(f"{endpoint} returned status={status}: {message}")
        return 2

    if key and frappe.cache.get_value(key) is None:
        _say(f"{endpoint} succeeded but left no payload at {key}")
        return 3

    _say("phase=cached")
    return 0


def _build_fingerprint() -> str:
    """Whether pandas' compiled extensions came from one build.

    A fault inside `pandas/_libs/pandas_datetime...so` called from
    `pandas/_libs/tslibs/np_datetime...so` is what a mixed install looks like:
    those two are compiled together against one internal C API, and
    `np_datetime` reaches `pandas_datetime`'s functions through a PyCapsule it
    does not version-check. Upgrading pandas in place over a live tree, or
    leaving two distributions shadowing each other, gives one half of that pair
    a struct layout the other half does not have -- a valid call to a valid
    address, faulting on the first field it reads.

    So: how many extensions, how far apart their timestamps are, and how many
    pandas distributions claim the directory.
    """
    import glob
    import os
    import platform

    import pandas as pd

    root = os.path.dirname(pd.__file__)
    sos = glob.glob(os.path.join(root, "_libs", "**", "*.so"), recursive=True)
    stamps = sorted(os.path.getmtime(p) for p in sos)
    spread = int(stamps[-1] - stamps[0]) if stamps else 0
    dists = glob.glob(os.path.join(os.path.dirname(root), "pandas-*.dist-info"))
    return (
        f"machine={platform.machine()} extensions={len(sos)} mtime_spread={spread}s "
        f"distributions={len(dists)} root={root}"
    )


def selftest() -> int:
    """Walk what a payload does, announcing each step before taking it.

    A signal death names the signal, and a fault with no Python frame of its
    own names nothing else. Ibis materialises every aggregate through pandas --
    `expr.execute()` builds a DataFrame from the cursor and converts each
    column to its schema type -- so every dashboard imports numpy and pandas,
    initialises the host's BLAS, and runs pandas' datetime C library over any
    date a query returns. This app has been made to crash on the first of
    those, and production crashed on the last.

    Each step below is announced first, so a host that faults says which step
    does it. Driven by `insights.api.ml.utils.child_selftest`.
    """
    import datetime
    import decimal

    _say("phase=selftest import numpy")
    import numpy as np

    _say(f"phase=selftest numpy={np.__version__} matmul")
    np.asarray([[1.0, 2.0], [3.0, 4.0]]) @ np.asarray([[1.0], [1.0]])

    _say("phase=selftest import pandas")
    import pandas as pd

    _say(f"phase=selftest pandas={pd.__version__} frame")
    pd.DataFrame({"a": [1, 2, 3]}).sum()

    _say(f"phase=selftest pandas build {_build_fingerprint()}")

    # The conversions a query result goes through, cheapest first. Every one of
    # these enters `pandas/_libs/tslibs/np_datetime` and the datetime C library
    # behind it, which is where production faults -- on twenty rows, so it is
    # the code that is wrong there, not the size of the data.
    _say("phase=selftest datetime64 unit conversion")
    np.array(["2026-01-01T00:00:00"], dtype="M8[ns]").astype("M8[s]")

    _say("phase=selftest date objects to datetime64")
    pd.Series([datetime.date(2026, 1, 1), None]).astype("datetime64[s]")

    _say("phase=selftest datetimes to datetime64")
    pd.Series([datetime.datetime(2026, 1, 1, 12, 30), None]).astype("datetime64[us]")

    _say("phase=selftest timedeltas to timedelta64")
    pd.Series([datetime.timedelta(days=3), None]).astype("timedelta64[s]")

    _say("phase=selftest import ibis")
    import ibis
    from ibis.formats.pandas import PandasData

    # The exact call in the production frames: one cursor result, one schema.
    _say(f"phase=selftest ibis={ibis.__version__} convert a result table")
    PandasData.convert_table(
        pd.DataFrame(
            {
                "d": [datetime.date(2026, 1, 1), None],
                "ts": [datetime.datetime(2026, 1, 1, 12, 30), None],
                "n": [decimal.Decimal("1.50"), None],
                "i": [1, None],
            }
        ),
        ibis.schema({"d": "date", "ts": "timestamp", "n": "decimal(18, 6)", "i": "int64"}),
    )

    _say("phase=selftest import ibis source")
    from insights.api.ml.ibis_source import t

    _say("phase=selftest execute one aggregate")
    users = t("User").count().execute()

    _say("phase=selftest execute a date column")
    u = t("User")
    u.select(d=u.creation.cast("date"), ts=u.creation).limit(5).execute()

    _say(f"phase=selftest ok users={users}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
