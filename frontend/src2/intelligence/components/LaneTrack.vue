<!--
  One reconciliation lane: how much of a stream is matched, how much is
  awaiting action, and how much is a live discrepancy.

  The reason this is a component and not three divs at the call site is the
  `total === 0` branch. A stacked bar computed as `matched / total` renders
  an empty track at 0/0, and an empty track next to the word "matched" reads
  as "nothing is wrong". On a reconciliation surface the difference between
  "every row matched" and "there are no rows" is the difference between a
  clean period and an unfiled one. Every caller got this wrong at least once,
  so the honest branch lives here where it cannot be forgotten.

  Segment order is fixed matched -> pending -> issue, worst last, so the eye
  lands on the unresolved tail without needing the colour to carry it.
-->
<template>
  <div class="min-w-0">
    <div class="flex items-baseline justify-between gap-3">
      <span class="min-w-0 truncate text-sm font-medium text-ink-gray-8">{{ label }}</span>
      <span v-if="hasRows" class="tnum shrink-0 text-sm font-semibold text-ink-gray-9">
        {{ formatPercent(matchedPct) }} matched
      </span>
      <span v-else class="shrink-0 text-sm text-ink-gray-5">No rows</span>
    </div>

    <!--
      With no rows there is nothing to apportion, so the track stays flat and
      empty rather than being filled by a division that has no denominator.
    -->
    <div
      class="mt-1.5 flex h-2.5 w-full overflow-hidden rounded-full bg-surface-gray-2"
      role="img"
      :aria-label="aria"
    >
      <template v-if="hasRows">
        <div
          v-for="seg in segments"
          :key="seg.key"
          class="h-full first:rounded-l-full last:rounded-r-full"
          :class="severityFill(seg.severity)"
          :style="{ width: `${seg.pct}%` }"
        />
      </template>
    </div>

    <p v-if="note" class="mt-1.5 text-xs text-ink-gray-5">{{ note }}</p>

    <dl v-if="hasRows" class="mt-2 flex flex-wrap gap-x-4 gap-y-1">
      <div v-for="seg in legend" :key="seg.key" class="flex items-center gap-1.5">
        <span
          class="h-2 w-2 shrink-0 rounded-full"
          :class="severityFill(seg.severity)"
          aria-hidden="true"
        />
        <dt class="text-xs text-ink-gray-6">{{ seg.label }}</dt>
        <dd class="tnum text-xs font-medium text-ink-gray-8">{{ formatCount(seg.count) }}</dd>
      </div>
    </dl>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'LaneTrack' })

import { computed } from 'vue'
import { formatCount, formatPercent } from '../../utils/format'
import { severityFill, type Severity } from '../../utils/status'

const props = withDefaults(
  defineProps<{
    label: string
    matched: number
    pending?: number
    issue?: number
    /**
     * Denominator. Defaults to the three counts summed, which is right when
     * they partition the stream. Pass it explicitly when the stream has rows
     * in none of the three states, so the unclassified remainder shows as
     * unfilled track instead of inflating the matched percentage.
     */
    total?: number
    note?: string
  }>(),
  { pending: 0, issue: 0 },
)

const counts = computed(() => ({
  matched: safe(props.matched),
  pending: safe(props.pending),
  issue: safe(props.issue),
}))

const total = computed(() => {
  const explicit = props.total
  if (Number.isFinite(explicit)) return Math.max(0, explicit as number)
  const c = counts.value
  return c.matched + c.pending + c.issue
})

const hasRows = computed(() => total.value > 0)

const matchedPct = computed(() => (hasRows.value ? (counts.value.matched / total.value) * 100 : 0))

/** `low` reads as resolved, `medium` as awaiting action, `critical` as a live gap. */
const legend = computed(() => [
  { key: 'matched', label: 'Matched', count: counts.value.matched, severity: 'low' as Severity },
  { key: 'pending', label: 'Pending', count: counts.value.pending, severity: 'medium' as Severity },
  { key: 'issue', label: 'Issue', count: counts.value.issue, severity: 'critical' as Severity },
])

const segments = computed(() =>
  legend.value
    .filter((seg) => seg.count > 0)
    .map((seg) => ({ ...seg, pct: (seg.count / total.value) * 100 })),
)

const aria = computed(() => {
  if (!hasRows.value) return `${props.label}: no rows to reconcile`
  const c = counts.value
  return (
    `${props.label}: ${formatPercent(matchedPct.value)} matched ` +
    `(${c.matched} matched, ${c.pending} pending, ${c.issue} issue of ${total.value})`
  )
})

function safe(value: number | undefined): number {
  return Number.isFinite(value) ? Math.max(0, value as number) : 0
}
</script>
