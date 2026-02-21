# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
from typing import Dict, List, Optional

import frappe
from frappe.model.document import Document


# Default system prompts for each dashboard type
DEFAULT_SYSTEM_PROMPTS = {
    "Sales": """You are a specialized Sales Intelligence AI assistant for ERPNext.

## Your Expertise:
- Revenue analysis, trends, and forecasting
- Sales representative performance evaluation
- Customer purchase patterns and order analysis
- Cash vs credit sales optimization
- Month-over-month and year-over-year comparisons
- Sales pipeline and conversion metrics

## Guidelines:
- Provide specific, actionable recommendations based on the sales data shown
- Reference actual revenue numbers, growth percentages, and trends from the dashboard
- Explain sales anomalies and their potential business impact
- Suggest strategies to improve sales performance
- Use markdown formatting with bullet points for clarity
- When asked about non-sales topics, acknowledge and suggest the appropriate dashboard

## Current Dashboard Context:
{context}""",

    "Risk": """You are a specialized Risk Intelligence AI assistant for ERPNext.

## Your Expertise:
- Credit risk assessment and management
- Overdue payment analysis and collection priorities
- Compliance monitoring (including KRA tax compliance)
- Operational risk identification
- Anomaly detection in transactions
- Cash flow risk analysis

## Guidelines:
- Prioritize risks by severity and potential financial impact
- Provide actionable mitigation strategies for identified risks
- Reference specific overdue amounts, credit limits, and compliance issues
- Explain risk indicators and their business implications
- Suggest preventive measures and monitoring approaches
- Use markdown formatting with bullet points for clarity

## Current Dashboard Context:
{context}""",

    "Inventory": """You are a specialized Inventory Intelligence AI assistant for ERPNext.

## Your Expertise:
- Stock level optimization and reorder point analysis
- ABC/XYZ classification and inventory segmentation
- Inventory turnover and days of inventory analysis
- Warehouse utilization and transfer recommendations
- FIFO aging and obsolescence risk assessment
- Dead stock identification and clearance strategies

## Guidelines:
- Provide specific recommendations for stock optimization
- Reference actual stock levels, turnover rates, and aging data
- Identify items requiring immediate attention (stockouts, excess)
- Suggest reorder quantities based on demand patterns
- Explain inventory metrics and their business impact
- Use markdown formatting with bullet points for clarity

## Current Dashboard Context:
{context}""",

    "Procurement": """You are a specialized Procurement Intelligence AI assistant for ERPNext.

## Your Expertise:
- Supplier performance evaluation and scoring
- Spend analysis and cost optimization
- Purchase price variance and benchmarking
- Vendor consolidation opportunities
- Lead time analysis and reliability tracking
- Contract compliance and savings identification

## Guidelines:
- Provide actionable supplier recommendations
- Reference specific spend amounts, price variances, and supplier metrics
- Identify cost reduction opportunities
- Suggest supplier diversification or consolidation strategies
- Explain procurement KPIs and their implications
- Use markdown formatting with bullet points for clarity

## Current Dashboard Context:
{context}""",

    "Financial": """You are a specialized Financial Intelligence AI assistant for ERPNext.

## Your Expertise:
- Profit & Loss analysis and margin optimization
- Cash flow forecasting and management
- Accounts receivable and payable analysis
- Financial ratio analysis (liquidity, profitability, efficiency)
- Tax compliance including KRA VAT (16%)
- Budget variance analysis

## Guidelines:
- Provide specific financial insights and recommendations
- Reference actual financial figures, ratios, and trends
- Identify areas of financial concern or opportunity
- Suggest strategies for improving financial performance
- Explain financial metrics in business terms
- Use markdown formatting with bullet points for clarity

## Current Dashboard Context:
{context}""",

    "Customer": """You are a specialized Customer Intelligence AI assistant for ERPNext.

## Your Expertise:
- Customer Lifetime Value (CLV) analysis
- Churn prediction and prevention strategies
- Customer segmentation and targeting
- Cohort analysis and retention metrics
- Geographic and demographic analysis
- Customer health scoring and engagement

## Guidelines:
- Provide actionable customer retention strategies
- Reference specific CLV values, churn rates, and segment data
- Identify at-risk customers requiring attention
- Suggest personalized engagement approaches
- Explain customer metrics and their business implications
- Use markdown formatting with bullet points for clarity

## Current Dashboard Context:
{context}"""
}

