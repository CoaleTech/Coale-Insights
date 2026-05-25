<template>
  <div class="space-y-6">
    <!-- Scenario Type Selector -->
    <div class="flex gap-4 mb-6">
      <button
        @click="selectedView = 'sensitivity'"
        :class="[
          'px-4 py-2 rounded-lg font-medium transition-colors',
          selectedView === 'sensitivity'
            ? 'bg-blue-600 text-white'
            : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
        ]"
      >
        <Sliders class="inline h-4 w-4 mr-2" />
        Sensitivity Analysis
      </button>
      <button
        @click="selectedView = 'montecarlo'"
        :class="[
          'px-4 py-2 rounded-lg font-medium transition-colors',
          selectedView === 'montecarlo'
            ? 'bg-purple-600 text-white'
            : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
        ]"
      >
        <Dices class="inline h-4 w-4 mr-2" />
        Monte Carlo Simulation
      </button>
    </div>

    <!-- Sensitivity Analysis View -->
    <div v-if="selectedView === 'sensitivity'" class="space-y-6">
      <!-- Sensitivity Matrix -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Grid3x3 class="h-5 w-5 text-gray-500" />
          Net Profit Sensitivity Matrix
        </h3>
        <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Shows how net profit changes with different revenue and expense variations
        </p>
        
        <div v-if="data?.sensitivity?.scenarios" class="overflow-x-auto">
          <table class="min-w-full">
            <thead>
              <tr>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase bg-gray-50 dark:bg-gray-800 sticky left-0">
                  Revenue ↓ / Expenses →
                </th>
                <th v-for="expenseChange in (data?.sensitivity?.expense_changes || expenseChanges)" :key="expenseChange" 
                    class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase bg-gray-50 dark:bg-gray-800">
                  {{ formatChange(expenseChange) }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="revenueChange in (data?.sensitivity?.revenue_changes || revenueChanges)" :key="revenueChange">
                <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white bg-gray-50 dark:bg-gray-800 sticky left-0">
                  {{ formatChange(revenueChange) }}
                </td>
                <td v-for="expenseChange in (data?.sensitivity?.expense_changes || expenseChanges)" :key="expenseChange"
                    :class="[
                      'px-4 py-3 text-center text-sm font-medium',
                      getCellClass(getScenarioValue(revenueChange, expenseChange))
                    ]">
                  {{ formatCurrency(getScenarioValue(revenueChange, expenseChange)) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="text-center py-8 text-gray-500">
          No sensitivity data available
        </div>
        
        <div class="mt-4 flex items-center gap-4 text-xs text-gray-500">
          <div class="flex items-center gap-2">
            <div class="w-4 h-4 rounded bg-green-500"></div>
            <span>Positive (Profit)</span>
          </div>
          <div class="flex items-center gap-2">
            <div class="w-4 h-4 rounded bg-red-500"></div>
            <span>Negative (Loss)</span>
          </div>
        </div>
      </div>

      <!-- Predefined Scenarios -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <GitBranch class="h-5 w-5 text-gray-500" />
          Predefined Business Scenarios
        </h3>
        
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <!-- Best Case from Named Scenarios -->
          <div class="p-4 rounded-lg border-2 border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20">
            <div class="flex items-center gap-2 mb-3">
              <TrendingUp class="h-5 w-5 text-green-600" />
              <h4 class="font-semibold text-green-700 dark:text-green-400">Best Case (P95)</h4>
            </div>
            <div class="space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-gray-600 dark:text-gray-400">Net Income</span>
                <span class="font-bold text-green-700 dark:text-green-400">
                  {{ formatCurrency(data?.monte_carlo?.percentiles?.p95 || 0) }}
                </span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-600 dark:text-gray-400">Probability</span>
                <span class="font-medium text-green-600">5% better than this</span>
              </div>
            </div>
          </div>

          <!-- Base Case from Baseline -->
          <div class="p-4 rounded-lg border-2 border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20">
            <div class="flex items-center gap-2 mb-3">
              <Target class="h-5 w-5 text-blue-600" />
              <h4 class="font-semibold text-blue-700 dark:text-blue-400">Base Case (Actual)</h4>
            </div>
            <div class="space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-gray-600 dark:text-gray-400">Revenue</span>
                <span class="font-medium text-blue-600">{{ formatCurrency(data?.baseline?.revenue || 0) }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-600 dark:text-gray-400">Expenses</span>
                <span class="font-medium text-blue-600">{{ formatCurrency(data?.baseline?.expenses || 0) }}</span>
              </div>
              <div class="pt-2 border-t border-blue-200 dark:border-blue-800">
                <div class="flex justify-between">
                  <span class="text-gray-600 dark:text-gray-400">Net Income</span>
                  <span class="font-bold text-blue-700 dark:text-blue-400">
                    {{ formatCurrency(data?.baseline?.net_income || 0) }}
                  </span>
                </div>
                <div class="flex justify-between mt-1">
                  <span class="text-gray-600 dark:text-gray-400">Tax (30%)</span>
                  <span class="font-medium text-gray-700 dark:text-gray-300">
                    {{ formatCurrency(data?.baseline?.tax || 0) }}
                  </span>
                </div>
                <div class="flex justify-between mt-1">
                  <span class="text-gray-600 dark:text-gray-400">Net After Tax</span>
                  <span class="font-bold text-blue-700 dark:text-blue-400">
                    {{ formatCurrency(data?.baseline?.net_after_tax || 0) }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Worst Case from Named Scenarios -->
          <div class="p-4 rounded-lg border-2 border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20">
            <div class="flex items-center gap-2 mb-3">
              <TrendingDown class="h-5 w-5 text-red-600" />
              <h4 class="font-semibold text-red-700 dark:text-red-400">Worst Case (P5)</h4>
            </div>
            <div class="space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-gray-600 dark:text-gray-400">Net Income</span>
                <span class="font-bold text-red-700 dark:text-red-400">
                  {{ formatCurrency(data?.monte_carlo?.percentiles?.p5 || 0) }}
                </span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-600 dark:text-gray-400">Probability</span>
                <span class="font-medium text-red-600">95% better than this</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Break-Even Analysis -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Scale class="h-5 w-5 text-gray-500" />
          Break-Even Analysis
        </h3>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div class="text-center p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Break-Even Revenue</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.break_even?.revenue || 0) }}
            </p>
          </div>
          <div class="text-center p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Current Revenue</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.break_even?.current_revenue || 0) }}
            </p>
          </div>
          <div class="text-center p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Margin of Safety</p>
            <p class="text-xl font-bold text-green-600">
              {{ data?.break_even?.margin_of_safety?.toFixed(1) || 0 }}%
            </p>
          </div>
          <div class="text-center p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Contribution Margin</p>
            <p class="text-xl font-bold text-blue-600">
              {{ data?.break_even?.contribution_margin?.toFixed(1) || 0 }}%
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Monte Carlo Simulation View -->
    <div v-else-if="selectedView === 'montecarlo'" class="space-y-6">
      <!-- Simulation Summary -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Dices class="h-5 w-5 text-purple-500" />
          Monte Carlo Simulation Results
        </h3>
        <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Based on {{ data?.monte_carlo?.simulations || 1000 }} simulations with random revenue (±20%) and expense (±15%) variations
        </p>

        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div class="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Mean Net Profit</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.monte_carlo?.mean || 0) }}
            </p>
          </div>
          <div class="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Std Deviation</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.monte_carlo?.std || 0) }}
            </p>
          </div>
          <div class="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Minimum</p>
            <p class="text-xl font-bold text-red-600">
              {{ formatCurrency(data?.monte_carlo?.min || 0) }}
            </p>
          </div>
          <div class="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Maximum</p>
            <p class="text-xl font-bold text-green-600">
              {{ formatCurrency(data?.monte_carlo?.max || 0) }}
            </p>
          </div>
        </div>
      </div>

      <!-- Percentile Distribution -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <BarChart3 class="h-5 w-5 text-gray-500" />
          Probability Distribution
        </h3>
        
        <div class="space-y-4">
          <!-- Percentile bars -->
          <div v-for="percentile in percentiles" :key="percentile.label" class="flex items-center gap-4">
            <div class="w-20 text-sm font-medium text-gray-700 dark:text-gray-300">
              {{ percentile.label }}
            </div>
            <div class="flex-1 h-8 bg-gray-200 dark:bg-gray-700 rounded-lg overflow-hidden relative">
              <div 
                class="h-full transition-all duration-500"
                :class="percentile.color"
                :style="{ width: `${getPercentileWidth(percentile.value)}%` }"
              ></div>
              <span class="absolute inset-y-0 flex items-center pl-2 text-sm font-medium" 
                    :class="percentile.value > 0 ? 'text-white' : 'text-gray-700 dark:text-gray-300'">
                {{ formatCurrency(percentile.value) }}
              </span>
            </div>
          </div>
        </div>

        <div class="mt-6 p-4 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
          <div class="flex items-start gap-3">
            <Info class="h-5 w-5 text-purple-600 flex-shrink-0 mt-0.5" />
            <div class="text-sm text-gray-700 dark:text-gray-300">
              <p class="font-medium text-purple-700 dark:text-purple-400 mb-1">How to interpret:</p>
              <ul class="list-disc list-inside space-y-1 text-gray-600 dark:text-gray-400">
                <li><strong>5th Percentile:</strong> 95% of outcomes will be better than this</li>
                <li><strong>25th Percentile:</strong> 75% of outcomes will be better than this</li>
                <li><strong>50th Percentile (Median):</strong> Half of outcomes above, half below</li>
                <li><strong>75th Percentile:</strong> 25% of outcomes will be better than this</li>
                <li><strong>95th Percentile:</strong> Only 5% of outcomes will be better than this</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <!-- Risk Probability -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <AlertTriangle class="h-5 w-5 text-amber-500" />
          Risk Probability Analysis
        </h3>
        
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
          <!-- Probability of Loss -->
          <div class="p-4 rounded-lg" :class="getLossProbClass(data?.monte_carlo?.probability_of_loss)">
            <div class="flex items-center gap-2 mb-2">
              <TrendingDown class="h-5 w-5" />
              <span class="font-semibold">Probability of Loss</span>
            </div>
            <p class="text-3xl font-bold">
              {{ formatPercent(data?.monte_carlo?.probability_of_loss) }}
            </p>
            <p class="text-sm mt-2 opacity-80">
              Chance of negative net profit
            </p>
          </div>

          <!-- Value at Risk -->
          <div class="p-4 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400">
            <div class="flex items-center gap-2 mb-2">
              <Shield class="h-5 w-5" />
              <span class="font-semibold">Value at Risk (5%)</span>
            </div>
            <p class="text-3xl font-bold">
              {{ formatCurrency(data?.monte_carlo?.percentiles?.p5 || 0) }}
            </p>
            <p class="text-sm mt-2 opacity-80">
              Worst expected outcome at 95% confidence
            </p>
          </div>

          <!-- Probability of Target -->
          <div class="p-4 rounded-lg bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400">
            <div class="flex items-center gap-2 mb-2">
              <Target class="h-5 w-5" />
              <span class="font-semibold">Target Achievement</span>
            </div>
            <p class="text-3xl font-bold">
              {{ formatPercent(data?.monte_carlo?.target_probability) }}
            </p>
            <p class="text-sm mt-2 opacity-80">
              Probability of exceeding target profit
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject } from 'vue'
import { 
  Sliders, 
  Dices, 
  Grid3x3, 
  GitBranch, 
  TrendingUp, 
  TrendingDown,
  Target,
  Scale,
  BarChart3,
  Info,
  AlertTriangle,
  Shield
} from 'lucide-vue-next'

interface Props {
  data: any
}

const props = defineProps<Props>()

const _currency = inject('currency', 'KES')
const getCurrency = () => (typeof _currency === 'string' ? _currency : (_currency as any)?.value) || 'KES'
const selectedView = ref('sensitivity')

const revenueChanges = [-30, -20, -10, 0, 10, 20, 30]
const expenseChanges = [-20, -10, 0, 10, 20]

const formatCurrency = (value: number) => {
  if (value === null || value === undefined) return `${getCurrency()} 0`
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: getCurrency(),
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '0%'
  return `${value.toFixed(1)}%`
}

const formatChange = (value: number) => {
  return value > 0 ? `+${value}%` : `${value}%`
}

// Find scenario value from the scenarios array
const getScenarioValue = (revenueChange: number, expenseChange: number) => {
  if (!props.data?.sensitivity?.scenarios) return 0
  const scenario = props.data.sensitivity.scenarios.find(
    (s: any) => s.revenue_change === revenueChange && s.expense_change === expenseChange
  )
  return scenario?.net_income || 0
}

const getCellClass = (value: number) => {
  if (value > 0) {
    const intensity = Math.min(Math.abs(value) / 1000000, 1)
    return `bg-green-${Math.round(intensity * 5 + 1)}00 text-green-900 dark:text-green-100`
  } else if (value < 0) {
    const intensity = Math.min(Math.abs(value) / 1000000, 1)
    return `bg-red-${Math.round(intensity * 5 + 1)}00 text-red-900 dark:text-red-100`
  }
  return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
}

// Percentile data for Monte Carlo
const percentiles = computed(() => {
  if (!props.data?.monte_carlo?.percentiles) return []
  const p = props.data.monte_carlo.percentiles
  return [
    { label: '5th %ile', value: p.p5 || 0, color: 'bg-red-500' },
    { label: '10th %ile', value: p.p10 || 0, color: 'bg-red-400' },
    { label: '25th %ile', value: p.p25 || 0, color: 'bg-amber-500' },
    { label: '50th %ile', value: p.p50 || 0, color: 'bg-blue-500' },
    { label: '75th %ile', value: p.p75 || 0, color: 'bg-green-400' },
    { label: '90th %ile', value: p.p90 || 0, color: 'bg-green-500' },
    { label: '95th %ile', value: p.p95 || 0, color: 'bg-green-600' }
  ]
})

const getPercentileWidth = (value: number) => {
  if (!props.data?.monte_carlo?.percentiles) return 0
  const p = props.data.monte_carlo.percentiles
  const max = p.p95 || 1
  const min = p.p5 || 0
  const range = max - min
  if (range === 0) return 50
  return Math.max(10, Math.min(100, ((value - min) / range) * 100))
}

const getLossProbClass = (probability: number | null | undefined) => {
  if (!probability) return 'bg-gray-50 dark:bg-gray-700/50 text-gray-700 dark:text-gray-300'
  if (probability <= 10) return 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
  if (probability <= 25) return 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400'
  return 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
}
</script>
