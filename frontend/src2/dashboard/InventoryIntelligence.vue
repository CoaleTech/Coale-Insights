<script setup lang="ts">
defineOptions({ name: 'InventoryIntelligence' })
import { Breadcrumbs, Button, Badge, Tabs, Spinner } from 'frappe-ui'
import { apiCall, ignoreRejection } from '../helpers/api'
import {
  RefreshCcw, Package, Warehouse, ArrowRightLeft, Clock,
  TrendingUp, TrendingDown, Activity, BarChart3,
  PieChart, ShoppingCart, Truck, DollarSign, Archive, Boxes,
  ArrowRight, Layers,
} from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { createToast } from '../helpers/toasts'
import {
  scoreSeverity, severityBadge, severityFill, severityAria,
  ragSeverity, deltaInk, deltaGlyph, prioritySeverity, type Severity,
} from '../utils/status'
import { formatDate, formatDateTime, formatCount, formatMoney, formatPercent, asNumber, NO_VALUE } from '../utils/format'
import { isCustomRange } from '../utils/dateRangePresets'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'
import KpiCard from '../intelligence/components/KpiCard.vue'
import SectionHeader from '../intelligence/components/SectionHeader.vue'
import TabBrief, { type Brief } from '../intelligence/components/TabBrief.vue'
import TabActions from '../intelligence/components/TabActions.vue'
import StatStrip, { type StatItem } from '../intelligence/components/StatStrip.vue'
import IntelligenceDashboardShell from '../intelligence/components/IntelligenceDashboardShell.vue'
import { useIntelligenceDashboard } from '../intelligence/composables/useIntelligenceDashboard'

const router = useRouter()

const INV_ENDPOINT = 'insights.api.ml.inventory.get_inventory_detail'
const drillDown = useDrillDown()

const dateFilter = ref('12m')
const lastUpdated = ref('')

// Training state
const isTraining = ref(false)
const trainingStatus = ref('')
const trainingSuccess = ref(false)

// Tab management
const tabIndex = ref(0)

const tabDefs = [
  { label: 'Stock Overview' },
  { label: 'Turnover' },
  { label: 'ABC/XYZ' },
  { label: 'Itemwise BE' },
  { label: 'Aging (FIFO)' },
  { label: 'Warehouses & Transfers' },
  { label: 'Procurement' },
]

const tabIds = ['overview', 'turnover', 'abc-xyz', 'itemwise-be', 'aging', 'warehouses', 'procurement']
const activeTab = computed(() => tabIds[tabIndex.value] ?? 'overview')

const tabBriefs = computed(() => inventoryData.value?.tab_briefs ?? {})
const itemwiseBeBrief = computed(() => itemwiseBeData.value?.brief as Brief | undefined)
const turnoverStrip = computed<StatItem[]>(() => [
  { label: `ITR (${windowText.value})`, value: asNumber(turnoverAnalysis.value.overall_turnover_ratio), unit: '×', sublabel: 'COGS ÷ Avg Inventory' },
  { label: `Days Sales Inventory (${windowText.value})`, value: asNumber(turnoverAnalysis.value.days_sales_inventory), unit: ' days', sublabel: '365 ÷ ITR' },
  { label: `Gross Margin (${windowText.value})`, percent: asNumber(turnoverAnalysis.value.gross_margin_pct), sublabel: '(Revenue − COGS) ÷ Revenue' },
  { label: 'Inventory Value', amount: asNumber(turnoverAnalysis.value.current_inventory_value), sublabel: 'On-hand at period end' },
])

interface TurnoverRow {
  group: string
  sales?: number
  cogs?: number
  stock?: number
  itr?: number
  dsi?: number
  gm?: number
}
/** Gross margin is (sales - COGS) / sales on the group's own payload figures. */
const groupGm = (sales?: number, cogs?: number): number | undefined =>
  sales && cogs !== undefined ? Math.round(((sales - cogs) / sales) * 1000) / 10 : undefined
const turnoverRows = computed<TurnoverRow[]>(() =>
  ((turnoverAnalysis.value.by_product_group as Record<string, unknown>[]) ?? []).map((g) => {
    const sales = asNumber(g.sales_12m)
    const cogs = asNumber(g.cogs_12m)
    return { group: String(g.item_group), sales, cogs, stock: asNumber(g.current_stock_value), itr: asNumber(g.turnover_ratio), dsi: asNumber(g.dsi), gm: groupGm(sales, cogs) }
  }),
)
const turnoverTotal = computed<TurnoverRow>(() => ({
  group: 'Total',
  sales: asNumber(turnoverAnalysis.value.revenue_12m),
  cogs: asNumber(turnoverAnalysis.value.cogs_12m),
  stock: asNumber(turnoverAnalysis.value.current_inventory_value),
  itr: asNumber(turnoverAnalysis.value.overall_turnover_ratio),
  dsi: asNumber(turnoverAnalysis.value.days_sales_inventory),
  gm: asNumber(turnoverAnalysis.value.gross_margin_pct),
}))

// Itemwise BE state (supplementary fetch — not the primary payload)
const itemwiseBeData = ref<Record<string, unknown> | null>(null)
const itemwiseBeLoading = ref(false)
const itemwiseBeError = ref<string | null>(null)

/** Shape of the inventory_intelligence endpoint payload. */
interface InventoryIntelligenceData {
  base_currency?: string
  stock_overview?: Record<string, unknown>
  turnover_analysis?: Record<string, unknown>
  aging_analysis?: Record<string, unknown>
  warehouse_analysis?: Record<string, unknown>
  transfer_recommendations?: unknown[]
  dead_stock?: Record<string, unknown>
  procurement_insights?: Record<string, unknown>
  abc_xyz?: AbcXyzData
  demand_planning?: Record<string, unknown> | null
  generated_at?: string
  tab_briefs?: Record<string, Brief>
  [k: string]: unknown
}

const {
  data: inventoryData,
  loading,
  refreshing,
  error,
  isPermissionError,
  warming,
  notImplemented,
  notImplementedMessage,
  hasData,
  reload,
  retry,
} = useIntelligenceDashboard<InventoryIntelligenceData>({
  url: 'insights.api.ml.inventory_intelligence',
  params: computed(() => ({ date_filter: dateFilter.value })),
  cache: 'inventory-intelligence',
})

// Stamp lastUpdated when the primary payload lands successfully.
watch(inventoryData, (payload) => {
  if (payload) lastUpdated.value = new Date().toISOString()
})

// Train/refresh inventory intelligence
async function trainInventoryIntelligence() {
  isTraining.value = true
  trainingStatus.value = ''

  try {
    const result = await apiCall<Record<string, unknown>>('insights.api.ml.train_inventory_intelligence', {
      date_filter: dateFilter.value,
    })
    trainingStatus.value = 'Analysis complete'
    trainingSuccess.value = true
    const stockOverview = (result.stock_overview as Record<string, unknown>) || {}
    createToast({
      title: 'Analysis Complete',
      message: `Analyzed ${formatCount(stockOverview.total_skus as number)} SKUs across ${formatCount(stockOverview.warehouse_count as number)} warehouses`,
      variant: 'success',
    })
    // Refetch the primary payload through the composable so the UI sees the
    // freshly-trained numbers. Writing back into a now-computed `data` is no
    // longer an option.
    ignoreRejection(reload())
  } catch (e: unknown) {
    trainingStatus.value = `Analysis error: ${(e instanceof Error ? e.message : String(e))}`
    trainingSuccess.value = false
    createToast({
      title: 'Analysis Error',
      message: (e instanceof Error ? e.message : String(e)) || 'Analysis failed',
      variant: 'error',
    })
  } finally {
    isTraining.value = false
  }
}

// Train ABC/XYZ Classification
const isTrainingAbcXyz = ref(false)
async function trainAbcXyz() {
  isTrainingAbcXyz.value = true

  try {
    const result = await apiCall('insights.api.ml.inventory_classification', {
      refresh: true,
      date_filter: dateFilter.value,
    })
    createToast({
      title: 'ABC/XYZ Classification Complete',
      message: `Classified ${formatCount((result as Record<string, unknown>)?.total_items as number)} items`,
      variant: 'success',
    })
    ignoreRejection(reload())
  } catch (e: unknown) {
    createToast({
      title: 'Classification Error',
      message: (e instanceof Error ? e.message : String(e)) || 'Classification failed',
      variant: 'error',
    })
  } finally {
    isTrainingAbcXyz.value = false
  }
}

/** Counts per ABC/XYZ class for the summary cards. */
interface AbcXyzSummary {
  a_count?: number; b_count?: number; c_count?: number
  x_count?: number; y_count?: number; z_count?: number
}
/** Shape of the abc_xyz sub-object returned by inventory_intelligence. */
interface AbcXyzData {
  summary?: AbcXyzSummary
  abc_summary?: unknown[]
  top_items?: unknown[]
  matrix?: Record<string, unknown>[]
  total_items?: number
  classification_date?: string
  [k: string]: unknown
}

