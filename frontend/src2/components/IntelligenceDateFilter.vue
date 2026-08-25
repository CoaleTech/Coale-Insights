<script setup lang="ts">
import { computed } from 'vue'
import { DEFAULT_DATE_RANGES, type DateRangeOption } from '../utils/dateRangePresets'

const props = withDefaults(
	defineProps<{
		modelValue: string
		options?: DateRangeOption[]
	}>(),
	{ options: () => DEFAULT_DATE_RANGES },
)

const emit = defineEmits<{
	(e: 'update:modelValue', value: string): void
}>()

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
    <option v-for="range in options" :key="range.value" :value="range.value">
      {{ range.label }}
    </option>
  </select>
</template>
