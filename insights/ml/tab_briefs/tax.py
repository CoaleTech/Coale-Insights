"""Tab briefs for the Tax dashboard (Rule 7: server-built sentences).

Customs is merged into `legal` ("Notices & Customs"), so there is no `customs` key.
"""

from datetime import date, datetime

from . import action, brief, detail, money, plural

PROBLEM_STATUSES = {"Overdue", "At Risk", "Action Required"}


def _label(area: str) -> str:
    return area.replace("tax.", "").replace("_", " ").replace(".", " ")


def _today() -> date:
    return date.today()


def _pct(v) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".") + "%"


def _gst(p: dict):
    rec, itc = p.get("reconciliation_score") or {}, p.get("itc_health") or {}
    score = rec.get("match_rate_pct")
    if score is None:
        return None
    cur = p.get("base_currency")
    risk = itc.get("at_risk_supplier_unfiled") or 0
    text = f"2A/2B match rate is {_pct(score)}."
    if risk:
        text += (
            f" {money(risk, cur)} of ITC is at risk across {plural(itc.get('at_risk_invoice_count') or 0, 'invoice')} "
            "from suppliers that have not filed."
        )
    if rec.get("unactioned_count"):
        text += f" {plural(rec['unactioned_count'], 'row')} unactioned."
    details = [detail(
        "2A/2B rows",
        ", ".join(
            f"{label} {rec[k + '_count']:,} ({money(rec.get(k + '_amount'), cur)})"
            for label, k in (("matched", "matched"), ("suggested", "suggested"), ("mismatched", "mismatch"), ("unmatched", "unmatched"))
            if rec.get(k + "_count") is not None
        ) + f" of {(rec.get('total_count') or 0):,}.",
    )]
    if itc.get("available") is not None:
        details.append(detail(
            "ITC",
            f"{money(itc['available'], cur)} available, {money(itc.get('utilised'), cur)} utilised ({itc.get('utilization_pct')}%), "
            f"{money(itc.get('balance'), cur)} balance.",
        ))
    actions = []
    if rec.get("unactioned_count"):
        actions.append(action(
            "Action the unmatched 2A/2B rows",
            f"{plural(rec['unactioned_count'], 'row')} still need a decision." + (f" Data runs to {rec['data_through']}." if rec.get("data_through") else ""),
            impact=money(rec.get("unmatched_amount"), cur),
        ))
    if risk:
        actions.append(action(
            "Chase suppliers that have not filed",
            f"{plural(itc.get('at_risk_invoice_count') or 0, 'invoice')} sit with suppliers that have not filed their return.",
            impact=money(risk, cur),
        ))
    return brief("high" if risk and rec.get("unactioned_count") else "medium" if risk else "low", text, details, actions)


def _compliance(p: dict):
    rows = p.get("compliance_matrix") or []
    score = p.get("compliance_score")
    if not rows or score is None:
        return None
    bad = [r for r in rows if r.get("status") in PROBLEM_STATUSES]
    idle = [r["area"] for r in rows if r.get("status") == "No Activity"]
    text = f"Compliance score is {_pct(score)} across {plural(len(rows), 'area')}."
    if bad:
        text += " " + ", ".join(f"{r['area']} {r['status']}" for r in bad) + "."
    if idle:
        text += f" {', '.join(idle)} has no activity, so the score does not test it."
    sev = "high" if any(r["status"] == "Overdue" for r in bad) else "medium" if bad else "low"
    cur = p.get("base_currency")
    details = [
        detail(r["area"], f"{r['status']}, {(money(r['exposure'], cur) + ' exposure, ') if r.get('exposure') else ''}{plural(r.get('open_actions') or 0, 'open action')}.")
        for r in sorted(bad, key=lambda r: -(r.get("exposure") or 0))
    ]
    actions = [
        action(
            f"Open an action for {r['area']}",
            f"{r['area']} is {r['status']} with no open action.",
            impact=money(r["exposure"], cur) if r.get("exposure") else None,
        )
        for r in sorted(bad, key=lambda r: -(r.get("exposure") or 0)) if not r.get("open_actions")
    ]
    return brief(sev, text, details, actions)


def _tds(p: dict):
    tds, rcm = p.get("tds_summary") or {}, p.get("rcm_summary") or {}
    cur = p.get("base_currency")
    parts = []
    if rcm.get("available") and rcm.get("gap"):
        parts.append(
            f"RCM books-to-portal gap is {money(rcm['gap'], cur)}: books {money((rcm.get('books') or {}).get('tax'), cur)} "
            f"against portal {money((rcm.get('portal') or {}).get('tax'), cur)}."
        )
    late = [t for t in (p.get("tax_cash_outlook") or {}).get("tds_periods") or [] if t.get("overdue")]
    if tds.get("total_payable"):
        text = f"TDS payable is {money(tds['total_payable'], cur)}"
        parts.append(text + (f", {plural(len(late), 'period')} overdue." if late else "."))
    if not parts:
        return None
    details, actions = [], []
    if rcm.get("available") and rcm.get("gap"):
        b, pt = rcm.get("books") or {}, rcm.get("portal") or {}
        details.append(detail("RCM", f"Books hold {plural(b.get('invoices') or 0, 'invoice')}; the portal shows {plural(pt.get('rows') or 0, 'row')}."))
        actions.append(action("Reconcile RCM against the portal", "Books and portal tax differ.", impact=money(rcm["gap"], cur)))
    if tds.get("total_payable"):
        details.append(detail("TDS position", f"{money(tds['total_payable'], cur)} payable and {money(tds.get('receivable'), cur)} receivable, net {money(tds.get('net_position'), cur)}."))
        if late:
            actions.append(action(
                "Deposit overdue TDS",
                f"{plural(len(late), 'period')} past the due date, the earliest {min(t['due_date'] for t in late)}.",
                impact=money(sum(t.get("amount") or 0 for t in late), cur),
            ))
    return brief("medium" if rcm.get("gap") or tds.get("total_payable") else "low", " ".join(parts), details, actions)


