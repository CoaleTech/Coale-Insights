# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Financial Intelligence API Endpoints (Ibis-backed)

All endpoints are synchronous, computed fresh per call, against the site's
own MariaDB through Ibis. No background jobs, no fork. `financial_intelligence`
(the full dashboard payload) is cached for 1 hour per date_filter via
`cached_run` -- see `insights.api.ml.utils` for why. Everything else here
has no cache.
"""

from __future__ import annotations

from typing import Any, Dict

import frappe
from insights.api.ml.utils import cached_run, run


@frappe.whitelist()
def financial_intelligence(refresh: bool = False, date_filter: str = "12m") -> Dict[str, Any]:
    """Get comprehensive financial intelligence, cached for 1 hour per date_filter."""
    frappe.has_permission("GL Entry", "read", throw=True)
    from insights.ml.financial_intelligence import FinancialIntelligence
    return cached_run(
        lambda: run(
            lambda: FinancialIntelligence(date_filter=date_filter).train(),
            "financial_intelligence",
        ),
        cache_key=f"insights_ml_financial_intelligence:{date_filter}",
    )


@frappe.whitelist()
def train_financial_intelligence() -> Dict[str, Any]:
    """Train financial intelligence models (synchronous, computes now)."""
    frappe.has_permission("GL Entry", "read", throw=True)
    from insights.ml.financial_intelligence import FinancialIntelligence
    return run(
        lambda: FinancialIntelligence().train(),
        "train_financial_intelligence",
    )


@frappe.whitelist()
def get_financial_overview() -> Dict[str, Any]:
    """Get P&L financial overview only."""
    frappe.has_permission("GL Entry", "read", throw=True)
    from insights.ml.financial_intelligence import FinancialIntelligence
    return run(
        lambda: FinancialIntelligence()._calculate_financial_overview(),
        "get_financial_overview",
    )


@frappe.whitelist()
def get_cash_flow_analysis() -> Dict[str, Any]:
    """Get cash flow analysis only."""
    frappe.has_permission("GL Entry", "read", throw=True)
    from insights.ml.financial_intelligence import FinancialIntelligence
    return run(
        lambda: FinancialIntelligence()._calculate_cash_flow(),
        "get_cash_flow_analysis",
    )


@frappe.whitelist()
def get_receivables_analysis() -> Dict[str, Any]:
    """Get receivables analysis only."""
    frappe.has_permission("Sales Invoice", "read", throw=True)
    from insights.ml.financial_intelligence import FinancialIntelligence
    return run(
        lambda: FinancialIntelligence()._analyze_receivables(),
        "get_receivables_analysis",
    )


@frappe.whitelist()
def get_payables_analysis() -> Dict[str, Any]:
    """Get payables analysis only."""
    frappe.has_permission("Purchase Invoice", "read", throw=True)
    from insights.ml.financial_intelligence import FinancialIntelligence
    return run(
        lambda: FinancialIntelligence()._analyze_payables(),
        "get_payables_analysis",
    )


@frappe.whitelist()
def get_forex_exposure() -> Dict[str, Any]:
    """Get forex exposure analysis only."""
    frappe.has_permission("GL Entry", "read", throw=True)
    from insights.ml.financial_intelligence import FinancialIntelligence
    return run(
        lambda: FinancialIntelligence()._analyze_forex_exposure(),
        "get_forex_exposure",
    )


# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_finance_detail(metric: str, filters: str) -> dict:
    from frappe import _
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")

    if metric == "outstanding_ar":
        frappe.has_permission("Sales Invoice", throw=True)
        db_filters = {"docstatus": 1, "outstanding_amount": (">", 0)}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "customer", "posting_date", "due_date", "grand_total", "outstanding_amount", "currency"],
            start=start, page_length=page_size, order_by="outstanding_amount desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Invoice", filters=db_filters),
        }

    if metric == "overdue_ar_90":
        frappe.has_permission("Sales Invoice", throw=True)
        cutoff = frappe.utils.add_days(frappe.utils.today(), -90)
        db_filters = {"docstatus": 1, "outstanding_amount": (">", 0), "due_date": ("<", cutoff)}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "customer", "posting_date", "due_date", "grand_total", "outstanding_amount"],
            start=start, page_length=page_size, order_by="due_date asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date"},
                {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Sales Invoice", filters=db_filters),
        }

    if metric == "outstanding_ap":
        frappe.has_permission("Purchase Invoice", throw=True)
        db_filters = {"docstatus": 1, "outstanding_amount": (">", 0)}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Purchase Invoice",
            filters=db_filters,
            fields=["name", "supplier", "posting_date", "due_date", "grand_total", "outstanding_amount"],
            start=start, page_length=page_size, order_by="outstanding_amount desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Bill", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Invoice"},
                {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date"},
                {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Purchase Invoice", filters=db_filters),
        }

    if metric == "cash_accounts":
        frappe.has_permission("Account", throw=True)
        db_filters = {"account_type": ("in", ["Cash", "Bank"]), "is_group": 0}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Account",
            filters=db_filters,
            fields=["name", "account_name", "account_type", "account_currency"],
            start=start, page_length=page_size, order_by="account_name asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Account", "fieldname": "name", "fieldtype": "Link", "options": "Account"},
                {"label": "Account Name", "fieldname": "account_name", "fieldtype": "Data"},
                {"label": "Type", "fieldname": "account_type", "fieldtype": "Data"},
                {"label": "Currency", "fieldname": "account_currency", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Account", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
