/**
 * Shared payload shapes for the Financial actuals tabs, sourced from
 * `insights.api.ml.financial_intelligence`. Mirrors the pattern in
 * `components/strategic-finance/types.ts`: the shell fetches one response
 * and passes each section down as a typed `data` prop.
 */

/** One row of monthly_trend. */
export interface MonthlyTrendRow {
	period: string
	revenue: number
	expenses?: number
	profit: number
	margin?: number | string
}

/** One row of expense_breakdown. */
export interface ExpenseRow {
	category: string
	amount: number
	pct: number
}

export interface OverviewData {
	ytd_revenue?: number
	ytd_expenses?: number
	ytd_profit?: number
	ytd_gross_profit?: number
	net_margin?: number
	monthly_trend?: MonthlyTrendRow[]
	expense_breakdown?: ExpenseRow[]
}

/**
 * One bank/cash/deposit account row. `account_class` is decided by the server
 * (`_calculate_cash_flow`) because ERPNext has no deposit account_type and the
 * name match that stands in for one belongs in exactly one place.
 */
export interface CashAccountRow {
	account: string
	account_name: string
	account_type: string
	account_class?: string
	is_fd?: boolean
	balance: number
	share_pct?: number | null
}

/** One month of GL-derived cash movement, closing balance included. */
export interface CashMovementRow {
	period: string
	inflow: number
	outflow: number
	net: number
	closing?: number
}

/** One month of deposit movement. */
export interface DepositMonthRow {
	period: string
	placed: number
	released: number
	net: number
	closing?: number
}

/** One deposit placement or release, as posted. */
export interface DepositActivityRow {
	posting_date: string
	voucher_no?: string
	amount: number
	direction: 'placement' | 'release'
	/** Bank deposit receipt number quoted in the journal remarks, if any. */
	reference?: string | null
}

/**
 * Everything the ledger can say about fixed deposits. Absent (`null`) when the
 * chart of accounts has no deposit account at all.
 *
 * Maturity date, tenor and contracted rate are not here because ERPNext does
 * not store them: `Account.account_type` has no term-deposit option and the
 * schema's only native mention of one is `Bank Guarantee.fixed_deposit_number`.
 */
export interface FixedDepositData {
	balance: number
	pct_of_cash?: number | null
	accounts?: Array<{ account: string; account_name: string; balance: number }>
	monthly?: DepositMonthRow[]
	window_months?: number
	placed?: number
	released?: number
	placement_count?: number
	release_count?: number
	avg_ticket?: number | null
	last_placement?: string | null
	last_release?: string | null
	swept_with?: string[]
	recent_activity?: DepositActivityRow[]
	interest_booked_fy?: number
	interest_accrued?: number
	fiscal_year?: string
	yield_pct?: number | null
}

/** Cash movement posted with a future date (post-dated cheques). */
export interface PostDatedCash {
	entries: number
	net: number
	last_date?: string | null
}

/** One row in monthly_inflows. */
export interface MonthlyCashRow {
	period: string
	amount: number
}

/** One large cash transaction (Payment Entry) in the last 30 days. */
export interface LargeTransactionRow {
	name: string
	posting_date: string
	payment_type: string
	party_type: string
	party: string
	paid_amount: number
	reference_no?: string
}

export interface CashFlowData {
	as_of?: string
	total_cash?: number
	bank_balance?: number
	cash_on_hand?: number
	fd_balance?: number
	liquid_cash?: number
	avg_monthly_inflow?: number
	avg_monthly_outflow?: number
	net_burn_rate?: number
	runway_months?: number
	cash_accounts?: CashAccountRow[]
	monthly_cash_movement?: CashMovementRow[]
	post_dated?: PostDatedCash | null
	fixed_deposits?: FixedDepositData | null
	monthly_inflows?: MonthlyCashRow[]
	monthly_outflows?: MonthlyCashRow[]
	inflow_by_source?: Array<{ source: string; amount: number }>
	outflow_by_use?: Array<{ category: string; amount: number }>
	large_transactions?: LargeTransactionRow[]
}

/** One aging bucket row (AR or AP). */
export interface AgingBucket {
	bucket: string
	amount: number
	count: number
}

/** One overdue customer row. */
export interface OverdueCustomerRow {
	customer: string
	customer_name?: string
	total_outstanding: number
	invoice_count: number
	max_overdue_days: number
}

export interface ReceivablesData {
	total_outstanding?: number
	current_dso?: number
	invoice_count?: number
	aging_buckets?: AgingBucket[]
	overdue_customers?: OverdueCustomerRow[]
}

/** One top supplier row. */
export interface TopSupplierRow {
	supplier: string
	supplier_name?: string
	total_outstanding: number
	invoice_count: number
}

export interface PayablesData {
	total_outstanding?: number
	current_dpo?: number
	invoice_count?: number
	aging_buckets?: AgingBucket[]
	top_suppliers?: TopSupplierRow[]
}

/** One row of exposure_summary (forex by currency). */
export interface ForexExposureRow {
	currency: string
	receivable: number
	payable: number
	net_exposure: number
	current_rate: number
	net_exposure_base: number
	position: string
}

/** One at-risk foreign currency invoice. */
export interface AtRiskInvoice {
	name: string
	doctype: string
	party: string
	currency: string
	outstanding_amount: number
	conversion_rate: number
	due_date: string
	days_to_due: number
}

export interface ForexData {
	net_exposure_base?: number
	total_receivable_base?: number
	total_payable_base?: number
	net_unrealized?: number
	exposure_summary?: ForexExposureRow[]
	at_risk_invoices?: AtRiskInvoice[]
}
