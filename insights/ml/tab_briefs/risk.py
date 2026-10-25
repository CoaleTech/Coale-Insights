"""Tab briefs for the Risk dashboard (Rule 7: server-built sentences).

Severity comes from the server's own risk categories (``overview.risk_components``)
and the payload's per-fact categories; nothing is re-scored here.
"""

from datetime import datetime

from . import action, brief, detail, money, plural

_ORDER = ["none", "low", "medium", "high", "critical"]
TOP_N = 3


def _sev(*cats) -> str:
    """Highest of the given category strings; unknown strings count as none."""
    known = [c.lower() for c in cats if isinstance(c, str) and c.lower() in _ORDER]
    return max(known, key=_ORDER.index, default="none")


def _component(p: dict, key: str):
    return (((p.get("overview") or {}).get("risk_components") or {}).get(key) or {}).get("category")


def _month(period: str) -> str:
    return datetime.strptime(period, "%Y-%m").strftime("%b %Y")


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _names(rows: list, key: str, name_key: str, cur, amount_key: str = "outstanding") -> str:
    return ", ".join(f"{r.get(name_key) or r.get(key)} ({money(r.get(amount_key), cur)})" for r in rows) + "."


def _credit(p: dict):
    c = p.get("credit_risk") or {}
    aging = c.get("aging_analysis") or []
    total = _f(c.get("total_outstanding"))
    if not aging or not total:
        return None
    cur = p.get("base_currency")
    past_buckets = [b for b in aging if b.get("aging_bucket") != "Current"]
    past = sum(_f(b.get("outstanding_amount")) for b in past_buckets)
    avg = c.get("avg_days_overdue")
    by_days = None if avg is None else "low" if avg <= 30 else "medium" if avg <= 60 else "high"
    text = f"{round(past * 100 / total)}% of receivables ({money(past, cur)} of {money(total, cur)}) is past payment terms"
    if c.get("high_risk_customers") is not None:
        text += f"; {plural(c['high_risk_customers'], 'customer')} rated high risk"
    text += "."

    details, actions = [], []
    big = max(past_buckets, key=lambda b: _f(b.get("outstanding_amount")), default=None)
    if big:
        details.append(detail(
            "Largest past-due bucket",
            f"{big['aging_bucket']} holds {money(big['outstanding_amount'], cur)} across {plural(big.get('invoice_count') or 0, 'invoice')}.",
        ))
    scored = sorted(c.get("customer_risk_scores") or [], key=lambda r: -_f(r.get("outstanding")))
    if avg is not None:
        details.append(detail("Collection speed", f"Open receivables average {avg:g} days overdue."))
    if scored:
        top = scored[:TOP_N]
        details.append(detail(f"Largest balances among {len(scored)} scored customers", _names(top, "customer", "customer_name", cur)))
        actions.append(action(
            "Review credit terms for the largest balances",
            _names(top, "customer", "customer_name", cur),
            impact=money(sum(_f(r.get("outstanding")) for r in top), cur),
        ))
    if big:
        actions.append(action(
            f"Run a collection sprint on {big['aging_bucket']}",
            f"{plural(big.get('invoice_count') or 0, 'invoice')} sit in this bucket.",
            impact=money(big["outstanding_amount"], cur),
        ))
    return brief(_sev(_component(p, "credit_risk"), by_days), text, details, actions)


def _payables(p: dict):
    ap = p.get("payables_risk") or {}
    aging = ap.get("aging_analysis") or []
    total = _f(ap.get("total_outstanding"))
    if not aging or not total:
        return None
    cur = p.get("base_currency")
    past_buckets = [b for b in aging if b.get("aging_bucket") != "Current"]
    past = sum(_f(b.get("outstanding_amount")) for b in past_buckets)
    avg = ap.get("avg_days_overdue")
    by_days = None if avg is None else "low" if avg <= 30 else "medium" if avg <= 60 else "high"
    text = f"{money(total, cur)} is owed to suppliers, {round(past * 100 / total)}% of it ({money(past, cur)}) past terms"
    if ap.get("high_risk_suppliers") is not None:
        text += f"; {plural(ap['high_risk_suppliers'], 'supplier')} rated high risk"
    text += "."
    details, actions = [], []
    if avg is not None:
        details.append(detail("Payment speed", f"Open bills average {avg:g} days overdue."))
    big = max(past_buckets, key=lambda b: _f(b.get("outstanding_amount")), default=None)
    if big:
        details.append(detail(
            "Largest past-due bucket",
            f"{big['aging_bucket']} holds {money(big['outstanding_amount'], cur)} across {plural(big.get('invoice_count') or 0, 'bill')}.",
        ))
    owed = sorted(ap.get("supplier_risk_scores") or [], key=lambda r: -_f(r.get("outstanding")))[:TOP_N]
    if owed:
        details.append(detail("Largest supplier balances", _names(owed, "supplier", "supplier_name", cur)))
        actions.append(action(
            "Agree payment plans with the largest supplier balances",
            _names(owed, "supplier", "supplier_name", cur),
            impact=money(sum(_f(r.get("outstanding")) for r in owed), cur),
        ))
    return brief(_sev(by_days, *[r.get("risk_category") for r in owed]), text, details, actions)