# Default quick actions for each dashboard type
DEFAULT_QUICK_ACTIONS = {
    "Sales": [
        {"label": "📈 Analyze Revenue Trends", "prompt_template": "Analyze the current revenue trends and identify key growth drivers and concerns.", "icon": "trending-up"},
        {"label": "🏆 Top Performers", "prompt_template": "Who are the top performing sales reps and what can we learn from their success?", "icon": "award"},
        {"label": "📊 Forecast Next Month", "prompt_template": "Based on current trends, what is the sales forecast for next month?", "icon": "calendar"},
        {"label": "⚠️ Sales Alerts", "prompt_template": "What are the key sales alerts or concerns I should be aware of?", "icon": "alert-triangle"}
    ],
    "Risk": [
        {"label": "🔴 Critical Risks", "prompt_template": "What are the most critical risks requiring immediate attention?", "icon": "alert-circle"},
        {"label": "💳 Credit Exposure", "prompt_template": "Analyze our current credit exposure and recommend actions.", "icon": "credit-card"},
        {"label": "📋 Compliance Status", "prompt_template": "What is our current compliance status and are there any issues?", "icon": "clipboard-check"},
        {"label": "🔍 Anomalies", "prompt_template": "Are there any unusual patterns or anomalies in recent transactions?", "icon": "search"}
    ],
    "Inventory": [
        {"label": "📦 Stock Alerts", "prompt_template": "Which items need immediate attention due to low stock or overstock?", "icon": "package"},
        {"label": "🔄 Reorder Recommendations", "prompt_template": "What items should be reordered and in what quantities?", "icon": "refresh-cw"},
        {"label": "📉 Slow Moving Items", "prompt_template": "Identify slow-moving or dead stock items and suggest clearance strategies.", "icon": "trending-down"},
        {"label": "🏭 Warehouse Optimization", "prompt_template": "How can we optimize warehouse utilization and stock distribution?", "icon": "home"}
    ],
    "Procurement": [
        {"label": "⭐ Supplier Performance", "prompt_template": "How are our key suppliers performing and who needs attention?", "icon": "star"},
        {"label": "💰 Cost Savings", "prompt_template": "Where are the opportunities for cost savings in procurement?", "icon": "dollar-sign"},
        {"label": "📊 Spend Analysis", "prompt_template": "Analyze our spending patterns and identify optimization opportunities.", "icon": "pie-chart"},
        {"label": "⏱️ Lead Time Issues", "prompt_template": "Are there any supplier lead time issues affecting operations?", "icon": "clock"}
    ],
    "Financial": [
        {"label": "📈 P&L Summary", "prompt_template": "Provide a summary of our P&L performance and key insights.", "icon": "file-text"},
        {"label": "💵 Cash Flow Status", "prompt_template": "What is our current cash flow situation and forecast?", "icon": "dollar-sign"},
        {"label": "📊 Financial Ratios", "prompt_template": "Analyze our key financial ratios and their implications.", "icon": "activity"},
        {"label": "🧾 Tax Compliance", "prompt_template": "What is our tax compliance status, especially for KRA VAT?", "icon": "file-check"}
    ],
    "Customer": [
        {"label": "⚠️ At-Risk Customers", "prompt_template": "Which customers are at risk of churning and what should we do?", "icon": "alert-triangle"},
        {"label": "💎 Top Customers", "prompt_template": "Who are our most valuable customers and how do we retain them?", "icon": "gem"},
        {"label": "📊 Segment Analysis", "prompt_template": "Analyze our customer segments and their characteristics.", "icon": "users"},
        {"label": "📈 Growth Opportunities", "prompt_template": "Which customer segments or regions offer the best growth opportunities?", "icon": "trending-up"}
    ]
}

# Default routing keywords for each dashboard type
DEFAULT_ROUTING_KEYWORDS = {
    "Sales": ["revenue", "sales", "invoice", "order", "sold", "selling", "rep", "representative", "forecast", "target", "quota", "deal", "opportunity", "pipeline"],
    "Risk": ["risk", "credit", "overdue", "compliance", "kra", "exposure", "default", "bad debt", "anomaly", "fraud", "audit", "violation"],
    "Inventory": ["stock", "inventory", "warehouse", "reorder", "turnover", "abc", "xyz", "aging", "fifo", "dead stock", "stockout", "excess"],
    "Procurement": ["supplier", "vendor", "purchase", "procurement", "spend", "buying", "sourcing", "contract", "lead time", "price variance"],
    "Financial": ["profit", "loss", "p&l", "cash flow", "receivable", "payable", "ratio", "liquidity", "margin", "budget", "tax", "vat", "forex"],
    "Customer": ["customer", "client", "clv", "lifetime value", "churn", "retention", "segment", "cohort", "loyalty", "satisfaction", "nps"]
}

# Default context fields for each dashboard type
DEFAULT_CONTEXT_FIELDS = {
    "Sales": ["revenue_metrics", "top_products", "top_customers", "sales_trends", "rep_performance", "cash_credit_mix"],
    "Risk": ["credit_risk", "overdue_summary", "compliance_status", "anomalies", "exposure_by_customer", "aging_analysis"],
    "Inventory": ["stock_overview", "low_stock_items", "excess_stock", "turnover_metrics", "abc_classification", "warehouse_utilization"],
    "Procurement": ["spend_summary", "supplier_performance", "price_trends", "pending_orders", "lead_time_analysis"],
    "Financial": ["pl_summary", "cash_flow", "receivables", "payables", "financial_ratios", "tax_summary"],
    "Customer": ["customer_segments", "clv_distribution", "churn_risk", "top_customers", "geographic_analysis", "cohort_metrics"]
}


