import { describe, expect, it } from 'vitest'
import { chartPalette, signedPalette, themeColor } from './chartTheme'

/**
 * The palette must actually be a palette.
 *
 * `--app-accent` and `--app-info-fill` both resolve to `#0070cc`, and both were
 * in the series list, so `chartPalette(2)` returned that colour twice and a
 * two-series chart drew one indistinguishable pair. Colour is the only thing
 * separating series on a canvas once the legend is read, so a duplicate is a
 * silent data-legibility bug rather than a cosmetic one.
 */
describe('chartPalette', () => {
	it('never repeats a colour, at any series count', () => {
		for (let n = 2; n <= 6; n++) {
			const palette = chartPalette(n)
			expect(palette).toHaveLength(n)
			expect(new Set(palette).size, `chartPalette(${n}) has a duplicate: ${palette.join(', ')}`).toBe(n)
		}
	})

	it('resolves every series slot to a real colour, not an empty string', () => {
		// `getComputedStyle` returns '' for an unknown custom property, and an empty
		// `colors` entry makes ECharts fall back to its own default hue, silently
		// leaving the app's theme.
		for (const colour of chartPalette()) {
			expect(colour).toMatch(/^#[0-9a-fA-F]{3,8}$|^(rgb|oklch|hsl)/)
		}
	})

	it('leads with the accent so a single-series chart matches the app chrome', () => {
		expect(chartPalette(1)[0]).toBe(themeColor('--app-accent'))
	})

	it('keeps the signed pair semantically opposed and distinct', () => {
		const [positive, negative] = signedPalette()
		expect(positive).not.toBe(negative)
	})

	it('falls back rather than returning an empty string for an unknown token', () => {
		expect(themeColor('--not-a-real-token')).toBeTruthy()
	})
})
