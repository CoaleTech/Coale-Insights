<!--
  Financial Ratios & Benchmarks: no drill-down.
  
  Every ratio on this tab is derived from two or more aggregates (e.g. Current
  Ratio = Current Assets / Current Liabilities). A ledger-account row list
  would not resolve the computation; the ratios themselves are the insights.
-->
<template>
  <div class="space-y-6">

    <!-- Key Ratio Summary Cards: headline six only; every ratio is in the benchmark list below -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <KpiCard
        v-for="card in headlineCards"
        :key="card.name"
        :label="card.name"
        :value="card.value"
        :severity="card.severity"
        :sublabel="`Benchmark: ${card.benchmark}`"
        :loading="!data"
      />
    </div>

    <!-- Ratio Categories -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div
        v-for="group in ratioGroups"
        :key="group.title"
        class="rounded-lg border border-outline-gray-1 bg-surface-white p-6"
      >
        <SectionHeader variant="caption" :title="group.title" :level="3">
          <template #actions>
            <component :is="group.icon" class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <div class="space-y-4 mt-4">
          <div
            v-for="ratio in group.rows"
            :key="ratio.name"
            class="flex justify-between items-center"
          >
            <div>
              <p class="text-sm font-medium text-ink-gray-7">{{ ratio.name }}</p>
              <p class="text-xs text-ink-gray-6">{{ ratio.description }}</p>
            </div>
            <p class="font-semibold text-ink-gray-9">{{ ratio.value }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Quarterly Ratio Trends -->
    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <SectionHeader variant="caption" title="Quarterly Ratio Trends" :level="3">
        <template #actions>
          <LineChartIcon class="h-5 w-5 text-ink-gray-5" />
        </template>
      </SectionHeader>
      <div v-if="quarterlyTrends.length" class="overflow-x-auto mt-4">
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
                v-for="quarter in quarterlyTrends"
                :key="quarter.period"
                scope="col"
                class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase whitespace-nowrap"
              >
                {{ quarter.period }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-1">
            <tr class="hover:bg-surface-gray-1">
              <th class="px-4 py-3 text-sm font-medium text-ink-gray-9 sticky left-0 bg-surface-white" scope="row">
                Gross Margin
              </th>
              <td
                v-for="quarter in quarterlyTrends"
                :key="'gm-' + quarter.period"
                class="px-4 py-3 text-sm text-right whitespace-nowrap"
                :class="ratioTrendInk(quarter.gross_margin, 35)"
              >
                {{ formatPercent(quarter.gross_margin) }}
              </td>
            </tr>
            <tr class="hover:bg-surface-gray-1">
              <th class="px-4 py-3 text-sm font-medium text-ink-gray-9 sticky left-0 bg-surface-white" scope="row">
                Net Margin
              </th>
              <td
                v-for="quarter in quarterlyTrends"
                :key="'nm-' + quarter.period"
                class="px-4 py-3 text-sm text-right whitespace-nowrap"
                :class="ratioTrendInk(quarter.net_margin, 10)"
              >
                {{ formatPercent(quarter.net_margin) }}
              </td>
            </tr>
            <tr class="hover:bg-surface-gray-1">
              <th class="px-4 py-3 text-sm font-medium text-ink-gray-9 sticky left-0 bg-surface-white" scope="row">
                ROA
              </th>
              <td
                v-for="quarter in quarterlyTrends"
                :key="'roa-' + quarter.period"
                class="px-4 py-3 text-sm text-right whitespace-nowrap"
                :class="ratioTrendInk(quarter.roa, 8)"
              >
                {{ formatPercent(quarter.roa) }}
              </td>
            </tr>
            <tr class="hover:bg-surface-gray-1">
              <th class="px-4 py-3 text-sm font-medium text-ink-gray-9 sticky left-0 bg-surface-white" scope="row">
                Asset Turnover
              </th>
              <td
                v-for="quarter in quarterlyTrends"
                :key="'at-' + quarter.period"
                class="px-4 py-3 text-sm text-right whitespace-nowrap"
                :class="ratioTrendInk(quarter.asset_turnover, 1.2)"
              >
                {{ formatMultiple(quarter.asset_turnover) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center py-8 text-ink-gray-6 mt-4">
        No quarterly trend data available
      </div>
    </div>

    <!-- Performance vs Benchmarks -->
    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <SectionHeader variant="caption" title="Performance vs Benchmarks" :level="3">
        <template #actions>
          <BarChart3 class="h-5 w-5 text-ink-gray-5" />
        </template>
      </SectionHeader>
      <div class="space-y-4 mt-4">
        <div v-for="benchmark in benchmarkComparison" :key="benchmark.name">
          <div class="flex justify-between mb-1">
            <span class="text-sm font-medium text-ink-gray-7">{{ benchmark.name }}</span>
            <span class="text-sm text-ink-gray-6">
              {{ benchmark.actual }} / {{ benchmark.benchmark }} (benchmark)
            </span>
          </div>
          <!-- Non-text fill bar with aria label -->
          <div
            class="h-3 bg-surface-gray-3 rounded-full overflow-hidden relative"
            :aria-label="severityAria(benchmark.name, benchmark.severity, benchmark.actual)"
            role="img"
          >
            <!-- Benchmark marker -->
            <div
              class="absolute top-0 bottom-0 w-0.5 bg-surface-gray-4 z-10"
              :style="{ left: `${Math.min(benchmark.benchmarkPosition, 100)}%` }"
            ></div>
            <!-- Actual value bar -->
            <div
              :class="['h-full rounded-full transition-all motion-reduce:transition-none', severityFill(benchmark.severity)]"
              :style="{ width: `${Math.min(benchmark.actualPosition, 100)}%` }"
            ></div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { NO_VALUE } from '../../utils/format'
import { computed } from 'vue'
import {
  TrendingUp,
  Droplets,
  Gauge,
  ShieldCheck,
  LineChart as LineChartIcon,
  BarChart3,
} from 'lucide-vue-next'
import { severityFill, severityAria, type Severity } from '../../utils/status'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import type { RatioCard, RatioTrendRow, FinancialRatiosData, WorkingCapitalData } from './types'

interface Props {
  data?: FinancialRatiosData
  workingCapital?: WorkingCapitalData | null
}

const props = defineProps<Props>()

const formatRatio = (value: number | null | undefined) => {
  if (value === null || value === undefined) return NO_VALUE
  return value.toFixed(2)
}

/** Ratio with an 'x' multiple suffix (e.g. "2.4x"), omitted -- not appended
 * to the "-" placeholder -- when the server sent no meaningful value. */
const formatMultiple = (value: number | null | undefined) => {
  if (value === null || value === undefined) return NO_VALUE
  return `${value.toFixed(2)}x`
}

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined) return NO_VALUE
  return `${value.toFixed(1)}%`
}

// Map API status string to Severity. `unavailable` (value could not be
// computed) stays neutral: a verdict about a missing figure is a false verdict.
function ratioStatusSeverity(status: string | undefined): Severity {
  if (status === 'good' || status === 'unavailable') return 'none'
  if (status === 'warning') return 'medium'
  return 'high'
}

// Text ink class for a ratio value compared to a benchmark threshold.
// Below benchmark is bad (red); at or above is neutral.
function ratioTrendInk(value: number | null | undefined, benchmark: number): string {
  if (!value) return 'text-ink-gray-6'
  return value >= benchmark ? 'text-ink-gray-9 font-medium' : 'text-ink-red-4'
}

// The server sends no per-ratio trend, so none is shown; the quarterly table
// below carries the history.
const ratioGroups = computed(() => {
  if (!props.data) return []
  const c: Partial<RatioTrendRow> = props.data.current_ratios ?? {}
  return [
    {
      title: 'Liquidity Ratios',
      icon: Droplets,
      rows: [
        { name: 'Current Ratio', value: formatMultiple(props.workingCapital?.current_ratio), description: 'Current Assets / Current Liabilities' },
        { name: 'Quick Ratio', value: formatMultiple(props.workingCapital?.quick_ratio), description: '(Current Assets - Inventory) / Current Liabilities' },
      ],
    },
    {
      title: 'Profitability Ratios',
      icon: TrendingUp,
      rows: [
        { name: 'Gross Margin', value: formatPercent(c.gross_margin), description: 'Gross Profit / Revenue' },
        { name: 'Net Profit Margin', value: formatPercent(c.net_margin), description: 'Net Income / Revenue' },
        { name: 'ROE', value: formatPercent(c.roe), description: 'Net Income / Shareholders Equity' },
        { name: 'ROA', value: formatPercent(c.roa), description: 'Net Income / Total Assets' },
      ],
    },
    {
      title: 'Efficiency Ratios',
      icon: Gauge,
      rows: [
        { name: 'Asset Turnover', value: formatMultiple(c.asset_turnover), description: 'Revenue / Total Assets' },
        {
          name: 'Working Capital Turnover',
          value: formatMultiple(c.working_capital_turnover),
          description: 'Revenue / Working Capital',
        },
      ],
    },
    {
      title: 'Debt & Coverage Ratios',
      icon: ShieldCheck,
      rows: [
        { name: 'Debt to Equity', value: formatRatio(c.debt_to_equity), description: 'Total Debt / Shareholders Equity' },
        { name: 'Interest Coverage', value: formatMultiple(c.interest_coverage), description: 'EBIT / Interest Expense' },
        { name: 'DSCR', value: formatMultiple(c.dscr), description: 'EBITDA / (Interest + Principal Repaid)' },
      ],
    },
  ]
})

const isPercentCard = (name: string) => name.includes('Margin') || name.includes('RO')
const isMultipleCard = (name: string) =>
  name.includes('Turnover') || name.includes('Coverage') || name === 'DSCR'
const cardFormatter = (name: string) =>
  isPercentCard(name) ? formatPercent : isMultipleCard(name) ? formatMultiple : formatRatio

const ratioCards = computed(() => {
  if (!props.data?.ratio_cards) return []
  return props.data.ratio_cards.map((card: RatioCard) => {
    const fmt = cardFormatter(card.name)
    return {
      name: card.name,
      value: fmt(card.value),
      benchmark: fmt(card.benchmark),
      status: card.status,
      severity: ratioStatusSeverity(card.status),
    }
  })
})

// Summary strip is capped at six; the benchmark list below shows every ratio.
const headlineCards = computed(() => ratioCards.value.slice(0, 6))

const quarterlyTrends = computed(() => props.data?.trends?.slice(-4) || [])

const benchmarkComparison = computed(() => {
  if (!props.data?.ratio_cards) return []
  return props.data.ratio_cards.map((card: RatioCard) => {
    const fmt = cardFormatter(card.name)
    const available = card.value !== null && card.value !== undefined
    const actual = card.value ?? 0
    const benchmark = card.benchmark || 1
    const maxVal = Math.max(Math.abs(actual), benchmark) * 1.2 || 1
    return {
      name: card.name,
      actual: fmt(card.value),
      benchmark: fmt(benchmark),
      actualPosition: available ? Math.min((Math.abs(actual) / maxVal) * 100, 100) : 0,
      benchmarkPosition: Math.min((benchmark / maxVal) * 100, 100),
      severity: ratioStatusSeverity(card.status),
    }
  })
})
</script>
