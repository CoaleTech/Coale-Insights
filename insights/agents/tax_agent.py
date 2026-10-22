# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Tax Intelligence Agent
Specialized AI agent for the Kenya (KRA) Tax Intelligence dashboard.

Every statutory figure in the prompt is read from
`insights.ml.kenya_tax_intelligence.rules` at call time, so the agent, the
dashboard and the rule tests cannot drift apart. Every company figure comes from
the dashboard payload (`KenyaTaxIntelligence(period).train()`), never from memory.
"""

import json
from datetime import date
from typing import Dict, List, Optional

import frappe

from insights.agents.base import BaseIntelligenceAgent, _safe_log_error
from insights.agents.registry import AgentRegistry
from insights.ml.kenya_tax_intelligence import rules

# Keys that are reference data (already in the prompt) or UI plumbing, not facts about the company.
_DROP = {"drill", "rate_card", "penalty_reference", "rates"}
# Chart series: 12 small rows, kept whole so trends stay answerable.
_SERIES = {"monthly", "coverage_trend"}
_ROWS = 5  # rows kept per list section
_MAX_CHARS = 16000  # base.py targets ~10KB; a 9-tab payload needs more, so this is the hard ceiling


def _pct(rate: float) -> str:
    return f"{rate * 100:g}%"


def _kes(amount: float) -> str:
    return f"KES {amount:,.0f}"


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def kenya_reference(on: Optional[date] = None) -> str:
    """The statutory reference block of the prompt, built only from `rules`."""
    on = on or date.today()
    due = rules.monthly_due_dates(on)
    lel, uel = rules.nssf_limits(on)
    nssf_year = max(sum(1 for row in rules.NSSF_YEARS if row[0] <= on), 1)
    bands = "; ".join(
        f"{label} {_pct(rate)}" for label, (_, rate) in zip(rules.PAYE_BAND_LABELS, rules.PAYE_BANDS)
    )
    wht = "\n".join(
        f"  - {r['payment']}: {r['resident']:g}% resident, {r['non_resident']:g}% non-resident"
        for r in rules.wht_rate_card()
    )
    instalments = ", ".join(f"{d.day} {d:%b}" for d in rules.instalment_dates(date(on.year, 1, 1)))
    penalties = "\n".join(f"  - {p['breach']}: {p['penalty']}" for p in rules.PENALTY_REFERENCE)
    return f"""## Kenya Tax Reference (Finance Act 2026 basis, from the dashboard rule table):