def _cashflow(p: dict):
    c = p.get("cashflow_risk") or {}
    cash = c.get("current_cash_position")
    if cash is None:
        return None
    cur = p.get("base_currency")
    trend = [r for r in c.get("overdue_days_trend") or [] if r.get("avg_days_overdue") is not None]
    text = f"Cash position is {money(cash, cur)}."
    if len(trend) > 1:
        first, last = trend[0], trend[-1]
        text += f" Average overdue days went from {first['avg_days_overdue']:g} in {_month(first['period'])} to {last['avg_days_overdue']:g} in {_month(last['period'])}."
    if c.get("top_customer_share") is not None:
        text += f" The top customer is {c['top_customer_share']:g}% of revenue."

    details, actions = [], []
    if c.get("current_working_capital") is not None and c.get("working_capital_ratio") is not None:
        details.append(detail("Working capital", f"{money(c['current_working_capital'], cur)} at a ratio of {c['working_capital_ratio']:g}×."))
    exp = [e for e in c.get("exposure_trend") or [] if e.get("receivables") is not None and e.get("payables") is not None]
    if exp:
        e = exp[-1]
        details.append(detail("Exposure", f"In {_month(e['period'])} receivables were {money(e['receivables'], cur)} against payables of {money(e['payables'], cur)}."))
    conc = (c.get("customer_concentration") or [])[:TOP_N]
    if conc:
        share = sum(_f(r.get("revenue_share")) for r in conc)
        details.append(detail(f"Top {len(conc)} customers", f"{', '.join(r['customer_name'] for r in conc)} together are {share:.1f}% of revenue."))
        actions.append(action(
            "Watch the largest customer relationships",
            f"The top {len(conc)} customers are {share:.1f}% of revenue.",
        ))
    aging = [b for b in (p.get("credit_risk") or {}).get("aging_analysis") or [] if b.get("aging_bucket") != "Current"]
    if aging and cash < 0:
        big = max(aging, key=lambda b: _f(b.get("outstanding_amount")))
        actions.insert(0, action(
            f"Collect the {big['aging_bucket']} bucket",
            "Cash is negative; this is the largest past-due receivable bucket.",
            impact=money(big["outstanding_amount"], cur),
        ))
    return brief(_sev(_component(p, "cashflow_risk")), text, details, actions)


def _operational(p: dict):
    o = p.get("operational_risk") or {}
    top = o.get("top_inventory_risk") or {}
    if top.get("stockout_risk_score") is None:
        return None
    cur = p.get("base_currency")
    items, total = top.get("stockout_items", 0), top.get("total_items", 0)
    text = f"{top['stockout_risk_score']:g}% of stock items are in stockout ({items:,} of {total:,})."
    sup = [s for s in o.get("supplier_performance") or [] if s.get("avg_delay_days") is not None]
    late = [s for s in sup if s["avg_delay_days"] > 0]
    if sup:
        text += f" All {len(sup)} tracked suppliers deliver early on average." if not late else f" {len(late)} of {len(sup)} tracked suppliers deliver late on average."

    details, actions = [], []
    if top.get("stock_value") is not None:
        details.append(detail("Stock position", f"The {total - items:,} items with stock are worth {money(top['stock_value'], cur)}."))
    if sup:
        worst = max(sup, key=lambda s: s["avg_delay_days"])
        details.append(detail("Supplier timing", f"{worst['supplier_name']} has the latest average delivery, {worst['avg_delay_days']:g} days against the due date (negative is early)."))
    err = (o.get("process_risks") or {}).get("invoice_error_rate")
    if err is not None:
        details.append(detail("Invoice error rate", f"{err:.2f}%."))
    groups = sorted(o.get("inventory_risks") or [], key=lambda g: -(g.get("stockout_items") or 0))[:TOP_N]
    if groups:
        actions.append(action(
            "Review reorder levels for the item groups in stockout",
            "; ".join(f"{g['item_group']} ({g['stockout_items']:,} of {g['total_items']:,} items)" for g in groups) + ".",
            impact=money(top.get("stock_value"), cur) if top.get("stock_value") is not None else None,
        ))
    if late:
        actions.append(action("Follow up late suppliers", f"{plural(len(late), 'supplier')} deliver after the due date on average."))
    return brief(_sev(_component(p, "operational_risk"), top.get("risk_category")), text, details, actions)


def _period(raw: str) -> str:
    try:
        return datetime.strptime(str(raw).zfill(6), "%m%Y").strftime("%b %Y")
    except ValueError:
        return ""


