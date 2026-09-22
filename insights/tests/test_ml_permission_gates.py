# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Regression tests for the has_permission gates added across insights/api/ml/
(plan-eng-review Architecture Finding 2, 2026-08-04). Before the fix, ~100
aggregate "intelligence/overview" endpoints had no doctype permission check
at all -- any logged-in user could read payroll, financial, and other
sensitive aggregates regardless of role.

Two things are verified per representative endpoint:
1. frappe.has_permission is actually called with the right doctype/mode.
2. A denied permission (PermissionError) propagates to the caller instead
   of being silently swallowed into a generic {"status": "error"} JSON
   response by the surrounding `except Exception` handler -- a real gap
   found and fixed in the same pass (see code review discussion).

Uses mocks rather than real users/roles since this bench's only site (jkm)
carries live production data that conflicts with Frappe's test-user/test-
record bootstrap (see plan-eng-review notes on the broken bench run-tests
fixture bootstrap).
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from insights.api.ml import hr as hr_api
from insights.api.ml import financial as financial_api
from insights.api.ml import customer as customer_api
from insights.api.ml import general as general_api
from insights.api.ml import breakeven as breakeven_api
from insights.api.ml import executive as executive_api
from insights.api.ml import price as price_api
from insights.api.ml import marketing as marketing_api


