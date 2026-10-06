<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <header class="bg-surface-white border-b border-outline-gray-1 px-6 py-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-ink-gray-9">Procurement Intelligence</h1>
        <p v-if="windowLabel" class="mt-1 text-sm text-ink-gray-6">
          Period: {{ windowLabel }}. Pending orders, overdue items and payment exposure are current, not period-based.
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <span v-if="lastUpdated" class="text-sm text-ink-gray-6">
          Updated: {{ formatDate(lastUpdated) }}
        </span>
        <IntelligenceDateFilter v-model="dateFilter" />
        <Button
          variant="solid"
          @click="reload"
          :loading="refreshing"
          aria-label="Refresh procurement analysis"
        >
          <template #prefix><RefreshCcw class="w-4 h-4" /></template>
          Refresh Analysis
        </Button>
      </div>
    </header>

    <IntelligenceDashboardShell
      :loading="loading"
      :refreshing="refreshing"
      :error="error ?? undefined"
      :is-permission-error="isPermissionError"
      :has-data="hasData"
      :warming="warming"
      :not-implemented="notImplemented"
      :not-implemented-message="notImplementedMessage"
      :kpi-count="6"
      subject="procurement data"
      permission-hint="Ask an administrator for procurement read access."
      @retry="retry"
    >
    <!-- Summary Cards -->
    <div class="p-6 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <KpiCard
        label="Total Spend"
        :amount="spendData.total_spend"
        :currency="baseCurrency"
        :delta="spendData.prior_period_growth"
        :delta-higher-is-better="false"
        :sublabel="spendData.prior_period_growth == null ? undefined : 'vs prior period'"
        :loading="loading && !hasData"
        :error="error ?? undefined"
      />
      <KpiCard
        label="Active Suppliers"
        :value="spendData.supplier_count"
        sublabel="Invoiced in period"
        :loading="loading && !hasData"
        :error="error ?? undefined"
      />
      <KpiCard
        label="Avg Lead Time"
        :value="supplierData.avg_lead_time"
        unit=" days"
        sublabel="PO to receipt"
        :loading="loading && !hasData"
        :error="error ?? undefined"
      />
      <KpiCard
        label="On-Time Delivery"
        :percent="supplierData.avg_on_time_rate"
        :severity="onTimeSeverity"
        :loading="loading && !hasData"
        :error="error ?? undefined"
      />
      <KpiCard
        label="Pending POs (current)"
        :value="purchaseData.pending_count"
        :sublabel="pendingSublabel"
        :clickable="true"
        :loading="loading && !hasData"
        :error="error ?? undefined"
        @click="drillDown.open(PROC_ENDPOINT, 'Pending Purchase Orders', { metric: 'pending_pos' })"
      />
      <KpiCard
        label="Risk Score"
        :value="riskData.risk_score"
        unit="/100"
        :sublabel="getRiskLabel(riskData.risk_score)"
        :severity="riskSeverity"
        :clickable="true"
        :loading="loading && !hasData"
        :error="error ?? undefined"
        @click="tabIndex = RISKS_TAB_INDEX"
      />
    </div>

    <!-- Tabs -->
    <div class="mx-6">
      <Tabs v-model="tabIndex" :tabs="tabDefs" />
    </div>

    <!-- Tab Content -->
    <div class="flex-1 p-6 overflow-auto">
      <!-- Tab 1: Spend Overview -->
      <div v-if="activeTab === 'spend'" class="space-y-6">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Monthly Spend Trend -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="Monthly Spend Trend" :hint="baseCurrency" :level="3" />
            <IntelligenceChart v-if="spendData.monthly_trend?.length" class="mt-4 h-48 sm:h-56 lg:h-64" :config="monthlySpendConfig" />
            <div v-else class="h-48 flex items-center justify-center text-ink-gray-6">
              No spend data available
            </div>
            <table v-if="spendData.monthly_trend?.length" class="sr-only">
              <caption>Monthly procurement spend</caption>
              <thead>
                <tr>
                  <th scope="col">Month</th>
                  <th scope="col">Spend</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="month in spendData.monthly_trend" :key="month.period">
                  <th scope="row">{{ monthLabel(month) }}</th>
                  <td>{{ formatCurrency(month.spend) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Spend by Category -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="Spend by Category" hint="% of period spend" :level="3" />
            <IntelligenceChart v-if="spendData.by_category?.length" class="mt-4 h-48 sm:h-56 lg:h-64" :config="spendByCategoryConfig" />
            <div v-else class="h-48 flex items-center justify-center text-ink-gray-6">
              No category data available
            </div>
            <table v-if="spendData.by_category?.length" class="sr-only">
              <caption>Spend by category as percent of total</caption>
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  <th scope="col">Spend</th>
                  <th scope="col">% of total</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="cat in spendData.by_category" :key="cat.category">
                  <th scope="row">{{ cat.category }}</th>
                  <td>{{ formatCurrency(cat.spend) }}</td>
                  <td>{{ formatPercent(cat.pct_of_total) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Top Suppliers by Spend -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" title="Top Suppliers by Spend" hint="Select a supplier to see its invoices" :level="3" />
          <div class="mt-4 overflow-x-auto" v-if="spendData.top_suppliers?.length">
            <table class="min-w-full">
              <thead>
                <tr class="bg-surface-gray-1">
                  <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Supplier</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Invoices</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Total Spend</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">% of Total</th>
                  <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Share</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-outline-gray-1">
                <tr v-for="sup in spendData.top_suppliers" :key="sup.supplier"
                    class="cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
                    @click="openSupplierInvoices(sup)">
                  <td class="px-4 py-3">
                    <button type="button" :class="LINK_BUTTON_CLASS">{{ supplierLabel(sup) }}</button>
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ formatCount(sup.invoice_count) }}</td>
                  <td class="px-4 py-3 text-right text-sm font-medium text-ink-gray-9">
                    {{ formatCurrency(sup.spend) }}
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ formatPercent(sup.pct_of_total) }}</td>
                  <td class="px-4 py-3 w-32">
                    <div class="bg-surface-gray-2 rounded-full h-2 overflow-hidden">
                      <div
                        class="bg-surface-blue-3 h-full rounded-full"
                        :style="{ width: `${sup.pct_of_total ?? 0}%` }"
                        role="img"
                        :aria-label="`${formatPercent(sup.pct_of_total)} of period spend`"
                      ></div>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="text-center py-6 text-sm text-ink-gray-6">No suppliers found</div>
        </div>
      </div>

      <!-- Tab 2: Supplier Performance -->
      <div v-if="activeTab === 'suppliers'" class="space-y-6">
        <!-- Performance Summary -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <KpiCard
            label="Avg Performance Score"
            :value="supplierData.avg_score"
            unit="/100"
            variant="tile"
            :loading="loading && !hasData"
          />
          <KpiCard
            label="Avg On-Time Rate"
            :percent="supplierData.avg_on_time_rate"
            variant="tile"
            :loading="loading && !hasData"
          />
          <KpiCard
            :label="qualityStatus === 'not_implemented' ? 'Avg Quality Rate (not tracked)' : 'Avg Quality Rate'"
            :percent="qualityStatus === 'not_implemented' ? null : (supplierData.avg_quality_rate ?? null)"
            variant="tile"
            :loading="loading && !hasData"
          />
          <KpiCard
            label="Avg Lead Time"
            :value="supplierData.avg_lead_time"
            unit=" days"
            variant="tile"
            :loading="loading && !hasData"
          />
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Top Performers -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="Top Performers" :level="3" />
            <div class="mt-4 space-y-3" v-if="supplierData.top_performers?.length">
              <div v-for="(sup, idx) in supplierData.top_performers?.slice(0, 5)" :key="sup.supplier"
                   :class="ROW_BUTTON_CLASS"
                   role="button"
                   tabindex="0"
                   @click="openSupplierPOs(sup)"
                   @keydown.enter.prevent="openSupplierPOs(sup)"
                   @keydown.space.prevent="openSupplierPOs(sup)">
                <div class="w-8 h-8 bg-surface-gray-3 rounded-full flex items-center justify-center text-ink-gray-9 font-bold text-sm">
                  {{ idx + 1 }}
                </div>
                <div class="flex-1">
                  <div class="font-medium text-ink-gray-9">{{ supplierLabel(sup) }}</div>
                  <div class="text-sm text-ink-gray-6">
                    On-time: {{ formatPercent(sup.on_time_rate) }} | Quality: {{ formatPercent(sup.quality_rate) }}
                  </div>
                </div>
                <div class="text-lg font-bold text-ink-gray-9">{{ scoreLabel(sup.overall_score) }}</div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-sm text-ink-gray-6">No supplier performance data</div>
          </div>

          <!-- Needs Improvement -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="Needs Improvement" :level="3" />
            <div class="mt-4 space-y-3" v-if="supplierData.bottom_performers?.length">
              <div v-for="sup in supplierData.bottom_performers?.slice(0, 5)" :key="sup.supplier"
                   :class="ROW_BUTTON_CLASS"
                   role="button"
                   tabindex="0"
                   @click="openSupplierPOs(sup)"
                   @keydown.enter.prevent="openSupplierPOs(sup)"
                   @keydown.space.prevent="openSupplierPOs(sup)">
                <div class="flex-1">
                  <div class="font-medium text-ink-gray-9">{{ supplierLabel(sup) }}</div>
                  <div class="text-sm text-ink-gray-6">
                    On-time: {{ formatPercent(sup.on_time_rate) }} | Quality: {{ formatPercent(sup.quality_rate) }}
                  </div>
                </div>
                <div class="text-lg font-bold text-ink-gray-9">{{ scoreLabel(sup.overall_score) }}</div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-sm text-ink-gray-6">No underperforming suppliers</div>
          </div>
        </div>

        <!-- All Suppliers Table -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" title="All Supplier Scores" hint="Select a supplier to see its purchase orders" :level="3" />
          <div class="mt-4 overflow-x-auto" v-if="supplierData.all_suppliers?.length">
            <table class="min-w-full">
              <thead>
                <tr class="bg-surface-gray-1">
                  <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Supplier</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">PO Count</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Total Value</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">On-Time %</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Quality %</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Lead Time</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Score</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-outline-gray-1">
                <tr v-for="sup in supplierData.all_suppliers?.slice(0, 20)" :key="sup.supplier"
                    class="cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
                    @click="openSupplierPOs(sup)">
                  <td class="px-4 py-3">
                    <button type="button" :class="LINK_BUTTON_CLASS">{{ supplierLabel(sup) }}</button>
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ formatCount(sup.po_count) }}</td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-9">{{ formatCurrency(sup.total_value) }}</td>
                  <td class="px-4 py-3 text-right">
                    <span :class="rateTint(sup.on_time_rate)" class="rounded px-2 py-0.5 text-sm font-medium text-ink-gray-9">
                      {{ formatPercent(sup.on_time_rate) }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right">
                    <span :class="rateTint(sup.quality_rate)" class="rounded px-2 py-0.5 text-sm font-medium text-ink-gray-9">
                      {{ formatPercent(sup.quality_rate) }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ formatDays(sup.avg_lead_time) }}</td>
                  <td class="px-4 py-3 text-right">
                    <Badge v-bind="severityBadge(scoreSeverity(sup.overall_score, SCORE_THRESHOLDS))"
                           :label="scoreLabel(sup.overall_score)" size="sm" />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="text-center py-6 text-sm text-ink-gray-6">No supplier data available</div>
        </div>
      </div>

      <!-- Tab 3: Purchase Analytics -->
      <div v-if="activeTab === 'analytics'" class="space-y-6">
        <!-- Cycle Times -->
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
          <KpiCard
            label="Total POs"
            :value="purchaseData.total_po_count"
            sublabel="Ordered in period"
            variant="tile"
            :clickable="true"
            :loading="loading && !hasData"
            @click="drillDown.open(PROC_ENDPOINT, 'Total Purchase Orders', { metric: 'total_pos', date_filter: dateFilter })"
          />
          <KpiCard
            label="Overdue POs (current)"
            :value="purchaseData.overdue_po_count"
            sublabel="Past expected date, not closed"
            variant="tile"
            :clickable="true"
            :loading="loading && !hasData"
            @click="drillDown.open(PROC_ENDPOINT, 'Overdue Purchase Orders', { metric: 'overdue_pos' })"
          />
          <KpiCard
            label="MR to PO"
            :value="purchaseData.avg_mr_to_po_days"
            unit=" days"
            :sublabel="purchaseData.avg_mr_to_po_days == null ? 'no material-request links' : 'Average processing time'"
            variant="tile"
            :loading="loading && !hasData"
          />
          <KpiCard
            label="PO to GRN"
            :value="purchaseData.avg_po_to_grn_days"
            unit=" days"
            sublabel="Average delivery time"
            variant="tile"
            :loading="loading && !hasData"
          />
          <KpiCard
            label="GRN to Invoice"
            :value="purchaseData.avg_grn_to_invoice_days"
            unit=" days"
            sublabel="Average invoice time"
            variant="tile"
            :loading="loading && !hasData"
          />
        </div>

        <!-- PO Status Summary -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" title="Purchase Order Status" hint="POs ordered in period" :level="3" />
          <div class="mt-4 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4" v-if="purchaseData.po_status_summary?.length">
            <div v-for="status in purchaseData.po_status_summary" :key="status.status"
                 class="p-4 rounded-lg border border-outline-gray-1 bg-surface-white">
              <Badge v-bind="severityBadge(poStatusSeverity(status.status))"
                     :label="status.status" size="sm" class="mb-2" />
              <div class="text-xl font-bold text-ink-gray-9">{{ formatCount(status.count) }}</div>
              <div class="text-sm text-ink-gray-6">{{ formatCurrency(status.value) }}</div>
            </div>
          </div>
          <div v-else class="text-center py-6 text-sm text-ink-gray-6">No purchase order status data</div>
        </div>

        <!-- Monthly PO Trend -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" title="Monthly Purchase Order Trend" :hint="baseCurrency" :level="3" />
          <IntelligenceChart v-if="purchaseData.monthly_trend?.length" class="mt-4 h-48 sm:h-56 lg:h-64" :config="monthlyPOConfig" />
          <div v-else class="h-48 flex items-center justify-center text-ink-gray-6">
            No purchase order data available
          </div>
          <table v-if="purchaseData.monthly_trend?.length" class="sr-only">
            <caption>Monthly purchase order value</caption>
            <thead>
              <tr>
                <th scope="col">Month</th>
                <th scope="col">PO Value</th>
                <th scope="col">PO Count</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="month in purchaseData.monthly_trend" :key="month.period">
                <th scope="row">{{ monthLabel(month) }}</th>
                <td>{{ formatCurrency(month.po_value) }}</td>
                <td>{{ formatCount(month.po_count) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pending POs -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" :title="`Pending Purchase Orders (${formatCount(purchaseData.pending_count)})`" hint="Current" :level="3" />
          <div class="mt-4 overflow-x-auto" v-if="purchaseData.pending_pos?.length">
            <table class="min-w-full">
              <thead>
                <tr class="bg-surface-gray-1">
                  <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">PO#</th>
                  <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Supplier</th>
                  <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Date</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Amount</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Days Pending</th>
                  <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Status</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-outline-gray-1">
                <tr v-for="po in purchaseData.pending_pos?.slice(0, 15)" :key="po.name">
                  <td class="px-4 py-3">
                    <button type="button" :class="LINK_BUTTON_CLASS" :aria-label="`Open purchase order ${po.name}`"
                            @click="openDocument('Purchase Order', po.name)">
                      {{ po.name }}
                    </button>
                  </td>
                  <td class="px-4 py-3 text-sm text-ink-gray-9">{{ po.supplier }}</td>
                  <td class="px-4 py-3 text-sm text-ink-gray-6">{{ formatDate(po.transaction_date) }}</td>
                  <td class="px-4 py-3 text-right text-sm font-medium text-ink-gray-9">
                    {{ formatCurrency(po.grand_total) }}
                  </td>
                  <td class="px-4 py-3 text-right">
                    <Badge v-bind="severityBadge(scoreSeverity(po.days_pending, { good: 7, warn: 14, higherIsBetter: false }))"
                           :label="`${formatCount(po.days_pending)} days`" size="sm" />
                  </td>
                  <td class="px-4 py-3 text-sm text-ink-gray-6">{{ po.status }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="text-center py-6 text-sm text-ink-gray-6">No pending purchase orders</div>
        </div>
      </div>

      <!-- Tab 4: Price Intelligence -->
      <div v-if="activeTab === 'pricing'" class="space-y-6">
        <!-- Summary -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KpiCard
            label="Items Analyzed"
            :value="priceData.items_analyzed"
            sublabel="Stock items purchased in period"
            variant="tile"
            :loading="loading && !hasData"
          />
          <KpiCard
            label="Items with Price Increases"
            :value="priceData.price_increases_count"
            sublabel="Last price over 5% above average"
            variant="tile"
            :loading="loading && !hasData"
          />
          <KpiCard
            label="Potential Savings"
            :amount="priceData.total_potential_savings"
            :currency="baseCurrency"
            variant="tile"
            :loading="loading && !hasData"
          />
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Price Increases -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="Items Priced Above Average" hint="Per stock UOM, select an item for its purchases" :level="3" />
            <div class="mt-4 space-y-3" v-if="priceData.price_increases?.length">
              <div v-for="item in priceData.price_increases?.slice(0, 8)" :key="item.item_code"
                   class="p-3 bg-surface-gray-1 rounded-lg border border-outline-gray-1 cursor-pointer hover:bg-surface-gray-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 motion-reduce:transition-none"
                   role="button"
                   tabindex="0"
                   @click="openItemPurchases(item)"
                   @keydown.enter.prevent="openItemPurchases(item)"
                   @keydown.space.prevent="openItemPurchases(item)">
                <div class="flex justify-between items-start">
                  <div>
                    <div class="font-medium text-ink-gray-9">{{ item.item_name || item.item_code }}</div>
                    <div class="text-sm text-ink-gray-6">{{ item.item_group }}</div>
                  </div>
                  <div class="text-right">
                    <Badge v-bind="severityBadge('high')" :label="`+${formatPercent(item.price_variance_pct)}`" size="sm" />
                    <div class="text-xs text-ink-gray-6 mt-1">vs avg</div>
                  </div>
                </div>
                <div class="mt-2 flex gap-4 text-sm text-ink-gray-6">
                  <span>Last: {{ formatCurrency(item.last_rate) }}</span>
                  <span>Avg: {{ formatCurrency(item.avg_rate) }}</span>
                  <span>Min: {{ formatCurrency(item.min_rate) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-sm text-ink-gray-6">No price increases found</div>
          </div>

          <!-- Volatile Items -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="High Price Variance Items" hint="Per stock UOM, select an item for its purchases" :level="3" />
            <div class="mt-4 space-y-3" v-if="priceData.volatile_items?.length">
              <div v-for="item in priceData.volatile_items?.slice(0, 8)" :key="item.item_code"
                   class="p-3 bg-surface-gray-1 rounded-lg border border-outline-gray-1 cursor-pointer hover:bg-surface-gray-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 motion-reduce:transition-none"
                   role="button"
                   tabindex="0"
                   @click="openItemPurchases(item)"
                   @keydown.enter.prevent="openItemPurchases(item)"
                   @keydown.space.prevent="openItemPurchases(item)">
                <div class="flex justify-between items-start">
                  <div>
                    <div class="font-medium text-ink-gray-9">{{ item.item_name || item.item_code }}</div>
                    <div class="text-sm text-ink-gray-6">{{ formatCount(item.purchase_count) }} purchases</div>
                  </div>
                  <div class="text-right">
                    <Badge v-bind="severityBadge('medium')" :label="`${formatPercent(item.price_range_pct)} variance`" size="sm" />
                  </div>
                </div>
                <div class="mt-2 flex gap-4 text-sm text-ink-gray-6">
                  <span>Min: {{ formatCurrency(item.min_rate) }}</span>
                  <span>Max: {{ formatCurrency(item.max_rate) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-sm text-ink-gray-6">No high-variance items found</div>
          </div>
        </div>

        <!-- Price Variance Table -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" title="Item Price Analysis" hint="Per stock UOM, select an item for its purchases" :level="3" />
          <div class="mt-4 overflow-x-auto" v-if="priceData.price_variance_items?.length">
            <table class="min-w-full">
              <thead>
                <tr class="bg-surface-gray-1">
                  <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Item</th>
                  <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Category</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Purchases</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Avg Rate</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Last Rate</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Variance</th>
                  <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Savings</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-outline-gray-1">
                <tr v-for="item in priceData.price_variance_items" :key="item.item_code"
                    class="cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
                    @click="openItemPurchases(item)">
                  <td class="px-4 py-3">
                    <button type="button" :class="LINK_BUTTON_CLASS">{{ item.item_name || item.item_code }}</button>
                  </td>
                  <td class="px-4 py-3 text-sm text-ink-gray-6">{{ item.item_group }}</td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ formatCount(item.purchase_count) }}</td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-9">{{ formatCurrency(item.avg_rate) }}</td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-9">{{ formatCurrency(item.last_rate) }}</td>
                  <td class="px-4 py-3 text-right">
                    <span :class="deltaInk(item.price_variance_pct, { higherIsBetter: false })" class="font-medium">
                      {{ deltaGlyph(item.price_variance_pct) }}{{ formatAbsPercent(item.price_variance_pct) }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-9 font-medium">
                    {{ formatCurrency(item.potential_savings) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="text-center py-6 text-sm text-ink-gray-6">No price variance data available</div>
        </div>
      </div>

      <!-- Tab 5: Risk Analysis -->
      <div v-if="activeTab === 'risks'" class="space-y-6">
        <!-- Risk Score Card -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <div class="flex items-center justify-between">
            <div>
              <SectionHeader variant="caption" title="Procurement Risk Score" hint="Lower is better" :level="3" />
              <p class="text-sm text-ink-gray-6 mt-1">Based on concentration, single-source, and overdue payment risks.</p>
            </div>
            <div class="text-center">
              <div class="text-5xl font-bold text-ink-gray-9">
                {{ formatCount(riskData.risk_score) }}
              </div>
              <Badge v-if="hasRiskScore" v-bind="severityBadge(riskSeverity)"
                     :label="getRiskLabel(riskData.risk_score) ?? ''" size="sm" class="mt-1" />
            </div>
          </div>
          <div class="mt-4 bg-surface-gray-2 rounded-full h-4 overflow-hidden"
               role="img"
               :aria-label="severityAria('Procurement Risk', riskSeverity, riskData.risk_score)">
            <div
              class="h-full rounded-full motion-reduce:transition-none transition-all"
              :class="severityFill(riskSeverity)"
              :style="{ width: `${riskData.risk_score ?? 0}%` }"
            ></div>
          </div>

          <!-- Components: text carries the value, the bar is decorative. -->
          <ul class="mt-6 space-y-3">
            <li v-for="comp in riskComponentRows" :key="comp.key">
              <div class="flex items-center justify-between text-sm">
                <span class="text-ink-gray-7">{{ comp.label }}</span>
                <span class="font-medium text-ink-gray-9">{{ formatCount(comp.value, { decimals: 1 }) }} / {{ comp.max }}</span>
              </div>
              <div class="mt-1 bg-surface-gray-2 rounded-full h-2 overflow-hidden" aria-hidden="true">
                <div class="bg-surface-gray-5 h-full rounded-full" :style="{ width: `${comp.pct}%` }"></div>
              </div>
            </li>
          </ul>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Supplier Concentration -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="Supplier Concentration Risk" hint="Share of period spend" :level="3" />
            <div class="mt-4 space-y-3" v-if="riskData.supplier_concentration?.length">
              <div v-for="sup in riskData.supplier_concentration" :key="sup.supplier"
                   class="flex items-center gap-3 p-3 rounded-lg border border-outline-gray-1">
                <div class="flex-1">
                  <div class="font-medium text-ink-gray-9">{{ supplierLabel(sup) }}</div>
                  <div class="text-sm text-ink-gray-6">{{ formatCurrency(sup.spend) }} spend</div>
                </div>
                <div class="text-right">
                  <div class="text-lg font-bold text-ink-gray-9">{{ formatPercent(sup.concentration_pct) }}</div>
                  <Badge v-bind="severityBadge(prioritySeverity(sup.risk_level))"
                         :label="sup.risk_level ?? ''" size="sm" />
                </div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-sm text-ink-gray-6">No supplier concentration data</div>
          </div>

          <!-- Single Source Items -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="Single Source Items" hint="Select an item for its purchases" :level="3" />
            <p class="text-sm text-ink-gray-6 mt-1 mb-4">
              {{ formatCount(riskData.single_source_count) }} items with only one supplier
              ({{ formatCurrency(riskData.single_source_value) }} spend in period)
            </p>
            <div class="space-y-2 max-h-64 overflow-auto" v-if="riskData.single_source_items?.length">
              <div v-for="item in riskData.single_source_items?.slice(0, 10)" :key="item.item_code"
                   class="flex items-center justify-between p-2 bg-surface-gray-1 rounded cursor-pointer hover:bg-surface-gray-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 motion-reduce:transition-none"
                   role="button"
                   tabindex="0"
                   @click="openItemPurchases(item)"
                   @keydown.enter.prevent="openItemPurchases(item)"
                   @keydown.space.prevent="openItemPurchases(item)">
                <div>
                  <div class="font-medium text-ink-gray-9 text-sm">{{ item.item_name || item.item_code }}</div>
                  <div class="text-xs text-ink-gray-6">{{ item.only_supplier }}</div>
                </div>
                <div class="text-sm font-medium text-ink-gray-9">{{ formatCurrency(item.total_spend) }}</div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-sm text-ink-gray-6">No single-source items found</div>
          </div>
        </div>

        <!-- Payment Exposure -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" :title="`Payment Exposure (${formatCurrency(riskData.total_outstanding)} outstanding)`" hint="Current" :level="3" />
          <div class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 class="font-medium text-ink-gray-7 mb-3">Outstanding by Supplier</h4>
              <div class="space-y-2" v-if="riskData.payment_exposure?.length">
                <div v-for="pay in riskData.payment_exposure?.slice(0, 8)" :key="pay.supplier"
                     class="flex items-center justify-between p-2 bg-surface-gray-1 rounded">
                  <span class="text-sm text-ink-gray-9">{{ supplierLabel(pay) }}</span>
                  <span class="text-sm font-medium text-ink-gray-9">{{ formatCurrency(pay.outstanding) }}</span>
                </div>
              </div>
              <div v-else class="text-center py-6 text-sm text-ink-gray-6">No outstanding payments</div>
            </div>
            <div>
              <h4 class="font-medium text-ink-gray-7 mb-3">
                <button type="button" :class="LINK_BUTTON_CLASS" @click="openOverdueInvoices">
                  Overdue Invoices ({{ formatCount(riskData.overdue_count) }})
                </button>
              </h4>
              <div class="space-y-2 max-h-48 overflow-auto" v-if="riskData.overdue_invoices?.length">
                <div v-for="inv in riskData.overdue_invoices?.slice(0, 8)" :key="inv.name"
                     class="flex items-center justify-between gap-3 p-2 bg-surface-gray-1 rounded">
                  <div class="min-w-0">
                    <button type="button" :class="LINK_BUTTON_CLASS" class="text-sm" @click="openOverdueInvoices">
                      {{ inv.name }}
                    </button>
                    <div class="text-xs text-ink-gray-6">{{ inv.supplier }}</div>
                    <button type="button" class="text-xs text-ink-gray-6 underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
                            :aria-label="`Open purchase invoice ${inv.name}`"
                            @click="openDocument('Purchase Invoice', inv.name)">
                      Open document
                    </button>
                  </div>
                  <div class="text-right shrink-0">
                    <div class="text-sm font-medium text-ink-gray-9">{{ formatCurrency(inv.outstanding_amount) }}</div>
                    <Badge v-bind="severityBadge(scoreSeverity(inv.days_overdue, { good: 0, warn: 30, higherIsBetter: false }))"
                           :label="`${formatCount(inv.days_overdue)}d overdue`" size="sm" />
                  </div>
                </div>
              </div>
              <div v-else class="text-center py-6 text-sm text-ink-gray-6">No overdue invoices</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 6: Forecasts & Planning -->
      <div v-if="activeTab === 'forecasts'" class="space-y-6">
        <!-- Forecast Summary -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KpiCard
            label="Avg Monthly Spend"
            :amount="forecastData.avg_monthly_spend"
            :currency="baseCurrency"
            sublabel="Last 6 complete months"
            variant="tile"
            :loading="loading && !hasData"
          />
          <KpiCard
            label="Trend Direction"
            :value="trendLabel"
            :sublabel="forecastData.trend_amount ? `${formatCurrency(forecastData.trend_amount)}/month` : undefined"
            variant="tile"
            :loading="loading && !hasData"
          />
          <KpiCard
            label="Data Points"
            :value="completeMonthCount"
            unit=" months"
            sublabel="Complete months in fit"
            variant="tile"
            :loading="loading && !hasData"
          />
        </div>

        <div v-if="forecastData.status === 'insufficient_data'" class="bg-surface-gray-1 border border-outline-gray-2 rounded-lg p-4">
          <p class="text-ink-gray-7">{{ forecastData.message }}</p>
        </div>

        <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Spend Forecast -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="3-Month Spend Forecast" hint="Linear trend" :level="3" />
            <div class="mt-4 space-y-4" v-if="forecastData.forecasts?.length">
              <div v-for="forecast in forecastData.forecasts" :key="forecast.period"
                   class="flex items-center gap-4 p-4 bg-surface-gray-1 rounded-lg">
                <div class="flex-1">
                  <div class="font-medium text-ink-gray-9">{{ formatPeriod(forecast.period) }}</div>
                </div>
                <div class="text-xl font-bold text-ink-gray-9">
                  {{ formatCurrency(forecast.predicted_spend) }}
                </div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-sm text-ink-gray-6">No forecast data available</div>
          </div>

          <!-- Category Forecast -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="Category run-rate (3M, flat)" hint="Trailing 12-month average x 3" :level="3" />
            <div class="mt-4 space-y-3" v-if="forecastData.category_forecast?.length">
              <div v-for="cat in forecastData.category_forecast" :key="cat.category"
                   class="flex items-center justify-between p-3 bg-surface-gray-1 rounded-lg">
                <div>
                  <div class="font-medium text-ink-gray-9">{{ cat.category }}</div>
                  <div class="text-sm text-ink-gray-6">Avg: {{ formatCurrency(cat.avg_monthly_spend) }}/mo</div>
                </div>
                <div class="text-lg font-bold text-ink-gray-9">
                  {{ formatCurrency(cat.forecast_3m) }}
                </div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-sm text-ink-gray-6">No category forecast data</div>
          </div>
        </div>

        <!-- Historical Trend + forecast -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" title="Monthly Spend History and Forecast" hint="Last 24 months, dashed = forecast, not affected by the period filter" :level="3" />
          <IntelligenceChart v-if="forecastData.historical?.length" class="mt-4 h-48 sm:h-56 lg:h-64" :config="historicalSpendConfig" />
          <div v-else class="h-48 flex items-center justify-center text-ink-gray-6">
            No historical data available
          </div>
          <table v-if="forecastData.historical?.length" class="sr-only">
            <caption>Monthly spend history and forecast</caption>
            <thead>
              <tr>
                <th scope="col">Month</th>
                <th scope="col">Actual spend</th>
                <th scope="col">Forecast spend</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in historyChartData" :key="row.period">
                <th scope="row">{{ row.period }}</th>
                <td>{{ formatCurrency(row.Actual) }}</td>
                <td>{{ formatCurrency(row.Forecast) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    </IntelligenceDashboardShell>

    <!-- AI Chat Button -->
    <DashboardChatButton
      dashboard-type="Procurement"
      :dashboard-context="chatContext"
      @navigate-dashboard="handleDashboardRedirect"
    />

    <IntelligenceDrillDown
      v-model:show="drillDown.show.value"
      :title="drillDown.title.value"
      :columns="drillDown.columns.value"
      :rows="drillDown.rows.value"
      :loading="drillDown.loading.value"
      :error="drillDown.error.value"
      :is-permission-error="drillDown.isPermissionError.value"
      :total="drillDown.total.value"
      :page="drillDown.page.value"
      @next-page="drillDown.nextPage()"
      @prev-page="drillDown.prevPage()"
      @close="drillDown.close()"
      @retry="drillDown.retry()"
    />
  </div>
</template>

<script setup lang="ts">
import IntelligenceChart from '../intelligence/components/IntelligenceChart.vue'
defineOptions({ name: 'ProcurementIntelligence' })
import { ref, computed } from 'vue'
import { Button, Badge, Tabs } from 'frappe-ui'
import { RefreshCcw } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import {
  scoreSeverity, severityBadge, severityFill, severityAria, severityTint,
  deltaInk, deltaGlyph, prioritySeverity, type Severity,
} from '../utils/status'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'
import IntelligenceDashboardShell from '../intelligence/components/IntelligenceDashboardShell.vue'
import { useIntelligenceDashboard } from '../intelligence/composables/useIntelligenceDashboard'
import KpiCard from '../intelligence/components/KpiCard.vue'
import SectionHeader from '../intelligence/components/SectionHeader.vue'
import { chartPalette, themeColor } from '../utils/chartTheme'
import { formatCount, formatDate, formatMoney, formatPercent, NO_VALUE } from '../utils/format'
import { formatPeriod } from '../components/financial/format'


/** One calendar month of spend; `partial` for a month cut by the window start or still in progress. */
interface SpendMonthRow { period: string; spend: number; partial?: boolean }
/** Spend by category row. */
interface CategoryRow { category: string; spend?: number; pct_of_total: number }
/** Top supplier by spend row. */
interface TopSupplierRow {
  supplier: string
  supplier_name?: string
  invoice_count?: number
  spend: number
  pct_of_total: number
}
/** Supplier performance scorecard row. Every rate is null when the supplier has no data for it. */
interface SupplierPerfRow {
  supplier: string
  supplier_name?: string
  on_time_rate?: number | null
  quality_rate?: number | null
  avg_lead_time?: number | null
  po_count?: number
  total_value?: number
  overall_score?: number | null
}
/** Purchase order status summary row. */
interface POStatusRow { status: string; count: number; value: number }
/** Monthly PO trend row. */
interface POMonthRow { period: string; po_value: number; po_count?: number; partial?: boolean }
/** Pending purchase order row. */
interface PendingPORow {
  name: string
  supplier?: string
  transaction_date?: string
  grand_total?: number
  days_pending?: number
  status?: string
}
/** Item price variance / analysis row. */
interface PriceVarianceItem {
  item_code: string
  item_name?: string
  item_group?: string
  purchase_count?: number
  avg_rate?: number
  last_rate?: number
  min_rate?: number
  max_rate?: number
  price_variance_pct?: number
  price_range_pct?: number
  potential_savings?: number
}
/** Supplier concentration risk row. */
interface SupplierConcentrationRow {
  supplier: string
  supplier_name?: string
  spend?: number
  concentration_pct?: number
  risk_level?: string
}
/** Single-source item row. */
interface SingleSourceItem { item_code: string; item_name?: string; only_supplier?: string; total_spend?: number }
/** Payment exposure by supplier row. */
interface PaymentExposureRow { supplier: string; supplier_name?: string; outstanding?: number }
/** Overdue invoice row. */
interface OverdueInvoiceRow { name: string; supplier?: string; outstanding_amount?: number; days_overdue?: number }
/** Spend forecast row. */
interface ForecastRow { period: string; predicted_spend?: number }
/** Category-level run-rate row. */
interface CategoryForecastRow { category: string; avg_monthly_spend?: number; forecast_3m?: number }

/** Typed spend overview sub-section from procurement_intelligence endpoint. */
interface SpendData {
  total_spend?: number | null
  /** % change vs the preceding window of equal length; null when there is no comparable base. */
  prior_period_growth?: number | null
  invoice_count?: number
  supplier_count?: number
  monthly_trend?: SpendMonthRow[]
  by_category?: CategoryRow[]
  top_suppliers?: TopSupplierRow[]
}
/** Typed supplier performance sub-section. */
interface SupplierData {
  avg_lead_time?: number | null
  avg_on_time_rate?: number | null
  avg_score?: number | null
  avg_quality_rate?: number | null
  quality_status?: 'success' | 'not_implemented' | string
  top_performers?: SupplierPerfRow[]
  bottom_performers?: SupplierPerfRow[]
  all_suppliers?: SupplierPerfRow[]
}
/** Typed purchase analytics sub-section. */
interface PurchaseData {
  avg_mr_to_po_days?: number | null
  avg_po_to_grn_days?: number | null
  avg_grn_to_invoice_days?: number | null
  total_po_count?: number
  overdue_po_count?: number
  pending_count?: number
  pending_value?: number
  po_status_summary?: POStatusRow[]
  monthly_trend?: POMonthRow[]
  pending_pos?: PendingPORow[]
}
/** Typed price intelligence sub-section. */
interface PriceData {
  items_analyzed?: number
  price_increases_count?: number
  total_potential_savings?: number
  price_increases?: PriceVarianceItem[]
  volatile_items?: PriceVarianceItem[]
  price_variance_items?: PriceVarianceItem[]
}
/** The three bounded parts of the risk score (max 35 / 35 / 30). */
interface RiskComponents {
  concentration?: number | null
  single_source?: number | null
  overdue?: number | null
}
/** Typed procurement risk analysis sub-section. */
interface ProcurementRiskData {
  risk_score?: number | null
  risk_components?: RiskComponents
  single_source_count?: number
  single_source_value?: number
  total_outstanding?: number
  overdue_count?: number
  supplier_concentration?: SupplierConcentrationRow[]
  single_source_items?: SingleSourceItem[]
  payment_exposure?: PaymentExposureRow[]
  overdue_invoices?: OverdueInvoiceRow[]
}
/** Typed forecasts & planning sub-section. */
interface ForecastData {
  avg_monthly_spend?: number | null
  trend_direction?: string
  trend_amount?: number
  status?: string
  message?: string
  forecasts?: ForecastRow[]
  category_forecast?: CategoryForecastRow[]
  historical?: SpendMonthRow[]
}
const router = useRouter()

const PROC_ENDPOINT = 'insights.api.ml.procurement.get_procurement_detail'
const drillDown = useDrillDown()

const dateFilter = ref('12m')

const tabIndex = ref(0)

const tabs = [
  { label: 'Spend Overview', value: 'spend' },
  { label: 'Supplier Performance', value: 'suppliers' },
  { label: 'Purchase Analytics', value: 'analytics' },
  { label: 'Price Intelligence', value: 'pricing' },
  { label: 'Risk Analysis', value: 'risks' },
  { label: 'Forecasts & Planning', value: 'forecasts' },
]
// Risk Score KPI card (above) navigates here on click -- it's a blended
// 0-100 composite (concentration/single-source/payment risk), not a single
// countable metric, so a tab jump reads better than a record-list
// drill-down (TODOS.md, 2026-08-17 drill-down/coverage audit). Looked up
// by value rather than hardcoded so a future tab reorder can't silently
// point the click at the wrong tab.
const RISKS_TAB_INDEX = tabs.findIndex(t => t.value === 'risks')

const tabDefs = tabs.map(t => ({ label: t.label }))
const activeTab = computed(() => tabs[tabIndex.value]?.value ?? 'spend')

/** Typed payload from procurement_intelligence endpoint. */
interface ProcurementData {
  spend_overview?: SpendData
  supplier_performance?: SupplierData
  purchase_analytics?: PurchaseData
  price_intelligence?: PriceData
  risk_analysis?: ProcurementRiskData
  forecasts?: ForecastData
  generated_at?: string
  base_currency?: string
  date_filter?: string
  /** `start` is null when the window is all history. */
  period?: { start: string | null; end: string }
}

const {
  data: procurementData,
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
} = useIntelligenceDashboard<ProcurementData>({
  url: 'insights.api.ml.procurement_intelligence',
  params: computed(() => ({ date_filter: dateFilter.value })),
  cache: 'procurement-intelligence',
})

// Data sub-sections are derived from the unwrapped payload; no separate refs.
const spendData = computed(() => procurementData.value?.spend_overview ?? ({} as SpendData))
const supplierData = computed(() => procurementData.value?.supplier_performance ?? ({} as SupplierData))
const purchaseData = computed(() => procurementData.value?.purchase_analytics ?? ({} as PurchaseData))
// Surface the backend's explicit "no quality data on this site" signal so
// the dashboard can label the Quality tile and supplier rows accordingly
// rather than rendering a misleading "100%" everywhere.
const qualityStatus = computed(() => supplierData.value.quality_status ?? 'success')
const priceData = computed(() => procurementData.value?.price_intelligence ?? ({} as PriceData))
const riskData = computed(() => procurementData.value?.risk_analysis ?? ({} as ProcurementRiskData))
const forecastData = computed(() => procurementData.value?.forecasts ?? ({} as ForecastData))
const baseCurrency = computed(() => procurementData.value?.base_currency)
const lastUpdated = computed(() => procurementData.value?.generated_at ?? null)

const windowLabel = computed(() => {
  const period = procurementData.value?.period
  if (!period) return null
  return `${period.start ? formatDate(period.start) : 'All history'} \u2013 ${formatDate(period.end)}`
})

// Score thresholds shared by the KPI strip and the table cells so both tint alike.
const RATE_THRESHOLDS = { good: 90, warn: 70 } as const
const SCORE_THRESHOLDS = { good: 80, warn: 60 } as const
const RISK_THRESHOLDS = { good: 30, warn: 60, higherIsBetter: false } as const

const onTimeSeverity = computed(() => scoreSeverity(supplierData.value.avg_on_time_rate, RATE_THRESHOLDS))
const riskSeverity = computed(() => scoreSeverity(riskData.value.risk_score, RISK_THRESHOLDS))
const hasRiskScore = computed(() => Number.isFinite(riskData.value.risk_score))

/** Tint for a rate cell; no tint when the supplier has no data for it. */
const rateTint = (rate: number | null | undefined) =>
  Number.isFinite(rate) ? severityTint(scoreSeverity(rate, RATE_THRESHOLDS)) : ''

// Formatting helpers
const formatCurrency = (value: number | null | undefined) => formatMoney(value, baseCurrency.value)
const scoreLabel = (value: number | null | undefined) => formatCount(value, { decimals: 1 })
const formatDays = (value: number | null | undefined) =>
  Number.isFinite(value) ? `${formatCount(value, { decimals: 1 })} days` : NO_VALUE
const formatAbsPercent = (value: number | null | undefined) =>
  Number.isFinite(value) ? formatPercent(Math.abs(value as number)) : NO_VALUE
const supplierLabel = (s: { supplier: string; supplier_name?: string }) => s.supplier_name || s.supplier
/** Month label; a window-edge or in-progress month is flagged so a low bar is not read as a drop. */
const monthLabel = (m: { period: string; partial?: boolean }) =>
  m.partial ? `${formatPeriod(m.period)} (partial)` : formatPeriod(m.period)

const pendingSublabel = computed(() =>
  Number.isFinite(purchaseData.value.pending_value)
    ? `${formatCurrency(purchaseData.value.pending_value)} open value`
    : undefined,
)

// Domain label helpers (non-colour)
const getRiskLabel = (score: number | null | undefined) => {
  if (score === null || score === undefined || Number.isNaN(score)) return undefined
  if (score <= RISK_THRESHOLDS.good) return 'Low Risk'
  if (score <= RISK_THRESHOLDS.warn) return 'Medium Risk'
  return 'High Risk'
}

const RISK_COMPONENTS = [
  { key: 'concentration', label: 'Supplier concentration', max: 35 },
  { key: 'single_source', label: 'Single-source spend', max: 35 },
  { key: 'overdue', label: 'Overdue payables', max: 30 },
] as const

const riskComponentRows = computed(() =>
  RISK_COMPONENTS.map(c => {
    const value = riskData.value.risk_components?.[c.key] ?? null
    return { ...c, value, pct: Math.min(100, Math.max(0, ((value ?? 0) / c.max) * 100)) }
  }),
)

const trendLabel = computed(() => {
  const dir = forecastData.value.trend_direction
  if (dir === 'up') return 'Increasing'
  if (dir === 'down') return 'Decreasing'
  return null
})
// The in-progress month is shown but excluded from the fit; count what the fit used.
const completeMonthCount = computed(() => {
  const rows = forecastData.value.historical
  return rows ? rows.filter(m => !m.partial).length : null
})

// Chart configs — ECharts cannot resolve CSS custom properties from canvas; use themeColor().
const monthlySpendConfig = computed(() => ({
  title: '',
  data: (spendData.value.monthly_trend ?? []).map(m => ({
    period: monthLabel(m),
    Spend: m.spend,
  })),
  xAxis: { key: 'period', type: 'category' as const },
  yAxis: { title: baseCurrency.value ?? '', yMin: 0 },
  series: [{ name: 'Spend', type: 'area' as const, color: themeColor('--app-info-fill') }],
}))

const spendByCategoryConfig = computed(() => ({
  title: '',
  data: (spendData.value.by_category ?? []).slice(0, 10).map(c => ({
    category: c.category,
    'Pct of total': c.pct_of_total,
  })),
  xAxis: { key: 'category', type: 'category' as const },
  yAxis: { title: '% of spend', yMin: 0 },
  swapXY: true,
  series: [{ name: 'Pct of total', type: 'bar' as const, color: themeColor('--app-info-fill') }],
}))

const monthlyPOConfig = computed(() => ({
  title: '',
  data: (purchaseData.value.monthly_trend ?? []).map(m => ({
    period: monthLabel(m),
    'PO Value': m.po_value,
  })),
  xAxis: { key: 'period', type: 'category' as const },
  yAxis: { title: baseCurrency.value ?? '', yMin: 0 },
  series: [{ name: 'PO Value', type: 'bar' as const, color: themeColor('--app-info-fill') }],
}))

/** Actual history then forecast months, one row per month; feeds both the chart and its sr-only table. */
const historyChartData = computed(() => {
  const historical = forecastData.value.historical ?? []
  const forecasts = forecastData.value.forecasts ?? []
  const rows: { period: string; Actual: number | null; Forecast: number | null }[] = historical.map(m => ({
    period: monthLabel(m),
    Actual: m.spend,
    Forecast: null,
  }))
  // Join the dashed line to the last complete month; an in-progress month is not a fit anchor.
  const lastRow = rows[rows.length - 1]
  const lastHistorical = historical[historical.length - 1]
  if (forecasts.length && lastRow && lastHistorical && !lastHistorical.partial) {
    lastRow.Forecast = lastHistorical.spend
  }
  for (const f of forecasts) {
    rows.push({ period: formatPeriod(f.period), Actual: null, Forecast: f.predicted_spend ?? null })
  }
  return rows
})

const historicalSpendConfig = computed(() => {
  const palette = chartPalette(2)
  return {
    title: '',
    data: historyChartData.value,
    xAxis: { key: 'period', type: 'category' as const },
    yAxis: { title: baseCurrency.value ?? '', yMin: 0 },
    series: [
      { name: 'Actual', type: 'area' as const, color: palette[0] },
      { name: 'Forecast', type: 'line' as const, color: palette[1], lineType: 'dashed' as const, showDataPoints: true },
    ],
  }
})

function poStatusSeverity(status: string): Severity {
  if (status === 'Cancelled') return 'critical'
  if (status === 'Completed' || status === 'Closed' || status === 'Draft') return 'none'
  if (status === 'To Receive and Bill') return 'low'
  return 'medium'
}

// Shared look for keyboard-operable non-button rows (role="button" + Enter/Space in the template)
// and for text buttons inside table cells.
const ROW_BUTTON_CLASS =
  'flex items-center gap-3 p-3 bg-surface-gray-1 rounded-lg cursor-pointer hover:bg-surface-gray-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 motion-reduce:transition-none'
const LINK_BUTTON_CLASS =
  'text-left font-medium text-ink-gray-9 hover:underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3'

// L3 evidence drill-downs. Windowed metrics carry the active date filter.
function openSupplierPOs(sup: { supplier: string; supplier_name?: string }) {
  drillDown.open(PROC_ENDPOINT, `${supplierLabel(sup)} Purchase Orders`, {
    metric: 'supplier_performance',
    supplier: sup.supplier,
    date_filter: dateFilter.value,
  })
}
function openSupplierInvoices(sup: { supplier: string; supplier_name?: string }) {
  drillDown.open(PROC_ENDPOINT, `${supplierLabel(sup)} Invoices`, {
    metric: 'supplier_invoices',
    supplier: sup.supplier,
    date_filter: dateFilter.value,
  })
}
function openItemPurchases(item: { item_code: string; item_name?: string }) {
  drillDown.open(PROC_ENDPOINT, `${item.item_name || item.item_code} Purchases`, {
    metric: 'item_purchases',
    item_code: item.item_code,
    date_filter: dateFilter.value,
  })
}
function openOverdueInvoices() {
  drillDown.open(PROC_ENDPOINT, 'Overdue Purchase Invoices', { metric: 'overdue_invoices' })
}

const openDocument = (doctype: string, name: string) => {
  window.open(`/app/${doctype.toLowerCase().replace(/ /g, '-')}/${encodeURIComponent(name)}`, '_blank', 'noopener')
}

// Chat context for AI insights: headline summary plus the section on screen, not the whole payload.
const summary = computed(() => ({
  totalSpend: spendData.value.total_spend,
  priorPeriodGrowth: spendData.value.prior_period_growth,
  supplierCount: spendData.value.supplier_count,
  avgLeadTime: supplierData.value.avg_lead_time,
  avgOnTimeRate: supplierData.value.avg_on_time_rate,
  pendingCount: purchaseData.value.pending_count,
  pendingValue: purchaseData.value.pending_value,
  riskScore: riskData.value.risk_score,
  currency: baseCurrency.value,
}))

const activeSection = computed(() => {
  switch (activeTab.value) {
    case 'suppliers': return supplierData.value
    case 'analytics': return purchaseData.value
    case 'pricing': return priceData.value
    case 'risks': return riskData.value
    case 'forecasts': return forecastData.value
    default: return spendData.value
  }
})

const chatContext = computed(() => ({
  summary: summary.value,
  activeTab: activeTab.value,
  activeSection: activeSection.value,
  dateFilter: dateFilter.value,
  period: procurementData.value?.period ?? null,
  lastUpdated: lastUpdated.value,
}))

// Handle navigation to other dashboards from chat suggestions
function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    'Sales': '/sales-intelligence',
    'Risk': '/risk-intelligence',
    'Inventory': '/inventory-intelligence',
    'Financial': '/financial-intelligence',
    'Customer': '/customer-intelligence',
    'Procurement': '/procurement-intelligence',
  }
  if (routes[target]) {
    router.push(routes[target])
  }
}
</script>
