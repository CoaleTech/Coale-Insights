<script setup>
import { computed } from 'vue'

const props = defineProps({
  costAnalytics: { type: Object, default: () => ({}) },
  kpiData: { type: Object, default: () => ({}) },
  revenueBreakdown: { type: Object, default: () => ({}) },
  // New keys from backend extension
  paymentStatus: { type: Array, default: () => [] },
  monthlyRevenue: { type: Array, default: () => [] },
  paymentMethods: { type: Array, default: () => [] },
})

// Existing cost helpers
const costSummary = computed(() => props.costAnalytics?.summary || {})
const costBreakdown = computed(() => props.costAnalytics?.cost_breakdown || [])
const costDailyTrends = computed(() => props.costAnalytics?.daily_trends || [])
const maxDailyCost = computed(() => Math.max(...costDailyTrends.value.map(d => d.total || 0), 1))
const breakfastCosts = computed(() => props.costAnalytics?.breakfast_costs || {})
const revenueVsCost = computed(() => props.costAnalytics?.revenue_vs_cost || {})
const financialKpis = computed(() => props.kpiData?.financial_kpis || {})

// Revenue growth from revenueBreakdown
const totalRevenue = computed(() => props.revenueBreakdown?.total_revenue ?? 0)

// Monthly revenue bar chart max — backend field is `revenue`
const maxMonthlyRevenue = computed(() => Math.max(...props.monthlyRevenue.map(m => m.revenue || 0), 1))

// Payment methods max for bar chart
const maxPaymentMethod = computed(() => Math.max(...props.paymentMethods.map(p => p.total_amount || 0), 1))

// Payment status helpers
function paymentStatusColor(status) {
  const s = (status || '').toLowerCase()
  if (s === 'paid') return 'border-green-200 bg-green-50'
  if (s === 'unpaid' || s === 'overdue') return 'border-red-200 bg-red-50'
  if (s === 'partly paid') return 'border-yellow-200 bg-yellow-50'
  return 'border-gray-200 bg-gray-50'
}

