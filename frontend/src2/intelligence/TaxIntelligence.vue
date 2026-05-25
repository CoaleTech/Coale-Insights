<script setup lang="ts">
defineOptions({ name: 'TaxIntelligence' })
import { Breadcrumbs } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import {
  RefreshCcw, Loader2, TrendingUp, BarChart3, Activity,
  Target, Percent, AlertTriangle, CheckCircle, Clock, FileText,
  Settings, Calculator, Shield,
} from 'lucide-vue-next'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { createToast } from '../helpers/toasts'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import BaseChart from '../charts/components/BaseChart.vue'

const router = useRouter()

const isLoading = ref(true)
const isRefreshing = ref(false)
const error = ref<string | null>(null)
const data = ref<any>(null)
const activeTab = ref('gst')
const dateFilter = ref('fy')
const baseCurrency = ref('INR')

let pollingTimer: ReturnType<typeof setTimeout> | null = null

const dateRanges = [
  { value: '3m', label: 'Last 3 Months' },
  { value: '6m', label: 'Last 6 Months' },
  { value: '12m', label: 'Last 12 Months' },
  { value: 'fy', label: 'Current FY' },
]

const tabs = [
  { id: 'gst', label: 'GST Overview', icon: FileText },
  { id: 'compliance', label: 'Compliance Health', icon: Shield },
  { id: 'tds', label: 'TDS', icon: Calculator },
  { id: 'planning', label: 'Tax Planning', icon: Target },
  { id: 'settings', label: 'Settings', icon: Settings },
]

const gstSummary = computed(() => data.value?.gst_summary || [])
const itcHealth = computed(() => data.value?.itc_health || {})
const tdsSummary = computed(() => data.value?.tds_summary || {})
const einvoiceStatus = computed(() => data.value?.einvoice_status || {})
const ewaybillStatus = computed(() => data.value?.ewaybill_status || {})
const filingCompliance = computed(() => data.value?.filing_compliance || {})
const reconciliationScore = computed(() => data.value?.reconciliation_score || {})
const hsnSummary = computed(() => data.value?.hsn_summary || [])
const taxForecast = computed(() => data.value?.tax_forecast || {})
const advanceTaxSchedule = computed(() => data.value?.advance_tax_schedule || [])
const einvoiceInfo = computed(() => data.value?.einvoice_compliance_info || {})

// Merged compliance class lookup — replaces two near-identical functions
const COMPLIANCE_CLASSES: Record<string, { text: string; bg: string }> = {
  Compliant:  { text: 'text-green-700', bg: 'bg-green-50 border-green-200' },
  Filed:      { text: 'text-green-700', bg: 'bg-green-50 border-green-200' },
  Pending:    { text: 'text-amber-700', bg: 'bg-amber-50 border-amber-200' },
  'Late Filing': { text: 'text-red-700', bg: 'bg-red-50 border-red-200' },
}
function filingClasses(status: string) {
  return COMPLIANCE_CLASSES[status] ?? { text: 'text-gray-700', bg: 'bg-gray-50 border-gray-200' }
}

// Merged insight class lookup — replaces two near-identical functions
const INSIGHT_CLASSES: Record<string, { bg: string; icon: string }> = {
  warning: { bg: 'bg-amber-50 border-amber-200', icon: 'text-amber-600' },
  success: { bg: 'bg-green-50 border-green-200', icon: 'text-green-600' },
  info:    { bg: 'bg-blue-50 border-blue-200',   icon: 'text-blue-600' },
}
function insightClasses(type: string) {
  return INSIGHT_CLASSES[type] ?? { bg: 'bg-gray-50 border-gray-200', icon: 'text-gray-600' }
}

function getComplianceTextClass(score: number): string {
  if (score >= 80) return 'text-green-600'
  if (score >= 60) return 'text-amber-600'
  return 'text-red-600'
}

function getRateColor(rate: number): string {
  if (rate > 25) return 'text-red-600'
  if (rate > 18) return 'text-amber-600'
  return 'text-green-600'
}

function getStatusBadge(status: string): string {
  const s = String(status).toLowerCase()
  if (s.includes('filed') || s.includes('paid') || s.includes('compliant')) return 'bg-green-100 text-green-700'
  if (s.includes('pending') || s.includes('due')) return 'bg-amber-100 text-amber-700'
  if (s.includes('overdue') || s.includes('failed') || s.includes('late')) return 'bg-red-100 text-red-700'
  return 'bg-gray-100 text-gray-700'
}

