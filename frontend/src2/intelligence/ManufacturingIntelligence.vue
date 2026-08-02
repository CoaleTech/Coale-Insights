<script setup lang="ts">
defineOptions({ name: 'ManufacturingIntelligence' })
import { ref, computed, onMounted } from 'vue'
import { Badge, Button, Tabs } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { apiCall } from '../helpers/api'
import { useIntelligenceDashboard } from './composables/useIntelligenceDashboard'
import {
  severityBadge, severityFill, severityAria, scoreSeverity, ragSeverity,
  prioritySeverity, type Severity,
} from '../utils/status'
import { formatCount, formatDateTime } from '../utils/format'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import { useDrillDown } from './composables/useDrillDown'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'
import KpiCard from './components/KpiCard.vue'
import IntelligenceDashboardShell from './components/IntelligenceDashboardShell.vue'
import SectionHeader from './components/SectionHeader.vue'

// ─── Payload interfaces (confirmed against insights/ml/manufacturing_intelligence.py) ───

interface OeeAnalysis {
  oee_score_pct?: number
  availability_pct?: number
  performance_pct?: number
  quality_pct?: number
  oee_rating?: string
  benchmark_comparison?: string
}

interface ProductionMetrics {
  total_work_orders?: number
  completed_orders?: number
  completion_rate_pct?: number
  total_production_qty?: number
  planned_production_qty?: number
  quantity_achievement_pct?: number
  monthly_growth_rate?: number
  production_health?: string
}

interface EfficiencyMetrics {
  average_efficiency_pct?: number
  efficiency_variance?: number
  efficiency_std_dev?: number
  consistency_rating?: string
  best_workstation?: string
  worst_workstation?: string
  efficiency_trend?: string
}

interface CapacityUtilization {
  overall_utilization_pct?: number
  available_capacity_pct?: number
  available_capacity_hours?: number
  capacity_constrained_stations?: number
  underutilized_stations?: number
  capacity_planning_status?: string
}

interface BottleneckRow {
  workstation?: string
  name?: string
  utilization_pct?: number
  load_pct?: number
  severity?: string
  improvement_potential?: number
}

interface BottleneckAnalysis {
  bottleneck_count?: number
  bottlenecks?: BottleneckRow[]
  priority_bottleneck?: string
  total_improvement_hours?: number
}

/** Workstation row from _analyze_workstations. Python returns utilization_pct; the template
 *  also uses efficiency_pct / total_jobs / completed_jobs which are not in the Python source
 *  and will simply be undefined at runtime (guarded with || 0 in the template). */
interface WorkstationRow {
  workstation?: string
  utilization_pct?: number
  capacity_hours?: number
  utilized_hours?: number
  status?: string
  efficiency_pct?: number   // [INFERENCE] not in Python source; template falls back to 0
  total_jobs?: number       // [INFERENCE] not in Python source; template falls back to 0
  completed_jobs?: number   // [INFERENCE] not in Python source; template falls back to 0
}

interface WorkstationPerformanceSection {
  workstation_count?: number
  workstation_performance?: WorkstationRow[]
  top_performer?: string
  bottom_performer?: string
}

/** Recommendation item from _generate_manufacturing_recommendations.
 *  Python returns: priority, category, title, description, actions[].
 *  Template also uses recommendation / impact / action / timeframe as optional fallbacks. */
interface ManufacturingRecommendation {
  priority?: string
  category?: string
  title?: string
  description?: string
  actions?: string[]
  recommendation?: string  // [INFERENCE] not in Python source; template uses as fallback for title
  impact?: string          // [INFERENCE] not in Python source; guarded by v-if
  action?: string          // [INFERENCE] not in Python source; guarded by v-if
  timeframe?: string       // [INFERENCE] not in Python source; guarded by v-if
}

/** Top-level payload for insights.api.ml.get_manufacturing_overview */
interface ManufacturingPayload {
  period?: string
  generated_at?: string
  production_metrics?: ProductionMetrics
  oee_analysis?: OeeAnalysis
  quality_metrics?: Record<string, unknown>
  efficiency_metrics?: EfficiencyMetrics
  capacity_utilization?: CapacityUtilization
  workstation_performance?: WorkstationPerformanceSection
  bottleneck_analysis?: BottleneckAnalysis
  cost_analysis?: Record<string, unknown>
  production_forecast?: Record<string, unknown>
  maintenance_insights?: Record<string, unknown>
  recommendations?: ManufacturingRecommendation[]
  raw_data?: Record<string, unknown>
}

