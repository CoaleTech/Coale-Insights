<script setup>
import { computed } from 'vue'

const props = defineProps({
  operationalMetrics: { type: Object, default: () => ({}) },
  checkinCheckout: { type: Object, default: () => ({}) },
  roomUtilization: { type: Object, default: () => ({}) },
  bookingPatterns: { type: Object, default: () => ({}) },
})

// Computed helpers from existing sections
const opMetrics = computed(() => props.operationalMetrics?.metrics || {})
const checkins = computed(() => props.checkinCheckout?.checkins || {})
const checkouts = computed(() => props.checkinCheckout?.checkouts || {})
const overstays = computed(() => props.checkinCheckout?.overstays || {})
const floorBreakdown = computed(() => props.roomUtilization?.floor_breakdown || [])
const wingBreakdown = computed(() => props.roomUtilization?.wing_breakdown || [])
const bedOccupancy = computed(() => props.roomUtilization?.bed_occupancy || {})
const dayOfWeekPatterns = computed(() => props.bookingPatterns?.day_of_week_patterns || [])
const maxDayBookings = computed(() => Math.max(...dayOfWeekPatterns.value.map(d => d.booking_count || 0), 1))

// New: booking pattern summary labels
const peakDay = computed(() => {
  const days = dayOfWeekPatterns.value
  if (!days.length) return null
  return days.reduce((max, d) => (d.booking_count > (max?.booking_count || 0)) ? d : max, days[0])
})
const slowestDay = computed(() => {
  const days = dayOfWeekPatterns.value
  if (!days.length) return null
  return days.reduce((min, d) => (d.booking_count < (min?.booking_count ?? Infinity)) ? d : min, days[0])
})

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
</script>

<template>
  <div class="space-y-6">

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

    <!-- Check-in / Check-out / Overstays -->
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

    <!-- Booking Pattern Summary (new enhanced summary) -->
    <div v-if="dayOfWeekPatterns.length" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-3">Booking Pattern Summary</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div v-if="peakDay" class="p-3 bg-green-50 border border-green-200 rounded-lg flex items-center justify-between">
          <div>
            <div class="text-xs text-green-600 font-medium uppercase">Peak Day</div>
            <div class="text-lg font-bold text-green-800">{{ peakDay.day_name }}</div>
          </div>
          <div class="text-right">
            <div class="text-xl font-bold text-green-700">{{ peakDay.booking_count }}</div>
            <div class="text-xs text-green-600">bookings</div>
          </div>
        </div>
        <div v-if="slowestDay" class="p-3 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
          <div>
            <div class="text-xs text-red-600 font-medium uppercase">Slowest Day</div>
            <div class="text-lg font-bold text-red-800">{{ slowestDay.day_name }}</div>
          </div>
          <div class="text-right">
            <div class="text-xl font-bold text-red-700">{{ slowestDay.booking_count }}</div>
            <div class="text-xs text-red-600">bookings</div>
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

    <!-- Bed Occupancy + Booking Patterns by Day -->
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

  </div>
</template>
