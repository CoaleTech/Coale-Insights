<template>
	<div class="space-y-6">
		<!-- ── Hero row: 2/3 waterfall + 1/3 attention rail ───────────────────── -->
		<div class="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-6">

			<!-- LEFT: Monthly net-profit waterfall + P&L KPI tiles -->
			<div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6 space-y-4">
				<div>
					<SectionHeader
						:title="windowLabel ? `Monthly Net Profit · ${windowLabel}` : 'Monthly Net Profit'"
						:hint="heroHint"
						:level="2"
					/>
				</div>

				<!-- Dual-series bar chart: Profit (green series) + Loss (red series) -->
				<IntelligenceChart
					v-if="trend.length"
					class="h-80"
					:config="profitChartConfig"
				/>
				<div v-else class="h-56 flex items-center justify-center text-ink-gray-6 text-sm">
					No postings in the selected date window
				</div>

				<!-- Accessible table for screen readers -->
				<table v-if="trend.length" class="sr-only">
					<caption>Monthly net profit</caption>
					<thead>
						<tr><th scope="col">Month</th><th scope="col">Revenue</th><th scope="col">Net profit</th></tr>
					</thead>
					<tbody>
						<tr v-for="m in trend" :key="m.period">
							<th scope="row">{{ formatPeriod(m.period) }}</th>
							<td>{{ formatMoney(m.revenue, props.currency) }}</td>
							<td>{{ formatMoney(m.profit, props.currency) }}</td>
						</tr>
					</tbody>
				</table>

				<!-- P&L KPI tile strip (4 tiles, variant="tile") -->
				<div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-2 wide:grid-cols-4 gap-3 pt-2 border-t border-outline-gray-1">
					<KpiCard
						variant="tile"
						label="YTD Revenue"
						:amount="data.ytd_revenue"
						:currency="props.currency"
						:delta="revenueGrowth ?? undefined"
						:delta-higher-is-better="true"
						:sublabel="revenueGrowthLabel"
					/>
					<KpiCard
						variant="tile"
						label="Gross Profit"
						:amount="grossProfit ?? undefined"
						:currency="props.currency"
						:sublabel="grossMarginLabel"
					/>
					<KpiCard
						variant="tile"
						label="Net Profit"
						:amount="data.ytd_profit"
						:currency="props.currency"
						:sublabel="netMarginLabel"
					/>
					<KpiCard
						variant="tile"
						label="EBITDA"
						:amount="data.ytd_ebitda ?? undefined"
						:currency="props.currency"
						:sublabel="ebitdaMarginLabel"
					/>
				</div>
			</div>

			<!-- RIGHT: Attention rail (key positions + needs attention) -->
			<div class="space-y-4">

				<!-- KEY POSITIONS -->
				<div class="bg-surface-white rounded-lg border border-outline-gray-1 p-5 space-y-3">
					<SectionHeader variant="caption" title="Key Positions" :level="3" />

					<!-- Cash -->
					<div class="flex items-start justify-between gap-2 py-2 border-b border-outline-gray-1">
						<div class="min-w-0">
							<p class="text-xs text-ink-gray-6 uppercase tracking-wide">Cash Position</p>
							<p class="text-sm font-semibold" :class="totalCashClass">
								{{ totalCash != null ? formatMoney(totalCash, props.currency, { compact: true }) : NO_VALUE }}
							</p>
							<p v-if="cashSublabel" class="text-xs text-ink-gray-6 mt-0.5">{{ cashSublabel }}</p>
						</div>
						<button
							class="text-xs text-ink-gray-6 hover:text-ink-blue-3 shrink-0 py-1.5 -mt-0.5 -mb-1.5"
							type="button"
							@click="drillDown.open(finEndpoint, 'Cash Accounts', { metric: 'cash_accounts' })"
						>View →</button>
					</div>

					<!-- Outstanding AR -->
					<div class="flex items-start justify-between gap-2 py-2 border-b border-outline-gray-1">
						<div class="min-w-0">
							<p class="text-xs text-ink-gray-6 uppercase tracking-wide">Outstanding AR</p>
							<p class="text-sm font-semibold text-ink-gray-9">
								{{ receivables.total_outstanding != null ? formatMoney(receivables.total_outstanding, props.currency, { compact: true }) : NO_VALUE }}
							</p>
							<p class="text-xs text-ink-gray-6 mt-0.5">
								<template v-if="receivables.invoice_count">{{ receivables.invoice_count }} invoices</template>
								<template v-if="receivables.current_dso != null"> · DSO {{ Math.round(receivables.current_dso) }} days</template>
							</p>
						</div>
						<button
							class="text-xs text-ink-gray-6 hover:text-ink-blue-3 shrink-0 py-1.5 -mt-0.5 -mb-1.5"
							type="button"
							@click="drillDown.open(finEndpoint, 'Outstanding AR', { metric: 'outstanding_ar' })"
						>View →</button>
					</div>

					<!-- 90+ Overdue AR -->
					<div
						v-if="overdueAR90Bucket"
						class="flex items-start justify-between gap-2 py-2 border-b border-outline-gray-1"
					>
						<div class="min-w-0">
							<p class="text-xs text-ink-gray-6 uppercase tracking-wide">90+ Days Overdue</p>
							<p class="text-sm font-semibold text-ink-red-4">
								{{ formatMoney(overdueAR90Bucket.amount, props.currency, { compact: true }) }}
							</p>
							<p v-if="overdueAR90Bucket.count" class="text-xs text-ink-gray-6 mt-0.5">
								{{ overdueAR90Bucket.count }} invoices
							</p>
						</div>
						<button
							class="text-xs text-ink-gray-6 hover:text-ink-blue-3 shrink-0 py-1.5 -mt-0.5 -mb-1.5"
							type="button"
							@click="drillDown.open(finEndpoint, '90+ Days Overdue AR', { metric: 'overdue_ar_90' })"
						>View →</button>
					</div>

					<!-- Outstanding AP -->
					<div class="flex items-start justify-between gap-2 py-2">
						<div class="min-w-0">
							<p class="text-xs text-ink-gray-6 uppercase tracking-wide">Outstanding AP</p>
							<p class="text-sm font-semibold text-ink-gray-9">
								{{ payables.total_outstanding != null ? formatMoney(payables.total_outstanding, props.currency, { compact: true }) : NO_VALUE }}
							</p>
							<p class="text-xs text-ink-gray-6 mt-0.5">
								<template v-if="payables.invoice_count">{{ payables.invoice_count }} invoices</template>
								<template v-if="payables.current_dpo != null"> · DPO {{ Math.round(payables.current_dpo) }} days</template>
							</p>
						</div>
						<button
							class="text-xs text-ink-gray-6 hover:text-ink-blue-3 shrink-0 py-1.5 -mt-0.5 -mb-1.5"
							type="button"
							@click="drillDown.open(finEndpoint, 'Outstanding AP', { metric: 'outstanding_ap' })"
						>View →</button>
					</div>
				</div>

				<!-- NEEDS ATTENTION -->
				<div
					v-if="attentionItems.length"
					class="bg-surface-white rounded-lg border border-outline-gray-1 p-5 space-y-4"
				>
					<SectionHeader variant="caption" title="Needs Attention" :level="3" />
					<div
						v-for="item in attentionItems"
						:key="item.title"
						class="space-y-1"
					>
						<div class="flex items-center justify-between gap-2">
							<p class="text-sm font-semibold text-ink-gray-9 leading-snug">{{ item.title }}</p>
							<Badge v-bind="severityBadge(item.severity)" :label="item.badge" size="sm" class="shrink-0" />
						</div>
						<p class="text-xs text-ink-gray-6 leading-relaxed">{{ item.description }}</p>
						<p v-if="item.action" class="text-xs text-ink-blue-3">→ {{ item.action }}</p>
					</div>
				</div>
			</div>
		</div>

		<!-- ── Evidence row: AR/AP aging + Expenses + Health ──────────────────── -->
		<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">

			<!-- AR & AP aging -->
			<div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6 space-y-5">
				<SectionHeader variant="caption" title="Receivables & Payables Aging" :level="3" />

				<!-- AR aging -->
				<div class="space-y-2">
					<div class="flex items-center justify-between">
						<span class="text-sm font-medium text-ink-gray-9">
							AR {{ receivables.total_outstanding != null ? formatMoney(receivables.total_outstanding, props.currency, { compact: true }) : NO_VALUE }}
							<span v-if="receivables.invoice_count" class="text-ink-gray-6 font-normal">
								· {{ receivables.invoice_count }} inv
							</span>
						</span>
						<button
							class="text-xs text-ink-gray-6 hover:text-ink-blue-3 py-1.5 -my-1.5"
							type="button"
							@click="drillDown.open(finEndpoint, 'Outstanding AR', { metric: 'outstanding_ar' })"
						>↗ Receivables</button>
					</div>
					<!-- Horizontal aging bar -->
					<div
						class="flex rounded-full overflow-hidden h-3 w-full"
						role="img"
						:aria-label="arAgingLabel"
					>
						<div
							v-for="seg in arSegments"
							:key="seg.bucket"
							:class="seg.colorClass"
							:style="{ width: seg.pct + '%' }"
						></div>
					</div>
					<div class="flex flex-wrap gap-x-3 gap-y-1 mt-1">
						<span
							v-for="seg in arSegments"
							:key="seg.bucket"
							class="flex items-center gap-1 text-xs text-ink-gray-6"
						>
							<span class="inline-block w-2 h-2 rounded-full" :class="seg.colorClass" aria-hidden="true"></span>
							{{ seg.bucket }} {{ seg.pct }}%
						</span>
					</div>
				</div>

				<!-- AP aging -->
				<div class="space-y-2">
					<div class="flex items-center justify-between">
						<span class="text-sm font-medium text-ink-gray-9">
							AP {{ payables.total_outstanding != null ? formatMoney(payables.total_outstanding, props.currency, { compact: true }) : NO_VALUE }}
							<span v-if="payables.invoice_count" class="text-ink-gray-6 font-normal">
								· {{ payables.invoice_count }} inv
							</span>
						</span>
						<button
							class="text-xs text-ink-gray-6 hover:text-ink-blue-3 py-1.5 -my-1.5"
							type="button"
							@click="drillDown.open(finEndpoint, 'Outstanding AP', { metric: 'outstanding_ap' })"
						>↗ Payables</button>
					</div>
					<div
						class="flex rounded-full overflow-hidden h-3 w-full"
						role="img"
						:aria-label="apAgingLabel"
					>
						<div
							v-for="seg in apSegments"
							:key="seg.bucket"
							:class="seg.colorClass"
							:style="{ width: seg.pct + '%' }"
						></div>
					</div>
					<div class="flex flex-wrap gap-x-3 gap-y-1 mt-1">
						<span
							v-for="seg in apSegments"
							:key="seg.bucket"
							class="flex items-center gap-1 text-xs text-ink-gray-6"
						>
							<span class="inline-block w-2 h-2 rounded-full" :class="seg.colorClass" aria-hidden="true"></span>
							{{ seg.bucket }} {{ seg.pct }}%
						</span>
					</div>
				</div>
			</div>

			<!-- Expense breakdown + Financial health -->
			<div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6 space-y-5">

				<!-- Expense breakdown (ranked bar list) -->
				<div>
					<SectionHeader
						variant="caption"
						:title="`Expense Breakdown · YTD ${data.ytd_expenses != null ? formatMoney(data.ytd_expenses, props.currency, { compact: true }) : NO_VALUE}`"
						:level="3"
					/>
					<div class="mt-3 space-y-2">
						<div
							v-for="row in topExpenses"
							:key="row.category"
							class="flex items-center gap-3"
						>
							<span class="text-xs text-ink-gray-6 w-20 truncate shrink-0">
								{{ row.category.replace(/ - JKM$/, '') }}
							</span>
							<div
								class="flex-1 bg-surface-gray-2 rounded-full h-2 overflow-hidden"
								aria-hidden="true"
							>
								<div
									class="bg-surface-red-2 h-full rounded-full"
									:style="{ width: row.pct + '%' }"
								></div>
							</div>
							<span class="text-xs font-medium text-ink-gray-9 shrink-0 w-14 text-right">
								{{ formatMoney(row.amount, props.currency, { compact: true }) }}
							</span>
							<span class="text-xs text-ink-gray-6 shrink-0 w-8 text-right">{{ row.pct }}%</span>
						</div>
					</div>
				</div>

				<!-- Financial health scores -->
				<div v-if="healthScoreItems.length">
					<SectionHeader variant="caption" title="Financial Health" :level="3" />
					<div class="mt-3 grid grid-cols-3 gap-3">
						<div
							v-for="score in healthScoreItems"
							:key="score.label"
							class="rounded-lg p-3 text-center"
							:class="score.bgClass"
						>
							<p class="text-xl font-bold text-ink-gray-9">{{ score.value }}</p>
							<p class="text-xs text-ink-gray-7 mt-0.5">{{ score.label }}</p>
							<p class="text-xs font-medium mt-0.5" :class="score.textClass">{{ score.status }}</p>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import IntelligenceChart from '../../intelligence/components/IntelligenceChart.vue'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import { signedPalette } from '../../utils/chartTheme'