- VAT: standard rate {_pct(rules.VAT_RATE)}; registration threshold {_kes(rules.VAT_REG_THRESHOLD)}; return and payment due on the {_ordinal(due["vat"].day)} of the following month
- Input VAT is claimable only against a valid eTIMS invoice and only within {rules.INPUT_VAT_WINDOW_MONTHS} months of the invoice date
- VAT withholding by appointed agents: {_pct(rules.WHVAT_RATE)}, remitted within {rules.WHT_WORKING_DAYS} working days
- PAYE (monthly bands): {bands}
- Personal relief {_kes(rules.PERSONAL_RELIEF)} a month (residents only); insurance relief {_pct(rules.INSURANCE_RELIEF_RATE)} of premiums capped at {_kes(rules.INSURANCE_RELIEF_CAP)}
- Pension and mortgage-interest deductions are each capped at {_kes(rules.PENSION_DEDUCTION_CAP)} a month
- NSSF Year {nssf_year}: {_pct(rules.NSSF_RATE)} of pensionable pay up to the upper earnings limit {_kes(uel)} (lower earnings limit {_kes(lel)}); the employer matches the employee
- SHIF: {_pct(rules.SHIF_RATE)} of gross pay, minimum {_kes(rules.SHIF_MIN)} a month
- Affordable Housing Levy (AHL): {_pct(rules.AHL_RATE)} employee plus {_pct(rules.AHL_RATE)} employer
- NITA levy: {_kes(rules.NITA_PER_EMPLOYEE)} per employee a month
- PAYE, NSSF, SHIF and NITA are due on the {_ordinal(due["paye"].day)} of the following month; AHL within {rules.AHL_WORKING_DAYS} working days after month end
- Withholding tax (WHT) rates, remitted within {rules.WHT_WORKING_DAYS} working days of the payment:
{wht}
- Corporate income tax (CIT): {_pct(rules.CIT_RATE)}; four instalments of 25% on the {instalments} for a calendar-year company; balance due the last day of the 4th month after year end; return due the last day of the 6th month after year end
- Instalment underpayment penalty: {_pct(rules.INSTALMENT_PENALTY)} of the shortfall; the dashboard sizes the instalment base from {_pct(rules.INSTALMENT_PRIOR_FACTOR)} of prior-year tax or the current estimate
- Tax losses carry forward {rules.LOSS_CARRY_FORWARD_YEARS} years
- Turnover tax (TOT): {_pct(rules.TOT_RATE)} of gross turnover for {_kes(rules.TOT_MIN)} to {_kes(rules.TOT_MAX)} a year, due on the {_ordinal(due["tot"].day)} of the following month
- Significant economic presence (SEP) tax: {_pct(rules.SEP_RATE)} on non-resident digital services; capital gains tax {_pct(rules.CGT_RATE)}
- Customs: import declaration fee (IDF) {_pct(rules.IDF_RATE)} of CIF, railway development levy (RDL) {_pct(rules.RDL_RATE)} of CIF; import VAT is charged on CIF plus duty plus excise; excise due on the {_ordinal(due["excise"].day)} of the following month
- Late payment: {_pct(rules.LATE_PAYMENT_PENALTY)} one-off plus {_pct(rules.INTEREST_PER_MONTH)} a month interest
- Penalty reference:
{penalties}
- Tax amnesty: liabilities up to {rules.AMNESTY_PERIOD_END:%d %b %Y} qualify if the principal is fully paid by {rules.AMNESTY_DEADLINE:%d %b %Y}; penalties and interest are then waived
- Disputes: object within {rules.OBJECTION_DAYS} days of the assessment; KRA decides within {rules.DECISION_DAYS} days of a valid objection; appeal to the Tax Appeals Tribunal within {rules.APPEAL_DAYS} days of the decision
- Keep tax records for {rules.RECORDS_YEARS} years"""


def _slim(value, rows: int = _ROWS, key: Optional[str] = None):
    """Trim a tab payload for the prompt: lists cut to `rows`, UI/reference keys dropped.

    `None` is kept on purpose: in the payload it means "cannot be determined from the
    data", which is different from a missing key and different from zero.
    """
    if isinstance(value, dict):
        return {k: _slim(v, rows, k) for k, v in value.items() if k not in _DROP}
    if isinstance(value, list):
        keep = value[: max(rows, 12)] if key in _SERIES else value[:rows]
        return [_slim(v, rows) for v in keep]
    return value


@AgentRegistry.register("Tax")
class TaxIntelligenceAgent(BaseIntelligenceAgent):
    """AI agent specialized for the Kenya Tax Intelligence dashboard"""

    dashboard_type = "Tax"
    agent_name = "Tax Intelligence Agent"
    description = "AI assistant for Kenya VAT, eTIMS, payroll taxes, withholding tax, income tax and KRA compliance"

    def compress_context(self, full_context: Dict) -> Dict:
        """Compress the `KenyaTaxIntelligence.train()` envelope for the prompt."""
        ctx = full_context or {}
        tabs = ctx.get("tabs") if isinstance(ctx.get("tabs"), dict) else {}
        period = ctx.get("period")
        period_name = period.get("name") if isinstance(period, dict) else period
        compressed = {
            "kenya_tax": True,
            "summary": f"Kenya tax position for {ctx.get('company') or 'the company'}, {period_name or 'current period'}",
            "company": ctx.get("company"),
            "base_currency": ctx.get("base_currency") or "KES",
            "period": period,
            "today": ctx.get("today"),
            "active_tab": ctx.get("activeTab") or ctx.get("active_tab"),
            "badges": ctx.get("badges") or {},
            "tabs": {name: _slim(tab) for name, tab in tabs.items() if isinstance(tab, dict)},
        }
        if len(json.dumps(compressed, default=str)) > _MAX_CHARS:
            compressed["tabs"] = {name: _slim(tab, 2) for name, tab in tabs.items() if isinstance(tab, dict)}
        return compressed

    def _train(self, period) -> Optional[Dict]:
        """Fetch the live dashboard payload when the caller sent no context."""
        key = period.get("key") if isinstance(period, dict) else period
        try:
            if not frappe.has_permission("GL Entry", "read"):
                return None
            # Lazy: the package's model module is heavy and must not load at import time.
            from insights.ml.kenya_tax_intelligence.model import KenyaTaxIntelligence

            return KenyaTaxIntelligence(key if isinstance(key, str) else "fy").train()
        except Exception as e:
            _safe_log_error(f"Tax agent payload failed: {str(e)[:300]}", "Tax Agent")
            return None

    def _prompt_context(self, context: Optional[Dict]) -> Dict:
        """Compressed context for the prompt, from whatever the caller has: an already
        compressed context, a raw dashboard envelope, or nothing (then the live payload)."""
        ctx = context or {}
        if ctx.get("kenya_tax"):
            return ctx
        if not isinstance(ctx.get("tabs"), dict):
            payload = self._train(ctx.get("period")) or {}
            ctx = {**payload, "activeTab": ctx.get("activeTab") or ctx.get("active_tab")}
        return self.compress_context(ctx)

    def build_system_prompt(self, context: Optional[Dict] = None) -> str:
        """Dashboard AI Agent Config ships no Tax prompt, so the base class would send only
        the skill block. Use the Kenya prompt unless an admin wrote their own."""
        ctx = self._prompt_context(context or self.compressed_context)
        if self.config and self.config.system_prompt:
            return super().build_system_prompt(ctx)

        from insights.agents.skills import skill_prompt_for

        prompt = self._get_default_system_prompt(ctx)
        skill = skill_prompt_for(self.dashboard_type, ctx)
        return f"{prompt}\n\n{skill}" if skill else prompt

    def get_quick_actions(self) -> List[Dict]:
        return (self.config.get_quick_actions() if self.config else []) or self._get_default_quick_actions()

    def get_routing_keywords(self) -> List[str]:
        return (self.config.get_routing_keywords() if self.config else []) or self._get_default_routing_keywords()

    def _get_default_system_prompt(self, context: Optional[Dict] = None) -> str:
        """Get default system prompt for tax agent"""
        ctx_str = json.dumps(context, separators=(",", ":"), default=str) if context else ""

        return f"""You are a specialized Kenya Tax Intelligence AI assistant for ERPNext, working for the finance team of a Kenyan business.

