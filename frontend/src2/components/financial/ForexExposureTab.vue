<template>
	<div class="space-y-6">
		<!-- Forex Summary -->
		<div class="grid grid-cols-1 md:grid-cols-4 gap-4">
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Net Forex Exposure</div>
				<div class="text-xl font-bold"
					 :class="deltaInk(data.net_exposure_base, { higherIsBetter: true })">
					{{ formatCurrency(Math.abs(data.net_exposure_base || 0), currency) }}
				</div>
				<div class="text-sm text-ink-gray-6">
					{{ (data.net_exposure_base || 0) >= 0 ? 'Long (Net Receivable)' : 'Short (Net Payable)' }}
				</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Foreign Receivables</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ formatCurrency(data.total_receivable_base || 0, currency) }}</div>
				<div class="text-sm text-ink-gray-6">In base currency ({{ currency }})</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Foreign Payables</div>
				<div class="text-xl font-bold text-ink-gray-9">{{ formatCurrency(data.total_payable_base || 0, currency) }}</div>
				<div class="text-sm text-ink-gray-6">In base currency ({{ currency }})</div>
			</div>
			<div class="bg-surface-white rounded-lg shadow-sm p-4 border border-outline-gray-1">
				<div class="text-sm text-ink-gray-6">Unrealized P&L</div>
				<div class="text-xl font-bold"
					 :class="deltaInk(data.net_unrealized, { higherIsBetter: true })">
					{{ formatCurrency(data.net_unrealized || 0, currency) }}
				</div>
				<div class="text-sm text-ink-gray-6">From rate changes</div>
			</div>
		</div>

		<!-- Exposure by Currency -->
		<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
			<SectionHeader title="Forex Exposure by Currency" :level="3" />
			<div class="mt-4 overflow-x-auto">
				<table class="min-w-full" v-if="data.exposure_summary?.length">
					<thead>
						<tr class="bg-surface-gray-1">
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Currency</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Receivable</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Payable</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Net Exposure</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Rate</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Value ({{ currency }})</th>
							<th scope="col" class="px-4 py-3 text-center text-xs font-medium text-ink-gray-6 uppercase">Position</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-outline-gray-1">
						<tr v-for="exp in data.exposure_summary" :key="exp.currency">
							<td class="px-4 py-3 font-medium text-ink-gray-9">{{ exp.currency }}</td>
							<td class="px-4 py-3 text-right text-sm text-ink-gray-9">
								{{ formatForeignCurrency(exp.receivable, exp.currency) }}
							</td>
							<td class="px-4 py-3 text-right text-sm text-ink-gray-9">
								{{ formatForeignCurrency(exp.payable, exp.currency) }}
							</td>
							<td class="px-4 py-3 text-right text-sm font-medium"
								:class="deltaInk(exp.net_exposure, { higherIsBetter: true })">
								{{ formatForeignCurrency(exp.net_exposure, exp.currency) }}
							</td>
							<td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ exp.current_rate }}</td>
							<td class="px-4 py-3 text-right text-sm font-bold"
								:class="deltaInk(exp.net_exposure_base, { higherIsBetter: true })">
								{{ formatCurrency(exp.net_exposure_base, currency) }}
							</td>
							<td class="px-4 py-3 text-center">
								<Badge v-bind="severityBadge(exp.position === 'Long' ? 'none' : 'medium')"
									   :label="exp.position" size="sm" />
							</td>
						</tr>
					</tbody>
				</table>
				<div v-else class="text-center py-8 text-ink-gray-6">
					No foreign currency exposure
				</div>
			</div>
		</div>

		<!-- At-Risk Invoices -->
		<div class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1">
			<SectionHeader :title="`At-Risk Foreign Currency Invoices (${data.at_risk_invoices?.length || 0})`" :level="3" />
			<div class="mt-4 overflow-x-auto">
				<table class="min-w-full" v-if="data.at_risk_invoices?.length">
					<thead>
						<tr class="bg-surface-gray-1">
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Type</th>
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Invoice</th>
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Party</th>
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Currency</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Outstanding</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Rate</th>
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Due Date</th>
							<th scope="col" class="px-4 py-3 text-center text-xs font-medium text-ink-gray-6 uppercase">Status</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-outline-gray-1">
						<tr v-for="invoice in data.at_risk_invoices" :key="invoice.name">
							<td class="px-4 py-3 text-sm">
								<Badge v-bind="severityBadge(invoice.doctype === 'Sales Invoice' ? 'none' : 'medium')"
									   :label="invoice.doctype === 'Sales Invoice' ? 'AR' : 'AP'" size="sm" />
							</td>
							<td class="px-4 py-3 font-medium text-ink-gray-9 cursor-pointer hover:underline"
								@click="openDocument(invoice.doctype, invoice.name)">
								{{ invoice.name }}
							</td>
							<td class="px-4 py-3 text-sm text-ink-gray-9">{{ invoice.party }}</td>
							<td class="px-4 py-3 text-sm font-medium text-ink-gray-6">{{ invoice.currency }}</td>
							<td class="px-4 py-3 text-right text-sm font-medium text-ink-gray-9">
								{{ formatForeignCurrency(invoice.outstanding_amount, invoice.currency) }}
							</td>
							<td class="px-4 py-3 text-right text-sm text-ink-gray-6">{{ invoice.conversion_rate }}</td>
							<td class="px-4 py-3 text-sm text-ink-gray-6">{{ formatDate(invoice.due_date) }}</td>
							<td class="px-4 py-3 text-center">
								<Badge v-bind="severityBadge(invoice.days_to_due < 0 ? 'high' : 'medium')"
									   :label="invoice.days_to_due < 0 ? `${Math.abs(invoice.days_to_due)}d overdue` : `${invoice.days_to_due}d to due`"
									   size="sm" />
							</td>
						</tr>
					</tbody>
				</table>
				<div v-else class="text-center py-8 text-ink-gray-6">
					No at-risk foreign currency invoices
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { Badge } from 'frappe-ui'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import { deltaInk, severityBadge } from '../../utils/status'
import { formatCurrency, formatForeignCurrency, formatDate } from './format'
import type { ForexData } from './types'

defineProps<{
	data: ForexData
	currency: string
}>()

const openDocument = (doctype: string, name: string) => {
	window.open(`/app/${doctype.toLowerCase().replace(/ /g, '-')}/${name}`, '_blank')
}
</script>
