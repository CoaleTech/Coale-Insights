<template>
  <div class="ink-fix flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <header class="bg-surface-white border-b border-outline-gray-1 px-6 py-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between flex-shrink-0">
      <div>
        <h1 class="text-2xl font-bold text-ink-gray-9">CEO Executive Dashboard</h1>
        <p class="text-sm text-ink-gray-6 mt-1">{{ selectedPeriod }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2 sm:gap-3">
        <IntelligenceDateFilter v-model="selectedPeriod" :options="FISCAL_PERIOD_RANGES" />
        <Button variant="subtle" @click="router.push('/executive-reports')">
          <template #prefix><FileText class="w-4 h-4" /></template>
          Strategic Report
        </Button>
        <Button variant="subtle" :disabled="!data" @click="exportData">
          <template #prefix><Download class="w-4 h-4" /></template>
          Export
        </Button>
        <Button :loading="refreshing" variant="solid" theme="gray" @click="reload">
          <template #prefix><RefreshCw class="w-4 h-4" /></template>
          Refresh
        </Button>
      </div>
    </header>

    <!-- Shell handles loading / error / warming / permission states -->
    <IntelligenceDashboardShell
      :loading="loading"
      :refreshing="refreshing"
      :error="error"
      :is-permission-error="isPermissionError"
      :warming="warming"
      :not-implemented="notImplemented"
      :not-implemented-message="notImplementedMessage"
      :has-data="hasData"
      :kpi-count="4"
      subject="executive data"
      permission-hint="Ask an administrator for executive dashboard access."
      @retry="retry"
    >
      <!-- ── Business Health Banner ── -->
      <div class="px-5 py-3 bg-surface-white border-b border-outline-gray-1 flex items-start gap-5 flex-wrap">
        <!-- Score + bar -->
        <template v-if="businessHealth.overall_score != null">
          <div class="flex-shrink-0">
            <div class="text-xs font-semibold text-ink-gray-6 uppercase tracking-wider mb-1">
              Business Health · {{ selectedPeriod }}
            </div>
            <div class="flex items-center gap-2">
              <span class="text-2xl font-bold text-ink-gray-9">{{ businessHealth.overall_score }}%</span>
              <Badge
                v-bind="severityBadge(scoreSeverity(businessHealth.overall_score, { good: 80, warn: 60 }))"
                :aria-label="severityAria('Health', scoreSeverity(businessHealth.overall_score, { good: 80, warn: 60 }), businessHealth.overall_score)"
                size="sm"
              />
            </div>
            <div
              class="mt-1.5 w-40 h-1.5 bg-surface-gray-2 rounded-full overflow-hidden"
              role="img"
              :aria-label="`Business health ${businessHealth.overall_score}%`"
            >
              <div
                :class="[severityFill(scoreSeverity(businessHealth.overall_score, { good: 80, warn: 60 })), 'h-full rounded-full motion-reduce:transition-none transition-all']"
                :style="`width: ${businessHealth.overall_score}%`"
              ></div>
            </div>
            <div v-if="businessHealth.score_breakdown" class="text-xs text-ink-gray-5 mt-1">
              {{ businessHealth.score_breakdown.excellent }} excellent ·
              {{ businessHealth.score_breakdown.good }} good ·
              {{ businessHealth.score_breakdown.needs_attention }} need attention
            </div>
          </div>

          <!-- Department score dots -->
          <div class="flex flex-wrap gap-4 flex-1">
            <button
              v-for="(score, dept) in businessHealth.department_scores"
              :key="dept"
              class="flex flex-col items-center gap-0.5 cursor-pointer hover:opacity-80 motion-reduce:transition-none transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 rounded"
              :aria-label="`${dept}: ${Math.round(score)}% — navigate to ${dept} dashboard`"
              @click="router.push(departmentRoutes[String(dept)] || '#')"
            >
              <span class="text-sm font-bold font-mono" :class="deptScoreClass(Number(score))">{{ Math.round(Number(score)) }}%</span>
              <span class="text-xs text-ink-gray-5 uppercase tracking-wide">{{ DEPT_SHORT[String(dept)] ?? dept }}</span>
            </button>
          </div>
        </template>
        <template v-else>
          <div class="text-sm text-ink-gray-6">
            {{ data?.restricted_note || 'Business Health Score is a cross-department composite and requires access to all departments.' }}
          </div>
        </template>

        <!-- AI narrative excerpt -->
        <div v-if="data?.narrative" class="hidden xl:block max-w-xs pl-4 border-l border-outline-gray-1 flex-shrink-0">
          <div class="text-xs text-ink-gray-5 mb-1">✦ AI Summary</div>
          <p class="text-xs text-ink-gray-7 leading-relaxed line-clamp-3">{{ data.narrative }}</p>
        </div>
      </div>

      <!-- ── Main 8/4 Layout ── -->
      <div class="grid grid-cols-1 lg:grid-cols-12">

        <!-- LEFT: Revenue Hero Panel -->
        <div class="lg:col-span-8 p-6 bg-accent-soft border-r border-outline-gray-1">

          <!-- Hero chart title -->
          <div class="mb-1">
            <h2 class="text-sm font-semibold text-ink-gray-7">Revenue · Monthly</h2>
            <p class="text-xs text-ink-gray-5">Last 12 months · {{ companyCurrency }}</p>
          </div>

          <!-- Revenue area chart -->
          <IntelligenceChart
            v-if="revenueTrendData.length > 1"
            :config="revenueTrendConfig"
            class="h-80"
          />
          <div v-else class="h-44 sm:h-52 flex items-center justify-center text-sm text-ink-gray-5">
            No revenue data available for this period
          </div>

          <!-- Stat strip: 4 headline KPIs below chart -->
          <div class="mt-4 grid grid-cols-2 sm:grid-cols-4 border border-outline-gray-1 rounded-lg bg-surface-white overflow-hidden">

            <!-- Revenue (12m) -->
            <button
              type="button"
              class="px-4 py-3 border-r border-outline-gray-1 text-left hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:bg-surface-gray-1"
              @click="openExecDrill('Revenue')"
            >
              <div class="text-xs text-ink-gray-5 uppercase tracking-wide">Revenue 12m</div>
              <div
                class="mt-1 text-xl font-bold font-mono"
                :class="ragTextClass(kpis.sales?.pipeline_value?.rag_status)"
              >
                {{ formatKpiValue(trends.revenue_12m, 'currency') }}
              </div>
              <div class="text-xs text-ink-gray-5 mt-0.5">Trailing 12 months</div>
            </button>

            <!-- Net Margin -->
            <div class="px-4 py-3 border-r border-outline-gray-1">
              <div class="text-xs text-ink-gray-5 uppercase tracking-wide">Net Margin</div>
              <div
                class="mt-1 text-xl font-bold font-mono"
                :class="ragTextClass(kpis.financial?.net_margin?.rag_status)"
              >
                {{ formatKpiValue(kpis.financial?.net_margin?.value, 'percentage') }}
              </div>
              <div class="text-xs text-ink-gray-5 mt-0.5">
                <span v-if="kpis.financial?.net_margin?.variance_pct != null">
                  <span :class="kpis.financial.net_margin.variance_pct >= 0 ? 'text-pos' : 'text-neg'">
                    {{ kpis.financial.net_margin.variance_pct >= 0 ? '+' : '' }}{{ kpis.financial.net_margin.variance_pct.toFixed(1) }}pp
                  </span>
                  vs target
                </span>
              </div>
            </div>

            <!-- Gross Margin -->
            <div class="px-4 py-3 border-r border-outline-gray-1">
              <div class="text-xs text-ink-gray-5 uppercase tracking-wide">Gross Margin</div>
              <div
                class="mt-1 text-xl font-bold font-mono"
                :class="ragTextClass(kpis.sales?.profit_margin?.rag_status)"
              >
                {{ formatKpiValue(kpis.sales?.profit_margin?.value, 'percentage') }}
              </div>
              <div class="text-xs text-ink-gray-5 mt-0.5">
                <span v-if="kpis.sales?.profit_margin?.variance_pct != null">
                  <span :class="kpis.sales.profit_margin.variance_pct >= 0 ? 'text-pos' : 'text-neg'">
                    {{ kpis.sales.profit_margin.variance_pct >= 0 ? '+' : '' }}{{ kpis.sales.profit_margin.variance_pct.toFixed(1) }}pp
                  </span>
                  vs target
                </span>
              </div>
            </div>

            <!-- Order Fulfillment -->
            <div class="px-4 py-3">
              <div class="text-xs text-ink-gray-5 uppercase tracking-wide">Order Fulfillment</div>
              <div
                class="mt-1 text-xl font-bold font-mono"
                :class="ragTextClass(kpis.sales?.fulfillment_rate?.rag_status)"
              >
                {{ formatKpiValue(kpis.sales?.fulfillment_rate?.value, 'percentage') }}
              </div>
              <div class="text-xs text-ink-gray-5 mt-0.5">
                <span v-if="kpis.sales?.fulfillment_rate?.variance_pct != null">
                  <span :class="kpis.sales.fulfillment_rate.variance_pct >= 0 ? 'text-pos' : 'text-neg'">
                    {{ kpis.sales.fulfillment_rate.variance_pct >= 0 ? '+' : '' }}{{ kpis.sales.fulfillment_rate.variance_pct.toFixed(1) }}pp
                  </span>
                  vs target
                </span>
              </div>
            </div>
          </div>

          <!-- Context grid: Customer + Ops & HR -->
          <div class="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">

            <!-- Customer card -->
            <div class="bg-surface-white border border-outline-gray-1 rounded-lg p-4">
              <div class="text-xs font-semibold text-ink-gray-5 uppercase tracking-wide mb-3">Customer</div>
              <template v-if="blockOk('customer')">
                <div
                  v-for="(kpi, key) in kpis.customer"
                  :key="String(key)"
                  class="flex justify-between items-baseline py-1.5 border-b border-outline-gray-1 last:border-0 text-sm"
                >
                  <template v-if="kpi && !kpi.error">
                    <span class="text-ink-gray-7">{{ kpi.label }}</span>
                    <span class="font-semibold font-mono" :class="ragTextClass(kpi.rag_status)">
                      {{ formatKpiValue(kpi.value, kpi.format) }}
                    </span>
                  </template>
                </div>
              </template>
              <div v-else class="text-xs text-ink-gray-5">Customer data unavailable</div>
              <button
                class="mt-2 text-xs text-accent font-medium hover:underline focus-visible:underline focus-visible:outline-none"
                @click="router.push('/customer-intelligence')"
              >
                View dashboard →
              </button>
            </div>

            <!-- Ops & HR card -->
            <div class="bg-surface-white border border-outline-gray-1 rounded-lg p-4">
              <div class="text-xs font-semibold text-ink-gray-5 uppercase tracking-wide mb-3">Operations &amp; HR</div>
              <template v-if="blockOk('operations')">
                <div
                  v-for="(kpi, key) in kpis.operations"
                  :key="String(key)"
                  class="flex justify-between items-baseline py-1.5 border-b border-outline-gray-1 last:border-0 text-sm"
                  :class="kpi && getExecMetric(kpi.label) ? 'cursor-pointer hover:bg-surface-gray-1' : ''"
                  @click="kpi && openExecDrill(kpi.label)"
                >
                  <template v-if="kpi && !kpi.error">
                    <span class="text-ink-gray-7">{{ kpi.label }}</span>
                    <span class="font-semibold font-mono" :class="ragTextClass(kpi.rag_status)">
                      {{ formatKpiValue(kpi.value, kpi.format) }}
                    </span>
                  </template>
                </div>
              </template>
              <!-- HR attrition below ops -->
              <template v-if="blockOk('hr')">
                <div
                  v-for="(kpi, key) in kpis.hr"
                  :key="`hr-${String(key)}`"
                  class="flex justify-between items-baseline py-1.5 border-b border-outline-gray-1 last:border-0 text-sm"
                >
                  <template v-if="kpi && !kpi.error && kpi.rag_status !== 'green'">
                    <span class="text-ink-gray-7">{{ kpi.label }}</span>
                    <span class="font-semibold font-mono" :class="ragTextClass(kpi.rag_status)">
                      {{ formatKpiValue(kpi.value, kpi.format) }}
                    </span>
                  </template>
                </div>
              </template>
              <button
                class="mt-2 text-xs text-accent font-medium hover:underline focus-visible:underline focus-visible:outline-none"
                @click="router.push('/inventory-intelligence')"
              >
                View dashboard →
              </button>
            </div>

          </div>
        </div>

        <!-- RIGHT: Attention Rail -->
        <div class="lg:col-span-4 p-5 bg-surface-white overflow-auto">

          <!-- Critical Issues -->
          <h2 class="text-xs font-semibold uppercase tracking-wider text-neg mb-3">
            ⚠ Critical Issues · {{ criticalAlerts.length }} Active
          </h2>
          <div v-if="criticalAlerts.length" class="mb-5 space-y-0">
            <div
              v-for="(alert, i) in criticalAlerts"
              :key="`crit-${i}`"
              class="py-3 border-b border-outline-gray-1 last:border-0"
            >
              <div class="flex items-start gap-2 mb-1">
                <span
                  class="flex-shrink-0 w-5 h-5 rounded-full bg-surface-red-2 text-ink-gray-9 text-xs font-bold flex items-center justify-center"
                  aria-hidden="true"
                >{{ i + 1 }}</span>
                <div>
                  <div class="text-sm font-semibold text-ink-gray-9">{{ alert.department }}</div>
                  <Badge
                    v-bind="severityBadge(ragSeverity(alert.rag_status))"
                    size="sm"
                    class="mt-0.5"
                  />
                </div>
              </div>
              <p class="text-xs text-ink-gray-7 ml-7 mb-1 leading-snug">{{ alert.message }}</p>
              <button
                v-if="alertDeptRoute(alert.department)"
                class="ml-7 text-xs text-accent font-medium hover:underline focus-visible:underline focus-visible:outline-none"
                @click="router.push(alertDeptRoute(alert.department))"
              >
                → {{ alert.department }} dashboard
              </button>
            </div>
          </div>
          <div v-else class="mb-5 text-xs text-ink-gray-5">No critical issues</div>

          <!-- Watch Items (amber) -->
          <div class="border-t border-outline-gray-1 pt-4 mb-5">
            <h2 class="text-xs font-semibold uppercase tracking-wider text-warn mb-3">
              Watch · {{ watchAlerts.length }} Items
            </h2>
            <div v-if="watchAlerts.length" class="space-y-0">
              <div
                v-for="(alert, i) in watchAlerts"
                :key="`watch-${i}`"
                class="flex items-start gap-2 py-2.5 border-b border-outline-gray-1 last:border-0"
              >
                <span
                  class="flex-shrink-0 w-5 h-5 rounded-full bg-surface-amber-2 text-ink-gray-9 text-xs font-bold flex items-center justify-center"
                  aria-hidden="true"
                >{{ criticalAlerts.length + i + 1 }}</span>
                <div class="flex-1 min-w-0">
                  <div class="flex items-baseline justify-between gap-2">
                    <span class="text-sm font-medium text-ink-gray-9 truncate">
                      {{ alert.department }}
                    </span>
                  </div>
                  <p class="text-xs text-ink-gray-6 leading-snug mt-0.5">{{ alert.message }}</p>
                  <button
                    v-if="alertDeptRoute(alert.department)"
                    class="text-xs text-accent font-medium hover:underline focus-visible:underline focus-visible:outline-none mt-0.5"
                    @click="router.push(alertDeptRoute(alert.department))"
                  >
                    → {{ alert.department }} dashboard
                  </button>
                </div>
              </div>
            </div>
            <div v-else class="text-xs text-ink-gray-5">No watch items</div>
          </div>

          <!-- Strengths -->
          <div class="border-t border-outline-gray-1 pt-4 mb-4">
            <h2 class="text-xs font-semibold uppercase tracking-wider text-pos mb-3">Strengths</h2>
            <div v-if="strengths.length" class="space-y-1.5">
              <div
                v-for="item in strengths"
                :key="item.key"
                class="flex items-center gap-2 text-sm"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-pos-fill flex-shrink-0" aria-hidden="true"></span>
                <span class="text-ink-gray-7 flex-1 min-w-0 truncate">{{ item.label }}</span>
                <span class="font-semibold text-pos font-mono flex-shrink-0">{{ item.value }}</span>
              </div>
            </div>
            <div v-else class="text-xs text-ink-gray-5">No green metrics at this time</div>
          </div>

          <!-- Manufacturing unavailable note -->
          <div
            v-if="mfgUnavailable"
            class="mt-2 p-3 bg-surface-gray-1 border border-outline-gray-1 rounded-lg"
          >
            <p class="text-xs text-ink-gray-6">
              ⚠ Manufacturing: no workstation or work-order records found; KPIs not applicable.
            </p>
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

<script setup lang="ts">
defineOptions({ name: 'ExecutiveDashboard' })
import { ref, computed, watch } from 'vue'
import { RefreshCw, Download, FileText } from 'lucide-vue-next'
import { Button, Badge } from 'frappe-ui'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import { FISCAL_PERIOD_RANGES } from '../utils/dateRangePresets'
import { useRouter } from 'vue-router'
import { useDrillDown } from './composables/useDrillDown'
import { useIntelligenceDashboard } from './composables/useIntelligenceDashboard'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'
import IntelligenceDashboardShell from './components/IntelligenceDashboardShell.vue'
import IntelligenceChart from './components/IntelligenceChart.vue'
import {
  severityBadge, severityFill, severityAria,
  scoreSeverity, ragSeverity,
} from '../utils/status'
import { formatMoney, formatPercent, NO_VALUE } from '../utils/format'
import { themeColor } from '../utils/chartTheme'

/** One KPI leaf produced by `_kpi()` (executive_intelligence.py). */
interface ExecutiveKpi {
  label: string
  value: number | null
  format: string
  target?: number
  rag_status?: 'green' | 'amber' | 'red'
  variance_pct?: number
  variance_points?: number
  variance_ratio?: number
  variance_weeks?: number
  variance_turns?: number
  error?: string
  status?: string
  note?: string
  skus_out?: number
  skus_total?: number
  net_change?: number
}
type KpiBlock = Record<string, ExecutiveKpi | undefined>

interface ExecutiveAlert {
  priority: string
  department: string
  message: string
  rag_status: string
}

interface BusinessHealthScore {
  overall_score: number
  overall_rag: string
  department_scores: Record<string, number>
  score_breakdown: { excellent: number; good: number; needs_attention: number }
}

interface ExecutiveTrends {
  revenue?: number[]
  /** Sum of `revenue[]` (trailing-12-month window), computed server-side. */
  revenue_12m?: number
  /** Month labels corresponding to `revenue[]`; added in 2026-10-22 fix. */
  revenue_months?: string[]
  sales_growth?: number[]
  new_hires_per_month?: number[]
  oee?: number[]
  customer_activity_change?: number[]
  stock_outflow_index?: number[]
}

interface ExecutiveSummaryData {
  period?: string
  generated_at?: string
  currency?: string
  kpis?: Record<string, KpiBlock>
  alerts?: ExecutiveAlert[]
  narrative?: string | null
  business_health_score?: BusinessHealthScore | null
  trends?: ExecutiveTrends | null
  restricted_note?: string
}

const router = useRouter()

const EXEC_ENDPOINT = 'insights.api.ml.executive.get_executive_detail'
const drillDown = useDrillDown()

const EXEC_DRILLABLE_METRICS: Record<string, (label: string) => boolean> = {
  'revenue_invoices': (label) => /Revenue|Sales/i.test(label),
  'open_orders': (label) => /Open Orders|Sales Orders/i.test(label),
  'active_employees': (label) => /Employees|Headcount/i.test(label),
  'open_pos': (label) => /Purchase Orders|Open PO/i.test(label),
}

function getExecMetric(label: string): string | null {
  for (const [metric, test] of Object.entries(EXEC_DRILLABLE_METRICS)) {
    if (test(label)) return metric
  }
  return null
}

function openExecDrill(label: string) {
  const metric = getExecMetric(label)
  if (metric) drillDown.open(EXEC_ENDPOINT, label, { metric })
}

const selectedPeriod = ref('YTD')
const companyCurrency = ref<string | null>(null)
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
} = useIntelligenceDashboard<ExecutiveSummaryData>({
  url: 'insights.api.ml.get_executive_summary',
  params: periodParams,
  cache: 'executive-dashboard',
})

