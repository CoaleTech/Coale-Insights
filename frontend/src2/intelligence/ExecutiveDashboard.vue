<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <header class="bg-surface-white border-b border-outline-gray-1 px-6 py-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-ink-gray-9">CEO Executive Dashboard</h1>
        <p v-if="lastUpdated" class="text-sm text-ink-gray-6 mt-1">
          Updated: {{ formatDateTime(lastUpdated) }} · {{ selectedPeriod }}
        </p>
        <p v-else class="text-sm text-ink-gray-6 mt-1">{{ selectedPeriod }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2 sm:gap-3">
        <!-- Period Selector -->
        <Select
          v-model="selectedPeriod"
          :options="periodOptions"
          @change="refreshData"
        />

        <Button
          :loading="isLoading"
          variant="solid"
          theme="gray"
          @click="refreshData"
        >
          <RefreshCw class="w-4 h-4 mr-2" />
          Refresh
        </Button>
        <Button
          variant="subtle"
          :disabled="!data"
          @click="exportData"
        >
          <Download class="w-4 h-4 mr-2" />
          Export
        </Button>
      </div>
    </header>

    <!-- Main Content -->
    <IntelligenceDashboardShell
      :loading="isLoading"
      :error="error"
      :has-data="!!data"
      subject="executive data"
      @retry="refreshData"
    >
      <!-- Business Health Score -->
      <div class="p-6">
        <div class="bg-surface-white rounded-lg shadow-sm border border-outline-gray-1 overflow-hidden">
          <div class="px-6 py-4 border-b border-outline-gray-1 bg-surface-gray-1">
            <div class="flex items-center justify-between">
              <h2 class="text-lg font-semibold text-ink-gray-9">Business Health Score</h2>
              <div class="flex items-center gap-3">
                <Badge
                  v-bind="severityBadge(scoreSeverity(businessHealth.overall_score, { good: 80, warn: 60 }))"
                  :aria-label="severityAria('Health', scoreSeverity(businessHealth.overall_score, { good: 80, warn: 60 }), businessHealth.overall_score)"
                  size="sm"
                />
                <span class="text-2xl font-bold text-ink-gray-9">{{ businessHealth.overall_score || 0 }}%</span>
              </div>
            </div>
          </div>
          <div class="p-6">
            <!-- AI Narrative -->
            <div v-if="data.narrative" class="mb-6 p-4 bg-surface-gray-1 rounded-lg border border-outline-gray-1">
              <div class="flex items-start gap-3">
                <Brain class="w-5 h-5 text-ink-gray-5 mt-0.5" />
                <div>
                  <h3 class="text-sm font-medium text-ink-gray-9">AI Executive Summary</h3>
                  <p class="text-sm text-ink-gray-7 mt-1">{{ data.narrative }}</p>
                </div>
              </div>
            </div>

            <!-- Department Health Breakdown -->
            <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
              <div
                v-for="(score, department) in businessHealth.department_scores"
                :key="department"
                class="text-center cursor-pointer hover:bg-surface-gray-1 rounded-lg p-2 motion-reduce:transition-none transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
                :tabindex="departmentRoutes[department] ? 0 : undefined"
                :role="departmentRoutes[department] ? 'button' : undefined"
                :aria-label="departmentRoutes[department] ? `Go to ${department} dashboard` : undefined"
                @click="departmentRoutes[department] && router.push(departmentRoutes[department])"
                @keydown.enter="departmentRoutes[department] && router.push(departmentRoutes[department])"
              >
                <div class="text-sm font-medium text-ink-gray-6 capitalize">{{ department }}</div>
                <div class="mt-1">
                  <div class="text-lg font-bold text-ink-gray-9">{{ Math.round(score) }}%</div>
                  <div
                    class="w-full h-2 bg-surface-gray-3 rounded-full mt-1"
                    :aria-label="severityAria(String(department), scoreSeverity(score, { good: 80, warn: 60 }), score)"
                    role="img"
                  >
                    <div
                      :class="[severityFill(scoreSeverity(score, { good: 80, warn: 60 })), 'h-full rounded-full motion-reduce:transition-none transition-all']"
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
        <div class="bg-surface-white rounded-lg shadow-sm border border-outline-gray-1">
          <div class="px-6 py-4 border-b border-outline-gray-1 bg-surface-gray-1">
            <h2 class="text-lg font-semibold text-ink-gray-9 flex items-center gap-2">
              <AlertTriangle class="w-5 h-5 text-ink-gray-5" />
              Critical Alerts
            </h2>
          </div>
          <div class="p-6">
            <div class="space-y-3">
              <div
                v-for="alert in alerts.slice(0, 5)"
                :key="alert.message"
                class="p-4 rounded-lg border border-outline-gray-1 bg-surface-white"
              >
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-3">
                    <span class="font-medium text-ink-gray-9">{{ alert.department }}</span>
                    <Badge
                      v-bind="severityBadge(ragSeverity(alert.rag_status))"
                      size="sm"
                    />
                  </div>
                </div>
                <p class="text-sm text-ink-gray-7 mt-2">{{ alert.message }}</p>
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
              class="text-lg font-semibold text-ink-gray-9 flex items-center gap-2 cursor-pointer hover:text-ink-gray-7 motion-reduce:transition-none transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 rounded"
              tabindex="0"
              role="button"
              :aria-label="`Navigate to ${dept.label} dashboard`"
              @click="router.push(departmentRoutes[dept.key])"
              @keydown.enter="router.push(departmentRoutes[dept.key])"
            >
              <component :is="dept.icon" class="w-5 h-5 text-ink-gray-5" />
              {{ dept.label }}
            </h3>
            <template
              v-for="(kpi, key, kpiIndex) in kpis[dept.key]"
              :key="dept.key + key"
            >
              <div
                v-if="kpi && typeof kpi === 'object' && !kpi.error"
                class="bg-surface-white p-4 rounded-lg shadow-sm border border-outline-gray-1"
                :class="getExecMetric(kpi.label) ? 'cursor-pointer hover:ring-2 hover:ring-outline-gray-3 motion-reduce:transition-none transition-shadow' : ''"
                :tabindex="getExecMetric(kpi.label) ? 0 : undefined"
                :role="getExecMetric(kpi.label) ? 'button' : undefined"
                :aria-label="getExecMetric(kpi.label) ? `Drill down: ${kpi.label}` : undefined"
                @click="getExecMetric(kpi.label) && drillDown.open(EXEC_ENDPOINT, kpi.label, { metric: getExecMetric(kpi.label) })"
                @keydown.enter="getExecMetric(kpi.label) && drillDown.open(EXEC_ENDPOINT, kpi.label, { metric: getExecMetric(kpi.label) })"
              >
                <div class="flex items-center justify-between mb-2">
                  <div class="text-sm font-medium text-ink-gray-6">{{ kpi.label }}</div>
                  <Badge
                    v-bind="severityBadge(ragSeverity(kpi.rag_status))"
                    size="sm"
                    :aria-label="severityAria(kpi.label, ragSeverity(kpi.rag_status))"
                  />
                </div>
                <div class="text-2xl font-bold text-ink-gray-9">
                  {{ formatKpiValue(kpi.value, kpi.format) }}
                </div>
                <div
                  v-if="getKpiVariance(kpi) !== null"
                  :class="deltaInk(getKpiVariance(kpi), { higherIsBetter: !dept.reverseVariance })"
                  class="text-sm mt-1"
                >
                  {{ deltaGlyph(getKpiVariance(kpi)) }} {{ Math.abs(getKpiVariance(kpi)).toFixed(1) }}% vs target
                </div>
                <div v-if="sparklineData(dept, kpiIndex).length > 1" class="mt-2">
                  <svg class="w-full h-8 text-ink-gray-5" viewBox="0 0 100 20" aria-hidden="true">
                    <path
                      :d="generateSparkline(sparklineData(dept, kpiIndex))"
                      fill="none"
                      stroke="currentColor"
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
        <div class="bg-surface-white rounded-lg shadow-sm border border-outline-gray-1">
          <div class="px-6 py-4 border-b border-outline-gray-1 bg-surface-gray-1">
            <h2 class="text-lg font-semibold text-ink-gray-9">Quick Actions</h2>
          </div>
          <div class="p-6">
            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
              <Button
                variant="subtle"
                class="flex items-center gap-3 p-4 text-left h-auto"
                @click="generateStrategicReport"
              >
                <FileText class="w-5 h-5 text-ink-gray-5" />
                <div>
                  <div class="text-sm font-medium text-ink-gray-9">Strategic Report</div>
                  <div class="text-xs text-ink-gray-6">Generate board-ready summary</div>
                </div>
              </Button>

              <Button
                variant="subtle"
                class="flex items-center gap-3 p-4 text-left h-auto"
                @click="exportExecutiveData"
              >
                <Download class="w-5 h-5 text-ink-gray-5" />
                <div>
                  <div class="text-sm font-medium text-ink-gray-9">Export Data</div>
                  <div class="text-xs text-ink-gray-6">Download PDF/Excel report</div>
                </div>
              </Button>

              <Button
                variant="subtle"
                class="flex items-center gap-3 p-4 text-left h-auto"
                @click="openAIChat"
              >
                <Brain class="w-5 h-5 text-ink-gray-5" />
                <div>
                  <div class="text-sm font-medium text-ink-gray-9">Ask AI</div>
                  <div class="text-xs text-ink-gray-6">Get insights &amp; recommendations</div>
                </div>
              </Button>

              <Button
                variant="subtle"
                class="flex items-center gap-3 p-4 text-left h-auto"
                @click="scheduleReport"
              >
                <Calendar class="w-5 h-5 text-ink-gray-5" />
                <div>
                  <div class="text-sm font-medium text-ink-gray-9">Schedule Reports</div>
                  <div class="text-xs text-ink-gray-6">Setup automated delivery</div>
                </div>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </IntelligenceDashboardShell>

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
import { Button, Badge, Select, LoadingIndicator } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { useRouter } from 'vue-router'
import { useDrillDown } from './composables/useDrillDown'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'
import IntelligenceDashboardShell from './components/IntelligenceDashboardShell.vue'
import {
  severityBadge, severityFill, severityAria,
  scoreSeverity, ragSeverity, deltaInk, deltaGlyph,
} from '../utils/status'
import { formatMoney } from '../utils/format'

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
const companyCurrency = ref(null)

const periodOptions = [
  { label: 'Month to Date', value: 'MTD' },
  { label: 'Quarter to Date', value: 'QTD' },
  { label: 'Year to Date', value: 'YTD' },
  { label: 'Trailing 12 Months', value: 'TTM' },
]

const businessHealth = computed(() => data.value?.business_health_score || {})
const alerts = computed(() => data.value?.alerts || [])
const kpis = computed(() => data.value?.kpis || {})
const trends = computed(() => data.value?.trends || {})

/**
 * Department columns with neutral annotation icon color.
 *
 * Thresholds stay explicit at 80/60 rather than adopting
 * `HEALTH_SCORE_THRESHOLDS`: `business_health_score` comes from
 * `ml/executive_intelligence`, and unlike the strategic-finance and customer
 * health scores its server-side band vocabulary has not been verified. Moving
 * it to 60/40 unverified would shift the green/amber line for the C-suite view
 * on no evidence. Needs a product decision, then this becomes the constant.
 */
const departmentColumns = computed(() => [
  { key: 'financial', label: 'Financial', icon: DollarSign, reverseVariance: false },
  { key: 'sales', label: 'Sales', icon: TrendingUp, reverseVariance: false },
  { key: 'customer', label: 'Customer', icon: Users, reverseVariance: false },
  { key: 'operations', label: 'Operations', icon: Settings, reverseVariance: false },
  { key: 'risk', label: 'Risk', icon: Shield, reverseVariance: true },
  { key: 'hr', label: 'HR', icon: UserCog, reverseVariance: false },
  { key: 'manufacturing', label: 'Manufacturing', icon: Factory, reverseVariance: false },
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
      return formatMoney(value, companyCurrency.value)
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

function getKpiVariance(kpi) {
  return kpi.variance_pct ?? kpi.variance_points ?? kpi.variance_ratio ?? kpi.variance_weeks ?? kpi.variance_turns ?? null
}

function sparklineData(dept, kpiIndex) {
  const key = (departmentTrendKeys[dept.key] || [])[kpiIndex] || ''
  return getTrendData(key)
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

function getTrendData(metric) {
  return trends.value[metric] || []
}

function generateSparkline(points) {
  if (!points || points.length === 0) return ''
  // The domain includes zero on purpose. A min-to-max domain rescales every
  // series to fill the full 20-unit band, so a 98->100 wobble rendered exactly
  // as steep as a 90->45 collapse and a CEO reading these calibrated severity
  // from noise. Including zero means height encodes magnitude, not rank.
  //
  // `Math.min(0, ...)` rather than 0 outright so negative series (sales_growth,
  // churn deltas) still plot, with the zero line inside the band.
  const lo = Math.min(0, ...points)
  const hi = Math.max(0, ...points)
  const range = hi - lo
  return points.map((value, index) => {
    // Guard length 1: `0 / 0` produced `NaN` and emitted an unrenderable path.
    const x = points.length === 1 ? 0 : (index / (points.length - 1)) * 100
    const y = range > 0 ? ((hi - value) / range) * 20 : 20
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