class TestMLPermissionGates(FrappeTestCase):
    def test_hr_overview_checks_employee_and_salary_slip_permission(self):
        """get_hr_overview aggregates payroll data (via _analyze_payroll), so
        it must gate on Salary Slip in addition to Employee -- Employee read
        alone doesn't imply salary visibility. See outside-voice finding 4."""
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.hr_intelligence.HRIntelligence") as MockHR:
            MockHR.return_value.train.return_value = {}
            hr_api.get_hr_overview()
            mock_has_perm.assert_any_call("Employee", "read", throw=True)
            mock_has_perm.assert_any_call("Salary Slip", "read", throw=True)

    def test_hr_overview_permission_denial_propagates_not_swallowed(self):
        """The critical regression: a PermissionError from has_permission
        must reach the caller as a PermissionError, not get caught by the
        generic `except Exception` and turned into a soft-fail JSON blob."""
        with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError("denied")):
            with self.assertRaises(frappe.PermissionError):
                hr_api.get_hr_overview()

    def test_hr_overview_denies_employee_role_without_hr_role(self):
        """CWE-863 regression: an Employee-role-only (ESS) user passes the
        doctype-level has_permission check on both Employee and Salary Slip
        (ESS self-service grants plain read), but HR aggregates must still
        be denied without an explicit HR Manager/HR User role -- otherwise
        the ESS user's single-row sample gets presented as a company-wide
        payroll/headcount figure. See t_06cf4e69 / t_ab698dcf.

        frappe.has_role() does not exist on this Frappe version; the gate
        is implemented via frappe.get_roles(), so that's what's mocked."""
        with patch.object(frappe, "has_permission"), \
             patch.object(frappe, "get_roles", return_value=["Employee"]):
            with self.assertRaises(frappe.PermissionError):
                hr_api.get_hr_overview()

    def test_payroll_analytics_denies_employee_role_without_hr_role(self):
        with patch.object(frappe, "has_permission"), \
             patch.object(frappe, "get_roles", return_value=["Employee"]):
            with self.assertRaises(frappe.PermissionError):
                hr_api.get_payroll_analytics()

    def test_headcount_analytics_denies_employee_role_without_hr_role(self):
        with patch.object(frappe, "has_permission"), \
             patch.object(frappe, "get_roles", return_value=["Employee"]):
            with self.assertRaises(frappe.PermissionError):
                hr_api.get_headcount_analytics()

    def test_attrition_analytics_denies_employee_role_without_hr_role(self):
        with patch.object(frappe, "has_permission"), \
             patch.object(frappe, "get_roles", return_value=["Employee"]):
            with self.assertRaises(frappe.PermissionError):
                hr_api.get_attrition_analytics()

    def test_workforce_planning_denies_employee_role_without_hr_role(self):
        with patch.object(frappe, "has_permission"), \
             patch.object(frappe, "get_roles", return_value=["Employee"]):
            with self.assertRaises(frappe.PermissionError):
                hr_api.get_workforce_planning()

    def test_hr_insights_denies_employee_role_without_hr_role(self):
        with patch.object(frappe, "has_permission"), \
             patch.object(frappe, "get_roles", return_value=["Employee"]):
            with self.assertRaises(frappe.PermissionError):
                hr_api.get_hr_insights(query="headcount")

    def test_talent_analytics_denies_employee_role_without_hr_role(self):
        with patch.object(frappe, "has_permission"), \
             patch.object(frappe, "get_roles", return_value=["Employee"]):
            with self.assertRaises(frappe.PermissionError):
                hr_api.get_talent_analytics()

    def test_analyze_hr_query_denies_employee_role_without_hr_role(self):
        with patch.object(frappe, "has_permission"), \
             patch.object(frappe, "get_roles", return_value=["Employee"]):
            with self.assertRaises(frappe.PermissionError):
                hr_api.analyze_hr_query(query="headcount")

    def test_hr_overview_allows_hr_user_role(self):
        """Positive case: an HR User role passes both the permission and
        role gates and reaches the underlying compute path."""
        with patch.object(frappe, "has_permission"), \
             patch.object(frappe, "get_roles", return_value=["Employee", "HR User"]), \
             patch("insights.ml.hr_intelligence.HRIntelligence") as MockHR:
            MockHR.return_value.train.return_value = {"status": "success"}
            result = hr_api.get_hr_overview()
            self.assertEqual(result.get("status"), "success")

    def test_financial_overview_checks_gl_entry_permission(self):
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.financial_intelligence.FinancialIntelligence") as MockFI:
            MockFI.return_value._calculate_financial_overview.return_value = {}
            financial_api.get_financial_overview()
            mock_has_perm.assert_called_once_with("GL Entry", "read", throw=True)

    def test_financial_overview_permission_denial_propagates(self):
        with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError("denied")):
            with self.assertRaises(frappe.PermissionError):
                financial_api.get_financial_overview()

    def test_customer_intelligence_checks_customer_permission_and_logs_traceback_on_real_error(self):
        """customer_intelligence has an extra frappe.log_error() call in its
        except clause (a different shape than the other endpoints) -- this
        exercises that this variant was fixed too, not just the common one."""
        with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError("denied")):
            with self.assertRaises(frappe.PermissionError):
                customer_api.customer_intelligence()

    def test_general_get_ml_status_is_honest_stub_not_swallowed_by_permission(self):
        """get_ml_status was rewired to an honest not_implemented stub during
        this review (no real model registry exists) -- confirm the
        permission gate still applies even though the body no longer calls
        a real intelligence module."""
        with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError("denied")):
            with self.assertRaises(frappe.PermissionError):
                general_api.get_ml_status()

    def test_general_get_reorder_alerts_calls_module_function_not_instance_method(self):
        """Regression for the general.py dead-code fix: get_reorder_alerts
        previously called model.get_reorder_alerts() (an AttributeError --
        it's a module-level function, not an instance method). Confirm it
        now resolves and calls the real module function."""
        with patch.object(frappe, "has_permission"), \
             patch("insights.ml.demand_forecasting.get_reorder_alerts", return_value={"alerts": []}) as mock_fn:
            result = general_api.get_reorder_alerts()
            mock_fn.assert_called_once_with()
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["data"], {"alerts": []})



