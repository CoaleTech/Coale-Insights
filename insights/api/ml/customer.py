# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Customer Intelligence API Endpoints (Ibis-native).

Every endpoint here answers out of the web worker: the compute is a chain of
Ibis aggregates that compile to one SQL statement each, so most requests
return in the same latency budget as any other Insights query.
`customer_intelligence` (the full dashboard payload) is the exception -- it
fans out across several of those chains and takes tens of seconds, so it is
served from cache and recomputed by a background job, keyed per
(date_filter, company); see `insights.api.ml.utils.cached_run`. Everything
else here has no cache.

Names + kwarg signatures are preserved exactly so the frontend (which calls
these by string through ``frappe.call``) keeps working.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import frappe

from insights.api.ml.utils import cached_run, enqueue_dashboard_compute, is_cached, run


# ---------------------------------------------------------------------------
# Segment summary / RFM segmentation
# ---------------------------------------------------------------------------

@frappe.whitelist()
def customer_segmentation(refresh: bool = False, company: Optional[str] = None) -> Dict[str, Any]:
    """RFM segmentation of all customers. `refresh` is accepted but no
    longer controls any cache -- every call is fresh.
    """
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_rfm_segmentation
    return run(lambda: compute_rfm_segmentation(company=company), "Customer segmentation")


@frappe.whitelist()
def get_segment_summary() -> Dict[str, Any]:
    """Segment counts/averages, pulled from the same RFM compute the
    segmentation endpoint uses. The previous code expected a `segment_summary`
    key shaped `{segment_name: {count, total_revenue, avg_revenue}}` -- we
    match that shape from the new `segments` list so the API contract is
    unchanged.
    """
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_rfm_segmentation

    def _summarize():
        result = compute_rfm_segmentation()
        seg_map: Dict[str, Dict[str, Any]] = {}
        for row in result.get("segments", []):
            seg = row.get("segment", "")
            seg_map[seg] = {
                "count": row.get("customer_count", 0),
                "total_revenue": row.get("total_revenue", 0),
                "avg_revenue": row.get("avg_revenue", 0),
            }
        return {"segments": seg_map, "analysis_date": result.get("analysis_date")}

    return run(_summarize, "Segment summary")


# ---------------------------------------------------------------------------
# Main customer_intelligence payload
# ---------------------------------------------------------------------------

@frappe.whitelist()
def customer_intelligence(refresh: bool = False,
                          async_mode: bool = False,
                          date_filter: str = "12m",
                          company: Optional[str] = None) -> Dict[str, Any]:
    """Comprehensive customer intelligence, served from cache and recomputed
    by a background job, keyed per (date_filter, company).

    `refresh` queues a recompute and keeps serving the payload it already
    has; `async_mode` is accepted for API compatibility and ignored -- every
    caller now gets the same cache-or-`warming` contract.
    """
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_customer_intelligence
    return cached_run(
        lambda: run(lambda: compute_customer_intelligence(date_filter=date_filter, company=company),
                    "Customer intelligence"),
        cache_key=f"insights_ml_customer_intelligence:{date_filter}:{company or 'all'}",
    )


@frappe.whitelist()
def customer_intelligence_status(date_filter: str = "12m",
                                 company: Optional[str] = None) -> Dict[str, Any]:
    """Whether the customer intelligence payload is ready for this caller.

    There is a real pending state again: the payload is computed by a
    background job, so a cold cache answers `warming` until that job lands.
    The dashboards read the same state off the payload response itself; this
    endpoint is for callers that want to ask without fetching it.
    """
    frappe.has_permission("Customer", "read", throw=True)
    ready = is_cached(f"insights_ml_customer_intelligence:{date_filter}:{company or 'all'}")
    return run(lambda: {"status": "ready" if ready else "warming",
                        "message": ("Customer intelligence is cached and ready"
                                    if ready
                                    else "Customer intelligence is being computed")},
               "Customer intelligence status")


