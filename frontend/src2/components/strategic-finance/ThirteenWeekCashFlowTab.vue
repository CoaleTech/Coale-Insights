<template>
  <div class="space-y-6">
    <!-- No Data State -->
    <div v-if="!data" class="flex flex-col items-center justify-center py-12 text-ink-gray-6">
      <CalendarDays class="h-12 w-12 mb-4 text-ink-gray-5" />
      <p class="text-lg font-medium text-ink-gray-8">No 13-Week Forecast Data</p>
      <p class="text-sm text-ink-gray-6">Data will appear once loaded</p>
    </div>

    <template v-else>
      <!-- Header with Threshold Input -->
      <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <SectionHeader title="13-Week Rolling Cash Flow Forecast" :level="3"
            hint="Week-by-week cash projections with categorized inflows and outflows" />
        </div>
        <div class="flex items-center gap-4">
          <!-- Payroll Detection Badge -->
          <Badge
            v-if="data?.payroll_detection?.detected"
            theme="gray"
            variant="subtle"
            :label="payrollLabel"
            size="sm"
          />
          <!-- Threshold Input -->
          <FormControl
            label="Min Cash Threshold"
            type="number"
            :model-value="threshold"
            placeholder="0"
            @update:model-value="(v) => { threshold = Number(v) || 0; saveThreshold() }"
          />
        </div>
      </div>

      <!-- Summary KPI Cards -->
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard label="Opening Balance" :amount="data?.opening_balance" :currency="currency" />
        <KpiCard label="Total Inflows" :amount="data?.summary?.total_inflows" :currency="currency" />
        <KpiCard label="Total Outflows" :amount="data?.summary?.total_outflows" :currency="currency" />
        <KpiCard label="Ending Cash" :amount="data?.summary?.ending_cash" :currency="currency" />
        <KpiCard
          label="Min Balance"
          :amount="data?.summary?.minimum_balance"
          :currency="currency"
          :sublabel="'Week ' + data?.summary?.minimum_balance_week"
          :severity="isMinBalanceCritical ? 'critical' : 'none'"
        />
        <KpiCard
          label="Weeks Below Threshold"
          :value="data?.summary?.weeks_below_threshold"
          :severity="hasThresholdWarning ? 'critical' : 'none'"
        />
      </div>

      <!-- Legend -->
      <div class="flex flex-wrap items-center gap-4 px-4 py-2 bg-surface-gray-1 rounded-lg">
        <span class="text-sm font-medium text-ink-gray-7">Legend:</span>
        <div class="flex items-center gap-2">
          <div class="w-4 h-4 bg-surface-blue-3 rounded" aria-hidden="true"></div>
          <span class="text-sm text-ink-gray-7">Actual (Historical)</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-4 h-4 bg-surface-white border border-outline-gray-2 rounded" aria-hidden="true"></div>
          <span class="text-sm text-ink-gray-7">Forecast</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-4 h-4 bg-surface-amber-3 rounded" aria-hidden="true"></div>
          <span class="text-sm text-ink-gray-7">Current Week</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-4 h-4 bg-surface-red-5 rounded" aria-hidden="true"></div>
          <span class="text-sm text-ink-gray-7">Below Threshold</span>
        </div>
      </div>

      <!-- Chart -->
      <div class="bg-surface-white rounded-lg p-6 shadow-sm border border-outline-gray-1">
        <SectionHeader title="Cash Flow Visualization" :level="4" />
        <div v-if="chartData" class="h-56 sm:h-72 lg:h-80 mt-4">
          <ThirteenWeekChart :data="chartData" :threshold="threshold" :currency="currency" />
        </div>
        <div v-else class="h-80 flex items-center justify-center text-ink-gray-6">
          No data available for chart
        </div>
      </div>

      <!-- Scenario Analysis and Variance Review Panels -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="bg-surface-white rounded-lg p-5 shadow-sm border border-outline-gray-1">
          <CashFlowScenarioPanel :scenarios="scenariosProp" />
        </div>
        <div class="bg-surface-white rounded-lg p-5 shadow-sm border border-outline-gray-1">
          <CashFlowVariancePanel :variance="varianceProp" />
        </div>
      </div>

      <!-- Weekly Table -->
      <div class="bg-surface-white rounded-lg shadow-sm border border-outline-gray-1 overflow-hidden">
        <div class="p-4 border-b border-outline-gray-1">
          <SectionHeader title="Weekly Cash Flow Detail" :level="4" />
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-outline-gray-1">
            <thead class="bg-surface-gray-1">
              <tr>
                <th
                  scope="col"
                  class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase tracking-wider sticky left-0 bg-surface-gray-1 z-10 min-w-[140px]"
                >
                  Category
                </th>
                <th
                  v-for="week in displayWeeks"
                  :key="'h-' + week.week_number"
                  scope="col"
                  :class="[
                    'px-3 py-3 text-center text-xs font-medium uppercase tracking-wider min-w-[100px]',
                    getWeekHeaderClass(week),
                  ]"
                >
                  <div>{{ week.week_label }}</div>
                  <div class="font-normal text-ink-gray-6 normal-case">{{ formatDateShort(week.week_start) }}</div>
                </th>
              </tr>
            </thead>
            <tbody class="bg-surface-white divide-y divide-outline-gray-1">
              <!-- Opening Balance -->
              <tr class="bg-surface-gray-1">
                <th scope="row" class="px-4 py-2 text-sm font-medium text-ink-gray-9 sticky left-0 bg-surface-gray-1 text-left">
                  Opening Balance
                </th>
                <td
                  v-for="week in displayWeeks"
                  :key="'ob-' + week.week_number"
                  :class="['px-3 py-2 text-sm text-right font-medium text-ink-gray-9', getWeekCellClass(week)]"
                >
                  {{ formatCompact(week.opening_balance) }}
                </td>
              </tr>

              <!-- Inflows Section (expandable row) -->
              <tr
                class="cursor-pointer hover:bg-surface-gray-1"
                tabindex="0"
                :aria-expanded="expandedSections.inflows"
                @click="toggleSection('inflows')"
                @keydown.enter.prevent="toggleSection('inflows')"
                @keydown.space.prevent="toggleSection('inflows')"
              >
                <td class="px-4 py-2 text-sm font-semibold text-ink-gray-8 sticky left-0 bg-surface-white">
                  <div class="flex items-center gap-2">
                    <ChevronDown
                      :class="[
                        'h-4 w-4 text-ink-gray-5 transition-transform motion-reduce:transition-none',
                        expandedSections.inflows ? '' : '-rotate-90',
                      ]"
                    />
                    <ArrowUpCircle class="h-4 w-4 text-ink-gray-5" />
                    Total Inflows
                  </div>
                </td>
                <td
                  v-for="week in displayWeeks"
                  :key="'ti-' + week.week_number"
                  :class="['px-3 py-2 text-sm text-right font-semibold text-ink-gray-8', getWeekCellClass(week)]"
                >
                  {{ formatCompact(week.inflows?.total || 0) }}
                </td>
              </tr>
              <!-- Inflows Detail Rows -->
              <template v-if="expandedSections.inflows">
                <tr class="bg-surface-gray-1">
                  <th scope="row" class="px-4 py-1.5 text-xs text-ink-gray-6 sticky left-0 bg-surface-gray-1 pl-10 font-normal text-left">
                    AR Collections
                  </th>
                  <td
                    v-for="week in displayWeeks"
                    :key="'ar-' + week.week_number"
                    class="px-3 py-1.5 text-xs text-right text-ink-gray-7"
                  >
                    {{ formatCompact(week.inflows?.ar_collections || 0) }}
                  </td>
                </tr>
                <tr class="bg-surface-gray-1">
                  <th scope="row" class="px-4 py-1.5 text-xs text-ink-gray-6 sticky left-0 bg-surface-gray-1 pl-10 font-normal text-left">
                    Other Receipts
                  </th>
                  <td
                    v-for="week in displayWeeks"
                    :key="'or-' + week.week_number"
                    class="px-3 py-1.5 text-xs text-right text-ink-gray-7"
                  >
                    {{ formatCompact(week.inflows?.other_receipts || 0) }}
                  </td>
                </tr>
              </template>

              <!-- Outflows Section (expandable row) -->
              <tr
                class="cursor-pointer hover:bg-surface-gray-1"
                tabindex="0"
                :aria-expanded="expandedSections.outflows"
                @click="toggleSection('outflows')"
                @keydown.enter.prevent="toggleSection('outflows')"
                @keydown.space.prevent="toggleSection('outflows')"
              >
                <td class="px-4 py-2 text-sm font-semibold text-ink-gray-8 sticky left-0 bg-surface-white">
                  <div class="flex items-center gap-2">
                    <ChevronDown
                      :class="[
                        'h-4 w-4 text-ink-gray-5 transition-transform motion-reduce:transition-none',
                        expandedSections.outflows ? '' : '-rotate-90',
                      ]"
                    />
                    <ArrowDownCircle class="h-4 w-4 text-ink-gray-5" />
                    Total Outflows
                  </div>
                </td>
                <td
                  v-for="week in displayWeeks"
                  :key="'to-' + week.week_number"
                  :class="['px-3 py-2 text-sm text-right font-semibold text-ink-gray-8', getWeekCellClass(week)]"
                >
                  ({{ formatCompact(week.outflows?.total || 0) }})
                </td>
              </tr>
              <!-- Outflows Detail Rows -->
              <template v-if="expandedSections.outflows">
                <tr class="bg-surface-gray-1">
                  <th scope="row" class="px-4 py-1.5 text-xs text-ink-gray-6 sticky left-0 bg-surface-gray-1 pl-10 font-normal text-left">
                    AP Payments
                  </th>
                  <td
                    v-for="week in displayWeeks"
                    :key="'ap-' + week.week_number"
                    class="px-3 py-1.5 text-xs text-right text-ink-gray-7"
                  >
                    {{ formatCompact(week.outflows?.ap_payments || 0) }}
                  </td>
                </tr>
                <tr class="bg-surface-gray-1">
                  <th scope="row" class="px-4 py-1.5 text-xs text-ink-gray-6 sticky left-0 bg-surface-gray-1 pl-10 font-normal text-left">
                    <div class="flex items-center gap-1">
                      <Users class="h-3 w-3 text-ink-gray-5" />
                      Payroll
                    </div>
                  </th>
                  <td
                    v-for="week in displayWeeks"
                    :key="'pr-' + week.week_number"
                    class="px-3 py-1.5 text-xs text-right text-ink-gray-7"
                  >
                    {{ formatCompact(week.outflows?.payroll || 0) }}
                  </td>
                </tr>
                <tr class="bg-surface-gray-1">
                  <th scope="row" class="px-4 py-1.5 text-xs text-ink-gray-6 sticky left-0 bg-surface-gray-1 pl-10 font-normal text-left">
                    Operating Expenses
                  </th>
                  <td
                    v-for="week in displayWeeks"
                    :key="'oe-' + week.week_number"
                    class="px-3 py-1.5 text-xs text-right text-ink-gray-7"
                  >
                    {{ formatCompact(week.outflows?.operating_expenses || 0) }}
                  </td>
                </tr>
                <tr class="bg-surface-gray-1">
                  <th scope="row" class="px-4 py-1.5 text-xs text-ink-gray-6 sticky left-0 bg-surface-gray-1 pl-10 font-normal text-left">
                    Taxes
                  </th>
                  <td
                    v-for="week in displayWeeks"
                    :key="'tx-' + week.week_number"
                    class="px-3 py-1.5 text-xs text-right text-ink-gray-7"
                  >
                    {{ formatCompact(week.outflows?.taxes || 0) }}
                  </td>
                </tr>
              </template>

              <!-- Net Flow -->
              <tr class="border-t-2 border-outline-gray-2">
                <th scope="row" class="px-4 py-2 text-sm font-semibold text-ink-gray-9 sticky left-0 bg-surface-white text-left">
                  Net Cash Flow
                </th>
                <td
                  v-for="week in displayWeeks"
                  :key="'nf-' + week.week_number"
                  :class="[
                    'px-3 py-2 text-sm text-right font-semibold',
                    deltaInk(week.net_flow),
                    getWeekCellClass(week),
                  ]"
                >
                  {{ week.net_flow >= 0 ? '+' : '' }}{{ formatCompact(week.net_flow) }}
                </td>
              </tr>

              <!-- Closing Balance -->
              <tr class="bg-surface-gray-2">
                <th scope="row" class="px-4 py-3 text-sm font-bold text-ink-gray-9 sticky left-0 bg-surface-gray-2 text-left">
                  Closing Balance
                </th>
                <td
                  v-for="week in displayWeeks"
                  :key="'cb-' + week.week_number"
                  :class="[
                    'px-3 py-3 text-sm text-right font-bold',
                    week.below_threshold ? 'text-ink-red-4' : 'text-ink-gray-9',
                    getWeekCellClass(week, true),
                  ]"
                >
                  {{ formatCompact(week.closing_balance) }}
                  <Badge
                    v-if="week.below_threshold"
                    label="Low"
                    theme="red"
                    variant="subtle"
                    size="sm"
                    class="block mt-1"
                  />
                </td>
              </tr>

              <!-- Variance Row (for actual weeks) -->
              <tr v-if="hasVariance" class="bg-surface-gray-1">
                <th scope="row" class="px-4 py-2 text-sm font-medium text-ink-gray-8 sticky left-0 bg-surface-gray-1 text-left">
                  Variance (Actual - Forecast)
                </th>
                <td
                  v-for="week in displayWeeks"
                  :key="'var-' + week.week_number"
                  class="px-3 py-2 text-sm text-right"
                >
                  <template v-if="week.variance">
                    <span :class="deltaInk(week.variance.net)">
                      {{ week.variance.net >= 0 ? '+' : '' }}{{ formatCompact(week.variance.net) }}
                    </span>
                  </template>
                  <span v-else class="text-ink-gray-6">-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Payroll Schedule Info -->
      <div
        v-if="data?.payroll_detection?.detected"
        class="bg-surface-gray-1 rounded-lg p-4 border border-outline-gray-1"
      >
        <h4 class="text-sm font-semibold text-ink-gray-9 flex items-center gap-2 mb-2">
          <Users class="h-4 w-4 text-ink-gray-5" />
          Auto-Detected Payroll Schedule
        </h4>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span class="text-ink-gray-6">Frequency:</span>
            <span class="ml-2 font-medium text-ink-gray-9 capitalize">{{ data.payroll_detection.frequency }}</span>
          </div>
          <div>
            <span class="text-ink-gray-6">Typical Amount:</span>
            <span class="ml-2 font-medium text-ink-gray-9">{{ formatCurrency(data.payroll_detection.typical_amount) }}</span>
          </div>
          <div>
            <span class="text-ink-gray-6">Next Payroll:</span>
            <span class="ml-2 font-medium text-ink-gray-9">{{ formatDate(data.payroll_detection.next_date) }}</span>
          </div>
          <div>
            <span class="text-ink-gray-6">Confidence:</span>
            <span class="ml-2 font-medium text-ink-gray-9">{{ Math.round((data.payroll_detection.confidence || 0) * 100) }}%</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, inject } from 'vue'
