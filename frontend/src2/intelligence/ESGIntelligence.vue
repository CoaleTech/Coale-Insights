<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <header class="bg-white border-b px-6 py-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">ESG Intelligence</h1>
        <p class="text-sm text-gray-500 mt-1">
          Environmental, Social &amp; Governance analytics for sustainable business practices
        </p>
      </div>
      <div class="flex items-center gap-3">
        <span v-if="lastUpdated" class="text-sm text-gray-500">
          Updated: {{ formatDate(lastUpdated) }}
        </span>
        <Button
          variant="outline"
          @click="exportReport"
          :loading="exporting"
          icon-left="file-text"
        >
          ESG Report
        </Button>
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
        <div class="text-sm font-medium text-gray-500">ESG Score</div>
        <div class="text-2xl font-bold mt-1" :class="getScoreColor(esgScore.overall_score)">
          {{ esgScore.overall_score || 0 }}
        </div>
        <div class="text-sm mt-1" :class="getRatingColor(esgScore.rating)">
          {{ esgScore.rating || 'Not Rated' }}
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Environmental</div>
        <div class="text-2xl font-bold text-green-600 mt-1">
          {{ esgScore.environmental_score || 0 }}
        </div>
        <div class="text-sm text-gray-500 mt-1">E score</div>
      </div>

      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Social</div>
        <div class="text-2xl font-bold text-blue-600 mt-1">
          {{ esgScore.social_score || 0 }}
        </div>
        <div class="text-sm text-gray-500 mt-1">S score</div>
      </div>

      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Governance</div>
        <div class="text-2xl font-bold text-purple-600 mt-1">
          {{ esgScore.governance_score || 0 }}
        </div>
        <div class="text-sm text-gray-500 mt-1">G score</div>
      </div>

      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Carbon Footprint</div>
        <div class="text-2xl font-bold text-gray-900 mt-1">
          {{ carbonFootprint.total_emissions_tco2 || 0 }}
        </div>
        <div class="text-sm text-gray-500 mt-1">tCO2</div>
      </div>

      <div class="bg-white rounded-lg shadow-sm p-4 border">
        <div class="text-sm font-medium text-gray-500">Renewable Energy</div>
        <div class="text-2xl font-bold text-green-600 mt-1">
          {{ environmentalKpis.renewable_energy_pct || 0 }}%
        </div>
        <div class="text-sm text-gray-500 mt-1">of total energy</div>
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
          <!-- ESG Scores -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-6">ESG Score Breakdown</h3>
            <div class="flex items-center justify-center mb-8">
              <div class="text-center">
                <div class="text-6xl font-bold mb-2" :class="getScoreColor(esgScore.overall_score)">
                  {{ esgScore.overall_score || 0 }}
                </div>
                <div class="text-gray-600 mb-2">Overall ESG Score</div>
                <div class="px-4 py-1 rounded-full text-sm font-medium inline-block"
                     :class="getRatingBadge(esgScore.rating)">
                  {{ esgScore.rating || 'Not Rated' }}
                </div>
                <p v-if="esgScore.rating_description" class="text-xs text-gray-500 mt-2">
                  {{ esgScore.rating_description }}
                </p>
              </div>
            </div>
            <div class="space-y-4">
              <div>
                <div class="flex justify-between text-sm font-medium mb-2">
                  <span class="text-gray-700">Environmental</span>
                  <span class="text-green-600">{{ esgScore.environmental_score || 0 }}</span>
                </div>
                <div class="w-full bg-gray-100 rounded-full h-4">
                  <div class="bg-green-500 h-4 rounded-full transition-all"
                       :style="{ width: Math.min(esgScore.environmental_score || 0, 100) + '%' }"></div>
                </div>
              </div>
              <div>
                <div class="flex justify-between text-sm font-medium mb-2">
                  <span class="text-gray-700">Social</span>
                  <span class="text-blue-600">{{ esgScore.social_score || 0 }}</span>
                </div>
                <div class="w-full bg-gray-100 rounded-full h-4">
                  <div class="bg-blue-500 h-4 rounded-full transition-all"
                       :style="{ width: Math.min(esgScore.social_score || 0, 100) + '%' }"></div>
                </div>
              </div>
              <div>
                <div class="flex justify-between text-sm font-medium mb-2">
                  <span class="text-gray-700">Governance</span>
                  <span class="text-purple-600">{{ esgScore.governance_score || 0 }}</span>
                </div>
                <div class="w-full bg-gray-100 rounded-full h-4">
                  <div class="bg-purple-500 h-4 rounded-full transition-all"
                       :style="{ width: Math.min(esgScore.governance_score || 0, 100) + '%' }"></div>
                </div>
              </div>
            </div>
          </div>

          <!-- Key Metrics Summary -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Key ESG Metrics</h3>
            <div class="space-y-3">
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Renewable Energy</span>
                <span class="font-semibold text-green-600">{{ environmentalKpis.renewable_energy_pct || 0 }}%</span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Water Recycled</span>
                <span class="font-semibold text-blue-600">{{ environmentalKpis.water_recycled_pct || 0 }}%</span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Waste Recycled</span>
                <span class="font-semibold text-green-600">{{ environmentalKpis.recycled_waste_pct || 0 }}%</span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Employee Satisfaction</span>
                <span class="font-semibold text-blue-600">{{ employeeWellbeing.employee_satisfaction_score || 0 }}/5</span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Ethics Score</span>
                <span class="font-semibold text-purple-600">{{ governanceScore.ethics_score || 0 }}</span>
              </div>
              <div class="flex justify-between items-center py-2">
                <span class="text-sm text-gray-600">Carbon Footprint</span>
                <span class="font-semibold text-gray-700">{{ carbonFootprint.total_emissions_tco2 || 0 }} tCO2</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Environmental Tab -->
      <div v-if="activeTab === 'environmental'">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Energy & Resources -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Energy &amp; Resources</h3>
            <div class="space-y-5">
              <div class="p-4 bg-green-50 rounded-lg">
                <div class="text-sm font-medium text-green-800 mb-1">Renewable Energy</div>
                <div class="text-3xl font-bold text-green-700">{{ environmentalKpis.renewable_energy_pct || 0 }}%</div>
                <div class="w-full bg-green-200 rounded-full h-3 mt-2">
                  <div class="bg-green-600 h-3 rounded-full"
                       :style="{ width: (environmentalKpis.renewable_energy_pct || 0) + '%' }"></div>
                </div>
              </div>
              <div class="p-4 bg-blue-50 rounded-lg">
                <div class="text-sm font-medium text-blue-800 mb-1">Water Recycled</div>
                <div class="text-3xl font-bold text-blue-700">{{ environmentalKpis.water_recycled_pct || 0 }}%</div>
                <div class="w-full bg-blue-200 rounded-full h-3 mt-2">
                  <div class="bg-blue-600 h-3 rounded-full"
                       :style="{ width: (environmentalKpis.water_recycled_pct || 0) + '%' }"></div>
                </div>
              </div>
              <div class="p-4 bg-yellow-50 rounded-lg">
                <div class="text-sm font-medium text-yellow-800 mb-1">Waste Recycled</div>
                <div class="text-3xl font-bold text-yellow-700">{{ environmentalKpis.recycled_waste_pct || 0 }}%</div>
                <div class="w-full bg-yellow-200 rounded-full h-3 mt-2">
                  <div class="bg-yellow-500 h-3 rounded-full"
                       :style="{ width: (environmentalKpis.recycled_waste_pct || 0) + '%' }"></div>
                </div>
              </div>
              <div class="p-4 bg-gray-50 rounded-lg">
                <div class="text-sm font-medium text-gray-700 mb-1">Total Carbon Footprint</div>
                <div class="text-3xl font-bold text-gray-800">{{ carbonFootprint.total_emissions_tco2 || 0 }}</div>
                <div class="text-sm text-gray-500">tCO2 equivalent</div>
              </div>
            </div>
          </div>

          <!-- Green Initiatives -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Green Initiatives</h3>
            <div v-if="greenInitiatives.length > 0" class="space-y-3 max-h-[480px] overflow-y-auto">
              <div
                v-for="initiative in greenInitiatives"
                :key="initiative.name"
                class="border border-gray-100 rounded-lg p-4"
              >
                <div class="flex items-center justify-between mb-2">
                  <h4 class="font-medium text-gray-900 text-sm">{{ initiative.name }}</h4>
                  <span class="px-2 py-0.5 text-xs rounded-full font-medium"
                        :class="getInitiativeStatusClass(initiative.status)">
                    {{ initiative.status }}
                  </span>
                </div>
                <div class="mb-2">
                  <div class="flex justify-between text-xs text-gray-500 mb-1">
                    <span>Progress</span>
                    <span>{{ initiative.progress_pct || 0 }}%</span>
                  </div>
                  <div class="w-full bg-gray-200 rounded-full h-2">
                    <div class="bg-green-500 h-2 rounded-full"
                         :style="{ width: (initiative.progress_pct || 0) + '%' }"></div>
                  </div>
                </div>
                <p v-if="initiative.expected_impact" class="text-xs text-gray-600">{{ initiative.expected_impact }}</p>
                <p v-if="initiative.target_completion" class="text-xs text-gray-400 mt-1">
                  Target: {{ formatDateShort(initiative.target_completion) }}
                </p>
              </div>
            </div>
            <div v-else class="text-center py-12 text-gray-500">
              <p class="text-sm">No green initiatives tracked</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Social Tab -->
      <div v-if="activeTab === 'social'">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Employee Wellbeing -->
          <div
            class="bg-white rounded-lg shadow-sm border p-6 cursor-pointer hover:ring-2 hover:ring-blue-300 transition-shadow"
            @click="drillDown.open(ESG_ENDPOINT, 'Employee & Diversity', { metric: 'employees_diversity' })"
          >
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Employee Wellbeing</h3>
            <div class="space-y-3">
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Satisfaction Score</span>
                <span class="font-semibold text-blue-600">{{ employeeWellbeing.employee_satisfaction_score || 0 }}/5</span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Work-Life Balance</span>
                <span class="font-semibold text-blue-600">{{ employeeWellbeing.work_life_balance_score || 0 }}/5</span>
              </div>
              <div class="flex justify-between items-center py-2">
                <span class="text-sm text-gray-600">Wellness Program Enrollment</span>
                <span class="font-semibold text-green-600">{{ employeeWellbeing.wellness_program_enrollment || 0 }}%</span>
              </div>
            </div>

            <h3 class="text-lg font-semibold text-gray-900 mt-6 mb-4">Diversity &amp; Inclusion</h3>
            <div class="space-y-3">
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Inclusion Index</span>
                <span class="font-semibold text-purple-600">{{ diversityMetrics.inclusion_index || 0 }}/10</span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Diverse Hiring</span>
                <span class="font-semibold text-purple-600">{{ diversityMetrics.diverse_hiring_pct || 0 }}%</span>
              </div>
              <div class="flex justify-between items-center py-2">
                <span class="text-sm text-gray-600">Diversity Training Completion</span>
                <span class="font-semibold text-purple-600">{{ diversityMetrics.diversity_training_completion || 0 }}%</span>
              </div>
            </div>
          </div>

          <!-- Community & Safety -->
          <div
            class="bg-white rounded-lg shadow-sm border p-6 cursor-pointer hover:ring-2 hover:ring-blue-300 transition-shadow"
            @click="drillDown.open(ESG_ENDPOINT, 'Supplier Count', { metric: 'supplier_count' })"
          >
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Community Impact</h3>
            <div class="space-y-3">
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Volunteer Participation</span>
                <span class="font-semibold text-green-600">{{ communityMetrics.volunteer_participation_pct || 0 }}%</span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Local Supplier Spend</span>
                <span class="font-semibold text-green-600">{{ communityMetrics.local_supplier_spend_pct || 0 }}%</span>
              </div>
              <div class="flex justify-between items-center py-2">
                <span class="text-sm text-gray-600">Community Partnerships</span>
                <span class="font-semibold text-gray-900">{{ communityMetrics.community_partnerships || 0 }}</span>
              </div>
            </div>

            <h3 class="text-lg font-semibold text-gray-900 mt-6 mb-4">Health &amp; Safety</h3>
            <div class="space-y-3">
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Safety Culture Index</span>
                <span class="font-semibold text-red-600">{{ safetyMetrics.safety_culture_index || 0 }}/10</span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Safety Training Completion</span>
                <span class="font-semibold text-red-600">{{ safetyMetrics.safety_training_completion_pct || 0 }}%</span>
              </div>
              <div class="flex justify-between items-center py-2 border-b">
                <span class="text-sm text-gray-600">Workplace Inspection Score</span>
                <span class="font-semibold text-red-600">{{ safetyMetrics.workplace_inspection_score || 0 }}/10</span>
              </div>
              <div class="flex justify-between items-center py-2">
                <span class="text-sm text-gray-600">Lost Time Injuries</span>
                <span class="font-semibold" :class="(safetyMetrics.lost_time_injury_rate || 0) === 0 ? 'text-green-600' : 'text-red-600'">
                  {{ safetyMetrics.lost_time_injury_rate || 0 }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Governance Tab -->
      <div v-if="activeTab === 'governance'">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Governance Scores -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-6">Governance Scores</h3>
            <div class="space-y-6">
              <div class="text-center p-4 bg-purple-50 rounded-lg">
                <div class="text-4xl font-bold text-purple-700 mb-1">{{ governanceScore.ethics_score || 0 }}</div>
                <div class="text-sm text-purple-600">Ethics &amp; Compliance Score</div>
              </div>
              <div class="text-center p-4 bg-indigo-50 rounded-lg">
                <div class="text-4xl font-bold text-indigo-700 mb-1">{{ governanceScore.risk_score || 0 }}</div>
                <div class="text-sm text-indigo-600">Risk Management Score</div>
              </div>
              <div class="text-center p-4 bg-gray-50 rounded-lg">
                <div class="text-4xl font-bold text-gray-700 mb-1">{{ governanceScore.transparency_score || 0 }}</div>
                <div class="text-sm text-gray-600">Transparency Score</div>
              </div>
            </div>
          </div>

          <!-- Governance Details -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Governance Overview</h3>
            <div class="space-y-4">
              <div>
                <div class="flex justify-between text-sm font-medium mb-2">
                  <span class="text-gray-700">Ethics &amp; Compliance</span>
                  <span class="text-purple-600">{{ governanceScore.ethics_score || 0 }}/100</span>
                </div>
                <div class="w-full bg-gray-100 rounded-full h-4">
                  <div class="bg-purple-500 h-4 rounded-full transition-all"
                       :style="{ width: Math.min(governanceScore.ethics_score || 0, 100) + '%' }"></div>
                </div>
              </div>
              <div>
                <div class="flex justify-between text-sm font-medium mb-2">
                  <span class="text-gray-700">Risk Management</span>
                  <span class="text-indigo-600">{{ governanceScore.risk_score || 0 }}/100</span>
                </div>
                <div class="w-full bg-gray-100 rounded-full h-4">
                  <div class="bg-indigo-500 h-4 rounded-full transition-all"
                       :style="{ width: Math.min(governanceScore.risk_score || 0, 100) + '%' }"></div>
                </div>
              </div>
              <div>
                <div class="flex justify-between text-sm font-medium mb-2">
                  <span class="text-gray-700">Transparency</span>
                  <span class="text-gray-600">{{ governanceScore.transparency_score || 0 }}/100</span>
                </div>
                <div class="w-full bg-gray-100 rounded-full h-4">
                  <div class="bg-gray-500 h-4 rounded-full transition-all"
                       :style="{ width: Math.min(governanceScore.transparency_score || 0, 100) + '%' }"></div>
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
                  <span class="px-2 py-1 text-xs font-medium rounded-full"
                        :class="getPriorityBadge(rec.priority)">
                    {{ (rec.priority || 'MEDIUM').toUpperCase() }}
                  </span>
                  <span v-if="rec.category" class="text-sm text-gray-500">{{ rec.category }}</span>
                </div>
                <h4 class="font-semibold text-gray-900 mb-2">{{ rec.recommendation || rec.title }}</h4>
                <p v-if="rec.impact" class="text-sm text-gray-600 mb-1">{{ rec.impact }}</p>
                <p v-if="rec.timeframe" class="text-xs text-gray-400 mt-2">Timeline: {{ rec.timeframe }}</p>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="bg-white rounded-lg shadow-sm border p-12 text-center text-gray-500">
          <p class="text-sm">No recommendations available. Refresh the analysis to generate insights.</p>
        </div>
      </div>

    </div>

    <!-- AI Chat Button -->
    <DashboardChatButton
      dashboard-type="ESG"
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
defineOptions({ name: 'ESGIntelligence' })
import { ref, computed, onMounted } from 'vue'
import { Button } from 'frappe-ui'
import { useRouter } from 'vue-router'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import { useDrillDown } from './composables/useDrillDown'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'

const router = useRouter()

const ESG_ENDPOINT = 'insights.api.ml.esg.get_esg_detail'
const drillDown = useDrillDown()

const loading = ref(false)
const exporting = ref(false)
const lastUpdated = ref('')
const activeTab = ref('overview')

const esgData = ref<Record<string, any>>({})

const esgScore = computed(() => esgData.value.esg_score || {})
const carbonFootprint = computed(() => esgData.value.carbon_footprint || {})
const greenInitiatives = computed(
  () => esgData.value.environmental_metrics?.green_initiatives || []
)
const environmentalKpis = computed(() => {
  const env = esgData.value.environmental_metrics || {}
  return {
    renewable_energy_pct: env.energy_consumption?.renewable_energy_pct || 0,
    water_recycled_pct: env.water_usage?.water_recycled_pct || 0,
    recycled_waste_pct: env.waste_management?.recycled_waste_pct || 0
  }
})
const employeeWellbeing = computed(() => esgData.value.social_metrics?.employee_wellbeing || {})
const diversityMetrics = computed(() => esgData.value.social_metrics?.diversity_inclusion || {})
const communityMetrics = computed(() => esgData.value.social_metrics?.community_involvement || {})
const safetyMetrics = computed(() => esgData.value.social_metrics?.health_safety || {})
const governanceScore = computed(() => esgData.value.governance_metrics?.governance_score || {})
const recommendations = computed(() => esgData.value.recommendations || [])

const tabs = [
  { label: 'Overview', value: 'overview' },
  { label: 'Environmental', value: 'environmental' },
  { label: 'Social', value: 'social' },
  { label: 'Governance', value: 'governance' },
  { label: 'Recommendations', value: 'recommendations' }
]

async function refreshData() {
  loading.value = true
  try {
    const response = await fetch('/api/method/insights.api.ml.get_esg_overview?period=YTD&refresh=1', {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': (window as any).csrf_token || ''
      }
    })
    const result = await response.json()
    if (result.message) {
      esgData.value = result.message?.status === 'success' ? result.message : result.message
    } else {
      console.error('ESG Intelligence Error:', result.exc || 'Unknown error')
    }
    lastUpdated.value = new Date().toISOString()
  } catch (error) {
    console.error('Error loading ESG intelligence data:', error)
  } finally {
    loading.value = false
  }
}

