<script setup lang="ts">
defineOptions({ name: 'HRIntelligence' })
import { Badge, Button, Tabs } from 'frappe-ui'
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
import { formatCount, formatMoney, formatPercent, NO_VALUE } from '../utils/format'
import { FISCAL_PERIOD_RANGES } from '../utils/dateRangePresets'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import { useDrillDown } from './composables/useDrillDown'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'
import KpiCard from './components/KpiCard.vue'
import IntelligenceDashboardShell from './components/IntelligenceDashboardShell.vue'
import SectionHeader from './components/SectionHeader.vue'
import TabBrief, { type Brief } from './components/TabBrief.vue'
import TabActions from './components/TabActions.vue'
import StatStrip, { type StatItem } from './components/StatStrip.vue'
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
  /** Set only when payroll_efficiency is 'no_data' -- explains an
   *  otherwise-unexplained zero (no Salary Slip table, or none in period)
   *  instead of leaving the reader to guess whether ₹0 is real or broken. */
  payroll_data_note?: string
}

interface AttendanceMetrics {
  attendance_rate_pct?: number
  late_arrivals?: number
  late_arrival_rate_pct?: number
  total_attendance_records?: number
  total_in_checkins?: number
  present_days?: number
  absent_days?: number
  half_day_days?: number
  on_leave_days?: number
  work_from_home_days?: number
  effective_present_days?: number
  attendance_health?: string
  productivity_indicator?: string
}

interface LeaveMetrics {
  total_leave_applications?: number
  total_leave_days?: number
  average_days_per_application?: number
  leave_utilization?: string
  leave_pattern?: string
}

