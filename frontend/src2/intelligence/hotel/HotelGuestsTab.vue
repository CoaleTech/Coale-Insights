<script setup>
import { computed } from 'vue'

const props = defineProps({
  guestData: { type: Object, default: () => ({}) },
  // New keys from backend extension (all arrays per API contract)
  guestRetention: { type: Array, default: () => [] },
  checkinPunctuality: { type: Array, default: () => [] },
  guestAcquisitionTrend: { type: Array, default: () => [] },
  corporateVsIndividual: { type: Array, default: () => [] },
})

// Max for acquisition trend chart
const maxAcquisitionCount = computed(() => {
  const trend = props.guestAcquisitionTrend
  return Math.max(...trend.map(t => (t.new_guests || 0) + (t.returning_guests || 0)), 1)
})

// Punctuality: backend returns array [{ punctuality: "Early/On-time", count: 85 }, ...]
// Map to display items with styling
const punctualityStyleMap = {
  'Early/On-time': { bgClass: 'bg-green-50 border-green-200', textClass: 'text-green-700' },
  'Slightly Late':  { bgClass: 'bg-yellow-50 border-yellow-200', textClass: 'text-yellow-700' },
  'Late':           { bgClass: 'bg-red-50 border-red-200', textClass: 'text-red-700' },
  'No Data':        { bgClass: 'bg-gray-50 border-gray-200', textClass: 'text-gray-500' },
}
const punctualityTotal = computed(() =>
  props.checkinPunctuality.reduce((s, i) => s + (i.count || 0), 0) || 1
)
const punctualityItems = computed(() =>
  props.checkinPunctuality
    .filter(i => i.punctuality !== 'No Data' && i.count > 0)
    .map(i => ({
      label: i.punctuality,
      count: i.count,
      pct: ((i.count / punctualityTotal.value) * 100).toFixed(1),
      ...(punctualityStyleMap[i.punctuality] || { bgClass: 'bg-gray-50 border-gray-200', textClass: 'text-gray-600' }),
    }))
)

// Retention: backend returns array [{ retention_category: "One-time", guest_count: 120, avg_revenue: 2500, total_revenue: 300000 }, ...]
const retentionColorMap = {
  'One-time': 'bg-blue-500',
  'Returning': 'bg-indigo-500',
  'Frequent': 'bg-green-500',
  'Loyal': 'bg-yellow-500',
}
const retentionTotal = computed(() =>
  props.guestRetention.reduce((s, i) => s + (i.guest_count || 0), 0) || 1
)
const retentionCategories = computed(() =>
  props.guestRetention.map(r => ({
    label: r.retention_category,
    count: r.guest_count || 0,
    pct: ((r.guest_count / retentionTotal.value) * 100),
    avgRevenue: r.avg_revenue || 0,
    color: retentionColorMap[r.retention_category] || 'bg-purple-500',
  }))
)

