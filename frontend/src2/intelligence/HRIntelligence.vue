<script setup lang="ts">
defineOptions({ name: 'HRIntelligence' })
import { Badge, Button, Select, Tabs } from 'frappe-ui'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Users, UserMinus, DollarSign, Building2,
  Target, Zap, PieChart, AlertTriangle,
} from 'lucide-vue-next'
import { useIntelligenceDashboard } from './composables/useIntelligenceDashboard'
import {
  severityBadge, deltaInk, deltaGlyph, ragSeverity, scoreSeverity,
  type Severity,
} from '../utils/status'
import { formatCount, formatMoney } from '../utils/format'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import { useDrillDown } from './composables/useDrillDown'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'
import KpiCard from './components/KpiCard.vue'
import IntelligenceDashboardShell from './components/IntelligenceDashboardShell.vue'
import SectionHeader from './components/SectionHeader.vue'
import SkeletonBlock from './components/SkeletonBlock.vue'

// ─── Payload interfaces (confirmed against insights/ml/hr_intelligence.py) ───

interface HeadcountMetrics {
  total_employees?: number
  new_hires?: number
  exits?: number
  net_growth?: number
  growth_rate_pct?: number
  turnover_rate_pct?: number
  hire_rate_pct?: number
  largest_department?: string
  smallest_department?: string
  department_count?: number
  headcount_health?: string
}

interface AttritionMetrics {
  attrition_rate_pct?: number
  total_exits?: number
  voluntary_exits?: number
  involuntary_exits?: number
  voluntary_rate_pct?: number
  involuntary_rate_pct?: number
  attrition_risk_level?: string
  benchmark_comparison?: string
  /** [INFERENCE] Not returned by Python _analyze_attrition; guarded by || undefined in kpis. */
  attrition_change?: number
}

interface PayrollMetrics {
  total_payroll_cost?: number
  average_salary?: number
  cost_per_employee?: number
  employees_on_payroll?: number
  deduction_rate_pct?: number
  payroll_efficiency?: string
}

interface EngagementIndicators {
  engagement_score?: number
  engagement_level?: string
}

interface DeptValues {
  headcount?: number
  count?: number
  payroll_cost?: number
  cost_per_employee?: number
  avg_cost?: number
}

interface DepartmentHealth {
  department_metrics?: Record<string, DeptValues>
  highest_cost_department?: string
  largest_department?: string
  total_departments?: number
  message?: string
}

interface CompensationAnalysis {
  median_salary?: number
  salary_variance?: number
  highest_paying_dept?: string
  lowest_paying_dept?: string
  pay_ratio?: number
  pay_equity_status?: string
}

interface AttritionRisk {
  risk_level?: string
  risk_score?: number
  risk_factors?: string[]
  predicted_attrition_rate?: number
  recommended_actions?: string[]
}

interface HiringForecast {
  projected_exits_next_quarter?: number
  growth_based_hiring?: number
  total_hiring_need?: number
  hiring_urgency?: string
}

/** Recommendation item from _generate_hr_recommendations.
 *  Python returns priority/category/title/description/actions[].
 *  Template also accesses impact (guarded by v-if) which is not in the Python source. */
interface HRRecommendation {
  priority?: string
  category?: string
  title?: string
  description?: string
  actions?: string[]
  impact?: string  // [INFERENCE] not in Python source; guarded by v-if in template
}

/** Row in workforce_composition.employment_type_distribution.
 *  API returns employment_type or type (both optional; exactly one is present). */
interface EmploymentTypeRow {
  employment_type?: string
  type?: string
  count: number
}

/** Row in workforce_composition.department_distribution. */
interface DepartmentDistRow {
  department: string
  count: number
}

interface WorkforceComposition {
  department_distribution?: DepartmentDistRow[]
  employment_type_distribution?: EmploymentTypeRow[]
  gender_ratios?: Record<string, number>
  diversity_score?: number
  composition_balance?: string
}

