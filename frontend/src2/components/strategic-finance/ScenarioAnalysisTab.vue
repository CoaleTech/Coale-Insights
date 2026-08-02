<template>
  <div class="space-y-6">

    <!-- View Selector: Tabs replaces hand-rolled button group -->
    <Tabs v-model="selectedViewIndex" :tabs="viewTabs" />

    <!-- Sensitivity Analysis View -->
    <div v-if="selectedView === 'sensitivity'" class="space-y-6">

      <!-- Sensitivity Matrix -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader title="Net Profit Sensitivity Matrix" :level="3">
          <template #actions>
            <Grid3x3 class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <p class="text-sm text-ink-gray-6 mt-2 mb-4">
          Shows how net profit changes with different revenue and expense variations.
          Each cell shows the net profit value; colour is a secondary guide.
        </p>

        <div v-if="data?.sensitivity?.scenarios" class="overflow-x-auto">
          <table class="min-w-full" role="grid">
            <caption class="sr-only">
              Net profit sensitivity matrix. Rows show revenue change; columns show expense change.
              Positive values (profit) have a green background; negative values (loss) have a red background.
            </caption>
            <thead>
              <tr>
                <th
                  scope="col"
                  class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase bg-surface-gray-1 sticky left-0"
                >
                  Revenue / Expenses
                </th>
                <th
                  v-for="expenseChange in (data?.sensitivity?.expense_changes || expenseChanges)"
                  :key="expenseChange"
                  scope="col"
                  class="px-4 py-3 text-center text-xs font-medium text-ink-gray-6 uppercase bg-surface-gray-1"
                >
                  {{ formatChange(expenseChange) }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="revenueChange in (data?.sensitivity?.revenue_changes || revenueChanges)"
                :key="revenueChange"
              >
                <th
                  scope="row"
                  class="px-4 py-3 text-sm font-medium text-ink-gray-9 bg-surface-gray-1 sticky left-0"
                >
                  {{ formatChange(revenueChange) }}
                </th>
                <td
                  v-for="expenseChange in (data?.sensitivity?.expense_changes || expenseChanges)"
                  :key="expenseChange"
                  class="px-4 py-3 text-center text-sm font-medium text-ink-gray-9"
                  :class="heatmapFill(getScenarioValue(revenueChange, expenseChange))"
                >
                  {{ formatCurrency(getScenarioValue(revenueChange, expenseChange)) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="text-center py-8 text-ink-gray-6">
          No sensitivity data available
        </div>

        <!-- Heatmap legend: swatch + text -->
        <div class="mt-4 flex items-center gap-4 text-xs text-ink-gray-6" aria-hidden="true">
          <div class="flex items-center gap-2">
            <div class="w-4 h-4 rounded bg-surface-green-3"></div>
            <span>Positive (Profit)</span>
          </div>
          <div class="flex items-center gap-2">
            <div class="w-4 h-4 rounded bg-surface-red-5"></div>
            <span>Negative (Loss)</span>
          </div>
        </div>
      </div>

      <!-- Predefined Scenarios: neutral cards with text labels (identity not severity) -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader title="Predefined Business Scenarios" :level="3">
          <template #actions>
            <GitBranch class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
          <!-- Best Case -->
          <div class="p-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1">
            <div class="flex items-center gap-2 mb-3">
              <TrendingUp class="h-5 w-5 text-ink-gray-5" />
              <h4 class="font-semibold text-ink-gray-9">Best Case (P95)</h4>
              <Badge label="Optimistic" variant="subtle" theme="gray" size="sm" />
            </div>
            <div class="space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-ink-gray-6">Net Income</span>
                <span class="font-bold text-ink-gray-9">
                  {{ formatCurrency(data?.monte_carlo?.percentiles?.p95 || 0) }}
                </span>
              </div>
              <div class="flex justify-between">
                <span class="text-ink-gray-6">Probability</span>
                <span class="font-medium text-ink-gray-7">5% better than this</span>
              </div>
            </div>
          </div>

          <!-- Base Case -->
          <div class="p-4 rounded-lg border border-outline-gray-1 bg-surface-white">
            <div class="flex items-center gap-2 mb-3">
              <Target class="h-5 w-5 text-ink-gray-5" />
              <h4 class="font-semibold text-ink-gray-9">Base Case (Actual)</h4>
              <Badge label="Baseline" variant="subtle" theme="gray" size="sm" />
            </div>
            <div class="space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-ink-gray-6">Revenue</span>
                <span class="font-medium text-ink-gray-8">{{ formatCurrency(data?.baseline?.revenue || 0) }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-ink-gray-6">Expenses</span>
                <span class="font-medium text-ink-gray-8">{{ formatCurrency(data?.baseline?.expenses || 0) }}</span>
              </div>
              <div class="pt-2 border-t border-outline-gray-1">
                <div class="flex justify-between">
                  <span class="text-ink-gray-6">Net Income</span>
                  <span class="font-bold text-ink-gray-9">
                    {{ formatCurrency(data?.baseline?.net_income || 0) }}
                  </span>
                </div>
                <div class="flex justify-between mt-1">
                  <span class="text-ink-gray-6">Tax (30%)</span>
                  <span class="font-medium text-ink-gray-7">
                    {{ formatCurrency(data?.baseline?.tax || 0) }}
                  </span>
                </div>
                <div class="flex justify-between mt-1">
                  <span class="text-ink-gray-6">Net After Tax</span>
                  <span class="font-bold text-ink-gray-9">
                    {{ formatCurrency(data?.baseline?.net_after_tax || 0) }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Worst Case -->
          <div class="p-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1">
            <div class="flex items-center gap-2 mb-3">
              <TrendingDown class="h-5 w-5 text-ink-gray-5" />
              <h4 class="font-semibold text-ink-gray-9">Worst Case (P5)</h4>
              <Badge label="Pessimistic" variant="outline" theme="gray" size="sm" />
            </div>
            <div class="space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-ink-gray-6">Net Income</span>
                <span class="font-bold text-ink-gray-9">
                  {{ formatCurrency(data?.monte_carlo?.percentiles?.p5 || 0) }}
                </span>
              </div>
              <div class="flex justify-between">
                <span class="text-ink-gray-6">Probability</span>
                <span class="font-medium text-ink-gray-7">95% better than this</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Break-Even Analysis -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader title="Break-Even Analysis" :level="3">
          <template #actions>
            <Scale class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mt-4">
          <div class="text-center p-4 bg-surface-gray-1 rounded-lg">
            <p class="text-sm text-ink-gray-6 mb-1">Break-Even Revenue</p>
            <p class="text-xl font-bold text-ink-gray-9">
              {{ formatCurrency(data?.break_even?.revenue || 0) }}
            </p>
          </div>
          <div class="text-center p-4 bg-surface-gray-1 rounded-lg">
            <p class="text-sm text-ink-gray-6 mb-1">Current Revenue</p>
            <p class="text-xl font-bold text-ink-gray-9">
              {{ formatCurrency(data?.break_even?.current_revenue || 0) }}
            </p>
          </div>
          <div class="text-center p-4 bg-surface-gray-1 rounded-lg">
            <p class="text-sm text-ink-gray-6 mb-1">Margin of Safety</p>
            <p class="text-xl font-bold text-ink-gray-9">
              {{ data?.break_even?.margin_of_safety?.toFixed(1) || 0 }}%
            </p>
          </div>
          <div class="text-center p-4 bg-surface-gray-1 rounded-lg">
            <p class="text-sm text-ink-gray-6 mb-1">Contribution Margin</p>
            <p class="text-xl font-bold text-ink-gray-9">
              {{ data?.break_even?.contribution_margin?.toFixed(1) || 0 }}%
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Monte Carlo Simulation View -->
    <div v-else-if="selectedView === 'montecarlo'" class="space-y-6">

      <!-- Simulation Summary -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader title="Monte Carlo Simulation Results" :level="3">
          <template #actions>
            <Dices class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <p class="text-sm text-ink-gray-6 mt-2 mb-4">
          Based on {{ data?.monte_carlo?.simulations || 1000 }} simulations with random revenue (+/-20%) and expense (+/-15%) variations.
        </p>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div class="p-4 bg-surface-gray-1 rounded-lg text-center">
            <p class="text-sm text-ink-gray-6 mb-1">Mean Net Profit</p>
            <p class="text-xl font-bold text-ink-gray-9">{{ formatCurrency(data?.monte_carlo?.mean || 0) }}</p>
          </div>
          <div class="p-4 bg-surface-gray-1 rounded-lg text-center">
            <p class="text-sm text-ink-gray-6 mb-1">Std Deviation</p>
            <p class="text-xl font-bold text-ink-gray-9">{{ formatCurrency(data?.monte_carlo?.std || 0) }}</p>
          </div>
          <div class="p-4 bg-surface-gray-1 rounded-lg text-center">
            <p class="text-sm text-ink-gray-6 mb-1">Minimum</p>
            <p class="text-xl font-bold text-ink-red-4">{{ formatCurrency(data?.monte_carlo?.min || 0) }}</p>
          </div>
          <div class="p-4 bg-surface-gray-1 rounded-lg text-center">
            <p class="text-sm text-ink-gray-6 mb-1">Maximum</p>
            <p class="text-xl font-bold text-ink-gray-9">{{ formatCurrency(data?.monte_carlo?.max || 0) }}</p>
          </div>
        </div>
      </div>

      <!-- Percentile Distribution -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader title="Probability Distribution" :level="3">
          <template #actions>
            <BarChart3 class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <div class="space-y-4 mt-4">
          <div v-for="percentile in percentiles" :key="percentile.label" class="flex items-center gap-4">
            <div class="w-20 text-sm font-medium text-ink-gray-7">{{ percentile.label }}</div>
            <div
              class="flex-1 h-8 bg-surface-gray-2 rounded-lg overflow-hidden relative"
              :aria-label="`${percentile.label}: ${formatCurrency(percentile.value)}`"
              role="img"
            >
              <div
                class="h-full transition-all motion-reduce:transition-none duration-500"
                :class="percentile.fill"
                :style="{ width: `${getPercentileWidth(percentile.value)}%` }"
              ></div>
              <span class="absolute inset-y-0 flex items-center pl-2 text-sm font-medium text-ink-gray-9">
                {{ formatCurrency(percentile.value) }}
              </span>
            </div>
          </div>
        </div>

        <div class="mt-6 p-4 bg-surface-gray-1 rounded-lg">
          <div class="flex items-start gap-3">
            <Info class="h-5 w-5 text-ink-gray-5 flex-shrink-0 mt-0.5" />
            <div class="text-sm text-ink-gray-7">
              <p class="font-medium text-ink-gray-8 mb-1">How to interpret:</p>
              <ul class="list-disc list-inside space-y-1 text-ink-gray-6">
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

      <!-- Risk Probability Analysis -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader title="Risk Probability Analysis" :level="3">
          <template #actions>
            <AlertTriangle class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mt-4">
          <!-- Probability of Loss -->
          <div class="p-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1">
            <div class="flex items-center gap-2 mb-2">
              <TrendingDown class="h-5 w-5 text-ink-gray-5" />
              <span class="font-semibold text-ink-gray-9">Probability of Loss</span>
            </div>
            <p class="text-3xl font-bold text-ink-gray-9">
              {{ formatPercent(data?.monte_carlo?.probability_of_loss) }}
            </p>
            <p class="text-sm text-ink-gray-6 mt-2">Chance of negative net profit</p>
            <Badge
              v-bind="lossProbBadge"
              :label="lossProbBadge.label"
              size="sm"
              class="mt-2"
            />
          </div>

          <!-- Value at Risk -->
          <div class="p-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1">
            <div class="flex items-center gap-2 mb-2">
              <Shield class="h-5 w-5 text-ink-gray-5" />
              <span class="font-semibold text-ink-gray-9">Value at Risk (5%)</span>
            </div>
            <p class="text-3xl font-bold text-ink-gray-9">
              {{ formatCurrency(data?.monte_carlo?.percentiles?.p5 || 0) }}
            </p>
            <p class="text-sm text-ink-gray-6 mt-2">Worst expected outcome at 95% confidence</p>
          </div>

          <!-- Target Achievement -->
          <div class="p-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1">
            <div class="flex items-center gap-2 mb-2">
              <Target class="h-5 w-5 text-ink-gray-5" />
              <span class="font-semibold text-ink-gray-9">Target Achievement</span>
            </div>
            <p class="text-3xl font-bold text-ink-gray-9">
              {{ formatPercent(data?.monte_carlo?.target_probability) }}
            </p>
            <p class="text-sm text-ink-gray-6 mt-2">Probability of exceeding target profit</p>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { NO_VALUE } from '../../utils/format'
import { ref, computed, inject, isRef, type Ref } from 'vue'
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
  Shield,
} from 'lucide-vue-next'
import { Tabs, Badge } from 'frappe-ui'
import { scoreSeverity, severityBadge, type BadgeSpec } from '../../utils/status'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'

interface ScenarioEntry {
  revenue_change: number
  expense_change: number
  net_income: number
}

interface MonteCarloPercentiles {
  p5?: number
  p10?: number
  p25?: number
  p50?: number
  p75?: number
  p90?: number
  p95?: number
}

interface ScenarioData {
  sensitivity?: {
    scenarios?: ScenarioEntry[]
    expense_changes?: number[]
    revenue_changes?: number[]
  }
  monte_carlo?: {
    percentiles?: MonteCarloPercentiles
    probability_of_loss?: number
    target_probability?: number
    simulations?: number
    mean?: number
    std?: number
    min?: number
    max?: number
  }
  baseline?: {
    revenue?: number
    expenses?: number
    net_income?: number
    tax?: number
    net_after_tax?: number
  }
  break_even?: {
    revenue?: number
    current_revenue?: number
    margin_of_safety?: number
    contribution_margin?: number
  }
}

interface Props {
  data?: ScenarioData
}

const props = defineProps<Props>()

const _currency = inject<string | Ref<string>>('currency', 'KES')
const getCurrency = () =>
  (isRef(_currency) ? _currency.value : _currency) || 'KES'

// Tabs model: numeric index mapped to string key
const viewTabs = [
  { label: 'Sensitivity Analysis' },
  { label: 'Monte Carlo Simulation' },
]
const viewKeys = ['sensitivity', 'montecarlo']
const selectedViewIndex = ref(0)
const selectedView = computed(() => viewKeys[selectedViewIndex.value])

const revenueChanges = [-30, -20, -10, 0, 10, 20, 30]
const expenseChanges = [-20, -10, 0, 10, 20]

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

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined) return NO_VALUE
  return `${value.toFixed(1)}%`
}

const formatChange = (value: number) => (value > 0 ? `+${value}%` : `${value}%`)

const getScenarioValue = (revenueChange: number, expenseChange: number): number => {
  if (!props.data?.sensitivity?.scenarios) return 0
  const scenario = props.data.sensitivity.scenarios.find(
    (s) => s.revenue_change === revenueChange && s.expense_change === expenseChange
  )
  return scenario?.net_income || 0
}

// Non-text surface fills for heatmap cells (>=3:1 on white).
// Neutral cell for zero. Text inside each cell carries the number.
const heatmapFill = (value: number): string => {
  if (value > 0) return 'bg-surface-green-3'
  if (value < 0) return 'bg-surface-red-5'
  return 'bg-surface-gray-2'
}

// Percentile bars use non-text fills; text label is always rendered
const percentiles = computed(() => {
  if (!props.data?.monte_carlo?.percentiles) return []
  const p = props.data.monte_carlo.percentiles
  return [
    { label: '5th %ile', value: p.p5 || 0, fill: 'bg-surface-red-5' },
    { label: '10th %ile', value: p.p10 || 0, fill: 'bg-surface-red-5' },
    { label: '25th %ile', value: p.p25 || 0, fill: 'bg-surface-amber-3' },
    { label: '50th %ile', value: p.p50 || 0, fill: 'bg-surface-blue-3' },
    { label: '75th %ile', value: p.p75 || 0, fill: 'bg-surface-green-3' },
    { label: '90th %ile', value: p.p90 || 0, fill: 'bg-surface-green-3' },
    { label: '95th %ile', value: p.p95 || 0, fill: 'bg-surface-green-3' },
  ]
})

const getPercentileWidth = (value: number): number => {
  if (!props.data?.monte_carlo?.percentiles) return 0
  const p = props.data.monte_carlo.percentiles
  const max = p.p95 || 1
  const min = p.p5 || 0
  const range = max - min
  if (range === 0) return 50
  return Math.max(10, Math.min(100, ((value - min) / range) * 100))
}

// Loss probability badge: severity from threshold
const lossProbBadge = computed((): BadgeSpec => {
  const prob = props.data?.monte_carlo?.probability_of_loss
  const sev = scoreSeverity(prob, { good: 10, warn: 25, higherIsBetter: false })
  return severityBadge(sev)
})
</script>
