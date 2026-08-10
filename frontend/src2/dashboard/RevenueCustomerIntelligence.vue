<!-- frontend/src2/dashboard/RevenueCustomerIntelligence.vue -->
<!--
  Merged Sales + Customer Intelligence. Two management questions, one dashboard:
  "How is the business performing?" (Revenue) and "Who are our customers and
  which are at risk?" (Customers). The two previously separate dashboards shared
  territory data and forced users to navigate away to get the other half of the
  story. This shell holds the shared header, KPI strip, and tab-group selector.
  Revenue/Customer section components are lazy-loaded to avoid loading 3,000+
  lines eagerly.
-->
<script setup lang="ts">
defineOptions({ name: 'RevenueCustomerIntelligence' })
import { Button, Tabs, TabButtons } from 'frappe-ui'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { groupButtons, useGroupedTabs } from '../composables/useGroupedTabs'
import { useRouter } from 'vue-router'
import { apiCall, readFrappeError } from '../helpers/api'
import { AlertTriangle, RefreshCcw, Loader2 } from 'lucide-vue-next'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import SkeletonBlock from '../intelligence/components/SkeletonBlock.vue'
import KpiCard from '../intelligence/components/KpiCard.vue'
import RevenueSections from './RevenueSections.vue'
import CustomerSections from './CustomerSections.vue'
import { scoreSeverity } from '../utils/status'
import { formatMoney, formatCount, formatPercent } from '../utils/format'

// ── Router ───────────────────────────────────────────────────────────────
const router = useRouter()
const drillDown = useDrillDown()

// ── Shared state ───────────────────────────────────────────────────────────
const isLoading = ref(true)
const isRefreshing = ref(false)
const error = ref<string | null>(null)
// Per-group errors: one endpoint failing must not blank the other's tabs.
const salesError = ref<string | null>(null)
const custError = ref<string | null>(null)
const dateFilter = ref('12m')

// Sales payload
const salesData = ref<Record<string, unknown> | null>(null)
// Customer payload
const custData = ref<Record<string, unknown> | null>(null)

// ── Tab-group architecture ────────────────────────────────────────────────
// Two groups ("Revenue" and "Customers") share the same tab strip. The strip
// is a flat list of all tab labels; an internal `group` field determines which
// section component renders. Tab-level loading (Cross-sell, Patterns, Sources)
// is handled inside the section components via watch.
type TabGroup = 'revenue' | 'customers'
interface TabDef { id: string; label: string; group: TabGroup }

const TAB_DEFS: TabDef[] = [
  // Revenue group
  { id: 'rev-overview',    label: 'Revenue Overview',     group: 'revenue' },
  { id: 'rev-payment',      label: 'Cash vs Credit', group: 'revenue' },
  { id: 'rev-reps',        label: 'Sales Reps',   group: 'revenue' },
  { id: 'rev-margins',     label: 'Margins',       group: 'revenue' },
  { id: 'rev-forecasts',   label: 'Forecasts',    group: 'revenue' },
  { id: 'rev-sources',     label: 'Attribution',  group: 'revenue' },
  // Customers group
  { id: 'cust-overview',   label: 'Customer Overview',     group: 'customers' },
  { id: 'cust-list',       label: 'Customers',     group: 'customers' },
  { id: 'cust-geography',  label: 'Geography',     group: 'customers' },
  { id: 'cust-actions',    label: 'Actions',       group: 'customers' },
  { id: 'cust-cohorts',    label: 'Cohorts',       group: 'customers' },
  { id: 'cust-patterns',   label: 'Patterns',     group: 'customers' },
  { id: 'cust-rankings',   label: 'Rankings',      group: 'customers' },
] as const

/**
 * The group is the primary axis, not a caption.
 *
 * Every tab already declared a `group` and the content was already routed by it
 * into two different section components; only the strip stayed flat, so thirteen
 * peer tabs sat in one row while the label above them merely reported which
 * group the selection happened to fall in. Revenue and Customers are also two
 * separate fetches, so the boundary already existed in the data layer too.
 */
const TAB_GROUPS: readonly TabGroup[] = ['revenue', 'customers']
const GROUP_BUTTONS = groupButtons(TAB_GROUPS)

const { activeGroup, tabItems, activeTabIndex, activeTab } = useGroupedTabs(TAB_DEFS, TAB_GROUPS)

// ── Computed: summary from both payloads ──────────────────────────────────
const salesSummary = computed(() => (salesData.value?.summary ?? {}) as Record<string, number>)
const custSummary = computed(() => (custData.value?.summary ?? {}) as Record<string, unknown>)
const baseCurrency = computed<string | null>(() => (custData.value?.base_currency as string) ?? null)

/** Unified KPI strip: 6 cards mixing revenue and customer metrics so the
 * cross-domain question ("is revenue down because customers left?") is answered
 * at a glance without navigating between tabs. */
