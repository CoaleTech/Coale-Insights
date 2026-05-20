<template>
  <div class="w-full h-full flex items-center justify-center">
    <div v-if="chartData.length" class="flex items-center gap-8">
      <!-- Pie Chart Visualization -->
      <div class="relative">
        <svg :width="size" :height="size" class="transform -rotate-90">
          <circle
            v-for="(segment, index) in segments"
            :key="index"
            :cx="size / 2"
            :cy="size / 2"
            :r="radius"
            fill="none"
            :stroke="segment.color"
            :stroke-width="strokeWidth"
            :stroke-dasharray="`${segment.dashArray} ${circumference}`"
            :stroke-dashoffset="segment.offset"
            class="transition-all duration-500 cursor-pointer hover:opacity-80"
            :title="`${segment.label}: ${formatCurrency(segment.value)}`"
          />
        </svg>
        <!-- Center text -->
        <div class="absolute inset-0 flex items-center justify-center">
          <div class="text-center">
            <p class="text-lg font-bold text-gray-900 dark:text-white">
              {{ formatCurrency(total) }}
            </p>
            <p class="text-xs text-gray-500">Total</p>
          </div>
        </div>
      </div>

      <!-- Legend -->
      <div class="space-y-2">
        <div 
          v-for="(item, index) in chartData.slice(0, 6)" 
          :key="index"
          class="flex items-center gap-2"
        >
          <div 
            class="w-3 h-3 rounded-full flex-shrink-0"
            :style="{ backgroundColor: colors[index % colors.length] }"
          ></div>
          <span class="text-sm text-gray-600 dark:text-gray-400 truncate max-w-32">
            {{ item.category || item.name || item.label }}
          </span>
          <span class="text-sm font-medium text-gray-900 dark:text-white">
            {{ formatPercent(item.percentage || getPercentage(item.value || item.amount || 0)) }}
          </span>
        </div>
        <div v-if="chartData.length > 6" class="text-xs text-gray-500">
          +{{ chartData.length - 6 }} more categories
        </div>
      </div>
    </div>

    <div v-else class="text-gray-500">
      No expense data available
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  data: any[]
  currency?: string
}

const props = withDefaults(defineProps<Props>(), {
  currency: 'KES'
})

const size = 180
const strokeWidth = 32
const radius = (size - strokeWidth) / 2
const circumference = 2 * Math.PI * radius

const colors = [
  '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
  '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1'
]

const chartData = computed(() => props.data || [])

const total = computed(() => {
  return chartData.value.reduce((sum, item) => {
    return sum + (item.value || item.amount || 0)
  }, 0)
})

const getPercentage = (value: number): number => {
  if (total.value === 0) return 0
  return (value / total.value) * 100
}

const segments = computed(() => {
  let currentOffset = 0
  return chartData.value.map((item, index) => {
    const value = item.value || item.amount || 0
    const percentage = getPercentage(value)
    const dashArray = (percentage / 100) * circumference
    const offset = -currentOffset
    currentOffset += dashArray
    
    return {
      color: colors[index % colors.length],
      dashArray,
      offset,
      label: item.category || item.name || item.label || `Item ${index + 1}`,
      value,
      percentage
    }
  })
})

const formatCurrency = (value: number) => {
  if (value >= 1000000) {
    return `${props.currency} ${(value / 1000000).toFixed(1)}M`
  }
  if (value >= 1000) {
    return `${props.currency} ${(value / 1000).toFixed(0)}K`
  }
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: props.currency,
    minimumFractionDigits: 0
  }).format(value)
}

const formatPercent = (value: number) => {
  return `${value.toFixed(1)}%`
}
</script>
