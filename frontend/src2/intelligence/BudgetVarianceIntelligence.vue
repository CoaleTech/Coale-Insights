<template>
  <div class="budget-variance-intelligence">
    <!-- Header Section -->
    <div class="mb-6">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">Budget Variance Intelligence</h1>
          <p class="text-sm text-gray-600 mt-1">
            Comprehensive budget variance analysis and forecasting insights
          </p>
        </div>
        <div class="flex items-center space-x-3">
          <Button @click="refreshData" :loading="loading">
            <RotateCcw class="w-4 h-4 mr-2" />
            Refresh
          </Button>
          <Button @click="exportReport">
            <Download class="w-4 h-4 mr-2" />
            Export Report
          </Button>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <div class="text-center">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
        <p class="text-gray-600">Loading budget variance data...</p>
      </div>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="text-center py-12">
      <AlertCircle class="w-12 h-12 text-red-500 mx-auto mb-4" />
      <h3 class="text-lg font-medium text-gray-900 mb-2">Unable to Load Data</h3>
      <p class="text-gray-600 mb-4">{{ error }}</p>
      <Button @click="refreshData" variant="outline">
        <RefreshCw class="w-4 h-4 mr-2" />
        Try Again
      </Button>
    </div>

    <!-- Main Content -->
    <div v-else class="space-y-6">
      <!-- Alerts Section -->
      <div v-if="data.alerts && data.alerts.length > 0" class="bg-red-50 border-l-4 border-red-400 p-4 rounded-r-lg">
        <div class="flex items-start">
          <AlertTriangle class="w-5 h-5 text-red-400 mt-0.5 mr-3 flex-shrink-0" />
          <div class="flex-1">
            <h3 class="text-sm font-medium text-red-800">Budget Alerts</h3>
            <div class="mt-2 space-y-1">
              <div v-for="alert in data.alerts.slice(0, 3)" :key="alert.title" 
                   class="text-sm text-red-700">
                <span class="font-medium">{{ alert.title }}:</span> {{ alert.description }}
              </div>
            </div>
            <Button v-if="data.alerts.length > 3" @click="showAllAlerts = !showAllAlerts" 
                    variant="ghost" class="text-xs text-red-600 mt-2 p-0">
              {{ showAllAlerts ? 'Show Less' : `View ${data.alerts.length - 3} More Alerts` }}
            </Button>
          </div>
        </div>
      </div>

      <!-- Summary Cards -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <!-- Overall Variance Card -->
        <Card class="p-6">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-gray-600">Overall Variance</p>
              <p class="text-2xl font-bold mt-1" :class="getVarianceColor(data.summary?.variance_percentage || 0)">
                {{ formatPercentage(data.summary?.variance_percentage || 0) }}
              </p>
              <p class="text-xs text-gray-500 mt-1">
                {{ formatCurrency(data.summary?.total_variance || 0) }}
              </p>
            </div>
            <div class="p-3 bg-blue-100 rounded-lg">
              <TrendingUp class="w-6 h-6 text-blue-600" />
            </div>
          </div>
          <div class="mt-4">
            <div class="flex items-center text-xs">
              <span class="text-gray-500">Status:</span>
              <Badge :variant="getStatusVariant(data.summary?.status)" class="ml-2 text-xs">
                {{ data.summary?.status?.replace('_', ' ') }}
              </Badge>
            </div>
          </div>
        </Card>

        <!-- Budget Utilization Card -->
        <Card class="p-6">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-gray-600">Budget Utilization</p>
              <p class="text-2xl font-bold mt-1 text-purple-600">
                {{ formatPercentage(data.summary?.budget_utilization || 0) }}
              </p>
              <p class="text-xs text-gray-500 mt-1">
                {{ formatCurrency(data.summary?.total_actual || 0) }} / {{ formatCurrency(data.summary?.total_budget || 0) }}
              </p>
            </div>
            <div class="p-3 bg-purple-100 rounded-lg">
              <PieChart class="w-6 h-6 text-purple-600" />
            </div>
          </div>
          <div class="mt-4 bg-gray-200 rounded-full h-2">
            <div 
              class="bg-purple-600 h-2 rounded-full transition-all duration-500"
              :style="{ width: `${Math.min(data.summary?.budget_utilization || 0, 100)}%` }"
            ></div>
          </div>
        </Card>

        <!-- Forecast Accuracy Card -->
        <Card class="p-6">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-gray-600">Forecast Accuracy</p>
              <p class="text-2xl font-bold mt-1 text-green-600">
                {{ formatPercentage(data.forecast_accuracy?.overall_accuracy || 0) }}
              </p>
              <p class="text-xs text-gray-500 mt-1">
                Grade: {{ data.forecast_accuracy?.accuracy_grade || 'N/A' }}
              </p>
            </div>
            <div class="p-3 bg-green-100 rounded-lg">
              <Target class="w-6 h-6 text-green-600" />
            </div>
          </div>
          <div class="mt-4">
            <div class="flex items-center text-xs">
              <span class="text-gray-500">Trend:</span>
              <span class="ml-2 capitalize">{{ data.forecast_accuracy?.accuracy_trend || 'stable' }}</span>
            </div>
          </div>
        </Card>

        <!-- Alert Count Card -->
        <Card class="p-6">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-gray-600">Active Alerts</p>
              <p class="text-2xl font-bold mt-1 text-red-600">
                {{ data.alerts?.length || 0 }}
              </p>
              <p class="text-xs text-gray-500 mt-1">
                {{ getHighPriorityAlerts.length }} high priority
              </p>
            </div>
            <div class="p-3 bg-red-100 rounded-lg">
              <AlertCircle class="w-6 h-6 text-red-600" />
            </div>
          </div>
          <div class="mt-4" v-if="data.alerts && data.alerts.length > 0">
            <div class="flex space-x-1">
              <div class="w-2 h-2 rounded-full bg-red-500"></div>
              <div class="w-2 h-2 rounded-full bg-yellow-500"></div>
              <div class="w-2 h-2 rounded-full bg-gray-300"></div>
            </div>
          </div>
        </Card>
      </div>

      <!-- Charts Section -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Variance Trend Chart -->
        <Card class="p-6">
          <h3 class="text-lg font-semibold mb-4">Variance Trends</h3>
          <div v-if="data.variance_trends?.monthly_variances" class="h-64">
            <div class="text-center py-8 text-gray-500">
              <BarChart class="w-8 h-8 mx-auto mb-2" />
              <p class="text-sm">Variance trend visualization</p>
              <p class="text-xs mt-1">{{ data.variance_trends.monthly_variances.length }} months of data</p>
            </div>
          </div>
          <div v-else class="h-64 flex items-center justify-center text-gray-500">
            <div class="text-center">
              <BarChart class="w-8 h-8 mx-auto mb-2" />
              <p class="text-sm">No trend data available</p>
            </div>
          </div>
        </Card>

        <!-- Department Performance Chart -->
        <Card class="p-6">
          <h3 class="text-lg font-semibold mb-4">Department Variance</h3>
          <div v-if="data.departmental_analysis && data.departmental_analysis.length > 0" class="space-y-3">
            <div v-for="dept in data.departmental_analysis.slice(0, 5)" :key="dept.department" 
                 class="flex items-center justify-between">
              <div class="flex-1">
                <p class="text-sm font-medium text-gray-900">{{ dept.department }}</p>
                <p class="text-xs text-gray-500">{{ formatCurrency(dept.variance) }}</p>
              </div>
              <div class="flex items-center space-x-2">
                <div class="w-20">
                  <div class="bg-gray-200 rounded-full h-2">
                    <div 
                      class="h-2 rounded-full"
                      :class="dept.variance >= 0 ? 'bg-red-500' : 'bg-green-500'"
                      :style="{ width: `${Math.min(Math.abs(dept.variance_percentage || 0), 100)}%` }"
                    ></div>
                  </div>
                </div>
                <span class="text-sm font-medium" :class="getVarianceColor(dept.variance_percentage || 0)">
                  {{ formatPercentage(dept.variance_percentage || 0) }}
                </span>
              </div>
            </div>
          </div>
          <div v-else class="h-32 flex items-center justify-center text-gray-500">
            <div class="text-center">
              <Building class="w-8 h-8 mx-auto mb-2" />
              <p class="text-sm">No department data available</p>
            </div>
          </div>
        </Card>
      </div>

      <!-- Detailed Analysis Tabs -->
      <Card class="p-6">
        <div class="border-b border-gray-200">
          <nav class="flex space-x-8">
            <button
              v-for="tab in tabs"
              :key="tab.key"
              @click="activeTab = tab.key"
              :class="[
                'py-2 px-1 border-b-2 font-medium text-sm',
                activeTab === tab.key
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              ]"
            >
              {{ tab.label }}
            </button>
          </nav>
        </div>

        <div class="mt-6">
          <!-- Department Analysis Tab -->
          <div v-if="activeTab === 'departments'" class="space-y-4">
            <div v-if="data.departmental_analysis && data.departmental_analysis.length > 0">
              <div class="grid grid-cols-1 gap-4">
                <div v-for="dept in data.departmental_analysis" :key="dept.department" 
                     class="border border-gray-200 rounded-lg p-4 hover:border-gray-300 transition-colors">
                  <div class="flex items-center justify-between mb-3">
                    <h4 class="font-medium text-gray-900">{{ dept.department }}</h4>
                    <Badge :variant="getStatusVariant(dept.status)">{{ dept.status }}</Badge>
                  </div>
                  
                  <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                      <p class="text-gray-500">Budget</p>
                      <p class="font-medium">{{ formatCurrency(dept.budget) }}</p>
                    </div>
                    <div>
                      <p class="text-gray-500">Actual</p>
                      <p class="font-medium">{{ formatCurrency(dept.actual) }}</p>
                    </div>
                    <div>
                      <p class="text-gray-500">Variance</p>
                      <p class="font-medium" :class="getVarianceColor(dept.variance_percentage)">
                        {{ formatCurrency(dept.variance) }}
                      </p>
                    </div>
                    <div>
                      <p class="text-gray-500">Trend</p>
                      <p class="font-medium capitalize">{{ dept.trend }}</p>
                    </div>
                  </div>

                  <!-- Key Accounts -->
                  <div v-if="dept.key_accounts && dept.key_accounts.length > 0" class="mt-4">
                    <p class="text-sm font-medium text-gray-700 mb-2">Key Contributing Accounts</p>
                    <div class="space-y-1">
                      <div v-for="account in dept.key_accounts.slice(0, 3)" :key="account.account" 
                           class="flex justify-between text-xs text-gray-600">
                        <span>{{ account.account }}</span>
                        <span>{{ formatCurrency(account.actual_amount) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <Building class="w-12 h-12 mx-auto mb-4" />
              <p>No department variance data available</p>
            </div>
          </div>

          <!-- Account Analysis Tab -->
          <div v-if="activeTab === 'accounts'" class="space-y-4">
            <div v-if="data.account_analysis && data.account_analysis.length > 0">
              <div class="overflow-hidden shadow ring-1 ring-black ring-opacity-5 rounded-lg">
                <table class="min-w-full divide-y divide-gray-300">
                  <thead class="bg-gray-50">
                    <tr>
                      <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Account
                      </th>
                      <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Type
                      </th>
                      <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Budget
                      </th>
                      <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Actual
                      </th>
                      <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Variance
                      </th>
                      <th class="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody class="bg-white divide-y divide-gray-200">
                    <tr v-for="account in data.account_analysis.slice(0, 10)" :key="account.account"
                        class="hover:bg-gray-50">
                      <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {{ account.account }}
                      </td>
                      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {{ account.account_type }}
                      </td>
                      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                        {{ formatCurrency(account.budget) }}
                      </td>
                      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                        {{ formatCurrency(account.actual) }}
                      </td>
                      <td class="px-6 py-4 whitespace-nowrap text-sm text-right font-medium"
                          :class="getVarianceColor(account.variance_percentage)">
                        {{ formatCurrency(account.variance) }}
                        <br>
                        <span class="text-xs">{{ formatPercentage(account.variance_percentage) }}</span>
                      </td>
                      <td class="px-6 py-4 whitespace-nowrap text-center">
                        <Badge :variant="getStatusVariant(account.status)">
                          {{ account.status }}
                        </Badge>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <Receipt class="w-12 h-12 mx-auto mb-4" />
              <p>No account variance data available</p>
            </div>
          </div>

          <!-- Recommendations Tab -->
          <div v-if="activeTab === 'recommendations'" class="space-y-4">
            <div v-if="data.recommendations && data.recommendations.length > 0">
              <div class="grid grid-cols-1 gap-4">
                <div v-for="rec in data.recommendations" :key="rec.title" 
                     class="border border-gray-200 rounded-lg p-6">
                  <div class="flex items-start justify-between">
                    <div class="flex-1">
                      <div class="flex items-center space-x-3 mb-2">
                        <h4 class="font-medium text-gray-900">{{ rec.title }}</h4>
                        <Badge :variant="getPriorityVariant(rec.priority)">{{ rec.priority }}</Badge>
                        <Badge variant="outline" class="text-xs">{{ rec.category }}</Badge>
                      </div>
                      <p class="text-sm text-gray-600 mb-3">{{ rec.description }}</p>
                      
                      <div class="grid grid-cols-2 gap-4 mb-4 text-sm">
                        <div>
                          <span class="text-gray-500">Impact:</span>
                          <span class="ml-2 font-medium">{{ rec.impact }}</span>
                        </div>
                        <div>
                          <span class="text-gray-500">Effort:</span>
                          <span class="ml-2 font-medium">{{ rec.effort }}</span>
                        </div>
                      </div>

                      <div v-if="rec.actions && rec.actions.length > 0">
                        <p class="text-sm font-medium text-gray-700 mb-2">Action Items:</p>
                        <ul class="list-disc list-inside text-sm text-gray-600 space-y-1">
                          <li v-for="action in rec.actions" :key="action">{{ action }}</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              <Lightbulb class="w-12 h-12 mx-auto mb-4" />
              <p>No recommendations available</p>
              <p class="text-sm mt-2">Budget performance appears to be optimal</p>
            </div>
          </div>

          <!-- Performance Metrics Tab -->
          <div v-if="activeTab === 'performance'" class="space-y-6">
            <div v-if="data.performance_metrics" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <!-- Overall Score -->
              <Card class="p-6">
                <h4 class="font-medium text-gray-900 mb-4">Overall Budget Score</h4>
                <div class="text-center">
                  <div class="text-3xl font-bold text-blue-600">
                    {{ Math.round(data.performance_metrics.overall_score || 0) }}
                  </div>
                  <div class="text-sm text-gray-500 mt-1">out of 100</div>
                  <div class="mt-4 bg-gray-200 rounded-full h-3">
                    <div 
                      class="bg-blue-600 h-3 rounded-full transition-all duration-500"
                      :style="{ width: `${data.performance_metrics.overall_score || 0}%` }"
                    ></div>
                  </div>
                </div>
              </Card>

              <!-- Budget Accuracy -->
              <Card class="p-6">
                <h4 class="font-medium text-gray-900 mb-4">Budget Accuracy</h4>
                <div class="space-y-3">
                  <div class="flex justify-between">
                    <span class="text-sm text-gray-600">Accuracy</span>
                    <span class="font-medium">
                      {{ formatPercentage(data.performance_metrics.budget_accuracy?.accuracy_percentage || 0) }}
                    </span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-sm text-gray-600">Grade</span>
                    <span class="font-medium">{{ data.performance_metrics.budget_accuracy?.grade || 'N/A' }}</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-sm text-gray-600">vs Benchmark</span>
                    <span class="font-medium">
                      {{ data.performance_metrics.budget_accuracy?.performance || 'unknown' }}
                    </span>
                  </div>
                </div>
              </Card>

              <!-- Variance Control -->
              <Card class="p-6">
                <h4 class="font-medium text-gray-900 mb-4">Variance Control</h4>
                <div class="space-y-3">
                  <div class="flex justify-between">
                    <span class="text-sm text-gray-600">Control Score</span>
                    <span class="font-medium">{{ Math.round(data.performance_metrics.variance_control?.control_score || 0) }}</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-sm text-gray-600">Avg Variance</span>
                    <span class="font-medium">{{ formatPercentage(data.performance_metrics.variance_control?.average_variance || 0) }}</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-sm text-gray-600">Control Level</span>
                    <span class="font-medium capitalize">{{ data.performance_metrics.variance_control?.control_level || 'unknown' }}</span>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { 
  Button, 
  Card, 
  Badge 
} from 'frappe-ui'
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
  Lightbulb 
} from 'lucide-vue-next'

// Reactive state
const data = ref({})
const loading = ref(false)
const error = ref(null)
const showAllAlerts = ref(false)
const activeTab = ref('departments')
const baseCurrency = ref('KES')

// Tab configuration
const tabs = [
  { key: 'departments', label: 'Departments' },
  { key: 'accounts', label: 'Accounts' },
  { key: 'recommendations', label: 'Recommendations' },
  { key: 'performance', label: 'Performance' }
]

// API endpoint
const apiEndpoint = '/api/method/insights.api.ml.get_budget_variance_overview'

// Computed properties
const getHighPriorityAlerts = computed(() => {
  return data.value.alerts?.filter(alert => alert.severity === 'high') || []
})

// Data fetching
const fetchData = async () => {
  loading.value = true
  error.value = null
  
  try {
    const response = await fetch(apiEndpoint, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': window.csrf_token || ''
      }
    })
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    
    const result = await response.json()
    
    if (result.message) {
      data.value = result.message
      if (result.message.base_currency) {
        baseCurrency.value = result.message.base_currency
      }
    } else {
      throw new Error('Invalid response format')
    }
  } catch (err) {
    console.error('Error fetching budget variance data:', err)
    error.value = err.message || 'Failed to load budget variance data'
  } finally {
    loading.value = false
  }
}

