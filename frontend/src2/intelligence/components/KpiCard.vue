<!--
  One KPI card for every intelligence dashboard.

  Replaces four divergent hand-rolled shapes (rounded-xl/mt-2 in Sales,
  rounded-lg/mt-1 in Financial, +label line in Risk, +sparkline in Executive)
  and the banned gradient blocks in Sales/Inventory.

  Shape language follows Espresso guidance: cards use --border-radius-lg
  + --card-shadow, so `rounded-lg shadow-sm`.

  Hierarchy is weight and scale, not colour (PRODUCT.md: "Typography carries
  authority ... Colour is secondary"). Colour appears only as a severity badge
  or a red delta, never as card decoration.

  `min-w-0` on the root is load-bearing, not defensive. Grid items default to
  `min-width: auto`, which refuses to shrink below their content, so an
  unbreakable ₹316,871,197 at text-2xl burst out of its track and overlapped the
  neighbouring card at tablet widths. Measured on FinancialIntelligence at 768px.

  Pass `amount` + `currency` for money rather than a pre-formatted string: the
  card knows its own width constraints and switches to compact notation on
  phones, where exact figures cannot fit a 160px track. `value` remains for
  non-money KPIs (percentages, counts, dates).

  The root is a static element, never `<component :is>`.

  `:is="clickable ? 'button' : 'div'"` looked harmless but rendered frappe-ui's
  Button component rather than a native button: Vue's dynamic resolution
  capitalizes the string and finds a registered `Button` first. Cards came out
  44px tall instead of 101, grey instead of white, with their three rows
  collapsed into the Button's single slot wrapper. Measured on
  StrategicFinanceIntelligence at 375px.

  A div with explicit button semantics also keeps the Badge out of a native
  <button>, which would be invalid the moment a card holds a link.

  Keep this comment outside <template>: a comment before the root element makes
  the component multi-root, which silently drops inherited class and attrs.
-->
<template>
  <div
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
    class="flex min-w-0 flex-col gap-1.5 rounded-lg p-4"
    :class="[
      variant === 'tile'
        ? 'bg-surface-gray-1 text-center'
        : 'border border-outline-gray-1 bg-card text-left',
      clickable
        ? 'cursor-pointer transition-colors duration-150 motion-reduce:duration-0 hover:border-accent hover:bg-accent-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3'
        : '',
    ]"
    @click="clickable ? $emit('click') : undefined"
    @keydown.enter.prevent="clickable ? $emit('click') : undefined"
    @keydown.space.prevent="clickable ? $emit('click') : undefined"
  >
    <!-- A tile centres its label over the figure; a card runs label and badge
         as a row with the badge trailing. -->
    <div
      class="flex min-w-0 gap-2"
      :class="variant === 'tile' ? 'flex-col items-center' : 'items-start justify-between'"
    >
      <span class="min-w-0 text-sm text-ink-gray-6">{{ label }}</span>
      <!--
        Hidden while errored or loading. Severity is derived from the value, and
        callers compute it from a `|| 0` fallback, so a failed AR fetch scored
        `scoreSeverity(0, { good: 30, higherIsBetter: false })` and painted a
        green "Low" badge onto a card that reads "Unavailable". A verdict about
        data that never arrived is still a false verdict.
      -->
      <Badge
        v-if="severity && severity !== 'none' && !error && !loading"
        v-bind="badge"
        :label="badge.label"
        size="sm"
        class="shrink-0"
      />
    </div>

    <SkeletonBlock v-if="loading" class="h-7 w-28" />
    <!--
      An unavailable metric must never be able to look like a real figure.
      Before this branch existed the card had only `loading` and data-present,
      so a rejected fetch left the parent's ref empty, `|| 0` took over, and the
      card rendered a confident "0". A zero and a failure are opposite facts.
    -->
    <span
      v-else-if="error"
      class="flex min-w-0 items-center gap-1.5 text-2xl font-semibold leading-tight text-ink-gray-6"
      :title="error"
    >
      <!-- `warn-fill`, not `warn`: the preset scopes the `-fill` steps to
           non-text graphics at the 3:1 threshold, which is exactly what an icon
           is. `text-app-warn-fill` would have emitted nothing at all, since the
           config registers these as `warn-fill` (tailwind.config.js:51). -->
      <AlertTriangle class="h-4 w-4 shrink-0 text-warn-fill" aria-hidden="true" />
      <span aria-hidden="true">Unavailable</span>
      <span class="sr-only">{{ label }} unavailable: {{ error }}</span>
    </span>
    <span
      v-else
      class="tnum block truncate text-2xl font-semibold leading-tight text-ink-gray-9"
      :title="exactValue"
    >
      <!-- Sighted readers get the compact figure that fits; assistive tech gets
           the exact one, so precision is never lost to a layout constraint. -->
      <span aria-hidden="true">{{ displayValue }}</span>
      <span class="sr-only">{{ exactValue }}</span>
    </span>

    <div
      v-if="!loading && !error && (hasDelta || sublabel || formattedTarget)"
      class="flex min-w-0 items-baseline gap-2"
    >
      <span v-if="hasDelta" class="tnum shrink-0 text-sm font-medium" :class="deltaClass">
        {{ deltaGlyph(delta) }}{{ formattedDelta }}
      </span>
      <!-- Target sits before the free-text sublabel: a benchmark is the thing
           that makes the figure judgeable, so it should not be pushed out by
           prose. Callers previously faked this by writing the benchmark into
           `sublabel` as a string, which no severity could ever read. -->
      <span v-if="formattedTarget" class="tnum shrink-0 text-sm text-ink-gray-5">
        Target {{ formattedTarget }}
      </span>
      <span v-if="sublabel" class="min-w-0 truncate text-sm text-ink-gray-6">{{ sublabel }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Badge } from 'frappe-ui'
