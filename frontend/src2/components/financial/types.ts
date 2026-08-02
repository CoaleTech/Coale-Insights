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

/** One bank/cash account row. */
export interface CashAccountRow {
	account: string
	account_name: string
	account_type: string
	balance: number
}

/** One row in monthly_inflows. */
export interface MonthlyCashRow {
	period: string
	amount: number
}

export interface CashFlowData {
	total_cash?: number
	avg_monthly_inflow?: number
	avg_monthly_outflow?: number
	runway_months?: number
	cash_accounts?: CashAccountRow[]
	monthly_inflows?: MonthlyCashRow[]
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
