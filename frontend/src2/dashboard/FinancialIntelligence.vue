<template>
	<div class="flex flex-col h-full bg-surface-gray-1">
		<!-- Header -->
		<header class="bg-surface-white border-b border-outline-gray-1 px-6 py-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
			<div>
				<h1 class="text-2xl font-bold text-ink-gray-9">Finance</h1>
				<p class="text-sm text-ink-gray-6 mt-1">Actuals and forward-looking planning in one place</p>
			</div>
			<div class="flex flex-wrap items-center gap-3">
				<IntelligenceDateFilter v-model="dateFilter" />
				<span v-if="lastUpdated" class="text-sm text-ink-gray-6">
					Updated: {{ formatDate(lastUpdated) }}
				</span>
				<Button
					variant="solid"
					@click="refreshData"
					:loading="loading"
					icon-left="refresh-cw"
				>
					Refresh
				</Button>
			</div>
		</header>

		<!-- Summary Cards: gated on hasData to prevent false zero amounts during first fetch -->
		<div class="p-6 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
			<KpiCard
				label="Net Profit (YTD)"
				:amount="summary.netProfit"
				:currency="baseCurrency"
				:delta="summary.profitMargin || undefined"
				:delta-higher-is-better="true"
				sublabel="margin"
				:loading="loading && !hasData"
				:error="actualsError ?? undefined"
			/>
			<KpiCard
				label="Cash Position"
				:amount="summary.cashPosition"
				:currency="baseCurrency"
				:sublabel="cashRunwayLabel"
				:clickable="true"
				:loading="loading && !hasData"
				:error="actualsError ?? undefined"
				@click="drillDown.open(FIN_ENDPOINT, 'Cash Position', { metric: 'cash_accounts' })"
			/>
			<KpiCard
				label="Outstanding AR"
				:amount="summary.outstandingAR"
				:currency="baseCurrency"
				:sublabel="summary.avgDSO != null ? `${summary.avgDSO} days DSO` : undefined"
				:severity="scoreSeverity(summary.avgDSO, { good: 30, warn: 60, higherIsBetter: false })"
				:clickable="true"
				:loading="loading && !hasData"
				:error="actualsError ?? undefined"
				@click="drillDown.open(FIN_ENDPOINT, 'Outstanding AR', { metric: 'outstanding_ar' })"
			/>
			<KpiCard
				label="Outstanding AP"
				:amount="summary.outstandingAP"
				:currency="baseCurrency"
				:sublabel="summary.avgDPO != null ? `${summary.avgDPO} days DPO` : undefined"
				:clickable="true"
				:loading="loading && !hasData"
				:error="actualsError ?? undefined"
				@click="drillDown.open(FIN_ENDPOINT, 'Outstanding AP', { metric: 'outstanding_ap' })"
			/>
			<KpiCard
				label="Working Capital"
				:amount="strategicSummary.workingCapital"
				:currency="baseCurrency"
				:sublabel="currentRatioLabel"
				:loading="strategicLoading && !strategicData"
				:error="strategicError ?? undefined"
			/>
			<KpiCard
				label="Forex Exposure"
				:amount="summary.forexExposure"
				:currency="baseCurrency"
				:sublabel="forexSublabel"
				:loading="loading && !hasData"
				:error="actualsError ?? undefined"
			/>
		</div>

		<!-- Tabs -->
		<div class="mx-6 flex flex-col gap-2">
			<!--
				Two levels, two visual weights: a filled segmented control for the
				group (recorded facts versus projection) and underlined tabs for the
				views inside it. Previously this row was a label that only reported
				which group the selected tab happened to belong to.
			-->
			<TabButtons v-model="activeGroup" :buttons="GROUP_BUTTONS" class="self-start" />
			<Tabs v-model="tabIndex" :tabs="tabDefs" />
		</div>

		<!-- Tab Content -->
		<div class="flex-1 p-6 overflow-auto">
			<!--
				One error panel for the whole group, rather than letting each tab
				render `|| 0` fallbacks. Fixing only the KPI strip made the page
				contradict itself: the strip read "Unavailable" while the P&L panel
				directly beneath it still asserted "KES 0" for revenue.

				Scoped per group on purpose. The two engines fail independently, so
				an actuals outage must not blank the planning tabs or vice versa.
			-->
			<div
				v-if="activeTabError"
				class="flex flex-col items-center justify-center gap-3 py-16 text-center"
			>
				<AlertTriangle class="h-8 w-8 text-warn-fill" aria-hidden="true" />
				<p class="font-medium text-ink-gray-8">
					{{ activeGroup === 'actuals' ? 'Actuals' : 'Planning' }} data could not be loaded
				</p>
				<p class="max-w-md text-sm text-ink-gray-6">{{ activeTabError }}</p>
				<Button variant="solid" @click="refreshData">Try again</Button>
			</div>

			<!-- All tab bodies sit under one `v-else`: each is its own `v-if` chain,
			     so without this wrapper they would render alongside the error panel
			     above rather than instead of it. -->
			<template v-else>
			<!-- Actuals: Overview -->
			<div v-if="activeTab === 'overview'" class="space-y-6">
				<ExecutiveSummaryTab :data="strategicTyped?.executive_summary ?? null" :expense-breakdown="strategicTyped?.expense_breakdown" />
				<OverviewTab :data="overviewData" :currency="baseCurrency" />
			</div>

			<!-- Actuals: Cash -->
			<div v-if="activeTab === 'cashflow'">
				<CashFlowTab :data="cashFlowData" :currency="baseCurrency" />
			</div>

			<!-- Actuals: Receivables -->
			<div v-if="activeTab === 'receivables'">
				<ReceivablesTab :data="receivablesData" :currency="baseCurrency" :fin-endpoint="FIN_ENDPOINT" :drill-down="drillDown" />
			</div>

			<!-- Actuals: Payables -->
			<div v-if="activeTab === 'payables'">
				<PayablesTab :data="payablesData" :currency="baseCurrency" :fin-endpoint="FIN_ENDPOINT" :drill-down="drillDown" />
			</div>

			<!-- Actuals: Working Capital -->
			<div v-if="activeTab === 'working'">
				<WorkingCapitalTab :data="strategicTyped?.working_capital" />
			</div>

			<!-- Actuals: Ratios & Trends -->
			<div v-if="activeTab === 'ratios'">
				<FinancialRatiosTab :data="strategicTyped?.ratio_trends" />
			</div>

			<!-- Actuals: Cost Structure -->
			<div v-if="activeTab === 'costratios'">
				<CostStructureTab
					:data="strategicTyped?.cost_structure ?? null"
					:forecast="strategicTyped?.expense_forecast ?? null"
					:currency="baseCurrency"
				/>
			</div>

			<!-- Actuals: Forex Exposure -->
			<div v-if="activeTab === 'forex'">
				<ForexExposureTab :data="forexData" :currency="baseCurrency" />
			</div>

			<!-- Planning: Cash Forecast -->
			<div v-if="activeTab === 'cashforecast'">
				<CashForecastingTab :data="strategicTyped?.cash_forecast ?? null" />
			</div>

			<!-- Planning: 13-Week Cash Flow -->
			<div v-if="activeTab === 'cashflow13'">
				<ThirteenWeekCashFlowTab :data="strategicTyped?.thirteen_week_forecast ?? null" />
			</div>

			<!-- Planning: Capital Planning -->
			<div v-if="activeTab === 'capital'">
				<CapitalPlanningTab :data="strategicTyped?.capital_planning" />
			</div>

			<!-- Planning: Scenario Analysis -->
			<div v-if="activeTab === 'scenarios'">
				<ScenarioAnalysisTab :data="strategicTyped?.scenario_analysis" />
			</div>

			<!-- Planning: Period Comparison -->
			<div v-if="activeTab === 'comparison'">
				<PeriodComparisonTab :data="strategicTyped?.period_comparison" />
			</div>

			<!-- Planning: Budget Variance -->
			<div v-if="activeTab === 'budget'">
				<BudgetVarianceTab />
			</div>

			<!-- Planning: Break-Even Overview -->
			<div v-if="activeTab === 'beOverview'">
				<div v-if="beLoading" class="flex items-center justify-center py-12">
					<LoadingIndicator class="w-8 h-8" />
				</div>
				<div v-else-if="beError" class="text-center py-12 text-ink-gray-6">{{ beError }}</div>
				<BreakEvenOverviewTab v-else-if="beData" :data="beData" />
				<div v-else class="text-center py-12 text-ink-gray-6">No break-even data available</div>
			</div>
			</template>
		</div>

		<!-- AI Chat Button -->
		<DashboardChatButton
			dashboard-type="Financial"
			:dashboard-context="chatContext"
			@navigate-dashboard="handleDashboardRedirect"
		/>

		<IntelligenceDrillDown
			v-model:show="drillDown.show.value"
			:title="drillDown.title.value"
			:columns="drillDown.columns.value"
			:rows="drillDown.rows.value"
			:loading="drillDown.loading.value"
			:error="drillDown.error.value"
			:is-permission-error="drillDown.isPermissionError.value"
			:total="drillDown.total.value"
			:page="drillDown.page.value"
			@next-page="drillDown.nextPage()"
			@prev-page="drillDown.prevPage()"
			@close="drillDown.close()"
			@retry="drillDown.retry()"
		/>
	</div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FinancialIntelligence' })
