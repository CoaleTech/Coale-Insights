<script setup lang="ts">
// IntelligenceChart, or an honest empty note when no series has a value (all null or 0).
import type { AxisChartConfig } from 'frappe-ui/src/components/Charts/types'
import { computed } from 'vue'
import IntelligenceChart from '../components/IntelligenceChart.vue'

const props = defineProps<{ config: AxisChartConfig }>()
const hasData = computed(() =>
	props.config.data.some((row) => props.config.series.some((s) => typeof row[s.name] === 'number' && row[s.name] !== 0)),
)
</script>

<template>
	<IntelligenceChart v-if="hasData" :config="config" />
	<p v-else class="py-10 text-center text-sm text-ink-gray-6">Nothing to chart for this period.</p>
</template>
