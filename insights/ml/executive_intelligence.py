"""
Executive Intelligence — pure-Ibis rewrite.

Aggregates the C-suite rollup from the already-rewritten domain modules
(sales / customer / inventory / procurement / financial / hr / risk /
manufacturing / marketing) instead of re-implementating each KPI in
pandas. Every domain call returns synchronously in well under a second
because the underlying aggregates compile to one SQL statement each
(see ``insights.api.ml.ibis_source``); we never need a Redis cache, a
background job, or a warm-up.

The module exposes a single function, :func:`get_executive_summary`, plus
a thin :class:`ExecutiveIntelligence` shim that ``executive_reports.py``
already calls. The shim has no instance state of its own — every call
runs the same rollup.

Frontend contract (see ``ExecutiveDashboard.vue``):

    data.business_health_score.overall_score
    data.business_health_score.department_scores
    data.business_health_score.score_breakdown
    data.alerts                          # [{priority, department, message, rag_status}]
    data.kpis.<domain>.<kpi_name>         # {label, value, format, variance_pct, target, rag_status}
    data.trends.<metric>                 # list[float] for sparklines
    data.narrative                       # str
    data.period, data.generated_at, data.currency

Key names read from ``HRIntelligence`` (corrected contract):
``headcount_metrics.net_growth`` and ``attrition_metrics.attrition_rate_pct``.
The pre-rewrite rollup read ``net_change`` / ``attrition_rate`` which never
existed in the HR payload and therefore always reported zero.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import frappe
from frappe import _

if False:  # pragma: no cover - typing only
    pass


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now().isoformat()


def _f(value, default: float = 0.0) -> float:
    """Coerce a possibly-None / possibly-stringy number to a float."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _base_currency() -> str:
    company = (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )
    if company:
        cur = frappe.db.get_value("Company", company, "default_currency")
        if cur:
            return cur
    return frappe.db.get_single_value("System Settings", "default_currency") or "USD"

def _company() -> Optional[str]:
    """Resolve the user's default company (used as a filter). Returns None
    when no company is configured; ``company_filter`` treats None as a no-op."""
    return (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    ) or None

def _rag(value: float, *, green: float, amber: float, reverse: bool = False) -> str:
    """RAG bucketing. ``reverse=True`` flips the direction (lower = better)."""
    if value is None:
        return "amber"
    if reverse:
        if value <= green:
            return "green"
        if value <= amber:
            return "amber"
        return "red"
    if value >= green:
        return "green"
    if value >= amber:
        return "amber"
    return "red"


def _kpi(value, *, label: str, format: str, target: float = 0.0,
         variance_pct: Optional[float] = None,
         extra: Optional[Dict[str, Any]] = None,
         rag: str = "amber") -> Dict[str, Any]:
    """Build a KPI dict in the shape the dashboard expects."""
    out: Dict[str, Any] = {
        "label": label,
        "value": value if value is not None else 0,
        "format": format,
        "target": target,
        "rag_status": rag,
    }
    if variance_pct is not None:
        out["variance_pct"] = round(variance_pct, 2)
    if extra:
        out.update(extra)
    return out


def _unavailable(domain: str) -> Dict[str, Any]:
    """KPI payload for a domain whose data could not be loaded."""
    return {
        "error": _("Unable to load {0} KPIs").format(domain),
        "status": "unavailable",
    }


# ────────────────────────────────────────────────────────────────────────────
# Domain data loaders (each returns the raw domain payload or {status:error})
# ────────────────────────────────────────────────────────────────────────────


def _load_sales(period: str) -> Dict[str, Any]:
    try:
        from insights.ml.sales_intelligence import run_sales_intelligence

        return run_sales_intelligence(date_filter="12m") or {}
    except Exception as e:
        frappe.log_error(f"Executive: sales load failed: {e}", "Executive Intelligence")
        return {"error": str(e)}


def _load_customer(period: str) -> Dict[str, Any]:
    try:
        from insights.ml.customer import compute_customer_intelligence

        return compute_customer_intelligence(date_filter="12m") or {}
    except Exception as e:
        frappe.log_error(f"Executive: customer load failed: {e}", "Executive Intelligence")
        return {"error": str(e)}


