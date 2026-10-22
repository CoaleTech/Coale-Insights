<script setup lang="ts">
import { computed } from 'vue'
import RankedBars from './RankedBars.vue'
import TaxCard from './TaxCard.vue'
import TaxChart from './TaxChart.vue'
import TaxTable from './TaxTable.vue'
import { axisConfig } from './taxCharts'
import type { PayrollData } from './taxTypes'
import { periodLabel, useTax } from './useTax'

const props = defineProps<{ tab: PayrollData }>()
const t = useTax()

const chart = computed(() =>
	axisConfig(
		props.tab.monthly.map((m) => ({ month: periodLabel(m.month), PAYE: m.paye, 'NSSF + SHIF + AHL': m.other })),
		'month',
		[{ name: 'PAYE' }, { name: 'NSSF + SHIF + AHL' }],
		{ title: t.amountTitle() },
	),
)
const slip = computed(() => `${periodLabel(props.tab.month)} payroll`)
const bands = computed(() =>
	props.tab.bands.map((b) => ({ label: b.label, sub: b.rate === null ? null : `${b.rate}%`, value: b.headcount, display: t.count(b.headcount) })),
)
const cost = computed(() => props.tab.cost.map((c) => ({ label: c.label, value: c.amount, display: t.moneyC(c.amount) })))
</script>

<template>
	<div class="space-y-4">
		<div class="grid gap-4 lg:grid-cols-3">
			<TaxCard class="lg:col-span-2" title="Statutory deductions by month" meta="Last 12 months">
				<TaxChart :config="chart" class="h-72" />
			</TaxCard>
			<TaxCard title="Headcount by PAYE band" subtitle="Monthly taxable pay" meta="Employees">
				<RankedBars v-if="bands.length" :rows="bands" />
				<p v-else class="py-6 text-center text-sm text-ink-gray-6">No salary slips in the latest month.</p>
			</TaxCard>
		</div>
		<div class="grid gap-4 lg:grid-cols-2">
			<TaxCard title="Remittance schedule" :subtitle="slip">
				<TaxTable
					caption="Remittance schedule"
					:cols="[
						{ key: 'remittance', label: 'Remittance' },
						{ key: 'rule', label: 'Rule' },
						{ key: 'due_date', label: 'Due', kind: 'date' },
						{ key: 'amount', label: 'Amount', kind: 'money', right: true },
						{ key: 'chip', label: 'Status', kind: 'chip' },
					]"
					:rows="tab.schedule"
				/>
			</TaxCard>
			<TaxCard title="Cost of statutory deductions" :subtitle="slip">
				<RankedBars v-if="cost.length" :rows="cost" />
				<p v-else class="py-6 text-center text-sm text-ink-gray-6">No payroll cost to show.</p>
			</TaxCard>
		</div>
		<TaxCard title="Payroll exceptions" subtitle="Recomputed from rates; every row drills to the Salary Slips">
			<TaxTable
				caption="Payroll exceptions"
				:cols="[
					{ key: 'check', label: 'Check' },
					{ key: 'employees', label: 'Employees', kind: 'count', right: true },
					{ key: 'impact', label: 'Impact' },
				]"
				:rows="tab.exceptions"
				:drill-title="(r) => r.check"
				empty="No exceptions found in the latest payroll."
			>
				<template #cell-impact="{ row }">{{ typeof row.impact === 'number' ? t.money(row.impact) : t.text(row.impact) }}</template>
			</TaxTable>
		</TaxCard>
	</div>
</template>
