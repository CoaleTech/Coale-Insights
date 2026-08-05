import { describe, expect, it } from 'vitest'
import { HEALTH_SCORE_THRESHOLDS, scoreSeverity, sparklineInk } from './status'

/**
 * Regression lock for a self-contradicting card, not coverage.
 *
 * The server labels composite health scores with a four-band word
 * (`>=80 Excellent, >=60 Good, >=40 Fair, else Poor` --
 * `ml/strategic_finance/summary.py:217`; the same bins for customer health at
 * `ml/customer_intelligence/analytics.py:452`). The badge beside that word is
 * driven by `scoreSeverity`, which has three outcomes.
 *
 * Two thresholds shipped before `HEALTH_SCORE_THRESHOLDS` existed and both
 * disagreed with the server: 75/50 painted "Good" amber, and 80/60 would have
 * painted "Good" amber and "Fair" red. These tests pin the one band that agrees.
 */

/** The server's own banding, transcribed from summary.py:217. */
function serverWord(score: number): 'Excellent' | 'Good' | 'Fair' | 'Poor' {
	if (score >= 80) return 'Excellent'
	if (score >= 60) return 'Good'
	if (score >= 40) return 'Fair'
	return 'Poor'
}

/** A word is contradicted when a positive verdict is painted as a warning. */
const POSITIVE_WORDS = ['Excellent', 'Good']

describe('HEALTH_SCORE_THRESHOLDS', () => {
	it('never paints a positive server word as amber or red', () => {
		// This is the actual defect: an amber "Warning" badge rendered beside the
		// word "Good" trains users to distrust the colour vocabulary entirely.
		for (let score = 0; score <= 100; score++) {
			const word = serverWord(score)
			if (!POSITIVE_WORDS.includes(word)) continue
			expect(
				scoreSeverity(score, HEALTH_SCORE_THRESHOLDS),
				`score ${score} is "${word}" server-side but badged non-green`,
			).toBe('low')
		}
	})

	it('never paints a negative server word as green', () => {
		// The opposite failure, and the more dangerous one for a governance tool:
		// reporting green over a "Poor" score.
		for (let score = 0; score <= 100; score++) {
			const word = serverWord(score)
			if (POSITIVE_WORDS.includes(word)) continue
			expect(
				scoreSeverity(score, HEALTH_SCORE_THRESHOLDS),
				`score ${score} is "${word}" server-side but badged green`,
			).not.toBe('low')
		}
	})

	it('maps each server band to exactly one severity', () => {
		expect(scoreSeverity(90, HEALTH_SCORE_THRESHOLDS)).toBe('low') // Excellent
		expect(scoreSeverity(70, HEALTH_SCORE_THRESHOLDS)).toBe('low') // Good
		expect(scoreSeverity(50, HEALTH_SCORE_THRESHOLDS)).toBe('medium') // Fair
		expect(scoreSeverity(30, HEALTH_SCORE_THRESHOLDS)).toBe('high') // Poor
	})

	it('rejects the two bands that shipped before it', () => {
		// Documents *why* this constant exists. If someone reverts to either of
		// these, the first two tests above fail; this one explains the reason.
		expect(scoreSeverity(70, { good: 75, warn: 50 })).toBe('medium') // "Good" -> amber
		expect(scoreSeverity(70, { good: 80, warn: 60 })).toBe('medium') // "Good" -> amber
		expect(scoreSeverity(50, { good: 80, warn: 60 })).toBe('high') // "Fair" -> red
	})

	it('covers the real liquidity score domain, which is not continuous', () => {
		// summary.py:202-209 only ever emits 90/70/50/30 (before the +/-10 debt
		// adjustment), so 70 -> "Good" was the common case, not an edge case.
		for (const score of [90, 80, 70, 60, 50, 40, 30, 20]) {
			const severity = scoreSeverity(score, HEALTH_SCORE_THRESHOLDS)
			const word = serverWord(score)
			if (POSITIVE_WORDS.includes(word)) expect(severity).toBe('low')
			else expect(severity).not.toBe('low')
		}
	})

	describe('sparklineInk', () => {
		it('colours improving trends with the app accent', () => {
			expect(sparklineInk(5, { higherIsBetter: true })).toBe('text-accent')
			expect(sparklineInk(-5, { higherIsBetter: false })).toBe('text-accent')
		})

		it('colours worsening trends with the status negative ink', () => {
			expect(sparklineInk(-5, { higherIsBetter: true })).toBe('text-neg')
			expect(sparklineInk(5, { higherIsBetter: false })).toBe('text-neg')
		})

		it('recedes neutral or missing trends', () => {
			expect(sparklineInk(0)).toBe('text-muted-fill')
			expect(sparklineInk(null)).toBe('text-muted-fill')
			expect(sparklineInk(undefined)).toBe('text-muted-fill')
			expect(sparklineInk(Number.NaN)).toBe('text-muted-fill')
		})
	})
})
