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
  TrendingUp, Activity, BarChart3, Calendar,
  Target,
} from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { createToast } from '../helpers/toasts'
import { chartPalette, themeColor } from '../utils/chartTheme'
import KpiCard from '../intelligence/components/KpiCard.vue'
import SectionHeader from '../intelligence/components/SectionHeader.vue'
import TabBrief, { type Brief } from '../intelligence/components/TabBrief.vue'
import TabActions from '../intelligence/components/TabActions.vue'
import StatStrip, { type StatItem } from '../intelligence/components/StatStrip.vue'
import { severityBadge, severityTint, scoreSeverity, deltaInk, deltaGlyph, type Severity } from '../utils/status'
import { formatMoney, formatDate, formatDateShort, formatCount, formatPercent, asNumber, NO_VALUE } from '../utils/format'
import { DEFAULT_DATE_RANGES, FISCAL_PERIOD_RANGES, decodeCustomRange } from '../utils/dateRangePresets'
import type { DrillDownParams } from '../intelligence/composables/useDrillDown'

const props = defineProps<{
  data: Record<string, unknown>
  activeTab: string
  dateFilter: string
  currency: string | null
  drillDownEndpoint: string
  atRiskCount?: number | null
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
  forecast?: { yhat?: number; yhat_lower?: number; yhat_upper?: number }[]
  forecast_summary?: { total_forecast?: number; avg_daily_forecast?: number; trend?: string; days?: number; stale_days?: number }
  method?: string
  metrics?: Record<string, number>
  data_range?: { start?: string; end?: string }
}
/** Daily forecast rows carry their date; the sales-forecast type above only lists the fields read elsewhere. */
interface DailyForecastRow { ds?: string; yhat?: number; yhat_lower?: number; yhat_upper?: number }
const salesForecast = computed(
  () => (forecasts.value.sales_forecast ?? null) as SalesForecastPayload | null,
)
const forecastDays = computed(
  () => salesForecast.value?.forecast_summary?.days ?? salesForecast.value?.forecast?.length ?? 0,
)
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
/** Friendly model name — the payload carries raw enums like `linear_trend`. */
const METHOD_LABELS: Record<string, string> = {
  linear_trend: 'Linear trend',
  moving_average: 'Moving average',
  seasonal_naive: 'Seasonal naïve',
  prophet: 'Prophet',
  arima: 'ARIMA',
}
const methodLabel = computed(() => {
  const m = salesForecast.value?.method
  return m ? (METHOD_LABELS[m] ?? m.replace(/_/g, ' ')) : '—'
})
/** Plain-language direction from the payload's `trend`. */
const forecastTrendLabel = computed(() => {
  const t = salesForecast.value?.forecast_summary?.trend
  return t === 'up' ? 'Rising' : t === 'down' ? 'Falling' : t ? 'Flat' : '—'
})
/**
 * sMAPE/MAPE is meaningless to most readers. Turn it into a High/Medium/Low
 * reliability band (lower error = higher reliability) and keep the raw figure
 * as a sublabel for anyone who wants it.
 */
const forecastReliability = computed(() => {
  const e = forecastError.value
  if (!e) return null
  const level = e.value < 20 ? 'High' : e.value < 40 ? 'Medium' : 'Low'
  return { level, value: e.value, label: e.label, days: e.days }
})
const fulfillmentRate = computed(
  () => asNumber(fulfillment.value.fulfillment_rate) ?? asNumber(summary.value.fulfillment_rate) ?? null,
)
// The server reports 0 days when there were no sales to divide by: unmeasured, not "paid instantly".
const dso = computed(() => {
  const v = asNumber(fulfillment.value.dso) ?? asNumber(summary.value.dso)
  return v !== undefined && v > 0 ? v : null
})
const fulfillmentSeverity = computed(() => scoreSeverity(fulfillmentRate.value, { good: 95, warn: 85 }))
const dsoSeverity = computed(() => scoreSeverity(dso.value, { good: 30, warn: 60, higherIsBetter: false }))

