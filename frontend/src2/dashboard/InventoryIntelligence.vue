<script setup lang="ts">
defineOptions({ name: 'InventoryIntelligence' })
import { Breadcrumbs } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { 
  RefreshCcw, Loader2, Package, Warehouse, ArrowRightLeft, Clock,
  AlertTriangle, TrendingUp, TrendingDown, Activity, BarChart3,
  PieChart, ShoppingCart, Truck, DollarSign, Archive, Boxes,
  ArrowUpRight, ArrowDownRight, Heart, Layers, ArrowRight, Zap
} from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { createToast } from '../helpers/toasts'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'

const router = useRouter()

const INV_ENDPOINT = 'insights.api.ml.inventory.get_inventory_detail'
const drillDown = useDrillDown()

// State
const isLoading = ref(true)
const isRefreshing = ref(false)
const error = ref<string | null>(null)
const data = ref<any>(null)
const dateFilter = ref('12m')

// Training state
const isTraining = ref(false)
const trainingStatus = ref('')

// Active tab
const activeTab = ref('overview')

// Itemwise BE state
const itemwiseBeData = ref<any>(null)
const itemwiseBeLoading = ref(false)
const itemwiseBeError = ref<string | null>(null)
const tabs = [
  { id: 'overview', label: 'Stock Overview', icon: Package },
  { id: 'turnover', label: 'Turnover', icon: Activity },
  { id: 'abc-xyz', label: 'ABC/XYZ', icon: Layers },
  { id: 'itemwise-be', label: 'Itemwise BE', icon: Zap },
  { id: 'aging', label: 'Aging (FIFO)', icon: Clock },
  { id: 'warehouses', label: 'Warehouses & Transfers', icon: Warehouse },
  { id: 'procurement', label: 'Procurement', icon: Truck },
]

// Load inventory intelligence data
async function loadData(refresh = false) {
  if (refresh) {
    isRefreshing.value = true
  } else {
    isLoading.value = true
  }
  error.value = null
  
  try {
    const result = await apiCall('insights.api.ml.inventory_intelligence', {
      refresh: refresh,
      date_filter: dateFilter.value
    })

    data.value = result
    createToast({
      title: 'Data Loaded',
      message: `Analyzed ${result?.stock_overview?.total_skus || 0} SKUs`,
      variant: 'success'
    })
  } catch (e: any) {
    error.value = e.message || 'Failed to load inventory intelligence'
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
    const result = await apiCall('insights.api.ml.train_inventory_intelligence')

    trainingStatus.value = '✓ Successfully refreshed inventory analysis'
    data.value = result
    createToast({
      title: 'Analysis Complete',
      message: `Analyzed ${result?.stock_overview?.total_skus || 0} SKUs across ${result?.stock_overview?.warehouse_count || 0} warehouses`,
      variant: 'success'
    })
  } catch (e: any) {
    trainingStatus.value = `✗ Analysis error: ${e.message}`
    createToast({
      title: 'Analysis Error',
      message: e.message,
      variant: 'error'
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
      refresh: true
    })

    createToast({
      title: 'ABC/XYZ Classification Complete',
      message: `Classified ${result?.total_items || 0} items`,
      variant: 'success'
    })
    // Reload main data to get updated ABC/XYZ
    await loadData(true)
  } catch (e: any) {
    createToast({
      title: 'Classification Error',
      message: e.message,
      variant: 'error'
    })
  } finally {
    isTrainingAbcXyz.value = false
  }
}

// Computed values
const stockOverview = computed(() => data.value?.stock_overview || {})
const turnoverAnalysis = computed(() => data.value?.turnover_analysis || {})
const agingAnalysis = computed(() => data.value?.aging_analysis || {})
const warehouseAnalysis = computed(() => data.value?.warehouse_analysis || {})
const transferRecommendations = computed(() => data.value?.transfer_recommendations || [])
const deadStock = computed(() => data.value?.dead_stock || {})
const procurementInsights = computed(() => data.value?.procurement_insights || {})
const abcXyz = computed(() => data.value?.abc_xyz || null)
const demandPlanning = computed(() => data.value?.demand_planning || null)

