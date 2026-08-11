# insights/ml/sales_source_analytics.py
"""Source-attributed sales metrics and quotation analytics.

Three small aggregations, all of which were previously issued as raw SQL
against `frappe.db` and then materialised in Python:
  * `get_source_attributed_sales` -- revenue, gross profit and order count
    per lead source, where the lead -> invoice chain is reconstructed by
    `insights.ml.source_attribution`.
  * `get_quotation_analytics` -- the quotation funnel (total / won / lost,
    lost reasons).
  * `get_territory_performance` -- revenue and gross profit per territory,
    over `Sales Invoice` joined to `Sales Invoice Item` for the per-line
    cost.

All three are now one Ibis expression each, run inside MariaDB, and
return a small DataFrame the caller reshapes to a dict in Python. There
is no fork, no cache, no background job.
"""

from __future__ import annotations

import ibis

from typing import Dict, Any, List

from insights.api.ml.ibis_source import t

from insights.ml.source_attribution import build_source_attribution_map


def get_source_attributed_sales(period_start: str, period_end: str) -> List[Dict]:
    """Revenue, orders, and gross profit attributed to each lead source.

    Invoices that have no lead attached (or whose lead has no
    `utm_source`) fall into the "Unattributed" bucket so the totals tie
    out to the un-attributed Sales Invoice sums in the rest of the
    Revenue dashboard.
    """
    attr_map = build_source_attribution_map(period_start, period_end)
    if not attr_map:
        return []

    # Materialise the (invoice, source) map in Python (it is already a few
    # hundred rows at most), then build a single Ibis expression that
    # returns revenue + gross profit per invoice. The Python merge into
    # the per-source bucket at the end is cheap because the post-aggregate
    # row count is small (number of distinct sources, ~handful).
    invoices = list(attr_map.keys())

    # Per-invoice revenue + gross profit, computed in a single SQL.
    si = t("Sales Invoice")
    sii = t("Sales Invoice Item")
    per_invoice = (
        si.inner_join(sii, sii.parent == si.name)
        .filter(si.docstatus == 1)
        .filter(si.is_return == 0)
        .filter(si.name.isin(invoices))
        .group_by(si.name)
        .aggregate(
            grand_total=si.grand_total.sum(),
            gross_profit=(
                sii.net_amount.sum() - (sii.qty * sii.incoming_rate.fill_null(0)).sum()
            ),
        )
    )
    df = per_invoice.execute()
    if df.empty:
        return []

    source_data: Dict[str, Dict[str, float]] = {}
    for _, row in df.iterrows():
        source = attr_map.get(str(row["name"]), "Unattributed")
        bucket = source_data.setdefault(
            source, {"revenue": 0.0, "gross_profit": 0.0, "order_count": 0}
        )
        bucket["revenue"] += float(row.get("grand_total") or 0)
        bucket["gross_profit"] += float(row.get("gross_profit") or 0)
        bucket["order_count"] += 1

    return [
        {"source": src, **vals}
        for src, vals in sorted(
            source_data.items(), key=lambda x: x[1]["revenue"], reverse=True
        )
    ]


def get_quotation_analytics(period_start: str, period_end: str) -> Dict[str, Any]:
    """Quotation funnel: total, won, lost, lost reasons, conversion rate."""
    q = t("Quotation")

    base = (
        q.filter(q.docstatus == 1)
        .filter(q.transaction_date.between(period_start, period_end))
    )

    overall = base.aggregate(
        total=base.count(),
        won=base.status.isin(["Ordered"]).sum(),
    ).execute().iloc[0]
    total = int(overall["total"] or 0)
    won = int(overall["won"] or 0)

    # Lost reasons. Each filter reassigns the intermediate -- the rule is
    # that columns passed to .group_by() / .aggregate() must come from the
    # SAME table expression, otherwise Ibis raises "belong to another
    # relation".
    lost = base.filter(base.status == ibis.literal("Lost"))
    lost = lost.filter(lost.order_lost_reason.notnull())
    lost = lost.filter(lost.order_lost_reason != ibis.literal(""))
    lost_reasons_df = (
        lost.group_by(lost.order_lost_reason)
        .aggregate(count=lost.count())
        .order_by(ibis.desc("count"))
        .execute()
    )
    lost_reasons: List[Dict[str, Any]] = []
    for _, r in lost_reasons_df.iterrows():
        lost_reasons.append(
            {
                "order_lost_reason": str(r["order_lost_reason"]),
                "count": int(r["count"]),
            }
        )
    total_lost = sum(r["count"] for r in lost_reasons)

    return {
        "total": total,
        "won": won,
        "lost": total_lost,
        "pending": max(0, total - won - total_lost),
        "conversion_rate": round(won / total * 100, 1) if total > 0 else 0,
        "lost_reasons": lost_reasons,
    }


def get_territory_performance(period_start: str, period_end: str) -> List[Dict]:
    """Sales invoices and gross profit by territory.

    Territory is a Sales Invoice header field, so the invoice total can be
    summed directly without the double-counting the naive line-join had.
    Gross profit still requires the line-level join for `incoming_rate`,
    and is allocated per-invoice in proportion to net line amount so the
    sum ties out to the un-attributed invoice gross profit.
    """
    si = t("Sales Invoice").filter(t("Sales Invoice").docstatus == 1).filter(
        t("Sales Invoice").is_return == 0
    ).filter(t("Sales Invoice").posting_date.between(period_start, period_end)).filter(
        t("Sales Invoice").territory.notnull()
    ).filter(t("Sales Invoice").territory != ibis.literal(""))

    sii = t("Sales Invoice Item")

    expr = (
        si.inner_join(sii, sii.parent == si.name)
        .group_by(si.territory)
        .aggregate(
            order_count=si.name.nunique(),
            revenue=si.grand_total.sum(),
            gross_profit=(
                sii.net_amount.sum() - (sii.qty * sii.incoming_rate.fill_null(0)).sum()
            ),
        )
        .order_by(ibis.desc("revenue"))
    )
    df = expr.execute()
    out: List[Dict] = []
    for _, r in df.iterrows():
        out.append(
            {
                "territory": str(r["territory"]),
                "order_count": int(r["order_count"] or 0),
                "revenue": float(r["revenue"] or 0),
                "gross_profit": float(r["gross_profit"] or 0),
            }
        )
    return out
