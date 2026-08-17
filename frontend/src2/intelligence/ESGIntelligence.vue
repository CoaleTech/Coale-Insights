<script setup lang="ts">
defineOptions({ name: 'ESGIntelligence' })
import { ref, computed, onMounted } from 'vue'
import { Badge, Button, Tabs } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { apiCall } from '../helpers/api'
import { useIntelligenceDashboard } from './composables/useIntelligenceDashboard'
import {
  severityBadge, severityFill, severityAria, scoreSeverity, ragSeverity,
  prioritySeverity, type Severity,
} from '../utils/status'
import { formatDate, formatDateTime, formatPercent, formatCount } from '../utils/format'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import { useDrillDown } from './composables/useDrillDown'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'
import KpiCard from './components/KpiCard.vue'
import IntelligenceDashboardShell from './components/IntelligenceDashboardShell.vue'
import SectionHeader from './components/SectionHeader.vue'

// ── Payload interfaces ────────────────────────────────────────────────────────

interface EsgScore {
  overall_score?: number
  environmental_score?: number
  social_score?: number
  governance_score?: number
  rating?: string
  rating_description?: string
}

interface CarbonFootprint {
  total_emissions_tco2?: number
}

interface EnergyConsumption { renewable_energy_pct?: number }
interface WaterUsage         { water_recycled_pct?: number }
interface WasteManagement    { recycled_waste_pct?: number }

interface GreenInitiativeRow {
  name: string
  status: string
  progress_pct?: number
  target_completion?: string
  expected_impact?: string
  investment?: number
  category?: string
}

interface EnvironmentalMetrics {
  energy_consumption?: EnergyConsumption
  waste_management?: WasteManagement
  water_usage?: WaterUsage
  green_initiatives?: GreenInitiativeRow[]
}

interface EmployeeWellbeing {
  employee_satisfaction_score?: number
  work_life_balance_score?: number
  wellness_program_enrollment?: number
}

interface DiversityInclusion {
  inclusion_index?: number
  diverse_hiring_pct?: number
  diversity_training_completion?: number
}
interface CommunityInvolvement {
  volunteer_participation_pct?: number
  local_supplier_spend_pct?: number
  community_partnerships?: number
}
interface HealthSafety {
  safety_culture_index?: number
  safety_training_completion_pct?: number
  workplace_inspection_score?: number
  lost_time_injury_rate?: number
}

interface SocialMetrics {
  employee_wellbeing?: EmployeeWellbeing
  diversity_inclusion?: DiversityInclusion
  community_involvement?: CommunityInvolvement
  health_safety?: HealthSafety
}

interface GovernanceScoreBlock {
  overall_score?: number
  ethics_score?: number
  transparency_score?: number
  risk_score?: number
}

interface GovernanceMetrics { governance_score?: GovernanceScoreBlock }

interface EsgRecommendationRow {
  recommendation?: string
  title?: string
  priority?: string
  category?: string
  impact?: string
  timeframe?: string
}

/** Top-level shape returned by insights.api.ml.get_esg_overview. */
interface EsgPayload {
  environmental_metrics?: EnvironmentalMetrics
  social_metrics?: SocialMetrics
  governance_metrics?: GovernanceMetrics
  esg_score?: EsgScore
  carbon_footprint?: CarbonFootprint
  recommendations?: EsgRecommendationRow[]
  generated_at?: string
  period?: string
  currency?: string
}

// ─────────────────────────────────────────────────────────────────────────────

const router = useRouter()
const ESG_ENDPOINT = 'insights.api.ml.esg.get_esg_detail'
const drillDown = useDrillDown()

const exporting = ref(false)
const lastUpdated = ref('')

const {
  data,
  loading,
  refreshing,
  error,
  isPermissionError,
  warming,
  notImplemented,
  notImplementedMessage,
  hasData,
  reload,
  retry,
} =
  useIntelligenceDashboard<EsgPayload>({
    url: 'insights.api.ml.get_esg_overview',
    cache: 'esg-intelligence',
  })

