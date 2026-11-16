"""A cached dashboard served while a newer payload computes is flagged `refreshing`,
so a Refresh click can wait for the new numbers instead of showing the old ones."""

import unittest
from unittest.mock import patch

from insights.api.ml import utils

CACHED = {"status": "success", "data": {"net_profit": 1}}


class TestCachedRunRefreshFlag(unittest.TestCase):
    def _serve(self, *, in_flight: bool, refresh: bool):
        with (
            patch.object(utils, "_in_request", return_value=True),
            patch.object(utils, "_refresh_requested", return_value=refresh),
            patch.object(utils, "_scoped", side_effect=lambda k: k),
            patch.object(utils, "_record_demand"),
            patch.object(utils, "_clear_attempt"),
            patch.object(utils, "_ensure_compute", return_value=None),
            patch.object(utils, "_attempt_in_flight", return_value=in_flight),
            patch.object(utils.frappe.cache, "get_value", return_value=CACHED),
            patch.object(utils.frappe.cache, "hget", return_value={"job_id": "j", "ts": 1}),
        ):
            return utils.cached_run(lambda: {}, "k")

    def test_flagged_while_a_compute_is_in_flight(self):
        for refresh in (True, False):
            served = self._serve(in_flight=True, refresh=refresh)
            self.assertIs(served["refreshing"], True)
            self.assertEqual(served["data"], CACHED["data"])
        self.assertNotIn("refreshing", CACHED)  # the cached object is never mutated

    def test_plain_cache_hit_when_nothing_is_computing(self):
        for refresh in (True, False):
            self.assertEqual(self._serve(in_flight=False, refresh=refresh), CACHED)