import { AlertTriangle } from 'lucide-vue-next'
import { computed } from 'vue'
import { useBreakpoint } from '../../composables/useBreakpoint'
import { formatMoney, formatPercent } from '../../utils/format'
import { deltaGlyph, deltaInk, severityBadge, type Severity } from '../../utils/status'
import SkeletonBlock from './SkeletonBlock.vue'

const props = withDefaults(
  defineProps<{
    label: string
    /**
     * Pre-formatted for display. Use for non-money KPIs. For money prefer
     * `amount` + `currency` so the card can pick notation for the viewport.
     */
    value?: string | number
    /**
     * Suffix for a non-money, non-percent figure: `' days'`, `'x'`, `'/100'`.
     *
     * Exists so a caller can pass the raw number instead of interpolating it
     * into a string, which is what forced `|| 0` into 49 call sites.
     */
    unit?: string
    /**
     * Raw percentage on a 0-100 scale. Prefer this over pre-formatting with
     * `formatPercent`, which substitutes 0 for a missing value and would put
     * "0.0%" where there is no measurement -- the confident-zero defect this
     * component exists to prevent, smuggled in through the caller.
     */
    percent?: number | null
    /** Raw money value. Formatted here, compact on phones. */
    amount?: number | null
    /** Company currency reported by the server. Never hardcode. */
    currency?: string | null
    /**
     * Signed percentage change. Omit when there is nothing to compare.
     *
     * `null` counts as nothing to compare, not as zero. A server that withholds
     * a growth figure (because the prior-period base is too small for the ratio
     * to mean anything) sends `null`, and an earlier `!== undefined` check let it
     * through to render "0.0%" -- a confident claim of flat performance, which is
     * the opposite of what withholding it was meant to say.
     */
    delta?: number | null
    /** False for metrics where a bigger number is worse (DSO, churn, debt ratio). */
    deltaHigherIsBetter?: boolean
    /** Secondary context, e.g. "vs last quarter". Never restate the label. */
    sublabel?: string
    /**
     * Benchmark this figure is judged against. Formatted to match the value, so
     * pass a raw number for money cards rather than a pre-formatted string.
     *
     * A bare figure is not decision support: the reader cannot tell whether it
     * is acceptable. Before this prop existed the only way to show a benchmark
     * was to write it into `sublabel` as prose, which meant no severity could
     * be derived from it and the comparison was invisible to assistive tech as
     * anything other than free text.
     */
    target?: number | string
    severity?: Severity
    /**
     * `tile` is the dense inner readout used inside a section, as opposed to
     * the bordered headline `card` used in a page's top KPI strip.
     *
     * It exists because roughly twenty hand-rolled `bg-surface-gray-1` divs
     * were doing this job across HR, ESG and Manufacturing, and every one of
     * them rendered `{{ x || 0 }}`: the same confident-zero defect this
     * component was fixed for, reintroduced by bypassing it. A tile is a
     * different weight of the same thing, not a different thing, so it lives
     * here rather than in a parallel component with its own vocabulary.
     */
    variant?: 'card' | 'tile'
    loading?: boolean
    /**
     * Set when the fetch behind this metric failed. Takes precedence over any
     * value, because a stale or zero-defaulted figure shown confidently is
     * worse than an explicit gap.
     */
    error?: string
    clickable?: boolean
  }>(),
  { deltaHigherIsBetter: true, loading: false, clickable: false, variant: 'card' },
)

