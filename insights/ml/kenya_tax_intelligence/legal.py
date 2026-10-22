# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Notices & Legal tab: tax assessments, objections and appeals from `Insights Tax Case`.

Statutory clocks (Tax Procedures Act) come from `rules`: objection 30 days after
the notice, KRA decision 60 days after the objection, appeal 30 days after the decision.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from insights.ml.kenya_tax_intelligence import rules
from insights.ml.kenya_tax_intelligence.common import (
    TaxContext,
    as_date,
    chip,
    doctype_exists,
    kpi,
    money_short,
    unavailable,
)

DOCTYPE = "Insights Tax Case"
OPEN_STAGES = ("Assessment received", "Objection lodged", "Appeal to Tribunal", "High Court")
STAGE_NOTES = {
    "Assessment received": "30 days to object",
    "Objection lodged": "KRA decision in 60 days",
    "Appeal to Tribunal": "30 days after decision",
    "High Court": "",
}
FIELDS = [
    "name", "case_ref", "tax_type", "period_label", "principal", "penalty_interest", "stage",
    "notice_date", "objection_date", "decision_date", "tribunal_date", "hearing_date",
    "amnesty_eligible", "company",
]
PAGE_SIZE = 50


def _open_cases(ctx: TaxContext) -> List[Dict[str, Any]]:
    rows = frappe.get_all(DOCTYPE, filters={"stage": ["in", OPEN_STAGES]}, fields=FIELDS, order_by="creation desc")
    return [r for r in rows if r.get("company") in (None, "", ctx.company)]


def _next_step(case: Dict[str, Any]):
    """(text, date) of the statutory next step for a case, or (text, None) if the date to count from is missing."""
    stage = case["stage"]
    notice, objection, decision = as_date(case.get("notice_date")), as_date(case.get("objection_date")), as_date(case.get("decision_date"))
    hearing = as_date(case.get("hearing_date"))
    if stage == "Assessment received":
        due = rules.objection_deadline(notice) if notice else None
        return (_("Lodge objection by {0}").format(due.strftime("%d %b")) if due else _("Set the notice date"), due)
    if stage == "Objection lodged":
        if decision:
            due = rules.appeal_deadline(decision)
            return _("Appeal to Tribunal by {0}").format(due.strftime("%d %b")), due
        due = rules.decision_deadline(objection) if objection else None
        return (_("KRA decision by {0}").format(due.strftime("%d %b")) if due else _("Set the objection date"), due)
    if hearing:
        return _("Hearing {0}").format(hearing.strftime("%d %b")), hearing
    return _("Awaiting hearing date"), None


def _stage_chip(case: Dict[str, Any], days: Optional[int]) -> Dict[str, str]:
    if case.get("amnesty_eligible"):
        return chip("pos", _("Amnesty-eligible"))
    stage = case["stage"]
    if stage == "Assessment received":
        return chip("neg" if days is not None and days <= 30 else "warn", _("Objection window"))
    return {
        "Objection lodged": chip("warn", _("Objection lodged")),
        "Appeal to Tribunal": chip("acc", _("Tribunal")),
    }.get(stage, chip("mut", _(stage)))


def _case_rows(ctx: TaxContext) -> List[Dict[str, Any]]:
    out = []
    for c in _open_cases(ctx):
        text, due = _next_step(c)
        days = (due - ctx.today).days if due else None
        out.append({
            "case_ref": c["case_ref"], "tax_type": c["tax_type"], "period_label": c.get("period_label"),
            "principal": c.get("principal") or 0, "penalty_interest": c.get("penalty_interest") or 0,
            "stage": c["stage"], "stage_chip": _stage_chip(c, days), "next_step": text,
            "next_date": due.isoformat() if due else None, "days_left": days,
            "amnesty_eligible": bool(c.get("amnesty_eligible")),
            "drill": {"metric": "legal_case", "filters": {"case_ref": c["case_ref"]}},
        })
    out.sort(key=lambda r: (r["next_date"] is None, r["next_date"] or ""))
    return out


