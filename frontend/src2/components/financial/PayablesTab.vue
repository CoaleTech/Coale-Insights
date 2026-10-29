<template>
	<div class="space-y-6">
		<!-- AP Summary -->
		<div class="grid grid-cols-2 md:grid-cols-3 wide:grid-cols-6 gap-4">
			<KpiCard
				label="Total Outstanding"
				:amount="data.total_outstanding"
				:currency="currency"
				:sublabel="glBalanceDiffers(data.gl_balance, data.total_outstanding) ? `GL balance ${formatCurrency(data.gl_balance, currency)}` : undefined"
			/>
			<KpiCard
				label="Days Payable Outstanding"
				:value="formatDays(data.current_dpo)"
			/>
			<KpiCard
				label="Invoice Count"
				:value="data.invoice_count ?? null"
			/>
			<KpiCard
				label="Avg Overdue Days"
				:value="formatDays(data.avg_overdue_days)"
			/>
			<KpiCard
				label="Avg Invoice Age"
				:value="formatDays(data.avg_open_payable_age_days)"
			/>
			<KpiCard
				label="90+ Days Overdue"
				:amount="get90PlusOverdue(data.aging_buckets)"
				:currency="currency"
				:severity="get90PlusOverdue(data.aging_buckets) > 0 ? 'high' : undefined"
				:clickable="true"
				@click="open90Plus"
			/>
		</div>

		<!-- 7-day cash adequacy bridge + concentration: arithmetic on payload fields only -->
		<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
			<div v-if="bridge" class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
				<SectionHeader variant="caption" title="7-Day Cash Adequacy Bridge" hint="Liquid cash and fixed deposits against invoices due within 7 days" :level="3" />
				<div class="mt-4 space-y-3">
					<div v-for="row in bridge.rows" :key="row.label" class="grid grid-cols-[9rem_1fr_auto] sm:grid-cols-[12rem_1fr_auto] items-center gap-3 text-sm">
						<span class="text-ink-gray-7">{{ row.label }}</span>
						<div class="h-3 bg-surface-gray-2 rounded-full overflow-hidden" role="img" :aria-label="`${row.label}: ${row.text}`">
							<div :class="['h-full rounded-full', row.fill]" :style="{ width: `${row.pct}%` }" />
						</div>
						<span class="tnum text-right font-medium text-ink-gray-9">{{ row.text }}</span>
					</div>
				</div>
				<p class="mt-4 text-sm" :class="bridge.gap > 0 ? 'text-ink-red-3' : 'text-ink-gray-7'">
					{{ bridge.note }}
				</p>
			</div>
			<div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
				<SectionHeader variant="caption" title="AP Concentration and Aging Health" :level="3" />
				<dl class="mt-4 space-y-3 text-sm">
					<div v-for="f in concentration" :key="f.label" class="flex items-baseline justify-between gap-4">
						<dt class="text-ink-gray-7">{{ f.label }}</dt>
						<dd class="tnum text-right font-medium text-ink-gray-9">{{ f.value }}</dd>
					</div>
				</dl>
			</div>
		</div>

		<!-- Aging Analysis -->
		<div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
			<SectionHeader variant="caption" title="Accounts Payable Aging" :level="3" />
			<IntelligenceChart v-if="data.aging_buckets?.length" class="mt-4 h-80" :config="apAgingConfig" />
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
			<div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
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

			<div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
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
		<div class="bg-surface-white rounded-lg p-6 border border-outline-gray-1">
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
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import { themeColor } from '../../utils/chartTheme'
import type { useDrillDown } from '../../intelligence/composables/useDrillDown'
import { formatDate, formatDays, get90PlusOverdue, glBalanceDiffers } from './format'
import { formatMoney as formatCurrency, formatPercent, NO_VALUE } from '../../utils/format'
import type { CashFlowData, PayablesData, TopSupplierRow } from './types'

const props = defineProps<{
	data: PayablesData
	currency: string
	finEndpoint: string
	drillDown: ReturnType<typeof useDrillDown>
	cashFlow?: CashFlowData
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

const bridge = computed(() => {
	const cash = props.cashFlow
	if (cash?.liquid_cash == null || !Number.isFinite(Number(cash.liquid_cash))) return null
	const liquid = Number(cash.liquid_cash)
	const fd = Number(cash.fd_balance) || 0
	const due = (props.data.upcoming_payments ?? [])
		.filter(b => b.days_until_due <= 7)
		.reduce((s, b) => s + Number(b.outstanding_amount), 0)
	const net = liquid + fd - due
	const gap = Math.max(due - liquid, 0)
	const scale = Math.max(Math.abs(liquid), fd, due, Math.abs(net)) || 1
	const money = (n: number) => formatCurrency(n, props.currency)
	const row = (label: string, amount: number, fill: string, text: string) => ({
		label, fill, text, pct: Math.min(Math.abs(amount) / scale * 100, 100),
	})
	return {
		gap,
		rows: [
			row('Liquid cash', liquid, liquid >= 0 ? 'bg-pos-fill' : 'bg-neg-fill', money(liquid)),
			row('Fixed deposits', fd, 'bg-muted-fill', money(fd)),
			row('Due within 7 days', due, 'bg-warn-fill', `-${money(due)}`),
			row('Net after 7-day payments', net, net >= 0 ? 'bg-pos-fill' : 'bg-neg-fill', money(net)),
		],
		note: gap > 0
			? `Payments due within 7 days exceed liquid cash by ${money(gap)}. After counting fixed deposits the net is ${money(net)}.`
			: `Liquid cash covers the ${money(due)} due within 7 days.`,
	}
})

const concentration = computed(() => {
	const d = props.data
	const total = Number(d.total_outstanding)
	const top = d.top_suppliers?.[0]
	const bucket = [...(d.aging_buckets ?? [])].sort((a, b) => Number(b.amount) - Number(a.amount))[0]
	const share = (n: number) => (total > 0 ? formatPercent(n / total * 100) : NO_VALUE)
	return [
		{ label: 'Days payable outstanding', value: formatDays(d.current_dpo) },
		{ label: 'Average open invoice age', value: formatDays(d.avg_open_payable_age_days) },
		{ label: 'Average overdue days', value: formatDays(d.avg_overdue_days) },
		{
			label: top ? `Largest supplier: ${top.supplier_name || top.supplier}` : 'Largest supplier',
			value: top ? `${formatCurrency(top.total_outstanding, props.currency)} (${share(Number(top.total_outstanding))} of AP, ${top.invoice_count} invoices)` : NO_VALUE,
		},
		{
			label: bucket ? `Largest aging bucket: ${bucket.bucket}` : 'Largest aging bucket',
			value: bucket ? `${formatCurrency(bucket.amount, props.currency)} (${share(Number(bucket.amount))} of AP)` : NO_VALUE,
		},
	]
})

const open90Plus = () =>
	props.drillDown.open(props.finEndpoint, 'Overdue 90+ Days AP', { metric: 'overdue_ap_90' })

const openSupplier = (s: TopSupplierRow) =>
	props.drillDown.open(props.finEndpoint, (s.supplier_name || s.supplier) + ' AP', {
		metric: 'top_suppliers_ap',
		supplier: s.supplier,
	})
</script>
