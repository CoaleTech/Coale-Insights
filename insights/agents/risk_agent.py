# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Risk Intelligence Agent
Specialized AI agent for Risk dashboard insights
"""

from typing import Dict, List, Optional

from insights.agents.base import BaseIntelligenceAgent
from insights.agents.registry import AgentRegistry


@AgentRegistry.register("Risk")
class RiskIntelligenceAgent(BaseIntelligenceAgent):
    """AI agent specialized for Risk Intelligence dashboard"""
    
    dashboard_type = "Risk"
    agent_name = "Risk Intelligence Agent"
    description = "AI assistant for risk assessment, compliance monitoring, and anomaly detection"
    
    def compress_context(self, full_context: Dict) -> Dict:
        """Compress risk-specific context"""
        compressed = {
            "summary": self._extract_summary(full_context),
            "credit_risk": self._extract_credit_risk(full_context),
            "compliance_status": self._extract_compliance(full_context),
            "overdue_analysis": self._extract_overdue(full_context),
            "anomalies": self._extract_anomalies(full_context),
            "risk_scores": self._extract_risk_scores(full_context),
            "alerts": self._extract_alerts(full_context),
            "period": full_context.get("period", "Current Period")
        }
        return compressed
    
    def _extract_credit_risk(self, context: Dict) -> Dict:
        """Extract credit risk metrics"""
        risk = {}
        credit_keys = [
            "total_exposure", "credit_exposure", "credit_utilized",
            "customers_over_limit", "high_risk_customers", "credit_limit_breaches"
        ]
        
        for key in credit_keys:
            if key in context:
                risk[key] = context[key]
        
        if "credit_risk" in context and isinstance(context["credit_risk"], dict):
            risk.update(context["credit_risk"])
        
        return risk
    
    def _extract_compliance(self, context: Dict) -> Dict:
        """Extract compliance status"""
        compliance = {}
        compliance_keys = [
            "gst_status", "regulatory_status",
            "pending_filings", "compliance_score", "violations"
        ]
        
        for key in compliance_keys:
            if key in context:
                compliance[key] = context[key]
        
        if "compliance" in context and isinstance(context["compliance"], dict):
            compliance.update(context["compliance"])
        
        return compliance
    
    def _extract_overdue(self, context: Dict) -> Dict:
        """Extract overdue payment analysis"""
        overdue = {}
        overdue_keys = [
            "total_overdue", "overdue_amount", "overdue_count",
            "aging_buckets", "days_sales_outstanding", "dso",
            "overdue_by_customer", "collection_rate"
        ]
        
        for key in overdue_keys:
            if key in context:
                overdue[key] = context[key]
        
        return overdue
    
    def _extract_anomalies(self, context: Dict) -> List[Dict]:
        """Extract detected anomalies"""
        anomalies = []
        
        if "anomalies" in context:
            anomaly_data = context["anomalies"]
            if isinstance(anomaly_data, list):
                anomalies = anomaly_data[:5]
        
        if "suspicious_transactions" in context:
            anomalies.extend(context["suspicious_transactions"][:3])
        
        return anomalies
    
    def _extract_risk_scores(self, context: Dict) -> Dict:
        """Extract risk scores by category"""
        scores = {}
        score_keys = [
            "overall_risk_score", "credit_risk_score", "operational_risk_score",
            "compliance_risk_score", "liquidity_risk_score"
        ]
        
        for key in score_keys:
            if key in context:
                scores[key] = context[key]
        
        return scores
    
    def _get_default_system_prompt(self, context: Optional[Dict] = None) -> str:
        """Get default system prompt for risk agent"""
        ctx_str = ""
        if context:
            import json
            ctx_str = json.dumps(context, indent=2, default=str)
        
        return f"""You are a specialized Risk Intelligence AI assistant for ERPNext.

## Your Expertise:
- Credit risk assessment and management
- Overdue payment analysis and collection priorities
- Compliance monitoring (GST filing status, e-Invoice coverage, GST/PAN registration)
- Operational risk identification
- Anomaly detection in transactions
- Cash flow risk analysis
- Fraud detection indicators

## Current Dashboard Data:
{ctx_str if ctx_str else "No data available"}

## Guidelines:
- Prioritize risks by severity and potential financial impact
- Provide actionable mitigation strategies for identified risks
- Reference specific overdue amounts, credit limits, and compliance issues
- Explain risk indicators and their business implications
- Suggest preventive measures and monitoring approaches
- Be specific about which customers or transactions need attention
- Use markdown formatting with bullet points for clarity
- Highlight urgent issues that require immediate action

## Response Format:
- Start with severity assessment (Critical/High/Medium/Low)
- Provide specific data points supporting the assessment
- List affected customers/transactions when relevant
- Recommend 2-3 specific actions to mitigate risks"""
    
    def _get_default_quick_actions(self) -> List[Dict]:
        """Get default quick actions for risk dashboard"""
        return [
            {
                "label": "🔴 Critical Risks",
                "prompt_template": "What are the most critical risks requiring immediate attention? Prioritize by potential financial impact.",
                "icon": "alert-circle"
            },
            {
                "label": "💳 Credit Exposure",
                "prompt_template": "Analyze our current credit exposure. Which customers are over their credit limits?",
                "icon": "credit-card"
            },
            {
                "label": "📋 Compliance Status",
                "prompt_template": "What is our current GST compliance status? Are there any pending GSTR-1/GSTR-3B filings or e-Invoice issues?",
                "icon": "clipboard-check"
            },
            {
                "label": "🔍 Anomalies",
                "prompt_template": "Are there any unusual patterns or anomalies in recent transactions that could indicate fraud or errors?",
                "icon": "search"
            },
            {
                "label": "📅 Overdue Analysis",
                "prompt_template": "Analyze overdue payments. Which accounts should be prioritized for collection?",
                "icon": "calendar"
            }
        ]
    
    def _get_default_routing_keywords(self) -> List[str]:
        """Get default routing keywords for risk queries"""
        return [
            "risk", "credit", "overdue", "compliance", "kra", "exposure",
            "default", "bad debt", "anomaly", "fraud", "audit", "violation",
            "penalty", "collection", "aging", "dso", "suspicious"
        ]
