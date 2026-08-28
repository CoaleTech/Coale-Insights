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
 * styling, or accessibility. That component also always offers a fourth,
 * cross-cutting "Custom Range" choice on top of whichever preset set it
 * is given -- see `encodeCustomRange`/`decodeCustomRange` below -- which
 * every backend period resolver in every one of those endpoint families
 * honours ahead of its own preset table (`insights.api.ml.utils.parse_custom_range`
 * is the one place that decodes it).
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

/**
 * Explicit "from / to" date range support, layered onto every dashboard by
 * `IntelligenceDateFilter` regardless of which preset set it renders.
 *
 * `custom:<start>:<end>` (ISO `YYYY-MM-DD` dates) is the one encoding every
 * backend period resolver understands -- see
 * `insights.api.ml.utils.parse_custom_range` for the authoritative grammar
 * this must stay byte-for-byte compatible with. `CUSTOM_RANGE_VALUE` is a
 * separate, purely local sentinel: it never leaves `IntelligenceDateFilter`
 * or reaches the backend, it only tells that component's own `<select>`
 * "show the custom-range option as selected" without needing a `start`/`end`
 * pair to already exist.
 */
export const CUSTOM_RANGE_PREFIX = 'custom:'
export const CUSTOM_RANGE_VALUE = '__custom_range__'

export interface CustomDateRange {
	/** ISO `YYYY-MM-DD` */
	start: string
	/** ISO `YYYY-MM-DD` */
	end: string
}

export function isCustomRange(value: string): boolean {
	return value.startsWith(CUSTOM_RANGE_PREFIX)
}

export function encodeCustomRange(range: CustomDateRange): string {
	return `${CUSTOM_RANGE_PREFIX}${range.start}:${range.end}`
}

/** Inverse of `encodeCustomRange`. Returns `null` for anything that isn't
 * a well-formed `custom:<start>:<end>` value, mirroring the backend's
 * `parse_custom_range` returning `None` on malformed input rather than
 * throwing. */
export function decodeCustomRange(value: string): CustomDateRange | null {
	if (!isCustomRange(value)) return null
	const [start, end] = value.slice(CUSTOM_RANGE_PREFIX.length).split(':')
	if (!start || !end) return null
	return { start, end }
}