import { ref, computed, onMounted, watch, provide } from 'vue'
import { Button, Tabs, TabButtons, createResource, LoadingIndicator } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { AlertTriangle } from 'lucide-vue-next'
import { groupButtons, useGroupedTabs } from '../composables/useGroupedTabs'
import { scoreSeverity } from '../utils/status'
import { formatCount } from '../utils/format'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'
import KpiCard from '../intelligence/components/KpiCard.vue'
import { formatDate } from '../components/financial/format'
import type {
	OverviewData, CashFlowData, ReceivablesData, PayablesData, ForexData,
} from '../components/financial/types'
import type { StrategicFinanceData } from '../components/strategic-finance/types'

// Actuals tab components (this dashboard's own, extracted verbatim from the
// pre-merge monolith)
import OverviewTab from '../components/financial/OverviewTab.vue'
import CashFlowTab from '../components/financial/CashFlowTab.vue'
import ReceivablesTab from '../components/financial/ReceivablesTab.vue'
import PayablesTab from '../components/financial/PayablesTab.vue'
import ForexExposureTab from '../components/financial/ForexExposureTab.vue'

// Planning tab components (reused from the former Strategic Finance
// dashboard, unmodified — they already self-contain their own formatting
// and severity logic via `inject('currency')`)
import ExecutiveSummaryTab from '../components/strategic-finance/ExecutiveSummaryTab.vue'
import WorkingCapitalTab from '../components/strategic-finance/WorkingCapitalTab.vue'
import FinancialRatiosTab from '../components/strategic-finance/FinancialRatiosTab.vue'
import CostStructureTab from '../components/strategic-finance/CostStructureTab.vue'
import CashForecastingTab from '../components/strategic-finance/CashForecastingTab.vue'
import ThirteenWeekCashFlowTab from '../components/strategic-finance/ThirteenWeekCashFlowTab.vue'
import CapitalPlanningTab from '../components/strategic-finance/CapitalPlanningTab.vue'
import ScenarioAnalysisTab from '../components/strategic-finance/ScenarioAnalysisTab.vue'
import PeriodComparisonTab from '../components/strategic-finance/PeriodComparisonTab.vue'
import BudgetVarianceTab from '../components/strategic-finance/BudgetVarianceTab.vue'
import BreakEvenOverviewTab from '../components/strategic-finance/BreakEvenOverviewTab.vue'
import { ignoreRejection } from '../helpers/api'

