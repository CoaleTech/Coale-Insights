<!--
  Cost Structure Benchmarks.

  Salary, fixed cost, and five named opex categories (Marketing, Training &
  Development, Incentives/Increment/Appraisal, Rent, Electricity) graded
  good/moderate/risky against the ideal/risky thresholds an admin sets in
  Insights Settings, each with a plain-English recommended action. Below
  that, a linear-trend forecast of total monthly expenses.

  A card whose `value` is `null` (e.g. Gross Profit ratios when no COGS
  accounts have posted this period) renders as "No data", never a fabricated
  figure — `cost_ratios.py:_build_card` guarantees the same.
-->
<template>
  <div class="space-y-6">
    <!-- Loading -->
    <div v-if="!data" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      <KpiCard v-for="i in 5" :key="i" label="..." value="" :loading="true" />
    </div>

    <template v-else>
      <!-- Overall status -->
      <div class="flex items-start gap-3 rounded-lg border p-4" :class="bannerClass(data.overall_status)">
        <component :is="bannerIcon(data.overall_status)" class="h-5 w-5 flex-shrink-0 mt-0.5" aria-hidden="true" />
        <div>
          <p class="font-semibold text-ink-gray-9">Cost Structure: {{ statusLabel(data.overall_status) }}</p>
          <p class="text-sm text-ink-gray-6 mt-0.5">{{ bannerSubtitle(data.overall_status) }}</p>
        </div>
      </div>

      <!-- Base figures -->
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <KpiCard label="Revenue (YTD)" :amount="data.figures.revenue" :currency="currency" />
        <KpiCard label="Gross Profit (YTD)" :amount="data.figures.gross_profit ?? undefined" :currency="currency" />
        <KpiCard label="Net Profit (YTD)" :amount="data.figures.net_profit" :currency="currency" />
        <KpiCard label="Salary Cost (YTD)" :amount="data.figures.salary_cost" :currency="currency" />
        <KpiCard label="Fixed Cost (YTD)" :amount="data.figures.fixed_cost" :currency="currency" />
      </div>

      <!-- Ratio cards -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader
          variant="caption"
          title="Cost Structure Benchmarks"
          hint="Ideal / risky thresholds, configurable in Insights Settings"
          :level="3"
        />
        <div class="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div
            v-for="card in data.ratio_cards"
            :key="card.key"
            class="rounded-lg border p-4"
            :class="cardBorderClass(card.status)"
          >
            <div class="flex flex-wrap items-start justify-between gap-2">
              <p class="text-sm font-semibold text-ink-gray-9">{{ card.name }}</p>
              <Badge v-bind="severityBadge(costStatusSeverity(card.status))" :label="statusLabel(card.status)" size="sm" class="shrink-0" />
            </div>
            <p class="tnum text-2xl font-bold text-ink-gray-9 mt-1">{{ formatCardValue(card) }}</p>

            <!-- Benchmark bar: ideal threshold marked, actual filled by status -->
            <div
              v-if="card.value !== null"
              class="mt-3 h-2 bg-surface-gray-3 rounded-full overflow-hidden relative"
              :aria-label="severityAria(card.name, costStatusSeverity(card.status), formatCardValue(card))"
              role="img"
            >
              <div
                class="absolute top-0 bottom-0 w-0.5 bg-surface-gray-5 z-10"
                :style="{ left: `${idealMarkerPct(card)}%` }"
              />
              <div
                :class="['h-full rounded-full motion-reduce:transition-none transition-all', severityFill(costStatusSeverity(card.status))]"
                :style="{ width: `${actualBarPct(card)}%` }"
              />
            </div>

            <p class="text-sm text-ink-gray-6 mt-3">{{ card.recommendation }}</p>
          </div>
        </div>
      </div>

      <!-- Expense forecast -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader
          variant="caption"
          title="Expense Forecast"
          hint="Linear trend over trailing complete months, not seasonally adjusted"
          :level="3"
        />
        <template v-if="forecast?.status === 'success'">
          <div class="mt-4 h-56 sm:h-64 lg:h-72">
            <IntelligenceChart v-if="forecastChartConfig" :config="forecastChartConfig" />
          </div>
          <div v-if="forecast.forecast?.length" class="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            <KpiCard
              v-for="pt in forecast.forecast"
              :key="pt.month"
              :label="formatPeriod(pt.month)"
              :amount="pt.projected_amount"
              :currency="currency"
              variant="tile"
            />
          </div>
          <p class="text-xs text-ink-gray-6 mt-3">
            {{ forecast.note }} Trend: <span class="font-medium">{{ forecast.trend_direction }}</span>,
            {{ formatMoney(forecast.monthly_change, currency) }}/month.
          </p>
        </template>
        <div v-else class="mt-4 text-center py-8 text-ink-gray-6">
          {{ forecast?.message || 'Not enough expense history yet to forecast.' }}
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import { CheckCircle2, AlertTriangle, AlertOctagon } from 'lucide-vue-next'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import IntelligenceChart from '../../intelligence/components/IntelligenceChart.vue'
import { severityBadge, severityFill, severityAria, type Severity } from '../../utils/status'
import { formatMoney, NO_VALUE } from '../../utils/format'
import { formatPeriod } from '../financial/format'
import { themeColor } from '../../utils/chartTheme'
import type { CostStructureData, CostRatioCard, CostRatioStatus, ExpenseForecastData } from './types'