/** Top-level payload for insights.api.ml.get_hr_overview */
interface HRPayload {
  period?: string
  generated_at?: string
  /** Company reporting currency. Sent so payroll figures are never labelled by a literal. */
  base_currency?: string
  company?: string
  headcount_metrics?: HeadcountMetrics
  attrition_metrics?: AttritionMetrics
  payroll_metrics?: PayrollMetrics
  attendance_metrics?: Record<string, unknown>
  leave_metrics?: Record<string, unknown>
  workforce_composition?: WorkforceComposition
  department_health?: DepartmentHealth
  compensation_analysis?: CompensationAnalysis
  engagement_indicators?: EngagementIndicators
  attrition_risk?: AttritionRisk
  hiring_forecast?: HiringForecast
  recommendations?: HRRecommendation[]
  raw_data?: Record<string, unknown>
}

// ─── State ───────────────────────────────────────────────────────────────────

const router = useRouter()
const HR_ENDPOINT = 'insights.api.ml.hr.get_hr_detail'
const drillDown = useDrillDown()

const period = ref('TTM')
const periods = [
  { value: 'MTD', label: 'Month to Date' },
  { value: 'QTD', label: 'Quarter to Date' },
  { value: 'YTD', label: 'Year to Date' },
  { value: 'TTM', label: 'Trailing 12 Months' },
]

const tabIndex = ref(0)
const tabs = [
  { label: 'Workforce Overview' },
  { label: 'Attrition & Retention' },
  { label: 'Payroll & Compensation' },
  { label: 'Department Health' },
  { label: 'Workforce Planning' },
]

const params = computed(() => ({ period: period.value as string }))

const { data, loading, refreshing, error, isPermissionError, hasData, reload, retry } =
  useIntelligenceDashboard<HRPayload>({
    url: 'insights.api.ml.get_hr_overview',
    params,
    cache: 'hr-intelligence',
  })

// Computed KPIs
const kpis = computed(() => {
  if (!data.value) return []
  const hc = data.value.headcount_metrics ?? ({} as HeadcountMetrics)
  const att = data.value.attrition_metrics ?? ({} as AttritionMetrics)
  const pay = data.value.payroll_metrics ?? ({} as PayrollMetrics)
  const eng = data.value.engagement_indicators ?? ({} as EngagementIndicators)

  return [
    {
      label: 'Total Headcount',
      value: formatCount(hc.total_employees),
      sublabel: `${hc.new_hires || 0} new hires, ${hc.exits || 0} exits`,
      delta: hc.growth_rate_pct || undefined,
      deltaHigherIsBetter: true,
      drillable: true,
      metric: 'total_employees',
    },
    {
      label: 'Attrition Rate',
      value: `${(att.attrition_rate_pct || 0).toFixed(1)}%`,
      sublabel: `${att.total_exits || 0} exits (${att.voluntary_exits || 0} voluntary)`,
      delta: att.attrition_change || undefined,
      // Higher attrition is worse
      deltaHigherIsBetter: false,
      severity: scoreSeverity(att.attrition_rate_pct, { good: 10, warn: 15, higherIsBetter: false }) as Severity,
      drillable: false,
      metric: undefined as string | undefined,
    },
    {
      label: 'Avg. Salary',
      value: formatCurrency(pay.average_salary || 0),
      sublabel: `Total: ${formatCurrency(pay.total_payroll_cost || 0)}`,
      drillable: false,
      metric: undefined,
    },
    {
      label: 'Engagement Score',
      value: `${(eng.engagement_score || 0).toFixed(0)}/100`,
      sublabel: eng.engagement_level || undefined,
      severity: scoreSeverity(eng.engagement_score, { good: 75, warn: 50, higherIsBetter: true }) as Severity,
      drillable: false,
      metric: undefined,
    },
  ]
})

const departments = computed(() => {
  if (!data.value?.department_health) return []
  const dh = data.value.department_health
  // department_metrics is a dict of dept → {headcount, payroll_cost, cost_per_employee}
  const metrics = dh.department_metrics
  if (!metrics) return []
  return Object.entries(metrics).map(([name, val]) => ({
    department: name,
    headcount: val.headcount || val.count || 0,
    payroll_cost: val.payroll_cost || 0,
    cost_per_employee: val.cost_per_employee || val.avg_cost || 0,
  }))
})

const composition = computed(() => {
  if (!data.value?.workforce_composition) return null
  const wc = data.value.workforce_composition
  return {
    gender: wc.gender_ratios ?? null,
    employment_type: wc.employment_type_distribution
      ? Object.fromEntries(
          wc.employment_type_distribution.map((e): [string, number] => [e.employment_type || e.type || '', e.count]),
        )
      : null,
    departments: wc.department_distribution
      ? Object.fromEntries(
          wc.department_distribution.map((e): [string, number] => [e.department, e.count]),
        )
      : null,
  }
})

