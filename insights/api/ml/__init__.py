"""
ML API Package
Domain-specific ML analytics endpoints. Utility helpers live in utils.py.

All public (whitelisted) functions are resolved via __getattr__ so that Frappe
can find them through the `insights.api.ml.<function>` dotted path.

Fully lazy loading — no submodule is imported at package init time.  This
avoids Python 3.14 module-lock deadlocks that occur when concurrent requests
both trigger `importlib.import_module("insights.api.ml")` while a submodule is
still being loaded in another thread.

Frappe's whitelist check reads the `method.whitelisted` attribute that
@frappe.whitelist() sets on the function object itself, so the decorator does
not need to run at startup — it runs the first time the function is lazily
imported and is cached for subsequent calls.
"""

# Utils — safe to import eagerly (no circular refs, no heavy deps)
from insights.api.ml.utils import parse_date_filter, get_date_filter_sql  # noqa: F401

# Lazy module map: function name -> (module_path, function_name)
_LAZY_MAP = {
    # ------------------------------------------------------------------ customer
    "customer_segmentation": ("insights.api.ml.customer", "customer_segmentation"),
    "get_segment_summary": ("insights.api.ml.customer", "get_segment_summary"),
    "customer_intelligence": ("insights.api.ml.customer", "customer_intelligence"),
    "customer_intelligence_status": ("insights.api.ml.customer", "customer_intelligence_status"),
    "customer_360": ("insights.api.ml.customer", "customer_360"),
    "customer_360_detail": ("insights.api.ml.customer", "customer_360_detail"),
    "purchase_patterns": ("insights.api.ml.customer", "purchase_patterns"),
    "cross_sell_opportunities": ("insights.api.ml.customer", "cross_sell_opportunities"),
    "at_risk_customers": ("insights.api.ml.customer", "at_risk_customers"),
    "geographic_insights": ("insights.api.ml.customer", "geographic_insights"),
    "next_best_actions": ("insights.api.ml.customer", "next_best_actions"),
    "refresh_scores": ("insights.api.ml.customer", "refresh_scores"),
    "customer_counts": ("insights.api.ml.customer", "customer_counts"),
    "customer_revenue_split": ("insights.api.ml.customer", "customer_revenue_split"),
    "customer_rankings": ("insights.api.ml.customer", "customer_rankings"),
    "customer_variance": ("insights.api.ml.customer", "customer_variance"),
    # ------------------------------------------------------------------ sales
    "sales_forecast": ("insights.api.ml.sales", "sales_forecast"),
    "get_forecast_chart_data": ("insights.api.ml.sales", "get_forecast_chart_data"),
    "sales_intelligence": ("insights.api.ml.sales", "sales_intelligence"),
    "payment_mix": ("insights.api.ml.sales", "payment_mix"),
    "sales_rep_performance": ("insights.api.ml.sales", "sales_rep_performance"),
    "revenue_breakdown": ("insights.api.ml.sales", "revenue_breakdown"),
    "margin_analysis": ("insights.api.ml.sales", "margin_analysis"),
    "sales_comparisons": ("insights.api.ml.sales", "sales_comparisons"),
    "train_forecast_models": ("insights.api.ml.sales", "train_forecast_models"),
    "get_historical_and_forecast_by_dimension": ("insights.api.ml.sales", "get_historical_and_forecast_by_dimension"),
    "source_attributed_sales": ("insights.api.ml.sales", "source_attributed_sales"),
    "quotation_analytics": ("insights.api.ml.sales", "quotation_analytics"),
    "territory_sales_performance": ("insights.api.ml.sales", "territory_sales_performance"),
    "territory_performance": ("insights.api.ml.sales", "territory_performance"),
    # ------------------------------------------------------------------ inventory
    "inventory_classification": ("insights.api.ml.inventory", "inventory_classification"),
    "get_inventory_recommendations": ("insights.api.ml.inventory", "get_inventory_recommendations"),
    "inventory_intelligence": ("insights.api.ml.inventory", "inventory_intelligence"),
    "train_inventory_intelligence": ("insights.api.ml.inventory", "train_inventory_intelligence"),
    "get_stock_overview": ("insights.api.ml.inventory", "get_stock_overview"),
    "get_turnover_analysis": ("insights.api.ml.inventory", "get_turnover_analysis"),
    "get_aging_analysis": ("insights.api.ml.inventory", "get_aging_analysis"),
    "get_warehouse_analysis": ("insights.api.ml.inventory", "get_warehouse_analysis"),
    "get_transfer_recommendations": ("insights.api.ml.inventory", "get_transfer_recommendations"),
    "get_dead_stock": ("insights.api.ml.inventory", "get_dead_stock"),
    # ------------------------------------------------------------------ financial
    "financial_intelligence": ("insights.api.ml.financial", "financial_intelligence"),
    "train_financial_intelligence": ("insights.api.ml.financial", "train_financial_intelligence"),
    "get_financial_overview": ("insights.api.ml.financial", "get_financial_overview"),
    "get_cash_flow_analysis": ("insights.api.ml.financial", "get_cash_flow_analysis"),
    "get_receivables_analysis": ("insights.api.ml.financial", "get_receivables_analysis"),
    "get_payables_analysis": ("insights.api.ml.financial", "get_payables_analysis"),
    "get_forex_exposure": ("insights.api.ml.financial", "get_forex_exposure"),
    # ------------------------------------------------------------------ tax
    "tax_intelligence": ("insights.api.ml.tax", "tax_intelligence"),
    "gst_summary": ("insights.api.ml.tax", "gst_summary"),
    "itc_health": ("insights.api.ml.tax", "itc_health"),
    "tds_summary": ("insights.api.ml.tax", "tds_summary"),
    # ------------------------------------------------------------------ general
    "get_ml_status": ("insights.api.ml.general", "get_ml_status"),
    "run_all_models": ("insights.api.ml.general", "run_all_models"),
    "payment_risk_analysis": ("insights.api.ml.general", "payment_risk_analysis"),
    "get_high_risk_invoices": ("insights.api.ml.general", "get_high_risk_invoices"),
    "demand_forecast": ("insights.api.ml.general", "demand_forecast"),
    "get_reorder_alerts": ("insights.api.ml.general", "get_reorder_alerts"),
    "product_recommendations": ("insights.api.ml.general", "product_recommendations"),
    "recommend_for_item": ("insights.api.ml.general", "recommend_for_item"),
    "recommend_for_customer": ("insights.api.ml.general", "recommend_for_customer"),
    "recommend_for_cart": ("insights.api.ml.general", "recommend_for_cart"),
    "get_dashboard_data": ("insights.api.ml.general", "get_dashboard_data"),
    "get_ml_insights_summary": ("insights.api.ml.general", "get_ml_insights_summary"),
    "generate_presentation_data": ("insights.api.ml.general", "generate_presentation_data"),
    # ------------------------------------------------------------------ search
    "perform_cross_dashboard_search": ("insights.api.ml.search", "perform_cross_dashboard_search"),
    "get_search_suggestions": ("insights.api.ml.search", "get_search_suggestions"),
    "get_search_history": ("insights.api.ml.search", "get_search_history"),
    "save_search_favorite": ("insights.api.ml.search", "save_search_favorite"),
    "get_cross_dashboard_navigation": ("insights.api.ml.search", "get_cross_dashboard_navigation"),
    "get_search_help": ("insights.api.ml.search", "get_search_help"),
    "search_domain_data": ("insights.api.ml.search", "search_domain_data"),
    "get_available_search_filters": ("insights.api.ml.search", "get_available_search_filters"),
    # ------------------------------------------------------------------ strategic_finance
    "strategic_finance_intelligence": ("insights.api.ml.strategic_finance", "strategic_finance_intelligence"),
    "get_budget_variance_overview": ("insights.api.ml.strategic_finance", "get_budget_variance_overview"),
    # ------------------------------------------------------------------ breakeven
    "item_breakeven": ("insights.api.ml.breakeven", "item_breakeven"),
    "employee_breakeven": ("insights.api.ml.breakeven", "employee_breakeven"),
    "cash_flow_breakeven": ("insights.api.ml.breakeven", "cash_flow_breakeven"),
    "capital_efficiency": ("insights.api.ml.breakeven", "capital_efficiency"),
    "breakeven_summary": ("insights.api.ml.breakeven", "breakeven_summary"),
    "item_lead_breakeven_ratio": ("insights.api.ml.breakeven", "item_lead_breakeven_ratio"),
    # ------------------------------------------------------------------ risk
    "risk_intelligence": ("insights.api.ml.risk", "risk_intelligence"),
    # ------------------------------------------------------------------ procurement
    "get_procurement_insights": ("insights.api.ml.procurement", "get_procurement_insights"),
    "procurement_intelligence": ("insights.api.ml.procurement", "procurement_intelligence"),
    "train_procurement_intelligence": ("insights.api.ml.procurement", "train_procurement_intelligence"),
    "get_spend_overview": ("insights.api.ml.procurement", "get_spend_overview"),
    "get_supplier_performance": ("insights.api.ml.procurement", "get_supplier_performance"),
    "get_purchase_analytics": ("insights.api.ml.procurement", "get_purchase_analytics"),
    "get_price_intelligence": ("insights.api.ml.procurement", "get_price_intelligence"),
    "get_procurement_risks": ("insights.api.ml.procurement", "get_procurement_risks"),
    "get_procurement_forecast": ("insights.api.ml.procurement", "get_procurement_forecast"),
    # ------------------------------------------------------------------ manufacturing
    "get_manufacturing_overview": ("insights.api.ml.manufacturing", "get_manufacturing_overview"),
    "get_oee_analysis": ("insights.api.ml.manufacturing", "get_oee_analysis"),
    "get_capacity_analysis": ("insights.api.ml.manufacturing", "get_capacity_analysis"),
    "get_production_forecast": ("insights.api.ml.manufacturing", "get_production_forecast"),
    "get_manufacturing_recommendations": ("insights.api.ml.manufacturing", "get_manufacturing_recommendations"),
    # ------------------------------------------------------------------ hr
    "get_hr_overview": ("insights.api.ml.hr", "get_hr_overview"),
    "get_headcount_analytics": ("insights.api.ml.hr", "get_headcount_analytics"),
    "get_attrition_analytics": ("insights.api.ml.hr", "get_attrition_analytics"),
    "get_payroll_analytics": ("insights.api.ml.hr", "get_payroll_analytics"),
    "get_workforce_planning": ("insights.api.ml.hr", "get_workforce_planning"),
    "get_hr_insights": ("insights.api.ml.hr", "get_hr_insights"),
    "get_talent_analytics": ("insights.api.ml.hr", "get_talent_analytics"),
    "analyze_hr_query": ("insights.api.ml.hr", "analyze_hr_query"),
    # ------------------------------------------------------------------ esg
    # get_esg_overview / export_esg_report: esg_intelligence.py previously
    # returned fabricated scores (hardcoded board/ethics/risk/transparency/audit
    # values, synthetic trend data). Now honest {"status": "not_implemented"}
    # stubs (see esg.py) — kept registered so callers get a clean response
    # instead of a not-found error. See plan-eng-review D3.1.
    "get_esg_overview": ("insights.api.ml.esg", "get_esg_overview"),
    "export_esg_report": ("insights.api.ml.esg", "export_esg_report"),
    # ------------------------------------------------------------------ executive
    "get_executive_summary": ("insights.api.ml.executive", "get_executive_summary"),
    "get_business_health_score": ("insights.api.ml.executive", "get_business_health_score"),
    "get_executive_kpis": ("insights.api.ml.executive", "get_executive_kpis"),
    "get_executive_alerts": ("insights.api.ml.executive", "get_executive_alerts"),
    "get_executive_trends": ("insights.api.ml.executive", "get_executive_trends"),
    "get_executive_insights": ("insights.api.ml.executive", "get_executive_insights"),
    "get_department_insights": ("insights.api.ml.executive", "get_department_insights"),
    "get_strategic_recommendations": ("insights.api.ml.executive", "get_strategic_recommendations"),
    "analyze_executive_query": ("insights.api.ml.executive", "analyze_executive_query"),
    "generate_executive_report": ("insights.api.ml.executive", "generate_executive_report"),
    "send_executive_report": ("insights.api.ml.executive", "send_executive_report"),
    "get_executive_reports_status": ("insights.api.ml.executive", "get_executive_reports_status"),
    "get_recent_executive_reports": ("insights.api.ml.executive", "get_recent_executive_reports"),
    "download_executive_report": ("insights.api.ml.executive", "download_executive_report"),
    "test_executive_intelligence_data": ("insights.api.ml.executive", "test_executive_intelligence_data"),
    "preview_executive_report_data": ("insights.api.ml.executive", "preview_executive_report_data"),
    # `predictive` removed 2026-08-10: AdvancedPredictiveAnalyticsEngine trained on
    # simulated history, all 8 endpoints had already been reduced to
    # {"status": "not_implemented"} stubs, and nothing in the frontend called any
    # of them. Engine, endpoints and agent deleted (~2,740 lines).
}

# Cache resolved functions to avoid repeated importlib calls
_imported_cache = {}


def __getattr__(name):
    if name in _imported_cache:
        return _imported_cache[name]
    if name in _LAZY_MAP:
        import importlib
        module_path, func_name = _LAZY_MAP[name]
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        _imported_cache[name] = func
        return func
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
