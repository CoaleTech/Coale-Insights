<script setup>
import { computed } from 'vue'
import { TrendingUp, TrendingDown, Minus } from 'lucide-vue-next'

const props = defineProps({
  occupancy: { type: Object, default: () => ({}) },
  revenueBreakdown: { type: Object, default: () => ({}) },
  kpiData: { type: Object, default: () => ({}) },
  snapshot: { type: Object, default: () => ({}) },
  housekeeping: { type: Object, default: () => ({}) },
  // New keys from backend extension
  topCustomers: { type: Array, default: () => [] },
  roomStatusOverview: { type: Object, default: () => ({}) },
  kpiTrends: { type: Array, default: () => [] },
})

// Revenue computed
const roomsRevenue = computed(() => props.revenueBreakdown?.rooms_revenue ?? props.revenueBreakdown?.room_revenue ?? 0)
const fnbRevenue = computed(() => props.revenueBreakdown?.fnb_revenue ?? props.revenueBreakdown?.restaurant_revenue ?? 0)
const eventsRevenue = computed(() => props.revenueBreakdown?.events_revenue ?? props.revenueBreakdown?.event_revenue ?? 0)
const otherRevenue = computed(() => props.revenueBreakdown?.other_revenue ?? 0)
const totalRevenue = computed(() => props.revenueBreakdown?.total_revenue ?? 0)

function revShare(value) {
  if (!totalRevenue.value || !value) return 0
  return ((value / totalRevenue.value) * 100).toFixed(1)
}

// Occupancy trend
const maxOccupancy = computed(() => {
  const trend = props.occupancy?.daily_trend || []
  return Math.max(...trend.map(p => p.occupancy_rate || 0), 1)
})

// KPI targets
const kpiTargets = computed(() => props.kpiData?.kpi_targets || [])
const financialKpis = computed(() => props.kpiData?.financial_kpis || {})

// KPI trends for 3-axis chart (new)
const maxKpiTrendOccupancy = computed(() => Math.max(...props.kpiTrends.map(d => d.occupancy_rate || 0), 1))

// Room status from room_status_overview
const roomStatus = computed(() => props.roomStatusOverview || {})

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
function perfColor(pct) {
  if (pct >= 90) return 'bg-green-500'
  if (pct >= 70) return 'bg-yellow-500'
  return 'bg-red-500'
}
function trendIcon(v) {
  if (v > 0) return TrendingUp
  if (v < 0) return TrendingDown
  return Minus
}
function trendClass(v) {
  if (v > 0) return 'text-green-400'
  if (v < 0) return 'text-red-400'
  return 'text-gray-400'
}
function trendText(v) {
  if (!v && v !== 0) return null
  return v > 0 ? '+' + Number(v).toFixed(1) + '%' : Number(v).toFixed(1) + '%'
}
</script>

