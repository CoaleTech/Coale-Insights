<!--
  The Cash tab: what we hold, what it is doing, and what it earns.

  Ordered the way the question is actually asked. Position first (and what of
  it can be spent today), then the deposits that hold most of it, then the
  movement that explains the change, then where the money came from and went.

  The deposit section exists because the previous version of this tab reported
  a fixed deposit as a single row in an account list and folded it into "Total
  Cash", so the reader could see that ~103% of the company's cash sits in a
  deposit but nothing about it: no movement, no interest, no turnover, no bank
  reference. It also printed `account_type || 'Fixed Deposit'`, which labelled
  any account with a blank account_type a deposit.

  ERPNext stores no deposit instrument -- `Account.account_type` has no
  term-deposit option and the schema's only native mention of one is
  `Bank Guarantee.fixed_deposit_number`, a margin-money field. Maturity date,
  tenor and contracted rate therefore cannot be shown, and are not implied
  anywhere here. Everything rendered is a ledger fact from
  `_fixed_deposit_analysis`, including the bank's own deposit receipt number
  which the journal remarks carry.
-->
<template>
	<div class="space-y-6">
		<!-- Cash position -->
		<div>
			<SectionHeader
				variant="caption"
				title="Cash position"
				:hint="asOfLabel"
				:level="3"
			/>
			<div class="mt-3 grid grid-cols-1 gap-4 md:grid-cols-3 lg:grid-cols-6">
				<KpiCard label="Total Cash" :amount="data.total_cash" :currency="currency"
					:sublabel="accountCountLabel" :clickable="true"
					@click="drillDown.open(finEndpoint, 'Cash & Bank Accounts', { metric: 'cash_accounts' })" />
				<KpiCard label="In Fixed Deposits" :amount="data.fd_balance" :currency="currency"
					:sublabel="fdShareLabel" />
				<KpiCard label="Bank" :amount="data.bank_balance" :currency="currency"
					:severity="data.bank_balance != null && data.bank_balance < 0 ? 'critical' : 'none'"
					:sublabel="data.bank_balance != null && data.bank_balance < 0 ? 'overdrawn on the books' : 'current accounts'" />
				<KpiCard label="Cash on Hand" :amount="data.cash_on_hand" :currency="currency" />
				<!--
					The figure a CFO actually spends from: total minus anything
					held on deposit. Computed server-side so the name match that
					identifies a deposit lives in one place.
				-->
				<KpiCard label="Free Cash" :amount="data.liquid_cash" :currency="currency"
					:severity="freeCashSeverity" sublabel="bank + hand, excl. deposits" />
				<KpiCard label="Cash Runway" :value="cashRunwayLabel(data.runway_months)"
					:severity="runwaySeverity(data.runway_months)" :sublabel="burnLabel" />
			</div>
		</div>

		<!--
			Post-dated cheques are posted the day they are written, so the book
			balance above already carries money that has not moved. Stating both
			figures is the difference between "we are overdrawn" and "we are not,
			yet" -- which the balance column alone cannot say.
		-->
		<div v-if="postDated" class="flex items-start gap-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4">
			<CalendarClock class="mt-0.5 h-5 w-5 shrink-0 text-ink-gray-6" aria-hidden="true" />
			<p class="text-sm text-ink-gray-7">
				<span class="font-medium text-ink-gray-9">{{ formatCurrency(Math.abs(postDated.net), currency) }}</span>
				of cash movement is posted with a future date
				({{ postDated.entries }} {{ postDated.entries === 1 ? 'entry' : 'entries' }},
				latest {{ formatDate(postDated.last_date) }}).
				Balance on the books today is
				<span class="font-medium text-ink-gray-9">{{ formatCurrency(balanceToday, currency) }}</span>.
			</p>
		</div>

		<!-- Fixed deposits -->
		<div v-if="fd" class="rounded-lg border border-outline-gray-1 bg-surface-white p-6 shadow-sm">
			<div class="flex flex-wrap items-start justify-between gap-3">
				<SectionHeader
					variant="caption"
					title="Fixed deposits"
					:hint="fdSubtitle"
					:level="3"
				/>
				<Badge v-if="fd.pct_of_cash != null" v-bind="severityBadge('none')"
					   :label="`${formatPercent(fd.pct_of_cash)} of cash`" size="sm" />
			</div>

			<div class="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
				<KpiCard variant="tile" label="Principal on Deposit" :amount="fd.balance" :currency="currency" />
				<KpiCard variant="tile" label="Placed" :amount="fd.placed" :currency="currency"
					:sublabel="placementLabel" />
				<KpiCard variant="tile" label="Released" :amount="fd.released" :currency="currency"
					:sublabel="releaseLabel" />
				<KpiCard variant="tile" label="Interest Booked" :amount="fd.interest_booked_fy" :currency="currency"
					:sublabel="fd.fiscal_year ? `FY ${fd.fiscal_year} to date` : undefined" />
				<KpiCard variant="tile" label="Interest Accrued" :amount="fd.interest_accrued" :currency="currency"
					sublabel="unrealised" />
				<!--
					Annualised booked interest over the average balance. Graded,
					because a deposit yielding under 3% almost never means the
					bank is paying that: it means interest is being posted
					somewhere else, or not at all, and that is the finding.
				-->
				<KpiCard variant="tile" label="Implied Yield" :percent="fd.yield_pct ?? null"
					:severity="yieldSeverity" :sublabel="yieldNote" />
			</div>

			<div class="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-5">
				<div class="lg:col-span-3">
					<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">
						Principal and movement, last {{ fd.window_months ?? 12 }} months
					</p>
					<IntelligenceChart v-if="depositConfig" class="mt-3 h-48 sm:h-56 lg:h-64" :config="depositConfig" />
					<div v-else class="flex h-48 items-center justify-center text-sm text-ink-gray-6">
						No deposit movement in this window
					</div>
				</div>

				<!-- Every movement the bank posted, with its own receipt number. -->
				<div class="lg:col-span-2">
					<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">Latest movements</p>
					<div class="mt-3 max-h-64 overflow-auto">
						<table v-if="fd.recent_activity?.length" class="min-w-full">
							<caption class="sr-only">Latest fixed deposit placements and releases</caption>
							<thead>
								<tr class="bg-surface-gray-1">
									<th scope="col" class="px-3 py-2 text-left text-xs font-medium uppercase text-ink-gray-6">Date</th>
									<th scope="col" class="px-3 py-2 text-left text-xs font-medium uppercase text-ink-gray-6">Receipt</th>
									<th scope="col" class="px-3 py-2 text-right text-xs font-medium uppercase text-ink-gray-6">Amount</th>
								</tr>
							</thead>
							<tbody class="divide-y divide-outline-gray-1">
								<tr v-for="(row, i) in fd.recent_activity" :key="`${row.voucher_no}-${i}`">
									<td class="px-3 py-2 text-sm text-ink-gray-6">{{ formatDate(row.posting_date) }}</td>
									<td class="px-3 py-2 text-sm">
										<span class="font-medium text-ink-gray-9">{{ row.reference ?? row.voucher_no ?? NO_VALUE }}</span>
										<span class="block text-xs text-ink-gray-6">
											{{ row.direction === 'placement' ? 'Placed' : 'Released' }}
										</span>
									</td>
									<td class="px-3 py-2 text-right text-sm font-medium"
										:class="deltaInk(row.direction === 'placement' ? 1 : -1, { higherIsBetter: true })">
										{{ formatCurrency(row.amount, currency) }}
									</td>
								</tr>
							</tbody>
						</table>
						<div v-else class="py-4 text-center text-sm text-ink-gray-6">No deposit movements recorded</div>
					</div>
				</div>
			</div>

			<!-- mt-8, not mt-4: ECharts paints its legend at the bottom of a
			     canvas that overflows the wrapper's height, so a tighter gap
			     ran this line through the legend swatches. -->
			<p class="mt-8 text-xs text-ink-gray-5">
				Maturity date, tenor and contracted rate are not stored by ERPNext for a deposit,
				so nothing above infers them. Figures are ledger movements on
				{{ fdAccountNames }}; receipt numbers are the bank's, taken from the journal remarks.
			</p>
		</div>

		<!-- Movement and accounts -->
		<div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
			<div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6 shadow-sm">
				<SectionHeader variant="caption" title="Cash in vs out"
					hint="All ledger movement on cash, bank and deposit accounts" :level="3" />
				<IntelligenceChart v-if="movementConfig" class="mt-4 h-48 sm:h-56 lg:h-64" :config="movementConfig" />
				<div v-else class="flex h-48 items-center justify-center text-sm text-ink-gray-6">
					No cash movement data available
				</div>
				<table v-if="movement.length" class="sr-only">
					<caption>Monthly cash inflows, outflows and closing balance</caption>
					<thead>
						<tr>
							<th scope="col">Month</th>
							<th scope="col">In</th>
							<th scope="col">Out</th>
							<th scope="col">Closing</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="month in movement" :key="month.period">
							<th scope="row">{{ formatPeriod(month.period) }}</th>
							<td>{{ formatCurrency(month.inflow, currency) }}</td>
							<td>{{ formatCurrency(month.outflow, currency) }}</td>
							<td>{{ formatCurrency(month.closing, currency) }}</td>
						</tr>
					</tbody>
				</table>
			</div>

			<div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6 shadow-sm">
				<SectionHeader variant="caption" title="Where it is held" :level="3" />
				<div class="mt-4 max-h-72 space-y-2 overflow-auto">
					<div v-for="acc in data.cash_accounts" :key="acc.account"
						 class="flex cursor-pointer items-center justify-between rounded bg-surface-gray-1 p-2 transition-colors hover:bg-surface-gray-2 motion-reduce:transition-none"
						 tabindex="0"
						 @click="drillDown.open(finEndpoint, acc.account_name, { metric: 'cash_accounts' })"
						 @keydown.enter="drillDown.open(finEndpoint, acc.account_name, { metric: 'cash_accounts' })">
						<div class="min-w-0">
							<div class="truncate text-sm font-medium text-ink-gray-9">{{ acc.account_name }}</div>
							<div class="text-xs text-ink-gray-6">
								{{ acc.account_class || acc.account_type || 'Unclassified' }}
								<template v-if="acc.share_pct != null"> · {{ formatPercent(acc.share_pct) }} of cash</template>
							</div>
						</div>
						<div class="shrink-0 text-right">
							<span :class="deltaInk(acc.balance, { higherIsBetter: true })" class="text-sm font-medium">
								{{ formatCurrency(acc.balance, currency) }}
							</span>
							<span v-if="acc.balance < 0" class="block text-xs text-ink-gray-6">overdrawn</span>
						</div>
					</div>
					<div v-if="!data.cash_accounts?.length" class="py-4 text-center text-sm text-ink-gray-6">
						No cash or bank accounts found
					</div>
				</div>
			</div>
		</div>

		<!--
			Both sides were already computed by the server and rendered nowhere,
			so "where did the money come from and go" was unanswerable on a tab
			that held the answer.
		-->
		<div v-if="sources.length || uses.length" class="grid grid-cols-1 gap-6 lg:grid-cols-2">
			<div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6 shadow-sm">
				<SectionHeader variant="caption" title="Where cash came from"
					hint="Receipts by party type, last 3 months" :level="3" />
				<WaterfallRows v-if="sources.length" class="mt-4" :rows="sources" :currency="currency"
					:scale-max="flowScaleMax" />
				<div v-else class="py-4 text-center text-sm text-ink-gray-6">No receipts in this window</div>
			</div>
			<div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6 shadow-sm">
				<SectionHeader variant="caption" title="Where cash went"
					hint="Payments by party type, last 3 months" :level="3" />
				<WaterfallRows v-if="uses.length" class="mt-4" :rows="uses" :currency="currency"
					:scale-max="flowScaleMax" />
				<div v-else class="py-4 text-center text-sm text-ink-gray-6">No payments in this window</div>
			</div>
		</div>

		<!-- Large Transactions -->
		<div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6 shadow-sm">
			<SectionHeader variant="caption" title="Large Cash Transactions (Last 30 Days)" :level="3" />
			<div class="mt-4 overflow-x-auto">
				<table v-if="data.large_transactions?.length" class="min-w-full">
					<thead>
						<tr class="bg-surface-gray-1">
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Date</th>
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Party</th>
							<th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Type</th>
							<th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Amount</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-outline-gray-1">
						<tr v-for="tx in data.large_transactions" :key="tx.name">
							<td class="px-4 py-3 text-sm text-ink-gray-6">{{ formatDate(tx.posting_date) }}</td>
							<td class="px-4 py-3 font-medium text-ink-gray-9">{{ tx.party }}</td>
							<td class="px-4 py-3">
								<Badge v-bind="severityBadge(tx.payment_type === 'Receive' ? 'low' : 'none')"
									   :label="tx.payment_type" size="sm" />
							</td>
							<td class="px-4 py-3 text-right text-sm font-medium"
								:class="deltaInk(tx.paid_amount, { higherIsBetter: tx.payment_type === 'Receive' })">
								{{ formatCurrency(tx.paid_amount, currency) }}
							</td>
						</tr>
					</tbody>
				</table>
				<div v-else class="text-sm text-ink-gray-6 text-center py-4">
					No large cash transactions in the last 30 days
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { Badge } from 'frappe-ui'
import { CalendarClock } from 'lucide-vue-next'
import { computed } from 'vue'
import IntelligenceChart from '../../intelligence/components/IntelligenceChart.vue'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import WaterfallRows from '../../intelligence/components/WaterfallRows.vue'
import type { useDrillDown } from '../../intelligence/composables/useDrillDown'
import { themeColor } from '../../utils/chartTheme'
import {
	NO_VALUE,
	cashRunwayLabel,
	formatCount,
	formatDate,
	formatMoney as formatCurrency,
	formatPercent,
} from '../../utils/format'
import { deltaInk, severityBadge, type Severity } from '../../utils/status'
import { formatPeriod } from './format'
import type { CashFlowData } from './types'

