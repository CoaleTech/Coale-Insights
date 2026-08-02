# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Marketing Intelligence API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any
from insights.api.response import success, error


@frappe.whitelist()
def source_metrics(period: str = "YTD") -> Dict[str, Any]:
    """Get lead source metrics including cost per lead."""
    try:
        from insights.ml.marketing_source_metrics import (
            get_leads_by_source,
            get_hot_leads_by_source,
            get_cost_per_lead,
            get_territory_leads,
        )
        from frappe.utils import nowdate, add_months
        from datetime import datetime

        end_date = nowdate()
        if period == "MTD":
            start_date = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        elif period == "QTD":
            current_month = datetime.now().month
            quarter_start_month = ((current_month - 1) // 3) * 3 + 1
            start_date = datetime.now().replace(month=quarter_start_month, day=1).strftime("%Y-%m-%d")
        elif period == "YTD":
            start_date = datetime.now().replace(month=1, day=1).strftime("%Y-%m-%d")
        else:  # TTM
            start_date = add_months(end_date, -12)

        return success({
            "leads_by_source": get_leads_by_source(start_date, end_date),
            "hot_leads_by_source": get_hot_leads_by_source(start_date, end_date),
            "cost_per_lead": get_cost_per_lead(start_date, end_date),
            "territory_leads": get_territory_leads(start_date, end_date),
        })
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def cost_per_lead(period: str = "YTD") -> Dict[str, Any]:
    """Get cost per lead by source."""
    try:
        from insights.ml.marketing_source_metrics import get_cost_per_lead
        from frappe.utils import nowdate, add_months
        from datetime import datetime

        end_date = nowdate()
        if period == "MTD":
            start_date = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        elif period == "QTD":
            current_month = datetime.now().month
            quarter_start_month = ((current_month - 1) // 3) * 3 + 1
            start_date = datetime.now().replace(month=quarter_start_month, day=1).strftime("%Y-%m-%d")
        elif period == "YTD":
            start_date = datetime.now().replace(month=1, day=1).strftime("%Y-%m-%d")
        else:  # TTM
            start_date = add_months(end_date, -12)

        return success(get_cost_per_lead(start_date, end_date))
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def territory_leads(period: str = "YTD") -> Dict[str, Any]:
    """Get lead count by territory."""
    try:
        from insights.ml.marketing_source_metrics import get_territory_leads
        from frappe.utils import nowdate, add_months
        from datetime import datetime

        end_date = nowdate()
        if period == "MTD":
            start_date = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        elif period == "QTD":
            current_month = datetime.now().month
            quarter_start_month = ((current_month - 1) // 3) * 3 + 1
            start_date = datetime.now().replace(month=quarter_start_month, day=1).strftime("%Y-%m-%d")
        elif period == "YTD":
            start_date = datetime.now().replace(month=1, day=1).strftime("%Y-%m-%d")
        else:  # TTM
            start_date = add_months(end_date, -12)

        return success(get_territory_leads(start_date, end_date))
    except Exception as e:
        return error(str(e))


# ─── Overview ─────────────────────────────────────────────────────────────────

# ERPNext Lead.status values, ordered along the CRM funnel. `Lead.status` is
# ERPNext's own progression field, so it is the honest funnel source rather than
# a synthesised join across Lead/Opportunity/Quotation.
_LEAD_OPEN_STATUSES = ("Lead", "Open", "Inquiry", "Interested")
_LEAD_WON_STATUSES = ("Converted",)


def _period_start(period: str) -> str:
    """Resolve a period keyword to an inclusive start date."""
    from datetime import datetime

    from frappe.utils import add_months, nowdate

    now = datetime.now()
    if period == "MTD":
        return now.replace(day=1).strftime("%Y-%m-%d")
    if period == "QTD":
        quarter_start = ((now.month - 1) // 3) * 3 + 1
        return now.replace(month=quarter_start, day=1).strftime("%Y-%m-%d")
    if period == "YTD":
        return now.replace(month=1, day=1).strftime("%Y-%m-%d")
    return add_months(nowdate(), -12)


@frappe.whitelist()
def get_marketing_overview(period: str = "YTD") -> Dict[str, Any]:
    """Marketing and CRM overview built from ERPNext's built-in CRM.

    Sources are the standard ERPNext doctypes: Lead, Opportunity and Quotation.
    The separate Frappe CRM app (`CRM Lead` / `CRM Deal`) is intentionally NOT
    read; on this site those tables are empty and ERPNext's CRM module holds the
    real records.

    Deliberately omitted, because the underlying data makes them vanity panels:
      * anything keyed on `Opportunity.opportunity_amount`, which is 0 for every
        row on this site. Pipeline value comes from Quotation.base_grand_total,
        which is populated.
      * campaign-level reporting, with a single Campaign record in existence.
    """
    try:
        # Whitelisted endpoints get no automatic doctype gate, so check
        # explicitly before reading any CRM data.
        frappe.has_permission("Lead", "read", throw=True)

        start = _period_start(period)

        open_placeholders = ", ".join(["%s"] * len(_LEAD_OPEN_STATUSES))

        # ── Funnel. Counts come from Lead.status, value from Quotation. ────────
        lead_totals = frappe.db.sql(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN creation >= %s THEN 1 ELSE 0 END) AS in_period,
                SUM(CASE WHEN status IN ({open_list}) THEN 1 ELSE 0 END) AS open_leads,
                SUM(CASE WHEN status = 'Opportunity' THEN 1 ELSE 0 END) AS at_opportunity,
                SUM(CASE WHEN status = 'Quotation' THEN 1 ELSE 0 END) AS at_quotation,
                SUM(CASE WHEN status = 'Converted' THEN 1 ELSE 0 END) AS converted,
                SUM(CASE WHEN status = 'Lost Quotation' THEN 1 ELSE 0 END) AS lost
            FROM `tabLead`
            WHERE docstatus < 2
            """.format(open_list=open_placeholders),
            (start, *_LEAD_OPEN_STATUSES),
            as_dict=True,
        )[0]

        # Open pipeline value is a CURRENT-STATE question: a Draft quotation is
        # live money regardless of when it was raised, so this is not period
        # filtered either. Period-scoped intake lives in `kpis.new_leads`.
        quote_totals = frappe.db.sql(
            """
            SELECT
                status,
                COUNT(*) AS count,
                COALESCE(SUM(base_grand_total), 0) AS value
            FROM `tabQuotation`
            WHERE docstatus < 2
            GROUP BY status
            """,
            as_dict=True,
        )

        # How current is the CRM at all? A dashboard over abandoned data must say
        # so rather than rendering a wall of confident zeros.
        freshness = frappe.db.sql(
            """
            SELECT
                (SELECT MAX(creation) FROM `tabLead` WHERE docstatus < 2) AS latest_lead,
                (SELECT MAX(creation) FROM `tabQuotation` WHERE docstatus < 2) AS latest_quotation
            """,
            as_dict=True,
        )[0]
        from frappe.utils import date_diff, nowdate

        latest = max(
            [d for d in (freshness.get("latest_lead"), freshness.get("latest_quotation")) if d],
            default=None,
        )
        days_stale = date_diff(nowdate(), latest) if latest else None
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

        # ── Source performance. The one panel that answers "which channel
        #    actually earns money", not just which one is loudest. ─────────────
        # Channel quality is a STRUCTURAL question ("which source converts"), not
        # a this-month question, so these two are deliberately unfiltered by
        # period. Filtering them would empty the panel whenever the period window
        # happens to miss the data, which tells the operator nothing.
        source_rows = frappe.db.sql(
            """
            SELECT
                COALESCE(NULLIF(l.source, ''), 'Unattributed') AS source,
                COUNT(*) AS leads,
                SUM(CASE WHEN l.status = 'Converted' THEN 1 ELSE 0 END) AS converted
            FROM `tabLead` l
            WHERE l.docstatus < 2
            GROUP BY 1
            ORDER BY leads DESC
            LIMIT 12
            """,
            as_dict=True,
        )
        quote_by_source = frappe.db.sql(
            """
            SELECT
                COALESCE(NULLIF(source, ''), 'Unattributed') AS source,
                COUNT(*) AS quotations,
                COALESCE(SUM(base_grand_total), 0) AS quoted_value,
                COALESCE(SUM(CASE WHEN status = 'Ordered' THEN base_grand_total ELSE 0 END), 0) AS won_value
            FROM `tabQuotation`
            WHERE docstatus < 2
            GROUP BY 1
            """,
            as_dict=True,
        )
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
        trend = frappe.db.sql(
            """
            SELECT
                DATE_FORMAT(creation, '%%Y-%%m') AS month,
                COUNT(*) AS leads,
                SUM(CASE WHEN status = 'Converted' THEN 1 ELSE 0 END) AS converted
            FROM `tabLead`
            WHERE docstatus < 2 AND creation >= %s
            GROUP BY 1
            ORDER BY 1
            """,
            (add_months_safe(start, -12),),
            as_dict=True,
        )

        pipeline = frappe.db.sql(
            """
            SELECT COALESCE(NULLIF(status, ''), 'Unset') AS status, COUNT(*) AS count
            FROM `tabLead`
            WHERE docstatus < 2
            GROUP BY 1
            ORDER BY count DESC
            """,
            as_dict=True,
        )

        territory = frappe.db.sql(
            """
            SELECT
                COALESCE(NULLIF(l.territory, ''), 'Unassigned') AS territory,
                COUNT(*) AS leads,
                SUM(CASE WHEN l.status = 'Converted' THEN 1 ELSE 0 END) AS converted
            FROM `tabLead` l
            WHERE l.docstatus < 2
            GROUP BY 1
            ORDER BY leads DESC
            LIMIT 10
            """,
            as_dict=True,
        )

        owners = frappe.db.sql(
            """
            SELECT
                COALESCE(NULLIF(lead_owner, ''), 'Unassigned') AS owner,
                COUNT(*) AS leads,
                SUM(CASE WHEN status = 'Converted' THEN 1 ELSE 0 END) AS converted
            FROM `tabLead`
            WHERE docstatus < 2
            GROUP BY 1
            ORDER BY leads DESC
            LIMIT 10
            """,
            as_dict=True,
        )
        for row in owners:
            leads = int(row["leads"] or 0)
            row["conversion_rate"] = round(
                (int(row["converted"] or 0) / leads * 100) if leads else 0, 1
            )

        total = int(lead_totals["total"] or 0)
        converted = int(lead_totals["converted"] or 0)
        open_leads = int(lead_totals["open_leads"] or 0)

        funnel = [
            {"label": _("Leads"), "count": total, "value": None},
            {
                "label": _("Reached Opportunity"),
                "count": int(lead_totals["at_opportunity"] or 0) + int(lead_totals["at_quotation"] or 0) + converted,
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
        # Quotation. Stage 1 -> 2 crosses from leads to quotation records, and a
        # quotation can exist for a lead that never reached status 'Opportunity',
        # so that hop is left null rather than reported as a >100% rate.
        _COMPARABLE_TO_PREV = {1, 3}
        for i, stage in enumerate(funnel):
            prev = funnel[i - 1]["count"] if i in _COMPARABLE_TO_PREV else None
            stage["conversion_from_prev"] = (
                round(stage["count"] / prev * 100, 1) if prev else None
            )

        # ── Alerts. The "what should someone do" answer. ──────────────────────
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

        period_leads = int(lead_totals["in_period"] or 0)

        # The server knows the company currency; the frontend was hardcoding KES
        # while this dataset is denominated in the company default.
        company = frappe.defaults.get_user_default("Company")
        currency = (
            frappe.db.get_value("Company", company, "default_currency") if company else None
        ) or frappe.db.get_default("currency") or ""

        return success({
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
        })
    except frappe.PermissionError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Marketing overview failed")
        return error(str(e))


def add_months_safe(date_str: str, months: int) -> str:
    """Shift a date string by months, tolerating either a date or datetime input."""
    from frappe.utils import add_months

    return add_months(date_str, months)


# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_crm_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")

    if metric == "leads":
        frappe.has_permission("Lead", throw=True)
        rows = frappe.get_list(
            "Lead",
            filters={"docstatus": 0},
            fields=["name", "lead_name", "company_name", "status", "source", "lead_owner", "creation"],
            start=start, page_length=page_size, order_by="creation desc",
            ignore_permissions=False,
        )
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
            "total": frappe.db.count("Lead", filters={"docstatus": 0}),
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

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
