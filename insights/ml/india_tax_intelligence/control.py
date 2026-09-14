# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence — management control layer.

``data.py`` answers *what do the tax ledgers say*. This module answers the
questions a management review asks on top of that answer:

1. **When does the cash leave?** :func:`get_tax_cash_outlook` re-dates every
   already-accrued statutory liability onto its own due date, turning a tax
   position into a payment calendar.
2. **Who owns each open exception?** :func:`get_action_queue` and
   :func:`get_legal_register` read workflow state — the ``JKM Action`` board and
   the tax/legal case register — where an exception has an owner, a promise date
   and evidence of closure.
3. **What is still unproven?** :func:`get_compliance_matrix` and
   :func:`get_compliance_pulse` roll the computed sections into per-area
   readiness, separating *filed* from *reconciled, paid and evidenced*.

Two rules hold throughout:

- **Absent is never zero.** Workflow state belongs to the ``jkm_finance`` app and
  the customs tables to ``india_compliance``; ``insights`` stays installable
  without either, so every reader degrades to an explicit
  ``{"available": False, "reason": ...}`` payload. A zero and a missing source
  render identically on a dashboard tile — it reads "nothing owed" when it means
  "nothing known", which is the one failure a compliance surface cannot absorb.
- **Nothing is projected.** No revenue forecast, no estimated accrual. The cash
  outlook only re-dates money the ledger has already recognised; where an amount
  genuinely is not derivable (advance tax needs a reviewed annual estimate that
  lives nowhere on this install) the date is emitted as a calendar marker with a
  null amount rather than a fabricated bar.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import frappe

from insights.api.ml.ibis_source import t
from insights.ml.india_tax_intelligence.data import (
    ALL_PLAIN,
    ALL_RCM,
    GST_DUE_DATES,
    _company_filter,
    _component_sum,
    _date_filter,
    _docstatus_filter,
    _scalar_or,
    _to_date,
)

# Workflow doctypes, owned by the `jkm_finance` app.
ACTION_DOCTYPE = "JKM Action"
LEGAL_DOCTYPE = "JKM Tax Legal Case"

# `JKM Action` statuses that still need somebody to act. Mirrors
# `jkm_finance.intelligence.action_plans.OPEN_STATES` — duplicated rather than
# imported so `insights` never imports from an app it does not depend on.
OPEN_ACTION_STATES = ("To Do", "In Progress", "Blocked")

# `JKM Tax Legal Case` terminal statuses.
CLOSED_CASE_STATES = ("Closed", "Dismissed")

# Forward statutory calendar length, in weeks.
OUTLOOK_WEEKS = 13

# "Due soon" horizon for the compliance pulse, in days.
DUE_SOON_DAYS = 7


# ---------------------------------------------------------------------------
# Availability primitives
# ---------------------------------------------------------------------------

def _unavailable(reason: str, **extra: Any) -> Dict[str, Any]:
    """Explicit *no source* payload. See the module docstring: never zeros."""
    return {"available": False, "reason": reason, **extra}


def _doctype_available(doctype: str) -> bool:
    """True when the DocType is registered *and* its table exists.

    Both halves are load-bearing: the DocType row can survive an app removal,
    and the table does not exist until the first ``bench migrate`` after the
    app is installed.
    """
    try:
        return bool(frappe.db.exists("DocType", doctype)) and bool(
            frappe.db.table_exists(doctype)
        )
    except Exception:
        return False


def _today() -> date:
    return datetime.now().date()


