"""Tab briefs for the HR dashboard (Rule 7: server-built sentences)."""

from . import action, brief, detail, money, plural

UNASSIGNED = "(Unassigned)"


def _sev(level) -> str:
    return level if level in ("low", "medium", "high") else "medium"


def _pct(v) -> str:
    return f"{v:.1f}%"


def _dept(name: str) -> str:
    return name.split(" - ")[0]


def _departments(p: dict):
    """(unassigned headcount, single-person department names) from department_health."""
    dm = (p.get("department_health") or {}).get("department_metrics") or {}
    un = (dm.get(UNASSIGNED) or {}).get("headcount") or 0
    solo = [_dept(d) for d, m in dm.items() if d != UNASSIGNED and (m.get("headcount") or 0) == 1]
    return un, solo, sum(1 for d in dm if d != UNASSIGNED)


def _attrition(p: dict):
    am, risk = p.get("attrition_metrics") or {}, p.get("attrition_risk") or {}
    eng = p.get("engagement_indicators") or {}
    rate, exits = am.get("attrition_rate_pct"), am.get("total_exits")
    if rate is None or exits is None:
        return None
    invol, vol = am.get("involuntary_exits"), am.get("voluntary_exits")
    text = f"Attrition is {_pct(rate)} TTM: {plural(exits, 'exit')}"
    if invol is not None and vol is not None:
        text += f", {invol} involuntary and {vol} voluntary"
    text += "."
    details, actions = [], []
    if risk.get("predicted_attrition_rate") is not None:
        details.append(detail("Predicted attrition", f"{_pct(risk['predicted_attrition_rate'])}, risk score {risk.get('risk_score')}/100."))
    if risk.get("risk_factors"):
        details.append(detail("Risk factors", "; ".join(risk["risk_factors"]) + "."))
    if eng.get("engagement_score") is not None:
        ki = eng.get("key_indicators") or {}
        line = f"Score {eng['engagement_score']}/100 ({eng.get('engagement_level')})"
        if ki:
            line += ": " + ", ".join(f"{k.replace('_contribution', '').replace('_', ' ')} {v}" for k, v in ki.items()) + " points"
        details.append(detail("Engagement", line + "."))
    att = p.get("attendance_metrics") or {}
    if att.get("attendance_rate_pct") is not None:
        details.append(detail("Attendance", f"{att['attendance_rate_pct']:g}% attendance, {plural(att.get('late_arrivals') or 0, 'late arrival')} ({att.get('late_arrival_rate_pct')}%)."))
    if exits and invol == exits:
        actions.append(action("Review the reasons for involuntary exits", f"All {plural(exits, 'exit')} in the period were involuntary."))
    return brief(_sev(risk.get("risk_level") or am.get("attrition_risk_level")), text, details, actions)


def _department(p: dict):
    dh = p.get("department_health") or {}
    dm = dh.get("department_metrics") or {}
    total = (p.get("headcount_metrics") or {}).get("total_employees")
    if not dm or not total:
        return None
    un, solo, n_named = _departments(p)
    big = dh.get("largest_department")
    text = f"{plural(n_named, 'department')} named"
    if big and big in dm:
        n = dm[big].get("headcount") or 0
        text += f"; the largest, {_dept(big)}, has {plural(n, 'employee')} ({_pct(n * 100 / total)} of {total})"
    if un:
        text += f". {plural(un, 'employee')} ({_pct(un * 100 / total)}) have no department"
    details, actions = [], []
    if solo:
        details.append(detail("Single-person departments", f"{len(solo)} of {n_named} named departments have one employee: {', '.join(solo)}."))
        actions.append(action("Plan cover for single-person departments", f"{', '.join(solo)} each have one employee."))
    if un:
        details.append(detail("Unassigned", "Their exits, attendance and payroll cost cannot be attributed to a department."))
        actions.append(action(f"Assign {plural(un, 'employee')} to a department", "Department figures cannot attribute these employees until the Department field is set."))
    if (p.get("payroll_metrics") or {}).get("payroll_efficiency") == "no_data":
        details.append(detail("Payroll cost", "Department payroll cost is unavailable because no Salary Slips exist."))
    return brief("medium" if un or solo else "low", text + ".", details, actions)


