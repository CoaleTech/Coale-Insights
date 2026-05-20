<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <header class="bg-white border-b px-6 py-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Strategic Finance Intelligence</h1>
        <p class="text-sm text-gray-500 mt-1">
          Forward-looking financial analytics, forecasting, and scenario planning
        </p>
      </div>
      <div class="flex items-center gap-3">
        <span v-if="lastUpdated" class="text-sm text-gray-500">
          Updated: {{ formatDateTime(lastUpdated) }}
        </span>
        <button
          @click="refreshData"
          :disabled="isLoading"
          class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <RefreshCw v-if="!isLoading" class="w-4 h-4" />
          <Loader2 v-else class="w-4 h-4 animate-spin" />
          Refresh
        </button>
        <button
          @click="exportData"
          :disabled="!data"
          class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
        >
          <Download class="w-4 h-4" />
          Export
        </button>
      </div>
    </header>

    <!-- Loading State -->
    <div v-if="isLoading && !data" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <Loader2 class="w-12 h-12 mx-auto text-blue-600 animate-spin" />
        <p class="mt-4 text-gray-600">Loading strategic finance data...</p>
      </div>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <AlertTriangle class="w-12 h-12 mx-auto text-red-500" />
        <p class="mt-4 text-gray-900 font-medium">Failed to load data</p>
        <p class="text-gray-600">{{ error }}</p>
        <button
          @click="refreshData"
          class="mt-4 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700"
        >
          Try Again
        </button>
      </div>
    </div>

    <!-- Main Content -->
    <div v-else-if="data" class="flex-1 overflow-auto">
      <!-- Summary Cards -->
      <div class="p-6 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <div class="bg-white rounded-lg shadow-sm p-4 border">
          <div class="text-sm font-medium text-gray-500">Total Revenue</div>
          <div class="text-2xl font-bold text-gray-900 mt-1">
            {{ formatCurrency(summaryData.totalRevenue) }}
          </div>
          <div :class="summaryData.revenueGrowth >= 0 ? 'text-green-600' : 'text-red-600'" class="text-sm mt-1">
            {{ summaryData.revenueGrowth >= 0 ? '↑' : '↓' }} {{ Math.abs(summaryData.revenueGrowth || 0).toFixed(1) }}% vs last period
          </div>
        </div>
        
        <div class="bg-white rounded-lg shadow-sm p-4 border">
          <div class="text-sm font-medium text-gray-500">Net Profit</div>
          <div class="text-2xl font-bold text-gray-900 mt-1">
            {{ formatCurrency(summaryData.netProfit) }}
          </div>
          <div :class="summaryData.profitMargin >= 0 ? 'text-green-600' : 'text-red-600'" class="text-sm mt-1">
            {{ summaryData.profitMargin?.toFixed(1) || 0 }}% margin
          </div>
        </div>
        
        <div class="bg-white rounded-lg shadow-sm p-4 border">
          <div class="text-sm font-medium text-gray-500">Cash Position</div>
          <div class="text-2xl font-bold text-gray-900 mt-1">
            {{ formatCurrency(summaryData.cashPosition) }}
          </div>
          <div class="text-sm text-gray-500 mt-1">{{ summaryData.cashRunway || 0 }} days runway</div>
        </div>
        
        <div class="bg-white rounded-lg shadow-sm p-4 border">
          <div class="text-sm font-medium text-gray-500">Working Capital</div>
          <div class="text-2xl font-bold text-gray-900 mt-1">
            {{ formatCurrency(summaryData.workingCapital) }}
          </div>
          <div class="text-sm text-gray-500 mt-1">Current Ratio: {{ summaryData.currentRatio?.toFixed(2) || '0' }}</div>
        </div>
        
        <div class="bg-white rounded-lg shadow-sm p-4 border">
          <div class="text-sm font-medium text-gray-500">DSO</div>
          <div class="text-2xl font-bold text-gray-900 mt-1">
            {{ summaryData.dso?.toFixed(0) || 0 }} days
          </div>
          <div class="text-sm text-gray-500 mt-1">Days Sales Outstanding</div>
        </div>
        
        <div class="bg-white rounded-lg shadow-sm p-4 border">
          <div class="text-sm font-medium text-gray-500">Gross Margin</div>
          <div class="text-2xl font-bold text-gray-900 mt-1">
            {{ summaryData.grossMargin?.toFixed(1) || 0 }}%
          </div>
          <div :class="summaryData.grossMargin >= 30 ? 'text-green-600' : 'text-amber-600'" class="text-sm mt-1">
            {{ summaryData.grossMargin >= 30 ? 'Healthy' : 'Below Target' }}
          </div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="bg-white border-b mx-6 rounded-t-lg">
        <div class="flex overflow-x-auto">
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
      </div>

      <!-- Tab Content -->
      <div class="p-6">
        <!-- Executive Summary Tab -->
        <div v-show="activeTab === 'executive'">
          <ExecutiveSummaryTab :data="data?.executive_summary" :expense-breakdown="data?.expense_breakdown" />
        </div>

        <!-- Cash Forecasting Tab -->
        <div v-show="activeTab === 'cash'">
          <CashForecastingTab :data="data?.cash_forecast" />
        </div>

        <!-- 13-Week Cash Flow Tab -->
        <div v-show="activeTab === 'cashflow13'">
          <ThirteenWeekCashFlowTab :data="data?.thirteen_week_forecast" />
        </div>

        <!-- Capital Planning Tab -->
        <div v-show="activeTab === 'capital'">
          <CapitalPlanningTab :data="data?.capital_planning" />
        </div>

        <!-- Working Capital Tab -->
        <div v-show="activeTab === 'working'">
          <WorkingCapitalTab :data="data?.working_capital" />
        </div>

        <!-- Financial Ratios Tab -->
        <div v-show="activeTab === 'ratios'">
          <FinancialRatiosTab :data="data?.ratio_trends" />
        </div>

        <!-- Scenario Analysis Tab -->
        <div v-show="activeTab === 'scenarios'">
          <ScenarioAnalysisTab :data="data?.scenario_analysis" />
        </div>

        <!-- Period Comparison Tab -->
        <div v-show="activeTab === 'comparison'">
          <PeriodComparisonTab :data="data?.period_comparison" />
        </div>

        <!-- Budget Variance Tab -->
        <div v-show="activeTab === 'budget'">
          <BudgetVarianceTab />
        </div>

        <!-- Break-Even Overview Tab -->
        <div v-show="activeTab === 'beOverview'">
          <div v-if="beLoading" class="flex items-center justify-center py-12">
            <Loader2 class="w-8 h-8 text-blue-600 animate-spin" />
          </div>
          <div v-else-if="beError" class="text-center py-12 text-red-500">{{ beError }}</div>
          <div v-else-if="beData" class="space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
              <div class="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border">
                <p class="text-sm text-gray-500 dark:text-gray-400">Fixed Costs</p>
                <p class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ formatCurrency(beData.fixed_costs) }}</p>
              </div>
              <div class="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border">
                <p class="text-sm text-gray-500 dark:text-gray-400">BE Revenue</p>
                <p class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ formatCurrency(beData.be_revenue) }}</p>
              </div>
              <div class="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border">
                <p class="text-sm text-gray-500 dark:text-gray-400">BE Qty</p>
                <p class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ beData.be_qty?.toLocaleString() || 0 }}</p>
              </div>
              <div class="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border">
                <p class="text-sm text-gray-500 dark:text-gray-400">Coverage</p>
                <p class="text-xl font-bold mt-1" :class="beData.coverage >= 1 ? 'text-green-600' : 'text-red-600'">{{ (beData.coverage * 100)?.toFixed(1) || 0 }}%</p>
                <span :class="getRagClass(beData.rag)" class="text-xs px-2 py-0.5 rounded mt-1 inline-block">{{ beData.rag }}</span>
              </div>
              <div class="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border">
                <p class="text-sm text-gray-500 dark:text-gray-400">Safety Margin</p>
                <p class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ beData.safety_margin?.toFixed(1) || 0 }}%</p>
              </div>
            </div>
          </div>
          <div v-else class="text-center py-12 text-gray-500">No break-even data available</div>
        </div>

        <!-- Employeewise BE Tab -->
        <div v-show="activeTab === 'beEmployee'">
          <div v-if="beLoading" class="flex items-center justify-center py-12">
            <Loader2 class="w-8 h-8 text-blue-600 animate-spin" />
          </div>
          <div v-else-if="beError" class="text-center py-12 text-red-500">{{ beError }}</div>
          <div v-else-if="beData?.employee_breakeven?.departments?.length" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div v-for="dept in beData.employee_breakeven.departments" :key="dept.department" class="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border">
              <div class="flex items-center justify-between mb-3">
                <h3 class="font-semibold text-gray-900 dark:text-white">{{ dept.department }}</h3>
                <span class="w-3 h-3 rounded-full" :class="getRagDotClass(dept.rag)"></span>
              </div>
              <div class="space-y-2">
                <div class="flex justify-between text-sm">
                  <span class="text-gray-500 dark:text-gray-400">Payroll Cost</span>
                  <span class="font-medium text-gray-900 dark:text-white">{{ formatCurrency(dept.payroll_cost) }}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-500 dark:text-gray-400">Orders Needed</span>
                  <span class="font-medium text-gray-900 dark:text-white">{{ dept.orders_needed?.toLocaleString() }}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-500 dark:text-gray-400">Actual Orders</span>
                  <span class="font-medium text-gray-900 dark:text-white">{{ dept.actual_orders?.toLocaleString() }}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-500 dark:text-gray-400">Coverage</span>
                  <span class="font-medium" :class="dept.coverage >= 1 ? 'text-green-600' : 'text-red-600'">{{ (dept.coverage * 100)?.toFixed(1) }}%</span>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="text-center py-12 text-gray-500">No employee break-even data available</div>
        </div>

        <!-- Capital Efficiency Tab -->
        <div v-show="activeTab === 'beCapital'">
          <div v-if="beLoading" class="flex items-center justify-center py-12">
            <Loader2 class="w-8 h-8 text-blue-600 animate-spin" />
          </div>
          <div v-else-if="beError" class="text-center py-12 text-red-500">{{ beError }}</div>
          <div v-else-if="beData" class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div class="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border">
              <p class="text-sm text-gray-500 dark:text-gray-400">ROCE</p>
              <p class="text-2xl font-bold mt-1" :class="getRagClass(beData.roce?.rag).split(' ')[1]">{{ beData.roce?.roce?.toFixed(2) || 0 }}%</p>
              <p class="text-xs text-gray-500 mt-1">Target: {{ beData.roce?.target?.toFixed(2) || 0 }}%</p>
              <span :class="getRagClass(beData.roce?.rag)" class="text-xs px-2 py-0.5 rounded mt-2 inline-block">{{ beData.roce?.rag }}</span>
            </div>
            <div class="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border">
              <p class="text-sm text-gray-500 dark:text-gray-400">IRR</p>
              <p class="text-2xl font-bold text-gray-900 dark:text-white mt-1">{{ beData.irr?.irr?.toFixed(2) || 'N/A' }}%</p>
              <p class="text-xs text-gray-500 mt-1">Monthly cash flows</p>
            </div>
            <div class="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border">
              <p class="text-sm text-gray-500 dark:text-gray-400">Capital Employed</p>
              <p class="text-2xl font-bold text-gray-900 dark:text-white mt-1">{{ formatCurrency(beData.roce?.capital_employed) }}</p>
              <p class="text-xs text-gray-500 mt-1">EBIT: {{ formatCurrency(beData.roce?.ebit) }}</p>
            </div>
          </div>
          <div v-else class="text-center py-12 text-gray-500">No capital efficiency data available</div>
        </div>
      </div>
    </div>

    <!-- Floating Chat Button -->
    <DashboardChatButton 
      dashboard-type="Financial"
      :dashboard-context="chatContext"
      @navigate-dashboard="handleChatNavigation"
    />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'StrategicFinanceIntelligence' })
