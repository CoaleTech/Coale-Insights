# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Customer Intelligence.

Nothing is imported at package-init time. The eager re-exports this replaced
held the package's own module lock while pulling in the whole subtree, which
deadlocks under concurrent requests on Python 3.14:

    thread A  import insights.ml.customer_intelligence
              -> holds lock(package), runs __init__, wants lock(package.model)
    thread B  import insights.ml.customer_intelligence.model
              -> holds lock(package.model), wants lock(package)

    _DeadlockError: deadlock detected by
        _ModuleLock('insights.ml.customer_intelligence')

importlib raises rather than hanging, the exception escapes as a non-JSON 500,
and the browser reports "the server returned a gateway error instead of a
response". It needs two threads, so it never reproduces on a single-threaded
probe and only ever appears on a real gunicorn.

Same fix, and the same reasoning, as `insights/api/ml/__init__.py`.
"""

from typing import Any

# Public name -> the submodule that defines it.
_LAZY_MAP = {
    "CustomerIntelligence": "insights.ml.customer_intelligence.model",
    "get_customer_360_detail": "insights.ml.customer_intelligence.api",
    "get_purchase_patterns": "insights.ml.customer_intelligence.api",
    "get_cross_sell_opportunities": "insights.ml.customer_intelligence.api",
    "get_at_risk_customers": "insights.ml.customer_intelligence.api",
    "get_geographic_insights": "insights.ml.customer_intelligence.api",
    "get_next_actions": "insights.ml.customer_intelligence.api",
    "refresh_customer_scores": "insights.ml.customer_intelligence.api",
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
