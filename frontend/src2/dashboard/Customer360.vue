<script setup lang="tsx">
import { Breadcrumbs, ListView, FormControl } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { 
  Search, Loader2, Star, AlertTriangle, Filter
} from 'lucide-vue-next'
import { computed, onMounted, ref, watch, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
import { createToast } from '../helpers/toasts'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'

const router = useRouter()

// State
const isLoading = ref(true)
const searchQuery = ref('')
const selectedTier = ref<string>('all')
const selectedRfmSegment = ref<string>('all')
const customers = ref<any[]>([])
const filteredCustomers = ref<any[]>([])
const recentCustomers = ref<string[]>([])
const dateFilter = ref('12m')
const baseCurrency = ref('KES')

// Tier options
const tierOptions = [
  { value: 'all', label: 'All Tiers' },
  { value: 'Diamond', label: '💎 Diamond' },
  { value: 'Platinum', label: '🥇 Platinum' },
  { value: 'Gold', label: '🥈 Gold' },
  { value: 'Silver', label: '🥉 Silver' },
  { value: 'Bronze', label: '🏅 Bronze' },
]

// RFM Segment options
const rfmSegmentOptions = [
  { value: 'all', label: 'All Segments' },
  { value: 'Champions', label: '🏆 Champions' },
  { value: 'Loyal Customers', label: '💙 Loyal Customers' },
  { value: 'Potential Loyalists', label: '🌟 Potential Loyalists' },
  { value: 'New Customers', label: '🆕 New Customers' },
  { value: 'Promising', label: '📈 Promising' },
  { value: 'Need Attention', label: '⚠️ Need Attention' },
  { value: 'About to Sleep', label: '😴 About to Sleep' },
  { value: 'At Risk', label: '🔴 At Risk' },
  { value: "Can't Lose", label: '💎 Can\'t Lose' },
  { value: 'Hibernating', label: '❄️ Hibernating' },
  { value: 'Lost', label: '👻 Lost' },
]

// Load customers with CLV data
async function loadCustomers() {
  isLoading.value = true
  try {
    const result = await apiCall('insights.api.ml.customer_intelligence', {
      date_filter: dateFilter.value
    })
    customers.value = result?.customers || []
    if (result?.base_currency) {
      baseCurrency.value = result.base_currency
    }
    filterCustomers()
  } catch (e: any) {
    console.error('Failed to load customers:', e)
    createToast({
      title: 'Error',
      message: 'Failed to load customer list',
      variant: 'error'
    })
  } finally {
    isLoading.value = false
  }
}

// Filter customers based on search, tier, and RFM segment
function filterCustomers() {
  let result = [...customers.value]
  
  // Filter by CLV tier
  if (selectedTier.value !== 'all') {
    result = result.filter(c => c.clv_tier === selectedTier.value)
  }
  
  // Filter by RFM segment
  if (selectedRfmSegment.value !== 'all') {
    result = result.filter(c => c.rfm_segment === selectedRfmSegment.value)
  }
  
  // Filter by search query
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(c => 
      c.customer_name?.toLowerCase().includes(query) ||
      c.customer_id?.toLowerCase().includes(query) ||
      c.territory?.toLowerCase().includes(query) ||
      c.rfm_segment?.toLowerCase().includes(query)
    )
  }
  
  // Sort by CLV descending
  result.sort((a, b) => (b.historical_clv || 0) - (a.historical_clv || 0))
  
  filteredCustomers.value = result
}

// Navigate to customer detail
function viewCustomer(customerId: string) {
  // Save to recent customers
  const recent = JSON.parse(localStorage.getItem('recentCustomers') || '[]')
  const updated = [customerId, ...recent.filter((id: string) => id !== customerId)].slice(0, 5)
  localStorage.setItem('recentCustomers', JSON.stringify(updated))
  recentCustomers.value = updated
  
  router.push(`/customer/${customerId}`)
}

// Load recent customers from localStorage
function loadRecentCustomers() {
  recentCustomers.value = JSON.parse(localStorage.getItem('recentCustomers') || '[]')
}