import { ref, onMounted, computed, markRaw, watch, provide } from 'vue'
import { useRouter } from 'vue-router'
import { createResource } from 'frappe-ui'
import {
  RefreshCw,
  Download,
  AlertTriangle,
  LayoutDashboard,
  Banknote,
  CalendarDays,
  Building2,
  Repeat,
  TrendingUp,
  GitBranch,
  Calendar,
  PiggyBank,
  Loader2,
  Scale,
  Users,
  Gauge
} from 'lucide-vue-next'
import DashboardChatButton from '../components/DashboardChatButton.vue'

// Tab Components
import ExecutiveSummaryTab from '../components/strategic-finance/ExecutiveSummaryTab.vue'
import CashForecastingTab from '../components/strategic-finance/CashForecastingTab.vue'
import ThirteenWeekCashFlowTab from '../components/strategic-finance/ThirteenWeekCashFlowTab.vue'
import CapitalPlanningTab from '../components/strategic-finance/CapitalPlanningTab.vue'
import WorkingCapitalTab from '../components/strategic-finance/WorkingCapitalTab.vue'
import FinancialRatiosTab from '../components/strategic-finance/FinancialRatiosTab.vue'
import ScenarioAnalysisTab from '../components/strategic-finance/ScenarioAnalysisTab.vue'
import PeriodComparisonTab from '../components/strategic-finance/PeriodComparisonTab.vue'
import BudgetVarianceTab from '../components/strategic-finance/BudgetVarianceTab.vue'