const businessHealth = computed<Partial<BusinessHealthScore>>(
  () => data.value?.business_health_score || {},
)
const alerts = computed<ExecutiveAlert[]>(() => data.value?.alerts || [])
const kpis = computed<Record<string, KpiBlock>>(() => data.value?.kpis || {})
const trends = computed<ExecutiveTrends>(() => (data.value?.trends || {}) as ExecutiveTrends)

watch(
  () => data.value?.currency,
  (currency) => { if (currency) companyCurrency.value = currency },
)

// ── Derived alert splits ──────────────────────────────────────────────────

const criticalAlerts = computed(() => alerts.value.filter((a) => a.rag_status === 'red'))
const watchAlerts = computed(() => alerts.value.filter((a) => a.rag_status === 'amber'))

// Collect all green KPIs across blocks for the strengths rail
const strengths = computed(() => {
  const result: Array<{ label: string; value: string; key: string }> = []
  for (const [domain, block] of Object.entries(kpis.value)) {
    if (!block || (block as any).error || (block as any).status === 'unavailable') continue
    for (const [k, kpi] of Object.entries(block)) {
      if (!kpi || typeof kpi !== 'object' || kpi.error) continue
      if (kpi.rag_status === 'green' && kpi.value != null) {
        result.push({ label: kpi.label, value: formatKpiValue(kpi.value, kpi.format), key: `${domain}-${k}` })
      }
    }
  }
  return result
})

