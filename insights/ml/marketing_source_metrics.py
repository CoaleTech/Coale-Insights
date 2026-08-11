# insights/ml/marketing_source_metrics.py
"""Lead source metrics for Marketing & CRM Intelligence.

Pure-Ibis rewrites of the old `frappe.db.sql` aggregates. The result of every
function here is at most a few dozen rows (one per source / territory), so the
final `.execute()` materialises a small DataFrame that's safe to touch with
plain Python.

Sources / territories are coalesced from empty strings to a literal
"Unattributed" / "Unassigned" so the UI can group and label them uniformly;
the source attribution chain walker in
``insights.ml.source_attribution`` is the canonical answer for "where did
this lead come from" when joining through Quotation -> Sales Order -> Sales
Invoice, but for the simpler question of "how many leads carry each tag on
their own record", this module is enough.
"""

from __future__ import annotations

from typing import Any, Dict, List

import ibis

from insights.api.ml.ibis_source import t

# _LEAD_OPEN_STATUSES in the API module matches the ERPNext Lead.status
# progression we surface in the funnel. Kept inline here so this module
# stays self-contained for the import that the API endpoint makes.
_LEAD_OPEN_STATUSES = ("Lead", "Open", "Inquiry", "Interested")
_HOT_STATUSES = ("Quotation", "Opportunity", "Interested")


def _rows(expr) -> List[Dict[str, Any]]:
    """Execute a small Ibis aggregate and return list-of-dict rows.

    The aggregate results fit in a handful of rows, so a pandas DataFrame
    is the right output format here even though we are otherwise avoiding
    pandas/sklearn in this module.
    """
    df = expr.execute()
    if df is None or len(df) == 0:
        return []
    return [
        {k: (None if v is None else v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def _scalar(expr, default: float = 0.0) -> float:
    df = expr.execute()
    if df is None or len(df) == 0:
        return default
    v = df.iloc[0, 0]
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def get_leads_by_source(period_start: str, period_end: str) -> List[Dict]:
    """Lead count grouped by source for the period [period_start, period_end]."""
    lead = t("Lead")
    # ``source`` is free-text: empty strings become 'Unattributed' so the
    # frontend can group and label uniformly.
    source_label = (
        ibis.cases(
            (lead["source"].notnull() & (lead["source"] != ""), lead["source"]),
            else_="Unattributed",
        )
    ).name("source")

    # Ibis bug class #1: after `.filter(...)` on a single base table, the
    # next `.group_by()` / `.aggregate()` must reference the FILTERED
    # relation, not the original `lead`. Capturing it in `lead_in_window`
    # makes the downstream aggregations resolve to the same projection.
    lead_in_window = lead.filter(
        (lead["docstatus"] < 2)
        & lead["creation"].between(period_start, period_end)
    )
    expr = (
        lead_in_window.group_by(source_label)
        .aggregate(leads=lead_in_window.count())
        .order_by(ibis.desc("leads"))
    )
    return _rows(expr)

def get_hot_leads_by_source(period_start: str, period_end: str) -> List[Dict]:
    """Hot leads (Quotation/Opportunity/Interested status) by source."""
    lead = t("Lead")
    source_label = (
        ibis.cases(
            (lead["source"].notnull() & (lead["source"] != ""), lead["source"]),
            else_="Unattributed",
        )
    ).name("source")

    hot = lead["status"].isin(_HOT_STATUSES)
    # See `get_leads_by_source` -- same single-table filter+aggregate fix.
    lead_in_window = lead.filter(
        (lead["docstatus"] < 2)
        & hot
        & lead["creation"].between(period_start, period_end)
    )
    expr = (
        lead_in_window.group_by(source_label)
        .aggregate(hot_leads=lead_in_window.count())
        .order_by(ibis.desc("hot_leads"))
    )
    return _rows(expr)

def get_source_costs(period_start: str, period_end: str) -> Dict[str, float]:
    """Approximate source cost from GL Entry postings tagged with UTM source.

    ERPNext does not have a first-class "campaign spend by source" link; the
    honest fallback is to look at GL Entry rows whose remarks / against
    account carry the UTM source, summed by debit. On sites without UTM
    bookkeeping the returned dict is empty -- which the API renders as a
    blank cost column rather than a fabricated number.
    """
    gl = t("GL Entry")
    if "utm_source" not in gl.columns:
        return {}

    expr = (
        gl.filter(
            (gl["docstatus"] == 1)
            & (gl["posting_date"].between(period_start, period_end))
            & gl["utm_source"].notnull()
            & (gl["utm_source"] != "")
        )
        .group_by(gl["utm_source"].name("source"))
        .aggregate(cost=gl["debit"].sum())
    )
    rows = _rows(expr)
    return {r["source"]: float(r.get("cost") or 0) for r in rows}


def get_cost_per_lead(period_start: str, period_end: str) -> List[Dict]:
    """Cost per lead for each source.

    Combines :func:`get_leads_by_source` (which provides the lead count) and
    :func:`get_source_costs` (which provides the spend). When a source has
    leads but no tracked spend the cost is reported as 0, not "unknown",
    because that is what the UI labels: the column is "cost" and the panel
    is "what we spent on ads tagged with this source", not "what leads
    actually cost us".
    """
    leads = get_leads_by_source(period_start, period_end)
    costs = get_source_costs(period_start, period_end)

    result: List[Dict[str, Any]] = []
    for row in leads:
        source = row.get("source") or "Unattributed"
        n_leads = int(row.get("leads") or 0)
        cost = float(costs.get(source, 0) or 0)
        result.append(
            {
                "source": source,
                "leads": n_leads,
                "cost": cost,
                "cost_per_lead": round(cost / n_leads, 2) if n_leads else 0,
            }
        )
    return result


def get_territory_leads(period_start: str, period_end: str) -> List[Dict]:
    """Lead count by territory, period-scoped."""
    lead = t("Lead")
    territory_label = (
        ibis.cases(
            (lead["territory"].notnull() & (lead["territory"] != ""), lead["territory"]),
            else_="Unassigned",
        )
    ).name("territory")

    # See `get_leads_by_source` -- same single-table filter+aggregate fix.
    lead_in_window = lead.filter(
        (lead["docstatus"] < 2)
        & lead["creation"].between(period_start, period_end)
    )
    expr = (
        lead_in_window.group_by(territory_label)
        .aggregate(
            leads=lead_in_window.count(),
            converted=lead_in_window["status"]
            .case()
            .when("Converted", 1)
            .else_(0)
            .end()
            .sum(),
        )
        .order_by(ibis.desc("leads"))
        .limit(20)
    )
    rows = _rows(expr)
    for r in rows:
        n_leads = int(r.get("leads") or 0)
        r["converted"] = int(r.get("converted") or 0)
        r["conversion_rate"] = round(r["converted"] / n_leads * 100, 1) if n_leads else 0
    return rows