## Your Expertise:
- VAT: output, input VAT claimability, the 6-month claim window, VAT withholding
- eTIMS: invoice transmission, supplier invoice coverage, KRA rejections, penalty exposure
- Payroll taxes: PAYE, NSSF, SHIF, Affordable Housing Levy, NITA
- Withholding tax by payee type, remittance timing and rate exceptions
- Corporate income tax instalments, tax losses, turnover tax
- Customs and excise: IDF, RDL, import VAT, digital services
- Tax disputes: assessments, objections, Tribunal appeals, the tax amnesty
- The rule-generated action queue

{kenya_reference()}

## Current Dashboard Data:
{ctx_str if ctx_str else "No data available"}

## How to read the data:
- Each tab has `kpis` (key, label, value, unit, sub, tone) plus detail sections. `available: false` means the tab's data source is missing: repeat its `message` and do not estimate.
- Amounts are plain numbers in `base_currency`; `pct` values are 0-100. A value of `null` means unknown, not zero. Say it cannot be determined and use the `sub` text for what is needed.
- `badges` count the exceptions needing action per tab. `active_tab` is the tab the user is looking at.

## Guidelines:
- Every figure about the company must come from Current Dashboard Data; every rate and date from the reference above. Never invent either.
- If a rate or rule is not in the reference, say it is not in the dashboard's rule table rather than guessing.
- ERPNext records tax payments, not KRA filings: say "paid", never "filed", unless the data says otherwise.
- Due dates are the nominal statutory dates and are not moved for weekends or holidays; advise paying before the earlier working day.
- Rank by exposure: overdue and penalty-bearing items first, then the soonest deadline.
- Use KES (the payload's base currency) and format numbers with thousands separators.
- You report the position and the deadline; recommend a tax adviser or KRA for rulings and do not give legal opinions.

## Response Format:
- Start with the tax position summary
- Highlight compliance issues (overdue remittances, low eTIMS coverage, input VAT about to lapse)
- Quantify exposure and penalties with real amounts and dates
- Recommend 2-3 specific actions, each with an owner-ready deadline"""

    def _get_default_quick_actions(self) -> List[Dict]:
        """Get default quick actions for tax dashboard"""
        return [
            {
                "label": "📅 Deadlines",
                "prompt_template": "Which tax obligations fall due in the next 30 days, how much is each, and is anything overdue?",
                "icon": "calendar",
            },
            {
                "label": "🧾 VAT Position",
                "prompt_template": "What is my VAT position? Summarize output VAT, claimable input VAT, net VAT payable and how much input VAT is at risk of lapsing.",
                "icon": "calculator",
            },
            {
                "label": "📡 eTIMS Coverage",
                "prompt_template": "How complete is my eTIMS coverage? How many sales are untransmitted or rejected by KRA, and which purchases lack a supplier eTIMS invoice?",
                "icon": "radio",
            },
            {
                "label": "👥 Payroll Taxes",
                "prompt_template": "What do I owe KRA, NSSF, SHIF and the housing levy for the latest payroll, and are there PAYE or NSSF exceptions to fix?",
                "icon": "users",
            },
            {
                "label": "✂️ Withholding Tax",
                "prompt_template": "How much withholding tax have I deducted and remitted? Which payments are unremitted past 5 working days or deducted at the wrong rate?",
                "icon": "scissors",
            },
            {
                "label": "⚖️ Disputes & Amnesty",
                "prompt_template": "What objection and appeal deadlines are coming up, and how much principal must I pay before the amnesty ends on 31 December 2026?",
                "icon": "scale",
            },
            {
                "label": "✅ Action Queue",
                "prompt_template": "What are the top open tax actions ranked by exposure, and what happens if I miss them?",
                "icon": "list-checks",
            },
        ]

    def _get_default_routing_keywords(self) -> List[str]:
        """Get default routing keywords for tax queries"""
        return [
            "tax", "kra", "vat", "input vat", "output vat", "etims", "cu number", "control unit",
            "paye", "nssf", "shif", "sha", "housing levy", "ahl", "nita", "payroll tax",
            "withholding", "wht", "instalment", "installment", "corporate tax", "income tax",
            "turnover tax", "tot", "excise", "customs", "idf", "rdl", "import duty",
            "amnesty", "objection", "tribunal", "assessment", "tax case",
            "filing", "compliance", "tax planning", "tax liability", "effective tax rate",
        ]
