<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <header class="bg-white border-b px-6 py-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">CEO Executive Dashboard</h1>
        <p class="text-sm text-gray-500 mt-1">
          Unified view of business performance across all departments with AI insights
        </p>
      </div>
      <div class="flex items-center gap-3">
        <!-- Period Selector -->
        <select
          v-model="selectedPeriod"
          @change="refreshData"
          class="text-sm border border-gray-300 rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="MTD">Month to Date</option>
          <option value="QTD">Quarter to Date</option>
          <option value="YTD" selected>Year to Date</option>
          <option value="TTM">Trailing 12 Months</option>
        </select>

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
        <p class="mt-4 text-gray-600">Loading executive dashboard...</p>
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
      <!-- Business Health Score -->
      <div class="p-6">
        <div class="bg-white rounded-lg shadow-sm border overflow-hidden">
          <div class="px-6 py-4 border-b bg-gray-50">
            <div class="flex items-center justify-between">
              <h2 class="text-lg font-semibold text-gray-900">Business Health Score</h2>
              <div class="flex items-center gap-2">
                <div :class="getHealthScoreColor(businessHealth.overall_score)" class="w-3 h-3 rounded-full"></div>
                <span class="text-2xl font-bold text-gray-900">{{ businessHealth.overall_score || 0 }}%</span>
              </div>
            </div>
          </div>
          <div class="p-6">
            <!-- AI Narrative -->
            <div v-if="data.narrative" class="mb-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
              <div class="flex items-start gap-3">
                <Brain class="w-5 h-5 text-blue-600 mt-0.5" />
                <div>
                  <h3 class="text-sm font-medium text-blue-900">AI Executive Summary</h3>
                  <p class="text-sm text-blue-800 mt-1">{{ data.narrative }}</p>
                </div>
              </div>
            </div>

            <!-- Department Health Breakdown -->
            <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
              <div
                v-for="(score, department) in businessHealth.department_scores"
                :key="department"
                class="text-center"
              >
                <div class="text-sm font-medium text-gray-500 capitalize">{{ department }}</div>
                <div class="mt-1">
                  <div :class="getHealthScoreColor(score)" class="text-lg font-bold">{{ score }}%</div>
                  <div :class="'w-full h-2 bg-gray-200 rounded-full mt-1'">
                    <div
                      :class="getHealthScoreColor(score) + ' h-full rounded-full transition-all'"
                      :style="`width: ${score}%`"
                    ></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Critical Alerts -->
      <div v-if="alerts && alerts.length > 0" class="px-6 mb-6">
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="px-6 py-4 border-b bg-gray-50">
            <h2 class="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <AlertTriangle class="w-5 h-5 text-red-500" />
              Critical Alerts
            </h2>
          </div>
          <div class="p-6">
            <div class="space-y-3">
              <div
                v-for="alert in alerts.slice(0, 5)"
                :key="alert.message"
                :class="getAlertClass(alert.priority)"
                class="p-4 rounded-lg border-l-4"
              >
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-3">
                    <div :class="getAlertIconColor(alert.priority)" class="w-2 h-2 rounded-full"></div>
                    <span class="font-medium text-gray-900">{{ alert.department }}</span>
                    <span :class="getAlertPriorityClass(alert.priority)" class="px-2 py-1 text-xs font-medium rounded-full">
                      {{ alert.priority.toUpperCase() }}
                    </span>
                  </div>
                  <div :class="'w-3 h-3 rounded-full ' + getRagColor(alert.rag_status)"></div>
                </div>
                <p class="text-sm text-gray-700 mt-2">{{ alert.message }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Executive KPIs Grid -->
      <div class="px-6 mb-6">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-6">
          <!-- Financial KPIs -->
          <div v-if="kpis.financial && !kpis.financial.error" class="space-y-4">
            <h3 class="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <DollarSign class="w-5 h-5 text-green-600" />
              Financial
            </h3>
            <template
              v-for="(kpi, key) in kpis.financial"
              :key="'financial' + key"
            >
            <div
              v-if="kpi && typeof kpi === 'object' && !kpi.error"
              class="bg-white p-4 rounded-lg shadow-sm border"
            >
              <div class="flex items-center justify-between mb-2">
                <div class="text-sm font-medium text-gray-500">{{ kpi.label }}</div>
                <div :class="'w-3 h-3 rounded-full ' + getRagColor(kpi.rag_status)"></div>
              </div>
              <div class="text-2xl font-bold text-gray-900">
                {{ formatKpiValue(kpi.value, kpi.format) }}
              </div>
              <div v-if="kpi.variance_pct !== undefined" :class="getVarianceColor(kpi.variance_pct)" class="text-sm mt-1">
                {{ kpi.variance_pct >= 0 ? '&#8593;' : '&#8595;' }} {{ Math.abs(kpi.variance_pct).toFixed(1) }}% vs target
              </div>
              <div v-if="getTrendData('revenue').length > 1" class="mt-2">
                <svg class="w-full h-8" viewBox="0 0 100 20">
                  <path
                    :d="generateSparkline(getTrendData('revenue'))"
                    fill="none"
                    :stroke="getVarianceColor(kpi.variance_pct).includes('green') ? '#10b981' : '#ef4444'"
                    stroke-width="1"
                  />
                </svg>
              </div>
            </div>
            </template>
          </div>

          <!-- Sales KPIs -->
          <div v-if="kpis.sales && !kpis.sales.error" class="space-y-4">
            <h3 class="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <TrendingUp class="w-5 h-5 text-blue-600" />
              Sales
            </h3>
            <template
              v-for="(kpi, key) in kpis.sales"
              :key="'sales' + key"
            >
            <div
              v-if="kpi && typeof kpi === 'object' && !kpi.error"
              class="bg-white p-4 rounded-lg shadow-sm border"
            >
              <div class="flex items-center justify-between mb-2">
                <div class="text-sm font-medium text-gray-500">{{ kpi.label }}</div>
                <div :class="'w-3 h-3 rounded-full ' + getRagColor(kpi.rag_status)"></div>
              </div>
              <div class="text-2xl font-bold text-gray-900">
                {{ formatKpiValue(kpi.value, kpi.format) }}
              </div>
              <div v-if="kpi.variance_pct !== undefined" :class="getVarianceColor(kpi.variance_pct)" class="text-sm mt-1">
                {{ kpi.variance_pct >= 0 ? '&#8593;' : '&#8595;' }} {{ Math.abs(kpi.variance_pct).toFixed(1) }}% vs target
              </div>
              <div v-if="getTrendData('sales_growth').length > 1" class="mt-2">
                <svg class="w-full h-8" viewBox="0 0 100 20">
                  <path
                    :d="generateSparkline(getTrendData('sales_growth'))"
                    fill="none"
                    :stroke="getVarianceColor(kpi.variance_pct).includes('green') ? '#10b981' : '#ef4444'"
                    stroke-width="1"
                  />
                </svg>
              </div>
            </div>
            </template>
          </div>

          <!-- Customer KPIs -->
          <div v-if="kpis.customer && !kpis.customer.error" class="space-y-4">
            <h3 class="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <Users class="w-5 h-5 text-purple-600" />
              Customer
            </h3>
            <template
              v-for="(kpi, key) in kpis.customer"
              :key="'customer' + key"
            >
            <div
              v-if="kpi && typeof kpi === 'object' && !kpi.error"
              class="bg-white p-4 rounded-lg shadow-sm border"
            >
              <div class="flex items-center justify-between mb-2">
                <div class="text-sm font-medium text-gray-500">{{ kpi.label }}</div>
                <div :class="'w-3 h-3 rounded-full ' + getRagColor(kpi.rag_status)"></div>
              </div>
              <div class="text-2xl font-bold text-gray-900">
                {{ formatKpiValue(kpi.value, kpi.format) }}
              </div>
              <div v-if="kpi.variance_pct !== undefined" :class="getVarianceColor(kpi.variance_pct)" class="text-sm mt-1">
                {{ kpi.variance_pct >= 0 ? '&#8595;' : '&#8593;' }} {{ Math.abs(kpi.variance_pct).toFixed(1) }}% vs target
              </div>
              <div v-if="getTrendData('churn_rate').length > 1" class="mt-2">
                <svg class="w-full h-8" viewBox="0 0 100 20">
                  <path
                    :d="generateSparkline(getTrendData('churn_rate'))"
                    fill="none"
                    :stroke="getVarianceColor(kpi.variance_pct).includes('green') ? '#10b981' : '#ef4444'"
                    stroke-width="1"
                  />
                </svg>
              </div>
            </div>
            </template>
          </div>

          <!-- Operations KPIs -->
          <div v-if="kpis.operations && !kpis.operations.error" class="space-y-4">
            <h3 class="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <Settings class="w-5 h-5 text-orange-600" />
              Operations
            </h3>
            <template
              v-for="(kpi, key) in kpis.operations"
              :key="'operations' + key"
            >
            <div
              v-if="kpi && typeof kpi === 'object' && !kpi.error"
              class="bg-white p-4 rounded-lg shadow-sm border"
            >
              <div class="flex items-center justify-between mb-2">
                <div class="text-sm font-medium text-gray-500">{{ kpi.label }}</div>
                <div :class="'w-3 h-3 rounded-full ' + getRagColor(kpi.rag_status)"></div>
              </div>
              <div class="text-2xl font-bold text-gray-900">
                {{ formatKpiValue(kpi.value, kpi.format) }}
              </div>
              <div v-if="kpi.variance_pct !== undefined" :class="getVarianceColor(kpi.variance_pct)" class="text-sm mt-1">
                {{ kpi.variance_pct >= 0 ? '&#8595;' : '&#8593;' }} {{ Math.abs(kpi.variance_pct).toFixed(1) }}% vs target
              </div>
              <div v-if="getTrendData('inventory_turns').length > 1" class="mt-2">
                <svg class="w-full h-8" viewBox="0 0 100 20">
                  <path
                    :d="generateSparkline(getTrendData('inventory_turns'))"
                    fill="none"
                    :stroke="getVarianceColor(kpi.variance_pct).includes('green') ? '#10b981' : '#ef4444'"
                    stroke-width="1"
                  />
                </svg>
              </div>
            </div>
            </template>
          </div>

          <!-- Risk KPIs -->
          <div v-if="kpis.risk && !kpis.risk.error" class="space-y-4">
            <h3 class="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <Shield class="w-5 h-5 text-red-600" />
              Risk
            </h3>
            <template
              v-for="(kpi, key) in kpis.risk"
              :key="'risk' + key"
            >
            <div
              v-if="kpi && typeof kpi === 'object' && !kpi.error"
              class="bg-white p-4 rounded-lg shadow-sm border"
            >
              <div class="flex items-center justify-between mb-2">
                <div class="text-sm font-medium text-gray-500">{{ kpi.label }}</div>
                <div :class="'w-3 h-3 rounded-full ' + getRagColor(kpi.rag_status)"></div>
              </div>
              <div class="text-2xl font-bold text-gray-900">
                {{ formatKpiValue(kpi.value, kpi.format) }}
              </div>
              <div v-if="kpi.variance_pct !== undefined" :class="getVarianceColor(kpi.variance_pct, true)" class="text-sm mt-1">
                {{ kpi.variance_pct >= 0 ? '&#8593;' : '&#8595;' }} {{ Math.abs(kpi.variance_pct).toFixed(1) }}% vs target
              </div>
              <div v-if="getTrendData('credit_risk').length > 1" class="mt-2">
                <svg class="w-full h-8" viewBox="0 0 100 20">
                  <path
                    :d="generateSparkline(getTrendData('credit_risk'))"
                    fill="none"
                    :stroke="getVarianceColor(kpi.variance_pct, true).includes('green') ? '#10b981' : '#ef4444'"
                    stroke-width="1"
                  />
                </svg>
              </div>
            </div>
            </template>
          </div>

          <!-- HR KPIs -->
          <div v-if="kpis.hr && !kpis.hr.error" class="space-y-4">
            <h3 class="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <UserCog class="w-5 h-5 text-indigo-600" />
              HR
            </h3>
            <template
              v-for="(kpi, key) in kpis.hr"
              :key="'hr' + key"
            >
            <div
              v-if="kpi && typeof kpi === 'object' && !kpi.error"
              class="bg-white p-4 rounded-lg shadow-sm border"
            >
              <div class="flex items-center justify-between mb-2">
                <div class="text-sm font-medium text-gray-500">{{ kpi.label }}</div>
                <div :class="'w-3 h-3 rounded-full ' + getRagColor(kpi.rag_status)"></div>
              </div>
              <div class="text-2xl font-bold text-gray-900">
                {{ formatKpiValue(kpi.value, kpi.format) }}
              </div>
              <div v-if="kpi.variance_pct !== undefined" :class="getVarianceColor(kpi.variance_pct)" class="text-sm mt-1">
                {{ kpi.variance_pct >= 0 ? '&#8593;' : '&#8595;' }} {{ Math.abs(kpi.variance_pct).toFixed(1) }}% vs target
              </div>
              <div v-if="getTrendData('headcount').length > 1" class="mt-2">
                <svg class="w-full h-8" viewBox="0 0 100 20">
                  <path
                    :d="generateSparkline(getTrendData('headcount'))"
                    fill="none"
                    :stroke="getVarianceColor(kpi.variance_pct).includes('green') ? '#10b981' : '#ef4444'"
                    stroke-width="1"
                  />
                </svg>
              </div>
            </div>
            </template>
          </div>

        </div>
      </div>

      <!-- Quick Actions -->
      <div class="px-6 pb-6">
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="px-6 py-4 border-b bg-gray-50">
            <h2 class="text-lg font-semibold text-gray-900">Quick Actions</h2>
          </div>
          <div class="p-6">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
              <button
                @click="generateStrategicReport"
                class="flex items-center gap-3 p-4 text-left border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <FileText class="w-5 h-5 text-blue-600" />
                <div>
                  <div class="text-sm font-medium text-gray-900">Strategic Report</div>
                  <div class="text-xs text-gray-500">Generate board-ready summary</div>
                </div>
              </button>

              <button
                @click="exportExecutiveData"
                class="flex items-center gap-3 p-4 text-left border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <Download class="w-5 h-5 text-green-600" />
                <div>
                  <div class="text-sm font-medium text-gray-900">Export Data</div>
                  <div class="text-xs text-gray-500">Download PDF/Excel report</div>
                </div>
              </button>

              <button
                @click="openAIChat"
                class="flex items-center gap-3 p-4 text-left border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <Brain class="w-5 h-5 text-purple-600" />
                <div>
                  <div class="text-sm font-medium text-gray-900">Ask AI</div>
                  <div class="text-xs text-gray-500">Get insights & recommendations</div>
                </div>
              </button>

              <button
                @click="scheduleReport"
                class="flex items-center gap-3 p-4 text-left border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <Calendar class="w-5 h-5 text-orange-600" />
                <div>
                  <div class="text-sm font-medium text-gray-900">Schedule Reports</div>
                  <div class="text-xs text-gray-500">Setup automated delivery</div>
                </div>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  RefreshCw,
  Download,
  Loader2,
  AlertTriangle,
  Brain,
  DollarSign,
  TrendingUp,
  Users,
  Settings,
  Shield,
  FileText,
  Calendar,
  UserCog
} from 'lucide-vue-next'
import { apiCall } from '../helpers/api'
import { useRouter } from 'vue-router'