import { Badge, FormControl } from 'frappe-ui'
import {
  CalendarDays,
  ArrowUpCircle,
  ArrowDownCircle,
  ChevronDown,
  Users,
} from 'lucide-vue-next'
import { deltaInk } from '../../utils/status'
import { formatDate, formatDateShort, NO_VALUE } from '../../utils/format'
import ThirteenWeekChart from './ThirteenWeekChart.vue'
import CashFlowScenarioPanel from './CashFlowScenarioPanel.vue'
import CashFlowVariancePanel from './CashFlowVariancePanel.vue'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import { ThirteenWeekData, ThirteenWeekRow } from './types'

/** Chart week with inflows/outflows required; ThirteenWeekRow has them optional (shell skips sub-fields). */
interface ChartWeekData extends ThirteenWeekRow {
  inflows: NonNullable<ThirteenWeekRow['inflows']>
  outflows: NonNullable<ThirteenWeekRow['outflows']>
}

/** Mirror of CashFlowScenarioPanel's expected scenarios prop shape. */
interface ScenarioPanelData {
  base_ending_balance: number
  base_min_balance: number
  threshold: number
  scenarios: { id: string; name: string; description: string; type: string; icon: string; impact: number; ending_balance: number; min_balance: number; risk_level: string; weeks_below_threshold: number }[]
  quick_actions: { action: string; description: string; priority: string; potential_impact: number }[]
}

