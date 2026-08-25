/**
 * Shared period/date-range option sets for intelligence dashboard filters.
 *
 * Two sets, because the backends they drive parse genuinely different
 * vocabularies -- this is not accidental duplication:
 *
 *   - `DEFAULT_DATE_RANGES` (7d/30d/.../all): rolling lookback windows
 *     parsed by `insights.api.ml.utils.parse_date_filter`. Drives
 *     Financial Intelligence, Revenue & Customers Intelligence, and
 *     Inventory Intelligence.
 *   - `FISCAL_PERIOD_RANGES` (MTD/QTD/YTD/TTM): calendar/fiscal period
 *     keywords resolved against the current date server-side. Drives
 *     Executive Dashboard, HR Intelligence, and Marketing & CRM
 *     Intelligence, which used to each hand-roll an identical copy of
 *     this exact four-item array.
 *
 * Tax Intelligence uses a third, tax-specific set (3m/6m/12m/fy, coerced
 * server-side by `insights.api.ml.tax._coerce_period`) that only one
 * dashboard needs, so it stays local to TaxIntelligence.vue: it is a real
 * business vocabulary, not drift, and folding it into either set here
 * would offer values its backend silently discards.
 *
 * Every dashboard renders its set through the same shared
 * `IntelligenceDateFilter` component (`options` prop), so only the value
 * vocabulary differs across dashboards -- never the picker markup,
 * styling, or accessibility.
 */

export interface DateRangeOption {
	value: string
	label: string
}

export const DEFAULT_DATE_RANGES: DateRangeOption[] = [
	{ value: '7d', label: 'Last 7 Days' },
	{ value: '30d', label: 'Last 30 Days' },
	{ value: '90d', label: 'Last 90 Days' },
	{ value: '6m', label: 'Last 6 Months' },
	{ value: '12m', label: 'Last 12 Months' },
	{ value: '24m', label: 'Last 24 Months' },
	{ value: 'all', label: 'All Time' },
]

export const FISCAL_PERIOD_RANGES: DateRangeOption[] = [
	{ value: 'MTD', label: 'Month to Date' },
	{ value: 'QTD', label: 'Quarter to Date' },
	{ value: 'YTD', label: 'Year to Date' },
	{ value: 'TTM', label: 'Trailing 12 Months' },
]