const router = useRouter()

const data = ref(null)
const isLoading = ref(false)
const error = ref(null)
const lastUpdated = ref(null)
const selectedPeriod = ref('YTD')
const companyCurrency = ref('KES')

const businessHealth = computed(() => data.value?.business_health_score || {})
const alerts = computed(() => data.value?.alerts || [])
const kpis = computed(() => data.value?.kpis || {})
const trends = computed(() => data.value?.trends || {})

onMounted(() => {
  loadData()
})

async function loadData() {
  isLoading.value = true
  error.value = null

  try {
    data.value = await apiCall('insights.api.ml.get_executive_summary', {
      period: selectedPeriod.value
    })
    lastUpdated.value = new Date()

    // Read currency from backend response
    if (data.value?.currency) {
      companyCurrency.value = data.value.currency
    }
  } catch (err) {
    console.error('Error loading executive data:', err)
    error.value = err.message || 'Failed to load data'
  } finally {
    isLoading.value = false
  }
}

function refreshData() {
  loadData()
}

function exportData() {
  const dataStr = JSON.stringify(data.value, null, 2)
  const dataUri = 'data:application/json;charset=utf-8,' + encodeURIComponent(dataStr)
  const exportFileDefaultName = `executive_dashboard_${selectedPeriod.value}_${new Date().toISOString().split('T')[0]}.json`
  const linkElement = document.createElement('a')
  linkElement.setAttribute('href', dataUri)
  linkElement.setAttribute('download', exportFileDefaultName)
  linkElement.click()
}

