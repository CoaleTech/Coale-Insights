# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Kenya Tax Intelligence API: VAT, eTIMS, payroll taxes, withholding, income tax, legal, customs.

`tax_intelligence` serves the full 9-tab payload from cache, recomputed in the
background per period (see `insights.api.ml.utils.cached_run`). `get_tax_detail`
is the drill-down behind any tab row or KPI.
"""

import frappe
from frappe import _
from typing import Any, Dict

from insights.api.response import error
from insights.api.ml.utils import cached_run, run, parse_custom_range

# `period` is one of `3m` / `6m` / `12m` / `fy`, or a `custom:<start>:<end>`
# range (see `insights.api.ml.utils.parse_custom_range`). Anything else,
# including an unset value, coerces to `fy`.
_PERIOD_KEYS = ("3m", "6m", "12m", "fy")
# modules whose `drilldown(ctx, metric, filters)` is asked, in order, for a metric
_DRILL_MODULES = ("vat", "etims", "payroll", "wht", "income", "legal", "customs")


def _coerce_period(period: str | None) -> str:
    if not period:
        return "fy"
    p = str(period).strip().lower()
    if p in _PERIOD_KEYS:
        return p
    return p if parse_custom_range(p) else "fy"


def _compute(period: str) -> Dict[str, Any]:
    """Single synchronous compute. Returns the full payload."""
    from insights.ml.kenya_tax_intelligence.model import KenyaTaxIntelligence

    return KenyaTaxIntelligence(period=period).train()


@frappe.whitelist()
def tax_intelligence(refresh: bool = False, period: str = "fy") -> Dict[str, Any]:
    """Full Kenya tax intelligence payload (see the envelope in `KenyaTaxIntelligence.train`).

    `period` is one of `3m` / `6m` / `12m` / `fy` and selects the reporting
    window. `refresh` queues a recompute and keeps serving the payload it
    already has.
    """
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        coerced = _coerce_period(period)
        return cached_run(
            lambda: run(lambda: _compute(coerced), "Tax intelligence"),
            cache_key=f"insights_ml_tax_intelligence:{coerced}",
        )
    except (frappe.PermissionError, frappe.ServiceUnavailableError):
        raise
    except Exception as e:
        return error("Failed to load tax intelligence", exc=e)


@frappe.whitelist()
def get_tax_detail(metric: str, filters: str) -> dict:
    """Row-level detail behind a tax metric, for the drill-down panel.

    `filters` is a JSON object (`period`, `company`, `page` plus the metric's own
    keys). Each section module decides whether the metric is its own via
    `drilldown(ctx, metric, filters)`; the first non-None answer wins and does its
    own permission check. Returns `{columns, rows, total}`.
    """
    import importlib
    from insights.ml.kenya_tax_intelligence.common import base_currency, build_context

    f = frappe.parse_json(filters) or {}
    if not isinstance(f, dict) or not isinstance(metric, str):
        frappe.throw(_("Invalid filters"), frappe.ValidationError)
    ctx = build_context(_coerce_period(f.get("period")))
    if f.get("company") and f["company"] != ctx.company:
        frappe.has_permission("Company", "read", doc=str(f["company"]), throw=True)
        ctx.company, ctx.base_currency = str(f["company"]), base_currency(str(f["company"]))
    for name in _DRILL_MODULES:
        result = importlib.import_module(f"insights.ml.kenya_tax_intelligence.{name}").drilldown(ctx, metric, f)
        if result is not None:
            return result
    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