const attritionRisk = computed(() => data.value?.attrition_risk ?? null)
const recommendations = computed(() => data.value?.recommendations ?? ([] as HRRecommendation[]))

/** Map attrition/HR risk text level to Severity. */
function riskLevelSeverity(level: string | undefined): Severity {
  if (level === 'high') return ragSeverity('red')
  if (level === 'medium') return ragSeverity('amber')
  return ragSeverity('green')
}

/** Map hiring urgency to Severity. */
function urgencySeverity(urgency: string | undefined): Severity {
  if (urgency === 'high') return 'critical'
  if (urgency === 'medium') return 'medium'
  return 'low'
}

/**
 * Currency comes from the payload, never a literal.
 *
 * This previously hardcoded "KES" in nine places and returned "KES 0" for a
 * falsy value, so on a site reporting in anything else every payroll figure on
 * the page was mislabelled, and a missing one was reported as zero money. The
 * endpoint now sends `base_currency` like the other seven do.
 */
const baseCurrency = computed(() => data.value?.base_currency ?? null)

function formatCurrency(value: number | null | undefined) {
  return formatMoney(value, baseCurrency.value, { compact: true })
}

function handleChatNavigation(path: string) {
  router.push(path)
}
</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <header class="bg-surface-white border-b px-6 py-4">
      <div class="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="text-2xl font-bold text-ink-gray-9">HR Intelligence</h1>
          <p class="text-sm text-ink-gray-6 mt-1">Workforce analytics, talent management, organisational health</p>
        </div>
        <div class="flex items-center gap-3">
          <Select v-model="period" :options="periods" />
          <Button variant="subtle" :loading="refreshing" @click="reload">Refresh</Button>
        </div>
      </div>
    </header>

    <IntelligenceDashboardShell
      :loading="loading"
      :refreshing="refreshing"
      :error="error"
      :is-permission-error="isPermissionError"
      :has-data="hasData"
      subject="HR data"
      permission-hint="Ask an administrator for Employee read access."
      @retry="retry"
    >
      <!-- Four, not the default six: matching the real strip below so the
           skeleton does not reflow the page when data lands. -->
      <template #skeleton>
        <div class="p-6 grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard v-for="n in 4" :key="n" label="" value="" loading />
        </div>
        <div class="p-6 space-y-3">
          <SkeletonBlock class="h-8 w-48" />
          <SkeletonBlock class="h-64 w-full rounded-lg" />
        </div>
      </template>

      <!-- KPI Cards -->
      <div class="p-6 grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          v-for="kpi in kpis"
          :key="kpi.label"
          :label="kpi.label"
          :value="kpi.value"
          :delta="kpi.delta"
          :delta-higher-is-better="kpi.deltaHigherIsBetter"
          :sublabel="kpi.sublabel"
          :severity="kpi.severity"
          :loading="!hasData"
          :clickable="!!kpi.drillable"
          @click="kpi.drillable && drillDown.open(HR_ENDPOINT, kpi.label, { metric: kpi.metric ?? '' })"
        />
      </div>

      <!-- Tab strip -->
      <div class="mx-6">
        <Tabs v-model="tabIndex" :tabs="tabs" />
      </div>

      <!-- Tab content -->
      <div class="p-6">

        <!-- Workforce Overview -->
        <div v-show="tabIndex === 0" class="space-y-6">
          <!-- Workforce Composition -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader title="Workforce Composition" :level="3" />
            <div v-if="hasData && composition" class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
              <!-- By Gender -->
              <div v-if="composition.gender" class="bg-surface-gray-1 rounded-lg p-4">
                <h4 class="text-sm font-medium text-ink-gray-7 mb-3">By Gender</h4>
                <div class="space-y-2">
                  <div v-for="(pct, gender) in composition.gender" :key="gender as string"
                    class="flex justify-between items-center">
                    <span class="text-sm text-ink-gray-6 capitalize">{{ gender }}</span>
                    <span class="text-sm font-medium text-ink-gray-8">{{ pct }}%</span>
                  </div>
                </div>
              </div>
              <!-- By Employment Type -->
              <div v-if="composition.employment_type" class="bg-surface-gray-1 rounded-lg p-4">
                <h4 class="text-sm font-medium text-ink-gray-7 mb-3">By Type</h4>
                <div class="space-y-2">
                  <button
                    v-for="(count, type) in composition.employment_type"
                    :key="type as string"
                    class="flex justify-between items-center w-full text-left hover:bg-surface-gray-2 rounded px-1 -mx-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 motion-reduce:transition-none transition-colors"
                    @click="drillDown.open(HR_ENDPOINT, type + ' Employees', { metric: 'employment_type', employment_type: type })"
                  >
                    <span class="text-sm text-ink-gray-6 capitalize">{{ type }}</span>
                    <span class="text-sm font-medium text-ink-gray-8">{{ count }}</span>
                  </button>
                </div>
              </div>
              <!-- By Department -->
              <div v-if="composition.departments" class="bg-surface-gray-1 rounded-lg p-4">
                <h4 class="text-sm font-medium text-ink-gray-7 mb-3">By Department</h4>
                <div class="space-y-2">
                  <div v-for="(count, dept) in composition.departments" :key="dept as string"
                    class="flex justify-between items-center">
                    <span class="text-sm text-ink-gray-6">{{ dept }}</span>
                    <span class="text-sm font-medium text-ink-gray-8">{{ count }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-else-if="hasData" class="text-center py-8 text-ink-gray-6 mt-4">
              <PieChart class="w-8 h-8 mx-auto mb-2 text-ink-gray-5" aria-hidden="true" />
              <p>No composition data available</p>
            </div>
            <div v-else class="space-y-3 mt-4">
              <SkeletonBlock v-for="n in 3" :key="n" class="h-20 w-full" />
            </div>
          </div>

          <!-- Headcount Metrics -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader title="Headcount Metrics" :level="3" />
            <div v-if="hasData && data?.headcount_metrics" class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
              <!--
                `|| 0` previously stood in for every one of these fields, so a
                payload that omitted `new_hires` reported zero hires rather than
                an absent figure. The tile shows a dash instead.
              -->
              <KpiCard variant="tile" label="Total Employees" :value="data.headcount_metrics.total_employees" />
              <KpiCard variant="tile" label="New Hires" :value="data.headcount_metrics.new_hires" />
              <KpiCard variant="tile" label="Exits" :value="data.headcount_metrics.exits" />
              <!-- Signed rather than glyph-plus-absolute: a leading minus is
                   unambiguous without relying on colour, which was never an
                   accessible signal on its own. -->
              <KpiCard variant="tile" label="Net Growth" :value="data.headcount_metrics.net_growth" />
            </div>
          </div>
        </div>

        <!-- Attrition & Retention -->
        <div v-show="tabIndex === 1" class="space-y-6">
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader title="Attrition Analysis" :level="3" />
            <div v-if="hasData && data?.attrition_metrics" class="grid grid-cols-1 md:grid-cols-4 gap-4 mt-4">
              <KpiCard
                variant="tile"
                label="Attrition Rate"
                :percent="data.attrition_metrics.attrition_rate_pct"
              />
              <KpiCard variant="tile" label="Total Exits" :value="data.attrition_metrics.total_exits" />
              <KpiCard
                variant="tile"
                label="Voluntary Exits"
                :value="data.attrition_metrics.voluntary_exits"
              />
              <div class="bg-surface-gray-1 rounded-lg p-4 text-center">
                <p class="text-sm text-ink-gray-6 font-medium">Risk Level</p>
                <Badge
                  class="mt-2"
                  v-bind="severityBadge(riskLevelSeverity(data.attrition_metrics.attrition_risk_level))"
                  :label="(data.attrition_metrics.attrition_risk_level || 'N/A').toUpperCase()"
                  size="sm"
                />
              </div>
            </div>
          </div>

          <!-- Attrition Risk Assessment -->
          <div v-if="hasData && attritionRisk" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader title="Attrition Risk Assessment" :level="3" />
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
              <div class="rounded-lg p-4 text-center bg-surface-gray-1">
                <p class="text-sm font-medium text-ink-gray-6">Overall Risk Level</p>
                <Badge
                  class="mt-2"
                  v-bind="severityBadge(riskLevelSeverity(attritionRisk.risk_level))"
                  :label="(attritionRisk.risk_level || 'N/A').toUpperCase()"
                  size="sm"
                />
                <p class="text-xs text-ink-gray-6 mt-2">Score: {{ attritionRisk.risk_score || 0 }}/100</p>
              </div>
              <KpiCard
                variant="tile"
                label="Predicted Attrition"
                :percent="attritionRisk.predicted_attrition_rate"
                sublabel="next period"
              />
              <div class="bg-surface-gray-1 rounded-lg p-4">
                <p class="text-sm font-medium text-ink-gray-7 mb-2">Risk Factors</p>
                <div v-if="attritionRisk.risk_factors?.length" class="space-y-1">
                  <div v-for="(factor, i) in attritionRisk.risk_factors" :key="i" class="flex items-start gap-2">
                    <AlertTriangle class="w-3 h-3 text-ink-gray-5 mt-0.5 flex-shrink-0" aria-hidden="true" />
                    <span class="text-xs text-ink-gray-6">{{ factor }}</span>
                  </div>
                </div>
                <p v-else class="text-xs text-ink-gray-6">No significant risk factors</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Payroll & Compensation -->
        <div v-show="tabIndex === 2" class="space-y-6">
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader title="Payroll Summary" :level="3" />
            <div v-if="hasData && data?.payroll_metrics" class="grid grid-cols-1 md:grid-cols-4 gap-4 mt-4">
              <!-- `amount` + `currency` rather than a pre-formatted string, so
                   the tile picks compact notation on a phone and an absent cost
                   cannot render as zero money. -->
              <KpiCard
                variant="tile"
                label="Total Payroll"
                :amount="data.payroll_metrics.total_payroll_cost"
                :currency="baseCurrency"
              />
              <KpiCard
                variant="tile"
                label="Avg Salary"
                :amount="data.payroll_metrics.average_salary"
                :currency="baseCurrency"
              />
              <KpiCard
                variant="tile"
                label="Cost Per Employee"
                :amount="data.payroll_metrics.cost_per_employee"
                :currency="baseCurrency"
              />
              <KpiCard
                variant="tile"
                label="Deduction Rate"
                :percent="data.payroll_metrics.deduction_rate_pct"
              />
            </div>
          </div>

          <!-- Compensation Analysis -->
          <div v-if="hasData && data?.compensation_analysis" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader title="Compensation Analysis" :level="3" />
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
              <div class="bg-surface-gray-1 rounded-lg p-4">
                <h4 class="text-sm font-medium text-ink-gray-7 mb-3">Key Metrics</h4>
                <div class="space-y-2">
                  <div class="flex justify-between items-center">
                    <span class="text-sm text-ink-gray-6">Median Salary</span>
                    <span class="text-sm font-medium text-ink-gray-8">{{ formatCurrency(data.compensation_analysis.median_salary || 0) }}</span>
                  </div>
                  <div class="flex justify-between items-center">
                    <span class="text-sm text-ink-gray-6">Pay Ratio (High/Low)</span>
                    <span class="text-sm font-medium text-ink-gray-8">{{ (data.compensation_analysis.pay_ratio || 0).toFixed(1) }}x</span>
                  </div>
                  <div class="flex justify-between items-center">
                    <span class="text-sm text-ink-gray-6">Highest Paying Dept</span>
                    <span class="text-sm font-medium text-ink-gray-8">{{ data.compensation_analysis.highest_paying_dept || 'N/A' }}</span>
                  </div>
                  <div class="flex justify-between items-center">
                    <span class="text-sm text-ink-gray-6">Lowest Paying Dept</span>
                    <span class="text-sm font-medium text-ink-gray-8">{{ data.compensation_analysis.lowest_paying_dept || 'N/A' }}</span>
                  </div>
                  <div class="flex justify-between items-center">
                    <span class="text-sm text-ink-gray-6">Pay Equity</span>
                    <Badge
                      v-bind="severityBadge(data.compensation_analysis.pay_equity_status === 'good' ? 'low' : 'medium')"
                      :label="(data.compensation_analysis.pay_equity_status || 'N/A').replace('_', ' ')"
                      size="sm"
                    />
                  </div>
                </div>
              </div>
              <div class="bg-surface-gray-1 rounded-lg p-4">
                <h4 class="text-sm font-medium text-ink-gray-7 mb-3">Salary Variance</h4>
                <p class="text-3xl font-bold text-ink-gray-9">{{ formatCurrency(data.compensation_analysis.salary_variance || 0) }}</p>
                <p class="text-xs text-ink-gray-6 mt-1">Standard deviation across departments</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Department Health -->
        <div v-show="tabIndex === 3" class="space-y-6">
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader title="Department Overview" :level="3" />
            <div v-if="hasData && departments.length > 0" class="space-y-3 mt-4">
              <button
                v-for="dept in departments"
                :key="dept.department"
                class="flex items-center justify-between w-full p-4 bg-surface-gray-1 rounded-lg text-left hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 motion-reduce:transition-none transition-colors"
                @click="drillDown.open(HR_ENDPOINT, dept.department + ' Employees', { metric: 'dept_employees', department: dept.department })"
              >
                <div class="flex-1">
                  <div class="flex items-center gap-3">
                    <Building2 class="w-5 h-5 text-ink-gray-5" aria-hidden="true" />
                    <div>
                      <p class="text-sm font-medium text-ink-gray-8">{{ dept.department }}</p>
                      <p class="text-xs text-ink-gray-6">{{ dept.headcount }} employees</p>
                    </div>
                  </div>
                </div>
                <div class="flex items-center gap-4">
                  <div class="text-right">
                    <p class="text-xs text-ink-gray-6">Payroll Cost</p>
                    <p class="text-sm font-medium text-ink-gray-8">{{ formatCurrency(dept.payroll_cost || 0) }}</p>
                  </div>
                  <div class="text-right">
                    <p class="text-xs text-ink-gray-6">Cost/Employee</p>
                    <p class="text-sm font-medium text-ink-gray-8">{{ formatCurrency(dept.cost_per_employee || 0) }}</p>
                  </div>
                </div>
              </button>
            </div>
            <div v-else-if="hasData" class="text-center py-8 text-ink-gray-6 mt-4">
              <Building2 class="w-8 h-8 mx-auto mb-2 text-ink-gray-5" aria-hidden="true" />
              <p>No department data available</p>
            </div>
            <div v-else class="space-y-3 mt-4">
              <SkeletonBlock v-for="n in 4" :key="n" class="h-16 w-full" />
            </div>
          </div>
        </div>

        <!-- Workforce Planning -->
        <div v-show="tabIndex === 4" class="space-y-6">
          <!-- Hiring Forecast -->
          <div v-if="hasData && data?.hiring_forecast" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader title="Hiring Forecast" :level="3" />
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mt-4">
              <KpiCard
                variant="tile"
                label="Total Hiring Need"
                :value="data.hiring_forecast.total_hiring_need"
              />
              <KpiCard
                variant="tile"
                label="Projected Exits"
                :value="data.hiring_forecast.projected_exits_next_quarter"
              />
              <KpiCard
                variant="tile"
                label="Growth-Based Hires"
                :value="data.hiring_forecast.growth_based_hiring"
              />
              <div class="bg-surface-gray-1 rounded-lg p-4 text-center">
                <p class="text-sm text-ink-gray-6 font-medium">Urgency</p>
                <Badge
                  class="mt-2"
                  v-bind="severityBadge(urgencySeverity(data.hiring_forecast.hiring_urgency))"
                  :label="(data.hiring_forecast.hiring_urgency || 'Normal').toUpperCase()"
                  size="sm"
                />
              </div>
            </div>
          </div>

          <!-- Recommendations -->
          <div v-if="hasData && recommendations.length > 0" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader title="Recommendations" :level="3" />
            <div class="space-y-3 mt-4">
              <div v-for="(rec, i) in recommendations" :key="i"
                class="flex items-start gap-3 p-3 bg-surface-gray-1 rounded-lg">
                <Zap class="w-5 h-5 text-ink-gray-5 flex-shrink-0 mt-0.5" aria-hidden="true" />
                <div>
                  <p class="text-sm font-medium text-ink-gray-8">{{ rec.title || rec }}</p>
                  <p v-if="rec.description" class="text-xs text-ink-gray-6 mt-1">{{ rec.description }}</p>
                  <p v-if="rec.impact" class="text-xs text-ink-gray-6 mt-1">Impact: {{ rec.impact }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </IntelligenceDashboardShell>

    <DashboardChatButton
      dashboard-type="HR"
      :dashboard-context="{ dashboard: 'HR Intelligence', data: data }"
      @navigate-dashboard="handleChatNavigation"
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
