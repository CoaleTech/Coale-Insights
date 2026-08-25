import { describe, expect, it } from 'vitest'
import { DEFAULT_DATE_RANGES, FISCAL_PERIOD_RANGES } from './dateRangePresets'

/**
 * Every `DEFAULT_DATE_RANGES` value is sent verbatim as `date_filter` to
 * `insights.api.ml.utils.parse_date_filter`, which only recognises
 * `Nd` / `Nm` / `Ny` / `ytd` / `all` -- anything else silently falls back to
 * a 365-day window with no error, so a typo here would misreport every
 * dashboard driven by it (Financial, Revenue & Customers, Inventory) without
 * ever surfacing as a bug.
 */
describe('DEFAULT_DATE_RANGES', () => {
	it('every value parses under parse_date_filter\'s supported grammar', () => {
		for (const { value } of DEFAULT_DATE_RANGES) {
			expect(value).toMatch(/^(\d+[dmy]|ytd|all)$/)
		}
	})

	it('has no duplicate values or blank labels', () => {
		const values = DEFAULT_DATE_RANGES.map((r) => r.value)
		expect(new Set(values).size).toBe(values.length)
		for (const { label } of DEFAULT_DATE_RANGES) {
			expect(label.trim()).not.toBe('')
		}
	})
})

/**
 * `FISCAL_PERIOD_RANGES` values are matched by string equality against
 * `MTD` / `QTD` / `YTD` in three independent backend resolvers
 * (`marketing._period_start`, `hr_intelligence._period_start_date`, and
 * executive's period plumbing); anything else falls back to trailing-12-months
 * treatment. A typo'd or re-cased token (e.g. `Ytd`) would silently render as
 * TTM data under a YTD label rather than failing loudly.
 */
describe('FISCAL_PERIOD_RANGES', () => {
	it('is exactly MTD/QTD/YTD/TTM, matching every backend period resolver', () => {
		expect(FISCAL_PERIOD_RANGES.map((r) => r.value)).toEqual(['MTD', 'QTD', 'YTD', 'TTM'])
	})
})
