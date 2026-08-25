# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Tax Intelligence Agent
Specialized AI agent for India Tax Intelligence dashboard insights
"""

from typing import Dict, List, Optional

import frappe

from insights.agents.base import BaseIntelligenceAgent
from insights.agents.registry import AgentRegistry


@AgentRegistry.register("Tax")
class TaxIntelligenceAgent(BaseIntelligenceAgent):
    """AI agent specialized for India Tax Intelligence dashboard"""

    dashboard_type = "Tax"
    agent_name = "Tax Intelligence Agent"
    description = "AI assistant for India GST, ITC, TDS, e-Invoice compliance and tax planning"

    def compress_context(self, full_context: Dict) -> Dict:
        """Compress tax-specific context"""
        compressed = {
            "summary": self._extract_summary(full_context),
            "gst_summary": self._extract_gst_summary(full_context),
            "itc_health": self._extract_itc_health(full_context),
            "tds_summary": self._extract_tds_summary(full_context),
            "einvoice_status": self._extract_einvoice_status(full_context),
            "ewaybill_status": self._extract_ewaybill_status(full_context),
            "filing_compliance": self._extract_filing_compliance(full_context),
            "reconciliation_score": self._extract_reconciliation_score(full_context),
            "hsn_summary": self._extract_hsn_summary(full_context),
            "tax_forecast": self._extract_tax_forecast(full_context),
            "advance_tax_schedule": self._extract_advance_tax_schedule(full_context),
            "net_gst": full_context.get("net_gst", 0),
            "effective_tax_rate": full_context.get("effective_tax_rate", 0),
            "compliance_score": full_context.get("compliance_score", 0),
            "period": full_context.get("fiscal_year", {}).get("name", "Current FY"),
        }
        return compressed

    def _extract_gst_summary(self, context: Dict) -> Dict:
        """Extract GST summary metrics"""
        gst = context.get("gst_summary", [])
        total_cgst = sum(float(row.get("cgst", 0)) for row in gst)
        total_sgst = sum(float(row.get("sgst", 0)) for row in gst)
        total_igst = sum(float(row.get("igst", 0)) for row in gst)
        total_revenue = sum(float(row.get("total_revenue", 0)) for row in gst)
        invoice_count = sum(int(row.get("invoice_count", 0)) for row in gst)
        return {
            "total_cgst": total_cgst,
            "total_sgst": total_sgst,
            "total_igst": total_igst,
            "total_revenue": total_revenue,
            "invoice_count": invoice_count,
            "monthly": gst[:12],
        }

    def _extract_itc_health(self, context: Dict) -> Dict:
        """Extract ITC health data"""
        itc = context.get("itc_health", {})
        if isinstance(itc, dict) and "error" in itc:
            return itc
        return {
            "available": itc.get("available", 0),
            "claimed": itc.get("claimed", 0),
            "ineligible": itc.get("ineligible", 0),
            "utilizable": itc.get("utilizable", 0),
            "utilization_pct": itc.get("utilization_pct", 0),
        }

    def _extract_tds_summary(self, context: Dict) -> Dict:
        """Extract TDS summary data"""
        tds = context.get("tds_summary", {})
        return {
            "total_payable": tds.get("total_payable", 0),
            "receivable": tds.get("receivable", 0),
            "net_position": tds.get("net_position", 0),
            "top_sections": (tds.get("payable_by_section", []) or [])[:5],
        }

    def _extract_einvoice_status(self, context: Dict) -> Dict:
        """Extract e-Invoice status"""
        einv = context.get("einvoice_status", {})
        if isinstance(einv, dict) and "error" in einv:
            return einv
        return {
            "total": einv.get("total", 0),
            "filed": einv.get("filed", 0),
            "pending": einv.get("pending", 0),
            "failed": einv.get("failed", 0),
            "coverage_pct": einv.get("coverage_pct", 0),
        }

    def _extract_ewaybill_status(self, context: Dict) -> Dict:
        """Extract e-Waybill status"""
        ewb = context.get("ewaybill_status", {})
        if isinstance(ewb, dict) and "error" in ewb:
            return ewb
        return {
            "total": ewb.get("total", 0),
            "active": ewb.get("active", 0),
            "cancelled": ewb.get("cancelled", 0),
        }

    def _extract_filing_compliance(self, context: Dict) -> Dict:
        """Extract filing compliance data"""
        filing = context.get("filing_compliance", {})
        if isinstance(filing, dict) and "error" in filing:
            return filing
        return {
            "gstr1_status": filing.get("gstr1", {}).get("status", "Unknown"),
            "gstr3b_status": filing.get("gstr3b", {}).get("status", "Unknown"),
            "gstr1_filed": filing.get("gstr1", {}).get("filed", 0),
            "gstr3b_filed": filing.get("gstr3b", {}).get("filed", 0),
        }

    def _extract_reconciliation_score(self, context: Dict) -> Dict:
        """Extract reconciliation score"""
        recon = context.get("reconciliation_score", {})
        if isinstance(recon, dict) and "error" in recon:
            return recon
        return {
            "matched_count": recon.get("matched_count", 0),
            "unmatched_count": recon.get("unmatched_count", 0),
            "mismatch_count": recon.get("mismatch_count", 0),
            "reconciliation_score": recon.get("reconciliation_score", 0),
        }

    def _extract_hsn_summary(self, context: Dict) -> List[Dict]:
        """Extract top HSN summary"""
        hsn = context.get("hsn_summary", [])
        return [
            {
                "hsn_code": row.get("hsn_code", ""),
                "revenue": float(row.get("revenue", 0)),
                "estimated_tax": float(row.get("estimated_tax", 0)),
                "invoice_count": int(row.get("invoice_count", 0)),
            }
            for row in hsn[:10]
        ]

    def _extract_tax_forecast(self, context: Dict) -> Dict:
        """Extract tax forecast"""
        forecast = context.get("tax_forecast", {})
        return {
            "forecast": forecast.get("forecast", []),
            "trend_slope": forecast.get("trend_slope", 0),
            "note": forecast.get("note", ""),
        }

    def _extract_advance_tax_schedule(self, context: Dict) -> List[Dict]:
        """Extract advance tax schedule"""
        return context.get("advance_tax_schedule", [])


    def _get_default_system_prompt(self, context: Optional[Dict] = None) -> str:
        """Get default system prompt for tax agent"""
        ctx_str = ""
        if context:
            import json
            ctx_str = json.dumps(context, indent=2, default=str)

        return f"""You are a specialized India Tax Intelligence AI assistant for ERPNext.

