<!--
  Ranked actions for a tab. Built on the server with the headline (Rule 7) and
  rendered verbatim. No actions, no card.

  Keep this comment outside <template> (see TabBrief.vue).
-->
<template>
  <section v-if="actions?.length" class="min-w-0 rounded-lg border border-outline-gray-1 bg-card">
    <h3 class="border-b border-outline-gray-1 px-4 py-3 text-base font-semibold text-ink-gray-9">Actions</h3>
    <ol class="divide-y divide-outline-gray-1">
      <li v-for="(a, i) in actions" :key="a.title" class="flex min-w-0 items-start gap-3 px-4 py-3">
        <span class="tnum flex size-6 shrink-0 items-center justify-center rounded-full bg-surface-gray-2 text-xs font-medium text-ink-gray-7">{{ i + 1 }}</span>
        <div class="min-w-0 flex-1">
          <p class="text-sm font-semibold text-ink-gray-9">{{ a.title }}</p>
          <p class="text-sm text-ink-gray-7">{{ a.text }}</p>
        </div>
        <div v-if="a.impact || a.owner" class="flex shrink-0 flex-col items-end gap-0.5 text-sm">
          <span v-if="a.impact" class="tnum font-medium text-ink-gray-9">{{ a.impact }}</span>
          <span v-if="a.owner" class="text-xs text-ink-gray-6">{{ a.owner }}</span>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import type { BriefAction } from './TabBrief.vue'

defineProps<{ actions?: BriefAction[] | null }>()
</script>
