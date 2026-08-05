<script setup lang="ts">
defineOptions({ name: 'InventoryIntelligence' })
import { Breadcrumbs, Button, Badge, Tabs, Spinner } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import {
  RefreshCcw, Package, Warehouse, ArrowRightLeft, Clock,
  TrendingUp, TrendingDown, Activity, BarChart3,
  PieChart, ShoppingCart, Truck, DollarSign, Archive, Boxes,
  ArrowRight, Layers,
} from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { createToast } from '../helpers/toasts'
import {
  scoreSeverity, severityBadge, severityFill, severityAria,
  ragSeverity, deltaInk, deltaGlyph, prioritySeverity, type Severity,
} from '../utils/status'
import { formatDate, formatDateTime, formatCount, asNumber, NO_VALUE } from '../utils/format'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'
import KpiCard from '../intelligence/components/KpiCard.vue'
import SectionHeader from '../intelligence/components/SectionHeader.vue'
import IntelligenceDashboardShell from '../intelligence/components/IntelligenceDashboardShell.vue'

const router = useRouter()

const INV_ENDPOINT = 'insights.api.ml.inventory.get_inventory_detail'
const drillDown = useDrillDown()

// State
const isLoading = ref(true)
const isRefreshing = ref(false)
const error = ref<string | null>(null)
const data = ref<Record<string, unknown> | null>(null)
const lastUpdated = ref('')
const dateFilter = ref('12m')

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

// Itemwise BE state
const itemwiseBeData = ref<Record<string, unknown> | null>(null)
const itemwiseBeLoading = ref(false)
const itemwiseBeError = ref<string | null>(null)

const hasData = computed(() => data.value !== null && !error.value)