import { formatMoney, NO_VALUE } from '../../utils/format'
import { severityBadge } from '../../utils/status'
import { formatPeriod } from './format'
import type { OverviewData, CashFlowData, ReceivablesData, PayablesData, AgingBucket } from './types'
import type { ExecutiveSummaryData } from '../strategic-finance/types'
import type { DrillDownState } from '../../intelligence/composables/useDrillDown'

// ── Aging bar colour per bucket (whole literal strings for Tailwind scanner) ──
function agingColor(bucket: string): string {
	switch (bucket) {
		case 'Current':    return 'bg-surface-green-2'
		case '1-30 Days':  return 'bg-surface-blue-2'
		case '31-60 Days': return 'bg-surface-amber-2'
		case '61-90 Days': return 'bg-surface-red-2'
		case '90+ Days':   return 'bg-surface-red-2'
		default:           return 'bg-surface-gray-2'
	}
}

function toAgingSegments(buckets: AgingBucket[]): Array<{ bucket: string; pct: number; colorClass: string }> {
	const total = buckets.reduce((s, b) => s + (b.amount ?? 0), 0)
	return buckets.map(b => ({
		bucket: b.bucket,
		pct: total > 0 ? Math.round((b.amount / total) * 100) : 0,
		colorClass: agingColor(b.bucket),
	}))
}

