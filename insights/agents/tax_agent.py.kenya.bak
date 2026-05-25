# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Tax Intelligence Agent
Specialized AI agent for Kenya Corporate Tax dashboard insights
"""

from typing import Dict, List, Optional

from insights.agents.base import BaseIntelligenceAgent
from insights.agents.registry import AgentRegistry


@AgentRegistry.register("Tax")
class TaxIntelligenceAgent(BaseIntelligenceAgent):
    """AI agent specialized for Kenya Tax Intelligence dashboard"""
    
    dashboard_type = "Tax"
    agent_name = "Tax Intelligence Agent"
    description = "AI assistant for Kenya corporate tax planning, compliance, and optimization"
    
    def compress_context(self, full_context: Dict) -> Dict:
        """Compress tax-specific context"""
        compressed = {
            "summary": self._extract_summary(full_context),
            "tax_overview": self._extract_tax_overview(full_context),
            "expense_classification": self._extract_expense_classification(full_context),
            "capital_allowances": self._extract_capital_allowances(full_context),
            "kra_schedule": self._extract_kra_schedule(full_context),
            "wht_analysis": self._extract_wht_analysis(full_context),
            "optimization_insights": self._extract_optimization(full_context),
            "period": full_context.get("fiscal_year", {}).get("name", "Current FY")
        }
        return compressed
    
    def _extract_tax_overview(self, context: Dict) -> Dict:
        """Extract tax overview metrics"""
        overview = {}
        overview_data = context.get("tax_overview", {})
        
        key_metrics = [
            "total_revenue", "total_expenses", "gross_profit",
            "allowable_expenses", "non_allowable_expenses", "add_backs",
            "capital_allowances", "taxable_income", "corporate_tax_rate",
            "tax_liability", "instalments_paid", "net_tax_position",
            "effective_tax_rate"
        ]
        
        for key in key_metrics:
            if key in overview_data:
                overview[key] = overview_data[key]
        
        return overview
    
    def _extract_expense_classification(self, context: Dict) -> Dict:
        """Extract expense classification data"""
        expense_data = context.get("expense_analysis", {})
        
        return {
            "total_allowable": expense_data.get("total_allowable", 0),
            "total_non_allowable": expense_data.get("total_non_allowable", 0),
            "non_allowable_items": expense_data.get("non_allowable_expenses", [])[:10],
            "add_back_amount": expense_data.get("add_back_amount", 0)
        }
    
    def _extract_capital_allowances(self, context: Dict) -> Dict:
        """Extract capital allowances data"""
        ca_data = context.get("capital_allowances", {})
        
        return {
            "total_allowances": ca_data.get("total_allowances", 0),
            "total_wear_tear": ca_data.get("total_wear_tear", 0),
            "total_investment_deduction": ca_data.get("total_investment_deduction", 0),
            "asset_count": ca_data.get("asset_count", 0),
            "by_category": ca_data.get("by_category", [])[:5]
        }
    
    def _extract_kra_schedule(self, context: Dict) -> Dict:
        """Extract KRA instalment schedule"""
        kra_data = context.get("kra_schedule", {})
        
        return {
            "instalments": kra_data.get("instalments", []),
            "total_annual_tax": kra_data.get("total_annual_tax", 0),
            "total_paid": kra_data.get("total_paid", 0),
            "total_balance": kra_data.get("total_balance", 0),
            "compliance_status": kra_data.get("compliance_status", "Unknown"),
            "next_payment": kra_data.get("next_payment"),
            "overdue_count": kra_data.get("overdue_count", 0)
        }
    
    def _extract_wht_analysis(self, context: Dict) -> Dict:
        """Extract WHT analysis data"""
        wht_data = context.get("wht_analysis", {})
        
        return {
            "total_wht_deducted": wht_data.get("total_wht_deducted", 0),
            "total_wht_suffered": wht_data.get("total_wht_suffered", 0),
            "wht_liability_balance": wht_data.get("wht_liability_balance", 0),
            "top_suppliers": wht_data.get("wht_deducted_by_supplier", [])[:5]
        }
    
    def _extract_optimization(self, context: Dict) -> List[Dict]:
        """Extract optimization insights"""
        insights = context.get("optimization_insights", [])
        return insights[:5]
    
    def _get_default_system_prompt(self, context: Optional[Dict] = None) -> str:
        """Get default system prompt for tax agent"""
        ctx_str = ""
        if context:
            import json
            ctx_str = json.dumps(context, indent=2, default=str)
        
        return f"""You are a specialized Kenya Corporate Tax Intelligence AI assistant for ERPNext.

