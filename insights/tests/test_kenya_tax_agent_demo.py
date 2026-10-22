# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Offline checks (no site): the Tax agent speaks Kenya figures taken from `rules`, and the
demo-data planners produce balanced, rule-consistent numbers.

    cd apps/insights && ../../env/bin/python -m unittest insights.tests.test_kenya_tax_agent_demo
"""

import json
import unittest
from datetime import date
from unittest.mock import patch

from insights.agents.base import BaseIntelligenceAgent
from insights.agents.tax_agent import TaxIntelligenceAgent
from insights.ml.kenya_tax_intelligence import rules
from insights.setup import tax_demo_data as demo


def _agent():
    with patch.object(BaseIntelligenceAgent, "_load_config", lambda self: None):
        return TaxIntelligenceAgent()


class TestTaxAgentKenya(unittest.TestCase):
    def test_prompt_carries_rule_figures(self):
        prompt = _agent()._get_default_system_prompt({})
        lel, uel = rules.nssf_limits(date.today())
        for needle in (
            f"{rules.VAT_RATE * 100:g}%",
            f"{rules.VAT_REG_THRESHOLD:,.0f}",
            f"{rules.SHIF_RATE * 100:g}%",
            f"{rules.SHIF_MIN:,.0f}",
            f"{uel:,.0f}",
            f"{lel:,.0f}",
            f"{rules.AMNESTY_DEADLINE:%d %b %Y}",
            f"{rules.CIT_RATE * 100:g}%",
            "Tribunal",
        ):
            self.assertIn(needle, prompt)
        for row in rules.wht_rate_card():
            self.assertIn(f"{row['payment']}: {row['resident']:g}% resident", prompt)
        self.assertNotIn("GST", prompt)

    def test_compress_keeps_unknowns_and_drops_ui_plumbing(self):
        payload = {
            "company": "Acme",
            "period": {"key": "fy", "name": "FY 2026"},
            "tabs": {"vat": {"available": True, "kpis": [{"key": "net", "value": None}], "monthly": [{"m": i, "drill": {"x": 1}} for i in range(12)], "cases": list(range(9))}},
        }
        out = _agent().compress_context(payload)
        vat = out["tabs"]["vat"]
        self.assertTrue(out["kenya_tax"])
        self.assertIsNone(vat["kpis"][0]["value"])
        self.assertEqual(len(vat["monthly"]), 12)  # chart series kept whole
        self.assertEqual(len(vat["cases"]), 5)
        self.assertNotIn("drill", json.dumps(out))

    def test_quick_actions_and_keywords_are_kenyan(self):
        agent = _agent()
        self.assertTrue(agent.get_quick_actions())
        self.assertIn("etims", agent.get_routing_keywords())
        self.assertNotIn("gst", " ".join(agent.get_routing_keywords()).lower())


class TestTaxDemoPlans(unittest.TestCase):
    on = date(2026, 10, 22)

    def test_sales_and_purchases_use_rule_rates(self):
        for s in demo.plan_sales(self.on):
            self.assertAlmostEqual(s["vat"], 0 if s["template"] is None else round(s["net"] * rules.VAT_RATE, 2), places=2)
        for p in demo.plan_purchases(self.on):
            self.assertAlmostEqual(p["total"], p["net"] + p["vat"] - p["wht"], places=2)

    def test_journals_balance_and_slips_follow_rules(self):
        payroll = demo.plan_payroll(self.on)
        for j in demo.journal_plan(self.on, demo.plan_purchases(self.on), payroll):
            self.assertAlmostEqual(sum(x[1] for x in j["lines"]), sum(x[2] for x in j["lines"]), places=2, msg=j["remark"])
        first = payroll[0]
        slip = first["slips"][3]
        expected = rules.paye(slip["gross"], first["month"], resident=True)
        self.assertEqual(slip["deductions"]["PAYE"], expected["paye"])
        self.assertEqual(slip["deductions"]["SHIF"], expected["shif"])
        # latest month carries the seeded exceptions
        latest = payroll[-1]["slips"]
        self.assertLess(latest[demo.UNDERSTATED_NSSF]["deductions"]["NSSF Employee"], rules.nssf(latest[demo.UNDERSTATED_NSSF]["gross"], payroll[-1]["month"])["employee"])


if __name__ == "__main__":
    unittest.main()