const atRiskCount = computed(() => {
  const arc = (custData.value?.at_risk_customers as unknown[]) ?? []
  return arc.length
})

/**
 * A cold cache answers `{status: "warming"}` while a background job fits the
 * models. Either half warming would render the KPI strip all-zeros, so the
 * page shows a "computing" state until both are ready. A group that errored is
 * not warming -- that is the error branch's job.
 */
const warming = computed(
  () =>
    !error.value &&
    (salesData.value?.status === 'warming' || custData.value?.status === 'warming'),
)

function money(value: number | undefined | null): string {
  return formatMoney(value, baseCurrency.value)
}

// ── Data loading ───────────────────────────────────────────────────────────
/** Parallel load of both APIs. The Sales and Customer endpoints are
 * independent, so they fire concurrently via Promise.all. */
async function loadData(refresh = false) {
  if (refresh) {
    isRefreshing.value = true
  } else {
    isLoading.value = true
  }
  error.value = null
  salesError.value = null
  custError.value = null

  /*
   * allSettled, not all: the two endpoints are independent and customer
   * intelligence is by far the heavier of the pair. With Promise.all a customer
   * failure discarded the revenue half that had already loaded, blanking the
   * whole page. Each group now fails on its own.
   */
  const [salesResult, custResult] = await Promise.allSettled([
    apiCall<Record<string, unknown>>('insights.api.ml.sales_intelligence', {
      refresh,
      date_filter: dateFilter.value,
    }),
    apiCall<Record<string, unknown>>('insights.api.ml.customer_intelligence', {
      refresh,
      date_filter: dateFilter.value,
    }),
  ])

  if (salesResult.status === 'fulfilled') {
    salesData.value = salesResult.value
  } else {
    salesError.value = readFrappeError(salesResult.reason, 'Could not load revenue data').message
  }

  if (custResult.status === 'fulfilled') {
    custData.value = custResult.value
  } else {
    custError.value = readFrappeError(custResult.reason, 'Could not load customer data').message
  }

  // Only a total failure is a page-level error; one bad half still renders.
  if (salesError.value && custError.value) {
    error.value = salesError.value
  }

  isLoading.value = false
  isRefreshing.value = false
}

// ── Date filter ────────────────────────────────────────────────────────────
watch(dateFilter, () => loadData())

// ── Chat context ───────────────────────────────────────────────────────────
const chatContext = computed(() => ({
  sales: salesData.value ?? {},
  customer: custData.value ?? {},
  activeTab: activeTab.value.id,
  activeGroup: activeGroup.value,
  dateFilter: dateFilter.value,
}))

function handleDashboardRedirect(_target: string) {
  // Redirect target removed from this dashboard; navigation to other
  // intelligence dashboards stays the same.
}

// ── Lifecycle ─────────────────────────────────────────────────────────────
onMounted(() => loadData())

onBeforeUnmount(() => {
  // Queued computations are polled inside apiCall, so there is no timer here.
})

