"""
Financial Intelligence Model

Comprehensive financial analytics for the Financial Intelligence dashboard:
- P&L analysis and profitability
- Cash flow management and runway
- Accounts receivable and payable
- Forex exposure analysis

All aggregates are computed via Ibis against the site's own MariaDB; the
Python process only ever materialises the final, already-aggregated result
(normally a few hundred rows). No pandas/sklearn, no training, no caching.

Financial ratios and budget variance have their own modules under
`insights.ml.strategic_finance` and `insights.ml.budget_variance_intelligence`
to keep one canonical computation per metric; see FinancialRatiosTab.vue /
BudgetVarianceTab.vue.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import frappe

from insights.api.ml.ibis_source import company_filter, default_company, t


def _now_iso() -> str:
    return datetime.now().isoformat()


def _today() -> str:
    return datetime.now().date().isoformat()


# ERPNext has no term-deposit `account_type`, so a fixed deposit is identified
# by account name. Lower-cased prefix match, applied in one place.
FD_PREFIX = "fixed deposit"


def _fiscal_year_for(company: str) -> dict[str, str]:
    """Return {name, start_date, end_date} for the fiscal year that contains
    today (calendar fallback if the company has no Fiscal Year record)."""
    today = datetime.now().date()
    FiscalYear = frappe.qb.DocType("Fiscal Year")
    rows = (
        frappe.qb.from_(FiscalYear)
        .select(FiscalYear.name, FiscalYear.year_start_date, FiscalYear.year_end_date)
        .where((today >= FiscalYear.year_start_date) & (today <= FiscalYear.year_end_date))
        .orderby(FiscalYear.year_start_date, order=frappe.qb.desc)
        .limit(1)
        .run(as_dict=True)
    )
    if rows:
        row = rows[0]
        return {
            "name": row.name,
            "start_date": str(row.year_start_date),
            "end_date": str(row.year_end_date),
        }
    return {
        "name": str(today.year),
        "start_date": f"{today.year}-01-01",
        "end_date": f"{today.year}-12-31",
    }


def _base_currency(company: str | None) -> str:
    if company:
        cur = frappe.db.get_value("Company", company, "default_currency")
        if cur:
            return cur
    return (
        frappe.db.get_single_value("Global Defaults", "default_currency")
        or "USD"
    )


class FinancialIntelligence:
    """Pure-Ibis financial analytics. No training, no caching."""

    def __init__(self, date_filter: str = "12m"):
        self.model_name = "FinancialIntelligence"
        self.date_filter = date_filter
        self.company = default_company()
        self.base_currency = _base_currency(self.company)
        self.fiscal_year = _fiscal_year_for(self.company) if self.company else None

    # ------------------------------------------------------------------ train
    def train(self) -> dict[str, Any]:
        """Generate comprehensive financial intelligence."""
        result = {
            "status": "success",
            "generated_at": _now_iso(),
            "company": self.company,
            "base_currency": self.base_currency,
            "overview": self._calculate_financial_overview(),
            "cash_flow": self._calculate_cash_flow(),
            "receivables": self._analyze_receivables(),
            "payables": self._analyze_payables(),
            "forex": self._analyze_forex_exposure(),
        }
        return result

    def predict(self) -> dict[str, Any]:
        """Same as train: every call is computed fresh, no stale cache."""
        return self.train()

    # ------------------------------------------------------------------ helpers
    def _gl_with_account(self, company: str | None = None):
        gle = t("GL Entry")
        acc = t("Account")
        joined = gle.join(acc, gle["account"] == acc["name"])
        joined = company_filter(joined, company or self.company)
        joined = joined.filter(joined["is_cancelled"] == 0)
        return joined

    def _scalar(self, expr, default: float = 0.0) -> float:
        """Execute an Ibis expression and return its single scalar value.

        Accepts a Table (1×1), a Column (Series of length 1), or a Scalar
        (numpy/pandas 0-d). Returns `default` if the result is empty/null.
        """
        result = expr.execute()
        if result is None:
            return default
        # Pandas/numpy scalar
        try:
            if hasattr(result, "iloc"):
                if result.ndim == 0:
                    v = result.item()
                else:
                    v = result.iloc[0]
                    # If it's a 1-row DataFrame, take the first column value
                    if hasattr(v, "iloc"):
                        v = v.iloc[0]
            else:
                v = result
        except Exception:
            return default
        if v is None:
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def _rows(self, expr) -> list[dict[str, Any]]:
        df = expr.execute()
        if df is None or len(df) == 0:
            return []
        return [
            {k: (None if v is None else v) for k, v in row.items()}
            for row in df.to_dict(orient="records")
        ]

    # ------------------------------------------------------------------ overview
    def _calculate_financial_overview(self) -> dict[str, Any]:
        fy_start = (self.fiscal_year or _fiscal_year_for(self.company or ""))["start_date"]
        mtd_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")

        joined = self._gl_with_account()

        # MTD
        mtd_inc = joined.filter(
            (joined["root_type"] == "Income")
            & (joined["posting_date"] >= mtd_start)
        ).aggregate(amount=(joined["credit"] - joined["debit"]).sum())
        mtd_income = self._scalar(mtd_inc["amount"].abs())

        mtd_exp = joined.filter(
            (joined["root_type"] == "Expense")
            & (joined["posting_date"] >= mtd_start)
        ).aggregate(amount=(joined["debit"] - joined["credit"]).sum())
        mtd_expenses = self._scalar(mtd_exp["amount"].abs())

        # YTD (fiscal)
        ytd_inc = joined.filter(
            (joined["root_type"] == "Income")
            & (joined["posting_date"] >= fy_start)
        ).aggregate(amount=(joined["credit"] - joined["debit"]).sum())
        ytd_income = self._scalar(ytd_inc["amount"].abs())

        ytd_exp = joined.filter(
            (joined["root_type"] == "Expense")
            & (joined["posting_date"] >= fy_start)
        ).aggregate(amount=(joined["debit"] - joined["credit"]).sum())
        ytd_expenses = self._scalar(ytd_exp["amount"].abs())

        mtd_revenue = mtd_income
        mtd_profit = mtd_revenue - mtd_expenses
        ytd_revenue = ytd_income
        ytd_expenses = ytd_expenses
        ytd_profit = ytd_revenue - ytd_expenses

        # YTD Interest and Depreciation for EBITDA. Same account-matching
        # convention as `calculate_ratio_trends` (analysis.py) and
        # `calculate_executive_summary` (summary.py) -- interest by account
        # name (this CoA tags no account_type for borrowing costs),
        # depreciation by `account_type == 'Depreciation'` -- so EBITDA
        # means the same thing across every dashboard that reports it. No
        # tax add-back: this CoA carries no income-tax / provision-for-tax
        # account distinct from indirect taxes (customs duty, GST) that are
        # real operating costs.
        ytd_interest_exp = joined.filter(
            (joined["root_type"] == "Expense")
            & (joined["posting_date"] >= fy_start)
            & (joined["account"].like("%Interest%"))
        ).aggregate(amount=(joined["debit"] - joined["credit"]).sum())
        ytd_interest_expense = self._scalar(ytd_interest_exp["amount"].abs())

        ytd_deprec = joined.filter(
            (joined["account_type"] == "Depreciation")
            & (joined["posting_date"] >= fy_start)
        ).aggregate(amount=(joined["debit"] - joined["credit"]).sum())
        ytd_depreciation = self._scalar(ytd_deprec["amount"].abs())

        ytd_ebit = ytd_profit + ytd_interest_expense
        ytd_ebitda = ytd_ebit + ytd_depreciation
        ebitda_margin = round((ytd_ebitda / ytd_revenue * 100), 1) if ytd_revenue > 0 else None

        # Monthly P&L trend: aggregate by YYYY-MM over the last 12 calendar months
        twelve_months_ago = datetime.now().replace(year=datetime.now().year - 1)
        import ibis
        period_expr = joined["posting_date"].strftime("%Y-%m").name("period")
        is_income = joined["root_type"] == "Income"
        is_expense = joined["root_type"] == "Expense"
        monthly_agg = (
            joined
            .filter(joined["posting_date"] >= twelve_months_ago.strftime("%Y-%m-%d"))
            .filter(joined["root_type"].isin(["Income", "Expense"]))
            .group_by(period_expr)
            .aggregate(
                revenue=ibis.ifelse(is_income, (joined["credit"] - joined["debit"]).abs(), 0).sum(),
                expenses=ibis.ifelse(is_expense, (joined["debit"] - joined["credit"]).abs(), 0).sum(),
            )
            .order_by("period")
        )
        monthly_rows = self._rows(monthly_agg)
        monthly_trend = []
        for r in monthly_rows:
            rev = float(r.get("revenue") or 0)
            exp = float(r.get("expenses") or 0)
            monthly_trend.append({
                "period": r["period"],
                "revenue": rev,
                "expenses": exp,
                "profit": rev - exp,
                "margin": round((rev - exp) / rev * 100, 1) if rev > 0 else 0,
            })

        # Revenue breakdown by parent_account
        _rev_diff = (joined["credit"] - joined["debit"]).abs()
        rev_break = (
            joined
            .filter(
                (joined["root_type"] == "Income")
                & (joined["posting_date"] >= fy_start)
            )
            .group_by(
                joined["parent_account"].coalesce(joined["account"]).name("category")
            )
            .aggregate(amount=_rev_diff.sum())
            .order_by(ibis.desc("amount"))
            .limit(10)
        )
        rev_rows = self._rows(rev_break)
        for r in rev_rows:
            amt = float(r.get("amount") or 0)
            r["amount"] = amt
            r["pct"] = round((amt / ytd_revenue * 100), 1) if ytd_revenue > 0 else 0

        # Expense breakdown by parent_account
        _exp_diff = (joined["debit"] - joined["credit"]).abs()
        exp_break = (
            joined
            .filter(
                (joined["root_type"] == "Expense")
                & (joined["posting_date"] >= fy_start)
            )
            .group_by(
                joined["parent_account"].coalesce(joined["account"]).name("category")
            )
            .aggregate(amount=_exp_diff.sum())
            .order_by(ibis.desc("amount"))
            .limit(10)
        )
        exp_rows = self._rows(exp_break)
        for r in exp_rows:
            amt = float(r.get("amount") or 0)
            r["amount"] = amt
            r["pct"] = round((amt / ytd_expenses * 100), 1) if ytd_expenses > 0 else 0

        # net_margin: net profit / revenue. gross_margin: not computed here
        # (no COGS query in overview); see strategic_finance/summary.py.
        net_margin = round((ytd_profit / ytd_revenue * 100), 1) if ytd_revenue > 0 else None

        return {
            "mtd_revenue": mtd_revenue,
            "mtd_expenses": mtd_expenses,
            "mtd_profit": mtd_profit,
            "ytd_revenue": ytd_revenue,
            "ytd_expenses": ytd_expenses,
            "ytd_profit": ytd_profit,
            "gross_margin": None,
            "ytd_ebitda": round(ytd_ebitda, 2),
            "ebitda_margin": ebitda_margin,
            "net_margin": net_margin,
            "monthly_trend": monthly_trend,
            "revenue_breakdown": rev_rows,
            "expense_breakdown": exp_rows,
        }

    # ------------------------------------------------------------------ cash flow
    def _calculate_cash_flow(self) -> dict[str, Any]:
        import ibis

        joined = self._gl_with_account()

        # Cash-equivalent accounts: Bank + Cash by account_type, plus
        # name-matched Fixed Deposit accounts. ERPNext models no term deposit:
        # `Account.account_type`'s Select options stop at Indirect Income, and
        # the schema's only native mention of a fixed deposit is
        # `Bank Guarantee.fixed_deposit_number` -- a margin-money field on an
        # unrelated document. An FD therefore lives in a plain Asset account
        # and is identifiable only by name, the same convention as the TDS/TCS
        # GL lookup in india_tax_intelligence/data.py.
        cash_agg = (
            self._cash_accounts(joined)
            .group_by(
                joined["account"].name("account"),
                joined["account_name"].name("account_name"),
                joined["account_type"].name("account_type"),
            )
            .aggregate(balance=(joined["debit"] - joined["credit"]).sum())
        )
        cash_rows: list[dict[str, Any]] = []
        for r in self._rows(cash_agg):
            balance = round(float(r.get("balance") or 0), 2)
            if balance == 0:
                continue
            # `account_class` is what the dashboard labels the row with. The
            # frontend used to re-derive it and fell back to printing
            # "Fixed Deposit" for any account with a blank account_type, so a
            # plain bank account with no type set was labelled a deposit.
            is_fd = (r.get("account_name") or "").lower().startswith(FD_PREFIX)
            r["balance"] = balance
            r["is_fd"] = is_fd
            r["account_class"] = "Fixed Deposit" if is_fd else (r.get("account_type") or "Other")
            cash_rows.append(r)
        cash_rows.sort(key=lambda r: -r["balance"])
        total_cash = sum(r["balance"] for r in cash_rows)
        for r in cash_rows:
            r["share_pct"] = round(r["balance"] / total_cash * 100, 1) if total_cash else None
        fd_rows = [r for r in cash_rows if r["is_fd"]]
        fd_balance = sum(r["balance"] for r in fd_rows)
        bank_balance = sum(
            r["balance"] for r in cash_rows if not r["is_fd"] and r.get("account_type") == "Bank"
        )
        cash_on_hand = sum(
            r["balance"] for r in cash_rows if not r["is_fd"] and r.get("account_type") == "Cash"
        )

        # Monthly inflows (Payment Entry Receive) for last 6 months
        pe = company_filter(t("Payment Entry"), self.company).filter(
            t("Payment Entry")["docstatus"] == 1
        )
        # last-6-months window is computed once and shared by both directions below
        six_months_ago = _months_ago(6)

        def _pe_monthly(payment_type: str) -> list[dict[str, Any]]:
            agg = (
                pe
                .filter(
                    (pe["payment_type"] == payment_type)
                    & (pe["posting_date"] >= six_months_ago)
                )
                .group_by(pe["posting_date"].truncate("month").name("period"))
                .aggregate(amount=pe["paid_amount"].sum())
                .order_by("period")
            )
            rows = self._rows(agg)
            for r in rows:
                r["period"] = str(r["period"])[:7] if r.get("period") else ""
            return rows

        cash_inflows = _pe_monthly("Receive")
        cash_outflows = _pe_monthly("Pay")

        avg_outflow = sum(float(o.get("amount") or 0) for o in cash_outflows) / max(len(cash_outflows), 1)
        avg_inflow = sum(float(i.get("amount") or 0) for i in cash_inflows) / max(len(cash_inflows), 1)
        net_burn = avg_outflow - avg_inflow
        runway_months = round(total_cash / net_burn, 1) if net_burn > 0 else 999

        # Inflow/outflow by source (party_type) for last 3 months
        three_months_ago = _months_ago(3)

        inflow_src = (
            pe
            .filter(
                (pe["payment_type"] == "Receive")
                & (pe["posting_date"] >= three_months_ago)
            )
            .group_by(pe["party_type"].name("source"))
            .aggregate(amount=pe["paid_amount"].sum())
            .order_by(ibis.desc("amount"))
        )
        inflow_by_source = [
            {**r, "source": r.get("source") or "Other"}
            for r in self._rows(inflow_src)
        ]
        outflow_use = (
            pe
            .filter(
                (pe["payment_type"] == "Pay")
                & (pe["posting_date"] >= three_months_ago)
            )
            .group_by(pe["party_type"].name("category"))
            .aggregate(amount=pe["paid_amount"].sum())
            .order_by(ibis.desc("amount"))
        )
        outflow_by_use = [
            {**r, "category": r.get("category") or "Other"}
            for r in self._rows(outflow_use)
        ]

        # Large transactions in last 1 month
        one_month_ago = _months_ago(1)
        large_tx = (
            pe
            .filter(pe["posting_date"] >= one_month_ago)
            .select(
                pe["name"],
                pe["posting_date"],
                pe["payment_type"],
                pe["party_type"],
                pe["party"],
                pe["paid_amount"],
                pe["reference_no"],
            )
            .order_by(pe["paid_amount"].desc())
            .limit(15)
        )
        large_transactions = self._rows(large_tx)

        return {
            "as_of": _today(),
            "total_cash": total_cash,
            "bank_balance": round(bank_balance, 2),
            "cash_on_hand": round(cash_on_hand, 2),
            "fd_balance": round(fd_balance, 2),
            # Spendable today without breaking a deposit.
            "liquid_cash": round(total_cash - fd_balance, 2),
            "cash_accounts": cash_rows,
            "post_dated": self._post_dated_cash(joined),
            # GL-based, so it reconciles to the balances above. The Payment
            # Entry series below cannot: it misses every journal-posted
            # movement (deposit sweeps, contra entries, bank charges).
            "monthly_cash_movement": self._monthly_cash_movement(joined, total_cash),
            "fixed_deposits": self._fixed_deposit_analysis(joined, fd_rows, total_cash),
            "avg_monthly_inflow": round(avg_inflow, 2),
            "avg_monthly_outflow": round(avg_outflow, 2),
            "net_burn_rate": round(net_burn, 2),
            "runway_months": runway_months,
            "monthly_inflows": cash_inflows,
            "monthly_outflows": cash_outflows,
            "inflow_by_source": inflow_by_source,
            "outflow_by_use": outflow_by_use,
            "large_transactions": large_transactions,
        }

    def _cash_accounts(self, joined):
        """Narrow a GL+Account join to the cash-equivalent accounts."""
        return joined.filter(
            joined["account_type"].isin(["Bank", "Cash"])
            | joined["account_name"].lower().startswith(FD_PREFIX)
        )

    def _post_dated_cash(self, joined) -> dict[str, Any] | None:
        """Cash movement that is posted but dated in the future.

        A post-dated cheque hits the ledger the day it is written, so a bank
        account can show a negative book balance for money that has not left
        yet. Separating the two is the difference between "we are overdrawn"
        and "we are not, yet" -- which is not a distinction a balance column
        can make on its own.
        """
        rows = self._rows(
            self._cash_accounts(joined)
            .filter(joined["posting_date"] > _today())
            .aggregate(
                net=(joined["debit"] - joined["credit"]).sum(),
                entries=joined["account"].count(),
                last_date=joined["posting_date"].max(),
            )
        )
        entries = int(rows[0].get("entries") or 0) if rows else 0
        if not entries:
            return None
        return {
            "entries": entries,
            "net": round(float(rows[0].get("net") or 0), 2),
            "last_date": str(rows[0].get("last_date") or "")[:10] or None,
        }

    def _monthly_cash_movement(
        self, joined, total_cash: float, months: int = 12
    ) -> list[dict[str, Any]]:
        """Monthly cash in/out from the GL, with each month's closing balance
        walked backwards from today's total so the series ties to the account
        balances instead of to an independently computed opening figure."""
        agg = (
            self._cash_accounts(joined)
            .filter(joined["posting_date"] >= _months_ago(months - 1))
            .group_by(joined["posting_date"].truncate("month").name("period"))
            .aggregate(inflow=joined["debit"].sum(), outflow=joined["credit"].sum())
            .order_by("period")
        )
        rows: list[dict[str, Any]] = []
        for r in self._rows(agg):
            inflow = float(r.get("inflow") or 0)
            outflow = float(r.get("outflow") or 0)
            rows.append(
                {
                    "period": str(r["period"])[:7] if r.get("period") else "",
                    "inflow": round(inflow, 2),
                    "outflow": round(outflow, 2),
                    "net": round(inflow - outflow, 2),
                }
            )
        # Future-dated months are walked through (so the current month's
        # closing excludes them) but not reported: `post_dated` covers them.
        balance = total_cash
        for r in reversed(rows):
            r["closing"] = round(balance, 2)
            balance -= r["net"]
        this_month = _today()[:7]
        return [r for r in rows if r["period"] <= this_month]

    def _fixed_deposit_analysis(
        self, joined, fd_rows: list[dict[str, Any]], total_cash: float, months: int = 12
    ) -> dict[str, Any] | None:
        """What the ledger can actually say about fixed deposits.

        Maturity date, tenor and contracted rate are not in the database at
        all (see `_cash_accounts` on ERPNext's missing deposit model), so this
        reports what is recoverable and nothing more: principal on deposit,
        how it moved, the bank reference each movement quotes, the interest
        booked against it, and which account it is swept to and from.
        """
        if not fd_rows:
            return None
        import re

        fd = joined.filter(joined["account"].isin([r["account"] for r in fd_rows]))
        balance = sum(r["balance"] for r in fd_rows)
        entries = self._rows(
            fd
            .filter(joined["posting_date"] >= _months_ago(months - 1))
            .select(
                joined["posting_date"],
                joined["voucher_no"],
                joined["debit"],
                joined["credit"],
                joined["remarks"],
                joined["against"],
            )
            .order_by(joined["posting_date"].desc())
        )

        # Bank deposit receipt numbers are quoted in the journal remarks
        # ("FD BKD FOR ... 50301417445901", "SWEEP-IN CREDIT - 50301417445901").
        # They are the only per-deposit identifier that exists, so they are
        # surfaced verbatim on the activity rows rather than aggregated into a
        # deposit register the ledger cannot actually support.
        ref_pat = re.compile(r"\d{10,}")
        monthly: dict[str, dict[str, float]] = {}
        placed = released = 0.0
        placements = releases = 0
        last_placement = last_release = None
        counterparties: dict[str, float] = {}
        activity: list[dict[str, Any]] = []
        for e in entries:
            date = str(e.get("posting_date") or "")[:10]
            debit = float(e.get("debit") or 0)
            credit = float(e.get("credit") or 0)
            bucket = monthly.setdefault(date[:7], {"placed": 0.0, "released": 0.0})
            bucket["placed"] += debit
            bucket["released"] += credit
            if debit:
                placed += debit
                placements += 1
                last_placement = last_placement or date
            if credit:
                released += credit
                releases += 1
                last_release = last_release or date
            against = e.get("against") or ""
            if against:
                counterparties[against] = counterparties.get(against, 0.0) + debit + credit
            if len(activity) < 12:
                ref = ref_pat.search(e.get("remarks") or "")
                activity.append(
                    {
                        "posting_date": date,
                        "voucher_no": e.get("voucher_no"),
                        "amount": round(debit or credit, 2),
                        "direction": "placement" if debit else "release",
                        "reference": ref.group(0) if ref else None,
                    }
                )

        series: list[dict[str, Any]] = []
        for period in sorted(monthly):
            bucket = monthly[period]
            series.append(
                {
                    "period": period,
                    "placed": round(bucket["placed"], 2),
                    "released": round(bucket["released"], 2),
                    "net": round(bucket["placed"] - bucket["released"], 2),
                }
            )
        running = balance
        for r in reversed(series):
            r["closing"] = round(running, 2)
            running -= r["net"]

        interest = self._deposit_interest()
        avg_balance = (
            sum(r["closing"] for r in series) / len(series) if series else balance
        )
        yield_pct = (
            round(interest["booked_fy"] / avg_balance * (12 / interest["months_elapsed"]) * 100, 2)
            if avg_balance > 0
            else None
        )
        return {
            "balance": round(balance, 2),
            "pct_of_cash": round(balance / total_cash * 100, 1) if total_cash else None,
            "accounts": [
                {"account": r["account"], "account_name": r["account_name"], "balance": r["balance"]}
                for r in fd_rows
            ],
            "monthly": series,
            "window_months": months,
            "placed": round(placed, 2),
            "released": round(released, 2),
            "placement_count": placements,
            "release_count": releases,
            "avg_ticket": round(placed / placements, 2) if placements else None,
            "last_placement": last_placement,
            "last_release": last_release,
            # Where the principal comes from and returns to: on a sweep
            # facility this is the operating current account, which is what
            # makes the deposit callable rather than locked.
            "swept_with": [
                a for a, _ in sorted(counterparties.items(), key=lambda kv: -kv[1])[:3]
            ],
            "recent_activity": activity,
            "interest_booked_fy": interest["booked_fy"],
            "interest_accrued": interest["accrued"],
            "fiscal_year": interest["fiscal_year"],
            "yield_pct": yield_pct,
        }

    def _deposit_interest(self) -> dict[str, Any]:
        """Deposit interest booked this fiscal year, and the accrual balance.

        Matched on account name (interest + deposit/FD) because the chart of
        accounts is the only place that link exists: nothing joins an interest
        account to the deposit that earned it.
        """
        joined = self._gl_with_account()
        name = joined["account_name"].lower()
        interest = joined.filter(
            name.contains("interest") & (name.contains("deposit") | name.contains("fd"))
        )
        fy = self.fiscal_year or _fiscal_year_for(self.company or "")
        booked = self._scalar(
            interest
            .filter(
                (joined["root_type"] == "Income")
                & (joined["posting_date"] >= fy["start_date"])
            )
            .aggregate(v=(joined["credit"] - joined["debit"]).sum())
        )
        accrued = self._scalar(
            interest
            .filter(joined["root_type"] == "Asset")
            .aggregate(v=(joined["debit"] - joined["credit"]).sum())
        )
        start = datetime.strptime(fy["start_date"], "%Y-%m-%d").date()
        elapsed = max((datetime.now().date() - start).days / 30.44, 1.0)
        return {
            "booked_fy": round(booked, 2),
            "accrued": round(accrued, 2),
            "fiscal_year": fy["name"],
            "months_elapsed": round(elapsed, 2),
        }

    # ------------------------------------------------------------------ receivables
    def _analyze_receivables(self) -> dict[str, Any]:
        import ibis

        si = company_filter(t("Sales Invoice"), self.company).filter(
            (t("Sales Invoice")["docstatus"] == 1)
            & (t("Sales Invoice")["outstanding_amount"] > 0)
        )

        ar_total = si.aggregate(
            total=si["outstanding_amount"].sum(),
            invoice_count=si.count(),
        )
        ar_total_row = self._rows(ar_total)
        if ar_total_row:
            ar_total_dict = ar_total_row[0]
        else:
            ar_total_dict = {"total": 0, "invoice_count": 0}

        # Aging buckets via a CASE expression on days-overdue (today minus
        # due date). Positive = overdue by that many days; <= 0 = not yet
        # due. (Was previously `due_date - today`, which put invoices
        # overdue by up to 354 days into "Current" and not-yet-due invoices
        # into the aged buckets -- exactly backwards. Fixed 2026-08-17.)
        days_overdue_expr = (datetime.now().date() - si["due_date"]).cast("int32")

        bucket_expr = ibis.cases(
            (days_overdue_expr <= 0, "Current"),
            ((days_overdue_expr >= 1) & (days_overdue_expr <= 30), "1-30 Days"),
            ((days_overdue_expr >= 31) & (days_overdue_expr <= 60), "31-60 Days"),
            ((days_overdue_expr >= 61) & (days_overdue_expr <= 90), "61-90 Days"),
            else_="90+ Days",
        ).name("bucket")

        aging_agg = (
            si.group_by(bucket_expr)
            .aggregate(
                count=si.count(),
                amount=si["outstanding_amount"].sum(),
            )
        )
        # Order buckets explicitly: collect rows, then sort in Python.
        bucket_order = {"Current": 0, "1-30 Days": 1, "31-60 Days": 2, "61-90 Days": 3, "90+ Days": 4}
        aging_rows = sorted(
            self._rows(aging_agg),
            key=lambda r: bucket_order.get(r.get("bucket", ""), 99),
        )

        # DSO: trailing 12m credit sales / 366 days
        si_sales = company_filter(t("Sales Invoice"), self.company).filter(
            (t("Sales Invoice")["docstatus"] == 1)
            & (t("Sales Invoice")["posting_date"] >= _months_ago(12))
        )
        dso_sales_12m = self._scalar(
            si_sales.aggregate(si_sales["base_grand_total"].sum().name("t"))["t"]
        )
        dso_ar_total = float(ar_total_dict.get("total") or 0)
        current_dso = round(dso_ar_total / dso_sales_12m * 366, 1) if dso_sales_12m > 0 else None

        # Average calendar age of open AR
        avg_age_agg = si.aggregate(
            avg_age=((datetime.now().date() - si["posting_date"]).cast("int32")).mean()
        )
        avg_open_age = self._scalar(avg_age_agg["avg_age"])

        # Top overdue customers
        si_overdue = si.filter(si["due_date"] < datetime.now().date())
        # Positive days-overdue (today minus due date); si_overdue is already
        # filtered to due_date < today so this is always > 0. Previously
        # `due_date - today` (negative) with `.max()` picked each customer's
        # LEAST overdue invoice and reported it as a negative number, which
        # the frontend's severity badge (lower=better) always painted green
        # regardless of actual severity. Fixed 2026-08-17.
        overdue_diff = (datetime.now().date() - si_overdue["due_date"]).cast("int32")
        overdue_agg = (
            si_overdue
            .group_by(si_overdue["customer"], si_overdue["customer_name"])
            .aggregate(
                invoice_count=si_overdue.count(),
                total_outstanding=si_overdue["outstanding_amount"].sum(),
                oldest_due_date=si_overdue["due_date"].min(),
                max_overdue_days=overdue_diff.max(),
            )
            .order_by(ibis.desc("total_outstanding"))
            .limit(15)
        )
        overdue_customers = self._rows(overdue_agg)

        # Collection trend (last 6 months)
        six_months_ago = _months_ago(6)
        per = t("Payment Entry Reference")
        pe_with_company = company_filter(t("Payment Entry"), self.company).filter(
            (t("Payment Entry")["docstatus"] == 1)
            & (t("Payment Entry")["payment_type"] == "Receive")
            & (t("Payment Entry")["posting_date"] >= six_months_ago)
        )
        coll = (
            pe_with_company
            .join(per, per["parent"] == pe_with_company["name"])
            .filter(per["reference_doctype"] == "Sales Invoice")
            .group_by(pe_with_company["posting_date"].truncate("month").name("period"))
            .aggregate(collected=per["allocated_amount"].sum())
            .order_by("period")
        )
        collections = self._rows(coll)
        for r in collections:
            r["period"] = str(r["period"])[:7] if r.get("period") else ""

        return {
            "total_outstanding": dso_ar_total,
            "invoice_count": int(ar_total_dict.get("invoice_count") or 0),
            "aging_buckets": aging_rows,
            "current_dso": current_dso,
            "avg_open_receivable_age_days": round(avg_open_age or 0.0, 1),
            "overdue_customers": overdue_customers,
            "collection_trend": collections,
        }

    # ------------------------------------------------------------------ payables
    def _analyze_payables(self) -> dict[str, Any]:
        import ibis

        pi = company_filter(t("Purchase Invoice"), self.company).filter(
            (t("Purchase Invoice")["docstatus"] == 1)
            & (t("Purchase Invoice")["outstanding_amount"] > 0)
        )

        ap_total = pi.aggregate(
            total=pi["outstanding_amount"].sum(),
            invoice_count=pi.count(),
        )
        ap_total_row = self._rows(ap_total)
        ap_dict = ap_total_row[0] if ap_total_row else {"total": 0, "invoice_count": 0}

        diff_expr = (pi["due_date"] - datetime.now().date()).cast("int32")
        # Aging buckets use days-overdue (today minus due date) -- the
        # mirror image of `diff_expr` above, which the Payment Schedule
        # section below correctly uses as "days until due" (negative =
        # overdue). Reusing diff_expr's sign directly here previously put
        # invoices overdue by months into "Current" and not-yet-due
        # invoices into the aged buckets -- exactly backwards, and directly
        # contradicted by Payment Schedule's own "Overdue" bucket a few
        # lines down using the opposite polarity. Fixed 2026-08-17.
        days_overdue_expr = (datetime.now().date() - pi["due_date"]).cast("int32")
        bucket_expr = ibis.cases(
            (days_overdue_expr <= 0, "Current"),
            ((days_overdue_expr >= 1) & (days_overdue_expr <= 30), "1-30 Days"),
            ((days_overdue_expr >= 31) & (days_overdue_expr <= 60), "31-60 Days"),
            ((days_overdue_expr >= 61) & (days_overdue_expr <= 90), "61-90 Days"),
            else_="90+ Days",
        ).name("bucket")
        aging_agg = (
            pi.group_by(bucket_expr)
            .aggregate(
                count=pi.count(),
                amount=pi["outstanding_amount"].sum(),
            )
        )
        bucket_order = {"Current": 0, "1-30 Days": 1, "31-60 Days": 2, "61-90 Days": 3, "90+ Days": 4}
        aging_rows = sorted(
            self._rows(aging_agg),
            key=lambda r: bucket_order.get(r.get("bucket", ""), 99),
        )

        # DPO: trailing 12m credit purchases
        pi_sales = company_filter(t("Purchase Invoice"), self.company).filter(
            (t("Purchase Invoice")["docstatus"] == 1)
            & (t("Purchase Invoice")["posting_date"] >= _months_ago(12))
        )
        dpo_purchases_12m = self._scalar(
            pi_sales.aggregate(pi_sales["base_grand_total"].sum().name("t"))["t"]
        )
        dpo_ap_total = float(ap_dict.get("total") or 0)
        current_dpo = round(dpo_ap_total / dpo_purchases_12m * 366, 1) if dpo_purchases_12m > 0 else None

        avg_age_agg = pi.aggregate(
            avg_age=((datetime.now().date() - pi["posting_date"]).cast("int32")).mean()
        )
        avg_open_age = self._scalar(avg_age_agg["avg_age"])
        today = datetime.now().date()

        upcoming = (
            pi
            .filter(pi["due_date"].between(today, _add_days(today, 30)))
            .select(
                name=pi["name"],
                supplier=pi["supplier"],
                supplier_name=pi["supplier_name"],
                posting_date=pi["posting_date"],
                due_date=pi["due_date"],
                outstanding_amount=pi["outstanding_amount"],
                days_until_due=(pi["due_date"] - today).cast("int32").name("days_until_due"),
            )
            .order_by("due_date")
            .limit(20)
        )
        upcoming_payments = self._rows(upcoming)

        # Top suppliers by payable
        top_sup = (
            pi
            .group_by(pi["supplier"], pi["supplier_name"])
            .aggregate(
                invoice_count=pi.count(),
                total_outstanding=pi["outstanding_amount"].sum(),
            )
            .order_by(ibis.desc("total_outstanding"))
            .limit(10)
        )
        top_suppliers = self._rows(top_sup)

        # Payment schedule buckets
        period_expr = ibis.cases(
            (diff_expr < 0, "Overdue"),
            ((diff_expr >= 0) & (diff_expr <= 7), "This Week"),
            ((diff_expr >= 8) & (diff_expr <= 14), "Next Week"),
            ((diff_expr >= 15) & (diff_expr <= 30), "This Month"),
            else_="Later",
        ).name("period")
        sched_agg = (
            pi.group_by(period_expr)
            .aggregate(
                count=pi.count(),
                amount=pi["outstanding_amount"].sum(),
            )
        )
        period_order = {"Overdue": 0, "This Week": 1, "Next Week": 2, "This Month": 3, "Later": 4}
        payment_schedule = sorted(
            self._rows(sched_agg),
            key=lambda r: period_order.get(r.get("period", ""), 99),
        )

        return {
            "total_outstanding": dpo_ap_total,
            "invoice_count": int(ap_dict.get("invoice_count") or 0),
            "aging_buckets": aging_rows,
            "current_dpo": current_dpo,
            "avg_open_payable_age_days": round(avg_open_age or 0.0, 1),
            "upcoming_payments": upcoming_payments,
            "top_suppliers": top_suppliers,
            "payment_schedule": payment_schedule,
        }

    # ------------------------------------------------------------------ forex
    def _analyze_forex_exposure(self) -> dict[str, Any]:
        import ibis

        base = self.base_currency
        si = company_filter(t("Sales Invoice"), self.company).filter(
            (t("Sales Invoice")["docstatus"] == 1)
            & (t("Sales Invoice")["outstanding_amount"] > 0)
            & (t("Sales Invoice")["currency"] != base)
        )
        fx_rec_agg = (
            si
            .group_by(si["currency"])
            .aggregate(
                invoice_count=si.count(),
                outstanding_foreign=si["outstanding_amount"].sum(),
                outstanding_base=(si["outstanding_amount"] * si["conversion_rate"]).sum(),
                avg_rate=si["conversion_rate"].mean(),
            )
        )
        fx_receivables = self._rows(fx_rec_agg)

        pi = company_filter(t("Purchase Invoice"), self.company).filter(
            (t("Purchase Invoice")["docstatus"] == 1)
            & (t("Purchase Invoice")["outstanding_amount"] > 0)
            & (t("Purchase Invoice")["currency"] != base)
        )
        fx_pay_agg = (
            pi
            .group_by(pi["currency"])
            .aggregate(
                invoice_count=pi.count(),
                outstanding_foreign=pi["outstanding_amount"].sum(),
                outstanding_base=(pi["outstanding_amount"] * pi["conversion_rate"]).sum(),
                avg_rate=pi["conversion_rate"].mean(),
            )
        )
        fx_payables = self._rows(fx_pay_agg)

        # Current exchange rates from Currency Exchange (latest <= today)
        currencies = {r["currency"] for r in fx_receivables} | {p["currency"] for p in fx_payables}
        current_rates: dict[str, float] = {}
        for cur in currencies:
            CurrencyExchange = frappe.qb.DocType("Currency Exchange")
            rows = (
                frappe.qb.from_(CurrencyExchange)
                .select(CurrencyExchange.exchange_rate)
                .where(
                    (CurrencyExchange.from_currency == cur)
                    & (CurrencyExchange.to_currency == base)
                    & (CurrencyExchange.date <= datetime.now().date())
                )
                .orderby(CurrencyExchange.date, order=frappe.qb.desc)
                .limit(1)
                .run(as_dict=True)
            )
            if rows and rows[0].exchange_rate is not None:
                current_rates[cur] = float(rows[0].exchange_rate)

        total_rec_foreign = 0.0
        total_rec_base = 0.0
        total_unrealized_ar = 0.0
        for r in fx_receivables:
            r["outstanding_foreign"] = float(r.get("outstanding_foreign") or 0)
            r["outstanding_base"] = float(r.get("outstanding_base") or 0)
            r["avg_rate"] = float(r.get("avg_rate") or 0)
            cur = current_rates.get(r["currency"], r["avg_rate"])
            r["current_rate"] = cur
            r["current_value"] = r["outstanding_foreign"] * cur
            r["unrealized_gain_loss"] = r["current_value"] - r["outstanding_base"]
            total_rec_foreign += r["outstanding_foreign"]
            total_rec_base += r["outstanding_base"]
            total_unrealized_ar += r["unrealized_gain_loss"]

        total_pay_foreign = 0.0
        total_pay_base = 0.0
        total_unrealized_ap = 0.0
        for p in fx_payables:
            p["outstanding_foreign"] = float(p.get("outstanding_foreign") or 0)
            p["outstanding_base"] = float(p.get("outstanding_base") or 0)
            p["avg_rate"] = float(p.get("avg_rate") or 0)
            cur = current_rates.get(p["currency"], p["avg_rate"])
            p["current_rate"] = cur
            p["current_value"] = p["outstanding_foreign"] * cur
            p["unrealized_gain_loss"] = p["current_value"] - p["outstanding_base"]
            total_pay_foreign += p["outstanding_foreign"]
            total_pay_base += p["outstanding_base"]
            total_unrealized_ap += p["unrealized_gain_loss"]

        net_exposure: dict[str, dict[str, float]] = {}
        for r in fx_receivables:
            net_exposure.setdefault(
                r["currency"],
                {"receivable": 0.0, "payable": 0.0, "current_rate": r.get("current_rate", 0.0)},
            )
            net_exposure[r["currency"]]["receivable"] = r["outstanding_foreign"]
        for p in fx_payables:
            net_exposure.setdefault(
                p["currency"],
                {"receivable": 0.0, "payable": 0.0, "current_rate": p.get("current_rate", 0.0)},
            )
            net_exposure[p["currency"]]["payable"] = p["outstanding_foreign"]

        exposure_summary = []
        for currency, data in net_exposure.items():
            net = data["receivable"] - data["payable"]
            exposure_summary.append({
                "currency": currency,
                "receivable": data["receivable"],
                "payable": data["payable"],
                "net_exposure": net,
                "current_rate": data["current_rate"],
                "net_exposure_base": net * data["current_rate"],
                "position": "Long" if net > 0 else "Short",
            })

        # At-risk invoices: large forex exposure nearing due date, top 20 by amount
        at_risk_si = (
            si
            .select(
                doctype=ibis_literal("Sales Invoice").name("doctype"),
                name=si["name"],
                party=si["customer"].name("party"),
                currency=si["currency"],
                outstanding_amount=si["outstanding_amount"],
                conversion_rate=si["conversion_rate"],
                due_date=si["due_date"],
                days_to_due=(si["due_date"] - datetime.now().date()).cast("int32").name("days_to_due"),
            )
            .order_by(si["outstanding_amount"].desc())
            .limit(20)
        )
        at_risk_pi = (
            pi
            .select(
                doctype=ibis_literal("Purchase Invoice").name("doctype"),
                name=pi["name"],
                party=pi["supplier"].name("party"),
                currency=pi["currency"],
                outstanding_amount=pi["outstanding_amount"],
                conversion_rate=pi["conversion_rate"],
                due_date=pi["due_date"],
                days_to_due=(pi["due_date"] - datetime.now().date()).cast("int32").name("days_to_due"),
            )
            .order_by(pi["outstanding_amount"].desc())
            .limit(20)
        )
        ar_risks = self._rows(at_risk_si)
        ap_risks = self._rows(at_risk_pi)
        at_risk_invoices = (ar_risks + ap_risks)
        at_risk_invoices.sort(key=lambda r: -float(r.get("outstanding_amount") or 0))
        at_risk_invoices = at_risk_invoices[:20]

        # Realized forex gains/losses from Journal Entry (account name LIKE 'Exchange Gain/Loss/Forex')
        je = company_filter(t("Journal Entry"), self.company).filter(
            (t("Journal Entry")["docstatus"] == 1)
            & (t("Journal Entry")["posting_date"] >= _months_ago(12))
        )
        jea = t("Journal Entry Account").select("parent", "account", "credit", "debit")
        acc = t("Account").select(account_id="name", account_name="account_name")
        realized = (
            je
            .join(jea, jea["parent"] == je["name"])
            .join(acc, acc["account_id"] == jea["account"])
            .filter(
                acc["account_name"].like("%Exchange Gain%")
                | acc["account_name"].like("%Exchange Loss%")
                | acc["account_name"].like("%Forex%")
            )
            .group_by(je["posting_date"].truncate("month").name("period"))
            .aggregate(
                forex_gain=ibis.cases(
                    (jea["credit"] > jea["debit"], jea["credit"] - jea["debit"]),
                    else_=0,
                ).sum(),
                forex_loss=ibis.cases(
                    (jea["debit"] > jea["credit"], jea["debit"] - jea["credit"]),
                    else_=0,
                ).sum(),
            )
            .order_by("period")
        )
        realized_rows = self._rows(realized)
        for r in realized_rows:
            r["period"] = str(r["period"])[:7] if r.get("period") else ""
            r["forex_gain"] = float(r.get("forex_gain") or 0)
            r["forex_loss"] = float(r.get("forex_loss") or 0)

        return {
            "base_currency": base,
            "receivables_by_currency": fx_receivables,
            "payables_by_currency": fx_payables,
            "exposure_summary": exposure_summary,
            "total_receivable_base": total_rec_base,
            "total_payable_base": total_pay_base,
            "net_exposure_base": total_rec_base - total_pay_base,
            "total_unrealized_ar": round(total_unrealized_ar, 2),
            "total_unrealized_ap": round(total_unrealized_ap, 2),
            "net_unrealized": round(total_unrealized_ar - total_unrealized_ap, 2),
            "at_risk_invoices": at_risk_invoices,
            "realized_forex_trend": realized_rows,
        }


# ─── Local helpers (no dateutil / pandas / numpy at module scope) ──────────
def _months_ago(n: int) -> str:
    """Return YYYY-MM-DD for the first day of the month `n` months ago."""
    from datetime import date
    today = date.today()
    month_index = today.year * 12 + (today.month - 1) - n
    y, m = divmod(month_index, 12)
    return f"{y:04d}-{m + 1:02d}-01"


def _add_days(base_date, days: int):
    from datetime import timedelta
    if hasattr(base_date, "date"):
        base_date = base_date.date()
    return base_date + timedelta(days=days)


def ibis_literal(value):
    """Lazy-import ibis.literal so the module loads even if ibis is missing
    at import time (e.g. for IDE/lint)."""
    import ibis
    return ibis.literal(value)


def run_financial_intelligence(refresh: bool = False, date_filter: str = "12m") -> dict[str, Any]:
    """Run financial intelligence analysis (computed fresh, no cache)."""
    return FinancialIntelligence(date_filter=date_filter).train()
