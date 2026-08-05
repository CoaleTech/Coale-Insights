<template>
	<div class="space-y-6">
		<!-- AR Summary -->
		<div class="grid grid-cols-1 md:grid-cols-4 gap-4">
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Total Outstanding</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ formatCurrency(data.total_outstanding, currency) }}</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Days Sales Outstanding</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ Math.round(data.current_dso || 0) }} days</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Invoice Count</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ data.invoice_count }}</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1 cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
				 @click="drillDown.open(finEndpoint, 'Overdue 90+ Days AR', { metric: 'overdue_ar_90' })">
				<div class="text-sm text-ink-gray-6">90+ Days Overdue</div>
				<div class="text-xl font-bold" :class="deltaInk(-1, { higherIsBetter: true })">
					{{ formatCurrency(get90PlusOverdue(data.aging_buckets), currency) }}
				</div>
			</div>
		</div>

		<!-- Aging Analysis -->
		<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
			<SectionHeader variant="caption" title="Accounts Receivable Aging" :level="3" />
			<IntelligenceChart v-if="data.aging_buckets?.length" class="mt-4 h-44 sm:h-52 lg:h-56" :config="arAgingConfig" />
			<table v-if="data.aging_buckets?.length" class="sr-only">
				<caption>Accounts receivable by aging bucket</caption>
				<thead>
					<tr>
						<th scope="col">Bucket</th>
						<th scope="col">Amount</th>
						<th scope="col">Invoices</th>
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

		<!-- Top Debtors -->
		<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
			<SectionHeader variant="caption" title="Top Outstanding Customers" :level="3" />
			<div class="mt-4 overflow-x-auto">
				<table class="min-w-full">
					<thead>
						<tr class="bg-surface-gray-1">
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Customer</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Outstanding</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Invoices</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Days Overdue</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-outline-gray-1">
						<tr v-for="customer in data.overdue_customers?.slice(0, 10)" :key="customer.customer"
							class="cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
							tabindex="0"
							@click="drillDown.open(finEndpoint, (customer.customer_name || customer.customer) + ' AR', { metric: 'top_customers_ar', customer: customer.customer })"
							@keydown.enter="drillDown.open(finEndpoint, (customer.customer_name || customer.customer) + ' AR', { metric: 'top_customers_ar', customer: customer.customer })">
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
import { get90PlusOverdue } from './format'
import { formatMoney as formatCurrency } from '../../utils/format'
import type { ReceivablesData } from './types'

const props = defineProps<{
	data: ReceivablesData
	currency: string
	finEndpoint: string
	drillDown: ReturnType<typeof useDrillDown>
}>()

const arAgingConfig = computed(() => ({
	title: '',
	data: (props.data.aging_buckets ?? []).map(b => ({
		bucket: b.bucket,
		Amount: b.amount,
	})),
	xAxis: { key: 'bucket', type: 'category' as const },
	yAxis: { title: props.currency },
	series: [{ name: 'Amount', type: 'bar' as const, color: themeColor('--app-info-fill') }],
}))
</script>
