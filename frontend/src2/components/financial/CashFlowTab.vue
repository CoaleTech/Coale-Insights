<template>
	<div class="space-y-6">
		<!-- Cash Position Summary -->
		<div class="grid grid-cols-1 md:grid-cols-4 gap-4">
			<KpiCard label="Current Cash" :amount="data.total_cash" :currency="currency" />
			<KpiCard label="Monthly Inflow" :amount="data.avg_monthly_inflow" :currency="currency" />
			<KpiCard label="Monthly Outflow" :amount="data.avg_monthly_outflow" :currency="currency" />
			<KpiCard
				label="Cash Runway"
				:value="data.runway_months == null ? undefined : Math.round(data.runway_months * 30)"
				unit=" days"
			/>
		</div>

		<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
			<!-- Cash Accounts -->
			<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
				<SectionHeader variant="caption" title="Cash & Bank Accounts" :level="3" />
				<div class="mt-4 space-y-2 max-h-64 overflow-auto">
					<div v-for="acc in data.cash_accounts" :key="acc.account"
						 class="flex items-center justify-between p-2 bg-surface-gray-1 rounded">
						<div>
							<div class="font-medium text-ink-gray-9 text-sm">{{ acc.account_name }}</div>
							<div class="text-xs text-ink-gray-6">{{ acc.account_type }}</div>
						</div>
						<span :class="deltaInk(acc.balance, { higherIsBetter: true })" class="font-medium">
							{{ formatCurrency(acc.balance, currency) }}
						</span>
					</div>
				</div>
			</div>

			<!-- Monthly Inflows -->
			<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
				<SectionHeader variant="caption" title="Monthly Cash Inflows" :level="3" />
				<IntelligenceChart v-if="data.monthly_inflows?.length" class="mt-4 h-48 sm:h-56 lg:h-64" :config="cashInflowConfig" />
				<div v-else class="h-48 flex items-center justify-center text-ink-gray-6">
					No inflow data available
				</div>
				<table v-if="data.monthly_inflows?.length" class="sr-only">
					<caption>Monthly cash inflows</caption>
					<thead>
						<tr>
							<th scope="col">Month</th>
							<th scope="col">Inflow</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="month in data.monthly_inflows" :key="month.period">
							<th scope="row">{{ formatPeriod(month.period) }}</th>
							<td>{{ formatCurrency(month.amount, currency) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import { deltaInk } from '../../utils/status'
import { themeColor } from '../../utils/chartTheme'
import { formatPeriod } from './format'
import { formatMoney as formatCurrency } from '../../utils/format'
import type { CashFlowData } from './types'

const props = defineProps<{
	data: CashFlowData
	currency: string
}>()

const cashInflowConfig = computed(() => ({
	title: '',
	data: (props.data.monthly_inflows ?? []).map(m => ({
		period: formatPeriod(m.period),
		Inflow: m.amount,
	})),
	xAxis: { key: 'period', type: 'category' as const },
	yAxis: { title: props.currency },
	series: [{ name: 'Inflow', type: 'bar' as const, color: themeColor('--app-pos-fill') }],
}))
</script>