const tabIndex = ref(0)
const tabs = [
  { label: 'Overview' },
  { label: 'Environmental' },
  { label: 'Social' },
  { label: 'Governance' },
  { label: 'Recommendations' },
]

const esgScore = computed((): EsgScore =>
  data.value?.esg_score ?? ({} as EsgScore))
const carbonFootprint = computed((): CarbonFootprint =>
  data.value?.carbon_footprint ?? ({} as CarbonFootprint))
const greenInitiatives = computed((): GreenInitiativeRow[] =>
  data.value?.environmental_metrics?.green_initiatives ?? [])
const environmentalKpis = computed(() => {
  const env = data.value?.environmental_metrics
  return {
    renewable_energy_pct: env?.energy_consumption?.renewable_energy_pct,
    water_recycled_pct: env?.water_usage?.water_recycled_pct,
    recycled_waste_pct: env?.waste_management?.recycled_waste_pct,
  }
})
const employeeWellbeing = computed((): EmployeeWellbeing =>
  data.value?.social_metrics?.employee_wellbeing ?? ({} as EmployeeWellbeing))
const diversityMetrics = computed((): DiversityInclusion =>
  data.value?.social_metrics?.diversity_inclusion ?? {})
const communityMetrics = computed((): CommunityInvolvement =>
  data.value?.social_metrics?.community_involvement ?? {})
const safetyMetrics = computed((): HealthSafety =>
  data.value?.social_metrics?.health_safety ?? {})
const governanceScore = computed((): GovernanceScoreBlock =>
  data.value?.governance_metrics?.governance_score ?? ({} as GovernanceScoreBlock))
const recommendations = computed((): EsgRecommendationRow[] =>
  data.value?.recommendations ?? [])


/** ESG letter ratings (AAA/AA/A/BBB/BB/B/CCC) mapped to a Severity for Badge. */
function esgRatingSeverity(rating: string | undefined): Severity {
  if (!rating) return 'none'
  if (['AAA', 'AA', 'A'].includes(rating)) return 'low'
  if (['BBB', 'BB'].includes(rating)) return 'medium'
  if (['B', 'CCC'].includes(rating)) return 'high'
  return 'none'
}



/** Initiative status (Completed / In Progress / Planning) to Severity. */
function initiativeStatusSeverity(status: string): Severity {
  if (status === 'Completed') return 'low'
  if (status === 'In Progress') return 'none'
  if (status === 'Planning') return 'medium'
  return 'none'
}

/** Numeric ESG subscore (0-100, higher is better) to Severity. */
function scoreSev(score: number | undefined): Severity {
  return scoreSeverity(score, { good: 85, warn: 70, higherIsBetter: true })
}

async function refreshData() {
  lastUpdated.value = ''
  reload()
  lastUpdated.value = new Date().toISOString()
}

async function exportReport() {
  exporting.value = true
  try {
    await apiCall('insights.api.ml.export_esg_report', { format: 'pdf' })
  } catch (e) {
    console.error('Error exporting ESG report:', e)
  } finally {
    exporting.value = false
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
  activeTab: tabIndex.value,
  lastUpdated: lastUpdated.value,
}))