// ── Local format helpers (respect server currency) ────────────────────────
function money(value: number | null | undefined): string {
  if (value == null) return '—'
  return formatMoney(value, props.currency)
}
function pct(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value.toFixed(1)}%`
}
function num(value: number | null | undefined): string {
  if (value == null) return '—'
  return value.toLocaleString()
}

// ── Window, basis and partial-period helpers ──────────────────────────────
/** The selected filter, spelled out, so a section never implies a fixed window. */
const windowLabel = computed(() => {
  const f = props.dateFilter
  const custom = decodeCustomRange(f)
  if (custom) return `${custom.start} to ${custom.end}`
  return [...DEFAULT_DATE_RANGES, ...FISCAL_PERIOD_RANGES].find(r => r.value === f)?.label ?? f
})

interface TrendRow { period: string; revenue?: number | null; is_partial?: boolean }
const monthlyTrendRows = computed(() => (comparisons.value.monthly_trend as TrendRow[]) ?? [])
// The in-progress month arrives flagged `is_partial`; its MoM is never headlined.
const currentMonthPartial = computed(
  () => monthlyTrendRows.value[monthlyTrendRows.value.length - 1]?.is_partial === true,
)
interface PeriodTotals { revenue?: number; transactions?: number; aov?: number; period?: string }
const currentMonth = computed(() => (comparisons.value.current_month ?? {}) as PeriodTotals)
const lastMonth = computed(() => (comparisons.value.last_month ?? {}) as PeriodTotals)
const lastYearMonth = computed(() => (comparisons.value.last_year_same_month ?? {}) as PeriodTotals)
const momGrowth = computed(() => asNumber(comparisons.value.mom_growth) ?? null)
const yoyGrowth = computed(() => asNumber(comparisons.value.yoy_growth) ?? null)
// Full-month comparisons: no day-of-month cap (added by backend fix)
const momGrowthFull = computed(() => asNumber(comparisons.value.mom_growth_full) ?? null)
const yoyGrowthFull = computed(() => asNumber(comparisons.value.yoy_growth_full) ?? null)
interface PeriodFull { revenue?: number; transactions?: number; period?: string }
const lastMonthFull = computed(() => (comparisons.value.last_month_full ?? {}) as PeriodFull)
const lastYearFull = computed(() => (comparisons.value.last_year_full ?? {}) as PeriodFull)

// Server-computed verdict headline (Rule 7)
const verdictHeadline = computed(
  () => (props.data.verdict_headline as string | undefined) ?? null,
)

function growthText(v: number | null): string {
  return v === null ? NO_VALUE : `${Math.abs(v).toFixed(1)}%`
}
function periodLabel(period: string, partial?: boolean): string {
  return formatPeriod(period) + (partial ? ' (partial)' : '')
}

const cashRatio = computed(() => asNumber(paymentMix.value.cash_ratio) ?? null)

// Unattributed revenue is ~0 once the basis is net; hide the note then.
const unattributedRevenue = computed(() => asNumber(salesReps.value.unattributed_revenue) ?? null)
const forecastStaleDays = computed(() => salesForecast.value?.forecast_summary?.stale_days ?? 0)
// ERPNext's built-in root Item Group: items left in it have no specific product group.
const ROOT_ITEM_GROUP = 'All Item Groups'

/**
 * Group-level margins (reps, product groups, sources) cluster around the
 * blended margin, so an absolute 30/15 scale paints every row red. Rate them
 * against the company's own blended margin instead.
 */
const marginBaseline = computed(
  () => asNumber(summary.value.overall_margin) ?? asNumber(margins.value.overall_margin) ?? null,
)
function groupMarginSeverity(v: number | null | undefined): Severity {
  const base = marginBaseline.value
  return base === null ? 'none' : scoreSeverity(v, { good: base * 1.2, warn: base * 0.8 })
}

// ── Attention rail items (computed from payload; severity classification only) ──
interface AttentionItem {
  severity: Severity
  metric: string
  why: string
  drill?: { title: string; params: DrillDownParams }
}
const attentionItems = computed((): AttentionItem[] => {
  const items: AttentionItem[] = []
  const dsoVal = dso.value
  const totalRec = asNumber(fulfillment.value.total_receivables) ?? null

  // 1. DSO (high if > 60, medium if > 30)
  if (dsoVal !== null && dsoVal > 30) {
    const sev: Severity = dsoVal > 60 ? 'high' : 'medium'
    const surplus = Math.round(dsoVal - 30)
    items.push({
      severity: sev,
      metric: `DSO: ${dsoVal.toFixed(0)} days`,
      why: `${surplus} days above the 30-day target.${totalRec != null ? ` ${money(totalRec)} in receivables outstanding.` : ''}`,
      drill: { title: 'Receivables', params: { metric: 'receivables' } },
    })
  }

  // 2. Softest complete month (warn if MoM < -20%)
  const trend = monthlyTrendRows.value.filter(m => !m.is_partial)
  if (trend.length >= 2) {
    const softest = trend.reduce((a, b) => ((b.revenue ?? 0) < (a.revenue ?? 0) ? b : a))
    const sf_pct = (softest as unknown as { mom_pct?: number | null }).mom_pct
    if (sf_pct !== null && sf_pct !== undefined && sf_pct < -20) {
      const sfFull = lastMonthFull.value
      const sfFullRev = sfFull.revenue != null ? ` Full prior month ${money(sfFull.revenue)}.` : ''
      items.push({
        severity: 'medium',
        metric: `${formatPeriod(softest.period)} revenue: ${money(softest.revenue)}`,
        why: `Softest complete month in the window.${sfFullRev}`,
        drill: { title: `Invoices — ${formatPeriod(softest.period)}`, params: { metric: 'invoices_by_period', period: softest.period } },
      })
    }
  }

  // 3. Forecast reliability / staleness
  const rel = forecastReliability.value
  const stale = forecastStaleDays.value
  if (rel && (rel.level === 'Low' || stale > 30)) {
    items.push({
      severity: 'medium',
      metric: `Forecast reliability: ${rel.level}`,
      why: `${rel.label} ${rel.value.toFixed(1)}%${stale > 0 ? ` — model is ${stale} days stale` : ''}. Retrain to improve accuracy.`,
    })
  }

  // 4. At-risk customers (from shell prop, optional)
  if (props.atRiskCount != null && props.atRiskCount > 0) {
    items.push({
      severity: 'medium',
      metric: `${props.atRiskCount} customers at risk`,
      why: 'High + Critical churn risk from customer intelligence. Review the Actions tab.',
    })
  }

  // Positive items
  const frRate = fulfillmentRate.value
  if (frRate !== null && frRate >= 95) {
    const fulfilled = asNumber(fulfillment.value.fulfilled) ?? null
    const total = asNumber(fulfillment.value.total_orders) ?? null
    items.push({
      severity: 'low',
      metric: `Fulfillment: ${pct(frRate)}`,
      why: fulfilled != null && total != null
        ? `${num(fulfilled)} of ${num(total)} orders fulfilled.`
        : 'Orders are being fulfilled on schedule.',
    })
  }
  const yoy = yoyGrowth.value
  if (yoy !== null && yoy >= 10) {
    items.push({
      severity: 'low',
      metric: `YoY: +${yoy.toFixed(1)}% (like-for-like)`,
      why: 'Same-duration comparison vs prior year. Full-month basis may differ.',
    })
  }

  return items
})
// ── Operational tile sublabel helpers ─────────────────────────────────────
const fulfillmentSublabel = computed(() => {
  const f = asNumber(fulfillment.value.fulfilled)
  const t = asNumber(fulfillment.value.total_orders)
  return f != null && t != null ? `${num(f)} of ${num(t)} orders` : undefined
})
const receivablesSublabel = computed(() => {
  const r = asNumber(fulfillment.value.total_receivables)
  return r != null ? `Receivables ${money(r)}` : undefined
})
const avgDaysSubLabel = computed(() => {
  const n = asNumber(revenueMetrics.value.unique_customers)
  return n != null ? `${num(n)} customers` : undefined
})


// ── State: ML training ────────────────────────────────────────────────────
const isTraining = ref<string | false>(false)
const trainingStatus = ref('')
const trainingOk = ref(true)

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
  const trend = monthlyTrendRows.value
  if (!trend.length) return null
  return {
    data: trend.map(m => ({
      period: periodLabel(m.period, m.is_partial),
      Revenue: m.revenue ?? null,
    })),
    title: '',
    xAxis: { key: 'period', type: 'category' as const },
    yAxis: { title: '', yMin: 0 },
    series: [
      { name: 'Revenue', type: 'bar' as const, color: themeColor('--app-accent') },
    ],
  }
})

// ── Margins story ──────────────────────────────────────────────────────────
// The tab used to show three KPIs + two tables and silently drop the
// server's `margin_trend`. These derive the narrative spine (trajectory,
// peak/trough, GP concentration) from the same payload.
interface MarginPoint { period: string; margin: number; revenue: number; gp: number; partial: boolean }
const marginStory = computed(() => {
  const trend = ((margins.value.margin_trend as Record<string, unknown>[]) ?? [])
    .filter(t => typeof t.margin_pct === 'number')
  if (!trend.length) return null
  const pts: MarginPoint[] = trend.map(t => ({
    period: (t.period as string) ?? '',
    margin: t.margin_pct as number,
    revenue: (t.revenue as number) ?? 0,
    gp: (t.gross_profit as number) ?? 0,
    partial: t.is_partial === true,
  }))
  const latest = pts[pts.length - 1]
  const prior = pts.length > 1 ? pts[pts.length - 2] : null
  const deltaPp = prior ? latest.margin - prior.margin : null
  const best = pts.reduce((a, b) => (b.margin > a.margin ? b : a))
  const worst = pts.reduce((a, b) => (b.margin < a.margin ? b : a))
  const avg = pts.reduce((s, p) => s + p.margin, 0) / pts.length
  return { latest, prior, deltaPp, best, worst, avg, months: pts.length }
})
const marginTrendConfig = computed(() => {
  const trend = (margins.value.margin_trend as Record<string, unknown>[]) ?? []
  if (!trend.length) return null
  const palette = chartPalette(2)
  return {
    data: trend.map(m => ({
      period: periodLabel(m.period as string, m.is_partial === true),
      'Net Sales': asNumber(m.revenue) ?? null,
      'Margin %': asNumber(m.margin_pct) ?? null,
    })),
    title: '',
    xAxis: { key: 'period', type: 'category' as const },
    yAxis: { title: '', yMin: 0 },
    y2Axis: { title: '', yMin: 0 },
    series: [
      { name: 'Net Sales', type: 'bar' as const, color: palette[0], axis: 'y' as const },
      { name: 'Margin %', type: 'line' as const, color: palette[1], axis: 'y2' as const, showDataPoints: true },
    ],
  }
})
// Product groups ranked by gross-profit contribution (share of total GP),
// so the table answers "where does the profit actually come from".
const marginGroups = computed(() => {
  const groups = (margins.value.by_product_group as Record<string, unknown>[]) ?? []
  const totalGp = groups.reduce((s, g) => s + ((g.gross_profit as number) ?? 0), 0)
  return [...groups]
    .sort((a, b) => ((b.gross_profit as number) ?? 0) - ((a.gross_profit as number) ?? 0))
    .slice(0, 10)
    .map((g): Record<string, unknown> & { gp_share: number } => ({
      ...g,
      gp_share: totalGp > 0 ? ((g.gross_profit as number) ?? 0) / totalGp * 100 : 0,
    }))
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
        trainingOk.value = true
        createToast({
          title: 'Training Started',
          message,
          variant: 'success',
        })
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : 'Unknown error'
        trainingStatus.value = `Training error: ${msg}`
        trainingOk.value = false
        createToast({ title: 'Training Error', message: msg, variant: 'error' })
      } finally {
        isTraining.value = false
      }
    },
  })
}

// ── Lazy loaders ──────────────────────────────────────────────────────────
// Lazy loaders: each runs on first visit to its tab and again only when the
// filter changes. A response for a filter that is no longer selected is dropped.
const dimensionalCache = new Map<string, Record<string, unknown>>()
let sourcesLoadedFor: string | null = null

async function loadDimensionalForecast(force = false) {
  const filter = props.dateFilter
  const cached = force ? undefined : dimensionalCache.get(filter)
  if (cached) {
    dimensionalForecast.value = cached
    productGroupPage.value = 0
    territoryPage.value = 0
    return
  }
  isLoadingDimensional.value = true
  try {
    const result = (await apiCall('insights.api.ml.get_historical_and_forecast_by_dimension', {
      dimension: 'both',
      date_filter: filter,
    })) as Record<string, unknown>
    dimensionalCache.set(filter, result)
    if (filter !== props.dateFilter) return
    dimensionalForecast.value = result
    productGroupPage.value = 0
    territoryPage.value = 0
  } catch {
    createToast({ title: 'Error', message: 'Failed to load dimensional forecast', variant: 'error' })
  } finally {
    if (filter === props.dateFilter) isLoadingDimensional.value = false
  }
}

async function loadSourceAttribution() {
  const filter = props.dateFilter
  isLoadingSources.value = true
  try {
    const [attribution, quotation] = await Promise.all([
      apiCall('insights.api.ml.sales.source_attributed_sales', { date_filter: filter }),
      apiCall('insights.api.ml.sales.quotation_analytics', { date_filter: filter }),
    ])
    if (filter !== props.dateFilter) return
    sourceAttribution.value = (attribution as Record<string, unknown>[]) || []
    quotationAnalytics.value = quotation as Record<string, unknown>
    sourcesLoadedFor = filter
  } catch (e: unknown) {
    console.error('Error loading source attribution:', e)
  } finally {
    if (filter === props.dateFilter) isLoadingSources.value = false
  }
}

function drillSource(source: string) {
  drillOpen(`Invoices attributed to ${source}`, { metric: 'sales_by_source', source, period: props.dateFilter })
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
): { periods: string[]; rows: DimRow[]; forecastPeriods: Set<string> } {
  if (!rawData.length) return { periods: [], rows: [], forecastPeriods: new Set() }
  const forecastPeriods = new Set<string>()
  const periodsSet = new Set<string>()
  const groupsMap = new Map<string, Map<string, { revenue: number; transactions: number; is_forecast: boolean }>>()
  rawData.forEach(item => {
    periodsSet.add(item.period)
    if (item.is_forecast) forecastPeriods.add(item.period)
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
  return { periods, rows, forecastPeriods }
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
/**
 * Overall monthly revenue — actuals then the model's projection — built by
 * summing the product-group dimensional rows across groups per month. Reuses
 * data already loaded for the tables (no extra call). `Actual` and `Forecast`
 * are separate columns so the chart draws a solid history line and a dashed
 * projection line; the last actual month is also written into `Forecast` so
 * the dashed line visually connects to where the solid one ends.
 */
const monthlyTrend = computed(() => {
  const rows = (dimensionalForecast.value.combined_product_group as DimItem[]) || []
  if (!rows.length) return null
  const byPeriod = new Map<string, { revenue: number; is_forecast: boolean }>()
  for (const r of rows) {
    const b = byPeriod.get(r.period) ?? { revenue: 0, is_forecast: false }
    b.revenue += r.revenue ?? 0
    if (r.is_forecast) b.is_forecast = true
    byPeriod.set(r.period, b)
  }
  const periods = Array.from(byPeriod.keys()).sort()
  const data = periods.map(p => {
    const { revenue, is_forecast } = byPeriod.get(p)!
    return {
      period: formatPeriod(p),
      Actual: is_forecast ? null : revenue,
      Forecast: is_forecast ? revenue : null,
    } as Record<string, unknown>
  })
  const lastActual = data.map(d => d.Actual !== null).lastIndexOf(true)
  if (lastActual >= 0 && lastActual < data.length - 1) data[lastActual].Forecast = data[lastActual].Actual
  return data
})
const revenueProjectionConfig = computed(() => {
  const d = monthlyTrend.value
  if (!d) return null
  const palette = chartPalette(2)
  return {
    data: d,
    title: '',
    xAxis: { key: 'period', type: 'category' as const },
    yAxis: { title: 'Revenue' },
    series: [
      { name: 'Actual', type: 'line' as const, color: palette[0], showDataPoints: true },
      { name: 'Forecast', type: 'line' as const, color: palette[1], lineType: 'dashed' as const, showDataPoints: true },
    ],
  }
})

interface TransposedRow {
  metric: string
  values: Record<string, number | null>
  total: number | null
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
  const recentDays = dailyMix.slice(-15)
  const dates = recentDays.map(d => d.sale_date)
  const rows: TransposedRow[] = [
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

/**
 * Cost of Sales, Gross Margin (amount) and Gross Margin % rows shared by the
 * Weekly / Monthly / Daily tables. Margin % is GP / net sales (GP + cost), the
 * same net-sales basis the Margins tab uses -- not the tax-inclusive Revenue
 * row above it, which is grand_total.
 */
function grossProfitRows<T extends { cost_of_sales?: number; gross_profit?: number }>(
  items: T[],
  keyOf: (i: T) => string,
): TransposedRow[] {
  // A period with revenue but zero cost basis has no valuation yet
  // (incoming_rate not posted), not a genuine 100% margin. Treat cost <= 0
  // as "not valued": render — and exclude it from the totals rather than
  // reporting a fake full-margin figure.
  const hasCost = (i: T) => typeof i.cost_of_sales === 'number' && i.cost_of_sales > 0
  const cost = (i: T) => i.cost_of_sales ?? 0
  const gp = (i: T) => i.gross_profit ?? 0
  const costed = items.filter(hasCost)
  const totalCost = costed.reduce((s, i) => s + cost(i), 0)
  const totalGp = costed.reduce((s, i) => s + gp(i), 0)
  const totalNet = totalGp + totalCost
  const anyCost = costed.length > 0
  return [
    {
      metric: 'Cost of Sales',
      values: items.reduce((acc, i) => { acc[keyOf(i)] = hasCost(i) ? cost(i) : null; return acc }, {} as Record<string, number | null>),
      total: anyCost ? totalCost : null,
      colorClass: 'text-ink-gray-7',
      isCurrency: true,
    },
    {
      metric: 'Gross Margin',
      values: items.reduce((acc, i) => { acc[keyOf(i)] = hasCost(i) ? gp(i) : null; return acc }, {} as Record<string, number | null>),
      total: anyCost ? totalGp : null,
      colorClass: 'text-ink-gray-8',
      isCurrency: true,
    },
    {
      metric: 'Gross Margin %',
      values: items.reduce((acc, i) => {
        acc[keyOf(i)] = hasCost(i) ? (gp(i) / (gp(i) + cost(i))) * 100 : null
        return acc
      }, {} as Record<string, number | null>),
      total: anyCost && totalNet > 0 ? (totalGp / totalNet) * 100 : null,
      colorClass: 'text-ink-gray-8',
      isPercent: true,
    },
  ]
}

// ── Format helpers ─────────────────────────────────────────────────────────
function formatPeriod(period: string | null | undefined): string {
  if (!period || !/^\d{4}-\d{2}/.test(period)) return period || NO_VALUE
  const [year, month] = period.split('-')
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${monthNames[parseInt(month) - 1]} ${year.slice(2)}`
}

