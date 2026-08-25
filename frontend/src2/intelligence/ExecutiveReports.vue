<template>
  <div class="executive-reports p-4">
    <!-- Header Section -->
    <div class="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between mb-6">
      <div>
        <h1 class="text-2xl font-semibold text-ink-gray-9">Executive Reports</h1>
        <p class="text-ink-gray-6 mt-1">Automated business intelligence reports for C-suite management</p>
      </div>
      <div class="flex flex-wrap gap-3">
        <Button
          variant="outline"
          @click="fetchReportsStatus"
          :loading="loadingStatus"
        >
          <template #prefix><RefreshCw class="w-4 h-4" /></template>
          Refresh
        </Button>
        <Button
          variant="solid"
          theme="gray"
          @click="generateReportModal = true"
        >
          <template #prefix><Plus class="w-4 h-4" /></template>
          Generate Report
        </Button>
      </div>
    </div>

    <!-- Status Cards -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <Card class="p-4">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-ink-gray-7">Daily Reports</h3>
            <p class="text-2xl font-bold text-ink-gray-9">{{ reportsStatus.daily_count || 0 }}</p>
            <p class="text-sm text-ink-gray-6">Last: {{ reportsStatus.last_daily || 'N/A' }}</p>
          </div>
          <Calendar class="w-8 h-8 text-ink-gray-5" />
        </div>
      </Card>

      <Card class="p-4">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-ink-gray-7">Weekly Reports</h3>
            <p class="text-2xl font-bold text-ink-gray-9">{{ reportsStatus.weekly_count || 0 }}</p>
            <p class="text-sm text-ink-gray-6">Last: {{ reportsStatus.last_weekly || 'N/A' }}</p>
          </div>
          <TrendingUp class="w-8 h-8 text-ink-gray-5" />
        </div>
      </Card>

      <Card class="p-4">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-ink-gray-7">Monthly Reports</h3>
            <p class="text-2xl font-bold text-ink-gray-9">{{ reportsStatus.monthly_count || 0 }}</p>
            <p class="text-sm text-ink-gray-6">Last: {{ reportsStatus.last_monthly || 'N/A' }}</p>
          </div>
          <BarChart3 class="w-8 h-8 text-ink-gray-5" />
        </div>
      </Card>
    </div>

    <!-- Scheduling Status -->
    <Card class="mb-6">
      <div class="p-4 border-b border-outline-gray-1">
        <h3 class="text-lg font-medium text-ink-gray-9 flex items-center">
          <Clock class="w-5 h-5 mr-2 text-ink-gray-5" />
          Automated Scheduling Status
        </h3>
      </div>
      <div class="p-4">
        <div v-if="schedulingStatus" class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="flex items-center justify-between p-3 bg-surface-gray-1 rounded-lg">
            <div>
              <p class="font-medium text-ink-gray-9">Daily Reports</p>
              <p class="text-sm text-ink-gray-7">{{ schedulingStatus.daily_reports || 'Not scheduled' }}</p>
            </div>
            <Badge
              theme="gray"
              variant="subtle"
              :label="schedulingStatus.daily_reports ? 'Active' : 'Not scheduled'"
              size="sm"
            />
          </div>
          <div class="flex items-center justify-between p-3 bg-surface-gray-1 rounded-lg">
            <div>
              <p class="font-medium text-ink-gray-9">Weekly Reports</p>
              <p class="text-sm text-ink-gray-7">{{ schedulingStatus.weekly_reports || 'Not scheduled' }}</p>
            </div>
            <Badge
              theme="gray"
              variant="subtle"
              :label="schedulingStatus.weekly_reports ? 'Active' : 'Not scheduled'"
              size="sm"
            />
          </div>
          <div class="flex items-center justify-between p-3 bg-surface-gray-1 rounded-lg">
            <div>
              <p class="font-medium text-ink-gray-9">Monthly Reports</p>
              <p class="text-sm text-ink-gray-7">{{ schedulingStatus.monthly_reports || 'Not scheduled' }}</p>
            </div>
            <Badge
              theme="gray"
              variant="subtle"
              :label="schedulingStatus.monthly_reports ? 'Active' : 'Not scheduled'"
              size="sm"
            />
          </div>
        </div>
        <div v-else class="text-center text-ink-gray-6">
          <LoadingIndicator class="w-5 h-5 mx-auto mb-2" />
          Loading scheduling status...
        </div>
      </div>
    </Card>

    <!-- Recent Reports Table -->
    <Card>
      <div class="p-4 border-b border-outline-gray-1">
        <h3 class="text-lg font-medium text-ink-gray-9 flex items-center">
          <FileText class="w-5 h-5 mr-2 text-ink-gray-5" />
          Recent Reports
        </h3>
      </div>
      <div class="p-0">
        <div v-if="loadingReports" class="text-center py-8">
          <LoadingIndicator class="w-6 h-6 mx-auto mb-2" />
          <p class="text-ink-gray-6">Loading reports...</p>
        </div>
        <div v-else-if="recentReports.length === 0" class="text-center py-8">
          <FileX class="w-12 h-12 mx-auto text-ink-gray-5 mb-4" />
          <p class="text-ink-gray-6">No reports generated yet</p>
          <p class="text-sm text-ink-gray-6">Generate your first executive report to get started</p>
        </div>
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-surface-gray-1">
              <tr>
                <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Report Type</th>
                <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Date</th>
                <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Generated</th>
                <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Status</th>
                <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody class="bg-surface-white divide-y divide-outline-gray-1">
              <tr v-for="report in recentReports" :key="report.id" class="hover:bg-surface-gray-1">
                <td class="px-4 py-3">
                  <div class="flex items-center">
                    <div class="flex items-center justify-center w-8 h-8 bg-surface-gray-2 text-ink-gray-5 rounded-full">
                      <component :is="getReportTypeIcon(report.report_type)" class="w-4 h-4" />
                    </div>
                    <span class="ml-2 font-medium text-ink-gray-9 capitalize">{{ report.report_type }}</span>
                  </div>
                </td>
                <td class="px-4 py-3 text-sm text-ink-gray-6">{{ formatReportDate(report.report_date) }}</td>
                <td class="px-4 py-3 text-sm text-ink-gray-6">{{ formatDateTime(report.created) }}</td>
                <td class="px-4 py-3">
                  <Badge
                    :theme="report.status === 'Failed' ? 'red' : 'gray'"
                    variant="subtle"
                    :label="report.status || 'Generated'"
                    size="sm"
                  />
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center space-x-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label="Preview report"
                      @click="previewReport(report)"
                      :loading="loadingPreview === report.id"
                    >
                      <Eye class="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label="Download report"
                      @click="downloadReport(report)"
                      :loading="loadingDownload === report.id"
                    >
                      <Download class="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label="Send report by email"
                      @click="sendReportEmail(report)"
                      :loading="loadingSend === report.id"
                    >
                      <Mail class="w-4 h-4" />
                    </Button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </Card>

    <!-- Generate Report Modal -->
    <Dialog
      v-model="generateReportModal"
      :options="{
        title: 'Generate Executive Report',
        actions: [
          { label: 'Cancel', variant: 'outline', onClick: () => generateReportModal = false },
          { label: generatingReport ? 'Generating...' : 'Generate Report', variant: 'solid', loading: generatingReport, disabled: generatingReport, onClick: generateReport }
        ]
      }"
    >
      <template #body-content>
        <p class="text-sm text-ink-gray-6 mb-4">Select the type of executive report to generate</p>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-ink-gray-7 mb-2">Report Type</label>
            <Select
              v-model="selectedReportType"
              :options="reportTypeOptions"
              class="w-full"
            />
          </div>

          <div class="flex items-center space-x-2">
            <input
              id="send-email"
              v-model="sendEmailAfterGeneration"
              type="checkbox"
              class="w-4 h-4 border-outline-gray-2 rounded focus-visible:ring-2 focus-visible:ring-outline-gray-3"
            >
            <label for="send-email" class="text-sm text-ink-gray-7">Send email after generation</label>
          </div>
        </div>
      </template>
    </Dialog>

    <!-- Preview Modal -->
    <Dialog
      v-model="previewModal"
      :options="{
        title: 'Report Preview',
        size: 'xl',
        actions: [
          { label: 'Close', variant: 'outline', onClick: () => previewModal = false }
        ]
      }"
    >
      <template #body-content>
        <p class="text-sm text-ink-gray-6 mb-4">Preview of {{ selectedReport?.report_type }} report data</p>
        <div v-if="previewData" class="space-y-4 max-h-96 overflow-y-auto">
          <div class="bg-surface-gray-1 p-4 rounded-lg">
            <h4 class="font-medium text-ink-gray-9 mb-2">Executive Summary</h4>
            <p class="text-ink-gray-7">{{ previewData.executive_summary }}</p>
          </div>

          <div v-if="previewData.key_metrics" class="bg-surface-gray-1 p-4 rounded-lg">
            <h4 class="font-medium text-ink-gray-9 mb-3">Key Metrics</h4>
            <div class="grid grid-cols-2 gap-3">
              <div v-for="(value, key) in previewData.key_metrics" :key="key" class="bg-surface-white p-2 rounded border border-outline-gray-1">
                <p class="text-sm text-ink-gray-6">{{ formatMetricKey(key) }}</p>
                <p class="font-semibold text-ink-gray-9">{{ formatMetricValue(value, key) }}</p>
              </div>
            </div>
          </div>

          <div v-if="previewData.alerts && previewData.alerts.length > 0" class="bg-surface-gray-1 p-4 rounded-lg">
            <h4 class="font-medium text-ink-gray-9 mb-3">Alerts and Exceptions</h4>
            <div v-for="alert in previewData.alerts" :key="alert.type" class="bg-surface-gray-2 p-2 rounded mb-2">
              <p class="font-medium text-ink-gray-8">{{ alert.type }} ({{ alert.priority }})</p>
              <p class="text-ink-gray-7 text-sm">{{ alert.message }}</p>
            </div>
          </div>

          <div class="bg-surface-gray-1 p-4 rounded-lg">
            <h4 class="font-medium text-ink-gray-9 mb-2">Data Availability</h4>
            <div class="flex flex-wrap gap-2">
              <Badge
                v-for="module in previewData.modules_with_data"
                :key="module"
                theme="gray"
                variant="subtle"
                :label="module"
                size="sm"
              />
            </div>
          </div>
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import {
  Calendar, TrendingUp, BarChart3, Clock, RefreshCw, Plus, FileText,
  Eye, Download, Mail, FileX
} from 'lucide-vue-next'
import { Button, Card, Dialog, Badge, Select, LoadingIndicator } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { createToast } from '../helpers/toasts'
import { formatMoney, formatPercent, formatCount } from '../utils/format'

