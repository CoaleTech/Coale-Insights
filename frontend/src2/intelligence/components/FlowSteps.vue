<!--
  An ordered control chain: the stages a document or obligation passes
  through, and what has to be true at each one.

  Marked up as an `<ol>` so the sequence survives without the arrows. The
  arrow glyphs are `aria-hidden` decoration; a screen reader gets the order
  from the list itself and the step label from the text, which means the
  diagram degrades to a numbered list rather than to nothing.

  Horizontal is the default because these chains read left-to-right in every
  process document they come from, but the flex container wraps and the arrow
  rotates a quarter turn once it does, so a four-stage chain on a phone
  becomes a vertical flow with the arrows still pointing along the sequence
  instead of a row that overflows its panel.

  No card chrome on the stages. Every call site already renders this inside a
  panel, so a bordered box in a bordered box is a nested card. The chevrons
  and the label hierarchy carry the sequence without one.
-->
<template>
  <ol
    class="flex gap-3"
    :class="orientation === 'vertical' ? 'flex-col' : 'flex-row flex-wrap items-stretch'"
  >
    <li
      v-for="(step, i) in steps"
      :key="`${step.label}-${i}`"
      class="flex min-w-0 gap-2"
      :class="orientation === 'vertical' ? 'flex-col' : 'flex-1 flex-row items-center'"
    >
      <div class="min-w-0 flex-1">
        <p class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5">
          {{ step.label }}
        </p>
        <p class="mt-1 text-sm font-semibold text-ink-gray-9">{{ step.title }}</p>
        <p v-if="step.detail" class="mt-1 text-xs leading-relaxed text-ink-gray-6">
          {{ step.detail }}
        </p>
      </div>

      <!--
        Between-items only. A trailing arrow after the last stage would
        promise a step that does not exist.
      -->
      <span
        v-if="i < steps.length - 1"
        class="shrink-0 self-center text-ink-gray-4"
        :class="orientation === 'vertical' ? 'rotate-90' : 'max-sm:rotate-90'"
        aria-hidden="true"
      >
        <ChevronRight class="h-4 w-4" />
      </span>
    </li>
  </ol>
</template>

<script setup lang="ts">
defineOptions({ name: 'FlowSteps' })

import { ChevronRight } from 'lucide-vue-next'

interface FlowStep {
  /** Stage marker: a number, or a short word like "Books" or "Portal". */
  label: string
  title: string
  detail?: string
}

withDefaults(
  defineProps<{
    steps: FlowStep[]
    orientation?: 'horizontal' | 'vertical'
  }>(),
  { orientation: 'horizontal' },
)
</script>
