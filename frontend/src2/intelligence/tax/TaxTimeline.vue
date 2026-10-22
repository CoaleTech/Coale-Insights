<script setup lang="ts">
// Dated rows: day/month + weekday, title + rule, optional amount and chip.
import TaxChip from './TaxChip.vue'
import { useTax } from './useTax'
import type { Chip, Num } from './taxTypes'

export interface TimelineItem {
	date: string
	weekday?: string
	title: string
	sub?: string | null
	amount?: Num
	chip?: Chip
}

withDefaults(defineProps<{ items: TimelineItem[]; showAmount?: boolean; empty?: string }>(), {
	showAmount: false,
	empty: 'Nothing due in this window.',
})
const t = useTax()
</script>

<template>
	<p v-if="!items.length" class="py-6 text-center text-sm text-ink-gray-6">{{ empty }}</p>
	<ul v-else class="divide-y divide-outline-gray-1">
		<li v-for="(it, i) in items" :key="i" class="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-3 py-2.5">
			<div>
				<div class="tnum text-sm font-semibold text-ink-gray-9">{{ t.dateShort(it.date) }}</div>
				<div class="text-xs text-ink-gray-6">{{ it.weekday ?? '' }}</div>
			</div>
			<div class="min-w-0">
				<div class="text-sm text-ink-gray-8">{{ it.title }}</div>
				<div v-if="it.sub" class="text-xs text-ink-gray-6">{{ it.sub }}</div>
			</div>
			<div class="flex items-center gap-3">
				<span v-if="showAmount" class="tnum text-sm text-ink-gray-8">{{ t.money(it.amount) }}</span>
				<TaxChip v-if="it.chip" :chip="it.chip" />
			</div>
		</li>
	</ul>
</template>