defineEmits<{ click: [] }>()

const { isPhone } = useBreakpoint()

const isMoney = computed(() => props.amount !== undefined && props.amount !== null)

/**
 * Distinct from a value that merely happens to be a number: `percent` being
 * present means the caller handed over a raw measurement and asked this
 * component to decide between formatting it and reporting it missing.
 */
const isPercent = computed(() => props.percent !== undefined)

/**
 * An absent figure reads as absent.
 *
 * Callers used to guard this themselves with `|| 0`, which is how a payload
 * missing `new_hires` came to report zero hires. Owning it here means a caller
 * can pass the raw field and cannot reintroduce that defect. A blank would look
 * like a rendering fault; a dash states that there is no value.
 */
const NO_VALUE = '-'

/**
 * Suffix is appended only to a value that exists.
 *
 * Callers wrote `` `${x || 0} days` `` and `(x || 0) + '/100'` because there was
 * nowhere to put the unit, and the interpolation forced them to coerce first --
 * so the suffix is what pushed a confident zero into the card. An absent value
 * renders as a bare dash: "- days" would be a unit on nothing.
 */
function plain(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return NO_VALUE
  return `${value}${props.unit ?? ''}`
}

/** A percentage renders identically compact and exact: it is already short. */
const percentValue = computed(() =>
  Number.isFinite(props.percent) ? formatPercent(props.percent as number) : NO_VALUE,
)

/** What the eye sees: compact on phones where a 160px track cannot hold exact. */
const displayValue = computed(() => {
  if (isPercent.value) return percentValue.value
  if (!isMoney.value) return plain(props.value)
  return formatMoney(props.amount, props.currency, { compact: isPhone.value })
})

/** What assistive tech and the tooltip get: always the exact figure. */
const exactValue = computed(() => {
  if (isPercent.value) return percentValue.value
  if (!isMoney.value) return plain(props.value)
  return formatMoney(props.amount, props.currency)
})

const badge = computed(() => severityBadge(props.severity))
/** A comparison exists only if it is a real number: `null` and `NaN` are not. */
const hasDelta = computed(() => Number.isFinite(props.delta))

const deltaClass = computed(() =>
  deltaInk(props.delta, { higherIsBetter: props.deltaHigherIsBetter }),
)
const formattedDelta = computed(() =>
  hasDelta.value ? `${Math.abs(props.delta as number).toFixed(1)}%` : '',
)

/**
 * Formatted to match the value it sits under: money targets go through the same
 * formatter as the figure so "Target KES 5,000,000" cannot appear beneath
 * "KES 4.2M" in a different notation.
 */
const formattedTarget = computed(() => {
  if (props.target === undefined || props.target === null || props.target === '') return ''
  if (isMoney.value && typeof props.target === 'number') {
    return formatMoney(props.target, props.currency, { compact: isPhone.value })
  }
  return String(props.target)
})
</script>
