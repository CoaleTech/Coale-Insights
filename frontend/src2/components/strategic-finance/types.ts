/**
 * Shared payload contract for the Strategic Finance surface.
 *
 * `FinancialIntelligence.vue` (the merged Finance dashboard's "Planning"
 * group) fetches one response and passes each section down as a `data` prop
 * to a tab component. A Vue SFC cannot export a
 * type, so the shell and the tabs cannot otherwise agree on those shapes: the
 * shell saw `Record<string, unknown>`, every `data?.section` was `unknown`, and
 * each typed tab prop rejected it.
 *
 * One module, imported by both sides, is what makes the two views agree.
 *
 * Row-level shapes local to a single tab stay in that tab. Only shapes that
 * cross the shell boundary belong here.
 */

// ---------------------------------------------------------------------------
// Executive summary
// ---------------------------------------------------------------------------

export interface ExecutiveSummaryData {
	ytd_revenue?: number
	ytd_expenses?: number
	ytd_net_income?: number
	cash_balance?: number
	revenue_growth?: number
	net_margin?: number
	cash_runway_months?: number
	kpis?: Array<{ label: string; value: number; format: string; subtitle?: string }>
	monthly_trends?: Array<{
		period: string
		revenue: number
		expenses: number
		net_income: number
		margin: number
	}>
	health_scores?: {
		liquidity: number
		liquidity_status: string
		profitability: number
		profitability_status: string
		efficiency: number
		efficiency_status: string
	}
	key_insights?: Array<{ type: string; title: string; description: string }>
}

// ---------------------------------------------------------------------------
// Cash forecasting
// ---------------------------------------------------------------------------

export interface CashForecastData {
	current_cash?: number
	expected_ar_inflows?: number
	expected_ap_outflows?: number
	net_expected?: number
	base_forecast?: unknown[]
	optimistic_forecast?: unknown[]
	pessimistic_forecast?: unknown[]
	end_of_period?: { optimistic?: number; base?: number; pessimistic?: number }
	optimistic_runway_days?: number
	base_runway_days?: number
	pessimistic_runway_days?: number
	avg_daily_flow?: number
	weekly_summary?: Array<{
		week: number
		base_balance: number
		optimistic_balance: number
		pessimistic_balance: number
	}>
}

// ---------------------------------------------------------------------------
// 13-week rolling cash flow
// ---------------------------------------------------------------------------

export interface ThirteenWeekRow {
	week_number: number
	week_label: string
	week_start: string
	is_actual: boolean
	is_forecast: boolean
	is_current: boolean
	below_threshold: boolean
	opening_balance: number
	closing_balance: number
	net_flow: number
	inflows?: { total: number; ar_collections: number; other_receipts: number }
	outflows?: {
		total: number
		ap_payments: number
		payroll: number
		operating_expenses: number
		taxes: number
	}
	variance?: { net: number }
}

export interface ThirteenWeekData {
	opening_balance?: number
	min_cash_threshold?: number
	payroll_detection?: {
		detected: boolean
		frequency: string
		typical_amount: number
		next_date: string
		confidence: number
	}
	summary?: {
		total_inflows: number
		total_outflows: number
		ending_cash: number
		minimum_balance: number
		minimum_balance_week: number
		weeks_below_threshold: number
	}
	weeks?: ThirteenWeekRow[]
	scenarios?: unknown
	variance_analysis?: unknown
}

// ---------------------------------------------------------------------------
// Capital planning
// ---------------------------------------------------------------------------

export interface AssetCategoryRow {
	name: string
	value: number
	percentage: number
}

export interface AssetAgeRow {
	bucket: string
	count: number
	percentage: number
	value?: number
}

export interface DepreciationForecastRow {
	period: string
	amount: number
}

export interface CapitalPlanningData {
	total_assets?: number
	ytd_capex?: number
	annual_depreciation?: number
	maintenance_costs?: number
	asset_categories?: AssetCategoryRow[]
	age_distribution?: AssetAgeRow[]
	depreciation_forecast?: DepreciationForecastRow[]
	attention_required?: Array<{ asset_name: string; reason: string; value?: number }>
	recommendations?: Array<{ title: string; description: string; priority?: string }>
}

// ---------------------------------------------------------------------------
// Working capital
// ---------------------------------------------------------------------------

export interface WorkingCapitalTrendRow {
	month: string
	working_capital?: number
	current_ratio?: number
	dso?: number
	dio?: number
	dpo?: number
}

export interface WorkingCapitalData {
	dso?: number
	dio?: number
	dpo?: number
	cash_conversion_cycle?: number
	current_ratio?: number
	quick_ratio?: number
	working_capital?: number
	cash?: number
	receivables?: number
	inventory?: number
	total_current_assets?: number
	total_current_liabilities?: number
	trends?: WorkingCapitalTrendRow[]
}

// ---------------------------------------------------------------------------
// Financial ratios
// ---------------------------------------------------------------------------

export interface RatioCard {
	name: string
	value?: number
	benchmark?: number
	status?: string
}

export interface RatioTrendRow {
	period: string
	current_ratio?: number
	quick_ratio?: number
	cash_ratio?: number
	gross_margin?: number
	net_margin?: number
	roe?: number
	roa?: number
	asset_turnover?: number
	debt_to_equity?: number
	debt_ratio?: number
	ebitda?: number
	ebitda_margin?: number
	working_capital_turnover?: number
	interest_coverage?: number
	dscr?: number
}

