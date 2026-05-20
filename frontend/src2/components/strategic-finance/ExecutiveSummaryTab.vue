<template>
  <div class="space-y-6">
    <!-- Key KPIs Row -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <!-- YTD Revenue -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
              <TrendingUp class="h-5 w-5 text-green-600" />
            </div>
            <div>
              <p class="text-sm text-gray-500 dark:text-gray-400">YTD Revenue</p>
              <p class="text-2xl font-bold text-gray-900 dark:text-white">
                {{ formatCurrency(data?.ytd_revenue || 0) }}
              </p>
            </div>
          </div>
        </div>
        <div class="mt-4 flex items-center gap-2">
          <span :class="getTrendClass(data?.revenue_growth)">
            {{ formatPercent(data?.revenue_growth) }}
          </span>
          <span class="text-xs text-gray-500">vs last year</span>
        </div>
      </div>

      <!-- YTD Expenses -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="p-2 bg-red-100 dark:bg-red-900/30 rounded-lg">
              <TrendingDown class="h-5 w-5 text-red-600" />
            </div>
            <div>
              <p class="text-sm text-gray-500 dark:text-gray-400">YTD Expenses</p>
              <p class="text-2xl font-bold text-gray-900 dark:text-white">
                {{ formatCurrency(data?.ytd_expenses || 0) }}
              </p>
            </div>
          </div>
        </div>
        <div class="mt-4 flex items-center gap-2">
          <span class="text-xs text-gray-500">Operating costs</span>
        </div>
      </div>

      <!-- Net Income -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <Banknote class="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <p class="text-sm text-gray-500 dark:text-gray-400">Net Income</p>
              <p class="text-2xl font-bold text-gray-900 dark:text-white">
                {{ formatCurrency(data?.ytd_net_income || 0) }}
              </p>
            </div>
          </div>
        </div>
        <div class="mt-4 flex items-center gap-2">
          <span :class="getMarginHealthClass(data?.net_margin)">
            {{ formatPercent(data?.net_margin) }} margin
          </span>
        </div>
      </div>

      <!-- Cash Position -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="p-2 bg-amber-100 dark:bg-amber-900/30 rounded-lg">
              <Wallet class="h-5 w-5 text-amber-600" />
            </div>
            <div>
              <p class="text-sm text-gray-500 dark:text-gray-400">Cash Position</p>
              <p class="text-2xl font-bold text-gray-900 dark:text-white">
                {{ formatCurrency(data?.cash_balance || 0) }}
              </p>
            </div>
          </div>
        </div>
        <div class="mt-4 flex items-center gap-2">
          <span class="text-xs text-gray-500">
            {{ data?.cash_runway_months || 0 }} months runway
          </span>
        </div>
      </div>
    </div>

    <!-- KPIs from Backend -->
    <div v-if="data?.kpis?.length" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <div 
        v-for="(kpi, index) in data.kpis" 
        :key="index"
        class="bg-gradient-to-br from-gray-50 to-white dark:from-gray-800 dark:to-gray-900 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-700"
      >
        <p class="text-sm text-gray-500 dark:text-gray-400">{{ kpi.label }}</p>
        <p class="text-xl font-bold text-gray-900 dark:text-white mt-1">
          {{ formatKpiValue(kpi.value, kpi.format) }}
        </p>
        <p v-if="kpi.subtitle" class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ kpi.subtitle }}</p>
      </div>
    </div>

    <!-- Revenue & Profit Trends -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Monthly Performance Trend - Line Chart -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <BarChart3 class="h-5 w-5 text-gray-500" />
          Monthly Performance Trend
        </h3>
        <div v-if="data?.monthly_trends?.length" class="space-y-4">
          <!-- SVG Line Chart -->
          <div class="relative ml-12">
            <!-- Y-axis labels -->
            <div class="absolute -left-12 top-0 h-48 flex flex-col justify-between text-xs text-gray-400 w-10 text-right">
              <span>{{ formatCompactValue(maxTrendValue) }}</span>
              <span>{{ formatCompactValue(maxTrendValue * 0.75) }}</span>
              <span>{{ formatCompactValue(maxTrendValue * 0.5) }}</span>
              <span>{{ formatCompactValue(maxTrendValue * 0.25) }}</span>
              <span>0</span>
            </div>
            <svg class="w-full h-48" :viewBox="`0 0 ${chartWidth} ${chartHeight}`" preserveAspectRatio="none">
              <!-- Grid lines -->
              <line v-for="i in 4" :key="'grid-'+i" 
                x1="0" :y1="chartHeight * (i-1) / 4" 
                :x2="chartWidth" :y2="chartHeight * (i-1) / 4" 
                stroke="#e5e7eb" stroke-dasharray="4,4" class="dark:stroke-gray-700"/>
              
              <!-- Revenue line (green) -->
              <polyline 
                :points="revenueLinePoints"
                fill="none" 
                stroke="#22c55e" 
                stroke-width="2.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <!-- Revenue area fill -->
              <polygon 
                :points="revenueAreaPoints"
                fill="url(#revenueGradient)" 
                opacity="0.2"
              />
              
              <!-- Expenses line (red) -->
              <polyline 
                :points="expensesLinePoints"
                fill="none" 
                stroke="#ef4444" 
                stroke-width="2.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <!-- Expenses area fill -->
              <polygon 
                :points="expensesAreaPoints"
                fill="url(#expensesGradient)" 
                opacity="0.2"
              />
              
              <!-- Net Income line (blue) -->
              <polyline 
                :points="netIncomeLinePoints"
                fill="none" 
                stroke="#3b82f6" 
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-dasharray="6,3"
              />
              
              <!-- Data points - Revenue -->
              <circle v-for="(point, i) in revenuePoints" :key="'rev-pt-'+i"
                :cx="point.x" :cy="point.y" r="4"
                fill="#22c55e" stroke="white" stroke-width="2"
                class="cursor-pointer hover:r-6 transition-all"
              >
                <title>{{ formatMonthLabel(data.monthly_trends[i].period) }}: {{ formatCurrencyValue(data.monthly_trends[i].revenue) }}</title>
              </circle>
              
              <!-- Data points - Expenses -->
              <circle v-for="(point, i) in expensesPoints" :key="'exp-pt-'+i"
                :cx="point.x" :cy="point.y" r="4"
                fill="#ef4444" stroke="white" stroke-width="2"
                class="cursor-pointer hover:r-6 transition-all"
              >
                <title>{{ formatMonthLabel(data.monthly_trends[i].period) }}: {{ formatCurrencyValue(data.monthly_trends[i].expenses) }}</title>
              </circle>
              
              <!-- Data points - Net Income -->
              <circle v-for="(point, i) in netIncomePoints" :key="'net-pt-'+i"
                :cx="point.x" :cy="point.y" r="3.5"
                fill="#3b82f6" stroke="white" stroke-width="2"
                class="cursor-pointer hover:r-6 transition-all"
              >
                <title>{{ formatMonthLabel(data.monthly_trends[i].period) }}: {{ formatCurrencyValue(data.monthly_trends[i].net_income) }}</title>
              </circle>
              
              <!-- Gradients -->
              <defs>
                <linearGradient id="revenueGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stop-color="#22c55e"/>
                  <stop offset="100%" stop-color="#22c55e" stop-opacity="0"/>
                </linearGradient>
                <linearGradient id="expensesGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stop-color="#ef4444"/>
                  <stop offset="100%" stop-color="#ef4444" stop-opacity="0"/>
                </linearGradient>
              </defs>
            </svg>
            <!-- X-axis labels -->
            <div class="flex justify-between text-xs text-gray-500 mt-1 px-1">
              <span v-for="trend in data.monthly_trends" :key="'x-'+trend.period" class="text-center flex-1">
                {{ formatMonthLabel(trend.period) }}
              </span>
            </div>
          </div>
          <!-- Legend -->
          <div class="flex justify-center gap-6 text-xs">
            <span class="flex items-center gap-1.5"><span class="w-4 h-0.5 bg-green-500 rounded"></span> Revenue</span>
            <span class="flex items-center gap-1.5"><span class="w-4 h-0.5 bg-red-500 rounded"></span> Expenses</span>
            <span class="flex items-center gap-1.5"><span class="w-4 h-0.5 bg-blue-500 rounded border-dashed"></span> Net Income</span>
          </div>
          <!-- Performance summary table (months as columns) -->
          <div class="overflow-x-auto mt-4">
            <table class="w-full text-xs">
              <thead>
                <tr class="text-gray-500 border-b dark:border-gray-700">
                  <th class="py-2 text-left font-medium sticky left-0 bg-white dark:bg-gray-800">Metric</th>
                  <th v-for="trend in data.monthly_trends" :key="trend.period" class="py-2 text-right font-medium px-2">
                    {{ formatMonthLabel(trend.period) }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr class="border-b dark:border-gray-700/50">
                  <td class="py-2 font-medium text-green-600 sticky left-0 bg-white dark:bg-gray-800">Revenue</td>
                  <td v-for="trend in data.monthly_trends" :key="'rev-'+trend.period" class="py-2 text-right text-gray-900 dark:text-white font-medium px-2">
                    {{ formatCompactValue(trend.revenue) }}
                  </td>
                </tr>
                <tr class="border-b dark:border-gray-700/50">
                  <td class="py-2 font-medium text-red-500 sticky left-0 bg-white dark:bg-gray-800">Expenses</td>
                  <td v-for="trend in data.monthly_trends" :key="'exp-'+trend.period" class="py-2 text-right text-gray-900 dark:text-white font-medium px-2">
                    {{ formatCompactValue(trend.expenses) }}
                  </td>
                </tr>
                <tr class="border-b dark:border-gray-700/50">
                  <td class="py-2 font-medium text-blue-600 sticky left-0 bg-white dark:bg-gray-800">Net Income</td>
                  <td v-for="trend in data.monthly_trends" :key="'net-'+trend.period" class="py-2 text-right font-medium px-2" :class="trend.net_income >= 0 ? 'text-green-600' : 'text-red-500'">
                    {{ formatCompactValue(trend.net_income) }}
                  </td>
                </tr>
                <tr>
                  <td class="py-2 font-medium text-gray-700 dark:text-gray-300 sticky left-0 bg-white dark:bg-gray-800">Margin</td>
                  <td v-for="trend in data.monthly_trends" :key="'margin-'+trend.period" class="py-2 text-right font-medium px-2" :class="trend.margin >= 0 ? 'text-green-600' : 'text-red-500'">
                    {{ trend.margin }}%
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-else class="h-64 flex items-center justify-center text-gray-500">
          No revenue data available
        </div>
      </div>

      <!-- Expense Breakdown -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <PieChartIcon class="h-5 w-5 text-gray-500" />
          Expense Breakdown
        </h3>
        <div v-if="expenseBreakdown?.length" class="h-64">
          <ExpensePieChart :data="expenseBreakdown" :currency="currency" />
        </div>
        <div v-else class="h-64 flex items-center justify-center text-gray-500">
          No expense data available
        </div>
      </div>
    </div>

    <!-- Financial Health Scorecard -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <Activity class="h-5 w-5 text-gray-500" />
        Financial Health Scorecard
      </h3>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <!-- Liquidity Score -->
        <div class="text-center">
          <div class="relative inline-flex items-center justify-center">
            <svg class="w-24 h-24 transform -rotate-90">
              <circle cx="48" cy="48" r="40" stroke="currentColor" stroke-width="8" fill="none" 
                class="text-gray-200 dark:text-gray-700" />
              <circle cx="48" cy="48" r="40" stroke="currentColor" stroke-width="8" fill="none"
                :stroke-dasharray="251.2"
                :stroke-dashoffset="251.2 - (251.2 * (data?.health_scores?.liquidity || 0) / 100)"
                :class="getScoreColorClass(data?.health_scores?.liquidity)" />
            </svg>
            <span class="absolute text-xl font-bold text-gray-900 dark:text-white">
              {{ data?.health_scores?.liquidity || 0 }}
            </span>
          </div>
          <p class="mt-2 text-sm font-medium text-gray-700 dark:text-gray-300">Liquidity</p>
          <p class="text-xs text-gray-500">{{ data?.health_scores?.liquidity_status || 'N/A' }}</p>
        </div>

        <!-- Profitability Score -->
        <div class="text-center">
          <div class="relative inline-flex items-center justify-center">
            <svg class="w-24 h-24 transform -rotate-90">
              <circle cx="48" cy="48" r="40" stroke="currentColor" stroke-width="8" fill="none" 
                class="text-gray-200 dark:text-gray-700" />
              <circle cx="48" cy="48" r="40" stroke="currentColor" stroke-width="8" fill="none"
                :stroke-dasharray="251.2"
                :stroke-dashoffset="251.2 - (251.2 * (data?.health_scores?.profitability || 0) / 100)"
                :class="getScoreColorClass(data?.health_scores?.profitability)" />
            </svg>
            <span class="absolute text-xl font-bold text-gray-900 dark:text-white">
              {{ data?.health_scores?.profitability || 0 }}
            </span>
          </div>
          <p class="mt-2 text-sm font-medium text-gray-700 dark:text-gray-300">Profitability</p>
          <p class="text-xs text-gray-500">{{ data?.health_scores?.profitability_status || 'N/A' }}</p>
        </div>

        <!-- Efficiency Score -->
        <div class="text-center">
          <div class="relative inline-flex items-center justify-center">
            <svg class="w-24 h-24 transform -rotate-90">
              <circle cx="48" cy="48" r="40" stroke="currentColor" stroke-width="8" fill="none" 
                class="text-gray-200 dark:text-gray-700" />
              <circle cx="48" cy="48" r="40" stroke="currentColor" stroke-width="8" fill="none"
                :stroke-dasharray="251.2"
                :stroke-dashoffset="251.2 - (251.2 * (data?.health_scores?.efficiency || 0) / 100)"
                :class="getScoreColorClass(data?.health_scores?.efficiency)" />
            </svg>
            <span class="absolute text-xl font-bold text-gray-900 dark:text-white">
              {{ data?.health_scores?.efficiency || 0 }}
            </span>
          </div>
          <p class="mt-2 text-sm font-medium text-gray-700 dark:text-gray-300">Efficiency</p>
          <p class="text-xs text-gray-500">{{ data?.health_scores?.efficiency_status || 'N/A' }}</p>
        </div>
      </div>
    </div>

    <!-- Key Insights -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <Lightbulb class="h-5 w-5 text-amber-500" />
        Key Executive Insights
      </h3>
      <div v-if="data?.key_insights?.length" class="space-y-3">
        <div 
          v-for="(insight, index) in data.key_insights" 
          :key="index"
          :class="[
            'p-4 rounded-lg border-l-4',
            getInsightClass(insight.type)
          ]"
        >
          <div class="flex items-start gap-3">
            <component :is="getInsightIcon(insight.type)" class="h-5 w-5 flex-shrink-0 mt-0.5" />
            <div>
              <p class="font-medium text-gray-900 dark:text-white">{{ insight.title }}</p>
              <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">{{ insight.description }}</p>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="text-center py-8 text-gray-500">
        No insights available yet
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { markRaw } from 'vue'
import { 
  TrendingUp, 
  TrendingDown,
  Banknote, 
  Percent, 
  Wallet, 
  BarChart3, 
  PieChart as PieChartIcon,
  Activity,
  Lightbulb,
  AlertTriangle,
  CheckCircle2,
  Info
} from 'lucide-vue-next'
import MonthlyBarChart from '../charts/MonthlyBarChart.vue'
import ExpensePieChart from '../charts/ExpensePieChart.vue'
import { inject } from 'vue'