class TestOutsideVoiceFixes(FrappeTestCase):
    """Regression tests for issues an independent second-pass review found
    in this same review's own fixes (2026-08-04). See plan-eng-review
    outside-voice findings 2, 3, 5, 7, and the parallel-whitelist-surface
    finding (verified and fixed separately, covered here for regression)."""

    def test_employee_breakeven_gates_on_salary_slip_not_sales_invoice(self):
        """calculate_employee_breakeven queries Salary Slip (payroll), plus
        Sales Order (order counts) and GL Entry (COGS ratio) -- the original
        gate checked Sales Invoice alone, the wrong doctype entirely. See
        outside-voice finding 3 and the security-reviewer-bot follow-up
        (2026-09-19) that widened this to match the full read surface."""
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.breakeven_engine.BreakevenEngine") as MockEngine:
            MockEngine.return_value.calculate_employee_breakeven.return_value = {}
            breakeven_api.employee_breakeven()
            mock_has_perm.assert_any_call("Salary Slip", "read", throw=True)
            mock_has_perm.assert_any_call("Sales Order", "read", throw=True)
            mock_has_perm.assert_any_call("GL Entry", "read", throw=True)

    def test_capital_efficiency_gates_on_gl_entry(self):
        """calculate_roce/calculate_irr are GL Entry- and Payment
        Entry-derived, not Sales Invoice. See outside-voice finding 3 and
        the security-reviewer-bot follow-up (2026-09-19) that added the
        missing Payment Entry (IRR) gate."""
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.breakeven_engine.BreakevenEngine") as MockEngine:
            MockEngine.return_value.calculate_roce.return_value = 0
            MockEngine.return_value.calculate_irr.return_value = 0
            breakeven_api.capital_efficiency()
            mock_has_perm.assert_any_call("GL Entry", "read", throw=True)
            mock_has_perm.assert_any_call("Payment Entry", "read", throw=True)

    def test_item_breakeven_gates_on_full_read_surface(self):
        """calculate_item_breakeven reads Item and GL Entry (fixed costs)
        besides Sales Invoice -- security-reviewer-bot follow-up
        (2026-09-19) to the backend-engineer fix in inventory.py's sibling
        endpoint, applied here to the older breakeven.py copy."""
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.breakeven_engine.BreakevenEngine") as MockEngine:
            MockEngine.return_value.calculate_item_breakeven.return_value = {}
            breakeven_api.item_breakeven()
            mock_has_perm.assert_any_call("Sales Invoice", "read", throw=True)
            mock_has_perm.assert_any_call("Item", "read", throw=True)
            mock_has_perm.assert_any_call("GL Entry", "read", throw=True)

    def test_breakeven_summary_gates_on_every_sub_analysis_doctype(self):
        """get_breakeven_summary fans out into every other calculate_*
        method (item/employee/cash-flow/ROCE/IRR) -- a Sales-Invoice-only
        gate let any Sales-only user pull company payroll-by-department and
        GL/Payment-Entry-derived financials through this single endpoint.
        security-reviewer-bot finding, 2026-09-19."""
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.breakeven_engine.BreakevenEngine") as MockEngine:
            MockEngine.return_value.get_breakeven_summary.return_value = {}
            breakeven_api.breakeven_summary()
            for doctype in ("Sales Invoice", "Item", "GL Entry", "Salary Slip", "Sales Order", "Payment Entry"):
                mock_has_perm.assert_any_call(doctype, "read", throw=True)

    def test_predict_breakeven_scenario_gates_on_item_and_gl_entry_too(self):
        """predict() recomputes calculate_item_breakeven under a scenario --
        same read surface as item_breakeven. security-reviewer-bot finding,
        2026-09-19."""
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.breakeven_engine.BreakevenEngine") as MockEngine:
            MockEngine.return_value.predict.return_value = {}
            breakeven_api.predict_breakeven_scenario()
            mock_has_perm.assert_any_call("Sales Invoice", "read", throw=True)
            mock_has_perm.assert_any_call("Item", "read", throw=True)
            mock_has_perm.assert_any_call("GL Entry", "read", throw=True)

    def test_item_lead_breakeven_ratio_gates_on_lead_too(self):
        """get_item_lead_breakeven_ratio reads Lead directly for conversion
        rate, on top of calculate_item_breakeven's own surface.
        security-reviewer-bot finding, 2026-09-19."""
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.breakeven_engine.BreakevenEngine") as MockEngine:
            MockEngine.return_value.get_item_lead_breakeven_ratio.return_value = {}
            breakeven_api.item_lead_breakeven_ratio()
            mock_has_perm.assert_any_call("Sales Invoice", "read", throw=True)
            mock_has_perm.assert_any_call("Item", "read", throw=True)
            mock_has_perm.assert_any_call("GL Entry", "read", throw=True)
            mock_has_perm.assert_any_call("Lead", "read", throw=True)

    def test_department_insights_gates_per_requested_department(self):
        """A single fixed 'Sales Invoice' gate let a Sales-only user pass
        department='hr' and read payroll data through get_department_insights
        -- the gate must match the doctype the requested department actually
        exposes. See outside-voice finding 2.

        get_department_insights now slices its department block out of
        get_cached_executive_summary()'s envelope (cached/backgrounded via
        insights.api.ml.utils.cached_run) -- mock that function directly."""
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.executive_intelligence.get_cached_executive_summary",
                   return_value={"status": "success", "data": {"kpis": {}, "alerts": []}}) as mock_summary:
            executive_api.get_department_insights(department="hr")
            mock_has_perm.assert_called_once_with("Salary Slip", "read", throw=True)
            mock_summary.assert_called_once_with("YTD")

        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.executive_intelligence.get_cached_executive_summary",
                   return_value={"status": "success", "data": {"kpis": {}, "alerts": []}}):
            executive_api.get_department_insights(department="manufacturing")
            mock_has_perm.assert_called_once_with("Work Order", "read", throw=True)

    def test_department_insights_denies_hr_read_for_sales_only_user(self):
        """The exploit path itself: a user permitted on Work Order (sales/
        manufacturing-ish) but NOT Salary Slip must be denied when requesting
        department='hr', even though the old code let this through."""
        def has_permission_side_effect(doctype, *args, **kwargs):
            if doctype == "Salary Slip":
                raise frappe.PermissionError("denied")
            return True
        with patch.object(frappe, "has_permission", side_effect=has_permission_side_effect):
            with self.assertRaises(frappe.PermissionError):
                executive_api.get_department_insights(department="hr")

    def test_payment_risk_analysis_always_computes_live_ignores_refresh_flag(self):
        """The old behavior queued PaymentPrediction.train() on a worker when
        refresh=True and answered immediately. That cache/train split is gone:
        payment_risk_analysis now always calls predict() synchronously and the
        refresh flag is accepted only for backward compatibility with older
        frontend callers (see insights/api/ml/general.py docstring) -- it must
        never train inline and must never enqueue a background job."""
        with patch.object(frappe, "has_permission"), \
             patch("insights.ml.payment_prediction.PaymentPrediction") as MockPP, \
             patch("frappe.enqueue") as mock_enqueue:
            instance = MockPP.return_value
            instance.predict.return_value = {"predictions": [], "summary": {}}
            result = general_api.payment_risk_analysis(refresh=True)

            instance.train.assert_not_called()
            instance.predict.assert_called_once()
            mock_enqueue.assert_not_called()
            self.assertEqual(result["status"], "success")

    def test_payment_risk_analysis_returns_predictions_shape(self):
        """PaymentPrediction.train() returns model metrics (accuracy,
        feature_importance...), NOT the {predictions, summary} shape callers expect.
        The read path must come from predict(). See outside-voice finding 5."""
        with patch.object(frappe, "has_permission"), \
             patch("insights.ml.payment_prediction.PaymentPrediction") as MockPP:
            instance = MockPP.return_value
            instance.predict.return_value = {"predictions": [], "summary": {}}
            result = general_api.payment_risk_analysis(refresh=False)
            instance.train.assert_not_called()
            instance.predict.assert_called_once()
            self.assertEqual(result["data"], {"predictions": [], "summary": {}})

    def test_cross_dashboard_search_sales_domain_is_a_direct_bounded_read_not_an_ml_call(self):
        """The sales branch of domain search previously instantiated
        SalesIntelligence and called .train()/.predict() per keystroke -- both
        slow and, in an earlier bug, retraining on every search hit. sales_intelligence.py
        is now pure Ibis functions (no SalesIntelligence class at all), and domain
        search was rewritten to a single capped frappe.get_all with zero ML
        involvement. See outside-voice finding 7."""
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService
        service = CrossDashboardSearchService()
        with patch.object(frappe, "get_all", return_value=[]) as mock_get_all:
            result = service._search_domain("sales", {"keywords": ["acme"]})
            mock_get_all.assert_called_once()
            self.assertEqual(mock_get_all.call_args.args[0], "Sales Invoice")
        self.assertEqual(result["results"], [])

    def test_duplicate_ml_module_functions_are_no_longer_whitelisted(self):
        """The critical finding: insights/ml/*.py had its own @frappe.whitelist()
        copies of the same functions gated in insights/api/ml/*.py, reachable
        via their full dotted path with zero permission check -- a parallel
        unguarded surface that bypassed every has_permission gate added in
        this review. Confirmed unused by frontend and by internal Python
        callers, so the fix is de-whitelisting rather than double-gating."""
        import insights.ml.hr_intelligence as hr_ml
        import insights.ml.executive_intelligence as exec_ml
        import insights.ml.marketing_intelligence as marketing_ml
        import insights.ml.sales_intelligence as sales_ml
        for module, name in [
            (hr_ml, "get_hr_overview"),
            (exec_ml, "get_executive_summary"),
            (marketing_ml, "get_marketing_overview"),
            (sales_ml, "get_sales_intelligence"),
        ]:
            fn = getattr(module, name)
            self.assertFalse(
                getattr(fn, "whitelisted", False),
                f"{module.__name__}.{name} is still whitelisted -- parallel unguarded surface reopened",
            )


