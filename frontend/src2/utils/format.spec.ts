import { describe, expect, it } from 'vitest'
import { formatCount, formatMoney, formatPercent } from './format'

/**
 * Guards the four bugs that existed across six hand-rolled formatters before
 * this module replaced them. Each `it` below corresponds to a defect that was
 * shipping on real dashboards, so these are regression locks, not coverage.
 */
describe('formatMoney', () => {
	it('formats negative money instead of dropping through every branch', () => {
		// The old helpers tested `value >= 1_000_000` without Math.abs, so any
		// negative amount matched no branch and fell out raw and ungrouped.
		expect(formatMoney(-5_000_000, 'INR', { compact: true })).toBe('-₹5M')
		expect(formatMoney(-1234.56, 'INR', { compact: true })).toBe('-₹1.2K')
		expect(formatMoney(-5_000_000, 'INR')).toBe('-₹5,000,000')
	})

	it('treats exactly one million as compact', () => {
		// ExecutiveReports used `>` not `>=`, so 1000000 skipped the compact branch.
		expect(formatMoney(1_000_000, 'INR', { compact: true })).toBe('₹1M')
	})

	it('uses the currency it is given and never a hardcoded default', () => {
		// Three helpers defaulted to 'KES' and one hardcoded '$', which is how
		// `Ksh 713,447,224` and `$`-prefixed figures reached an INR company.
		//
		// The \u00a0 is deliberate: Intl separates a symbol-less code from its
		// number with a non-breaking space so the two never wrap apart. Symbol
		// currencies get no separator at all.
		expect(formatMoney(1_500, 'INR')).toBe('₹1,500')
		expect(formatMoney(1_500, 'KES')).toBe('KES\u00a01,500')
		expect(formatMoney(1_500, 'USD')).toBe('$1,500')
	})

	it('renders zero rather than an empty string', () => {
		expect(formatMoney(0, 'INR')).toBe('₹0')
	})

	it('reports an absent amount as absent, not as zero money', () => {
		// Reversed deliberately. These originally asserted `₹0`, which encoded the
		// exact defect this vocabulary exists to remove: a payload missing a field
		// rendered as a confident measurement. `format.ts` was also split against
		// itself, since its date formatters already returned a dash.
		expect(formatMoney(null, 'INR')).toBe('-')
		expect(formatMoney(undefined, 'INR')).toBe('-')
		expect(formatMoney(Number.NaN, 'INR')).toBe('-')
		expect(formatMoney(Number.POSITIVE_INFINITY, 'INR')).toBe('-')
	})

	it('keeps a real zero as zero money', () => {
		// The distinction that matters: nothing measured versus measured as nothing.
		expect(formatMoney(0, 'INR')).toBe('₹0')
	})

	it('degrades instead of throwing on an invalid currency code', () => {
		// Intl throws RangeError on a malformed code. A dashboard must not blank
		// out because a site returned something unexpected.
		expect(formatMoney(316_871_197, 'not-a-code', { compact: true })).toBe(
			'not-a-code\u00a0316.9M',
		)
		expect(formatMoney(316_871_197, '', { compact: true })).toBe('316.9M')
		expect(formatMoney(316_871_197, null, { compact: true })).toBe('316.9M')
	})

	it('passes through an unknown but well-formed ISO code', () => {
		expect(formatMoney(5_000_000, 'XYZ', { compact: true })).toBe('XYZ\u00a05M')
	})

	it('is compact only when asked, since exact is the desktop default', () => {
		expect(formatMoney(316_871_197, 'INR')).toBe('₹316,871,197')
		expect(formatMoney(316_871_197, 'INR', { compact: true })).toBe('₹316.9M')
	})

	it('shortens enough to fit a phone KPI track', () => {
		// The reason compact exists: this value clipped inside a 160px card.
		expect(formatMoney(316_871_197, 'INR', { compact: true }).length).toBeLessThan(
			formatMoney(316_871_197, 'INR').length,
		)
	})

	it('accepts a lowercase or padded currency code', () => {
		expect(formatMoney(1_500, 'inr')).toBe('₹1,500')
		expect(formatMoney(1_500, ' INR ')).toBe('₹1,500')
	})
})

describe('formatCount', () => {
	it('groups plain numbers', () => {
		expect(formatCount(890)).toBe('890')
		expect(formatCount(13_500)).toBe('13,500')
	})

	it('compacts on request', () => {
		expect(formatCount(13_500, { compact: true })).toBe('13.5K')
	})

	it('reports an absent count as absent, but keeps a real zero', () => {
		expect(formatCount(null)).toBe('-')
		expect(formatCount(undefined)).toBe('-')
		expect(formatCount(Number.NaN)).toBe('-')
		expect(formatCount(0)).toBe('0')
	})

	it('honours a decimal count', () => {
		expect(formatCount(3.14159, { decimals: 2 })).toBe('3.14')
	})
})

describe('formatPercent', () => {
	it('treats input as already on a 0-100 scale', () => {
		// Every endpoint on this surface returns 88.9 for 88.9%, not 0.889.
		expect(formatPercent(88.9)).toBe('88.9%')
		expect(formatPercent(3.9)).toBe('3.9%')
	})

	it('keeps a trailing zero so columns stay aligned', () => {
		expect(formatPercent(50)).toBe('50.0%')
	})

	it('honours an explicit precision', () => {
		expect(formatPercent(23.6666, 2)).toBe('23.67%')
		expect(formatPercent(23.6666, 0)).toBe('24%')
	})

	it('reports an absent percentage as absent, but keeps a real zero', () => {
		expect(formatPercent(null)).toBe('-')
		expect(formatPercent(undefined)).toBe('-')
		expect(formatPercent(0)).toBe('0.0%')
	})
})
