<template>
  <div class="space-y-6">
    <!-- Loading state -->
    <div v-if="!data" class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
      <KpiCard v-for="i in 7" :key="i" label="..." value="" :loading="true" />
    </div>

    <template v-else>
      <!-- Summary KPI Cards -->
      <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
        <KpiCard
          v-for="card in kpiCards"
          :key="card.label"
          :label="card.label"
          :value="card.value"
          :delta="card.delta"
          :delta-higher-is-better="card.deltaHigherIsBetter"
          :severity="card.severity"
        />
      </div>

      <!-- Cash Flow Break-Even Banner -->
      <div v-if="cashData" class="bg-surface-white rounded-lg p-5 shadow-sm border border-outline-gray-1">
        <SectionHeader variant="caption" title="Cash Flow Break-Even" :level="3" />
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3">
          <div>
            <p class="text-xs text-ink-gray-6">Break-Even Month</p>
            <p class="text-base font-semibold text-ink-gray-9 mt-0.5">
              {{ cashData.breakeven_month || 'Not reached' }}
            </p>
          </div>
          <div>
            <p class="text-xs text-ink-gray-6">Total Cash In</p>
            <p class="text-base font-semibold text-ink-gray-9 mt-0.5">{{ formatCurrency(cashData.total_cash_in) }}</p>
          </div>
          <div>
            <p class="text-xs text-ink-gray-6">Total Cash Out</p>
            <p class="text-base font-semibold text-ink-gray-9 mt-0.5">{{ formatCurrency(cashData.total_cash_out) }}</p>
          </div>
          <div>
            <p class="text-xs text-ink-gray-6">Cash Coverage</p>
            <p
              class="text-base font-semibold mt-0.5"
              :class="cashData.coverage >= 1 ? 'text-ink-gray-9' : 'text-ink-red-4'"
            >
              {{ ((cashData.coverage ?? 0) * 100).toFixed(1) }}%
            </p>
            <Badge v-bind="severityBadge(ragSeverity(cashData.rag))" size="sm" class="mt-1" />
          </div>
        </div>
      </div>

      <!-- Employee Break-Even -->
      <div v-if="departments.length" class="bg-surface-white rounded-lg shadow-sm border border-outline-gray-1 overflow-hidden">
        <div class="px-5 py-4 border-b border-outline-gray-1">
          <SectionHeader variant="caption" title="Employee Break-Even by Department" :level="3" />
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-5">
          <div
            v-for="dept in departments"
            :key="dept.department"
            class="bg-surface-gray-1 rounded-lg p-4 border border-outline-gray-1"
          >
            <div class="flex items-center justify-between mb-3">
              <h4 class="font-semibold text-ink-gray-9 text-sm">{{ dept.department }}</h4>
              <Badge v-bind="severityBadge(ragSeverity(dept.rag))" size="sm" />
            </div>
            <div class="space-y-2">
              <div class="flex justify-between text-xs">
                <span class="text-ink-gray-6">Payroll Cost</span>
                <span class="font-medium text-ink-gray-9">{{ formatCurrency(dept.payroll_cost) }}</span>
              </div>
              <div class="flex justify-between text-xs">
                <span class="text-ink-gray-6">Orders Needed</span>
                <span class="font-medium text-ink-gray-9">{{ dept.orders_needed?.toLocaleString() }}</span>
              </div>
              <div class="flex justify-between text-xs">
                <span class="text-ink-gray-6">Actual Orders</span>
                <span class="font-medium text-ink-gray-9">{{ dept.actual_orders?.toLocaleString() }}</span>
              </div>
              <div class="flex justify-between text-xs">
                <span class="text-ink-gray-6">Coverage</span>
                <span
                  class="font-medium"
                  :class="dept.coverage >= 1 ? 'text-ink-gray-9' : 'text-ink-red-4'"
                >
                  {{ ((dept.coverage ?? 0) * 100).toFixed(1) }}%
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Capital Efficiency -->
      <div v-if="data.roce || data.irr" class="bg-surface-white rounded-lg shadow-sm border border-outline-gray-1 overflow-hidden">
        <div class="px-5 py-4 border-b border-outline-gray-1">
          <SectionHeader variant="caption" title="Capital Efficiency" :level="3" />
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 p-5">
          <div class="bg-surface-gray-1 rounded-lg p-4 border border-outline-gray-1">
            <p class="text-xs text-ink-gray-6">ROCE</p>
            <p class="text-2xl font-bold mt-1 text-ink-gray-9">
              {{ data.roce?.roce?.toFixed(2) || 0 }}%
            </p>
            <p class="text-xs text-ink-gray-6 mt-1">Target: {{ data.roce?.target?.toFixed(2) || 0 }}%</p>
            <Badge v-bind="severityBadge(ragSeverity(data.roce?.rag))" size="sm" class="mt-2" />
          </div>
          <div class="bg-surface-gray-1 rounded-lg p-4 border border-outline-gray-1">
            <p class="text-xs text-ink-gray-6">IRR</p>
            <p class="text-2xl font-bold text-ink-gray-9 mt-1">
              {{ data.irr?.irr != null ? `${data.irr.irr.toFixed(2)}%` : 'N/A' }}
            </p>
            <p class="text-xs text-ink-gray-6 mt-1">Monthly cash flows</p>
          </div>
          <div class="bg-surface-gray-1 rounded-lg p-4 border border-outline-gray-1">
            <p class="text-xs text-ink-gray-6">Capital Employed</p>
            <p class="text-2xl font-bold text-ink-gray-9 mt-1">
              {{ formatCurrency(data.roce?.capital_employed) }}
            </p>
            <p class="text-xs text-ink-gray-6 mt-1">EBIT: {{ formatCurrency(data.roce?.ebit) }}</p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useCurrency } from '../../composables/useCurrency'
