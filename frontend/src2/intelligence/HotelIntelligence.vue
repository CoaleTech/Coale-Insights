<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  RefreshCcw, Loader2, AlertTriangle, Home,
  Users, UtensilsCrossed, CalendarDays, Activity, Star,
  HelpCircle, Zap, Skull, ChefHat, Wallet,
  Gauge
} from 'lucide-vue-next'
import { apiCall } from '../helpers/api'
import { createToast } from '../helpers/toasts'
import DashboardChatButton from '../components/DashboardChatButton.vue'

// State
const data = ref(null)
const isLoading = ref(true)
const isRefreshing = ref(false)
const error = ref(null)
const activeTab = ref('overview')

const tabs = [
  { id: 'overview', label: 'Overview', icon: Home },
  { id: 'costs', label: 'Cost & Profitability', icon: Wallet },
  { id: 'operations', label: 'Operations', icon: Gauge },
  { id: 'guests', label: 'Guest Intelligence', icon: Users },
  { id: 'restaurant', label: 'Restaurant & F&B', icon: UtensilsCrossed },
  { id: 'kitchen', label: 'Kitchen Analytics', icon: ChefHat },
  { id: 'events', label: 'Events & Banquets', icon: CalendarDays },
  { id: 'forecast', label: 'Demand Forecast', icon: Activity },
]

// Date range
const dateRange = ref('12m')
const dateRanges = [
  { value: '7d', label: '7 Days' },
  { value: '30d', label: '30 Days' },
  { value: '90d', label: '90 Days' },
  { value: '6m', label: '6 Months' },
  { value: '12m', label: '12 Months' },
]

// Computed data sections -- mapped to actual backend keys
const occupancy = computed(() => data.value?.occupancy || {})
const snapshot = computed(() => occupancy.value?.today_snapshot || {})
const revenueBreakdown = computed(() => data.value?.revenue_breakdown || {})
const guestData = computed(() => data.value?.guest_analytics || {})
const restaurant = computed(() => data.value?.restaurant || {})
const events = computed(() => data.value?.events || {})
const demandForecast = computed(() => data.value?.demand_forecast || {})
// Extended analytics
const costAnalytics = computed(() => data.value?.cost_analytics || {})
const kpiData = computed(() => data.value?.kpi_data || {})
const operationalMetrics = computed(() => data.value?.operational_metrics || {})
const checkinCheckout = computed(() => data.value?.checkin_checkout || {})
const roomUtilization = computed(() => data.value?.room_utilization || {})
const bookingPatterns = computed(() => data.value?.booking_patterns || {})
const kitchenAnalytics = computed(() => data.value?.kitchen_analytics || {})
const restaurantExtended = computed(() => data.value?.restaurant_extended || {})
const eventExtended = computed(() => data.value?.event_extended || {})

// Revenue breakdown -- handle both old cached keys and new keys
const roomsRevenue = computed(() => revenueBreakdown.value?.rooms_revenue ?? revenueBreakdown.value?.room_revenue ?? 0)
const fnbRevenue = computed(() => revenueBreakdown.value?.fnb_revenue ?? revenueBreakdown.value?.restaurant_revenue ?? 0)
const eventsRevenue = computed(() => revenueBreakdown.value?.events_revenue ?? revenueBreakdown.value?.event_revenue ?? 0)
const otherRevenue = computed(() => revenueBreakdown.value?.other_revenue ?? 0)
const totalRevenue = computed(() => revenueBreakdown.value?.total_revenue ?? 0)

// Occupancy trend
const maxOccupancy = computed(() => {
  const trend = occupancy.value?.daily_trend || []
  return Math.max(...trend.map(p => p.occupancy_rate || 0), 1)
})

// Restaurant helpers
const peakHours = computed(() => restaurant.value?.peak_hours || [])
const maxPeakHourCount = computed(() => Math.max(...peakHours.value.map(h => h.order_count || h.count || 0), 1))
const tableTurnover = computed(() => restaurant.value?.table_turnover || {})

// Menu engineering -- backend returns separate arrays per category
const menuEngineering = computed(() => restaurant.value?.menu_engineering || {})
const menuSummary = computed(() => menuEngineering.value.summary || {})
const topStars = computed(() => (menuEngineering.value.stars || []).slice(0, 8))
const topDogs = computed(() => (menuEngineering.value.dogs || []).slice(0, 5))

// Demand forecast
const forecastDays = computed(() => demandForecast.value?.forecast || [])
const maxForecastOccupancy = computed(() =>
  Math.max(...forecastDays.value.map(d => d.upper_bound || d.forecast_occupancy || 0), 1)
)
const avgForecastOccupancy = computed(() => {
  const days = forecastDays.value
  if (!days.length) return 0
  return days.reduce((sum, d) => sum + (d.forecast_occupancy || 0), 0) / days.length
})
const peakForecastDay = computed(() => {
  const days = forecastDays.value
  if (!days.length) return null
  return days.reduce((max, d) => (d.forecast_occupancy > (max?.forecast_occupancy || 0)) ? d : max, days[0])
})

// Housekeeping
const housekeeping = computed(() => occupancy.value?.housekeeping || {})

// Upcoming events
const upcomingEvents = computed(() => events.value?.upcoming_events || [])

// Cost helpers
const costSummary = computed(() => costAnalytics.value?.summary || {})
const costBreakdown = computed(() => costAnalytics.value?.cost_breakdown || [])
const costDailyTrends = computed(() => costAnalytics.value?.daily_trends || [])
const maxDailyCost = computed(() => Math.max(...costDailyTrends.value.map(d => d.total || 0), 1))
const breakfastCosts = computed(() => costAnalytics.value?.breakfast_costs || {})
const revenueVsCost = computed(() => costAnalytics.value?.revenue_vs_cost || {})

// KPI targets
const kpiTargets = computed(() => kpiData.value?.kpi_targets || [])
const financialKpis = computed(() => kpiData.value?.financial_kpis || {})

