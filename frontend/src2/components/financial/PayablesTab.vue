<template>
	<div class="space-y-6">
		<!-- AP Summary -->
		<div class="grid grid-cols-1 md:grid-cols-4 gap-4">
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Total Outstanding</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ formatCurrency(data.total_outstanding, currency) }}</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Days Payable Outstanding</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ Math.round(data.current_dpo || 0) }} days</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Invoice Count</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ data.invoice_count }}</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">90+ Days Overdue</div>
				<div class="text-xl font-bold" :class="deltaInk(-1, { higherIsBetter: true })">
					{{ formatCurrency(get90PlusOverdue(data.aging_buckets), currency) }}
				</div>
			</div>
		</div>

		<!-- Aging Analysis -->
		<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
			<SectionHeader title="Accounts Payable Aging" :level="3" />
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

		<!-- Top Creditors -->
		<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
			<SectionHeader title="Top Outstanding Suppliers" :level="3" />
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
							tabindex="0"
							@click="drillDown.open(finEndpoint, (supplier.supplier_name || supplier.supplier) + ' AP', { metric: 'top_suppliers_ap', supplier: supplier.supplier })"
							@keydown.enter="drillDown.open(finEndpoint, (supplier.supplier_name || supplier.supplier) + ' AP', { metric: 'top_suppliers_ap', supplier: supplier.supplier })">
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
import { formatCurrency, get90PlusOverdue } from './format'
import type { PayablesData } from './types'

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
	yAxis: { title: props.currency },
	series: [{ name: 'Amount', type: 'bar' as const, color: themeColor('--app-warn-fill') }],
}))
</script>