/** True when a KPI block is a real data block (not the _unavailable() sentinel). */
function blockOk(domain: string): boolean {
  const b = kpis.value[domain] as Record<string, unknown> | undefined
  return !!b && !b.error && b.status !== 'unavailable'
}

/** True when manufacturing returned the no-data sentinel. */
const mfgUnavailable = computed(() => {
  const b = kpis.value.manufacturing as Record<string, unknown> | undefined
  return !!b && b.status === 'unavailable'
})

// ── Revenue hero chart ────────────────────────────────────────────────────

const revenueTrendData = computed(() => {
  const values = trends.value.revenue ?? []
  // revenue_months added in the Oct 2026 fix; fall back to M1…MN for old cache
  const months = trends.value.revenue_months ?? values.map((_, i) => `M${i + 1}`)
  return values.map((v, i) => ({ month: months[i] ?? `M${i + 1}`, Revenue: v }))
})

const revenueTrendConfig = computed(() => ({
  title: '',
  data: revenueTrendData.value,
  xAxis: { key: 'month', type: 'category' as const },
  yAxis: { title: '', yMin: 0 },
  colors: [themeColor('--app-accent')],
  series: [{ name: 'Revenue', type: 'area' as const, fillOpacity: 0.12 }],
}))

// ── Navigation helpers ────────────────────────────────────────────────────