# ---------------------------------------------------------------------------
# Customer 360 / detail view
# ---------------------------------------------------------------------------

@frappe.whitelist()
def customer_360(customer_id: str) -> Dict[str, Any]:
    """Convenience alias for customer_360_detail without the purchase /
    recommendation sub-objects -- the original endpoint signature.
    """
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_customer_360
    return run(lambda: compute_customer_360(customer_id,
                                            include_purchases=False,
                                            include_recommendations=False),
               "Customer 360")


@frappe.whitelist()
def customer_360_detail(customer_id: str,
                        include_purchases: bool = True,
                        include_recommendations: bool = True,
                        company: Optional[str] = None) -> Dict[str, Any]:
    """Detailed 360-degree customer view. The base_currency field is
    injected at the payload root (not inside `customer`) because that's
    where the frontend reads it.
    """
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_customer_360, _base_currency

    def _with_currency():
        result = compute_customer_360(customer_id,
                                      include_purchases=include_purchases,
                                      include_recommendations=include_recommendations,
                                      company=company)
        if isinstance(result, dict):
            result.setdefault("base_currency", _base_currency(company))
        return result

    return run(_with_currency, "Customer 360 detail")


# ---------------------------------------------------------------------------
# Purchase patterns / cross-sell / at-risk / geographic / next actions
# ---------------------------------------------------------------------------

@frappe.whitelist()
def purchase_patterns(top_percentile: int = 20,
                      company: Optional[str] = None) -> Dict[str, Any]:
    """Day-of-week, monthly, and quarterly patterns for the top customers
    by CLV.
    """
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_purchase_patterns
    return run(lambda: compute_purchase_patterns(top_percentile=int(top_percentile),
                                                company=company),
               "Purchase patterns")


@frappe.whitelist()
def cross_sell_opportunities(tier_filter: str = "Diamond,Platinum",
                             company: Optional[str] = None) -> Dict[str, Any]:
    """Cross-sell opportunities for top-tier customers. Default tier list is
    "Diamond,Platinum" to match the original signature.
    """
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_cross_sell_opportunities
    return run(lambda: compute_cross_sell_opportunities(tier_filter=tier_filter,
                                                       company=company),
               "Cross-sell opportunities")


@frappe.whitelist()
def at_risk_customers(company: Optional[str] = None) -> Dict[str, Any]:
    """Customers with churn risk High or Critical."""
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_at_risk_customers
    return run(lambda: compute_at_risk_customers(company=company),
               "At-risk customers")


@frappe.whitelist()
def geographic_insights(company: Optional[str] = None) -> Dict[str, Any]:
    """Territory + customer-group rollups with the TerritoryMap projection."""
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_geographic_insights
    return run(lambda: compute_geographic_insights(company=company),
               "Geographic insights")


@frappe.whitelist()
def next_best_actions(company: Optional[str] = None) -> Dict[str, Any]:
    """Rule-based next-best-action recommendations per customer."""
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_next_best_actions
    return run(lambda: compute_next_best_actions(company=company),
               "Next best actions")


# ---------------------------------------------------------------------------
# refresh_scores: queues the same background compute the dashboard uses.
# ---------------------------------------------------------------------------

@frappe.whitelist()
def refresh_scores(company: Optional[str] = None) -> Dict[str, Any]:
    """Queue a recompute of the customer intelligence payload.

    This used to run the compute inline, which on a full ledger is a request
    that outlives the gateway. It now queues the same job the dashboard's own
    cache miss would, for the default `12m` window, and returns immediately.
    """
    frappe.has_permission("Customer", "write", throw=True)
    enqueue_dashboard_compute(
        "insights.api.ml.customer_intelligence",
        {"date_filter": "12m", "company": company},
        str(frappe.session.user),
    )
    return run(lambda: {"queued": True}, "Refresh customer scores")


# ---------------------------------------------------------------------------
# Counts / revenue split / rankings / variance
# ---------------------------------------------------------------------------

