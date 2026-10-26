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
        <IntelligenceDateFilter v-model="period" :options="FISCAL_PERIOD_RANGES" />
        <Button
          variant="subtle"
          :loading="refreshing"
          icon-left="refresh-cw"
          label="Refresh"
          @click="reload"
        />
      </div>
    </header>

    <div class="flex flex-1 flex-col overflow-hidden">
      <IntelligenceDashboardShell
        :loading="loading"
        :refreshing="refreshing"
        :error="error"
        :is-permission-error="isPermissionError"
        :warming="warming"
        :not-implemented="notImplemented"
        :not-implemented-message="notImplementedMessage"
        :has-data="hasData"
        :kpi-count="6"
        subject="CRM data"
        permission-hint="Ask an administrator for Lead read access."
        @retry="retry"
      >
        <div class="px-6 py-5">
        <Tabs v-model="tabIndex" :tabs="tabs" />

        <!-- Funnel tab: Hero + Attention Rail (Variant C) -->
        <section v-show="tabIndex === 0" class="mt-5">
          <div class="grid grid-cols-1 gap-5 lg:grid-cols-3">

            <!-- Hero panel: funnel bars + KPI stat list -->
            <div class="lg:col-span-2 rounded-lg border border-outline-gray-1 bg-surface-white">
              <div class="p-5">
                <SectionHeader variant="caption" title="Conversion Funnel" :hint="`ERPNext Lead status · ${period}`" />

                <!-- Stage bars -->
                <div v-if="funnel.length" class="mt-4 space-y-px" role="list" aria-label="Conversion funnel stages">
                  <template v-for="(stage, idx) in funnel" :key="stage.label">
                    <div class="flex items-center gap-3 py-0.5" role="listitem">
                      <!-- Stage label: clickable for drill-down -->
                      <div class="w-36 flex-shrink-0 text-right">
                        <button
                          class="text-xs leading-snug text-ink-gray-7 hover:text-ink-gray-9 hover:underline"
                          @click="openFunnelDrill(idx, stage.label)"
                        >
                          {{ stage.label }}
                        </button>
                        <p v-if="idx === 2 && stage.doc_count != null" class="mt-0.5 text-xs text-ink-gray-5">(docs †)</p>
                      </div>

                      <!-- Bar track -->
                      <div class="flex-1 min-w-0 h-9 relative">
                        <!-- Stages 0–2: proportional bar proportional to lead count -->
                        <template v-if="idx < 3">
                          <div
                            class="h-full rounded flex items-center overflow-hidden"
                            :style="{ width: funnelBarWidth(stage.count) + '%', background: 'var(--app-accent)' }"
                          >
                            <span class="tnum pl-2.5 text-sm font-semibold text-white leading-none flex-shrink-0">
                              {{ formatNumber(stage.count) }}
                            </span>
                            <span v-if="stage.doc_count != null" class="ml-1.5 text-xs text-white opacity-80 truncate leading-none">
                              · {{ formatNumber(stage.doc_count) }} docs · {{ stage.value != null ? formatMoney(stage.value, currency, { compact: true }) : '' }}
                            </span>
                          </div>
                        </template>

                        <!-- Stage 3 (Ordered): 3-zone financial breakdown of the pipeline -->
                        <template v-else>
                          <div
                            class="h-full flex items-stretch gap-px overflow-hidden rounded bg-surface-gray-1"
                            :style="{ width: funnelBarWidth(funnel[2]?.count ?? 0) + '%' }"
                          >
                            <div
                              v-if="orderedZonePct > 0"
                              class="flex items-center justify-center overflow-hidden text-ink-white text-xs font-medium leading-none"
                              :style="{ width: orderedZonePct + '%', minWidth: '2rem', flexShrink: 0, background: 'var(--app-warn-fill)' }"
                            >
                              <span class="tnum truncate px-1">{{ formatMoney(kpis.won_value, currency, { compact: true }) }}</span>
                            </div>
                            <div
                              v-if="expiredZonePct > 0"
                              class="flex items-center justify-center overflow-hidden text-xs font-medium border-2 border-dashed leading-none"
                              :style="{ width: expiredZonePct + '%', flexShrink: 0, borderColor: 'var(--app-neg-fill)', color: 'var(--app-neg)' }"
                            >
                              <span class="tnum truncate px-1">{{ formatMoney(kpis.expired_value, currency, { compact: true }) }}</span>
                            </div>
                            <div
                              v-if="openZonePct > 0"
                              class="flex items-center justify-center overflow-hidden text-xs font-medium border-2 border-dashed leading-none"
                              :style="{ width: openZonePct + '%', flexShrink: 0, borderColor: 'var(--app-accent)', color: 'var(--app-accent)' }"
                            >
                              <span class="tnum truncate px-1">{{ formatMoney(kpis.open_quote_value, currency, { compact: true }) }}</span>
                            </div>
                          </div>
                        </template>
                      </div>

                      <!-- Conversion annotation (right side) -->
                      <div class="w-28 flex-shrink-0 text-right text-xs text-ink-gray-5">
                        <template v-if="idx === 0">leads</template>
                        <template v-else-if="stage.conversion_from_prev != null">
                          {{ stage.conversion_from_prev }}% from prev
                        </template>
                      </div>
                    </div>

                    <!-- Conversion annotation between Quoted → Ordered stages -->
                    <div
                      v-if="idx === 2 && funnel[3] != null && funnel[3].conversion_from_prev != null"
                      class="flex items-center gap-3 pb-0.5"
                    >
                      <span class="w-36 flex-shrink-0"></span>
                      <span class="text-xs text-ink-gray-5">
                        {{ funnel[3].conversion_from_prev }}% → {{ formatNumber(funnel[3].count) }} converted leads
                      </span>
                    </div>
                  </template>
                </div>

                <!-- 3-zone legend -->
                <div
                  v-if="kpis.won_value || kpis.expired_value || kpis.open_quote_value"
                  class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-ink-gray-6"
                >
                  <span class="flex items-center gap-1.5">
                    <span class="inline-block h-2.5 w-2.5 rounded-sm flex-shrink-0" :style="{ background: 'var(--app-warn-fill)' }" aria-hidden="true"></span>
                    Ordered
                  </span>
                  <span class="flex items-center gap-1.5">
                    <span class="inline-block h-2.5 w-2.5 rounded-sm border border-dashed flex-shrink-0" :style="{ borderColor: 'var(--app-neg-fill)' }" aria-hidden="true"></span>
                    Expired ({{ period }})
                  </span>
                  <span class="flex items-center gap-1.5">
                    <span class="inline-block h-2.5 w-2.5 rounded-sm border border-dashed flex-shrink-0" :style="{ borderColor: 'var(--app-accent)' }" aria-hidden="true"></span>
                    Open pipeline
                  </span>
                </div>

                <!-- Footnote for doc-count annotation -->
                <p v-if="funnel[2]?.doc_count != null" class="mt-2 text-xs text-ink-gray-5 leading-relaxed">
                  † Stage count = unique leads at each status.
                  Doc count = quotation documents raised ({{ formatNumber(funnel[2].doc_count) }} docs for {{ formatNumber(funnel[2].count) }} leads).
                  Ordered and Expired values are period-scoped ({{ period }}).
                </p>
              </div>

              <!-- Divider + KPI stat list -->
              <div class="mx-5 border-t border-outline-gray-1"></div>
              <div class="p-5">
                <SectionHeader variant="caption" title="Key metrics" />
                <dl class="mt-3 divide-y divide-outline-gray-1">
                  <div
                    class="flex items-baseline justify-between gap-2 py-2.5 -mx-2 rounded px-2 cursor-pointer hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
                    tabindex="0"
                    @click="drillDown.open(CRM_ENDPOINT, 'Leads', { metric: 'leads' })"
                    @keydown.enter="drillDown.open(CRM_ENDPOINT, 'Leads', { metric: 'leads' })"
                  >
                    <dt class="text-sm text-ink-gray-7">Total leads</dt>
                    <dd class="flex flex-shrink-0 items-baseline gap-2 text-right">
                      <span class="tnum text-sm font-semibold text-ink-gray-9">{{ formatNumber(kpis.total_leads) }}</span>
                      <span v-if="kpis.new_leads" class="text-xs text-ink-gray-5">{{ formatNumber(kpis.new_leads) }} this period</span>
                    </dd>
                  </div>
                  <div
                    class="flex items-baseline justify-between gap-2 py-2.5 -mx-2 rounded px-2 cursor-pointer hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
                    tabindex="0"
                    @click="drillDown.open(CRM_ENDPOINT, 'Unqualified Leads', { metric: 'leads', status: ['Lead', 'Open', 'Inquiry', 'Interested'] })"
                    @keydown.enter="drillDown.open(CRM_ENDPOINT, 'Unqualified Leads', { metric: 'leads', status: ['Lead', 'Open', 'Inquiry', 'Interested'] })"
                  >
                    <dt class="text-sm text-ink-gray-7">Unqualified / open</dt>
                    <dd class="flex flex-shrink-0 items-baseline gap-2 text-right">
                      <span class="tnum text-sm font-semibold text-ink-gray-9">{{ formatNumber(kpis.open_leads) }}</span>
                      <span class="text-xs text-ink-gray-5">{{ openShare }}% of all</span>
                    </dd>
                  </div>
                  <div
                    class="flex items-baseline justify-between gap-2 py-2.5 -mx-2 rounded px-2 cursor-pointer hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
                    tabindex="0"
                    @click="drillDown.open(CRM_ENDPOINT, 'Converted Leads', { metric: 'leads', status: 'Converted' })"
                    @keydown.enter="drillDown.open(CRM_ENDPOINT, 'Converted Leads', { metric: 'leads', status: 'Converted' })"
                  >
                    <dt class="text-sm text-ink-gray-7">Lead conversion rate</dt>
                    <dd class="flex flex-shrink-0 items-baseline gap-2 text-right">
                      <span class="tnum text-sm font-semibold text-ink-gray-9">{{ kpis.lead_conversion_rate }}%</span>
                      <span class="text-xs text-ink-gray-5">{{ formatNumber(kpis.converted_leads) }} converted</span>
                    </dd>
                  </div>
                  <div
                    class="flex items-baseline justify-between gap-2 py-2.5 -mx-2 rounded px-2 cursor-pointer hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
                    tabindex="0"
                    @click="drillDown.open(CRM_ENDPOINT, 'Draft Quotations', { metric: 'quotations', status: 'Draft' })"
                    @keydown.enter="drillDown.open(CRM_ENDPOINT, 'Draft Quotations', { metric: 'quotations', status: 'Draft' })"
                  >
                    <dt class="text-sm text-ink-gray-7">Open pipeline</dt>
                    <dd class="flex flex-shrink-0 items-baseline gap-2 text-right">
                      <span class="tnum text-sm font-semibold text-ink-gray-9">{{ formatMoney(kpis.open_quote_value, currency, { compact: true }) }}</span>
                      <span class="text-xs text-ink-gray-5">Draft quotations</span>
                    </dd>
                  </div>
                  <div
                    class="flex items-baseline justify-between gap-2 py-2.5 -mx-2 rounded px-2 cursor-pointer hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
                    tabindex="0"
                    @click="drillDown.open(CRM_ENDPOINT, 'Ordered Quotations', { metric: 'quotations', status: 'Ordered', creation_from: data?.period_start })"
                    @keydown.enter="drillDown.open(CRM_ENDPOINT, 'Ordered Quotations', { metric: 'quotations', status: 'Ordered', creation_from: data?.period_start })"
                  >
                    <dt class="text-sm text-ink-gray-7">Won (ordered)</dt>
                    <dd class="flex flex-shrink-0 items-baseline gap-2 text-right">
                      <span class="tnum text-sm font-semibold text-ink-gray-9">{{ formatMoney(kpis.won_value, currency, { compact: true }) }}</span>
                      <span v-if="kpis.period_won_count" class="text-xs text-ink-gray-5">{{ formatNumber(kpis.period_won_count) }} orders</span>
                    </dd>
                  </div>
                  <div class="flex items-baseline justify-between gap-2 py-2.5">
                    <dt class="text-sm text-ink-gray-7">Win rate by value</dt>
                    <dd class="flex flex-shrink-0 items-baseline gap-2 text-right">
                      <span
                        class="tnum text-sm font-semibold"
                        :class="kpis.win_rate_by_value > 0 && kpis.win_rate_by_value < 20 ? 'text-ink-red-4' : 'text-ink-gray-9'"
                      >{{ kpis.win_rate_by_value > 0 ? `${kpis.win_rate_by_value}%` : '-' }}</span>
                      <span v-if="kpis.expired_value" class="text-xs text-ink-gray-5">
                        {{ formatMoney(kpis.expired_value, currency, { compact: true }) }} expired
                      </span>
                    </dd>
                  </div>
                </dl>
              </div>
            </div>

            <!-- Attention Rail: alerts + channel effectiveness -->
            <div class="flex flex-col gap-5">
              <div
                v-if="alerts.length"
                class="rounded-lg border border-outline-gray-1 bg-surface-white p-5"
                aria-label="Alerts"
              >
                <SectionHeader variant="caption" title="Needs attention" />
                <div class="mt-3 space-y-4">
                  <article v-for="(alert, i) in alerts" :key="i">
                    <div class="flex items-start justify-between gap-2">
                      <p class="text-sm font-medium text-ink-gray-9 leading-snug">{{ alert.title }}</p>
                      <Badge
                        v-bind="severityBadge(alert.severity)"
                        :label="severityBadge(alert.severity).label"
                        size="sm"
                        class="flex-shrink-0"
                      />
                    </div>
                    <p class="mt-1 text-xs text-ink-gray-6 leading-relaxed">{{ alert.description }}</p>
                  </article>
                </div>
              </div>

              <div
                v-if="channelsEffective.length"
                class="rounded-lg border border-outline-gray-1 bg-surface-white p-5"
              >
                <SectionHeader variant="caption" title="Channel effectiveness" :hint="`${currency} / lead`" />
                <table class="mt-3 w-full text-sm">
                  <caption class="sr-only">Channel effectiveness by value per lead</caption>
                  <thead>
                    <tr class="border-b border-outline-gray-1">
                      <th scope="col" class="pb-2 text-left text-xs font-medium text-ink-gray-6">Source</th>
                      <th scope="col" class="pb-2 text-right text-xs font-medium text-ink-gray-6">Conv.</th>
                      <th scope="col" class="pb-2 text-right text-xs font-medium text-ink-gray-6">{{ currency }}/lead</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-outline-gray-1">
                    <tr v-for="row in channelsEffective" :key="row.source" class="hover:bg-surface-gray-1">
                      <th scope="row" class="max-w-28 truncate py-1.5 text-left text-xs font-normal text-ink-gray-8" :title="row.source">
                        {{ row.source }}
                      </th>
                      <td class="tnum py-1.5 text-right">
                        <Badge
                          v-bind="severityBadge(conversionSeverity(row.conversion_rate))"
                          :label="`${row.conversion_rate}%`"
                          size="sm"
                        />
                      </td>
                      <td class="tnum py-1.5 text-right text-xs font-medium text-ink-gray-9">
                        {{ formatMoney(row.value_per_lead, currency, { compact: true }) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
                <button
                  class="mt-3 text-xs text-ink-blue-3 hover:underline"
                  @click="tabIndex = 1"
                >
                  View full channel report →
                </button>
              </div>
            </div>

          </div>
        </section>

        <!-- Channels: the money panel -->
        <section v-show="tabIndex === 1" class="mt-5 space-y-5">
          <TabBrief :brief="tabBriefs.channels" :as-of="data?.data_freshness?.latest_activity ?? undefined" />
          <StatStrip :items="channelsStrip" :currency="currency" />
          <div v-if="wonBars.length" class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
            <SectionHeader variant="caption" title="Won revenue by channel" :hint="`Top ${wonBars.length}, ${currency} won, all time`" />
            <ul class="mt-3 space-y-3">
              <li v-for="row in wonBars" :key="row.source">
                <div class="flex items-baseline justify-between gap-3 text-sm">
                  <span class="truncate text-ink-gray-9">{{ row.source }}</span>
                  <span class="tnum font-medium text-ink-gray-9">{{ formatMoney(row.won_value, currency) }}</span>
                </div>
                <div
                  class="mt-1 h-2 w-full overflow-hidden rounded-full bg-surface-gray-2"
                  role="img"
                  :aria-label="`${row.source}: ${formatMoney(row.won_value, currency)}`"
                >
                  <div class="h-full rounded-full bg-surface-gray-5" :style="{ width: `${row.pct}%` }" />
                </div>
                <p class="tnum mt-1 text-xs text-ink-gray-6">
                  {{ formatNumber(row.leads) }} leads, {{ row.conversion_rate }}% converted, {{ formatMoney(row.value_per_lead, currency) }} per lead
                </p>
              </li>
            </ul>
          </div>
          <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
            <SectionHeader
              variant="caption"
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
                    <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Vol %</th>
                    <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Conv.</th>
                    <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Quotes (#)</th>
                    <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Quoted Value</th>
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
                    <td class="tnum py-2.5 text-right text-ink-gray-6">
                      {{ kpis.total_leads ? `${((row.leads / kpis.total_leads) * 100).toFixed(1)}%` : NO_VALUE }}
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
          <TabActions class="mt-6" :actions="tabBriefs.channels?.actions" />
        </section>

        <!-- What changed -->
        <section v-show="tabIndex === 2" class="mt-5 space-y-5">
          <TabBrief :brief="tabBriefs.trend" :as-of="data?.data_freshness?.latest_activity ?? undefined" />
          <StatStrip :items="trendStrip" />
          <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
            <SectionHeader variant="caption" title="Lead intake by month" hint="New leads, and how many converted" />
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
            <table v-if="recentMonths.length" class="mt-4 w-full text-sm">
              <caption class="mb-2 text-left text-xs text-ink-gray-6">Recent months</caption>
              <thead class="bg-surface-gray-1">
                <tr>
                  <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Month</th>
                  <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Leads</th>
                  <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Change</th>
                  <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Converted</th>
                  <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Conversion</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in recentMonths" :key="m.month" class="border-b border-outline-gray-1">
                  <td class="px-4 py-2 text-ink-gray-8">{{ shortMonth(m.month) }}</td>
                  <td class="px-4 py-2 text-right text-ink-gray-8">{{ formatNumber(m.leads) }}</td>
                  <td
                    class="px-4 py-2 text-right"
                    :class="m.mom === null ? 'text-ink-gray-6' : m.mom < 0 ? 'text-ink-red-3' : 'text-ink-green-3'"
                  >
                    {{ m.mom === null ? NO_VALUE : `${m.mom > 0 ? '+' : ''}${m.mom.toFixed(0)}%` }}
                  </td>
                  <td class="px-4 py-2 text-right text-ink-gray-8">{{ formatNumber(m.converted) }}</td>
                  <td class="px-4 py-2 text-right text-ink-gray-7">{{ m.rate === null ? NO_VALUE : `${m.rate.toFixed(1)}%` }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <TabActions class="mt-6" :actions="tabBriefs.trend?.actions" />
        </section>

        <!-- Coverage -->
        <section v-show="tabIndex === 3" class="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div class="space-y-5 lg:col-span-2">
            <TabBrief :brief="tabBriefs.coverage" :as-of="data?.data_freshness?.latest_activity ?? undefined" />
            <StatStrip :items="coverageStrip" />
            <TabActions class="mt-6" :actions="tabBriefs.coverage?.actions" />
          </div>
          <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
            <SectionHeader variant="caption" title="Territory" hint="All time. Bar is green above team average, red under 5%" />
            <table class="mt-4 w-full text-sm">
              <caption class="sr-only">Leads and conversions by territory</caption>
              <thead>
                <tr class="border-b border-outline-gray-1">
                  <th scope="col" class="pb-2 text-left font-medium text-ink-gray-6">Territory</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Leads</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Converted</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Conv.</th>
                  <th scope="col" class="w-1/3 pb-2 pl-3 text-left font-medium text-ink-gray-6">Rate</th>
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
                  <td class="tnum py-2 text-right text-ink-gray-7">
                    {{ row.leads > 0 ? `${((row.converted / row.leads) * 100).toFixed(1)}%` : NO_VALUE }}
                  </td>
                  <td class="py-2 pl-3">
                    <div class="h-1.5 w-full rounded-full bg-surface-gray-2">
                      <div
                        class="h-1.5 rounded-full"
                        :class="severityFill(territorySeverity(territoryRate(row)))"
                        :style="{ width: `${maxTerritoryRate ? (territoryRate(row) / maxTerritoryRate) * 100 : 0}%` }"
                      />
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
            <SectionHeader variant="caption" title="Lead owner" hint="All time, by conversion" />
            <table class="mt-4 w-full text-sm">
              <caption class="sr-only">Leads and conversion rate by owner</caption>
              <thead>
                <tr class="border-b border-outline-gray-1">
                  <th scope="col" class="pb-2 text-left font-medium text-ink-gray-6">Owner</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Leads</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Conv.</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">vs team</th>
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
                  <td class="tnum py-2 text-right" :class="ownerDeltaInk(row.conversion_rate - avgOwnerConversion)">
                    {{ row.conversion_rate }}%
                  </td>
                  <td class="tnum py-2 text-right text-ink-gray-7">
                    {{ kpis.lead_conversion_rate ? `${row.conversion_rate >= kpis.lead_conversion_rate ? '+' : ''}${(row.conversion_rate - kpis.lead_conversion_rate).toFixed(1)} pp` : NO_VALUE }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- `v-if`, not `v-show` like its siblings: this tab owns a separate
             endpoint, so mounting it is what issues the request. No reason to
             score every open lead for someone who never opened the tab. -->
        <section v-if="tabIndex === 4" class="mt-5">
          <LeadWinProbability />
        </section>
        </div>
      </IntelligenceDashboardShell>
      <IntelligenceDrillDown
        v-model:show="drillDown.show.value"
        :loading="drillDown.loading.value"
        :error="drillDown.error.value"
        :is-permission-error="drillDown.isPermissionError.value"
        :title="drillDown.title.value"
        :columns="drillDown.columns.value"
        :rows="drillDown.rows.value"
        :total="drillDown.total.value"
        :page="drillDown.page.value"
        @retry="drillDown.retry"
        @next-page="drillDown.nextPage"
        @prev-page="drillDown.prevPage"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Badge, Button, Tabs } from 'frappe-ui'
import { computed, ref } from 'vue'
import IntelligenceChart from './components/IntelligenceChart.vue'
import IntelligenceDashboardShell from './components/IntelligenceDashboardShell.vue'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'
import KpiCard from './components/KpiCard.vue'
import TabBrief, { type Brief } from './components/TabBrief.vue'
import TabActions from './components/TabActions.vue'
import StatStrip, { type StatItem } from './components/StatStrip.vue'
import LeadWinProbability from './components/LeadWinProbability.vue'
import SectionHeader from './components/SectionHeader.vue'
import { useDrillDown, type DrillDownParams } from './composables/useDrillDown'
import { useIntelligenceDashboard } from './composables/useIntelligenceDashboard'
import { chartPalette } from '../utils/chartTheme'
import { formatMoney, formatCount as formatNumber, NO_VALUE } from '../utils/format'
import { FISCAL_PERIOD_RANGES } from '../utils/dateRangePresets'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import {
  deltaInk,
  scoreSeverity,
  severityBadge,
  severityFill,
  type Severity,
} from '../utils/status'

const CRM_ENDPOINT = 'insights.api.ml.marketing.get_crm_detail'

// Index-aligned with the fixed 4-stage order `_build_marketing_funnel`
// (api/ml/marketing.py) always emits: Leads, Reached Opportunity, Quoted,
// Ordered. Keyed by position rather than `stage.label`, which passes through
// Frappe's `_()` translation and cannot be relied on to match literally.
// Verified against live data 2026-08-17: each drill-down `total` matches its
// funnel stage `count` exactly (2,607 / 4,036 / 548 on this site).
// All four stages now count distinct leads, so drill-downs use `metric:'leads'`
// throughout. Updated 2026-10-22 when the funnel fix made stage counts lead-based.
const FUNNEL_DRILL_PARAMS: DrillDownParams[] = [
  { metric: 'leads' },
  { metric: 'leads', status: ['Opportunity', 'Quotation', 'Converted', 'Lost Quotation'] },
  { metric: 'leads', status: ['Quotation', 'Converted', 'Lost Quotation'] },
  { metric: 'leads', status: 'Converted' },
]

interface FunnelStage {
  label: string
  count: number
  doc_count?: number | null   // quotation document count (can exceed lead count)
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
    /** Period-scoped ordered quotation count — matches the won_value window. */
    period_won_count?: number
    expired_value?: number
    win_rate_by_value?: number
  }
  /** ISO date string of the period start; passed to the Won drill so the drill
   *  total matches kpis.won_value (audit fix 2026-10-26). */
  period_start?: string
  funnel?: FunnelStage[]
  source_performance?: SourceRow[]
  lead_trend?: TrendPoint[]
  pipeline_by_status?: Array<{ status: string; count: number }>
  territory_performance?: Array<{ territory: string; leads: number; converted: number }>
  owner_performance?: Array<{ owner: string; leads: number; conversion_rate: number }>
  alerts?: AlertRow[]
  tab_briefs?: Record<string, Brief>
}

const period = ref('TTM')

const tabs = [
  { label: 'Funnel' },
  { label: 'Channels' },
  { label: 'Trend' },
  { label: 'Coverage' },
  { label: 'Win Probability' },
]
const tabIndex = ref(0)

const drillDown = useDrillDown()

function openFunnelDrill(idx: number, label: string) {
  const params = FUNNEL_DRILL_PARAMS[idx]
  if (params) drillDown.open(CRM_ENDPOINT, label, params)
}

const {
  data,
  loading,
  refreshing,
  error,
  isPermissionError,
  warming,
  notImplemented,
  notImplementedMessage,
  hasData,
  reload,
  retry,
} =
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
  period_won_count: data.value?.kpis?.period_won_count ?? 0,
  expired_value: data.value?.kpis?.expired_value ?? 0,
  win_rate_by_value: data.value?.kpis?.win_rate_by_value ?? 0,
}))

