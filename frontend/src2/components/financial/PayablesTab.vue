<template>
	<div class="space-y-6">
		<!-- AP Summary -->
		<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Total Outstanding</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ formatCurrency(data.total_outstanding, currency) }}</div>
				<div v-if="glBalanceDiffers(data.gl_balance, data.total_outstanding)" class="text-xs text-ink-gray-6">
					GL balance {{ formatCurrency(data.gl_balance, currency) }}
				</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Days Payable Outstanding</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ formatDays(data.current_dpo) }}</div>
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
				<div class="text-xl font-bold text-ink-gray-9">{{ formatDays(data.avg_open_payable_age_days) }}</div>
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
			<SectionHeader variant="caption" title="Accounts Payable Aging" :level="3" />
			<IntelligenceChart v-if="data.aging_buckets?.length" class="mt-4 h-44 sm:h-52 lg:h-56" :config="apAgingConfig" />
			<table v-if="data.aging_buckets?.length" class="sr-only">
				<caption>Accounts payable by aging bucket</caption>
				<thead>
					<tr>
						<th scope="col">Bucket</th>
						<th scope="col">Amount</th>
						<th scope="col">Bills</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="bucket in data.aging_buckets" :key="bucket.bucket">
						<th scope="row">{{ bucket.bucket }}</th>
						<td>{{ formatCurrency(bucket.amount, currency) }}</td>
						<td>{{ bucket.count }}</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- Due soon + schedule -->
		<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
			<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
				<SectionHeader variant="caption" title="Due Soon" :level="3" />
				<div v-if="data.upcoming_payments?.length" class="mt-4 overflow-x-auto max-h-72 overflow-y-auto">
					<table class="min-w-full">
						<thead>
							<tr class="bg-surface-gray-1">
								<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Supplier</th>
								<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Due</th>
								<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Amount</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-outline-gray-1">
							<tr v-for="bill in data.upcoming_payments" :key="bill.name">
								<td class="px-4 py-3 font-medium text-ink-gray-9">{{ bill.supplier_name || bill.supplier }}</td>
								<td class="px-4 py-3 text-right text-sm text-ink-gray-6">
									{{ formatDate(bill.due_date) }}
									<span class="block text-xs">{{ bill.days_until_due === 0 ? 'today' : `in ${bill.days_until_due} days` }}</span>
								</td>
								<td class="px-4 py-3 text-right text-sm font-medium text-ink-gray-9">
									{{ formatCurrency(bill.outstanding_amount, currency) }}
								</td>
							</tr>
						</tbody>
					</table>
				</div>
				<div v-else class="mt-4 py-4 text-center text-sm text-ink-gray-6">No bills falling due soon</div>
			</div>

			<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
				<SectionHeader variant="caption" title="Payment Schedule" :level="3" />
				<div v-if="data.payment_schedule?.length" class="mt-4 overflow-x-auto">
					<table class="min-w-full">
						<thead>
							<tr class="bg-surface-gray-1">
								<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Period</th>
								<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Bills</th>
								<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Amount</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-outline-gray-1">
							<tr v-for="row in data.payment_schedule" :key="row.period">
								<td class="px-4 py-3 font-medium text-ink-gray-9">{{ row.period }}</td>
								<td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ row.count }}</td>
								<td class="px-4 py-3 text-right text-sm font-medium text-ink-gray-9">
									{{ formatCurrency(row.amount, currency) }}
								</td>
							</tr>
						</tbody>
					</table>
				</div>
				<div v-else class="mt-4 py-4 text-center text-sm text-ink-gray-6">No open bills</div>
			</div>
		</div>

		<!-- Top Creditors -->
		<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
			<SectionHeader variant="caption" title="Top Outstanding Suppliers" :level="3" />
			<div class="mt-4 overflow-x-auto">
				<table class="min-w-full">
					<thead>
						<tr class="bg-surface-gray-1">
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Supplier</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Outstanding</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Invoices</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-outline-gray-1">
						<tr v-for="supplier in data.top_suppliers?.slice(0, 10)" :key="supplier.supplier"
							class="cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
							role="button"
							tabindex="0"
							@click="openSupplier(supplier)"
							@keydown.enter="openSupplier(supplier)"
							@keydown.space.prevent="openSupplier(supplier)">
							<td class="px-4 py-3 font-medium text-ink-gray-9">{{ supplier.supplier_name || supplier.supplier }}</td>
							<td class="px-4 py-3 text-right text-sm font-medium text-ink-gray-9">
								{{ formatCurrency(supplier.total_outstanding, currency) }}
							</td>
							<td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ supplier.invoice_count }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import IntelligenceChart from '../../intelligence/components/IntelligenceChart.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import { deltaInk } from '../../utils/status'
import { themeColor } from '../../utils/chartTheme'
import type { useDrillDown } from '../../intelligence/composables/useDrillDown'
import { formatDate, formatDays, get90PlusOverdue, glBalanceDiffers } from './format'
import { formatMoney as formatCurrency } from '../../utils/format'
import type { PayablesData, TopSupplierRow } from './types'

const props = defineProps<{
	data: PayablesData
	currency: string
	finEndpoint: string
	drillDown: ReturnType<typeof useDrillDown>
}>()

const apAgingConfig = computed(() => ({
	title: '',
	data: (props.data.aging_buckets ?? []).map(b => ({
		bucket: b.bucket,
		Amount: b.amount,
	})),
	xAxis: { key: 'bucket', type: 'category' as const },
	yAxis: { title: props.currency, yMin: 0 },
	series: [{ name: 'Amount', type: 'bar' as const, color: themeColor('--app-warn-fill') }],
}))

const open90Plus = () =>
	props.drillDown.open(props.finEndpoint, 'Overdue 90+ Days AP', { metric: 'overdue_ap_90' })

const openSupplier = (s: TopSupplierRow) =>
	props.drillDown.open(props.finEndpoint, (s.supplier_name || s.supplier) + ' AP', {
		metric: 'top_suppliers_ap',
		supplier: s.supplier,
	})
</script>
