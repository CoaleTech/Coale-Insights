<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
	DEFAULT_DATE_RANGES,
	CUSTOM_RANGE_VALUE,
	isCustomRange,
	encodeCustomRange,
	decodeCustomRange,
	type DateRangeOption,
} from '../utils/dateRangePresets'

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

// Local custom-range editing state, seeded from an already-encoded value.
// Selecting "Custom Range" from the dropdown enters this mode immediately,
// even before both dates are picked -- `modelValue` only updates once the
// range is complete (see the watcher below), so the dropdown's own
// v-model can't be the source of truth for whether the date inputs show.
const initialRange = decodeCustomRange(props.modelValue)
const customMode = ref(isCustomRange(props.modelValue))
const customStart = ref(initialRange?.start ?? '')
const customEnd = ref(initialRange?.end ?? '')

// Resync when a parent changes `modelValue` out from under us -- a filter
// reset back to a preset, or a different custom range set programmatically.
watch(
	() => props.modelValue,
	(value) => {
		const range = decodeCustomRange(value)
		customMode.value = !!range
		if (range) {
			customStart.value = range.start
			customEnd.value = range.end
		}
	},
)

watch([customStart, customEnd], ([start, end]) => {
	if (customMode.value && start && end) {
		emit('update:modelValue', encodeCustomRange({ start, end }))
	}
})

const selectedValue = computed({
  get: () => (customMode.value ? CUSTOM_RANGE_VALUE : props.modelValue),
  set: (value: string) => {
    customMode.value = value === CUSTOM_RANGE_VALUE
    if (!customMode.value) emit('update:modelValue', value)
  },
})
</script>

<!--
  Period selector shared by the intelligence dashboards, plus an optional
  explicit "from / to" range (see `customMode` in the script above).

  `shrink-0` and `min-w-0` together are load-bearing: this sits in a flex control
  cluster beside a title and a refresh button, and without them it was measured
  collapsing to 30px wide at 375px, showing none of its selected label. The
  wrapping div's own `flex-wrap` lets the two date inputs drop to a second
  line rather than force horizontal scroll once space runs out.

  Height floor of 44px on phones for a reliable touch target, released at `sm`
  where the pointer is likely a mouse and vertical space is better spent on data.
-->
<template>
  <div class="flex flex-wrap items-center gap-2">
    <select
      v-model="selectedValue"
      aria-label="Reporting period"
      class="min-h-11 w-auto shrink-0 cursor-pointer rounded-md border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-7 hover:border-outline-gray-3 focus:outline-none focus:ring-2 focus:ring-outline-gray-3 sm:min-h-0"
    >
      <option v-for="range in options" :key="range.value" :value="range.value">
        {{ range.label }}
      </option>
      <option :value="CUSTOM_RANGE_VALUE">Custom Range</option>
    </select>
    <template v-if="customMode">
      <input
        v-model="customStart"
        type="date"
        aria-label="Custom range start date"
        :max="customEnd || undefined"
        class="min-h-11 w-auto shrink-0 rounded-md border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-7 hover:border-outline-gray-3 focus:outline-none focus:ring-2 focus:ring-outline-gray-3 sm:min-h-0"
      />
      <span class="text-sm text-ink-gray-5" aria-hidden="true">to</span>
      <input
        v-model="customEnd"
        type="date"
        aria-label="Custom range end date"
        :min="customStart || undefined"
        class="min-h-11 w-auto shrink-0 rounded-md border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-7 hover:border-outline-gray-3 focus:outline-none focus:ring-2 focus:ring-outline-gray-3 sm:min-h-0"
      />
    </template>
  </div>
</template>
