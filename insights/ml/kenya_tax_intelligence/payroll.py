# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Payroll taxes tab: PAYE / NSSF / SHIF / AHL / NITA from HRMS Salary Slips.

Source: Salary Slip + Salary Detail (deductions) + Employee. The statutory
deductions are found by component name (`rules.SALARY_COMPONENT_PATTERNS`), and the
latest month with submitted slips (start_date <= today) is the reporting month.

Heuristics (ceilings noted where they bite):
- Employer NSSF and AHL mirror the employee amount (statutory match); NITA = 50 x headcount.
- Residency and KRA PIN are read from Employee custom fields whose name holds "resident" / the word
  "pin". Without such a field the matching check is skipped (never guessed).
- "Remittance paid" is the sum of Payment/Journal Entry debits on the matching tax account after
  month end. With no matching account the chip says payment is not traceable.

Drill metrics (filters: `page`): payroll_slips, payroll_nssf_mismatch, payroll_shif_mismatch,
payroll_ahl_mismatch, payroll_relief_nonresident, payroll_missing_pin, payroll_paye_movement.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from insights.ml.kenya_tax_intelligence import rules
from insights.ml.kenya_tax_intelligence.common import (
    TaxContext,
    chip,
    doctype_exists,
    drill_page,
    gl_debit,
    holidays,
    kpi,
    month_key,
    month_starts,
    tax_accounts,
    unavailable,
)

TOL = 1.0  # KES; deductions are rounded to whole shillings on payslips
MOVE_PCT = 0.05
KINDS = ("paye", "nssf", "shif", "ahl", "pension", "mortgage")
_PIN_RE = re.compile(r"(^|_)pin($|_)")
_MISMATCH = {"nssf", "shif", "ahl"}


# --------------------------------------------------------------------------- pure logic
def is_non_resident(col: str, value: Any) -> Optional[bool]:
    """Read a residency custom field: True non-resident, False resident, None unknown.

    `col` decides the polarity of a Check/Yes-No value ("non_resident" = yes means non-resident,
    "is_resident" = no means non-resident); free text is read by the word "non".
    """
    if value in (None, ""):
        return None
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "y"):
        yes = True
    elif s in ("0", "false", "no", "n"):
        yes = False
    else:
        return "non" in s
    return yes if "non" in col.lower() else not yes


def nssf_year(on: date) -> int:
    """1-based NSSF contribution year in force on `on`."""
    return max(sum(1 for row in rules.NSSF_YEARS if on >= row[0]), 1)


def remit_chip(due: date, today: date, amount: Optional[float], paid: Optional[float]) -> Dict[str, str]:
    """Status chip for one remittance. `paid` None = no tax account to trace payment against."""
    days = (due - today).days
    if paid is not None and amount and paid >= amount * 0.99:
        return chip("pos", "Paid")
    if paid:
        return chip("warn", "Part-paid")
    if days >= 0:
        return chip("acc", f"Due in {days} d")
    if paid is None:
        return chip("mut", f"Due {-days} d ago, payment not traceable")
    return chip("neg", f"Overdue {-days} d")


def band_headcount(taxables: List[float]) -> List[Dict[str, Any]]:
    counts = [0] * len(rules.PAYE_BANDS)
    for t in taxables:
        counts[rules.paye_band_index(t)] += 1
    return [
        {"label": rules.PAYE_BAND_LABELS[i], "rate": round(rate * 100, 2), "headcount": counts[i]}
        for i, (_upper, rate) in enumerate(rules.PAYE_BANDS)
    ]


def enrich(row: Dict[str, Any], on: date) -> Dict[str, Any]:
    """Attach the expected statutory figures (`exp`) to a slip row; unknown residency counts as resident."""
    row["exp"] = rules.paye(
        row["gross"], on, resident=not row.get("nonres"), pension=row.get("pension", 0.0), mortgage_interest=row.get("mortgage", 0.0)
    )
    return row


