<!-- frontend/src2/dashboard/RevenueSections.vue -->
<!--
  Revenue tab-group content for the merged Revenue & Customers dashboard.
  Receives the sales_intelligence payload from the shell and renders 6 tabs:
  Overview, Cash vs Credit, Sales Reps, Margins, Forecasts, Attribution.
  The TerritoryMap was removed from Attribution — it lives in the Customer
  Geography tab now.
-->
<script setup lang="ts">
import IntelligenceChart from '../intelligence/components/IntelligenceChart.vue'
defineOptions({ name: 'RevenueSections' })
import { Badge, Button } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { confirmDialog } from '../helpers/confirm_dialog'
import {
  TrendingUp, Activity, BarChart3, Calendar, ArrowUpRight, ArrowDownRight,
  Banknote, CreditCard, Target, AlertTriangle, CheckCircle,
} from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { createToast } from '../helpers/toasts'
import { chartPalette, themeColor } from '../utils/chartTheme'
import KpiCard from '../intelligence/components/KpiCard.vue'
import SectionHeader from '../intelligence/components/SectionHeader.vue'
import { severityBadge, scoreSeverity, deltaInk, deltaGlyph } from '../utils/status'
import { formatMoney, formatDateShort, NO_VALUE } from '../utils/format'
import type { DrillDownParams } from '../intelligence/composables/useDrillDown'

const props = defineProps<{
  data: Record<string, unknown>
  activeTab: string
  dateFilter: string
  currency: string | null
  drillDownEndpoint: string
}>()

const emit = defineEmits<{
  (e: 'drill-down', endpoint: string, title: string, params: DrillDownParams): void
}>()

function drillOpen(title: string, params: DrillDownParams) {
  emit('drill-down', props.drillDownEndpoint, title, params)
}

// ── Computed data accessors ────────────────────────────────────────────────
const summary = computed(() => (props.data.summary ?? {}) as Record<string, number>)
const revenueMetrics = computed(() => (props.data.revenue_metrics ?? {}) as Record<string, unknown>)
const paymentMix = computed(() => (props.data.payment_mix ?? {}) as Record<string, unknown>)
const salesReps = computed(() => (props.data.sales_reps ?? {}) as Record<string, unknown>)
const comparisons = computed(() => (props.data.comparisons ?? {}) as Record<string, unknown>)
const dimensions = computed(() => (props.data.dimensions ?? {}) as Record<string, unknown>)
const margins = computed(() => (props.data.margins ?? {}) as Record<string, unknown>)
const fulfillment = computed(() => (props.data.fulfillment ?? {}) as Record<string, unknown>)
const forecasts = computed(() => (props.data.forecasts ?? {}) as Record<string, unknown>)

/**
 * The sales forecast panel, read from the payload rather than assumed.
 *
 * The template hardcoded "Next 90 Days" and three 30-day buckets. The model
 * returns 30 days, so two buckets always rendered zero and the heading was
 * wrong by a factor of three.
 */
interface SalesForecastPayload {
  forecast?: { yhat?: number }[]
  forecast_summary?: { total_forecast?: number; days?: number }
  method?: string
  metrics?: Record<string, number>
}
const salesForecast = computed(
  () => (forecasts.value.sales_forecast ?? null) as SalesForecastPayload | null,
)
const forecastDays = computed(
  () => salesForecast.value?.forecast_summary?.days ?? salesForecast.value?.forecast?.length ?? 0,
)
/** 30-day buckets, but only the ones the horizon actually covers. */
const forecastBuckets = computed(() => {
  const rows = salesForecast.value?.forecast ?? []
  const buckets: { label: string; amount: number }[] = []
  for (let start = 0; start < rows.length; start += 30) {
    const slice = rows.slice(start, start + 30)
    buckets.push({
      label: start === 0 ? `Next ${slice.length} days` : `Days ${start + 1}-${start + slice.length}`,
      amount: slice.reduce((sum, row) => sum + (row.yhat || 0), 0),
    })
  }
  return buckets
})
/**
 * Forecast error, reported as error rather than as "accuracy".
 *
 * This read `100 - mape`. MAPE divides by actuals, so a single zero-sales day
 * sends it past 100 and the panel showed a negative accuracy -- this site
 * measures MAPE 162.7%, which rendered as "-62.7%". sMAPE is bounded and
 * defined at zero, and is what the model health page reports, so the two
 * surfaces now agree.
 */
const forecastError = computed(() => {
  const metrics = salesForecast.value?.metrics
  if (!metrics) return null
  if (typeof metrics.smape === 'number') {
    return { label: 'sMAPE', value: metrics.smape, days: metrics.horizon_days }
  }
  if (typeof metrics.mape === 'number') {
    return { label: 'MAPE', value: metrics.mape, days: metrics.horizon_days }
  }
  return null
})
const fulfillmentSeverity = computed(() =>
  scoreSeverity((fulfillment.value.fulfillment_rate as number) || summary.value.fulfillment_rate, { good: 95, warn: 85 }),
)
const dsoSeverity = computed(() =>
  scoreSeverity((fulfillment.value.dso as number) || (summary.value.dso as number), { good: 30, warn: 60, higherIsBetter: false }),
)

// ── Local format helpers (respect server currency) ────────────────────────
function money(value: number | null | undefined): string {
  return formatMoney(value, props.currency)
}
function pct(value: number | null | undefined): string {
  return `${value?.toFixed(1) ?? 0}%`
}
function num(value: number | null | undefined): string {
  return value?.toLocaleString() ?? '0'
}

// ── State: collapsible daily sales ─────────────────────────────────────────
const showDailySales = ref(false)

// ── State: ML training ────────────────────────────────────────────────────
const isTraining = ref<string | false>(false)
const trainingStatus = ref('')

// ── State: source attribution (lazy) ──────────────────────────────────────
const sourceAttribution = ref<Record<string, unknown>[]>([])
const quotationAnalytics = ref<Record<string, unknown> | null>(null)
const isLoadingSources = ref(false)

// ── State: dimensional forecast (lazy) ────────────────────────────────────
const dimensionalForecast = ref<Record<string, unknown>>({})
const isLoadingDimensional = ref(false)
const productGroupPage = ref(0)
const territoryPage = ref(0)

// ── Chart config: monthly trend ───────────────────────────────────────────
const monthlyTrendConfig = computed(() => {
  const trend = (comparisons.value.monthly_trend as Record<string, unknown>[]) ?? []
  if (!trend.length) return null
  return {
    data: trend.map(m => ({
      period: (m.period as string)?.slice(5) ?? '',
      Revenue: (m.revenue as number) ?? 0,
    })),
    title: '',
    xAxis: { key: 'period', type: 'category' as const },
    yAxis: { title: '' },
    series: [
      { name: 'Revenue', type: 'bar' as const, color: themeColor('--app-accent') },
    ],
  }
})

