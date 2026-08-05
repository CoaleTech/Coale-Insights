# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Per-dashboard analysis skills for the intelligence chat.

A skill is a small, declarative playbook: which part of the dashboard payload
to read, which questions an analyst would answer from it, which numbers are
worth flagging, and how to structure the reply.

Without one the model free-associates about what a tab *usually* shows. With
one it answers the questions the tab exists to answer, grounded in the figures
actually on screen.

Skills are matched on dashboard type plus the active tab, so "Customer
Patterns" gets a retention playbook while "Margins" gets a profitability one.
The reads listed here are real top-level keys observed in the ML payloads;
the renderer additionally lists the keys present at runtime so the model never
has to guess where a figure lives.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class AnalysisSkill:
	"""A playbook for interpreting one dashboard surface."""

	key: str
	title: str
	focus: str
	# Dashboard types this applies to, e.g. ("Sales",).
	dashboards: Tuple[str, ...]
	# Active tab ids this applies to; empty means the whole dashboard.
	tabs: Tuple[str, ...] = ()
	# Context keys that carry the figures for this surface.
	reads: Tuple[str, ...] = ()
	questions: Tuple[str, ...] = ()
	signals: Tuple[str, ...] = ()
	outline: Tuple[str, ...] = field(default_factory=tuple)


# --- Revenue -----------------------------------------------------------------

REVENUE_OVERVIEW = AnalysisSkill(
	key="revenue-overview",
	title="Revenue Overview",
	focus="Where revenue came from, whether it is growing, and what is driving the change.",
	dashboards=("Sales",),
	tabs=("rev-overview",),
	reads=("summary", "revenue_metrics", "comparisons", "dimensions"),
	questions=(
		"What is total revenue, transaction count and average order value for the period?",
		"How does month-over-month and year-over-year growth compare?",
		"Which dimension (product group, territory, segment) moved the number most?",
	),
	signals=(
		"Growth beyond +/-20% month-over-month usually means a timing artefact, a lost account or a one-off order — say which.",
		"Rising revenue with a falling transaction count means fewer, larger orders: concentration risk, not health.",
	),
	outline=(
		"Headline: revenue, growth, AOV",
		"What moved: the two or three largest contributors",
		"Risk or opportunity in one line",
	),
)

REVENUE_PAYMENT_MIX = AnalysisSkill(
	key="revenue-payment-mix",
	title="Cash vs Credit",
	focus="Collection quality and the working-capital cost of the sales mix.",
	dashboards=("Sales",),
	tabs=("rev-payment",),
	reads=("payment_mix", "summary"),
	questions=(
		"What share of revenue is cash versus credit?",
		"Is the credit share trending up, and what does that do to DSO?",
	),
	signals=(
		"A credit share climbing while DSO rises is cash tied up, even when revenue looks fine.",
		"A very high cash ratio can mean healthy collection or an under-served credit segment — do not assume.",
	),
	outline=("The split", "Cash-flow consequence", "What to change"),
)

REVENUE_REPS = AnalysisSkill(
	key="revenue-reps",
	title="Sales Rep Performance",
	focus="Who is producing, how consistently, and what separates the top from the rest.",
	dashboards=("Sales",),
	tabs=("rev-reps",),
	reads=("sales_reps", "summary"),
	questions=(
		"Who are the top and bottom reps by revenue and by order count?",
		"Is performance concentrated in one or two people?",
		"Do the top reps win on deal size or deal frequency?",
	),
	signals=(
		"One rep above ~40% of revenue is a key-person dependency.",
		"High revenue with low order count is a single large deal, not sustained performance.",
	),
	outline=("Ranking", "What the leaders do differently", "Coaching or coverage action"),
)

REVENUE_MARGINS = AnalysisSkill(
	key="revenue-margins",
	title="Margin Analysis",
	focus="Whether revenue is converting into profit, and where it leaks.",
	dashboards=("Sales",),
	tabs=("rev-margins",),
	reads=("margins", "summary", "dimensions"),
	questions=(
		"What is the overall margin and how does it vary by product group or customer?",
		"Are the largest revenue lines also the most profitable?",
		"Which lines are sold at or below cost?",
	),
	signals=(
		"A top-revenue line with below-average margin is the highest-value fix on the page.",
		"Margin falling while revenue rises means discounting or input-cost pass-through failure.",
	),
	outline=("Overall margin", "Best and worst lines", "The one line worth repricing"),
)