interface FrappeResponse { status: string; message?: string; [key: string]: unknown }

// Mirrors BreakEvenOverviewTab.vue's local interfaces; declared here so beData
// can carry the correct type for the tab prop.
interface CashFlowBreakeven {
	breakeven_month: string | null
	total_cash_in: number
	total_cash_out: number
	coverage: number
	rag: string
}
interface BeDeparmtent {
	department: string
	payroll_cost: number
	orders_needed: number
	actual_orders: number
	coverage: number
	rag: string
}
interface RoceData { roce: number; target: number; capital_employed: number; ebit: number; rag: string }
interface IrrData { irr: number | null }
interface BreakevenSummary {
	fixed_costs: number
	variable_costs: number
	be_revenue: number
	be_qty: number
	actual_revenue: number
	coverage: number
	safety_margin: number
	rag: string
	cash_flow_breakeven?: CashFlowBreakeven
	employee_breakeven?: { departments: BeDeparmtent[] }
	roce?: RoceData
	irr?: IrrData
}

const router = useRouter()

type TabGroup = 'actuals' | 'planning'

const tabs: { id: string; label: string; group: TabGroup }[] = [
	{ id: 'overview', label: 'Overview', group: 'actuals' },
	{ id: 'cashflow', label: 'Cash', group: 'actuals' },
	{ id: 'receivables', label: 'Receivables', group: 'actuals' },
	{ id: 'payables', label: 'Payables', group: 'actuals' },
	{ id: 'working', label: 'Working Capital', group: 'actuals' },
	{ id: 'ratios', label: 'Ratios & Trends', group: 'actuals' },
	{ id: 'costratios', label: 'Cost Structure', group: 'actuals' },
	{ id: 'forex', label: 'Forex Exposure', group: 'actuals' },
	{ id: 'cashforecast', label: 'Cash Forecast', group: 'planning' },
	{ id: 'cashflow13', label: '13-Week Cash Flow', group: 'planning' },
	{ id: 'capital', label: 'Capital Planning', group: 'planning' },
	{ id: 'scenarios', label: 'Scenario Analysis', group: 'planning' },
	{ id: 'comparison', label: 'Period Comparison', group: 'planning' },
	{ id: 'budget', label: 'Budget Variance', group: 'planning' },
	{ id: 'beOverview', label: 'Break-Even Overview', group: 'planning' },
]
/**
 * The group is the primary axis, not a caption.
 *
 * Every tab already declared a `group`, the content was already routed by it,
 * and the two groups are fed by two independent fetches whose errors are scoped
 * per group. Only the strip stayed flat, so fourteen peer tabs sat in one row
 * and the group label above them was a read-back of the current selection
 * rather than a control. This completes the structure already declared here; it
 * does not invent one.
 *
 * Actuals are recorded facts, Planning is projection. On an audit surface that
 * distinction is worth making navigable rather than incidental.
 */