// Computed values
const stockOverview = computed(() => (inventoryData.value?.stock_overview as Record<string, unknown>) || {})
const turnoverAnalysis = computed(() => (inventoryData.value?.turnover_analysis as Record<string, unknown>) || {})
const agingAnalysis = computed(() => (inventoryData.value?.aging_analysis as Record<string, unknown>) || {})
const warehouseAnalysis = computed(() => (inventoryData.value?.warehouse_analysis as Record<string, unknown>) || {})
const transferRecommendations = computed(() => (inventoryData.value?.transfer_recommendations as unknown[]) || [])
const deadStock = computed(() => (inventoryData.value?.dead_stock as Record<string, unknown>) || {})
const procurementInsights = computed(() => (inventoryData.value?.procurement_insights as Record<string, unknown>) || {})
const abcXyz = computed(() => (inventoryData.value?.abc_xyz as AbcXyzData | null) ?? null)
/** Share of total classified sales value per ABC class, from abc_summary. */
const abcShare = computed(() => {
  const rows = (abcXyz.value?.abc_summary ?? []) as { class?: string; total_value?: number }[]
  const total = rows.reduce((s, r) => s + (r.total_value || 0), 0)
  const out: Record<string, string> = {}
  for (const r of rows) out[r.class ?? ''] = total > 0 ? `${formatPercent(((r.total_value || 0) / total) * 100)} of sales` : NO_VALUE
  return out
})
/** ABC rows by XYZ columns for the management grid; each cell is the payload `matrix` row for that class. */
const abcGrid = computed(() => {
  const m = (abcXyz.value?.matrix ?? []) as { class?: string; item_count?: number; total_value?: number; stock_value?: number }[]
  return ['A', 'B', 'C'].map(a => ({
    abc: a,
    cells: ['X', 'Y', 'Z'].map(x => ({ cls: a + x, row: m.find(r => r.class === a + x) })),
  }))
})
/** Pareto concentration: each ABC class's share of classified sales value, with its share of items. */
const abcPareto = computed(() => {
  const rows = (abcXyz.value?.abc_summary ?? []) as { class?: string; item_count?: number; total_value?: number }[]
  const total = rows.reduce((s, r) => s + (Number(r.total_value) || 0), 0)
  const items = rows.reduce((s, r) => s + (Number(r.item_count) || 0), 0)
  return rows.map(r => ({
    cls: r.class ?? '',
    value: Number(r.total_value) || 0,
    items: Number(r.item_count) || 0,
    pct: total > 0 ? ((Number(r.total_value) || 0) / total) * 100 : null,
    itemPct: items > 0 ? ((Number(r.item_count) || 0) / items) * 100 : null,
  }))
})
const demandPlanning = computed(() => (inventoryData.value?.demand_planning as Record<string, unknown> | null) ?? null)

// Max value for age bucket bars (avoids inline template Math.max)
const maxAgeBucketValue = computed(() => {
  const buckets = agingAnalysis.value.age_buckets as Record<string, { value: number }> | undefined
  if (!buckets) return 1
  return Math.max(...Object.values(buckets).map(b => b.value || 1))
})

// Format helpers
const baseCurrency = computed(() => inventoryData.value?.base_currency)
const money = (value: number | null | undefined) => formatMoney(value, baseCurrency.value)

// Windowed sections follow the selected filter. Dead stock (180d no-sale) and
// aging buckets are fixed by definition and keep their own labels.
const windowText = computed(() =>
  isCustomRange(dateFilter.value) ? 'selected range' : dateFilter.value === 'all' ? 'all time' : dateFilter.value,
)

function openDetail(title: string, metric: string, extra: Record<string, unknown> = {}) {
  drillDown.open(INV_ENDPOINT, title, { metric, date_filter: dateFilter.value, ...extra })
}
function openWarehouse(wh: unknown) {
  const name = (wh as Record<string, unknown>).warehouse as string
  openDetail(`${name} Stock`, 'warehouse_stock', { warehouse: name })
}

/** `${value}${suffix}` only for a real number; null renders NO_VALUE, never a fake 0. */
function suffixed(value: unknown, suffix: string): string {
  const n = asNumber(value)
  return n === undefined ? NO_VALUE : `${n}${suffix}`
}

function coveragePct(item: unknown): number | undefined {
  const c = asNumber((item as Record<string, unknown>).coverage)
  return c === undefined ? undefined : c * 100
}
function coverageInk(item: unknown): string {
  const c = asNumber((item as Record<string, unknown>).coverage)
  return c === undefined ? 'text-ink-gray-6' : deltaInk(c >= 1 ? 1 : -1, { higherIsBetter: true })
}

const reorderRows = computed(() => (procurementInsights.value.reorder_needed as Record<string, unknown>[] | undefined) ?? [])
const reorderTotal = computed(() => asNumber(procurementInsights.value.reorder_count))
const pendingRows = computed(() => (procurementInsights.value.pending_orders as Record<string, unknown>[] | undefined) ?? [])
const pendingTotal = computed(() => asNumber(procurementInsights.value.pending_orders_count))
const demandSummary = computed(() => demandPlanning.value?.summary as Record<string, unknown> | undefined)
const demandAlerts = computed(() => (demandPlanning.value?.reorder_alerts as Record<string, unknown>[] | undefined) ?? [])
const demandTotal = computed(() => asNumber(demandSummary.value?.total_items))

// --- overview tab: hero chart & attention rail ---------------------------------

/** Groups with positive stock, ordered by value (from the payload). */
const heroGroups = computed(
  () => (stockOverview.value.by_item_group as Record<string, unknown>[] | undefined) ?? []
)
const heroTotalValue = computed(() =>
  heroGroups.value.reduce((s, g) => s + (g.stock_value as number || 0), 0)
)
const heroMaxValue = computed(() =>
  Math.max(...heroGroups.value.map(g => g.stock_value as number || 0), 1)
)
/** Dominant group's share of total on-hand value (0–100). */
const heroDominantPct = computed(() => {
  if (!heroTotalValue.value || !heroGroups.value[0]) return 0
  return Math.round((heroGroups.value[0].stock_value as number || 0) / heroTotalValue.value * 100)
})
function heroBarPct(value: number): number {
  return heroMaxValue.value > 0 ? Math.round((value / heroMaxValue.value) * 100) : 0
}
const heroInStockCount = computed(() =>
  heroGroups.value.reduce((s, g) => s + (g.item_count as number || 0), 0)
)
const heroOosText = computed(() => {
  const oos = asNumber(stockOverview.value.out_of_stock_count)
  const total = asNumber(stockOverview.value.total_skus)
  if (!oos || !total) return ''
  return `${oos} SKU${oos === 1 ? '' : 's'} (${Math.round(oos / total * 100)}%) out of stock, excluded from chart`
})

/** Sublabel for OOS KpiCard: e.g. '56% of SKUs'. */
const oosSubLabel = computed((): string | undefined => {
  const oos = asNumber(stockOverview.value.out_of_stock_count)
  const total = asNumber(stockOverview.value.total_skus)
  if (oos === undefined || !total) return undefined
  return `${Math.round(oos / total * 100)}% of SKUs`
})

/** Reorder sublabel: denominator for the attention-rail item. */
const reorderSubLabel = computed((): string | undefined => {
  const total = asNumber(stockOverview.value.total_skus)
  return total ? `of ${formatCount(total)} active SKUs` : undefined
})

const agingBuckets = computed(
  () => agingAnalysis.value.age_buckets as Record<string, { value: number; count: number }> | undefined
)
const hasAgingData = computed(() => !!agingBuckets.value)

const agingRiskValue = computed(() => {
  const b = agingBuckets.value
  if (!b) return 0
  return (b['181-365 days']?.value ?? 0) + (b['365+ days']?.value ?? 0)
})
const agingRiskCount = computed(() => {
  const b = agingBuckets.value
  if (!b) return 0
  return (b['181-365 days']?.count ?? 0) + (b['365+ days']?.count ?? 0)
})

/** Portfolio split by age zone (0-180d, 181-365d, 365+d); shares are of the FIFO snapshot total. */
const agingZones = computed(() => {
  const b = agingBuckets.value
  if (!b) return []
  const sum = (names: string[], k: 'value' | 'count') => names.reduce((s, n) => s + (Number(b[n]?.[k]) || 0), 0)
  const zones = [
    { label: 'Safe stock (0-180d)', names: ['0-30 days', '31-60 days', '61-90 days', '91-180 days'], fill: 'bg-pos-fill' },
    { label: 'At risk (181-365d)', names: ['181-365 days'], fill: 'bg-warn-fill' },
    { label: 'Write-off (365+d)', names: ['365+ days'], fill: 'bg-neg-fill' },
  ].map(z => ({ label: z.label, fill: z.fill, value: sum(z.names, 'value'), count: sum(z.names, 'count') }))
  const total = zones.reduce((s, z) => s + z.value, 0)
  return zones.map(z => ({ ...z, pct: total > 0 ? (z.value / total) * 100 : null, total }))
})

