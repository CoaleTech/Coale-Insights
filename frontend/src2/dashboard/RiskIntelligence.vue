<script setup lang="ts">
defineOptions({ name: 'RiskIntelligence' })
import { ref, computed } from 'vue'
import { Badge, Button, ListView, Tabs } from 'frappe-ui'
import { useRouter } from 'vue-router'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'
import { useIntelligenceDashboard } from '../intelligence/composables/useIntelligenceDashboard'
import KpiCard from '../intelligence/components/KpiCard.vue'
import IntelligenceDashboardShell from '../intelligence/components/IntelligenceDashboardShell.vue'
import LedgerAnomalies from '../intelligence/components/LedgerAnomalies.vue'
import SectionHeader from '../intelligence/components/SectionHeader.vue'
import IntelligenceChart from '../intelligence/components/IntelligenceChart.vue'
import { themeColor } from '../utils/chartTheme'
import {
  severityBadge, severityFill, severityAria, scoreSeverity, normaliseSeverity, type Severity,
} from '../utils/status'
import { formatCount, formatDate, formatDateTime, formatMoney, NO_VALUE } from '../utils/format'

const router = useRouter()
const drillDown = useDrillDown()
const RISK_ENDPOINT = 'insights.api.ml.risk.get_risk_detail'

// Minimal shapes that keep templates type-safe without casts
interface RiskAlert {
  severity: string
  title: string
  description: string
  action: string
  /** Alert class, e.g. `credit_risk`. Decides whether rows exist behind it. */
  type?: string
  /** Present on credit alerts: the drill key, with its matching cut-off. */
  customer?: string
  overdue_days?: number
  /**
   * The figure already inside `description`, as a number. Null where the item
   * has no money dimension (a stock-out count), so the queue can right-align
   * money without parsing its own formatted prose.
   */
  amount?: number | null
}
interface RiskComponent { score: number; category: string }
interface RiskComponents { credit_risk?: RiskComponent; cashflow_risk?: RiskComponent; operational_risk?: RiskComponent; compliance_risk?: RiskComponent }

/** Risk assessment matrix row. */
interface RiskMatrixRow { name: string; category?: string; probability: number; impact: number; risk_score?: number; risk_category?: string }
/** Receivables aging bucket. */
interface AgingBucket { aging_bucket: string; outstanding_amount?: number; invoice_count?: number }
/** Customer credit risk score row. */
interface CustomerRiskScore { customer: string; customer_name?: string; outstanding?: number; avg_overdue_days?: number; risk_category?: string; risk_score?: number }
/** Supplier credit risk score row (payables side). */
interface SupplierRiskScore { supplier: string; supplier_name?: string; outstanding?: number; avg_overdue_days?: number; risk_category?: string; risk_score?: number }
/** Revenue concentration customer row. */
interface ConcentrationCustomer { customer: string; customer_name?: string; revenue?: number; revenue_share: number }
/** Overdue days trend period row. */
interface DSOPeriod { period: string; avg_days_overdue?: number }
/** Inventory risk by item group row. */
interface InventoryRiskRow { item_group: string; total_items?: number; stockout_items: number; stock_value?: number; risk_category?: string }
/** Supplier reliability row from operational risk. */
interface SupplierReliabilityRow { supplier: string; supplier_name?: string; total_orders?: number; total_value?: number; avg_delay_days?: number; risk_category?: string }
/** GST compliance status block (GSTR-1/GSTR-3B filing, e-Invoice coverage). */
interface GstStatus {
  gstr1_status?: string; gstr1_latest_period?: string
  gstr3b_status?: string; gstr3b_latest_period?: string
  einvoice_coverage_pct?: number | null; einvoice_pending_value?: number
}
/** Document completeness audit row. */
interface DocumentAuditRow { document_type: string; total_docs: number; incomplete_docs: number }
/** GST/PAN registration row. */
interface LicenseRow { license_type: string; reference?: string; status?: string; risk_level?: string }
/** Financial anomaly row. */
interface AnomalyRow { type: string; description?: string; date?: string; severity?: string; amount?: number | null }
/** Early warning alert row. */
interface EarlyWarningRow { title?: string; description?: string; timeframe?: string; severity?: string; amount?: number | null }
/** High-risk payment customer row. */
interface PaymentRiskCustomer { customer: string; avg_delay_days: number; risk_category?: string; risk_score?: number }

/** Typed overview sub-section. */
interface OverviewSection {
  alerts?: RiskAlert[]
  risk_matrix?: RiskMatrixRow[]
  risk_components?: RiskComponents
  aggregate_risk_score?: number
  aggregate_risk_category?: string
  total_customers?: number
  total_suppliers?: number
  total_items?: number
}
/** Typed credit risk sub-section. */
interface CreditSection {
  total_outstanding?: number
  high_risk_customers?: number
  avg_days_overdue?: number
  aging_analysis?: AgingBucket[]
  customer_risk_scores?: CustomerRiskScore[]
}
/** Typed payables risk sub-section (AP mirror of CreditSection). */
interface PayablesSection {
  total_outstanding?: number
  high_risk_suppliers?: number
  avg_days_overdue?: number
  aging_analysis?: AgingBucket[]
  supplier_risk_scores?: SupplierRiskScore[]
}
/** One month-end GL balance pair from `_exposure_trend`. */
interface ExposurePeriod {
  period: string
  receivables: number
  payables: number
}
/** Typed cashflow risk sub-section. */
interface CashflowSection {
  current_cash_position?: number
  current_working_capital?: number
  working_capital_ratio?: number
  top_customer_share?: number
  customer_concentration?: ConcentrationCustomer[]
  overdue_days_trend?: DSOPeriod[]
  exposure_trend?: ExposurePeriod[]
}
/** Typed operational risk sub-section. */
interface OperationalSection {
  process_risks?: Record<string, number | undefined>
  inventory_risks?: InventoryRiskRow[]
  supplier_performance?: SupplierReliabilityRow[]
}
/** Typed compliance risk sub-section. */
interface ComplianceSection {
  gst_status?: GstStatus
  document_audit?: DocumentAuditRow[]
  licenses?: LicenseRow[]
}
/** Typed predictive analytics sub-section. */
interface PredictiveSection {
  cash_flow_forecast?: { status?: string }
  revenue_forecast?: { status?: string }
  anomalies?: AnomalyRow[]
  early_warnings?: EarlyWarningRow[]
  payment_risk_forecast?: { high_risk_customers?: PaymentRiskCustomer[] }
}

interface RiskIntelligenceData {
  overview: OverviewSection
  credit_risk: CreditSection
  payables_risk: PayablesSection
  cashflow_risk: CashflowSection
  operational_risk: OperationalSection
  compliance_risk: ComplianceSection
  predictive_analytics: PredictiveSection
  generated_at?: string
  base_currency?: string
}

const {
  data: riskData,
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
} = useIntelligenceDashboard<RiskIntelligenceData>({
  url: 'insights.api.ml.risk_intelligence',
  cache: 'risk-intelligence',
})

