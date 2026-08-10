# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Strategic Finance Intelligence.

This package is the clearest case for lazy re-exports, because it has no
circular import at all: `model.py` imports its siblings by full path and the
leaf modules import nothing from `insights`. It still deadlocked.

An eager `__init__` is sufficient on its own. Holding the package lock while
importing a subtree is the hazard; a second thread importing any submodule
directly is all it takes to close the loop:

    _DeadlockError: deadlock detected by
        _ModuleLock('insights.ml.strategic_finance.data')

which is verbatim what production reported. Reproduced by `repro_deadlock.py`.
"""

from typing import Any

_LAZY_MAP = {
    "StrategicFinanceIntelligence": "insights.ml.strategic_finance.model",
    "run_strategic_finance_intelligence": "insights.ml.strategic_finance.model",
    "sanitize_for_json": "insights.ml.strategic_finance.data",
}

__all__ = list(_LAZY_MAP)

_cache: dict = {}


def __getattr__(name: str) -> Any:
    if name in _cache:
        return _cache[name]
    if name in _LAZY_MAP:
        import importlib

        value = getattr(importlib.import_module(_LAZY_MAP[name]), name)
        _cache[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
