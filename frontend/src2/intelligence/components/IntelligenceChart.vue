<!--
  One chart entry point for the intelligence dashboards.

  Exists for a single reason frappe-ui cannot cover: reduced motion.
  `frappe-ui/src/components/Charts/eChartOptions.ts:27` hardcodes
  `animation: true, animationDuration: 700` with no config override, and ECharts
  never consults `prefers-reduced-motion`. PRODUCT.md requires that preference be
  respected, so every chart on this surface animated against it.

  This builds the options with frappe-ui's own builders, so the typed config
  contract and all its axis/legend/tooltip behaviour are unchanged, then
  overrides only the animation flags before handing them to frappe-ui's ECharts.

  Use this instead of frappe-ui's AxisChart / DonutChart directly.

  The wrapper div is load-bearing. frappe-ui's ECharts root already carries
  `h-full`, so a caller's `class="lg:h-64"` landed on the same element and the
  two height utilities fought, with the winner decided by stylesheet order
  rather than intent. When `h-full` won the chart took the height of its grid
  cell instead: measured 892px at 1024x768 where 256px was asked for. The
  wrapper receives the caller's height and `h-full` resolves against it.

  Deliberately no height of its own here, or it would collide the same way. The
  one exception is `min-h-[300px]`, which mirrors frappe-ui's ECharts root: a
  caller height under 300px used to leave the chart overflowing its wrapper.
-->
<template>
  <div ref="root" class="w-full min-h-[300px]" role="img" :aria-label="label ?? summary">
    <!-- frappe-ui's ECharts applies `options` only on mount, so a theme switch needs a remount. -->
    <ECharts :key="theme" :options="options" :error="error" />
  </div>
</template>

<script setup lang="ts">
import { getInstanceByDom } from 'echarts/core'
import { ECharts } from 'frappe-ui'
import useAxisChartOptions from 'frappe-ui/src/components/Charts/axisChartOptions'
import useDonutChartOptions from 'frappe-ui/src/components/Charts/donutChartOptions'
import type {
  AxisChartConfig,
  DonutChartConfig,
} from 'frappe-ui/src/components/Charts/types'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { usePrefersReducedMotion } from '../../composables/usePrefersReducedMotion'
import { useTheme } from '../../composables/useTheme'
import { themeColor } from '../../utils/chartTheme'

const props = withDefaults(
  defineProps<{
    /** 'axis' for bar/line/area, 'donut' for share-of-total. */
    kind?: 'axis' | 'donut'
    config: AxisChartConfig | DonutChartConfig
    /** Drop the chart's own legend (the caller renders an accessible one). */
    hideLegend?: boolean
    /** Accessible name. Defaults to the series names and point count. */
    label?: string
    /**
     * Format for tooltip values. frappe-ui prints the raw number
     * ("-2,535,356.05"), so a money chart passes `formatMoney` to match its axis and tiles.
     * The series name is the second argument, for a chart that mixes units.
     */
    valueFormat?: (value: number, series: string) => string
  }>(),
  { kind: 'axis' },
)

const error = ref('')
const reduceMotion = usePrefersReducedMotion()
const { theme } = useTheme()

interface Retintable {
  splitLine?: object
  axisLabel?: object
  nameTextStyle?: object
}

/**
 * frappe-ui leaves ECharts' light-theme grid and legend text and hardcodes a
 * white `#fff` background on the axis-name label, so in dark mode the grid is
 * near-white and the "↑ INR" label is a white box. Retint from the theme tokens.
 */
function retint(opts: { xAxis?: Retintable | Retintable[]; yAxis?: Retintable | Retintable[]; legend?: { textStyle?: object; padding?: number[]; itemGap?: number }; tooltip?: object }) {
  const grid = themeColor('--outline-gray-2')
  const ink = themeColor('--ink-gray-6')
  const surface = themeColor('--surface-white')
  for (const axis of [opts.xAxis, opts.yAxis].flat()) {
    if (!axis) continue
    axis.splitLine = { ...axis.splitLine, lineStyle: { color: grid } }
    axis.axisLabel = { ...axis.axisLabel, color: ink }
    axis.nameTextStyle = { ...axis.nameTextStyle, color: ink, backgroundColor: surface, borderColor: surface }
  }
  // frappe-ui reserves 25px each side for the pager arrows and a 12px gap, so a
  // three-item legend paged ("1/3") in a 260px phone chart. Items still scroll if they truly overflow.
  if (opts.legend) opts.legend = Object.assign(opts.legend, { padding: [0, 0], itemGap: 8, textStyle: { ...opts.legend.textStyle, color: ink } })
  // The tooltip card is ECharts' white with grey text in either theme: a bright box on a dark page.
  if (opts.tooltip) Object.assign(opts.tooltip, { backgroundColor: surface, borderColor: grid, textStyle: { color: themeColor('--ink-gray-8') } })
}

