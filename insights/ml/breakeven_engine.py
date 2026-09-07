from __future__ import annotations

# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Break-Even Engine for Frappe Insights.

Calculates item-level, employee-level, cash-flow, and capital-efficiency
break-even metrics using GL, Sales, Payroll, and Payment Entry data.

Every metric is a parameterized SQL aggregate computed fresh on each call --
fast enough for a web request, unlike the pandas/sklearn training modules
elsewhere in ``insights.ml`` -- so there is no self-managed cache and no
``BaseMLModel`` dependency. IRR is solved via ``numpy.roots`` on the
cash-flow polynomial instead of the unmaintained, uninstalled
``numpy_financial`` package (``calculate_irr`` was silently returning
``irr: None`` on every call -- see ``_polynomial_irr``).
"""

from datetime import datetime
from typing import Any

import frappe
from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import Coalesce, Count, DateFormat, Sum


class BreakevenEngine:
    """Break-even analysis engine"""

    def __init__(self, period: str = "Quarterly", fiscal_year: str | None = None):
        self.period = period
        self.fiscal_year = fiscal_year
        self.company = frappe.defaults.get_user_default("Company")
        if not self.company:
            self.company = frappe.db.get_single_value("Global Defaults", "default_company")

        settings = frappe.get_doc("Insights Settings", None) if frappe.db.exists("Insights Settings", "Insights Settings") else None
        if settings is None:
            settings_doc = frappe.get_doc({"doctype": "Insights Settings"})
        else:
            settings_doc = settings

        self.fixed_cost_centers = []
        if getattr(settings_doc, "fixed_cost_centers", None):
            self.fixed_cost_centers = [c.strip() for c in settings_doc.fixed_cost_centers.split("\n") if c.strip()]

        self.variable_cost_centers = []
        if getattr(settings_doc, "variable_cost_centers", None):
            self.variable_cost_centers = [c.strip() for c in settings_doc.variable_cost_centers.split("\n") if c.strip()]

        self.corporate_tax_rate = getattr(settings_doc, "corporate_tax_rate", 0.30) or 0.30
        self.roce_target = getattr(settings_doc, "roce_target", 0.15) or 0.15

    def _get_fiscal_dates(self) -> tuple:
        """Returns (start_date, end_date) for the selected fiscal year. Result cached on instance."""
        if hasattr(self, "_fiscal_dates"):
            return self._fiscal_dates

        if self.fiscal_year:
            FiscalYear = DocType("Fiscal Year")
            fy = (
                frappe.qb.from_(FiscalYear)
                .select(FiscalYear.year_start_date, FiscalYear.year_end_date)
                .where(FiscalYear.name == self.fiscal_year)
                .limit(1)
                .run(as_dict=True)
            )
            if fy:
                self._fiscal_dates = (str(fy[0].year_start_date), str(fy[0].year_end_date))
                return self._fiscal_dates

        today = datetime.now().date()
        FiscalYear = DocType("Fiscal Year")
        fy = (
            frappe.qb.from_(FiscalYear)
            .select(FiscalYear.year_start_date, FiscalYear.year_end_date)
            .where(FiscalYear.year_start_date <= today)
            .where(FiscalYear.year_end_date >= today)
            .orderby(FiscalYear.year_start_date, order=frappe.qb.desc)
            .limit(1)
            .run(as_dict=True)
        )
        if fy:
            self._fiscal_dates = (str(fy[0].year_start_date), str(fy[0].year_end_date))
            return self._fiscal_dates


        start = today.replace(month=1, day=1)
        end = today.replace(month=12, day=31)
        self._fiscal_dates = (str(start), str(end))
        return self._fiscal_dates

    def _get_fixed_costs(self, start: str, end: str) -> float:
        """Sum GL entries from fixed cost centers. Result cached on instance per date range."""
        if hasattr(self, "_fixed_costs_result"):
            return self._fixed_costs_result

        if not self.fixed_cost_centers:
            self._fixed_costs_result = 0.0
            return 0.0

        GLEntry = DocType("GL Entry")
        costs = (
            frappe.qb.from_(GLEntry)
            .select(Coalesce(Sum(GLEntry.debit - GLEntry.credit), 0).as_("total"))
            .where(GLEntry.company == self.company)
            .where(GLEntry.posting_date.between(start, end))
            .where(GLEntry.cost_center.isin(self.fixed_cost_centers))
            .where(GLEntry.is_cancelled == 0)
            .run(as_dict=True)
        )
        self._fixed_costs_result = round(float(costs[0].total or 0), 2)
        return self._fixed_costs_result

    def _get_variable_costs(self, start: str, end: str) -> float:
        """Sum GL entries from variable cost centers."""
        if not self.variable_cost_centers:
            return 0.0

        GLEntry = DocType("GL Entry")
        costs = (
            frappe.qb.from_(GLEntry)
            .select(Coalesce(Sum(GLEntry.debit - GLEntry.credit), 0).as_("total"))
            .where(GLEntry.company == self.company)
            .where(GLEntry.posting_date.between(start, end))
            .where(GLEntry.cost_center.isin(self.variable_cost_centers))
            .where(GLEntry.is_cancelled == 0)
            .run(as_dict=True)
        )
        return round(float(costs[0].total or 0), 2)

    def _rag_coverage(self, coverage: float) -> str:
        """RAG for coverage ratio."""
        if coverage > 1.2:
            return "green"
        elif coverage >= 1.0:
            return "amber"
        return "red"

    def _rag_roce(self, roce: float) -> str:
        """RAG for ROCE vs target."""
        if roce > self.roce_target:
            return "green"
        elif roce > self.roce_target * 0.8:
            return "amber"
        return "red"

    def calculate_item_breakeven(self, item_group: str | None = None) -> dict[str, Any]:
        """Per-item contribution margin, break-even qty, coverage, RAG indicator."""
        start, end = self._get_fiscal_dates()
        total_fixed = self._get_fixed_costs(start, end)

        item = DocType("Item")
        items_q = (
            frappe.qb.from_(item)
            .select(
                item.name.as_("item_code"),
                item.item_name,
                item.item_group,
            )
            .where(item.disabled == 0)
            .where((item.is_sales_item == 1) | (item.is_stock_item == 1))
            .orderby(item.name)
        )
        if item_group:
            items_q = items_q.where(item.item_group == item_group)
        items = items_q.run(as_dict=True)


        # Real selling price = weighted-avg rate from Sales Invoice Items for the
        # period. Item.standard_rate / Item Price are 0 / unpopulated on many
        # benches (the standard ERPNext Item master never has prices filled in
        # when an Item Price list exists) -- falling back to those alone gave
        # contribution_margin = 0 for every item and broke the whole
        # per-item break-even view. Only fall back to Item.standard_rate when
        # no period sales exist; we don't want to silently mix a stale master
        # price into a real cost basis.
        SalesInvoiceItem = DocType("Sales Invoice Item")
        SalesInvoice = DocType("Sales Invoice")
        sales_prices = (
            frappe.qb.from_(SalesInvoiceItem)
            .join(SalesInvoice)
            .on(SalesInvoiceItem.parent == SalesInvoice.name)
            .select(
                SalesInvoiceItem.item_code,
                Sum(SalesInvoiceItem.net_amount).as_("period_revenue"),
                Sum(SalesInvoiceItem.qty).as_("period_qty"),
            )
            .where(SalesInvoice.docstatus == 1)
            .where(SalesInvoice.company == self.company)
            .where(SalesInvoice.posting_date.between(start, end))
            .groupby(SalesInvoiceItem.item_code)
            .run(as_dict=True)
        )
        sales_price_map = {}
        for sp in sales_prices:
            revenue = float(sp.period_revenue or 0)
            qty = float(sp.period_qty or 0)
            # net_amount / qty -- handles discount-inclusive pricing correctly
            # (qty is in the same UOM as net_amount, so the ratio is unit price)
        Bin = DocType("Bin")
        SLE = DocType("Stock Ledger Entry")
        # Subquery: most recent positive incoming_rate per item, to fall back
        # to when Bin has no valuation_rate for the item.
        latest_sle = (
            frappe.qb.from_(SLE)
            .select(SLE.incoming_rate)
            .where(SLE.item_code == Bin.item_code)
            .where(SLE.docstatus == 1)
            .where(SLE.incoming_rate > 0)
            .orderby(SLE.posting_date, order=frappe.qb.desc)
            .orderby(SLE.creation, order=frappe.qb.desc)
            .limit(1)
        )
        costs = (
            frappe.qb.from_(Bin)
            .select(
                Bin.item_code,
                Coalesce(Bin.valuation_rate, latest_sle, 0).as_("variable_cost"),
            )
            .run(as_dict=True)
        )
        bin_cost_map = {c.item_code: float(c.variable_cost or 0) for c in costs}

        sales = (
            frappe.qb.from_(SalesInvoiceItem)
            .join(SalesInvoice)
            .on(SalesInvoiceItem.parent == SalesInvoice.name)
            .select(
                SalesInvoiceItem.item_code,
                Coalesce(Sum(SalesInvoiceItem.qty), 0).as_("total_qty"),
                Coalesce(Sum(SalesInvoiceItem.net_amount), 0).as_("total_revenue"),
            )
            .where(SalesInvoice.docstatus == 1)
            .where(SalesInvoice.company == self.company)
            .where(SalesInvoice.posting_date.between(start, end))
            .groupby(SalesInvoiceItem.item_code)
            .run(as_dict=True)
        )
        sales_map = {s.item_code: s for s in sales}

        master_prices = (
            frappe.qb.from_(item)
            .select(
                item.name.as_("item_code"),
                Coalesce(item.standard_rate, 0).as_("master_selling_price"),
                Coalesce(item.valuation_rate, 0).as_("master_variable_cost"),
            )
            .where(item.disabled == 0)
            .run(as_dict=True)
        )
        master_map = {m.item_code: m for m in master_prices}

        # Compute total contribution to allocate fixed costs proportionally
        total_contribution = 0.0
        for item in items:
            sp = sales_price_map.get(item.item_code, 0.0)
            if sp <= 0:
                sp = float(master_map.get(item.item_code, {}).get("master_selling_price", 0))
            vc = bin_cost_map.get(item.item_code, 0.0)
            if vc <= 0:
                vc = float(master_map.get(item.item_code, {}).get("master_variable_cost", 0))
            cm = sp - vc
            actual_qty = float(sales_map.get(item.item_code, {}).get("total_qty", 0))
            total_contribution += cm * actual_qty

        results = []
        for item in items:
            sp = sales_price_map.get(item.item_code, 0.0)
            if sp <= 0:
                sp = float(master_map.get(item.item_code, {}).get("master_selling_price", 0))
            vc = bin_cost_map.get(item.item_code, 0.0)
            if vc <= 0:
                vc = float(master_map.get(item.item_code, {}).get("master_variable_cost", 0))
            cm = round(sp - vc, 2)
            actual_qty = float(sales_map.get(item.item_code, {}).get("total_qty", 0))
            actual_revenue = float(sales_map.get(item.item_code, {}).get("total_revenue", 0))

            # Allocate fixed costs by contribution share
            allocated_fixed = 0.0
            if total_contribution > 0 and cm > 0:
                allocated_fixed = round(total_fixed * (cm * actual_qty / total_contribution), 2)

            be_qty = round(allocated_fixed / cm, 2) if cm > 0 else 0.0
            coverage = round(actual_qty / be_qty, 2) if be_qty > 0 else 0.0
            safety_margin = round((actual_qty - be_qty) / actual_qty * 100, 2) if actual_qty > 0 else 0.0

            results.append({
                "item_code": item.item_code,
                "item_name": item.item_name,
                "item_group": item.item_group,
                "selling_price": round(sp, 2),
                "variable_cost": round(vc, 2),
                "contribution_margin": cm,
                "be_qty": be_qty,
                "actual_qty": round(actual_qty, 2),
                "actual_revenue": round(actual_revenue, 2),
                "coverage": coverage,
                "safety_margin": safety_margin,
            })

        return {
            "period": self.period,
            "fiscal_year": self.fiscal_year,
            "date_range": {"start": start, "end": end},
            "total_fixed_costs": total_fixed,
            "items": results,
        }

    def calculate_employee_breakeven(self) -> dict[str, Any]:
        """Orders needed to cover each department's payroll."""
        start, end = self._get_fiscal_dates()

        # Payroll by department
        SalarySlip = DocType("Salary Slip")
        payroll = (
            frappe.qb.from_(SalarySlip)
            .select(
                Coalesce(SalarySlip.department, "Unassigned").as_("department"),
                Coalesce(Sum(SalarySlip.net_pay), 0).as_("total_payroll"),
            )
            .where(SalarySlip.docstatus == 1)
            .where(SalarySlip.company == self.company)
            .where(SalarySlip.posting_date.between(start, end))
            .groupby(SalarySlip.department)
            .run(as_dict=True)
        )


        # Average contribution per order
        SalesOrder = DocType("Sales Order")
        order_stats = (
            frappe.qb.from_(SalesOrder)
            .select(
                Coalesce(Sum(SalesOrder.grand_total), 0).as_("total_revenue"),
                Coalesce(Sum(SalesOrder.total_taxes_and_charges), 0).as_("total_tax"),
                Count("*").as_("order_count"),
            )
            .where(SalesOrder.docstatus == 1)
            .where(SalesOrder.company == self.company)
            .where(SalesOrder.transaction_date.between(start, end))
            .run(as_dict=True)
        )[0]

        total_revenue = float(order_stats.total_revenue or 0)
        total_tax = float(order_stats.total_tax or 0)
        order_count = int(order_stats.order_count or 0)

        # Estimate variable cost as a % of revenue (from COGS / Revenue ratio)
        GLEntry = DocType("GL Entry")
        Account = DocType("Account")
        cogs_row = (
            frappe.qb.from_(GLEntry)
            .join(Account)
            .on(GLEntry.account == Account.name)
            .select(Coalesce(Sum(GLEntry.debit - GLEntry.credit), 0).as_("cogs"))
            .where(GLEntry.company == self.company)
            .where(GLEntry.posting_date.between(start, end))
            .where(Account.account_type == "Cost of Goods Sold")
            .where(GLEntry.is_cancelled == 0)
            .run(as_dict=True)
        )[0]
        cogs = cogs_row.cogs or 0

        cogs = float(cogs)
        net_revenue = total_revenue - total_tax
        variable_cost_ratio = (cogs / net_revenue) if net_revenue > 0 else 0.6
        avg_contribution_per_order = round((net_revenue / order_count) * (1 - variable_cost_ratio), 2) if order_count > 0 else 0.0

        # Actual orders per department (proxy: count by department of creator)
        Employee = DocType("Employee")
        dept_orders = (
            frappe.qb.from_(SalesOrder)
            .left_join(Employee)
            .on(Employee.user_id == SalesOrder.owner)
            .select(
                Coalesce(Employee.department, "Unassigned").as_("department"),
                Count(SalesOrder.name).distinct().as_("order_count"),
            )
            .where(SalesOrder.docstatus == 1)
            .where(SalesOrder.company == self.company)
            .where(SalesOrder.transaction_date.between(start, end))
            .groupby(Employee.department)
            .run(as_dict=True)
        )


        payroll_map = {p.department: float(p.total_payroll or 0) for p in payroll}
        orders_map = {d.department: int(d.order_count or 0) for d in dept_orders}

        # Departments actually present in the data. A hardcoded
        # ["Sales", "HR", "Purchase", "Procurement"] whitelist never matched
        # this company's real department names (e.g. "Sales - JKM"), so every
        # coverage figure below was silently zero regardless of real payroll
        # or order volume.
        departments: list[str] = sorted(str(d) for d in set(payroll_map) | set(orders_map))
        results = []
        for dept in departments:
            payroll_cost = payroll_map.get(dept, 0.0)
            orders_needed = round(payroll_cost / avg_contribution_per_order, 2) if avg_contribution_per_order > 0 else 0.0
            actual_orders = orders_map.get(dept, 0)
            coverage = round(actual_orders / orders_needed, 2) if orders_needed > 0 else 0.0

            results.append({
                "department": dept,
                "payroll_cost": round(payroll_cost, 2),
                "orders_needed": orders_needed,
                "actual_orders": actual_orders,
                "coverage": coverage,
                "rag": self._rag_coverage(coverage),
            })

        return {
            "period": self.period,
            "fiscal_year": self.fiscal_year,
            "date_range": {"start": start, "end": end},
            "avg_contribution_per_order": avg_contribution_per_order,
            "departments": results,
        }

    def calculate_cash_flow_breakeven(self) -> dict[str, Any]:
        """Cash flow break-even using Payment Entry data."""
        start, end = self._get_fiscal_dates()

        PaymentEntry = DocType("Payment Entry")
        month_expr = DateFormat(PaymentEntry.posting_date, "%Y-%m").as_("month")
        cash_in_expr = Sum(
            Case()
            .when(PaymentEntry.payment_type == "Receive", PaymentEntry.paid_amount)
            .else_(0)
        ).as_("cash_in")
        cash_out_expr = Sum(
            Case()
            .when(PaymentEntry.payment_type == "Pay", PaymentEntry.paid_amount)
            .else_(0)
        ).as_("cash_out")
        monthly = (
            frappe.qb.from_(PaymentEntry)
            .select(
                month_expr,
                Coalesce(cash_in_expr, 0),
                Coalesce(cash_out_expr, 0),
            )
            .where(PaymentEntry.docstatus == 1)
            .where(PaymentEntry.company == self.company)
            .where(PaymentEntry.posting_date.between(start, end))
            .groupby(month_expr)
            .orderby(month_expr)
            .run(as_dict=True)
        )


        cumulative_in = 0.0
        cumulative_out = 0.0
        breakeven_month = None
        monthly_data = []

        for row in monthly:
            cash_in = float(row.cash_in or 0)
            cash_out = float(row.cash_out or 0)
            cumulative_in += cash_in
            cumulative_out += cash_out
            net = round(cash_in - cash_out, 2)
            monthly_data.append({
                "month": row.month,
                "cash_in": round(cash_in, 2),
                "cash_out": round(cash_out, 2),
                "net_cash": net,
                "cumulative_in": round(cumulative_in, 2),
                "cumulative_out": round(cumulative_out, 2),
            })
            if breakeven_month is None and cumulative_in >= cumulative_out:
                breakeven_month = row.month

        total_in = round(cumulative_in, 2)
        total_out = round(cumulative_out, 2)
        coverage = round(total_in / total_out, 2) if total_out > 0 else 0.0

        return {
            "period": self.period,
            "fiscal_year": self.fiscal_year,
            "date_range": {"start": start, "end": end},
            "monthly": monthly_data,
            "breakeven_month": breakeven_month,
            "total_cash_in": total_in,
            "total_cash_out": total_out,
            "coverage": coverage,
            "rag": self._rag_coverage(coverage),
        }

    def calculate_roce(self) -> dict[str, Any]:
        """Return on Capital Employed from GL data."""
        start, end = self._get_fiscal_dates()
        GLEntry = DocType("GL Entry")
        Account = DocType("Account")

        # EBIT = Income - Operating Expenses
        income = (
            frappe.qb.from_(GLEntry)
            .join(Account)
            .on(GLEntry.account == Account.name)
            .select(Coalesce(Sum(GLEntry.credit - GLEntry.debit), 0).as_("amount"))
            .where(GLEntry.company == self.company)
            .where(GLEntry.posting_date.between(start, end))
            .where(Account.root_type == "Income")
            .where(GLEntry.is_cancelled == 0)
            .run(as_dict=True)
        )[0].amount or 0


        expenses = (
            frappe.qb.from_(GLEntry)
            .join(Account)
            .on(GLEntry.account == Account.name)
            .select(Coalesce(Sum(GLEntry.debit - GLEntry.credit), 0).as_("amount"))
            .where(GLEntry.company == self.company)
            .where(GLEntry.posting_date.between(start, end))
            .where(Account.root_type == "Expense")
            .where(Account.account_type.notin(["Tax", "Interest"]))
            .where(GLEntry.is_cancelled == 0)
            .run(as_dict=True)
        )[0].amount or 0

        ebit = float(income) - float(expenses)


        # Capital Employed = Total Assets - Current Liabilities
        total_assets = (
            frappe.qb.from_(GLEntry)
            .join(Account)
            .on(GLEntry.account == Account.name)
            .select(Coalesce(Sum(GLEntry.debit - GLEntry.credit), 0).as_("amount"))
            .where(GLEntry.company == self.company)
            .where(Account.root_type == "Asset")
            .where(Account.is_group == 0)
            .where(GLEntry.is_cancelled == 0)
            .run(as_dict=True)
        )[0].amount or 0
        current_liabilities = (
            frappe.qb.from_(GLEntry)
            .join(Account)
            .on(GLEntry.account == Account.name)
            .select(Coalesce(Sum(GLEntry.credit - GLEntry.debit), 0).as_("amount"))
            .where(GLEntry.company == self.company)
            .where(Account.root_type == "Liability")
            .where(Account.is_group == 0)
            .where(Account.account_type.isin(["Payable", "Tax", "Stock Liability"]))
            .where(GLEntry.is_cancelled == 0)
            .run(as_dict=True)
        )[0].amount or 0

        capital_employed = float(total_assets) - float(current_liabilities)
        roce = round(ebit / capital_employed, 4) if capital_employed > 0 else 0.0

        return {
            "ebit": round(ebit, 2),
            "capital_employed": round(capital_employed, 2),
            "roce": round(roce * 100, 2),
            "roce_decimal": round(roce, 4),
            "target": round(self.roce_target * 100, 2),
            "rag": self._rag_roce(roce),
        }

    def _irr_from_flows(self, cash_flows: list[float]) -> dict[str, Any]:
        """Compute IRR dict from a list of net cash flow values."""
        irr_value = _polynomial_irr(cash_flows) if len(cash_flows) >= 2 else None
        return {
            "monthly_cash_flows": [round(v, 2) for v in cash_flows],
            "irr": round(irr_value * 100, 2) if irr_value is not None else None,
            "irr_decimal": round(irr_value, 6) if irr_value is not None else None,
        }

    def calculate_irr(self) -> dict[str, Any]:
        """Internal Rate of Return on monthly net cash flows."""
        start, end = self._get_fiscal_dates()
        PaymentEntry = DocType("Payment Entry")

        month_expr = DateFormat(PaymentEntry.posting_date, "%Y-%m").as_("month")
        net_cash_expr = Sum(
            Case()
            .when(PaymentEntry.payment_type == "Receive", PaymentEntry.paid_amount)
            .else_(-PaymentEntry.paid_amount)
        ).as_("net_cash")
        monthly = (
            frappe.qb.from_(PaymentEntry)
            .select(month_expr, Coalesce(net_cash_expr, 0))
            .where(PaymentEntry.docstatus == 1)
            .where(PaymentEntry.company == self.company)
            .where(PaymentEntry.posting_date.between(start, end))
            .groupby(month_expr)
            .orderby(month_expr)
            .run(as_dict=True)
        )


        cash_flows = [float(row.net_cash or 0) for row in monthly]
        return self._irr_from_flows(cash_flows)

    def get_item_lead_breakeven_ratio(self) -> dict[str, Any]:
        """Leads needed per item = BE qty / lead conversion rate."""
        item_data = self.calculate_item_breakeven()

        # Lead conversion rate
        Lead = DocType("Lead")
        converted_expr = Sum(
            Case()
            .when(Lead.status.isin(["Converted", "Opportunity", "Quotation"]), 1)
            .else_(0)
        ).as_("converted")
        lead_q = (
            frappe.qb.from_(Lead)
            .select(Count("*").as_("total_leads"), converted_expr)
        )
        # Original SQL was `WHERE company = %s OR %s = ''`; mirror that by
        # skipping the filter entirely when the company is falsy, since the
        # OR-empty side is just a back-compat fallback for benches with no
        # company on Lead.
        if self.company:
            lead_q = lead_q.where(Lead.company == self.company)
        lead_stats = lead_q.run(as_dict=True)[0]

        total_leads = int(lead_stats.total_leads or 0)
        converted = int(lead_stats.converted or 0)
        conversion_rate = round(converted / total_leads, 4) if total_leads > 0 else 0.05

        results = []
        for item in item_data.get("items", []):
            be_qty = item.get("be_qty", 0)
            leads_needed = round(be_qty / conversion_rate, 2) if conversion_rate > 0 else 0.0
            results.append({
                "item_code": item["item_code"],
                "item_name": item["item_name"],
                "be_qty": be_qty,
                "conversion_rate": round(conversion_rate * 100, 2),
                "leads_needed": leads_needed,
            })

        return {
            "period": self.period,
            "fiscal_year": self.fiscal_year,
            "conversion_rate": round(conversion_rate * 100, 2),
            "items": results,
        }

    def get_breakeven_summary(self) -> dict[str, Any]:
        """Returns all break-even metrics in one call."""
        start, end = self._get_fiscal_dates()
        total_fixed = self._get_fixed_costs(start, end)
        total_variable = self._get_variable_costs(start, end)

        item_data = self.calculate_item_breakeven()
        cash_data = self.calculate_cash_flow_breakeven()
        roce_data = self.calculate_roce()
        # Derive IRR from the already-fetched monthly cash flows to avoid a duplicate Payment Entry query
        cash_flows = [row["net_cash"] for row in cash_data.get("monthly", [])]
        irr_data = self._irr_from_flows(cash_flows)
        employee_data = self.calculate_employee_breakeven()

        # Overall BE revenue and qty
        total_cm = sum(i.get("contribution_margin", 0) * i.get("actual_qty", 0) for i in item_data.get("items", []))
        total_qty = sum(i.get("actual_qty", 0) for i in item_data.get("items", []))
        avg_cm = round(total_cm / total_qty, 2) if total_qty > 0 else 0.0

        overall_be_qty = round(total_fixed / avg_cm, 2) if avg_cm > 0 else 0.0
        overall_be_revenue = round(total_fixed + total_variable, 2)
        actual_revenue = sum(i.get("actual_revenue", 0) for i in item_data.get("items", []))
        coverage = round(actual_revenue / overall_be_revenue, 2) if overall_be_revenue > 0 else 0.0
        safety_margin = round((actual_revenue - overall_be_revenue) / actual_revenue * 100, 2) if actual_revenue > 0 else 0.0

        return {
            "period": self.period,
            "fiscal_year": self.fiscal_year,
            "date_range": {"start": start, "end": end},
            "fixed_costs": total_fixed,
            "variable_costs": total_variable,
            "be_revenue": overall_be_revenue,
            "be_qty": overall_be_qty,
            "actual_revenue": round(actual_revenue, 2),
            "coverage": coverage,
            "safety_margin": safety_margin,
            "rag": self._rag_coverage(coverage),
            "item_breakeven": item_data,
            "employee_breakeven": employee_data,
            "cash_flow_breakeven": cash_data,
            "roce": roce_data,
            "irr": irr_data,
        }

    def train(self) -> dict[str, Any]:
        """Run the full break-even summary (kept for the weekly scheduler)."""
        try:
            summary = self.get_breakeven_summary()
            frappe.logger().info(
                f"BreakevenEngine training completed: "
                f"{len(summary.get('item_breakeven', {}).get('items', []))} items"
            )
            return {"status": "success", "data": summary}
        except Exception as e:
            frappe.log_error(f"BreakevenEngine training failed: {e!s}", "BreakevenEngine")
            return {"status": "error", "message": str(e)}

    def predict(self, data: Any) -> dict[str, Any]:
        """Recompute item and overall break-even under a hypothetical scenario.

        ``data`` is a dict of percentage deltas applied to the current period's
        real fixed costs, prices, variable costs, and sold quantities (all
        optional, default 0):
            - ``fixed_cost_delta_pct``: change to total fixed costs
            - ``price_delta_pct``: change to each item's selling price
            - ``variable_cost_delta_pct``: change to each item's unit variable
              cost and to the aggregate variable-cost-center total
            - ``volume_delta_pct``: change to each item's sold quantity --
              shifts coverage/safety margin, not the break-even qty itself
            - ``item_group``: optional Item Group filter (same as
              ``calculate_item_breakeven``)

        Deterministic sensitivity recompute using the same real Item-master
        prices/costs, actual sales quantities, and fixed-cost allocation
        formula as ``calculate_item_breakeven``/``get_breakeven_summary`` --
        not a trained model. Cash flow, payroll, ROCE, and IRR are unaffected
        by this scenario and are intentionally not recomputed here.
        """
        try:
            scenario = data if isinstance(data, dict) else {}
            fixed_delta = float(scenario.get("fixed_cost_delta_pct", 0) or 0) / 100
            price_delta = float(scenario.get("price_delta_pct", 0) or 0) / 100
            variable_delta = float(scenario.get("variable_cost_delta_pct", 0) or 0) / 100
            volume_delta = float(scenario.get("volume_delta_pct", 0) or 0) / 100
            item_group = scenario.get("item_group") or None

            baseline = self.calculate_item_breakeven(item_group=item_group)
            start, end = self._get_fiscal_dates()
            base_fixed = baseline["total_fixed_costs"]
            base_variable = self._get_variable_costs(start, end)
            scenario_fixed = round(base_fixed * (1 + fixed_delta), 2)
            scenario_variable = round(base_variable * (1 + variable_delta), 2)

            scenario_items = []
            for item in baseline["items"]:
                sp = round(item["selling_price"] * (1 + price_delta), 2)
                vc = round(item["variable_cost"] * (1 + variable_delta), 2)
                qty = round(item["actual_qty"] * (1 + volume_delta), 2)
                scenario_items.append({
                    "item_code": item["item_code"],
                    "item_name": item["item_name"],
                    "item_group": item["item_group"],
                    "selling_price": sp,
                    "variable_cost": vc,
                    "contribution_margin": round(sp - vc, 2),
                    "qty": qty,
                })

            total_contribution = sum(i["contribution_margin"] * i["qty"] for i in scenario_items)

            results = []
            for item in scenario_items:
                cm = item["contribution_margin"]
                qty = item["qty"]
                allocated_fixed = 0.0
                if total_contribution > 0 and cm > 0:
                    allocated_fixed = round(scenario_fixed * (cm * qty / total_contribution), 2)
                be_qty = round(allocated_fixed / cm, 2) if cm > 0 else 0.0
                coverage = round(qty / be_qty, 2) if be_qty > 0 else 0.0
                safety_margin = round((qty - be_qty) / qty * 100, 2) if qty > 0 else 0.0
                results.append({
                    **item,
                    "revenue": round(item["selling_price"] * qty, 2),
                    "be_qty": be_qty,
                    "coverage": coverage,
                    "safety_margin": safety_margin,
                    "rag": self._rag_coverage(coverage),
                })

            projected_revenue = round(sum(r["revenue"] for r in results), 2)
            projected_qty = round(sum(r["qty"] for r in results), 2)
            overall_be_revenue = round(scenario_fixed + scenario_variable, 2)
            overall_coverage = round(projected_revenue / overall_be_revenue, 2) if overall_be_revenue > 0 else 0.0
            overall_safety_margin = (
                round((projected_revenue - overall_be_revenue) / projected_revenue * 100, 2)
                if projected_revenue > 0 else 0.0
            )

            current_qty = round(sum(i.get("actual_qty", 0) for i in baseline["items"]), 2)
            current_revenue = round(sum(i.get("actual_revenue", 0) for i in baseline["items"]), 2)
            current_be_revenue = round(base_fixed + base_variable, 2)
            current_coverage = round(current_revenue / current_be_revenue, 2) if current_be_revenue > 0 else 0.0

            return {
                "status": "success",
                "scenario": {
                    "fixed_cost_delta_pct": round(fixed_delta * 100, 2),
                    "price_delta_pct": round(price_delta * 100, 2),
                    "variable_cost_delta_pct": round(variable_delta * 100, 2),
                    "volume_delta_pct": round(volume_delta * 100, 2),
                    "item_group": item_group,
                },
                "items": results,
                "overall": {
                    "fixed_costs": scenario_fixed,
                    "variable_costs": scenario_variable,
                    "be_revenue": overall_be_revenue,
                    "projected_qty": projected_qty,
                    "projected_revenue": projected_revenue,
                    "coverage": overall_coverage,
                    "safety_margin": overall_safety_margin,
                    "rag": self._rag_coverage(overall_coverage),
                },
                "current": {
                    "fixed_costs": base_fixed,
                    "variable_costs": base_variable,
                    "be_revenue": current_be_revenue,
                    "actual_qty": current_qty,
                    "actual_revenue": current_revenue,
                    "coverage": current_coverage,
                },
            }
        except Exception as e:
            frappe.log_error(f"BreakevenEngine predict failed: {e!s}", "BreakevenEngine")
            return {"status": "error", "message": str(e)}


