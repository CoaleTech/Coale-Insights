<script setup lang="ts">
defineOptions({ name: 'HRIntelligence' })
import { call } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { 
  RefreshCcw, Loader2, TrendingUp, TrendingDown, Users, 
  UserMinus, UserPlus, DollarSign, Clock, Calendar,
  BarChart3, PieChart, Activity, AlertTriangle, CheckCircle,
  ArrowUpRight, ArrowDownRight, Building2, Briefcase, Heart,
  Award, Target, Zap, Shield, GraduationCap
} from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import { useDrillDown } from './composables/useDrillDown'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'

const router = useRouter()

// State
const isLoading = ref(true)
const isRefreshing = ref(false)
const error = ref<string | null>(null)
const data = ref<any>(null)

const drillDown = useDrillDown()
const HR_ENDPOINT = 'insights.api.ml.hr.get_hr_detail'

// Period filter
const period = ref('TTM')
const periods = [
  { value: 'MTD', label: 'Month to Date' },
  { value: 'QTD', label: 'Quarter to Date' },
  { value: 'YTD', label: 'Year to Date' },
  { value: 'TTM', label: 'Trailing 12 Months' },
]

// Active tab
const activeTab = ref('overview')
const tabs = [
  { id: 'overview', label: 'Workforce Overview', icon: Users },
  { id: 'attrition', label: 'Attrition & Retention', icon: UserMinus },
  { id: 'payroll', label: 'Payroll & Compensation', icon: DollarSign },
  { id: 'departments', label: 'Department Health', icon: Building2 },
  { id: 'planning', label: 'Workforce Planning', icon: Target },
]