import { Badge } from 'frappe-ui'
import { ragSeverity, severityBadge, type Severity } from '../../utils/status'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'

defineOptions({ name: 'BreakEvenOverviewTab' })

interface CashFlowBreakeven {
  breakeven_month: string | null
  total_cash_in: number
  total_cash_out: number
  coverage: number
  rag: string
}

interface Department {
  department: string
  payroll_cost: number
  orders_needed: number
  actual_orders: number
  coverage: number
  rag: string
}

interface RoceData {
  roce: number
  target: number
  capital_employed: number
  ebit: number
  rag: string
}

interface IrrData {
  irr: number | null
}

interface BreakevenSummary {
  fixed_costs: number
  variable_costs: number
  be_revenue: number
  be_qty: number
  actual_revenue: number
  coverage: number
  safety_margin: number
  rag: string
  cash_flow_breakeven?: CashFlowBreakeven
  employee_breakeven?: { departments: Department[] }
  roce?: RoceData
  irr?: IrrData
}

interface KpiCardData {
  label: string
  value: string
  delta?: number
  deltaHigherIsBetter?: boolean
  severity?: Severity
}

const props = defineProps<{ data: BreakevenSummary | null }>()

const currency = useCurrency()
const getCurrency = (): string => currency.value

const cashData = computed<CashFlowBreakeven | null>(() => props.data?.cash_flow_breakeven ?? null)
const departments = computed<Department[]>(() => props.data?.employee_breakeven?.departments ?? [])

const kpiCards = computed<KpiCardData[]>(() => {
  if (!props.data) return []
  return [
    { label: 'Fixed Costs', value: formatCurrency(props.data.fixed_costs) },
    { label: 'Variable Costs', value: formatCurrency(props.data.variable_costs) },
    { label: 'BE Revenue', value: formatCurrency(props.data.be_revenue) },
    { label: 'Actual Revenue', value: formatCurrency(props.data.actual_revenue) },
    { label: 'BE Quantity', value: (props.data.be_qty ?? 0).toLocaleString() },
    {
      label: 'Coverage',
      value: `${((props.data.coverage ?? 0) * 100).toFixed(1)}%`,
      severity: ragSeverity(props.data.rag),
    },
    {
      label: 'Safety Margin',
      value: `${(props.data.safety_margin ?? 0).toFixed(1)}%`,
      delta: props.data.safety_margin ?? 0,
      deltaHigherIsBetter: true,
    },
  ]
})

function formatCurrency(value: number | null | undefined): string {
  const n = value ?? 0
  const curr = getCurrency()
  if (Math.abs(n) >= 1_000_000) return `${curr} ${(n / 1_000_000).toFixed(2)}M`
  if (Math.abs(n) >= 1_000) return `${curr} ${(n / 1_000).toFixed(1)}K`
  return `${curr} ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
</script>