<template>
  <div class="space-y-6">

    <!-- KPI Cards row -->
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <!-- Occupancy -->
      <div class="bg-white rounded-lg border p-4">
        <span class="text-xs font-medium text-gray-500 uppercase">Occupancy</span>
        <div class="text-2xl font-bold mt-1">{{ fmtPct(occupancy.occupancy_rate) }}</div>
        <div v-if="trendText(kpiData?.financial_kpis?.occupancy_trend)" class="flex items-center gap-1 mt-1">
          <component :is="trendIcon(kpiData?.financial_kpis?.occupancy_trend)" class="w-3 h-3" :class="trendClass(kpiData?.financial_kpis?.occupancy_trend)" />
          <span class="text-xs" :class="trendClass(kpiData?.financial_kpis?.occupancy_trend)">{{ trendText(kpiData?.financial_kpis?.occupancy_trend) }}</span>
        </div>
      </div>
      <!-- ADR -->
      <div class="bg-white rounded-lg border p-4">
        <span class="text-xs font-medium text-gray-500 uppercase">ADR</span>
        <div class="text-2xl font-bold mt-1">{{ fmt(occupancy.adr) }}</div>
        <div v-if="trendText(financialKpis.adr_trend)" class="flex items-center gap-1 mt-1">
          <component :is="trendIcon(financialKpis.adr_trend)" class="w-3 h-3" :class="trendClass(financialKpis.adr_trend)" />
          <span class="text-xs" :class="trendClass(financialKpis.adr_trend)">{{ trendText(financialKpis.adr_trend) }}</span>
        </div>
      </div>
      <!-- RevPAR -->
      <div class="bg-white rounded-lg border p-4">
        <span class="text-xs font-medium text-gray-500 uppercase">RevPAR</span>
        <div class="text-2xl font-bold mt-1">{{ fmt(occupancy.revpar) }}</div>
        <div v-if="trendText(financialKpis.revpar_trend)" class="flex items-center gap-1 mt-1">
          <component :is="trendIcon(financialKpis.revpar_trend)" class="w-3 h-3" :class="trendClass(financialKpis.revpar_trend)" />
          <span class="text-xs" :class="trendClass(financialKpis.revpar_trend)">{{ trendText(financialKpis.revpar_trend) }}</span>
        </div>
      </div>
      <!-- Total Revenue -->
      <div class="bg-white rounded-lg border p-4">
        <span class="text-xs font-medium text-gray-500 uppercase">Total Revenue</span>
        <div class="text-2xl font-bold mt-1">{{ fmt(totalRevenue) }}</div>
        <div v-if="trendText(financialKpis.revenue_trend)" class="flex items-center gap-1 mt-1">
          <component :is="trendIcon(financialKpis.revenue_trend)" class="w-3 h-3" :class="trendClass(financialKpis.revenue_trend)" />
          <span class="text-xs" :class="trendClass(financialKpis.revenue_trend)">{{ trendText(financialKpis.revenue_trend) }}</span>
        </div>
      </div>
      <!-- Arrivals Today -->
      <div class="bg-white rounded-lg border p-4">
        <span class="text-xs font-medium text-gray-500 uppercase">Arrivals Today</span>
        <div class="text-2xl font-bold mt-1">{{ snapshot.arrivals_today ?? 0 }}</div>
      </div>
      <!-- Departures Today -->
      <div class="bg-white rounded-lg border p-4">
        <span class="text-xs font-medium text-gray-500 uppercase">Departures Today</span>
        <div class="text-2xl font-bold mt-1">{{ snapshot.departures_today ?? 0 }}</div>
      </div>
    </div>

    <!-- Occupancy Trend + Revenue Breakdown -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Occupancy Trend Chart -->
      <div class="bg-white rounded-lg border p-5">
        <h3 class="text-sm font-semibold text-gray-900 mb-4">Occupancy Trend (30 Days)</h3>
        <div v-if="occupancy.daily_trend?.length" class="h-48 flex items-end gap-0.5">
          <div
            v-for="(point, idx) in occupancy.daily_trend" :key="idx"
            class="flex-1 bg-blue-400 rounded-t hover:bg-blue-600 transition-colors cursor-default"
            :style="{ height: `${Math.max((point.occupancy_rate / maxOccupancy) * 100, 2)}%` }"
            :title="`${point.date}: ${point.occupancy_rate?.toFixed(1)}% (${point.rooms_occupied} rooms)`"
          ></div>
        </div>
        <div v-else class="h-48 flex items-center justify-center text-sm text-gray-400">No trend data</div>
      </div>

      <!-- Revenue Breakdown -->
      <div class="bg-white rounded-lg border p-5">
        <h3 class="text-sm font-semibold text-gray-900 mb-4">Revenue Breakdown</h3>
        <div class="space-y-3">
          <div>
            <div class="flex justify-between text-sm mb-1">
              <span class="text-gray-600">Rooms</span>
              <span class="font-medium">{{ fmt(roomsRevenue) }} <span class="text-gray-400">({{ revShare(roomsRevenue) }}%)</span></span>
            </div>
            <div class="w-full bg-gray-100 rounded-full h-2.5">
              <div class="bg-blue-500 h-2.5 rounded-full" :style="{ width: revShare(roomsRevenue) + '%' }"></div>
            </div>
          </div>
          <div>
            <div class="flex justify-between text-sm mb-1">
              <span class="text-gray-600">Restaurant / F&B</span>
              <span class="font-medium">{{ fmt(fnbRevenue) }} <span class="text-gray-400">({{ revShare(fnbRevenue) }}%)</span></span>
            </div>
            <div class="w-full bg-gray-100 rounded-full h-2.5">
              <div class="bg-green-500 h-2.5 rounded-full" :style="{ width: revShare(fnbRevenue) + '%' }"></div>
            </div>
          </div>
          <div>
            <div class="flex justify-between text-sm mb-1">
              <span class="text-gray-600">Events / Banquets</span>
              <span class="font-medium">{{ fmt(eventsRevenue) }} <span class="text-gray-400">({{ revShare(eventsRevenue) }}%)</span></span>
            </div>
            <div class="w-full bg-gray-100 rounded-full h-2.5">
              <div class="bg-purple-500 h-2.5 rounded-full" :style="{ width: revShare(eventsRevenue) + '%' }"></div>
            </div>
          </div>
          <div v-if="otherRevenue > 0">
            <div class="flex justify-between text-sm mb-1">
              <span class="text-gray-600">Other</span>
              <span class="font-medium">{{ fmt(otherRevenue) }} <span class="text-gray-400">({{ revShare(otherRevenue) }}%)</span></span>
            </div>
            <div class="w-full bg-gray-100 rounded-full h-2.5">
              <div class="bg-orange-500 h-2.5 rounded-full" :style="{ width: revShare(otherRevenue) + '%' }"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Today's Operations -->
    <div class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-4">Today's Operations</h3>
      <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
        <div class="text-center p-3 bg-gray-50 rounded-lg">
          <div class="text-xl font-bold">{{ snapshot.occupied_rooms ?? 0 }}</div>
          <div class="text-xs text-gray-500 mt-1">Occupied Rooms</div>
        </div>
        <div class="text-center p-3 bg-gray-50 rounded-lg">
          <div class="text-xl font-bold">{{ snapshot.available_rooms ?? 0 }}</div>
          <div class="text-xs text-gray-500 mt-1">Available</div>
        </div>
        <div class="text-center p-3 bg-gray-50 rounded-lg">
          <div class="text-xl font-bold">{{ snapshot.out_of_order ?? 0 }}</div>
          <div class="text-xs text-gray-500 mt-1">Out of Order</div>
        </div>
        <div class="text-center p-3 bg-gray-50 rounded-lg">
          <div class="text-xl font-bold">{{ snapshot.in_house_guests ?? 0 }}</div>
          <div class="text-xs text-gray-500 mt-1">In-House Guests</div>
        </div>
        <div class="text-center p-3 bg-gray-50 rounded-lg">
          <div class="text-xl font-bold">{{ occupancy.total_rooms ?? 0 }}</div>
          <div class="text-xs text-gray-500 mt-1">Total Rooms</div>
        </div>
        <div class="text-center p-3 bg-gray-50 rounded-lg">
          <div class="text-xl font-bold">{{ housekeeping.completed ?? 0 }}/{{ housekeeping.total_tasks ?? 0 }}</div>
          <div class="text-xs text-gray-500 mt-1">Housekeeping</div>
        </div>
        <div class="text-center p-3 bg-gray-50 rounded-lg">
          <div class="text-xl font-bold">{{ occupancy.avg_length_of_stay?.toFixed(1) ?? 0 }}</div>
          <div class="text-xs text-gray-500 mt-1">Avg Stay (nights)</div>
        </div>
      </div>

      <!-- Room Types -->
      <div v-if="occupancy.by_room_type?.length" class="mt-4">
        <h4 class="text-xs font-medium text-gray-500 uppercase mb-2">By Room Type</h4>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b text-left text-gray-500">
                <th class="py-2 font-medium">Type</th>
                <th class="py-2 font-medium text-right">Total</th>
                <th class="py-2 font-medium text-right">Occupied</th>
                <th class="py-2 font-medium text-right">Available</th>
                <th class="py-2 font-medium text-right">Occupancy</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rt in occupancy.by_room_type" :key="rt.room_type" class="border-b last:border-0">
                <td class="py-2 font-medium text-gray-900">{{ rt.room_type }}</td>
                <td class="py-2 text-right">{{ rt.total_rooms }}</td>
                <td class="py-2 text-right">{{ rt.occupied }}</td>
                <td class="py-2 text-right">{{ rt.available }}</td>
                <td class="py-2 text-right font-medium" :class="rt.occupancy_rate > 70 ? 'text-green-600' : rt.occupancy_rate > 30 ? 'text-yellow-600' : 'text-red-600'">
                  {{ rt.occupancy_rate?.toFixed(1) }}%
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Room Status Visual Grid (new from occupancy report) -->
    <div v-if="roomStatus.available !== undefined || roomStatus.occupied !== undefined" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-4">Room Status Overview</h3>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="p-4 rounded-lg bg-green-50 border border-green-200 text-center">
          <div class="text-2xl font-bold text-green-700">{{ roomStatus.available ?? 0 }}</div>
          <div class="text-xs text-green-600 mt-1">Available</div>
        </div>
        <div class="p-4 rounded-lg bg-blue-50 border border-blue-200 text-center">
          <div class="text-2xl font-bold text-blue-700">{{ roomStatus.occupied ?? 0 }}</div>
          <div class="text-xs text-blue-600 mt-1">Occupied</div>
        </div>
        <div class="p-4 rounded-lg bg-yellow-50 border border-yellow-200 text-center">
          <div class="text-2xl font-bold text-yellow-700">{{ roomStatus.reserved ?? 0 }}</div>
          <div class="text-xs text-yellow-600 mt-1">Reserved</div>
        </div>
        <div class="p-4 rounded-lg bg-red-50 border border-red-200 text-center">
          <div class="text-2xl font-bold text-red-700">{{ roomStatus.out_of_order ?? 0 }}</div>
          <div class="text-xs text-red-600 mt-1">Out of Order</div>
        </div>
      </div>
    </div>

    <!-- KPI Trends chart (new 3-axis: occupancy % / RevPAR / ADR) -->
    <div v-if="kpiTrends.length" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-2">KPI Trends</h3>
      <div class="flex items-center gap-4 mb-4 text-xs text-gray-500">
        <div class="flex items-center gap-1.5"><div class="w-3 h-3 rounded-full bg-blue-500"></div><span>Occupancy %</span></div>
        <div class="flex items-center gap-1.5"><div class="w-3 h-3 rounded-full bg-green-500"></div><span>RevPAR</span></div>
        <div class="flex items-center gap-1.5"><div class="w-3 h-3 rounded-full bg-purple-500"></div><span>ADR</span></div>
      </div>
      <div class="h-40 flex items-end gap-0.5">
        <div v-for="(d, idx) in kpiTrends" :key="idx" class="flex-1 flex items-end gap-px justify-center">
          <div
            class="w-1.5 bg-blue-400 rounded-t hover:bg-blue-600 transition-colors cursor-default"
            :style="{ height: `${Math.max((d.occupancy_rate / maxKpiTrendOccupancy) * 100, 2)}%` }"
            :title="`${d.date}: Occ ${d.occupancy_rate?.toFixed(1)}%`"
          ></div>
        </div>
      </div>
      <div class="flex justify-between text-xs text-gray-400 mt-1">
        <span>{{ kpiTrends[0]?.date }}</span>
        <span>{{ kpiTrends[Math.floor(kpiTrends.length / 2)]?.date }}</span>
        <span>{{ kpiTrends[kpiTrends.length - 1]?.date }}</span>
      </div>
    </div>

    <!-- KPI Performance Targets -->
    <div v-if="kpiTargets.length" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-4">KPI Performance Targets</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <div v-for="kpi in kpiTargets" :key="kpi.name" class="p-3 bg-gray-50 rounded-lg">
          <div class="text-xs text-gray-500 font-medium">{{ kpi.name }}</div>
          <div class="text-lg font-bold mt-1">{{ kpi.unit === '%' ? fmtPct(kpi.current) : fmt(kpi.current) }}</div>
          <div class="flex items-center gap-2 mt-2">
            <div class="flex-1 bg-gray-200 rounded-full h-1.5">
              <div :class="perfColor(kpi.performance)" class="h-1.5 rounded-full transition-all" :style="{ width: Math.min(kpi.performance, 100) + '%' }"></div>
            </div>
            <span class="text-xs text-gray-500">{{ kpi.performance }}%</span>
          </div>
          <div class="text-xs text-gray-400 mt-1">Target: {{ kpi.unit === '%' ? kpi.target + '%' : fmt(kpi.target) }}</div>
        </div>
      </div>
    </div>

    <!-- Top Customers (new from revenue report) -->
    <div v-if="topCustomers.length" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-4">Top Customers</h3>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-left text-gray-500">
              <th class="py-2 font-medium">Guest</th>
              <th class="py-2 font-medium text-right">Revenue</th>
              <th class="py-2 font-medium text-right">Visits</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in topCustomers.slice(0, 10)" :key="c.customer || c.guest_name" class="border-b last:border-0 hover:bg-gray-50">
              <td class="py-2">
                <div class="font-medium text-gray-900">{{ c.guest_name || c.customer }}</div>
                <div v-if="c.last_visit" class="text-xs text-gray-400">Last: {{ c.last_visit }}</div>
              </td>
              <td class="py-2 text-right font-medium">{{ fmt(c.total_revenue) }}</td>
              <td class="py-2 text-right text-gray-600">{{ c.total_bookings ?? 0 }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

  </div>
</template>
