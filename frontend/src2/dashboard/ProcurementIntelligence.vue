<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <header class="bg-surface-white border-b border-outline-gray-1 px-6 py-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-ink-gray-9">Procurement Intelligence</h1>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <span v-if="lastUpdated" class="text-sm text-ink-gray-6">
          Updated: {{ formatDate(lastUpdated) }}
        </span>
        <Button
          variant="solid"
          @click="reload"
          :loading="refreshing"
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
      subject="procurement data"
      permission-hint="Ask an administrator for procurement read access."
      @retry="retry"
    >
    <!-- Summary Cards -->
    <div class="p-6 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <KpiCard
        label="Total Spend (12M)"
        :value="formatCurrency(summary.totalSpend)"
        :delta="summary.yoyGrowth || undefined"
        :delta-higher-is-better="false"
        sublabel="YoY"
        :loading="loading && !hasData"
        :error="error ?? undefined"
      />
      <KpiCard
        label="Active Suppliers"
        :value="String(summary.supplierCount)"
        sublabel="In last 12 months"
        :loading="loading && !hasData"
        :error="error ?? undefined"
      />
      <KpiCard
        label="Avg Lead Time"
        :value="`${summary.avgLeadTime} days`"
        sublabel="Order to delivery"
        :loading="loading && !hasData"
        :error="error ?? undefined"
      />
      <KpiCard
        label="On-Time Delivery"
        :value="`${summary.avgOnTimeRate}%`"
        :severity="scoreSeverity(summary.avgOnTimeRate, { good: 90, warn: 70, higherIsBetter: true })"
        :loading="loading && !hasData"
        :error="error ?? undefined"
      />
      <KpiCard
        label="Pending POs"
        :value="String(summary.pendingCount)"
        :sublabel="formatCurrency(summary.pendingValue)"
        :clickable="true"
        :loading="loading && !hasData"
        :error="error ?? undefined"
        @click="drillDown.open(PROC_ENDPOINT, 'Pending Purchase Orders', { metric: 'pending_pos' })"
      />
      <KpiCard
        label="Risk Score"
        :value="`${summary.riskScore}/100`"
        :sublabel="getRiskLabel(summary.riskScore)"
        :severity="scoreSeverity(summary.riskScore, { good: 30, warn: 60, higherIsBetter: false })"
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
            <SectionHeader variant="caption" title="Monthly Spend Trend" :level="3" />
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
                  <th scope="row">{{ formatPeriod(month.period) }}</th>
                  <td>{{ formatCurrency(month.spend) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Spend by Category -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="Spend by Category" :level="3" />
            <IntelligenceChart v-if="spendData.by_category?.length" class="mt-4 h-48 sm:h-56 lg:h-64" :config="spendByCategoryConfig" />
            <div v-else class="h-48 flex items-center justify-center text-ink-gray-6">
              No category data available
            </div>
            <table v-if="spendData.by_category?.length" class="sr-only">
              <caption>Spend by category as percent of total</caption>
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  <th scope="col">% of total</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="cat in spendData.by_category" :key="cat.category">
                  <th scope="row">{{ cat.category }}</th>
                  <td>{{ cat.pct_of_total }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Top Suppliers by Spend -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" title="Top Suppliers by Spend" :level="3" />
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
                <tr v-for="sup in spendData.top_suppliers" :key="sup.supplier">
                  <td class="px-4 py-3">
                    <div class="font-medium text-ink-gray-9">{{ sup.supplier_name || sup.supplier }}</div>
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ sup.invoice_count }}</td>
                  <td class="px-4 py-3 text-right text-sm font-medium text-ink-gray-9">
                    {{ formatCurrency(sup.spend) }}
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ sup.pct_of_total }}%</td>
                  <td class="px-4 py-3 w-32">
                    <div class="bg-surface-gray-2 rounded-full h-2 overflow-hidden">
                      <div
                        class="bg-surface-blue-3 h-full rounded-full"
                        :style="{ width: `${sup.pct_of_total}%` }"
                        role="img"
                        :aria-label="`${sup.pct_of_total}% of total spend`"
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
                   class="flex items-center gap-3 p-3 bg-surface-gray-1 rounded-lg cursor-pointer hover:bg-surface-gray-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 motion-reduce:transition-none"
                   tabindex="0"
                   @click="drillDown.open(PROC_ENDPOINT, (sup.supplier_name || sup.supplier) + ' Purchase Orders', { metric: 'supplier_performance', supplier: sup.supplier })"
                   @keydown.enter="drillDown.open(PROC_ENDPOINT, (sup.supplier_name || sup.supplier) + ' Purchase Orders', { metric: 'supplier_performance', supplier: sup.supplier })">
                <div class="w-8 h-8 bg-surface-gray-3 rounded-full flex items-center justify-center text-ink-gray-9 font-bold text-sm">
                  {{ idx + 1 }}
                </div>
                <div class="flex-1">
                  <div class="font-medium text-ink-gray-9">{{ sup.supplier_name || sup.supplier }}</div>
                  <div class="text-sm text-ink-gray-6">
                    On-time: {{ sup.on_time_rate }}% | Quality: {{ sup.quality_rate == null ? 'N/A' : sup.quality_rate + '%' }}
                  </div>
                </div>
                <div class="text-lg font-bold text-ink-gray-9">{{ sup.overall_score }}</div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-sm text-ink-gray-6">No supplier performance data</div>
          </div>

          <!-- Needs Improvement -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="Needs Improvement" :level="3" />
            <div class="mt-4 space-y-3" v-if="supplierData.bottom_performers?.length">
              <div v-for="sup in supplierData.bottom_performers?.slice(0, 5)" :key="sup.supplier"
                   class="flex items-center gap-3 p-3 bg-surface-gray-1 rounded-lg cursor-pointer hover:bg-surface-gray-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 motion-reduce:transition-none"
                   tabindex="0"
                   @click="drillDown.open(PROC_ENDPOINT, (sup.supplier_name || sup.supplier) + ' Purchase Orders', { metric: 'supplier_performance', supplier: sup.supplier })"
                   @keydown.enter="drillDown.open(PROC_ENDPOINT, (sup.supplier_name || sup.supplier) + ' Purchase Orders', { metric: 'supplier_performance', supplier: sup.supplier })">
                <div class="flex-1">
                  <div class="font-medium text-ink-gray-9">{{ sup.supplier_name || sup.supplier }}</div>
                  <div class="text-sm text-ink-gray-6">
                    On-time: {{ sup.on_time_rate }}% | Quality: {{ sup.quality_rate == null ? 'N/A' : sup.quality_rate + '%' }}
                  </div>
                </div>
                <div class="text-lg font-bold text-ink-gray-9">{{ sup.overall_score }}</div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-sm text-ink-gray-6">No underperforming suppliers</div>
          </div>
        </div>

        <!-- All Suppliers Table -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" title="All Supplier Scores" :level="3" />
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
                    tabindex="0"
                    @click="drillDown.open(PROC_ENDPOINT, (sup.supplier_name || sup.supplier) + ' Purchase Orders', { metric: 'supplier_performance', supplier: sup.supplier })"
                    @keydown.enter="drillDown.open(PROC_ENDPOINT, (sup.supplier_name || sup.supplier) + ' Purchase Orders', { metric: 'supplier_performance', supplier: sup.supplier })">
                  <td class="px-4 py-3 font-medium text-ink-gray-9">{{ sup.supplier_name || sup.supplier }}</td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ sup.po_count }}</td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-9">{{ formatCurrency(sup.total_value) }}</td>
                  <td class="px-4 py-3 text-right">
                    <span :class="deltaInk((sup.on_time_rate ?? 0) - 70, { higherIsBetter: true })" class="font-medium">
                      {{ sup.on_time_rate }}%
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right">
                    <span :class="sup.quality_rate == null ? 'text-ink-gray-6' : deltaInk((sup.quality_rate ?? 0) - 70, { higherIsBetter: true })" class="font-medium">
                      {{ sup.quality_rate == null ? 'N/A' : sup.quality_rate + '%' }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ sup.avg_lead_time }} days</td>
                  <td class="px-4 py-3 text-right">
                    <Badge v-bind="severityBadge(scoreSeverity(sup.overall_score, { good: 80, warn: 60, higherIsBetter: true }))"
                           :label="String(sup.overall_score)" size="sm" />
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
            sublabel="All confirmed orders"
            variant="tile"
            :clickable="true"
            :loading="loading && !hasData"
            @click="drillDown.open(PROC_ENDPOINT, 'Total Purchase Orders', { metric: 'total_pos' })"
          />
          <KpiCard
            label="Overdue POs"
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
            sublabel="Average processing time"
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
          <SectionHeader variant="caption" title="Purchase Order Status" :level="3" />
          <div class="mt-4 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4" v-if="purchaseData.po_status_summary?.length">
            <div v-for="status in purchaseData.po_status_summary" :key="status.status"
                 class="p-4 rounded-lg border border-outline-gray-1 bg-surface-white">
              <Badge v-bind="severityBadge(poStatusSeverity(status.status))"
                     :label="status.status" size="sm" class="mb-2" />
              <div class="text-xl font-bold text-ink-gray-9">{{ status.count }}</div>
              <div class="text-sm text-ink-gray-6">{{ formatCurrency(status.value) }}</div>
            </div>
          </div>
          <div v-else class="text-center py-6 text-sm text-ink-gray-6">No purchase order status data</div>
        </div>

        <!-- Monthly PO Trend -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" title="Monthly Purchase Order Trend" :level="3" />
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
                <th scope="row">{{ formatPeriod(month.period) }}</th>
                <td>{{ formatCurrency(month.po_value) }}</td>
                <td>{{ month.po_count }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pending POs -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" :title="`Pending Purchase Orders (${purchaseData.pending_count || 0})`" :level="3" />
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
                  <td class="px-4 py-3 font-medium text-ink-gray-9 cursor-pointer hover:underline"
                      @click="openDocument('Purchase Order', po.name)">
                    {{ po.name }}
                  </td>
                  <td class="px-4 py-3 text-sm text-ink-gray-9">{{ po.supplier }}</td>
                  <td class="px-4 py-3 text-sm text-ink-gray-6">{{ formatDate(po.transaction_date) }}</td>
                  <td class="px-4 py-3 text-right text-sm font-medium text-ink-gray-9">
                    {{ formatCurrency(po.grand_total) }}
                  </td>
                  <td class="px-4 py-3 text-right">
                    <Badge v-bind="severityBadge(scoreSeverity(po.days_pending, { good: 7, warn: 14, higherIsBetter: false }))"
                           :label="`${po.days_pending} days`" size="sm" />
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
            variant="tile"
            :loading="loading && !hasData"
          />
          <KpiCard
            label="Items with Price Increases"
            :value="priceData.price_increases?.length"
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
            <SectionHeader variant="caption" title="Recent Price Increases" :level="3" />
            <div class="mt-4 space-y-3" v-if="priceData.price_increases?.length">
              <div v-for="item in priceData.price_increases?.slice(0, 8)" :key="item.item_code"
                   class="p-3 bg-surface-gray-1 rounded-lg border border-outline-gray-1">
                <div class="flex justify-between items-start">
                  <div>
                    <div class="font-medium text-ink-gray-9">{{ item.item_name || item.item_code }}</div>
                    <div class="text-sm text-ink-gray-6">{{ item.item_group }}</div>
                  </div>
                  <div class="text-right">
                    <Badge v-bind="severityBadge('high')" :label="`+${item.price_variance_pct}%`" size="sm" />
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
            <SectionHeader variant="caption" title="High Price Variance Items" :level="3" />
            <div class="mt-4 space-y-3" v-if="priceData.volatile_items?.length">
              <div v-for="item in priceData.volatile_items?.slice(0, 8)" :key="item.item_code"
                   class="p-3 bg-surface-gray-1 rounded-lg border border-outline-gray-1">
                <div class="flex justify-between items-start">
                  <div>
                    <div class="font-medium text-ink-gray-9">{{ item.item_name || item.item_code }}</div>
                    <div class="text-sm text-ink-gray-6">{{ item.purchase_count }} purchases</div>
                  </div>
                  <div class="text-right">
                    <Badge v-bind="severityBadge('medium')" :label="`${item.price_range_pct}% variance`" size="sm" />
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
          <SectionHeader variant="caption" title="Item Price Analysis" :level="3" />
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
                <tr v-for="item in priceData.price_variance_items" :key="item.item_code">
                  <td class="px-4 py-3">
                    <div class="font-medium text-ink-gray-9">{{ item.item_name || item.item_code }}</div>
                  </td>
                  <td class="px-4 py-3 text-sm text-ink-gray-6">{{ item.item_group }}</td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ item.purchase_count }}</td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-9">{{ formatCurrency(item.avg_rate) }}</td>
                  <td class="px-4 py-3 text-right text-sm text-ink-gray-9">{{ formatCurrency(item.last_rate) }}</td>
                  <td class="px-4 py-3 text-right">
                    <span :class="deltaInk(item.price_variance_pct, { higherIsBetter: false })" class="font-medium">
                      {{ deltaGlyph(item.price_variance_pct) }}{{ Math.abs(item.price_variance_pct ?? 0) }}%
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
              <p class="text-sm text-ink-gray-6 mt-1">Based on concentration, single-source, and payment risks.</p>
            </div>
            <div class="text-center">
              <div class="text-5xl font-bold text-ink-gray-9">
                {{ riskData.risk_score || 0 }}
              </div>
              <Badge v-bind="severityBadge(scoreSeverity(riskData.risk_score, { good: 30, warn: 60, higherIsBetter: false }))"
                     :label="getRiskLabel(riskData.risk_score)" size="sm" class="mt-1" />
            </div>
          </div>
          <div class="mt-4 bg-surface-gray-2 rounded-full h-4 overflow-hidden"
               role="img"
               :aria-label="severityAria('Procurement Risk', scoreSeverity(riskData.risk_score, { good: 30, warn: 60, higherIsBetter: false }), riskData.risk_score)">
            <div
              class="h-full rounded-full motion-reduce:transition-none transition-all"
              :class="severityFill(scoreSeverity(riskData.risk_score, { good: 30, warn: 60, higherIsBetter: false }))"
              :style="{ width: `${riskData.risk_score}%` }"
            ></div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Supplier Concentration -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="Supplier Concentration Risk" :level="3" />
            <div class="mt-4 space-y-3" v-if="riskData.supplier_concentration?.length">
              <div v-for="sup in riskData.supplier_concentration" :key="sup.supplier"
                   class="flex items-center gap-3 p-3 rounded-lg border border-outline-gray-1">
                <div class="flex-1">
                  <div class="font-medium text-ink-gray-9">{{ sup.supplier_name || sup.supplier }}</div>
                  <div class="text-sm text-ink-gray-6">{{ formatCurrency(sup.spend) }} spend</div>
                </div>
                <div class="text-right">
                  <div class="text-lg font-bold text-ink-gray-9">{{ sup.concentration_pct }}%</div>
                  <Badge v-bind="severityBadge(prioritySeverity(sup.risk_level))"
                         :label="sup.risk_level" size="sm" />
                </div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-sm text-ink-gray-6">No supplier concentration data</div>
          </div>

          <!-- Single Source Items -->
          <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
            <SectionHeader variant="caption" title="Single Source Items" :level="3" />
            <p class="text-sm text-ink-gray-6 mt-1 mb-4">
              {{ riskData.single_source_count || 0 }} items with only one supplier
              ({{ formatCurrency(riskData.single_source_value) }} total spend)
            </p>
            <div class="space-y-2 max-h-64 overflow-auto" v-if="riskData.single_source_items?.length">
              <div v-for="item in riskData.single_source_items?.slice(0, 10)" :key="item.item_code"
                   class="flex items-center justify-between p-2 bg-surface-gray-1 rounded">
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
          <SectionHeader variant="caption" :title="`Payment Exposure (${formatCurrency(riskData.total_outstanding)} outstanding)`" :level="3" />
          <div class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 class="font-medium text-ink-gray-7 mb-3">Outstanding by Supplier</h4>
              <div class="space-y-2" v-if="riskData.payment_exposure?.length">
                <div v-for="pay in riskData.payment_exposure?.slice(0, 8)" :key="pay.supplier"
                     class="flex items-center justify-between p-2 bg-surface-gray-1 rounded">
                  <span class="text-sm text-ink-gray-9">{{ pay.supplier_name || pay.supplier }}</span>
                  <span class="text-sm font-medium text-ink-gray-9">{{ formatCurrency(pay.outstanding) }}</span>
                </div>
              </div>
              <div v-else class="text-center py-6 text-sm text-ink-gray-6">No outstanding payments</div>
            </div>
            <div>
              <h4 class="font-medium text-ink-gray-7 mb-3">
                Overdue Invoices ({{ riskData.overdue_count || 0 }})
              </h4>
              <div class="space-y-2 max-h-48 overflow-auto" v-if="riskData.overdue_invoices?.length">
                <div v-for="inv in riskData.overdue_invoices?.slice(0, 8)" :key="inv.name"
                     class="flex items-center justify-between p-2 bg-surface-gray-1 rounded">
                  <div>
                    <div class="text-sm font-medium text-ink-gray-9 cursor-pointer hover:underline"
                         @click="openDocument('Purchase Invoice', inv.name)">
                      {{ inv.name }}
                    </div>
                    <div class="text-xs text-ink-gray-6">{{ inv.supplier }}</div>
                  </div>
                  <div class="text-right">
                    <div class="text-sm font-medium text-ink-gray-9">{{ formatCurrency(inv.outstanding_amount) }}</div>
                    <Badge v-bind="severityBadge(scoreSeverity(inv.days_overdue, { good: 0, warn: 30, higherIsBetter: false }))"
                           :label="`${inv.days_overdue}d overdue`" size="sm" />
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
            variant="tile"
            :loading="loading && !hasData"
          />
          <KpiCard
            label="Trend Direction"
            :value="forecastData.trend_direction === 'up' ? 'Increasing' : 'Decreasing'"
            :sublabel="forecastData.trend_amount ? `${formatCurrency(forecastData.trend_amount)}/month` : undefined"
            variant="tile"
            :loading="loading && !hasData"
          />
          <KpiCard
            label="Data Points"
            :value="forecastData.historical?.length"
            unit=" months"
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
            <SectionHeader variant="caption" title="3-Month Spend Forecast" :level="3" />
            <div class="mt-4 space-y-4" v-if="forecastData.forecasts?.length">
              <div v-for="forecast in forecastData.forecasts" :key="forecast.period"
                   class="flex items-center gap-4 p-4 bg-surface-gray-1 rounded-lg">
                <div class="flex-1">
                  <div class="font-medium text-ink-gray-9">{{ formatPeriod(forecast.period) }}</div>
                  <div class="text-sm text-ink-gray-6">Confidence: {{ forecast.confidence }}</div>
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
            <SectionHeader variant="caption" title="Category-wise 3M Forecast" :level="3" />
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

        <!-- Historical Trend -->
        <div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
          <SectionHeader variant="caption" title="Historical Spend Pattern" :level="3" />
          <IntelligenceChart v-if="forecastData.historical?.length" class="mt-4 h-48 sm:h-56 lg:h-64" :config="historicalSpendConfig" />
          <div v-else class="h-48 flex items-center justify-center text-ink-gray-6">
            No historical data available
          </div>
          <table v-if="forecastData.historical?.length" class="sr-only">
            <caption>Historical monthly spend</caption>
            <thead>
              <tr>
                <th scope="col">Month</th>
                <th scope="col">Spend</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="month in forecastData.historical" :key="month.period">
                <th scope="row">{{ formatPeriod(month.period) }}</th>
                <td>{{ formatCurrency(month.spend) }}</td>
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
  scoreSeverity, severityBadge, severityFill, severityAria,
  deltaInk, deltaGlyph, prioritySeverity, type Severity,
} from '../utils/status'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'
import IntelligenceDashboardShell from '../intelligence/components/IntelligenceDashboardShell.vue'
import { useIntelligenceDashboard } from '../intelligence/composables/useIntelligenceDashboard'
import KpiCard from '../intelligence/components/KpiCard.vue'
import SectionHeader from '../intelligence/components/SectionHeader.vue'
import { themeColor } from '../utils/chartTheme'
import { formatDate, formatMoney, NO_VALUE } from '../utils/format'
import { formatPeriod } from '../components/financial/format'


