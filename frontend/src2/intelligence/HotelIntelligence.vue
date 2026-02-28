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
import HotelOverviewTab from './hotel/HotelOverviewTab.vue'
import HotelCostsTab from './hotel/HotelCostsTab.vue'
import HotelOperationsTab from './hotel/HotelOperationsTab.vue'
import HotelGuestsTab from './hotel/HotelGuestsTab.vue'

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

// =================== COMPUTED DATA SECTIONS ===================

// Existing data sections
const occupancy = computed(() => data.value?.occupancy || {})
const snapshot = computed(() => occupancy.value?.today_snapshot || {})
const revenueBreakdown = computed(() => data.value?.revenue_breakdown || {})
const guestData = computed(() => data.value?.guest_analytics || {})
const restaurant = computed(() => data.value?.restaurant || {})
const events = computed(() => data.value?.events || {})
const demandForecast = computed(() => data.value?.demand_forecast || {})
const costAnalytics = computed(() => data.value?.cost_analytics || {})
const kpiData = computed(() => data.value?.kpi_data || {})
const operationalMetrics = computed(() => data.value?.operational_metrics || {})
const checkinCheckout = computed(() => data.value?.checkin_checkout || {})
const roomUtilization = computed(() => data.value?.room_utilization || {})
const bookingPatterns = computed(() => data.value?.booking_patterns || {})
const kitchenAnalytics = computed(() => data.value?.kitchen_analytics || {})
const restaurantExtended = computed(() => data.value?.restaurant_extended || {})
const eventExtended = computed(() => data.value?.event_extended || {})

// New keys from backend extension
const topCustomers = computed(() => data.value?.top_customers || [])
const paymentStatus = computed(() => data.value?.payment_status || [])
const monthlyRevenue = computed(() => data.value?.monthly_revenue || [])
const paymentMethods = computed(() => data.value?.payment_methods || [])
const guestRetention = computed(() => data.value?.guest_retention || [])
const checkinPunctuality = computed(() => data.value?.checkin_punctuality || [])
const guestAcquisitionTrend = computed(() => data.value?.guest_acquisition_trend || [])
const corporateVsIndividual = computed(() => data.value?.corporate_vs_individual || [])
const kpiTrends = computed(() => data.value?.kpi_trends || [])
const roomStatusOverview = computed(() => data.value?.room_status_overview || {})

// Revenue breakdown -- handle both old cached keys and new keys
const roomsRevenue = computed(() => revenueBreakdown.value?.rooms_revenue ?? revenueBreakdown.value?.room_revenue ?? 0)
const fnbRevenue = computed(() => revenueBreakdown.value?.fnb_revenue ?? revenueBreakdown.value?.restaurant_revenue ?? 0)
const eventsRevenue = computed(() => revenueBreakdown.value?.events_revenue ?? revenueBreakdown.value?.event_revenue ?? 0)
const otherRevenue = computed(() => revenueBreakdown.value?.other_revenue ?? 0)
const totalRevenue = computed(() => revenueBreakdown.value?.total_revenue ?? 0)

// Housekeeping
const housekeeping = computed(() => occupancy.value?.housekeeping || {})

// Restaurant helpers
const peakHours = computed(() => restaurant.value?.peak_hours || [])
const maxPeakHourCount = computed(() => Math.max(...peakHours.value.map(h => h.order_count || h.count || 0), 1))
const tableTurnover = computed(() => restaurant.value?.table_turnover || {})

// Menu engineering
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

// Upcoming events
const upcomingEvents = computed(() => events.value?.upcoming_events || [])

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
  gopar: operationalMetrics.value?.metrics?.gopar,
  cpor: kpiData.value?.financial_kpis?.cpor,
  profit_margin: costAnalytics.value?.summary?.profit_margin,
}))

// =================== DATA LOADING ===================

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

// Format helpers (used by inline tabs: restaurant, kitchen, events, forecast)
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
      <HotelOverviewTab
        v-if="activeTab === 'overview'"
        :occupancy="occupancy"
        :revenue-breakdown="revenueBreakdown"
        :kpi-data="kpiData"
        :snapshot="snapshot"
        :housekeeping="housekeeping"
        :top-customers="topCustomers"
        :room-status-overview="roomStatusOverview"
        :kpi-trends="kpiTrends"
      />

      <!-- ==================== COST & PROFITABILITY TAB ==================== -->
      <HotelCostsTab
        v-if="activeTab === 'costs'"
        :cost-analytics="costAnalytics"
        :kpi-data="kpiData"
        :revenue-breakdown="revenueBreakdown"
        :payment-status="paymentStatus"
        :monthly-revenue="monthlyRevenue"
        :payment-methods="paymentMethods"
      />

      <!-- ==================== OPERATIONS TAB ==================== -->
      <HotelOperationsTab
        v-if="activeTab === 'operations'"
        :operational-metrics="operationalMetrics"
        :checkin-checkout="checkinCheckout"
        :room-utilization="roomUtilization"
        :booking-patterns="bookingPatterns"
      />

      <!-- ==================== GUESTS TAB ==================== -->
      <HotelGuestsTab
        v-if="activeTab === 'guests'"
        :guest-data="guestData"
        :guest-retention="guestRetention"
        :checkin-punctuality="checkinPunctuality"
        :guest-acquisition-trend="guestAcquisitionTrend"
        :corporate-vs-individual="corporateVsIndividual"
      />

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
