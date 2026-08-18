# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Executive Intelligence API endpoints.

Thin whitelisted wrappers around the pure-Ibis rollup in
``insights.ml.executive_intelligence``. Every endpoint:

1. Gates on ``frappe.has_permission(<doctype>, "read", throw=True)``
   before any data access. Per-department endpoints gate on the doctype
   the requested department actually exposes (see ``_DEPARTMENT_DOCTYPE``
   below) so a Sales-only user cannot pass department="hr" and read
   payroll data.
2. Computes the rollup synchronously via Ibis aggregates (no cache,
   no background job, no ``compute_or_cache``). The rollup is the same
   pure-Ibis function the dashboard already calls; nothing here does
   pandas or sklearn work.
3. Returns the standard ``{"status": "success", "data": ...}`` envelope
   on success, or ``{"status": "error", "message": ...}`` on a non-
   permission failure. ``frappe.PermissionError`` is re-raised so
   Frappe's own auth layer returns 403.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from insights.api.response import error, success

# Each department's rollup surfaces a different doctype's data. The
# frontend selects via ``department=``; this map is the one place that
# needs to know which doctype guards which domain's read.
_DEPARTMENT_DOCTYPE = {
    "financial": "GL Entry",
    "sales": "Sales Invoice",
    "customer": "Customer",
    "operations": "Purchase Order",
    "risk": "Sales Invoice",
    "hr": "Salary Slip",
    "manufacturing": "Work Order",
    "marketing": "Lead",
}


def _permitted_departments(user: Optional[str] = None) -> set:
    """Departments (see ``_DEPARTMENT_DOCTYPE``) the current user can read.

    The rollup fans out to every domain in one response; gating the whole
    endpoint on a single doctype (the bug this replaces) let a user with
    only Sales Invoice read access pull HR/financial/manufacturing figures
    too. Checked non-throwing per doctype so the caller gets the *subset*
    they can see rather than an all-or-nothing 403.
    """
    return {
        dept
        for dept, doctype in _DEPARTMENT_DOCTYPE.items()
        if frappe.has_permission(doctype, "read", user=user)
    }


def _scoped_rollup(rollup: Dict[str, Any], permitted: set) -> Dict[str, Any]:
    """Redact the cross-domain rollup down to what ``permitted`` can see.

    ``kpis``/``alerts`` are per-department and filterable in place.
    ``business_health_score``/``trends``/``narrative`` are composites
    computed across *every* domain (see ``_business_health_score`` /
    ``_trend_sparklines`` / ``_narrative`` in ``executive_intelligence.py``)
    -- a partial-access user shown a blended composite could infer roughly
    what the hidden departments' numbers are from how the composite moves,
    so those are omitted rather than exposed in some "sanitized" form,
    unless the caller can read every department.
    """
    kpis = rollup.get("kpis", {}) or {}
    scoped_kpis = {k: v for k, v in kpis.items() if k in permitted}
    alerts = rollup.get("alerts", []) or []
    scoped_alerts = [a for a in alerts if a.get("department", "").lower() in permitted]
    out = dict(rollup)
    out["kpis"] = scoped_kpis
    out["alerts"] = scoped_alerts
    if not set(_DEPARTMENT_DOCTYPE) <= permitted:
        out["business_health_score"] = None
        out["trends"] = None
        out["narrative"] = None
        out["restricted_note"] = _(
            "Business health score, trends, and narrative are composites across "
            "every department and are only shown to users with read access to "
            "all of them. You have access to: {0}."
        ).format(", ".join(sorted(scoped_kpis)) or "none")
    return out


def _require_any_department(permitted: set) -> None:
    """Raise the standard 403 if the caller cannot read any department."""
    if not permitted:
        frappe.has_permission("Sales Invoice", "read", throw=True)


# ─── Headline rollup ─────────────────────────────────────────────────────────


