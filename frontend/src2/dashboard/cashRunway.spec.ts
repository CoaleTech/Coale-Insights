import { describe, expect, it } from 'vitest'
import { formatCount } from '../utils/format'

/**
 * The cash-runway sublabel, as implemented in `FinancialIntelligence.vue`.
 *
 * `financial_intelligence.py:272` returns `999` when net burn is zero or
 * negative. That is a flag meaning "not consuming cash", not a measurement, and
 * the card multiplied it by 30 and printed "29970 days runway" -- an 82-year
 * forecast stated as fact, to the day, from monthly averages. This was only
 * visible on screen; every gate passed while it shipped.
 */
function cashRunwayLabel(months: number | null | undefined): string | undefined {
	if (months === null || months === undefined || !Number.isFinite(months)) return undefined
	if (months >= 999) return 'no net cash burn'
	return `${formatCount(months, { decimals: 1 })} months runway`
}

describe('cash runway sublabel', () => {
	it('names the no-burn case instead of forecasting 82 years', () => {
		expect(cashRunwayLabel(999)).toBe('no net cash burn')
		expect(cashRunwayLabel(999)).not.toMatch(/\d+\s*(days|months)/)
	})

	it('reports a real runway in months, the unit the server measures', () => {
		// The strategic engine reports this concept as 49.6 months. Converting to
		// days put two different units for one metric on the same screen.
		expect(cashRunwayLabel(49.6)).toBe('49.6 months runway')
		// `formatCount` caps fraction digits rather than padding them, so a whole
		// number of months reads "3 months", not "3.0 months".
		expect(cashRunwayLabel(3)).toBe('3 months runway')
	})

	it('omits the sublabel entirely when the server sent nothing', () => {
		// `undefined` makes KpiCard drop the row rather than print "0 days runway".
		expect(cashRunwayLabel(undefined)).toBeUndefined()
		expect(cashRunwayLabel(null)).toBeUndefined()
		expect(cashRunwayLabel(Number.NaN)).toBeUndefined()
	})

	it('treats anything at or above the sentinel as no burn', () => {
		// Guards a future change that raises the sentinel.
		expect(cashRunwayLabel(1200)).toBe('no net cash burn')
		expect(cashRunwayLabel(Number.POSITIVE_INFINITY)).toBeUndefined()
	})

	it('keeps a genuinely short runway legible, which is the case that matters', () => {
		expect(cashRunwayLabel(0)).toBe('0 months runway')
		expect(cashRunwayLabel(1.4)).toBe('1.4 months runway')
	})
})
