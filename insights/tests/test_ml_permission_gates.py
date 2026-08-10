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


class TestMLPermissionGates(FrappeTestCase):
    def test_hr_overview_checks_employee_and_salary_slip_permission(self):
        """get_hr_overview aggregates payroll data (via _analyze_payroll), so
        it must gate on Salary Slip in addition to Employee -- Employee read
        alone doesn't imply salary visibility. See outside-voice finding 4."""
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.hr_intelligence.HRIntelligence") as MockHR:
            MockHR.return_value.get_hr_overview.return_value = {}
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
        """calculate_employee_breakeven queries Salary Slip (payroll), not
        Sales Invoice -- the original gate was for the wrong doctype
        entirely. See outside-voice finding 3."""
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.breakeven_engine.BreakevenEngine") as MockEngine:
            MockEngine.return_value.calculate_employee_breakeven.return_value = {}
            breakeven_api.employee_breakeven()
            mock_has_perm.assert_called_once_with("Salary Slip", "read", throw=True)

    def test_capital_efficiency_gates_on_gl_entry(self):
        """calculate_roce/calculate_irr are GL Entry-derived, not Sales
        Invoice. See outside-voice finding 3."""
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.breakeven_engine.BreakevenEngine") as MockEngine:
            MockEngine.return_value.calculate_roce.return_value = 0
            MockEngine.return_value.calculate_irr.return_value = 0
            breakeven_api.capital_efficiency()
            mock_has_perm.assert_called_once_with("GL Entry", "read", throw=True)

    def test_department_insights_gates_per_requested_department(self):
        """A single fixed 'Sales Invoice' gate let a Sales-only user pass
        department='hr' and read payroll data through get_department_insights
        -- the gate must match the doctype the requested department actually
        exposes. See outside-voice finding 2."""
        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.executive_intelligence.ExecutiveIntelligence") as MockEI:
            MockEI.return_value.get_department_deep_dive.return_value = {}
            executive_api.get_department_insights(department="hr")
            mock_has_perm.assert_called_once_with("Salary Slip", "read", throw=True)

        with patch.object(frappe, "has_permission") as mock_has_perm, \
             patch("insights.ml.executive_intelligence.ExecutiveIntelligence") as MockEI:
            MockEI.return_value.get_department_deep_dive.return_value = {}
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

    def test_payment_risk_analysis_never_trains_in_the_request(self):
        """refresh=True used to call PaymentPrediction.train() inline, which fitted a
        RandomForest while the browser held the connection. It now queues the fit on
        a worker and answers immediately."""
        with patch.object(frappe, "has_permission"), \
             patch("insights.ml.payment_prediction.PaymentPrediction") as MockPP, \
             patch("frappe.utils.background_jobs.get_job_status", return_value=None), \
             patch("frappe.enqueue") as mock_enqueue:
            instance = MockPP.return_value
            result = general_api.payment_risk_analysis(refresh=True)

            instance.train.assert_not_called()
            instance.predict.assert_not_called()
            mock_enqueue.assert_called_once()
            self.assertEqual(
                mock_enqueue.call_args[0][0],
                "insights.ml.scheduler.train_payment_prediction",
            )
            self.assertEqual(mock_enqueue.call_args[1]["queue"], "long")
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

    def test_cross_dashboard_search_sales_domain_uses_predict_not_train(self):
        """The sales branch of _get_domain_data was written new in this
        review and initially called .train() unconditionally on every search
        hit -- same cache-bypass bug as the sales.py dashboard endpoints it
        was meant to be consistent with. See outside-voice finding 7."""
        from insights.ml.cross_dashboard_search import CrossDashboardSearchService
        service = CrossDashboardSearchService()
        with patch("insights.ml.sales_intelligence.SalesIntelligence") as MockSI:
            MockSI.return_value.predict.return_value = {}
            service._get_domain_data("sales")
            MockSI.return_value.predict.assert_called_once()
            MockSI.return_value.train.assert_not_called()

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