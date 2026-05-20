<script setup lang="ts">
defineOptions({ name: 'MarketingCRMIntelligence' })
import { Breadcrumbs } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { 
  RefreshCcw, Loader2, TrendingUp, TrendingDown, Target, 
  Users, Megaphone, BarChart3, PieChart, Activity,
  ArrowUpRight, ArrowDownRight, AlertTriangle, CheckCircle, 
  Clock, Filter, Zap, Mail, MousePointerClick, DollarSign,
  Percent, Eye, UserPlus, ArrowRightLeft
} from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import BaseChart from '../charts/components/BaseChart.vue'
import TerritoryMap from '../components/TerritoryMap.vue'

const router = useRouter()

// State
const isLoading = ref(true)
const isRefreshing = ref(false)
const error = ref<string | null>(null)
const data = ref<any>(null)

// Source metrics state
const sourceMetrics = ref<any>(null)
const costPerLead = ref<any>(null)
const territoryLeadsData = ref<any>(null)
const isLoadingSources = ref(false)

// Period filter
const period = ref('YTD')
const periods = [
  { value: 'MTD', label: 'Month to Date' },
  { value: 'QTD', label: 'Quarter to Date' },
  { value: 'YTD', label: 'Year to Date' },
  { value: 'TTM', label: 'Trailing 12 Months' },
]

// Active tab
const activeTab = ref('pipeline')
const tabs = [
  { id: 'pipeline', label: 'Pipeline', icon: Target },
  { id: 'leads', label: 'Lead Analytics', icon: UserPlus },
  { id: 'campaigns', label: 'Campaigns', icon: Megaphone },
  { id: 'conversions', label: 'Conversions', icon: ArrowRightLeft },
  { id: 'roi', label: 'Marketing ROI', icon: DollarSign },
  { id: 'sources', label: 'Source Performance', icon: BarChart3 },
]