const router = useRouter()

// State
const activeTab = ref('executive')
const isLoading = ref(false)
const error = ref<string | null>(null)
const data = ref<any>(null)
const lastUpdated = ref<string | null>(null)

// Break-even state
const beData = ref<any>(null)
const beLoading = ref(false)
const beError = ref<string | null>(null)

// Tab Configuration
const tabs = [
  { id: 'executive', label: 'Executive Summary', icon: markRaw(LayoutDashboard) },
  { id: 'cash', label: 'Cash Forecasting', icon: markRaw(Banknote) },
  { id: 'cashflow13', label: '13-Week Cash Flow', icon: markRaw(CalendarDays) },
  { id: 'capital', label: 'Capital Planning', icon: markRaw(Building2) },
  { id: 'working', label: 'Working Capital', icon: markRaw(Repeat) },
  { id: 'ratios', label: 'Financial Ratios', icon: markRaw(TrendingUp) },
  { id: 'scenarios', label: 'Scenario Analysis', icon: markRaw(GitBranch) },
  { id: 'comparison', label: 'Period Comparison', icon: markRaw(Calendar) },
  { id: 'budget', label: 'Budget', icon: markRaw(PiggyBank) },
  { id: 'beOverview', label: 'Break-Even Overview', icon: markRaw(Scale) },
  { id: 'beEmployee', label: 'Employeewise BE', icon: markRaw(Users) },
  { id: 'beCapital', label: 'Capital Efficiency', icon: markRaw(Gauge) }
]