// ── Attribution chart configs ─────────────────────────────────────────────
// Per-source rows enriched with revenue share, margin %, and avg/order — all
// derived from the {source, revenue, gross_profit, order_count} payload, no
// extra backend call.
const attributionRows = computed(() => {
  const rows = sourceAttribution.value
  const total = rows.reduce((s, r) => s + ((r.revenue as number) ?? 0), 0)
  return rows.map((r) => {
    const rev = (r.revenue as number) ?? 0
    const gp = (r.gross_profit as number) ?? 0
    const orders = (r.order_count as number) ?? 0
    return {
      source: r.source as string,
      revenue: rev,
      share: total > 0 ? (rev / total) * 100 : null,
      gross_profit: gp,
      margin_pct: rev > 0 ? (gp / rev) * 100 : null,
      order_count: orders,
      aov: orders > 0 ? rev / orders : null,
    }
  })
})
const attributionSummary = computed(() => {
  const rows = attributionRows.value
  if (!rows.length) return null
  const total = rows.reduce((s, r) => s + r.revenue, 0)
  const unattributed = rows.find(r => r.source === 'Unattributed')?.revenue ?? 0
  const attributed = total - unattributed
  const named = rows.filter(r => r.source !== 'Unattributed')
  const top = named[0] ?? null
  return {
    attributedRevenue: attributed,
    attributedPct: total > 0 ? (attributed / total) * 100 : 0,
    sourceCount: named.length,
    topSource: top ? top.source : NO_VALUE,
    topSourceRevenue: top ? top.revenue : null,
  }
})
const attributionConfig = computed(() => {
  const d = attributionRows.value.slice(0, 10)
  if (!d.length) return null
  const palette = chartPalette(2)
  return {
    data: d.map(x => ({
      source: x.source,
      Revenue: x.revenue,
      Profit: x.gross_profit,
    })),
    title: '',
    xAxis: { key: 'source', type: 'category' as const },
    yAxis: { title: 'Amount', yMin: 0 },
    series: [
      { name: 'Revenue', type: 'bar' as const, color: palette[0] },
      { name: 'Profit', type: 'bar' as const, color: palette[1] },
    ],
  }
})
const lostReasonsData = computed(() => {
  const reasons = (quotationAnalytics.value?.lost_reasons as Record<string, unknown>[]) ?? []
  if (!reasons.length) return []
  // Compute total for percentage calculation
  const total = reasons.reduce((sum, r) => sum + ((r.count as number) ?? 0), 0)
  // Sort by count descending, then calculate percentage for each
  return reasons
    .map(r => ({
      reason: r.order_lost_reason as string,
      count: (r.count as number) ?? 0,
      percentage: total > 0 ? (((r.count as number) ?? 0) / total * 100) : 0,
    }))
    .sort((a, b) => b.count - a.count)
})

// ── Lazy-load on tab activation / filter change ───────────────────────────
// Immediate so a mount that lands on a lazy tab loads it; tabs not yet visited
// load nothing, and a visited tab reloads here only while it is the active one.
watch([() => props.activeTab, () => props.dateFilter], ([tab, filter]) => {
  if (tab === 'rev-forecasts') loadDimensionalForecast()
  if (tab === 'rev-sources' && sourcesLoadedFor !== filter) loadSourceAttribution()
}, { immediate: true })

const sourcesBrief = computed(
  () => (quotationAnalytics.value?.brief ?? null) as Brief | null,
)
// ── Server briefs + stat strips ───────────────────────────────────────────
// Headline text is built server-side (insights/ml/tab_briefs/revenue.py); the
// client only renders it, and renders nothing for an older cached payload.
const tabBriefs = computed(
  () => (props.data.tab_briefs ?? {}) as Record<string, Brief>,
)
const toneOf = (s: Severity): StatItem['tone'] =>
  s === 'high' || s === 'critical' ? 'neg' : s === 'medium' ? 'warn' : s === 'low' ? 'pos' : undefined
const ofRevenue = (v: unknown) => {
  const n = asNumber(v)
  return n == null ? undefined : `${n.toFixed(1)}% of revenue`
}

const paymentStrip = computed<StatItem[]>(() => [
  { label: 'Cash Sales', amount: asNumber(paymentMix.value.cash_total) ?? null, sublabel: ofRevenue(paymentMix.value.cash_ratio) },
  { label: 'Credit Sales', amount: asNumber(paymentMix.value.credit_total) ?? null, sublabel: ofRevenue(paymentMix.value.credit_ratio) },
  { label: 'DSO', value: dso.value?.toFixed(1) ?? null, unit: ' days', tone: toneOf(dsoSeverity.value) },
  { label: 'Receivables Outstanding', amount: asNumber(fulfillment.value.total_receivables) ?? null },
])

