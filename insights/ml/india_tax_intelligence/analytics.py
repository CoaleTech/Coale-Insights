# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence — analytics & forecasting.

The old `get_tax_forecast` used `sklearn.linear_model.LinearRegression`
on the monthly net-GST series. We replaced it with a closed-form
ordinary-least-squares fit on a series of ~12-24 scalars: the regression
is just `(mean(x*y) - mean(x)*mean(y)) / (mean(x*x) - mean(x)**2)`, which
runs in plain Python without importing numpy, and skips the entire
sklearn/statsmodels/prophet stack that the rewrite is removing across the
app.

`get_advance_tax_schedule` was always pure-Python; kept verbatim.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List


def _closed_form_linear_fit(ys: List[float]) -> Dict[str, Any]:
    """OLS slope/intercept on (x = 0, 1, …, n-1) → y.

    Returns ``{"slope", "intercept", "r_squared"}`` (r_squared is None
    if n < 2). Avoids numpy/sklearn entirely.
    """
    n = len(ys)
    if n < 2:
        return {"slope": 0.0, "intercept": ys[0] if ys else 0.0, "r_squared": None}
    x_mean = (n - 1) / 2.0
    y_mean = sum(ys) / n
    num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(ys))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den > 0 else 0.0
    intercept = y_mean - slope * x_mean
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (slope * i + intercept)) ** 2 for i, y in enumerate(ys))
    r_sq = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else None
    return {
        "slope": slope,
        "intercept": intercept,
        "r_squared": r_sq,
    }


def get_tax_forecast(intelligence, start, end) -> Dict[str, Any]:
    """Forecast next 3 months' net GST from the monthly series.

    Closed-form OLS on the monthly net-GST list (no scikit-learn).

    Two things this deliberately does not do:

    - **Fit on the running month.** A month that is still open carries a
      part-month of invoices, so it sits far below every closed month and
      drags the slope down. The fit uses closed months only; the current
      calendar month is dropped even though it is inside the window.
    - **Clamp the projection at zero.** Net GST is output tax less input
      credit, so a negative projection is a real state -- credit exceeding
      liability, carried forward -- not an error and not a refund. Clamping
      would hide it. `r_squared` is returned so a reader can discount a line
      that does not fit; the caller renders it.
    """
    from insights.ml.india_tax_intelligence.data import (
        get_gst_output_tax,
        get_gst_input_tax,
    )

    output_tax = get_gst_output_tax(intelligence, start, end) or []
    input_tax = get_gst_input_tax(intelligence, start, end) or []

    if not output_tax:
        return {
            "forecast": [],
            "note": "Insufficient historical data for forecasting",
        }

    months: List[str] = []
    net_gst: List[float] = []
    for o in output_tax:
        month = o.get("month")
        if not month:
            continue
        out_total = float(
            (o.get("cgst") or 0) + (o.get("sgst") or 0) + (o.get("igst") or 0)
        )
        inp_total = 0.0
        for i in input_tax:
            if i.get("month") == month:
                inp_total = float(
                    (i.get("cgst") or 0) + (i.get("sgst") or 0) + (i.get("igst") or 0)
                )
                break
        months.append(month)
        net_gst.append(out_total - inp_total)

    # A month equal to today's is still accruing. String compare is safe on
    # zero-padded `YYYY-MM`, and a window that ended in the past keeps every
    # month it has.
    running_month = datetime.now().date().strftime("%Y-%m")
    closed = [(m, v) for m, v in zip(months, net_gst, strict=True) if m < running_month]
    dropped_running_month = len(closed) < len(months)
    months = [m for m, _ in closed]
    net_gst = [v for _, v in closed]

    n = len(months)
    if n < 3:
        return {
            "forecast": [],
            "note": "Need at least 3 closed months of data for forecasting",
        }

    fit = _closed_form_linear_fit(net_gst)
    slope = fit["slope"]
    intercept = fit["intercept"]
    r_sq = fit["r_squared"]

    forecast: List[Dict[str, Any]] = []
    for i in range(1, 4):
        # next_month_idx is the future X (n + i - 1) so the line continues
        # the same slope from the last observed point.
        next_month_idx = n + i - 1
        pred = slope * next_month_idx + intercept
        forecast.append(
            {
                "month_offset": i,
                "projected_net_gst": round(float(pred), 2),
            }
        )

    note = (
        f"Ordinary least squares on net GST for the {n} closed months to {months[-1]}"
    )
    if dropped_running_month:
        note += "; the running month is still accruing and is excluded"

    return {
        "forecast": forecast,
        "trend_slope": round(float(slope), 2),
        "r_squared": round(float(r_sq), 4) if r_sq is not None else None,
        "months_used": n,
        "last_closed_month": months[-1],
        "note": note,
    }


def get_advance_tax_schedule(intelligence) -> List[Dict[str, Any]]:
    """Return advance-tax instalments with their actual calendar dates.

    Statutory basis:
    - Section 208: mandatory when estimated tax liability ≥ ₹10,000
    - Section 207: senior citizens (60+) with no business income are exempt
    - Section 234B: 1% p.m. interest if <90% of liability paid by 31 Mar
    - Section 234C: 1% p.m. interest for delay in quarterly instalments
    - Presumptive taxpayers (44AD/44ADA): entire tax due on 15 Mar
    """
    # Resolve the FY start from the fiscal_year attribute the model
    # populated at construction. Fall back to today's year if absent.
    fy_start = None
    fy = getattr(intelligence, "fiscal_year", None)
    if fy:
        fy_start = fy.get("year_start_date")

    if not fy_start:
        fy_start = date(datetime.now().year, 1, 1)

    if isinstance(fy_start, str):
        try:
            fy_year = int(fy_start[:4])
        except (TypeError, ValueError):
            fy_year = datetime.now().year
    else:
        fy_year = fy_start.year if hasattr(fy_start, "year") else int(str(fy_start)[:4])
    next_year = fy_year + 1

    return [
        {
            "label": "1st Instalment",
            "due_date": f"15 Jun {fy_year}",
            "cumulative_pct": 15,
            "note": "Pay ≥ 15% of estimated annual tax (Section 207(1)(a))",
        },
        {
            "label": "2nd Instalment",
            "due_date": f"15 Sep {fy_year}",
            "cumulative_pct": 45,
            "note": "Cumulative 45% — pay shortfall from 1st instalment",
        },
        {
            "label": "3rd Instalment",
            "due_date": f"15 Dec {fy_year}",
            "cumulative_pct": 75,
            "note": "Cumulative 75% — pay shortfall from earlier instalments",
        },
        {
            "label": "4th (Final) Instalment",
            "due_date": f"15 Mar {next_year}",
            "cumulative_pct": 100,
            "note": (
                "100% balance due. Presumptive taxpayers (44AD/44ADA): "
                "entire advance tax due on this date only."
            ),
        },
    ]
