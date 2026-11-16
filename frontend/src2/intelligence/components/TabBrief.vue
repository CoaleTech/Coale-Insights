<!--
  One-sentence verdict for a tab. The sentence is built on the server
  (insights/ml/tab_briefs) and rendered verbatim; this component never derives
  text from numbers. No brief, no panel: an older cached payload simply shows
  the tab without one.

  Full border + tint, never a side stripe (impeccable ban).

  Keep this comment outside <template>: a comment before the root element makes
  the component multi-root, which silently drops inherited class and attrs.
-->
<template>
  <section
    v-if="brief?.headline"
    class="flex min-w-0 flex-col gap-2 rounded-lg border border-outline-gray-1 p-4"
    :class="severityTint(severity)"
  >
    <p class="text-xs font-medium uppercase tracking-wide text-ink-gray-7">
      {{ severityBadge(severity).label }}
    </p>
    <h2 class="max-w-3xl text-lg font-semibold leading-snug text-ink-gray-9">{{ brief.headline }}</h2>
    <dl v-if="brief.details?.length" class="grid gap-x-8 gap-y-2 text-sm text-ink-gray-7 md:grid-cols-2">
      <div v-for="d in brief.details" :key="d.label">
        <dt class="inline font-semibold text-ink-gray-9">{{ d.label }}: </dt>
        <dd class="inline">{{ d.text }}</dd>
      </div>
    </dl>
    <div v-if="$slots.default" class="text-sm text-ink-gray-7"><slot /></div>
    <p v-if="asOfText" class="tnum text-xs text-ink-gray-7">As of {{ asOfText }}</p>
  </section>
</template>

<script lang="ts">
export interface BriefAction {
  title: string
  text: string
  impact?: string | null
  owner?: string | null
}
export interface Brief {
  severity: string
  headline: string
  details?: { label: string; text: string }[]
  actions?: BriefAction[]
}
</script>

<script setup lang="ts">
import { computed } from 'vue'
import { formatDate, formatDateTime } from '../../utils/format'
import { normaliseSeverity, severityBadge, severityTint } from '../../utils/status'

const props = defineProps<{
  brief?: Brief | null
  asOf?: string
}>()
// Date-only stamps would read "00:00" through formatDateTime.
const asOfText = computed(() =>
  props.asOf ? (props.asOf.length <= 10 ? formatDate(props.asOf) : formatDateTime(props.asOf)) : '',
)
const severity = computed(() => normaliseSeverity(props.brief?.severity))
</script>