const alerts = computed(() => data.value?.alerts ?? [])
const funnel = computed(() => data.value?.funnel ?? [])
const trend = computed(() => data.value?.lead_trend ?? [])
/** Last 6 months with month-over-month lead change; arithmetic on lead_trend only. */
const recentMonths = computed(() =>
  trend.value.slice(-7).map((p, i, a) => {
    const prev = i > 0 ? a[i - 1].leads : 0
    return {
      month: p.month,
      leads: p.leads,
      converted: p.converted,
      mom: prev > 0 ? ((p.leads - prev) / prev) * 100 : null,
      rate: p.leads > 0 ? (p.converted / p.leads) * 100 : null,
    }
  }).slice(-6),
)

const pipelineByStatus = computed(() => data.value?.pipeline_by_status ?? [])
const territories = computed(() => data.value?.territory_performance ?? [])
const owners = computed(() => data.value?.owner_performance ?? [])

/** Revenue-ordered for the Channels tab; ₹/lead-ordered for the Funnel rail. */
const channels = computed(() =>
  [...(data.value?.source_performance ?? [])].sort((a, b) => b.won_value - a.won_value),
)

/** Top 5 channels with revenue won, bar width relative to the largest. */
const wonBars = computed(() => {
  const rows = channels.value.filter((r) => r.won_value > 0).slice(0, 5)
  const max = rows[0]?.won_value ?? 0
  return rows.map((r) => ({ ...r, pct: max ? (r.won_value / max) * 100 : 0 }))
})

