<script setup lang="ts" generic="T extends object">
// Generic data table. `kind` picks the formatter so a null always prints `-`.
// If any row carries `drill`, a trailing button column opens the drill panel.
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import TaxChip from './TaxChip.vue'
import { useTax } from './useTax'
import type { Chip, Drill } from './taxTypes'

export interface Col {
	key: string
	label: string
	kind?: 'text' | 'money' | 'moneyC' | 'count' | 'pct' | 'date' | 'chip' | 'days'
	right?: boolean
}

const props = withDefaults(
	defineProps<{
		cols: Col[]
		rows: T[]
		/** Drill panel title, per row. */
		drillTitle?: (row: T) => string
		/** Row field holding a per-row button label; `actionLabel` is the fallback. */
		actionKey?: string
		actionLabel?: string
		/** Fallback for rows without `drill`, e.g. jump to the source tab. */
		onAction?: (row: T) => void
		empty?: string
		caption: string
	}>(),
	{ empty: 'Nothing to show for this period.', actionKey: 'action_label', actionLabel: 'View rows' },
)

const t = useTax()
const drillOf = (row: T) => (row as { drill?: Drill }).drill
const hasAction = computed(() => !!props.onAction || props.rows.some(drillOf))

function cell(row: T, c: Col): string {
	const v = (row as Record<string, unknown>)[c.key]
	switch (c.kind) {
		case 'money': return t.money(v as number | null)
		case 'moneyC': return t.moneyC(v as number | null)
		case 'count': return t.count(v as number | null)
		case 'pct': return t.pct(v as number | null)
		case 'date': return t.date(v as string | null)
		case 'days': return v === null || v === undefined ? t.text(v) : `${t.count(v as number)} d`
		default: return t.text(v)
	}
}
const chip = (row: T, c: Col) => (row as Record<string, unknown>)[c.key] as Chip | null
const label = (row: T) => ((row as Record<string, unknown>)[props.actionKey] as string | undefined) || props.actionLabel
function open(row: T) {
	const d = drillOf(row)
	if (d) t.openDrill(props.drillTitle?.(row) ?? props.caption, d)
	else props.onAction?.(row)
}
</script>

<template>
	<p v-if="!rows.length" class="py-6 text-center text-sm text-ink-gray-6">{{ empty }}</p>
	<div v-else class="overflow-x-auto">
		<table class="w-full border-collapse text-sm">
			<caption class="sr-only">{{ caption }}</caption>
			<thead>
				<tr class="border-b border-outline-gray-2 text-left text-ink-gray-6">
					<th v-for="c in cols" :key="c.key" scope="col" class="px-2 py-2 font-medium" :class="c.right ? 'text-right' : ''">
						{{ c.label }}
					</th>
					<th v-if="hasAction" scope="col" class="px-2 py-2"><span class="sr-only">Action</span></th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="(row, i) in rows" :key="i" class="border-b border-outline-gray-1 last:border-0">
					<td v-for="c in cols" :key="c.key" class="px-2 py-2 text-ink-gray-8" :class="c.right ? 'tnum text-right' : ''">
						<TaxChip v-if="c.kind === 'chip'" :chip="chip(row, c)" />
						<slot v-else :name="`cell-${c.key}`" :row="row" :text="cell(row, c)">{{ cell(row, c) }}</slot>
					</td>
					<td v-if="hasAction" class="whitespace-nowrap px-2 py-2 text-right">
						<Button v-if="drillOf(row) || onAction" size="sm" variant="outline" @click="open(row)">{{ label(row) }}</Button>
					</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>