// Operations helpers
const opMetrics = computed(() => operationalMetrics.value?.metrics || {})
const checkins = computed(() => checkinCheckout.value?.checkins || {})
const checkouts = computed(() => checkinCheckout.value?.checkouts || {})
const overstays = computed(() => checkinCheckout.value?.overstays || {})
const floorBreakdown = computed(() => roomUtilization.value?.floor_breakdown || [])
const wingBreakdown = computed(() => roomUtilization.value?.wing_breakdown || [])
const bedOccupancy = computed(() => roomUtilization.value?.bed_occupancy || {})
const dayOfWeekPatterns = computed(() => bookingPatterns.value?.day_of_week_patterns || [])
const maxDayBookings = computed(() => Math.max(...dayOfWeekPatterns.value.map(d => d.booking_count || 0), 1))

// Kitchen helpers
const kitchenSummary = computed(() => kitchenAnalytics.value?.summary || {})
const kitchenTopItems = computed(() => kitchenAnalytics.value?.top_items || [])
const kitchenPrepTime = computed(() => kitchenAnalytics.value?.prep_time || {})
const foodCost = computed(() => kitchenAnalytics.value?.food_cost || {})
const waiterPerformance = computed(() => kitchenAnalytics.value?.waiter_performance || [])
const kitchenPeakHours = computed(() => kitchenAnalytics.value?.peak_hours || [])
const maxKitchenHour = computed(() => Math.max(...kitchenPeakHours.value.map(h => h.orders || 0), 1))
const categoryBreakdown = computed(() => kitchenAnalytics.value?.category_breakdown || [])

// Restaurant extended helpers
const restExtSummary = computed(() => restaurantExtended.value?.summary || {})
const restWaiterPerf = computed(() => restaurantExtended.value?.waiter_performance || [])
const restPaymentMethods = computed(() => restaurantExtended.value?.payment_methods || [])

// Event extended helpers
const eventExtSummary = computed(() => eventExtended.value?.summary || {})
const eventCommission = computed(() => eventExtended.value?.commission_data || {})
const eventTopEvents = computed(() => eventExtended.value?.top_events || [])
const eventCostByType = computed(() => eventExtended.value?.cost_by_type || [])

// AI Chat context
const chatContext = computed(() => ({
  occupancy_rate: occupancy.value?.occupancy_rate,
  adr: occupancy.value?.adr,
  revpar: occupancy.value?.revpar,
  total_revenue: totalRevenue.value,
  arrivals_today: snapshot.value?.arrivals_today,
  departures_today: snapshot.value?.departures_today,
  repeat_guest_rate: guestData.value?.repeat_guest_rate,
  total_guests: guestData.value?.total_guests,
  revpash: restaurant.value?.avg_revpash,
  total_events: events.value?.total_events,
  gopar: opMetrics.value?.gopar,
  cpor: financialKpis.value?.cpor,
  profit_margin: costSummary.value?.profit_margin,
}))

// Load data
onMounted(() => loadData())

