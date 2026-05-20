<template>
  <div class="space-y-6">
    <!-- No Data State -->
    <div v-if="!data" class="flex flex-col items-center justify-center py-12 text-gray-500">
      <CalendarDays class="h-12 w-12 mb-4 text-gray-300" />
      <p class="text-lg font-medium">No 13-Week Forecast Data</p>
      <p class="text-sm">Data will appear once loaded</p>
    </div>

    <template v-else>
    <!-- Header with Threshold Input -->
    <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
      <div>
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <CalendarDays class="h-5 w-5 text-blue-600" />
          13-Week Rolling Cash Flow Forecast
        </h3>
        <p class="text-sm text-gray-500 mt-1">
          Week-by-week cash projections with categorized inflows and outflows
        </p>
      </div>
      <div class="flex items-center gap-4">
        <!-- Payroll Detection Badge -->
        <div v-if="data?.payroll_detection?.detected" class="flex items-center gap-2 px-3 py-1.5 bg-purple-50 dark:bg-purple-900/30 rounded-lg border border-purple-200 dark:border-purple-700">
          <Users class="h-4 w-4 text-purple-600" />
          <span class="text-sm text-purple-700 dark:text-purple-300">
            {{ payrollLabel }}
          </span>
        </div>
        <!-- Threshold Input -->
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-500">Min Cash Threshold:</label>
          <input
            v-model.number="threshold"
            type="number"
            class="w-32 px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
            placeholder="0"
            @change="saveThreshold"
          />
        </div>
      </div>
    </div>

    <!-- Summary Cards -->
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <div class="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-2">
          <div class="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
            <Wallet class="h-4 w-4 text-blue-600" />
          </div>
          <div>
            <p class="text-xs text-gray-500 dark:text-gray-400">Opening Balance</p>
            <p class="text-lg font-bold text-gray-900 dark:text-white">
              {{ formatCompact(data?.opening_balance || 0) }}
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-2">
          <div class="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
            <ArrowUpCircle class="h-4 w-4 text-green-600" />
          </div>
          <div>
            <p class="text-xs text-gray-500 dark:text-gray-400">Total Inflows</p>
            <p class="text-lg font-bold text-green-600">
              {{ formatCompact(data?.summary?.total_inflows || 0) }}
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-2">
          <div class="p-2 bg-red-100 dark:bg-red-900/30 rounded-lg">
            <ArrowDownCircle class="h-4 w-4 text-red-600" />
          </div>
          <div>
            <p class="text-xs text-gray-500 dark:text-gray-400">Total Outflows</p>
            <p class="text-lg font-bold text-red-600">
              {{ formatCompact(data?.summary?.total_outflows || 0) }}
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-2">
          <div class="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
            <PiggyBank class="h-4 w-4 text-purple-600" />
          </div>
          <div>
            <p class="text-xs text-gray-500 dark:text-gray-400">Ending Cash</p>
            <p class="text-lg font-bold text-gray-900 dark:text-white">
              {{ formatCompact(data?.summary?.ending_cash || 0) }}
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-2">
          <div class="p-2 bg-amber-100 dark:bg-amber-900/30 rounded-lg">
            <TrendingDown class="h-4 w-4 text-amber-600" />
          </div>
          <div>
            <p class="text-xs text-gray-500 dark:text-gray-400">Min Balance</p>
            <p class="text-lg font-bold" :class="isMinBalanceCritical ? 'text-red-600' : 'text-amber-600'">
              {{ formatCompact(data?.summary?.minimum_balance || 0) }}
            </p>
            <p class="text-xs text-gray-400">Week {{ data?.summary?.minimum_balance_week }}</p>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm border" :class="hasThresholdWarning ? 'border-red-300 bg-red-50 dark:bg-red-900/20' : 'border-gray-100 dark:border-gray-700'">
        <div class="flex items-center gap-2">
          <div :class="['p-2 rounded-lg', hasThresholdWarning ? 'bg-red-100 dark:bg-red-900/30' : 'bg-gray-100 dark:bg-gray-700']">
            <AlertTriangle :class="['h-4 w-4', hasThresholdWarning ? 'text-red-600' : 'text-gray-500']" />
          </div>
          <div>
            <p class="text-xs text-gray-500 dark:text-gray-400">Weeks Below Threshold</p>
            <p class="text-lg font-bold" :class="hasThresholdWarning ? 'text-red-600' : 'text-gray-900 dark:text-white'">
              {{ data?.summary?.weeks_below_threshold || 0 }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Legend -->
    <div class="flex flex-wrap items-center gap-4 px-4 py-2 bg-gray-50 dark:bg-gray-800 rounded-lg">
      <span class="text-sm font-medium text-gray-600 dark:text-gray-400">Legend:</span>
      <div class="flex items-center gap-2">
        <div class="w-4 h-4 bg-blue-100 border border-blue-300 rounded"></div>
        <span class="text-sm text-gray-600 dark:text-gray-400">Actual (Historical)</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-4 h-4 bg-white border border-gray-300 rounded"></div>
        <span class="text-sm text-gray-600 dark:text-gray-400">Forecast</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-4 h-4 bg-amber-100 border border-amber-300 rounded"></div>
        <span class="text-sm text-gray-600 dark:text-gray-400">Current Week</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-4 h-4 bg-red-100 border border-red-300 rounded"></div>
        <span class="text-sm text-gray-600 dark:text-gray-400">Below Threshold</span>
      </div>
    </div>

    <!-- Chart -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h4 class="text-md font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <BarChart3 class="h-5 w-5 text-gray-500" />
        Cash Flow Visualization
      </h4>
      <div v-if="chartData" class="h-80">
        <ThirteenWeekChart :data="chartData" :threshold="threshold" :currency="currency" />
      </div>
      <div v-else class="h-80 flex items-center justify-center text-gray-500">
        No data available for chart
      </div>
    </div>

    <!-- Scenario Analysis & Variance Review Panels -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Scenario Analysis Panel -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border border-gray-100 dark:border-gray-700">
        <CashFlowScenarioPanel :scenarios="data?.scenarios" />
      </div>
      
      <!-- Variance Review Panel -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border border-gray-100 dark:border-gray-700">
        <CashFlowVariancePanel :variance="data?.variance_analysis" />
      </div>
    </div>

    <!-- Weekly Table -->
    <div class="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700 overflow-hidden">
      <div class="p-4 border-b border-gray-200 dark:border-gray-700">
        <h4 class="text-md font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Table2 class="h-5 w-5 text-gray-500" />
          Weekly Cash Flow Detail
        </h4>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead class="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider sticky left-0 bg-gray-50 dark:bg-gray-900 z-10 min-w-[140px]">
                Category
              </th>
              <th 
                v-for="week in displayWeeks" 
                :key="'h-' + week.week_number"
                :class="[
                  'px-3 py-3 text-center text-xs font-medium uppercase tracking-wider min-w-[100px]',
                  getWeekHeaderClass(week)
                ]"
              >
                <div>{{ week.week_label }}</div>
                <div class="font-normal text-gray-400 normal-case">{{ formatDateShort(week.week_start) }}</div>
              </th>
            </tr>
          </thead>
          <tbody class="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
            <!-- Opening Balance -->
            <tr class="bg-gray-50 dark:bg-gray-900/50">
              <td class="px-4 py-2 text-sm font-medium text-gray-900 dark:text-white sticky left-0 bg-gray-50 dark:bg-gray-900/50">
                Opening Balance
              </td>
              <td 
                v-for="week in displayWeeks" 
                :key="'ob-' + week.week_number"
                :class="['px-3 py-2 text-sm text-right font-medium', getWeekCellClass(week)]"
              >
                {{ formatCompact(week.opening_balance) }}
              </td>
            </tr>

            <!-- Inflows Section -->
            <tr class="cursor-pointer hover:bg-green-50 dark:hover:bg-green-900/20" @click="toggleSection('inflows')">
              <td class="px-4 py-2 text-sm font-semibold text-green-700 dark:text-green-400 sticky left-0 bg-white dark:bg-gray-800 flex items-center gap-2">
                <ChevronDown :class="['h-4 w-4 transition-transform', expandedSections.inflows ? '' : '-rotate-90']" />
                <ArrowUpCircle class="h-4 w-4" />
                Total Inflows
              </td>
              <td 
                v-for="week in displayWeeks" 
                :key="'ti-' + week.week_number"
                :class="['px-3 py-2 text-sm text-right font-semibold text-green-600', getWeekCellClass(week)]"
              >
                {{ formatCompact(week.inflows?.total || 0) }}
              </td>
            </tr>
            <!-- Inflows Detail Rows -->
            <template v-if="expandedSections.inflows">
              <tr class="bg-green-50/30 dark:bg-green-900/10">
                <td class="px-4 py-1.5 text-xs text-gray-600 dark:text-gray-400 sticky left-0 bg-green-50/30 dark:bg-green-900/10 pl-10">
                  AR Collections
                </td>
                <td 
                  v-for="week in displayWeeks" 
                  :key="'ar-' + week.week_number"
                  class="px-3 py-1.5 text-xs text-right text-gray-600 dark:text-gray-400"
                >
                  {{ formatCompact(week.inflows?.ar_collections || 0) }}
                </td>
              </tr>
              <tr class="bg-green-50/30 dark:bg-green-900/10">
                <td class="px-4 py-1.5 text-xs text-gray-600 dark:text-gray-400 sticky left-0 bg-green-50/30 dark:bg-green-900/10 pl-10">
                  Other Receipts
                </td>
                <td 
                  v-for="week in displayWeeks" 
                  :key="'or-' + week.week_number"
                  class="px-3 py-1.5 text-xs text-right text-gray-600 dark:text-gray-400"
                >
                  {{ formatCompact(week.inflows?.other_receipts || 0) }}
                </td>
              </tr>
            </template>

            <!-- Outflows Section -->
            <tr class="cursor-pointer hover:bg-red-50 dark:hover:bg-red-900/20" @click="toggleSection('outflows')">
              <td class="px-4 py-2 text-sm font-semibold text-red-700 dark:text-red-400 sticky left-0 bg-white dark:bg-gray-800 flex items-center gap-2">
                <ChevronDown :class="['h-4 w-4 transition-transform', expandedSections.outflows ? '' : '-rotate-90']" />
                <ArrowDownCircle class="h-4 w-4" />
                Total Outflows
              </td>
              <td 
                v-for="week in displayWeeks" 
                :key="'to-' + week.week_number"
                :class="['px-3 py-2 text-sm text-right font-semibold text-red-600', getWeekCellClass(week)]"
              >
                ({{ formatCompact(week.outflows?.total || 0) }})
              </td>
            </tr>
            <!-- Outflows Detail Rows -->
            <template v-if="expandedSections.outflows">
              <tr class="bg-red-50/30 dark:bg-red-900/10">
                <td class="px-4 py-1.5 text-xs text-gray-600 dark:text-gray-400 sticky left-0 bg-red-50/30 dark:bg-red-900/10 pl-10">
                  AP Payments
                </td>
                <td 
                  v-for="week in displayWeeks" 
                  :key="'ap-' + week.week_number"
                  class="px-3 py-1.5 text-xs text-right text-gray-600 dark:text-gray-400"
                >
                  {{ formatCompact(week.outflows?.ap_payments || 0) }}
                </td>
              </tr>
              <tr class="bg-red-50/30 dark:bg-red-900/10">
                <td class="px-4 py-1.5 text-xs text-gray-600 dark:text-gray-400 sticky left-0 bg-red-50/30 dark:bg-red-900/10 pl-10">
                  <span class="flex items-center gap-1">
                    <Users class="h-3 w-3" />
                    Payroll
                  </span>
                </td>
                <td 
                  v-for="week in displayWeeks" 
                  :key="'pr-' + week.week_number"
                  class="px-3 py-1.5 text-xs text-right text-gray-600 dark:text-gray-400"
                >
                  {{ formatCompact(week.outflows?.payroll || 0) }}
                </td>
              </tr>
              <tr class="bg-red-50/30 dark:bg-red-900/10">
                <td class="px-4 py-1.5 text-xs text-gray-600 dark:text-gray-400 sticky left-0 bg-red-50/30 dark:bg-red-900/10 pl-10">
                  Operating Expenses
                </td>
                <td 
                  v-for="week in displayWeeks" 
                  :key="'oe-' + week.week_number"
                  class="px-3 py-1.5 text-xs text-right text-gray-600 dark:text-gray-400"
                >
                  {{ formatCompact(week.outflows?.operating_expenses || 0) }}
                </td>
              </tr>
              <tr class="bg-red-50/30 dark:bg-red-900/10">
                <td class="px-4 py-1.5 text-xs text-gray-600 dark:text-gray-400 sticky left-0 bg-red-50/30 dark:bg-red-900/10 pl-10">
                  Taxes
                </td>
                <td 
                  v-for="week in displayWeeks" 
                  :key="'tx-' + week.week_number"
                  class="px-3 py-1.5 text-xs text-right text-gray-600 dark:text-gray-400"
                >
                  {{ formatCompact(week.outflows?.taxes || 0) }}
                </td>
              </tr>
            </template>

            <!-- Net Flow -->
            <tr class="border-t-2 border-gray-300 dark:border-gray-600">
              <td class="px-4 py-2 text-sm font-semibold text-gray-900 dark:text-white sticky left-0 bg-white dark:bg-gray-800">
                Net Cash Flow
              </td>
              <td 
                v-for="week in displayWeeks" 
                :key="'nf-' + week.week_number"
                :class="[
                  'px-3 py-2 text-sm text-right font-semibold',
                  week.net_flow >= 0 ? 'text-green-600' : 'text-red-600',
                  getWeekCellClass(week)
                ]"
              >
                {{ week.net_flow >= 0 ? '+' : '' }}{{ formatCompact(week.net_flow) }}
              </td>
            </tr>

            <!-- Closing Balance -->
            <tr class="bg-gray-100 dark:bg-gray-900">
              <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-white sticky left-0 bg-gray-100 dark:bg-gray-900">
                Closing Balance
              </td>
              <td 
                v-for="week in displayWeeks" 
                :key="'cb-' + week.week_number"
                :class="[
                  'px-3 py-3 text-sm text-right font-bold',
                  week.below_threshold ? 'text-red-600 bg-red-100 dark:bg-red-900/30' : 'text-gray-900 dark:text-white',
                  getWeekCellClass(week, true)
                ]"
              >
                {{ formatCompact(week.closing_balance) }}
                <span v-if="week.below_threshold" class="block text-xs text-red-500">⚠️ Below threshold</span>
              </td>
            </tr>

            <!-- Variance Row (for actual weeks) -->
            <tr v-if="hasVariance" class="bg-purple-50 dark:bg-purple-900/20">
              <td class="px-4 py-2 text-sm font-medium text-purple-700 dark:text-purple-400 sticky left-0 bg-purple-50 dark:bg-purple-900/20">
                Variance (Actual - Forecast)
              </td>
              <td 
                v-for="week in displayWeeks" 
                :key="'var-' + week.week_number"
                class="px-3 py-2 text-sm text-right"
              >
                <template v-if="week.variance">
                  <span :class="week.variance.net >= 0 ? 'text-green-600' : 'text-red-600'">
                    {{ week.variance.net >= 0 ? '+' : '' }}{{ formatCompact(week.variance.net) }}
                  </span>
                </template>
                <span v-else class="text-gray-400">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Payroll Schedule Info -->
    <div v-if="data?.payroll_detection?.detected" class="bg-purple-50 dark:bg-purple-900/20 rounded-xl p-4 border border-purple-200 dark:border-purple-700">
      <h4 class="text-sm font-semibold text-purple-800 dark:text-purple-300 flex items-center gap-2 mb-2">
        <Users class="h-4 w-4" />
        Auto-Detected Payroll Schedule
      </h4>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <span class="text-purple-600 dark:text-purple-400">Frequency:</span>
          <span class="ml-2 font-medium text-gray-900 dark:text-white capitalize">{{ data.payroll_detection.frequency }}</span>
        </div>
        <div>
          <span class="text-purple-600 dark:text-purple-400">Typical Amount:</span>
          <span class="ml-2 font-medium text-gray-900 dark:text-white">{{ formatCurrency(data.payroll_detection.typical_amount) }}</span>
        </div>
        <div>
          <span class="text-purple-600 dark:text-purple-400">Next Payroll:</span>
          <span class="ml-2 font-medium text-gray-900 dark:text-white">{{ formatDate(data.payroll_detection.next_date) }}</span>
        </div>
        <div>
          <span class="text-purple-600 dark:text-purple-400">Confidence:</span>
          <span class="ml-2 font-medium text-gray-900 dark:text-white">{{ Math.round((data.payroll_detection.confidence || 0) * 100) }}%</span>
        </div>
      </div>
    </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, inject } from 'vue'