const overviewData = computed(() => riskData.value?.overview ?? ({} as OverviewSection))
const creditData = computed(() => riskData.value?.credit_risk ?? ({} as CreditSection))
const payablesData = computed(() => riskData.value?.payables_risk ?? ({} as PayablesSection))
const cashflowData = computed(() => riskData.value?.cashflow_risk ?? ({} as CashflowSection))
const operationalData = computed(() => riskData.value?.operational_risk ?? ({} as OperationalSection))
const complianceData = computed(() => riskData.value?.compliance_risk ?? ({} as ComplianceSection))
const predictiveData = computed(() => riskData.value?.predictive_analytics ?? ({} as PredictiveSection))
// No ISO fallback: this site reports in neither KES nor INR, and a constant
// relabels every figure on the page. `formatMoney` renders the number bare
// when the code is empty, which is honest; a wrong code is not.
const baseCurrency = computed(() => riskData.value?.base_currency ?? '')
const lastUpdated = computed(() => riskData.value?.generated_at ?? null)

// Tabs - numeric index for frappe-ui Tabs component
const tabDefs = [
  { label: 'Overview', value: 'overview' },
  { label: 'Credit Risk', value: 'credit' },
  { label: 'Payables Risk', value: 'payables' },
  { label: 'Cash Flow Risk', value: 'cashflow' },
  { label: 'Operational Risk', value: 'operational' },
  { label: 'Compliance Risk', value: 'compliance' },
  { label: 'Predictive Analytics', value: 'predictive' },
  { label: 'Ledger Anomalies', value: 'anomalies' },
]
const activeTabIndex = ref(0)
const activeTab = computed(() => tabDefs[activeTabIndex.value]?.value ?? 'overview')
const tabsForComponent = tabDefs.map(t => ({ label: t.label }))

/**
 * Summary derived from the overview sub-object.
 *
 * Every field is nullable on purpose. `|| 0` and `|| 'Low'` used to stand in
 * for a missing score and a missing category, which on a *risk* surface is the
 * one substitution you must never make: a payload that failed to compute
 * credit risk rendered "0/100" with a green "Low" badge -- an all-clear the
 * server never gave. It is also wrong for a real zero: `compliance_risk` does
 * legitimately score 0.0, and `|| 0` made the two indistinguishable. `KpiCard`
 * renders `null` as a dash, and `normaliseSeverity` is only consulted when a
 * category actually arrived.
 */
const summary = computed(() => {
  const overview = overviewData.value
  const components = overview.risk_components ?? {}
  const alerts = overview.alerts ?? []
  const score = (c?: RiskComponent) => (Number.isFinite(c?.score) ? (c as RiskComponent).score : null)
  return {
    overallScore: Number.isFinite(overview.aggregate_risk_score) ? overview.aggregate_risk_score! : null,
    overallRisk: overview.aggregate_risk_category ?? null,
    creditScore: score(components.credit_risk),
    creditRisk: components.credit_risk?.category ?? null,
    cashflowScore: score(components.cashflow_risk),
    cashflowRisk: components.cashflow_risk?.category ?? null,
    operationalScore: score(components.operational_risk),
    operationalRisk: components.operational_risk?.category ?? null,
    complianceScore: score(components.compliance_risk),
    complianceRisk: components.compliance_risk?.category ?? null,
    activeAlerts: alerts.length,
    criticalAlerts: alerts.filter(a => a.severity === 'critical').length,
  }
})

/**
 * The four components as rows, so "Risk Component Breakdown" iterates instead
 * of repeating a 17-line block four times. The copies had already drifted --
 * each one re-derived `normaliseSeverity(...)` three times per row -- and a
 * fifth component would have meant a fifth copy.
 */
const riskComponentRows = computed(() => [
  // Weights mirror `WEIGHTS` in `insights/ml/risk_intelligence.py`. They are a
  // fixed policy constant, not part of the payload, so they are stated here
  // rather than faked as data.
  { label: 'Credit Risk', weight: 0.3, score: summary.value.creditScore, category: summary.value.creditRisk },
  { label: 'Cash Flow Risk', weight: 0.3, score: summary.value.cashflowScore, category: summary.value.cashflowRisk },
  { label: 'Operational Risk', weight: 0.25, score: summary.value.operationalScore, category: summary.value.operationalRisk },
  { label: 'Compliance Risk', weight: 0.15, score: summary.value.complianceScore, category: summary.value.complianceRisk },
].map(r => ({
  ...r,
  severity: r.category ? normaliseSeverity(r.category) : ('none' as Severity),
  // A missing score draws no bar at all rather than a zero-length one that
  // reads as "measured, and fine".
  width: r.score === null ? null : `${Math.min(100, Math.max(0, r.score))}%`,
  display: r.score === null ? NO_VALUE : `${r.score}/100`,
})))

const exposureTrend = computed(() => cashflowData.value.exposure_trend ?? [])

/**
 * Both series are money in the same currency, so they share one axis --
 * splitting them across y and y2 would let two different scales imply a
 * crossover that never happened (IBCS unified scaling).
 */
const exposureTrendConfig = computed(() => ({
  title: '',
  data: exposureTrend.value.map(r => ({
    period: r.period,
    Receivables: r.receivables,
    Payables: r.payables,
  })),
  xAxis: { key: 'period', type: 'category' as const },
  yAxis: { title: baseCurrency.value },
  series: [
    { name: 'Receivables', type: 'line' as const, color: themeColor('--app-accent-strong'), axis: 'y' as const, showDataPoints: true },
    { name: 'Payables', type: 'line' as const, color: themeColor('--app-muted-fill'), axis: 'y' as const, showDataPoints: true },
  ],
}))

/**
 * States the actual move over the window instead of leaving the reader to
 * eyeball two endpoints. Direction words only -- no percentage, because a
 * balance that starts near zero makes the percentage meaningless.
 *
 * The basis is named because the last point does not equal the receivables
 * tile above it: this is the general-ledger balance through month end, while
 * the tile is invoice outstanding, which includes future-dated invoices this
 * ledger carries. Both are right; unlabelled, they look like a bug.
 */
const exposureTrendHint = computed(() => {
  const basis = 'Month-end ledger balance'
  const rows = exposureTrend.value
  if (rows.length < 2) return basis
  const first = rows[0]
  const last = rows[rows.length - 1]
  const move = last.receivables - first.receivables
  const word = move > 0 ? 'up' : move < 0 ? 'down' : 'flat'
  if (!move) return `${basis} · receivables flat since ${first.period}`
  return `${basis} · receivables ${word} ${formatMoney(Math.abs(move), baseCurrency.value)} since ${first.period}`
})

/**
 * The two matrix axes, iterated so the identical bar cell is written once.
 *
 * `graded` marks the axis that is a live measurement: probability is this
 * period's computed score, impact is a constant severity weight assigned per
 * category in `_risk_matrix`. Colouring the latter by magnitude claimed a
 * fixed judgment was a bad reading.
 */
