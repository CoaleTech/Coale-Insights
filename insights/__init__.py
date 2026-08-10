# First statements in the package, deliberately. OpenBLAS/MKL/libgomp size a
# thread pool from the host's CPU count on first import, and that pool does not
# survive rq's per-job fork() — the work-horse dies as
# "waitpid returned 139 (signal 11)" with no Python traceback. Pinning to 1
# means no pool exists to corrupt. numpy only enters this process through an
# `insights.*` module, and importing any of them runs this file first, so this
# is the one placement our own import order cannot race.
# setdefault: an operator who tuned these keeps their value.
import os

for _var in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_var, "1")

__version__ = "3.2.0-dev"
