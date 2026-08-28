import { describe, expect, it } from 'vitest'
import {
	CUSTOM_RANGE_PREFIX,
	CUSTOM_RANGE_VALUE,
	DEFAULT_DATE_RANGES,
	FISCAL_PERIOD_RANGES,
	decodeCustomRange,
	encodeCustomRange,
	isCustomRange,
} from './dateRangePresets'

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

/**
 * `encodeCustomRange`/`decodeCustomRange` must stay byte-for-byte compatible
 * with the backend's `insights.api.ml.utils.parse_custom_range` grammar
 * (`custom:<start>:<end>`, ISO `YYYY-MM-DD`), since every intelligence
 * dashboard's period resolver decodes a value this component emitted.
 */
describe('encodeCustomRange / decodeCustomRange', () => {
	it('round-trips a valid range through encode then decode', () => {
		const range = { start: '2026-01-01', end: '2026-02-15' }
		expect(decodeCustomRange(encodeCustomRange(range))).toEqual(range)
	})

	it('encodes with the backend-recognised custom: prefix', () => {
		expect(encodeCustomRange({ start: '2026-01-01', end: '2026-02-15' })).toBe(
			'custom:2026-01-01:2026-02-15',
		)
	})

	it('decodes null for values without the custom: prefix', () => {
		expect(decodeCustomRange('12m')).toBeNull()
		expect(decodeCustomRange('all')).toBeNull()
		// CUSTOM_RANGE_VALUE is a local-only <select> sentinel, never the
		// encoded form -- it must not be mistaken for one.
		expect(decodeCustomRange(CUSTOM_RANGE_VALUE)).toBeNull()
	})

	it('decodes null when start or end is missing', () => {
		expect(decodeCustomRange(`${CUSTOM_RANGE_PREFIX}2026-01-01`)).toBeNull()
		expect(decodeCustomRange(`${CUSTOM_RANGE_PREFIX}:`)).toBeNull()
	})

	it('isCustomRange only matches the custom: prefix, not the select sentinel', () => {
		expect(isCustomRange('custom:2026-01-01:2026-02-15')).toBe(true)
		expect(isCustomRange(CUSTOM_RANGE_VALUE)).toBe(false)
		expect(isCustomRange('12m')).toBe(false)
	})
})