@frappe.whitelist()
def customer_counts(date_filter: str = "12m",
                    active_cutoff_months: int = 6,
                    company: Optional[str] = None) -> Dict[str, Any]:
    """KPI-strip counts: total, new, existing, active, inactive, advance
    payment, manufacturers, traders.
    """
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_customer_counts
    return run(lambda: compute_customer_counts(date_filter=date_filter,
                                               active_cutoff_months=int(active_cutoff_months),
                                               company=company),
               "Customer counts")


@frappe.whitelist()
def customer_revenue_split(date_filter: str = "12m",
                           company: Optional[str] = None) -> Dict[str, Any]:
    """Revenue split between new and existing customers."""
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_customer_revenue_split
    return run(lambda: compute_customer_revenue_split(date_filter=date_filter, company=company),
               "Customer revenue split")


@frappe.whitelist()
def customer_rankings(date_filter: str = "12m",
                      limit: int = 20,
                      company: Optional[str] = None) -> Dict[str, Any]:
    """Top customers by revenue, gross profit, margin %, consistency."""
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_customer_rankings
    return run(lambda: compute_customer_rankings(date_filter=date_filter,
                                                 limit=int(limit),
                                                 company=company),
               "Customer rankings")


@frappe.whitelist()
def customer_variance(date_filter: str = "12m",
                      company: Optional[str] = None) -> Dict[str, Any]:
    """Per-customer actual revenue vs territory target."""
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_customer_variance
    return run(lambda: {"variance": compute_customer_variance(date_filter=date_filter, company=company)},
               "Customer variance")


# ---------------------------------------------------------------------------
# Drill-Down (unchanged from the original file -- it was already direct
# frappe.get_list / frappe.db.sql, not model-based)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_customer_detail(metric: str, filters: str) -> dict:
    from frappe import _

    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")

    if metric == "total_customers":
        frappe.has_permission("Customer", throw=True)
        db_filters = {"disabled": 0}
        rows = frappe.get_list(
            "Customer",
            filters=db_filters,
            fields=["name", "customer_name", "customer_group", "territory", "customer_type"],
            start=start, page_length=page_size, order_by="customer_name asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Customer", "fieldname": "name", "fieldtype": "Link", "options": "Customer"},
                {"label": "Name", "fieldname": "customer_name", "fieldtype": "Data"},
                {"label": "Group", "fieldname": "customer_group", "fieldtype": "Data"},
                {"label": "Territory", "fieldname": "territory", "fieldtype": "Data"},
                {"label": "Type", "fieldname": "customer_type", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Customer", filters=db_filters),
        }

    if metric == "top_customers":
        frappe.has_permission("Sales Invoice", throw=True)
        db_filters = {"docstatus": 1}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "customer", "posting_date", "grand_total", "outstanding_amount"],
            start=start, page_length=page_size, order_by="grand_total desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Invoice", filters=db_filters),
        }

    if metric == "new_customers":
        frappe.has_permission("Customer", throw=True)
        period = f.get("period", "30d")
        days = {"7d": 7, "30d": 30, "90d": 90, "12m": 365}.get(period, 30)
        cutoff = frappe.utils.add_days(frappe.utils.today(), -days)
        db_filters = {"disabled": 0, "creation": (">=", cutoff)}
        rows = frappe.get_list(
            "Customer",
            filters=db_filters,
            fields=["name", "customer_name", "customer_group", "territory", "creation"],
            start=start, page_length=page_size, order_by="creation desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Customer", "fieldname": "name", "fieldtype": "Link", "options": "Customer"},
                {"label": "Name", "fieldname": "customer_name", "fieldtype": "Data"},
                {"label": "Group", "fieldname": "customer_group", "fieldtype": "Data"},
                {"label": "Created", "fieldname": "creation", "fieldtype": "Date"},
            ],
            "rows": rows,
            "total": frappe.db.count("Customer", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
