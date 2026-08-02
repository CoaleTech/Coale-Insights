<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <div class="p-2 bg-surface-gray-2 rounded-lg">
          <FlaskConical class="h-5 w-5 text-ink-gray-5" />
        </div>
        <div>
          <h4 class="font-semibold text-ink-gray-9">What-If Scenarios</h4>
          <p class="text-xs text-ink-gray-6">Explore different cash flow outcomes</p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <!-- Filter by type -->
        <Select
          v-model="filterType"
          :options="filterOptions"
        />
        <Button
          variant="ghost"
          aria-label="Toggle scenarios panel"
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
    </div>

    <div v-if="expanded" class="space-y-4">
      <!-- Baseline Summary -->
      <div class="grid grid-cols-3 gap-3 p-3 bg-surface-gray-1 rounded-lg">
        <div class="text-center">
          <p class="text-xs text-ink-gray-6">Base Ending Balance</p>
          <p class="text-lg font-bold text-ink-gray-9">{{ formatCompact(scenarios?.base_ending_balance || 0) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs text-ink-gray-6">Base Min Balance</p>
          <p
            class="text-lg font-bold"
            :class="(scenarios?.base_min_balance || 0) < (scenarios?.threshold || 0) ? 'text-ink-red-4' : 'text-ink-gray-9'"
          >
            {{ formatCompact(scenarios?.base_min_balance || 0) }}
          </p>
        </div>
        <div class="text-center">
          <p class="text-xs text-ink-gray-6">Min Threshold</p>
          <p class="text-lg font-bold text-ink-gray-9">{{ formatCompact(scenarios?.threshold || 0) }}</p>
        </div>
      </div>

      <!-- Scenarios Table -->
      <div class="border border-outline-gray-1 rounded-lg overflow-hidden">
        <table class="w-full text-sm" aria-label="What-if scenarios">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-3 py-2.5 text-left text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Scenario</th>
              <th scope="col" class="px-3 py-2.5 text-center text-xs font-medium text-ink-gray-6 uppercase tracking-wider w-20">Type</th>
              <th scope="col" class="px-3 py-2.5 text-right text-xs font-medium text-ink-gray-6 uppercase tracking-wider w-24">Impact</th>
              <th scope="col" class="px-3 py-2.5 text-right text-xs font-medium text-ink-gray-6 uppercase tracking-wider w-24">End Bal.</th>
              <th scope="col" class="px-3 py-2.5 text-right text-xs font-medium text-ink-gray-6 uppercase tracking-wider w-24">Min Bal.</th>
              <th scope="col" class="px-3 py-2.5 text-center text-xs font-medium text-ink-gray-6 uppercase tracking-wider w-20">Risk</th>
              <th scope="col" class="px-3 py-2.5 text-center text-xs font-medium text-ink-gray-6 uppercase tracking-wider w-16">Alert</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-1">
            <tr
              v-for="row in filteredScenarios"
              :key="row.id"
              :class="[
                'cursor-pointer transition-colors motion-reduce:transition-none',
                selectedScenario?.id === row.id
                  ? 'bg-surface-gray-2 outline outline-2 outline-offset-[-2px] outline-outline-gray-3'
                  : 'hover:bg-surface-gray-1',
              ]"
              tabindex="0"
              :aria-selected="selectedScenario?.id === row.id"
              @click="selectRow(row)"
              @keydown.enter.prevent="selectRow(row)"
              @keydown.space.prevent="selectRow(row)"
            >
              <!-- Scenario Name -->
              <td class="px-3 py-3">
                <div class="flex items-center gap-2">
                  <div class="p-1.5 bg-surface-gray-2 rounded-lg flex-shrink-0">
                    <component :is="getScenarioIcon(row)" class="h-4 w-4 text-ink-gray-5" />
                  </div>
                  <div class="min-w-0">
                    <p class="font-medium text-ink-gray-9 text-sm truncate">{{ row.name }}</p>
                    <p class="text-xs text-ink-gray-6 truncate">{{ row.description }}</p>
                  </div>
                </div>
              </td>

              <!-- Type Badge -->
              <td class="px-3 py-3 text-center">
                <Badge :label="row.type" theme="gray" variant="subtle" size="sm" />
              </td>

              <!-- Impact -->
              <td class="px-3 py-3 text-right">
                <span class="font-bold text-sm" :class="deltaInk(row.impact)">
                  {{ row.impact >= 0 ? '+' : '' }}{{ formatCompact(row.impact) }}
                </span>
              </td>

              <!-- Ending Balance -->
              <td class="px-3 py-3 text-right">
                <span class="font-medium text-ink-gray-9 text-sm">{{ formatCompact(row.ending_balance) }}</span>
              </td>

              <!-- Min Balance -->
              <td class="px-3 py-3 text-right">
                <span
                  class="font-medium text-sm"
                  :class="row.min_balance < (scenarios?.threshold || 0) ? 'text-ink-red-4' : 'text-ink-gray-9'"
                >
                  {{ formatCompact(row.min_balance) }}
                </span>
              </td>

              <!-- Risk Level -->
              <td class="px-3 py-3 text-center">
                <Badge v-bind="severityBadge(riskToSeverity(row.risk_level))" size="sm" />
              </td>

              <!-- Weeks Below Threshold -->
              <td class="px-3 py-3 text-center">
                <span
                  v-if="row.weeks_below_threshold > 0"
                  class="flex items-center justify-center gap-1 text-ink-red-4 text-sm"
                >
                  <AlertTriangle class="h-3.5 w-3.5" />
                  {{ row.weeks_below_threshold }}
                </span>
                <CheckCircle v-else class="h-4 w-4 text-ink-gray-5 mx-auto" />
              </td>
            </tr>
          </tbody>
        </table>

        <!-- Empty State -->
        <div v-if="!filteredScenarios.length" class="p-8 text-center">
          <FlaskConical class="h-10 w-10 mx-auto text-ink-gray-5 mb-2" />
          <p class="text-sm text-ink-gray-7">No scenarios available</p>
        </div>
      </div>

      <!-- Selected Scenario Detail -->
      <div
        v-if="selectedScenario"
        class="p-4 bg-surface-gray-1 rounded-lg border border-outline-gray-1"
      >
        <div class="flex items-center justify-between mb-3">
          <h5 class="font-medium text-sm text-ink-gray-8 flex items-center gap-2">
            <BarChart3 class="h-4 w-4 text-ink-gray-5" />
            {{ selectedScenario.name }}
          </h5>
          <Button
            variant="ghost"
            aria-label="Close scenario detail"
            @click="selectedScenario = null"
          >
            <X class="h-4 w-4 text-ink-gray-5" />
          </Button>
        </div>

        <!-- Comparison Bars -->
        <div class="space-y-3">
          <div class="flex items-center gap-3">
            <span class="w-16 text-xs text-ink-gray-7">Base</span>
            <div class="flex-1 h-6 bg-surface-gray-2 rounded-lg overflow-hidden relative">
              <div
                class="h-full bg-surface-blue-3 rounded-lg motion-reduce:transition-none"
                :style="{ width: getBarWidth(scenarios?.base_ending_balance || 0) + '%', transition: 'width 0.3s ease' }"
              ></div>
              <span class="absolute right-2 top-1 text-xs font-medium text-ink-gray-8">
                {{ formatCompact(scenarios?.base_ending_balance || 0) }}
              </span>
            </div>
          </div>
          <div class="flex items-center gap-3">
            <span class="w-16 text-xs text-ink-gray-7">Scenario</span>
            <div class="flex-1 h-6 bg-surface-gray-2 rounded-lg overflow-hidden relative">
              <div
                class="h-full rounded-lg motion-reduce:transition-none"
                :class="selectedScenario.impact >= 0 ? 'bg-surface-green-3' : 'bg-surface-red-5'"
                :style="{ width: getBarWidth(selectedScenario.ending_balance) + '%', transition: 'width 0.3s ease' }"
              ></div>
              <span class="absolute right-2 top-1 text-xs font-medium text-ink-gray-8">
                {{ formatCompact(selectedScenario.ending_balance) }}
              </span>
            </div>
          </div>
        </div>

        <div class="mt-3 pt-3 border-t border-outline-gray-1 grid grid-cols-3 gap-4 text-center">
          <div>
            <p class="text-xs text-ink-gray-6">Impact</p>
            <p class="font-bold" :class="deltaInk(selectedScenario.impact)">
              {{ selectedScenario.impact >= 0 ? '+' : '' }}{{ formatCompact(selectedScenario.impact) }}
            </p>
          </div>
          <div>
            <p class="text-xs text-ink-gray-6">Min Balance</p>
            <p
              class="font-bold"
              :class="selectedScenario.min_balance < (scenarios?.threshold || 0) ? 'text-ink-red-4' : 'text-ink-gray-9'"
            >
              {{ formatCompact(selectedScenario.min_balance) }}
            </p>
          </div>
          <div>
            <p class="text-xs text-ink-gray-6">Weeks at Risk</p>
            <p
              class="font-bold"
              :class="selectedScenario.weeks_below_threshold > 0 ? 'text-ink-red-4' : 'text-ink-gray-9'"
            >
              {{ selectedScenario.weeks_below_threshold || 0 }}
            </p>
          </div>
        </div>
      </div>

      <!-- Quick Actions -->
      <div v-if="scenarios?.quick_actions?.length" class="space-y-2">
        <h5 class="font-medium text-sm text-ink-gray-8 flex items-center gap-2">
          <Lightbulb class="h-4 w-4 text-ink-gray-5" />
          Recommended Actions
        </h5>
        <div class="space-y-2">
          <div
            v-for="(action, idx) in scenarios.quick_actions"
            :key="idx"
            class="p-3 rounded-lg border border-outline-gray-1 bg-surface-white"
          >
            <div class="flex items-center justify-between mb-1">
              <span class="font-medium text-sm text-ink-gray-9">{{ action.action }}</span>
              <Badge
                v-bind="severityBadge(riskToSeverity(action.priority))"
                size="sm"
              />
            </div>
            <p class="text-xs text-ink-gray-7">{{ action.description }}</p>
            <p class="text-xs text-ink-gray-6 mt-1">Potential impact: {{ formatCompact(action.potential_impact) }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { NO_VALUE } from '../../utils/format'
import { ref, computed } from 'vue'
import { Badge, Button, Select } from 'frappe-ui'
import {
  FlaskConical,
  ChevronDown,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Clock,
  FastForward,
  Pause,
  Sun,
  CloudRain,
  Lightbulb,
  Zap,
  CheckCircle,
  BarChart3,
  X,
} from 'lucide-vue-next'
import { deltaInk, severityBadge, type Severity } from '../../utils/status'

interface ScenarioRow {
  id: string
  name: string
  description: string
  type: string
  icon: string
  impact: number
  ending_balance: number
  min_balance: number
  risk_level: string
  weeks_below_threshold: number
}

interface QuickAction {
  action: string
  description: string
  priority: string
  potential_impact: number
}

interface Props {
  scenarios: {
    base_ending_balance: number
    base_min_balance: number
    threshold: number
    scenarios: ScenarioRow[]
    quick_actions: QuickAction[]
  } | null | undefined
}

const props = defineProps<Props>()

const expanded = ref(true)
const selectedScenario = ref<ScenarioRow | null>(null)
const filterType = ref('all')

const filterOptions = [
  { label: 'All Types', value: 'all' },
  { label: 'Risks', value: 'risk' },
  { label: 'Opportunities', value: 'opportunity' },
  { label: 'Decisions', value: 'decision' },
]

const filteredScenarios = computed<ScenarioRow[]>(() => {
  const scenarios = props.scenarios?.scenarios || []
  if (filterType.value === 'all') return scenarios
  return scenarios.filter((s) => s.type === filterType.value)
})

const selectRow = (row: ScenarioRow) => {
  selectedScenario.value = selectedScenario.value?.id === row.id ? null : row
}

const getBarWidth = (value: number) => {
  const max = Math.max(
    props.scenarios?.base_ending_balance || 0,
    ...((props.scenarios?.scenarios || []).map((s) => s.ending_balance)),
  )
  if (max <= 0) return 10
  return Math.max(10, Math.min(100, (value / max) * 100))
}

const iconMap: Record<string, unknown> = {
  'clock': Clock,
  'trending-up': TrendingUp,
  'trending-down': TrendingDown,
  'fast-forward': FastForward,
  'pause': Pause,
  'alert-triangle': AlertTriangle,
  'sun': Sun,
  'cloud-rain': CloudRain,
}

const getScenarioIcon = (scenario: ScenarioRow) => iconMap[scenario.icon] || Zap

/** Map a risk level string to a Severity for Badge rendering. */
const riskToSeverity = (level: string | undefined): Severity => {
  switch (level) {
    case 'critical': return 'critical'
    case 'high': return 'high'
    case 'medium': return 'medium'
    case 'low': return 'low'
    default: return 'none'
  }
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
