"""Tab briefs for the Marketing dashboard (Rule 7: server-built sentences).

Every figure is a payload field or arithmetic on payload fields. The Funnel tab
keeps the alerts the payload already carries.
"""

from datetime import datetime

from . import action, brief, detail, money, plural

MIN_TERRITORY_LEADS = 100  # below this a territory conversion rate is mostly noise
MIN_OWNER_LEADS = 50
INTAKE_DROP_HIGH_PCT = 50
ZERO_WON_SHOWN = 2


def _and(names: list) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _label(month: str) -> str:
    return datetime.strptime(month, "%Y-%m").strftime("%b %Y")


def _channels(p: dict):
    rows = [r for r in p.get("source_performance") or [] if r.get("leads")]
    total = (p.get("kpis") or {}).get("total_leads")
    if len(rows) < 2 or not total:
        return None
    cur = p.get("currency")
    base = max(rows, key=lambda r: r["leads"])
    best = max(rows, key=lambda r: r.get("value_per_lead") or 0)
    if best is base or not base.get("value_per_lead"):
        return brief(
            "low",
            f"{base['source']} supplies {base['leads'] * 100 / total:.1f}% of leads and {money(base.get('value_per_lead'), cur)} won per lead.",
        )
    share = best["leads"] * 100 / total
    ratio = best["value_per_lead"] / base["value_per_lead"]
    text = (
        f"{best['source']} wins {money(best['value_per_lead'], cur)} per lead against {money(base['value_per_lead'], cur)} "
        f"for {base['source']} ({ratio:,.0f}×), yet supplies {share:.1f}% of leads."
    )

    details = [
        detail(r["source"], f"{r['leads']:,} leads, {money(r.get('won_value'), cur)} won, {money(r.get('value_per_lead'), cur)} a lead, {r.get('conversion_rate')}% conversion.")
        for r in (best, base)
    ]
    zero_won = sorted((r for r in rows if not r.get("won_value")), key=lambda r: -(r.get("quoted_value") or 0))
    if zero_won:
        shown = zero_won[:ZERO_WON_SHOWN]
        line = ", ".join(f"{r['source']} {money(r.get('quoted_value'), cur)} quoted" for r in shown)
        more = len(zero_won) - len(shown)
        details.append(detail(plural(len(zero_won), "channel with no won value", "channels with no won value"), line + (f" and {plural(more, 'other')}" if more else "") + "."))

    actions = [action(
        f"Protect and grow {best['source']}",
        f"{best['leads']:,} leads at {best.get('conversion_rate')}% conversion.",
        impact=money(best.get("won_value"), cur),
    ), action(
        f"Review the return on {base['source']}",
        f"{base['leads']:,} leads win {money(base.get('value_per_lead'), cur)} each against {money(best['value_per_lead'], cur)} for {best['source']}.",
        impact=money(base.get("won_value"), cur),
    )]
    if zero_won:
        top = zero_won[:ZERO_WON_SHOWN]
        actions.append(action(
            f"Follow up quotations from {_and([r['source'] for r in top])}",
            f"{money(sum(r.get('quoted_value') or 0 for r in top), cur)} quoted with no won value.",
            impact=money(sum(r.get("quoted_value") or 0 for r in top), cur),
        ))
    return brief("high" if share < 5 else "medium", text, details, actions)