REVENUE_FORECASTS = AnalysisSkill(
	key="revenue-forecasts",
	title="Revenue Forecast",
	focus="What the trend implies, and how much confidence it deserves.",
	dashboards=("Sales",),
	tabs=("rev-forecasts",),
	reads=("forecasts", "summary", "comparisons"),
	questions=(
		"What is the forecast for the coming period and what method produced it?",
		"How volatile is the history the forecast is extrapolating from?",
	),
	signals=(
		"State the basis. A linear trend over a short or seasonal history is weak evidence — say so.",
		"If the payload reports insufficient data, report that rather than producing a number.",
	),
	outline=("Forecast and basis", "Confidence and why", "What would change it"),
)

REVENUE_ATTRIBUTION = AnalysisSkill(
	key="revenue-attribution",
	title="Revenue Attribution",
	focus="Which sources and channels are actually generating revenue.",
	dashboards=("Sales",),
	tabs=("rev-sources",),
	reads=("dimensions", "summary"),
	questions=(
		"Which sources contribute most revenue and most orders?",
		"Does any source convert far above or below its share of volume?",
	),
	signals=("A source with many orders but little revenue is a low-value channel; name it.",),
	outline=("Top sources", "Efficiency outliers", "Where to shift effort"),
)


# --- Customers ---------------------------------------------------------------

CUSTOMER_PATTERNS = AnalysisSkill(
	key="customer-patterns",
	title="Customer Patterns",
	focus="Who buys, how often, how much they are worth, and who is slipping away.",
	dashboards=("Customer", "Sales"),
	tabs=("cust-patterns",),
	reads=(
		"summary",
		"pareto_analysis",
		"cohort_analysis",
		"at_risk_customers",
		"top_customers",
		"customers",
	),
	questions=(
		"How concentrated is revenue — what share comes from the top 10% and top 20% of customers?",
		"What is average order value and average customer lifetime value?",
		"Which previously active customers have gone quiet, and what were they worth?",
		"How do the value tiers break down, and how much sits in the lowest tier?",
	),
	signals=(
		"Top 10% above ~70% of revenue is dependency risk, not just a strength — name the accounts.",
		"A dormant customer with high historical value is the cheapest revenue on the page.",
		"A large low-tier population with a high average CLV means the average is hiding a pyramid; report both.",
		"Rising churn risk against a flat health score is an early warning worth stating plainly.",
	),
	outline=(
		"Concentration: the dependency picture with real percentages",
		"Value and frequency: AOV, CLV, order cadence",
		"At risk: named accounts that went quiet and their value",
		"The single highest-value action",
	),
)

CUSTOMER_OVERVIEW = AnalysisSkill(
	key="customer-overview",
	title="Customer Overview",
	focus="The health of the customer base as a whole.",
	dashboards=("Customer", "Sales"),
	tabs=("cust-overview",),
	reads=("summary", "customers", "top_customers"),
	questions=(
		"How many customers are there, and how many are active in the period?",
		"What are average health and churn-risk scores telling you?",
	),
	signals=("Report health and churn together; either alone is misleading.",),
	outline=("Base size and activity", "Health and risk", "What stands out"),
)

CUSTOMER_COHORTS = AnalysisSkill(
	key="customer-cohorts",
	title="Customer Cohorts",
	focus="Whether newer customers retain as well as older ones.",
	dashboards=("Customer", "Sales"),
	tabs=("cust-cohorts",),
	reads=("cohort_analysis", "summary"),
	questions=(
		"How does retention differ between acquisition cohorts?",
		"Are recent cohorts retaining better or worse than earlier ones?",
	),
	signals=(
		"Declining retention in recent cohorts is an acquisition-quality problem, not a churn problem.",
		"Thin cohorts are noisy; say when a cohort is too small to read.",
	),
	outline=("Retention by cohort", "The trend across cohorts", "What it implies about acquisition"),
)

