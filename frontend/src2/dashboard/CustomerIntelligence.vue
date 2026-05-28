<script setup lang="ts">
defineOptions({ name: 'CustomerIntelligence' })
import { Breadcrumbs, FormControl } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { 
  RefreshCcw, Loader2, TrendingUp, AlertTriangle, Users, DollarSign, 
  Target, Heart, MapPin, BarChart3, PieChart, Activity, Zap, 
  UserCheck, UserX, ChevronRight, ArrowUpRight, ArrowDownRight,
  Search, Filter, Star
} from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createToast } from '../helpers/toasts'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import TerritoryMap from '../components/TerritoryMap.vue'
import {
  formatCurrency, formatNumber, formatPercent,
  getTierColor, getTierIcon, getRiskColor, getHealthColor, getHealthBgColor,
  getRfmColor, getPriorityColor,
  tierFilterOptions, rfmSegmentFilterOptions, riskFilterOptions,
  getRecentCustomers, addRecentCustomer,
} from '../utils/customerUtils'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'

const router = useRouter()

const CUST_ENDPOINT = 'insights.api.ml.customer.get_customer_detail'
const drillDown = useDrillDown()

// Recommendation tier helpers
const recTierConfig: Record<number, { label: string; style: string }> = {
  0: { label: 'Seasonal', style: 'bg-purple-100 text-purple-700' },
  1: { label: 'Rules', style: 'bg-blue-100 text-blue-700' },
  2: { label: 'FBT', style: 'bg-teal-100 text-teal-700' },
  3: { label: 'Popular', style: 'bg-amber-100 text-amber-700' },
  4: { label: 'Explore', style: 'bg-gray-100 text-gray-600' },
}
function getRecTierLabel(tier: number) { return recTierConfig[tier]?.label || `Tier ${tier}` }
function getRecTierStyle(tier: number) { return recTierConfig[tier]?.style || 'bg-gray-100 text-gray-600' }

// State
const isLoading = ref(true)
const isRefreshing = ref(false)
const error = ref<string | null>(null)
const data = ref<any>(null)
const crossSellData = ref<any>(null)
const purchasePatternsData = ref<any>(null)
const counts = ref<any>(null)
const revenueSplit = ref<any>(null)
const rankings = ref<any>(null)
const variance = ref<any>(null)
const activeCutoff = ref('6')
const territoryMapData = ref({ world: [], india: [], unmapped: [] })
const isLoadingCrossSell = ref(false)
const isLoadingPatterns = ref(false)

// Active tab
const activeTab = ref('overview')
const tabs = [
  { id: 'overview', label: 'Overview', icon: PieChart },
  { id: 'customers', label: 'Customers', icon: Users },
  { id: 'geography', label: 'Geography', icon: MapPin },
  { id: 'actions', label: 'Actions', icon: Zap },
  { id: 'cohorts', label: 'Cohorts', icon: BarChart3 },
  { id: 'cross-sell', label: 'Cross-sell', icon: Target },
  { id: 'patterns', label: 'Patterns', icon: Activity },
  { id: 'rankings', label: 'Rankings', icon: TrendingUp },
  { id: 'territory', label: 'Territory', icon: MapPin },
]

// Date filter
const dateFilter = ref('12m')

// Customer filters
const customerFilter = ref('')
const tierFilter = ref('')
const riskFilter = ref('')
const rfmFilter = ref('')
const recentCustomerIds = ref<string[]>(getRecentCustomers())

