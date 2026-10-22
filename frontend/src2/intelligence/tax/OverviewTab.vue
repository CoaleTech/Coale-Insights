<script setup lang="ts">
import { computed } from 'vue'
import { NO_VALUE } from '../../utils/format'
import RankedBars from './RankedBars.vue'
import TaxCard from './TaxCard.vue'
import TaxChart from './TaxChart.vue'
import TaxTable from './TaxTable.vue'
import TaxTimeline from './TaxTimeline.vue'
import { axisConfig } from './taxCharts'
import type { OverviewData } from './taxTypes'
import { periodLabel, useTax } from './useTax'

const props = defineProps<{ tab: OverviewData }>()
const t = useTax()

const amnesty = computed(() => props.tab.amnesty)
// Ring needs both figures; with either unknown it shows `-` rather than 0%.
const paidPct = computed(() => {
	const { principal_paid: paid, principal_total: total } = amnesty.value
	return paid !== null && total !== null && total > 0 ? Math.min(100, (paid / total) * 100) : null
})
const RING = 2 * Math.PI * 28
const dash = computed(() => `${((paidPct.value ?? 0) / 100) * RING} ${RING}`)

const liabilities = computed(() =>
	props.tab.liabilities.map((l) => ({ label: l.label, value: l.amount, display: t.moneyC(l.amount) })),
)
const unpaid = computed(() =>
	amnesty.value.by_tax.map((b) => ({ label: b.tax, value: b.amount, display: t.moneyC(b.amount), tone: 'neg' as const })),
)
const dueVsPaid = computed(() =>
	axisConfig(
		props.tab.monthly.map((m) => ({ month: periodLabel(m.month), Due: m.due, Paid: m.paid })),
		'month',
		[{ name: 'Due' }, { name: 'Paid' }],
		{ title: t.amountTitle() },
	),
)
</script>

<template>
	<div class="space-y-4">
		<div class="grid gap-4 lg:grid-cols-5">
			<TaxCard class="lg:col-span-3" title="Next 30 days" subtitle="Deadlines from Kenya rules; amounts from the tabs">
				<TaxTimeline :items="tab.deadlines" show-amount />
			</TaxCard>
			<TaxCard class="lg:col-span-2" title="Amnesty tracker" :subtitle="`Principal up to ${t.date(amnesty.scope_end)}`" :meta="amnesty.days_left === null ? undefined : `${amnesty.days_left} days left`" highlight>
				<div class="flex items-center gap-4">
					<div v-if="paidPct !== null" class="relative h-16 w-16 shrink-0">
						<svg viewBox="0 0 64 64" class="h-16 w-16 -rotate-90" aria-hidden="true">
							<circle cx="32" cy="32" r="28" fill="none" stroke-width="7" style="stroke: var(--outline-gray-2)" />
							<circle cx="32" cy="32" r="28" fill="none" stroke-width="7" stroke-linecap="round" class="stroke-pos-fill" :stroke-dasharray="dash" />
						</svg>
						<span class="tnum absolute inset-0 flex items-center justify-center text-sm font-semibold text-ink-gray-9">
							{{ paidPct === null ? NO_VALUE : `${Math.round(paidPct)}%` }}
						</span>
					</div>
					<p class="text-sm text-ink-gray-8">
						<template v-if="amnesty.principal_total === null">No disputed principal in scope is recorded on this site.</template>
						<template v-else-if="paidPct !== null">
							<strong>{{ t.moneyC(amnesty.principal_paid) }}</strong> of {{ t.moneyC(amnesty.principal_total) }} principal paid.
						</template>
						<template v-else>
							<strong>{{ t.moneyC(amnesty.principal_total) }}</strong> principal in scope. Payments against disputed assessments are not recorded, so progress is not shown.
						</template>
						<span class="block text-xs text-ink-gray-6">
							Interest and penalties are waived only if the principal is fully paid by {{ t.date(amnesty.deadline) }}.
						</span>
					</p>
				</div>
				<template v-if="amnesty.principal_total !== null">
					<p class="mb-2 mt-4 text-sm font-semibold text-ink-gray-9">Principal still unpaid, {{ t.moneyC(amnesty.principal_outstanding) }}</p>
					<RankedBars v-if="unpaid.length" :rows="unpaid" />
					<p class="mt-3 rounded-md bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-7">
						Interest and penalties waived if cleared: <strong>{{ t.moneyC(amnesty.penalty_interest_waivable) }}</strong>
					</p>
				</template>
			</TaxCard>
		</div>
		<div class="grid gap-4 lg:grid-cols-3">
			<TaxCard title="Liability by tax type" subtitle="Open obligations, current cycle">
				<RankedBars v-if="liabilities.length" :rows="liabilities" />
				<p v-else class="py-6 text-center text-sm text-ink-gray-6">No open obligations.</p>
			</TaxCard>
			<TaxCard title="Tax due vs paid by month" meta="Last 12 months">
				<TaxChart :config="dueVsPaid" class="h-64" />
			</TaxCard>
			<TaxCard title="Filing status" subtitle="Last cycle, from payment evidence">
				<TaxTable
					caption="Filing status by obligation"
					:cols="[
						{ key: 'obligation', label: 'Obligation' },
						{ key: 'period', label: 'Period' },
						{ key: 'due', label: 'Due', kind: 'date' },
						{ key: 'chip', label: 'Status', kind: 'chip' },
					]"
					:rows="tab.filing_status"
				/>
			</TaxCard>
		</div>
	</div>
</template>
