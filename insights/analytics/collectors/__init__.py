# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Analytics data collectors.

Lazy for the same reason as the ML intelligence packages: the eager block this
replaced imported eight submodules while holding this package's module lock,
and each collector reached back with `from . import BaseCollector`, which
cannot complete until this package finishes initialising. Two concurrent
requests is all it takes:

    _DeadlockError: deadlock detected by
        _ModuleLock('insights.analytics.collectors.customer')

Reproduced by `repro_deadlock.py`. The collectors' own back-imports were also
repointed at `.base` directly, so nothing here waits on a partially initialised
package even while `__getattr__` is resolving.
"""

from typing import Any

_LAZY_MAP = {
    "BaseCollector": "insights.analytics.collectors.base",
    "FinancialDataCollector": "insights.analytics.collectors.financial",
    "SalesDataCollector": "insights.analytics.collectors.sales",
    "CustomerDataCollector": "insights.analytics.collectors.customer",
    "InventoryDataCollector": "insights.analytics.collectors.inventory",
    "ProcurementDataCollector": "insights.analytics.collectors.procurement",
    "ProductionDataCollector": "insights.analytics.collectors.production",
    "HRDataCollector": "insights.analytics.collectors.hr",
    "get_collector": "insights.analytics.collectors.api",
    "get_analytics_data": "insights.analytics.collectors.api",
    "get_all_analytics_data": "insights.analytics.collectors.api",
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
