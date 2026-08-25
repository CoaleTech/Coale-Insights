<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <header class="bg-surface-white border-b border-outline-gray-1 px-6 py-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-ink-gray-9">CEO Executive Dashboard</h1>
        <p class="text-sm text-ink-gray-6 mt-1">{{ selectedPeriod }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2 sm:gap-3">
        <!-- Period Selector -->
        <IntelligenceDateFilter v-model="selectedPeriod" :options="FISCAL_PERIOD_RANGES" />

        <Button
          :loading="refreshing"
          variant="solid"
          theme="gray"
          @click="reload"
        >
          <template #prefix><RefreshCw class="w-4 h-4" /></template>
          Refresh
        </Button>
        <Button
          variant="subtle"
          :disabled="!data"
          @click="exportData"
        >
          <template #prefix><Download class="w-4 h-4" /></template>
          Export
        </Button>
      </div>
    </header>

    <!-- Main Content -->
    <IntelligenceDashboardShell
      :loading="loading"
      :refreshing="refreshing"
      :error="error"
      :is-permission-error="isPermissionError"
      :warming="warming"
      :not-implemented="notImplemented"
      :not-implemented-message="notImplementedMessage"
      :has-data="hasData"
      subject="executive data"
      permission-hint="Ask an administrator for executive dashboard access."
      @retry="retry"
    >
      <!-- Business Health Score -->
      <div class="px-6 pt-6">
        <div class="bg-accent-soft rounded-xl p-6 lg:p-8">
          <!-- Main Score -->
          <div class="max-w-4xl">
            <div class="text-sm font-semibold text-ink-gray-6 uppercase tracking-wider">
              Business Health Score
            </div>
            <div class="mt-2 flex items-baseline gap-3">
              <span class="text-5xl font-bold text-ink-gray-9 tracking-tight">
                {{ businessHealth.overall_score || 0 }}
              </span>
              <span class="text-3xl font-semibold text-ink-gray-6">%</span>
              <Badge
                v-bind="severityBadge(scoreSeverity(businessHealth.overall_score, { good: 80, warn: 60 }))"
                :aria-label="severityAria('Health', scoreSeverity(businessHealth.overall_score, { good: 80, warn: 60 }), businessHealth.overall_score)"
                size="sm"
                class="self-center"
              />
            </div>
            <div
              class="mt-4 h-3 w-full bg-surface-white rounded-full overflow-hidden"
              role="img"
              :aria-label="severityAria('Overall health score', scoreSeverity(businessHealth.overall_score, { good: 80, warn: 60 }), businessHealth.overall_score)"
            >
              <div
                :class="[severityFill(scoreSeverity(businessHealth.overall_score, { good: 80, warn: 60 })), 'h-full rounded-full motion-reduce:transition-none transition-all']"
                :style="`width: ${businessHealth.overall_score || 0}%`"
              ></div>
            </div>
          </div>

          <!-- AI Narrative -->
          <div v-if="data.narrative" class="mt-6 flex items-start gap-3 max-w-4xl">
            <Brain class="w-5 h-5 text-accent mt-0.5" />
            <div>
              <h3 class="text-sm font-semibold text-ink-gray-9">AI Executive Summary</h3>
              <p class="text-sm text-ink-gray-7 mt-1 leading-relaxed">{{ data.narrative }}</p>
            </div>
          </div>

          <!-- Department Health Breakdown -->
          <div class="mt-6 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
            <div
              v-for="(score, department) in businessHealth.department_scores"
              :key="department"
              class="flex flex-col p-3 rounded-lg motion-reduce:transition-none transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
              :class="departmentRoutes[department] ? 'cursor-pointer hover:bg-surface-white' : ''"
              :tabindex="departmentRoutes[department] ? 0 : undefined"
              :role="departmentRoutes[department] ? 'button' : undefined"
              :aria-label="departmentRoutes[department] ? `Go to ${department} dashboard` : undefined"
              @click="departmentRoutes[department] && router.push(departmentRoutes[department])"
              @keydown.enter="departmentRoutes[department] && router.push(departmentRoutes[department])"
            >
              <div class="text-xs font-medium text-ink-gray-6 uppercase tracking-wide truncate">{{ department }}</div>
              <div class="mt-1 text-2xl font-bold text-ink-gray-9">{{ Math.round(score) }}%</div>
              <div
                class="mt-2 h-1.5 w-full bg-surface-white rounded-full overflow-hidden"
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

      <!-- Critical Alerts -->
      <div v-if="alerts && alerts.length > 0" class="px-6 mb-6">
        <h2 class="text-sm font-semibold text-ink-gray-9 uppercase tracking-wider mb-3 flex items-center gap-2">
          <AlertTriangle class="w-5 h-5 text-neg" />
          Critical Alerts
        </h2>
        <div class="space-y-3">
          <div
            v-for="alert in alerts.slice(0, 5)"
            :key="alert.message"
            class="flex items-start justify-between gap-4 p-4 rounded-lg border border-outline-gray-1 bg-surface-white"
          >
            <div>
              <div class="flex items-center gap-3">
                <span class="font-semibold text-ink-gray-9">{{ alert.department }}</span>
              </div>
              <p class="text-sm text-ink-gray-7 mt-2">{{ alert.message }}</p>
            </div>
            <Badge
              v-bind="severityBadge(ragSeverity(alert.rag_status))"
              size="sm"
              class="shrink-0"
            />
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
            class="space-y-3"
          >
            <h3
              class="text-xs font-semibold text-ink-gray-6 uppercase tracking-wider flex items-center gap-2 cursor-pointer hover:text-accent motion-reduce:transition-none transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 rounded"
              tabindex="0"
              role="button"
              :aria-label="`Navigate to ${dept.label} dashboard`"
              @click="router.push(departmentRoutes[dept.key])"
              @keydown.enter="router.push(departmentRoutes[dept.key])"
            >
              <component :is="dept.icon" class="w-4 h-4" />
              {{ dept.label }}
            </h3>
            <template
              v-for="(kpi, key, kpiIndex) in kpis[dept.key]"
              :key="dept.key + key"
            >
              <div
                v-if="kpi && typeof kpi === 'object' && !kpi.error"
                class="relative"
              >
                <KpiCard
                  :label="kpi.label"
                  v-bind="kpi.format === 'currency'
                    ? { amount: kpi.value, currency: companyCurrency }
                    : kpi.format === 'percentage'
                      ? { percent: kpi.value }
                      : { value: formatKpiValue(kpi.value, kpi.format) }"
                  :severity="ragSeverity(kpi.rag_status)"
                  :delta="getKpiVariance(kpi)"
                  :delta-higher-is-better="!dept.reverseVariance"
                  :clickable="!!getExecMetric(kpi.label)"
                  @click="getExecMetric(kpi.label) && drillDown.open(EXEC_ENDPOINT, kpi.label, { metric: getExecMetric(kpi.label) })"
                >
                  <template v-if="sparklineData(dept, kpiIndex).length > 1" #footer>
                    <svg
                      class="w-full h-8"
                      :class="sparklineInk(getKpiVariance(kpi), { higherIsBetter: !dept.reverseVariance })"
                      viewBox="0 0 100 20"
                      aria-hidden="true"
                    >
                      <path
                        :d="generateSparkline(sparklineData(dept, kpiIndex))"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.5"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </template>
                </KpiCard>
                <ChevronRight
                  v-if="getExecMetric(kpi.label)"
                  class="absolute top-3 right-3 w-3.5 h-3.5 text-ink-gray-4 pointer-events-none"
                  aria-hidden="true"
                />
              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- Quick Actions -->
      <div class="px-6 pb-6">
        <h2 class="text-sm font-semibold text-ink-gray-9 uppercase tracking-wider mb-3">Quick Actions</h2>
        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          <Button
            variant="subtle"
            class="flex items-center gap-3 p-4 text-left h-auto"
            @click="generateStrategicReport"
          >
            <template #prefix><FileText class="w-5 h-5 text-ink-gray-6" /></template>
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
            <template #prefix><Download class="w-5 h-5 text-ink-gray-6" /></template>
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
            <template #prefix><Brain class="w-5 h-5 text-accent" /></template>
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
            <template #prefix><Calendar class="w-5 h-5 text-ink-gray-6" /></template>
            <div>
              <div class="text-sm font-medium text-ink-gray-9">Schedule Reports</div>
              <div class="text-xs text-ink-gray-6">Setup automated delivery</div>
            </div>
          </Button>
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
import { ref, computed, watch } from 'vue'
import {
  RefreshCw,
  Download,
  ChevronRight,
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
import { Button, Badge, LoadingIndicator } from 'frappe-ui'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import { FISCAL_PERIOD_RANGES } from '../utils/dateRangePresets'
import { useRouter } from 'vue-router'
import { useDrillDown } from './composables/useDrillDown'
import { useIntelligenceDashboard } from './composables/useIntelligenceDashboard'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'
import IntelligenceDashboardShell from './components/IntelligenceDashboardShell.vue'
import KpiCard from './components/KpiCard.vue'
import {
  severityBadge, severityFill, severityAria, sparklineInk,
  scoreSeverity, ragSeverity,
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

const selectedPeriod = ref('YTD')
const companyCurrency = ref(null)

const periodParams = computed(() => ({ period: selectedPeriod.value }))

const {
  data,
  loading,
  refreshing,
  error,
  isPermissionError,
  warming,
  notImplemented,
  notImplementedMessage,
  hasData,
  reload,
  retry,
} =
  useIntelligenceDashboard({
    url: 'insights.api.ml.get_executive_summary',
    params: periodParams,
    cache: 'executive-dashboard',
  })

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

watch(() => data.value?.currency, (currency) => {
  if (currency) companyCurrency.value = currency
})

function exportData() {
  const dataStr = JSON.stringify(data.value, null, 2)
  const dataUri = 'data:application/json;charset=utf-8,' + encodeURIComponent(dataStr)
  const exportFileDefaultName = `executive_dashboard_${selectedPeriod.value}_${new Date().toISOString().split('T')[0]}.json`
  const linkElement = document.createElement('a')
  linkElement.setAttribute('href', dataUri)
  linkElement.setAttribute('download', exportFileDefaultName)
  linkElement.click()
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

// Trend keys are the names produced by `ml/executive_intelligence
// ._trend_sparklines`. The previous version referenced three keys
// (`headcount`, `churn_rate`, `inventory_turns`) that did not match
// the underlying computation: the Python module was already
// computing `new_hires_per_month`, a self-referential customer-
// activity index, and a normalised stock-outflow index under
// those names, all of which read as misleading labels on the
// KPI cards. The Python module has been renamed to
// `new_hires_per_month`, `customer_activity_change`, and
// `stock_outflow_index` so the sparkline data and the KPI card
// numbers reconcile. (Risk has no monthly trend -- see
// `_trend_sparklines` -- so all three Risk KPI cards render
// without a sparkline; not a regression, just an honest absence.)
const departmentTrendKeys = {
  financial: ['revenue', 'revenue', 'revenue'],
  sales: ['sales_growth', 'sales_growth', 'sales_growth'],
  customer: ['customer_activity_change', 'customer_activity_change', 'customer_activity_change'],
  operations: ['stock_outflow_index', 'stock_outflow_index', 'stock_outflow_index'],
  risk: ['credit_risk', 'credit_risk', 'credit_risk'],
  hr: ['new_hires_per_month', 'new_hires_per_month', 'new_hires_per_month'],
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