/** Payload for insights.api.ml.get_production_forecast (returns _forecast_production() dict). */
interface ProductionForecastData {
  current_monthly_avg?: number
  trend_direction?: string
  monthly_growth_rate?: number
  quarterly_forecast?: unknown[]
  forecast_reliability?: string
  message?: string
  error?: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const router = useRouter()
const drillDown = useDrillDown()
const MFG_ENDPOINT = 'insights.api.ml.manufacturing.get_manufacturing_detail'

const lastUpdated = ref('')
const productionForecast = ref<ProductionForecastData>({})

const { data, loading, refreshing, error, isPermissionError, hasData, reload, retry } =
  useIntelligenceDashboard<ManufacturingPayload>({
    url: 'insights.api.ml.get_manufacturing_overview',
    cache: 'manufacturing-intelligence',
  })

const tabIndex = ref(0)
const tabs = [
  { label: 'Overview' },
  { label: 'OEE Analysis' },
  { label: 'Capacity' },
  { label: 'Production Forecast' },
  { label: 'Recommendations' },
]

const oeeAnalysis = computed(() => data.value?.oee_analysis ?? ({} as OeeAnalysis))
const productionMetrics = computed(() => data.value?.production_metrics ?? ({} as ProductionMetrics))
const capacityUtilization = computed(() => data.value?.capacity_utilization ?? ({} as CapacityUtilization))
const bottleneckAnalysis = computed(() => data.value?.bottleneck_analysis ?? ({} as BottleneckAnalysis))
const efficiencyMetrics = computed(() => data.value?.efficiency_metrics ?? ({} as EfficiencyMetrics))
const workstationPerformance = computed(
  () => data.value?.workstation_performance?.workstation_performance ?? ([] as WorkstationRow[]),
)
const recommendations = computed(() => data.value?.recommendations ?? ([] as ManufacturingRecommendation[]))

/** OEE / availability / performance / quality: higher is better. */
function oeeSeverity(score: number | undefined): Severity {
  return scoreSeverity(score, { good: 85, warn: 65, higherIsBetter: true })
}

/**
 * Capacity utilization: model as higher-is-better up to 89%,
 * then critical above 90% (overloaded). We treat < 70% as low (good -- headroom),
 * 70-89% as medium (operating range), >= 90% as critical (overloaded).
 */
function utilizationSeverity(pct: number | undefined): Severity {
  const p = pct ?? 0
  if (p >= 90) return 'critical'
  if (p >= 70) return 'medium'
  return 'low'
}

/** Scrap/defect rates: lower is better. */
function scrapSeverity(rate: number | undefined): Severity {
  return scoreSeverity(rate, { good: 2, warn: 5, higherIsBetter: false })
}

/** OEE rating string ('World Class' / 'Good' / etc.) to Severity. */
function oeeRatingSeverity(rating: string | undefined): Severity {
  if (['World Class', 'Excellent'].includes(rating || '')) return 'low'
  if (['Good', 'Average'].includes(rating || '')) return 'medium'
  return 'high'
}



async function loadForecast() {
  try {
    // Python get_production_forecast() returns the forecast dict directly, not {forecast: ...}
    const result = await apiCall<ProductionForecastData>('insights.api.ml.get_production_forecast')
    productionForecast.value = result
  } catch (e) {
    console.error('Error loading production forecast:', e)
  }
}

function refreshAll() {
  lastUpdated.value = new Date().toISOString()
  reload()
  loadForecast()
}



const formatKey = (key: string) =>
  key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

const formatValue = (value: unknown) =>
  typeof value === 'number' ? formatCount(value) : String(value ?? '')

const chatContext = computed(() => ({
  oeeAnalysis: oeeAnalysis.value,
  productionMetrics: productionMetrics.value,
  capacityUtilization: capacityUtilization.value,
  bottleneckAnalysis: bottleneckAnalysis.value,
  efficiencyMetrics: efficiencyMetrics.value,
  recommendations: recommendations.value,
  activeTab: tabIndex.value,
  lastUpdated: lastUpdated.value,
}))

function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    'Sales': '/sales-intelligence',
    'Financial': '/financial-intelligence',
    'Inventory': '/inventory-intelligence',
    'Procurement': '/procurement-intelligence',
    'HR': '/hr-intelligence',
    'Manufacturing': '/manufacturing-intelligence',
    'ESG': '/esg-intelligence',
  }
  if (routes[target]) router.push(routes[target])
}