def find_exceptions(rows: List[Dict[str, Any]], prev_paye: Dict[str, float], kinds: set, has_pin: bool, has_res: bool) -> Dict[str, List[Dict[str, Any]]]:
    """metric -> [{slip, employee, employee_name, gross, actual, expected, difference}] over enriched slip rows."""
    out: Dict[str, List[Dict[str, Any]]] = {}

    def add(metric, r, actual, expected, diff):
        out.setdefault(metric, []).append({
            "slip": r["slip"], "employee": r["employee"], "employee_name": r["employee_name"], "gross": r["gross"],
            "actual": actual, "expected": expected, "difference": diff,
        })

    for r in rows:
        e = r["exp"]
        for k in _MISMATCH & kinds:
            if abs(r[k] - e[k]) > TOL:
                add(f"payroll_{k}_mismatch", r, r[k], e[k], round(r[k] - e[k], 2))
        if has_res and "paye" in kinds and r.get("nonres") and r["paye"] < e["paye"] - TOL:
            add("payroll_relief_nonresident", r, r["paye"], e["paye"], round(e["paye"] - r["paye"], 2))
        if has_pin and not r.get("pin"):
            add("payroll_missing_pin", r, None, None, None)
    if "paye" in kinds:
        cur: Dict[str, float] = {}
        for r in rows:
            cur[r["employee"]] = cur.get(r["employee"], 0.0) + r["paye"]
        names = {r["employee"]: r for r in rows}
        for emp, now in cur.items():
            prev = prev_paye.get(emp)
            if prev and abs(now - prev) / prev > MOVE_PCT:
                add("payroll_paye_movement", names[emp], now, prev, round(now - prev, 2))
    return out


# --------------------------------------------------------------------------- data
def _employee_cols():
    """(pin fieldname, residency fieldname) among Employee custom fields, else None each."""
    fields = [df.fieldname for df in frappe.get_meta("Employee").fields if df.fieldtype in ("Data", "Select", "Check", "Link", "Small Text")]
    custom = [f for f in fields if f.startswith("custom_")]
    pin = next((f for f in custom if _PIN_RE.search(f)), None)
    res = next((f for f in custom if "resident" in f or "residency" in f), None)
    return pin, res


def _load(ctx: TaxContext) -> Optional[Dict[str, Any]]:
    """Latest-month slip rows, 12-month trend and prior-month PAYE. None when no slips exist."""
    if "payroll" in ctx._cache:
        return ctx._cache["payroll"]
    data = None
    last = frappe.db.sql(
        "SELECT MAX(start_date) FROM `tabSalary Slip` WHERE docstatus = 1 AND company = %s AND start_date <= %s",
        (ctx.company, ctx.today),
    )[0][0]
    if last:
        month = last.replace(day=1)
        start = month_starts(month, 12)[0]
        end = rules.month_end(month)
        slips = frappe.db.sql(
            """SELECT name, employee, employee_name, start_date, base_gross_pay AS gross,
                      COALESCE(NULLIF(exchange_rate, 0), 1) AS fx
               FROM `tabSalary Slip` WHERE docstatus = 1 AND company = %s AND start_date BETWEEN %s AND %s""",
            (ctx.company, start, end),
            as_dict=True,
        )
        comp_kind = {c: k for c in frappe.get_all("Salary Component", pluck="name") if (k := rules.match_kind(c, rules.SALARY_COMPONENT_PATTERNS)) in KINDS}
        deds: Dict[str, Dict[str, float]] = {}
        if comp_kind and slips:
            for d in frappe.db.sql(
                """SELECT sd.parent, sd.salary_component, sd.amount FROM `tabSalary Detail` sd
                   WHERE sd.parenttype = 'Salary Slip' AND sd.parentfield = 'deductions' AND COALESCE(sd.statistical_component, 0) = 0
                     AND sd.parent IN %s AND sd.salary_component IN %s""",
                (tuple(s["name"] for s in slips), tuple(comp_kind)),
                as_dict=True,
            ):
                by = deds.setdefault(d["parent"], {})
                by[comp_kind[d["salary_component"]]] = by.get(comp_kind[d["salary_component"]], 0.0) + float(d["amount"] or 0)
        pin_col, res_col = _employee_cols()
        cols = [c for c in (pin_col, res_col) if c]
        emp_info = {}
        if cols:
            latest_emps = [s["employee"] for s in slips if s["start_date"] >= month]
            emp_info = {e["name"]: e for e in frappe.get_all("Employee", filters={"name": ["in", latest_emps]}, fields=["name", *cols])}
        trend: Dict[str, Dict[str, float]] = {}
        rows: List[Dict[str, Any]] = []
        prev_paye: Dict[str, float] = {}
        prev_month = rules.add_months(month, -1)
        for s in slips:
            fx = float(s["fx"])
            d = deds.get(s["name"], {})
            r = {k: d.get(k, 0.0) * fx for k in KINDS}
            m = s["start_date"].replace(day=1)
            t = trend.setdefault(month_key(m), dict.fromkeys(("paye", "nssf", "shif", "ahl"), 0.0))
            for k in t:
                t[k] += r[k]
            if m == prev_month:
                prev_paye[s["employee"]] = prev_paye.get(s["employee"], 0.0) + r["paye"]
            if m == month:
                info = emp_info.get(s["employee"], {})
                r.update(
                    slip=s["name"], employee=s["employee"], employee_name=s["employee_name"], gross=float(s["gross"] or 0),
                    nonres=is_non_resident(res_col, info.get(res_col)) if res_col else None,
                    pin=(info.get(pin_col) or "").strip() if pin_col else None,
                )
                rows.append(enrich(r, end))
        data = {
            "month": month, "end": end, "rows": rows, "trend": trend, "prev_paye": prev_paye, "kinds": set(comp_kind.values()),
            "has_pin": bool(pin_col), "has_res": bool(res_col),
        }
    ctx._cache["payroll"] = data
    return data