function formatDateTime(date) {
  if (!date) return ''
  return new Date(date).toLocaleDateString() + ' ' + new Date(date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function formatKpiValue(value, format) {
  if (value === null || value === undefined) return 'N/A'
  switch (format) {
    case 'currency':
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: companyCurrency.value, minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value)
    case 'percentage':
      return `${value.toFixed(1)}%`
    case 'decimal':
      return value.toFixed(1)
    case 'ratio':
      return `${value.toFixed(1)}:1`
    case 'risk_score':
      return `${Math.round(value)}/100`
    default:
      return value.toLocaleString()
  }
}

function getHealthScoreColor(score) {
  if (score >= 80) return 'text-green-600'
  if (score >= 60) return 'text-yellow-600'
  return 'text-red-600'
}

function getRagColor(status) {
  switch (status) {
    case 'green': return 'bg-green-500'
    case 'amber': return 'bg-yellow-500'
    case 'red': return 'bg-red-500'
    default: return 'bg-gray-400'
  }
}

function getVarianceColor(variance, reverse = false) {
  if (variance === null || variance === undefined) return 'text-gray-500'
  const isPositive = variance >= 0
  if (reverse) return isPositive ? 'text-red-600' : 'text-green-600'
  return isPositive ? 'text-green-600' : 'text-red-600'
}

function getAlertClass(priority) {
  switch (priority) {
    case 'critical': return 'bg-red-50 border-red-500'
    case 'high': return 'bg-orange-50 border-orange-500'
    case 'medium': return 'bg-yellow-50 border-yellow-500'
    default: return 'bg-blue-50 border-blue-500'
  }
}

function getAlertIconColor(priority) {
  switch (priority) {
    case 'critical': return 'bg-red-500'
    case 'high': return 'bg-orange-500'
    case 'medium': return 'bg-yellow-500'
    default: return 'bg-blue-500'
  }
}

function getAlertPriorityClass(priority) {
  switch (priority) {
    case 'critical': return 'bg-red-100 text-red-800'
    case 'high': return 'bg-orange-100 text-orange-800'
    case 'medium': return 'bg-yellow-100 text-yellow-800'
    default: return 'bg-blue-100 text-blue-800'
  }
}

function getTrendData(metric) {
  return trends.value[metric] || []
}

function generateSparkline(data) {
  if (!data || data.length === 0) return ''
  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min
  return data.map((value, index) => {
    const x = (index / (data.length - 1)) * 100
    const y = range > 0 ? ((max - value) / range) * 20 : 10
    return `${index === 0 ? 'M' : 'L'} ${x} ${y}`
  }).join(' ')
}

function generateStrategicReport() {
  router.push('/executive-reports')
}

function exportExecutiveData() {
  exportData()
}

function openAIChat() {
  router.push('/ai-insights?context=executive')
}

function scheduleReport() {
  router.push('/executive-reports')
}
</script>

<style scoped>
/* Add any custom styles here */
</style>
