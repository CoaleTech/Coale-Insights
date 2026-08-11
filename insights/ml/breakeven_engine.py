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
            fy = frappe.db.sql(
                """
                SELECT year_start_date, year_end_date
                FROM `tabFiscal Year`
                WHERE name = %s
                LIMIT 1
                """,
                (self.fiscal_year,),
                as_dict=True,
            )
            if fy:
                self._fiscal_dates = (str(fy[0].year_start_date), str(fy[0].year_end_date))
                return self._fiscal_dates

        today = datetime.now().date()
        fy = frappe.db.sql(
            """
            SELECT year_start_date, year_end_date
            FROM `tabFiscal Year`
            WHERE %s BETWEEN year_start_date AND year_end_date
            ORDER BY year_start_date DESC
            LIMIT 1
            """,
            (today,),
            as_dict=True,
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

        costs = frappe.db.sql(
            """
            SELECT COALESCE(SUM(debit - credit), 0) as total
            FROM `tabGL Entry`
            WHERE company = %s
                AND posting_date BETWEEN %s AND %s
                AND cost_center IN %s
                AND is_cancelled = 0
            """,
            (self.company, start, end, self.fixed_cost_centers),
            as_dict=True,
        )
        self._fixed_costs_result = round(float(costs[0].total or 0), 2)
        return self._fixed_costs_result

    def _get_variable_costs(self, start: str, end: str) -> float:
        """Sum GL entries from variable cost centers."""
        if not self.variable_cost_centers:
            return 0.0

        costs = frappe.db.sql(
            """
            SELECT COALESCE(SUM(debit - credit), 0) as total
            FROM `tabGL Entry`
            WHERE company = %s
                AND posting_date BETWEEN %s AND %s
                AND cost_center IN %s
                AND is_cancelled = 0
            """,
            (self.company, start, end, self.variable_cost_centers),
            as_dict=True,
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

        group_filter = ""
        if item_group:
            group_filter = " AND item.item_group = %s"

        items = frappe.db.sql(
            f"""
            SELECT
                item.name as item_code,
                item.item_name,
                item.item_group,
                COALESCE(item.standard_rate, 0) as selling_price,
                COALESCE(item.valuation_rate, 0) as variable_cost
            FROM `tabItem` item
            WHERE item.disabled = 0
                AND (item.is_sales_item = 1 OR item.is_stock_item = 1)
                {group_filter}
            ORDER BY item.name
            """,
            (item_group,) if item_group else (),
            as_dict=True,
        )

        # Actual sales quantities for the period
        sales = frappe.db.sql(
            """
            SELECT
                sii.item_code,
                COALESCE(SUM(sii.qty), 0) as total_qty,
                COALESCE(SUM(sii.net_amount), 0) as total_revenue
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.docstatus = 1
                AND si.company = %s
                AND si.posting_date BETWEEN %s AND %s
            GROUP BY sii.item_code
            """,
            (self.company, start, end),
            as_dict=True,
        )
        sales_map = {s.item_code: s for s in sales}

        # Compute total contribution to allocate fixed costs proportionally
        total_contribution = 0.0
        for item in items:
            sp = float(item.selling_price or 0)
            vc = float(item.variable_cost or 0)
            cm = sp - vc
            actual_qty = float(sales_map.get(item.item_code, {}).get("total_qty", 0))
            total_contribution += cm * actual_qty

        results = []
        for item in items:
            sp = float(item.selling_price or 0)
            vc = float(item.variable_cost or 0)
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
                "rag": self._rag_coverage(coverage),
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
        payroll = frappe.db.sql(
            """
            SELECT
                COALESCE(department, 'Unassigned') as department,
                COALESCE(SUM(net_pay), 0) as total_payroll
            FROM `tabSalary Slip`
            WHERE docstatus = 1
                AND company = %s
                AND posting_date BETWEEN %s AND %s
            GROUP BY department
            """,
            (self.company, start, end),
            as_dict=True,
        )

        # Average contribution per order
        order_stats = frappe.db.sql(
            """
            SELECT
                COALESCE(SUM(grand_total), 0) as total_revenue,
                COALESCE(SUM(total_taxes_and_charges), 0) as total_tax,
                COUNT(*) as order_count
            FROM `tabSales Order`
            WHERE docstatus = 1
                AND company = %s
                AND transaction_date BETWEEN %s AND %s
            """,
            (self.company, start, end),
            as_dict=True,
        )[0]

        total_revenue = float(order_stats.total_revenue or 0)
        total_tax = float(order_stats.total_tax or 0)
        order_count = int(order_stats.order_count or 0)

        # Estimate variable cost as a % of revenue (from COGS / Revenue ratio)
        cogs = frappe.db.sql(
            """
            SELECT COALESCE(SUM(debit - credit), 0) as cogs
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND acc.account_type = 'Cost of Goods Sold'
                AND gle.is_cancelled = 0
            """,
            (self.company, start, end),
            as_dict=True,
        )[0].cogs or 0

        cogs = float(cogs)
        net_revenue = total_revenue - total_tax
        variable_cost_ratio = (cogs / net_revenue) if net_revenue > 0 else 0.6
        avg_contribution_per_order = round((net_revenue / order_count) * (1 - variable_cost_ratio), 2) if order_count > 0 else 0.0

        # Actual orders per department (proxy: count by department of creator)
        dept_orders = frappe.db.sql(
            """
            SELECT
                COALESCE(e.department, 'Unassigned') as department,
                COUNT(DISTINCT so.name) as order_count
            FROM `tabSales Order` so
            LEFT JOIN `tabEmployee` e ON e.user_id = so.owner
            WHERE so.docstatus = 1
                AND so.company = %s
                AND so.transaction_date BETWEEN %s AND %s
            GROUP BY e.department
            """,
            (self.company, start, end),
            as_dict=True,
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

        monthly = frappe.db.sql(
            """
            SELECT
                DATE_FORMAT(posting_date, '%%Y-%%m') as month,
                COALESCE(SUM(CASE WHEN payment_type = 'Receive' THEN paid_amount ELSE 0 END), 0) as cash_in,
                COALESCE(SUM(CASE WHEN payment_type = 'Pay' THEN paid_amount ELSE 0 END), 0) as cash_out
            FROM `tabPayment Entry`
            WHERE docstatus = 1
                AND company = %s
                AND posting_date BETWEEN %s AND %s
            GROUP BY month
            ORDER BY month
            """,
            (self.company, start, end),
            as_dict=True,
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

        # EBIT = Income - Operating Expenses
        income = frappe.db.sql(
            """
            SELECT COALESCE(SUM(credit - debit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND acc.root_type = 'Income'
                AND gle.is_cancelled = 0
            """,
            (self.company, start, end),
            as_dict=True,
        )[0].amount or 0

        expenses = frappe.db.sql(
            """
            SELECT COALESCE(SUM(debit - credit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND acc.root_type = 'Expense'
                AND acc.account_type NOT IN ('Tax', 'Interest')
                AND gle.is_cancelled = 0
            """,
            (self.company, start, end),
            as_dict=True,
        )[0].amount or 0

        ebit = float(income) - float(expenses)

        # Capital Employed = Total Assets - Current Liabilities
        total_assets = frappe.db.sql(
            """
            SELECT COALESCE(SUM(debit - credit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND acc.root_type = 'Asset'
                AND acc.is_group = 0
                AND gle.is_cancelled = 0
            """,
            (self.company,),
            as_dict=True,
        )[0].amount or 0

        current_liabilities = frappe.db.sql(
            """
            SELECT COALESCE(SUM(credit - debit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND acc.root_type = 'Liability'
                AND acc.is_group = 0
                AND acc.account_type IN ('Payable', 'Tax', 'Stock Liability')
                AND gle.is_cancelled = 0
            """,
            (self.company,),
            as_dict=True,
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

        monthly = frappe.db.sql(
            """
            SELECT
                DATE_FORMAT(posting_date, '%%Y-%%m') as month,
                COALESCE(SUM(CASE WHEN payment_type = 'Receive' THEN paid_amount ELSE -paid_amount END), 0) as net_cash
            FROM `tabPayment Entry`
            WHERE docstatus = 1
                AND company = %s
                AND posting_date BETWEEN %s AND %s
            GROUP BY month
            ORDER BY month
            """,
            (self.company, start, end),
            as_dict=True,
        )

        cash_flows = [float(row.net_cash or 0) for row in monthly]
        return self._irr_from_flows(cash_flows)

    def get_item_lead_breakeven_ratio(self) -> dict[str, Any]:
        """Leads needed per item = BE qty / lead conversion rate."""
        item_data = self.calculate_item_breakeven()

        # Lead conversion rate
        lead_stats = frappe.db.sql(
            """
            SELECT
                COUNT(*) as total_leads,
                SUM(CASE WHEN status IN ('Converted', 'Opportunity', 'Quotation') THEN 1 ELSE 0 END) as converted
            FROM `tabLead`
            WHERE company = %s OR %s = ''
            """,
            (self.company, self.company),
            as_dict=True,
        )[0]

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
        """Predict break-even for a given scenario (not implemented)."""
        return {"status": "not_implemented"}


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