const props = defineProps<{
  data: CostStructureData | null | undefined
  forecast?: ExpenseForecastData | null
  currency: string
}>()

// ── Status vocabulary ───────────────────────────────────────────────────────

function costStatusSeverity(status: CostRatioStatus): Severity {
  if (status === 'good') return 'none'
  if (status === 'moderate') return 'medium'
  if (status === 'risky') return 'high'
  return 'none'
}

function statusLabel(status: CostRatioStatus): string {
  if (status === 'good') return 'Good'
  if (status === 'moderate') return 'Moderate'
  if (status === 'risky') return 'Risky'
  return 'No Data'
}


function cardBorderClass(status: CostRatioStatus): string {
  if (status === 'risky') return 'border-outline-red-2 bg-surface-red-1'
  if (status === 'moderate') return 'border-outline-amber-2 bg-surface-amber-1'
  return 'border-outline-gray-1 bg-surface-white'
}

function bannerClass(status: CostRatioStatus): string {
  if (status === 'risky') return 'border-outline-red-2 bg-surface-red-1'
  if (status === 'moderate') return 'border-outline-amber-2 bg-surface-amber-1'
  return 'border-outline-green-2 bg-surface-green-1'
}

function bannerIcon(status: CostRatioStatus) {
  if (status === 'risky') return AlertOctagon
  if (status === 'moderate') return AlertTriangle
  return CheckCircle2
}

function bannerSubtitle(status: CostRatioStatus): string {
  if (status === 'risky') return 'At least one cost ratio is past its risk threshold. Review the flagged cards below and act on the recommended step.'
  if (status === 'moderate') return 'Every ratio is contained, but one or more sit above their ideal target. Worth a closer look before it drifts further.'
  return 'Every cost ratio is within its ideal target for the current fiscal year to date.'
}

// ── Card rendering ───────────────────────────────────────────────────────────

function formatCardValue(card: CostRatioCard): string {
  if (card.value === null) return NO_VALUE
  return card.unit === '%' ? `${card.value.toFixed(1)}%` : `${card.value.toFixed(2)}x`
}

/** Track max spans the wider of actual, ideal, and risky so the ideal marker
 *  and the fill bar always land inside the visible track. */
function barMax(card: CostRatioCard): number {
  return Math.max(Math.abs(card.value ?? 0), card.ideal, card.risky) * 1.2 || 1
}

function actualBarPct(card: CostRatioCard): number {
  if (card.value === null) return 0
  return Math.min((Math.abs(card.value) / barMax(card)) * 100, 100)
}

function idealMarkerPct(card: CostRatioCard): number {
  return Math.min((card.ideal / barMax(card)) * 100, 100)
}

// ── Forecast chart ───────────────────────────────────────────────────────────

const forecastChartConfig = computed(() => {
  if (!props.forecast || props.forecast.status !== 'success') return null
  const history = props.forecast.history || []
  const forecast = props.forecast.forecast || []

  const rows: { period: string; Actual?: number; Forecast?: number }[] = history.map((h, i) => ({
    period: formatPeriod(h.month),
    Actual: h.amount,
    // Bridge point: seed Forecast with the last actual so the two lines connect
    // instead of leaving a visual gap at the handoff month.
    Forecast: i === history.length - 1 ? h.amount : undefined,
  }))
  forecast.forEach((f) => {
    rows.push({ period: formatPeriod(f.month), Forecast: f.projected_amount })
  })

  return {
    title: '',
    data: rows,
    xAxis: { key: 'period', type: 'category' as const },
    yAxis: { title: props.currency },
    series: [
      { name: 'Actual', type: 'line' as const, color: themeColor('--app-accent') },
      { name: 'Forecast', type: 'line' as const, color: themeColor('--app-warn-fill') },
    ],
  }
})
</script>