/** Proportional segments for the C+aging heat-strip in the hero caption. */
const agingHeatSegments = computed(() => {
  const b = agingBuckets.value
  if (!b) return []
  const names = ['31-60 days', '61-90 days', '91-180 days', '181-365 days', '365+ days'] as const
  const segs = names
    .map(name => ({ name, value: b[name]?.value ?? 0, count: b[name]?.count ?? 0 }))
    .filter(s => s.value > 0)
  const total = segs.reduce((s, sg) => s + sg.value, 0)
  if (!total) return []
  return segs.map(s => ({ ...s, fill: severityFill(ageBucketSeverity(s.name)), pct: s.value / total }))
})

/** One-line OOS description for the attention rail. */
const oosDescription = computed(() => {
  const oos = asNumber(stockOverview.value.out_of_stock_count)
  const total = asNumber(stockOverview.value.total_skus)
  if (oos === undefined) return ''
  const pct = total ? Math.round(oos / total * 100) : 0
  const top3 = reorderRows.value
    .filter(r => (r.current_stock as number) <= 0)
    .slice(0, 3)
    .map(r => String(r.item_name ?? r.item_code))
    .join(', ')
  return `${pct}% of active base has zero on-hand${top3 ? `. Top demand: ${top3}` : ''}.`
})

/** Top item with positive stock below 14d threshold (for low-stock rail entry). */
const lowStockTop = computed(
  () => reorderRows.value.find(r => (r.current_stock as number) > 0)
)

/** Navigate to a tab by its ID string. */
function goToTab(id: string) {
  const idx = tabIds.indexOf(id)
  if (idx >= 0) tabIndex.value = idx
}


// Age bucket: severity by bucket name
function ageBucketSeverity(name: string): Severity {
  if (name.includes('0-30')) return 'none'
  if (name.includes('31-60')) return 'low'
  if (name.includes('61-90')) return 'medium'
  if (name.includes('91-180')) return 'high'
  return 'critical'
}

// Load itemwise break-even data
async function loadItemwiseBe() {
  if (itemwiseBeData.value) return

  itemwiseBeLoading.value = true
  itemwiseBeError.value = null

  try {
    const result = await apiCall('insights.api.ml.inventory.item_breakeven', {
      period: 'Quarterly',
    })
    itemwiseBeData.value = result as Record<string, unknown>
  } catch (e: unknown) {
    itemwiseBeError.value = (e instanceof Error ? e.message : String(e)) || 'Failed to load itemwise break-even data'
  } finally {
    itemwiseBeLoading.value = false
  }
}

// Watch tab changes to lazy-load itemwise BE
watch(activeTab, (tab) => {
  if (tab === 'itemwise-be') {
    loadItemwiseBe()
  }
})

// Breadcrumbs
const breadcrumbs = [
  { label: 'Insights', href: '/insights' },
  { label: 'Inventory Intelligence' },
]

// Chat context for AI insights
const chatContext = computed(() => ({
  stockOverview: inventoryData.value?.stock_overview || {},
  turnoverAnalysis: inventoryData.value?.turnover_analysis || {},
  abcXyzAnalysis: inventoryData.value?.abc_xyz || {},
  agingAnalysis: inventoryData.value?.aging_analysis || {},
  warehouseAnalysis: inventoryData.value?.warehouse_analysis || {},
  deadStock: inventoryData.value?.dead_stock || {},
  transferRecommendations: inventoryData.value?.transfer_recommendations || [],
  procurementInsights: inventoryData.value?.procurement_insights || {},
  demandPlanning: inventoryData.value?.demand_planning || {},
  activeTab: activeTab.value,
  isLoading: loading.value,
}))