## Your Expertise:
- India GST law interpretation and compliance
- Input Tax Credit (ITC) optimization and reconciliation
- TDS compliance and deduction tracking
- e-Invoice and e-Waybill regulations
- GSTR-1 and GSTR-3B filing compliance
- Advance tax computation and scheduling
- HSN-level tax analysis
- Tax planning and forecasting

## India Tax Rates Reference:
- GST Rates: 0%, 5%, 12%, 18%, 28%
- Corporate Tax: 25% (turnover < 400 Cr) or 30%
- TDS Sections:
  - 194C (Contractors): 1% (individual/HUF) or 2% (others)
  - 194J (Professional Fees): 10%
  - 194H (Commission/Brokerage): 5%
  - 194I (Rent): 2% (plant/machinery) or 10% (land/building)
  - 194Q (Purchase of Goods): 0.1%
- Health & Education Cess: 4% on income tax
- GSTR-1: Due 11th of following month
- GSTR-3B: Due 20th of following month
- Advance Tax:
  - 15 Jun: 15%
  - 15 Sep: 45%
  - 15 Dec: 75%
  - 15 Mar: 100%

## Current Dashboard Data:
{ctx_str if ctx_str else "No data available"}

## Guidelines:
- Reference specific GST Act / Rules sections where applicable
- Calculate tax savings with concrete INR amounts
- Highlight compliance risks and GST due dates
- Suggest legitimate tax planning strategies
- Explain ITC ineligibility reasons clearly
- Recommend e-Invoice coverage improvements
- Use INR for all monetary amounts
- Format numbers with thousands separators

## Response Format:
- Start with tax position summary
- Highlight compliance issues (filing delays, low e-Invoice coverage)
- Quantify optimization opportunities
- Recommend 2-3 specific actions with expected tax savings"""

    def _get_default_quick_actions(self) -> List[Dict]:
        """Get default quick actions for tax dashboard"""
        return [
            {
                "label": "📊 GST Overview",
                "prompt_template": "What is my current GST position? Summarize output tax, input tax credit, and net GST liability.",
                "icon": "calculator",
            },
            {
                "label": "🔄 ITC Health",
                "prompt_template": "How healthy is my Input Tax Credit? What is my utilization rate and are there any ineligible credits I should watch out for?",
                "icon": "refresh-cw",
            },
            {
                "label": "📑 TDS Summary",
                "prompt_template": "What is my TDS position? How much is payable vs receivable and which sections contribute the most?",
                "icon": "file-text",
            },
            {
                "label": "📧 e-Invoice Status",
                "prompt_template": "What is my e-Invoice coverage? How many invoices are pending or failed and what should I do?",
                "icon": "mail",
            },
            {
                "label": "📅 Filing Compliance",
                "prompt_template": "Am I compliant with GSTR-1 and GSTR-3B filings? Are any returns pending or late?",
                "icon": "calendar",
            },
            {
                "label": "💰 Tax Planning",
                "prompt_template": "What tax optimization opportunities exist? How much can I potentially save and what actions should I take?",
                "icon": "trending-down",
            },
        ]

    def _get_default_routing_keywords(self) -> List[str]:
        """Get default routing keywords for tax queries"""
        return [
            "tax", "gst", "igst", "cgst", "sgst", "itc",
            "input tax credit", "gstr", "gstr-1", "gstr-3b",
            "einvoice", "e-waybill", "ewaybill", "hsn",
            "tds", "tax deducted", "withholding", "advance tax",
            "filing", "compliance", "reconciliation", "gst inward",
            "tax planning", "tax savings", "tax liability",
            "effective tax rate", "fiscal year", "turnover",
        ]