const departmentRoutes: Record<string, string> = {
  financial: '/financial-intelligence',
  sales: '/sales-intelligence',
  customer: '/customer-intelligence',
  operations: '/inventory-intelligence',
  risk: '/risk-intelligence',
  hr: '/hr-intelligence',
  manufacturing: '/manufacturing-intelligence',
}

// Alert.department values are _DOMAIN_LABELS-capitalised (People, Operations, …)
const DEPT_LABEL_TO_KEY: Record<string, string> = {
  Financial: 'financial',
  Sales: 'sales',
  Customer: 'customer',
  Operations: 'operations',
  Risk: 'risk',
  People: 'hr',
  HR: 'hr',
  Manufacturing: 'manufacturing',
}

function alertDeptRoute(dept: string): string {
  return departmentRoutes[DEPT_LABEL_TO_KEY[dept] ?? dept.toLowerCase()] ?? ''
}

const DEPT_SHORT: Record<string, string> = {
  financial: 'Fin',
  sales: 'Sales',
  customer: 'Cust',
  operations: 'Ops',
  risk: 'Risk',
  hr: 'HR',
  manufacturing: 'Mfg',
}

// ── Colour helpers ────────────────────────────────────────────────────────

function deptScoreClass(score: number): string {
  // scoreSeverity: good threshold 80, warn 60; higherIsBetter=true
  const sev = scoreSeverity(score, { good: 80, warn: 60 })
  if (sev === 'low') return 'text-pos'
  if (sev === 'medium') return 'text-warn'
  return 'text-neg'
}

function ragTextClass(rag?: string | null): string {
  if (rag === 'green') return 'text-pos'
  if (rag === 'red') return 'text-neg'
  return 'text-warn'
}

// ── Formatting ────────────────────────────────────────────────────────────

function formatKpiValue(value: number | null | undefined, format: string): string {
  if (value === null || value === undefined) return NO_VALUE
  switch (format) {
    case 'currency':
      return formatMoney(value, companyCurrency.value, { compact: true })
    case 'percentage':
      return formatPercent(value)
    case 'decimal':
      return Number.isInteger(value) ? String(value) : value.toFixed(1)
    case 'ratio':
      return `${value.toFixed(1)}:1`
    case 'risk_score':
      return `${Math.round(value)}/100`
    default:
      return value.toLocaleString()
  }
}

function exportData() {
  const dataStr = JSON.stringify(data.value, null, 2)
  const dataUri = 'data:application/json;charset=utf-8,' + encodeURIComponent(dataStr)
  const link = document.createElement('a')
  link.setAttribute('href', dataUri)
  link.setAttribute('download', `executive_dashboard_${selectedPeriod.value}_${new Date().toISOString().split('T')[0]}.json`)
  link.click()
}
</script>
