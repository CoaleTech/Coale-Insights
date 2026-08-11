from __future__ import annotations
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence — Analytics & Forecasting"""

from datetime import datetime
from typing import Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np



def get_tax_forecast(intelligence, start: str, end: str) -> Dict[str, Any]:
    """Forecast next 3 months GST liability using linear regression on monthly data."""
    import numpy as np
    try:
        from sklearn.linear_model import LinearRegression
    except ImportError:
        return {
            "forecast": [],
            "note": "scikit-learn not installed; forecast unavailable",
        }

    from insights.ml.india_tax_intelligence.data import get_gst_output_tax, get_gst_input_tax

    output_tax = get_gst_output_tax(intelligence, start, end)
    input_tax = get_gst_input_tax(intelligence, start, end)

    if not output_tax:
        return {
            "forecast": [],
            "note": "Insufficient historical data for forecasting",
        }

    # Build monthly net GST series
    months = []
    net_gst = []
    for o in output_tax:
        month = o.get("month")
        out_total = float(o.get("cgst", 0) + o.get("sgst", 0) + o.get("igst", 0))
        inp_total = 0.0
        for i in input_tax:
            if i.get("month") == month:
                inp_total = float(i.get("cgst", 0) + i.get("sgst", 0) + i.get("igst", 0))
                break
        months.append(month)
        net_gst.append(out_total - inp_total)

    n = len(months)
    if n < 3:
        return {
            "forecast": [],
            "note": "Need at least 3 months of data for forecasting",
        }

    X = np.arange(n).reshape(-1, 1)
    y = np.array(net_gst)
    model = LinearRegression()
    model.fit(X, y)

    forecast = []
    for i in range(1, 4):
        next_month_idx = n + i - 1
        pred = model.predict([[next_month_idx]])[0]
        forecast.append({
            "month_offset": i,
            "projected_net_gst": round(float(pred), 2),
        })

    return {
        "forecast": forecast,
        "trend_slope": round(float(model.coef_[0]), 2),
        "r_squared": round(float(model.score(X, y)), 4) if n > 1 else None,
        "note": "Linear regression on monthly net GST",
    }


def get_advance_tax_schedule(intelligence) -> List[Dict[str, Any]]:
    """Return advance tax instalments with actual calendar dates for India.

    Statutory basis:
    - Section 208 : mandatory when estimated tax liability ≥ ₹10,000
    - Section 207  : senior citizens (60+) with no business income are exempt
    - Section 234B : 1 % p.m. interest if < 90 % of liability paid by 31 Mar
    - Section 234C : 1 % p.m. interest for delay in quarterly instalments
    - Presumptive taxpayers (Section 44AD/44ADA): entire tax due on 15 Mar
    """
    fy_doc = intelligence._get_fiscal_dates()
    fy_start = fy_doc.get("year_start_date")

    if not fy_start:
        fy_start = datetime(datetime.now().year, 4, 1).date()

    # India FY = April–March; advance tax calendar year = year when FY starts
    fy_year: int = fy_start.year if hasattr(fy_start, "year") else int(str(fy_start)[:4])
    next_year: int = fy_year + 1

    return [
        {
            "label": "1st Instalment",
            "due_date": f"15 Jun {fy_year}",
            "cumulative_pct": 15,
            "note": "Pay ≥ 15 % of estimated annual tax (Section 207(1)(a))",
        },
        {
            "label": "2nd Instalment",
            "due_date": f"15 Sep {fy_year}",
            "cumulative_pct": 45,
            "note": "Cumulative 45 % — pay shortfall from 1st instalment",
        },
        {
            "label": "3rd Instalment",
            "due_date": f"15 Dec {fy_year}",
            "cumulative_pct": 75,
            "note": "Cumulative 75 % — pay shortfall from earlier instalments",
        },
        {
            "label": "4th (Final) Instalment",
            "due_date": f"15 Mar {next_year}",
            "cumulative_pct": 100,
            "note": (
                "100 % balance due. Presumptive taxpayers (44AD/44ADA): "
                "entire advance tax due on this date only."
            ),
        },
    ]
