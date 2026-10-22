# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Action queue: rule-generated from the other tab payloads. Nothing is written to ToDo or any doctype."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Dict, List, Tuple

from frappe import _

from insights.ml.kenya_tax_intelligence import rules
from insights.ml.kenya_tax_intelligence.common import TaxContext, as_date, chip, kpi, safe, unavailable

MAX_ROWS = 25
SOURCES = ("wht", "vat", "etims", "payroll", "income", "legal", "customs")
PRIORITIES = {"critical": ("neg", "Critical"), "high": ("warn", "High"), "medium": ("mut", "Medium")}


def _tab(tabs: Dict[str, Any], key: str) -> Dict[str, Any]:
    t = tabs.get(key) or {}
    return t if t.get("available") else {}


def _kpi_value(tab: Dict[str, Any], key: str):
    return next((k.get("value") for k in tab.get("kpis") or [] if k.get("key") == key), None)


def _row(priority, action, tax, tax_key, source_tab, button, due=None, exposure=None, penalty=None, drill=None) -> Dict[str, Any]:
    return {"priority": priority, "action": action, "tax": tax, "tax_key": tax_key, "source_tab": source_tab,
            "button_label": button, "due_date": due, "exposure": exposure, "penalty": penalty, "drill": drill}


def _by_urgency(days: int, critical: int = 14) -> str:
    return "critical" if days <= critical else "high"


# --------------------------------------------------------------------------- rules: (ctx, tabs) -> rows
def wht_unremitted(ctx: TaxContext, tabs: Dict[str, Any]) -> List[Dict[str, Any]]:
    late = [r for r in _tab(tabs, "wht").get("unremitted") or [] if (r.get("days_late") or 0) > 0]
    if not late:
        return []
    payees = ", ".join(dict.fromkeys(r["payee"] for r in late if r.get("payee")))
    withheld = sum(r.get("withheld") or 0 for r in late)
    penalty = sum(rules.late_payment_cost(r.get("withheld") or 0, as_date(r["due_on"]) or ctx.today, ctx.today)["total"] for r in late)
    return [_row("critical", _("Remit {0} late WHT payments ({1})").format(len(late), payees), "WHT", "wht", "wht", _("Pay now"),
                 due=min(as_date(r["due_on"]) or ctx.today for r in late), exposure=withheld, penalty=penalty,
                 drill={"metric": "wht_unremitted", "filters": {}})]


