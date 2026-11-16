"""Minimal test for _risk_verdict — run with: python -m pytest insights/ml/test_risk_verdict.py -x -q"""

from insights.ml.risk_intelligence import _risk_verdict, WEIGHTS


def test_cashflow_primary_with_critical():
    # cash flow 70.8 * 0.30 = 21.24 > credit 44.0 * 0.30 = 13.2
    v = _risk_verdict(44.0, 70.8, 41.3, 0.0, 44.8, [{"severity": "critical"}])
    assert "Cash Flow" in v
    assert "critical" in v


def test_credit_primary_no_alerts():
    # credit 80 * 0.30 = 24 > cashflow 20 * 0.30 = 6
    total = 80.0 * WEIGHTS["credit"] + 20.0 * WEIGHTS["cashflow"] + 10.0 * WEIGHTS["operational"] + 5.0 * WEIGHTS["compliance"]
    v = _risk_verdict(80.0, 20.0, 10.0, 5.0, total, [])
    assert "Credit" in v
    assert "critical" not in v
