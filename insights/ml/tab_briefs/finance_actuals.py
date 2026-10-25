"""Tab briefs for the Financial dashboard's actuals tabs (Rule 7: server-built sentences)."""

import calendar

from . import action, brief, detail, money, plural

LOOKBACK_MONTHS = 6
DUE_SOON_DAYS = 7
DSO_GOOD, DSO_WARN = 30, 60  # same cut-points as the Overview DSO badge in the Vue


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _month(period: str) -> str:
    y, m = period.split("-")
    return f"{calendar.month_abbr[int(m)]} {y}"


def _cashflow(p: dict):
    c = p.get("cash_flow") or {}
    cur = p.get("base_currency")
    if c.get("liquid_cash") is None:
        return None
    liquid = _f(c["liquid_cash"])
    text = f"Liquid cash is {money(liquid, cur)}"
    if c.get("fd_balance"):
        text += f" with {money(c['fd_balance'], cur)} held in fixed deposits"
    done = [m for m in c.get("monthly_cash_movement") or [] if m["period"] < (c.get("as_of") or "9999")[:7]]
    recent = done[-LOOKBACK_MONTHS:]
    if recent:
        neg = [m for m in recent if _f(m["net"]) < 0]
        text += f". Net cash fell in {len(neg)} of the last {plural(len(recent), 'complete month')}"
        if neg:
            worst = min(neg, key=lambda m: m["net"])
            text += f", the largest fall in {_month(worst['period'])} ({money(worst['net'], cur)})"
    sev = "medium" if liquid < 0 else "low"
    details = [detail(
        "Balances",
        f"Bank {money(c.get('bank_balance'), cur)}, cash on hand {money(c.get('cash_on_hand'), cur)}, fixed deposits {money(c.get('fd_balance'), cur)}.",
    )]
    if c.get("avg_monthly_inflow") is not None and c.get("avg_monthly_outflow") is not None:
        net = _f(c["avg_monthly_inflow"]) - _f(c["avg_monthly_outflow"])
        details.append(detail(
            "Average month",
            f"Inflow {money(c['avg_monthly_inflow'], cur)}, outflow {money(c['avg_monthly_outflow'], cur)}, net {money(net, cur)}.",
        ))
    actions = []
    if liquid < 0:
        actions.append(action(
            "Close the liquid cash gap",
            f"Bank and cash on hand are negative while {money(c.get('fd_balance'), cur)} sits in fixed deposits.",
            impact=money(-liquid, cur),
        ))
    return brief(sev, text + ".", details, actions)


def _receivables(p: dict):
    r = p.get("receivables") or {}
    cur = p.get("base_currency")
    total = _f(r.get("total_outstanding"))
    buckets = [b for b in r.get("aging_buckets") or [] if _f(b.get("amount")) > 0]
    if total <= 0 or not buckets:
        return None
    big = max(buckets, key=lambda b: b["amount"])
    text = f"{money(total, cur)} is outstanding across {plural(r.get('invoice_count') or 0, 'invoice')}"
    if r.get("avg_open_receivable_age_days") is not None:
        text += f", open for {_f(r['avg_open_receivable_age_days']):.1f} days on average"
    text += f". The largest bucket, {big['bucket']}, holds {money(big['amount'], cur)} ({_f(big['amount']) * 100 / total:.1f}% of receivables)."
    dso = r.get("current_dso")
    if dso is None:
        sev = "none"
    else:
        sev = "low" if dso <= DSO_GOOD else "medium" if dso <= DSO_WARN else "high"
    details = [detail("Aging", "; ".join(f"{b['bucket']} {money(b['amount'], cur)} ({plural(b.get('count') or 0, 'invoice')})" for b in r.get("aging_buckets") or []) + ".")]
    if dso is not None:
        details.append(detail("Collection speed", f"DSO is {dso:g} days" + (f" and overdue invoices average {r['avg_overdue_days']:g} days late." if r.get("avg_overdue_days") is not None else ".")))
    late = sorted(r.get("overdue_customers") or [], key=lambda c: -_f(c.get("total_outstanding")))
    actions = []
    if late:
        top = late[:3]
        actions.append(action(
            "Collect from the largest overdue customers",
            ", ".join(f"{c['customer_name']} ({money(c['total_outstanding'], cur)}, {plural(c['max_overdue_days'], 'day')} late)" for c in top) + ".",
            impact=money(sum(_f(c["total_outstanding"]) for c in top), cur),
        ))
    return brief(sev, text, details, actions)


