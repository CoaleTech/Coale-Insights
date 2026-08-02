import { NO_VALUE } from '../../utils/format'
/**
 * Currency/date formatters for the Financial actuals tabs, preserved
 * verbatim from the pre-merge `FinancialIntelligence.vue` monolith.
 *
 * Deliberately kept separate from `utils/format.ts`'s `formatMoney`: that
 * formatter pins compact `en-US` notation, while this dashboard has always
 * shown exact `en-KE` grouped amounts (KES 1,234,567, not KES 1.2M). Not a
 * gap to close as part of this merge — a locale/notation change is a
 * separate product decision.
 */

export const formatCurrency = (value: number | undefined, currency: string) => {
	// Absent is not zero: this returned `${currency} 0`, reporting zero money for
	// a field the server never sent. Notation is untouched, per the note above.
	if (value === undefined || value === null) return NO_VALUE
	return new Intl.NumberFormat('en-KE', {
		style: 'currency',
		currency,
		minimumFractionDigits: 0,
		maximumFractionDigits: 0,
	}).format(value)
}

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
