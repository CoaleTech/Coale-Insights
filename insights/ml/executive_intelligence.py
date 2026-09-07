"""
Executive Intelligence — pure-Ibis rewrite.

Aggregates the C-suite rollup from the already-rewritten domain modules
(sales / customer / inventory / procurement / financial / hr / risk /
manufacturing / marketing) instead of re-implementating each KPI in
pandas. Every *individual* domain call returns synchronously in well
under a second because the underlying aggregates compile to one SQL
statement each (see ``insights.api.ml.ibis_source``) -- but fanning out
to all nine of them in one rollup (see :func:`get_executive_summary`)
measured ~60-215s cold on the live jkm DB, well past most gateway/
reverse-proxy timeouts. Request-time callers MUST go through
:func:`get_cached_executive_summary`, which serves a cached payload and
recomputes it in a background job, the same pattern every other
``insights.ml.*`` dashboard uses (see ``insights.api.ml.utils.cached_run``).

The module exposes :func:`get_executive_summary` (the pure compute) and
:func:`get_cached_executive_summary` (its cached/backgrounded form), plus
a thin :class:`ExecutiveIntelligence` shim that ``executive_reports.py``
and ``executive_agent.py`` already call. The shim has no instance state
of its own -- every call delegates to the module-level functions.

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
    return frappe.db.get_single_value("Global Defaults", "default_currency") or "USD"

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
    """Build a KPI dict in the shape the dashboard expects.

    ``value`` is passed through as-is, including ``None`` -- the
    dashboard's ``KpiCard``/``formatKpiValue`` already render ``null``
    as "N/A" (a dash), which is the whole point of the three call
    sites (``cash_runway`` sentinel, ``stockout_rate``/
    ``supplier_performance`` no-data) that pass ``None`` on purpose to
    mean "not applicable" rather than a fabricated 0. Coercing to 0
    here would silently render those as a confident "$0"/"0%" instead.
    """
    out: Dict[str, Any] = {
        "label": label,
        "value": value,
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


def _resolve_date_filter(period: str) -> str:
    """Translate the executive period vocabulary (`MTD`/`QTD`/`YTD`/`TTM`, or
    an already-encoded `custom:<start>:<end>` range) into the `date_filter`
    encoding Financial/Inventory/Sales/Customer intelligence expect
    (`insights.api.ml.utils.parse_date_filter`'s vocabulary), by reusing the
    fiscal-period resolver HR already ships (`insights.ml.hr_intelligence.
    _period_start_date`/`_period_end_date`, which itself checks
    `parse_custom_range` first).

    Without this, the four domains below silently stayed on a hardcoded
    `"12m"` window no matter what the dashboard's period selector was set
    to -- the composite health score and HR/Manufacturing KPIs moved with
    the picker, everything else did not.
    """
    from insights.ml.hr_intelligence import _period_end_date, _period_start_date

    return f"custom:{_period_start_date(period)}:{_period_end_date(period)}"


def _load_sales(period: str) -> Dict[str, Any]:
    try:
        from insights.ml.sales_intelligence import run_sales_intelligence

        return run_sales_intelligence(date_filter=_resolve_date_filter(period)) or {}
    except Exception as e:
        frappe.log_error(f"Executive: sales load failed: {e}", "Executive Intelligence")
        return {"error": str(e)}


def _load_customer(period: str) -> Dict[str, Any]:
    try:
        from insights.ml.customer import compute_customer_intelligence

        return compute_customer_intelligence(date_filter=_resolve_date_filter(period)) or {}
    except Exception as e:
        frappe.log_error(f"Executive: customer load failed: {e}", "Executive Intelligence")
        return {"error": str(e)}


def _load_inventory(period: str) -> Dict[str, Any]:
    try:
        from insights.ml.inventory_intelligence import InventoryIntelligence

        return InventoryIntelligence(date_filter=_resolve_date_filter(period)).train() or {}
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

        return FinancialIntelligence(date_filter=_resolve_date_filter(period)).train() or {}
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
        overview = data.get("overview", {}) or {}
        mtd_revenue = _f(overview.get("mtd_revenue"))
        mtd_profit = _f(overview.get("mtd_profit"))
        net_margin = (mtd_profit / mtd_revenue * 100) if mtd_revenue else 0.0

        # Cash runway: reuse the burn-rate figure FinancialIntelligence already
        # computed (cash / net outflow -- how long the balance lasts if the
        # current spend pace continues). When net burn is non-positive (the
        # site is cash-flow positive, i.e. money is coming in faster than it
        # leaves) FinancialIntelligence returns a sentinel 999 for
        # `runway_months`; that "83 years of runway" would render as a real
        # C-suite KPI otherwise. Detect the sentinel and surface an
        # "unavailable" KPI in that case so the number doesn't lie.
        cash_flow = data.get("cash_flow", {}) or {}
        raw_runway = _f(cash_flow.get("runway_months"))
        burn_positive = raw_runway < 999 and raw_runway > 0
        if burn_positive:
            runway_weeks = round(raw_runway * 4.33, 1)
            runway_kpi = _kpi(
                runway_weeks, label=_("Cash Runway (Weeks)"), format="decimal",
                target=13, variance_pct=runway_weeks - 13,
                rag=_rag(runway_weeks, green=13, amber=8),
                extra={"variance_weeks": round(runway_weeks - 13, 1)},
            )
        else:
            runway_kpi = _kpi(
                None, label=_("Cash Runway (Weeks)"), format="decimal",
                target=13, variance_pct=None,
                extra={
                    "rag_status": "amber",
                    "note": _("Cash flow is positive; runway not applicable (sentinel 999 from FinancialIntelligence)"),
                },
            )
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
            "cash_runway": runway_kpi,
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
        pipeline_value = _f(rev_metrics.get("total_revenue", summary.get("total_revenue")))
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
        turnover_ratio = _f(turnover.get("overall_turnover_ratio"))
        total_items = _f(stock.get("total_skus"))
        total_value = _f(stock.get("total_value"))
        # Stockout rate: InventoryIntelligence exposes
        # `stock_overview.out_of_stock_count` (and `total_skus`) -- use them
        # rather than the previous hardcoded 0.0. The prior placeholder
        # silently reported "0% stockout, green RAG" on sites with 36 of 62
        # SKUs out of stock, which is the opposite of what the data says.
        out_of_stock = _f(stock.get("out_of_stock_count"))
        if total_items > 0 and out_of_stock > 0:
            stockout_pct = round((out_of_stock / total_items) * 100, 1)
            out["stockout_rate"] = _kpi(
                stockout_pct, label=_("Stockout Rate %"), format="percentage",
                target=2.0, variance_pct=stockout_pct - 2.0,
                rag=_rag(stockout_pct, green=2, amber=10, reverse=True),
                extra={"skus_out": int(out_of_stock), "skus_total": int(total_items)},
            )
        elif total_items > 0:
            out["stockout_rate"] = _kpi(
                0.0, label=_("Stockout Rate %"), format="percentage",
                target=2.0, variance_pct=-2.0, rag="green",
                extra={"skus_out": 0, "skus_total": int(total_items)},
            )
        else:
            out["stockout_rate"] = _kpi(
                None, label=_("Stockout Rate %"), format="percentage",
                target=2.0, variance_pct=None,
                extra={"rag_status": "amber", "note": _("No inventory data")},
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


        # `supplier_performance: null` (not a dict) when it has no supplier
        # score data. Guard against the dict.get raising and against the
        # resulting `_f(None)` silently reporting "0% supplier performance,
        # red RAG" when the truth is "we don't track this yet".
        supplier_perf = proc.get("supplier_performance") or {}
        if not supplier_perf or proc.get("status") in ("error", "unavailable"):
            out["supplier_performance"] = _kpi(
                None, label=_("Supplier Performance %"), format="percentage",
                target=85.0, variance_pct=None,
                extra={"rag_status": "amber", "note": _("No supplier performance data")},
            )
        else:
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

        # ManufacturingIntelligence returns a `message` field instead of
        # actual figures when it has no workstation/work-order data (sites
        # with no Workstation or no Work Order records); the previous
        # behaviour silently surfaced "0% OEE / 0% on-time / 0% capacity,
        # all red RAG" -- which was indistinguishable from a manufacturer
        # in genuine crisis, and dragged the business-health score down by
        # the 0.10 manufacturing weight (4 points on jkm). Detect the
        # no-data shape and skip the whole block so the health score
        # doesn't penalise the company for not tracking manufacturing.
        has_no_data = (
            "message" in oee
            or "message" in capacity
            or int(production.get("total_work_orders") or 0) == 0
        )
        if has_no_data:
            return _unavailable("Manufacturing")

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

    # Headcount trend -- previous implementation labelled this trend key
    # `headcount` but actually computed `new_hires per month` (employees
    # grouped by date_of_joining) and then padded with zeros. The HR
    # department's "Headcount" KPI card and the sparkline were showing
    # two unrelated metrics under the same name: the card showed the
    # current `total_employees`, the sparkline showed a new-hires-per-
    # month series with zero-padded historical months. Rename to the
    # truthful `new_hires_per_month` and update the Vue
    # `departmentTrendKeys.hr` to match.
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
        trends["new_hires_per_month"] = new_hires[-12:]
    except Exception as e:
        frappe.log_error(f"Executive: new_hires trend failed: {e}", "Executive Intelligence")
        trends["new_hires_per_month"] = [0] * 12
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

    # Customer activity trend -- previous implementation labelled this
    # trend key `churn_rate` but computed `max(0, (1 - v/max) * 100)`:
    # a self-referential index that scales every site's value against
    # its own max-active month, which guarantees a ceiling of 100 in the
    # most-recent (always partial) month and a floor of 0 in the
    # highest-active month regardless of real customer retention. The
    # customer block's `churn_risk` KPI already reports a real model
    # score (avg_churn_risk from `customer.summary`), so the trend and
    # the KPI were using different formulas under the same name.
    # Replace with a real per-month change in distinct active customers:
    # the % drop in active customers from one month to the next. Positive
    # value = customer base shrank (real activity loss). Negative value
    # = customer base grew. Zero-pad the first month. Renamed to
    # `customer_activity_change` to match the Vue's `departmentTrendKeys
    # .customer` after the rename.
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
        active = [int(v or 0) for v in cust_series["active_customers"].tolist()]
        change: List[float] = []
        for i, v in enumerate(active):
            if i == 0 or not active[i - 1]:
                change.append(0.0)
            else:
                change.append(round(((v - active[i - 1]) / active[i - 1]) * 100, 1))
        # Pad to 12 entries on the left (oldest months) with zeros.
        while len(change) < 12:
            change.insert(0, 0.0)
        trends["customer_activity_change"] = change[-12:]
    except Exception as e:
        frappe.log_error(f"Executive: customer activity trend failed: {e}", "Executive Intelligence")
        trends["customer_activity_change"] = [0.0] * 12
    # Stock-outflow trend -- previous implementation labelled this trend
    # key `inventory_turns` but computed a normalised relative index of
    # outgoing-stock qty (`(q / mean) * 6`) and explicitly admitted in
    # a comment that this was "without fabricating a real turnover
    # figure". The Operations department's "Inventory Turns" KPI card
    # uses the real formula (COGS / avg_inventory = 72.61 on jkm) and
    # the sparkline uses a different formula under the same name --
    # two unrelated metrics. Rename to `stock_outflow_index` (truthful)
    # and update the Vue's `departmentTrendKeys.operations` to match.
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
        # Normalised relative index of outgoing stock (positive qty only,
        # scaled around its own 12-month mean). NOT a real inventory
        # turns figure -- see the real KPI in `_operations_kpis`.
        qtys = [float(v or 0) for v in inv["qty"].tolist()]
        mean = (sum(qtys) / len(qtys)) if qtys else 1
        trends["stock_outflow_index"] = [
            round((q / mean) * 6, 2) if mean else 0.0 for q in qtys
        ]
    except Exception as e:
        frappe.log_error(f"Executive: stock outflow trend failed: {e}", "Executive Intelligence")
        trends["stock_outflow_index"] = []

    return trends

def _friendly_period_label(period: str) -> str:
    """Human-readable period name for the narrative sentence. The acronyms
    (MTD/QTD/YTD/TTM) read fine verbatim; the raw `custom:<start>:<end>`
    encoding (see `_resolve_date_filter`) does not -- format it as a date
    range instead. `data.period` itself is left untouched by this: the
    frontend round-trips that raw value into the filter control."""
    if period.startswith("custom:"):
        try:
            start, end = period[len("custom:"):].split(":")
            start_label = datetime.strptime(start, "%Y-%m-%d").strftime("%d %b %Y")
            end_label = datetime.strptime(end, "%Y-%m-%d").strftime("%d %b %Y")
            return f"{start_label} - {end_label}"
        except ValueError:
            return period
    return period


def _narrative(kpis: Dict[str, Any], health: Dict[str, Any], period: str) -> str:
    """Template narrative. AI narrative is not wired here (no LLM client
    confirmed for executive); the dashboard reads the string verbatim."""
    parts: List[str] = []
    score = health.get("overall_score", 0)
    rag = health.get("overall_rag", "amber")
    parts.append(
        _("Business health for the {0} period is {1}/100 ({2}).").format(
            _friendly_period_label(period), score, rag.upper()
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
    """Compute the executive summary rollup.

    Every other domain module in ``insights/ml/`` computes fresh on every
    call by design (see their own docstrings). This function is the one
    exception in shape, not in caching policy: it fans out to *nine* of
    those pipelines in one call (sales, customer, inventory, procurement,
    financial, risk, hr, manufacturing, marketing), and each one runs its
    own full computation -- there is no lighter-weight "KPIs only" path
    into any of them. Measured cold on the live jkm DB: 9 loaders sum to
    ~57s, the full rollup ~62-215s -- past most gateway/reverse-proxy
    timeouts, so nothing that can be reached from a web request may call
    this directly. Use :func:`get_cached_executive_summary` instead, which
    serves this from cache and recomputes it in a background job.

    This function itself is a pure, uncached compute like every other
    domain module: it raises on failure instead of swallowing the error,
    so ``insights.api.ml.utils.run`` (the caller inside
    :func:`get_cached_executive_summary`) decides whether to cache or
    surface it -- an error dict returned from here instead of raised
    would look like a valid payload to ``cached_run`` and get cached for
    a full day.
    """
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


def get_cached_executive_summary(period: str = "YTD") -> Dict[str, Any]:
    """The full, unfiltered rollup for ``period``: served from cache and
    recomputed in a background job on a miss (see
    ``insights.api.ml.utils.cached_run``), instead of blocking the request
    for the ~60-215s cold compute in :func:`get_executive_summary`.

    Returns the standard envelope (``{"status": "success", "data": ...}``,
    ``"error"``, or ``"warming"``) -- callers unwrap ``envelope["data"]``
    themselves. This has no permission gate of its own: callers must check
    permission *before* calling this (see
    ``insights.api.ml.executive._permitted_departments``), same as every
    other ``cached_run``-backed endpoint.
    """
    from insights.api.ml.utils import cached_run, run

    return cached_run(
        lambda: run(lambda: get_executive_summary(period), "executive_summary"),
        cache_key=f"insights_ml_executive_summary:{period}",
    )


# ────────────────────────────────────────────────────────────────────────────
# Backwards-compatible class shim
# ────────────────────────────────────────────────────────────────────────────


class ExecutiveIntelligence:
    """Thin compatibility shim. ``insights.reports.executive_reports`` and
    ``insights.agents.executive_agent`` instantiate this class and call
    ``.get_executive_summary``. The class has no instance state; every
    method delegates to the module-level functions."""

    def get_executive_summary(self, period: str = "YTD") -> Dict[str, Any]:
        """Cached/backgrounded rollup, unwrapped back to the plain dict
        shape this shim's callers were built against (pre-cache)."""
        envelope = get_cached_executive_summary(period)
        if envelope.get("status") == "success":
            return envelope["data"]
        return {
            "error": envelope.get("message") or _("Executive summary is still being prepared."),
            "period": period,
            "generated_at": _now_iso(),
        }

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
