<!--
The external legend pairs swatch, label, value and percentage for every slice.
It is the accessible text equivalent of the canvas donut: a screen reader reads
the legend and gets the same information without needing the chart.
-->
<template>
  <div class="w-full h-full flex items-center justify-center">
    <!--
      Stacks on phones. Side by side at 375px the legend claimed 232px of a
      296px row and the donut was squeezed to 32px, since a flex item shrinks
      below its declared width unless told not to. `shrink-0` holds the ring at
      its stated size in the row layout too.
    -->
    <div v-if="donutData.length" class="flex flex-col items-center gap-4 sm:flex-row sm:gap-8">
      <!-- Fixed box holds the ring; IntelligenceChart's internal w-full would
           otherwise stretch the ECharts area and leave a gap before the legend. -->
      <div class="h-48 w-48 shrink-0">
        <IntelligenceChart kind="donut" class="h-full w-full" :config="donutConfig" hide-legend />
      </div>

      <!-- Legend: swatch + label + value + percentage (visible, serves as accessible text) -->
      <div class="space-y-2">
        <div
          v-for="(item, index) in donutData.slice(0, 6)"
          :key="index"
          class="flex items-center gap-2"
        >
          <div
            class="w-3 h-3 rounded-full flex-shrink-0"
            :style="{ backgroundColor: paletteColors[index % paletteColors.length] }"
            aria-hidden="true"
          ></div>
        <span class="text-sm text-ink-gray-6 truncate max-w-32">
          {{ item.category }}
        </span>
        <span class="text-sm font-medium text-ink-gray-9 whitespace-nowrap shrink-0">
          {{ formatCurrency(item.value) }}
        </span>
        <span class="text-xs text-ink-gray-6 whitespace-nowrap shrink-0">
          ({{ formatPercent(item.pct || getPercentage(item.value)) }})
        </span>
        </div>
        <div v-if="donutData.length > 6" class="text-xs text-ink-gray-6">
          +{{ donutData.length - 6 }} more categories
        </div>
      </div>
    </div>

    <div v-else class="text-ink-gray-6">No expense data available</div>
  </div>
</template>

<script setup lang="ts">
import IntelligenceChart from '../../intelligence/components/IntelligenceChart.vue'

import { computed } from 'vue'
import { chartPalette } from '../../utils/chartTheme'

/** Slice rows: category/name/label plus value/amount/percentage, all optional upstream. */
type PieRow = Record<string, number | string | boolean | null | undefined>

interface Props {
  data: PieRow[]
  currency?: string
}

const props = withDefaults(defineProps<Props>(), { currency: 'KES' })

const total = computed(() =>
  (props.data || []).reduce((sum, item) => sum + Number(item.value || item.amount || 0), 0)
)

const getPercentage = (value: number): number =>
  total.value === 0 ? 0 : (value / total.value) * 100

/**
 * Normalised, descending-sorted data.
 *
 * DonutChart sorts internally by descending value. We pre-sort so the legend
 * order matches the slice order in the chart, keeping colour-to-label
 * correspondence correct.
 *
 * Dynamic keys (value/amount, category/name/label) from the upstream prop are
 * resolved here once so the template stays free of coercion noise.
 */
const donutData = computed(() =>
  (props.data || [])
    .map(item => ({
      category: String(item.category || item.name || item.label || 'Other'),
      value: Number(item.value || item.amount || 0),
      pct: Number(item.percentage) || 0,
    }))
    .sort((a, b) => b.value - a.value)
)

/**
 * Resolved hex palette for DonutChart. ECharts paints to a canvas and cannot
 * resolve CSS custom properties; chartPalette reads the computed values from the
 * theme layer so a [data-theme] switch picks up the right colours on next render.
 */
const paletteColors = computed(() => chartPalette(6))

const donutConfig = computed(() => ({
  data: donutData.value.map(({ category, value }) => ({ category, value })),
  title: formatCurrency(total.value),
  categoryColumn: 'category',
  valueColumn: 'value',
  maxSliceCount: 6,
  colors: paletteColors.value,
}))

const formatCurrency = (value: number): string => {
  if (value >= 1_000_000) return `${props.currency} ${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${props.currency} ${(value / 1_000).toFixed(0)}K`
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: props.currency,
    minimumFractionDigits: 0,
  }).format(value)
}

const formatPercent = (value: number): string => `${value.toFixed(1)}%`
</script>