const matrixAxes = [
  { key: 'probability', label: 'Probability', graded: true },
  { key: 'impact', label: 'Impact', graded: false },
] as const

/**
 * Overdue money and its invoice count, from the aging buckets.
 *
 * Read off the buckets rather than `total_outstanding` so the headline and the
 * tiles on the Credit/Payables tabs cannot disagree, and so "overdue" means the
 * four past-due buckets rather than the whole open book -- most of which is not
 * yet due and is not a risk figure.
 */
function overdueFrom(buckets?: AgingBucket[]) {
  const rows = buckets ?? []
  if (!rows.length) return { amount: null, count: null, open: null }
  const late = rows.filter(b => b.aging_bucket !== 'Current')
  const sum = (bs: AgingBucket[], k: 'outstanding_amount' | 'invoice_count') =>
    bs.reduce((acc, b) => acc + (b[k] ?? 0), 0)
  return {
    amount: sum(late, 'outstanding_amount'),
    count: sum(late, 'invoice_count'),
    open: sum(rows, 'outstanding_amount'),
  }
}
const overdueReceivables = computed(() => overdueFrom(creditData.value.aging_analysis))
const overduePayables = computed(() => overdueFrom(payablesData.value.aging_analysis))

/**
 * Which component contributes most to the overall score, and how much of it.
 *
 * Arithmetic on figures already in the payload (`score x weight / aggregate`),
 * not a new claim: it names what the reader would otherwise have to compute
 * from the four bars further down the page. Cash flow at 70.8 x 0.30 is 21.2
 * of the 40.0 total here -- over half the score from one component.
 */
const riskDriver = computed(() => {
  const total = summary.value.overallScore
  const rows = riskComponentRows.value.filter(r => r.score !== null)
  if (!total || !rows.length) return null
  const top = rows.reduce((a, b) => (b.score! * b.weight > a.score! * a.weight ? b : a))
  const share = Math.round(((top.score! * top.weight) / total) * 100)
  return `${top.label.replace(/ Risk$/, '')} drives ${share}% of it`
})

/** Worst first. Anything the server did not classify sorts last. */
const SEVERITY_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 }

/**
 * One queue from the three lists the server computes separately: `alerts`
 * (observed, from `_top_alerts`), `early_warnings` (forecast) and `anomalies`
 * (a flagged posting).
 *
 * They were three sections in two different tabs, all answering "what should I
 * do now", so a reader had to merge them by hand and no ordering existed across
 * them. `kind` stays visible because a forecast is not an observation and the
 * distinction decides whether you act or verify first. No `action` is invented
 * for the two sources that do not carry one.
 */
const actionQueue = computed(() => {
  const items = [
    ...(overviewData.value.alerts ?? []).map(a => ({
      kind: 'Observed',
      severity: a.severity,
      title: a.title,
      detail: a.description,
      action: a.action,
      context: null as string | null,
      amount: a.amount ?? null,
      customer: a.customer,
      overdueDays: a.overdue_days,
    })),
    ...(predictiveData.value.early_warnings ?? []).map(w => ({
      kind: 'Forecast',
      severity: w.severity ?? '',
      title: w.title ?? 'Early warning',
      detail: w.description ?? '',
      action: null as string | null,
      context: w.timeframe ?? null,
      amount: w.amount ?? null,
      customer: undefined as string | undefined,
      overdueDays: undefined as number | undefined,
    })),
    ...(predictiveData.value.anomalies ?? []).map(an => ({
      kind: 'Anomaly',
      severity: an.severity ?? '',
      title: an.type.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase()),
      detail: an.description ?? '',
      action: null as string | null,
      context: an.date ? formatDate(an.date) : null,
      amount: an.amount ?? null,
      customer: undefined as string | undefined,
      overdueDays: undefined as number | undefined,
    })),
  ]
  // Stable within a severity: the server already orders credit alerts by money.
  return items
    .map((item, i) => ({ item, i }))
    .sort(
      (a, b) =>
        (SEVERITY_RANK[a.item.severity] ?? 9) - (SEVERITY_RANK[b.item.severity] ?? 9) || a.i - b.i,
    )
    // `ListView` needs a stable per-row key and none of the three sources
    // carries an id, so position in the ranked queue is the key.
    .map(({ item }, rank) => ({ ...item, key: `q${rank}` }))
})

/** One ranked queue row, as `actionQueue` emits it. */
type QueueItem = (typeof actionQueue.value)[number]

const queueCritical = computed(() => actionQueue.value.filter(i => i.severity === 'critical').length)

/**
 * Queue columns. Money gets its own right-aligned column because the amounts
 * used to sit inside prose (`Outstanding: ₹ 5,80,922.00`), where nine rows of
 * differently-worded sentences could not be compared at a glance. The server
 * now sends `amount` alongside the sentence, so no string is parsed back into
 * a number here.
 */
const queueColumns = [
  { label: 'Severity', key: 'severity', width: 0.8 },
  { label: 'Item', key: 'title', width: 2.2 },
  { label: 'Basis', key: 'kind', width: 0.9 },
  {
    label: 'Detail',
    key: 'detail',
    width: 2.4,
    getLabel: ({ row }: { row: QueueItem }) =>
      row.context ? `${row.detail} · ${row.context}` : row.detail,
  },
  {
    label: 'Amount',
    key: 'amount',
    width: 1.2,
    align: 'right',
    // `NO_VALUE`, not a zero: a stock-out count and a seasonal window have no
    // amount, and printing 0 would read as "measured, and nil".
    getLabel: ({ row }: { row: QueueItem }) =>
      row.amount === null ? NO_VALUE : formatMoney(row.amount, baseCurrency.value),
  },
  {
    label: 'Next step',
    key: 'action',
    width: 2.2,
    // Only the observed alerts carry one; nothing is invented for the rest.
    getLabel: ({ row }: { row: QueueItem }) => row.action ?? NO_VALUE,
  },
  { label: '', key: 'drill', width: 0.9, align: 'right' },
]

/**
 * The Predictive tab's two lists, as `ListView` rows. Neither source carries an
 * id, so rank is the key -- the same reason `actionQueue` derives one.
 *
 * These are the same three sources the Overview queue merges. They stay on this
 * tab because the queue shows only what outranks everything else on the page,
 * while this tab is the full detector output: 20 anomalies, not the worst one.
 */
const anomalyRows = computed(() =>
  (predictiveData.value.anomalies ?? []).map((a, i) => ({ ...a, key: `a${i}` })),
)

