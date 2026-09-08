<script setup lang="ts">
import { asNumber } from '../utils/format'
import { Badge, Button, ListView, Select, Spinner } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import {
  User, ShoppingCart, TrendingUp,
  Gift, AlertTriangle, ArrowLeft, Mail, Phone, MapPin,
  Calendar, DollarSign, Heart, Target, ChevronRight,
  Package, Clock, CreditCard, BarChart3, Zap,
  ArrowUpRight, ArrowDownRight,
} from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createToast } from '../helpers/toasts'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'
import KpiCard from '../intelligence/components/KpiCard.vue'
import SectionHeader from '../intelligence/components/SectionHeader.vue'
import {
  severityBadge, severityFill, severityAria, scoreSeverity, deltaInk, deltaGlyph, type Severity,
  HEALTH_SCORE_THRESHOLDS,
} from '../utils/status'
import {
  formatCurrency as formatCurrencyFull, formatCurrencyCompact, formatNumber,
  formatDate, formatPercent,
  addRecentCustomer,
} from '../utils/customerUtils'

const route = useRoute()
const router = useRouter()

const customerId = computed(() => route.params.customerId as string)
const drillDown = useDrillDown()
const CUSTOMER_ENDPOINT = 'insights.api.ml.customer.get_customer_detail'

// State
const isLoading = ref(true)
const isRefreshing = ref(false)
const error = ref<string | null>(null)
const customer = ref<Record<string, unknown> | null>(null)

/**
 * Money in the currency the server reported for this customer's company.
 *
 * `formatCurrency` used to default to KES with the en-KE locale, rendering KES
 * as "Ksh" on an INR company. The 360 payload now carries `base_currency`.
 */
const payloadCurrency = ref<string | null>(null)
const baseCurrency = computed<string | null>(() => payloadCurrency.value)
function money(value: number | undefined | null): string {
  return formatCurrencyFull(value, baseCurrency.value)
}
function moneyCompact(value: number | undefined | null): string {
  return formatCurrencyCompact(value, baseCurrency.value)
}
const purchaseHistory = ref<Record<string, unknown>[]>([])
const crossSellRecommendations = ref<Record<string, unknown>[]>([])
const purchasePatterns = ref<Record<string, unknown> | null>(null)

const hasData = computed(() => customer.value !== null && !isLoading.value)

// Cross-sell ListView columns
const crossSellColumns = [
  { label: 'Item Code', key: 'item_code', width: 1.5 },
  { label: 'Item Name', key: 'item_name', width: 2.5 },
  {
    label: 'Confidence',
    key: 'confidence',
    width: 1,
    align: 'right',
    getLabel: (props: { row: Record<string, unknown> }) =>
      `${(((props.row.confidence as number) || 0) * 100).toFixed(0)}%`,
  },
  {
    label: 'Reason',
    key: 'reason',
    width: 2,
    getLabel: (props: { row: Record<string, unknown> }) =>
      (props.row.reason as string) || 'Purchase history',
  },
]

// Sidebar navigation
const activeSection = ref('profile')
const sections = [
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'purchases', label: 'Purchases', icon: ShoppingCart },
  { id: 'clv', label: 'CLV Analysis', icon: TrendingUp },
  { id: 'recommendations', label: 'Recommendations', icon: Gift },
  { id: 'risk', label: 'Risk Assessment', icon: AlertTriangle },
]

// Filter type for navigation context
const filterType = ref<'clv' | 'territory' | 'rfm'>('clv')
const filterOptions = [
  { value: 'clv', label: 'By CLV Tier' },
  { value: 'territory', label: 'By Territory' },
  { value: 'rfm', label: 'By RFM Segment' },
]