def input_vat_window(ctx: TaxContext, tabs: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for r in _tab(tabs, "vat").get("suppliers_at_risk") or []:
        days = r.get("days_left")
        if days is None or days < 0 or days > 30:
            continue
        rows.append(_row(_by_urgency(days), _("Claim input VAT for {0} before the 6-month window closes").format(r["supplier"]),
                         "VAT", "vat", "vat", _("Open"), due=as_date(r.get("window_closes")), exposure=r.get("input_vat_at_risk"),
                         drill=r.get("drill")))
    return rows


def wht_rate_exceptions(ctx: TaxContext, tabs: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for r in _tab(tabs, "wht").get("rate_exceptions") or []:
        exp, app = r.get("expected_rate"), r.get("applied_rate") or 0
        if exp is None:
            continue
        frac = lambda x: x / 100 if x > 1 else x  # rates may arrive as 0.2 or 20
        gap = frac(exp) - frac(app)
        if gap <= 0:
            continue
        rows.append(_row("high", _("Apply {0:g}% WHT to {1}").format(round(frac(exp) * 100, 2), r.get("payee") or r.get("payment")),
                         "WHT", "wht", "wht", _("Assign"), exposure=round((r.get("gross") or 0) * gap, 2),
                         drill={"metric": "wht_rate_exceptions", "filters": {}}))
    return rows


def etims_failures(ctx: TaxContext, tabs: Dict[str, Any]) -> List[Dict[str, Any]]:
    tab = _tab(tabs, "etims")
    rows = []
    # ponytail: issue wording decides which exception rows belong to which bucket; revisit if etims.py renames its chips
    for key, text, words in (
        ("rejected_by_kra", _("Fix {0} invoices KRA rejected"), ("reject",)),
        ("awaiting_transmission", _("Transmit {0} invoices still waiting for KRA"), ("await", "queue", "transmi", "pending")),
    ):
        n = _kpi_value(tab, key)
        if not n:
            continue
        exposure = sum(e.get("exposure") or 0 for e in tab.get("exceptions") or []
                       if any(w in ((e.get("issue_chip") or {}).get("label") or "").lower() for w in words)) or None
        rows.append(_row("high", text.format(n), "eTIMS", "etims", "etims", _("Open"), exposure=exposure,
                         drill={"metric": "etims_exceptions", "filters": {}}))
    return rows


def paye_exceptions(ctx: TaxContext, tabs: Dict[str, Any]) -> List[Dict[str, Any]]:
    payroll = _tab(tabs, "payroll")
    nxt = next((as_date(r["due_date"]) for r in payroll.get("schedule") or [] if as_date(r.get("due_date")) and as_date(r["due_date"]) >= ctx.today), None)
    rows = []
    for e in payroll.get("exceptions") or []:
        n = e.get("employees")
        n = len(n) if isinstance(n, (list, tuple)) else n
        rows.append(_row("medium", f"{e['check']} ({n})" if n is not None else e["check"], "PAYE", "paye", "payroll", _("Open"),
                         due=nxt, exposure=e.get("impact"), drill=e.get("drill")))
    return rows


def instalment_shortfall(ctx: TaxContext, tabs: Dict[str, Any]) -> List[Dict[str, Any]]:
    insts = _tab(tabs, "income").get("instalments") or []
    upcoming = next((as_date(i["due_date"]) for i in insts if as_date(i.get("due_date")) and as_date(i["due_date"]) >= ctx.today), None)
    rows = []
    for n, i in enumerate(insts, 1):
        due, req, paid = as_date(i.get("due_date")), i.get("required"), i.get("paid")
        if not due or due >= ctx.today or req is None or paid is None or req - paid <= 0.5:
            continue
        short = req - paid
        pen = round(short * rules.INSTALMENT_PENALTY, 2)
        rows.append(_row("high", _("Top up CIT instalment {0} by {1:,.0f}").format(n, short), "CIT", "cit", "income", _("Open"),
                         due=upcoming, exposure=pen, penalty=pen))
    return rows


def objection_deadline(ctx: TaxContext, tabs: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for c in _tab(tabs, "legal").get("cases") or []:
        days = c.get("days_left")
        if c.get("stage") != "Assessment received" or days is None or days > 30:
            continue
        rows.append(_row("critical" if days <= 14 else "high", _("Lodge objection {0}").format(c["case_ref"]), c["tax_type"], c["tax_type"].lower(),
                         "legal", _("Open"), due=as_date(c["next_date"]), exposure=(c.get("principal") or 0) + (c.get("penalty_interest") or 0),
                         drill=c.get("drill")))
    return rows


def amnesty_outstanding(ctx: TaxContext, tabs: Dict[str, Any]) -> List[Dict[str, Any]]:
    a = _tab(tabs, "overview").get("amnesty") or {}
    out = a.get("principal_outstanding")
    if not out or out <= 0:
        return []
    days = a["days_left"]
    return [_row("critical" if days <= 30 else "high" if days <= 90 else "medium",
                 _("Pay {0:,.0f} principal by {1} to waive interest and penalties").format(out, rules.AMNESTY_DEADLINE.strftime("%d %b %Y")),
                 "Amnesty", "amnesty", "overview", _("Open"), due=rules.AMNESTY_DEADLINE, exposure=a.get("penalty_interest_waivable"))]


def missing_export_docs(ctx: TaxContext, tabs: Dict[str, Any]) -> List[Dict[str, Any]]:
    n = _kpi_value(_tab(tabs, "customs"), "entries_missing_docs")  # None unless the data tracks documents
    if not n:
        return []
    return [_row("medium", _("Add export certificates for {0} import entries").format(n), "Customs", "customs", "customs", _("Assign"))]


RULES: List[Tuple[str, Callable]] = [
    ("WHT unremitted past 5 working days", wht_unremitted),
    ("Input VAT within 30 days of the 6-month window", input_vat_window),
    ("WHT rate exceptions", wht_rate_exceptions),
    ("eTIMS rejected or untransmitted", etims_failures),
    ("PAYE exceptions", paye_exceptions),
    ("CIT instalment shortfall", instalment_shortfall),
    ("Objection deadline within 30 days", objection_deadline),
    ("Amnesty principal outstanding", amnesty_outstanding),
    ("Missing export documents", missing_export_docs),
]


# --------------------------------------------------------------------------- orchestration
def _due_label(due: date, today: date) -> str:
    d = (due - today).days
    return _("Overdue {0} d").format(-d) if d < 0 else _("{0} · {1} d").format(due.strftime("%d %b"), d)


def compute(ctx: TaxContext, tabs: Dict[str, Any]) -> Dict[str, Any]:
    if not any(_tab(tabs, k) for k in SOURCES):
        return unavailable(_("No source tab has data to generate actions from"))
    all_rows, hits = [], []
    for name, fn in RULES:
        found = safe(fn, ctx, tabs, default=[]) or []
        hits.append({"rule": _(name), "hits": len(found)})
        all_rows += found
    rank = {"critical": 0, "high": 1, "medium": 2}
    all_rows.sort(key=lambda r: (-(r["exposure"] or 0), rank[r["priority"]]))
    rows = []
    for r in all_rows[:MAX_ROWS]:
        tone, label = PRIORITIES[r["priority"]]
        due = r["due_date"]
        rows.append({**r, "chip": chip(tone, _(label)), "owner": None, "due_date": due.isoformat() if due else None,
                     "due_label": _due_label(due, ctx.today) if due else _("No fixed date")})

    soon = [r for r in all_rows if r["due_date"] and (r["due_date"] - ctx.today).days <= 7]
    penalties = [r["penalty"] for r in all_rows if r["penalty"] is not None]
    by_tax: Dict[str, int] = {}
    for r in all_rows:
        by_tax[r["tax"]] = by_tax.get(r["tax"], 0) + 1
    critical = sum(1 for r in all_rows if r["priority"] == "critical")
    return {
        "available": True,
        "kpis": [
            kpi("open_actions", _("Open actions"), len(all_rows), "count", _("Generated by compliance rules")),
            kpi("critical", _("Critical"), critical, "count", _("Penalty accrues until fixed"), "bad" if critical else "neutral"),
            kpi("due_in_7_days", _("Due in 7 days"), len(soon), "count", "", "warn" if soon else "neutral"),
            kpi("penalty_if_missed", _("Penalty if missed"), sum(penalties) if penalties else None, "money",
                _("Late-payment and instalment penalties; other rules carry no fixed penalty"), "bad" if penalties else "neutral"),
            kpi("resolved_this_month", _("Resolved this month"), None, "count", _("Not tracked: actions are generated, not stored")),
            kpi("unassigned", _("Unassigned"), None, "count", _("Not tracked: owners are not stored")),
        ],
        "rows": rows,
        "total_open": len(all_rows),
        "by_tax": sorted(({"label": k, "count": v} for k, v in by_tax.items()), key=lambda x: -x["count"]),
        "by_priority_7d": [{"label": PRIORITIES[p][1], "count": sum(1 for r in soon if r["priority"] == p)} for p in rank],
        "rules": hits,
    }
