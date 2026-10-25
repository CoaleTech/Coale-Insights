<!-- frontend/src2/dashboard/CustomerSections.vue -->
<!--
  Customer tab-group content for the merged Revenue & Customers dashboard.
  Receives the customer_intelligence payload from the shell and renders 7 tabs:
  Overview, Customers, Geography, Actions, Cohorts, Patterns, Rankings.
  The TerritoryMap lives here (not in Revenue Attribution).
-->
<script setup lang="ts">
defineOptions({ name: 'CustomerSections' })
import { Badge, Button, FormControl, Select, Tooltip } from 'frappe-ui'
import { apiCall, readFrappeError } from '../helpers/api'
import {
  Search, Filter, Star, ChevronRight, MapPin, Target, Activity, AlertTriangle,
} from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { createToast } from '../helpers/toasts'
import TerritoryMap from '../components/TerritoryMap.vue'
import {
  formatCurrency, formatNumber, formatPercent,
  tierFilterOptions, rfmSegmentFilterOptions, riskFilterOptions,
  getRecentCustomers, addRecentCustomer, actionLabel,
} from '../utils/customerUtils'
import { asNumber, NO_VALUE } from '../utils/format'
import { DEFAULT_DATE_RANGES, FISCAL_PERIOD_RANGES, decodeCustomRange } from '../utils/dateRangePresets'
import { severityBadge, severityFill, scoreSeverity, ragSeverity, prioritySeverity, deltaInk, type Severity } from '../utils/status'
import type { DrillDownParams } from '../intelligence/composables/useDrillDown'
import KpiCard from '../intelligence/components/KpiCard.vue'
import SectionHeader from '../intelligence/components/SectionHeader.vue'
import SkeletonBlock from '../intelligence/components/SkeletonBlock.vue'
import TabBrief, { type Brief } from '../intelligence/components/TabBrief.vue'
import TabActions from '../intelligence/components/TabActions.vue'
import StatStrip, { type StatItem } from '../intelligence/components/StatStrip.vue'

// ── Props & emits ──────────────────────────────────────────────────────────
const props = defineProps<{
  data: Record<string, unknown>
  activeTab: string
  dateFilter: string
  currency: string | null
  drillDownEndpoint: string
}>()

const emit = defineEmits<{
  (e: 'drill-down', endpoint: string, title: string, params: DrillDownParams): void
  (e: 'view-customer', customerId: string): void
}>()

function drillOpen(title: string, params: DrillDownParams) {
  emit('drill-down', props.drillDownEndpoint, title, params)
}

function viewCustomerDetail(customerId: string) {
  recentCustomerIds.value = addRecentCustomer(customerId)
  emit('view-customer', customerId)
}

// Rankings row -> that customer's invoices over the selected window (D9).
function drillCustomerOrders(c: ScorecardRow) {
  drillOpen(`${c.customer_name} Orders`, { metric: 'top_customers', customer: c.customer, date_filter: props.dateFilter })
}

// ── Types ──────────────────────────────────────────────────────────────────
interface CustomerRow {
  customer_id: string
  customer_name?: string
  territory?: string
  rfm_segment?: string
  clv_tier?: string
  churn_risk?: string
  total_clv?: number
  historical_clv?: number
  health_status?: string
  health_score?: number
  order_count?: number
  recency_days?: number
  gross_profit?: number
}

interface ScorecardRow {
  customer: string
  customer_name: string
  revenue: number
  gross_profit: number
  margin_pct: number | null
  months_active: number
  total_months: number
  consistency_score: number
  avg_monthly_spend: number
  clv_tier?: string
  rfm_segment?: string
  churn_risk?: string
  health_status?: string
  health_score?: number
}
interface ScorecardData {
  customers: ScorecardRow[]
  total_months: number
}
type RankSortKey = 'revenue' | 'gross_profit' | 'margin_pct' | 'months_active' | 'consistency_score' | 'health_score'
interface GeoPoint { name: string; value: number }
interface UnmappedTerritory { territory: string; value: number }
interface DayOfWeekDataRow { order_count: number }
interface ActionRec {
  action: string
  priority: string
  description: string
  suggestion: string
}
interface ActionItem {
  customer_id: string
  customer_name?: string
  clv_tier?: string
  health_status?: string
  churn_risk?: string
  historical_clv?: number
  predicted_12m_clv?: number
  outstanding_amount?: number
  recency_days?: number
  recommendations: ActionRec[]
}

// ── Recommendation tier labels ─────────────────────────────────────────────
const REC_TIER_LABELS: Record<number, string> = {
  0: 'Seasonal', 1: 'Rules', 2: 'FBT', 3: 'Popular', 4: 'Explore',
}

// ── State ──────────────────────────────────────────────────────────────────
const counts = ref<any>(null)
const scorecard = ref<ScorecardData | null>(null)
const isLoadingRankings = ref(false)
// Purchase patterns cached per date filter, so a window change refetches but
// flipping back to a seen window (or between tabs) does not.
const patternsByFilter = ref<Record<string, any>>({})
const patternsLoadingKey = ref<string | null>(null)
const purchasePatternsData = computed(() => patternsByFilter.value[props.dateFilter] ?? null)
const isLoadingPatterns = computed(() => patternsLoadingKey.value === props.dateFilter && !purchasePatternsData.value)
const activeCutoff = ref('6')
// Period-wise counts: loaded lazily when the "Customers by period" panel opens.
const periodOpen = ref(false)
const periodGran = ref('auto')
const periodData = ref<{ granularity: string | null, periods: Record<string, any>[] } | null>(null)

// Rankings filters + sort — all client-side over the one scorecard list.
const rankSearch = ref('')
const rankTier = ref('')
const rankSegment = ref('')
const rankRisk = ref('')
const minRevenue = ref('')
const minGrossProfit = ref('')
const minMargin = ref('')
const minMonths = ref('')
const minScore = ref('')
const rankSort = ref<RankSortKey>('revenue')
const rankDir = ref<'asc' | 'desc'>('desc')
const sortableCols: { key: RankSortKey; label: string }[] = [
  { key: 'revenue', label: 'Revenue' },
  { key: 'gross_profit', label: 'Gross Profit' },
  { key: 'margin_pct', label: 'Margin %' },
  { key: 'months_active', label: 'Months' },
  { key: 'consistency_score', label: 'Consistency' },
  { key: 'health_score', label: 'Health' },
]

// ── Filters ────────────────────────────────────────────────────────────────
const customerFilter = ref('')
const tierFilter = ref('')
const riskFilter = ref('')
const rfmFilter = ref('')
const recentCustomerIds = ref<string[]>(getRecentCustomers())

// ── Computed data accessors ────────────────────────────────────────────────
const summary = computed(() => (props.data.summary ?? {}) as Record<string, unknown>)
const baseCurrency = computed<string | null>(() => (props.data.base_currency as string) ?? props.currency)
// D1: revenue on this dashboard is tax-exclusive; the payload says so at its root.
const revenueBasisNote = computed(() =>
  props.data.revenue_basis === 'net_of_tax'
    ? `Revenue shown net of tax${baseCurrency.value ? ` in ${baseCurrency.value}` : ''}`
    : null)
const windowLabel = computed(() => {
  const f = props.dateFilter
  const custom = decodeCustomRange(f)
  if (custom) return `${custom.start} to ${custom.end}`
  return [...DEFAULT_DATE_RANGES, ...FISCAL_PERIOD_RANGES].find(r => r.value === f)?.label ?? f
})
const customers = computed(() => {
  let list: CustomerRow[] = (props.data.customers ?? []) as unknown as CustomerRow[]
  if (customerFilter.value) {
    const search = customerFilter.value.toLowerCase()
    list = list.filter((c: CustomerRow) =>
      // Coerce each field: the payload occasionally carries a non-string
      // (e.g. territory `0` for customers with no territory), and calling
      // `.toLowerCase()` on it throws, crashing the whole tab.
      [c.customer_name, c.customer_id, c.territory, c.rfm_segment]
        .some(v => typeof v === 'string' && v.toLowerCase().includes(search)),
    )
  }
  if (tierFilter.value) list = list.filter(c => c.clv_tier === tierFilter.value)
  if (riskFilter.value) list = list.filter(c => c.churn_risk === riskFilter.value)
  if (rfmFilter.value) list = list.filter(c => c.rfm_segment === rfmFilter.value)
  return list
})

// Cards above the directory. Both read the same customers[] rows the table shows.
const criticalTop = computed(() =>
  ((props.data.customers ?? []) as unknown as CustomerRow[])
    .filter(c => c.churn_risk === 'Critical')
    .sort((a, b) => (b.total_clv ?? 0) - (a.total_clv ?? 0))
    .slice(0, 5),
)
const TIER_ORDER = ['Diamond', 'Platinum', 'Gold', 'Silver', 'Bronze']
const tierHealth = computed(() => {
  const by = new Map<string, { accounts: number; atRisk: number; healthy: number; critical: number }>()
  for (const c of (props.data.customers ?? []) as unknown as CustomerRow[]) {
    const tier = c.clv_tier || 'Unrated'
    const row = by.get(tier) ?? { accounts: 0, atRisk: 0, healthy: 0, critical: 0 }
    row.accounts++
    if (c.health_status === 'At Risk') row.atRisk++
    else if (c.health_status === 'Healthy' || c.health_status === 'Excellent') row.healthy++
    else if (c.health_status === 'Critical') row.critical++
    by.set(tier, row)
  }
  const rank = (t: string) => (TIER_ORDER.includes(t) ? TIER_ORDER.indexOf(t) : TIER_ORDER.length)
  return [...by.entries()].sort((a, b) => rank(a[0]) - rank(b[0])).map(([tier, v]) => ({ tier, ...v }))
})
const recentCustomerDetails = computed(() => {
  const allCustomers: CustomerRow[] = (props.data.customers ?? []) as unknown as CustomerRow[]
  return recentCustomerIds.value
    .map((id: string) => allCustomers.find((c: CustomerRow) => c.customer_id === id))
    .filter((c): c is CustomerRow => c !== undefined)
})