/** One month of spend trend from procurement_intelligence. */
interface SpendMonthRow { period: string; spend: number }
/** Spend by category row. */
interface CategoryRow { category: string; pct_of_total: number }
/** Top supplier by spend row. */
interface TopSupplierRow {
  supplier: string
  supplier_name?: string
  invoice_count?: number
  spend: number
  pct_of_total: number
}
/** Supplier performance scorecard row. */
interface SupplierPerfRow {
  supplier: string
  supplier_name?: string
  on_time_rate?: number
  /** null when the backend reported ``quality_status: not_implemented`` */
  quality_rate?: number | null
  avg_lead_time?: number
  po_count?: number
  total_value?: number
  overall_score?: number
}
/** Purchase order status summary row. */
interface POStatusRow { status: string; count: number; value: number }
/** Monthly PO trend row. */
interface POMonthRow { period: string; po_value: number; po_count?: number }
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
interface SingleSourceItem { item_code?: string; item_name?: string; only_supplier?: string; total_spend?: number }
/** Payment exposure by supplier row. */
interface PaymentExposureRow { supplier: string; supplier_name?: string; outstanding?: number }
/** Overdue invoice row. */
interface OverdueInvoiceRow { name: string; supplier?: string; outstanding_amount?: number; days_overdue?: number }
/** Spend forecast row. */
interface ForecastRow { period: string; confidence?: string; predicted_spend?: number }
/** Category-level 3-month forecast row. */
interface CategoryForecastRow { category: string; avg_monthly_spend?: number; forecast_3m?: number }
/** Historical spend row. */
interface HistoricalRow { period: string; spend: number }

