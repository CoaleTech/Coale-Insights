"""Tab briefs for the Revenue dashboard (Rule 7: server-built sentences)."""

from datetime import date

from . import action, brief, detail, money

# Same cut-points as RevenueSections.vue `dsoSeverity` (good <= 30, warn <= 60).
DSO_TARGET, DSO_HIGH = 30, 60
# sMAPE above this is "low reliability" in the approved Forecasts design.
SMAPE_LOW_RELIABILITY = 40
# ERPNext's built-in root Item Group: items left in it have no specific product group.
ROOT_ITEM_GROUP = "All Item Groups"


def _pct(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}%"


def _month(period: str) -> str:
    y, m = period.split("-")
    return date(int(y), int(m), 1).strftime("%b %Y")


def _day(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d %b %Y")


def _rev_payment(p: dict, cur):
    mix, ful = p.get("payment_mix") or {}, p.get("fulfillment") or {}
    dso, ar, credit = ful.get("dso"), ful.get("total_receivables"), mix.get("credit_ratio")
    if dso is None or ar is None:
        return None
    sev = "low" if dso <= DSO_TARGET else "medium" if dso <= DSO_HIGH else "high"
    daily = ful.get("avg_daily_sales")
    text = f"Credit terms are locking {money(ar, cur)} in receivables: DSO {dso:.1f} days against a {DSO_TARGET}-day target"
    if daily:
        text += f", equal to {dso:.1f} days of average daily sales ({money(daily, cur)})"
    text += "."
    if credit is not None:
        text += f" Credit is {_pct(credit)} of revenue and carries all of that receivable balance."
    details, actions = [], []
    if daily and dso > DSO_TARGET:
        # DSO = receivables / average daily sales, so the balance a 30-day DSO would hold is 30 x that daily figure.
        excess = ar - DSO_TARGET * daily
        details.append(detail(
            "Impact",
            f"At a {DSO_TARGET}-day DSO receivables would be {money(DSO_TARGET * daily, cur)}; "
            f"{money(excess, cur)} is held beyond that target.",
        ))
        actions.append(action(
            f"Bring receivables to a {DSO_TARGET}-day DSO",
            f"DSO is {dso:.1f} days. Each day removed releases {money(daily, cur)} of working capital.",
            impact=money(excess, cur),
        ))
    if mix.get("cash_total") is not None and mix.get("credit_total") is not None:
        details.append(detail(
            "Mix",
            f"Cash sales {money(mix['cash_total'], cur)} ({_pct(mix.get('cash_ratio') or 0)}), "
            f"credit sales {money(mix['credit_total'], cur)} ({_pct(credit or 0)}).",
        ))
    if not mix.get("daily_mix"):
        details.append(detail("Data gap", "The daily payment-mix feed is empty for this window, so the daily cash ratio cannot be shown."))
        actions.append(action(
            "Check that payment mode is recorded on Sales Invoices",
            "The daily cash and credit split is empty for this window.",
        ))
    return brief(sev, text, details, actions)


def _rev_reps(p: dict, cur):
    sr = p.get("sales_reps") or {}
    reps, team, top = sr.get("reps") or [], sr.get("total_team_revenue"), sr.get("top_performer")
    if not reps or not team or not top:
        return None
    name = lambda r: r.get("sales_person_name") or r.get("sales_person")
    share = top["total_revenue"] / team * 100
    rest = team - top["total_revenue"]
    if len(reps) == 1:
        return brief("medium", f"All {money(team, cur)} of revenue is attributed to one rep, {name(top)}.")
    text = (
        f"One rep drives {_pct(share)} of revenue: if {name(top)} left, the team would retain "
        f"{money(rest, cur)} ({_pct(100 - share)}) of the {money(team, cur)} book."
    )
    best = max(reps, key=lambda r: r.get("margin_pct") or 0)
    if best is not top and best.get("margin_pct") is not None:
        text += (
            f" The highest-margin rep ({name(best)}, {_pct(best['margin_pct'])}) handles "
            f"{_pct(best['total_revenue'] / team * 100, 2)} of revenue."
        )
    blended = (p.get("margins") or {}).get("overall_margin")
    ranked = sorted(reps, key=lambda r: r["total_revenue"], reverse=True)
    hhi = sum((r["total_revenue"] / team * 100) ** 2 for r in reps)
    details = [detail(
        "Concentration",
        f"{name(top)} {money(top['total_revenue'], cur)} against {money(rest, cur)} for all other reps combined. "
        f"Herfindahl index {hhi:,.0f} (10,000 means one rep holds all revenue).",
    )]
    actions = [action(
        f"Reduce dependence on {name(top)}'s book",
        f"{name(top)} holds {top.get('unique_customers', 0):,} customers and {_pct(share)} of revenue. "
        "Assign a second rep to the largest accounts.",
        impact=f"{_pct(share)} of revenue",
    )]
    if blended is not None:
        second = ranked[1]
        if second.get("margin_pct") is not None and second["margin_pct"] < blended:
            gap = blended - second["margin_pct"]
            details.append(detail(
                "Margin quality",
                f"{name(second)} ({_pct(second['total_revenue'] / team * 100)} share) earns {_pct(second['margin_pct'])}, "
                f"{gap:.1f}pp below the blended {_pct(blended)}.",
            ))
            actions.append(action(
                f"Review {name(second)}'s pricing",
                f"Margin is {gap:.1f}pp below blended on {money(second['total_revenue'], cur)} of revenue.",
                impact=f"{money(second['total_revenue'] / 100, cur)} per margin point",
            ))
        if best is not top and (best.get("margin_pct") or 0) > blended:
            details.append(detail(
                "Best margin",
                f"{name(best)} ({_pct(best['total_revenue'] / team * 100, 2)} share) earns {_pct(best['margin_pct'])}, "
                f"{best['margin_pct'] - blended:.1f}pp above the blended {_pct(blended)}.",
            ))
            actions.append(action(
                f"Grow {name(best)}'s book",
                f"{name(best)} earns {_pct(best['margin_pct'])} on {best.get('unique_customers', 0):,} customers.",
                impact=f"{best['margin_pct'] - blended:.1f}pp above blended",
            ))
    if all(not r.get("total_incentives") for r in reps):
        actions.append(action(
            "Check incentive data",
            f"Incentives are {money(0, cur)} for all {len(reps)} reps in this window.",
        ))
    return brief("medium" if share >= 50 else "none", text, details, actions)


def _rev_margins(p: dict, cur):
    m = p.get("margins") or {}
    overall, trend = m.get("overall_margin"), [t for t in m.get("margin_trend") or [] if not t.get("is_partial")]
    if overall is None:
        return None
    text = f"Blended margin is {_pct(overall)}."
    details, actions = [], []
    if len(trend) >= 3:
        peak = max(trend, key=lambda t: t["margin_pct"])
        after = [t for t in trend if t["period"] > peak["period"]]
        if after:
            low = min(after, key=lambda t: t["margin_pct"])
            months = (int(low["period"][:4]) - int(peak["period"][:4])) * 12 + int(low["period"][5:]) - int(peak["period"][5:])
            text += (
                f" It fell from {_pct(peak['margin_pct'])} ({_month(peak['period'])}) to {_pct(low['margin_pct'])} "
                f"({_month(low['period'])}) in {months} months, a {abs(peak['margin_pct'] - low['margin_pct']):.1f}pp decline,"
                f" and was {_pct(trend[-1]['margin_pct'])} in {_month(trend[-1]['period'])}."
            )
        others = sorted((t["gross_profit"] for t in trend if t is not peak), reverse=True)
        if others and others[0] > 0:
            details.append(detail(
                f"{_month(peak['period'])} peak",
                f"Gross profit was {money(peak['gross_profit'], cur)} on {money(peak['revenue'], cur)} revenue "
                f"({_pct(peak['margin_pct'])}), {peak['gross_profit'] / others[0] * 100 - 100:.0f}% above the next-highest month.",
            ))
            actions.append(action(
                f"Find what drove {_month(peak['period'])}",
                f"Margin was {peak['margin_pct'] - overall:.1f}pp above blended that month. Check for a one-off batch or pricing event.",
            ))
    groups, total = m.get("by_product_group") or [], m.get("total_revenue")
    if len(groups) >= 2 and total:
        hi, lo = max(groups, key=lambda g: g["margin_pct"]), min(groups, key=lambda g: g["margin_pct"])
        text += (
            f" {hi['item_group']} is the margin outlier at {_pct(hi['margin_pct'])} on "
            f"{_pct(hi['revenue'] / total * 100)} of revenue; the lowest margin is {lo['item_group']} at {_pct(lo['margin_pct'])}."
        )
        root = next((g for g in groups if g["item_group"] == ROOT_ITEM_GROUP), None)
        if root:
            rshare = root["revenue"] / total * 100
            details.append(detail(
                "Taxonomy gap",
                f"'{ROOT_ITEM_GROUP}' ({money(root['revenue'], cur)}, {_pct(rshare)} of revenue) is the root group: "
                f"items sold under it have no specific group, so group margins cover only {_pct(100 - rshare)} of revenue.",
            ))
            actions.append(action(
                "Assign item groups to items under the root group",
                f"{_pct(rshare)} of revenue cannot be analyzed by product group.",
                impact=f"{_pct(rshare)} of revenue",
            ))
        if lo["item_group"] != ROOT_ITEM_GROUP:
            actions.append(action(
                f"Review pricing in {lo['item_group']}",
                f"Margin is {_pct(lo['margin_pct'])} on {money(lo['revenue'], cur)} of revenue.",
                impact=f"{money(lo['revenue'] / 100, cur)} per margin point",
            ))
    return brief("none", text, details, actions)


def _rev_forecasts(p: dict, cur):
    sf = (p.get("forecasts") or {}).get("sales_forecast") or {}
    summary = sf.get("forecast_summary") or {}
    total = summary.get("total_forecast")
    if total is None:
        return None
    smape, stale = (sf.get("metrics") or {}).get("smape"), summary.get("stale_days")
    days = summary.get("days", 30)
    text = f"The {days}-day point forecast of {money(total, cur)} is directional, not a plan number."
    if smape is not None:
        text += f" sMAPE is {_pct(smape)} fitting the trend to its own {sf['metrics'].get('n_points', 'daily')} days of history."
    if stale:
        text += f" Training data ends {stale} days before the forecast starts."
    details, actions = [], []
    end, first = (sf.get("data_range") or {}).get("end"), summary.get("first_day")
    if stale and end and first:
        details.append(detail(
            "Stale window",
            f"The model was trained through {_day(end)}. Forecasting starts {_day(first)}, {stale} days of revenue the model has not seen.",
        ))
        actions.append(action(
            "Retrain after the latest invoices post",
            f"Training data ends {_day(end)}. Retrain once later invoices are posted so the forecast starts from current data.",
        ))
    rows = sf.get("forecast") or []
    lows = [r["yhat_lower"] for r in rows if r.get("yhat_lower") is not None]
    ups = [r["yhat_upper"] for r in rows if r.get("yhat_upper") is not None]
    if lows and ups and len(lows) == len(rows):
        ci = f"The daily confidence interval spans {money(min(lows), cur)} to {money(max(ups), cur)}."
        if max(lows) == 0:
            ci += f" The lower bound is {money(0, cur)} on all {len(rows)} days."
        details.append(detail("Interval width", ci))
        actions.append(action(
            "Plan on the range, not the point",
            f"Over {days} days: downside {money(sum(lows), cur)}, base {money(total, cur)}, upside {money(sum(ups), cur)}.",
        ))
    return brief("medium" if smape is not None and smape > SMAPE_LOW_RELIABILITY else "none", text, details, actions)


def lazy_rev_sources(q: dict):
    """Brief for the Attribution tab, built from the quotation funnel response."""
    total = q.get("total") or 0
    if not total:
        return brief("none", "No quotations in this period. Lead Source must be set on Quotations before revenue can be attributed to sources.")
    rate, lost = q.get("conversion_rate"), q.get("lost") or 0
    text = f"{total:,} quotations: {q.get('won') or 0:,} won, {lost:,} lost, {q.get('pending') or 0:,} open or expired, conversion {_pct(rate or 0)}."
    reasons = q.get("lost_reasons") or []
    if reasons:
        top = max(reasons, key=lambda r: r["count"])
        text += f" The most common loss reason is {top['order_lost_reason']} ({top['count']:,})."
    return brief("none", text)


def briefs(p: dict) -> dict:
    cur = p.get("base_currency")
    out = {
        "rev-payment": _rev_payment(p, cur),
        "rev-reps": _rev_reps(p, cur),
        "rev-margins": _rev_margins(p, cur),
        "rev-forecasts": _rev_forecasts(p, cur),
    }
    return {k: v for k, v in out.items() if v}
