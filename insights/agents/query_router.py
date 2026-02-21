# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Query Router for Cross-Dashboard Intelligence
Routes queries to the appropriate dashboard agent based on content analysis
"""

import re
from typing import Dict, List, Optional, Tuple

import frappe


class QueryRouter:
    """
    Routes user queries to the appropriate dashboard agent.
    Uses keyword matching and scoring to determine the best agent for a query.
    """
    
    # Dashboard routing keywords with weights
    DASHBOARD_KEYWORDS = {
        "Executive": {
            "high": ["CEO", "executive", "board", "strategy", "KPI", "performance", "summary", "overview", 
                     "health", "score", "business performance", "company performance", "overall", 
                     "cross-departmental", "enterprise", "organization", "C-suite", "executive report",
                     "daily report", "weekly report", "monthly report", "business report", "management report",
                     "board report", "executive summary report", "automated report", "scheduled report"],
            "medium": ["strategic", "planning", "forecast", "governance", "leadership", "management",
                      "quarterly", "annual", "board meeting", "executive summary", "business review",
                      "report generation", "report scheduling", "email report", "PDF report"],
            "low": ["dashboard", "report", "metrics", "analytics", "intelligence", "insights", "delivery",
                   "notification", "alert", "automation", "schedule", "distribution"]
        },
        "Sales": {
            "high": ["revenue", "sales invoice", "sales order", "selling", "quota", "sales target"],
            "medium": ["sales", "sold", "order", "invoice", "customer order", "deal", "pipeline", "rep", "representative"],
            "low": ["product", "item", "price", "discount", "customer"]
        },
        "Risk": {
            "high": ["risk", "credit limit", "overdue", "compliance", "kra", "bad debt", "exposure"],
            "medium": ["credit", "default", "audit", "fraud", "anomaly", "violation", "penalty"],
            "low": ["payment", "outstanding", "late", "due"]
        },
        "Inventory": {
            "high": ["stock", "inventory", "warehouse", "reorder point", "stockout", "dead stock"],
            "medium": ["bin", "turnover", "abc analysis", "xyz", "fifo", "aging stock", "excess"],
            "low": ["item", "quantity", "storage", "transfer"]
        },
        "Procurement": {
            "high": ["supplier", "vendor", "procurement", "purchase order", "sourcing"],
            "medium": ["purchase", "buying", "spend", "contract", "lead time", "supplier performance"],
            "low": ["cost", "price", "order", "delivery"]
        },
        "Financial": {
            "high": ["profit and loss", "p&l", "cash flow", "financial ratio", "balance sheet"],
            "medium": ["profit", "loss", "receivable", "payable", "liquidity", "margin", "budget"],
            "low": ["tax", "vat", "expense", "income", "forex", "currency"]
        },
        "Customer": {
            "high": ["customer lifetime value", "clv", "churn", "customer segment", "retention"],
            "medium": ["customer", "client", "cohort", "loyalty", "nps", "satisfaction"],
            "low": ["buyer", "account", "contact", "territory"]
        },
        "HR": {
            "high": ["employee", "staff", "workforce", "headcount", "attrition", "turnover", "retention", 
                     "payroll", "salary", "compensation", "hiring", "recruitment", "HR", "human resources", 
                     "talent", "attendance", "leave", "training", "performance", "engagement"],
            "medium": ["department", "team", "manager", "supervisor", "promotion", "career", "development",
                      "skills", "competency", "appraisal", "review", "diversity", "inclusion", "benefits"],
            "low": ["employee satisfaction", "work-life balance", "productivity", "absenteeism", "policy"]
        },
        "ESG": {
            "high": ["esg", "environmental", "social", "governance", "sustainability", "carbon", "emissions",
                     "renewable energy", "diversity", "inclusion", "compliance", "ethics", "corporate responsibility",
                     "sustainable", "green", "carbon footprint", "greenhouse gas", "esg score", "esg rating"],
            "medium": ["environment", "climate", "waste", "recycling", "water", "energy", "safety", "wellbeing",
                      "training", "community", "risk management", "transparency", "audit", "board", "stakeholder"],
            "low": ["impact", "responsibility", "policy", "framework", "standard", "benchmark", "target", "goal"]
        },
        "Budget": {
            "high": ["budget variance", "budget vs actual", "variance analysis", "overspend", "underspend",
                     "budget control", "forecast accuracy", "budget planning", "variance reporting", "budget deviation",
                     "spending variance", "budget performance", "actual vs budget", "budget monitoring"],
            "medium": ["budget", "variance", "actual", "forecast", "planning", "spending", "allocation", "deviation",
                      "budget utilization", "forecast error", "budget review", "financial planning", "cost control",
                      "expense management", "budget tracking", "variance threshold", "budget alerts"],
            "low": ["spend", "cost", "expense", "allocation", "monitoring", "control", "financial", "planning"]
        },
        "Hotel": {
            "high": ["hotel", "occupancy", "revpar", "adr", "average daily rate", "revenue per available room",
                     "check-in", "checkout", "night audit", "housekeeping", "room rate", "goppar",
                     "front desk", "reservation", "revpash", "banquet", "event hall"],
            "medium": ["room", "guest", "booking", "bed", "meal plan", "concierge", "amenity", "vip",
                       "loyalty", "arrivals", "departures", "room type", "suite", "minibar",
                       "room service", "folio", "no show", "overbooking", "channel manager"],
            "low": ["stay", "accommodation", "hospitality", "check out", "property", "reception"]
        }
    }
    
    # Weight multipliers
    WEIGHT_MULTIPLIERS = {
        "high": 3,
        "medium": 2,
        "low": 1
    }
    
    def __init__(self):
        self._load_custom_keywords()
    
    def _load_custom_keywords(self):
        """Load custom keywords from Dashboard AI Agent Config"""
        try:
            for dtype in self.DASHBOARD_KEYWORDS.keys():
                if frappe.db.exists("Dashboard AI Agent Config", dtype):
                    config = frappe.get_doc("Dashboard AI Agent Config", dtype)
                    custom_keywords = config.get_routing_keywords()
                    if custom_keywords:
                        # Add custom keywords to medium priority
                        if "medium" not in self.DASHBOARD_KEYWORDS[dtype]:
                            self.DASHBOARD_KEYWORDS[dtype]["medium"] = []
                        self.DASHBOARD_KEYWORDS[dtype]["medium"].extend(custom_keywords)
        except Exception:
            pass  # Use defaults if config not available
    
    def route_query(
        self,
        query: str,
        current_dashboard: str
    ) -> Dict:
        """
        Route a query to the appropriate dashboard.
        
        Args:
            query: User's question
            current_dashboard: The dashboard the user is currently on
            
        Returns:
            Dict with:
                - target_dashboard: Recommended dashboard for this query
                - confidence: Confidence score (0-1)
                - redirect_suggested: Whether to redirect
                - reason: Explanation for the routing decision
                - scores: Raw scores for each dashboard
        """
        query_lower = query.lower()
        scores = self._calculate_scores(query_lower)
        
        # Get the best matching dashboard
        best_match = max(scores, key=scores.get)
        best_score = scores[best_match]
        current_score = scores.get(current_dashboard, 0)
        
        # Calculate confidence (normalize to 0-1)
        total_score = sum(scores.values())
        confidence = best_score / total_score if total_score > 0 else 0
        
        # Determine if redirect is needed
        # Redirect if:
        # 1. Best match is different from current
        # 2. Best match has significantly higher score (at least 50% more)
        # 3. Confidence is above threshold (0.3)
        redirect_suggested = (
            best_match != current_dashboard and
            best_score > current_score * 1.5 and
            confidence > 0.3
        )
        
        # Generate reason
        if redirect_suggested:
            top_keywords = self._get_matched_keywords(query_lower, best_match)
            reason = f"Your question about '{', '.join(top_keywords[:3])}' is better suited for the {best_match} Intelligence dashboard."
        elif best_match == current_dashboard:
            reason = f"This question is well-suited for the {current_dashboard} Intelligence dashboard."
        else:
            reason = f"Answering from {current_dashboard} Intelligence, though {best_match} may have additional context."
        
        return {
            "target_dashboard": best_match,
            "confidence": round(confidence, 2),
            "redirect_suggested": redirect_suggested,
            "reason": reason,
            "scores": scores,
            "current_dashboard": current_dashboard
        }
    
    def _calculate_scores(self, query_lower: str) -> Dict[str, int]:
        """Calculate relevance scores for each dashboard"""
        scores = {}
        
        for dashboard, keyword_groups in self.DASHBOARD_KEYWORDS.items():
            score = 0
            for priority, keywords in keyword_groups.items():
                multiplier = self.WEIGHT_MULTIPLIERS.get(priority, 1)
                for keyword in keywords:
                    if keyword.lower() in query_lower:
                        # Give bonus for exact phrase match
                        if f" {keyword.lower()} " in f" {query_lower} ":
                            score += multiplier * 2
                        else:
                            score += multiplier
            scores[dashboard] = score
        
        return scores
    
    def _get_matched_keywords(self, query_lower: str, dashboard: str) -> List[str]:
        """Get keywords that matched for a dashboard"""
        matched = []
        keyword_groups = self.DASHBOARD_KEYWORDS.get(dashboard, {})
        
        for priority, keywords in keyword_groups.items():
            for keyword in keywords:
                if keyword.lower() in query_lower:
                    matched.append(keyword)
        
        return matched
    
    def detect_cross_domain_query(self, query: str) -> Tuple[bool, List[str]]:
        """
        Detect if a query spans multiple domains.
        
        Args:
            query: User's question
            
        Returns:
            Tuple of (is_cross_domain, list of relevant dashboards)
        """
        query_lower = query.lower()
        scores = self._calculate_scores(query_lower)
        
        # Filter dashboards with significant scores
        threshold = max(scores.values()) * 0.5 if scores else 0
        relevant_dashboards = [d for d, s in scores.items() if s >= threshold and s > 0]
        
        is_cross_domain = len(relevant_dashboards) > 1
        
        return is_cross_domain, relevant_dashboards
    
    def get_dashboard_description(self, dashboard_type: str) -> str:
        """Get a brief description of what a dashboard covers"""
        descriptions = {
            "Executive": "C-suite overview, business health score, cross-departmental KPIs, and strategic insights",
            "Sales": "revenue analysis, sales performance, customer orders, and sales forecasting",
            "Risk": "credit risk, compliance, overdue payments, and anomaly detection",
            "Inventory": "stock levels, warehouse management, turnover analysis, and reorder optimization",
            "Procurement": "supplier management, purchasing, spend analysis, and vendor performance",
            "Financial": "profit & loss, cash flow, financial ratios, and tax compliance",
            "Customer": "customer lifetime value, churn analysis, segmentation, and retention",
            "HR": "workforce analytics, talent management, employee retention, and payroll optimization",
			"ESG": "environmental impact, social responsibility, governance compliance, and sustainability reporting",
			"Budget": "budget variance analysis, forecast accuracy, spending control, and financial planning optimization",
            "Hotel": "hotel occupancy analytics, RevPAR, guest intelligence, revenue management, and F&B operations"
        }
        return descriptions.get(dashboard_type, f"{dashboard_type} intelligence and analytics")


# Singleton instance
_router_instance: Optional[QueryRouter] = None


def get_query_router() -> QueryRouter:
    """Get or create the query router singleton"""
    global _router_instance
    if _router_instance is None:
        _router_instance = QueryRouter()
    return _router_instance


def route_query(query: str, current_dashboard: str) -> Dict:
    """Convenience function to route a query"""
    router = get_query_router()
    return router.route_query(query, current_dashboard)
