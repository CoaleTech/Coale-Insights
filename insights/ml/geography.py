# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Geography / territory breakdown - pure-Ibis, drillable.

One dimension-parametrised aggregate powers the Customer Geography tab:
slice sales by ``territory``, ``item_group``, ``sales_person`` or
``customer`` and read revenue, gross profit, margin, distinct customers and
transactions for each. Any dimension row drills to ``customer`` by passing
the row's key back as a narrowing filter, so the same query serves both the
breakdown and the per-customer drill-down that navigates to Customer Detail.

Cost of goods reuses :func:`insights.api.ml.ibis_source.line_cogs` /
:func:`sle_cost` - the actual booked Stock Ledger valuation, matching the
Margins tab and ERPNext's Gross Profit report. Revenue is company-currency
``base_net_amount``. When the dimension is ``sales_person`` (or a salesperson
narrowing filter is set) each line is weighted by the invoice's Sales Team
``allocated_percentage`` so revenue and profit split proportionally between
the reps credited on the invoice, exactly as the Sales Reps tab attributes.
"""

from __future__ import annotations

from typing import Any

import ibis

from insights.api.ml.ibis_source import (
    company_filter,
    default_company,
    dn_cost,
    line_cogs,
    sle_cost,
    t,
)
from insights.api.ml.utils import parse_date_filter

DIMENSIONS = ("territory", "item_group", "sales_person", "customer")


def _scoped_invoices(date_filter: str, company: str | None):
    """Submitted, non-return Sales Invoices for the company + window."""
    si = (
        company_filter(t("Sales Invoice"), company)
        .filter(t("Sales Invoice").docstatus == 1)
        .filter(t("Sales Invoice").is_return == 0)
    )
    start, end = parse_date_filter(date_filter)
    if start is not None:
        si = si.filter(si.posting_date >= start.date())
    if end is not None:
        si = si.filter(si.posting_date <= end.date())
    return si


def compute_geography_breakdown(
    dimension: str = "territory",
    date_filter: str = "12m",
    company: str | None = None,
    territory: str | None = None,
    item_group: str | None = None,
    sales_person: str | None = None,
) -> dict[str, Any]:
    """Revenue / gross profit / customers by the requested dimension.

    ``territory`` / ``item_group`` / ``sales_person`` are optional narrowing
    filters (the drill-down context); passing all three with
    ``dimension="customer"`` lists the customers behind one slice.
    """
    dimension = dimension if dimension in DIMENSIONS else "territory"
    company = company or default_company()

    si = _scoped_invoices(date_filter, company)
    sii = t("Sales Invoice Item")
    dn = dn_cost()
    sle = sle_cost()
    svd_key = ibis.coalesce(sii.dn_detail.nullif(""), sii.name)
    base = (
        si.inner_join(sii, sii.parent == si.name)
        .left_join(dn, sii.dn_detail == dn.dn_name)
        .left_join(sle, svd_key == sle.vd_name)
    )

    # Sales Team is only joined when a salesperson is in play, to avoid
    # fanning invoice lines out by their credited reps for the other
    # dimensions. When joined, every line is weighted by the rep's share.
    use_team = dimension == "sales_person" or bool(sales_person)
    weight = None
    st = None
    if use_team:
        # Project to just the keys we need: Sales Team shares ~7 column
        # names with Sales Invoice (name, creation, owner, idx ...), which
        # collide on join. Same idiom as dn_cost()/sle_cost().
        stt = t("Sales Team")
        st = stt.filter(stt.parenttype == "Sales Invoice").select(
            st_parent=stt.parent,
            st_person=stt.sales_person,
            st_pct=stt.allocated_percentage,
        )
        base = base.inner_join(st, st.st_parent == si.name)
        weight = st.st_pct.fill_null(0) / 100.0

    if territory:
        base = base.filter(si.territory == territory)
    if item_group:
        base = base.filter(sii.item_group == item_group)
    if sales_person and st is not None:
        base = base.filter(st.st_person == sales_person)

    line_rev = sii.base_net_amount
    line_cost = line_cogs(sii, dn.dn_rate, sle.svd)
    if weight is not None:
        line_rev = line_rev * weight
        line_cost = line_cost * weight

    key_by = {
        "territory": si.territory,
        "item_group": sii.item_group,
        "customer": si.customer,
    }
    if st is not None:
        key_by["sales_person"] = st.st_person

    measures = dict(
        revenue=line_rev.sum(),
        cost=line_cost.sum(),
        customers=si.customer.nunique(),
        transactions=si.name.nunique(),
    )

    if dimension == "customer":
        grp = base.group_by(key=si.customer, label=si.customer_name)
    else:
        grp = base.group_by(key=key_by[dimension])
    df = grp.aggregate(**measures).execute()

    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        revenue = float(r["revenue"] or 0)
        cost = float(r["cost"] or 0)
        gp = revenue - cost
        key = r["key"]
        label = r["label"] if dimension == "customer" else key
        rows.append(
            {
                "key": key if key not in (None, "") else "",
                "label": (label or "Unassigned") if label not in (None, "") else "Unassigned",
                "revenue": round(revenue, 2),
                "gross_profit": round(gp, 2),
                "margin_pct": round(gp / revenue * 100, 1) if revenue else 0.0,
                "customers": int(r["customers"] or 0),
                "transactions": int(r["transactions"] or 0),
            }
        )
    rows.sort(key=lambda x: x["revenue"], reverse=True)

    total_rev = sum(x["revenue"] for x in rows)
    total_gp = sum(x["gross_profit"] for x in rows)
    # Distinct customers/transactions across the whole scope (not the sum of
    # per-row distincts, which double-counts customers spanning rows).
    totals_df = base.aggregate(
        customers=si.customer.nunique(), transactions=si.name.nunique()
    ).execute()
    return {
        "dimension": dimension,
        "rows": rows,
        "totals": {
            "revenue": round(total_rev, 2),
            "gross_profit": round(total_gp, 2),
            "margin_pct": round(total_gp / total_rev * 100, 1) if total_rev else 0.0,
            "customers": int(totals_df.iloc[0]["customers"] or 0),
            "transactions": int(totals_df.iloc[0]["transactions"] or 0),
        },
    }


def compute_geography_options(
    date_filter: str = "12m", company: str | None = None
) -> dict[str, list[str]]:
    """Distinct territory / item group / salesperson values for the filter
    selectors, scoped to the same company + window as the breakdown."""
    company = company or default_company()
    si = _scoped_invoices(date_filter, company)
    sii = t("Sales Invoice Item")

    terr = si.select(v=si.territory).distinct().execute()
    igrp = (
        si.inner_join(sii, sii.parent == si.name)
        .select(v=sii.item_group)
        .distinct()
        .execute()
    )
    stt = t("Sales Team")
    st = stt.filter(stt.parenttype == "Sales Invoice").select(
        st_parent=stt.parent, st_person=stt.sales_person
    )
    reps = (
        si.inner_join(st, st.st_parent == si.name)
        .select(v=st.st_person)
        .distinct()
        .execute()
    )

    def _clean(frame) -> list[str]:
        vals = {str(v) for v in frame["v"].tolist() if v not in (None, "")}
        return sorted(vals)

    return {
        "territories": _clean(terr),
        "item_groups": _clean(igrp),
        "sales_persons": _clean(reps),
    }