const repsStrip = computed<StatItem[]>(() => {
  const reps = (salesReps.value.reps ?? []) as Record<string, number | string>[]
  const team = asNumber(salesReps.value.total_team_revenue)
  const top = salesReps.value.top_performer as Record<string, number | string> | undefined
  const best = reps.reduce<Record<string, number | string> | null>(
    (a, r) => (a === null || (r.margin_pct as number) > (a.margin_pct as number) ? r : a), null)
  const nameOf = (r: Record<string, number | string> | null | undefined) =>
    r ? String(r.sales_person_name || r.sales_person) : undefined
  return [
    { label: 'Team Revenue', amount: team ?? null, sublabel: `${reps.length} reps` },
    { label: 'Top Rep Share', percent: top && team ? ((top.total_revenue as number) / team) * 100 : null, sublabel: nameOf(top) },
    { label: 'Blended Margin', percent: asNumber(margins.value.overall_margin) ?? null },
    { label: 'Best Margin Rep', percent: best ? (best.margin_pct as number) : null, sublabel: nameOf(best) },
  ]
})

/** "Apr 26, ₹2.25M gross profit, +4.1pp vs blended" for a margin-trend month; the blended margin is the payload's overall margin. */
const monthSub = (t: Record<string, unknown> | null): string | undefined => {
  if (!t) return undefined
  const blended = asNumber(margins.value.overall_margin)
  const gp = asNumber(t.gross_profit)
  const diff = blended === undefined ? null : Number(t.margin_pct) - blended
  return [
    formatPeriod(t.period as string),
    gp === undefined ? null : `${money(gp)} gross profit`,
    diff === null ? null : `${diff >= 0 ? '+' : '-'}${Math.abs(diff).toFixed(1)}pp vs blended`,
  ].filter(Boolean).join(', ')
}

const marginsStrip = computed<StatItem[]>(() => {
  const done = ((margins.value.margin_trend ?? []) as Record<string, unknown>[])
    .filter(t => t.is_partial !== true && typeof t.margin_pct === 'number')
  const hi = done.reduce<Record<string, unknown> | null>((a, t) => (a === null || (t.margin_pct as number) > (a.margin_pct as number) ? t : a), null)
  const lo = done.reduce<Record<string, unknown> | null>((a, t) => (a === null || (t.margin_pct as number) < (a.margin_pct as number) ? t : a), null)
  const groups = (margins.value.by_product_group ?? []) as Record<string, unknown>[]
  const top = groups.reduce<Record<string, unknown> | null>((a, g) => (a === null || (g.margin_pct as number) > (a.margin_pct as number) ? g : a), null)
  return [
    { label: 'Blended Margin', percent: asNumber(margins.value.overall_margin) ?? null, sublabel: `${money(margins.value.total_profit as number)} gross profit` },
    { label: 'Peak Month', percent: hi ? (hi.margin_pct as number) : null, sublabel: monthSub(hi) },
    { label: 'Trough Month', percent: lo ? (lo.margin_pct as number) : null, sublabel: monthSub(lo) },
    { label: 'Top Group Margin', percent: top ? (top.margin_pct as number) : null, sublabel: top ? String(top.item_group) : undefined },
  ]
})

const forecastStrip = computed<StatItem[]>(() => {
  const rows = salesForecast.value?.forecast ?? []
  const sum = (k: 'yhat_lower' | 'yhat_upper') =>
    rows.length && rows.every(r => typeof r[k] === 'number') ? rows.reduce((s, r) => s + (r[k] as number), 0) : null
  const rel = forecastReliability.value
  return [
    { label: 'Base Forecast', amount: salesForecast.value?.forecast_summary?.total_forecast ?? null, sublabel: `${forecastDays.value} days, ${methodLabel.value}` },
    { label: 'Downside', amount: sum('yhat_lower'), sublabel: 'sum of the lower bound' },
    { label: 'Upside', amount: sum('yhat_upper'), sublabel: 'sum of the upper bound' },
    { label: 'Model Error', percent: rel ? rel.value : null, sublabel: rel ? `${rel.label}, ${rel.level} reliability` : undefined, tone: rel?.level === 'Low' ? 'warn' : undefined },
  ]
})

/** The 30 daily forecast values with their confidence band, one line each. */
const dailyForecastConfig = computed(() => {
  const rows = (salesForecast.value?.forecast ?? []) as DailyForecastRow[]
  if (!rows.length || rows.some((r) => !r.ds || typeof r.yhat !== 'number')) return null
  const palette = chartPalette(3)
  return {
    data: rows.map((r) => ({
      day: r.ds!,
      'Upper bound': Number(r.yhat_upper ?? r.yhat),
      'Point estimate': Number(r.yhat),
      'Lower bound': Number(r.yhat_lower ?? r.yhat),
    })),
    title: '',
    xAxis: { key: 'day', type: 'category' as const },
    yAxis: { title: 'Revenue per day' },
    series: [
      { name: 'Upper bound', type: 'area' as const, color: palette[1], fillOpacity: 0.12, showDataPoints: false },
      { name: 'Point estimate', type: 'line' as const, color: palette[0], showDataPoints: false },
      { name: 'Lower bound', type: 'line' as const, color: palette[2], lineType: 'dashed' as const, showDataPoints: false },
    ],
  }
})

const sourcesStrip = computed<StatItem[]>(() => {
  const s = attributionSummary.value
  return [
    { label: 'Attributed Revenue', amount: s ? s.attributedRevenue : null, sublabel: s ? `${pct(s.attributedPct)} of total revenue` : undefined },
    { label: 'Top Lead Source', value: s ? s.topSource : null, sublabel: s?.topSourceRevenue != null ? money(s.topSourceRevenue) : undefined },
    { label: 'Quote Conversion', percent: quotationAnalytics.value ? (quotationAnalytics.value.conversion_rate as number) : null, sublabel: 'quotes won / total' },
    { label: 'Sources Tracked', value: s ? String(s.sourceCount) : null, sublabel: 'excludes unattributed' },
  ]
})

// ── Cash vs Credit panels: arithmetic on payload fields only ──────────────
const DSO_TARGET = 30 // the `good` cut of `dsoSeverity`
const creditRatio = computed(() => asNumber(paymentMix.value.credit_ratio) ?? null)
const paymentCards = computed(() => [
  { title: 'Cash', share: cashRatio.value, amount: asNumber(paymentMix.value.cash_total) ?? null, note: 'Collected at the point of sale', tint: 'bg-card', fill: 'bg-surface-green-3' },
  {
    title: 'Credit',
    share: creditRatio.value,
    amount: asNumber(paymentMix.value.credit_total) ?? null,
    note: asNumber(fulfillment.value.total_receivables) == null ? null : `${money(asNumber(fulfillment.value.total_receivables))} outstanding now`,
    tint: 'bg-surface-amber-2',
    fill: 'bg-surface-amber-3',
  },
])
interface BridgeBar { text: string; width: number; fill: string }
// Each bar is scaled against the longest bar in its own row (money rows against
// 100%, the DSO row against the larger of DSO and target).
const bridge = computed<{ label: string; bars: BridgeBar[] }[]>(() => {
  const daily = asNumber(fulfillment.value.avg_daily_sales)
  const ar = asNumber(fulfillment.value.total_receivables)
  const d = dso.value
  if (!daily || ar == null || d === null) return []
  const rows: { label: string; bars: BridgeBar[] }[] = [
    { label: 'Avg daily sales', bars: [{ text: `${money(daily)} / day`, width: 100, fill: 'bg-surface-blue-2' }] },
  ]
  if (creditRatio.value != null) {
    rows.push({
      label: `Credit portion (${pct(creditRatio.value)})`,
      bars: [{ text: `${money((daily * creditRatio.value) / 100)} / day`, width: creditRatio.value, fill: 'bg-surface-amber-2' }],
    })
  }
  const longest = Math.max(d, DSO_TARGET)
  rows.push({
    label: 'Collection period',
    bars: [
      { text: `${d.toFixed(1)} days`, width: (d / longest) * 100, fill: 'bg-surface-amber-2' },
      { text: `${DSO_TARGET} day target`, width: (DSO_TARGET / longest) * 100, fill: 'bg-surface-green-2' },
    ],
  })
  const excess = ar - DSO_TARGET * daily
  if (excess > 0) {
    rows.push({
      label: 'Receivables beyond target',
      bars: [{ text: money(excess), width: (excess / ar) * 100, fill: 'bg-surface-red-2' }],
    })
  }
  return rows
})

// ── Sales Reps: concentration bar + spotlight cards ───────────────────────
interface RepRow { sales_person: string; sales_person_name?: string; total_revenue: number; margin_pct: number; gross_profit: number; avg_order_value: number; total_orders: number; unique_customers: number; rank: number }
const repName = (r: RepRow) => r.sales_person_name || r.sales_person
const rankedReps = computed(() =>
  [...((salesReps.value.reps ?? []) as RepRow[])].sort((a, b) => b.total_revenue - a.total_revenue),
)
const repSegments = computed(() => {
  const team = asNumber(salesReps.value.total_team_revenue)
  const reps = rankedReps.value
  if (!team || !reps.length) return []
  const fills = ['bg-surface-blue-3', 'bg-surface-amber-3', 'bg-surface-green-3']
  const seg = (name: string, amount: number, fill: string) => ({ name, amount, share: (amount / team) * 100, fill })
  const out = reps.slice(0, 3).map((r, i) => seg(repName(r), r.total_revenue, fills[i]))
  const tail = reps.slice(3)
  if (tail.length) out.push(seg(tail.map(repName).join(' + '), tail.reduce((s, r) => s + r.total_revenue, 0), 'bg-surface-gray-4'))
  return out
})
const repSpotlights = computed(() => {
  const reps = rankedReps.value
  const base = marginBaseline.value
  if (reps.length < 2) return []
  const top = reps[0]
  const cards = [{ heading: 'Largest book', rep: top, tint: 'bg-surface-amber-2' }]
  const second = reps[1]
  if (base !== null && second.margin_pct < base) cards.push({ heading: 'Below blended margin', rep: second, tint: 'bg-surface-red-2' })
  const best = reps.reduce((a, r) => (r.margin_pct > a.margin_pct ? r : a), reps[0])
  if (best !== top && base !== null && best.margin_pct > base) cards.push({ heading: 'Highest margin', rep: best, tint: 'bg-surface-green-2' })
  return cards
})

