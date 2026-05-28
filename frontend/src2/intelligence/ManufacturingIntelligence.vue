<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <header class="bg-white border-b px-6 py-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Manufacturing Intelligence</h1>
        <p class="text-sm text-gray-500 mt-1">
          Production efficiency, OEE analysis, capacity planning, and manufacturing insights
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
        <div class="text-sm font-medium text-gray-500">OEE Score</div>
        <div class="text-2xl font-bold mt-1" :class="getOeeColor(oeeAnalysis.oee_score_pct)">
          {{ oeeAnalysis.oee_score_pct || 0 }}%
        </div>
        <div class="text-sm mt-1" :class="getOeeColor(oeeAnalysis.oee_score_pct)">
          {{ oeeAnalysis.oee_rating || '-' }}
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Availability</div>
        <div class="text-2xl font-bold text-blue-600 mt-1">
          {{ oeeAnalysis.availability_pct || 0 }}%
        </div>
        <div class="text-sm text-gray-500 mt-1">Uptime ratio</div>
      </div>

      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Completion Rate</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ productionMetrics.completion_rate_pct || 0 }}%
        </div>
        <div class="text-sm text-gray-500 mt-1">Work orders</div>
      </div>

      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Capacity Utilization</div>
        <div class="text-2xl font-bold mt-1" :class="getUtilizationColor(capacityUtilization.overall_utilization_pct)">
          {{ capacityUtilization.overall_utilization_pct || 0 }}%
        </div>
        <div class="text-sm text-gray-500 mt-1">Overall</div>
      </div>

      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Efficiency</div>
        <div class="text-2xl font-bold text-green-600 mt-1">
          {{ efficiencyMetrics.average_efficiency_pct || 0 }}%
        </div>
        <div class="text-sm text-gray-500 mt-1">{{ efficiencyMetrics.consistency_rating || '-' }}</div>
      </div>

      <div
        class="bg-white rounded-lg shadow-sm p-4 border cursor-pointer hover:ring-2 hover:ring-blue-300 transition-shadow"
        @click="drillDown.open(MFG_ENDPOINT, 'Work Orders', { metric: 'completed_work_orders' })"
      >
        <div class="text-sm font-medium text-gray-500">Work Orders</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ productionMetrics.completed_orders || 0 }}
        </div>
        <div class="text-sm text-gray-500 mt-1">of {{ productionMetrics.total_work_orders || 0 }} total</div>
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

      <!-- Overview Tab -->
      <div v-if="activeTab === 'overview'">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Production Summary -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Production Summary</h3>
            <div class="space-y-3">
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Total Work Orders</span>
                <span class="font-semibold text-gray-900">{{ productionMetrics.total_work_orders || 0 }}</span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Completed Orders</span>
                <span class="font-semibold text-green-600">{{ productionMetrics.completed_orders || 0 }}</span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Total Production Qty</span>
                <span class="font-semibold text-gray-900">{{ formatNumber(productionMetrics.total_production_qty) }}</span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Monthly Growth Rate</span>
                <span class="font-semibold" :class="(productionMetrics.monthly_growth_rate || 0) >= 0 ? 'text-green-600' : 'text-red-600'">
                  {{ productionMetrics.monthly_growth_rate || 0 }}%
                </span>
              </div>
              <div class="flex justify-between items-center py-2">
                <span class="text-sm text-gray-600">Completion Rate</span>
                <span class="font-semibold text-blue-600">{{ productionMetrics.completion_rate_pct || 0 }}%</span>
              </div>
            </div>
          </div>

          <!-- OEE Quick View -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">OEE Quick View</h3>
            <div class="space-y-4">
              <div>
                <div class="flex justify-between text-sm mb-1">
                  <span class="text-gray-600">Availability</span>
                  <span class="font-medium text-blue-600">{{ oeeAnalysis.availability_pct || 0 }}%</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-2">
                  <div class="bg-blue-500 h-2 rounded-full" :style="{ width: (oeeAnalysis.availability_pct || 0) + '%' }"></div>
                </div>
              </div>
              <div>
                <div class="flex justify-between text-sm mb-1">
                  <span class="text-gray-600">Performance</span>
                  <span class="font-medium text-green-600">{{ oeeAnalysis.performance_pct || 0 }}%</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-2">
                  <div class="bg-green-500 h-2 rounded-full" :style="{ width: (oeeAnalysis.performance_pct || 0) + '%' }"></div>
                </div>
              </div>
              <div>
                <div class="flex justify-between text-sm mb-1">
                  <span class="text-gray-600">Quality</span>
                  <span class="font-medium text-purple-600">{{ oeeAnalysis.quality_pct || 0 }}%</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-2">
                  <div class="bg-purple-500 h-2 rounded-full" :style="{ width: (oeeAnalysis.quality_pct || 0) + '%' }"></div>
                </div>
              </div>
              <div class="pt-2 border-t">
                <div class="flex justify-between text-sm mb-1">
                  <span class="font-medium text-gray-700">Overall OEE</span>
                  <span class="font-bold" :class="getOeeColor(oeeAnalysis.oee_score_pct)">{{ oeeAnalysis.oee_score_pct || 0 }}%</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-3">
                  <div
                    class="h-3 rounded-full transition-all"
                    :class="getOeeBarColor(oeeAnalysis.oee_score_pct)"
                    :style="{ width: (oeeAnalysis.oee_score_pct || 0) + '%' }"
                  ></div>
                </div>
              </div>
            </div>
          </div>

          <!-- Efficiency Metrics -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Efficiency Metrics</h3>
            <div class="space-y-3">
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Average Efficiency</span>
                <span class="font-semibold text-green-600">{{ efficiencyMetrics.average_efficiency_pct || 0 }}%</span>
              </div>
              <div class="flex justify-between items-center py-2">
                <span class="text-sm text-gray-600">Consistency Rating</span>
                <span class="font-semibold text-gray-900">{{ efficiencyMetrics.consistency_rating || '-' }}</span>
              </div>
            </div>
          </div>

          <!-- Capacity at a Glance -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Capacity at a Glance</h3>
            <div class="space-y-3">
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Overall Utilization</span>
                <span class="font-semibold" :class="getUtilizationColor(capacityUtilization.overall_utilization_pct)">
                  {{ capacityUtilization.overall_utilization_pct || 0 }}%
                </span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Available Capacity</span>
                <span class="font-semibold text-blue-600">{{ capacityUtilization.available_capacity_pct || 0 }}%</span>
              </div>
              <div class="flex justify-between items-center py-2">
                <span class="text-sm text-gray-600">Bottlenecks Identified</span>
                <span class="font-semibold text-red-600">{{ bottleneckAnalysis.bottleneck_count || 0 }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- OEE Analysis Tab -->
      <div v-if="activeTab === 'oee'">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- OEE Score Card -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-6">OEE Score Breakdown</h3>
            <div class="flex items-center justify-center mb-6">
              <div class="text-center">
                <div class="text-6xl font-bold mb-2" :class="getOeeColor(oeeAnalysis.oee_score_pct)">
                  {{ oeeAnalysis.oee_score_pct || 0 }}%
                </div>
                <div class="text-lg font-medium text-gray-600">Overall OEE</div>
                <div class="mt-2 px-4 py-1 rounded-full text-sm font-medium inline-block"
                     :class="getOeeRatingBadge(oeeAnalysis.oee_rating)">
                  {{ oeeAnalysis.oee_rating || 'Not Rated' }}
                </div>
              </div>
            </div>
            <div class="space-y-5">
              <div>
                <div class="flex justify-between text-sm font-medium mb-2">
                  <span class="text-gray-700">Availability</span>
                  <span class="text-blue-600">{{ oeeAnalysis.availability_pct || 0 }}%</span>
                </div>
                <div class="w-full bg-gray-100 rounded-full h-4">
                  <div class="bg-blue-500 h-4 rounded-full transition-all" :style="{ width: (oeeAnalysis.availability_pct || 0) + '%' }"></div>
                </div>
                <p class="text-xs text-gray-500 mt-1">Actual run time vs planned production time</p>
              </div>
              <div>
                <div class="flex justify-between text-sm font-medium mb-2">
                  <span class="text-gray-700">Performance</span>
                  <span class="text-green-600">{{ oeeAnalysis.performance_pct || 0 }}%</span>
                </div>
                <div class="w-full bg-gray-100 rounded-full h-4">
                  <div class="bg-green-500 h-4 rounded-full transition-all" :style="{ width: (oeeAnalysis.performance_pct || 0) + '%' }"></div>
                </div>
                <p class="text-xs text-gray-500 mt-1">Actual speed vs ideal/maximum speed</p>
              </div>
              <div>
                <div class="flex justify-between text-sm font-medium mb-2">
                  <span class="text-gray-700">Quality</span>
                  <span class="text-purple-600">{{ oeeAnalysis.quality_pct || 0 }}%</span>
                </div>
                <div class="w-full bg-gray-100 rounded-full h-4">
                  <div class="bg-purple-500 h-4 rounded-full transition-all" :style="{ width: (oeeAnalysis.quality_pct || 0) + '%' }"></div>
                </div>
                <p class="text-xs text-gray-500 mt-1">Good units vs total units produced</p>
              </div>
            </div>
          </div>

          <!-- Workstation Performance -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Workstation Performance</h3>
            <div v-if="workstationPerformance.length > 0" class="space-y-3 max-h-96 overflow-y-auto">
              <div
                v-for="ws in workstationPerformance"
                :key="ws.workstation"
                class="border border-gray-100 rounded-lg p-3"
              >
                <div class="flex justify-between items-center mb-2">
                  <span class="font-medium text-gray-900 text-sm">{{ ws.workstation }}</span>
                  <span class="text-sm font-semibold" :class="getOeeColor(ws.efficiency_pct)">
                    {{ ws.efficiency_pct || 0 }}%
                  </span>
                </div>
                <div class="w-full bg-gray-100 rounded-full h-2">
                  <div
                    class="h-2 rounded-full"
                    :class="getOeeBarColor(ws.efficiency_pct)"
                    :style="{ width: (ws.efficiency_pct || 0) + '%' }"
                  ></div>
                </div>
                <div class="flex justify-between text-xs text-gray-500 mt-1">
                  <span>Jobs: {{ ws.total_jobs || 0 }}</span>
                  <span>Completed: {{ ws.completed_jobs || 0 }}</span>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-12 text-gray-500">
              <p class="text-sm">No workstation data available</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Capacity Tab -->
      <div v-if="activeTab === 'capacity'">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Capacity Utilization -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-6">Capacity Utilization</h3>
            <div class="space-y-6">
              <div class="text-center py-4">
                <div class="text-5xl font-bold mb-2" :class="getUtilizationColor(capacityUtilization.overall_utilization_pct)">
                  {{ capacityUtilization.overall_utilization_pct || 0 }}%
                </div>
                <div class="text-gray-600">Overall Utilization</div>
              </div>
              <div class="space-y-3">
                <div>
                  <div class="flex justify-between text-sm font-medium mb-2">
                    <span class="text-gray-700">Used Capacity</span>
                    <span :class="getUtilizationColor(capacityUtilization.overall_utilization_pct)">
                      {{ capacityUtilization.overall_utilization_pct || 0 }}%
                    </span>
                  </div>
                  <div class="w-full bg-gray-100 rounded-full h-5">
                    <div
                      class="h-5 rounded-full transition-all"
                      :class="getUtilizationBarColor(capacityUtilization.overall_utilization_pct)"
                      :style="{ width: (capacityUtilization.overall_utilization_pct || 0) + '%' }"
                    ></div>
                  </div>
                </div>
                <div>
                  <div class="flex justify-between text-sm font-medium mb-2">
                    <span class="text-gray-700">Available Capacity</span>
                    <span class="text-blue-600">{{ capacityUtilization.available_capacity_pct || 0 }}%</span>
                  </div>
                  <div class="w-full bg-gray-100 rounded-full h-5">
                    <div
                      class="bg-blue-400 h-5 rounded-full transition-all"
                      :style="{ width: (capacityUtilization.available_capacity_pct || 0) + '%' }"
                    ></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Bottleneck Analysis -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Bottleneck Analysis</h3>
            <div class="text-center py-6 border rounded-lg mb-4"
                 :class="(bottleneckAnalysis.bottleneck_count || 0) > 0 ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'">
              <div class="text-5xl font-bold mb-2"
                   :class="(bottleneckAnalysis.bottleneck_count || 0) > 0 ? 'text-red-700' : 'text-green-700'">
                {{ bottleneckAnalysis.bottleneck_count || 0 }}
              </div>
              <div class="text-sm font-medium"
                   :class="(bottleneckAnalysis.bottleneck_count || 0) > 0 ? 'text-red-600' : 'text-green-600'">
                {{ (bottleneckAnalysis.bottleneck_count || 0) > 0 ? 'Bottlenecks Identified' : 'No Bottlenecks' }}
              </div>
            </div>
            <div v-if="bottleneckAnalysis.bottlenecks && bottleneckAnalysis.bottlenecks.length > 0" class="space-y-2">
              <h4 class="text-sm font-medium text-gray-700 mb-2">Affected Workstations</h4>
              <div
                v-for="b in bottleneckAnalysis.bottlenecks"
                :key="b.workstation || b.name"
                class="flex justify-between items-center p-2 bg-red-50 rounded border border-red-100"
              >
                <span class="text-sm text-red-800">{{ b.workstation || b.name }}</span>
                <span class="text-xs text-red-600">{{ b.utilization_pct || b.load_pct || 0 }}% load</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Production Forecast Tab -->
      <div v-if="activeTab === 'forecast'">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Production Forecast</h3>
            <div v-if="productionForecast && Object.keys(productionForecast).length > 0" class="space-y-3">
              <div
                v-for="(value, key) in productionForecast"
                :key="key"
                class="flex justify-between items-center py-2 border-b"
              >
                <span class="text-sm text-gray-600">{{ formatKey(String(key)) }}</span>
                <span class="font-semibold text-gray-900">{{ formatValue(value) }}</span>
              </div>
            </div>
            <div v-else class="text-center py-12 text-gray-500">
              <p class="text-sm">Forecast data will appear after generating an analysis.</p>
            </div>
          </div>

          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Growth Indicators</h3>
            <div class="space-y-4">
              <div class="p-4 rounded-lg" :class="(productionMetrics.monthly_growth_rate || 0) >= 0 ? 'bg-green-50' : 'bg-red-50'">
                <div class="text-sm text-gray-600 mb-1">Monthly Growth Rate</div>
                <div class="text-3xl font-bold" :class="(productionMetrics.monthly_growth_rate || 0) >= 0 ? 'text-green-700' : 'text-red-700'">
                  {{ (productionMetrics.monthly_growth_rate || 0) >= 0 ? '+' : '' }}{{ productionMetrics.monthly_growth_rate || 0 }}%
                </div>
              </div>
              <div class="p-4 bg-blue-50 rounded-lg">
                <div class="text-sm text-gray-600 mb-1">Total Production Qty</div>
                <div class="text-3xl font-bold text-blue-700">
                  {{ formatNumber(productionMetrics.total_production_qty) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Recommendations Tab -->
      <div v-if="activeTab === 'recommendations'">
        <div v-if="recommendations.length > 0" class="space-y-4">
          <div
            v-for="rec in recommendations"
            :key="rec.recommendation || rec.title"
            class="bg-white rounded-lg shadow-sm border p-6"
          >
            <div class="flex items-start justify-between mb-3">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-2">
                  <span class="px-2 py-1 text-xs font-medium rounded-full" :class="getPriorityBadge(rec.priority)">
                    {{ (rec.priority || 'MEDIUM').toUpperCase() }}
                  </span>
                  <span v-if="rec.category" class="text-sm text-gray-500">{{ rec.category }}</span>
                </div>
                <h4 class="font-semibold text-gray-900 mb-2">{{ rec.recommendation || rec.title }}</h4>
                <p v-if="rec.impact" class="text-sm text-gray-600 mb-1">{{ rec.impact }}</p>
                <p v-if="rec.action" class="text-sm text-gray-500">{{ rec.action }}</p>
                <p v-if="rec.timeframe" class="text-xs text-gray-400 mt-2">Timeline: {{ rec.timeframe }}</p>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="bg-white rounded-lg shadow-sm border p-12 text-center text-gray-500">
          <p class="text-sm">No recommendations available. Refresh to generate insights.</p>
        </div>
      </div>

    </div>

    <!-- AI Chat Button -->
    <DashboardChatButton
      dashboard-type="Manufacturing"
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
defineOptions({ name: 'ManufacturingIntelligence' })
import { ref, computed, onMounted } from 'vue'
import { Button } from 'frappe-ui'
import { useRouter } from 'vue-router'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import { useDrillDown } from './composables/useDrillDown'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'

const router = useRouter()

const drillDown = useDrillDown()
const MFG_ENDPOINT = 'insights.api.ml.manufacturing.get_manufacturing_detail'

const loading = ref(false)
const lastUpdated = ref('')
const activeTab = ref('overview')

const manufacturingData = ref<Record<string, any>>({})
const productionForecast = ref<Record<string, any>>({})

const oeeAnalysis = computed(() => manufacturingData.value.oee_analysis || {})
const productionMetrics = computed(() => manufacturingData.value.production_metrics || {})
const capacityUtilization = computed(() => manufacturingData.value.capacity_utilization || {})
const bottleneckAnalysis = computed(() => manufacturingData.value.bottleneck_analysis || {})
const efficiencyMetrics = computed(() => manufacturingData.value.efficiency_metrics || {})
const workstationPerformance = computed(
  () => manufacturingData.value.workstation_performance?.workstation_performance || []
)
const recommendations = computed(() => manufacturingData.value.recommendations || [])

const tabs = [
  { label: 'Overview', value: 'overview' },
  { label: 'OEE Analysis', value: 'oee' },
  { label: 'Capacity', value: 'capacity' },
  { label: 'Production Forecast', value: 'forecast' },
  { label: 'Recommendations', value: 'recommendations' }
]

async function refreshData() {
  loading.value = true
  try {
    const headers = {
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': (window as any).csrf_token || ''
    }
    const [overviewRes, forecastRes] = await Promise.all([
      fetch('/api/method/insights.api.ml.get_manufacturing_overview?period=YTD&refresh=1', { headers }),
      fetch('/api/method/insights.api.ml.get_production_forecast?refresh=1', { headers })
    ])
    const overviewResult = await overviewRes.json()
    const forecastResult = await forecastRes.json()

    if (overviewResult.message) {
      const data = overviewResult.message?.status === 'success'
        ? overviewResult.message
        : overviewResult.message
      manufacturingData.value = data
    }
    if (forecastResult.message) {
      productionForecast.value = forecastResult.message?.forecast || forecastResult.message || {}
    }
    lastUpdated.value = new Date().toISOString()
  } catch (error) {
    console.error('Error loading manufacturing data:', error)
  } finally {
    loading.value = false
  }
}

const formatDate = (date: string | undefined) => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('en-KE', {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  })
}

const formatNumber = (val: number | undefined) => {
  if (val === null || val === undefined) return '0'
  return new Intl.NumberFormat('en-KE').format(val)
}

const formatKey = (key: string) =>
  key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

const formatValue = (value: any) =>
  typeof value === 'number' ? formatNumber(value) : String(value ?? '')

const getOeeColor = (score: number) => {
  if (score >= 85) return 'text-green-600'
  if (score >= 65) return 'text-amber-500'
  return 'text-red-600'
}

const getOeeBarColor = (score: number) => {
  if (score >= 85) return 'bg-green-500'
  if (score >= 65) return 'bg-amber-400'
  return 'bg-red-500'
}

const getOeeRatingBadge = (rating: string) => {
  if (['World Class', 'Excellent'].includes(rating)) return 'bg-green-100 text-green-700'
  if (['Good', 'Average'].includes(rating)) return 'bg-amber-100 text-amber-700'
  return 'bg-red-100 text-red-700'
}

const getUtilizationColor = (pct: number) => {
  if (pct >= 90) return 'text-red-600'
  if (pct >= 70) return 'text-amber-500'
  return 'text-green-600'
}

const getUtilizationBarColor = (pct: number) => {
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 70) return 'bg-amber-400'
  return 'bg-green-500'
}

const getPriorityBadge = (priority: string) => {
  switch ((priority || '').toLowerCase()) {
    case 'critical': return 'bg-red-100 text-red-800'
    case 'high': return 'bg-orange-100 text-orange-800'
    case 'medium': return 'bg-amber-100 text-amber-800'
    case 'low': return 'bg-blue-100 text-blue-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}

const chatContext = computed(() => ({
  oeeAnalysis: oeeAnalysis.value,
  productionMetrics: productionMetrics.value,
  capacityUtilization: capacityUtilization.value,
  bottleneckAnalysis: bottleneckAnalysis.value,
  efficiencyMetrics: efficiencyMetrics.value,
  recommendations: recommendations.value,
  activeTab: activeTab.value,
  lastUpdated: lastUpdated.value
}))

function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    'Sales': '/sales-intelligence',
    'Financial': '/financial-intelligence',
    'Inventory': '/inventory-intelligence',
    'Procurement': '/procurement-intelligence',
    'HR': '/hr-intelligence',
    'Manufacturing': '/manufacturing-intelligence',
    'ESG': '/esg-intelligence'
  }
  if (routes[target]) router.push(routes[target])
}

onMounted(() => { refreshData() })
</script>