async function loadData(refresh = false) {
  if (refresh) {
    isRefreshing.value = true
  } else {
    isLoading.value = true
  }
  error.value = null
  try {
    data.value = await apiCall('insights.api.ml.hotel.hotel_intelligence', {
      date_filter: dateRange.value,
      refresh: refresh
    })
    if (refresh) {
      createToast({ title: 'Refreshed', message: 'Hotel intelligence data updated', variant: 'success' })
    }
  } catch (err) {
    console.error('Error loading hotel data:', err)
    error.value = err.message || 'Failed to load hotel intelligence data'
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

function refreshData() { loadData(true) }

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

function revShare(value) {
  if (!totalRevenue.value || !value) return 0
  return ((value / totalRevenue.value) * 100).toFixed(1)
}

function growthClass(v) { return v > 0 ? 'text-green-600' : v < 0 ? 'text-red-600' : 'text-gray-500' }
function trendArrow(v) { return v > 0 ? '+' + v.toFixed(1) + '%' : v < 0 ? v.toFixed(1) + '%' : '0%' }
function perfColor(pct) {
  if (pct >= 90) return 'bg-green-500'
  if (pct >= 70) return 'bg-yellow-500'
  return 'bg-red-500'
}
</script>

<template>
  <div class="flex flex-col h-full bg-gray-50">

    <!-- Header -->
    <header class="bg-white border-b px-6 py-4">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-xl font-bold text-gray-900">Hotel Intelligence</h1>
          <p class="text-sm text-gray-500">Comprehensive hotel analytics & operations</p>
        </div>
        <div class="flex items-center gap-3">
          <div class="flex bg-gray-100 rounded-lg p-0.5">
            <button
              v-for="r in dateRanges" :key="r.value"
              @click="dateRange = r.value; loadData()"
              :class="[
                'px-3 py-1 text-xs font-medium rounded-md transition-colors',
                dateRange === r.value ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              ]"
            >{{ r.label }}</button>
          </div>
          <button @click="refreshData" :disabled="isRefreshing" class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border rounded-lg hover:bg-gray-50 disabled:opacity-50">
            <RefreshCcw :class="['w-3.5 h-3.5', isRefreshing && 'animate-spin']" />
            Refresh
          </button>
        </div>
      </div>

      <!-- Tabs -->
      <div class="flex gap-1 mt-4 -mb-4 border-b-0 overflow-x-auto">
        <button
          v-for="tab in tabs" :key="tab.id"
          @click="activeTab = tab.id"
          :class="[
            'flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-lg border border-b-0 transition-colors whitespace-nowrap',
            activeTab === tab.id
              ? 'bg-white text-gray-900 border-gray-200'
              : 'text-gray-500 hover:text-gray-700 border-transparent hover:bg-gray-100'
          ]"
        >
          <component :is="tab.icon" class="w-3.5 h-3.5" />
          {{ tab.label }}
        </button>
      </div>
    </header>

    <!-- Loading -->
    <div v-if="isLoading && !data" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <Loader2 class="w-10 h-10 mx-auto text-gray-400 animate-spin" />
        <p class="mt-3 text-sm text-gray-500">Loading hotel intelligence...</p>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <AlertTriangle class="w-10 h-10 mx-auto text-red-400" />
        <p class="mt-3 text-sm font-medium text-gray-900">Failed to load data</p>
        <p class="text-sm text-gray-500">{{ error }}</p>
        <button @click="loadData()" class="mt-3 px-4 py-2 text-sm text-white bg-gray-900 rounded-lg hover:bg-gray-800">Retry</button>
      </div>
    </div>

    <!-- Content -->
    <div v-else-if="data" class="flex-1 overflow-auto p-6 space-y-6">

      <!-- ==================== OVERVIEW TAB ==================== -->
      <template v-if="activeTab === 'overview'">

        <!-- KPI Cards -->
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Occupancy</span>
            <div class="text-2xl font-bold mt-1">{{ fmtPct(occupancy.occupancy_rate) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">ADR</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(occupancy.adr) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">RevPAR</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(occupancy.revpar) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Total Revenue</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(totalRevenue) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Arrivals Today</span>
            <div class="text-2xl font-bold mt-1">{{ snapshot.arrivals_today ?? 0 }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Departures Today</span>
            <div class="text-2xl font-bold mt-1">{{ snapshot.departures_today ?? 0 }}</div>
          </div>
        </div>

        <!-- Occupancy Trend + Revenue Breakdown -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
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

        <!-- Operations -->
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

        <!-- KPI Targets -->
        <div v-if="kpiTargets.length" class="bg-white rounded-lg border p-5">
          <h3 class="text-sm font-semibold text-gray-900 mb-4">KPI Performance</h3>
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
      </template>

      <!-- ==================== COST & PROFITABILITY TAB ==================== -->
      <template v-if="activeTab === 'costs'">
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
                  <div class="h-2 rounded-full" :class="cat.color === 'blue' ? 'bg-blue-500' : cat.color === 'orange' ? 'bg-orange-500' : cat.color === 'green' ? 'bg-green-500' : 'bg-purple-500'" :style="{ width: cat.percentage + '%' }"></div>
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

        <!-- Cost Trends + Breakfast Costs -->
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

        <!-- Room Expenses Detail -->
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
      </template>

      <!-- ==================== OPERATIONS TAB ==================== -->
      <template v-if="activeTab === 'operations'">
        <!-- Operational KPIs -->
        <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">GoPAR</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(opMetrics.gopar) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">RPG</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(opMetrics.rpg) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">ALOS</span>
            <div class="text-2xl font-bold mt-1">{{ opMetrics.alos ?? 0 }} nights</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Today Revenue</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(opMetrics.today_revenue) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">OOO Rooms</span>
            <div class="text-2xl font-bold mt-1">{{ opMetrics.out_of_order_rooms ?? 0 }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Lost Revenue</span>
            <div class="text-2xl font-bold mt-1 text-red-600">{{ fmt(opMetrics.potential_lost_revenue) }}</div>
          </div>
        </div>

        <!-- Check-in/Check-out + Overstays -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Check-ins Today</h3>
            <div class="grid grid-cols-3 gap-3 mb-3">
              <div class="text-center p-2 bg-blue-50 rounded">
                <div class="text-lg font-bold text-blue-700">{{ checkins.expected ?? 0 }}</div>
                <div class="text-xs text-blue-600">Expected</div>
              </div>
              <div class="text-center p-2 bg-green-50 rounded">
                <div class="text-lg font-bold text-green-700">{{ checkins.completed ?? 0 }}</div>
                <div class="text-xs text-green-600">Done</div>
              </div>
              <div class="text-center p-2 bg-yellow-50 rounded">
                <div class="text-lg font-bold text-yellow-700">{{ checkins.pending ?? 0 }}</div>
                <div class="text-xs text-yellow-600">Pending</div>
              </div>
            </div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Check-outs Today</h3>
            <div class="grid grid-cols-3 gap-3 mb-3">
              <div class="text-center p-2 bg-blue-50 rounded">
                <div class="text-lg font-bold text-blue-700">{{ checkouts.expected ?? 0 }}</div>
                <div class="text-xs text-blue-600">Expected</div>
              </div>
              <div class="text-center p-2 bg-green-50 rounded">
                <div class="text-lg font-bold text-green-700">{{ checkouts.completed ?? 0 }}</div>
                <div class="text-xs text-green-600">Done</div>
              </div>
              <div class="text-center p-2 bg-yellow-50 rounded">
                <div class="text-lg font-bold text-yellow-700">{{ checkouts.pending ?? 0 }}</div>
                <div class="text-xs text-yellow-600">Pending</div>
              </div>
            </div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Overstays</h3>
            <div class="text-center p-3 mb-3" :class="overstays.count > 0 ? 'bg-red-50 rounded' : 'bg-green-50 rounded'">
              <div class="text-2xl font-bold" :class="overstays.count > 0 ? 'text-red-700' : 'text-green-700'">{{ overstays.count ?? 0 }}</div>
              <div class="text-xs" :class="overstays.count > 0 ? 'text-red-600' : 'text-green-600'">{{ overstays.count > 0 ? 'Guests overstaying' : 'No overstays' }}</div>
            </div>
            <div v-if="overstays.details?.length" class="space-y-1">
              <div v-for="o in overstays.details.slice(0, 5)" :key="o.name" class="flex justify-between text-xs p-1.5 bg-red-50 rounded">
                <span class="text-gray-700 truncate mr-2">{{ o.guest_name }}</span>
                <span class="text-red-600 font-medium whitespace-nowrap">{{ o.overdue_days }}d overdue</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Room Utilization by Floor & Wing -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Utilization by Floor</h3>
            <div v-if="floorBreakdown.length" class="space-y-2">
              <div v-for="f in floorBreakdown" :key="f.floor" class="flex items-center gap-3">
                <span class="text-sm text-gray-600 w-20">Floor {{ f.floor }}</span>
                <div class="flex-1 bg-gray-100 rounded-full h-3">
                  <div class="bg-blue-500 h-3 rounded-full" :style="{ width: f.occupancy_rate + '%' }"></div>
                </div>
                <span class="text-sm font-medium w-16 text-right">{{ f.occupancy_rate }}%</span>
                <span class="text-xs text-gray-400 w-20 text-right">{{ f.occupied }}/{{ f.total_rooms }}</span>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No floor data</div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Utilization by Wing</h3>
            <div v-if="wingBreakdown.length" class="space-y-2">
              <div v-for="w in wingBreakdown" :key="w.wing" class="flex items-center gap-3">
                <span class="text-sm text-gray-600 w-20">{{ w.wing }}</span>
                <div class="flex-1 bg-gray-100 rounded-full h-3">
                  <div class="bg-indigo-500 h-3 rounded-full" :style="{ width: w.occupancy_rate + '%' }"></div>
                </div>
                <span class="text-sm font-medium w-16 text-right">{{ w.occupancy_rate }}%</span>
                <span class="text-xs text-gray-400 w-20 text-right">{{ w.occupied }}/{{ w.total_rooms }}</span>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No wing data</div>
          </div>
        </div>

        <!-- Bed Occupancy + Booking Patterns -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Bed Occupancy</h3>
            <div class="grid grid-cols-2 gap-4">
              <div class="text-center p-3 bg-gray-50 rounded-lg">
                <div class="text-xl font-bold">{{ fmtPct(bedOccupancy.occupancy_rate) }}</div>
                <div class="text-xs text-gray-500 mt-1">Guest Occupancy Rate</div>
              </div>
              <div class="text-center p-3 bg-gray-50 rounded-lg">
                <div class="text-xl font-bold">{{ fmtPct(bedOccupancy.beds_occupancy_rate) }}</div>
                <div class="text-xs text-gray-500 mt-1">Bed Occupancy Rate</div>
              </div>
              <div class="text-center p-3 bg-gray-50 rounded-lg">
                <div class="text-xl font-bold">{{ fmtNum(bedOccupancy.actual_guests) }}</div>
                <div class="text-xs text-gray-500 mt-1">Current Guests</div>
              </div>
              <div class="text-center p-3 bg-gray-50 rounded-lg">
                <div class="text-xl font-bold">{{ fmtNum(bedOccupancy.total_capacity) }}</div>
                <div class="text-xs text-gray-500 mt-1">Total Capacity</div>
              </div>
            </div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Booking Patterns by Day</h3>
            <div v-if="dayOfWeekPatterns.length" class="space-y-2">
              <div v-for="d in dayOfWeekPatterns" :key="d.day_name" class="flex items-center gap-3">
                <span class="text-sm text-gray-600 w-12" :class="d.is_peak ? 'font-bold text-gray-900' : ''">{{ d.day_name?.slice(0, 3) }}</span>
                <div class="flex-1 bg-gray-100 rounded-full h-2.5">
                  <div class="h-2.5 rounded-full" :class="d.is_peak ? 'bg-green-500' : 'bg-blue-400'" :style="{ width: `${(d.booking_count / maxDayBookings) * 100}%` }"></div>
                </div>
                <span class="text-sm font-medium w-10 text-right">{{ d.booking_count }}</span>
                <span class="text-xs text-gray-400 w-12 text-right">{{ d.percentage?.toFixed(0) }}%</span>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No booking pattern data</div>
          </div>
        </div>
      </template>

      <!-- ==================== GUESTS TAB ==================== -->
      <template v-if="activeTab === 'guests'">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Total Guests</span>
            <div class="text-2xl font-bold mt-1">{{ fmtNum(guestData.total_guests) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Repeat Rate</span>
            <div class="text-2xl font-bold mt-1">{{ fmtPct(guestData.repeat_guest_rate) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">VIP Guests</span>
            <div class="text-2xl font-bold mt-1">{{ guestData.vip_count ?? 0 }}</div>
            <div class="text-xs text-gray-400">{{ fmtPct(guestData.vip_percentage) }} of total</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Avg Spend</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(guestData.avg_guest_spend) }}</div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Guest Segments</h3>
            <div v-if="guestData.guest_segments?.length" class="space-y-2">
              <div v-for="seg in guestData.guest_segments" :key="seg.segment" class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="w-3 h-3 rounded-full" :class="seg.segment === 'Loyal' ? 'bg-green-500' : seg.segment === 'Returning' ? 'bg-blue-500' : 'bg-gray-400'"></div>
                  <span class="text-sm text-gray-700">{{ seg.segment }}</span>
                </div>
                <div class="text-sm">
                  <span class="font-medium">{{ seg.count }}</span>
                  <span class="text-gray-400 ml-1">({{ seg.percentage?.toFixed(1) }}%)</span>
                </div>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No segment data</div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Top Nationalities</h3>
            <div v-if="guestData.nationality_distribution?.length" class="space-y-2">
              <div v-for="nat in guestData.nationality_distribution.slice(0, 8)" :key="nat.nationality" class="flex justify-between text-sm">
                <span class="text-gray-600">{{ nat.nationality || 'Unknown' }}</span>
                <div>
                  <span class="font-medium">{{ nat.count }}</span>
                  <span class="text-gray-400 ml-1">({{ nat.percentage?.toFixed(1) }}%)</span>
                </div>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No nationality data</div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Booking Sources</h3>
            <div v-if="guestData.booking_source_distribution?.length" class="space-y-2">
              <div v-for="src in guestData.booking_source_distribution.slice(0, 8)" :key="src.source" class="flex justify-between text-sm">
                <span class="text-gray-600">{{ src.source || 'Direct' }}</span>
                <span class="font-medium">{{ src.count }} bookings</span>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No booking source data</div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Top Guests by Spend</h3>
            <div v-if="guestData.top_guests?.length" class="space-y-2">
              <div v-for="g in guestData.top_guests.slice(0, 8)" :key="g.name" class="flex justify-between text-sm">
                <span class="text-gray-600 truncate mr-2">{{ g.guest_name || g.name }}</span>
                <span class="font-medium whitespace-nowrap">{{ fmt(g.total_spent) }}</span>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No guest data</div>
          </div>
        </div>
      </template>

      <!-- ==================== RESTAURANT TAB ==================== -->
      <template v-if="activeTab === 'restaurant'">
        <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">F&B Revenue</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(restaurant.total_revenue) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">RevPASH</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(restaurant.avg_revpash) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Avg Order</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(restaurant.avg_order_value) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Table Turnover</span>
            <div class="text-2xl font-bold mt-1">{{ tableTurnover.avg_orders_per_table?.toFixed(1) ?? 0 }}/day</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Bar Revenue</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(restExtSummary.bar_revenue) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Room Service</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(restExtSummary.room_service_revenue) }}</div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Peak Hours -->
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Peak Hours Distribution</h3>
            <div v-if="peakHours.length" class="h-40 flex items-end gap-0.5">
              <div v-for="hour in peakHours" :key="hour.hour"
                class="flex-1 rounded-t transition-colors cursor-default"
                :class="(hour.order_count || hour.count) > 0 ? 'bg-green-400 hover:bg-green-500' : 'bg-gray-100'"
                :style="{ height: `${Math.max(((hour.order_count || hour.count) / maxPeakHourCount) * 100, 2)}%` }"
                :title="`${hour.hour_label || hour.hour + ':00'} — ${hour.order_count || hour.count} orders (${hour.percentage?.toFixed(1)}%)`"
              ></div>
            </div>
            <div v-else class="h-40 flex items-center justify-center text-sm text-gray-400">No peak hour data</div>
            <div v-if="peakHours.length" class="flex justify-between text-xs text-gray-400 mt-1">
              <span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>12am</span>
            </div>
          </div>

          <!-- RevPASH by Section -->
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">RevPASH by Section</h3>
            <div v-if="restaurant.revpash_by_section?.length" class="space-y-2">
              <div v-for="sec in restaurant.revpash_by_section" :key="sec.section" class="flex justify-between text-sm">
                <span class="text-gray-600">{{ sec.section }}</span>
                <span class="font-medium">{{ fmt(sec.revpash) }}</span>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No section data</div>
          </div>
        </div>

        <!-- Waiter Performance + Payment Methods -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Waiter Performance</h3>
            <div v-if="restWaiterPerf.length" class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b text-left text-gray-500">
                    <th class="py-2 font-medium">Waiter</th>
                    <th class="py-2 font-medium text-right">Orders</th>
                    <th class="py-2 font-medium text-right">Revenue</th>
                    <th class="py-2 font-medium text-right">Avg Order</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="w in restWaiterPerf" :key="w.waiter" class="border-b last:border-0">
                    <td class="py-2 text-gray-900">{{ w.waiter }}</td>
                    <td class="py-2 text-right">{{ w.orders }}</td>
                    <td class="py-2 text-right">{{ fmt(w.revenue) }}</td>
                    <td class="py-2 text-right">{{ fmt(w.avg_order) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No waiter data</div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Payment Methods</h3>
            <div v-if="restPaymentMethods.length" class="space-y-2">
              <div v-for="pm in restPaymentMethods" :key="pm.mode_of_payment" class="flex justify-between text-sm">
                <span class="text-gray-600">{{ pm.mode_of_payment }}</span>
                <div>
                  <span class="font-medium">{{ fmt(pm.total_amount) }}</span>
                  <span class="text-gray-400 ml-1">({{ pm.invoice_count }} orders)</span>
                </div>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No payment data</div>
          </div>
        </div>

        <!-- Menu Engineering Matrix -->
        <div class="bg-white rounded-lg border p-5">
          <h3 class="text-sm font-semibold text-gray-900 mb-4">Menu Engineering Matrix</h3>
          <div v-if="menuSummary.total_items">
            <div class="grid grid-cols-4 gap-3 mb-5">
              <div class="p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-center">
                <Star class="w-4 h-4 text-yellow-600 mx-auto mb-1" />
                <div class="text-xl font-bold text-yellow-700">{{ menuSummary.stars_count }}</div>
                <div class="text-xs text-yellow-600">Stars</div>
              </div>
              <div class="p-3 bg-blue-50 border border-blue-200 rounded-lg text-center">
                <HelpCircle class="w-4 h-4 text-blue-600 mx-auto mb-1" />
                <div class="text-xl font-bold text-blue-700">{{ menuSummary.puzzles_count }}</div>
                <div class="text-xs text-blue-600">Puzzles</div>
              </div>
              <div class="p-3 bg-green-50 border border-green-200 rounded-lg text-center">
                <Zap class="w-4 h-4 text-green-600 mx-auto mb-1" />
                <div class="text-xl font-bold text-green-700">{{ menuSummary.plowhorses_count }}</div>
                <div class="text-xs text-green-600">Plowhorses</div>
              </div>
              <div class="p-3 bg-red-50 border border-red-200 rounded-lg text-center">
                <Skull class="w-4 h-4 text-red-600 mx-auto mb-1" />
                <div class="text-xl font-bold text-red-700">{{ menuSummary.dogs_count }}</div>
                <div class="text-xs text-red-600">Dogs</div>
              </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div>
                <h4 class="text-xs font-medium text-gray-500 uppercase mb-2">Top Stars (promote these)</h4>
                <table class="w-full text-sm">
                  <thead><tr class="border-b text-left text-gray-500"><th class="py-1.5 font-medium">Item</th><th class="py-1.5 font-medium text-right">Qty</th><th class="py-1.5 font-medium text-right">Margin</th></tr></thead>
                  <tbody>
                    <tr v-for="item in topStars" :key="item.item_code" class="border-b last:border-0">
                      <td class="py-1.5 text-gray-900 truncate max-w-[200px]">{{ item.item_name }}</td>
                      <td class="py-1.5 text-right">{{ item.total_qty }}</td>
                      <td class="py-1.5 text-right text-green-600 font-medium">{{ fmt(item.contribution_margin) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div>
                <h4 class="text-xs font-medium text-gray-500 uppercase mb-2">Dogs (consider removing)</h4>
                <table class="w-full text-sm">
                  <thead><tr class="border-b text-left text-gray-500"><th class="py-1.5 font-medium">Item</th><th class="py-1.5 font-medium text-right">Qty</th><th class="py-1.5 font-medium text-right">Margin</th></tr></thead>
                  <tbody>
                    <tr v-for="item in topDogs" :key="item.item_code" class="border-b last:border-0">
                      <td class="py-1.5 text-gray-900 truncate max-w-[200px]">{{ item.item_name }}</td>
                      <td class="py-1.5 text-right">{{ item.total_qty }}</td>
                      <td class="py-1.5 text-right text-red-600 font-medium">{{ fmt(item.contribution_margin) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <div v-else class="text-sm text-gray-400 text-center py-8">No menu engineering data available</div>
        </div>
      </template>

      <!-- ==================== KITCHEN ANALYTICS TAB ==================== -->
      <template v-if="activeTab === 'kitchen'">
        <!-- Kitchen KPIs -->
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Kitchen Orders</span>
            <div class="text-2xl font-bold mt-1">{{ fmtNum(kitchenSummary.total_orders) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Revenue</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(kitchenSummary.revenue) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Avg Prep Time</span>
            <div class="text-2xl font-bold mt-1">{{ kitchenPrepTime.avg ?? 0 }} min</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Food Cost %</span>
            <div class="text-2xl font-bold mt-1" :class="foodCost.benchmark_status === 'good' ? 'text-green-600' : foodCost.benchmark_status === 'ok' ? 'text-yellow-600' : 'text-red-600'">
              {{ fmtPct(foodCost.cost_percentage) }}
            </div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Completion Rate</span>
            <div class="text-2xl font-bold mt-1">{{ fmtPct(kitchenSummary.completion_rate) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Avg Order Value</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(kitchenSummary.avg_order_value) }}</div>
          </div>
        </div>

        <!-- Food Cost Analysis + Prep Time -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Food Cost Analysis</h3>
            <div class="grid grid-cols-2 gap-3 mb-4">
              <div class="text-center p-3 bg-gray-50 rounded-lg">
                <div class="text-lg font-bold">{{ fmt(foodCost.total_revenue) }}</div>
                <div class="text-xs text-gray-500">Food Revenue</div>
              </div>
              <div class="text-center p-3 bg-gray-50 rounded-lg">
                <div class="text-lg font-bold">{{ fmt(foodCost.total_cost) }}</div>
                <div class="text-xs text-gray-500">Food Cost</div>
              </div>
              <div class="text-center p-3 bg-gray-50 rounded-lg">
                <div class="text-lg font-bold text-green-600">{{ fmt(foodCost.gross_margin) }}</div>
                <div class="text-xs text-gray-500">Gross Margin</div>
              </div>
              <div class="text-center p-3 bg-gray-50 rounded-lg">
                <div class="text-lg font-bold">{{ fmtPct(foodCost.gross_margin_pct) }}</div>
                <div class="text-xs text-gray-500">Margin %</div>
              </div>
            </div>
            <div class="p-2 rounded text-xs text-center" :class="foodCost.benchmark_status === 'good' ? 'bg-green-50 text-green-700' : foodCost.benchmark_status === 'ok' ? 'bg-yellow-50 text-yellow-700' : 'bg-red-50 text-red-700'">
              Food cost {{ fmtPct(foodCost.cost_percentage) }} — Benchmark: &lt;{{ foodCost.benchmark_low }}% good, {{ foodCost.benchmark_low }}-{{ foodCost.benchmark_high }}% ok, &gt;{{ foodCost.benchmark_high }}% high
            </div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Preparation Time</h3>
            <div class="grid grid-cols-3 gap-3 mb-4">
              <div class="text-center p-3 bg-gray-50 rounded-lg">
                <div class="text-lg font-bold">{{ kitchenPrepTime.avg ?? 0 }}m</div>
                <div class="text-xs text-gray-500">Average</div>
              </div>
              <div class="text-center p-3 bg-gray-50 rounded-lg">
                <div class="text-lg font-bold text-green-600">{{ kitchenPrepTime.min ?? 0 }}m</div>
                <div class="text-xs text-gray-500">Fastest</div>
              </div>
              <div class="text-center p-3 bg-gray-50 rounded-lg">
                <div class="text-lg font-bold text-red-600">{{ kitchenPrepTime.max ?? 0 }}m</div>
                <div class="text-xs text-gray-500">Slowest</div>
              </div>
            </div>
            <div v-if="kitchenPrepTime.per_item?.length">
              <h4 class="text-xs font-medium text-gray-500 uppercase mb-2">Slowest Items</h4>
              <div class="space-y-1">
                <div v-for="item in kitchenPrepTime.per_item.slice(0, 5)" :key="item.item_code" class="flex justify-between text-sm">
                  <span class="text-gray-600 truncate mr-2">{{ item.item_name }}</span>
                  <span class="font-medium whitespace-nowrap">{{ item.avg_minutes }}m avg</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Peak Hours + Top Items -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Kitchen Peak Hours</h3>
            <div v-if="kitchenPeakHours.length" class="h-36 flex items-end gap-0.5">
              <div v-for="h in kitchenPeakHours" :key="h.hour"
                class="flex-1 rounded-t transition-colors cursor-default"
                :class="h.orders > 0 ? 'bg-orange-400 hover:bg-orange-500' : 'bg-gray-100'"
                :style="{ height: `${Math.max((h.orders / maxKitchenHour) * 100, 2)}%` }"
                :title="`${h.label} — ${h.orders} orders`"
              ></div>
            </div>
            <div v-else class="h-36 flex items-center justify-center text-sm text-gray-400">No data</div>
            <div v-if="kitchenPeakHours.length" class="flex justify-between text-xs text-gray-400 mt-1">
              <span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>12am</span>
            </div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Top Kitchen Items</h3>
            <div v-if="kitchenTopItems.length" class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b text-left text-gray-500">
                    <th class="py-1.5 font-medium">Item</th>
                    <th class="py-1.5 font-medium text-right">Qty</th>
                    <th class="py-1.5 font-medium text-right">Revenue</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in kitchenTopItems" :key="item.item_code" class="border-b last:border-0">
                    <td class="py-1.5 text-gray-900 truncate max-w-[200px]">{{ item.item_name }}</td>
                    <td class="py-1.5 text-right">{{ item.total_qty }}</td>
                    <td class="py-1.5 text-right font-medium">{{ fmt(item.total_revenue) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No item data</div>
          </div>
        </div>

        <!-- Waiter Performance + Category Breakdown -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Waiter Performance</h3>
            <div v-if="waiterPerformance.length" class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b text-left text-gray-500">
                    <th class="py-1.5 font-medium">Waiter</th>
                    <th class="py-1.5 font-medium text-right">Orders</th>
                    <th class="py-1.5 font-medium text-right">Revenue</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="w in waiterPerformance" :key="w.waiter" class="border-b last:border-0">
                    <td class="py-1.5 text-gray-900">{{ w.waiter }}</td>
                    <td class="py-1.5 text-right">{{ w.orders }}</td>
                    <td class="py-1.5 text-right font-medium">{{ fmt(w.revenue) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No waiter data</div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Category Breakdown</h3>
            <div v-if="categoryBreakdown.length" class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b text-left text-gray-500">
                    <th class="py-1.5 font-medium">Category</th>
                    <th class="py-1.5 font-medium text-right">Items</th>
                    <th class="py-1.5 font-medium text-right">Qty</th>
                    <th class="py-1.5 font-medium text-right">Revenue</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="cat in categoryBreakdown" :key="cat.category" class="border-b last:border-0">
                    <td class="py-1.5 text-gray-900">{{ cat.category }}</td>
                    <td class="py-1.5 text-right">{{ cat.item_count }}</td>
                    <td class="py-1.5 text-right">{{ fmtNum(cat.total_qty) }}</td>
                    <td class="py-1.5 text-right font-medium">{{ fmt(cat.revenue) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No category data</div>
          </div>
        </div>
      </template>

      <!-- ==================== EVENTS TAB ==================== -->
      <template v-if="activeTab === 'events'">
        <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Total Events</span>
            <div class="text-2xl font-bold mt-1">{{ events.total_events ?? eventExtSummary.total_events ?? 0 }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Event Revenue</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(events.total_revenue || eventExtSummary.total_revenue) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Avg/Event</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(events.avg_revenue_per_event || eventExtSummary.avg_event_value) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Material Cost</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(eventExtSummary.total_material_cost) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Commission</span>
            <div class="text-2xl font-bold mt-1">{{ fmt(eventCommission.total_commission) }}</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Outstanding</span>
            <div class="text-2xl font-bold mt-1 text-red-600">{{ fmt(eventExtSummary.outstanding) }}</div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Upcoming Events -->
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Upcoming Events</h3>
            <div v-if="upcomingEvents.length" class="space-y-2">
              <div v-for="evt in upcomingEvents.slice(0, 8)" :key="evt.name" class="p-3 bg-gray-50 rounded-lg">
                <div class="flex justify-between">
                  <span class="text-sm font-medium text-gray-900">{{ evt.event_name }}</span>
                  <span class="text-sm font-medium text-gray-900">{{ fmt(evt.grand_total) }}</span>
                </div>
                <div class="text-xs text-gray-500 mt-1">{{ evt.event_type }} &middot; {{ evt.total_expected_guests }} guests</div>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No upcoming events</div>
          </div>

          <!-- Top Events by Revenue -->
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Top Events by Revenue</h3>
            <div v-if="eventTopEvents.length" class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b text-left text-gray-500">
                    <th class="py-1.5 font-medium">Event</th>
                    <th class="py-1.5 font-medium text-right">Revenue</th>
                    <th class="py-1.5 font-medium text-right">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="e in eventTopEvents.slice(0, 8)" :key="e.name" class="border-b last:border-0">
                    <td class="py-1.5 text-gray-900 truncate max-w-[200px]">{{ e.event_name }}</td>
                    <td class="py-1.5 text-right font-medium">{{ fmt(e.revenue) }}</td>
                    <td class="py-1.5 text-right text-red-600">{{ fmt(e.material_cost) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No event data</div>
          </div>
        </div>

        <!-- Event Type + Hall Utilization + Cost by Type -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">By Event Type</h3>
            <div v-if="events.by_type?.length" class="space-y-2">
              <div v-for="t in events.by_type" :key="t.event_type" class="flex justify-between text-sm">
                <span class="text-gray-600">{{ t.event_type }}</span>
                <div>
                  <span class="font-medium">{{ t.count }}</span>
                  <span class="text-gray-400 ml-2">{{ fmt(t.revenue) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-4">No data</div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Hall Utilization</h3>
            <div v-if="events.hall_utilization?.length" class="space-y-2">
              <div v-for="h in events.hall_utilization" :key="h.hall_name" class="flex justify-between text-sm">
                <span class="text-gray-600">{{ h.hall_name }}</span>
                <span class="font-medium" :class="h.utilization_rate > 50 ? 'text-green-600' : 'text-yellow-600'">
                  {{ h.utilization_rate?.toFixed(1) }}%
                </span>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-4">No hall data</div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Material Cost by Type</h3>
            <div v-if="eventCostByType.length" class="space-y-2">
              <div v-for="c in eventCostByType" :key="c.event_type" class="flex justify-between text-sm">
                <span class="text-gray-600">{{ c.event_type }}</span>
                <span class="font-medium text-red-600">{{ fmt(c.material_cost) }}</span>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-4">No cost data</div>
          </div>
        </div>
      </template>

      <!-- ==================== FORECAST TAB ==================== -->
      <template v-if="activeTab === 'forecast'">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Forecast Period</span>
            <div class="text-2xl font-bold mt-1">{{ demandForecast.forecast_days ?? 0 }} days</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Avg Forecast Occ.</span>
            <div class="text-2xl font-bold mt-1">{{ avgForecastOccupancy.toFixed(1) }}%</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Peak Day</span>
            <div class="text-lg font-bold mt-1">{{ peakForecastDay?.day_name ?? 'N/A' }}</div>
            <div class="text-xs text-gray-400">{{ peakForecastDay?.forecast_occupancy?.toFixed(1) }}%</div>
          </div>
          <div class="bg-white rounded-lg border p-4">
            <span class="text-xs font-medium text-gray-500 uppercase">Historical Days</span>
            <div class="text-2xl font-bold mt-1">{{ demandForecast.historical_days ?? 0 }}</div>
          </div>
        </div>

        <!-- Forecast Chart -->
        <div class="bg-white rounded-lg border p-5">
          <h3 class="text-sm font-semibold text-gray-900 mb-4">30-Day Occupancy Forecast</h3>
          <div v-if="forecastDays.length" class="h-56 flex items-end gap-0.5">
            <div
              v-for="(day, idx) in forecastDays" :key="idx"
              class="flex-1 rounded-t transition-colors cursor-default relative group"
              :class="day.forecast_occupancy > avgForecastOccupancy ? 'bg-indigo-500 hover:bg-indigo-600' : 'bg-indigo-300 hover:bg-indigo-400'"
              :style="{ height: `${Math.max((day.forecast_occupancy / maxForecastOccupancy) * 100, 3)}%` }"
              :title="`${day.date} (${day.day_name}): ${day.forecast_occupancy?.toFixed(1)}% [${day.lower_bound?.toFixed(1)}-${day.upper_bound?.toFixed(1)}%]`"
            ></div>
          </div>
          <div v-else class="h-56 flex items-center justify-center text-sm text-gray-400">No forecast data</div>
          <div v-if="forecastDays.length" class="flex justify-between text-xs text-gray-400 mt-2">
            <span>{{ forecastDays[0]?.date }}</span>
            <span>{{ forecastDays[Math.floor(forecastDays.length/2)]?.date }}</span>
            <span>{{ forecastDays[forecastDays.length - 1]?.date }}</span>
          </div>
        </div>

        <!-- Day-of-Week + Room Type Demand -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Demand by Day of Week</h3>
            <div v-if="demandForecast.seasonal_patterns?.by_day_of_week" class="space-y-2">
              <div v-for="dow in demandForecast.seasonal_patterns.by_day_of_week" :key="dow.day" class="flex items-center gap-3">
                <span class="text-sm text-gray-600 w-12">{{ dow.day_name?.slice(0, 3) }}</span>
                <div class="flex-1 bg-gray-100 rounded-full h-2.5">
                  <div class="bg-indigo-500 h-2.5 rounded-full" :style="{ width: `${Math.min(dow.avg_occupancy * 1.5, 100)}%` }"></div>
                </div>
                <span class="text-sm font-medium w-12 text-right">{{ dow.avg_occupancy?.toFixed(1) }}%</span>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No seasonal data</div>
          </div>

          <div class="bg-white rounded-lg border p-5">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Demand by Room Type</h3>
            <div v-if="demandForecast.demand_by_room_type?.length" class="space-y-2">
              <div v-for="rt in demandForecast.demand_by_room_type" :key="rt.room_type" class="flex justify-between text-sm">
                <span class="text-gray-600">{{ rt.room_type }}</span>
                <div>
                  <span class="font-medium">{{ rt.reservation_count }} bookings</span>
                  <span class="text-gray-400 ml-2">({{ rt.demand_share_pct?.toFixed(1) }}%)</span>
                </div>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 text-center py-6">No room type demand data</div>
          </div>
        </div>

        <!-- Booking Pace -->
        <div class="bg-white rounded-lg border p-5" v-if="demandForecast.booking_pace">
          <h3 class="text-sm font-semibold text-gray-900 mb-3">Booking Pace</h3>
          <div class="grid grid-cols-2 gap-4 mb-3">
            <div class="text-center p-3 bg-gray-50 rounded-lg">
              <div class="text-xl font-bold">{{ demandForecast.booking_pace.avg_lead_time?.toFixed(0) ?? 0 }} days</div>
              <div class="text-xs text-gray-500">Avg Lead Time</div>
            </div>
            <div class="text-center p-3 bg-gray-50 rounded-lg">
              <div class="text-xl font-bold">{{ demandForecast.booking_pace.median_lead_time?.toFixed(0) ?? 0 }} days</div>
              <div class="text-xs text-gray-500">Median Lead Time</div>
            </div>
          </div>
          <div v-if="demandForecast.booking_pace.distribution?.length" class="space-y-1">
            <div v-for="b in demandForecast.booking_pace.distribution" :key="b.bucket" class="flex items-center gap-3">
              <span class="text-xs text-gray-500 w-24">{{ b.bucket }}</span>
              <div class="flex-1 bg-gray-100 rounded-full h-2">
                <div class="bg-blue-500 h-2 rounded-full" :style="{ width: b.percentage + '%' }"></div>
              </div>
              <span class="text-xs font-medium w-10 text-right">{{ b.percentage?.toFixed(0) }}%</span>
            </div>
          </div>
        </div>
      </template>

    </div>

    <!-- AI Chat -->
    <DashboardChatButton dashboard-type="Hotel" :dashboard-context="chatContext" />
  </div>
</template>
