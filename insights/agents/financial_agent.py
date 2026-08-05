# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Financial Intelligence Agent
Specialized AI agent for Financial dashboard insights
"""

from typing import Dict, List, Optional

from insights.agents.base import BaseIntelligenceAgent
from insights.agents.registry import AgentRegistry


@AgentRegistry.register("Financial")
class FinancialIntelligenceAgent(BaseIntelligenceAgent):
    """AI agent specialized for Financial Intelligence dashboard"""
    
    dashboard_type = "Financial"
    agent_name = "Financial Intelligence Agent"
    description = "AI assistant for P&L analysis, cash flow management, and financial health monitoring"
    
    def compress_context(self, full_context: Dict) -> Dict:
        """Compress financial-specific context"""
        compressed = {
            "summary": self._extract_summary(full_context),
            "pl_metrics": self._extract_pl_metrics(full_context),
            "cash_flow": self._extract_cash_flow(full_context),
            "receivables_payables": self._extract_receivables_payables(full_context),
            "financial_ratios": self._extract_ratios(full_context),
            "tax_status": self._extract_tax_status(full_context),
            "alerts": self._extract_alerts(full_context),
            "period": full_context.get("period", "Current Period")
        }
        return compressed
    
    def _extract_pl_metrics(self, context: Dict) -> Dict:
        """Extract P&L metrics"""
        pl = {}
        pl_keys = [
            "revenue", "gross_profit", "net_profit", "operating_income",
            "gross_margin", "net_margin", "operating_margin", "ebitda",
            "total_expenses", "cost_of_goods_sold", "cogs"
        ]
        
        for key in pl_keys:
            if key in context:
                pl[key] = context[key]
        
        if "pl_summary" in context and isinstance(context["pl_summary"], dict):
            pl.update(context["pl_summary"])
        
        return pl
    
    def _extract_cash_flow(self, context: Dict) -> Dict:
        """Extract cash flow data"""
        cash = {}
        cash_keys = [
            "cash_balance", "cash_inflow", "cash_outflow", "net_cash_flow",
            "operating_cash_flow", "free_cash_flow", "cash_runway"
        ]
        
        for key in cash_keys:
            if key in context:
                cash[key] = context[key]
        
        if "cash_flow" in context and isinstance(context["cash_flow"], dict):
            cash.update(context["cash_flow"])
        
        return cash
    
    def _extract_receivables_payables(self, context: Dict) -> Dict:
        """Extract AR/AP data"""
        ar_ap = {}
        
        if "accounts_receivable" in context:
            ar_ap["receivables"] = context["accounts_receivable"]
        if "accounts_payable" in context:
            ar_ap["payables"] = context["accounts_payable"]
        if "dso" in context:
            ar_ap["dso"] = context["dso"]
        if "dpo" in context:
            ar_ap["dpo"] = context["dpo"]
        if "working_capital" in context:
            ar_ap["working_capital"] = context["working_capital"]
        
        return ar_ap
    
    def _extract_ratios(self, context: Dict) -> Dict:
        """Extract financial ratios"""
        ratios = {}
        ratio_keys = [
            "current_ratio", "quick_ratio", "debt_to_equity",
            "return_on_equity", "roe", "return_on_assets", "roa",
            "asset_turnover", "inventory_turnover"
        ]
        
        for key in ratio_keys:
            if key in context:
                ratios[key] = context[key]
        
        if "ratios" in context and isinstance(context["ratios"], dict):
            ratios.update(context["ratios"])
        
        return ratios
    
    def _extract_tax_status(self, context: Dict) -> Dict:
        """Extract tax compliance status (GST/TDS focus)"""
        tax = {}
        
        if "gst_status" in context:
            tax["gst"] = context["gst_status"]
        if "tax_payable" in context:
            tax["payable"] = context["tax_payable"]
        if "gst_compliance" in context:
            tax["gst_compliance"] = context["gst_compliance"]
        if "withholding_tax" in context:
            tax["tds"] = context["withholding_tax"]
        
        return tax
    
    def _get_default_system_prompt(self, context: Optional[Dict] = None) -> str:
        """Get default system prompt for financial agent"""
        ctx_str = ""
        if context:
            import json
            ctx_str = json.dumps(context, indent=2, default=str)
        
        return f"""You are a specialized Financial Intelligence AI assistant for ERPNext.

## Your Expertise:
- Profit & Loss analysis and margin optimization
- Cash flow forecasting and management
- Accounts receivable and payable analysis
- Financial ratio analysis (liquidity, profitability, efficiency)
- Tax compliance including India GST (CGST/SGST/IGST) and TDS
- Budget variance analysis
- Working capital management

## Current Dashboard Data:
{ctx_str if ctx_str else "No data available"}

## Guidelines:
- Provide specific financial insights and recommendations
- Reference actual financial figures, ratios, and trends
- Identify areas of financial concern or opportunity
- Suggest strategies for improving financial performance
- Explain financial metrics in business terms
- Consider tax implications (GST rates, TDS sections, filing deadlines)
- Highlight cash flow risks and opportunities
- Use markdown formatting with bullet points for clarity

## Response Format:
- Start with overall financial health assessment
- Highlight key metrics and their implications
- Identify risks and opportunities
- Recommend 2-3 specific actions for financial improvement"""
    
    def _get_default_quick_actions(self) -> List[Dict]:
        """Get default quick actions for financial dashboard"""
        return [
            {
                "label": "📈 P&L Summary",
                "prompt_template": "Provide a summary of our P&L performance. What are the key insights and areas of concern?",
                "icon": "file-text"
            },
            {
                "label": "💵 Cash Flow Status",
                "prompt_template": "What is our current cash flow situation? Forecast for the next 30 days and highlight any risks.",
                "icon": "dollar-sign"
            },
            {
                "label": "📊 Financial Ratios",
                "prompt_template": "Analyze our key financial ratios. How do they compare to healthy benchmarks?",
                "icon": "activity"
            },
            {
                "label": "🧾 Tax Compliance",
                "prompt_template": "What is our GST and TDS compliance status? Any pending GSTR-1/GSTR-3B filings or obligations?",
                "icon": "file-check"
            },
            {
                "label": "💳 Working Capital",
                "prompt_template": "Analyze our working capital position. How can we optimize AR/AP to improve cash flow?",
                "icon": "credit-card"
            }
        ]
    
    def _get_default_routing_keywords(self) -> List[str]:
        """Get default routing keywords for financial queries"""
        return [
            "profit", "loss", "p&l", "cash flow", "receivable", "payable",
            "liquidity", "margin", "budget", "tax", "gst", "tds", "gstr",
            "ratio", "revenue", "expense", "income", "balance sheet",
            "working capital", "forex", "currency"
        ]
