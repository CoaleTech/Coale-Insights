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

from insights.api.ml.utils import (
    _scoped,
    cached_run,
    enqueue_dashboard_compute,
    is_cached,
    parse_date_filter,
    run,
)


# ---------------------------------------------------------------------------
# Segment summary / RFM segmentation
# ---------------------------------------------------------------------------

@frappe.whitelist()
def customer_segmentation(refresh: bool = False, date_filter: str = "12m",
                          company: Optional[str] = None) -> Dict[str, Any]:
    """RFM segmentation of all customers in the `date_filter` window -- the
    same RFM the customer intelligence payload carries. `refresh` is accepted
    but no longer controls any cache -- every call is fresh.
    """
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_rfm_segmentation
    return run(lambda: compute_rfm_segmentation(date_filter=date_filter, company=company),
               "Customer segmentation")


@frappe.whitelist()
def get_segment_summary(date_filter: str = "12m", company: Optional[str] = None) -> Dict[str, Any]:
    """Segment counts/averages, pulled from the same RFM compute the
    segmentation endpoint uses. The previous code expected a `segment_summary`
    key shaped `{segment_name: {count, total_revenue, avg_revenue}}` -- we
    match that shape from the new `segments` list so the API contract is
    unchanged.
    """
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_rfm_segmentation

    def _summarize():
        result = compute_rfm_segmentation(date_filter=date_filter, company=company)
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
def customer_360(customer_id: str, date_filter: str = "12m") -> Dict[str, Any]:
    """Convenience alias for customer_360_detail without the purchase /
    recommendation sub-objects -- the original endpoint signature.
    """
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_customer_360
    return run(lambda: compute_customer_360(customer_id,
                                            include_purchases=False,
                                            include_recommendations=False,
                                            date_filter=date_filter),
               "Customer 360")


@frappe.whitelist()
def customer_360_detail(customer_id: str,
                        include_purchases: bool = True,
                        include_recommendations: bool = True,
                        company: Optional[str] = None,
                        date_filter: str = "12m") -> Dict[str, Any]:
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
                                      company=company,
                                      date_filter=date_filter)
        if isinstance(result, dict):
            result.setdefault("base_currency", _base_currency(company))
            result.setdefault("revenue_basis", "net_of_tax")
        return result

    return run(_with_currency, "Customer 360 detail")


# ---------------------------------------------------------------------------
# Purchase patterns / cross-sell / at-risk / geographic / next actions
# ---------------------------------------------------------------------------