const props = defineProps<{
	data: CashFlowData
	currency: string
	finEndpoint: string
	drillDown: ReturnType<typeof useDrillDown>
}>()

const fd = computed(() => props.data.fixed_deposits ?? null)
const postDated = computed(() => props.data.post_dated ?? null)
const movement = computed(() => props.data.monthly_cash_movement ?? [])

const asOfLabel = computed(() =>
	props.data.as_of ? `As of ${formatDate(props.data.as_of)}` : '',
)

const accountCountLabel = computed(() => {
	const n = props.data.cash_accounts?.length ?? 0
	return n ? `${formatCount(n)} ${n === 1 ? 'account' : 'accounts'}` : undefined
})

const fdShareLabel = computed(() => {
	const pct = fd.value?.pct_of_cash
	return pct == null ? undefined : `${formatPercent(pct)} of total cash`
})

/**
 * The book balance includes future-dated entries, so today's balance is the
 * total with that movement taken back out.
 */
const balanceToday = computed(
	() => (props.data.total_cash ?? 0) - (postDated.value?.net ?? 0),
)

/** Nothing spendable left is a red flag, not a neutral figure. */
const freeCashSeverity = computed<Severity>(() => {
	const free = props.data.liquid_cash
	if (free == null) return 'none'
	if (free < 0) return 'critical'
	return free < (props.data.avg_monthly_outflow ?? 0) ? 'medium' : 'low'
})

