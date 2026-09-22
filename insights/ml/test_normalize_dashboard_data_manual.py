"""Self-check for PresentationModeService._normalize_dashboard_data --
run directly (no bench needed): python test_normalize_dashboard_data.py

Fixtures are minimal, shape-accurate slices of the real insights.api.ml.*
payloads verified live on jkm bench (see t_1f929a20 / t_28255820).
"""
import sys
import types

# Stub out `frappe` enough for presentation_service.py's module-level
# `import frappe` and `from frappe import _` -- this test only exercises
# _normalize_dashboard_data, which touches neither.
frappe_stub = types.ModuleType("frappe")
frappe_stub.utils = types.SimpleNamespace(now=lambda: "2026-01-01")
frappe_stub.db = types.SimpleNamespace(get_default=lambda *a, **k: "Test Co")
frappe_stub._ = lambda s: s
sys.modules.setdefault("frappe", frappe_stub)

from insights.ml.presentation_service import PresentationModeService

svc = PresentationModeService()


def test_executive_kpis_flatten_to_summary():
    data = {
        "kpis": {
            "financial": {"revenue": {"value": 6964241.25, "label": "Revenue"}},
            "sales": {"growth_rate": {"value": 10.0, "label": "Growth"}},
        },
        "alerts": [{"priority": "high", "message": "x"}],
    }
    out = svc._normalize_dashboard_data("executive", data)
    assert out["summary"] == {"revenue": 6964241.25, "growth_rate": 10.0}, out["summary"]
    assert data.get("summary") is None, "must not mutate caller's dict"


def test_hr_headcount_metrics_become_summary():
    data = {
        "headcount_metrics": {"total_employees": 11, "growth_rate_pct": 36.36, "largest_department": "Sales"},
        "recommendations": [{"title": "x"}],
    }
    out = svc._normalize_dashboard_data("hr", data)
    assert out["summary"]["total_employees"] == 11
    assert out["summary"]["growth_rate_pct"] == 36.36
    assert "largest_department" not in out["summary"], "non-numeric fields excluded"


def test_risk_overview_summary_and_nested_alerts():
    data = {
        "overview": {
            "aggregate_risk_score": 39.7,
            "aggregate_risk_category": "Medium",
            "alerts": [{"severity": "high", "title": "Overdue"}],
        }
    }
    out = svc._normalize_dashboard_data("risk", data)
    assert out["summary"]["aggregate_risk_score"] == 39.7
    assert out["alerts"] == [{"severity": "high", "title": "Overdue"}]


def test_tax_flat_scalars_become_summary():
    data = {"net_gst": 885884.17, "effective_tax_rate": 16.04, "compliance_score": 87.17, "status": "success"}
    out = svc._normalize_dashboard_data("tax", data)
    assert out["summary"] == {
        "net_gst": 885884.17,
        "effective_tax_rate": 16.04,
        "compliance_score": 87.17,
    }


def test_manufacturing_and_procurement_and_inventory():
    out = svc._normalize_dashboard_data(
        "manufacturing", {"production_metrics": {"total_work_orders": 12, "completion_rate_pct": 91.5}}
    )
    assert out["summary"] == {"total_work_orders": 12, "completion_rate_pct": 91.5}

    out = svc._normalize_dashboard_data(
        "procurement", {"spend_overview": {"total_spend_12m": 1000, "supplier_count": 4}}
    )
    assert out["summary"] == {"total_spend_12m": 1000, "supplier_count": 4}

    out = svc._normalize_dashboard_data(
        "inventory", {"stock_overview": {"total_skus": 64, "health_score": 80}}
    )
    assert out["summary"] == {"total_skus": 64, "health_score": 80}


def test_marketing_kpis_become_summary():
    out = svc._normalize_dashboard_data(
        "marketing", {"kpis": {"total_leads": 3763, "lead_conversion_rate": 8.8}}
    )
    assert out["summary"] == {"total_leads": 3763, "lead_conversion_rate": 8.8}


def test_unknown_or_already_flat_data_is_left_alone():
    # esg is "not_implemented" today; must not crash on a status-only dict.
    out = svc._normalize_dashboard_data("esg", {"status": "not_implemented", "message": "x"})
    assert "summary" not in out

    # price has no mapped summary source -- must not crash / must not fabricate one.
    out = svc._normalize_dashboard_data("price", {"margin_by_item": [{"item_code": "A"}]})
    assert "summary" not in out


def test_existing_summary_key_is_not_clobbered():
    data = {"summary": {"already": "here"}, "headcount_metrics": {"total_employees": 99}}
    out = svc._normalize_dashboard_data("hr", data)
    assert out["summary"] == {"already": "here"}


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} tests passed")