// Corporate vs Individual: backend returns array [{ check_in_type: "Corporate", count: 42, total_revenue: 210000, avg_revenue: 5000 }, ...]
const corpEntry = computed(() => props.corporateVsIndividual.find(e => e.check_in_type === 'Corporate') || null)
const indivEntry = computed(() => props.corporateVsIndividual.find(e => e.check_in_type === 'Individual') || null)
const maxCorpIndiv = computed(() => Math.max(corpEntry.value?.total_revenue || 0, indivEntry.value?.total_revenue || 0, 1))

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

    <!-- Guest KPI Cards -->
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

    <!-- Guest Segments + Top Nationalities -->
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

    <!-- Booking Sources + Top Guests by Spend -->
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

    <!-- Guest Acquisition Trend (new - new vs returning over time) -->
    <div v-if="guestAcquisitionTrend.length" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-2">Guest Acquisition Trend</h3>
      <div class="flex items-center gap-4 mb-4 text-xs text-gray-500">
        <div class="flex items-center gap-1.5"><div class="w-3 h-3 rounded-full bg-blue-500"></div><span>New Guests</span></div>
        <div class="flex items-center gap-1.5"><div class="w-3 h-3 rounded-full bg-green-500"></div><span>Returning Guests</span></div>
      </div>
      <div class="h-40 flex items-end gap-0.5">
        <div v-for="(t, idx) in guestAcquisitionTrend" :key="idx" class="flex-1 flex items-end gap-px">
          <!-- Stacked bar: new (blue) + returning (green) -->
          <div class="flex-1 flex flex-col items-center justify-end h-full gap-0">
            <div
              class="w-full bg-blue-400 hover:bg-blue-600 transition-colors cursor-default"
              :style="{ height: `${Math.max(((t.new_guests || 0) / maxAcquisitionCount) * 100, t.new_guests ? 2 : 0)}%` }"
              :title="`${t.date || t.period}: ${t.new_guests} new`"
            ></div>
            <div
              class="w-full bg-green-400 hover:bg-green-600 transition-colors cursor-default"
              :style="{ height: `${Math.max(((t.returning_guests || 0) / maxAcquisitionCount) * 100, t.returning_guests ? 2 : 0)}%` }"
              :title="`${t.date || t.period}: ${t.returning_guests} returning`"
            ></div>
          </div>
        </div>
      </div>
      <div class="flex justify-between text-xs text-gray-400 mt-1">
        <span>{{ guestAcquisitionTrend[0]?.date || guestAcquisitionTrend[0]?.period }}</span>
        <span>{{ guestAcquisitionTrend[Math.floor(guestAcquisitionTrend.length / 2)]?.date || '' }}</span>
        <span>{{ guestAcquisitionTrend[guestAcquisitionTrend.length - 1]?.date || guestAcquisitionTrend[guestAcquisitionTrend.length - 1]?.period }}</span>
      </div>
    </div>

    <!-- Check-in Punctuality (new from Guests report) -->
    <div v-if="punctualityItems.length" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-4">Check-in Punctuality</h3>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div v-for="item in punctualityItems" :key="item.label"
          class="p-4 rounded-xl border" :class="item.bgClass">
          <p class="text-sm font-medium" :class="item.textClass">{{ item.label }}</p>
          <p class="text-3xl font-bold text-gray-900 mt-1">{{ item.count }}</p>
          <p class="text-xs text-gray-500 mt-0.5">{{ item.pct }}% of check-ins</p>
        </div>
      </div>
    </div>

    <!-- Guest Retention Analysis (new from Guests report) -->
    <div v-if="retentionCategories.length" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-4">Guest Retention Analysis</h3>
      <div class="space-y-3">
        <div v-for="cat in retentionCategories" :key="cat.label">
          <div class="flex justify-between text-sm mb-1">
            <span class="text-gray-700 font-medium">{{ cat.label }}</span>
            <span class="text-gray-600">{{ fmtNum(cat.count) }} <span class="text-gray-400">({{ cat.pct?.toFixed(1) }}%)</span></span>
          </div>
          <div class="w-full bg-gray-100 rounded-full h-3">
            <div :class="cat.color" class="h-3 rounded-full transition-all" :style="{ width: `${Math.min(cat.pct, 100)}%` }"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Corporate vs Individual (new from Guests report) -->
    <!-- corporateVsIndividual is an array: [{ check_in_type, count, total_revenue, avg_revenue }, ...] -->
    <div v-if="corpEntry || indivEntry" class="bg-white rounded-lg border p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-4">Corporate vs Individual</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="space-y-3">
          <!-- Corporate -->
          <div v-if="corpEntry" class="p-4 rounded-lg bg-blue-50 border border-blue-200">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-semibold text-blue-800">Corporate</span>
              <span class="text-xs text-blue-600">{{ corpEntry.count ?? 0 }} guests</span>
            </div>
            <div class="text-2xl font-bold text-blue-900">{{ fmt(corpEntry.total_revenue) }}</div>
            <div class="mt-2 w-full bg-blue-200 rounded-full h-2">
              <div class="bg-blue-500 h-2 rounded-full" :style="{ width: `${((corpEntry.total_revenue || 0) / maxCorpIndiv) * 100}%` }"></div>
            </div>
          </div>
          <!-- Individual -->
          <div v-if="indivEntry" class="p-4 rounded-lg bg-green-50 border border-green-200">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-semibold text-green-800">Individual</span>
              <span class="text-xs text-green-600">{{ indivEntry.count ?? 0 }} guests</span>
            </div>
            <div class="text-2xl font-bold text-green-900">{{ fmt(indivEntry.total_revenue) }}</div>
            <div class="mt-2 w-full bg-green-200 rounded-full h-2">
              <div class="bg-green-500 h-2 rounded-full" :style="{ width: `${((indivEntry.total_revenue || 0) / maxCorpIndiv) * 100}%` }"></div>
            </div>
          </div>
        </div>

        <!-- Avg revenue comparison -->
        <div class="space-y-3">
          <div v-if="corpEntry" class="p-3 bg-gray-50 rounded-lg flex justify-between items-center">
            <span class="text-sm text-gray-600">Corporate Avg Revenue</span>
            <span class="font-bold text-gray-900">{{ fmt(corpEntry.avg_revenue) }}</span>
          </div>
          <div v-if="indivEntry" class="p-3 bg-gray-50 rounded-lg flex justify-between items-center">
            <span class="text-sm text-gray-600">Individual Avg Revenue</span>
            <span class="font-bold text-gray-900">{{ fmt(indivEntry.avg_revenue) }}</span>
          </div>
          <!-- Show all other check-in types if any -->
          <template v-for="entry in corporateVsIndividual" :key="entry.check_in_type">
            <div v-if="entry.check_in_type !== 'Corporate' && entry.check_in_type !== 'Individual'"
              class="p-3 bg-gray-50 rounded-lg flex justify-between items-center">
              <span class="text-sm text-gray-600">{{ entry.check_in_type }}</span>
              <span class="font-bold text-gray-900">{{ fmt(entry.total_revenue) }} <span class="text-xs text-gray-400">({{ entry.count }})</span></span>
            </div>
          </template>
        </div>
      </div>
    </div>

  </div>
</template>