// ── Train ML models ───────────────────────────────────────────────────────
function trainForecasts(modelType: string) {
  confirmDialog({
    title: 'Train Forecast Model',
    message: `This will retrain the ${modelType} forecast model on a background worker. It takes several minutes; the dashboard updates once it finishes.`,
    primaryActionLabel: 'Train Model',
    onSuccess: async () => {
      isTraining.value = modelType
      trainingStatus.value = ''
      try {
        // The endpoint queues the fit and returns immediately, so report what
        // the server actually said rather than claiming the model is trained.
        const result = (await apiCall('insights.api.ml.train_forecast_models', {
          model_type: modelType,
        })) as Record<string, unknown>
        const message = (result?.message as string) || 'Training started in the background'
        trainingStatus.value = message
        createToast({
          title: 'Training Started',
          message,
          variant: 'success',
        })
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : 'Unknown error'
        trainingStatus.value = `Training error: ${msg}`
        createToast({ title: 'Training Error', message: msg, variant: 'error' })
      } finally {
        isTraining.value = false
      }
    },
  })
}

// ── Lazy loaders ──────────────────────────────────────────────────────────
async function loadDimensionalForecast() {
  isLoadingDimensional.value = true
  try {
    const result = await apiCall('insights.api.ml.get_historical_and_forecast_by_dimension', {
      dimension: 'both',
    })
    dimensionalForecast.value = result as Record<string, unknown>
    productGroupPage.value = 0
    territoryPage.value = 0
  } catch {
    createToast({ title: 'Error', message: 'Failed to load dimensional forecast', variant: 'error' })
  } finally {
    isLoadingDimensional.value = false
  }
}

async function loadSourceAttribution() {
  isLoadingSources.value = true
  try {
    const [attribution, quotation] = await Promise.all([
      apiCall('insights.api.ml.sales.source_attributed_sales', { date_filter: props.dateFilter }),
      apiCall('insights.api.ml.sales.quotation_analytics', { date_filter: props.dateFilter }),
    ])
    sourceAttribution.value = (attribution as Record<string, unknown>[]) || []
    quotationAnalytics.value = quotation as Record<string, unknown>
  } catch (e: unknown) {
    console.error('Error loading source attribution:', e)
  } finally {
    isLoadingSources.value = false
  }
}

// ── Transposed table builders ─────────────────────────────────────────────
interface DimItem {
  period: string
  product_group?: string
  territory?: string
  revenue: number
  transactions: number
  is_forecast: boolean
}
interface DimRow {
  product_group?: string
  territory?: string
  values: Record<string, { revenue: number; transactions: number; is_forecast: boolean }>
  total_revenue: number
  total_transactions: number
}

function buildTransposedDimData(
  rawData: DimItem[],
  keyField: 'product_group' | 'territory',
): { periods: string[]; rows: DimRow[] } {
  if (!rawData.length) return { periods: [], rows: [] }
  const periodsSet = new Set<string>()
  const groupsMap = new Map<string, Map<string, { revenue: number; transactions: number; is_forecast: boolean }>>()
  rawData.forEach(item => {
    periodsSet.add(item.period)
    const key = item[keyField] ?? 'Unknown'
    if (!groupsMap.has(key)) groupsMap.set(key, new Map())
    groupsMap.get(key)!.set(item.period, {
      revenue: item.revenue,
      transactions: item.transactions,
      is_forecast: item.is_forecast,
    })
  })
  const periods = Array.from(periodsSet).sort()
  const rows: DimRow[] = []
  groupsMap.forEach((periodData, groupKey) => {
    let totalRevenue = 0
    let totalTransactions = 0
    const values: DimRow['values'] = {}
    periods.forEach(period => {
      const d = periodData.get(period)
      if (d) {
        values[period] = d
        totalRevenue += d.revenue
        totalTransactions += d.transactions
      } else {
        values[period] = { revenue: 0, transactions: 0, is_forecast: false }
      }
    })
    const row: DimRow = { values, total_revenue: totalRevenue, total_transactions: totalTransactions }
    row[keyField] = groupKey
    rows.push(row)
  })
  rows.sort((a, b) => b.total_revenue - a.total_revenue)
  return { periods, rows }
}

const transposedProductGroupData = computed(() =>
  buildTransposedDimData(
    (dimensionalForecast.value.combined_product_group as DimItem[]) || [],
    'product_group',
  ),
)
const paginatedTransposedProductGroups = computed(() => {
  const start = productGroupPage.value * 15
  return transposedProductGroupData.value.rows.slice(start, start + 15)
})
const transposedTerritoryData = computed(() =>
  buildTransposedDimData(
    (dimensionalForecast.value.combined_territory as DimItem[]) || [],
    'territory',
  ),
)
const paginatedTransposedTerritories = computed(() => {
  const start = territoryPage.value * 15
  return transposedTerritoryData.value.rows.slice(start, start + 15)
})

interface TransposedRow {
  metric: string
  values: Record<string, number>
  total: number
  colorClass: string
  isCurrency?: boolean
  isPercent?: boolean
}

// ── Daily cash ratio transposed table ─────────────────────────────────────
interface DailyMixItem {
  sale_date: string
  Cash?: number
  Credit?: number
  total?: number
  cash_pct?: number
}
const transposedDailyCashRatio = computed(() => {
  const dailyMix = (paymentMix.value.daily_mix as DailyMixItem[]) || []
  if (!dailyMix.length) return { dates: [] as string[], rows: [] as TransposedRow[] }
  const recentDays = dailyMix.slice(0, 15).reverse()
  const dates = recentDays.map(d => d.sale_date)
  const rows = [
    {
      metric: 'Cash',
      values: recentDays.reduce((acc, d) => { acc[d.sale_date] = d.Cash ?? 0; return acc }, {} as Record<string, number>),
      total: recentDays.reduce((sum, d) => sum + (d.Cash ?? 0), 0),
      colorClass: 'text-ink-gray-8',
    },
    {
      metric: 'Credit',
      values: recentDays.reduce((acc, d) => { acc[d.sale_date] = d.Credit ?? 0; return acc }, {} as Record<string, number>),
      total: recentDays.reduce((sum, d) => sum + (d.Credit ?? 0), 0),
      colorClass: 'text-ink-gray-7',
    },
    {
      metric: 'Total',
      values: recentDays.reduce((acc, d) => { acc[d.sale_date] = d.total ?? 0; return acc }, {} as Record<string, number>),
      total: recentDays.reduce((sum, d) => sum + (d.total ?? 0), 0),
      colorClass: 'text-ink-gray-9 font-bold',
    },
    {
      metric: 'Cash %',
      values: recentDays.reduce((acc, d) => { acc[d.sale_date] = d.cash_pct ?? 0; return acc }, {} as Record<string, number>),
      total: recentDays.length > 0 ? recentDays.reduce((sum, d) => sum + (d.cash_pct ?? 0), 0) / recentDays.length : 0,
      colorClass: 'text-ink-gray-8',
      isPercent: true,
    },
  ]
  return { dates, rows }
})

