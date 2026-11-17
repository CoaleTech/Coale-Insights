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


def test_tax_overview_kpis_become_summary():
    kpis = [
        {"key": "due_30d", "label": "Due in next 30 days", "value": 1905660.0, "unit": "money"},
        {"key": "etims_purchase_coverage", "label": "eTIMS purchase coverage", "value": 92.5, "unit": "pct"},
        {"key": "paid_on_time_12m", "label": "Paid on time, 12 months", "value": None, "unit": "pct"},
        {"key": "filing_note", "label": "Note", "value": "n/a", "unit": "text"},
    ]
    out = svc._normalize_dashboard_data("tax", {"status": "success", "tabs": {"overview": {"kpis": kpis}}})
    # tiles with no number (None, text) are dropped; the rest keep their label and unit's format
    assert out["summary"] == {"due_30d": 1905660.0, "etims_purchase_coverage": 92.5}
    assert out["_kpi_meta"] == {
        "due_30d": {"label": "Due in next 30 days", "format": "currency"},
        "etims_purchase_coverage": {"label": "eTIMS purchase coverage", "format": "percentage"},
    }
    assert svc._format_metric_value(92.5, "etims_purchase_coverage", "percentage") == "92.5%"


def test_tax_without_overview_has_empty_summary():
    assert svc._normalize_dashboard_data("tax", {"status": "success", "tabs": {}})["summary"] == {}


def test_deck_title_names_the_dashboard():
    def title(dashboard_type):
        return svc._generate_executive_slides({}, {}, dashboard_type)[0]["content"]["title"]

    assert title("hr") == "People Intelligence"
    assert title("revenue-customers") == "Revenue & Customers Intelligence"
    assert title("some_new_dashboard") == "Some New Dashboard Intelligence"


BRIEFS = {
    "tab_briefs": {
        "aging": {
            "severity": "high",
            "headline": "22,633 items older than 180 days.",
            "actions": [{"title": "Sell or write down stock", "text": "22,633 items.", "impact": "KSh 278,595,258"}],
        },
        "abc-xyz": {"severity": "none", "headline": "A-class items carry 80% of sales."},
        "turnover": {"severity": "low", "headline": ""},
    }
}


def test_slides_get_the_dashboard_specific_recommendations():
    slide_titles = lambda d, t: [s["content"]["title"] for s in svc._generate_executive_slides(d, {}, t)]
    # a recommendations slide exists only where the dashboard has something to recommend
    assert "Strategic Recommendations" in slide_titles(BRIEFS, "inventory")
    assert "Strategic Recommendations" not in slide_titles({}, "hr")


def test_manufacturing_and_procurement_and_inventory():
    out = svc._normalize_dashboard_data(
        "manufacturing", {"production_metrics": {"total_work_orders": 12, "completion_rate_pct": 91.5}}
    )
    assert out["summary"] == {"total_work_orders": 12, "completion_rate_pct": 91.5}

    out = svc._normalize_dashboard_data(
        "procurement", {"spend_overview": {"total_spend": 1000, "supplier_count": 4}}
    )
    assert out["summary"] == {"total_spend": 1000, "supplier_count": 4}

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


def test_insights_and_recommendations_come_from_the_dashboards_own_briefs():
    ins = svc._extract_key_insights(BRIEFS, "inventory")
    # worst first; a brief with no headline is skipped; "none" severity shows the placeholder
    assert [(i["title"], i["value"], i["impact"]) for i in ins] == [("Aging", "High", "high"), ("ABC / XYZ", "-", "none")]
    assert ins[0]["insight"] == "22,633 items older than 180 days."
    assert svc._extract_recommendations(BRIEFS, "inventory") == [
        {"title": "Sell or write down stock", "description": "22,633 items.", "priority": "high",
         "impact": "KSh 278,595,258", "effort": "-", "category": "Aging"}
    ]


