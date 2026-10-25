"""Tab briefs for the Customer dashboard (Rule 7: server-built sentences).

Lists in the cached payload (``customers``, ``next_best_actions``,
``at_risk_customers``) are capped, so every figure here comes from ``summary``
or another pre-aggregated block, never from ``len()`` of a list.
"""

from . import action, brief, detail, money, plural

# At-risk share of accounts above which the portfolio is flagged high.
AT_RISK_HIGH_PCT = 50
# Same cut-points as CustomerSections.vue `retentionSeverity` (good 50, warn 25).
RETENTION_GOOD, RETENTION_WARN = 50, 25
# Share of revenue in the top four territories that counts as concentrated.
TERRITORY_CONCENTRATION_PCT = 50


def _pct(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}%"


def _cust_list(p: dict, cur):
    s = p.get("summary") or {}
    total, health = s.get("total_customers"), s.get("health_distribution") or {}
    if not total or not health:
        return None
    at_risk = health.get("At Risk", 0)
    share = at_risk / total * 100
    churn = s.get("churn_risk_distribution") or {}
    hi_crit = churn.get("High", 0) + churn.get("Critical", 0)
    text = f"{_pct(share)} of accounts are At Risk ({at_risk:,} of {total:,})."
    if churn:
        text += f" {plural(hi_crit, 'account')} carry High or Critical churn risk, {churn.get('Critical', 0):,} of them Critical."
    par = p.get("pareto_analysis") or {}
    if par.get("top_80_percent_customers") is not None:
        n = round(par["top_80_percent_customers"] / 100 * total)
        text += f" The top {n:,} customers ({_pct(par['top_80_percent_customers'])}) generate 80% of revenue."
    sev = "high" if share >= AT_RISK_HIGH_PCT else "medium" if share >= AT_RISK_HIGH_PCT / 2 else "low"
    details = [detail("Health", ", ".join(f"{n:,} {k}" for k, n in health.items()) + f" of {total:,} accounts.")]
    actions = []
    if par.get("top_80_percent_customers") is not None:
        details.append(detail(
            "Concentration",
            f"{_pct(par['top_80_percent_customers'])} of accounts generate 80% of revenue; "
            f"the top 10% of customers contribute {_pct(par.get('top_10_percent_contribute') or 0)}.",
        ))
        actions.append(action(
            "Protect the accounts that carry revenue",
            f"{n:,} customers generate 80% of {money(par.get('total_revenue'), cur)} revenue.",
        ))
    if s.get("quote_conversion_rate") is not None:
        details.append(detail(
            "Quotes",
            f"{_pct(s['quote_conversion_rate'])} conversion ({(s.get('converted_quotes') or 0):,} of {(s.get('total_quotes') or 0):,} quotes).",
        ))
    if churn.get("Critical"):
        actions.insert(0, action(
            "Contact Critical churn accounts first",
            f"{churn['Critical']:,} accounts are Critical churn risk. Rank them by predicted 12-month CLV in the Customers directory.",
            impact=f"{churn['Critical']:,} accounts",
        ))
    return brief(sev, text, details, actions)


def _cust_geography(p: dict, cur):
    ga = p.get("geographic_analysis") or {}
    terr = ga.get("territory_analysis") or []
    if len(terr) < 2:
        return None

    def margin(t):
        return t["gross_profit"] / t["total_revenue"] * 100 if t.get("total_revenue") else 0.0

    a, b = terr[0], terr[1]
    text = (
        f"{a['territory']} holds {_pct(a['customer_share'])} of customers and {_pct(a['revenue_share'])} of revenue"
        f" at a {_pct(margin(a))} gross margin."
        f" {b['territory']} drives {_pct(b['revenue_share'])} of revenue from {plural(b['customer_count'], 'customer')}"
        f" at {_pct(margin(b))} margin."
    )
    top = terr[:4]
    top_share = sum(t["revenue_share"] for t in top)
    text += f" The top {len(top)} territories account for {_pct(top_share)} of revenue."
    details = [detail(
        "Margin gap",
        f"{a['territory']} earns {_pct(margin(a))} on {_pct(a['revenue_share'])} of revenue; "
        f"{b['territory']} earns {_pct(margin(b))} on {_pct(b['revenue_share'])}.",
    )]
    actions = []
    cov = ga.get("coverage") or {}
    if cov.get("territories_covered"):
        details.append(detail("Coverage", f"{plural(cov['territories_covered'], 'territory', 'territories')} and {plural(cov.get('customer_groups_covered') or 0, 'customer group')} carry {plural(cov.get('total_customers') or 0, 'customer')}."))
    if margin(b) < margin(a):
        actions.append(action(
            f"Review pricing in {b['territory']}",
            f"Margin is {margin(a) - margin(b):.1f}pp below {a['territory']} on {_pct(b['revenue_share'])} of revenue.",
            impact=f"{money(b['total_revenue'] / 100, cur)} per margin point",
        ))
    return brief("medium" if top_share >= TERRITORY_CONCENTRATION_PCT else "none", text, details, actions)