interface Props {
  data: any
  expenseBreakdown?: any[]
}

const props = defineProps<Props>()
const currency = inject('currency', 'KES')

const formatCurrency = (value: number) => {
  if (value === null || value === undefined) return `${currency} 0`
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const formatKpiValue = (value: number | null | undefined, format: string) => {
  if (value === null || value === undefined) return 'N/A'
  switch (format) {
    case 'currency':
      return formatCurrency(value)
    case 'percent':
      return `${value.toFixed(1)}%`
    case 'number':
      return new Intl.NumberFormat('en-KE').format(value)
    case 'months':
      return `${value.toFixed(1)} months`
    default:
      return String(value)
  }
}

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '0%'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

const getTrendClass = (value: number | null | undefined) => {
  if (!value) return 'text-gray-500 text-sm'
  return value >= 0 
    ? 'text-green-600 bg-green-100 dark:bg-green-900/30 px-2 py-0.5 rounded text-sm font-medium'
    : 'text-red-600 bg-red-100 dark:bg-red-900/30 px-2 py-0.5 rounded text-sm font-medium'
}

const getMarginHealth = (margin: number | null | undefined) => {
  if (!margin) return 'No data'
  if (margin >= 20) return 'Excellent'
  if (margin >= 10) return 'Good'
  if (margin >= 5) return 'Fair'
  return 'Needs Improvement'
}

const getMarginHealthClass = (margin: number | null | undefined) => {
  if (!margin) return 'text-gray-500 text-xs'
  if (margin >= 20) return 'text-green-600 bg-green-100 dark:bg-green-900/30 px-2 py-0.5 rounded text-xs font-medium'
  if (margin >= 10) return 'text-blue-600 bg-blue-100 dark:bg-blue-900/30 px-2 py-0.5 rounded text-xs font-medium'
  if (margin >= 5) return 'text-amber-600 bg-amber-100 dark:bg-amber-900/30 px-2 py-0.5 rounded text-xs font-medium'
  return 'text-red-600 bg-red-100 dark:bg-red-900/30 px-2 py-0.5 rounded text-xs font-medium'
}

const getScoreColorClass = (score: number | null | undefined) => {
  if (!score) return 'text-gray-400'
  if (score >= 75) return 'text-green-500'
  if (score >= 50) return 'text-amber-500'
  return 'text-red-500'
}

const getInsightClass = (type: string) => {
  switch (type) {
    case 'success': return 'bg-green-50 dark:bg-green-900/20 border-green-500'
    case 'warning': return 'bg-amber-50 dark:bg-amber-900/20 border-amber-500'
    case 'danger': return 'bg-red-50 dark:bg-red-900/20 border-red-500'
    default: return 'bg-blue-50 dark:bg-blue-900/20 border-blue-500'
  }
}

const getInsightIcon = (type: string) => {
  switch (type) {
    case 'success': return markRaw(CheckCircle2)
    case 'warning': return markRaw(AlertTriangle)
    case 'danger': return markRaw(TrendingDown)
    default: return markRaw(Info)
  }
}

// Monthly Trend Chart helpers
import { computed } from 'vue'

const maxTrendValue = computed(() => {
  if (!props.data?.monthly_trends?.length) return 1
  const allValues = props.data.monthly_trends.flatMap((t: any) => [t.revenue, t.expenses])
  return Math.max(...allValues) || 1
})

const maxNetIncome = computed(() => {
  if (!props.data?.monthly_trends?.length) return 1
  const netValues = props.data.monthly_trends.map((t: any) => Math.abs(t.net_income))
  return Math.max(...netValues) || 1
})

const getBarHeightPercent = (value: number) => {
  return Math.max(5, (Math.abs(value) / maxTrendValue.value) * 100)
}

const getNetIncomePosition = (value: number) => {
  // Position the net income dot relative to the chart height
  // Scale it between 20% and 80% of chart height based on net income value
  const normalized = (Math.abs(value) / maxNetIncome.value)
  return 20 + (normalized * 60) // Range from 20% to 80%
}

const formatMonthLabel = (period: string) => {
  if (!period) return ''
  const [year, month] = period.split('-')
  const date = new Date(parseInt(year), parseInt(month) - 1)
  return date.toLocaleDateString('en-KE', { month: 'short' })
}

const formatCompactValue = (value: number) => {
  if (value === null || value === undefined) return '0'
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absValue >= 1000000) return `${sign}${(absValue / 1000000).toFixed(1)}M`
  if (absValue >= 1000) return `${sign}${(absValue / 1000).toFixed(0)}K`
  return `${sign}${absValue.toFixed(0)}`
}