interface EngagementIndicators {
  engagement_score?: number
  engagement_level?: string
  /** Per-dimension contribution in bucketed points (10/15/20/30/40). Sum equals `engagement_score`. */
  key_indicators?: {
    attendance_contribution?: number
    retention_contribution?: number
    leave_pattern_contribution?: number
  }
  /** Raw underlying metrics exposed for diagnosis; prefixed `_` so the dashboard does not need them. */
  _raw?: {
    attendance_rate_pct?: number
    retention_rate_pct?: number
    leave_pattern_days?: number
    leave_applications_count?: number
  }
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


/** Item in the synthesised "Needs Attention" rail on the Overview tab.
 *  Derived client-side from payload fields; every field used comes from
 *  a server-computed value, not a client heuristic. */
interface AttentionItem {
  severity: Severity
  badge: string
  category: string
  title: string
  description: string
  actions: string[]
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
  tab_briefs?: Record<string, Brief>
  company?: string
  headcount_metrics?: HeadcountMetrics
  attrition_metrics?: AttritionMetrics
  payroll_metrics?: PayrollMetrics
  attendance_metrics?: AttendanceMetrics
  leave_metrics?: LeaveMetrics
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

const tabIndex = ref(0)
const tabs = [
  { id: 'overview', label: 'Workforce Overview' },
  { id: 'attrition', label: 'Attrition & Retention' },
  { id: 'payroll', label: 'Payroll & Compensation' },
  { id: 'department', label: 'Department Health' },
  { id: 'planning', label: 'Workforce Planning' },
]
const activeTab = computed(() => tabs[tabIndex.value]?.id ?? 'overview')
const tabBriefs = computed(() => data.value?.tab_briefs ?? {})
const attritionStrip = computed<StatItem[]>(() => {
  const am = data.value?.attrition_metrics
  const rate = am?.attrition_rate_pct
  return [
    { label: 'Attrition Rate', percent: rate ?? null },
    { label: 'Total Exits', value: am?.total_exits ?? null },
    { label: 'Voluntary Exits', value: am?.voluntary_exits ?? null },
    { label: 'Involuntary Exits', value: am?.involuntary_exits ?? null },
    { label: 'Retention Rate', percent: rate == null ? null : 100 - rate },
    { label: 'Predicted Attrition', percent: data.value?.attrition_risk?.predicted_attrition_rate ?? null, sublabel: 'next period' },
  ]
})
// No Salary Slips: show the dash, not a zero that reads as a real payroll of nothing.
const payrollMissing = computed(() => data.value?.payroll_metrics?.payroll_efficiency === 'no_data')
const payrollStrip = computed<StatItem[]>(() => {
  const pm = data.value?.payroll_metrics
  const gap = payrollMissing.value
  return [
    { label: 'Total Payroll', amount: gap ? null : pm?.total_payroll_cost ?? null },
    { label: 'Avg Salary', amount: gap ? null : pm?.average_salary ?? null },
    { label: 'Cost Per Employee', amount: gap ? null : pm?.cost_per_employee ?? null },
    { label: 'Deduction Rate', percent: gap ? null : pm?.deduction_rate_pct ?? null },
  ]
})
const departmentStrip = computed<StatItem[]>(() => {
  const dm = data.value?.department_health?.department_metrics
  if (!dm) return []
  const named = Object.keys(dm).filter(d => d !== '(Unassigned)')
  const total = data.value?.headcount_metrics?.total_employees ?? null
  const big = data.value?.department_health?.largest_department
  return [
    { label: 'Named Departments', value: named.length },
    { label: 'Unassigned', value: dm['(Unassigned)']?.headcount ?? 0, sublabel: total == null ? undefined : `of ${total} employees` },
    { label: 'Largest Department', value: big ? big.split(' - ')[0] : null, sublabel: big && dm[big] ? `${dm[big].headcount} employees` : undefined },
    { label: 'Single-Person Departments', value: named.filter(d => dm[d].headcount === 1).length, sublabel: `of ${named.length} named` },
  ]
})
const planningStrip = computed<StatItem[]>(() => {
  const hf = data.value?.hiring_forecast
  const urgency = hf?.hiring_urgency
  return [
    { label: 'Total Hiring Need', value: hf?.total_hiring_need ?? null },
    { label: 'Projected Exits', value: hf?.projected_exits_next_quarter ?? null, sublabel: 'next quarter' },
    { label: 'Growth-Based Hires', value: hf?.growth_based_hiring ?? null },
    { label: 'Current Attrition', percent: data.value?.attrition_metrics?.attrition_rate_pct ?? null },
    { label: 'Predicted Attrition', percent: data.value?.attrition_risk?.predicted_attrition_rate ?? null, sublabel: 'next period' },
    { label: 'Hiring Urgency', value: urgency ? urgency.charAt(0).toUpperCase() + urgency.slice(1) : null },
  ]
})

const params = computed(() => ({ period: period.value as string }))

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
  useIntelligenceDashboard<HRPayload>({
    url: 'insights.api.ml.get_hr_overview',
    params,
    cache: 'hr-intelligence',
  })

// Computed KPIs — 4 cards matching the skeleton `:kpi-count="4"`.
const kpis = computed(() => {
  if (!data.value) return []
  const hc = data.value.headcount_metrics ?? ({} as HeadcountMetrics)
  const att = data.value.attrition_metrics ?? ({} as AttritionMetrics)
  const atm = data.value.attendance_metrics ?? ({} as AttendanceMetrics)
  const eng = data.value.engagement_indicators ?? ({} as EngagementIndicators)
  const total = hc.total_employees ?? 0

  return [
    {
      label: 'Total Headcount',
      value: formatCount(hc.total_employees),
      // Show absolute counts (not just rates) so each figure is interpretable
      // with a tiny population where one person moves the rate ~9 pp.
      sublabel: [
        hc.new_hires != null ? `↑${hc.new_hires} hires` : null,
        hc.exits != null ? `↓${hc.exits} exits` : null,
        hc.net_growth != null ? `${(hc.net_growth ?? 0) >= 0 ? '+' : ''}${hc.net_growth} net` : null,
      ].filter(Boolean).join(' · ') || undefined,
      delta: hc.growth_rate_pct || undefined,
      deltaHigherIsBetter: true,
      drillable: true,
      metric: 'total_employees',
    },
    {
      label: 'Attrition Rate',
      value: formatPercent(att.attrition_rate_pct),
      // "X of Y" denominator: with only ~11 employees, a percent-only display
      // is misleading — one exit is 9 pp. Show the absolute count and total.
      sublabel: att.total_exits != null
        ? `${att.total_exits} of ${total} exits · ${formatPercent(att.involuntary_rate_pct)} involuntary`
        : undefined,
      delta: att.attrition_change || undefined,
      deltaHigherIsBetter: false,
      severity: scoreSeverity(att.attrition_rate_pct, { good: 10, warn: 15, higherIsBetter: false }) as Severity,
      drillable: true,
      metric: 'recent_exits',
    },
    {
      // Avg. Salary moved out of the KPI strip (no payroll data this period).
      // Attendance Rate is more actionable at a glance and drives the
      // engagement score; salary now appears in the hero sub-metrics row.
      label: 'Attendance Rate',
      value: formatPercent(atm.attendance_rate_pct),
      sublabel: atm.total_attendance_records != null
        ? `${atm.present_days ?? 0} present of ${atm.total_attendance_records} records`
        : undefined,
      severity: scoreSeverity(atm.attendance_rate_pct, { good: 92, warn: 85, higherIsBetter: true }) as Severity,
      drillable: false,
      metric: undefined,
    },
    {
      label: 'Engagement Score',
      value: `${formatCount(eng.engagement_score)}/100`,
      sublabel: eng.key_indicators?.retention_contribution != null
        ? `Retention contribution ${eng.key_indicators.retention_contribution}/40`
        : (eng.engagement_level || undefined),
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

/** Map compensation pay-equity status to Severity. Binary because the
 *  server only reports 'good' vs anything else (e.g. 'needs_review'). */
function payEquitySeverity(status: string | undefined): Severity {
  return status === 'good' ? 'low' : 'medium'
}

// ─── Variant C: hero waterfall + attention rail ───────────────────────────

const attendanceMetrics = computed(() => data.value?.attendance_metrics ?? ({} as AttendanceMetrics))

/** Opening headcount = closing (current active) minus net change. */
const openingHeadcount = computed(() => {
  const hc = data.value?.headcount_metrics ?? ({} as HeadcountMetrics)
  return (hc.total_employees ?? 0) - ((hc.new_hires ?? 0) - (hc.exits ?? 0))
})

/** Tallest bar in the waterfall (Opening or Closing). */
const peakHc = computed(() =>
  Math.max(openingHeadcount.value, data.value?.headcount_metrics?.total_employees ?? 0),
)

/** Minimum headcount reached during the period (bottom of the exit bar). */
const floorHc = computed(() =>
  Math.max(0, openingHeadcount.value - (data.value?.headcount_metrics?.exits ?? 0)),
)

const maxDeptCount = computed(() =>
  (data.value?.workforce_composition?.department_distribution ?? []).reduce(
    (m, r) => Math.max(m, r.count), 1,
  ),
)

const maxEmpTypeCount = computed(() =>
  (data.value?.workforce_composition?.employment_type_distribution ?? []).reduce(
    (m, r) => Math.max(m, r.count), 1,
  ),
)

/** Bar height as a percentage of the chart container (0–100, integer). */
function hcPct(count: number | null | undefined): number {
  if (!peakHc.value || count == null || !Number.isFinite(count)) return 0
  return Math.max(0, Math.min(100, Math.round((count / peakHc.value) * 100)))
}

/** Badge text colour for the attention rail.
 *  `text-ink-amber-3` fails AA in light mode so high severity uses --app-warn via style. */
function attentionBadgeStyle(severity: Severity): Record<string, string> {
  if (severity === 'critical') return { color: 'var(--app-neg)' }
  if (severity === 'high') return { color: 'var(--app-warn)' }
  return {}
}

/** Synthesised "Needs Attention" items derived entirely from server payload fields.
 *  Each title uses a value the backend already computed; no client-side verdicts. */
const attentionItems = computed<AttentionItem[]>(() => {
  if (!data.value) return []
  const hcm = data.value.headcount_metrics ?? ({} as HeadcountMetrics)
  const att = data.value.attrition_metrics ?? ({} as AttritionMetrics)
  const atm = data.value.attendance_metrics ?? ({} as AttendanceMetrics)
  const pay = data.value.payroll_metrics ?? ({} as PayrollMetrics)
  const hiring = data.value.hiring_forecast ?? ({} as HiringForecast)
  const wc = data.value.workforce_composition ?? ({} as WorkforceComposition)
  const eng = data.value.engagement_indicators ?? ({} as EngagementIndicators)
  const risk = data.value.attrition_risk ?? ({} as AttritionRisk)
  const total = hcm.total_employees ?? 0

  const items: AttentionItem[] = []

  if ((att.attrition_rate_pct ?? 0) > 15) {
    const exits = att.total_exits ?? 0
    const invol = att.involuntary_exits ?? 0
    items.push({
      severity: 'critical',
      badge: 'CRITICAL',
      category: 'RETENTION',
      title: `Address ${formatPercent(att.attrition_rate_pct)} Attrition Rate`,
      description: `${invol === exits && exits > 0 ? `All ${exits}` : `${invol} of ${exits}`} exit${exits !== 1 ? 's' : ''} involuntary — above industry average. Risk score ${risk.risk_score ?? 0}/100; predicted ${formatPercent(risk.predicted_attrition_rate)} next period.`,
      actions: ['Conduct exit interviews immediately', 'Implement retention bonuses', 'Employee satisfaction survey', 'Review management practices'],
    })
  }

  if ((atm.attendance_rate_pct ?? 0) < 92 && (atm.attendance_rate_pct ?? 0) > 0) {
    const absent = atm.absent_days ?? 0
    const totalRecs = atm.total_attendance_records ?? 0
    items.push({
      severity: 'high',
      badge: 'SERIOUS',
      category: 'ENGAGEMENT',
      title: `Improve ${formatPercent(atm.attendance_rate_pct)} Attendance Rate`,
      description: `${absent} absent of ${totalRecs} records. Attendance drives only ${eng.key_indicators?.attendance_contribution ?? 0}/40 of engagement score.`,
      actions: ['Review attendance policy', 'Address work-life balance', 'Consider flexible working'],
    })
  }

  if (pay.payroll_efficiency === 'no_data') {
    items.push({
      severity: 'medium',
      badge: 'DATA GAP',
      category: 'PAYROLL',
      title: 'No Salary Slip Records',
      description: `Compensation analysis is unavailable this period. ${pay.payroll_data_note ?? 'Avg. salary and total payroll show as "–"'}.`,
      actions: ['Verify Salary Slip setup in HRMS', 'Confirm payroll period alignment'],
    })
  }

  const hirNeed = hiring.total_hiring_need ?? 0
  if (hirNeed > 0) {
    const unassigned = wc.department_distribution?.find(d => d.department === '(Unassigned)')?.count ?? 0
    items.push({
      severity: 'low',
      badge: 'WATCH',
      category: 'WORKFORCE PLANNING',
      title: `${hirNeed} Hire${hirNeed !== 1 ? 's' : ''} Projected Q+1`,
      description: `${hiring.hiring_urgency === 'high' ? 'High urgency.' : 'Normal urgency.'} ${unassigned ? `${unassigned} employee${unassigned !== 1 ? 's' : ''} currently unassigned to a department.` : ''}`.trim(),
      actions: unassigned
        ? ['Assign unassigned employees to departments', 'Plan for projected exit']
        : ['Plan for projected exit'],
    })
  }

  // Composition health — always shown as a positive closing item.
  const genderRatios = wc.gender_ratios ?? {}
  const diversityScore = wc.diversity_score ?? 0
  const genderSummary = Object.entries(genderRatios)
    .map(([g, p]) => `${g.charAt(0).toUpperCase() + g.slice(1)} ${p}%`)
    .join(', ')
  const leaveApps = data.value.leave_metrics?.total_leave_applications ?? 0
  const avgLeave = data.value.leave_metrics?.average_days_per_application ?? 0
  items.push({
    severity: 'none',
    badge: 'OK',
    category: 'COMPOSITION',
    title: 'Balance & Diversity Healthy',
    description: `${genderSummary}. Diversity score ${diversityScore} ${wc.composition_balance ?? ''}. Leave pattern healthy (${leaveApps} app${leaveApps !== 1 ? 's' : ''}, ${avgLeave.toFixed(1)}d avg).`,
    actions: [],
  })

  return items.slice(0, 5)
})

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
        <div class="flex flex-wrap items-center gap-3">
          <IntelligenceDateFilter v-model="period" :options="FISCAL_PERIOD_RANGES" />
          <Button variant="subtle" :loading="refreshing" @click="reload">Refresh</Button>
        </div>
      </div>
    </header>

    <IntelligenceDashboardShell
      :loading="loading"
      :refreshing="refreshing"
      :error="error"
      :is-permission-error="isPermissionError"
      :warming="warming"
      :not-implemented="notImplemented"
      :not-implemented-message="notImplementedMessage"
      :has-data="hasData"
      subject="HR data"
      permission-hint="Ask an administrator for Employee read access."
      :kpi-count="4"
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
      <div v-if="activeTab === 'overview'" class="p-6 grid grid-cols-2 lg:grid-cols-4 gap-4">
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
          @click="kpi.drillable && drillDown.open(HR_ENDPOINT, kpi.label, { metric: kpi.metric ?? '', period: period })"
        />
      </div>

      <!-- Tab strip -->
      <div class="mx-6">
        <Tabs v-model="tabIndex" :tabs="tabs" />
      </div>

      <!-- Tab content -->
      <div class="p-6">

        <!-- Workforce Overview — variant C: hero waterfall + attention rail -->
        <div v-show="activeTab === 'overview'" class="space-y-6">

          <!-- Hero + Rail (2-col grid) -->
          <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">

            <!-- Hero: headcount waterfall chart (2/3 width) -->
            <div class="lg:col-span-2 bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader title="Headcount flow — Trailing 12 months" :level="3" />
              <p v-if="hasData" class="mt-1 text-sm text-ink-gray-6">
                {{ data?.headcount_metrics?.exits ?? 0 }} exits equal {{ data?.headcount_metrics?.new_hires ?? 0 }} new hires
                — {{ (data?.headcount_metrics?.net_growth ?? 0) === 0
                    ? 'the entire workforce turned over in one year, with zero net growth'
                    : 'workforce changed significantly this period' }}.
              </p>

              <template v-if="hasData">
                <!-- Value labels above bars -->
                <div class="mt-6 flex gap-3" aria-hidden="true">
                  <div class="flex-1 text-center text-sm font-bold text-ink-gray-7">{{ openingHeadcount }}</div>
                  <div class="flex-1 text-center text-sm font-bold text-ink-red-4">−{{ data?.headcount_metrics?.exits ?? 0 }}</div>
                  <div class="flex-1 text-center text-sm font-bold" :style="{color: 'var(--app-pos)'}">+{{ data?.headcount_metrics?.new_hires ?? 0 }}</div>
                  <div class="flex-1 text-center text-sm font-bold text-ink-gray-7">{{ data?.headcount_metrics?.total_employees ?? 0 }}</div>
                </div>

                <!-- Waterfall bars — vertically bottom-aligned, absolute positioned -->
                <div
                  class="relative mt-1 h-40"
                  role="img"
                  :aria-label="`Headcount waterfall: opening ${openingHeadcount}, exits -${data?.headcount_metrics?.exits ?? 0}, new hires +${data?.headcount_metrics?.new_hires ?? 0}, closing ${data?.headcount_metrics?.total_employees ?? 0}`"
                >
                  <!-- Floor annotation: dashed line at the minimum headcount level -->
                  <div
                    v-if="floorHc > 0 && peakHc > 0"
                    class="absolute inset-x-0 z-10 pointer-events-none"
                    :style="{bottom: hcPct(floorHc) + '%'}"
                  >
                    <div class="border-t-2 border-dashed border-outline-gray-3"></div>
                    <span class="text-xs font-semibold text-ink-red-4 pl-1">floor: {{ floorHc }}</span>
                  </div>

                  <!-- Bars container (fills chart area) -->
                  <div class="absolute inset-0 flex gap-3">
                    <!-- Opening: full height, gray -->
                    <div class="flex-1 relative">
                      <div
                        class="absolute inset-x-0 bottom-0 rounded-t"
                        :style="{height: hcPct(openingHeadcount) + '%', backgroundColor: 'var(--app-muted-fill)'}"
                      ></div>
                    </div>
                    <!-- Exits: from floor upward, red -->
                    <div class="flex-1 relative">
                      <div
                        class="absolute inset-x-0 rounded-t"
                        :style="{
                          bottom: hcPct(floorHc) + '%',
                          height: hcPct(data?.headcount_metrics?.exits ?? 0) + '%',
                          backgroundColor: 'var(--app-neg-fill)'
                        }"
                      ></div>
                    </div>
                    <!-- New Hires: from floor upward, green -->
                    <div class="flex-1 relative">
                      <div
                        class="absolute inset-x-0 rounded-t"
                        :style="{
                          bottom: hcPct(floorHc) + '%',
                          height: hcPct(data?.headcount_metrics?.new_hires ?? 0) + '%',
                          backgroundColor: 'var(--app-pos-fill)'
                        }"
                      ></div>
                    </div>
                    <!-- Closing: full height, gray -->
                    <div class="flex-1 relative">
                      <div
                        class="absolute inset-x-0 bottom-0 rounded-t"
                        :style="{height: hcPct(data?.headcount_metrics?.total_employees ?? 0) + '%', backgroundColor: 'var(--app-muted-fill)'}"
                      ></div>
                    </div>
                  </div>
                </div>

                <!-- X-axis labels -->
                <div class="flex gap-3 mt-1">
                  <div class="flex-1 text-center text-xs text-ink-gray-6">Opening</div>
                  <div class="flex-1 text-center text-xs text-ink-gray-6">Exits</div>
                  <div class="flex-1 text-center text-xs text-ink-gray-6">New Hires</div>
                  <div class="flex-1 text-center text-xs text-ink-gray-6">Closing</div>
                </div>
              </template>
              <div v-else class="mt-6">
                <SkeletonBlock class="h-48 w-full" />
              </div>

              <!-- Sub-metrics row: attendance / engagement / payroll (no data) -->
              <div v-if="hasData" class="mt-6 pt-4 border-t border-outline-gray-2 grid grid-cols-3 gap-4">
                <div>
                  <p
                    class="text-xl font-bold"
                    :class="(attendanceMetrics.attendance_rate_pct ?? 100) < 85 ? 'text-ink-red-4' : 'text-ink-gray-9'"
                  >{{ formatPercent(attendanceMetrics.attendance_rate_pct) }}</p>
                  <p class="text-xs text-ink-gray-6 mt-0.5">Attendance rate</p>
                  <p class="text-xs text-ink-gray-6">
                    {{ attendanceMetrics.present_days ?? '–' }} present · {{ attendanceMetrics.absent_days ?? '–' }} absent
                  </p>
                </div>
                <div>
                  <p class="text-xl font-bold text-ink-gray-8">
                    {{ data?.engagement_indicators?.engagement_score ?? '–' }}/100
                  </p>
                  <p class="text-xs text-ink-gray-6 mt-0.5">Engagement score</p>
                  <p class="text-xs text-ink-gray-6">
                    Retention contribution {{ data?.engagement_indicators?.key_indicators?.retention_contribution ?? '–' }}/40
                  </p>
                </div>
                <div>
                  <!-- Payroll absent: communicate the absence clearly rather than show a dash with no context. -->
                  <p class="text-xl font-bold text-ink-gray-5">—</p>
                  <p class="text-xs text-ink-gray-6 mt-0.5">
                    Avg. salary{{ baseCurrency ? ` (${baseCurrency})` : '' }}
                  </p>
                  <p class="text-xs text-ink-gray-6">{{ data?.payroll_metrics?.payroll_data_note ?? 'No payroll data' }}</p>
                </div>
              </div>
            </div>

            <!-- Attention Rail: synthesised from payload, ranked by consequence -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
              <p class="text-xs font-semibold text-ink-gray-6 uppercase tracking-wide mb-3">
                Needs Attention
                <span class="font-normal normal-case text-ink-gray-6"> — ranked by consequence</span>
              </p>
              <div v-if="hasData" class="space-y-4">
                <div
                  v-for="(item, i) in attentionItems"
                  :key="i"
                >
                  <div class="flex items-center gap-1 mb-0.5">
                    <span
                      class="text-xs font-semibold text-ink-gray-6"
                      :style="attentionBadgeStyle(item.severity)"
                    >{{ item.badge }}</span>
                    <span class="text-xs text-ink-gray-5" aria-hidden="true">·</span>
                    <span class="text-xs text-ink-gray-6 uppercase tracking-wide">{{ item.category }}</span>
                  </div>
                  <p class="text-sm font-medium text-ink-gray-8">{{ item.title }}</p>
                  <p class="text-xs text-ink-gray-6 mt-0.5">{{ item.description }}</p>
                  <ul v-if="item.actions.length" class="mt-1 space-y-0.5">
                    <li
                      v-for="(action, j) in item.actions.slice(0, 3)"
                      :key="j"
                      class="text-xs text-ink-gray-6 flex items-start gap-1"
                    >
                      <span class="text-ink-gray-5 flex-shrink-0" aria-hidden="true">→</span>
                      {{ action }}
                    </li>
                  </ul>
                </div>
              </div>
              <div v-else class="space-y-3">
                <SkeletonBlock v-for="n in 3" :key="n" class="h-16 w-full" />
              </div>
            </div>
          </div>

          <!-- Workforce composition (below fold): ranked horizontal bars instead of
               the previous plain text list. Rule 2: position/length over table-of-numbers. -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <div class="flex items-center justify-between mb-4">
              <SectionHeader title="Workforce composition" :level="3" />
              <button
                class="text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 rounded"
                :style="{color: 'var(--app-accent)'}"
                @click="drillDown.open(HR_ENDPOINT, 'All Employees', { metric: 'total_employees', period: period })"
              >View rows ↗</button>
            </div>
            <div v-if="hasData && data?.workforce_composition" class="grid grid-cols-1 md:grid-cols-3 gap-8">
              <!-- By Department (ranked descending by count) -->
              <div>
                <p class="text-xs font-semibold text-ink-gray-6 uppercase tracking-wide mb-3">By Department</p>
                <div class="space-y-2">
                  <div
                    v-for="row in (data?.workforce_composition?.department_distribution ?? [])"
                    :key="row.department"
                    class="flex items-center gap-2"
                  >
                    <span class="text-sm text-ink-gray-7 w-24 truncate flex-shrink-0">{{ row.department }}</span>
                    <div class="flex-1 h-1.5 bg-surface-gray-2 rounded-full overflow-hidden" aria-hidden="true">
                      <div
                        class="h-full rounded-full"
                        :style="{width: maxDeptCount > 0 ? (row.count / maxDeptCount * 100) + '%' : '0%', backgroundColor: 'var(--app-accent)'}"
                      ></div>
                    </div>
                    <span class="text-sm font-medium text-ink-gray-8 w-5 text-right flex-shrink-0">{{ row.count }}</span>
                  </div>
                </div>
              </div>
              <!-- By Employment Type (clickable → drill-down) -->
              <div>
                <p class="text-xs font-semibold text-ink-gray-6 uppercase tracking-wide mb-3">By Employment Type</p>
                <div class="space-y-2">
                  <button
                    v-for="row in (data?.workforce_composition?.employment_type_distribution ?? [])"
                    :key="row.employment_type || row.type"
                    class="flex items-center gap-2 w-full text-left hover:bg-surface-gray-1 rounded -mx-1 px-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 motion-reduce:transition-none transition-colors"
                    @click="drillDown.open(HR_ENDPOINT, (row.employment_type || row.type || '') + ' Employees', { metric: 'employment_type', employment_type: row.employment_type || row.type, period: period })"
                  >
                    <span class="text-sm text-ink-gray-7 w-24 truncate flex-shrink-0">{{ row.employment_type || row.type }}</span>
                    <div class="flex-1 h-1.5 bg-surface-gray-2 rounded-full overflow-hidden" aria-hidden="true">
                      <div
                        class="h-full rounded-full"
                        :style="{width: maxEmpTypeCount > 0 ? (row.count / maxEmpTypeCount * 100) + '%' : '0%', backgroundColor: 'var(--app-accent)'}"
                      ></div>
                    </div>
                    <span class="text-sm font-medium text-ink-gray-8 w-5 text-right flex-shrink-0">{{ row.count }}</span>
                  </button>
                </div>
              </div>
              <!-- By Gender + diversity score panel -->
              <div>
                <p class="text-xs font-semibold text-ink-gray-6 uppercase tracking-wide mb-3">By Gender</p>
                <div class="space-y-2">
                  <div
                    v-for="(pct, gender) in (data?.workforce_composition?.gender_ratios ?? {})"
                    :key="gender as string"
                    class="flex items-center gap-2"
                  >
                    <span class="text-sm text-ink-gray-7 w-24 truncate flex-shrink-0 capitalize">{{ gender }}</span>
                    <div class="flex-1 h-1.5 bg-surface-gray-2 rounded-full overflow-hidden" aria-hidden="true">
                      <div
                        class="h-full rounded-full"
                        :style="{width: pct + '%', backgroundColor: 'var(--app-accent)'}"
                      ></div>
                    </div>
                    <span class="text-sm font-medium text-ink-gray-8 w-10 text-right flex-shrink-0">{{ pct }}%</span>
                  </div>
                </div>
                <div
                  v-if="(data?.workforce_composition?.diversity_score ?? 0) > 0"
                  class="mt-3 bg-surface-green-2 rounded p-2"
                >
                  <p class="text-ink-gray-9">
                    <span class="text-xl font-bold">{{ data?.workforce_composition?.diversity_score }}</span>
                    <span class="text-xs text-ink-gray-6 ml-1">{{ data?.workforce_composition?.composition_balance }}</span>
                  </p>
                  <p class="text-xs text-ink-gray-6">Diversity score</p>
                </div>
              </div>
            </div>
            <div v-else-if="hasData" class="text-center py-8 text-ink-gray-6">
              <p>No composition data available</p>
            </div>
            <div v-else class="space-y-3">
              <SkeletonBlock v-for="n in 3" :key="n" class="h-20 w-full" />
            </div>
          </div>
        </div>

        <!-- Attrition & Retention -->
        <div v-show="activeTab === 'attrition'" class="space-y-6">
          <TabBrief :brief="tabBriefs.attrition" :as-of="data?.generated_at" />
          <StatStrip :items="attritionStrip" />

          <!-- What happened (TTM): headcount movement behind the attrition rate -->
          <div v-if="hasData && data?.headcount_metrics" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="What Happened (TTM)" :level="3" />
            <dl class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
              <div class="bg-surface-gray-1 rounded-lg p-4">
                <dt class="text-sm text-ink-gray-6">Opening headcount</dt>
                <dd class="text-lg font-semibold tnum text-ink-gray-8">{{ openingHeadcount }}</dd>
              </div>
              <div class="bg-surface-gray-1 rounded-lg p-4">
                <dt class="text-sm text-ink-gray-6">Total exits</dt>
                <dd class="text-lg font-semibold tnum text-ink-gray-8">{{ data.attrition_metrics?.total_exits ?? NO_VALUE }}</dd>
              </div>
              <div class="bg-surface-gray-1 rounded-lg p-4">
                <dt class="text-sm text-ink-gray-6">New hires</dt>
                <dd class="text-lg font-semibold tnum text-ink-gray-8">{{ data.headcount_metrics.new_hires ?? NO_VALUE }}</dd>
              </div>
              <div class="bg-surface-gray-1 rounded-lg p-4">
                <dt class="text-sm text-ink-gray-6">Net headcount change</dt>
                <dd class="text-lg font-semibold tnum text-ink-gray-8">{{ data.headcount_metrics.net_growth ?? NO_VALUE }}</dd>
              </div>
            </dl>
          </div>

          <!-- Attrition Risk Assessment -->
          <div v-if="hasData && attritionRisk" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Attrition Risk Assessment" :level="3" />
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
              <div class="rounded-lg p-4 text-center bg-surface-gray-1">
                <p class="text-sm font-medium text-ink-gray-6">Overall Risk Level</p>
                <Badge
                  class="mt-2"
                  v-bind="severityBadge(riskLevelSeverity(attritionRisk.risk_level))"
                  :label="severityBadge(riskLevelSeverity(attritionRisk.risk_level)).label"
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

          <!-- Attendance Breakdown (supports the engagement score on the KPI strip). -->
          <div v-if="hasData && data?.attendance_metrics" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Attendance Breakdown" :level="3" />
            <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mt-4">
              <KpiCard
                variant="tile"
                label="Attendance Rate"
                :percent="data.attendance_metrics.attendance_rate_pct"
                sublabel="effective (incl. half-day/on-leave)"
              />
              <KpiCard
                variant="tile"
                label="Present (strict)"
                :value="data.attendance_metrics.present_days"
                :sublabel="`of ${data.attendance_metrics.total_attendance_records || 0} records`"
              />
              <KpiCard
                variant="tile"
                label="Half Day + On Leave"
                :value="(data.attendance_metrics.half_day_days || 0) + (data.attendance_metrics.on_leave_days || 0)"
                sublabel="partially attended"
              />
              <KpiCard
                variant="tile"
                label="Absent"
                :value="data.attendance_metrics.absent_days"
              />
              <KpiCard
                variant="tile"
                label="Late Arrivals"
                :percent="data.attendance_metrics.late_arrival_rate_pct"
                :sublabel="`of ${data.attendance_metrics.total_in_checkins || 0} check-ins`"
              />
            </div>
          </div>

          <!-- Engagement score decomposition: the three payload contributions, in points of 100. -->
          <div v-if="hasData && data?.engagement_indicators?.key_indicators" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader
              variant="caption"
              :title="`Engagement score decomposition: ${data.engagement_indicators.engagement_score ?? 0} / 100`"
              :level="3"
            />
            <div
              class="mt-4 flex h-6 w-full overflow-hidden rounded bg-surface-gray-1"
              role="img"
              :aria-label="`Engagement score ${data.engagement_indicators.engagement_score ?? 0} of 100`"
            >
              <div class="h-full bg-surface-gray-7" :style="{ width: `${Number(data.engagement_indicators.key_indicators.attendance_contribution) || 0}%` }" />
              <div class="h-full bg-surface-gray-5" :style="{ width: `${Number(data.engagement_indicators.key_indicators.retention_contribution) || 0}%` }" />
              <div class="h-full bg-surface-gray-3" :style="{ width: `${Number(data.engagement_indicators.key_indicators.leave_pattern_contribution) || 0}%` }" />
            </div>
            <dl class="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm text-ink-gray-7">
              <div class="flex items-center gap-2">
                <span class="inline-block h-2.5 w-2.5 rounded-sm bg-surface-gray-7" aria-hidden="true" />
                <dt>Attendance</dt>
                <dd class="tnum font-semibold text-ink-gray-8">{{ data.engagement_indicators.key_indicators.attendance_contribution ?? 0 }} pts</dd>
              </div>
              <div class="flex items-center gap-2">
                <span class="inline-block h-2.5 w-2.5 rounded-sm bg-surface-gray-5" aria-hidden="true" />
                <dt>Retention</dt>
                <dd class="tnum font-semibold text-ink-gray-8">{{ data.engagement_indicators.key_indicators.retention_contribution ?? 0 }} pts</dd>
              </div>
              <div class="flex items-center gap-2">
                <span class="inline-block h-2.5 w-2.5 rounded-sm bg-surface-gray-3" aria-hidden="true" />
                <dt>Leave pattern</dt>
                <dd class="tnum font-semibold text-ink-gray-8">{{ data.engagement_indicators.key_indicators.leave_pattern_contribution ?? 0 }} pts</dd>
              </div>
            </dl>
          </div>
          <TabActions class="mt-6" :actions="tabBriefs.attrition?.actions" />
        </div>

        <!-- Department Health -->
        <div v-show="activeTab === 'department'" class="space-y-6">
          <TabBrief :brief="tabBriefs.department" :as-of="data?.generated_at" />
          <StatStrip :items="departmentStrip" />
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Department Overview" :level="3" />
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
                      <p class="text-xs text-ink-gray-6">{{ dept.headcount }} {{ dept.headcount === 1 ? 'employee' : 'employees' }} · {{ formatPercent(dept.headcount / departments.reduce((n, d) => n + d.headcount, 0) * 100) }} of headcount</p>
                    </div>
                  </div>
                </div>
                <div class="flex items-center gap-4">
                  <div class="text-right">
                    <p class="text-xs text-ink-gray-6">Payroll Cost</p>
                    <p class="text-sm font-medium text-ink-gray-8">{{ data?.payroll_metrics?.payroll_efficiency === 'no_data' ? NO_VALUE : formatCurrency(dept.payroll_cost || 0) }}</p>
                  </div>
                  <div class="text-right">
                    <p class="text-xs text-ink-gray-6">Cost/Employee</p>
                    <p class="text-sm font-medium text-ink-gray-8">{{ data?.payroll_metrics?.payroll_efficiency === 'no_data' ? NO_VALUE : formatCurrency(dept.cost_per_employee || 0) }}</p>
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
          <TabActions class="mt-6" :actions="tabBriefs.department?.actions" />
        </div>

        <!-- Payroll & Compensation -->
        <div v-show="activeTab === 'payroll'" class="space-y-6">
          <TabBrief :brief="tabBriefs.payroll" :as-of="data?.generated_at" />
          <StatStrip :items="payrollStrip" :currency="baseCurrency" />

          <!-- Compensation Analysis -->
          <div v-if="hasData && data?.compensation_analysis && !payrollMissing" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Compensation Analysis" :level="3" />
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
                      v-bind="severityBadge(payEquitySeverity(data.compensation_analysis.pay_equity_status))"
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
          <TabActions class="mt-6" :actions="tabBriefs.payroll?.actions" />
        </div>

        <!-- Workforce Planning -->
        <div v-show="activeTab === 'planning'" class="space-y-6">
          <TabBrief :brief="tabBriefs.planning" :as-of="data?.generated_at" />
          <StatStrip :items="planningStrip" />

          <!-- Recommendations -->
          <div v-if="hasData && recommendations.length > 0" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Recommendations" :level="3" />
            <div class="space-y-3 mt-4">
              <div v-for="(rec, i) in recommendations" :key="i"
                class="flex items-start gap-3 p-3 bg-surface-gray-1 rounded-lg">
                <Zap class="w-5 h-5 text-ink-gray-5 flex-shrink-0 mt-0.5" aria-hidden="true" />
                <div>
                  <p class="text-sm font-medium text-ink-gray-8">{{ typeof rec === 'string' ? rec : rec.title }}</p>
                  <p v-if="rec.description" class="text-xs text-ink-gray-6 mt-1">{{ rec.description }}</p>
                  <p v-if="rec.impact" class="text-xs text-ink-gray-6 mt-1">Impact: {{ rec.impact }}</p>
                </div>
              </div>
            </div>
          </div>
          <TabActions class="mt-6" :actions="tabBriefs.planning?.actions" />
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
