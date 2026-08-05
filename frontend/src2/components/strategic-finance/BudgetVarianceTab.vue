<template>
  <div class="budget-variance-tab">

    <!-- Controls Bar -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-lg font-semibold text-ink-gray-9">Budget Variance Analysis</h2>
        <p class="text-sm text-ink-gray-6 mt-0.5">
          Budget variance analysis and forecasting insights
        </p>
      </div>
      <div class="flex items-center space-x-3">
        <Button @click="reload" :loading="refreshing" variant="subtle" theme="gray" size="sm">
          <RotateCcw class="w-4 h-4 mr-2" />
          Refresh
        </Button>
        <Button @click="exportReport" variant="subtle" theme="gray" size="sm">
          <Download class="w-4 h-4 mr-2" />
          Export
        </Button>
      </div>
    </div>

    <!-- Loading State: skeleton cards rather than page-blocking spinner -->
    <div v-if="loading && !hasData" class="space-y-6">
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard v-for="n in 4" :key="n" label="Loading..." value="" :loading="true" />
      </div>
      <SkeletonBlock class="h-48 w-full rounded-lg" />
      <SkeletonBlock class="h-64 w-full rounded-lg" />
    </div>

    <!-- Permission Error State -->
    <div v-else-if="isPermissionError" class="text-center py-12">
      <Lock class="w-12 h-12 text-ink-gray-5 mx-auto mb-4" />
      <h3 class="text-lg font-medium text-ink-gray-9 mb-2">Access Restricted</h3>
      <p class="text-ink-gray-6">You do not have permission to view budget variance data.</p>
    </div>

    <!-- Error State with Retry -->
    <div v-else-if="error" class="text-center py-12">
      <AlertCircle class="w-12 h-12 text-ink-gray-5 mx-auto mb-4" />
      <h3 class="text-lg font-medium text-ink-gray-9 mb-2">Unable to Load Data</h3>
      <p class="text-ink-gray-6 mb-4">{{ error }}</p>
      <Button @click="retry" variant="outline" theme="gray">
        <RefreshCw class="w-4 h-4 mr-2" />
        Try Again
      </Button>
    </div>

    <!-- Empty State -->
    <div v-else-if="!hasData" class="text-center py-12">
      <BarChart class="w-12 h-12 text-ink-gray-5 mx-auto mb-4" />
      <p class="text-ink-gray-6">No budget variance data available</p>
    </div>

    <!-- Main Content -->
    <div v-else class="space-y-6">

      <!-- Alerts Section: Badge replaces border-l-4 accent -->
      <div
        v-if="budgetData?.alerts && budgetData.alerts.length > 0"
        class="p-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1"
      >
        <div class="flex items-center gap-2 mb-3">
          <AlertTriangle class="w-5 h-5 text-ink-gray-5 flex-shrink-0" />
          <span class="text-sm font-medium text-ink-gray-9">Budget Alerts</span>
          <Badge label="Attention" variant="subtle" theme="red" size="sm" />
        </div>
        <div class="space-y-1">
          <div
            v-for="alert in (budgetData?.alerts || []).slice(0, showAllAlerts ? undefined : 3)"
            :key="alert.title"
            class="text-sm text-ink-gray-7"
          >
            <span class="font-medium">{{ alert.title }}:</span> {{ alert.description }}
          </div>
        </div>
        <Button
          v-if="budgetData?.alerts.length > 3"
          @click="showAllAlerts = !showAllAlerts"
          variant="ghost"
          theme="gray"
          size="sm"
          class="mt-2"
        >
          {{ showAllAlerts ? 'Show Less' : `View ${budgetData.alerts.length - 3} More Alerts` }}
        </Button>
      </div>

      <!-- Summary Cards -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">

        <!-- Overall Variance -->
        <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-ink-gray-6">Overall Variance</p>
              <p class="text-2xl font-bold mt-1" :class="varianceInk(budgetData?.summary?.variance_percentage || 0)">
                {{ formatPercentage(budgetData?.summary?.variance_percentage || 0) }}
              </p>
              <p class="text-xs text-ink-gray-6 mt-1">
                {{ formatCurrency(budgetData?.summary?.total_variance || 0) }}
              </p>
            </div>
            <TrendingUp class="w-6 h-6 text-ink-gray-5" />
          </div>
          <div class="mt-3 flex items-center text-xs gap-2">
            <span class="text-ink-gray-6">Status:</span>
            <Badge
              v-bind="statusBadge(budgetData?.summary?.status)"
              :label="statusBadge(budgetData?.summary?.status).label"
              size="sm"
            />
          </div>
        </div>

        <!-- Budget Utilization -->
        <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-ink-gray-6">Budget Utilization</p>
              <p class="text-2xl font-bold mt-1 text-ink-gray-9">
                {{ formatPercentage(budgetData?.summary?.budget_utilization || 0) }}
              </p>
              <p class="text-xs text-ink-gray-6 mt-1">
                {{ formatCurrency(budgetData?.summary?.total_actual || 0) }} / {{ formatCurrency(budgetData?.summary?.total_budget || 0) }}
              </p>
            </div>
            <PieChart class="w-6 h-6 text-ink-gray-5" />
          </div>
          <div class="mt-3 bg-surface-gray-3 rounded-full h-2">
            <div
              class="bg-surface-blue-3 h-2 rounded-full transition-all motion-reduce:transition-none duration-500"
              :style="{ width: `${Math.min(budgetData?.summary?.budget_utilization || 0, 100)}%` }"
            ></div>
          </div>
        </div>

        <!-- Forecast Accuracy -->
        <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-ink-gray-6">Forecast Accuracy</p>
              <p class="text-2xl font-bold mt-1 text-ink-gray-9">
                {{ formatPercentage(budgetData?.forecast_accuracy?.overall_accuracy || 0) }}
              </p>
              <p class="text-xs text-ink-gray-6 mt-1">
                Grade: {{ budgetData?.forecast_accuracy?.accuracy_grade || 'N/A' }}
              </p>
            </div>
            <Target class="w-6 h-6 text-ink-gray-5" />
          </div>
          <div class="mt-3 flex items-center text-xs gap-2">
            <span class="text-ink-gray-6">Trend:</span>
            <span class="text-ink-gray-7 capitalize">{{ budgetData?.forecast_accuracy?.accuracy_trend || 'stable' }}</span>
          </div>
        </div>

        <!-- Alert Count -->
        <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-ink-gray-6">Active Alerts</p>
              <p class="text-2xl font-bold mt-1 text-ink-gray-9">
                {{ budgetData?.alerts?.length || 0 }}
              </p>
              <p class="text-xs text-ink-gray-6 mt-1">
                {{ getHighPriorityAlerts.length }} high priority
              </p>
            </div>
            <AlertCircle class="w-6 h-6 text-ink-gray-5" />
          </div>
        </div>
      </div>

      <!-- Charts Section -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Variance Trend Chart -->
        <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
          <SectionHeader variant="caption" title="Variance Trends" :level="3" class="mb-4" />
          <!--
            Was a placeholder that rendered a BarChart icon plus "Variance trend
            visualization" in the has-data branch and a near-identical icon plus
            "No trend data available" in the empty branch. Eighteen months of
            real data therefore looked the same as none, which is worse than an
            honest empty state: it hid that the data had arrived.

            Budget and Actual as two lines rather than the variance as one: the
            gap between the lines IS the variance, and showing both keeps the
            reference visible, so a reader can see whether a gap came from
            overspend or from a budget that was never realistic.
          -->
          <IntelligenceChart
            v-if="monthlyVarianceChart"
            class="h-48"
            :config="monthlyVarianceChart"
          />
          <div v-else class="h-48 flex items-center justify-center text-ink-gray-6">
            <div class="text-center">
              <BarChart class="w-8 h-8 mx-auto mb-2 text-ink-gray-5" />
              <p class="text-sm">No monthly variance recorded for this fiscal year yet</p>
              <p class="text-xs mt-1">Rows appear once budgets and actuals both post to a month.</p>
            </div>
          </div>
        </div>

        <!-- Department Performance -->
        <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
          <SectionHeader variant="caption" title="Department Variance" :level="3" class="mb-4" />
          <div v-if="budgetData?.departmental_analysis && budgetData.departmental_analysis.length > 0" class="space-y-3">
            <div
              v-for="dept in (budgetData?.departmental_analysis || []).slice(0, 5)"
              :key="dept.department"
              class="flex items-center justify-between"
            >
              <div class="flex-1">
                <p class="text-sm font-medium text-ink-gray-9">{{ dept.department }}</p>
                <p class="text-xs text-ink-gray-6">{{ formatCurrency(dept.variance) }}</p>
              </div>
              <div class="flex items-center space-x-2">
                <div class="w-20">
                  <!-- Over budget (variance >= 0) = bad = surface-red-5; under = surface-green-3 -->
                  <div class="bg-surface-gray-3 rounded-full h-2">
                    <div
                      class="h-2 rounded-full"
                      :class="dept.variance >= 0 ? 'bg-surface-red-5' : 'bg-surface-green-3'"
                      :style="{ width: `${Math.min(Math.abs(dept.variance_percentage || 0), 100)}%` }"
                    ></div>
                  </div>
                </div>
                <span class="text-sm font-medium" :class="varianceInk(dept.variance_percentage || 0)">
                  {{ formatPercentage(dept.variance_percentage || 0) }}
                </span>
              </div>
            </div>
          </div>
          <div v-else class="h-32 flex items-center justify-center text-ink-gray-6">
            <div class="text-center">
              <Building class="w-8 h-8 mx-auto mb-2 text-ink-gray-5" />
              <p class="text-sm">No department data available</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Detailed Analysis: frappe-ui Tabs replaces hand-rolled nav -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
        <Tabs v-model="activeDetailTabIndex" :tabs="detailTabs" />

        <div class="mt-6">
          <!-- Department Analysis -->
          <div v-if="activeDetailTab === 'departments'" class="space-y-4">
            <div v-if="budgetData?.departmental_analysis && budgetData.departmental_analysis.length > 0">
              <div class="grid grid-cols-1 gap-4">
                <div
                  v-for="dept in budgetData.departmental_analysis"
                  :key="dept.department"
                  class="border border-outline-gray-1 rounded-lg p-4"
                >
                  <div class="flex items-center justify-between mb-3">
                    <h4 class="font-medium text-ink-gray-9">{{ dept.department }}</h4>
                    <Badge
                      v-bind="statusBadge(dept.status)"
                      :label="statusBadge(dept.status).label"
                      size="sm"
                    />
                  </div>
                  <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                      <p class="text-ink-gray-6">Budget</p>
                      <p class="font-medium text-ink-gray-9">{{ formatCurrency(dept.budget) }}</p>
                    </div>
                    <div>
                      <p class="text-ink-gray-6">Actual</p>
                      <p class="font-medium text-ink-gray-9">{{ formatCurrency(dept.actual) }}</p>
                    </div>
                    <div>
                      <p class="text-ink-gray-6">Variance</p>
                      <p class="font-medium" :class="varianceInk(dept.variance_percentage)">
                        {{ formatCurrency(dept.variance) }}
                      </p>
                    </div>
                    <div>
                      <p class="text-ink-gray-6">Trend</p>
                      <p class="font-medium capitalize text-ink-gray-8">{{ dept.trend }}</p>
                    </div>
                  </div>
                  <div v-if="dept.key_accounts && dept.key_accounts.length > 0" class="mt-4">
                    <p class="text-sm font-medium text-ink-gray-7 mb-2">Key Contributing Accounts</p>
                    <div class="space-y-1">
                      <div
                        v-for="account in (dept.key_accounts || []).slice(0, 3)"
                        :key="account.account"
                        class="flex justify-between text-xs text-ink-gray-6"
                      >
                        <span>{{ account.account }}</span>
                        <span>{{ formatCurrency(account.actual_amount) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-8 text-ink-gray-6">
              <Building class="w-12 h-12 mx-auto mb-4 text-ink-gray-5" />
              <p>No department variance data available</p>
            </div>
          </div>

          <!-- Account Analysis -->
          <div v-if="activeDetailTab === 'accounts'" class="space-y-4">
            <div v-if="budgetData?.account_analysis && budgetData.account_analysis.length > 0">
              <div class="overflow-x-auto border border-outline-gray-1 rounded-lg">
                <table class="min-w-full divide-y divide-outline-gray-1">
                  <thead class="bg-surface-gray-1">
                    <tr>
                      <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Account</th>
                      <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Type</th>
                      <th scope="col" class="px-6 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Budget</th>
                      <th scope="col" class="px-6 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Actual</th>
                      <th scope="col" class="px-6 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Variance</th>
                      <th scope="col" class="px-6 py-3 text-center text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Status</th>
                    </tr>
                  </thead>
                  <tbody class="bg-surface-white divide-y divide-outline-gray-1">
                    <tr
                      v-for="account in (budgetData?.account_analysis || []).slice(0, 10)"
                      :key="account.account"
                      class="hover:bg-surface-gray-1"
                    >
                      <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-ink-gray-9">{{ account.account }}</td>
                      <td class="px-6 py-4 whitespace-nowrap text-sm text-ink-gray-6">{{ account.account_type }}</td>
                      <td class="px-6 py-4 whitespace-nowrap text-sm text-ink-gray-9 text-right">{{ formatCurrency(account.budget) }}</td>
                      <td class="px-6 py-4 whitespace-nowrap text-sm text-ink-gray-9 text-right">{{ formatCurrency(account.actual) }}</td>
                      <td class="px-6 py-4 whitespace-nowrap text-sm text-right font-medium" :class="varianceInk(account.variance_percentage)">
                        {{ formatCurrency(account.variance) }}<br>
                        <span class="text-xs">{{ formatPercentage(account.variance_percentage) }}</span>
                      </td>
                      <td class="px-6 py-4 whitespace-nowrap text-center">
                        <Badge
                          v-bind="statusBadge(account.status)"
                          :label="statusBadge(account.status).label"
                          size="sm"
                        />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div v-else class="text-center py-8 text-ink-gray-6">
              <Receipt class="w-12 h-12 mx-auto mb-4 text-ink-gray-5" />
              <p>No account variance data available</p>
            </div>
          </div>

          <!-- Recommendations -->
          <div v-if="activeDetailTab === 'recommendations'" class="space-y-4">
            <div v-if="budgetData?.recommendations && budgetData.recommendations.length > 0">
              <div class="grid grid-cols-1 gap-4">
                <div
                  v-for="rec in budgetData.recommendations"
                  :key="rec.title"
                  class="border border-outline-gray-1 rounded-lg p-5"
                >
                  <div class="flex items-start justify-between">
                    <div class="flex-1">
                      <div class="flex items-center space-x-3 mb-2">
                        <h4 class="font-medium text-ink-gray-9">{{ rec.title }}</h4>
                        <Badge
                          v-bind="priorityBadge(rec.priority)"
                          :label="priorityBadge(rec.priority).label"
                          size="sm"
                        />
                        <Badge :label="rec.category" variant="subtle" theme="gray" size="sm" />
                      </div>
                      <p class="text-sm text-ink-gray-6 mb-3">{{ rec.description }}</p>
                      <div class="grid grid-cols-2 gap-4 mb-4 text-sm">
                        <div>
                          <span class="text-ink-gray-6">Impact:</span>
                          <span class="ml-2 font-medium text-ink-gray-8">{{ rec.impact }}</span>
                        </div>
                        <div>
                          <span class="text-ink-gray-6">Effort:</span>
                          <span class="ml-2 font-medium text-ink-gray-8">{{ rec.effort }}</span>
                        </div>
                      </div>
                      <div v-if="rec.actions && rec.actions.length > 0">
                        <p class="text-sm font-medium text-ink-gray-7 mb-2">Action Items:</p>
                        <ul class="list-disc list-inside text-sm text-ink-gray-6 space-y-1">
                          <li v-for="action in rec.actions" :key="action">{{ action }}</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-8 text-ink-gray-6">
              <Lightbulb class="w-12 h-12 mx-auto mb-4 text-ink-gray-5" />
              <p>No recommendations available</p>
              <p class="text-sm mt-2">Budget performance appears to be optimal</p>
            </div>
          </div>

          <!-- Performance Metrics -->
          <div v-if="activeDetailTab === 'performance'" class="space-y-6">
            <div v-if="budgetData?.performance_metrics" class="grid grid-cols-1 md:grid-cols-3 gap-6">
              <!-- Overall Score -->
              <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
                <h4 class="font-medium text-ink-gray-9 mb-4">Overall Budget Score</h4>
                <div class="text-center">
                  <div class="text-3xl font-bold text-ink-gray-9">
                    {{ Math.round(budgetData.performance_metrics.overall_score || 0) }}
                  </div>
                  <div class="text-sm text-ink-gray-6 mt-1">out of 100</div>
                  <div class="mt-4 bg-surface-gray-3 rounded-full h-3">
                    <div
                      class="bg-surface-blue-3 h-3 rounded-full transition-all motion-reduce:transition-none duration-500"
                      :style="{ width: `${budgetData.performance_metrics.overall_score || 0}%` }"
                    ></div>
                  </div>
                </div>
              </div>

              <!-- Budget Accuracy -->
              <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
                <h4 class="font-medium text-ink-gray-9 mb-4">Budget Accuracy</h4>
                <div class="space-y-3">
                  <div class="flex justify-between">
                    <span class="text-sm text-ink-gray-6">Accuracy</span>
                    <span class="font-medium text-ink-gray-9">
                      {{ formatPercentage(budgetData.performance_metrics.budget_accuracy?.accuracy_percentage || 0) }}
                    </span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-sm text-ink-gray-6">Grade</span>
                    <span class="font-medium text-ink-gray-9">{{ budgetData.performance_metrics.budget_accuracy?.grade || 'N/A' }}</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-sm text-ink-gray-6">vs Benchmark</span>
                    <span class="font-medium text-ink-gray-8">
                      {{ budgetData.performance_metrics.budget_accuracy?.performance || 'unknown' }}
                    </span>
                  </div>
                </div>
              </div>

              <!-- Variance Control -->
              <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-5">
                <h4 class="font-medium text-ink-gray-9 mb-4">Variance Control</h4>
                <div class="space-y-3">
                  <div class="flex justify-between">
                    <span class="text-sm text-ink-gray-6">Control Score</span>
                    <span class="font-medium text-ink-gray-9">{{ Math.round(budgetData.performance_metrics.variance_control?.control_score || 0) }}</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-sm text-ink-gray-6">Avg Variance</span>
                    <span class="font-medium text-ink-gray-9">{{ formatPercentage(budgetData.performance_metrics.variance_control?.average_variance || 0) }}</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-sm text-ink-gray-6">Control Level</span>
                    <span class="font-medium capitalize text-ink-gray-8">{{ budgetData.performance_metrics.variance_control?.control_level || 'unknown' }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Button, Badge, Tabs } from 'frappe-ui'
import {
  RotateCcw,
  Download,
  AlertCircle,
  RefreshCw,
  AlertTriangle,
  TrendingUp,
  PieChart,
  Target,
  BarChart,
  Building,
  Receipt,
  Lightbulb,
  Lock,
} from 'lucide-vue-next'
import { severityBadge } from '../../utils/status'
import { useIntelligenceDashboard } from '../../intelligence/composables/useIntelligenceDashboard'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SkeletonBlock from '../../intelligence/components/SkeletonBlock.vue'
import IntelligenceChart from '../../intelligence/components/IntelligenceChart.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import { themeColor } from '../../utils/chartTheme'
import { formatMoney, NO_VALUE } from '../../utils/format'
import { formatPeriod } from '../financial/format'
import { computed as vueComputed, inject, isRef } from 'vue'

/**
 * Server currency, same injection the sibling planning tabs use. This tab used
 * to hardcode "KES" in its own formatter, which lied on any company reporting
 * in another currency.
 */
const _currency = inject('currency', 'KES')
const currency = vueComputed(() => (isRef(_currency) ? _currency.value : _currency) || 'KES')

const emptyParams = ref({})
const {
  data: budgetData,
  loading,
  refreshing,
  error,
  isPermissionError,
  hasData,
  reload,
  retry,
} = useIntelligenceDashboard({
  url: '/api/method/insights.api.ml.get_budget_variance_overview',
  params: emptyParams,
  cache: 'budget-variance-overview',
})

/**
 * Budget vs Actual by month, or `null` when there is nothing to plot.
 *
 * Returns null rather than an empty config so the template can pick a real
 * empty state; an axis chart handed an empty series renders bare gridlines,
 * which reads as "loaded, and the answer is nothing".
 */
const monthlyVarianceChart = vueComputed(() => {
  const rows = budgetData.value?.variance_trends?.monthly_variances
  if (!Array.isArray(rows) || rows.length === 0) return null
  return {
    title: '',
    data: rows.map((m) => ({
      month: formatPeriod(String(m.month ?? '')),
      Budget: Number(m.budget) || 0,
      Actual: Number(m.actual) || 0,
    })),
    xAxis: { key: 'month', type: 'category' },
    yAxis: { title: currency.value },
    series: [
      // Neither series is a status, so both take neutral data colours. Budget is
      // the subdued reference and Actual the prominent measured line.
      // Not `--app-accent` for Actual: it resolves to the same #0070cc as
      // `--app-info-fill` (chartTheme.ts:31,33), which would have drawn two
      // indistinguishable lines.
      { name: 'Budget', type: 'line', color: themeColor('--app-muted-fill') },
      { name: 'Actual', type: 'line', color: themeColor('--app-info-fill') },
    ],
  }
})

const showAllAlerts = ref(false)

// Detail tabs: numeric index for Tabs, string key for v-if
const detailTabDefs = [
  { label: 'Departments', key: 'departments' },
  { label: 'Accounts', key: 'accounts' },
  { label: 'Recommendations', key: 'recommendations' },
  { label: 'Performance', key: 'performance' },
]
const detailTabs = detailTabDefs.map(t => ({ label: t.label }))
const activeDetailTabIndex = ref(0)
const activeDetailTab = computed(() => detailTabDefs[activeDetailTabIndex.value]?.key || 'departments')

const getHighPriorityAlerts = computed(() =>
  budgetData.value?.alerts?.filter(alert => alert.severity === 'high') || []
)

const exportReport = () => {
  const reportData = {
    timestamp: new Date().toISOString(),
    summary: budgetData.value?.summary,
    alerts: budgetData.value?.alerts,
    recommendations: budgetData.value?.recommendations,
  }
  const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `budget_variance_report_${new Date().toISOString().split('T')[0]}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// Formatting. Delegates to the shared formatter rather than re-deriving it: the
// previous local version hardcoded "KES" and tested `value >= 1_000_000`
// without `Math.abs`, so a negative variance (the common case when actuals come
// in under budget) matched no branch and printed raw and ungrouped. That is the
// exact defect `utils/format.ts` was created to remove.
const formatCurrency = (value) => formatMoney(value, currency.value, { compact: true })

const formatPercentage = (value) => {
  if (value === null || value === undefined) return NO_VALUE
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`
}

// Variance colour: high absolute variance is bad (red); low is neutral.
// Replaces getVarianceColor which used green/yellow/red raw classes.
const varianceInk = (percentage) => {
  if (Math.abs(percentage) <= 5) return 'text-ink-gray-9'
  if (Math.abs(percentage) <= 15) return 'text-ink-gray-7'
  return 'text-ink-red-4'
}

// Status badge: domain labels preserved, Espresso-safe themes/variants
const statusBadge = (status) => {
  const map = {
    excellent: { theme: 'gray', variant: 'subtle', label: 'Excellent' },
    good: { theme: 'gray', variant: 'subtle', label: 'Good' },
    acceptable: { theme: 'gray', variant: 'outline', label: 'Acceptable' },
    poor: { theme: 'gray', variant: 'outline', label: 'Poor' },
    critical: { theme: 'red', variant: 'subtle', label: 'Critical' },
  }
  return map[status] || { theme: 'gray', variant: 'subtle', label: (status || '').replace('_', ' ') || 'Unknown' }
}

// Priority badge
const priorityBadge = (priority) => {
  switch (priority) {
    case 'high': return { theme: 'red', variant: 'subtle', label: 'High' }
    case 'medium': return { theme: 'gray', variant: 'outline', label: 'Medium' }
    case 'low': return { theme: 'gray', variant: 'subtle', label: 'Low' }
    default: return { theme: 'gray', variant: 'subtle', label: priority || 'Unknown' }
  }
}
</script>