// Load inventory intelligence data
async function loadData(refresh = false) {
  if (refresh) {
    isRefreshing.value = true
  } else {
    isLoading.value = true
  }
  error.value = null

  try {
    const result = await apiCall<Record<string, unknown>>('insights.api.ml.inventory_intelligence', {
      refresh: refresh,
      date_filter: dateFilter.value,
    })
    data.value = result
    lastUpdated.value = new Date().toISOString()
  } catch (e: unknown) {
    error.value = (e instanceof Error ? e.message : String(e)) || 'Failed to load inventory intelligence'
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

// Train/refresh inventory intelligence
async function trainInventoryIntelligence() {
  isTraining.value = true
  trainingStatus.value = ''

  try {
    const result = await apiCall<Record<string, unknown>>('insights.api.ml.train_inventory_intelligence')
    trainingStatus.value = 'Analysis complete'
    trainingSuccess.value = true
    data.value = result
    lastUpdated.value = new Date().toISOString()
    createToast({
      title: 'Analysis Complete',
      message: `Analyzed ${(result.stock_overview as Record<string, unknown>)?.total_skus || 0} SKUs across ${(result.stock_overview as Record<string, unknown>)?.warehouse_count || 0} warehouses`,
      variant: 'success',
    })
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
    })
    createToast({
      title: 'ABC/XYZ Classification Complete',
      message: `Classified ${(result as Record<string, unknown>)?.total_items || 0} items`,
      variant: 'success',
    })
    await loadData(true)
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
  matrix?: Record<string, unknown>[]
  total_items?: number
  classification_date?: string
}

// Computed values
const stockOverview = computed(() => (data.value?.stock_overview as Record<string, unknown>) || {})
const turnoverAnalysis = computed(() => (data.value?.turnover_analysis as Record<string, unknown>) || {})
const agingAnalysis = computed(() => (data.value?.aging_analysis as Record<string, unknown>) || {})
const warehouseAnalysis = computed(() => (data.value?.warehouse_analysis as Record<string, unknown>) || {})
const transferRecommendations = computed(() => (data.value?.transfer_recommendations as unknown[]) || [])
const deadStock = computed(() => (data.value?.dead_stock as Record<string, unknown>) || {})
const procurementInsights = computed(() => (data.value?.procurement_insights as Record<string, unknown>) || {})
const abcXyz = computed(() => (data.value?.abc_xyz as AbcXyzData | null) ?? null)
const demandPlanning = computed(() => (data.value?.demand_planning as Record<string, unknown> | null) ?? null)

// Max value for age bucket bars (avoids inline template Math.max)
const maxAgeBucketValue = computed(() => {
  const buckets = agingAnalysis.value.age_buckets as Record<string, { value: number }> | undefined
  if (!buckets) return 1
  return Math.max(...Object.values(buckets).map(b => b.value || 1))
})

// Format helpers
function formatCurrency(value: number): string {
  if (value === undefined || value === null) return NO_VALUE
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`
  return value?.toFixed(0) || '0'
}


function formatPercent(value: number): string {
  return `${value?.toFixed(1) || 0}%`
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

// Load on mount
onMounted(() => {
  loadData()
})

// Watch for date filter changes
watch(dateFilter, () => {
  loadData()
})

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
  stockOverview: data.value?.stock_overview || {},
  turnoverAnalysis: data.value?.turnover_analysis || {},
  abcXyzAnalysis: data.value?.abc_xyz_analysis || {},
  agingFifo: data.value?.aging_fifo || {},
  warehouseTransfers: data.value?.warehouse_transfers || {},
  procurementInsights: data.value?.procurement_insights || {},
  demandPlanning: data.value?.demand_planning || {},
  activeTab: activeTab.value,
  isLoading: isLoading.value,
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
      <div class="flex items-center gap-3">
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
          :loading="isRefreshing"
          @click="loadData(true)"
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
      :loading="isLoading"
      :refreshing="isRefreshing"
      :error="error"
      :has-data="!!data"
      :kpi-count="6"
      subject="inventory data"
      @retry="loadData()"
    >
    <!-- Main Content -->
    <div class="flex-1 overflow-auto p-6">
      <!-- Summary Cards -->
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
        <!-- Health Score -->
        <KpiCard
          label="Health Score"
          :value="asNumber(stockOverview.health_score)"
          :severity="scoreSeverity(stockOverview.health_score as number, { good: 80, warn: 60, higherIsBetter: true })"
          :loading="!hasData"
        />
        <!-- Total SKUs -->
        <KpiCard
          label="Active SKUs"
          :value="formatCount(stockOverview.total_skus as number)"
          :clickable="true"
          :loading="!hasData"
          @click="drillDown.open(INV_ENDPOINT, 'Active SKUs', { metric: 'total_skus' })"
        />
        <!-- Stock Value -->
        <KpiCard
          label="Stock Value"
          :value="formatCurrency(stockOverview.total_value as number)"
          :loading="!hasData"
        />
        <!-- Out of Stock -->
        <KpiCard
          label="Out of Stock"
          :value="formatCount(stockOverview.out_of_stock_count as number)"
          :severity="(stockOverview.out_of_stock_count as number) > 0 ? 'high' : 'none'"
          :loading="!hasData"
        />
        <!-- Low Stock -->
        <KpiCard
          label="Low Stock"
          :value="formatCount(stockOverview.low_stock_count as number)"
          :severity="(stockOverview.low_stock_count as number) > 0 ? 'medium' : 'none'"
          :clickable="true"
          :loading="!hasData"
          @click="drillDown.open(INV_ENDPOINT, 'Low Stock Items', { metric: 'low_stock_items' })"
        />
        <!-- Overstock -->
        <KpiCard
          label="Overstock"
          :value="formatCount(stockOverview.overstock_count as number)"
          :severity="(stockOverview.overstock_count as number) > 0 ? 'low' : 'none'"
          :loading="!hasData"
        />
      </div>

      <!-- Tabs -->
      <div class="mx-6">
        <Tabs v-model="tabIndex" :tabs="tabDefs" />
      </div>

      <!-- Tab Content -->
      <div class="flex-1 p-6">
          <!-- Stock Overview Tab -->
          <div v-if="activeTab === 'overview'">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Stock by Item Group -->
              <div>
                <SectionHeader variant="caption" title="Stock Value by Item Group" :level="3" />
                <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item Group</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Items</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Qty</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(group, idx) in stockOverview.by_item_group as unknown[]"
                        :key="idx"
                        class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                      >
                        <td class="px-4 py-2 font-medium text-ink-gray-9">{{ (group as Record<string, unknown>).item_group }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount((group as Record<string, unknown>).item_count as number) }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount((group as Record<string, unknown>).total_qty as number) }}</td>
                        <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ formatCurrency((group as Record<string, unknown>).stock_value as number) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Dead Stock Summary -->
              <div>
                <SectionHeader variant="caption" title="Dead Stock (No Sales 180+ Days)" :level="3" />
                <div class="mt-4 grid grid-cols-2 gap-4 mb-4">
                  <KpiCard
                    label="Total Dead Stock Value"
                    :value="formatCurrency(deadStock.total_value as number)"
                    severity="high"
                    variant="tile"
                  />
                  <KpiCard
                    label="Items"
                    :value="formatCount(deadStock.total_items as number)"
                    variant="tile"
                  />
                </div>
                <div class="bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item Group</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Count</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(group, idx) in (deadStock.by_product_group as unknown[])?.slice(0, 8)"
                        :key="idx"
                        class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                      >
                        <td class="px-4 py-2 font-medium text-ink-gray-9">{{ (group as Record<string, unknown>).item_group }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount((group as Record<string, unknown>).count as number) }}</td>
                        <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ formatCurrency((group as Record<string, unknown>).value as number) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>

          <!-- Turnover Tab -->
          <div v-if="activeTab === 'turnover'">
            <!-- Turnover Summary - KpiCards replace the banned gradient blocks -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <KpiCard
                label="Turnover Ratio"
                :value="asNumber(turnoverAnalysis.overall_turnover_ratio)"
                unit="x"
                :loading="!hasData"
              />
              <KpiCard
                label="Days Sales Inventory"
                :value="asNumber(turnoverAnalysis.days_sales_inventory)"
                unit=" days"
                :loading="!hasData"
              />
              <KpiCard
                label="COGS (12m)"
                :value="formatCurrency(turnoverAnalysis.cogs_12m as number)"
                :loading="!hasData"
              />
              <KpiCard
                label="Avg Inventory Value"
                :value="formatCurrency(turnoverAnalysis.avg_inventory_value as number)"
                :loading="!hasData"
              />
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Turnover by Product Group -->
              <div>
                <SectionHeader variant="caption" title="Turnover by Product Group" :level="3" />
                <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item Group</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Sales 12m</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Turnover</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">DSI</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(group, idx) in turnoverAnalysis.by_product_group as unknown[]"
                        :key="idx"
                        class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                      >
                        <td class="px-4 py-2 font-medium text-ink-gray-9">{{ (group as Record<string, unknown>).item_group }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCurrency((group as Record<string, unknown>).sales_12m as number) }}</td>
                        <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ (group as Record<string, unknown>).turnover_ratio }}x</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ (group as Record<string, unknown>).dsi }} days</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Fast & Slow Movers -->
              <div class="space-y-6">
                <!-- Fast Moving -->
                <div>
                  <SectionHeader variant="caption" title="Fast Moving Items (90d)" :level="3" />
                  <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                    <table class="w-full text-sm">
                      <thead class="bg-surface-gray-1">
                        <tr>
                          <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Sold</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Stock</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="(item, idx) in (turnoverAnalysis.fast_moving as unknown[])?.slice(0, 5)"
                          :key="idx"
                          class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                        >
                          <td class="px-4 py-2 font-medium text-ink-gray-9 truncate max-w-[200px]"
                              :title="(item as Record<string, unknown>).item_name as string">
                            {{ (item as Record<string, unknown>).item_code }}
                          </td>
                          <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ formatCount((item as Record<string, unknown>).qty_sold as number) }}</td>
                          <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount((item as Record<string, unknown>).current_stock as number) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- Slow Moving -->
                <div>
                  <SectionHeader variant="caption" title="Slow Moving Items (90d)" :level="3" />
                  <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                    <table class="w-full text-sm">
                      <thead class="bg-surface-gray-1">
                        <tr>
                          <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Item</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Stock</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="(item, idx) in (turnoverAnalysis.slow_moving as unknown[])?.slice(0, 5)"
                          :key="idx"
                          class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                        >
                          <td class="px-4 py-2 font-medium text-ink-gray-9 truncate max-w-[200px]"
                              :title="(item as Record<string, unknown>).item_name as string">
                            {{ (item as Record<string, unknown>).item_code }}
                          </td>
                          <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount((item as Record<string, unknown>).current_stock as number) }}</td>
                          <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ formatCurrency((item as Record<string, unknown>).stock_value as number) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ABC/XYZ Tab -->
          <div v-if="activeTab === 'abc-xyz'">
            <div v-if="abcXyz">
              <!-- Summary Cards -->
              <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
                <KpiCard label="Class A Items" :value="formatCount(abcXyz.summary?.a_count as number)"
                         sublabel="High Value (~80%)" />
                <KpiCard label="Class B Items" :value="formatCount(abcXyz.summary?.b_count as number)"
                         sublabel="Medium Value (~15%)" />
                <KpiCard label="Class C Items" :value="formatCount(abcXyz.summary?.c_count as number)"
                         sublabel="Low Value (~5%)" />
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
                  <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                    <table class="w-full text-sm">
                      <thead class="bg-surface-gray-1">
                        <tr>
                          <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Class</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Items</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Sales Value</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Stock Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="(item, idx) in abcXyz.matrix as unknown[]"
                          :key="idx"
                          class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                        >
                          <td class="px-4 py-2">
                            <Badge v-bind="severityBadge(
                              ((item as Record<string, unknown>).class as string | undefined)?.startsWith('A') ? 'none' :
                              ((item as Record<string, unknown>).class as string | undefined)?.startsWith('B') ? 'medium' : 'high'
                            )" :label="String((item as Record<string, unknown>).class)" size="sm" />
                          </td>
                          <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ formatCount((item as Record<string, unknown>).item_count as number) }}</td>
                          <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCurrency((item as Record<string, unknown>).sales_value as number) }}</td>
                          <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCurrency((item as Record<string, unknown>).stock_value as number) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- ABC Summary -->
                  <SectionHeader variant="caption" title="ABC Summary (by Value)" :level="4" class="mt-6 mb-3" />
                  <div class="bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                    <table class="w-full text-sm">
                      <thead class="bg-surface-gray-1">
                        <tr>
                          <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Class</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Items</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Total Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(item, idx) in abcXyz.abc_summary as unknown[]" :key="idx"
                            class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
                          <td class="px-4 py-2">
                            <Badge v-bind="severityBadge(
                              (item as Record<string, unknown>).class === 'A' ? 'none' :
                              (item as Record<string, unknown>).class === 'B' ? 'medium' : 'high'
                            )" :label="String((item as Record<string, unknown>).class)" size="sm" />
                          </td>
                          <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ formatCount((item as Record<string, unknown>).item_count as number) }}</td>
                          <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCurrency((item as Record<string, unknown>).total_value as number) }}</td>
                        </tr>
                      </tbody>
                    </table>
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
                          <th scope="col" class="px-3 py-2 text-right text-ink-gray-6">Sales</th>
                          <th scope="col" class="px-3 py-2 text-right text-ink-gray-6">Stock</th>
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
                          <td class="px-3 py-2 text-right text-xs text-ink-gray-6">{{ formatCurrency((item as Record<string, unknown>).total_value as number) }}</td>
                          <td class="px-3 py-2 text-right text-xs text-ink-gray-6">{{ formatCount((item as Record<string, unknown>).stock_qty as number) }}</td>
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
          </div>

          <!-- Itemwise BE Tab -->
          <div v-if="activeTab === 'itemwise-be'">
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
                    <td class="px-4 py-3 text-sm text-right text-ink-gray-6">{{ formatCurrency((item as Record<string, unknown>).selling_price as number) }}</td>
                    <td class="px-4 py-3 text-sm text-right text-ink-gray-6">{{ formatCurrency((item as Record<string, unknown>).variable_cost as number) }}</td>
                    <td class="px-4 py-3 text-sm text-right font-medium text-ink-gray-9">{{ formatCurrency((item as Record<string, unknown>).contribution_margin as number) }}</td>
                    <td class="px-4 py-3 text-sm text-right text-ink-gray-6">{{ ((item as Record<string, unknown>).be_qty as number)?.toLocaleString() }}</td>
                    <td class="px-4 py-3 text-sm text-right text-ink-gray-6">{{ ((item as Record<string, unknown>).actual_qty as number)?.toLocaleString() }}</td>
                    <td class="px-4 py-3 text-sm text-right font-medium"
                        :class="deltaInk((item as Record<string, unknown>).coverage as number >= 1 ? 1 : -1, { higherIsBetter: true })">
                      {{ (((item as Record<string, unknown>).coverage as number) * 100)?.toFixed(1) }}%
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
          </div>

          <!-- Aging (FIFO) Tab -->
          <div v-if="activeTab === 'aging'">
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
                         :aria-label="severityAria(String(name), ageBucketSeverity(String(name)), formatCurrency(bucket.value))">
                      <div
                        :class="['h-full rounded-full', severityFill(ageBucketSeverity(String(name)))]"
                        :style="{ width: `${Math.min(100, (bucket.value / maxAgeBucketValue) * 100)}%` }"
                      ></div>
                    </div>
                    <div class="w-20 text-right text-sm font-bold text-ink-gray-9">{{ formatCurrency(bucket.value) }}</div>
                    <div class="w-16 text-right text-xs text-ink-gray-6">{{ bucket.count }} items</div>
                  </div>
                </div>

                <div class="mt-6 p-4 bg-surface-gray-1 rounded-lg border border-outline-gray-1">
                  <p class="text-sm text-ink-gray-6">
                    <strong class="text-ink-gray-8">Total Items Analyzed:</strong> {{ formatCount(agingAnalysis.total_items_analyzed as number) }}
                  </p>
                  <p class="text-xs text-ink-gray-6 mt-1">
                    Age calculation based on FIFO (First-In-First-Out) valuation method
                  </p>
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
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCurrency((group as Record<string, unknown>).total_value as number) }}</td>
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
                      <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCurrency((item as Record<string, unknown>).total_value as number) }}</td>
                      <td class="px-4 py-2 text-right font-bold" :class="deltaInk(-1, { higherIsBetter: true })">
                        {{ (item as Record<string, unknown>).avg_age_days }} days
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- Warehouses & Transfers Tab -->
          <div v-if="activeTab === 'warehouses'">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Warehouse Stock -->
              <div>
                <SectionHeader variant="caption" title="Stock by Warehouse" :level="3" />
                <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Warehouse</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Items</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Value</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">% Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(wh, idx) in warehouseAnalysis.by_warehouse as unknown[]"
                        :key="idx"
                        class="border-b border-outline-gray-1 hover:bg-surface-gray-1 cursor-pointer"
                        tabindex="0"
                        @click="drillDown.open(INV_ENDPOINT, (wh as Record<string, unknown>).warehouse + ' Stock', { metric: 'warehouse_stock', warehouse: (wh as Record<string, unknown>).warehouse })"
                        @keydown.enter="drillDown.open(INV_ENDPOINT, (wh as Record<string, unknown>).warehouse + ' Stock', { metric: 'warehouse_stock', warehouse: (wh as Record<string, unknown>).warehouse })"
                      >
                        <td class="px-4 py-2 font-medium text-ink-gray-9 truncate max-w-[200px]">{{ (wh as Record<string, unknown>).warehouse }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount((wh as Record<string, unknown>).item_count as number) }}</td>
                        <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ formatCurrency((wh as Record<string, unknown>).stock_value as number) }}</td>
                        <td class="px-4 py-2 text-right">
                          <div class="flex items-center justify-end gap-2">
                            <div class="w-16 bg-surface-gray-2 rounded-full h-2">
                              <div class="bg-surface-blue-3 h-2 rounded-full"
                                   :style="{ width: `${(wh as Record<string, unknown>).pct_of_total}%` }"
                                   role="img"
                                   :aria-label="`${(wh as Record<string, unknown>).pct_of_total}% of total`"></div>
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
                    :value="formatCurrency(warehouseAnalysis.total_stock_value as number)"
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
                          :title="(item as Record<string, unknown>).distribution as string">
                        {{ (item as Record<string, unknown>).distribution }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- Procurement Tab -->
          <div v-if="activeTab === 'procurement'">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Supplier Performance -->
              <div>
                <SectionHeader variant="caption" title="Supplier Performance (12m)" :level="3" />
                <div class="mt-4 bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Supplier</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Orders</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Value</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Lead Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(supplier, idx) in procurementInsights.supplier_performance as unknown[]"
                        :key="idx"
                        class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                      >
                        <td class="px-4 py-2 font-medium text-ink-gray-9 truncate max-w-[150px]"
                            :title="(supplier as Record<string, unknown>).supplier_name as string">
                          {{ (supplier as Record<string, unknown>).supplier_name || (supplier as Record<string, unknown>).supplier }}
                        </td>
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ formatCount((supplier as Record<string, unknown>).order_count as number) }}</td>
                        <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ formatCurrency((supplier as Record<string, unknown>).total_value as number) }}</td>
                        <td class="px-4 py-2 text-right">
                          <!-- Lead time: good <= 7, warn <= 14, higherIsBetter: false -->
                          <span :class="['font-medium', deltaInk(Math.round((supplier as Record<string, unknown>).avg_lead_time as number || 0) - 14, { higherIsBetter: false })]">
                            {{ Math.round((supplier as Record<string, unknown>).avg_lead_time as number || 0) }} days
                          </span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Reorder Needed -->
              <div>
                <SectionHeader variant="caption" title="Items Needing Reorder" :level="3">
                  <template #actions>
                    <Badge v-bind="severityBadge(scoreSeverity(procurementInsights.reorder_count as number, { good: 0, warn: 5, higherIsBetter: false }))"
                           :label="String(procurementInsights.reorder_count)" size="sm" />
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
                        v-for="(item, idx) in (procurementInsights.reorder_needed as unknown[])?.slice(0, 10)"
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
                        <td class="px-4 py-2 text-right text-ink-gray-6">{{ ((item as Record<string, unknown>).avg_daily_demand as number || 0).toFixed(1) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <!-- Pending Orders -->
            <div class="mt-6">
              <SectionHeader variant="caption" title="Pending Purchase Orders" :level="3">
                <template #actions>
                  <Badge v-bind="severityBadge(scoreSeverity(procurementInsights.pending_orders_count as number, { good: 0, warn: 10, higherIsBetter: false }))"
                         :label="String(procurementInsights.pending_orders_count)" size="sm" />
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
                      v-for="(order, idx) in procurementInsights.pending_orders as unknown[]"
                      :key="idx"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                    >
                      <td class="px-4 py-2 font-medium text-ink-gray-9">{{ (order as Record<string, unknown>).name }}</td>
                      <td class="px-4 py-2 text-ink-gray-6 truncate max-w-[150px]">{{ (order as Record<string, unknown>).supplier }}</td>
                      <td class="px-4 py-2 text-ink-gray-6">{{ (order as Record<string, unknown>).transaction_date }}</td>
                      <td class="px-4 py-2 text-right font-bold text-ink-gray-9">{{ formatCurrency((order as Record<string, unknown>).grand_total as number) }}</td>
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
            </div>

            <!-- Demand Planning Integration -->
            <div v-if="demandPlanning" class="mt-6">
              <SectionHeader variant="caption" title="Demand Planning Summary" :level="3" />
              <div class="mt-4 grid grid-cols-4 gap-4 mb-4">
                <KpiCard label="Total Items"
                         :value="asNumber((demandPlanning.summary as Record<string, unknown>)?.total_items)" />
                <KpiCard label="Reorder Now"
                         :value="asNumber((demandPlanning.summary as Record<string, unknown>)?.reorder_now_count)"
                         :severity="Number((demandPlanning.summary as Record<string, unknown>)?.reorder_now_count) > 0 ? 'high' : 'none'" />
                <KpiCard label="Monitor"
                         :value="asNumber((demandPlanning.summary as Record<string, unknown>)?.monitor_count)"
                         :severity="Number((demandPlanning.summary as Record<string, unknown>)?.monitor_count) > 0 ? 'medium' : 'none'" />
                <KpiCard label="Adequate"
                         :value="asNumber((demandPlanning.summary as Record<string, unknown>)?.adequate_count)" />
              </div>
            </div>
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