interface AttentionItem {
	title: string
	badge: string
	severity: string
	description: string
	action?: string
}

const props = defineProps<{
	data: OverviewData
	currency: string
	cashFlow: CashFlowData
	receivables: ReceivablesData
	payables: PayablesData
	executiveSummary?: ExecutiveSummaryData | null
	overdueAR90Bucket?: { amount: number; count: number } | null
	finEndpoint: string
	drillDown: DrillDownState
	refreshing?: boolean
	error?: string
}>()

// ── Trend (future-dated posts excluded) ─────────────────────────────────────
const now = new Date()
const currentPeriod = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
const trend = computed(() => (props.data.monthly_trend ?? []).filter(m => m.period <= currentPeriod))

const windowLabel = computed(() => {
	if (!trend.value.length) return ''
	const first = trend.value[0].period
	const last  = trend.value[trend.value.length - 1].period
	return first === last ? formatPeriod(first) : `${formatPeriod(first)} – ${formatPeriod(last)}`
})

// A window longer than a year repeats month names, so keep the year there ("Mar 25").
const lossMonths = computed(() =>
	trend.value
		.filter(m => (m.profit ?? 0) < 0)
		.map(m => (trend.value.length > 12 ? formatPeriod(m.period) : formatPeriod(m.period).split(' ')[0])),
)