/** Typed spend overview sub-section from procurement_intelligence endpoint. */
interface SpendData {
  total_spend_12m?: number
  yoy_growth?: number
  supplier_count?: number
  monthly_trend?: SpendMonthRow[]
  by_category?: CategoryRow[]
  top_suppliers?: TopSupplierRow[]
}
/** Typed supplier performance sub-section. */
interface SupplierData {
  avg_lead_time?: number
  avg_on_time_rate?: number
  avg_score?: number
  avg_quality_rate?: number | null
  quality_status?: 'success' | 'not_implemented' | string
  top_performers?: SupplierPerfRow[]
  bottom_performers?: SupplierPerfRow[]
  all_suppliers?: SupplierPerfRow[]
}
/** Typed purchase analytics sub-section. */
interface PurchaseData {
  avg_mr_to_po_days?: number
  avg_po_to_grn_days?: number
  avg_grn_to_invoice_days?: number
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
  total_potential_savings?: number
  price_increases?: PriceVarianceItem[]
  volatile_items?: PriceVarianceItem[]
  price_variance_items?: PriceVarianceItem[]
}
/** Typed procurement risk analysis sub-section. */
interface ProcurementRiskData {
  risk_score?: number
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
  avg_monthly_spend?: number
  trend_direction?: string
  trend_amount?: number
  status?: string
  message?: string
  forecasts?: ForecastRow[]
  category_forecast?: CategoryForecastRow[]
  historical?: HistoricalRow[]
}
const router = useRouter()

