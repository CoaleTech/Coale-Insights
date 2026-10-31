import unittest

from insights.ml.hr_intelligence import _count


class TestHRCount(unittest.TestCase):
    def test_null_sum_over_empty_window_is_zero(self):
        # SUM over zero rows is NULL -> NaN, which broke every empty period (e.g. MTD).
        self.assertEqual(_count(float("nan")), 0)
        self.assertEqual(_count(None), 0)

    def test_values_pass_through_as_int(self):
        self.assertEqual(_count(3.0), 3)
        self.assertEqual(_count(0), 0)
