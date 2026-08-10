<template>
  <div class="space-y-6">

    <!-- CAPEX Overview Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <KpiCard
        label="Total Assets"
        :amount="data?.total_assets"
        :currency="getCurrency()"
        :loading="!data"
      />
      <KpiCard
        label="YTD CAPEX"
        :amount="data?.ytd_capex"
        :currency="getCurrency()"
        :loading="!data"
      />
      <KpiCard
        label="Annual Depreciation"
        :amount="data?.annual_depreciation"
        :currency="getCurrency()"
        :loading="!data"
      />
      <KpiCard
        label="Maintenance Costs"
        :amount="data?.maintenance_costs"
        :currency="getCurrency()"
        :loading="!data"
      />
    </div>

    <!-- Asset Categories and Age Distribution -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Assets by Category -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader variant="caption" title="Assets by Category" :level="3">
          <template #actions>
            <PieChartIcon class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <div v-if="data?.asset_categories?.length" class="space-y-4 mt-4">
          <div v-for="(category, index) in data.asset_categories" :key="index">
            <div class="flex justify-between mb-1">
              <span class="text-sm font-medium text-ink-gray-7">{{ category.name }}</span>
              <span class="text-sm text-ink-gray-6">
                {{ formatCurrency(category.value) }} ({{ category.percentage.toFixed(1) }}%)
              </span>
            </div>
            <!-- Non-text fill bar; CSS var for series colour; aria-label makes it accessible -->
            <div
              class="h-3 bg-surface-gray-3 rounded-full overflow-hidden"
              :aria-label="`${category.name}: ${category.percentage.toFixed(1)}%`"
              role="img"
            >
              <div
                class="h-full rounded-full transition-all motion-reduce:transition-none"
                :style="{ width: `${category.percentage}%`, backgroundColor: categoryColors[index % categoryColors.length] }"
              ></div>
            </div>
          </div>
        </div>
        <div v-else class="text-center py-8 text-ink-gray-6 mt-4">No asset data available</div>
      </div>

      <!-- Asset Age Distribution -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
        <SectionHeader variant="caption" title="Asset Age Distribution" :level="3">
          <template #actions>
            <Clock class="h-5 w-5 text-ink-gray-5" />
          </template>
        </SectionHeader>
        <div v-if="data?.age_distribution?.length" class="space-y-4 mt-4">
          <div v-for="(age, index) in data.age_distribution" :key="index">
            <div class="flex justify-between mb-1">
              <span class="text-sm font-medium text-ink-gray-7">{{ age.bucket }}</span>
              <span class="text-sm text-ink-gray-6">
                {{ age.count }} assets ({{ formatCurrency(age.value ?? 0) }})
              </span>
            </div>
            <div
              class="h-3 bg-surface-gray-3 rounded-full overflow-hidden"
              :aria-label="`${age.bucket}: ${age.percentage.toFixed(1)}%`"
              role="img"
            >
              <div
                :class="['h-full rounded-full transition-all motion-reduce:transition-none', ageBarFill(age.bucket)]"
                :style="{ width: `${age.percentage}%` }"
              ></div>
            </div>
          </div>
        </div>
        <div v-else class="text-center py-8 text-ink-gray-6 mt-4">No age distribution data</div>
      </div>
    </div>

    <!-- Assets Requiring Attention -->
    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <SectionHeader variant="caption" title="Assets Requiring Attention" :level="3">
        <template #actions>
          <AlertTriangle class="h-5 w-5 text-ink-gray-5" />
        </template>
      </SectionHeader>
      <div v-if="data?.attention_required?.length" class="overflow-x-auto mt-4">
        <table class="min-w-full divide-y divide-outline-gray-1">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Asset</th>
              <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Category</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Value</th>
              <th scope="col" class="px-4 py-3 text-center text-xs font-medium text-ink-gray-6 uppercase">Age (Years)</th>
              <th scope="col" class="px-4 py-3 text-center text-xs font-medium text-ink-gray-6 uppercase">Reason</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-1">
            <tr v-for="(asset, index) in data.attention_required" :key="index" class="hover:bg-surface-gray-1">
              <td class="px-4 py-3 text-sm font-medium text-ink-gray-9">{{ asset.name }}</td>
              <td class="px-4 py-3 text-sm text-ink-gray-6">{{ asset.category }}</td>
              <td class="px-4 py-3 text-sm text-right text-ink-gray-6">{{ formatCurrency(asset.value ?? 0) }}</td>
              <td class="px-4 py-3 text-sm text-center text-ink-gray-6">{{ asset.age_years }}</td>
              <td class="px-4 py-3 text-center">
                <!-- Reason badge: severity from reason text, all via status API -->
                <Badge
                  v-bind="reasonBadge(asset.reason)"
                  :label="asset.reason"
                  size="sm"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center py-8 text-ink-gray-6 mt-4">
        No assets requiring immediate attention
      </div>
    </div>

    <!-- Depreciation Forecast -->
    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <SectionHeader variant="caption" title="Depreciation Forecast (Next 5 Years)" :level="3">
        <template #actions>
          <TrendingDown class="h-5 w-5 text-ink-gray-5" />
        </template>
      </SectionHeader>
      <div v-if="data?.depreciation_forecast?.length" class="overflow-x-auto mt-4">
        <table class="min-w-full divide-y divide-outline-gray-1">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Year</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Depreciation</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Accumulated</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Net Book Value</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-1">
            <tr
              v-for="(forecast, index) in data.depreciation_forecast"
              :key="index"
              class="hover:bg-surface-gray-1"
            >
              <td class="px-4 py-3 text-sm font-medium text-ink-gray-9">{{ forecast.year }}</td>
              <td class="px-4 py-3 text-sm text-right text-ink-gray-6">{{ formatCurrency(forecast.depreciation ?? 0) }}</td>
              <td class="px-4 py-3 text-sm text-right text-ink-gray-6">{{ formatCurrency(forecast.accumulated ?? 0) }}</td>
              <td class="px-4 py-3 text-sm text-right font-medium text-ink-gray-9">{{ formatCurrency(forecast.net_book_value ?? 0) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center py-8 text-ink-gray-6 mt-4">No depreciation forecast available</div>
    </div>

    <!-- CAPEX Recommendations -->
    <div v-if="data?.recommendations?.length" class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <SectionHeader variant="caption" title="Capital Investment Recommendations" :level="3">
        <template #actions>
          <Lightbulb class="h-5 w-5 text-ink-gray-5" />
        </template>
      </SectionHeader>
      <div class="space-y-3 mt-4">
        <div
          v-for="(rec, index) in data.recommendations"
          :key="index"
          class="p-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1"
        >
          <div class="flex items-start gap-3">
            <Lightbulb class="h-5 w-5 text-ink-gray-5 flex-shrink-0 mt-0.5" />
            <div>
              <p class="font-medium text-ink-gray-9">{{ rec.title }}</p>
              <p class="text-sm text-ink-gray-6 mt-1">{{ rec.description }}</p>
              <p v-if="rec.estimated_cost" class="text-sm text-ink-gray-7 mt-2">
                Estimated Cost: {{ formatCurrency(rec.estimated_cost ?? 0) }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { NO_VALUE } from '../../utils/format'
import {
  Building2,
  TrendingUp,
  TrendingDown,
  Calculator,
  Wrench,
  Clock,
  PieChart as PieChartIcon,
  AlertTriangle,
  Lightbulb,
} from 'lucide-vue-next'
import { type Ref } from 'vue'
import { useCurrency } from '../../composables/useCurrency'
import { Badge } from 'frappe-ui'
import { scoreSeverity, severityBadge, type BadgeSpec } from '../../utils/status'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import type { CapitalPlanningData, AssetCategoryRow, AssetAgeRow, DepreciationForecastRow } from './types'

// Tab-local: template binds year/depreciation/accumulated/net_book_value;
// extends Partial<DepreciationForecastRow> to include the shared period/amount fields.
interface LocalDepreciationRow extends Partial<DepreciationForecastRow> {
  year?: string | number
  depreciation?: number
  accumulated?: number
  net_book_value?: number
}

// Tab-local: attention_required items bind name/category/age_years beyond the
// asset_name/reason/value guaranteed by the shared type.
interface AttentionAsset {
  name?: string
  asset_name?: string
  category?: string
  value?: number
  age_years?: number
  reason: string
}

interface Props {
  data?: Omit<CapitalPlanningData, 'depreciation_forecast' | 'attention_required' | 'recommendations'> & {
    depreciation_forecast?: LocalDepreciationRow[]
    attention_required?: AttentionAsset[]
    recommendations?: Array<{ title: string; description: string; priority?: string; estimated_cost?: number }>
  }
}

const props = defineProps<Props>()

const currency = useCurrency()
const getCurrency = () => currency.value

const formatCurrency = (value: number): string => {
  // Absent is not zero: this returned `${getCurrency()} 0`, reporting zero money
  // for a field the server never sent. Notation is unchanged -- exact
  // `en-KE` grouping is a deliberate choice for this surface, and
  // switching it is a separate product decision.
  if (value === null || value === undefined) return NO_VALUE
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: getCurrency(),
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

// CSS var-based series colours for category bars (non-text fills, >=3:1 on white).
const categoryColors = [
  'var(--surface-blue-3)',
  'var(--surface-green-3)',
  'var(--surface-amber-3)',
  'var(--surface-red-5)',
  'var(--surface-gray-4)',
  'var(--surface-red-6)',
  'var(--surface-blue-3)',
  'var(--surface-green-3)',
]

// Asset age: older assets are higher-severity (need replacement sooner)
function ageBarFill(range: string): string {
  if (range.includes('0-2')) return 'bg-surface-green-3'
  if (range.includes('2-5') || range.includes('3-5')) return 'bg-surface-blue-3'
  if (range.includes('5-10') || range.includes('5-7')) return 'bg-surface-amber-3'
  return 'bg-surface-red-5'
}

// Reason badge: use severity to pick theme/variant; label comes from the asset's reason text
function reasonBadge(reason: string): BadgeSpec {
  const r = reason.toLowerCase()
  if (r.includes('fully depreciated')) return severityBadge('high')
  if (r.includes('maintenance') || r.includes('repair')) return severityBadge('medium')
  if (r.includes('replace')) return severityBadge('medium')
  return { ...severityBadge('none'), label: reason }
}
</script>
