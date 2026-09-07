"""
HR Intelligence Module.

Pure-Ibis rewrite of the HR surface. Every aggregate compiles to one SQL
statement and runs inside MariaDB; the Python process only materialises
the final, already-aggregated result (a handful of rows in the worst case).

Source doctypes (HRMS app):
    Employee           - headcount, attrition, dept composition
    Salary Slip        - payroll aggregates (may be empty on sites without
                         a payroll cycle; every payroll function is written
                         so the empty result is a valid zero, not an
                         exception)
    Attendance         - present/absent/late aggregates
    Leave Application  - leave volume

Sites without HRMS installed (no Employee table) raise a clean error from
the API layer, not a stack trace -- HR is opt-in for ERPNext deployments
that don't run payroll in-house.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    pass  # no pandas / numpy / sklearn in this rewrite

import frappe
from frappe.defaults import get_user_default
from frappe.utils import add_months

from insights.api.ml.ibis_source import t

# ────────────────────────────────────────────────────────────────────────────
# Module helpers
# ────────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now().isoformat()


def _rows(expr) -> List[Dict[str, Any]]:
    """Execute a small Ibis aggregate and return list-of-dict rows."""
    df = expr.execute()
    if df is None or len(df) == 0:
        return []
    return [
        {k: (None if v is None else v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def _scalar(expr, default: float = 0.0):
    df = expr.execute()
    if df is None or len(df) == 0:
        return default
    v = df.iloc[0, 0]
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _period_start_date(period: str, company: str | None = None) -> date:
    """Resolve a period keyword, or the start of an encoded custom range
    (see `insights.api.ml.utils.parse_custom_range`), to a ``date``. ``YTD``
    resolves to the company's fiscal year start (e.g. April 1 for an
    Apr-Mar fiscal year, via `financial_intelligence._fiscal_year_for`) --
    not the calendar year. Every other "YTD" consumer in this codebase
    (Financial/Tax/Strategic Finance) already means fiscal year; this one
    silently meant calendar year until fixed, which is why HR's own YTD
    figures and every Executive KPI routed through `_resolve_date_filter`
    understated the window whenever the fiscal year starts before Jan 1
    of the current calendar year (e.g. an Apr-Mar fiscal year in Q1)."""
    from insights.api.ml.utils import parse_custom_range

    custom = parse_custom_range(period)
    if custom:
        return custom[0].date()
    today = date.today()
    if period == "MTD":
        return today.replace(day=1)
    if period == "QTD":
        quarter_start = ((today.month - 1) // 3) * 3 + 1
        return today.replace(month=quarter_start, day=1)
    if period == "YTD":
        from insights.api.ml.ibis_source import default_company
        from insights.ml.financial_intelligence import _fiscal_year_for

        fy = _fiscal_year_for(company or default_company() or "")
        return datetime.strptime(fy["start_date"], "%Y-%m-%d").date()
    # TTM
    end = today
    return add_months(end.strftime("%Y-%m-%d"), -12) if isinstance(end, date) else add_months(str(end), -12)


def _period_end_date(period: str) -> date:
    """End date paired with `_period_start_date`: today, unless `period` is
    an encoded custom range, in which case its own end. Every HR query
    genuinely enforces this as an upper bound (``.between(from_date,
    to_date)``), unlike Marketing's, which are start-bounded only -- see
    the comment on `marketing_intelligence._period_start_date`."""
    from insights.api.ml.utils import parse_custom_range

    custom = parse_custom_range(period)
    return custom[1].date() if custom else date.today()


def _base_currency(company: Optional[str]) -> str:
    if company:
        cur = frappe.db.get_value("Company", company, "default_currency")
        if cur:
            return cur
    return (
        frappe.db.get_single_value("Global Defaults", "default_currency")
        or "USD"
    )


def _median(values: List[float]) -> float:
    """Plain-Python median. Operates on a list of at most a few hundred
    per-department averages, so no numpy needed."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 0:
        return (s[n // 2 - 1] + s[n // 2]) / 2
    return s[n // 2]


def _variance(values: List[float]) -> float:
    """Plain-Python variance (population)."""
    if not values:
        return 0.0
    m = sum(values) / len(values)
    return sum((v - m) ** 2 for v in values) / len(values)


def _shannon_normalised(counts: List[int]) -> float:
    """Shannon diversity index normalised to 0-100, matching the
    pre-existing formula the frontend expects."""
    total = sum(counts)
    if not counts or total == 0 or len(counts) < 2:
        return 0
    import math

    proportions = [c / total for c in counts if c > 0]
    diversity = -sum(p * math.log2(p) for p in proportions)
    max_div = math.log2(len(counts))
    return round((diversity / max_div * 100), 1) if max_div > 0 else 0


# ────────────────────────────────────────────────────────────────────────────
# HRIntelligence class
# ────────────────────────────────────────────────────────────────────────────


class HRIntelligence:
    """Pure-Ibis HR analytics. No training, no caching, no background job."""

    def __init__(self, period: str = "YTD"):
        self.model_name = "HRIntelligence"
        self.period = period
        self.company = (
            get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        self.company = str(self.company) if self.company else None
        self.from_date = _period_start_date(period, self.company)
        self.to_date = _period_end_date(period)
        self.base_currency = _base_currency(self.company)

    # ------------------------------------------------------------------ train
    def train(self) -> Dict[str, Any]:
        """Generate the full HR overview payload. The Vue dashboard reads
        every top-level key below, so the shape must match exactly."""
        return {
            "status": "success",
            "period": self.period,
            "generated_at": _now_iso(),
            "company": self.company,
            "base_currency": self.base_currency,
            "headcount_metrics": self._analyze_headcount(),
            "attrition_metrics": self._analyze_attrition(),
            "payroll_metrics": self._analyze_payroll(),
            "attendance_metrics": self._analyze_attendance(),
            "leave_metrics": self._analyze_leave(),
            "workforce_composition": self._analyze_workforce_composition(),
            "department_health": self._analyze_department_health(),
            "compensation_analysis": self._analyze_compensation(),
            "engagement_indicators": self._analyze_engagement(),
            "attrition_risk": self._predict_attrition_risk(),
            "hiring_forecast": self._forecast_hiring_needs(),
            "recommendations": self._generate_hr_recommendations(),
        }

    def predict(self) -> Dict[str, Any]:
        """Backward-compat alias for callers that expect a sklearn-style
        ``predict()``. The endpoint has no real "model" to predict with --
        every call computes fresh, so this is the same dict as ``train``."""
        return self.train()

    def get_hr_overview(self, period: str = "YTD") -> Dict[str, Any]:
        """Instance-method form of the module-level ``get_hr_overview``
        wrapper. Used by ``HRIntelligenceAgent`` (``agents/hr_agent.py``)
        and ``ExecutiveIntelligence`` (``ml/executive_intelligence.py``),
        which instantiate ``HRIntelligence()`` and call this on the
        instance. Re-instantiates with the requested ``period`` so a
        caller holding an instance built with one window can ask for
        another without rebuilding the object themselves."""
        if period == self.period:
            return self.train()
        return HRIntelligence(period=period).train()

    # ------------------------------------------------------------------ helpers
    def _compressed_corpora(self) -> Dict[str, Any]:
        """Pre-aggregate everything once and reuse across the slices.

        Saves a handful of round-trips when the dashboard hits six tabs
        of analytics in one render. Returns plain dicts of scalars /
        per-row aggregates that downstream methods consume.
        """
        employee = t("Employee")
        emp_active = employee.filter(employee["status"] == "Active")

        # Headcount snapshot
        total_active = _scalar(emp_active.aggregate(n=emp_active.count()))

        # Period hires (any status, with date_of_joining in the window).
        # Use a bound intermediate so the count belongs to the filtered
        # relation; referencing the original `employee` after `.filter()`
        # triggers the documented "belong to another relation" IntegrityError.
        emp_hires = employee.filter(
            employee["date_of_joining"].between(
                str(self.from_date), str(self.to_date)
            )
        )
        new_hires = _scalar(emp_hires.aggregate(n=emp_hires.count()))

        # Period exits (any status, with relieving_date in the window).
        # Same gotcha as above: bind the filtered table to a local so the
        # count and sum belong to that relation.
        emp_exits = employee.filter(
            employee["relieving_date"].between(
                str(self.from_date), str(self.to_date)
            )
        )
        exits_df = (
            emp_exits
            .aggregate(
                total=emp_exits.count(),
                voluntary=(
                    emp_exits["resignation_letter_date"].notnull().cast("int").sum()
                ),
            )
            .execute()
        )
        total_exits = 0
        voluntary_exits = 0
        if exits_df is not None and len(exits_df):
            total_exits = int(exits_df.iloc[0].get("total") or 0)
            voluntary_exits = int(exits_df.iloc[0].get("voluntary") or 0)

        # Department composition (active only).
        # Ibis gotcha: count must reference the filtered+grouped relation,
        # not the original `employee` table, or you get the
        # "belong to another relation" IntegrityError. Bind to a local.
        #
        # Include unassigned (NULL/empty department) as an explicit
        # "(Unassigned)" bucket so the breakdown reconciles with the
        # active headcount. Previously these were silently dropped: the
        # dashboard's `department_count` and per-department totals summed
        # to fewer than `total_employees`, leaving the breakdown card
        # unable to explain where 3 of every 10 active employees went.
        emp_active_dept = emp_active.mutate(
            _dept=(
                ibis.cases(
                    (employee["department"].isnull(), "(Unassigned)"),
                    (employee["department"] == "", "(Unassigned)"),
                    else_=employee["department"],
                )
            )
        )
        dept_df = (
            emp_active_dept
            .group_by(emp_active_dept["_dept"].name("department"))
            .aggregate(count=emp_active_dept.count())
            .order_by(ibis.desc("count"))
            .execute()
        )
        dept_breakdown = []
        if dept_df is not None and len(dept_df):
            for _, r in dept_df.iterrows():
                dept_breakdown.append({
                    "department": r.get("department"),
                    "count": int(r.get("count") or 0),
                })

        # Employment type composition (active only).
        # Same NULL/empty handling: bucket as "(Unassigned)" so the
        # breakdown reconciles with the active headcount.
        emp_active_emptype = emp_active.mutate(
            _etype=(
                ibis.cases(
                    (employee["employment_type"].isnull(), "(Unassigned)"),
                    (employee["employment_type"] == "", "(Unassigned)"),
                    else_=employee["employment_type"],
                )
            )
        )
        emptype_df = (
            emp_active_emptype
            .group_by(emp_active_emptype["_etype"].name("employment_type"))
            .aggregate(count=emp_active_emptype.count())
            .execute()
        )
        emp_type_breakdown = []
        if emptype_df is not None and len(emptype_df):
            for _, r in emptype_df.iterrows():
                emp_type_breakdown.append({
                    "employment_type": r.get("employment_type"),
                    "count": int(r.get("count") or 0),
                })

        # Gender composition (active only).
        # Same NULL/empty handling: bucket as "(Unspecified)" so the
        # breakdown reconciles with the active headcount.
        emp_active_gender = emp_active.mutate(
            _gender=(
                ibis.cases(
                    (employee["gender"].isnull(), "(Unspecified)"),
                    (employee["gender"] == "", "(Unspecified)"),
                    else_=employee["gender"],
                )
            )
        )
        gender_df = (
            emp_active_gender
            .group_by(emp_active_gender["_gender"].name("gender"))
            .aggregate(count=emp_active_gender.count())
            .execute()
        )
        gender_dist = []
        if gender_df is not None and len(gender_df):
            for _, r in gender_df.iterrows():
                gender_dist.append({
                    "gender": r.get("gender"),
                    "count": int(r.get("count") or 0),
                })

        return {
            "total_active": int(total_active),
            "new_hires": int(new_hires),
            "total_exits": total_exits,
            "voluntary_exits": voluntary_exits,
            "involuntary_exits": max(0, total_exits - voluntary_exits),
            "department_breakdown": dept_breakdown,
            "employment_type_breakdown": emp_type_breakdown,
            "gender_dist": gender_dist,
        }

    # ------------------------------------------------------------------ headcount
    def _analyze_headcount(self) -> Dict[str, Any]:
        c = self._compressed_corpora()
        total_active = c["total_active"]
        new_hires = c["new_hires"]
        exits = c["total_exits"]
        net_change = new_hires - exits

        growth_rate = (net_change / total_active * 100) if total_active else 0
        # Note: `turnover_rate_pct` here uses the *active* headcount
        # denominator (snapshot of currently-employed). `attrition_metrics
        # .attrition_rate_pct` uses the *all* Employee denominator. Both
        # formulas are legitimate (one is a snapshot, the other is a
        # full-population rate) but the dashboard surfaces both side-by-
        # side, so the difference can look like a bug. The Headcount tab
        # does not display this field today; it's only here for callers
        # that asked for a "headcount turnover" specifically.
        turnover_rate = (exits / total_active * 100) if total_active else 0
        hire_rate = (new_hires / total_active * 100) if total_active else 0

        dept = c["department_breakdown"]
        largest_dept = dept[0] if dept else {}
        smallest_dept = dept[-1] if dept else {}

        return {
            "total_employees": total_active,
            "new_hires": new_hires,
            "exits": exits,
            "net_growth": net_change,
            "growth_rate_pct": round(growth_rate, 2),
            "turnover_rate_pct": round(turnover_rate, 2),
            "hire_rate_pct": round(hire_rate, 2),
            "largest_department": largest_dept.get("department") or "N/A",
            "smallest_department": smallest_dept.get("department") or "N/A",
            "department_count": len(dept),
            "headcount_health": "healthy" if growth_rate >= 0 and turnover_rate < 15 else "needs_attention",
        }

    # ------------------------------------------------------------------ attrition
    def _analyze_attrition(self) -> Dict[str, Any]:
        c = self._compressed_corpora()
        total_exits = c["total_exits"]
        voluntary_exits = c["voluntary_exits"]
        involuntary_exits = c["involuntary_exits"]

        # Attrition rate denominator is total employees, not just active
        # (industry-standard formula: exits / average headcount). The
        # site has 26 employees, so use the snapshot total.
        employee = t("Employee")
        total_employees = _scalar(employee.aggregate(n=employee.count()))
        attrition_rate = (total_exits / total_employees * 100) if total_employees else 0

        voluntary_rate = (voluntary_exits / total_exits * 100) if total_exits else 0
        involuntary_rate = (involuntary_exits / total_exits * 100) if total_exits else 0

        attrition_risk = "low"
        if attrition_rate > 20:
            attrition_risk = "high"
        elif attrition_rate > 12:
            attrition_risk = "medium"

        return {
            "attrition_rate_pct": round(attrition_rate, 2),
            "total_exits": total_exits,
            "voluntary_exits": voluntary_exits,
            "involuntary_exits": involuntary_exits,
            "voluntary_rate_pct": round(voluntary_rate, 2),
            "involuntary_rate_pct": round(involuntary_rate, 2),
            "attrition_risk_level": attrition_risk,
            "benchmark_comparison": "above_average" if attrition_rate > 15 else "below_average",
        }

    # ------------------------------------------------------------------ payroll
    def _analyze_payroll(self) -> Dict[str, Any]:
        """Payroll aggregates over Salary Slip. Returns zeroed-out structure
        on sites with no payroll cycle (Salary Slip table empty)."""
        if not frappe.db.table_exists("Salary Slip"):
            return {
                "total_payroll_cost": 0,
                "average_salary": 0,
                "cost_per_employee": 0,
                "employees_on_payroll": 0,
                "deduction_rate_pct": 0,
                "payroll_efficiency": "no_data",
                "payroll_data_note": "Salary Slip table not available on this site",
            }

        ss = t("Salary Slip")
        ss_period = ss.filter(
            (ss["docstatus"] == 1)
            & (ss["start_date"] <= str(self.to_date))
            & (ss["end_date"] >= str(self.from_date))
        )

        # Single aggregate for the totals row
        # Single aggregate for the totals row. References must point at
        # `ss_period`, the filtered table, not the original `ss`.
        totals_df = (
            ss_period.aggregate(
                total_gross=ss_period["gross_pay"].sum(),
                total_deductions=ss_period["total_deduction"].sum(),
                total_net=ss_period["net_pay"].sum(),
                avg_gross=ss_period["gross_pay"].mean(),
                employees_paid=ss_period["employee"].nunique(),
            ).execute()
        )

        if totals_df is None or not len(totals_df):
            return {
                "total_payroll_cost": 0,
                "average_salary": 0,
                "cost_per_employee": 0,
                "employees_on_payroll": 0,
                "deduction_rate_pct": 0,
                "payroll_efficiency": "no_data",
                "payroll_data_note": "No Salary Slip records in this period",
            }

        r = totals_df.iloc[0]
        total_gross = float(r.get("total_gross") or 0)

        total_net = float(r.get("total_net") or 0)
        avg_gross = float(r.get("avg_gross") or 0)
        employees_paid = int(r.get("employees_paid") or 0)

        # A non-grouped aggregate always returns exactly one row from SQL
        # (SUM/AVG NULL, COUNT(DISTINCT) 0) even when `ss_period` matched
        # zero Salary Slips -- so `len(totals_df)` above is always 1 and
        # never catches this case. Check the actual row count via
        # `employees_paid` instead; without this, a site with no payroll
        # data for the period silently falls through to the "success"
        # return below with every figure coerced to 0 by `or 0`, reporting
        # `payroll_efficiency: "optimal"` for a company with no payroll
        # cycle at all instead of the honest no_data branch.
        if employees_paid == 0:
            return {
                "total_payroll_cost": 0,
                "average_salary": 0,
                "cost_per_employee": 0,
                "employees_on_payroll": 0,
                "deduction_rate_pct": 0,
                "payroll_efficiency": "no_data",
                "payroll_data_note": "No Salary Slip records in this period",
            }

        # Department breakdown via Employee join
        dept_payroll_df = (
            ss_period
            .join(t("Employee"), ss_period["employee"] == t("Employee")["name"])
            .filter(t("Employee")["department"].notnull() & (t("Employee")["department"] != ""))
            .group_by(t("Employee")["department"].name("department"))
            .aggregate(
                total_cost=ss_period["gross_pay"].sum(),
                avg_cost=ss_period["gross_pay"].mean(),
                employee_count=ss_period["employee"].nunique(),
            )
            .order_by(ibis.desc("total_cost"))
            .execute()
        )
        dept_payroll = []
        if dept_payroll_df is not None and len(dept_payroll_df):
            for _, row in dept_payroll_df.iterrows():
                dept_payroll.append({
                    "department": row.get("department"),
                    "total_cost": float(row.get("total_cost") or 0),
                    "avg_cost": float(row.get("avg_cost") or 0),
                    "employee_count": int(row.get("employee_count") or 0),
                })

        cost_per_employee = total_gross / employees_paid if employees_paid else 0
        deduction_rate = (
            (total_gross - total_net) / total_gross * 100
            if total_gross
            else 0
        )

        return {
            "total_payroll_cost": total_gross,
            "average_salary": avg_gross,
            "cost_per_employee": cost_per_employee,
            "employees_on_payroll": employees_paid,
            "deduction_rate_pct": round(deduction_rate, 2),
            "payroll_efficiency": "optimal" if deduction_rate < 25 else "review_needed",
            "department_breakdown": dept_payroll,
        }

    # ------------------------------------------------------------------ attendance
    def _analyze_attendance(self) -> Dict[str, Any]:
        if not frappe.db.table_exists("Attendance"):
            return {
                "attendance_rate_pct": 0,
                "late_arrivals": 0,
                "total_attendance_records": 0,
                "attendance_health": "no_data",
                "productivity_indicator": "unknown",
                "attendance_data_note": "Attendance table not available on this site",
            }

        att = t("Attendance")
        period_att = att.filter(
            (att["docstatus"] == 1)
            & att["attendance_date"].between(str(self.from_date), str(self.to_date))
        )

        # Ibis gotcha: aggregate metrics must reference the filtered
        # relation (`period_att`), not the original `att` table, or you
        # get the "belong to another relation" IntegrityError.
        #
        # Attendance rate previously counted ONLY `status == "Present"` as
        # attendance -- silently dropping Half Day (0.5) and On Leave
        # (1.0, approved absence) into the "neither present nor absent"
        # bucket. With this site's 7 Half Days and 3 On Leaves, that
        # dropped the reported rate from the true 49.1% to 43.43% for no
        # good reason. Weight statuses now:
        #   Present    -> 1.0  (full day)
        #   Work From Home -> 1.0  (where supported; counted as Present)
        #   Half Day   -> 0.5
        #   On Leave   -> 1.0  (approved absence; not absenteeism)
        #   Absent     -> 0.0
        # `effective_present` sums the weights; `attendance_rate_pct` is
        # that over `total`. The strict "Present only" count is still
        # surfaced as `present_days` for backward compat.
        totals_df = (
            period_att.aggregate(
                total=period_att.count(),
                present_strict=((period_att["status"] == "Present").cast("int").sum()),
                absent=((period_att["status"] == "Absent").cast("int").sum()),
                half_day=((period_att["status"] == "Half Day").cast("int").sum()),
                on_leave=((period_att["status"] == "On Leave").cast("int").sum()),
                work_from_home=((period_att["status"] == "Work From Home").cast("int").sum()),
            ).execute()
        )
        total = 0
        present = 0
        absent = 0
        half_day = 0
        on_leave = 0
        work_from_home = 0
        if totals_df is not None and len(totals_df):
            r = totals_df.iloc[0]
            total = int(r.get("total") or 0)
            present = int(r.get("present_strict") or 0)
            absent = int(r.get("absent") or 0)
            half_day = int(r.get("half_day") or 0)
            on_leave = int(r.get("on_leave") or 0)
            work_from_home = int(r.get("work_from_home") or 0)

        effective_present = (
            present + work_from_home + on_leave + (half_day * 0.5)
        )
        attendance_rate = (effective_present / total * 100) if total else 0

        # Late arrivals from Employee Checkin.
        # Count must reference the filtered relation (see the "belong to
        # another relation" note above), and the time-of-day check is done
        # in Python on the already-filtered count -- the SQL we send to
        # MariaDB is "all IN checkins in the period".
        late_arrivals = 0
        total_checkins = 0
        if frappe.db.table_exists("Employee Checkin"):
            ec = t("Employee Checkin")
            ec_in_period = ec.filter(
                (ec["log_type"] == "IN")
                & ec["time"].between(
                    str(self.from_date), str(self.to_date)
                )
            )
            df_late = ec_in_period.select(
                ec_in_period["time"].name("t")
            ).execute()
            if df_late is not None and len(df_late):
                # Count rows where the time-of-day is after 09:30.
                # `total_checkins` is the same column we used to count
                # `late_arrivals`, so the ratio is meaningful (late IN
                # checkins / all IN checkins in the period) rather than
                # previously dividing by unrelated attendance records.
                total_checkins = len(df_late)
                late_arrivals = int(sum(
                    1 for v in df_late["t"] if v is not None and v.time() > __import__("datetime").time(9, 30)
                ))

        late_arrival_rate = (late_arrivals / total_checkins * 100) if total_checkins else 0

        if attendance_rate < 85:
            health = "poor"
        elif attendance_rate < 92:
            health = "needs_improvement"
        elif attendance_rate < 96:
            health = "good"
        else:
            health = "excellent"
        if attendance_rate > 95:
            productivity = "high"
        elif attendance_rate > 90:
            productivity = "medium"
        else:
            productivity = "low"

        return {
            "attendance_rate_pct": round(attendance_rate, 2),
            "late_arrivals": late_arrivals,
            "late_arrival_rate_pct": round(late_arrival_rate, 2),
            "total_attendance_records": total,
            "total_in_checkins": total_checkins,
            # `present_days` is the strict Present count (back-compat).
            # The weighted effective-present is what `attendance_rate_pct`
            # is computed against -- exposed alongside so the dashboard
            # can show both numbers when they diverge.
            "present_days": present,
            "absent_days": absent,
            "half_day_days": half_day,
            "on_leave_days": on_leave,
            "work_from_home_days": work_from_home,
            "effective_present_days": round(effective_present, 2),
            "attendance_health": health,
            "productivity_indicator": productivity,
        }
    # ------------------------------------------------------------------ leave
    def _analyze_leave(self) -> Dict[str, Any]:
        if not frappe.db.table_exists("Leave Application"):
            return {
                "total_leave_applications": 0,
                "total_leave_days": 0,
                "average_days_per_application": 0,
                "leave_utilization": "no_data",
                "leave_pattern": "no_data",
                "leave_data_note": "Leave Application table not available on this site",
            }

        la = t("Leave Application")
        period_la = la.filter(
            (la["status"] == "Approved")
            & (la["from_date"] <= str(self.to_date))
            & (la["to_date"] >= str(self.from_date))
        )

        # Aggregate must reference the filtered relation.
        totals_df = (
            period_la.aggregate(
                total=period_la.count(),
                total_days=period_la["total_leave_days"].sum(),
                avg_days=period_la["total_leave_days"].mean(),
            ).execute()
        )
        total_apps = 0
        total_days = 0
        avg_days = 0
        if totals_df is not None and len(totals_df):
            r = totals_df.iloc[0]
            total_apps = int(r.get("total") or 0)
            total_days = float(r.get("total_days") or 0)
            avg_days = float(r.get("avg_days") or 0)

        return {
            "total_leave_applications": total_apps,
            "total_leave_days": total_days,
            "average_days_per_application": round(avg_days, 1),
            "leave_utilization": "normal" if avg_days < 5 else "high",
            "leave_pattern": "healthy" if total_apps > 0 else "low_utilization",
        }

    # ------------------------------------------------------------------ composition
    def _analyze_workforce_composition(self) -> Dict[str, Any]:
        c = self._compressed_corpora()
        gender = c["gender_dist"]
        total = sum(g["count"] for g in gender)
        gender_ratios = {
            g["gender"]: round(g["count"] / total * 100, 1) if total else 0
            for g in gender
        }

        return {
            "department_distribution": c["department_breakdown"],
            "employment_type_distribution": c["employment_type_breakdown"],
            "gender_ratios": gender_ratios,
            "diversity_score": _shannon_normalised([g["count"] for g in gender]),
            "composition_balance": "balanced" if len(c["department_breakdown"]) > 3 else "concentrated",
        }

    # ------------------------------------------------------------------ department health
    def _analyze_department_health(self) -> Dict[str, Any]:
        c = self._compressed_corpora()
        dept_hc = {d["department"]: d["count"] for d in c["department_breakdown"]}

        # Department payroll (zeroed on sites with no payroll data)
        payroll = self._analyze_payroll()
        dept_pr = {
            d["department"]: d
            for d in payroll.get("department_breakdown", [])
        }

        merged = {}
        for dept_name, headcount in dept_hc.items():
            pr = dept_pr.get(dept_name, {})
            merged[dept_name] = {
                "headcount": headcount,
                "payroll_cost": float(pr.get("total_cost") or 0),
                "cost_per_employee": float(pr.get("avg_cost") or 0),
            }
        # Include any payroll-only departments (no employees in current list)
        for dept_name, pr in dept_pr.items():
            if dept_name not in merged:
                merged[dept_name] = {
                    "headcount": 0,
                    "payroll_cost": float(pr.get("total_cost") or 0),
                    "cost_per_employee": float(pr.get("avg_cost") or 0),
                }

        if merged:
            highest_cost_dept = max(
                merged.items(), key=lambda kv: kv[1]["payroll_cost"]
            )[0]
            largest_dept = max(
                merged.items(), key=lambda kv: kv[1]["headcount"]
            )[0]
        else:
            highest_cost_dept = "N/A"
            largest_dept = "N/A"

        return {
            "department_metrics": merged,
            "highest_cost_department": highest_cost_dept,
            "largest_department": largest_dept,
            "total_departments": len(merged),
        }

    # ------------------------------------------------------------------ compensation
    def _analyze_compensation(self) -> Dict[str, Any]:
        payroll = self._analyze_payroll()
        dept_payroll = payroll.get("department_breakdown", [])

        if not dept_payroll:
            return {
                "median_salary": 0,
                "salary_variance": 0,
                "highest_paying_dept": "N/A",
                "lowest_paying_dept": "N/A",
                "pay_ratio": 0,
                "pay_equity_status": "no_data",
            }

        all_avg_salaries = [d["avg_cost"] for d in dept_payroll]
        overall_median = _median(all_avg_salaries)
        salary_var = _variance(all_avg_salaries)

        highest_paying = max(dept_payroll, key=lambda d: d["avg_cost"])
        lowest_paying = min(dept_payroll, key=lambda d: d["avg_cost"])
        pay_ratio = (
            highest_paying["avg_cost"] / lowest_paying["avg_cost"]
            if lowest_paying["avg_cost"]
            else 0
        )

        return {
            "median_salary": overall_median,
            "salary_variance": salary_var,
            "highest_paying_dept": highest_paying["department"],
            "lowest_paying_dept": lowest_paying["department"],
            "pay_ratio": round(pay_ratio, 2),
            "pay_equity_status": "good" if pay_ratio < 3 else "needs_review",
        }

    # ------------------------------------------------------------------ engagement
    def _analyze_engagement(self) -> Dict[str, Any]:
        """Engagement score derived from attendance + retention + leave use.

        A transparent weighted formula, fully explained in the comments,
        rather than a learned score -- a BI dashboard shouldn't hide its
        assumptions behind a model.
        """
        att = self._analyze_attendance()
        attr = self._analyze_attrition()
        leave = self._analyze_leave()

        attendance_rate = att.get("attendance_rate_pct", 0)
        attrition_rate = attr.get("attrition_rate_pct", 0)
        leave_pattern = leave.get("average_days_per_application", 0)
        leave_apps_count = leave.get("total_leave_applications", 0)

        # Track the BUCKETED contribution from each dimension so the
        # `key_indicators` breakdown actually sums to `engagement_score`.
        # Previously the breakdown showed the raw underlying metrics
        # (attendance_rate, 100-attrition, leave pattern) which never
        # reconciled with the bucketed score -- a user could read the
        # breakdown and conclude something completely different from the
        # headline score.
        score = 0
        # Attendance contribution (40 pts)
        if attendance_rate > 95:
            score += 40
            attendance_contribution = 40
        elif attendance_rate > 90:
            score += 30
            attendance_contribution = 30
        elif attendance_rate > 85:
            score += 20
            attendance_contribution = 20
        else:
            score += 10
            attendance_contribution = 10

        # Retention contribution (40 pts, inverse)
        if attrition_rate < 5:
            score += 40
            retention_contribution = 40
        elif attrition_rate < 10:
            score += 30
            retention_contribution = 30
        elif attrition_rate < 15:
            score += 20
            retention_contribution = 20
        else:
            score += 10
            retention_contribution = 10

        # Leave pattern contribution (20 pts).
        # Previously the formula `100 - (leave_pattern * 10)` saturated
        # at 100 whenever there were zero leave applications (avg_days=0),
        # which read as "perfect leave pattern" -- but zero leave is the
        # opposite of healthy: people aren't taking time off. Treat the
        # "no leave data" case as neutral (10 pts) rather than top score.
        if leave_apps_count == 0:
            score += 10
            leave_pattern_contribution = 10
        elif leave_pattern < 3:
            score += 20
            leave_pattern_contribution = 20
        elif leave_pattern < 5:
            score += 15
            leave_pattern_contribution = 15
        else:
            score += 10
            leave_pattern_contribution = 10

        if score < 50:
            level = "low"
        elif score < 75:
            level = "medium"
        else:
            level = "high"

        return {
            "engagement_score": score,
            "engagement_level": level,
            # Bucketed contributions -- matches `engagement_score` exactly.
            # Raw per-dimension percentages are still useful for diagnosis
            # and are returned alongside under `_raw` (prefixed with `_`
            # so frontend consumers that only look at the top-level keys
            # are not affected).
            "key_indicators": {
                "attendance_contribution": attendance_contribution,
                "retention_contribution": retention_contribution,
                "leave_pattern_contribution": leave_pattern_contribution,
            },
            "_raw": {
                "attendance_rate_pct": attendance_rate,
                "retention_rate_pct": max(0, 100 - attrition_rate),
                "leave_pattern_days": leave_pattern,
                "leave_applications_count": leave_apps_count,
            },
        }


    # ------------------------------------------------------------------ attrition risk
    def _predict_attrition_risk(self) -> Dict[str, Any]:
        """Transparent risk score: each factor adds a documented weight.
        Not a learned model -- a BI dashboard wants an explainable
        heuristic, not a black box."""
        attr = self._analyze_attrition()
        att = self._analyze_attendance()

        current_attrition = attr.get("attrition_rate_pct", 0)
        attendance_rate = att.get("attendance_rate_pct", 0)

        risk_factors: List[str] = []
        risk_score = 0
        # Make "Critical" a strict superset of "High": when attrition is
        # above 20, only the Critical branch fires (otherwise the same
        # underlying condition was contributing 30+25=55 points from
        # itself and showing up twice in `risk_factors` as both "High"
        # and "Critical" -- misleading). Same idea for attendance vs
        # engagement-style buckets elsewhere.
        if current_attrition > 20:
            risk_factors.append("Critical attrition levels")
            risk_score += 55  # was 30+25 stacked; same single condition
        elif current_attrition > 15:
            risk_factors.append("High current attrition rate")
            risk_score += 30
        if attendance_rate < 90:
            risk_factors.append("Low attendance rate")
            risk_score += 20


        # Apply a heuristic drift to next-period projection: high risk
        # inflates, low risk holds. Linear, no model needed.
        predicted_attrition = current_attrition
        if risk_score > 50:
            predicted_attrition *= 1.2
        elif risk_score > 30:
            predicted_attrition *= 1.1

        if risk_score > 50:
            risk_level = "high"
        elif risk_score > 30:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_level": risk_level,
            "risk_score": risk_score,
            "risk_factors": risk_factors,
            "predicted_attrition_rate": round(predicted_attrition, 2),
            "recommended_actions": self._attrition_recommendations(risk_level),
        }

    @staticmethod
    def _attrition_recommendations(risk_level: str) -> List[str]:
        if risk_level == "high":
            return [
                "Implement immediate retention bonuses",
                "Conduct urgent employee satisfaction survey",
                "Review and improve management practices",
                "Accelerate career development programs",
            ]
        if risk_level == "medium":
            return [
                "Enhance employee engagement initiatives",
                "Review compensation competitiveness",
                "Improve internal communication",
                "Strengthen performance management",
            ]
        return [
            "Maintain current retention strategies",
            "Continue monitoring engagement metrics",
            "Regular check-ins with high performers",
        ]

    # ------------------------------------------------------------------ hiring forecast
    def _forecast_hiring_needs(self) -> Dict[str, Any]:
        hc = self._analyze_headcount()
        attr = self._analyze_attrition()

        current_headcount = hc.get("total_employees", 0)
        net_growth = hc.get("net_growth", 0)
        attrition_rate = attr.get("attrition_rate_pct", 0)

        # Quarterly projection: ((attrition_rate / 4) / 100) * current_headcount
        quarterly_attrition = (attrition_rate / 4) / 100 * current_headcount
        projected_exits = int(quarterly_attrition)
        projected_growth_hires = max(0, int(net_growth))
        total_hiring_need = projected_exits + projected_growth_hires

        return {
            "projected_exits_next_quarter": projected_exits,
            "growth_based_hiring": projected_growth_hires,
            "total_hiring_need": total_hiring_need,
            "hiring_urgency": "high" if total_hiring_need > current_headcount * 0.1 else "normal",
        }

    # ------------------------------------------------------------------ recommendations
    def _generate_hr_recommendations(self) -> List[Dict[str, Any]]:
        attr = self._analyze_attrition()
        att = self._analyze_attendance()
        hc = self._analyze_headcount()

        recs: List[Dict[str, Any]] = []
        if attr.get("attrition_rate_pct", 0) > 15:
            recs.append({
                "priority": "high",
                "category": "Retention",
                "title": "Address High Attrition Rate",
                "description": f"Current attrition rate of {attr.get('attrition_rate_pct', 0)}% is above industry average.",
                "actions": ["Conduct exit interviews", "Review compensation", "Improve management training"],
            })
        if att.get("attendance_rate_pct", 0) < 92 and att.get("attendance_rate_pct", 0) > 0:
            recs.append({
                "priority": "medium",
                "category": "Engagement",
                "title": "Improve Attendance Rates",
                "description": f"Attendance rate of {att.get('attendance_rate_pct', 0)}% indicates engagement issues.",
                "actions": ["Review attendance policy", "Address work-life balance", "Implement flexible working"],
            })
        if hc.get("net_growth", 0) < 0:
            recs.append({
                "priority": "medium",
                "category": "Growth",
                "title": "Address Negative Headcount Growth",
                "description": "Net headcount reduction may impact business growth.",
                "actions": ["Accelerate hiring", "Improve retention", "Review workforce planning"],
            })
        return recs

    # ------------------------------------------------------------------ chat
    def _compress_for_chat(self) -> Dict[str, Any]:
        """Smaller payload for the chat agent. Same numbers, fewer keys."""
        return {
            "headcount_metrics": self._analyze_headcount(),
            "attrition_metrics": self._analyze_attrition(),
            "payroll_metrics": self._analyze_payroll(),
            "attendance_metrics": self._analyze_attendance(),
            "engagement_indicators": self._analyze_engagement(),
            "workforce_composition": self._analyze_workforce_composition(),
            "department_health": self._analyze_department_health(),
            "compensation_analysis": self._analyze_compensation(),
            "hiring_forecast": self._forecast_hiring_needs(),
            "recommendations": self._generate_hr_recommendations(),
            "period": self.period,
        }


# ────────────────────────────────────────────────────────────────────────────
# Backward-compatible module-level API functions
# ────────────────────────────────────────────────────────────────────────────


def get_hr_overview(period: str = "YTD") -> Dict[str, Any]:
    """Module-level convenience wrapper matching the old API."""
    return HRIntelligence(period=period).train()


def get_headcount_analytics(period: str = "YTD") -> Dict[str, Any]:
    return HRIntelligence(period=period)._analyze_headcount()


def get_attrition_prediction() -> Dict[str, Any]:
    return HRIntelligence(period="TTM")._predict_attrition_risk()


def get_hr_recommendations() -> List[Dict[str, Any]]:
    return HRIntelligence(period="YTD")._generate_hr_recommendations()


# `update_hr_intelligence` is the scheduler entry point that the central
# hooks call on a daily cron. With the ML layer gone (no cache, no
# background job), this is a no-op kept for forward compatibility.
def update_hr_intelligence() -> Dict[str, Any]:
    """No-op stub.

    The pre-rewrite scheduler filled a 24h Redis cache here; with the ML
    layer gone (every endpoint computes fresh in-request), there is
    nothing to pre-compute. Kept so the existing scheduler entry point
    in ``hooks.py`` continues to resolve.
    """
    return {"status": "no_op", "message": "HR intelligence is computed on demand; no scheduled warm-up needed."}


# `ibis` is imported at module bottom so the `desc` helper used in the
# ranking/order_by clauses above is resolvable. We only use ibis for
# pure desc, so the import is local to keep the public surface small.
import ibis
