<script setup lang="ts">
import { computed } from 'vue'
import RankedBars from './RankedBars.vue'
import TaxCard from './TaxCard.vue'
import TaxTable from './TaxTable.vue'
import TaxTimeline from './TaxTimeline.vue'
import type { LegalData } from './taxTypes'
import { useTax } from './useTax'

const props = defineProps<{ tab: LegalData }>()
const t = useTax()

const stages = computed(() => props.tab.stages.map((s) => ({ label: s.label, sub: s.note, value: s.count, display: t.count(s.count) })))
const amnesty = computed(() => props.tab.amnesty_by_tax.map((a) => ({ label: a.tax, value: a.amount, display: t.moneyC(a.amount) })))
</script>

<template>
	<div class="space-y-4">
		<div class="grid gap-4 lg:grid-cols-3">
			<TaxCard title="Cases by stage" subtitle="From notice to court">
				<RankedBars v-if="stages.length" :rows="stages" />
				<p v-else class="py-6 text-center text-sm text-ink-gray-6">No open cases.</p>
			</TaxCard>
			<TaxCard class="lg:col-span-2" title="Case register" subtitle="Statutory clocks come from the Tax Procedures Act">
				<TaxTable
					caption="Tax case register"
					:cols="[
						{ key: 'case_ref', label: 'Ref' },
						{ key: 'tax_type', label: 'Tax' },
						{ key: 'period_label', label: 'Period' },
						{ key: 'principal', label: 'Principal', kind: 'money', right: true },
						{ key: 'penalty_interest', label: 'Penalty + interest', kind: 'money', right: true },
						{ key: 'stage_chip', label: 'Stage', kind: 'chip' },
						{ key: 'next_step', label: 'Next step' },
					]"
					:rows="tab.cases"
					:drill-title="(r) => r.case_ref"
					action-label="Open"
					empty="No open cases."
				>
					<template #cell-next_step="{ row }">
						{{ t.text(row.next_step) }}<span v-if="row.days_left !== null"> · {{ row.days_left }} d</span>
					</template>
				</TaxTable>
			</TaxCard>
		</div>
		<div class="grid gap-4 lg:grid-cols-2">
			<TaxCard title="Upcoming legal dates">
				<TaxTimeline :items="tab.dates" empty="No upcoming legal dates." />
			</TaxCard>
			<TaxCard title="Principal in amnesty scope, by tax" subtitle="Principal outstanding up to the scope date">
				<RankedBars v-if="amnesty.length" :rows="amnesty" />
				<p v-else class="py-6 text-center text-sm text-ink-gray-6">No amnesty-eligible cases.</p>
			</TaxCard>
		</div>
	</div>
</template>