def compute(ctx: TaxContext) -> Dict[str, Any]:
    if not doctype_exists(DOCTYPE):
        return unavailable(_("Run bench migrate to create the Insights Tax Case doctype"))
    cases = _case_rows(ctx)
    principal = sum(c["principal"] for c in cases)
    penalty = sum(c["penalty_interest"] for c in cases)
    due_soon = [c for c in cases if c["stage"] == "Assessment received" and c["days_left"] is not None and c["days_left"] <= 30]
    overdue = [c for c in due_soon if c["days_left"] < 0]
    tribunal = [c for c in cases if c["stage"] == "Appeal to Tribunal"]
    amnesty = [c for c in cases if c["amnesty_eligible"]]
    next_due = min((c["next_date"] for c in due_soon), default=None)

    amnesty_by_tax: Dict[str, float] = {}
    for c in amnesty:
        amnesty_by_tax[c["tax_type"]] = amnesty_by_tax.get(c["tax_type"], 0) + c["principal"]

    dates = [
        {
            "date": c["next_date"], "weekday": as_date(c["next_date"]).strftime("%a"),
            "title": f"{c['case_ref']}: {c['next_step']}",
            "sub": f"{c['tax_type']} {c['period_label'] or ''}".strip(),
            "chip": chip("neg" if c["days_left"] <= 14 else "warn" if c["days_left"] <= 30 else "mut", f"{c['days_left']} d"),
        }
        for c in cases if c["next_date"] and c["days_left"] >= 0
    ]
    if amnesty:
        dates.append({
            "date": rules.AMNESTY_DEADLINE.isoformat(), "weekday": rules.AMNESTY_DEADLINE.strftime("%a"),
            "title": _("Amnesty principal deadline"), "sub": money_short(ctx, sum(amnesty_by_tax.values())),
            "chip": chip("warn", f"{(rules.AMNESTY_DEADLINE - ctx.today).days} d"),
        })
    dates.sort(key=lambda r: r["date"])

    return {
        "available": True,
        "kpis": [
            {**kpi("open_cases", _("Open assessments"), len(cases), "count",
                   _("Across {0} tax heads").format(len({c["tax_type"] for c in cases}))),
             "drill": {"metric": "legal_cases", "filters": {}}},
            kpi("amount_in_dispute", _("Amount in dispute"), principal + penalty, "money",
                _("Principal {0} · interest and penalty {1}").format(money_short(ctx, principal), money_short(ctx, penalty))),
            {**kpi("objections_due_30d", _("Objections due in 30 days"), len(due_soon), "count",
                   (_("Next on {0}").format(as_date(next_due).strftime("%d %b")) if next_due else _("None open"))
                   + (_(" · {0} overdue").format(len(overdue)) if overdue else ""),
                   "bad" if due_soon else "neutral"),
             "drill": {"metric": "legal_objections_due", "filters": {}}},
            kpi("tribunal", _("Before Tax Appeals Tribunal"), len(tribunal), "count",
                money_short(ctx, sum(c["principal"] + c["penalty_interest"] for c in tribunal))),
            kpi("amnesty_principal", _("Principal in amnesty scope"), sum(amnesty_by_tax.values()) if amnesty else 0, "money",
                _("Principal only if paid by {0}").format(rules.AMNESTY_DEADLINE.strftime("%d %b %Y")), "warn" if amnesty else "neutral"),
            kpi("records_near_5y", _("Records near 5-year limit"), None, "count",
                _("Needs a document retention register; not tracked")),
        ],
        "stages": [
            {"label": s, "count": sum(1 for c in cases if c["stage"] == s), "note": STAGE_NOTES[s]} for s in OPEN_STAGES
        ],
        "cases": cases,
        "dates": dates[:10],
        "amnesty_by_tax": [{"tax": t, "amount": a} for t, a in sorted(amnesty_by_tax.items(), key=lambda kv: -kv[1])],
        "exceptions": [{"case_ref": c["case_ref"], "next_step": c["next_step"], "days_left": c["days_left"]} for c in due_soon],
    }


# --------------------------------------------------------------------------- drill-down
_COLUMNS = [
    {"label": "Case Ref", "fieldname": "case_ref", "fieldtype": "Link", "options": DOCTYPE},
    {"label": "Tax", "fieldname": "tax_type", "fieldtype": "Data"},
    {"label": "Period", "fieldname": "period_label", "fieldtype": "Data"},
    {"label": "Stage", "fieldname": "stage", "fieldtype": "Data"},
    {"label": "Principal", "fieldname": "principal", "fieldtype": "Currency"},
    {"label": "Penalty and Interest", "fieldname": "penalty_interest", "fieldtype": "Currency"},
    {"label": "Next Step", "fieldname": "next_step", "fieldtype": "Data"},
    {"label": "Next Date", "fieldname": "next_date", "fieldtype": "Date"},
]


def drilldown(ctx: TaxContext, metric: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if metric not in ("legal_cases", "legal_case", "legal_objections_due"):
        return None
    frappe.has_permission(DOCTYPE, throw=True)
    rows = _case_rows(ctx) if doctype_exists(DOCTYPE) else []
    if metric == "legal_case":
        rows = [r for r in rows if r["case_ref"] == filters.get("case_ref")]
    elif metric == "legal_objections_due":
        rows = [r for r in rows if r["stage"] == "Assessment received" and r["days_left"] is not None and r["days_left"] <= 30]
    start = (int(filters.get("page") or 1) - 1) * PAGE_SIZE
    return {"columns": _COLUMNS, "rows": rows[start:start + PAGE_SIZE], "total": len(rows)}
