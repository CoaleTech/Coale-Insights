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
import { computed, ref } from 'vue'
import { groupButtons, useGroupedTabs } from '../composables/useGroupedTabs'
import { useRouter } from 'vue-router'
import { AlertTriangle, RefreshCcw, Loader2 } from 'lucide-vue-next'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import SkeletonBlock from '../intelligence/components/SkeletonBlock.vue'
import IntelligenceDashboardShell from '../intelligence/components/IntelligenceDashboardShell.vue'
import { useIntelligenceDashboard } from '../intelligence/composables/useIntelligenceDashboard'
import KpiCard from '../intelligence/components/KpiCard.vue'
import RevenueSections from './RevenueSections.vue'
import CustomerSections from './CustomerSections.vue'
import { scoreSeverity } from '../utils/status'
import { formatMoney, formatCount, formatPercent } from '../utils/format'

// ── Router ───────────────────────────────────────────────────────────────
const router = useRouter()
const drillDown = useDrillDown()

// ── Data ──────────────────────────────────────────────────────────────────
//
// Two independent feeds, one per group, both on the shared data-loading
// contract. This file hand-rolled that pair: two payload refs, two error refs,
// two warming refs, two poll timers, a `clearPollTimers`, two loader functions
// and an `allSettled` driver -- ~90 lines reproducing per-instance what
// `useIntelligenceDashboard` already provides, and still missing the 503
// backpressure retry it has.
const dateFilter = ref('12m')
const dateParams = computed(() => ({ date_filter: dateFilter.value }))

const sales = useIntelligenceDashboard<Record<string, unknown>>({
  url: 'insights.api.ml.sales_intelligence',
  params: dateParams,
  cache: 'sales-intelligence',
})
const customers = useIntelligenceDashboard<Record<string, unknown>>({
  url: 'insights.api.ml.customer_intelligence',
  params: dateParams,
  cache: 'customer-intelligence',
})

// Per-group refs under their original names: one endpoint failing or warming
// must not blank the other's tabs, which is what the inline branches in each
// tab block below read.
const salesData = sales.data
const custData = customers.data
const salesError = sales.error
const custError = customers.error
const salesWarming = sales.warming
const custWarming = customers.warming

/** First paint only -- either half still on its first fetch. */
const isLoading = computed(() => sales.loading.value || customers.loading.value)
const isRefreshing = computed(() => sales.refreshing.value || customers.refreshing.value)

/**
 * Page-level failure only when BOTH halves failed. One bad half still renders
 * its sibling's tabs -- the reason this dashboard loaded the two endpoints
 * with `allSettled` rather than `all`.
 */
const error = computed(() => (salesError.value && custError.value ? salesError.value : null))
/** Same rule for "no access", which this page had no state for at all. */
const isPermissionError = computed(
  () => sales.isPermissionError.value && customers.isPermissionError.value,
)
const hasData = computed(() => sales.hasData.value || customers.hasData.value)

const loadSales = () => sales.reload()
const loadCustomer = () => customers.reload()
const loadData = () => {
  loadSales()
  loadCustomer()
}
const retryAll = () => {
  sales.retry()
  customers.retry()
}

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
  { id: 'cust-cohorts',    label: 'Cohorts',       group: 'customers' },
  { id: 'cust-patterns',   label: 'Patterns',     group: 'customers' },
  { id: 'cust-rankings',   label: 'Rankings',      group: 'customers' },
  { id: 'cust-actions',    label: 'Actions',       group: 'customers' },
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
 * Full-page "Preparing" only when BOTH halves are warming. Per-group warming
 * is handled inline in each tab block, so one warm half still renders its
 * data while the other computes.
 */
const warming = computed(
  () => !error.value && !isLoading.value && salesWarming.value && custWarming.value,
)

function money(value: number | undefined | null): string {
  return formatMoney(value, baseCurrency.value)
}


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