onMounted(() => {
  loadForecast()
})
</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <header class="bg-surface-white border-b px-6 py-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-ink-gray-9">Manufacturing Intelligence</h1>
        <p class="text-sm text-ink-gray-6 mt-1">
          Production efficiency, OEE analysis, and capacity planning
        </p>
      </div>
      <div class="flex items-center gap-3">
        <span v-if="lastUpdated" class="text-sm text-ink-gray-6">
          Updated: {{ formatDateTime(lastUpdated) }}
        </span>
        <Button variant="subtle" :loading="refreshing" @click="refreshAll">
          Refresh
        </Button>
      </div>
    </header>

    <IntelligenceDashboardShell
      :loading="loading"
      :refreshing="refreshing"
      :error="error"
      :is-permission-error="isPermissionError"
      :has-data="hasData"
      subject="manufacturing data"
      permission-hint="Ask an administrator for Work Order and BOM read access."
      :kpi-count="6"
      @retry="retry"
    >
      <!-- Summary KPI cards -->
      <div class="p-6 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard
          label="OEE Score"
          :percent="oeeAnalysis.oee_score_pct"
          :severity="oeeSeverity(oeeAnalysis.oee_score_pct)"
          :loading="!hasData"
          :sublabel="oeeAnalysis.oee_rating || undefined"
        />
        <KpiCard
          label="Availability"
          :percent="oeeAnalysis.availability_pct"
          :severity="oeeSeverity(oeeAnalysis.availability_pct)"
          :loading="!hasData"
          sublabel="Uptime ratio"
        />
        <KpiCard
          label="Completion Rate"
          :percent="productionMetrics.completion_rate_pct"
          :severity="oeeSeverity(productionMetrics.completion_rate_pct)"
          :loading="!hasData"
          sublabel="Work orders"
        />
        <KpiCard
          label="Capacity Utilization"
          :percent="capacityUtilization.overall_utilization_pct"
          :severity="utilizationSeverity(capacityUtilization.overall_utilization_pct)"
          :loading="!hasData"
          sublabel="Overall"
        />
        <KpiCard
          label="Efficiency"
          :percent="efficiencyMetrics.average_efficiency_pct"
          :severity="oeeSeverity(efficiencyMetrics.average_efficiency_pct)"
          :loading="!hasData"
          :sublabel="efficiencyMetrics.consistency_rating || undefined"
        />
        <KpiCard
          label="Work Orders"
          :value="productionMetrics.completed_orders"
          :loading="!hasData"
          :sublabel="hasData ? `of ${productionMetrics.total_work_orders || 0} total` : undefined"
          :clickable="true"
          @click="drillDown.open(MFG_ENDPOINT, 'Work Orders', { metric: 'completed_work_orders' })"
        />
      </div>

      <!-- Tab strip -->
      <div class="mx-6">
        <Tabs v-model="tabIndex" :tabs="tabs" />
      </div>

      <!-- Tab content -->
      <div class="flex-1 p-6 overflow-auto">

        <!-- Overview -->
        <div v-if="tabIndex === 0">
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Production Summary -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader title="Production Summary" :level="3" />
              <div class="space-y-3 mt-4">
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Total Work Orders</span>
                  <span class="font-semibold text-ink-gray-8">{{ productionMetrics.total_work_orders || 0 }}</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Completed Orders</span>
                  <span class="font-semibold text-ink-gray-8">{{ productionMetrics.completed_orders || 0 }}</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Total Production Qty</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatCount(productionMetrics.total_production_qty) }}</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Monthly Growth Rate</span>
                  <span class="font-semibold text-ink-gray-8">
                    {{ (productionMetrics.monthly_growth_rate || 0) >= 0 ? '+' : '' }}{{ productionMetrics.monthly_growth_rate || 0 }}%
                  </span>
                </div>
                <div class="flex justify-between items-center py-2">
                  <span class="text-sm text-ink-gray-6">Completion Rate</span>
                  <span class="font-semibold text-ink-gray-8">{{ productionMetrics.completion_rate_pct || 0 }}%</span>
                </div>
              </div>
            </div>

            <!-- OEE Quick View -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader title="OEE Quick View" :level="3" />
              <div class="space-y-4 mt-4">
                <div>
                  <div class="flex justify-between text-sm mb-1">
                    <span class="text-ink-gray-6">Availability</span>
                    <span class="font-medium text-ink-gray-8">{{ oeeAnalysis.availability_pct || 0 }}%</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-2">
                    <div
                      class="h-2 rounded-full"
                      :class="severityFill(oeeSeverity(oeeAnalysis.availability_pct))"
                      :style="{ width: (oeeAnalysis.availability_pct || 0) + '%' }"
                      role="img"
                      :aria-label="severityAria('Availability', oeeSeverity(oeeAnalysis.availability_pct), oeeAnalysis.availability_pct + '%')"
                    />
                  </div>
                </div>
                <div>
                  <div class="flex justify-between text-sm mb-1">
                    <span class="text-ink-gray-6">Performance</span>
                    <span class="font-medium text-ink-gray-8">{{ oeeAnalysis.performance_pct || 0 }}%</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-2">
                    <div
                      class="h-2 rounded-full"
                      :class="severityFill(oeeSeverity(oeeAnalysis.performance_pct))"
                      :style="{ width: (oeeAnalysis.performance_pct || 0) + '%' }"
                      role="img"
                      :aria-label="severityAria('Performance', oeeSeverity(oeeAnalysis.performance_pct), oeeAnalysis.performance_pct + '%')"
                    />
                  </div>
                </div>
                <div>
                  <div class="flex justify-between text-sm mb-1">
                    <span class="text-ink-gray-6">Quality</span>
                    <span class="font-medium text-ink-gray-8">{{ oeeAnalysis.quality_pct || 0 }}%</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-2">
                    <div
                      class="h-2 rounded-full"
                      :class="severityFill(oeeSeverity(oeeAnalysis.quality_pct))"
                      :style="{ width: (oeeAnalysis.quality_pct || 0) + '%' }"
                      role="img"
                      :aria-label="severityAria('Quality', oeeSeverity(oeeAnalysis.quality_pct), oeeAnalysis.quality_pct + '%')"
                    />
                  </div>
                </div>
                <div class="pt-2 border-t border-outline-gray-1">
                  <div class="flex justify-between text-sm mb-1">
                    <span class="font-medium text-ink-gray-7">Overall OEE</span>
                    <span class="font-bold text-ink-gray-9">{{ oeeAnalysis.oee_score_pct || 0 }}%</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-3">
                    <div
                      class="h-3 rounded-full motion-reduce:transition-none transition-all"
                      :class="severityFill(oeeSeverity(oeeAnalysis.oee_score_pct))"
                      :style="{ width: (oeeAnalysis.oee_score_pct || 0) + '%' }"
                      role="img"
                      :aria-label="severityAria('Overall OEE', oeeSeverity(oeeAnalysis.oee_score_pct), oeeAnalysis.oee_score_pct + '%')"
                    />
                  </div>
                </div>
              </div>
            </div>

            <!-- Efficiency Metrics -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader title="Efficiency Metrics" :level="3" />
              <div class="space-y-3 mt-4">
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Average Efficiency</span>
                  <span class="font-semibold text-ink-gray-8">{{ efficiencyMetrics.average_efficiency_pct || 0 }}%</span>
                </div>
                <div class="flex justify-between items-center py-2">
                  <span class="text-sm text-ink-gray-6">Consistency Rating</span>
                  <span class="font-semibold text-ink-gray-8">{{ efficiencyMetrics.consistency_rating || '-' }}</span>
                </div>
              </div>
            </div>

            <!-- Capacity at a Glance -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader title="Capacity at a Glance" :level="3" />
              <div class="space-y-3 mt-4">
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Overall Utilization</span>
                  <span class="font-semibold text-ink-gray-8">
                    {{ capacityUtilization.overall_utilization_pct || 0 }}%
                  </span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Available Capacity</span>
                  <span class="font-semibold text-ink-gray-8">{{ capacityUtilization.available_capacity_pct || 0 }}%</span>
                </div>
                <div class="flex justify-between items-center py-2">
                  <span class="text-sm text-ink-gray-6">Bottlenecks Identified</span>
                  <Badge
                    v-bind="severityBadge((bottleneckAnalysis.bottleneck_count || 0) > 0 ? 'critical' : 'low')"
                    :label="String(bottleneckAnalysis.bottleneck_count || 0)"
                    size="sm"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- OEE Analysis -->
        <div v-if="tabIndex === 1">
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- OEE Score Breakdown -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader title="OEE Score Breakdown" :level="3" />
              <div class="flex items-center justify-center mt-4 mb-6">
                <div class="text-center">
                  <div class="text-6xl font-bold mb-2 text-ink-gray-9">
                    {{ oeeAnalysis.oee_score_pct || 0 }}%
                  </div>
                  <div class="text-lg font-medium text-ink-gray-6">Overall OEE</div>
                  <Badge
                    class="mt-2"
                    v-bind="severityBadge(oeeRatingSeverity(oeeAnalysis.oee_rating))"
                    :label="oeeAnalysis.oee_rating || 'Not Rated'"
                    size="sm"
                  />
                </div>
              </div>
              <div class="space-y-5">
                <div>
                  <div class="flex justify-between text-sm font-medium mb-2">
                    <span class="text-ink-gray-7">Availability</span>
                    <span class="text-ink-gray-8">{{ oeeAnalysis.availability_pct || 0 }}%</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-4">
                    <div
                      class="h-4 rounded-full motion-reduce:transition-none transition-all"
                      :class="severityFill(oeeSeverity(oeeAnalysis.availability_pct))"
                      :style="{ width: (oeeAnalysis.availability_pct || 0) + '%' }"
                      role="img"
                      :aria-label="severityAria('Availability', oeeSeverity(oeeAnalysis.availability_pct), oeeAnalysis.availability_pct + '%')"
                    />
                  </div>
                  <p class="text-xs text-ink-gray-6 mt-1">Actual run time vs planned production time</p>
                </div>
                <div>
                  <div class="flex justify-between text-sm font-medium mb-2">
                    <span class="text-ink-gray-7">Performance</span>
                    <span class="text-ink-gray-8">{{ oeeAnalysis.performance_pct || 0 }}%</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-4">
                    <div
                      class="h-4 rounded-full motion-reduce:transition-none transition-all"
                      :class="severityFill(oeeSeverity(oeeAnalysis.performance_pct))"
                      :style="{ width: (oeeAnalysis.performance_pct || 0) + '%' }"
                      role="img"
                      :aria-label="severityAria('Performance', oeeSeverity(oeeAnalysis.performance_pct), oeeAnalysis.performance_pct + '%')"
                    />
                  </div>
                  <p class="text-xs text-ink-gray-6 mt-1">Actual speed vs ideal speed</p>
                </div>
                <div>
                  <div class="flex justify-between text-sm font-medium mb-2">
                    <span class="text-ink-gray-7">Quality</span>
                    <span class="text-ink-gray-8">{{ oeeAnalysis.quality_pct || 0 }}%</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-4">
                    <div
                      class="h-4 rounded-full motion-reduce:transition-none transition-all"
                      :class="severityFill(oeeSeverity(oeeAnalysis.quality_pct))"
                      :style="{ width: (oeeAnalysis.quality_pct || 0) + '%' }"
                      role="img"
                      :aria-label="severityAria('Quality', oeeSeverity(oeeAnalysis.quality_pct), oeeAnalysis.quality_pct + '%')"
                    />
                  </div>
                  <p class="text-xs text-ink-gray-6 mt-1">Good units vs total units produced</p>
                </div>
              </div>
            </div>

            <!-- Workstation Performance -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader title="Workstation Performance" :level="3" />
              <div v-if="workstationPerformance.length > 0" class="space-y-3 max-h-96 overflow-y-auto mt-4">
                <div
                  v-for="ws in workstationPerformance"
                  :key="ws.workstation"
                  class="border border-outline-gray-1 rounded-lg p-3"
                >
                  <div class="flex justify-between items-center mb-2">
                    <span class="font-medium text-ink-gray-8 text-sm">{{ ws.workstation }}</span>
                    <Badge
                      v-bind="severityBadge(oeeSeverity(ws.efficiency_pct))"
                      :label="`${ws.efficiency_pct || 0}%`"
                      size="sm"
                    />
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-2">
                    <div
                      class="h-2 rounded-full"
                      :class="severityFill(oeeSeverity(ws.efficiency_pct))"
                      :style="{ width: (ws.efficiency_pct || 0) + '%' }"
                      role="img"
                      :aria-label="severityAria('Workstation efficiency', oeeSeverity(ws.efficiency_pct), ws.efficiency_pct + '%')"
                    />
                  </div>
                  <div class="flex justify-between text-xs text-ink-gray-6 mt-1">
                    <span>Jobs: {{ ws.total_jobs || 0 }}</span>
                    <span>Completed: {{ ws.completed_jobs || 0 }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="text-center py-12 text-ink-gray-6 mt-4">
                <p class="text-sm">No workstation data available</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Capacity -->
        <div v-if="tabIndex === 2">
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Capacity Utilization -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader title="Capacity Utilization" :level="3" />
              <div class="space-y-6 mt-4">
                <div class="text-center py-4">
                  <div class="text-5xl font-bold mb-2 text-ink-gray-9">
                    {{ capacityUtilization.overall_utilization_pct || 0 }}%
                  </div>
                  <div class="text-ink-gray-6">Overall Utilization</div>
                  <Badge
                    class="mt-2"
                    v-bind="severityBadge(utilizationSeverity(capacityUtilization.overall_utilization_pct))"
                    :label="severityBadge(utilizationSeverity(capacityUtilization.overall_utilization_pct)).label"
                    size="sm"
                  />
                </div>
                <div class="space-y-3">
                  <div>
                    <div class="flex justify-between text-sm font-medium mb-2">
                      <span class="text-ink-gray-7">Used Capacity</span>
                      <span class="text-ink-gray-8">{{ capacityUtilization.overall_utilization_pct || 0 }}%</span>
                    </div>
                    <div class="w-full bg-surface-gray-2 rounded-full h-5">
                      <div
                        class="h-5 rounded-full motion-reduce:transition-none transition-all"
                        :class="severityFill(utilizationSeverity(capacityUtilization.overall_utilization_pct))"
                        :style="{ width: (capacityUtilization.overall_utilization_pct || 0) + '%' }"
                        role="img"
                        :aria-label="severityAria('Used capacity', utilizationSeverity(capacityUtilization.overall_utilization_pct), capacityUtilization.overall_utilization_pct + '%')"
                      />
                    </div>
                  </div>
                  <div>
                    <div class="flex justify-between text-sm font-medium mb-2">
                      <span class="text-ink-gray-7">Available Capacity</span>
                      <span class="text-ink-gray-8">{{ capacityUtilization.available_capacity_pct || 0 }}%</span>
                    </div>
                    <div class="w-full bg-surface-gray-2 rounded-full h-5">
                      <div
                        class="bg-surface-gray-4 h-5 rounded-full motion-reduce:transition-none transition-all"
                        :style="{ width: (capacityUtilization.available_capacity_pct || 0) + '%' }"
                        role="img"
                        :aria-label="`Available capacity: ${capacityUtilization.available_capacity_pct || 0}%`"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Bottleneck Analysis -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader title="Bottleneck Analysis" :level="3" />
              <div
                class="text-center py-6 border border-outline-gray-1 rounded-lg mb-4 mt-4"
                :class="(bottleneckAnalysis.bottleneck_count || 0) > 0 ? 'bg-surface-gray-2' : 'bg-surface-gray-1'"
              >
                <div class="text-5xl font-bold mb-2 text-ink-gray-9">
                  {{ bottleneckAnalysis.bottleneck_count || 0 }}
                </div>
                <Badge
                  v-bind="severityBadge((bottleneckAnalysis.bottleneck_count || 0) > 0 ? 'critical' : 'low')"
                  :label="(bottleneckAnalysis.bottleneck_count || 0) > 0 ? 'Bottlenecks Identified' : 'No Bottlenecks'"
                  size="sm"
                />
              </div>
              <div v-if="(bottleneckAnalysis.bottlenecks?.length ?? 0) > 0" class="space-y-2">
                <h4 class="text-sm font-medium text-ink-gray-7 mb-2">Affected Workstations</h4>
                <div
                  v-for="b in bottleneckAnalysis.bottlenecks"
                  :key="b.workstation || b.name"
                  class="flex justify-between items-center p-2 bg-surface-gray-2 rounded border border-outline-gray-1"
                >
                  <span class="text-sm text-ink-gray-8">{{ b.workstation || b.name }}</span>
                  <span class="text-xs text-ink-gray-6">{{ b.utilization_pct || b.load_pct || 0 }}% load</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Production Forecast -->
        <div v-if="tabIndex === 3">
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader title="Production Forecast" :level="3" />
              <div v-if="productionForecast && Object.keys(productionForecast).length > 0" class="space-y-3 mt-4">
                <div
                  v-for="(value, key) in productionForecast"
                  :key="key"
                  class="flex justify-between items-center py-2 border-b border-outline-gray-1"
                >
                  <span class="text-sm text-ink-gray-6">{{ formatKey(String(key)) }}</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatValue(value) }}</span>
                </div>
              </div>
              <div v-else class="text-center py-12 text-ink-gray-6 mt-4">
                <p class="text-sm">Forecast data will appear after generating an analysis.</p>
              </div>
            </div>

            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader title="Growth Indicators" :level="3" />
              <div class="space-y-4 mt-4">
                <div class="p-4 rounded-lg bg-surface-gray-1">
                  <div class="text-sm text-ink-gray-6 mb-1">Monthly Growth Rate</div>
                  <div class="text-3xl font-bold text-ink-gray-9">
                    {{ (productionMetrics.monthly_growth_rate || 0) >= 0 ? '+' : '' }}{{ productionMetrics.monthly_growth_rate || 0 }}%
                  </div>
                </div>
                <div class="p-4 bg-surface-gray-1 rounded-lg">
                  <div class="text-sm text-ink-gray-6 mb-1">Total Production Qty</div>
                  <div class="text-3xl font-bold text-ink-gray-9">
                    {{ formatCount(productionMetrics.total_production_qty) }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Recommendations -->
        <div v-if="tabIndex === 4">
          <div v-if="recommendations.length > 0" class="space-y-4">
            <div
              v-for="rec in recommendations"
              :key="rec.recommendation || rec.title"
              class="bg-surface-white rounded-lg border border-outline-gray-1 p-6"
            >
              <div class="flex items-start justify-between mb-3">
                <div class="flex-1">
                  <div class="flex items-center gap-2 mb-2">
                    <Badge
                      v-bind="severityBadge(prioritySeverity(rec.priority))"
                      :label="(rec.priority || 'Medium').toUpperCase()"
                      size="sm"
                    />
                    <span v-if="rec.category" class="text-sm text-ink-gray-6">{{ rec.category }}</span>
                  </div>
                  <h4 class="font-semibold text-ink-gray-8 mb-2">{{ rec.recommendation || rec.title }}</h4>
                  <p v-if="rec.impact" class="text-sm text-ink-gray-6 mb-1">{{ rec.impact }}</p>
                  <p v-if="rec.action" class="text-sm text-ink-gray-6">{{ rec.action }}</p>
                  <p v-if="rec.timeframe" class="text-xs text-ink-gray-5 mt-2">Timeline: {{ rec.timeframe }}</p>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="bg-surface-white rounded-lg border border-outline-gray-1 p-12 text-center text-ink-gray-6">
            <p class="text-sm">No recommendations available. Refresh to generate insights.</p>
          </div>
        </div>

      </div>
    </IntelligenceDashboardShell>

    <!-- AI Chat Button -->
    <DashboardChatButton
      dashboard-type="Manufacturing"
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