@frappe.whitelist()
def get_executive_summary(period: str = "YTD") -> Dict[str, Any]:
    """Return the executive summary rollup, scoped to the caller's departments.

    Reads the same shape the ``ExecutiveDashboard.vue`` consumes:
    ``business_health_score``, ``alerts``, ``kpis.<domain>``, ``trends``,
    ``narrative``, plus ``period`` / ``generated_at`` / ``currency`` --
    but ``kpis``/``alerts`` are filtered to departments the caller can
    read, and the cross-domain composites are omitted unless the caller
    can read every department (see ``_scoped_rollup``).
    """
    try:
        permitted = _permitted_departments()
        _require_any_department(permitted)
        from insights.ml.executive_intelligence import get_executive_summary

        return success(_scoped_rollup(get_executive_summary(period), permitted))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_business_health_score() -> Dict[str, Any]:
    """Return the ``business_health_score`` block, if the caller can read
    every department -- it is a composite across all of them (see
    ``_scoped_rollup``)."""
    try:
        permitted = _permitted_departments()
        _require_any_department(permitted)
        from insights.ml.executive_intelligence import get_executive_summary

        scoped = _scoped_rollup(get_executive_summary("YTD"), permitted)
        health = scoped.get("business_health_score")
        if health is None:
            return success({"restricted_note": scoped.get("restricted_note")})
        return success(health)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_kpis(department: Optional[str] = None, period: str = "YTD") -> Dict[str, Any]:
    """Return the KPI block: one domain if ``department`` is given (gated on
    that domain's doctype), otherwise every domain the caller can read."""
    try:
        if department:
            frappe.has_permission(_DEPARTMENT_DOCTYPE.get(department, "Sales Invoice"), "read", throw=True)
            from insights.ml.executive_intelligence import get_executive_summary

            rollup = get_executive_summary(period)
            kpis = rollup.get("kpis", {}) or {}
            return success(kpis.get(department, {}))
        permitted = _permitted_departments()
        _require_any_department(permitted)
        from insights.ml.executive_intelligence import get_executive_summary

        rollup = get_executive_summary(period)
        kpis = rollup.get("kpis", {}) or {}
        return success({k: v for k, v in kpis.items() if k in permitted})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_alerts() -> Dict[str, Any]:
    """Return the alerts list, filtered to departments the caller can read."""
    try:
        permitted = _permitted_departments()
        _require_any_department(permitted)
        from insights.ml.executive_intelligence import get_executive_summary

        alerts = get_executive_summary("YTD").get("alerts", []) or []
        return success([a for a in alerts if a.get("department", "").lower() in permitted])
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_trends(period: str = "YTD") -> Dict[str, Any]:
    """Return the trend sparkline series, if the caller can read every
    department -- the series span all of them (see ``_scoped_rollup``)."""
    try:
        permitted = _permitted_departments()
        _require_any_department(permitted)
        from insights.ml.executive_intelligence import get_executive_summary

        scoped = _scoped_rollup(get_executive_summary(period), permitted)
        trends = scoped.get("trends")
        if trends is None:
            return success({"restricted_note": scoped.get("restricted_note")})
        return success(trends)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


# ─── On-demand conversational / advisory endpoints ───────────────────────────


