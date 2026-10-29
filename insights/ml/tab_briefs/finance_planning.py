"""Tab briefs for the Financial dashboard's planning tabs (Rule 7: server-built sentences).

``ratios`` and ``cost`` are the Ratios and Cost Structure tabs; ``cashforecast`` and
``cashflow13`` are the 90-day Cash Forecast and the 13-Week Cash Flow tabs.
"""

import calendar

from . import action, brief, detail, money, plural

CR_GOOD, CR_WARN = 1.5, 1.0  # current-ratio cut-points
LOSS_GOOD, LOSS_WARN = 10, 25  # same loss-probability cut-points as ScenarioAnalysisTab


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _month(period: str) -> str:
    y, m = period.split("-")
    return f"{calendar.month_abbr[int(m)]} {y}"


def _chg(label: str, v) -> str:
    return f"{label} {'up' if v >= 0 else 'down'} {abs(v):g}%"


def _working(p: dict):
    w = p.get("working_capital") or {}
    cur = p.get("base_currency")
    if w.get("cash_conversion_cycle") is None or w.get("working_capital") is None:
        return None
    text = f"The cash conversion cycle is {_f(w['cash_conversion_cycle']):g} days and working capital is {money(w['working_capital'], cur)}"
    cr = w.get("current_ratio")
    if cr is not None:
        text += f" (current ratio {_f(cr):g}×"
        trend = [t for t in w.get("trends") or [] if t.get("current_ratio") is not None]
        if trend:
            low = min(trend, key=lambda t: t["current_ratio"])
            text += f", the lowest over {plural(len(trend), 'month')} was {low['current_ratio']:g}× in {_month(low['period'])}"
        text += ")"
    sev = "none" if cr is None else "low" if cr >= CR_GOOD else "medium" if cr >= CR_WARN else "high"
    details = []
    if all(w.get(k) is not None for k in ("dso", "dio", "dpo")):
        details.append(detail("Cycle", f"DSO {w['dso']:g} + DIO {w['dio']:g} - DPO {w['dpo']:g} = {_f(w['cash_conversion_cycle']):g} days."))
    if w.get("quick_ratio") is not None:
        details.append(detail(
            "Liquidity",
            f"Current assets {money(w.get('total_current_assets'), cur)} against current liabilities {money(w.get('total_current_liabilities'), cur)}; quick ratio {w['quick_ratio']:g}×.",
        ))
    actions = []
    if w.get("dso") is not None and w.get("dpo") is not None and w["dso"] > w["dpo"]:
        actions.append(action(
            "Collect receivables faster",
            f"DSO is {w['dso']:g} days against DPO {w['dpo']:g}: DSO exceeds DPO by {w['dso'] - w['dpo']:.1f} days.",
        ))
    return brief(sev, text + ".", details, actions)


def _capital(p: dict):
    c = p.get("capital_planning") or {}
    cur = p.get("base_currency")
    gross = _f(c.get("total_gross_assets"))
    if gross <= 0:
        return None
    dep = _f(c.get("total_accumulated_depreciation"))
    text = f"Gross assets are {money(gross, cur)} with {money(dep, cur)} of accumulated depreciation"
    sev = "medium" if dep == 0 else "low"
    reg = c.get("register_gross_assets")
    if reg is not None and gross - _f(reg) > 0.5:
        text += f"; the asset register lists {money(reg, cur)} across {plural(c.get('asset_count') or 0, 'asset')}, {money(gross - _f(reg), cur)} less than the ledger"
        sev = "medium"
    details = []
    if c.get("ytd_capex") is not None:
        text_c = f"Capex this year is {money(c['ytd_capex'], cur)}"
        if c.get("prior_year_capex") is not None:
            text_c += f" against {money(c['prior_year_capex'], cur)} over the same period last year"
            if c.get("capex_change_pct") is not None:
                text_c += f" ({c['capex_change_pct']:g}%)"
        details.append(detail("Capex", text_c + "."))
    cats = c.get("category_summary") or []
    if cats:
        details.append(detail("Register", "; ".join(f"{x['category']} {money(x['gross_value'], cur)} ({plural(x['asset_count'], 'asset')})" for x in cats) + "."))
    actions = []
    if reg is not None and gross - _f(reg) > 0.5:
        actions.append(action("Reconcile the asset register to the ledger", "The register lists fewer assets than the ledger carries.", impact=money(gross - _f(reg), cur)))
    if dep == 0:
        actions.append(action("Check depreciation schedules", f"No depreciation is booked on {money(gross, cur)} of assets.", impact=money(gross, cur)))
    return brief(sev, text + ".", details, actions)