// ── Forecasts: model health + scenarios ───────────────────────────────────
const forecastRange = computed(() => {
  const rows = salesForecast.value?.forecast ?? []
  const lows = rows.map(r => r.yhat_lower).filter((v): v is number => typeof v === 'number')
  const ups = rows.map(r => r.yhat_upper).filter((v): v is number => typeof v === 'number')
  return { lows, ups, complete: rows.length > 0 && lows.length === rows.length && ups.length === rows.length }
})
const modelHealth = computed(() => {
  const sf = salesForecast.value
  if (!sf) return []
  const m = sf.metrics ?? {}
  const { lows, ups, complete } = forecastRange.value
  const range = sf.data_range
  return [
    { label: 'Method', value: methodLabel.value },
    { label: 'Training points', value: m.n_points == null ? NO_VALUE : `${num(m.n_points)} daily observations` },
    { label: 'Training window', value: range?.start && range?.end ? `${formatDate(range.start)} to ${formatDate(range.end)}` : NO_VALUE },
    { label: 'Hold-out horizon', value: m.horizon_days == null ? NO_VALUE : `${m.horizon_days} days` },
    { label: 'sMAPE', value: m.smape == null ? NO_VALUE : pct(m.smape) },
    { label: 'RMSE', value: m.rmse == null ? NO_VALUE : money(m.rmse) },
    { label: 'MAE', value: m.mae == null ? NO_VALUE : money(m.mae) },
    { label: 'Daily interval', value: complete ? `${money(Math.min(...lows))} to ${money(Math.max(...ups))}` : NO_VALUE },
  ]
})
const scenarioRows = computed(() => {
  const { lows, ups, complete } = forecastRange.value
  const base = salesForecast.value?.forecast_summary?.total_forecast
  if (!complete || base == null) return []
  const sum = (xs: number[]) => xs.reduce((s, v) => s + v, 0)
  return [
    { name: 'Downside', note: 'Sum of the daily lower bound', amount: sum(lows), tint: 'bg-surface-red-2' },
    { name: 'Base', note: 'Sum of the daily point forecast', amount: base, tint: 'bg-surface-blue-2' },
    { name: 'Upside', note: 'Sum of the daily upper bound', amount: sum(ups), tint: 'bg-surface-green-2' },
  ]
})
</script>