/** Mirror of CashFlowVariancePanel's expected variance prop shape. */
interface VariancePanelData {
  has_variance_data: boolean
  weeks_analyzed: number
  summary?: { inflow_forecast_accuracy: number; outflow_forecast_accuracy: number; total_net_variance: number; total_inflow_variance: number; total_outflow_variance: number }
  insights?: { type: string; title: string; category: string; description: string; recommendation: string }[]
  weekly_details?: { week_number: number; week_label: string; inflow_variance: number; inflow_variance_pct: number; outflow_variance: number; outflow_variance_pct: number; net_variance: number }[]
}

interface Props {
  data: ThirteenWeekData | null
}

const props = defineProps<Props>()

const currency = inject('currency', 'KES')

const threshold = ref(0)
const expandedSections = ref({ inflows: false, outflows: false })

onMounted(() => {
  const savedThreshold = localStorage.getItem('cashflow_threshold')
  if (savedThreshold) {
    threshold.value = parseFloat(savedThreshold)
  } else if (props.data?.min_cash_threshold) {
    threshold.value = props.data.min_cash_threshold
  }
})

watch(
  () => props.data?.min_cash_threshold,
  (newVal) => {
    if (newVal && !localStorage.getItem('cashflow_threshold')) {
      threshold.value = newVal
    }
  },
)

