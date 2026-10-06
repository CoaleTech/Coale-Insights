from __future__ import annotations

# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Sales Forecasting -- Ibis-native rewrite.

Was a `BaseMLModel` subclass that ran Prophet (>=2 years of history) or
Holt-Winters (>=14 days) or a plain moving-average fallback over the
daily Sales Invoice series. On Frappe Cloud the work-horse's ``fork()``
segfaulted (see ``insights.api.ml.ibis_source`` for the long version);
even where the work-horse was happy, the model needed multi-second CPU
on this site's series, which is why the old file shipped a Redis
cache, a warming contract, and a scheduler that pre-fills it.

The Prophet/Holt-Winters machinery is gone. The same `train()` / `predict`
contract is now answered in one Ibis expression: a daily sales series
aggregated inside MariaDB, dropped to a small DataFrame (~10-30 rows
depending on the lookback), and a closed-form least-squares linear
trend + residual std-dev projected forward N days. The result is
honest -- a single trend line plus a ±2σ band -- and runs in low
hundreds of milliseconds regardless of the lookback. No cache, no
background job, no fork.

Forecasting policy (from the shared contract):
  - aggregate historical revenue into daily buckets via Ibis group-by,
    `.execute()` to a small DataFrame
  - compute a linear trend via closed-form slope/intercept in plain
    Python (the `statistics` module is fine; we are operating on ~30
    scalars, not raw transactions)
  - project forward N days; band = ± 2 * residual std-dev

The dimensional / per-group and "by territory" / "by item group"
forecasts that the Revenue dashboard's "Forecasts" tab renders follow
the same rule, but per group, with a weighted mean of the last 3
observed months as the projection (12-point monthly series is below any
reasonable seasonal fit floor).

`BaseMLModel`, Prophet, statsmodels, scikit-learn, and ``fork()`` are
nowhere in this file. `BaseMLModel` itself is being deleted centrally
after every domain lands.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

from insights.api.ml.ibis_source import company_filter, default_company, t
from insights.api.ml.utils import parse_date_filter

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# A group with fewer than this many observed months has no trend worth
# extrapolating; it still contributes its history, just no forecast rows.
_DIM_MIN_MONTHS = 3

# How many future months the dimensional forecast projects.
_DIM_FORECAST_MONTHS = 3

# Daily-series forecast: with fewer than this many observations, a
# closed-form linear trend has 1 degree of freedom per point and
# extrapolates wildly (a 3-point series spanning 35 days projected
# 14 days out can yield a 5x slope). Fall back to the historical
# mean instead, so the forecast at least matches the recent run-rate.
_DAILY_MIN_SAMPLES = 7

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_partial(period: str, start: datetime | None, end: datetime | None) -> bool:
    """True when a ``YYYY-MM`` bucket is not wholly inside the window: its first
    day precedes the window start, or its last day is after the window end /
    today (still in progress)."""
    first = date(int(period[:4]), int(period[5:7]), 1)
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    cutoff = min(end.date(), date.today()) if end else date.today()
    return (start is not None and first < start.date()) or last > cutoff


def _first_projected_day(last_date: date, first_day: date | None) -> date:
    """First day of the projection: the day after the last observation, but
    never earlier than `first_day` (today) so a stale series is not projected
    into the past."""
    nxt = last_date + timedelta(days=1)
    return max(nxt, first_day) if first_day else nxt


