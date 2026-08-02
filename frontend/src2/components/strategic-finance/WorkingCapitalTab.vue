<template>
  <div class="space-y-6">

    <!-- Working Capital Metric Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <!--
        DSO and DIO: higherIsBetter=false (more days to collect/hold = worse).
        DPO: higherIsBetter=true (more days before paying suppliers = better cash position).
        Thresholds from original helpers, preserved exactly.
      -->
      <KpiCard
        label="Days Sales Outstanding"
        :value="`${data?.dso?.toFixed(1) ?? '0'} days`"
        :severity="dsoSeverity"
        :loading="!data"
      />
      <KpiCard
        label="Days Inventory Outstanding"
        :value="`${data?.dio?.toFixed(1) ?? '0'} days`"
        :severity="dioSeverity"
        :loading="!data"
      />
      <KpiCard
        label="Days Payables Outstanding"
        :value="`${data?.dpo?.toFixed(1) ?? '0'} days`"
        :severity="dpoSeverity"
        :loading="!data"
      />
      <KpiCard
        label="Cash Conversion Cycle"
        :value="`${data?.cash_conversion_cycle?.toFixed(1) ?? '0'} days`"
        :severity="cccSeverity"
        :loading="!data"
      />
    </div>

    <!-- Cash Conversion Cycle Visual Breakdown -->
    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <SectionHeader title="Cash Conversion Cycle Breakdown" :level="3" />
      <div class="flex flex-col md:flex-row items-center justify-center gap-4 md:gap-8 mt-6">
        <!-- DSO circle -->
        <div class="text-center">
          <div
            class="w-24 h-24 rounded-full bg-surface-gray-2 flex items-center justify-center mx-auto"
            :aria-label="severityAria('DSO', dsoSeverity, data?.dso?.toFixed(0))"
            role="img"
          >
            <div>
              <p class="text-xl font-bold text-ink-gray-9">{{ data?.dso?.toFixed(0) || 0 }}</p>
              <p class="text-xs text-ink-gray-6">days</p>
            </div>
          </div>
          <p class="mt-2 text-sm font-medium text-ink-gray-7">DSO</p>
          <p class="text-xs text-ink-gray-6">Collect Receivables</p>
        </div>

        <div class="hidden md:block text-2xl text-ink-gray-6">+</div>

        <!-- DIO circle -->
        <div class="text-center">
          <div
            class="w-24 h-24 rounded-full bg-surface-gray-2 flex items-center justify-center mx-auto"
            :aria-label="severityAria('DIO', dioSeverity, data?.dio?.toFixed(0))"
            role="img"
          >
            <div>
              <p class="text-xl font-bold text-ink-gray-9">{{ data?.dio?.toFixed(0) || 0 }}</p>
              <p class="text-xs text-ink-gray-6">days</p>
            </div>
          </div>
          <p class="mt-2 text-sm font-medium text-ink-gray-7">DIO</p>
          <p class="text-xs text-ink-gray-6">Sell Inventory</p>
        </div>

        <div class="hidden md:block text-2xl text-ink-gray-6">-</div>

        <!-- DPO circle -->
        <div class="text-center">
          <div
            class="w-24 h-24 rounded-full bg-surface-gray-2 flex items-center justify-center mx-auto"
            :aria-label="severityAria('DPO', dpoSeverity, data?.dpo?.toFixed(0))"
            role="img"
          >
            <div>
              <p class="text-xl font-bold text-ink-gray-9">{{ data?.dpo?.toFixed(0) || 0 }}</p>
              <p class="text-xs text-ink-gray-6">days</p>
            </div>
          </div>
          <p class="mt-2 text-sm font-medium text-ink-gray-7">DPO</p>
          <p class="text-xs text-ink-gray-6">Pay Suppliers</p>
        </div>

        <div class="hidden md:block text-2xl text-ink-gray-6">=</div>

        <!-- CCC circle: non-text fill from severity -->
        <div class="text-center">
          <div
            :class="['w-24 h-24 rounded-full flex items-center justify-center mx-auto', severityFill(cccSeverity)]"
            :aria-label="severityAria('Cash Conversion Cycle', cccSeverity, data?.cash_conversion_cycle?.toFixed(0))"
            role="img"
          >
            <div>
              <p :class="['text-xl font-bold', cccSeverity === 'high' || cccSeverity === 'critical' ? 'text-ink-red-4' : 'text-ink-gray-9']">
                {{ data?.cash_conversion_cycle?.toFixed(0) || 0 }}
              </p>
              <p class="text-xs text-ink-gray-6">days</p>
            </div>
          </div>
          <p class="mt-2 text-sm font-medium text-ink-gray-7">CCC</p>
          <p class="text-xs text-ink-gray-6">Cash Cycle</p>
        </div>
      </div>
    </div>

    <!-- Working Capital Components -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Current Assets -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader title="Current Assets" :level="3">
          <template #actions>
            <ArrowUpCircle class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <div class="space-y-4 mt-4">
          <div class="flex justify-between items-center p-3 bg-surface-gray-1 rounded-lg">
            <span class="text-sm font-medium text-ink-gray-7">Cash &amp; Bank</span>
            <span class="text-sm font-semibold text-ink-gray-9">{{ formatCurrency(data?.cash || 0) }}</span>
          </div>
          <div class="flex justify-between items-center p-3 bg-surface-gray-1 rounded-lg">
            <span class="text-sm font-medium text-ink-gray-7">Accounts Receivable</span>
            <span class="text-sm font-semibold text-ink-gray-9">{{ formatCurrency(data?.receivables || 0) }}</span>
          </div>
          <div class="flex justify-between items-center p-3 bg-surface-gray-1 rounded-lg">
            <span class="text-sm font-medium text-ink-gray-7">Inventory</span>
            <span class="text-sm font-semibold text-ink-gray-9">{{ formatCurrency(data?.inventory || 0) }}</span>
          </div>
          <!-- Total row: neutral emphasis, not a status colour -->
          <div class="flex justify-between items-center p-3 bg-surface-gray-1 rounded-lg border border-outline-gray-2">
            <span class="text-sm font-bold text-ink-gray-9">Total Current Assets</span>
            <span class="text-sm font-bold text-ink-gray-9">{{ formatCurrency(data?.total_current_assets || 0) }}</span>
          </div>
        </div>
      </div>

      <!-- Current Liabilities -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader title="Current Liabilities" :level="3">
          <template #actions>
            <ArrowDownCircle class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <div class="space-y-4 mt-4">
          <div class="flex justify-between items-center p-3 bg-surface-gray-1 rounded-lg border border-outline-gray-2">
            <span class="text-sm font-bold text-ink-gray-9">Total Current Liabilities</span>
            <span class="text-sm font-bold text-ink-gray-9">
              {{ formatCurrency(data?.total_current_liabilities || 0) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Net Working Capital -->
    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <SectionHeader title="Net Working Capital" :level="3" hint="Current Assets - Current Liabilities" />
        </div>
        <div class="text-center md:text-right">
          <p
            :class="['text-3xl font-bold', (data?.working_capital || 0) >= 0 ? 'text-ink-gray-9' : 'text-ink-red-4']"
          >
            {{ formatCurrency(data?.working_capital || 0) }}
          </p>
          <p class="text-sm text-ink-gray-6 mt-1">
            Current Ratio: <span class="font-semibold">{{ data?.current_ratio?.toFixed(2) || '0' }}</span>
            | Quick Ratio: <span class="font-semibold">{{ data?.quick_ratio?.toFixed(2) || '0' }}</span>
          </p>
        </div>
      </div>
    </div>

    <!-- Trend Analysis (Months as Columns) -->
    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <SectionHeader title="Working Capital Trends" hint="Last 6 months" :level="3">
        <template #actions>
          <TrendingUp class="h-5 w-5 text-ink-gray-5" />
        </template>
      </SectionHeader>
      <div v-if="trendMonths.length" class="overflow-x-auto mt-4">
        <table class="min-w-full divide-y divide-outline-gray-1">
          <thead class="bg-surface-gray-1">
            <tr>
              <th
                scope="col"
                class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase sticky left-0 bg-surface-gray-1"
              >
                Metric
              </th>
              <th
                v-for="month in trendMonths"
                :key="month.period"
                scope="col"
                class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase whitespace-nowrap"
              >
                {{ formatPeriod(month.period) }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-1">
            <tr class="hover:bg-surface-gray-1">
              <th scope="row" class="px-4 py-3 text-sm font-medium text-ink-gray-9 sticky left-0 bg-surface-white">Current Assets</th>
              <td
                v-for="month in trendMonths"
                :key="'ca-' + month.period"
                class="px-4 py-3 text-sm text-right text-ink-gray-9 whitespace-nowrap"
              >
                {{ formatCompactCurrency(month.current_assets) }}
              </td>
            </tr>
            <tr class="hover:bg-surface-gray-1">
              <th scope="row" class="px-4 py-3 text-sm font-medium text-ink-gray-9 sticky left-0 bg-surface-white">Current Liabilities</th>
              <td
                v-for="month in trendMonths"
                :key="'cl-' + month.period"
                class="px-4 py-3 text-sm text-right text-ink-red-4 whitespace-nowrap"
              >
                {{ formatCompactCurrency(Math.abs(month.current_liabilities || 0)) }}
              </td>
            </tr>
            <tr class="hover:bg-surface-gray-1 font-semibold">
              <th scope="row" class="px-4 py-3 text-sm font-medium text-ink-gray-9 sticky left-0 bg-surface-white">Working Capital</th>
              <td
                v-for="month in trendMonths"
                :key="'wc-' + month.period"
                class="px-4 py-3 text-sm text-right whitespace-nowrap"
                :class="(month.working_capital ?? -1) >= 0 ? 'text-ink-gray-9' : 'text-ink-red-4'"
              >
                {{ formatCompactCurrency(month.working_capital) }}
              </td>
            </tr>
            <tr class="hover:bg-surface-gray-1">
              <th scope="row" class="px-4 py-3 text-sm font-medium text-ink-gray-9 sticky left-0 bg-surface-white">Current Ratio</th>
              <td
                v-for="month in trendMonths"
                :key="'cr-' + month.period"
                class="px-4 py-3 text-sm text-right whitespace-nowrap"
                :class="ratioInk(month.current_ratio)"
              >
                {{ (month.current_ratio ?? 0) >= 999 ? '∞' : month.current_ratio?.toFixed(2) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center py-8 text-ink-gray-6 mt-4">No trend data available</div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { NO_VALUE } from '../../utils/format'
import { computed, inject, isRef, type Ref } from 'vue'
import {
  Repeat,
  Package,
  Clock,
  RefreshCw,
  ArrowUpCircle,
  ArrowDownCircle,
  TrendingUp,
} from 'lucide-vue-next'
import { scoreSeverity, severityFill, severityAria, type Severity } from '../../utils/status'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import { WorkingCapitalData, WorkingCapitalTrendRow } from './types'

/** API trend rows also carry display fields the shell contract does not need. */
interface TrendRow extends WorkingCapitalTrendRow {
  period?: string
  current_assets?: number
  current_liabilities?: number
}

interface Props {
  data?: WorkingCapitalData
}

const props = defineProps<Props>()

const _currency = inject<string | Ref<string>>('currency', 'KES')
const getCurrency = () => (isRef(_currency) ? _currency.value : _currency) || 'KES'

// DSO: higherIsBetter=false (fewer days to collect is better).
// Thresholds carried from original getDSOHealthClass: <=30 good, <=45 fair, <=60 warn, >60 high
const dsoSeverity = computed((): Severity =>
  scoreSeverity(props.data?.dso, { good: 30, warn: 60, higherIsBetter: false })
)

// DIO: higherIsBetter=false (fewer days holding inventory is better).
// Original: <=30 good, <=60 fair, <=90 warn, >90 high
const dioSeverity = computed((): Severity =>
  scoreSeverity(props.data?.dio, { good: 30, warn: 90, higherIsBetter: false })
)

// DPO: higherIsBetter=true (paying later is better for cash position).
// Original: >=45 good, >=30 fair, >=15 warn, <15 high
const dpoSeverity = computed((): Severity =>
  scoreSeverity(props.data?.dpo, { good: 45, warn: 30, higherIsBetter: true })
)

// CCC: higherIsBetter=false (lower/negative cycle is better).
// Original: <=0 excellent, <=30 good, <=60 fair, >60 high
const cccSeverity = computed((): Severity =>
  scoreSeverity(props.data?.cash_conversion_cycle, { good: 0, warn: 60, higherIsBetter: false })
)

// Current ratio ink: below 1 is bad (red), 1-2 is neutral, >=2 is good (neutral)
const ratioInk = (ratio: number | null | undefined): string => {
  if (!ratio || ratio >= 999) return 'text-ink-gray-9'
  if (ratio >= 1) return 'text-ink-gray-9'
  return 'text-ink-red-4'
}

// API trend rows include display fields (period, current_assets, current_liabilities) beyond the
// shared minimal contract; cast once at this computed boundary.
const trendMonths = computed(() => (props.data?.trends as unknown as TrendRow[] | undefined)?.slice(-6) || [])

const formatPeriod = (period: string | undefined): string => {
  if (!period) return ''
  const [year, month] = period.split('-')
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${monthNames[parseInt(month) - 1]} ${year.slice(2)}`
}

const formatCompactCurrency = (value: number | undefined): string => {
  // Absent is not zero, same as the exact formatter below.
  if (value === undefined || value === null) return NO_VALUE
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  const c = getCurrency()
  if (absValue >= 1_000_000) return `${sign}${c} ${(absValue / 1_000_000).toFixed(1)}M`
  if (absValue >= 1_000) return `${sign}${c} ${(absValue / 1_000).toFixed(0)}K`
  return `${sign}${c} ${absValue.toFixed(0)}`
}

const formatCurrency = (value: number): string => {
  // Absent is not zero: this returned `${getCurrency()} 0`, reporting zero money
  // for a field the server never sent. Notation is unchanged -- exact
  // `en-KE` grouping is a deliberate choice for this surface, and
  // switching it is a separate product decision.
  if (value === null || value === undefined) return NO_VALUE
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: getCurrency(),
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}
</script>