const TAB_GROUPS: readonly TabGroup[] = ['actuals', 'planning']
const GROUP_BUTTONS = groupButtons(TAB_GROUPS)

const {
	activeGroup,
	tabItems: tabDefs,
	activeTabIndex: tabIndex,
	activeTab: activeTabDef,
} = useGroupedTabs(tabs, TAB_GROUPS)

/** Template and chat context key off the id, as they did before. */
const activeTab = computed(() => activeTabDef.value?.id ?? 'overview')

/**
 * Error for whichever engine feeds the active tab.
 *
 * The actuals and planning engines are separate fetches that fail
 * independently, so a single dashboard-wide error flag would blank working
 * tabs. Declared after both refs exist; see `actualsError` / `strategicError`.
 */
const activeTabError = computed(() =>
	activeGroup.value === 'actuals' ? actualsError.value : strategicError.value,
)

const loading = ref(false)
const lastUpdated = ref<string | null>(null)
const dateFilter = ref('12m')
const baseCurrency = ref('KES')
provide('currency', baseCurrency)

// Actuals data (from insights.api.ml.financial_intelligence)
const overviewData = ref<OverviewData>({})
const cashFlowData = ref<CashFlowData>({})
const receivablesData = ref<ReceivablesData>({})
const payablesData = ref<PayablesData>({})
const forexData = ref<ForexData>({})

const fetched = ref(false)
const hasData = computed(() => fetched.value)

/**
 * Set when the actuals fetch did not yield usable data, so the KPI strip can
 * say so instead of rendering `|| 0` as a real figure.
 *
 * Two distinct paths land here. `onError` is the obvious one; the other is a
 * 200 response carrying `status !== 'success'`, which used to fall straight
 * through to `fetched = true` with every data ref still empty.
 */
