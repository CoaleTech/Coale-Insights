<template>
	<div class="space-y-6">
		<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
			<!-- P&L Summary -->
			<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
				<SectionHeader title="Profit & Loss Summary (YTD)" :level="3" />
				<div class="mt-4 space-y-3">
					<div class="flex justify-between items-center">
						<span class="text-ink-gray-6">Total Revenue</span>
						<span class="font-medium text-ink-gray-9">{{ formatCurrency(data.ytd_revenue, currency) }}</span>
					</div>
					<div class="flex justify-between items-center">
						<span class="text-ink-gray-6">Total Expenses</span>
						<span class="font-medium text-ink-gray-9">{{ formatCurrency(data.ytd_expenses, currency) }}</span>
					</div>
					<div class="flex justify-between items-center border-t border-outline-gray-1 pt-2">
						<span class="font-medium text-ink-gray-9">Net Profit</span>
						<span :class="deltaInk(data.ytd_profit, { higherIsBetter: true })" class="font-bold">
							{{ formatCurrency(data.ytd_profit, currency) }}
						</span>
					</div>
					<div class="flex justify-between items-center">
						<span class="text-ink-gray-6">Profit Margin</span>
						<span class="font-medium text-ink-gray-9">{{ data.net_margin }}%</span>
					</div>
				</div>
			</div>

			<!-- Monthly Revenue Trend -->
			<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
				<SectionHeader title="Monthly Revenue Trend" :level="3" />
				<IntelligenceChart v-if="data.monthly_trend?.length" class="mt-4 h-48 sm:h-56 lg:h-64" :config="revenueTrendConfig" />
				<div v-else class="h-48 flex items-center justify-center text-ink-gray-6">
					No revenue data available
				</div>
				<table v-if="data.monthly_trend?.length" class="sr-only">
					<caption>Monthly revenue</caption>
					<thead>
						<tr>
							<th scope="col">Month</th>
							<th scope="col">Revenue</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="month in data.monthly_trend" :key="month.period">
							<th scope="row">{{ formatPeriod(month.period) }}</th>
							<td>{{ formatCurrency(month.revenue, currency) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>

		<!-- Expense Breakdown -->
		<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
			<SectionHeader title="Expense Breakdown" :level="3" />
			<div class="mt-4 overflow-x-auto">
				<table class="min-w-full">
					<thead>
						<tr class="bg-surface-gray-1">
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Category</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Amount</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">% of Total</th>
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Share</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-outline-gray-1">
						<tr v-for="expense in data.expense_breakdown" :key="expense.category">
							<td class="px-4 py-3 font-medium text-ink-gray-9">{{ expense.category }}</td>
							<td class="px-4 py-3 text-right text-sm font-medium text-ink-gray-9">
								{{ formatCurrency(expense.amount, currency) }}
							</td>
							<td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ expense.pct }}%</td>
							<td class="px-4 py-3 w-32">
								<div class="bg-surface-gray-2 rounded-full h-2 overflow-hidden">
									<div
										class="bg-surface-red-5 h-full rounded-full"
										:style="{ width: `${expense.pct}%` }"
										role="img"
										:aria-label="`${expense.pct}% of total expenses`"
									></div>
								</div>
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
import IntelligenceChart from '../../intelligence/components/IntelligenceChart.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import { deltaInk } from '../../utils/status'
import { themeColor } from '../../utils/chartTheme'
import { formatCurrency, formatPeriod } from './format'
import type { OverviewData } from './types'

const props = defineProps<{
	data: OverviewData
	currency: string
}>()

// Chart configs — ECharts cannot resolve CSS custom properties; use themeColor().
const revenueTrendConfig = computed(() => ({
	title: '',
	data: (props.data.monthly_trend ?? []).map(m => ({
		period: formatPeriod(m.period),
		Revenue: m.revenue,
	})),
	xAxis: { key: 'period', type: 'category' as const },
	yAxis: { title: props.currency },
	series: [{ name: 'Revenue', type: 'area' as const, color: themeColor('--app-pos-fill') }],
}))
</script>