def _as_date(value: Any) -> Optional[date]:
    """Coerce a Frappe date/datetime/ISO string to `date`, or None."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _days_until(value: Any, today: Optional[date] = None) -> Optional[int]:
    """Signed days from today to `value`; negative means already past."""
    d = _as_date(value)
    if d is None:
        return None
    return (d - (today or _today())).days


# ---------------------------------------------------------------------------
# Action queue — the ownership layer
# ---------------------------------------------------------------------------

def get_action_queue(intelligence) -> Dict[str, Any]:
    """Open tax exceptions from the ``JKM Action`` board, worst money first.

    The board is the system of record for *ownership*. Detectors in
    ``jkm_finance.agents.tax_compliance`` raise a finding on every run and
    ``action_plans.reconcile_actions`` folds it into a stable action that keeps
    its assignee and due date across weeks and auto-resolves the week the
    underlying exception clears. Reading it here means this dashboard shows the
    queue the owners are actually working rather than a second, divergent list.

    Company scoping goes through the linked ``JKM Weekly Report``: ``JKM Action``
    itself carries no company column.
    """
    if not _doctype_available(ACTION_DOCTYPE):
        return _unavailable(
            "JKM Action board is not installed (jkm_finance app)",
            rows=[],
            summary={},
        )

    conditions = ["a.plan_type = 'Tax'", "a.status IN %(open_states)s"]
    params: Dict[str, Any] = {"open_states": tuple(OPEN_ACTION_STATES)}
    if intelligence.company:
        conditions.append("(r.company = %(company)s OR a.plan IS NULL OR a.plan = '')")
        params["company"] = intelligence.company

    rows = frappe.db.sql(
        f"""
        SELECT a.name, a.title, a.action_key, a.area, a.priority, a.status,
               a.plan_state, a.owner_role, a.owner_type, a.impact_kes,
               a.due_date, a.first_seen, a.last_seen, a.rationale, a.steps,
               a._assign
        FROM `tab{ACTION_DOCTYPE}` a
        LEFT JOIN `tabJKM Weekly Report` r ON r.name = a.plan
        WHERE {' AND '.join(conditions)}
        ORDER BY a.impact_kes DESC
        """,
        params,
        as_dict=True,
    )

    today = _today()
    out: List[Dict[str, Any]] = []
    for r in rows:
        due_in = _days_until(r.get("due_date"), today)
        first_seen = _as_date(r.get("first_seen"))
        out.append(
            {
                "name": r.get("name"),
                "title": r.get("title") or "",
                "action_key": r.get("action_key") or "",
                "area": r.get("area") or "",
                "priority": r.get("priority") or "",
                "status": r.get("status") or "",
                "plan_state": r.get("plan_state") or "",
                "owner_role": r.get("owner_role") or "",
                "owner_type": r.get("owner_type") or "",
                "exposure": float(r.get("impact_kes") or 0),
                "due_date": _to_date(r.get("due_date")),
                "due_in_days": due_in,
                "overdue": due_in is not None and due_in < 0,
                # Ageing is the honest urgency signal on a standing backlog: a
                # detector re-raises the same finding every week, so `first_seen`
                # is how long the exception has gone unclosed.
                "age_days": (today - first_seen).days if first_seen else None,
                "assigned_to": _first_assignee(r.get("_assign")),
                "rationale": r.get("rationale") or "",
                "steps": r.get("steps") or "",
            }
        )

    overdue = [r for r in out if r["overdue"]]
    due_soon = [
        r for r in out
        if r["due_in_days"] is not None and 0 <= r["due_in_days"] <= DUE_SOON_DAYS
    ]
    unassigned = [r for r in out if not r["assigned_to"]]

    return {
        "available": True,
        "rows": out,
        "summary": {
            "open": len(out),
            "exposure": round(sum(r["exposure"] for r in out), 2),
            "overdue": len(overdue),
            "overdue_exposure": round(sum(r["exposure"] for r in overdue), 2),
            "due_soon": len(due_soon),
            "unassigned": len(unassigned),
            "by_priority": _count_by(out, "priority"),
            "by_owner_role": _count_by(out, "owner_role"),
        },
    }


def _first_assignee(assign_json: Any) -> str:
    """First user out of Frappe's `_assign` JSON list, or ``""``."""
    if not assign_json:
        return ""
    try:
        parsed = frappe.parse_json(assign_json)
    except Exception:
        return ""
    if isinstance(parsed, list) and parsed:
        return str(parsed[0])
    return ""


