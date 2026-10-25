<!--
  Inline stat strip: one bordered row of labelled figures. Replaces a grid of
  identical KPI cards (impeccable ban). Money is exact (compact only on phones,
  with the exact figure kept for assistive tech); a missing figure is a dash,
  never a confident zero.

  Keep this comment outside <template> (see TabBrief.vue).
-->
<template>
  <dl
    class="grid min-w-0 grid-cols-2 divide-x divide-y divide-outline-gray-1 overflow-hidden rounded-lg border border-outline-gray-1 bg-card sm:divide-y-0"
    :class="items.length === 5 ? 'sm:grid-cols-5' : 'sm:grid-cols-4'"
  >
    <div v-for="item in items" :key="item.label" class="flex min-w-0 flex-col gap-1 p-4">
      <dt class="text-xs uppercase tracking-wide text-ink-gray-6">{{ item.label }}</dt>
      <dd class="tnum truncate text-xl font-semibold" :class="TONE[item.tone ?? 'none']" :title="exact(item)">
        <span aria-hidden="true">{{ display(item) }}</span>
        <span class="sr-only">{{ exact(item) }}</span>
      </dd>
      <dd v-if="item.sublabel" class="truncate text-xs text-ink-gray-6">{{ item.sublabel }}</dd>
    </div>
  </dl>
</template>

<script setup lang="ts">
import { useBreakpoint } from '../../composables/useBreakpoint'
import { NO_VALUE, formatMoney, formatPercent } from '../../utils/format'

export interface StatItem {
  label: string
  amount?: number | null
  percent?: number | null
  value?: string | number | null
  unit?: string
  sublabel?: string
  tone?: 'neg' | 'warn' | 'pos'
}

const props = defineProps<{ items: StatItem[]; currency?: string | null }>()
const { isPhone } = useBreakpoint()

const TONE = {
  none: 'text-ink-gray-9',
  neg: 'text-ink-red-4',
  warn: 'text-ink-amber-3',
  pos: 'text-ink-green-3',
} as const

function render(item: StatItem, compact: boolean): string {
  if ('amount' in item) return formatMoney(item.amount, props.currency, { compact })
  if ('percent' in item) return formatPercent(item.percent)
  return item.value == null ? NO_VALUE : `${item.value}${item.unit ?? ''}`
}
const exact = (item: StatItem) => render(item, false)
const display = (item: StatItem) => render(item, isPhone.value)
</script>
