<!-- frontend/src2/dashboard/CustomerSections.vue -->
<!--
  Customer tab-group content for the merged Revenue & Customers dashboard.
  Receives the customer_intelligence payload from the shell and renders 7 tabs:
  Overview, Customers, Geography, Actions, Cohorts, Patterns, Rankings.
  The TerritoryMap lives here (not in Revenue Attribution).
-->
<script setup lang="ts">
defineOptions({ name: 'CustomerSections' })
import { Badge, Button, FormControl, Select, Tooltip } from 'frappe-ui'
import { apiCall, readFrappeError } from '../helpers/api'
import {
  Search, Filter, Star, ChevronRight, MapPin, Target, Activity,
} from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { createToast } from '../helpers/toasts'
import TerritoryMap from '../components/TerritoryMap.vue'
import {
  formatCurrency, formatNumber, formatPercent,
  tierFilterOptions, rfmSegmentFilterOptions, riskFilterOptions,
  getRecentCustomers, addRecentCustomer, actionLabel,
} from '../utils/customerUtils'
import { severityBadge, severityFill, scoreSeverity, ragSeverity, prioritySeverity, deltaInk, type Severity } from '../utils/status'
import type { DrillDownParams } from '../intelligence/composables/useDrillDown'
import KpiCard from '../intelligence/components/KpiCard.vue'
import SectionHeader from '../intelligence/components/SectionHeader.vue'
import SkeletonBlock from '../intelligence/components/SkeletonBlock.vue'

// ── Props & emits ──────────────────────────────────────────────────────────
const props = defineProps<{
  data: Record<string, unknown>
  activeTab: string
  dateFilter: string
  currency: string | null
  drillDownEndpoint: string
}>()

const emit = defineEmits<{
  (e: 'drill-down', endpoint: string, title: string, params: DrillDownParams): void
  (e: 'view-customer', customerId: string): void
}>()

function drillOpen(title: string, params: DrillDownParams) {
  emit('drill-down', props.drillDownEndpoint, title, params)
}

function viewCustomerDetail(customerId: string) {
  recentCustomerIds.value = addRecentCustomer(customerId)
  emit('view-customer', customerId)
}

// ── Types ──────────────────────────────────────────────────────────────────
interface CustomerRow {
  customer_id: string
  customer_name?: string
  territory?: string
  rfm_segment?: string
  clv_tier?: string
  churn_risk?: string
  total_clv?: number
  historical_clv?: number
  health_status?: string
  health_score?: number
  order_count?: number
  recency_days?: number
}

interface ScorecardRow {
  customer: string
  customer_name: string
  revenue: number
  gross_profit: number
  margin_pct: number
  months_active: number
  total_months: number
  consistency_score: number
  avg_monthly_spend: number
  clv_tier?: string
  rfm_segment?: string
  churn_risk?: string
  health_status?: string
  health_score?: number
}
interface ScorecardData {
  customers: ScorecardRow[]
  total_months: number
}
type RankSortKey = 'revenue' | 'gross_profit' | 'margin_pct' | 'months_active' | 'consistency_score' | 'health_score'
interface GeoPoint { name: string; value: number }
interface UnmappedTerritory { territory: string; value: number }
interface DayOfWeekDataRow { order_count: number }
interface ActionRec {
  action: string
  priority: string
  description: string
  suggestion: string
}
interface ActionItem {
  customer_id: string
  customer_name?: string
  clv_tier?: string
  health_status?: string
  churn_risk?: string
  historical_clv?: number
  predicted_12m_clv?: number
  outstanding_amount?: number
  recency_days?: number
  recommendations: ActionRec[]
}

// ── Recommendation tier labels ─────────────────────────────────────────────
const REC_TIER_LABELS: Record<number, string> = {
  0: 'Seasonal', 1: 'Rules', 2: 'FBT', 3: 'Popular', 4: 'Explore',
}

// ── State ──────────────────────────────────────────────────────────────────
const counts = ref<any>(null)
const scorecard = ref<ScorecardData | null>(null)
const isLoadingRankings = ref(false)
const purchasePatternsData = ref<any>(null)
const activeCutoff = ref('6')
const isLoadingPatterns = ref(false)
// Rankings filters + sort — all client-side over the one scorecard list.
const rankSearch = ref('')
const rankTier = ref('')
const rankSegment = ref('')
const rankRisk = ref('')
const minRevenue = ref('')
const minGrossProfit = ref('')
const minMargin = ref('')
const minMonths = ref('')
const minScore = ref('')
const rankSort = ref<RankSortKey>('revenue')
const rankDir = ref<'asc' | 'desc'>('desc')
const sortableCols: { key: RankSortKey; label: string }[] = [
  { key: 'revenue', label: 'Revenue' },
  { key: 'gross_profit', label: 'Gross Profit' },
  { key: 'margin_pct', label: 'Margin %' },
  { key: 'months_active', label: 'Months' },
  { key: 'consistency_score', label: 'Score' },
  { key: 'health_score', label: 'Health' },
]

// ── Filters ────────────────────────────────────────────────────────────────
const customerFilter = ref('')
const tierFilter = ref('')
const riskFilter = ref('')
const rfmFilter = ref('')
const recentCustomerIds = ref<string[]>(getRecentCustomers())

// ── Computed data accessors ────────────────────────────────────────────────
const summary = computed(() => (props.data.summary ?? {}) as Record<string, unknown>)
const baseCurrency = computed<string | null>(() => (props.data.base_currency as string) ?? props.currency)
const customers = computed(() => {
  let list: CustomerRow[] = (props.data.customers ?? []) as unknown as CustomerRow[]
  if (customerFilter.value) {
    const search = customerFilter.value.toLowerCase()
    list = list.filter((c: CustomerRow) =>
      // Coerce each field: the payload occasionally carries a non-string
      // (e.g. territory `0` for customers with no territory), and calling
      // `.toLowerCase()` on it throws, crashing the whole tab.
      [c.customer_name, c.customer_id, c.territory, c.rfm_segment]
        .some(v => typeof v === 'string' && v.toLowerCase().includes(search)),
    )
  }
  if (tierFilter.value) list = list.filter(c => c.clv_tier === tierFilter.value)
  if (riskFilter.value) list = list.filter(c => c.churn_risk === riskFilter.value)
  if (rfmFilter.value) list = list.filter(c => c.rfm_segment === rfmFilter.value)
  return list
})
const recentCustomerDetails = computed(() => {
  const allCustomers: CustomerRow[] = (props.data.customers ?? []) as unknown as CustomerRow[]
  return recentCustomerIds.value
    .map((id: string) => allCustomers.find((c: CustomerRow) => c.customer_id === id))
    .filter((c): c is CustomerRow => c !== undefined)
})