const heroHint = computed((): string => {
	const parts: string[] = []
	const rev    = props.data.ytd_revenue
	const profit = props.data.ytd_profit
	const margin = props.data.net_margin
	if (rev != null && profit != null)
		parts.push(`Fiscal YTD ${formatMoney(profit, props.currency, { compact: true })} profit on ${formatMoney(rev, props.currency, { compact: true })} revenue`)
	if (margin != null)
		parts.push(`${margin.toFixed(1)}% margin`)
	if (lossMonths.value.length)
		parts.push(`${lossMonths.value.length} loss month${lossMonths.value.length > 1 ? 's' : ''} in the chart: ${lossMonths.value.join(', ')}`)
	return parts.join(' · ')
})

// ── Chart: signed bar chart – positive bars green, negative bars red ─────────
// Two series per month (only one non-null per row); stacked so they share the axis.
const profitChartConfig = computed(() => ({
	title: '',
	data: trend.value.map(m => ({
		period: formatPeriod(m.period),
		Profit: (m.profit ?? 0) > 0 ? (m.profit as number) : null,
		Loss:   (m.profit ?? 0) <= 0 ? (m.profit as number) : null,
	})),
	xAxis: { key: 'period', type: 'category' as const },
	yAxis: { title: '' as const },
	colors: signedPalette(),
	series: [
		{ name: 'Profit', type: 'bar' as const, showDataLabels: true },
		{ name: 'Loss',   type: 'bar' as const, showDataLabels: true },
	],
	stacked: true,
}))

