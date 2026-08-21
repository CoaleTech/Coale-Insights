<!-- frontend/src2/dashboard/PriceIntelligence.vue -->
<!--
  Price Intelligence: where margin actually comes from, and where it leaks.

  Four sections, in the order a pricing conversation happens:

  1. Margin by item — realised price against stock valuation. A negative row
     here means stock left the building below what it cost to hold, which is
     the single strongest signal on this page.
  2. Discount pressure — where the list price is not holding, measured against
     the `price_list_rate` ERPNext itself stamped on the line.
  3. Floor breaches — open quotations priced under a floor jkm_finance
     approved. Absent that app, the section says so rather than showing zero.
  4. Approval queue — pricing requests by workflow state.

  Every number is server-computed (`insights.api.ml.price.get_selling_price_intelligence`)
  and every "unavailable" is rendered as its own message, never as 0: a missing
  measurement and a measured zero are different claims.
-->
<template>
	<div class="flex flex-col h-full bg-surface-gray-1">
		<header class="bg-surface-white border-b border-outline-gray-1 px-6 py-4 flex items-center justify-between">
			<div>
				<h1 class="text-2xl font-bold text-ink-gray-9">Price Intelligence</h1>
				<p class="text-sm text-ink-gray-6 mt-0.5">
					Realised pricing over the last {{ lookbackDays }} days
				</p>
			</div>
			<div class="flex items-center gap-3">
				<span v-if="lastUpdated" class="text-sm text-ink-gray-5">
					Updated {{ formatDateTime(lastUpdated) }}
				</span>
				<Button variant="solid" :loading="refreshing" @click="reload">
					<template #prefix><RefreshCcw class="w-4 h-4" /></template>
					Refresh
				</Button>
			</div>
		</header>

		<IntelligenceDashboardShell
			subject="price intelligence"
			permission-hint="Ask for read access to Sales Invoice."
			:loading="loading"
			:refreshing="refreshing"
			:error="error"
			:is-permission-error="isPermissionError"
			:has-data="hasData"
			:warming="warming"
			:not-implemented="notImplemented"
			:not-implemented-message="notImplementedMessage"
			@retry="retry"
		>
			<div class="p-6 space-y-8">
				<!-- KPI strip: three claims, each derived from one section below. -->
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
					<KpiCard
						label="Items below valuation"
						:value="belowValuation.length"
						:severity="belowValuation.length ? 'critical' : 'good'"
						sublabel="Sold under stock cost"
					/>
					<KpiCard
						label="Discount given"
						:amount="totalDiscount"
						:currency="currency"
						sublabel="Against list price"
					/>
					<KpiCard
						label="Quotations under floor"
						:value="floorBreaches.length"
						:severity="floorBreaches.length ? 'warning' : 'good'"
						:sublabel="floorStatusNote"
					/>
				</div>

				<!-- 1. Margin by item -->
				<section>
					<h2 class="text-lg font-semibold text-ink-gray-8 mb-3">Margin by item</h2>
					<p v-if="!marginRows.length" class="text-sm text-ink-gray-6">
						No invoiced sales in this window.
					</p>
					<table v-else class="w-full text-sm">
						<thead>
							<tr class="text-left text-ink-gray-5 border-b border-outline-gray-1">
								<th class="py-2 pr-4 font-medium">Item</th>
								<th class="py-2 pr-4 font-medium">Group</th>
								<th class="py-2 pr-4 font-medium text-right">Revenue</th>
								<th class="py-2 pr-4 font-medium text-right">Qty</th>
								<th class="py-2 pr-4 font-medium text-right">Avg price</th>
								<th class="py-2 pr-4 font-medium text-right">Valuation</th>
								<th class="py-2 font-medium text-right">Margin</th>
							</tr>
						</thead>
						<tbody>
							<tr
								v-for="row in marginRows"
								:key="row.item_code"
								class="border-b border-outline-gray-1"
							>
								<td class="py-2 pr-4 text-ink-gray-8">
									{{ row.item_name || row.item_code }}
								</td>
								<td class="py-2 pr-4 text-ink-gray-6">{{ row.item_group || '—' }}</td>
								<td class="py-2 pr-4 text-right tabular-nums">{{ money(row.revenue) }}</td>
								<td class="py-2 pr-4 text-right tabular-nums">{{ count(row.qty) }}</td>
								<td class="py-2 pr-4 text-right tabular-nums">{{ money(row.avg_rate) }}</td>
								<td class="py-2 pr-4 text-right tabular-nums">
									{{ row.valuation_rate == null ? '—' : money(row.valuation_rate) }}
								</td>
								<!-- Sign carries the meaning, colour only reinforces it. -->
								<td
									class="py-2 text-right tabular-nums"
									:class="marginClass(row.margin_pct)"
								>
									{{ row.margin_pct == null ? '—' : percent(row.margin_pct) }}
								</td>
							</tr>
						</tbody>
					</table>
				</section>

				<!-- 2. Discount pressure -->
				<section>
					<h2 class="text-lg font-semibold text-ink-gray-8 mb-3">Discount pressure</h2>
					<p v-if="!discountRows.length" class="text-sm text-ink-gray-6">
						No line sold below its list price in this window.
					</p>
					<table v-else class="w-full text-sm">
						<thead>
							<tr class="text-left text-ink-gray-5 border-b border-outline-gray-1">
								<th class="py-2 pr-4 font-medium">Item</th>
								<th class="py-2 pr-4 font-medium text-right">Lines</th>
								<th class="py-2 pr-4 font-medium text-right">List value</th>
								<th class="py-2 pr-4 font-medium text-right">Realised</th>
								<th class="py-2 font-medium text-right">Discount</th>
							</tr>
						</thead>
						<tbody>
							<tr
								v-for="row in discountRows"
								:key="row.item_code"
								class="border-b border-outline-gray-1"
							>
								<td class="py-2 pr-4 text-ink-gray-8">
									{{ row.item_name || row.item_code }}
								</td>
								<td class="py-2 pr-4 text-right tabular-nums">{{ count(row.line_count) }}</td>
								<td class="py-2 pr-4 text-right tabular-nums">{{ money(row.list_value) }}</td>
								<td class="py-2 pr-4 text-right tabular-nums">{{ money(row.revenue) }}</td>
								<td class="py-2 text-right tabular-nums text-ink-amber-6">
									{{ money(row.discount_value) }}
								</td>
							</tr>
						</tbody>
					</table>
				</section>

				<!-- 3. Floor breaches -->
				<section>
					<h2 class="text-lg font-semibold text-ink-gray-8 mb-3">Quotations under approved floor</h2>
					<p v-if="floorSection.status !== 'available'" class="text-sm text-ink-gray-6">
						{{ floorSection.message }}
					</p>
					<p v-else-if="!floorBreaches.length" class="text-sm text-ink-gray-6">
						No open quotation is priced under its approved floor.
					</p>
					<table v-else class="w-full text-sm">
						<thead>
							<tr class="text-left text-ink-gray-5 border-b border-outline-gray-1">
								<th class="py-2 pr-4 font-medium">Quotation</th>
								<th class="py-2 pr-4 font-medium">Customer</th>
								<th class="py-2 pr-4 font-medium">Item</th>
								<th class="py-2 pr-4 font-medium text-right">Rate</th>
								<th class="py-2 pr-4 font-medium text-right">Floor</th>
								<th class="py-2 font-medium text-right">Shortfall</th>
							</tr>
						</thead>
						<tbody>
							<tr
								v-for="row in floorBreaches"
								:key="`${row.quotation}-${row.item_code}`"
								class="border-b border-outline-gray-1"
							>
								<td class="py-2 pr-4 text-ink-gray-8">{{ row.quotation }}</td>
								<td class="py-2 pr-4 text-ink-gray-6">{{ row.customer_name || '—' }}</td>
								<td class="py-2 pr-4 text-ink-gray-6">{{ row.item_code }}</td>
								<td class="py-2 pr-4 text-right tabular-nums">{{ money(row.rate) }}</td>
								<td class="py-2 pr-4 text-right tabular-nums">{{ money(row.floor_price) }}</td>
								<td class="py-2 text-right tabular-nums text-ink-red-6">
									{{ money(row.shortfall) }}
								</td>
							</tr>
						</tbody>
					</table>
				</section>

				<!-- 4. Approval queue -->
				<section>
					<h2 class="text-lg font-semibold text-ink-gray-8 mb-3">Pricing approval queue</h2>
					<p v-if="queueSection.status !== 'available'" class="text-sm text-ink-gray-6">
						{{ queueSection.message }}
					</p>
					<p v-else-if="!queueRows.length" class="text-sm text-ink-gray-6">
						No open pricing requests.
					</p>
					<div v-else class="grid grid-cols-2 gap-4 sm:grid-cols-4">
						<KpiCard
							v-for="row in queueRows"
							:key="row.state || 'draft'"
							variant="tile"
							:label="row.state || 'Draft'"
							:value="row.count"
							:sublabel="money(row.value)"
						/>
					</div>
				</section>
			</div>
		</IntelligenceDashboardShell>
	</div>