// ── Rankings scorecard (unified, filterable, sortable) ──────────────────────
// The scorecard endpoint carries revenue/profit/margin/months/consistency;
// tier, segment, risk and health come from the shell's customer payload,
// joined by customer id so the Rankings tab shares one row per customer.
const rankMeta = computed(() => {
  const m = new Map<string, CustomerRow>()
  for (const c of ((props.data.customers ?? []) as unknown as CustomerRow[])) {
    if (c.customer_id) m.set(String(c.customer_id), c)
  }
  return m
})
const scorecardRows = computed<ScorecardRow[]>(() => {
  const meta = rankMeta.value
  let rows = (scorecard.value?.customers ?? []).map((r) => {
    const md = meta.get(String(r.customer))
    return {
      ...r,
      clv_tier: md?.clv_tier,
      rfm_segment: md?.rfm_segment ?? r.rfm_segment,
      churn_risk: md?.churn_risk,
      health_status: md?.health_status,
      health_score: md?.health_score,
    } as ScorecardRow
  })
  const q = rankSearch.value.trim().toLowerCase()
  if (q) {
    rows = rows.filter(r =>
      [r.customer_name, r.customer].some(v => typeof v === 'string' && v.toLowerCase().includes(q)))
  }
  if (rankTier.value) rows = rows.filter(r => r.clv_tier === rankTier.value)
  if (rankSegment.value) rows = rows.filter(r => r.rfm_segment === rankSegment.value)
  if (rankRisk.value) rows = rows.filter(r => r.churn_risk === rankRisk.value)
  const gte = (v: number | undefined, min: string) => {
    const n = parseFloat(min)
    return Number.isNaN(n) || (typeof v === 'number' && v >= n)
  }
  rows = rows.filter(r =>
    gte(r.revenue, minRevenue.value) &&
    gte(r.gross_profit, minGrossProfit.value) &&
    gte(r.margin_pct, minMargin.value) &&
    gte(r.months_active, minMonths.value) &&
    gte(r.consistency_score, minScore.value))
  const key = rankSort.value
  const dir = rankDir.value === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => (Number(a[key] ?? 0) - Number(b[key] ?? 0)) * dir)
})
function setRankSort(key: RankSortKey) {
  if (rankSort.value === key) rankDir.value = rankDir.value === 'asc' ? 'desc' : 'asc'
  else { rankSort.value = key; rankDir.value = 'desc' }
}
function clearRankFilters() {
  rankSearch.value = ''
  rankTier.value = ''
  rankSegment.value = ''
  rankRisk.value = ''
  minRevenue.value = ''
  minGrossProfit.value = ''
  minMargin.value = ''
  minMonths.value = ''
  minScore.value = ''
}
const atRiskCustomers = computed(() => (props.data.at_risk_customers ?? []) as unknown[])
const topCustomers = computed(() => (props.data.top_customers ?? []) as unknown[])
const geoAnalysis = computed(() => (props.data.geographic_analysis ?? {}) as any)
const territoryGeo = computed(() => (geoAnalysis.value.territory_geo ?? {}) as Record<string, unknown>)
const territoryWorld = computed<GeoPoint[]>(() => (territoryGeo.value.world ?? []) as GeoPoint[])
const territoryIndia = computed<GeoPoint[]>(() => (territoryGeo.value.india ?? []) as GeoPoint[])
const territoryUnmapped = computed<UnmappedTerritory[]>(() => (territoryGeo.value.unmapped ?? []) as UnmappedTerritory[])
const mappedCustomers = computed(() => territoryWorld.value.reduce((s, r) => s + (Number(r.value) || 0), 0))
const unmappedCustomers = computed(() => territoryUnmapped.value.reduce((s, r) => s + (Number(r.value) || 0), 0))
const mapCoveragePct = computed(() => {
  const total = mappedCustomers.value + unmappedCustomers.value
  return total > 0 ? (mappedCustomers.value / total) * 100 : 0
})
const paretoAnalysis = computed(() => (props.data.pareto_analysis ?? {}) as Record<string, unknown>)
const cohortAnalysis = computed(() => (props.data.cohort_analysis ?? {}) as Record<string, unknown>)
const nextActions = computed(() => (props.data.next_best_actions ?? []) as ActionItem[])

// ── Actions (next best actions) ────────────────────────────────────────────
// Each action leads with the real ledger figure at stake, not just advice:
// churn/re-engagement risk the booked revenue (`historical_clv`), payment
// follow-up the `outstanding_amount`, upsell/nurture the predicted 12-month
// forward value. All quantification, filtering and sorting is client-side.
type MoneyField = 'historical_clv' | 'outstanding_amount' | 'predicted_12m_clv'
const ACTION_MONEY: Record<string, { label: string; field: MoneyField }> = {
  CHURN_PREVENTION:     { label: 'Revenue at risk',     field: 'historical_clv' },
  RE_ENGAGEMENT:        { label: 'Revenue at risk',     field: 'historical_clv' },
  PAYMENT_FOLLOW_UP:    { label: 'Outstanding',         field: 'outstanding_amount' },
  UPSELL_OPPORTUNITY:   { label: '12-mo forward value', field: 'predicted_12m_clv' },
  NEW_CUSTOMER_NURTURE: { label: '12-mo forward value', field: 'predicted_12m_clv' },
}
const actionTypeOptions = [
  { value: '', label: 'All action types' },
  { value: 'CHURN_PREVENTION', label: 'Churn prevention' },
  { value: 'RE_ENGAGEMENT', label: 'Re-engagement' },
  { value: 'PAYMENT_FOLLOW_UP', label: 'Payment follow-up' },
  { value: 'UPSELL_OPPORTUNITY', label: 'Upsell opportunity' },
  { value: 'NEW_CUSTOMER_NURTURE', label: 'New customer nurture' },
]
const actionPriorityOptions = [
  { value: '', label: 'All priorities' },
  { value: 'High', label: 'High priority' },
  { value: 'Medium', label: 'Medium priority' },
]
const actionType = ref('')
const actionPriority = ref('')