def _scenarios(p: dict):
    s = p.get("scenario_analysis") or {}
    cur = p.get("base_currency")
    mc, be = s.get("monte_carlo") or {}, s.get("break_even") or {}
    prob = mc.get("probability_of_loss")
    if prob is None:
        return None
    text = f"{_f(prob):g}% of {mc.get('simulations'):,} simulated outcomes end in a loss"
    if be.get("revenue") is not None and be.get("margin_of_safety") is not None:
        text += f"; break-even revenue is {money(be['revenue'], cur)}, a {_f(be['margin_of_safety']):g}% margin of safety"
        if be.get("fixed_cost_basis") == "assumed_40pct":
            text += " on an assumed 40% fixed-cost share"
    sev = "low" if prob <= LOSS_GOOD else "medium" if prob <= LOSS_WARN else "high"
    pc = mc.get("percentiles") or {}
    details = []
    if pc.get("p5") is not None and pc.get("p50") is not None and pc.get("p95") is not None:
        details.append(detail("Outcome range", f"Net income runs from {money(pc['p5'], cur)} (5th percentile) through {money(pc['p50'], cur)} (median) to {money(pc['p95'], cur)} (95th percentile)."))
    if mc.get("revenue_volatility") is not None:
        details.append(detail("Volatility", f"Revenue {mc['revenue_volatility']:g}%, expenses {mc.get('expense_volatility'):g}%."))
    actions = []
    if be.get("fixed_cost_basis") == "assumed_40pct":
        actions.append(action("Configure fixed and variable costs", "Break-even uses an assumed 40% fixed-cost share; set up cost centers to measure it."))
    if prob > LOSS_GOOD and be.get("margin_of_safety") is not None:
        actions.append(action("Protect the margin of safety", f"Revenue can fall {_f(be['margin_of_safety']):g}% before the business reaches break-even.", impact=money(_f(be.get("current_revenue")) - _f(be.get("revenue")), cur) if be.get("current_revenue") and be.get("revenue") else None))
    return brief(sev, text + ".", details, actions)


def _comparison(p: dict):
    y = (p.get("period_comparison") or {}).get("yoy") or {}
    if y.get("revenue_change") is None or y.get("net_income_change") is None:
        return None
    cur_, prior = y.get("current") or {}, y.get("prior") or {}
    text = f"{_chg('Revenue', y['revenue_change'])} and {_chg('net income', y['net_income_change'])} against {prior.get('label', 'the prior period')}"
    if cur_.get("margin") is not None and prior.get("margin") is not None:
        text += f" (net margin {cur_['margin']:g}% against {prior['margin']:g}%)"
    cur = p.get("base_currency")
    details = [
        detail(label, f"{money(cur_.get(k), cur)} against {money(prior.get(k), cur)}.")
        for label, k in (("Revenue", "revenue"), ("Expenses", "expenses"), ("Net income", "net_income"))
        if cur_.get(k) is not None and prior.get(k) is not None
    ]
    actions = []
    if y["revenue_change"] < 0 and cur_.get("revenue") is not None and prior.get("revenue") is not None:
        actions.append(action(
            "Explain the revenue decline",
            f"Revenue is {money(prior['revenue'] - cur_['revenue'], cur)} lower, while net income is {'higher' if y['net_income_change'] >= 0 else 'lower'}.",
            impact=money(prior["revenue"] - cur_["revenue"], cur),
        ))
    return brief("medium" if y["revenue_change"] < 0 else "low", text + ".", details, actions)


def _unit(card: dict) -> str:
    return "%" if "Margin" in card["name"] or card["name"] in ("ROA", "ROE", "ROCE") else ""