async function exportReport() {
  exporting.value = true
  try {
    const response = await fetch('/api/method/insights.api.ml.export_esg_report', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': (window as any).csrf_token || ''
      },
      body: JSON.stringify({ format: 'pdf' })
    })
    const result = await response.json()
    if (result.message) {
      console.log('ESG report exported:', result.message)
    }
  } catch (error) {
    console.error('Error exporting ESG report:', error)
  } finally {
    exporting.value = false
  }
}

const formatDate = (date: string | undefined) => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('en-KE', {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  })
}

const formatDateShort = (dateStr: string | undefined) => {
  if (!dateStr) return 'TBD'
  return new Date(dateStr).toLocaleDateString('en-KE', { year: 'numeric', month: 'short', day: 'numeric' })
}

const getScoreColor = (score: number) => {
  if (score >= 85) return 'text-green-600'
  if (score >= 70) return 'text-amber-500'
  if (score >= 55) return 'text-orange-500'
  return 'text-red-600'
}

const getRatingColor = (rating: string) => {
  if (['AAA', 'AA', 'A'].includes(rating)) return 'text-green-600'
  if (['BBB', 'BB'].includes(rating)) return 'text-amber-500'
  if (['B', 'CCC'].includes(rating)) return 'text-orange-500'
  return 'text-red-600'
}