/** Top 7 channels by value-per-lead for the Funnel tab attention rail. */
const channelsEffective = computed(() =>
  [...(data.value?.source_performance ?? [])]
    .filter((r) => r.value_per_lead > 0)
    .sort((a, b) => b.value_per_lead - a.value_per_lead)
    .slice(0, 7),
)

const currency = computed(() => data.value?.currency || '')

const tabBriefs = computed(() => data.value?.tab_briefs ?? {})
const MIN_OWNER_LEADS = 50 // same floor as the server brief

const channelsStrip = computed<StatItem[]>(() => {
  const k = data.value?.kpis
  return [
    { label: 'Total Leads', value: k?.total_leads ?? null },
    {
      label: 'Conversion Rate',
      percent: k?.lead_conversion_rate ?? null,
      sublabel: k?.converted_leads != null ? `${formatNumber(k.converted_leads)} converted` : undefined,
    },
    { label: 'Won Revenue', amount: k?.won_value ?? null, sublabel: 'ordered quotations' },
    { label: 'Expired', amount: k?.expired_value ?? null, sublabel: 'quoted, never ordered' },
  ]
})

const trendStrip = computed<StatItem[]>(() => {
  const t = trend.value
  const sum = (rows: TrendPoint[]) => rows.reduce((s, r) => s + r.leads, 0)
  const peak = t.reduce<TrendPoint | null>((m, p) => (!m || p.leads > m.leads ? p : m), null)
  const last3 = t.slice(-3)
  const last12 = t.slice(-12)
  const prior12 = t.slice(-24, -12)
  const yoy = prior12.length === 12 && sum(prior12) ? Math.round((sum(last12) / sum(prior12) - 1) * 100) : null
  return [
    { label: 'Peak Month', value: peak?.leads ?? null, sublabel: peak?.month },
    { label: 'Last 3 Months Avg', value: last3.length === 3 ? Math.round(sum(last3) / 3) : null, sublabel: 'leads per month' },
    {
      label: 'Last 12 Months',
      value: last12.length === 12 ? sum(last12) : null,
      sublabel: yoy == null ? 'leads' : `leads, ${yoy > 0 ? '+' : ''}${yoy}% vs prior 12`,
      tone: yoy != null && yoy < 0 ? 'neg' : undefined,
    },
    { label: 'Prior 12 Months', value: prior12.length === 12 ? sum(prior12) : null, sublabel: 'leads' },
  ]
})

