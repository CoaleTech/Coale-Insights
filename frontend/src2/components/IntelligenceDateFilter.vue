<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const dateRanges = [
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
  { value: '90d', label: 'Last 90 Days' },
  { value: '6m', label: 'Last 6 Months' },
  { value: '12m', label: 'Last 12 Months' },
  { value: '24m', label: 'Last 24 Months' },
  { value: 'all', label: 'All Time' },
]

const selectedValue = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
})
</script>

<!--
  Period selector shared by the intelligence dashboards.

  `shrink-0` and `min-w-0` together are load-bearing: this sits in a flex control
  cluster beside a title and a refresh button, and without them it was measured
  collapsing to 30px wide at 375px, showing none of its selected label.

  Height floor of 44px on phones for a reliable touch target, released at `sm`
  where the pointer is likely a mouse and vertical space is better spent on data.
-->
<template>
  <select
    v-model="selectedValue"
    aria-label="Reporting period"
    class="min-h-11 w-auto shrink-0 cursor-pointer rounded-md border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-7 hover:border-outline-gray-3 focus:outline-none focus:ring-2 focus:ring-outline-gray-3 sm:min-h-0"
  >
    <option v-for="range in dateRanges" :key="range.value" :value="range.value">
      {{ range.label }}
    </option>
  </select>
</template>
