from __future__ import annotations

# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Price Intelligence -- Ibis-native selling-price analytics and forecast.

Two jobs, both answered by SQL aggregates executed inside MariaDB:

1. ``price_forecast`` -- a per-item selling-price band, consumed by
   ``jkm_finance.pricing.forecast.get_price_forecast`` on every recompute of a
   pricing request. It reuses ``sales_forecasting._linear_trend_forecast``
   rather than fitting a second model: the same closed-form least-squares
   trend, the same +/-2 sigma band, the same sMAPE. A price series is a daily
   scalar series like any other, so a second forecaster would only be a second
   thing to keep honest.

2. ``get_price_intelligence`` -- the dashboard payload: where margin actually
   comes from, where discounting is heaviest, and which quotations breach an
   approved floor.

The series is the qty-weighted realised unit price,
``sum(base_net_amount) / sum(stock_qty)``, in company currency and stock UOM.
Not ``avg(rate)``: ``rate`` is per transaction UOM, so a drum line and a tonne
line of the same item would be averaged into a meaningless number, and an
unweighted mean lets a single 5-kg sample outvote a 20-tonne one.
``base_net_amount`` is used because it is net of discount and converted to
company currency, so a price series is never distorted by FX or by a line
discount the seller did not intend to hide.

No pandas modelling, no scikit-learn, no fork: same posture as
``sales_forecasting`` and ``procurement_intelligence``.
"""

from datetime import datetime, timedelta
from math import isfinite
from typing import Any

import frappe
import ibis
from frappe.query_builder import Order
from frappe.query_builder.functions import Count, Sum

from insights.api.ml.ibis_source import company_filter, default_company, t
from insights.ml.sales_forecasting import _linear_trend_forecast

# A price series shorter than this cannot support a trend anybody should quote
# against: two invoices a year apart would produce a confident-looking slope.
_MIN_POINTS = 4

# How far back the price series looks. One year covers a full seasonal cycle
# without letting a price regime from two years ago drag the trend.
_LOOKBACK_DAYS = 365

# Confidence is reported as a word, not a number, because it gates how much of
# the forecast the pricing engine is allowed to apply
# (``jkm_finance.pricing.engine._CONFIDENCE_GATE``). Thresholds: enough points
# to see a trend, and a symmetric error small enough that the trend means
# something.
_HIGH_POINTS, _HIGH_SMAPE = 24, 15.0
_MEDIUM_POINTS, _MEDIUM_SMAPE = 12, 30.0


def _to_records(df) -> list[dict[str, Any]]:
    """``execute().pipe(_to_records)`` with Decimal coerced and NaN nulled.

    Two coercions, both required before the payload reaches JSON:

    - MariaDB DECIMAL aggregates arrive as ``decimal.Decimal``, which the JSON
      layer either stringifies or rejects (same reason as
      ``procurement_intelligence._to_records``).
    - A left join with no match yields ``NaN``, not ``None``. ``NaN`` is not
      valid JSON, and it is not ``null`` to the frontend either, so a missing
      valuation would render as "NaN" instead of a dash. Every non-finite float
      becomes ``None`` here so "no data" has exactly one representation.
    """
    rows = df.to_dict("records")
    for row in rows:
        for key, value in list(row.items()):
            if value is None or isinstance(value, (int, str, bool)):
                continue
            if isinstance(value, float):
                if not isfinite(value):
                    row[key] = None
                continue
            try:
                coerced = float(value)
            except (TypeError, ValueError):
                row[key] = str(value)
            else:
                row[key] = coerced if isfinite(coerced) else None
    return rows


def _sold_lines(company: str | None):
    """Submitted, non-return Sales Invoice Items with a real unit price.

    The parent is filtered *before* the semi-join, because after a semi-join
    the right relation is out of scope (see
    ``procurement_intelligence:168-172``).
    """
    SI = company_filter(t("Sales Invoice"), company)
    SII = t("Sales Invoice Item")
    parents = SI.filter((SI.docstatus == 1) & (SI.is_return == 0))
    return SII, parents


def _price_series(item_code: str, company: str | None):
    """Daily qty-weighted realised unit price for one item."""
    SI = company_filter(t("Sales Invoice"), company)
    SII = t("Sales Invoice Item")
    cutoff = datetime.now().date() - timedelta(days=_LOOKBACK_DAYS)

    parents = SI.filter(
        (SI.docstatus == 1) & (SI.is_return == 0) & (SI.posting_date >= cutoff)
    ).select(SI.name, SI.posting_date)

    lines = SII.filter((SII.item_code == item_code) & (SII.stock_qty > 0)).select(
        SII.parent, SII.stock_qty, SII.base_net_amount
    )

    return (
        lines.inner_join(parents, lines.parent == parents.name)
        .group_by(parents.posting_date)
        .aggregate(amount=lines.base_net_amount.sum(), qty=lines.stock_qty.sum())
        .order_by("posting_date")
    )


def _confidence(n_points: int, smape: float | None) -> str:
    """Word, not a number: it gates how much of the forecast is applied."""
    error = 999.0 if smape is None else float(smape)
    if n_points >= _HIGH_POINTS and error <= _HIGH_SMAPE:
        return "high"
    if n_points >= _MEDIUM_POINTS and error <= _MEDIUM_SMAPE:
        return "medium"
    return "low"


def price_forecast(item_code: str, horizon_days: int = 30) -> dict[str, Any]:
    """Selling-price band for one item ``horizon_days`` out.

    Returns ``status: "available"`` with ``mid``/``low``/``high``/``confidence``,
    or a status naming why there is no forecast. Never raises for want of data:
    "no history" is an answer, not a failure, and the caller shows it as such.
    """
    horizon = max(1, int(horizon_days or 30))
    company = default_company()
    df = _price_series(item_code, company).execute()

    if df.empty or len(df) < _MIN_POINTS:
        return {
            "status": "insufficient_history",
            "message": frappe._(
                "Only {0} day(s) of sales history for {1} in the last {2} days — "
                "at least {3} are needed to project a price."
            ).format(len(df), item_code, _LOOKBACK_DAYS, _MIN_POINTS),
            "n_points": len(df),
            "drivers": [],
        }

    # Weighted unit price per day, then hand the plain ds/y frame to the shared
    # forecaster. `_linear_trend_forecast` wants exactly these two columns.
    df["y"] = df["amount"].astype(float) / df["qty"].astype(float)
    df = df.rename(columns={"posting_date": "ds"})[["ds", "y"]]

    result = _linear_trend_forecast(df, horizon)
    rows = result.get("forecast") or []
    if not rows:
        return {
            "status": "insufficient_history",
            "message": frappe._("The price series for {0} is too short to project.").format(
                item_code
            ),
            "n_points": len(df),
            "drivers": [],
        }

    # The band at the far end of the horizon: that is the date being quoted
    # for, and it carries the widest honest interval.
    target = rows[-1]
    metrics = result.get("metrics") or {}
    n_points = int(metrics.get("n_points") or len(df))
    smape = metrics.get("smape")
    trend = (result.get("forecast_summary") or {}).get("trend") or "stable"

    observed_last = float(df["y"].iloc[-1])
    drivers = [
        frappe._("Trend over the last {0} days is {1}.").format(_LOOKBACK_DAYS, trend),
        frappe._("Built from {0} days of invoiced prices; last realised {1:.2f}.").format(
            n_points, observed_last
        ),
    ]
    if smape is not None:
        drivers.append(frappe._("Fit error (sMAPE) {0:.1f}%.").format(float(smape)))

    return {
        "status": "available",
        "message": None,
        "mid": target["yhat"],
        "low": target["yhat_lower"],
        "high": target["yhat_upper"],
        "confidence": _confidence(n_points, smape),
        "drivers": drivers,
        "method": result.get("method"),
        "n_points": n_points,
        "smape": smape,
        "horizon_days": horizon,
        "as_of": target["ds"],
        "observed_last": round(observed_last, 2),
        "series": [
            {"ds": str(row["ds"]), "y": round(float(row["y"]), 2)}
            for row in df.to_dict("records")
        ],
        "forecast": rows,
    }


# --------------------------------------------------------------------------- #
# Dashboard payload
# --------------------------------------------------------------------------- #
def _realised_margin(company: str | None, limit: int = 25) -> list[dict[str, Any]]:
    """Per-item realised price against stock valuation.

    ``Bin.valuation_rate`` is the comparison, not ``Item.valuation_rate``: the
    former is what the stock ledger actually holds. A negative margin here is
    the strongest single signal on this dashboard, because it means the item
    left the building below what it cost to hold. An item the stock ledger never
    costed reports a null margin, not a 100% one.
    """
    SII, parents = _sold_lines(company)
    Item = t("Item")
    cutoff = datetime.now().date() - timedelta(days=_LOOKBACK_DAYS)
    recent = parents.filter(parents.posting_date >= cutoff).select(parents.name)

    sold = (
        SII.filter(SII.stock_qty > 0)
        .join(recent, SII.parent == recent.name, how="semi")
        .select(SII.item_code, SII.stock_qty, SII.base_net_amount)
    )
    Bin = t("Bin")
    valuation = (
        Bin.filter(Bin.actual_qty > 0)
        .group_by(Bin.item_code)
        .aggregate(valuation_rate=Bin.valuation_rate.mean())
    )

    rows = (
        sold.group_by(sold.item_code)
        .aggregate(revenue=sold.base_net_amount.sum(), qty=sold.stock_qty.sum())
        .left_join(Item, sold.item_code == Item.name)
        .left_join(valuation, sold.item_code == valuation.item_code)
        .select(
            item_code=sold.item_code,
            item_name=Item.item_name,
            item_group=Item.item_group,
            revenue=ibis._.revenue,
            qty=ibis._.qty,
            valuation_rate=valuation.valuation_rate,
        )
        .order_by(ibis.desc("revenue"))
        .limit(limit)
        .execute()
        .pipe(_to_records)
    )

    for row in rows:
        _margin_columns(row)
    return rows


def _margin_columns(row: dict[str, Any]) -> None:
    """Stamp ``avg_rate``, ``margin_per_unit`` and ``margin_pct`` on one row.

    ``valuation_rate`` is None when the item has no positive-qty ``Bin`` row - a
    consignment or drop-ship line the stock ledger never costed. Coercing that
    to 0 would report a 100% margin on an unknown cost, which is the single most
    misleading number this dashboard could show, and on screen it is
    indistinguishable from a genuinely costless sale. Unknown cost means unknown
    margin; the frontend renders null as a dash.
    """
    qty = float(row.get("qty") or 0)
    revenue = float(row.get("revenue") or 0)
    avg_rate = revenue / qty if qty else 0.0
    row["avg_rate"] = round(avg_rate, 2)

    valuation_rate = row.get("valuation_rate")
    if valuation_rate is None or not avg_rate:
        row["margin_per_unit"] = None
        row["margin_pct"] = None
        return
    margin = avg_rate - float(valuation_rate)
    row["margin_per_unit"] = round(margin, 2)
    row["margin_pct"] = round(margin / avg_rate * 100, 1)


def _discount_pressure(company: str | None, limit: int = 15) -> list[dict[str, Any]]:
    """Where the list price is not holding.

    ``price_list_rate`` is the pre-discount reference ERPNext itself stamped on
    the line, so this measures realised discount without needing a second
    source of truth for "what we meant to charge".
    """
    SII, parents = _sold_lines(company)
    cutoff = datetime.now().date() - timedelta(days=_LOOKBACK_DAYS)
    recent = parents.filter(parents.posting_date >= cutoff).select(parents.name)

    lines = (
        SII.filter((SII.stock_qty > 0) & (SII.price_list_rate > 0))
        .join(recent, SII.parent == recent.name, how="semi")
        .select(SII.item_code, SII.stock_qty, SII.base_net_amount, SII.price_list_rate)
    )
    # `item_name` is joined here, not left to the frontend: the margin table one
    # section above names its items, and the same item appearing as a code in one
    # table and a name in the other reads as two different things.
    Item = t("Item")
    return (
        lines.group_by(lines.item_code)
        .aggregate(
            revenue=lines.base_net_amount.sum(),
            qty=lines.stock_qty.sum(),
            list_value=(lines.price_list_rate * lines.stock_qty).sum(),
            line_count=lines.item_code.count(),
        )
        .mutate(discount_value=ibis._.list_value - ibis._.revenue)
        .filter(ibis._.discount_value > 0)
        .left_join(Item, ibis._.item_code == Item.name)
        .select(
            "item_code",
            "revenue",
            "qty",
            "list_value",
            "line_count",
            "discount_value",
            item_name=Item.item_name,
        )
        .order_by(ibis.desc("discount_value"))
        .limit(limit)
        .execute()
        .pipe(_to_records)
    )


def _floor_breaches(limit: int = 25) -> dict[str, Any]:
    """Open quotations priced under a floor jkm_finance approved.

    Guarded on the Custom Field: without ``jkm_finance`` installed the column
    does not exist, and this section reports that rather than failing the whole
    dashboard.
    """
    if not frappe.get_meta("Quotation Item").get_field("jkm_floor_price"):
        return {
            "status": "unavailable",
            "message": frappe._("Approved floor prices are not tracked on this site."),
            "rows": [],
        }

    QI = t("Quotation Item")
    Q = t("Quotation")
    open_quotes = Q.filter(Q.docstatus < 2).select(Q.name, Q.customer_name)
    breaches = (
        QI.filter((QI.jkm_floor_price > 0) & (QI.rate < QI.jkm_floor_price))
        .select(QI.parent, QI.item_code, QI.rate, QI.jkm_floor_price, QI.qty)
        .inner_join(open_quotes, ibis._.parent == open_quotes.name)
        .select(
            quotation=ibis._.parent,
            customer_name=open_quotes.customer_name,
            item_code=ibis._.item_code,
            rate=ibis._.rate,
            floor_price=ibis._.jkm_floor_price,
            qty=ibis._.qty,
        )
        .limit(limit)
        .execute()
        .pipe(_to_records)
    )
    for row in breaches:
        row["shortfall"] = round(
            (float(row.get("floor_price") or 0) - float(row.get("rate") or 0))
            * float(row.get("qty") or 0),
            2,
        )
    return {"status": "available", "message": None, "rows": breaches}


def _approval_queue() -> dict[str, Any]:
    """Pricing requests by workflow state, when jkm_finance is installed."""
    if not frappe.db.exists("DocType", "JKM Sales Pricing Request"):
        return {
            "status": "unavailable",
            "message": frappe._("The JKM Finance pricing app is not installed on this site."),
            "rows": [],
        }
    # `frappe.qb`, not `get_all(fields=["count(name) as count"])`: v16's query
    # builder rejects SQL functions written as strings in `fields`.
    SPR = frappe.qb.DocType("JKM Sales Pricing Request")
    rows = (
        frappe.qb.from_(SPR)
        .select(
            SPR.workflow_state.as_("state"),
            Count(SPR.name).as_("count"),
            Sum(SPR.total_offer).as_("value"),
        )
        .where(SPR.docstatus < 2)
        .groupby(SPR.workflow_state)
        .orderby("count", order=Order.desc)
        .run(as_dict=True)
    )
    # DECIMAL sums arrive as `decimal.Decimal`, which the JSON layer stringifies.
    for row in rows:
        row["count"] = int(row["count"] or 0)
        row["value"] = float(row["value"] or 0)
    return {"status": "available", "message": None, "rows": rows}


def get_selling_price_intelligence() -> dict[str, Any]:
    """The whole Price Intelligence dashboard payload."""
    company = default_company()
    return {
        "status": "success",
        "company": company,
        "currency": frappe.get_cached_value("Company", company, "default_currency")
        if company
        else None,
        "lookback_days": _LOOKBACK_DAYS,
        "margin_by_item": _realised_margin(company),
        "discount_pressure": _discount_pressure(company),
        "floor_breaches": _floor_breaches(),
        "approval_queue": _approval_queue(),
    }