def _payroll(p: dict):
    pm = p.get("payroll_metrics") or {}
    if not pm:
        return None
    if pm.get("payroll_efficiency") == "no_data":
        n = (p.get("headcount_metrics") or {}).get("total_employees")
        who = f"for {plural(n, 'active employee')}" if n else "for the workforce"
        return brief(
            "medium",
            f"No Salary Slip records exist, so payroll and compensation figures are unavailable {who}.",
            [detail("Not an error", "The analysis ran; the source documents do not exist yet, so total payroll, average salary, cost per employee, deduction rate and pay ratio show as unavailable.")],
            [action("Set up payroll in HRMS", "Create a Salary Structure for each employee, then process and submit a Payroll Entry so Salary Slips exist. The tab fills at the next dashboard refresh.")],
        )
    cur = p.get("currency") or p.get("base_currency")
    text = (
        f"Payroll cost {money(pm.get('total_payroll_cost'), cur)} across "
        f"{plural(pm.get('employees_on_payroll') or 0, 'employee')}, average salary {money(pm.get('average_salary'), cur)}."
    )
    details = []
    if pm.get("cost_per_employee") is not None:
        details.append(detail("Cost per employee", f"{money(pm['cost_per_employee'], cur)}; deduction rate {pm.get('deduction_rate_pct')}%."))
    comp = p.get("compensation_analysis") or {}
    if comp.get("pay_equity_status") not in (None, "no_data"):
        details.append(detail("Pay spread", f"Median salary {money(comp.get('median_salary'), cur)}; highest paying department {comp.get('highest_paying_dept')}, lowest {comp.get('lowest_paying_dept')}."))
    return brief("low", text, details)


def _planning(p: dict):
    hf, risk = p.get("hiring_forecast") or {}, p.get("attrition_risk") or {}
    am, hc = p.get("attrition_metrics") or {}, p.get("headcount_metrics") or {}
    need = hf.get("total_hiring_need")
    if need is None:
        return None
    rate, exits, total = am.get("attrition_rate_pct"), am.get("total_exits"), hc.get("total_employees")
    proj = hf.get("projected_exits_next_quarter")
    if rate is not None and exits is not None and total:
        text = f"Attrition is {_pct(rate)} on {plural(total, 'employee')}: {exits} exits a year."
        if risk.get("predicted_attrition_rate") is not None:
            text += f" The model predicts {_pct(risk['predicted_attrition_rate'])}."
        text += f" Hiring need next quarter is {need}."
    else:
        text = f"Hiring need next quarter is {need} against {plural(proj or 0, 'projected exit')}."

    details, actions = [], []
    if proj is not None and exits is not None:
        details.append(detail("Next quarter", f"The model projects {plural(proj, 'exit')}; the last twelve months averaged {exits / 4:g} a quarter."))
    if hf.get("growth_based_hiring") is not None:
        details.append(detail("Hiring need", f"{hf.get('growth_based_hiring')} for growth, {need} in total; urgency {hf.get('hiring_urgency')}."))
    nodata = (p.get("payroll_metrics") or {}).get("payroll_efficiency") == "no_data"
    if nodata:
        details.append(detail("Payroll", "No Salary Slip records exist, so replacement cost cannot be computed."))
    un, _, _ = _departments(p)
    if un:
        actions.append(action(f"Assign {plural(un, 'employee')} to a department", "Department-level hiring needs cannot be computed until every employee is attributed."))
    if nodata:
        actions.append(action("Record Salary Slips", "Replacement cost and cost per hire need a salary baseline."))
    if need:
        actions.append(action("Plan next quarter's hires", f"{plural(need, 'hire')} needed next quarter."))
    return brief(_sev(risk.get("risk_level")), text, details, actions)


def briefs(p: dict) -> dict:
    out = {"attrition": _attrition(p), "department": _department(p), "payroll": _payroll(p), "planning": _planning(p)}
    return {k: v for k, v in out.items() if v}