// Reactive data
const recentReports = ref([])
const reportsStatus = ref({})
const schedulingStatus = ref(null)
const loadingReports = ref(false)
const loadingStatus = ref(false)
const loadingPreview = ref(null)
const loadingDownload = ref(null)
const loadingSend = ref(null)

// Modal states
const generateReportModal = ref(false)
const previewModal = ref(false)
const selectedReportType = ref('daily')
const sendEmailAfterGeneration = ref(true)
const generatingReport = ref(false)

// Preview data
const selectedReport = ref(null)
const previewData = ref(null)

const reportTypeOptions = [
  { label: 'Daily Executive Summary', value: 'daily' },
  { label: 'Weekly Business Review', value: 'weekly' },
  { label: 'Monthly Board Report', value: 'monthly' },
]

// Methods
const fetchRecentReports = async () => {
  loadingReports.value = true
  try {
    const result = await apiCall('insights.api.ml.get_recent_executive_reports', { limit: 20 })
    recentReports.value = result?.reports || []
    updateReportsStatus()
  } catch (error) {
    console.error('Error fetching recent reports:', error)
  } finally {
    loadingReports.value = false
  }
}

const fetchReportsStatus = async () => {
  loadingStatus.value = true
  try {
    schedulingStatus.value = await apiCall('insights.api.ml.get_executive_reports_status')
  } catch (error) {
    console.error('Error fetching reports status:', error)
  } finally {
    loadingStatus.value = false
  }
}

