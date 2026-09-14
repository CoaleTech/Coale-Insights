<!--
  A labelled money waterfall: how a headline figure is arrived at, one
  contributing line at a time.

  Bars are scaled against the largest absolute amount in the set, not against
  a running total, because these rows are components of an explanation rather
  than a cumulative balance. Scaling to the maximum keeps the largest line at
  full width so the relative weight of the others is readable; scaling to the
  sum would compress every line into a sliver whenever one term dominates,
  which on a tax breakdown it always does.

  `direction` tints the bar only. It never changes the sign of the number or
  wraps it in brackets: the server decides whether an amount is negative and
  the reader needs to see exactly what it sent. A deduction whose amount is
  positive is a data question, and hiding it behind presentation logic here
  would make that question unanswerable from the screen.

  A `null` amount is a dash and no bar. Drawing a zero-width bar for an
  unmeasured line implies a measured zero.
-->
<template>
  <dl class="space-y-2.5">
    <div v-for="(row, i) in rows" :key="`${row.label}-${i}`" class="min-w-0">
      <div class="flex items-baseline justify-between gap-3">
        <dt class="min-w-0 truncate text-sm text-ink-gray-7">{{ row.label }}</dt>
        <dd
          class="tnum shrink-0 text-sm font-semibold"
          :class="amountInk(row)"
        >
          {{ formatMoney(row.amount, currency, { compact: true }) }}
        </dd>
      </div>
      <div
        v-if="width(row) !== null"
        class="mt-1 h-2 w-full overflow-hidden rounded-full bg-surface-gray-2"
        role="img"
        :aria-label="`${row.label}: ${formatMoney(row.amount, currency)}`"
      >
        <div
          class="h-full rounded-full"
          :class="barFill(row)"
          :style="{ width: `${width(row)}%` }"
        />
      </div>
    </div>
    <p v-if="!rows.length" class="text-sm text-ink-gray-5">No breakdown available</p>
  </dl>
</template>

<script setup lang="ts">
defineOptions({ name: 'WaterfallRows' })

import { computed } from 'vue'
import { formatMoney } from '../../utils/format'
import { severityFill } from '../../utils/status'

interface WaterfallRow {
  label: string
  amount: number | null
  /** 0-100. Overrides the derived proportional width when supplied. */
  pct?: number
  direction?: 'positive' | 'negative' | 'neutral'
}

const props = withDefaults(
  defineProps<{
    rows: WaterfallRow[]
    currency?: string | null
  }>(),
  { currency: null },
)

const maxAbs = computed(() =>
  props.rows.reduce(
    (max, row) => (Number.isFinite(row.amount) ? Math.max(max, Math.abs(row.amount as number)) : max),
    0,
  ),
)

/** `null` means "draw no bar at all", which is distinct from a 0% bar. */
function width(row: WaterfallRow): number | null {
  if (Number.isFinite(row.pct)) return clamp(row.pct as number)
  if (!Number.isFinite(row.amount)) return null
  if (maxAbs.value === 0) return null
  return clamp((Math.abs(row.amount as number) / maxAbs.value) * 100)
}

/**
 * Reuse the shared severity ramp so a deduction here is the same amber as a
 * pending item anywhere else on the dashboard, instead of a fourth colour
 * vocabulary that only this component speaks.
 */
function barFill(row: WaterfallRow): string {
  switch (row.direction) {
    case 'negative':
      return severityFill('medium')
    case 'positive':
      return severityFill('low')
    default:
      return severityFill('none')
  }
}

function amountInk(row: WaterfallRow): string {
  if (!Number.isFinite(row.amount)) return 'text-ink-gray-5'
  return row.direction === 'negative' ? 'text-ink-gray-7' : 'text-ink-gray-9'
}

function clamp(value: number): number {
  return Math.min(100, Math.max(0, value))
}
</script>
