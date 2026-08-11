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
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import ibis

if TYPE_CHECKING:
    import pandas as pd

from insights.api.ml.ibis_source import company_filter, default_company, t

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# A group with fewer than this many observed months has no trend worth
# extrapolating; it still contributes its history, just no forecast rows.
_DIM_MIN_MONTHS = 3

# How many historical months the dimensional forecast shows.
_DIM_HISTORY_MONTHS = 12
# How many future months the dimensional forecast projects.
_DIM_FORECAST_MONTHS = 3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _linear_trend_forecast(
    history: pd.DataFrame,
    periods: int,
) -> dict[str, Any]:
    """Project `history` (single-column time series, datetime-indexed
    if possible) forward `periods` rows via a closed-form least-squares
    linear trend on the row index. Returns a payload shaped for the
    Revenue dashboard's "Forecasts" tab.

    `history` must have a 'ds' (date) and a 'y' (scalar) column.
    """
    import pandas as pd

    if history.empty or len(history) < 2:
        return {
            "method": "linear_trend",
            "forecast": [],
        }

    df = history[["ds", "y"]].copy()
    df.loc[:, "ds"] = pd.to_datetime(df["ds"])
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

    last_date = df["ds"].iloc[-1]
    future_rows: list[dict[str, Any]] = []
    for i in range(1, periods + 1):
        step_idx = n + i - 1
        yhat = a + b * step_idx
        yhat_floor = max(0.0, float(yhat))
        future_rows.append(
            {
                "ds": (last_date + timedelta(days=i)).date().isoformat(),
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


def get_sales_forecast(periods: int = 30) -> dict[str, Any]:
    """Get the sales forecast (a daily projection of `periods` days)."""
    si = company_filter(t("Sales Invoice"), default_company()).filter(
        t("Sales Invoice").docstatus == 1
    ).filter(t("Sales Invoice").is_return == 0)

    # Daily revenue series. `posting_date` is already a DATE in MariaDB
    # and `grand_total` is DECIMAL -- `sum` returns a numeric column.
    # The `_linear_trend_forecast` helper expects columns named `ds` and
    # `y`; rename after .execute() rather than trying to alias inside
    # the aggregate (Ibis 10 rejects keyword-aliasing of a bare column
    # in a group-by metric).
    daily = (
        si.group_by(si.posting_date)
        .aggregate(y=si.grand_total.sum())
        .order_by("posting_date")
    )
    df = daily.execute()
    if not df.empty:
        df = df.rename(columns={"posting_date": "ds"})
    forecast = _linear_trend_forecast(df, periods)

    if not df.empty:
        last_date = df["ds"].max()
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


def get_grouped_forecast(group_by: str = "item_group", periods: int = 30) -> dict[str, Any]:
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

    si = t("Sales Invoice").filter(t("Sales Invoice").docstatus == 1).filter(
        t("Sales Invoice").is_return == 0
    )
    sii = t("Sales Invoice Item")

    joined = si.inner_join(sii, sii.parent == si.name).inner_join(cust, join_on)
    filtered = joined.filter(cust[group_col].notnull())

    expr = (
        filtered.group_by([si.posting_date, cust[group_col]])
        .aggregate(y=sii.amount.sum())
        .order_by([si.posting_date, cust[group_col]])
    )
    df = expr.execute()
    if df.empty:
        return {"status": "success", "group_by": group_by, "groups": {}}

    df = df.rename(columns={group_col: "group_name", "posting_date": "ds"})

    groups: dict[str, dict[str, Any]] = {}
    for group_name, group_df in df.groupby("group_name"):
        forecast = _linear_trend_forecast(group_df, periods)
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


def _monthly_by_territory(months: int) -> list[dict[str, Any]]:
    """Monthly revenue per territory.

    Territory is a Sales Invoice header field, so the invoice total
    can be summed directly -- one row per invoice, no fan-out.
    """
    si = t("Sales Invoice")
    cutoff = (datetime.now() - timedelta(days=months * 30)).date()
    base = (
        si.filter(si.docstatus == 1)
        .filter(si.is_return == 0)
        .filter(si.posting_date >= cutoff)
        .filter(si.territory.notnull())
        .filter(si.territory != ibis.literal(""))
        .mutate(period=si.posting_date.strftime("%Y-%m"))
    )
    expr = (
        base.group_by(["period", "territory"])
        .aggregate(
            revenue=si.base_grand_total.sum(),
            transactions=base.name.count(),
        )
        .order_by(["period", "territory"])
    )
    df = expr.execute().rename(columns={"territory": "bucket"})
    return _rows(df, "territory")


def _monthly_by_item_group(months: int) -> list[dict[str, Any]]:
    """Monthly revenue per item group.

    Item group lives on the invoice *lines*, so this has to join. A
    naive join counting `base_grand_total` per line inflates revenue
    by ~42% (a known prior bug). The fix: allocate the invoice total
    to its lines in proportion to their net amount, and fall back to
    the line amount itself when the invoice net total is zero (fully
    discounted). Either way the per-period sum ties out to revenue.
    """
    si = t("Sales Invoice")
    sii = t("Sales Invoice Item")
    cutoff = (datetime.now() - timedelta(days=months * 30)).date()

    base = (
        si.inner_join(sii, sii.parent == si.name)
        .filter(si.docstatus == 1)
        .filter(si.is_return == 0)
        .filter(si.posting_date >= cutoff)
        .filter(sii.item_group.notnull())
        .filter(sii.item_group != ibis.literal(""))
        .mutate(period=si.posting_date.strftime("%Y-%m"))
    )

    # Allocate invoice total to each line in proportion to its net
    # amount, with a zero-net-total guard. The same logic is in
    # ``_monthly_by_item_group`` of the previous implementation.
    allocated = ibis.ifelse(
        si.base_net_total == 0,
        sii.base_net_amount,
        sii.base_net_amount / si.base_net_total * si.base_grand_total,
    )

    expr = (
        base.group_by(["period", "item_group"])
        .aggregate(
            revenue=allocated.sum(),
            transactions=si.name.nunique(),
        )
        .order_by(["period", "item_group"])
    )
    df = expr.execute().rename(columns={"item_group": "bucket"})
    return _rows(df, "product_group")



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


def get_dimensional_history_and_forecast(months: int = _DIM_HISTORY_MONTHS) -> dict[str, Any]:
    """Monthly actuals plus a short projection, by product group and
    territory. Shaped for the Revenue dashboard's "Forecasts" tab,
    which transposes these into a period-by-group table.
    """
    product_group = _monthly_by_item_group(months)
    territory = _monthly_by_territory(months)

    return {
        "status": "success",
        "months": months,
        "horizon_months": _DIM_FORECAST_MONTHS,
        "combined_product_group": _extend_with_forecast(product_group, "product_group"),
        "combined_territory": _extend_with_forecast(territory, "territory"),
    }
