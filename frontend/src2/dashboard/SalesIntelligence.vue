<script setup lang="ts">
defineOptions({ name: 'SalesIntelligence' })
import { Breadcrumbs } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { 
  RefreshCcw, Loader2, TrendingUp, TrendingDown, DollarSign, 
  CreditCard, Banknote, Users, Package, BarChart3, PieChart, 
  Activity, Target, ShoppingCart, Percent, Calendar, ArrowUpRight,
  ArrowDownRight, AlertTriangle, CheckCircle, Clock
} from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { createToast } from '../helpers/toasts'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import BaseChart from '../charts/components/BaseChart.vue'
import TerritoryMap from '../components/TerritoryMap.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'

// Router for AI chat navigation
const router = useRouter()

// State
const isLoading = ref(true)
const isRefreshing = ref(false)
const error = ref<string | null>(null)
const data = ref<any>(null)
const showDailySales = ref(false)

// Training state
const isTraining = ref<string | false>(false)
const trainingStatus = ref('')

// Source attribution state
const sourceAttribution = ref<any>(null)
const quotationAnalytics = ref<any>(null)
const territoryPerformanceData = ref<any>(null)
const isLoadingSources = ref(false)

// Dimensional forecast state
const dimensionalForecast = ref<any>({})
const isLoadingDimensional = ref(false)
const productGroupPage = ref(0)
const territoryPage = ref(0)

// Active tab
const activeTab = ref('overview')
const tabs = [
  { id: 'overview', label: 'Revenue Overview', icon: TrendingUp },
  { id: 'payment', label: 'Cash vs Credit', icon: CreditCard },
  { id: 'reps', label: 'Sales Reps', icon: Users },
  { id: 'dimensions', label: 'Breakdown', icon: PieChart },
  { id: 'margins', label: 'Margins', icon: Percent },
  { id: 'forecasts', label: 'Forecasts', icon: Activity },
  { id: 'sources', label: 'Source Attribution', icon: Target },
]

// Date range filter
const dateRange = ref('12m')
const dateRanges = [
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
  { value: '90d', label: 'Last 90 Days' },
  { value: '12m', label: 'Last 12 Months' },
  { value: '24m', label: 'Last 24 Months' },
]

const SALES_ENDPOINT = 'insights.api.ml.sales.get_sales_detail'
const drillDown = useDrillDown()

