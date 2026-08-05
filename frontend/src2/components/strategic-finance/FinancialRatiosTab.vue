<template>
  <div class="space-y-6">

    <!-- Key Ratio Summary Cards -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <KpiCard
        v-for="card in ratioCards"
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
      <!-- Liquidity Ratios -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader variant="caption" title="Liquidity Ratios" :level="3">
          <template #actions>
            <Droplets class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <div class="space-y-4 mt-4">
          <div
            v-for="ratio in liquidityRatios"
            :key="ratio.name"
            class="flex justify-between items-center"
          >
            <div>
              <p class="text-sm font-medium text-ink-gray-7">{{ ratio.name }}</p>
              <p class="text-xs text-ink-gray-6">{{ ratio.description }}</p>
            </div>
            <div class="text-right">
              <p class="font-semibold text-ink-gray-9">{{ ratio.value }}</p>
              <p :class="['text-xs', deltaInk(ratio.trend)]">
                {{ deltaGlyph(ratio.trend) }}{{ Math.abs(ratio.trend).toFixed(1) }}%
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- Profitability Ratios -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader variant="caption" title="Profitability Ratios" :level="3">
          <template #actions>
            <TrendingUp class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <div class="space-y-4 mt-4">
          <div
            v-for="ratio in profitabilityRatios"
            :key="ratio.name"
            class="flex justify-between items-center"
          >
            <div>
              <p class="text-sm font-medium text-ink-gray-7">{{ ratio.name }}</p>
              <p class="text-xs text-ink-gray-6">{{ ratio.description }}</p>
            </div>
            <div class="text-right">
              <p class="font-semibold text-ink-gray-9">{{ ratio.value }}</p>
              <p :class="['text-xs', deltaInk(ratio.trend)]">
                {{ deltaGlyph(ratio.trend) }}{{ Math.abs(ratio.trend).toFixed(1) }}%
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- Efficiency Ratios -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader variant="caption" title="Efficiency Ratios" :level="3">
          <template #actions>
            <Gauge class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <div class="space-y-4 mt-4">
          <div
            v-for="ratio in efficiencyRatios"
            :key="ratio.name"
            class="flex justify-between items-center"
          >
            <div>
              <p class="text-sm font-medium text-ink-gray-7">{{ ratio.name }}</p>
              <p class="text-xs text-ink-gray-6">{{ ratio.description }}</p>
            </div>
            <div class="text-right">
              <p class="font-semibold text-ink-gray-9">{{ ratio.value }}</p>
              <p :class="['text-xs', deltaInk(ratio.trend)]">
                {{ deltaGlyph(ratio.trend) }}{{ Math.abs(ratio.trend).toFixed(1) }}%
              </p>
            </div>
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
                {{ quarter.gross_margin?.toFixed(1) }}%
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
                {{ quarter.net_margin?.toFixed(1) }}%
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
                {{ quarter.roa?.toFixed(1) }}%
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
                {{ quarter.asset_turnover?.toFixed(2) }}x
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
  Droplets,
  TrendingUp,
  Gauge,
  LineChart as LineChartIcon,
  BarChart3,
} from 'lucide-vue-next'
import {
  deltaGlyph,
  deltaInk,
  scoreSeverity,
  severityFill,
  severityAria,
  type Severity,
} from '../../utils/status'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import type { RatioCard, RatioTrendRow, FinancialRatiosData } from './types'

interface Props {
  data?: FinancialRatiosData
}

const props = defineProps<Props>()

const formatRatio = (value: number | null | undefined) => {
  if (value === null || value === undefined) return NO_VALUE
  return value.toFixed(2)
}

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined) return NO_VALUE
  return `${value.toFixed(1)}%`
}

// Map API status string to Severity
function ratioStatusSeverity(status: string | undefined): Severity {
  if (status === 'good') return 'none'
  if (status === 'warning') return 'medium'
  return 'high'
}