const updateReportsStatus = () => {
  const dailyReports = recentReports.value.filter(r => r.report_type === 'daily')
  const weeklyReports = recentReports.value.filter(r => r.report_type === 'weekly')
  const monthlyReports = recentReports.value.filter(r => r.report_type === 'monthly')

  reportsStatus.value = {
    daily_count: dailyReports.length,
    weekly_count: weeklyReports.length,
    monthly_count: monthlyReports.length,
    last_daily: dailyReports.length > 0 ? dailyReports[0].report_date : null,
    last_weekly: weeklyReports.length > 0 ? weeklyReports[0].report_date : null,
    last_monthly: monthlyReports.length > 0 ? monthlyReports[0].report_date : null
  }
}

const generateReport = async () => {
  generatingReport.value = true
  try {
    await apiCall('insights.api.ml.generate_executive_report', {
      report_type: selectedReportType.value
    })

    if (sendEmailAfterGeneration.value) {
      await apiCall('insights.api.ml.send_executive_report', {
        report_type: selectedReportType.value
      })
    }

    await fetchRecentReports()
    generateReportModal.value = false

    createToast({
      message: `${selectedReportType.value.charAt(0).toUpperCase() + selectedReportType.value.slice(1)} executive report generated successfully!`,
      variant: 'success',
    })
  } catch (error) {
    console.error('Error generating report:', error)
    createToast({
      message: error?.message || 'Error generating report. Please try again.',
      variant: 'error',
    })
  } finally {
    generatingReport.value = false
  }
}