def _planning(p: dict):
    sched = p.get("advance_tax_schedule") or []
    if not sched:
        return None
    today = _today()
    due = [(datetime.strptime(s["due_date"], "%d %b %Y").date(), s) for s in sched]
    passed = sum(1 for d, _ in due if d < today)
    nxt = next(((d, s) for d, s in due if d >= today), None)
    text = f"{passed} of {len(sched)} advance tax instalments have passed."
    if nxt:
        d, s = nxt
        text += f" Next is the {s['label']}, cumulative {s['cumulative_pct']}%, due {s['due_date']} ({plural((d - today).days, 'day')})."
    r2 = (p.get("tax_forecast") or {}).get("r_squared")
    if r2 is not None:
        text += f" The GST forecast fits at R² {r2:.2f} over {(p.get('tax_forecast') or {}).get('months_used')} closed months."
    details = [detail("Instalments", "; ".join(f"{x['label']} {x['due_date']} ({x['cumulative_pct']}%)" for x in sched) + ".")]
    fc = (p.get("tax_forecast") or {}).get("forecast") or []
    cur = p.get("base_currency")
    if fc:
        details.append(detail("Net GST forecast", ", ".join(f"month +{f['month_offset']} {money(f['projected_net_gst'], cur)}" for f in fc) + "."))
    actions = []
    if nxt:
        actions.append(action(
            f"Pay the {nxt[1]['label']}",
            f"Due {nxt[1]['due_date']}, cumulative {nxt[1]['cumulative_pct']}% of estimated annual tax.",
        ))
    return brief("medium" if passed else "low", text, details, actions)


def _actions(p: dict):
    aq = p.get("action_queue") or {}
    s = aq.get("summary")
    if not aq.get("available") or not s:
        return None
    cur = p.get("base_currency")
    late = [r for r in aq.get("rows") or [] if r.get("overdue")]
    text = f"{plural(s['open'], 'action')} open with {money(s['exposure'], cur)} exposure"
    if s.get("overdue"):
        worst = min((r.get("due_in_days") or 0) for r in late) if late else 0
        text += f", {s['overdue']} overdue" + (f" by up to {plural(-worst, 'day')}" if worst < 0 else "")
    if s.get("unassigned"):
        text += f", {s['unassigned']} unassigned"
    text += "."
    gaps = [r["area"] for r in p.get("compliance_matrix") or [] if r.get("status") in PROBLEM_STATUSES and not r.get("open_actions")]
    if gaps:
        text += f" {', '.join(gaps)} {'is' if len(gaps) == 1 else 'are'} flagged with no action."
    overdue_tds = ((p.get("tax_cash_outlook") or {}).get("overdue", {}) or {}).get("tds")
    if overdue_tds:
        text += f" TDS overdue is {money(overdue_tds, cur)}."
    details = [
        detail(_label(r["area"]).capitalize(), f"{r['priority']} priority, {r['status']}, {plural(r['age_days'], 'day')} old, due {r['due_date']}, {money(r.get('exposure'), cur)} exposure.")
        for r in (aq.get("rows") or [])[:3]
    ]
    actions = [
        action(
            f"Resolve {_label(r['area'])}",
            f"{r['status']} and {'overdue by ' + plural(-r['due_in_days'], 'day') if r.get('overdue') else 'due in ' + plural(r.get('due_in_days') or 0, 'day')}"
            + ("; no one is assigned." if not r.get("assigned_to") else "."),
            impact=money(r.get("exposure"), cur),
        )
        for r in sorted(aq.get("rows") or [], key=lambda r: r.get("due_in_days") or 0)[:3]
    ]
    return brief("high" if s.get("overdue") or gaps else "medium" if s.get("open") else "low", text, details, actions)


def _legal(p: dict):
    reg, cus = p.get("legal_register") or {}, p.get("customs_summary") or {}
    s = reg.get("summary") or {}
    if not (reg.get("available") or cus.get("available")):
        return None
    cur = p.get("base_currency")
    text = (
        f"{plural(s.get('open') or 0, 'legal matter')} open with {money(s.get('exposure') or 0, cur)} exposure"
        f"; {plural(cus.get('documents') or 0, 'Bill of Entry', 'Bills of Entry')} recorded."
    )
    active = s.get("open") or cus.get("documents")
    details = []
    if cus.get("note"):
        details.append(detail("Customs", cus["note"] + "."))
    actions = []
    if s.get("overdue"):
        actions.append(action("Resolve overdue legal matters", f"{plural(s['overdue'], 'matter')} past due.", impact=money(s.get("exposure"), cur)))
    if cus.get("unreconciled"):
        actions.append(action("Reconcile Bills of Entry", f"{plural(cus['unreconciled'], 'Bill of Entry', 'Bills of Entry')} unreconciled."))
    return brief("high" if s.get("overdue") else "medium" if active else "none", text, details, actions)


def briefs(p: dict) -> dict:
    out = {
        "gst": _gst(p),
        "compliance": _compliance(p),
        "tds": _tds(p),
        "planning": _planning(p),
        "actions": _actions(p),
        "legal": _legal(p),
    }
    return {k: v for k, v in out.items() if v}