const coverageStrip = computed<StatItem[]>(() => {
  const unassigned = territories.value.find((t) => t.territory === 'Unassigned')
  const top = owners.value
    .filter((o) => o.leads >= MIN_OWNER_LEADS)
    .reduce<(typeof owners.value)[number] | null>((m, o) => (!m || o.conversion_rate > m.conversion_rate ? o : m), null)
  return [
    { label: 'Territories', value: territories.value.filter((t) => t !== unassigned).length || null, sublabel: unassigned ? 'plus Unassigned' : undefined },
    { label: 'Team Avg Conversion', percent: data.value?.kpis?.lead_conversion_rate ?? null },
    { label: 'Best Owner Conversion', percent: top?.conversion_rate ?? null, sublabel: top?.owner },
    { label: 'Unassigned Leads', value: unassigned?.leads ?? null },
  ]
})

// ECharts cannot read CSS custom properties; chartPalette reads computed values.
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

/** Colour an owner's conversion-rate delta from the team average, but only
 *  once the gap is wide enough to be a real signal: a sub-2pt deviation is
 *  noise and gets the same neutral ink `deltaInk` already uses for zero. */
function ownerDeltaInk(delta: number): string {
  return Math.abs(delta) >= 2 ? deltaInk(delta) : 'text-ink-gray-6'
}

