"""Tab briefs for the Procurement dashboard (Rule 7: server-built sentences).

Severity cut-points mirror the ones ProcurementIntelligence.vue already uses
(RATE_THRESHOLDS 90/70, RISK_THRESHOLDS 30/60, days_pending 7/14).
"""

from datetime import datetime

from . import _SYMBOLS, action, brief, detail, money, plural

RATE_GOOD, RATE_WARN = 90, 70
RISK_GOOD, RISK_WARN = 30, 60
STALE_PO_DAYS = 14


def _rate(v, cur) -> str:
    """Unit rates are small numbers: keep two decimals (``money`` rounds to whole units)."""
    return f"{_SYMBOLS.get(cur or '', f'{cur} ' if cur else '')}{v:,.2f}"


def _band(v, good, warn, higher_is_better=True) -> str:
    if not higher_is_better:
        return "low" if v <= good else "medium" if v <= warn else "high"
    return "low" if v >= good else "medium" if v >= warn else "high"


def _suppliers(p: dict):
    sp = p.get("supplier_performance") or {}
    rate = sp.get("avg_on_time_rate")
    if rate is None:
        return None
    cur = p.get("base_currency")
    text = f"Average on-time rate is {rate}%"
    if sp.get("quality_status") == "success" and sp.get("avg_quality_rate") is not None:
        text += f", quality {sp['avg_quality_rate']}%"
    if sp.get("avg_lead_time") is not None:
        text += f", average lead time {sp['avg_lead_time']} days"
    text += "."
    rows = sp.get("all_suppliers") or []
    details, actions = [], []
    if rows and len(rows) == sp.get("total_suppliers"):  # complete list only
        zero = [s for s in rows if s.get("on_time_rate") == 0]
        perfect = [s for s in rows if s.get("on_time_rate") == 100]
        if zero:
            spend = sum(s.get("total_value") or 0 for s in zero)
            text += f" {plural(len(zero), 'supplier')} at 0% on-time account for {money(spend, cur)} of spend."
            actions.append(action(
                "Review suppliers with 0% on-time delivery",
                f"{plural(len(zero), 'supplier')} delivered none of their orders on time. The largest by value is "
                f"{max(zero, key=lambda s: s.get('total_value') or 0).get('supplier_name')}.",
                impact=money(spend, cur),
            ))
        details.append(detail("Spread", f"{len(perfect)} of {len(rows)} suppliers are at 100% on-time and {len(zero)} at 0%."))
    worst = (sp.get("bottom_performers") or [None])[0]
    if worst:
        details.append(detail(
            "Lowest score",
            f"{worst.get('supplier_name')} scores {worst.get('overall_score')}/100: on-time {worst.get('on_time_rate')}%, "
            f"lead time {worst.get('avg_lead_time')} days on {money(worst.get('total_value'), cur)} of orders.",
        ))
    return brief(_band(rate, RATE_GOOD, RATE_WARN), text, details, actions)


def _analytics(p: dict):
    pa = p.get("purchase_analytics") or {}
    n = pa.get("pending_count")
    if n is None:
        return None
    cur = p.get("base_currency")
    text = f"{plural(n, 'purchase order')} pending, worth {money(pa.get('pending_value'), cur)}"
    days = [r["days_pending"] for r in pa.get("pending_pos") or [] if r.get("days_pending") is not None]
    if days:  # the backend lists the oldest first, so the max is the true oldest
        text += f", the oldest {plural(int(max(days)), 'day')}"
    text += "."
    cycle = [
        f"{label} {pa[k]} days"
        for label, k in (("PO to GRN", "avg_po_to_grn_days"), ("GRN to invoice", "avg_grn_to_invoice_days"))
        if pa.get(k) is not None
    ]
    if cycle:
        text += f" {' and '.join(cycle)} on average."
    details = []
    if pa.get("overdue_po_count") is not None and pa.get("total_po_count"):
        details.append(detail("Overdue", f"{pa['overdue_po_count']:,} of {pa['total_po_count']:,} purchase orders are overdue."))
    status = pa.get("po_status_summary") or []
    if status:
        details.append(detail("By status", "; ".join(f"{r['status']}: {int(r['count']):,} ({money(r.get('value'), cur)})" for r in status) + "."))
    actions = []
    if n and days:
        actions.append(action(
            "Chase or close the oldest pending orders",
            f"{plural(n, 'order')} pending, the oldest {plural(int(max(days)), 'day')}.",
            impact=money(pa.get("pending_value"), cur),
        ))
    return brief("high" if days and max(days) > STALE_PO_DAYS else "medium" if n else "low", text, details, actions)