const actualsError = ref<string | null>(null)

const FIN_ENDPOINT = 'insights.api.ml.financial.get_finance_detail'
const drillDown = useDrillDown()

const summary = computed(() => ({
	netProfit: (overviewData.value.ytd_profit as number) || 0,
	profitMargin: (overviewData.value.net_margin as number) || 0,
	cashPosition: (cashFlowData.value.total_cash as number) || 0,
	cashRunwayMonths: cashFlowData.value.runway_months as number | undefined,
	outstandingAR: (receivablesData.value.total_outstanding as number) || 0,
	avgDSO: receivablesData.value.current_dso != null ? Math.round(receivablesData.value.current_dso as number) : undefined,
	outstandingAP: (payablesData.value.total_outstanding as number) || 0,
	avgDPO: payablesData.value.current_dpo != null ? Math.round(payablesData.value.current_dpo as number) : undefined,
	forexExposure: Math.abs((forexData.value.net_exposure_base as number) || 0),
	forexCurrencies: forexData.value.exposure_summary?.length || undefined,
}))

/**
 * Runway in the units the server measures it in, and never as a sentinel.
 *
 * `financial_intelligence.py:272` returns `999` when net burn is zero or
 * negative -- a flag for "not consuming cash", not a measurement. This card
 * multiplied it by 30 and rendered "29970 days runway": an 82-year forecast
 * presented as fact, and to the day, from a figure derived from monthly
 * averages. The strategic engine reports the same concept as 49.6 months, so
 * the day conversion also put two different units for one metric on one screen.
 */
const cashRunwayLabel = computed(() => {
	const months = summary.value.cashRunwayMonths
	if (months === null || months === undefined || !Number.isFinite(months)) return undefined
	// The server's "effectively unbounded" flag. Saying so beats inventing a date.
	if (months >= 999) return 'no net cash burn'
	return `${formatCount(months, { decimals: 1 })} months runway`
})

/** Singular/plural currency label; absent when exposure count is unknown or zero. */
const forexSublabel = computed(() => {
	const n = summary.value.forexCurrencies
	if (n == null) return undefined
	return `${n} ${n === 1 ? 'currency' : 'currencies'}`
})

const financialResource = createResource({
	url: 'insights.api.ml.financial_intelligence',
	auto: false,
	onSuccess(data: Record<string, unknown>) {
		if (data.status === 'success') {
			overviewData.value = ((data.overview ?? {}) as OverviewData)
			cashFlowData.value = ((data.cash_flow ?? {}) as CashFlowData)
			receivablesData.value = ((data.receivables ?? {}) as ReceivablesData)
			payablesData.value = ((data.payables ?? {}) as PayablesData)
			forexData.value = ((data.forex ?? {}) as ForexData)
			lastUpdated.value = (data.generated_at as string) || null
			actualsError.value = null
			if (data.base_currency) {
				baseCurrency.value = data.base_currency as string
			}
		} else {
			actualsError.value = (data.message as string) || 'Financial data could not be loaded'
		}
		fetched.value = true
		loading.value = false
	},
	onError(err: unknown) {
		console.error('Financial Intelligence error:', err)
		actualsError.value = 'Financial data could not be loaded'
		fetched.value = true
		loading.value = false
	},
})

// Planning data (from insights.api.ml.strategic_finance_intelligence) —
// single canonical source for ratios, working capital, and every
// forward-looking tab. Fetched in parallel with the actuals resource.
const strategicLoading = ref(false)
const strategicData = ref<Record<string, unknown> | null>(null)
/** Mirrors `actualsError` for the planning engine; same two failure paths. */
const strategicError = ref<string | null>(null)
const strategicTyped = computed<StrategicFinanceData | null>(() => strategicData.value as unknown as StrategicFinanceData | null)

/**
 * Absent, not zero, when the planning engine has not answered.
 *
 * This returned `{ workingCapital: 0, currentRatio: 0 }` for a null payload, so
 * the card reported working capital of nothing and a current ratio of 0.00 --
 * a solvency crisis -- whenever the second fetch was merely slow or failed.
 */
