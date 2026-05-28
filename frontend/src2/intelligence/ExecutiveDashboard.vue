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
                class="text-center cursor-pointer hover:bg-gray-50 rounded-lg p-2 transition-colors"
                @click="departmentRoutes[department] && router.push(departmentRoutes[department])"
              >
                <div class="text-sm font-medium text-gray-500 capitalize">{{ department }}</div>
                <div class="mt-1">
                  <div :class="getHealthScoreColor(score)" class="text-lg font-bold">{{ Math.round(score) }}%</div>
                  <div class="w-full h-2 bg-gray-200 rounded-full mt-1">
                    <div
                      :class="[getHealthScoreBgColor(score), 'h-full rounded-full transition-all']"
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
          <div
            v-for="dept in departmentColumns"
            :key="dept.key"
            v-show="kpis[dept.key] && !kpis[dept.key].error"
            class="space-y-4"
          >
            <h3
              class="text-lg font-semibold text-gray-900 flex items-center gap-2 cursor-pointer hover:text-blue-600 transition-colors"
              @click="router.push(departmentRoutes[dept.key])"
            >
              <component :is="dept.icon" :class="['w-5 h-5', dept.iconColor]" />
              {{ dept.label }}
            </h3>
            <template
              v-for="(kpi, key, kpiIndex) in kpis[dept.key]"
              :key="dept.key + key"
            >
              <div
                v-if="kpi && typeof kpi === 'object' && !kpi.error"
                :class="['bg-white p-4 rounded-lg shadow-sm border', getExecMetric(kpi.label) ? 'cursor-pointer hover:ring-2 hover:ring-blue-300 transition-shadow' : '']"
                @click="getExecMetric(kpi.label) && drillDown.open(EXEC_ENDPOINT, kpi.label, { metric: getExecMetric(kpi.label) })"
              >
                <div class="flex items-center justify-between mb-2">
                  <div class="text-sm font-medium text-gray-500">{{ kpi.label }}</div>
                  <div :class="'w-3 h-3 rounded-full ' + getRagColor(kpi.rag_status)"></div>
                </div>
                <div class="text-2xl font-bold text-gray-900">
                  {{ formatKpiValue(kpi.value, kpi.format) }}
                </div>
                <div v-if="getKpiVariance(kpi) !== null" :class="getVarianceColor(getKpiVariance(kpi), dept.reverseVariance)" class="text-sm mt-1">
                  {{ getKpiVariance(kpi) >= 0 ? '&#8593;' : '&#8595;' }} {{ Math.abs(getKpiVariance(kpi)).toFixed(1) }}% vs target
                </div>
                <div v-if="getTrendData((departmentTrendKeys[dept.key] || [])[kpiIndex] || '').length > 1" class="mt-2">
                  <svg class="w-full h-8" viewBox="0 0 100 20">
                    <path
                      :d="generateSparkline(getTrendData((departmentTrendKeys[dept.key] || [])[kpiIndex] || ''))"
                      fill="none"
                      :stroke="kpi.rag_status === 'green' ? '#10b981' : kpi.rag_status === 'amber' ? '#f59e0b' : '#ef4444'"
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

<script setup>
defineOptions({ name: 'ExecutiveDashboard' })
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
  UserCog,
  Factory
} from 'lucide-vue-next'
import { apiCall } from '../helpers/api'
import { useRouter } from 'vue-router'
import { useDrillDown } from './composables/useDrillDown'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'

const router = useRouter()

const EXEC_ENDPOINT = 'insights.api.ml.executive.get_executive_detail'
const drillDown = useDrillDown()

const EXEC_DRILLABLE_METRICS = {
  'revenue_invoices': (label) => /Revenue|Sales/i.test(label),
  'open_orders': (label) => /Open Orders|Sales Orders/i.test(label),
  'active_employees': (label) => /Employees|Headcount/i.test(label),
  'open_pos': (label) => /Purchase Orders|Open PO/i.test(label),
}

function getExecMetric(label) {
  for (const [metric, test] of Object.entries(EXEC_DRILLABLE_METRICS)) {
    if (test(label)) return metric
  }
  return null
}

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

const departmentColumns = computed(() => [
  { key: 'financial', label: 'Financial', icon: DollarSign, iconColor: 'text-green-600', reverseVariance: false },
  { key: 'sales', label: 'Sales', icon: TrendingUp, iconColor: 'text-blue-600', reverseVariance: false },
  { key: 'customer', label: 'Customer', icon: Users, iconColor: 'text-purple-600', reverseVariance: false },
  { key: 'operations', label: 'Operations', icon: Settings, iconColor: 'text-orange-600', reverseVariance: false },
  { key: 'risk', label: 'Risk', icon: Shield, iconColor: 'text-red-600', reverseVariance: true },
  { key: 'hr', label: 'HR', icon: UserCog, iconColor: 'text-indigo-600', reverseVariance: false },
  { key: 'manufacturing', label: 'Manufacturing', icon: Factory, iconColor: 'text-teal-600', reverseVariance: false },
])

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

function getHealthScoreBgColor(score) {
  if (score >= 80) return 'bg-green-500'
  if (score >= 60) return 'bg-yellow-500'
  return 'bg-red-500'
}

function getKpiVariance(kpi) {
  return kpi.variance_pct ?? kpi.variance_points ?? kpi.variance_ratio ?? kpi.variance_weeks ?? kpi.variance_turns ?? null
}

const departmentRoutes = {
  financial: '/financial-intelligence',
  sales: '/sales-intelligence',
  customer: '/customer-intelligence',
  operations: '/inventory-intelligence',
  risk: '/risk-intelligence',
  hr: '/hr-intelligence',
  manufacturing: '/manufacturing-intelligence',
}

const departmentTrendKeys = {
  financial: ['revenue', 'margin', 'revenue'],
  sales: ['sales_growth', 'sales_growth', 'sales_growth'],
  customer: ['churn_rate', 'churn_rate', 'churn_rate'],
  operations: ['inventory_turns', 'inventory_turns', 'inventory_turns'],
  risk: ['credit_risk', 'credit_risk', 'credit_risk'],
  hr: ['headcount', 'headcount', 'headcount'],
  manufacturing: ['oee', 'oee', 'oee'],
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
