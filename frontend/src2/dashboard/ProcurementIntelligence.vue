<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <header class="bg-white border-b px-6 py-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Procurement Intelligence</h1>
        <p class="text-sm text-gray-500 mt-1">
          Comprehensive procurement analytics, supplier performance, and spend optimization
        </p>
      </div>
      <div class="flex items-center gap-3">
        <span v-if="lastUpdated" class="text-sm text-gray-500">
          Updated: {{ formatDate(lastUpdated) }}
        </span>
        <Button 
          variant="solid" 
          @click="refreshData" 
          :loading="loading"
          icon-left="refresh-cw"
        >
          Refresh Analysis
        </Button>
      </div>
    </header>

    <!-- Summary Cards -->
    <div class="p-6 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Total Spend (12M)</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ formatCurrency(summary.totalSpend) }}
        </div>
        <div :class="summary.yoyGrowth >= 0 ? 'text-red-600' : 'text-green-600'" class="text-sm mt-1">
          {{ summary.yoyGrowth >= 0 ? '↑' : '↓' }} {{ Math.abs(summary.yoyGrowth) }}% YoY
        </div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Active Suppliers</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ summary.supplierCount }}
        </div>
        <div class="text-sm text-gray-500 mt-1">In last 12 months</div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Avg Lead Time</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ summary.avgLeadTime }} days
        </div>
        <div class="text-sm text-gray-500 mt-1">Order to delivery</div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">On-Time Delivery</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ summary.avgOnTimeRate }}%
        </div>
        <div :class="summary.avgOnTimeRate >= 90 ? 'text-green-600' : 'text-amber-600'" class="text-sm mt-1">
          {{ summary.avgOnTimeRate >= 90 ? 'Good' : 'Needs Improvement' }}
        </div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border cursor-pointer hover:bg-blue-50 transition-colors"
           @click="drillDown.open(PROC_ENDPOINT, 'Pending Purchase Orders', { metric: 'pending_pos' })">
        <div class="text-sm font-medium text-gray-500">Pending POs</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ summary.pendingCount }}
        </div>
        <div class="text-sm text-gray-500 mt-1">
          {{ formatCurrency(summary.pendingValue) }}
        </div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Risk Score</div>
        <div class="text-2xl font-bold mt-1" :class="getRiskColor(summary.riskScore)">
          {{ summary.riskScore }}/100
        </div>
        <div class="text-sm mt-1" :class="getRiskColor(summary.riskScore)">
          {{ getRiskLabel(summary.riskScore) }}
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="bg-white border-b mx-6 rounded-t-lg">
      <div class="flex overflow-x-auto">
        <button
          v-for="tab in tabs"
          :key="tab.value"
          @click="activeTab = tab.value"
          :class="[
            'px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 -mb-px',
            activeTab === tab.value 
              ? 'text-blue-600 border-blue-600' 
              : 'text-gray-500 border-transparent hover:text-gray-700'
          ]"
        >
          {{ tab.label }}
        </button>
      </div>
    </div>

    <!-- Tab Content -->
    <div class="flex-1 p-6 overflow-auto">
      <!-- Tab 1: Spend Overview -->
      <div v-if="activeTab === 'spend'" class="space-y-6">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Monthly Spend Trend -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Monthly Spend Trend</h3>
            <div v-if="spendData.monthly_trend?.length" class="h-64">
              <div class="space-y-2">
                <div v-for="month in spendData.monthly_trend.slice(-12)" :key="month.period" 
                     class="flex items-center gap-3">
                  <span class="text-sm text-gray-600 w-20">{{ formatPeriod(month.period) }}</span>
                  <div class="flex-1 bg-gray-100 rounded-full h-6 overflow-hidden">
                    <div 
                      class="bg-blue-500 h-full rounded-full flex items-center justify-end pr-2"
                      :style="{ width: `${getSpendBarWidth(month.spend)}%` }"
                    >
                      <span class="text-xs text-white font-medium">{{ formatCurrency(month.spend) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="h-64 flex items-center justify-center text-gray-500">
              No spend data available
            </div>
          </div>

          <!-- Spend by Category -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Spend by Category</h3>
            <div v-if="spendData.by_category?.length" class="space-y-3">
              <div v-for="cat in spendData.by_category.slice(0, 10)" :key="cat.category"
                   class="flex items-center justify-between">
                <div class="flex items-center gap-3 flex-1">
                  <span class="text-sm font-medium text-gray-700 truncate w-32">{{ cat.category }}</span>
                  <div class="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
                    <div 
                      class="bg-indigo-500 h-full rounded-full"
                      :style="{ width: `${cat.pct_of_total}%` }"
                    ></div>
                  </div>
                </div>
                <span class="text-sm text-gray-600 w-24 text-right">{{ cat.pct_of_total }}%</span>
              </div>
            </div>
            <div v-else class="h-48 flex items-center justify-center text-gray-500">
              No category data available
            </div>
          </div>
        </div>

        <!-- Top Suppliers by Spend -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Top Suppliers by Spend</h3>
          <div class="overflow-x-auto">
            <table class="min-w-full">
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Supplier</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Invoices</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Total Spend</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">% of Total</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Share</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <tr v-for="sup in spendData.top_suppliers" :key="sup.supplier">
                  <td class="px-4 py-3">
                    <div class="font-medium text-gray-900">{{ sup.supplier_name || sup.supplier }}</div>
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-gray-600">{{ sup.invoice_count }}</td>
                  <td class="px-4 py-3 text-right text-sm font-medium text-gray-900">
                    {{ formatCurrency(sup.spend) }}
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-gray-600">{{ sup.pct_of_total }}%</td>
                  <td class="px-4 py-3 w-32">
                    <div class="bg-gray-100 rounded-full h-2 overflow-hidden">
                      <div 
                        class="bg-blue-500 h-full rounded-full"
                        :style="{ width: `${sup.pct_of_total}%` }"
                      ></div>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Tab 2: Supplier Performance -->
      <div v-if="activeTab === 'suppliers'" class="space-y-6">
        <!-- Performance Summary -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Avg Performance Score</div>
            <div class="text-xl font-bold text-gray-900">{{ supplierData.avg_score || 0 }}/100</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Avg On-Time Rate</div>
            <div class="text-xl font-bold text-green-600">{{ supplierData.avg_on_time_rate || 0 }}%</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Avg Quality Rate</div>
            <div class="text-xl font-bold text-blue-600">{{ supplierData.avg_quality_rate || 0 }}%</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Avg Lead Time</div>
            <div class="text-xl font-bold text-gray-900">{{ supplierData.avg_lead_time || 0 }} days</div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Top Performers -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <span class="text-green-500">★</span> Top Performers
            </h3>
            <div class="space-y-3">
              <div v-for="(sup, idx) in supplierData.top_performers?.slice(0, 5)" :key="sup.supplier"
                   class="flex items-center gap-3 p-3 bg-green-50 rounded-lg cursor-pointer hover:bg-blue-50 transition-colors"
                   @click="drillDown.open(PROC_ENDPOINT, (sup.supplier_name || sup.supplier) + ' Purchase Orders', { metric: 'supplier_performance', supplier: sup.supplier })">
                <div class="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center text-white font-bold">
                  {{ idx + 1 }}
                </div>
                <div class="flex-1">
                  <div class="font-medium text-gray-900">{{ sup.supplier_name || sup.supplier }}</div>
                  <div class="text-sm text-gray-500">
                    On-time: {{ sup.on_time_rate }}% | Quality: {{ sup.quality_rate }}%
                  </div>
                </div>
                <div class="text-lg font-bold text-green-600">{{ sup.overall_score }}</div>
              </div>
            </div>
          </div>

          <!-- Needs Improvement -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <span class="text-amber-500">⚠</span> Needs Improvement
            </h3>
            <div class="space-y-3">
              <div v-for="sup in supplierData.bottom_performers?.slice(0, 5)" :key="sup.supplier"
                   class="flex items-center gap-3 p-3 bg-amber-50 rounded-lg cursor-pointer hover:bg-blue-50 transition-colors"
                   @click="drillDown.open(PROC_ENDPOINT, (sup.supplier_name || sup.supplier) + ' Purchase Orders', { metric: 'supplier_performance', supplier: sup.supplier })">
                <div class="flex-1">
                  <div class="font-medium text-gray-900">{{ sup.supplier_name || sup.supplier }}</div>
                  <div class="text-sm text-gray-500">
                    On-time: {{ sup.on_time_rate }}% | Quality: {{ sup.quality_rate }}%
                  </div>
                </div>
                <div class="text-lg font-bold text-amber-600">{{ sup.overall_score }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- All Suppliers Table -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">All Supplier Scores</h3>
          <div class="overflow-x-auto">
            <table class="min-w-full">
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Supplier</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">PO Count</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Total Value</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">On-Time %</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Quality %</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Lead Time</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Score</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <tr v-for="sup in supplierData.all_suppliers?.slice(0, 20)" :key="sup.supplier"
                    class="cursor-pointer hover:bg-blue-50 transition-colors"
                    @click="drillDown.open(PROC_ENDPOINT, (sup.supplier_name || sup.supplier) + ' Purchase Orders', { metric: 'supplier_performance', supplier: sup.supplier })">
                  <td class="px-4 py-3 font-medium text-gray-900">{{ sup.supplier_name || sup.supplier }}</td>
                  <td class="px-4 py-3 text-right text-sm text-gray-600">{{ sup.po_count }}</td>
                  <td class="px-4 py-3 text-right text-sm text-gray-900">{{ formatCurrency(sup.total_value) }}</td>
                  <td class="px-4 py-3 text-right">
                    <span :class="getPercentageColor(sup.on_time_rate)" class="font-medium">
                      {{ sup.on_time_rate }}%
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right">
                    <span :class="getPercentageColor(sup.quality_rate)" class="font-medium">
                      {{ sup.quality_rate }}%
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-gray-600">{{ sup.avg_lead_time }} days</td>
                  <td class="px-4 py-3 text-right">
                    <span class="px-2 py-1 rounded text-sm font-bold" :class="getScoreBadge(sup.overall_score)">
                      {{ sup.overall_score }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Tab 3: Purchase Analytics -->
      <div v-if="activeTab === 'analytics'" class="space-y-6">
        <!-- Cycle Times -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">MR to PO</div>
            <div class="text-2xl font-bold text-gray-900">{{ purchaseData.avg_mr_to_po_days || 0 }} days</div>
            <div class="text-sm text-gray-500">Average processing time</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">PO to GRN</div>
            <div class="text-2xl font-bold text-gray-900">{{ purchaseData.avg_po_to_grn_days || 0 }} days</div>
            <div class="text-sm text-gray-500">Average delivery time</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">GRN to Invoice</div>
            <div class="text-2xl font-bold text-gray-900">{{ purchaseData.avg_grn_to_invoice_days || 0 }} days</div>
            <div class="text-sm text-gray-500">Average invoice time</div>
          </div>
        </div>

        <!-- PO Status Summary -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Purchase Order Status</h3>
          <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <div v-for="status in purchaseData.po_status_summary" :key="status.status"
                 class="p-4 rounded-lg" :class="getStatusBgColor(status.status)">
              <div class="text-sm font-medium" :class="getStatusTextColor(status.status)">{{ status.status }}</div>
              <div class="text-xl font-bold text-gray-900">{{ status.count }}</div>
              <div class="text-sm text-gray-500">{{ formatCurrency(status.value) }}</div>
            </div>
          </div>
        </div>

        <!-- Monthly PO Trend -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Monthly Purchase Order Trend</h3>
          <div class="space-y-2">
            <div v-for="month in purchaseData.monthly_trend?.slice(-12)" :key="month.period"
                 class="flex items-center gap-3">
              <span class="text-sm text-gray-600 w-20">{{ formatPeriod(month.period) }}</span>
              <div class="flex-1 flex gap-2">
                <div class="flex-1 bg-gray-100 rounded-full h-6 overflow-hidden">
                  <div 
                    class="bg-indigo-500 h-full rounded-full flex items-center justify-end pr-2"
                    :style="{ width: `${getPOBarWidth(month.po_value)}%` }"
                  >
                    <span class="text-xs text-white font-medium">{{ formatCurrency(month.po_value) }}</span>
                  </div>
                </div>
                <span class="text-sm text-gray-500 w-16">{{ month.po_count }} POs</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Pending POs -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">
            Pending Purchase Orders ({{ purchaseData.pending_count || 0 }})
          </h3>
          <div class="overflow-x-auto">
            <table class="min-w-full">
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">PO#</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Supplier</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Amount</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Days Pending</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <tr v-for="po in purchaseData.pending_pos?.slice(0, 15)" :key="po.name">
                  <td class="px-4 py-3 font-medium text-blue-600 cursor-pointer hover:underline"
                      @click="openDocument('Purchase Order', po.name)">
                    {{ po.name }}
                  </td>
                  <td class="px-4 py-3 text-sm text-gray-900">{{ po.supplier }}</td>
                  <td class="px-4 py-3 text-sm text-gray-600">{{ formatDate(po.transaction_date) }}</td>
                  <td class="px-4 py-3 text-right text-sm font-medium text-gray-900">
                    {{ formatCurrency(po.grand_total) }}
                  </td>
                  <td class="px-4 py-3 text-right">
                    <span class="px-2 py-1 rounded text-sm" :class="getDaysBadge(po.days_pending)">
                      {{ po.days_pending }} days
                    </span>
                  </td>
                  <td class="px-4 py-3 text-sm text-gray-600">{{ po.status }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Tab 4: Price Intelligence -->
      <div v-if="activeTab === 'pricing'" class="space-y-6">
        <!-- Summary -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Items Analyzed</div>
            <div class="text-2xl font-bold text-gray-900">{{ priceData.items_analyzed || 0 }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Items with Price Increases</div>
            <div class="text-2xl font-bold text-red-600">{{ priceData.price_increases?.length || 0 }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Potential Savings</div>
            <div class="text-2xl font-bold text-green-600">{{ formatCurrency(priceData.total_potential_savings) }}</div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Price Increases -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <span class="text-red-500">↑</span> Recent Price Increases
            </h3>
            <div class="space-y-3">
              <div v-for="item in priceData.price_increases?.slice(0, 8)" :key="item.item_code"
                   class="p-3 bg-red-50 rounded-lg">
                <div class="flex justify-between items-start">
                  <div>
                    <div class="font-medium text-gray-900">{{ item.item_name || item.item_code }}</div>
                    <div class="text-sm text-gray-500">{{ item.item_group }}</div>
                  </div>
                  <div class="text-right">
                    <div class="text-lg font-bold text-red-600">+{{ item.price_variance_pct }}%</div>
                    <div class="text-sm text-gray-500">vs avg</div>
                  </div>
                </div>
                <div class="mt-2 flex gap-4 text-sm">
                  <span>Last: {{ formatCurrency(item.last_rate) }}</span>
                  <span>Avg: {{ formatCurrency(item.avg_rate) }}</span>
                  <span>Min: {{ formatCurrency(item.min_rate) }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Volatile Items -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <span class="text-amber-500">⚡</span> High Price Variance Items
            </h3>
            <div class="space-y-3">
              <div v-for="item in priceData.volatile_items?.slice(0, 8)" :key="item.item_code"
                   class="p-3 bg-amber-50 rounded-lg">
                <div class="flex justify-between items-start">
                  <div>
                    <div class="font-medium text-gray-900">{{ item.item_name || item.item_code }}</div>
                    <div class="text-sm text-gray-500">{{ item.purchase_count }} purchases</div>
                  </div>
                  <div class="text-right">
                    <div class="text-lg font-bold text-amber-600">{{ item.price_range_pct }}%</div>
                    <div class="text-sm text-gray-500">variance</div>
                  </div>
                </div>
                <div class="mt-2 flex gap-4 text-sm">
                  <span>Min: {{ formatCurrency(item.min_rate) }}</span>
                  <span>Max: {{ formatCurrency(item.max_rate) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Price Variance Table -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Item Price Analysis</h3>
          <div class="overflow-x-auto">
            <table class="min-w-full">
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Item</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Category</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Purchases</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Avg Rate</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Last Rate</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Variance</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Savings</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <tr v-for="item in priceData.price_variance_items" :key="item.item_code">
                  <td class="px-4 py-3">
                    <div class="font-medium text-gray-900">{{ item.item_name || item.item_code }}</div>
                  </td>
                  <td class="px-4 py-3 text-sm text-gray-600">{{ item.item_group }}</td>
                  <td class="px-4 py-3 text-right text-sm text-gray-600">{{ item.purchase_count }}</td>
                  <td class="px-4 py-3 text-right text-sm text-gray-900">{{ formatCurrency(item.avg_rate) }}</td>
                  <td class="px-4 py-3 text-right text-sm text-gray-900">{{ formatCurrency(item.last_rate) }}</td>
                  <td class="px-4 py-3 text-right">
                    <span :class="item.price_variance_pct > 0 ? 'text-red-600' : 'text-green-600'" class="font-medium">
                      {{ item.price_variance_pct > 0 ? '+' : '' }}{{ item.price_variance_pct }}%
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-green-600 font-medium">
                    {{ formatCurrency(item.potential_savings) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Tab 5: Risk Analysis -->
      <div v-if="activeTab === 'risks'" class="space-y-6">
        <!-- Risk Score Card -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="text-lg font-semibold text-gray-900">Procurement Risk Score</h3>
              <p class="text-sm text-gray-500">Lower is better. Based on concentration, single-source, and payment risks.</p>
            </div>
            <div class="text-center">
              <div class="text-5xl font-bold" :class="getRiskColor(riskData.risk_score)">
                {{ riskData.risk_score || 0 }}
              </div>
              <div class="text-sm" :class="getRiskColor(riskData.risk_score)">
                {{ getRiskLabel(riskData.risk_score) }}
              </div>
            </div>
          </div>
          <div class="mt-4 bg-gray-100 rounded-full h-4 overflow-hidden">
            <div 
              class="h-full rounded-full transition-all"
              :class="getRiskBarColor(riskData.risk_score)"
              :style="{ width: `${riskData.risk_score}%` }"
            ></div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Supplier Concentration -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Supplier Concentration Risk</h3>
            <div class="space-y-3">
              <div v-for="sup in riskData.supplier_concentration" :key="sup.supplier"
                   class="flex items-center gap-3 p-3 rounded-lg"
                   :class="sup.risk_level === 'High' ? 'bg-red-50' : (sup.risk_level === 'Medium' ? 'bg-amber-50' : 'bg-green-50')">
                <div class="flex-1">
                  <div class="font-medium text-gray-900">{{ sup.supplier_name || sup.supplier }}</div>
                  <div class="text-sm text-gray-500">{{ formatCurrency(sup.spend) }} spend</div>
                </div>
                <div class="text-right">
                  <div class="text-lg font-bold">{{ sup.concentration_pct }}%</div>
                  <span class="text-xs px-2 py-1 rounded" 
                        :class="sup.risk_level === 'High' ? 'bg-red-100 text-red-700' : (sup.risk_level === 'Medium' ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700')">
                    {{ sup.risk_level }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Single Source Items -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-2">Single Source Items</h3>
            <p class="text-sm text-gray-500 mb-4">
              {{ riskData.single_source_count || 0 }} items with only one supplier 
              ({{ formatCurrency(riskData.single_source_value) }} total spend)
            </p>
            <div class="space-y-2 max-h-64 overflow-auto">
              <div v-for="item in riskData.single_source_items?.slice(0, 10)" :key="item.item_code"
                   class="flex items-center justify-between p-2 bg-amber-50 rounded">
                <div>
                  <div class="font-medium text-gray-900 text-sm">{{ item.item_name || item.item_code }}</div>
                  <div class="text-xs text-gray-500">{{ item.only_supplier }}</div>
                </div>
                <div class="text-sm font-medium text-gray-900">{{ formatCurrency(item.total_spend) }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Payment Exposure -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">
            Payment Exposure ({{ formatCurrency(riskData.total_outstanding) }} outstanding)
          </h3>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 class="font-medium text-gray-700 mb-3">Outstanding by Supplier</h4>
              <div class="space-y-2">
                <div v-for="pay in riskData.payment_exposure?.slice(0, 8)" :key="pay.supplier"
                     class="flex items-center justify-between p-2 bg-gray-50 rounded">
                  <span class="text-sm text-gray-900">{{ pay.supplier_name || pay.supplier }}</span>
                  <span class="text-sm font-medium text-gray-900">{{ formatCurrency(pay.outstanding) }}</span>
                </div>
              </div>
            </div>
            <div>
              <h4 class="font-medium text-gray-700 mb-3">
                Overdue Invoices ({{ riskData.overdue_count || 0 }})
              </h4>
              <div class="space-y-2 max-h-48 overflow-auto">
                <div v-for="inv in riskData.overdue_invoices?.slice(0, 8)" :key="inv.name"
                     class="flex items-center justify-between p-2 bg-red-50 rounded">
                  <div>
                    <div class="text-sm font-medium text-gray-900 cursor-pointer hover:underline"
                         @click="openDocument('Purchase Invoice', inv.name)">
                      {{ inv.name }}
                    </div>
                    <div class="text-xs text-gray-500">{{ inv.supplier }}</div>
                  </div>
                  <div class="text-right">
                    <div class="text-sm font-medium text-red-600">{{ formatCurrency(inv.outstanding_amount) }}</div>
                    <div class="text-xs text-red-600">{{ inv.days_overdue }} days overdue</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 6: Forecasts & Planning -->
      <div v-if="activeTab === 'forecasts'" class="space-y-6">
        <!-- Forecast Summary -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Avg Monthly Spend</div>
            <div class="text-2xl font-bold text-gray-900">{{ formatCurrency(forecastData.avg_monthly_spend) }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Trend Direction</div>
            <div class="text-2xl font-bold" :class="forecastData.trend_direction === 'up' ? 'text-red-600' : 'text-green-600'">
              {{ forecastData.trend_direction === 'up' ? '↑ Increasing' : '↓ Decreasing' }}
            </div>
            <div class="text-sm text-gray-500">{{ formatCurrency(forecastData.trend_amount) }}/month</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Data Points</div>
            <div class="text-2xl font-bold text-gray-900">{{ forecastData.historical?.length || 0 }} months</div>
          </div>
        </div>

        <div v-if="forecastData.status === 'insufficient_data'" class="bg-amber-50 border border-amber-200 rounded-lg p-4">
          <p class="text-amber-800">{{ forecastData.message }}</p>
        </div>

        <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Spend Forecast -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">3-Month Spend Forecast</h3>
            <div class="space-y-4">
              <div v-for="forecast in forecastData.forecasts" :key="forecast.period"
                   class="flex items-center gap-4 p-4 bg-blue-50 rounded-lg">
                <div class="flex-1">
                  <div class="font-medium text-gray-900">{{ formatPeriod(forecast.period) }}</div>
                  <div class="text-sm text-gray-500">Confidence: {{ forecast.confidence }}</div>
                </div>
                <div class="text-xl font-bold text-blue-600">
                  {{ formatCurrency(forecast.predicted_spend) }}
                </div>
              </div>
            </div>
          </div>

          <!-- Category Forecast -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Category-wise 3M Forecast</h3>
            <div class="space-y-3">
              <div v-for="cat in forecastData.category_forecast" :key="cat.category"
                   class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <div class="font-medium text-gray-900">{{ cat.category }}</div>
                  <div class="text-sm text-gray-500">Avg: {{ formatCurrency(cat.avg_monthly_spend) }}/mo</div>
                </div>
                <div class="text-lg font-bold text-indigo-600">
                  {{ formatCurrency(cat.forecast_3m) }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Historical Trend -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Historical Spend Pattern</h3>
          <div class="space-y-2">
            <div v-for="month in forecastData.historical?.slice(-12)" :key="month.period"
                 class="flex items-center gap-3">
              <span class="text-sm text-gray-600 w-20">{{ formatPeriod(month.period) }}</span>
              <div class="flex-1 bg-gray-100 rounded-full h-6 overflow-hidden">
                <div 
                  class="bg-gradient-to-r from-blue-400 to-blue-600 h-full rounded-full flex items-center justify-end pr-2"
                  :style="{ width: `${getHistoricalBarWidth(month.spend)}%` }"
                >
                  <span class="text-xs text-white font-medium">{{ formatCurrency(month.spend) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

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
defineOptions({ name: 'ProcurementIntelligence' })
import { ref, computed, onMounted } from 'vue'
import { Button, createResource } from 'frappe-ui'
import { useRouter } from 'vue-router'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'

const router = useRouter()

const PROC_ENDPOINT = 'insights.api.ml.procurement.get_procurement_detail'
const drillDown = useDrillDown()

const activeTab = ref('spend')
const loading = ref(false)
const lastUpdated = ref<string | null>(null)
const baseCurrency = ref('KES')

const tabs = [
  { label: 'Spend Overview', value: 'spend' },
  { label: 'Supplier Performance', value: 'suppliers' },
  { label: 'Purchase Analytics', value: 'analytics' },
  { label: 'Price Intelligence', value: 'pricing' },
  { label: 'Risk Analysis', value: 'risks' },
  { label: 'Forecasts & Planning', value: 'forecasts' }
]

// Data refs
const spendData = ref<any>({})
const supplierData = ref<any>({})
const purchaseData = ref<any>({})
const priceData = ref<any>({})
const riskData = ref<any>({})
const forecastData = ref<any>({})

// Summary computed
const summary = computed(() => ({
  totalSpend: spendData.value.total_spend_12m || 0,
  yoyGrowth: spendData.value.yoy_growth || 0,
  supplierCount: spendData.value.supplier_count || 0,
  avgLeadTime: supplierData.value.avg_lead_time || 0,
  avgOnTimeRate: supplierData.value.avg_on_time_rate || 0,
  pendingCount: purchaseData.value.pending_count || 0,
  pendingValue: purchaseData.value.pending_value || 0,
  riskScore: riskData.value.risk_score || 0
}))

// API Resources
const procurementResource = createResource({
  url: 'insights.api.ml.procurement_intelligence',
  auto: false,
  onSuccess(data: any) {
    if (data.status === 'success') {
      spendData.value = data.spend_overview || {}
      supplierData.value = data.supplier_performance || {}
      purchaseData.value = data.purchase_analytics || {}
      priceData.value = data.price_intelligence || {}
      riskData.value = data.risk_analysis || {}
      forecastData.value = data.forecasts || {}
      lastUpdated.value = data.generated_at
      if (data.base_currency) {
        baseCurrency.value = data.base_currency
      }
    }
    loading.value = false
  },
  onError(err: any) {
    console.error('Procurement Intelligence error:', err)
    loading.value = false
  }
})

const refreshData = () => {
  loading.value = true
  procurementResource.submit({ refresh: true })
}

onMounted(() => {
  loading.value = true
  procurementResource.submit({ refresh: false })
})

// Formatting helpers
const formatCurrency = (value: number | undefined) => {
  if (value === undefined || value === null) return `${baseCurrency.value} 0`
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: baseCurrency.value,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const formatDate = (date: string | undefined) => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('en-KE', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}

const formatPeriod = (period: string) => {
  if (!period) return ''
  const [year, month] = period.split('-')
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${monthNames[parseInt(month) - 1]} ${year.slice(2)}`
}

// Bar width calculators
const getSpendBarWidth = (spend: number) => {
  const maxSpend = Math.max(...(spendData.value.monthly_trend?.map((m: any) => m.spend) || [1]))
  return Math.max(10, (spend / maxSpend) * 100)
}

const getPOBarWidth = (value: number) => {
  const maxValue = Math.max(...(purchaseData.value.monthly_trend?.map((m: any) => m.po_value) || [1]))
  return Math.max(10, (value / maxValue) * 100)
}

const getHistoricalBarWidth = (spend: number) => {
  const maxSpend = Math.max(...(forecastData.value.historical?.map((m: any) => m.spend) || [1]))
  return Math.max(10, (spend / maxSpend) * 100)
}

// Color helpers
const getRiskColor = (score: number) => {
  if (score <= 30) return 'text-green-600'
  if (score <= 60) return 'text-amber-600'
  return 'text-red-600'
}

const getRiskBarColor = (score: number) => {
  if (score <= 30) return 'bg-green-500'
  if (score <= 60) return 'bg-amber-500'
  return 'bg-red-500'
}

const getRiskLabel = (score: number) => {
  if (score <= 30) return 'Low Risk'
  if (score <= 60) return 'Medium Risk'
  return 'High Risk'
}

const getPercentageColor = (pct: number) => {
  if (pct >= 90) return 'text-green-600'
  if (pct >= 70) return 'text-amber-600'
  return 'text-red-600'
}

const getScoreBadge = (score: number) => {
  if (score >= 80) return 'bg-green-100 text-green-700'
  if (score >= 60) return 'bg-amber-100 text-amber-700'
  return 'bg-red-100 text-red-700'
}

const getDaysBadge = (days: number) => {
  if (days <= 7) return 'bg-green-100 text-green-700'
  if (days <= 14) return 'bg-amber-100 text-amber-700'
  return 'bg-red-100 text-red-700'
}

const getStatusBgColor = (status: string) => {
  const colors: Record<string, string> = {
    'Draft': 'bg-gray-100',
    'To Receive and Bill': 'bg-blue-100',
    'To Receive': 'bg-indigo-100',
    'To Bill': 'bg-purple-100',
    'Completed': 'bg-green-100',
    'Closed': 'bg-gray-100',
    'Cancelled': 'bg-red-100'
  }
  return colors[status] || 'bg-gray-100'
}

const getStatusTextColor = (status: string) => {
  const colors: Record<string, string> = {
    'Draft': 'text-gray-700',
    'To Receive and Bill': 'text-blue-700',
    'To Receive': 'text-indigo-700',
    'To Bill': 'text-purple-700',
    'Completed': 'text-green-700',
    'Closed': 'text-gray-700',
    'Cancelled': 'text-red-700'
  }
  return colors[status] || 'text-gray-700'
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
  lastUpdated: lastUpdated.value
}))

// Handle navigation to other dashboards from chat suggestions
function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    'Sales': '/sales-intelligence',
    'Risk': '/risk-intelligence',
    'Inventory': '/inventory-intelligence',
    'Financial': '/financial-intelligence',
    'Customer': '/customer-intelligence',
    'Procurement': '/procurement-intelligence'
  }
  if (routes[target]) {
    router.push(routes[target])
  }
}
</script>
