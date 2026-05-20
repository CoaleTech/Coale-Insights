<template>
  <div class="w-full h-full">
    <div v-if="hasData" class="space-y-4">
      <!-- SVG Chart -->
      <div class="relative ml-14">
        <!-- Y-axis labels -->
        <div class="absolute -left-14 top-0 h-64 flex flex-col justify-between text-xs text-gray-500 w-12 text-right pr-2">
          <span>{{ formatCompact(maxValue) }}</span>
          <span>{{ formatCompact(maxValue * 0.75 + minValue * 0.25) }}</span>
          <span>{{ formatCompact(maxValue * 0.5 + minValue * 0.5) }}</span>
          <span>{{ formatCompact(maxValue * 0.25 + minValue * 0.75) }}</span>
          <span>{{ formatCompact(minValue) }}</span>
        </div>
        
        <svg class="w-full h-64" :viewBox="`0 0 ${chartWidth} ${chartHeight}`" preserveAspectRatio="none">
          <!-- Grid lines -->
          <line v-for="i in 5" :key="'grid-'+i"
            x1="0" :y1="(i-1) * chartHeight / 4"
            :x2="chartWidth" :y2="(i-1) * chartHeight / 4"
            stroke="#e5e7eb" stroke-dasharray="4,4" class="dark:stroke-gray-700"
          />
          
          <!-- Zero line -->
          <line 
            x1="0" :y1="zeroY"
            :x2="chartWidth" :y2="zeroY"
            stroke="#9ca3af" stroke-width="1"
          />
          
          <!-- Threshold line -->
          <line v-if="threshold > 0 && thresholdY >= 0 && thresholdY <= chartHeight"
            x1="0" :y1="thresholdY"
            :x2="chartWidth" :y2="thresholdY"
            stroke="#ef4444" stroke-width="2" stroke-dasharray="8,4"
          />
          <text v-if="threshold > 0 && thresholdY >= 0 && thresholdY <= chartHeight"
            :x="chartWidth - 5" :y="thresholdY - 5"
            fill="#ef4444" font-size="10" text-anchor="end"
          >
            Min Threshold
          </text>
          
          <!-- Bars for each week -->
          <g v-for="(week, i) in chartData" :key="'bar-'+i">
            <!-- Background bar for actual weeks -->
            <rect v-if="week.is_actual"
              :x="getBarX(i) - 2" :y="0"
              :width="barWidth + 4" :height="chartHeight"
              fill="#dbeafe" fill-opacity="0.5"
            />
            
            <!-- Current week highlight -->
            <rect v-if="week.is_current"
              :x="getBarX(i) - 2" :y="0"
              :width="barWidth + 4" :height="chartHeight"
              fill="#fef3c7" fill-opacity="0.5"
            />
            
            <!-- Inflow bar (green, going up from zero) -->
            <rect 
              :x="getBarX(i)" 
              :y="Math.min(zeroY, getY(week.inflows?.total || 0))"
              :width="barWidth / 2 - 1" 
              :height="Math.abs(zeroY - getY(week.inflows?.total || 0))"
              :fill="week.is_actual ? '#22c55e' : '#86efac'"
              :fill-opacity="week.is_forecast ? 0.7 : 1"
              rx="2"
            >
              <title>{{ week.week_label }}: Inflows {{ formatCurrency(week.inflows?.total || 0) }}</title>
            </rect>
            
            <!-- Outflow bar (red, going down from zero) -->
            <rect 
              :x="getBarX(i) + barWidth / 2" 
              :y="zeroY"
              :width="barWidth / 2 - 1" 
              :height="Math.abs(getY(-(week.outflows?.total || 0)) - zeroY)"
              :fill="week.is_actual ? '#ef4444' : '#fca5a5'"
              :fill-opacity="week.is_forecast ? 0.7 : 1"
              rx="2"
            >
              <title>{{ week.week_label }}: Outflows {{ formatCurrency(week.outflows?.total || 0) }}</title>
            </rect>
          </g>
          
          <!-- Balance line -->
          <polyline 
            :points="balanceLinePoints" 
            fill="none" 
            stroke="#3b82f6" 
            stroke-width="3" 
            stroke-linecap="round" 
            stroke-linejoin="round"
          />
          
          <!-- Balance points -->
          <g v-for="(week, i) in chartData" :key="'point-'+i">
            <circle 
              :cx="getBarX(i) + barWidth / 2" 
              :cy="getY(week.closing_balance)"
              r="5" 
              :fill="week.below_threshold ? '#ef4444' : '#3b82f6'" 
              stroke="white" 
              stroke-width="2"
              class="cursor-pointer"
            >
              <title>{{ week.week_label }}: Balance {{ formatCurrency(week.closing_balance) }}</title>
            </circle>
            
            <!-- Warning icon for below threshold -->
            <text v-if="week.below_threshold"
              :x="getBarX(i) + barWidth / 2"
              :y="getY(week.closing_balance) - 12"
              fill="#ef4444"
              font-size="14"
              text-anchor="middle"
            >⚠</text>
          </g>
        </svg>
        
        <!-- X-axis labels -->
        <div class="flex justify-between text-xs text-gray-500 mt-2">
          <div 
            v-for="(week, i) in chartData" 
            :key="'x-'+i" 
            class="text-center flex-1"
            :class="{
              'text-blue-600 font-medium': week.is_actual && !week.is_current,
              'text-amber-600 font-bold': week.is_current
            }"
          >
            {{ week.week_label }}
          </div>
        </div>
      </div>

      <!-- Legend -->
      <div class="flex justify-center gap-6 text-xs">
        <div class="flex items-center gap-1.5">
          <div class="w-3 h-3 bg-green-500 rounded-sm"></div>
          <span class="text-gray-600 dark:text-gray-400">Inflows</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-3 h-3 bg-red-500 rounded-sm"></div>
          <span class="text-gray-600 dark:text-gray-400">Outflows</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-0.5 bg-blue-500 rounded"></div>
          <span class="text-gray-600 dark:text-gray-400">Balance</span>
        </div>
        <div v-if="threshold > 0" class="flex items-center gap-1.5">
          <div class="w-4 h-0.5 bg-red-500 rounded border-dashed"></div>
          <span class="text-gray-600 dark:text-gray-400">Threshold</span>
        </div>
      </div>
      
      <!-- Summary stats -->
      <div class="grid grid-cols-4 gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <div class="text-center">
          <p class="text-xs text-gray-500">Avg Weekly Inflow</p>
          <p class="text-sm font-bold text-green-600">{{ formatCompact(avgInflow) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs text-gray-500">Avg Weekly Outflow</p>
          <p class="text-sm font-bold text-red-600">{{ formatCompact(avgOutflow) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs text-gray-500">Week 13 Balance</p>
          <p class="text-sm font-bold text-blue-600">{{ formatCompact(endingBalance) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs text-gray-500">Net Change</p>
          <p :class="['text-sm font-bold', netChange >= 0 ? 'text-green-600' : 'text-red-600']">
            {{ netChange >= 0 ? '+' : '' }}{{ formatCompact(netChange) }}
          </p>
        </div>
      </div>
    </div>

    <div v-else class="flex items-center justify-center h-full text-gray-500">
      No forecast data available
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'

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

// Chart dimensions
const chartWidth = 800
const chartHeight = 250
const padding = 20

// Computed
const hasData = computed(() => {
  return props.data?.weeks && props.data.weeks.length > 0
})

const chartData = computed(() => {
  return props.data?.weeks || []
})

const threshold = computed(() => {
  return props.threshold || props.data?.threshold || 0
})

// Calculate Y-axis range including inflows, outflows, and balances
const allValues = computed(() => {
  if (!chartData.value.length) return [0]
  const values: number[] = []
  chartData.value.forEach(w => {
    values.push(w.inflows?.total || 0)
    values.push(-(w.outflows?.total || 0))
    values.push(w.closing_balance)
  })
  if (threshold.value > 0) {
    values.push(threshold.value)
  }
  return values
})

const maxValue = computed(() => {
  const max = Math.max(...allValues.value)
  return max * 1.1 // Add 10% padding
})

const minValue = computed(() => {
  const min = Math.min(...allValues.value)
  return min < 0 ? min * 1.1 : 0
})

const valueRange = computed(() => {
  return maxValue.value - minValue.value
})

const zeroY = computed(() => {
  return chartHeight - ((0 - minValue.value) / valueRange.value) * chartHeight
})

const thresholdY = computed(() => {
  return chartHeight - ((threshold.value - minValue.value) / valueRange.value) * chartHeight
})

const barWidth = computed(() => {
  const numWeeks = chartData.value.length
  return (chartWidth - padding * 2) / numWeeks - 8
})

// Summary stats
const avgInflow = computed(() => {
  const weeks = chartData.value.filter(w => w.is_forecast)
  if (!weeks.length) return 0
  return weeks.reduce((sum, w) => sum + (w.inflows?.total || 0), 0) / weeks.length
})

const avgOutflow = computed(() => {
  const weeks = chartData.value.filter(w => w.is_forecast)
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

// Balance line points
const balanceLinePoints = computed(() => {
  if (!chartData.value.length) return ''
  return chartData.value.map((week, i) => {
    const x = getBarX(i) + barWidth.value / 2
    const y = getY(week.closing_balance)
    return `${x},${y}`
  }).join(' ')
})

// Methods
const getBarX = (index: number) => {
  return padding + index * ((chartWidth - padding * 2) / chartData.value.length) + 4
}

const getY = (value: number) => {
  return chartHeight - ((value - minValue.value) / valueRange.value) * chartHeight
}

const formatCompact = (value: number) => {
  if (value === null || value === undefined) return '0'
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absValue >= 1000000) return `${sign}${(absValue / 1000000).toFixed(1)}M`
  if (absValue >= 1000) return `${sign}${(absValue / 1000).toFixed(0)}K`
  return `${sign}${absValue.toFixed(0)}`
}

const formatCurrency = (value: number) => {
  if (value === null || value === undefined) return `${currency} 0`
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}
</script>
