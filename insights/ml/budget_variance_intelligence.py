from __future__ import annotations

"""
Budget Variance Intelligence Module

This module provides comprehensive budget variance analysis capabilities including:
- Budget vs Actual analysis with detailed variance reporting
- Forecast accuracy tracking and improvement recommendations
- Department-wise budget performance analytics
- Automated variance alerts and notifications
- Budget planning optimization with predictive insights
- Cash flow variance analysis and trend identification

Author: AI Assistant
Version: 1.0.0
"""

from typing import TYPE_CHECKING, Any

import frappe

if TYPE_CHECKING:
    pass

import logging

from frappe.query_builder import Case
from frappe.query_builder.functions import Abs, Coalesce, Sum
from frappe.utils import flt, getdate

logger = logging.getLogger(__name__)


def _is_favorable(root_type: str | None, actual: float, budget: float) -> bool | None:
    """Income beats plan when actual > budget, Expense when actual <= budget; None without a budget."""
    if not budget:
        return None
    return actual > budget if root_type == "Income" else actual <= budget


def _prorated_amount(amount: float, row_start, row_end, start, end) -> float:
    """Share of `amount`, spread evenly over row_start..row_end (inclusive), that falls in start..end (inclusive)."""
    lo, hi = max(row_start, start), min(row_end, end)
    if hi < lo:
        return 0.0
    return flt(amount) * ((hi - lo).days + 1) / ((row_end - row_start).days + 1)