export interface FinancialRatiosData {
	ratio_cards?: RatioCard[]
	trends?: RatioTrendRow[]
	cash_ratio?: number
	cash_ratio_trend?: number
	current_ratios?: RatioTrendRow
}

// ---------------------------------------------------------------------------
// Scenario analysis
// ---------------------------------------------------------------------------

export interface ScenarioEntry {
	name?: string
	revenue?: number
	expenses?: number
	net_income?: number
	probability?: number
}

export interface MonteCarloPercentiles {
	p5?: number
	p25?: number
	p50?: number
	p75?: number
	p95?: number
}

export interface ScenarioData {
	sensitivity?: {
		revenue_changes?: number[]
		expense_changes?: number[]
		matrix?: number[][]
	}
	monte_carlo?: {
		percentiles?: MonteCarloPercentiles
		loss_probability?: number
		iterations?: number
	}
	baseline?: { revenue?: number; expenses?: number; net_income?: number }
	scenarios?: ScenarioEntry[]
}

// ---------------------------------------------------------------------------
// Period comparison
// ---------------------------------------------------------------------------

/**
 * One period's financials.
 *
 * Verified against `insights/ml/strategic_finance/scenarios.py:254-261`
 * (`get_period_financials`), which returns revenue, expenses, net_income and
 * margin, plus a `label` added at line 268.
 */
export interface PeriodMetrics {
	revenue?: number
	expenses?: number
	net_income?: number
	margin?: number
	label?: string
}

/**
 * A single comparison block.
 *
 * `current` and `prior` are NESTED objects, not flattened `current_revenue`
 * fields. Verified against `scenarios.py:277-282`, which builds
 * `{"current": period_data[...], "prior": period_data[...], "revenue_change": ...}`.
 */
export interface PeriodComparison {
	current?: PeriodMetrics
	prior?: PeriodMetrics
	revenue_change?: number
	expense_change?: number
	net_income_change?: number
	/**
	 * Read by the tab template but NOT emitted by `compare_periods` today, so the
	 * insights block never renders. Kept optional rather than dropped so the
	 * existing markup keeps working if the endpoint starts returning it.
	 */
	insights?: Array<{ type: string; title: string; description: string; message?: string }>
}

/** Rows of the `summary` array built at `scenarios.py:306-325`. */
export interface PeriodComparisonSummaryRow {
	comparison: string
	revenue_change?: number
	expense_change?: number
	net_income_change?: number
}

/**
 * Response of `compare_periods` (`scenarios.py:302-326`). Periods are looked up
 * by dynamic key, so the three keys are named explicitly rather than left to an
 * index signature.
 */
export interface PeriodComparisonData {
	period_data?: Record<string, PeriodMetrics>
	summary?: PeriodComparisonSummaryRow[]
	mom?: PeriodComparison
	qoq?: PeriodComparison
	yoy?: PeriodComparison
}

// ---------------------------------------------------------------------------
// Cost structure ratios
// ---------------------------------------------------------------------------

export type CostRatioStatus = 'good' | 'moderate' | 'risky' | 'unknown'

/**
 * One cost-structure benchmark card from `cost_ratios.py:_build_card` —
 * distinct from `RatioCard` (single `benchmark`) because these carry two
 * thresholds (ideal/risky), a unit for formatting, and a rule-based action
 * recommendation rather than a bare status.
 */
export interface CostRatioCard {
	key: string
	name: string
	/** `null` when the underlying figure could not be computed (e.g. no COGS
	 *  accounts posted this period) — never a fabricated estimate. */
	value: number | null
	ideal: number
	risky: number
	unit: 'x' | '%'
	higher_is_better: boolean
	status: CostRatioStatus
	recommendation: string
}

export interface CostStructureFigures {
	revenue: number
	gross_profit: number | null
	net_profit: number
	fixed_cost: number
	salary_cost: number
	marketing_cost: number
	training_cost: number
	incentive_cost: number
	rent_cost: number
	electricity_cost: number
}

/** Response of `calculate_cost_structure_ratios` (`cost_ratios.py`). */
export interface CostStructureData {
	period: { start: string; end: string }
	figures: CostStructureFigures
	overall_status: CostRatioStatus
	ratio_cards: CostRatioCard[]
}

// ---------------------------------------------------------------------------
// Expense forecast
// ---------------------------------------------------------------------------

export interface ExpenseHistoryPoint {
	month: string
	amount: number
}

export interface ExpenseForecastPoint {
	month: string
	projected_amount: number
}

/** Response of `forecast_expenses` (`cost_ratios.py`). */
export interface ExpenseForecastData {
	status: 'success' | 'insufficient_data'
	message?: string
	method?: string
	window_months?: number
	history: ExpenseHistoryPoint[]
	forecast?: ExpenseForecastPoint[]
	trend_direction?: 'rising' | 'falling' | 'flat'
	monthly_change?: number
	note?: string
}

// ---------------------------------------------------------------------------
// Shell payload
// ---------------------------------------------------------------------------

/** The whole response the Strategic Finance shell fetches and fans out. */
export interface StrategicFinanceData {
	executive_summary?: ExecutiveSummaryData | null
	expense_breakdown?: unknown[]
	cash_forecast?: CashForecastData | null
	thirteen_week_forecast?: ThirteenWeekData | null
	capital_planning?: CapitalPlanningData
	working_capital?: WorkingCapitalData
	ratio_trends?: FinancialRatiosData
	scenario_analysis?: ScenarioData
	period_comparison?: PeriodComparisonData
	cost_structure?: CostStructureData
	expense_forecast?: ExpenseForecastData
}