const formatCurrencyValue = (value: number) => {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

// Line Chart computed properties
const chartWidth = 400
const chartHeight = 180
const padding = 10

const getXPosition = (index: number, total: number) => {
  return padding + (index * (chartWidth - 2 * padding) / (total - 1))
}

const getYPosition = (value: number, maxVal: number) => {
  return chartHeight - padding - ((value / maxVal) * (chartHeight - 2 * padding))
}

const revenuePoints = computed(() => {
  if (!props.data?.monthly_trends?.length) return []
  return props.data.monthly_trends.map((t: any, i: number) => ({
    x: getXPosition(i, props.data.monthly_trends.length),
    y: getYPosition(t.revenue, maxTrendValue.value)
  }))
})

const expensesPoints = computed(() => {
  if (!props.data?.monthly_trends?.length) return []
  return props.data.monthly_trends.map((t: any, i: number) => ({
    x: getXPosition(i, props.data.monthly_trends.length),
    y: getYPosition(t.expenses, maxTrendValue.value)
  }))
})

const netIncomePoints = computed(() => {
  if (!props.data?.monthly_trends?.length) return []
  // Net income can be negative, so we need to handle it differently
  const maxAbsNet = Math.max(...props.data.monthly_trends.map((t: any) => Math.abs(t.net_income)))
  return props.data.monthly_trends.map((t: any, i: number) => ({
    x: getXPosition(i, props.data.monthly_trends.length),
    y: chartHeight / 2 - ((t.net_income / (maxAbsNet * 1.2)) * (chartHeight / 2 - padding))
  }))
})

const revenueLinePoints = computed(() => {
  return revenuePoints.value.map(p => `${p.x},${p.y}`).join(' ')
})

const expensesLinePoints = computed(() => {
  return expensesPoints.value.map(p => `${p.x},${p.y}`).join(' ')
})

const netIncomeLinePoints = computed(() => {
  return netIncomePoints.value.map(p => `${p.x},${p.y}`).join(' ')
})

const revenueAreaPoints = computed(() => {
  if (!revenuePoints.value.length) return ''
  const points = revenuePoints.value.map(p => `${p.x},${p.y}`).join(' ')
  const firstX = revenuePoints.value[0].x
  const lastX = revenuePoints.value[revenuePoints.value.length - 1].x
  return `${firstX},${chartHeight - padding} ${points} ${lastX},${chartHeight - padding}`
})

const expensesAreaPoints = computed(() => {
  if (!expensesPoints.value.length) return ''
  const points = expensesPoints.value.map(p => `${p.x},${p.y}`).join(' ')
  const firstX = expensesPoints.value[0].x
  const lastX = expensesPoints.value[expensesPoints.value.length - 1].x
  return `${firstX},${chartHeight - padding} ${points} ${lastX},${chartHeight - padding}`
})
</script>
