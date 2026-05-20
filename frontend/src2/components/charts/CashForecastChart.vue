<template>
  <div class="w-full h-full">
    <div v-if="hasData" class="space-y-2">
      <!-- SVG Line Chart -->
      <div class="relative ml-14">
        <!-- Y-axis labels -->
        <div class="absolute -left-14 top-0 h-56 flex flex-col justify-between text-xs text-gray-500 w-12 text-right pr-2">
          <span>{{ formatCompact(maxValue) }}</span>
          <span>{{ formatCompact(maxValue * 0.75 + minValue * 0.25) }}</span>
          <span>{{ formatCompact(maxValue * 0.5 + minValue * 0.5) }}</span>
          <span>{{ formatCompact(maxValue * 0.25 + minValue * 0.75) }}</span>
          <span>{{ formatCompact(minValue) }}</span>
        </div>
        
        <svg class="w-full h-56" :viewBox="`0 0 ${chartWidth} ${chartHeight}`" preserveAspectRatio="none">
          <!-- Grid lines -->
          <line v-for="i in 5" :key="'grid-'+i"
            x1="0" :y1="(i-1) * chartHeight / 4"
            :x2="chartWidth" :y2="(i-1) * chartHeight / 4"
            stroke="#e5e7eb" stroke-dasharray="4,4" class="dark:stroke-gray-700"
          />
          
          <!-- Gradient definitions -->
          <defs>
            <linearGradient id="optimisticGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stop-color="#22c55e" stop-opacity="0.3"/>
              <stop offset="100%" stop-color="#22c55e" stop-opacity="0"/>
            </linearGradient>
            <linearGradient id="baseGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.3"/>
              <stop offset="100%" stop-color="#3b82f6" stop-opacity="0"/>
            </linearGradient>
            <linearGradient id="pessimisticGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.3"/>
              <stop offset="100%" stop-color="#f59e0b" stop-opacity="0"/>
            </linearGradient>
          </defs>
          
          <!-- Area fills -->
          <polygon :points="optimisticAreaPoints" fill="url(#optimisticGradient)" />
          <polygon :points="baseAreaPoints" fill="url(#baseGradient)" />
          <polygon :points="pessimisticAreaPoints" fill="url(#pessimisticGradient)" />
          
          <!-- Lines -->
          <polyline :points="optimisticLinePoints" fill="none" stroke="#22c55e" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
          <polyline :points="baseLinePoints" fill="none" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
          <polyline :points="pessimisticLinePoints" fill="none" stroke="#f59e0b" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
          
          <!-- Data points with tooltips -->
          <g v-for="(point, i) in chartPoints" :key="'pts-'+i">
            <circle :cx="point.x" :cy="point.optimistic" r="4" fill="#22c55e" stroke="white" stroke-width="2" class="cursor-pointer hover:r-6">
              <title>{{ point.label }} Optimistic: {{ formatCurrency(displayData[i].optimistic) }}</title>
            </circle>
            <circle :cx="point.x" :cy="point.base" r="4" fill="#3b82f6" stroke="white" stroke-width="2" class="cursor-pointer hover:r-6">
              <title>{{ point.label }} Base: {{ formatCurrency(displayData[i].base) }}</title>
            </circle>
            <circle :cx="point.x" :cy="point.pessimistic" r="4" fill="#f59e0b" stroke="white" stroke-width="2" class="cursor-pointer hover:r-6">
              <title>{{ point.label }} Pessimistic: {{ formatCurrency(displayData[i].pessimistic) }}</title>
            </circle>
          </g>
        </svg>
        
        <!-- X-axis labels -->
        <div class="flex justify-between text-xs text-gray-500 mt-2 px-1">
          <span v-for="(point, index) in displayData" :key="'x-'+index" class="text-center" :style="{ width: `${100/displayData.length}%` }">
            {{ point.shortLabel }}
          </span>
        </div>
      </div>

      <!-- Legend -->
      <div class="flex justify-center gap-6 text-xs mt-3">
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-0.5 bg-green-500 rounded"></div>
          <span class="text-gray-600 dark:text-gray-400">Optimistic</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-0.5 bg-blue-500 rounded"></div>
          <span class="text-gray-600 dark:text-gray-400">Base</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-0.5 bg-amber-500 rounded"></div>
          <span class="text-gray-600 dark:text-gray-400">Pessimistic</span>
        </div>
      </div>
      
      <!-- Summary stats -->
      <div class="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <div class="text-center">
          <p class="text-xs text-gray-500">Day 90 Optimistic</p>
          <p class="text-sm font-bold text-green-600">{{ formatCompact(lastOptimistic) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs text-gray-500">Day 90 Base</p>
          <p class="text-sm font-bold text-blue-600">{{ formatCompact(lastBase) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs text-gray-500">Day 90 Pessimistic</p>
          <p class="text-sm font-bold text-amber-600">{{ formatCompact(lastPessimistic) }}</p>
        </div>
      </div>
    </div>

    <div v-else class="flex items-center justify-center h-full text-gray-500">
      No forecast data available
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface ForecastPoint {
  date: string
  day: number
  balance: number
}

interface Props {
  base: ForecastPoint[]
  optimistic: ForecastPoint[]
  pessimistic: ForecastPoint[]
  currency?: string
}

const props = withDefaults(defineProps<Props>(), {
  currency: 'KES'
})

const chartWidth = 500
const chartHeight = 224
const padding = 10

const hasData = computed(() => props.base?.length > 0)

// Show every 7th day for cleaner display (weekly)
const displayData = computed(() => {
  if (!props.base?.length) return []
  
  const result = []
  for (let i = 6; i < props.base.length; i += 7) {
    result.push({
      label: props.base[i].date,
      shortLabel: `W${Math.ceil((i + 1) / 7)}`,
      base: props.base[i].balance,
      optimistic: props.optimistic?.[i]?.balance || props.base[i].balance,
      pessimistic: props.pessimistic?.[i]?.balance || props.base[i].balance
    })
  }
  return result
})

const maxValue = computed(() => {
  if (!displayData.value.length) return 1
  const allValues = displayData.value.flatMap(p => [p.base, p.optimistic, p.pessimistic])
  return Math.max(...allValues) * 1.05 // 5% padding
})

const minValue = computed(() => {
  if (!displayData.value.length) return 0
  const allValues = displayData.value.flatMap(p => [p.base, p.optimistic, p.pessimistic])
  const min = Math.min(...allValues)
  return min * 0.95 // 5% padding below
})

const lastOptimistic = computed(() => {
  if (!displayData.value.length) return 0
  return displayData.value[displayData.value.length - 1].optimistic
})

const lastBase = computed(() => {
  if (!displayData.value.length) return 0
  return displayData.value[displayData.value.length - 1].base
})

const lastPessimistic = computed(() => {
  if (!displayData.value.length) return 0
  return displayData.value[displayData.value.length - 1].pessimistic
})

const getX = (index: number) => {
  return padding + (index * (chartWidth - 2 * padding) / (displayData.value.length - 1 || 1))
}

const getY = (value: number) => {
  const range = maxValue.value - minValue.value
  if (range === 0) return chartHeight / 2
  return chartHeight - padding - ((value - minValue.value) / range) * (chartHeight - 2 * padding)
}

const chartPoints = computed(() => {
  return displayData.value.map((p, i) => ({
    x: getX(i),
    optimistic: getY(p.optimistic),
    base: getY(p.base),
    pessimistic: getY(p.pessimistic),
    label: p.shortLabel
  }))
})

const optimisticLinePoints = computed(() => {
  return chartPoints.value.map(p => `${p.x},${p.optimistic}`).join(' ')
})

const baseLinePoints = computed(() => {
  return chartPoints.value.map(p => `${p.x},${p.base}`).join(' ')
})

const pessimisticLinePoints = computed(() => {
  return chartPoints.value.map(p => `${p.x},${p.pessimistic}`).join(' ')
})

const optimisticAreaPoints = computed(() => {
  if (!chartPoints.value.length) return ''
  const points = chartPoints.value.map(p => `${p.x},${p.optimistic}`).join(' ')
  const firstX = chartPoints.value[0].x
  const lastX = chartPoints.value[chartPoints.value.length - 1].x
  return `${firstX},${chartHeight - padding} ${points} ${lastX},${chartHeight - padding}`
})

const baseAreaPoints = computed(() => {
  if (!chartPoints.value.length) return ''
  const points = chartPoints.value.map(p => `${p.x},${p.base}`).join(' ')
  const firstX = chartPoints.value[0].x
  const lastX = chartPoints.value[chartPoints.value.length - 1].x
  return `${firstX},${chartHeight - padding} ${points} ${lastX},${chartHeight - padding}`
})

const pessimisticAreaPoints = computed(() => {
  if (!chartPoints.value.length) return ''
  const points = chartPoints.value.map(p => `${p.x},${p.pessimistic}`).join(' ')
  const firstX = chartPoints.value[0].x
  const lastX = chartPoints.value[chartPoints.value.length - 1].x
  return `${firstX},${chartHeight - padding} ${points} ${lastX},${chartHeight - padding}`
})

const formatCurrency = (value: number) => {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: props.currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const formatCompact = (value: number) => {
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absValue >= 1000000) {
    return `${sign}${(absValue / 1000000).toFixed(1)}M`
  }
  if (absValue >= 1000) {
    return `${sign}${(absValue / 1000).toFixed(0)}K`
  }
  return sign + absValue.toFixed(0)
}
</script>
