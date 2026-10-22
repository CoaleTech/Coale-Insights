<script setup lang="ts">
/**
 * Kenya tax dashboard (KRA: VAT, eTIMS, PAYE/NSSF/SHIF/AHL/NITA, withholding,
 * corporation tax, notices, customs, rule-generated action queue).
 *
 * This file is only the shell: tab bar with badge counts, the active tab's KPI
 * strip, date range, load/error states and the drill-down panel. Each tab
 * component in `./tax/` renders from the payload it is handed and never fetches.
 * Payload contract: `./tax/taxTypes.ts`.
 */
defineOptions({ name: 'TaxIntelligence' })
import { Breadcrumbs, Button, Tabs } from 'frappe-ui'
import { Info, RefreshCcw } from 'lucide-vue-next'
import { computed, provide, ref } from 'vue'
import { useRouter } from 'vue-router'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import { asNumber, formatCount, formatDate, formatDateTime, NO_VALUE } from '../utils/format'
import IntelligenceDashboardShell from './components/IntelligenceDashboardShell.vue'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'
import KpiCard from './components/KpiCard.vue'
import SkeletonBlock from './components/SkeletonBlock.vue'
import { useDrillDown } from './composables/useDrillDown'
import { useIntelligenceDashboard } from './composables/useIntelligenceDashboard'
import ActionsTab from './tax/ActionsTab.vue'
import CustomsTab from './tax/CustomsTab.vue'
import EtimsTab from './tax/EtimsTab.vue'
import IncomeTab from './tax/IncomeTab.vue'
import LegalTab from './tax/LegalTab.vue'
import OverviewTab from './tax/OverviewTab.vue'
import PayrollTab from './tax/PayrollTab.vue'
import VatTab from './tax/VatTab.vue'
import WhtTab from './tax/WhtTab.vue'
import type {
	ActionsData, CustomsData, Drill, EtimsData, IncomeData, Kpi, LegalData, OverviewData,
	PayrollData, Rates, TabId, TaxPayload, VatData, WhtData,
} from './tax/taxTypes'
import { TAX_CTX } from './tax/useTax'

const router = useRouter()
const drillDown = useDrillDown()
const TAX_ENDPOINT = 'insights.api.ml.tax.get_tax_detail'

const dateFilter = ref('fy')
// The backend resolves 3m / 6m / 12m / fy (and custom:a:b); this set is local to Tax.
const dateRangeOptions = [
	{ value: '3m', label: 'Last 3 Months' },
	{ value: '6m', label: 'Last 6 Months' },
	{ value: '12m', label: 'Last 12 Months' },
	{ value: 'fy', label: 'Current FY' },
]
const dateParams = computed(() => ({ period: dateFilter.value }))

const { data, loading, refreshing, error, isPermissionError, warming, notImplemented, notImplementedMessage, hasData, reload, retry } =
	useIntelligenceDashboard<TaxPayload>({
		url: 'insights.api.ml.tax.tax_intelligence',
		params: dateParams,
		cache: 'tax-intelligence',
	})

const baseCurrency = computed(() => data.value?.base_currency ?? null)

function openDrill(title: string, drill: Drill) {
	drillDown.open(TAX_ENDPOINT, title, {
		...drill.filters,
		metric: drill.metric,
		period: dateFilter.value,
		company: data.value?.company,
	})
}
provide(TAX_CTX, { currency: baseCurrency, openDrill })

const TABS: { id: TabId; label: string; badge?: keyof TaxPayload['badges'] }[] = [
	{ id: 'overview', label: 'Overview' },
	{ id: 'vat', label: 'VAT' },
	{ id: 'etims', label: 'eTIMS', badge: 'etims' },
	{ id: 'payroll', label: 'Payroll taxes', badge: 'payroll' },
	{ id: 'wht', label: 'Withholding', badge: 'wht' },
	{ id: 'income', label: 'Income tax' },
	{ id: 'legal', label: 'Notices & Legal', badge: 'legal' },
	{ id: 'customs', label: 'Customs & Excise' },
	{ id: 'actions', label: 'Action queue', badge: 'actions' },
]
const activeIndex = ref(0)
const activeId = computed(() => TABS[activeIndex.value]?.id ?? 'overview')
const tabItems = computed(() =>
	TABS.map((t) => ({ label: t.label, count: t.badge ? (data.value?.badges?.[t.badge] ?? 0) : 0 })),
)
function goTab(id: TabId) {
	const i = TABS.findIndex((t) => t.id === id)
	if (i >= 0) activeIndex.value = i
}

