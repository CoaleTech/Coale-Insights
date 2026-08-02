<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <div class="p-2 bg-surface-gray-2 rounded-lg">
          <GitCompare class="h-5 w-5 text-ink-gray-5" />
        </div>
        <div>
          <h4 class="font-semibold text-ink-gray-9">Variance Review</h4>
          <p class="text-xs text-ink-gray-6">Actual vs Forecast Analysis</p>
        </div>
      </div>
      <Button
        variant="ghost"
        aria-label="Toggle variance panel"
        :aria-expanded="String(expanded)"
        @click="expanded = !expanded"
      >
        <ChevronDown
          :class="[
            'h-5 w-5 text-ink-gray-5 transition-transform motion-reduce:transition-none',
            expanded ? 'rotate-180' : '',
          ]"
        />
      </Button>
    </div>

    <div v-if="expanded">
      <!-- No Data State -->
      <div v-if="!variance?.has_variance_data" class="p-6 text-center bg-surface-gray-1 rounded-lg">
        <FileQuestion class="h-10 w-10 mx-auto text-ink-gray-5 mb-2" />
        <p class="text-sm text-ink-gray-7">No variance data available yet</p>
        <p class="text-xs text-ink-gray-6">Variance data will appear after weeks with actual vs forecast comparisons</p>
      </div>

      <template v-else>
        <!-- Accuracy Summary -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div class="p-3 bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="flex items-center gap-2 mb-1">
              <Target class="h-4 w-4 text-ink-gray-5" />
              <span class="text-xs text-ink-gray-6">Inflow Accuracy</span>
            </div>
            <p
              class="text-xl font-bold"
              :class="(variance.summary?.inflow_forecast_accuracy ?? 0) < 75 ? 'text-ink-red-4' : 'text-ink-gray-9'"
            >
              {{ variance.summary?.inflow_forecast_accuracy || 0 }}%
            </p>
          </div>

          <div class="p-3 bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="flex items-center gap-2 mb-1">
              <Target class="h-4 w-4 text-ink-gray-5" />
              <span class="text-xs text-ink-gray-6">Outflow Accuracy</span>
            </div>
            <p
              class="text-xl font-bold"
              :class="(variance.summary?.outflow_forecast_accuracy ?? 0) < 75 ? 'text-ink-red-4' : 'text-ink-gray-9'"
            >
              {{ variance.summary?.outflow_forecast_accuracy || 0 }}%
            </p>
          </div>

          <div class="p-3 bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="flex items-center gap-2 mb-1">
              <TrendingUp class="h-4 w-4 text-ink-gray-5" />
              <span class="text-xs text-ink-gray-6">Net Variance</span>
            </div>
            <p
              class="text-xl font-bold"
              :class="deltaInk(variance.summary?.total_net_variance)"
            >
              {{ (variance.summary?.total_net_variance || 0) >= 0 ? '+' : '' }}{{ formatCompact(variance.summary?.total_net_variance || 0) }}
            </p>
          </div>

          <div class="p-3 bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="flex items-center gap-2 mb-1">
              <Calendar class="h-4 w-4 text-ink-gray-5" />
              <span class="text-xs text-ink-gray-6">Weeks Analyzed</span>
            </div>
            <p class="text-xl font-bold text-ink-gray-9">
              {{ variance.weeks_analyzed || 0 }}
            </p>
          </div>
        </div>

        <!-- Insights -->
        <div v-if="variance.insights?.length" class="space-y-2">
          <h5 class="font-medium text-sm text-ink-gray-8 flex items-center gap-2">
            <Sparkles class="h-4 w-4 text-ink-gray-5" />
            Key Insights
          </h5>
          <div class="space-y-2">
            <div
              v-for="(insight, idx) in variance.insights"
              :key="idx"
              class="p-3 rounded-lg border border-outline-gray-1 bg-surface-white"
            >
              <div class="flex items-center gap-2 mb-1">
                <component
                  :is="insight.type === 'positive' ? TrendingUp : TrendingDown"
                  class="h-4 w-4 text-ink-gray-5"
                />
                <span class="font-medium text-sm text-ink-gray-9">{{ insight.title }}</span>
                <Badge
                  :label="insight.category"
                  theme="gray"
                  variant="subtle"
                  size="sm"
                />
              </div>
              <p class="text-sm text-ink-gray-7">{{ insight.description }}</p>
              <p class="text-xs text-ink-gray-6 mt-1 flex items-center gap-1">
                <Lightbulb class="h-3 w-3 text-ink-gray-5" />
                {{ insight.recommendation }}
              </p>
            </div>
          </div>
        </div>

        <!-- Weekly Variance Table -->
        <div v-if="variance.weekly_details?.length" class="overflow-x-auto">
          <h5 class="font-medium text-sm text-ink-gray-8 mb-2 flex items-center gap-2">
            <Table2 class="h-4 w-4 text-ink-gray-5" />
            Weekly Variance Details
          </h5>
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-outline-gray-1">
                <th scope="col" class="px-3 py-2 text-left text-ink-gray-6 font-medium">Week</th>
                <th scope="col" class="px-3 py-2 text-right text-ink-gray-6 font-medium">Inflow Var</th>
                <th scope="col" class="px-3 py-2 text-right text-ink-gray-6 font-medium">%</th>
                <th scope="col" class="px-3 py-2 text-right text-ink-gray-6 font-medium">Outflow Var</th>
                <th scope="col" class="px-3 py-2 text-right text-ink-gray-6 font-medium">%</th>
                <th scope="col" class="px-3 py-2 text-right text-ink-gray-6 font-medium">Net Var</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="week in variance.weekly_details"
                :key="week.week_number"
                class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
              >
                <th scope="row" class="px-3 py-2 font-medium text-ink-gray-9 text-left">
                  {{ week.week_label }}
                </th>
                <td class="px-3 py-2 text-right" :class="deltaInk(week.inflow_variance)">
                  {{ week.inflow_variance >= 0 ? '+' : '' }}{{ formatCompact(week.inflow_variance) }}
                </td>
                <td class="px-3 py-2 text-right text-xs" :class="deltaInk(week.inflow_variance_pct)">
                  {{ week.inflow_variance_pct >= 0 ? '+' : '' }}{{ week.inflow_variance_pct }}%
                </td>
                <!-- outflow variance: negative actual variance is good (spent less than forecast) -->
                <td class="px-3 py-2 text-right" :class="deltaInk(-week.outflow_variance)">
                  {{ week.outflow_variance >= 0 ? '+' : '' }}{{ formatCompact(week.outflow_variance) }}
                </td>
                <td class="px-3 py-2 text-right text-xs" :class="deltaInk(-week.outflow_variance_pct)">
                  {{ week.outflow_variance_pct >= 0 ? '+' : '' }}{{ week.outflow_variance_pct }}%
                </td>
                <td class="px-3 py-2 text-right font-medium" :class="deltaInk(week.net_variance)">
                  {{ week.net_variance >= 0 ? '+' : '' }}{{ formatCompact(week.net_variance) }}
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="bg-surface-gray-1 font-medium">
                <th scope="row" class="px-3 py-2 text-ink-gray-8 text-left">Total</th>
                <td class="px-3 py-2 text-right" :class="deltaInk(variance.summary?.total_inflow_variance)">
                  {{ (variance.summary?.total_inflow_variance || 0) >= 0 ? '+' : '' }}{{ formatCompact(variance.summary?.total_inflow_variance || 0) }}
                </td>
                <td class="px-3 py-2"></td>
                <td class="px-3 py-2 text-right" :class="deltaInk(-(variance.summary?.total_outflow_variance || 0))">
                  {{ (variance.summary?.total_outflow_variance || 0) >= 0 ? '+' : '' }}{{ formatCompact(variance.summary?.total_outflow_variance || 0) }}
                </td>
                <td class="px-3 py-2"></td>
                <td class="px-3 py-2 text-right" :class="deltaInk(variance.summary?.total_net_variance)">
                  {{ (variance.summary?.total_net_variance || 0) >= 0 ? '+' : '' }}{{ formatCompact(variance.summary?.total_net_variance || 0) }}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        <!-- Visual Variance Chart -->
        <div class="p-4 bg-surface-white rounded-lg border border-outline-gray-1">
          <h5 class="font-medium text-sm text-ink-gray-8 mb-3 flex items-center gap-2">
            <BarChart3 class="h-4 w-4 text-ink-gray-5" />
            Variance Trend
          </h5>
          <div class="flex items-end justify-around h-32 gap-1">
            <div
              v-for="week in variance.weekly_details"
              :key="week.week_number"
              class="flex flex-col items-center flex-1"
            >
              <!-- Positive variance (above zero line) -->
              <div class="w-full flex justify-center" style="height: 50px;">
                <div
                  v-if="week.net_variance > 0"
                  class="w-4/5 bg-surface-green-3 rounded-t motion-reduce:transition-none"
                  :style="{ height: getBarHeight(week.net_variance, true) + '%', transition: 'height 0.2s ease' }"
                  role="img"
                  :aria-label="`Week ${week.week_label}: positive variance +${formatCompact(week.net_variance)}`"
                ></div>
              </div>
              <!-- Zero line -->
              <div class="w-full h-px bg-surface-gray-4"></div>
              <!-- Negative variance (below zero line) -->
              <div class="w-full flex justify-center" style="height: 50px;">
                <div
                  v-if="week.net_variance < 0"
                  class="w-4/5 bg-surface-red-5 rounded-b motion-reduce:transition-none"
                  :style="{ height: getBarHeight(week.net_variance, false) + '%', transition: 'height 0.2s ease' }"
                  role="img"
                  :aria-label="`Week ${week.week_label}: negative variance ${formatCompact(week.net_variance)}`"
                ></div>
              </div>
              <!-- Label -->
              <span class="text-xs text-ink-gray-6 mt-1 truncate w-full text-center">
                {{ week.week_label?.split(' ')[0] }}
              </span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { NO_VALUE } from '../../utils/format'