const PROC_ENDPOINT = 'insights.api.ml.procurement.get_procurement_detail'
const drillDown = useDrillDown()

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
const baseCurrency = computed(() => procurementData.value?.base_currency ?? 'KES')
const lastUpdated = computed(() => procurementData.value?.generated_at ?? null)

// Summary computed
const summary = computed(() => ({
  totalSpend: (spendData.value.total_spend_12m as number) || 0,
  yoyGrowth: (spendData.value.yoy_growth as number) || 0,
  supplierCount: (spendData.value.supplier_count as number) || 0,
  avgLeadTime: (supplierData.value.avg_lead_time as number) || 0,
  avgOnTimeRate: (supplierData.value.avg_on_time_rate as number) || 0,
  pendingCount: (purchaseData.value.pending_count as number) || 0,
  pendingValue: (purchaseData.value.pending_value as number) || 0,
  riskScore: (riskData.value.risk_score as number) || 0,
}))

// Formatting helpers
const formatCurrency = (value: number | undefined) => formatMoney(value, baseCurrency.value)



// Domain label helpers (non-colour)
const getRiskLabel = (score: number | undefined) => {
  if ((score ?? 0) <= 30) return 'Low Risk'
  if ((score ?? 0) <= 60) return 'Medium Risk'
  return 'High Risk'
}