CUSTOMER_GEOGRAPHY = AnalysisSkill(
	key="customer-geography",
	title="Customer Geography",
	focus="Where revenue is concentrated geographically and where it is thin.",
	dashboards=("Customer", "Sales"),
	tabs=("cust-geography",),
	reads=("geographic_analysis", "summary"),
	questions=(
		"Which territories generate the most revenue and the most customers?",
		"Is any territory over-indexed on a single account?",
	),
	signals=("A territory carried by one customer is a concentration risk disguised as coverage.",),
	outline=("Top territories", "Coverage gaps", "Where expansion is cheapest"),
)

CUSTOMER_ACTIONS = AnalysisSkill(
	key="customer-actions",
	title="Next Best Actions",
	focus="Turning the customer signals into a ranked, concrete worklist.",
	dashboards=("Customer", "Sales"),
	tabs=("cust-actions",),
	reads=("next_best_actions", "at_risk_customers", "top_customers"),
	questions=(
		"Which accounts warrant contact first, and why?",
		"What is the expected value of each recommended action?",
	),
	signals=("Rank by value at stake, not by alphabetical or arbitrary order.",),
	outline=("Ranked actions with the account and the reason", "Value at stake", "Suggested sequence"),
)

CUSTOMER_RANKINGS = AnalysisSkill(
	key="customer-rankings",
	title="Customer Rankings",
	focus="The league table and what the ordering reveals.",
	dashboards=("Customer", "Sales"),
	tabs=("cust-rankings", "cust-list"),
	reads=("top_customers", "customers", "pareto_analysis"),
	questions=(
		"Who are the top customers by value and by order volume?",
		"How steep is the drop-off between ranks?",
	),
	signals=("A steep drop after the top few accounts is the concentration story; quantify the cliff.",),
	outline=("Top accounts", "Shape of the curve", "Dependency implication"),
)


# --- Financial ---------------------------------------------------------------

FINANCIAL_OVERVIEW = AnalysisSkill(
	key="financial-overview",
	title="Financial Overview",
	focus="Profitability, liquidity and the direction of both.",
	dashboards=("Financial",),
	tabs=("overview", "ratios", "costratios"),
	reads=("overview", "cash_flow", "receivables", "payables"),
	questions=(
		"What are revenue, profit and margin for the period?",
		"What do the liquidity and leverage ratios say about solvency?",
	),
	signals=(
		"Profit on paper with negative operating cash flow is the most important thing on the page.",
		"Compare ratios to their targets where the payload supplies them, not to generic benchmarks.",
	),
	outline=("Profitability", "Liquidity", "The one number to watch"),
)

FINANCIAL_CASHFLOW = AnalysisSkill(
	key="financial-cashflow",
	title="Cash Flow",
	focus="Whether the business is generating or consuming cash, and for how long it can continue.",
	dashboards=("Financial",),
	tabs=("cashflow", "cashforecast", "cashflow13"),
	reads=("cash_flow", "overview", "receivables", "payables"),
	questions=(
		"What is net cash flow and the current burn or generation rate?",
		"How many weeks or months of runway does that imply?",
	),
	signals=(
		"Negative net cash flow deserves a runway figure, not an adjective.",
		"A forecast built on a short history is weak; state the basis.",
	),
	outline=("Position", "Runway", "The lever that moves it most"),
)

FINANCIAL_RECEIVABLES = AnalysisSkill(
	key="financial-receivables",
	title="Receivables",
	focus="Who owes money, for how long, and what is at risk of never arriving.",
	dashboards=("Financial",),
	tabs=("receivables",),
	reads=("receivables", "overview"),
	questions=(
		"What is total outstanding and how is it aged?",
		"Which customers hold the largest overdue balances?",
	),
	signals=(
		"Concentrated overdue balances are a collection problem with a name — give the name.",
		"Rising DSO with flat revenue means collection is slipping.",
	),
	outline=("Total and ageing", "Worst accounts", "Collection priority"),
)