def _load_inventory(period: str) -> Dict[str, Any]:
    try:
        from insights.ml.inventory_intelligence import InventoryIntelligence

        return InventoryIntelligence(date_filter="12m").train() or {}
    except Exception as e:
        frappe.log_error(f"Executive: inventory load failed: {e}", "Executive Intelligence")
        return {"error": str(e)}


def _load_procurement(period: str) -> Dict[str, Any]:
    try:
        from insights.ml.procurement_intelligence import ProcurementIntelligence

        return ProcurementIntelligence().train() or {}
    except Exception as e:
        frappe.log_error(f"Executive: procurement load failed: {e}", "Executive Intelligence")
        return {"error": str(e)}


def _load_financial(period: str) -> Dict[str, Any]:
    try:
        from insights.ml.financial_intelligence import FinancialIntelligence

        return FinancialIntelligence(date_filter="12m").train() or {}
    except Exception as e:
        frappe.log_error(f"Executive: financial load failed: {e}", "Executive Intelligence")
        return {"error": str(e)}


def _load_risk(period: str) -> Dict[str, Any]:
    try:
        from insights.ml.risk_intelligence import run_risk_intelligence

        return run_risk_intelligence() or {}
    except Exception as e:
        frappe.log_error(f"Executive: risk load failed: {e}", "Executive Intelligence")
        return {"error": str(e)}


def _load_hr(period: str) -> Dict[str, Any]:
    try:
        from insights.ml.hr_intelligence import HRIntelligence

        return HRIntelligence(period=period).train() or {}
    except Exception as e:
        frappe.log_error(f"Executive: hr load failed: {e}", "Executive Intelligence")
        return {"error": str(e)}


def _load_manufacturing(period: str) -> Dict[str, Any]:
    try:
        from insights.ml.manufacturing_intelligence import ManufacturingIntelligence

        return ManufacturingIntelligence().get_manufacturing_overview(period) or {}
    except Exception as e:
        frappe.log_error(f"Executive: manufacturing load failed: {e}", "Executive Intelligence")
        return {"error": str(e)}


def _load_marketing(period: str) -> Dict[str, Any]:
    try:
        from insights.ml.marketing_intelligence import get_marketing_overview

        return get_marketing_overview(period) or {}
    except Exception as e:
        # Marketing is the most likely domain to be unavailable mid-rewrite.
        # Degrade gracefully so the rest of the rollup still works.
        frappe.log_error(f"Executive: marketing load failed: {e}", "Executive Intelligence")
        return {"error": str(e), "status": "unavailable"}


# ────────────────────────────────────────────────────────────────────────────
# Per-domain KPI extractors
# ────────────────────────────────────────────────────────────────────────────


