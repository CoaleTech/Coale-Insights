<template>
  <div class="space-y-6">
    <!-- CAPEX Overview -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
            <Building2 class="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Total Assets</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.total_assets || 0) }}
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
            <TrendingUp class="h-5 w-5 text-green-600" />
          </div>
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">YTD CAPEX</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.ytd_capex || 0) }}
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-amber-100 dark:bg-amber-900/30 rounded-lg">
            <Calculator class="h-5 w-5 text-amber-600" />
          </div>
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Annual Depreciation</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.annual_depreciation || 0) }}
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
            <Wrench class="h-5 w-5 text-purple-600" />
          </div>
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Maintenance Costs</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">
              {{ formatCurrency(data?.maintenance_costs || 0) }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Asset Categories Breakdown -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <PieChartIcon class="h-5 w-5 text-gray-500" />
          Assets by Category
        </h3>
        <div v-if="data?.asset_categories?.length" class="space-y-4">
          <div v-for="(category, index) in data.asset_categories" :key="index">
            <div class="flex justify-between mb-1">
              <span class="text-sm font-medium text-gray-700 dark:text-gray-300">{{ category.name }}</span>
              <span class="text-sm text-gray-600 dark:text-gray-400">
                {{ formatCurrency(category.value) }} ({{ category.percentage.toFixed(1) }}%)
              </span>
            </div>
            <div class="h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div 
                class="h-full rounded-full transition-all" 
                :style="{ width: `${category.percentage}%`, backgroundColor: getCategoryColor(index) }"
              ></div>
            </div>
          </div>
        </div>
        <div v-else class="text-center py-8 text-gray-500">
          No asset data available
        </div>
      </div>

      <!-- Asset Age Analysis -->
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Clock class="h-5 w-5 text-gray-500" />
          Asset Age Distribution
        </h3>
        <div v-if="data?.age_distribution?.length" class="space-y-4">
          <div v-for="(age, index) in data.age_distribution" :key="index">
            <div class="flex justify-between mb-1">
              <span class="text-sm font-medium text-gray-700 dark:text-gray-300">{{ age.range }}</span>
              <span class="text-sm text-gray-600 dark:text-gray-400">
                {{ age.count }} assets ({{ formatCurrency(age.value) }})
              </span>
            </div>
            <div class="h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div 
                :class="['h-full rounded-full transition-all', getAgeColor(age.range)]"
                :style="{ width: `${age.percentage}%` }"
              ></div>
            </div>
          </div>
        </div>
        <div v-else class="text-center py-8 text-gray-500">
          No age distribution data
        </div>
      </div>
    </div>

    <!-- Assets Requiring Attention -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <AlertTriangle class="h-5 w-5 text-amber-500" />
        Assets Requiring Attention
      </h3>
      <div v-if="data?.attention_required?.length" class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead class="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Asset</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Category</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Value</th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Age (Years)</th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Reason</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr v-for="(asset, index) in data.attention_required" :key="index" class="hover:bg-gray-50 dark:hover:bg-gray-700">
              <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">{{ asset.name }}</td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ asset.category }}</td>
              <td class="px-4 py-3 text-sm text-right text-gray-600 dark:text-gray-400">
                {{ formatCurrency(asset.value) }}
              </td>
              <td class="px-4 py-3 text-sm text-center text-gray-600 dark:text-gray-400">
                {{ asset.age_years }}
              </td>
              <td class="px-4 py-3 text-center">
                <span :class="getReasonBadgeClass(asset.reason)">
                  {{ asset.reason }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center py-8 text-gray-500">
        No assets requiring immediate attention
      </div>
    </div>

    <!-- Depreciation Forecast -->
    <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <TrendingDown class="h-5 w-5 text-gray-500" />
        Depreciation Forecast (Next 5 Years)
      </h3>
      <div v-if="data?.depreciation_forecast?.length" class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead class="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Year</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Depreciation</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Accumulated</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Net Book Value</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr v-for="(forecast, index) in data.depreciation_forecast" :key="index" class="hover:bg-gray-50 dark:hover:bg-gray-700">
              <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">{{ forecast.year }}</td>
              <td class="px-4 py-3 text-sm text-right text-gray-600 dark:text-gray-400">
                {{ formatCurrency(forecast.depreciation) }}
              </td>
              <td class="px-4 py-3 text-sm text-right text-gray-600 dark:text-gray-400">
                {{ formatCurrency(forecast.accumulated) }}
              </td>
              <td class="px-4 py-3 text-sm text-right font-medium text-gray-900 dark:text-white">
                {{ formatCurrency(forecast.net_book_value) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center py-8 text-gray-500">
        No depreciation forecast available
      </div>
    </div>

    <!-- CAPEX Recommendations -->
    <div v-if="data?.recommendations?.length" class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <Lightbulb class="h-5 w-5 text-amber-500" />
        Capital Investment Recommendations
      </h3>
      <div class="space-y-3">
        <div 
          v-for="(rec, index) in data.recommendations" 
          :key="index"
          class="p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border-l-4 border-blue-500"
        >
          <div class="flex items-start gap-3">
            <Lightbulb class="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
            <div>
              <p class="font-medium text-gray-900 dark:text-white">{{ rec.title }}</p>
              <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">{{ rec.description }}</p>
              <p v-if="rec.estimated_cost" class="text-sm text-blue-600 dark:text-blue-400 mt-2">
                Estimated Cost: {{ formatCurrency(rec.estimated_cost) }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { 
  Building2, 
  TrendingUp, 
  TrendingDown,
  Calculator, 
  Wrench, 
  Clock,
  PieChart as PieChartIcon,
  AlertTriangle,
  Lightbulb
} from 'lucide-vue-next'
import { inject } from 'vue'

interface Props {
  data: any
}

const props = defineProps<Props>()

const _currency = inject('currency', 'KES')
const getCurrency = () => (typeof _currency === 'string' ? _currency : (_currency as any)?.value) || 'KES'

const formatCurrency = (value: number) => {
  if (value === null || value === undefined) return `${getCurrency()} 0`
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: getCurrency(),
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const categoryColors = [
  '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', 
  '#EC4899', '#06B6D4', '#84CC16'
]

const getCategoryColor = (index: number) => {
  return categoryColors[index % categoryColors.length]
}

const getAgeColor = (range: string) => {
  if (range.includes('0-2')) return 'bg-green-500'
  if (range.includes('2-5') || range.includes('3-5')) return 'bg-blue-500'
  if (range.includes('5-10') || range.includes('5-7')) return 'bg-amber-500'
  return 'bg-red-500'
}

const getReasonBadgeClass = (reason: string) => {
  const base = 'px-2 py-1 text-xs font-medium rounded-full'
  if (reason.toLowerCase().includes('fully depreciated')) {
    return `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`
  }
  if (reason.toLowerCase().includes('maintenance') || reason.toLowerCase().includes('repair')) {
    return `${base} bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400`
  }
  if (reason.toLowerCase().includes('replace')) {
    return `${base} bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400`
  }
  return `${base} bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300`
}
</script>