@frappe.whitelist()
def get_executive_insights(query: str, complexity: str = "Medium") -> Dict[str, Any]:
    """Return the executive rollup as a snapshot for an open-ended query,
    scoped to the caller's departments (see ``_scoped_rollup``).

    The current implementation does not call an LLM: it returns the
    same rollup the dashboard uses, tagged with the user's query and
    complexity. If a future rewrite wants to wire this through an LLM,
    replace the body of this function (and only this function) — the
    permission gate, success/error envelope, and contract are
    preserved.
    """
    try:
        permitted = _permitted_departments()
        _require_any_department(permitted)
        from insights.ml.executive_intelligence import get_executive_summary

        return success(
            {
                "query": query,
                "complexity": complexity,
                "rollup": _scoped_rollup(get_executive_summary("YTD"), permitted),
            }
        )
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_department_insights(department: str, query: Optional[str] = None) -> Dict[str, Any]:
    """Return one department's KPI block plus its underlying rollup.

    Permission is gated on the doctype that the requested department
    exposes — see ``_DEPARTMENT_DOCTYPE``. A user with Sales Invoice
    read access cannot use department="hr" to read payroll data.
    """
    try:
        frappe.has_permission(_DEPARTMENT_DOCTYPE.get(department, "Sales Invoice"), "read", throw=True)
        from insights.ml.executive_intelligence import get_executive_summary

        rollup = get_executive_summary("YTD")
        kpis = rollup.get("kpis", {}) or {}
        dept_kpis = kpis.get(department, {})
        return success(
            {
                "department": department,
                "query": query,
                "kpis": dept_kpis,
                "alerts": [a for a in (rollup.get("alerts") or []) if a.get("department", "").lower() == department],
            }
        )
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_strategic_recommendations(focus_area: str = "overall") -> Dict[str, Any]:
    """Return strategic recommendations derived from the rollup.

    No LLM call: the recommendations are the alerts list (each alert
    is a recommendation "address this department's RAG-red KPI"),
    filtered to departments the caller can read and optionally further
    narrowed to the focus area's department.
    """
    try:
        permitted = _permitted_departments()
        _require_any_department(permitted)
        from insights.ml.executive_intelligence import get_executive_summary

        rollup = get_executive_summary("YTD")
        alerts = [a for a in (rollup.get("alerts", []) or []) if a.get("department", "").lower() in permitted]
        # Map focus area to a department when the user picks one.
        focus_dept = {
            "financial": "Financial",
            "sales": "Sales",
            "customer": "Customer",
            "operations": "Operations",
            "risk": "Risk",
            "hr": "Hr",
            "manufacturing": "Manufacturing",
        }.get(focus_area.lower())
        recs = [a for a in alerts if not focus_dept or a.get("department", "").lower() == focus_dept.lower()]
        return success({"focus_area": focus_area, "recommendations": recs})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def analyze_executive_query(query: str) -> Dict[str, Any]:
    """Return the rollup tagged with the user's query, scoped to the
    caller's departments (see ``_scoped_rollup``).

    No LLM call: the executive rollup is the analysis. (The previous
    version of this endpoint also returned the same rollup; the
    difference is only that the data it returns is now real instead of
    fabricated from pandas/sklearn models that never saw this site.)
    """
    try:
        permitted = _permitted_departments()
        _require_any_department(permitted)
        from insights.ml.executive_intelligence import get_executive_summary

        return success({"query": query, "analysis": _scoped_rollup(get_executive_summary("YTD"), permitted)})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


# ─── Executive Report orchestration (PDF + DB record + email) ────────────────


