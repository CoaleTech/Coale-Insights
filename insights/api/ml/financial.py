# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Financial Intelligence API Endpoints (Ibis-backed)

Endpoints here compute against the site's own MariaDB through Ibis -- no
fork, no model training. `financial_intelligence` (the full dashboard
payload) fans out to two dozen of those queries and takes tens of seconds,
so it is served from cache and recomputed by a background job -- see
`insights.api.ml.utils` for the contract. Everything else here computes
fresh per call.
"""

from __future__ import annotations

from typing import Any, Dict

import frappe
from frappe.query_builder.functions import Sum
from frappe.utils import flt, nowdate
from insights.api.ml.utils import cached_run, canonical_date_filter, run


@frappe.whitelist()
def financial_intelligence(refresh: bool = False, date_filter: str = "12m") -> Dict[str, Any]:
    """Comprehensive financial intelligence: served from cache, recomputed in
    the background per date_filter."""
    frappe.has_permission("GL Entry", "read", throw=True)
    date_filter = canonical_date_filter(date_filter)
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
    if not isinstance(f, dict):
        frappe.throw(_("filters must be an object"), frappe.ValidationError)
    page = max(1, frappe.utils.cint(f.pop("page", 1)))
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
            fields=["name", "customer", "customer_name", "posting_date", "due_date", "grand_total", "outstanding_amount", "currency"],
            start=start, page_length=page_size, order_by="outstanding_amount desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Name", "fieldname": "customer_name", "fieldtype": "Data"},
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
            fields=["name", "customer", "customer_name", "posting_date", "due_date", "grand_total", "outstanding_amount"],
            start=start, page_length=page_size, order_by="due_date asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Name", "fieldname": "customer_name", "fieldtype": "Data"},
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
            fields=["name", "supplier", "supplier_name", "posting_date", "due_date", "grand_total", "outstanding_amount"],
            start=start, page_length=page_size, order_by="outstanding_amount desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Bill", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Invoice"},
                {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
                {"label": "Name", "fieldname": "supplier_name", "fieldtype": "Data"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date"},
                {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Purchase Invoice", filters=db_filters),
        }

    if metric in ("cash_accounts", "working_capital_components"):
        frappe.has_permission("Account", throw=True)
        frappe.has_permission("GL Entry", throw=True)
        # cash_accounts = what _calculate_cash_flow counts: Bank/Cash by account_type plus
        # Fixed Deposit accounts (no core account_type for FD, name-matched). Working
        # capital adds the Receivable/Payable/Stock accounts its figures are built from.
        # Its card is as of today; the Cash Position card includes future-dated postings.
        is_wc = metric == "working_capital_components"
        acct_filters = [["is_group", "=", 0]]
        if company:
            acct_filters.append(["company", "=", company])
        if f.get("account"):  # one row clicked on the Cash tab
            acct_filters.append(["name", "=", f["account"]])
        acct_or_filters = [
            ["account_type", "in", ["Cash", "Bank", "Receivable", "Payable", "Stock"] if is_wc else ["Cash", "Bank"]],
            ["account_name", "like", "fixed deposit%"],
        ]
        rows = frappe.get_list(
            "Account",
            filters=acct_filters,
            or_filters=acct_or_filters,
            fields=["name", "account_name", "account_type", "account_currency"],
            start=start, page_length=page_size, order_by="account_name asc",
            ignore_permissions=False,
        )
        GL = frappe.qb.DocType("GL Entry")
        names = [r["name"] for r in rows]
        bal = {}
        if names:
            q = (
                frappe.qb.from_(GL)
                .select(GL.account, Sum(GL.debit - GL.credit))
                .where((GL.account.isin(names)) & (GL.is_cancelled == 0))
            )
            if is_wc:
                q = q.where(GL.posting_date <= nowdate())
            bal = dict(q.groupby(GL.account).run())
        for r in rows:
            r["balance"] = flt(bal.get(r["name"]))
            r["account_type"] = r["account_type"] or "Fixed Deposit"
        return {
            "columns": [
                {"label": "Account", "fieldname": "name", "fieldtype": "Link", "options": "Account"},
                {"label": "Account Name", "fieldname": "account_name", "fieldtype": "Data"},
                {"label": "Type", "fieldname": "account_type", "fieldtype": "Data"},
                {"label": "Currency", "fieldname": "account_currency", "fieldtype": "Data"},
                {"label": "Balance (Dr − Cr)" if is_wc else "Balance", "fieldname": "balance", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.get_list(
                "Account", filters=acct_filters, or_filters=acct_or_filters,
                fields=[{"COUNT": "name", "as": "c"}],
            )[0].c,
        }

    if metric == "cost_structure_accounts":
        frappe.has_permission("Account", throw=True)
        db_filters = {"is_group": 0, "root_type": "Expense"}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Account",
            filters=db_filters,
            fields=["name", "account_name", "parent_account", "account_currency"],
            start=start, page_length=page_size, order_by="account_name asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Account", "fieldname": "name", "fieldtype": "Link", "options": "Account"},
                {"label": "Account Name", "fieldname": "account_name", "fieldtype": "Data"},
                {"label": "Parent", "fieldname": "parent_account", "fieldtype": "Data"},
                {"label": "Currency", "fieldname": "account_currency", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Account", filters=db_filters),
        }

    if metric == "forex_exposure":
        frappe.has_permission("Account", throw=True)
        columns = [
            {"label": "Account", "fieldname": "name", "fieldtype": "Link", "options": "Account"},
            {"label": "Account Name", "fieldname": "account_name", "fieldtype": "Data"},
            {"label": "Currency", "fieldname": "account_currency", "fieldtype": "Data"},
            {"label": "Type", "fieldname": "account_type", "fieldtype": "Data"},
        ]
        default_currency = (
            frappe.get_cached_value("Company", company, "default_currency") if company else None
        )
        # "Foreign" is only definable against a reporting currency. Without one
        # there is no exposure to list -- which is not the same as an error, and
        # not the same as zero exposure either; the empty table says so.
        if not default_currency:
            return {"columns": columns, "rows": [], "total": 0}
        db_filters = [
            ["is_group", "=", 0],
            ["company", "=", company],
            ["account_currency", "!=", default_currency],
        ]
        rows = frappe.get_list(
            "Account",
            filters=db_filters,
            fields=["name", "account_name", "account_currency", "account_type"],
            start=start, page_length=page_size, order_by="account_name asc",
            ignore_permissions=False,
        )
        return {
            "columns": columns,
            "rows": rows,
            "total": frappe.db.count("Account", filters=db_filters),
        }

    if metric in ("top_customers_ar", "top_suppliers_ap", "overdue_ap_90"):
        # One party's open invoices (top_*), or Purchase Invoices > 90 days past due.
        is_ar = metric == "top_customers_ar"
        doctype = "Sales Invoice" if is_ar else "Purchase Invoice"
        party_field = "customer" if is_ar else "supplier"
        frappe.has_permission(doctype, throw=True)
        db_filters = {"docstatus": 1, "outstanding_amount": (">", 0)}
        if company:
            db_filters["company"] = company
        if metric == "overdue_ap_90":
            db_filters["due_date"] = ("<", frappe.utils.add_days(frappe.utils.today(), -90))
            order_by = "due_date asc"
        else:
            party = f.get(party_field)
            if not party or not isinstance(party, str):
                frappe.throw(_("{0} is required").format(_(party_field.title())), frappe.ValidationError)
            db_filters[party_field] = party
            if is_ar:  # the tile lists overdue customers, so the drill lists their overdue invoices
                db_filters["due_date"] = ("<", frappe.utils.today())
            order_by = "outstanding_amount desc"
        rows = frappe.get_list(
            doctype,
            filters=db_filters,
            fields=["name", party_field, f"{party_field}_name", "posting_date", "due_date", "grand_total", "outstanding_amount"],
            start=start, page_length=page_size, order_by=order_by,
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": _("Invoice") if is_ar else _("Bill"), "fieldname": "name", "fieldtype": "Link", "options": doctype},
                {"label": _(party_field.title()), "fieldname": party_field, "fieldtype": "Link", "options": party_field.title()},
                {"label": _("Name"), "fieldname": f"{party_field}_name", "fieldtype": "Data"},
                {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": _("Due Date"), "fieldname": "due_date", "fieldtype": "Date"},
                {"label": _("Total"), "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": _("Outstanding"), "fieldname": "outstanding_amount", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count(doctype, filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