def _cust_actions(p: dict, cur):
    total = p.get("next_best_actions_total")
    churn = (p.get("summary") or {}).get("churn_risk_distribution") or {}
    if not total:
        return None
    crit, high = churn.get("Critical", 0), churn.get("High", 0)
    text = f"{plural(total, 'customer')} have open recommended actions."
    if churn:
        text += f" {crit + high:,} carry Critical or High churn risk ({crit:,} Critical)."
    details = [detail("Churn risk", ", ".join(f"{n:,} {k}" for k, n in churn.items()) + ".")] if churn else []
    acts = [action(
        "Work the Critical list first" if crit else "Work the High risk list first",
        f"{(crit or high):,} accounts are {'Critical' if crit else 'High'} churn risk. Each has recommendations in the list below.",
        impact=f"{(crit or high):,} accounts",
    )]
    return brief("high" if crit else "medium" if high else "low", text, details, acts)


def _cust_cohorts(p: dict, cur):
    ca = p.get("cohort_analysis") or {}
    avg = ca.get("average_retention") or {}
    m1 = avg.get("1")
    if m1 is None:
        return None
    text = f"{_pct(m1)} of new customers return in month 1"
    if avg.get("2") is not None:
        text += f" and {_pct(avg['2'])} in month 2"
    text += f", averaged over {plural(ca.get('cohort_count') or 0, 'cohort')}."
    sev = "low" if m1 >= RETENTION_GOOD else "medium" if m1 >= RETENTION_WARN else "high"
    details = []
    m2 = avg.get("2")
    if m2 is not None and m1:
        details.append(detail("Month 2", f"Retention falls from {_pct(m1)} to {_pct(m2)}, {(m1 - m2) / m1 * 100:.0f}% lower than month 1."))
    cohorts = [c for c in ca.get("cohort_retention") or [] if (c.get("retention") or {}).get("1") is not None]
    if cohorts:
        best = max(cohorts, key=lambda c: c["retention"]["1"])
        details.append(detail("Best month 1", f"Cohort {best['cohort']} retained {_pct(best['retention']['1'])} at month 1 (cohort of {best.get('size', 0):,})."))
    acts = [action(
        "Re-engage new customers within the first month",
        f"{_pct(100 - m1)} of new customers do not return in month 1.",
        impact=f"{_pct(m1)} month 1 retention",
    )]
    return brief(sev, text, details, acts)


def _cust_rankings(p: dict, cur):
    rows = [c for c in p.get("top_customers") or [] if c.get("gross_profit") is not None]
    if len(rows) < 5:
        return None
    by_rev = {c["customer_id"] for c in sorted(rows, key=lambda c: -(c.get("historical_clv") or 0))[:5]}
    by_gp = {c["customer_id"] for c in sorted(rows, key=lambda c: -c["gross_profit"])[:5]}
    same = len(by_rev & by_gp)
    text = (
        f"Among the top {len(rows)} customers, {same} of the 5 highest by revenue are also in the top 5 by gross profit."
        " Ranking by gross profit changes the list."
        if same < 5
        else f"Among the top {len(rows)} customers, the 5 highest by revenue are also the 5 highest by gross profit."
    )
    lead = max(rows, key=lambda c: c["gross_profit"])
    details = [detail("Gross profit leader", f"{' '.join(lead['customer_name'].split())} earned {money(lead['gross_profit'], cur)} gross profit on {money(lead.get('historical_clv'), cur)} historical revenue.")]
    return brief("medium" if same < 5 else "none", text, details)


def lazy_cust_patterns(r: dict):
    """Brief for the Patterns tab, from the ``purchase_patterns`` response."""
    dow, mon, sea, s = r.get("day_of_week"), r.get("monthly"), r.get("seasonal"), r.get("summary")
    if not (dow and mon and s):
        return brief("none", "No transactions in this window, so there are no purchase patterns to show.")
    total = s.get("total_revenue") or 0
    day_rev = next((d["total_revenue"] for d in dow.get("data") or [] if d.get("day_name") == dow.get("peak_day")), None)
    text = f"Revenue peaks on {dow['peak_day']}"
    if day_rev is not None and total:
        text += f" ({_pct(day_rev / total * 100)} of revenue)"
    text += f" and in {mon['peak_month']}"
    if sea and sea.get("peak_quarter"):
        text += f"; {sea['peak_quarter']} is the strongest quarter"
    scope = r.get("analysis_scope") or {}
    text += f", across {plural(scope.get('transaction_count') or s.get('total_orders') or 0, 'transaction')}."
    return brief("none", text)


def briefs(p: dict) -> dict:
    cur = p.get("base_currency")
    out = {
        "cust-list": _cust_list(p, cur),
        "cust-geography": _cust_geography(p, cur),
        "cust-actions": _cust_actions(p, cur),
        "cust-cohorts": _cust_cohorts(p, cur),
        "cust-rankings": _cust_rankings(p, cur),
    }
    return {k: v for k, v in out.items() if v}
