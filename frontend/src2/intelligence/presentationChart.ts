import type { AxisChartConfig } from 'frappe-ui/src/components/Charts/types'
import { chartPalette } from '../utils/chartTheme'

/**
 * Board-deck chart slides, from the server's Chart.js payload to the axis config
 * the rest of this app already uses.
 *
 * `presentation_service.py` has always sent real `chart_data` on `type: 'chart'`
 * slides (lines 175 and 239), but the slide template rendered a lucide icon and
 * the words "Chart Visualization" over the top of it, so an executive deck
 * presented a placeholder where the trend belonged.
 *
 * Lives in its own module rather than inside the SFC so the transposition is
 * directly testable against a captured payload.
 */
/** One row per x-axis category, with a key per series. */
export type PresentationChartRow = Record<string, string | number>

/**
 * The server's shape. Every field it sends is declared, including the two colour
 * keys, so that ignoring them is visible in the type rather than silently
 * dropped by an under-specified interface.
 */
export interface PresentationChartPayload {
	labels?: unknown[]
	datasets?: {
		label?: string
		data?: unknown[]
		/** Light-mode literal, deliberately unused. See the note on `series` below. */
		borderColor?: string
		/** Light-mode literal, deliberately unused. */
		backgroundColor?: string
	}[]
}

function isFiniteNumber(value: unknown): value is number {
	return typeof value === 'number' && Number.isFinite(value)
}

/**
 * Returns `null` when there is nothing real to plot.
 *
 * An axis chart handed an empty series draws bare gridlines, which reads as "the
 * value is flat" rather than "there is no measurement" -- the same class of
 * false confidence as a KPI card rendering `0` for a failed fetch. The caller is
 * expected to show an explicit empty state on `null`.
 */
export function presentationChartConfig(
	payload: PresentationChartPayload | undefined | null,
	chartType: string | undefined,
	title = '',
): AxisChartConfig | null {
	const labels = Array.isArray(payload?.labels) ? payload.labels : []
	const datasets = Array.isArray(payload?.datasets) ? payload.datasets : []
	if (labels.length === 0 || datasets.length === 0) return null

	// A dataset whose every point is missing is an absence, not a series.
	const usable = datasets.filter((d) => Array.isArray(d?.data) && d.data.some(isFiniteNumber))
	if (usable.length === 0) return null

	const names = usable.map((d, i) => String(d.label ?? `Series ${i + 1}`))
	const palette = chartPalette(names.length)
	const type: 'bar' | 'line' = chartType === 'bar' ? 'bar' : 'line'

	const data = labels.map((label, i) => {
		const row: PresentationChartRow = { label: String(label ?? '') }
		usable.forEach((dataset, j) => {
			const point = dataset.data?.[i]
			// Absent points are dropped rather than coerced to 0: a gap in a trend
			// line is honest, a zero invents a measurement the server never sent.
			if (isFiniteNumber(point)) row[names[j]] = point
		})
		return row
	})

	return {
		// The slide already renders its own heading, so the chart's own title is
		// empty by default rather than repeating it inside the plot area.
		title,
		data,
		xAxis: { key: 'label', type: 'category' },
		yAxis: { title: '' },
		// The server also sends `borderColor` / `backgroundColor` hex values
		// (`#3b82f6`, `#ef4444`). They are deliberately ignored: light-mode
		// literals outside the Espresso palette that would stay fixed under
		// `data-theme="dark"`. Colour comes from the app's token-resolving palette.
		series: names.map((name, i) => ({ name, type, color: palette[i] })),
	}
}