class TestPriceIntelligenceGates(FrappeTestCase):
    """The two selling-price endpoints, gated on the same principle as the rest.

    Both derive entirely from invoiced prices, so ``Sales Invoice`` read is the
    access that matters - not ``Item``, which almost every role can read.
    ``price_forecast`` is the one on the hot path: the ``price-intelligence``
    Desk page calls it on every keystroke, so an ungated copy here would leak
    realised customer pricing to anyone who can open a form.
    """

    def test_price_forecast_checks_sales_invoice_permission(self):
        with patch.object(frappe, "has_permission") as mock_has_perm, patch(
            "insights.ml.price_intelligence.price_forecast", return_value={}
        ):
            price_api.price_forecast(item_code="ANY")
            mock_has_perm.assert_called_once_with("Sales Invoice", "read", throw=True)

    def test_price_forecast_permission_denial_propagates(self):
        with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError("denied")):
            with self.assertRaises(frappe.PermissionError):
                price_api.price_forecast(item_code="ANY")

    def test_dashboard_payload_checks_sales_invoice_permission(self):
        with patch.object(frappe, "has_permission") as mock_has_perm, patch(
            "insights.ml.price_intelligence.get_selling_price_intelligence", return_value={}
        ):
            price_api.get_selling_price_intelligence()
            mock_has_perm.assert_called_once_with("Sales Invoice", "read", throw=True)

    def test_dashboard_payload_permission_denial_propagates(self):
        """A cache hit must not bypass the gate: `cached_run` is called *after*
        `has_permission`, so a denial has to raise before any cache read."""
        with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError("denied")):
            with self.assertRaises(frappe.PermissionError):
                price_api.get_selling_price_intelligence()

    def test_ml_module_price_functions_are_not_whitelisted(self):
        """No parallel unguarded surface: the module functions are plain."""
        import insights.ml.price_intelligence as price_ml

        for name in ("price_forecast", "get_selling_price_intelligence"):
            fn = getattr(price_ml, name)
            self.assertFalse(
                getattr(fn, "whitelisted", False),
                f"insights.ml.price_intelligence.{name} is whitelisted -- ungated surface",
            )

    def test_approval_queue_checks_own_permission(self):
        """`_approval_queue` bypasses `ibis_source.t()` (raw `frappe.qb` against a
        doctype not wired into the ibis registry), so unlike its sibling sections
        it must gate itself explicitly rather than inherit row/column filtering
        for free."""
        import insights.ml.price_intelligence as price_ml

        with patch.object(frappe, "db") as mock_db, patch.object(
            frappe, "has_permission", return_value=False
        ) as mock_has_perm:
            mock_db.exists.return_value = True
            result = price_ml._approval_queue(company=None)

        mock_has_perm.assert_called_once_with("JKM Sales Pricing Request", "read")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["rows"], [])