@frappe.whitelist()
def generate_executive_report(report_type: str = "daily") -> Dict[str, Any]:
    """Generate a fresh report and persist it (PDF + ``Executive Report`` doc)."""
    try:
        frappe.has_permission("Executive Report", "read", throw=True)
        from insights.reports.executive_reports import ExecutiveReports

        reports = ExecutiveReports()
        if report_type == "daily":
            result = reports.generate_daily_executive_report()
        elif report_type == "weekly":
            result = reports.generate_weekly_executive_report()
        elif report_type == "monthly":
            result = reports.generate_monthly_executive_report()
        else:
            return error(_("Unknown report type: {0}").format(report_type))
        if not result.get("success"):
            return error(result.get("error") or _("Report generation failed"))
        return success({"report_name": result["report_name"], "report_type": report_type})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def send_executive_report(
    report_type: str = "daily",
    recipients: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generate a fresh report and email it. Defaults recipients to the
    current user (not a placeholder inbox that cannot exist)."""
    try:
        frappe.has_permission("Executive Report", "read", throw=True)
        from insights.reports.executive_reports import send_executive_report_email

        if not recipients:
            recipients = [frappe.session.user] if frappe.session.user != "Guest" else []
        result = send_executive_report_email(report_type=report_type, recipients=recipients)
        if result.get("error"):
            return error(result["error"])
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_executive_reports_status() -> Dict[str, Any]:
    """Return the real schedule from ``hooks.py``'s scheduler buckets.

    Permission-gated on ``Executive Report`` read — anyone with
    dashboard read access can see when the next report will run.
    """
    try:
        frappe.has_permission("Executive Report", "read", throw=True)
        from insights.reports.executive_reports import ExecutiveReports

        return success(ExecutiveReports().schedule_automated_reports())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_recent_executive_reports(limit: int = 10) -> Dict[str, Any]:
    """List recent ``Executive Report`` docs."""
    try:
        frappe.has_permission("Executive Report", "read", throw=True)
        rows = frappe.get_all(
            "Executive Report",
            fields=["name as id", "report_type", "report_date", "status", "creation as created"],
            order_by="creation desc",
            limit_page_length=int(limit),
        )
        return success({"reports": rows, "count": len(rows)})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def download_executive_report(report_id: str) -> Dict[str, Any]:
    """Return the download URL of the PDF attached to a generated report."""
    try:
        frappe.has_permission("Executive Report", "read", throw=True)
        if not frappe.db.exists("Executive Report", report_id):
            return error(_("Report {0} not found").format(report_id))
        pdf_file = frappe.db.get_value("Executive Report", report_id, "pdf_file")
        if not pdf_file:
            return error(_("No PDF is attached to this report"))
        return success({"download_url": pdf_file})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def test_executive_intelligence_data() -> Dict[str, Any]:
    """Sanity check: does the rollup return anything for this user/site?"""
    try:
        frappe.has_permission("Executive Report", "read", throw=True)
        from insights.ml.executive_intelligence import get_executive_summary

        rollup = get_executive_summary("YTD")
        has_data = bool(rollup.get("business_health_score") or rollup.get("kpis"))
        return success(
            {
                "test": "passed" if has_data else "no_data",
                "data_available": has_data,
                "kpi_domains": list((rollup.get("kpis") or {}).keys()),
                "alert_count": len(rollup.get("alerts") or []),
            }
        )
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def preview_executive_report_data(report_type: str = "daily") -> Dict[str, Any]:
    """Return the most recent generated report's data, or generate one."""
    try:
        frappe.has_permission("Executive Report", "read", throw=True)
        existing = frappe.get_all(
            "Executive Report",
            filters={"report_type": report_type, "status": "Generated"},
            fields=["name"],
            order_by="creation desc",
            limit_page_length=1,
        )
        if existing:
            raw = frappe.db.get_value("Executive Report", existing[0].name, "report_data")
            report_data = json.loads(raw) if raw else {}
        else:
            from insights.reports.executive_reports import ExecutiveReports

            reports = ExecutiveReports()
            if report_type == "daily":
                result = reports.generate_daily_executive_report()
            elif report_type == "weekly":
                result = reports.generate_weekly_executive_report()
            elif report_type == "monthly":
                result = reports.generate_monthly_executive_report()
            else:
                return error(_("Unknown report type: {0}").format(report_type))
            if not result.get("success"):
                return error(result.get("error") or _("Could not generate preview"))
            report_data = result["report_data"]

        modules_with_data = [
            module for module, data in (report_data.get("detailed_data") or {}).items() if data
        ]
        from frappe.defaults import get_user_default

        company = (
            get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        currency = (
            frappe.db.get_value("Company", company, "default_currency")
            or frappe.db.get_single_value("Global Defaults", "default_currency")
            or "USD"
        )
        return success(
            {
                "executive_summary": report_data.get("executive_summary", ""),
                "key_metrics": report_data.get("key_metrics", {}),
                "alerts": report_data.get("alerts", []),
                "modules_with_data": modules_with_data,
                "currency": currency,
            }
        )
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


# ─── Drill-down: per-metric paginated row tables ─────────────────────────────


@frappe.whitelist()
def get_executive_detail(metric: str, filters: str) -> dict:
    """Drill-down endpoint: return the underlying rows for a headline KPI.

    Not wrapped in success/error because the function either returns
    the data shape the drill-down component expects, or throws a
    Frappe ValidationError on an unknown metric. Permission is gated
    per metric on the doctype that holds the data.
    """
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")

    if metric == "revenue_invoices":
        frappe.has_permission("Sales Invoice", "read", throw=True)
        db_filters = {"docstatus": 1}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "customer", "posting_date", "grand_total"],
            start=start, page_length=page_size, order_by="posting_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": _("Invoice"), "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": _("Total"), "fieldname": "grand_total", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Invoice", filters=db_filters),
        }

    if metric == "active_employees":
        frappe.has_permission("Employee", "read", throw=True)
        db_filters = {"status": "Active"}
        rows = frappe.get_list(
            "Employee",
            filters=db_filters,
            fields=["name", "employee_name", "department", "designation"],
            start=start, page_length=page_size, order_by="employee_name asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": _("Employee"), "fieldname": "name", "fieldtype": "Link", "options": "Employee"},
                {"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data"},
                {"label": _("Department"), "fieldname": "department", "fieldtype": "Data"},
                {"label": _("Designation"), "fieldname": "designation", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Employee", filters=db_filters),
        }

    if metric == "open_orders":
        frappe.has_permission("Sales Order", "read", throw=True)
        db_filters = {"docstatus": 1, "status": ("not in", ["Completed", "Cancelled", "Closed"])}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Sales Order",
            filters=db_filters,
            fields=["name", "customer", "transaction_date", "grand_total", "status"],
            start=start, page_length=page_size, order_by="transaction_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": _("Order"), "fieldname": "name", "fieldtype": "Link", "options": "Sales Order"},
                {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": _("Date"), "fieldname": "transaction_date", "fieldtype": "Date"},
                {"label": _("Total"), "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": _("Status"), "fieldname": "status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Order", filters=db_filters),
        }

    if metric == "open_pos":
        frappe.has_permission("Purchase Order", "read", throw=True)
        db_filters = {"docstatus": 1, "status": ("not in", ["Completed", "Cancelled", "Closed"])}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Purchase Order",
            filters=db_filters,
            fields=["name", "supplier", "transaction_date", "grand_total", "status"],
            start=start, page_length=page_size, order_by="transaction_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": _("PO"), "fieldname": "name", "fieldtype": "Link", "options": "Purchase Order"},
                {"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
                {"label": _("Date"), "fieldname": "transaction_date", "fieldtype": "Date"},
                {"label": _("Total"), "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": _("Status"), "fieldname": "status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Purchase Order", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)


# ─── Action Tracker (CEO cross-department action items) ──────────────────────


def _require_department_permission(department: str) -> None:
    """Raise the standard 403 unless the caller can read the doctype that
    backs `department` (see `_DEPARTMENT_DOCTYPE`). Actions are scoped by
    the same department boundary as `alerts`/`kpis` -- a Sales-only user
    must not create or resolve an HR action any more than they can read
    HR figures."""
    doctype = _DEPARTMENT_DOCTYPE.get((department or "").lower())
    if not doctype:
        frappe.throw(_("Unknown department: {0}").format(department), frappe.ValidationError)
    frappe.has_permission(doctype, "read", throw=True)


def _readable_department_titles(permitted: set) -> List[str]:
    """Title-Case department values (matching the doctype's Select options)
    for every lowercase key in `permitted`. `_DEPARTMENT_DOCTYPE` carries a
    "marketing" entry the 7-department dashboard/action tracker don't use;
    harmless here since it would just never match a stored record."""
    return [("HR" if d == "hr" else d.title()) for d in _DEPARTMENT_DOCTYPE if d in permitted]


# Doctype `Select` options for `department`, verified against
# `insights_financial_action.json`. `_DEPARTMENT_DOCTYPE` carries an extra
# "marketing" entry that other endpoints tolerate as a harmless no-op filter
# (see `_readable_department_titles`'s docstring), but offering it as a
# *create* choice here would let a Marketing-permitted user submit a value
# the doctype's Select field rejects on `.insert()`. Intersect against this
# list instead of reusing that helper's output directly.
_ACTION_DEPARTMENTS = ("Financial", "Sales", "Customer", "Operations", "Risk", "HR", "Manufacturing")


@frappe.whitelist()
def get_permitted_departments() -> Dict[str, Any]:
    """Departments the current user can create/read actions for, restricted
    to the Action doctype's actual Select options. Powers the Action
    Tracker's department pickers so a user is never offered a choice whose
    create or filter call will fail."""
    try:
        permitted = _permitted_departments()
        titles = set(_readable_department_titles(permitted))
        return success([d for d in _ACTION_DEPARTMENTS if d in titles])
    except Exception as e:
        return error(str(e))

@frappe.whitelist()
def list_actions(department: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
    """List action-tracker items, scoped to departments the caller can read.
    `status` filters to one status (e.g. "Open"); omit for all statuses."""
    try:
        permitted = _permitted_departments()
        _require_any_department(permitted)
        filters: Dict[str, Any] = {}
        if department:
            _require_department_permission(department)
            filters["department"] = department
        else:
            filters["department"] = ["in", _readable_department_titles(permitted)]
        if status:
            filters["status"] = status
        rows = frappe.get_list(
            "Insights Financial Action",
            filters=filters,
            fields=["name", "title", "department", "priority", "status", "description",
                    "source_alert", "assigned_to", "due_date", "resolved_on", "resolved_by", "creation"],
            order_by="due_date asc, creation desc",
            page_length=500,
            ignore_permissions=True,
        )
        # Frappe v16's `order_by` validator only accepts plain/linked field
        # names (see `_validate_and_parse_field_for_clause`) -- no raw SQL
        # expressions like `FIELD(priority, ...)`. Priority rank is applied
        # here instead, as a stable secondary sort on top of the DB's
        # due_date/creation ordering (Python's `sort` is stable, so ties
        # within the same priority keep the SQL-supplied order).
        _priority_rank = {"Urgent": 0, "High": 1, "Medium": 2, "Low": 3}
        rows.sort(key=lambda r: _priority_rank.get(r.get("priority"), 4))
        return success(rows)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def create_action(title: str, department: str, priority: str = "Medium",
                  description: str = "", due_date: Optional[str] = None,
                  assigned_to: Optional[str] = None, source_alert: Optional[str] = None) -> Dict[str, Any]:
    """Create a cross-department action item. Gated on read access to the
    target department's underlying doctype (see `_require_department_permission`)."""
    try:
        _require_department_permission(department)
        doc = frappe.new_doc("Insights Financial Action")
        doc.title = title
        doc.department = department
        doc.priority = priority or "Medium"
        doc.description = description or ""
        doc.due_date = due_date or None
        doc.assigned_to = assigned_to or None
        doc.source_alert = source_alert or None
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return success({"name": doc.name})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def update_action_status(name: str, status: str) -> Dict[str, Any]:
    """Transition an action's status (Open/In Progress/Resolved/Dismissed).
    Gated on read access to the ACTION's own department, fetched from the
    document itself -- so a caller cannot bypass department scoping by
    guessing another department's action name."""
    try:
        doc = frappe.get_doc("Insights Financial Action", name)
        _require_department_permission(doc.department)
        valid_statuses = ("Open", "In Progress", "Resolved", "Dismissed")
        if status not in valid_statuses:
            frappe.throw(_("Invalid status: {0}").format(status), frappe.ValidationError)
        doc.status = status
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return success({"name": doc.name, "status": doc.status,
                        "resolved_on": doc.resolved_on, "resolved_by": doc.resolved_by})
    except frappe.PermissionError:
        raise
    except frappe.DoesNotExistError:
        return error(_("Action not found"))
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def action_tracker_summary() -> Dict[str, Any]:
    """Open/overdue counts across departments the caller can read -- a
    compact badge for the Action Tracker section header."""
    try:
        permitted = _permitted_departments()
        _require_any_department(permitted)
        rows = frappe.get_list(
            "Insights Financial Action",
            filters={"department": ["in", _readable_department_titles(permitted)],
                    "status": ["in", ["Open", "In Progress"]]},
            fields=["department", "status", "due_date"],
            page_length=500,
            ignore_permissions=True,
        )
        today = frappe.utils.today()
        overdue_count = sum(1 for r in rows if r.get("due_date") and str(r["due_date"]) < today)
        return success({"open_count": len(rows), "overdue_count": overdue_count})
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))