<template>
  <!-- ═══ Revenue Overview ═══ -->
  <div v-if="activeTab === 'rev-overview'">

    <!-- Verdict card: server-computed finding (Rule 7) -->
    <div
      v-if="verdictHeadline"
      class="mb-6 rounded-lg border border-outline-gray-2 bg-accent-soft p-4"
    >
      <p class="text-sm font-semibold leading-snug text-ink-gray-9">{{ verdictHeadline }}</p>
      <p class="mt-1 text-xs text-ink-gray-6">{{ windowLabel }}{{ currency ? ` · ${currency}` : '' }}</p>
    </div>

    <!-- 2-col: hero chart + period comparison (left) + attention rail (right) -->
    <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">

      <!-- LEFT: hero chart + period comparison -->
      <div class="space-y-4 lg:col-span-2">

        <!-- Monthly trend: accent-soft hero panel -->
        <SectionHeader variant="caption" title="Monthly Revenue Trend" :hint="windowLabel" :level="3">
          <template #actions><TrendingUp class="w-4 h-4 text-ink-gray-6" aria-hidden="true" /></template>
        </SectionHeader>
        <div class="rounded-lg border border-outline-gray-1 bg-accent-soft p-4">
          <IntelligenceChart v-if="monthlyTrendConfig" :config="monthlyTrendConfig" class="h-80" />
          <div v-else class="flex h-56 items-center justify-center text-sm text-ink-gray-6">No trend data</div>
          <table v-if="monthlyTrendConfig" class="sr-only">
            <caption>Monthly revenue trend</caption>
            <thead><tr><th scope="col">Period</th><th scope="col">Revenue</th></tr></thead>
            <tbody>
              <tr v-for="m in monthlyTrendRows" :key="m.period">
                <th scope="row">{{ m.period }}{{ m.is_partial ? ' (partial)' : '' }}</th>
                <td>{{ money(m.revenue) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Period comparison: current | like-for-like prior | year-ago -->
        <div class="overflow-hidden rounded-lg border border-outline-gray-1 bg-card">
          <div class="flex items-center justify-between border-b border-outline-gray-1 px-4 py-2">
            <span class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">Period Comparison</span>
            <span class="text-xs text-ink-gray-6">{{ formatPeriod(currentMonth.period) }} vs prior periods</span>
          </div>
          <div class="grid grid-cols-1 divide-y divide-outline-gray-1 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            <!-- Current period -->
            <div class="p-4">
              <p class="mb-1 text-xs text-ink-gray-6">{{ formatPeriod(currentMonth.period) }} (current{{ currentMonthPartial ? ', partial' : '' }})</p>
              <p class="tnum text-xl font-bold text-ink-gray-9">{{ money(currentMonth.revenue) }}</p>
              <p class="mt-1 text-xs text-ink-gray-6">
                {{ num(currentMonth.transactions) }} orders
                <template v-if="currentMonth.aov"> · AOV {{ money(currentMonth.aov) }}</template>
              </p>
            </div>
            <!-- Prior window (like-for-like, same-duration) -->
            <div class="p-4">
              <div class="mb-1 flex items-baseline justify-between gap-2">
                <p class="text-xs text-ink-gray-6">Prior window (like-for-like)</p>
                <span v-if="momGrowth !== null" :class="['shrink-0 text-xs font-bold', deltaInk(momGrowth)]">
                  {{ deltaGlyph(momGrowth) }} {{ growthText(momGrowth) }}
                </span>
              </div>
              <p class="tnum text-lg font-semibold text-ink-gray-9">{{ money(lastMonth.revenue) }}</p>
              <p class="mt-1 text-xs text-ink-gray-6">{{ num(lastMonth.transactions) }} orders</p>
              <!-- Full-month MoM for disambiguation -->
              <p v-if="momGrowthFull !== null && lastMonthFull.revenue != null"
                 class="mt-2 border-t border-outline-gray-1 pt-2 text-xs text-ink-gray-6">
                Full {{ formatPeriod(lastMonthFull.period) }}: {{ money(lastMonthFull.revenue) }}
                <span :class="['ml-1 font-medium', deltaInk(momGrowthFull)]">
                  {{ deltaGlyph(momGrowthFull) }} {{ growthText(momGrowthFull) }}
                </span>
              </p>
            </div>
            <!-- Year ago (like-for-like, same-duration) -->
            <div class="p-4">
              <div class="mb-1 flex items-baseline justify-between gap-2">
                <p class="text-xs text-ink-gray-6">Year ago (like-for-like)</p>
                <span v-if="yoyGrowth !== null" :class="['shrink-0 text-xs font-bold', deltaInk(yoyGrowth)]">
                  {{ deltaGlyph(yoyGrowth) }} {{ growthText(yoyGrowth) }}
                </span>
              </div>
              <p class="tnum text-lg font-semibold text-ink-gray-9">{{ money(lastYearMonth.revenue) }}</p>
              <p class="mt-1 text-xs text-ink-gray-6">{{ num(lastYearMonth.transactions) }} orders</p>
              <!-- Full-month YoY for disambiguation -->
              <p v-if="yoyGrowthFull !== null && lastYearFull.revenue != null"
                 class="mt-2 border-t border-outline-gray-1 pt-2 text-xs text-ink-gray-6">
                Full {{ formatPeriod(lastYearFull.period) }}: {{ money(lastYearFull.revenue) }}
                <span :class="['ml-1 font-medium', deltaInk(yoyGrowthFull)]">
                  {{ deltaGlyph(yoyGrowthFull) }} {{ growthText(yoyGrowthFull) }}
                </span>
              </p>
            </div>
          </div>
        </div>

      </div><!-- /LEFT -->

      <!-- RIGHT: attention rail -->
      <div>
        <SectionHeader variant="caption" title="Needs Attention" :level="3" class="mb-3" />
        <div
          v-if="attentionItems.length"
          class="divide-y divide-outline-gray-1 overflow-hidden rounded-lg border border-outline-gray-1"
        >
          <div
            v-for="item in attentionItems"
            :key="item.metric"
            :class="['p-3', item.severity === 'low' ? 'bg-surface-green-1' : '']"
          >
            <div class="mb-1"><Badge v-bind="severityBadge(item.severity)" size="sm" /></div>
            <p class="text-sm font-semibold text-ink-gray-9">{{ item.metric }}</p>
            <p class="mt-0.5 text-xs leading-snug text-ink-gray-6">{{ item.why }}</p>
            <button
              v-if="item.drill"
              class="mt-1 text-xs font-medium text-ink-blue-2 hover:underline focus-visible:outline-none"
              @click="drillOpen(item.drill.title, item.drill.params)"
            >
              View details →
            </button>
          </div>
        </div>
        <div v-else class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-4 text-center text-xs text-ink-gray-6">
          No alerts for this period
        </div>
      </div><!-- /RIGHT -->

    </div><!-- /2-col -->

    <!-- Operational metric tiles: 4-up below main grid -->
    <div class="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
      <KpiCard
        variant="tile"
        label="Fulfillment Rate"
        :percent="fulfillmentRate"
        :severity="fulfillmentSeverity"
        :sublabel="fulfillmentSublabel"
        :clickable="true"
        @click="drillOpen('Unfulfilled Orders', { metric: 'unfulfilled_orders' })"
      />
      <KpiCard
        variant="tile"
        label="Days Sales Outstanding"
        :value="dso !== null ? `${dso.toFixed(0)} days` : undefined"
        :severity="dsoSeverity"
        :sublabel="receivablesSublabel"
        :clickable="true"
        @click="drillOpen('Receivables Detail', { metric: 'receivables' })"
      />
      <KpiCard
        variant="tile"
        label="30-Day Forecast"
        :value="salesForecast?.forecast_summary?.total_forecast != null
          ? money(salesForecast.forecast_summary.total_forecast as number)
          : undefined"
        :sublabel="forecastReliability
          ? `${forecastTrendLabel} · reliability: ${forecastReliability.level}`
          : forecastStaleDays > 0 ? `${forecastStaleDays}d stale` : undefined"
        :severity="forecastReliability?.level === 'Low' ? 'medium' : 'none'"
      />
      <KpiCard
        variant="tile"
        label="Avg Days Between Orders"
        :value="revenueMetrics.avg_days_between_orders != null
          ? `${(revenueMetrics.avg_days_between_orders as number).toFixed(1)} days`
          : undefined"
        :sublabel="avgDaysSubLabel"
      />
    </div>

  </div>

  <!-- ═══ Cash vs Credit ═══ -->
  <div v-if="activeTab === 'rev-payment'">
    <div class="mb-6 space-y-4">
      <TabBrief :brief="tabBriefs['rev-payment']" />
      <StatStrip :items="paymentStrip" :currency="props.currency" />
    </div>
    <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <section v-for="c in paymentCards" :key="c.title" class="min-w-0 rounded-lg border border-outline-gray-1 p-4" :class="c.tint">
        <h3 class="text-base font-semibold text-ink-gray-9">{{ c.title }} ({{ pct(c.share) }} of revenue)</h3>
        <div class="mt-3 h-2 overflow-hidden rounded-full bg-surface-gray-3" role="img" :aria-label="`${c.title} share of revenue ${pct(c.share)}`">
          <div class="h-full rounded-full" :class="c.fill" :style="{ width: `${Math.max(0, Math.min(100, c.share ?? 0))}%` }" />
        </div>
        <p class="tnum mt-3 text-2xl font-semibold text-ink-gray-9">{{ money(c.amount) }}</p>
        <p v-if="c.note" class="text-sm text-ink-gray-7">{{ c.note }}</p>
      </section>
    </div>

    <section v-if="bridge.length" class="mt-6 min-w-0 rounded-lg border border-outline-gray-1 bg-card">
      <h3 class="border-b border-outline-gray-1 px-4 py-3 text-base font-semibold text-ink-gray-9">Working capital bridge</h3>
      <div class="space-y-3 p-4">
        <div v-for="row in bridge" :key="row.label" class="grid grid-cols-1 gap-1 text-sm sm:grid-cols-[12rem_1fr] sm:items-center sm:gap-3">
          <span class="text-ink-gray-7">{{ row.label }}</span>
          <div class="flex min-w-0 flex-col gap-1">
            <div
              v-for="bar in row.bars"
              :key="bar.text"
              class="tnum flex h-7 min-w-max items-center whitespace-nowrap rounded px-2 text-xs text-ink-gray-9"
              :class="bar.fill"
              :style="{ width: `${Math.max(0, Math.min(100, bar.width))}%` }"
            >{{ bar.text }}</div>
          </div>
        </div>
      </div>
    </section>

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

    <TabActions class="mt-6" :actions="tabBriefs['rev-payment']?.actions" />
  </div>

  <!-- ═══ Sales Reps ═══ -->
  <div v-if="activeTab === 'rev-reps'">
    <div class="mb-6 space-y-4">
      <TabBrief :brief="tabBriefs['rev-reps']" />
      <StatStrip :items="repsStrip" :currency="props.currency" />
      <p v-if="(unattributedRevenue ?? 0) >= 1" class="text-xs text-ink-gray-6">
        + {{ money(unattributedRevenue) }} ({{ pct(salesReps.unattributed_revenue_pct as number) }}) invoiced with no reconciling Sales Team allocation
      </p>
    </div>
    <section v-if="repSegments.length" class="min-w-0 rounded-lg border border-outline-gray-1 bg-card p-4">
      <h3 class="text-base font-semibold text-ink-gray-9">Revenue concentration</h3>
      <div class="mt-3 flex h-10 overflow-hidden rounded" role="img" :aria-label="`Revenue share by rep: ${repSegments.map(s => `${s.name} ${pct(s.share)}`).join(', ')}`">
        <div v-for="s in repSegments" :key="s.name" class="h-full" :class="s.fill" :style="{ width: `${s.share}%` }" :title="`${s.name}: ${pct(s.share)}`" />
      </div>
      <ul class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-gray-7">
        <li v-for="s in repSegments" :key="s.name" class="flex items-center gap-1.5">
          <span class="size-2.5 shrink-0 rounded-sm" :class="s.fill" aria-hidden="true" />
          <span>{{ s.name }} ({{ pct(s.share) }}, {{ money(s.amount) }})</span>
        </li>
      </ul>
    </section>

    <div v-if="repSpotlights.length" class="my-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
      <section v-for="c in repSpotlights" :key="c.heading" class="min-w-0 rounded-lg border border-outline-gray-1" :class="c.tint">
        <p class="px-4 pt-3 text-xs font-medium uppercase tracking-wide text-ink-gray-7">{{ c.heading }}</p>
        <div class="p-4">
          <h3 class="text-base font-semibold text-ink-gray-9">{{ repName(c.rep) }}</h3>
          <p class="text-xs text-ink-gray-7">Rank {{ c.rep.rank }} · {{ num(c.rep.total_orders) }} orders · {{ num(c.rep.unique_customers) }} customers</p>
          <dl class="tnum mt-3 space-y-1 text-sm">
            <div class="flex justify-between gap-2"><dt class="text-ink-gray-7">Revenue</dt><dd class="font-medium text-ink-gray-9">{{ money(c.rep.total_revenue) }}</dd></div>
            <div class="flex justify-between gap-2"><dt class="text-ink-gray-7">Margin</dt><dd class="font-medium text-ink-gray-9">{{ pct(c.rep.margin_pct) }} ({{ money(c.rep.gross_profit) }} GP)</dd></div>
            <div class="flex justify-between gap-2"><dt class="text-ink-gray-7">Avg order</dt><dd class="font-medium text-ink-gray-9">{{ money(c.rep.avg_order_value) }}</dd></div>
          </dl>
        </div>
      </section>
    </div>

    <SectionHeader variant="caption" title="Sales Rep Leaderboard" :hint="windowLabel" :level="3" />
    <p v-if="marginBaseline !== null" class="mt-1 text-xs text-ink-gray-6">
      Margin badges are relative to the blended {{ pct(marginBaseline) }}: green at 1.2× or better, amber at 0.8× or better, red below.
    </p>
    <div class="mt-4 overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-surface-gray-1">
          <tr>
            <th scope="col" class="px-4 py-2 text-left text-ink-gray-7">Rank</th>
            <th scope="col" class="px-4 py-2 text-left text-ink-gray-7">Sales Person</th>
            <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Revenue</th>
            <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Gross Profit</th>
            <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Margin %</th>
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
            <td class="px-4 py-2 text-right text-ink-gray-7">{{ money(rep.gross_profit as number) }}</td>
            <td class="px-4 py-2 text-right">
              <Badge v-bind="severityBadge(groupMarginSeverity(rep.margin_pct as number))" :label="pct(rep.margin_pct as number)" size="sm" />
            </td>
            <td class="px-4 py-2 text-right text-ink-gray-7">{{ rep.total_orders }}</td>
            <td class="px-4 py-2 text-right text-ink-gray-7">{{ money(rep.avg_order_value as number) }}</td>
            <td class="px-4 py-2 text-right text-ink-gray-7">{{ rep.unique_customers }}</td>
            <td class="px-4 py-2 text-right text-ink-gray-7">{{ money(rep.total_incentives as number) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <TabActions class="mt-6" :actions="tabBriefs['rev-reps']?.actions" />
  </div>

  <!-- ═══ Margins ═══ -->
  <div v-if="activeTab === 'rev-margins'" class="space-y-6">
    <TabBrief :brief="tabBriefs['rev-margins']" />
    <StatStrip :items="marginsStrip" :currency="props.currency" />
    <p v-if="(margins.uncosted_items_excluded as number) > 0" class="text-sm text-ink-gray-6">
      {{ margins.uncosted_items_excluded }} item(s) still lack recorded cost ({{ money(margins.uncosted_revenue as number) }} revenue) and are held out of the rankings below.
    </p>


    <!-- Margin trend chart -->
    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
      <SectionHeader variant="caption" title="Margin Trend"
        hint="Bars are monthly net sales; the line is gross margin % on the right axis" :level="3">
        <template #actions><TrendingUp class="w-5 h-5 text-ink-gray-6" aria-hidden="true" /></template>
      </SectionHeader>
      <div v-if="marginTrendConfig" class="mt-4 h-64 sm:h-72 lg:h-80">
        <IntelligenceChart :config="marginTrendConfig" class="h-64 sm:h-72 lg:h-80" />
      </div>
      <p v-else class="mt-4 text-center py-12 text-ink-gray-6 text-sm">No margin history available.</p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Where profit comes from -->
      <div>
        <SectionHeader variant="caption" title="Where Profit Comes From"
          hint="Product groups ranked by share of total gross profit" :level="3" />
        <p v-if="marginBaseline !== null" class="mt-1 text-xs text-ink-gray-6">
          Margin badges are relative to the blended {{ pct(marginBaseline) }}: green at 1.2× or better, amber at 0.8× or better, red below.
        </p>
        <div class="mt-4 overflow-x-auto">
          <table class="w-full text-sm">
            <caption class="sr-only">Product groups by revenue, gross profit, share of total gross profit, and margin.</caption>
            <thead class="bg-surface-gray-1">
              <tr>
                <th scope="col" class="px-4 py-2 text-left text-ink-gray-7">Product Group</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Revenue</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Gross Profit</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">GP Share</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Margin</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="pg in marginGroups" :key="pg.item_group as string"
                class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
                <td class="px-4 py-2 text-ink-gray-8">
                  {{ pg.item_group || 'Uncategorized' }}
                  <Badge v-if="pg.item_group === ROOT_ITEM_GROUP" v-bind="severityBadge('medium')" label="taxonomy gap" size="sm" class="ml-2" />
                </td>
                <td class="px-4 py-2 text-right text-ink-gray-8 tnum">{{ money(pg.revenue as number) }}</td>
                <td class="px-4 py-2 text-right text-ink-gray-7 tnum">{{ money(pg.gross_profit as number) }}</td>
                <td class="px-4 py-2 text-right">
                  <div class="flex items-center justify-end gap-2">
                    <div class="h-1.5 w-16 rounded-full bg-surface-gray-3 overflow-hidden" aria-hidden="true">
                      <div class="h-full rounded-full bg-surface-gray-7" :style="{ width: Math.min(100, pg.gp_share as number) + '%' }"></div>
                    </div>
                    <span class="tnum text-ink-gray-7 w-12 text-right">{{ (pg.gp_share as number).toFixed(1) }}%</span>
                  </div>
                </td>
                <td class="px-4 py-2 text-right">
                  <Badge v-bind="severityBadge(groupMarginSeverity(pg.margin_pct as number))" :label="pct(pg.margin_pct as number)" size="sm" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Protect / Fix leaderboards -->
      <div class="space-y-6">
        <div>
          <SectionHeader variant="caption" title="Protect — Highest Margin"
            hint="Top sellers by margin; guard their pricing and supply" :level="3" />
          <div class="mt-2 space-y-2">
            <div v-for="item in (margins.top_margin_items as Record<string, unknown>[])?.slice(0, 8)" :key="item.item_code as string"
              class="flex justify-between items-center gap-2 text-sm bg-surface-gray-1 rounded p-2">
              <span class="truncate flex-1 text-ink-gray-8" :title="`${item.item_code} - ${item.item_name}`">{{ item.item_code }} — {{ item.item_name }}</span>
              <span class="tnum text-ink-gray-6 shrink-0">{{ money(item.revenue as number) }}</span>
              <span class="font-bold text-ink-gray-9 tnum shrink-0 w-14 text-right">{{ pct(item.margin_pct as number) }}</span>
            </div>
          </div>
        </div>
        <div>
          <SectionHeader variant="caption" title="Fix — Lowest Margin"
            hint="Sellers dragging the blended margin down" :level="3" />
          <div class="mt-2 space-y-2">
            <div v-for="item in (margins.low_margin_items as Record<string, unknown>[])?.slice(0, 8)" :key="item.item_code as string"
              class="flex justify-between items-center gap-2 text-sm bg-surface-gray-1 rounded p-2">
              <span class="truncate flex-1 text-ink-gray-8" :title="`${item.item_code} - ${item.item_name}`">{{ item.item_code }} — {{ item.item_name }}</span>
              <span class="tnum text-ink-gray-6 shrink-0">{{ money(item.revenue as number) }}</span>
              <Badge v-bind="severityBadge(scoreSeverity(item.margin_pct as number, { good: 30, warn: 15 }))" :label="pct(item.margin_pct as number)" size="sm" class="shrink-0" />
            </div>
          </div>
        </div>
      </div>
    </div>
    <TabActions :actions="tabBriefs['rev-margins']?.actions" />
  </div>

  <!-- ═══ Forecasts ═══ -->
  <div v-if="activeTab === 'rev-forecasts'">
    <div class="mb-6 space-y-4">
      <TabBrief :brief="tabBriefs['rev-forecasts']" />
      <StatStrip v-if="salesForecast" :items="forecastStrip" :currency="props.currency" />
    </div>
    <p v-if="forecastStaleDays > 1" class="mb-6 text-sm text-ink-gray-6">
      The latest invoice is {{ forecastStaleDays }} days old, so the projection starts today rather than the day after the last sale.
    </p>
    <div class="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
      <section v-if="modelHealth.length" class="min-w-0 rounded-lg border border-outline-gray-1 bg-card">
        <h3 class="border-b border-outline-gray-1 px-4 py-3 text-base font-semibold text-ink-gray-9">Model health</h3>
        <dl class="tnum divide-y divide-outline-gray-1 text-sm">
          <div v-for="row in modelHealth" :key="row.label" class="flex justify-between gap-3 px-4 py-2">
            <dt class="text-ink-gray-7">{{ row.label }}</dt>
            <dd class="font-medium text-ink-gray-9">{{ row.value }}</dd>
          </div>
        </dl>
      </section>
      <section v-if="dailyForecastConfig" class="min-w-0 rounded-lg border border-outline-gray-1 bg-card">
        <h3 class="border-b border-outline-gray-1 px-4 py-3 text-base font-semibold text-ink-gray-9">{{ forecastDays }}-day projection with confidence interval</h3>
        <div class="p-4"><IntelligenceChart :config="dailyForecastConfig" class="h-72" /></div>
      </section>
    </div>
    <div class="mb-6">
      <section v-if="scenarioRows.length" class="min-w-0 rounded-lg border border-outline-gray-1 bg-card">
        <h3 class="border-b border-outline-gray-1 px-4 py-3 text-base font-semibold text-ink-gray-9">{{ forecastDays }}-day revenue scenarios</h3>
        <ul class="divide-y divide-outline-gray-1">
          <li v-for="s in scenarioRows" :key="s.name" class="flex items-center justify-between gap-3 px-4 py-3" :class="s.tint">
            <div class="min-w-0">
              <p class="text-sm font-semibold text-ink-gray-9">{{ s.name }}</p>
              <p class="text-xs text-ink-gray-7">{{ s.note }}</p>
            </div>
            <p class="tnum text-lg font-semibold text-ink-gray-9">{{ money(s.amount) }}</p>
          </li>
        </ul>
      </section>
    </div>

    <!-- Revenue trend & projection -->
    <div class="mb-6 bg-surface-white rounded-lg border border-outline-gray-1 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <SectionHeader variant="caption" title="Revenue Trend & Projection"
          hint="Monthly revenue — the solid line is actual, the dashed line is the model’s projection" :level="3">
          <template #actions><TrendingUp class="w-5 h-5 text-ink-gray-6" aria-hidden="true" /></template>
        </SectionHeader>
        <Button variant="subtle" theme="gray" :loading="isTraining === 'sales'" :disabled="!!isTraining" @click="trainForecasts('sales')">
          Retrain model
        </Button>
      </div>
      <p v-if="trainingStatus" class="mt-2 text-sm" :class="trainingOk ? 'text-ink-gray-8' : 'text-ink-red-4'">{{ trainingStatus }}</p>
      <div v-if="revenueProjectionConfig" class="mt-4 h-64 sm:h-72 lg:h-80">
        <IntelligenceChart :config="revenueProjectionConfig" class="h-64 sm:h-72 lg:h-80" />
      </div>
      <div v-else-if="isLoadingDimensional" class="mt-4 text-center py-12 text-ink-gray-6">
        <Activity class="w-10 h-10 mx-auto opacity-40 mb-2 animate-pulse" aria-hidden="true" />
        <p class="text-sm">Loading revenue trend…</p>
      </div>
      <div v-else class="mt-4 text-center py-12 text-ink-gray-6">
        <Activity class="w-10 h-10 mx-auto opacity-40 mb-2" aria-hidden="true" />
        <p class="font-medium text-ink-gray-7">No forecast available yet</p>
        <p class="text-xs">Click “Retrain model” to generate projections</p>
      </div>
    </div>

    <!-- Dimensional forecast by product group -->
    <div class="mb-6">
      <div class="flex items-center justify-between mb-4">
        <SectionHeader variant="caption" title="Sales by Product Group (Historical + Forecast)" :level="3">
          <template #actions><BarChart3 class="w-5 h-5 text-ink-gray-6" aria-hidden="true" /></template>
        </SectionHeader>
        <Button variant="subtle" theme="gray" :loading="isLoadingDimensional" @click="loadDimensionalForecast(true)">Refresh</Button>
      </div>
      <div v-if="transposedProductGroupData.rows.length" class="overflow-x-auto bg-surface-white rounded-lg border border-outline-gray-1">
        <table class="w-full text-sm">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-2 text-left sticky left-0 bg-surface-gray-1 z-10 min-w-[180px] text-ink-gray-7">Product Group</th>
              <th v-for="period in transposedProductGroupData.periods" :key="period" scope="col"
                :class="['px-3 py-2 text-right min-w-[90px]', transposedProductGroupData.forecastPeriods.has(period) ? 'bg-surface-gray-2 text-ink-gray-7' : 'text-ink-gray-7']">
                <div>{{ formatPeriod(period) }}</div>
                <div class="text-xs font-normal text-ink-gray-6">{{ transposedProductGroupData.forecastPeriods.has(period) ? 'Forecast' : 'Actual' }}</div>
              </th>
              <th scope="col" class="px-4 py-2 text-right bg-surface-gray-2 min-w-[100px] text-ink-gray-7">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in paginatedTransposedProductGroups" :key="idx" class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
              <td class="px-4 py-2 font-medium sticky left-0 bg-surface-white z-10 truncate max-w-[180px] text-ink-gray-8" :title="row.product_group">{{ row.product_group }}</td>
              <td v-for="period in transposedProductGroupData.periods" :key="period"
                :class="['px-3 py-2 text-right', row.values[period]?.is_forecast ? 'bg-surface-gray-1 text-ink-gray-7' : 'text-ink-gray-8']">
                <div class="font-medium">{{ money(row.values[period]?.revenue) }}</div>
                <div class="text-xs text-ink-gray-6">{{ num(row.values[period]?.transactions) }} txns</div>
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
                :class="['px-3 py-2 text-right min-w-[90px]', transposedTerritoryData.forecastPeriods.has(period) ? 'bg-surface-gray-2 text-ink-gray-7' : 'text-ink-gray-7']">
                <div>{{ formatPeriod(period) }}</div>
                <div class="text-xs font-normal text-ink-gray-6">{{ transposedTerritoryData.forecastPeriods.has(period) ? 'Forecast' : 'Actual' }}</div>
              </th>
              <th scope="col" class="px-4 py-2 text-right bg-surface-gray-2 min-w-[100px] text-ink-gray-7">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in paginatedTransposedTerritories" :key="idx" class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
              <td class="px-4 py-2 font-medium sticky left-0 bg-surface-white z-10 truncate max-w-[180px] text-ink-gray-8" :title="row.territory">{{ row.territory }}</td>
              <td v-for="period in transposedTerritoryData.periods" :key="period"
                :class="['px-3 py-2 text-right', row.values[period]?.is_forecast ? 'bg-surface-gray-1 text-ink-gray-7' : 'text-ink-gray-8']">
                <div class="font-medium">{{ money(row.values[period]?.revenue) }}</div>
                <div class="text-xs text-ink-gray-6">{{ num(row.values[period]?.transactions) }} txns</div>
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

    <TabActions class="mt-6" :actions="tabBriefs['rev-forecasts']?.actions" />
  </div>

  <!-- ═══ Attribution ═══ -->
  <div v-if="activeTab === 'rev-sources'" class="space-y-6">
    <TabBrief :brief="sourcesBrief" />
    <StatStrip :items="sourcesStrip" :currency="props.currency" />

    <!-- Revenue by lead source: chart + visible table -->
    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
      <SectionHeader variant="caption" title="Revenue by Lead Source"
        hint="Revenue and gross profit attributed through the lead → invoice chain" :level="3" />
      <div v-if="attributionConfig" class="mt-4 h-56 sm:h-72 lg:h-80">
        <IntelligenceChart :config="attributionConfig" class="h-56 sm:h-72 lg:h-80" />
      </div>
      <div v-if="attributionRows.length" class="mt-6 overflow-x-auto">
        <table class="w-full text-sm">
          <caption class="sr-only">Revenue, share, gross profit, margin, orders and average order value by lead source</caption>
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-2 text-left text-ink-gray-7">Source</th>
              <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Revenue</th>
              <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Share</th>
              <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Gross Profit</th>
              <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Margin %</th>
              <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Orders</th>
              <th scope="col" class="px-4 py-2 text-right text-ink-gray-7">Avg / Order</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in attributionRows" :key="row.source"
              class="border-b border-outline-gray-1 cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
              :class="row.source === 'Unattributed' ? 'text-ink-gray-5 italic' : ''"
              tabindex="0"
              role="button"
              @click="drillSource(row.source)"
              @keydown.enter="drillSource(row.source)"
              @keydown.space.prevent="drillSource(row.source)">
              <td class="px-4 py-2 text-left font-medium text-ink-gray-8">{{ row.source }}</td>
              <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ money(row.revenue) }}</td>
              <td class="px-4 py-2 text-right text-ink-gray-6">{{ pct(row.share) }}</td>
              <td class="px-4 py-2 text-right text-ink-gray-7">{{ money(row.gross_profit) }}</td>
              <td class="px-4 py-2 text-right">
                <Badge v-bind="severityBadge(groupMarginSeverity(row.margin_pct))" :label="pct(row.margin_pct)" size="sm" />
              </td>
              <td class="px-4 py-2 text-right text-ink-gray-7">{{ num(row.order_count) }}</td>
              <td class="px-4 py-2 text-right text-ink-gray-7">{{ row.order_count > 0 ? money(row.aov) : NO_VALUE }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="mt-4 text-center py-8 text-ink-gray-6">
        <Target class="w-8 h-8 mx-auto mb-2 opacity-40" aria-hidden="true" />
        <p>No source attribution data available</p>
      </div>
    </div>

    <!-- Quotation funnel -->
    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
      <SectionHeader variant="caption" title="Quotation Funnel"
        hint="Quote-to-order conversion and why deals are lost" :level="3" />
      <div v-if="quotationAnalytics" class="mt-4 grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <KpiCard label="Total Quotes" :value="num(quotationAnalytics.total as number)" :clickable="true"
          @click="drillOpen('Quotations', { metric: 'quotations', bucket: 'all', period: props.dateFilter })" />
        <KpiCard label="Won" :value="num(quotationAnalytics.won as number)" :clickable="true"
          @click="drillOpen('Quotations won', { metric: 'quotations', bucket: 'won', period: props.dateFilter })" />
        <KpiCard label="Pending" :value="num(quotationAnalytics.pending as number)" :clickable="true"
          @click="drillOpen('Quotations pending', { metric: 'quotations', bucket: 'pending', period: props.dateFilter })" />
        <KpiCard label="Lost" :value="num(quotationAnalytics.lost as number)" severity="high" :clickable="true"
          @click="drillOpen('Quotations lost', { metric: 'quotations', bucket: 'lost', period: props.dateFilter })" />
        <KpiCard label="Conversion" :percent="quotationAnalytics.conversion_rate as number" />
      </div>
      <div v-if="lostReasonsData.length" class="space-y-4">
        <SectionHeader variant="caption" title="Why quotes are lost" :level="4" />
        <!-- Ranked bar list, largest reason first -->
        <div class="space-y-3">
          <div v-for="row in lostReasonsData" :key="row.reason" class="space-y-1">
            <!-- Row header: reason label, count, percentage -->
            <div class="flex justify-between items-baseline">
              <span class="font-medium text-ink-gray-8">{{ row.reason }}</span>
              <span class="text-ink-gray-7 text-sm">
                {{ formatCount(row.count) }}
                <span class="text-ink-gray-6">{{ formatPercent(row.percentage) }}</span>
              </span>
            </div>
            <!--
              Share of total lost quotes. Fill comes from a whole token class,
              not an inline `themeColor()` hex: `themeColor` exists because
              ECharts cannot resolve CSS custom properties, and using it on DOM
              freezes the colour at render so a light/dark switch no longer
              reaches it. Same shape as `WaterfallRows`, which is the precedent.
            -->
            <div
              class="h-6 overflow-hidden rounded-full bg-surface-gray-2"
              role="img"
              :aria-label="`${row.reason}: ${formatCount(row.count)} lost quotes`"
            >
              <div
                class="h-full rounded-full bg-muted-fill"
                :style="{ width: `${Math.max(0, Math.min(100, row.percentage))}%` }"
              />
            </div>
          </div>
        </div>
        <table class="sr-only">
          <caption>Quotation lost reasons by count</caption>
          <thead><tr><th scope="col">Reason</th><th scope="col">Count</th></tr></thead>
          <tbody>
            <tr v-for="r in lostReasonsData" :key="r.reason">
              <th scope="row">{{ r.reason }}</th>
              <td>{{ formatCount(r.count) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="quotationAnalytics" class="text-center py-8 text-ink-gray-6">
        <p>No lost reason data available</p>
      </div>
    </div>
  </div>
</template>
