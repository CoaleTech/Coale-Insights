import { describe, expect, it } from 'vitest'
import {
	presentationChartConfig,
	type PresentationChartPayload,
} from './presentationChart'

/**
 * The chart slide shipped a placeholder on top of real data.
 *
 * The payload below is copied verbatim from a live
 * `generate_presentation_data("budget", ...)` call, including the server's
 * hardcoded `#3b82f6`, so these assertions lock the actual contract rather than
 * an assumed one.
 */
const LIVE: PresentationChartPayload = {
	labels: ['2026-01', '2026-02', '2026-03'],
	datasets: [
		{
			label: 'Variance %',
			data: [-8.0, 7.3, -1.0],
			borderColor: '#3b82f6',
			backgroundColor: 'rgba(59, 130, 246, 0.1)',
		},
	],
}

describe('presentationChartConfig', () => {
	it('transposes labels and datasets into rows keyed by series name', () => {
		const cfg = presentationChartConfig(LIVE, 'line')
		expect(cfg).not.toBeNull()
		expect(cfg?.data).toEqual([
			{ label: '2026-01', 'Variance %': -8 },
			{ label: '2026-02', 'Variance %': 7.3 },
			{ label: '2026-03', 'Variance %': -1 },
		])
		expect(cfg?.xAxis).toEqual({ key: 'label', type: 'category' })
		expect(cfg?.series.map((s) => s.name)).toEqual(['Variance %'])
	})

	it('carries a negative value through rather than flattening it', () => {
		// A variance chart is mostly signed values; coercing them would invert the
		// meaning of the slide.
		const cfg = presentationChartConfig(LIVE, 'line')
		expect(cfg?.data[0]['Variance %']).toBe(-8)
	})

	it('honours the server chart_type, defaulting to a trend line', () => {
		expect(presentationChartConfig(LIVE, 'bar')?.series[0].type).toBe('bar')
		expect(presentationChartConfig(LIVE, 'line')?.series[0].type).toBe('line')
		expect(presentationChartConfig(LIVE, undefined)?.series[0].type).toBe('line')
	})

	it('discards the server hex so the chart themes with the app', () => {
		// `#3b82f6` is a light-mode literal outside the Espresso palette and would
		// stay fixed under `data-theme="dark"`.
		const cfg = presentationChartConfig(LIVE, 'line')
		expect(cfg?.series[0].color).toBeTruthy()
		expect(cfg?.series[0].color).not.toBe('#3b82f6')
		expect(cfg?.series[0].color).not.toBe('rgba(59, 130, 246, 0.1)')
	})

	it('names an unlabelled series instead of producing an undefined key', () => {
		const cfg = presentationChartConfig({ labels: ['Jan'], datasets: [{ data: [5] }] }, 'line')
		expect(cfg?.series[0].name).toBe('Series 1')
		expect(cfg?.data[0]).toEqual({ label: 'Jan', 'Series 1': 5 })
	})

	it('keeps multiple series distinct', () => {
		const cfg = presentationChartConfig(
			{
				labels: ['Jan', 'Feb'],
				datasets: [
					{ label: 'Budget', data: [100, 110] },
					{ label: 'Actual', data: [92, 118] },
				],
			},
			'bar',
		)
		expect(cfg?.series.map((s) => s.name)).toEqual(['Budget', 'Actual'])
		expect(cfg?.data).toEqual([
			{ label: 'Jan', Budget: 100, Actual: 92 },
			{ label: 'Feb', Budget: 110, Actual: 118 },
		])
		// Two series on one chart must not resolve to the same colour, which is the
		// defect that made Budget and Actual indistinguishable elsewhere.
		expect(cfg?.series[0].color).not.toBe(cfg?.series[1].color)
	})

	it('returns null when there is nothing real to plot', () => {
		// The caller renders an explicit empty state on null. An axis chart handed
		// an empty series draws bare gridlines, which reads as a flat measurement
		// rather than a missing one.
		expect(presentationChartConfig(undefined, 'line')).toBeNull()
		expect(presentationChartConfig({ labels: [], datasets: [] }, 'line')).toBeNull()
		expect(presentationChartConfig({ labels: ['Jan'], datasets: [] }, 'line')).toBeNull()
		expect(presentationChartConfig({ labels: [], datasets: [{ label: 'A', data: [1] }] }, 'line')).toBeNull()
	})

	it('treats an all-missing series as absent rather than as zeroes', () => {
		expect(
			presentationChartConfig({ labels: ['Jan', 'Feb'], datasets: [{ label: 'Spend', data: [null, null] }] }, 'line'),
		).toBeNull()
	})

	it('leaves a gap for a missing point instead of inventing a zero', () => {
		const cfg = presentationChartConfig(
			{ labels: ['Jan', 'Feb', 'Mar'], datasets: [{ label: 'Spend', data: [10, null, 30] }] },
			'line',
		)
		expect(cfg?.data[1]).toEqual({ label: 'Feb' })
		expect(cfg?.data[1].Spend).toBeUndefined()
	})

	it('ignores a non-numeric point rather than coercing it', () => {
		// `Number('n/a')` is NaN, which ECharts renders as a break; a silent 0 would
		// render as a real measurement.
		const cfg = presentationChartConfig(
			{ labels: ['Jan', 'Feb'], datasets: [{ label: 'Spend', data: ['n/a', 20] }] },
			'line',
		)
		expect(cfg?.data[0].Spend).toBeUndefined()
		expect(cfg?.data[1].Spend).toBe(20)
	})
})