const active = computed(() => data.value?.tabs?.[activeId.value])
const unavailable = computed(() => (active.value && !active.value.available ? active.value.message : null))

// Whole-class lookups: the KPI strip's tone drives the card's severity badge.
const SEVERITY = { neutral: 'none', warn: 'medium', bad: 'high', good: 'none' } as const
function kpiProps(k: Kpi) {
	const v = k.value
	const base = {
		label: k.label,
		severity: SEVERITY[k.tone ?? 'neutral'],
	}
	switch (k.unit) {
		case 'money': return { ...base, amount: asNumber(v) ?? null, currency: baseCurrency.value }
		case 'pct': return { ...base, percent: asNumber(v) ?? null }
		case 'count': return { ...base, value: asNumber(v) === undefined ? null : formatCount(asNumber(v) as number) }
		case 'date': return { ...base, value: typeof v === 'string' ? formatDate(v.length === 10 ? `${v}T00:00:00` : v) : NO_VALUE }
		default: return { ...base, value: v === null || v === undefined ? null : String(v) }
	}
}
const kpiCards = computed(() => (active.value?.kpis ?? []).map((k) => ({ key: k.key, drill: k.drill, sub: k.sub, props: kpiProps(k) })))

const pc = (v: number) => `${+(v * 100).toFixed(2)}%`
const FOOTERS: Record<TabId, (r: Rates) => string> = {
	overview: (r) => `VAT ${pc(r.vat_rate)} · corporation tax ${pc(r.cit_rate)} · SHIF ${pc(r.shif_rate)} · housing levy ${pc(r.ahl_rate)}`,
	vat: (r) => `VAT standard rate ${pc(r.vat_rate)} · registration threshold ${formatCount(r.vat_registration_threshold, { compact: true })} · input VAT claim window ${r.input_vat_window_months} months`,
	etims: (r) => `Corporation tax ${pc(r.cit_rate)} applied to spend without an eTIMS invoice`,
	payroll: (r) => `SHIF ${pc(r.shif_rate)} (minimum ${formatCount(r.shif_min)}) · housing levy ${pc(r.ahl_rate)} · NITA ${formatCount(r.nita_per_employee)} per employee · NSSF limits ${formatCount(r.nssf_lel)} to ${formatCount(r.nssf_uel)} · personal relief ${formatCount(r.personal_relief)}`,
	wht: () => 'Withholding rates are those in the rate card above',
	income: (r) => `Corporation tax ${pc(r.cit_rate)} · TOT ${pc(r.tot_rate)} on turnover from ${formatCount(r.tot_min, { compact: true })} to ${formatCount(r.tot_max, { compact: true })} · CGT ${pc(r.cgt_rate)}`,
	legal: () => 'Deadlines are computed from the notice, objection and decision dates on each case',
	customs: (r) => `IDF ${pc(r.idf_rate)} · RDL ${pc(r.rdl_rate)} · SEP tax ${pc(r.sep_rate)} · import VAT ${pc(r.vat_rate)}`,
	actions: () => 'Actions are generated from the other tabs each time the dashboard runs',
}
const footer = computed(() => (data.value ? `Rates from ${data.value.rates.law_basis}. ${FOOTERS[activeId.value](data.value.rates)}.` : ''))

const chatContext = computed(() => ({
	dashboard: 'Kenya tax (KRA)',
	company: data.value?.company,
	period: data.value?.period?.name,
	date_filter: dateFilter.value,
	activeTab: activeId.value,
	badges: data.value?.badges,
	kpis: (active.value?.kpis ?? []).map((k) => ({ label: k.label, value: k.value, unit: k.unit, note: k.sub })),
}))

function handleDashboardRedirect(target: string) {
	const routes: Record<string, string> = {
		Sales: '/sales-intelligence', Risk: '/risk-intelligence', Inventory: '/inventory-intelligence',
		Financial: '/financial-intelligence', Customer: '/customer-intelligence',
		Procurement: '/procurement-intelligence', Tax: '/tax-intelligence',
	}
	if (routes[target]) router.push(routes[target])
}
</script>