// Format helpers
function formatCurrency(value: number): string {
  if (value === undefined || value === null) return '0'
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`
  return value?.toFixed(0) || '0'
}

function formatNumber(value: number): string {
  return value?.toLocaleString() || '0'
}

function formatPercent(value: number): string {
  return `${value?.toFixed(1) || 0}%`
}

function formatDate(dateString: string): string {
  if (!dateString) return 'N/A'
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

function getHealthScoreColor(score: number): string {
  if (score >= 80) return 'text-green-600'
  if (score >= 60) return 'text-yellow-600'
  return 'text-red-600'
}

function getHealthScoreBg(score: number): string {
  if (score >= 80) return 'bg-green-100 border-green-200'
  if (score >= 60) return 'bg-yellow-100 border-yellow-200'
  return 'bg-red-100 border-red-200'
}

function getPriorityColor(priority: string): string {
  if (priority === 'High') return 'bg-red-100 text-red-700'
  if (priority === 'Medium') return 'bg-yellow-100 text-yellow-700'
  return 'bg-green-100 text-green-700'
}

function getAgeBucketColor(bucket: string): string {
  if (bucket.includes('0-30')) return 'bg-green-500'
  if (bucket.includes('31-60')) return 'bg-blue-500'
  if (bucket.includes('61-90')) return 'bg-yellow-500'
  if (bucket.includes('91-180')) return 'bg-orange-500'
  if (bucket.includes('181-365')) return 'bg-red-400'
  return 'bg-red-600'
}

// Load itemwise break-even data
async function loadItemwiseBe() {
  if (itemwiseBeData.value) return

  itemwiseBeLoading.value = true
  itemwiseBeError.value = null

  try {
    const result = await apiCall('insights.api.ml.inventory.item_breakeven', {
      period: 'Quarterly'
    })
    itemwiseBeData.value = result
  } catch (e: any) {
    itemwiseBeError.value = e.message || 'Failed to load itemwise break-even data'
  } finally {
    itemwiseBeLoading.value = false
  }
}

function getRagDotClass(rag: string): string {
  if (rag === 'green') return 'bg-green-500'
  if (rag === 'amber') return 'bg-amber-500'
  return 'bg-red-500'
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
  { label: 'Inventory Intelligence' }
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
  isLoading: isLoading.value
}))

// Handle navigation to other dashboards from chat suggestions
function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    'Sales': '/sales-intelligence',
    'Risk': '/risk-intelligence',
    'Procurement': '/procurement-intelligence',
    'Financial': '/financial-intelligence',
    'Customer': '/customer-intelligence',
    'Inventory': '/inventory-intelligence'
  }
  if (routes[target]) {
    router.push(routes[target])
  }
}
</script>

<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 bg-white border-b">
      <div>
        <Breadcrumbs :items="breadcrumbs" />
        <h1 class="text-2xl font-bold text-gray-900 mt-1">Inventory Intelligence</h1>
        <p class="text-sm text-gray-500">Comprehensive inventory analytics with FIFO valuation</p>
      </div>
      <div class="flex items-center gap-3">
        <IntelligenceDateFilter v-model="dateFilter" />
        <button
          @click="trainInventoryIntelligence"
          :disabled="isTraining"
          class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 disabled:opacity-50 border border-blue-200"
        >
          <Loader2 v-if="isTraining" class="w-4 h-4 animate-spin" />
          <Activity v-else class="w-4 h-4" />
          {{ isTraining ? 'Analyzing...' : 'Refresh Analysis' }}
        </button>
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

    <!-- Training Status -->
    <div v-if="trainingStatus" class="mx-6 mt-4">
      <div :class="[
        'px-4 py-2 rounded-lg text-sm',
        trainingStatus.startsWith('✓') ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'
      ]">
        {{ trainingStatus }}
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <Loader2 class="w-12 h-12 mx-auto text-blue-600 animate-spin" />
        <p class="mt-4 text-gray-600">Loading inventory intelligence...</p>
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
        <!-- Health Score -->
        <div :class="['bg-white rounded-xl shadow-sm p-4 border', getHealthScoreBg(stockOverview.health_score)]">
          <div class="flex items-center justify-between">
            <Heart :class="['w-8 h-8', getHealthScoreColor(stockOverview.health_score)]" />
          </div>
          <p :class="['text-2xl font-bold mt-2', getHealthScoreColor(stockOverview.health_score)]">
            {{ stockOverview.health_score || 0 }}
          </p>
          <p class="text-sm text-gray-500">Health Score</p>
        </div>

        <!-- Total SKUs -->
        <div class="bg-white rounded-xl shadow-sm p-4 border cursor-pointer hover:bg-blue-50 transition-colors"
             @click="drillDown.open(INV_ENDPOINT, 'Active SKUs', { metric: 'total_skus' })">
          <div class="flex items-center justify-between">
            <Package class="w-8 h-8 text-blue-500" />
          </div>
          <p class="text-2xl font-bold mt-2">{{ formatNumber(stockOverview.total_skus) }}</p>
          <p class="text-sm text-gray-500">Active SKUs</p>
        </div>

        <!-- Stock Value -->
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <div class="flex items-center justify-between">
            <DollarSign class="w-8 h-8 text-green-500" />
          </div>
          <p class="text-2xl font-bold mt-2">{{ formatCurrency(stockOverview.total_value) }}</p>
          <p class="text-sm text-gray-500">Stock Value</p>
        </div>

        <!-- Out of Stock -->
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <div class="flex items-center justify-between">
            <AlertTriangle class="w-8 h-8 text-red-500" />
            <span class="text-xs text-red-600 font-medium">Alert</span>
          </div>
          <p class="text-2xl font-bold mt-2 text-red-600">{{ formatNumber(stockOverview.out_of_stock_count) }}</p>
          <p class="text-sm text-gray-500">Out of Stock</p>
        </div>

        <!-- Low Stock -->
        <div class="bg-white rounded-xl shadow-sm p-4 border cursor-pointer hover:bg-blue-50 transition-colors"
             @click="drillDown.open(INV_ENDPOINT, 'Low Stock Items', { metric: 'low_stock_items' })">
          <div class="flex items-center justify-between">
            <TrendingDown class="w-8 h-8 text-orange-500" />
          </div>
          <p class="text-2xl font-bold mt-2 text-orange-600">{{ formatNumber(stockOverview.low_stock_count) }}</p>
          <p class="text-sm text-gray-500">Low Stock</p>
        </div>

        <!-- Overstock -->
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <div class="flex items-center justify-between">
            <TrendingUp class="w-8 h-8 text-purple-500" />
          </div>
          <p class="text-2xl font-bold mt-2 text-purple-600">{{ formatNumber(stockOverview.overstock_count) }}</p>
          <p class="text-sm text-gray-500">Overstock</p>
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
          <!-- Stock Overview Tab -->
          <div v-if="activeTab === 'overview'">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Stock by Item Group -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <Boxes class="w-4 h-4" />
                  Stock Value by Item Group
                </h3>
                <div class="bg-white rounded-lg border overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                      <tr>
                        <th class="px-4 py-2 text-left">Item Group</th>
                        <th class="px-4 py-2 text-right">Items</th>
                        <th class="px-4 py-2 text-right">Qty</th>
                        <th class="px-4 py-2 text-right">Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr 
                        v-for="(group, idx) in stockOverview.by_item_group" 
                        :key="idx"
                        class="border-b hover:bg-blue-50"
                      >
                        <td class="px-4 py-2 font-medium">{{ group.item_group }}</td>
                        <td class="px-4 py-2 text-right">{{ formatNumber(group.item_count) }}</td>
                        <td class="px-4 py-2 text-right">{{ formatNumber(group.total_qty) }}</td>
                        <td class="px-4 py-2 text-right font-bold text-green-600">{{ formatCurrency(group.stock_value) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Dead Stock Summary -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <Archive class="w-4 h-4" />
                  Dead Stock (No Sales 180+ Days)
                </h3>
                <div class="bg-red-50 rounded-lg border border-red-200 p-4 mb-4">
                  <div class="flex justify-between items-center">
                    <div>
                      <p class="text-sm text-red-600">Total Dead Stock Value</p>
                      <p class="text-2xl font-bold text-red-700">{{ formatCurrency(deadStock.total_value) }}</p>
                    </div>
                    <div class="text-right">
                      <p class="text-sm text-red-600">Items</p>
                      <p class="text-xl font-bold text-red-700">{{ formatNumber(deadStock.total_items) }}</p>
                    </div>
                  </div>
                </div>
                <div class="bg-white rounded-lg border overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                      <tr>
                        <th class="px-4 py-2 text-left">Item Group</th>
                        <th class="px-4 py-2 text-right">Count</th>
                        <th class="px-4 py-2 text-right">Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr 
                        v-for="(group, idx) in deadStock.by_product_group?.slice(0, 8)" 
                        :key="idx"
                        class="border-b hover:bg-red-50"
                      >
                        <td class="px-4 py-2 font-medium">{{ group.item_group }}</td>
                        <td class="px-4 py-2 text-right">{{ formatNumber(group.count) }}</td>
                        <td class="px-4 py-2 text-right font-bold text-red-600">{{ formatCurrency(group.value) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>

          <!-- Turnover Tab -->
          <div v-if="activeTab === 'turnover'">
            <!-- Turnover Summary -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div class="bg-gradient-to-br from-blue-500 to-blue-600 rounded-lg p-4 text-white">
                <p class="text-sm opacity-80">Turnover Ratio</p>
                <p class="text-2xl font-bold">{{ turnoverAnalysis.overall_turnover_ratio || 0 }}x</p>
              </div>
              <div class="bg-gradient-to-br from-green-500 to-green-600 rounded-lg p-4 text-white">
                <p class="text-sm opacity-80">Days Sales Inventory</p>
                <p class="text-2xl font-bold">{{ turnoverAnalysis.days_sales_inventory || 0 }} days</p>
              </div>
              <div class="bg-gradient-to-br from-purple-500 to-purple-600 rounded-lg p-4 text-white">
                <p class="text-sm opacity-80">COGS (12m)</p>
                <p class="text-2xl font-bold">{{ formatCurrency(turnoverAnalysis.cogs_12m) }}</p>
              </div>
              <div class="bg-gradient-to-br from-orange-500 to-orange-600 rounded-lg p-4 text-white">
                <p class="text-sm opacity-80">Avg Inventory Value</p>
                <p class="text-2xl font-bold">{{ formatCurrency(turnoverAnalysis.avg_inventory_value) }}</p>
              </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Turnover by Product Group -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <BarChart3 class="w-4 h-4" />
                  Turnover by Product Group
                </h3>
                <div class="bg-white rounded-lg border overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                      <tr>
                        <th class="px-4 py-2 text-left">Item Group</th>
                        <th class="px-4 py-2 text-right">Sales 12m</th>
                        <th class="px-4 py-2 text-right">Turnover</th>
                        <th class="px-4 py-2 text-right">DSI</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr 
                        v-for="(group, idx) in turnoverAnalysis.by_product_group" 
                        :key="idx"
                        class="border-b hover:bg-blue-50"
                      >
                        <td class="px-4 py-2 font-medium">{{ group.item_group }}</td>
                        <td class="px-4 py-2 text-right">{{ formatCurrency(group.sales_12m) }}</td>
                        <td class="px-4 py-2 text-right font-bold text-blue-600">{{ group.turnover_ratio }}x</td>
                        <td class="px-4 py-2 text-right">{{ group.dsi }} days</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Fast & Slow Movers -->
              <div class="space-y-6">
                <!-- Fast Moving -->
                <div>
                  <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <TrendingUp class="w-4 h-4 text-green-500" />
                    Fast Moving Items (90d)
                  </h3>
                  <div class="bg-white rounded-lg border overflow-hidden">
                    <table class="w-full text-sm">
                      <thead class="bg-gray-50">
                        <tr>
                          <th class="px-4 py-2 text-left">Item</th>
                          <th class="px-4 py-2 text-right">Sold</th>
                          <th class="px-4 py-2 text-right">Stock</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr 
                          v-for="(item, idx) in turnoverAnalysis.fast_moving?.slice(0, 5)" 
                          :key="idx"
                          class="border-b hover:bg-green-50"
                        >
                          <td class="px-4 py-2 font-medium truncate max-w-[200px]" :title="item.item_name">
                            {{ item.item_code }}
                          </td>
                          <td class="px-4 py-2 text-right text-green-600 font-bold">{{ formatNumber(item.qty_sold) }}</td>
                          <td class="px-4 py-2 text-right">{{ formatNumber(item.current_stock) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- Slow Moving -->
                <div>
                  <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <TrendingDown class="w-4 h-4 text-red-500" />
                    Slow Moving Items (90d)
                  </h3>
                  <div class="bg-white rounded-lg border overflow-hidden">
                    <table class="w-full text-sm">
                      <thead class="bg-gray-50">
                        <tr>
                          <th class="px-4 py-2 text-left">Item</th>
                          <th class="px-4 py-2 text-right">Stock</th>
                          <th class="px-4 py-2 text-right">Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr 
                          v-for="(item, idx) in turnoverAnalysis.slow_moving?.slice(0, 5)" 
                          :key="idx"
                          class="border-b hover:bg-red-50"
                        >
                          <td class="px-4 py-2 font-medium truncate max-w-[200px]" :title="item.item_name">
                            {{ item.item_code }}
                          </td>
                          <td class="px-4 py-2 text-right">{{ formatNumber(item.current_stock) }}</td>
                          <td class="px-4 py-2 text-right text-red-600 font-bold">{{ formatCurrency(item.stock_value) }}</td>
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
                <div class="bg-green-50 rounded-lg p-4 border border-green-200">
                  <p class="text-sm text-green-600">Class A Items</p>
                  <p class="text-2xl font-bold text-green-700">{{ formatNumber(abcXyz.summary?.a_count) }}</p>
                  <p class="text-xs text-green-500">High Value (~80%)</p>
                </div>
                <div class="bg-yellow-50 rounded-lg p-4 border border-yellow-200">
                  <p class="text-sm text-yellow-600">Class B Items</p>
                  <p class="text-2xl font-bold text-yellow-700">{{ formatNumber(abcXyz.summary?.b_count) }}</p>
                  <p class="text-xs text-yellow-500">Medium Value (~15%)</p>
                </div>
                <div class="bg-red-50 rounded-lg p-4 border border-red-200">
                  <p class="text-sm text-red-600">Class C Items</p>
                  <p class="text-2xl font-bold text-red-700">{{ formatNumber(abcXyz.summary?.c_count) }}</p>
                  <p class="text-xs text-red-500">Low Value (~5%)</p>
                </div>
                <div class="bg-blue-50 rounded-lg p-4 border border-blue-200">
                  <p class="text-sm text-blue-600">Class X Items</p>
                  <p class="text-2xl font-bold text-blue-700">{{ formatNumber(abcXyz.summary?.x_count) }}</p>
                  <p class="text-xs text-blue-500">Stable Demand</p>
                </div>
                <div class="bg-purple-50 rounded-lg p-4 border border-purple-200">
                  <p class="text-sm text-purple-600">Class Y Items</p>
                  <p class="text-2xl font-bold text-purple-700">{{ formatNumber(abcXyz.summary?.y_count) }}</p>
                  <p class="text-xs text-purple-500">Variable Demand</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <p class="text-sm text-gray-600">Class Z Items</p>
                  <p class="text-2xl font-bold text-gray-700">{{ formatNumber(abcXyz.summary?.z_count) }}</p>
                  <p class="text-xs text-gray-500">Irregular Demand</p>
                </div>
              </div>

              <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <!-- ABC/XYZ Matrix -->
                <div>
                  <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <Layers class="w-4 h-4" />
                    ABC/XYZ Classification Matrix
                  </h3>
                  <p class="text-sm text-gray-500 mb-4">
                    Classification Date: {{ formatDate(abcXyz.classification_date) }} • {{ formatNumber(abcXyz.total_items) }} items analyzed
                  </p>
                  <div class="bg-white rounded-lg border overflow-hidden">
                    <table class="w-full text-sm">
                      <thead class="bg-gray-50">
                        <tr>
                          <th class="px-4 py-2 text-left">Class</th>
                          <th class="px-4 py-2 text-right">Items</th>
                          <th class="px-4 py-2 text-right">Sales Value</th>
                          <th class="px-4 py-2 text-right">Stock Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr 
                          v-for="(item, idx) in abcXyz.matrix" 
                          :key="idx"
                          class="border-b hover:bg-blue-50"
                        >
                          <td class="px-4 py-2">
                            <span :class="[
                              'px-2 py-1 rounded text-xs font-medium',
                              item.class?.startsWith('A') ? 'bg-green-100 text-green-700' :
                              item.class?.startsWith('B') ? 'bg-yellow-100 text-yellow-700' :
                              'bg-red-100 text-red-700'
                            ]">
                              {{ item.class }}
                            </span>
                          </td>
                          <td class="px-4 py-2 text-right font-bold">{{ formatNumber(item.item_count) }}</td>
                          <td class="px-4 py-2 text-right">{{ formatCurrency(item.sales_value) }}</td>
                          <td class="px-4 py-2 text-right">{{ formatCurrency(item.stock_value) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- ABC Summary -->
                  <h4 class="font-medium text-gray-700 mt-6 mb-3">ABC Summary (by Value)</h4>
                  <div class="bg-white rounded-lg border overflow-hidden">
                    <table class="w-full text-sm">
                      <thead class="bg-gray-50">
                        <tr>
                          <th class="px-4 py-2 text-left">Class</th>
                          <th class="px-4 py-2 text-right">Items</th>
                          <th class="px-4 py-2 text-right">Total Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(item, idx) in abcXyz.abc_summary" :key="idx" class="border-b hover:bg-blue-50">
                          <td class="px-4 py-2">
                            <span :class="[
                              'px-2 py-1 rounded text-xs font-medium',
                              item.class === 'A' ? 'bg-green-100 text-green-700' :
                              item.class === 'B' ? 'bg-yellow-100 text-yellow-700' :
                              'bg-red-100 text-red-700'
                            ]">{{ item.class }}</span>
                          </td>
                          <td class="px-4 py-2 text-right font-bold">{{ formatNumber(item.item_count) }}</td>
                          <td class="px-4 py-2 text-right">{{ formatCurrency(item.total_value) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- Top Items with Strategy -->
                <div>
                  <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <PieChart class="w-4 h-4" />
                    Top Items with Strategy Recommendations
                  </h3>
                  <div class="bg-white rounded-lg border overflow-hidden max-h-[600px] overflow-y-auto">
                    <table class="w-full text-sm">
                      <thead class="bg-gray-50 sticky top-0">
                        <tr>
                          <th class="px-3 py-2 text-left">Item</th>
                          <th class="px-3 py-2 text-center">Class</th>
                          <th class="px-3 py-2 text-right">Sales</th>
                          <th class="px-3 py-2 text-right">Stock</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr 
                          v-for="(item, idx) in abcXyz.top_items?.slice(0, 20)" 
                          :key="idx"
                          class="border-b hover:bg-blue-50"
                        >
                          <td class="px-3 py-2">
                            <div class="font-medium truncate max-w-[120px]" :title="item.item_name">{{ item.item_code }}</div>
                            <div class="text-xs text-gray-500 truncate max-w-[120px]" :title="item.item_name">{{ item.item_name }}</div>
                          </td>
                          <td class="px-3 py-2 text-center">
                            <span :class="[
                              'px-1.5 py-0.5 rounded text-xs font-bold',
                              item.abc_class === 'A' ? 'bg-green-100 text-green-700' :
                              item.abc_class === 'B' ? 'bg-yellow-100 text-yellow-700' :
                              'bg-red-100 text-red-700'
                            ]">{{ item.abc_class }}</span>
                            <span :class="[
                              'px-1.5 py-0.5 rounded text-xs font-bold ml-1',
                              item.xyz_class === 'X' ? 'bg-blue-100 text-blue-700' :
                              item.xyz_class === 'Y' ? 'bg-purple-100 text-purple-700' :
                              'bg-gray-100 text-gray-700'
                            ]">{{ item.xyz_class }}</span>
                          </td>
                          <td class="px-3 py-2 text-right text-xs">{{ formatCurrency(item.total_value) }}</td>
                          <td class="px-3 py-2 text-right text-xs">{{ formatNumber(item.stock_qty) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- Strategy Legend -->
                  <div class="mt-4 p-4 bg-gray-50 rounded-lg border">
                    <h4 class="font-medium text-gray-700 mb-2">Strategy Guide</h4>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
                      <div><span class="font-bold text-green-700">AX:</span> JIT inventory, tight control</div>
                      <div><span class="font-bold text-green-600">AY:</span> Safety stock, close monitoring</div>
                      <div><span class="font-bold text-green-500">AZ:</span> Make-to-order preferred</div>
                      <div><span class="font-bold text-yellow-700">BX:</span> Moderate stock levels</div>
                      <div><span class="font-bold text-yellow-600">BY:</span> Regular review cycles</div>
                      <div><span class="font-bold text-yellow-500">BZ:</span> Buffer safety stock</div>
                      <div><span class="font-bold text-red-700">CX:</span> Simple reorder rules</div>
                      <div><span class="font-bold text-red-600">CY:</span> Periodic review</div>
                      <div><span class="font-bold text-red-500">CZ:</span> Consider discontinuing</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-12">
              <Layers class="w-12 h-12 mx-auto text-gray-400" />
              <p class="mt-4 text-gray-600">ABC/XYZ Classification not available</p>
              <p class="text-sm text-gray-500 mb-4">Run ABC/XYZ analysis to see classification data</p>
              <button
                @click="trainAbcXyz"
                :disabled="isTrainingAbcXyz"
                class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                <span v-if="isTrainingAbcXyz">Running Analysis...</span>
                <span v-else>Run ABC/XYZ Classification</span>
              </button>
            </div>
          </div>

          <!-- Itemwise BE Tab -->
          <div v-if="activeTab === 'itemwise-be'">
            <div v-if="itemwiseBeLoading" class="flex items-center justify-center py-12">
              <Loader2 class="w-8 h-8 text-blue-600 animate-spin" />
            </div>
            <div v-else-if="itemwiseBeError" class="text-center py-12 text-red-500">{{ itemwiseBeError }}</div>
            <div v-else-if="itemwiseBeData?.items?.length" class="bg-white rounded-xl shadow-sm border overflow-x-auto">
              <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                  <tr>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Item</th>
                    <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Selling Price</th>
                    <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Variable Cost</th>
                    <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">CM</th>
                    <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">BE Qty</th>
                    <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actual Qty</th>
                    <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Coverage %</th>
                    <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">RAG</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-200">
                  <tr v-for="item in itemwiseBeData.items" :key="item.item_code" class="hover:bg-gray-50">
                    <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ item.item_code }}<br><span class="text-xs text-gray-500">{{ item.item_name }}</span></td>
                    <td class="px-4 py-3 text-sm text-right text-gray-600">{{ formatCurrency(item.selling_price) }}</td>
                    <td class="px-4 py-3 text-sm text-right text-gray-600">{{ formatCurrency(item.variable_cost) }}</td>
                    <td class="px-4 py-3 text-sm text-right font-medium text-gray-900">{{ formatCurrency(item.contribution_margin) }}</td>
                    <td class="px-4 py-3 text-sm text-right text-gray-600">{{ item.be_qty?.toLocaleString() }}</td>
                    <td class="px-4 py-3 text-sm text-right text-gray-600">{{ item.actual_qty?.toLocaleString() }}</td>
                    <td class="px-4 py-3 text-sm text-right font-medium" :class="item.coverage >= 1 ? 'text-green-600' : 'text-red-600'">{{ (item.coverage * 100)?.toFixed(1) }}%</td>
                    <td class="px-4 py-3 text-center">
                      <span class="inline-block w-3 h-3 rounded-full" :class="getRagDotClass(item.rag)"></span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-center py-12 text-gray-500">No item break-even data available</div>
          </div>

          <!-- Aging (FIFO) Tab -->
          <div v-if="activeTab === 'aging'">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Age Buckets Visual -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <Clock class="w-4 h-4" />
                  Stock Age Distribution (FIFO)
                </h3>
                <div class="space-y-3">
                  <div 
                    v-for="(bucket, name) in agingAnalysis.age_buckets" 
                    :key="name"
                    class="flex items-center gap-4"
                  >
                    <div class="w-24 text-sm font-medium text-gray-600">{{ name }}</div>
                    <div class="flex-1 bg-gray-100 rounded-full h-6 overflow-hidden">
                      <div 
                        :class="['h-full rounded-full', getAgeBucketColor(String(name))]"
                        :style="{ 
                          width: `${Math.min(100, (bucket.value / Math.max(...Object.values(agingAnalysis.age_buckets || {}).map((b: any) => b.value || 1))) * 100)}%` 
                        }"
                      ></div>
                    </div>
                    <div class="w-20 text-right text-sm font-bold">{{ formatCurrency(bucket.value) }}</div>
                    <div class="w-12 text-right text-xs text-gray-500">{{ bucket.count }} items</div>
                  </div>
                </div>

                <div class="mt-6 p-4 bg-gray-50 rounded-lg border">
                  <p class="text-sm text-gray-600">
                    <strong>Total Items Analyzed:</strong> {{ formatNumber(agingAnalysis.total_items_analyzed) }}
                  </p>
                  <p class="text-xs text-gray-500 mt-1">
                    Age calculation based on FIFO (First-In-First-Out) valuation method
                  </p>
                </div>
              </div>

              <!-- Aging by Product Group -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <BarChart3 class="w-4 h-4" />
                  Average Age by Product Group
                </h3>
                <div class="bg-white rounded-lg border overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                      <tr>
                        <th class="px-4 py-2 text-left">Item Group</th>
                        <th class="px-4 py-2 text-right">Items</th>
                        <th class="px-4 py-2 text-right">Value</th>
                        <th class="px-4 py-2 text-right">Avg Age</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr 
                        v-for="(group, idx) in agingAnalysis.by_product_group" 
                        :key="idx"
                        class="border-b hover:bg-blue-50"
                      >
                        <td class="px-4 py-2 font-medium">{{ group.item_group }}</td>
                        <td class="px-4 py-2 text-right">{{ formatNumber(group.item_count) }}</td>
                        <td class="px-4 py-2 text-right">{{ formatCurrency(group.total_value) }}</td>
                        <td class="px-4 py-2 text-right">
                          <span :class="[
                            'font-bold',
                            group.avg_age_days <= 30 ? 'text-green-600' :
                            group.avg_age_days <= 90 ? 'text-yellow-600' :
                            'text-red-600'
                          ]">{{ group.avg_age_days }} days</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <!-- Oldest Items -->
            <div class="mt-6">
              <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <AlertTriangle class="w-4 h-4 text-red-500" />
                Oldest Stock Items
              </h3>
              <div class="bg-white rounded-lg border overflow-hidden">
                <table class="w-full text-sm">
                  <thead class="bg-gray-50">
                    <tr>
                      <th class="px-4 py-2 text-left">Item Code</th>
                      <th class="px-4 py-2 text-left">Item Name</th>
                      <th class="px-4 py-2 text-left">Item Group</th>
                      <th class="px-4 py-2 text-right">Qty</th>
                      <th class="px-4 py-2 text-right">Value</th>
                      <th class="px-4 py-2 text-right">Avg Age</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr 
                      v-for="(item, idx) in agingAnalysis.oldest_items" 
                      :key="idx"
                      class="border-b hover:bg-red-50"
                    >
                      <td class="px-4 py-2 font-medium">{{ item.item_code }}</td>
                      <td class="px-4 py-2 truncate max-w-[200px]">{{ item.item_name }}</td>
                      <td class="px-4 py-2">{{ item.item_group }}</td>
                      <td class="px-4 py-2 text-right">{{ formatNumber(item.total_qty) }}</td>
                      <td class="px-4 py-2 text-right">{{ formatCurrency(item.total_value) }}</td>
                      <td class="px-4 py-2 text-right font-bold text-red-600">{{ item.avg_age_days }} days</td>
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
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <Warehouse class="w-4 h-4" />
                  Stock by Warehouse
                </h3>
                <div class="bg-white rounded-lg border overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                      <tr>
                        <th class="px-4 py-2 text-left">Warehouse</th>
                        <th class="px-4 py-2 text-right">Items</th>
                        <th class="px-4 py-2 text-right">Value</th>
                        <th class="px-4 py-2 text-right">% Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(wh, idx) in warehouseAnalysis.by_warehouse"
                        :key="idx"
                        class="border-b hover:bg-blue-50 cursor-pointer rounded transition-colors"
                        @click="drillDown.open(INV_ENDPOINT, wh.warehouse + ' Stock', { metric: 'warehouse_stock', warehouse: wh.warehouse })"
                      >
                        <td class="px-4 py-2 font-medium truncate max-w-[200px]">{{ wh.warehouse }}</td>
                        <td class="px-4 py-2 text-right">{{ formatNumber(wh.item_count) }}</td>
                        <td class="px-4 py-2 text-right font-bold text-green-600">{{ formatCurrency(wh.stock_value) }}</td>
                        <td class="px-4 py-2 text-right">
                          <div class="flex items-center justify-end gap-2">
                            <div class="w-16 bg-gray-100 rounded-full h-2">
                              <div class="bg-blue-500 h-2 rounded-full" :style="{ width: `${wh.pct_of_total}%` }"></div>
                            </div>
                            <span class="text-xs">{{ formatPercent(wh.pct_of_total) }}</span>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <!-- Summary -->
                <div class="mt-4 grid grid-cols-2 gap-4">
                  <div class="bg-blue-50 rounded-lg p-4 border border-blue-200">
                    <p class="text-sm text-blue-600">Total Warehouses</p>
                    <p class="text-2xl font-bold text-blue-700">{{ warehouseAnalysis.total_warehouses }}</p>
                  </div>
                  <div class="bg-green-50 rounded-lg p-4 border border-green-200">
                    <p class="text-sm text-green-600">Total Stock Value</p>
                    <p class="text-2xl font-bold text-green-700">{{ formatCurrency(warehouseAnalysis.total_stock_value) }}</p>
                  </div>
                </div>
              </div>

              <!-- Transfer Recommendations -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <ArrowRightLeft class="w-4 h-4" />
                  Transfer Recommendations
                </h3>
                <p class="text-sm text-gray-500 mb-4">
                  Suggested stock transfers to balance inventory across warehouses
                </p>
                <div v-if="transferRecommendations.length > 0" class="space-y-3">
                  <div 
                    v-for="(rec, idx) in transferRecommendations.slice(0, 8)" 
                    :key="idx"
                    class="bg-white rounded-lg border p-4 hover:shadow-md transition-shadow"
                  >
                    <div class="flex items-center justify-between mb-2">
                      <span class="font-medium truncate max-w-[200px]" :title="rec.item_name">
                        {{ rec.item_code }}
                      </span>
                      <span :class="['text-xs px-2 py-1 rounded', getPriorityColor(rec.priority)]">
                        {{ rec.priority }}
                      </span>
                    </div>
                    <div class="flex items-center gap-2 text-sm text-gray-600">
                      <span class="truncate max-w-[100px]" :title="rec.from_warehouse">{{ rec.from_warehouse }}</span>
                      <ArrowRight class="w-4 h-4 text-blue-500 flex-shrink-0" />
                      <span class="truncate max-w-[100px]" :title="rec.to_warehouse">{{ rec.to_warehouse }}</span>
                    </div>
                    <div class="mt-2 flex justify-between items-center">
                      <span class="text-xs text-gray-500">{{ rec.reason }}</span>
                      <span class="text-sm font-bold text-blue-600">{{ formatNumber(rec.recommended_qty) }} units</span>
                    </div>
                  </div>
                </div>
                <div v-else class="text-center py-8 bg-gray-50 rounded-lg border">
                  <ArrowRightLeft class="w-8 h-8 mx-auto text-gray-400" />
                  <p class="mt-2 text-gray-600">No transfer recommendations</p>
                  <p class="text-sm text-gray-500">Stock is well-balanced across warehouses</p>
                </div>
              </div>
            </div>

            <!-- Multi-Warehouse Items -->
            <div class="mt-6">
              <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <Boxes class="w-4 h-4" />
                Items in Multiple Warehouses
              </h3>
              <div class="bg-white rounded-lg border overflow-hidden">
                <table class="w-full text-sm">
                  <thead class="bg-gray-50">
                    <tr>
                      <th class="px-4 py-2 text-left">Item Code</th>
                      <th class="px-4 py-2 text-left">Item Name</th>
                      <th class="px-4 py-2 text-right">Warehouses</th>
                      <th class="px-4 py-2 text-right">Total Qty</th>
                      <th class="px-4 py-2 text-left">Distribution</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr 
                      v-for="(item, idx) in warehouseAnalysis.multi_warehouse_items?.slice(0, 10)" 
                      :key="idx"
                      class="border-b hover:bg-blue-50"
                    >
                      <td class="px-4 py-2 font-medium">{{ item.item_code }}</td>
                      <td class="px-4 py-2 truncate max-w-[150px]">{{ item.item_name }}</td>
                      <td class="px-4 py-2 text-right">
                        <span class="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-bold">
                          {{ item.warehouse_count }}
                        </span>
                      </td>
                      <td class="px-4 py-2 text-right font-bold">{{ formatNumber(item.total_qty) }}</td>
                      <td class="px-4 py-2 text-xs text-gray-500 truncate max-w-[200px]" :title="item.distribution">
                        {{ item.distribution }}
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
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <Truck class="w-4 h-4" />
                  Supplier Performance (12m)
                </h3>
                <div class="bg-white rounded-lg border overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                      <tr>
                        <th class="px-4 py-2 text-left">Supplier</th>
                        <th class="px-4 py-2 text-right">Orders</th>
                        <th class="px-4 py-2 text-right">Value</th>
                        <th class="px-4 py-2 text-right">Lead Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr 
                        v-for="(supplier, idx) in procurementInsights.supplier_performance" 
                        :key="idx"
                        class="border-b hover:bg-blue-50"
                      >
                        <td class="px-4 py-2 font-medium truncate max-w-[150px]" :title="supplier.supplier_name">
                          {{ supplier.supplier_name || supplier.supplier }}
                        </td>
                        <td class="px-4 py-2 text-right">{{ formatNumber(supplier.order_count) }}</td>
                        <td class="px-4 py-2 text-right font-bold text-green-600">{{ formatCurrency(supplier.total_value) }}</td>
                        <td class="px-4 py-2 text-right">
                          <span :class="[
                            'font-medium',
                            supplier.avg_lead_time <= 7 ? 'text-green-600' :
                            supplier.avg_lead_time <= 14 ? 'text-yellow-600' :
                            'text-red-600'
                          ]">{{ Math.round(supplier.avg_lead_time || 0) }} days</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Reorder Needed -->
              <div>
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <ShoppingCart class="w-4 h-4" />
                  Items Needing Reorder
                  <span class="ml-2 px-2 py-1 bg-red-100 text-red-700 rounded text-xs font-bold">
                    {{ procurementInsights.reorder_count }}
                  </span>
                </h3>
                <div class="bg-white rounded-lg border overflow-hidden">
                  <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                      <tr>
                        <th class="px-4 py-2 text-left">Item</th>
                        <th class="px-4 py-2 text-right">Stock</th>
                        <th class="px-4 py-2 text-right">Reorder Level</th>
                        <th class="px-4 py-2 text-right">Daily Demand</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr 
                        v-for="(item, idx) in procurementInsights.reorder_needed?.slice(0, 10)" 
                        :key="idx"
                        class="border-b hover:bg-red-50"
                      >
                        <td class="px-4 py-2 font-medium truncate max-w-[150px]" :title="item.item_name">
                          {{ item.item_code }}
                        </td>
                        <td class="px-4 py-2 text-right text-red-600 font-bold">{{ formatNumber(item.current_stock) }}</td>
                        <td class="px-4 py-2 text-right">{{ formatNumber(item.reorder_level) }}</td>
                        <td class="px-4 py-2 text-right">{{ (item.avg_daily_demand || 0).toFixed(1) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <!-- Pending Orders -->
            <div class="mt-6">
              <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <Clock class="w-4 h-4" />
                Pending Purchase Orders
                <span class="ml-2 px-2 py-1 bg-orange-100 text-orange-700 rounded text-xs font-bold">
                  {{ procurementInsights.pending_orders_count }}
                </span>
              </h3>
              <div class="bg-white rounded-lg border overflow-hidden">
                <table class="w-full text-sm">
                  <thead class="bg-gray-50">
                    <tr>
                      <th class="px-4 py-2 text-left">PO Number</th>
                      <th class="px-4 py-2 text-left">Supplier</th>
                      <th class="px-4 py-2 text-left">Date</th>
                      <th class="px-4 py-2 text-right">Value</th>
                      <th class="px-4 py-2 text-right">Days Pending</th>
                      <th class="px-4 py-2 text-center">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr 
                      v-for="(order, idx) in procurementInsights.pending_orders" 
                      :key="idx"
                      class="border-b hover:bg-orange-50"
                    >
                      <td class="px-4 py-2 font-medium">{{ order.name }}</td>
                      <td class="px-4 py-2 truncate max-w-[150px]">{{ order.supplier }}</td>
                      <td class="px-4 py-2">{{ order.transaction_date }}</td>
                      <td class="px-4 py-2 text-right font-bold">{{ formatCurrency(order.grand_total) }}</td>
                      <td class="px-4 py-2 text-right">
                        <span :class="[
                          'font-medium',
                          order.days_pending <= 7 ? 'text-green-600' :
                          order.days_pending <= 14 ? 'text-yellow-600' :
                          'text-red-600'
                        ]">{{ order.days_pending }} days</span>
                      </td>
                      <td class="px-4 py-2 text-center">
                        <span class="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                          {{ order.status }}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Demand Planning Integration -->
            <div v-if="demandPlanning" class="mt-6">
              <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <Activity class="w-4 h-4" />
                Demand Planning Summary
              </h3>
              <div class="grid grid-cols-4 gap-4 mb-4">
                <div class="bg-blue-50 rounded-lg p-4 border border-blue-200">
                  <p class="text-sm text-blue-600">Total Items</p>
                  <p class="text-xl font-bold text-blue-700">{{ demandPlanning.summary?.total_items || 0 }}</p>
                </div>
                <div class="bg-red-50 rounded-lg p-4 border border-red-200">
                  <p class="text-sm text-red-600">Reorder Now</p>
                  <p class="text-xl font-bold text-red-700">{{ demandPlanning.summary?.reorder_now_count || 0 }}</p>
                </div>
                <div class="bg-yellow-50 rounded-lg p-4 border border-yellow-200">
                  <p class="text-sm text-yellow-600">Monitor</p>
                  <p class="text-xl font-bold text-yellow-700">{{ demandPlanning.summary?.monitor_count || 0 }}</p>
                </div>
                <div class="bg-green-50 rounded-lg p-4 border border-green-200">
                  <p class="text-sm text-green-600">Adequate</p>
                  <p class="text-xl font-bold text-green-700">{{ demandPlanning.summary?.adequate_count || 0 }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

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