def _payables(p: dict):
    pay = p.get("payables") or {}
    cur = p.get("base_currency")
    if pay.get("total_outstanding") is None:
        return None
    soon = [u for u in pay.get("upcoming_payments") or [] if 0 <= _f(u.get("days_until_due")) <= DUE_SOON_DAYS]
    liquid = (p.get("cash_flow") or {}).get("liquid_cash")
    details = []
    if pay.get("current_dpo") is not None:
        details.append(detail("Payment speed", f"DPO is {pay['current_dpo']:g} days; open invoices average {pay.get('avg_open_payable_age_days')} days old."))
    sched = pay.get("payment_schedule") or []
    if sched:
        details.append(detail("Schedule", "; ".join(f"{x['period']} {money(x['amount'], cur)} ({plural(x['count'], 'invoice')})" for x in sched) + "."))
    top = (pay.get("top_suppliers") or [None])[0]
    if top:
        details.append(detail("Largest supplier balance", f"{top['supplier_name']}, {money(top['total_outstanding'], cur)} across {plural(top['invoice_count'], 'invoice')}."))
    actions = []
    overdue = next((x for x in sched if x.get("period") == "Overdue"), None)
    if overdue and overdue.get("amount"):
        actions.append(action("Agree a plan for overdue payables", f"{plural(overdue['count'], 'invoice')} are past their due date.", impact=money(overdue["amount"], cur)))
    if not soon:
        return brief("none", f"{money(pay['total_outstanding'], cur)} is outstanding across {plural(pay.get('invoice_count') or 0, 'invoice')}; none falls due in the next {DUE_SOON_DAYS} days.", details, actions)
    due = sum(_f(u["outstanding_amount"]) for u in soon)
    first = min(soon, key=lambda u: u["days_until_due"])
    text = f"{plural(len(soon), 'invoice')} totalling {money(due, cur)} fall due within {DUE_SOON_DAYS} days, the first being {first['name']} ({money(first['outstanding_amount'], cur)}) on {first['due_date']}"
    actions.insert(0, action(f"Pay or schedule invoices due within {DUE_SOON_DAYS} days", f"{plural(len(soon), 'invoice')} fall due, the first on {first['due_date']}.", impact=money(due, cur)))
    if liquid is None:
        return brief("medium", text + ".", details, actions)
    sev = "high" if due > _f(liquid) else "medium"
    return brief(sev, text + f", against liquid cash of {money(liquid, cur)}.", details, actions)


def _forex(p: dict):
    fx = p.get("forex")
    if fx is None:
        return None
    cur = p.get("base_currency")
    trend = fx.get("realized_forex_trend") or []
    realised = sum(_f(r.get("forex_gain")) - _f(r.get("forex_loss")) for r in trend)
    tail = f" Realised forex nets {money(realised, cur)} across {plural(len(trend), 'month')} with entries." if trend else ""
    rows = fx.get("exposure_summary") or []
    if not rows:
        return brief(
            "none",
            f"No foreign currency exposure: no open invoice is outside {cur}.{tail}",
            [],
            [],
        )
    net = _f(fx.get("net_exposure_base"))
    risky = fx.get("at_risk_invoices") or []
    text = f"Net foreign currency exposure is {money(net, cur)} across {plural(len(rows), 'currency', 'currencies')}."
    actions = []
    if risky:
        text += f" {plural(len(risky), 'foreign currency invoice')} at risk."
        actions.append(action("Review at-risk foreign currency invoices", f"{plural(len(risky), 'invoice')} flagged in the payload."))
    return brief("medium" if risky else "low", text + tail, [], actions)


def briefs(p: dict) -> dict:
    out = {}
    for tab, fn in (("cashflow", _cashflow), ("receivables", _receivables), ("payables", _payables), ("forex", _forex)):
        b = fn(p)
        if b:
            out[tab] = b
    return out