# --------------------------------------------------------------------------- compute
def compute(ctx: TaxContext) -> Dict[str, Any]:
    if not ctx.company:
        return unavailable(_("Set a default Company to see payroll taxes"))
    if not doctype_exists("Salary Slip"):
        return unavailable(_("Install HRMS (Salary Slip) to see payroll taxes"))
    d = _load(ctx)
    if not d:
        return unavailable(_("No submitted Salary Slips yet"))

    rows, kinds, month, end = d["rows"], d["kinds"], d["month"], d["end"]
    n = len({r["employee"] for r in rows})
    gross = sum(r["gross"] for r in rows)
    tot = {k: (sum(r[k] for r in rows) if k in kinds else None) for k in ("paye", "nssf", "shif", "ahl")}
    nssf_both = tot["nssf"] * 2 if tot["nssf"] is not None else None  # ponytail: employer NSSF mirrors employee
    ahl_both = tot["ahl"] * 2 if tot["ahl"] is not None else None  # ponytail: employer AHL mirrors employee
    nita = rules.NITA_PER_EMPLOYEE * n
    nonres = sum(1 for r in rows if r["nonres"]) if d["has_res"] else None
    lel, uel = rules.nssf_limits(end)
    floor_n = sum(1 for r in rows if r["gross"] * rules.SHIF_RATE < rules.SHIF_MIN)

    def missing(k, label):
        return "" if k in kinds else _("No {0} salary component found").format(label)

    # remittance schedule
    due = rules.monthly_due_dates(end, holidays(ctx))
    paid_from = end + timedelta(days=1)
    ninth, ahl_rule = _("9th of next month"), _("{0} working days after month end").format(rules.AHL_WORKING_DAYS)
    sched_def = (
        ("PAYE + P10 monthly", "paye", ninth, tot["paye"]),
        ("NSSF", "nssf", ninth, nssf_both),
        ("SHIF", "shif", _("9th of next month (assumed)"), tot["shif"]),
        ("NITA", "nita", ninth, nita),
        ("Housing levy", "ahl", ahl_rule, ahl_both),
    )
    schedule = []
    for label, k, rule, amount in sched_def:
        paid = gl_debit(ctx, tax_accounts(ctx, k), paid_from, ctx.today)
        schedule.append({"remittance": label, "rule": rule, "due_date": due[k].isoformat(), "amount": amount,
                         "chip": remit_chip(due[k], ctx.today, amount, paid), "key": k})
    pending = [s for s in schedule if s["chip"]["tone"] != "pos"]
    if pending:
        d0 = min(s["due_date"] for s in pending)
        same = [s for s in pending if s["due_date"] == d0]
        amts = [s["amount"] for s in same if s["amount"] is not None]
        due_kpi = kpi(
            "remittance_due", f"Remittance due {int(d0[8:])} {date.fromisoformat(d0):%b}", sum(amts) if amts else None, "money",
            " · ".join(s["key"].upper() for s in same), "bad" if d0 < ctx.today.isoformat() else "warn",
        )
    else:
        due_kpi = kpi("remittance_due", "Remittance due", None, "money", _("Payment traced for every component"), "good")
    for s in schedule:
        del s["key"]

    # exceptions
    found = find_exceptions(rows, d["prev_paye"], kinds, d["has_pin"], d["has_res"])
    prev_label = f"{rules.add_months(month, -1):%b}"
    spec = (
        ("payroll_nssf_mismatch", _("NSSF differs from Year {0} table").format(nssf_year(end)), "money"),
        ("payroll_shif_mismatch", _("SHIF differs from 2.75% (KES 300 minimum)"), "money"),
        ("payroll_ahl_mismatch", _("Housing levy differs from 1.5%"), "money"),
        ("payroll_relief_nonresident", _("Personal relief applied to non-resident"), "money"),
        ("payroll_missing_pin", _("Missing KRA PIN"), "P10 rejects line"),
        ("payroll_paye_movement", _("PAYE moved more than 5% vs {0}").format(prev_label), None),
    )
    exceptions = []
    for metric, label, impact in spec:
        hits = found.get(metric)
        if hits:
            money = sum(abs(h["difference"]) for h in hits) if impact == "money" else impact
            exceptions.append({"check": label, "employees": len({h["employee"] for h in hits}), "impact": money,
                               "drill": {"metric": metric, "filters": {}}})

    monthly = []
    for m in month_starts(month, 12):
        t = d["trend"].get(month_key(m))
        other = None if not t or not (kinds & _MISMATCH) else 2 * t["nssf"] + t["shif"] + 2 * t["ahl"]
        monthly.append({"month": month_key(m), "paye": t["paye"] if t and "paye" in kinds else None, "other": other})

    cost = [
        {"label": "PAYE", "amount": tot["paye"]},
        {"label": "NSSF employer + employee", "amount": nssf_both},
        {"label": "Housing levy", "amount": ahl_both},
        {"label": "SHIF", "amount": tot["shif"]},
        {"label": f"NITA (KES {rules.NITA_PER_EMPLOYEE:,.0f} x {n})", "amount": nita},
    ]
    k_gross = kpi(
        "gross_payroll", f"Gross payroll, {month:%b}", gross, "money",
        _("{0} employees · {1} non-resident").format(n, nonres) if nonres is not None else _("{0} employees · residency not tracked").format(n),
    )
    k_gross["drill"] = {"metric": "payroll_slips", "filters": {}}
    return {
        "available": True,
        "month": month_key(month),
        "kpis": [
            k_gross,
            kpi("paye", "PAYE", tot["paye"], "money", _("Effective rate {0:.1f}% of gross").format(tot["paye"] / gross * 100) if tot["paye"] is not None and gross else missing("paye", "PAYE")),
            kpi("nssf", "NSSF (EE + ER)", nssf_both, "money", _("Year {0} · LEL {1:,.0f} · UEL {2:,.0f}").format(nssf_year(end), lel, uel) if "nssf" in kinds else missing("nssf", "NSSF")),
            kpi("shif", "SHIF 2.75%", tot["shif"], "money", _("{0} employees on the KES 300 floor").format(floor_n) if "shif" in kinds else missing("shif", "SHIF")),
            kpi("ahl", "Housing levy (EE + ER)", ahl_both, "money", _("1.5% + 1.5% of gross") if "ahl" in kinds else missing("ahl", "housing levy")),
            due_kpi,
        ],
        "monthly": monthly,
        "bands": band_headcount([r["exp"]["taxable"] for r in rows]),
        "schedule": schedule,
        "cost": cost,
        "exceptions": exceptions,
    }


