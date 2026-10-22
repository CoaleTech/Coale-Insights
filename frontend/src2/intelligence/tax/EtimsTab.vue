<script setup lang="ts">
import { computed } from 'vue'
import RankedBars from './RankedBars.vue'
import TaxCallout from './TaxCallout.vue'
import TaxCard from './TaxCard.vue'
import TaxChart from './TaxChart.vue'
import TaxTable from './TaxTable.vue'
import { axisConfig } from './taxCharts'
import type { EtimsData } from './taxTypes'
import { periodLabel, useTax } from './useTax'

const props = defineProps<{ tab: EtimsData }>()
const t = useTax()

const trend = computed(() => {
	const known = props.tab.coverage_trend.map((w) => w.pct).filter((p): p is number => p !== null)
	// 90-100 keeps week-to-week movement readable; drop lower only if data needs it.
	const yMin = Math.min(90, Math.floor(Math.min(...known, 100) / 5) * 5)
	return axisConfig(
		props.tab.coverage_trend.map((w) => ({ week: periodLabel(w.week), 'Purchase coverage %': w.pct, 'Target 100%': 100 })),
		'week',
		[{ name: 'Purchase coverage %', type: 'line' }, { name: 'Target 100%', type: 'line' }],
		{ title: 'Coverage (%)', yMin, yMax: 100 },
	)
})
const x = computed(() => props.tab.exposure)
const costs = computed(() => [
	{ label: 'Income tax disallowance', sub: x.value.cit_rate === null ? null : `${t.pct(x.value.cit_rate * 100, 0)} of spend without an invoice`, value: x.value.income_tax_disallowance, display: t.moneyC(x.value.income_tax_disallowance), tone: 'neg' as const },
	{ label: 'Input VAT lost', sub: 'On purchases without a CU number', value: x.value.input_vat_lost, display: t.moneyC(x.value.input_vat_lost), tone: 'warn' as const },
])
const reasons = computed(() => props.tab.failure_reasons.map((r) => ({ label: r.label, value: r.count, display: t.count(r.count) })))
const channels = computed(() => props.tab.by_channel.map((r) => ({ label: r.label, value: r.count, display: t.count(r.count) })))
</script>

<template>
	<div class="space-y-4">
		<div class="grid gap-4 lg:grid-cols-2">
			<TaxCard title="Purchase coverage by week" subtitle="Invoices with a valid CU number, share of all purchase invoices" meta="12 weeks">
				<TaxChart :config="trend" class="h-64" />
			</TaxCard>
			<TaxCard title="What non-compliance costs" subtitle="Computed from purchase invoices without an eTIMS invoice" :meta="`Total ${t.moneyC(x.total)}`">
				<TaxCallout :big="t.moneyC(x.income_tax_disallowance)" title="Deduction at risk">
					Expense without an eTIMS invoice is not deductible; the tax effect is computed on {{ t.moneyC(x.spend_without_invoice) }} of spend.
				</TaxCallout>
				<div class="mt-4"><RankedBars :rows="costs" /></div>
			</TaxCard>
		</div>
		<TaxCard title="Exception queue" subtitle="Sorted by tax exposure" :meta="`${tab.exceptions.length} of ${tab.exception_total}`">
			<TaxTable
				caption="eTIMS exceptions"
				:cols="[
					{ key: 'document', label: 'Document' },
					{ key: 'counterparty', label: 'Counterparty' },
					{ key: 'amount', label: 'Amount', kind: 'money', right: true },
					{ key: 'issue_chip', label: 'Issue', kind: 'chip' },
					{ key: 'age_days', label: 'Age', kind: 'days', right: true },
					{ key: 'exposure', label: 'Exposure', kind: 'money', right: true },
				]"
				:rows="tab.exceptions"
				:drill-title="(r) => r.document"
			/>
		</TaxCard>
		<div class="grid gap-4" :class="channels.length ? 'lg:grid-cols-3' : 'lg:grid-cols-2'">
			<TaxCard title="Failure reasons" subtitle="Open exceptions">
				<RankedBars v-if="reasons.length" :rows="reasons" />
				<p v-else class="py-6 text-center text-sm text-ink-gray-6">No open exceptions.</p>
			</TaxCard>
			<TaxCard v-if="channels.length" title="Failure by eTIMS channel" subtitle="Open exceptions">
				<RankedBars :rows="channels" />
			</TaxCard>
			<TaxCard title="Penalty reference" subtitle="Tax Procedures Act">
				<TaxTable
					caption="Penalty reference"
					:cols="[{ key: 'breach', label: 'Breach' }, { key: 'penalty', label: 'Penalty' }]"
					:rows="tab.penalty_reference"
				/>
			</TaxCard>
		</div>
	</div>
</template>
