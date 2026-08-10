# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Financial Data Collector - Revenue, expenses, profit/loss, cash flow analysis"""

import frappe
from frappe.utils import add_months, flt, cint
from typing import Dict, Any, List

from insights.analytics.collectors.base import BaseCollector


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
        result = frappe.db.sql("""
            SELECT
                SUM(gle.debit - gle.credit) as total_revenue
            FROM `tabGL Entry` gle
            INNER JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.posting_date BETWEEN %s AND %s
            AND gle.company = %s
            AND acc.root_type = 'Income'
            AND gle.is_cancelled = 0
        """, (self.from_date, self.to_date, self.company), as_dict=True)

        total = abs(flt(result[0].get("total_revenue"))) if result else 0

        # Get previous period for comparison
        prev_from = add_months(self.from_date, -12)
        prev_to = add_months(self.to_date, -12)

        prev_result = frappe.db.sql("""
            SELECT SUM(gle.debit - gle.credit) as total_revenue
            FROM `tabGL Entry` gle
            INNER JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.posting_date BETWEEN %s AND %s
            AND gle.company = %s
            AND acc.root_type = 'Income'
            AND gle.is_cancelled = 0
        """, (prev_from, prev_to, self.company), as_dict=True)

        prev_total = abs(flt(prev_result[0].get("total_revenue"))) if prev_result else 0
        growth = ((total - prev_total) / prev_total * 100) if prev_total else 0

        return {
            "total": total,
            "previous_period": prev_total,
            "growth_percent": round(growth, 2)
        }

    def _get_expenses(self) -> Dict[str, Any]:
        """Get expense summary using JOIN instead of subquery"""
        result = frappe.db.sql("""
            SELECT
                SUM(gle.debit - gle.credit) as total_expense
            FROM `tabGL Entry` gle
            INNER JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.posting_date BETWEEN %s AND %s
            AND gle.company = %s
            AND acc.root_type = 'Expense'
            AND gle.is_cancelled = 0
        """, (self.from_date, self.to_date, self.company), as_dict=True)

        total = flt(result[0].get("total_expense")) if result else 0

        # Top expense categories
        top_expenses = frappe.db.sql("""
            SELECT
                parent_account as category,
                SUM(debit - credit) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.posting_date BETWEEN %s AND %s
            AND gle.company = %s
            AND acc.root_type = 'Expense'
            AND gle.is_cancelled = 0
            GROUP BY parent_account
            ORDER BY amount DESC
            LIMIT 10
        """, (self.from_date, self.to_date, self.company), as_dict=True)

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
        # Cash inflows (receipts)
        inflows = frappe.db.sql("""
            SELECT SUM(paid_amount) as total
            FROM `tabPayment Entry`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND payment_type = 'Receive'
            AND docstatus = 1
        """, (self.from_date, self.to_date, self.company), as_dict=True)

        # Cash outflows (payments)
        outflows = frappe.db.sql("""
            SELECT SUM(paid_amount) as total
            FROM `tabPayment Entry`
            WHERE posting_date BETWEEN %s AND %s
            AND company = %s
            AND payment_type = 'Pay'
            AND docstatus = 1
        """, (self.from_date, self.to_date, self.company), as_dict=True)

        total_in = flt(inflows[0].get("total")) if inflows else 0
        total_out = flt(outflows[0].get("total")) if outflows else 0

        return {
            "inflows": total_in,
            "outflows": total_out,
            "net_cash_flow": total_in - total_out
        }

    def _get_receivables(self) -> Dict[str, Any]:
        """Get accounts receivable summary"""
        result = frappe.db.sql("""
            SELECT
                SUM(outstanding_amount) as total_outstanding,
                COUNT(*) as invoice_count
            FROM `tabSales Invoice`
            WHERE outstanding_amount > 0
            AND company = %s
            AND docstatus = 1
        """, (self.company,), as_dict=True)

        # Aging analysis
        aging = frappe.db.sql("""
            SELECT
                CASE
                    WHEN DATEDIFF(CURDATE(), due_date) <= 0 THEN 'Not Due'
                    WHEN DATEDIFF(CURDATE(), due_date) BETWEEN 1 AND 30 THEN '0-30 Days'
                    WHEN DATEDIFF(CURDATE(), due_date) BETWEEN 31 AND 60 THEN '31-60 Days'
                    WHEN DATEDIFF(CURDATE(), due_date) BETWEEN 61 AND 90 THEN '61-90 Days'
                    ELSE '90+ Days'
                END as aging_bucket,
                SUM(outstanding_amount) as amount,
                COUNT(*) as count
            FROM `tabSales Invoice`
            WHERE outstanding_amount > 0
            AND company = %s
            AND docstatus = 1
            GROUP BY aging_bucket
            ORDER BY FIELD(aging_bucket, 'Not Due', '0-30 Days', '31-60 Days', '61-90 Days', '90+ Days')
        """, (self.company,), as_dict=True)

        return {
            "total_outstanding": flt(result[0].get("total_outstanding")) if result else 0,
            "invoice_count": cint(result[0].get("invoice_count")) if result else 0,
            "aging": aging
        }

    def _get_payables(self) -> Dict[str, Any]:
        """Get accounts payable summary"""
        result = frappe.db.sql("""
            SELECT
                SUM(outstanding_amount) as total_outstanding,
                COUNT(*) as invoice_count
            FROM `tabPurchase Invoice`
            WHERE outstanding_amount > 0
            AND company = %s
            AND docstatus = 1
        """, (self.company,), as_dict=True)

        return {
            "total_outstanding": flt(result[0].get("total_outstanding")) if result else 0,
            "invoice_count": cint(result[0].get("invoice_count")) if result else 0
        }

    def _get_bank_balance(self) -> Dict[str, Any]:
        """Get bank balance"""
        result = frappe.db.sql("""
            SELECT
                account,
                SUM(debit - credit) as balance
            FROM `tabGL Entry`
            WHERE company = %s
            AND account IN (
                SELECT name FROM `tabAccount`
                WHERE account_type = 'Bank' AND company = %s
            )
            AND is_cancelled = 0
            GROUP BY account
        """, (self.company, self.company), as_dict=True)

        total = sum(flt(r.get("balance")) for r in result)

        return {
            "total": total,
            "accounts": result
        }

    def _get_monthly_trend(self) -> List[Dict]:
        """Get monthly revenue/expense trend"""
        result = frappe.db.sql("""
            SELECT
                DATE_FORMAT(posting_date, '%%Y-%%m') as month,
                SUM(CASE WHEN acc.root_type = 'Income' THEN ABS(gle.debit - gle.credit) ELSE 0 END) as revenue,
                SUM(CASE WHEN acc.root_type = 'Expense' THEN gle.debit - gle.credit ELSE 0 END) as expense
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.posting_date BETWEEN %s AND %s
            AND gle.company = %s
            AND acc.root_type IN ('Income', 'Expense')
            AND gle.is_cancelled = 0
            GROUP BY month
            ORDER BY month
        """, (self.from_date, self.to_date, self.company), as_dict=True)

        return result