// Load marketing data
async function loadData(refresh = false) {
  if (refresh) {
    isRefreshing.value = true
  } else {
    isLoading.value = true
  }
  error.value = null
  
  try {
    data.value = await apiCall('insights.ml.marketing_intelligence.get_marketing_overview', {
      period: period.value
    })
  } catch (e: any) {
    console.error('Error loading marketing data:', e)
    error.value = e.message || 'Failed to load marketing data'
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

// Load source metrics
async function loadSourceMetrics() {
  isLoadingSources.value = true
  try {
    const [metrics, costs, territories] = await Promise.all([
      apiCall('insights.api.ml.marketing.source_metrics', { period: period.value }),
      apiCall('insights.api.ml.marketing.cost_per_lead', { period: period.value }),
      apiCall('insights.api.ml.marketing.territory_leads', { period: period.value }),
    ])
    sourceMetrics.value = metrics
    costPerLead.value = costs
    territoryLeadsData.value = territories
  } catch (e: any) {
    console.error('Error loading source metrics:', e)
  } finally {
    isLoadingSources.value = false
  }
}

// Computed KPIs
const kpis = computed(() => {
  if (!data.value) return []
  const pipeline = data.value.pipeline_metrics || {}
  const leads = data.value.lead_metrics || {}
  const conversion = data.value.conversion_metrics || {}
  const roi = data.value.marketing_roi || {}
  
  return [
    {
      label: 'Pipeline Value',
      value: formatCurrency(pipeline.total_pipeline_value || pipeline.total_value || 0),
      change: pipeline.growth_rate || 0,
      icon: Target,
      color: 'blue'
    },
    {
      label: 'Active Leads',
      value: formatNumber(leads.total_leads || leads.active_leads || 0),
      change: leads.growth_rate || 0,
      icon: UserPlus,
      color: 'green'
    },
    {
      label: 'Conversion Rate',
      value: formatPercent(conversion.overall_rate || conversion.lead_to_opportunity || 0),
      change: conversion.change || 0,
      icon: ArrowRightLeft,
      color: 'purple'
    },
    {
      label: 'Marketing ROI',
      value: roi.overall_roi ? `${roi.overall_roi.toFixed(1)}x` : 'N/A',
      change: roi.roi_change || 0,
      icon: DollarSign,
      color: 'amber'
    },
  ]
})

// Pipeline stages
const pipelineStages = computed(() => {
  if (!data.value?.pipeline_metrics) return []
  const stages = data.value.pipeline_metrics.stage_breakdown 
    || data.value.pipeline_metrics.stages 
    || data.value.pipeline_metrics.by_stage
    || []
  return Array.isArray(stages) ? stages : Object.entries(stages).map(([name, val]: [string, any]) => ({
    stage: name,
    count: val.count || val,
    value: val.value || val.amount || 0,
    conversion_rate: val.conversion_rate || 0
  }))
})

// Lead sources
const leadSources = computed(() => {
  if (!data.value?.lead_metrics) return []
  const sources = data.value.lead_metrics.by_source 
    || data.value.lead_metrics.source_breakdown 
    || []
  return Array.isArray(sources) ? sources : Object.entries(sources).map(([name, val]: [string, any]) => ({
    source: name,
    count: val.count || val,
    conversion_rate: val.conversion_rate || 0,
    quality_score: val.quality_score || 0
  }))
})

// Campaigns
const campaigns = computed(() => {
  if (!data.value?.campaign_metrics) return []
  const list = data.value.campaign_metrics.campaigns 
    || data.value.campaign_metrics.active_campaigns 
    || data.value.campaign_metrics.campaign_list
    || []
  return Array.isArray(list) ? list : []
})

// Channel performance
const channels = computed(() => {
  if (!data.value?.channel_performance) return []
  const ch = data.value.channel_performance.channels || data.value.channel_performance
  if (Array.isArray(ch)) return ch
  return Object.entries(ch).map(([name, val]: [string, any]) => ({
    channel: name,
    leads: val.leads || 0,
    conversions: val.conversions || 0,
    roi: val.roi || 0,
    cost: val.cost || 0
  }))
})

// Recommendations
const recommendations = computed(() => {
  return data.value?.recommendations || []
})

// Source chart options
const sourceChartOptions = computed(() => {
  if (!sourceMetrics.value?.leads_by_source?.length) return {}
  const data = [...sourceMetrics.value.leads_by_source].reverse()
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value', boundaryGap: [0, 0.01] },
    yAxis: { type: 'category', data: data.map((d: any) => d.source) },
    series: [{
      name: 'Leads',
      type: 'bar',
      data: data.map((d: any) => d.count),
      itemStyle: { color: '#3b82f6' }
    }]
  }
})

const territoryWorldData = computed(() => {
  if (!territoryLeadsData.value) return []
  return territoryLeadsData.value.map((t: any) => ({ name: t.territory, value: t.count }))
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
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`
  return value.toLocaleString()
}

function formatPercent(value: number) {
  if (!value) return '0%'
  return `${value.toFixed(1)}%`
}

function getChangeColor(value: number) {
  if (value > 0) return 'text-green-600'
  if (value < 0) return 'text-red-600'
  return 'text-gray-500'
}

function getChangeIcon(value: number) {
  return value >= 0 ? ArrowUpRight : ArrowDownRight
}

function handleChatNavigation(path: string) {
  router.push(path)
}

onMounted(() => {
  loadData()
  loadSourceMetrics()
})
</script>

<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <header class="bg-white border-b px-6 py-4">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">Marketing & CRM Intelligence</h1>
          <p class="text-sm text-gray-500 mt-1">Pipeline analytics, lead optimization & campaign performance</p>
        </div>
        <div class="flex items-center gap-3">
          <select v-model="period" @change="loadData(); loadSourceMetrics()" class="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white">
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
        <p class="mt-4 text-gray-600">Loading marketing intelligence...</p>
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
        <div v-for="kpi in kpis" :key="kpi.label" class="bg-white rounded-lg shadow-sm border p-4">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-gray-500">{{ kpi.label }}</p>
              <p class="text-2xl font-bold text-gray-900 mt-1">{{ kpi.value }}</p>
              <div class="flex items-center gap-1 mt-1" :class="getChangeColor(kpi.change)">
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
        <!-- Pipeline Tab -->
        <div v-show="activeTab === 'pipeline'" class="space-y-6">
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Sales Pipeline</h3>
            <div v-if="pipelineStages.length > 0" class="space-y-4">
              <div v-for="stage in pipelineStages" :key="stage.stage || stage.name"
                class="flex items-center gap-4">
                <div class="w-40 text-sm font-medium text-gray-700 truncate">{{ stage.stage || stage.name }}</div>
                <div class="flex-1">
                  <div class="bg-gray-200 rounded-full h-6 relative overflow-hidden">
                    <div class="bg-blue-500 h-6 rounded-full transition-all duration-500 flex items-center justify-end pr-2"
                      :style="{ width: `${Math.max(Math.min((stage.count / Math.max(...pipelineStages.map((s: any) => s.count || 1), 1)) * 100, 100), 5)}%` }">
                      <span class="text-xs text-white font-medium">{{ stage.count }}</span>
                    </div>
                  </div>
                </div>
                <div class="w-28 text-right text-sm font-medium text-gray-900">
                  {{ formatCurrency(stage.value || stage.amount || 0) }}
                </div>
              </div>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <Target class="w-8 h-8 mx-auto mb-2" />
              <p>No pipeline data available</p>
            </div>
          </div>

          <!-- Pipeline Forecast -->
          <div v-if="data?.pipeline_forecast" class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Pipeline Forecast</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div class="bg-blue-50 rounded-lg p-4">
                <p class="text-sm text-blue-700 font-medium">Expected Close (30 days)</p>
                <p class="text-xl font-bold text-blue-900 mt-1">
                  {{ formatCurrency(data.pipeline_forecast.next_30_days || data.pipeline_forecast.short_term || 0) }}
                </p>
              </div>
              <div class="bg-green-50 rounded-lg p-4">
                <p class="text-sm text-green-700 font-medium">Expected Close (90 days)</p>
                <p class="text-xl font-bold text-green-900 mt-1">
                  {{ formatCurrency(data.pipeline_forecast.next_90_days || data.pipeline_forecast.medium_term || 0) }}
                </p>
              </div>
              <div class="bg-purple-50 rounded-lg p-4">
                <p class="text-sm text-purple-700 font-medium">Pipeline Velocity</p>
                <p class="text-xl font-bold text-purple-900 mt-1">
                  {{ data.pipeline_forecast.velocity || data.pipeline_forecast.avg_days || 'N/A' }} days
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- Lead Analytics Tab -->
        <div v-show="activeTab === 'leads'" class="space-y-6">
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Lead Sources</h3>
            <div v-if="leadSources.length > 0" class="space-y-3">
              <div v-for="source in leadSources" :key="source.source || source.name"
                class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <p class="text-sm font-medium text-gray-900">{{ source.source || source.name }}</p>
                  <p class="text-xs text-gray-500">{{ source.count || source.total || 0 }} leads</p>
                </div>
                <div class="text-right">
                  <p class="text-sm font-medium text-green-600">
                    {{ formatPercent(source.conversion_rate || 0) }} conversion
                  </p>
                  <p v-if="source.quality_score" class="text-xs text-gray-500">
                    Quality: {{ source.quality_score.toFixed(0) }}/100
                  </p>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <Users class="w-8 h-8 mx-auto mb-2" />
              <p>No lead source data available</p>
            </div>
          </div>

          <!-- Lead Quality -->
          <div v-if="data?.lead_quality_score" class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Lead Quality Score</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div class="text-center p-4 bg-gray-50 rounded-lg">
                <div class="text-3xl font-bold text-blue-600">
                  {{ (data.lead_quality_score.overall_score || data.lead_quality_score.average || 0).toFixed(0) }}
                </div>
                <p class="text-sm text-gray-500 mt-1">Overall Score</p>
              </div>
              <div class="text-center p-4 bg-gray-50 rounded-lg">
                <div class="text-3xl font-bold text-green-600">
                  {{ data.lead_quality_score.hot_leads || data.lead_quality_score.high_quality || 0 }}
                </div>
                <p class="text-sm text-gray-500 mt-1">Hot Leads</p>
              </div>
              <div class="text-center p-4 bg-gray-50 rounded-lg">
                <div class="text-3xl font-bold text-amber-600">
                  {{ data.lead_quality_score.warm_leads || data.lead_quality_score.medium_quality || 0 }}
                </div>
                <p class="text-sm text-gray-500 mt-1">Warm Leads</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Campaigns Tab -->
        <div v-show="activeTab === 'campaigns'" class="space-y-6">
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Campaign Performance</h3>
            <div v-if="campaigns.length > 0" class="overflow-x-auto">
              <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                  <tr>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Campaign</th>
                    <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Leads</th>
                    <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Conversions</th>
                    <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Revenue</th>
                    <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-200">
                  <tr v-for="campaign in campaigns" :key="campaign.name || campaign.campaign_name" class="hover:bg-gray-50">
                    <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ campaign.campaign_name || campaign.name }}</td>
                    <td class="px-4 py-3 text-sm text-right text-gray-700">{{ campaign.leads_generated || campaign.leads || 0 }}</td>
                    <td class="px-4 py-3 text-sm text-right text-gray-700">{{ campaign.conversions || 0 }}</td>
                    <td class="px-4 py-3 text-sm text-right font-medium text-gray-900">{{ formatCurrency(campaign.revenue || 0) }}</td>
                    <td class="px-4 py-3 text-center">
                      <span class="px-2 py-1 text-xs rounded-full font-medium"
                        :class="campaign.status === 'Active' || campaign.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'">
                        {{ campaign.status || 'N/A' }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <Megaphone class="w-8 h-8 mx-auto mb-2" />
              <p>No campaign data available</p>
            </div>
          </div>
        </div>

        <!-- Conversions Tab -->
        <div v-show="activeTab === 'conversions'" class="space-y-6">
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Conversion Funnel</h3>
            <div v-if="data?.conversion_metrics" class="space-y-4">
              <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div class="bg-blue-50 rounded-lg p-4 text-center">
                  <p class="text-sm text-blue-700 font-medium">Lead → Opportunity</p>
                  <p class="text-2xl font-bold text-blue-900 mt-1">
                    {{ formatPercent(data.conversion_metrics.lead_to_opportunity || 0) }}
                  </p>
                </div>
                <div class="bg-green-50 rounded-lg p-4 text-center">
                  <p class="text-sm text-green-700 font-medium">Opportunity → Quotation</p>
                  <p class="text-2xl font-bold text-green-900 mt-1">
                    {{ formatPercent(data.conversion_metrics.opportunity_to_quotation || 0) }}
                  </p>
                </div>
                <div class="bg-purple-50 rounded-lg p-4 text-center">
                  <p class="text-sm text-purple-700 font-medium">Quotation → Order</p>
                  <p class="text-2xl font-bold text-purple-900 mt-1">
                    {{ formatPercent(data.conversion_metrics.quotation_to_order || 0) }}
                  </p>
                </div>
                <div class="bg-amber-50 rounded-lg p-4 text-center">
                  <p class="text-sm text-amber-700 font-medium">Overall Rate</p>
                  <p class="text-2xl font-bold text-amber-900 mt-1">
                    {{ formatPercent(data.conversion_metrics.overall_rate || 0) }}
                  </p>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <ArrowRightLeft class="w-8 h-8 mx-auto mb-2" />
              <p>No conversion data available</p>
            </div>
          </div>

          <!-- Channel Performance -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Channel Performance</h3>
            <div v-if="channels.length > 0" class="space-y-3">
              <div v-for="ch in channels" :key="ch.channel || ch.name"
                class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <p class="text-sm font-medium text-gray-900">{{ ch.channel || ch.name }}</p>
                  <p class="text-xs text-gray-500">{{ ch.leads || 0 }} leads · {{ ch.conversions || 0 }} conversions</p>
                </div>
                <div class="text-right">
                  <p class="text-sm font-medium" :class="(ch.roi || 0) > 1 ? 'text-green-600' : 'text-red-600'">
                    {{ ch.roi ? `${ch.roi.toFixed(1)}x ROI` : 'N/A' }}
                  </p>
                  <p v-if="ch.cost" class="text-xs text-gray-500">Cost: {{ formatCurrency(ch.cost) }}</p>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <BarChart3 class="w-8 h-8 mx-auto mb-2" />
              <p>No channel data available</p>
            </div>
          </div>
        </div>

        <!-- Marketing ROI Tab -->
        <div v-show="activeTab === 'roi'" class="space-y-6">
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Marketing ROI Overview</h3>
            <div v-if="data?.marketing_roi" class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div class="bg-green-50 rounded-lg p-4 text-center">
                <p class="text-sm text-green-700 font-medium">Overall ROI</p>
                <p class="text-3xl font-bold text-green-900 mt-1">
                  {{ data.marketing_roi.overall_roi ? `${data.marketing_roi.overall_roi.toFixed(1)}x` : 'N/A' }}
                </p>
              </div>
              <div class="bg-blue-50 rounded-lg p-4 text-center">
                <p class="text-sm text-blue-700 font-medium">Total Spend</p>
                <p class="text-2xl font-bold text-blue-900 mt-1">
                  {{ formatCurrency(data.marketing_roi.total_spend || data.marketing_roi.total_cost || 0) }}
                </p>
              </div>
              <div class="bg-purple-50 rounded-lg p-4 text-center">
                <p class="text-sm text-purple-700 font-medium">Revenue Generated</p>
                <p class="text-2xl font-bold text-purple-900 mt-1">
                  {{ formatCurrency(data.marketing_roi.revenue_generated || data.marketing_roi.total_revenue || 0) }}
                </p>
              </div>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <DollarSign class="w-8 h-8 mx-auto mb-2" />
              <p>No ROI data available</p>
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
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Source Performance Tab -->
        <div v-show="activeTab === 'sources'" class="space-y-6">
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Source Performance</h3>
            <div v-if="sourceMetrics?.leads_by_source?.length" class="h-80">
              <BaseChart :options="sourceChartOptions" />
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <BarChart3 class="w-8 h-8 mx-auto mb-2" />
              <p>No source performance data available</p>
            </div>
          </div>

          <!-- Cost Efficiency -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Cost Efficiency</h3>
            <div v-if="costPerLead?.length" class="overflow-x-auto">
              <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                  <tr>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                    <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Cost Per Source</th>
                    <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Cost Per Lead</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-200">
                  <tr v-for="row in costPerLead" :key="row.source">
                    <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ row.source }}</td>
                    <td class="px-4 py-3 text-sm text-right text-gray-700">{{ formatCurrency(row.total_cost) }}</td>
                    <td class="px-4 py-3 text-sm text-right text-gray-700">{{ formatCurrency(row.cost_per_lead) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <DollarSign class="w-8 h-8 mx-auto mb-2" />
              <p>No cost data available</p>
            </div>
          </div>

          <!-- Territory Leads -->
          <div class="bg-white rounded-lg shadow-sm border p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Territory Leads</h3>
            <div v-if="territoryLeadsData?.length" class="h-96">
              <TerritoryMap
                :worldData="territoryWorldData"
                :indiaData="[]"
                metric="Leads"
                colorScale="purple"
              />
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <Target class="w-8 h-8 mx-auto mb-2" />
              <p>No territory data available</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <DashboardChatButton 
      dashboard-type="Marketing"
      :dashboard-context="{ dashboard: 'Marketing & CRM Intelligence', data: data }"
      @navigate-dashboard="handleChatNavigation"
    />
  </div>
</template>
