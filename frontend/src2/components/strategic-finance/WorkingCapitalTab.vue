<template>
  <div class="space-y-6">
    <!-- Working Capital Metrics -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
            <Repeat class="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Days Sales Outstanding</p>
            <p class="text-2xl font-bold text-gray-900 dark:text-white">
              {{ data?.dso?.toFixed(1) || '0' }} <span class="text-sm font-normal text-gray-500">days</span>
            </p>
          </div>
        </div>
        <div class="mt-3">
          <span :class="getDSOHealthClass(data?.dso)">
            {{ getDSOHealth(data?.dso) }}
          </span>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
            <Package class="h-5 w-5 text-green-600" />
          </div>
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Days Inventory Outstanding</p>
            <p class="text-2xl font-bold text-gray-900 dark:text-white">
              {{ data?.dio?.toFixed(1) || '0' }} <span class="text-sm font-normal text-gray-500">days</span>
            </p>
          </div>
        </div>
        <div class="mt-3">
          <span :class="getDIOHealthClass(data?.dio)">
            {{ getDIOHealth(data?.dio) }}
          </span>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-amber-100 dark:bg-amber-900/30 rounded-lg">
            <Clock class="h-5 w-5 text-amber-600" />
          </div>
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Days Payables Outstanding</p>
            <p class="text-2xl font-bold text-gray-900 dark:text-white">
              {{ data?.dpo?.toFixed(1) || '0' }} <span class="text-sm font-normal text-gray-500">days</span>
            </p>
          </div>
        </div>
        <div class="mt-3">
          <span :class="getDPOHealthClass(data?.dpo)">
            {{ getDPOHealth(data?.dpo) }}
          </span>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <div :class="['p-2 rounded-lg', getCCCClass(data?.cash_conversion_cycle)]">
            <RefreshCw class="h-5 w-5" :class="getCCCIconClass(data?.cash_conversion_cycle)" />
          </div>
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Cash Conversion Cycle</p>
            <p class="text-2xl font-bold" :class="getCCCTextClass(data?.cash_conversion_cycle)">
              {{ data?.cash_conversion_cycle?.toFixed(1) || '0' }} <span class="text-sm font-normal text-gray-500">days</span>
            </p>
          </div>
        </div>
        <div class="mt-3">
          <span :class="getCCCHealthClass(data?.cash_conversion_cycle)">
            {{ getCCCHealth(data?.cash_conversion_cycle) }}
          </span>
        </div>
      </div>
    </div>

    <!-- Cash Conversion Cycle Visual -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-6">Cash Conversion Cycle Breakdown</h3>
      <div class="flex flex-col md:flex-row items-center justify-center gap-4 md:gap-8">
        <!-- DSO -->
        <div class="text-center">
          <div class="w-24 h-24 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center mx-auto">
            <div>
              <p class="text-xl font-bold text-blue-600">{{ data?.dso?.toFixed(0) || 0 }}</p>
              <p class="text-xs text-blue-500">days</p>
            </div>
          </div>
          <p class="mt-2 text-sm font-medium text-gray-700 dark:text-gray-300">DSO</p>
          <p class="text-xs text-gray-500">Collect Receivables</p>
        </div>

        <div class="hidden md:block text-2xl text-gray-400">+</div>

        <!-- DIO -->
        <div class="text-center">
          <div class="w-24 h-24 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mx-auto">
            <div>
              <p class="text-xl font-bold text-green-600">{{ data?.dio?.toFixed(0) || 0 }}</p>
              <p class="text-xs text-green-500">days</p>
            </div>
          </div>
          <p class="mt-2 text-sm font-medium text-gray-700 dark:text-gray-300">DIO</p>
          <p class="text-xs text-gray-500">Sell Inventory</p>
        </div>

        <div class="hidden md:block text-2xl text-gray-400">−</div>

        <!-- DPO -->
        <div class="text-center">
          <div class="w-24 h-24 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center mx-auto">
            <div>
              <p class="text-xl font-bold text-amber-600">{{ data?.dpo?.toFixed(0) || 0 }}</p>
              <p class="text-xs text-amber-500">days</p>
            </div>
          </div>
          <p class="mt-2 text-sm font-medium text-gray-700 dark:text-gray-300">DPO</p>
          <p class="text-xs text-gray-500">Pay Suppliers</p>
        </div>

        <div class="hidden md:block text-2xl text-gray-400">=</div>

        <!-- CCC -->
        <div class="text-center">
          <div :class="['w-24 h-24 rounded-full flex items-center justify-center mx-auto', 
            (data?.cash_conversion_cycle || 0) <= 30 ? 'bg-green-100 dark:bg-green-900/30' : 
            (data?.cash_conversion_cycle || 0) <= 60 ? 'bg-amber-100 dark:bg-amber-900/30' : 'bg-red-100 dark:bg-red-900/30']">
            <div>
              <p :class="['text-xl font-bold', 
                (data?.cash_conversion_cycle || 0) <= 30 ? 'text-green-600' : 
                (data?.cash_conversion_cycle || 0) <= 60 ? 'text-amber-600' : 'text-red-600']">
                {{ data?.cash_conversion_cycle?.toFixed(0) || 0 }}
              </p>
              <p :class="['text-xs', 
                (data?.cash_conversion_cycle || 0) <= 30 ? 'text-green-500' : 
                (data?.cash_conversion_cycle || 0) <= 60 ? 'text-amber-500' : 'text-red-500']">days</p>
            </div>
          </div>
          <p class="mt-2 text-sm font-medium text-gray-700 dark:text-gray-300">CCC</p>
          <p class="text-xs text-gray-500">Cash Cycle</p>
        </div>
      </div>
    </div>

    <!-- Working Capital Components -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Current Assets -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <ArrowUpCircle class="h-5 w-5 text-green-500" />
          Current Assets
        </h3>
        <div class="space-y-4">
          <div class="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-300">Cash & Bank</span>
            <span class="text-sm font-semibold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.cash || 0) }}
            </span>
          </div>
          <div class="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-300">Accounts Receivable</span>
            <span class="text-sm font-semibold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.receivables || 0) }}
            </span>
          </div>
          <div class="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-300">Inventory</span>
            <span class="text-sm font-semibold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.inventory || 0) }}
            </span>
          </div>
          <div class="flex justify-between items-center p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
            <span class="text-sm font-bold text-green-700 dark:text-green-400">Total Current Assets</span>
            <span class="text-sm font-bold text-green-700 dark:text-green-400">
              {{ formatCurrency(data?.total_current_assets || 0) }}
            </span>
          </div>
        </div>
      </div>

      <!-- Current Liabilities -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <ArrowDownCircle class="h-5 w-5 text-red-500" />
          Current Liabilities
        </h3>
        <div class="space-y-4">
          <div class="flex justify-between items-center p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
            <span class="text-sm font-bold text-red-700 dark:text-red-400">Total Current Liabilities</span>
            <span class="text-sm font-bold text-red-700 dark:text-red-400">
              {{ formatCurrency(data?.total_current_liabilities || 0) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Net Working Capital -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h3 class="text-lg font-semibold text-gray-900 dark:text-white">Net Working Capital</h3>
          <p class="text-sm text-gray-500 dark:text-gray-400">Current Assets - Current Liabilities</p>
        </div>
        <div class="text-center md:text-right">
          <p :class="['text-3xl font-bold', (data?.working_capital || 0) >= 0 ? 'text-green-600' : 'text-red-600']">
            {{ formatCurrency(data?.working_capital || 0) }}
          </p>
          <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Current Ratio: <span class="font-semibold">{{ data?.current_ratio?.toFixed(2) || '0' }}</span>
            | Quick Ratio: <span class="font-semibold">{{ data?.quick_ratio?.toFixed(2) || '0' }}</span>
          </p>
        </div>
      </div>
    </div>

    <!-- Trend Analysis (Transposed: Months as Columns) -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <TrendingUp class="h-5 w-5 text-gray-500" />
        Working Capital Trends (Last 6 Months)
      </h3>
      <div v-if="trendMonths.length" class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead class="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase sticky left-0 bg-gray-50 dark:bg-gray-800">Metric</th>
              <th v-for="month in trendMonths" :key="month.period"
                  class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase whitespace-nowrap">
                {{ formatPeriod(month.period) }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <!-- Current Assets Row -->
            <tr class="hover:bg-gray-50 dark:hover:bg-gray-700">
              <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white sticky left-0 bg-white dark:bg-gray-800">Current Assets</td>
              <td v-for="month in trendMonths" :key="'ca-'+month.period" 
                  class="px-4 py-3 text-sm text-right text-green-600 dark:text-green-400 whitespace-nowrap">
                {{ formatCompactCurrency(month.current_assets) }}
              </td>
            </tr>
            <!-- Current Liabilities Row -->
            <tr class="hover:bg-gray-50 dark:hover:bg-gray-700">
              <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white sticky left-0 bg-white dark:bg-gray-800">Current Liabilities</td>
              <td v-for="month in trendMonths" :key="'cl-'+month.period" 
                  class="px-4 py-3 text-sm text-right text-red-600 dark:text-red-400 whitespace-nowrap">
                {{ formatCompactCurrency(Math.abs(month.current_liabilities)) }}
              </td>
            </tr>
            <!-- Working Capital Row -->
            <tr class="hover:bg-gray-50 dark:hover:bg-gray-700 font-semibold">
              <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white sticky left-0 bg-white dark:bg-gray-800">Working Capital</td>
              <td v-for="month in trendMonths" :key="'wc-'+month.period" 
                  class="px-4 py-3 text-sm text-right whitespace-nowrap"
                  :class="month.working_capital >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'">
                {{ formatCompactCurrency(month.working_capital) }}
              </td>
            </tr>
            <!-- Current Ratio Row -->
            <tr class="hover:bg-gray-50 dark:hover:bg-gray-700">
              <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white sticky left-0 bg-white dark:bg-gray-800">Current Ratio</td>
              <td v-for="month in trendMonths" :key="'cr-'+month.period" 
                  class="px-4 py-3 text-sm text-right whitespace-nowrap"
                  :class="getRatioClass(month.current_ratio)">
                {{ month.current_ratio >= 999 ? '∞' : month.current_ratio?.toFixed(2) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center py-8 text-gray-500">
        No trend data available
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import { 
  Repeat, 
  Package, 
  Clock, 
  RefreshCw, 
  ArrowUpCircle, 
  ArrowDownCircle,
  TrendingUp
} from 'lucide-vue-next'

interface Props {
  data: any
}

const props = defineProps<Props>()

const currency = inject('currency', 'KES')

// Computed property for transposed table - last 6 months
const trendMonths = computed(() => {
  return props.data?.trends?.slice(-6) || []
})

// Format period (YYYY-MM to Mon YY)
const formatPeriod = (period: string) => {
  if (!period) return ''
  const [year, month] = period.split('-')
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${monthNames[parseInt(month) - 1]} ${year.slice(2)}`
}

// Format currency in compact form
const formatCompactCurrency = (value: number | undefined) => {
  if (value === undefined || value === null) return `${currency} 0`
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absValue >= 1000000) {
    return `${sign}${currency} ${(absValue / 1000000).toFixed(1)}M`
  } else if (absValue >= 1000) {
    return `${sign}${currency} ${(absValue / 1000).toFixed(0)}K`
  }
  return `${sign}${currency} ${absValue.toFixed(0)}`
}

// Current ratio class
const getRatioClass = (ratio: number | null | undefined) => {
  if (!ratio || ratio >= 999) return 'text-green-600 dark:text-green-400'
  if (ratio >= 2) return 'text-green-600 dark:text-green-400'
  if (ratio >= 1) return 'text-amber-600 dark:text-amber-400'
  return 'text-red-600 dark:text-red-400'
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

// DSO Health
const getDSOHealth = (dso: number | null | undefined) => {
  if (!dso) return 'No data'
  if (dso <= 30) return 'Excellent'
  if (dso <= 45) return 'Good'
  if (dso <= 60) return 'Fair'
  return 'Needs Attention'
}

const getDSOHealthClass = (dso: number | null | undefined) => {
  if (!dso) return 'text-gray-500 text-xs'
  const base = 'px-2 py-0.5 rounded text-xs font-medium'
  if (dso <= 30) return `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`
  if (dso <= 45) return `${base} bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`
  if (dso <= 60) return `${base} bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400`
  return `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`
}

// DIO Health
const getDIOHealth = (dio: number | null | undefined) => {
  if (!dio) return 'No data'
  if (dio <= 30) return 'Excellent'
  if (dio <= 60) return 'Good'
  if (dio <= 90) return 'Fair'
  return 'High Inventory'
}

const getDIOHealthClass = (dio: number | null | undefined) => {
  if (!dio) return 'text-gray-500 text-xs'
  const base = 'px-2 py-0.5 rounded text-xs font-medium'
  if (dio <= 30) return `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`
  if (dio <= 60) return `${base} bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`
  if (dio <= 90) return `${base} bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400`
  return `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`
}

// DPO Health
const getDPOHealth = (dpo: number | null | undefined) => {
  if (!dpo) return 'No data'
  if (dpo >= 45) return 'Optimal'
  if (dpo >= 30) return 'Good'
  if (dpo >= 15) return 'Fast Payment'
  return 'Very Fast'
}

const getDPOHealthClass = (dpo: number | null | undefined) => {
  if (!dpo) return 'text-gray-500 text-xs'
  const base = 'px-2 py-0.5 rounded text-xs font-medium'
  if (dpo >= 45) return `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`
  if (dpo >= 30) return `${base} bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`
  if (dpo >= 15) return `${base} bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400`
  return `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`
}

// CCC Health
const getCCCHealth = (ccc: number | null | undefined) => {
  if (ccc === null || ccc === undefined) return 'No data'
  if (ccc <= 0) return 'Excellent (Negative)'
  if (ccc <= 30) return 'Good'
  if (ccc <= 60) return 'Fair'
  return 'Needs Improvement'
}

const getCCCHealthClass = (ccc: number | null | undefined) => {
  if (ccc === null || ccc === undefined) return 'text-gray-500 text-xs'
  const base = 'px-2 py-0.5 rounded text-xs font-medium'
  if (ccc <= 0) return `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`
  if (ccc <= 30) return `${base} bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`
  if (ccc <= 60) return `${base} bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400`
  return `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`
}

const getCCCClass = (ccc: number | null | undefined) => {
  if (ccc === null || ccc === undefined) return 'bg-gray-100 dark:bg-gray-700'
  if (ccc <= 30) return 'bg-green-100 dark:bg-green-900/30'
  if (ccc <= 60) return 'bg-amber-100 dark:bg-amber-900/30'
  return 'bg-red-100 dark:bg-red-900/30'
}

const getCCCIconClass = (ccc: number | null | undefined) => {
  if (ccc === null || ccc === undefined) return 'text-gray-500'
  if (ccc <= 30) return 'text-green-600'
  if (ccc <= 60) return 'text-amber-600'
  return 'text-red-600'
}

const getCCCTextClass = (ccc: number | null | undefined) => {
  if (ccc === null || ccc === undefined) return 'text-gray-900 dark:text-white'
  if (ccc <= 30) return 'text-green-600'
  if (ccc <= 60) return 'text-amber-600'
  return 'text-red-600'
}
</script>
