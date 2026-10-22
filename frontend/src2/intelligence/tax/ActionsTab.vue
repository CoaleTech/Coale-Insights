<script setup lang="ts">
import { computed } from 'vue'
import RankedBars from './RankedBars.vue'
import TaxCard from './TaxCard.vue'
import TaxTable, { type Col } from './TaxTable.vue'
import type { ActionsData, TabId } from './taxTypes'
import { useTax } from './useTax'

const props = defineProps<{ tab: ActionsData }>()
const emit = defineEmits<{ navigate: [tab: TabId] }>()
const t = useTax()

// Drop the owner column when no row has one: a column of dashes says nothing.
const cols = computed<Col[]>(() => [
	{ key: 'chip', label: 'Priority', kind: 'chip' },
	{ key: 'action', label: 'Action' },
	{ key: 'tax', label: 'Tax' },
	...(props.tab.rows.some((r) => r.owner) ? [{ key: 'owner', label: 'Owner' }] : []),
	{ key: 'due_label', label: 'Due' },
	{ key: 'exposure', label: 'Exposure', kind: 'money' as const, right: true },
])
const byTax = computed(() => props.tab.by_tax.map((r) => ({ label: r.label, value: r.count, display: t.count(r.count) })))
const TONE = { critical: 'neg', high: 'warn' } as const
const byPriority = computed(() =>
	props.tab.by_priority_7d.map((r) => ({
		label: r.label,
		value: r.count,
		display: t.count(r.count),
		tone: TONE[r.label.toLowerCase() as keyof typeof TONE] ?? ('mut' as const),
	})),
)
// A row without its own drill-down opens the dashboard tab the rule came from.
function goSource(row: ActionsData['rows'][number]) {
	emit('navigate', row.source_tab as TabId)
}
</script>

<template>
	<div class="space-y-4">
		<TaxCard title="Action queue" subtitle="Ranked by exposure; each rule links back to its source tab" :meta="`${tab.rows.length} of ${tab.total_open}`">
			<TaxTable
				caption="Open tax actions"
				:cols="cols"
				:rows="tab.rows"
				:drill-title="(r) => r.action"
				action-key="button_label"
				action-label="Open"
				:on-action="goSource"
				empty="No open actions."
			/>
		</TaxCard>
		<div class="grid gap-4 lg:grid-cols-3">
			<TaxCard title="Open by tax" subtitle="Count">
				<RankedBars v-if="byTax.length" :rows="byTax" />
				<p v-else class="py-6 text-center text-sm text-ink-gray-6">No open actions.</p>
			</TaxCard>
			<TaxCard title="Due in 7 days by priority" subtitle="Count">
				<RankedBars v-if="byPriority.length" :rows="byPriority" />
				<p v-else class="py-6 text-center text-sm text-ink-gray-6">Nothing due in the next 7 days.</p>
			</TaxCard>
			<TaxCard title="Rules that created actions" subtitle="Hits in this run">
				<TaxTable
					caption="Rules that created actions"
					:cols="[{ key: 'rule', label: 'Rule' }, { key: 'hits', label: 'Hits', kind: 'count', right: true }]"
					:rows="tab.rules"
				/>
			</TaxCard>
		</div>
	</div>
</template>
