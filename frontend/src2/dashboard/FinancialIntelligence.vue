<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <header class="bg-white border-b px-6 py-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Financial Intelligence</h1>
        <p class="text-sm text-gray-500 mt-1">
          Comprehensive financial analytics, cash flow management, and KRA tax compliance
        </p>
      </div>
      <div class="flex items-center gap-3">
        <IntelligenceDateFilter v-model="dateFilter" />
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
        <div class="text-sm font-medium text-gray-500">Net Profit (12M)</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ formatCurrency(summary.netProfit) }}
        </div>
        <div :class="summary.profitMargin >= 0 ? 'text-green-600' : 'text-red-600'" class="text-sm mt-1">
          {{ summary.profitMargin >= 0 ? '↑' : '↓' }} {{ Math.abs(summary.profitMargin) }}% margin
        </div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Cash Position</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ formatCurrency(summary.cashPosition) }}
        </div>
        <div class="text-sm text-gray-500 mt-1">{{ summary.cashRunway }} days runway</div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Outstanding AR</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ formatCurrency(summary.outstandingAR) }}
        </div>
        <div class="text-sm text-gray-500 mt-1">{{ summary.avgDSO }} days DSO</div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Outstanding AP</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ formatCurrency(summary.outstandingAP) }}
        </div>
        <div class="text-sm text-gray-500 mt-1">{{ summary.avgDPO }} days DPO</div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Net VAT Payable</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ formatCurrency(summary.netVATPayable) }}
        </div>
        <div class="text-sm text-gray-500 mt-1">16% VAT rate</div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Forex Exposure</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ formatCurrency(summary.forexExposure) }}
        </div>
        <div class="text-sm text-gray-500 mt-1">{{ summary.forexCurrencies }} currencies</div>
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
      <!-- Tab 1: Overview -->
      <div v-if="activeTab === 'overview'" class="space-y-6">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- P&L Summary -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Profit & Loss Summary (YTD)</h3>
            <div class="space-y-3">
              <div class="flex justify-between items-center">
                <span class="text-gray-600">Total Revenue</span>
                <span class="font-medium text-gray-900">{{ formatCurrency(overviewData.ytd_revenue) }}</span>
              </div>
              <div class="flex justify-between items-center">
                <span class="text-gray-600">Total Expenses</span>
                <span class="font-medium text-gray-900">{{ formatCurrency(overviewData.ytd_expenses) }}</span>
              </div>
              <div class="flex justify-between items-center border-t pt-2">
                <span class="font-medium text-gray-900">Net Profit</span>
                <span :class="overviewData.ytd_profit >= 0 ? 'text-green-600' : 'text-red-600'" class="font-bold">
                  {{ formatCurrency(overviewData.ytd_profit) }}
                </span>
              </div>
              <div class="flex justify-between items-center">
                <span class="text-gray-600">Profit Margin</span>
                <span class="font-medium text-gray-900">{{ overviewData.net_margin }}%</span>
              </div>
            </div>
          </div>

          <!-- Monthly Revenue Trend -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Monthly Revenue Trend</h3>
            <div v-if="overviewData.monthly_trend?.length" class="h-64">
              <div class="space-y-2">
                <div v-for="month in overviewData.monthly_trend.slice(-12)" :key="month.period" 
                     class="flex items-center gap-3">
                  <span class="text-sm text-gray-600 w-20">{{ formatPeriod(month.period) }}</span>
                  <div class="flex-1 bg-gray-100 rounded-full h-6 overflow-hidden">
                    <div 
                      class="bg-green-500 h-full rounded-full flex items-center justify-end pr-2"
                      :style="{ width: `${getRevenueBarWidth(month.revenue)}%` }"
                    >
                      <span class="text-xs text-white font-medium">{{ formatCurrency(month.revenue) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="h-64 flex items-center justify-center text-gray-500">
              No revenue data available
            </div>
          </div>
        </div>

        <!-- Expense Breakdown -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Expense Breakdown</h3>
          <div class="overflow-x-auto">
            <table class="min-w-full">
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Category</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Amount</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">% of Total</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Share</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <tr v-for="expense in overviewData.expense_breakdown" :key="expense.category">
                  <td class="px-4 py-3 font-medium text-gray-900">{{ expense.category }}</td>
                  <td class="px-4 py-3 text-right text-sm font-medium text-gray-900">
                    {{ formatCurrency(expense.amount) }}
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-gray-600">{{ expense.pct }}%</td>
                  <td class="px-4 py-3 w-32">
                    <div class="bg-gray-100 rounded-full h-2 overflow-hidden">
                      <div 
                        class="bg-red-500 h-full rounded-full"
                        :style="{ width: `${expense.pct}%` }"
                      ></div>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Tab 2: Cash Flow -->
      <div v-if="activeTab === 'cashflow'" class="space-y-6">
        <!-- Cash Position Summary -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Current Cash</div>
            <div class="text-xl font-bold text-gray-900">{{ formatCurrency(cashFlowData.total_cash) }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Monthly Inflow</div>
            <div class="text-xl font-bold text-green-600">{{ formatCurrency(cashFlowData.avg_monthly_inflow) }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Monthly Outflow</div>
            <div class="text-xl font-bold text-red-600">{{ formatCurrency(cashFlowData.avg_monthly_outflow) }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Cash Runway</div>
            <div class="text-xl font-bold text-gray-900">{{ Math.round((cashFlowData.runway_months || 0) * 30) }} days</div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Cash Accounts -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Cash & Bank Accounts</h3>
            <div class="space-y-2 max-h-64 overflow-auto">
              <div v-for="acc in cashFlowData.cash_accounts" :key="acc.account"
                   class="flex items-center justify-between p-2 bg-gray-50 rounded">
                <div>
                  <div class="font-medium text-gray-900 text-sm">{{ acc.account_name }}</div>
                  <div class="text-xs text-gray-500">{{ acc.account_type }}</div>
                </div>
                <span :class="acc.balance >= 0 ? 'text-green-600' : 'text-red-600'" class="font-medium">
                  {{ formatCurrency(acc.balance) }}
                </span>
              </div>
            </div>
          </div>

          <!-- Monthly Inflows -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Monthly Cash Inflows</h3>
            <div class="space-y-2">
              <div v-for="month in cashFlowData.monthly_inflows?.slice(-6)" :key="month.period"
                   class="flex items-center gap-3">
                <span class="text-sm text-gray-600 w-20">{{ formatPeriod(month.period) }}</span>
                <div class="flex-1 bg-gray-100 rounded-full h-6 overflow-hidden">
                  <div 
                    class="bg-green-500 h-full rounded-full flex items-center justify-end pr-2"
                    :style="{ width: `${getInflowBarWidth(month.amount)}%` }"
                  >
                    <span class="text-xs text-white font-medium">{{ formatCurrency(month.amount) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 3: Receivables -->
      <div v-if="activeTab === 'receivables'" class="space-y-6">
        <!-- AR Summary -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Total Outstanding</div>
            <div class="text-xl font-bold text-gray-900">{{ formatCurrency(receivablesData.total_outstanding) }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Days Sales Outstanding</div>
            <div class="text-xl font-bold text-gray-900">{{ Math.round(receivablesData.current_dso || 0) }} days</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Invoice Count</div>
            <div class="text-xl font-bold text-gray-900">{{ receivablesData.invoice_count }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">90+ Days Overdue</div>
            <div class="text-xl font-bold text-red-600">{{ formatCurrency(get90PlusOverdue(receivablesData.aging_buckets)) }}</div>
          </div>
        </div>

        <!-- Aging Analysis -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Accounts Receivable Aging</h3>
          <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <div v-for="bucket in receivablesData.aging_buckets" :key="bucket.bucket"
                 class="p-4 rounded-lg bg-gray-50">
              <div class="text-sm font-medium text-gray-700">{{ bucket.bucket }}</div>
              <div class="text-xl font-bold text-gray-900">{{ formatCurrency(bucket.amount) }}</div>
              <div class="text-sm text-gray-500">{{ bucket.count }} invoices</div>
            </div>
          </div>
        </div>

        <!-- Top Debtors -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Top Outstanding Customers</h3>
          <div class="overflow-x-auto">
            <table class="min-w-full">
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Customer</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Outstanding</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Invoices</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Days Overdue</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <tr v-for="customer in receivablesData.overdue_customers?.slice(0, 10)" :key="customer.customer">
                  <td class="px-4 py-3 font-medium text-gray-900">{{ customer.customer_name || customer.customer }}</td>
                  <td class="px-4 py-3 text-right text-sm font-medium text-gray-900">
                    {{ formatCurrency(customer.total_outstanding) }}
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-gray-600">{{ customer.invoice_count }}</td>
                  <td class="px-4 py-3 text-right">
                    <span class="px-2 py-1 rounded text-sm" :class="getDaysBadge(customer.max_overdue_days)">
                      {{ customer.max_overdue_days }} days
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Tab 4: Payables -->
      <div v-if="activeTab === 'payables'" class="space-y-6">
        <!-- AP Summary -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Total Outstanding</div>
            <div class="text-xl font-bold text-gray-900">{{ formatCurrency(payablesData.total_outstanding) }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Days Payable Outstanding</div>
            <div class="text-xl font-bold text-gray-900">{{ Math.round(payablesData.current_dpo || 0) }} days</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Invoice Count</div>
            <div class="text-xl font-bold text-gray-900">{{ payablesData.invoice_count }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">90+ Days Overdue</div>
            <div class="text-xl font-bold text-red-600">{{ formatCurrency(get90PlusOverdue(payablesData.aging_buckets)) }}</div>
          </div>
        </div>

        <!-- Aging Analysis -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Accounts Payable Aging</h3>
          <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <div v-for="bucket in payablesData.aging_buckets" :key="bucket.bucket"
                 class="p-4 rounded-lg bg-gray-50">
              <div class="text-sm font-medium text-gray-700">{{ bucket.bucket }}</div>
              <div class="text-xl font-bold text-gray-900">{{ formatCurrency(bucket.amount) }}</div>
              <div class="text-sm text-gray-500">{{ bucket.count }} bills</div>
            </div>
          </div>
        </div>

        <!-- Top Creditors -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Top Outstanding Suppliers</h3>
          <div class="overflow-x-auto">
            <table class="min-w-full">
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Supplier</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Outstanding</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Invoices</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <tr v-for="supplier in payablesData.top_suppliers?.slice(0, 10)" :key="supplier.supplier">
                  <td class="px-4 py-3 font-medium text-gray-900">{{ supplier.supplier_name || supplier.supplier }}</td>
                  <td class="px-4 py-3 text-right text-sm font-medium text-gray-900">
                    {{ formatCurrency(supplier.total_outstanding) }}
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-gray-600">{{ supplier.invoice_count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Tab 5: Financial Ratios & Trends -->
      <div v-if="activeTab === 'ratios'" class="space-y-6">
        <!-- Ratio Category Cards -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          
          <!-- Liquidity Ratios -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <div class="flex items-center gap-2 mb-4">
              <div class="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
                </svg>
              </div>
              <h3 class="text-lg font-semibold text-gray-900">Liquidity</h3>
            </div>
            <div class="space-y-3">
              <div class="flex justify-between items-center">
                <span class="text-sm text-gray-600">Current Ratio</span>
                <span class="font-semibold" :class="getRatioColor('current', ratiosData.liquidity?.current_ratio)">
                  {{ ratiosData.liquidity?.current_ratio || 'N/A' }}
                </span>
              </div>
              <div class="flex justify-between items-center">
                <span class="text-sm text-gray-600">Quick Ratio</span>
                <span class="font-semibold" :class="getRatioColor('quick', ratiosData.liquidity?.quick_ratio)">
                  {{ typeof ratiosData.liquidity?.quick_ratio === 'number' ? ratiosData.liquidity.quick_ratio.toFixed(2) : 'N/A' }}
                </span>
              </div>
              <div class="flex justify-between items-center">
                <span class="text-sm text-gray-600">Cash Ratio</span>
                <span class="font-semibold" :class="getRatioColor('cash', ratiosData.liquidity?.cash_ratio)">
                  {{ ratiosData.liquidity?.cash_ratio || 'N/A' }}
                </span>
              </div>
              <div class="flex justify-between items-center pt-2 border-t">
                <span class="text-sm text-gray-600">Working Capital</span>
                <span class="font-semibold" :class="(ratiosData.liquidity?.working_capital || 0) >= 0 ? 'text-green-600' : 'text-red-600'">
                  {{ formatCurrency(ratiosData.liquidity?.working_capital) }}
                </span>
              </div>
            </div>
          </div>

          <!-- Profitability Ratios -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <div class="flex items-center gap-2 mb-4">
              <div class="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                <svg class="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/>
                </svg>
              </div>
              <h3 class="text-lg font-semibold text-gray-900">Profitability</h3>
            </div>
            <div class="space-y-3">
              <div class="flex justify-between items-center">
                <span class="text-sm text-gray-600">Gross Margin</span>
                <span class="font-semibold" :class="getMarginColor(ratiosData.profitability?.gross_margin)">
                  {{ ratiosData.profitability?.gross_margin || 0 }}%
                </span>
              </div>
              <div class="flex justify-between items-center">
                <span class="text-sm text-gray-600">Net Margin</span>
                <span class="font-semibold" :class="getMarginColor(ratiosData.profitability?.net_margin)">
                  {{ ratiosData.profitability?.net_margin || 0 }}%
                </span>
              </div>
              <div class="flex justify-between items-center">
                <span class="text-sm text-gray-600">Return on Assets</span>
                <span class="font-semibold" :class="getMarginColor(ratiosData.profitability?.roa)">
                  {{ ratiosData.profitability?.roa || 0 }}%
                </span>
              </div>
              <div class="flex justify-between items-center pt-2 border-t">
                <span class="text-sm text-gray-600">Return on Equity</span>
                <span class="font-semibold" :class="getMarginColor(ratiosData.profitability?.roe)">
                  {{ ratiosData.profitability?.roe || 0 }}%
                </span>
              </div>
            </div>
          </div>

          <!-- Efficiency Ratios -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <div class="flex items-center gap-2 mb-4">
              <div class="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                <svg class="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
              </div>
              <h3 class="text-lg font-semibold text-gray-900">Efficiency</h3>
            </div>
            <div class="space-y-3">
              <div class="flex justify-between items-center">
                <span class="text-sm text-gray-600">Days Sales Outstanding</span>
                <span class="font-semibold" :class="getDSOColor(ratiosData.efficiency?.dso)">
                  {{ ratiosData.efficiency?.dso || 0 }} days
                </span>
              </div>
              <div class="flex justify-between items-center">
                <span class="text-sm text-gray-600">Days Payable Outstanding</span>
                <span class="font-semibold text-gray-900">
                  {{ ratiosData.efficiency?.dpo || 0 }} days
                </span>
              </div>
              <div class="flex justify-between items-center">
                <span class="text-sm text-gray-600">Cash Conversion Cycle</span>
                <span class="font-semibold" :class="(ratiosData.efficiency?.cash_conversion_cycle || 0) <= 30 ? 'text-green-600' : 'text-amber-600'">
                  {{ ratiosData.efficiency?.cash_conversion_cycle || 0 }} days
                </span>
              </div>
              <div class="flex justify-between items-center pt-2 border-t">
                <span class="text-sm text-gray-600">Asset Turnover</span>
                <span class="font-semibold text-gray-900">
                  {{ ratiosData.efficiency?.asset_turnover || 0 }}x
                </span>
              </div>
            </div>
          </div>

          <!-- Leverage Ratios -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <div class="flex items-center gap-2 mb-4">
              <div class="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
                <svg class="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3"/>
                </svg>
              </div>
              <h3 class="text-lg font-semibold text-gray-900">Leverage</h3>
            </div>
            <div class="space-y-3">
              <div class="flex justify-between items-center">
                <span class="text-sm text-gray-600">Debt Ratio</span>
                <span class="font-semibold" :class="getDebtColor(ratiosData.leverage?.debt_ratio)">
                  {{ ratiosData.leverage?.debt_ratio || 0 }}%
                </span>
              </div>
              <div class="flex justify-between items-center">
                <span class="text-sm text-gray-600">Debt to Equity</span>
                <span class="font-semibold" :class="getDebtToEquityColor(ratiosData.leverage?.debt_to_equity)">
                  {{ ratiosData.leverage?.debt_to_equity || 'N/A' }}
                </span>
              </div>
              <div class="flex justify-between items-center pt-2 border-t">
                <span class="text-sm text-gray-600">Equity Ratio</span>
                <span class="font-semibold" :class="parseFloat(ratiosData.leverage?.equity_ratio || 0) >= 50 ? 'text-green-600' : 'text-amber-600'">
                  {{ ratiosData.leverage?.equity_ratio || 0 }}%
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Ratio Benchmarks & Health Score -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- Financial Health Score -->
          <div class="bg-white rounded-lg shadow-sm p-6 border">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Financial Health Score</h3>
            <div class="flex items-center justify-center mb-4">
              <div class="relative w-32 h-32">
                <svg class="w-full h-full transform -rotate-90">
                  <circle cx="64" cy="64" r="56" stroke="#e5e7eb" stroke-width="12" fill="none"/>
                  <circle cx="64" cy="64" r="56" :stroke="getHealthScoreColor(financialHealthScore)"
                          stroke-width="12" fill="none" stroke-linecap="round"
                          :stroke-dasharray="`${financialHealthScore * 3.52} 352`"/>
                </svg>
                <div class="absolute inset-0 flex items-center justify-center">
                  <span class="text-3xl font-bold" :class="getHealthScoreTextColor(financialHealthScore)">
                    {{ financialHealthScore }}
                  </span>
                </div>
              </div>
            </div>
            <div class="text-center">
              <span class="text-lg font-medium" :class="getHealthScoreTextColor(financialHealthScore)">
                {{ getHealthScoreLabel(financialHealthScore) }}
              </span>
              <p class="text-sm text-gray-500 mt-1">Based on key financial ratios</p>
            </div>
          </div>

          <!-- Key Ratio Benchmarks -->
          <div class="bg-white rounded-lg shadow-sm p-6 border lg:col-span-2">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Ratio Benchmarks</h3>
            <div class="space-y-4">
              <div class="flex items-center gap-4">
                <span class="w-32 text-sm text-gray-600">Current Ratio</span>
                <div class="flex-1 bg-gray-100 rounded-full h-3 overflow-hidden">
                  <div class="h-full rounded-full transition-all duration-500"
                       :class="getRatioBenchmarkClass('current', ratiosData.liquidity?.current_ratio)"
                       :style="{ width: `${getRatioBenchmarkWidth('current', ratiosData.liquidity?.current_ratio)}%` }">
                  </div>
                </div>
                <span class="w-20 text-right text-sm font-medium">{{ ratiosData.liquidity?.current_ratio || 'N/A' }}</span>
              </div>
              <div class="flex items-center gap-4">
                <span class="w-32 text-sm text-gray-600">Net Margin</span>
                <div class="flex-1 bg-gray-100 rounded-full h-3 overflow-hidden">
                  <div class="h-full rounded-full transition-all duration-500"
                       :class="getRatioBenchmarkClass('margin', ratiosData.profitability?.net_margin)"
                       :style="{ width: `${Math.min(100, Math.max(0, (ratiosData.profitability?.net_margin || 0) * 2))}%` }">
                  </div>
                </div>
                <span class="w-20 text-right text-sm font-medium">{{ ratiosData.profitability?.net_margin || 0 }}%</span>
              </div>
              <div class="flex items-center gap-4">
                <span class="w-32 text-sm text-gray-600">DSO</span>
                <div class="flex-1 bg-gray-100 rounded-full h-3 overflow-hidden">
                  <div class="h-full rounded-full transition-all duration-500"
                       :class="getRatioBenchmarkClass('dso', ratiosData.efficiency?.dso)"
                       :style="{ width: `${Math.min(100, Math.max(0, 100 - (ratiosData.efficiency?.dso || 0)))}%` }">
                  </div>
                </div>
                <span class="w-20 text-right text-sm font-medium">{{ ratiosData.efficiency?.dso || 0 }} days</span>
              </div>
              <div class="flex items-center gap-4">
                <span class="w-32 text-sm text-gray-600">Debt Ratio</span>
                <div class="flex-1 bg-gray-100 rounded-full h-3 overflow-hidden">
                  <div class="h-full rounded-full transition-all duration-500"
                       :class="getRatioBenchmarkClass('debt', ratiosData.leverage?.debt_ratio)"
                       :style="{ width: `${Math.min(100, 100 - parseFloat(ratiosData.leverage?.debt_ratio || 0))}%` }">
                  </div>
                </div>
                <span class="w-20 text-right text-sm font-medium">{{ ratiosData.leverage?.debt_ratio || 0 }}%</span>
              </div>
            </div>
            <div class="mt-4 flex items-center gap-4 text-xs text-gray-500">
              <span class="flex items-center gap-1"><span class="w-3 h-3 bg-green-500 rounded-full"></span> Healthy</span>
              <span class="flex items-center gap-1"><span class="w-3 h-3 bg-amber-500 rounded-full"></span> Caution</span>
              <span class="flex items-center gap-1"><span class="w-3 h-3 bg-red-500 rounded-full"></span> At Risk</span>
            </div>
          </div>
        </div>

        <!-- Monthly Trend Analysis (Transposed: Months as Columns) -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Monthly Performance Trends</h3>
          <div class="overflow-x-auto">
            <table class="min-w-full">
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase sticky left-0 bg-gray-50">Metric</th>
                  <th v-for="month in trendMonths" :key="month.period"
                      class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase whitespace-nowrap">
                    {{ formatPeriod(month.period) }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <!-- Revenue Row -->
                <tr>
                  <td class="px-4 py-3 font-medium text-gray-900 sticky left-0 bg-white">Revenue</td>
                  <td v-for="month in trendMonths" :key="'rev-'+month.period" 
                      class="px-4 py-3 text-right text-sm text-gray-900 whitespace-nowrap">
                    {{ formatCompactCurrency(month.revenue) }}
                  </td>
                </tr>
                <!-- Expenses Row -->
                <tr>
                  <td class="px-4 py-3 font-medium text-gray-900 sticky left-0 bg-white">Expenses</td>
                  <td v-for="month in trendMonths" :key="'exp-'+month.period" 
                      class="px-4 py-3 text-right text-sm text-gray-600 whitespace-nowrap">
                    {{ formatCompactCurrency(month.expenses || (month.revenue - month.profit)) }}
                  </td>
                </tr>
                <!-- Net Profit Row -->
                <tr>
                  <td class="px-4 py-3 font-medium text-gray-900 sticky left-0 bg-white">Net Profit</td>
                  <td v-for="month in trendMonths" :key="'profit-'+month.period" 
                      class="px-4 py-3 text-right text-sm font-medium whitespace-nowrap"
                      :class="month.profit >= 0 ? 'text-green-600' : 'text-red-600'">
                    {{ formatCompactCurrency(month.profit) }}
                  </td>
                </tr>
                <!-- Margin Row -->
                <tr>
                  <td class="px-4 py-3 font-medium text-gray-900 sticky left-0 bg-white">Margin %</td>
                  <td v-for="month in trendMonths" :key="'margin-'+month.period" 
                      class="px-4 py-3 text-right text-sm whitespace-nowrap">
                    <span :class="getMarginColor(getMonthMargin(month))">
                      {{ getMonthMargin(month) }}%
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="!ratiosData.trends?.length" class="text-center py-8 text-gray-500">
            No trend data available
          </div>
        </div>
      </div>

      <!-- Tab 6: Budget Analysis -->
      <div v-if="activeTab === 'budget'" class="space-y-6">
        <div v-if="budgetData.status === 'no_budgets'" class="bg-amber-50 border border-amber-200 rounded-lg p-6">
          <h3 class="text-lg font-semibold text-amber-800 mb-2">No Budget Data Available</h3>
          <p class="text-amber-700">{{ budgetData.message }}</p>
          <p class="text-sm text-amber-600 mt-2">Configure budgets in ERPNext to enable budget variance analysis.</p>
        </div>
        
        <div v-else>
          <!-- Budget Summary -->
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div class="bg-white rounded-lg shadow-sm p-4 border">
              <div class="text-sm text-gray-500">Budget Variance</div>
              <div class="text-xl font-bold" :class="budgetData.overall_variance >= 0 ? 'text-green-600' : 'text-red-600'">
                {{ formatCurrency(budgetData.overall_variance) }}
              </div>
              <div class="text-sm text-gray-500">{{ budgetData.variance_pct }}% of budget</div>
            </div>
            <div class="bg-white rounded-lg shadow-sm p-4 border">
              <div class="text-sm text-gray-500">Under Budget</div>
              <div class="text-xl font-bold text-green-600">{{ budgetData.under_budget_count }}</div>
              <div class="text-sm text-gray-500">accounts</div>
            </div>
            <div class="bg-white rounded-lg shadow-sm p-4 border">
              <div class="text-sm text-gray-500">Over Budget</div>
              <div class="text-xl font-bold text-red-600">{{ budgetData.over_budget_count }}</div>
              <div class="text-sm text-gray-500">accounts</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 7: KRA Tax -->
      <div v-if="activeTab === 'kra'" class="space-y-6">
        <!-- Tax Summary -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">VAT Output (16%)</div>
            <div class="text-xl font-bold text-gray-900">{{ formatCurrency(kraData.output_vat_mtd) }}</div>
            <div class="text-sm text-gray-500">This month</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">VAT Input (16%)</div>
            <div class="text-xl font-bold text-gray-900">{{ formatCurrency(kraData.input_vat_mtd) }}</div>
            <div class="text-sm text-gray-500">This month</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">VAT Withholding (2%)</div>
            <div class="text-xl font-bold text-gray-900">{{ formatCurrency(kraData.vat_wht_mtd) }}</div>
            <div class="text-sm text-gray-500">This month</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Net VAT Payable</div>
            <div class="text-xl font-bold" :class="kraData.net_vat_payable >= 0 ? 'text-red-600' : 'text-green-600'">
              {{ formatCurrency(kraData.net_vat_payable) }}
            </div>
            <div class="text-sm text-gray-500">This month</div>
          </div>
        </div>

        <!-- VAT Filing Alert -->
        <div v-if="kraData.days_to_deadline <= 5" 
             :class="kraData.days_to_deadline <= 0 ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'"
             class="border rounded-lg p-4">
          <div class="flex items-center gap-2">
            <span class="text-2xl">⚠️</span>
            <div>
              <div class="font-semibold" :class="kraData.days_to_deadline <= 0 ? 'text-red-800' : 'text-amber-800'">
                {{ kraData.days_to_deadline <= 0 ? 'VAT Filing Overdue!' : 'VAT Filing Deadline Approaching' }}
              </div>
              <div :class="kraData.days_to_deadline <= 0 ? 'text-red-600' : 'text-amber-600'">
                Due: {{ formatDate(kraData.vat_due_date) }} 
                ({{ kraData.days_to_deadline <= 0 ? `${Math.abs(kraData.days_to_deadline)} days overdue` : `${kraData.days_to_deadline} days remaining` }})
              </div>
            </div>
          </div>
        </div>

        <!-- Monthly VAT Trend (Transposed: Months as Columns) -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Monthly VAT Summary</h3>
          <div class="overflow-x-auto">
            <table class="min-w-full">
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase sticky left-0 bg-gray-50">Metric</th>
                  <th v-for="month in vatMonths" :key="month.period"
                      class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase whitespace-nowrap">
                    {{ formatPeriod(month.period) }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <!-- Output VAT Row -->
                <tr>
                  <td class="px-4 py-3 font-medium text-gray-900 sticky left-0 bg-white">Output VAT</td>
                  <td v-for="month in vatMonths" :key="'out-'+month.period" 
                      class="px-4 py-3 text-right text-sm text-gray-900 whitespace-nowrap">
                    {{ formatCompactCurrency(month.output_vat) }}
                  </td>
                </tr>
                <!-- Input VAT Row -->
                <tr>
                  <td class="px-4 py-3 font-medium text-gray-900 sticky left-0 bg-white">Input VAT</td>
                  <td v-for="month in vatMonths" :key="'in-'+month.period" 
                      class="px-4 py-3 text-right text-sm text-gray-600 whitespace-nowrap">
                    {{ formatCompactCurrency(month.input_vat) }}
                  </td>
                </tr>
                <!-- Net VAT Row -->
                <tr>
                  <td class="px-4 py-3 font-medium text-gray-900 sticky left-0 bg-white">Net VAT</td>
                  <td v-for="month in vatMonths" :key="'net-'+month.period" 
                      class="px-4 py-3 text-right text-sm font-medium whitespace-nowrap"
                      :class="month.net_vat >= 0 ? 'text-red-600' : 'text-green-600'">
                    {{ formatCompactCurrency(month.net_vat) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- VAT Forecast -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">3-Month VAT Forecast</h3>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div v-for="forecast in kraData.forecast" :key="forecast.period"
                 class="p-4 rounded-lg bg-blue-50">
              <div class="font-medium text-gray-900">{{ formatPeriod(forecast.period) }}</div>
              <div class="text-lg font-bold text-blue-600 mt-2">{{ formatCurrency(forecast.predicted_net_vat) }}</div>
              <div class="text-sm text-gray-500">Predicted Net VAT</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 8: Forex Exposure -->
      <div v-if="activeTab === 'forex'" class="space-y-6">
        <!-- Forex Summary -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Net Forex Exposure</div>
            <div class="text-xl font-bold" :class="(forexData.net_exposure_base || 0) >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ formatCurrency(Math.abs(forexData.net_exposure_base || 0)) }}
            </div>
            <div class="text-sm" :class="(forexData.net_exposure_base || 0) >= 0 ? 'text-green-500' : 'text-red-500'">
              {{ (forexData.net_exposure_base || 0) >= 0 ? 'Long (Net Receivable)' : 'Short (Net Payable)' }}
            </div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Foreign Receivables</div>
            <div class="text-xl font-bold text-green-600">{{ formatCurrency(forexData.total_receivable_base || 0) }}</div>
            <div class="text-sm text-gray-500">In base currency ({{ baseCurrency }})</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Foreign Payables</div>
            <div class="text-xl font-bold text-red-600">{{ formatCurrency(forexData.total_payable_base || 0) }}</div>
            <div class="text-sm text-gray-500">In base currency ({{ baseCurrency }})</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm text-gray-500">Unrealized P&L</div>
            <div class="text-xl font-bold" :class="(forexData.net_unrealized || 0) >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ formatCurrency(forexData.net_unrealized || 0) }}
            </div>
            <div class="text-sm text-gray-500">From rate changes</div>
          </div>
        </div>

        <!-- Exposure by Currency -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Forex Exposure by Currency</h3>
          <div class="overflow-x-auto">
            <table class="min-w-full" v-if="forexData.exposure_summary?.length">
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Currency</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Receivable</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Payable</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Net Exposure</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Rate</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Value ({{ baseCurrency }})</th>
                  <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Position</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <tr v-for="exp in forexData.exposure_summary" :key="exp.currency">
                  <td class="px-4 py-3 font-medium text-gray-900">{{ exp.currency }}</td>
                  <td class="px-4 py-3 text-right text-sm text-green-600">
                    {{ formatForeignCurrency(exp.receivable, exp.currency) }}
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-red-600">
                    {{ formatForeignCurrency(exp.payable, exp.currency) }}
                  </td>
                  <td class="px-4 py-3 text-right text-sm font-medium" :class="exp.net_exposure >= 0 ? 'text-green-600' : 'text-red-600'">
                    {{ formatForeignCurrency(exp.net_exposure, exp.currency) }}
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-gray-600">{{ exp.current_rate }}</td>
                  <td class="px-4 py-3 text-right text-sm font-bold" :class="exp.net_exposure_base >= 0 ? 'text-green-600' : 'text-red-600'">
                    {{ formatCurrency(exp.net_exposure_base) }}
                  </td>
                  <td class="px-4 py-3 text-center">
                    <span :class="exp.position === 'Long' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'"
                          class="px-2 py-1 text-xs font-medium rounded-full">
                      {{ exp.position }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="text-center py-8 text-gray-500">
              No foreign currency exposure
            </div>
          </div>
        </div>

        <!-- At-Risk Invoices -->
        <div class="bg-white rounded-lg shadow-sm p-6 border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">At-Risk Foreign Currency Invoices ({{ forexData.at_risk_invoices?.length || 0 }})</h3>
          <div class="overflow-x-auto">
            <table class="min-w-full" v-if="forexData.at_risk_invoices?.length">
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Invoice</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Party</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Currency</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Outstanding</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Rate</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Due Date</th>
                  <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <tr v-for="invoice in forexData.at_risk_invoices" :key="invoice.name">
                  <td class="px-4 py-3 text-sm">
                    <span :class="invoice.doctype === 'Sales Invoice' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'"
                          class="px-2 py-1 text-xs font-medium rounded-full">
                      {{ invoice.doctype === 'Sales Invoice' ? 'AR' : 'AP' }}
                    </span>
                  </td>
                  <td class="px-4 py-3 font-medium text-blue-600 cursor-pointer hover:underline"
                      @click="openDocument(invoice.doctype, invoice.name)">
                    {{ invoice.name }}
                  </td>
                  <td class="px-4 py-3 text-sm text-gray-900">{{ invoice.party }}</td>
                  <td class="px-4 py-3 text-sm font-medium text-gray-600">{{ invoice.currency }}</td>
                  <td class="px-4 py-3 text-right text-sm font-medium text-gray-900">
                    {{ formatForeignCurrency(invoice.outstanding_amount, invoice.currency) }}
                  </td>
                  <td class="px-4 py-3 text-right text-sm text-gray-600">{{ invoice.conversion_rate }}</td>
                  <td class="px-4 py-3 text-sm text-gray-600">{{ formatDate(invoice.due_date) }}</td>
                  <td class="px-4 py-3 text-center">
                    <span :class="invoice.days_to_due < 0 ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'"
                          class="px-2 py-1 text-xs font-medium rounded-full">
                      {{ invoice.days_to_due < 0 ? `${Math.abs(invoice.days_to_due)}d overdue` : `${invoice.days_to_due}d to due` }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="text-center py-8 text-gray-500">
              No at-risk foreign currency invoices
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- AI Chat Button -->
    <DashboardChatButton
      dashboard-type="Financial"
      :dashboard-context="chatContext"
      @navigate-dashboard="handleDashboardRedirect"
    />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FinancialIntelligence' })
import { ref, computed, onMounted, watch } from 'vue'
import { Button, createResource } from 'frappe-ui'
import { useRouter } from 'vue-router'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'

const router = useRouter()

const activeTab = ref('overview')
const loading = ref(false)
const lastUpdated = ref<string | null>(null)
const dateFilter = ref('12m')
const baseCurrency = ref('KES')

const tabs = [
  { label: 'Overview', value: 'overview' },
  { label: 'Cash Flow', value: 'cashflow' },
  { label: 'Receivables', value: 'receivables' },
  { label: 'Payables', value: 'payables' },
  { label: 'Ratios & Trends', value: 'ratios' },
  { label: 'Budget Analysis', value: 'budget' },
  { label: 'KRA Tax', value: 'kra' },
  { label: 'Forex Exposure', value: 'forex' }
]

// Data refs
const overviewData = ref<any>({})
const cashFlowData = ref<any>({})
const receivablesData = ref<any>({})
const payablesData = ref<any>({})
const ratiosData = ref<any>({})
const budgetData = ref<any>({})
const kraData = ref<any>({})
const forexData = ref<any>({})

// Summary computed - matches API field names
const summary = computed(() => ({
  netProfit: overviewData.value.ytd_profit || 0,
  profitMargin: overviewData.value.net_margin || 0,
  cashPosition: cashFlowData.value.total_cash || 0,
  cashRunway: Math.round((cashFlowData.value.runway_months || 0) * 30),
  outstandingAR: receivablesData.value.total_outstanding || 0,
  avgDSO: Math.round(receivablesData.value.current_dso || 0),
  outstandingAP: payablesData.value.total_outstanding || 0,
  avgDPO: Math.round(payablesData.value.current_dpo || 0),
  netVATPayable: kraData.value.net_vat_payable || 0,
  forexExposure: Math.abs(forexData.value.net_exposure_base || 0),
  forexCurrencies: forexData.value.exposure_summary?.length || 0
}))

// API Resources
const financialResource = createResource({
  url: 'insights.api.ml.financial_intelligence',
  auto: false,
  onSuccess(data: any) {
    if (data.status === 'success') {
      overviewData.value = data.overview || {}
      cashFlowData.value = data.cash_flow || {}
      receivablesData.value = data.receivables || {}
      payablesData.value = data.payables || {}
      // Use backend ratios if available, otherwise compute from data
      const backendRatios = data.ratios || {}
      // Merge backend ratios with fallback values and ensure trends are included
      ratiosData.value = {
        ...computeRatios(data),
        ...backendRatios,
        // Ensure trends are always available from either source
        trends: backendRatios.trends || data.overview?.monthly_trend || []
      }
      budgetData.value = data.budget || {}
      kraData.value = data.kra_tax || {}
      forexData.value = data.forex || {}
      lastUpdated.value = data.generated_at
      if (data.base_currency) {
        baseCurrency.value = data.base_currency
      }
    }
    loading.value = false
  },
  onError(err: any) {
    console.error('Financial Intelligence error:', err)
    loading.value = false
  }
})

// Compute financial ratios from available data
const computeRatios = (data: any) => {
  const overview = data.overview || {}
  const cashFlow = data.cash_flow || {}
  const receivables = data.receivables || {}
  const payables = data.payables || {}
  
  const totalAssets = (cashFlow.total_cash || 0) + (receivables.total_outstanding || 0)
  const totalLiabilities = payables.total_outstanding || 0
  const equity = totalAssets - totalLiabilities
  const revenue = overview.ytd_revenue || 1
  const netProfit = overview.ytd_profit || 0
  const grossProfit = overview.ytd_gross_profit || overview.ytd_profit || 0
  
  return {
    liquidity: {
      current_ratio: totalLiabilities > 0 ? (totalAssets / totalLiabilities).toFixed(2) : 'N/A',
      quick_ratio: totalLiabilities > 0 ? ((cashFlow.total_cash || 0) + (receivables.total_outstanding || 0)) / totalLiabilities : 'N/A',
      cash_ratio: totalLiabilities > 0 ? ((cashFlow.total_cash || 0) / totalLiabilities).toFixed(2) : 'N/A',
      working_capital: totalAssets - totalLiabilities
    },
    profitability: {
      gross_margin: revenue > 0 ? ((grossProfit / revenue) * 100).toFixed(1) : 0,
      net_margin: overview.net_margin || 0,
      roa: totalAssets > 0 ? ((netProfit / totalAssets) * 100).toFixed(1) : 0,
      roe: equity > 0 ? ((netProfit / equity) * 100).toFixed(1) : 0
    },
    efficiency: {
      dso: Math.round(receivables.current_dso || 0),
      dpo: Math.round(payables.current_dpo || 0),
      cash_conversion_cycle: Math.round((receivables.current_dso || 0) - (payables.current_dpo || 0)),
      asset_turnover: totalAssets > 0 ? (revenue / totalAssets).toFixed(2) : 0
    },
    leverage: {
      debt_ratio: totalAssets > 0 ? ((totalLiabilities / totalAssets) * 100).toFixed(1) : 0,
      debt_to_equity: equity > 0 ? (totalLiabilities / equity).toFixed(2) : 'N/A',
      equity_ratio: totalAssets > 0 ? ((equity / totalAssets) * 100).toFixed(1) : 0
    },
    trends: overview.monthly_trend || []
  }
}

const refreshData = () => {
  loading.value = true
  financialResource.submit({ refresh: true, date_filter: dateFilter.value })
}

onMounted(() => {
  loading.value = true
  financialResource.submit({ refresh: false, date_filter: dateFilter.value })
})

// Watch for date filter changes
watch(dateFilter, () => {
  loading.value = true
  financialResource.submit({ refresh: false, date_filter: dateFilter.value })
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

const formatForeignCurrency = (value: number | undefined, currency: string) => {
  if (value === undefined || value === null) return `${currency} 0`
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
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
const getRevenueBarWidth = (revenue: number) => {
  const maxRevenue = Math.max(...(overviewData.value.monthly_revenue?.map((m: any) => m.revenue) || [1]))
  return Math.max(10, (revenue / maxRevenue) * 100)
}

const getCashFlowBarWidth = (amount: number) => {
  const maxAmount = Math.max(...(cashFlowData.value.monthly_cash_flow?.map((m: any) => Math.abs(m.net_cash_flow)) || [1]))
  return Math.max(10, (Math.abs(amount) / maxAmount) * 100)
}

const getInflowBarWidth = (amount: number) => {
  const maxAmount = Math.max(...(cashFlowData.value.monthly_inflows?.map((m: any) => m.amount) || [1]))
  return Math.max(10, (amount / maxAmount) * 100)
}

const getVATBarWidth = (amount: number) => {
  const maxAmount = Math.max(...(kraData.value.monthly_vat?.map((m: any) => m.vat_collected) || [1]))
  return Math.max(10, (amount / maxAmount) * 100)
}

// Get 90+ days overdue from aging buckets
const get90PlusOverdue = (buckets: any[] | undefined) => {
  if (!buckets) return 0
  const bucket90Plus = buckets.find((b: any) => b.bucket === '90+ Days' || b.bucket === '90+')
  return bucket90Plus?.amount || 0
}

// Days overdue badge color
const getDaysBadge = (days: number) => {
  if (days > 90) return 'bg-red-100 text-red-700'
  if (days > 60) return 'bg-orange-100 text-orange-700'
  if (days > 30) return 'bg-amber-100 text-amber-700'
  return 'bg-gray-100 text-gray-700'
}

// Color helpers
const getVarianceBadge = (pct: number) => {
  if (pct <= -10) return 'bg-red-100 text-red-700'
  if (pct >= 10) return 'bg-green-100 text-green-700'
  return 'bg-amber-100 text-amber-700'
}

const openDocument = (doctype: string, name: string) => {
  window.open(`/app/${doctype.toLowerCase().replace(/ /g, '-')}/${name}`, '_blank')
}

// Financial ratio color helpers
const getRatioColor = (type: string, value: any) => {
  if (value === 'N/A' || value === undefined) return 'text-gray-500'
  const num = parseFloat(value)
  if (type === 'current') {
    if (num >= 2) return 'text-green-600'
    if (num >= 1) return 'text-amber-600'
    return 'text-red-600'
  }
  if (type === 'quick') {
    if (num >= 1) return 'text-green-600'
    if (num >= 0.5) return 'text-amber-600'
    return 'text-red-600'
  }
  if (type === 'cash') {
    if (num >= 0.5) return 'text-green-600'
    if (num >= 0.2) return 'text-amber-600'
    return 'text-red-600'
  }
  return 'text-gray-900'
}

const getMarginColor = (value: any) => {
  const num = parseFloat(value) || 0
  if (num >= 15) return 'text-green-600'
  if (num >= 5) return 'text-amber-600'
  if (num >= 0) return 'text-gray-600'
  return 'text-red-600'
}

const getDSOColor = (value: number) => {
  if (value <= 30) return 'text-green-600'
  if (value <= 60) return 'text-amber-600'
  return 'text-red-600'
}

const getDebtColor = (value: any) => {
  const num = parseFloat(value) || 0
  if (num <= 30) return 'text-green-600'
  if (num <= 60) return 'text-amber-600'
  return 'text-red-600'
}

const getDebtToEquityColor = (value: any) => {
  if (value === 'N/A') return 'text-gray-500'
  const num = parseFloat(value) || 0
  if (num <= 1) return 'text-green-600'
  if (num <= 2) return 'text-amber-600'
  return 'text-red-600'
}

// Financial Health Score (0-100)
const financialHealthScore = computed(() => {
  let score = 0
  const r = ratiosData.value
  
  // Liquidity (25 points)
  const currentRatio = parseFloat(r.liquidity?.current_ratio) || 0
  if (currentRatio >= 2) score += 25
  else if (currentRatio >= 1.5) score += 20
  else if (currentRatio >= 1) score += 15
  else score += currentRatio * 10
  
  // Profitability (25 points)
  const netMargin = parseFloat(r.profitability?.net_margin) || 0
  if (netMargin >= 15) score += 25
  else if (netMargin >= 10) score += 20
  else if (netMargin >= 5) score += 15
  else if (netMargin >= 0) score += netMargin * 2
  
  // Efficiency (25 points)
  const dso = r.efficiency?.dso || 0
  if (dso <= 30) score += 25
  else if (dso <= 45) score += 20
  else if (dso <= 60) score += 15
  else score += Math.max(0, 25 - (dso - 30) * 0.5)
  
  // Leverage (25 points)
  const debtRatio = parseFloat(r.leverage?.debt_ratio) || 0
  if (debtRatio <= 30) score += 25
  else if (debtRatio <= 50) score += 20
  else if (debtRatio <= 70) score += 10
  else score += 0
  
  return Math.round(Math.min(100, Math.max(0, score)))
})

const getHealthScoreColor = (score: number) => {
  if (score >= 75) return '#22c55e'
  if (score >= 50) return '#eab308'
  return '#ef4444'
}

const getHealthScoreTextColor = (score: number) => {
  if (score >= 75) return 'text-green-600'
  if (score >= 50) return 'text-amber-600'
  return 'text-red-600'
}

const getHealthScoreLabel = (score: number) => {
  if (score >= 75) return 'Excellent'
  if (score >= 60) return 'Good'
  if (score >= 50) return 'Fair'
  if (score >= 35) return 'Needs Improvement'
  return 'Critical'
}

const getRatioBenchmarkClass = (type: string, value: any) => {
  if (value === 'N/A' || value === undefined) return 'bg-gray-300'
  const num = parseFloat(value) || 0
  
  if (type === 'current') {
    if (num >= 1.5) return 'bg-green-500'
    if (num >= 1) return 'bg-amber-500'
    return 'bg-red-500'
  }
  if (type === 'margin') {
    if (num >= 10) return 'bg-green-500'
    if (num >= 5) return 'bg-amber-500'
    return 'bg-red-500'
  }
  if (type === 'dso') {
    if (num <= 45) return 'bg-green-500'
    if (num <= 60) return 'bg-amber-500'
    return 'bg-red-500'
  }
  if (type === 'debt') {
    if (num <= 40) return 'bg-green-500'
    if (num <= 60) return 'bg-amber-500'
    return 'bg-red-500'
  }
  return 'bg-gray-300'
}

const getRatioBenchmarkWidth = (type: string, value: any) => {
  if (value === 'N/A' || value === undefined) return 0
  const num = parseFloat(value) || 0
  
  if (type === 'current') {
    return Math.min(100, num * 33) // 3.0 = 100%
  }
  return Math.min(100, num * 20)
}

// Chat context for AI insights
const chatContext = computed(() => ({
  summary: summary.value,
  overview: overviewData.value,
  cashFlow: cashFlowData.value,
  receivables: receivablesData.value,
  payables: payablesData.value,
  ratios: ratiosData.value,
  financialHealthScore: financialHealthScore.value,
  budget: budgetData.value,
  kraTax: kraData.value,
  forex: forexData.value,
  activeTab: activeTab.value,
  lastUpdated: lastUpdated.value
}))

// Computed property for transposed Monthly Performance Trends table
const trendMonths = computed(() => {
  return ratiosData.value.trends?.slice(-12) || []
})

// Computed property for transposed Monthly VAT Summary table
const vatMonths = computed(() => {
  return kraData.value.monthly_trend?.slice(-6) || []
})

// Helper to get margin value
const getMonthMargin = (month: any) => {
  return month.margin || (month.revenue > 0 ? (month.profit / month.revenue * 100).toFixed(1) : 0)
}

// Format currency in compact form (e.g., 1.2M, 500K)
const formatCompactCurrency = (value: number | undefined) => {
  if (value === undefined || value === null) return `${baseCurrency.value} 0`
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absValue >= 1000000) {
    return `${sign}${baseCurrency.value} ${(absValue / 1000000).toFixed(1)}M`
  } else if (absValue >= 1000) {
    return `${sign}${baseCurrency.value} ${(absValue / 1000).toFixed(0)}K`
  }
  return `${sign}${baseCurrency.value} ${absValue.toFixed(0)}`
}

// Handle navigation to other dashboards from chat suggestions
function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    'Sales': '/sales-intelligence',
    'Risk': '/risk-intelligence',
    'Inventory': '/inventory-intelligence',
    'Procurement': '/procurement-intelligence',
    'Customer': '/customer-intelligence',
    'Financial': '/financial-intelligence'
  }
  if (routes[target]) {
    router.push(routes[target])
  }
}
</script>