/** Runway is months of cash left at the current burn; 999 is the backend's
 * sentinel for "not burning cash" (see cashRunwayLabel), not a real number. */
function runwaySeverity(months: number | undefined): Severity {
	if (months == null || months >= 999) return 'none'
	if (months < 3) return 'critical'
	return months < 6 ? 'medium' : 'low'
}

/** Average net movement from the GL series, which reconciles to the balances
 * above -- unlike the Payment Entry averages, which miss journal postings. */
const burnLabel = computed(() => {
	if (!movement.value.length) return undefined
	const avg = movement.value.reduce((sum, m) => sum + m.net, 0) / movement.value.length
	const direction = avg >= 0 ? 'building' : 'drawing down'
	return `${formatCurrency(Math.abs(avg), props.currency)}/mo ${direction}`
})

const fdSubtitle = computed(() => {
	const swept = fd.value?.swept_with?.[0]
	if (!swept) return 'Ledger movements on deposit accounts'
	// The account a deposit is placed from and released to. On a sweep
	// facility that is the operating current account, which is what makes the
	// principal callable rather than locked away.
	return `Placed from and released to ${swept.split(' - ').slice(0, 2).join(' - ')}`
})

const fdAccountNames = computed(
	() => fd.value?.accounts?.map(a => a.account_name).join(', ') || 'the deposit accounts',
)