// Load customer intelligence data
async function loadData(refresh = false) {
  if (refresh) {
    isRefreshing.value = true
  } else {
    isLoading.value = true
  }
  error.value = null
  
  try {
    const result = await apiCall('insights.api.ml.customer_intelligence', {
      refresh: refresh,
      date_filter: dateFilter.value
    })

    if (result?.status === 'queued') {
      createToast({
        title: 'Processing',
        message: result.message || 'Analysis queued for processing',
        variant: 'info'
      })
      // Poll for results
      setTimeout(() => checkJobStatus(), 5000)
    } else {
      data.value = result
      createToast({
        title: 'Data Loaded',
        message: `Analyzed ${result?.summary?.total_customers || 0} customers`,
        variant: 'success'
      })
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to load customer intelligence'
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

async function checkJobStatus() {
  try {
    const status = await apiCall('insights.api.ml.customer_intelligence_status')
    if (status?.status === 'completed') {
      data.value = status.result
      createToast({
        title: 'Analysis Complete',
        message: 'Customer intelligence analysis finished',
        variant: 'success'
      })
    } else if (status?.status !== 'not_found') {
      // Still processing, check again
      setTimeout(() => checkJobStatus(), 5000)
    }
  } catch (e) {
    console.error('Failed to check job status:', e)
  }
}

// Load cross-sell opportunities
async function loadCrossSellData() {
  if (crossSellData.value) return // Already loaded
  
  isLoadingCrossSell.value = true
  try {
    crossSellData.value = await apiCall('insights.api.ml.cross_sell_opportunities', {
      tier_filter: 'Diamond,Platinum,Gold'
    })
  } catch (e: any) {
    console.error('Failed to load cross-sell data:', e)
  } finally {
    isLoadingCrossSell.value = false
  }
}

// Load purchase patterns
async function loadPurchasePatterns() {
  if (purchasePatternsData.value) return // Already loaded

  isLoadingPatterns.value = true
  try {
    purchasePatternsData.value = await apiCall('insights.api.ml.purchase_patterns', {
      top_percentile: 20
    })
  } catch (e: any) {
    console.error('Failed to load purchase patterns:', e)
  } finally {
    isLoadingPatterns.value = false
  }
}

async function loadCustomerCounts() {
  try {
    counts.value = await apiCall('insights.api.ml.customer.customer_counts', {
      date_filter: dateFilter.value,
      active_cutoff_months: activeCutoff.value,
    })
  } catch (e: any) {
    console.error('Failed to load customer counts:', e)
  }
}

async function loadRankings() {
  try {
    rankings.value = await apiCall('insights.api.ml.customer.customer_rankings', {
      date_filter: dateFilter.value,
    })
  } catch (e: any) {
    console.error('Failed to load rankings:', e)
  }
}

async function loadRevenueSplit() {
  try {
    revenueSplit.value = await apiCall('insights.api.ml.customer.customer_revenue_split', {
      date_filter: dateFilter.value,
    })
  } catch (e: any) {
    console.error('Failed to load revenue split:', e)
  }
}

async function loadVariance() {
  try {
    variance.value = await apiCall('insights.api.ml.customer.customer_variance', {
      date_filter: dateFilter.value,
    })
  } catch (e: any) {
    console.error('Failed to load variance:', e)
  }
}

watch(activeCutoff, () => loadCustomerCounts())

// Navigate to customer detail & track recent
function viewCustomerDetail(customerId: string) {
  recentCustomerIds.value = addRecentCustomer(customerId)
  router.push(`/customer/${customerId}`)
}

// Watch tab changes to load data
import { watch } from 'vue'
watch(activeTab, (newTab) => {
  if (newTab === 'cross-sell') loadCrossSellData()
  if (newTab === 'patterns') loadPurchasePatterns()
})

// Computed values
const summary = computed(() => data.value?.summary || {})
const customers = computed(() => {
  let list = data.value?.customers || []
  
  // Apply filters
  if (customerFilter.value) {
    const search = customerFilter.value.toLowerCase()
    list = list.filter((c: any) => 
      c.customer_name?.toLowerCase().includes(search) ||
      c.customer_id?.toLowerCase().includes(search) ||
      c.territory?.toLowerCase().includes(search) ||
      c.rfm_segment?.toLowerCase().includes(search)
    )
  }
  
  if (tierFilter.value) {
    list = list.filter((c: any) => c.clv_tier === tierFilter.value)
  }
  
  if (riskFilter.value) {
    list = list.filter((c: any) => c.churn_risk === riskFilter.value)
  }
  
  if (rfmFilter.value) {
    list = list.filter((c: any) => c.rfm_segment === rfmFilter.value)
  }
  
  return list
})

// Recent customers with details
const recentCustomerDetails = computed(() => {
  const allCustomers = data.value?.customers || []
  return recentCustomerIds.value
    .map((id: string) => allCustomers.find((c: any) => c.customer_id === id))
    .filter(Boolean)
})

const atRiskCustomers = computed(() => data.value?.at_risk_customers || [])
const topCustomers = computed(() => data.value?.top_customers || [])
const geoAnalysis = computed(() => data.value?.geographic_analysis || {})
const paretoAnalysis = computed(() => data.value?.pareto_analysis || {})
const cohortAnalysis = computed(() => data.value?.cohort_analysis || {})
const nextActions = computed(() => data.value?.next_best_actions || [])

// Format helpers imported from ../utils/customerUtils

// Chat context for AI insights
const chatContext = computed(() => ({
  summary: data.value?.summary || {},
  customerList: data.value?.customers || [],
  segmentation: data.value?.segmentation || {},
  geographicDistribution: data.value?.geographic_distribution || {},
  actionableInsights: data.value?.actionable_insights || [],
  cohortAnalysis: data.value?.cohort_analysis || [],
  topCustomers: data.value?.top_customers || [],
  churnRisk: data.value?.churn_risk || {},
  activeTab: activeTab.value,
  filters: {
    customer: customerFilter.value,
    tier: tierFilter.value,
    risk: riskFilter.value
  }
}))

// Handle navigation to other dashboards from chat suggestions
function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    'Sales': '/sales-intelligence',
    'Risk': '/risk-intelligence',
    'Inventory': '/inventory-intelligence',
    'Procurement': '/procurement-intelligence',
    'Financial': '/financial-intelligence',
    'Customer': '/customer-intelligence'
  }
  if (routes[target]) {
    router.push(routes[target])
  }
}

// Reload when date filter changes
watch(dateFilter, () => {
  loadData()
  loadCustomerCounts()
  loadRankings()
  loadRevenueSplit()
  loadVariance()
})

// Load data on mount
onMounted(() => {
  recentCustomerIds.value = getRecentCustomers()
  loadData()
  loadCustomerCounts()
  loadRankings()
  loadRevenueSplit()
  loadVariance()
})
</script>

<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 bg-white border-b">
      <div class="flex items-center gap-4">
        <Breadcrumbs
          :items="[
            { label: 'Dashboards', route: '/dashboards' },
            { label: 'Customer Intelligence' }
          ]"
        />
      </div>
      
      <div class="flex items-center gap-3">
        <IntelligenceDateFilter v-model="dateFilter" />
        <button
          @click="loadData(true)"
          :disabled="isRefreshing"
          class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <RefreshCcw v-if="!isRefreshing" class="w-4 h-4" />
          <Loader2 v-else class="w-4 h-4 animate-spin" />
          {{ isRefreshing ? 'Refreshing...' : 'Refresh Analysis' }}
        </button>
      </div>
    </div>
    
    <!-- Loading State -->
    <div v-if="isLoading" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <Loader2 class="w-12 h-12 mx-auto text-blue-500 animate-spin" />
        <p class="mt-4 text-gray-600">Loading Customer Intelligence...</p>
      </div>
    </div>
    
    <!-- Error State -->
    <div v-else-if="error" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <AlertTriangle class="w-12 h-12 mx-auto text-red-500" />
        <p class="mt-4 text-gray-600">{{ error }}</p>
        <button 
          @click="loadData()" 
          class="px-4 py-2 mt-4 text-white bg-blue-600 rounded-lg hover:bg-blue-700"
        >
          Try Again
        </button>
      </div>
    </div>
    
    <!-- Main Content -->
    <div v-else class="flex-1 overflow-auto">
      <!-- Summary Cards -->
      <div class="grid grid-cols-2 gap-4 p-6 lg:grid-cols-4">
        <!-- Total CLV -->
        <div class="p-4 bg-white rounded-xl shadow-sm">
          <div class="flex items-center gap-3">
            <div class="p-2 bg-green-100 rounded-lg">
              <DollarSign class="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p class="text-sm text-gray-500">Total CLV</p>
              <p class="text-xl font-bold text-gray-900">{{ formatCurrency(summary.total_clv) }}</p>
            </div>
          </div>
        </div>
        
        <!-- Total Customers -->
        <div class="p-4 bg-white rounded-xl shadow-sm cursor-pointer hover:bg-blue-50 transition-colors"
             @click="drillDown.open(CUST_ENDPOINT, 'Total Customers', { metric: 'total_customers' })">
          <div class="flex items-center gap-3">
            <div class="p-2 bg-blue-100 rounded-lg">
              <Users class="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p class="text-sm text-gray-500">Customers</p>
              <p class="text-xl font-bold text-gray-900">{{ formatNumber(summary.total_customers) }}</p>
            </div>
          </div>
        </div>
        
        <!-- Health Score -->
        <div class="p-4 bg-white rounded-xl shadow-sm">
          <div class="flex items-center gap-3">
            <div class="p-2 bg-purple-100 rounded-lg">
              <Heart class="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p class="text-sm text-gray-500">Avg Health Score</p>
              <p class="text-xl font-bold text-gray-900">{{ formatNumber(summary.avg_health_score, 1) }}</p>
            </div>
          </div>
        </div>
        
        <!-- At Risk -->
        <div class="p-4 bg-white rounded-xl shadow-sm">
          <div class="flex items-center gap-3">
            <div class="p-2 bg-red-100 rounded-lg">
              <AlertTriangle class="w-5 h-5 text-red-600" />
            </div>
            <div>
              <p class="text-sm text-gray-500">At Risk</p>
              <p class="text-xl font-bold text-gray-900">{{ atRiskCustomers.length }}</p>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Customer Counts Summary -->
      <div v-if="counts" class="grid grid-cols-2 gap-3 p-6 lg:grid-cols-4 xl:grid-cols-8">
        <div class="p-3 bg-white rounded-xl shadow-sm text-center">
          <p class="text-xs text-gray-500">Total</p>
          <p class="text-lg font-bold">{{ counts.total?.toLocaleString() }}</p>
        </div>
        <div class="p-3 bg-white rounded-xl shadow-sm text-center">
          <p class="text-xs text-gray-500">New</p>
          <p class="text-lg font-bold text-green-600">{{ counts.new_by_creation?.toLocaleString() }}</p>
        </div>
        <div class="p-3 bg-white rounded-xl shadow-sm text-center">
          <p class="text-xs text-gray-500">Existing</p>
          <p class="text-lg font-bold">{{ counts.existing?.toLocaleString() }}</p>
        </div>
        <div class="p-3 bg-white rounded-xl shadow-sm text-center">
          <p class="text-xs text-gray-500">Active</p>
          <p class="text-lg font-bold text-blue-600">{{ counts.active?.toLocaleString() }}</p>
        </div>
        <div class="p-3 bg-white rounded-xl shadow-sm text-center">
          <p class="text-xs text-gray-500">Inactive</p>
          <p class="text-lg font-bold text-red-500">{{ counts.inactive?.toLocaleString() }}</p>
        </div>
        <div class="p-3 bg-white rounded-xl shadow-sm text-center">
          <p class="text-xs text-gray-500">Advance Pay</p>
          <p class="text-lg font-bold text-purple-600">{{ counts.advance_payment?.toLocaleString() }}</p>
        </div>
        <div class="p-3 bg-white rounded-xl shadow-sm text-center">
          <p class="text-xs text-gray-500">Manufacturers</p>
          <p class="text-lg font-bold">{{ counts.manufacturers?.toLocaleString() }}</p>
        </div>
        <div class="p-3 bg-white rounded-xl shadow-sm text-center">
          <p class="text-xs text-gray-500">Traders</p>
          <p class="text-lg font-bold">{{ counts.traders?.toLocaleString() }}</p>
        </div>
      </div>

      <!-- Active Cutoff Selector -->
      <div class="px-6 mb-4">
        <select v-model="activeCutoff" class="px-3 py-1 text-sm border rounded-lg">
          <option value="3">Active: 3 months</option>
          <option value="6">Active: 6 months</option>
          <option value="12">Active: 12 months</option>
        </select>
      </div>

      <!-- Tabs -->
      <div class="px-6">
        <div class="flex gap-1 p-1 bg-gray-100 rounded-lg w-fit">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            @click="activeTab = tab.id"
            :class="[
              'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition-colors',
              activeTab === tab.id 
                ? 'bg-white text-gray-900 shadow-sm' 
                : 'text-gray-600 hover:text-gray-900'
            ]"
          >
            <component :is="tab.icon" class="w-4 h-4" />
            {{ tab.label }}
          </button>
        </div>
      </div>
      
      <!-- Tab Content -->
      <div class="p-6">
        <!-- Overview Tab -->
        <div v-if="activeTab === 'overview'" class="grid gap-6 lg:grid-cols-2">
          <!-- CLV Tier Distribution -->
          <div class="p-6 bg-white rounded-xl shadow-sm">
            <h3 class="mb-4 text-lg font-semibold text-gray-900">CLV Tier Distribution</h3>
            <div class="space-y-3">
              <div 
                v-for="(count, tier) in summary.clv_tier_distribution" 
                :key="tier"
                class="flex items-center gap-3"
              >
                <div :class="['w-3 h-3 rounded-full', getTierColor(String(tier))]"></div>
                <span class="flex-1 text-gray-700">{{ tier }}</span>
                <span class="font-medium text-gray-900">{{ count }}</span>
                <div class="w-24 h-2 bg-gray-100 rounded-full">
                  <div 
                    :class="[getTierColor(String(tier)), 'h-full rounded-full']"
                    :style="{ width: `${(count / summary.total_customers) * 100}%` }"
                  ></div>
                </div>
              </div>
            </div>
          </div>
          
          <!-- Churn Risk Distribution -->
          <div class="p-6 bg-white rounded-xl shadow-sm">
            <h3 class="mb-4 text-lg font-semibold text-gray-900">Churn Risk Distribution</h3>
            <div class="space-y-3">
              <div 
                v-for="(count, risk) in summary.churn_risk_distribution" 
                :key="risk"
                class="flex items-center gap-3"
              >
                <span :class="['px-2 py-0.5 text-xs font-medium rounded', getRiskColor(String(risk))]">
                  {{ risk }}
                </span>
                <span class="flex-1"></span>
                <span class="font-medium text-gray-900">{{ count }}</span>
                <span class="text-sm text-gray-500">
                  {{ formatPercent((count / summary.total_customers) * 100) }}
                </span>
              </div>
            </div>
          </div>
          
          <!-- Pareto Analysis -->
          <div class="p-6 bg-white rounded-xl shadow-sm">
            <h3 class="mb-4 text-lg font-semibold text-gray-900">80/20 Analysis</h3>
            <div class="space-y-4">
              <div class="flex items-center justify-between p-3 rounded-lg bg-blue-50">
                <span class="text-blue-700">Top 10% contribute</span>
                <span class="text-xl font-bold text-blue-900">
                  {{ formatPercent(paretoAnalysis.top_10_percent_contribute) }}
                </span>
              </div>
              <div class="flex items-center justify-between p-3 rounded-lg bg-purple-50">
                <span class="text-purple-700">Top 20% contribute</span>
                <span class="text-xl font-bold text-purple-900">
                  {{ formatPercent(paretoAnalysis.top_20_percent_contribute) }}
                </span>
              </div>
              <div class="flex items-center justify-between p-3 rounded-lg bg-green-50">
                <span class="text-green-700">Customers for 80% revenue</span>
                <span class="text-xl font-bold text-green-900">
                  {{ formatPercent(paretoAnalysis.top_80_percent_customers) }}
                </span>
              </div>
            </div>
          </div>
          
          <!-- Health Distribution -->
          <div class="p-6 bg-white rounded-xl shadow-sm">
            <h3 class="mb-4 text-lg font-semibold text-gray-900">Health Distribution</h3>
            <div class="space-y-3">
              <div 
                v-for="(count, status) in summary.health_distribution" 
                :key="status"
                class="flex items-center gap-3"
              >
                <Heart :class="['w-4 h-4', getHealthColor(String(status))]" />
                <span class="flex-1 text-gray-700">{{ status }}</span>
                <span class="font-medium text-gray-900">{{ count }}</span>
                <span class="text-sm text-gray-500">
                  {{ formatPercent((count / summary.total_customers) * 100) }}
                </span>
              </div>
            </div>
          </div>
        </div>
        
        <!-- Customers Tab (merged Customer 360° search) -->
        <div v-if="activeTab === 'customers'" class="space-y-4">
          <!-- Search & Filters -->
          <div class="flex flex-wrap gap-4 p-4 bg-white rounded-xl">
            <div class="relative flex-1 min-w-[200px]">
              <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                v-model="customerFilter"
                type="text"
                placeholder="Search by name, ID, or territory..."
                class="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div class="flex items-center gap-2">
              <Filter class="w-4 h-4 text-gray-400" />
              <select
                v-model="tierFilter"
                class="px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option v-for="opt in tierFilterOptions" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
              <select
                v-model="rfmFilter"
                class="px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option v-for="opt in rfmSegmentFilterOptions" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
              <select
                v-model="riskFilter"
                class="px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option v-for="opt in riskFilterOptions" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </div>
            <span class="self-center text-sm text-gray-500">
              {{ customers.length }} of {{ data?.customers?.length || 0 }} customers
            </span>
          </div>
          
          <!-- Recent Customers -->
          <div v-if="recentCustomerDetails.length > 0 && !customerFilter && !tierFilter && !riskFilter && !rfmFilter" class="flex items-center gap-3 px-1">
            <Star class="w-4 h-4 text-yellow-500 flex-shrink-0" />
            <span class="text-sm font-medium text-gray-600">Recent:</span>
            <div class="flex gap-2 flex-wrap">
              <button
                v-for="rc in recentCustomerDetails"
                :key="rc.customer_id"
                @click="viewCustomerDetail(rc.customer_id)"
                class="flex items-center gap-1.5 px-3 py-1 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors text-sm text-blue-700"
              >
                <span>{{ getTierIcon(rc.clv_tier) }}</span>
                {{ rc.customer_name }}
              </button>
            </div>
          </div>
          
          <!-- Customer Table -->
          <div class="overflow-hidden bg-white rounded-xl shadow-sm">
            <table class="w-full">
              <thead class="bg-gray-50">
                <tr>
                  <th class="px-4 py-3 text-xs font-medium text-left text-gray-500 uppercase">Customer</th>
                  <th class="px-4 py-3 text-xs font-medium text-left text-gray-500 uppercase">RFM Segment</th>
                  <th class="px-4 py-3 text-xs font-medium text-left text-gray-500 uppercase">CLV Tier</th>
                  <th class="px-4 py-3 text-xs font-medium text-right text-gray-500 uppercase">Total CLV</th>
                  <th class="px-4 py-3 text-xs font-medium text-center text-gray-500 uppercase">Health</th>
                  <th class="px-4 py-3 text-xs font-medium text-center text-gray-500 uppercase">Churn Risk</th>
                  <th class="px-4 py-3 text-xs font-medium text-right text-gray-500 uppercase">Orders</th>
                  <th class="px-4 py-3 text-xs font-medium text-right text-gray-500 uppercase">Recency</th>
                  <th class="px-4 py-3 text-xs font-medium text-center text-gray-500 uppercase"></th>
                </tr>
              </thead>
              <tbody class="divide-y">
                <tr 
                  v-for="customer in customers.slice(0, 100)" 
                  :key="customer.customer_id" 
                  class="hover:bg-blue-50 cursor-pointer transition-colors"
                  @click="viewCustomerDetail(customer.customer_id)"
                >
                  <td class="px-4 py-3">
                    <div class="flex items-center gap-2">
                      <span class="text-lg">{{ getTierIcon(customer.clv_tier) }}</span>
                      <div>
                        <p class="font-medium text-gray-900">{{ customer.customer_name }}</p>
                        <p class="text-sm text-gray-500">{{ customer.territory || 'No territory' }}</p>
                      </div>
                    </div>
                  </td>
                  <td class="px-4 py-3">
                    <span :class="['px-2 py-0.5 text-xs font-medium rounded', getRfmColor(customer.rfm_segment || '')]">
                      {{ customer.rfm_segment || '-' }}
                    </span>
                  </td>
                  <td class="px-4 py-3">
                    <span :class="['inline-flex items-center gap-1.5 px-2 py-1 text-xs font-medium rounded-full text-white', getTierColor(customer.clv_tier)]">
                      {{ customer.clv_tier }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right font-medium text-gray-900">
                    {{ formatCurrency(customer.total_clv || customer.historical_clv) }}
                  </td>
                  <td class="px-4 py-3 text-center">
                    <span :class="['font-medium', getHealthColor(customer.health_status)]">
                      {{ Math.round(customer.health_score || 0) }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-center">
                    <span :class="['px-2 py-0.5 text-xs font-medium rounded', getRiskColor(customer.churn_risk)]">
                      {{ customer.churn_risk }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right text-gray-700">
                    {{ customer.order_count }}
                  </td>
                  <td class="px-4 py-3 text-right text-gray-500">
                    {{ Math.round(customer.recency_days || 0) }}d
                  </td>
                  <td class="px-4 py-3 text-center">
                    <ChevronRight class="w-4 h-4 text-gray-400 inline" />
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-if="customers.length > 100" class="px-4 py-3 text-sm text-center text-gray-500 bg-gray-50">
              Showing 100 of {{ customers.length }} customers
            </div>
          </div>
        </div>
        
        <!-- Geography Tab -->
        <div v-if="activeTab === 'geography'" class="space-y-6">
          <!-- Territory Stats -->
          <div class="grid gap-4 lg:grid-cols-3">
            <div class="p-4 bg-white rounded-xl shadow-sm">
              <p class="text-sm text-gray-500">Territories Covered</p>
              <p class="text-2xl font-bold text-gray-900">{{ geoAnalysis.coverage?.territories_covered || 0 }}</p>
            </div>
            <div class="p-4 bg-white rounded-xl shadow-sm">
              <p class="text-sm text-gray-500">Customer Groups</p>
              <p class="text-2xl font-bold text-gray-900">{{ geoAnalysis.coverage?.customer_groups_covered || 0 }}</p>
            </div>
            <div class="p-4 bg-white rounded-xl shadow-sm">
              <p class="text-sm text-gray-500">Total Revenue</p>
              <p class="text-2xl font-bold text-gray-900">{{ formatCurrency(geoAnalysis.coverage?.total_revenue || 0) }}</p>
            </div>
          </div>
          
          <!-- Territory Table -->
          <div class="overflow-hidden bg-white rounded-xl shadow-sm">
            <div class="px-4 py-3 border-b">
              <h3 class="font-semibold text-gray-900">Territory Performance</h3>
            </div>
            <table class="w-full">
              <thead class="bg-gray-50">
                <tr>
                  <th class="px-4 py-3 text-xs font-medium text-left text-gray-500 uppercase">Territory</th>
                  <th class="px-4 py-3 text-xs font-medium text-right text-gray-500 uppercase">Customers</th>
                  <th class="px-4 py-3 text-xs font-medium text-right text-gray-500 uppercase">Revenue</th>
                  <th class="px-4 py-3 text-xs font-medium text-right text-gray-500 uppercase">Share</th>
                  <th class="px-4 py-3 text-xs font-medium text-right text-gray-500 uppercase">Avg AOV</th>
                  <th class="px-4 py-3 text-xs font-medium text-right text-gray-500 uppercase">Health</th>
                </tr>
              </thead>
              <tbody class="divide-y">
                <tr v-for="territory in geoAnalysis.territory_analysis?.slice(0, 20)" :key="territory.territory" class="hover:bg-gray-50">
                  <td class="px-4 py-3">
                    <div class="flex items-center gap-2">
                      <MapPin class="w-4 h-4 text-gray-400" />
                      <span class="font-medium text-gray-900">{{ territory.territory || 'Unassigned' }}</span>
                    </div>
                  </td>
                  <td class="px-4 py-3 text-right text-gray-700">{{ territory.customer_count }}</td>
                  <td class="px-4 py-3 text-right font-medium text-gray-900">{{ formatCurrency(territory.total_revenue) }}</td>
                  <td class="px-4 py-3 text-right text-gray-500">{{ formatPercent(territory.revenue_share) }}</td>
                  <td class="px-4 py-3 text-right text-gray-700">{{ formatCurrency(territory.avg_order_value) }}</td>
                  <td class="px-4 py-3 text-right">
                    <span :class="territory.avg_health_score >= 60 ? 'text-green-600' : 'text-orange-600'">
                      {{ Math.round(territory.avg_health_score) }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        
        <!-- Actions Tab -->
        <div v-if="activeTab === 'actions'" class="space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-lg font-semibold text-gray-900">Next Best Actions</h3>
            <span class="text-sm text-gray-500">{{ nextActions.length }} action items</span>
          </div>
          
          <div class="space-y-3">
            <div 
              v-for="action in nextActions.slice(0, 30)" 
              :key="action.customer_id"
              class="p-4 bg-white rounded-xl shadow-sm"
            >
              <div class="flex items-start justify-between mb-3">
                <div>
                  <h4 class="font-semibold text-gray-900">{{ action.customer_name }}</h4>
                  <div class="flex items-center gap-2 mt-1">
                    <span :class="['px-2 py-0.5 text-xs font-medium rounded-full text-white', getTierColor(action.clv_tier)]">
                      {{ action.clv_tier }}
                    </span>
                    <span :class="['px-2 py-0.5 text-xs font-medium rounded', getRiskColor(action.churn_risk)]">
                      {{ action.churn_risk }} Risk
                    </span>
                  </div>
                </div>
                <span :class="getHealthColor(action.health_status)">
                  {{ action.health_status }}
                </span>
              </div>
              
              <div class="space-y-2">
                <div 
                  v-for="rec in action.recommendations" 
                  :key="rec.action"
                  :class="['p-3 rounded-lg border', getPriorityColor(rec.priority)]"
                >
                  <div class="flex items-center justify-between mb-1">
                    <span class="text-xs font-bold uppercase">{{ rec.action.replace(/_/g, ' ') }}</span>
                    <span class="text-xs">{{ rec.priority }} Priority</span>
                  </div>
                  <p class="text-sm">{{ rec.description }}</p>
                  <p class="mt-1 text-xs opacity-75">💡 {{ rec.suggestion }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- Cohorts Tab -->
        <div v-if="activeTab === 'cohorts'" class="space-y-6">
          <div class="p-6 bg-white rounded-xl shadow-sm">
            <h3 class="mb-4 text-lg font-semibold text-gray-900">Average Retention by Month</h3>
            <div class="flex flex-wrap gap-2">
              <div 
                v-for="(retention, month) in cohortAnalysis.average_retention" 
                :key="month"
                class="px-3 py-2 text-center bg-blue-50 rounded-lg"
              >
                <p class="text-xs text-blue-600">Month {{ month }}</p>
                <p class="text-lg font-bold text-blue-900">{{ formatPercent(retention) }}</p>
              </div>
            </div>
          </div>
          
          <div class="p-6 bg-white rounded-xl shadow-sm">
            <h3 class="mb-4 text-lg font-semibold text-gray-900">Cohort Retention Matrix</h3>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr>
                    <th class="px-3 py-2 text-left text-gray-500">Cohort</th>
                    <th class="px-3 py-2 text-right text-gray-500">Size</th>
                    <th v-for="n in 12" :key="n" class="px-3 py-2 text-center text-gray-500">M{{ n - 1 }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="cohort in cohortAnalysis.cohort_retention" :key="cohort.cohort">
                    <td class="px-3 py-2 font-medium text-gray-900">{{ cohort.cohort }}</td>
                    <td class="px-3 py-2 text-right text-gray-600">{{ cohort.size }}</td>
                    <td 
                      v-for="n in 12" 
                      :key="n"
                      class="px-3 py-2 text-center"
                    >
                      <span 
                        v-if="cohort.retention[n - 1] !== undefined"
                        :class="[
                          'inline-block px-2 py-1 rounded text-xs font-medium',
                          cohort.retention[n - 1] >= 50 ? 'bg-green-100 text-green-700' :
                          cohort.retention[n - 1] >= 25 ? 'bg-yellow-100 text-yellow-700' :
                          'bg-red-100 text-red-700'
                        ]"
                      >
                        {{ formatPercent(cohort.retention[n - 1]) }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
        
        <!-- Cross-sell Tab -->
        <div v-if="activeTab === 'cross-sell'" class="space-y-6">
          <div v-if="isLoadingCrossSell" class="flex items-center justify-center h-64">
            <div class="text-center">
              <Loader2 class="w-8 h-8 mx-auto text-blue-500 animate-spin" />
              <p class="mt-4 text-gray-500">Loading cross-sell opportunities...</p>
            </div>
          </div>
          
          <div v-else-if="crossSellData">
            <!-- Summary -->
            <div class="grid gap-4 lg:grid-cols-3">
              <div class="p-4 bg-white rounded-xl shadow-sm">
                <p class="text-sm text-gray-500">Target Tiers</p>
                <p class="text-xl font-bold text-purple-600">{{ crossSellData.tier_filter?.join(', ') }}</p>
              </div>
              <div class="p-4 bg-white rounded-xl shadow-sm">
                <p class="text-sm text-gray-500">Customers with Opportunities</p>
                <p class="text-xl font-bold text-gray-900">{{ crossSellData.customer_count || 0 }}</p>
              </div>
              <div class="p-4 bg-white rounded-xl shadow-sm">
                <p class="text-sm text-gray-500">Total Recommendations</p>
                <p class="text-xl font-bold text-green-600">
                  {{ crossSellData.opportunities?.reduce((sum: number, o: any) => sum + (o.recommendations?.length || 0), 0) || 0 }}
                </p>
              </div>
            </div>
            
            <!-- Opportunities List -->
            <div class="space-y-4">
              <h3 class="text-lg font-semibold text-gray-900">Cross-sell Opportunities by Customer</h3>
              <div 
                v-for="opp in crossSellData.opportunities?.slice(0, 20)" 
                :key="opp.customer_id"
                class="p-4 bg-white rounded-xl shadow-sm hover:shadow-md transition-shadow cursor-pointer"
                @click="viewCustomerDetail(opp.customer_id)"
              >
                <div class="flex items-center justify-between mb-3">
                  <div class="flex items-center gap-3">
                    <div>
                      <h4 class="font-semibold text-gray-900">{{ opp.customer_name }}</h4>
                      <p class="text-sm text-gray-500">CLV: {{ formatCurrency(opp.historical_clv) }}</p>
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <span :class="['px-3 py-1 text-sm font-medium text-white rounded-full', getTierColor(opp.clv_tier)]">
                      {{ opp.clv_tier }}
                    </span>
                    <ChevronRight class="w-5 h-5 text-gray-400" />
                  </div>
                </div>
                
                <div class="flex flex-wrap gap-2">
                  <div
                    v-for="rec in opp.recommendations"
                    :key="rec.item_code"
                    class="px-3 py-2 bg-green-50 rounded-lg border border-green-200"
                  >
                    <div class="flex items-center gap-1.5">
                      <p class="text-sm font-medium text-green-800">{{ rec.item_code }}</p>
                      <span
                        v-if="rec.recommendation_tier !== undefined"
                        :class="['px-1.5 py-0.5 text-[10px] font-medium rounded', getRecTierStyle(rec.recommendation_tier)]"
                      >{{ getRecTierLabel(rec.recommendation_tier) }}</span>
                    </div>
                    <p class="text-xs text-green-600">{{ (rec.confidence * 100).toFixed(0) }}% confidence</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          <div v-else class="text-center py-12">
            <Target class="w-12 h-12 mx-auto text-gray-300" />
            <p class="mt-4 text-gray-500">No cross-sell data available</p>
          </div>
        </div>
        
        <!-- Purchase Patterns Tab -->
        <div v-if="activeTab === 'patterns'" class="space-y-6">
          <div v-if="isLoadingPatterns" class="flex items-center justify-center h-64">
            <div class="text-center">
              <Loader2 class="w-8 h-8 mx-auto text-blue-500 animate-spin" />
              <p class="mt-4 text-gray-500">Loading purchase patterns...</p>
            </div>
          </div>
          
          <div v-else-if="purchasePatternsData">
            <!-- Scope Info -->
            <div class="p-4 bg-blue-50 rounded-xl border border-blue-200">
              <p class="text-sm text-blue-700">
                <strong>Analysis Scope:</strong> Top {{ purchasePatternsData.analysis_scope?.top_percentile }}% of customers by CLV
                ({{ purchasePatternsData.analysis_scope?.customer_count }} customers, {{ purchasePatternsData.analysis_scope?.transaction_count }} transactions)
              </p>
            </div>
            
            <!-- Summary Cards -->
            <div class="grid gap-4 lg:grid-cols-4">
              <div class="p-4 bg-white rounded-xl shadow-sm">
                <p class="text-sm text-gray-500">Total Orders</p>
                <p class="text-2xl font-bold text-gray-900">{{ formatNumber(purchasePatternsData.summary?.total_orders) }}</p>
              </div>
              <div class="p-4 bg-white rounded-xl shadow-sm">
                <p class="text-sm text-gray-500">Total Revenue</p>
                <p class="text-2xl font-bold text-green-600">{{ formatCurrency(purchasePatternsData.summary?.total_revenue) }}</p>
              </div>
              <div class="p-4 bg-white rounded-xl shadow-sm">
                <p class="text-sm text-gray-500">Peak Day</p>
                <p class="text-2xl font-bold text-blue-600">{{ purchasePatternsData.summary?.peak_day }}</p>
              </div>
              <div class="p-4 bg-white rounded-xl shadow-sm">
                <p class="text-sm text-gray-500">Peak Month</p>
                <p class="text-2xl font-bold text-purple-600">{{ purchasePatternsData.summary?.peak_month }}</p>
              </div>
            </div>
            
            <!-- Day of Week Analysis -->
            <div class="p-6 bg-white rounded-xl shadow-sm">
              <h3 class="mb-4 text-lg font-semibold text-gray-900">Day of Week Analysis</h3>
              <div class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead class="bg-gray-50">
                    <tr>
                      <th class="px-4 py-2 text-left text-gray-600">Day</th>
                      <th class="px-4 py-2 text-right text-gray-600">Orders</th>
                      <th class="px-4 py-2 text-right text-gray-600">Revenue</th>
                      <th class="px-4 py-2 text-right text-gray-600">Avg Order</th>
                      <th class="px-4 py-2 text-left text-gray-600">Activity</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr 
                      v-for="day in purchasePatternsData.day_of_week?.data" 
                      :key="day.day_name"
                      :class="day.day_name === purchasePatternsData.day_of_week?.peak_day ? 'bg-blue-50' : 'hover:bg-gray-50'"
                    >
                      <td class="px-4 py-2 font-medium">
                        {{ day.day_name }}
                        <span v-if="day.day_name === purchasePatternsData.day_of_week?.peak_day" class="ml-2 text-xs text-blue-600">⭐ Peak</span>
                      </td>
                      <td class="px-4 py-2 text-right">{{ formatNumber(day.order_count) }}</td>
                      <td class="px-4 py-2 text-right">{{ formatCurrency(day.total_revenue) }}</td>
                      <td class="px-4 py-2 text-right">{{ formatCurrency(day.avg_order_value) }}</td>
                      <td class="px-4 py-2">
                        <div class="w-full bg-gray-200 rounded-full h-2">
                          <div 
                            class="bg-blue-600 h-2 rounded-full" 
                            :style="{ width: `${(day.order_count / Math.max(...purchasePatternsData.day_of_week?.data.map((d: any) => d.order_count))) * 100}%` }"
                          ></div>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            
            <!-- Monthly Analysis -->
            <div class="p-6 bg-white rounded-xl shadow-sm">
              <h3 class="mb-4 text-lg font-semibold text-gray-900">Monthly Trends</h3>
              <div class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead class="bg-gray-50">
                    <tr>
                      <th class="px-4 py-2 text-left text-gray-600">Month</th>
                      <th class="px-4 py-2 text-right text-gray-600">Orders</th>
                      <th class="px-4 py-2 text-right text-gray-600">Revenue</th>
                      <th class="px-4 py-2 text-right text-gray-600">Avg Order</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr 
                      v-for="month in purchasePatternsData.monthly?.data" 
                      :key="month.month_name"
                      :class="month.month_name === purchasePatternsData.monthly?.peak_month ? 'bg-purple-50' : 'hover:bg-gray-50'"
                    >
                      <td class="px-4 py-2 font-medium">
                        {{ month.month_name }}
                        <span v-if="month.month_name === purchasePatternsData.monthly?.peak_month" class="ml-2 text-xs text-purple-600">⭐ Peak</span>
                      </td>
                      <td class="px-4 py-2 text-right">{{ formatNumber(month.order_count) }}</td>
                      <td class="px-4 py-2 text-right">{{ formatCurrency(month.total_revenue) }}</td>
                      <td class="px-4 py-2 text-right">{{ formatCurrency(month.avg_order_value) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            
            <!-- Seasonal Analysis -->
            <div class="p-6 bg-white rounded-xl shadow-sm">
              <h3 class="mb-4 text-lg font-semibold text-gray-900">Seasonal Patterns</h3>
              <div class="grid gap-4 lg:grid-cols-4">
                <div 
                  v-for="season in purchasePatternsData.seasonal?.data" 
                  :key="season.quarter"
                  :class="[
                    'p-4 rounded-lg border-2',
                    season.quarter === purchasePatternsData.seasonal?.peak_quarter ? 'border-green-500 bg-green-50' : 'border-gray-200'
                  ]"
                >
                  <p class="text-sm font-medium text-gray-600">{{ season.quarter }}</p>
                  <p class="text-xl font-bold text-gray-900">{{ formatCurrency(season.total_revenue) }}</p>
                  <p class="text-sm text-gray-500">{{ formatNumber(season.order_count) }} orders</p>
                  <p class="text-xs text-gray-400">Avg: {{ formatCurrency(season.avg_order_value) }}</p>
                </div>
              </div>
            </div>
          </div>
          
          <div v-else class="text-center py-12">
            <Activity class="w-12 h-12 mx-auto text-gray-300" />
            <p class="mt-4 text-gray-500">No purchase pattern data available</p>
          </div>
        </div>

        <!-- Rankings Tab -->
        <div v-if="activeTab === 'rankings' && rankings" class="p-6 space-y-6">
          <!-- Top by Revenue -->
          <div class="bg-white rounded-xl shadow-sm p-4">
            <h3 class="text-sm font-semibold text-gray-700 mb-3">Top Customers by Revenue</h3>
            <table class="w-full text-sm">
              <thead><tr class="text-left text-gray-500 border-b">
                <th class="pb-2">Customer</th><th class="pb-2 text-right">Revenue</th>
              </tr></thead>
              <tbody>
                <tr v-for="c in rankings.top_revenue" :key="c.customer"
                    class="border-b last:border-0 cursor-pointer hover:bg-blue-50 rounded transition-colors"
                    @click="drillDown.open(CUST_ENDPOINT, c.customer_name + ' Orders', { metric: 'top_customers', customer: c.customer })">
                  <td class="py-2">{{ c.customer_name }}</td>
                  <td class="py-2 text-right font-medium">{{ Number(c.revenue).toLocaleString() }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <!-- Top by Profit -->
          <div class="bg-white rounded-xl shadow-sm p-4">
            <h3 class="text-sm font-semibold text-gray-700 mb-3">Top Customers by Gross Profit</h3>
            <table class="w-full text-sm">
              <thead><tr class="text-left text-gray-500 border-b">
                <th class="pb-2">Customer</th><th class="pb-2 text-right">Gross Profit</th>
              </tr></thead>
              <tbody>
                <tr v-for="c in rankings.top_profit" :key="c.customer" class="border-b last:border-0">
                  <td class="py-2">{{ c.customer_name }}</td>
                  <td class="py-2 text-right font-medium">{{ Number(c.gross_profit).toLocaleString() }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <!-- Top by Margin -->
          <div class="bg-white rounded-xl shadow-sm p-4">
            <h3 class="text-sm font-semibold text-gray-700 mb-3">Top Customers by Margin %</h3>
            <table class="w-full text-sm">
              <thead><tr class="text-left text-gray-500 border-b">
                <th class="pb-2">Customer</th><th class="pb-2 text-right">Margin %</th><th class="pb-2 text-right">Revenue</th>
              </tr></thead>
              <tbody>
                <tr v-for="c in rankings.top_margin" :key="c.customer" class="border-b last:border-0">
                  <td class="py-2">{{ c.customer_name }}</td>
                  <td class="py-2 text-right font-medium">{{ c.margin_pct }}%</td>
                  <td class="py-2 text-right">{{ Number(c.revenue).toLocaleString() }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <!-- Top Consistent -->
          <div class="bg-white rounded-xl shadow-sm p-4">
            <h3 class="text-sm font-semibold text-gray-700 mb-3">Most Consistent Customers</h3>
            <table class="w-full text-sm">
              <thead><tr class="text-left text-gray-500 border-b">
                <th class="pb-2">Customer</th><th class="pb-2 text-right">Score</th><th class="pb-2 text-right">Months Active</th>
              </tr></thead>
              <tbody>
                <tr v-for="c in rankings.top_consistent" :key="c.customer" class="border-b last:border-0">
                  <td class="py-2">{{ c.customer_name }}</td>
                  <td class="py-2 text-right font-medium">{{ c.consistency_score }}</td>
                  <td class="py-2 text-right">{{ c.months_active }}/{{ c.total_months }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Territory Map Tab -->
        <div v-if="activeTab === 'territory'" class="p-6">
          <div class="bg-white rounded-xl shadow-sm" style="height: 500px">
            <TerritoryMap
              :worldData="territoryMapData.world"
              :indiaData="territoryMapData.india"
              :unmapped="territoryMapData.unmapped"
              metric="Customers"
              colorScale="blue"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- AI Chat Button -->
    <DashboardChatButton
      dashboard-type="Customer"
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
