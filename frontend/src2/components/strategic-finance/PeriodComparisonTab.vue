<template>
  <div class="space-y-6">

    <!-- Period Selector: frappe-ui Tabs replaces hand-rolled button group -->
    <Tabs v-model="selectedPeriodIndex" :tabs="periodTabs" />

    <!-- Comparison Summary Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <KpiCard
        label="Revenue"
        :amount="currentPeriodData?.current_revenue ?? 0"
        :currency="currencyVal"
        :delta="currentPeriodData?.revenue_change"
        :delta-higher-is-better="true"
        :sublabel="`vs ${formatCurrency(currentPeriodData?.previous_revenue ?? 0)}`"
        :loading="!data"
      />
      <KpiCard
        label="Expenses"
        :amount="currentPeriodData?.current_expenses ?? 0"
        :currency="currencyVal"
        :delta="currentPeriodData?.expense_change"
        :delta-higher-is-better="false"
        :sublabel="`vs ${formatCurrency(currentPeriodData?.previous_expenses ?? 0)}`"
        :loading="!data"
      />
      <KpiCard
        label="Net Profit"
        :amount="currentPeriodData?.current_profit ?? 0"
        :currency="currencyVal"
        :delta="currentPeriodData?.profit_change"
        :delta-higher-is-better="true"
        :sublabel="`vs ${formatCurrency(currentPeriodData?.previous_profit ?? 0)}`"
        :loading="!data"
      />
      <KpiCard
        label="Margin"
        :value="`${(currentPeriodData?.current_margin ?? 0).toFixed(1)}%`"
        :sublabel="`${formatBps(currentPeriodData?.margin_change)}`"
        :loading="!data"
      />
    </div>

    <!-- Detailed Comparison Table -->
    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <SectionHeader variant="caption" :title="`Detailed ${selectedPeriodLabel} Comparison`" :level="3">
        <template #actions>
          <BarChart3 class="h-5 w-5 text-ink-gray-5" />
        </template>
      </SectionHeader>
      <div class="overflow-x-auto mt-4">
        <table class="min-w-full divide-y divide-outline-gray-1">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Metric</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Current Period</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Previous Period</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Change</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">% Change</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-1">
            <tr v-for="item in comparisonItems" :key="item.label" class="hover:bg-surface-gray-1">
              <td class="px-4 py-3 text-sm font-medium text-ink-gray-9">{{ item.label }}</td>
              <td class="px-4 py-3 text-sm text-right text-ink-gray-9">
                {{ formatCurrency(item.current) }}
              </td>
              <td class="px-4 py-3 text-sm text-right text-ink-gray-6">
                {{ formatCurrency(item.previous) }}
              </td>
              <td
                class="px-4 py-3 text-sm text-right font-medium"
                :class="deltaInk(item.change, { higherIsBetter: !item.invertColors })"
              >
                {{ formatCurrency(item.change) }}
              </td>
              <td class="px-4 py-3 text-sm text-right">
                <span :class="deltaInk(item.percentChange, { higherIsBetter: !item.invertColors })">
                  {{ deltaGlyph(item.percentChange) }}{{ formatChange(item.percentChange) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Period Comparison Summary Table -->
    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <SectionHeader variant="caption" title="Period Comparison Summary" :level="3">
        <template #actions>
          <TrendingUp class="h-5 w-5 text-ink-gray-5" />
        </template>
      </SectionHeader>
      <div v-if="summaryRows.length" class="overflow-x-auto mt-4">
        <table class="min-w-full divide-y divide-outline-gray-1">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Comparison</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Revenue Change</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Expense Change</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Net Income Change</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-1">
            <tr
              v-for="(item, index) in summaryRows"
              :key="index"
              class="hover:bg-surface-gray-1"
            >
              <td class="px-4 py-3 text-sm font-medium text-ink-gray-9">{{ item.comparison }}</td>
              <td class="px-4 py-3 text-sm text-right">
                <span :class="deltaInk(item.revenue_change)">
                  {{ deltaGlyph(item.revenue_change) }}{{ formatChange(item.revenue_change) }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-right">
                <!-- Expenses: lower is better (higherIsBetter: false) -->
                <span :class="deltaInk(item.expense_change, { higherIsBetter: false })">
                  {{ deltaGlyph(item.expense_change) }}{{ formatChange(item.expense_change) }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-right">
                <span :class="deltaInk(item.net_income_change)">
                  {{ deltaGlyph(item.net_income_change) }}{{ formatChange(item.net_income_change) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center py-8 text-ink-gray-6 mt-4">
        No comparison data available
      </div>
    </div>

    <!-- Key Insights -->
    <div
      v-if="currentPeriodData?.insights?.length"
      class="rounded-lg border border-outline-gray-1 bg-surface-white p-6"
    >
      <SectionHeader variant="caption" title="Key Insights" :level="3">
        <template #actions>
          <Lightbulb class="h-5 w-5 text-ink-gray-5" />
        </template>
      </SectionHeader>
      <div class="space-y-3 mt-4">
        <div
          v-for="(insight, index) in currentPeriodData.insights"
          :key="index"
          class="p-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1"
        >
          <div class="flex items-start gap-3">
            <component :is="getInsightIcon(insight.type)" class="h-5 w-5 text-ink-gray-5 flex-shrink-0 mt-0.5" />
            <div class="flex items-start gap-2">
              <Badge v-bind="insightBadge(insight.type)" :label="insightBadge(insight.type).label" size="sm" />
              <p class="text-ink-gray-7">{{ insight.message }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, markRaw, type Ref } from 'vue'
import { useCurrency } from '../../composables/useCurrency'
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Lightbulb,
  CheckCircle2,
  AlertTriangle,
  Info,
} from 'lucide-vue-next'
import { Tabs, Badge } from 'frappe-ui'
import {
  deltaGlyph,
  deltaInk,
  severityBadge,
  type BadgeSpec,
  type Severity,
} from '../../utils/status'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import type { PeriodComparisonData, PeriodComparison, PeriodComparisonSummaryRow } from './types'

interface InsightItem {
  type: string
  title?: string
  message?: string
  description?: string
}



interface Props {
  data?: PeriodComparisonData
}

const props = defineProps<Props>()

const currency = useCurrency('')
const getCurrency = () => currency.value
const currencyVal = computed(() => getCurrency())

// Tabs model: numeric index; computed string key used downstream
const periodTabs = [
  { label: 'Month-over-Month' },
  { label: 'Quarter-over-Quarter' },
  { label: 'Year-over-Year' },
]
const periodKeys = ['mom', 'qoq', 'yoy'] as const
const selectedPeriodIndex = ref(0)
const selectedPeriod = computed(() => periodKeys[selectedPeriodIndex.value])
const selectedPeriodLabel = computed(() => periodTabs[selectedPeriodIndex.value]?.label || '')

const currentPeriodData = computed(() => {
  if (!props.data) return null
  const periodData: PeriodComparison | undefined = props.data[selectedPeriod.value]
  if (!periodData) return null
  // `current` and `prior` are nested objects, verified against
  // insights/ml/strategic_finance/scenarios.py:277-282. Flattening them here
  // keeps the template bindings unchanged.
  const current = periodData.current ?? {}
  const prior = periodData.prior ?? {}
  return {
    current_revenue: current.revenue || 0,
    previous_revenue: prior.revenue || 0,
    current_expenses: current.expenses || 0,
    previous_expenses: prior.expenses || 0,
    current_profit: current.net_income || 0,
    previous_profit: prior.net_income || 0,
    current_margin: current.margin || 0,
    previous_margin: prior.margin || 0,
    revenue_change: periodData.revenue_change || 0,
    expense_change: periodData.expense_change || 0,
    profit_change: periodData.net_income_change || 0,
    margin_change: (current.margin || 0) - (prior.margin || 0),
    current_label: current.label || 'Current',
    prior_label: prior.label || 'Prior',
    insights: periodData.insights,
  }
})

const summaryRows = computed(() => props.data?.summary ?? [])

const comparisonItems = computed(() => {
  const d = currentPeriodData.value
  if (!d) return []
  return [
    {
      label: 'Revenue',
      current: d.current_revenue,
      previous: d.previous_revenue,
      change: d.current_revenue - d.previous_revenue,
      percentChange: d.revenue_change,
      invertColors: false,
    },
    {
      label: 'Total Expenses',
      current: d.current_expenses,
      previous: d.previous_expenses,
      change: d.current_expenses - d.previous_expenses,
      percentChange: d.expense_change,
      invertColors: true,
    },
    {
      label: 'Net Profit',
      current: d.current_profit,
      previous: d.previous_profit,
      change: d.current_profit - d.previous_profit,
      percentChange: d.profit_change,
      invertColors: false,
    },
  ]
})

import { formatMoney, NO_VALUE } from '../../utils/format'

const formatCurrency = (value: number | null | undefined) => formatMoney(value, getCurrency())

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined) return NO_VALUE
  return `${value.toFixed(1)}%`
}

const formatChange = (value: number | null | undefined) => {
  if (value === null || value === undefined) return NO_VALUE
  return `${Math.abs(value).toFixed(1)}%`
}

const formatBps = (value: number | null | undefined) => {
  if (value === null || value === undefined) return NO_VALUE
  const sign = value > 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(0)} bps`
}

/**
 * Insight type maps onto the shared severity vocabulary, then overrides only the
 * label. Constructing a BadgeSpec by hand duplicates the colour pairs and drifts
 * from status.ts, which is what the required `class` field now prevents.
 */
function insightBadge(type: string): BadgeSpec {
  const severity: Severity =
    type === 'negative' ? 'high' : type === 'warning' ? 'medium' : type === 'positive' ? 'low' : 'none'
  const label =
    type === 'negative' ? 'Attention' : type === 'warning' ? 'Watch' : type === 'positive' ? 'Positive' : 'Info'
  return { ...severityBadge(severity), label }
}

const getInsightIcon = (type: string) => {
  switch (type) {
    case 'positive': return markRaw(CheckCircle2)
    case 'warning': return markRaw(AlertTriangle)
    case 'negative': return markRaw(TrendingDown)
    default: return markRaw(Info)
  }
}
</script>
