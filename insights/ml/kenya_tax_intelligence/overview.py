# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Overview tab, derived from the other tab payloads.

Obligation amounts come from the section tabs (payroll schedule, VAT monthly, customs excise,
income instalments). ERPNext has no "return filed" record, so status is *payment evidence*:
debits on the matched tax accounts from Payment Entry / Journal Entry after the period ended,
applied against the computed liability. Chips therefore say Paid / Paid late / Part-paid /
Overdue / Not started, never "Filed".
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

import frappe
from frappe import _

from insights.ml.kenya_tax_intelligence import rules
from insights.ml.kenya_tax_intelligence.common import (
    TaxContext,
    as_date,
    chip,
    holidays,
    kpi,
    month_key,
    month_starts,
    pct,
    tax_accounts,
)

PAYROLL_KINDS = ("paye", "nssf", "shif", "ahl", "nita")
SETTLEMENT_VOUCHERS = ("Payment Entry", "Journal Entry")
TAX_LABELS = {
    "paye": "PAYE", "nssf": "NSSF (EE + ER)", "shif": "SHIF", "ahl": "AHL (EE + ER)", "nita": "NITA",
    "vat": "VAT", "excise": "Customs & excise", "cit": "CIT instalments", "wht": "Withholding tax",
}
# payroll rows due on the same date are one payment to KRA, so they are settled together
_RULE_TEXT = {"vat": "20th of the next month", "excise": "20th of the next month", "ahl": "9 working days after month end"}


# --------------------------------------------------------------------------- payment evidence
def _payments(ctx: TaxContext, accounts: List[str], start: date) -> List[Tuple[date, float]]:
    """(posting_date, amount) of settlement debits on `accounts` from `start` to today."""
    if not accounts:
        return []
    key = ("pay", tuple(sorted(accounts)), start)
    if key not in ctx._cache:
        rows = frappe.db.sql(
            """SELECT posting_date, SUM(debit - credit) FROM `tabGL Entry`
               WHERE company = %s AND is_cancelled = 0 AND account IN %s AND voucher_type IN %s
                 AND posting_date BETWEEN %s AND %s GROUP BY posting_date""",
            (ctx.company, tuple(accounts), SETTLEMENT_VOUCHERS, start, ctx.today),
        )
        ctx._cache[key] = [(as_date(d), float(a or 0)) for d, a in rows]
    return ctx._cache[key]


def _settle(pay: List[Tuple[date, float]], liabs: List[Tuple[Any, date, float, date]], today: date) -> Dict[Any, Dict[str, Any]]:
    """Apply payments oldest-liability-first. `liabs` = (key, period_end, amount, due), oldest first.

    A payment only counts toward periods that ended before it. Returns per key
    {status: paid|paid_late|part|overdue|not_started, unpaid, paid_on, pct}.
    """
    pool = [[d, a] for d, a in sorted(pay) if a > 0]
    out = {}
    for key, period_end, amount, due in liabs:
        need, paid_on = amount, None
        for item in pool:
            if item[1] <= 0 or item[0] <= period_end:
                continue
            take = min(item[1], need)
            item[1] -= take
            need -= take
            if need <= 0.5:
                paid_on = item[0]
                break
        got = amount - max(need, 0)
        if paid_on:
            status = "paid" if paid_on <= due else "paid_late"
        elif got > 0:
            status = "part"
        else:
            status = "overdue" if today > due else "not_started"
        out[key] = {"status": status, "unpaid": 0.0 if paid_on else max(need, 0), "paid_on": paid_on, "pct": pct(got, amount)}
    return out


def _chip_for(o: Dict[str, Any], today: date) -> Dict[str, str]:
    st = o["status"]
    if st == "paid":
        return chip("pos", _("Paid {0}").format(o["paid_on"].strftime("%d %b")) if o.get("paid_on") else _("Paid"))
    if st == "paid_late":
        return chip("neg", _("Paid {0} days late").format((o["paid_on"] - o["due"]).days))
    if st == "part":
        return chip("warn", _("Part-paid {0}%").format(round(o["pct"] or 0)))
    if st == "overdue":
        return chip("neg", _("Overdue {0} d").format((today - o["due"]).days))
    if st == "not_started":
        return chip("mut", _("Not started"))
    return chip("mut", _("No payment evidence"))