def _trend(p: dict):
    rows = p.get("lead_trend") or []
    if len(rows) < 4:
        return None
    peak = max(rows, key=lambda r: r["leads"])
    if not peak["leads"]:
        return None
    avg = sum(r["leads"] for r in rows[-3:]) / 3
    drop = (1 - avg / peak["leads"]) * 100
    sev = "high" if drop >= INTAKE_DROP_HIGH_PCT else "medium" if drop > 0 else "low"
    if drop <= 0:
        return brief(sev, f"Lead intake is at its peak: {avg:.0f} a month over the last 3 months.")
    text = f"Lead intake is {drop:.0f}% below its {_label(peak['month'])} peak: {avg:.0f} a month (3-month average) against {peak['leads']:,} at peak."

    details, actions = [], []
    rate = (p.get("kpis") or {}).get("lead_conversion_rate")
    if rate is not None:
        details.append(detail("Conversion", f"The lead conversion rate is {rate}%."))
    peak_i = rows.index(peak)
    after = rows[peak_i:]
    details.append(detail("Since the peak", f"{peak['leads']:,} leads in {_label(peak['month'])}, {rows[-1]['leads']:,} in {_label(rows[-1]['month'])}, {plural(len(after) - 1, 'month')} later."))
    actions.append(action(
        f"Find what changed after {_label(peak['month'])}",
        f"Intake fell from {peak['leads']:,} to {avg:.0f} a month.",
    ))
    return brief(sev, text, details, actions)


def _coverage(p: dict):
    avg = (p.get("kpis") or {}).get("lead_conversion_rate")
    terr_raw = p.get("territory_performance") or []
    terr = [
        {**t, "rate": t["converted"] * 100 / t["leads"]}
        for t in terr_raw
        if t["territory"] != "Unassigned" and t["leads"] >= MIN_TERRITORY_LEADS
    ]
    low = sorted((t for t in terr if avg is not None and t["rate"] < avg), key=lambda t: -t["leads"])
    owners = [o for o in p.get("owner_performance") or [] if o["leads"] >= MIN_OWNER_LEADS]
    top = max(owners, key=lambda o: o["conversion_rate"], default=None)
    if not low and not top:
        return None

    parts = []
    if low:
        rates = [t["rate"] for t in low]
        parts.append(
            f"{_and([t['territory'] for t in low])} hold {plural(sum(t['leads'] for t in low), 'lead')} "
            f"at {min(rates):.1f}% to {max(rates):.1f}% conversion, below the {avg}% average"
        )
    if top and avg:
        parts.append(f"{top['owner']} converts at {top['conversion_rate']}%, {top['conversion_rate'] / avg:.1f}× the average")
    text = ". ".join(parts) + "."

    details, actions = [], []
    if low:
        details.append(detail("Low-converting territories", ", ".join(f"{t['territory']} {t['rate']:.1f}% ({t['leads']:,} leads)" for t in low) + "."))
        actions.append(action(
            f"Review follow-up in {_and([t['territory'] for t in low[:2]])}",
            f"{plural(sum(t['leads'] for t in low[:2]), 'lead')} convert at {min(t['rate'] for t in low[:2]):.1f}% to {max(t['rate'] for t in low[:2]):.1f}%.",
        ))
    if top and avg:
        details.append(detail(top["owner"], f"{top['conversion_rate']}% conversion on {top['leads']:,} leads, {top.get('converted', 0):,} converted, against the {avg}% average."))
        actions.append(action(f"Compare how {top['owner']} handles leads", f"Highest conversion among owners with at least {MIN_OWNER_LEADS} leads."))
    un = next((t for t in terr_raw if t["territory"] == "Unassigned"), None)
    if un and un["leads"]:
        details.append(detail("Unassigned", f"{un['leads']:,} leads have no territory; {un['converted']:,} converted ({un['converted'] * 100 / un['leads']:.1f}%)."))
        actions.append(action("Set a territory at lead intake", f"{plural(un['leads'], 'lead')} have none."))
    return brief("medium", text, details, actions)


def lazy_winprob(r: dict):
    t = r.get("training") or {}
    if r.get("status") != "success" or not t.get("closed_total"):
        return None
    return brief(
        "low",
        "Open leads are ranked by a weighted score of source, territory, industry, engagement, size and age. "
        f"It is not a trained model, so no accuracy is measured. It learns from {plural(t['closed_total'], 'closed lead')} "
        f"({t.get('won', 0):,} won, {t.get('lost', 0):,} lost).",
    )


def briefs(p: dict) -> dict:
    out = {"channels": _channels(p), "trend": _trend(p), "coverage": _coverage(p)}
    return {k: v for k, v in out.items() if v}