def _compliance(p: dict):
    c = p.get("compliance_risk") or {}
    g = c.get("gst_status") or {}
    if not g:
        return None
    cur = p.get("base_currency")
    late = [
        (name, str(g.get(f"{key}_latest_period") or ""))
        for name, key in (("GSTR-1", "gstr1"), ("GSTR-3B", "gstr3b"))
        if g.get(f"{key}_status") in ("Overdue", "Pending")
    ]
    if late:
        periods = {pd for _, pd in late}
        when = f" for {_period(next(iter(periods)))}" if len(periods) == 1 and _period(next(iter(periods))) else ""
        text = f"{' and '.join(n for n, _ in late)}{when} {'is' if len(late) == 1 else 'are'} overdue."
    else:
        text = "GST filings are up to date."
    if g.get("einvoice_coverage_pct") is not None:
        text += f" e-Invoice coverage is {g['einvoice_coverage_pct']:g}%."
    docs = c.get("document_audit") or []
    total = sum(d.get("total_docs") or 0 for d in docs)
    bad = sum(d.get("incomplete_docs") or 0 for d in docs)
    if total:
        text += f" {total - bad:,} of {total:,} documents are complete."

    details = [detail(d["document_type"], f"{d['total_docs']:,} documents, {d.get('incomplete_docs') or 0:,} incomplete.") for d in docs if d.get("total_docs")]
    if g.get("einvoice_pending_value") is not None:
        details.append(detail("e-Invoice", f"{money(g['einvoice_pending_value'], cur)} pending."))
    lic = c.get("licenses") or []
    if lic:
        details.append(detail("Licences", "; ".join(f"{x['license_type']} {x['status']}" for x in lic) + "."))
    actions = [action(f"File {name}" + (f" for {_period(pd)}" if _period(pd) else ""), "Its status is overdue.") for name, pd in late]
    return brief(_sev(_component(p, "compliance_risk"), "high" if late else None), text, details, actions)


def _predictive(p: dict):
    a = p.get("predictive_analytics") or {}
    fc = (a.get("cash_flow_forecast") or {}).get("forecast") or []
    if not fc:
        return None
    cur = p.get("base_currency")
    last = fc[-1]
    d = datetime.strptime(last["ds"], "%Y-%m-%d")
    risky = (a.get("payment_risk_forecast") or {}).get("high_risk_customers") or []
    text = (
        f"{len(fc)}-day cash forecast: {money(last['yhat'], cur)} on {d.day} {d:%b %Y}. "
        f"{plural(len(risky), 'customer')} flagged for payment delay risk."
    )
    warnings = a.get("early_warnings") or []
    sev = _sev(*[w.get("severity") for w in warnings], "medium" if risky else None)

    details, actions = [], []
    perf = (a.get("cash_flow_forecast") or {}).get("model_performance") or {}
    if perf.get("method"):
        details.append(detail("Forecast model", f"{perf['method']} over {len(fc)} days" + (f", trend {perf['trend']}." if perf.get("trend") else ".")))
    for w in warnings:
        details.append(detail(w.get("title") or "Warning", f"{w.get('description')} ({w.get('timeframe')})."))
        actions.append(action(w.get("title") or "Act on the warning", f"{w.get('description')} ({w.get('timeframe')}).", impact=money(abs(w["amount"]), cur) if w.get("amount") is not None else None))
    if risky:
        names = {r["customer"]: r.get("customer_name") for r in (p.get("credit_risk") or {}).get("customer_risk_scores") or []}
        top = sorted(risky, key=lambda r: -_f(r.get("avg_delay_days")))[:TOP_N]
        line = ", ".join(f"{names.get(r['customer']) or r['customer']} ({r['avg_delay_days']:g} days)" for r in top) + "."
        details.append(detail("Longest forecast payment delays", line))
        actions.append(action("Follow up the customers forecast to pay latest", line))
    return brief(sev, text, details, actions)


def _ledger(p: dict):
    a = p.get("predictive_analytics")
    if a is None:
        return None
    rows = a.get("anomalies") or []
    if not rows:
        return brief("none", "The model detected no ledger anomalies. The full ledger scan runs on request from this tab.")
    text = f"{plural(len(rows), 'ledger anomaly', 'ledger anomalies')} detected by the model."
    top = sorted(rows, key=lambda r: -_ORDER.index(_sev(r.get("severity"))))[:TOP_N]
    details = [detail(str(r.get("type") or "anomaly").replace("_", " ").capitalize(), f"{r.get('description')}.") for r in top]
    return brief(_sev(*[r.get("severity") for r in rows]), text, details, [action("Run the ledger scan", "The scan checks submitted invoices on request and is not part of the cached figures.")])


def briefs(p: dict) -> dict:
    out = {
        "credit": _credit(p),
        "payables": _payables(p),
        "cashflow": _cashflow(p),
        "operational": _operational(p),
        "compliance": _compliance(p),
        "predictive": _predictive(p),
        "ledger": _ledger(p),
    }
    return {k: v for k, v in out.items() if v}