function recImpact(item: ActionItem, rec: ActionRec): number {
  const m = ACTION_MONEY[rec.action]
  return m ? Number(item[m.field] ?? 0) : 0
}
function recImpactLabel(rec: ActionRec): string {
  return ACTION_MONEY[rec.action]?.label ?? ''
}
// Largest single ledger figure at stake for the customer. Uses max, not sum,
// so two recs pointing at the same field (churn + re-engagement) don't
// double-count the one revenue relationship.
function atStake(item: ActionItem): number {
  return item.recommendations.reduce((mx, r) => Math.max(mx, recImpact(item, r)), 0)
}
function hasHighPriority(item: ActionItem): boolean {
  return item.recommendations.some(r => r.priority === 'High')
}
const filteredActions = computed<ActionItem[]>(() => {
  let list = nextActions.value
  if (actionType.value) list = list.filter(a => a.recommendations.some(r => r.action === actionType.value))
  if (actionPriority.value) list = list.filter(a => a.recommendations.some(r => r.priority === actionPriority.value))
  // High-priority customers first, then biggest money at stake.
  return [...list].sort((a, b) =>
    (Number(hasHighPriority(b)) - Number(hasHighPriority(a))) || (atStake(b) - atStake(a)))
})
// Impact summary — one action item is one customer, so these sums never
// double-count a customer across its own recommendations.
const actionsSummary = computed(() => {
  let revenueAtRisk = 0, outstanding = 0, upside = 0, high = 0
  for (const a of nextActions.value) {
    const kinds = new Set(a.recommendations.map(r => r.action))
    if (kinds.has('CHURN_PREVENTION') || kinds.has('RE_ENGAGEMENT')) revenueAtRisk += Number(a.historical_clv ?? 0)
    if (kinds.has('PAYMENT_FOLLOW_UP')) outstanding += Number(a.outstanding_amount ?? 0)
    if (kinds.has('UPSELL_OPPORTUNITY') || kinds.has('NEW_CUSTOMER_NURTURE')) upside += Number(a.predicted_12m_clv ?? 0)
    if (hasHighPriority(a)) high++
  }
  return { revenueAtRisk, outstanding, upside, high, total: nextActions.value.length }
})
function clearActionFilters() { actionType.value = ''; actionPriority.value = '' }
// `totalCrossSellRecommendations`, `crossSellData`, `loadCrossSellData`,
// `revenueSplit`/`loadRevenueSplit` and `variance`/`loadVariance` were removed:
// all were computed or fetched but never rendered. The revenue-split and
// variance calls fired on mount AND on every date-filter change, so each page
// view and each filter touch spent two round trips producing data nothing read.
const maxDayOfWeekOrders = computed((): number => {
  const rows: DayOfWeekDataRow[] = (purchasePatternsData.value?.day_of_week?.data ?? []) as unknown as DayOfWeekDataRow[]
  if (!rows.length) return 1
  return Math.max(...rows.map(d => d.order_count))
})

// ── Money formatter (server currency) ──────────────────────────────────────
function money(value: number | undefined | null): string {
  return formatCurrency(value, baseCurrency.value)
}

// ── Severity helpers ───────────────────────────────────────────────────────
function healthSeverity(status: string | undefined | null): Severity {
  // Backend `_classify_health()` only ever returns these four buckets.
  const map: Record<string, Severity> = {
    Excellent: 'none', Healthy: 'none',
    'At Risk': 'high', Critical: 'critical',
  }
  return map[String(status ?? '')] ?? 'none'
}
function churnSeverity(risk: string | undefined | null): Severity {
  const r = String(risk ?? '').toLowerCase()
  if (r === 'critical' || r === 'high') return 'high'
  if (r === 'medium') return 'medium'
  return 'none'
}
function retentionSeverity(pct: number | undefined): Severity {
  return scoreSeverity(pct, { good: 50, warn: 25, higherIsBetter: true })
}

// ── Lazy loaders ──────────────────────────────────────────────────────────
async function loadPurchasePatterns() {
  if (purchasePatternsData.value) return
  isLoadingPatterns.value = true
  try {
    purchasePatternsData.value = await apiCall('insights.api.ml.purchase_patterns', {
      top_percentile: 20,
    }) as Record<string, unknown>
  } catch (e: unknown) {
    const { message } = readFrappeError(e, 'Could not load purchase patterns')
    console.error('Failed to load purchase patterns:', message)
  } finally {
    isLoadingPatterns.value = false
  }
}

async function loadCustomerCounts() {
  try {
    counts.value = await apiCall('insights.api.ml.customer.customer_counts', {
      date_filter: props.dateFilter,
      active_cutoff_months: activeCutoff.value,
    }) as Record<string, unknown>
  } catch (e: unknown) {
    console.error('Failed to load customer counts:', readFrappeError(e).message)
  }
}

async function loadRankings() {
  isLoadingRankings.value = true
  try {
    scorecard.value = await apiCall('insights.api.ml.customer.customer_scorecard', {
      date_filter: props.dateFilter,
    }) as ScorecardData
  } catch (e: unknown) {
    console.error('Failed to load rankings:', readFrappeError(e).message)
  } finally {
    isLoadingRankings.value = false
  }
}


// ── Watchers ───────────────────────────────────────────────────────────────
watch(activeCutoff, () => loadCustomerCounts())
watch(() => props.activeTab, (tab) => {
  if (tab === 'cust-patterns') loadPurchasePatterns()
  if (tab === 'cust-rankings') loadRankings()
})

watch(() => props.dateFilter, () => {
  loadCustomerCounts()
  loadRankings()
})

onMounted(() => {
  recentCustomerIds.value = getRecentCustomers()
  loadCustomerCounts()
  loadRankings()
})
</script>