// Format currency
function formatCurrency(value: number | undefined): string {
  if (value === undefined || value === null) return `${baseCurrency.value} 0`
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: baseCurrency.value,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

// Get tier color
function getTierColor(tier: string): string {
  const colors: Record<string, string> = {
    'Diamond': 'bg-purple-600',
    'Platinum': 'bg-gray-700',
    'Gold': 'bg-yellow-500',
    'Silver': 'bg-gray-400',
    'Bronze': 'bg-amber-700'
  }
  return colors[tier] || 'bg-gray-500'
}

// Get tier icon
function getTierIcon(tier: string): string {
  const icons: Record<string, string> = {
    'Diamond': '💎',
    'Platinum': '🥇',
    'Gold': '🥈',
    'Silver': '🥉',
    'Bronze': '🏅'
  }
  return icons[tier] || '👤'
}

// Get health color class
function getHealthBgColor(status: string): string {
  const colors: Record<string, string> = {
    'Excellent': 'bg-green-500',
    'Good': 'bg-blue-500',
    'Average': 'bg-yellow-500',
    'Poor': 'bg-orange-500',
    'Critical': 'bg-red-500'
  }
  return colors[status] || 'bg-gray-400'
}

// Watch for filter changes
watch([searchQuery, selectedTier, selectedRfmSegment], () => {
  filterCustomers()
})

// Computed: Recent customers with details
const recentCustomerDetails = computed(() => {
  return recentCustomers.value
    .map(id => customers.value.find(c => c.customer_id === id))
    .filter(Boolean)
})

// Chat context
const chatContext = computed(() => ({
  page: 'Customer 360 Search',
  totalCustomers: customers.value.length,
  filteredCount: filteredCustomers.value.length,
  selectedTier: selectedTier.value
}))

// Get RFM segment color
function getRfmColor(segment: string): string {
  const colors: Record<string, string> = {
    'Champions': 'bg-purple-100 text-purple-800',
    'Loyal Customers': 'bg-blue-100 text-blue-800',
    'Potential Loyalists': 'bg-cyan-100 text-cyan-800',
    'New Customers': 'bg-green-100 text-green-800',
    'Promising': 'bg-teal-100 text-teal-800',
    'Need Attention': 'bg-yellow-100 text-yellow-800',
    'About to Sleep': 'bg-orange-100 text-orange-800',
    'At Risk': 'bg-red-100 text-red-800',
    "Can't Lose": 'bg-pink-100 text-pink-800',
    'Hibernating': 'bg-gray-100 text-gray-600',
    'Lost': 'bg-gray-200 text-gray-500',
  }
  return colors[segment] || 'bg-gray-100 text-gray-600'
}

// ListView configuration
const listOptions = ref({
  columns: [
    {
      label: 'Customer',
      key: 'customer_name',
      width: 2.5,
      prefix: (props: any) => {
        const customer = props.row
        return <span class="text-xl mr-2">{getTierIcon(customer.clv_tier)}</span>
      },
    },
    {
      label: 'RFM Segment',
      key: 'rfm_segment',
      width: 2,
      prefix: (props: any) => {
        const segment = props.row.rfm_segment || 'Unknown'
        return (
          <span class={`px-2 py-0.5 text-xs font-medium rounded ${getRfmColor(segment)}`}>
            {segment}
          </span>
        )
      },
      getLabel: () => '',
    },
    {
      label: 'CLV Tier',
      key: 'clv_tier',
      width: 1.5,
      prefix: (props: any) => {
        const customer = props.row
        return (
          <span class={`px-2 py-0.5 text-xs font-medium text-white rounded-full ${getTierColor(customer.clv_tier)}`}>
            {customer.clv_tier}
          </span>
        )
      },
      getLabel: () => '',
    },
    {
      label: 'Lifetime Value',
      key: 'historical_clv',
      width: 1.5,
      align: 'right',
      getLabel: (props: any) => formatCurrency(props.row.historical_clv),
    },
    {
      label: 'Health',
      key: 'health_status',
      width: 1.5,
      prefix: (props: any) => {
        const status = props.row.health_status
        return <span class={`w-2 h-2 rounded-full inline-block mr-2 ${getHealthBgColor(status)}`}></span>
      },
      getLabel: (props: any) => props.row.health_status || 'Unknown',
    },
    {
      label: 'Churn Risk',
      key: 'churn_risk',
      width: 1.5,
      prefix: (props: any) => {
        const risk = props.row.churn_risk
        if (risk === 'High' || risk === 'Critical') {
          return <AlertTriangle class="h-4 w-4 text-red-500 mr-1" />
        }
        return null
      },
      getLabel: (props: any) => props.row.churn_risk || '-',
    },
  ],
  rows: filteredCustomers,
  rowKey: 'customer_id',
  options: {
    showTooltip: false,
    getRowRoute: (customer: any) => ({
      path: `/customer/${customer.customer_id}`,
    }),
    onRowClick: (customer: any) => {
      viewCustomer(customer.customer_id)
    },
    emptyState: {
      title: 'No Customers Found',
      description: 'No customers available.',
    },
  },
})

watchEffect(() => {
  document.title = 'Customer 360° | Insights'
})

onMounted(() => {
  loadRecentCustomers()
  loadCustomers()
})

// Watch for date filter changes
watch(dateFilter, () => {
  loadCustomers()
})
</script>

<template>
  <header class="flex h-12 items-center justify-between border-b py-2.5 pl-5 pr-2">
    <Breadcrumbs :items="[
      { label: 'Insights', route: { name: 'DashboardList' } },
      { label: 'Customer 360°', route: { name: 'Customer360' } }
    ]" />
    <div class="flex items-center gap-4">
      <IntelligenceDateFilter v-model="dateFilter" />
      <span class="text-sm text-gray-500">
        {{ filteredCustomers.length }} of {{ customers.length }} customers
      </span>
    </div>
  </header>

  <div class="mb-4 flex h-full flex-col gap-3 overflow-auto px-5 py-3">
    <!-- Search & Filters -->
    <div class="flex gap-2 overflow-visible py-1">
      <FormControl 
        placeholder="Search by name, ID, or territory..." 
        v-model="searchQuery" 
        :debounce="300"
        class="w-80"
      >
        <template #prefix>
          <Search class="h-4 w-4 text-gray-500" />
        </template>
      </FormControl>
      
      <div class="flex items-center gap-2">
        <Filter class="h-4 w-4 text-gray-400" />
        <select
          v-model="selectedTier"
          class="px-3 py-1.5 text-sm border rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option v-for="opt in tierOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <select
          v-model="selectedRfmSegment"
          class="px-3 py-1.5 text-sm border rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option v-for="opt in rfmSegmentOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </div>
    </div>

    <!-- Recent Customers -->
    <div v-if="recentCustomerDetails.length > 0 && !searchQuery && selectedTier === 'all' && selectedRfmSegment === 'all'" class="mb-2">
      <div class="flex items-center gap-2 mb-2">
        <Star class="h-4 w-4 text-yellow-500" />
        <span class="text-sm font-medium text-gray-700">Recent Customers</span>
      </div>
      <div class="flex gap-2 flex-wrap">
        <button
          v-for="customer in recentCustomerDetails"
          :key="customer.customer_id"
          @click="viewCustomer(customer.customer_id)"
          class="flex items-center gap-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
        >
          <span>{{ getTierIcon(customer.clv_tier) }}</span>
          <span class="text-sm text-blue-700">{{ customer.customer_name }}</span>
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="flex items-center justify-center h-64">
      <div class="text-center">
        <Loader2 class="w-8 h-8 mx-auto text-blue-500 animate-spin" />
        <p class="mt-4 text-gray-500">Loading customers...</p>
      </div>
    </div>

    <!-- Customer List -->
    <ListView v-else class="h-full" v-bind="listOptions" />
  </div>

  <!-- AI Chat Button -->
  <DashboardChatButton
    dashboard-type="Customer"
    :dashboard-context="chatContext"
  />
</template>