// Computed summary data from API response
const summaryData = computed(() => {
  if (!data.value) return {}
  const exec = data.value.executive_summary || {}
  const wc = data.value.working_capital || {}
  const ratios = data.value.ratio_trends?.current_ratios || {}
  const kpis = exec.kpis || []
  
  // Extract KPIs by label (matching backend labels)
  const revenueKpi = kpis.find((k: any) => k.label === 'Total Revenue') || {}
  const profitKpi = kpis.find((k: any) => k.label === 'Net Profit') || {}
  const grossMarginKpi = kpis.find((k: any) => k.label === 'Gross Margin') || {}
  const revenueGrowthKpi = kpis.find((k: any) => k.label === 'Revenue Growth') || {}
  const cashKpi = kpis.find((k: any) => k.label === 'Cash Position') || {}
  
  return {
    // Total Revenue - from KPI or direct field
    totalRevenue: revenueKpi.value || exec.ytd_revenue || 0,
    revenueGrowth: revenueKpi.trend || exec.revenue_growth_yoy || 0,
    // Net Profit - from KPI or direct field  
    netProfit: profitKpi.value || exec.ytd_net_income || 0,
    profitMargin: exec.net_margin || ratios.net_margin || 0,
    // Gross Margin - from KPI or direct field
    grossMargin: grossMarginKpi.value || exec.gross_margin || ratios.gross_margin || 0,
    // Cash Position - from KPI or direct field
    cashPosition: cashKpi.value || exec.cash_balance || wc.cash || 0,
    cashRunway: exec.cash_runway_months ? Math.round(exec.cash_runway_months * 30) : (data.value.cash_forecast?.runway_days || 0),
    // Working Capital metrics
    workingCapital: wc.working_capital || 0,
    currentRatio: wc.current_ratio || 0,
    dso: wc.dso || 0
  }
})

