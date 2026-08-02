<!--
  Marketing & CRM Intelligence.

  Data source is ERPNext's BUILT-IN CRM: Lead, Opportunity and Quotation. The
  separate Frappe CRM app (`CRM Lead` / `CRM Deal`) is intentionally not read;
  on this site those tables are empty and ERPNext's CRM module holds the records.

  Built from operator questions, not from the metric list:
    is it healthy      -> alert strip + KPI row
    where's the bottleneck -> funnel + pipeline-by-status
    what changed       -> monthly lead trend
    what should I do   -> the alert strip, severity ranked

  Panels deliberately absent, because the data makes them vanity panels:
    * anything keyed on Opportunity.opportunity_amount, which is 0 for every row
    * campaign-level reporting, with a single Campaign record in existence
-->
<template>
  <div class="flex h-full flex-col overflow-hidden">
    <!-- Header -->
    <header
      class="flex flex-shrink-0 flex-col items-start gap-3 border-b border-outline-gray-1 bg-surface-white px-6 py-4 sm:flex-row sm:items-center sm:justify-between"
    >
      <div>
        <h1 class="text-xl font-semibold text-ink-gray-9">Marketing &amp; CRM</h1>
        <p class="mt-0.5 text-sm text-ink-gray-6">
          ERPNext CRM
          <span v-if="freshnessLabel"> &middot; {{ freshnessLabel }}</span>
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2 sm:gap-3">
        <Select v-model="period" :options="periodOptions" />
        <Button
          variant="subtle"
          :loading="refreshing"
          icon-left="refresh-cw"
          label="Refresh"
          @click="reload"
        />
      </div>
    </header>

    <div class="flex-1 overflow-y-auto px-6 py-5">
      <!-- Permission -->
      <div
        v-if="isPermissionError"
        class="rounded-lg border border-outline-gray-1 bg-surface-white p-8 text-center"
      >
        <Lock class="mx-auto mb-3 h-8 w-8 text-ink-gray-5" aria-hidden="true" />
        <p class="text-ink-gray-8">You do not have permission to view CRM data.</p>
        <p class="mt-1 text-sm text-ink-gray-6">Ask an administrator for Lead read access.</p>
      </div>

      <!-- Error -->
      <div
        v-else-if="error"
        class="rounded-lg border border-outline-gray-1 bg-surface-white p-8 text-center"
      >
        <TriangleAlert class="mx-auto mb-3 h-8 w-8 text-neg" aria-hidden="true" />
        <p class="text-ink-gray-8">{{ error }}</p>
        <Button class="mt-4" variant="solid" theme="gray" label="Try again" @click="retry" />
      </div>

      <!-- Loading -->
      <div v-else-if="loading" class="space-y-5">
        <div class="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
          <KpiCard v-for="n in 6" :key="n" label="Loading" value="" loading />
        </div>
        <SkeletonBlock class="h-64 w-full rounded-lg" />
      </div>

      <template v-else-if="hasData">
        <!-- Alerts. The action list, worst first. -->
        <section v-if="alerts.length" class="mb-5 space-y-2" aria-label="Alerts">
          <article
            v-for="(alert, i) in alerts"
            :key="i"
            class="flex items-start gap-3 rounded-lg border border-outline-gray-1 bg-surface-white p-4"
          >
            <Badge
              v-bind="severityBadge(alert.severity)"
              :label="severityBadge(alert.severity).label"
              size="sm"
              class="mt-0.5 flex-shrink-0"
            />
            <div class="min-w-0">
              <p class="text-sm font-medium text-ink-gray-9">{{ alert.title }}</p>
              <p class="mt-0.5 text-sm text-ink-gray-6">{{ alert.description }}</p>
            </div>
          </article>
        </section>

        <!-- Health -->
        <section class="mb-6" aria-label="Key metrics">
          <div class="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
            <KpiCard
              label="Total leads"
              :value="formatNumber(kpis.total_leads)"
              :sublabel="`${formatNumber(kpis.new_leads)} this period`"
              clickable
              @click="drillDown.open(CRM_ENDPOINT, 'Leads', { metric: 'leads' })"
            />
            <KpiCard
              label="Unqualified"
              :value="formatNumber(kpis.open_leads)"
              :severity="scoreSeverity(openShare, { good: 30, warn: 50, higherIsBetter: false })"
              :sublabel="`${openShare}% of all leads`"
            />
            <KpiCard
              label="Lead conversion"
              :value="`${kpis.lead_conversion_rate}%`"
              :severity="scoreSeverity(kpis.lead_conversion_rate, { good: 10, warn: 5 })"
              :sublabel="`${formatNumber(kpis.converted_leads)} converted`"
            />
            <KpiCard
              label="Open pipeline"
              :amount="kpis.open_quote_value"
              :currency="currency"
              sublabel="Draft quotations"
            />
            <KpiCard
              label="Won"
              :amount="kpis.won_value"
              :currency="currency"
              sublabel="Ordered quotations"
            />
            <KpiCard
              label="Win rate by value"
              :value="`${kpis.win_rate_by_value}%`"
              :severity="scoreSeverity(kpis.win_rate_by_value, { good: 40, warn: 20 })"
              :sublabel="`${formatMoney(kpis.expired_value, currency, { compact: true })} expired`"
            />
          </div>
        </section>

        <Tabs v-model="tabIndex" :tabs="tabs" />

        <!-- Funnel + bottleneck -->
        <section v-show="tabIndex === 0" class="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
            <SectionHeader title="Funnel" hint="ERPNext Lead status, then Quotation" />
            <IntelligenceChart class="mt-2 h-48 sm:h-56 lg:h-64" :config="funnelConfig" />
            <!-- The chart carries the shape; this list carries the numbers and the
                 conversion rates, and is what a screen reader reads. -->
            <dl class="mt-3 divide-y divide-outline-gray-1 border-t border-outline-gray-1">
              <div
                v-for="stage in funnel"
                :key="stage.label"
                class="flex items-baseline justify-between gap-3 py-2"
              >
                <dt class="text-sm text-ink-gray-7">
                  {{ stage.label }}
                  <span v-if="stage.conversion_from_prev !== null" class="text-ink-gray-6">
                    &middot; {{ stage.conversion_from_prev }}% of previous
                  </span>
                </dt>
                <dd class="flex flex-shrink-0 items-baseline gap-3">
                  <span v-if="stage.value" class="tnum text-sm text-ink-gray-6">
                    {{ formatMoney(stage.value, currency, { compact: true }) }}
                  </span>
                  <span class="tnum text-sm font-semibold text-ink-gray-9">
                    {{ formatNumber(stage.count) }}
                  </span>
                </dd>
              </div>
            </dl>
          </div>

          <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
            <SectionHeader title="Where leads are sitting" hint="All open records by status" />
            <table class="mt-4 w-full text-sm">
              <caption class="sr-only">Lead count by CRM status</caption>
              <thead>
                <tr class="border-b border-outline-gray-1">
                  <th scope="col" class="pb-2 text-left font-medium text-ink-gray-6">Status</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Leads</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Share</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-outline-gray-1">
                <tr v-for="row in pipelineByStatus" :key="row.status">
                  <th scope="row" class="py-2 text-left font-normal text-ink-gray-8">
                    {{ row.status }}
                  </th>
                  <td class="tnum py-2 text-right text-ink-gray-9">{{ formatNumber(row.count) }}</td>
                  <td class="tnum py-2 text-right text-ink-gray-6">
                    {{ sharePct(row.count, kpis.total_leads) }}%
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Channels: the money panel -->
        <section v-show="tabIndex === 1" class="mt-5">
          <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
            <SectionHeader
              title="Channel performance"
              hint="All time, ordered by revenue won"
            />
            <p class="mt-1 text-sm text-ink-gray-6">
              Volume and revenue are not the same channel. Compare won value against lead
              count before shifting spend.
            </p>
            <div class="mt-4 overflow-x-auto">
              <table class="w-full text-sm">
                <caption class="sr-only">
                  Lead source performance: volume, conversion and revenue
                </caption>
                <thead>
                  <tr class="border-b border-outline-gray-1">
                    <th scope="col" class="pb-2 text-left font-medium text-ink-gray-6">Source</th>
                    <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Leads</th>
                    <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Conv.</th>
                    <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Quotes</th>
                    <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Quoted</th>
                    <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Won</th>
                    <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">
                      Won / lead
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-outline-gray-1">
                  <tr v-for="row in channels" :key="row.source" class="hover:bg-surface-gray-1">
                    <th scope="row" class="py-2.5 text-left font-normal text-ink-gray-9">
                      {{ row.source }}
                    </th>
                    <td class="tnum py-2.5 text-right text-ink-gray-8">
                      {{ formatNumber(row.leads) }}
                    </td>
                    <td class="py-2.5 text-right">
                      <Badge
                        v-bind="severityBadge(conversionSeverity(row.conversion_rate))"
                        :label="`${row.conversion_rate}%`"
                        size="sm"
                      />
                    </td>
                    <td class="tnum py-2.5 text-right text-ink-gray-8">
                      {{ formatNumber(row.quotations) }}
                    </td>
                    <td class="tnum py-2.5 text-right text-ink-gray-6">
                      {{ formatMoney(row.quoted_value, currency, { compact: true }) }}
                    </td>
                    <td class="tnum py-2.5 text-right font-medium text-ink-gray-9">
                      {{ formatMoney(row.won_value, currency, { compact: true }) }}
                    </td>
                    <td class="tnum py-2.5 text-right text-ink-gray-8">
                      {{ formatMoney(row.value_per_lead, currency, { compact: true }) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <!-- What changed -->
        <section v-show="tabIndex === 2" class="mt-5">
          <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
            <SectionHeader title="Lead intake by month" hint="New leads, and how many converted" />
            <IntelligenceChart v-if="trend.length" class="mt-2 h-52 sm:h-64 lg:h-72" :config="trendConfig" />
            <p v-else class="mt-4 text-sm text-ink-gray-6">No lead activity in this window.</p>
            <!-- Canvas is invisible to assistive tech, so the same series is
                 available as a table. -->
            <table v-if="trend.length" class="sr-only">
              <caption>Leads created and converted by month</caption>
              <thead>
                <tr>
                  <th scope="col">Month</th>
                  <th scope="col">Leads</th>
                  <th scope="col">Converted</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="point in trend" :key="point.month">
                  <th scope="row">{{ point.month }}</th>
                  <td>{{ point.leads }}</td>
                  <td>{{ point.converted }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Coverage -->
        <section v-show="tabIndex === 3" class="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
            <SectionHeader title="Territory" hint="All time" />
            <table class="mt-4 w-full text-sm">
              <caption class="sr-only">Leads and conversions by territory</caption>
              <thead>
                <tr class="border-b border-outline-gray-1">
                  <th scope="col" class="pb-2 text-left font-medium text-ink-gray-6">Territory</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Leads</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Converted</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-outline-gray-1">
                <tr v-for="row in territories" :key="row.territory">
                  <th scope="row" class="py-2 text-left font-normal text-ink-gray-8">
                    {{ row.territory }}
                  </th>
                  <td class="tnum py-2 text-right text-ink-gray-9">{{ formatNumber(row.leads) }}</td>
                  <td class="tnum py-2 text-right text-ink-gray-6">
                    {{ formatNumber(row.converted) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
            <SectionHeader title="Lead owner" hint="All time, by conversion" />
            <table class="mt-4 w-full text-sm">
              <caption class="sr-only">Leads and conversion rate by owner</caption>
              <thead>
                <tr class="border-b border-outline-gray-1">
                  <th scope="col" class="pb-2 text-left font-medium text-ink-gray-6">Owner</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Leads</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Conv.</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-outline-gray-1">
                <tr v-for="row in owners" :key="row.owner">
                  <th
                    scope="row"
                    class="max-w-56 py-2 text-left font-normal text-ink-gray-8"
                    :title="row.owner"
                  >
                    {{ row.owner }}
                  </th>
                  <td class="tnum py-2 text-right text-ink-gray-9">{{ formatNumber(row.leads) }}</td>
                  <td class="tnum py-2 text-right" :class="deltaInk(row.conversion_rate - avgOwnerConversion)">
                    {{ row.conversion_rate }}%
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>

      <IntelligenceDrillDown
        :show="drillDown.show.value"
        :loading="drillDown.loading.value"
        :error="drillDown.error.value"
        :is-permission-error="drillDown.isPermissionError.value"
        :title="drillDown.title.value"
        :columns="drillDown.columns.value"
        :rows="drillDown.rows.value"
        :total="drillDown.total.value"
        :page="drillDown.page.value"
        @close="drillDown.close"
        @retry="drillDown.retry"
        @next-page="drillDown.nextPage"
        @prev-page="drillDown.prevPage"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Badge, Button, Select, Tabs } from 'frappe-ui'
import { Lock, TriangleAlert } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import IntelligenceChart from './components/IntelligenceChart.vue'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'
import KpiCard from './components/KpiCard.vue'
import SectionHeader from './components/SectionHeader.vue'
import SkeletonBlock from './components/SkeletonBlock.vue'
import { useDrillDown } from './composables/useDrillDown'
import { useIntelligenceDashboard } from './composables/useIntelligenceDashboard'
import { chartPalette, themeColor } from '../utils/chartTheme'
import { formatMoney, formatCount as formatNumber } from '../utils/format'
import {
  deltaInk,
  scoreSeverity,
  severityBadge,
  type Severity,
} from '../utils/status'

const CRM_ENDPOINT = 'insights.api.ml.marketing.get_crm_detail'

interface FunnelStage {
  label: string
  count: number
  value: number | null
  conversion_from_prev: number | null
}
interface SourceRow {
  source: string
  leads: number
  converted: number
  quotations: number
  quoted_value: number
  won_value: number
  conversion_rate: number
  value_per_lead: number
}
interface TrendPoint {
  month: string
  leads: number
  converted: number
}
interface AlertRow {
  severity: string
  title: string
  description: string
}
interface MarketingPayload {
  period?: string
  currency?: string
  data_freshness?: { latest_activity: string | null; days_stale: number | null }
  kpis?: {
    total_leads?: number
    new_leads?: number
    open_leads?: number
    converted_leads?: number
    lead_conversion_rate?: number
    open_quote_value?: number
    won_value?: number
    expired_value?: number
    win_rate_by_value?: number
  }
  funnel?: FunnelStage[]
  source_performance?: SourceRow[]
  lead_trend?: TrendPoint[]
  pipeline_by_status?: Array<{ status: string; count: number }>
  territory_performance?: Array<{ territory: string; leads: number; converted: number }>
  owner_performance?: Array<{ owner: string; leads: number; conversion_rate: number }>
  alerts?: AlertRow[]
}

const periodOptions = [
  { label: 'Month to date', value: 'MTD' },
  { label: 'Quarter to date', value: 'QTD' },
  { label: 'Year to date', value: 'YTD' },
  { label: 'Trailing 12 months', value: 'TTM' },
]
const period = ref('TTM')

const tabs = [
  { label: 'Funnel' },
  { label: 'Channels' },
  { label: 'Trend' },
  { label: 'Coverage' },
]
const tabIndex = ref(0)

const drillDown = useDrillDown()

const { data, loading, refreshing, error, isPermissionError, hasData, reload, retry } =
  useIntelligenceDashboard<MarketingPayload>({
    url: 'insights.api.ml.marketing.get_marketing_overview',
    params: computed(() => ({ period: period.value })),
    cache: 'marketing-crm-intelligence',
  })

const kpis = computed(() => ({
  total_leads: data.value?.kpis?.total_leads ?? 0,
  new_leads: data.value?.kpis?.new_leads ?? 0,
  open_leads: data.value?.kpis?.open_leads ?? 0,
  converted_leads: data.value?.kpis?.converted_leads ?? 0,
  lead_conversion_rate: data.value?.kpis?.lead_conversion_rate ?? 0,
  open_quote_value: data.value?.kpis?.open_quote_value ?? 0,
  won_value: data.value?.kpis?.won_value ?? 0,
  expired_value: data.value?.kpis?.expired_value ?? 0,
  win_rate_by_value: data.value?.kpis?.win_rate_by_value ?? 0,
}))

const alerts = computed(() => data.value?.alerts ?? [])
const funnel = computed(() => data.value?.funnel ?? [])
const trend = computed(() => data.value?.lead_trend ?? [])
const pipelineByStatus = computed(() => data.value?.pipeline_by_status ?? [])
const territories = computed(() => data.value?.territory_performance ?? [])
const owners = computed(() => data.value?.owner_performance ?? [])

/** Revenue-ordered, because the point of the panel is that volume != revenue. */
const channels = computed(() =>
  [...(data.value?.source_performance ?? [])].sort((a, b) => b.won_value - a.won_value),
)

const currency = computed(() => data.value?.currency || '')

// Resolved once per render from the theme layer; ECharts paints to a canvas and
// cannot read CSS custom properties.
const accent = computed(() => themeColor('--app-accent'))
const palette = computed(() => chartPalette(2))

const openShare = computed(() =>
  kpis.value.total_leads
    ? Math.round((kpis.value.open_leads / kpis.value.total_leads) * 100)
    : 0,
)

const avgOwnerConversion = computed(() => {
  const rows = owners.value
  if (!rows.length) return 0
  return rows.reduce((sum, r) => sum + (r.conversion_rate || 0), 0) / rows.length
})

const freshnessLabel = computed(() => {
  const stale = data.value?.data_freshness?.days_stale
  if (stale === null || stale === undefined) return ''
  if (stale <= 1) return 'up to date'
  return `last activity ${stale} days ago`
})

/**
 * frappe-ui charts wrap ECharts, which paints to a canvas and therefore cannot
 * resolve CSS custom properties. `chartPalette` reads the computed theme values
 * so the series match the app chrome and still follow a [data-theme] switch.
 */
/**
 * Horizontal bar, deliberately NOT frappe-ui's FunnelChart.
 *
 * `funnelChartOptions.ts` hardcodes `sort: 'descending'` and a blue gradient,
 * ignoring `config.colors`. Both are disqualifying here: these stage counts are
 * not monotonic (Lead.status stages and Quotation records are counted off
 * different bases, see the endpoint), so magnitude-sorting them would show
 * "Quoted" ahead of "Reached Opportunity" and misrepresent the process.
 *
 * Data is reversed because ECharts draws a swapped category axis bottom-up, and
 * the first stage should read at the top.
 */
const funnelConfig = computed(() => ({
  data: [...funnel.value].reverse().map((stage) => ({
    stage: stage.label,
    Records: stage.count,
  })),
  title: '',
  xAxis: { key: 'stage', type: 'category' as const },
  yAxis: { title: '' },
  swapXY: true,
  series: [
    { name: 'Records', type: 'bar' as const, color: accent.value, showDataLabels: true },
  ],
}))

const trendConfig = computed(() => ({
  data: trend.value.map((point) => ({
    month: shortMonth(point.month),
    Leads: point.leads,
    Converted: point.converted,
  })),
  title: '',
  xAxis: { key: 'month', type: 'category' as const },
  yAxis: { title: '' },
  // Per-series `color` overrides the config-level palette. Both work for
  // AxisChart: `eChartOptions.ts` applies `config.colors` as the global palette
  // and `axisChartOptions.ts` lets `series[].color` win. FunnelChart is the
  // exception that honours neither.
  series: [
    { name: 'Leads', type: 'bar' as const, color: palette.value[0] },
    {
      name: 'Converted',
      type: 'line' as const,
      color: palette.value[1],
      showDataPoints: true,
    },
  ],
}))

/** Conversion bands. Named so the thresholds are visible at the call site. */
function conversionSeverity(rate: number): Severity {
  return scoreSeverity(rate, { good: 10, warn: 3 })
}

function sharePct(count: number, total: number): number {
  return total ? Math.round((count / total) * 100) : 0
}

function shortMonth(month: string): string {
  const [y, m] = (month || '').split('-')
  if (!y || !m) return month
  return `${['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(m)]} ${y.slice(2)}`
}

</script>
