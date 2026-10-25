"""Tab briefs for the Manufacturing dashboard (Rule 7: server-built sentences).

OEE, Capacity, Forecast and Recommendations each get their own brief. While no
Work Order exists every sentence names the missing prerequisite using the
payload's own notes; once Work Orders exist the sentences quote the measured
figures instead.
"""

from . import action, brief, detail, plural


def _sentence(note) -> str:
    note = (note or "").strip()
    return note if not note or note.endswith(".") else note + "."


def _empty(p: dict) -> bool:
    return (p.get("production_metrics") or {}).get("total_work_orders") == 0


def _mrs(p: dict):
    return (p.get("production_metrics") or {}).get("pending_material_requests")


def _mr_action(p: dict):
    n = _mrs(p)
    return [action("Clear pending material requests", f"{plural(n, 'material request')} pending.")] if n else []


def _oee(p: dict):
    o = p.get("oee_analysis") or {}
    if _empty(p):
        text = f"OEE is unmeasurable: {plural(0, 'Work Order')} recorded. {_sentence(o.get('message'))}"
        q = (p.get("quality_metrics") or {}).get("quality_data_note")
        if q:
            text += f" {_sentence(q)}"
        mrs = _mrs(p)
        if mrs:
            text += f" {plural(mrs, 'material request')} pending."
        details = [detail(k, _sentence(v)) for k, v in (("OEE", o.get("message")), ("Quality", q)) if v]
        return brief(
            "medium",
            text.strip(),
            details,
            [action("Record Work Orders", "Availability, performance and quality all start from Work Orders; none exist for this period."), *_mr_action(p)],
        )
    score = o.get("oee_score_pct")
    if score is None:
        return None
    parts = [f"OEE is {score}%"]
    for label, key in (("availability", "availability_pct"), ("performance", "performance_pct"), ("quality", "quality_pct")):
        if o.get(key) is not None:
            parts.append(f"{label} {o[key]}%")
    sev = "low" if score >= 85 else "medium" if score >= 60 else "high"
    return brief(sev, ", ".join(parts) + ".", [], [])


def _capacity(p: dict):
    c = p.get("capacity_utilization") or {}
    b = p.get("bottleneck_analysis") or {}
    if _empty(p):
        text = f"Capacity is unmeasurable: {plural(0, 'Work Order')} recorded. {_sentence(c.get('message'))}"
        if b.get("message"):
            text += f" {_sentence(b['message'])}"
        details = [detail(k, _sentence(v)) for k, v in (("Capacity", c.get("message")), ("Bottlenecks", b.get("message"))) if v]
        return brief(
            "medium",
            text.strip(),
            details,
            [action("Configure workstation working hours", "Utilization needs available hours as well as worked hours; the payload reports no workstation capacity.")],
        )
    util = c.get("overall_utilization_pct")
    if util is None:
        return None
    n = b.get("bottleneck_count")
    text = f"Overall utilization is {util}%"
    if n is not None:
        text += f" with {plural(n, 'bottleneck')}"
    sev = "high" if (n or 0) > 0 else "medium" if util >= 90 else "low"
    return brief(sev, text + ".", [], [])


def _forecast(p: dict):
    f = p.get("production_forecast") or {}
    if _empty(p):
        return brief(
            "medium",
            f"No production forecast: {plural(0, 'Work Order')} recorded. {_sentence(f.get('message'))}",
            [],
            [action("Record Work Orders", "The forecast extrapolates monthly production history; none exists yet.")],
        )
    pm = p.get("production_metrics") or {}
    if pm.get("total_production_qty") is None:
        return None
    text = f"{pm['total_production_qty']:,} units produced"
    if pm.get("monthly_growth_rate") is not None:
        text += f", monthly growth {pm['monthly_growth_rate']}%"
    return brief("low", text + ".", [], [])


def _recommendations(p: dict):
    recs = p.get("recommendations")
    if recs is None:
        return None
    if not recs:
        text = "The recommendations engine has nothing to evaluate: zero alerts is not an all clear."
        if _empty(p):
            text = f"{plural(0, 'Work Order')} recorded, so the engine has no production signals; zero alerts is not an all clear."
        mrs = _mrs(p)
        if mrs:
            text += f" {plural(mrs, 'material request')} pending."
        return brief("medium" if _empty(p) else "low", text, [], _mr_action(p))
    high = [r for r in recs if r.get("priority") in ("critical", "high")]
    text = f"{plural(len(recs), 'recommendation')}, {len(high)} high priority."
    return brief("high" if high else "medium", text, [detail(r.get("title") or "Recommendation", r.get("description") or "") for r in recs[:3]], [])


def briefs(p: dict) -> dict:
    out = {"oee": _oee(p), "capacity": _capacity(p), "forecast": _forecast(p), "recommendations": _recommendations(p)}
    return {k: v for k, v in out.items() if v}