const displayWeeks = computed(() => {
  if (!props.data?.weeks) return []
  return props.data.weeks.filter((w) => w.week_number >= 0)
})

const hasVariance = computed(() => props.data?.weeks?.some((w) => w.variance))
const hasThresholdWarning = computed(() => (props.data?.summary?.weeks_below_threshold || 0) > 0)
const isMinBalanceCritical = computed(() => {
  const minBalance = props.data?.summary?.minimum_balance || 0
  return minBalance < threshold.value
})

const payrollLabel = computed(() => {
  const pattern = props.data?.payroll_detection
  if (!pattern?.detected) return ''
  return `${pattern.frequency} payroll: ${formatCurrency(pattern.typical_amount)}`
})

const chartData = computed(() => {
  if (!props.data?.weeks) return null
  // ThirteenWeekRow types inflows/outflows optional; ThirteenWeekChart requires them.
  // All API rows carry both; cast once at this chart boundary.
  return { weeks: displayWeeks.value as unknown as ChartWeekData[], threshold: threshold.value }
})

// scenarios boundary: unknown in shared type, passed through from shell.
const scenariosProp = computed(() => props.data?.scenarios as unknown as ScenarioPanelData | null | undefined)
// variance_analysis boundary: same pass-through pattern.
const varianceProp = computed(() => props.data?.variance_analysis as unknown as VariancePanelData | null | undefined)

