/**
 * Payload of `insights.api.ml.tax.tax_intelligence`, mirroring the backend
 * contract. `null` always means "not derivable from this site's data" and is
 * rendered as `-`, never as 0.
 */
export type Num = number | null

export type ChipTone = 'pos' | 'warn' | 'neg' | 'mut' | 'acc'
export interface Chip {
	tone: ChipTone
	label: string
}

export interface Drill {
	metric: string
	filters?: Record<string, unknown>
}

export interface Kpi {
	key: string
	label: string
	value: number | string | null
	unit: 'money' | 'pct' | 'count' | 'text' | 'date'
	sub?: string | null
	tone?: 'neutral' | 'warn' | 'bad' | 'good'
	drill?: Drill
}

export interface Unavailable {
	available: false
	message: string
	kpis: Kpi[]
}

interface Base {
	available: true
	kpis: Kpi[]
}

export interface LabelAmount {
	label: string
	amount: Num
}

export interface Rates {
	law_basis: string
	vat_rate: number
	vat_registration_threshold: number
	input_vat_window_months: number
	cit_rate: number
	tot_rate: number
	tot_min: number
	tot_max: number
	sep_rate: number
	cgt_rate: number
	idf_rate: number
	rdl_rate: number
	shif_rate: number
	shif_min: number
	ahl_rate: number
	nita_per_employee: number
	nssf_lel: number
	nssf_uel: number
	personal_relief: number
	amnesty_deadline: string
	wht_rate_card: { kind: string; payment: string; resident: Num; non_resident: Num }[]
	penalty_reference: { breach: string; penalty: string }[]
}

export interface OverviewData extends Base {
	deadlines: {
		date: string
		weekday: string
		title: string
		sub: string
		amount: Num
		chip: Chip
		tax_key?: string
	}[]
	amnesty: {
		deadline: string
		scope_end: string
		days_left: Num
		principal_total: Num
		principal_paid: Num
		principal_outstanding: Num
		penalty_interest_waivable: Num
		by_tax: { tax: string; amount: Num }[]
	}
	liabilities: { tax: string; label: string; amount: Num }[]
	monthly: { month: string; due: Num; paid: Num }[]
	filing_status: { obligation: string; period: string; due: string | null; chip: Chip }[]
}

export interface VatData extends Base {
	monthly: { month: string; output: Num; input: Num; net: Num }[]
	supply_mix: { key: string; label: string; taxable_value: Num; share_pct: Num; note?: string }[]
	input_risk: {
		reason: string
		invoices: Num
		input_vat: Num
		action_label?: string
		drill?: Drill
	}[]
	suppliers_at_risk: {
		supplier: string
		invoices: Num
		input_vat_at_risk: Num
		oldest_date: string | null
		window_closes: string | null
		days_left: Num
		chip: Chip
		drill?: Drill
	}[]
	reverse_charge: { amount: Num; note: string }
}

export interface EtimsData extends Base {
	coverage_trend: { week: string; pct: Num }[]
	exposure: {
		spend_without_invoice: Num
		income_tax_disallowance: Num
		input_vat_lost: Num
		cit_rate: Num // fraction (0.30)
		total: Num
	}
	exceptions: {
		document: string
		doctype: string
		counterparty: string | null
		amount: Num
		issue_chip: Chip
		age_days: Num
		exposure: Num
		action_label?: string
		drill?: Drill
	}[]
	exception_total: number
	failure_reasons: { label: string; count: Num }[]
	by_channel: { label: string; count: Num }[]
	penalty_reference: { breach: string; penalty: string }[]
}

export interface PayrollData extends Base {
	/** YYYY-MM of the slip period the figures describe. */
	month: string
	monthly: { month: string; paye: Num; other: Num }[]
	bands: { label: string; rate: Num; headcount: Num }[]
	schedule: { remittance: string; rule: string; due_date: string | null; amount: Num; chip: Chip }[]
	cost: LabelAmount[]
	exceptions: { check: string; employees: Num; impact: string | number | null; drill?: Drill }[]
}