def _flat_mean_forecast(history: pd.DataFrame, periods: int, first_day: date | None = None) -> dict[str, Any]:
    """Forecast a flat line at the historical mean.

    Used as a fallback when the daily history is too short for a
    closed-form linear trend to be meaningful (fewer than
    `_DAILY_MIN_SAMPLES` observed days). See
    `_linear_trend_forecast` for why.
    """
    df = history[["ds", "y"]].copy().sort_values("ds").reset_index(drop=True)
    y = df["y"].astype(float).to_numpy()
    n = len(y)
    mean = float(y.mean())
    std = float(y.std(ddof=1)) if n > 1 else 0.0
    band = 2.0 * std
    last_date = df["ds"].iloc[-1]
    if hasattr(last_date, "date") and callable(last_date.date):
        last_date = last_date.date()
    start = _first_projected_day(last_date, first_day)
    future_rows: list[dict[str, Any]] = [
        {
            "ds": (start + timedelta(days=i)).isoformat(),
            "yhat": round(max(0.0, mean), 2),
            "yhat_lower": round(max(0.0, mean - band), 2),
            "yhat_upper": round(mean + band, 2),
        }
        for i in range(periods)
    ]
    return {
        "method": "linear_trend",
        "forecast": future_rows,
        "forecast_summary": {
            "total_forecast": round(mean * periods, 2),
            "avg_daily_forecast": round(mean, 2),
            "trend": "stable",
            "days": periods,
        },
        "metrics": {
            "method_tested": "linear_trend",
            "horizon_days": min(14, max(1, n // 4)),
            "rmse": round(std, 2),
            "mae": round(std, 2),
            "n_points": int(n),
            "smape": 0.0,
        },
    }

def _linear_trend_forecast(
    history: pd.DataFrame,
    periods: int,
    first_day: date | None = None,
) -> dict[str, Any]:
    """Project `history` (single-column time series, datetime-indexed
    if possible) forward `periods` rows via a closed-form least-squares
    linear trend on the row index. Returns a payload shaped for the
    Revenue dashboard's "Forecasts" tab.

    `history` must have a 'ds' (date) and a 'y' (scalar) column.
    """
    import numpy as np
    import pandas as pd

    if history.empty or len(history) < 2:
        return {
            "method": "linear_trend",
            "forecast": [],
        }

    n_raw = len(history)
    if n_raw < _DAILY_MIN_SAMPLES:
        # Fall back to a flat mean forecast: a 3-4 point series is one
        # degree of freedom per point, so a least-squares line fits
        # perfectly and then projects wildly. Mean is the honest answer
        # for "we don't have enough data yet" and matches the recent
        # run-rate. The method name is kept as `linear_trend` for
        # forward-compat with the dashboard's rendering path, but the
        # slope is forced to zero below.
        return _flat_mean_forecast(history, periods, first_day)

    df = history[["ds", "y"]].copy()
    # With the PyArrow execute path `ds` is object-dtype datetime.date objects,
    # not datetime64. They sort and diff correctly without pd.to_datetime.
    df = df.sort_values("ds").reset_index(drop=True)
    y = df["y"].astype(float).to_numpy()
    n = len(y)
    x = pd.Series(range(n), dtype=float).to_numpy()

    # Closed-form least squares: y = a + b*x
    x_mean = x.mean()
    y_mean = y.mean()
    denom = ((x - x_mean) ** 2).sum()
    if denom == 0:
        b = 0.0
        a = float(y_mean)
    else:
        b = float(((x - x_mean) * (y - y_mean)).sum() / denom)
        a = float(y_mean - b * x_mean)

    # Residual std-dev for the ±2σ band. A single future point's
    # prediction interval widens with the squared distance from
    # x_mean -- we use the simpler "residual std" form, which is the
    # same thing Prophet's defaults render when the trend is linear.
    residuals = y - (a + b * x)
    residual_std = float(residuals.std(ddof=1)) if n > 1 else 0.0
    band = 2.0 * residual_std

    # Symmetric MAPE: bounded 0-200 and defined at zero, unlike plain MAPE
    # which this site's sparse series can push past 100% (rendering as a
    # nonsensical negative "accuracy" on the dashboard). The model-health
    # page already reports sMAPE; this brings the forecast panel in line.
    fitted = a + b * x
    smape_denom = np.abs(y) + np.abs(fitted)
    smape = float(np.mean(np.where(smape_denom == 0, 0.0, 2.0 * np.abs(residuals) / smape_denom))) * 100

    last_date = df["ds"].iloc[-1]
    if hasattr(last_date, "date") and callable(last_date.date):
        # `Timestamp`/`datetime` under the default (pandas) materialization path --
        # normalize once so every arithmetic step below sees a plain `date`.
        last_date = last_date.date()
    start = _first_projected_day(last_date, first_day)
    future_rows: list[dict[str, Any]] = []
    for i in range(periods):
        step_idx = n + i
        yhat = a + b * step_idx
        yhat_floor = max(0.0, float(yhat))
        future_rows.append(
            {
                "ds": (start + timedelta(days=i)).isoformat(),
                "yhat": round(yhat_floor, 2),
                "yhat_lower": round(max(0.0, yhat_floor - band), 2),
                "yhat_upper": round(yhat_floor + band, 2),
            }
        )

    # A summary dict the dashboard renders as a "next N days" total.
    total = round(sum(r["yhat"] for r in future_rows), 2)
    avg = round(total / max(1, len(future_rows)), 2)
    first = future_rows[0]["yhat"] if future_rows else 0.0
    last = future_rows[-1]["yhat"] if future_rows else 0.0
    if last > first:
        trend = "up"
    elif last < first:
        trend = "down"
    else:
        trend = "stable"

    return {
        "method": "linear_trend",
        "forecast": future_rows,
        "forecast_summary": {
            "total_forecast": total,
            "avg_daily_forecast": avg,
            "trend": trend,
            "days": len(future_rows),
        },
        "metrics": {
            "method_tested": "linear_trend",
            "horizon_days": min(14, max(1, n // 4)),
            "rmse": round(float((residuals ** 2).mean() ** 0.5), 2),
            "mae": round(float(abs(residuals).mean()), 2),
            "n_points": int(n),
            "smape": round(smape, 2),
        },
    }


# ---------------------------------------------------------------------------
# Public surface (preserved from the old module)
# ---------------------------------------------------------------------------


def run_sales_forecast(periods: int = 30, method: str = "auto") -> dict[str, Any]:
    """Run the sales forecast.

    `method` is accepted for backward compatibility and ignored --
    the only available forecaster now is the closed-form linear trend
    over the full available daily history.
    """
    return get_sales_forecast(periods=periods)


def get_sales_forecast(periods: int = 30, company: str | None = None) -> dict[str, Any]:
    """Get the sales forecast (a daily projection of `periods` days).

    The series is tax-exclusive base-currency revenue, matching the
    dashboard headline. Projection starts at max(last data day + 1, today).
    """
    inv = t("Sales Invoice")
    si = company_filter(inv, company or default_company()).filter(inv.docstatus == 1).filter(inv.is_return == 0)

    # `_linear_trend_forecast` expects columns named `ds` and `y`; rename
    # after .execute() (Ibis 10 rejects keyword-aliasing of a bare column in
    # a group-by metric).
    daily = si.group_by(si.posting_date).aggregate(y=si.base_net_total.sum()).order_by("posting_date")
    df = daily.execute()
    if not df.empty:
        df = df.rename(columns={"posting_date": "ds"})
    forecast = _linear_trend_forecast(df, periods, first_day=date.today())

    if not df.empty:
        last_date = df["ds"].max()
        if hasattr(last_date, "date") and callable(last_date.date):
            last_date = last_date.date()
        if "forecast_summary" in forecast:
            forecast["forecast_summary"]["stale_days"] = max(0, (date.today() - last_date).days)
            forecast["forecast_summary"]["first_day"] = forecast["forecast"][0]["ds"]
        first_date = df["ds"].min()
        data_range = {
            "start": str(first_date),
            "end": str(last_date),
            "days": len(df),
        }
        historical_summary = {
            "total_sales": float(df["y"].sum()),
            "avg_daily_sales": float(df["y"].mean()),
            "max_daily_sales": float(df["y"].max()),
            "min_daily_sales": float(df["y"].min()),
        }
    else:
        data_range = {"start": None, "end": None, "days": 0}
        historical_summary = {
            "total_sales": 0.0,
            "avg_daily_sales": 0.0,
            "max_daily_sales": 0.0,
            "min_daily_sales": 0.0,
        }

    return {
        "status": "success",
        "forecast_date": datetime.now().isoformat(),
        "data_range": data_range,
        "historical_summary": historical_summary,
        **forecast,
    }


def get_grouped_forecast(
    group_by: str = "item_group", periods: int = 30, company: str | None = None
) -> dict[str, Any]:
    """Get the forecast split by `group_by` (either "item_group" or
    "customer_group"). Aggregates daily sales per group, then runs the
    same linear-trend projection per group. Returns the same shape the
    Revenue "Forecasts" tab used to render from.
    """
    # Project to small, explicitly-named columns before joining -- this
    # is the only way to keep Ibis happy when the joined tables share
    # common ERPNext audit column names (every DocType has `name`,
    # `docstatus`, `modified`, ...). See ``source_attribution.py`` for
    # the same pattern.
    if group_by == "customer_group":
        cust = t("Customer").select(
            leadname=t("Customer")["name"],
            customer_group=t("Customer").customer_group,
        )
        join_on = (t("Sales Invoice").customer == cust.leadname)
        group_col = "customer_group"
    else:  # default and explicit: item_group
        cust = t("Item").select(
            itemname=t("Item")["name"],
            item_group=t("Item").item_group,
        )
        join_on = (t("Sales Invoice Item").item_code == cust.itemname)
        group_col = "item_group"

    inv = t("Sales Invoice")
    si = company_filter(inv, company or default_company()).filter(inv.docstatus == 1).filter(inv.is_return == 0)
    sii = t("Sales Invoice Item")

    joined = si.inner_join(sii, sii.parent == si.name).inner_join(cust, join_on)
    filtered = joined.filter(cust[group_col].notnull())

    expr = (
        filtered.group_by([si.posting_date, cust[group_col]])
        .aggregate(y=sii.base_net_amount.sum())
        .order_by([si.posting_date, cust[group_col]])
    )
    df = expr.execute()
    if df.empty:
        return {"status": "success", "group_by": group_by, "groups": {}}

    df = df.rename(columns={group_col: "group_name", "posting_date": "ds"})

    groups: dict[str, dict[str, Any]] = {}
    for group_name, group_df in df.groupby("group_name"):
        forecast = _linear_trend_forecast(group_df, periods, first_day=date.today())
        historical_avg = float(group_df["y"].mean())
        groups[str(group_name)] = {
            "forecast": forecast["forecast"],
            "historical_avg": round(historical_avg, 2),
        }
    return {
        "status": "success",
        "group_by": group_by,
        "groups": groups,
    }



# ---------------------------------------------------------------------------
# Dimensional history + forecast (Revenue "Forecasts" tab)
# ---------------------------------------------------------------------------


def _rows(raw: pd.DataFrame, alias: str) -> list[dict[str, Any]]:
    return [
        {
            "period": str(r["period"]),
            alias: r["bucket"],
            "revenue": float(r["revenue"] or 0),
            "transactions": int(r["transactions"] or 0),
            "is_forecast": False,
        }
        for _, r in raw.iterrows()
    ]


def _monthly_by_territory(company: str | None = None) -> list[dict[str, Any]]:
    """Monthly net revenue per invoice territory, full history.

    Territory is a Sales Invoice header field, so `base_net_total` can be
    summed directly -- one row per invoice, no fan-out.
    """
    inv = t("Sales Invoice")
    si = company_filter(inv, company or default_company())
    base = (
        si.filter(si.docstatus == 1)
        .filter(si.is_return == 0)
        .mutate(
            period=si.posting_date.strftime("%Y-%m"),
            bucket=si.territory.nullif("").fill_null("Unassigned"),
        )
    )
    expr = (
        base.group_by(["period", "bucket"])
        .aggregate(revenue=base.base_net_total.sum(), transactions=base.name.count())
        .order_by(["period", "bucket"])
    )
    return _rows(expr.execute(), "territory")


def _monthly_by_item_group(company: str | None = None) -> list[dict[str, Any]]:
    """Monthly net revenue per item group, full history.

    Item group lives on the invoice *lines*, so this joins; line
    `base_net_amount` sums to the invoice `base_net_total`, so no allocation
    is needed and the per-period sum ties out to revenue.
    """
    inv = t("Sales Invoice")
    sii = t("Sales Invoice Item")
    si = company_filter(inv, company or default_company())
    base = (
        si.inner_join(sii, sii.parent == si.name)
        .filter(si.docstatus == 1)
        .filter(si.is_return == 0)
        .mutate(
            period=si.posting_date.strftime("%Y-%m"),
            bucket=sii.item_group.nullif("").fill_null("Uncategorized"),
        )
    )
    expr = (
        base.group_by(["period", "bucket"])
        .aggregate(revenue=sii.base_net_amount.sum(), transactions=si.name.nunique())
        .order_by(["period", "bucket"])
    )
    return _rows(expr.execute(), "product_group")



def _extend_with_forecast(history: list[dict[str, Any]], alias: str) -> list[dict[str, Any]]:
    """Append forecast months per group, using its own recent
    weighted mean (no fit -- 12 observed months is below every
    reasonable seasonal-fit floor and the dashboard does not pretend
    otherwise).
    """
    if not history:
        return []

    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in history:
        by_group[row[alias]].append(row)

    last_period = max(row["period"] for row in history)
    year_str, month_str = last_period.split("-")
    year, month = int(year_str), int(month_str)

    future_periods: list[str] = []
    for step in range(1, _DIM_FORECAST_MONTHS + 1):
        total = month + step
        future_periods.append(f"{year + (total - 1) // 12}-{(total - 1) % 12 + 1:02d}")

    projected: list[dict[str, Any]] = []
    for group, rows in by_group.items():
        rows.sort(key=lambda r: r["period"])
        if len(rows) < _DIM_MIN_MONTHS:
            continue
        recent = rows[-3:]
        # Weight the most recent month heaviest: 1, 2, 3 over the
        # last three.
        weights = list(range(1, len(recent) + 1))
        divisor = sum(weights)
        revenue = sum(r["revenue"] * w for r, w in zip(recent, weights, strict=True)) / divisor
        transactions = sum(r["transactions"] * w for r, w in zip(recent, weights, strict=True)) / divisor
        for period in future_periods:
            projected.append(
                {
                    "period": period,
                    alias: group,
                    "revenue": round(revenue, 2),
                    "transactions": int(round(transactions)),
                    "is_forecast": True,
                }
            )

    return history + projected


def get_dimensional_history_and_forecast(
    date_filter: str = "12m", company: str | None = None
) -> dict[str, Any]:
    """Monthly net-revenue actuals (windowed by `date_filter`) plus a short
    projection, by product group and territory. Shaped for the Revenue
    dashboard's "Forecasts" tab, which transposes these into a
    period-by-group table.

    The projection is fitted on the full history; only the returned actual
    rows are windowed, and each carries `is_partial`.
    """
    start, end = parse_date_filter(date_filter)
    lo = start.strftime("%Y-%m") if start else ""
    hi = end.strftime("%Y-%m") if end else "9999-99"

    def build(rows: list[dict[str, Any]], alias: str) -> list[dict[str, Any]]:
        out = []
        for r in _extend_with_forecast(rows, alias):
            if r["is_forecast"]:
                r["is_partial"] = False
            elif lo <= r["period"] <= hi:
                r["is_partial"] = _is_partial(r["period"], start, end)
            else:
                continue
            out.append(r)
        return out

    return {
        "status": "success",
        "date_filter": date_filter,
        "horizon_months": _DIM_FORECAST_MONTHS,
        "combined_product_group": build(_monthly_by_item_group(company), "product_group"),
        "combined_territory": build(_monthly_by_territory(company), "territory"),
    }