// ── KPI tile sublabels ───────────────────────────────────────────────────────
const grossProfit  = computed(() => props.executiveSummary?.gross_profit ?? null)
const grossMargin  = computed(() => props.executiveSummary?.gross_margin ?? null)
const revenueGrowth = computed(() =>
	props.executiveSummary?.revenue_growth ?? props.executiveSummary?.revenue_growth_yoy ?? null,
)

const revenueGrowthLabel = computed((): string | undefined => {
	const g = revenueGrowth.value
	if (g == null) return undefined
	return `${g > 0 ? '+' : ''}${g.toFixed(1)}% YoY`
})
const grossMarginLabel = computed((): string | undefined =>
	grossMargin.value != null ? `${grossMargin.value.toFixed(1)}% gross margin` : undefined,
)
const netMarginLabel = computed((): string | undefined =>
	props.data.net_margin != null ? `${props.data.net_margin.toFixed(1)}% net margin` : undefined,
)
const ebitdaMarginLabel = computed((): string | undefined => {
	const m = props.data.ebitda_margin
	return m != null ? `${m.toFixed(1)}% margin` : undefined
})

// ── Cash position display ────────────────────────────────────────────────────
const totalCash = computed(() => props.cashFlow.total_cash ?? props.cashFlow.liquid_cash ?? null)
const totalCashClass = computed(() =>
	(props.cashFlow.liquid_cash ?? 0) < 0 ? 'text-ink-red-4' : 'text-ink-gray-9',
)
const cashSublabel = computed((): string | undefined => {
	const fd  = props.cashFlow.fd_balance
	const liq = props.cashFlow.liquid_cash
	if (fd != null && fd > 0 && liq != null) {
		return `incl. ${formatMoney(fd, props.currency, { compact: true })} FDs; liquid ${formatMoney(liq, props.currency, { compact: true })}`
	}
	const runway = props.cashFlow.runway_months
	if (runway == null) return undefined
	return runway === 0 ? 'Overdrawn' : `${runway.toFixed(1)} months runway`
})

// ── Aging segments ───────────────────────────────────────────────────────────
const arSegments = computed(() => toAgingSegments(props.receivables.aging_buckets ?? []))
const apSegments = computed(() => toAgingSegments(props.payables.aging_buckets ?? []))

const arAgingLabel = computed(() =>
	arSegments.value.map(s => `${s.bucket} ${s.pct}%`).join(', ') || 'No AR aging data',
)
const apAgingLabel = computed(() =>
	apSegments.value.map(s => `${s.bucket} ${s.pct}%`).join(', ') || 'No AP aging data',
)

// ── Expense breakdown ────────────────────────────────────────────────────────
const topExpenses = computed(() =>
	(props.data.expense_breakdown ?? []).filter(e => (e.amount ?? 0) > 0),
)

// ── Financial health ─────────────────────────────────────────────────────────
const healthScoreItems = computed(() => {
	const hs = props.executiveSummary?.health_scores
	if (!hs) return []
	function cls(score: number): { bgClass: string; textClass: string } {
		if (score >= 60) return { bgClass: 'bg-surface-green-2', textClass: 'text-ink-green-3' }
		if (score >= 40) return { bgClass: 'bg-surface-amber-2', textClass: 'text-warn' }
		return { bgClass: 'bg-surface-red-2', textClass: 'text-ink-red-4' }
	}
	return [
		{ label: 'Liquidity',     value: hs.liquidity,     status: hs.liquidity_status,     ...cls(hs.liquidity) },
		{ label: 'Profitability', value: hs.profitability, status: hs.profitability_status, ...cls(hs.profitability) },
		{ label: 'Efficiency',    value: hs.efficiency,    status: hs.efficiency_status,    ...cls(hs.efficiency) },
	]
})