async function loadData(refresh = false) {
  if (refresh) isRefreshing.value = true
  else isLoading.value = true
  error.value = null
  try {
    const result = await apiCall('insights.api.ml.tax.tax_intelligence', { refresh })
    if (result?.status === 'queued') {
      createToast({ title: 'Processing', message: result.message || 'Analysis queued', variant: 'info' })
      pollingTimer = setTimeout(checkJobStatus, 5000)
    } else {
      data.value = result
      createToast({ title: 'Data Loaded', message: 'Tax intelligence updated', variant: 'success' })
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to load tax intelligence'
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

async function checkJobStatus() {
  try {
    const status = await apiCall('insights.api.ml.tax.tax_intelligence_status')
    if (status?.status === 'completed') {
      data.value = status.result
      createToast({ title: 'Analysis Complete', message: 'Tax intelligence ready', variant: 'success' })
    } else if (status?.status !== 'not_found') {
      pollingTimer = setTimeout(checkJobStatus, 5000)
    }
  } catch {
    // polling failure is non-critical
  }
}

onUnmounted(() => { if (pollingTimer !== null) clearTimeout(pollingTimer) })
watch(dateFilter, () => loadData())
onMounted(() => loadData())

function formatCurrency(value: number): string {
  if (value == null) return '₹0'
  return new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR',
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(value)
}
function formatNumber(value: number): string { return value?.toLocaleString('en-IN') || '0' }
function formatPercent(value: number): string { return `${(value ?? 0).toFixed(1)}%` }

// Charts
const gstStackedBarOptions = computed(() => {
  const months = gstSummary.value.map((d: any) => d.month)
  if (!months.length) return null
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['CGST', 'SGST', 'IGST'], bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '10%', top: '10%', containLabel: true },
    xAxis: { type: 'category', data: months },
    yAxis: { type: 'value', name: 'Amount (₹)' },
    series: [
      { name: 'CGST', type: 'bar', stack: 'tax', data: gstSummary.value.map((d: any) => d.cgst || 0), itemStyle: { color: '#3b82f6' } },
      { name: 'SGST', type: 'bar', stack: 'tax', data: gstSummary.value.map((d: any) => d.sgst || 0), itemStyle: { color: '#10b981' } },
      { name: 'IGST', type: 'bar', stack: 'tax', data: gstSummary.value.map((d: any) => d.igst || 0), itemStyle: { color: '#f59e0b' } },
    ],
  }
})

const itcGaugeOptions = computed(() => {
  const pct = itcHealth.value.utilization_pct || 0
  return {
    series: [{
      type: 'gauge', startAngle: 180, endAngle: 0, min: 0, max: 100,
      axisLine: { lineStyle: { width: 10, color: [[0.3, '#ef4444'], [0.7, '#f59e0b'], [1, '#10b981']] } },
      pointer: { itemStyle: { color: 'auto' } },
      axisTick: { distance: -10, length: 6, lineStyle: { color: '#fff', width: 1 } },
      splitLine: { distance: -10, length: 14, lineStyle: { color: '#fff', width: 2 } },
      axisLabel: { color: 'inherit', distance: 18, fontSize: 10 },
      detail: { valueAnimation: true, formatter: '{value}%', color: 'inherit', fontSize: 24, offsetCenter: [0, '30%'] },
      data: [{ value: pct, name: 'Utilization' }],
    }],
  }
})

const tdsBarOptions = computed(() => {
  const sections = (tdsSummary.value.payable_by_section || []).slice(0, 5)
  if (!sections.length) return null
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: sections.map((s: any) => s.section) },
    yAxis: { type: 'value', name: 'TDS (₹)' },
    series: [{ type: 'bar', data: sections.map((s: any) => s.amount), itemStyle: { color: '#8b5cf6' } }],
  }
})

const effectiveRateTrendOptions = computed(() => {
  const months = gstSummary.value.map((d: any) => d.month)
  if (!months.length) return null
  const rates = gstSummary.value.map((d: any) => {
    const totalTax = (d.cgst || 0) + (d.sgst || 0) + (d.igst || 0)
    return d.total_revenue > 0 ? +(totalTax / d.total_revenue * 100).toFixed(2) : 0
  })
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
    xAxis: { type: 'category', data: months, boundaryGap: false },
    yAxis: { type: 'value', name: 'Rate %' },
    series: [{ type: 'line', data: rates, smooth: true, itemStyle: { color: '#3b82f6' }, areaStyle: { opacity: 0.2 } }],
  }
})

