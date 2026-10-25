import sys
import types
import unittest

from insights.ml import tab_briefs as tb


class TestMoney(unittest.TestCase):
    def test_exact_grouped_no_decimals(self):
        self.assertEqual(tb.money(316871197, "INR"), "₹316,871,197")

    def test_negative_sign_before_symbol(self):
        self.assertEqual(tb.money(-246351, "INR"), "-₹246,351")

    def test_missing_value_is_dash(self):
        self.assertEqual(tb.money(None, "INR"), "-")

    def test_rounds_half_up_to_whole_units(self):
        self.assertEqual(tb.money(42714077.5, "INR"), "₹42,714,078")


class TestPlural(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(tb.plural(1, "customer"), "1 customer")
        self.assertEqual(tb.plural(3, "customer"), "3 customers")
        self.assertEqual(tb.plural(2, "category", "categories"), "2 categories")
        self.assertEqual(tb.plural(0, "invoice"), "0 invoices")


class TestAttach(unittest.TestCase):
    def setUp(self):
        sys.modules["insights.ml.tab_briefs.fake"] = types.SimpleNamespace(
            briefs=lambda p: {"overview": tb.brief("low", f"n={p['n']}")}
        )
        tb.MODULES["insights_ml_fake"] = "fake"

    def tearDown(self):
        tb.MODULES.pop("insights_ml_fake", None)
        sys.modules.pop("insights.ml.tab_briefs.fake", None)

    def test_enveloped_payload_gets_briefs_under_data(self):
        r = tb.attach("insights_ml_fake:12m", {"status": "success", "data": {"n": 2}})
        self.assertEqual(r["data"]["tab_briefs"]["overview"]["headline"], "n=2")

    def test_unenveloped_payload_gets_briefs_at_top(self):
        r = tb.attach("insights_ml_fake", {"status": "success", "n": 5})
        self.assertEqual(r["tab_briefs"]["overview"]["headline"], "n=5")

    def test_error_result_is_untouched(self):
        r = tb.attach("insights_ml_fake", {"status": "error", "message": "x"})
        self.assertNotIn("tab_briefs", r)

    def test_unknown_key_is_untouched(self):
        r = tb.attach("insights_ml_other", {"status": "success", "data": {}})
        self.assertNotIn("tab_briefs", r["data"])

    def test_lazy_endpoint_gets_a_single_brief(self):
        r = tb.attach_lazy(
            {"status": "success", "rows": 3}, lambda p: tb.brief("none", f"{p['rows']} rows"), "x"
        )
        self.assertEqual(r["brief"], {"severity": "none", "headline": "3 rows"})

    def test_a_raising_lazy_brief_leaves_the_response_alone(self):
        r = tb.attach_lazy({"status": "success"}, lambda p: p["missing"], "x")
        self.assertNotIn("brief", r)

    def test_a_raising_brief_never_blanks_the_dashboard(self):
        sys.modules["insights.ml.tab_briefs.fake"] = types.SimpleNamespace(briefs=lambda _p: 1 / 0)
        r = tb.attach("insights_ml_fake", {"status": "success", "data": {"n": 1}})
        self.assertEqual(r, {"status": "success", "data": {"n": 1}})


class TestCachedRunHook(unittest.TestCase):
    def setUp(self):
        sys.modules["insights.ml.tab_briefs.fake"] = types.SimpleNamespace(
            briefs=lambda p: {"overview": tb.brief("low", f"n={p['n']}")}
        )
        tb.MODULES["insights_ml_fake"] = "fake"

    def tearDown(self):
        tb.MODULES.pop("insights_ml_fake", None)
        sys.modules.pop("insights.ml.tab_briefs.fake", None)

    def test_cached_run_attaches_before_caching(self):
        from unittest import mock

        from insights.api.ml import utils

        stored = {}
        with (
            mock.patch.object(utils, "_in_request", return_value=False),
            mock.patch.object(utils, "_refresh_requested", return_value=True),
            mock.patch.object(
                utils.frappe.cache, "set_value", side_effect=lambda k, v, **kw: stored.update({k: v})
            ),
        ):
            out = utils.cached_run(
                lambda: {"status": "success", "data": {"n": 7}}, "insights_ml_fake:12m"
            )
        self.assertEqual(out["data"]["tab_briefs"]["overview"]["headline"], "n=7")
        self.assertIn("tab_briefs", next(iter(stored.values()))["data"])
