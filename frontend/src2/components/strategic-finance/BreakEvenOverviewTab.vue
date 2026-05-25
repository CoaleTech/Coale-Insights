<template>
  <div class="space-y-6">
    <!-- Summary KPI Cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
      <div v-for="card in kpiCards" :key="card.label" class="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm border">
        <p class="text-xs text-gray-500 dark:text-gray-400">{{ card.label }}</p>
        <p class="text-lg font-bold mt-1" :class="card.colorClass ?? 'text-gray-900 dark:text-white'">{{ card.value }}</p>
        <span v-if="card.badge" :class="card.badge.cls" class="text-xs px-2 py-0.5 rounded mt-1 inline-block">{{ card.badge.label }}</span>
      </div>
    </div>

    <!-- Cash Flow Breakeven Banner -->
    <div v-if="cashData" class="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border">
      <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Cash Flow Break-Even</h3>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <p class="text-xs text-gray-500">Break-Even Month</p>
          <p class="text-base font-semibold text-gray-900 dark:text-white mt-0.5">
            {{ cashData.breakeven_month || 'Not reached' }}
          </p>
        </div>
        <div>
          <p class="text-xs text-gray-500">Total Cash In</p>
          <p class="text-base font-semibold text-green-600 mt-0.5">{{ formatCurrency(cashData.total_cash_in) }}</p>
        </div>
        <div>
          <p class="text-xs text-gray-500">Total Cash Out</p>
          <p class="text-base font-semibold text-red-600 mt-0.5">{{ formatCurrency(cashData.total_cash_out) }}</p>
        </div>
        <div>
          <p class="text-xs text-gray-500">Cash Coverage</p>
          <p class="text-base font-semibold mt-0.5" :class="cashData.coverage >= 1 ? 'text-green-600' : 'text-red-600'">
            {{ ((cashData.coverage ?? 0) * 100).toFixed(1) }}%
          </p>
          <span :class="ragBadgeClass(cashData.rag)" class="text-xs px-2 py-0.5 rounded mt-0.5 inline-block">{{ cashData.rag }}</span>
        </div>
      </div>
    </div>

    <!-- Employee Break-Even -->
    <div v-if="departments.length" class="bg-white dark:bg-gray-800 rounded-xl shadow-sm border overflow-hidden">
      <div class="px-5 py-4 border-b">
        <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300">Employee Break-Even by Department</h3>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-5">
        <div v-for="dept in departments" :key="dept.department" class="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-100 dark:border-gray-600">
          <div class="flex items-center justify-between mb-3">
            <h4 class="font-semibold text-gray-900 dark:text-white text-sm">{{ dept.department }}</h4>
            <span class="w-3 h-3 rounded-full flex-shrink-0" :class="ragDotClass(dept.rag)"></span>
          </div>
          <div class="space-y-2">
            <div class="flex justify-between text-xs">
              <span class="text-gray-500 dark:text-gray-400">Payroll Cost</span>
              <span class="font-medium text-gray-900 dark:text-white">{{ formatCurrency(dept.payroll_cost) }}</span>
            </div>
            <div class="flex justify-between text-xs">
              <span class="text-gray-500 dark:text-gray-400">Orders Needed</span>
              <span class="font-medium text-gray-900 dark:text-white">{{ dept.orders_needed?.toLocaleString() }}</span>
            </div>
            <div class="flex justify-between text-xs">
              <span class="text-gray-500 dark:text-gray-400">Actual Orders</span>
              <span class="font-medium text-gray-900 dark:text-white">{{ dept.actual_orders?.toLocaleString() }}</span>
            </div>
            <div class="flex justify-between text-xs">
              <span class="text-gray-500 dark:text-gray-400">Coverage</span>
              <span class="font-medium" :class="dept.coverage >= 1 ? 'text-green-600' : 'text-red-600'">
                {{ ((dept.coverage ?? 0) * 100).toFixed(1) }}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Capital Efficiency -->
    <div v-if="data.roce || data.irr" class="bg-white dark:bg-gray-800 rounded-xl shadow-sm border overflow-hidden">
      <div class="px-5 py-4 border-b">
        <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300">Capital Efficiency</h3>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 p-5">
        <div class="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-100 dark:border-gray-600">
          <p class="text-xs text-gray-500 dark:text-gray-400">ROCE</p>
          <p class="text-2xl font-bold mt-1" :class="ragTextClass(data.roce?.rag)">
            {{ data.roce?.roce?.toFixed(2) || 0 }}%
          </p>
          <p class="text-xs text-gray-500 mt-1">Target: {{ data.roce?.target?.toFixed(2) || 0 }}%</p>
          <span :class="ragBadgeClass(data.roce?.rag)" class="text-xs px-2 py-0.5 rounded mt-2 inline-block">{{ data.roce?.rag }}</span>
        </div>
        <div class="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-100 dark:border-gray-600">
          <p class="text-xs text-gray-500 dark:text-gray-400">IRR</p>
          <p class="text-2xl font-bold text-gray-900 dark:text-white mt-1">
            {{ data.irr?.irr != null ? `${data.irr.irr.toFixed(2)}%` : 'N/A' }}
          </p>
          <p class="text-xs text-gray-500 mt-1">Monthly cash flows</p>
        </div>
        <div class="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-100 dark:border-gray-600">
          <p class="text-xs text-gray-500 dark:text-gray-400">Capital Employed</p>
          <p class="text-2xl font-bold text-gray-900 dark:text-white mt-1">
            {{ formatCurrency(data.roce?.capital_employed) }}
          </p>
          <p class="text-xs text-gray-500 mt-1">EBIT: {{ formatCurrency(data.roce?.ebit) }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'

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

interface KpiCard {
  label: string
  value: string
  colorClass?: string
  badge?: { label: string; cls: string }
}

const props = defineProps<{ data: BreakevenSummary }>()

const _injectedCurrency = inject('currency', 'KES')
const getCurrency = (): string =>
  (typeof _injectedCurrency === 'string' ? _injectedCurrency : (_injectedCurrency as any)?.value) || 'KES'

const cashData = computed<CashFlowBreakeven | null>(() => props.data.cash_flow_breakeven ?? null)
const departments = computed<Department[]>(() => props.data.employee_breakeven?.departments ?? [])

const kpiCards = computed<KpiCard[]>(() => [
  { label: 'Fixed Costs', value: formatCurrency(props.data.fixed_costs) },
  { label: 'Variable Costs', value: formatCurrency(props.data.variable_costs) },
  { label: 'BE Revenue', value: formatCurrency(props.data.be_revenue) },
  { label: 'Actual Revenue', value: formatCurrency(props.data.actual_revenue) },
  { label: 'BE Quantity', value: (props.data.be_qty ?? 0).toLocaleString() },
  {
    label: 'Coverage',
    value: `${((props.data.coverage ?? 0) * 100).toFixed(1)}%`,
    colorClass: props.data.coverage >= 1 ? 'text-green-600' : 'text-red-600',
    badge: { label: props.data.rag, cls: ragBadgeClass(props.data.rag) }
  },
  {
    label: 'Safety Margin',
    value: `${(props.data.safety_margin ?? 0).toFixed(1)}%`,
    colorClass: (props.data.safety_margin ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
  }
])

function formatCurrency(value: number | null | undefined): string {
  const n = value ?? 0
  const curr = getCurrency()
  if (Math.abs(n) >= 1_000_000) return `${curr} ${(n / 1_000_000).toFixed(2)}M`
  if (Math.abs(n) >= 1_000) return `${curr} ${(n / 1_000).toFixed(1)}K`
  return `${curr} ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function ragBadgeClass(rag: string | undefined): string {
  if (rag === 'green') return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
  if (rag === 'amber') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
  return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
}

function ragTextClass(rag: string | undefined): string {
  if (rag === 'green') return 'text-green-700 dark:text-green-400'
  if (rag === 'amber') return 'text-amber-700 dark:text-amber-400'
  return 'text-red-700 dark:text-red-400'
}

function ragDotClass(rag: string | undefined): string {
  if (rag === 'green') return 'bg-green-500'
  if (rag === 'amber') return 'bg-amber-500'
  return 'bg-red-500'
}
</script>
