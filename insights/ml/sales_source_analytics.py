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

from insights.api.ml.ibis_source import dn_cost, line_cogs, t

from insights.ml.source_attribution import build_source_attribution_map


def get_source_attributed_sales(period_start: str, period_end: str) -> List[Dict]:
    """Revenue, orders, and gross profit attributed to each lead source.

    Every Sales Invoice in the period lands in some bucket. Only invoices
    traceable through the full Lead -> Opportunity -> Quotation -> Sales
    Order -> Sales Invoice chain resolve to a real source (measured 4.6% of
    invoices on this site: 169 of 3,696); every other invoice goes to
    "Unattributed" so the per-source totals sum to the same revenue as the
    rest of the Revenue dashboard instead of silently reporting on a ~5%
    slice of it.

    The previous version restricted the per-invoice query itself to
    `si.name.isin(attr_map.keys())`, so `attr_map.get(name, "Unattributed")`
    could never actually miss -- every row it saw was, by construction,
    already a key in `attr_map`. "Unattributed" was reachable in neither
    this function's output nor (when `attr_map` was empty) even as a
    fallback, since an empty map short-circuited to `[]` before any
    invoice was read.
    """
    attr_map = build_source_attribution_map(period_start, period_end)

    si = t("Sales Invoice")
    sii = t("Sales Invoice Item")
    base = (
        si.filter(si.docstatus == 1)
        .filter(si.is_return == 0)
        .filter(si.posting_date.between(period_start, period_end))
    )

    # Revenue: `grand_total` is a Sales Invoice HEADER field. Read it off
    # `si` directly, with no join -- joining to `Sales Invoice Item` first
    # (as the previous version did) replicates the header row once per line
    # item, and `.sum()` over that then multiplies every invoice's total by
    # its own line count. Measured on this site: reported revenue 242.17M
    # against a raw `SUM(grand_total)` ground truth of 177.30M for the same
    # 12-month window (1.37x inflation, tracking the ~1.3 lines/invoice
    # average) -- order_count tied out exactly because that was counted in
    # Python per DataFrame row post-`group_by(si.name)`, so only the summed
    # currency columns were affected.
    revenue_df = base.select(name=si.name, grand_total=si.grand_total).execute()
    if revenue_df.empty:
        return []

    # Gross profit genuinely is line-level (`net_amount`, `incoming_rate`),
    # so summing it per invoice across the invoice's own joined lines is
    # correct -- unlike `grand_total`, these values are not replicated
    # header fields.
    dn = dn_cost()
    gp_df = (
        si.inner_join(sii, sii.parent == si.name)
        .left_join(dn, sii.dn_detail == dn.dn_name)
        .filter(si.docstatus == 1)
        .filter(si.is_return == 0)
        .filter(si.posting_date.between(period_start, period_end))
        .group_by(si.name)
        .aggregate(
            gross_profit=sii.net_amount.sum() - line_cogs(sii, dn.dn_rate).sum()
        )
        .execute()
    )
    gp_map = (
        dict(zip(gp_df["name"].astype(str), gp_df["gross_profit"].astype(float), strict=True))
        if not gp_df.empty else {}
    )

    source_data: Dict[str, Dict[str, float]] = {}
    for _, row in revenue_df.iterrows():
        name = str(row["name"])
        source = attr_map.get(name, "Unattributed")
        bucket = source_data.setdefault(
            source, {"revenue": 0.0, "gross_profit": 0.0, "order_count": 0}
        )
        bucket["revenue"] += float(row.get("grand_total") or 0)
        bucket["gross_profit"] += gp_map.get(name, 0.0)
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
        # Count all `Lost` rows here, regardless of whether the
        # salesperson filled in a reason. The previous version grouped
        # on `order_lost_reason` and took the SUM of that, silently
        # dropping ~half of lost quotations on this site (542 total
        # Lost, 287 with a reason, 255 with NULL/empty reason -- the
        # reported `lost` was 287, leaving 255 unaccounted for in the
        # total/won/lost/pending sum).
        lost_all=base.status.isin(["Lost"]).sum(),
    ).execute().iloc[0]
    total = int(overall["total"] or 0)
    won = int(overall["won"] or 0)
    total_lost = int(overall["lost_all"] or 0)

    # Lost reasons come from the structured `Quotation Lost Reason Detail`
    # child table (each row links to a controlled `Quotation Lost Reason`
    # master), NOT the free-text `order_lost_reason` header field. That
    # header field is a per-quote note -- on this site 287 lost quotes filled
    # it and 282 of those values are distinct -- so grouping on it produced
    # ~280 count-1 slices of unusable noise (multi-line rep memos like
    # "acetic purchase 85\nnot sure about with billing..."). The child table
    # resolves to a clean 17-reason distribution led by Price (339),
    # Transport (76), Sample (41). A quote may carry several reasons, so each
    # reason is counted once per distinct quotation it appears on.
    lost_names = base.filter(base.status == ibis.literal("Lost")).select(name=q.name)
    lrd = t("Quotation Lost Reason Detail")
    lost_reasons_df = (
        lrd.inner_join(lost_names, lrd.parent == lost_names.name)
        .filter(lrd.lost_reason.notnull())
        .filter(lrd.lost_reason != ibis.literal(""))
        .group_by(lrd.lost_reason)
        .aggregate(count=lrd.parent.nunique())
        .order_by(ibis.desc("count"))
        .execute()
    )
    lost_reasons: List[Dict[str, Any]] = []
    for _, r in lost_reasons_df.iterrows():
        lost_reasons.append(
            {
                "order_lost_reason": str(r["lost_reason"]),
                "count": int(r["count"]),
            }
        )

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

    Territory and `grand_total` are both Sales Invoice header fields.
    Revenue is aggregated straight off `si` with no join; joining to
    `Sales Invoice Item` first (the previous version's `inner_join` ->
    `group_by(territory)` -> `grand_total.sum()`, despite what its old
    docstring claimed) replicates each invoice's header row once per line
    item, so the sum multiplies every invoice's total by its own line
    count. Measured on this site: reported revenue 239.48M against a raw
    per-invoice ground truth of 175.24M for the same window (1.37x
    inflation, tracking the ~1.3 lines/invoice average).

    Gross profit still requires the line-level join for `incoming_rate`;
    grouping the joined result by territory is correct there because
    those fields are genuinely per-line, not a replicated header value.
    """
    si = t("Sales Invoice")
    sii = t("Sales Invoice Item")
    base = (
        si.filter(si.docstatus == 1)
        .filter(si.is_return == 0)
        .filter(si.posting_date.between(period_start, period_end))
        .filter(si.territory.notnull())
        .filter(si.territory != ibis.literal(""))
    )

    revenue_expr = base.group_by(si.territory).aggregate(
        order_count=si.name.nunique(),
        revenue=si.grand_total.sum(),
    )
    revenue_df = revenue_expr.execute()
    if revenue_df.empty:
        return []

    dn = dn_cost()
    gp_expr = (
        base.inner_join(sii, sii.parent == si.name)
        .left_join(dn, sii.dn_detail == dn.dn_name)
        .group_by(si.territory)
        .aggregate(
            gross_profit=sii.net_amount.sum() - line_cogs(sii, dn.dn_rate).sum()
        )
    )
    gp_df = gp_expr.execute()
    gp_map = (
        dict(zip(gp_df["territory"].astype(str), gp_df["gross_profit"].astype(float), strict=True))
        if not gp_df.empty else {}
    )

    out: List[Dict] = []
    for _, r in revenue_df.iterrows():
        territory = str(r["territory"])
        out.append(
            {
                "territory": territory,
                "order_count": int(r["order_count"] or 0),
                "revenue": float(r["revenue"] or 0),
                "gross_profit": gp_map.get(territory, 0.0),
            }
        )
    out.sort(key=lambda x: x["revenue"], reverse=True)
    return out
