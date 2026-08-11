from __future__ import annotations
import frappe
from frappe import _
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, Any, List, Optional
from insights.ml.base import BaseMLModel, get_date_range

if TYPE_CHECKING:
    import pandas as pd
    import numpy as np


class CustomerSegmentation(BaseMLModel):
    """
    RFM-based Customer Segmentation
    
    Segments:
    - Champions: High R, High F, High M (Best customers)
    - Loyal Customers: High F, High M
    - Potential Loyalists: High R, Medium F
    - New Customers: High R, Low F
    - Promising: Medium R, Low F
    - Need Attention: Medium R, Medium F, Medium M
    - About to Sleep: Low R, Low F
    - At Risk: Low R, High F, High M (Were good, haven't bought recently)
    - Can't Lose: Low R, High F, High M (Must win back)
    - Hibernating: Low R, Low F, Low M
    - Lost: Very Low R, Low F
    """
    
    SEGMENTS = {
        (5, 5, 5): "Champions",
        (5, 5, 4): "Champions",
        (5, 4, 5): "Champions",
        (5, 4, 4): "Champions",
        (4, 5, 5): "Champions",
        (4, 5, 4): "Loyal Customers",
        (4, 4, 5): "Loyal Customers",
        (4, 4, 4): "Loyal Customers",
        (5, 3, 3): "Potential Loyalists",
        (5, 3, 4): "Potential Loyalists",
        (5, 2, 3): "Potential Loyalists",
        (4, 3, 3): "Potential Loyalists",
        (5, 1, 1): "New Customers",
        (5, 1, 2): "New Customers",
        (5, 2, 1): "New Customers",
        (5, 2, 2): "New Customers",
        (4, 1, 1): "Promising",
        (4, 1, 2): "Promising",
        (4, 2, 1): "Promising",
        (3, 3, 3): "Need Attention",
        (3, 3, 4): "Need Attention",
        (3, 4, 3): "Need Attention",
        (3, 4, 4): "Need Attention",
        (3, 2, 2): "About to Sleep",
        (3, 2, 3): "About to Sleep",
        (3, 1, 2): "About to Sleep",
        (2, 5, 5): "At Risk",
        (2, 5, 4): "At Risk",
        (2, 4, 5): "At Risk",
        (2, 4, 4): "At Risk",
        (1, 5, 5): "Can't Lose",
        (1, 5, 4): "Can't Lose",
        (1, 4, 5): "Can't Lose",
        (2, 2, 2): "Hibernating",
        (2, 2, 3): "Hibernating",
        (2, 3, 2): "Hibernating",
        (1, 2, 2): "Hibernating",
        (1, 1, 1): "Lost",
        (1, 1, 2): "Lost",
        (1, 2, 1): "Lost",
        (2, 1, 1): "Lost",
    }
    
    def __init__(self):
        super().__init__()
        self.model_name = "CustomerSegmentation"
        self.analysis_date = datetime.now()
        
    def _get_rfm_data(self) -> pd.DataFrame:
        """Get RFM data from Sales Invoices"""
        query = """
            SELECT 
                customer,
                customer_name,
                MAX(posting_date) as last_purchase_date,
                COUNT(*) as frequency,
                SUM(grand_total) as monetary,
                MIN(posting_date) as first_purchase_date
            FROM `tabSales Invoice`
            WHERE docstatus = 1
                AND customer IS NOT NULL
                AND customer != ''
            GROUP BY customer, customer_name
            HAVING frequency > 0
        """
        return self.get_training_data(query)
    
    def _calculate_rfm_scores(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate RFM scores for each customer"""
        import pandas as pd

        if df.empty:
            return df
        
        # Calculate Recency (days since last purchase)
        df['last_purchase_date'] = pd.to_datetime(df['last_purchase_date'])
        df['recency'] = (self.analysis_date - df['last_purchase_date']).dt.days
        
        # Handle edge cases
        df['frequency'] = df['frequency'].fillna(0).astype(int)
        df['monetary'] = df['monetary'].fillna(0).astype(float)
        df['recency'] = df['recency'].fillna(999).astype(int)
        
        # Calculate quintile scores (1-5)
        # For Recency: Lower is better, so we reverse
        df['R'] = pd.qcut(df['recency'], q=5, labels=[5, 4, 3, 2, 1], duplicates='drop').astype(int)
        
        # For Frequency: Higher is better
        df['F'] = pd.qcut(df['frequency'].rank(method='first'), q=5, labels=[1, 2, 3, 4, 5], duplicates='drop').astype(int)
        
        # For Monetary: Higher is better
        df['M'] = pd.qcut(df['monetary'].rank(method='first'), q=5, labels=[1, 2, 3, 4, 5], duplicates='drop').astype(int)
        
        # Calculate RFM Score
        df['RFM_Score'] = df['R'].astype(str) + df['F'].astype(str) + df['M'].astype(str)
        
        # Assign Segment
        df['segment'] = df.apply(
            lambda x: self._get_segment(x['R'], x['F'], x['M']), 
            axis=1
        )
        
        return df
    
    def _get_segment(self, r: int, f: int, m: int) -> str:
        """Get segment name from RFM scores"""
        # Try exact match first
        segment = self.SEGMENTS.get((r, f, m))
        if segment:
            return segment
        
        # Fallback logic based on score ranges
        if r >= 4 and f >= 4 and m >= 4:
            return "Champions"
        elif r >= 4 and f >= 3:
            return "Loyal Customers"
        elif r >= 4 and f <= 2:
            return "New Customers"
        elif r == 3 and f >= 3:
            return "Need Attention"
        elif r <= 2 and f >= 4:
            return "At Risk"
        elif r <= 2 and f >= 3 and m >= 4:
            return "Can't Lose"
        elif r <= 2 and f <= 2:
            return "Hibernating"
        else:
            return "Need Attention"
    
    def train(self) -> Dict[str, Any]:
        """Run RFM analysis and segment customers"""
        # Get data
        df = self._get_rfm_data()
        
        if df.empty:
            return {
                "status": "error",
                "message": _("No customer data available"),
                "segments": {}
            }
        
        # Calculate RFM scores
        df = self._calculate_rfm_scores(df)
        
        # Prepare results
        segment_summary = df.groupby('segment').agg({
            'customer': 'count',
            'monetary': ['sum', 'mean'],
            'frequency': 'mean',
            'recency': 'mean'
        }).round(2)
        
        segment_summary.columns = ['customer_count', 'total_revenue', 'avg_revenue', 'avg_orders', 'avg_days_since']
        segment_summary = segment_summary.reset_index()
        
        # Update customer records with segments
        self._update_customer_segments(df)
        
        # Cache results
        results = {
            "status": "success",
            "analysis_date": self.analysis_date.isoformat(),
            "total_customers": len(df),
            "segments": segment_summary.to_dict('records'),
            "customers": df[['customer', 'customer_name', 'segment', 'R', 'F', 'M', 
                           'recency', 'frequency', 'monetary']].to_dict('records')
        }
        
        self.cache_results("customer_segmentation", results, expires_in_hours=24)
        
        # Log training
        self.log_training({
            "total_customers": len(df),
            "segments_found": len(segment_summary),
            "analysis_date": self.analysis_date.isoformat()
        })
        
        return results
    
    def _update_customer_segments(self, df: pd.DataFrame):
        """Update Customer doctype with segment info"""
        for _, row in df.iterrows():
            try:
                if frappe.db.exists("Customer", row['customer']):
                    frappe.db.set_value(
                        "Customer",
                        row['customer'],
                        {
                            "custom_rfm_segment": row['segment'],
                            "custom_rfm_score": f"{row['R']}{row['F']}{row['M']}",
                            "custom_lifetime_value": row['monetary'],
                            "custom_total_orders": row['frequency'],
                            "custom_days_since_purchase": row['recency'],
                            "custom_segment_updated": frappe.utils.now()
                        },
                        update_modified=False
                    )
            except Exception as e:
                # Skip if custom fields don't exist
                pass
        frappe.db.commit()
    
    def predict(self, customer: str = None) -> Dict[str, Any]:
        """Get segmentation for a specific customer or all"""
        cached = self.get_cached_results("customer_segmentation")
        
        if not cached:
            cached = self.train()
        
        if customer:
            customers = cached.get("customers", [])
            for c in customers:
                if c['customer'] == customer:
                    return {"status": "success", "customer": c}
            return {"status": "error", "message": _("Customer not found")}
        
        return cached
    
    def get_segment_recommendations(self, segment: str) -> Dict[str, Any]:
        """Get marketing recommendations for a segment"""
        recommendations = {
            "Champions": {
                "strategy": "Reward and retain",
                "actions": [
                    "Exclusive early access to new products",
                    "VIP loyalty rewards program",
                    "Personal account manager",
                    "Referral program with premium incentives"
                ],
                "channels": ["Email", "Personal calls", "WhatsApp"],
                "frequency": "Weekly engagement"
            },
            "Loyal Customers": {
                "strategy": "Upsell and cross-sell",
                "actions": [
                    "Product recommendations based on history",
                    "Bundle offers",
                    "Loyalty points program",
                    "Early sale access"
                ],
                "channels": ["Email", "SMS", "App notifications"],
                "frequency": "Bi-weekly"
            },
            "Potential Loyalists": {
                "strategy": "Convert to loyal",
                "actions": [
                    "Membership/subscription offers",
                    "Product education content",
                    "Feedback requests",
                    "Second purchase discount"
                ],
                "channels": ["Email", "Retargeting ads"],
                "frequency": "Weekly"
            },
            "New Customers": {
                "strategy": "Onboard and nurture",
                "actions": [
                    "Welcome series emails",
                    "Product usage tips",
                    "First review request",
                    "Related product suggestions"
                ],
                "channels": ["Email", "In-app guides"],
                "frequency": "First 30 days intensive"
            },
            "At Risk": {
                "strategy": "Win back urgently",
                "actions": [
                    "Personal outreach call",
                    "Win-back discount offer",
                    "Survey to understand issues",
                    "Showcase new products/features"
                ],
                "channels": ["Phone", "Email", "SMS"],
                "frequency": "Immediate action required"
            },
            "Can't Lose": {
                "strategy": "Aggressive retention",
                "actions": [
                    "CEO/Manager personal call",
                    "Special pricing negotiation",
                    "Dedicated support",
                    "Custom solutions"
                ],
                "channels": ["Personal meetings", "Phone"],
                "frequency": "Immediate priority"
            },
            "Hibernating": {
                "strategy": "Reactivation campaign",
                "actions": [
                    "Re-engagement email series",
                    "Special comeback offer",
                    "Show what they're missing",
                    "Easy re-order options"
                ],
                "channels": ["Email", "Retargeting"],
                "frequency": "Monthly"
            },
            "Lost": {
                "strategy": "Low-cost reactivation",
                "actions": [
                    "Final win-back offer",
                    "Survey for feedback",
                    "Remove from active campaigns",
                    "Occasional big promotions only"
                ],
                "channels": ["Email only"],
                "frequency": "Quarterly"
            }
        }
        
        return recommendations.get(segment, {
            "strategy": "Standard engagement",
            "actions": ["Regular marketing communications"],
            "channels": ["Email"],
            "frequency": "Monthly"
        })


# API Functions
def run_customer_segmentation() -> Dict[str, Any]:
    """Run customer segmentation analysis"""
    model = CustomerSegmentation()
    return model.train()


def get_customer_segment(customer: str = None) -> Dict[str, Any]:
    """Get customer segment"""
    model = CustomerSegmentation()
    return model.predict(customer)


def get_segment_recommendations(segment: str) -> Dict[str, Any]:
    """Get recommendations for a segment"""
    model = CustomerSegmentation()
    return model.get_segment_recommendations(segment)
