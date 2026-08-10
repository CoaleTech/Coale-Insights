<template>
  <div class="space-y-6">
    <!-- Loading state -->
    <div v-if="!data" class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <KpiCard v-for="i in 4" :key="i" label="..." value="" :loading="true" />
    </div>

    <template v-else>
      <!-- Cash Position Overview -->
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        <KpiCard label="Current Cash" :amount="data.current_cash" :currency="currency" />
        <KpiCard label="Expected AR Inflows" :amount="data.expected_ar_inflows" :currency="currency" />
        <KpiCard label="Expected AP Outflows" :amount="data.expected_ap_outflows" :currency="currency" />
        <KpiCard
          label="Net Expected"
          :amount="data.net_expected"
          :currency="currency"
          :severity="(data.net_expected || 0) < 0 ? 'critical' : 'none'"
        />
      </div>

      <!-- 90-Day Cash Forecast Chart -->
      <div class="bg-surface-white rounded-lg p-6 shadow-sm border border-outline-gray-1">
        <SectionHeader variant="caption" title="90-Day Cash Flow Forecast" :level="3" />
        <div v-if="data.base_forecast?.length" class="h-56 sm:h-72 lg:h-80 mt-4">
          <CashForecastChart
            :base="chartForecasts.base"
            :optimistic="chartForecasts.optimistic"
            :pessimistic="chartForecasts.pessimistic"
            :currency="currency"
          />
        </div>
        <div v-else class="h-80 flex items-center justify-center text-ink-gray-6">
          Insufficient data for forecasting
        </div>
      </div>

      <!-- Forecast Scenarios (identity labels, not status colors) -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Optimistic -->
        <div class="bg-surface-white rounded-lg p-6 shadow-sm border border-outline-gray-1">
          <div class="flex items-center gap-2 mb-4">
            <TrendingUp class="h-5 w-5 text-ink-gray-5" />
            <h4 class="font-semibold text-ink-gray-9">Optimistic Scenario</h4>
          </div>
          <div class="space-y-3">
            <div class="flex justify-between">
              <span class="text-sm text-ink-gray-6">End Position</span>
              <span class="font-medium text-ink-gray-9">
                {{ formatCurrency(data.end_of_period?.optimistic || 0) }}
              </span>
            </div>
            <div class="flex justify-between">
              <span class="text-sm text-ink-gray-6">Cash Runway</span>
              <span class="font-medium text-ink-gray-9">
                {{ (data.optimistic_runway_days ?? 0) >= 90 ? '90+ days' : data.optimistic_runway_days + ' days' }}
              </span>
            </div>
          </div>
          <div class="mt-4 pt-4 border-t border-outline-gray-1">
            <p class="text-xs text-ink-gray-6">Assumes 20% higher inflows</p>
          </div>
        </div>

        <!-- Base Case -->
        <div class="bg-surface-white rounded-lg p-6 shadow-sm border border-outline-gray-1">
          <div class="flex items-center gap-2 mb-4">
            <Target class="h-5 w-5 text-ink-gray-5" />
            <h4 class="font-semibold text-ink-gray-9">Base Case</h4>
          </div>
          <div class="space-y-3">
            <div class="flex justify-between">
              <span class="text-sm text-ink-gray-6">End Position</span>
              <span class="font-medium text-ink-gray-9">
                {{ formatCurrency(data.end_of_period?.base || 0) }}
              </span>
            </div>
            <div class="flex justify-between">
              <span class="text-sm text-ink-gray-6">Cash Runway</span>
              <span class="font-medium text-ink-gray-9">
                {{ (data.base_runway_days ?? 0) >= 90 ? '90+ days' : data.base_runway_days + ' days' }}
              </span>
            </div>
            <div class="flex justify-between">
              <span class="text-sm text-ink-gray-6">Avg Daily Flow</span>
              <span class="font-medium text-ink-gray-9">
                {{ formatCurrency(data.avg_daily_flow || 0) }}
              </span>
            </div>
          </div>
          <div class="mt-4 pt-4 border-t border-outline-gray-1">
            <p class="text-xs text-ink-gray-6">Based on historical averages and AR/AP</p>
          </div>
        </div>

        <!-- Pessimistic -->
        <div class="bg-surface-white rounded-lg p-6 shadow-sm border border-outline-gray-1">
          <div class="flex items-center gap-2 mb-4">
            <TrendingDown class="h-5 w-5 text-ink-gray-5" />
            <h4 class="font-semibold text-ink-gray-9">Pessimistic Scenario</h4>
          </div>
          <div class="space-y-3">
            <div class="flex justify-between">
              <span class="text-sm text-ink-gray-6">End Position</span>
              <span class="font-medium text-ink-gray-9">
                {{ formatCurrency(data.end_of_period?.pessimistic || 0) }}
              </span>
            </div>
            <div class="flex justify-between">
              <span class="text-sm text-ink-gray-6">Cash Runway</span>
              <span
                class="font-medium"
                :class="(data.pessimistic_runway_days ?? 0) < 30 ? 'text-ink-red-4' : 'text-ink-gray-9'"
              >
                {{ (data.pessimistic_runway_days ?? 0) >= 90 ? '90+ days' : data.pessimistic_runway_days + ' days' }}
              </span>
            </div>
          </div>
          <div class="mt-4 pt-4 border-t border-outline-gray-1">
            <p class="text-xs text-ink-gray-6">Assumes 20% lower inflows</p>
          </div>
        </div>
      </div>

      <!-- Weekly Cash Summary -->
      <div class="bg-surface-white rounded-lg p-6 shadow-sm border border-outline-gray-1">
        <SectionHeader variant="caption" title="Weekly Cash Summary" :level="3" />
        <div v-if="data.weekly_summary?.length" class="overflow-x-auto mt-4">
          <table class="min-w-full divide-y divide-outline-gray-1">
            <thead>
              <tr>
                <th
                  scope="col"
                  class="px-3 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase sticky left-0 bg-surface-white"
                >
                  Scenario
                </th>
                <th
                  v-for="week in data.weekly_summary"
                  :key="'h-' + week.week"
                  scope="col"
                  class="px-3 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase"
                >
                  W{{ week.week }}
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-outline-gray-1">
              <tr class="hover:bg-surface-gray-1">
                <td class="px-3 py-3 text-sm font-medium text-ink-gray-8 sticky left-0 bg-surface-white">Base</td>
                <td
                  v-for="week in data.weekly_summary"
                  :key="'b-' + week.week"
                  class="px-3 py-3 text-sm text-right font-medium text-ink-gray-9 whitespace-nowrap"
                >
                  {{ formatCompact(week.base_balance) }}
                </td>
              </tr>
              <tr class="hover:bg-surface-gray-1">
                <td class="px-3 py-3 text-sm font-medium text-ink-gray-8 sticky left-0 bg-surface-white">Optimistic</td>
                <td
                  v-for="week in data.weekly_summary"
                  :key="'o-' + week.week"
                  class="px-3 py-3 text-sm text-right font-medium text-ink-gray-9 whitespace-nowrap"
                >
                  {{ formatCompact(week.optimistic_balance) }}
                </td>
              </tr>
              <tr class="hover:bg-surface-gray-1">
                <td class="px-3 py-3 text-sm font-medium text-ink-gray-8 sticky left-0 bg-surface-white">Pessimistic</td>
                <td
                  v-for="week in data.weekly_summary"
                  :key="'p-' + week.week"
                  class="px-3 py-3 text-sm text-right font-medium whitespace-nowrap"
                  :class="week.pessimistic_balance < 0 ? 'text-ink-red-4' : 'text-ink-gray-9'"
                >
                  {{ formatCompact(week.pessimistic_balance) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="text-center py-8 text-ink-gray-6">
          No weekly summary available
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { NO_VALUE } from '../../utils/format'
import {
  TrendingUp,
  TrendingDown,
  Target,
} from 'lucide-vue-next'
import { computed } from 'vue'
import { useCurrency } from '../../composables/useCurrency'
import CashForecastChart from '../charts/CashForecastChart.vue'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import { CashForecastData } from './types'

/** Row shape consumed by CashForecastChart; matches the chart's internal ForecastPoint exactly. */
interface ForecastPoint {
  date: string
  day: number
  balance: number
}

interface Props {
  data: CashForecastData | null
}

const props = defineProps<Props>()

// base/optimistic/pessimistic_forecast are unknown[] in the shared type; the shell never reads
// row fields. CashForecastChart needs ForecastPoint[]. Narrow once here at the chart boundary.
const chartForecasts = computed(() => ({
  base: (props.data?.base_forecast ?? []) as unknown as ForecastPoint[],
  optimistic: (props.data?.optimistic_forecast ?? []) as unknown as ForecastPoint[],
  pessimistic: (props.data?.pessimistic_forecast ?? []) as unknown as ForecastPoint[],
}))

const _currency = useCurrency()
const getCurrency = () =>
  (typeof _currency === 'string' ? _currency : (_currency as unknown as { value: string })?.value) || 'KES'
const currency = getCurrency()

const formatCurrency = (value: number) => {
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

const formatCompact = (value: number) => {
  if (value === null || value === undefined) return NO_VALUE
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absValue >= 1000000) return `${sign}${(absValue / 1000000).toFixed(1)}M`
  if (absValue >= 1000) return `${sign}${(absValue / 1000).toFixed(0)}K`
  return `${sign}${absValue.toFixed(0)}`
}
</script>