FINANCIAL_PAYABLES = AnalysisSkill(
	key="financial-payables",
	title="Payables",
	focus="What is owed, when it falls due, and whether terms are being used well.",
	dashboards=("Financial",),
	tabs=("payables", "working"),
	reads=("payables", "cash_flow", "overview"),
	questions=(
		"What is outstanding to suppliers and how is it aged?",
		"Are payments being made materially earlier than terms require?",
	),
	signals=("Paying well before terms while cash is tight is free working capital left unused.",),
	outline=("Position and ageing", "Terms usage", "Timing recommendation"),
)

FINANCIAL_FOREX = AnalysisSkill(
	key="financial-forex",
	title="Forex Exposure",
	focus="Currency exposure and what a rate move would cost.",
	dashboards=("Financial",),
	tabs=("forex",),
	reads=("forex", "overview"),
	questions=(
		"Which currencies carry exposure and how large is each?",
		"What is the unrealised gain or loss at current rates?",
	),
	signals=("Quantify sensitivity where the data allows; avoid directional predictions about rates.",),
	outline=("Exposure by currency", "Current impact", "Hedging consideration"),
)


# --- Operations --------------------------------------------------------------

INVENTORY_SKILL = AnalysisSkill(
	key="inventory",
	title="Inventory Intelligence",
	focus="Whether stock is working: turning over, correctly placed, and not dying on a shelf.",
	dashboards=("Inventory",),
	reads=(
		"stock_overview",
		"turnover_analysis",
		"aging_analysis",
		"dead_stock",
		"abc_xyz",
		"warehouse_analysis",
		"transfer_recommendations",
		"demand_planning",
	),
	questions=(
		"What is total stock value and how fast is it turning?",
		"How much capital is sitting in dead or slow-moving stock?",
		"Which items are class A by value, and are any of them at risk of stockout?",
		"Do any warehouses hold stock that another location needs?",
	),
	signals=(
		"Dead stock is cash already spent; always quantify it in currency, not units.",
		"A class-A item running low is more urgent than a large pile of class-C stock.",
		"Low overall turnover with healthy revenue means the imbalance is in a few SKUs — find them.",
	),
	outline=("Stock position and turnover", "Capital trapped in dead or slow stock", "Rebalancing or reorder actions"),
)

PROCUREMENT_SKILL = AnalysisSkill(
	key="procurement",
	title="Procurement Intelligence",
	focus="Where spend goes, whether suppliers perform, and where price is drifting.",
	dashboards=("Procurement",),
	reads=(
		"spend_overview",
		"supplier_performance",
		"purchase_analytics",
		"price_intelligence",
		"risk_analysis",
		"forecasts",
	),
	questions=(
		"What is total spend and how concentrated is it across suppliers?",
		"Which suppliers miss on delivery or quality?",
		"Which items show the sharpest price increases?",
	),
	signals=(
		"A single supplier above ~30% of spend is a continuity risk; name them.",
		"Poor delivery performance on a sole-sourced item is the highest-risk combination on the page.",
	),
	outline=("Spend and concentration", "Supplier performance outliers", "Price movements worth acting on"),
)

RISK_SKILL = AnalysisSkill(
	key="risk",
	title="Risk Intelligence",
	focus="The largest exposures right now and which are getting worse.",
	dashboards=("Risk",),
	reads=(
		"overview",
		"credit_risk",
		"cashflow_risk",
		"operational_risk",
		"compliance_risk",
		"predictive_analytics",
	),
	questions=(
		"What is the overall risk score and which category contributes most?",
		"Which specific counterparties or processes drive the credit and operational scores?",
		"What is trending worse rather than merely being high?",
	),
	signals=(
		"Rank by exposure value, not by score alone; a high score on a small balance is not the priority.",
		"Separate 'high but stable' from 'moderate and deteriorating' — the second usually matters more.",
	),
	outline=("Overall posture", "Top exposures with values", "What is deteriorating"),
)