import { 
  CalendarDays,
  Wallet,
  ArrowUpCircle,
  ArrowDownCircle,
  TrendingDown,
  PiggyBank,
  AlertTriangle,
  BarChart3,
  Table2,
  ChevronDown,
  Users
} from 'lucide-vue-next'
import ThirteenWeekChart from './ThirteenWeekChart.vue'
import CashFlowScenarioPanel from './CashFlowScenarioPanel.vue'
import CashFlowVariancePanel from './CashFlowVariancePanel.vue'

interface Props {
  data: any
}

const props = defineProps<Props>()

const currency = inject('currency', 'KES')

// Reactive state
const threshold = ref(0)
const expandedSections = ref({
  inflows: false,
  outflows: false
})

// Initialize threshold from data or localStorage
onMounted(() => {
  const savedThreshold = localStorage.getItem('cashflow_threshold')
  if (savedThreshold) {
    threshold.value = parseFloat(savedThreshold)
  } else if (props.data?.min_cash_threshold) {
    threshold.value = props.data.min_cash_threshold
  }
})

// Watch for data changes
watch(() => props.data?.min_cash_threshold, (newVal) => {
  if (newVal && !localStorage.getItem('cashflow_threshold')) {
    threshold.value = newVal
  }
})

// Computed properties
const displayWeeks = computed(() => {
  if (!props.data?.weeks) return []
  // Skip the historical week (-1) for main display, show weeks 0-12
  return props.data.weeks.filter((w: any) => w.week_number >= 0)
})

