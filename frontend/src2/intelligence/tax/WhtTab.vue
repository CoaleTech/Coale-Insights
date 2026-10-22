<script setup lang="ts">
import { computed } from 'vue'
import RankedBars from './RankedBars.vue'
import TaxCallout from './TaxCallout.vue'
import TaxCard from './TaxCard.vue'
import TaxTable from './TaxTable.vue'
import type { WhtData } from './taxTypes'
import { useTax } from './useTax'

const props = defineProps<{ tab: WhtData }>()
const t = useTax()

const byType = computed(() =>
	props.tab.by_type.map((b) => ({ label: b.label, sub: b.note, value: b.amount, display: t.moneyC(b.amount) })),
)
// "5 of 12" only when the list was capped.
const shown = (n: number, total?: number) => (total !== undefined && total > n ? `${n} of ${total}` : undefined)
const cardFees = computed(() => (props.tab.watch.card_fees_amount === null ? undefined : t.moneyC(props.tab.watch.card_fees_amount)))
</script>

<template>
	<div class="space-y-4">
		<div class="grid gap-4 lg:grid-cols-2">
			<TaxCard title="Withholding by payment type" subtitle="Withheld, period to date">
				<RankedBars v-if="byType.length" :rows="byType" />
				<p v-else class="py-6 text-center text-sm text-ink-gray-6">No withholding postings in this period.</p>
			</TaxCard>
			<TaxCard title="Unremitted past the 5 working-day rule" subtitle="Deduction date to remittance" :meta="shown(tab.unremitted.length, tab.unremitted_total)">
				<TaxTable
					caption="Unremitted withholding"
					:cols="[
						{ key: 'payment', label: 'Payment' },
						{ key: 'payee', label: 'Payee' },
						{ key: 'withheld', label: 'Withheld', kind: 'money', right: true },
						{ key: 'deducted_on', label: 'Deducted', kind: 'date' },
						{ key: 'due_on', label: 'Due', kind: 'date' },
						{ key: 'chip', label: 'Days late', kind: 'chip' },
					]"
					:rows="tab.unremitted"
					:drill-title="(r) => r.payment"
					empty="No withholding is past the 5 working-day rule."
				/>
			</TaxCard>
		</div>
		<div class="grid gap-4 lg:grid-cols-2">
			<TaxCard title="Payments where the rate looks wrong" subtitle="Expected rate from payee residency and payment type" :meta="shown(tab.rate_exceptions.length, tab.rate_exceptions_total)">
				<TaxTable
					caption="Withholding rate exceptions"
					:cols="[
						{ key: 'payment', label: 'Payment' },
						{ key: 'payee', label: 'Payee' },
						{ key: 'gross', label: 'Gross', kind: 'money', right: true },
						{ key: 'expected_rate', label: 'Expected', kind: 'pct', right: true },
						{ key: 'chip', label: 'Applied', kind: 'chip' },
					]"
					:rows="tab.rate_exceptions"
					:drill-title="(r) => r.payment"
					empty="No rate exceptions found."
				/>
			</TaxCard>
			<TaxCard title="Rate card in force" subtitle="Percent of gross payment">
				<TaxTable
					caption="Withholding rate card"
					:cols="[
						{ key: 'payment', label: 'Payment' },
						{ key: 'resident', label: 'Resident', kind: 'pct', right: true },
						{ key: 'non_resident', label: 'Non-resident', kind: 'pct', right: true },
					]"
					:rows="tab.rate_card"
				/>
			</TaxCard>
		</div>
		<TaxCallout :big="cardFees">{{ tab.watch.note }}</TaxCallout>
	</div>
</template>