<template>
  <!-- Customer counts strip: always visible above tab content -->
  <div v-if="counts" class="mb-6">
    <dl class="grid grid-cols-2 gap-x-6 gap-y-4 rounded-lg border border-outline-gray-1 bg-card p-4 sm:grid-cols-4 xl:grid-cols-8">
      <div class="min-w-0">
        <dt class="text-sm text-ink-gray-6">Total</dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">{{ formatNumber(counts.total as number) }}</dd>
      </div>
      <div class="min-w-0">
        <dt class="text-sm text-ink-gray-6">New</dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">{{ formatNumber(counts.new_by_creation as number) }}</dd>
      </div>
      <div class="min-w-0">
        <dt class="text-sm text-ink-gray-6">Existing</dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">{{ formatNumber(counts.existing as number) }}</dd>
      </div>
      <div class="min-w-0">
        <dt class="text-sm text-ink-gray-6">Active</dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">{{ formatNumber(counts.active as number) }}</dd>
      </div>
      <div class="min-w-0">
        <dt class="text-sm text-ink-gray-6">Inactive</dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">{{ formatNumber(counts.inactive as number) }}</dd>
      </div>
      <div class="min-w-0">
        <dt class="text-sm text-ink-gray-6">Advance pay</dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">{{ formatNumber(counts.advance_payment as number) }}</dd>
      </div>
      <div class="min-w-0">
        <dt class="text-sm text-ink-gray-6">Manufacturers</dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">{{ formatNumber(counts.manufacturers as number) }}</dd>
      </div>
      <div class="min-w-0">
        <dt class="text-sm text-ink-gray-6">Traders</dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">{{ formatNumber(counts.traders as number) }}</dd>
      </div>
    </dl>
  </div>

  <!-- Active Cutoff Selector -->
  <div class="mb-4">
    <Select
      v-model="activeCutoff"
      :options="[
        { value: '3', label: 'Active: 3 months' },
        { value: '6', label: 'Active: 6 months' },
        { value: '12', label: 'Active: 12 months' },
      ]"
      class="text-sm"
    />
  </div>

  <!-- ═══ Overview ═══ -->
  <div v-if="activeTab === 'cust-overview'" class="grid gap-6 lg:grid-cols-2">
    <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
      <SectionHeader variant="caption" title="CLV Tier Distribution" :level="3" />
      <div class="space-y-3 mt-4">
        <div v-for="(count, tier) in (summary.clv_tier_distribution as Record<string, number>)" :key="tier"
          class="flex items-center gap-3">
          <span class="flex-1 text-ink-gray-7">{{ tier }}</span>
          <span class="tnum font-medium text-ink-gray-9">{{ formatNumber(count) }}</span>
          <div class="w-24 h-2 bg-surface-gray-2 rounded-full" role="img" :aria-label="'CLV Tier ' + tier + ': ' + count">
            <div class="bg-surface-gray-4 h-full rounded-full" :style="{ width: `${(count / (summary.total_customers as number)) * 100}%` }" />
          </div>
        </div>
      </div>
    </div>

    <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
      <SectionHeader variant="caption" title="Churn Risk Distribution" :level="3" />
      <div class="space-y-3 mt-4">
        <div v-for="(count, risk) in (summary.churn_risk_distribution as Record<string, number>)" :key="risk"
          class="flex items-center gap-3">
          <Badge v-bind="severityBadge(churnSeverity(String(risk)))" :label="String(risk)" size="sm" />
          <span class="flex-1" />
          <span class="tnum font-medium text-ink-gray-9">{{ formatNumber(count) }}</span>
          <span class="text-sm text-ink-gray-6">{{ formatPercent((count / (summary.total_customers as number)) * 100) }}</span>
        </div>
      </div>
    </div>

    <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
      <SectionHeader variant="caption" title="80/20 Analysis" :level="3" />
      <div class="space-y-4 mt-4">
        <div class="flex items-center justify-between p-3 rounded-lg bg-surface-gray-1">
          <span class="text-ink-gray-7">Top 10% contribute</span>
          <span class="text-xl font-bold text-ink-gray-9">{{ formatPercent(paretoAnalysis.top_10_percent_contribute as number) }}</span>
        </div>
        <div class="flex items-center justify-between p-3 rounded-lg bg-surface-gray-1">
          <span class="text-ink-gray-7">Top 20% contribute</span>
          <span class="text-xl font-bold text-ink-gray-9">{{ formatPercent(paretoAnalysis.top_20_percent_contribute as number) }}</span>
        </div>
        <div class="flex items-center justify-between p-3 rounded-lg bg-surface-gray-1">
          <span class="text-ink-gray-7">Customers for 80% revenue</span>
          <span class="text-xl font-bold text-ink-gray-9">{{ formatPercent(paretoAnalysis.top_80_percent_customers as number) }}</span>
        </div>
      </div>
    </div>

    <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
      <SectionHeader variant="caption" title="Health Distribution" :level="3" />
      <div class="space-y-3 mt-4">
        <div v-for="(count, status) in (summary.health_distribution as Record<string, number>)" :key="status"
          class="flex items-center gap-3">
          <Badge v-bind="severityBadge(healthSeverity(String(status)))" :label="String(status)" size="sm" />
          <span class="flex-1" />
          <span class="tnum font-medium text-ink-gray-9">{{ formatNumber(count) }}</span>
          <span class="text-sm text-ink-gray-6">{{ formatPercent((count / (summary.total_customers as number)) * 100) }}</span>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ Customers (list) ═══ -->
  <div v-if="activeTab === 'cust-list'" class="space-y-4">
    <div class="flex flex-wrap gap-4 p-4 bg-surface-white rounded-lg border border-outline-gray-1">
      <div class="flex-1 min-w-[200px]">
        <FormControl
          v-model="customerFilter" type="text" :debounce="300"
          placeholder="Search by name, ID, or territory..."
          aria-label="Search customers"
        >
          <template #prefix>
            <Search class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
          </template>
        </FormControl>
      </div>
      <div class="flex items-center gap-2">
        <Filter class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
        <Select v-model="tierFilter" :options="tierFilterOptions" aria-label="Filter by tier" class="text-sm" />
        <Select v-model="rfmFilter" :options="rfmSegmentFilterOptions" aria-label="Filter by RFM segment" class="text-sm" />
        <Select v-model="riskFilter" :options="riskFilterOptions" aria-label="Filter by risk level" class="text-sm" />
      </div>
      <span class="self-center text-sm text-ink-gray-6">
        {{ customers.length }} of {{ (props.data.customers as unknown[])?.length || 0 }} customers
      </span>
    </div>

    <div v-if="recentCustomerDetails.length > 0 && !customerFilter && !tierFilter && !riskFilter && !rfmFilter"
      class="flex items-center gap-3 px-1">
      <Star class="w-4 h-4 text-ink-gray-5 flex-shrink-0" aria-hidden="true" />
      <span class="text-sm font-medium text-ink-gray-6">Recent:</span>
      <div class="flex gap-2 flex-wrap">
        <Button v-for="rc in recentCustomerDetails" :key="rc.customer_id" variant="subtle" size="sm"
          @click="viewCustomerDetail(rc.customer_id)">
          {{ rc.customer_name }}
        </Button>
      </div>
    </div>

    <div class="overflow-hidden bg-surface-white rounded-lg border border-outline-gray-1">
      <table class="w-full">
        <caption class="sr-only">Customers by lifetime value, highest first. Shows up to 100 rows of the filtered set.</caption>
        <thead class="bg-surface-gray-1">
          <tr>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-left text-ink-gray-6">Customer</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-left text-ink-gray-6">RFM Segment</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-left text-ink-gray-6">CLV Tier</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Total CLV</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-center text-ink-gray-6">Health</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-center text-ink-gray-6">Churn Risk</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Orders</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Recency</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-center text-ink-gray-6"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-gray-1">
          <tr v-for="customer in customers.slice(0, 100)" :key="customer.customer_id"
            class="hover:bg-surface-gray-1 cursor-pointer transition-colors motion-reduce:transition-none"
            tabindex="0"
            @click="viewCustomerDetail(customer.customer_id)"
            @keydown.enter="viewCustomerDetail(customer.customer_id)">
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <div>
                  <p class="font-medium text-ink-gray-8">{{ customer.customer_name }}</p>
                  <p class="text-sm text-ink-gray-6">{{ customer.territory || 'No territory' }}</p>
                </div>
              </div>
            </td>
            <td class="px-4 py-3"><Badge theme="gray" variant="subtle" :label="customer.rfm_segment || '-'" size="sm" /></td>
            <td class="px-4 py-3"><Badge theme="gray" variant="subtle" :label="customer.clv_tier || '-'" size="sm" /></td>
            <td class="px-4 py-3 text-right tnum font-medium text-ink-gray-8">{{ money(customer.total_clv || customer.historical_clv) }}</td>
            <td class="px-4 py-3 text-center">
              <Badge v-bind="severityBadge(healthSeverity(customer.health_status))" :label="String(Math.round(customer.health_score || 0))" size="sm" />
            </td>
            <td class="px-4 py-3 text-center">
              <Badge v-bind="severityBadge(churnSeverity(customer.churn_risk))" :label="customer.churn_risk || '-'" size="sm" />
            </td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-7">{{ customer.order_count }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-6">{{ Math.round(customer.recency_days || 0) }}d</td>
            <td class="px-4 py-3 text-center"><ChevronRight class="w-4 h-4 text-ink-gray-5 inline" aria-hidden="true" /></td>
          </tr>
        </tbody>
      </table>
      <div v-if="customers.length > 100" class="px-4 py-3 text-sm text-center text-ink-gray-6 bg-surface-gray-1">
        Showing 100 of {{ customers.length }} customers
      </div>
    </div>
  </div>

  <!-- ═══ Geography ═══ -->
  <div v-if="activeTab === 'cust-geography'" class="space-y-6">
    <div class="grid gap-4 sm:grid-cols-3">
      <KpiCard label="Territories covered" :value="formatNumber(geoAnalysis.coverage?.territories_covered)" />
      <KpiCard label="Customer groups" :value="formatNumber(geoAnalysis.coverage?.customer_groups_covered)" />
      <KpiCard label="Total revenue" :amount="geoAnalysis.coverage?.total_revenue as number" :currency="baseCurrency" />
    </div>

    <div class="rounded-lg border border-outline-gray-1 bg-card">
      <div class="h-[500px]">
        <TerritoryMap
          :worldData="territoryWorld"
          :indiaData="territoryIndia"
          :unmapped="territoryUnmapped"
          metric="Customers"
          colorScale="blue"
        />
      </div>
      <p v-if="unmappedCustomers > 0" class="border-t border-outline-gray-1 px-4 py-3 text-sm text-ink-gray-6">
        Shaded regions cover {{ formatNumber(mappedCustomers) }} of
        {{ formatNumber(mappedCustomers + unmappedCustomers) }} customers
        ({{ formatPercent(mapCoveragePct) }}). City territories are counted
        under their parent state, so click India to see them. The remainder
        have no usable parent territory and are listed below the map.
      </p>
    </div>

    <div class="overflow-hidden bg-surface-white rounded-lg border border-outline-gray-1">
      <div class="px-4 py-3 border-b border-outline-gray-1">
        <SectionHeader variant="caption" title="Territory Performance" :level="3" />
      </div>
      <table class="w-full">
        <caption class="sr-only">Territory performance by customer count, revenue, revenue share, and health.</caption>
        <thead class="bg-surface-gray-1">
          <tr>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-left text-ink-gray-6">Territory</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Customers</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Revenue</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Share</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Avg AOV</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Health</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-gray-1">
          <tr v-for="territory in (geoAnalysis.territory_analysis as Record<string, unknown>[])?.slice(0, 20)" :key="territory.territory as string"
            class="hover:bg-surface-gray-1">
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <MapPin class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
                <span class="font-medium text-ink-gray-8">{{ territory.territory || 'Unassigned' }}</span>
              </div>
            </td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-7">{{ territory.customer_count }}</td>
            <td class="px-4 py-3 text-right tnum font-medium text-ink-gray-8">{{ money(territory.total_revenue as number) }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-6">{{ formatPercent(territory.revenue_share as number) }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-7">{{ money(territory.avg_order_value as number) }}</td>
            <td class="px-4 py-3 text-right">
              <Badge v-bind="severityBadge(scoreSeverity(territory.avg_health_score as number, { good: 60, warn: 40, higherIsBetter: true }))"
                :label="String(Math.round(territory.avg_health_score as number))" size="sm" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- ═══ Actions ═══ -->
  <div v-if="activeTab === 'cust-actions'" class="space-y-6">
    <!-- Impact summary: money at stake, not just a count -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      <KpiCard label="Revenue at risk" :amount="actionsSummary.revenueAtRisk" :currency="baseCurrency"
        sublabel="churn + re-engagement" :severity="actionsSummary.revenueAtRisk > 0 ? 'high' : undefined" />
      <KpiCard label="Outstanding to collect" :amount="actionsSummary.outstanding" :currency="baseCurrency"
        sublabel="payment follow-ups" :severity="actionsSummary.outstanding > 0 ? 'medium' : undefined" />
      <KpiCard label="Upsell + nurture upside" :amount="actionsSummary.upside" :currency="baseCurrency"
        sublabel="predicted 12-mo value" />
      <KpiCard label="Customers flagged" :value="actionsSummary.total"
        :sublabel="`${actionsSummary.high} high priority`" />
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-center gap-3 p-4 bg-surface-white rounded-lg border border-outline-gray-1">
      <Filter class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
      <Select v-model="actionType" :options="actionTypeOptions" aria-label="Filter by action type" class="text-sm" />
      <Select v-model="actionPriority" :options="actionPriorityOptions" aria-label="Filter by priority" class="text-sm" />
      <Button variant="outline" label="Clear filters" @click="clearActionFilters" />
      <span class="ml-auto text-sm text-ink-gray-6">{{ filteredActions.length }} of {{ nextActions.length }} customers</span>
    </div>

    <!-- Empty state -->
    <div v-if="!filteredActions.length" class="p-10 text-center bg-surface-white rounded-lg border border-outline-gray-1">
      <Target class="w-8 h-8 mx-auto text-ink-gray-4" aria-hidden="true" />
      <p class="mt-3 text-sm text-ink-gray-6">No action items match the current filters.</p>
    </div>

    <!-- Action cards, biggest money at stake first -->
    <div v-else class="space-y-3">
      <div v-for="item in filteredActions.slice(0, 50)" :key="item.customer_id"
        class="bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
        <!-- Header: customer, tier/risk/health, money at stake, drill-in -->
        <button type="button"
          class="w-full flex items-center justify-between gap-4 px-4 py-3 text-left hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
          @click="viewCustomerDetail(item.customer_id)">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h4 class="font-semibold text-ink-gray-9 truncate">{{ item.customer_name }}</h4>
              <Badge v-if="hasHighPriority(item)" theme="red" variant="subtle" label="High priority" size="sm" />
            </div>
            <div class="flex flex-wrap items-center gap-2 mt-1">
              <Badge theme="gray" variant="subtle" :label="item.clv_tier || '-'" size="sm" />
              <Badge v-bind="severityBadge(churnSeverity(item.churn_risk))" :label="(item.churn_risk || '-') + ' risk'" size="sm" />
              <Badge v-bind="severityBadge(healthSeverity(item.health_status))" :label="item.health_status || '-'" size="sm" />
            </div>
          </div>
          <div class="flex items-center gap-3 shrink-0">
            <div class="text-right">
              <div class="text-xs text-ink-gray-5">At stake</div>
              <div class="font-semibold tnum text-ink-gray-9">{{ money(atStake(item)) }}</div>
            </div>
            <ChevronRight class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
          </div>
        </button>
        <!-- Recommendations, each with its own money figure -->
        <div class="divide-y divide-outline-gray-1 border-t border-outline-gray-1">
          <div v-for="rec in item.recommendations" :key="rec.action" class="px-4 py-3">
            <div class="flex items-center justify-between gap-3 mb-1">
              <span class="text-sm font-semibold text-ink-gray-8">{{ actionLabel(rec.action) }}</span>
              <div class="flex items-center gap-2 shrink-0">
                <span v-if="recImpact(item, rec) > 0" class="text-sm tnum text-ink-gray-6">
                  {{ recImpactLabel(rec) }}: <span class="font-medium text-ink-gray-9">{{ money(recImpact(item, rec)) }}</span>
                </span>
                <Badge v-bind="severityBadge(prioritySeverity(rec.priority))" :label="rec.priority" size="sm" />
              </div>
            </div>
            <p class="text-sm text-ink-gray-7">{{ rec.description }}</p>
            <p class="mt-1 text-sm text-ink-gray-6">{{ rec.suggestion }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ Cohorts ═══ -->
  <div v-if="activeTab === 'cust-cohorts'" class="space-y-6">
    <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
      <SectionHeader variant="caption" title="Average Retention by Month" :level="3" />
      <div class="flex flex-wrap gap-2 mt-4">
        <div v-for="(retention, month) in (cohortAnalysis.average_retention as Record<string, number>)" :key="month"
          class="px-3 py-2 text-center bg-surface-gray-1 rounded-lg">
          <p class="text-sm text-ink-gray-6">Month {{ month }}</p>
          <p class="text-lg font-bold text-ink-gray-9">{{ formatPercent(retention) }}</p>
        </div>
      </div>
    </div>
    <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
      <SectionHeader variant="caption" title="Cohort Retention Matrix" :level="3" />
      <div class="overflow-x-auto mt-4">
        <table class="w-full text-sm">
          <caption class="sr-only">Cohort retention by month since first purchase.</caption>
          <thead>
            <tr>
              <th scope="col" class="px-3 py-2 text-left text-ink-gray-6">Cohort</th>
              <th scope="col" class="px-3 py-2 text-right text-ink-gray-6">Size</th>
              <th v-for="n in 12" :key="n" scope="col" class="px-3 py-2 text-center text-ink-gray-6">M{{ n - 1 }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="cohort in (cohortAnalysis.cohort_retention as Record<string, unknown>[])" :key="cohort.cohort as string">
              <td class="px-3 py-2 font-medium text-ink-gray-8">{{ cohort.cohort }}</td>
              <td class="px-3 py-2 text-right text-ink-gray-7">{{ cohort.size }}</td>
              <td v-for="n in 12" :key="n" class="px-3 py-2 text-center">
                <Badge v-if="(cohort.retention as Record<string, number>)[n - 1] !== undefined"
                  v-bind="severityBadge(retentionSeverity((cohort.retention as Record<string, number>)[n - 1]))"
                  :label="formatPercent((cohort.retention as Record<string, number>)[n - 1])" size="sm" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ═══ Patterns ═══ -->
  <div v-if="activeTab === 'cust-patterns'" class="space-y-6">
    <div v-if="isLoadingPatterns" class="flex items-center justify-center h-64">
      <div class="text-center space-y-3">
        <SkeletonBlock class="h-24 w-96 rounded-xl mx-auto" />
        <p class="text-sm text-ink-gray-6">Loading purchase patterns...</p>
      </div>
    </div>

    <div v-else-if="purchasePatternsData?.status === 'error'"
      class="rounded-lg border border-outline-gray-1 bg-card p-6">
      <p class="text-sm font-medium text-ink-gray-8">Purchase pattern analysis could not be completed.</p>
      <p class="mt-1 text-sm text-ink-gray-6">{{ purchasePatternsData.message || 'The analysis returned an error.' }}</p>
    </div>

    <div v-else-if="purchasePatternsData">
      <div class="p-4 bg-surface-gray-1 rounded-lg border border-outline-gray-1">
        <p class="text-sm text-ink-gray-7">
          <strong>Analysis Scope:</strong> Top {{ purchasePatternsData.analysis_scope?.top_percentile }}% of customers by CLV
          ({{ purchasePatternsData.analysis_scope?.customer_count }} customers, {{ purchasePatternsData.analysis_scope?.transaction_count }} transactions)
        </p>
      </div>

      <div class="grid gap-4 lg:grid-cols-4">
        <KpiCard
          label="Total Orders"
          :value="formatNumber(purchasePatternsData.summary?.total_orders as number)"
          variant="tile"
        />
        <KpiCard
          label="Total Revenue"
          :value="money(purchasePatternsData.summary?.total_revenue as number)"
          variant="tile"
        />
        <KpiCard
          label="Peak Day"
          :value="purchasePatternsData.summary?.peak_day as string | undefined"
          variant="tile"
        />
        <KpiCard
          label="Peak Month"
          :value="purchasePatternsData.summary?.peak_month as string | undefined"
          variant="tile"
        />
      </div>

      <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
        <SectionHeader variant="caption" title="Day of Week Analysis" :level="3" />
        <div class="overflow-x-auto mt-4">
          <table class="w-full text-sm">
            <caption class="sr-only">Order activity by day of week.</caption>
            <thead class="bg-surface-gray-1">
              <tr>
                <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Day</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Orders</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Revenue</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Gross Profit</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Avg Order</th>
                <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Activity</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="day in (purchasePatternsData.day_of_week?.data as Record<string, unknown>[])" :key="day.day_name as string"
                :class="day.day_name === purchasePatternsData.day_of_week?.peak_day ? 'bg-surface-gray-1' : 'hover:bg-surface-gray-1'">
                <td class="px-4 py-2 font-medium text-ink-gray-8">
                  {{ day.day_name }}
                  <Badge v-if="day.day_name === purchasePatternsData.day_of_week?.peak_day" theme="gray" variant="subtle" label="Peak" size="sm" class="ml-2" />
                </td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ formatNumber(day.order_count as number) }}</td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ money(day.total_revenue as number) }}</td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ money(day.gross_profit as number) }}</td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ money(day.avg_order_value as number) }}</td>
                <td class="px-4 py-2">
                  <div class="w-full bg-surface-gray-2 rounded-full h-2" role="img" :aria-label="'Activity bar: ' + day.day_name">
                    <div class="bg-surface-gray-4 h-2 rounded-full" :style="{ width: `${maxDayOfWeekOrders > 0 ? ((day.order_count as number) / maxDayOfWeekOrders) * 100 : 0}%` }" />
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
        <SectionHeader variant="caption" title="Monthly Trends" :level="3" />
        <div class="overflow-x-auto mt-4">
          <table class="w-full text-sm">
            <caption class="sr-only">Order activity by month.</caption>
            <thead class="bg-surface-gray-1">
              <tr>
                <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Month</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Orders</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Revenue</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Gross Profit</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Avg Order</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="month in (purchasePatternsData.monthly?.data as Record<string, unknown>[])" :key="month.month_name as string"
                :class="month.month_name === purchasePatternsData.monthly?.peak_month ? 'bg-surface-gray-1' : 'hover:bg-surface-gray-1'">
                <td class="px-4 py-2 font-medium text-ink-gray-8">
                  {{ month.month_name }}
                  <Badge v-if="month.month_name === purchasePatternsData.monthly?.peak_month" theme="gray" variant="subtle" label="Peak" size="sm" class="ml-2" />
                </td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ formatNumber(month.order_count as number) }}</td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ money(month.total_revenue as number) }}</td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ money(month.gross_profit as number) }}</td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ money(month.avg_order_value as number) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
        <SectionHeader variant="caption" title="Seasonal Patterns" :level="3" />
        <div class="grid gap-4 lg:grid-cols-4 mt-4">
          <div v-for="season in (purchasePatternsData.seasonal?.data as Record<string, unknown>[])" :key="season.quarter as string"
            :class="[
              'p-4 rounded-lg border',
              season.quarter === purchasePatternsData.seasonal?.peak_quarter
                ? 'border-outline-gray-2 bg-surface-gray-2'
                : 'border-outline-gray-1 bg-surface-white'
            ]">
            <p class="text-sm font-medium text-ink-gray-7">{{ season.quarter }}</p>
            <p class="text-xl font-bold text-ink-gray-9">{{ money(season.total_revenue as number) }}</p>
            <p class="text-sm text-ink-gray-6">{{ formatNumber(season.order_count as number) }} orders</p>
            <p class="text-sm text-ink-gray-6">Avg: {{ money(season.avg_order_value as number) }}</p>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="text-center py-12">
      <Activity class="w-12 h-12 mx-auto text-ink-gray-4" aria-hidden="true" />
      <p class="mt-4 text-ink-gray-6">No purchase pattern data available</p>
    </div>
  </div>

  <!-- ═══ Rankings ═══ -->
  <div v-if="activeTab === 'cust-rankings'" class="p-6 space-y-4">
    <!-- Category filters -->
    <div class="flex flex-wrap items-center gap-3 p-4 bg-surface-white rounded-lg border border-outline-gray-1">
      <div class="flex-1 min-w-[200px]">
        <FormControl v-model="rankSearch" type="text" :debounce="300"
          placeholder="Search by name or ID..." aria-label="Search customers">
          <template #prefix><Search class="w-4 h-4 text-ink-gray-5" aria-hidden="true" /></template>
        </FormControl>
      </div>
      <Filter class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
      <Select v-model="rankTier" :options="tierFilterOptions" aria-label="Filter by tier" class="text-sm" />
      <Select v-model="rankSegment" :options="rfmSegmentFilterOptions" aria-label="Filter by segment" class="text-sm" />
      <Select v-model="rankRisk" :options="riskFilterOptions" aria-label="Filter by risk level" class="text-sm" />
    </div>
    <!-- Numeric thresholds -->
    <div class="flex flex-wrap items-end gap-3 p-4 bg-surface-white rounded-lg border border-outline-gray-1">
      <label class="text-xs text-ink-gray-6">Min Revenue
        <FormControl v-model="minRevenue" type="number" placeholder="0" aria-label="Minimum revenue" class="mt-1 w-32" />
      </label>
      <label class="text-xs text-ink-gray-6">Min Gross Profit
        <FormControl v-model="minGrossProfit" type="number" placeholder="0" aria-label="Minimum gross profit" class="mt-1 w-32" />
      </label>
      <label class="text-xs text-ink-gray-6">Min Margin %
        <FormControl v-model="minMargin" type="number" placeholder="0" aria-label="Minimum margin percent" class="mt-1 w-24" />
      </label>
      <label class="text-xs text-ink-gray-6">Min Months Active
        <FormControl v-model="minMonths" type="number" placeholder="0" aria-label="Minimum months active" class="mt-1 w-24" />
      </label>
      <label class="text-xs text-ink-gray-6">Min Score
        <FormControl v-model="minScore" type="number" placeholder="0" aria-label="Minimum consistency score" class="mt-1 w-24" />
      </label>
      <Button variant="outline" label="Clear filters" @click="clearRankFilters" />
    </div>

    <div v-if="isLoadingRankings && !scorecard" class="text-center py-12">
      <Activity class="w-12 h-12 mx-auto text-ink-gray-4 animate-pulse" aria-hidden="true" />
      <p class="mt-4 text-ink-gray-6">Loading customer scorecard…</p>
    </div>

    <div v-else class="overflow-hidden bg-surface-white rounded-lg border border-outline-gray-1">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <caption class="sr-only">Customer scorecard with revenue, gross profit, margin, months active and consistency. Click a metric header to sort, or a row to drill into that customer's orders.</caption>
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-3 text-left font-medium text-ink-gray-6">Customer</th>
              <th scope="col" class="px-4 py-3 text-left font-medium text-ink-gray-6">Tier</th>
              <th scope="col" class="px-4 py-3 text-left font-medium text-ink-gray-6">Segment</th>
              <th scope="col" class="px-4 py-3 text-left font-medium text-ink-gray-6">Risk</th>
              <th v-for="col in sortableCols" :key="col.key" scope="col"
                class="px-4 py-3 text-right font-medium text-ink-gray-6 cursor-pointer select-none hover:text-ink-gray-8"
                :aria-sort="rankSort === col.key ? (rankDir === 'asc' ? 'ascending' : 'descending') : 'none'"
                @click="setRankSort(col.key)">
                <span class="inline-flex items-center gap-1 justify-end">
                  {{ col.label }}
                  <ChevronRight v-if="rankSort === col.key" class="w-3 h-3"
                    :class="rankDir === 'asc' ? '-rotate-90' : 'rotate-90'" aria-hidden="true" />
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in scorecardRows.slice(0, 200)" :key="c.customer"
              class="border-b border-outline-gray-1 last:border-0 cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
              tabindex="0"
              @click="drillOpen(String(c.customer_name) + ' Orders', { metric: 'top_customers', customer: c.customer })"
              @keydown.enter="drillOpen(String(c.customer_name) + ' Orders', { metric: 'top_customers', customer: c.customer })">
              <td class="px-4 py-2 text-ink-gray-8">{{ c.customer_name }}</td>
              <td class="px-4 py-2">
                <Badge v-if="c.clv_tier" theme="gray" variant="subtle" :label="c.clv_tier" size="sm" />
                <span v-else class="text-ink-gray-4">—</span>
              </td>
              <td class="px-4 py-2 text-ink-gray-7">{{ c.rfm_segment || '—' }}</td>
              <td class="px-4 py-2">
                <Badge v-if="c.churn_risk" v-bind="severityBadge(churnSeverity(c.churn_risk))" :label="c.churn_risk" size="sm" />
                <span v-else class="text-ink-gray-4">—</span>
              </td>
              <td class="px-4 py-2 text-right tnum font-medium text-ink-gray-9">{{ money(c.revenue) }}</td>
              <td class="px-4 py-2 text-right tnum font-medium" :class="deltaInk(c.gross_profit)">{{ money(c.gross_profit) }}</td>
              <td class="px-4 py-2 text-right tnum" :class="deltaInk(c.margin_pct)">{{ c.margin_pct }}%</td>
              <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ c.months_active }}/{{ c.total_months }}</td>
              <td class="px-4 py-2 text-right tnum text-ink-gray-9">{{ c.consistency_score }}</td>
              <td class="px-4 py-2 text-right">
                <Badge v-if="c.health_score != null" v-bind="severityBadge(healthSeverity(c.health_status))" :label="String(Math.round(c.health_score))" size="sm" />
                <span v-else class="text-ink-gray-4">—</span>
              </td>
            </tr>
            <tr v-if="!scorecardRows.length">
              <td colspan="10" class="px-4 py-12 text-center text-ink-gray-6">No customers match these filters.</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="px-4 py-3 text-xs text-center text-ink-gray-6 bg-surface-gray-1">
        Showing {{ Math.min(scorecardRows.length, 200) }} of {{ scorecardRows.length }} filtered
        <span v-if="scorecard">({{ scorecard.customers.length }} customers total)</span>
      </div>
    </div>
  </div>
</template>