// ── Rankings scorecard (unified, filterable, sortable) ──────────────────────
// The scorecard endpoint carries revenue/profit/margin/months/consistency;
// tier, segment, risk and health come from the shell's customer payload,
// joined by customer id so the Rankings tab shares one row per customer.
const rankMeta = computed(() => {
  const m = new Map<string, CustomerRow>()
  for (const c of ((props.data.customers ?? []) as unknown as CustomerRow[])) {
    if (c.customer_id) m.set(String(c.customer_id), c)
  }
  return m
})
const scorecardRows = computed<ScorecardRow[]>(() => {
  const meta = rankMeta.value
  let rows = (scorecard.value?.customers ?? []).map((r) => {
    const md = meta.get(String(r.customer))
    return {
      ...r,
      clv_tier: md?.clv_tier,
      rfm_segment: md?.rfm_segment ?? r.rfm_segment,
      churn_risk: md?.churn_risk,
      health_status: md?.health_status,
      health_score: md?.health_score,
    } as ScorecardRow
  })
  const q = rankSearch.value.trim().toLowerCase()
  if (q) {
    rows = rows.filter(r =>
      [r.customer_name, r.customer].some(v => typeof v === 'string' && v.toLowerCase().includes(q)))
  }
  if (rankTier.value) rows = rows.filter(r => r.clv_tier === rankTier.value)
  if (rankSegment.value) rows = rows.filter(r => r.rfm_segment === rankSegment.value)
  if (rankRisk.value) rows = rows.filter(r => r.churn_risk === rankRisk.value)
  const gte = (v: number | undefined, min: string) => {
    const n = parseFloat(min)
    return Number.isNaN(n) || (typeof v === 'number' && v >= n)
  }
  rows = rows.filter(r =>
    gte(r.revenue, minRevenue.value) &&
    gte(r.gross_profit, minGrossProfit.value) &&
    gte(r.margin_pct ?? undefined, minMargin.value) &&
    gte(r.months_active, minMonths.value) &&
    gte(r.consistency_score == null ? undefined : r.consistency_score * 100, minScore.value))
  const key = rankSort.value
  const dir = rankDir.value === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => (Number(a[key] ?? 0) - Number(b[key] ?? 0)) * dir)
})
function setRankSort(key: RankSortKey) {
  if (rankSort.value === key) rankDir.value = rankDir.value === 'asc' ? 'desc' : 'asc'
  else { rankSort.value = key; rankDir.value = 'desc' }
}
function clearRankFilters() {
  rankSearch.value = ''
  rankTier.value = ''
  rankSegment.value = ''
  rankRisk.value = ''
  minRevenue.value = ''
  minGrossProfit.value = ''
  minMargin.value = ''
  minMonths.value = ''
  minScore.value = ''
}
const geoAnalysis = computed(() => (props.data.geographic_analysis ?? {}) as any)
const territoryGeo = computed(() => (geoAnalysis.value.territory_geo ?? {}) as Record<string, unknown>)
const territoryWorld = computed<GeoPoint[]>(() => (territoryGeo.value.world ?? []) as GeoPoint[])
const territoryIndia = computed<GeoPoint[]>(() => (territoryGeo.value.india ?? []) as GeoPoint[])
const customerGroups = computed(() => (geoAnalysis.value.customer_group_analysis ?? []) as {
  customer_group: string; customer_count: number; total_revenue: number; avg_order_value: number; avg_health_score: number
}[])
const territoryUnmapped = computed<UnmappedTerritory[]>(() => (territoryGeo.value.unmapped ?? []) as UnmappedTerritory[])
const mappedCustomers = computed(() => territoryWorld.value.reduce((s, r) => s + (Number(r.value) || 0), 0))
// Denominator is every customer counted by the backend, not mapped + unmapped
// territory buckets: customers with no territory are in neither bucket.
const totalGeoCustomers = computed(() => asNumber(geoAnalysis.value.coverage?.total_customers) ?? 0)
const unmappedCustomers = computed(() => Math.max(0, totalGeoCustomers.value - mappedCustomers.value))
const mapCoveragePct = computed(() =>
  totalGeoCustomers.value > 0 ? (mappedCustomers.value / totalGeoCustomers.value) * 100 : null)
const paretoAnalysis = computed(() => (props.data.pareto_analysis ?? {}) as Record<string, unknown>)
const cohortAnalysis = computed(() => (props.data.cohort_analysis ?? {}) as Record<string, unknown>)
const nextActions = computed(() => (props.data.next_best_actions ?? []) as ActionItem[])
// The payload caps next_best_actions; the true flagged count rides alongside.
const nextActionsTotal = computed(() => asNumber(props.data.next_best_actions_total) ?? nextActions.value.length)

// ── Customer Overview: Pareto SVG, at-risk rail, RFM ranked list ──────────
interface ParetoCurvePoint { customer_pct: number; cumulative_percent: number }
interface AtRiskRow {
  customer_id: string; customer_name: string; churn_risk: string
  historical_clv: number; recency_days: number; outstanding_amount: number
}
interface RfmSegRow { label: string; count: number; pct: number; barWidth: number; fillClass: string }

// SVG chart layout constants (viewBox 0 0 560 220)
const CHART_L = 50, CHART_T = 20, CHART_R = 540, CHART_B = 175
const CHART_W = CHART_R - CHART_L   // 490
const CHART_H = CHART_B - CHART_T   // 155
function sx(pct: number): number { return CHART_L + (pct / 100) * CHART_W }
function sy(pct: number): number { return CHART_B - (pct / 100) * CHART_H }

const paretoCurve = computed<ParetoCurvePoint[]>(() =>
  (paretoAnalysis.value.pareto_curve ?? []) as ParetoCurvePoint[])
const pareto80ThresholdPct = computed<number>(() =>
  asNumber(paretoAnalysis.value.pareto_80_threshold_pct) ?? 0)
const paretoPoints = computed(() =>
  paretoCurve.value.map(p => `${sx(p.customer_pct).toFixed(1)},${sy(p.cumulative_percent).toFixed(1)}`))
const paretoLinePath = computed(() => {
  const pts = paretoPoints.value
  if (pts.length < 2) return ''
  return `M ${pts[0]} L ${pts.slice(1).join(' L ')}`
})
const paretoAreaPath = computed(() => {
  const pts = paretoPoints.value
  if (!pts.length) return ''
  return `M ${CHART_L},${CHART_B} L ${pts.join(' L ')} L ${CHART_R},${CHART_B} Z`
})

const atRiskCustomers = computed<AtRiskRow[]>(() =>
  (props.data.at_risk_customers ?? []) as AtRiskRow[])
// Already sorted by historical_clv desc from backend
const atRiskCritical = computed(() => atRiskCustomers.value.filter(c => c.churn_risk === 'Critical'))
const atRiskHigh = computed(() => atRiskCustomers.value.filter(c => c.churn_risk === 'High'))
const atRiskSummaryCount = computed<number>(() => {
  const dist = (summary.value.churn_risk_distribution ?? {}) as Record<string, number>
  return (dist.High ?? 0) + (dist.Critical ?? 0)
})
const healthDistribution = computed<Record<string, number>>(() =>
  (summary.value.health_distribution ?? {}) as Record<string, number>)

function rfmSegmentFill(label: string): string {
  const neg = new Set(['At Risk', 'Hibernating', 'Lost', "Can't Lose"])
  const warn = new Set(['Need Attention', 'About to Sleep'])
  const pos = new Set(['Champions', 'Loyal Customers', 'Potential Loyalists', 'Promising', 'New Customers'])
  if (neg.has(label)) return severityFill('high')
  if (warn.has(label)) return severityFill('medium')
  if (pos.has(label)) return severityFill('low')
  return severityFill('none')
}

function healthDistTint(status: string): string {
  if (status === 'Excellent' || status === 'Healthy') return 'bg-surface-green-2'
  if (status === 'At Risk') return 'bg-surface-amber-2'
  if (status === 'Critical') return 'bg-surface-red-2'
  return 'bg-surface-gray-2'
}

const rfmSortedSegments = computed<RfmSegRow[]>(() => {
  const dist = (summary.value.rfm_segment_distribution ?? {}) as Record<string, number>
  const total = (summary.value.total_customers as number) || 1
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1])
  const maxC = entries.length ? entries[0][1] : 1
  return entries.map(([label, count]) => ({
    label,
    count,
    pct: (count / total) * 100,
    barWidth: (count / maxC) * 100,
    fillClass: rfmSegmentFill(label),
  }))
})

// ── Geography breakdown (dimension-driven, drillable) ───────────────────────
// One endpoint slices sales by territory / item group / salesperson /
// customer with revenue, gross profit (SLE-based, matching Margins),
// distinct customers and transactions. Clicking a dimension row drills to
// the customers behind it; clicking a customer opens Customer Detail.
type GeoDim = 'territory' | 'item_group' | 'sales_person'
type GeoMeasure = 'revenue' | 'gross_profit' | 'customers' | 'margin_pct' | 'transactions'
interface GeoRow {
  key: string; label: string
  revenue: number; gross_profit: number; margin_pct: number
  customers: number; transactions: number
}
interface GeoBreakdown { dimension: string; rows: GeoRow[]; totals: Omit<GeoRow, 'key' | 'label'> }
interface GeoOptions { territories: string[]; item_groups: string[]; sales_persons: string[] }
const GEO_DIM_LABELS: Record<string, string> = {
  territory: 'Territory', item_group: 'Item Group', sales_person: 'Salesperson', customer: 'Customer',
}
const geoDim = ref<GeoDim>('territory')
const geoNarrow = ref<{ territory: string; item_group: string; sales_person: string }>({ territory: '', item_group: '', sales_person: '' })
const geoDrill = ref(false)
const geoResp = ref<GeoBreakdown | null>(null)
const geoLoading = ref(false)
const geoOptions = ref<GeoOptions>({ territories: [], item_groups: [], sales_persons: [] })
const geoSortKey = ref<GeoMeasure>('revenue')
const geoSortDir = ref<'asc' | 'desc'>('desc')

const effectiveGeoDim = computed(() => (geoDrill.value ? 'customer' : geoDim.value))
const geoRows = computed<GeoRow[]>(() => {
  const rows = [...(geoResp.value?.rows ?? [])]
  const k = geoSortKey.value
  const dir = geoSortDir.value === 'asc' ? 1 : -1
  return rows.sort((a, b) => (Number(a[k] ?? 0) - Number(b[k] ?? 0)) * dir)
})
const geoTotals = computed(() => geoResp.value?.totals ?? null)
const geoActiveNarrow = computed(
  () => Object.entries(geoNarrow.value).filter(([, v]) => v) as [GeoDim, string][],
)
function asSelectOptions(placeholder: string, vals: string[]) {
  return [{ value: '', label: placeholder }, ...vals.map(v => ({ value: v, label: v }))]
}

// ── Actions (next best actions) ────────────────────────────────────────────
// Each action leads with the real ledger figure at stake, not just advice:
// churn/re-engagement risk the booked revenue (`historical_clv`), payment
// follow-up the `outstanding_amount`, upsell/nurture the predicted 12-month
// forward value. All quantification, filtering and sorting is client-side.
type MoneyField = 'historical_clv' | 'outstanding_amount' | 'predicted_12m_clv'
const ACTION_MONEY: Record<string, { label: string; field: MoneyField }> = {
  CHURN_PREVENTION:     { label: 'Revenue at risk',     field: 'historical_clv' },
  RE_ENGAGEMENT:        { label: 'Revenue at risk',     field: 'historical_clv' },
  PAYMENT_FOLLOW_UP:    { label: 'Outstanding',         field: 'outstanding_amount' },
  UPSELL_OPPORTUNITY:   { label: '12-mo forward value', field: 'predicted_12m_clv' },
  NEW_CUSTOMER_NURTURE: { label: '12-mo forward value', field: 'predicted_12m_clv' },
}
const actionTypeOptions = [
  { value: '', label: 'All action types' },
  { value: 'CHURN_PREVENTION', label: 'Churn prevention' },
  { value: 'RE_ENGAGEMENT', label: 'Re-engagement' },
  { value: 'PAYMENT_FOLLOW_UP', label: 'Payment follow-up' },
  { value: 'UPSELL_OPPORTUNITY', label: 'Upsell opportunity' },
  { value: 'NEW_CUSTOMER_NURTURE', label: 'New customer nurture' },
]
const actionPriorityOptions = [
  { value: '', label: 'All priorities' },
  { value: 'High', label: 'High priority' },
  { value: 'Medium', label: 'Medium priority' },
]
const actionType = ref('')
const actionPriority = ref('')