const hasVariance = computed(() => {
  return props.data?.weeks?.some((w: any) => w.variance)
})

const hasThresholdWarning = computed(() => {
  return (props.data?.summary?.weeks_below_threshold || 0) > 0
})

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
  return {
    weeks: displayWeeks.value,
    threshold: threshold.value
  }
})

// Methods
const toggleSection = (section: 'inflows' | 'outflows') => {
  expandedSections.value[section] = !expandedSections.value[section]
}

const saveThreshold = () => {
  localStorage.setItem('cashflow_threshold', threshold.value.toString())
}

const getWeekHeaderClass = (week: any) => {
  if (week.is_current) return 'text-amber-700 bg-amber-100 dark:bg-amber-900/30'
  if (week.is_actual) return 'text-blue-700 bg-blue-50 dark:bg-blue-900/20'
  return 'text-gray-500'
}

const getWeekCellClass = (week: any, isClosing = false) => {
  const classes = []
  if (week.is_current) {
    classes.push('bg-amber-50 dark:bg-amber-900/20')
  } else if (week.is_actual) {
    classes.push('bg-blue-50/50 dark:bg-blue-900/10')
  }
  if (isClosing && week.below_threshold) {
    classes.push('bg-red-100 dark:bg-red-900/30')
  }
  return classes.join(' ')
}

const formatCurrency = (value: number) => {
  if (value === null || value === undefined) return `${currency} 0`
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const formatCompact = (value: number) => {
  if (value === null || value === undefined) return '0'
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absValue >= 1000000) return `${sign}${(absValue / 1000000).toFixed(1)}M`
  if (absValue >= 1000) return `${sign}${(absValue / 1000).toFixed(0)}K`
  return `${sign}${absValue.toFixed(0)}`
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-KE', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  })
}

const formatDateShort = (dateStr: string) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-KE', {
    month: 'short',
    day: 'numeric'
  })
}
</script>