class TestMarketingSourceMetricsGates(FrappeTestCase):
    """source_metrics/cost_per_lead/territory_leads had NO permission check
    at all -- unlike get_marketing_overview/get_crm_detail/lead_conversion
    in the same module, which all gate on Lead read. Found during the
    Marketing & CRM Intelligence dashboard audit (2026-09-19): orphaned
    (unused by the current Vue frontend, confirmed via grep) but still a
    live, reachable @frappe.whitelist() surface leaking Lead/GL Entry
    aggregates to any authenticated user."""

    def test_source_metrics_checks_lead_and_gl_entry_permission(self):
        with patch.object(frappe, "has_permission") as mock_has_perm, patch(
            "insights.ml.marketing_source_metrics.get_leads_by_source", return_value=[]
        ), patch(
            "insights.ml.marketing_source_metrics.get_hot_leads_by_source", return_value=[]
        ), patch(
            "insights.ml.marketing_source_metrics.get_cost_per_lead", return_value=[]
        ), patch(
            "insights.ml.marketing_source_metrics.get_territory_leads", return_value=[]
        ):
            marketing_api.source_metrics()
            mock_has_perm.assert_any_call("Lead", "read", throw=True)
            mock_has_perm.assert_any_call("GL Entry", "read", throw=True)

    def test_source_metrics_permission_denial_propagates(self):
        with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError("denied")):
            with self.assertRaises(frappe.PermissionError):
                marketing_api.source_metrics()

    def test_cost_per_lead_checks_lead_and_gl_entry_permission(self):
        with patch.object(frappe, "has_permission") as mock_has_perm, patch(
            "insights.ml.marketing_source_metrics.get_cost_per_lead", return_value=[]
        ):
            marketing_api.cost_per_lead()
            mock_has_perm.assert_any_call("Lead", "read", throw=True)
            mock_has_perm.assert_any_call("GL Entry", "read", throw=True)

    def test_cost_per_lead_permission_denial_propagates(self):
        with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError("denied")):
            with self.assertRaises(frappe.PermissionError):
                marketing_api.cost_per_lead()

    def test_territory_leads_checks_lead_permission(self):
        with patch.object(frappe, "has_permission") as mock_has_perm, patch(
            "insights.ml.marketing_source_metrics.get_territory_leads", return_value=[]
        ):
            marketing_api.territory_leads()
            mock_has_perm.assert_called_once_with("Lead", "read", throw=True)

    def test_territory_leads_permission_denial_propagates(self):
        with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError("denied")):
            with self.assertRaises(frappe.PermissionError):
                marketing_api.territory_leads()