const placementLabel = computed(() => {
	const f = fd.value
	if (!f?.placement_count) return undefined
	// Compact, because a tile's sublabel is one line at ~200px and the exact
	// figure is already the headline above it.
	const avg = f.avg_ticket
		? formatCurrency(f.avg_ticket, props.currency, { compact: true })
		: null
	return `${formatCount(f.placement_count)} lots${avg ? ` · avg ${avg}` : ''}`
})

const releaseLabel = computed(() => {
	const f = fd.value
	if (!f?.release_count) return undefined
	return `${formatCount(f.release_count)} releases`
})

/**
 * A term deposit does not pay under 3%. A yield that low is evidence that
 * interest is being posted elsewhere (or not at all), which is a finding for
 * the reader rather than a number to accept.
 */
const yieldSeverity = computed<Severity>(() => {
	const y = fd.value?.yield_pct
	if (y == null) return 'none'
	return y < 3 ? 'medium' : 'low'
})

const yieldNote = computed(() => {
	const y = fd.value?.yield_pct
	if (y == null) return 'no interest booked'
	return y < 3 ? 'check interest posting' : 'annualised'
})

const depositConfig = computed(() => {
	const rows = fd.value?.monthly ?? []
	if (!rows.length) return null
	return {
		title: '',
		data: rows.map(r => ({
			period: formatPeriod(r.period),
			Placed: r.placed,
			Released: r.released,
			Balance: r.closing ?? 0,
		})),
		xAxis: { key: 'period', type: 'category' as const },
		yAxis: { title: props.currency },
		// A line axis that does not start at zero overstates every swing on it.
		y2Axis: { title: '', yMin: 0 },
		series: [
			{ name: 'Placed', type: 'bar' as const, color: themeColor('--app-pos-fill'), axis: 'y' as const },
			{ name: 'Released', type: 'bar' as const, color: themeColor('--app-neg-fill'), axis: 'y' as const },
			{
				name: 'Balance',
				type: 'line' as const,
				color: themeColor('--app-accent-strong'),
				axis: 'y2' as const,
				showDataPoints: true,
			},
		],
	}
})