// Handle navigation to other dashboards from chat suggestions
function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    'Sales': '/sales-intelligence',
    'Risk': '/risk-intelligence',
    'Procurement': '/procurement-intelligence',
    'Financial': '/financial-intelligence',
    'Customer': '/customer-intelligence',
    'Inventory': '/inventory-intelligence',
  }
  if (routes[target]) {
    router.push(routes[target])
  }
}
</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <div class="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between px-6 py-4 bg-surface-white border-b border-outline-gray-1">
      <div>
        <Breadcrumbs :items="breadcrumbs" />
        <h1 class="text-2xl font-bold text-ink-gray-9 mt-1">Inventory Intelligence</h1>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <span v-if="lastUpdated" class="text-sm text-ink-gray-6">
          Updated: {{ formatDateTime(lastUpdated) }}
        </span>
        <IntelligenceDateFilter v-model="dateFilter" />
        <Button
          variant="subtle"
          :loading="isTraining"
          @click="trainInventoryIntelligence"
        >
          <template #prefix><Activity class="w-4 h-4" /></template>
          {{ isTraining ? 'Retraining...' : 'Retrain Model' }}
        </Button>
        <Button
          variant="solid"
          :loading="refreshing"
          @click="reload"
          aria-label="Refresh inventory data"
        >
          <template #prefix><RefreshCcw class="w-4 h-4" /></template>
          Refresh Data
        </Button>
      </div>
    </div>

    <!-- Training Status -->
    <div v-if="trainingStatus" class="mx-6 mt-4">
      <div class="px-4 py-2 rounded-lg text-sm border border-outline-gray-1 flex items-center gap-2 bg-surface-white">
        <Badge v-bind="severityBadge(trainingSuccess ? 'none' : 'high')"
               :label="trainingSuccess ? 'Success' : 'Error'" size="sm" />
        <span class="text-ink-gray-7">{{ trainingStatus }}</span>
      </div>
    </div>

    <IntelligenceDashboardShell
      :loading="loading"
      :refreshing="refreshing"
      :error="error"
      :is-permission-error="isPermissionError"
      :has-data="hasData"
      :warming="warming"
      :not-implemented="notImplemented"
      :not-implemented-message="notImplementedMessage"
      subject="inventory data"
      permission-hint="Ask an administrator for inventory read access."
      :kpi-count="0"
      @retry="retry"
    >
    <!-- Main Content -->
    <div class="flex-1 overflow-auto p-6">
      <!-- Tabs -->
      <div class="mx-6">
        <Tabs v-model="tabIndex" :tabs="tabDefs" />
      </div>

      <!-- Tab Content -->
      <div class="flex-1 p-6">
          <!-- Stock Overview Tab — Variant C: Hero + Attention Rail -->
          <div v-if="activeTab === 'overview'">
            <div class="grid lg:grid-cols-3 gap-5">

              <!-- Left 2/3: hero chart + compact KPI stat grid -->
              <div class="lg:col-span-2 flex flex-col gap-4">

                <!-- Hero panel: stock-by-group horizontal bar chart -->
                <div class="bg-surface-white border border-outline-gray-1 rounded-lg overflow-hidden">
                  <div class="px-5 pt-5 pb-3">
                    <p class="text-sm font-semibold text-ink-gray-9">Stock Value by Item Group — On-Hand Inventory</p>
                    <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-gray-6">
                      <span>{{ heroInStockCount }} items in-stock · {{ money(asNumber(stockOverview.total_value)) }} · {{ baseCurrency ?? NO_VALUE }}</span>
                      <span v-if="heroOosText" class="text-ink-red-4">{{ heroOosText }}</span>
                      <!-- C+aging: heat-strip per note.md recommendation -->
                      <span v-if="hasAgingData && agingHeatSegments.length" class="flex items-center gap-1 ml-auto" aria-hidden="true">
                        <span class="text-xs text-ink-gray-6">Age risk:</span>
                        <span class="inline-flex h-1.5 w-10 rounded-full overflow-hidden">
                          <span
                            v-for="seg in agingHeatSegments"
                            :key="seg.name"
                            :class="seg.fill"
                            :style="{ width: `${Math.round(seg.pct * 100)}%` }"
                          ></span>
                        </span>
                      </span>
                    </div>
                  </div>
                  <!-- Ranked horizontal bar list (Rule 2: share-of-total → ranked bar) -->
                  <div class="px-5 pb-4 space-y-2" role="list" aria-label="Stock value by item group">
                    <div
                      v-for="(group, idx) in heroGroups"
                      :key="idx"
                      class="flex items-center gap-3"
                      role="listitem"
                    >
                      <div class="w-40 shrink-0 text-right">
                        <p class="text-xs font-medium text-ink-gray-8 truncate" :title="String(group.item_group ?? '')">{{ group.item_group }}</p>
                        <p class="text-xs text-ink-gray-6">{{ formatCount(group.item_count as number) }} item{{ (group.item_count as number) === 1 ? '' : 's' }} · {{ formatCount(group.total_qty as number) }} qty</p>
                      </div>
                      <div
                        class="relative flex-1 h-7 bg-surface-gray-1 rounded overflow-hidden"
                        role="img"
                        :aria-label="`${String(group.item_group)}: ${money(group.stock_value as number)}`"
                      >
                        <div
                          class="h-full bg-surface-blue-3 rounded transition-[width] duration-300 motion-reduce:transition-none"
                          :style="{ width: `${heroBarPct(group.stock_value as number)}%` }"
                        ></div>
                        <span
                          v-if="idx === 0 && heroDominantPct > 0"
                          class="absolute right-2 top-1/2 -translate-y-1/2 text-xs font-semibold text-ink-gray-9"
                        >{{ heroDominantPct }}% of portfolio</span>
                      </div>
                      <div class="w-20 shrink-0 text-right text-xs font-semibold text-ink-gray-9 tabular-nums">{{ money(group.stock_value as number) }}</div>
                    </div>
                    <p v-if="!heroGroups.length" class="text-sm text-ink-gray-6 py-4 text-center">No in-stock items</p>
                  </div>
                  <div class="px-5 pb-3 pt-1 border-t border-outline-gray-1 flex justify-end">
                    <Button size="sm" variant="ghost" @click="openDetail('Active SKUs', 'total_skus')">View all rows ↗</Button>
                  </div>
                </div>

                <!-- Compact KPI stat grid (2 rows × 3 cols) — replaces global KPI strip -->
                <div>
                  <p class="text-xs font-medium uppercase tracking-wider text-ink-gray-6 mb-2">Inventory Health Indicators</p>
                  <div class="grid grid-cols-3 gap-px rounded-lg overflow-hidden bg-surface-gray-3 border border-outline-gray-1">
                    <KpiCard
                      label="Health Score"
                      :value="asNumber(stockOverview.health_score)"
                      :severity="stockOverview.health_score != null ? scoreSeverity(stockOverview.health_score as number, { good: 80, warn: 60, higherIsBetter: true }) : 'none'"
                      sublabel="0–100 scale"
                      variant="tile"
                    />
                    <KpiCard
                      label="Active SKUs"
                      :value="formatCount(stockOverview.total_skus as number)"
                      variant="tile"
                      :clickable="true"
                      @click="openDetail('Active SKUs', 'total_skus')"
                    />
                    <KpiCard
                      label="Stock Value"
                      :amount="asNumber(stockOverview.total_value)"
                      :currency="baseCurrency"
                      variant="tile"
                    />
                    <KpiCard
                      label="Out of Stock"
                      :value="formatCount(stockOverview.out_of_stock_count as number)"
                      :sublabel="oosSubLabel"
                      :severity="(stockOverview.out_of_stock_count as number) > 0 ? 'high' : 'none'"
                      variant="tile"
                      :clickable="true"
                      @click="openDetail('Out of Stock Items', 'out_of_stock_items')"
                    />
                    <KpiCard
                      label="Low Stock"
                      :value="formatCount(stockOverview.low_stock_count as number)"
                      :severity="(stockOverview.low_stock_count as number) > 0 ? 'medium' : 'none'"
                      variant="tile"
                      :clickable="true"
                      @click="openDetail('Low Stock Items', 'low_stock_items')"
                    />
                    <KpiCard
                      label="Overstock"
                      :value="formatCount(stockOverview.overstock_count as number)"
                      :severity="(stockOverview.overstock_count as number) > 0 ? 'low' : 'none'"
                      variant="tile"
                      :clickable="true"
                      @click="openDetail('Overstock Items', 'overstock_items')"
                    />
                  </div>
                </div>

              </div><!-- end left column -->

              <!-- Right 1/3: Attention rail (ranked by consequence) -->
              <div class="bg-surface-white border border-outline-gray-1 rounded-lg overflow-hidden flex flex-col">
                <div class="px-4 py-3 border-b border-outline-gray-1 flex items-baseline gap-2">
                  <span class="text-sm font-semibold text-ink-gray-9">Needs Attention</span>
                  <span class="text-xs text-ink-gray-6">ranked by consequence</span>
                </div>

                <!-- 1. Out of stock -->
                <div v-if="(stockOverview.out_of_stock_count as number) > 0" class="px-4 py-3 border-b border-outline-gray-1">
                  <div class="flex items-center gap-2 mb-1.5">
                    <Badge v-bind="severityBadge('high')" label="HIGH" size="sm" />
                    <span class="text-sm font-semibold text-ink-red-4">{{ formatCount(stockOverview.out_of_stock_count as number) }} SKUs out of stock</span>
                  </div>
                  <p class="text-xs text-ink-gray-6 leading-relaxed">{{ oosDescription }}</p>
                  <Button size="sm" variant="ghost" class="mt-1 -ml-2" @click="openDetail('Out of Stock Items', 'out_of_stock_items')">View out-of-stock items ↗</Button>
                </div>

                <!-- 2. Reorder queue -->
                <div v-if="reorderTotal !== undefined && reorderTotal > 0" class="px-4 py-3 border-b border-outline-gray-1">
                  <div class="flex items-center gap-2 mb-1.5">
                    <Badge v-bind="severityBadge('high')" label="HIGH" size="sm" />
                    <span class="text-sm font-semibold text-ink-red-4">{{ formatCount(reorderTotal) }} items need reorder</span>
                  </div>
                  <p class="text-xs text-ink-gray-6 leading-relaxed">
                    {{ reorderSubLabel }}.
                    <template v-if="reorderRows[0]">
                      {{ String((reorderRows[0] as Record<string, unknown>).item_name ?? (reorderRows[0] as Record<string, unknown>).item_code) }}:
                      {{ formatCount(asNumber((reorderRows[0] as Record<string, unknown>).current_stock)) }} on-hand,
                      {{ formatCount(asNumber((reorderRows[0] as Record<string, unknown>).avg_daily_demand), { decimals: 1 }) }}/day.
                    </template>
                  </p>
                  <Button size="sm" variant="ghost" class="mt-1 -ml-2" @click="openDetail('Items Needing Reorder', 'reorder_items')">View reorder list ↗</Button>
                </div>

                <!-- 3. Pending POs -->
                <div v-if="pendingTotal !== undefined && pendingTotal > 0" class="px-4 py-3 border-b border-outline-gray-1">
                  <div class="flex items-center gap-2 mb-1.5">
                    <Badge v-bind="severityBadge('medium')" label="WARN" size="sm" />
                    <span class="text-sm font-semibold text-ink-gray-9">{{ formatCount(pendingTotal) }} POs pending</span>
                  </div>
                  <p class="text-xs text-ink-gray-6 leading-relaxed">
                    <template v-if="pendingRows[0]">
                      Oldest: {{ String((pendingRows[0] as Record<string, unknown>).supplier_name ?? (pendingRows[0] as Record<string, unknown>).supplier) }}
                      {{ money(asNumber((pendingRows[0] as Record<string, unknown>).grand_total)) }}
                      ({{ (pendingRows[0] as Record<string, unknown>).days_pending }} days pending).
                    </template>
                  </p>
                  <Button size="sm" variant="ghost" class="mt-1 -ml-2" @click="goToTab('procurement')">View Procurement tab ↗</Button>
                </div>

                <!-- 4. Low stock -->
                <div v-if="(stockOverview.low_stock_count as number) > 0" class="px-4 py-3 border-b border-outline-gray-1">
                  <div class="flex items-center gap-2 mb-1.5">
                    <Badge v-bind="severityBadge('medium')" label="WARN" size="sm" />
                    <span class="text-sm font-semibold text-ink-gray-9">{{ formatCount(stockOverview.low_stock_count as number) }} low-stock items</span>
                  </div>
                  <p class="text-xs text-ink-gray-6 leading-relaxed">
                    Below 14 days of supply.
                    <template v-if="lowStockTop">
                      {{ String(lowStockTop.item_name ?? lowStockTop.item_code) }}:
                      {{ formatCount(asNumber(lowStockTop.current_stock)) }} units vs
                      {{ formatCount(asNumber(lowStockTop.avg_daily_demand), { decimals: 1 }) }}/day.
                    </template>
                  </p>
                  <Button size="sm" variant="ghost" class="mt-1 -ml-2" @click="openDetail('Low Stock Items', 'low_stock_items')">View low-stock items ↗</Button>
                </div>

                <!-- 5. Aging risk -->
                <div v-if="agingRiskCount > 0" class="px-4 py-3 border-b border-outline-gray-1">
                  <div class="flex items-center gap-2 mb-1.5">
                    <Badge v-bind="severityBadge('medium')" label="WARN" size="sm" />
                    <span class="text-sm font-semibold text-ink-gray-9">{{ agingRiskCount }} items aged 181+ days</span>
                  </div>
                  <p class="text-xs text-ink-gray-6 leading-relaxed">
                    {{ money(agingRiskValue) }} at write-off risk.
                    <template v-if="(agingAnalysis.oldest_items as Record<string, unknown>[] | undefined)?.[0]">
                      Oldest: {{ String((agingAnalysis.oldest_items as Record<string, unknown>[])[0].item_name ?? (agingAnalysis.oldest_items as Record<string, unknown>[])[0].item_code) }}
                      ({{ (agingAnalysis.oldest_items as Record<string, unknown>[])[0].avg_age_days }} days).
                    </template>
                  </p>
                  <Button size="sm" variant="ghost" class="mt-1 -ml-2" @click="goToTab('aging')">View Aging (FIFO) tab ↗</Button>
                </div>

                <!-- 6. Dead stock status -->
                <div class="px-4 py-3 border-b border-outline-gray-1">
                  <div class="flex items-center gap-2 mb-1.5">
                    <Badge
                      v-bind="severityBadge((deadStock.total_value as number) > 0 ? 'medium' : 'none')"
                      :label="(deadStock.total_value as number) > 0 ? 'WARN' : 'CLEAR'"
                      size="sm"
                    />
                    <span class="text-sm font-semibold text-ink-gray-9">Dead stock: {{ money(asNumber(deadStock.total_value)) }}</span>
                  </div>
                  <p class="text-xs text-ink-gray-6 leading-relaxed">
                    <template v-if="(deadStock.total_value as number) > 0">
                      {{ formatCount(deadStock.total_items as number) }} items with no sales in 180+ days.
                    </template>
                    <template v-else>Zero items with no sales in 180+ days.</template>
                  </p>
                </div>

                <!-- Turnover context footer -->
                <div class="mt-auto px-4 py-3 bg-surface-gray-1 border-t border-outline-gray-1">
                  <p class="text-xs font-medium uppercase tracking-wider text-ink-gray-6 mb-2">Turnover Context</p>
                  <div class="space-y-1.5">
                    <div class="flex justify-between items-baseline">
                      <span class="text-xs text-ink-gray-6">Turnover Ratio ({{ windowText }})</span>
                      <span class="text-sm font-semibold text-ink-gray-9 tabular-nums">{{ suffixed(turnoverAnalysis.overall_turnover_ratio, '×') }}</span>
                    </div>
                    <div class="flex justify-between items-baseline">
                      <span class="text-xs text-ink-gray-6">Days Sales Inventory</span>
                      <span class="text-sm font-semibold text-ink-gray-9 tabular-nums">{{ suffixed(turnoverAnalysis.days_sales_inventory, ' days') }}</span>
                    </div>
                    <div class="flex justify-between items-baseline">
                      <span class="text-xs text-ink-gray-6">COGS ({{ windowText }})</span>
                      <span class="text-sm font-semibold text-ink-gray-9 tabular-nums">{{ money(asNumber(turnoverAnalysis.cogs_12m)) }}</span>
                    </div>
                  </div>
                  <Button size="sm" variant="ghost" class="mt-2 -ml-2" @click="goToTab('turnover')">Full analysis in Turnover tab ↗</Button>
                </div>
              </div><!-- end attention rail -->

            </div><!-- end 3-col grid -->
          </div>

          <!-- Warehouses & Transfers -->
          <div v-if="activeTab === 'warehouses'">
            <TabBrief class="mb-6" :brief="tabBriefs.warehouses" :as-of="inventoryData?.generated_at" />
          <div>
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <!-- Warehouse Stock -->
              <div class="lg:col-span-2">
                <SectionHeader variant="caption" title="Stock by Warehouse" :level="3" />
                <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Warehouse</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Items</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">On hand</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Reserved</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">On order</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Value</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">% Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(wh, idx) in warehouseAnalysis.by_warehouse as unknown[]"
                        :key="idx"
                        class="border-b border-outline-gray-1 hover:bg-surface-gray-1 cursor-pointer"
                        role="button"
                        tabindex="0"
                        @click="openWarehouse(wh)"
                        @keydown.enter="openWarehouse(wh)"
                        @keydown.space.prevent="openWarehouse(wh)"
                      >
                        <td class="px-4 py-2 font-medium text-ink-gray-9 truncate max-w-[200px]">{{ (wh as Record<string, unknown>).warehouse }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount((wh as Record<string, unknown>).item_count as number) }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount(Number((wh as Record<string, unknown>).total_qty)) }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount(Number((wh as Record<string, unknown>).reserved_qty)) }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount(Number((wh as Record<string, unknown>).ordered_qty)) }}</td>
                        <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ money((wh as Record<string, unknown>).stock_value as number) }}</td>
                        <td class="px-4 py-2 text-right">
                          <div class="flex items-center justify-end gap-2">
                            <div class="w-16 bg-surface-gray-2 rounded-full h-2">
                              <div class="bg-surface-blue-3 h-2 rounded-full"
                                   :style="{ width: `${(wh as Record<string, unknown>).pct_of_total}%` }"
                                   role="img"
                                   :aria-label="`${formatPercent((wh as Record<string, unknown>).pct_of_total as number)} of total`"></div>
                            </div>
                            <span class="text-xs text-ink-gray-6">{{ formatPercent((wh as Record<string, unknown>).pct_of_total as number) }}</span>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <!-- Summary -->
                <div class="mt-4 grid grid-cols-2 gap-4">
                  <KpiCard
                    label="Total Warehouses"
                    :value="asNumber(warehouseAnalysis.total_warehouses)"
                    variant="tile"
                  />
                  <KpiCard
                    label="Total Stock Value"
                    :amount="asNumber(warehouseAnalysis.total_stock_value)"
                    :currency="baseCurrency"
                    variant="tile"
                  />
                </div>
              </div>

              <!-- Transfer Recommendations -->
              <div>
                <SectionHeader variant="caption" title="Transfer Recommendations" :level="3"
                               hint="Suggested transfers to balance inventory" />
                <div v-if="(transferRecommendations as unknown[]).length > 0" class="mt-4 space-y-3">
                  <div
                    v-for="(rec, idx) in (transferRecommendations as unknown[]).slice(0, 8)"
                    :key="idx"
                    class="bg-surface-white rounded-lg border border-outline-gray-1 p-4 hover:shadow-md transition-shadow motion-reduce:transition-none"
                  >
                    <div class="flex items-center justify-between mb-2">
                      <span class="font-medium text-ink-gray-9 truncate max-w-[200px]"
                            :title="(rec as Record<string, unknown>).item_name as string">
                        {{ (rec as Record<string, unknown>).item_code }}
                      </span>
                      <Badge v-bind="severityBadge(prioritySeverity((rec as Record<string, unknown>).priority as string))"
                        :label="(rec as Record<string, unknown>).priority as string" size="sm" />
                    </div>
                    <div class="flex items-center gap-2 text-sm text-ink-gray-6">
                      <span class="truncate max-w-[100px]"
                            :title="(rec as Record<string, unknown>).from_warehouse as string">
                        {{ (rec as Record<string, unknown>).from_warehouse }}
                      </span>
                      <ArrowRight class="w-4 h-4 text-ink-gray-5 flex-shrink-0" aria-hidden="true" />
                      <span class="truncate max-w-[100px]"
                            :title="(rec as Record<string, unknown>).to_warehouse as string">
                        {{ (rec as Record<string, unknown>).to_warehouse }}
                      </span>
                    </div>
                    <div class="mt-2 flex justify-between items-center">
                      <span class="text-xs text-ink-gray-6">{{ (rec as Record<string, unknown>).reason }}</span>
                      <span class="text-sm font-bold text-ink-gray-9">{{ formatCount((rec as Record<string, unknown>).recommended_qty as number) }} units</span>
                    </div>
                  </div>
                </div>
                <div v-else class="mt-4 text-center py-8 bg-surface-gray-1 rounded-lg border border-outline-gray-1">
                  <ArrowRightLeft class="w-8 h-8 mx-auto text-ink-gray-5" aria-hidden="true" />
                  <p class="mt-2 text-ink-gray-6">No transfer recommendations</p>
                  <p class="text-sm text-ink-gray-6">Stock is well-balanced across warehouses</p>
                </div>
              </div>
            </div>

            <!-- Multi-Warehouse Items -->
            <div class="mt-6">
              <SectionHeader variant="caption" title="Items in Multiple Warehouses" :level="3" />
              <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                <table class="w-full text-sm">
                  <thead class="bg-surface-gray-1">
                    <tr>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item Code</th>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item Name</th>
                      <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Warehouses</th>
                      <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Total Qty</th>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Distribution</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(item, idx) in (warehouseAnalysis.multi_warehouse_items as unknown[])?.slice(0, 10)"
                      :key="idx"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                    >
                      <td class="px-4 py-2 font-medium text-ink-gray-9">{{ (item as Record<string, unknown>).item_code }}</td>
                      <td class="px-4 py-2 text-ink-gray-6 truncate max-w-[150px]">{{ (item as Record<string, unknown>).item_name }}</td>
                      <td class="px-4 py-2 text-right">
                        <Badge v-bind="severityBadge('none')"
                               :label="String((item as Record<string, unknown>).warehouse_count)" size="sm" />
                      </td>
                      <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ formatCount((item as Record<string, unknown>).total_qty as number) }}</td>
                      <td class="px-4 py-2 text-xs text-ink-gray-6 truncate max-w-[200px]"
                          :title="((item as Record<string, unknown>).distribution as string) || undefined">
                        {{ (item as Record<string, unknown>).distribution || NO_VALUE }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <TabActions class="mt-6" :actions="tabBriefs.warehouses?.actions" />

          </div>

          <!-- Turnover Tab -->
          <div v-if="activeTab === 'turnover'">
            <TabBrief class="mb-6" :brief="tabBriefs.turnover" :as-of="inventoryData?.generated_at" />
            <StatStrip class="mb-6" :items="turnoverStrip" :currency="baseCurrency" />

            <!-- Turnover by Product Group -->
            <SectionHeader variant="caption" title="Turnover by Product Group" :level="3" />
            <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="bg-surface-gray-1">
                  <tr>
                    <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item Group</th>
                    <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Sales ({{ windowText }})</th>
                    <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">COGS ({{ windowText }})</th>
                    <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Inventory Value</th>
                    <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">ITR</th>
                    <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">DSI</th>
                    <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">GM%</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in turnoverRows"
                    :key="row.group"
                    class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                  >
                    <td class="px-4 py-2 font-medium text-ink-gray-9">{{ row.group }}</td>
                    <td class="tnum px-4 py-2 text-right text-ink-gray-6">{{ money(row.sales) }}</td>
                    <td class="tnum px-4 py-2 text-right text-ink-gray-6">{{ money(row.cogs) }}</td>
                    <td class="tnum px-4 py-2 text-right text-ink-gray-6">{{ money(row.stock) }}</td>
                    <td class="tnum px-4 py-2 text-right font-bold text-ink-gray-9">{{ suffixed(row.itr, 'x') }}</td>
                    <td class="tnum px-4 py-2 text-right text-ink-gray-6">{{ suffixed(row.dsi, ' days') }}</td>
                    <td class="tnum px-4 py-2 text-right text-ink-gray-6">{{ suffixed(row.gm, '%') }}</td>
                  </tr>
                  <tr class="bg-surface-gray-1 font-semibold text-ink-gray-9">
                    <td class="px-4 py-2">{{ turnoverTotal.group }}</td>
                    <td class="tnum px-4 py-2 text-right">{{ money(turnoverTotal.sales) }}</td>
                    <td class="tnum px-4 py-2 text-right">{{ money(turnoverTotal.cogs) }}</td>
                    <td class="tnum px-4 py-2 text-right">{{ money(turnoverTotal.stock) }}</td>
                    <td class="tnum px-4 py-2 text-right">{{ suffixed(turnoverTotal.itr, 'x') }}</td>
                    <td class="tnum px-4 py-2 text-right">{{ suffixed(turnoverTotal.dsi, ' days') }}</td>
                    <td class="tnum px-4 py-2 text-right">{{ suffixed(turnoverTotal.gm, '%') }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Fast Moving -->
              <div class="min-w-0">
                <SectionHeader variant="caption" :title="`Fast Moving Items (${windowText})`" :level="3" />
                <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-x-auto">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Qty Sold</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Sales Value</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Stock Now</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(item, idx) in (turnoverAnalysis.fast_moving as Record<string, unknown>[])"
                        :key="idx"
                        class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                      >
                        <td class="px-4 py-2">
                          <p class="font-medium text-ink-gray-9">{{ item.item_code }}</p>
                          <p class="truncate max-w-[200px] text-xs text-ink-gray-6">{{ item.item_name }}</p>
                        </td>
                        <td class="tnum px-4 py-2 text-right font-bold text-ink-gray-9">{{ formatCount(item.qty_sold as number) }}</td>
                        <td class="tnum px-4 py-2 text-right text-ink-gray-6">{{ money(item.sales_value as number) }}</td>
                        <td class="tnum px-4 py-2 text-right text-ink-gray-6">{{ formatCount(item.current_stock as number) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Slow Moving -->
              <div class="min-w-0">
                <SectionHeader variant="caption" :title="`Slow Moving Items (${windowText})`" :level="3" />
                <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-x-auto">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">On Hand</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Valuation Rate</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Stock Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(item, idx) in (turnoverAnalysis.slow_moving as Record<string, unknown>[])"
                        :key="idx"
                        class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                      >
                        <td class="px-4 py-2">
                          <p class="font-medium text-ink-gray-9">{{ item.item_code }}</p>
                          <p class="truncate max-w-[200px] text-xs text-ink-gray-6">{{ item.item_name }}</p>
                        </td>
                        <td class="tnum px-4 py-2 text-right text-ink-gray-6">{{ formatCount(item.current_stock as number) }}</td>
                        <td class="tnum px-4 py-2 text-right text-ink-gray-6">{{ money(item.valuation_rate as number) }}</td>
                        <td class="tnum px-4 py-2 text-right font-bold text-ink-gray-9">{{ money(item.stock_value as number) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <TabActions class="mt-6" :actions="tabBriefs.turnover?.actions" />
          </div>

          <!-- ABC/XYZ Tab -->
          <div v-if="activeTab === 'abc-xyz'">
            <TabBrief class="mb-6" :brief="tabBriefs['abc-xyz']" :as-of="inventoryData?.generated_at" />
            <div v-if="abcXyz">
              <!-- Summary Cards -->
              <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
                <KpiCard label="Class A Items" :value="formatCount(abcXyz.summary?.a_count as number)"
                         :sublabel="`High value, ${abcShare.A ?? NO_VALUE}`" />
                <KpiCard label="Class B Items" :value="formatCount(abcXyz.summary?.b_count as number)"
                         :sublabel="`Medium value, ${abcShare.B ?? NO_VALUE}`" />
                <KpiCard label="Class C Items" :value="formatCount(abcXyz.summary?.c_count as number)"
                         :sublabel="`Low value, ${abcShare.C ?? NO_VALUE}`" />
                <KpiCard label="Class X Items" :value="formatCount(abcXyz.summary?.x_count as number)"
                         sublabel="Stable Demand" />
                <KpiCard label="Class Y Items" :value="formatCount(abcXyz.summary?.y_count as number)"
                         sublabel="Variable Demand" />
                <KpiCard label="Class Z Items" :value="formatCount(abcXyz.summary?.z_count as number)"
                         sublabel="Irregular Demand" />
              </div>

              <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <!-- ABC/XYZ Matrix -->
                <div>
                  <SectionHeader variant="caption" title="ABC/XYZ Classification Matrix" :level="3"
                                 :hint="`${formatCount(abcXyz.total_items as number)} items, ${formatDate(abcXyz.classification_date as string)}`" />
                  <div class="mt-4 grid grid-cols-[auto_repeat(3,minmax(0,1fr))] gap-px overflow-hidden rounded-lg border border-outline-gray-1 bg-surface-gray-3 text-sm">
                    <div class="bg-surface-gray-1 px-3 py-2" />
                    <div v-for="h in ['X: Stable', 'Y: Variable', 'Z: Erratic']" :key="h" class="bg-surface-gray-1 px-3 py-2 text-xs font-medium uppercase tracking-wide text-ink-gray-6">{{ h }}</div>
                    <template v-for="r in abcGrid" :key="r.abc">
                      <div class="bg-surface-gray-1 px-3 py-2 text-xs font-medium uppercase tracking-wide text-ink-gray-6">{{ r.abc }}</div>
                      <div v-for="c in r.cells" :key="c.cls" class="bg-surface-white px-3 py-2">
                        <p class="font-semibold text-ink-gray-9">{{ c.cls }}</p>
                        <p class="text-ink-gray-7">{{ formatCount(c.row?.item_count as number) }} items</p>
                        <p class="tnum text-ink-gray-8">{{ money(c.row?.total_value as number) }} sales</p>
                        <p class="tnum text-xs text-ink-gray-6">{{ money(c.row?.stock_value as number) }} stock</p>
                      </div>
                    </template>
                  </div>

                  <!-- ABC Summary -->
                  <SectionHeader variant="caption" title="Pareto concentration (by value)" :level="4" class="mt-6 mb-3" />
                  <div class="space-y-3 rounded-lg border border-outline-gray-1 bg-surface-white p-4">
                    <div v-for="p in abcPareto" :key="p.cls">
                      <div class="flex items-baseline justify-between gap-3 text-sm">
                        <span class="font-medium text-ink-gray-8">Class {{ p.cls }}</span>
                        <span class="tnum text-ink-gray-7">
                          {{ money(p.value) }} · {{ p.pct === null ? NO_VALUE : formatPercent(p.pct) }} · {{ formatCount(p.items) }} items<template v-if="p.itemPct !== null"> ({{ formatPercent(p.itemPct) }})</template>
                        </span>
                      </div>
                      <div class="mt-1 h-2 w-full overflow-hidden rounded-full bg-surface-gray-2">
                        <div class="h-full rounded-full bg-muted-fill" :style="{ width: `${p.pct ?? 0}%` }" />
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Top Items with Strategy -->
                <div>
                  <SectionHeader variant="caption" title="Top Items with Strategy Recommendations" :level="3" />
                  <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden max-h-[600px] overflow-y-auto">
                    <table class="w-full text-sm">
                      <thead class="bg-surface-gray-1 sticky top-0">
                        <tr>
                          <th scope="col" class="px-3 py-2 text-left text-ink-gray-6">Item</th>
                          <th scope="col" class="px-3 py-2 text-center text-ink-gray-6">Class</th>
                          <th scope="col" class="px-3 py-2 text-right text-ink-gray-6">Sales value</th>
                          <th scope="col" class="px-3 py-2 text-right text-ink-gray-6">Stock</th>
                          <th scope="col" class="px-3 py-2 text-left text-ink-gray-6">Strategy</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="(item, idx) in (abcXyz.top_items as unknown[])?.slice(0, 20)"
                          :key="idx"
                          class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                        >
                          <td class="px-3 py-2">
                            <div class="font-medium text-ink-gray-9 truncate max-w-[120px]"
                                 :title="(item as Record<string, unknown>).item_name as string">
                              {{ (item as Record<string, unknown>).item_code }}
                            </div>
                            <div class="text-xs text-ink-gray-6 truncate max-w-[120px]"
                                 :title="(item as Record<string, unknown>).item_name as string">
                              {{ (item as Record<string, unknown>).item_name }}
                            </div>
                          </td>
                          <td class="px-3 py-2 text-center">
                            <Badge v-bind="severityBadge(
                              (item as Record<string, unknown>).abc_class === 'A' ? 'none' :
                              (item as Record<string, unknown>).abc_class === 'B' ? 'medium' : 'high'
                            )" :label="String((item as Record<string, unknown>).abc_class)" size="sm" />
                            <Badge v-bind="severityBadge(
                              (item as Record<string, unknown>).xyz_class === 'X' ? 'none' :
                              (item as Record<string, unknown>).xyz_class === 'Y' ? 'medium' : 'low'
                            )" :label="String((item as Record<string, unknown>).xyz_class)" size="sm" class="ml-1" />
                          </td>
                          <td class="px-3 py-2 text-right text-xs text-ink-gray-6">{{ money((item as Record<string, unknown>).total_value as number) }}</td>
                          <td class="px-3 py-2 text-right text-xs text-ink-gray-6">{{ formatCount((item as Record<string, unknown>).stock_qty as number) }}</td>
                          <td class="px-3 py-2 text-xs text-ink-gray-6">{{ (item as Record<string, unknown>).strategy || NO_VALUE }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- Strategy Legend -->
                  <div class="mt-4 p-4 bg-surface-gray-1 rounded-lg border border-outline-gray-1">
                    <h4 class="font-medium text-ink-gray-7 mb-2">Strategy Guide</h4>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs text-ink-gray-6">
                      <div><span class="font-bold text-ink-gray-8">AX:</span> JIT inventory, tight control</div>
                      <div><span class="font-bold text-ink-gray-8">AY:</span> Safety stock, close monitoring</div>
                      <div><span class="font-bold text-ink-gray-8">AZ:</span> Make-to-order preferred</div>
                      <div><span class="font-bold text-ink-gray-8">BX:</span> Moderate stock levels</div>
                      <div><span class="font-bold text-ink-gray-8">BY:</span> Regular review cycles</div>
                      <div><span class="font-bold text-ink-gray-8">BZ:</span> Buffer safety stock</div>
                      <div><span class="font-bold text-ink-gray-8">CX:</span> Simple reorder rules</div>
                      <div><span class="font-bold text-ink-gray-8">CY:</span> Periodic review</div>
                      <div><span class="font-bold text-ink-gray-8">CZ:</span> Consider discontinuing</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-12">
              <Layers class="w-12 h-12 mx-auto text-ink-gray-5" aria-hidden="true" />
              <p class="mt-4 text-ink-gray-6">ABC/XYZ Classification not available</p>
              <p class="text-sm text-ink-gray-6 mb-4">Run ABC/XYZ analysis to see classification data</p>
              <Button variant="solid" :loading="isTrainingAbcXyz" @click="trainAbcXyz">
                {{ isTrainingAbcXyz ? 'Running Analysis...' : 'Run ABC/XYZ Classification' }}
              </Button>
            </div>
            <TabActions class="mt-6" :actions="tabBriefs['abc-xyz']?.actions" />
          </div>

          <!-- Itemwise BE Tab -->
          <div v-if="activeTab === 'itemwise-be'">
            <TabBrief class="mb-6" :brief="itemwiseBeBrief" />
            <div v-if="itemwiseBeLoading" class="flex items-center justify-center py-12">
              <Spinner class="w-8 h-8" />
            </div>
            <div v-else-if="itemwiseBeError" class="text-center py-12 text-ink-gray-6">{{ itemwiseBeError }}</div>
            <div v-else-if="(itemwiseBeData?.items as unknown[])?.length" class="bg-surface-white rounded-lg shadow-sm border border-outline-gray-1 overflow-x-auto">
              <table class="min-w-full divide-y divide-outline-gray-1">
                <thead class="bg-surface-gray-1">
                  <tr>
                    <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Item</th>
                    <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Selling Price</th>
                    <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Variable Cost</th>
                    <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">CM</th>
                    <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">BE Qty</th>
                    <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Actual Qty</th>
                    <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Coverage %</th>
                    <th scope="col" class="px-4 py-3 text-center text-xs font-medium text-ink-gray-6 uppercase">RAG</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-outline-gray-1">
                  <tr v-for="item in (itemwiseBeData?.items || []) as unknown[]" :key="(item as Record<string, unknown>).item_code as string"
                      class="hover:bg-surface-gray-1">
                    <td class="px-4 py-3 text-sm font-medium text-ink-gray-9">
                      {{ (item as Record<string, unknown>).item_code }}
                      <br>
                      <span class="text-xs text-ink-gray-6">{{ (item as Record<string, unknown>).item_name }}</span>
                    </td>
                    <td class="px-4 py-3 text-sm text-right text-ink-gray-6">{{ money((item as Record<string, unknown>).selling_price as number) }}</td>
                    <td class="px-4 py-3 text-sm text-right text-ink-gray-6">{{ money((item as Record<string, unknown>).variable_cost as number) }}</td>
                    <td class="px-4 py-3 text-sm text-right font-medium text-ink-gray-9">{{ money((item as Record<string, unknown>).contribution_margin as number) }}</td>
                    <td class="px-4 py-3 text-sm text-right text-ink-gray-6">{{ ((item as Record<string, unknown>).be_qty as number)?.toLocaleString() }}</td>
                    <td class="px-4 py-3 text-sm text-right text-ink-gray-6">{{ ((item as Record<string, unknown>).actual_qty as number)?.toLocaleString() }}</td>
                    <td class="px-4 py-3 text-sm text-right font-medium"
                        :class="coverageInk(item)">
                      {{ formatPercent(coveragePct(item)) }}
                    </td>
                    <td class="px-4 py-3 text-center">
                      <Badge v-bind="severityBadge(ragSeverity((item as Record<string, unknown>).rag as string))"
                             :label="severityBadge(ragSeverity((item as Record<string, unknown>).rag as string)).label"
                             size="sm"
                             :aria-label="severityAria('Break-even', ragSeverity((item as Record<string, unknown>).rag as string))" />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-center py-12 text-ink-gray-6">No item break-even data available</div>
            <TabActions class="mt-6" :actions="itemwiseBeBrief?.actions" />
          </div>

          <!-- Aging (FIFO) Tab -->
          <div v-if="activeTab === 'aging'">
            <TabBrief class="mb-6" :brief="tabBriefs.aging" :as-of="inventoryData?.generated_at" />
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Age Buckets Visual -->
              <div>
                <SectionHeader variant="caption" title="Stock Age Distribution (FIFO)" :level="3" />
                <div class="mt-4 space-y-3">
                  <div
                    v-for="(bucket, name) in agingAnalysis.age_buckets as Record<string, { value: number; count: number }>"
                    :key="name"
                    class="flex items-center gap-4"
                  >
                    <div class="w-24 text-sm font-medium text-ink-gray-6">{{ name }}</div>
                    <div class="flex-1 bg-surface-gray-2 rounded-full h-6 overflow-hidden"
                         role="img"
                         :aria-label="severityAria(String(name), ageBucketSeverity(String(name)), money(bucket.value))">
                      <div
                        :class="['h-full rounded-full', severityFill(ageBucketSeverity(String(name)))]"
                        :style="{ width: `${Math.min(100, (bucket.value / maxAgeBucketValue) * 100)}%` }"
                      ></div>
                    </div>
                    <div class="w-20 text-right text-sm font-bold text-ink-gray-9">{{ money(bucket.value) }}</div>
                    <div class="w-16 text-right text-xs text-ink-gray-6">{{ bucket.count }} items</div>
                  </div>
                </div>

                <div class="mt-6 p-4 bg-surface-gray-1 rounded-lg border border-outline-gray-1">
                  <p class="text-sm text-ink-gray-6">
                    <strong class="text-ink-gray-8">Total Items Analyzed:</strong> {{ formatCount(agingAnalysis.total_items_analyzed as number) }}
                  </p>
                  <p class="text-xs text-ink-gray-6 mt-1">
                    Items with positive stock only; {{ formatCount(stockOverview.out_of_stock_count as number) }} out-of-stock items excluded
                  </p>
                  <p class="text-xs text-ink-gray-6 mt-1">
                    Age calculation based on FIFO (First-In-First-Out) valuation method
                  </p>
                </div>

                <div v-if="agingZones.length" class="mt-6 rounded-lg border border-outline-gray-1 bg-surface-white p-4">
                  <SectionHeader variant="caption" title="Capital at risk vs portfolio" :level="4" />
                  <div class="mt-3 space-y-3">
                    <div v-for="z in agingZones" :key="z.label">
                      <div class="flex items-baseline justify-between gap-3 text-sm">
                        <span class="text-ink-gray-7">{{ z.label }}, {{ formatCount(z.count) }} items</span>
                        <span class="tnum font-semibold text-ink-gray-8">{{ money(z.value) }} · {{ z.pct === null ? NO_VALUE : formatPercent(z.pct) }}</span>
                      </div>
                      <div class="mt-1 h-2 w-full overflow-hidden rounded-full bg-surface-gray-2">
                        <div class="h-full rounded-full" :class="z.fill" :style="{ width: `${z.pct ?? 0}%` }" />
                      </div>
                    </div>
                  </div>
                  <p class="mt-3 text-sm text-ink-gray-7">Total portfolio <span class="tnum font-semibold text-ink-gray-8">{{ money(agingZones[0].total) }}</span></p>
                </div>
              </div>

              <!-- Aging by Product Group -->
              <div>
                <SectionHeader variant="caption" title="Average Age by Product Group" :level="3" />
                <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item Group</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Items</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Value</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Avg Age</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(group, idx) in agingAnalysis.by_product_group as unknown[]"
                        :key="idx"
                        class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                      >
                        <td class="px-4 py-2 font-medium text-ink-gray-9">{{ (group as Record<string, unknown>).item_group }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount((group as Record<string, unknown>).item_count as number) }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ money((group as Record<string, unknown>).total_value as number) }}</td>
                        <td class="px-4 py-2 text-right">
                          <!-- Age: good <= 30, warn <= 90, higherIsBetter: false -->
                          <span :class="['font-bold', deltaInk((group as Record<string, unknown>).avg_age_days as number - 90, { higherIsBetter: false })]">
                            {{ (group as Record<string, unknown>).avg_age_days }} days
                          </span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <!-- Oldest Items -->
            <div class="mt-6">
              <SectionHeader variant="caption" title="Oldest Stock Items" :level="3" />
              <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                <table class="w-full text-sm">
                  <thead class="bg-surface-gray-1">
                    <tr>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item Code</th>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item Name</th>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item Group</th>
                      <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Qty</th>
                      <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Value</th>
                      <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Avg Age</th>
                      <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Days to 365+ bucket</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(item, idx) in agingAnalysis.oldest_items as unknown[]"
                      :key="idx"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                    >
                      <td class="px-4 py-2 font-medium text-ink-gray-9">{{ (item as Record<string, unknown>).item_code }}</td>
                      <td class="px-4 py-2 text-ink-gray-6 truncate max-w-[200px]">{{ (item as Record<string, unknown>).item_name }}</td>
                      <td class="px-4 py-2 text-ink-gray-6">{{ (item as Record<string, unknown>).item_group }}</td>
                      <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount((item as Record<string, unknown>).total_qty as number) }}</td>
                      <td class="px-4 py-2 text-right text-ink-gray-6">{{ money((item as Record<string, unknown>).total_value as number) }}</td>
                      <td class="px-4 py-2 text-right font-bold" :class="deltaInk(-1, { higherIsBetter: true })">
                        {{ (item as Record<string, unknown>).avg_age_days }} days
                      </td>
                      <td class="tnum px-4 py-2 text-right text-ink-gray-6">
                        {{ Math.max(0, 365 - Number((item as Record<string, unknown>).avg_age_days)) }} days
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <TabActions class="mt-6" :actions="tabBriefs.aging?.actions" />
          </div>

          <!-- Procurement Tab -->
          <div v-if="activeTab === 'procurement'">
            <TabBrief class="mb-6" :brief="tabBriefs.procurement" :as-of="inventoryData?.generated_at" />
            <div>
              <!-- Reorder Needed -->
              <div>
                <SectionHeader variant="caption" title="Items Needing Reorder" :level="3">
                  <template #actions>
                    <div class="flex items-center gap-2">
                      <Badge v-bind="severityBadge(scoreSeverity(reorderTotal as number, { good: 0, warn: 5, higherIsBetter: false }))"
                             :label="formatCount(reorderTotal)" size="sm" />
                      <Button size="sm" variant="subtle" @click="openDetail('Items Needing Reorder', 'reorder_items')">View all</Button>
                    </div>
                  </template>
                </SectionHeader>
                <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Stock</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Reorder Level</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Daily Demand</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(item, idx) in reorderRows"
                        :key="idx"
                        class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                      >
                        <td class="px-4 py-2 font-medium text-ink-gray-9 truncate max-w-[150px]"
                            :title="(item as Record<string, unknown>).item_name as string">
                          {{ (item as Record<string, unknown>).item_code }}
                        </td>
                        <td class="px-4 py-2 text-right font-bold" :class="deltaInk(-1, { higherIsBetter: true })">
                          {{ formatCount((item as Record<string, unknown>).current_stock as number) }}
                        </td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount((item as Record<string, unknown>).reorder_level as number) }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount(asNumber(item.avg_daily_demand), { decimals: 1 }) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p v-if="reorderTotal !== undefined && reorderRows.length < reorderTotal" class="mt-2 text-xs text-ink-gray-6">
                  Showing {{ reorderRows.length }} of {{ formatCount(reorderTotal) }} items needing reorder
                </p>
              </div>
            </div>

            <!-- Pending Orders -->
            <div class="mt-6">
              <SectionHeader variant="caption" title="Pending Purchase Orders" :level="3">
                <template #actions>
                  <div class="flex items-center gap-2">
                    <Badge v-bind="severityBadge(scoreSeverity(pendingTotal as number, { good: 0, warn: 10, higherIsBetter: false }))"
                           :label="formatCount(pendingTotal)" size="sm" />
                    <Button size="sm" variant="subtle" @click="openDetail('Pending Purchase Orders', 'pending_orders')">View all</Button>
                  </div>
                </template>
              </SectionHeader>
              <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                <table class="w-full text-sm">
                  <thead class="bg-surface-gray-1">
                    <tr>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">PO Number</th>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Supplier</th>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Date</th>
                      <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Value</th>
                      <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Days Pending</th>
                      <th scope="col" class="px-4 py-2 text-center text-ink-gray-6">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(order, idx) in pendingRows"
                      :key="idx"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                    >
                      <td class="px-4 py-2 font-medium text-ink-gray-9">{{ (order as Record<string, unknown>).name }}</td>
                      <td class="px-4 py-2 text-ink-gray-6 truncate max-w-[150px]">{{ order.supplier_name || order.supplier }}</td>
                      <td class="px-4 py-2 text-ink-gray-6">{{ formatDate(order.transaction_date as string) }}</td>
                      <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ money(asNumber(order.grand_total)) }}</td>
                      <td class="px-4 py-2 text-right">
                        <!-- Days pending: good <= 7, warn <= 14, higherIsBetter: false -->
                        <Badge v-bind="severityBadge(scoreSeverity((order as Record<string, unknown>).days_pending as number, { good: 7, warn: 14, higherIsBetter: false }))"
                               :label="`${(order as Record<string, unknown>).days_pending} days`" size="sm" />
                      </td>
                      <td class="px-4 py-2 text-center">
                        <Badge v-bind="severityBadge('none')"
                               :label="(order as Record<string, unknown>).status as string" size="sm" />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-if="pendingTotal !== undefined && pendingRows.length < pendingTotal" class="mt-2 text-xs text-ink-gray-6">
                Showing {{ pendingRows.length }} of {{ formatCount(pendingTotal) }} pending orders
              </p>
            </div>

            <!-- Demand Planning Integration -->
            <div class="mt-6">
              <SectionHeader variant="caption" title="Demand Planning Summary" :level="3" />
              <p v-if="!demandPlanning" class="mt-4 text-sm text-ink-gray-6">Demand planning not available</p>
              <template v-else>
                <div class="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <KpiCard label="Total Items" :value="demandTotal" />
                  <KpiCard label="Reorder Now"
                           :value="asNumber(demandSummary?.reorder_now_count)"
                           :severity="Number(demandSummary?.reorder_now_count) > 0 ? 'high' : 'none'" />
                  <KpiCard label="Monitor"
                           :value="asNumber(demandSummary?.monitor_count)"
                           :severity="Number(demandSummary?.monitor_count) > 0 ? 'medium' : 'none'" />
                  <KpiCard label="Adequate" :value="asNumber(demandSummary?.adequate_count)" />
                </div>
                <div v-if="demandAlerts.length" class="bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Stock</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Monthly Forecast</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Months Cover</th>
                        <th scope="col" class="px-4 py-2 text-center text-ink-gray-6">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(alert, idx) in demandAlerts" :key="idx"
                          class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
                        <td class="px-4 py-2 font-medium text-ink-gray-9">{{ alert.item_code }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount(asNumber(alert.current_stock)) }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount(asNumber(alert.monthly_forecast), { decimals: 1 }) }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount(asNumber(alert.months_cover), { decimals: 1 }) }}</td>
                        <td class="px-4 py-2 text-center">
                          <Badge v-bind="severityBadge(alert.status === 'reorder_now' ? 'high' : alert.status === 'monitor' ? 'medium' : 'none')"
                                 :label="String(alert.status ?? NO_VALUE).replace('_', ' ')" size="sm" />
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p v-if="demandTotal !== undefined && demandAlerts.length < demandTotal" class="mt-2 text-xs text-ink-gray-6">
                  Showing {{ demandAlerts.length }} of {{ formatCount(demandTotal) }} items analyzed
                </p>
              </template>
            </div>
            <TabActions class="mt-6" :actions="tabBriefs.procurement?.actions" />
          </div>
        </div>
    </div>
    </IntelligenceDashboardShell>

    <!-- AI Chat Button -->
    <DashboardChatButton
      dashboard-type="Inventory"
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
