# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Machine Learning for Frappe Insights.

Nothing is imported at package-init time, and this package is the one where it
matters most.

This module used to re-export eleven model classes eagerly. Because it is the
parent of every ML module, *any* `from insights.ml.<anything> import ...`
initialises it first -- so a single request pulled in customer intelligence,
sales, risk, India tax, and their pandas/sklearn/statsmodels dependencies,
while holding this package's module lock for the whole run.

Two consequences, both of which production hit:

1. Deadlock. A second concurrent request that needs any `insights.ml.*` module
   blocks in `_lock_unlock_module("insights.ml")` waiting for the first to
   finish initialising. If the first thread then needs a lock the second
   holds, Python 3.14 raises rather than hanging:

       _DeadlockError: deadlock detected by
           _ModuleLock('insights.ml.customer_intelligence')

   The exception escapes as a non-JSON 500, which the browser reports as
   "the server returned a gateway error instead of a response".

2. Serialisation. Even with no deadlock, the second request waits out the
   first's entire eleven-module import before its own work starts. On a cold
   worker that is seconds of dead time attributable to nothing in the handler,
   which is its own route to a gateway read timeout.

Both explain why the two heaviest dashboards failed together and why neither
ever failed alone on a single-threaded local probe.

Callers keep working unchanged: `from insights.ml import SalesIntelligence`
resolves through `__getattr__` on first use, and importing a submodule directly
(`from insights.ml.sales_intelligence import SalesIntelligence`, which is what
the API layer does) now costs nothing beyond that one module.
"""

from typing import Any

# Public name -> module that defines it.
_LAZY_MAP = {
    "PaymentPrediction": "insights.ml.payment_prediction",
    "DemandForecasting": "insights.ml.demand_forecasting",
    "ProductRecommendations": "insights.ml.product_recommendations",
    "BreakevenEngine": "insights.ml.breakeven_engine",
    "IndiaTaxIntelligence": "insights.ml.india_tax_intelligence.model",
    # `CustomerIntelligence` removed 2026-08-11: the underlying
    # `insights.ml.customer_intelligence.model` subpackage was deleted in the
    # pure-Ibis rewrite and nothing in the live tree uses
    # `from insights.ml import CustomerIntelligence` anymore. The replacement
    # module-level function is `insights.ml.customer.compute_customer_intelligence`.
    #
    # `CustomerSegmentation` and `ABCXYZClassification` removed the same day:
    # `insights.ml.customer_segmentation` and `insights.ml.abc_xyz_classification`
    # were both deleted. RFM segmentation now lives at
    # `insights.ml.customer.compute_rfm_segmentation`; ABC/XYZ classification's
    # canonical home is the `ABCXYZClassification` class in
    # `insights.ml.inventory_intelligence`.
    #
    # `SalesForecasting`, `SalesIntelligence`, and `RiskIntelligence` removed the
    # same day: all three domains were rewritten from `BaseMLModel` subclasses to
    # plain functions with no equivalent class. Use
    # `insights.ml.sales_forecasting.run_sales_forecast`,
    # `insights.ml.sales_intelligence.run_sales_intelligence`, and
    # `insights.ml.risk_intelligence.run_risk_intelligence` instead.
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