const getRatingBadge = (rating: string) => {
  if (['AAA', 'AA', 'A'].includes(rating)) return 'bg-green-100 text-green-700'
  if (['BBB', 'BB'].includes(rating)) return 'bg-amber-100 text-amber-700'
  return 'bg-red-100 text-red-700'
}

const getInitiativeStatusClass = (status: string) => {
  switch (status) {
    case 'Completed': return 'bg-green-100 text-green-800'
    case 'In Progress': return 'bg-blue-100 text-blue-800'
    case 'Planning': return 'bg-yellow-100 text-yellow-800'
    default: return 'bg-gray-100 text-gray-800'
  }
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
  esgScore: esgScore.value,
  environmentalKpis: environmentalKpis.value,
  carbonFootprint: carbonFootprint.value,
  employeeWellbeing: employeeWellbeing.value,
  diversityMetrics: diversityMetrics.value,
  governanceScore: governanceScore.value,
  recommendations: recommendations.value,
  activeTab: activeTab.value,
  lastUpdated: lastUpdated.value
}))

function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    'HR': '/hr-intelligence',
    'Manufacturing': '/manufacturing-intelligence',
    'Financial': '/financial-intelligence',
    'Executive': '/executive-intelligence',
    'ESG': '/esg-intelligence'
  }
  if (routes[target]) router.push(routes[target])
}

onMounted(() => { refreshData() })
</script>