// Text ink class for a ratio value compared to a benchmark threshold.
// Below benchmark is bad (red); at or above is neutral.
function ratioTrendInk(value: number | null | undefined, benchmark: number): string {
  if (!value) return 'text-ink-gray-6'
  return value >= benchmark ? 'text-ink-gray-9 font-medium' : 'text-ink-red-4'
}

const liquidityRatios = computed(() => {
  if (!props.data) return []
  const current: Partial<RatioTrendRow> = props.data.current_ratios ?? {}
  return [
    {
      name: 'Asset Turnover',
      value: formatRatio(current.asset_turnover),
      description: 'Revenue / Total Assets',
      trend: 0,
    },
    {
      name: 'Debt to Equity',
      value: formatRatio(current.debt_to_equity),
      description: 'Total Debt / Shareholders Equity',
      trend: 0,
    },
    {
      name: 'Cash Ratio',
      value: formatRatio(props.data.cash_ratio),
      description: 'Cash / Current Liabilities',
      trend: props.data.cash_ratio_trend || 0,
    },
  ]
})

const profitabilityRatios = computed(() => {
  if (!props.data) return []
  const current: Partial<RatioTrendRow> = props.data.current_ratios ?? {}
  return [
    {
      name: 'Gross Margin',
      value: formatPercent(current.gross_margin),
      description: 'Gross Profit / Revenue',
      trend: 0,
    },
    {
      name: 'Net Profit Margin',
      value: formatPercent(current.net_margin),
      description: 'Net Income / Revenue',
      trend: 0,
    },
    {
      name: 'ROE',
      value: (current.roe ?? 0) > 0 ? formatPercent(current.roe) : 'N/A',
      description: 'Net Income / Shareholders Equity',
      trend: 0,
    },
    {
      name: 'ROA',
      value: formatPercent(current.roa),
      description: 'Net Income / Total Assets',
      trend: 0,
    },
  ]
})

const efficiencyRatios = computed(() => {
  if (!props.data) return []
  const current: Partial<RatioTrendRow> = props.data.current_ratios ?? {}
  return [
    {
      name: 'Asset Turnover',
      value: formatRatio(current.asset_turnover) + 'x',
      description: 'Revenue / Total Assets',
      trend: 0,
    },
    {
      name: 'Debt/Equity',
      value: (current.debt_to_equity ?? 0) > 0 ? formatRatio(current.debt_to_equity) : 'N/A',
      description: 'Total Debt / Equity',
      trend: 0,
    },
  ]
})

const ratioCards = computed(() => {
  if (!props.data?.ratio_cards) return []
  return props.data.ratio_cards.map((card: RatioCard) => ({
    name: card.name,
    value: card.name.includes('Margin') || card.name.includes('RO')
      ? ((card.value ?? 0) > 0 ? formatPercent(card.value) : 'N/A')
      : formatRatio(card.value),
    benchmark: card.name.includes('Margin') || card.name.includes('RO')
      ? formatPercent(card.benchmark)
      : formatRatio(card.benchmark),
    status: card.status,
    severity: ratioStatusSeverity(card.status),
  }))
})

const quarterlyTrends = computed(() => props.data?.trends?.slice(-4) || [])

const benchmarkComparison = computed(() => {
  if (!props.data?.ratio_cards) return []
  return props.data.ratio_cards.map((card: RatioCard) => {
    const actual = card.value || 0
    const benchmark = card.benchmark || 1
    const maxVal = Math.max(Math.abs(actual), benchmark) * 1.2 || 1
    const isPercent = card.name.includes('Margin') || card.name.includes('RO')
    const severity: Severity = ratioStatusSeverity(card.status)
    return {
      name: card.name,
      actual: isPercent ? `${actual.toFixed(1)}%` : actual.toFixed(2),
      benchmark: isPercent ? `${benchmark}%` : benchmark.toFixed(2),
      actualPosition: Math.min((Math.abs(actual) / maxVal) * 100, 100),
      benchmarkPosition: Math.min((benchmark / maxVal) * 100, 100),
      severity,
    }
  })
})
</script>
