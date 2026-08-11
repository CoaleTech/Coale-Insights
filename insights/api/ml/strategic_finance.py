# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Strategic Finance Intelligence API Endpoints
"""

import frappe
from frappe import _
from typing import Dict, Any
from insights.api.response import success, error


@frappe.whitelist()
def strategic_finance_intelligence(refresh: bool = False, date_filter: str = "12m") -> Dict[str, Any]:
    """Get strategic finance intelligence analysis"""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        from insights.ml.strategic_finance_intelligence import run_strategic_finance_intelligence
        return run_strategic_finance_intelligence(refresh=refresh)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def get_budget_variance_overview(company: str = None, fiscal_year: str = None) -> Dict[str, Any]:
    """Get budget variance overview"""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        from insights.ml.budget_variance_intelligence import BudgetVarianceIntelligence
    
        model = BudgetVarianceIntelligence()
        result = model.get_budget_variance_overview()
        return success(result)
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_strategic_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")

    if metric == "revenue_invoices":
        frappe.has_permission("Sales Invoice", throw=True)
        db_filters = {"docstatus": 1}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Sales Invoice",
            filters=db_filters,
            fields=["name", "customer", "posting_date", "grand_total", "outstanding_amount"],
            start=start, page_length=page_size, order_by="posting_date desc",
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

    if metric == "expense_entries":
        frappe.has_permission("Purchase Invoice", throw=True)
        db_filters = {"docstatus": 1}
        if company:
            db_filters["company"] = company
        rows = frappe.get_list(
            "Purchase Invoice",
            filters=db_filters,
            fields=["name", "supplier", "posting_date", "grand_total", "outstanding_amount"],
            start=start, page_length=page_size, order_by="posting_date desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Bill", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Invoice"},
                {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Total", "fieldname": "grand_total", "fieldtype": "Currency"},
                {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency"},
            ],
            "rows": rows,
            "total": frappe.db.count("Purchase Invoice", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