@frappe.whitelist()
def purchase_patterns(top_percentile: int = 20,
                      date_filter: str = "12m",
                      company: Optional[str] = None) -> Dict[str, Any]:
    """Day-of-week, monthly, and quarterly patterns for the top customers
    by revenue in the `date_filter` window.
    """
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_purchase_patterns
    return run(lambda: compute_purchase_patterns(top_percentile=int(top_percentile),
                                                date_filter=date_filter,
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
def geography_breakdown(
    dimension: str = "territory",
    date_filter: str = "12m",
    company: Optional[str] = None,
    territory: Optional[str] = None,
    item_group: Optional[str] = None,
    sales_person: Optional[str] = None,
) -> Dict[str, Any]:
    """Drillable geography slice: revenue / gross profit / customers by
    territory, item group, salesperson or customer. The optional
    territory/item_group/sales_person args narrow the slice (drill-down)."""
    frappe.has_permission("Sales Invoice", "read", throw=True)
    from insights.ml.geography import compute_geography_breakdown
    return run(
        lambda: compute_geography_breakdown(
            dimension=dimension,
            date_filter=date_filter,
            company=company,
            territory=territory or None,
            item_group=item_group or None,
            sales_person=sales_person or None,
        ),
        "Geography breakdown",
    )


@frappe.whitelist()
def geography_options(
    date_filter: str = "12m", company: Optional[str] = None
) -> Dict[str, Any]:
    """Distinct territory / item group / salesperson values for the
    Geography tab filter selectors."""
    frappe.has_permission("Sales Invoice", "read", throw=True)
    from insights.ml.geography import compute_geography_options
    return run(
        lambda: compute_geography_options(date_filter=date_filter, company=company),
        "Geography options",
    )


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
def refresh_scores(date_filter: str = "12m", company: Optional[str] = None) -> Dict[str, Any]:
    """Queue a recompute of the customer intelligence payload.

    This used to run the compute inline, which on a full ledger is a request
    that outlives the gateway. It now queues the same job the dashboard's own
    cache miss would, for the caller's `date_filter` window, and returns
    immediately.
    """
    frappe.has_permission("Customer", "write", throw=True)
    enqueue_dashboard_compute(
        "insights.api.ml.customer_intelligence",
        {"date_filter": date_filter, "company": company},
        str(frappe.session.user),
        _scoped(f"insights_ml_customer_intelligence:{date_filter}:{company or 'all'}"),
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
def customer_counts_by_period(date_filter: str = "12m",
                              granularity: str = "auto",
                              active_cutoff_months: int = 6,
                              company: Optional[str] = None) -> Dict[str, Any]:
    """Buyers / new / repeat / reactivated per day, week or month."""
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_customer_counts_by_period
    return run(lambda: compute_customer_counts_by_period(date_filter=date_filter,
                                                         granularity=granularity,
                                                         active_cutoff_months=int(active_cutoff_months),
                                                         company=company),
               "Customer counts by period")


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
def bottom_customers(date_filter: str = "12m",
                     limit: int = 20,
                     company: Optional[str] = None) -> Dict[str, Any]:
    """Bottom customers by revenue, gross profit, margin %, consistency --
    weakest accounts, biggest losses, worst margins, most erratic spend."""
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_bottom_customers
    return run(lambda: compute_bottom_customers(date_filter=date_filter,
                                                limit=int(limit),
                                                company=company),
               "Bottom customers")


@frappe.whitelist()
def customer_scorecard(date_filter: str = "12m",
                       company: Optional[str] = None) -> Dict[str, Any]:
    """Unified per-customer scorecard for the Rankings tab: every customer
    with revenue, gross profit, margin %, months-active and consistency in
    one list, filtered and sorted client-side."""
    frappe.has_permission("Customer", "read", throw=True)
    from insights.ml.customer import compute_customer_scorecard
    return run(lambda: compute_customer_scorecard(date_filter=date_filter,
                                                  company=company),
               "Customer scorecard")


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
    # Same window as the KPI the drill-down belongs to (the dashboard's filter).
    date_filter = f.get("date_filter")

    def _in_window(db_filters, default=None):
        start_dt, end_dt = parse_date_filter(date_filter or default)
        if start_dt and end_dt:
            db_filters["posting_date"] = ("between", [start_dt.date(), end_dt.date()])
        return db_filters

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
        # Revenue KPIs are submitted, non-return invoices in the window.
        db_filters = _in_window({"docstatus": 1, "is_return": 0}, default="12m")
        if company:
            db_filters["company"] = company
        # The only caller (CustomerSections.vue Top/Bottom Customers by
        # Revenue tables) always passes `customer` -- one row's click drills
        # into that row's own invoices. Without this filter every row
        # returned the identical system-wide top-invoices list regardless
        # of which customer was clicked, under a misleading "<Name> Orders"
        # title. When a customer IS scoped, order by recency (most useful
        # for a single account); the unscoped fallback keeps the original
        # base_net_total-desc browse behaviour.
        customer = f.get("customer")
        if customer:
            db_filters["customer"] = customer
            order_by = "posting_date desc"
        else:
            order_by = "base_net_total desc"
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "customer", "posting_date", "base_net_total", "grand_total", "outstanding_amount"],
            start=start, page_length=page_size, order_by=order_by,
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Net Total", "fieldname": "base_net_total", "fieldtype": "Currency"},
                {"label": "Total (incl. tax)", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Invoice", filters=db_filters),
        }

    if metric == "new_customers":
        frappe.has_permission("Customer", throw=True)
        from insights.api.ml.ibis_source import default_company
        from insights.ml.customer import _si_base

        # Customers whose first-ever invoice falls in the window -- exactly
        # what the `customer_counts` "new" KPI (`new_by_first_txn`) counts.
        start_dt, end_dt = parse_date_filter(date_filter or "12m")
        si = _si_base(company or default_company())
        first = si.group_by(si.customer).aggregate(first_invoice=si.posting_date.min())
        if start_dt and end_dt:
            first = first.filter(first.first_invoice.between(start_dt.date(), end_dt.date()))
        first_df = first.order_by(first.first_invoice.desc(), "customer").execute()
        total = len(first_df)
        page_df = first_df.iloc[start:start + page_size]
        by_name = {
            r["name"]: r
            for r in frappe.get_list(
                "Customer",
                filters={"name": ("in", page_df["customer"].tolist())},
                fields=["name", "customer_name", "customer_group", "territory", "creation"],
                ignore_permissions=False,
            )
        }
        rows = [
            {**by_name[c], "first_invoice": fi}
            for c, fi in zip(page_df["customer"], page_df["first_invoice"])
            if c in by_name
        ]
        return {
            "columns": [
                {"label": "Customer", "fieldname": "name", "fieldtype": "Link", "options": "Customer"},
                {"label": "Name", "fieldname": "customer_name", "fieldtype": "Data"},
                {"label": "Group", "fieldname": "customer_group", "fieldtype": "Data"},
                {"label": "First Invoice", "fieldname": "first_invoice", "fieldtype": "Date"},
                {"label": "Created", "fieldname": "creation", "fieldtype": "Date"},
            ],
            "rows": rows,
            "total": total,
        }

    if metric == "reactivated_customers":
        frappe.has_permission("Customer", throw=True)
        from insights.api.ml.ibis_source import default_company
        from insights.ml.customer import reactivated_customers

        # Exactly what the `customer_counts` "reactivated" KPI counts.
        start_dt, end_dt = parse_date_filter(date_filter or "12m")
        react = reactivated_customers(
            company or default_company(), start_dt, end_dt, int(f.get("active_cutoff_months") or 6)
        )
        df = react.order_by(react.first_in_window.desc(), "customer").execute()
        page_df = df.iloc[start:start + page_size]
        by_name = {
            r["name"]: r
            for r in frappe.get_list(
                "Customer",
                filters={"name": ("in", page_df["customer"].tolist())},
                fields=["name", "customer_name", "customer_group", "territory"],
                ignore_permissions=False,
            )
        }
        rows = [
            {**by_name[c], "last_before": lb, "first_in_window": fi}
            for c, lb, fi in zip(page_df["customer"], page_df["last_before"], page_df["first_in_window"])
            if c in by_name
        ]
        return {
            "columns": [
                {"label": "Customer", "fieldname": "name", "fieldtype": "Link", "options": "Customer"},
                {"label": "Name", "fieldname": "customer_name", "fieldtype": "Data"},
                {"label": "Group", "fieldname": "customer_group", "fieldtype": "Data"},
                {"label": "Last Order Before", "fieldname": "last_before", "fieldtype": "Date"},
                {"label": "Back On", "fieldname": "first_in_window", "fieldtype": "Date"},
            ],
            "rows": rows,
            "total": len(df),
        }

    if metric == "customer_invoices":
        frappe.has_permission("Sales Invoice", throw=True)
        customer = f.get("customer")
        if not customer:
            frappe.throw(_("customer is required"), frappe.ValidationError)
        bucket = f.get("bucket", "all")  # all | outstanding | overdue
        # Lifetime unless the caller scopes a window (customer detail is lifetime).
        db_filters = _in_window({"docstatus": 1, "is_return": 0, "customer": customer})
        if company:
            db_filters["company"] = company
        if bucket in ("outstanding", "overdue"):
            db_filters["outstanding_amount"] = (">", 0)
        if bucket == "overdue":
            db_filters["due_date"] = ("<", frappe.utils.today())
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "posting_date", "due_date", "base_net_total", "grand_total", "outstanding_amount", "status"],
            start=start, page_length=page_size, order_by="posting_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date"},
                {"label": "Net Total", "fieldname": "base_net_total", "fieldtype": "Currency"},
                {"label": "Total (incl. tax)", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Invoice", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