def _ratios(p: dict):
    cards = [c for c in (p.get("ratio_trends") or {}).get("ratio_cards") or [] if c.get("value") is not None]
    if not cards:
        return None
    off = [c for c in cards if c.get("status") != "good"]
    text = f"{len(off)} of {plural(len(cards), 'measurable ratio')} fall short of the generic benchmark"
    pick = [c for c in off if c["name"] in ("Gross Margin", "Net Margin", "Asset Turnover")]
    if pick:
        text += ": " + ", ".join(f"{c['name'].lower()} {c['value']:g}{u} against {c['benchmark']:g}{u}" for c in pick for u in ["%" if "Margin" in c["name"] else ""])
    sev = "high" if any(c.get("status") == "critical" for c in off) else "medium" if off else "low"
    details = [
        detail(c["name"], f"{c['value']:g}{_unit(c)} against {c['benchmark']:g}{_unit(c)}, status {c['status']}.")
        for c in off if c.get("benchmark") is not None
    ]
    actions = [
        action(f"Lift {c['name']}", f"It is {c['value']:g}{_unit(c)} against {c['benchmark']:g}{_unit(c)}.")
        for c in sorted(off, key=lambda c: c["value"] / c["benchmark"] if c.get("benchmark") else 1)[:3] if c.get("benchmark")
    ]
    return brief(sev, text + ".", details, actions)


def _cost(p: dict):
    cs = p.get("cost_structure") or {}
    f = cs.get("figures") or {}
    cur = p.get("base_currency")
    rev, gp, net = f.get("revenue"), f.get("gross_profit"), f.get("net_profit")
    if not rev or gp is None:
        return None
    cards = cs.get("ratio_cards") or []
    graded = [c for c in cards if c.get("value") is not None]
    off = [c for c in graded if c.get("status") != "good"]
    ungraded = [c for c in cards if c.get("value") is None]
    text = f"Gross profit is {gp / rev * 100:.1f}% of revenue ({money(gp, cur)} of {money(rev, cur)})"
    if net is not None:
        text += f" and net profit is {net / rev * 100:.1f}%"
    if graded:
        text += f". {len(graded) - len(off)} of {plural(len(graded), 'graded cost ratio')} are within target"
    else:
        text += ". No cost ratio can be graded for this period"
    if ungraded:
        text += f"; {plural(len(ungraded), 'ratio')} have no data"
    sev = {"risky": "high", "moderate": "medium"}.get(cs.get("overall_status"), "low")

    def val(c: dict, key: str) -> str:
        return f"{c[key]:g}{c.get('unit') or ''}"

    details = [detail(c["name"], f"{val(c, 'value')} against an ideal of {val(c, 'ideal')}, status {c['status']}.") for c in off if c.get("ideal") is not None]
    if ungraded:
        details.append(detail("No data", ", ".join(c["name"] for c in ungraded) + " have no activity recorded against their accounts this period."))
    actions = [action(f"Bring {c['name']} back to target", f"It is {val(c, 'value')} against an ideal of {val(c, 'ideal')}.") for c in off[:3] if c.get("ideal") is not None]
    return brief(sev, text + ".", details, actions)


def _cashforecast(p: dict):
    f = p.get("cash_forecast") or {}
    cur = p.get("base_currency")
    eop = f.get("end_of_period") or {}
    end, pess = eop.get("base"), eop.get("pessimistic")
    if end is None or f.get("current_cash") is None:
        return None
    text = (
        f"The 90-day base forecast moves cash from {money(f['current_cash'], cur)} to {money(end, cur)}, "
        f"with {money(f.get('expected_ar_inflows'), cur)} of receivable inflows against {money(f.get('expected_ap_outflows'), cur)} of payable outflows"
    )
    sev = "high" if end < 0 else "medium" if pess is not None and pess < 0 else "low"
    details = [detail("90-day scenarios", f"Base {money(end, cur)}, optimistic {money(eop.get('optimistic'), cur)}, pessimistic {money(pess, cur)}.")]
    base_d, pess_d = f.get("base_runway_days"), f.get("pessimistic_runway_days")
    if base_d is not None or pess_d is not None:
        # None = balance stays positive for the whole forecast; 0 = already at or below zero.
        def _runway(d):
            return "stays positive for 90 days" if d is None else "is already at or below zero" if d == 0 else f"runs out in {plural(d, 'day')}"

        details.append(detail("Runway", f"Base case {_runway(base_d)}; pessimistic case {_runway(pess_d)}."))
    ending = ((p.get("thirteen_week_forecast") or {}).get("summary") or {}).get("ending_cash")
    if ending is not None:
        details.append(detail("13-week model", f"Ends at {money(ending, cur)}, built from open invoices by due date rather than a trend; see the 13-Week Cash Flow tab."))
    actions = []
    weeks = f.get("weekly_summary") or []
    if end < 0 and weeks:
        low = min(weeks, key=lambda w: w["base_balance"])
        actions.append(action("Cover the projected cash shortfall", f"The 90-day base forecast is lowest in week {low['week']} at {money(low['base_balance'], cur)}.", impact=money(-low["base_balance"], cur)))
    if f.get("expected_ar_inflows"):
        actions.append(action("Collect the receivables the forecast relies on", f"Forecast inflows assume {money(f['expected_ar_inflows'], cur)} of receivables are collected.", impact=money(f["expected_ar_inflows"], cur)))
    return brief(sev, text + ".", details, actions)


