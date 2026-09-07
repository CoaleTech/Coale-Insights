# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Financial Data Collector - Revenue, expenses, profit/loss, cash flow analysis"""

import frappe
from frappe.utils import add_months, flt, cint
from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import (
    Abs,
    Avg,
    Coalesce,
    Count,
    CurDate,
    DateFormat,
    Sum,
)
from pypika.terms import CustomFunction
from typing import Dict, Any, List

from insights.analytics.collectors.base import BaseCollector

_DateDiff = CustomFunction("DATEDIFF", ["date1", "date2"])


class FinancialDataCollector(BaseCollector):
    """Collect financial data from Accounts module"""

    def collect(self) -> Dict[str, Any]:
        return {
            "revenue": self._get_revenue(),
            "expenses": self._get_expenses(),
            "profit_loss": self._get_profit_loss(),
            "cash_flow": self._get_cash_flow(),
            "receivables": self._get_receivables(),
            "payables": self._get_payables(),
            "bank_balance": self._get_bank_balance(),
            "monthly_trend": self._get_monthly_trend()
        }

    def _get_revenue(self) -> Dict[str, Any]:
        """Get revenue summary using JOIN instead of subquery for better index usage"""
        gle = DocType("GL Entry")
        acc = DocType("Account")

        result = (
            frappe.qb.from_(gle)
            .inner_join(acc)
            .on(gle.account == acc.name)
            .select(Coalesce(Sum(gle.debit - gle.credit), 0).as_("total_revenue"))
            .where(gle.posting_date.between(self.from_date, self.to_date))
            .where(gle.company == self.company)
            .where(acc.root_type == "Income")
            .where(gle.is_cancelled == 0)
            .run(as_dict=True)
        )

        total = abs(flt(result[0].get("total_revenue"))) if result else 0

        # Get previous period for comparison
        prev_from = add_months(self.from_date, -12)
        prev_to = add_months(self.to_date, -12)

        prev_result = (
            frappe.qb.from_(gle)
            .inner_join(acc)
            .on(gle.account == acc.name)
            .select(Coalesce(Sum(gle.debit - gle.credit), 0).as_("total_revenue"))
            .where(gle.posting_date.between(prev_from, prev_to))
            .where(gle.company == self.company)
            .where(acc.root_type == "Income")
            .where(gle.is_cancelled == 0)
            .run(as_dict=True)
        )

        prev_total = abs(flt(prev_result[0].get("total_revenue"))) if prev_result else 0
        growth = ((total - prev_total) / prev_total * 100) if prev_total else 0

        return {
            "total": total,
            "previous_period": prev_total,
            "growth_percent": round(growth, 2)
        }

    def _get_expenses(self) -> Dict[str, Any]:
        """Get expense summary using JOIN instead of subquery"""
        gle = DocType("GL Entry")
        acc = DocType("Account")

        result = (
            frappe.qb.from_(gle)
            .inner_join(acc)
            .on(gle.account == acc.name)
            .select(Coalesce(Sum(gle.debit - gle.credit), 0).as_("total_expense"))
            .where(gle.posting_date.between(self.from_date, self.to_date))
            .where(gle.company == self.company)
            .where(acc.root_type == "Expense")
            .where(gle.is_cancelled == 0)
            .run(as_dict=True)
        )

        total = flt(result[0].get("total_expense")) if result else 0

        # Top expense categories
        top_expenses = (
            frappe.qb.from_(gle)
            .join(acc)
            .on(gle.account == acc.name)
            .select(
                acc.parent_account.as_("category"),
                Coalesce(Sum(gle.debit - gle.credit), 0).as_("amount"),
            )
            .where(gle.posting_date.between(self.from_date, self.to_date))
            .where(gle.company == self.company)
            .where(acc.root_type == "Expense")
            .where(gle.is_cancelled == 0)
            .groupby(acc.parent_account)
            .orderby(Sum(gle.debit - gle.credit), order=frappe.qb.desc)
            .limit(10)
            .run(as_dict=True)
        )

        return {
            "total": total,
            "top_categories": top_expenses
        }

    def _get_profit_loss(self) -> Dict[str, Any]:
        """Calculate profit/loss"""
        revenue = self._get_revenue()
        expenses = self._get_expenses()

        net_profit = revenue["total"] - expenses["total"]
        margin = (net_profit / revenue["total"] * 100) if revenue["total"] else 0

        return {
            "revenue": revenue["total"],
            "expenses": expenses["total"],
            "net_profit": net_profit,
            "profit_margin": round(margin, 2)
        }

    def _get_cash_flow(self) -> Dict[str, Any]:
        """Get cash flow data"""
        pe = DocType("Payment Entry")

        # Cash inflows (receipts)
        inflows = (
            frappe.qb.from_(pe)
            .select(Coalesce(Sum(pe.paid_amount), 0).as_("total"))
            .where(pe.posting_date.between(self.from_date, self.to_date))
            .where(pe.company == self.company)
            .where(pe.payment_type == "Receive")
            .where(pe.docstatus == 1)
            .run(as_dict=True)
        )

        # Cash outflows (payments)
        outflows = (
            frappe.qb.from_(pe)
            .select(Coalesce(Sum(pe.paid_amount), 0).as_("total"))
            .where(pe.posting_date.between(self.from_date, self.to_date))
            .where(pe.company == self.company)
            .where(pe.payment_type == "Pay")
            .where(pe.docstatus == 1)
            .run(as_dict=True)
        )

        total_in = flt(inflows[0].get("total")) if inflows else 0
        total_out = flt(outflows[0].get("total")) if outflows else 0

        return {
            "inflows": total_in,
            "outflows": total_out,
            "net_cash_flow": total_in - total_out
        }

    def _get_receivables(self) -> Dict[str, Any]:
        """Get accounts receivable summary"""
        si = DocType("Sales Invoice")

        result = (
            frappe.qb.from_(si)
            .select(
                Coalesce(Sum(si.outstanding_amount), 0).as_("total_outstanding"),
                Count("*").as_("invoice_count"),
            )
            .where(si.outstanding_amount > 0)
            .where(si.company == self.company)
            .where(si.docstatus == 1)
            .run(as_dict=True)
        )

        days_diff = _DateDiff(CurDate(), si.due_date)

        # Aging analysis buckets — built from the original CASE ordering so the
        # query returns the same buckets (`Not Due`, `0-30 Days`, ...).
        aging_bucket = (
            Case()
            .when(days_diff <= 0, "Not Due")
            .when(days_diff.between(1, 30), "0-30 Days")
            .when(days_diff.between(31, 60), "31-60 Days")
            .when(days_diff.between(61, 90), "61-90 Days")
            .else_("90+ Days")
        )

        aging = (
            frappe.qb.from_(si)
            .select(
                aging_bucket.as_("aging_bucket"),
                Coalesce(Sum(si.outstanding_amount), 0).as_("amount"),
                Count("*").as_("count"),
            )
            .where(si.outstanding_amount > 0)
            .where(si.company == self.company)
            .where(si.docstatus == 1)
            .groupby(aging_bucket)
            .orderby(aging_bucket)
            .run(as_dict=True)
        )

        return {
            "total_outstanding": flt(result[0].get("total_outstanding")) if result else 0,
            "invoice_count": cint(result[0].get("invoice_count")) if result else 0,
            "aging": aging
        }

    def _get_payables(self) -> Dict[str, Any]:
        """Get accounts payable summary"""
        pi = DocType("Purchase Invoice")

        result = (
            frappe.qb.from_(pi)
            .select(
                Coalesce(Sum(pi.outstanding_amount), 0).as_("total_outstanding"),
                Count("*").as_("invoice_count"),
            )
            .where(pi.outstanding_amount > 0)
            .where(pi.company == self.company)
            .where(pi.docstatus == 1)
            .run(as_dict=True)
        )

        return {
            "total_outstanding": flt(result[0].get("total_outstanding")) if result else 0,
            "invoice_count": cint(result[0].get("invoice_count")) if result else 0
        }

    def _get_bank_balance(self) -> Dict[str, Any]:
        """Get bank balance"""
        gle = DocType("GL Entry")
        acc = DocType("Account")

        # Subquery: bank accounts belonging to this company
        bank_subq = (
            frappe.qb.from_(acc)
            .select(acc.name)
            .where(acc.account_type == "Bank")
            .where(acc.company == self.company)
        )

        result = (
            frappe.qb.from_(gle)
            .select(
                gle.account,
                Coalesce(Sum(gle.debit - gle.credit), 0).as_("balance"),
            )
            .where(gle.company == self.company)
            .where(gle.account.isin(bank_subq))
            .where(gle.is_cancelled == 0)
            .groupby(gle.account)
            .run(as_dict=True)
        )

        total = sum(flt(r.get("balance")) for r in result)

        return {
            "total": total,
            "accounts": result
        }

    def _get_monthly_trend(self) -> List[Dict]:
        """Get monthly revenue/expense trend"""
        gle = DocType("GL Entry")
        acc = DocType("Account")

        month_expr = DateFormat(gle.posting_date, "%Y-%m").as_("month")

        revenue_expr = (
            Sum(Case().when(acc.root_type == "Income", Abs(gle.debit - gle.credit)).else_(0))
            .as_("revenue")
        )
        expense_expr = (
            Sum(Case().when(acc.root_type == "Expense", gle.debit - gle.credit).else_(0))
            .as_("expense")
        )

        result = (
            frappe.qb.from_(gle)
            .join(acc)
            .on(gle.account == acc.name)
            .select(month_expr, revenue_expr, expense_expr)
            .where(gle.posting_date.between(self.from_date, self.to_date))
            .where(gle.company == self.company)
            .where(acc.root_type.isin(["Income", "Expense"]))
            .where(gle.is_cancelled == 0)
            .groupby(month_expr)
            .orderby(month_expr)
            .run(as_dict=True)
        )

        return result