const movementConfig = computed(() => {
	const rows = movement.value
	if (!rows.length) return null
	return {
		title: '',
		data: rows.map(r => ({
			period: formatPeriod(r.period),
			In: r.inflow,
			Out: r.outflow,
			Closing: r.closing ?? 0,
		})),
		xAxis: { key: 'period', type: 'category' as const },
		yAxis: { title: props.currency },
		y2Axis: { title: '', yMin: 0 },
		series: [
			{ name: 'In', type: 'bar' as const, color: themeColor('--app-pos-fill'), axis: 'y' as const },
			{ name: 'Out', type: 'bar' as const, color: themeColor('--app-neg-fill'), axis: 'y' as const },
			{
				name: 'Closing',
				type: 'line' as const,
				color: themeColor('--app-accent-strong'),
				axis: 'y2' as const,
				showDataPoints: true,
			},
		],
	}
})

const sources = computed(() =>
	(props.data.inflow_by_source ?? []).map(row => ({
		label: row.source,
		amount: row.amount,
		direction: 'positive' as const,
	})),
)

const uses = computed(() =>
	(props.data.outflow_by_use ?? []).map(row => ({
		label: row.category,
		amount: row.amount,
		direction: 'negative' as const,
	})),
)

/**
 * One scale across both waterfalls below. They are a pair -- the same money,
 * arriving and leaving -- rendered in adjacent panels, and each normalises to
 * its own largest row by default. Unshared, the largest outflow drew the same
 * bar as the largest inflow however far apart the two actually were, which is
 * the one comparison this section exists to support.
 */
const flowScaleMax = computed(() =>
	[...sources.value, ...uses.value].reduce(
		(max, row) => (Number.isFinite(row.amount) ? Math.max(max, Math.abs(row.amount)) : max),
		0,
	),
)
</script>