const freshnessLabel = computed(() => {
  const stale = data.value?.data_freshness?.days_stale
  if (stale === null || stale === undefined) return ''
  if (stale <= 1) return 'up to date'
  return `last activity ${stale} days ago`
})

/** Proportional bar width for the funnel hero (stage count / total leads × 100). */
function funnelBarWidth(count: number): number {
  const max = funnel.value[0]?.count || 1
  return Math.round((count / max) * 100 * 10) / 10
}

/**
 * 3-zone proportions for the Ordered row: Ordered / Expired (period) / Open.
 * Using the sum of the three shown values as the denominator keeps the zones
 * proportional to each other regardless of the historical total.
 */
const _zoneDenominator = computed(
  () => kpis.value.won_value + kpis.value.expired_value + kpis.value.open_quote_value,
)
function _zonePct(value: number): number {
  const d = _zoneDenominator.value
  return d > 0 ? Math.max(0, Math.round((value / d) * 100 * 10) / 10) : 0
}
const orderedZonePct = computed(() => _zonePct(kpis.value.won_value))
const expiredZonePct = computed(() => _zonePct(kpis.value.expired_value))
const openZonePct = computed(() => _zonePct(kpis.value.open_quote_value))


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

/** Territory bar: green above the team average, red under 5%, amber between. */
function territorySeverity(rate: number): Severity {
  const avg = data.value?.kpis?.lead_conversion_rate
  if (avg != null && rate > avg) return 'low'
  return rate < 5 ? 'high' : 'medium'
}

const maxTerritoryRate = computed(() =>
  Math.max(0, ...territories.value.map((t) => (t.leads > 0 ? (t.converted / t.leads) * 100 : 0))),
)

function territoryRate(row: { leads: number; converted: number }): number {
  return row.leads > 0 ? (row.converted / row.leads) * 100 : 0
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
