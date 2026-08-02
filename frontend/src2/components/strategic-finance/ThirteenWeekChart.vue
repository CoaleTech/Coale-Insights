<template>
  <div class="w-full h-full">
    <div v-if="hasData" class="space-y-4">
      <!-- frappe-ui AxisChart: inflow/outflow bars on primary axis, balance + threshold on y2 -->
      <IntelligenceChart class="h-52 sm:h-64 lg:h-72" :config="axisConfig" />

      <!-- Accessible text equivalent for screen readers (canvas is invisible to AT) -->
      <table class="sr-only">
        <caption>13-week cash flow forecast: inflows, outflows, and closing balance by week</caption>
        <thead>
          <tr>
            <th scope="col">Week</th>
            <th scope="col">Inflows</th>
            <th scope="col">Outflows</th>
            <th scope="col">Closing Balance</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="week in chartData" :key="week.week_label">
            <th scope="row">{{ week.week_label }}</th>
            <td>{{ formatCurrency(week.inflows?.total || 0) }}</td>
            <td>{{ formatCurrency(week.outflows?.total || 0) }}</td>
            <td>
              {{ formatCurrency(week.closing_balance) }}{{ week.below_threshold ? ' (below threshold)' : '' }}
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Legend -->
      <div class="flex justify-center gap-6 text-xs">
        <div class="flex items-center gap-1.5">
          <div class="w-3 h-3 bg-surface-green-3 rounded-sm"></div>
          <span class="text-ink-gray-7">Inflows</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-3 h-3 bg-surface-red-5 rounded-sm"></div>
          <span class="text-ink-gray-7">Outflows</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-0.5 bg-surface-blue-3 rounded"></div>
          <span class="text-ink-gray-7">Balance</span>
        </div>
        <div v-if="threshold > 0" class="flex items-center gap-1.5">
          <div class="w-4 h-0.5 rounded" style="border-top: 2px dashed; background: transparent; border-color: var(--app-warn-fill)"></div>
          <span class="text-ink-gray-7">Threshold</span>
        </div>
      </div>

      <!-- Summary stats -->
      <div class="grid grid-cols-4 gap-4 pt-4 border-t border-outline-gray-1">
        <div class="text-center">
          <p class="text-xs text-ink-gray-6">Avg Weekly Inflow</p>
          <p class="text-sm font-bold text-ink-gray-8">{{ formatCompact(avgInflow) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs text-ink-gray-6">Avg Weekly Outflow</p>
          <p class="text-sm font-bold text-ink-gray-8">{{ formatCompact(avgOutflow) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs text-ink-gray-6">Week 13 Balance</p>
          <p class="text-sm font-bold text-ink-gray-8">{{ formatCompact(endingBalance) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs text-ink-gray-6">Net Change</p>
          <p class="text-sm font-bold" :class="deltaInk(netChange)">
            {{ netChange >= 0 ? '+' : '' }}{{ formatCompact(netChange) }}
          </p>
        </div>
      </div>
    </div>

    <div v-else class="flex items-center justify-center h-full text-ink-gray-6">
      No forecast data available
    </div>
  </div>
</template>

<script setup lang="ts">
import { NO_VALUE } from '../../utils/format'
import IntelligenceChart from '../../intelligence/components/IntelligenceChart.vue'

import { computed, inject } from 'vue'
import { themeColor } from '../../utils/chartTheme'
import { deltaInk } from '../../utils/status'

interface WeekData {
  week_number: number
  week_label: string
  week_start: string
  is_actual: boolean
  is_forecast: boolean
  is_current: boolean
  opening_balance: number
  inflows: {
    ar_collections: number
    other_receipts: number
    total: number
  }
  outflows: {
    ap_payments: number
    payroll: number
    operating_expenses: number
    taxes: number
    total: number
  }
  net_flow: number
  closing_balance: number
  below_threshold: boolean
}

interface Props {
  data: {
    weeks: WeekData[]
    threshold: number
  } | null
  threshold?: number
}

const props = defineProps<Props>()

const currency = inject('currency', 'KES')

const hasData = computed(() => {
  return props.data?.weeks && props.data.weeks.length > 0
})

const chartData = computed(() => {
  return props.data?.weeks || []
})

const threshold = computed(() => {
  return props.threshold || props.data?.threshold || 0
})

const avgInflow = computed(() => {
  const weeks = chartData.value.filter((w) => w.is_forecast)
  if (!weeks.length) return 0
  return weeks.reduce((sum, w) => sum + (w.inflows?.total || 0), 0) / weeks.length
})

const avgOutflow = computed(() => {
  const weeks = chartData.value.filter((w) => w.is_forecast)
  if (!weeks.length) return 0
  return weeks.reduce((sum, w) => sum + (w.outflows?.total || 0), 0) / weeks.length
})

const endingBalance = computed(() => {
  if (!chartData.value.length) return 0
  return chartData.value[chartData.value.length - 1].closing_balance
})

const netChange = computed(() => {
  if (!chartData.value.length) return 0
  const first = chartData.value[0].opening_balance
  const last = chartData.value[chartData.value.length - 1].closing_balance
  return last - first
})

/**
 * AxisChart config.
 *
 * Inflows and outflows share the primary y axis. Outflows are negative so they
 * render as bars extending below zero, mirroring the original SVG layout.
 *
 * Balance uses y2 because its magnitude (running total) is typically an order
 * of magnitude larger than the weekly flow bars and would crush them if on the
 * same scale. swapXY cannot be used here because of the line series and y2.
 *
 * Threshold (when set) is a constant dashed line on y2 so it aligns with the
 * balance scale, replacing the SVG dashed threshold line.
 *
 * themeColor is called inside computed so [data-theme] switches pick up new
 * resolved values; ECharts canvas cannot resolve CSS custom properties.
 */
const axisConfig = computed(() => {
  const pos = themeColor('--app-pos-fill')
  const neg = themeColor('--app-neg-fill')
  const accent = themeColor('--app-accent')
  const warn = themeColor('--app-warn-fill')
  const thr = threshold.value

  const rows = chartData.value.map(w => {
    const row: Record<string, string | number> = {
      week: w.week_label,
      Inflows: w.inflows?.total || 0,
      Outflows: -(w.outflows?.total || 0),
      Balance: w.closing_balance,
    }
    if (thr > 0) row.Threshold = thr
    return row
  })

  type SeriesEntry = {
    name: string
    type: 'bar' | 'line' | 'area'
    color: string
    axis?: 'y' | 'y2'
    showDataPoints?: boolean
    lineType?: 'solid' | 'dashed' | 'dotted'
  }

  const series: SeriesEntry[] = [
    { name: 'Inflows', type: 'bar', color: pos },
    { name: 'Outflows', type: 'bar', color: neg },
    { name: 'Balance', type: 'line', color: accent, axis: 'y2', showDataPoints: true },
  ]

  if (thr > 0) {
    series.push({
      name: 'Threshold',
      type: 'line',
      color: warn,
      axis: 'y2',
      lineType: 'dashed',
      showDataPoints: false,
    })
  }

  return {
    data: rows,
    title: '',
    xAxis: { key: 'week', type: 'category' as const },
    yAxis: { title: 'Weekly flow' },
    y2Axis: { title: 'Balance' },
    series,
  }
})

const formatCompact = (value: number | null | undefined) => {
  if (value === null || value === undefined) return NO_VALUE
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absValue >= 1000000) return `${sign}${(absValue / 1000000).toFixed(1)}M`
  if (absValue >= 1000) return `${sign}${(absValue / 1000).toFixed(0)}K`
  return `${sign}${absValue.toFixed(0)}`
}

const formatCurrency = (value: number) => {
  // Absent is not zero: this returned `${currency} 0`, reporting zero money
  // for a field the server never sent. Notation is unchanged -- exact
  // `en-KE` grouping is a deliberate choice for this surface, and
  // switching it is a separate product decision.
  if (value === null || value === undefined) return NO_VALUE
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}
</script>
