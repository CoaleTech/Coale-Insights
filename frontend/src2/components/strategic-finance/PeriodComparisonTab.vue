<template>
  <div class="space-y-6">
    <!-- Period Selector -->
    <div class="flex gap-4 mb-6">
      <button
        v-for="period in periods"
        :key="period.id"
        @click="selectedPeriod = period.id"
        :class="[
          'px-4 py-2 rounded-lg font-medium transition-colors',
          selectedPeriod === period.id
            ? 'bg-blue-600 text-white'
            : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
        ]"
      >
        {{ period.label }}
      </button>
    </div>

    <!-- Comparison Summary Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <!-- Revenue -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center justify-between mb-2">
          <p class="text-sm text-gray-500 dark:text-gray-400">Revenue</p>
          <span :class="getTrendBadge(currentPeriodData?.revenue_change)">
            {{ formatChange(currentPeriodData?.revenue_change) }}
          </span>
        </div>
        <div class="flex items-baseline gap-2">
          <p class="text-xl font-bold text-gray-900 dark:text-white">
            {{ formatCurrency(currentPeriodData?.current_revenue || 0) }}
          </p>
          <p class="text-sm text-gray-500">
            vs {{ formatCurrency(currentPeriodData?.previous_revenue || 0) }}
          </p>
        </div>
      </div>

      <!-- Expenses -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center justify-between mb-2">
          <p class="text-sm text-gray-500 dark:text-gray-400">Expenses</p>
          <span :class="getExpenseTrendBadge(currentPeriodData?.expense_change)">
            {{ formatChange(currentPeriodData?.expense_change) }}
          </span>
        </div>
        <div class="flex items-baseline gap-2">
          <p class="text-xl font-bold text-gray-900 dark:text-white">
            {{ formatCurrency(currentPeriodData?.current_expenses || 0) }}
          </p>
          <p class="text-sm text-gray-500">
            vs {{ formatCurrency(currentPeriodData?.previous_expenses || 0) }}
          </p>
        </div>
      </div>

      <!-- Net Profit -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center justify-between mb-2">
          <p class="text-sm text-gray-500 dark:text-gray-400">Net Profit</p>
          <span :class="getTrendBadge(currentPeriodData?.profit_change)">
            {{ formatChange(currentPeriodData?.profit_change) }}
          </span>
        </div>
        <div class="flex items-baseline gap-2">
          <p class="text-xl font-bold text-gray-900 dark:text-white">
            {{ formatCurrency(currentPeriodData?.current_profit || 0) }}
          </p>
          <p class="text-sm text-gray-500">
            vs {{ formatCurrency(currentPeriodData?.previous_profit || 0) }}
          </p>
        </div>
      </div>

      <!-- Margin -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center justify-between mb-2">
          <p class="text-sm text-gray-500 dark:text-gray-400">Profit Margin</p>
          <span :class="getTrendBadge(currentPeriodData?.margin_change)">
            {{ formatBps(currentPeriodData?.margin_change) }}
          </span>
        </div>
        <div class="flex items-baseline gap-2">
          <p class="text-xl font-bold text-gray-900 dark:text-white">
            {{ formatPercent(currentPeriodData?.current_margin) }}
          </p>
          <p class="text-sm text-gray-500">
            vs {{ formatPercent(currentPeriodData?.previous_margin) }}
          </p>
        </div>
      </div>
    </div>

    <!-- Detailed Comparison Table -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <BarChart3 class="h-5 w-5 text-gray-500" />
        Detailed {{ selectedPeriodLabel }} Comparison
      </h3>
      
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead class="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Metric</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Current Period</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Previous Period</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Change</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">% Change</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr v-for="item in comparisonItems" :key="item.label" class="hover:bg-gray-50 dark:hover:bg-gray-700">
              <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">{{ item.label }}</td>
              <td class="px-4 py-3 text-sm text-right text-gray-900 dark:text-white">
                {{ formatCurrency(item.current) }}
              </td>
              <td class="px-4 py-3 text-sm text-right text-gray-600 dark:text-gray-400">
                {{ formatCurrency(item.previous) }}
              </td>
              <td class="px-4 py-3 text-sm text-right" :class="getChangeClass(item.change, item.invertColors)">
                {{ formatCurrency(item.change) }}
              </td>
              <td class="px-4 py-3 text-sm text-right">
                <span :class="getTrendBadgeSmall(item.percentChange, item.invertColors)">
                  {{ formatChange(item.percentChange) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Comparison Summary Table -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <TrendingUp class="h-5 w-5 text-gray-500" />
        Period Comparison Summary
      </h3>
      <div v-if="data?.summary?.length" class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead class="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Comparison</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Revenue Change</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Expense Change</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Net Income Change</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr v-for="(item, index) in data.summary" :key="index" 
                class="hover:bg-gray-50 dark:hover:bg-gray-700">
              <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                {{ item.comparison }}
              </td>
              <td class="px-4 py-3 text-sm text-right">
                <span :class="item.revenue_change >= 0 ? 'text-green-600' : 'text-red-600'">
                  {{ formatChange(item.revenue_change) }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-right">
                <span :class="item.expense_change <= 0 ? 'text-green-600' : 'text-red-600'">
                  {{ formatChange(item.expense_change) }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-right">
                <span :class="item.net_income_change >= 0 ? 'text-green-600' : 'text-red-600'">
                  {{ formatChange(item.net_income_change) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center py-8 text-gray-500">
        No comparison data available
      </div>
    </div>

    <!-- Key Insights -->
    <div v-if="currentPeriodData?.insights?.length" class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <Lightbulb class="h-5 w-5 text-amber-500" />
        Key Insights
      </h3>
      <div class="space-y-3">
        <div 
          v-for="(insight, index) in currentPeriodData.insights" 
          :key="index"
          :class="[
            'p-4 rounded-lg border-l-4',
            getInsightClass(insight.type)
          ]"
        >
          <div class="flex items-start gap-3">
            <component :is="getInsightIcon(insight.type)" class="h-5 w-5 flex-shrink-0 mt-0.5" />
            <p class="text-gray-700 dark:text-gray-300">{{ insight.message }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, markRaw, inject } from 'vue'
import { 
  BarChart3, 
  TrendingUp, 
  TrendingDown,
  Lightbulb,
  CheckCircle2,
  AlertTriangle,
  Info
} from 'lucide-vue-next'

interface Props {
  data: any
}

const props = defineProps<Props>()

const currency = inject('currency', 'KES')
const selectedPeriod = ref('mom')

const periods = [
  { id: 'mom', label: 'Month-over-Month' },
  { id: 'qoq', label: 'Quarter-over-Quarter' },
  { id: 'yoy', label: 'Year-over-Year' }
]

const selectedPeriodLabel = computed(() => {
  return periods.find(p => p.id === selectedPeriod.value)?.label || ''
})

const currentPeriodData = computed(() => {
  if (!props.data) return null
  const periodData = props.data[selectedPeriod.value]
  if (!periodData) return null
  
  // Map API structure to expected format
  return {
    current_revenue: periodData.current?.revenue || 0,
    previous_revenue: periodData.prior?.revenue || 0,
    current_expenses: periodData.current?.expenses || 0,
    previous_expenses: periodData.prior?.expenses || 0,
    current_profit: periodData.current?.net_income || 0,
    previous_profit: periodData.prior?.net_income || 0,
    current_margin: periodData.current?.margin || 0,
    previous_margin: periodData.prior?.margin || 0,
    revenue_change: periodData.revenue_change || 0,
    expense_change: periodData.expense_change || 0,
    profit_change: periodData.net_income_change || 0,
    margin_change: (periodData.current?.margin || 0) - (periodData.prior?.margin || 0),
    current_label: periodData.current?.label || 'Current',
    prior_label: periodData.prior?.label || 'Prior'
  }
})

const comparisonItems = computed(() => {
  const d = currentPeriodData.value
  if (!d) return []
  
  return [
    {
      label: 'Revenue',
      current: d.current_revenue,
      previous: d.previous_revenue,
      change: d.current_revenue - d.previous_revenue,
      percentChange: d.revenue_change,
      invertColors: false
    },
    {
      label: 'Total Expenses',
      current: d.current_expenses,
      previous: d.previous_expenses,
      change: d.current_expenses - d.previous_expenses,
      percentChange: d.expense_change,
      invertColors: true
    },
    {
      label: 'Net Profit',
      current: d.current_profit,
      previous: d.previous_profit,
      change: d.current_profit - d.previous_profit,
      percentChange: d.profit_change,
      invertColors: false
    }
  ]
})

const formatCurrency = (value: number | null | undefined) => {
  if (value === null || value === undefined) return `${currency} 0`
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '0%'
  return `${value.toFixed(1)}%`
}

const formatChange = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '0%'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

const formatBps = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '0 bps'
  const sign = value > 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(0)} bps`
}

const getTrendBadge = (value: number | null | undefined) => {
  if (!value) return 'px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-400'
  const base = 'px-2 py-0.5 rounded text-xs font-medium'
  return value >= 0
    ? `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`
    : `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`
}

const getExpenseTrendBadge = (value: number | null | undefined) => {
  // For expenses, lower is better
  if (!value) return 'px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-400'
  const base = 'px-2 py-0.5 rounded text-xs font-medium'
  return value <= 0
    ? `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`
    : `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`
}

const getTrendBadgeSmall = (value: number | null | undefined, invertColors: boolean = false) => {
  if (!value) return 'text-gray-500'
  const isPositive = invertColors ? value <= 0 : value >= 0
  return isPositive ? 'text-green-600 font-medium' : 'text-red-600 font-medium'
}

const getChangeClass = (value: number | null | undefined, invertColors: boolean = false) => {
  if (!value) return 'text-gray-600 dark:text-gray-400'
  const isPositive = invertColors ? value <= 0 : value >= 0
  return isPositive ? 'text-green-600 font-medium' : 'text-red-600 font-medium'
}

const getInsightClass = (type: string) => {
  switch (type) {
    case 'positive': return 'bg-green-50 dark:bg-green-900/20 border-green-500'
    case 'warning': return 'bg-amber-50 dark:bg-amber-900/20 border-amber-500'
    case 'negative': return 'bg-red-50 dark:bg-red-900/20 border-red-500'
    default: return 'bg-blue-50 dark:bg-blue-900/20 border-blue-500'
  }
}

const getInsightIcon = (type: string) => {
  switch (type) {
    case 'positive': return markRaw(CheckCircle2)
    case 'warning': return markRaw(AlertTriangle)
    case 'negative': return markRaw(TrendingDown)
    default: return markRaw(Info)
  }
}
</script>