function recImpact(item: ActionItem, rec: ActionRec): number {
  const m = ACTION_MONEY[rec.action]
  return m ? Number(item[m.field] ?? 0) : 0
}
function recImpactLabel(rec: ActionRec): string {
  return ACTION_MONEY[rec.action]?.label ?? ''
}
// Largest single ledger figure at stake for the customer. Uses max, not sum,
// so two recs pointing at the same field (churn + re-engagement) don't
// double-count the one revenue relationship.
function atStake(item: ActionItem): number {
  return item.recommendations.reduce((mx, r) => Math.max(mx, recImpact(item, r)), 0)
}
function hasHighPriority(item: ActionItem): boolean {
  return item.recommendations.some(r => r.priority === 'High')
}
const filteredActions = computed<ActionItem[]>(() => {
  let list = nextActions.value
  if (actionType.value) list = list.filter(a => a.recommendations.some(r => r.action === actionType.value))
  if (actionPriority.value) list = list.filter(a => a.recommendations.some(r => r.priority === actionPriority.value))
  // High-priority customers first, then biggest money at stake.
  return [...list].sort((a, b) =>
    (Number(hasHighPriority(b)) - Number(hasHighPriority(a))) || (atStake(b) - atStake(a)))
})
// Impact summary — one action item is one customer, so these sums never
// double-count a customer across its own recommendations.
const actionsSummary = computed(() => {
  let revenueAtRisk = 0, outstanding = 0, upside = 0, high = 0
  for (const a of nextActions.value) {
    const kinds = new Set(a.recommendations.map(r => r.action))
    if (kinds.has('CHURN_PREVENTION') || kinds.has('RE_ENGAGEMENT')) revenueAtRisk += Number(a.historical_clv ?? 0)
    if (kinds.has('PAYMENT_FOLLOW_UP')) outstanding += Number(a.outstanding_amount ?? 0)
    if (kinds.has('UPSELL_OPPORTUNITY') || kinds.has('NEW_CUSTOMER_NURTURE')) upside += Number(a.predicted_12m_clv ?? 0)
    if (hasHighPriority(a)) high++
  }
  return { revenueAtRisk, outstanding, upside, high, total: nextActions.value.length }
})
function clearActionFilters() { actionType.value = ''; actionPriority.value = '' }
const ACTION_CARD_LIMIT = 50
const actionsCountLabel = computed(() => {
  const shown = Math.min(filteredActions.value.length, ACTION_CARD_LIMIT)
  if (actionType.value || actionPriority.value)
    return `Showing ${shown} of ${filteredActions.value.length} matching (${nextActions.value.length} loaded of ${nextActionsTotal.value} flagged)`
  return `Showing ${shown} of ${nextActionsTotal.value} flagged customers`
})
// `totalCrossSellRecommendations`, `crossSellData`, `loadCrossSellData`,
// `revenueSplit`/`loadRevenueSplit` and `variance`/`loadVariance` were removed:
// all were computed or fetched but never rendered. The revenue-split and
// variance calls fired on mount AND on every date-filter change, so each page
// view and each filter touch spent two round trips producing data nothing read.
const maxDayOfWeekOrders = computed((): number => {
  const rows: DayOfWeekDataRow[] = (purchasePatternsData.value?.day_of_week?.data ?? []) as unknown as DayOfWeekDataRow[]
  if (!rows.length) return 1
  return Math.max(...rows.map(d => d.order_count))
})

// ── Money formatter (server currency) ──────────────────────────────────────
function money(value: number | undefined | null): string {
  return formatCurrency(value, baseCurrency.value)
}

// ── Severity helpers ───────────────────────────────────────────────────────
function healthSeverity(status: string | undefined | null): Severity {
  // Backend `_classify_health()` only ever returns these four buckets.
  const map: Record<string, Severity> = {
    Excellent: 'none', Healthy: 'none',
    'At Risk': 'high', Critical: 'critical',
  }
  return map[String(status ?? '')] ?? 'none'
}
function churnSeverity(risk: string | undefined | null): Severity {
  const r = String(risk ?? '').toLowerCase()
  if (r === 'critical' || r === 'high') return 'high'
  if (r === 'medium') return 'medium'
  return 'none'
}
function retentionSeverity(pct: number | undefined): Severity {
  return scoreSeverity(pct, { good: 50, warn: 25, higherIsBetter: true })
}

// ── Lazy loaders ──────────────────────────────────────────────────────────
async function loadPurchasePatterns() {
  const key = props.dateFilter
  if (patternsByFilter.value[key]) return
  patternsLoadingKey.value = key
  try {
    const res = await apiCall('insights.api.ml.purchase_patterns', {
      top_percentile: 20,
      date_filter: key,
    }) as Record<string, unknown>
    patternsByFilter.value = { ...patternsByFilter.value, [key]: res }
  } catch (e: unknown) {
    const { message } = readFrappeError(e, 'Could not load purchase patterns')
    console.error('Failed to load purchase patterns:', message)
  } finally {
    if (patternsLoadingKey.value === key) patternsLoadingKey.value = null
  }
}

async function loadCustomerCounts() {
  try {
    counts.value = await apiCall('insights.api.ml.customer.customer_counts', {
      date_filter: props.dateFilter,
      active_cutoff_months: activeCutoff.value,
    }) as Record<string, unknown>
  } catch (e: unknown) {
    console.error('Failed to load customer counts:', readFrappeError(e).message)
  }
}

async function loadPeriodCounts() {
  try {
    periodData.value = await apiCall('insights.api.ml.customer.customer_counts_by_period', {
      date_filter: props.dateFilter,
      granularity: periodGran.value,
      active_cutoff_months: activeCutoff.value,
    }) as typeof periodData.value
  } catch (e: unknown) {
    console.error('Failed to load customer counts by period:', readFrappeError(e).message)
  }
}
function periodLabel(p: Record<string, string>): string {
  const d = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })
  return p.period_start === p.period_end ? d(p.period_start) : `${d(p.period_start)} – ${d(p.period_end)}`
}
// A period row drills with its own range, so the list matches the cell.
function drillPeriod(metric: 'new_customers' | 'reactivated_customers', title: string, p: Record<string, string>) {
  drillOpen(`${title} · ${periodLabel(p)}`, {
    metric,
    date_filter: `custom:${p.period_start}:${p.period_end}`,
    active_cutoff_months: activeCutoff.value,
  })
}

// Counts strip. Total is the Customer master; "Buyers" is the customers who
// invoiced in the window (the dashboard's customer KPIs); Reactivated is
// customers who restarted buying after the "Inactive after" gap.
const countTiles = computed(() => {
  const c = (counts.value ?? {}) as Record<string, number>
  const months = activeCutoff.value
  return [
    { label: 'All customers', value: c.total, hint: 'Every enabled customer on the master, whether or not they bought in this period', drill: { title: 'All Customers', params: { metric: 'total_customers' } } },
    { label: 'Buyers', value: c.transacting, hint: 'Customers with a sales invoice in the selected period' },
    { label: 'New', value: c.new_by_first_txn, hint: 'First-ever invoice falls in the selected period', drill: { title: 'New Customers', params: { metric: 'new_customers', date_filter: props.dateFilter } } },
    { label: 'Repeat', value: c.repeat, hint: 'Bought in the period and had bought before it' },
    { label: 'Reactivated', value: c.reactivated, hint: `Bought in the period after ${months}+ months without buying`, drill: { title: 'Reactivated Customers', params: { metric: 'reactivated_customers', date_filter: props.dateFilter, active_cutoff_months: months } } },
    { label: 'Inactive', value: c.inactive, hint: `No order or invoice in the last ${months} months` },
    { label: 'Advance pay', value: c.advance_payment },
    { label: 'Manufacturers', value: c.manufacturers },
    { label: 'Traders', value: c.traders },
  ]
})

async function loadRankings() {
  isLoadingRankings.value = true
  try {
    scorecard.value = await apiCall('insights.api.ml.customer.customer_scorecard', {
      date_filter: props.dateFilter,
    }) as ScorecardData
  } catch (e: unknown) {
    console.error('Failed to load rankings:', readFrappeError(e).message)
  } finally {
    isLoadingRankings.value = false
  }
}

async function loadGeoOptions() {
  try {
    geoOptions.value = await apiCall('insights.api.ml.customer.geography_options', {
      date_filter: props.dateFilter,
    }) as GeoOptions
  } catch (e: unknown) {
    console.error('Failed to load geography options:', readFrappeError(e).message)
  }
}

async function loadGeoBreakdown() {
  geoLoading.value = true
  try {
    geoResp.value = await apiCall('insights.api.ml.customer.geography_breakdown', {
      dimension: effectiveGeoDim.value,
      date_filter: props.dateFilter,
      territory: geoNarrow.value.territory,
      item_group: geoNarrow.value.item_group,
      sales_person: geoNarrow.value.sales_person,
    }) as GeoBreakdown
  } catch (e: unknown) {
    createToast({ title: 'Error', message: readFrappeError(e, 'Failed to load geography breakdown').message, variant: 'error' })
  } finally {
    geoLoading.value = false
  }
}

function setGeoSort(k: GeoMeasure) {
  if (geoSortKey.value === k) geoSortDir.value = geoSortDir.value === 'asc' ? 'desc' : 'asc'
  else { geoSortKey.value = k; geoSortDir.value = 'desc' }
}
// A dimension row drills to the customers behind it: narrow by the clicked
// key and switch to the customer view. A customer row navigates to detail.
function geoRowClick(row: GeoRow) {
  if (effectiveGeoDim.value === 'customer') { viewCustomerDetail(row.key); return }
  geoNarrow.value = { ...geoNarrow.value, [geoDim.value]: row.key }
  geoDrill.value = true
}
function clearGeoDrill() { geoDrill.value = false }
function clearGeoAll() {
  geoNarrow.value = { territory: '', item_group: '', sales_person: '' }
  geoDrill.value = false
}


// ── Watchers ───────────────────────────────────────────────────────────────
watch([periodGran, activeCutoff, () => props.dateFilter, periodOpen], () => { if (periodOpen.value) loadPeriodCounts() })
watch(activeCutoff, () => loadCustomerCounts())
watch(() => props.activeTab, (tab) => {
  if (tab === 'cust-patterns') loadPurchasePatterns()
  if (tab === 'cust-rankings') loadRankings()
  if (tab === 'cust-geography') { loadGeoOptions(); loadGeoBreakdown() }
})

// Reload the geography slice whenever its dimension, drill state, narrow
// filters or the dashboard window change -- but only while the tab is open.
watch([effectiveGeoDim, geoNarrow, () => props.dateFilter], () => {
  if (props.activeTab === 'cust-geography') loadGeoBreakdown()
}, { deep: true })

watch(() => props.dateFilter, () => {
  loadCustomerCounts()
  loadRankings()
  if (props.activeTab === 'cust-geography') loadGeoOptions()
  if (props.activeTab === 'cust-patterns') loadPurchasePatterns()
})

onMounted(() => {
  recentCustomerIds.value = getRecentCustomers()
  loadCustomerCounts()
  loadRankings()
})

// ── Server briefs + stat strips ───────────────────────────────────────────
// Headline text is built server-side (insights/ml/tab_briefs/customer.py); the
// client only renders it, and renders nothing for an older cached payload.
const tabBriefs = computed(() => (props.data.tab_briefs ?? {}) as Record<string, Brief>)
const patternsBrief = computed(() => (purchasePatternsData.value?.brief ?? null) as Brief | null)

const listStrip = computed<StatItem[]>(() => {
  const s = summary.value
  const health = (s.health_distribution ?? {}) as Record<string, number>
  const churn = (s.churn_risk_distribution ?? {}) as Record<string, number>
  const total = asNumber(s.total_customers)
  const atRisk = health['At Risk']
  return [
    { label: 'Portfolio CLV', amount: asNumber(s.total_clv) ?? null, sublabel: 'predicted lifetime' },
    { label: 'At Risk', value: atRisk != null ? formatNumber(atRisk) : null, sublabel: atRisk != null && total ? `${formatPercent((atRisk / total) * 100)} of accounts` : undefined },
    { label: 'Critical Churn', value: churn.Critical != null ? formatNumber(churn.Critical) : null, sublabel: 'accounts' },
    { label: 'Quote Conversion', percent: asNumber(s.quote_conversion_rate) ?? null, sublabel: s.total_quotes != null ? `${formatNumber(s.converted_quotes as number)} of ${formatNumber(s.total_quotes as number)} quotes` : undefined },
  ]
})

