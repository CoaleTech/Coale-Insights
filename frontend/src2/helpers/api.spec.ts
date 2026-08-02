import { describe, expect, it } from 'vitest'
import { readInsightsEnvelope } from './api'

/**
 * The single point every dashboard's data passes through, and it had no test.
 *
 * `insights.api.*` endpoints return three different shapes, and the decoder
 * silently mishandled one of them: `risk_intelligence` puts `status` at the top
 * level with the payload as its siblings rather than nested under `data`. The
 * decoder returned `null` for that shape, so the entire Risk dashboard rendered
 * "N/A" while the API answered 200 with a Credit Risk score of 70.8 and a live
 * overdue-customer alert worth ₹22m.
 *
 * It survived because the consumer's `hasData` ignored a null payload, so the
 * cards fell back to a plausible zero. Tightening `hasData` turned a silent
 * wrong-data bug into a visible no-data bug, which is how it was finally found.
 */
describe('readInsightsEnvelope', () => {
	it('unwraps the nested envelope most endpoints use', () => {
		const { data, error } = readInsightsEnvelope({ status: 'success', data: { ytd_revenue: 451855824 } })
		expect(error).toBeNull()
		expect(data).toEqual({ ytd_revenue: 451855824 })
	})

	it('unwraps a top-level payload that sits beside `status`', () => {
		// Verbatim shape from `insights.api.ml.risk_intelligence`.
		const { data, error } = readInsightsEnvelope({
			status: 'success',
			generated_at: '2026-08-02T10:08:12',
			company: 'JKM Chemtrade',
			base_currency: 'INR',
			overview: { aggregate_risk_score: 32.6, aggregate_risk_category: 'Medium' },
			credit_risk: { avg_days_overdue: 183.7 },
		})
		expect(error).toBeNull()
		expect(data).toMatchObject({
			overview: { aggregate_risk_score: 32.6 },
			credit_risk: { avg_days_overdue: 183.7 },
		})
	})

	it('strips `status` from a top-level payload so it is not mistaken for a metric', () => {
		const { data } = readInsightsEnvelope({ status: 'success', overview: {} })
		expect(data).not.toHaveProperty('status')
	})

	it('never returns null for a successful response', () => {
		// The defect: a success that decodes to null makes every consumer render
		// its empty state, which reads as "no data" when data was in fact returned.
		for (const payload of [
			{ status: 'success', data: { a: 1 } },
			{ status: 'success', overview: { a: 1 } },
			{ status: 'success' },
		]) {
			const { data, error } = readInsightsEnvelope(payload)
			expect(error, JSON.stringify(payload)).toBeNull()
			expect(data, JSON.stringify(payload)).not.toBeNull()
		}
	})

	it('surfaces an error status as an error, not as empty data', () => {
		const { data, error } = readInsightsEnvelope({ status: 'error', message: 'Permission denied' })
		expect(error).toBe('Permission denied')
		expect(data).toBeNull()
	})

	it('falls back to a generic message when an error carries none', () => {
		expect(readInsightsEnvelope({ status: 'error' }).error).toBe('Request failed')
	})

	it('passes through a plain dict that has no envelope at all', () => {
		const raw = { total_items: 42 }
		const { data, error } = readInsightsEnvelope(raw)
		expect(error).toBeNull()
		expect(data).toEqual(raw)
	})

	it('does not throw on null, undefined or a primitive', () => {
		for (const v of [null, undefined, 0, '', 'text', false]) {
			expect(() => readInsightsEnvelope(v)).not.toThrow()
			expect(readInsightsEnvelope(v).error).toBeNull()
		}
	})

	it('passes through an unrecognised status rather than discarding the payload', () => {
		// `queued` is used by the tax endpoint while a job runs.
		const { data, error } = readInsightsEnvelope({ status: 'queued', message: 'Analysis queued' })
		expect(error).toBeNull()
		expect(data).toMatchObject({ status: 'queued' })
	})
})