async function loadCustomerData(refresh = false) {
  if (refresh) {
    isRefreshing.value = true
  } else {
    isLoading.value = true
  }
  error.value = null

  try {
    const result = await apiCall('insights.api.ml.customer_360_detail', {
      customer_id: customerId.value,
      include_purchases: true,
      include_recommendations: true,
    }) as Record<string, unknown>

    customer.value = result.customer as Record<string, unknown>
    // `base_currency` sits at the payload root, not inside `customer`, so it has
    // to be captured here. Missing it rendered every figure with no currency at all.
    payloadCurrency.value = (result.base_currency as string | undefined) ?? null
    purchaseHistory.value = (result.purchase_history as Record<string, unknown>[]) || []
    crossSellRecommendations.value = (result.cross_sell as Record<string, unknown>[]) || []
    purchasePatterns.value = (result.purchase_patterns as Record<string, unknown>) || null
  } catch (e: unknown) {
    error.value = (e instanceof Error ? e.message : null) || 'Failed to load customer details'
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

function goBack() {
  router.push('/revenue-customers-intelligence')
}

function navigateToRelated(relatedCustomerId: string) {
  addRecentCustomer(relatedCustomerId)
  router.push(`/customer/${relatedCustomerId}`)
}

// Computed values
const clvTier = computed(() => (customer.value?.clv_tier as string) || 'Unknown')
const healthScore = computed(() => (customer.value?.health_score as number) || 0)
const healthStatus = computed(() => (customer.value?.health_status as string) || 'Unknown')
const churnRisk = computed(() => (customer.value?.churn_risk as string) || 'Unknown')
const churnScore = computed(() => (customer.value?.churn_score as number) || 0)
const rfmSegment = computed(() => (customer.value?.rfm_segment as string) || 'Unknown')

const totalOrders = computed(() => (customer.value?.order_count as number) || 0)
const totalRevenue = computed(() => (customer.value?.historical_clv as number) || 0)
const avgOrderValue = computed(() => (customer.value?.avg_order_value as number) || 0)
const daysSincePurchase = computed(() => (customer.value?.days_since_last_purchase as number) || 0)
const predictedClv = computed(() => (customer.value?.predicted_12m_clv as number) || 0)

const nextBestActions = computed(() => (customer.value?.recommendations as Record<string, unknown>[]) || [])

// Health and churn severity computed from scores
const healthSeverity = computed(() =>
  scoreSeverity(healthScore.value, HEALTH_SCORE_THRESHOLDS),
)
const churnSeverity = computed(() => severityBadge(churnRisk.value))

// Credit limit: recommended exposure ceiling vs the current ERPNext limit
const recommendedCreditLimit = computed(() => (customer.value?.recommended_credit_limit as number) || 0)
const currentCreditLimit = computed(() => (customer.value?.current_credit_limit as number) || 0)
const creditHeadroom = computed(() => (customer.value?.credit_headroom as number) || 0)
const creditRationale = computed(() => {
  const c = customer.value
  if (!c || !recommendedCreditLimit.value) return ''
  const rr = moneyCompact(c.credit_monthly_run_rate as number)
  const days = c.credit_target_days as number
  const ps = c.payment_score == null ? 'unknown' : `${Math.round(c.payment_score as number)}/100`
  const od = (c.overdue_count as number) || 0
  return `Based on ~${rr}/mo expected sales funded over ${days}-day terms, discounted for payment behaviour (score ${ps}${od ? `, ${od} overdue` : ''}). A suggestion for the credit team, not auto-applied.`
})

const chatContext = computed(() => ({
  customer_id: customerId.value,
  customer_name: customer.value?.customer_name,
  clv_tier: clvTier.value,
  health_status: healthStatus.value,
  churn_risk: churnRisk.value,
  total_revenue: totalRevenue.value,
  total_orders: totalOrders.value,
  rfm_segment: rfmSegment.value,
}))

onMounted(() => {
  loadCustomerData()
})

watch(customerId, () => {
  loadCustomerData()
})
</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <header class="sticky top-0 z-10 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between px-6 py-4 bg-surface-white border-b border-outline-gray-1">
      <div class="flex items-center gap-4">
        <Button
          variant="ghost"
          theme="gray"
          aria-label="Back to customer intelligence"
          @click="goBack"
        >
          <ArrowLeft class="w-4 h-4" />
        </Button>
        <div>
          <div class="flex items-center gap-3">
            <h1 class="text-xl font-semibold text-ink-gray-9">
              {{ customer?.customer_name || customerId }}
            </h1>
            <Badge
              v-if="clvTier !== 'Unknown'"
              theme="gray"
              variant="subtle"
              :label="clvTier"
              size="sm"
            />
          </div>
          <p class="text-sm text-ink-gray-6">Customer ID: {{ customerId }}</p>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <Select
          v-model="filterType"
          :options="filterOptions"
          aria-label="Filter customers by"
        />
        <Button
          variant="subtle"
          theme="gray"
          :loading="isRefreshing"
          @click="loadCustomerData(true)"
        >
          Refresh
        </Button>
      </div>
    </header>

    <!-- Main Content -->
    <div class="flex flex-1 overflow-hidden">
      <!-- Sidebar Navigation -->
      <aside class="w-64 bg-surface-white border-r border-outline-gray-1 overflow-y-auto">
        <nav class="p-4 space-y-1" aria-label="Customer sections">
          <button
            v-for="section in sections"
            :key="section.id"
            type="button"
            class="flex w-full items-center gap-3 rounded px-3 py-1.5 text-left text-sm transition-colors hover:bg-surface-gray-2"
            :class="activeSection === section.id ? 'bg-surface-gray-2 text-ink-gray-9 font-medium' : 'text-ink-gray-6'"
            :aria-pressed="activeSection === section.id"
            @click="activeSection = section.id"
          >
            <component :is="section.icon" class="w-5 h-5 shrink-0" aria-hidden="true" />
            <span>{{ section.label }}</span>
          </button>
        </nav>

        <!-- Quick Stats in Sidebar -->
        <div class="p-4 border-t border-outline-gray-1">
          <h4 class="text-xs font-semibold text-ink-gray-6 uppercase mb-3">Quick Stats</h4>
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <span class="text-sm text-ink-gray-6">Health</span>
              <Badge
                v-bind="severityBadge(healthSeverity)"
                :label="`${healthScore.toFixed(0)}%`"
                size="sm"
              />
            </div>
            <div class="flex items-center justify-between">
              <span class="text-sm text-ink-gray-6">Churn Risk</span>
              <Badge v-bind="severityBadge(churnRisk)" size="sm" />
            </div>
            <div class="flex items-center justify-between">
              <span class="text-sm text-ink-gray-6">RFM Segment</span>
              <Badge
                theme="gray"
                variant="subtle"
                :label="rfmSegment"
                size="sm"
                class="max-w-[110px] truncate"
                :title="rfmSegment"
              />
            </div>
          </div>
        </div>
      </aside>

      <!-- Content Area -->
      <main class="flex-1 overflow-y-auto p-6">
        <!-- Loading State -->
        <div v-if="isLoading" class="flex items-center justify-center h-64">
          <div class="text-center">
            <Spinner class="mx-auto" />
            <p class="mt-4 text-ink-gray-6">Loading customer data...</p>
          </div>
        </div>

        <!-- Error State -->
        <div v-else-if="error" class="flex items-center justify-center h-64">
          <div class="text-center">
            <AlertTriangle class="w-12 h-12 mx-auto text-ink-gray-6" />
            <p class="mt-4 text-ink-gray-9 font-medium">Failed to load customer</p>
            <p class="text-sm text-ink-gray-6 mt-1">{{ error }}</p>
            <Button variant="solid" theme="gray" class="mt-4" @click="loadCustomerData(true)">
              Try Again
            </Button>
          </div>
        </div>

        <!-- Content Sections -->
        <div v-else>
          <!-- Profile Section -->
          <div v-if="activeSection === 'profile'" class="space-y-6">
            <!-- Key Metrics Cards -->
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <KpiCard
                label="Total Revenue"
                :value="money(totalRevenue)"
                sublabel="Lifetime Value"
                :loading="!hasData"
                :clickable="true"
                @click="drillDown.open(CUSTOMER_ENDPOINT, 'Invoices', { metric: 'customer_invoices', customer: customerId, bucket: 'all' })"
              />
              <KpiCard
                label="Total Orders"
                :value="formatNumber(totalOrders)"
                :sublabel="`AOV: ${money(avgOrderValue)}`"
                :loading="!hasData"
                :clickable="true"
                @click="drillDown.open(CUSTOMER_ENDPOINT, 'Invoices', { metric: 'customer_invoices', customer: customerId, bucket: 'all' })"
              />
              <KpiCard
                label="Predicted CLV (12m)"
                :value="money(predictedClv)"
                sublabel="Next 12 months"
                :loading="!hasData"
              />
              <KpiCard
                label="Last Purchase"
                :value="String(daysSincePurchase)"
                sublabel="days ago"
                :severity="scoreSeverity(daysSincePurchase, { good: 30, warn: 90, higherIsBetter: false })"
                :loading="!hasData"
              />
            </div>

            <!-- Customer Details -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
                <SectionHeader variant="caption" title="Customer Information" :level="3">
                  <template #actions>
                    <User class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                  </template>
                </SectionHeader>
                <div class="space-y-4 mt-4">
                  <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                    <span class="text-sm text-ink-gray-6">Customer Group</span>
                    <span class="text-sm font-medium text-ink-gray-8">{{ customer?.customer_group || 'N/A' }}</span>
                  </div>
                  <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                    <span class="text-sm text-ink-gray-6">Territory</span>
                    <span class="text-sm font-medium text-ink-gray-8">{{ customer?.territory || 'N/A' }}</span>
                  </div>
                  <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                    <span class="text-sm text-ink-gray-6">Account Manager</span>
                    <span class="text-sm font-medium text-ink-gray-8">{{ customer?.account_manager || 'N/A' }}</span>
                  </div>
                  <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                    <span class="text-sm text-ink-gray-6">Customer Since</span>
                    <span class="text-sm font-medium text-ink-gray-8">{{ formatDate(customer?.customer_since as string) }}</span>
                  </div>
                  <div class="flex justify-between items-center py-2">
                    <span class="text-sm text-ink-gray-6">Tenure</span>
                    <span class="text-sm font-medium text-ink-gray-8">{{ customer?.tenure_days || 0 }} days</span>
                  </div>
                </div>
              </div>

              <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
                <SectionHeader variant="caption" title="Segmentation" :level="3">
                  <template #actions>
                    <BarChart3 class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                  </template>
                </SectionHeader>
                <div class="space-y-4 mt-4">
                  <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                    <span class="text-sm text-ink-gray-6">CLV Tier</span>
                    <Badge theme="gray" variant="subtle" :label="clvTier" />
                  </div>
                  <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                    <span class="text-sm text-ink-gray-6">RFM Segment</span>
                    <Badge theme="gray" variant="subtle" :label="rfmSegment" />
                  </div>
                  <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                    <span class="text-sm text-ink-gray-6">Health Status</span>
                    <Badge v-bind="severityBadge(healthSeverity)" :label="healthStatus" />
                  </div>
                  <div class="flex justify-between items-center py-2">
                    <span class="text-sm text-ink-gray-6">Churn Risk</span>
                    <Badge v-bind="severityBadge(churnRisk)" :label="`${churnRisk} (${churnScore.toFixed(0)}%)`" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Purchases Section -->
          <div v-if="activeSection === 'purchases'" class="space-y-6">
            <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
              <SectionHeader variant="caption" title="Purchase History" :level="3">
                <template #actions>
                  <ShoppingCart class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                </template>
              </SectionHeader>

              <div v-if="purchaseHistory.length > 0" class="mt-4 overflow-x-auto">
                <table class="w-full text-sm">
                  <thead>
                    <tr class="border-b border-outline-gray-1">
                      <th scope="col" class="px-4 py-3 text-left text-ink-gray-7 font-medium">Invoice</th>
                      <th scope="col" class="px-4 py-3 text-left text-ink-gray-7 font-medium">Date</th>
                      <th scope="col" class="px-4 py-3 text-right text-ink-gray-7 font-medium">Amount</th>
                      <th scope="col" class="px-4 py-3 text-right text-ink-gray-7 font-medium">Outstanding</th>
                      <th scope="col" class="px-4 py-3 text-center text-ink-gray-7 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="purchase in purchaseHistory.slice(0, 20)"
                      :key="purchase.invoice_id as string"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                      tabindex="0"
                      @keydown.enter.prevent="navigateToRelated(purchase.invoice_id as string)"
                    >
                      <td class="px-4 py-3 font-medium text-ink-gray-8">{{ purchase.invoice_id }}</td>
                      <td class="px-4 py-3 text-ink-gray-6">{{ formatDate(purchase.posting_date as string) }}</td>
                      <td class="px-4 py-3 text-right font-medium text-ink-gray-8">{{ money(purchase.grand_total as number) }}</td>
                      <td class="px-4 py-3 text-right">
                        <span :class="(purchase.outstanding_amount as number) > 0 ? 'text-ink-red-4 font-medium' : 'text-ink-gray-8'">
                          {{ money(purchase.outstanding_amount as number) }}
                          <span v-if="(purchase.outstanding_amount as number) > 0" class="text-xs ml-1">(due)</span>
                        </span>
                      </td>
                      <td class="px-4 py-3 text-center">
                        <Badge
                          v-bind="severityBadge(
                            purchase.payment_status === 'Paid' ? 'low' :
                            purchase.payment_status === 'Overdue' ? 'high' : 'medium'
                          )"
                          :label="purchase.payment_status as string"
                          size="sm"
                        />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div v-else class="mt-4 text-center py-12 text-ink-gray-6">
                <ShoppingCart class="w-12 h-12 mx-auto text-ink-gray-6 opacity-40" aria-hidden="true" />
                <p class="mt-4">No purchase history available</p>
              </div>
            </div>

            <!-- Purchase Patterns -->
            <div v-if="purchasePatterns" class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
              <SectionHeader variant="caption" title="Purchase Patterns" :level="3">
                <template #actions>
                  <BarChart3 class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                </template>
              </SectionHeader>
              <div class="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                <KpiCard
                  label="Avg Order Frequency"
                  :value="purchasePatterns.avg_frequency as string | number | undefined"
                  sublabel="days between orders"
                  variant="tile"
                />
                <KpiCard
                  label="Preferred Day"
                  :value="purchasePatterns.preferred_day as string | number | undefined"
                  sublabel="most common purchase day"
                  variant="tile"
                />
                <KpiCard
                  label="Peak Month"
                  :value="purchasePatterns.peak_month as string | number | undefined"
                  sublabel="highest spending month"
                  variant="tile"
                />
              </div>
            </div>
          </div>

          <!-- CLV Analysis Section -->
          <div v-if="activeSection === 'clv'" class="space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
                <SectionHeader variant="caption" title="CLV Breakdown" :level="3">
                  <template #actions>
                    <TrendingUp class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                  </template>
                </SectionHeader>
                <div class="space-y-4 mt-4">
                  <div class="flex justify-between items-center py-3 border-b border-outline-gray-1">
                    <span class="text-sm text-ink-gray-6">Historical CLV</span>
                    <span class="text-lg font-bold text-ink-gray-9">{{ money(totalRevenue) }}</span>
                  </div>
                  <div class="flex justify-between items-center py-3 border-b border-outline-gray-1">
                    <span class="text-sm text-ink-gray-6">Predicted 12m CLV</span>
                    <span class="text-lg font-bold text-ink-gray-9">{{ money(predictedClv) }}</span>
                  </div>
                  <div class="flex justify-between items-center py-3 border-b border-outline-gray-1">
                    <span class="text-sm text-ink-gray-6">CLV Score</span>
                    <span class="text-lg font-bold text-ink-gray-8">{{ (customer?.clv_score as number)?.toFixed(0) || 0 }}</span>
                  </div>
                  <div class="flex justify-between items-center py-3">
                    <span class="text-sm text-ink-gray-6">CLV Tier</span>
                    <Badge theme="gray" variant="subtle" :label="clvTier" />
                  </div>
                </div>
              </div>

              <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
                <SectionHeader variant="caption" title="CLV Components" :level="3">
                  <template #actions>
                    <Target class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                  </template>
                </SectionHeader>
                <div class="space-y-4 mt-4">
                  <div>
                    <div class="flex justify-between text-sm mb-1">
                      <span class="text-ink-gray-6">Revenue Score</span>
                      <span class="font-medium text-ink-gray-8">{{ (customer?.revenue_score as number)?.toFixed(0) || 0 }}%</span>
                    </div>
                    <div class="w-full bg-surface-gray-2 rounded-full h-2">
                      <div
                        class="bg-surface-gray-5 rounded-full h-2"
                        :style="{ width: `${customer?.revenue_score || 0}%` }"
                        :aria-label="`Revenue score: ${(customer?.revenue_score as number)?.toFixed(0) || 0}%`"
                        role="img"
                      />
                    </div>
                  </div>
                  <div>
                    <div class="flex justify-between text-sm mb-1">
                      <span class="text-ink-gray-6">Engagement Score</span>
                      <span class="font-medium text-ink-gray-8">{{ (customer?.engagement_score as number)?.toFixed(0) || 0 }}%</span>
                    </div>
                    <div class="w-full bg-surface-gray-2 rounded-full h-2">
                      <div
                        class="bg-surface-gray-5 rounded-full h-2"
                        :style="{ width: `${customer?.engagement_score || 0}%` }"
                        :aria-label="`Engagement score: ${(customer?.engagement_score as number)?.toFixed(0) || 0}%`"
                        role="img"
                      />
                    </div>
                  </div>
                  <div>
                    <div class="flex justify-between text-sm mb-1">
                      <span class="text-ink-gray-6">Longevity Score</span>
                      <span class="font-medium text-ink-gray-8">{{ (customer?.longevity_score as number)?.toFixed(0) || 0 }}%</span>
                    </div>
                    <div class="w-full bg-surface-gray-2 rounded-full h-2">
                      <div
                        class="bg-surface-gray-5 rounded-full h-2"
                        :style="{ width: `${customer?.longevity_score || 0}%` }"
                        :aria-label="`Longevity score: ${(customer?.longevity_score as number)?.toFixed(0) || 0}%`"
                        role="img"
                      />
                    </div>
                  </div>
                  <div>
                    <div class="flex justify-between text-sm mb-1">
                      <span class="text-ink-gray-6">Growth Score</span>
                      <span class="font-medium text-ink-gray-8">{{ (customer?.growth_score as number)?.toFixed(0) || 0 }}%</span>
                    </div>
                    <div class="w-full bg-surface-gray-2 rounded-full h-2">
                      <div
                        class="bg-surface-gray-5 rounded-full h-2"
                        :style="{ width: `${customer?.growth_score || 0}%` }"
                        :aria-label="`Growth score: ${(customer?.growth_score as number)?.toFixed(0) || 0}%`"
                        role="img"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Recommendations Section -->
          <div v-if="activeSection === 'recommendations'" class="space-y-6">
            <!-- Next Best Actions -->
            <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
              <SectionHeader variant="caption" title="Next Best Actions" :level="3">
                <template #actions>
                  <Zap class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                </template>
              </SectionHeader>
              <div v-if="nextBestActions.length > 0" class="mt-4 space-y-3">
                <div
                  v-for="action in nextBestActions"
                  :key="action.action as string"
                  class="p-4 rounded-lg border border-outline-gray-1 bg-surface-white"
                >
                  <div class="flex items-center justify-between mb-2">
                    <span class="text-sm font-bold uppercase text-ink-gray-8">
                      {{ (action.action as string)?.replace(/_/g, ' ') }}
                    </span>
                    <Badge
                      v-bind="severityBadge((action.priority as string)?.toLowerCase())"
                      :label="`${action.priority} Priority`"
                      size="sm"
                    />
                  </div>
                  <p class="text-sm text-ink-gray-7">{{ action.description }}</p>
                  <p v-if="action.suggestion" class="mt-2 text-xs text-ink-gray-6">{{ action.suggestion }}</p>
                </div>
              </div>
              <div v-else class="mt-4 text-center py-12 text-ink-gray-6">
                <Zap class="w-12 h-12 mx-auto opacity-40" aria-hidden="true" />
                <p class="mt-4">No actions recommended at this time</p>
              </div>
            </div>

            <!-- Cross-sell Recommendations -->
            <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
              <SectionHeader variant="caption" title="Cross-sell Recommendations" :level="3">
                <template #actions>
                  <Gift class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                </template>
              </SectionHeader>
              <div class="mt-4">
                <ListView
                  v-if="crossSellRecommendations.length > 0"
                  :columns="crossSellColumns"
                  :rows="crossSellRecommendations"
                  row-key="item_code"
                  :options="{ showTooltip: false, emptyState: { title: 'No cross-sell recommendations', description: 'No recommendations available at this time.' } }"
                />
                <div v-else class="text-center py-12 text-ink-gray-6">
                  <Gift class="w-12 h-12 mx-auto opacity-40" aria-hidden="true" />
                  <p class="mt-4">No cross-sell recommendations available</p>
                </div>
              </div>
            </div>
          </div>

          <!-- Risk Assessment Section -->
          <div v-if="activeSection === 'risk'" class="space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <!-- Churn Risk -->
              <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
                <SectionHeader variant="caption" title="Churn Risk Assessment" :level="3">
                  <template #actions>
                    <AlertTriangle class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                  </template>
                </SectionHeader>
                <div class="text-center py-6">
                  <div
                    :class="['inline-flex items-center justify-center w-24 h-24 rounded-full text-3xl font-bold text-ink-gray-9', severityFill(churnRisk)]"
                    :aria-label="severityAria('Churn Risk', churnRisk, `${churnScore.toFixed(0)}%`)"
                    role="img"
                  >
                    {{ churnScore.toFixed(0) }}%
                  </div>
                  <div class="mt-4 flex items-center justify-center gap-2">
                    <p class="text-lg font-semibold text-ink-gray-8">{{ churnRisk }} Risk</p>
                    <Badge v-bind="severityBadge(churnRisk)" size="sm" />
                  </div>
                </div>
                <div class="mt-4 space-y-3">
                  <div class="flex justify-between items-center text-sm">
                    <span class="text-ink-gray-6">Frequency Trend</span>
                    <span :class="['font-medium', deltaInk(customer?.frequency_trend as number)]">
                      {{ deltaGlyph(customer?.frequency_trend as number) }}
                      {{ Math.abs((customer?.frequency_trend as number) || 0).toFixed(1) }}
                    </span>
                  </div>
                  <div class="flex justify-between items-center text-sm">
                    <span class="text-ink-gray-6">Value Trend</span>
                    <span :class="['font-medium', deltaInk(customer?.value_trend as number)]">
                      {{ deltaGlyph(customer?.value_trend as number) }}
                      {{ Math.abs((customer?.value_trend as number) || 0).toFixed(1) }}
                    </span>
                  </div>
                </div>
              </div>

              <!-- Health Score -->
              <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
                <SectionHeader variant="caption" title="Health Score" :level="3">
                  <template #actions>
                    <Heart class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                  </template>
                </SectionHeader>
                <div class="text-center py-6">
                  <div
                    :class="['inline-flex items-center justify-center w-24 h-24 rounded-full text-3xl font-bold text-ink-gray-9', severityFill(healthSeverity)]"
                    :aria-label="severityAria('Health Score', healthSeverity, healthScore.toFixed(0))"
                    role="img"
                  >
                    {{ healthScore.toFixed(0) }}
                  </div>
                  <div class="mt-4 flex items-center justify-center gap-2">
                    <p class="text-lg font-semibold text-ink-gray-8">{{ healthStatus }}</p>
                    <Badge v-bind="severityBadge(healthSeverity)" size="sm" />
                  </div>
                </div>
                <div class="mt-4">
                  <div class="flex justify-between text-sm text-ink-gray-6 mb-2">
                    <span>Health Components</span>
                    <span>Score</span>
                  </div>
                  <div class="space-y-2">
                    <div v-for="(comp, label) in {
                      Revenue: customer?.revenue_score,
                      Engagement: customer?.engagement_score,
                      Payment: customer?.payment_score,
                      Longevity: customer?.longevity_score,
                      Growth: customer?.growth_score,
                    }" :key="label" class="flex justify-between items-center">
                      <span class="text-sm text-ink-gray-7">{{ label }}</span>
                      <div class="flex items-center gap-2">
                        <div class="w-20 bg-surface-gray-2 rounded-full h-1.5">
                          <div
                            class="bg-surface-gray-5 rounded-full h-1.5"
                            :style="{ width: `${comp || 0}%` }"
                            :aria-label="`${label}: ${((comp as number) || 0).toFixed(0)}`"
                            role="img"
                          />
                        </div>
                        <span class="text-xs font-medium w-8 text-right text-ink-gray-7">
                          {{ ((comp as number) || 0).toFixed(0) }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Payment Behavior -->
            <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
              <SectionHeader variant="caption" title="Payment Behavior" :level="3">
                <template #actions>
                  <CreditCard class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                </template>
              </SectionHeader>
              <div class="mt-4 grid grid-cols-1 md:grid-cols-4 gap-4">
                <KpiCard
                  label="Avg Days to Pay"
                  :value="(customer?.avg_days_to_pay as number)?.toFixed(0) ?? 'N/A'"
                  :severity="scoreSeverity(customer?.avg_days_to_pay as number, { good: 30, warn: 60, higherIsBetter: false })"
                />
                <KpiCard
                  label="Outstanding Amount"
                  :value="money(customer?.outstanding_amount as number)"
                  :severity="(customer?.outstanding_amount as number) > 0 ? 'high' : undefined"
                  :clickable="true"
                  @click="drillDown.open(CUSTOMER_ENDPOINT, 'Outstanding Invoices', { metric: 'customer_invoices', customer: customerId, bucket: 'outstanding' })"
                />
                <KpiCard
                  label="Payment Score"
                  :percent="customer?.payment_score == null ? null : Math.round(customer?.payment_score as number)"
                  :severity="scoreSeverity(customer?.payment_score as number, { good: 75, warn: 50 })"
                />
                <KpiCard
                  label="Overdue Invoices"
                  :value="asNumber(customer?.overdue_count)"
                  :severity="(customer?.overdue_count as number) > 0 ? 'high' : undefined"
                  :clickable="true"
                  @click="drillDown.open(CUSTOMER_ENDPOINT, 'Overdue Invoices', { metric: 'customer_invoices', customer: customerId, bucket: 'overdue' })"
                />
              </div>

              <!-- Recommended Credit Limit -->
              <div v-if="recommendedCreditLimit > 0" class="mt-6 pt-6 border-t border-outline-gray-1">
                <SectionHeader variant="caption" title="Recommended Credit Limit"
                  hint="Suggested exposure ceiling from demand and repayment risk" :level="4" />
                <div class="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                  <KpiCard label="Recommended" :value="money(recommendedCreditLimit)" sublabel="suggested ceiling" />
                  <KpiCard label="Current Limit (ERPNext)" :value="currentCreditLimit > 0 ? money(currentCreditLimit) : 'Not set'"
                    :sublabel="currentCreditLimit > 0 ? undefined : 'no limit configured'" />
                  <KpiCard label="Headroom vs Outstanding" :value="money(creditHeadroom)"
                    :severity="creditHeadroom < 0 ? 'high' : undefined"
                    :sublabel="creditHeadroom < 0 ? 'over recommended exposure' : 'available'" />
                </div>
                <p class="mt-3 text-sm text-ink-gray-6">{{ creditRationale }}</p>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- AI Chat Button -->
    <!--
      "Customer", not "Customer 360": the server has no agent registered under
      the latter, so `get_agent_for_dashboard` threw "No agent available" and the
      chat was dead here. Verified against the live endpoint. "Customer" is the
      exact match for a per-customer profile and returns real quick actions.
    -->
    <DashboardChatButton
      dashboard-type="Customer"
      :dashboard-context="chatContext"
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