# --------------------------------------------------------------------------- drill-down
_EMP = [
    {"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee"},
    {"label": "Name", "fieldname": "employee_name", "fieldtype": "Data"},
    {"label": "Salary Slip", "fieldname": "slip", "fieldtype": "Link", "options": "Salary Slip"},
    {"label": "Gross", "fieldname": "gross", "fieldtype": "Currency"},
]
_CHECK_COLS = _EMP + [
    {"label": "On slip", "fieldname": "actual", "fieldtype": "Currency"},
    {"label": "Expected / previous", "fieldname": "expected", "fieldtype": "Currency"},
    {"label": "Difference", "fieldname": "difference", "fieldtype": "Currency"},
]
_SLIP_COLS = _EMP + [{"label": k.upper(), "fieldname": k, "fieldtype": "Currency"} for k in ("paye", "nssf", "shif", "ahl")]


def _project(rows: List[Dict[str, Any]], cols: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{c["fieldname"]: r.get(c["fieldname"]) for c in cols} for r in rows]


def drilldown(ctx: TaxContext, metric: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not metric.startswith("payroll_"):
        return None
    if metric != "payroll_slips" and metric not in {f"payroll_{k}_mismatch" for k in _MISMATCH} | {"payroll_relief_nonresident", "payroll_missing_pin", "payroll_paye_movement"}:
        return None
    frappe.has_permission("Salary Slip", throw=True)
    d = _load(ctx) if ctx.company and doctype_exists("Salary Slip") else None
    if not d:
        return drill_page(_CHECK_COLS, [], filters)
    if metric == "payroll_slips":
        return drill_page(_SLIP_COLS, _project(d["rows"], _SLIP_COLS), filters)
    found = find_exceptions(d["rows"], d["prev_paye"], d["kinds"], d["has_pin"], d["has_res"])
    return drill_page(_CHECK_COLS, _project(found.get(metric, []), _CHECK_COLS), filters)
