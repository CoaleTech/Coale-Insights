<!-- frontend/src2/dashboard/CustomerSections.vue -->
<!--
  Customer tab-group content for the merged Revenue & Customers dashboard.
  Receives the customer_intelligence payload from the shell and renders 7 tabs:
  Overview, Customers, Geography, Actions, Cohorts, Patterns, Rankings.
  The TerritoryMap lives here (not in Revenue Attribution).
-->
<script setup lang="ts">
defineOptions({ name: 'CustomerSections' })
import { Badge, Button, Select, Tooltip } from 'frappe-ui'
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
interface GeoPoint { name: string; value: number }
interface UnmappedTerritory { territory: string; value: number }
interface DayOfWeekDataRow { order_count: number }

// ── Recommendation tier labels ─────────────────────────────────────────────
const REC_TIER_LABELS: Record<number, string> = {
  0: 'Seasonal', 1: 'Rules', 2: 'FBT', 3: 'Popular', 4: 'Explore',
}

// ── State ──────────────────────────────────────────────────────────────────
const counts = ref<any>(null)
const rankings = ref<any>(null)
const bottomRankings = ref<any>(null)
const rankingsView = ref<'top' | 'bottom'>('top')
const purchasePatternsData = ref<any>(null)
const activeCutoff = ref('6')
const isLoadingPatterns = ref(false)
const isLoadingBottomRankings = ref(false)

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
      c.customer_name?.toLowerCase().includes(search) ||
      c.customer_id?.toLowerCase().includes(search) ||
      c.territory?.toLowerCase().includes(search) ||
      c.rfm_segment?.toLowerCase().includes(search),
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
const nextActions = computed(() => (props.data.next_best_actions ?? []) as unknown[])
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
  try {
    rankings.value = await apiCall('insights.api.ml.customer.customer_rankings', {
      date_filter: props.dateFilter,
    }) as Record<string, unknown>
  } catch (e: unknown) {
    console.error('Failed to load rankings:', readFrappeError(e).message)
  }
}

async function loadBottomRankings() {
  isLoadingBottomRankings.value = true
  try {
    bottomRankings.value = await apiCall('insights.api.ml.customer.bottom_customers', {
      date_filter: props.dateFilter,
    }) as Record<string, unknown>
  } catch (e: unknown) {
    console.error('Failed to load bottom rankings:', readFrappeError(e).message)
  } finally {
    isLoadingBottomRankings.value = false
  }
}


// ── Watchers ───────────────────────────────────────────────────────────────
watch(activeCutoff, () => loadCustomerCounts())

watch(() => props.activeTab, (tab) => {
  if (tab === 'cust-patterns') loadPurchasePatterns()
  if (tab === 'cust-rankings') loadRankings()
})

// Bottom Performers is opt-in via the toggle, not loaded by default —
// fetch lazily the first time the user switches to it.
watch(rankingsView, (view) => {
  if (view === 'bottom' && !bottomRankings.value) loadBottomRankings()
})

