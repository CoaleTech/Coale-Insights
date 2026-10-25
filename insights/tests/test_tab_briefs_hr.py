import unittest

from insights.ml.tab_briefs.hr import briefs
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def test_attrition_brief_merges_department_health(self):
        b = briefs(load("hr"))["attrition"]
        self.assertEqual(b["severity"], "high")
        self.assertIn("63.6%", b["headline"])
        self.assertIn("7 involuntary and 0 voluntary", b["headline"])
        self.assertIn("3 employees (27.3%) without a department", b["headline"])

    def test_payroll_brief_absent_until_salary_slips_exist(self):
        self.assertNotIn("payroll", briefs(load("hr")))

    def test_payroll_brief_with_data(self):
        p = load("hr")
        p["payroll_metrics"].update(payroll_efficiency="ok", total_payroll_cost=1000, employees_on_payroll=2, average_salary=500)
        self.assertEqual(briefs(p)["payroll"]["headline"], "Payroll cost ₹1,000 across 2 employees, average salary ₹500.")

    def test_planning_brief(self):
        b = briefs(load("hr"))["planning"]
        self.assertEqual(b["severity"], "high")
        self.assertIn("63.6%", b["headline"])
        self.assertIn("7 exits a year", b["headline"])
        self.assertIn("76.4%", b["headline"])

    def test_merged_department_id_is_gone(self):
        self.assertNotIn("department", briefs(load("hr")))
