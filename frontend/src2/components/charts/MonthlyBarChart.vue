<template>
  <div class="w-full h-full">
    <div v-if="chartData.length" class="relative h-full">
      <!-- Y-axis -->
      <div class="absolute -left-14 top-0 h-full flex flex-col justify-between text-xs text-gray-500">
        <span>{{ formatCompact(maxValue) }}</span>
        <span>{{ formatCompact(maxValue * 0.5) }}</span>
        <span>0</span>
      </div>
      
      <!-- Chart area -->
      <div class="h-full flex items-end justify-around gap-2 px-2 border-l border-b border-gray-300 dark:border-gray-600">
        <div 
          v-for="(item, index) in chartData" 
          :key="index"
          class="flex flex-col items-center flex-1 max-w-16"
        >
          <!-- Bar -->
          <div 
            :class="[
              'w-full rounded-t transition-all duration-300 cursor-pointer hover:opacity-80',
              getBarColor
            ]"
            :style="{ height: `${getBarHeight(getItemValue(item))}%` }"
            :title="`${getItemLabel(item)}: ${formatCurrency(getItemValue(item))}`"
          ></div>
          <!-- Label -->
          <span class="text-xs text-gray-500 mt-2 truncate w-full text-center">
            {{ getItemLabel(item) }}
          </span>
        </div>
      </div>
    </div>

    <div v-else class="flex items-center justify-center h-full text-gray-500">
      No data available
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  data: any[]
  keyField: string
  valueField: string
  color?: string
  currency?: string
}

const props = withDefaults(defineProps<Props>(), {
  color: 'blue',
  currency: 'KES'
})

const chartData = computed(() => props.data || [])

const getBarColor = computed(() => {
  const colors: Record<string, string> = {
    green: 'bg-green-500',
    blue: 'bg-blue-500',
    red: 'bg-red-500',
    amber: 'bg-amber-500',
    purple: 'bg-purple-500'
  }
  return colors[props.color] || 'bg-blue-500'
})

const getItemValue = (item: any): number => {
  return item[props.valueField] || 0
}

const getItemLabel = (item: any): string => {
  const label = item[props.keyField] || ''
  // Shorten month names
  if (typeof label === 'string' && label.match(/^\d{4}-\d{2}/)) {
    const date = new Date(label)
    return date.toLocaleDateString('en-KE', { month: 'short' })
  }
  return label
}

const maxValue = computed(() => {
  if (!chartData.value.length) return 1
  const max = Math.max(...chartData.value.map(item => Math.abs(getItemValue(item))))
  return max || 1
})

const getBarHeight = (value: number) => {
  return Math.max(5, (Math.abs(value) / maxValue.value) * 100)
}

const formatCurrency = (value: number) => {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: props.currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const formatCompact = (value: number) => {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
  if (value >= 1000) return `${(value / 1000).toFixed(0)}K`
  return value.toFixed(0)
}
</script>
