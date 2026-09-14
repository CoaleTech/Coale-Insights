<!--
  A composite 0-100 score as a ring, with an optional per-input breakdown
  beside it.

  Why SVG and not a conic-gradient: the arc length is data. A conic-gradient
  has to be assembled as an inline `style` string, which means resolving a
  design token to a literal colour in JS (`themeColor()`) and re-resolving it
  on every theme flip. A stroked circle takes a `stroke-*` utility directly,
  so the same Tailwind severity token that paints every other status graphic
  on these dashboards paints this one, and dark mode needs no extra code.

  The `viewBox` is 36x36 with `r = 15.9155` on purpose: that radius has a
  circumference of exactly 100 (2 * pi * 15.9155), so `stroke-dasharray`
  takes the score as a literal percentage with no arithmetic at the call site
  and no rounding drift between the number in the middle and the arc around
  it.

  A missing score renders the track only, never a 0% arc. Those look nothing
  alike to a reader who knows the difference and identical to one who does
  not: an unmeasured compliance score and a compliance score of zero are
  opposite facts, and the second one is an emergency.

  `min-w-0` on the root and on the breakdown list is load-bearing. Both are
  flex children, which default to `min-width: auto` and refuse to shrink
  below their content, so a long breakdown label pushed the ring out of its
  column instead of wrapping.
-->
<template>
  <div class="flex min-w-0 items-center gap-5">
    <div
      class="relative shrink-0"
      :style="{ width: `${size}px`, height: `${size}px` }"
    >
      <!--
        `-rotate-90` starts the arc at twelve o'clock. SVG angles start at
        three o'clock, which reads as a ring that is already 25% full.
      -->
      <svg
        class="h-full w-full -rotate-90"
        viewBox="0 0 36 36"
        role="img"
        :aria-label="aria"
      >
        <circle
          class="stroke-ink-gray-2"
          cx="18"
          cy="18"
          r="15.9155"
          fill="none"
          stroke-width="3"
        />
        <circle
          v-if="hasScore"
          :class="arcInk"
          cx="18"
          cy="18"
          r="15.9155"
          fill="none"
          stroke-width="3"
          stroke-linecap="round"
          :stroke-dasharray="`${dash} 100`"
        />
      </svg>

      <div class="absolute inset-0 flex flex-col items-center justify-center">
        <span class="tnum text-2xl font-semibold leading-none text-ink-gray-9">
          {{ scoreText }}
        </span>
        <span class="mt-1 text-xs text-ink-gray-6">{{ label }}</span>
      </div>
    </div>

    <dl v-if="breakdown && breakdown.length" class="min-w-0 flex-1 space-y-2.5">
      <div v-for="row in breakdown" :key="row.label" class="min-w-0">
        <div class="flex items-baseline gap-2">
          <!--
            The dot is decorative: the row already names its own severity in
            the accessible label below, so announcing the colour twice adds
            noise for a screen reader and nothing for anyone else.
          -->
          <span
            class="mt-1.5 h-2 w-2 shrink-0 rounded-full"
            :class="severityFill(row.severity)"
            aria-hidden="true"
          />
          <dt class="min-w-0 flex-1 truncate text-sm text-ink-gray-6">
            {{ row.label }}
          </dt>
          <dd class="tnum shrink-0 text-sm font-medium text-ink-gray-8">
            {{ row.value }}
          </dd>
        </div>
        <div
          v-if="row.pct !== undefined"
          class="mt-1 h-1 w-full overflow-hidden rounded-full bg-surface-gray-2"
          role="img"
          :aria-label="severityAria(row.label, row.severity, formatPercent(row.pct))"
        >
          <div
            class="h-full rounded-full"
            :class="severityFill(row.severity)"
            :style="{ width: `${clampPct(row.pct)}%` }"
          />
        </div>
      </div>
    </dl>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'HealthRing' })

import { computed } from 'vue'
import { formatCount, formatPercent, NO_VALUE } from '../../utils/format'
import {
  HEALTH_SCORE_THRESHOLDS,
  readinessLabel,
  scoreSeverity,
  severityAria,
  severityFill,
  severityStroke,
  type Severity,
} from '../../utils/status'

interface BreakdownRow {
  label: string
  value: number | string
  severity?: Severity
  /** 0-100. Renders a thin proportional bar under the row when present. */
  pct?: number
}

const props = withDefaults(
  defineProps<{
    score: number | null | undefined
    label?: string
    /** Outer diameter in px. */
    size?: number
    breakdown?: BreakdownRow[]
  }>(),
  { label: 'Health', size: 100 },
)

const hasScore = computed(() => Number.isFinite(props.score))

const severity = computed((): Severity =>
  // Higher is better for every score that reaches this component: these are
  // readiness and coverage percentages, not risk indices.
  scoreSeverity(hasScore.value ? (props.score as number) : null, HEALTH_SCORE_THRESHOLDS),
)

/**
 * Reuse the one severity-to-colour mapping rather than restating it, as a
 * stroke rather than a background.
 *
 * Neither circle routes its colour through `currentColor` any more. That
 * indirection failed silently: `outline-gray` is role-scoped to borders, so
 * asking it for ink emitted no CSS, `currentColor` fell through to the
 * ambient text colour, and both the track and the arc drew in near-black --
 * one flat dark ring carrying no severity signal on either theme.
 */
const arcInk = computed(() => severityStroke(severity.value))

const dash = computed(() => clampPct(props.score))

const scoreText = computed(() =>
  hasScore.value ? formatCount(props.score, { decimals: 0 }) : NO_VALUE,
)

/**
 * Readiness vocabulary for the ring, risk vocabulary for the breakdown rows,
 * and both are correct.
 *
 * The score is higher-is-better, so `severityAria` would announce a healthy
 * 86% as "Low" -- contradicting the badge beside it. The breakdown rows are
 * categorical risk buckets the caller labels itself (`Overdue` is genuinely
 * `critical`), so those keep the risk words.
 */
const aria = computed(() =>
  hasScore.value
    ? `${props.label}: ${readinessLabel(severity.value)} (${formatPercent(props.score, 0)})`
    : `${props.label}: not available`,
)

function clampPct(value: number | null | undefined): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(100, Math.max(0, value as number))
}
</script>
