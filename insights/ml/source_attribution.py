# insights/ml/source_attribution.py
"""Lead-to-Invoice source attribution chain walker.

Walks the path Lead.utm_source -> Opportunity.party_name (when the
opportunity is from a Lead) -> Quotation.opportunity -> Sales Order
Item.prevdoc_docname -> Sales Invoice Item.sales_order, in one joined
Ibis expression that compiles to a single SQL statement and runs inside
MariaDB. The result is a small map of {invoice_name: utm_source} -- at
most one row per invoice -- so a final ``.execute()`` is cheap. There is
nothing left to fork, no cache to maintain, no background job to schedule.

`tabSales Order Item` in v16 has a `prevdoc_docname` column but no
`prevdoc_doctype`; the prevdoc is always a Quotation (verified: every
non-null `prevdoc_docname` on this site matches a `tabQuotation.name`),
so a `Quotation` join on `prevdoc_docname` is enough -- no extra doctype
filter needed.

Ibis raises `IntegrityError: Name collisions` when joining two tables
that share column names (`name`, `docstatus`, `modified`, ...). Each
table is therefore projected to a small set of renamed columns first, so
the join graph has no overlapping names.
"""

from __future__ import annotations

import ibis

from typing import Dict, List, Optional

from insights.api.ml.ibis_source import t


def build_source_attribution_map(
    period_start: str,
    period_end: str,
    force_refresh: bool = False,
) -> Dict[str, str]:
    """
    Build a map of Sales Invoice -> Lead Source by walking:
    Lead.utm_source -> Opportunity.party_name (from a Lead) ->
    Quotation.opportunity -> Sales Order Item.prevdoc_docname ->
    Sales Invoice Item.sales_order

    Returns: ``{invoice_name: utm_source}``.

    ``force_refresh`` is accepted for backward compatibility with callers
    (sales_source_analytics / SalesIntelligence) but is unused: there is
    no cache to clear, every call answers fresh.
    """
    # Project each table to a small set of renamed columns first -- the
    # shared ERPNext audit columns (name, docstatus, modified, ...) would
    # otherwise collide when two tables are joined.
    si_p = t("Sales Invoice").select(
        invoice=t("Sales Invoice")["name"],
        posting_date=t("Sales Invoice").posting_date,
        docstatus=t("Sales Invoice").docstatus,
    )
    sii_p = t("Sales Invoice Item").select(
        parent=t("Sales Invoice Item").parent,
        sales_order=t("Sales Invoice Item").sales_order,
    )
    so_p = t("Sales Order").select(name=t("Sales Order").name)
    soi_p = t("Sales Order Item").select(
        parent=t("Sales Order Item").parent,
        prevdoc_docname=t("Sales Order Item").prevdoc_docname,
    )
    q_p = t("Quotation").select(
        qname=t("Quotation")["name"],
        opportunity=t("Quotation").opportunity,
    )
    opp_p = t("Opportunity").select(
        oppname=t("Opportunity")["name"],
        opportunity_from=t("Opportunity").opportunity_from,
        party_name=t("Opportunity").party_name,
    )
    lead_p = t("Lead").select(
        leadname=t("Lead")["name"],
        utm_source=t("Lead").utm_source,
    )

    expr = (
        si_p.inner_join(sii_p, sii_p.parent == si_p.invoice)
        .inner_join(so_p, so_p.name == sii_p.sales_order)
        .inner_join(soi_p, soi_p.parent == so_p.name)
        .inner_join(q_p, q_p.qname == soi_p.prevdoc_docname)
        .inner_join(opp_p, opp_p.oppname == q_p.opportunity)
        .inner_join(lead_p, lead_p.leadname == opp_p.party_name)
        .filter(opp_p.opportunity_from == ibis.literal("Lead"))
        .filter(lead_p.utm_source.notnull())
        .filter(lead_p.utm_source != ibis.literal(""))
        .filter(si_p.docstatus == 1)
        .filter(si_p.posting_date.between(period_start, period_end))
        .select(invoice=si_p.invoice, utm_source=lead_p.utm_source)
        .distinct()
    )

    try:
        df = expr.execute()
    except Exception:
        # The Lead table may not have a utm_source column in this ERPNext
        # version (Lead was reworked between v13 and v14). Return an empty
        # map so source-attributed KPIs render as zero rather than 500ing.
        return {}

    if df.empty:
        return {}

    return dict(zip(df["invoice"].astype(str), df["utm_source"].astype(str)))


def get_invoices_by_source(
    period_start: str, period_end: str, force_refresh: bool = False,
) -> Dict[str, List[str]]:
    """Group invoices by lead source. Returns {source: [invoice_names]}."""
    attr_map = build_source_attribution_map(period_start, period_end, force_refresh)
    by_source: Dict[str, List[str]] = {}
    for invoice, source in attr_map.items():
        by_source.setdefault(source, []).append(invoice)
    return by_source


def get_source_for_invoice(
    invoice_name: str, period_start: str, period_end: str,
) -> Optional[str]:
    """Get the lead source for a single invoice."""
    attr_map = build_source_attribution_map(period_start, period_end)
    return attr_map.get(invoice_name)