// Load HR data
async function loadData(refresh = false) {
  if (refresh) {
    isRefreshing.value = true
  } else {
    isLoading.value = true
  }
  error.value = null
  
  try {
    data.value = await apiCall('insights.api.ml.get_hr_overview', {
      period: period.value
    })
  } catch (e: any) {
    console.error('Error loading HR data:', e)
    error.value = e.message || 'Failed to load HR data'
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

// Computed KPIs
const kpis = computed(() => {
  if (!data.value) return []
  const hc = data.value.headcount_metrics || {}
  const att = data.value.attrition_metrics || {}
  const pay = data.value.payroll_metrics || {}
  const eng = data.value.engagement_indicators || {}
  
  return [
    {
      label: 'Total Headcount',
      value: formatNumber(hc.total_employees || 0),
      subtitle: `${hc.new_hires || 0} new hires · ${hc.exits || 0} exits`,
      change: hc.growth_rate_pct || 0,
      icon: Users,
      color: 'blue',
      drillable: true,
      metric: 'total_employees',
    },
    {
      label: 'Attrition Rate',
      value: `${(att.attrition_rate_pct || 0).toFixed(1)}%`,
      subtitle: `${att.total_exits || 0} exits (${att.voluntary_exits || 0} voluntary)`,
      change: att.attrition_rate_pct > 15 ? -1 : 1, // red if above 15%
      icon: UserMinus,
      color: 'red',
      drillable: false,
      metric: null,
    },
    {
      label: 'Avg. Salary',
      value: formatCurrency(pay.average_salary || 0),
      subtitle: `Total: ${formatCurrency(pay.total_payroll_cost || 0)}`,
      change: 0,
      icon: DollarSign,
      color: 'green',
      drillable: false,
      metric: null,
    },
    {
      label: 'Engagement Score',
      value: `${(eng.engagement_score || 0).toFixed(0)}/100`,
      subtitle: eng.engagement_level || 'N/A',
      change: eng.engagement_score >= 75 ? 1 : eng.engagement_score >= 50 ? 0 : -1,
      icon: Heart,
      color: 'purple',
      drillable: false,
      metric: null,
    },
  ]
})

// Department data — backend returns { department_metrics: { "Dept": { headcount, payroll_cost, cost_per_employee } } }
const departments = computed(() => {
  if (!data.value?.department_health) return []
  const dh = data.value.department_health
  const metrics = dh.department_metrics || dh
  if (Array.isArray(metrics)) return metrics
  return Object.entries(metrics).map(([name, val]: [string, any]) => ({
    department: name,
    headcount: val.headcount || val.count || 0,
    payroll_cost: val.payroll_cost || 0,
    cost_per_employee: val.cost_per_employee || val.avg_cost || 0,
  }))
})

// Workforce composition — backend returns { gender_ratios: {M: 60.5, F: 39.5}, employment_type_distribution: [{employment_type, count}] }
const composition = computed(() => {
  if (!data.value?.workforce_composition) return null
  const wc = data.value.workforce_composition
  return {
    gender: wc.gender_ratios || null,
    employment_type: wc.employment_type_distribution
      ? Object.fromEntries(
          (wc.employment_type_distribution as any[]).map((e: any) => [e.employment_type || e.type, e.count])
        )
      : null,
    departments: wc.department_distribution
      ? Object.fromEntries(
          (wc.department_distribution as any[]).map((e: any) => [e.department, e.count])
        )
      : null,
  }
})

// Attrition risk — backend returns { risk_level, risk_score, risk_factors, predicted_attrition_rate }
const attritionRisk = computed(() => {
  if (!data.value?.attrition_risk) return null
  return data.value.attrition_risk
})

// Recommendations
const recommendations = computed(() => {
  return data.value?.recommendations || []
})

// Helpers
function formatCurrency(value: number) {
  if (!value) return 'KES 0'
  if (value >= 1000000) return `KES ${(value / 1000000).toFixed(1)}M`
  if (value >= 1000) return `KES ${(value / 1000).toFixed(0)}K`
  return `KES ${value.toFixed(0)}`
}

function formatNumber(value: number) {
  if (!value) return '0'
  return value.toLocaleString()
}

function getChangeColor(value: number) {
  if (value > 0) return 'text-green-600'
  if (value < 0) return 'text-red-600'
  return 'text-gray-500'
}

function getChangeIcon(value: number) {
  return value >= 0 ? ArrowUpRight : ArrowDownRight
}

function getHealthColor(score: number) {
  if (score >= 80) return 'text-green-600 bg-green-100'
  if (score >= 60) return 'text-amber-600 bg-amber-100'
  return 'text-red-600 bg-red-100'
}

function handleChatNavigation(path: string) {
  router.push(path)
}

onMounted(() => loadData())
</script>

<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <header class="bg-white border-b px-6 py-4">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">HR Intelligence</h1>
          <p class="text-sm text-gray-500 mt-1">Workforce analytics, talent management & organizational health</p>
        </div>
        <div class="flex items-center gap-3">
          <select v-model="period" @change="loadData()" class="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white">
            <option v-for="p in periods" :key="p.value" :value="p.value">{{ p.label }}</option>
          </select>
          <button @click="loadData(true)" :disabled="isRefreshing"
            class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50">
            <RefreshCcw v-if="!isRefreshing" class="w-4 h-4" />
            <Loader2 v-else class="w-4 h-4 animate-spin" />
            Refresh
          </button>
        </div>
      </div>
    </header>

    <!-- Loading -->
    <div v-if="isLoading && !data" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <Loader2 class="w-12 h-12 mx-auto text-blue-600 animate-spin" />
        <p class="mt-4 text-gray-600">Loading HR intelligence...</p>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error && !data" class="flex items-center justify-center flex-1">
      <div class="text-center max-w-md">
        <AlertTriangle class="w-12 h-12 mx-auto text-red-500" />
        <p class="mt-4 text-gray-900 font-medium">Failed to load data</p>
        <p class="text-gray-600 mt-1">{{ error }}</p>
        <button @click="loadData()" class="mt-4 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700">
          Try Again
        </button>
      </div>
    </div>

    <!-- Main Content -->
    <div v-else-if="data" class="flex-1 overflow-auto">
      <!-- KPI Cards -->
      <div class="p-6 grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div
          v-for="kpi in kpis"
          :key="kpi.label"
          :class="[
            'bg-white rounded-lg shadow-sm border p-4',
            kpi.drillable ? 'cursor-pointer hover:ring-2 hover:ring-blue-300 transition-shadow' : ''
          ]"
          @click="kpi.drillable && drillDown.open(HR_ENDPOINT, kpi.label, { metric: kpi.metric })"
        >
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-gray-500">{{ kpi.label }}</p>
              <p class="text-2xl font-bold text-gray-900 mt-1">{{ kpi.value }}</p>
              <p class="text-xs text-gray-500 mt-0.5">{{ kpi.subtitle }}</p>
              <div v-if="kpi.change" class="flex items-center gap-1 mt-1" :class="getChangeColor(kpi.change)">
                <component :is="getChangeIcon(kpi.change)" class="w-3 h-3" />
                <span class="text-sm">{{ Math.abs(kpi.change).toFixed(1) }}%</span>
              </div>
            </div>
            <div class="p-3 rounded-lg" :class="`bg-${kpi.color}-100`">
              <component :is="kpi.icon" class="w-6 h-6" :class="`text-${kpi.color}-600`" />
            </div>
          </div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="bg-white border-b mx-6 rounded-t-lg">
        <div class="flex overflow-x-auto">
          <button v-for="tab in tabs" :key="tab.id" @click="activeTab = tab.id"
            :class="['flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 -mb-px',
              activeTab === tab.id ? 'text-blue-600 border-blue-600' : 'text-gray-500 border-transparent hover:text-gray-700']">
            <component :is="tab.icon" class="w-4 h-4" />
            {{ tab.label }}
          </button>
        </div>
      </div>

      <!-- Tab Content -->
      <div class="p-6">
        <!-- Workforce Overview Tab -->
        <div v-show="activeTab === 'overview'" class="space-y-6">
          <!-- Workforce Composition -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Workforce Composition</h3>
            <div v-if="composition" class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <!-- By Gender (percentages from gender_ratios) -->
              <div v-if="composition.gender" class="bg-gray-50 rounded-lg p-4">
                <h4 class="text-sm font-medium text-gray-700 mb-3">By Gender</h4>
                <div class="space-y-2">
                  <div v-for="(pct, gender) in composition.gender" :key="gender as string"
                    class="flex justify-between items-center">
                    <span class="text-sm text-gray-600 capitalize">{{ gender }}</span>
                    <span class="text-sm font-medium text-gray-900">{{ pct }}%</span>
                  </div>
                </div>
              </div>
              <!-- By Employment Type -->
              <div v-if="composition.employment_type" class="bg-gray-50 rounded-lg p-4">
                <h4 class="text-sm font-medium text-gray-700 mb-3">By Type</h4>
                <div class="space-y-2">
                  <div
                    v-for="(count, type) in composition.employment_type"
                    :key="type as string"
                    class="flex justify-between items-center cursor-pointer hover:bg-blue-50 rounded px-1 -mx-1 transition-colors"
                    @click="drillDown.open(HR_ENDPOINT, type + ' Employees', { metric: 'employment_type', employment_type: type })"
                  >
                    <span class="text-sm text-gray-600 capitalize">{{ type }}</span>
                    <span class="text-sm font-medium text-gray-900">{{ count }}</span>
                  </div>
                </div>
              </div>
              <!-- By Department -->
              <div v-if="composition.departments" class="bg-gray-50 rounded-lg p-4">
                <h4 class="text-sm font-medium text-gray-700 mb-3">By Department</h4>
                <div class="space-y-2">
                  <div v-for="(count, dept) in composition.departments" :key="dept as string"
                    class="flex justify-between items-center">
                    <span class="text-sm text-gray-600">{{ dept }}</span>
                    <span class="text-sm font-medium text-gray-900">{{ count }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <PieChart class="w-8 h-8 mx-auto mb-2" />
              <p>No composition data available</p>
            </div>
          </div>

          <!-- Headcount Trends -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Headcount Metrics</h3>
            <div v-if="data?.headcount_metrics" class="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div class="bg-blue-50 rounded-lg p-4 text-center">
                <p class="text-sm text-blue-700 font-medium">Total Employees</p>
                <p class="text-2xl font-bold text-blue-900 mt-1">
                  {{ data.headcount_metrics.total_employees || 0 }}
                </p>
              </div>
              <div class="bg-green-50 rounded-lg p-4 text-center">
                <p class="text-sm text-green-700 font-medium">New Hires</p>
                <p class="text-2xl font-bold text-green-900 mt-1">
                  {{ data.headcount_metrics.new_hires || 0 }}
                </p>
              </div>
              <div class="bg-red-50 rounded-lg p-4 text-center">
                <p class="text-sm text-red-700 font-medium">Exits</p>
                <p class="text-2xl font-bold text-red-900 mt-1">
                  {{ data.headcount_metrics.exits || 0 }}
                </p>
              </div>
              <div class="bg-purple-50 rounded-lg p-4 text-center">
                <p class="text-sm text-purple-700 font-medium">Net Growth</p>
                <p class="text-2xl font-bold text-purple-900 mt-1"
                  :class="(data.headcount_metrics.net_growth || 0) >= 0 ? 'text-green-700' : 'text-red-700'">
                  {{ (data.headcount_metrics.net_growth || 0) >= 0 ? '+' : '' }}{{ data.headcount_metrics.net_growth || 0 }}
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- Attrition & Retention Tab -->
        <div v-show="activeTab === 'attrition'" class="space-y-6">
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Attrition Analysis</h3>
            <div v-if="data?.attrition_metrics" class="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div class="bg-red-50 rounded-lg p-4 text-center">
                <p class="text-sm text-red-700 font-medium">Attrition Rate</p>
                <p class="text-3xl font-bold text-red-900 mt-1">
                  {{ (data.attrition_metrics.attrition_rate_pct || 0).toFixed(1) }}%
                </p>
              </div>
              <div class="bg-amber-50 rounded-lg p-4 text-center">
                <p class="text-sm text-amber-700 font-medium">Total Exits</p>
                <p class="text-2xl font-bold text-amber-900 mt-1">
                  {{ data.attrition_metrics.total_exits || 0 }}
                </p>
              </div>
              <div class="bg-orange-50 rounded-lg p-4 text-center">
                <p class="text-sm text-orange-700 font-medium">Voluntary Exits</p>
                <p class="text-2xl font-bold text-orange-900 mt-1">
                  {{ data.attrition_metrics.voluntary_exits || 0 }}
                </p>
              </div>
              <div class="bg-blue-50 rounded-lg p-4 text-center">
                <p class="text-sm text-blue-700 font-medium">Risk Level</p>
                <p class="text-2xl font-bold mt-1" :class="{
                  'text-red-700': data.attrition_metrics.attrition_risk_level === 'high',
                  'text-amber-700': data.attrition_metrics.attrition_risk_level === 'medium',
                  'text-green-700': data.attrition_metrics.attrition_risk_level === 'low'
                }">
                  {{ (data.attrition_metrics.attrition_risk_level || 'N/A').toUpperCase() }}
                </p>
              </div>
            </div>
          </div>

          <!-- Attrition Risk -->
          <div v-if="attritionRisk" class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Attrition Risk Assessment</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div class="rounded-lg p-4 text-center" :class="{
                'bg-red-50': attritionRisk.risk_level === 'high',
                'bg-amber-50': attritionRisk.risk_level === 'medium',
                'bg-green-50': attritionRisk.risk_level === 'low'
              }">
                <p class="text-sm font-medium text-gray-700">Overall Risk Level</p>
                <p class="text-3xl font-bold mt-1" :class="{
                  'text-red-700': attritionRisk.risk_level === 'high',
                  'text-amber-700': attritionRisk.risk_level === 'medium',
                  'text-green-700': attritionRisk.risk_level === 'low'
                }">{{ (attritionRisk.risk_level || 'N/A').toUpperCase() }}</p>
                <p class="text-xs text-gray-500 mt-1">Score: {{ attritionRisk.risk_score || 0 }}/100</p>
              </div>
              <div class="bg-blue-50 rounded-lg p-4 text-center">
                <p class="text-sm text-blue-700 font-medium">Predicted Attrition</p>
                <p class="text-2xl font-bold text-blue-900 mt-1">
                  {{ (attritionRisk.predicted_attrition_rate || 0).toFixed(1) }}%
                </p>
                <p class="text-xs text-blue-600">next period</p>
              </div>
              <div class="bg-gray-50 rounded-lg p-4">
                <p class="text-sm font-medium text-gray-700 mb-2">Risk Factors</p>
                <div v-if="attritionRisk.risk_factors?.length" class="space-y-1">
                  <div v-for="(factor, i) in attritionRisk.risk_factors" :key="i" class="flex items-start gap-2">
                    <AlertTriangle class="w-3 h-3 text-amber-500 mt-0.5 flex-shrink-0" />
                    <span class="text-xs text-gray-600">{{ factor }}</span>
                  </div>
                </div>
                <p v-else class="text-xs text-gray-500">No significant risk factors</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Payroll & Compensation Tab -->
        <div v-show="activeTab === 'payroll'" class="space-y-6">
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Payroll Summary</h3>
            <div v-if="data?.payroll_metrics" class="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div class="bg-green-50 rounded-lg p-4 text-center">
                <p class="text-sm text-green-700 font-medium">Total Payroll</p>
                <p class="text-2xl font-bold text-green-900 mt-1">
                  {{ formatCurrency(data.payroll_metrics.total_payroll_cost || 0) }}
                </p>
              </div>
              <div class="bg-blue-50 rounded-lg p-4 text-center">
                <p class="text-sm text-blue-700 font-medium">Avg Salary</p>
                <p class="text-2xl font-bold text-blue-900 mt-1">
                  {{ formatCurrency(data.payroll_metrics.average_salary || 0) }}
                </p>
              </div>
              <div class="bg-purple-50 rounded-lg p-4 text-center">
                <p class="text-sm text-purple-700 font-medium">Cost Per Employee</p>
                <p class="text-2xl font-bold text-purple-900 mt-1">
                  {{ formatCurrency(data.payroll_metrics.cost_per_employee || 0) }}
                </p>
              </div>
              <div class="bg-amber-50 rounded-lg p-4 text-center">
                <p class="text-sm text-amber-700 font-medium">Deduction Rate</p>
                <p class="text-2xl font-bold text-amber-900 mt-1">
                  {{ (data.payroll_metrics.deduction_rate_pct || 0).toFixed(1) }}%
                </p>
              </div>
            </div>
          </div>

          <!-- Compensation Analysis -->
          <div v-if="data?.compensation_analysis" class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Compensation Analysis</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div class="bg-gray-50 rounded-lg p-4">
                <h4 class="text-sm font-medium text-gray-700 mb-3">Key Metrics</h4>
                <div class="space-y-2">
                  <div class="flex justify-between items-center">
                    <span class="text-sm text-gray-600">Median Salary</span>
                    <span class="text-sm font-medium text-gray-900">{{ formatCurrency(data.compensation_analysis.median_salary || 0) }}</span>
                  </div>
                  <div class="flex justify-between items-center">
                    <span class="text-sm text-gray-600">Pay Ratio (High/Low)</span>
                    <span class="text-sm font-medium text-gray-900">{{ (data.compensation_analysis.pay_ratio || 0).toFixed(1) }}x</span>
                  </div>
                  <div class="flex justify-between items-center">
                    <span class="text-sm text-gray-600">Highest Paying Dept</span>
                    <span class="text-sm font-medium text-gray-900">{{ data.compensation_analysis.highest_paying_dept || 'N/A' }}</span>
                  </div>
                  <div class="flex justify-between items-center">
                    <span class="text-sm text-gray-600">Lowest Paying Dept</span>
                    <span class="text-sm font-medium text-gray-900">{{ data.compensation_analysis.lowest_paying_dept || 'N/A' }}</span>
                  </div>
                  <div class="flex justify-between items-center">
                    <span class="text-sm text-gray-600">Pay Equity</span>
                    <span class="text-sm font-medium" :class="data.compensation_analysis.pay_equity_status === 'good' ? 'text-green-600' : 'text-amber-600'">
                      {{ (data.compensation_analysis.pay_equity_status || 'N/A').replace('_', ' ') }}
                    </span>
                  </div>
                </div>
              </div>
              <div class="bg-gray-50 rounded-lg p-4">
                <h4 class="text-sm font-medium text-gray-700 mb-3">Salary Variance</h4>
                <p class="text-3xl font-bold text-gray-900">{{ formatCurrency(data.compensation_analysis.salary_variance || 0) }}</p>
                <p class="text-xs text-gray-500 mt-1">Standard deviation across departments</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Department Health Tab -->
        <div v-show="activeTab === 'departments'" class="space-y-6">
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Department Overview</h3>
            <div v-if="departments.length > 0" class="space-y-3">
              <div
                v-for="dept in departments"
                :key="dept.department"
                class="flex items-center justify-between p-4 bg-gray-50 rounded-lg cursor-pointer hover:ring-2 hover:ring-blue-300 transition-shadow"
                @click="drillDown.open(HR_ENDPOINT, dept.department + ' Employees', { metric: 'dept_employees', department: dept.department })"
              >
                <div class="flex-1">
                  <div class="flex items-center gap-3">
                    <Building2 class="w-5 h-5 text-gray-400" />
                    <div>
                      <p class="text-sm font-medium text-gray-900">{{ dept.department }}</p>
                      <p class="text-xs text-gray-500">
                        {{ dept.headcount }} employees
                      </p>
                    </div>
                  </div>
                </div>
                <div class="flex items-center gap-4">
                  <div class="text-right">
                    <p class="text-xs text-gray-500">Payroll Cost</p>
                    <p class="text-sm font-medium text-gray-900">{{ formatCurrency(dept.payroll_cost || 0) }}</p>
                  </div>
                  <div class="text-right">
                    <p class="text-xs text-gray-500">Cost/Employee</p>
                    <p class="text-sm font-medium text-gray-900">{{ formatCurrency(dept.cost_per_employee || 0) }}</p>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <Building2 class="w-8 h-8 mx-auto mb-2" />
              <p>No department data available</p>
            </div>
          </div>
        </div>

        <!-- Workforce Planning Tab -->
        <div v-show="activeTab === 'planning'" class="space-y-6">
          <!-- Hiring Forecast -->
          <div v-if="data?.hiring_forecast" class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Hiring Forecast</h3>
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div class="bg-blue-50 rounded-lg p-4 text-center">
                <p class="text-sm text-blue-700 font-medium">Total Hiring Need</p>
                <p class="text-2xl font-bold text-blue-900 mt-1">
                  {{ data.hiring_forecast.total_hiring_need || 0 }}
                </p>
              </div>
              <div class="bg-red-50 rounded-lg p-4 text-center">
                <p class="text-sm text-red-700 font-medium">Projected Exits</p>
                <p class="text-2xl font-bold text-red-900 mt-1">
                  {{ data.hiring_forecast.projected_exits_next_quarter || 0 }}
                </p>
              </div>
              <div class="bg-green-50 rounded-lg p-4 text-center">
                <p class="text-sm text-green-700 font-medium">Growth-Based Hires</p>
                <p class="text-2xl font-bold text-green-900 mt-1">
                  {{ data.hiring_forecast.growth_based_hiring || 0 }}
                </p>
              </div>
              <div class="bg-purple-50 rounded-lg p-4 text-center">
                <p class="text-sm text-purple-700 font-medium">Urgency</p>
                <p class="text-2xl font-bold mt-1" :class="data.hiring_forecast.hiring_urgency === 'high' ? 'text-red-700' : 'text-green-700'">
                  {{ (data.hiring_forecast.hiring_urgency || 'normal').toUpperCase() }}
                </p>
              </div>
            </div>
          </div>

          <!-- Recommendations -->
          <div v-if="recommendations.length > 0" class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">AI Recommendations</h3>
            <div class="space-y-3">
              <div v-for="(rec, i) in recommendations" :key="i"
                class="flex items-start gap-3 p-3 bg-blue-50 rounded-lg">
                <Zap class="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p class="text-sm font-medium text-blue-900">{{ rec.title || rec }}</p>
                  <p v-if="rec.description" class="text-xs text-blue-700 mt-1">{{ rec.description }}</p>
                  <p v-if="rec.impact" class="text-xs text-blue-600 mt-1">Impact: {{ rec.impact }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <DashboardChatButton
      dashboard-type="HR"
      :dashboard-context="{ dashboard: 'HR Intelligence', data: data }"
      @navigate-dashboard="handleChatNavigation"
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