// ── Weekly performance transposed table ───────────────────────────────────
interface WeeklySalesItem { week: number; year: number; revenue?: number; transactions?: number }
const transposedWeeklyPerformance = computed(() => {
  const weeklyData = (revenueMetrics.value.weekly_sales as WeeklySalesItem[]) || []
  if (!weeklyData.length) return { weeks: [] as { label: string; year: number; week: number }[], rows: [] as TransposedRow[] }
  const recentWeeks = weeklyData.slice(-8)
  const weeks = recentWeeks.map(w => ({ label: `W${w.week}`, year: w.year, week: w.week }))
  const rows = [
    {
      metric: 'Revenue',
      values: recentWeeks.reduce((acc, w) => { acc[`W${w.week}`] = w.revenue ?? 0; return acc }, {} as Record<string, number>),
      total: recentWeeks.reduce((sum, w) => sum + (w.revenue ?? 0), 0),
      colorClass: 'text-ink-gray-9 font-bold',
      isCurrency: true,
    },
    {
      metric: 'Orders',
      values: recentWeeks.reduce((acc, w) => { acc[`W${w.week}`] = w.transactions ?? 0; return acc }, {} as Record<string, number>),
      total: recentWeeks.reduce((sum, w) => sum + (w.transactions ?? 0), 0),
      colorClass: 'text-ink-gray-7',
      isCurrency: false,
    },
    {
      metric: 'AOV',
      values: recentWeeks.reduce((acc, w) => {
        acc[`W${w.week}`] = (w.transactions ?? 0) > 0 ? (w.revenue ?? 0) / (w.transactions ?? 1) : 0
        return acc
      }, {} as Record<string, number>),
      total: recentWeeks.reduce((sum, w) => sum + (w.revenue ?? 0), 0) / Math.max(1, recentWeeks.reduce((sum, w) => sum + (w.transactions ?? 0), 0)),
      colorClass: 'text-ink-gray-8',
      isCurrency: true,
    },
  ]
  return { weeks, rows }
})

// ── Monthly summary transposed table ──────────────────────────────────────
interface MonthlySalesItem { period: string; revenue?: number; transactions?: number; unique_customers?: number }
const transposedMonthlySummary = computed(() => {
  const monthlyData = (revenueMetrics.value.monthly_sales as MonthlySalesItem[]) || []
  if (!monthlyData.length) return { months: [] as string[], rows: [] as TransposedRow[] }
  const recentMonths = monthlyData.slice(-6)
  const months = recentMonths.map(m => m.period)
  const rows = [
    {
      metric: 'Revenue',
      values: recentMonths.reduce((acc, m) => { acc[m.period] = m.revenue ?? 0; return acc }, {} as Record<string, number>),
      total: recentMonths.reduce((sum, m) => sum + (m.revenue ?? 0), 0),
      colorClass: 'text-ink-gray-9 font-bold',
      isCurrency: true,
    },
    {
      metric: 'Orders',
      values: recentMonths.reduce((acc, m) => { acc[m.period] = m.transactions ?? 0; return acc }, {} as Record<string, number>),
      total: recentMonths.reduce((sum, m) => sum + (m.transactions ?? 0), 0),
      colorClass: 'text-ink-gray-7',
      isCurrency: false,
    },
    {
      metric: 'Customers',
      values: recentMonths.reduce((acc, m) => { acc[m.period] = m.unique_customers ?? 0; return acc }, {} as Record<string, number>),
      total: recentMonths.reduce((sum, m) => sum + (m.unique_customers ?? 0), 0),
      colorClass: 'text-ink-gray-8',
      isCurrency: false,
    },
  ]
  return { months, rows }
})

// ── Daily sales transposed table ──────────────────────────────────────────
interface DailySalesItem { date: string; revenue?: number; transactions?: number }
const transposedDailySales = computed(() => {
  const dailyData = (revenueMetrics.value.daily_sales as DailySalesItem[]) || []
  if (!dailyData.length) return { dates: [] as string[], rows: [] as TransposedRow[] }
  const recentDays = dailyData.slice(0, 15).reverse()
  const dates = recentDays.map(d => d.date)
  const rows = [
    {
      metric: 'Revenue',
      values: recentDays.reduce((acc, d) => { acc[d.date] = d.revenue ?? 0; return acc }, {} as Record<string, number>),
      total: recentDays.reduce((sum, d) => sum + (d.revenue ?? 0), 0),
      colorClass: 'text-ink-gray-9 font-bold',
      isCurrency: true,
    },
    {
      metric: 'Transactions',
      values: recentDays.reduce((acc, d) => { acc[d.date] = d.transactions ?? 0; return acc }, {} as Record<string, number>),
      total: recentDays.reduce((sum, d) => sum + (d.transactions ?? 0), 0),
      colorClass: 'text-ink-gray-7',
      isCurrency: false,
    },
    {
      metric: 'Avg Order',
      values: recentDays.reduce((acc, d) => {
        acc[d.date] = (d.transactions ?? 0) > 0 ? (d.revenue ?? 0) / (d.transactions ?? 1) : 0
        return acc
      }, {} as Record<string, number>),
      total: recentDays.reduce((sum, d) => sum + (d.revenue ?? 0), 0) / Math.max(1, recentDays.reduce((sum, d) => sum + (d.transactions ?? 0), 0)),
      colorClass: 'text-ink-gray-8',
      isCurrency: true,
    },
  ]
  return { dates, rows }
})

