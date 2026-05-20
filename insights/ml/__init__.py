# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Machine Learning Module for Frappe Insights
Provides predictive analytics and data science capabilities for ERPNext
"""

from insights.ml.customer_segmentation import CustomerSegmentation
from insights.ml.abc_xyz_classification import ABCXYZClassification
from insights.ml.sales_forecasting import SalesForecasting
from insights.ml.payment_prediction import PaymentPrediction
from insights.ml.demand_forecasting import DemandForecasting
from insights.ml.product_recommendations import ProductRecommendations
from insights.ml.customer_intelligence.model import CustomerIntelligence
from insights.ml.sales_intelligence import SalesIntelligence
from insights.ml.risk_intelligence import RiskIntelligence
from insights.ml.breakeven_engine import BreakevenEngine

from insights.ml.india_tax_intelligence import IndiaTaxIntelligence

__all__ = [
    "CustomerSegmentation",
    "ABCXYZClassification",
    "SalesForecasting",
    "PaymentPrediction",
    "DemandForecasting",
    "ProductRecommendations",
    "CustomerIntelligence",
    "SalesIntelligence",
    "RiskIntelligence",
    "BreakevenEngine",
    "IndiaTaxIntelligence",
]