// Event handlers
const refreshData = () => {
  fetchData()
}

const exportReport = () => {
  // Implementation for exporting reports
  const reportData = {
    timestamp: new Date().toISOString(),
    summary: data.value.summary,
    alerts: data.value.alerts,
    recommendations: data.value.recommendations
  }
  
  const blob = new Blob([JSON.stringify(reportData, null, 2)], { 
    type: 'application/json' 
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `budget_variance_report_${new Date().getTime()}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// Utility functions
const formatCurrency = (value) => {
  if (value === null || value === undefined) return `${baseCurrency.value} 0`
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: baseCurrency.value,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const formatPercentage = (value) => {
  if (value === null || value === undefined) return '0.0%'
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`
}

const getVarianceColor = (percentage) => {
  if (Math.abs(percentage) <= 5) return 'text-green-600'
  if (Math.abs(percentage) <= 15) return 'text-yellow-600'
  return 'text-red-600'
}

const getStatusVariant = (status) => {
  const variants = {
    'excellent': 'green',
    'good': 'blue', 
    'acceptable': 'yellow',
    'poor': 'orange',
    'critical': 'red'
  }
  return variants[status] || 'gray'
}

const getPriorityVariant = (priority) => {
  const variants = {
    'high': 'red',
    'medium': 'yellow',
    'low': 'blue'
  }
  return variants[priority] || 'gray'
}

// Initialize component
onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.budget-variance-intelligence {
  max-width: 1400px;
  margin: 0 auto;
  padding: 1.5rem;
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Custom scrollbar for tables */
.overflow-hidden::-webkit-scrollbar {
  height: 6px;
}

.overflow-hidden::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.overflow-hidden::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 3px;
}

.overflow-hidden::-webkit-scrollbar-thumb:hover {
  background: #555;
}
</style>