def _count_by(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    """Count + exposure grouped by `key`, largest exposure first."""
    buckets: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        k = r.get(key) or "Unassigned"
        b = buckets.setdefault(k, {"key": k, "count": 0, "exposure": 0.0})
        b["count"] += 1
        b["exposure"] += float(r.get("exposure") or 0)
    for b in buckets.values():
        b["exposure"] = round(b["exposure"], 2)
    return sorted(buckets.values(), key=lambda b: b["exposure"], reverse=True)


# ---------------------------------------------------------------------------
# Legal register — notices, demands, assessments, appeals
# ---------------------------------------------------------------------------

def get_legal_register(intelligence) -> Dict[str, Any]:
    """Open tax and legal matters from ``JKM Tax Legal Case``.

    A notice or demand is not a transaction, so it has no ERPNext home and
    historically lived in mailboxes and spreadsheets — which is exactly why the
    reply date is the one that gets missed. Every row here carries its own
    statutory clock (``statutory_reply_date``, ``hearing_date``,
    ``appeal_limitation_date``) and the register reports the nearest of the three
    as the binding date.
    """
    if not _doctype_available(LEGAL_DOCTYPE):
        return _unavailable(
            "JKM Tax Legal Case register is not installed (jkm_finance app)",
            rows=[],
            summary={},
        )

    filters: Dict[str, Any] = {"status": ["not in", list(CLOSED_CASE_STATES)]}
    if intelligence.company:
        filters["company"] = intelligence.company

    rows = frappe.get_all(
        LEGAL_DOCTYPE,
        filters=filters,
        fields=[
            "name", "title", "case_type", "matter", "stage", "status",
            "authority", "reference_no", "gstin", "related_period",
            "reference_doctype", "reference_name",
            "received_date", "internal_target_date", "statutory_reply_date",
            "hearing_date", "appeal_limitation_date",
            "demand_amount", "interest_amount", "penalty_amount",
            "disputed_amount", "provision_amount", "paid_amount",
            "total_exposure", "recovery_position",
            "business_owner", "accounts_owner", "advisor", "approver",
            "next_action", "evidence_note",
        ],
        order_by="total_exposure desc",
    )

    today = _today()
    out: List[Dict[str, Any]] = []
    for r in rows:
        # The binding date is whichever statutory clock runs out first — a
        # hearing next week outranks a reply window that closes next month.
        clocks = [
            ("Reply", _as_date(r.get("statutory_reply_date"))),
            ("Hearing", _as_date(r.get("hearing_date"))),
            ("Appeal", _as_date(r.get("appeal_limitation_date"))),
        ]
        live = sorted([(lbl, d) for lbl, d in clocks if d], key=lambda p: p[1])
        next_label, next_date = live[0] if live else ("", None)
        due_in = (next_date - today).days if next_date else None
        out.append(
            {
                **{
                    k: r.get(k)
                    for k in (
                        "name", "title", "case_type", "matter", "stage", "status",
                        "authority", "reference_no", "gstin", "related_period",
                        "reference_doctype", "reference_name", "recovery_position",
                        "business_owner", "accounts_owner", "advisor", "approver",
                        "next_action", "evidence_note",
                    )
                },
                "received_date": _to_date(r.get("received_date")),
                "internal_target_date": _to_date(r.get("internal_target_date")),
                "statutory_reply_date": _to_date(r.get("statutory_reply_date")),
                "hearing_date": _to_date(r.get("hearing_date")),
                "appeal_limitation_date": _to_date(r.get("appeal_limitation_date")),
                "demand_amount": float(r.get("demand_amount") or 0),
                "interest_amount": float(r.get("interest_amount") or 0),
                "penalty_amount": float(r.get("penalty_amount") or 0),
                "disputed_amount": float(r.get("disputed_amount") or 0),
                "provision_amount": float(r.get("provision_amount") or 0),
                "paid_amount": float(r.get("paid_amount") or 0),
                "exposure": float(r.get("total_exposure") or 0),
                "next_date_label": next_label,
                "next_date": next_date.isoformat() if next_date else None,
                "due_in_days": due_in,
                "overdue": due_in is not None and due_in < 0,
                # An unevidenced matter is the one that collapses at hearing.
                "has_evidence": bool((r.get("evidence_note") or "").strip()),
            }
        )

    overdue = [r for r in out if r["overdue"]]
    due_soon = [
        r for r in out
        if r["due_in_days"] is not None and 0 <= r["due_in_days"] <= DUE_SOON_DAYS
    ]

    return {
        "available": True,
        "rows": out,
        "summary": {
            "open": len(out),
            "exposure": round(sum(r["exposure"] for r in out), 2),
            "provision": round(sum(r["provision_amount"] for r in out), 2),
            "disputed": round(sum(r["disputed_amount"] for r in out), 2),
            "paid_under_protest": round(
                sum(
                    r["paid_amount"] for r in out
                    if r.get("recovery_position") == "Paid Under Protest"
                ),
                2,
            ),
            "overdue": len(overdue),
            "due_soon": len(due_soon),
            "hearings": len([r for r in out if r.get("hearing_date")]),
            "appeals": len([r for r in out if r.get("stage") == "Appeal"]),
            "without_evidence": len([r for r in out if not r["has_evidence"]]),
            "by_case_type": _count_by(out, "case_type"),
            "by_matter": _count_by(out, "matter"),
        },
    }


# ---------------------------------------------------------------------------
# Reverse charge
# ---------------------------------------------------------------------------

def get_rcm_summary(intelligence, start: date, end: date) -> Dict[str, Any]:
    """Reverse-charge liability we self-assess on inward supplies.

    Two distinct things get called "RCM" and conflating them is the usual error:

    - **Books** — ``Purchase Invoice.is_reverse_charge``: supplies where *we* owe
      the tax directly to government rather than to the supplier. This is real
      cash out and the number that belongs on a liability tile.
    - **Portal** — ``GST Inward Supply.is_reverse_charge``: what suppliers
      reported as reverse-charge in GSTR-2A/2B. Useful only as a cross-check;
      it is their filing, not our liability.

    A gap between them is a reconciliation finding, not an accounting error, so
    both are returned with the difference named rather than silently netted.

    RCM is also *cash-neutral where the credit is eligible*: the liability we
    self-assess is matched by an input credit on the same invoice. A tile that
    shows only the liability overstates the cash impact, so `liability`,
    `credit` and `net_cash` are all returned.
    """
    pi = _company_filter(t("Purchase Invoice"), intelligence.company)
    pi = _docstatus_filter(pi)
    pi = _date_filter(pi, start, end, "posting_date")

    if "is_reverse_charge" not in pi.columns:
        return _unavailable("Purchase Invoice has no is_reverse_charge column")

    rcm_pi = pi.filter(pi["is_reverse_charge"].fill_null(0) == 1)
    ptc = t("Purchase Taxes and Charges")
    joined = rcm_pi.join(ptc, rcm_pi["name"] == ptc["parent"], how="inner")

    # An RCM-flagged invoice books the tax twice: the self-assessed liability
    # on the `*_RCM` heads and an equal input credit on the plain heads. Live
    # on this ledger both sides read 70,522.21 across 556 invoices -- they are
    # equal by construction, so reporting one number alone would imply a cash
    # cost that the credit offsets. Report the liability, the credit, and the
    # net cash effect (zero where the credit is fully eligible).
    liability = float(_scalar_or(_component_sum(joined, *ALL_RCM), 0.0))
    credit = float(_scalar_or(_component_sum(joined, *ALL_PLAIN), 0.0))
    tax = liability
    invoices = int(_scalar_or(rcm_pi.aggregate(v=rcm_pi["name"].count())["v"], 0))
    taxable = float(
        _scalar_or(rcm_pi.aggregate(v=rcm_pi["base_net_total"].sum())["v"], 0.0)
    )

    portal: Dict[str, Any] = _unavailable("india_compliance not installed")
    if intelligence.india_compliance_installed:
        gis = t("GST Inward Supply")
        if "is_reverse_charge" in gis.columns:
            gis_c = _company_filter(gis, intelligence.company)
            gis_c = _date_filter(gis_c, start, end, "bill_date")
            rcm_gis = gis_c.filter(gis_c["is_reverse_charge"].fill_null(0) == 1)
            components = [
                rcm_gis[c].fill_null(0)
                for c in ("igst", "cgst", "sgst", "cess")
                if c in rcm_gis.columns
            ]
            portal_tax = 0.0
            if components:
                total_expr = components[0]
                for c in components[1:]:
                    total_expr = total_expr + c
                portal_tax = float(
                    _scalar_or(rcm_gis.aggregate(v=total_expr.sum())["v"], 0.0)
                )
            portal = {
                "available": True,
                "rows": int(
                    _scalar_or(rcm_gis.aggregate(v=rcm_gis["name"].count())["v"], 0)
                ),
                "tax": round(portal_tax, 2),
            }
        else:
            portal = _unavailable("GST Inward Supply has no is_reverse_charge column")

    return {
        "available": True,
        "books": {
            "invoices": invoices,
            "taxable_value": round(taxable, 2),
            "tax": round(tax, 2),
            "liability": round(liability, 2),
            "credit": round(credit, 2),
            "net_cash": round(liability - credit, 2),
        },
        "portal": portal,
        "gap": (
            round(tax - float(portal.get("tax") or 0), 2)
            if portal.get("available")
            else None
        ),
    }


# ---------------------------------------------------------------------------
# TDS master-data exceptions
# ---------------------------------------------------------------------------

def get_pan_exceptions(intelligence, start: date, end: date) -> Dict[str, Any]:
    """Suppliers under TDS withholding with no PAN on record.

    Section 206AA forces deduction at the higher of the specified rate or 20%
    when the deductee has no PAN, and a return filed against a missing PAN is
    rejected outright. So this is not a data-hygiene nag: every rupee already
    deducted for these suppliers is at risk of being unclaimable by them and
    non-remittable by us until the master is fixed.

    Exposure is the invoice value transacted in the window, which is what the
    correction has to be applied across — not the deducted tax, which is the
    smaller and less useful number.
    """
    sup = t("Supplier")
    if not all(c in sup.columns for c in ("pan", "tax_withholding_category")):
        return _unavailable("Supplier has no pan / tax_withholding_category column")

    flagged = sup.filter(
        (sup["tax_withholding_category"].fill_null("") != "")
        & (sup["pan"].fill_null("") == "")
    )

    pi = _company_filter(t("Purchase Invoice"), intelligence.company)
    pi = _docstatus_filter(pi)
    pi = _date_filter(pi, start, end, "posting_date")

    joined = pi.join(flagged, pi["supplier"] == flagged["name"], how="inner")
    agg = (
        joined.group_by(joined["supplier"].name("supplier"))
        .aggregate(
            exposure=joined["base_grand_total"].sum(),
            invoices=joined["name"].nunique(),
            category=joined["tax_withholding_category"].max(),
        )
        .order_by(joined["base_grand_total"].sum().desc())
    )
    df = agg.execute()

    rows: List[Dict[str, Any]] = []
    if df is not None and not df.empty:
        for _, r in df.iterrows():
            rows.append(
                {
                    "supplier": r.get("supplier") or "",
                    "withholding_category": r.get("category") or "",
                    "exposure": round(float(r.get("exposure") or 0), 2),
                    "invoices": int(r.get("invoices") or 0),
                }
            )

    # Suppliers flagged for TDS with no PAN and no invoice in the window still
    # need fixing before the next bill lands, so count them separately rather
    # than dropping them with the join.
    flagged_total = int(_scalar_or(flagged.aggregate(v=flagged["name"].count())["v"], 0))

    return {
        "available": True,
        "rows": rows,
        "summary": {
            "suppliers_missing_pan": flagged_total,
            "transacted_in_window": len(rows),
            "exposure": round(sum(r["exposure"] for r in rows), 2),
            "statutory_basis": "Sec 206AA: higher of specified rate or 20% where PAN is absent",
        },
    }


# ---------------------------------------------------------------------------
# Customs / import
# ---------------------------------------------------------------------------

def get_customs_summary(intelligence, start: date, end: date) -> Dict[str, Any]:
    """Bill of Entry duty, import IGST and reconciliation state.

    Distinguishes three states the frontend must not collapse: the app is not
    installed, the app is installed but no import documents exist (a legitimate
    "no import activity" answer), and real rows.
    """
    if not intelligence.india_compliance_installed:
        return _unavailable("india_compliance not installed")
    if not _doctype_available("Bill of Entry"):
        return _unavailable("Bill of Entry DocType not available")

    boe = _company_filter(t("Bill of Entry"), intelligence.company)
    boe = _docstatus_filter(boe)
    boe = _date_filter(boe, start, end, "bill_of_entry_date")

    total = int(_scalar_or(boe.aggregate(v=boe["name"].count())["v"], 0))
    if total == 0:
        return {
            "available": True,
            "documents": 0,
            "note": "No Bill of Entry documents recorded for this window",
            "customs_duty": 0.0,
            "by_reconciliation_status": [],
            "unreconciled": 0,
        }

    duty = float(
        _scalar_or(boe.aggregate(v=boe["total_customs_duty"].sum())["v"], 0.0)
        if "total_customs_duty" in boe.columns
        else 0.0
    )

    by_status: List[Dict[str, Any]] = []
    unreconciled = 0
    if "reconciliation_status" in boe.columns:
        agg = boe.group_by(
            boe["reconciliation_status"].fill_null("Not Applicable").name("status")
        ).aggregate(count=boe["name"].count())
        df = agg.execute()
        if df is not None and not df.empty:
            for _, r in df.iterrows():
                status = r.get("status") or "Not Applicable"
                count = int(r.get("count") or 0)
                by_status.append({"status": status, "count": count})
                if status == "Unreconciled":
                    unreconciled = count

    return {
        "available": True,
        "documents": total,
        "customs_duty": round(duty, 2),
        "by_reconciliation_status": by_status,
        "unreconciled": unreconciled,
    }


# ---------------------------------------------------------------------------
# 13-week statutory tax cash outlook
# ---------------------------------------------------------------------------

def _gstr3b_filing_status(intelligence) -> Dict[str, Optional[str]]:
    """``{"YYYY-MM": filing_status}`` for every logged GSTR-3B period.

    ``GST Return Log.return_period`` is ``MMYYYY``, normalised here to the
    ``YYYY-MM`` month keys the GST summary emits. A period with no log row is
    absent from the map — deliberately distinct from a row whose
    ``filing_status`` is NULL, because "never synced" and "synced, not filed"
    warrant different labels on a cash chart.
    """
    if not intelligence.india_compliance_installed:
        return {}
    if not _doctype_available("GST Return Log"):
        return {}

    filters: Dict[str, Any] = {"return_type": "GSTR3B"}
    if intelligence.company and frappe.db.has_column("GST Return Log", "company"):
        filters["company"] = intelligence.company

    out: Dict[str, Optional[str]] = {}
    for r in frappe.get_all(
        "GST Return Log", filters=filters, fields=["return_period", "filing_status"]
    ):
        period = (r.get("return_period") or "").strip()
        if len(period) != 6 or not period.isdigit():
            continue
        out[f"{period[2:]}-{period[:2]}"] = r.get("filing_status") or None
    return out


def _tds_accrual_by_month(intelligence, start: date, end: date) -> Dict[str, float]:
    """TDS deducted per posting month, keyed ``YYYY-MM``.

    Same account-head match as :func:`data.get_tds_summary` — there is no
    dedicated TDS flag on a charge row — grouped by month so each period can be
    placed on its own challan due date instead of apportioned.
    """
    pi = _company_filter(t("Purchase Invoice"), intelligence.company)
    pi = _docstatus_filter(pi)
    pi = _date_filter(pi, start, end, "posting_date")
    ptc = t("Purchase Taxes and Charges")
    joined = pi.join(ptc, pi["name"] == ptc["parent"], how="inner")
    head = ptc["account_head"].lower()
    filtered = joined.filter(head.like("%tds%") | head.like("%tax deducted%"))
    agg = filtered.group_by(
        pi["posting_date"].strftime("%Y-%m").name("month")
    ).aggregate(amount=filtered["base_tax_amount"].abs().sum())
    df = agg.execute()
    if df is None or df.empty:
        return {}
    return {
        str(r["month"]): float(r["amount"] or 0)
        for _, r in df.iterrows()
        if r.get("month")
    }


def _due_date_for_period(period: str, day: int) -> Optional[date]:
    """Statutory due date for a ``YYYY-MM`` return period: `day` of the next month."""
    try:
        year_s, month_s = str(period).split("-")
        year, month = int(year_s), int(month_s)
    except (ValueError, AttributeError):
        return None
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    try:
        return date(next_year, next_month, day)
    except ValueError:
        return None


def _week_slots(anchor: date, count: int) -> List[Dict[str, Any]]:
    """`count` Monday-anchored weeks, starting with the week containing `anchor`."""
    monday = anchor - timedelta(days=anchor.weekday())
    slots = []
    for i in range(count):
        start = monday + timedelta(weeks=i)
        slots.append(
            {
                "label": f"W{i + 1}",
                "week_start": start.isoformat(),
                "week_end": (start + timedelta(days=6)).isoformat(),
                "gst": 0.0,
                "tds": 0.0,
                "legal": 0.0,
                "total": 0.0,
                "events": [],
            }
        )
    return slots


def get_tax_cash_outlook(
    intelligence,
    start: date,
    end: date,
    output_rows: List[Dict[str, Any]],
    input_rows: List[Dict[str, Any]],
    legal: Dict[str, Any],
) -> Dict[str, Any]:
    """Statutory tax cash outlook: overdue, plus the next 13 weeks.

    Every rupee here is already accrued in the ledger and already carries a
    statutory due date. This is a payment calendar, not a forecast.

    Three funded streams:

    - **GST** — net liability (output tax less input tax) for each return period
      whose GSTR-3B is not ``Filed``, due on the 20th of the following month
      (``GST_DUE_DATES``). Filed periods are dropped: that cash already left.
      A net credit is clamped to zero rather than shown as an inflow — excess
      ITC carries forward, the government does not refund it.
    - **TDS** — tax deducted per month, due on the 7th of the following month.
    - **Legal** — open register matters at net exposure on their binding date,
      excluding anything with a stay granted (no cash moves under a stay).

    Advance tax is emitted as dated *markers* with a null amount: the
    instalment dates are statutory, but the amounts need a reviewed annual
    estimate that exists nowhere on this install, and inventing one would put a
    fictional bar on a cash chart.

    Anything already past its due date lands in ``overdue`` instead of week 1,
    so a late return reads as late rather than as this week's plan.
    """
    today = _today()
    weeks = _week_slots(today, OUTLOOK_WEEKS)
    horizon_start = date.fromisoformat(weeks[0]["week_start"])
    horizon_end = date.fromisoformat(weeks[-1]["week_end"])
    overdue = {"gst": 0.0, "tds": 0.0, "legal": 0.0, "total": 0.0, "events": []}

    def place(stream: str, due: Optional[date], amount: float, label: str) -> None:
        """Drop `amount` into its week bucket, or into `overdue` if already past."""
        if due is None or amount <= 0:
            return
        event = {"due_date": due.isoformat(), "stream": stream, "label": label,
                 "amount": round(amount, 2)}
        if due < horizon_start:
            overdue[stream] += amount
            overdue["total"] += amount
            overdue["events"].append(event)
            return
        if due > horizon_end:
            return
        for slot in weeks:
            if slot["week_start"] <= due.isoformat() <= slot["week_end"]:
                slot[stream] += amount
                slot["total"] += amount
                slot["events"].append(event)
                return

    # --- GST: unfiled return periods at their own due date -------------------
    filing = _gstr3b_filing_status(intelligence)
    inputs_by_month = {
        row.get("month"): float(
            (row.get("cgst") or 0) + (row.get("sgst") or 0) + (row.get("igst") or 0)
        )
        for row in (input_rows or [])
    }
    gst_periods: List[Dict[str, Any]] = []
    for row in output_rows or []:
        month = row.get("month")
        if not month:
            continue
        status = filing.get(month)
        out_tax = float(
            (row.get("cgst") or 0) + (row.get("sgst") or 0) + (row.get("igst") or 0)
        )
        in_tax = inputs_by_month.get(month, 0.0)
        # Excess ITC carries forward; it is never cash back.
        net = max(out_tax - in_tax, 0.0)
        due = _due_date_for_period(month, GST_DUE_DATES["gstr3b_monthly_day"])
        period_state = (
            "filed" if status == "Filed"
            else "not_filed" if month in filing
            else "not_logged"
        )
        gst_periods.append(
            {
                "period": month,
                "output_tax": round(out_tax, 2),
                "input_tax": round(in_tax, 2),
                "net_payable": round(net, 2),
                "due_date": due.isoformat() if due else None,
                "filing_state": period_state,
                "overdue": bool(due and period_state != "filed" and due < today),
            }
        )
        if period_state == "filed":
            continue
        place("gst", due, net, f"GSTR-3B {month}")

    # --- TDS: monthly challan ------------------------------------------------
    tds_periods: List[Dict[str, Any]] = []
    for month, amount in sorted(_tds_accrual_by_month(intelligence, start, end).items()):
        due = _due_date_for_period(month, 7)
        tds_periods.append(
            {
                "period": month,
                "amount": round(amount, 2),
                "due_date": due.isoformat() if due else None,
                "overdue": bool(due and due < today),
            }
        )
        place("tds", due, amount, f"TDS challan {month}")

    # --- Legal: demands with a live clock and no stay ------------------------
    for case in (legal or {}).get("rows") or []:
        if case.get("recovery_position") == "Stay Granted":
            continue
        place(
            "legal",
            _as_date(case.get("next_date")),
            float(case.get("exposure") or 0),
            f"{case.get('matter') or 'Matter'} {case.get('reference_no') or ''}".strip(),
        )

    # --- Advance tax: real dates, unknown amounts ----------------------------
    markers: List[Dict[str, Any]] = []
    fy = getattr(intelligence, "fiscal_year", None) or {}
    fy_start = _as_date(fy.get("year_start_date"))
    fy_year = fy_start.year if fy_start else today.year
    for label, (month, day), pct in (
        ("1st Instalment", (6, 15), 15),
        ("2nd Instalment", (9, 15), 45),
        ("3rd Instalment", (12, 15), 75),
        ("4th (Final) Instalment", (3, 15), 100),
    ):
        year = fy_year + 1 if month == 3 else fy_year
        try:
            due = date(year, month, day)
        except ValueError:
            continue
        if horizon_start <= due <= horizon_end:
            markers.append(
                {
                    "due_date": due.isoformat(),
                    "label": f"Advance tax — {label}",
                    "cumulative_pct": pct,
                    "amount": None,
                    "reason": "No reviewed annual tax estimate recorded on this site",
                }
            )

    for slot in weeks:
        for key in ("gst", "tds", "legal", "total"):
            slot[key] = round(slot[key], 2)
    for key in ("gst", "tds", "legal", "total"):
        overdue[key] = round(overdue[key], 2)

    funded = [s for s in weeks if s["total"] > 0]
    peak = max(funded, key=lambda s: s["total"]) if funded else None

    return {
        "available": True,
        "weeks": weeks,
        "overdue": overdue,
        "total_horizon": round(sum(s["total"] for s in weeks), 2),
        "peak_week": peak["label"] if peak else None,
        "peak_amount": peak["total"] if peak else 0.0,
        "gst_periods": gst_periods,
        "tds_periods": tds_periods,
        "markers": markers,
        "basis": (
            "Accrued ledger tax placed on statutory due dates. GSTR-3B: 20th of "
            "the following month, filed periods excluded. TDS: 7th of the "
            "following month. Legal: binding date per matter, stays excluded. "
            "No amount is projected."
        ),
    }


# ---------------------------------------------------------------------------
# Derived control views — pure functions over already-computed sections
# ---------------------------------------------------------------------------

def get_compliance_pulse(
    queue: Dict[str, Any],
    legal: Dict[str, Any],
    compliance_score: float,
) -> Dict[str, Any]:
    """Readiness split three ways: closed with evidence, due soon, overdue.

    ``compliance_score`` already says how much of the statutory *mechanics* are
    done — e-invoice coverage, e-waybill coverage, filing, reconciliation. It
    says nothing about whether the exceptions those mechanics surfaced were ever
    closed by a person. This adds that half.
    """
    q = (queue or {}).get("summary") or {}
    lg = (legal or {}).get("summary") or {}

    open_items = int(q.get("open") or 0) + int(lg.get("open") or 0)
    overdue = int(q.get("overdue") or 0) + int(lg.get("overdue") or 0)
    due_soon = int(q.get("due_soon") or 0) + int(lg.get("due_soon") or 0)
    exposure = float(q.get("exposure") or 0) + float(lg.get("exposure") or 0)

    return {
        "available": bool(queue.get("available") or legal.get("available")),
        "compliance_score": compliance_score,
        "open_items": open_items,
        "overdue": overdue,
        "due_soon": due_soon,
        "on_track": max(open_items - overdue - due_soon, 0),
        "exposure": round(exposure, 2),
        "unassigned": int(q.get("unassigned") or 0),
        "without_evidence": int(lg.get("without_evidence") or 0),
        "sources": {
            "action_board": bool(queue.get("available")),
            "legal_register": bool(legal.get("available")),
        },
    }


def _cell(value: Any, note: str = "", unit: str = "text") -> Dict[str, Any]:
    """Matrix cell. ``value is None`` renders as *not available*, never as 0.

    ``unit`` is part of the contract because these cells are deliberately
    heterogeneous: one column holds a match-rate percentage for GST, a row
    count for e-Waybill and a rupee amount for TDS. Without it a consumer has
    to guess from the note text, and the dashboard rendered 1,838 unactioned
    rows as ``1,838.0%`` and ₹21.1 lakh of input credit as
    ``2,111,865.5%``. One of ``percent``, ``count``, ``currency``, ``text``.
    """
    return {"value": value, "note": note, "unit": unit}


def get_compliance_matrix(
    intelligence,
    *,
    filing: Dict[str, Any],
    recon: Dict[str, Any],
    einvoice: Dict[str, Any],
    ewaybill: Dict[str, Any],
    itc: Dict[str, Any],
    tds: Dict[str, Any],
    pan: Dict[str, Any],
    customs: Dict[str, Any],
    legal: Dict[str, Any],
    queue: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Per-area readiness: reconciled, filed/paid, evidenced, escalated.

    The wireframe's coverage matrix, built only from sections already computed —
    no extra queries. Each cell is either a real figure or ``None``, which the
    frontend renders as *not available*. Filling a blank cell with a zero is how
    an unmonitored area comes to look compliant.
    """
    q_rows = (queue or {}).get("rows") or []

    # The board stores the *finding code* in `area` (e.g. `tax.missing_irn`),
    # not a matrix area name, so filtering by row label matches nothing and
    # every area silently inherits the whole queue -- which is how all six rows
    # first rendered the same three owners. Map codes to areas explicitly.
    codes_for = {
        "GST": ("tax.missing_irn", "tax.gstin_at_risk"),
        "ITC": ("tax.gstr2b_supplier_unfiled", "tax.recon_unactioned"),
        "TDS / TCS": ("tax.pan_missing",),
        "e-Waybill": ("tax.ewaybill_pending",),
        # No agent detector raises customs or legal findings, so these areas
        # own no queue rows. An empty tuple keeps them blank; omitting them
        # would fall through to "every row" and borrow another area's owners.
        "Customs / Import": (),
        "Notices, Demands & Legal": (),
    }

    def _scoped(area: str) -> List[Dict[str, Any]]:
        codes = codes_for.get(area)
        if codes is None:
            return list(q_rows)
        return [r for r in q_rows if r.get("area") in codes]

    def owners(area: str) -> Optional[str]:
        roles = sorted({
            r.get("owner_role") for r in _scoped(area) if r.get("owner_role")
        })
        return ", ".join(roles) if roles else None

    def open_count(area: str) -> int:
        return len(_scoped(area))

    gstr3b = (filing or {}).get("gstr3b") or {}
    gstr1 = (filing or {}).get("gstr1") or {}
    recon_ok = isinstance(recon, dict) and "error" not in recon
    itc_ok = isinstance(itc, dict) and "error" not in itc

    rows: List[Dict[str, Any]] = [
        {
            "area": "GST",
            "status": (filing or {}).get("gstr3b_status") or gstr3b.get("status") or "Unknown",
            "reconciliation": _cell(
                round(float(recon.get("reconciliation_score") or 0), 2) if recon_ok else None,
                "Purchase vs GSTR-2A/2B match rate",
                "percent",
            ),
            "filing": _cell(
                f"{gstr3b.get('filed') or 0}/{gstr3b.get('total') or 0} GSTR-3B",
                f"GSTR-1 {gstr1.get('filed') or 0}/{gstr1.get('total') or 0}",
            ),
            "evidence": _cell(
                round(float((einvoice or {}).get("coverage_pct") or 0), 2),
                "e-Invoice IRN coverage of invoices that require one",
                "percent",
            ),
            "escalation": _cell(owners("GST"), "Owners on the open GST queue"),
            "open_actions": open_count("GST"),
            "exposure": round(float(itc.get("at_risk_supplier_unfiled") or 0), 2) if itc_ok else None,
        },
        {
            "area": "ITC",
            "status": "At Risk" if itc_ok and float(itc.get("at_risk_supplier_unfiled") or 0) > 0 else "Unknown" if not itc_ok else "Healthy",
            "reconciliation": _cell(
                int(itc.get("recon_unactioned") or 0) if itc_ok else None,
                "Inward supply rows with no action taken",
                "count",
            ),
            "filing": _cell(
                round(float(itc.get("utilization_pct") or 0), 2) if itc_ok else None,
                "Credit utilisation %",
                "percent",
            ),
            "evidence": _cell(
                round(float(itc.get("utilised") or 0), 2) if itc_ok else None,
                "Input credit set off against output tax",
                "currency",
            ),
            "escalation": _cell(owners("ITC"), "Owners on the open ITC queue"),
            "open_actions": open_count("ITC"),
            "exposure": round(float(itc.get("at_risk_supplier_unfiled") or 0), 2) if itc_ok else None,
        },
        {
            "area": "TDS / TCS",
            "status": "Action Required" if (pan or {}).get("available") and ((pan.get("summary") or {}).get("suppliers_missing_pan") or 0) > 0 else "On Track",
            "reconciliation": _cell(
                round(float((tds or {}).get("receivable") or 0), 2),
                "TDS suffered on sales, to reconcile to customer certificates",
                "currency",
            ),
            "filing": _cell(
                round(float((tds or {}).get("total_payable") or 0), 2),
                "Deducted and payable",
                "currency",
            ),
            "evidence": _cell(
                None,
                "Challan / certificate evidence is not recorded on this install",
            ),
            "escalation": _cell(owners("TDS / TCS"), "Owners on the open TDS queue"),
            "open_actions": open_count("TDS / TCS"),
            "exposure": round(float((pan.get("summary") or {}).get("exposure") or 0), 2) if (pan or {}).get("available") else None,
        },
        {
            "area": "e-Waybill",
            "status": "Action Required" if int((ewaybill or {}).get("pending") or 0) > 0 else "On Track",
            "reconciliation": _cell(
                int((ewaybill or {}).get("active") or 0),
                "Active covers in the window",
                "count",
            ),
            "filing": _cell(
                int((ewaybill or {}).get("pending") or 0),
                "Pending or failed generation",
                "count",
            ),
            "evidence": _cell(
                int((ewaybill or {}).get("cancelled") or 0),
                "Cancelled covers",
                "count",
            ),
            "escalation": _cell(owners("e-Waybill"), "Owners on the open e-Waybill queue"),
            "open_actions": open_count("e-Waybill"),
            "exposure": None,
        },
        {
            "area": "Customs / Import",
            "status": (
                "Not Available" if not (customs or {}).get("available")
                else "No Activity" if int(customs.get("documents") or 0) == 0
                else "Action Required" if int(customs.get("unreconciled") or 0) > 0
                else "On Track"
            ),
            "reconciliation": _cell(
                int(customs.get("unreconciled") or 0) if (customs or {}).get("available") else None,
                (customs or {}).get("note") or "Unreconciled Bills of Entry",
                "count",
            ),
            "filing": _cell(
                round(float(customs.get("customs_duty") or 0), 2) if (customs or {}).get("available") else None,
                "Customs duty paid",
                "currency",
            ),
            "evidence": _cell(None, "Bill of Entry to purchase-invoice linkage"),
            "escalation": _cell(None, ""),
            "open_actions": 0,
            "exposure": None,
        },
        {
            "area": "Notices, Demands & Legal",
            "status": (
                "Not Available" if not (legal or {}).get("available")
                else "Action Required" if int((legal.get("summary") or {}).get("overdue") or 0) > 0
                else "Under Control" if int((legal.get("summary") or {}).get("open") or 0) > 0
                else "Clear"
            ),
            # `disputed` is a rupee amount, not a row count. `int()` here
            # truncated the paise off a money figure and then the frontend
            # printed it as a percentage.
            "reconciliation": _cell(
                round(float((legal.get("summary") or {}).get("disputed") or 0), 2) if (legal or {}).get("available") else None,
                "Disputed amount across open matters",
                "currency",
            ),
            "filing": _cell(
                int((legal.get("summary") or {}).get("due_soon") or 0) if (legal or {}).get("available") else None,
                f"Replies or hearings within {DUE_SOON_DAYS} days",
                "count",
            ),
            "evidence": _cell(
                int((legal.get("summary") or {}).get("without_evidence") or 0) if (legal or {}).get("available") else None,
                "Open matters with no evidence recorded",
                "count",
            ),
            "escalation": _cell(owners("Notices, Demands & Legal"), ""),
            "open_actions": int((legal.get("summary") or {}).get("open") or 0) if (legal or {}).get("available") else 0,
            "exposure": round(float((legal.get("summary") or {}).get("exposure") or 0), 2) if (legal or {}).get("available") else None,
        },
    ]
    return rows
