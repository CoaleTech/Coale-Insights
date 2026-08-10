# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence.

Lazy for the same reason as `insights/ml/customer_intelligence/__init__.py`: an
eager `from .model import IndiaTaxIntelligence` holds this package's module lock
while loading the submodule, and a concurrent request importing the submodule
directly holds that lock while waiting for this one. Python 3.14 detects the
cycle and raises `_DeadlockError`, which escapes as a non-JSON 500.

Reproduced by `repro_deadlock.py`, which fails on this package without the
indirection below.
"""

from typing import Any

_LAZY_MAP = {
    "IndiaTaxIntelligence": "insights.ml.india_tax_intelligence.model",
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