// ── Attention rail — computed from live payload fields ───────────────────────
const attentionItems = computed((): AttentionItem[] => {
	const items: Array<AttentionItem & { _order: number }> = []
	const cf  = props.cashFlow
	const es  = props.executiveSummary
	const rec = props.receivables

	// 1. Cash runway — overdrawn or very short liquid position
	const liq  = cf.liquid_cash
	const fd   = cf.fd_balance
	const burn = cf.net_burn_rate
	if (liq != null && liq <= 0) {
		const fdPart   = (fd != null && fd > 0)
			? ` FDs ${formatMoney(fd, props.currency, { compact: true })} buffer but not immediately liquid.`
			: ''
		const burnPart = burn != null && burn > 0
			? ` Burn ${formatMoney(burn, props.currency, { compact: true })}/month.`
			: ''
		items.push({
			title: 'Critical Cash Runway',
			badge: 'High', severity: 'high',
			description: `Liquid cash ${formatMoney(liq, props.currency, { compact: true })}.${fdPart}${burnPart}`,
			action: 'Accelerate collections; review FD drawdown',
			_order: 0,
		})
	} else if (cf.runway_months != null && cf.runway_months < 3 && cf.runway_months > 0) {
		items.push({
			title: 'Low Cash Runway',
			badge: 'High', severity: 'high',
			description: `Only ${cf.runway_months.toFixed(1)} months of liquid runway.`,
			action: 'Review cash forecast tab',
			_order: 0,
		})
	}

	// 2. Revenue YoY decline
	const growth = revenueGrowth.value
	if (growth != null && growth < -10) {
		const ytd   = props.data.ytd_revenue
		const prior = es?.prior_period_revenue
		const parts: string[] = []
		if (ytd != null && prior != null)
			parts.push(`${formatMoney(ytd, props.currency, { compact: true })} vs ${formatMoney(prior, props.currency, { compact: true })} prior period.`)
		const lastMonth = trend.value[trend.value.length - 1]
		if (lastMonth)
			parts.push(`${formatPeriod(lastMonth.period)} ${formatMoney(lastMonth.revenue, props.currency, { compact: true })}: lowest in 12 months.`)
		items.push({
			title: `Revenue ${growth > 0 ? '+' : ''}${growth.toFixed(1)}% YoY`,
			badge: 'High', severity: 'high',
			description: parts.join(' '),
			action: 'Root cause analysis; recovery plan',
			_order: 1,
		})
	}

	// 3. AR 31-60d bucket
	const ar3160 = rec.aging_buckets?.find(b => b.bucket === '31-60 Days')
	if (ar3160 != null && ar3160.amount > 0) {
		items.push({
			title: `AR 31–60d ${formatMoney(ar3160.amount, props.currency, { compact: true })}`,
			badge: 'Medium', severity: 'medium',
			description: `${ar3160.count} invoice${ar3160.count !== 1 ? 's' : ''} in 31–60 day bucket.`,
			action: 'Priority chase; Receivables tab',
			_order: 2,
		})
	}

	// 4. Thin gross margin
	const gm = es?.gross_margin
	const topExp = topExpenses.value[0]
	if (gm != null && gm < 15) {
		const expNote = topExp
			? `${topExp.category.replace(/ - JKM$/, '')} ${topExp.pct}% of opex. `
			: ''
		const nm = props.data.net_margin
		items.push({
			title: `Gross Margin ${gm.toFixed(1)}%`,
			badge: 'Monitor', severity: 'none',
			description: `${expNote}Thin buffer above EBITDA of ${nm != null ? nm.toFixed(1) : '–'}%.`,
			action: 'Cost Structure tab',
			_order: 3,
		})
	}

	return items.sort((a, b) => a._order - b._order)
})
</script>
