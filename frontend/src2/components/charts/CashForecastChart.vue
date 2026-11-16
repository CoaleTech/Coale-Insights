<template>
  <div class="w-full h-full">
    <div v-if="hasData" class="space-y-2">
      <!-- frappe-ui AxisChart: three area series, one per scenario -->
      <IntelligenceChart class="h-48 sm:h-56 lg:h-64" :config="axisConfig" :value-format="formatCurrency" hide-legend />

      <!-- Accessible text equivalent for screen readers (canvas is invisible to AT) -->
      <table class="sr-only">
        <caption>Cash flow forecast by scenario over {{ displayData.length }} weeks</caption>
        <thead>
          <tr>
            <th scope="col">Week</th>
            <th scope="col">Optimistic</th>
            <th scope="col">Base</th>
            <th scope="col">Pessimistic</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in displayData" :key="p.label">
            <th scope="row">{{ p.shortLabel }}</th>
            <td>{{ formatCurrency(p.optimistic) }}</td>
            <td>{{ formatCurrency(p.base) }}</td>
            <td>{{ formatCurrency(p.pessimistic) }}</td>
          </tr>
        </tbody>
      </table>

      <!-- Legend: swatch + text label per series -->
      <div class="flex justify-center gap-6 text-xs mt-3" aria-hidden="true">
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-0.5 bg-surface-green-3 rounded"></div>
          <span class="text-ink-gray-6">Optimistic</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-0.5 bg-surface-blue-3 rounded"></div>
          <span class="text-ink-gray-6">Base</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-0.5 bg-surface-amber-3 rounded"></div>
          <span class="text-ink-gray-6">Pessimistic</span>
        </div>
      </div>

      <!-- Summary stats -->
      <div class="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-outline-gray-1">
        <div class="text-center">
          <p class="text-xs text-ink-gray-6">Day 90 Optimistic</p>
          <p class="text-sm font-bold text-ink-gray-9">{{ formatCompact(lastOptimistic) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs text-ink-gray-6">Day 90 Base</p>
          <p class="text-sm font-bold text-ink-gray-9">{{ formatCompact(lastBase) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs text-ink-gray-6">Day 90 Pessimistic</p>
          <p class="text-sm font-bold text-ink-gray-9">{{ formatCompact(lastPessimistic) }}</p>
        </div>
      </div>
    </div>

    <div v-else class="flex items-center justify-center h-full text-ink-gray-6">
      No forecast data available
    </div>
  </div>
</template>

<script setup lang="ts">
import IntelligenceChart from '../../intelligence/components/IntelligenceChart.vue'

import { computed } from 'vue'
import { themeColor } from '../../utils/chartTheme'
import { useCurrency } from '../../composables/useCurrency'
import { formatMoney } from '../../utils/format'

interface ForecastPoint {
  date: string
  day: number
  balance: number
}

interface Props {
  base: ForecastPoint[]
  optimistic: ForecastPoint[]
  pessimistic: ForecastPoint[]
}

const props = defineProps<Props>()

// Company currency from the server. This chart used to default to 'KES' (en-KE), so the
// screen-reader table announced Kenyan shillings on an INR site.
const currency = useCurrency('')

const hasData = computed(() => props.base?.length > 0)

// Show every 7th day for cleaner display (weekly), plus the last day: 90 days is
// not a whole number of weeks, so the sample alone would stop at day 84 and the
// chart would end short of the "Day 90" tiles and the weekly summary table (W13).
const displayData = computed(() => {
  const n = props.base?.length ?? 0
  if (!n) return []
  const days: number[] = []
  for (let i = 6; i < n; i += 7) days.push(i)
  if (days.at(-1) !== n - 1) days.push(n - 1)
  return days.map(i => ({
    label: props.base[i].date,
    shortLabel: `W${Math.ceil((i + 1) / 7)}`,
    base: props.base[i].balance,
    optimistic: props.optimistic?.[i]?.balance ?? props.base[i].balance,
    pessimistic: props.pessimistic?.[i]?.balance ?? props.base[i].balance,
  }))
})

const lastOptimistic = computed(() => props.optimistic?.at(-1)?.balance ?? props.base?.at(-1)?.balance ?? 0)
const lastBase = computed(() => props.base?.at(-1)?.balance ?? 0)
const lastPessimistic = computed(() => props.pessimistic?.at(-1)?.balance ?? props.base?.at(-1)?.balance ?? 0)

/**
 * AxisChart config. Three area series so the fill bands are visible; `showDataPoints: false`
 * because ~13 weekly points on an area chart are too dense for dots to add signal.
 * themeColor is called inside computed so any [data-theme] switch picks up the new resolved
 * values on next render (ECharts paints canvas and cannot resolve CSS custom properties).
 */
const axisConfig = computed(() => ({
  data: displayData.value.map(p => ({
    week: p.shortLabel,
    Optimistic: p.optimistic,
    Base: p.base,
    Pessimistic: p.pessimistic,
  })),
  title: '',
  xAxis: { key: 'week', type: 'category' as const },
  yAxis: { title: '' },
  series: [
    {
      name: 'Optimistic',
      type: 'area' as const,
      color: themeColor('--app-pos-fill'),
      showDataPoints: false,
      fillOpacity: 0.15,
    },
    {
      name: 'Base',
      type: 'area' as const,
      color: themeColor('--app-accent'),
      showDataPoints: false,
      fillOpacity: 0.15,
    },
    {
      name: 'Pessimistic',
      type: 'area' as const,
      color: themeColor('--app-warn-fill'),
      showDataPoints: false,
      fillOpacity: 0.15,
    },
  ],
}))

const formatCurrency = (value: number | null | undefined) => formatMoney(value, currency.value)
const formatCompact = (value: number) => formatMoney(value, currency.value, { compact: true })
</script>