function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    'HR': '/hr-intelligence',
    'Manufacturing': '/manufacturing-intelligence',
    'Financial': '/financial-intelligence',
    'Executive': '/executive-intelligence',
    'ESG': '/esg-intelligence',
  }
  if (routes[target]) router.push(routes[target])
}
</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <header class="bg-surface-white border-b px-6 py-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-ink-gray-9">ESG Intelligence</h1>
        <p class="text-sm text-ink-gray-6 mt-1">
          Environmental, Social &amp; Governance analytics
        </p>
      </div>
      <div class="flex items-center gap-3">
        <span v-if="lastUpdated" class="text-sm text-ink-gray-6">
          Updated: {{ formatDateTime(lastUpdated) }}
        </span>
        <Button variant="outline" @click="exportReport" :loading="exporting">
          ESG Report
        </Button>
        <Button variant="subtle" @click="refreshData" :loading="refreshing">
          Refresh
        </Button>
      </div>
    </header>

    <IntelligenceDashboardShell
      :loading="loading"
      :refreshing="refreshing"
      :error="error"
      :is-permission-error="isPermissionError"
      :warming="warming"
      :not-implemented="notImplemented"
      :not-implemented-message="notImplementedMessage"
      :has-data="hasData"
      subject="ESG data"
      permission-hint="Ask an administrator for Sustainability read access."
      :kpi-count="6"
      @retry="retry"
    >
      <!-- Summary KPI cards -->
      <div class="p-6 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard
          label="ESG Score"
          :value="esgScore.overall_score"
          :severity="scoreSev(esgScore.overall_score)"
          :loading="!hasData"
          :sublabel="esgScore.rating || undefined"
        />
        <KpiCard
          label="Environmental"
          :value="esgScore.environmental_score"
          :severity="scoreSev(esgScore.environmental_score)"
          :loading="!hasData"
          sublabel="E score"
        />
        <KpiCard
          label="Social"
          :value="esgScore.social_score"
          :severity="scoreSev(esgScore.social_score)"
          :loading="!hasData"
          sublabel="S score"
        />
        <KpiCard
          label="Governance"
          :value="esgScore.governance_score"
          :severity="scoreSev(esgScore.governance_score)"
          :loading="!hasData"
          sublabel="G score"
        />
        <KpiCard
          label="Carbon Footprint"
          :value="carbonFootprint.total_emissions_tco2"
          :loading="!hasData"
          sublabel="tCO2"
        />
        <KpiCard
          label="Renewable Energy"
          :percent="environmentalKpis.renewable_energy_pct"
          :loading="!hasData"
          sublabel="of total energy"
        />
      </div>

      <!-- Tab strip -->
      <div class="mx-6">
        <Tabs v-model="tabIndex" :tabs="tabs" />
      </div>

      <!-- Tab content -->
      <div class="flex-1 p-6">

        <!-- Overview -->
        <div v-show="tabIndex === 0">
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- ESG Score Breakdown -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader variant="caption" title="ESG Score Breakdown" :level="3" />
              <div class="flex items-center justify-center mt-6 mb-8">
                <div class="text-center">
                  <div class="text-6xl font-bold mb-2 text-ink-gray-9">
                    {{ formatCount(esgScore.overall_score) }}
                  </div>
                  <div class="text-ink-gray-6 mb-2">Overall ESG Score</div>
                  <Badge
                    v-bind="severityBadge(esgRatingSeverity(esgScore.rating))"
                    :label="esgScore.rating || 'Not Rated'"
                    size="sm"
                  />
                  <p v-if="esgScore.rating_description" class="text-xs text-ink-gray-6 mt-2">
                    {{ esgScore.rating_description }}
                  </p>
                </div>
              </div>
              <div class="space-y-4">
                <div>
                  <div class="flex justify-between text-sm font-medium mb-2">
                    <span class="text-ink-gray-7">Environmental</span>
                    <span class="text-ink-gray-8">{{ formatCount(esgScore.environmental_score) }}</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-4">
                    <div
                      class="h-4 rounded-full motion-reduce:transition-none transition-all"
                      :class="severityFill(scoreSev(esgScore.environmental_score))"
                      :style="{ width: Math.min(esgScore.environmental_score || 0, 100) + '%' }"
                      role="img"
                      :aria-label="severityAria('Environmental score', scoreSev(esgScore.environmental_score), esgScore.environmental_score)"
                    />
                  </div>
                </div>
                <div>
                  <div class="flex justify-between text-sm font-medium mb-2">
                    <span class="text-ink-gray-7">Social</span>
                    <span class="text-ink-gray-8">{{ formatCount(esgScore.social_score) }}</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-4">
                    <div
                      class="h-4 rounded-full motion-reduce:transition-none transition-all"
                      :class="severityFill(scoreSev(esgScore.social_score))"
                      :style="{ width: Math.min(esgScore.social_score || 0, 100) + '%' }"
                      role="img"
                      :aria-label="severityAria('Social score', scoreSev(esgScore.social_score), esgScore.social_score)"
                    />
                  </div>
                </div>
                <div>
                  <div class="flex justify-between text-sm font-medium mb-2">
                    <span class="text-ink-gray-7">Governance</span>
                    <span class="text-ink-gray-8">{{ formatCount(esgScore.governance_score) }}</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-4">
                    <div
                      class="h-4 rounded-full motion-reduce:transition-none transition-all"
                      :class="severityFill(scoreSev(esgScore.governance_score))"
                      :style="{ width: Math.min(esgScore.governance_score || 0, 100) + '%' }"
                      role="img"
                      :aria-label="severityAria('Governance score', scoreSev(esgScore.governance_score), esgScore.governance_score)"
                    />
                  </div>
                </div>
              </div>
            </div>

            <!-- Key ESG Metrics -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader variant="caption" title="Key ESG Metrics" :level="3" />
              <div class="space-y-3 mt-4">
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Renewable Energy</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatPercent(environmentalKpis.renewable_energy_pct) }}</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Water Recycled</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatPercent(environmentalKpis.water_recycled_pct) }}</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Waste Recycled</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatPercent(environmentalKpis.recycled_waste_pct) }}</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Employee Satisfaction</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatCount(employeeWellbeing.employee_satisfaction_score) }}/5</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Ethics Score</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatCount(governanceScore.ethics_score) }}</span>
                </div>
                <div class="flex justify-between items-center py-2">
                  <span class="text-sm text-ink-gray-6">Carbon Footprint</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatCount(carbonFootprint.total_emissions_tco2) }} tCO2</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Environmental -->
        <div v-show="tabIndex === 1">
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Energy & Resources -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader variant="caption" title="Energy &amp; Resources" :level="3" />
              <div class="space-y-5 mt-4">
                <div class="p-4 bg-surface-gray-1 rounded-lg">
                  <div class="text-sm font-medium text-ink-gray-7 mb-1">Renewable Energy</div>
                  <div class="text-3xl font-bold text-ink-gray-9">{{ formatPercent(environmentalKpis.renewable_energy_pct) }}</div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-3 mt-2">
                    <div
                      class="h-3 rounded-full"
                      :class="severityFill(scoreSeverity(environmentalKpis.renewable_energy_pct, { good: 80, warn: 50, higherIsBetter: true }))"
                      :style="{ width: (environmentalKpis.renewable_energy_pct || 0) + '%' }"
                      role="img"
                      :aria-label="severityAria('Renewable energy', scoreSeverity(environmentalKpis.renewable_energy_pct, { good: 80, warn: 50, higherIsBetter: true }), environmentalKpis.renewable_energy_pct + '%')"
                    />
                  </div>
                </div>
                <div class="p-4 bg-surface-gray-1 rounded-lg">
                  <div class="text-sm font-medium text-ink-gray-7 mb-1">Water Recycled</div>
                  <div class="text-3xl font-bold text-ink-gray-9">{{ formatPercent(environmentalKpis.water_recycled_pct) }}</div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-3 mt-2">
                    <div
                      class="h-3 rounded-full"
                      :class="severityFill(scoreSeverity(environmentalKpis.water_recycled_pct, { good: 70, warn: 40, higherIsBetter: true }))"
                      :style="{ width: (environmentalKpis.water_recycled_pct || 0) + '%' }"
                      role="img"
                      :aria-label="severityAria('Water recycled', scoreSeverity(environmentalKpis.water_recycled_pct, { good: 70, warn: 40, higherIsBetter: true }), environmentalKpis.water_recycled_pct + '%')"
                    />
                  </div>
                </div>
                <div class="p-4 bg-surface-gray-1 rounded-lg">
                  <div class="text-sm font-medium text-ink-gray-7 mb-1">Waste Recycled</div>
                  <div class="text-3xl font-bold text-ink-gray-9">{{ formatPercent(environmentalKpis.recycled_waste_pct) }}</div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-3 mt-2">
                    <div
                      class="h-3 rounded-full"
                      :class="severityFill(scoreSeverity(environmentalKpis.recycled_waste_pct, { good: 70, warn: 40, higherIsBetter: true }))"
                      :style="{ width: (environmentalKpis.recycled_waste_pct || 0) + '%' }"
                      role="img"
                      :aria-label="severityAria('Waste recycled', scoreSeverity(environmentalKpis.recycled_waste_pct, { good: 70, warn: 40, higherIsBetter: true }), environmentalKpis.recycled_waste_pct + '%')"
                    />
                  </div>
                </div>
                <div class="p-4 bg-surface-gray-1 rounded-lg">
                  <div class="text-sm font-medium text-ink-gray-7 mb-1">Total Carbon Footprint</div>
                  <div class="text-3xl font-bold text-ink-gray-9">{{ formatCount(carbonFootprint.total_emissions_tco2) }}</div>
                  <div class="text-sm text-ink-gray-6">tCO2 equivalent</div>
                </div>
              </div>
            </div>

            <!-- Green Initiatives -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader variant="caption" title="Green Initiatives" :level="3" />
              <div v-if="greenInitiatives.length > 0" class="space-y-3 max-h-[480px] overflow-y-auto mt-4">
                <div
                  v-for="initiative in greenInitiatives"
                  :key="initiative.name"
                  class="border border-outline-gray-1 rounded-lg p-4"
                >
                  <div class="flex items-center justify-between mb-2">
                    <h4 class="font-medium text-ink-gray-8 text-sm">{{ initiative.name }}</h4>
                    <Badge
                      v-bind="severityBadge(initiativeStatusSeverity(initiative.status))"
                      :label="initiative.status"
                      size="sm"
                    />
                  </div>
                  <div class="mb-2">
                    <div class="flex justify-between text-xs text-ink-gray-6 mb-1">
                      <span>Progress</span>
                      <span>{{ formatPercent(initiative.progress_pct) }}</span>
                    </div>
                    <div class="w-full bg-surface-gray-2 rounded-full h-2">
                      <div
                        class="h-2 rounded-full"
                        :class="severityFill(scoreSeverity(initiative.progress_pct, { good: 80, warn: 40, higherIsBetter: true }))"
                        :style="{ width: (initiative.progress_pct || 0) + '%' }"
                        role="img"
                        :aria-label="severityAria('Initiative progress', scoreSeverity(initiative.progress_pct, { good: 80, warn: 40, higherIsBetter: true }), initiative.progress_pct + '%')"
                      />
                    </div>
                  </div>
                  <p v-if="initiative.expected_impact" class="text-xs text-ink-gray-6">{{ initiative.expected_impact }}</p>
                  <p v-if="initiative.target_completion" class="text-xs text-ink-gray-5 mt-1">
                    Target: {{ formatDate(initiative.target_completion) }}
                  </p>
                </div>
              </div>
              <div v-else class="text-center py-12 text-ink-gray-6 mt-4">
                <p class="text-sm">No green initiatives tracked</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Social -->
        <div v-show="tabIndex === 2">
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Employee Wellbeing + Diversity -->
            <button
              class="bg-surface-white rounded-lg border border-outline-gray-1 p-6 text-left w-full cursor-pointer hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 motion-reduce:transition-none transition-colors"
              @click="drillDown.open(ESG_ENDPOINT, 'Employee & Diversity', { metric: 'employees_diversity' })"
            >
              <SectionHeader variant="caption" title="Employee Wellbeing" :level="3" />
              <div class="space-y-3 mt-4">
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Satisfaction Score</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatCount(employeeWellbeing.employee_satisfaction_score) }}/5</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Work-Life Balance</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatCount(employeeWellbeing.work_life_balance_score) }}/5</span>
                </div>
                <div class="flex justify-between items-center py-2">
                  <span class="text-sm text-ink-gray-6">Wellness Program Enrollment</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatPercent(employeeWellbeing.wellness_program_enrollment) }}</span>
                </div>
              </div>

              <SectionHeader variant="caption" title="Diversity &amp; Inclusion" :level="3" class="mt-6" />
              <div class="space-y-3 mt-4">
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Inclusion Index</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatCount(diversityMetrics.inclusion_index) }}/10</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Diverse Hiring</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatPercent(diversityMetrics.diverse_hiring_pct) }}</span>
                </div>
                <div class="flex justify-between items-center py-2">
                  <span class="text-sm text-ink-gray-6">Diversity Training Completion</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatPercent(diversityMetrics.diversity_training_completion) }}</span>
                </div>
              </div>
            </button>

            <!-- Community + Safety -->
            <button
              class="bg-surface-white rounded-lg border border-outline-gray-1 p-6 text-left w-full cursor-pointer hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 motion-reduce:transition-none transition-colors"
              @click="drillDown.open(ESG_ENDPOINT, 'Supplier Count', { metric: 'supplier_count' })"
            >
              <SectionHeader variant="caption" title="Community Impact" :level="3" />
              <div class="space-y-3 mt-4">
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Volunteer Participation</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatPercent(communityMetrics.volunteer_participation_pct) }}</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Local Supplier Spend</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatPercent(communityMetrics.local_supplier_spend_pct) }}</span>
                </div>
                <div class="flex justify-between items-center py-2">
                  <span class="text-sm text-ink-gray-6">Community Partnerships</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatCount(communityMetrics.community_partnerships) }}</span>
                </div>
              </div>

              <SectionHeader variant="caption" title="Health &amp; Safety" :level="3" class="mt-6" />
              <div class="space-y-3 mt-4">
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Safety Culture Index</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatCount(safetyMetrics.safety_culture_index) }}/10</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Safety Training Completion</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatPercent(safetyMetrics.safety_training_completion_pct) }}</span>
                </div>
                <div class="flex justify-between items-center py-2 border-b border-outline-gray-1">
                  <span class="text-sm text-ink-gray-6">Workplace Inspection Score</span>
                  <span class="font-semibold text-ink-gray-8">{{ formatCount(safetyMetrics.workplace_inspection_score) }}/10</span>
                </div>
                <div class="flex justify-between items-center py-2">
                  <span class="text-sm text-ink-gray-6">Lost Time Injuries</span>
                  <Badge
                    v-bind="severityBadge(safetyMetrics.lost_time_injury_rate == null ? 'none' : safetyMetrics.lost_time_injury_rate === 0 ? 'low' : 'critical')"
                    :label="formatCount(safetyMetrics.lost_time_injury_rate)"
                    size="sm"
                  />
                </div>
              </div>
            </button>
          </div>
        </div>

        <!-- Governance -->
        <div v-show="tabIndex === 3">
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Governance Score Cards (deliberate flat treatment replacing the broken violet panel) -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader variant="caption" title="Governance Scores" :level="3" />
              <div class="space-y-6 mt-4">
                <div class="text-center p-4 bg-surface-gray-1 rounded-lg">
                  <div class="text-4xl font-bold text-ink-gray-9 mb-1">{{ formatCount(governanceScore.ethics_score) }}</div>
                  <div class="text-sm text-ink-gray-6">Ethics &amp; Compliance Score</div>
                  <Badge
                    class="mt-2"
                    v-bind="severityBadge(scoreSev(governanceScore.ethics_score))"
                    :label="severityBadge(scoreSev(governanceScore.ethics_score)).label"
                    size="sm"
                  />
                </div>
                <div class="text-center p-4 bg-surface-gray-1 rounded-lg">
                  <div class="text-4xl font-bold text-ink-gray-9 mb-1">{{ formatCount(governanceScore.risk_score) }}</div>
                  <div class="text-sm text-ink-gray-6">Risk Management Score</div>
                  <Badge
                    class="mt-2"
                    v-bind="severityBadge(scoreSev(governanceScore.risk_score))"
                    :label="severityBadge(scoreSev(governanceScore.risk_score)).label"
                    size="sm"
                  />
                </div>
                <div class="text-center p-4 bg-surface-gray-1 rounded-lg">
                  <div class="text-4xl font-bold text-ink-gray-9 mb-1">{{ formatCount(governanceScore.transparency_score) }}</div>
                  <div class="text-sm text-ink-gray-6">Transparency Score</div>
                </div>
              </div>
            </div>

            <!-- Governance Progress Bars -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader variant="caption" title="Governance Overview" :level="3" />
              <div class="space-y-4 mt-4">
                <div>
                  <div class="flex justify-between text-sm font-medium mb-2">
                    <span class="text-ink-gray-7">Ethics &amp; Compliance</span>
                    <span class="text-ink-gray-8">{{ formatCount(governanceScore.ethics_score) }}/100</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-4">
                    <div
                      class="h-4 rounded-full motion-reduce:transition-none transition-all"
                      :class="severityFill(scoreSev(governanceScore.ethics_score))"
                      :style="{ width: Math.min(governanceScore.ethics_score || 0, 100) + '%' }"
                      role="img"
                      :aria-label="severityAria('Ethics score', scoreSev(governanceScore.ethics_score), governanceScore.ethics_score)"
                    />
                  </div>
                </div>
                <div>
                  <div class="flex justify-between text-sm font-medium mb-2">
                    <span class="text-ink-gray-7">Risk Management</span>
                    <span class="text-ink-gray-8">{{ formatCount(governanceScore.risk_score) }}/100</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-4">
                    <div
                      class="h-4 rounded-full motion-reduce:transition-none transition-all"
                      :class="severityFill(scoreSev(governanceScore.risk_score))"
                      :style="{ width: Math.min(governanceScore.risk_score || 0, 100) + '%' }"
                      role="img"
                      :aria-label="severityAria('Risk management score', scoreSev(governanceScore.risk_score), governanceScore.risk_score)"
                    />
                  </div>
                </div>
                <div>
                  <div class="flex justify-between text-sm font-medium mb-2">
                    <span class="text-ink-gray-7">Transparency</span>
                    <span class="text-ink-gray-8">{{ formatCount(governanceScore.transparency_score) }}/100</span>
                  </div>
                  <div class="w-full bg-surface-gray-2 rounded-full h-4">
                    <div
                      class="bg-surface-gray-4 h-4 rounded-full motion-reduce:transition-none transition-all"
                      :style="{ width: Math.min(governanceScore.transparency_score || 0, 100) + '%' }"
                      role="img"
                      :aria-label="`Transparency: ${governanceScore.transparency_score || 0}%`"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Recommendations -->
        <div v-show="tabIndex === 4">
          <div v-if="recommendations.length > 0" class="space-y-4">
            <div
              v-for="rec in recommendations"
              :key="rec.recommendation || rec.title"
              class="bg-surface-white rounded-lg border border-outline-gray-1 p-6"
            >
              <div class="flex items-start justify-between mb-3">
                <div class="flex-1">
                  <div class="flex items-center gap-2 mb-2">
                    <Badge
                      v-bind="severityBadge(prioritySeverity(rec.priority))"
                      :label="severityBadge(prioritySeverity(rec.priority)).label"
                      size="sm"
                    />
                    <span v-if="rec.category" class="text-sm text-ink-gray-6">{{ rec.category }}</span>
                  </div>
                  <h4 class="font-semibold text-ink-gray-8 mb-2">{{ rec.recommendation || rec.title }}</h4>
                  <p v-if="rec.impact" class="text-sm text-ink-gray-6 mb-1">{{ rec.impact }}</p>
                  <p v-if="rec.timeframe" class="text-xs text-ink-gray-5 mt-2">Timeline: {{ rec.timeframe }}</p>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="bg-surface-white rounded-lg border border-outline-gray-1 p-12 text-center text-ink-gray-6">
            <p class="text-sm">No recommendations available. Refresh to generate insights.</p>
          </div>
        </div>

      </div>
    </IntelligenceDashboardShell>

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