HR_SKILL = AnalysisSkill(
	key="hr",
	title="HR Intelligence",
	focus="Headcount, attrition and the cost and stability of the workforce.",
	dashboards=("HR",),
	questions=(
		"What is current headcount and how has it moved?",
		"What is the attrition rate and where is it concentrated?",
		"What do payroll cost and productivity per head look like?",
	),
	signals=(
		"Attrition concentrated in one department or tenure band is a management signal, not a market one.",
		"Small headcounts make attrition percentages volatile; report the raw counts alongside.",
	),
	outline=("Headcount and movement", "Attrition and where", "Cost and retention action"),
)

MANUFACTURING_SKILL = AnalysisSkill(
	key="manufacturing",
	title="Manufacturing Intelligence",
	focus="Throughput, efficiency and where production loses time or yield.",
	dashboards=("Manufacturing",),
	questions=(
		"What is OEE and which of availability, performance or quality drags it down?",
		"How do completion and on-time rates look against plan?",
		"Where are the bottlenecks and scrap concentrated?",
	),
	signals=(
		"OEE is a product of three factors; always say which one is the constraint.",
		"If quality data is absent, say so rather than presenting a partial OEE as complete.",
	),
	outline=("Output versus plan", "Efficiency and the binding constraint", "The intervention with most upside"),
)

MARKETING_SKILL = AnalysisSkill(
	key="marketing",
	title="Marketing & CRM Intelligence",
	focus="Pipeline quality, conversion and what acquisition actually costs.",
	dashboards=("Marketing",),
	questions=(
		"How many leads and opportunities are in play, and what is the conversion rate at each stage?",
		"Which campaigns or sources produce customers rather than merely leads?",
		"Where does the funnel leak most?",
	),
	signals=(
		"Lead volume without conversion is a vanity number; lead with converted value.",
		"The largest stage-to-stage drop is the story, not the total.",
	),
	outline=("Funnel shape", "Source quality", "Where to fix the leak"),
)

ESG_SKILL = AnalysisSkill(
	key="esg",
	title="ESG Intelligence",
	focus="Environmental, social and governance posture and the gaps in the evidence.",
	dashboards=("ESG",),
	questions=(
		"What are the scores across environmental, social and governance dimensions?",
		"Which metrics are measured, and which are missing?",
	),
	signals=(
		"Missing ESG data is itself a finding; report unmeasured areas explicitly rather than scoring them well by default.",
	),
	outline=("Scores by dimension", "Evidence gaps", "Highest-leverage improvement"),
)

TAX_SKILL = AnalysisSkill(
	key="tax",
	title="Tax Intelligence",
	focus="Liabilities, filing position and compliance exposure.",
	dashboards=("Tax",),
	questions=(
		"What are current tax liabilities by type and period?",
		"Are there filings due or overdue?",
	),
	signals=(
		"Overdue filings outrank liability size; penalties compound.",
		"Do not offer tax advice — report the position and the deadline.",
	),
	outline=("Liability position", "Filing status", "Immediate deadlines"),
)


# Dashboard-wide fallbacks, used when the active tab is unknown or absent.
# Registered after the tab-specific skills so a tab match always wins.
SALES_SKILL = AnalysisSkill(
	key="sales",
	title="Sales Intelligence",
	focus="Revenue performance, its drivers, and what to do about them.",
	dashboards=("Sales",),
	reads=("summary", "revenue_metrics", "comparisons", "margins", "sales_reps", "payment_mix"),
	questions=(
		"What is revenue for the period and how is it trending?",
		"Which customers, reps or products drive the number?",
		"Where is margin or collection quality slipping?",
	),
	signals=(
		"Lead with the figure that changed most, not the largest figure.",
		"Separate volume effects from price effects when the data allows.",
	),
	outline=("Headline numbers", "What is driving them", "The action worth taking"),
)

CUSTOMER_SKILL = AnalysisSkill(
	key="customer",
	title="Customer Intelligence",
	focus="Who the customers are, what they are worth, and who is at risk.",
	dashboards=("Customer",),
	reads=("summary", "top_customers", "pareto_analysis", "at_risk_customers", "customers"),
	questions=(
		"How concentrated is revenue across the customer base?",
		"What are customers worth on average, and how wide is the spread?",
		"Which accounts are at risk and what is their value?",
	),
	signals=(
		"Name accounts rather than describing them in aggregate.",
		"Report concentration as a risk and a strength together.",
	),
	outline=("Base and concentration", "Value distribution", "At-risk accounts and next step"),
)