// Load sales intelligence data
async function loadData(refresh = false) {
  if (refresh) {
    isRefreshing.value = true
  } else {
    isLoading.value = true
  }
  error.value = null
  
  try {
    const result = await apiCall('insights.api.ml.sales_intelligence', {
      refresh: refresh,
      date_filter: dateRange.value
    })

    data.value = result
    createToast({
      title: 'Data Loaded',
      message: `Analyzed ${result?.summary?.total_transactions || 0} transactions`,
      variant: 'success'
    })
  } catch (e: any) {
    error.value = e.message || 'Failed to load sales intelligence'
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

// Computed values
const summary = computed(() => data.value?.summary || {})
const revenueMetrics = computed(() => data.value?.revenue_metrics || {})
const paymentMix = computed(() => data.value?.payment_mix || {})
const salesReps = computed(() => data.value?.sales_reps || {})
const comparisons = computed(() => data.value?.comparisons || {})
const dimensions = computed(() => data.value?.dimensions || {})
const margins = computed(() => data.value?.margins || {})
const pipeline = computed(() => data.value?.pipeline || {})
const fulfillment = computed(() => data.value?.fulfillment || {})
const forecasts = computed(() => data.value?.forecasts || {})

// Format helpers
function formatCurrency(value: number): string {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`
  return value?.toFixed(0) || '0'
}

function formatPercent(value: number): string {
  return `${value?.toFixed(1) || 0}%`
}

function formatNumber(value: number): string {
  return value?.toLocaleString() || '0'
}

function getGrowthClass(value: number): string {
  if (value > 0) return 'text-green-600'
  if (value < 0) return 'text-red-600'
  return 'text-gray-600'
}

function getGrowthIcon(value: number) {
  return value >= 0 ? ArrowUpRight : ArrowDownRight
}

// Train ML forecast models
async function trainForecasts(modelType: string) {
  isTraining.value = modelType
  trainingStatus.value = ''
  
  try {
    const result = await apiCall('insights.api.ml.train_forecast_models', {
      model_type: modelType
    })

    trainingStatus.value = `✓ Successfully trained ${modelType} forecast model(s)`
    createToast({
      title: 'Training Complete',
      message: result?.message || 'Training complete',
      variant: 'success'
    })
    // Reload main data to get updated forecasts
    await loadData(true)
  } catch (e: any) {
    trainingStatus.value = `✗ Training error: ${e.message}`
    createToast({
      title: 'Training Error',
      message: e.message,
      variant: 'error'
    })
  } finally {
    isTraining.value = false
  }
}

// Load dimensional forecast data
async function loadDimensionalForecast() {
  isLoadingDimensional.value = true
  
  try {
    const result = await apiCall('insights.api.ml.get_historical_and_forecast_by_dimension', {
      dimension: 'both'
    })

    dimensionalForecast.value = result
    productGroupPage.value = 0
    territoryPage.value = 0
  } catch (e: any) {
    createToast({
      title: 'Error',
      message: 'Failed to load dimensional forecast',
      variant: 'error'
    })
  } finally {
    isLoadingDimensional.value = false
  }
}

// Load source attribution data
async function loadSourceAttribution() {
  isLoadingSources.value = true
  try {
    const [attribution, quotation, territory] = await Promise.all([
      apiCall('insights.api.ml.sales.source_attributed_sales', { date_filter: dateRange.value }),
      apiCall('insights.api.ml.sales.quotation_analytics', { date_filter: dateRange.value }),
      apiCall('insights.api.ml.sales.territory_performance', { date_filter: dateRange.value }),
    ])
    sourceAttribution.value = attribution
    quotationAnalytics.value = quotation
    territoryPerformanceData.value = territory
  } catch (e: any) {
    console.error('Error loading source attribution:', e)
  } finally {
    isLoadingSources.value = false
  }
}

// Paginated data computed
const paginatedProductGroupData = computed(() => {
  const data = dimensionalForecast.value.combined_product_group || []
  const start = productGroupPage.value * 10
  return data.slice(start, start + 10)
})

const paginatedTerritoryData = computed(() => {
  const data = dimensionalForecast.value.combined_territory || []
  const start = territoryPage.value * 10
  return data.slice(start, start + 10)
})

// Transposed Product Group data - months as columns, product groups as rows
const transposedProductGroupData = computed(() => {
  const rawData = dimensionalForecast.value.combined_product_group || []
  if (!rawData.length) return { periods: [], rows: [] }
  
  // Get unique periods and product groups
  const periodsSet = new Set<string>()
  const groupsMap = new Map<string, Map<string, { revenue: number; transactions: number; is_forecast: boolean }>>()
  
  rawData.forEach((item: any) => {
    periodsSet.add(item.period)
    if (!groupsMap.has(item.product_group)) {
      groupsMap.set(item.product_group, new Map())
    }
    groupsMap.get(item.product_group)!.set(item.period, {
      revenue: item.revenue,
      transactions: item.transactions,
      is_forecast: item.is_forecast
    })
  })
  
  // Sort periods chronologically
  const periods = Array.from(periodsSet).sort()
  
  // Build rows with totals
  const rows: any[] = []
  groupsMap.forEach((periodData, productGroup) => {
    let totalRevenue = 0
    let totalTransactions = 0
    const values: any = {}
    
    periods.forEach(period => {
      const data = periodData.get(period)
      if (data) {
        values[period] = data
        totalRevenue += data.revenue
        totalTransactions += data.transactions
      } else {
        values[period] = { revenue: 0, transactions: 0, is_forecast: false }
      }
    })
    
    rows.push({
      product_group: productGroup,
      values,
      total_revenue: totalRevenue,
      total_transactions: totalTransactions
    })
  })
  
  // Sort by total revenue descending
  rows.sort((a, b) => b.total_revenue - a.total_revenue)
  
  return { periods, rows }
})

// Paginated transposed product group rows
const paginatedTransposedProductGroups = computed(() => {
  const start = productGroupPage.value * 15
  return transposedProductGroupData.value.rows.slice(start, start + 15)
})

// Transposed Territory data - months as columns, territories as rows
const transposedTerritoryData = computed(() => {
  const rawData = dimensionalForecast.value.combined_territory || []
  if (!rawData.length) return { periods: [], rows: [] }
  
  // Get unique periods and territories
  const periodsSet = new Set<string>()
  const territoriesMap = new Map<string, Map<string, { revenue: number; transactions: number; is_forecast: boolean }>>()
  
  rawData.forEach((item: any) => {
    periodsSet.add(item.period)
    if (!territoriesMap.has(item.territory)) {
      territoriesMap.set(item.territory, new Map())
    }
    territoriesMap.get(item.territory)!.set(item.period, {
      revenue: item.revenue,
      transactions: item.transactions,
      is_forecast: item.is_forecast
    })
  })
  
  // Sort periods chronologically
  const periods = Array.from(periodsSet).sort()
  
  // Build rows with totals
  const rows: any[] = []
  territoriesMap.forEach((periodData, territory) => {
    let totalRevenue = 0
    let totalTransactions = 0
    const values: any = {}
    
    periods.forEach(period => {
      const data = periodData.get(period)
      if (data) {
        values[period] = data
        totalRevenue += data.revenue
        totalTransactions += data.transactions
      } else {
        values[period] = { revenue: 0, transactions: 0, is_forecast: false }
      }
    })
    
    rows.push({
      territory,
      values,
      total_revenue: totalRevenue,
      total_transactions: totalTransactions
    })
  })
  
  // Sort by total revenue descending
  rows.sort((a, b) => b.total_revenue - a.total_revenue)
  
  return { periods, rows }
})

// Paginated transposed territory rows
const paginatedTransposedTerritories = computed(() => {
  const start = territoryPage.value * 15
  return transposedTerritoryData.value.rows.slice(start, start + 15)
})

// Transposed Daily Cash Ratio - dates as columns, metrics as rows
const transposedDailyCashRatio = computed(() => {
  const dailyMix = paymentMix.value.daily_mix || []
  if (!dailyMix.length) return { dates: [], rows: [] }
  
  // Get last 15 days, most recent first
  const recentDays = dailyMix.slice(0, 15).reverse()
  const dates = recentDays.map(d => d.sale_date)
  
  // Build rows for each metric
  const rows = [
    {
      metric: 'Cash',
      values: recentDays.reduce((acc, d) => { acc[d.sale_date] = d.Cash || 0; return acc }, {} as Record<string, number>),
      total: recentDays.reduce((sum, d) => sum + (d.Cash || 0), 0),
      colorClass: 'text-green-600'
    },
    {
      metric: 'Credit',
      values: recentDays.reduce((acc, d) => { acc[d.sale_date] = d.Credit || 0; return acc }, {} as Record<string, number>),
      total: recentDays.reduce((sum, d) => sum + (d.Credit || 0), 0),
      colorClass: 'text-blue-600'
    },
    {
      metric: 'Total',
      values: recentDays.reduce((acc, d) => { acc[d.sale_date] = d.total || 0; return acc }, {} as Record<string, number>),
      total: recentDays.reduce((sum, d) => sum + (d.total || 0), 0),
      colorClass: 'text-gray-900 font-bold'
    },
    {
      metric: 'Cash %',
      values: recentDays.reduce((acc, d) => { acc[d.sale_date] = d.cash_pct || 0; return acc }, {} as Record<string, number>),
      total: recentDays.length > 0 ? recentDays.reduce((sum, d) => sum + (d.cash_pct || 0), 0) / recentDays.length : 0,
      colorClass: 'text-green-700',
      isPercent: true
    }
  ]
  
  return { dates, rows }
})

// Transposed Weekly Performance - weeks as columns, metrics as rows
const transposedWeeklyPerformance = computed(() => {
  const weeklyData = revenueMetrics.value.weekly_sales || []
  if (!weeklyData.length) return { weeks: [], rows: [] }
  
  // Get last 8 weeks
  const recentWeeks = weeklyData.slice(-8)
  const weeks = recentWeeks.map(w => ({ label: `W${w.week}`, year: w.year, week: w.week }))
  
  const rows = [
    {
      metric: 'Revenue',
      values: recentWeeks.reduce((acc, w) => { acc[`W${w.week}`] = w.revenue || 0; return acc }, {} as Record<string, number>),
      total: recentWeeks.reduce((sum, w) => sum + (w.revenue || 0), 0),
      colorClass: 'text-green-600 font-bold',
      isCurrency: true
    },
    {
      metric: 'Orders',
      values: recentWeeks.reduce((acc, w) => { acc[`W${w.week}`] = w.transactions || 0; return acc }, {} as Record<string, number>),
      total: recentWeeks.reduce((sum, w) => sum + (w.transactions || 0), 0),
      colorClass: 'text-gray-700',
      isCurrency: false
    },
    {
      metric: 'AOV',
      values: recentWeeks.reduce((acc, w) => { 
        acc[`W${w.week}`] = w.transactions > 0 ? w.revenue / w.transactions : 0
        return acc 
      }, {} as Record<string, number>),
      total: recentWeeks.reduce((sum, w) => sum + (w.revenue || 0), 0) / Math.max(1, recentWeeks.reduce((sum, w) => sum + (w.transactions || 0), 0)),
      colorClass: 'text-blue-600',
      isCurrency: true
    }
  ]
  
  return { weeks, rows }
})

// Transposed Monthly Summary - months as columns, metrics as rows
const transposedMonthlySummary = computed(() => {
  const monthlyData = revenueMetrics.value.monthly_sales || []
  if (!monthlyData.length) return { months: [], rows: [] }
  
  // Get last 6 months
  const recentMonths = monthlyData.slice(-6)
  const months = recentMonths.map(m => m.period)
  
  const rows = [
    {
      metric: 'Revenue',
      values: recentMonths.reduce((acc, m) => { acc[m.period] = m.revenue || 0; return acc }, {} as Record<string, number>),
      total: recentMonths.reduce((sum, m) => sum + (m.revenue || 0), 0),
      colorClass: 'text-green-600 font-bold',
      isCurrency: true
    },
    {
      metric: 'Orders',
      values: recentMonths.reduce((acc, m) => { acc[m.period] = m.transactions || 0; return acc }, {} as Record<string, number>),
      total: recentMonths.reduce((sum, m) => sum + (m.transactions || 0), 0),
      colorClass: 'text-gray-700',
      isCurrency: false
    },
    {
      metric: 'Customers',
      values: recentMonths.reduce((acc, m) => { acc[m.period] = m.unique_customers || 0; return acc }, {} as Record<string, number>),
      total: recentMonths.reduce((sum, m) => sum + (m.unique_customers || 0), 0),
      colorClass: 'text-purple-600',
      isCurrency: false
    }
  ]
  
  return { months, rows }
})

// Transposed Daily Sales - dates as columns, metrics as rows
const transposedDailySales = computed(() => {
  const dailyData = revenueMetrics.value.daily_sales || []
  if (!dailyData.length) return { dates: [], rows: [] }
  
  // Get last 15 days, most recent first then reverse for display
  const recentDays = dailyData.slice(0, 15).reverse()
  const dates = recentDays.map(d => d.date)
  
  const rows = [
    {
      metric: 'Revenue',
      values: recentDays.reduce((acc, d) => { acc[d.date] = d.revenue || 0; return acc }, {} as Record<string, number>),
      total: recentDays.reduce((sum, d) => sum + (d.revenue || 0), 0),
      colorClass: 'text-green-600 font-bold',
      isCurrency: true
    },
    {
      metric: 'Transactions',
      values: recentDays.reduce((acc, d) => { acc[d.date] = d.transactions || 0; return acc }, {} as Record<string, number>),
      total: recentDays.reduce((sum, d) => sum + (d.transactions || 0), 0),
      colorClass: 'text-gray-700',
      isCurrency: false
    },
    {
      metric: 'Avg Order',
      values: recentDays.reduce((acc, d) => { 
        acc[d.date] = d.transactions > 0 ? d.revenue / d.transactions : 0
        return acc 
      }, {} as Record<string, number>),
      total: recentDays.reduce((sum, d) => sum + (d.revenue || 0), 0) / Math.max(1, recentDays.reduce((sum, d) => sum + (d.transactions || 0), 0)),
      colorClass: 'text-blue-600',
      isCurrency: true
    }
  ]
  
  return { dates, rows }
})

// Format date for column header (e.g., "2025-12-20" -> "Dec 20")
function formatDateShort(dateStr: string): string {
  const date = new Date(dateStr)
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${monthNames[date.getMonth()]} ${date.getDate()}`
}

// Helper to format period for display (e.g., "2025-06" -> "Jun 25")
function formatPeriod(period: string): string {
  const [year, month] = period.split('-')
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${monthNames[parseInt(month) - 1]} ${year.slice(2)}`
}

// Check if period is forecast (after current month)
function isPeriodForecast(period: string): boolean {
  const now = new Date()
  const currentPeriod = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  return period > currentPeriod
}

// Load on mount
onMounted(() => {
  loadData()
  loadDimensionalForecast()
  loadSourceAttribution()
})

// Watch for date filter changes
watch(dateRange, () => {
  loadData()
  loadDimensionalForecast()
  loadSourceAttribution()
})

// Breadcrumbs
const breadcrumbs = [
  { label: 'Insights', href: '/insights' },
  { label: 'Sales Intelligence' }
]

// AI Chat context - computed from dashboard data
const chatContext = computed(() => ({
  summary: summary.value,
  revenue_metrics: revenueMetrics.value,
  payment_mix: paymentMix.value,
  sales_reps: salesReps.value,
  comparisons: comparisons.value,
  dimensions: dimensions.value,
  margins: margins.value,
  forecasts: forecasts.value,
  period: dateRange.value
}))

// Handle AI chat dashboard navigation
function handleDashboardRedirect(target: string) {
  router.push(`/${target}-intelligence`)
}

// Source attribution chart options
const attributionChartOptions = computed(() => {
  if (!sourceAttribution.value?.length) return {}
  const data = sourceAttribution.value.slice(0, 10)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['Revenue', 'Profit', 'Orders'] },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: data.map((d: any) => d.source) },
    yAxis: [
      { type: 'value', name: 'Amount' },
      { type: 'value', name: 'Orders' }
    ],
    series: [
      { name: 'Revenue', type: 'bar', data: data.map((d: any) => d.revenue), itemStyle: { color: '#3b82f6' } },
      { name: 'Profit', type: 'bar', data: data.map((d: any) => d.gross_profit), itemStyle: { color: '#10b981' } },
      { name: 'Orders', type: 'bar', yAxisIndex: 1, data: data.map((d: any) => d.order_count), itemStyle: { color: '#f59e0b' } },
    ]
  }
})

const lostReasonsChartOptions = computed(() => {
  if (!quotationAnalytics.value?.lost_reasons?.length) return {}
  return {
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', left: 'left' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: quotationAnalytics.value.lost_reasons.map((r: any) => ({
        name: r.order_lost_reason,
        value: r.count
      }))
    }]
  }
})

const territoryPerformanceWorldData = computed(() => {
  if (!territoryPerformanceData.value) return []
  return territoryPerformanceData.value.map((t: any) => ({ name: t.territory, value: t.revenue }))
})
</script>

<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 bg-white border-b">
      <div>
        <Breadcrumbs :items="breadcrumbs" />
        <h1 class="text-2xl font-bold text-gray-900 mt-1">Sales Intelligence</h1>
        <p class="text-sm text-gray-500">Comprehensive sales analytics and performance metrics</p>
      </div>
      <div class="flex items-center gap-3">
        <select 
          v-model="dateRange" 
          class="px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-blue-500"
        >
          <option v-for="range in dateRanges" :key="range.value" :value="range.value">
            {{ range.label }}
          </option>
        </select>
        <button
          @click="loadData(true)"
          :disabled="isRefreshing"
          class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <RefreshCcw v-if="!isRefreshing" class="w-4 h-4" />
          <Loader2 v-else class="w-4 h-4 animate-spin" />
          Refresh
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <Loader2 class="w-12 h-12 mx-auto text-blue-600 animate-spin" />
        <p class="mt-4 text-gray-600">Loading sales intelligence...</p>
      </div>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <AlertTriangle class="w-12 h-12 mx-auto text-red-500" />
        <p class="mt-4 text-gray-900 font-medium">Failed to load data</p>
        <p class="text-gray-600">{{ error }}</p>
        <button
          @click="loadData()"
          class="mt-4 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700"
        >
          Try Again
        </button>
      </div>
    </div>

    <!-- Main Content -->
    <div v-else class="flex-1 overflow-auto p-6">
      <!-- Summary Cards -->
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
        <!-- Total Revenue -->
        <div class="bg-white rounded-xl shadow-sm p-4 border cursor-pointer hover:ring-2 hover:ring-blue-300 transition-shadow"
             @click="drillDown.open(SALES_ENDPOINT, 'Total Revenue', { metric: 'total_orders' })">
          <div class="flex items-center justify-between">
            <DollarSign class="w-8 h-8 text-green-500" />
            <span :class="['text-sm font-medium', getGrowthClass(summary.mom_growth)]">
              {{ summary.mom_growth >= 0 ? '+' : '' }}{{ formatPercent(summary.mom_growth) }}
            </span>
          </div>
          <p class="text-2xl font-bold mt-2">{{ formatCurrency(summary.total_revenue) }}</p>
          <p class="text-sm text-gray-500">Total Revenue</p>
        </div>

        <!-- Cash Ratio -->
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <div class="flex items-center justify-between">
            <Banknote class="w-8 h-8 text-blue-500" />
            <span class="text-sm text-gray-500">Today: {{ formatPercent(paymentMix.today_cash_pct) }}</span>
          </div>
          <p class="text-2xl font-bold mt-2">{{ formatPercent(summary.cash_ratio) }}</p>
          <p class="text-sm text-gray-500">Cash Sales</p>
        </div>

        <!-- AOV -->
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <div class="flex items-center justify-between">
            <ShoppingCart class="w-8 h-8 text-purple-500" />
          </div>
          <p class="text-2xl font-bold mt-2">{{ formatCurrency(summary.avg_order_value) }}</p>
          <p class="text-sm text-gray-500">Avg Order Value</p>
        </div>

        <!-- Transactions -->
        <div class="bg-white rounded-xl shadow-sm p-4 border cursor-pointer hover:ring-2 hover:ring-blue-300 transition-shadow"
             @click="drillDown.open(SALES_ENDPOINT, 'Total Orders', { metric: 'total_orders' })">
          <div class="flex items-center justify-between">
            <BarChart3 class="w-8 h-8 text-orange-500" />
          </div>
          <p class="text-2xl font-bold mt-2">{{ formatNumber(summary.total_transactions) }}</p>
          <p class="text-sm text-gray-500">Transactions</p>
        </div>

        <!-- Gross Margin -->
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <div class="flex items-center justify-between">
            <Percent class="w-8 h-8 text-teal-500" />
          </div>
          <p class="text-2xl font-bold mt-2">{{ formatPercent(summary.overall_margin) }}</p>
          <p class="text-sm text-gray-500">Gross Margin</p>
        </div>

        <!-- YoY Growth -->
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <div class="flex items-center justify-between">
            <component :is="getGrowthIcon(summary.yoy_growth)" :class="['w-8 h-8', getGrowthClass(summary.yoy_growth)]" />
          </div>
          <p :class="['text-2xl font-bold mt-2', getGrowthClass(summary.yoy_growth)]">
            {{ summary.yoy_growth >= 0 ? '+' : '' }}{{ formatPercent(summary.yoy_growth) }}
          </p>
          <p class="text-sm text-gray-500">YoY Growth</p>
        </div>
      </div>

      <!-- Tabs -->
      <div class="bg-white rounded-xl shadow-sm border mb-6">
        <div class="flex border-b overflow-x-auto">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            @click="activeTab = tab.id"
            :class="[
              'flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 -mb-px',
              activeTab === tab.id 
                ? 'text-blue-600 border-blue-600' 
                : 'text-gray-500 border-transparent hover:text-gray-700'
            ]"
          >
            <component :is="tab.icon" class="w-4 h-4" />
            {{ tab.label }}
          </button>
        </div>

        <!-- Tab Content -->
        <div class="p-6">
          <!-- Revenue Overview Tab -->
          <div v-if="activeTab === 'overview'">
            <!-- Quick Stats Row -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div class="bg-gradient-to-br from-blue-500 to-blue-600 rounded-lg p-4 text-white">
                <p class="text-sm opacity-80">Unique Customers</p>
                <p class="text-2xl font-bold">{{ formatNumber(revenueMetrics.unique_customers || summary.unique_customers) }}</p>
              </div>
              <div class="bg-gradient-to-br from-green-500 to-green-600 rounded-lg p-4 text-white">
                <p class="text-sm opacity-80">Avg Days Between Orders</p>
                <p class="text-2xl font-bold">{{ revenueMetrics.avg_days_between_orders || '-' }}</p>
              </div>
              <div class="bg-gradient-to-br from-purple-500 to-purple-600 rounded-lg p-4 text-white">
                <p class="text-sm opacity-80">Fulfillment Rate</p>
                <p class="text-2xl font-bold">{{ formatPercent(fulfillment.fulfillment_rate || summary.fulfillment_rate) }}</p>
              </div>
              <div class="bg-gradient-to-br from-orange-500 to-orange-600 rounded-lg p-4 text-white">
                <p class="text-sm opacity-80">Days Sales Outstanding</p>
                <p class="text-2xl font-bold">{{ fulfillment.dso?.toFixed(0) || summary.dso?.toFixed(0) || '-' }}</p>
              </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <!-- MoM/YoY Comparison Cards -->
              <div class="lg:col-span-1 space-y-4">
                <h3 class="font-semibold text-gray-900 flex items-center gap-2">
                  <Calendar class="w-4 h-4" />
                  Period Comparison
                </h3>
                
                <!-- Current Month -->
                <div class="bg-gradient-to-r from-blue-50 to-blue-100 rounded-lg p-4 border border-blue-200">
                  <div class="flex justify-between items-start">
                    <div>
                      <p class="text-sm text-blue-600 font-medium">Current Month</p>
                      <p class="text-2xl font-bold text-blue-900">{{ formatCurrency(comparisons.current_month?.revenue || 0) }}</p>
                    </div>
                    <span class="px-2 py-1 bg-blue-200 text-blue-800 rounded text-xs font-medium">
                      {{ comparisons.current_month?.period }}
                    </span>
                  </div>
                  <div class="flex gap-4 mt-2 text-sm text-blue-600">
                    <span>{{ formatNumber(comparisons.current_month?.transactions || 0) }} orders</span>
                    <span>AOV: {{ formatCurrency(comparisons.current_month?.aov || 0) }}</span>
                  </div>
                </div>

                <!-- Last Month -->
                <div class="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <div class="flex justify-between items-center">
                    <p class="text-sm text-gray-600 font-medium">Previous Month</p>
                    <span :class="['text-sm font-bold px-2 py-1 rounded', comparisons.mom_growth >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700']">
                      {{ comparisons.mom_growth >= 0 ? '↑' : '↓' }} {{ Math.abs(comparisons.mom_growth || 0).toFixed(1) }}%
                    </span>
                  </div>
                  <p class="text-xl font-bold text-gray-900">{{ formatCurrency(comparisons.last_month?.revenue || 0) }}</p>
                  <p class="text-xs text-gray-500 mt-1">{{ formatNumber(comparisons.last_month?.transactions || 0) }} transactions</p>
                </div>

                <!-- Same Month Last Year -->
                <div class="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <div class="flex justify-between items-center">
                    <p class="text-sm text-gray-600 font-medium">Same Month Last Year</p>
                    <span :class="['text-sm font-bold px-2 py-1 rounded', comparisons.yoy_growth >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700']">
                      {{ comparisons.yoy_growth >= 0 ? '↑' : '↓' }} {{ Math.abs(comparisons.yoy_growth || 0).toFixed(1) }}%
                    </span>
                  </div>
                  <p class="text-xl font-bold text-gray-900">{{ formatCurrency(comparisons.last_year_same_month?.revenue || 0) }}</p>
                  <p class="text-xs text-gray-500 mt-1">{{ formatNumber(comparisons.last_year_same_month?.transactions || 0) }} transactions</p>
                </div>
              </div>

              <!-- Monthly Trend Chart -->
              <div class="lg:col-span-2">
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <TrendingUp class="w-4 h-4" />
                  Monthly Revenue Trend
                </h3>
                <div class="bg-gray-50 rounded-lg p-4 border">
                  <div class="h-56">
                    <div class="flex items-end h-full gap-1">
                      <div 
                        v-for="(month, idx) in comparisons.monthly_trend" 
                        :key="idx"
                        class="flex-1 flex flex-col items-center group"
                      >
                        <div class="relative w-full">
                          <!-- Bar -->
                          <div 
                            :class="[
                              'w-full rounded-t transition-all cursor-pointer',
                              month.mom_pct >= 0 ? 'bg-blue-500 hover:bg-blue-600' : 'bg-blue-400 hover:bg-blue-500'
                            ]"
                            :style="{ 
                              height: `${Math.max(20, (month.revenue / Math.max(...comparisons.monthly_trend.map((m: any) => m.revenue || 1))) * 160)}px` 
                            }"
                          ></div>
                          <!-- Tooltip -->
                          <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-10">
                            <div class="bg-gray-800 text-white text-xs rounded py-1 px-2 whitespace-nowrap">
                              <p class="font-bold">{{ month.period }}</p>
                              <p>{{ formatCurrency(month.revenue) }}</p>
                              <p :class="month.mom_pct >= 0 ? 'text-green-300' : 'text-red-300'">
                                {{ month.mom_pct >= 0 ? '+' : '' }}{{ month.mom_pct?.toFixed(1) }}% MoM
                              </p>
                            </div>
                          </div>
                        </div>
                        <!-- Month label -->
                        <p class="text-xs text-gray-500 mt-2 font-medium">{{ month.period?.slice(5) }}</p>
                        <!-- MoM indicator -->
                        <p :class="['text-xs font-medium', month.mom_pct >= 0 ? 'text-green-600' : 'text-red-600']">
                          {{ month.mom_pct >= 0 ? '↑' : '↓' }}{{ Math.abs(month.mom_pct || 0).toFixed(0) }}%
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Weekly Sales Section -->
            <div class="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Weekly Performance - Transposed -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <BarChart3 class="w-4 h-4" />
                  Weekly Performance
                </h3>
                <div v-if="transposedWeeklyPerformance.weeks.length" class="bg-white rounded-lg border overflow-x-auto">
                  <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                      <tr>
                        <th class="px-3 py-2 text-left sticky left-0 bg-gray-50 z-10 min-w-[80px]">Metric</th>
                        <th 
                          v-for="week in transposedWeeklyPerformance.weeks" 
                          :key="week.label"
                          class="px-2 py-2 text-right min-w-[70px] text-xs"
                        >
                          {{ week.label }}
                        </th>
                        <th class="px-3 py-2 text-right bg-gray-100 min-w-[85px]">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr 
                        v-for="row in transposedWeeklyPerformance.rows" 
                        :key="row.metric" 
                        class="border-b hover:bg-blue-50"
                      >
                        <td class="px-3 py-2 font-medium sticky left-0 bg-white z-10" :class="row.colorClass">
                          {{ row.metric }}
                        </td>
                        <td 
                          v-for="week in transposedWeeklyPerformance.weeks" 
                          :key="week.label"
                          class="px-2 py-2 text-right text-xs"
                          :class="row.colorClass"
                        >
                          {{ row.isCurrency ? formatCurrency(row.values[week.label]) : formatNumber(row.values[week.label]) }}
                        </td>
                        <td class="px-3 py-2 text-right bg-gray-50 font-bold" :class="row.colorClass">
                          {{ row.isCurrency ? formatCurrency(row.total) : formatNumber(row.total) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-else class="text-center py-6 text-gray-500 bg-gray-50 rounded-lg border">
                  No weekly data available
                </div>
              </div>

              <!-- Monthly Summary - Transposed -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <Calendar class="w-4 h-4" />
                  Monthly Summary
                </h3>
                <div v-if="transposedMonthlySummary.months.length" class="bg-white rounded-lg border overflow-x-auto">
                  <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                      <tr>
                        <th class="px-3 py-2 text-left sticky left-0 bg-gray-50 z-10 min-w-[80px]">Metric</th>
                        <th 
                          v-for="month in transposedMonthlySummary.months" 
                          :key="month"
                          class="px-2 py-2 text-right min-w-[70px] text-xs"
                        >
                          {{ formatPeriod(month) }}
                        </th>
                        <th class="px-3 py-2 text-right bg-gray-100 min-w-[85px]">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr 
                        v-for="row in transposedMonthlySummary.rows" 
                        :key="row.metric" 
                        class="border-b hover:bg-blue-50"
                      >
                        <td class="px-3 py-2 font-medium sticky left-0 bg-white z-10" :class="row.colorClass">
                          {{ row.metric }}
                        </td>
                        <td 
                          v-for="month in transposedMonthlySummary.months" 
                          :key="month"
                          class="px-2 py-2 text-right text-xs"
                          :class="row.colorClass"
                        >
                          {{ row.isCurrency ? formatCurrency(row.values[month]) : formatNumber(row.values[month]) }}
                        </td>
                        <td class="px-3 py-2 text-right bg-gray-50 font-bold" :class="row.colorClass">
                          {{ row.isCurrency ? formatCurrency(row.total) : formatNumber(row.total) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-else class="text-center py-6 text-gray-500 bg-gray-50 rounded-lg border">
                  No monthly data available
                </div>
              </div>
            </div>

            <!-- Daily Sales (Collapsible) - Transposed -->
            <div class="mt-6">
              <div 
                @click="showDailySales = !showDailySales" 
                class="flex items-center justify-between cursor-pointer p-3 bg-gray-50 rounded-lg hover:bg-gray-100"
              >
                <h3 class="font-semibold text-gray-900 flex items-center gap-2">
                  <Activity class="w-4 h-4" />
                  Daily Sales Detail (Last 15 Days)
                </h3>
                <span class="text-gray-500">{{ showDailySales ? '▼' : '▶' }}</span>
              </div>
              <div v-if="showDailySales && transposedDailySales.dates.length" class="mt-4 overflow-x-auto">
                <table class="w-full text-sm">
                  <thead class="bg-gray-50">
                    <tr>
                      <th class="px-3 py-2 text-left sticky left-0 bg-gray-50 z-10 min-w-[90px]">Metric</th>
                      <th 
                        v-for="date in transposedDailySales.dates" 
                        :key="date"
                        class="px-2 py-2 text-right min-w-[70px] text-xs"
                      >
                        {{ formatDateShort(date) }}
                      </th>
                      <th class="px-3 py-2 text-right bg-gray-100 min-w-[90px]">Total/Avg</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr 
                      v-for="row in transposedDailySales.rows" 
                      :key="row.metric" 
                      class="border-b hover:bg-gray-50"
                    >
                      <td class="px-3 py-2 font-medium sticky left-0 bg-white z-10" :class="row.colorClass">
                        {{ row.metric }}
                      </td>
                      <td 
                        v-for="date in transposedDailySales.dates" 
                        :key="date"
                        class="px-2 py-2 text-right text-xs"
                        :class="row.colorClass"
                      >
                        {{ row.isCurrency ? formatCurrency(row.values[date]) : formatNumber(row.values[date]) }}
                      </td>
                      <td class="px-3 py-2 text-right bg-gray-50 font-bold" :class="row.colorClass">
                        {{ row.isCurrency ? formatCurrency(row.total) : formatNumber(row.total) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-else-if="showDailySales" class="mt-4 text-center py-6 text-gray-500 bg-gray-50 rounded-lg border">
                No daily data available
              </div>
            </div>
          </div>

          <!-- Payment Mix Tab -->
          <div v-if="activeTab === 'payment'">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Overall Mix -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4">Overall Payment Mix</h3>
                <div class="flex items-center gap-8">
                  <!-- Donut representation -->
                  <div class="relative w-40 h-40">
                    <svg viewBox="0 0 100 100" class="w-full h-full">
                      <circle
                        cx="50" cy="50" r="40"
                        fill="none"
                        stroke="#e5e7eb"
                        stroke-width="20"
                      />
                      <circle
                        cx="50" cy="50" r="40"
                        fill="none"
                        stroke="#10b981"
                        stroke-width="20"
                        :stroke-dasharray="`${(paymentMix.cash_ratio || 0) * 2.51} 251`"
                        stroke-dashoffset="0"
                        transform="rotate(-90 50 50)"
                      />
                    </svg>
                    <div class="absolute inset-0 flex items-center justify-center flex-col">
                      <p class="text-2xl font-bold text-green-600">{{ formatPercent(paymentMix.cash_ratio) }}</p>
                      <p class="text-xs text-gray-500">Cash</p>
                    </div>
                  </div>
                  
                  <div class="space-y-4">
                    <div class="flex items-center gap-3">
                      <div class="w-4 h-4 bg-green-500 rounded"></div>
                      <div>
                        <p class="font-medium">Cash Sales</p>
                        <p class="text-sm text-gray-500">{{ formatCurrency(paymentMix.cash_total) }}</p>
                      </div>
                    </div>
                    <div class="flex items-center gap-3">
                      <div class="w-4 h-4 bg-gray-300 rounded"></div>
                      <div>
                        <p class="font-medium">Credit Sales</p>
                        <p class="text-sm text-gray-500">{{ formatCurrency(paymentMix.credit_total) }}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Today's Stats -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4">Today's Performance</h3>
                <div class="bg-gradient-to-r from-green-50 to-blue-50 rounded-lg p-6">
                  <div class="flex items-center justify-between mb-4">
                    <p class="text-lg font-medium">Today's Total</p>
                    <p class="text-2xl font-bold">{{ formatCurrency(paymentMix.today_total) }}</p>
                  </div>
                  <div class="flex gap-4">
                    <div class="flex-1 bg-white rounded-lg p-3 text-center">
                      <Banknote class="w-6 h-6 mx-auto text-green-500 mb-1" />
                      <p class="text-lg font-bold text-green-600">{{ formatPercent(paymentMix.today_cash_pct) }}</p>
                      <p class="text-xs text-gray-500">Cash</p>
                    </div>
                    <div class="flex-1 bg-white rounded-lg p-3 text-center">
                      <CreditCard class="w-6 h-6 mx-auto text-blue-500 mb-1" />
                      <p class="text-lg font-bold text-blue-600">{{ formatPercent(100 - (paymentMix.today_cash_pct || 0)) }}</p>
                      <p class="text-xs text-gray-500">Credit</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Daily Mix Trend - Transposed -->
            <div class="mt-6">
              <h3 class="font-semibold text-gray-900 mb-4">Daily Cash Ratio Trend</h3>
              <div v-if="transposedDailyCashRatio.dates.length" class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead class="bg-gray-50">
                    <tr>
                      <th class="px-3 py-2 text-left sticky left-0 bg-gray-50 z-10 min-w-[80px]">Metric</th>
                      <th 
                        v-for="date in transposedDailyCashRatio.dates" 
                        :key="date"
                        class="px-2 py-2 text-right min-w-[75px] text-xs"
                      >
                        {{ formatDateShort(date) }}
                      </th>
                      <th class="px-3 py-2 text-right bg-gray-100 min-w-[90px]">Total/Avg</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr 
                      v-for="row in transposedDailyCashRatio.rows" 
                      :key="row.metric" 
                      class="border-b hover:bg-gray-50"
                    >
                      <td class="px-3 py-2 font-medium sticky left-0 bg-white z-10" :class="row.colorClass">
                        {{ row.metric }}
                      </td>
                      <td 
                        v-for="date in transposedDailyCashRatio.dates" 
                        :key="date"
                        class="px-2 py-2 text-right text-xs"
                        :class="row.colorClass"
                      >
                        <template v-if="row.isPercent">
                          <span class="px-1.5 py-0.5 bg-green-100 text-green-700 rounded text-xs">
                            {{ formatPercent(row.values[date]) }}
                          </span>
                        </template>
                        <template v-else>
                          {{ formatCurrency(row.values[date]) }}
                        </template>
                      </td>
                      <td class="px-3 py-2 text-right bg-gray-50 font-bold" :class="row.colorClass">
                        <template v-if="row.isPercent">
                          <span class="px-2 py-1 bg-green-200 text-green-800 rounded text-xs">
                            {{ formatPercent(row.total) }}
                          </span>
                        </template>
                        <template v-else>
                          {{ formatCurrency(row.total) }}
                        </template>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-else class="text-center py-8 text-gray-500 bg-gray-50 rounded-lg">
                <p>No daily data available</p>
              </div>
            </div>
          </div>

          <!-- Sales Reps Tab -->
          <div v-if="activeTab === 'reps'">
            <div class="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-6">
              <div class="bg-blue-50 rounded-lg p-4">
                <p class="text-sm text-blue-600">Total Sales Reps</p>
                <p class="text-2xl font-bold text-blue-900">{{ salesReps.total_reps }}</p>
              </div>
              <div class="bg-green-50 rounded-lg p-4">
                <p class="text-sm text-green-600">Team Revenue</p>
                <p class="text-2xl font-bold text-green-900">{{ formatCurrency(salesReps.total_team_revenue) }}</p>
              </div>
              <div v-if="salesReps.top_performer" class="bg-purple-50 rounded-lg p-4 lg:col-span-2">
                <p class="text-sm text-purple-600">Top Performer</p>
                <p class="text-xl font-bold text-purple-900">{{ salesReps.top_performer.sales_person_name || salesReps.top_performer.sales_person }}</p>
                <p class="text-sm text-purple-600">{{ formatCurrency(salesReps.top_performer.total_revenue) }} revenue</p>
              </div>
            </div>

            <!-- Rep Leaderboard -->
            <h3 class="font-semibold text-gray-900 mb-4">Sales Rep Leaderboard</h3>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="bg-gray-50">
                  <tr>
                    <th class="px-4 py-2 text-left">Rank</th>
                    <th class="px-4 py-2 text-left">Sales Person</th>
                    <th class="px-4 py-2 text-right">Revenue</th>
                    <th class="px-4 py-2 text-right">Orders</th>
                    <th class="px-4 py-2 text-right">AOV</th>
                    <th class="px-4 py-2 text-right">Customers</th>
                    <th class="px-4 py-2 text-right">Incentives</th>
                  </tr>
                </thead>
                <tbody>
                  <tr 
                    v-for="rep in salesReps.reps" 
                    :key="rep.sales_person" 
                    :class="['border-b hover:bg-gray-50', rep.rank <= 3 ? 'bg-yellow-50' : '']"
                  >
                    <td class="px-4 py-2">
                      <span 
                        :class="[
                          'w-6 h-6 rounded-full inline-flex items-center justify-center text-xs font-bold',
                          rep.rank === 1 ? 'bg-yellow-400 text-yellow-900' :
                          rep.rank === 2 ? 'bg-gray-300 text-gray-700' :
                          rep.rank === 3 ? 'bg-orange-300 text-orange-900' :
                          'bg-gray-100 text-gray-600'
                        ]"
                      >
                        {{ rep.rank }}
                      </span>
                    </td>
                    <td class="px-4 py-2 font-medium" :title="rep.sales_person">{{ rep.sales_person_name || rep.sales_person }}</td>
                    <td class="px-4 py-2 text-right font-bold text-green-600">{{ formatCurrency(rep.total_revenue) }}</td>
                    <td class="px-4 py-2 text-right">{{ rep.total_orders }}</td>
                    <td class="px-4 py-2 text-right">{{ formatCurrency(rep.avg_order_value) }}</td>
                    <td class="px-4 py-2 text-right">{{ rep.unique_customers }}</td>
                    <td class="px-4 py-2 text-right text-purple-600">{{ formatCurrency(rep.total_incentives) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Dimensions Tab -->
          <div v-if="activeTab === 'dimensions'">
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <!-- By Product Group -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4">By Product Group</h3>
                <div class="space-y-2 max-h-80 overflow-y-auto">
                  <div 
                    v-for="pg in dimensions.by_product_group?.slice(0, 15)" 
                    :key="pg.item_group"
                    class="flex items-center gap-2"
                  >
                    <div class="flex-1">
                      <div class="flex justify-between text-sm">
                        <span class="truncate">{{ pg.item_group || 'Uncategorized' }}</span>
                        <span class="text-gray-500">{{ formatPercent(pg.pct) }}</span>
                      </div>
                      <div class="h-2 bg-gray-100 rounded-full mt-1">
                        <div 
                          class="h-full bg-blue-500 rounded-full"
                          :style="{ width: `${pg.pct}%` }"
                        ></div>
                      </div>
                    </div>
                    <span class="text-sm font-medium w-20 text-right">{{ formatCurrency(pg.revenue) }}</span>
                  </div>
                </div>
              </div>

              <!-- By Customer Segment -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4">By Customer Segment</h3>
                <div class="space-y-2 max-h-80 overflow-y-auto">
                  <div 
                    v-for="seg in dimensions.by_customer_segment" 
                    :key="seg.customer_group"
                    class="flex items-center gap-2"
                  >
                    <div class="flex-1">
                      <div class="flex justify-between text-sm">
                        <span class="truncate">{{ seg.customer_group || 'Uncategorized' }}</span>
                        <span class="text-gray-500">{{ formatPercent(seg.pct) }}</span>
                      </div>
                      <div class="h-2 bg-gray-100 rounded-full mt-1">
                        <div 
                          class="h-full bg-green-500 rounded-full"
                          :style="{ width: `${seg.pct}%` }"
                        ></div>
                      </div>
                    </div>
                    <span class="text-sm font-medium w-20 text-right">{{ formatCurrency(seg.revenue) }}</span>
                  </div>
                </div>
              </div>

              <!-- By Territory -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4">By Territory</h3>
                <div class="space-y-2 max-h-80 overflow-y-auto">
                  <div
                    v-for="terr in dimensions.by_territory"
                    :key="terr.territory"
                    class="flex items-center gap-2 cursor-pointer hover:bg-blue-50 rounded transition-colors"
                    @click="drillDown.open(SALES_ENDPOINT, (terr.territory || 'Unknown') + ' Sales', { metric: 'sales_by_territory', territory: terr.territory })"
                  >
                    <div class="flex-1">
                      <div class="flex justify-between text-sm">
                        <span class="truncate">{{ terr.territory || 'Unknown' }}</span>
                        <span class="text-gray-500">{{ formatPercent(terr.pct) }}</span>
                      </div>
                      <div class="h-2 bg-gray-100 rounded-full mt-1">
                        <div 
                          class="h-full bg-purple-500 rounded-full"
                          :style="{ width: `${terr.pct}%` }"
                        ></div>
                      </div>
                    </div>
                    <span class="text-sm font-medium w-20 text-right">{{ formatCurrency(terr.revenue) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Margins Tab -->
          <div v-if="activeTab === 'margins'">
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
              <div class="bg-teal-50 rounded-lg p-4">
                <p class="text-sm text-teal-600">Overall Margin</p>
                <p class="text-3xl font-bold text-teal-900">{{ formatPercent(margins.overall_margin) }}</p>
              </div>
              <div class="bg-green-50 rounded-lg p-4">
                <p class="text-sm text-green-600">Total Revenue</p>
                <p class="text-2xl font-bold text-green-900">{{ formatCurrency(margins.total_revenue) }}</p>
              </div>
              <div class="bg-blue-50 rounded-lg p-4">
                <p class="text-sm text-blue-600">Gross Profit</p>
                <p class="text-2xl font-bold text-blue-900">{{ formatCurrency(margins.total_profit) }}</p>
              </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Margin by Product Group -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4">Margin by Product Group</h3>
                <div class="overflow-x-auto">
                  <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                      <tr>
                        <th class="px-4 py-2 text-left">Product Group</th>
                        <th class="px-4 py-2 text-right">Revenue</th>
                        <th class="px-4 py-2 text-right">Profit</th>
                        <th class="px-4 py-2 text-right">Margin %</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr 
                        v-for="pg in margins.by_product_group?.slice(0, 10)" 
                        :key="pg.item_group" 
                        class="border-b hover:bg-gray-50"
                      >
                        <td class="px-4 py-2">{{ pg.item_group || 'Uncategorized' }}</td>
                        <td class="px-4 py-2 text-right">{{ formatCurrency(pg.revenue) }}</td>
                        <td class="px-4 py-2 text-right text-green-600">{{ formatCurrency(pg.gross_profit) }}</td>
                        <td class="px-4 py-2 text-right">
                          <span 
                            :class="[
                              'px-2 py-1 rounded text-xs font-medium',
                              pg.margin_pct >= 30 ? 'bg-green-100 text-green-700' :
                              pg.margin_pct >= 15 ? 'bg-yellow-100 text-yellow-700' :
                              'bg-red-100 text-red-700'
                            ]"
                          >
                            {{ formatPercent(pg.margin_pct) }}
                          </span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Top/Low Margin Items -->
              <div class="space-y-6">
                <div>
                  <h3 class="font-semibold text-green-600 mb-2">🏆 Top Margin Items</h3>
                  <div class="space-y-2">
                    <div 
                      v-for="item in margins.top_margin_items?.slice(0, 10)" 
                      :key="item.item_code"
                      class="flex justify-between items-center text-sm bg-green-50 rounded p-2"
                    >
                      <span class="truncate flex-1">{{ item.item_code }} - {{ item.item_name }}</span>
                      <span class="font-bold text-green-600 ml-2">{{ formatPercent(item.margin_pct) }}</span>
                    </div>
                  </div>
                </div>
                
                <div>
                  <h3 class="font-semibold text-red-600 mb-2">⚠️ Low Margin Items</h3>
                  <div class="space-y-2">
                    <div 
                      v-for="item in margins.low_margin_items?.slice(0, 10)" 
                      :key="item.item_code"
                      class="flex justify-between items-center text-sm bg-red-50 rounded p-2"
                    >
                      <span class="truncate flex-1">{{ item.item_code }} - {{ item.item_name }}</span>
                      <span class="font-bold text-red-600 ml-2">{{ formatPercent(item.margin_pct) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Forecasts Tab -->
          <div v-if="activeTab === 'forecasts'">
            <!-- Training Controls -->
            <div class="mb-6 bg-gradient-to-r from-indigo-50 to-purple-50 rounded-lg p-4 border border-indigo-200">
              <div class="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 class="font-semibold text-indigo-900 flex items-center gap-2">
                    <Activity class="w-5 h-5" />
                    ML Forecast Training
                  </h3>
                  <p class="text-sm text-indigo-600 mt-1">Train ML models to generate sales forecasts</p>
                </div>
                <div class="flex gap-2">
                  <button 
                    @click="trainForecasts('sales')"
                    :disabled="isTraining"
                    class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2 text-sm font-medium"
                  >
                    <Loader2 v-if="isTraining === 'sales'" class="w-4 h-4 animate-spin" />
                    <TrendingUp v-else class="w-4 h-4" />
                    Train Sales Forecast
                  </button>
                </div>
              </div>
              <p v-if="trainingStatus" class="mt-2 text-sm" :class="trainingStatus.includes('success') ? 'text-green-600' : 'text-red-600'">
                {{ trainingStatus }}
              </p>
            </div>

            <div class="mb-6">
              <!-- Sales Forecast (90 Days) -->
              <div v-if="forecasts.sales_forecast">
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <TrendingUp class="w-5 h-5 text-blue-500" />
                  Sales Forecast (Next 90 Days)
                </h3>
                <div class="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4 mb-4 border border-blue-200">
                  <p class="text-sm text-blue-600">Predicted Total ({{ forecasts.sales_forecast.forecast_summary?.days || 90 }} days)</p>
                  <p class="text-3xl font-bold text-blue-900">
                    {{ formatCurrency(forecasts.sales_forecast.forecast_summary?.total_forecast || 0) }}
                  </p>
                  <p class="text-sm text-blue-600 mt-1">Method: {{ forecasts.sales_forecast.method }}</p>
                </div>
                <div class="text-sm text-gray-500">
                  <p v-if="forecasts.sales_forecast.metrics?.mape">
                    Accuracy (MAPE): {{ formatPercent(100 - (forecasts.sales_forecast.metrics.mape || 0)) }}
                  </p>
                </div>
                <!-- Forecast breakdown -->
                <div v-if="forecasts.sales_forecast.forecast?.length" class="mt-4">
                  <h4 class="text-sm font-medium text-gray-700 mb-2">Monthly Breakdown</h4>
                  <div class="grid grid-cols-3 gap-2">
                    <div class="bg-white rounded-lg p-3 text-center border shadow-sm">
                      <p class="text-xs text-gray-500">Next 30 Days</p>
                      <p class="font-bold text-blue-600 text-lg">{{ formatCurrency(forecasts.sales_forecast.forecast?.slice(0, 30).reduce((a: number, b: any) => a + (b.yhat || 0), 0) || 0) }}</p>
                    </div>
                    <div class="bg-white rounded-lg p-3 text-center border shadow-sm">
                      <p class="text-xs text-gray-500">Days 31-60</p>
                      <p class="font-bold text-blue-600 text-lg">{{ formatCurrency(forecasts.sales_forecast.forecast?.slice(30, 60).reduce((a: number, b: any) => a + (b.yhat || 0), 0) || 0) }}</p>
                    </div>
                    <div class="bg-white rounded-lg p-3 text-center border shadow-sm">
                      <p class="text-xs text-gray-500">Days 61-90</p>
                      <p class="font-bold text-blue-600 text-lg">{{ formatCurrency(forecasts.sales_forecast.forecast?.slice(60, 90).reduce((a: number, b: any) => a + (b.yhat || 0), 0) || 0) }}</p>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="text-center py-8 text-gray-500 bg-gray-50 rounded-lg border">
                <Activity class="w-12 h-12 mx-auto text-gray-400 mb-2" />
                <p class="font-medium">No sales forecast available</p>
                <p class="text-xs">Click "Train Sales Forecast" to generate predictions</p>
              </div>
            </div>

            <!-- Historical + Forecast by Product Group -->
            <div class="mb-6">
              <div class="flex items-center justify-between mb-4">
                <h3 class="font-semibold text-gray-900 flex items-center gap-2">
                  <BarChart3 class="w-5 h-5 text-purple-500" />
                  Sales by Product Group (Historical + Forecast)
                </h3>
                <button 
                  @click="loadDimensionalForecast"
                  :disabled="isLoadingDimensional"
                  class="px-3 py-1.5 text-sm bg-purple-100 text-purple-700 rounded-lg hover:bg-purple-200 flex items-center gap-1"
                >
                  <Loader2 v-if="isLoadingDimensional" class="w-3 h-3 animate-spin" />
                  <RefreshCcw v-else class="w-3 h-3" />
                  Refresh
                </button>
              </div>
              <div v-if="transposedProductGroupData.rows.length" class="overflow-x-auto bg-white rounded-lg border">
                <table class="w-full text-sm">
                  <thead class="bg-purple-50">
                    <tr>
                      <th class="px-4 py-2 text-left sticky left-0 bg-purple-50 z-10 min-w-[180px]">Product Group</th>
                      <th 
                        v-for="period in transposedProductGroupData.periods" 
                        :key="period"
                        :class="[
                          'px-3 py-2 text-right min-w-[90px]',
                          isPeriodForecast(period) ? 'bg-blue-50 text-blue-700' : 'text-gray-700'
                        ]"
                      >
                        <div>{{ formatPeriod(period) }}</div>
                        <div class="text-xs font-normal">{{ isPeriodForecast(period) ? 'Forecast' : 'Actual' }}</div>
                      </th>
                      <th class="px-4 py-2 text-right bg-gray-100 min-w-[100px]">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr 
                      v-for="(row, idx) in paginatedTransposedProductGroups" 
                      :key="idx" 
                      class="border-b hover:bg-gray-50"
                    >
                      <td class="px-4 py-2 font-medium sticky left-0 bg-white z-10 truncate max-w-[180px]" :title="row.product_group">
                        {{ row.product_group }}
                      </td>
                      <td 
                        v-for="period in transposedProductGroupData.periods" 
                        :key="period"
                        :class="[
                          'px-3 py-2 text-right',
                          row.values[period]?.is_forecast ? 'bg-blue-50/50 text-blue-600' : 'text-green-600'
                        ]"
                      >
                        <div class="font-medium">{{ formatCurrency(row.values[period]?.revenue || 0) }}</div>
                        <div class="text-xs text-gray-400">{{ formatNumber(row.values[period]?.transactions || 0) }} txns</div>
                      </td>
                      <td class="px-4 py-2 text-right bg-gray-50 font-bold text-gray-900">
                        <div>{{ formatCurrency(row.total_revenue) }}</div>
                        <div class="text-xs font-normal text-gray-500">{{ formatNumber(row.total_transactions) }} txns</div>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <!-- Pagination -->
                <div class="flex justify-between items-center px-4 py-2 bg-gray-50 border-t">
                  <span class="text-sm text-gray-500">
                    Showing {{ productGroupPage * 15 + 1 }} - {{ Math.min((productGroupPage + 1) * 15, transposedProductGroupData.rows.length) }} 
                    of {{ transposedProductGroupData.rows.length }} product groups
                  </span>
                  <div class="flex gap-2">
                    <button 
                      @click="productGroupPage--" 
                      :disabled="productGroupPage === 0"
                      class="px-3 py-1 text-sm bg-white border rounded hover:bg-gray-50 disabled:opacity-50"
                    >
                      Previous
                    </button>
                    <button 
                      @click="productGroupPage++" 
                      :disabled="(productGroupPage + 1) * 15 >= transposedProductGroupData.rows.length"
                      class="px-3 py-1 text-sm bg-white border rounded hover:bg-gray-50 disabled:opacity-50"
                    >
                      Next
                    </button>
                  </div>
                </div>
              </div>
              <div v-else class="text-center py-8 text-gray-500 bg-gray-50 rounded-lg border">
                <BarChart3 class="w-12 h-12 mx-auto text-gray-400 mb-2" />
                <p>No product group data available</p>
                <p class="text-xs">Click Refresh to load dimensional forecast</p>
              </div>
            </div>

            <!-- Historical + Forecast by Territory -->
            <div>
              <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <Target class="w-5 h-5 text-teal-500" />
                Sales by Territory (Historical + Forecast)
              </h3>
              <div v-if="transposedTerritoryData.rows.length" class="overflow-x-auto bg-white rounded-lg border">
                <table class="w-full text-sm">
                  <thead class="bg-teal-50">
                    <tr>
                      <th class="px-4 py-2 text-left sticky left-0 bg-teal-50 z-10 min-w-[180px]">Territory</th>
                      <th 
                        v-for="period in transposedTerritoryData.periods" 
                        :key="period"
                        :class="[
                          'px-3 py-2 text-right min-w-[90px]',
                          isPeriodForecast(period) ? 'bg-blue-50 text-blue-700' : 'text-gray-700'
                        ]"
                      >
                        <div>{{ formatPeriod(period) }}</div>
                        <div class="text-xs font-normal">{{ isPeriodForecast(period) ? 'Forecast' : 'Actual' }}</div>
                      </th>
                      <th class="px-4 py-2 text-right bg-gray-100 min-w-[100px]">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr 
                      v-for="(row, idx) in paginatedTransposedTerritories" 
                      :key="idx" 
                      class="border-b hover:bg-gray-50"
                    >
                      <td class="px-4 py-2 font-medium sticky left-0 bg-white z-10 truncate max-w-[180px]" :title="row.territory">
                        {{ row.territory }}
                      </td>
                      <td 
                        v-for="period in transposedTerritoryData.periods" 
                        :key="period"
                        :class="[
                          'px-3 py-2 text-right',
                          row.values[period]?.is_forecast ? 'bg-blue-50/50 text-blue-600' : 'text-green-600'
                        ]"
                      >
                        <div class="font-medium">{{ formatCurrency(row.values[period]?.revenue || 0) }}</div>
                        <div class="text-xs text-gray-400">{{ formatNumber(row.values[period]?.transactions || 0) }} txns</div>
                      </td>
                      <td class="px-4 py-2 text-right bg-gray-50 font-bold text-gray-900">
                        <div>{{ formatCurrency(row.total_revenue) }}</div>
                        <div class="text-xs font-normal text-gray-500">{{ formatNumber(row.total_transactions) }} txns</div>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <!-- Pagination -->
                <div class="flex justify-between items-center px-4 py-2 bg-gray-50 border-t">
                  <span class="text-sm text-gray-500">
                    Showing {{ territoryPage * 15 + 1 }} - {{ Math.min((territoryPage + 1) * 15, transposedTerritoryData.rows.length) }} 
                    of {{ transposedTerritoryData.rows.length }} territories
                  </span>
                  <div class="flex gap-2">
                    <button 
                      @click="territoryPage--" 
                      :disabled="territoryPage === 0"
                      class="px-3 py-1 text-sm bg-white border rounded hover:bg-gray-50 disabled:opacity-50"
                    >
                      Previous
                    </button>
                    <button 
                      @click="territoryPage++" 
                      :disabled="(territoryPage + 1) * 15 >= transposedTerritoryData.rows.length"
                      class="px-3 py-1 text-sm bg-white border rounded hover:bg-gray-50 disabled:opacity-50"
                    >
                      Next
                    </button>
                  </div>
                </div>
              </div>
              <div v-else class="text-center py-8 text-gray-500 bg-gray-50 rounded-lg border">
                <Target class="w-12 h-12 mx-auto text-gray-400 mb-2" />
                <p>No territory data available</p>
                <p class="text-xs">Click Refresh above to load dimensional forecast</p>
              </div>
            </div>
          </div>

          <!-- Source Attribution Tab -->
          <div v-if="activeTab === 'sources'" class="space-y-6">
            <!-- Stacked Bar Chart -->
            <div class="bg-white rounded-xl shadow-sm border p-6">
              <h3 class="font-semibold text-gray-900 mb-4">Source Attribution</h3>
              <div v-if="sourceAttribution?.length" class="h-80">
                <BaseChart :options="attributionChartOptions" />
              </div>
              <div v-else class="text-center py-8 text-gray-500">
                <Target class="w-8 h-8 mx-auto mb-2" />
                <p>No source attribution data available</p>
              </div>
            </div>

            <!-- Cost Per Order Cards -->
            <div v-if="sourceAttribution?.length" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              <div v-for="src in sourceAttribution.slice(0, 8)" :key="src.source" class="bg-white rounded-lg shadow-sm border p-4">
                <p class="text-sm text-gray-500 truncate">{{ src.source }}</p>
                <p class="text-xl font-bold text-gray-900">{{ formatCurrency(src.revenue / src.order_count) }}</p>
                <p class="text-xs text-gray-500">per order</p>
              </div>
            </div>

            <!-- Quotation Funnel -->
            <div class="bg-white rounded-xl shadow-sm border p-6">
              <h3 class="font-semibold text-gray-900 mb-4">Quotation Funnel</h3>
              <div v-if="quotationAnalytics" class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div class="bg-blue-50 rounded-lg p-4 text-center">
                  <p class="text-sm text-blue-700 font-medium">Total Quotes</p>
                  <p class="text-2xl font-bold text-blue-900">{{ formatNumber(quotationAnalytics.total) }}</p>
                </div>
                <div class="bg-green-50 rounded-lg p-4 text-center">
                  <p class="text-sm text-green-700 font-medium">Won</p>
                  <p class="text-2xl font-bold text-green-900">{{ formatNumber(quotationAnalytics.won) }}</p>
                </div>
                <div class="bg-red-50 rounded-lg p-4 text-center">
                  <p class="text-sm text-red-700 font-medium">Lost</p>
                  <p class="text-2xl font-bold text-red-900">{{ formatNumber(quotationAnalytics.lost) }}</p>
                </div>
              </div>
              <div v-if="quotationAnalytics?.lost_reasons?.length" class="h-64">
                <BaseChart :options="lostReasonsChartOptions" />
              </div>
              <div v-else-if="quotationAnalytics" class="text-center py-8 text-gray-500">
                <p>No lost reason data available</p>
              </div>
            </div>

            <!-- Territory Performance -->
            <div class="bg-white rounded-xl shadow-sm border p-6">
              <h3 class="font-semibold text-gray-900 mb-4">Territory Performance</h3>
              <div v-if="territoryPerformanceData?.length" class="h-96">
                <TerritoryMap
                  :worldData="territoryPerformanceWorldData"
                  :indiaData="[]"
                  metric="Revenue"
                  colorScale="green"
                />
              </div>
              <div v-else class="text-center py-8 text-gray-500">
                <Target class="w-8 h-8 mx-auto mb-2" />
                <p>No territory performance data available</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- AI Chat Button -->
    <DashboardChatButton
      dashboard-type="Sales"
      :dashboard-context="chatContext"
      @navigate-dashboard="handleDashboardRedirect"
    />

    <IntelligenceDrillDown
      v-model:show="drillDown.show.value"
      :title="drillDown.title.value"
      :columns="drillDown.columns.value"
      :rows="drillDown.rows.value"
      :loading="drillDown.loading.value"
      :error="drillDown.error.value"
      :is-permission-error="drillDown.isPermissionError.value"
      :total="drillDown.total.value"
      :page="drillDown.page.value"
      @next-page="drillDown.nextPage()"
      @prev-page="drillDown.prevPage()"
      @close="drillDown.close()"
      @retry="drillDown.retry()"
    />
  </div>
</template>
