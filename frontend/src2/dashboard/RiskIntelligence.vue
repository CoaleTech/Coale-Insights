<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <header class="bg-white border-b px-6 py-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Risk Intelligence & Analytics</h1>
        <p class="text-sm text-gray-500 mt-1">
          Comprehensive risk assessment with Prophet forecasting and early warning systems
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
        <div class="text-sm font-medium text-gray-500">Overall Risk Score</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ summary.overallScore }}/100
        </div>
        <div :class="getRiskColor(summary.overallRisk)" class="text-sm mt-1 font-medium">
          {{ summary.overallRisk }}
        </div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Credit Risk</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ summary.creditScore }}/100
        </div>
        <div :class="getRiskColor(summary.creditRisk)" class="text-sm mt-1 font-medium">
          {{ summary.creditRisk }}
        </div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Cash Flow Risk</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ summary.cashflowScore }}/100
        </div>
        <div :class="getRiskColor(summary.cashflowRisk)" class="text-sm mt-1 font-medium">
          {{ summary.cashflowRisk }}
        </div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Operational Risk</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ summary.operationalScore }}/100
        </div>
        <div :class="getRiskColor(summary.operationalRisk)" class="text-sm mt-1 font-medium">
          {{ summary.operationalRisk }}
        </div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Compliance Risk</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ summary.complianceScore }}/100
        </div>
        <div :class="getRiskColor(summary.complianceRisk)" class="text-sm mt-1 font-medium">
          {{ summary.complianceRisk }}
        </div>
      </div>
      
      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Active Alerts</div>
        <div class="text-2xl font-bold text-red-600 mt-1">
          {{ summary.activeAlerts }}
        </div>
        <div class="text-sm text-gray-500 mt-1">{{ summary.criticalAlerts }} critical</div>
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
        <!-- Active Alerts -->
        <div v-if="overviewData.alerts?.length" class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Active Risk Alerts</h3>
            <p class="text-sm text-gray-600 mt-1">{{ overviewData.alerts?.length }} alerts requiring attention</p>
          </div>
          <div class="p-6">
            <div class="space-y-3">
              <div v-for="(alert, index) in overviewData.alerts" :key="index" 
                   class="flex items-start gap-4 p-4 rounded-lg"
                   :class="getAlertClass(alert.severity)">
                <div class="flex-shrink-0">
                  <span v-if="alert.severity === 'high'" class="text-red-500 text-xl">⚠️</span>
                  <span v-else-if="alert.severity === 'medium'" class="text-yellow-500 text-xl">⚡</span>
                  <span v-else class="text-blue-500 text-xl">ℹ️</span>
                </div>
                <div class="flex-1">
                  <div class="font-medium text-gray-900">{{ alert.title }}</div>
                  <div class="text-sm text-gray-600 mt-1">{{ alert.description }}</div>
                  <div class="text-xs text-gray-500 mt-2">Action: {{ alert.action }}</div>
                </div>
                <span :class="getRiskBadgeClass(alert.severity === 'high' ? 'High' : alert.severity === 'medium' ? 'Medium' : 'Low')" 
                      class="px-2 py-1 rounded text-xs font-medium uppercase">
                  {{ alert.severity }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Risk Assessment Matrix Table -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Risk Assessment Matrix</h3>
            <p class="text-sm text-gray-600 mt-1">Impact vs Probability analysis for key business risks</p>
          </div>
          <div class="p-6">
            <div class="overflow-x-auto">
              <table class="w-full">
                <thead>
                  <tr class="border-b">
                    <th class="text-left py-2">Risk</th>
                    <th class="text-left py-2">Category</th>
                    <th class="text-center py-2">Probability</th>
                    <th class="text-center py-2">Impact</th>
                    <th class="text-center py-2">Risk Score</th>
                    <th class="text-center py-2">Level</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="risk in overviewData.risk_matrix" :key="risk.name" class="border-b hover:bg-gray-50">
                    <td class="py-3 font-medium">{{ risk.name }}</td>
                    <td class="py-3 text-gray-600">{{ risk.category }}</td>
                    <td class="py-3 text-center">
                      <div class="flex items-center justify-center gap-2">
                        <div class="w-16 bg-gray-200 rounded-full h-2">
                          <div class="bg-blue-500 h-2 rounded-full" :style="{ width: risk.probability + '%' }"></div>
                        </div>
                        <span class="text-sm">{{ risk.probability }}%</span>
                      </div>
                    </td>
                    <td class="py-3 text-center">
                      <div class="flex items-center justify-center gap-2">
                        <div class="w-16 bg-gray-200 rounded-full h-2">
                          <div class="bg-orange-500 h-2 rounded-full" :style="{ width: risk.impact + '%' }"></div>
                        </div>
                        <span class="text-sm">{{ risk.impact }}%</span>
                      </div>
                    </td>
                    <td class="py-3 text-center font-bold">{{ risk.risk_score?.toFixed(1) }}</td>
                    <td class="py-3 text-center">
                      <span :class="getRiskBadgeClass(risk.risk_category)" class="px-2 py-1 rounded text-xs font-medium">
                        {{ risk.risk_category }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Key Business Metrics -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Key Business Metrics</h3>
          </div>
          <div class="p-6">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div class="text-center p-6 bg-blue-50 rounded-lg">
                <div class="text-4xl font-bold text-blue-600">{{ formatNumber(overviewData.total_customers) }}</div>
                <div class="text-sm text-gray-600 mt-2">Total Customers</div>
              </div>
              <div class="text-center p-6 bg-green-50 rounded-lg">
                <div class="text-4xl font-bold text-green-600">{{ formatNumber(overviewData.total_suppliers) }}</div>
                <div class="text-sm text-gray-600 mt-2">Total Suppliers</div>
              </div>
              <div class="text-center p-6 bg-purple-50 rounded-lg">
                <div class="text-4xl font-bold text-purple-600">{{ formatNumber(overviewData.total_items) }}</div>
                <div class="text-sm text-gray-600 mt-2">Inventory Items</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Risk Breakdown Chart (Visual) -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Risk Component Breakdown</h3>
            <p class="text-sm text-gray-600 mt-1">Visual breakdown of risk scores by category</p>
          </div>
          <div class="p-6">
            <div class="space-y-4">
              <div class="flex items-center gap-4">
                <div class="w-32 text-sm font-medium text-gray-700">Credit Risk</div>
                <div class="flex-1 bg-gray-200 rounded-full h-4">
                  <div class="h-4 rounded-full transition-all" 
                       :class="summary.creditScore >= 60 ? 'bg-red-500' : summary.creditScore >= 40 ? 'bg-orange-500' : summary.creditScore >= 20 ? 'bg-yellow-500' : 'bg-green-500'"
                       :style="{ width: summary.creditScore + '%' }"></div>
                </div>
                <div class="w-20 text-right font-bold" :class="getRiskColor(summary.creditRisk)">
                  {{ summary.creditScore }}/100
                </div>
              </div>
              <div class="flex items-center gap-4">
                <div class="w-32 text-sm font-medium text-gray-700">Cash Flow Risk</div>
                <div class="flex-1 bg-gray-200 rounded-full h-4">
                  <div class="h-4 rounded-full transition-all" 
                       :class="summary.cashflowScore >= 60 ? 'bg-red-500' : summary.cashflowScore >= 40 ? 'bg-orange-500' : summary.cashflowScore >= 20 ? 'bg-yellow-500' : 'bg-green-500'"
                       :style="{ width: summary.cashflowScore + '%' }"></div>
                </div>
                <div class="w-20 text-right font-bold" :class="getRiskColor(summary.cashflowRisk)">
                  {{ summary.cashflowScore }}/100
                </div>
              </div>
              <div class="flex items-center gap-4">
                <div class="w-32 text-sm font-medium text-gray-700">Operational Risk</div>
                <div class="flex-1 bg-gray-200 rounded-full h-4">
                  <div class="h-4 rounded-full transition-all" 
                       :class="summary.operationalScore >= 60 ? 'bg-red-500' : summary.operationalScore >= 40 ? 'bg-orange-500' : summary.operationalScore >= 20 ? 'bg-yellow-500' : 'bg-green-500'"
                       :style="{ width: summary.operationalScore + '%' }"></div>
                </div>
                <div class="w-20 text-right font-bold" :class="getRiskColor(summary.operationalRisk)">
                  {{ summary.operationalScore }}/100
                </div>
              </div>
              <div class="flex items-center gap-4">
                <div class="w-32 text-sm font-medium text-gray-700">Compliance Risk</div>
                <div class="flex-1 bg-gray-200 rounded-full h-4">
                  <div class="h-4 rounded-full transition-all" 
                       :class="summary.complianceScore >= 60 ? 'bg-red-500' : summary.complianceScore >= 40 ? 'bg-orange-500' : summary.complianceScore >= 20 ? 'bg-yellow-500' : 'bg-green-500'"
                       :style="{ width: summary.complianceScore + '%' }"></div>
                </div>
                <div class="w-20 text-right font-bold" :class="getRiskColor(summary.complianceRisk)">
                  {{ summary.complianceScore }}/100
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 2: Credit Risk -->
      <div v-if="activeTab === 'credit'" class="space-y-6">
        <!-- Credit Summary Cards -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div
            class="bg-white rounded-lg shadow-sm p-4 border cursor-pointer hover:ring-2 hover:ring-blue-300 transition-shadow"
            @click="drillDown.open(RISK_ENDPOINT, 'Overdue Invoices', { metric: 'overdue_invoices' })"
          >
            <div class="text-sm font-medium text-gray-500">Total Outstanding</div>
            <div class="text-2xl font-bold text-gray-900 mt-1">{{ formatCurrency(creditData.total_outstanding) }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm font-medium text-gray-500">High Risk Customers</div>
            <div class="text-2xl font-bold text-red-600 mt-1">{{ creditData.high_risk_customers || 0 }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm font-medium text-gray-500">Average DSO</div>
            <div class="text-2xl font-bold text-gray-900 mt-1">{{ Math.round(creditData.avg_dso || 0) }} days</div>
          </div>
        </div>

        <!-- Aging Analysis -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Receivables Aging Analysis</h3>
          </div>
          <div class="p-6">
            <div class="grid grid-cols-5 gap-4">
              <div
                v-for="bucket in creditData.aging_analysis"
                :key="bucket.aging_bucket"
                class="text-center p-4 border rounded-lg cursor-pointer hover:ring-2 hover:ring-blue-300 transition-shadow"
                @click="drillDown.open(RISK_ENDPOINT, bucket.aging_bucket + ' Overdue', { metric: 'overdue_invoices' })"
              >
                <div class="text-sm font-medium text-gray-500">{{ bucket.aging_bucket }}</div>
                <div class="text-xl font-bold text-gray-900 mt-1">{{ formatCurrency(bucket.outstanding_amount) }}</div>
                <div class="text-xs text-gray-500 mt-1">{{ bucket.invoice_count }} invoices</div>
              </div>
            </div>
          </div>
        </div>

        <!-- High Risk Customers Table -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Customer Risk Scores</h3>
            <p class="text-sm text-gray-600 mt-1">Payment behavior analysis and default probability</p>
          </div>
          <div class="p-6">
            <div class="overflow-x-auto">
              <table class="w-full">
                <thead>
                  <tr class="border-b">
                    <th class="text-left py-2">Customer</th>
                    <th class="text-right py-2">Outstanding</th>
                    <th class="text-right py-2">Avg Overdue Days</th>
                    <th class="text-center py-2">Risk Category</th>
                    <th class="text-right py-2">Risk Score</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="customer in creditData.customer_risk_scores?.slice(0, 20)" :key="customer.customer" class="border-b hover:bg-gray-50">
                    <td class="py-2">{{ customer.customer_name }}</td>
                    <td class="py-2 text-right">{{ formatCurrency(customer.outstanding) }}</td>
                    <td class="py-2 text-right">{{ Math.round(customer.avg_overdue_days || 0) }}</td>
                    <td class="py-2 text-center">
                      <span :class="getRiskBadgeClass(customer.risk_category)" class="px-2 py-1 rounded text-xs font-medium">
                        {{ customer.risk_category }}
                      </span>
                    </td>
                    <td class="py-2 text-right font-medium">{{ customer.risk_score }}/100</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 3: Cash Flow Risk -->
      <div v-if="activeTab === 'cashflow'" class="space-y-6">
        <!-- Cash Flow Summary Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm font-medium text-gray-500">Current Cash Position</div>
            <div class="text-2xl font-bold text-green-600 mt-1">{{ formatCurrency(cashflowData.current_cash_position) }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm font-medium text-gray-500">Working Capital</div>
            <div class="text-2xl font-bold text-gray-900 mt-1">{{ formatCurrency(cashflowData.current_working_capital) }}</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm font-medium text-gray-500">Working Capital Ratio</div>
            <div class="text-2xl font-bold text-blue-600 mt-1">{{ cashflowData.working_capital_ratio }}x</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm font-medium text-gray-500">Top Customer Share</div>
            <div class="text-2xl font-bold text-orange-600 mt-1">{{ Math.round(cashflowData.top_customer_share || 0) }}%</div>
          </div>
        </div>

        <!-- Customer Concentration -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Revenue Concentration Analysis</h3>
            <p class="text-sm text-gray-600 mt-1">Top customers by revenue share</p>
          </div>
          <div class="p-6">
            <div class="space-y-3">
              <div v-for="customer in cashflowData.customer_concentration" :key="customer.customer" 
                   class="flex items-center justify-between p-3 bg-gray-50 rounded">
                <div>
                  <div class="font-medium">{{ customer.customer_name }}</div>
                  <div class="text-sm text-gray-500">{{ formatCurrency(customer.revenue) }}</div>
                </div>
                <div class="text-right">
                  <div class="text-lg font-bold" :class="customer.revenue_share > 30 ? 'text-red-600' : 'text-gray-900'">
                    {{ customer.revenue_share?.toFixed(1) }}%
                  </div>
                  <div v-if="customer.revenue_share > 30" class="text-xs text-red-500">High Concentration</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- DSO Trend -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">DSO Trend Analysis</h3>
          </div>
          <div class="p-6">
            <div class="grid grid-cols-5 gap-4">
              <div v-for="period in cashflowData.dso_trend" :key="period.period" 
                   class="text-center p-4 border rounded-lg">
                <div class="text-sm font-medium text-gray-500">{{ period.period }}</div>
                <div class="text-xl font-bold text-gray-900 mt-1">{{ Math.round(period.avg_dso || 0) }}</div>
                <div class="text-xs text-gray-500 mt-1">days DSO</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 4: Operational Risk -->
      <div v-if="activeTab === 'operational'" class="space-y-6">
        <!-- Process Metrics -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm font-medium text-gray-500">Invoice Error Rate</div>
            <div class="text-2xl font-bold text-gray-900 mt-1">{{ (operationalData.process_risks?.invoice_error_rate || 0).toFixed(2) }}%</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm font-medium text-gray-500">Avg Approval Time</div>
            <div class="text-2xl font-bold text-gray-900 mt-1">{{ operationalData.process_risks?.average_approval_time || 0 }} hrs</div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm font-medium text-gray-500">System Incidents</div>
            <div class="text-2xl font-bold text-gray-900 mt-1">{{ operationalData.process_risks?.system_downtime_incidents || 0 }}</div>
          </div>
        </div>

        <!-- Inventory Risk by Item Group -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Inventory Risk by Item Group</h3>
          </div>
          <div class="p-6">
            <div class="overflow-x-auto">
              <table class="w-full">
                <thead>
                  <tr class="border-b">
                    <th class="text-left py-2">Item Group</th>
                    <th class="text-right py-2">Total Items</th>
                    <th class="text-right py-2">Stockout Items</th>
                    <th class="text-right py-2">Stock Value</th>
                    <th class="text-center py-2">Risk Level</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="risk in operationalData.inventory_risks?.slice(0, 15)" :key="risk.item_group" class="border-b hover:bg-gray-50">
                    <td class="py-2">{{ risk.item_group }}</td>
                    <td class="py-2 text-right">{{ risk.total_items }}</td>
                    <td class="py-2 text-right text-red-600">{{ risk.stockout_items }}</td>
                    <td class="py-2 text-right">{{ formatCurrency(risk.stock_value) }}</td>
                    <td class="py-2 text-center">
                      <span :class="getRiskBadgeClass(risk.risk_category)" class="px-2 py-1 rounded text-xs font-medium">
                        {{ risk.risk_category }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Supplier Performance -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Supplier Reliability Analysis</h3>
          </div>
          <div class="p-6">
            <div class="overflow-x-auto">
              <table class="w-full">
                <thead>
                  <tr class="border-b">
                    <th class="text-left py-2">Supplier</th>
                    <th class="text-right py-2">Total Orders</th>
                    <th class="text-right py-2">Total Value</th>
                    <th class="text-right py-2">Avg Delay</th>
                    <th class="text-center py-2">Risk Score</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="supplier in operationalData.supplier_performance" :key="supplier.supplier" class="border-b hover:bg-gray-50">
                    <td class="py-2">{{ supplier.supplier_name }}</td>
                    <td class="py-2 text-right">{{ supplier.total_orders }}</td>
                    <td class="py-2 text-right">{{ formatCurrency(supplier.total_value) }}</td>
                    <td class="py-2 text-right">{{ Math.round(supplier.avg_delay_days || 0) }} days</td>
                    <td class="py-2 text-center">
                      <span :class="getRiskBadgeClass(supplier.risk_category)" class="px-2 py-1 rounded text-xs font-medium">
                        {{ supplier.reliability_risk_score }}/100
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 5: Compliance Risk -->
      <div v-if="activeTab === 'compliance'" class="space-y-6">
        <!-- KRA Status -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">KRA Compliance Status</h3>
          </div>
          <div class="p-6">
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div class="text-center p-4 border rounded-lg">
                <div class="text-2xl font-bold text-green-600">{{ complianceData.kra_status?.vat_filing_status || 'N/A' }}</div>
                <div class="text-sm text-gray-500 mt-1">VAT Filing Status</div>
              </div>
              <div class="text-center p-4 border rounded-lg">
                <div class="text-lg font-bold text-blue-600">{{ complianceData.kra_status?.last_filing_date || 'N/A' }}</div>
                <div class="text-sm text-gray-500 mt-1">Last Filing Date</div>
              </div>
              <div class="text-center p-4 border rounded-lg">
                <div class="text-lg font-bold text-orange-600">{{ complianceData.kra_status?.next_filing_due || 'N/A' }}</div>
                <div class="text-sm text-gray-500 mt-1">Next Filing Due</div>
              </div>
              <div class="text-center p-4 border rounded-lg">
                <div class="text-2xl font-bold" :class="(complianceData.kra_status?.outstanding_penalties || 0) > 0 ? 'text-red-600' : 'text-green-600'">
                  {{ formatCurrency(complianceData.kra_status?.outstanding_penalties || 0) }}
                </div>
                <div class="text-sm text-gray-500 mt-1">Outstanding Penalties</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Document Audit -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Document Completeness Audit</h3>
          </div>
          <div class="p-6">
            <div class="overflow-x-auto">
              <table class="w-full">
                <thead>
                  <tr class="border-b">
                    <th class="text-left py-2">Document Type</th>
                    <th class="text-right py-2">Total Documents</th>
                    <th class="text-right py-2">Incomplete</th>
                    <th class="text-right py-2">Completion Rate</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="doc in complianceData.document_audit" :key="doc.document_type" class="border-b hover:bg-gray-50">
                    <td class="py-2">{{ doc.document_type }}</td>
                    <td class="py-2 text-right">{{ doc.total_docs }}</td>
                    <td class="py-2 text-right text-red-600">{{ doc.incomplete_docs }}</td>
                    <td class="py-2 text-right">
                      <span :class="(doc.total_docs - doc.incomplete_docs) / doc.total_docs > 0.95 ? 'text-green-600' : 'text-orange-600'">
                        {{ ((doc.total_docs - doc.incomplete_docs) / doc.total_docs * 100).toFixed(1) }}%
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Licenses & Permits -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Licenses & Permits</h3>
          </div>
          <div class="p-6">
            <div class="space-y-3">
              <div v-for="license in complianceData.licenses" :key="license.license_type" 
                   class="flex items-center justify-between p-4 border rounded-lg">
                <div>
                  <div class="font-medium text-gray-900">{{ license.license_type }}</div>
                  <div class="text-sm text-gray-500">Expires: {{ license.expiry_date }}</div>
                </div>
                <div class="text-right">
                  <span :class="getRiskBadgeClass(license.risk_level)" class="px-2 py-1 rounded text-xs font-medium">
                    {{ license.status }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 6: Predictive Analytics -->
      <div v-if="activeTab === 'predictive'" class="space-y-6">
        <!-- Forecast Status -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm font-medium text-gray-500">Cash Flow Forecast</div>
            <div class="text-lg font-bold mt-1" :class="predictiveData.cash_flow_forecast?.status === 'success' ? 'text-green-600' : 'text-orange-600'">
              {{ predictiveData.cash_flow_forecast?.status || 'N/A' }}
            </div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm font-medium text-gray-500">Revenue Forecast</div>
            <div class="text-lg font-bold mt-1" :class="predictiveData.revenue_forecast?.status === 'success' ? 'text-green-600' : 'text-orange-600'">
              {{ predictiveData.revenue_forecast?.status || 'N/A' }}
            </div>
          </div>
          <div class="bg-white rounded-lg shadow-sm p-4 border">
            <div class="text-sm font-medium text-gray-500">Forecast Confidence</div>
            <div class="text-lg font-bold text-blue-600 mt-1">{{ predictiveData.forecast_confidence || 'Medium' }}</div>
          </div>
        </div>

        <!-- Anomaly Detection -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Detected Anomalies</h3>
            <p class="text-sm text-gray-600 mt-1">Unusual patterns in financial data</p>
          </div>
          <div class="p-6">
            <div v-if="predictiveData.anomalies?.length" class="space-y-3">
              <div v-for="(anomaly, index) in predictiveData.anomalies" :key="index" 
                   class="flex items-center justify-between p-4 rounded-lg"
                   :class="anomaly.severity === 'high' ? 'bg-red-50 border-l-4 border-red-400' : 'bg-yellow-50 border-l-4 border-yellow-400'">
                <div>
                  <div class="font-medium text-gray-900">{{ anomaly.type.replace(/_/g, ' ').toUpperCase() }}</div>
                  <div class="text-sm text-gray-600">{{ anomaly.description }}</div>
                </div>
                <div class="text-sm text-gray-500">{{ anomaly.date }}</div>
              </div>
            </div>
            <div v-else class="text-center text-gray-500 py-8">
              No anomalies detected in recent data
            </div>
          </div>
        </div>

        <!-- Early Warning Alerts -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Early Warning System</h3>
          </div>
          <div class="p-6">
            <div v-if="predictiveData.early_warnings?.length" class="space-y-4">
              <div v-for="(warning, index) in predictiveData.early_warnings" :key="index" 
                   class="flex items-center justify-between p-4 rounded-lg"
                   :class="getAlertClass(warning.severity)">
                <div>
                  <div class="font-medium">{{ warning.title }}</div>
                  <div class="text-sm opacity-75">{{ warning.description }}</div>
                  <div class="text-xs mt-1">Timeframe: {{ warning.timeframe }}</div>
                </div>
                <span :class="getRiskBadgeClass(warning.severity === 'critical' ? 'Critical' : warning.severity === 'high' ? 'High' : 'Medium')" 
                      class="px-2 py-1 rounded text-xs font-medium">
                  {{ warning.severity }}
                </span>
              </div>
            </div>
            <div v-else class="text-center text-gray-500 py-8">
              No early warnings at this time
            </div>
          </div>
        </div>

        <!-- Payment Risk Forecast -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-6 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Payment Delay Risk Forecast</h3>
          </div>
          <div class="p-6">
            <div v-if="predictiveData.payment_risk_forecast?.high_risk_customers?.length" class="overflow-x-auto">
              <table class="w-full">
                <thead>
                  <tr class="border-b">
                    <th class="text-left py-2">Customer</th>
                    <th class="text-right py-2">Avg Delay Days</th>
                    <th class="text-center py-2">Risk Category</th>
                    <th class="text-right py-2">Risk Score</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="customer in predictiveData.payment_risk_forecast.high_risk_customers" :key="customer.customer" class="border-b hover:bg-gray-50">
                    <td class="py-2">{{ customer.customer }}</td>
                    <td class="py-2 text-right">{{ Math.round(customer.avg_delay_days) }}</td>
                    <td class="py-2 text-center">
                      <span :class="getRiskBadgeClass(customer.risk_category)" class="px-2 py-1 rounded text-xs font-medium">
                        {{ customer.risk_category }}
                      </span>
                    </td>
                    <td class="py-2 text-right font-medium">{{ customer.risk_score }}/100</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-center text-gray-500 py-8">
              No high-risk payment patterns detected
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- AI Chat Button -->
    <DashboardChatButton
      dashboard-type="Risk"
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

<script setup>
defineOptions({ name: 'RiskIntelligence' })
import { ref, computed, onMounted, nextTick } from 'vue'
import { Button } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { useRouter } from 'vue-router'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'

const router = useRouter()

const drillDown = useDrillDown()
const RISK_ENDPOINT = 'insights.api.ml.risk.get_risk_detail'

const activeTab = ref('overview')
const loading = ref(false)
const lastUpdated = ref(null)

const tabs = [
  { label: 'Overview', value: 'overview' },
  { label: 'Credit Risk', value: 'credit' },
  { label: 'Cash Flow Risk', value: 'cashflow' },
  { label: 'Operational Risk', value: 'operational' },
  { label: 'Compliance Risk', value: 'compliance' },
  { label: 'Predictive Analytics', value: 'predictive' }
]

// Data refs
const overviewData = ref({})
const creditData = ref({})
const cashflowData = ref({})
const operationalData = ref({})
const complianceData = ref({})
const predictiveData = ref({})

// Summary computed - map from API response structure
const summary = computed(() => {
  const overview = overviewData.value
  const components = overview.risk_components || {}
  return {
    overallScore: overview.aggregate_risk_score || 0,
    overallRisk: overview.aggregate_risk_category || 'Low',
    creditScore: components.credit_risk?.score || 0,
    creditRisk: components.credit_risk?.category || 'Low',
    cashflowScore: components.cashflow_risk?.score || 0,
    cashflowRisk: components.cashflow_risk?.category || 'Low',
    operationalScore: components.operational_risk?.score || 0,
    operationalRisk: components.operational_risk?.category || 'Low',
    complianceScore: components.compliance_risk?.score || 0,
    complianceRisk: components.compliance_risk?.category || 'Low',
    activeAlerts: overview.alerts?.length || 0,
    criticalAlerts: overview.alerts?.filter(a => a.severity === 'critical').length || 0
  }
})

// Chat context for AI insights
const chatContext = computed(() => ({
  summary: summary.value,
  overview: overviewData.value,
  creditRisk: creditData.value,
  cashflowRisk: cashflowData.value,
  operationalRisk: operationalData.value,
  complianceRisk: complianceData.value,
  predictiveAnalytics: predictiveData.value,
  activeTab: activeTab.value,
  lastUpdated: lastUpdated.value
}))

// Handle navigation to other dashboards from chat suggestions
function handleDashboardRedirect(target) {
  const routes = {
    'Sales': '/sales-intelligence',
    'Inventory': '/inventory-intelligence',
    'Procurement': '/procurement-intelligence',
    'Financial': '/financial-intelligence',
    'Customer': '/customer-intelligence',
    'Risk': '/risk-intelligence'
  }
  if (routes[target]) {
    router.push(routes[target])
  }
}

// Methods
const baseCurrency = ref('KES')

const refreshData = async () => {
  loading.value = true
  try {
    const result = await apiCall('insights.api.ml.risk_intelligence', { refresh: true })

    // Map API response to data refs - API returns data directly, not under data.data
    overviewData.value = result.overview || {}
    creditData.value = result.credit_risk || {}
    cashflowData.value = result.cashflow_risk || {}
    operationalData.value = result.operational_risk || {}
    complianceData.value = result.compliance_risk || {}
    predictiveData.value = result.predictive_analytics || {}

    lastUpdated.value = result.generated_at || new Date().toISOString()
    if (result.base_currency) {
      baseCurrency.value = result.base_currency
    }

    // Render charts after data update
    await nextTick()
    renderCharts()
  } catch (error) {
    console.error('Failed to refresh risk intelligence data:', error)
  } finally {
    loading.value = false
  }
}

const formatCurrency = (value) => {
  if (!value) return `${baseCurrency.value} 0`
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: baseCurrency.value,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const formatNumber = (value) => {
  if (!value) return '0'
  return new Intl.NumberFormat('en-US').format(value)
}

const formatDate = (dateString) => {
  if (!dateString) return ''
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const getRiskColor = (riskLevel) => {
  switch (riskLevel?.toLowerCase()) {
    case 'low': return 'text-green-600'
    case 'medium': return 'text-yellow-600'
    case 'high': return 'text-orange-600'
    case 'critical': return 'text-red-600'
    default: return 'text-gray-600'
  }
}

const getRiskBadgeClass = (riskLevel) => {
  switch (riskLevel?.toLowerCase()) {
    case 'low': return 'bg-green-100 text-green-800'
    case 'medium': return 'bg-yellow-100 text-yellow-800'
    case 'high': return 'bg-orange-100 text-orange-800'
    case 'critical': return 'bg-red-100 text-red-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}

const getAlertClass = (severity) => {
  switch (severity?.toLowerCase()) {
    case 'critical': return 'bg-red-100 border border-red-200'
    case 'high': return 'bg-orange-100 border border-orange-200'
    case 'medium': return 'bg-yellow-100 border border-yellow-200'
    default: return 'bg-blue-100 border border-blue-200'
  }
}

const getAlertIcon = (severity) => {
  switch (severity?.toLowerCase()) {
    case 'critical': return 'text-red-600'
    case 'high': return 'text-orange-600'
    case 'medium': return 'text-yellow-600'
    default: return 'text-blue-600'
  }
}

const renderCharts = () => {
  // Implementation would use Chart.js or similar for visualizations
  // This is a placeholder for the chart rendering logic
  console.log('Rendering risk intelligence charts...')
}

// Initialize data on component mount
onMounted(async () => {
  await refreshData()
})
</script>

<style scoped>
/* Custom styles for the Risk Intelligence dashboard */
</style>