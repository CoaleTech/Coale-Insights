# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Marketing Intelligence API Endpoints
"""

import frappe
from typing import Dict, Any
from insights.api.response import success, error


@frappe.whitelist()
def source_metrics(period: str = "YTD") -> Dict[str, Any]:
    """Get lead source metrics including cost per lead."""
    try:
        from insights.ml.marketing_source_metrics import (
            get_leads_by_source,
            get_hot_leads_by_source,
            get_cost_per_lead,
            get_territory_leads,
        )
        from frappe.utils import nowdate, add_months
        from datetime import datetime

        end_date = nowdate()
        if period == "MTD":
            start_date = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        elif period == "QTD":
            current_month = datetime.now().month
            quarter_start_month = ((current_month - 1) // 3) * 3 + 1
            start_date = datetime.now().replace(month=quarter_start_month, day=1).strftime("%Y-%m-%d")
        elif period == "YTD":
            start_date = datetime.now().replace(month=1, day=1).strftime("%Y-%m-%d")
        else:  # TTM
            start_date = add_months(end_date, -12)

        return success({
            "leads_by_source": get_leads_by_source(start_date, end_date),
            "hot_leads_by_source": get_hot_leads_by_source(start_date, end_date),
            "cost_per_lead": get_cost_per_lead(start_date, end_date),
            "territory_leads": get_territory_leads(start_date, end_date),
        })
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def cost_per_lead(period: str = "YTD") -> Dict[str, Any]:
    """Get cost per lead by source."""
    try:
        from insights.ml.marketing_source_metrics import get_cost_per_lead
        from frappe.utils import nowdate, add_months
        from datetime import datetime

        end_date = nowdate()
        if period == "MTD":
            start_date = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        elif period == "QTD":
            current_month = datetime.now().month
            quarter_start_month = ((current_month - 1) // 3) * 3 + 1
            start_date = datetime.now().replace(month=quarter_start_month, day=1).strftime("%Y-%m-%d")
        elif period == "YTD":
            start_date = datetime.now().replace(month=1, day=1).strftime("%Y-%m-%d")
        else:  # TTM
            start_date = add_months(end_date, -12)

        return success(get_cost_per_lead(start_date, end_date))
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def territory_leads(period: str = "YTD") -> Dict[str, Any]:
    """Get lead count by territory."""
    try:
        from insights.ml.marketing_source_metrics import get_territory_leads
        from frappe.utils import nowdate, add_months
        from datetime import datetime

        end_date = nowdate()
        if period == "MTD":
            start_date = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        elif period == "QTD":
            current_month = datetime.now().month
            quarter_start_month = ((current_month - 1) // 3) * 3 + 1
            start_date = datetime.now().replace(month=quarter_start_month, day=1).strftime("%Y-%m-%d")
        elif period == "YTD":
            start_date = datetime.now().replace(month=1, day=1).strftime("%Y-%m-%d")
        else:  # TTM
            start_date = add_months(end_date, -12)

        return success(get_territory_leads(start_date, end_date))
    except Exception as e:
        return error(str(e))


# ─── Drill-Down ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_crm_detail(metric: str, filters: str) -> dict:
    f = frappe.parse_json(filters) or {}
    page = int(f.pop("page", 1))
    page_size = 50
    start = (page - 1) * page_size
    company = f.get("company") or frappe.defaults.get_user_default("company")

    if metric == "leads":
        frappe.has_permission("Lead", throw=True)
        rows = frappe.get_list(
            "Lead",
            filters={"docstatus": 0},
            fields=["name", "lead_name", "company_name", "status", "source", "lead_owner", "creation"],
            start=start, page_length=page_size, order_by="creation desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Lead", "fieldname": "name", "fieldtype": "Link", "options": "Lead"},
                {"label": "Name", "fieldname": "lead_name", "fieldtype": "Data"},
                {"label": "Company", "fieldname": "company_name", "fieldtype": "Data"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
                {"label": "Source", "fieldname": "source", "fieldtype": "Data"},
                {"label": "Owner", "fieldname": "lead_owner", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Lead", filters={"docstatus": 0}),
        }

    if metric == "opportunities":
        frappe.has_permission("Opportunity", throw=True)
        db_filters = {"docstatus": 0, "status": ("not in", ["Closed", "Lost"])}
        rows = frappe.get_list(
            "Opportunity",
            filters=db_filters,
            fields=["name", "opportunity_from", "party_name", "opportunity_amount", "expected_closing", "status", "sales_stage"],
            start=start, page_length=page_size, order_by="expected_closing asc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Opportunity", "fieldname": "name", "fieldtype": "Link", "options": "Opportunity"},
                {"label": "From", "fieldname": "party_name", "fieldtype": "Data"},
                {"label": "Amount", "fieldname": "opportunity_amount", "fieldtype": "Currency"},
                {"label": "Closing", "fieldname": "expected_closing", "fieldtype": "Date"},
                {"label": "Stage", "fieldname": "sales_stage", "fieldtype": "Data"},
                {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
            ],
            "rows": rows,
            "total": frappe.db.count("Opportunity", filters=db_filters),
        }

    if metric == "lost_opportunities":
        frappe.has_permission("Opportunity", throw=True)
        db_filters = {"docstatus": 0, "status": "Lost"}
        rows = frappe.get_list(
            "Opportunity",
            filters=db_filters,
            fields=["name", "party_name", "opportunity_amount", "lost_reasons", "modified"],
            start=start, page_length=page_size, order_by="modified desc",
            ignore_permissions=False,
        )
        return {
            "columns": [
                {"label": "Opportunity", "fieldname": "name", "fieldtype": "Link", "options": "Opportunity"},
                {"label": "From", "fieldname": "party_name", "fieldtype": "Data"},
                {"label": "Amount", "fieldname": "opportunity_amount", "fieldtype": "Currency"},
                {"label": "Date", "fieldname": "modified", "fieldtype": "Date"},
            ],
            "rows": rows,
            "total": frappe.db.count("Opportunity", filters=db_filters),
        }

    frappe.throw(_("Unknown metric: {0}").format(metric), frappe.ValidationError)