SKILLS: Tuple[AnalysisSkill, ...] = (
	REVENUE_OVERVIEW,
	REVENUE_PAYMENT_MIX,
	REVENUE_REPS,
	REVENUE_MARGINS,
	REVENUE_FORECASTS,
	REVENUE_ATTRIBUTION,
	CUSTOMER_PATTERNS,
	CUSTOMER_OVERVIEW,
	CUSTOMER_COHORTS,
	CUSTOMER_GEOGRAPHY,
	CUSTOMER_ACTIONS,
	CUSTOMER_RANKINGS,
	FINANCIAL_OVERVIEW,
	FINANCIAL_CASHFLOW,
	FINANCIAL_RECEIVABLES,
	FINANCIAL_PAYABLES,
	FINANCIAL_FOREX,
	INVENTORY_SKILL,
	PROCUREMENT_SKILL,
	RISK_SKILL,
	HR_SKILL,
	MANUFACTURING_SKILL,
	MARKETING_SKILL,
	ESG_SKILL,
	TAX_SKILL,
	SALES_SKILL,
	CUSTOMER_SKILL,
)


def _active_tab(context: Optional[Dict[str, Any]]) -> str:
	if not isinstance(context, dict):
		return ""
	return str(context.get("activeTab") or context.get("active_tab") or "").strip()


def select_skill(dashboard_type: str, context: Optional[Dict[str, Any]] = None) -> Optional[AnalysisSkill]:
	"""Pick the most specific skill for the surface the user is looking at.

	A tab match wins over a dashboard-wide match, so "Customer Patterns" gets
	the retention playbook rather than the generic customer one.
	"""
	dashboard = (dashboard_type or "").strip()
	tab = _active_tab(context)

	if tab:
		for skill in SKILLS:
			if dashboard in skill.dashboards and tab in skill.tabs:
				return skill

	for skill in SKILLS:
		if dashboard in skill.dashboards and not skill.tabs:
			return skill

	return None


def _present_keys(context: Optional[Dict[str, Any]]) -> List[str]:
	"""Top-level data keys actually present, so the model knows where to look."""
	if not isinstance(context, dict):
		return []
	keys: List[str] = []
	for key, value in context.items():
		if isinstance(value, dict):
			keys.extend(f"{key}.{sub}" for sub in list(value.keys())[:24])
		else:
			keys.append(key)
	return keys[:80]


def render_skill(skill: AnalysisSkill, context: Optional[Dict[str, Any]] = None) -> str:
	"""Render a skill as a prompt block."""
	lines = [
		f"## Active analysis skill: {skill.title}",
		skill.focus,
		"",
	]

	if skill.reads:
		lines.append(f"Read first: {', '.join(skill.reads)}")

	present = _present_keys(context)
	if present:
		lines.append(f"Keys present in DASHBOARD DATA: {', '.join(present)}")
	lines.append("")

	if skill.questions:
		lines.append("Answer these:")
		lines.extend(f"- {q}" for q in skill.questions)
		lines.append("")

	if skill.signals:
		lines.append("Interpretation rules:")
		lines.extend(f"- {s}" for s in skill.signals)
		lines.append("")

	if skill.outline:
		lines.append("Structure the reply as:")
		lines.extend(f"{i}. {section}" for i, section in enumerate(skill.outline, 1))
		lines.append("")

	lines.extend(
		[
			"Grounding rules:",
			"- Every figure you state must come from DASHBOARD DATA. Never invent or estimate one.",
			"- Quote real numbers with their units and currency.",
			"- If a figure this skill asks for is missing, name it as missing and continue.",
			"- Prefer specifics over adjectives: name the account, territory, item or rep.",
		]
	)

	return "\n".join(lines)


def skill_prompt_for(dashboard_type: str, context: Optional[Dict[str, Any]] = None) -> str:
	"""Convenience wrapper: select and render in one call. Empty when no match."""
	skill = select_skill(dashboard_type, context)
	return render_skill(skill, context) if skill else ""