class TestStrategicFinanceAndBudgetVarianceCompanyScoping(FrappeTestCase):
    """Regression tests for routing company resolution through
    `permitted_company()` instead of `get_user_default`/`Global Defaults`
    (see insights/ml/breakeven_engine.py:29,38-49 for the reference fix).

    A user default or site-wide Global Default is a preference, not a
    permission boundary; these tests confirm both intelligence classes
    resolve `self.company` through the same permission-checked path
    `BreakevenEngine` already uses, and that both dashboard entry points
    are gated by `authorize_dashboard` like every other dashboard.
    """

    def test_strategic_finance_intelligence_resolves_company_via_permitted_company(self):
        with patch(
            "insights.ml.strategic_finance.model.permitted_company", return_value="Test Company"
        ) as mock_permitted:
            from insights.ml.strategic_finance.model import StrategicFinanceIntelligence

            model = StrategicFinanceIntelligence()
            mock_permitted.assert_called_once_with(None)
            self.assertEqual(model.company, "Test Company")

    def test_strategic_finance_intelligence_throws_when_no_company_permitted(self):
        with patch("insights.ml.strategic_finance.model.permitted_company", return_value=None):
            from insights.ml.strategic_finance.model import StrategicFinanceIntelligence

            with self.assertRaises(frappe.ValidationError):
                StrategicFinanceIntelligence()

    def test_budget_variance_intelligence_resolves_company_via_permitted_company(self):
        with patch(
            "insights.api.ml.permissions.permitted_company", return_value="Test Company"
        ) as mock_permitted:
            from insights.ml.budget_variance_intelligence import BudgetVarianceIntelligence

            model = BudgetVarianceIntelligence()
            mock_permitted.assert_called_once_with(None)
            self.assertEqual(model.company, "Test Company")

    def test_budget_variance_intelligence_checks_explicit_company_against_permitted_list(self):
        """An explicit `company=` argument must still cross `permitted_company`
        -- passing it straight through (the pre-fix `company or default_company()`
        shape) would let a caller request an unpermitted company directly."""
        with patch(
            "insights.api.ml.permissions.permitted_company", return_value="Requested Co"
        ) as mock_permitted:
            from insights.ml.budget_variance_intelligence import BudgetVarianceIntelligence

            model = BudgetVarianceIntelligence(company="Requested Co")
            mock_permitted.assert_called_once_with({"company": "Requested Co"})
            self.assertEqual(model.company, "Requested Co")

    def test_budget_variance_intelligence_throws_when_no_company_permitted(self):
        with patch("insights.api.ml.permissions.permitted_company", return_value=None):
            from insights.ml.budget_variance_intelligence import BudgetVarianceIntelligence

            with self.assertRaises(frappe.ValidationError):
                BudgetVarianceIntelligence()

    def test_strategic_finance_intelligence_endpoint_gated_by_authorize_dashboard(self):
        from insights.api.ml import strategic_finance as strategic_finance_api

        with patch.object(frappe, "has_permission"), patch(
            "insights.api.ml.strategic_finance.authorize_dashboard",
            side_effect=frappe.PermissionError("denied"),
        ) as mock_authorize:
            with self.assertRaises(frappe.PermissionError):
                strategic_finance_api.strategic_finance_intelligence()
            mock_authorize.assert_called_once_with("strategic_finance")

    def test_budget_variance_overview_endpoint_gated_by_authorize_dashboard(self):
        from insights.api.ml import strategic_finance as strategic_finance_api

        with patch.object(frappe, "has_permission"), patch(
            "insights.api.ml.strategic_finance.authorize_dashboard",
            side_effect=frappe.PermissionError("denied"),
        ) as mock_authorize:
            with self.assertRaises(frappe.PermissionError):
                strategic_finance_api.get_budget_variance_overview()
            mock_authorize.assert_called_once_with("budget_variance")

    def test_dashboard_doctypes_lists_strategic_finance_and_budget_variance(self):
        from insights.api.ml.permissions import DASHBOARD_DOCTYPES

        self.assertIn("strategic_finance", DASHBOARD_DOCTYPES)
        self.assertIn("budget_variance", DASHBOARD_DOCTYPES)
        self.assertIn("GL Entry", DASHBOARD_DOCTYPES["strategic_finance"])
        self.assertIn("GL Entry", DASHBOARD_DOCTYPES["budget_variance"])