const taxForecastOptions = computed(() => {
  const forecast = taxForecast.value.forecast || []
  if (!forecast.length) return null
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
    xAxis: { type: 'category', data: forecast.map((f: any) => `Month +${f.month_offset}`), boundaryGap: false },
    yAxis: { type: 'value', name: 'Predicted Net GST (₹)' },
    series: [{ type: 'line', data: forecast.map((f: any) => f.projected_net_gst), smooth: true, itemStyle: { color: '#10b981' }, areaStyle: { opacity: 0.2 } }],
  }
})

const chatContext = computed(() => ({
  summary: { net_gst: data.value?.net_gst, effective_tax_rate: data.value?.effective_tax_rate, compliance_score: data.value?.compliance_score },
  gst_summary: gstSummary.value, itc_health: itcHealth.value, tds_summary: tdsSummary.value,
  einvoice_status: einvoiceStatus.value, ewaybill_status: ewaybillStatus.value,
  filing_compliance: filingCompliance.value, reconciliation_score: reconciliationScore.value,
  hsn_summary: hsnSummary.value, tax_forecast: taxForecast.value,
  activeTab: activeTab.value, date_filter: dateFilter.value,
}))

function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    Sales: '/sales-intelligence', Risk: '/risk-intelligence', Inventory: '/inventory-intelligence',
    Financial: '/financial-intelligence', Customer: '/customer-intelligence',
    Procurement: '/procurement-intelligence', Tax: '/tax-intelligence',
  }
  if (routes[target]) router.push(routes[target])
}
</script>