const toggleSection = (section: 'inflows' | 'outflows') => {
  expandedSections.value[section] = !expandedSections.value[section]
}

const saveThreshold = () => {
  localStorage.setItem('cashflow_threshold', threshold.value.toString())
}

const getWeekHeaderClass = (week: { is_current: boolean; is_actual: boolean }) => {
  if (week.is_current) return 'text-ink-gray-9 font-bold bg-surface-gray-2'
  if (week.is_actual) return 'text-ink-gray-8 bg-surface-gray-1'
  return 'text-ink-gray-6'
}

const getWeekCellClass = (week: { is_current: boolean; is_actual: boolean; below_threshold: boolean }, isClosing = false) => {
  const classes: string[] = []
  if (week.is_current) {
    classes.push('bg-surface-gray-2')
  } else if (week.is_actual) {
    classes.push('bg-surface-gray-1')
  }
  // Below-threshold closing cells get a subtle surface tint; text already handles severity
  if (isClosing && week.below_threshold) {
    classes.push('bg-surface-gray-2')
  }
  return classes.join(' ')
}

const formatCurrency = (value: number) => {
  // Absent is not zero: this returned `${currency} 0`, reporting zero money
  // for a field the server never sent. Notation is unchanged -- exact
  // `en-KE` grouping is a deliberate choice for this surface, and
  // switching it is a separate product decision.
  if (value === null || value === undefined) return NO_VALUE
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const formatCompact = (value: number | null | undefined) => {
  if (value === null || value === undefined) return NO_VALUE
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absValue >= 1000000) return `${sign}${(absValue / 1000000).toFixed(1)}M`
  if (absValue >= 1000) return `${sign}${(absValue / 1000).toFixed(0)}K`
  return `${sign}${absValue.toFixed(0)}`
}
</script>