# --------------------------------------------------------------------------- obligations
def _obligation(key, tax_key, label, period_end, due, liability, status=None, parts=()) -> Dict[str, Any]:
    return {"key": key, "tax_key": tax_key, "label": label, "period_end": period_end, "due": due,
            "liability": liability, "status": status, "unpaid": liability, "paid_on": None, "pct": None, "parts": list(parts)}


def _obligations(ctx: TaxContext, tabs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Current-cycle obligations with their settlement, from the tab payloads."""
    out: List[Dict[str, Any]] = []
    hol = holidays(ctx)
    prev_end = rules.month_end(rules.add_months(ctx.today.replace(day=1), -1))

    payroll = tabs.get("payroll") or {}
    groups: Dict[date, List[Dict[str, Any]]] = {}
    for r in payroll.get("schedule") or []:
        if as_date(r.get("due_date")):
            groups.setdefault(as_date(r["due_date"]), []).append(r)
    for due, rows in sorted(groups.items()):
        kinds = [rules.match_kind(r["remittance"], rules.SALARY_COMPONENT_PATTERNS) or "paye" for r in rows]
        amounts = [r.get("amount") for r in rows]
        known = [a for a in amounts if a is not None]
        pe = rules.month_end(due.replace(day=1) - timedelta(days=1))
        o = _obligation(f"payroll:{due}", "paye" if "paye" in kinds else kinds[0], " / ".join(r["remittance"] for r in rows), pe, due,
                        sum(known) if known else None,
                        parts=[(r["remittance"], k, a) for r, k, a in zip(rows, kinds, amounts)])
        o["accounts"] = sorted({a for k in kinds for a in tax_accounts(ctx, k)})
        out.append(o)

    vat = tabs.get("vat") or {}
    net = next((m.get("net") for m in vat.get("monthly") or [] if m.get("month") == month_key(prev_end)), None)
    if vat.get("available") and net is not None:
        o = _obligation("vat", "vat", "VAT3", prev_end, rules.monthly_due_dates(prev_end, hol)["vat"], max(net, 0.0))
        o["accounts"] = tax_accounts(ctx, "vat_output")
        out.append(o)

    excise = [r.get("amount") for r in (tabs.get("customs") or {}).get("excise") or [] if r.get("amount") is not None]
    if excise:
        o = _obligation("excise", "excise", "Excise duty", prev_end, rules.monthly_due_dates(prev_end, hol)["excise"], sum(excise))
        o["accounts"] = tax_accounts(ctx, "excise")
        out.append(o)

    for n, inst in enumerate((tabs.get("income") or {}).get("instalments") or [], 1):
        due, req, paid = as_date(inst.get("due_date")), inst.get("required"), inst.get("paid")
        if not due:
            continue
        o = _obligation(f"cit:{n}", "cit", _("CIT instalment {0}").format(n), None, due, req, parts=[(inst.get("label"), "cit", req)])
        if req is not None and paid is not None:
            o["unpaid"] = max(req - paid, 0.0)
            o["pct"] = pct(min(paid, req), req)
            o["status"] = "paid" if o["unpaid"] <= 0.5 else "part" if paid > 0 else "overdue" if ctx.today > due else "not_started"
        out.append(o)

    for o in out:
        accounts = o.pop("accounts", None)
        if accounts and o["liability"] and o["period_end"]:
            pay = _payments(ctx, accounts, o["period_end"] + timedelta(days=1))
            o.update(_settle(pay, [(0, o["period_end"], o["liability"], o["due"])], ctx.today)[0])
        due_in = (o["due"] - ctx.today).days
        o["chip"] = chip("acc", _("Due in {0} d").format(due_in)) if due_in >= 0 and o["status"] in (None, "not_started") else _chip_for(o, ctx.today)
    return out


# --------------------------------------------------------------------------- sections
def _deadlines(ctx: TaxContext, tabs: Dict[str, Any], obls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    horizon = ctx.today + timedelta(days=30)
    rows = []
    for o in obls:
        if not (ctx.today <= o["due"] <= horizon) or o["status"] in ("paid", "paid_late"):
            continue
        sub = _RULE_TEXT.get(o["tax_key"]) or (
            _("25% of the higher of 110% of prior-year tax or the current-year estimate") if o["tax_key"] == "cit"
            else _("9th of the next month"))
        if o["period_end"]:
            sub = f"{o['period_end'].strftime('%b %Y')} · {sub}"
        rows.append({"date": o["due"], "title": o["label"], "sub": sub, "amount": o["unpaid"], "chip": o["chip"], "tax_key": o["tax_key"]})
    # corporate tax balance and return: fixed statutory dates from the income-year end
    for ye in (ctx.fy_start - timedelta(days=1), ctx.fy_end):
        for title, due, rule_text in (
            (_("CIT balance of tax"), rules.cit_balance_due(ye), _("Last day of the 4th month after year end")),
            (_("CIT return"), rules.cit_return_due(ye), _("Last day of the 6th month after year end")),
        ):
            if ctx.today <= due <= horizon:
                rows.append({"date": due, "title": title, "sub": rule_text, "amount": None,
                             "chip": chip("acc", _("Due in {0} d").format((due - ctx.today).days)), "tax_key": "cit"})
    rows.sort(key=lambda r: r["date"])
    return [{**r, "date": r["date"].isoformat(), "weekday": r["date"].strftime("%a")} for r in rows]


def _wht_overdue(tabs: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [r for r in (tabs.get("wht") or {}).get("unremitted") or [] if (r.get("days_late") or 0) > 0]


def _overdue(ctx: TaxContext, tabs: Dict[str, Any], obls: List[Dict[str, Any]]):
    """(principal, penalty+interest, count) of unpaid, past-due items."""
    principal = penalty = 0.0
    n = 0
    for o in obls:
        if o["due"] < ctx.today and o["status"] in ("overdue", "part") and o["unpaid"]:
            cost = rules.late_payment_cost(o["unpaid"], o["due"], ctx.today)
            principal += o["unpaid"]
            penalty += cost["total"]
            n += 1
    for r in _wht_overdue(tabs):
        w = r.get("withheld") or 0
        cost = rules.late_payment_cost(w, as_date(r["due_on"]) or ctx.today, ctx.today)
        principal += w
        penalty += cost["total"]
        n += 1
    return principal, penalty, n


def _amnesty(ctx: TaxContext, tabs: Dict[str, Any], obls: List[Dict[str, Any]]) -> Dict[str, Any]:
    out = {
        "deadline": rules.AMNESTY_DEADLINE.isoformat(), "scope_end": rules.AMNESTY_PERIOD_END.isoformat(),
        "days_left": (rules.AMNESTY_DEADLINE - ctx.today).days, "principal_total": None, "principal_paid": None,
        "principal_outstanding": None, "penalty_interest_waivable": None, "by_tax": [],
    }
    legal = tabs.get("legal") or {}
    if not legal.get("available"):
        return out
    cases = [c for c in legal.get("cases") or [] if c.get("amnesty_eligible")]
    by_tax = {r["tax"]: r["amount"] for r in legal.get("amnesty_by_tax") or []}
    total = sum(c["principal"] for c in cases)
    waivable = sum(c["penalty_interest"] for c in cases)
    for o in obls:  # overdue obligations from periods inside the amnesty scope
        if o["period_end"] and o["period_end"] <= rules.AMNESTY_PERIOD_END and o["due"] < ctx.today and o["unpaid"] and o["status"] in ("overdue", "part"):
            total += o["unpaid"]
            waivable += rules.late_payment_cost(o["unpaid"], o["due"], ctx.today)["total"]
            by_tax[o["label"]] = by_tax.get(o["label"], 0) + o["unpaid"]
    # ponytail: ERPNext records no part-payment against a disputed assessment, so "paid" stays None
    out.update(principal_total=total, principal_outstanding=total, penalty_interest_waivable=waivable,
               by_tax=[{"tax": t, "amount": a} for t, a in sorted(by_tax.items(), key=lambda kv: -kv[1])])
    return out


def _liabilities(ctx: TaxContext, tabs: Dict[str, Any], obls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    horizon = ctx.today + timedelta(days=30)
    amounts: Dict[str, Tuple[str, float]] = {}
    for o in obls:
        if o["status"] in ("paid", "paid_late") or o["due"] > horizon or not o["unpaid"]:
            continue
        scale = (o["unpaid"] / o["liability"]) if o["liability"] else 1
        for label, kind, amount in o["parts"] or [(o["label"], o["tax_key"], o["liability"])]:
            if amount:
                lab = TAX_LABELS.get(kind, label)
                amounts[kind] = (lab, amounts.get(kind, (lab, 0))[1] + amount * scale)
    wht = sum(r.get("withheld") or 0 for r in (tabs.get("wht") or {}).get("unremitted") or [])
    if wht:
        amounts["wht"] = (TAX_LABELS["wht"], wht)
    rows = [{"tax": k, "label": lab, "amount": round(a, 2)} for k, (lab, a) in amounts.items()]
    return sorted(rows, key=lambda r: -r["amount"])


def _monthly(ctx: TaxContext, tabs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Due per month from the payroll and VAT tabs; paid = settlement debits in the month after."""
    months = month_starts(rules.month_end(rules.add_months(ctx.today.replace(day=1), -1)), 12)
    payroll = {m["month"]: m for m in (tabs.get("payroll") or {}).get("monthly") or []}
    vat = {m["month"]: m for m in (tabs.get("vat") or {}).get("monthly") or []}
    accounts = sorted({a for k in (*PAYROLL_KINDS, "vat_output") for a in tax_accounts(ctx, k)})
    pay = _payments(ctx, accounts, rules.add_months(months[0], 1))
    out = []
    for m in months:
        key = month_key(m)
        p, v = payroll.get(key), vat.get(key)
        parts = ([(p.get("paye") or 0) + (p.get("other") or 0)] if p else []) + ([max(v.get("net") or 0, 0)] if v and v.get("net") is not None else [])
        nxt = rules.add_months(m, 1)
        paid = None
        if accounts and nxt <= ctx.today:
            end = rules.month_end(nxt)
            paid = round(sum(a for d, a in pay if nxt <= d <= end), 2)
        out.append({"month": key, "due": round(sum(parts), 2) if parts else None, "paid": paid})
    return out


def _on_time_12m(ctx: TaxContext, tabs: Dict[str, Any]):
    """(on_time, total) monthly remittances over the last 12 closed months, settled against the books."""
    hol = holidays(ctx)
    months = month_starts(rules.month_end(rules.add_months(ctx.today.replace(day=1), -1)), 12)
    first, last = months[0], rules.month_end(months[-1])
    vat = {m["month"]: m.get("net") for m in (tabs.get("vat") or {}).get("monthly") or []}
    streams = []  # (accounts, {month_key: liability}, due kind)
    for kind in PAYROLL_KINDS:
        accounts = tax_accounts(ctx, kind)
        if not accounts:
            continue
        rows = frappe.db.sql(
            """SELECT posting_date, SUM(credit) FROM `tabGL Entry`
               WHERE company = %s AND is_cancelled = 0 AND account IN %s AND posting_date BETWEEN %s AND %s
               GROUP BY posting_date""",
            (ctx.company, tuple(accounts), first, last),
        )
        by_month: Dict[str, float] = {}
        for d, a in rows:
            by_month[month_key(as_date(d))] = by_month.get(month_key(as_date(d)), 0) + float(a or 0)
        streams.append((accounts, by_month, kind))
    if (tabs.get("vat") or {}).get("available") and tax_accounts(ctx, "vat_output"):
        streams.append((tax_accounts(ctx, "vat_output"), {k: v for k, v in vat.items() if v}, "vat"))
    on_time = total = 0
    for accounts, by_month, kind in streams:
        liabs = []
        for m in months:
            amount, pe = by_month.get(month_key(m)), rules.month_end(m)
            due = rules.monthly_due_dates(pe, hol)[kind]
            if amount and amount > 0 and due <= ctx.today:
                liabs.append((month_key(m), pe, amount, due))
        res = _settle(_payments(ctx, accounts, first), liabs, ctx.today)
        total += len(res)
        on_time += sum(1 for r in res.values() if r["status"] == "paid")
    return on_time, total


def _filing_status(ctx: TaxContext, tabs: Dict[str, Any], obls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [(o["due"], {"obligation": o["label"], "period": o["period_end"].strftime("%b %Y") if o["period_end"] else o["label"],
                        "due": o["due"].isoformat(), "chip": o["chip"]})
            for o in obls if o["due"] <= ctx.today and o["tax_key"] != "cit"]
    past = [o for o in obls if o["tax_key"] == "cit" and o["due"] <= ctx.today]
    if past:  # most recent instalment only
        o = max(past, key=lambda x: x["due"])
        rows.append((o["due"], {"obligation": o["label"], "period": f"FY {ctx.fy_name}", "due": o["due"].isoformat(), "chip": o["chip"]}))
    wht = tabs.get("wht") or {}
    if wht.get("available"):
        late = _wht_overdue(tabs)
        rows.append((ctx.today, {"obligation": _("WHT (5 working days)"), "period": ctx.period_name, "due": None,
                                 "chip": chip("neg", _("{0} payments late").format(len(late))) if late else chip("pos", _("No late payments"))}))
    return [r for _d, r in sorted(rows, key=lambda x: x[0], reverse=True)]


def _src(tabs: Dict[str, Any], tab: str, key: str) -> Dict[str, Any]:
    return next((k for k in (tabs.get(tab) or {}).get("kpis") or [] if k.get("key") == key), {})


def compute(ctx: TaxContext, tabs: Dict[str, Any]) -> Dict[str, Any]:
    obls = _obligations(ctx, tabs)
    deadlines = _deadlines(ctx, tabs, obls)
    have_amounts = any((tabs.get(k) or {}).get("available") for k in ("payroll", "vat", "income", "customs"))
    due_30 = sum(d["amount"] or 0 for d in deadlines) if have_amounts else None
    over_principal, over_penalty, over_n = _overdue(ctx, tabs, obls)
    can_judge = any(o["status"] for o in obls) or bool((tabs.get("wht") or {}).get("available"))
    on_time, total = _on_time_12m(ctx, tabs)
    etims, risk = _src(tabs, "etims", "purchase_cu_coverage_pct"), _src(tabs, "vat", "input_vat_at_risk")
    late = total - on_time
    return {
        "available": True,
        "kpis": [
            kpi("due_30d", _("Due in next 30 days"), due_30, "money",
                _("{0} obligations · first {1}").format(len(deadlines), as_date(deadlines[0]["date"]).strftime("%d %b")) if deadlines else _("Nothing due"),
                "neutral"),
            kpi("overdue_principal", _("Overdue principal"), over_principal if can_judge else None, "money",
                _("{0} past-due unpaid items").format(over_n) if can_judge else _("No payment evidence available"),
                "bad" if over_principal else "neutral"),
            kpi("penalty_exposure", _("Penalty & interest exposure"), over_penalty if can_judge else None, "money",
                _("5% late-payment penalty + 1% a month interest to date"), "warn" if over_penalty else "neutral"),
            kpi("etims_purchase_coverage", _("eTIMS purchase coverage"), etims.get("value"), "pct",
                etims.get("sub") or (tabs.get("etims") or {}).get("message", ""), etims.get("tone", "neutral")),
            kpi("input_vat_at_risk", _("Input VAT at risk"), risk.get("value"), "money",
                risk.get("sub") or (tabs.get("vat") or {}).get("message", ""), risk.get("tone", "neutral")),
            kpi("paid_on_time_12m", _("Paid on time, 12 months"), pct(on_time, total), "pct",
                _("{0} of {1} obligations · {2} late").format(on_time, total, late) if total else _("No tax account postings found"),
                "neutral"),
        ],
        "deadlines": deadlines,
        "amnesty": _amnesty(ctx, tabs, obls),
        "liabilities": _liabilities(ctx, tabs, obls),
        "monthly": _monthly(ctx, tabs),
        "filing_status": _filing_status(ctx, tabs, obls),
    }