// API Resource
const strategicFinanceResource = createResource({
  url: 'insights.api.ml.strategic_finance_intelligence',
  auto: false,
  onSuccess(response: any) {
    if (response && response.status === 'success') {
      data.value = response
      lastUpdated.value = response.generated_at || new Date().toISOString()
      error.value = null
    } else {
      error.value = response?.message || 'Failed to load data'
    }
    isLoading.value = false
  },
  onError(err: any) {
    console.error('Strategic Finance Intelligence error:', err)
    error.value = 'An error occurred while loading data'
    isLoading.value = false
  }
})

// Functions
const fetchData = (refresh = false) => {
  isLoading.value = true
  error.value = null
  strategicFinanceResource.submit({ refresh })
}

const refreshData = () => {
  fetchData(true)
}

const formatDateTime = (dateStr: string) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('en-KE', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const currency = computed(() => data.value?.base_currency || 'KES')
provide('currency', currency)

const formatCurrency = (value: number) => {
  if (value === null || value === undefined) return `${currency.value} 0`
  if (value >= 1000000) return `${currency.value} ${(value / 1000000).toFixed(1)}M`
  if (value >= 1000) return `${currency.value} ${(value / 1000).toFixed(0)}K`
  return `${currency.value} ${value.toFixed(0)}`
}

// Chat context for AI assistant
const chatContext = computed(() => ({
  dashboard: 'Strategic Finance Intelligence',
  company: data.value?.company || '',
  currency: data.value?.base_currency || 'KES',
  fiscalYear: data.value?.fiscal_year || {},
  executiveSummary: data.value?.executive_summary || {},
  cashForecast: data.value?.cash_forecast || {},
  workingCapital: data.value?.working_capital || {},
  expenseBreakdown: data.value?.expense_breakdown || []
}))

const exportData = () => {
  if (!data.value) return
  
  const exportContent = JSON.stringify(data.value, null, 2)
  const blob = new Blob([exportContent], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `strategic-finance-intelligence-${new Date().toISOString().split('T')[0]}.json`
  a.click()
  URL.revokeObjectURL(url)
}

const handleChatNavigation = (path: string) => {
  router.push(path)
}

// Break-even helpers
const getRagClass = (rag: string) => {
  if (rag === 'green') return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
  if (rag === 'amber') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
  return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
}

const getRagDotClass = (rag: string) => {
  if (rag === 'green') return 'bg-green-500'
  if (rag === 'amber') return 'bg-amber-500'
  return 'bg-red-500'
}

// Break-even API Resources
const beSummaryResource = createResource({
  url: 'insights.api.ml.breakeven.breakeven_summary',
  auto: false,
  onSuccess(response: any) {
    if (response && response.status === 'success') {
      beData.value = response.data
      beError.value = null
    } else {
      beError.value = response?.message || 'Failed to load break-even data'
    }
    beLoading.value = false
  },
  onError(err: any) {
    console.error('Break-even summary error:', err)
    beError.value = 'An error occurred while loading break-even data'
    beLoading.value = false
  }
})

const beEmployeeResource = createResource({
  url: 'insights.api.ml.breakeven.employee_breakeven',
  auto: false,
  onSuccess(response: any) {
    if (response && response.status === 'success' && beData.value) {
      beData.value.employee_breakeven = response.data
    }
  },
  onError(err: any) {
    console.error('Employee BE error:', err)
  }
})

const beCapitalResource = createResource({
  url: 'insights.api.ml.breakeven.capital_efficiency',
  auto: false,
  onSuccess(response: any) {
    if (response && response.status === 'success' && beData.value) {
      beData.value.roce = response.data.roce
      beData.value.irr = response.data.irr
    }
  },
  onError(err: any) {
    console.error('Capital efficiency error:', err)
  }
})

const fetchBreakEvenData = () => {
  beLoading.value = true
  beError.value = null
  beSummaryResource.submit({})
}

// Watch tab changes to lazy-load break-even data
watch(activeTab, (tab) => {
  if (tab.startsWith('be') && !beData.value) {
    fetchBreakEvenData()
  }
})

// Lifecycle
onMounted(() => {
  fetchData()
})
</script>
