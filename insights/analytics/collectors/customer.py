# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Customer Data Collector - Customer segments, retention, lifetime value, leads"""

import frappe
from frappe.utils import add_months, flt, cint
from typing import Dict, Any, List

from insights.analytics.collectors.base import BaseCollector


class CustomerDataCollector(BaseCollector):
    """Collect customer data from CRM module"""

    def collect(self) -> Dict[str, Any]:
        return {
            "summary": self._get_customer_summary(),
            "new_customers": self._get_new_customers(),
            "customer_segments": self._get_customer_segments(),
            "retention": self._get_retention_metrics(),
            "lifetime_value": self._get_top_ltv_customers(),
            "leads": self._get_lead_metrics()
        }

    def _get_customer_summary(self) -> Dict[str, Any]:
        """Get customer summary"""
        total_customers = frappe.db.count("Customer", {"disabled": 0})

        active_customers = frappe.db.sql("""
            SELECT COUNT(DISTINCT customer) as count
            FROM `tabSales Invoice`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
        """, (self.from_date, self.to_date, self.company), as_dict=True)

        return {
            "total_customers": total_customers,
            "active_customers": cint(active_customers[0].get("count")) if active_customers else 0
        }

    def _get_new_customers(self) -> Dict[str, Any]:
        """Get new customers in period"""
        result = frappe.db.sql("""
            SELECT COUNT(*) as count
            FROM `tabCustomer`
            WHERE creation BETWEEN %s AND %s
            AND disabled = 0
        """, (self.from_date, self.to_date), as_dict=True)

        # Monthly trend
        trend = frappe.db.sql("""
            SELECT
                DATE_FORMAT(creation, '%%Y-%%m') as month,
                COUNT(*) as new_customers
            FROM `tabCustomer`
            WHERE creation BETWEEN %s AND %s
            AND disabled = 0
            GROUP BY month
            ORDER BY month
        """, (self.from_date, self.to_date), as_dict=True)

        return {
            "total_new": cint(result[0].get("count")) if result else 0,
            "monthly_trend": trend
        }

    def _get_customer_segments(self) -> List[Dict]:
        """Get customer segments by revenue"""
        return frappe.db.sql("""
            SELECT
                c.customer_group as segment,
                COUNT(DISTINCT c.name) as customer_count,
                COALESCE(SUM(si.grand_total), 0) as total_revenue
            FROM `tabCustomer` c
            LEFT JOIN `tabSales Invoice` si ON c.name = si.customer
                AND si.posting_date BETWEEN %s AND %s
                AND si.company = %s
                AND si.docstatus = 1
            WHERE c.disabled = 0
            GROUP BY c.customer_group
            ORDER BY total_revenue DESC
        """, (self.from_date, self.to_date, self.company), as_dict=True)

    def _get_retention_metrics(self) -> Dict[str, Any]:
        """Calculate customer retention metrics"""
        # Customers who purchased in both current and previous period
        prev_from = add_months(self.from_date, -12)
        prev_to = add_months(self.to_date, -12)

        prev_customers = frappe.db.sql("""
            SELECT DISTINCT customer
            FROM `tabSales Invoice`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
        """, (prev_from, prev_to, self.company))
        prev_set = set(c[0] for c in prev_customers)

        current_customers = frappe.db.sql("""
            SELECT DISTINCT customer
            FROM `tabSales Invoice`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND docstatus = 1
        """, (self.from_date, self.to_date, self.company))
        current_set = set(c[0] for c in current_customers)

        retained = prev_set.intersection(current_set)
        churned = prev_set - current_set

        retention_rate = (len(retained) / len(prev_set) * 100) if prev_set else 0
        churn_rate = (len(churned) / len(prev_set) * 100) if prev_set else 0

        return {
            "previous_period_customers": len(prev_set),
            "retained_customers": len(retained),
            "churned_customers": len(churned),
            "retention_rate": round(retention_rate, 2),
            "churn_rate": round(churn_rate, 2)
        }

    def _get_top_ltv_customers(self, limit: int = 10) -> List[Dict]:
        """Get top customers by lifetime value"""
        return frappe.db.sql("""
            SELECT
                customer,
                customer_name,
                SUM(grand_total) as lifetime_value,
                COUNT(*) as total_orders,
                MIN(posting_date) as first_order,
                MAX(posting_date) as last_order
            FROM `tabSales Invoice`
            WHERE company = %s
            AND docstatus = 1
            GROUP BY customer, customer_name
            ORDER BY lifetime_value DESC
            LIMIT %s
        """, (self.company, limit), as_dict=True)

    def _get_lead_metrics(self) -> Dict[str, Any]:
        """Get lead metrics from CRM"""
        total_leads = frappe.db.count("Lead", {
            "creation": ["between", [self.from_date, self.to_date]]
        })

        converted = frappe.db.count("Lead", {
            "creation": ["between", [self.from_date, self.to_date]],
            "status": "Converted"
        })

        conversion_rate = (converted / total_leads * 100) if total_leads else 0

        # Lead sources
        sources = frappe.db.sql("""
            SELECT
                source,
                COUNT(*) as count
            FROM `tabLead`
            WHERE creation BETWEEN %s AND %s
            GROUP BY source
            ORDER BY count DESC
            LIMIT 10
        """, (self.from_date, self.to_date), as_dict=True)

        return {
            "total_leads": total_leads,
            "converted_leads": converted,
            "conversion_rate": round(conversion_rate, 2),
            "lead_sources": sources
        }
