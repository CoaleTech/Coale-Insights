# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Customer Data Collector - Customer segments, retention, lifetime value, leads"""

import frappe
from frappe.query_builder.functions import Coalesce, Count, DateFormat, Max, Min, Sum
from frappe.utils import add_months, cint, flt
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
            "leads": self._get_lead_metrics(),
        }

    def _get_customer_summary(self) -> Dict[str, Any]:
        """Get customer summary"""
        total_customers = frappe.db.count("Customer", {"disabled": 0})

        SalesInvoice = frappe.qb.DocType("Sales Invoice")
        active_customers = (
            frappe.qb.from_(SalesInvoice)
            .select(Count(SalesInvoice.customer).distinct().as_("count"))
            .where(
                (SalesInvoice.posting_date.between(self.from_date, self.to_date))
                & (SalesInvoice.company == self.company)
                & (SalesInvoice.docstatus == 1)
            )
            .run(as_dict=True)
        )

        return {
            "total_customers": total_customers,
            "active_customers": cint(active_customers[0].get("count")) if active_customers else 0,
        }

    def _get_new_customers(self) -> Dict[str, Any]:
        """Get new customers in period"""
        Customer = frappe.qb.DocType("Customer")
        result = (
            frappe.qb.from_(Customer)
            .select(Count("*").as_("count"))
            .where(
                (Customer.creation.between(self.from_date, self.to_date))
                & (Customer.disabled == 0)
            )
            .run(as_dict=True)
        )

        # Monthly trend
        period = DateFormat(Customer.creation, "%Y-%m").as_("month")
        trend = (
            frappe.qb.from_(Customer)
            .select(period, Count("*").as_("new_customers"))
            .where(
                (Customer.creation.between(self.from_date, self.to_date))
                & (Customer.disabled == 0)
            )
            .groupby(period)
            .orderby(period)
            .run(as_dict=True)
        )

        return {
            "total_new": cint(result[0].get("count")) if result else 0,
            "monthly_trend": trend,
        }

    def _get_customer_segments(self) -> List[Dict]:
        """Get customer segments by revenue"""
        Customer = frappe.qb.DocType("Customer")
        SalesInvoice = frappe.qb.DocType("Sales Invoice")

        return (
            frappe.qb.from_(Customer)
            .left_join(SalesInvoice)
            .on(
                (Customer.name == SalesInvoice.customer)
                & (SalesInvoice.posting_date.between(self.from_date, self.to_date))
                & (SalesInvoice.company == self.company)
                & (SalesInvoice.docstatus == 1)
            )
            .select(
                Customer.customer_group.as_("segment"),
                Count(Customer.name).distinct().as_("customer_count"),
                Coalesce(Sum(SalesInvoice.grand_total), 0).as_("total_revenue"),
            )
            .where(Customer.disabled == 0)
            .groupby(Customer.customer_group)
            .orderby(Coalesce(Sum(SalesInvoice.grand_total), 0), order=frappe.qb.desc)
            .run(as_dict=True)
        )

    def _get_retention_metrics(self) -> Dict[str, Any]:
        """Calculate customer retention metrics"""
        # Customers who purchased in both current and previous period
        prev_from = add_months(self.from_date, -12)
        prev_to = add_months(self.to_date, -12)

        SalesInvoice = frappe.qb.DocType("Sales Invoice")

        prev_customers = (
            frappe.qb.from_(SalesInvoice)
            .select(SalesInvoice.customer)
            .distinct()
            .where(
                (SalesInvoice.posting_date.between(prev_from, prev_to))
                & (SalesInvoice.company == self.company)
                & (SalesInvoice.docstatus == 1)
            )
            .run()
        )
        prev_set = set(c[0] for c in prev_customers)

        current_customers = (
            frappe.qb.from_(SalesInvoice)
            .select(SalesInvoice.customer)
            .distinct()
            .where(
                (SalesInvoice.posting_date.between(self.from_date, self.to_date))
                & (SalesInvoice.company == self.company)
                & (SalesInvoice.docstatus == 1)
            )
            .run()
        )
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
            "churn_rate": round(churn_rate, 2),
        }

    def _get_top_ltv_customers(self, limit: int = 10) -> List[Dict]:
        """Get top customers by lifetime value"""
        SalesInvoice = frappe.qb.DocType("Sales Invoice")

        return (
            frappe.qb.from_(SalesInvoice)
            .select(
                SalesInvoice.customer,
                SalesInvoice.customer_name,
                Sum(SalesInvoice.grand_total).as_("lifetime_value"),
                Count("*").as_("total_orders"),
                Min(SalesInvoice.posting_date).as_("first_order"),
                Max(SalesInvoice.posting_date).as_("last_order"),
            )
            .where(
                (SalesInvoice.company == self.company) & (SalesInvoice.docstatus == 1)
            )
            .groupby(SalesInvoice.customer, SalesInvoice.customer_name)
            .orderby(Sum(SalesInvoice.grand_total), order=frappe.qb.desc)
            .limit(limit)
            .run(as_dict=True)
        )

    def _get_lead_metrics(self) -> Dict[str, Any]:
        """Get lead metrics from CRM"""
        total_leads = frappe.db.count(
            "Lead",
            {"creation": ["between", [self.from_date, self.to_date]]},
        )

        converted = frappe.db.count(
            "Lead",
            {
                "creation": ["between", [self.from_date, self.to_date]],
                "status": "Converted",
            },
        )

        conversion_rate = (converted / total_leads * 100) if total_leads else 0

        # Lead sources
        Lead = frappe.qb.DocType("Lead")
        sources = (
            frappe.qb.from_(Lead)
            .select(Lead.source, Count("*").as_("count"))
            .where(Lead.creation.between(self.from_date, self.to_date))
            .groupby(Lead.source)
            .orderby(Count("*"), order=frappe.qb.desc)
            .limit(10)
            .run(as_dict=True)
        )

        return {
            "total_leads": total_leads,
            "converted_leads": converted,
            "conversion_rate": round(conversion_rate, 2),
            "lead_sources": sources,
        }