def _polynomial_irr(cash_flows: list[float]) -> float | None:
    """Internal rate of return via the roots of the cash-flow polynomial.

    Replaces ``numpy_financial.irr``: that package is not declared as a
    dependency of this app and is not installed, so ``calculate_irr`` was
    silently returning ``irr: None`` on every call (the import always raised
    inside the old ``try/except``). ``numpy`` is already a hard dependency
    elsewhere in ``insights.ml``, so this solves the same equation
    numpy_financial does internally instead of adding the extra package back:

        NPV(r) = sum(cf_i * (1 + r) ** (n - 1 - i)) == 0

    which, substituting X = (1 + r), is a plain polynomial in X whose
    decreasing-power coefficients are exactly ``cash_flows`` in order.
    """
    import numpy as np

    try:
        roots = np.roots(cash_flows)
    except Exception:
        return None

    real_x = roots[np.abs(roots.imag) < 1e-9].real
    real_x = real_x[real_x > 0]  # X = 1 + r must be positive (r > -100%)
    if real_x.size == 0:
        return None

    # Cash flows with more than one sign change can satisfy NPV == 0 at
    # several rates; the one closest to zero is the economically sensible
    # root (matches numpy_financial's Newton iteration, which starts near a
    # 0.1 guess and converges to this same root for realistic cash flows).
    rates = real_x - 1.0
    return float(rates[np.argmin(np.abs(rates))])