</template>

<script setup lang="ts">
defineOptions({ name: 'PriceIntelligence' })
import { Button } from 'frappe-ui'
import { computed } from 'vue'
import { RefreshCcw } from 'lucide-vue-next'
import IntelligenceDashboardShell from '../intelligence/components/IntelligenceDashboardShell.vue'
import KpiCard from '../intelligence/components/KpiCard.vue'
import { useIntelligenceDashboard } from '../intelligence/composables/useIntelligenceDashboard'
import { formatCount, formatDateTime, formatMoney, formatPercent } from '../utils/format'

/** Per-item realised margin row. */
interface MarginRow {
	item_code: string
	item_name?: string | null
	item_group?: string | null
	revenue?: number
	qty?: number
	avg_rate?: number
	valuation_rate?: number | null
	margin_per_unit?: number | null
	margin_pct?: number | null
}

interface DiscountRow {
	item_code: string
	item_name?: string | null
	revenue?: number
	qty?: number
	list_value?: number
	line_count?: number
	discount_value?: number
}

interface BreachRow {
	quotation: string
	customer_name?: string | null
	item_code: string
	rate?: number
	floor_price?: number
	qty?: number
	shortfall?: number
}

interface QueueRow {
	state?: string | null
	count?: number
	value?: number
}

/** A section the backend may honestly refuse to compute. */
interface GuardedSection<T> {
	status: string
	message?: string | null
	rows: T[]
}