/**
 * Re-runs frappe-ui's tooltip formatter with the values already formatted: its
 * `isNaN(y) ? y : formatValue(y)` leaves a string alone. The zero filter and
 * descending sort are frappe-ui's own, repeated here because they need numbers; a
 * missing value (a Loss series in a profit month) is dropped too, not printed as "-".
 */
type TipRow = { seriesName?: string; value: [unknown, number] }
function formatTooltipValues(
  base: { tooltip?: { formatter?: (p: unknown) => string } },
  format: (value: number, series: string) => string,
  swapXY: boolean,
) {
  const inner = base.tooltip?.formatter
  if (!inner) return
  const at = swapXY ? 0 : 1
  base.tooltip!.formatter = (params: unknown) => {
    if (!Array.isArray(params)) return inner(params)
    const rows = (params as TipRow[])
      .filter((p) => p.value?.[at] != null && p.value[at] !== 0)
      .sort((a, b) => (b.value?.[at] as number) - (a.value?.[at] as number))
      .map((p) => {
        const value = [...p.value] as unknown[]
        value[at] = format(value[at] as number, p.seriesName ?? '')
        return { ...p, value }
      })
    return inner(rows)
  }
}

const options = computed(() => {
  try {
    error.value = ''
    const base =
      props.kind === 'donut'
        ? useDonutChartOptions(props.config as DonutChartConfig)
        : useAxisChartOptions(props.config as AxisChartConfig)
    // frappe-ui 0.1.142 types `yAxis.yMin/yMax` but never passes them to ECharts.
    const yAxis = (props.config as AxisChartConfig).yAxis
    const echartsY = (base as { yAxis?: unknown }).yAxis
    const y0 = (Array.isArray(echartsY) ? echartsY[0] : echartsY) as
      | { min?: number; max?: number }
      | undefined
    if (props.kind !== 'donut' && yAxis && y0) {
      if (yAxis.yMin != null) y0.min = yAxis.yMin
      if (yAxis.yMax != null) y0.max = yAxis.yMax
    }
    // ECharts shows no legend unless `legend` is present, so removing the key
    // (not setting `show:false`) also reclaims the space it reserved.
    if (props.hideLegend && base && typeof base === 'object') {
      delete (base as { legend?: unknown }).legend
    }
    // Reading `theme` re-runs this computed on a light/dark switch.
    if (props.kind !== 'donut' && theme.value) retint(base as Parameters<typeof retint>[0])
    if (props.kind !== 'donut' && props.valueFormat) {
      formatTooltipValues(base as Parameters<typeof formatTooltipValues>[0], props.valueFormat, !!(props.config as AxisChartConfig).swapXY)
    }
    if (!reduceMotion.value) return base
    // Drop the entrance and update tweens; the chart still renders in full.
    return {
      ...base,
      animation: false,
      animationDuration: 0,
      animationDurationUpdate: 0,
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Could not render this chart'
    return {}
  }
})

// Canvas charts expose nothing to assistive tech, so name them from the config.
const summary = computed(() => {
  const c = props.config as { data?: unknown[]; series?: { name?: string }[] }
  const names = (c.series ?? []).map((s) => s.name).filter(Boolean).join(', ')
  const kind = props.kind === 'donut' ? 'Donut chart' : 'Chart'
  return `${kind}${names ? `: ${names}` : ''}, ${c.data?.length ?? 0} data points`
})

// frappe-ui resizes on a debounced ResizeObserver, which has not fired by the
// time the browser lays out the print page, so printed charts kept their
// screen width. Resize synchronously on both sides of printing.
const root = ref<HTMLElement>()
function resizeAll() {
  root.value?.querySelectorAll<HTMLElement>('div').forEach((el) => {
    getInstanceByDom(el)?.resize({ animation: { duration: 0 } })
  })
}
onMounted(() => {
  window.addEventListener('beforeprint', resizeAll)
  window.addEventListener('afterprint', resizeAll)
})
onBeforeUnmount(() => {
  window.removeEventListener('beforeprint', resizeAll)
  window.removeEventListener('afterprint', resizeAll)
})
</script>
