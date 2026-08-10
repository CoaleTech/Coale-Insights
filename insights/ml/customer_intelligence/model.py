# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Customer Intelligence Model
Houses the CustomerIntelligence class (formerly in __init__.py).
"""

import frappe
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List

from insights.ml.base import BaseMLModel
from insights.api.ml.utils import get_date_filter_sql, parse_date_filter

# Sibling submodules by direct module path, never
# `from <package> import <submodule>`: that form has to wait for the package's
# own __init__ to finish, so it deadlocks against a concurrent request that is
# initialising the package. Importing the submodule by path only needs the
# parent present in sys.modules, not completed.
import insights.ml.customer_intelligence.actions as _actions
import insights.ml.customer_intelligence.analytics as _analytics
import insights.ml.customer_intelligence.counts as _counts
import insights.ml.customer_intelligence.data as _data
import insights.ml.customer_intelligence.predict as _predict
import insights.ml.customer_intelligence.rankings as _rankings
import insights.ml.customer_intelligence.variance as _variance


class CustomerIntelligence(BaseMLModel):
    """
    Customer Intelligence Analytics Engine

    Provides:
    - Customer Lifetime Value (CLV) Analytics
    - Churn Risk Prediction
    - Customer Health Scoring
    - Geographic Intelligence (Territory-based)
    - Cohort Analysis
    - 80/20 Analysis (Pareto)
    - Next Best Action Recommendations

    Methods delegate to standalone functions in submodules, receiving
    ``self`` (the intelligence instance) as the first argument.
    """

    CUSTOMER_THRESHOLD = 5000  # Async threshold

    def __init__(self, date_filter: str = "12m"):
        super().__init__()
        self.model_name = "CustomerIntelligence"
        self.date_filter = date_filter
        self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
        self.base_currency = (
            frappe.db.get_value("Company", self.company, "default_currency")
            or frappe.db.get_single_value("System Settings", "default_currency")
            or "USD"
        )
        self.DATE_FILTER = get_date_filter_sql(date_filter, "posting_date", "si")
        parsed = parse_date_filter(date_filter)
        if parsed[0] is not None:
            self.period_start = parsed[0].strftime("%Y-%m-%d")
            self.period_end = parsed[1].strftime("%Y-%m-%d")
        else:
            self.period_start = "2000-01-01"
            self.period_end = datetime.now().strftime("%Y-%m-%d")

    # ==================== DATA COLLECTION ====================

    def _get_customer_transactions(self) -> pd.DataFrame:
        return _data.get_customer_transactions(self)

    def _get_territory_data(self) -> pd.DataFrame:
        return _data.get_territory_data(self)

    def _get_customer_items(self) -> pd.DataFrame:
        return _data.get_customer_items(self)

    def _get_payment_history(self) -> pd.DataFrame:
        return _data.get_payment_history(self)

    def _get_quotation_data(self) -> pd.DataFrame:
        return _data.get_quotation_data(self)

    # ==================== ANALYTICS ====================

    def calculate_clv(self, customer_df: pd.DataFrame) -> pd.DataFrame:
        return _analytics.calculate_clv(self, customer_df)

    def _calculate_clv_components(self, df: pd.DataFrame, tenure_months: pd.Series) -> pd.DataFrame:
        return _analytics._calculate_clv_components(df, tenure_months)

    def _calculate_rfm_segment(self, df: pd.DataFrame) -> pd.DataFrame:
        return _analytics._calculate_rfm_segment(df)

    def calculate_churn_risk(self, customer_df: pd.DataFrame, clv_df: pd.DataFrame) -> pd.DataFrame:
        return _analytics.calculate_churn_risk(self, customer_df, clv_df)

    def calculate_health_score(self, churn_df: pd.DataFrame, payment_df: pd.DataFrame) -> pd.DataFrame:
        return _analytics.calculate_health_score(self, churn_df, payment_df)

    # ==================== ACTIONS ====================

    def analyze_geography(self, health_df: pd.DataFrame, territory_df: pd.DataFrame) -> Dict[str, Any]:
        return _actions.analyze_geography(self, health_df, territory_df)

    def analyze_product_affinity(self, items_df: pd.DataFrame, health_df: pd.DataFrame) -> Dict[str, Any]:
        return _actions.analyze_product_affinity(self, items_df, health_df)

    def pareto_analysis(self, health_df: pd.DataFrame) -> Dict[str, Any]:
        return _actions.pareto_analysis(self, health_df)

    def cohort_analysis(self, customer_df: pd.DataFrame) -> Dict[str, Any]:
        return _actions.cohort_analysis(self, customer_df)

    def get_next_best_actions(self, health_df: pd.DataFrame) -> List[Dict[str, Any]]:
        return _actions.get_next_best_actions(self, health_df)

    def update_customer_scores(self, health_df: pd.DataFrame) -> Dict[str, Any]:
        return _actions.update_customer_scores(self, health_df)

    # ==================== PREDICT ====================

    def predict(self, customer: str = None, allow_train: bool = False) -> Dict[str, Any]:
        return _predict.predict(self, customer, allow_train=allow_train)

    # ==================== COUNTS & RANKINGS ====================

    def get_customer_counts(self, active_cutoff_months: int = 6) -> Dict[str, Any]:
        cache_key = f"customer_counts_{self.date_filter}_{active_cutoff_months}"
        cached = self.get_cached_results(cache_key, max_age_hours=6)
        if cached:
            return cached
        result = _counts.get_customer_counts(self, active_cutoff_months)
        self.cache_results(cache_key, result, expires_in_hours=6)
        return result

    def get_customer_revenue_split(self) -> Dict[str, Any]:
        cache_key = f"customer_revenue_split_{self.date_filter}"
        cached = self.get_cached_results(cache_key, max_age_hours=6)
        if cached:
            return cached
        result = _counts.get_customer_revenue_split(self)
        self.cache_results(cache_key, result, expires_in_hours=6)
        return result

    def get_customer_rankings(self, limit: int = 20) -> Dict[str, Any]:
        cache_key = f"customer_rankings_{self.date_filter}_{limit}"
        cached = self.get_cached_results(cache_key, max_age_hours=6)
        if cached:
            return cached
        result = _rankings.get_customer_rankings(self, limit)
        self.cache_results(cache_key, result, expires_in_hours=6)
        return result

    def get_customer_variance(self) -> List[Dict[str, Any]]:
        cache_key = f"customer_variance_{self.date_filter}"
        cached = self.get_cached_results(cache_key, max_age_hours=6)
        if cached:
            return cached
        result = _variance.get_customer_variance(self)
        self.cache_results(cache_key, result, expires_in_hours=6)
        return result

    # ==================== MAIN TRAINING METHOD ====================

    def train(self, update_customers: bool = True) -> Dict[str, Any]:
        """Run complete customer intelligence analysis"""
        customer_df = self._get_customer_transactions()
        territory_df = self._get_territory_data()
        items_df = self._get_customer_items()
        payment_df = self._get_payment_history()
        quotation_df = self._get_quotation_data()

        if customer_df.empty:
            return {"status": "error", "message": "No customer data found"}

        clv_df = self.calculate_clv(customer_df)
        churn_df = self.calculate_churn_risk(customer_df, clv_df)
        health_df = self.calculate_health_score(churn_df, payment_df)

        geo_analysis = self.analyze_geography(health_df, territory_df)
        product_affinity = self.analyze_product_affinity(items_df, health_df)
        pareto = self.pareto_analysis(health_df)
        cohort = self.cohort_analysis(customer_df)
        actions = self.get_next_best_actions(health_df)

        if not quotation_df.empty:
            conversion_rate = quotation_df["converted"].mean() * 100
            total_quotes = len(quotation_df)
            converted_quotes = int(quotation_df["converted"].sum())
        else:
            conversion_rate = 0
            total_quotes = 0
            converted_quotes = 0

        update_result = {"status": "skipped"}
        if update_customers:
            update_result = self.update_customer_scores(health_df)

        summary = {
            "total_customers": len(health_df),
            "total_clv": float(health_df["historical_clv"].sum()),
            "avg_clv": float(health_df["historical_clv"].mean()),
            "avg_order_value": float(health_df["avg_order_value"].mean()),
            "avg_health_score": float(health_df["health_score"].mean()),
            "avg_churn_risk": float(health_df["churn_score"].mean()),
            "clv_tier_distribution": {
                str(k): int(v)
                for k, v in health_df["clv_tier"].value_counts().to_dict().items()
            },
            "health_distribution": {
                str(k): int(v)
                for k, v in health_df["health_status"].value_counts().to_dict().items()
            },
            "churn_risk_distribution": {
                str(k): int(v)
                for k, v in health_df["churn_risk"].value_counts().to_dict().items()
            },
            "rfm_segment_distribution": (
                {
                    str(k): int(v)
                    for k, v in health_df["rfm_segment"].value_counts().to_dict().items()
                }
                if "rfm_segment" in health_df.columns
                else {}
            ),
            "quote_conversion_rate": round(conversion_rate, 1),
            "total_quotes": int(total_quotes),
            "converted_quotes": converted_quotes,
        }

        customer_fields = [
            "customer_id", "customer_name", "customer_group", "territory",
            "historical_clv", "predicted_12m_clv", "total_clv", "clv_tier", "clv_score",
            "order_count", "avg_order_value", "recency_days", "purchase_frequency",
            "churn_score", "churn_risk", "health_score", "health_status",
            "outstanding_amount", "rfm_score", "rfm_segment",
            "revenue_score", "engagement_score", "longevity_score", "growth_score",
            "avg_days_to_pay", "payment_score", "overdue_count",
        ]
        available_fields = [f for f in customer_fields if f in health_df.columns]
        customer_details = health_df[available_fields].copy()

        for col in ["clv_tier", "churn_risk", "health_status", "rfm_segment", "rfm_score"]:
            if col in customer_details.columns:
                customer_details[col] = customer_details[col].astype(str)

        for col in customer_details.columns:
            if customer_details[col].dtype == "object":
                customer_details[col] = customer_details[col].fillna("").astype(str)
            elif pd.api.types.is_numeric_dtype(customer_details[col]):
                customer_details[col] = customer_details[col].fillna(0)

        customer_details["clv_tier"] = customer_details["clv_tier"].replace("nan", "Bronze")
        customer_details["churn_risk"] = customer_details["churn_risk"].replace("nan", "Low")
        customer_details["health_status"] = customer_details["health_status"].replace("nan", "Healthy")
        if "rfm_segment" in customer_details.columns:
            customer_details["rfm_segment"] = customer_details["rfm_segment"].replace("nan", "Need Attention")
        if "rfm_score" in customer_details.columns:
            customer_details["rfm_score"] = customer_details["rfm_score"].replace("nan", "333")

        def clean_dict_for_json(d):
            """Recursively clean dict for JSON serialization"""
            if isinstance(d, dict):
                return {k: clean_dict_for_json(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [clean_dict_for_json(item) for item in d]
            elif isinstance(d, np.generic):
                # Convert numpy scalars (float64, int64, etc.) to native Python types
                val = d.item()
                return 0 if (isinstance(val, float) and (pd.isna(val) or val != val)) else val
            elif isinstance(d, float) and (pd.isna(d) or np.isnan(d)):
                return 0
            elif d is None or (isinstance(d, str) and d.lower() == "nan"):
                return ""
            return d

        # Annotated because `clean_dict_for_json` is untyped: without it the sorts
        # below are unresolvable against its union return type.
        customers_list: list[dict] = clean_dict_for_json(customer_details.to_dict("records"))

        # Highest value first. The query orders by `tabCustomer.name` (the customer
        # CODE, not the name), so the payload arrived in record-creation order and
        # the dashboard's 100-row table showed the 100 oldest customers: 0 of 66
        # customers with any CLV, ₹0 of ₹1.77bn. Every top customer sat past index
        # 390 and was unreachable without searching for it by name. Same key and
        # direction `top_customers` below already uses.
        customers_list.sort(key=lambda c: float(c.get("total_clv") or 0), reverse=True)

        results = {
            "status": "success",
            "analysis_date": datetime.now().isoformat(),
            "company": self.company,
            "base_currency": self.base_currency,
            "summary": clean_dict_for_json(summary),
            "customers": customers_list,
            "geographic_analysis": clean_dict_for_json(geo_analysis),
            "product_affinity": clean_dict_for_json(product_affinity),
            "pareto_analysis": clean_dict_for_json(pareto),
            "cohort_analysis": clean_dict_for_json(cohort),
            "next_best_actions": clean_dict_for_json(actions),
            "at_risk_customers": [c for c in customers_list if c.get("churn_risk") in ["High", "Critical"]],
            "top_customers": sorted(customers_list, key=lambda x: x.get("total_clv", 0), reverse=True)[:20],
            "customer_update_result": update_result,
        }

        self.cache_results("customer_intelligence", results, expires_in_hours=12)
        self.log_training({
            "customers_analyzed": len(health_df),
            "at_risk_count": len(results["at_risk_customers"]),
            "actions_generated": len(actions),
            "customers_updated": update_result.get("updated", 0),
        })

        return results
