# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Financial Intelligence API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any
from insights.api.response import success, error


@frappe.whitelist()
def financial_intelligence(refresh: bool = False, date_filter: str = '12m') -> Dict[str, Any]:
    """Get comprehensive financial intelligence"""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence(date_filter=date_filter)
        if refresh:
            return model.train()
        return model.predict()
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def train_financial_intelligence() -> Dict[str, Any]:
    """Train financial intelligence models"""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model.train()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_financial_overview() -> Dict[str, Any]:
    """Get financial overview"""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._calculate_financial_overview()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_cash_flow_analysis() -> Dict[str, Any]:
    """Get cash flow analysis"""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._calculate_cash_flow()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_receivables_analysis() -> Dict[str, Any]:
    """Get receivables analysis"""
    try:
        frappe.has_permission("Sales Invoice", "read", throw=True)
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._analyze_receivables()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_payables_analysis() -> Dict[str, Any]:
    """Get payables analysis"""
    try:
        frappe.has_permission("Purchase Invoice", "read", throw=True)
        from insights.ml.financial_intelligence import FinancialIntelligence
        model = FinancialIntelligence()
        result = model._analyze_payables()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))

# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_finance_detail(metric: str, filters: str) -> dict:
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