export interface WhtData extends Base {
	by_type: { kind: string; label: string; amount: Num; note?: string }[]
	unremitted: {
		payment: string
		payee: string
		withheld: Num
		deducted_on: string | null
		due_on: string | null
		days_late: Num
		chip: Chip
		drill?: Drill
	}[]
	rate_exceptions: {
		payment: string
		payee: string
		gross: Num
		expected_rate: Num
		applied_rate: Num
		chip: Chip
		drill?: Drill
	}[]
	rate_card: { kind: string; payment: string; resident: Num; non_resident: Num }[]
	watch: { card_fees_amount: Num; note: string }
	unremitted_total?: number
	rate_exceptions_total?: number
	exception_total?: number
	exceptions?: unknown[]
}

export interface IncomeData extends Base {
	instalments: {
		label: string
		due_date: string | null
		required: Num
		paid: Num
		chip: Chip
	}[]
	bridge: { label: string; amount: Num; kind: 'base' | 'add' | 'less' }[]
	losses: {
		year: number | string
		amount: Num
		used: Num
		remaining: Num
		lapses_on: string | null
		chip: Chip
	}[]
	tot: {
		applicable: boolean
		trailing_12m_turnover: Num
		ceiling: Num
		pct_of_ceiling: Num
		note: string
	}
	key_dates: { date: string; title: string; sub?: string }[]
	wht_credits: { matched: Num; unmatched: Num }
	cgt: { disposal: string; gain: Num; cgt: Num }[]
	instalment_base?: { prior_year_tax: Num; current_estimate: Num; annual_required: Num; next: string | null }
	/** Data caveats, shown as muted footnotes. */
	notes?: string[]
}

export interface LegalData extends Base {
	stages: { label: string; count: Num; note?: string }[]
	cases: {
		case_ref: string
		tax_type: string
		period_label: string
		principal: Num
		penalty_interest: Num
		stage_chip: Chip
		next_step: string | null
		next_date: string | null
		days_left: Num
		drill?: Drill
	}[]
	dates: { date: string; weekday: string; title: string; sub?: string; chip: Chip }[]
	amnesty_by_tax: { tax: string; amount: Num }[]
}

export interface CustomsData extends Base {
	landed: LabelAmount[]
	entries: {
		entry: string
		supplier: string
		cif: Num
		duty: Num
		idf: Num
		rdl: Num
		vat: Num
		chip: Chip
		drill?: Drill
	}[]
	excise: { item: string; basis: string; rate: string; amount: Num }[]
	digital_services: { supplier: string; service: string; tax_note: string; amount: Num }[]
}

export interface ActionsData extends Base {
	rows: {
		priority: 'critical' | 'high' | 'medium'
		chip: Chip
		action: string
		tax: string
		tax_key?: string
		owner: string | null
		due_date: string | null
		due_label: string | null
		exposure: Num
		button_label: string
		source_tab: string
		drill?: Drill
	}[]
	total_open: number
	by_tax: { label: string; count: Num }[]
	by_priority_7d: { label: string; count: Num }[]
	rules: { rule: string; hits: Num }[]
}

export type TabId =
	| 'overview'
	| 'vat'
	| 'etims'
	| 'payroll'
	| 'wht'
	| 'income'
	| 'legal'
	| 'customs'
	| 'actions'

export interface TaxPayload {
	status: string
	generated_at: string
	company: string
	base_currency: string | null
	period: { key: string; name: string; start_date: string; end_date: string }
	today: string
	rates: Rates
	tabs: {
		overview: OverviewData | Unavailable
		vat: VatData | Unavailable
		etims: EtimsData | Unavailable
		payroll: PayrollData | Unavailable
		wht: WhtData | Unavailable
		income: IncomeData | Unavailable
		legal: LegalData | Unavailable
		customs: CustomsData | Unavailable
		actions: ActionsData | Unavailable
	}
	badges: { etims: number; payroll: number; wht: number; legal: number; actions: number }
}
