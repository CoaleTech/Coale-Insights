# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Marketing Intelligence API Endpoints.

Pure-Ibis rewrite of the marketing surface. Every aggregate compiles to one
SQL statement and runs inside MariaDB; the Python process only materialises
the final, already-aggregated result (a few dozen rows in the worst case).

The two-line ``from insights.api.ml.utils import run`` import at the top of
``run_lambda`` calls does the same role the older hand-rolled
``try / except / return success-or-error`` block did for every endpoint
elsewhere: a single call, a single ``success()`` envelope, with
``frappe.PermissionError`` re-raised unchanged and any other exception
turned into a logged ``error()`` response. ``get_marketing_overview`` (the
full dashboard payload) is served from cache and recomputed by a background
job per period (``cached_run``); everything else here has no cache and no
background work.
"""

from __future__ import annotations

from typing import Any, Dict, List

import frappe
import ibis
from frappe import _

from insights.api.ml.ibis_source import t
from insights.api.ml.utils import cached_run, run
from insights.api.response import success

# ────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ────────────────────────────────────────────────────────────────────────────


# ERPNext Lead.status values, ordered along the CRM funnel. `Lead.status` is
# ERPNext's own progression field, so it is the honest funnel source rather
# than a synthesised join across Lead/Opportunity/Quotation.
_LEAD_OPEN_STATUSES = ("Lead", "Open", "Inquiry", "Interested")
_LEAD_WON_STATUSES = ("Converted",)


def _rows(expr) -> List[Dict[str, Any]]:
    """Execute a small Ibis aggregate and return list-of-dict rows.

    Aggregates here have a single-digit to a few-dozen rows, so a pandas
    DataFrame is the right return format even though we otherwise avoid
    pandas in the rest of the ML layer.
    """
    df = expr.execute()
    if df is None or len(df) == 0:
        return []
    return [
        {k: (None if v is None else v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def _period_start(period: str):
    """Resolve a period keyword to an inclusive start ``date`` (datetime.date).

    Returns a ``datetime.date`` rather than a string so Ibis can pass it
    through as a real bound parameter (verified against MySQL backend).
    """
    from datetime import datetime

    from frappe.utils import add_months, nowdate

    now = datetime.now()
    if period == "MTD":
        return now.replace(day=1).date()
    if period == "QTD":
        quarter_start = ((now.month - 1) // 3) * 3 + 1
        return now.replace(month=quarter_start, day=1).date()
    if period == "YTD":
        return now.replace(month=1, day=1).date()
    # default: trailing 12 months
    end = nowdate()
    return add_months(end, -12)


def _add_months_safe(date_obj, months: int):
    """Shift a date-like by months, returning a ``datetime.date``."""
    from frappe.utils import add_months

    return add_months(date_obj, months)


def _company_currency() -> str:
    """Resolve the company reporting currency for currency display."""
    company = frappe.defaults.get_user_default("Company")
    return (
        frappe.db.get_value("Company", company, "default_currency") if company else None
    ) or frappe.db.get_default("currency") or ""


# ────────────────────────────────────────────────────────────────────────────
# Source / territory / cost-per-lead (the smaller endpoints)
# ────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def source_metrics(period: str = "YTD") -> Dict[str, Any]:
    """Get lead source metrics including cost per lead."""
    from datetime import datetime

    from insights.ml.marketing_source_metrics import (
        get_cost_per_lead,
        get_hot_leads_by_source,
        get_leads_by_source,
        get_territory_leads,
    )

    end_date = datetime.now().date()
    if period == "MTD":
        start_date = end_date.replace(day=1)
    elif period == "QTD":
        current_month = end_date.month
        quarter_start_month = ((current_month - 1) // 3) * 3 + 1
        start_date = end_date.replace(month=quarter_start_month, day=1)
    elif period == "YTD":
        start_date = end_date.replace(month=1, day=1)
    else:  # TTM
        start_date = _add_months_safe(end_date, -12)

    return success({
        "leads_by_source": get_leads_by_source(start_date, end_date),
        "hot_leads_by_source": get_hot_leads_by_source(start_date, end_date),
        "cost_per_lead": get_cost_per_lead(start_date, end_date),
        "territory_leads": get_territory_leads(start_date, end_date),
    })


@frappe.whitelist()
def cost_per_lead(period: str = "YTD") -> Dict[str, Any]:
    """Get cost per lead by source."""
    from datetime import datetime

    from insights.ml.marketing_source_metrics import get_cost_per_lead

    end_date = datetime.now().date()
    if period == "MTD":
        start_date = end_date.replace(day=1)
    elif period == "QTD":
        current_month = end_date.month
        quarter_start_month = ((current_month - 1) // 3) * 3 + 1
        start_date = end_date.replace(month=quarter_start_month, day=1)
    elif period == "YTD":
        start_date = end_date.replace(month=1, day=1)
    else:
        start_date = _add_months_safe(end_date, -12)

    return success(get_cost_per_lead(start_date, end_date))


@frappe.whitelist()
def territory_leads(period: str = "YTD") -> Dict[str, Any]:
    """Get lead count by territory."""
    from datetime import datetime

    from insights.ml.marketing_source_metrics import get_territory_leads

    end_date = datetime.now().date()
    if period == "MTD":
        start_date = end_date.replace(day=1)
    elif period == "QTD":
        current_month = end_date.month
        quarter_start_month = ((current_month - 1) // 3) * 3 + 1
        start_date = end_date.replace(month=quarter_start_month, day=1)
    elif period == "YTD":
        start_date = end_date.replace(month=1, day=1)
    else:
        start_date = _add_months_safe(end_date, -12)

    return success(get_territory_leads(start_date, end_date))


# ────────────────────────────────────────────────────────────────────────────
# Overview
# ────────────────────────────────────────────────────────────────────────────


def _build_marketing_funnel(
    lead_totals: dict,
    quote_totals: list,
    won: dict,
    open_value: float,
    decided_value: float,
    won_value: float,
    total: int,
    converted: int,
) -> list:
    """Build the 4-stage marketing funnel with conversion-from-prev rates.

    Pure function of already-fetched query results -- no I/O, unit-testable
    without a DB fixture.
    """
    funnel = [
        {"label": _("Leads"), "count": total, "value": None},
        {
            "label": _("Reached Opportunity"),
            "count": int(lead_totals.get("at_opportunity") or 0)
            + int(lead_totals.get("at_quotation") or 0)
            + converted,
            "value": None,
        },
        {
            "label": _("Quoted"),
            "count": sum(int(r["count"] or 0) for r in quote_totals),
            "value": open_value + decided_value,
        },
        {
            "label": _("Ordered"),
            "count": int(won.get("count") or 0),
            "value": won_value,
        },
    ]
    # Conversion is only meaningful between stages counted off the SAME base.
    # Stages 0-1 both come from Lead.status; stages 2-3 both come from
    # Quotation. Stage 1 -> 2 crosses from leads to quotation records, and
    # a quotation can exist for a lead that never reached status 'Opportunity',
    # so that hop is left null rather than reported as a >100% rate.
    _COMPARABLE_TO_PREV = {1, 3}
    for i, stage in enumerate(funnel):
        prev = funnel[i - 1]["count"] if i in _COMPARABLE_TO_PREV else None
        stage["conversion_from_prev"] = (
            round(stage["count"] / prev * 100, 1) if prev else None
        )
    return funnel


def _generate_marketing_alerts(
    total: int,
    open_leads: int,
    expired_value: float,
    won_value: float,
    trend: list,
    source_rows: list,
    days_stale,
) -> list:
    """Threshold-based alert generation. Pure function of already-fetched
    query results -- no I/O, unit-testable without a DB fixture.
    """
    alerts = []
    if total and open_leads / total > 0.5:
        alerts.append({
            "severity": "high",
            "title": _("Funnel is bottlenecked at intake"),
            "description": _("{0} of {1} leads ({2}%) are still unqualified.").format(
                open_leads, total, round(open_leads / total * 100)
            ),
        })
    if expired_value > won_value and expired_value > 0:
        alerts.append({
            "severity": "critical",
            "title": _("Quotations are expiring unconverted"),
            "description": _("{0} expired versus {1} ordered in this period.").format(
                frappe.format_value(expired_value, {"fieldtype": "Currency"}),
                frappe.format_value(won_value, {"fieldtype": "Currency"}),
            ),
        })
    if len(trend) >= 4:
        recent = sum(int(r["leads"] or 0) for r in trend[-3:]) / 3
        earlier = sum(int(r["leads"] or 0) for r in trend[:3]) / 3
        if earlier > 0 and recent < earlier * 0.5:
            alerts.append({
                "severity": "critical",
                "title": _("Lead volume has collapsed"),
                "description": _("Averaging {0} per month, down from {1}.").format(
                    round(recent, 1), round(earlier, 1)
                ),
            })
    # Concentration is measured against the same all-time base as
    # `source_performance`, so the percentage on screen matches the panel.
    source_total = sum(int(r["leads"] or 0) for r in source_rows)
    concentration = max((int(r["leads"] or 0) for r in source_rows), default=0)
    if source_total and concentration / source_total > 0.6:
        top = max(source_rows, key=lambda r: int(r["leads"] or 0))
        alerts.append({
            "severity": "medium",
            "title": _("Lead supply is concentrated in one channel"),
            "description": _("{0} accounts for {1}% of all leads, so the pipeline depends on a single source.").format(
                top["source"], round(concentration / source_total * 100)
            ),
        })
    if days_stale is not None and days_stale > 60:
        alerts.insert(0, {
            "severity": "critical",
            "title": _("CRM data is not being maintained"),
            "description": _("The most recent lead or quotation is {0} days old, so period figures below are empty by definition.").format(
                days_stale
            ),
        })
    return alerts


@frappe.whitelist()
def get_marketing_overview(period: str = "YTD") -> Dict[str, Any]:
    """Marketing and CRM overview built from ERPNext's built-in CRM.

    Sources are the standard ERPNext doctypes: Lead, Opportunity and
    Quotation. The separate Frappe CRM app (`CRM Lead` / `CRM Deal`) is
    intentionally NOT read; on this site those tables are empty and
    ERPNext's CRM module holds the real records.

    Deliberately omitted, because the underlying data makes them vanity
    panels:
      * anything keyed on `Opportunity.opportunity_amount`, which is 0 for
        every row on this site. Pipeline value comes from
        Quotation.base_grand_total, which is populated.
      * campaign-level reporting, with a single Campaign record in
        existence.
    """
    # Whitelisted endpoints get no automatic doctype gate, so check
    # explicitly before reading any CRM data.
    frappe.has_permission("Lead", "read", throw=True)

    start = _period_start(period)
    return cached_run(
        lambda: run(lambda: _compute_marketing_overview(start, period), "Marketing overview"),
        cache_key=f"insights_ml_marketing_overview:{period}",
    )


def _compute_marketing_overview(start, period: str) -> Dict[str, Any]:
    """Ibis-backed computation of the marketing overview payload.

    All aggregates below compile to a single SQL statement each and run
    inside MariaDB; the Python process only ever touches a handful of
    aggregated rows. ``start`` is a ``datetime.date`` so Ibis binds it as
    a proper parameter.
    """
    # `source` was dropped from both doctypes' meta in favour of UTM
    # tracking (`utm_source`), but this site never adopted UTM: `utm_source`
    # is 0% populated across 3,660 leads / 4,383 quotations, while the
    # orphaned `source` column (still physically in the table -- Frappe
    # does not drop columns when a field is removed) is 97.8% / 94.9%
    # populated with real channel data (IndiaMart, Trade India, Google, ...).
    # `extra_columns` reads it back without weakening row-level permissions.
    lead = t("Lead", extra_columns=("source",))
    quote = t("Quotation", extra_columns=("source",))

    # ── Funnel. Counts come from Lead.status, value from Quotation. ────────
    # `creation >= %s` accepts a date or datetime; ibis binds whichever we
    # pass. We use a stringified form for the period-window comparison
    # because `creation` is a DATETIME and `start` is a DATE -- the
    # datetime string comparison is exact.
    start_str = str(start)

    lead_total = lead.filter(lead["docstatus"] < 2)
    lead_totals = {
        "total": 0,
        "in_period": 0,
        "open_leads": 0,
        "at_opportunity": 0,
        "at_quotation": 0,
        "converted": 0,
        "lost": 0,
    }
    # Pull the individual aggregate components back out of the combined
    # aggregate ("total submitted leads", "how many entered this period",
    # etc.). Single-row df, so .iloc[0] is the only row; the defaults
    # above stand if the query somehow comes back empty.
    lead_total_df = (
        lead_total.aggregate(
            total=lead_total.count(),
            in_period=((lead_total["creation"] >= start_str).cast("int").sum()),
            open_leads=(lead_total["status"].isin(_LEAD_OPEN_STATUSES).cast("int").sum()),
            at_opportunity=((lead_total["status"] == "Opportunity").cast("int").sum()),
            at_quotation=((lead_total["status"] == "Quotation").cast("int").sum()),
            converted=((lead_total["status"] == "Converted").cast("int").sum()),
            lost=((lead_total["status"] == "Lost Quotation").cast("int").sum()),
        ).execute()
    )
    if lead_total_df is not None and len(lead_total_df):
        r = lead_total_df.iloc[0]
        lead_totals = {
            "total": int(r.get("total") or 0),
            "in_period": int(r.get("in_period") or 0),
            "open_leads": int(r.get("open_leads") or 0),
            "at_opportunity": int(r.get("at_opportunity") or 0),
            "at_quotation": int(r.get("at_quotation") or 0),
            "converted": int(r.get("converted") or 0),
            "lost": int(r.get("lost") or 0),
        }

    # Open pipeline value is a CURRENT-STATE question: a Draft quotation is
    # live money regardless of when it was raised, so this is not period
    # filtered either. Period-scoped intake lives in `kpis.new_leads`.
    quote_total = quote.filter(quote["docstatus"] < 2)
    quote_totals_df = (
        quote_total
        .group_by(quote_total["status"].name("status"))
        .aggregate(
            count=quote_total.count(),
            value=quote_total["base_grand_total"].sum(),
        )
        .execute()
    )
    quote_totals = []
    if quote_totals_df is not None and len(quote_totals_df):
        for _, r in quote_totals_df.iterrows():
            quote_totals.append({
                "status": r.get("status"),
                "count": int(r.get("count") or 0),
                "value": float(r.get("value") or 0),
            })

    # How current is the CRM at all? A dashboard over abandoned data must
    # say so rather than rendering a wall of confident zeros.
    freshness_df = (
        lead.aggregate(latest_lead=lead["creation"].max())
        .cross_join(
            quote.aggregate(latest_quotation=quote["creation"].max())
        )
        .execute()
    )
    latest_lead = None
    latest_quotation = None
    if freshness_df is not None and len(freshness_df):
        r = freshness_df.iloc[0]
        latest_lead = r.get("latest_lead")
        latest_quotation = r.get("latest_quotation")

    from frappe.utils import date_diff, nowdate

    latest = max([d for d in (latest_lead, latest_quotation) if d], default=None)
    days_stale = date_diff(nowdate(), latest.date()) if latest else None
    by_status = {r["status"]: r for r in quote_totals}
    won = by_status.get("Ordered", {})
    expired = by_status.get("Expired", {})
    draft = by_status.get("Draft", {})

    won_value = float(won.get("value") or 0)
    open_value = float(draft.get("value") or 0)
    expired_value = float(expired.get("value") or 0)
    decided_value = won_value + expired_value + float(
        by_status.get("Lost", {}).get("value") or 0
    )

    # ── Source performance. The one panel that answers "which channel ──
    #    actually earns money", not just which one is loudest. ─────────────
    # Channel quality is a STRUCTURAL question ("which source converts"),
    # not a this-month question, so these two are deliberately unfiltered
    # by period. Filtering them would empty the panel whenever the period
    # window happens to miss the data, which tells the operator nothing.
    source_label = (
        ibis.cases(
            (lead_total["source"].notnull() & (lead_total["source"] != ""), lead_total["source"]),
            else_="Unattributed",
        )
    ).name("source")

    source_rows_df = (
        lead_total
        .group_by(source_label)
        .aggregate(
            leads=lead_total.count(),
            converted=((lead_total["status"] == "Converted").cast("int").sum()),
        )
        .order_by(ibis.desc("leads"))
        .limit(12)
        .execute()
    )
    source_rows = []
    if source_rows_df is not None and len(source_rows_df):
        for _, r in source_rows_df.iterrows():
            source_rows.append({
                "source": r.get("source") or "Unattributed",
                "leads": int(r.get("leads") or 0),
                "converted": int(r.get("converted") or 0),
            })

    quote_source_label = (
        ibis.cases(
            (quote_total["source"].notnull() & (quote_total["source"] != ""), quote_total["source"]),
            else_="Unattributed",
        )
    ).name("source")

    quote_by_source_df = (
        quote_total
        .group_by(quote_source_label)
        .aggregate(
            quotations=quote_total.count(),
            quoted_value=quote_total["base_grand_total"].sum(),
            won_value=(
                ibis.cases(
                    (quote_total["status"] == "Ordered", quote_total["base_grand_total"]),
                    else_=0,
                ).sum()
            ),
        )
        .execute()
    )
    quote_by_source = []
    if quote_by_source_df is not None and len(quote_by_source_df):
        for _, r in quote_by_source_df.iterrows():
            quote_by_source.append({
                "source": r.get("source") or "Unattributed",
                "quotations": int(r.get("quotations") or 0),
                "quoted_value": float(r.get("quoted_value") or 0),
                "won_value": float(r.get("won_value") or 0),
            })

    quote_map = {r["source"]: r for r in quote_by_source}
    for row in source_rows:
        q = quote_map.get(row["source"], {})
        leads = int(row["leads"] or 0)
        row["quotations"] = int(q.get("quotations") or 0)
        row["quoted_value"] = float(q.get("quoted_value") or 0)
        row["won_value"] = float(q.get("won_value") or 0)
        row["conversion_rate"] = round(
            (int(row["converted"] or 0) / leads * 100) if leads else 0, 1
        )
        row["value_per_lead"] = round(row["won_value"] / leads, 2) if leads else 0

    # ── Trend. Answers "what changed". ────────────────────────────────────
    trend_start = _add_months_safe(start, -12)
    lead_trend = lead_total.filter(lead_total["creation"] >= str(trend_start))
    period_expr = lead_trend["creation"].strftime("%Y-%m")
    trend_df = (
        lead_trend
        .group_by(period_expr.name("month"))
        .aggregate(
            leads=lead_trend.count(),
            converted=((lead_trend["status"] == "Converted").cast("int").sum()),
        )
        .order_by("month")
        .execute()
    )
    trend = []
    if trend_df is not None and len(trend_df):
        for _, r in trend_df.iterrows():
            trend.append({
                "month": str(r.get("month") or ""),
                "leads": int(r.get("leads") or 0),
                "converted": int(r.get("converted") or 0),
            })

    pipeline_df = (
        lead_total
        .group_by(
            ibis.cases(
                (lead_total["status"].notnull() & (lead_total["status"] != ""), lead_total["status"]),
                else_="Unset",
            ).name("status")
        )
        .aggregate(count=lead_total.count())
        .order_by(ibis.desc("count"))
        .execute()
    )
    pipeline = []
    if pipeline_df is not None and len(pipeline_df):
        for _, r in pipeline_df.iterrows():
            pipeline.append({
                "status": r.get("status") or "Unset",
                "count": int(r.get("count") or 0),
            })

    territory_df = (
        lead_total
        .group_by(
            ibis.cases(
                (lead_total["territory"].notnull() & (lead_total["territory"] != ""), lead_total["territory"]),
                else_="Unassigned",
            ).name("territory")
        )
        .aggregate(
            leads=lead_total.count(),
            converted=((lead_total["status"] == "Converted").cast("int").sum()),
        )
        .order_by(ibis.desc("leads"))
        .limit(10)
        .execute()
    )
    territory = []
    if territory_df is not None and len(territory_df):
        for _, r in territory_df.iterrows():
            territory.append({
                "territory": r.get("territory") or "Unassigned",
                "leads": int(r.get("leads") or 0),
                "converted": int(r.get("converted") or 0),
            })

    owner_df = (
        lead_total
        .group_by(
            ibis.cases(
                (lead_total["lead_owner"].notnull() & (lead_total["lead_owner"] != ""), lead_total["lead_owner"]),
                else_="Unassigned",
            ).name("owner")
        )
        .aggregate(
            leads=lead_total.count(),
            converted=((lead_total["status"] == "Converted").cast("int").sum()),
        )
        .order_by(ibis.desc("leads"))
        .limit(10)
        .execute()
    )
    owners = []
    if owner_df is not None and len(owner_df):
        for _, r in owner_df.iterrows():
            leads = int(r.get("leads") or 0)
            owners.append({
                "owner": r.get("owner") or "Unassigned",
                "leads": leads,
                "converted": int(r.get("converted") or 0),
                "conversion_rate": round(
                    (int(r.get("converted") or 0) / leads * 100) if leads else 0, 1
                ),
            })

    total = int(lead_totals["total"] or 0)
    converted = int(lead_totals["converted"] or 0)
    open_leads = int(lead_totals["open_leads"] or 0)

    funnel = _build_marketing_funnel(
        lead_totals, quote_totals, won, open_value, decided_value, won_value, total, converted
    )
    alerts = _generate_marketing_alerts(
        total, open_leads, expired_value, won_value, trend, source_rows, days_stale
    )

    period_leads = int(lead_totals["in_period"] or 0)
    currency = _company_currency()

    return {
        "period": period,
        "currency": currency,
        "data_freshness": {
            "latest_activity": str(latest) if latest else None,
            "days_stale": days_stale,
        },
        "kpis": {
            "total_leads": total,
            "new_leads": period_leads,
            "open_leads": open_leads,
            "converted_leads": converted,
            "lead_conversion_rate": round(converted / total * 100, 1) if total else 0,
            "open_quote_value": open_value,
            "won_value": won_value,
            "expired_value": expired_value,
            "win_rate_by_value": round(won_value / decided_value * 100, 1) if decided_value else 0,
        },
        "funnel": funnel,
        "source_performance": source_rows,
        "lead_trend": trend,
        "pipeline_by_status": pipeline,
        "territory_performance": territory,
        "owner_performance": owners,
        "alerts": alerts,
    }


# ────────────────────────────────────────────────────────────────────────────
# Drill-Down
# ────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_crm_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size

    if metric == "leads":
        frappe.has_permission("Lead", throw=True)
        db_filters = {"docstatus": 0}
        # Optional context filter from the funnel ("Reached Opportunity" ->
        # a list of statuses) or the "Where leads are sitting" status table
        # (a single status). Matches Frappe's own filter-tuple convention.
        status = f.get("status")
        if status:
            db_filters["status"] = ("in", status) if isinstance(status, list) else status
        rows = frappe.get_list(
            "Lead",
            filters=db_filters,
            # `source` is not in Lead's current meta (see
            # `_compute_marketing_overview`), so `get_list` silently drops it
            # instead of erroring -- fetch it separately below, scoped to
            # just the already-permitted rows on this page.
            fields=["name", "lead_name", "company_name", "status", "lead_owner", "creation"],
            start=start, page_length=page_size, order_by="creation desc",
            ignore_permissions=False,
        )
        if rows:
            Lead = frappe.qb.DocType("Lead")
            names = [r["name"] for r in rows]
            source_rows = (
                frappe.qb.from_(Lead)
                .select(Lead.name, Lead.source)
                .where(Lead.name.isin(names))
                .run(as_dict=False)
            )
            source_by_name = dict(source_rows)
            for r in rows:
                r["source"] = source_by_name.get(r["name"]) or ""
        return {
            "columns": [
                {"label": "Lead", "fieldname": "name", "fieldtype": "Link", "options": "Lead"},
                {"label": "Name", "fieldname": "lead_name", "fieldtype": "Data"},
                {"label": "Company", "fieldname": "company_name", "fieldtype": "Data"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
                {"label": "Source", "fieldname": "source", "fieldtype": "Data"},
                {"label": "Owner", "fieldname": "lead_owner", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Lead", filters=db_filters),
        }

    if metric == "opportunities":
        frappe.has_permission("Opportunity", throw=True)
        db_filters = {"docstatus": 0, "status": ("not in", ["Closed", "Lost"])}
        rows = frappe.get_list(
            "Opportunity",
            filters=db_filters,
            fields=["name", "opportunity_from", "party_name", "opportunity_amount", "expected_closing", "status", "sales_stage"],
            start=start, page_length=page_size, order_by="expected_closing asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Opportunity", "fieldname": "name", "fieldtype": "Link", "options": "Opportunity"},
                {"label": "From", "fieldname": "party_name", "fieldtype": "Data"},
                {"label": "Amount", "fieldname": "opportunity_amount", "fieldtype": "Currency"},
                {"label": "Closing", "fieldname": "expected_closing", "fieldtype": "Date"},
                {"label": "Stage", "fieldname": "sales_stage", "fieldtype": "Data"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Opportunity", filters=db_filters),
        }

    if metric == "lost_opportunities":
        frappe.has_permission("Opportunity", throw=True)
        db_filters = {"docstatus": 0, "status": "Lost"}
        rows = frappe.get_list(
            "Opportunity",
            filters=db_filters,
            fields=["name", "party_name", "opportunity_amount", "lost_reasons", "modified"],
            start=start, page_length=page_size, order_by="modified desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Opportunity", "fieldname": "name", "fieldtype": "Link", "options": "Opportunity"},
                {"label": "From", "fieldname": "party_name", "fieldtype": "Data"},
                {"label": "Amount", "fieldname": "opportunity_amount", "fieldtype": "Currency"},
                {"label": "Date", "fieldname": "modified", "fieldtype": "Date"},
            ],
            "rows": rows,
            "total": frappe.db.count("Opportunity", filters=db_filters),
        }

    if metric == "quotations":
        # Gap fix 2026-08-17: the funnel's "Quoted" / "Ordered" stages had
        # no drill-down at all. Mirrors `quote_total` in
        # `_compute_marketing_overview`: docstatus < 2 (Draft + Submitted,
        # excludes Cancelled), not period-filtered -- same population the
        # funnel counts, so the drill-down total matches the stage number.
        frappe.has_permission("Quotation", throw=True)
        db_filters = {"docstatus": ("<", 2)}
        status = f.get("status")
        if status:
            db_filters["status"] = ("in", status) if isinstance(status, list) else status
        rows = frappe.get_list(
            "Quotation",
            filters=db_filters,
            fields=["name", "party_name", "status", "transaction_date", "base_grand_total"],
            start=start, page_length=page_size, order_by="transaction_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Quotation", "fieldname": "name", "fieldtype": "Link", "options": "Quotation"},
                {"label": "Party", "fieldname": "party_name", "fieldtype": "Data"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
                {"label": "Date", "fieldname": "transaction_date", "fieldtype": "Date"},
                {"label": "Amount", "fieldname": "base_grand_total", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Quotation", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