const strategicSummary = computed(() => {
	const wc = (strategicData.value?.['working_capital'] as Record<string, number> | undefined) ?? {}
	const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : undefined)
	return {
		workingCapital: num(wc['working_capital']),
		currentRatio: num(wc['current_ratio']),
	}
})

/** Omitted entirely rather than asserting a ratio the server never sent. */
const currentRatioLabel = computed(() =>
	strategicSummary.value.currentRatio === undefined
		? undefined
		: `Current Ratio: ${strategicSummary.value.currentRatio.toFixed(2)}`,
)

const strategicResource = createResource({
	url: 'insights.api.ml.strategic_finance_intelligence',
	auto: false,
	onSuccess(response: FrappeResponse) {
		if (response && response.status === 'success') {
			strategicData.value = response as Record<string, unknown>
			strategicError.value = null
		} else {
			strategicError.value = response?.message || 'Planning data could not be loaded'
		}
		strategicLoading.value = false
	},
	onError(err: unknown) {
		console.error('Strategic Finance Intelligence error:', err)
		strategicError.value = 'Planning data could not be loaded'
		strategicLoading.value = false
	},
})

const fetchStrategicData = (refresh = false) => {
	strategicLoading.value = true
	ignoreRejection(strategicResource.submit({ refresh }))
}

const refreshData = () => {
	loading.value = true
	ignoreRejection(financialResource.submit({ refresh: true, date_filter: dateFilter.value }))
	fetchStrategicData(true)
}

onMounted(() => {
	loading.value = true
	ignoreRejection(financialResource.submit({ refresh: false, date_filter: dateFilter.value }))
	fetchStrategicData(false)
})

watch(dateFilter, () => {
	loading.value = true
	ignoreRejection(financialResource.submit({ refresh: false, date_filter: dateFilter.value }))
})

// Break-even state — lazy-loaded on first visit to that tab, same as the
// pre-merge Strategic Finance dashboard.
const beData = ref<BreakevenSummary | null>(null)
const beLoading = ref(false)
const beError = ref<string | null>(null)

const beSummaryResource = createResource({
	url: 'insights.api.ml.breakeven.breakeven_summary',
	auto: false,
	onSuccess(response: FrappeResponse) {
		if (response && response.status === 'success') {
			beData.value = (response['data'] as unknown as BreakevenSummary) || null
			beError.value = null
		} else {
			beError.value = response?.message || 'Failed to load break-even data'
		}
		beLoading.value = false
	},
	onError(err: unknown) {
		console.error('Break-even summary error:', err)
		beError.value = 'An error occurred while loading break-even data'
		beLoading.value = false
	},
})

const fetchBreakEvenData = () => {
	beLoading.value = true
	beError.value = null
	ignoreRejection(beSummaryResource.submit({}))
}

// Watches the id, not the index: the index is group-relative now, so
// `tabs[idx]` would resolve against the wrong tab once Planning is selected.
watch(activeTab, (tabId) => {
	if (tabId?.startsWith('be') && !beData.value) {
		fetchBreakEvenData()
	}
})

// Chat context for AI insights — combines both engines.
const chatContext = computed(() => ({
	summary: summary.value,
	overview: overviewData.value,
	cashFlow: cashFlowData.value,
	receivables: receivablesData.value,
	payables: payablesData.value,
	forex: forexData.value,
	executiveSummary: (strategicData.value?.['executive_summary'] as Record<string, unknown>) || {},
	workingCapital: (strategicData.value?.['working_capital'] as Record<string, unknown>) || {},
	activeTab: activeTab.value,
	lastUpdated: lastUpdated.value,
}))

// Handle navigation to other dashboards from chat suggestions
function handleDashboardRedirect(target: string) {
	const routes: Record<string, string> = {
		'Sales': '/sales-intelligence',
		'Risk': '/risk-intelligence',
		'Inventory': '/inventory-intelligence',
		'Procurement': '/procurement-intelligence',
		'Customer': '/customer-intelligence',
		'Financial': '/financial-intelligence',
	}
	if (routes[target]) {
		router.push(routes[target])
	}
}
</script>