def test_tax_deck_flags_warn_and_bad_tiles_and_lists_the_action_queue():
    tile = lambda key, value, tone: {"key": key, "label": key.title(), "value": value, "unit": "count", "tone": tone, "sub": "why"}
    data = {"tabs": {
        "wht": {"kpis": [tile("late", 6, "bad"), tile("fine", 1, "neutral"), tile("unknown", None, "bad")]},
        "actions": {"rows": [{"priority": "high", "action": "Apply 10% WHT to X", "tax": "WHT", "due_label": "No fixed date"}]},
    }}
    ins = svc._extract_key_insights(data, "tax")
    assert [(i["title"], i["value"], i["insight"], i["impact"]) for i in ins] == [("Late", "6", "why", "high")]
    (rec,) = svc._extract_recommendations(data, "tax")
    assert (rec["title"], rec["priority"], rec["category"], rec["description"]) == (
        "Apply 10% WHT to X", "high", "WHT", "WHT · No fixed date")


def test_executive_deck_reports_health_and_flagged_alerts():
    data = {
        "business_health_score": {"overall_score": 77.8, "overall_rag": "amber", "department_scores": {"hr": 90.0, "customer": 47.5}},
        "narrative": "Business health for the YTD period is 77.8/100 (watch). Financially: Revenue is up.",
        "alerts": [{"priority": "high", "department": "Customer", "message": "Avg Churn Risk at 47.4%", "rag_status": "red"}],
    }
    ins = svc._extract_key_insights(data, "executive")
    assert [(i["title"], i["value"], i["impact"]) for i in ins] == [
        ("Business Health", "77.8/100", "medium"), ("Lowest Department", "47.5/100", "high")]
    assert ins[0]["insight"] == "Business health for the YTD period is 77.8/100 (watch)."
    assert ins[1]["insight"] == "Customer scores lowest of 2 departments."
    (rec,) = svc._extract_recommendations(data, "executive")
    assert (rec["title"], rec["priority"]) == ("Customer: Avg Churn Risk at 47.4%", "high")


def test_marketing_alerts_become_recommendations_and_empty_dashboards_invent_nothing():
    alerts = [{"severity": "critical", "title": "CRM data is not being maintained", "description": "496 days old."}]
    recs = svc._extract_recommendations({"alerts": alerts}, "marketing")
    assert [(r["title"], r["priority"], r["category"]) for r in recs] == [
        ("CRM data is not being maintained", "high", "Marketing & CRM")]
    for dashboard_type in ("hr", "esg", "price", "tax", "executive"):
        assert svc._extract_recommendations({}, dashboard_type) == []
        assert svc._extract_key_insights({}, dashboard_type) == []


def test_machine_learning_deck_reports_untrained_models_missing_libraries_and_empty_tables():
    data = {
        "trained": 1, "total": 2,
        "models": [
            {"label": "Sales Forecast", "state": "trained", "detail": None, "gate": "g"},
            {"label": "Lead Conversion", "state": "blocked_on_data", "detail": "Needs 50 won leads.", "gate": "50+"},
        ],
        "libraries_missing": ["prophet"],
        "data": [{"doctype": "Work Order", "used_by": "Production forecast", "state": "empty"},
                 {"doctype": "Lead", "used_by": "Lead scoring", "state": "populated"}],
    }
    ins = svc._extract_key_insights(data, "machine_learning")
    assert [(i["title"], i["value"], i["impact"]) for i in ins] == [
        ("Models Trained", "1/2", "medium"), ("Lead Conversion", "Blocked on data", "medium"),
        ("Missing libraries", "prophet", "medium"), ("Empty source tables", "Work Order", "medium")]
    assert ins[1]["insight"] == "Needs 50 won leads."
    recs = svc._extract_recommendations(data, "machine_learning")
    assert [(r["title"], r["category"]) for r in recs] == [
        ("Unblock Lead Conversion", "Models"), ("Install prophet", "Libraries"), ("Record data in Work Order", "Data")]
    # nothing wrong: one low-severity line, no recommendations
    healthy = {"trained": 1, "total": 1, "models": [{"label": "A", "state": "trained"}]}
    assert [i["impact"] for i in svc._extract_key_insights(healthy, "machine_learning")] == ["low"]
    assert svc._extract_recommendations(healthy, "machine_learning") == []


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} tests passed")