const anomalyColumns = [
  { label: 'Severity', key: 'severity', width: 0.9 },
  {
    label: 'Type',
    key: 'type',
    width: 1.6,
    getLabel: ({ row }: { row: { type: string } }) =>
      row.type.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase()),
  },
  {
    label: 'What was flagged',
    key: 'description',
    width: 3.4,
    getLabel: ({ row }: { row: { description?: string } }) => row.description ?? NO_VALUE,
  },
  {
    label: 'Date',
    key: 'date',
    width: 1.2,
    // The raw payload date is ISO; every other date on this page is formatted.
    getLabel: ({ row }: { row: { date?: string } }) =>
      row.date ? formatDate(row.date) : NO_VALUE,
  },
]

const anomalyListHeight = computed(() => `${(anomalyRows.value.length + 1) * 40 + 12}px`)

const warningRows = computed(() =>
  (predictiveData.value.early_warnings ?? []).map((w, i) => ({ ...w, key: `w${i}` })),
)

const warningColumns = [
  { label: 'Severity', key: 'severity', width: 0.9 },
  {
    label: 'Warning',
    key: 'title',
    width: 1.8,
    getLabel: ({ row }: { row: { title?: string } }) => row.title ?? NO_VALUE,
  },
  {
    label: 'Basis',
    key: 'description',
    width: 3.2,
    getLabel: ({ row }: { row: { description?: string } }) => row.description ?? NO_VALUE,
  },
  {
    label: 'Horizon',
    key: 'timeframe',
    width: 1.2,
    getLabel: ({ row }: { row: { timeframe?: string } }) => row.timeframe ?? NO_VALUE,
  },
]

const warningListHeight = computed(() => `${(warningRows.value.length + 1) * 40 + 12}px`)

/** Header row plus one row per item, so the list never scrolls internally. */
const queueListHeight = computed(() => `${(actionQueue.value.length + 1) * 40 + 12}px`)

/**
 * Opens the invoices behind a queue row. Only the credit alerts have rows: a
 * cash-position warning and an expense anomaly are derived from balances and a
 * posting, not from a filterable list, so those rows stay inert instead of
 * opening an empty dialog. `overdueDays` travels with the figure so the
 * dialog's total reconciles with the outstanding amount quoted in the row.
 */
function openQueueDrill(item: { title: string; customer?: string; overdueDays?: number }) {
  if (!item.customer) return
  drillDown.open(RISK_ENDPOINT, item.title, {
    metric: 'overdue_invoices',
    customer: item.customer,
    overdue_days: item.overdueDays ?? 60,
  })
}

// Risk score: higher = worse, so higherIsBetter: false. Scoped to the risk
// matrix's Probability/Impact bars only, which have no server-computed
// category of their own. The four risk *components* and the overall score
// each carry an authoritative category from the backend's `_risk_category()`
// (Low <=25, Medium <=50, High <=75, Critical >75) -- use
// `normaliseSeverity(summary.xRisk)` for those instead of recomputing a
// second, differently-thresholded classification here. That divergence used
// to show a KPI card as "High" while the identical score's category badge
// lower on the same page said "Medium" (e.g. Credit Risk at 43.5/100).
function riskScoreSeverity(score: number): Severity {
  return scoreSeverity(score, { good: 20, warn: 40, higherIsBetter: false })
}

// GST filing status vocabulary from `get_filing_compliance` (server):
// No Data | Not Due | Compliant | Overdue. `Pending` / `Not Tracked` are the
// pre-due-date-aware spellings, still served from cached payloads.
function gstStatusSeverity(status: string | undefined): Severity {
  if (status === 'Compliant' || status === 'Not Due') return 'none'
  if (status === 'Overdue' || status === 'Pending') return 'high'
  if (status === 'Not Tracked' || status === 'No Data' || status === 'Not Available') return 'medium'
  // An unrecognised status is an unread signal, never an all-clear: a silent
  // green fallthrough is how `Overdue` would have rendered as no risk.
  return 'medium'
}

const chatContext = computed(() => ({
  summary: summary.value,
  overview: overviewData.value,
  creditRisk: creditData.value,
  cashflowRisk: cashflowData.value,
  operationalRisk: operationalData.value,
  complianceRisk: complianceData.value,
  predictiveAnalytics: predictiveData.value,
  activeTab: activeTab.value,
  lastUpdated: lastUpdated.value,
}))

function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    Sales: '/sales-intelligence',
    Inventory: '/inventory-intelligence',
    Procurement: '/procurement-intelligence',
    Financial: '/financial-intelligence',
    Customer: '/customer-intelligence',
    Risk: '/risk-intelligence',
  }
  if (routes[target]) router.push(routes[target])
}

const formatCurrency = (value: number | null | undefined) => formatMoney(value, baseCurrency.value)


