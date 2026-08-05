<!--
  Section heading for dashboard panels.

  Exists to lock one type scale. The hand-rolled headings had drifted to at
  least three different size and weight combinations across Sales, Financial,
  and the strategic-finance tabs, with no rationale.

  Renders a real <h2>/<h3> so the page has a heading outline for assistive tech;
  the old markup used bare styled divs. `level` picks the element, never the size.
-->
<template>
  <div class="flex items-baseline justify-between gap-4">
    <component
      :is="`h${level}`"
      :class="[
        variant === 'caption'
          ? 'text-sm font-semibold text-ink-gray-6 uppercase tracking-wider'
          : 'text-base font-semibold text-ink-gray-8',
      ]"
    >
      {{ title }}
      <span v-if="hint" class="ml-2 text-sm font-normal text-ink-gray-6">{{ hint }}</span>
    </component>
    <slot name="actions" />
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    /** Scope or freshness, e.g. "YTD, KES". Never restate the title. */
    hint?: string
    /** Document outline position. Does not change the rendered size. */
    level?: 2 | 3 | 4
    /**
     * `caption` shrinks the heading to a small uppercase label so the panel
     * content dominates the visual hierarchy. `default` keeps the original
     * text-base semibold heading for legacy callers.
     */
    variant?: 'default' | 'caption'
  }>(),
  { level: 3, variant: 'default' },
)
</script>
