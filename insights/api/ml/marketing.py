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