## Your Expertise:
- Kenya Income Tax Act interpretation and compliance
- Corporate tax computation (30% rate)
- Allowable vs non-allowable expense classification
- Capital allowances (wear & tear, investment deduction)
- KRA quarterly instalment compliance (Section 12A)
- Withholding Tax (WHT) regulations
- Tax planning and optimization strategies
- Transfer pricing considerations

## Kenya Tax Rates Reference:
- Corporate Tax: 30%
- Wear & Tear: Class I (37.5%), Class II (30%), Class III (25%), Class IV (12.5%)
- Investment Deduction: 100% first year for qualifying manufacturing assets
- WHT Rates: Dividends 5%/15%, Interest 15%, Management Fees 5%, Contractors 3%
- KRA Instalments: Due 20th of 4th, 6th, 9th, 12th month of accounting period

## Current Dashboard Data:
{ctx_str if ctx_str else "No data available"}

## Guidelines:
- Reference specific Kenya Income Tax Act sections where applicable
- Calculate potential tax savings with concrete amounts
- Highlight compliance risks and KRA deadlines
- Suggest legitimate tax planning strategies
- Explain expense disallowance reasons clearly
- Recommend capital investment timing for optimal allowances
- Use KES for all monetary amounts
- Format numbers with thousands separators

## Response Format:
- Start with tax position summary
- Highlight compliance issues (overdue instalments, WHT remittance)
- Quantify optimization opportunities
- Recommend 2-3 specific actions with expected tax savings"""
    
    def _get_default_quick_actions(self) -> List[Dict]:
        """Get default quick actions for tax dashboard"""
        return [
            {
                "label": "📊 Tax Position",
                "prompt_template": "What is my current corporate tax position? Summarize taxable income, tax liability, and instalments paid.",
                "icon": "calculator"
            },
            {
                "label": "🚫 Non-Allowable Expenses",
                "prompt_template": "Which of my expenses are non-allowable for tax purposes? Explain why and how I can restructure them.",
                "icon": "x-circle"
            },
            {
                "label": "🏭 Capital Allowances",
                "prompt_template": "Am I maximizing my capital allowances? Which assets qualify for wear & tear or investment deduction?",
                "icon": "building"
            },
            {
                "label": "📅 KRA Instalments",
                "prompt_template": "What is my KRA instalment status? Are any payments overdue? What's due next?",
                "icon": "calendar"
            },
            {
                "label": "💰 Tax Savings",
                "prompt_template": "What tax optimization opportunities exist? How much can I potentially save and what actions should I take?",
                "icon": "trending-down"
            },
            {
                "label": "📑 WHT Compliance",
                "prompt_template": "Am I compliant with WHT obligations? What's my WHT position and when is remittance due?",
                "icon": "file-text"
            }
        ]
    
    def _get_default_routing_keywords(self) -> List[str]:
        """Get default routing keywords for tax queries"""
        return [
            "tax", "corporate tax", "income tax", "kra", "kenya revenue",
            "allowable", "non-allowable", "deductible", "expense",
            "capital allowance", "wear and tear", "depreciation",
            "investment deduction", "instalment", "quarterly",
            "withholding", "wht", "tax planning", "tax savings",
            "taxable income", "effective rate", "fiscal year"
        ]