const geoStrip = computed<StatItem[]>(() => {
  const cov = geoAnalysis.value.coverage ?? {}
  const terr = (geoAnalysis.value.territory_analysis ?? []) as { revenue_share?: number }[]
  const top3 = terr.length >= 3 ? terr.slice(0, 3).reduce((a, t) => a + (t.revenue_share ?? 0), 0) : null
  return [
    { label: 'Territories Covered', value: cov.territories_covered != null ? formatNumber(cov.territories_covered) : null },
    { label: 'Customer Groups', value: cov.customer_groups_covered != null ? formatNumber(cov.customer_groups_covered) : null },
    { label: 'Total Revenue', amount: asNumber(cov.total_revenue) ?? null },
    { label: 'Top 3 Territories', percent: top3, sublabel: 'of revenue' },
  ]
})

const actionsStrip = computed<StatItem[]>(() => [
  { label: 'Customers Flagged', value: formatNumber(nextActionsTotal.value), sublabel: `${actionsSummary.value.high} high priority${nextActionsTotal.value > nextActions.value.length ? ` (of top ${nextActions.value.length})` : ''}` },
  { label: 'Revenue at Risk', amount: actionsSummary.value.revenueAtRisk, sublabel: 'churn + re-engagement', tone: actionsSummary.value.revenueAtRisk > 0 ? 'neg' : undefined },
  { label: 'Outstanding to Collect', amount: actionsSummary.value.outstanding, sublabel: 'payment follow-ups', tone: actionsSummary.value.outstanding > 0 ? 'warn' : undefined },
  { label: 'Upsell + Nurture Upside', amount: actionsSummary.value.upside, sublabel: 'predicted 12-mo value' },
])

const cohortStrip = computed<StatItem[]>(() => {
  const avg = (cohortAnalysis.value.average_retention ?? {}) as Record<string, number>
  const cohorts = (cohortAnalysis.value.cohort_retention ?? []) as { cohort: string; size: number; retention: Record<string, number> }[]
  const best = cohorts.reduce<(typeof cohorts)[number] | null>(
    (a, c) => (c.retention?.['1'] != null && (a === null || c.retention['1'] > (a.retention['1'] ?? -1)) ? c : a), null)
  return [
    { label: 'Month 1 Retention', percent: avg['1'] ?? null, sublabel: 'average across cohorts', tone: avg['1'] != null ? toneOf(retentionSeverity(avg['1'])) : undefined },
    { label: 'Month 2 Retention', percent: avg['2'] ?? null, sublabel: 'average across cohorts' },
    { label: 'Cohorts Tracked', value: cohorts.length ? String(cohorts.length) : null },
    { label: 'Best Month 1 Cohort', percent: best ? best.retention['1'] : null, sublabel: best ? `${best.cohort}, ${best.size} customers` : undefined },
  ]
})
const toneOf = (s: Severity): StatItem['tone'] =>
  s === 'high' || s === 'critical' ? 'neg' : s === 'medium' ? 'warn' : s === 'low' ? 'pos' : undefined
</script>