<template>
  <div class="flex flex-col h-full bg-gray-50">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 bg-white border-b">
      <div>
        <Breadcrumbs :items="[{ label: 'Dashboards', route: '/dashboards' }, { label: 'Tax Intelligence' }]" />
        <h1 class="text-2xl font-bold text-gray-900 mt-1">Tax Intelligence</h1>
        <p class="text-sm text-gray-500">India GST, TDS, ITC analytics, compliance monitoring, and tax planning</p>
      </div>
      <div class="flex items-center gap-3">
        <select v-model="dateFilter" class="px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-blue-500">
          <option v-for="r in dateRanges" :key="r.value" :value="r.value">{{ r.label }}</option>
        </select>
        <button @click="loadData(true)" :disabled="isRefreshing"
          class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50">
          <RefreshCcw v-if="!isRefreshing" class="w-4 h-4" />
          <Loader2 v-else class="w-4 h-4 animate-spin" />
          {{ isRefreshing ? 'Refreshing...' : 'Refresh Analysis' }}
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <Loader2 class="w-12 h-12 mx-auto text-blue-600 animate-spin" />
        <p class="mt-4 text-gray-600">Loading tax intelligence...</p>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <AlertTriangle class="w-12 h-12 mx-auto text-red-500" />
        <p class="mt-4 text-gray-900 font-medium">Failed to load data</p>
        <p class="text-gray-600">{{ error }}</p>
        <button @click="loadData()" class="mt-4 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700">Try Again</button>
      </div>
    </div>

    <!-- Content -->
    <div v-else class="flex-1 overflow-auto p-6">

      <!-- Summary Cards -->
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <Calculator class="w-8 h-8 text-blue-500" />
          <p class="text-2xl font-bold mt-2">{{ formatCurrency(data?.net_gst) }}</p>
          <p class="text-sm text-gray-500">Net GST Payable</p>
          <p class="text-xs text-gray-400 mt-1">Output − Input Tax Credit</p>
        </div>
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <Percent class="w-8 h-8 text-purple-500" />
          <p class="text-2xl font-bold mt-2" :class="getRateColor(data?.effective_tax_rate)">{{ formatPercent(data?.effective_tax_rate) }}</p>
          <p class="text-sm text-gray-500">Effective Tax Rate</p>
          <p class="text-xs mt-1" :class="getRateColor(data?.effective_tax_rate)">
            {{ data?.effective_tax_rate > 25 ? 'High' : data?.effective_tax_rate > 18 ? 'Moderate' : 'Optimal' }}
          </p>
        </div>
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <BarChart3 class="w-8 h-8 text-green-500" />
          <p class="text-2xl font-bold mt-2" :class="getComplianceTextClass(itcHealth.utilization_pct)">{{ formatPercent(itcHealth.utilization_pct) }}</p>
          <p class="text-sm text-gray-500">ITC Utilisation</p>
          <p class="text-xs text-gray-400 mt-1">Input Tax Credit</p>
        </div>
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <Calculator class="w-8 h-8 text-orange-500" />
          <p class="text-2xl font-bold mt-2">{{ formatCurrency(tdsSummary.total_payable) }}</p>
          <p class="text-sm text-gray-500">TDS Payable</p>
          <p class="text-xs text-gray-400 mt-1">Tax Deducted at Source</p>
        </div>
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <FileText class="w-8 h-8 text-teal-500" />
          <p class="text-2xl font-bold mt-2" :class="getComplianceTextClass(einvoiceStatus.coverage_pct)">{{ formatPercent(einvoiceStatus.coverage_pct) }}</p>
          <p class="text-sm text-gray-500">e-Invoice Coverage</p>
          <p class="text-xs text-gray-400 mt-1">IRN filing rate</p>
        </div>
        <div class="bg-white rounded-xl shadow-sm p-4 border">
          <Shield class="w-8 h-8 text-indigo-500" />
          <p class="text-2xl font-bold mt-2" :class="getComplianceTextClass(data?.compliance_score)">{{ data?.compliance_score || 0 }}/100</p>
          <p class="text-sm text-gray-500">Compliance Score</p>
          <p class="text-xs text-gray-400 mt-1">e-Invoice · Filing · Recon</p>
        </div>
      </div>

      <!-- Tabs -->
      <div class="bg-white rounded-xl shadow-sm border mb-6">
        <div class="flex border-b overflow-x-auto">
          <button v-for="tab in tabs" :key="tab.id" @click="activeTab = tab.id"
            :class="['flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 -mb-px',
              activeTab === tab.id ? 'text-blue-600 border-blue-600' : 'text-gray-500 border-transparent hover:text-gray-700']">
            <component :is="tab.icon" class="w-4 h-4" />
            {{ tab.label }}
          </button>
        </div>

        <div class="p-6">

          <!-- ── GST Overview ── -->
          <div v-if="activeTab === 'gst'" class="space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div class="bg-white rounded-xl shadow-sm border p-6">
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <BarChart3 class="w-5 h-5 text-blue-500" /> Monthly GST Breakdown (CGST / SGST / IGST)
                </h3>
                <div class="h-72">
                  <BaseChart v-if="gstStackedBarOptions" :options="gstStackedBarOptions" />
                  <div v-else class="h-full flex items-center justify-center text-gray-500">No GST data available</div>
                </div>
              </div>

              <div class="bg-white rounded-xl shadow-sm border p-6">
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <Activity class="w-5 h-5 text-green-500" /> ITC Utilisation
                </h3>
                <div class="h-72">
                  <BaseChart :options="itcGaugeOptions" />
                </div>
                <div class="grid grid-cols-2 gap-4 mt-4">
                  <div class="p-3 bg-gray-50 rounded-lg text-center">
                    <p class="text-xs text-gray-500">Available</p>
                    <p class="text-lg font-bold text-gray-900">{{ formatCurrency(itcHealth.available) }}</p>
                  </div>
                  <div class="p-3 bg-gray-50 rounded-lg text-center">
                    <p class="text-xs text-gray-500">Claimed</p>
                    <p class="text-lg font-bold text-gray-900">{{ formatCurrency(itcHealth.claimed) }}</p>
                  </div>
                </div>
              </div>
            </div>

            <!-- Filing Status -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div class="p-4 rounded-lg border" :class="filingClasses(filingCompliance.gstr1?.status).bg">
                <div class="flex items-center justify-between">
                  <div>
                    <p class="text-sm font-medium text-gray-900">GSTR-1</p>
                    <p class="text-lg font-bold mt-1" :class="filingClasses(filingCompliance.gstr1?.status).text">
                      {{ filingCompliance.gstr1?.status || 'No Data' }}
                    </p>
                  </div>
                  <FileText class="w-8 h-8 text-gray-400" />
                </div>
                <p class="text-sm mt-2 text-gray-500">Filed: <span class="font-medium">{{ filingCompliance.gstr1?.filed || 0 }}</span></p>
              </div>
              <div class="p-4 rounded-lg border" :class="filingClasses(filingCompliance.gstr3b?.status).bg">
                <div class="flex items-center justify-between">
                  <div>
                    <p class="text-sm font-medium text-gray-900">GSTR-3B</p>
                    <p class="text-lg font-bold mt-1" :class="filingClasses(filingCompliance.gstr3b?.status).text">
                      {{ filingCompliance.gstr3b?.status || 'No Data' }}
                    </p>
                  </div>
                  <FileText class="w-8 h-8 text-gray-400" />
                </div>
                <p class="text-sm mt-2 text-gray-500">Filed: <span class="font-medium">{{ filingCompliance.gstr3b?.filed || 0 }}</span></p>
              </div>
            </div>

            <!-- HSN Summary -->
            <div class="bg-white rounded-xl shadow-sm border p-6">
              <h3 class="font-semibold text-gray-900 mb-4">HSN Summary (Top 10 by Revenue)</h3>
              <div class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead class="bg-gray-50">
                    <tr>
                      <th class="px-4 py-2 text-left">HSN Code</th>
                      <th class="px-4 py-2 text-right">Revenue (Pre-GST)</th>
                      <th class="px-4 py-2 text-right">Actual GST</th>
                      <th class="px-4 py-2 text-right">Eff. Rate</th>
                      <th class="px-4 py-2 text-right">Invoices</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="hsn in hsnSummary.slice(0, 10)" :key="hsn.hsn_code" class="border-b hover:bg-gray-50">
                      <td class="px-4 py-2 font-medium">{{ hsn.hsn_code || '—' }}</td>
                      <td class="px-4 py-2 text-right">{{ formatCurrency(hsn.revenue) }}</td>
                      <td class="px-4 py-2 text-right">{{ formatCurrency(hsn.actual_gst) }}</td>
                      <td class="px-4 py-2 text-right">
                        <span class="px-2 py-1 rounded text-xs"
                          :class="hsn.effective_gst_rate >= 28 ? 'bg-red-100 text-red-700'
                                : hsn.effective_gst_rate >= 18 ? 'bg-amber-100 text-amber-700'
                                : hsn.effective_gst_rate >= 5  ? 'bg-blue-100 text-blue-700'
                                : 'bg-green-100 text-green-700'">
                          {{ formatPercent(hsn.effective_gst_rate) }}
                        </span>
                      </td>
                      <td class="px-4 py-2 text-right">{{ formatNumber(hsn.invoice_count) }}</td>
                    </tr>
                    <tr v-if="!hsnSummary.length">
                      <td colspan="5" class="px-4 py-6 text-center text-gray-500">No HSN data available</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- ── Compliance Health ── -->
          <div v-if="activeTab === 'compliance'" class="space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <!-- e-Invoice -->
              <div class="bg-white rounded-xl shadow-sm border p-4">
                <div class="flex items-center justify-between mb-1">
                  <p class="text-sm text-gray-500">e-Invoice Coverage</p>
                  <span class="text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded px-2 py-0.5">
                    Mandatory ≥ ₹{{ einvoiceInfo.mandatory_threshold_crore || 5 }} Cr AATO
                  </span>
                </div>
                <p class="text-2xl font-bold" :class="getComplianceTextClass(einvoiceStatus.coverage_pct)">
                  {{ formatPercent(einvoiceStatus.coverage_pct) }}
                </p>
                <div class="w-full bg-gray-200 rounded-full h-2 mt-3">
                  <div class="h-2 rounded-full transition-all"
                    :class="einvoiceStatus.coverage_pct >= 80 ? 'bg-green-500' : einvoiceStatus.coverage_pct >= 60 ? 'bg-amber-500' : 'bg-red-500'"
                    :style="{ width: `${Math.min(einvoiceStatus.coverage_pct || 0, 100)}%` }" />
                </div>
                <div class="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                  <div><p class="text-gray-500">Filed</p><p class="font-bold">{{ formatNumber(einvoiceStatus.filed) }}</p></div>
                  <div><p class="text-gray-500">Pending</p><p class="font-bold text-amber-600">{{ formatNumber(einvoiceStatus.pending) }}</p></div>
                  <div><p class="text-gray-500">Failed</p><p class="font-bold text-red-600">{{ formatNumber(einvoiceStatus.failed) }}</p></div>
                </div>
                <p v-if="einvoiceInfo.upload_30day_threshold_crore" class="mt-2 text-xs text-gray-400">
                  ≥ ₹{{ einvoiceInfo.upload_30day_threshold_crore }} Cr: upload within
                  {{ einvoiceInfo.upload_within_days }} days (from {{ einvoiceInfo.upload_30day_mandatory_from }})
                </p>
              </div>

              <!-- e-Waybill -->
              <div class="bg-white rounded-xl shadow-sm border p-4">
                <p class="text-sm text-gray-500">e-Waybill Status</p>
                <div class="mt-3 grid grid-cols-3 gap-2 text-center">
                  <div class="p-2 bg-gray-50 rounded-lg"><p class="text-xs text-gray-500">Total</p><p class="text-lg font-bold">{{ formatNumber(ewaybillStatus.total) }}</p></div>
                  <div class="p-2 bg-green-50 rounded-lg"><p class="text-xs text-green-600">Active</p><p class="text-lg font-bold text-green-700">{{ formatNumber(ewaybillStatus.active) }}</p></div>
                  <div class="p-2 bg-red-50 rounded-lg"><p class="text-xs text-red-600">Cancelled</p><p class="text-lg font-bold text-red-700">{{ formatNumber(ewaybillStatus.cancelled) }}</p></div>
                </div>
              </div>

              <!-- Reconciliation -->
              <div class="bg-white rounded-xl shadow-sm border p-4">
                <p class="text-sm text-gray-500">Purchase Reconciliation Score</p>
                <p class="text-2xl font-bold" :class="getComplianceTextClass(reconciliationScore.reconciliation_score)">
                  {{ reconciliationScore.reconciliation_score || 0 }}/100
                </p>
                <div class="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                  <div><p class="text-gray-500">Matched</p><p class="font-bold text-green-600">{{ formatNumber(reconciliationScore.matched_count) }}</p></div>
                  <div><p class="text-gray-500">Unmatched</p><p class="font-bold text-amber-600">{{ formatNumber(reconciliationScore.unmatched_count) }}</p></div>
                  <div><p class="text-gray-500">Mismatch</p><p class="font-bold text-red-600">{{ formatNumber(reconciliationScore.mismatch_count) }}</p></div>
                </div>
              </div>
            </div>

            <!-- Alerts -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div v-if="filingCompliance.gstr1?.status !== 'Filed' && filingCompliance.gstr1?.status !== 'Compliant'"
                class="p-4 bg-amber-50 border border-amber-200 rounded-lg">
                <div class="flex items-start gap-3">
                  <AlertTriangle class="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p class="font-medium text-amber-900">Overdue Filings</p>
                    <p class="text-sm text-amber-700 mt-1">
                      <span v-if="filingCompliance.gstr1?.status !== 'Filed' && filingCompliance.gstr1?.status !== 'Compliant'">GSTR-1 is pending. </span>
                      <span v-if="filingCompliance.gstr3b?.status !== 'Filed' && filingCompliance.gstr3b?.status !== 'Compliant'">GSTR-3B is pending.</span>
                    </p>
                  </div>
                </div>
              </div>

              <div v-if="(einvoiceStatus.coverage_pct || 0) < 80" class="p-4 bg-red-50 border border-red-200 rounded-lg">
                <div class="flex items-start gap-3">
                  <AlertTriangle class="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p class="font-medium text-red-900">Low e-Invoice Coverage</p>
                    <p class="text-sm text-red-700 mt-1">Coverage is {{ formatPercent(einvoiceStatus.coverage_pct) }}. Enable e-Invoicing for B2B invoices above the threshold.</p>
                  </div>
                </div>
              </div>

              <div v-if="(reconciliationScore.mismatch_count || 0) > 0" class="p-4 bg-red-50 border border-red-200 rounded-lg">
                <div class="flex items-start gap-3">
                  <AlertTriangle class="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p class="font-medium text-red-900">Reconciliation Mismatches</p>
                    <p class="text-sm text-red-700 mt-1">{{ formatNumber(reconciliationScore.mismatch_count) }} invoices have GST mismatches with GSTR-2A/2B.</p>
                  </div>
                </div>
              </div>

              <div v-if="(itcHealth.utilizable || 0) > 0 && (itcHealth.utilization_pct || 0) < 70"
                class="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <div class="flex items-start gap-3">
                  <CheckCircle class="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p class="font-medium text-blue-900">Unutilised ITC</p>
                    <p class="text-sm text-blue-700 mt-1">{{ formatCurrency(itcHealth.utilizable) }} of ITC is still utilisable. Review blocked/ineligible credits.</p>
                  </div>
                </div>
              </div>

              <div v-if="(filingCompliance.gstr1?.status === 'Filed' || filingCompliance.gstr1?.status === 'Compliant')
                      && (filingCompliance.gstr3b?.status === 'Filed' || filingCompliance.gstr3b?.status === 'Compliant')
                      && (einvoiceStatus.coverage_pct || 0) >= 80
                      && (reconciliationScore.mismatch_count || 0) === 0"
                class="p-4 bg-green-50 border border-green-200 rounded-lg">
                <div class="flex items-start gap-3">
                  <CheckCircle class="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p class="font-medium text-green-900">All Clear</p>
                    <p class="text-sm text-green-800">No major compliance issues detected.</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ── TDS ── -->
          <div v-if="activeTab === 'tds'" class="space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div class="bg-white rounded-xl shadow-sm border p-4">
                <p class="text-sm text-gray-500">TDS Payable</p>
                <p class="text-2xl font-bold text-orange-600">{{ formatCurrency(tdsSummary.total_payable) }}</p>
              </div>
              <div class="bg-white rounded-xl shadow-sm border p-4">
                <p class="text-sm text-gray-500">TDS Receivable</p>
                <p class="text-2xl font-bold text-blue-600">{{ formatCurrency(tdsSummary.receivable) }}</p>
              </div>
              <div class="bg-white rounded-xl shadow-sm border p-4">
                <p class="text-sm text-gray-500">Net Position</p>
                <p class="text-2xl font-bold" :class="(tdsSummary.net_position || 0) >= 0 ? 'text-green-600' : 'text-red-600'">
                  {{ formatCurrency(tdsSummary.net_position) }}
                </p>
              </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div class="bg-white rounded-xl shadow-sm border p-6">
                <h3 class="font-semibold text-gray-900 mb-4">TDS Payable by Section</h3>
                <div class="overflow-x-auto">
                  <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                      <tr>
                        <th class="px-4 py-2 text-left">Section</th>
                        <th class="px-4 py-2 text-left">Nature of Payment</th>
                        <th class="px-4 py-2 text-right">Rate</th>
                        <th class="px-4 py-2 text-right">TDS Amount</th>
                        <th class="px-4 py-2 text-right">% of Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="sec in (tdsSummary.payable_by_section || [])" :key="sec.section" class="border-b hover:bg-gray-50">
                        <td class="px-4 py-2 font-medium">
                          <span v-if="sec.section_code" class="px-2 py-0.5 rounded text-xs bg-purple-100 text-purple-700 mr-1">{{ sec.section_code }}</span>
                          <span v-else class="text-gray-600 text-xs">{{ sec.section }}</span>
                        </td>
                        <td class="px-4 py-2 text-gray-600">{{ sec.description || sec.section }}</td>
                        <td class="px-4 py-2 text-right text-gray-600">
                          {{ sec.rate_pct != null ? `${sec.rate_pct}%` : '—' }}
                        </td>
                        <td class="px-4 py-2 text-right">{{ formatCurrency(sec.amount) }}</td>
                        <td class="px-4 py-2 text-right">
                          <span class="px-2 py-1 rounded text-xs bg-purple-100 text-purple-700">
                            {{ formatPercent(tdsSummary.total_payable > 0 ? (sec.amount / tdsSummary.total_payable) * 100 : 0) }}
                          </span>
                        </td>
                      </tr>
                      <tr v-if="!(tdsSummary.payable_by_section || []).length">
                        <td colspan="5" class="px-4 py-6 text-center text-gray-500">No TDS data available</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div class="bg-white rounded-xl shadow-sm border p-6">
                <h3 class="font-semibold text-gray-900 mb-4">Top 5 TDS Sections</h3>
                <div class="h-72">
                  <BaseChart v-if="tdsBarOptions" :options="tdsBarOptions" />
                  <div v-else class="h-full flex items-center justify-center text-gray-500">No TDS section data available</div>
                </div>
              </div>
            </div>
          </div>

          <!-- ── Tax Planning ── -->
          <div v-if="activeTab === 'planning'" class="space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div class="bg-white rounded-xl shadow-sm border p-6">
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <TrendingUp class="w-5 h-5 text-blue-500" /> Effective Tax Rate Trend
                </h3>
                <div class="h-72">
                  <BaseChart v-if="effectiveRateTrendOptions" :options="effectiveRateTrendOptions" />
                  <div v-else class="h-full flex items-center justify-center text-gray-500">No trend data available</div>
                </div>
              </div>

              <div class="bg-white rounded-xl shadow-sm border p-6">
                <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <Activity class="w-5 h-5 text-green-500" /> GST Forecast (Next 3 Months)
                </h3>
                <div class="h-72">
                  <BaseChart v-if="taxForecastOptions" :options="taxForecastOptions" />
                  <div v-else class="h-full flex items-center justify-center text-gray-500">No forecast data available</div>
                </div>
                <p v-if="taxForecast.note" class="text-xs text-gray-500 mt-2">{{ taxForecast.note }}</p>
              </div>
            </div>

            <!-- YTD Summary -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div class="bg-white rounded-xl shadow-sm border p-4">
                <p class="text-sm text-gray-500">Total Revenue (YTD)</p>
                <p class="text-2xl font-bold text-gray-900">
                  {{ formatCurrency(gstSummary.reduce((s: number, d: any) => s + (d.total_revenue || 0), 0)) }}
                </p>
              </div>
              <div class="bg-white rounded-xl shadow-sm border p-4">
                <p class="text-sm text-gray-500">Total Output GST (YTD)</p>
                <p class="text-2xl font-bold text-red-600">
                  {{ formatCurrency(gstSummary.reduce((s: number, d: any) => s + (d.cgst || 0) + (d.sgst || 0) + (d.igst || 0), 0)) }}
                </p>
              </div>
              <div class="bg-white rounded-xl shadow-sm border p-4">
                <p class="text-sm text-gray-500">ITC Claimed (Tax Saved)</p>
                <p class="text-2xl font-bold text-green-600">{{ formatCurrency(itcHealth.claimed || 0) }}</p>
              </div>
            </div>

            <!-- Advance Tax Schedule -->
            <div class="bg-white rounded-xl shadow-sm border p-6">
              <div class="flex items-center justify-between mb-4">
                <h3 class="font-semibold text-gray-900">Advance Tax Schedule</h3>
                <span class="text-xs text-gray-500 bg-gray-100 rounded px-2 py-1">
                  Sec 207/208 · Mandatory if liability ≥ ₹10,000
                </span>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead class="bg-gray-50">
                    <tr>
                      <th class="px-4 py-2 text-left">Instalment</th>
                      <th class="px-4 py-2 text-left">Due Date</th>
                      <th class="px-4 py-2 text-right">Cumulative %</th>
                      <th class="px-4 py-2 text-left">Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="inst in advanceTaxSchedule" :key="inst.label" class="border-b hover:bg-gray-50">
                      <td class="px-4 py-2 font-medium">{{ inst.label }}</td>
                      <td class="px-4 py-2 font-medium text-blue-700">{{ inst.due_date }}</td>
                      <td class="px-4 py-2 text-right">
                        <span class="px-2 py-1 rounded text-xs bg-blue-100 text-blue-700">{{ inst.cumulative_pct }}%</span>
                      </td>
                      <td class="px-4 py-2 text-gray-500 text-xs">{{ inst.note }}</td>
                    </tr>
                    <tr v-if="!advanceTaxSchedule.length">
                      <td colspan="4" class="px-4 py-6 text-center text-gray-500">No schedule available</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p class="mt-3 text-xs text-gray-400">
                Late payment: 1 % p.m. interest (Sec 234B/234C). Presumptive taxpayers (44AD/44ADA): entire tax due 15 Mar only.
              </p>
            </div>
          </div>

          <!-- ── Settings ── -->
          <div v-if="activeTab === 'settings'" class="space-y-6">
            <div class="bg-white rounded-xl shadow-sm border p-6 max-w-xl">
              <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <Settings class="w-5 h-5 text-gray-500" /> Analysis Settings
              </h3>
              <div class="space-y-4">
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">Analysis Period</label>
                  <select v-model="dateFilter" class="w-full px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-blue-500">
                    <option v-for="r in dateRanges" :key="r.value" :value="r.value">{{ r.label }}</option>
                  </select>
                </div>
                <div class="pt-2">
                  <button @click="loadData(true)" :disabled="isRefreshing"
                    class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50">
                    <RefreshCcw v-if="!isRefreshing" class="w-4 h-4" />
                    <Loader2 v-else class="w-4 h-4 animate-spin" />
                    {{ isRefreshing ? 'Refreshing...' : 'Refresh Analysis' }}
                  </button>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>

    <DashboardChatButton dashboard-type="Tax" :dashboard-context="chatContext" @navigate-dashboard="handleDashboardRedirect" />
  </div>
</template>