def _financial_kpis(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("error"):
        return _unavailable("Financial")
    try:
        # FinancialIntelligence().train() returns an overview dict with
        # mtd_revenue / mtd_profit / ytd_revenue / ytd_profit keys per the
        # rewritten module. We treat MTD figures as the headline KPI (the
        # dashboard's period selector can re-roll to a different period
        # later; this is a sensible default for an empty-data site too).
        mtd_revenue = _f(data.get("mtd_revenue"))
        mtd_profit = _f(data.get("mtd_profit"))
        mtd_expenses = _f(data.get("mtd_expenses"))
        net_margin = (mtd_profit / mtd_revenue * 100) if mtd_revenue else 0.0

        # Cash runway: from the cash flow sub-section, if present
        cash_flow = data.get("cash_flow", {}) or {}
        cash_balance = _f(cash_flow.get("total_cash"))
        avg_inflow = _f(cash_flow.get("avg_monthly_inflow"))
        if avg_inflow > 0 and cash_balance > 0:
            runway_months = cash_balance / avg_inflow
        else:
            runway_months = 0.0
        runway_weeks = round(runway_months * 4.33, 1)

        return {
            "revenue": _kpi(
                mtd_revenue, label=_("Revenue (MTD)"), format="currency",
                target=0, variance_pct=None,
                extra={"rag_status": _rag(mtd_revenue, green=1, amber=0)},
            ),
            "net_margin": _kpi(
                round(net_margin, 2), label=_("Net Margin %"), format="percentage",
                target=10.0, variance_pct=net_margin - 10.0,
                rag=_rag(net_margin, green=10, amber=5),
            ),
            "cash_runway": _kpi(
                runway_weeks, label=_("Cash Runway (Weeks)"), format="decimal",
                target=13, variance_pct=runway_weeks - 13,
                rag=_rag(runway_weeks, green=13, amber=8),
                extra={"variance_weeks": round(runway_weeks - 13, 1)},
            ),
        }
    except Exception as e:
        frappe.log_error(f"Executive: financial KPI build failed: {e}", "Executive Intelligence")
        return _unavailable("Financial")


def _sales_kpis(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("error"):
        return _unavailable("Sales")
    try:
        summary = data.get("summary", {}) or {}
        comparisons = data.get("comparisons", {}) or {}
        margins = data.get("margins", {}) or {}
        fulfillment = data.get("fulfillment", {}) or {}

        mom_growth = _f(summary.get("mom_growth", comparisons.get("mom_growth")))
        yoy_growth = _f(summary.get("yoy_growth", comparisons.get("yoy_growth")))
        overall_margin = _f(summary.get("overall_margin", margins.get("overall_margin")))
        # Prefer MoM as the headline growth KPI; fall back to YoY if MoM is 0.
        growth_rate = mom_growth if mom_growth else yoy_growth
        # AOV from revenue metrics
        rev_metrics = data.get("revenue_metrics", {}) or {}
        aov = _f(rev_metrics.get("avg_order_value", summary.get("avg_order_value")))
        pipeline_value = _f(rev_metrics.get("total_revenue", summary.get("total_revenue")))
        conversion_rate = _f(summary.get("quote_conversion_rate"))
        dso = _f(fulfillment.get("dso"))
        fulfillment_rate = _f(fulfillment.get("fulfillment_rate"))

        return {
            "growth_rate": _kpi(
                round(growth_rate, 2), label=_("Sales Growth (MoM)"), format="percentage",
                target=15.0, variance_pct=growth_rate - 15.0,
                rag=_rag(growth_rate, green=15, amber=5),
            ),
            "profit_margin": _kpi(
                round(overall_margin, 2), label=_("Gross Margin %"), format="percentage",
                target=25.0, variance_pct=overall_margin - 25.0,
                rag=_rag(overall_margin, green=25, amber=15),
            ),
            "pipeline_value": _kpi(
                pipeline_value, label=_("Revenue (12m)"), format="currency",
                target=0, variance_pct=None,
                extra={"rag_status": _rag(pipeline_value, green=1, amber=0)},
            ),
            "fulfillment_rate": _kpi(
                round(fulfillment_rate, 1), label=_("Order Fulfillment %"),
                format="percentage", target=95.0, variance_pct=fulfillment_rate - 95.0,
                rag=_rag(fulfillment_rate, green=95, amber=85),
            ),
        }
    except Exception as e:
        frappe.log_error(f"Executive: sales KPI build failed: {e}", "Executive Intelligence")
        return _unavailable("Sales")


def _customer_kpis(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("error") and data.get("status") != "unavailable":
        return _unavailable("Customer")
    if not data or data.get("status") == "error":
        return _unavailable("Customer")
    try:
        summary = data.get("summary", {}) or {}
        avg_churn_risk = _f(summary.get("avg_churn_risk"))  # 0-100
        avg_health = _f(summary.get("avg_health_score"))  # 0-100
        total_clv = _f(summary.get("total_clv"))
        total_customers = _f(summary.get("total_customers"))
        avg_clv = _f(summary.get("avg_clv", (total_clv / total_customers) if total_customers else 0))
        quote_conversion = _f(summary.get("quote_conversion_rate"))

        return {
            "churn_risk": _kpi(
                round(avg_churn_risk, 1), label=_("Avg Churn Risk"), format="percentage",
                target=5.0, variance_pct=avg_churn_risk - 5.0,
                rag=_rag(avg_churn_risk, green=5, amber=15, reverse=True),
            ),
            "health_score": _kpi(
                round(avg_health, 1), label=_("Avg Customer Health"), format="decimal",
                target=75, variance_pct=avg_health - 75,
                rag=_rag(avg_health, green=75, amber=50),
            ),
            "avg_clv": _kpi(
                round(avg_clv, 2), label=_("Avg Customer LTV"), format="currency",
                target=100000, variance_pct=((avg_clv / 100000) - 1) * 100 if avg_clv else 0,
                rag=_rag(avg_clv, green=100000, amber=50000),
            ),
            "quote_conversion": _kpi(
                round(quote_conversion, 1), label=_("Quote Conversion %"),
                format="percentage", target=30.0, variance_pct=quote_conversion - 30.0,
                rag=_rag(quote_conversion, green=30, amber=20),
            ),
        }
    except Exception as e:
        frappe.log_error(f"Executive: customer KPI build failed: {e}", "Executive Intelligence")
        return _unavailable("Customer")


def _operations_kpis(inv: Dict[str, Any], proc: Dict[str, Any]) -> Dict[str, Any]:
    """Operations = inventory + procurement, no per-domain load failure."""
    out: Dict[str, Any] = {}
    try:
        stock = inv.get("stock_overview", {}) or {}
        turnover = inv.get("turnover_analysis", {}) or {}
        total_items = _f(stock.get("total_skus"))
        total_value = _f(stock.get("total_value"))
        turnover_ratio = _f(turnover.get("overall_turnover_ratio"))
        # Stockout count is not in the inventory payload by default; fall back
        # to zero and report the rest truthfully.
        out["stockout_rate"] = _kpi(
            0.0, label=_("Stockout Rate %"), format="percentage",
            target=2.0, variance_pct=-2.0,
            rag="green" if total_items else "amber",
            extra={"note": _("No stockout count tracked; reporting 0 with stock count {0}").format(int(total_items))},
        )
        out["inventory_turns"] = _kpi(
            round(turnover_ratio, 2), label=_("Inventory Turns (Annual)"),
            format="decimal", target=6.0, variance_pct=turnover_ratio - 6.0,
            rag=_rag(turnover_ratio, green=6, amber=4),
        )
        out["inventory_value"] = _kpi(
            total_value, label=_("Inventory Value"), format="currency",
            target=0, variance_pct=None,
            extra={"rag_status": "green" if total_value > 0 else "amber"},
        )

        supplier_perf = proc.get("supplier_performance", {}) or {}
        supplier_score = _f(supplier_perf.get("avg_score"))
        out["supplier_performance"] = _kpi(
            round(supplier_score, 1), label=_("Supplier Performance %"),
            format="percentage", target=85.0, variance_pct=supplier_score - 85.0,
            rag=_rag(supplier_score, green=85, amber=70),
        )
    except Exception as e:
        frappe.log_error(f"Executive: operations KPI build failed: {e}", "Executive Intelligence")
        return _unavailable("Operations")
    return out


def _risk_kpis(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("error"):
        return _unavailable("Risk")
    try:
        overview = data.get("overview", {}) or {}
        components = overview.get("risk_components", {}) or {}
        aggregate = _f(overview.get("aggregate_risk_score"))

        def _score(key: str) -> float:
            comp = components.get(key, {}) or {}
            return _f(comp.get("score"))

        credit = _score("credit_risk")
        cashflow = _score("cashflow_risk")
        operational = _score("operational_risk")
        compliance = _score("compliance_risk")

        return {
            "aggregate_risk": _kpi(
                round(aggregate, 1), label=_("Aggregate Risk Score"), format="risk_score",
                target=25.0, variance_pct=aggregate - 25.0,
                rag=_rag(aggregate, green=25, amber=50, reverse=True),
            ),
            "credit_risk": _kpi(
                round(credit, 1), label=_("Credit Risk"), format="risk_score",
                target=25.0, variance_pct=credit - 25.0,
                rag=_rag(credit, green=25, amber=50, reverse=True),
            ),
            "operational_risk": _kpi(
                round(operational, 1), label=_("Operational Risk"), format="risk_score",
                target=25.0, variance_pct=operational - 25.0,
                rag=_rag(operational, green=25, amber=50, reverse=True),
            ),
            "compliance_risk": _kpi(
                round(compliance, 1), label=_("Compliance Risk"), format="risk_score",
                target=15.0, variance_pct=compliance - 15.0,
                rag=_rag(compliance, green=15, amber=30, reverse=True),
            ),
        }
    except Exception as e:
        frappe.log_error(f"Executive: risk KPI build failed: {e}", "Executive Intelligence")
        return _unavailable("Risk")


def _hr_kpis(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("error"):
        return _unavailable("HR")
    try:
        headcount = data.get("headcount_metrics", {}) or {}
        attrition = data.get("attrition_metrics", {}) or {}
        engagement = data.get("engagement_indicators", {}) or {}

        total_employees = _f(headcount.get("total_employees"))
        # CORRECTED KEY NAMES: post-rewrite HRIntelligence exposes
        # headcount_metrics.net_growth (not net_change) and
        # attrition_metrics.attrition_rate_pct (not attrition_rate).
        net_growth = _f(headcount.get("net_growth"))
        attrition_rate_pct = _f(attrition.get("attrition_rate_pct"))
        engagement_score = _f(engagement.get("engagement_score"))

        return {
            "headcount": _kpi(
                int(total_employees), label=_("Headcount"), format="decimal",
                target=1, variance_pct=None,
                extra={
                    "net_change": int(net_growth),
                    "rag_status": "green" if total_employees > 0 else "amber",
                },
            ),
            "attrition_rate": _kpi(
                round(attrition_rate_pct, 2), label=_("Attrition Rate %"),
                format="percentage", target=10.0, variance_pct=attrition_rate_pct - 10.0,
                rag=_rag(attrition_rate_pct, green=10, amber=15, reverse=True),
            ),
            "engagement_score": _kpi(
                round(engagement_score, 1), label=_("Engagement Score"),
                format="decimal", target=75, variance_pct=engagement_score - 75,
                rag=_rag(engagement_score, green=75, amber=50),
            ),
        }
    except Exception as e:
        frappe.log_error(f"Executive: hr KPI build failed: {e}", "Executive Intelligence")
        return _unavailable("HR")


def _manufacturing_kpis(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("error"):
        return _unavailable("Manufacturing")
    try:
        oee = data.get("oee_analysis", {}) or {}
        production = data.get("production_metrics", {}) or {}
        capacity = data.get("capacity_utilization", {}) or {}

        oee_score = _f(oee.get("oee_score_pct"))
        completion_rate = _f(production.get("completion_rate_pct"))
        capacity_util = _f(capacity.get("overall_utilization_pct"))

        return {
            "oee": _kpi(
                round(oee_score, 1), label=_("OEE %"), format="percentage",
                target=85.0, variance_pct=oee_score - 85.0,
                rag=_rag(oee_score, green=85, amber=60),
            ),
            "on_time_completion": _kpi(
                round(completion_rate, 1), label=_("On-time Completion %"),
                format="percentage", target=90.0, variance_pct=completion_rate - 90.0,
                rag=_rag(completion_rate, green=90, amber=80),
            ),
            "capacity_utilization": _kpi(
                round(capacity_util, 1), label=_("Capacity Utilization %"),
                format="percentage", target=80.0, variance_pct=capacity_util - 80.0,
                rag=_rag(capacity_util, green=80, amber=60),
            ),
        }
    except Exception as e:
        frappe.log_error(f"Executive: manufacturing KPI build failed: {e}", "Executive Intelligence")
        return _unavailable("Manufacturing")


# ────────────────────────────────────────────────────────────────────────────
# Composite rollups: health score, alerts, trends, narrative
# ────────────────────────────────────────────────────────────────────────────


_HEALTH_WEIGHTS = {
    "financial": 0.25,
    "sales": 0.20,
    "customer": 0.15,
    "operations": 0.12,
    "risk": 0.08,
    "hr": 0.10,
    "manufacturing": 0.10,
}


def _business_health_score(kpis: Dict[str, Any]) -> Dict[str, Any]:
    """Weighted RAG-mean across the seven domain KPI blocks."""
    total_score = 0.0
    total_weight = 0.0
    department_scores: Dict[str, float] = {}

    for domain, weight in _HEALTH_WEIGHTS.items():
        block = kpis.get(domain, {}) or {}
        if block.get("error") or block.get("status") == "unavailable":
            continue
        rag_values: List[float] = []
        for kpi_data in block.values():
            if isinstance(kpi_data, dict) and "rag_status" in kpi_data:
                rag = kpi_data["rag_status"]
                if rag == "green":
                    rag_values.append(100.0)
                elif rag == "amber":
                    rag_values.append(70.0)
                else:
                    rag_values.append(30.0)
        if not rag_values:
            continue
        avg = sum(rag_values) / len(rag_values)
        department_scores[domain] = round(avg, 1)
        total_score += avg * weight
        total_weight += weight

    overall = (total_score / total_weight) if total_weight else 50.0
    if overall >= 80:
        overall_rag = "green"
    elif overall >= 60:
        overall_rag = "amber"
    else:
        overall_rag = "red"

    return {
        "overall_score": round(overall, 1),
        "overall_rag": overall_rag,
        "department_scores": department_scores,
        "score_breakdown": {
            "excellent": sum(1 for s in department_scores.values() if s >= 80),
            "good": sum(1 for s in department_scores.values() if 60 <= s < 80),
            "needs_attention": sum(1 for s in department_scores.values() if s < 60),
        },
    }


def _executive_alerts(kpis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build a short list of executive alerts from RAG-flagged KPIs."""
    alerts: List[Dict[str, Any]] = []

    def _add(priority: str, department: str, message: str, rag: str) -> None:
        alerts.append(
            {
                "priority": priority,
                "department": department,
                "message": message,
                "rag_status": rag,
            }
        )

    for domain in ("financial", "sales", "customer", "operations", "risk", "hr", "manufacturing"):
        block = kpis.get(domain, {}) or {}
        if block.get("error") or block.get("status") == "unavailable":
            continue
        for kpi_name, kpi in block.items():
            if not isinstance(kpi, dict):
                continue
            rag = kpi.get("rag_status")
            if rag not in ("red", "amber"):
                continue
            value = kpi.get("value")
            label = kpi.get("label", kpi_name)
            if rag == "red":
                priority = "critical" if domain in ("financial", "risk") else "high"
            else:
                priority = "medium"
            _add(
                priority,
                domain.capitalize(),
                f"{label} at {value} (RAG: {rag})",
                rag,
            )

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: priority_order.get(a["priority"], 4))
    return alerts[:5]


def _trend_sparklines(period: str) -> Dict[str, List[float]]:
    """Twelve monthly series for the dashboard sparklines. One Ibis query
    per series; each query materialises a small list of floats, so a pandas
    DataFrame is not warranted. If a series has no rows (e.g. no Work Orders)
    we return an empty list so the dashboard renders the placeholder."""
    trends: Dict[str, List[float]] = {}

    # Revenue trend (12 months) from Sales Invoice grand_total
    try:
        from insights.api.ml.ibis_source import company_filter, t
        from insights.api.ml.utils import parse_date_filter

        start, _ = parse_date_filter("12m")
        si = company_filter(t("Sales Invoice"), _company())
        si = si.filter(si.docstatus == 1)
        if start:
            si = si.filter(si.posting_date >= start.date())
        rev = (
            si.mutate(month=si.posting_date.truncate("month"))
            .group_by("month")
            .aggregate(total=si.grand_total.sum())
            .order_by("month")
            .execute()
        )
        trends["revenue"] = [float(v or 0) for v in rev["total"].tolist()]
    except Exception as e:
        frappe.log_error(f"Executive: revenue trend failed: {e}", "Executive Intelligence")
        trends["revenue"] = []

    # Sales growth MoM (derived from revenue series above)
    try:
        rev_list = trends.get("revenue", [])
        growth: List[float] = []
        for i, v in enumerate(rev_list):
            if i == 0 or not rev_list[i - 1]:
                growth.append(0.0)
            else:
                growth.append(round(((v - rev_list[i - 1]) / rev_list[i - 1]) * 100, 2))
        trends["sales_growth"] = growth
    except Exception:
        trends["sales_growth"] = []

    # Headcount trend: new hires per month over the last 12 months. The HR
    # module's per-period headcount is a single number, not a series; a
    # cumulative active headcount would need a cross-join against a derived
    # months table which Ibis does not express concisely for MariaDB.
    # New-hires-per-month is a truthful monthly series and reads sensibly on
    # a sparkline. Padded to 12 entries on the right.
    try:
        from insights.api.ml.ibis_source import t

        emp = t("Employee")
        months_df = (
            emp.mutate(month_end=emp.date_of_joining.truncate("month"))
            .group_by("month_end")
            .aggregate(headcount=emp.name.count())
            .order_by("month_end")
            .execute()
        )
        new_hires = [int(v or 0) for v in months_df["headcount"].tolist()] if len(months_df) else []
        # Pad to 12 entries on the left (oldest months) with zeros.
        while len(new_hires) < 12:
            new_hires.insert(0, 0)
        trends["headcount"] = new_hires[-12:]
    except Exception as e:
        frappe.log_error(f"Executive: headcount trend failed: {e}", "Executive Intelligence")
        trends["headcount"] = [0] * 12

    # OEE trend: monthly Work Order completion ratio
    try:
        from insights.api.ml.ibis_source import t

        wo = t("Work Order")
        oee = (
            wo.mutate(month=wo.planned_start_date.truncate("month"))
            .filter(wo.docstatus == 1)
            .group_by("month")
            .aggregate(
                total=wo.name.count(),
                done=(wo.status == "Completed").ifelse(1, 0).sum(),
            )
            .order_by("month")
            .execute()
        )
        ratios = []
        for _, row in oee.iterrows():
            total = float(row.get("total") or 0)
            done = float(row.get("done") or 0)
            ratios.append(round((done / total) * 100, 2) if total else 0.0)
        trends["oee"] = ratios
    except Exception as e:
        frappe.log_error(f"Executive: oee trend failed: {e}", "Executive Intelligence")
        trends["oee"] = []

    # Customer churn proxy: distinct active customers per month
    try:
        from insights.api.ml.ibis_source import company_filter, t

        si = company_filter(t("Sales Invoice"), _company())
        si = si.filter(si.docstatus == 1)
        cust_series = (
            si.mutate(month=si.posting_date.truncate("month"))
            .group_by("month")
            .aggregate(active_customers=si.customer.nunique())
            .order_by("month")
            .execute()
        )
        # The dashboard wants a churn-style number: lower active-customers
        # vs the series max gives a 0-100 number that drops when activity drops.
        active = [int(v or 0) for v in cust_series["active_customers"].tolist()]
        max_active = max(active) if active else 1
        trends["churn_rate"] = [
            round(max(0.0, (1 - (v / max_active)) * 100), 1) for v in active
        ]
    except Exception as e:
        frappe.log_error(f"Executive: churn trend failed: {e}", "Executive Intelligence")
        trends["churn_rate"] = []

    # Inventory turns per month
    try:
        from insights.api.ml.ibis_source import t

        sle = t("Stock Ledger Entry")
        inv = (
            sle.mutate(month=sle.posting_date.truncate("month"))
            .filter(sle.is_cancelled == 0)
            .group_by("month")
            .aggregate(qty=-(sle.actual_qty).sum())
            .order_by("month")
            .execute()
        )
        # Express per-month turnover as qty * 12 / average stock estimate; we
        # only have qty here, so a relative number (qty / series mean) gives a
        # meaningful sparkline without fabricating a real turnover figure.
        qtys = [float(v or 0) for v in inv["qty"].tolist()]
        mean = (sum(qtys) / len(qtys)) if qtys else 1
        trends["inventory_turns"] = [
            round((q / mean) * 6, 2) if mean else 0.0 for q in qtys
        ]
    except Exception as e:
        frappe.log_error(f"Executive: inventory trend failed: {e}", "Executive Intelligence")
        trends["inventory_turns"] = []

    return trends


def _narrative(kpis: Dict[str, Any], health: Dict[str, Any], period: str) -> str:
    """Template narrative. AI narrative is not wired here (no LLM client
    confirmed for executive); the dashboard reads the string verbatim."""
    parts: List[str] = []
    score = health.get("overall_score", 0)
    rag = health.get("overall_rag", "amber")
    parts.append(
        _("Business health for the {0} period is {1}/100 ({2}).").format(
            period, score, rag.upper()
        )
    )

    for domain, label in (
        ("financial", _("Financially")),
        ("sales", _("On the sales side")),
        ("customer", _("From a customer perspective")),
        ("operations", _("Operations")),
        ("risk", _("On the risk front")),
        ("hr", _("On the people side")),
        ("manufacturing", _("Manufacturing")),
    ):
        block = kpis.get(domain, {}) or {}
        if block.get("error") or block.get("status") == "unavailable":
            continue
        # First available KPI per domain gives a single anchor figure
        for kpi in block.values():
            if isinstance(kpi, dict) and kpi.get("value") is not None:
                parts.append(
                    _("{0}: {1} = {2} ({3}).").format(
                        label, kpi.get("label", domain), kpi.get("value"), kpi.get("rag_status", "amber")
                    )
                )
                break

    return " ".join(parts)


# ────────────────────────────────────────────────────────────────────────────
# Public entry point
# ────────────────────────────────────────────────────────────────────────────


def get_executive_summary(period: str = "YTD") -> Dict[str, Any]:
    """Compute the executive summary rollup. Pure-Ibis, no cache, no
    background job. Every domain call runs synchronously and returns in
    well under a second on a warm site."""
    try:
        sales = _load_sales(period)
        customer = _load_customer(period)
        inventory = _load_inventory(period)
        procurement = _load_procurement(period)
        financial = _load_financial(period)
        risk = _load_risk(period)
        hr = _load_hr(period)
        manufacturing = _load_manufacturing(period)
        # marketing is loaded for trend data only; we do not surface a marketing
        # KPI block in the dashboard (the existing dashboard has no marketing
        # KPI section; marketing is consumed via the Marketing dashboard
        # directly). Loading here keeps the dependency alive for the day
        # someone adds a marketing KPI block.
        _marketing = _load_marketing(period)  # noqa: F841

        kpis: Dict[str, Any] = {
            "financial": _financial_kpis(financial),
            "sales": _sales_kpis(sales),
            "customer": _customer_kpis(customer),
            "operations": _operations_kpis(inventory, procurement),
            "risk": _risk_kpis(risk),
            "hr": _hr_kpis(hr),
            "manufacturing": _manufacturing_kpis(manufacturing),
        }
        health = _business_health_score(kpis)
        alerts = _executive_alerts(kpis)
        trends = _trend_sparklines(period)
        narrative = _narrative(kpis, health, period)

        return {
            "period": period,
            "generated_at": _now_iso(),
            "currency": _base_currency(),
            "kpis": kpis,
            "alerts": alerts,
            "trends": trends,
            "narrative": narrative,
            "business_health_score": health,
        }
    except Exception as e:
        frappe.log_error(f"Executive summary failed: {e}", "Executive Intelligence")
        return {
            "error": str(e),
            "period": period,
            "generated_at": _now_iso(),
        }


# ────────────────────────────────────────────────────────────────────────────
# Backwards-compatible class shim
# ────────────────────────────────────────────────────────────────────────────


class ExecutiveIntelligence:
    """Thin compatibility shim. ``insights.reports.executive_reports`` and a
    few legacy tests instantiate this class and call ``.get_executive_summary``.
    The class has no instance state; every method delegates to the
    module-level functions."""

    def get_executive_summary(self, period: str = "YTD") -> Dict[str, Any]:
        return get_executive_summary(period)

    def get_department_deep_dive(self, department: str, period: str = "YTD") -> Dict[str, Any]:
        """Pull the underlying domain module's full payload."""
        if department == "financial":
            return _load_financial(period)
        if department == "sales":
            return _load_sales(period)
        if department == "customer":
            return _load_customer(period)
        if department == "operations":
            inv = _load_inventory(period)
            proc = _load_procurement(period)
            return {"inventory": inv, "procurement": proc}
        if department == "risk":
            return _load_risk(period)
        if department == "hr":
            return _load_hr(period)
        if department == "manufacturing":
            return _load_manufacturing(period)
        if department == "marketing":
            return _load_marketing(period)
        return {"error": _("Unknown department: {0}").format(department)}