def _cashflow13(p: dict):
    t = p.get("thirteen_week_forecast") or {}
    cur = p.get("base_currency")
    s = t.get("summary") or {}
    opening = t.get("opening_balance")
    if s.get("ending_cash") is None or opening is None:
        return None
    text = f"The 13-week model opens at {money(opening, cur)} and ends at {money(s['ending_cash'], cur)}"
    low = s.get("minimum_balance")
    below = s.get("weeks_below_threshold") or 0
    if low is not None:
        text += f", with its lowest balance of {money(low, cur)} in week {s.get('minimum_balance_week')} ({s.get('minimum_balance_date')})"
    sev = "high" if low is not None and low < 0 else "medium" if below else "low"
    details = []
    if low is not None:
        details.append(detail("13-week low", f"Week {s.get('minimum_balance_week')} ({s.get('minimum_balance_date')}) at {money(low, cur)}; {plural(below, 'week')} below the minimum."))
    pay = t.get("payroll_detection") or {}
    if pay.get("detected"):
        details.append(detail("Payroll", f"{pay.get('frequency', '').capitalize()} payroll of {money(pay.get('typical_amount'), cur)} detected, next {pay.get('next_date')}."))
    actions = []
    if low is not None and low < 0:
        actions.append(action("Cover the 13-week cash gap", f"Week {s.get('minimum_balance_week')} is the lowest at {money(low, cur)}.", impact=money(-low, cur)))
    return brief(sev, text + ".", details, actions)


def briefs(p: dict) -> dict:
    out = {}
    for tab, fn in (
        ("working", _working),
        ("capital", _capital),
        ("scenarios", _scenarios),
        ("comparison", _comparison),
        ("ratios", _ratios),
        ("cost", _cost),
        ("cashforecast", _cashforecast),
        ("cashflow13", _cashflow13),
    ):
        b = fn(p)
        if b:
            out[tab] = b
    return out


# Lazy tabs: each endpoint returns its own payload, so the brief rides that response.
_RAG = {"green": "low", "amber": "medium", "red": "high"}
BUDGET_HIGH, BUDGET_MED = 20, 10  # |variance %|


def lazy_budget(p: dict):
    cur = p.get("base_currency")
    info = p.get("period_info") or {}
    if p.get("has_budget") is False:
        return brief("medium", f"No submitted Budget exists for fiscal year {info.get('fiscal_year', '')}".rstrip() + "; variance cannot be computed.")
    s = p.get("summary") or {}
    if s.get("total_budget") is None or s.get("variance_percentage") is None:
        return None
    v = abs(_f(s["variance_percentage"]))
    sev = "high" if v > BUDGET_HIGH else "medium" if v > BUDGET_MED else "low"
    return brief(
        sev,
        f"Budget of {money(s['total_budget'], cur)} shows a variance of {money(s.get('total_variance'), cur)} ({_f(s['variance_percentage']):g}%).",
        [detail("Actual", f"{money(s.get('total_actual'), cur)} spent against {money(s['total_budget'], cur)} budgeted.")] if s.get("total_actual") is not None else None,
    )


def lazy_beoverview(p: dict):
    cur = p.get("base_currency")
    if p.get("configured") is False:
        text = "Break-even is not configured: no fixed or variable cost centers are set up"
        if p.get("actual_revenue") is not None:
            text += f"; revenue for the period is {money(p['actual_revenue'], cur)}"
        return brief("none", text + ".")
    if p.get("be_revenue") is None or p.get("actual_revenue") is None:
        return None
    text = f"Break-even revenue is {money(p['be_revenue'], cur)} against {money(p['actual_revenue'], cur)} actual"
    if p.get("safety_margin") is not None:
        text += f", a {_f(p['safety_margin']):g}% safety margin"
    return brief(_RAG.get((p.get("rag") or "").lower(), "none"), text + ".")
