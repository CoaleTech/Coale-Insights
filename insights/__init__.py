# First statements in the package, deliberately. OpenBLAS/MKL/libgomp size a
# thread pool from the host's CPU count on first import, and that pool does not
# survive rq's per-job fork() — the work-horse dies as
# "waitpid returned 139 (signal 11)" with no Python traceback. Pinning to 1
# means no pool exists to corrupt. numpy only enters this process through an
# `insights.*` module, and importing any of them runs this file first, so this
# is the one placement our own import order cannot race.
#
# Forced, not setdefault: a forking work-horse has no safe multi-thread value.
# Frappe Cloud exports these vars sized to the container's CPUs, so setdefault
# quietly kept that multi-thread count and the segfault survived — which is why
# it only ever reproduced on Cloud, never on a local bench where they're unset.
import os

for _var in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ[_var] = "1"

__version__ = "3.2.0-dev"