const previewReport = async (report) => {
  loadingPreview.value = report.id
  try {
    const result = await apiCall('insights.api.ml.preview_executive_report_data', {
      report_type: report.report_type
    })

    selectedReport.value = report
    previewData.value = result
    previewModal.value = true
  } catch (error) {
    console.error('Error previewing report:', error)
    createToast({
      message: error?.message || 'Could not load report preview.',
      variant: 'error',
    })
  } finally {
    loadingPreview.value = null
  }
}

const downloadReport = async (report) => {
  loadingDownload.value = report.id
  try {
    const result = await apiCall('insights.api.ml.download_executive_report', {
      report_id: report.id
    })

    window.open(result.download_url, '_blank')
  } catch (error) {
    console.error('Error downloading report:', error)
    createToast({
      message: error?.message || 'Could not download report.',
      variant: 'error',
    })
  } finally {
    loadingDownload.value = null
  }
}

const sendReportEmail = async (report) => {
  loadingSend.value = report.id
  try {
    await apiCall('insights.api.ml.send_executive_report', {
      report_type: report.report_type
    })

    createToast({ message: 'Report sent successfully!', variant: 'success' })
  } catch (error) {
    console.error('Error sending report:', error)
    createToast({
      message: error?.message || 'Could not send report.',
      variant: 'error',
    })
  } finally {
    loadingSend.value = null
  }
}

// Utility functions
const getReportTypeIcon = (type) => {
  switch (type) {
    case 'daily': return Calendar
    case 'weekly': return TrendingUp
    case 'monthly': return BarChart3
    default: return FileText
  }
}

const formatReportDate = (dateStr) => {
  if (!dateStr) return 'N/A'
  return new Date(dateStr).toLocaleDateString()
}

const formatDateTime = (dateTimeStr) => {
  if (!dateTimeStr) return 'N/A'
  return new Date(dateTimeStr).toLocaleString()
}

const formatMetricKey = (key) => {
  return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

// Metric-name -> shape, so the same numeric field isn't formatted as if it
// were money for every key. The previous version applied `$`-prefixed
// M/K-compaction to every numeric value regardless of what it measured
// (lead counts, headcount, and 0-100 scores all rendered as fake currency),
// hardcoded `$` on a company that reports in a different currency, and used
// `>` instead of `>=` so a value of exactly 1,000,000 skipped compaction --
// the same three bugs `formatMoney` already exists to prevent.
const MONEY_METRICS = new Set(['revenue', 'cash_flow'])
const SCORE_METRICS = new Set(['business_health_score'])
const PERCENT_METRICS = new Set(['oee_score'])

const formatMetricValue = (value, key) => {
  if (typeof value !== 'number') return value
  if (MONEY_METRICS.has(key)) return formatMoney(value, previewData.value?.currency, { compact: true })
  if (PERCENT_METRICS.has(key)) return formatPercent(value)
  if (SCORE_METRICS.has(key)) return `${formatCount(value)}/100`
  return formatCount(value)
}

// Lifecycle
onMounted(() => {
  fetchRecentReports()
  fetchReportsStatus()
})
</script>

<style scoped>
.executive-reports {
  max-width: 1200px;
  margin: 0 auto;
}
</style>
