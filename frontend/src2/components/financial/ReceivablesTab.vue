<template>
	<div class="space-y-6">
		<!-- AR Summary -->
		<div class="grid grid-cols-2 md:grid-cols-3 wide:grid-cols-6 gap-4">
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Total Outstanding</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ formatCurrency(data.total_outstanding, currency) }}</div>
				<div v-if="glBalanceDiffers(data.gl_balance, data.total_outstanding)" class="text-xs text-ink-gray-6">
					GL balance {{ formatCurrency(data.gl_balance, currency) }}
				</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Days Sales Outstanding</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ formatDays(data.current_dso) }}</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Invoice Count</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ data.invoice_count }}</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Avg Overdue Days</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ formatDays(data.avg_overdue_days) }}</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Avg Invoice Age</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ formatDays(data.avg_open_receivable_age_days) }}</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1 cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
				 role="button"
				 tabindex="0"
				 @click="open90Plus"
				 @keydown.enter="open90Plus"
				 @keydown.space.prevent="open90Plus">
				<div class="text-sm text-ink-gray-6">90+ Days Overdue</div>
				<div class="text-xl font-bold" :class="deltaInk(-1, { higherIsBetter: true })">
					{{ formatCurrency(get90PlusOverdue(data.aging_buckets), currency) }}
				</div>
			</div>
		</div>

		<!-- Aging Analysis -->
		<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
			<SectionHeader variant="caption" title="Accounts Receivable Aging" :level="3" />
			<IntelligenceChart v-if="data.aging_buckets?.length" class="mt-4 h-80" :config="arAgingConfig" />
			<table v-if="data.aging_buckets?.length" class="mt-4 w-full text-sm">
				<caption class="sr-only">Accounts receivable by aging bucket</caption>
				<thead>
					<tr class="text-xs uppercase text-ink-gray-6">
						<th scope="col" class="px-3 py-2 text-left font-medium">Bucket</th>
						<th scope="col" class="px-3 py-2 text-right font-medium">Amount</th>
						<th scope="col" class="px-3 py-2 text-right font-medium">Invoices</th>
						<th scope="col" class="px-3 py-2 text-right font-medium">% of AR</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-outline-gray-1">
					<tr v-for="bucket in agingRows.rows" :key="bucket.bucket">
						<th scope="row" class="px-3 py-2 text-left font-normal text-ink-gray-9">{{ bucket.bucket }}</th>
						<td class="px-3 py-2 text-right text-ink-gray-9">{{ formatCurrency(bucket.amount, currency) }}</td>
						<td class="px-3 py-2 text-right text-ink-gray-7">{{ bucket.count }}</td>
						<td class="px-3 py-2 text-right text-ink-gray-7">{{ bucket.share === null ? NO_VALUE : formatPercent(bucket.share) }}</td>
					</tr>
				</tbody>
				<tfoot>
					<tr class="border-t border-outline-gray-2 font-semibold text-ink-gray-9">
						<th scope="row" class="px-3 py-2 text-left">Total</th>
						<td class="px-3 py-2 text-right">{{ formatCurrency(agingRows.amount, currency) }}</td>
						<td class="px-3 py-2 text-right">{{ agingRows.count }}</td>
						<td class="px-3 py-2 text-right">{{ agingRows.amount > 0 ? formatPercent(100) : NO_VALUE }}</td>
					</tr>
				</tfoot>
			</table>
		</div>

		<!-- Collections -->
		<div v-if="data.collection_trend?.length" class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
			<SectionHeader variant="caption" title="Monthly Collections" hint="Receipts applied to invoices; advances not included" :level="3" />
			<IntelligenceChart class="mt-4 h-80" :config="collectionTrendConfig" />
			<table class="sr-only">
				<caption>Receipts applied to invoices per month</caption>
				<thead>
					<tr>
						<th scope="col">Month</th>
						<th scope="col">Collected</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="row in data.collection_trend" :key="row.period">
						<th scope="row">{{ formatPeriod(row.period) }}</th>
						<td>{{ formatCurrency(row.collected, currency) }}</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- Top Debtors -->
		<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
			<SectionHeader variant="caption" title="Top Overdue Customers" :level="3" />
			<div class="mt-4 overflow-x-auto">
				<table class="min-w-full">
					<thead>
						<tr class="bg-surface-gray-1">
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Customer</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Overdue</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Invoices</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Days Overdue</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-outline-gray-1">
						<tr v-for="customer in data.overdue_customers?.slice(0, 10)" :key="customer.customer"
							class="cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
							role="button"
							tabindex="0"
							@click="openCustomer(customer)"
							@keydown.enter="openCustomer(customer)"
							@keydown.space.prevent="openCustomer(customer)">
							<td class="px-4 py-3 font-medium text-ink-gray-9">{{ customer.customer_name || customer.customer }}</td>
							<td class="px-4 py-3 text-right text-sm font-medium text-ink-gray-9">
								{{ formatCurrency(customer.total_outstanding, currency) }}
							</td>
							<td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ customer.invoice_count }}</td>
							<td class="px-4 py-3 text-right">
								<!-- DSO: good <= 30, warn <= 60, higherIsBetter: false -->
								<Badge v-bind="severityBadge(scoreSeverity(customer.max_overdue_days, { good: 30, warn: 60, higherIsBetter: false }))"
									   :label="`${customer.max_overdue_days} days`" size="sm" />
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import IntelligenceChart from '../../intelligence/components/IntelligenceChart.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import { deltaInk, severityBadge, scoreSeverity } from '../../utils/status'
import { themeColor } from '../../utils/chartTheme'
import type { useDrillDown } from '../../intelligence/composables/useDrillDown'
import { formatDays, formatPeriod, get90PlusOverdue, glBalanceDiffers } from './format'
import { formatMoney as formatCurrency, formatPercent, NO_VALUE } from '../../utils/format'
import type { OverdueCustomerRow, ReceivablesData } from './types'

