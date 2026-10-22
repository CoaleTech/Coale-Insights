<script setup lang="ts">
import { computed } from 'vue'
import RankedBars from './RankedBars.vue'
import TaxCard from './TaxCard.vue'
import TaxTable from './TaxTable.vue'
import type { CustomsData } from './taxTypes'
import { useTax } from './useTax'

const props = defineProps<{ tab: CustomsData }>()
const t = useTax()

const landed = computed(() => props.tab.landed.map((l) => ({ label: l.label, value: l.amount, display: t.moneyC(l.amount) })))
</script>

<template>
	<div class="space-y-4">
		<div class="grid gap-4 lg:grid-cols-3">
			<TaxCard title="Landed taxes on imports" subtitle="Period to date">
				<RankedBars v-if="landed.length" :rows="landed" />
				<p v-else class="py-6 text-center text-sm text-ink-gray-6">No landed cost vouchers in this period.</p>
			</TaxCard>
			<TaxCard class="lg:col-span-2" title="Import entries" subtitle="Reconcile each line to the customs entry; keep documents for 5 years">
				<TaxTable
					caption="Import entries"
					:cols="[
						{ key: 'entry', label: 'Entry' },
						{ key: 'supplier', label: 'Supplier' },
						{ key: 'cif', label: 'CIF', kind: 'moneyC', right: true },
						{ key: 'duty', label: 'Duty', kind: 'moneyC', right: true },
						{ key: 'idf', label: 'IDF', kind: 'moneyC', right: true },
						{ key: 'rdl', label: 'RDL', kind: 'moneyC', right: true },
						{ key: 'vat', label: 'VAT', kind: 'moneyC', right: true },
						{ key: 'chip', label: 'Docs', kind: 'chip' },
					]"
					:rows="tab.entries"
					:drill-title="(r) => r.entry"
					empty="No import entries in this period."
				/>
			</TaxCard>
		</div>
		<div class="grid gap-4 lg:grid-cols-2">
			<TaxCard title="Excise duty" subtitle="Only for excisable goods and services the entity supplies">
				<TaxTable
					caption="Excise duty"
					:cols="[
						{ key: 'item', label: 'Excisable item' },
						{ key: 'basis', label: 'Basis' },
						{ key: 'rate', label: 'Rate' },
						{ key: 'amount', label: 'Amount', kind: 'money', right: true },
					]"
					:rows="tab.excise"
					empty="No excise postings found."
				/>
			</TaxCard>
			<TaxCard title="Digital services from abroad" subtitle="Services bought from non-resident suppliers">
				<div class="max-h-96 overflow-y-auto">
					<TaxTable
						caption="Digital services from non-resident suppliers"
						:cols="[
							{ key: 'supplier', label: 'Supplier' },
							{ key: 'service', label: 'Service' },
							{ key: 'tax_note', label: 'Tax' },
							{ key: 'amount', label: 'Amount', kind: 'money', right: true },
						]"
						:rows="tab.digital_services"
						empty="No services from non-resident suppliers."
					/>
				</div>
			</TaxCard>
		</div>
	</div>
</template>