interface PriceData {
	company?: string | null
	currency?: string | null
	lookback_days?: number
	margin_by_item?: MarginRow[]
	discount_pressure?: DiscountRow[]
	floor_breaches?: GuardedSection<BreachRow>
	approval_queue?: GuardedSection<QueueRow>
}

const {
	data,
	loading,
	refreshing,
	error,
	isPermissionError,
	warming,
	notImplemented,
	notImplementedMessage,
	hasData,
	reload,
	retry,
	lastUpdated,
} = useIntelligenceDashboard<PriceData>({
	url: 'insights.api.ml.price.get_selling_price_intelligence',
	cache: 'price-intelligence',
})

const currency = computed(() => data.value?.currency ?? null)
const lookbackDays = computed(() => data.value?.lookback_days ?? 365)
const marginRows = computed<MarginRow[]>(() => data.value?.margin_by_item ?? [])
const discountRows = computed<DiscountRow[]>(() => data.value?.discount_pressure ?? [])

const EMPTY_SECTION = { status: 'unavailable', message: null, rows: [] }
const floorSection = computed<GuardedSection<BreachRow>>(
	() => data.value?.floor_breaches ?? (EMPTY_SECTION as GuardedSection<BreachRow>),
)
const queueSection = computed<GuardedSection<QueueRow>>(
	() => data.value?.approval_queue ?? (EMPTY_SECTION as GuardedSection<QueueRow>),
)
const floorBreaches = computed(() => floorSection.value.rows ?? [])
const queueRows = computed(() => queueSection.value.rows ?? [])

/** Rows whose realised price is under stock valuation. */
const belowValuation = computed(() =>
	marginRows.value.filter((row) => (row.margin_per_unit ?? 0) < 0),
)

const totalDiscount = computed(() =>
	discountRows.value.reduce((sum, row) => sum + (row.discount_value ?? 0), 0),
)

/* The KPI's sublabel must not imply "zero breaches" when the section could not
 * be computed at all — the two are different claims. */
const floorStatusNote = computed(() =>
	floorSection.value.status === 'available' ? 'Open quotations' : 'Not tracked on this site',
)

function money(value: number | null | undefined): string {
	return formatMoney(value, currency.value)
}

function count(value: number | null | undefined): string {
	return formatCount(value)
}

function percent(value: number | null | undefined): string {
	return formatPercent(value)
}

function marginClass(marginPct: number | null | undefined): string {
	if (marginPct == null) return 'text-ink-gray-5'
	return marginPct < 0 ? 'text-ink-red-6' : 'text-ink-green-6'
}
</script>