class DashboardAIAgentConfig(Document):
    # begin: auto-generated types
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        dashboard_type: DF.Literal["", "Sales", "Risk", "Inventory", "Procurement", "Financial", "Customer"]
        is_enabled: DF.Check
        model_preference: DF.Literal["auto", "meta-llama/llama-3.1-8b-instruct:free", "meta-llama/llama-3.1-70b-instruct", "anthropic/claude-3-haiku", "openai/gpt-4o-mini"]
        max_context_tokens: DF.Int
        system_prompt: DF.LongText | None
        quick_actions: DF.JSON | None
        routing_keywords: DF.JSON | None
        context_fields: DF.JSON | None
        temperature: DF.Float
        max_response_tokens: DF.Int
        include_conversation_history: DF.Check
    # end: auto-generated types

    def before_insert(self):
        """Set defaults before creating new config"""
        self._set_defaults()

    def validate(self):
        """Validate configuration"""
        valid_types = [
            "Sales", "Risk", "Inventory", "Procurement", "Financial",
            "Customer", "General", "HR", "Executive", "Tax",
            "Marketing", "ESG", "Budget Variance"
        ]
        if self.dashboard_type not in valid_types:
            frappe.throw("Invalid dashboard type")
        
        if self.temperature and (self.temperature < 0 or self.temperature > 1):
            frappe.throw("Temperature must be between 0 and 1")

    def _set_defaults(self):
        """Set default values based on dashboard type"""
        if not self.system_prompt and self.dashboard_type:
            self.system_prompt = DEFAULT_SYSTEM_PROMPTS.get(self.dashboard_type, "")
        
        if not self.quick_actions and self.dashboard_type:
            self.quick_actions = json.dumps(DEFAULT_QUICK_ACTIONS.get(self.dashboard_type, []))
        
        if not self.routing_keywords and self.dashboard_type:
            self.routing_keywords = json.dumps(DEFAULT_ROUTING_KEYWORDS.get(self.dashboard_type, []))
        
        if not self.context_fields and self.dashboard_type:
            self.context_fields = json.dumps(DEFAULT_CONTEXT_FIELDS.get(self.dashboard_type, []))

    def get_system_prompt(self, context: Dict = None) -> str:
        """Get the system prompt with context filled in"""
        prompt = self.system_prompt or DEFAULT_SYSTEM_PROMPTS.get(self.dashboard_type, "")
        
        if context:
            prompt = prompt.replace("{context}", json.dumps(context, indent=2))
        else:
            prompt = prompt.replace("{context}", "No context available")
        
        prompt = prompt.replace("{dashboard_type}", self.dashboard_type or "")
        
        quick_actions = self.get_quick_actions()
        actions_text = "\n".join([f"- {a['label']}" for a in quick_actions])
        prompt = prompt.replace("{quick_actions}", actions_text)
        
        return prompt

    def get_quick_actions(self) -> List[Dict]:
        """Get quick actions as a list"""
        if not self.quick_actions:
            return DEFAULT_QUICK_ACTIONS.get(self.dashboard_type, [])
        if isinstance(self.quick_actions, str):
            return json.loads(self.quick_actions)
        return self.quick_actions

    def get_routing_keywords(self) -> List[str]:
        """Get routing keywords as a list"""
        if not self.routing_keywords:
            return DEFAULT_ROUTING_KEYWORDS.get(self.dashboard_type, [])
        if isinstance(self.routing_keywords, str):
            return json.loads(self.routing_keywords)
        return self.routing_keywords

    def get_context_fields(self) -> List[str]:
        """Get context fields as a list"""
        if not self.context_fields:
            return DEFAULT_CONTEXT_FIELDS.get(self.dashboard_type, [])
        if isinstance(self.context_fields, str):
            return json.loads(self.context_fields)
        return self.context_fields

    @staticmethod
    def get_config(dashboard_type: str) -> Optional["DashboardAIAgentConfig"]:
        """Get configuration for a dashboard type, creating default if needed"""
        if frappe.db.exists("Dashboard AI Agent Config", dashboard_type):
            return frappe.get_doc("Dashboard AI Agent Config", dashboard_type)
        
        # Create default config
        config = frappe.get_doc({
            "doctype": "Dashboard AI Agent Config",
            "dashboard_type": dashboard_type,
            "is_enabled": 1
        })
        config.insert(ignore_permissions=True)
        return config

    @staticmethod
    def get_all_routing_keywords() -> Dict[str, List[str]]:
        """Get routing keywords for all dashboard types"""
        result = {}
        for dtype in ["Sales", "Risk", "Inventory", "Procurement", "Financial", "Customer"]:
            try:
                config = DashboardAIAgentConfig.get_config(dtype)
                result[dtype] = config.get_routing_keywords()
            except Exception:
                result[dtype] = DEFAULT_ROUTING_KEYWORDS.get(dtype, [])
        return result
