<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <header class="bg-white border-b px-6 py-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">ESG Intelligence</h1>
        <p class="text-sm text-gray-500 mt-1">Environmental, Social & Governance analytics</p>
      </div>
      <div class="flex items-center gap-3">
        <select v-model="selectedPeriod" @change="refreshData" class="text-sm border border-gray-300 rounded-lg px-3 py-1.5">
          <option value="YTD">Year to Date</option>
          <option value="12m">Last 12 Months</option>
          <option value="6m">Last 6 Months</option>
          <option value="3m">Last 3 Months</option>
        </select>
        <span v-if="lastUpdated" class="text-sm text-gray-500">Updated: {{ formatDateTime(lastUpdated) }}</span>
        <button @click="refreshData" :disabled="isLoading" class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50">
          <RefreshCw v-if="!isLoading" class="w-4 h-4" />
          <Loader2 v-else class="w-4 h-4 animate-spin" />
          Refresh
        </button>
      </div>
    </header>

    <!-- Loading State -->
    <div v-if="isLoading && !esgData" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <Loader2 class="w-12 h-12 mx-auto text-blue-600 animate-spin" />
        <p class="mt-4 text-gray-600">Loading ESG intelligence...</p>
      </div>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <AlertTriangle class="w-12 h-12 mx-auto text-red-500" />
        <p class="mt-4 text-gray-900 font-medium">Failed to load data</p>
        <p class="text-gray-600">{{ error }}</p>
        <button @click="refreshData" class="mt-4 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700">Try Again</button>
      </div>
    </div>

    <!-- Main Content -->
    <div v-else-if="esgData" class="flex-1 overflow-auto">

      <!-- ESG Score KPI Cards -->
      <div class="p-6 pb-0">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <!-- Overall ESG Score -->
          <div class="bg-white rounded-lg shadow-sm border p-4">
            <div class="flex items-center gap-2 mb-2">
              <Target class="w-4 h-4 text-gray-600" />
              <span class="text-xs font-medium text-gray-500 uppercase tracking-wide">ESG Score</span>
            </div>
            <div class="flex items-baseline gap-2">
              <div class="text-2xl font-bold" :class="getScoreTextClass(esgScore.overall_score)">
                {{ esgScore.overall_score || 0 }}
              </div>
              <span class="text-sm font-medium" :class="getRatingColorClass(esgScore.rating)">
                {{ esgScore.rating || 'N/A' }}
              </span>
            </div>
            <p class="text-xs text-gray-500 mt-1">{{ esgScore.rating_description || 'Overall performance' }}</p>
          </div>

          <!-- Environmental Score -->
          <div class="bg-white rounded-lg shadow-sm border p-4">
            <div class="flex items-center gap-2 mb-2">
              <Leaf class="w-4 h-4 text-green-600" />
              <span class="text-xs font-medium text-gray-500 uppercase tracking-wide">Environmental</span>
            </div>
            <div class="text-2xl font-bold text-green-600">{{ esgScore.environmental_score || 0 }}</div>
            <p class="text-xs text-gray-500 mt-1">Carbon & Resource Impact</p>
          </div>

          <!-- Social Score -->
          <div class="bg-white rounded-lg shadow-sm border p-4">
            <div class="flex items-center gap-2 mb-2">
              <Users class="w-4 h-4 text-blue-600" />
              <span class="text-xs font-medium text-gray-500 uppercase tracking-wide">Social</span>
            </div>
            <div class="text-2xl font-bold text-blue-600">{{ esgScore.social_score || 0 }}</div>
            <p class="text-xs text-gray-500 mt-1">People & Community</p>
          </div>

          <!-- Governance Score -->
          <div class="bg-white rounded-lg shadow-sm border p-4">
            <div class="flex items-center gap-2 mb-2">
              <Shield class="w-4 h-4 text-purple-600" />
              <span class="text-xs font-medium text-gray-500 uppercase tracking-wide">Governance</span>
            </div>
            <div class="text-2xl font-bold text-purple-600">{{ esgScore.governance_score || 0 }}</div>
            <p class="text-xs text-gray-500 mt-1">Ethics & Compliance</p>
          </div>
        </div>
      </div>

      <!-- Environmental Impact -->
      <div class="p-6 pb-0">
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-4 border-b flex items-center gap-2">
            <Leaf class="w-5 h-5 text-green-600" />
            <h3 class="text-lg font-semibold text-gray-900">Environmental Impact</h3>
          </div>
          <div class="p-6">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div class="bg-green-50 p-4 rounded-lg">
                <div class="flex items-center justify-between mb-2">
                  <Zap class="w-5 h-5 text-green-600" />
                  <span class="text-xs font-medium text-green-700">Energy</span>
                </div>
                <p class="text-2xl font-bold text-green-800">{{ environmentalMetrics.renewable_energy_pct || 0 }}%</p>
                <p class="text-xs text-green-600 mt-1">Renewable Energy</p>
              </div>
              <div class="bg-blue-50 p-4 rounded-lg">
                <div class="flex items-center justify-between mb-2">
                  <Droplets class="w-5 h-5 text-blue-600" />
                  <span class="text-xs font-medium text-blue-700">Water</span>
                </div>
                <p class="text-2xl font-bold text-blue-800">{{ environmentalMetrics.water_recycled_pct || 0 }}%</p>
                <p class="text-xs text-blue-600 mt-1">Water Recycled</p>
              </div>
              <div class="bg-yellow-50 p-4 rounded-lg">
                <div class="flex items-center justify-between mb-2">
                  <Recycle class="w-5 h-5 text-yellow-600" />
                  <span class="text-xs font-medium text-yellow-700">Waste</span>
                </div>
                <p class="text-2xl font-bold text-yellow-800">{{ environmentalMetrics.recycled_waste_pct || 0 }}%</p>
                <p class="text-xs text-yellow-600 mt-1">Waste Recycled</p>
              </div>
              <div class="bg-gray-50 p-4 rounded-lg">
                <div class="flex items-center justify-between mb-2">
                  <Cloud class="w-5 h-5 text-gray-600" />
                  <span class="text-xs font-medium text-gray-700">Emissions</span>
                </div>
                <p class="text-2xl font-bold text-gray-800">{{ carbonFootprint.total_emissions_tco2 || 0 }}</p>
                <p class="text-xs text-gray-600 mt-1">tCO2 Footprint</p>
              </div>
            </div>

            <!-- Green Initiatives -->
            <div v-if="greenInitiatives.length > 0" class="mt-6">
              <h4 class="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide">Green Initiatives</h4>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div v-for="initiative in greenInitiatives" :key="initiative.name" class="border border-gray-200 rounded-lg p-3">
                  <div class="flex items-center justify-between mb-2">
                    <h5 class="font-medium text-gray-900 text-sm">{{ initiative.name }}</h5>
                    <span class="px-2 py-0.5 text-xs rounded-full" :class="getInitiativeStatusClass(initiative.status)">
                      {{ initiative.status }}
                    </span>
                  </div>
                  <div class="mb-2">
                    <div class="flex justify-between text-xs text-gray-500 mb-1">
                      <span>Progress</span>
                      <span>{{ initiative.progress_pct }}%</span>
                    </div>
                    <div class="w-full bg-gray-200 rounded-full h-1.5">
                      <div class="bg-green-500 h-1.5 rounded-full" :style="{ width: initiative.progress_pct + '%' }"></div>
                    </div>
                  </div>
                  <p class="text-xs text-gray-500">{{ initiative.expected_impact }}</p>
                  <p class="text-xs text-gray-400 mt-1">Target: {{ formatDate(initiative.target_completion) }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Social Responsibility + Governance Row -->
      <div class="p-6 pb-0 grid grid-cols-1 lg:grid-cols-2 gap-6">

        <!-- Social Responsibility -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-4 border-b flex items-center gap-2">
            <Users class="w-5 h-5 text-blue-600" />
            <h3 class="text-lg font-semibold text-gray-900">Social Responsibility</h3>
          </div>
          <div class="p-6 space-y-4">
            <!-- Employee Wellbeing -->
            <div class="bg-blue-50 p-4 rounded-lg">
              <h4 class="text-sm font-semibold text-blue-900 mb-3">Employee Wellbeing</h4>
              <div class="space-y-2">
                <div class="flex justify-between text-sm">
                  <span class="text-blue-700">Satisfaction Score</span>
                  <span class="font-medium text-blue-900">{{ employeeWellbeing.employee_satisfaction_score || 0 }}/5</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-blue-700">Work-Life Balance</span>
                  <span class="font-medium text-blue-900">{{ employeeWellbeing.work_life_balance_score || 0 }}/5</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-blue-700">Wellness Participation</span>
                  <span class="font-medium text-blue-900">{{ employeeWellbeing.wellness_program_enrollment || 0 }}%</span>
                </div>
              </div>
            </div>

            <!-- Diversity & Inclusion -->
            <div class="bg-purple-50 p-4 rounded-lg">
              <h4 class="text-sm font-semibold text-purple-900 mb-3">Diversity & Inclusion</h4>
              <div class="space-y-2">
                <div class="flex justify-between text-sm">
                  <span class="text-purple-700">Inclusion Index</span>
                  <span class="font-medium text-purple-900">{{ diversityMetrics.inclusion_index || 0 }}/10</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-purple-700">Diverse Hiring</span>
                  <span class="font-medium text-purple-900">{{ diversityMetrics.diverse_hiring_pct || 0 }}%</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-purple-700">Training Completion</span>
                  <span class="font-medium text-purple-900">{{ diversityMetrics.diversity_training_completion || 0 }}%</span>
                </div>
              </div>
            </div>

            <!-- Community Impact -->
            <div class="bg-green-50 p-4 rounded-lg">
              <h4 class="text-sm font-semibold text-green-900 mb-3">Community Impact</h4>
              <div class="space-y-2">
                <div class="flex justify-between text-sm">
                  <span class="text-green-700">Volunteer Participation</span>
                  <span class="font-medium text-green-900">{{ communityMetrics.volunteer_participation_pct || 0 }}%</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-green-700">Local Suppliers</span>
                  <span class="font-medium text-green-900">{{ communityMetrics.local_supplier_spend_pct || 0 }}%</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-green-700">Partnerships</span>
                  <span class="font-medium text-green-900">{{ communityMetrics.community_partnerships || 0 }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Governance & Compliance -->
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-4 border-b flex items-center gap-2">
            <Shield class="w-5 h-5 text-purple-600" />
            <h3 class="text-lg font-semibold text-gray-900">Governance & Compliance</h3>
          </div>
          <div class="p-6 space-y-4">
            <div class="grid grid-cols-3 gap-4">
              <div class="bg-purple-50 p-4 rounded-lg text-center">
                <p class="text-2xl font-bold text-purple-800">{{ governanceScore.ethics_score || 0 }}</p>
                <p class="text-xs text-purple-600 mt-1">Ethics Score</p>
              </div>
              <div class="bg-indigo-50 p-4 rounded-lg text-center">
                <p class="text-2xl font-bold text-indigo-800">{{ governanceScore.risk_score || 0 }}</p>
                <p class="text-xs text-indigo-600 mt-1">Risk Score</p>
              </div>
              <div class="bg-gray-100 p-4 rounded-lg text-center">
                <p class="text-2xl font-bold text-gray-800">{{ governanceScore.transparency_score || 0 }}</p>
                <p class="text-xs text-gray-600 mt-1">Transparency</p>
              </div>
            </div>

            <!-- Health & Safety -->
            <div class="bg-red-50 p-4 rounded-lg">
              <h4 class="text-sm font-semibold text-red-900 mb-3 flex items-center gap-2">
                <Shield class="w-4 h-4" />
                Health & Safety
              </h4>
              <div class="grid grid-cols-2 gap-4">
                <div class="text-center">
                  <p class="text-xl font-bold text-red-800">{{ safetyMetrics.safety_culture_index || 0 }}</p>
                  <p class="text-xs text-red-600">Safety Culture /10</p>
                </div>
                <div class="text-center">
                  <p class="text-xl font-bold text-red-800">{{ safetyMetrics.safety_training_completion_pct || 0 }}%</p>
                  <p class="text-xs text-red-600">Training Complete</p>
                </div>
                <div class="text-center">
                  <p class="text-xl font-bold text-red-800">{{ safetyMetrics.workplace_inspection_score || 0 }}</p>
                  <p class="text-xs text-red-600">Inspection /10</p>
                </div>
                <div class="text-center">
                  <p class="text-xl font-bold text-red-800">{{ safetyMetrics.lost_time_injury_rate || 0 }}</p>
                  <p class="text-xs text-red-600">Lost Time Injuries</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ESG Recommendations -->
      <div v-if="recommendations.length > 0" class="p-6 pb-0">
        <div class="bg-white rounded-lg shadow-sm border">
          <div class="p-4 border-b flex items-center gap-2">
            <Target class="w-5 h-5 text-orange-600" />
            <h3 class="text-lg font-semibold text-gray-900">Improvement Recommendations</h3>
          </div>
          <div class="p-6">
            <div class="space-y-3">
              <div v-for="rec in recommendations" :key="rec.recommendation" class="border border-gray-200 rounded-lg p-4">
                <div class="flex items-center gap-2 mb-2">
                  <span class="px-2 py-0.5 text-xs font-medium rounded-full" :class="getPriorityColorClass(rec.priority)">
                    {{ rec.priority?.toUpperCase() || 'MEDIUM' }}
                  </span>
                  <span class="text-xs text-gray-500">{{ rec.category }}</span>
                </div>
                <h4 class="font-medium text-gray-900 text-sm mb-1">{{ rec.recommendation }}</h4>
                <p class="text-xs text-gray-600">{{ rec.impact }}</p>
                <p class="text-xs text-gray-400 mt-1">Timeline: {{ rec.timeframe }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Bottom padding -->
      <div class="p-6"></div>
    </div>

    <!-- Floating Chat Button -->
    <DashboardChatButton
      dashboard-type="ESG"
      :dashboard-context="chatContext"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import {
  Leaf, Users, Shield, Zap, Droplets, Recycle, Cloud, Target,
  RefreshCw, Loader2, AlertTriangle
} from 'lucide-vue-next'
import { apiCall } from '../helpers/api'
import DashboardChatButton from '../components/DashboardChatButton.vue'

// State
const isLoading = ref(false)
const error = ref(null)
const esgData = ref(null)
const selectedPeriod = ref('YTD')
const lastUpdated = ref(null)

// Computed properties
const esgScore = computed(() => esgData.value?.esg_score || {})
const environmentalMetrics = computed(() => {
  const env = esgData.value?.environmental_metrics || {}
  return {
    renewable_energy_pct: env.energy_consumption?.renewable_energy_pct || 0,
    water_recycled_pct: env.water_usage?.water_recycled_pct || 0,
    recycled_waste_pct: env.waste_management?.recycled_waste_pct || 0,
  }
})
const carbonFootprint = computed(() => esgData.value?.carbon_footprint || {})
const greenInitiatives = computed(() => esgData.value?.environmental_metrics?.green_initiatives || [])
const employeeWellbeing = computed(() => esgData.value?.social_metrics?.employee_wellbeing || {})
const diversityMetrics = computed(() => esgData.value?.social_metrics?.diversity_inclusion || {})
const communityMetrics = computed(() => esgData.value?.social_metrics?.community_involvement || {})
const safetyMetrics = computed(() => esgData.value?.social_metrics?.health_safety || {})
const governanceScore = computed(() => esgData.value?.governance_metrics?.governance_score || {})
const recommendations = computed(() => esgData.value?.recommendations || [])

const chatContext = computed(() => ({
  esg_score: esgScore.value,
  environmental: environmentalMetrics.value,
  carbon: carbonFootprint.value,
  governance: governanceScore.value,
  safety: safetyMetrics.value,
}))

// Methods
const refreshData = async () => {
  isLoading.value = true
  error.value = null
  try {
    esgData.value = await apiCall('insights.api.ml.get_esg_overview', { period: selectedPeriod.value })
    lastUpdated.value = new Date().toISOString()
  } catch (e) {
    error.value = e.message || 'Failed to load ESG data'
    console.error('Error fetching ESG data:', e)
  } finally {
    isLoading.value = false
  }
}

const formatDateTime = (isoStr) => {
  if (!isoStr) return ''
  return new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

const formatDate = (dateStr) => {
  if (!dateStr) return 'TBD'
  return new Date(dateStr).toLocaleDateString()
}

const getScoreTextClass = (score) => {
  if (score >= 85) return 'text-green-600'
  if (score >= 70) return 'text-yellow-600'
  if (score >= 55) return 'text-orange-600'
  return 'text-red-600'
}

const getRatingColorClass = (rating) => {
  if (['AAA', 'AA', 'A'].includes(rating)) return 'text-green-600'
  if (['BBB', 'BB'].includes(rating)) return 'text-yellow-600'
  if (['B', 'CCC'].includes(rating)) return 'text-orange-600'
  return 'text-red-600'
}

const getInitiativeStatusClass = (status) => {
  switch (status) {
    case 'Completed': return 'bg-green-100 text-green-800'
    case 'In Progress': return 'bg-blue-100 text-blue-800'
    case 'Planning': return 'bg-yellow-100 text-yellow-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}

const getPriorityColorClass = (priority) => {
  switch (priority) {
    case 'critical': return 'bg-red-100 text-red-800'
    case 'high': return 'bg-orange-100 text-orange-800'
    case 'medium': return 'bg-yellow-100 text-yellow-800'
    case 'low': return 'bg-blue-100 text-blue-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}

// Lifecycle
onMounted(() => {
  refreshData()
})
</script>
