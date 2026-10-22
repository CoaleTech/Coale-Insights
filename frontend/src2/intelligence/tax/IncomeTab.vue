<script setup lang="ts">
import { computed } from 'vue'
import RankedBars from './RankedBars.vue'
import TaxCard from './TaxCard.vue'
import TaxChart from './TaxChart.vue'
import TaxTable from './TaxTable.vue'
import TaxTimeline from './TaxTimeline.vue'
import { axisConfig } from './taxCharts'
import type { IncomeData } from './taxTypes'
import { useTax } from './useTax'

const props = defineProps<{ tab: IncomeData }>()
const t = useTax()

const chart = computed(() =>
	axisConfig(
		props.tab.instalments.map((i) => ({ label: i.label, Required: i.required, Paid: i.paid })),
		'label',
		[{ name: 'Required' }, { name: 'Paid' }],
		{ title: t.amountTitle() },
	),
)
// Add-backs raise taxable profit (amber), reliefs lower it (green).
const bridge = computed(() =>
	props.tab.bridge.map((b) => {
		const mag = b.amount === null ? null : Math.abs(b.amount)
		const sign = b.kind === 'add' ? '+' : b.kind === 'less' ? '\u2212' : ''
		return {
			label: b.label,
			value: mag,
			display: mag === null ? '-' : `${sign}${t.moneyC(mag)}`,
			tone: b.kind === 'add' ? ('warn' as const) : b.kind === 'less' ? ('pos' as const) : ('acc' as const),
		}
	}),
)
const credits = computed(() => [
	{ label: 'Credits on certificates', value: props.tab.wht_credits.matched, display: t.moneyC(props.tab.wht_credits.matched) },
	{ label: 'Credits not yet matched', value: props.tab.wht_credits.unmatched, display: t.moneyC(props.tab.wht_credits.unmatched), tone: 'warn' as const },
])
const base = computed(() => props.tab.instalment_base)
const totPct = computed(() => {
	const p = props.tab.tot.pct_of_ceiling
	return p === null ? null : Math.max(0, Math.min(100, p))
})
</script>

<template>
	<div class="space-y-4">
		<div class="grid gap-4 lg:grid-cols-2">
			<TaxCard title="Instalment tax: required vs paid" subtitle="Four instalments in the financial year">
				<TaxChart :config="chart" class="mb-4 h-64" />
				<TaxTable
					caption="Instalment status"
					:cols="[
						{ key: 'label', label: 'Instalment' },
						{ key: 'due_date', label: 'Due', kind: 'date' },
						{ key: 'chip', label: 'Status', kind: 'chip' },
					]"
					:rows="tab.instalments"
				/>
				<p v-if="base" class="mt-2 text-xs text-ink-gray-6">
					Annual instalment base {{ t.moneyC(base.annual_required) }} (prior-year tax {{ t.moneyC(base.prior_year_tax) }}, current estimate {{ t.moneyC(base.current_estimate) }}).
				</p>
			</TaxCard>
			<TaxCard title="Taxable profit bridge" subtitle="Financial year to date, before tax">
				<RankedBars v-if="bridge.length" :rows="bridge" />
				<p v-else class="py-6 text-center text-sm text-ink-gray-6">No profit data for this year.</p>
			</TaxCard>
		</div>
		<div class="grid gap-4 lg:grid-cols-3">
			<TaxCard class="lg:col-span-2" title="Tax loss ledger" subtitle="A loss can be used for 5 years from the year it arose">
				<TaxTable
					caption="Tax loss ledger"
					:cols="[
						{ key: 'year', label: 'Year of loss' },
						{ key: 'amount', label: 'Amount', kind: 'money', right: true },
						{ key: 'used', label: 'Used', kind: 'money', right: true },
						{ key: 'remaining', label: 'Remaining', kind: 'money', right: true },
						{ key: 'chip', label: 'Lapses', kind: 'chip' },
					]"
					:rows="tab.losses"
					empty="No tax losses found."
				/>
			</TaxCard>
			<TaxCard title="Turnover tax monitor" subtitle="Small business units on TOT">
				<template v-if="tab.tot.applicable">
					<p class="text-sm text-ink-gray-8">
						Trailing 12 months turnover <strong>{{ t.moneyC(tab.tot.trailing_12m_turnover) }}</strong> of the {{ t.moneyC(tab.tot.ceiling) }} ceiling
					</p>
					<div
						class="mt-2 h-2.5 rounded-full bg-surface-gray-2"
						role="progressbar"
						aria-label="Turnover as a share of the TOT ceiling"
						:aria-valuenow="totPct ?? undefined"
						aria-valuemin="0"
						aria-valuemax="100"
					>
						<div class="h-full rounded-full bg-accent" :style="{ width: `${totPct ?? 0}%` }" />
					</div>
					<p class="tnum mt-1 text-xs text-ink-gray-6">{{ t.pct(tab.tot.pct_of_ceiling) }} of ceiling</p>
				</template>
				<p class="mt-3 text-sm text-ink-gray-6">{{ tab.tot.note }}</p>
			</TaxCard>
		</div>
		<div class="grid gap-4 lg:grid-cols-3">
			<TaxCard title="Key dates" subtitle="Financial year end">
				<TaxTimeline :items="tab.key_dates" empty="No key dates." />
			</TaxCard>
			<TaxCard title="Withholding credits" subtitle="Offsets the balance due">
				<RankedBars :rows="credits" />
			</TaxCard>
			<TaxCard title="Capital gains" subtitle="Not part of the instalment base">
				<TaxTable
					caption="Capital gains on disposals"
					:cols="[
						{ key: 'disposal', label: 'Disposal' },
						{ key: 'gain', label: 'Gain', kind: 'money', right: true },
						{ key: 'cgt', label: 'CGT', kind: 'money', right: true },
					]"
					:rows="tab.cgt"
					empty="No asset disposals in this period."
				/>
			</TaxCard>
		</div>
		<ul v-if="tab.notes?.length" class="list-disc space-y-1 pl-5 text-xs text-ink-gray-6">
			<li v-for="n in tab.notes" :key="n">{{ n }}</li>
		</ul>
	</div>
</template>
