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

  Deliberately no height of its own here, or it would collide the same way.
-->
<template>
  <div class="w-full">
    <ECharts :options="options" :error="error" />
  </div>
</template>

<script setup lang="ts">
import { ECharts } from 'frappe-ui'
import useAxisChartOptions from 'frappe-ui/src/components/Charts/axisChartOptions'
import useDonutChartOptions from 'frappe-ui/src/components/Charts/donutChartOptions'
import type {
  AxisChartConfig,
  DonutChartConfig,
} from 'frappe-ui/src/components/Charts/types'
import { computed, ref } from 'vue'
import { usePrefersReducedMotion } from '../../composables/usePrefersReducedMotion'

const props = withDefaults(
  defineProps<{
    /** 'axis' for bar/line/area, 'donut' for share-of-total. */
    kind?: 'axis' | 'donut'
    config: AxisChartConfig | DonutChartConfig
    /** Drop the chart's own legend (the caller renders an accessible one). */
    hideLegend?: boolean
  }>(),
  { kind: 'axis' },
)

const error = ref('')
const reduceMotion = usePrefersReducedMotion()

const options = computed(() => {
  try {
    error.value = ''
    const base =
      props.kind === 'donut'
        ? useDonutChartOptions(props.config as DonutChartConfig)
        : useAxisChartOptions(props.config as AxisChartConfig)
    // ECharts shows no legend unless `legend` is present, so removing the key
    // (not setting `show:false`) also reclaims the space it reserved.
    if (props.hideLegend && base && typeof base === 'object') {
      delete (base as { legend?: unknown }).legend
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
</script>