import { ref, computed } from 'vue'
import { Badge, Button } from 'frappe-ui'
import {
  GitCompare,
  ChevronDown,
  Target,
  TrendingUp,
  TrendingDown,
  Calendar,
  Sparkles,
  Lightbulb,
  Table2,
  BarChart3,
  FileQuestion,
} from 'lucide-vue-next'
import { deltaInk } from '../../utils/status'

interface Props {
  variance: {
    has_variance_data: boolean
    weeks_analyzed: number
    summary?: {
      inflow_forecast_accuracy: number
      outflow_forecast_accuracy: number
      total_net_variance: number
      total_inflow_variance: number
      total_outflow_variance: number
    }
    insights?: Array<{
      type: string
      title: string
      category: string
      description: string
      recommendation: string
    }>
    weekly_details?: Array<{
      week_number: number
      week_label: string
      inflow_variance: number
      inflow_variance_pct: number
      outflow_variance: number
      outflow_variance_pct: number
      net_variance: number
    }>
  } | null | undefined
}

const props = defineProps<Props>()

const expanded = ref(true)

const getBarHeight = (value: number, isPositive: boolean) => {
  const maxVariance = Math.max(
    ...((props.variance?.weekly_details || []).map((w) => Math.abs(w.net_variance))),
  )
  if (maxVariance === 0) return 0
  const absValue = Math.abs(value)
  const height = (absValue / maxVariance) * 100
  if (isPositive && value > 0) return height
  if (!isPositive && value < 0) return height
  return 0
}

const formatCompact = (value: number | null | undefined) => {
  if (value === null || value === undefined) return NO_VALUE
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absValue >= 1000000) return `${sign}${(absValue / 1000000).toFixed(1)}M`
  if (absValue >= 1000) return `${sign}${(absValue / 1000).toFixed(0)}K`
  return `${sign}${absValue.toFixed(0)}`
}
</script>