</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <header class="bg-surface-white border-b border-outline-gray-1 px-6 py-4 flex flex-col flex-wrap items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-ink-gray-9">Risk Intelligence & Analytics</h1>
        <!--
          The three ledger counts live here, not in a card grid. They never move
          and none of them is a KPI: they are the denominators the scores below
          are computed over, which is context for the page, not content on it.
        -->
        <p v-if="hasData" class="text-sm text-ink-gray-6 mt-1">
          Across {{ formatCount(overviewData.total_customers) }} customers &middot;
          {{ formatCount(overviewData.total_suppliers) }} suppliers &middot;
          {{ formatCount(overviewData.total_items) }} stock items
        </p>
        <p v-if="lastUpdated" class="text-sm text-ink-gray-6">
          Updated: {{ formatDateTime(lastUpdated) }}
        </p>
      </div>
      <Button
        variant="solid"
        theme="gray"
        :loading="refreshing"
        icon-left="refresh-cw"
        @click="reload"
      >
        Refresh Analysis
      </Button>
    </header>


    <IntelligenceDashboardShell
      :loading="loading"
      :refreshing="refreshing"
      :error="error"
      :is-permission-error="isPermissionError"
      :warming="warming"
      :not-implemented="notImplemented"
      :not-implemented-message="notImplementedMessage"
      :has-data="hasData"
      subject="risk data"
      permission-hint="Ask an administrator for risk read access."
      @retry="retry"
    >
      <!--
        Four cards, not six, and three of them are money.

        The strip used to be the overall score plus its own four components plus
        an alert count: six widths spent on one metric family, repeating the
        four scores that the weighted breakdown further down already shows, and
        answering "what are my indices" rather than "what is at stake". An index
        is the summary of an exposure, not a substitute for it -- so the overall
        score stays (with its dominant driver named) and the other three slots
        carry the exposures it summarises: money late in, cash on hand, money
        late out. Each opens its own rows.

        The shell renders this slot only when `hasData` and never while
        `loading`, so no card needs a `hasData`/`:loading` guard.
      -->
      <div class="p-6 grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Overall Risk Score"
          :value="summary.overallScore"
          unit="/100"
          :sublabel="riskDriver ?? undefined"
          :severity="summary.overallRisk ? normaliseSeverity(summary.overallRisk) : undefined"
        />
        <KpiCard
          label="Overdue receivables"
          :amount="overdueReceivables.amount"
          :currency="baseCurrency"
          :sublabel="`${formatCount(overdueReceivables.count)} invoices of ${formatMoney(overdueReceivables.open, baseCurrency, { compact: true })} open`"
          :severity="summary.creditRisk ? normaliseSeverity(summary.creditRisk) : undefined"
          clickable
          @click="drillDown.open(RISK_ENDPOINT, 'Overdue Invoices', { metric: 'overdue_invoices' })"
        />
        <!--
          Cash is the one figure here that can be negative, and the sign is the
          whole message, so it is graded by sign rather than by a score: the
          server's cashflow category already covers the trend this sits inside.
        -->
        <KpiCard
          label="Cash position"
          :amount="cashflowData.current_cash_position"
          :currency="baseCurrency"
          :sublabel="cashflowData.working_capital_ratio == null ? undefined : `Working capital ratio ${cashflowData.working_capital_ratio}`"
          :severity="cashflowData.current_cash_position == null ? undefined : cashflowData.current_cash_position < 0 ? 'critical' : 'low'"
        />
        <KpiCard
          label="Overdue payables"
          :amount="overduePayables.amount"
          :currency="baseCurrency"
          :sublabel="`${formatCount(overduePayables.count)} bills of ${formatMoney(overduePayables.open, baseCurrency, { compact: true })} open`"
          clickable
          @click="drillDown.open(RISK_ENDPOINT, 'Overdue Payables', { metric: 'overdue_payables' })"
        />
      </div>

      <!-- Tabs -->
      <div class="bg-surface-white border-b border-outline-gray-1 mx-6 rounded-t-lg">
        <Tabs v-model="activeTabIndex" :tabs="tabsForComponent" />
      </div>

      <!-- Tab Content -->
      <div class="flex-1 p-6 overflow-auto">
        <!-- Tab 1: Overview -->
        <div v-if="activeTab === 'overview'" class="space-y-6">
          <!--
            The overall score in the strip above is a *weighted* blend of these
            four (credit .30, cashflow .30, operational .25, compliance .15 --
            `WEIGHTS` in `risk_intelligence.py`). Nothing on the page said so,
            which left "Overall 40/100" impossible to reconcile with a 70.8
            cash-flow score sitting next to a 0.0 compliance score. The weight
            is shown per row because that is what makes each bar readable.
          -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader
              variant="caption"
              title="Risk Component Breakdown"
              hint="Weighted into the overall score"
              :level="3"
            />
            <div class="mt-4 space-y-4">
              <div v-for="row in riskComponentRows" :key="row.label" class="flex items-center gap-4">
                <div class="w-44 shrink-0 text-sm font-medium text-ink-gray-7">
                  {{ row.label }}
                  <span class="font-normal text-ink-gray-6">&times;{{ row.weight }}</span>
                </div>
                <div
                  class="flex-1 bg-surface-gray-3 rounded-full h-4"
                  :aria-label="severityAria(row.label, row.severity, row.display)"
                  role="img"
                >
                  <div
                    v-if="row.width"
                    :class="[severityFill(row.severity), 'h-4 rounded-full motion-reduce:transition-none transition-all']"
                    :style="{ width: row.width }"
                  />
                </div>
                <div class="w-24 text-right flex items-center gap-2 justify-end">
                  <span class="font-bold text-ink-gray-8">{{ row.display }}</span>
                  <Badge v-if="row.category" v-bind="severityBadge(row.category)" size="sm" />
                </div>
              </div>
            </div>
          </div>

          <!--
            Direction of travel, which the page never showed: the strip says
            exposure is 10.6M today but not whether that is the best or the
            worst it has been. Month-end GL balances, not the invoice-derived
            `overdue_days_trend` sitting on the Cash Flow tab -- that series
            averages `today - due_date` over settled and open invoices alike,
            so it decays ~30 a month by calendar arithmetic, and its
            companion `month_end_outstanding` only measures how recently an
            invoice was raised. Both would draw a confident improving line
            out of an artefact. See `_exposure_trend` for the full reasoning.
          -->
          <div v-if="exposureTrend.length" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader
              variant="caption"
              title="Exposure trend"
              :hint="exposureTrendHint"
              :level="3"
            />
            <IntelligenceChart
              :config="exposureTrendConfig"
              class="mt-3 h-48 sm:h-56 lg:h-64"
            />
          </div>
          <!-- Risk Assessment Matrix Table -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader
              variant="caption"
              title="Risk Assessment Matrix"
              hint="Score = probability &times; impact &divide; 100"
              :level="3"
            />
            <div class="mt-4 overflow-x-auto">
              <table class="w-full">
                <caption class="sr-only">
                  Risk register. Probability is this period's computed score for the
                  category; impact is a fixed severity weight for the event, not a
                  measurement. Both are on a 0-100 scale.
                </caption>
                <thead>
                  <tr class="border-b border-outline-gray-1">
                    <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Risk</th>
                    <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Category</th>
                    <th
                      v-for="axis in matrixAxes"
                      :key="axis.key"
                      scope="col"
                      class="text-center py-2 text-sm font-medium text-ink-gray-7"
                    >
                      {{ axis.label }}
                    </th>
                    <th scope="col" class="text-center py-2 text-sm font-medium text-ink-gray-7">Risk Score</th>
                    <th scope="col" class="text-center py-2 text-sm font-medium text-ink-gray-7">Level</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="risk in overviewData.risk_matrix"
                    :key="risk.name"
                    class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                  >
                    <td class="py-3 font-medium text-ink-gray-8">{{ risk.name }}</td>
                    <td class="py-3 text-ink-gray-6">{{ risk.category }}</td>
                    <!--
                      Both axes are 0-100 scores, so neither carries a `%`: the
                      cells used to render impact as "90%", which reads as a
                      measured likelihood when it is a fixed severity weight.
                      Only probability is graded by severity for the same reason
                      -- a high impact weight is a property of the event, not bad
                      news about this period, so its bar stays neutral.
                    -->
                    <td v-for="axis in matrixAxes" :key="axis.key" class="py-3 text-center">
                      <div class="flex items-center justify-center gap-2">
                        <div
                          class="w-16 bg-surface-gray-3 rounded-full h-2"
                          :aria-label="severityAria(axis.label, axis.graded ? riskScoreSeverity(risk[axis.key]) : 'none', String(risk[axis.key]))"
                          role="img"
                        >
                          <div
                            :class="severityFill(axis.graded ? riskScoreSeverity(risk[axis.key]) : 'none')"
                            class="h-2 rounded-full motion-reduce:transition-none transition-all"
                            :style="{ width: risk[axis.key] + '%' }"
                          />
                        </div>
                        <span class="text-sm text-ink-gray-7 tnum">{{ risk[axis.key] }}</span>
                      </div>
                    </td>
                    <td class="py-3 text-center font-bold text-ink-gray-8 tnum">
                      {{ risk.risk_score?.toFixed(1) ?? NO_VALUE }}
                    </td>
                    <td class="py-3 text-center">
                      <Badge v-bind="severityBadge(risk.risk_category)" size="sm" />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <!--
            One queue, three sources: observed alerts, forecast warnings and
            flagged postings. They were three lists in two tabs, all answering
            "what do I do now", with no ordering across them -- so the reader
            merged them by hand and the critical cash warning sat two tabs away
            from the critical cash alert. `kind` is shown because a forecast is
            not an observation: one you act on, the other you verify.
          -->
          <div v-if="actionQueue.length" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader
              variant="caption"
              title="Act on this"
              :hint="`${queueCritical} critical of ${actionQueue.length}`"
              :level="3"
            />
            <!--
              Height is computed rather than a `h-*` class: `ListView` scrolls
              its own body, so a fixed class either clips the queue or leaves
              dead space, and a scrollbar inside a scrolling tab is two
              scrollbars for nine rows.
            -->
            <ListView
              class="mt-4 list-ink-fix"
              :style="{ height: queueListHeight }"
              :columns="queueColumns"
              :rows="actionQueue"
              row-key="key"
              :options="{ selectable: false, showTooltip: true, rowHeight: 40 }"
            >
              <template #cell="{ column, row, item }">
                <Badge
                  v-if="column.key === 'severity' && row.severity"
                  v-bind="severityBadge(row.severity)"
                  size="sm"
                />
                <!--
                  The drill is a button per row, not `options.onRowClick`:
                  `ListRow` marks every row `cursor-pointer` as soon as a click
                  handler exists, and only the credit alerts have invoices
                  behind them. Four of nine rows would promise a dialog that
                  cannot open.
                -->
                <Button
                  v-else-if="column.key === 'drill' && row.customer"
                  variant="subtle"
                  size="sm"
                  label="Invoices"
                  @click.stop="openQueueDrill(row)"
                />
                <span v-else class="truncate">{{ column.getLabel ? column.getLabel({ row }) : item }}</span>
              </template>
            </ListView>
          </div>

        </div>

        <!-- Tab 2: Credit Risk -->
        <div v-if="activeTab === 'credit'" class="space-y-6">
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <KpiCard
              label="Total Outstanding"
              :value="formatCurrency(creditData.total_outstanding as number)"
              :clickable="true"
              @click="drillDown.open(RISK_ENDPOINT, 'Overdue Invoices', { metric: 'overdue_invoices' })"
            />
            <KpiCard
              label="High Risk Customers"
              :value="creditData.high_risk_customers"
              :severity="(creditData.high_risk_customers as number) > 0 ? 'high' : undefined"
            />
            <KpiCard
              label="Avg Days Overdue"
              :value="creditData.avg_days_overdue == null ? undefined : Math.round(creditData.avg_days_overdue as number)"
              unit=" days"
              :severity="scoreSeverity(creditData.avg_days_overdue as number, { good: 30, warn: 60, higherIsBetter: false })"
            />
          </div>

          <!-- Aging Analysis -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Receivables Aging Analysis" :level="3" />
            <div class="mt-4">
              <div class="grid grid-cols-5 gap-4">
                <KpiCard
                  v-for="bucket in creditData.aging_analysis"
                  :key="bucket.aging_bucket"
                  :label="bucket.aging_bucket"
                  :amount="bucket.outstanding_amount"
                  :currency="baseCurrency"
                  :sublabel="`${bucket.invoice_count} invoices`"
                  variant="tile"
                  clickable
                  @click="drillDown.open(RISK_ENDPOINT, bucket.aging_bucket + ' Overdue', { metric: 'overdue_invoices', aging_bucket: bucket.aging_bucket })"
                />
              </div>
            </div>
          </div>

          <!-- Customer Risk Scores -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
          <SectionHeader variant="caption" title="Customer Risk Scores" hint="Payment behaviour and default probability" :level="3" />
          <div class="mt-4">
            <div class="overflow-x-auto">
                <table class="w-full">
                  <thead>
                    <tr class="border-b border-outline-gray-1">
                      <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Customer</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Outstanding</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Avg Overdue Days</th>
                      <th scope="col" class="text-center py-2 text-sm font-medium text-ink-gray-7">Risk Category</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Risk Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="customer in creditData.customer_risk_scores?.slice(0, 20)"
                      :key="customer.customer"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                    >
                      <td class="py-2 text-ink-gray-8">{{ customer.customer_name }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ formatCurrency(customer.outstanding) }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ Math.round(customer.avg_overdue_days || 0) }}</td>
                      <td class="py-2 text-center">
                        <Badge v-bind="severityBadge(customer.risk_category)" size="sm" />
                      </td>
                      <td class="py-2 text-right font-medium text-ink-gray-8">{{ customer.risk_score }}/100</td>
                    </tr>
                  </tbody>
                </table>
              </div>
          </div>
        </div>
        </div>

        <!-- Tab: Payables Risk -->
        <div v-if="activeTab === 'payables'" class="space-y-6">
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <KpiCard
              label="Total Outstanding"
              :value="formatCurrency(payablesData.total_outstanding as number)"
              :clickable="true"
              @click="drillDown.open(RISK_ENDPOINT, 'Overdue Payables', { metric: 'overdue_payables' })"
            />
            <KpiCard
              label="High Risk Suppliers"
              :value="payablesData.high_risk_suppliers"
              :severity="(payablesData.high_risk_suppliers as number) > 0 ? 'high' : undefined"
            />
            <KpiCard
              label="Avg Days Overdue"
              :value="payablesData.avg_days_overdue == null ? undefined : Math.round(payablesData.avg_days_overdue as number)"
              unit=" days"
              :severity="scoreSeverity(payablesData.avg_days_overdue as number, { good: 30, warn: 60, higherIsBetter: false })"
            />
          </div>

          <!-- Aging Analysis -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Payables Aging Analysis" :level="3" />
            <div class="mt-4">
              <div class="grid grid-cols-5 gap-4">
                <KpiCard
                  v-for="bucket in payablesData.aging_analysis"
                  :key="bucket.aging_bucket"
                  :label="bucket.aging_bucket"
                  :amount="bucket.outstanding_amount"
                  :currency="baseCurrency"
                  :sublabel="`${bucket.invoice_count} bills`"
                  variant="tile"
                  clickable
                  @click="drillDown.open(RISK_ENDPOINT, bucket.aging_bucket + ' Overdue Payables', { metric: 'overdue_payables', aging_bucket: bucket.aging_bucket })"
                />
              </div>
            </div>
          </div>

          <!-- Supplier Risk Scores -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
          <SectionHeader variant="caption" title="Supplier Risk Scores" hint="Payment behaviour and default probability" :level="3" />
          <div class="mt-4">
            <div class="overflow-x-auto">
                <table class="w-full">
                  <thead>
                    <tr class="border-b border-outline-gray-1">
                      <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Supplier</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Outstanding</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Avg Overdue Days</th>
                      <th scope="col" class="text-center py-2 text-sm font-medium text-ink-gray-7">Risk Category</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Risk Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="supplier in payablesData.supplier_risk_scores?.slice(0, 20)"
                      :key="supplier.supplier"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                    >
                      <td class="py-2 text-ink-gray-8">{{ supplier.supplier_name }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ formatCurrency(supplier.outstanding) }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ Math.round(supplier.avg_overdue_days || 0) }}</td>
                      <td class="py-2 text-center">
                        <Badge v-bind="severityBadge(supplier.risk_category)" size="sm" />
                      </td>
                      <td class="py-2 text-right font-medium text-ink-gray-8">{{ supplier.risk_score }}/100</td>
                    </tr>
                  </tbody>
                </table>
              </div>
          </div>
        </div>
        </div>

        <!-- Tab 3: Cash Flow Risk -->
        <div v-if="activeTab === 'cashflow'" class="space-y-6">
          <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <KpiCard label="Current Cash Position" :value="formatCurrency(cashflowData.current_cash_position as number)" />
            <KpiCard label="Working Capital" :value="formatCurrency(cashflowData.current_working_capital as number)" />
            <KpiCard label="Working Capital Ratio" :value="`${cashflowData.working_capital_ratio}x`" />
            <KpiCard
              label="Top Customer Share"
              :percent="cashflowData.top_customer_share == null ? null : Math.round(cashflowData.top_customer_share as number)"
              :severity="scoreSeverity(cashflowData.top_customer_share as number, { good: 20, warn: 30, higherIsBetter: false })"
            />
          </div>

          <!-- Revenue Concentration -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
          <SectionHeader variant="caption" title="Revenue Concentration Analysis" hint="Top customers by revenue share" :level="3" />
          <div class="mt-4">
            <div class="space-y-3">
                <div
                  v-for="customer in cashflowData.customer_concentration"
                  :key="customer.customer"
                  class="flex items-center justify-between p-3 bg-surface-gray-1 rounded"
                >
                  <div>
                    <div class="font-medium text-ink-gray-8">{{ customer.customer_name }}</div>
                    <div class="text-sm text-ink-gray-6">{{ formatCurrency(customer.revenue) }}</div>
                  </div>
                  <div class="text-right flex items-center gap-2">
                    <div class="font-bold text-ink-gray-8">{{ customer.revenue_share?.toFixed(1) }}%</div>
                    <Badge
                      v-if="customer.revenue_share > 30"
                      v-bind="severityBadge('high')"
                      size="sm"
                    />
                  </div>
                </div>
              </div>
          </div>
        </div>

          <!-- Overdue Days Trend -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Overdue Days Trend" :level="3" />
            <div class="mt-4">
              <div class="grid grid-cols-5 gap-4">
                <KpiCard
                  v-for="period in cashflowData.overdue_days_trend"
                  :key="period.period"
                  :label="period.period"
                  :value="period.avg_days_overdue"
                  unit=" days overdue"
                  variant="tile"
                  :loading="loading && !hasData"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Tab 4: Operational Risk -->
        <div v-if="activeTab === 'operational'" class="space-y-6">
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <KpiCard label="Invoice Error Rate" :value="`${(operationalData.process_risks as Record<string, number | undefined>)?.invoice_error_rate?.toFixed(2) || '0.00'}%`" />
            <KpiCard
              label="Avg Approval Time"
              :value="(operationalData.process_risks as Record<string, number | undefined>)?.average_approval_time"
              unit=" hrs"
            />
            <KpiCard label="System Incidents" :value="(operationalData.process_risks as Record<string, number | undefined>)?.system_downtime_incidents" />
          </div>

          <!-- Inventory Risk by Item Group -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
          <SectionHeader variant="caption" title="Inventory Risk by Item Group" :level="3" />
          <div class="mt-4">
            <div class="overflow-x-auto">
                <table class="w-full">
                  <thead>
                    <tr class="border-b border-outline-gray-1">
                      <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Item Group</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Total Items</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Stockout Items</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Stock Value</th>
                      <th scope="col" class="text-center py-2 text-sm font-medium text-ink-gray-7">Risk Level</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="risk in operationalData.inventory_risks?.slice(0, 15)"
                      :key="risk.item_group"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                    >
                      <td class="py-2 text-ink-gray-8">{{ risk.item_group }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ risk.total_items }}</td>
                      <td class="py-2 text-right">
                        <span :class="risk.stockout_items > 0 ? 'text-neg font-medium' : 'text-ink-gray-8'">
                          {{ risk.stockout_items }}
                        </span>
                      </td>
                      <td class="py-2 text-right text-ink-gray-8">{{ formatCurrency(risk.stock_value) }}</td>
                      <td class="py-2 text-center">
                        <Badge v-bind="severityBadge(risk.risk_category)" size="sm" />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
          </div>
        </div>

          <!-- Supplier Performance -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
          <SectionHeader variant="caption" title="Supplier Reliability Analysis" :level="3" />
          <div class="mt-4">
            <div class="overflow-x-auto">
                <table class="w-full">
                  <thead>
                    <tr class="border-b border-outline-gray-1">
                      <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Supplier</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Total Orders</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Total Value</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Avg Delay</th>
                      <th scope="col" class="text-center py-2 text-sm font-medium text-ink-gray-7">Risk Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="supplier in operationalData.supplier_performance"
                      :key="supplier.supplier"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                    >
                      <td class="py-2 text-ink-gray-8">{{ supplier.supplier_name }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ supplier.total_orders }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ formatCurrency(supplier.total_value) }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ Math.round(supplier.avg_delay_days || 0) }} days</td>
                      <td class="py-2 text-center">
                        <Badge v-bind="severityBadge(supplier.risk_category)" size="sm" />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
          </div>
        </div>
        </div>

        <!-- Tab 5: Compliance Risk -->
        <div v-if="activeTab === 'compliance'" class="space-y-6">
          <!-- GST Status -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="GST Compliance Status" hint="GSTR-1 / GSTR-3B filing and e-Invoice coverage" :level="3" />
            <div class="mt-4">
              <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <KpiCard
                  label="GSTR-1 Status"
                  :value="complianceData.gst_status?.gstr1_status"
                  :sublabel="complianceData.gst_status?.gstr1_latest_period ? `Latest: ${complianceData.gst_status.gstr1_latest_period}` : undefined"
                  :severity="gstStatusSeverity(complianceData.gst_status?.gstr1_status)"
                  variant="tile"
                  :loading="loading && !hasData"
                />
                <KpiCard
                  label="GSTR-3B Status"
                  :value="complianceData.gst_status?.gstr3b_status"
                  :sublabel="complianceData.gst_status?.gstr3b_latest_period ? `Latest: ${complianceData.gst_status.gstr3b_latest_period}` : undefined"
                  :severity="gstStatusSeverity(complianceData.gst_status?.gstr3b_status)"
                  variant="tile"
                  :loading="loading && !hasData"
                />
                <KpiCard
                  label="e-Invoice Coverage"
                  :percent="complianceData.gst_status?.einvoice_coverage_pct ?? null"
                  :severity="scoreSeverity(complianceData.gst_status?.einvoice_coverage_pct as number, { good: 95, warn: 80 })"
                  variant="tile"
                  :loading="loading && !hasData"
                />
                <KpiCard
                  label="e-Invoice Pending Value"
                  :amount="complianceData.gst_status?.einvoice_pending_value"
                  :currency="baseCurrency"
                  :severity="(complianceData.gst_status?.einvoice_pending_value || 0) > 0 ? 'high' : 'none'"
                  variant="tile"
                  :loading="loading && !hasData"
                />
              </div>
            </div>
          </div>

          <!-- Document Audit -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
          <SectionHeader variant="caption" title="Document Completeness Audit" :level="3" />
          <div class="mt-4">
            <div class="overflow-x-auto">
                <table class="w-full">
                  <thead>
                    <tr class="border-b border-outline-gray-1">
                      <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Document Type</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Total Documents</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Incomplete</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Completion Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="doc in complianceData.document_audit"
                      :key="doc.document_type"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                    >
                      <td class="py-2 text-ink-gray-8">{{ doc.document_type }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ doc.total_docs }}</td>
                      <td class="py-2 text-right">
                        <span :class="doc.incomplete_docs > 0 ? 'text-neg font-medium' : 'text-ink-gray-8'">
                          {{ doc.incomplete_docs }}
                        </span>
                      </td>
                      <td class="py-2 text-right">
                        <Badge
                          v-bind="severityBadge(scoreSeverity((doc.total_docs - doc.incomplete_docs) / doc.total_docs * 100, { good: 95, warn: 80 }))"
                          :label="`${((doc.total_docs - doc.incomplete_docs) / doc.total_docs * 100).toFixed(1)}%`"
                          size="sm"
                        />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
          </div>
        </div>

          <!-- GST / PAN Registration -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="GST / PAN Registration" :level="3" />
            <div class="mt-4">
              <div class="space-y-3">
                <div
                  v-for="license in complianceData.licenses"
                  :key="license.license_type"
                  class="flex items-center justify-between p-4 border border-outline-gray-1 rounded-lg"
                >
                  <div>
                    <div class="font-medium text-ink-gray-9">{{ license.license_type }}</div>
                    <div class="text-sm text-ink-gray-6">Reg No: {{ license.reference }}</div>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-sm text-ink-gray-7">{{ license.status }}</span>
                    <Badge v-bind="severityBadge(license.risk_level)" size="sm" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Tab 6: Predictive Analytics -->
        <div v-if="activeTab === 'predictive'" class="space-y-6">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <KpiCard
              label="Cash Flow Forecast"
              :value="(predictiveData.cash_flow_forecast as Record<string, string>)?.status || 'N/A'"
              :severity="(predictiveData.cash_flow_forecast as Record<string, string>)?.status === 'success' ? 'low' : 'medium'"
            />
            <KpiCard
              label="Revenue Forecast"
              :value="(predictiveData.revenue_forecast as Record<string, string>)?.status || 'N/A'"
              :severity="(predictiveData.revenue_forecast as Record<string, string>)?.status === 'success' ? 'low' : 'medium'"
            />
          </div>

          <!-- Anomaly Detection -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
          <SectionHeader variant="caption" title="Detected Anomalies" hint="Unusual patterns in financial data" :level="3" />
          <div class="mt-4">
            <ListView
              v-if="anomalyRows.length"
              class="list-ink-fix"
              :style="{ height: anomalyListHeight }"
              :columns="anomalyColumns"
              :rows="anomalyRows"
              row-key="key"
              :options="{ selectable: false, showTooltip: true, rowHeight: 40 }"
            >
              <template #cell="{ column, row, item }">
                <Badge
                  v-if="column.key === 'severity' && row.severity"
                  v-bind="severityBadge(row.severity)"
                  size="sm"
                />
                <span v-else class="truncate">{{ column.getLabel ? column.getLabel({ row }) : item }}</span>
              </template>
            </ListView>
              <div v-else class="text-center text-ink-gray-6 py-8">
                No anomalies detected in recent data
              </div>
          </div>
        </div>

          <!-- Early Warning Alerts -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
          <SectionHeader variant="caption" title="Early Warning System" :level="3" />
          <div class="mt-4">
            <ListView
              v-if="warningRows.length"
              class="list-ink-fix"
              :style="{ height: warningListHeight }"
              :columns="warningColumns"
              :rows="warningRows"
              row-key="key"
              :options="{ selectable: false, showTooltip: true, rowHeight: 40 }"
            >
              <template #cell="{ column, row, item }">
                <Badge
                  v-if="column.key === 'severity' && row.severity"
                  v-bind="severityBadge(row.severity)"
                  size="sm"
                />
                <span v-else class="truncate">{{ column.getLabel ? column.getLabel({ row }) : item }}</span>
              </template>
            </ListView>
              <div v-else class="text-center text-ink-gray-6 py-8">
                No early warnings at this time
              </div>
          </div>
        </div>

          <!-- Payment Risk Forecast -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
          <SectionHeader variant="caption" title="Payment Delay Risk Forecast" :level="3" />
          <div class="mt-4">
            <div
                v-if="predictiveData.payment_risk_forecast?.high_risk_customers?.length"
                class="overflow-x-auto"
              >
                <table class="w-full">
                  <thead>
                    <tr class="border-b border-outline-gray-1">
                      <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Customer</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Avg Delay Days</th>
                      <th scope="col" class="text-center py-2 text-sm font-medium text-ink-gray-7">Risk Category</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Risk Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="customer in predictiveData.payment_risk_forecast?.high_risk_customers"
                      :key="customer.customer"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                    >
                      <td class="py-2 text-ink-gray-8">{{ customer.customer }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ Math.round(customer.avg_delay_days) }}</td>
                      <td class="py-2 text-center">
                        <Badge v-bind="severityBadge(customer.risk_category)" size="sm" />
                      </td>
                      <td class="py-2 text-right font-medium text-ink-gray-8">{{ customer.risk_score }}/100</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-else class="text-center text-ink-gray-6 py-8">
                No high-risk payment patterns detected
              </div>
          </div>
        </div>
        </div>

        <!-- `v-if` like its siblings, which suits this tab: mounting is what
             issues the scan, so it stays unrequested until someone opens it. -->
        <div v-if="activeTab === 'anomalies'" class="space-y-6">
          <!-- No SectionHeader: the tab is already labelled "Ledger Anomalies",
               and the component opens with the flagged/scanned count and the
               caveat that unusual is not the same as wrong. -->
          <LedgerAnomalies />
        </div>
      </div>
    </IntelligenceDashboardShell>

    <!-- AI Chat Button -->
    <DashboardChatButton
      dashboard-type="Risk"
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

<style scoped>
/* Risk Intelligence dashboard */
</style>