// ── Format helpers ─────────────────────────────────────────────────────────
function formatPeriod(period: string): string {
  const [year, month] = period.split('-')
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${monthNames[parseInt(month) - 1]} ${year.slice(2)}`
}
function isPeriodForecast(period: string): boolean {
  const now = new Date()
  const currentPeriod = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  return period > currentPeriod
}

// ── Attribution chart configs ─────────────────────────────────────────────
const attributionConfig = computed(() => {
  const d = sourceAttribution.value.slice(0, 10)
  if (!d.length) return null
  const palette = chartPalette(3)
  return {
    data: d.map(x => ({
      source: x.source as string,
      Revenue: x.revenue as number,
      Profit: x.gross_profit as number,
      Orders: x.order_count as number,
    })),
    title: '',
    xAxis: { key: 'source', type: 'category' as const },
    yAxis: { title: 'Amount' },
    y2Axis: { title: 'Orders' },
    series: [
      { name: 'Revenue', type: 'bar' as const, color: palette[0] },
      { name: 'Profit', type: 'bar' as const, color: palette[1] },
      { name: 'Orders', type: 'bar' as const, color: palette[2], axis: 'y2' as const },
    ],
  }
})
const lostReasonsConfig = computed(() => {
  const reasons = (quotationAnalytics.value?.lost_reasons as Record<string, unknown>[]) ?? []
  if (!reasons.length) return null
  return {
    data: reasons.map(r => ({
      reason: r.order_lost_reason as string,
      count: r.count as number,
    })),
    title: '',
    categoryColumn: 'reason',
    valueColumn: 'count',
  }
})

// ── Lazy-load on tab activation ───────────────────────────────────────────
watch(() => props.activeTab, (tab) => {
  if (tab === 'rev-forecasts') loadDimensionalForecast()
  if (tab === 'rev-sources') loadSourceAttribution()
})
watch(() => props.dateFilter, () => {
  loadDimensionalForecast()
  loadSourceAttribution()
})

onMounted(() => {
  loadDimensionalForecast()
  loadSourceAttribution()
})
</script>

<template>
  <!-- ═══ Revenue Overview ═══ -->
  <div v-if="activeTab === 'rev-overview'">
    <dl class="mb-6 grid grid-cols-2 gap-x-6 gap-y-4 rounded-lg border border-outline-gray-1 bg-card p-4 sm:grid-cols-4">
      <div class="min-w-0">
        <dt class="text-sm text-ink-gray-6">Unique Customers</dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">{{ num((revenueMetrics.unique_customers as number) || summary.unique_customers) }}</dd>
      </div>
      <div class="min-w-0">
        <dt class="text-sm text-ink-gray-6">Avg Days Between Orders</dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">{{ revenueMetrics.avg_days_between_orders ?? '-' }}</dd>
      </div>
      <div class="min-w-0">
        <dt class="flex items-center gap-2 text-sm text-ink-gray-6">
          Fulfillment Rate
          <Badge v-if="fulfillmentSeverity !== 'none'" v-bind="severityBadge(fulfillmentSeverity)" size="sm" />
        </dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">{{ pct((fulfillment.fulfillment_rate as number) || summary.fulfillment_rate) }}</dd>
      </div>
      <div class="min-w-0">
        <dt class="flex items-center gap-2 text-sm text-ink-gray-6">
          Days Sales Outstanding
          <Badge v-if="dsoSeverity !== 'none'" v-bind="severityBadge(dsoSeverity)" size="sm" />
        </dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">{{ `${(fulfillment.dso as number)?.toFixed(0) || (summary.dso as number)?.toFixed(0) || '-'} days` }}</dd>
      </div>
    </dl>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Period Comparison -->
      <div class="lg:col-span-1 space-y-4">
        <SectionHeader variant="caption" title="Period Comparison" :level="3">
          <template #actions><Calendar class="w-4 h-4 text-ink-gray-6" aria-hidden="true" /></template>
        </SectionHeader>
        <div class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-1 bg-card">
          <div class="p-4">
            <div class="flex justify-between items-start">
              <div>
                <p class="text-sm text-ink-gray-6 font-medium">Current month</p>
                <p class="text-2xl font-bold text-ink-gray-9">
                  {{ money((comparisons.current_month as Record<string, number>)?.revenue ?? 0) }}
                </p>
              </div>
              <span class="text-xs text-ink-gray-6">{{ (comparisons.current_month as Record<string, string>)?.period }}</span>
            </div>
            <div class="flex gap-4 mt-2 text-sm text-ink-gray-6">
              <span>{{ num((comparisons.current_month as Record<string, number>)?.transactions ?? 0) }} orders</span>
              <span>AOV: {{ money((comparisons.current_month as Record<string, number>)?.aov ?? 0) }}</span>
            </div>
          </div>
          <div class="p-4">
            <div class="flex justify-between items-center">
              <p class="text-sm text-ink-gray-6 font-medium">Previous month</p>
              <span :class="['text-sm font-bold', deltaInk(comparisons.mom_growth as number)]">
                {{ deltaGlyph(comparisons.mom_growth as number) }}
                {{ Math.abs((comparisons.mom_growth as number) || 0).toFixed(1) }}%
              </span>
            </div>
            <p class="text-lg font-semibold text-ink-gray-9 mt-1">
              {{ money((comparisons.last_month as Record<string, number>)?.revenue ?? 0) }}
            </p>
            <p class="text-xs text-ink-gray-6 mt-0.5">
              {{ num((comparisons.last_month as Record<string, number>)?.transactions ?? 0) }} transactions
            </p>
          </div>
          <div class="p-4">
            <div class="flex justify-between items-center">
              <p class="text-sm text-ink-gray-6 font-medium">Same month last year</p>
              <span :class="['text-sm font-bold', deltaInk(comparisons.yoy_growth as number)]">
                {{ deltaGlyph(comparisons.yoy_growth as number) }}
                {{ Math.abs((comparisons.yoy_growth as number) || 0).toFixed(1) }}%
              </span>
            </div>
            <p class="text-lg font-semibold text-ink-gray-9 mt-1">
              {{ money((comparisons.last_year_same_month as Record<string, number>)?.revenue ?? 0) }}
            </p>
            <p class="text-xs text-ink-gray-6 mt-0.5">
              {{ num((comparisons.last_year_same_month as Record<string, number>)?.transactions ?? 0) }} transactions
            </p>
          </div>
        </div>
      </div>

      <!-- Monthly Revenue Trend -->
      <div class="lg:col-span-2">
        <SectionHeader variant="caption" title="Monthly Revenue Trend" :level="3">
          <template #actions><TrendingUp class="w-4 h-4 text-ink-gray-6" aria-hidden="true" /></template>
        </SectionHeader>
        <div class="mt-4 bg-surface-gray-1 rounded-lg p-4 border border-outline-gray-1">
          <IntelligenceChart v-if="monthlyTrendConfig" :config="monthlyTrendConfig" class="h-56" />
          <div v-else class="h-56 flex items-center justify-center text-ink-gray-6">No trend data</div>
        </div>
        <table v-if="monthlyTrendConfig" class="sr-only">
          <caption>Monthly revenue trend</caption>
          <thead><tr><th scope="col">Period</th><th scope="col">Revenue</th></tr></thead>
          <tbody>
            <tr v-for="m in (comparisons.monthly_trend as Record<string, unknown>[])" :key="m.period as string">
              <th scope="row">{{ m.period }}</th>
              <td>{{ money(m.revenue as number) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Daily Sales (collapsible) -->
    <div class="mt-6">
      <Button
        variant="ghost" theme="gray"
        class="w-full justify-between p-3 bg-surface-gray-1 rounded-lg hover:bg-surface-gray-2 h-auto text-left"
        :aria-expanded="showDailySales"
        @click="showDailySales = !showDailySales"
      >
        <span class="font-semibold text-ink-gray-8 flex items-center gap-2">
          <Activity class="w-4 h-4" aria-hidden="true" />
          Daily Sales Detail (Last 15 Days)
        </span>
        <span class="text-ink-gray-6" aria-hidden="true">{{ showDailySales ? '▼' : '▶' }}</span>
      </Button>
      <div v-if="showDailySales && transposedDailySales.dates.length" class="mt-4 overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-3 py-2 text-left sticky left-0 bg-surface-gray-1 z-10 min-w-[90px] text-ink-gray-7">Metric</th>
              <th v-for="date in transposedDailySales.dates" :key="date" scope="col" class="px-2 py-2 text-right min-w-[70px] text-xs text-ink-gray-7">{{ formatDateShort(date) }}</th>
              <th scope="col" class="px-3 py-2 text-right bg-surface-gray-2 min-w-[90px] text-ink-gray-7">Total/Avg</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in transposedDailySales.rows" :key="row.metric" class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
              <td class="px-3 py-2 font-medium sticky left-0 bg-surface-white z-10" :class="row.colorClass">{{ row.metric }}</td>
              <td v-for="date in transposedDailySales.dates" :key="date" class="px-2 py-2 text-right text-xs" :class="row.colorClass">
                {{ row.isCurrency ? money(row.values[date]) : num(row.values[date]) }}
              </td>
              <td class="px-3 py-2 text-right bg-surface-gray-1 font-bold" :class="row.colorClass">
                {{ row.isCurrency ? money(row.total) : num(row.total) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="showDailySales" class="mt-4 text-center py-6 text-ink-gray-6 bg-surface-gray-1 rounded-lg border border-outline-gray-1">No daily data available</div>
    </div>

    <!-- Weekly Performance -->
    <div class="mt-6">
      <SectionHeader variant="caption" title="Weekly Performance" :level="3">
        <template #actions><BarChart3 class="w-4 h-4 text-ink-gray-6" aria-hidden="true" /></template>
      </SectionHeader>
      <div v-if="transposedWeeklyPerformance.weeks.length" class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-3 py-2 text-left sticky left-0 bg-surface-gray-1 z-10 min-w-[80px] text-ink-gray-7">Metric</th>
              <th v-for="week in transposedWeeklyPerformance.weeks" :key="week.label" scope="col" class="px-2 py-2 text-right min-w-[70px] text-xs text-ink-gray-7">{{ week.label }}</th>
              <th scope="col" class="px-3 py-2 text-right bg-surface-gray-2 min-w-[85px] text-ink-gray-7">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in transposedWeeklyPerformance.rows" :key="row.metric" class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
              <td class="px-3 py-2 font-medium sticky left-0 bg-surface-white z-10" :class="row.colorClass">{{ row.metric }}</td>
              <td v-for="week in transposedWeeklyPerformance.weeks" :key="week.label" class="px-2 py-2 text-right text-xs" :class="row.colorClass">
                {{ row.isCurrency ? money(row.values[week.label]) : num(row.values[week.label]) }}
              </td>
              <td class="px-3 py-2 text-right bg-surface-gray-1 font-bold" :class="row.colorClass">
                {{ row.isCurrency ? money(row.total) : num(row.total) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="mt-4 text-center py-6 text-ink-gray-6 bg-surface-gray-1 rounded-lg border border-outline-gray-1">No weekly data available</div>
    </div>

    <!-- Monthly Summary -->
    <div class="mt-6">
      <SectionHeader variant="caption" title="Monthly Summary" :level="3">
        <template #actions><Calendar class="w-4 h-4 text-ink-gray-6" aria-hidden="true" /></template>
      </SectionHeader>
      <div v-if="transposedMonthlySummary.months.length" class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-3 py-2 text-left sticky left-0 bg-surface-gray-1 z-10 min-w-[80px] text-ink-gray-7">Metric</th>
              <th v-for="month in transposedMonthlySummary.months" :key="month" scope="col" class="px-2 py-2 text-right min-w-[70px] text-xs text-ink-gray-7">{{ formatPeriod(month) }}</th>
              <th scope="col" class="px-3 py-2 text-right bg-surface-gray-2 min-w-[85px] text-ink-gray-7">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in transposedMonthlySummary.rows" :key="row.metric" class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
              <td class="px-3 py-2 font-medium sticky left-0 bg-surface-white z-10" :class="row.colorClass">{{ row.metric }}</td>
              <td v-for="month in transposedMonthlySummary.months" :key="month" class="px-2 py-2 text-right text-xs" :class="row.colorClass">
                {{ row.isCurrency ? money(row.values[month]) : num(row.values[month]) }}
              </td>
              <td class="px-3 py-2 text-right bg-surface-gray-1 font-bold" :class="row.colorClass">
                {{ row.isCurrency ? money(row.total) : num(row.total) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="mt-4 text-center py-6 text-ink-gray-6 bg-surface-gray-1 rounded-lg border border-outline-gray-1">No monthly data available</div>
    </div>
  </div>

  <!-- ═══ Cash vs Credit ═══ -->
  <div v-if="activeTab === 'rev-payment'">
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div>
        <SectionHeader variant="caption" title="Overall Payment Mix" :level="3" />
        <div class="mt-4 flex items-center gap-8">
          <div class="relative w-40 h-40" role="img" :aria-label="`Cash ratio: ${pct(paymentMix.cash_ratio as number)}`">
            <!--
              The two arcs are categories, not statuses: the filled arc is Cash
              and the track is the Credit remainder, so they must equal the
              legend swatches below (`bg-surface-green-3` / `bg-surface-gray-4`).
              They previously used raw `#10b981` (emerald-500, which is not even
              in the Espresso palette) and `#e5e7eb`, so they mismatched their
              own legend AND stayed light-mode fixed under `data-theme="dark"`.
              `lint:palette` did not catch it because that gate greps Tailwind
              class names, not SVG presentation attributes.
            -->
            <svg viewBox="0 0 100 100" class="w-full h-full">
              <circle cx="50" cy="50" r="40" fill="none" stroke="var(--surface-gray-4)" stroke-width="20" />
              <circle cx="50" cy="50" r="40" fill="none" stroke="var(--surface-green-3)" stroke-width="20"
                :stroke-dasharray="`${((paymentMix.cash_ratio as number) || 0) * 2.51} 251`"
                stroke-dashoffset="0" transform="rotate(-90 50 50)" />
            </svg>
            <div class="absolute inset-0 flex items-center justify-center flex-col">
              <p class="text-2xl font-bold text-ink-gray-9">{{ pct(paymentMix.cash_ratio as number) }}</p>
              <p class="text-xs text-ink-gray-6">Cash</p>
            </div>
          </div>
          <div class="space-y-4">
            <div class="flex items-center gap-3">
              <div class="w-4 h-4 bg-surface-green-3 rounded" aria-hidden="true" />
              <div>
                <p class="font-medium text-ink-gray-8">Cash Sales</p>
                <p class="text-sm text-ink-gray-6">{{ money(paymentMix.cash_total as number) }}</p>
              </div>
            </div>
            <div class="flex items-center gap-3">
              <div class="w-4 h-4 bg-surface-gray-4 rounded" aria-hidden="true" />
              <div>
                <p class="font-medium text-ink-gray-8">Credit Sales</p>
                <p class="text-sm text-ink-gray-6">{{ money(paymentMix.credit_total as number) }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div>
        <SectionHeader variant="caption" title="Today's Performance" :level="3" />
        <div class="mt-4 bg-surface-gray-1 rounded-lg p-6 border border-outline-gray-1">
          <div class="flex items-center justify-between mb-4">
            <p class="text-lg font-medium text-ink-gray-8">Today's Total</p>
            <p class="text-2xl font-bold text-ink-gray-9">{{ money(paymentMix.today_total as number) }}</p>
          </div>
          <div class="flex gap-4">
            <div class="flex-1 bg-surface-white rounded-lg p-3 text-center border border-outline-gray-1">
              <Banknote class="w-6 h-6 mx-auto text-ink-gray-6 mb-1" aria-hidden="true" />
              <p class="text-lg font-bold text-ink-gray-9">{{ pct(paymentMix.today_cash_pct as number) }}</p>
              <p class="text-xs text-ink-gray-6">Cash</p>
            </div>
            <div class="flex-1 bg-surface-white rounded-lg p-3 text-center border border-outline-gray-1">
              <CreditCard class="w-6 h-6 mx-auto text-ink-gray-6 mb-1" aria-hidden="true" />
              <p class="text-lg font-bold text-ink-gray-9">{{ pct(100 - ((paymentMix.today_cash_pct as number) || 0)) }}</p>
              <p class="text-xs text-ink-gray-6">Credit</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-6">
      <SectionHeader variant="caption" title="Daily Cash Ratio Trend" :level="3" />
      <div v-if="transposedDailyCashRatio.dates.length" class="mt-4 overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-3 py-2 text-left sticky left-0 bg-surface-gray-1 z-10 min-w-[80px] text-ink-gray-7">Metric</th>
              <th v-for="date in transposedDailyCashRatio.dates" :key="date" scope="col" class="px-2 py-2 text-right min-w-[75px] text-xs text-ink-gray-7">{{ formatDateShort(date) }}</th>
              <th scope="col" class="px-3 py-2 text-right bg-surface-gray-2 min-w-[90px] text-ink-gray-7">Total/Avg</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in transposedDailyCashRatio.rows" :key="row.metric" class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
              <td class="px-3 py-2 font-medium sticky left-0 bg-surface-white z-10" :class="row.colorClass">{{ row.metric }}</td>
              <td v-for="date in transposedDailyCashRatio.dates" :key="date" class="px-2 py-2 text-right text-xs" :class="row.colorClass">
                {{ row.isPercent ? pct(row.values[date]) : money(row.values[date]) }}
              </td>
              <td class="px-3 py-2 text-right bg-surface-gray-1 font-bold" :class="row.colorClass">
                {{ row.isPercent ? pct(row.total) : money(row.total) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="mt-4 text-center py-8 text-ink-gray-6 bg-surface-gray-1 rounded-lg border border-outline-gray-1">No daily data available</div>
    </div>
  </div>

  <!-- ═══ Sales Reps ═══ -->
  <div v-if="activeTab === 'rev-reps'">
    <div class="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-6">
      <KpiCard label="Total Sales Reps" :value="String(salesReps.total_reps ?? 0)" />
      <KpiCard label="Team Revenue" :value="money(salesReps.total_team_revenue as number)" />
      <div v-if="salesReps.top_performer" class="lg:col-span-2 bg-surface-gray-1 rounded-lg p-4 border border-outline-gray-1">
        <p class="text-sm text-ink-gray-6">Top Performer</p>
        <p class="text-xl font-bold text-ink-gray-9">
          {{ (salesReps.top_performer as Record<string, string>).sales_person_name || (salesReps.top_performer as Record<string, string>).sales_person }}
        </p>
        <p class="text-sm text-ink-gray-6">
          {{ money((salesReps.top_performer as Record<string, number>).total_revenue) }} revenue
        </p>
      </div>
    </div>

    <SectionHeader variant="caption" title="Sales Rep Leaderboard" :level="3" />
    <div class="mt-4 overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-surface-gray-1">
          <tr>
            <th scope="col" class="px-4 py-2 text-left text-ink-gray-7">Rank</th>
            <th scope="col" class="px-4 py-2 text-left text-ink-gray-7">Sales Person</th>
            <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Revenue</th>
            <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Orders</th>
            <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">AOV</th>
            <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Customers</th>
            <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Incentives</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="rep in (salesReps.reps as Record<string, unknown>[])" :key="rep.sales_person as string"
            :class="['border-b border-outline-gray-1 hover:bg-surface-gray-1', (rep.rank as number) <= 3 ? 'bg-surface-gray-1' : '']">
            <td class="px-4 py-2">
              <span :class="[
                'w-6 h-6 rounded-full inline-flex items-center justify-center text-xs font-bold',
                rep.rank === 1 ? 'bg-surface-amber-3 text-ink-gray-9' :
                rep.rank === 2 ? 'bg-surface-gray-3 text-ink-gray-7' :
                rep.rank === 3 ? 'bg-surface-gray-4 text-ink-gray-7' :
                'bg-surface-gray-2 text-ink-gray-6'
              ]" :aria-label="`Rank ${rep.rank}`">{{ rep.rank }}</span>
            </td>
            <td class="px-4 py-2 font-medium text-ink-gray-8" :title="rep.sales_person as string">
              {{ (rep.sales_person_name as string) || (rep.sales_person as string) }}
            </td>
            <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ money(rep.total_revenue as number) }}</td>
            <td class="px-4 py-2 text-right text-ink-gray-7">{{ rep.total_orders }}</td>
            <td class="px-4 py-2 text-right text-ink-gray-7">{{ money(rep.avg_order_value as number) }}</td>
            <td class="px-4 py-2 text-right text-ink-gray-7">{{ rep.unique_customers }}</td>
            <td class="px-4 py-2 text-right text-ink-gray-7">{{ money(rep.total_incentives as number) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- ═══ Margins ═══ -->
  <div v-if="activeTab === 'rev-margins'">
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
      <KpiCard label="Overall Margin" :value="pct(margins.overall_margin as number)" />
      <KpiCard label="Total Revenue" :value="money(margins.total_revenue as number)" />
      <KpiCard label="Gross Profit" :value="money(margins.total_profit as number)" />
    </div>
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div>
        <SectionHeader variant="caption" title="Margin by Product Group" :level="3" />
        <div class="mt-4 overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-surface-gray-1">
              <tr>
                <th scope="col" class="px-4 py-2 text-left text-ink-gray-7">Product Group</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Revenue</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Profit</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Margin %</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="pg in (margins.by_product_group as Record<string, unknown>[])?.slice(0, 10)" :key="pg.item_group as string"
                class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
                <td class="px-4 py-2 text-ink-gray-8">{{ pg.item_group || 'Uncategorized' }}</td>
                <td class="px-4 py-2 text-right text-ink-gray-8">{{ money(pg.revenue as number) }}</td>
                <td class="px-4 py-2 text-right text-ink-gray-7">{{ money(pg.gross_profit as number) }}</td>
                <td class="px-4 py-2 text-right">
                  <Badge v-bind="severityBadge(scoreSeverity(pg.margin_pct as number, { good: 30, warn: 15 }))" :label="pct(pg.margin_pct as number)" size="sm" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="space-y-6">
        <div>
          <SectionHeader variant="caption" title="Top Margin Items" :level="3" />
          <div class="mt-2 space-y-2">
            <div v-for="item in (margins.top_margin_items as Record<string, unknown>[])?.slice(0, 10)" :key="item.item_code as string"
              class="flex justify-between items-center text-sm bg-surface-gray-1 rounded p-2">
              <span class="truncate flex-1 text-ink-gray-8">{{ item.item_code }} - {{ item.item_name }}</span>
              <span class="font-bold text-ink-gray-9 ml-2">{{ pct(item.margin_pct as number) }}</span>
            </div>
          </div>
        </div>
        <div>
          <SectionHeader variant="caption" title="Low Margin Items" :level="3" />
          <div class="mt-2 space-y-2">
            <div v-for="item in (margins.low_margin_items as Record<string, unknown>[])?.slice(0, 10)" :key="item.item_code as string"
              class="flex justify-between items-center text-sm bg-surface-gray-1 rounded p-2">
              <span class="truncate flex-1 text-ink-gray-8">{{ item.item_code }} - {{ item.item_name }}</span>
              <Badge v-bind="severityBadge(scoreSeverity(item.margin_pct as number, { good: 30, warn: 15 }))" :label="pct(item.margin_pct as number)" size="sm" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ Forecasts ═══ -->
  <div v-if="activeTab === 'rev-forecasts'">
    <div class="mb-6 bg-surface-gray-1 rounded-lg p-4 border border-outline-gray-1">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <SectionHeader variant="caption" title="ML Forecast Training" hint="Train models to generate sales forecasts" :level="3" />
        <div class="flex gap-2">
          <Button variant="solid" theme="gray" :loading="isTraining === 'sales'" :disabled="!!isTraining" @click="trainForecasts('sales')">
            Train Sales Forecast
          </Button>
        </div>
      </div>
      <p v-if="trainingStatus" class="mt-2 text-sm" :class="trainingStatus.includes('successfully') ? 'text-ink-gray-8' : 'text-ink-red-4'">{{ trainingStatus }}</p>
    </div>

    <div class="mb-6">
      <div v-if="salesForecast">
        <SectionHeader
          variant="caption"
          :title="`Sales Forecast (Next ${forecastDays} Days)`"
          :level="3"
        >
          <template #actions><TrendingUp class="w-5 h-5 text-ink-gray-6" aria-hidden="true" /></template>
        </SectionHeader>
        <div class="mt-4 bg-surface-gray-1 rounded-lg p-4 mb-4 border border-outline-gray-1">
          <p class="text-sm text-ink-gray-6">Predicted Total ({{ forecastDays }} days)</p>
          <p class="text-3xl font-bold text-ink-gray-9">
            {{ money(salesForecast.forecast_summary?.total_forecast || 0) }}
          </p>
          <p class="text-sm text-ink-gray-6 mt-1">Method: {{ salesForecast.method || '—' }}</p>
        </div>
        <p v-if="forecastError" class="text-sm text-ink-gray-6">
          Forecast error ({{ forecastError.label }}): {{ pct(forecastError.value) }}
          <span v-if="forecastError.days" class="text-ink-gray-5">
            · measured on a {{ forecastError.days }}-day held-out tail
          </span>
        </p>
        <div v-if="forecastBuckets.length" class="mt-4">
          <h4 class="text-sm font-medium text-ink-gray-7 mb-2">Monthly Breakdown</h4>
          <div class="grid gap-2" :class="forecastBuckets.length > 1 ? 'grid-cols-3' : 'grid-cols-1'">
            <KpiCard
              v-for="bucket in forecastBuckets"
              :key="bucket.label"
              :label="bucket.label"
              :amount="bucket.amount"
              :currency="props.currency"
              variant="tile"
            />
          </div>
        </div>
      </div>
      <div v-else class="text-center py-8 text-ink-gray-6 bg-surface-gray-1 rounded-lg border border-outline-gray-1">
        <Activity class="w-12 h-12 mx-auto text-ink-gray-6 opacity-40 mb-2" aria-hidden="true" />
        <p class="font-medium text-ink-gray-7">No sales forecast available</p>
        <p class="text-xs text-ink-gray-6">Click "Train Sales Forecast" to generate predictions</p>
      </div>
    </div>

    <!-- Dimensional forecast by product group -->
    <div class="mb-6">
      <div class="flex items-center justify-between mb-4">
        <SectionHeader variant="caption" title="Sales by Product Group (Historical + Forecast)" :level="3">
          <template #actions><BarChart3 class="w-5 h-5 text-ink-gray-6" aria-hidden="true" /></template>
        </SectionHeader>
        <Button variant="subtle" theme="gray" :loading="isLoadingDimensional" @click="loadDimensionalForecast">Refresh</Button>
      </div>
      <div v-if="transposedProductGroupData.rows.length" class="overflow-x-auto bg-surface-white rounded-lg border border-outline-gray-1">
        <table class="w-full text-sm">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-2 text-left sticky left-0 bg-surface-gray-1 z-10 min-w-[180px] text-ink-gray-7">Product Group</th>
              <th v-for="period in transposedProductGroupData.periods" :key="period" scope="col"
                :class="['px-3 py-2 text-right min-w-[90px]', isPeriodForecast(period) ? 'bg-surface-gray-2 text-ink-gray-7' : 'text-ink-gray-7']">
                <div>{{ formatPeriod(period) }}</div>
                <div class="text-xs font-normal text-ink-gray-6">{{ isPeriodForecast(period) ? 'Forecast' : 'Actual' }}</div>
              </th>
              <th scope="col" class="px-4 py-2 text-right bg-surface-gray-2 min-w-[100px] text-ink-gray-7">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in paginatedTransposedProductGroups" :key="idx" class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
              <td class="px-4 py-2 font-medium sticky left-0 bg-surface-white z-10 truncate max-w-[180px] text-ink-gray-8" :title="row.product_group">{{ row.product_group }}</td>
              <td v-for="period in transposedProductGroupData.periods" :key="period"
                :class="['px-3 py-2 text-right', row.values[period]?.is_forecast ? 'bg-surface-gray-1 text-ink-gray-7' : 'text-ink-gray-8']">
                <div class="font-medium">{{ money(row.values[period]?.revenue || 0) }}</div>
                <div class="text-xs text-ink-gray-6">{{ num(row.values[period]?.transactions || 0) }} txns</div>
              </td>
              <td class="px-4 py-2 text-right bg-surface-gray-1 font-bold text-ink-gray-9">
                <div>{{ money(row.total_revenue) }}</div>
                <div class="text-xs font-normal text-ink-gray-6">{{ num(row.total_transactions) }} txns</div>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="flex justify-between items-center px-4 py-2 bg-surface-gray-1 border-t border-outline-gray-1">
          <span class="text-sm text-ink-gray-6">
            Showing {{ productGroupPage * 15 + 1 }} - {{ Math.min((productGroupPage + 1) * 15, transposedProductGroupData.rows.length) }}
            of {{ transposedProductGroupData.rows.length }} product groups
          </span>
          <div class="flex gap-2">
            <Button variant="outline" theme="gray" :disabled="productGroupPage === 0" @click="productGroupPage--">Previous</Button>
            <Button variant="outline" theme="gray" :disabled="(productGroupPage + 1) * 15 >= transposedProductGroupData.rows.length" @click="productGroupPage++">Next</Button>
          </div>
        </div>
      </div>
      <div v-else class="text-center py-8 text-ink-gray-6 bg-surface-gray-1 rounded-lg border border-outline-gray-1">
        <BarChart3 class="w-12 h-12 mx-auto opacity-40 mb-2" aria-hidden="true" />
        <p class="text-ink-gray-7">No product group data available</p>
        <p class="text-xs text-ink-gray-6">Click Refresh to load dimensional forecast</p>
      </div>
    </div>

    <!-- Dimensional forecast by territory -->
    <div>
      <SectionHeader variant="caption" title="Sales by Territory (Historical + Forecast)" :level="3">
        <template #actions><Target class="w-5 h-5 text-ink-gray-6" aria-hidden="true" /></template>
      </SectionHeader>
      <div v-if="transposedTerritoryData.rows.length" class="mt-4 overflow-x-auto bg-surface-white rounded-lg border border-outline-gray-1">
        <table class="w-full text-sm">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-2 text-left sticky left-0 bg-surface-gray-1 z-10 min-w-[180px] text-ink-gray-7">Territory</th>
              <th v-for="period in transposedTerritoryData.periods" :key="period" scope="col"
                :class="['px-3 py-2 text-right min-w-[90px]', isPeriodForecast(period) ? 'bg-surface-gray-2 text-ink-gray-7' : 'text-ink-gray-7']">
                <div>{{ formatPeriod(period) }}</div>
                <div class="text-xs font-normal text-ink-gray-6">{{ isPeriodForecast(period) ? 'Forecast' : 'Actual' }}</div>
              </th>
              <th scope="col" class="px-4 py-2 text-right bg-surface-gray-2 min-w-[100px] text-ink-gray-7">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in paginatedTransposedTerritories" :key="idx" class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
              <td class="px-4 py-2 font-medium sticky left-0 bg-surface-white z-10 truncate max-w-[180px] text-ink-gray-8" :title="row.territory">{{ row.territory }}</td>
              <td v-for="period in transposedTerritoryData.periods" :key="period"
                :class="['px-3 py-2 text-right', row.values[period]?.is_forecast ? 'bg-surface-gray-1 text-ink-gray-7' : 'text-ink-gray-8']">
                <div class="font-medium">{{ money(row.values[period]?.revenue || 0) }}</div>
                <div class="text-xs text-ink-gray-6">{{ num(row.values[period]?.transactions || 0) }} txns</div>
              </td>
              <td class="px-4 py-2 text-right bg-surface-gray-1 font-bold text-ink-gray-9">
                <div>{{ money(row.total_revenue) }}</div>
                <div class="text-xs font-normal text-ink-gray-6">{{ num(row.total_transactions) }} txns</div>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="flex justify-between items-center px-4 py-2 bg-surface-gray-1 border-t border-outline-gray-1">
          <span class="text-sm text-ink-gray-6">
            Showing {{ territoryPage * 15 + 1 }} - {{ Math.min((territoryPage + 1) * 15, transposedTerritoryData.rows.length) }}
            of {{ transposedTerritoryData.rows.length }} territories
          </span>
          <div class="flex gap-2">
            <Button variant="outline" theme="gray" :disabled="territoryPage === 0" @click="territoryPage--">Previous</Button>
            <Button variant="outline" theme="gray" :disabled="(territoryPage + 1) * 15 >= transposedTerritoryData.rows.length" @click="territoryPage++">Next</Button>
          </div>
        </div>
      </div>
      <div v-else class="mt-4 text-center py-8 text-ink-gray-6 bg-surface-gray-1 rounded-lg border border-outline-gray-1">
        <Target class="w-12 h-12 mx-auto opacity-40 mb-2" aria-hidden="true" />
        <p class="text-ink-gray-7">No territory data available</p>
        <p class="text-xs text-ink-gray-6">Click Refresh above to load dimensional forecast</p>
      </div>
    </div>
  </div>

  <!-- ═══ Attribution ═══ -->
  <div v-if="activeTab === 'rev-sources'" class="space-y-6">
    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
      <SectionHeader variant="caption" title="Source Attribution" :level="3" />
      <div v-if="attributionConfig" class="mt-4 h-56 sm:h-72 lg:h-80">
        <IntelligenceChart :config="attributionConfig" class="h-56 sm:h-72 lg:h-80" />
      </div>
      <table v-if="attributionConfig" class="sr-only">
        <caption>Source attribution: revenue, gross profit, and order count by channel</caption>
        <thead><tr><th scope="col">Source</th><th scope="col">Revenue</th><th scope="col">Gross Profit</th><th scope="col">Orders</th></tr></thead>
        <tbody>
          <tr v-for="row in sourceAttribution.slice(0, 10)" :key="row.source as string">
            <th scope="row">{{ row.source }}</th>
            <td>{{ money(row.revenue as number) }}</td>
            <td>{{ money(row.gross_profit as number) }}</td>
            <td>{{ num(row.order_count as number) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="mt-4 text-center py-8 text-ink-gray-6">
        <Target class="w-8 h-8 mx-auto mb-2 opacity-40" aria-hidden="true" />
        <p>No source attribution data available</p>
      </div>
    </div>

    <div v-if="sourceAttribution.length" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      <KpiCard v-for="src in sourceAttribution.slice(0, 8)" :key="src.source as string"
        :label="src.source as string" :value="(src.order_count as number) > 0 ? money((src.revenue as number) / (src.order_count as number)) : NO_VALUE" sublabel="per order" />
    </div>

    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
      <SectionHeader variant="caption" title="Quotation Funnel" :level="3" />
      <div v-if="quotationAnalytics" class="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <KpiCard label="Total Quotes" :value="num(quotationAnalytics.total as number)" />
        <KpiCard label="Won" :value="num(quotationAnalytics.won as number)" />
        <KpiCard label="Lost" :value="num(quotationAnalytics.lost as number)" severity="high" />
      </div>
      <div v-if="lostReasonsConfig" class="h-48 sm:h-56 lg:h-64">
        <IntelligenceChart kind="donut" :config="lostReasonsConfig" class="h-48 sm:h-56 lg:h-64" />
      </div>
      <table v-if="lostReasonsConfig" class="sr-only">
        <caption>Quotation lost reasons by count</caption>
        <thead><tr><th scope="col">Reason</th><th scope="col">Count</th></tr></thead>
        <tbody>
          <tr v-for="r in (quotationAnalytics?.lost_reasons as Record<string, unknown>[])" :key="r.order_lost_reason as string">
            <th scope="row">{{ r.order_lost_reason }}</th>
            <td>{{ r.count }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else-if="quotationAnalytics" class="text-center py-8 text-ink-gray-6">
        <p>No lost reason data available</p>
      </div>
    </div>
  </div>
</template>
