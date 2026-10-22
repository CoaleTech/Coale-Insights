<script setup lang="ts">
import { computed } from 'vue'
import RankedBars from './RankedBars.vue'
import TaxCallout from './TaxCallout.vue'
import TaxCard from './TaxCard.vue'
import TaxChart from './TaxChart.vue'
import TaxTable from './TaxTable.vue'
import { axisConfig } from './taxCharts'
import type { VatData } from './taxTypes'
import { periodLabel, useTax } from './useTax'

const props = defineProps<{ tab: VatData }>()
const t = useTax()

const chart = computed(() => {
	const rows = props.tab.monthly.map((m) => ({ month: periodLabel(m.month), Output: m.output, Input: m.input, 'Net payable': m.net }))
	// A refund month makes net negative; keep it on the axis instead of clipping it.
	const lowest = Math.min(0, ...props.tab.monthly.map((m) => m.net ?? 0))
	return axisConfig(rows, 'month', [{ name: 'Output' }, { name: 'Input' }, { name: 'Net payable', type: 'line' }], { title: t.amountTitle(), yMin: lowest })
})
const mix = computed(() =>
	props.tab.supply_mix.map((s) => ({ label: s.label, sub: s.note, value: s.taxable_value, display: t.moneyC(s.taxable_value) })),
)
</script>

<template>
	<div class="space-y-4">
		<div class="grid gap-4 lg:grid-cols-3">
			<TaxCard class="lg:col-span-2" title="Output vs input VAT" subtitle="Monthly, 12 months">
				<TaxChart :config="chart" class="h-72" />
			</TaxCard>
			<TaxCard title="Supply mix by VAT treatment" subtitle="Taxable value, period to date">
				<RankedBars v-if="mix.length" :rows="mix" />
				<p v-else class="py-6 text-center text-sm text-ink-gray-6">No sales in this period.</p>
			</TaxCard>
		</div>
		<div class="grid gap-4 lg:grid-cols-2">
			<TaxCard title="Input VAT at risk by reason" subtitle="Input VAT needs a valid eTIMS invoice and has a claim window">
				<TaxTable
					caption="Input VAT at risk by reason"
					:cols="[
						{ key: 'reason', label: 'Reason' },
						{ key: 'invoices', label: 'Invoices', kind: 'count', right: true },
						{ key: 'input_vat', label: 'Input VAT', kind: 'money', right: true },
					]"
					:rows="tab.input_risk"
					:drill-title="(r) => r.reason"
				/>
			</TaxCard>
			<TaxCard title="Suppliers closest to the cut-off" subtitle="Drill-down opens purchase invoices">
				<TaxTable
					caption="Suppliers closest to the input VAT cut-off"
					:cols="[
						{ key: 'supplier', label: 'Supplier' },
						{ key: 'invoices', label: 'Invoices', kind: 'count', right: true },
						{ key: 'input_vat_at_risk', label: 'Input VAT at risk', kind: 'money', right: true },
						{ key: 'oldest_date', label: 'Oldest', kind: 'date' },
						{ key: 'chip', label: 'Window', kind: 'chip' },
					]"
					:rows="tab.suppliers_at_risk"
					:drill-title="(r) => r.supplier"
				/>
			</TaxCard>
		</div>
		<TaxCallout :big="t.moneyC(tab.reverse_charge.amount)">{{ tab.reverse_charge.note }}</TaxCallout>
	</div>
</template>