// Format helpers
function fmt(value) {
  if (!value && value !== 0) return 'N/A'
  return new Intl.NumberFormat('en-KE', { style: 'currency', currency: 'KES', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value)
}
function fmtPct(value) {
  if (!value && value !== 0) return '0%'
  return Number(value).toFixed(1) + '%'
}
function fmtNum(value) {
  if (!value && value !== 0) return '0'
  return Number(value).toLocaleString()
}
function growthClass(v) { return v > 0 ? 'text-green-600' : v < 0 ? 'text-red-600' : 'text-gray-500' }
function trendArrow(v) { return v > 0 ? '+' + v.toFixed(1) + '%' : v < 0 ? v.toFixed(1) + '%' : '0%' }
</script>

<template>
  <div class="space-y-6">

    <!-- Cost KPI Cards -->
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <div class="bg-white rounded-lg border p-4">
        <span class="text-xs font-medium text-gray-500 uppercase">Total Costs</span>
        <div class="text-2xl font-bold mt-1">{{ fmt(costSummary.total_operational_costs) }}</div>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <span class="text-xs font-medium text-gray-500 uppercase">Gross Profit</span>
        <div class="text-2xl font-bold mt-1" :class="costSummary.gross_profit > 0 ? 'text-green-600' : 'text-red-600'">{{ fmt(costSummary.gross_profit) }}</div>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <span class="text-xs font-medium text-gray-500 uppercase">Profit Margin</span>
        <div class="text-2xl font-bold mt-1">{{ fmtPct(costSummary.profit_margin) }}</div>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <span class="text-xs font-medium text-gray-500 uppercase">CPOR</span>
        <div class="text-2xl font-bold mt-1">{{ fmt(financialKpis.cpor) }}</div>
        <div v-if="financialKpis.cpor_trend" class="text-xs mt-0.5" :class="growthClass(-financialKpis.cpor_trend)">{{ trendArrow(financialKpis.cpor_trend) }}</div>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <span class="text-xs font-medium text-gray-500 uppercase">Cost/Room Night</span>
        <div class="text-2xl font-bold mt-1">{{ fmt(costSummary.cost_per_room_night) }}</div>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <span class="text-xs font-medium text-gray-500 uppercase">Room Nights</span>
        <div class="text-2xl font-bold mt-1">{{ fmtNum(costSummary.room_nights) }}</div>
      </div>
    </div>

    <!-- Cost Breakdown + Revenue vs Cost -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="bg-white rounded-lg border p-5">
        <h3 class="text-sm font-semibold text-gray-900 mb-4">Cost Breakdown by Category</h3>
        <div v-if="costBreakdown.length" class="space-y-3">
          <div v-for="cat in costBreakdown" :key="cat.category">
            <div class="flex justify-between text-sm mb-1">
              <span class="text-gray-600">{{ cat.category }}</span>
              <span class="font-medium">{{ fmt(cat.amount) }} <span class="text-gray-400">({{ cat.percentage?.toFixed(1) }}%)</span></span>
            </div>
            <div class="w-full bg-gray-100 rounded-full h-2">
              <div class="h-2 rounded-full"
                :class="cat.color === 'blue' ? 'bg-blue-500' : cat.color === 'orange' ? 'bg-orange-500' : cat.color === 'green' ? 'bg-green-500' : 'bg-purple-500'"
                :style="{ width: cat.percentage + '%' }">
              </div>
            </div>
          </div>
        </div>
        <div v-else class="text-sm text-gray-400 text-center py-6">No cost data</div>
      </div>

      <div class="bg-white rounded-lg border p-5">
        <h3 class="text-sm font-semibold text-gray-900 mb-4">Revenue vs Cost</h3>
        <div class="space-y-4">
          <div class="flex items-center justify-between p-3 bg-green-50 rounded-lg">
            <span class="text-sm text-green-700 font-medium">Revenue</span>
            <span class="text-lg font-bold text-green-700">{{ fmt(revenueVsCost.revenue) }}</span>
          </div>
          <div class="flex items-center justify-between p-3 bg-red-50 rounded-lg">
            <span class="text-sm text-red-700 font-medium">Costs</span>
            <span class="text-lg font-bold text-red-700">{{ fmt(revenueVsCost.costs) }}</span>
          </div>
          <div class="flex items-center justify-between p-3 rounded-lg" :class="revenueVsCost.profit > 0 ? 'bg-blue-50' : 'bg-yellow-50'">
            <span class="text-sm font-medium" :class="revenueVsCost.profit > 0 ? 'text-blue-700' : 'text-yellow-700'">Net Profit</span>
            <span class="text-lg font-bold" :class="revenueVsCost.profit > 0 ? 'text-blue-700' : 'text-yellow-700'">{{ fmt(revenueVsCost.profit) }}</span>
          </div>
          <div class="text-center text-sm text-gray-500">
            Margin: <span class="font-semibold" :class="revenueVsCost.margin_percentage > 30 ? 'text-green-600' : 'text-yellow-600'">{{ fmtPct(revenueVsCost.margin_percentage) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Daily Cost Trend + Breakfast Costs -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="bg-white rounded-lg border p-5">
        <h3 class="text-sm font-semibold text-gray-900 mb-4">Daily Cost Trend</h3>
        <div v-if="costDailyTrends.length" class="h-40 flex items-end gap-0.5">
          <div
            v-for="(day, idx) in costDailyTrends.slice(-30)" :key="idx"
            class="flex-1 bg-red-300 rounded-t hover:bg-red-500 transition-colors cursor-default"
            :style="{ height: `${Math.max((day.total / maxDailyCost) * 100, 2)}%` }"
            :title="`${day.date}: ${fmt(day.total)} (Room: ${fmt(day.room_expenses)}, Breakfast: ${fmt(day.breakfast_costs)})`"
          ></div>
        </div>
        <div v-else class="h-40 flex items-center justify-center text-sm text-gray-400">No cost trend data</div>
      </div>

      <div class="bg-white rounded-lg border p-5">
        <h3 class="text-sm font-semibold text-gray-900 mb-4">Breakfast Cost Analysis</h3>
        <div class="grid grid-cols-2 gap-4">
          <div class="text-center p-3 bg-gray-50 rounded-lg">
            <div class="text-xl font-bold">{{ fmt(breakfastCosts.total) }}</div>
            <div class="text-xs text-gray-500 mt-1">Total Breakfast Cost</div>
          </div>
          <div class="text-center p-3 bg-gray-50 rounded-lg">
            <div class="text-xl font-bold">{{ fmt(breakfastCosts.avg_daily) }}</div>
            <div class="text-xs text-gray-500 mt-1">Avg Daily</div>
          </div>
          <div class="text-center p-3 bg-gray-50 rounded-lg">
            <div class="text-xl font-bold">{{ fmt(breakfastCosts.cost_per_guest) }}</div>
            <div class="text-xs text-gray-500 mt-1">Cost Per Guest</div>
          </div>
          <div class="text-center p-3 bg-gray-50 rounded-lg">
            <div class="text-xl font-bold">{{ fmtNum(breakfastCosts.total_guests) }}</div>
            <div class="text-xs text-gray-500 mt-1">Guests Served</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Monthly Revenue Chart (new from Revenue report) -->
    <div v-if="monthlyRevenue.length" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-4">Monthly Revenue</h3>
      <div class="h-40 flex items-end gap-1">
        <div
          v-for="(m, idx) in monthlyRevenue" :key="idx"
          class="flex-1 bg-blue-400 rounded-t hover:bg-blue-600 transition-colors cursor-default min-w-0"
          :style="{ height: `${Math.max(((m.revenue || 0) / maxMonthlyRevenue) * 100, 2)}%` }"
          :title="`${m.month_name || m.month}: ${fmt(m.revenue)}`"
        ></div>
      </div>
      <div class="flex justify-between text-xs text-gray-400 mt-2">
        <span v-for="(m, idx) in monthlyRevenue" :key="idx" class="flex-1 text-center truncate">{{ m.month_name?.slice(0, 3) || m.month }}</span>
      </div>
    </div>

    <!-- Payment Status Breakdown (new from Revenue report) -->
    <div v-if="paymentStatus.length" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-4">Payment Status</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div
          v-for="status in paymentStatus" :key="status.status"
          class="p-4 rounded-lg border" :class="paymentStatusColor(status.status)"
        >
          <div class="text-sm font-medium capitalize">{{ status.status }}</div>
          <div class="text-xl font-bold text-gray-900 mt-1">{{ fmt(status.total_amount) }}</div>
          <div class="text-xs text-gray-500">{{ status.count }} invoices</div>
          <div v-if="status.outstanding_amount > 0" class="text-xs text-orange-600 mt-1">
            {{ fmt(status.outstanding_amount) }} outstanding
          </div>
        </div>
      </div>
    </div>

    <!-- Payment Methods Bar Chart (new from Revenue report) -->
    <div v-if="paymentMethods.length" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-4">Payment Methods</h3>
      <div class="space-y-3">
        <div v-for="pm in paymentMethods" :key="pm.mode_of_payment || pm.method">
          <div class="flex justify-between text-sm mb-1">
            <span class="text-gray-600">{{ pm.mode_of_payment || pm.method }}</span>
            <span class="font-medium">{{ fmt(pm.total_amount) }} <span class="text-gray-400">({{ pm.invoice_count || pm.count }} orders)</span></span>
          </div>
          <div class="w-full bg-gray-100 rounded-full h-2">
            <div class="bg-indigo-500 h-2 rounded-full" :style="{ width: `${((pm.total_amount || 0) / maxPaymentMethod) * 100}%` }"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Room Expenses by Account -->
    <div v-if="costAnalytics.room_expenses?.by_account?.length" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-3">Room Expenses by Account</h3>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-left text-gray-500">
              <th class="py-2 font-medium">Account</th>
              <th class="py-2 font-medium text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="acc in costAnalytics.room_expenses.by_account" :key="acc.account" class="border-b last:border-0">
              <td class="py-2 text-gray-900">{{ acc.account }}</td>
              <td class="py-2 text-right font-medium">{{ fmt(acc.amount) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

  </div>
</template>
