<script setup lang="ts">
// Ranked horizontal bars. The bar is decoration (aria-hidden); the figure is
// always printed, so nothing depends on reading the bar length or colour.
import { computed } from 'vue'
import { NO_VALUE } from '../../utils/format'

export interface BarRow {
	label: string
	sub?: string | null
	value: number | null | undefined
	/** Printed figure; falls back to `-` for null. */
	display: string
	tone?: 'acc' | 'pos' | 'warn' | 'neg' | 'mut'
}

const props = defineProps<{ rows: BarRow[] }>()

const FILL = {
	acc: 'bg-accent',
	pos: 'bg-pos-fill',
	warn: 'bg-warn-fill',
	neg: 'bg-neg-fill',
	mut: 'bg-muted-fill',
} as const

const max = computed(() => Math.max(0, ...props.rows.map((r) => (Number.isFinite(r.value) ? Math.abs(r.value as number) : 0))))
const bars = computed(() =>
	props.rows.map((r) => ({
		...r,
		width: Number.isFinite(r.value) && max.value > 0 ? Math.max(2, (Math.abs(r.value as number) / max.value) * 100) : 0,
		fill: FILL[r.tone ?? 'acc'],
	})),
)
</script>

<template>
	<ul class="space-y-3">
		<li
			v-for="b in bars"
			:key="b.label"
			class="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_auto] items-center gap-3"
		>
			<div class="min-w-0">
				<div class="text-sm text-ink-gray-8">{{ b.label }}</div>
				<div v-if="b.sub" class="text-xs text-ink-gray-6">{{ b.sub }}</div>
			</div>
			<div class="h-2.5 rounded-full bg-surface-gray-2" aria-hidden="true">
				<div class="h-full rounded-full" :class="b.fill" :style="{ width: `${b.width}%` }" />
			</div>
			<span class="tnum min-w-[4.5rem] text-right text-sm text-ink-gray-8">{{ b.display || NO_VALUE }}</span>
		</li>
	</ul>
</template>
