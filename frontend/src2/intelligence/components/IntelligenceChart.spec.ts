import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import IntelligenceChart from './IntelligenceChart.vue'

/**
 * The contract this component exists to hold: frappe-ui's chart option builders
 * hardcode `animation: true, animationDuration: 700`
 * (`Charts/eChartOptions.ts:27`) with no config override, and ECharts never
 * consults `prefers-reduced-motion`. This wrapper is the only thing forcing the
 * preference through, so the override is worth pinning.
 */

// frappe-ui's ECharts mounts a real chart; stub it and capture the options it receives.
const received: Record<string, unknown>[] = []
vi.mock('frappe-ui', () => ({
	ECharts: {
		props: ['options', 'error'],
		template: '<div data-testid="echarts" />',
		created() {
			// @ts-expect-error runtime stub reads its own prop
			received.push(this.options)
		},
	},
}))

const axisConfig = {
	data: [{ month: 'Jan', Leads: 4 }],
	title: '',
	xAxis: { key: 'month', type: 'category' as const },
	yAxis: {},
	series: [{ name: 'Leads', type: 'bar' as const }],
}

function stubMatchMedia(matches: boolean) {
	vi.stubGlobal(
		'matchMedia',
		vi.fn(() => ({
			matches,
			media: '(prefers-reduced-motion: reduce)',
			addEventListener: vi.fn(),
			removeEventListener: vi.fn(),
		})),
	)
}

const lastOptions = () => received[received.length - 1]

describe('IntelligenceChart', () => {
	beforeEach(() => {
		received.length = 0
		vi.unstubAllGlobals()
	})

	it('keeps frappe-ui animation defaults when no preference is set', () => {
		stubMatchMedia(false)
		mount(IntelligenceChart, { props: { config: axisConfig } })
		expect(lastOptions().animation).toBe(true)
		expect(lastOptions().animationDuration).toBe(700)
	})

	it('disables animation when the user prefers reduced motion', () => {
		stubMatchMedia(true)
		mount(IntelligenceChart, { props: { config: axisConfig } })
		expect(lastOptions().animation).toBe(false)
		expect(lastOptions().animationDuration).toBe(0)
		expect(lastOptions().animationDurationUpdate).toBe(0)
	})

	it('still renders the full chart, it only drops the tween', () => {
		stubMatchMedia(true)
		mount(IntelligenceChart, { props: { config: axisConfig } })
		// series and axes survive; only the animation keys changed
		expect(lastOptions().series).toBeDefined()
		expect(lastOptions().xAxis).toBeDefined()
	})

	it('builds donut options when kind is donut', () => {
		stubMatchMedia(false)
		mount(IntelligenceChart, {
			props: {
				kind: 'donut',
				config: {
					data: [{ k: 'a', v: 1 }],
					title: '',
					categoryColumn: 'k',
					valueColumn: 'v',
				},
			},
		})
		// donut options carry a pie series rather than an x axis
		expect(lastOptions().xAxis).toBeUndefined()
		expect(lastOptions().series).toBeDefined()
	})

	it('surfaces a message instead of throwing on an invalid config', () => {
		stubMatchMedia(false)
		// swapXY is unsupported for a line series; the builder throws
		const wrapper = mount(IntelligenceChart, {
			props: {
				config: {
					...axisConfig,
					swapXY: true,
					series: [{ name: 'Leads', type: 'line' as const }],
				},
			},
		})
		expect(wrapper.find('[data-testid="echarts"]').exists()).toBe(true)
	})
})
