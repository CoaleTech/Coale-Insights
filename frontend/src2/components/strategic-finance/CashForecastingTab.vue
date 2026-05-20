<template>
  <div class="space-y-6">
    <!-- Cash Position Overview -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
            <Wallet class="h-5 w-5 text-green-600" />
          </div>
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Current Cash</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.current_cash || 0) }}
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
            <ArrowUpCircle class="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Expected AR Inflows</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.expected_ar_inflows || 0) }}
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-red-100 dark:bg-red-900/30 rounded-lg">
            <ArrowDownCircle class="h-5 w-5 text-red-600" />
          </div>
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Expected AP Outflows</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.expected_ap_outflows || 0) }}
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <div :class="['p-2 rounded-lg', getNetCashClass(data?.net_expected)]">
            <TrendingUp class="h-5 w-5" :class="getNetCashIconClass(data?.net_expected)" />
          </div>
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Net Expected</p>
            <p class="text-xl font-bold" :class="getNetCashTextClass(data?.net_expected)">
              {{ formatCurrency(data?.net_expected || 0) }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- 90-Day Cash Forecast Chart -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <LineChartIcon class="h-5 w-5 text-gray-500" />
        90-Day Cash Flow Forecast
      </h3>
      <div v-if="data?.base_forecast?.length" class="h-80">
        <CashForecastChart 
          :base="data.base_forecast" 
          :optimistic="data.optimistic_forecast" 
          :pessimistic="data.pessimistic_forecast" 
          :currency="currency"
        />
      </div>
      <div v-else class="h-80 flex items-center justify-center text-gray-500">
        Insufficient data for forecasting
      </div>
    </div>

    <!-- Forecast Scenarios -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Optimistic -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-green-200 dark:border-green-800">
        <div class="flex items-center gap-2 mb-4">
          <TrendingUp class="h-5 w-5 text-green-600" />
          <h4 class="font-semibold text-green-700 dark:text-green-400">Optimistic Scenario</h4>
        </div>
        <div class="space-y-3">
          <div class="flex justify-between">
            <span class="text-sm text-gray-600 dark:text-gray-400">End Position</span>
            <span class="font-medium text-gray-900 dark:text-white">
              {{ formatCurrency(data?.end_of_period?.optimistic || 0) }}
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-sm text-gray-600 dark:text-gray-400">Cash Runway</span>
            <span class="font-medium text-green-600">
              {{ data?.optimistic_runway_days >= 90 ? '90+ days' : data?.optimistic_runway_days + ' days' }}
            </span>
          </div>
        </div>
        <div class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <p class="text-xs text-gray-500">Assumes 20% higher inflows</p>
        </div>
      </div>

      <!-- Base Case -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-blue-200 dark:border-blue-800">
        <div class="flex items-center gap-2 mb-4">
          <Target class="h-5 w-5 text-blue-600" />
          <h4 class="font-semibold text-blue-700 dark:text-blue-400">Base Case</h4>
        </div>
        <div class="space-y-3">
          <div class="flex justify-between">
            <span class="text-sm text-gray-600 dark:text-gray-400">End Position</span>
            <span class="font-medium text-gray-900 dark:text-white">
              {{ formatCurrency(data?.end_of_period?.base || 0) }}
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-sm text-gray-600 dark:text-gray-400">Cash Runway</span>
            <span class="font-medium text-blue-600">
              {{ data?.base_runway_days >= 90 ? '90+ days' : data?.base_runway_days + ' days' }}
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-sm text-gray-600 dark:text-gray-400">Avg Daily Flow</span>
            <span class="font-medium text-gray-900 dark:text-white">
              {{ formatCurrency(data?.avg_daily_flow || 0) }}
            </span>
          </div>
        </div>
        <div class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <p class="text-xs text-gray-500">Based on historical averages and AR/AP</p>
        </div>
      </div>

      <!-- Pessimistic -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-red-200 dark:border-red-800">
        <div class="flex items-center gap-2 mb-4">
          <TrendingDown class="h-5 w-5 text-red-600" />
          <h4 class="font-semibold text-red-700 dark:text-red-400">Pessimistic Scenario</h4>
        </div>
        <div class="space-y-3">
          <div class="flex justify-between">
            <span class="text-sm text-gray-600 dark:text-gray-400">End Position</span>
            <span class="font-medium text-gray-900 dark:text-white">
              {{ formatCurrency(data?.end_of_period?.pessimistic || 0) }}
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-sm text-gray-600 dark:text-gray-400">Cash Runway</span>
            <span class="font-medium" :class="data?.pessimistic_runway_days < 30 ? 'text-red-600' : 'text-amber-600'">
              {{ data?.pessimistic_runway_days >= 90 ? '90+ days' : data?.pessimistic_runway_days + ' days' }}
            </span>
          </div>
        </div>
        <div class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <p class="text-xs text-gray-500">Assumes 20% lower inflows</p>
        </div>
      </div>
    </div>

    <!-- Weekly Cash Summary -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <Calendar class="h-5 w-5 text-gray-500" />
        Weekly Cash Summary
      </h3>
      <div v-if="data?.weekly_summary?.length" class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead>
            <tr>
              <th class="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase sticky left-0 bg-white dark:bg-gray-800">Scenario</th>
              <th v-for="week in data.weekly_summary" :key="'h-'+week.week" class="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                W{{ week.week }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr class="hover:bg-gray-50 dark:hover:bg-gray-700/50">
              <td class="px-3 py-3 text-sm font-medium text-blue-600 sticky left-0 bg-white dark:bg-gray-800">Base</td>
              <td v-for="week in data.weekly_summary" :key="'b-'+week.week" class="px-3 py-3 text-sm text-right font-medium text-gray-900 dark:text-white whitespace-nowrap">
                {{ formatCompact(week.base_balance) }}
              </td>
            </tr>
            <tr class="hover:bg-gray-50 dark:hover:bg-gray-700/50">
              <td class="px-3 py-3 text-sm font-medium text-green-600 sticky left-0 bg-white dark:bg-gray-800">Optimistic</td>
              <td v-for="week in data.weekly_summary" :key="'o-'+week.week" class="px-3 py-3 text-sm text-right font-medium text-green-600 whitespace-nowrap">
                {{ formatCompact(week.optimistic_balance) }}
              </td>
            </tr>
            <tr class="hover:bg-gray-50 dark:hover:bg-gray-700/50">
              <td class="px-3 py-3 text-sm font-medium text-amber-600 sticky left-0 bg-white dark:bg-gray-800">Pessimistic</td>
              <td v-for="week in data.weekly_summary" :key="'p-'+week.week" class="px-3 py-3 text-sm text-right font-medium whitespace-nowrap" :class="week.pessimistic_balance < 0 ? 'text-red-600' : 'text-amber-600'">
                {{ formatCompact(week.pessimistic_balance) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center py-8 text-gray-500">
        No weekly summary available
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { 
  Wallet, 
  ArrowUpCircle, 
  ArrowDownCircle, 
  TrendingUp, 
  TrendingDown,
  LineChart as LineChartIcon,
  Target,
  AlertTriangle,
  Calendar
} from 'lucide-vue-next'
import { inject } from 'vue'
import CashForecastChart from '../charts/CashForecastChart.vue'

interface Props {
  data: any
}

const props = defineProps<Props>()

const currency = inject('currency', 'KES')

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

const getNetCashClass = (value: number | null | undefined) => {
  if (!value) return 'bg-gray-100 dark:bg-gray-700'
  return value >= 0 
    ? 'bg-green-100 dark:bg-green-900/30'
    : 'bg-red-100 dark:bg-red-900/30'
}

const getNetCashIconClass = (value: number | null | undefined) => {
  if (!value) return 'text-gray-500'
  return value >= 0 ? 'text-green-600' : 'text-red-600'
}

const getNetCashTextClass = (value: number | null | undefined) => {
  if (!value) return 'text-gray-900 dark:text-white'
  return value >= 0 ? 'text-green-600' : 'text-red-600'
}
</script>