</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <div class="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between px-6 py-4 bg-surface-white border-b border-outline-gray-1">
      <div>
        <h1 class="text-xl font-semibold text-ink-gray-9">Revenue & Customers</h1>
        <p class="text-sm text-ink-gray-6 mt-0.5">Sales performance and customer intelligence</p>
      </div>
      <div class="flex items-center gap-3">
        <IntelligenceDateFilter v-model="dateFilter" />
        <Button
          variant="solid"
          theme="gray"
          :loading="isRefreshing"
          @click="loadData(true)"
        >
          <RefreshCcw class="w-4 h-4 mr-2" />
          {{ isRefreshing ? 'Refreshing...' : 'Refresh' }}
        </Button>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="isLoading" class="flex items-center justify-center flex-1">
      <div class="flex flex-col items-center gap-4">
        <div class="grid grid-cols-4 gap-4">
          <SkeletonBlock class="h-24 w-40 rounded-lg" />
          <SkeletonBlock class="h-24 w-40 rounded-lg" />
          <SkeletonBlock class="h-24 w-40 rounded-lg" />
          <SkeletonBlock class="h-24 w-40 rounded-lg" />
        </div>
        <p class="text-sm text-ink-gray-6">Loading dashboard...</p>
      </div>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="flex items-center justify-center flex-1">
      <div class="text-center space-y-3">
        <AlertTriangle class="w-12 h-12 mx-auto text-neg" aria-hidden="true" />
        <p class="text-ink-gray-6">{{ error }}</p>
        <Button variant="subtle" @click="loadData()">Try Again</Button>
      </div>
    </div>

    <!-- Warming state: a cold cache is being computed by a background job.
         Distinct from loading (first paint) and error. Shown when either
         payload returns {status:"warming"} so the strip is not rendered
         all-zeros while the numbers are still being built. -->
    <div v-else-if="warming" class="flex items-center justify-center flex-1">
      <div class="text-center space-y-3 max-w-sm">
        <Loader2 class="w-12 h-12 mx-auto text-ink-gray-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        <p class="font-medium text-ink-gray-8">Preparing your dashboard</p>
        <p class="text-sm text-ink-gray-6">
          Revenue and customer intelligence is being computed in the background.
          It can take a few minutes the first time.
        </p>
        <Button variant="subtle" @click="loadData()">Check again</Button>
      </div>
    </div>

    <!-- Main content -->
    <div v-else class="flex-1 overflow-auto">
      <!-- Unified KPI strip: 6 cards mixing revenue + customer metrics -->
      <div class="grid grid-cols-2 gap-4 p-6 lg:grid-cols-3 xl:grid-cols-6">
        <KpiCard
          label="Total Revenue"
          :value="money(salesSummary.total_revenue)"
          :delta="salesSummary.mom_growth"
          :loading="!salesData"
        />
        <KpiCard
          label="Customers"
          :value="formatCount(custSummary.total_customers as number)"
          :loading="!custData"
        />
        <KpiCard
          label="Avg Order Value"
          :value="money(salesSummary.avg_order_value)"
          :loading="!salesData"
        />
        <KpiCard
          label="Gross Margin"
          :value="formatPercent(salesSummary.overall_margin)"
          :loading="!salesData"
        />
        <KpiCard
          label="At Risk"
          :value="String(atRiskCount)"
          :severity="atRiskCount > 0 ? 'high' : 'none'"
          :loading="!custData"
        />
        <KpiCard
          label="YoY Growth"
          :value="`${(salesSummary.yoy_growth ?? 0) >= 0 ? '+' : ''}${formatPercent(salesSummary.yoy_growth)}`"
          :loading="!salesData"
          :severity="scoreSeverity(salesSummary.yoy_growth, { good: 0, warn: -10 })"
        />
      </div>

      <!-- Tab strip -->
      <div class="flex flex-col gap-2 px-6">
        <!-- Filled segmented control for the group, underlined tabs for the views
             inside it: two levels, two visual weights. -->
        <TabButtons v-model="activeGroup" :buttons="GROUP_BUTTONS" class="self-start" />
        <Tabs v-model="activeTabIndex" :tabs="tabItems" />
      </div>

      <!-- Tab content: Revenue group -->
      <div v-if="activeGroup === 'revenue'" class="p-6">
        <RevenueSections
          v-if="salesData"
          :data="salesData"
          :active-tab="activeTab.id"
          :date-filter="dateFilter"
          :currency="baseCurrency"
          :drill-down-endpoint="'insights.api.ml.sales.get_sales_detail'"
          @drill-down="drillDown.open"
        />
        <div v-else-if="salesError" class="flex flex-col items-center justify-center h-64 gap-3 text-center">
          <AlertTriangle class="w-8 h-8 text-neg" aria-hidden="true" />
          <p class="text-sm text-ink-gray-6">{{ salesError }}</p>
          <Button variant="subtle" @click="loadData()">Try Again</Button>
        </div>
        <div v-else class="flex items-center justify-center h-64">
          <SkeletonBlock class="h-24 w-96 rounded-lg" />
        </div>
      </div>

      <!-- Tab content: Customer group -->
      <div v-if="activeGroup === 'customers'" class="p-6">
        <CustomerSections
          v-if="custData"
          :data="custData"
          :active-tab="activeTab.id"
          :date-filter="dateFilter"
          :currency="baseCurrency"
          :drill-down-endpoint="'insights.api.ml.customer.get_customer_detail'"
          @drill-down="drillDown.open"
          @view-customer="(id: string) => router.push(`/customer/${id}`)"
        />
        <div v-else-if="custError" class="flex flex-col items-center justify-center h-64 gap-3 text-center">
          <AlertTriangle class="w-8 h-8 text-neg" aria-hidden="true" />
          <p class="text-sm text-ink-gray-6">{{ custError }}</p>
          <Button variant="subtle" @click="loadData()">Try Again</Button>
        </div>
        <div v-else class="flex items-center justify-center h-64">
          <SkeletonBlock class="h-24 w-96 rounded-lg" />
        </div>
      </div>
    </div>

    <!-- AI Chat Button -->
    <!--
      "Sales", not "Revenue & Customers": the server has no agent under the
      merged name, so this chat threw "No agent available" and was dead. Verified
      against the live endpoint. "Sales" matches the landing tab and the
      `/sales-intelligence` route this page replaced, and returns real quick
      actions; "General" resolves but returns none. A dedicated merged agent
      would serve both halves better.
    -->
    <DashboardChatButton
      dashboard-type="Sales"
      :dashboard-context="chatContext"
      @navigate-dashboard="handleDashboardRedirect"
    />

    <!-- Drill-down modal -->
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