def _pricing(p: dict):
    pi = p.get("price_intelligence") or {}
    n, up = pi.get("items_analyzed"), pi.get("price_increases_count")
    if not n or up is None:
        return None
    cur = p.get("base_currency")
    text = f"{up} of {plural(n, 'item')} analyzed ({up * 100 / n:.0f}%) are bought above their own average rate."
    if pi.get("total_potential_savings"):
        text += f" Identified savings: {money(pi['total_potential_savings'], cur)}."
    details, actions = [], []
    top = max(pi.get("price_increases") or [], key=lambda i: i.get("price_variance_pct") or 0, default=None)
    if top:
        details.append(detail(
            "Largest increase",
            f"{top['item_name']} was last bought at {_rate(top['last_rate'], cur)} against an average of {_rate(top['avg_rate'], cur)} "
            f"({top['price_variance_pct']}% above) over {plural(top['purchase_count'], 'purchase')}.",
        ))
    if pi.get("total_potential_savings"):
        details.append(detail("Savings", f"Potential savings on the analyzed items total {money(pi['total_potential_savings'], cur)}."))
        actions.append(action(
            "Renegotiate items bought above their average rate",
            f"{up} items were last bought above their own average rate.",
            impact=money(pi["total_potential_savings"], cur),
        ))
    return brief("medium" if up else "low", text, details, actions)


def _risks(p: dict):
    ra = p.get("risk_analysis") or {}
    score = ra.get("risk_score")
    if score is None:
        return None
    cur = p.get("base_currency")
    sev = _band(score, RISK_GOOD, RISK_WARN, higher_is_better=False)
    text = f"Procurement risk is {sev.capitalize()} at {score}/100."
    conc = [c["concentration_pct"] for c in ra.get("supplier_concentration") or [] if c.get("concentration_pct") is not None]
    if conc:
        text += f" The largest supplier is {max(conc)}% of period spend."
    if ra.get("single_source_count"):
        text += f" {plural(ra['single_source_count'], 'item')} {'has' if ra['single_source_count'] == 1 else 'have'} a single supplier, {money(ra.get('single_source_value'), cur)} of spend."
    comp = ra.get("risk_components") or {}
    details = []
    if comp:
        details.append(detail("Score components", ", ".join(f"{k.replace('_', ' ')} {v:g}" for k, v in comp.items()) + " points."))
    exposure = (ra.get("payment_exposure") or [None])[0]
    if exposure:
        details.append(detail("Payment exposure", f"{exposure.get('supplier_name')} has the largest outstanding balance, {money(exposure.get('outstanding'), cur)}."))
    actions = []
    if ra.get("single_source_count"):
        actions.append(action(
            "Qualify a second supplier for single-source items",
            f"{plural(ra['single_source_count'], 'item')} {'has' if ra['single_source_count'] == 1 else 'have'} one supplier.",
            impact=money(ra.get("single_source_value"), cur),
        ))
    return brief(sev, text, details, actions)


def _month(period: str) -> str:
    return datetime.strptime(period, "%Y-%m").strftime("%b %Y")


def _forecasts(p: dict):
    f = p.get("forecasts") or {}
    nxt = (f.get("forecasts") or [])[:3]
    if not nxt:
        return None
    cur = p.get("base_currency")
    direction, amt = f.get("trend_direction"), f.get("trend_amount")
    text = ""
    if direction in ("up", "down") and amt is not None:
        text += f"Spend is trending {direction} by {money(amt, cur)} a month. "
    text += (
        f"The next {len(nxt)} months forecast {money(sum(r['predicted_spend'] for r in nxt), cur)}: "
        + ", ".join(f"{_month(r['period'])} {money(r['predicted_spend'], cur)}" for r in nxt)
        + "."
    )
    details = []
    if f.get("avg_monthly_spend") is not None:
        details.append(detail("Historical average", f"Spend averaged {money(f['avg_monthly_spend'], cur)} a month over the last 6 complete months."))
    cats = f.get("category_forecast") or []
    if cats:
        c = max(cats, key=lambda r: r.get("forecast_3m") or 0)
        details.append(detail("Largest category", f"{c['category']} is forecast at {money(c['forecast_3m'], cur)} over three months."))
    actions = []
    if f.get("avg_monthly_spend") is not None:
        total = sum(r["predicted_spend"] for r in nxt)
        actions.append(action(
            "Budget purchasing against the forecast",
            f"The next {len(nxt)} months forecast {money(total, cur)} against {money(f['avg_monthly_spend'] * len(nxt), cur)} at the historical monthly average.",
        ))
    return brief("medium" if direction == "up" else "low", text, details, actions)


def briefs(p: dict) -> dict:
    out = {
        "suppliers": _suppliers(p),
        "analytics": _analytics(p),
        "pricing": _pricing(p),
        "risks": _risks(p),
        "forecasts": _forecasts(p),
    }
    return {k: v for k, v in out.items() if v}