<template>
  <!-- Customer counts strip: always visible above tab content -->
  <div v-if="counts" class="mb-6">
    <dl class="grid grid-cols-2 gap-x-6 gap-y-4 rounded-lg border border-outline-gray-1 bg-card p-4 sm:grid-cols-4 xl:grid-cols-9">
      <div v-for="tile in countTiles" :key="tile.label" class="min-w-0" :title="tile.hint">
        <dt class="text-sm text-ink-gray-6">{{ tile.label }}</dt>
        <dd class="tnum text-lg font-semibold text-ink-gray-9">
          <button
            v-if="tile.drill && tile.value"
            type="button"
            class="underline decoration-dotted underline-offset-4 hover:text-ink-blue-3"
            @click="drillOpen(tile.drill.title, tile.drill.params)"
          >{{ formatNumber(tile.value) }}</button>
          <template v-else>{{ formatNumber(tile.value) }}</template>
        </dd>
      </div>
    </dl>
    <details class="mt-3 rounded-lg border border-outline-gray-1 bg-card p-4" @toggle="periodOpen = ($event.target as HTMLDetailsElement).open">
      <summary class="cursor-pointer text-sm font-medium text-ink-gray-8">Customers by period</summary>
      <div class="mt-3 flex flex-wrap items-center gap-3">
        <Select
          v-model="periodGran"
          :options="[
            { value: 'auto', label: 'Auto' },
            { value: 'day', label: 'By day' },
            { value: 'week', label: 'By week' },
            { value: 'month', label: 'By month' },
          ]"
          class="text-sm"
        />
        <p class="text-sm text-ink-gray-6">Buyers, Repeat and Reactivated count a customer in every period they bought; New adds up to the window total.</p>
      </div>
      <div v-if="periodData?.periods.length" class="mt-3 max-h-80 overflow-auto">
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-card text-left text-ink-gray-6">
            <tr>
              <th class="py-1 pr-4 font-medium">Period</th>
              <th class="py-1 pr-4 text-right font-medium">Buyers</th>
              <th class="py-1 pr-4 text-right font-medium">New</th>
              <th class="py-1 pr-4 text-right font-medium">Repeat</th>
              <th class="py-1 text-right font-medium">Reactivated</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in periodData.periods" :key="p.period_start" class="border-t border-outline-gray-1">
              <td class="py-1 pr-4 text-ink-gray-8">{{ periodLabel(p) }}</td>
              <td class="tnum py-1 pr-4 text-right">{{ formatNumber(p.buyers) }}</td>
              <td class="tnum py-1 pr-4 text-right">
                <button v-if="p.new" type="button" class="underline decoration-dotted underline-offset-4 hover:text-ink-blue-3" @click="drillPeriod('new_customers', 'New Customers', p)">{{ formatNumber(p.new) }}</button>
                <template v-else>{{ formatNumber(p.new) }}</template>
              </td>
              <td class="tnum py-1 pr-4 text-right">{{ formatNumber(p.repeat) }}</td>
              <td class="tnum py-1 text-right">
                <button v-if="p.reactivated" type="button" class="underline decoration-dotted underline-offset-4 hover:text-ink-blue-3" @click="drillPeriod('reactivated_customers', 'Reactivated Customers', p)">{{ formatNumber(p.reactivated) }}</button>
                <template v-else>{{ formatNumber(p.reactivated) }}</template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="periodData" class="mt-3 text-sm text-ink-gray-6">No periods for this window.</p>
    </details>
  </div>

  <!-- Active Cutoff Selector + window / revenue-basis caption -->
  <div class="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
    <Select
      v-model="activeCutoff"
      :options="[
        { value: '3', label: 'Inactive after: 3 months' },
        { value: '6', label: 'Inactive after: 6 months' },
        { value: '12', label: 'Inactive after: 12 months' },
      ]"
      class="text-sm"
    />
    <p class="text-sm text-ink-gray-6">
      Window: {{ windowLabel }}<template v-if="revenueBasisNote"> · {{ revenueBasisNote }}</template>
    </p>
  </div>

  <!-- ═══ Customer Overview (Variant C: Hero + Attention Rail, + A's RFM ranked-bar list) ═══ -->
  <div v-if="activeTab === 'cust-overview'" class="grid gap-6 lg:grid-cols-3">

    <!-- Left: Hero Pareto + stat tiles + RFM ranked bar list (2/3 width) -->
    <div class="lg:col-span-2 flex flex-col gap-5">

      <!-- Hero Pareto panel -->
      <div class="p-5 rounded-lg border border-outline-gray-1 bg-accent-soft">
        <div class="inline-flex items-center h-5 px-2.5 rounded text-xs font-semibold bg-accent text-white mb-3">
          Key finding
        </div>
        <h3 class="text-sm font-semibold text-ink-gray-9 leading-snug mb-1">
          {{ formatPercent(paretoAnalysis.top_80_percent_customers as number) }} of customers
          account for 80% of revenue.
          <template v-if="atRiskSummaryCount > 0"> Most of them are At Risk.</template>
        </h3>
        <p class="text-xs text-ink-gray-6 mb-3">
          Concentration risk is structural; {{ atRiskSummaryCount }} at-risk accounts make it urgent.
        </p>

        <!-- Pareto SVG (rendered from full downsampled curve) -->
        <svg
          v-if="paretoCurve.length"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 560 220"
          width="100%"
          class="max-h-56"
          role="img"
          :aria-label="`Pareto chart: ${formatPercent(paretoAnalysis.top_80_percent_customers as number)} of customers generate 80% of revenue`"
        >
          <!-- Y-grid lines -->
          <line v-for="yp in [25, 50, 75, 100]" :key="yp" :x1="CHART_L" :y1="sy(yp)" :x2="CHART_R" :y2="sy(yp)" style="stroke: var(--outline-gray-1)" stroke-width="1" />
          <!-- 80% revenue threshold line (horizontal) -->
          <line :x1="CHART_L" :y1="sy(80)" :x2="CHART_R" :y2="sy(80)" style="stroke: var(--app-warn)" stroke-width="1.2" stroke-dasharray="4 3" opacity="0.7" />
          <!-- 80% threshold crossing line (vertical) -->
          <line v-if="pareto80ThresholdPct > 0" :x1="sx(pareto80ThresholdPct)" :y1="CHART_T" :x2="sx(pareto80ThresholdPct)" :y2="CHART_B" style="stroke: var(--app-warn)" stroke-width="1.2" stroke-dasharray="4 3" opacity="0.7" />
          <!-- Equal-distribution diagonal -->
          <line :x1="CHART_L" :y1="CHART_B" :x2="CHART_R" :y2="CHART_T" style="stroke: var(--outline-gray-2)" stroke-width="1" stroke-dasharray="3 3" />
          <!-- Area fill under the Pareto curve -->
          <path :d="paretoAreaPath" style="fill: var(--app-accent)" opacity="0.07" />
          <!-- Pareto curve line -->
          <path :d="paretoLinePath" style="stroke: var(--app-accent); fill: none" stroke-width="2.5" stroke-linejoin="round" />
          <!-- 80% threshold dot -->
          <circle v-if="pareto80ThresholdPct > 0" :cx="sx(pareto80ThresholdPct)" :cy="sy(80)" r="4" style="fill: var(--app-warn); stroke: var(--app-card)" stroke-width="1.5" />
          <!-- 80% annotation label -->
          <text v-if="pareto80ThresholdPct > 0" :x="sx(pareto80ThresholdPct) + 6" :y="sy(80) - 6" font-size="11" style="fill: var(--app-warn)" font-family="Inter,sans-serif">
            {{ formatPercent(pareto80ThresholdPct) }} customers → 80% revenue
          </text>
          <!-- Axis borders -->
          <line :x1="CHART_L" :y1="CHART_B" :x2="CHART_R" :y2="CHART_B" style="stroke: var(--outline-gray-2)" stroke-width="1" />
          <line :x1="CHART_L" :y1="CHART_T" :x2="CHART_L" :y2="CHART_B" style="stroke: var(--outline-gray-2)" stroke-width="1" />
          <!-- X-axis labels -->
          <text v-for="xp in [0, 20, 40, 60, 80, 100]" :key="xp" :x="sx(xp)" y="189" font-size="10" style="fill: var(--ink-gray-5)" text-anchor="middle" font-family="Inter,sans-serif">{{ xp }}%</text>
          <!-- Y-axis labels -->
          <text v-for="yp in [0, 25, 50, 75, 100]" :key="yp" x="44" :y="sy(yp) + 4" font-size="10" style="fill: var(--ink-gray-5)" text-anchor="end" font-family="Inter,sans-serif">{{ yp }}%</text>
          <!-- Axis titles -->
          <text :x="(CHART_L + CHART_R) / 2" y="214" font-size="11" style="fill: var(--ink-gray-5)" text-anchor="middle" font-family="Inter,sans-serif">% of customers (by CLV rank)</text>
          <text x="12" :y="(CHART_T + CHART_B) / 2" font-size="11" style="fill: var(--ink-gray-5)" text-anchor="middle" :transform="`rotate(-90,12,${(CHART_T + CHART_B) / 2})`" font-family="Inter,sans-serif">Cumulative revenue %</text>
        </svg>
        <div v-else class="h-32 flex items-center justify-center text-sm text-ink-gray-5">
          No Pareto data available
        </div>

        <!-- Legend + drill link -->
        <div class="flex flex-wrap items-center gap-4 mt-2 text-xs text-ink-gray-6">
          <span class="flex items-center gap-1.5">
            <span class="inline-block w-5 h-0.5 bg-accent rounded" aria-hidden="true" />
            Pareto curve
          </span>
          <span class="flex items-center gap-1.5">
            <span class="inline-block w-4 border-t border-dashed border-outline-gray-3" aria-hidden="true" />
            Equal distribution
          </span>
          <span class="flex items-center gap-1.5 text-warn">
            <span class="inline-block w-2 h-2 rounded-full bg-warn-fill" aria-hidden="true" />
            80% revenue threshold
          </span>
          <button
            class="ml-auto text-xs text-accent hover:underline"
            @click="drillOpen('Top Customers', { metric: 'top_customers' })"
          >
            View rankings →
          </button>
        </div>
      </div>

      <!-- Stat tiles: CLV portfolio / Diamond tier / Champions / Quote conversion -->
      <div class="grid grid-cols-2 sm:grid-cols-4 rounded-lg border border-outline-gray-1 bg-surface-white overflow-hidden">
        <div class="px-4 py-3 border-b sm:border-b-0 border-r border-outline-gray-1">
          <div class="text-xs font-medium uppercase tracking-wide text-ink-gray-5 mb-1">CLV Portfolio</div>
          <div class="text-lg font-semibold text-ink-gray-9 tnum leading-tight">{{ money(summary.total_clv as number) }}</div>
          <div class="text-xs text-ink-gray-6 mt-0.5">{{ money(summary.avg_clv as number) }} avg</div>
        </div>
        <div class="px-4 py-3 border-b sm:border-b-0 sm:border-r border-outline-gray-1">
          <div class="text-xs font-medium uppercase tracking-wide text-ink-gray-5 mb-1">Diamond Tier</div>
          <div class="text-lg font-semibold text-ink-gray-9 tnum leading-tight">{{ formatNumber((summary.clv_tier_distribution as Record<string,number>)?.Diamond ?? 0) }}</div>
          <div class="text-xs text-ink-gray-6 mt-0.5">Top 10% → {{ formatPercent(paretoAnalysis.top_10_percent_contribute as number) }}</div>
        </div>
        <div class="px-4 py-3 border-r border-outline-gray-1">
          <div class="text-xs font-medium uppercase tracking-wide text-ink-gray-5 mb-1">Champions</div>
          <div class="text-lg font-semibold text-ink-gray-9 tnum leading-tight">{{ formatNumber((summary.rfm_segment_distribution as Record<string,number>)?.Champions ?? 0) }}</div>
          <div class="text-xs text-ink-gray-6 mt-0.5">+ {{ formatNumber((summary.rfm_segment_distribution as Record<string,number>)?.['Loyal Customers'] ?? 0) }} Loyal</div>
        </div>
        <div class="px-4 py-3">
          <div class="text-xs font-medium uppercase tracking-wide text-ink-gray-5 mb-1">Quote Conversion</div>
          <div class="text-lg font-semibold text-ink-gray-9 tnum leading-tight">{{ summary.quote_conversion_rate != null ? formatPercent(summary.quote_conversion_rate as number) : NO_VALUE }}</div>
          <div class="text-xs text-ink-gray-6 mt-0.5">{{ formatNumber(summary.converted_quotes as number) }} / {{ formatNumber(summary.total_quotes as number) }}</div>
        </div>
      </div>

      <!-- RFM ranked bar list (Variant A: horizontal, sorted by count desc) -->
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white">
        <div class="px-4 py-3 border-b border-outline-gray-1">
          <SectionHeader variant="caption" title="RFM Segment Distribution" :level="3"
            :hint="`${formatNumber(summary.total_customers as number)} customers`" />
        </div>
        <div class="p-4 space-y-2.5">
          <div
            v-for="seg in rfmSortedSegments"
            :key="seg.label"
            class="flex items-center gap-3 min-w-0"
          >
            <span class="w-32 shrink-0 text-sm text-ink-gray-7 truncate">{{ seg.label }}</span>
            <div class="flex-1 min-w-0">
              <div
                class="h-2 rounded-full bg-surface-gray-2"
                role="img"
                :aria-label="`${seg.label}: ${seg.count} customers (${formatPercent(seg.pct)})`"
              >
                <div class="h-full rounded-full" :class="seg.fillClass" :style="{ width: `${seg.barWidth}%` }" />
              </div>
            </div>
            <span class="tnum text-sm font-medium text-ink-gray-9 w-8 text-right shrink-0">{{ formatNumber(seg.count) }}</span>
            <span class="text-xs text-ink-gray-6 w-10 text-right shrink-0">{{ formatPercent(seg.pct) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Right: Attention Rail (1/3 width, at-risk customers sorted by CLV) -->
    <div class="flex flex-col rounded-lg border border-outline-gray-1 bg-surface-white overflow-hidden min-h-0">
      <!-- Rail header -->
      <div class="px-4 py-3 bg-surface-red-1 border-b border-outline-gray-1 shrink-0">
        <div class="flex items-center gap-2 text-sm font-semibold text-ink-gray-9">
          <AlertTriangle class="w-3.5 h-3.5 text-neg shrink-0" aria-hidden="true" />
          Needs Attention
        </div>
        <div class="text-xs text-ink-gray-6 mt-0.5">
          {{ atRiskSummaryCount }} accounts · High + Critical churn risk
        </div>
      </div>

      <!-- Critical section -->
      <template v-if="atRiskCritical.length">
        <div class="px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-neg bg-surface-gray-1 border-b border-outline-gray-1">
          Critical ({{ atRiskCritical.length }})
        </div>
        <div
          v-for="item in atRiskCritical.slice(0, 3)"
          :key="item.customer_id"
          class="px-4 py-3 border-b border-outline-gray-1"
        >
          <div class="flex items-start justify-between gap-2 mb-1">
            <span class="text-xs font-medium text-ink-gray-9 leading-snug truncate">{{ item.customer_name }}</span>
            <Badge v-bind="severityBadge('critical')" size="sm" class="shrink-0" />
          </div>
          <div class="flex flex-wrap items-center gap-x-3 gap-y-0.5">
            <span class="tnum text-sm font-semibold text-ink-gray-8">{{ money(item.historical_clv) }}</span>
            <span class="text-xs text-ink-gray-6">{{ item.recency_days }}d inactive</span>
            <span v-if="(item.outstanding_amount ?? 0) > 0" class="text-xs text-warn">{{ money(item.outstanding_amount) }} o/s</span>
          </div>
          <button class="mt-1.5 text-xs text-accent hover:underline" @click="viewCustomerDetail(item.customer_id)">
            View →
          </button>
        </div>
      </template>

      <!-- High section -->
      <template v-if="atRiskHigh.length">
        <div class="px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-warn bg-surface-gray-1 border-b border-outline-gray-1">
          High ({{ atRiskHigh.length }})
        </div>
        <div
          v-for="item in atRiskHigh.slice(0, 4)"
          :key="item.customer_id"
          class="px-4 py-3 border-b border-outline-gray-1"
        >
          <div class="flex items-start justify-between gap-2 mb-1">
            <span class="text-xs font-medium text-ink-gray-9 leading-snug truncate">{{ item.customer_name }}</span>
            <Badge v-bind="severityBadge('high')" size="sm" class="shrink-0" />
          </div>
          <div class="flex flex-wrap items-center gap-x-3 gap-y-0.5">
            <span class="tnum text-sm font-semibold text-ink-gray-8">{{ money(item.historical_clv) }}</span>
            <span class="text-xs text-ink-gray-6">{{ item.recency_days }}d inactive</span>
            <span v-if="(item.outstanding_amount ?? 0) > 0" class="text-xs text-warn">{{ money(item.outstanding_amount) }} o/s</span>
          </div>
          <button class="mt-1.5 text-xs text-accent hover:underline" @click="viewCustomerDetail(item.customer_id)">
            View →
          </button>
        </div>
      </template>

      <!-- Footer: actions count -->
      <div class="px-4 py-3 bg-surface-gray-1 border-t border-outline-gray-1 mt-auto shrink-0">
        <div class="text-xs text-ink-gray-6 mb-2">{{ nextActionsTotal }} actions queued across flagged accounts</div>
      </div>

      <!-- Health distribution mini-grid -->
      <div class="px-4 py-3 border-t border-outline-gray-1 shrink-0">
        <div class="text-xs font-medium uppercase tracking-wider text-ink-gray-5 mb-2">Health distribution</div>
        <div class="grid grid-cols-2 gap-1.5">
          <div
            v-for="(count, status) in healthDistribution"
            :key="status"
            class="text-center py-2 rounded"
            :class="healthDistTint(String(status))"
          >
            <div class="text-sm font-semibold text-ink-gray-9 tnum">{{ formatNumber(count) }}</div>
            <div class="text-xs text-ink-gray-6">{{ status }}</div>
          </div>
        </div>
        <button
          class="mt-2 text-xs text-accent hover:underline"
          @click="drillOpen('Customers by Health Status', { metric: 'customers' })"
        >
          View customers →
        </button>
      </div>
    </div>
  </div>

  <!-- ═══ Customers (list) ═══ -->
  <div v-if="activeTab === 'cust-list'" class="space-y-4">
    <TabBrief :brief="tabBriefs['cust-list']" />
    <StatStrip :items="listStrip" :currency="baseCurrency" />
    <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <section class="min-w-0 rounded-lg border border-outline-gray-1 bg-card">
        <h3 class="border-b border-outline-gray-1 px-4 py-3 text-base font-semibold text-ink-gray-9">Critical accounts</h3>
        <p v-if="!criticalTop.length" class="px-4 py-6 text-sm text-ink-gray-6">No customers are at Critical churn risk.</p>
        <ol v-else class="divide-y divide-outline-gray-1">
          <li v-for="(c, i) in criticalTop" :key="c.customer_id" class="flex min-w-0 items-center gap-3 px-4 py-3">
            <span class="tnum w-5 shrink-0 text-sm text-ink-gray-6">{{ i + 1 }}</span>
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-semibold text-ink-gray-9">{{ c.customer_name || c.customer_id }}</p>
              <p class="truncate text-xs text-ink-gray-6">{{ c.territory || NO_VALUE }} · {{ c.recency_days == null ? NO_VALUE : `${c.recency_days}d inactive` }}</p>
            </div>
            <Badge theme="gray" variant="subtle" :label="c.clv_tier || '-'" size="sm" />
            <span class="tnum shrink-0 text-sm font-semibold text-ink-gray-9">{{ money(c.total_clv) }}</span>
          </li>
        </ol>
      </section>
      <section class="min-w-0 rounded-lg border border-outline-gray-1 bg-card">
        <h3 class="border-b border-outline-gray-1 px-4 py-3 text-base font-semibold text-ink-gray-9">Health by tier</h3>
        <table class="w-full text-sm">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Tier</th>
              <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Accounts</th>
              <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">At Risk</th>
              <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Healthy</th>
              <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Critical</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in tierHealth" :key="t.tier" class="border-b border-outline-gray-1">
              <td class="px-4 py-2 font-medium text-ink-gray-9">{{ t.tier }}</td>
              <td class="tnum px-4 py-2 text-right text-ink-gray-9">{{ t.accounts }}</td>
              <td class="tnum px-4 py-2 text-right text-ink-red-3">{{ t.atRisk }}</td>
              <td class="tnum px-4 py-2 text-right text-ink-green-3">{{ t.healthy }}</td>
              <td class="tnum px-4 py-2 text-right text-ink-gray-9">{{ t.critical }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
    <section class="rounded-lg border border-outline-gray-1 bg-card" aria-label="RFM segments">
      <h3 class="border-b border-outline-gray-1 px-4 py-3 text-base font-semibold text-ink-gray-9">RFM segments</h3>
      <dl class="grid grid-cols-2 gap-3 p-4 sm:grid-cols-4 lg:grid-cols-8">
        <div v-for="seg in rfmSortedSegments" :key="seg.label" class="min-w-0 rounded-md border border-outline-gray-1 bg-surface-gray-1 p-3">
          <dt class="truncate text-xs uppercase tracking-wide text-ink-gray-6" :title="seg.label">{{ seg.label }}</dt>
          <dd class="tnum text-xl font-semibold text-ink-gray-9">{{ formatNumber(seg.count) }}</dd>
          <dd class="text-xs text-ink-gray-6">{{ formatPercent(seg.pct) }} of customers</dd>
        </div>
      </dl>
    </section>
    <div class="flex flex-wrap gap-4 p-4 bg-surface-white rounded-lg border border-outline-gray-1">
      <div class="flex-1 min-w-[200px]">
        <FormControl
          v-model="customerFilter" type="text" :debounce="300"
          placeholder="Search by name, ID, or territory..."
          aria-label="Search customers"
        >
          <template #prefix>
            <Search class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
          </template>
        </FormControl>
      </div>
      <div class="flex items-center gap-2">
        <Filter class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
        <Select v-model="tierFilter" :options="tierFilterOptions" aria-label="Filter by tier" class="text-sm" />
        <Select v-model="rfmFilter" :options="rfmSegmentFilterOptions" aria-label="Filter by RFM segment" class="text-sm" />
        <Select v-model="riskFilter" :options="riskFilterOptions" aria-label="Filter by risk level" class="text-sm" />
      </div>
      <span class="self-center text-sm text-ink-gray-6">
        {{ customers.length }} of {{ (props.data.customers as unknown[])?.length || 0 }} customers
      </span>
    </div>

    <div v-if="recentCustomerDetails.length > 0 && !customerFilter && !tierFilter && !riskFilter && !rfmFilter"
      class="flex items-center gap-3 px-1">
      <Star class="w-4 h-4 text-ink-gray-5 flex-shrink-0" aria-hidden="true" />
      <span class="text-sm font-medium text-ink-gray-6">Recent:</span>
      <div class="flex gap-2 flex-wrap">
        <Button v-for="rc in recentCustomerDetails" :key="rc.customer_id" variant="subtle" size="sm"
          @click="viewCustomerDetail(rc.customer_id)">
          {{ rc.customer_name }}
        </Button>
      </div>
    </div>

    <div class="overflow-hidden bg-surface-white rounded-lg border border-outline-gray-1">
      <table class="w-full">
        <caption class="sr-only">Customers by lifetime value, highest first. Shows up to 100 rows of the filtered set.</caption>
        <thead class="bg-surface-gray-1">
          <tr>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-left text-ink-gray-6">Customer</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-left text-ink-gray-6">RFM Segment</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-left text-ink-gray-6">CLV Tier</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Total CLV</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Gross Profit</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-center text-ink-gray-6">Health</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-center text-ink-gray-6">Churn Risk</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Orders</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Recency</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-center text-ink-gray-6"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-gray-1">
          <tr v-for="customer in customers.slice(0, 100)" :key="customer.customer_id"
            class="hover:bg-surface-gray-1 cursor-pointer transition-colors motion-reduce:transition-none"
            tabindex="0" role="button"
            @click="viewCustomerDetail(customer.customer_id)"
            @keydown.enter="viewCustomerDetail(customer.customer_id)"
            @keydown.space.prevent="viewCustomerDetail(customer.customer_id)">
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <div>
                  <p class="font-medium text-ink-gray-8">{{ customer.customer_name }}</p>
                  <p class="text-sm text-ink-gray-6">{{ customer.territory || 'No territory' }}</p>
                </div>
              </div>
            </td>
            <td class="px-4 py-3"><Badge theme="gray" variant="subtle" :label="customer.rfm_segment || '-'" size="sm" /></td>
            <td class="px-4 py-3"><Badge theme="gray" variant="subtle" :label="customer.clv_tier || '-'" size="sm" /></td>
            <td class="px-4 py-3 text-right tnum font-medium text-ink-gray-8">{{ money(customer.total_clv ?? customer.historical_clv) }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-7">{{ money(customer.gross_profit) }}</td>
            <td class="px-4 py-3 text-center">
              <Badge v-bind="severityBadge(healthSeverity(customer.health_status))" :label="customer.health_score == null ? NO_VALUE : String(Math.round(customer.health_score))" size="sm" />
            </td>
            <td class="px-4 py-3 text-center">
              <Badge v-bind="severityBadge(churnSeverity(customer.churn_risk))" :label="customer.churn_risk || '-'" size="sm" />
            </td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-7">{{ customer.order_count }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-6">{{ customer.recency_days == null ? NO_VALUE : `${Math.round(customer.recency_days)}d` }}</td>
            <td class="px-4 py-3 text-center"><ChevronRight class="w-4 h-4 text-ink-gray-5 inline" aria-hidden="true" /></td>
          </tr>
        </tbody>
      </table>
      <div v-if="customers.length > 100" class="px-4 py-3 text-sm text-center text-ink-gray-6 bg-surface-gray-1">
        Showing 100 of {{ customers.length }} customers
      </div>
    </div>
    <TabActions class="mt-6" :actions="tabBriefs['cust-list']?.actions" />
  </div>

  <!-- ═══ Geography ═══ -->
  <div v-if="activeTab === 'cust-geography'" class="space-y-6">
    <TabBrief :brief="tabBriefs['cust-geography']" />
    <StatStrip :items="geoStrip" :currency="baseCurrency" />

    <div class="rounded-lg border border-outline-gray-1 bg-card">
      <div class="h-[500px]">
        <TerritoryMap
          :worldData="territoryWorld"
          :indiaData="territoryIndia"
          :unmapped="territoryUnmapped"
          metric="Customers"
          colorScale="blue"
        />
      </div>
      <p v-if="unmappedCustomers > 0" class="border-t border-outline-gray-1 px-4 py-3 text-sm text-ink-gray-6">
        Shaded regions cover {{ formatNumber(mappedCustomers) }} of
        {{ formatNumber(totalGeoCustomers) }} customers
        ({{ formatPercent(mapCoveragePct) }}). City territories are counted
        under their parent state, so click India to see them. The remaining
        {{ formatNumber(unmappedCustomers) }} have no usable parent territory;
        those with a territory name are listed below the map.
      </p>
    </div>

    <!-- Dimension-driven, drillable breakdown -->
    <div class="overflow-hidden bg-surface-white rounded-lg border border-outline-gray-1">
      <div class="flex flex-wrap items-center gap-3 px-4 py-3 border-b border-outline-gray-1">
        <SectionHeader variant="caption"
          :title="geoDrill ? 'Customers' : (GEO_DIM_LABELS[geoDim] + ' Breakdown')" :level="3" />
        <div class="flex flex-wrap items-center gap-2 ml-auto">
          <Select v-if="!geoDrill" v-model="geoDim" aria-label="Group by" class="text-sm"
            :options="[{ value: 'territory', label: 'By Territory' }, { value: 'item_group', label: 'By Item Group' }, { value: 'sales_person', label: 'By Salesperson' }]" />
          <Select v-model="geoSortKey" aria-label="Sort by measure" class="text-sm"
            :options="[{ value: 'revenue', label: 'Sort: Revenue' }, { value: 'gross_profit', label: 'Sort: Gross Profit' }, { value: 'customers', label: 'Sort: Customers' }, { value: 'margin_pct', label: 'Sort: Margin %' }, { value: 'transactions', label: 'Sort: Transactions' }]" />
        </div>
      </div>

      <!-- Narrowing filters -->
      <div class="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-outline-gray-1 bg-surface-gray-1">
        <Filter class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
        <Select v-model="geoNarrow.territory" aria-label="Filter by territory" class="text-sm"
          :options="asSelectOptions('All territories', geoOptions.territories)" />
        <Select v-model="geoNarrow.item_group" aria-label="Filter by item group" class="text-sm"
          :options="asSelectOptions('All item groups', geoOptions.item_groups)" />
        <Select v-model="geoNarrow.sales_person" aria-label="Filter by salesperson" class="text-sm"
          :options="asSelectOptions('All salespeople', geoOptions.sales_persons)" />
        <Button v-if="geoActiveNarrow.length || geoDrill" variant="outline" theme="gray" size="sm" label="Clear" @click="clearGeoAll" />
        <span v-if="geoTotals" class="ml-auto text-sm text-ink-gray-6">
          {{ money(geoTotals.revenue) }} rev · {{ formatPercent(geoTotals.margin_pct) }} margin · {{ formatNumber(geoTotals.customers) }} customers
        </span>
      </div>

      <!-- Drill breadcrumb -->
      <div v-if="geoDrill" class="flex flex-wrap items-center gap-2 px-4 py-2 border-b border-outline-gray-1">
        <Button variant="subtle" theme="gray" size="sm" :label="'Back to ' + GEO_DIM_LABELS[geoDim]" @click="clearGeoDrill" />
        <Badge v-for="[f, v] in geoActiveNarrow" :key="f" theme="blue" variant="subtle"
          :label="GEO_DIM_LABELS[f] + ': ' + v" size="sm" />
      </div>

      <div v-if="geoLoading" class="p-6"><SkeletonBlock :rows="6" /></div>
      <table v-else-if="geoRows.length" class="w-full">
        <caption class="sr-only">Sales breakdown: revenue, gross profit, margin, customers and transactions.</caption>
        <thead class="bg-surface-gray-1">
          <tr>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-left text-ink-gray-6">
              {{ effectiveGeoDim === 'customer' ? 'Customer' : GEO_DIM_LABELS[geoDim] }}
            </th>
            <th v-if="effectiveGeoDim !== 'customer'" scope="col" tabindex="0" role="button"
              class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6 cursor-pointer select-none"
              :aria-sort="geoSortKey === 'customers' ? (geoSortDir === 'asc' ? 'ascending' : 'descending') : 'none'"
              @click="setGeoSort('customers')" @keydown.enter="setGeoSort('customers')" @keydown.space.prevent="setGeoSort('customers')">
              Customers <span v-if="geoSortKey === 'customers'" aria-hidden="true">{{ geoSortDir === 'desc' ? '▼' : '▲' }}</span>
            </th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Rev share</th>
            <th scope="col" tabindex="0" role="button" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6 cursor-pointer select-none"
              :aria-sort="geoSortKey === 'revenue' ? (geoSortDir === 'asc' ? 'ascending' : 'descending') : 'none'"
              @click="setGeoSort('revenue')" @keydown.enter="setGeoSort('revenue')" @keydown.space.prevent="setGeoSort('revenue')">
              Revenue <span v-if="geoSortKey === 'revenue'" aria-hidden="true">{{ geoSortDir === 'desc' ? '▼' : '▲' }}</span>
            </th>
            <th scope="col" tabindex="0" role="button" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6 cursor-pointer select-none"
              :aria-sort="geoSortKey === 'gross_profit' ? (geoSortDir === 'asc' ? 'ascending' : 'descending') : 'none'"
              @click="setGeoSort('gross_profit')" @keydown.enter="setGeoSort('gross_profit')" @keydown.space.prevent="setGeoSort('gross_profit')">
              Gross Profit <span v-if="geoSortKey === 'gross_profit'" aria-hidden="true">{{ geoSortDir === 'desc' ? '▼' : '▲' }}</span>
            </th>
            <th scope="col" tabindex="0" role="button" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6 cursor-pointer select-none"
              :aria-sort="geoSortKey === 'margin_pct' ? (geoSortDir === 'asc' ? 'ascending' : 'descending') : 'none'"
              @click="setGeoSort('margin_pct')" @keydown.enter="setGeoSort('margin_pct')" @keydown.space.prevent="setGeoSort('margin_pct')">
              Margin % <span v-if="geoSortKey === 'margin_pct'" aria-hidden="true">{{ geoSortDir === 'desc' ? '▼' : '▲' }}</span>
            </th>
            <th scope="col" tabindex="0" role="button" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6 cursor-pointer select-none"
              :aria-sort="geoSortKey === 'transactions' ? (geoSortDir === 'asc' ? 'ascending' : 'descending') : 'none'"
              @click="setGeoSort('transactions')" @keydown.enter="setGeoSort('transactions')" @keydown.space.prevent="setGeoSort('transactions')">
              Transactions <span v-if="geoSortKey === 'transactions'" aria-hidden="true">{{ geoSortDir === 'desc' ? '▼' : '▲' }}</span>
            </th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Avg order</th>
            <th scope="col" class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-gray-1">
          <tr v-for="row in geoRows.slice(0, 100)" :key="row.key || row.label"
            class="hover:bg-surface-gray-1 cursor-pointer transition-colors motion-reduce:transition-none" tabindex="0" role="button"
            @click="geoRowClick(row)" @keydown.enter="geoRowClick(row)" @keydown.space.prevent="geoRowClick(row)">
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <MapPin v-if="effectiveGeoDim === 'territory'" class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
                <span class="font-medium text-ink-gray-8">{{ row.label }}</span>
              </div>
            </td>
            <td v-if="effectiveGeoDim !== 'customer'" class="px-4 py-3 text-right tnum text-ink-gray-7">{{ formatNumber(row.customers) }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-6">{{ Number(geoTotals?.revenue) ? formatPercent((Number(row.revenue) / Number(geoTotals?.revenue)) * 100) : NO_VALUE }}</td>
            <td class="px-4 py-3 text-right tnum font-medium text-ink-gray-8">{{ money(row.revenue) }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-7">{{ money(row.gross_profit) }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-6">{{ formatPercent(row.margin_pct) }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-6">{{ formatNumber(row.transactions) }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-6">{{ Number(row.transactions) ? money(Number(row.revenue) / Number(row.transactions)) : NO_VALUE }}</td>
            <td class="px-4 py-3 text-center"><ChevronRight class="w-4 h-4 text-ink-gray-5 inline" aria-hidden="true" /></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="p-10 text-center text-ink-gray-6">
        <MapPin class="w-8 h-8 mx-auto text-ink-gray-4 mb-2" aria-hidden="true" />
        <p class="text-sm">No data for this slice.</p>
      </div>
      <div v-if="geoRows.length > 100" class="px-4 py-3 text-sm text-center text-ink-gray-6 bg-surface-gray-1">
        Showing 100 of {{ geoRows.length }} rows
      </div>
    </div>

    <div v-if="customerGroups.length" class="rounded-lg border border-outline-gray-1 bg-card overflow-x-auto">
      <div class="px-4 py-3 border-b border-outline-gray-1">
        <h3 class="text-base font-semibold text-ink-gray-9">Customer group breakdown</h3>
        <p class="text-xs text-ink-gray-6">Revenue and health by customer group.</p>
      </div>
      <table class="w-full">
        <caption class="sr-only">Customer groups: accounts, revenue, average order value and average health score.</caption>
        <thead class="bg-surface-gray-1">
          <tr>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-left text-ink-gray-6">Customer group</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Accounts</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Revenue</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Avg order value</th>
            <th scope="col" class="px-4 py-3 text-sm font-medium text-right text-ink-gray-6">Avg health score</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-gray-1">
          <tr v-for="g in customerGroups.slice(0, 10)" :key="g.customer_group">
            <td class="px-4 py-3 font-medium text-ink-gray-8">{{ g.customer_group || 'Unclassified' }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-7">{{ formatNumber(g.customer_count) }}</td>
            <td class="px-4 py-3 text-right tnum font-medium text-ink-gray-8">{{ money(g.total_revenue) }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-7">{{ money(g.avg_order_value) }}</td>
            <td class="px-4 py-3 text-right tnum text-ink-gray-7">{{ formatNumber(g.avg_health_score, 1) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="customerGroups.length > 10" class="px-4 py-3 text-sm text-center text-ink-gray-6 bg-surface-gray-1">
        Showing 10 of {{ customerGroups.length }} groups
      </div>
    </div>
    <TabActions class="mt-6" :actions="tabBriefs['cust-geography']?.actions" />
  </div>

  <!-- ═══ Actions ═══ -->
  <div v-if="activeTab === 'cust-actions'" class="space-y-6">
    <TabBrief :brief="tabBriefs['cust-actions']" />
    <StatStrip :items="actionsStrip" :currency="baseCurrency" />

    <!-- Filters -->
    <div class="flex flex-wrap items-center gap-3 p-4 bg-surface-white rounded-lg border border-outline-gray-1">
      <Filter class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
      <Select v-model="actionType" :options="actionTypeOptions" aria-label="Filter by action type" class="text-sm" />
      <Select v-model="actionPriority" :options="actionPriorityOptions" aria-label="Filter by priority" class="text-sm" />
      <Button variant="outline" label="Clear filters" @click="clearActionFilters" />
      <span class="ml-auto text-sm text-ink-gray-6">{{ actionsCountLabel }}</span>
    </div>

    <!-- Empty state -->
    <div v-if="!filteredActions.length" class="p-10 text-center bg-surface-white rounded-lg border border-outline-gray-1">
      <Target class="w-8 h-8 mx-auto text-ink-gray-4" aria-hidden="true" />
      <p class="mt-3 text-sm text-ink-gray-6">No action items match the current filters.</p>
    </div>

    <!-- Action cards, biggest money at stake first -->
    <div v-else class="space-y-3">
      <div v-for="item in filteredActions.slice(0, 50)" :key="item.customer_id"
        class="bg-surface-white rounded-lg border border-outline-gray-1 overflow-hidden">
        <!-- Header: customer, tier/risk/health, money at stake, drill-in -->
        <button type="button"
          class="w-full flex items-center justify-between gap-4 px-4 py-3 text-left hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
          @click="viewCustomerDetail(item.customer_id)">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h4 class="font-semibold text-ink-gray-9 truncate">{{ item.customer_name }}</h4>
              <Badge v-if="hasHighPriority(item)" theme="red" variant="subtle" label="High priority" size="sm" />
            </div>
            <div class="flex flex-wrap items-center gap-2 mt-1">
              <Badge theme="gray" variant="subtle" :label="item.clv_tier || '-'" size="sm" />
              <Badge v-bind="severityBadge(churnSeverity(item.churn_risk))" :label="(item.churn_risk || '-') + ' risk'" size="sm" />
              <Badge v-bind="severityBadge(healthSeverity(item.health_status))" :label="item.health_status || '-'" size="sm" />
            </div>
          </div>
          <div class="flex items-center gap-3 shrink-0">
            <div class="text-right">
              <div class="text-xs text-ink-gray-5">At stake</div>
              <div class="font-semibold tnum text-ink-gray-9">{{ money(atStake(item)) }}</div>
            </div>
            <ChevronRight class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
          </div>
        </button>
        <!-- Recommendations, each with its own money figure -->
        <div class="divide-y divide-outline-gray-1 border-t border-outline-gray-1">
          <div v-for="rec in item.recommendations" :key="rec.action" class="px-4 py-3">
            <div class="flex items-center justify-between gap-3 mb-1">
              <span class="text-sm font-semibold text-ink-gray-8">{{ actionLabel(rec.action) }}</span>
              <div class="flex items-center gap-2 shrink-0">
                <span v-if="recImpact(item, rec) > 0" class="text-sm tnum text-ink-gray-6">
                  {{ recImpactLabel(rec) }}: <span class="font-medium text-ink-gray-9">{{ money(recImpact(item, rec)) }}</span>
                </span>
                <Badge v-bind="severityBadge(prioritySeverity(rec.priority))" :label="rec.priority" size="sm" />
              </div>
            </div>
            <p class="text-sm text-ink-gray-7">{{ rec.description }}</p>
            <p class="mt-1 text-sm text-ink-gray-6">{{ rec.suggestion }}</p>
          </div>
        </div>
      </div>
    </div>
    <TabActions class="mt-6" :actions="tabBriefs['cust-actions']?.actions" />
  </div>

  <!-- ═══ Cohorts ═══ -->
  <div v-if="activeTab === 'cust-cohorts'" class="space-y-6">
    <TabBrief :brief="tabBriefs['cust-cohorts']" />
    <StatStrip :items="cohortStrip" :currency="baseCurrency" />
    <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
      <SectionHeader variant="caption" title="Average Retention by Month" :level="3" />
      <div class="flex flex-wrap gap-2 mt-4">
        <div v-for="(retention, month) in (cohortAnalysis.average_retention as Record<string, number>)" :key="month"
          class="px-3 py-2 text-center bg-surface-gray-1 rounded-lg">
          <p class="text-sm text-ink-gray-6">Month {{ month }}</p>
          <p class="text-lg font-bold text-ink-gray-9">{{ formatPercent(retention) }}</p>
        </div>
      </div>
    </div>
    <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
      <SectionHeader variant="caption" title="Cohort Retention Matrix" :level="3" />
      <div class="overflow-x-auto mt-4">
        <table class="w-full text-sm">
          <caption class="sr-only">Cohort retention by month since first purchase.</caption>
          <thead>
            <tr>
              <th scope="col" class="px-3 py-2 text-left text-ink-gray-6">Cohort</th>
              <th scope="col" class="px-3 py-2 text-right text-ink-gray-6">Size</th>
              <th v-for="n in 12" :key="n" scope="col" class="px-3 py-2 text-center text-ink-gray-6">M{{ n - 1 }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="cohort in (cohortAnalysis.cohort_retention as Record<string, unknown>[])" :key="cohort.cohort as string">
              <td class="px-3 py-2 font-medium text-ink-gray-8">{{ cohort.cohort }}</td>
              <td class="px-3 py-2 text-right text-ink-gray-7">{{ cohort.size }}</td>
              <td v-for="n in 12" :key="n" class="px-3 py-2 text-center">
                <Badge v-if="(cohort.retention as Record<string, number>)[n - 1] !== undefined"
                  v-bind="severityBadge(retentionSeverity((cohort.retention as Record<string, number>)[n - 1]))"
                  :label="formatPercent((cohort.retention as Record<string, number>)[n - 1])" size="sm" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <TabActions class="mt-6" :actions="tabBriefs['cust-cohorts']?.actions" />
  </div>

  <!-- ═══ Patterns ═══ -->
  <div v-if="activeTab === 'cust-patterns'" class="space-y-6">
    <TabBrief :brief="patternsBrief" />
    <div v-if="isLoadingPatterns" class="flex items-center justify-center h-64">
      <div class="text-center space-y-3">
        <SkeletonBlock class="h-24 w-96 rounded-xl mx-auto" />
        <p class="text-sm text-ink-gray-6">Loading purchase patterns...</p>
      </div>
    </div>

    <div v-else-if="purchasePatternsData?.status === 'error'"
      class="rounded-lg border border-outline-gray-1 bg-card p-6">
      <p class="text-sm font-medium text-ink-gray-8">Purchase pattern analysis could not be completed.</p>
      <p class="mt-1 text-sm text-ink-gray-6">{{ purchasePatternsData.message || 'The analysis returned an error.' }}</p>
    </div>

    <div v-else-if="purchasePatternsData">
      <div class="p-4 bg-surface-gray-1 rounded-lg border border-outline-gray-1">
        <p class="text-sm text-ink-gray-7">
          <strong>Analysis Scope:</strong> {{ windowLabel }} · Top {{ purchasePatternsData.analysis_scope?.top_percentile }}% of customers by CLV
          ({{ purchasePatternsData.analysis_scope?.customer_count }} customers, {{ purchasePatternsData.analysis_scope?.transaction_count }} transactions)
        </p>
      </div>

      <div class="grid gap-4 lg:grid-cols-4">
        <KpiCard
          label="Total Orders"
          :value="formatNumber(purchasePatternsData.summary?.total_orders as number)"
          variant="tile"
        />
        <KpiCard
          label="Total Revenue"
          :value="money(purchasePatternsData.summary?.total_revenue as number)"
          variant="tile"
        />
        <KpiCard
          label="Peak Day"
          :value="purchasePatternsData.summary?.peak_day as string | undefined"
          variant="tile"
        />
        <KpiCard
          label="Peak Month"
          :value="purchasePatternsData.summary?.peak_month as string | undefined"
          variant="tile"
        />
      </div>

      <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
        <SectionHeader variant="caption" title="Day of Week Analysis" :level="3" />
        <div class="overflow-x-auto mt-4">
          <table class="w-full text-sm">
            <caption class="sr-only">Order activity by day of week.</caption>
            <thead class="bg-surface-gray-1">
              <tr>
                <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Day</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Orders</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Revenue</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Gross Profit</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Avg Order</th>
                <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Activity</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="day in (purchasePatternsData.day_of_week?.data as Record<string, unknown>[])" :key="day.day_name as string"
                :class="day.day_name === purchasePatternsData.day_of_week?.peak_day ? 'bg-surface-gray-1' : 'hover:bg-surface-gray-1'">
                <td class="px-4 py-2 font-medium text-ink-gray-8">
                  {{ day.day_name }}
                  <Badge v-if="day.day_name === purchasePatternsData.day_of_week?.peak_day" theme="gray" variant="subtle" label="Peak" size="sm" class="ml-2" />
                </td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ formatNumber(day.order_count as number) }}</td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ money(day.total_revenue as number) }}</td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ money(day.gross_profit as number) }}</td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ money(day.avg_order_value as number) }}</td>
                <td class="px-4 py-2">
                  <div class="w-full bg-surface-gray-2 rounded-full h-2" role="img" :aria-label="'Activity bar: ' + day.day_name">
                    <div class="bg-surface-gray-4 h-2 rounded-full" :style="{ width: `${maxDayOfWeekOrders > 0 ? ((day.order_count as number) / maxDayOfWeekOrders) * 100 : 0}%` }" />
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
        <SectionHeader variant="caption" title="Monthly Trends" :level="3" />
        <div class="overflow-x-auto mt-4">
          <table class="w-full text-sm">
            <caption class="sr-only">Order activity by month.</caption>
            <thead class="bg-surface-gray-1">
              <tr>
                <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Month</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Orders</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Revenue</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Gross Profit</th>
                <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Avg Order</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="month in (purchasePatternsData.monthly?.data as Record<string, unknown>[])" :key="month.month_name as string"
                :class="month.month_name === purchasePatternsData.monthly?.peak_month ? 'bg-surface-gray-1' : 'hover:bg-surface-gray-1'">
                <td class="px-4 py-2 font-medium text-ink-gray-8">
                  {{ month.month_name }}
                  <Badge v-if="month.month_name === purchasePatternsData.monthly?.peak_month" theme="gray" variant="subtle" label="Peak" size="sm" class="ml-2" />
                </td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ formatNumber(month.order_count as number) }}</td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ money(month.total_revenue as number) }}</td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ money(month.gross_profit as number) }}</td>
                <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ money(month.avg_order_value as number) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="p-6 bg-surface-white rounded-lg border border-outline-gray-1">
        <SectionHeader variant="caption" title="Seasonal Patterns" :level="3" />
        <div class="grid gap-4 lg:grid-cols-4 mt-4">
          <div v-for="season in (purchasePatternsData.seasonal?.data as Record<string, unknown>[])" :key="season.quarter as string"
            :class="[
              'p-4 rounded-lg border',
              season.quarter === purchasePatternsData.seasonal?.peak_quarter
                ? 'border-outline-gray-2 bg-surface-gray-2'
                : 'border-outline-gray-1 bg-surface-white'
            ]">
            <p class="text-sm font-medium text-ink-gray-7">{{ season.quarter }}</p>
            <p class="text-xl font-bold text-ink-gray-9">{{ money(season.total_revenue as number) }}</p>
            <p class="text-sm text-ink-gray-6">{{ formatNumber(season.order_count as number) }} orders</p>
            <p class="text-sm text-ink-gray-6">Avg: {{ money(season.avg_order_value as number) }}</p>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="text-center py-12">
      <Activity class="w-12 h-12 mx-auto text-ink-gray-4" aria-hidden="true" />
      <p class="mt-4 text-ink-gray-6">No purchase pattern data available</p>
    </div>
    <TabActions class="mt-6" :actions="patternsBrief?.actions" />
  </div>

  <!-- ═══ Rankings ═══ -->
  <div v-if="activeTab === 'cust-rankings'" class="p-6 space-y-4">
    <TabBrief :brief="tabBriefs['cust-rankings']" />
    <!-- Category filters -->
    <div class="flex flex-wrap items-center gap-3 p-4 bg-surface-white rounded-lg border border-outline-gray-1">
      <div class="flex-1 min-w-[200px]">
        <FormControl v-model="rankSearch" type="text" :debounce="300"
          placeholder="Search by name or ID..." aria-label="Search customers">
          <template #prefix><Search class="w-4 h-4 text-ink-gray-5" aria-hidden="true" /></template>
        </FormControl>
      </div>
      <Filter class="w-4 h-4 text-ink-gray-5" aria-hidden="true" />
      <Select v-model="rankTier" :options="tierFilterOptions" aria-label="Filter by tier" class="text-sm" />
      <Select v-model="rankSegment" :options="rfmSegmentFilterOptions" aria-label="Filter by segment" class="text-sm" />
      <Select v-model="rankRisk" :options="riskFilterOptions" aria-label="Filter by risk level" class="text-sm" />
    </div>
    <!-- Numeric thresholds -->
    <div class="flex flex-wrap items-end gap-3 p-4 bg-surface-white rounded-lg border border-outline-gray-1">
      <label class="text-xs text-ink-gray-6">Min Revenue
        <FormControl v-model="minRevenue" type="number" placeholder="0" aria-label="Minimum revenue" class="mt-1 w-32" />
      </label>
      <label class="text-xs text-ink-gray-6">Min Gross Profit
        <FormControl v-model="minGrossProfit" type="number" placeholder="0" aria-label="Minimum gross profit" class="mt-1 w-32" />
      </label>
      <label class="text-xs text-ink-gray-6">Min Margin %
        <FormControl v-model="minMargin" type="number" placeholder="0" aria-label="Minimum margin percent" class="mt-1 w-24" />
      </label>
      <label class="text-xs text-ink-gray-6">Min Months Active
        <FormControl v-model="minMonths" type="number" placeholder="0" aria-label="Minimum months active" class="mt-1 w-24" />
      </label>
      <label class="text-xs text-ink-gray-6">Min Consistency %
        <FormControl v-model="minScore" type="number" placeholder="0" aria-label="Minimum consistency score" class="mt-1 w-24" />
      </label>
      <Button variant="outline" label="Clear filters" @click="clearRankFilters" />
    </div>

    <div v-if="isLoadingRankings && !scorecard" class="text-center py-12">
      <Activity class="w-12 h-12 mx-auto text-ink-gray-4 animate-pulse" aria-hidden="true" />
      <p class="mt-4 text-ink-gray-6">Loading customer scorecard…</p>
    </div>

    <div v-else class="overflow-hidden bg-surface-white rounded-lg border border-outline-gray-1">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <caption class="sr-only">Customer scorecard with revenue, gross profit, margin, months active and consistency. Click a metric header to sort, or a row to drill into that customer's orders.</caption>
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-3 text-left font-medium text-ink-gray-6">Customer</th>
              <th scope="col" class="px-4 py-3 text-left font-medium text-ink-gray-6">Tier</th>
              <th scope="col" class="px-4 py-3 text-left font-medium text-ink-gray-6">Segment</th>
              <th scope="col" class="px-4 py-3 text-left font-medium text-ink-gray-6">Risk</th>
              <th v-for="col in sortableCols" :key="col.key" scope="col" tabindex="0" role="button"
                class="px-4 py-3 text-right font-medium text-ink-gray-6 cursor-pointer select-none hover:text-ink-gray-8"
                :aria-sort="rankSort === col.key ? (rankDir === 'asc' ? 'ascending' : 'descending') : 'none'"
                @click="setRankSort(col.key)" @keydown.enter="setRankSort(col.key)" @keydown.space.prevent="setRankSort(col.key)">
                <span class="inline-flex items-center gap-1 justify-end">
                  {{ col.label }}
                  <ChevronRight v-if="rankSort === col.key" class="w-3 h-3"
                    :class="rankDir === 'asc' ? '-rotate-90' : 'rotate-90'" aria-hidden="true" />
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in scorecardRows.slice(0, 200)" :key="c.customer"
              class="border-b border-outline-gray-1 last:border-0 cursor-pointer hover:bg-surface-gray-1 transition-colors motion-reduce:transition-none"
              tabindex="0" role="button"
              @click="drillCustomerOrders(c)"
              @keydown.enter="drillCustomerOrders(c)"
              @keydown.space.prevent="drillCustomerOrders(c)">
              <td class="px-4 py-2 text-ink-gray-8">{{ c.customer_name }}</td>
              <td class="px-4 py-2">
                <Badge v-if="c.clv_tier" theme="gray" variant="subtle" :label="c.clv_tier" size="sm" />
                <span v-else class="text-ink-gray-4">—</span>
              </td>
              <td class="px-4 py-2 text-ink-gray-7">{{ c.rfm_segment || '—' }}</td>
              <td class="px-4 py-2">
                <Badge v-if="c.churn_risk" v-bind="severityBadge(churnSeverity(c.churn_risk))" :label="c.churn_risk" size="sm" />
                <span v-else class="text-ink-gray-4">—</span>
              </td>
              <td class="px-4 py-2 text-right tnum font-medium text-ink-gray-9">{{ money(c.revenue) }}</td>
              <td class="px-4 py-2 text-right tnum font-medium" :class="deltaInk(c.gross_profit)">{{ money(c.gross_profit) }}</td>
              <td class="px-4 py-2 text-right tnum" :class="deltaInk(c.margin_pct)">{{ formatPercent(c.margin_pct) }}</td>
              <td class="px-4 py-2 text-right tnum text-ink-gray-7">{{ c.months_active }}/{{ c.total_months }}</td>
              <td class="px-4 py-2 text-right tnum text-ink-gray-9">{{ c.consistency_score == null ? NO_VALUE : formatPercent(c.consistency_score * 100) }}</td>
              <td class="px-4 py-2 text-right">
                <Badge v-if="c.health_score != null" v-bind="severityBadge(healthSeverity(c.health_status))" :label="String(Math.round(c.health_score))" size="sm" />
                <span v-else class="text-ink-gray-4">—</span>
              </td>
            </tr>
            <tr v-if="!scorecardRows.length">
              <td colspan="10" class="px-4 py-12 text-center text-ink-gray-6">No customers match these filters.</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="px-4 py-3 text-xs text-center text-ink-gray-6 bg-surface-gray-1">
        Showing {{ Math.min(scorecardRows.length, 200) }} of {{ scorecardRows.length }} filtered
        <span v-if="scorecard">({{ scorecard.customers.length }} customers total)</span>
      </div>
    </div>
    <TabActions class="mt-6" :actions="tabBriefs['cust-rankings']?.actions" />
  </div>
</template>
