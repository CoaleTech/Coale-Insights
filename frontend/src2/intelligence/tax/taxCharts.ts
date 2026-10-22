import type { AxisChartConfig } from 'frappe-ui/src/components/Charts/types'
import { chartPalette } from '../../utils/chartTheme'

export interface Ser {
	name: string
	type?: 'bar' | 'line'
}

/**
 * Axis chart over `rows`, one column per series (`row[series.name]`). Bars start
 * at zero. `yMin`/`yMax` are in the frappe-ui type but frappe-ui 0.1.142 does not
 * read them, so axes auto-scale until IntelligenceChart applies them.
 */
export function axisConfig(
	rows: Record<string, string | number | null>[],
	xKey: string,
	series: Ser[],
	axis: { title: string; yMin?: number; yMax?: number },
): AxisChartConfig {
	return {
		data: rows,
		title: '',
		xAxis: { key: xKey, type: 'category' },
		// frappe-ui prints `undefined` as the axis name when no title is given.
		yAxis: { title: axis.title, yMin: axis.yMin ?? 0, yMax: axis.yMax },
		series: series.map((s) => ({ name: s.name, type: s.type ?? 'bar' })),
		colors: chartPalette(series.length),
	}
}
