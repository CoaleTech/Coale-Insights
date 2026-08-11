# insights/ml/demand_forecasting.py
"""Item-level demand forecasting -- re-export shim.

The canonical implementation lives at
``insights.ml.inventory_intelligence.DemandForecasting`` (per-item
monthly-quantity-bucket forecast, reorder points, current stock vs.
weighted recent demand). It is owned by the Inventory / Procurement
domain; the Sales / Forecasting domain is only responsible for the
*revenue* forecast at ``insights.ml.sales_forecasting``.

This module exists so the existing call sites -- ``insights.api.ml.general``
(`demand_forecast`, `get_reorder_alerts`) and
``insights.ml.sales_intelligence``'s refresh path (the auto-train block
that re-resolves `DemandForecasting` lazily) -- keep working without
re-implementing the per-item forecast here. Every name in the public
surface below is re-exported from the canonical home so callers do not
need to change.

No training, no cache, no background job: the canonical implementation
computes its payload in one Ibis round trip per query and returns
synchronously. ``BaseMLModel`` is not used (it is being deleted centrally
after every domain lands).
"""

from __future__ import annotations

from typing import Any, Dict

from insights.ml.inventory_intelligence import DemandForecasting


def run_demand_forecast(periods: int = 4, top_items: int = 100) -> Dict[str, Any]:
    """Run item-level demand forecasting.

    The canonical implementation does not take a `periods` or
    `top_items` parameter -- it forecasts a fixed 3-month forward
    window for every item with sales history and reports the top 10
    reorder alerts. The parameters are accepted for backward
    compatibility with the previous implementation and are ignored.
    """
    return DemandForecasting().train()


def get_demand_forecast() -> Dict[str, Any]:
    """Get the demand forecast (the canonical train() result, computed
    fresh on every call -- there is no cache layer here)."""
    return DemandForecasting().train()


def get_item_demand_forecast(item_code: str, periods: int = 4) -> Dict[str, Any]:
    """Get demand forecast for a specific item.

    The canonical class does not currently accept a per-item filter
    (every call returns the full top-N list). The signature is
    preserved for backward compatibility; `item_code` and `periods` are
    accepted but ignored.
    """
    return {
        "status": "success",
        "item_code": item_code,
        "message": "Per-item forecast is included in the full demand_forecast() payload; "
        "filter the `reorder_alerts` array on `item_code` to extract it.",
    }


def get_reorder_alerts() -> Dict[str, Any]:
    """Get the items that need to be reordered.

    Reads the canonical `train()` payload and reshapes it to the
    shape callers historically expected: a list of alert dicts under
    `alerts` plus a count under `alert_count`. The canonical
    `reorder_alerts` key is preserved for callers that read it
    directly.
    """
    payload = DemandForecasting().train()
    alerts = payload.get("reorder_alerts", [])
    return {
        "status": payload.get("status", "success"),
        "alert_count": len(alerts),
        "reorder_alerts": alerts,
        "alerts": alerts,
        "reorder_now_count": payload.get("reorder_now_count", 0),
        "monitor_count": payload.get("monitor_count", 0),
        "adequate_count": payload.get("adequate_count", 0),
        "total_items_analyzed": payload.get("total_items_analyzed", 0),
    }
