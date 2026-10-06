import { NO_VALUE } from '../../utils/format'
/**
 * Date/period formatters and helpers for the Financial actuals tabs.
 *
 * The old `formatCurrency` this file exported (a different locale and symbol
 * style) was retired: every consumer now imports `formatMoney` from
 * `../../utils/format` directly (aliased to `formatCurrency` at the import site
 * where the shorter name reads better), so one currency vocabulary is used
 * everywhere on this surface.
 *
 * `formatForeignCurrency` is unrelated to that fork — it renders a value
 * that is already in a *different* currency (e.g. USD exposure on an INR
 * company), so it deliberately keeps its own explicit currency code and
 * en-US notation, matching `formatMoney`'s locale.
 */

export const formatForeignCurrency = (value: number | undefined, currency: string) => {
	if (value === undefined || value === null) return NO_VALUE
	return new Intl.NumberFormat('en-US', {
		style: 'currency',
		currency,
		minimumFractionDigits: 0,
		maximumFractionDigits: 0,
	}).format(value)
}

/**
 * Re-exported rather than redefined: this file previously carried its own
 * byte-identical copy, which is how the surface ended up with thirteen.
 */
export { formatDate } from '../../utils/format'

export const formatPeriod = (period: string) => {
	if (!period) return ''
	const [year, month] = period.split('-')
	const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
	return `${monthNames[parseInt(month) - 1]} ${year.slice(2)}`
}

/** 90+ days overdue amount from an aging bucket list (AR or AP). */
export const get90PlusOverdue = (buckets: Array<{ bucket: string; amount: number }> | undefined) => {
	if (!buckets) return 0
	const bucket90Plus = buckets.find(b => b.bucket === '90+ Days' || b.bucket === '90+')
	return bucket90Plus?.amount || 0
}

/** Whole-day label for an average that may be absent (no overdue invoices, no data). */
export const formatDays = (value: number | null | undefined) =>
	Number.isFinite(value) ? `${Math.round(value as number)} days` : NO_VALUE

/** GL control-account balance worth showing: only when it parts from the invoice total. */
export const glBalanceDiffers = (gl: number | null | undefined, total: number | undefined) =>
	Number.isFinite(gl) && Math.abs((gl as number) - (total ?? 0)) >= 1