watch(() => props.dateFilter, () => {
  loadCustomerCounts()
  loadRankings()
  // Only refetch bottom rankings if the user has actually viewed them —
  // mirrors the lazy-load-once-then-keep-fresh behaviour above.
  if (bottomRankings.value) loadBottomRankings()
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
      <div class="relative flex-1 min-w-[200px]">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-gray-5" aria-hidden="true" />
        <input
          v-model="customerFilter" type="text"
          placeholder="Search by name, ID, or territory..."
          aria-label="Search customers"
          class="w-full pl-10 pr-4 py-2 border border-outline-gray-2 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 text-ink-gray-8"
        />
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
  <div v-if="activeTab === 'cust-actions'" class="space-y-4">
    <div class="flex items-center justify-between">
      <SectionHeader variant="caption" title="Next Best Actions" :level="3" />
      <span class="text-sm text-ink-gray-6">{{ nextActions.length }} action items</span>
    </div>
    <div class="space-y-3">
      <div v-for="action in nextActions.slice(0, 30)" :key="(action as Record<string, unknown>).customer_id as string"
        class="p-4 bg-surface-white rounded-lg border border-outline-gray-1">
        <div class="flex items-start justify-between mb-3">
          <div>
            <h4 class="font-semibold text-ink-gray-9">{{ (action as Record<string, unknown>).customer_name }}</h4>
            <div class="flex items-center gap-2 mt-1">
              <Badge theme="gray" variant="subtle" :label="((action as Record<string, unknown>).clv_tier as string) || '-'" size="sm" />
              <Badge v-bind="severityBadge(churnSeverity((action as Record<string, unknown>).churn_risk as string))"
                :label="((action as Record<string, unknown>).churn_risk as string) + ' Risk'" size="sm" />
            </div>
          </div>
          <Badge v-bind="severityBadge(healthSeverity((action as Record<string, unknown>).health_status as string))"
            :label="((action as Record<string, unknown>).health_status as string) || '-'" size="sm" />
        </div>
        <div class="-mx-4 mt-3 divide-y divide-outline-gray-1 border-t border-outline-gray-1">
          <div v-for="rec in ((action as Record<string, unknown>).recommendations as Record<string, unknown>[])" :key="rec.action as string"
            class="px-4 py-3">
            <div class="flex items-center justify-between mb-1">
              <span class="text-sm font-semibold text-ink-gray-8">{{ actionLabel(rec.action as string) }}</span>
              <Badge v-bind="severityBadge(prioritySeverity(rec.priority as string))" :label="(rec.priority as string) + ' Priority'" size="sm" />
            </div>
            <p class="text-sm text-ink-gray-7">{{ rec.description }}</p>
            <p class="mt-1 text-sm text-ink-gray-7">{{ rec.suggestion }}</p>
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
  <div v-if="activeTab === 'cust-rankings' && rankings" class="p-6 space-y-6">
    <div class="flex items-center gap-2">
      <Button
        :variant="rankingsView === 'top' ? 'solid' : 'outline'"
        label="Top Performers"
        @click="rankingsView = 'top'"
      />
      <Button
        :variant="rankingsView === 'bottom' ? 'solid' : 'outline'"
        label="Bottom Performers"
        @click="rankingsView = 'bottom'"
      />
    </div>

    <template v-if="rankingsView === 'top'">
    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
      <SectionHeader variant="caption" title="Top Customers by Revenue" :level="3" />
      <table class="w-full text-sm mt-3">
        <caption class="sr-only">Top customers by revenue.</caption>
        <thead><tr class="text-left border-b border-outline-gray-1">
          <th scope="col" class="pb-2 text-ink-gray-6">Customer</th><th scope="col" class="pb-2 text-right text-ink-gray-6">Revenue</th>
        </tr></thead>
        <tbody>
          <tr v-for="c in (rankings.top_revenue as Record<string, unknown>[])" :key="c.customer as string"
            class="border-b border-outline-gray-1 last:border-0 cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
            tabindex="0"
            @click="drillOpen(String(c.customer_name) + ' Orders', { metric: 'top_customers', customer: c.customer })"
            @keydown.enter="drillOpen(String(c.customer_name) + ' Orders', { metric: 'top_customers', customer: c.customer })">
            <td class="py-2 text-ink-gray-8">{{ c.customer_name }}</td>
            <td class="py-2 text-right tnum font-medium text-ink-gray-9">{{ money(c.revenue as number) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
      <SectionHeader variant="caption" title="Top Customers by Gross Profit" :level="3" />
      <table class="w-full text-sm mt-3">
        <caption class="sr-only">Top customers by gross profit.</caption>
        <thead><tr class="text-left border-b border-outline-gray-1">
          <th scope="col" class="pb-2 text-ink-gray-6">Customer</th><th scope="col" class="pb-2 text-right text-ink-gray-6">Gross Profit</th>
        </tr></thead>
        <tbody>
          <tr v-for="c in (rankings.top_profit as Record<string, unknown>[])" :key="c.customer as string" class="border-b border-outline-gray-1 last:border-0">
            <td class="py-2 text-ink-gray-8">{{ c.customer_name }}</td>
            <td class="py-2 text-right tnum font-medium text-ink-gray-9">{{ money(c.gross_profit as number) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
      <SectionHeader variant="caption" title="Top Customers by Margin %" :level="3" />
      <table class="w-full text-sm mt-3">
        <caption class="sr-only">Top customers by margin percentage.</caption>
        <thead><tr class="text-left border-b border-outline-gray-1">
          <th scope="col" class="pb-2 text-ink-gray-6">Customer</th><th scope="col" class="pb-2 text-right text-ink-gray-6">Margin %</th><th scope="col" class="pb-2 text-right text-ink-gray-6">Revenue</th>
        </tr></thead>
        <tbody>
          <tr v-for="c in (rankings.top_margin as Record<string, unknown>[])" :key="c.customer as string" class="border-b border-outline-gray-1 last:border-0">
            <td class="py-2 text-ink-gray-8">{{ c.customer_name }}</td>
            <td class="py-2 text-right tnum font-medium text-ink-gray-9">{{ c.margin_pct }}%</td>
            <td class="py-2 text-right tnum text-ink-gray-7">{{ money(c.revenue as number) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
      <SectionHeader variant="caption" title="Most Consistent Customers" :level="3" />
      <table class="w-full text-sm mt-3">
        <caption class="sr-only">Most consistent customers by score and months active.</caption>
        <thead><tr class="text-left border-b border-outline-gray-1">
          <th scope="col" class="pb-2 text-ink-gray-6">Customer</th><th scope="col" class="pb-2 text-right text-ink-gray-6">Score</th><th scope="col" class="pb-2 text-right text-ink-gray-6">Months Active</th>
        </tr></thead>
        <tbody>
          <tr v-for="c in (rankings.top_consistent as Record<string, unknown>[])" :key="c.customer as string" class="border-b border-outline-gray-1 last:border-0">
            <td class="py-2 text-ink-gray-8">{{ c.customer_name }}</td>
            <td class="py-2 text-right tnum font-medium text-ink-gray-9">{{ c.consistency_score }}</td>
            <td class="py-2 text-right text-ink-gray-7">{{ c.months_active }}/{{ c.total_months }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    </template>

    <template v-else-if="bottomRankings">
    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
      <SectionHeader variant="caption" title="Weakest Customers by Revenue" :level="3" />
      <table class="w-full text-sm mt-3">
        <caption class="sr-only">Weakest customers by revenue.</caption>
        <thead><tr class="text-left border-b border-outline-gray-1">
          <th scope="col" class="pb-2 text-ink-gray-6">Customer</th><th scope="col" class="pb-2 text-right text-ink-gray-6">Revenue</th>
        </tr></thead>
        <tbody>
          <tr v-for="c in (bottomRankings.top_revenue as Record<string, unknown>[])" :key="c.customer as string"
            class="border-b border-outline-gray-1 last:border-0 cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
            tabindex="0"
            @click="drillOpen(String(c.customer_name) + ' Orders', { metric: 'top_customers', customer: c.customer })"
            @keydown.enter="drillOpen(String(c.customer_name) + ' Orders', { metric: 'top_customers', customer: c.customer })">
            <td class="py-2 text-ink-gray-8">{{ c.customer_name }}</td>
            <td class="py-2 text-right tnum font-medium text-ink-gray-9">{{ money(c.revenue as number) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
      <SectionHeader variant="caption" title="Customers with Biggest Losses" :level="3" />
      <table class="w-full text-sm mt-3">
        <caption class="sr-only">Customers with the lowest or most negative gross profit.</caption>
        <thead><tr class="text-left border-b border-outline-gray-1">
          <th scope="col" class="pb-2 text-ink-gray-6">Customer</th><th scope="col" class="pb-2 text-right text-ink-gray-6">Gross Profit</th>
        </tr></thead>
        <tbody>
          <tr v-for="c in (bottomRankings.top_profit as Record<string, unknown>[])" :key="c.customer as string" class="border-b border-outline-gray-1 last:border-0">
            <td class="py-2 text-ink-gray-8">{{ c.customer_name }}</td>
            <td class="py-2 text-right tnum font-medium" :class="deltaInk(c.gross_profit as number)">{{ money(c.gross_profit as number) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
      <SectionHeader variant="caption" title="Worst Margin %" :level="3" />
      <table class="w-full text-sm mt-3">
        <caption class="sr-only">Customers with the worst margin percentage.</caption>
        <thead><tr class="text-left border-b border-outline-gray-1">
          <th scope="col" class="pb-2 text-ink-gray-6">Customer</th><th scope="col" class="pb-2 text-right text-ink-gray-6">Margin %</th><th scope="col" class="pb-2 text-right text-ink-gray-6">Revenue</th>
        </tr></thead>
        <tbody>
          <tr v-for="c in (bottomRankings.top_margin as Record<string, unknown>[])" :key="c.customer as string" class="border-b border-outline-gray-1 last:border-0">
            <td class="py-2 text-ink-gray-8">{{ c.customer_name }}</td>
            <td class="py-2 text-right tnum font-medium" :class="deltaInk(c.margin_pct as number)">{{ c.margin_pct }}%</td>
            <td class="py-2 text-right tnum text-ink-gray-7">{{ money(c.revenue as number) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
      <SectionHeader variant="caption" title="Most Erratic Customers" :level="3" />
      <table class="w-full text-sm mt-3">
        <caption class="sr-only">Least consistent customers by score and months active.</caption>
        <thead><tr class="text-left border-b border-outline-gray-1">
          <th scope="col" class="pb-2 text-ink-gray-6">Customer</th><th scope="col" class="pb-2 text-right text-ink-gray-6">Score</th><th scope="col" class="pb-2 text-right text-ink-gray-6">Months Active</th>
        </tr></thead>
        <tbody>
          <tr v-for="c in (bottomRankings.top_consistent as Record<string, unknown>[])" :key="c.customer as string" class="border-b border-outline-gray-1 last:border-0">
            <td class="py-2 text-ink-gray-8">{{ c.customer_name }}</td>
            <td class="py-2 text-right tnum font-medium text-ink-gray-9">{{ c.consistency_score }}</td>
            <td class="py-2 text-right text-ink-gray-7">{{ c.months_active }}/{{ c.total_months }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    </template>

    <div v-else class="text-center py-12">
      <Activity class="w-12 h-12 mx-auto text-ink-gray-4 animate-pulse" aria-hidden="true" />
      <p class="mt-4 text-ink-gray-6">Loading bottom performers…</p>
    </div>
  </div>
</template>
