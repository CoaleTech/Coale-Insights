# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ML dependency diagnostics.

`BaseMLModel` (the old train/predict/cache_results base class) and its last
subclass were removed 2026-08-11: every intelligence domain in this app now
computes fresh via Ibis on each request instead of training-then-caching a
pandas model, so there is nothing left to subclass. This module now only
answers "which ML libraries can this interpreter import" - the one piece of
`base.py` that still has a real caller (`model_health` via
`insights.api.ml.model_ops.ensure_dependencies`).
"""

from __future__ import annotations

import importlib
from typing import Optional


def ensure_dependencies() -> dict[str, Optional[str]]:
    """Which ML libraries this interpreter can import, and at what version.

    Previously returned bare booleans for a list that had drifted from reality:
    it probed `xgboost`, which the app no longer installs, and never mentioned
    `statsmodels`, which is what the sales forecast actually fits on. It also
    had no callers -- the only way to see its answer was to run it by hand over
    a bench shell, which is why "check the dependencies on production" kept
    living on a task list instead of being knowable.

    Now it reports versions rather than True/False, because "installed" was
    never the interesting question -- two benches disagreeing about which
    version is installed is what silently changes a model's behaviour. The
    `model_health` endpoint reads this, so the answer shows on the Machine
    Learning page for whatever site you are looking at.

    Returns a mapping of import name to version string, or None when the
    library cannot be imported.
    """
    found: dict[str, Optional[str]] = {}
    for label, module_name in (
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("scikit-learn", "sklearn"),
        ("statsmodels", "statsmodels"),
        ("prophet", "prophet"),
    ):
        try:
            module = importlib.import_module(module_name)
            found[label] = getattr(module, "__version__", "unknown")
        except Exception:
            # ImportError for a missing package, but a broken native build
            # raises other things -- and for this report they mean the same.
            found[label] = None
    return found