<template>
	<div class="flex h-full flex-col bg-surface-gray-1">
		<div class="flex flex-col items-start gap-3 border-b border-outline-gray-1 bg-surface-white px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
			<div>
				<Breadcrumbs :items="[{ label: 'Dashboards', route: '/dashboards' }, { label: 'Tax Intelligence' }]" />
				<h1 class="mt-1 text-2xl font-bold text-ink-gray-9">Tax Intelligence</h1>
				<p class="text-sm text-ink-gray-6">
					Kenya · KRA iTax / eTIMS<template v-if="data"> · {{ data.company }} · All figures in {{ data.base_currency ?? 'the company currency' }}</template>
				</p>
			</div>
			<div class="flex flex-wrap items-center gap-3">
				<span v-if="data" class="text-sm text-ink-gray-6">Updated {{ formatDateTime(data.generated_at) }}</span>
				<IntelligenceDateFilter v-model="dateFilter" :options="dateRangeOptions" />
				<Button :loading="refreshing" variant="solid" theme="gray" @click="reload">
					<template #prefix><RefreshCcw class="h-4 w-4" /></template>
					{{ refreshing ? 'Refreshing...' : 'Refresh Analysis' }}
				</Button>
			</div>
		</div>

		<IntelligenceDashboardShell
			:loading="loading"
			:refreshing="refreshing"
			:error="error"
			:is-permission-error="isPermissionError"
			:warming="warming"
			:not-implemented="notImplemented"
			:not-implemented-message="notImplementedMessage"
			:has-data="hasData"
			subject="tax data"
			permission-hint="Ask an administrator for tax dashboard access."
			@retry="retry"
		>
			<template #skeleton>
				<div class="flex flex-1 items-center justify-center gap-4 py-16">
					<div class="flex flex-col items-center gap-4">
						<div class="grid w-96 grid-cols-3 gap-3">
							<SkeletonBlock v-for="n in 6" :key="n" class="h-24 rounded-xl" />
						</div>
						<p class="text-sm text-ink-gray-6">Loading tax intelligence...</p>
					</div>
				</div>
			</template>

			<div v-if="data" class="space-y-4 p-6">
				<Tabs v-model="activeIndex" :tabs="tabItems">
					<template #tab-item="{ tab, selected }">
						<button
							class="flex items-center gap-1.5 whitespace-nowrap py-3 text-base duration-300 ease-in-out hover:text-ink-gray-9"
							:class="selected ? 'font-medium text-ink-gray-9' : 'text-ink-gray-6'"
						>
							{{ tab.label }}
							<span
								v-if="tab.count > 0"
								class="tnum rounded-full bg-surface-red-1 px-1.5 text-xs font-semibold text-neg"
							>
								{{ tab.count }}<span class="sr-only"> items need attention</span>
							</span>
						</button>
					</template>
				</Tabs>

				<!-- Up to six KPIs, three to a row: exact money does not fit six across. -->
				<div v-if="kpiCards.length" class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
					<KpiCard
						v-for="k in kpiCards"
						:key="k.key"
						v-bind="k.props"
						:clickable="!!k.drill"
						@click="k.drill && openDrill(k.props.label, k.drill)"
					>
						<!-- Footer, not sublabel: the sublabel truncates to one line and these notes carry the rule. -->
						<template v-if="k.sub" #footer>
							<p class="text-sm text-ink-gray-6">{{ k.sub }}</p>
						</template>
					</KpiCard>
				</div>

				<div v-if="unavailable" class="flex flex-col items-center gap-2 rounded-lg border border-outline-gray-2 bg-card px-6 py-16 text-center">
					<Info class="h-6 w-6 text-ink-gray-5" aria-hidden="true" />
					<p class="text-base font-medium text-ink-gray-8">This tab has no data yet</p>
					<p class="max-w-xl text-sm text-ink-gray-6">{{ unavailable }}</p>
				</div>
				<template v-else-if="active">
					<OverviewTab v-if="activeId === 'overview'" :tab="active as OverviewData" />
					<VatTab v-else-if="activeId === 'vat'" :tab="active as VatData" />
					<EtimsTab v-else-if="activeId === 'etims'" :tab="active as EtimsData" />
					<PayrollTab v-else-if="activeId === 'payroll'" :tab="active as PayrollData" />
					<WhtTab v-else-if="activeId === 'wht'" :tab="active as WhtData" />
					<IncomeTab v-else-if="activeId === 'income'" :tab="active as IncomeData" />
					<LegalTab v-else-if="activeId === 'legal'" :tab="active as LegalData" />
					<CustomsTab v-else-if="activeId === 'customs'" :tab="active as CustomsData" />
					<ActionsTab v-else :tab="active as ActionsData" @navigate="goTab" />
				</template>

				<p class="pt-2 text-sm text-ink-gray-6">{{ footer }}</p>
			</div>
		</IntelligenceDashboardShell>

		<DashboardChatButton dashboard-type="Tax" :dashboard-context="chatContext" @navigate-dashboard="handleDashboardRedirect" />

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