</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <div class="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between px-6 py-4 bg-surface-white border-b border-outline-gray-1">
      <div>
        <h1 class="text-xl font-semibold text-ink-gray-9">Revenue & Customers</h1>
        <p class="text-sm text-ink-gray-6 mt-0.5">Sales performance and customer intelligence</p>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <IntelligenceDateFilter v-model="dateFilter" />
        <Button
          variant="solid"
          theme="gray"
          :loading="isRefreshing"
          @click="loadData()"
        >
          <template #prefix><RefreshCcw class="w-4 h-4" /></template>
          {{ isRefreshing ? 'Refreshing...' : 'Refresh' }}
        </Button>
      </div>
    </div>

    <!--
      One state machine, in the shell: first-load skeleton, error, warming,
      not-implemented and empty. The three blocks that stood here were this
      page's own copies of it, and they had drifted -- there was no permission
      branch at all, so a 403 rendered as a generic "Try Again" that could
      never work.
    -->
    <IntelligenceDashboardShell
      :loading="isLoading"
      :refreshing="isRefreshing"
      :error="error ?? undefined"
      :is-permission-error="isPermissionError"
      :warming="warming"
      :has-data="hasData"
      subject="revenue and customer data"
      permission-hint="Ask an administrator for Sales Invoice and Customer read access."
      :kpi-count="6"
      @retry="retryAll"
    >
      <!-- Unified KPI strip: 6 cards mixing revenue + customer metrics -->
      <div class="grid grid-cols-2 gap-4 p-6 lg:grid-cols-3 xl:grid-cols-6">
        <KpiCard
          label="Total Revenue"
          :value="money(salesSummary.total_revenue)"
          :delta="salesSummary.mom_growth"
          :loading="!salesData || salesWarming"
        />
        <KpiCard
          label="Customers"
          :value="formatCount(custSummary.total_customers as number)"
          :loading="!custData || custWarming"
        />
        <KpiCard
          label="Avg Order Value"
          :value="money(salesSummary.avg_order_value)"
          :loading="!salesData || salesWarming"
        />
        <KpiCard
          label="Gross Margin"
          :value="formatPercent(salesSummary.overall_margin)"
          :loading="!salesData || salesWarming"
        />
        <KpiCard
          label="At Risk"
          :value="String(atRiskCount)"
          :severity="atRiskCount > 0 ? 'high' : 'none'"
          :loading="!custData || custWarming"
        />
        <KpiCard
          label="YoY Growth"
          :value="`${(salesSummary.yoy_growth ?? 0) >= 0 ? '+' : ''}${formatPercent(salesSummary.yoy_growth)}`"
          :loading="!salesData || salesWarming"
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
          v-if="salesData && !salesWarming"
          :data="salesData"
          :active-tab="activeTab.id"
          :date-filter="dateFilter"
          :currency="baseCurrency"
          :drill-down-endpoint="'insights.api.ml.sales.get_sales_detail'"
          @drill-down="drillDown.open"
        />
        <!-- Warming: the cache is cold and a background job is computing.
             Distinct from error — the data is coming, not broken. -->
        <div v-else-if="salesWarming" class="flex flex-col items-center justify-center h-64 gap-3 text-center">
          <Loader2 class="w-8 h-8 text-ink-gray-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          <p class="font-medium text-ink-gray-8">Computing revenue intelligence</p>
          <p class="text-sm text-ink-gray-6">This takes a few minutes the first time. Check back shortly.</p>
          <Button variant="subtle" @click="loadSales()">Refresh</Button>
        </div>
        <div v-else-if="salesError" class="flex flex-col items-center justify-center h-64 gap-3 text-center">
          <AlertTriangle class="w-8 h-8 text-neg" aria-hidden="true" />
          <p class="text-sm text-ink-gray-6">{{ salesError }}</p>
          <Button variant="subtle" @click="retryAll()">Try Again</Button>
        </div>
        <div v-else class="flex items-center justify-center h-64">
          <SkeletonBlock class="h-24 w-96 rounded-lg" />
        </div>
      </div>

      <!-- Tab content: Customer group -->
      <div v-if="activeGroup === 'customers'" class="p-6">
        <CustomerSections
          v-if="custData && !custWarming"
          :data="custData"
          :active-tab="activeTab.id"
          :date-filter="dateFilter"
          :currency="baseCurrency"
          :drill-down-endpoint="'insights.api.ml.customer.get_customer_detail'"
          @drill-down="drillDown.open"
          @view-customer="(id: string) => router.push(`/customer/${id}`)"
        />
        <!-- Warming: the cache is cold and a background job is computing.
             Distinct from error — the data is coming, not broken. -->
        <div v-else-if="custWarming" class="flex flex-col items-center justify-center h-64 gap-3 text-center">
          <Loader2 class="w-8 h-8 text-ink-gray-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          <p class="font-medium text-ink-gray-8">Computing customer intelligence</p>
          <p class="text-sm text-ink-gray-6">This takes a few minutes the first time. Check back shortly.</p>
          <Button variant="subtle" @click="loadCustomer()">Refresh</Button>
        </div>
        <div v-else-if="custError" class="flex flex-col items-center justify-center h-64 gap-3 text-center">
          <AlertTriangle class="w-8 h-8 text-neg" aria-hidden="true" />
          <p class="text-sm text-ink-gray-6">{{ custError }}</p>
          <Button variant="subtle" @click="retryAll()">Try Again</Button>
        </div>
        <div v-else class="flex items-center justify-center h-64">
          <SkeletonBlock class="h-24 w-96 rounded-lg" />
        </div>
      </div>
    </IntelligenceDashboardShell>

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