// Chart configs — ECharts cannot resolve CSS custom properties from canvas; use themeColor().
const monthlySpendConfig = computed(() => ({
  title: '',
  data: (spendData.value.monthly_trend ?? []).map(m => ({
    period: formatPeriod(m.period),
    Spend: m.spend,
  })),
  xAxis: { key: 'period', type: 'category' as const },
  yAxis: { title: baseCurrency.value },
  series: [{ name: 'Spend', type: 'area' as const, color: themeColor('--app-info-fill') }],
}))

const spendByCategoryConfig = computed(() => ({
  title: '',
  data: (spendData.value.by_category ?? []).slice(0, 10).map(c => ({
    category: c.category,
    'Pct of total': c.pct_of_total,
  })),
  xAxis: { key: 'category', type: 'category' as const },
  yAxis: { title: '% of spend' },
  swapXY: true,
  series: [{ name: 'Pct of total', type: 'bar' as const, color: themeColor('--app-info-fill') }],
}))

const monthlyPOConfig = computed(() => ({
  title: '',
  data: (purchaseData.value.monthly_trend ?? []).map(m => ({
    period: formatPeriod(m.period),
    'PO Value': m.po_value,
  })),
  xAxis: { key: 'period', type: 'category' as const },
  yAxis: { title: baseCurrency.value },
  series: [{ name: 'PO Value', type: 'bar' as const, color: themeColor('--app-info-fill') }],
}))

const historicalSpendConfig = computed(() => ({
  title: '',
  data: (forecastData.value.historical ?? []).map(m => ({
    period: formatPeriod(m.period),
    Spend: m.spend,
  })),
  xAxis: { key: 'period', type: 'category' as const },
  yAxis: { title: baseCurrency.value },
  series: [{ name: 'Spend', type: 'area' as const, color: themeColor('--app-accent') }],
}))

function poStatusSeverity(status: string): Severity {
  if (status === 'Cancelled') return 'critical'
  if (status === 'Completed' || status === 'Closed' || status === 'Draft') return 'none'
  if (status === 'To Receive and Bill') return 'low'
  return 'medium'
}

const openDocument = (doctype: string, name: string) => {
  window.open(`/app/${doctype.toLowerCase().replace(/ /g, '-')}/${name}`, '_blank')
}

// Chat context for AI insights
const chatContext = computed(() => ({
  summary: summary.value,
  spendOverview: spendData.value,
  supplierPerformance: supplierData.value,
  purchaseAnalytics: purchaseData.value,
  priceIntelligence: priceData.value,
  riskAnalysis: riskData.value,
  forecasts: forecastData.value,
  activeTab: activeTab.value,
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