class BudgetVarianceIntelligence:
    """
    Advanced budget variance analysis system providing:
    - Comprehensive budget vs actual tracking
    - Variance analysis across multiple dimensions 
    - Forecast accuracy measurement
    - Automated budget performance alerts
    - Predictive budget optimization
    """

    def __init__(self, company: str | None = None, fiscal_year: str | None = None,
                 budget_period: str = "monthly"):
        """
        Initialize Budget Variance Intelligence
        
        Args:
            company: Company for budget analysis
            fiscal_year: Fiscal year for budget tracking
            budget_period: Budget period granularity (monthly/quarterly)
        """
        from insights.api.ml.permissions import permitted_company
        from insights.ml.financial_intelligence import _base_currency, _fiscal_year_for

        # `permitted_company` (not `default_company`/`get_user_default`
        # directly): every query below is raw `frappe.qb`, which -- unlike
        # `frappe.get_list` -- applies NO row-level permission check at all.
        # A user default or site-wide Global Default is a preference, not a
        # permission boundary; a user restricted via User Permission to
        # Company B but whose default/global company is A would previously
        # get company A's GL Entries, Budgets, and Accounts back even
        # without read access to company A. `permitted_company` routes
        # through `frappe.get_list("Company")`, which does apply User
        # Permissions, and throws if a company is requested but not
        # permitted.
        self.company = permitted_company({"company": company} if company else None)
        if not self.company:
            # None means either zero permitted companies, or several with no
            # single default -- every query below filters `company ==
            # self.company` unconditionally, so `None` would silently return
            # zero rows everywhere rather than "all companies". Fail loud
            # instead: a report that quietly shows nothing is worse than one
            # that says why.
            frappe.throw(
                frappe._("Set a default Company (or ask an administrator to grant one) to view budget variance analysis.")
            )
        self.budget_period = budget_period
        self.base_currency = _base_currency(self.company)

        # Get fiscal year dates. An explicit `fiscal_year` name is looked up
        # directly; otherwise resolve the fiscal year containing today (with
        # a calendar-year fallback if the company has no Fiscal Year record).
        if fiscal_year:
            fy_doc = frappe.get_doc("Fiscal Year", fiscal_year)
            self.fiscal_year = fiscal_year
            self.fy_start_date = fy_doc.year_start_date
            self.fy_end_date = fy_doc.year_end_date
        else:
            fy = _fiscal_year_for(self.company)
            self.fiscal_year = fy["name"]
            self.fy_start_date = frappe.utils.getdate(fy["start_date"])
            self.fy_end_date = frappe.utils.getdate(fy["end_date"])

        # Budget rows are fetched once per overview call (see _fetch_budget_data)
        self._budget_rows = None
        self._errors: list[str] = []
        self.cache_timeout = 3600  # 1 hour

    def get_budget_variance_overview(self) -> dict[str, Any]:
        """
        Get comprehensive budget variance overview

        Returns:
            Dict containing complete budget variance analysis. ``has_budget`` is False
            when no submitted Budget covers the fiscal year (the sections are then
            empty instead of zero-filled); ``errors`` lists sections that failed.
        """
        self._errors = []
        self._budget_rows = None
        try:
            logger.info("Generating budget variance overview")

            has_budget = bool(self._fetch_budget_data())

            # Get budget vs actual analysis
            variance_summary = self._get_variance_summary()

            # Get departmental analysis
            dept_analysis = self._get_departmental_variance()

            # Get account-wise analysis
            account_analysis = self._get_account_variance()

            # Get forecast accuracy metrics
            forecast_accuracy = self._get_forecast_accuracy()

            # Get variance trends
            variance_trends = self._get_variance_trends()

            # Get budget alerts
            alerts = self._get_variance_alerts()

            # Get performance metrics
            performance_metrics = self._get_budget_performance_metrics()

            # Get improvement recommendations
            recommendations = self._get_variance_recommendations()

            return {
                "has_budget": has_budget,
                "errors": self._errors,
                "summary": variance_summary,
                "departmental_analysis": dept_analysis,
                "account_analysis": account_analysis,
                "forecast_accuracy": forecast_accuracy,
                "variance_trends": variance_trends,
                "alerts": alerts,
                "performance_metrics": performance_metrics,
                "recommendations": recommendations,
                "last_updated": frappe.utils.now(),
                "base_currency": self.base_currency,
                "period_info": {
                    "fiscal_year": self.fiscal_year,
                    "start_date": str(self.fy_start_date),
                    "end_date": str(self.fy_end_date),
                    "budget_period": self.budget_period
                }
            }

        except Exception as e:
            self._fail("overview", e)
            return {"has_budget": False, "errors": self._errors}

    def _get_variance_summary(self) -> dict[str, Any]:
        """Get high-level budget variance summary"""
        try:
            budget_data = self._fetch_budget_data()
            if not budget_data:
                return {}

            # Actuals are scoped to the budgeted account/cost-center pairs so the
            # total compares like with like (unbudgeted postings are not utilisation).
            merged = self._merge_budget_actual(budget_data, self._fetch_actual_data())
            total_budget = sum(item["budget_amount"] for item in merged)
            total_actual = sum(item["actual_amount"] for item in merged)

            total_variance = total_actual - total_budget
            variance_percentage = (total_variance / total_budget * 100) if total_budget != 0 else 0

            # Favourable: income above plan / expense below plan. Adverse is the mirror.
            favorable_variance = sum(
                max(0, item["variance"] if item["root_type"] == "Income" else -item["variance"])
                for item in merged
            )
            adverse_variance = sum(
                max(0, -item["variance"] if item["root_type"] == "Income" else item["variance"])
                for item in merged
            )

            # Get variance trend
            variance_trend = self._calculate_variance_trend()

            return {
                "total_budget": total_budget,
                "total_actual": total_actual,
                "total_variance": total_variance,
                "variance_percentage": variance_percentage,
                "favorable_variance": favorable_variance,
                "adverse_variance": adverse_variance,
                "variance_trend": variance_trend,
                "budget_utilization": (total_actual / total_budget * 100) if total_budget != 0 else 0,
                "status": self._get_variance_status(variance_percentage),
                "ytd_performance": self._get_ytd_performance()
            }

        except Exception as e:
            self._fail("variance summary", e)
            return {}

    def _get_departmental_variance(self) -> list[dict[str, Any]]:
        """Get department-wise budget variance analysis (expense budgets of the department's cost center)"""
        try:
            departments = self._get_active_departments()
            dept_variances = []

            for dept in departments:
                dept_budget = self._get_department_budget(dept.name)
                dept_actual = self._get_department_actual(dept.name)

                if dept_budget or dept_actual:
                    variance = dept_actual - dept_budget
                    variance_pct = (variance / dept_budget * 100) if dept_budget != 0 else 0

                    dept_variances.append({
                        "department": dept.name,
                        "budget": dept_budget,
                        "actual": dept_actual,
                        "variance": variance,
                        "variance_percentage": variance_pct,
                        "favorable": _is_favorable("Expense", dept_actual, dept_budget),
                        "status": self._get_variance_status(variance_pct),
                        "trend": self._get_department_trend(dept.name),
                        "key_accounts": self._get_department_key_accounts(dept.name)
                    })

            # Sort by absolute variance
            dept_variances.sort(key=lambda x: abs(x['variance']), reverse=True)
            return dept_variances

        except Exception as e:
            self._fail("departmental variance", e)
            return []

    def _get_account_variance(self) -> list[dict[str, Any]]:
        """Get account-wise budget variance analysis"""
        try:
            # One entry per budgeted account (any cost center)
            budgeted = {b["account"]: b for b in self._fetch_budget_data()}
            account_variances = []

            for account, b in budgeted.items():
                budget_amount = self._get_account_budget(account)
                actual_amount = self._get_account_actual(account)

                if budget_amount != 0 or actual_amount != 0:
                    variance = actual_amount - budget_amount
                    variance_pct = (variance / budget_amount * 100) if budget_amount != 0 else 0

                    account_variances.append({
                        "account": account,
                        "account_type": b["account_type"],
                        "root_type": b["root_type"],
                        "budget": budget_amount,
                        "actual": actual_amount,
                        "variance": variance,
                        "variance_percentage": variance_pct,
                        "favorable": _is_favorable(b["root_type"], actual_amount, budget_amount),
                        "status": self._get_variance_status(variance_pct),
                        "monthly_breakdown": self._get_account_monthly_breakdown(account),
                        "impact_level": self._get_variance_impact_level(abs(variance), budget_amount)
                    })

            # Sort by absolute variance
            account_variances.sort(key=lambda x: abs(x['variance']), reverse=True)
            return account_variances[:20]  # Top 20 accounts by variance

        except Exception as e:
            self._fail("account variance", e)
            return []

    def _get_forecast_accuracy(self) -> dict[str, Any]:
        """Calculate forecast accuracy metrics"""
        try:
            # Get historical forecast vs actual data
            forecast_data = self._get_historical_forecasts()

            if not forecast_data:
                return {
                    "status": "not_implemented",
                    "message": "Historical budget forecast tracking is not yet captured; accuracy cannot be computed.",
                }

            accuracies = []
            for item in forecast_data:
                forecast_amount = item.get('forecast_amount', 0)
                actual_amount = item.get('actual_amount', 0)

                if forecast_amount != 0:
                    accuracy = 100 - abs((actual_amount - forecast_amount) / forecast_amount * 100)
                    accuracies.append(max(0, accuracy))  # Ensure non-negative

            if not accuracies:
                return {}

            avg_accuracy = sum(accuracies) / len(accuracies)

            # Calculate accuracy by period
            monthly_accuracy = self._get_monthly_forecast_accuracy()

            # Get forecast improvement trends
            accuracy_trend = self._calculate_forecast_accuracy_trend()

            return {
                "overall_accuracy": avg_accuracy,
                "accuracy_grade": self._get_accuracy_grade(avg_accuracy),
                "monthly_accuracy": monthly_accuracy,
                "accuracy_trend": accuracy_trend,
                "forecast_bias": self._calculate_forecast_bias(forecast_data),
                "improvement_recommendations": self._get_forecast_improvement_tips(avg_accuracy)
            }

        except Exception as e:
            logger.error(f"Error calculating forecast accuracy: {e}")
            return {}

    def _get_variance_trends(self) -> dict[str, Any]:
        """Get budget variance trends over time"""
        try:
            # Get monthly variance data
            monthly_variances = self._get_monthly_variances()

            # Calculate trend metrics
            trend_direction = self._calculate_trend_direction(monthly_variances)
            volatility = self._calculate_variance_volatility(monthly_variances)
            seasonality = self._detect_variance_seasonality(monthly_variances)

            # Get rolling averages
            rolling_avg_3m = self._get_rolling_average(monthly_variances, 3)
            rolling_avg_6m = self._get_rolling_average(monthly_variances, 6)

            return {
                "monthly_variances": monthly_variances,
                "trend_direction": trend_direction,
                "volatility": volatility,
                "seasonality": seasonality,
                "rolling_average_3m": rolling_avg_3m,
                "rolling_average_6m": rolling_avg_6m,
                "variance_prediction": self._predict_next_period_variance()
            }

        except Exception as e:
            self._fail("variance trends", e)
            return {}

    def _get_variance_alerts(self) -> list[dict[str, Any]]:
        """Generate automated variance alerts"""
        try:
            alerts = []

            # Check for significant variances
            variance_summary = self._get_variance_summary()
            if variance_summary:
                variance_pct = variance_summary.get('variance_percentage', 0)

                if abs(variance_pct) > 15:  # Alert for variances over 15%
                    alerts.append({
                        "type": "high_variance",
                        "severity": "high" if abs(variance_pct) > 25 else "medium",
                        "title": f"High Budget Variance: {variance_pct:.1f}%",
                        "description": f"Overall budget variance of {variance_pct:.1f}% exceeds acceptable threshold",
                        "action": "Review budget assumptions and actual spending patterns"
                    })

            # Check for department variances
            dept_variances = self._get_departmental_variance()
            for dept in dept_variances[:5]:  # Top 5 departments
                if abs(dept['variance_percentage']) > 20:
                    alerts.append({
                        "type": "department_variance",
                        "severity": "medium",
                        "title": f"Department Alert: {dept['department']}",
                        "description": f"{dept['department']} has {dept['variance_percentage']:.1f}% variance",
                        "action": f"Review {dept['department']} spending and budget allocation"
                    })

            # Check for forecast accuracy issues
            forecast_accuracy = self._get_forecast_accuracy()
            if forecast_accuracy and forecast_accuracy.get('overall_accuracy', 100) < 70:
                alerts.append({
                    "type": "forecast_accuracy",
                    "severity": "medium",
                    "title": "Low Forecast Accuracy",
                    "description": f"Forecast accuracy at {forecast_accuracy['overall_accuracy']:.1f}%",
                    "action": "Review forecasting methodology and assumptions"
                })

            # Check for cash flow issues
            cash_flow_variance = self._get_cash_flow_variance()
            if cash_flow_variance and abs(cash_flow_variance.get('variance_percentage', 0)) > 30:
                alerts.append({
                    "type": "cash_flow",
                    "severity": "high",
                    "title": "Cash Flow Variance Alert",
                    "description": f"Cash flow variance of {cash_flow_variance['variance_percentage']:.1f}%",
                    "action": "Review cash flow projections and working capital management"
                })

            return sorted(alerts, key=lambda x: {'high': 3, 'medium': 2, 'low': 1}[x['severity']], reverse=True)

        except Exception as e:
            self._fail("variance alerts", e)
            return []

    def _get_budget_performance_metrics(self) -> dict[str, Any]:
        """Calculate comprehensive budget performance metrics"""
        try:
            # Budget accuracy metrics
            budget_accuracy = self._calculate_budget_accuracy()

            # Budget efficiency metrics
            budget_efficiency = self._calculate_budget_efficiency()

            # Variance control metrics
            variance_control = self._calculate_variance_control()

            # Budget planning quality
            planning_quality = self._assess_budget_planning_quality()

            # Overall budget score
            overall_score = self._calculate_overall_budget_score(
                budget_accuracy, budget_efficiency, variance_control, planning_quality
            )

            return {
                "overall_score": overall_score,
                "budget_accuracy": budget_accuracy,
                "budget_efficiency": budget_efficiency,
                "variance_control": variance_control,
                "planning_quality": planning_quality,
                "benchmarks": self._get_industry_benchmarks(),
                "improvement_areas": self._identify_improvement_areas(overall_score)
            }

        except Exception as e:
            self._fail("performance metrics", e)
            return {}

    def _get_variance_recommendations(self) -> list[dict[str, Any]]:
        """Generate AI-powered variance improvement recommendations"""
        try:
            recommendations = []

            # Analyze variance patterns
            variance_summary = self._get_variance_summary()
            if not variance_summary:
                return recommendations

            variance_pct = variance_summary.get('variance_percentage', 0)

            # High-level recommendations based on overall variance
            if abs(variance_pct) > 20:
                recommendations.append({
                    "category": "budget_planning",
                    "priority": "high",
                    "title": "Improve Budget Planning Process",
                    "description": "Significant variance indicates issues with budget assumptions",
                    "actions": [
                        "Review historical data and trends more thoroughly",
                        "Implement rolling forecasts",
                        "Increase stakeholder involvement in budget planning",
                        "Consider zero-based budgeting approach"
                    ],
                    "impact": "High",
                    "effort": "Medium"
                })

            # Department-specific recommendations
            dept_variances = self._get_departmental_variance()
            for dept in dept_variances[:3]:  # Top 3 problematic departments
                if abs(dept['variance_percentage']) > 15:
                    recommendations.append({
                        "category": "department_control",
                        "priority": "medium",
                        "title": f"Enhance {dept['department']} Budget Control",
                        "description": f"{dept['department']} shows consistent variance patterns",
                        "actions": [
                            f"Implement monthly budget reviews for {dept['department']}",
                            "Provide budget management training",
                            "Set up automated spending alerts",
                            "Review budget allocation methodology"
                        ],
                        "impact": "Medium",
                        "effort": "Low"
                    })

            # Forecast accuracy recommendations
            forecast_accuracy = self._get_forecast_accuracy()
            if forecast_accuracy and forecast_accuracy.get('overall_accuracy', 100) < 80:
                recommendations.append({
                    "category": "forecasting",
                    "priority": "medium",
                    "title": "Enhance Forecasting Accuracy",
                    "description": "Forecast accuracy below optimal levels",
                    "actions": [
                        "Implement predictive analytics tools",
                        "Create scenario-based forecasting models",
                        "Increase forecast review frequency",
                        "Train team on advanced forecasting techniques"
                    ],
                    "impact": "Medium",
                    "effort": "Medium"
                })

            # Process improvement recommendations
            if self._needs_process_improvement():
                recommendations.append({
                    "category": "process",
                    "priority": "low",
                    "title": "Automate Budget Monitoring",
                    "description": "Implement automated budget tracking and alerts",
                    "actions": [
                        "Set up automated variance reports",
                        "Create budget dashboard for real-time monitoring",
                        "Implement approval workflows for budget changes",
                        "Establish variance investigation procedures"
                    ],
                    "impact": "High",
                    "effort": "High"
                })

            return recommendations

        except Exception as e:
            self._fail("recommendations", e)
            return []

    # Helper methods for data fetching and calculations

    def _fail(self, section: str, e: Exception) -> None:
        """Record a failed section: log it once and surface it in the payload's `errors`."""
        msg = f"{section}: {e}"
        if msg not in self._errors:
            self._errors.append(msg)
            logger.error(f"Budget variance {msg}")
            frappe.log_error(msg, "Budget Variance Intelligence")

    def _fetch_budget_data(self) -> list[dict[str, Any]]:
        """Submitted cost-center Budgets overlapping the fiscal year (ERPNext v16: one account per Budget).

        Cached per overview call. Each row carries its `budget_distribution` rows
        (per-period amounts) so period budgets follow the real distribution.
        """
        if self._budget_rows is not None:
            return self._budget_rows

        Budget = frappe.qb.DocType("Budget")
        Account = frappe.qb.DocType("Account")
        rows = (
            frappe.qb.from_(Budget)
            .join(Account)
            .on(Account.name == Budget.account)
            .select(
                Budget.name.as_("budget_name"),
                Budget.cost_center,
                Budget.account,
                Budget.budget_amount,
                Budget.budget_start_date.as_("start"),
                Budget.budget_end_date.as_("end"),
                Budget.creation,
                Account.root_type,
                Account.account_type,
            )
            .where(Budget.company == self.company)
            .where(Budget.docstatus == 1)
            .where(Budget.budget_against == "Cost Center")
            .where(Budget.budget_start_date <= self.fy_end_date)
            .where(Budget.budget_end_date >= self.fy_start_date)
            .run(as_dict=True)
        )

        distributions: dict[str, list] = {}
        if rows:
            Dist = frappe.qb.DocType("Budget Distribution")
            for d in (
                frappe.qb.from_(Dist)
                .select(Dist.parent, Dist.start_date, Dist.end_date, Dist.amount)
                .where(Dist.parent.isin([r.budget_name for r in rows]))
                .run(as_dict=True)
            ):
                distributions.setdefault(d.parent, []).append(d)

        for r in rows:
            r["budget_amount"] = flt(r["budget_amount"])
            r["distribution"] = distributions.get(r["budget_name"], [])
        self._budget_rows = rows
        return rows

    @staticmethod
    def _period_budget(row: dict, start, end) -> float:
        """Budget falling in start..end: the Budget's own distribution rows, else even day pro-rating."""
        if row.get("distribution"):
            return sum(
                _prorated_amount(d["amount"], d["start_date"], d["end_date"], start, end)
                for d in row["distribution"]
            )
        return _prorated_amount(row["budget_amount"], row["start"], row["end"], start, end)

    def _signed_actual(self, start, end):
        """Base GL query for Income/Expense postings in [start, min(end, today)].

        Excludes cancelled, opening and period-closing entries. Returns
        (query, GLEntry, Account, signed_amount); signed_amount is credit-debit for
        Income and debit-credit for Expense, so both read as positive activity.
        """
        GLEntry = frappe.qb.DocType("GL Entry")
        Account = frappe.qb.DocType("Account")
        signed = (
            Case()
            .when(Account.root_type == "Income", GLEntry.credit - GLEntry.debit)
            .else_(GLEntry.debit - GLEntry.credit)
        )
        query = (
            frappe.qb.from_(GLEntry)
            .join(Account)
            .on(Account.name == GLEntry.account)
            .where(GLEntry.company == self.company)
            .where(GLEntry.posting_date.between(start, min(getdate(end), getdate())))
            .where(GLEntry.is_cancelled == 0)
            .where(Coalesce(GLEntry.is_opening, "No") != "Yes")
            .where(GLEntry.voucher_type != "Period Closing Voucher")
            .where(Account.root_type.isin(["Income", "Expense"]))
        )
        return query, GLEntry, Account, signed

    def _budgeted_actual(self, start, end) -> float:
        """Actual (sign-corrected) on the budgeted account / cost-center sets over start..end."""
        rows = self._fetch_budget_data()
        if not rows:
            return 0.0
        query, GLEntry, _, signed = self._signed_actual(start, end)
        result = (
            query.select(Coalesce(Sum(signed), 0))
            .where(GLEntry.account.isin(list({b["account"] for b in rows})))
            .where(GLEntry.cost_center.isin(list({b["cost_center"] for b in rows})))
            .run()
        )
        return flt(result[0][0]) if result else 0.0

    def _fetch_actual_data(self) -> list[dict[str, Any]]:
        """Fetch sign-corrected actuals per account / cost center for the fiscal year"""
        query, GLEntry, _, signed = self._signed_actual(self.fy_start_date, self.fy_end_date)
        net_amount = Sum(signed)
        rows = (
            query.select(GLEntry.account, GLEntry.cost_center, net_amount.as_("actual_amount"))
            .groupby(GLEntry.account, GLEntry.cost_center)
            .having(net_amount != 0)
            .orderby(Abs(net_amount), order=frappe.qb.desc)
            .run(as_dict=True)
        )
        for r in rows:
            r["actual_amount"] = flt(r["actual_amount"])
        return rows

    def _merge_budget_actual(self, budget_data: list, actual_data: list) -> list[dict[str, Any]]:
        """Merge each budget row with its account / cost-center actual"""
        actual_lookup = {(a["account"], a["cost_center"]): flt(a["actual_amount"]) for a in actual_data}

        merged_data = []
        for b in budget_data:
            budget = self._period_budget(b, self.fy_start_date, self.fy_end_date)
            actual = actual_lookup.get((b["account"], b["cost_center"]), 0.0)
            merged_data.append({
                "account": b["account"],
                "cost_center": b["cost_center"],
                "budget_amount": budget,
                "actual_amount": actual,
                "variance": actual - budget,
                "favorable": _is_favorable(b["root_type"], actual, budget),
                "account_type": b["account_type"],
                "root_type": b["root_type"],
            })
        return merged_data

    def _calculate_variance_trend(self) -> str:
        """Calculate overall variance trend direction (over months that have a budget)"""
        return self._calculate_trend_direction(self._get_monthly_variances())

    def _get_ytd_performance(self) -> dict[str, Any]:
        """Get year-to-date budget performance"""
        try:
            current_date = frappe.utils.today()
            ytd_end = min(frappe.utils.getdate(current_date), self.fy_end_date)

            # Calculate YTD budget and actual
            ytd_budget = self._get_ytd_budget_amount(ytd_end)
            ytd_actual = self._get_ytd_actual_amount(ytd_end)

            ytd_variance = ytd_actual - ytd_budget
            ytd_variance_pct = (ytd_variance / ytd_budget * 100) if ytd_budget != 0 else 0

            # Calculate run rate
            days_elapsed = (ytd_end - self.fy_start_date).days
            days_total = (self.fy_end_date - self.fy_start_date).days
            expected_completion = (days_elapsed / days_total * 100) if days_total > 0 else 0

            actual_completion = (ytd_actual / ytd_budget * 100) if ytd_budget != 0 else 0

            return {
                "ytd_budget": ytd_budget,
                "ytd_actual": ytd_actual,
                "ytd_variance": ytd_variance,
                "ytd_variance_percentage": ytd_variance_pct,
                "expected_completion": expected_completion,
                "actual_completion": actual_completion,
                "run_rate_status": self._assess_run_rate(expected_completion, actual_completion)
            }

        except Exception as e:
            logger.error(f"Error calculating YTD performance: {e}")
            return {}

    def _get_variance_status(self, variance_percentage: float) -> str:
        """Determine variance status based on percentage"""
        abs_variance = abs(variance_percentage)

        if abs_variance <= 5:
            return "excellent"
        elif abs_variance <= 10:
            return "good"
        elif abs_variance <= 15:
            return "acceptable"
        elif abs_variance <= 25:
            return "poor"
        else:
            return "critical"

    def _get_active_departments(self) -> list:
        """Get list of active departments"""
        try:
            return frappe.get_all(
                "Department",
                filters={"disabled": 0},
                fields=["name", "department_name"]
            )
        except Exception as e:
            logger.error(f"Error fetching departments: {e}")
            return []

    def _get_department_budget(self, department: str) -> float:
        """Total expense budget for a department's cost center over the fiscal year"""
        return self._get_department_budget_for_period(department, self.fy_start_date, self.fy_end_date)

    def _get_department_actual(self, department: str) -> float:
        """Total expense actual for a department's cost center over the fiscal year"""
        return self._get_department_actual_for_period(department, self.fy_start_date, self.fy_end_date)

    def _get_department_trend(self, department: str) -> str:
        """Get variance trend for a department"""
        try:
            # Get last 3 months data for trend analysis
            monthly_data = []
            current_date = frappe.utils.getdate(frappe.utils.today())

            for i in range(3):
                month_end = frappe.utils.add_months(current_date, -i)
                month_start = frappe.utils.get_first_day(month_end)

                month_actual = self._get_department_actual_for_period(department, month_start, month_end)
                month_budget = self._get_department_budget_for_period(department, month_start, month_end)

                if month_budget != 0:
                    variance_pct = ((month_actual - month_budget) / month_budget) * 100
                    monthly_data.append(variance_pct)

            if len(monthly_data) >= 2:
                if monthly_data[0] < monthly_data[-1]:  # Getting better (more recent is better)
                    return "improving"
                elif monthly_data[0] > monthly_data[-1]:
                    return "deteriorating"
                else:
                    return "stable"

            return "insufficient_data"

        except Exception as e:
            logger.error(f"Error calculating department trend: {e}")
            return "unknown"

    def _get_department_key_accounts(self, department: str) -> list[dict[str, Any]]:
        """Get key accounts contributing to department variance"""
        try:
            cost_center = frappe.db.get_value("Department", department, "payroll_cost_center")

            if not cost_center:
                return []

            query, GLEntry, Account, signed = self._signed_actual(self.fy_start_date, self.fy_end_date)
            account_data = (
                query.select(
                    GLEntry.account,
                    Sum(signed).as_("actual_amount"),
                    Account.account_type,
                    Account.root_type,
                )
                .where(GLEntry.cost_center == cost_center)
                .groupby(GLEntry.account, Account.account_type, Account.root_type)
                .orderby(Abs(Sum(signed)), order=frappe.qb.desc)
                .limit(5)
                .run(as_dict=True)
            )
            for row in account_data:
                row["actual_amount"] = flt(row["actual_amount"])

            return account_data

        except Exception as e:
            logger.error(f"Error getting department key accounts: {e}")
            return []

    def _get_account_budget(self, account: str) -> float:
        """Get fiscal-year budget amount for specific account"""
        return sum(
            self._period_budget(b, self.fy_start_date, self.fy_end_date)
            for b in self._fetch_budget_data()
            if b["account"] == account
        )

    def _account_actual(self, account: str, start, end) -> float:
        """Sign-corrected actual for one account over start..end"""
        query, GLEntry, _, signed = self._signed_actual(start, end)
        result = query.select(Coalesce(Sum(signed), 0)).where(GLEntry.account == account).run()
        return flt(result[0][0]) if result else 0.0

    def _get_account_actual(self, account: str) -> float:
        """Get actual amount for specific account"""
        return self._account_actual(account, self.fy_start_date, self.fy_end_date)

    def _get_account_monthly_breakdown(self, account: str) -> list[dict[str, Any]]:
        """Get monthly breakdown for account"""
        try:
            monthly_data = []
            current_date = self.fy_start_date
            rows = [b for b in self._fetch_budget_data() if b["account"] == account]

            while current_date <= self.fy_end_date:
                month_end = min(
                    frappe.utils.get_last_day(current_date),
                    self.fy_end_date
                )

                monthly_data.append({
                    "month": current_date.strftime("%Y-%m"),
                    "actual": self._account_actual(account, current_date, month_end),
                    "budget": sum(self._period_budget(b, current_date, month_end) for b in rows),
                })

                current_date = frappe.utils.add_months(current_date, 1)

            return monthly_data

        except Exception as e:
            logger.error(f"Error getting account monthly breakdown: {e}")
            return []

    def _get_variance_impact_level(self, variance_amount: float, budget_amount: float) -> str:
        """Determine impact level of variance"""
        if budget_amount == 0:
            return "low"

        variance_pct = (variance_amount / budget_amount) * 100

        if variance_pct < 5:
            return "low"
        elif variance_pct < 15:
            return "medium"
        elif variance_pct < 30:
            return "high"
        else:
            return "critical"

    def _get_historical_forecasts(self) -> list[dict[str, Any]]:
        """Get historical forecast data for accuracy calculation"""
        try:
            # This would typically come from a custom doctype for forecasts
            # For now, returning empty list as example structure
            return []

        except Exception as e:
            logger.error(f"Error getting historical forecasts: {e}")
            return []

    def _get_monthly_forecast_accuracy(self) -> list[dict[str, Any]]:
        """Get monthly forecast accuracy breakdown"""
        try:
            # Placeholder for monthly forecast accuracy calculation
            return []

        except Exception as e:
            logger.error(f"Error calculating monthly forecast accuracy: {e}")
            return []

    def _calculate_forecast_accuracy_trend(self) -> str:
        """Calculate forecast accuracy trend"""
        try:
            # Placeholder for forecast accuracy trend calculation
            return "stable"

        except Exception as e:
            logger.error(f"Error calculating forecast accuracy trend: {e}")
            return "unknown"

    def _calculate_forecast_bias(self, forecast_data: list) -> dict[str, Any]:
        """Calculate forecast bias metrics"""
        try:
            if not forecast_data:
                return {}

            total_forecast = sum(item.get('forecast_amount', 0) for item in forecast_data)
            total_actual = sum(item.get('actual_amount', 0) for item in forecast_data)

            bias = total_actual - total_forecast
            bias_percentage = (bias / total_forecast * 100) if total_forecast != 0 else 0

            return {
                "bias_amount": bias,
                "bias_percentage": bias_percentage,
                "bias_direction": "over_forecast" if bias < 0 else "under_forecast"
            }

        except Exception as e:
            logger.error(f"Error calculating forecast bias: {e}")
            return {}

    def _get_accuracy_grade(self, accuracy: float) -> str:
        """Get accuracy grade based on percentage"""
        if accuracy >= 90:
            return "A+"
        elif accuracy >= 85:
            return "A"
        elif accuracy >= 80:
            return "B+"
        elif accuracy >= 75:
            return "B"
        elif accuracy >= 70:
            return "C+"
        elif accuracy >= 65:
            return "C"
        else:
            return "D"

    def _get_forecast_improvement_tips(self, accuracy: float) -> list[str]:
        """Get forecast improvement recommendations"""
        tips = []

        if accuracy < 70:
            tips.extend([
                "Review historical data patterns more thoroughly",
                "Implement scenario-based forecasting",
                "Increase forecast review frequency",
                "Consider external market factors"
            ])
        elif accuracy < 80:
            tips.extend([
                "Fine-tune forecasting models",
                "Incorporate leading indicators",
                "Improve data quality processes"
            ])
        elif accuracy < 90:
            tips.append("Consider advanced analytics and machine learning")

        return tips

    def _get_monthly_variances(self) -> list[dict[str, Any]]:
        """Get monthly budget variances"""
        try:
            monthly_data = []
            current_date = self.fy_start_date

            while current_date <= min(frappe.utils.getdate(frappe.utils.today()), self.fy_end_date):
                month_start = current_date
                month_end = min(
                    frappe.utils.get_last_day(current_date),
                    self.fy_end_date,
                    frappe.utils.getdate(frappe.utils.today())
                )

                # Get monthly budget (proportional)
                monthly_budget = self._get_monthly_budget_amount(month_start, month_end)

                # Get monthly actual
                monthly_actual = self._get_monthly_actual_amount(month_start, month_end)

                variance = monthly_actual - monthly_budget
                # `monthly_budget == 0` means no Budget doctype covers this
                # month, not that actual spend landed exactly on a real
                # plan. Masking that as `variance_percentage: 0` reads as
                # "on budget"; `has_budget` lets consumers (variance
                # control, in particular) tell the two apart instead of
                # averaging in a fabricated zero.
                has_budget = monthly_budget != 0
                variance_pct = (variance / monthly_budget * 100) if has_budget else 0

                monthly_data.append({
                    "month": month_start.strftime("%Y-%m"),
                    "budget": monthly_budget,
                    "actual": monthly_actual,
                    "variance": variance,
                    "variance_percentage": variance_pct,
                    "has_budget": has_budget,
                })

                current_date = frappe.utils.add_months(current_date, 1)

            return monthly_data

        except Exception as e:
            logger.error(f"Error getting monthly variances: {e}")
            return []

    def _calculate_trend_direction(self, monthly_data: list) -> str:
        """Calculate overall trend direction from monthly data"""
        try:
            monthly_data = [m for m in monthly_data if m.get("has_budget")]
            if len(monthly_data) < 3:
                return "insufficient_data"

            variances = [item['variance_percentage'] for item in monthly_data[-3:]]

            if len(variances) >= 2:
                avg_early = sum(variances[:len(variances)//2]) / (len(variances)//2)
                avg_late = sum(variances[len(variances)//2:]) / (len(variances) - len(variances)//2)

                if avg_late > avg_early:
                    return "deteriorating"
                elif avg_late < avg_early:
                    return "improving"
                else:
                    return "stable"

            return "stable"

        except Exception as e:
            logger.error(f"Error calculating trend direction: {e}")
            return "unknown"

    def _calculate_variance_volatility(self, monthly_data: list) -> float:
        """Calculate variance volatility (standard deviation)"""
        try:
            if len(monthly_data) < 2:
                return 0

            variances = [item['variance_percentage'] for item in monthly_data]
            mean_variance = sum(variances) / len(variances)

            variance = sum((x - mean_variance) ** 2 for x in variances) / len(variances)
            return variance ** 0.5

        except Exception as e:
            logger.error(f"Error calculating variance volatility: {e}")
            return 0

    def _detect_variance_seasonality(self, monthly_data: list) -> dict[str, Any]:
        """Detect seasonal patterns in variance"""
        try:
            if len(monthly_data) < 12:
                return {"seasonal": False, "pattern": "insufficient_data"}

            # Group by month number (1-12)
            monthly_patterns = {}
            for item in monthly_data:
                month_num = int(item['month'].split('-')[1])
                if month_num not in monthly_patterns:
                    monthly_patterns[month_num] = []
                monthly_patterns[month_num].append(item['variance_percentage'])

            # Calculate average variance by month
            monthly_averages = {}
            for month, variances in monthly_patterns.items():
                monthly_averages[month] = sum(variances) / len(variances)

            # Check for significant seasonal variation
            if len(monthly_averages) >= 12:
                values = list(monthly_averages.values())
                avg_variance = sum(values) / len(values)
                variance_range = max(values) - min(values)

                is_seasonal = variance_range > (avg_variance * 0.5)  # 50% of average

                return {
                    "seasonal": is_seasonal,
                    "pattern": "significant" if is_seasonal else "minimal",
                    "peak_month": max(monthly_averages, key=monthly_averages.get),
                    "low_month": min(monthly_averages, key=monthly_averages.get),
                    "variance_range": variance_range
                }

            return {"seasonal": False, "pattern": "insufficient_data"}

        except Exception as e:
            logger.error(f"Error detecting seasonality: {e}")
            return {"seasonal": False, "pattern": "error"}

    def _get_rolling_average(self, monthly_data: list, period: int) -> list[dict[str, Any]]:
        """Calculate rolling average for variance data"""
        try:
            if len(monthly_data) < period:
                return []

            rolling_data = []
            for i in range(period - 1, len(monthly_data)):
                window_data = monthly_data[i - period + 1:i + 1]
                avg_variance = sum(item['variance_percentage'] for item in window_data) / period

                rolling_data.append({
                    "month": monthly_data[i]['month'],
                    "rolling_average": avg_variance
                })

            return rolling_data

        except Exception as e:
            logger.error(f"Error calculating rolling average: {e}")
            return []

    def _predict_next_period_variance(self) -> dict[str, Any]:
        """Predict next period variance using simple linear regression"""
        try:
            monthly_data = self._get_monthly_variances()

            if len(monthly_data) < 3:
                return {"prediction": None, "confidence": "low"}

            # Simple linear trend calculation
            variances = [item['variance_percentage'] for item in monthly_data[-6:]]  # Last 6 months

            if len(variances) < 2:
                return {"prediction": None, "confidence": "low"}

            # Calculate trend
            x_values = list(range(len(variances)))
            n = len(variances)

            sum_x = sum(x_values)
            sum_y = sum(variances)
            sum_xy = sum(x * y for x, y in zip(x_values, variances))
            sum_x2 = sum(x * x for x in x_values)

            # Linear regression slope
            if n * sum_x2 - sum_x * sum_x != 0:
                slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
                intercept = (sum_y - slope * sum_x) / n

                # Predict next period
                next_x = len(variances)
                predicted_variance = slope * next_x + intercept

                # Calculate confidence based on trend consistency
                recent_trend = variances[-1] - variances[0]
                predicted_trend = predicted_variance - variances[-1]

                confidence = "high" if abs(recent_trend - predicted_trend) < 5 else "medium"

                return {
                    "prediction": predicted_variance,
                    "confidence": confidence,
                    "trend": "improving" if slope < 0 else "deteriorating" if slope > 0 else "stable"
                }

            return {"prediction": variances[-1], "confidence": "low"}

        except Exception as e:
            logger.error(f"Error predicting variance: {e}")
            return {"prediction": None, "confidence": "low"}

    def _get_cash_flow_variance(self) -> dict[str, Any]:
        """Get cash flow variance analysis"""
        try:
            # Get cash and bank accounts
            cash_accounts = frappe.get_all(
                "Account",
                filters={
                    "company": self.company,
                    "account_type": ["in", ["Cash", "Bank"]],
                    "disabled": 0
                },
                fields=["name"]
            )

            if not cash_accounts:
                return {}

            account_names = [acc.name for acc in cash_accounts]

            # Calculate cash flow for the period
            GLEntry = frappe.qb.DocType("GL Entry")
            result = (
                frappe.qb.from_(GLEntry)
                .select(Coalesce(Sum(GLEntry.debit - GLEntry.credit), 0).as_("net_cash_flow"))
                .where(GLEntry.company == self.company)
                .where(GLEntry.posting_date.between(self.fy_start_date, min(self.fy_end_date, getdate())))
                .where(GLEntry.account.isin(account_names))
                .where(GLEntry.is_cancelled == 0)
                .run()
            )

            actual_cash_flow = flt(result[0][0]) if result else 0.0

            # For this example, assume budgeted cash flow is 80% of revenue budget
            # In practice, this should come from a proper cash flow budget
            revenue_budget = self._get_revenue_budget()
            budgeted_cash_flow = revenue_budget * 0.8  # Simplified assumption

            variance = actual_cash_flow - budgeted_cash_flow
            variance_pct = (variance / budgeted_cash_flow * 100) if budgeted_cash_flow != 0 else 0

            return {
                "budgeted_cash_flow": budgeted_cash_flow,
                "actual_cash_flow": actual_cash_flow,
                "variance": variance,
                "variance_percentage": variance_pct,
                "status": self._get_variance_status(variance_pct)
            }

        except Exception as e:
            logger.error(f"Error calculating cash flow variance: {e}")
            return {}

    # Additional helper methods continue...

    def _calculate_budget_accuracy(self) -> dict[str, Any]:
        """Calculate overall budget accuracy metrics"""
        try:
            variance_summary = self._get_variance_summary()
            if not variance_summary:
                return {}

            variance_pct = abs(variance_summary.get('variance_percentage', 0))
            accuracy = max(0, 100 - variance_pct)

            return {
                "accuracy_percentage": accuracy,
                "grade": self._get_accuracy_grade(accuracy),
                "benchmark": 85,  # Industry benchmark
                "performance": "above" if accuracy >= 85 else "below"
            }

        except Exception as e:
            logger.error(f"Error calculating budget accuracy: {e}")
            return {}

    def _calculate_budget_efficiency(self) -> dict[str, Any]:
        """Calculate budget efficiency metrics"""
        try:
            performance_metrics = self._get_performance_metrics()
            budget_metrics = self._get_budget_allocation_metrics()
            resource_utilization = self._calculate_resource_utilization()
            cost_effectiveness = self._calculate_cost_effectiveness()

            # Weighted blend: how well spend tracked plan (cost efficiency),
            # how tightly the budget was allocated across accounts, and the
            # utilization/effectiveness of what was actually spent.
            efficiency_score = round(
                performance_metrics.get("cost_efficiency", 0) * 0.35
                + budget_metrics.get("allocation_efficiency", 0) * 0.25
                + resource_utilization * 0.2
                + cost_effectiveness * 0.2,
                2,
            )

            return {
                "efficiency_score": efficiency_score,
                "resource_utilization": resource_utilization,
                "cost_effectiveness": cost_effectiveness
            }

        except Exception as e:
            logger.error(f"Error calculating budget efficiency: {e}")
            return {}

    def _calculate_variance_control(self) -> dict[str, Any]:
        """Calculate variance control effectiveness, over months with a real budget.

        Months where no Budget doctype covers the period (`has_budget: False`,
        see `_get_monthly_variances`) carry a fabricated `variance_percentage:
        0` -- averaging those in reads as "on budget" when the truth is
        "nothing to compare against". On a site with zero Budget records this
        previously scored every month 0% variance and reported
        "Excellent (100/100)" control while actual spend ran millions
        unbudgeted per month.
        """
        try:
            monthly_variances = self._get_monthly_variances()
            budgeted_months = [m for m in monthly_variances if m.get("has_budget")]

            if not budgeted_months:
                return {
                    "status": "not_implemented",
                    "message": "No Budget records cover this period; variance control cannot be assessed.",
                }

            # Calculate control metrics
            avg_variance = sum(abs(item['variance_percentage']) for item in budgeted_months) / len(budgeted_months)
            variance_volatility = self._calculate_variance_volatility(budgeted_months)

            control_score = max(0, 100 - (avg_variance + variance_volatility) / 2)

            return {
                "control_score": control_score,
                "average_variance": avg_variance,
                "volatility": variance_volatility,
                "control_level": "excellent" if control_score >= 90 else "good" if control_score >= 75 else "needs_improvement",
                "months_assessed": len(budgeted_months),
                "months_without_budget": len(monthly_variances) - len(budgeted_months),
            }

        except Exception as e:
            logger.error(f"Error calculating variance control: {e}")
            return {}

    def _assess_budget_planning_quality(self) -> dict[str, Any]:
        """Assess overall budget planning quality"""
        try:
            # Assess various quality factors
            accuracy = self._calculate_budget_accuracy()
            completeness = self._assess_budget_completeness()
            timeliness = self._assess_budget_timeliness()
            stakeholder_involvement = self._assess_stakeholder_involvement()

            # Calculate overall quality score
            quality_factors = [
                accuracy.get('accuracy_percentage', 0) * 0.4,
                completeness.get('completeness_score', 0) * 0.3,
                timeliness.get('timeliness_score', 0) * 0.2,
                stakeholder_involvement.get('involvement_score', 0) * 0.1
            ]

            overall_quality = sum(quality_factors)

            return {
                "overall_quality": overall_quality,
                "accuracy": accuracy,
                "completeness": completeness,
                "timeliness": timeliness,
                "stakeholder_involvement": stakeholder_involvement,
                "grade": self._get_quality_grade(overall_quality)
            }

        except Exception as e:
            logger.error(f"Error assessing planning quality: {e}")
            return {}

    def _get_quality_grade(self, score: float) -> str:
        """Get quality grade based on score"""
        if score >= 90:
            return "Excellent"
        elif score >= 80:
            return "Good"
        elif score >= 70:
            return "Satisfactory"
        elif score >= 60:
            return "Needs Improvement"
        else:
            return "Poor"

    def _calculate_overall_budget_score(self, accuracy: dict, efficiency: dict, control: dict, quality: dict) -> float:
        """Calculate overall budget management score"""
        try:
            accuracy_score = accuracy.get('accuracy_percentage', 0) * 0.3
            efficiency_score = efficiency.get('efficiency_score', 0) * 0.25
            control_score = control.get('control_score', 0) * 0.25
            quality_score = quality.get('overall_quality', 0) * 0.2

            return accuracy_score + efficiency_score + control_score + quality_score

        except Exception as e:
            logger.error(f"Error calculating overall score: {e}")
            return 0

    # Additional utility methods

    def _get_revenue_budget(self) -> float:
        """Get total revenue budget for the fiscal year"""
        return sum(
            self._period_budget(b, self.fy_start_date, self.fy_end_date)
            for b in self._fetch_budget_data()
            if b["root_type"] == "Income"
        )

    def _needs_process_improvement(self) -> bool:
        """Determine if process improvement recommendations are needed"""
        try:
            variance_summary = self._get_variance_summary()

            if not variance_summary:
                return True

            # Check multiple criteria
            high_variance = abs(variance_summary.get('variance_percentage', 0)) > 20
            poor_trend = variance_summary.get('variance_trend') == 'deteriorating'

            return high_variance or poor_trend

        except Exception as e:
            logger.error(f"Error assessing process improvement needs: {e}")
            return True

    # Final utility and validation methods

    def _get_ytd_budget_amount(self, end_date) -> float:
        """Get year-to-date budget amount (follows each Budget's distribution)"""
        return sum(self._period_budget(b, self.fy_start_date, end_date) for b in self._fetch_budget_data())

    def _get_ytd_actual_amount(self, end_date) -> float:
        """Get year-to-date actual on the budgeted accounts"""
        return self._budgeted_actual(self.fy_start_date, end_date)

    def _assess_run_rate(self, expected: float, actual: float) -> str:
        """Assess budget run rate status"""
        variance = abs(actual - expected)

        if variance <= 5:
            return "on_track"
        elif variance <= 15:
            return "slight_deviation"
        elif variance <= 30:
            return "significant_deviation"
        else:
            return "major_deviation"

    def _get_department_actual_for_period(self, department: str, start_date, end_date) -> float:
        """Expense actual for a department's cost center over a period"""
        cost_center = frappe.db.get_value("Department", department, "payroll_cost_center")
        if not cost_center:
            return 0.0

        query, GLEntry, Account, signed = self._signed_actual(start_date, end_date)
        result = (
            query.select(Coalesce(Sum(signed), 0))
            .where(GLEntry.cost_center == cost_center)
            .where(Account.root_type == "Expense")
            .run()
        )
        return flt(result[0][0]) if result else 0.0

    def _get_department_budget_for_period(self, department: str, start_date, end_date) -> float:
        """Expense budget for a department's cost center over a period"""
        cost_center = frappe.db.get_value("Department", department, "payroll_cost_center")
        if not cost_center:
            return 0.0

        return sum(
            self._period_budget(b, start_date, end_date)
            for b in self._fetch_budget_data()
            if b["cost_center"] == cost_center and b["root_type"] == "Expense"
        )

    def _get_monthly_budget_amount(self, start_date, end_date) -> float:
        """Budget falling in a month (follows each Budget's distribution)"""
        return sum(self._period_budget(b, start_date, end_date) for b in self._fetch_budget_data())

    def _get_monthly_actual_amount(self, start_date, end_date) -> float:
        """Actual on the budgeted accounts for a month"""
        return self._budgeted_actual(start_date, end_date)

    def _get_performance_metrics(self) -> dict[str, Any]:
        """Get general performance metrics, derived from the variance summary"""
        try:
            summary = self._get_variance_summary()
            if not summary:
                return {"cost_efficiency": 0, "profit_margin": 0}

            total_variance_abs = abs(summary.get("total_variance", 0))
            favorable = summary.get("favorable_variance", 0)
            # Share of the total budget-vs-actual variance that was favorable.
            cost_efficiency = (
                round(favorable / total_variance_abs * 100, 2) if total_variance_abs > 0 else 100.0
            )
            # How far actual spend came in under the budget ceiling.
            profit_margin = round(100 - summary.get("budget_utilization", 0), 2)

            return {
                "cost_efficiency": cost_efficiency,
                "profit_margin": profit_margin
            }

        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {}

    def _get_budget_allocation_metrics(self) -> dict[str, Any]:
        """Get budget allocation metrics, derived from account-wise variance"""
        try:
            accounts = self._get_account_variance()
            if not accounts:
                return {"allocation_efficiency": 0, "resource_distribution": {}}

            # Tighter budgets (lower average absolute variance) score higher.
            avg_abs_variance = sum(abs(a.get("variance_percentage", 0)) for a in accounts) / len(accounts)
            allocation_efficiency = round(max(0.0, 100 - avg_abs_variance), 2)

            # Actual spend share by root type (Asset/Liability/Income/Expense/Equity).
            distribution: dict[str, float] = {}
            for acc in accounts:
                root_type = acc.get("root_type") or "Unknown"
                distribution[root_type] = distribution.get(root_type, 0) + abs(acc.get("actual", 0))
            total_actual = sum(distribution.values())
            if total_actual > 0:
                distribution = {k: round(v / total_actual * 100, 2) for k, v in distribution.items()}

            return {
                "allocation_efficiency": allocation_efficiency,
                "resource_distribution": distribution
            }

        except Exception as e:
            logger.error(f"Error getting allocation metrics: {e}")
            return {}

    def _calculate_resource_utilization(self) -> float:
        """Calculate resource utilization efficiency: share of allocated budget actually spent"""
        try:
            summary = self._get_variance_summary()
            if not summary:
                return 0
            return round(summary.get("budget_utilization", 0), 2)

        except Exception as e:
            logger.error(f"Error calculating resource utilization: {e}")
            return 0

    def _calculate_cost_effectiveness(self) -> float:
        """Calculate cost effectiveness: share of budget where spend was favorable to plan"""
        try:
            summary = self._get_variance_summary()
            total_budget = summary.get("total_budget", 0) if summary else 0
            if not summary or total_budget == 0:
                return 0
            favorable = summary.get("favorable_variance", 0)
            return round(min(100.0, favorable / total_budget * 100), 2)

        except Exception as e:
            logger.error(f"Error calculating cost effectiveness: {e}")
            return 0

    def _assess_budget_completeness(self) -> dict[str, Any]:
        """Assess budget completeness"""
        try:
            # Check if all major accounts have budgets
            total_accounts = frappe.db.count("Account", {
                "company": self.company,
                "disabled": 0,
                "is_group": 0,
                "root_type": ["in", ["Income", "Expense"]]
            })

            budgeted_count = len({b["account"] for b in self._fetch_budget_data()})
            completeness = (budgeted_count / total_accounts * 100) if total_accounts > 0 else 0

            return {
                "completeness_score": completeness,
                "total_accounts": total_accounts,
                "budgeted_accounts": budgeted_count
            }

        except Exception as e:
            logger.error(f"Error assessing budget completeness: {e}")
            return {"completeness_score": 0}

    def _assess_budget_timeliness(self) -> dict[str, Any]:
        """Assess budget preparation timeliness"""
        try:
            # Check when budgets were created relative to fiscal year start
            budget_rows = self._fetch_budget_data()

            if budget_rows:
                creation_date = min(b["creation"] for b in budget_rows)
                days_before_fy = (self.fy_start_date - creation_date.date()).days

                if days_before_fy >= 30:
                    timeliness_score = 100
                elif days_before_fy >= 0:
                    timeliness_score = 80
                else:
                    timeliness_score = max(0, 60 + days_before_fy)  # Penalty for late budgets
            else:
                timeliness_score = 0

            return {
                "timeliness_score": timeliness_score,
                "assessment": "excellent" if timeliness_score >= 90 else "good" if timeliness_score >= 70 else "needs_improvement"
            }

        except Exception as e:
            logger.error(f"Error assessing budget timeliness: {e}")
            return {"timeliness_score": 50}

    def _assess_stakeholder_involvement(self) -> dict[str, Any]:
        """Assess stakeholder involvement in budgeting"""
        try:
            # Check number of people involved in budget creation/approval
            budget_count = len({b["budget_name"] for b in self._fetch_budget_data()})

            # Simplified assessment
            involvement_score = min(100, budget_count * 10)  # More budgets = more involvement

            return {
                "involvement_score": involvement_score,
                "budget_documents": budget_count
            }

        except Exception as e:
            logger.error(f"Error assessing stakeholder involvement: {e}")
            return {"involvement_score": 50}

    def _get_industry_benchmarks(self) -> dict[str, Any]:
        """Get industry budget management benchmarks"""
        return {
            "budget_accuracy": 85,
            "variance_threshold": 10,
            "forecast_accuracy": 80,
            "budget_cycle_time": 45,  # days
            "stakeholder_satisfaction": 75
        }

    def _identify_improvement_areas(self, overall_score: float) -> list[str]:
        """Identify key areas for budget management improvement"""
        improvement_areas = []

        if overall_score < 70:
            improvement_areas.extend([
                "Overall budget management process needs significant enhancement",
                "Implement comprehensive budget training program",
                "Review and redesign budget planning methodology"
            ])
        elif overall_score < 80:
            improvement_areas.extend([
                "Budget accuracy needs improvement",
                "Enhance variance monitoring and control",
                "Implement more frequent budget reviews"
            ])
        elif overall_score < 90:
            improvement_areas.append("Fine-tune budget forecasting models")

        return improvement_areas

    # Export and reporting methods

    def export_variance_report(self, format="json") -> dict[str, Any]:
        """Export comprehensive variance report"""
        try:
            report_data = self.get_budget_variance_overview()

            if format == "json":
                return report_data
            elif format == "summary":
                return self._create_executive_summary(report_data)
            else:
                return report_data

        except Exception as e:
            logger.error(f"Error exporting variance report: {e}")
            return {}

    def _create_executive_summary(self, data: dict) -> dict[str, Any]:
        """Create executive summary of variance analysis"""
        try:
            summary = data.get('summary', {})
            alerts = data.get('alerts', [])

            return {
                "executive_summary": {
                    "overall_variance": f"{summary.get('variance_percentage', 0):.1f}%",
                    "budget_status": summary.get('status', 'unknown'),
                    "key_alerts": len([a for a in alerts if a.get('severity') == 'high']),
                    "top_recommendations": [r['title'] for r in data.get('recommendations', [])[:3]],
                    "budget_utilization": f"{summary.get('budget_utilization', 0):.1f}%",
                    "forecast_accuracy": f"{data.get('forecast_accuracy', {}).get('overall_accuracy', 0):.1f}%"
                },
                "generated_at": frappe.utils.now(),
                "period": data.get('period_info', {})
            }

        except Exception as e:
            logger.error(f"Error creating executive summary: {e}")
            return {}