const props = defineProps<{
	data: ReceivablesData
	currency: string
	finEndpoint: string
	drillDown: ReturnType<typeof useDrillDown>
}>()

/** Aging buckets with each one's share of the bucket total, plus the totals. */
const agingRows = computed(() => {
	const buckets = props.data.aging_buckets ?? []
	const amount = buckets.reduce((s, b) => s + Number(b.amount), 0)
	const count = buckets.reduce((s, b) => s + Number(b.count), 0)
	return {
		amount,
		count,
		rows: buckets.map(b => ({ ...b, share: amount > 0 ? (Number(b.amount) / amount) * 100 : null })),
	}
})

const arAgingConfig = computed(() => ({
	title: '',
	data: (props.data.aging_buckets ?? []).map(b => ({
		bucket: b.bucket,
		Amount: b.amount,
	})),
	xAxis: { key: 'bucket', type: 'category' as const },
	yAxis: { title: props.currency, yMin: 0 },
	series: [{ name: 'Amount', type: 'bar' as const, color: themeColor('--app-info-fill') }],
}))

const collectionTrendConfig = computed(() => ({
	title: '',
	data: (props.data.collection_trend ?? []).map(r => ({
		period: formatPeriod(r.period),
		Collected: r.collected,
	})),
	xAxis: { key: 'period', type: 'category' as const },
	yAxis: { title: props.currency, yMin: 0 },
	series: [{ name: 'Collected', type: 'bar' as const, color: themeColor('--app-pos-fill') }],
}))

const open90Plus = () =>
	props.drillDown.open(props.finEndpoint, 'Overdue 90+ Days AR', { metric: 'overdue_ar_90' })

const openCustomer = (c: OverdueCustomerRow) =>
	props.drillDown.open(props.finEndpoint, (c.customer_name || c.customer) + ' AR', {
		metric: 'top_customers_ar',
		customer: c.customer,
	})
</script>
