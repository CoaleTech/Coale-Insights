<template>
  <div class="space-y-6">
    <!-- Loading state: top KPI row -->
    <div v-if="!data" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <KpiCard v-for="i in 4" :key="i" label="..." value="" :loading="true" />
    </div>

    <template v-else>
      <!-- Key KPIs Row -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="YTD Revenue"
          :amount="data?.ytd_revenue"
          :currency="currencyVal"
          :delta="data?.revenue_growth"
          :delta-higher-is-better="true"
          :sublabel="revenueComparisonLabel"
        />
        <KpiCard
          label="YTD Expenses"
          :amount="data?.ytd_expenses"
          :currency="currencyVal"
          sublabel="Operating costs"
        />
        <KpiCard
          label="Net Income"
          :amount="data?.ytd_net_income"
          :currency="currencyVal"
          :sublabel="marginLabel"
        />
        <KpiCard
          label="Cash Position"
          :amount="data?.cash_balance"
          :currency="currencyVal"
          :sublabel="runwayLabel"
        />
      </div>

      <!-- KPIs from Backend -->
      <div v-if="extraKpis.length" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          v-for="(kpi, index) in extraKpis"
          :key="index"
          :label="kpi.label"
          :value="formatKpiValue(kpi.value, kpi.format)"
          :sublabel="kpi.subtitle"
        />
      </div>

      <!-- Revenue and Profit Trends -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Monthly Performance Trend -->
        <div class="bg-surface-white rounded-lg p-6 shadow-sm border border-outline-gray-1">
          <SectionHeader variant="caption" title="Monthly Performance Trend" :level="3" />
          <div v-if="data?.monthly_trends?.length" class="space-y-4 mt-4">
            <IntelligenceChart class="h-48 sm:h-56 lg:h-72 mt-2" :config="trendConfig" />

            <!-- Performance summary table -->
            <div class="overflow-x-auto mt-4">
              <table class="w-full text-xs">
                <caption class="sr-only">Monthly revenue, expenses, and net income by period</caption>
                <thead>
                  <tr class="text-ink-gray-6 border-b border-outline-gray-1">
                    <th scope="col" class="py-2 text-left font-medium sticky left-0 bg-surface-white">Metric</th>
                    <th
                      v-for="trend in data.monthly_trends"
                      :key="trend.period"
                      scope="col"
                      class="py-2 text-right font-medium px-2"
                    >
                      {{ formatMonthLabel(trend.period) }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr class="border-b border-outline-gray-1">
                    <th scope="row" class="py-2 font-medium text-ink-gray-8 sticky left-0 bg-surface-white text-left">Revenue</th>
                    <td
                      v-for="trend in data.monthly_trends"
                      :key="'rev-' + trend.period"
                      class="py-2 text-right text-ink-gray-9 font-medium px-2"
                    >
                      {{ formatCompactValue(trend.revenue) }}
                    </td>
                  </tr>
                  <tr class="border-b border-outline-gray-1">
                    <th scope="row" class="py-2 font-medium text-ink-gray-8 sticky left-0 bg-surface-white text-left">Expenses</th>
                    <td
                      v-for="trend in data.monthly_trends"
                      :key="'exp-' + trend.period"
                      class="py-2 text-right text-ink-gray-9 font-medium px-2"
                    >
                      {{ formatCompactValue(trend.expenses) }}
                    </td>
                  </tr>
                  <tr class="border-b border-outline-gray-1">
                    <th scope="row" class="py-2 font-medium text-ink-gray-8 sticky left-0 bg-surface-white text-left">Net Income</th>
                    <td
                      v-for="trend in data.monthly_trends"
                      :key="'net-' + trend.period"
                      class="py-2 text-right font-medium px-2"
                      :class="deltaInk(trend.net_income)"
                    >
                      {{ formatCompactValue(trend.net_income) }}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row" class="py-2 font-medium text-ink-gray-7 sticky left-0 bg-surface-white text-left">Margin</th>
                    <td
                      v-for="trend in data.monthly_trends"
                      :key="'margin-' + trend.period"
                      class="py-2 text-right font-medium px-2"
                      :class="deltaInk(trend.margin)"
                    >
                      {{ trend.margin }}%
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div v-else class="h-40 sm:h-56 lg:h-64 flex items-center justify-center text-ink-gray-6 mt-4">
            No revenue data available
          </div>
        </div>

        <!-- Expense Breakdown -->
        <div class="bg-surface-white rounded-lg p-6 shadow-sm border border-outline-gray-1">
          <SectionHeader variant="caption" title="Expense Breakdown" :level="3" />
          <!-- Auto height: the ranked list grows with the category count and
               balances against the taller Monthly trend card beside it. -->
          <div v-if="expenseBreakdown?.length" class="mt-4">
            <ExpensePieChart :data="expenseBreakdown" :currency="currencyVal" />
          </div>
          <div v-else class="h-40 sm:h-56 lg:h-64 flex items-center justify-center text-ink-gray-6 mt-4">
            No expense data available
          </div>
        </div>
      </div>

      <!-- Financial Health Scorecard -->
      <div class="bg-surface-white rounded-lg p-6 shadow-sm border border-outline-gray-1">
        <SectionHeader variant="caption" title="Financial Health Scorecard" :level="3" />
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mt-4">
          <!-- Liquidity -->
          <div class="text-center">
            <div class="relative inline-flex items-center justify-center">
              <svg
                class="w-24 h-24 transform -rotate-90"
                aria-hidden="true"
              >
                <circle
                  cx="48" cy="48" r="40"
                  :style="{ stroke: 'var(--surface-gray-3)' }"
                  stroke-width="8"
                  fill="none"
                />
                <circle
                  cx="48" cy="48" r="40"
                  :style="{ stroke: 'var(--surface-blue-3)' }"
                  stroke-width="8"
                  fill="none"
                  :stroke-dasharray="251.2"
                  :stroke-dashoffset="251.2 - (251.2 * (data?.health_scores?.liquidity || 0) / 100)"
                />
              </svg>
              <span class="absolute text-xl font-bold text-ink-gray-9">
                {{ data?.health_scores?.liquidity || 0 }}
              </span>
            </div>
            <p class="mt-2 text-sm font-medium text-ink-gray-8">Liquidity</p>
            <Badge
              v-bind="severityBadge(scoreSeverity(data?.health_scores?.liquidity, HEALTH_SCORE_THRESHOLDS))"
              size="sm"
              class="mt-1"
            />
            <p class="text-xs text-ink-gray-6 mt-1">{{ data?.health_scores?.liquidity_status || 'N/A' }}</p>
          </div>

          <!-- Profitability -->
          <div class="text-center">
            <div class="relative inline-flex items-center justify-center">
              <svg class="w-24 h-24 transform -rotate-90" aria-hidden="true">
                <circle
                  cx="48" cy="48" r="40"
                  :style="{ stroke: 'var(--surface-gray-3)' }"
                  stroke-width="8"
                  fill="none"
                />
                <circle
                  cx="48" cy="48" r="40"
                  :style="{ stroke: 'var(--surface-blue-3)' }"
                  stroke-width="8"
                  fill="none"
                  :stroke-dasharray="251.2"
                  :stroke-dashoffset="251.2 - (251.2 * (data?.health_scores?.profitability || 0) / 100)"
                />
              </svg>
              <span class="absolute text-xl font-bold text-ink-gray-9">
                {{ data?.health_scores?.profitability || 0 }}
              </span>
            </div>
            <p class="mt-2 text-sm font-medium text-ink-gray-8">Profitability</p>
            <Badge
              v-bind="severityBadge(scoreSeverity(data?.health_scores?.profitability, HEALTH_SCORE_THRESHOLDS))"
              size="sm"
              class="mt-1"
            />
            <p class="text-xs text-ink-gray-6 mt-1">{{ data?.health_scores?.profitability_status || 'N/A' }}</p>
          </div>

          <!-- Efficiency -->
          <div class="text-center">
            <div class="relative inline-flex items-center justify-center">
              <svg class="w-24 h-24 transform -rotate-90" aria-hidden="true">
                <circle
                  cx="48" cy="48" r="40"
                  :style="{ stroke: 'var(--surface-gray-3)' }"
                  stroke-width="8"
                  fill="none"
                />
                <circle
                  cx="48" cy="48" r="40"
                  :style="{ stroke: 'var(--surface-blue-3)' }"
                  stroke-width="8"
                  fill="none"
                  :stroke-dasharray="251.2"
                  :stroke-dashoffset="251.2 - (251.2 * (data?.health_scores?.efficiency || 0) / 100)"
                />
              </svg>
              <span class="absolute text-xl font-bold text-ink-gray-9">
                {{ data?.health_scores?.efficiency || 0 }}
              </span>
            </div>
            <p class="mt-2 text-sm font-medium text-ink-gray-8">Efficiency</p>
            <Badge
              v-bind="severityBadge(scoreSeverity(data?.health_scores?.efficiency, HEALTH_SCORE_THRESHOLDS))"
              size="sm"
              class="mt-1"
            />
            <p class="text-xs text-ink-gray-6 mt-1">{{ data?.health_scores?.efficiency_status || 'N/A' }}</p>
          </div>
        </div>
      </div>

      <!-- Key Insights -->
      <div class="bg-surface-white rounded-lg p-6 shadow-sm border border-outline-gray-1">
        <SectionHeader variant="caption" title="Key Executive Insights" :level="3" />
        <div v-if="data?.key_insights?.length" class="space-y-3 mt-4">
          <div
            v-for="(insight, index) in data.key_insights"
            :key="index"
            class="p-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1"
          >
            <div class="flex items-start gap-3">
              <component
                :is="getInsightIcon(insight.type)"
                class="h-5 w-5 flex-shrink-0 mt-0.5 text-ink-gray-5"
              />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1">
                  <p class="font-medium text-ink-gray-9">{{ insight.title }}</p>
                  <Badge
                    v-bind="severityBadge(insightSeverity(insight.type))"
                    size="sm"
                  />
                </div>
                <p class="text-sm text-ink-gray-7">{{ insight.description }}</p>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="text-center py-8 text-ink-gray-6 mt-4">
          No insights available yet
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import IntelligenceChart from '../../intelligence/components/IntelligenceChart.vue'
import { computed, markRaw, type Ref } from 'vue'
import { useCurrency } from '../../composables/useCurrency'
import { Badge } from 'frappe-ui'
import {
  TrendingDown,
  AlertTriangle,
  CheckCircle2,
  Info,
} from 'lucide-vue-next'
import {
  deltaInk,
  severityBadge,
  scoreSeverity,
  type Severity,
  HEALTH_SCORE_THRESHOLDS,
} from '../../utils/status'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import ExpensePieChart from '../charts/ExpensePieChart.vue'
import { themeColor } from '../../utils/chartTheme'

interface Props {
  data: {
    ytd_revenue?: number
    /** Comparison base for growth. Sent so a suppressed ratio is still disclosed. */
    prior_period_revenue?: number
    ytd_expenses?: number
    ytd_net_income?: number
    cash_balance?: number
    revenue_growth?: number
    net_margin?: number
    cash_runway_months?: number
    kpis?: Array<{ label: string; value: number; format: string; subtitle?: string }>
    monthly_trends?: Array<{
      period: string
      revenue: number
      expenses: number
      net_income: number
      margin: number
    }>
    health_scores?: {
      liquidity: number
      liquidity_status: string
      profitability: number
      profitability_status: string
      efficiency: number
      efficiency_status: string
    }
    key_insights?: Array<{
      type: string
      title: string
      description: string
    }>
  } | null
  /** Rows accept category/name/label + value/amount/percentage keys; see ExpensePieChart's PieRow. */
  expenseBreakdown?: Record<string, number | string | boolean | null | undefined>[]
}

const props = defineProps<Props>()

const currency = useCurrency('')
const getCurrency = () => currency.value
const currencyVal = computed(() => getCurrency())


const marginLabel = computed(() => {
  const margin = props.data?.net_margin
  if (margin === null || margin === undefined) return undefined
  const sign = margin > 0 ? '+' : ''
  return `${sign}${margin.toFixed(1)}% margin`
})

/**
 * Runway in months, absent when the server did not measure it.
 *
 * Was `(cash_runway_months || 0) + ' months runway'`, which reported "0 months
 * runway" -- an imminent insolvency warning -- for a field that simply was not
 * sent.
 */
const runwayLabel = computed(() => {
  const months = props.data?.cash_runway_months
  if (months === null || months === undefined || !Number.isFinite(months)) return undefined
  return `${formatCount(months, { decimals: 1 })} months runway`
})

/**
 * States the base the growth is measured against, not just "vs last year".
 *
 * The server withholds `revenue_growth` when the prior period is under 10% of
 * the current one, because 1554% off a 6% base is not a performance signal
 * (`summary.py:84-92`). But suppressing the ratio and saying nothing would hide
 * a real change, which is under-reporting rather than accuracy. Naming the base
 * lets the reader discount it themselves: "vs KES 27.3M last year" is honest
 * whether the jump is growth or an incomplete prior year.
 */
const revenueComparisonLabel = computed(() => {
  const prior = props.data?.prior_period_revenue
  if (typeof prior !== 'number' || !Number.isFinite(prior)) return 'vs last year'
  return `vs ${formatMoney(prior, getCurrency(), { compact: true })} last year`
})

/**
 * Server KPIs that the explicit cards above do not already show.
 *
 * The backend's `kpis` array overlaps those cards on four of its six entries,
 * so the tab rendered Total Revenue twice, Net Profit twice, Revenue Growth as
 * both a delta and a card, and Cash Position twice with two different runway
 * figures (49.6 months on the card, "50 months" in the server's subtitle).
 * Filtering by label keeps a genuinely new server KPI visible while refusing to
 * restate one, rather than hard-coding which six the server happens to send.
 */
const CARDS_ALREADY_SHOW = new Set([
  'ytd revenue', 'total revenue',
  'ytd expenses', 'total expenses',
  'net income', 'net profit',
  'cash position', 'cash balance',
  // Rendered as the delta on the YTD Revenue card.
  'revenue growth',
])

const extraKpis = computed(() =>
  (props.data?.kpis ?? []).filter(
    (k) => !CARDS_ALREADY_SHOW.has(String(k?.label ?? '').trim().toLowerCase()),
  ),
)

import { formatCount, formatMoney, NO_VALUE } from '../../utils/format'

const formatCurrency = (value: number | null | undefined) => formatMoney(value, getCurrency())

const formatKpiValue = (value: number | null | undefined, format: string) => {
  if (value === null || value === undefined) return NO_VALUE
  switch (format) {
    case 'currency': return formatCurrency(value)
    case 'percent': return `${value.toFixed(1)}%`
    case 'number': return value.toLocaleString()
    case 'months': return `${value.toFixed(1)} months`
    default: return String(value)
  }
}

const insightSeverity = (type: string): Severity => {
  switch (type) {
    case 'success': return 'low'
    case 'warning': return 'medium'
    case 'danger': return 'high'
    default: return 'none'
  }
}

const getInsightIcon = (type: string) => {
  switch (type) {
    case 'success': return markRaw(CheckCircle2)
    case 'warning': return markRaw(AlertTriangle)
    case 'danger': return markRaw(TrendingDown)
    default: return markRaw(Info)
  }
}

const formatMonthLabel = (period: string) => {
  if (!period) return ''
  const [year, month] = period.split('-')
  const date = new Date(parseInt(year), parseInt(month) - 1)
  return date.toLocaleDateString('en-KE', { month: 'short' })
}

const trendConfig = computed(() => ({
  title: '',
  data: (props.data?.monthly_trends ?? []).map(t => ({
    month: formatMonthLabel(t.period),
    Revenue: t.revenue,
    Expenses: t.expenses,
    'Net Income': t.net_income,
  })),
  xAxis: { key: 'month', type: 'category' as const },
  yAxis: { title: getCurrency() },
  series: [
    { name: 'Revenue', type: 'area' as const, color: themeColor('--app-pos-fill'), fillOpacity: 0.2 },
    { name: 'Expenses', type: 'area' as const, color: themeColor('--app-neg-fill'), fillOpacity: 0.2 },
    { name: 'Net Income', type: 'line' as const, color: themeColor('--app-info-fill') },
  ],
}))

const formatCompactValue = (value: number) => {
  if (value === null || value === undefined) return NO_VALUE
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absValue >= 1000000) return `${sign}${(absValue / 1000000).toFixed(1)}M`
  if (absValue >= 1000) return `${sign}${(absValue / 1000).toFixed(0)}K`
  return `${sign}${absValue.toFixed(0)}`
}

</script>
