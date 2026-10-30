import unittest

from insights.ml.tab_briefs.hr import briefs
from insights.tests.tab_briefs_fixture import load


class TestBriefs(unittest.TestCase):
    def test_attrition_brief(self):
        b = briefs(load("hr"))["attrition"]
        self.assertEqual(b["severity"], "high")
        self.assertIn("63.6%", b["headline"])
        self.assertIn("7 involuntary and 0 voluntary", b["headline"])
        self.assertNotIn("department", b["headline"])

    def test_department_brief(self):
        b = briefs(load("hr"))["department"]
        self.assertEqual(b["severity"], "medium")
        self.assertEqual(
            b["headline"],
            "5 departments named; the largest, Sales, has 4 employees (36.4% of 11). 3 employees (27.3%) have no department.",
        )
        self.assertEqual([a["title"] for a in b["actions"]], ["Plan cover for single-person departments", "Assign 3 employees to a department"])

    def test_payroll_brief_explains_the_gap_until_salary_slips_exist(self):
        b = briefs(load("hr"))["payroll"]
        self.assertEqual(b["headline"], "No Salary Slip records exist, so payroll and compensation figures are unavailable for 11 active employees.")
        self.assertEqual(b["actions"][0]["title"], "Set up payroll in HRMS")

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

    def test_every_tab_has_a_brief(self):
        self.assertEqual(set(briefs(load("hr"))), {"attrition", "department", "payroll", "planning"})


class TestAttritionPeriods(unittest.TestCase):
    def test_attrition_computes_for_every_period(self):
        # TTM's start date came back as a string and broke the start-headcount maths.
        from insights.ml.hr_intelligence import HRIntelligence

        for period in ("MTD", "QTD", "YTD", "TTM"):
            rate = HRIntelligence(period)._analyze_attrition()["attrition_rate_pct"]
            self.assertGreaterEqual(rate, 0, period)
