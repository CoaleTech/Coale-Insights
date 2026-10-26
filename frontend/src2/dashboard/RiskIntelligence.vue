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
import TabBrief, { type Brief } from '../intelligence/components/TabBrief.vue'
import TabActions from '../intelligence/components/TabActions.vue'
import StatStrip, { type StatItem } from '../intelligence/components/StatStrip.vue'
import IntelligenceChart from '../intelligence/components/IntelligenceChart.vue'
import { themeColor } from '../utils/chartTheme'
import {
  severityBadge, severityFill, severityAria, scoreSeverity, normaliseSeverity, type Severity,
} from '../utils/status'
import { formatCount, formatDate, formatDateTime, formatMoney, formatPercent, NO_VALUE } from '../utils/format'

// GST return periods are stored as MMYYYY (e.g. 102026); render as "Oct 2026".
function formatReturnPeriod(p: string): string {
  if (!/^(0[1-9]|1[0-2])\d{4}$/.test(p)) return p
  return new Date(Number(p.slice(2)), Number(p.slice(0, 2)) - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

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
interface CustomerRiskScore { customer: string; customer_name?: string; outstanding?: number; avg_overdue_days?: number; max_overdue_days?: number; risk_category?: string; risk_score?: number }
/** Supplier credit risk score row (payables side). */
interface SupplierRiskScore { supplier: string; supplier_name?: string; outstanding?: number; avg_overdue_days?: number; risk_category?: string; risk_score?: number }
/** Revenue concentration customer row. */
interface ConcentrationCustomer { customer: string; customer_name?: string; revenue?: number; revenue_share: number }
/** Overdue days trend period row. */
interface DSOPeriod { period: string; avg_days_overdue?: number }
/** Inventory risk by item group row. */
interface InventoryRiskRow { item_group: string; total_items?: number; stockout_items: number; stock_value?: number; risk_category?: string }
/** Supplier reliability row from operational risk. */
interface SupplierReliabilityRow { supplier: string; supplier_name?: string; total_orders?: number; total_value?: number; avg_delay_days?: number; cancelled_orders?: number; risk_category?: string }
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
  /** Server-computed verdict: names the primary driver, overall category, and critical alert count. */
  risk_verdict?: string
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
  /** Added 2026-10: component score, now echoed in the sub-dict so the Cash Flow tab can display it. */
  cashflow_score?: number | null
  /** Total open AR (= credit_risk.total_outstanding), added so cashflow detail has it without looking up a sibling section. */
  total_receivables?: number | null
  /** Total open AP (= payables_risk.total_outstanding). */
  total_payables?: number | null
  /** total_receivables − total_payables; null when either is absent. */
  net_exposure?: number | null
  /** Alias for current_cash_position (canonical name used by the new fields). */
  cash_position?: number | null
  /** Alias for current_working_capital. */
  net_working_capital?: number | null
  /** Prophet-style daily series from the cash model; the tab shows one row a week. */
  cash_forecast?: { forecast?: Array<{ ds: string; yhat: number; yhat_lower: number; yhat_upper: number }> } | null
}
/** Typed operational risk sub-section. */
interface OperationalSection {
  process_risks?: Record<string, number | undefined>
  inventory_risks?: InventoryRiskRow[]
  supplier_performance?: SupplierReliabilityRow[]
  top_inventory_risk?: InventoryRiskRow & { stockout_risk_score?: number }
}
/** Typed compliance risk sub-section. */
interface ComplianceSection {
  gst_status?: GstStatus
  document_audit?: DocumentAuditRow[]
  licenses?: LicenseRow[]
}
/** Typed predictive analytics sub-section. */
interface PredictiveSection {
  cash_flow_forecast?: { status?: string; forecast?: { ds: string; yhat: number; yhat_lower?: number; yhat_upper?: number }[]; model_performance?: { trend?: string; method?: string; data_points?: number } }
  revenue_forecast?: { status?: string; forecast?: { ds: string }[]; total_forecasted_revenue?: number; model_performance?: { trend?: string; method?: string; data_points?: number } }
  anomalies?: AnomalyRow[]
  early_warnings?: EarlyWarningRow[]
  payment_risk_forecast?: { average_market_delay?: number; high_risk_customers?: PaymentRiskCustomer[] }
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
  tab_briefs?: Record<string, Brief>
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
// Payment-risk rows carry only the customer code; names come from the credit scores.
const customerNames = computed(() => new Map((creditData.value.customer_risk_scores ?? []).map(r => [r.customer, r.customer_name])))
// Table order follows the mock: outstanding x risk score, highest first.
const exposure = (r: { outstanding?: number; risk_score?: number }) => (Number(r.outstanding) || 0) * (Number(r.risk_score) || 0) / 100
const byExposure = <T extends { outstanding?: number; risk_score?: number }>(rows: T[] | undefined) =>
  [...(rows ?? [])].sort((a, b) => exposure(b) - exposure(a)).slice(0, 20)
const creditByExposure = computed(() => byExposure(creditData.value.customer_risk_scores))
const payablesByExposure = computed(() => byExposure(payablesData.value.supplier_risk_scores))
// Weekly sample of the daily cash forecast, plus the last day.
const forecastSample = computed(() => {
  const fc = predictiveData.value.cash_flow_forecast?.forecast ?? []
  return fc.filter((_, i) => i % 7 === 0 || i === fc.length - 1)
})
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
  { label: 'Ledger Anomalies', value: 'ledger' },
]
const activeTabIndex = ref(0)
const activeTab = computed(() => tabDefs[activeTabIndex.value]?.value ?? 'overview')
const tabsForComponent = tabDefs.map(t => ({ label: t.label }))

const tabBriefs = computed(() => riskData.value?.tab_briefs ?? {})
// The ledger scan is issued on mount, so it runs only on request.
const showLedger = ref(false)
const cashForecastWeekly = computed(() =>
  (cashflowData.value.cash_forecast?.forecast ?? []).filter((_, i) => i % 7 === 0),
)
const creditStrip = computed<StatItem[]>(() => {
  const c = creditData.value
  const buckets = c.aging_analysis ?? []
  const sum = (bs: AgingBucket[], k: 'outstanding_amount' | 'invoice_count') => bs.reduce((n, b) => n + (Number(b[k]) || 0), 0)
  const total = c.total_outstanding == null ? null : Number(c.total_outstanding)
  const late = buckets.filter((b) => b.aging_bucket !== 'Current' && b.aging_bucket !== '1-30 Days')
  const lateAmt = buckets.length ? sum(late, 'outstanding_amount') : null
  return [
    { label: 'Total AR', amount: total, sublabel: buckets.length ? `${formatCount(sum(buckets, 'invoice_count'))} invoices` : undefined },
    { label: 'Overdue over 30 days', amount: lateAmt, tone: lateAmt ? 'neg' : undefined, sublabel: lateAmt != null && total ? `${formatPercent((lateAmt / total) * 100)} of total AR` : undefined },
    { label: 'High Risk Customers', value: c.high_risk_customers ?? null, tone: (c.high_risk_customers ?? 0) > 0 ? 'neg' : undefined },
    { label: 'Credit Risk Score', value: summary.value.creditScore ?? null, unit: '/100', sublabel: summary.value.creditRisk ?? undefined },
  ]
})
const TIER_ORDER = ['Critical', 'High', 'Medium', 'Low']
const creditTiers = computed(() => {
  const rows = creditData.value.customer_risk_scores ?? []
  const by = new Map<string, { category: string; count: number; outstanding: number }>()
  for (const r of rows) {
    const key = r.risk_category ?? 'Unrated'
    const t = by.get(key) ?? { category: key, count: 0, outstanding: 0 }
    t.count += 1
    t.outstanding += Number(r.outstanding) || 0
    by.set(key, t)
  }
  const rank = (c: string) => (TIER_ORDER.includes(c) ? TIER_ORDER.indexOf(c) : TIER_ORDER.length)
  return { rows: [...by.values()].sort((a, b) => rank(a.category) - rank(b.category)), scored: rows.length }
})
const payablesStrip = computed<StatItem[]>(() => {
  const p = payablesData.value
  const buckets = p.aging_analysis ?? []
  const bills = buckets.reduce((n, b) => n + (Number(b.invoice_count) || 0), 0)
  const oldest = buckets.find((b) => b.aging_bucket === '90+ Days')
  const totalSuppliers = overviewData.value.total_suppliers
  return [
    { label: 'Total AP', amount: p.total_outstanding == null ? null : Number(p.total_outstanding), sublabel: buckets.length ? `${formatCount(bills)} bills` : undefined },
    { label: 'High-Risk Suppliers', value: p.high_risk_suppliers ?? null, tone: (p.high_risk_suppliers ?? 0) > 0 ? 'neg' : undefined, sublabel: totalSuppliers == null ? undefined : `of ${formatCount(totalSuppliers)} total` },
    { label: 'Avg Days Overdue', value: p.avg_days_overdue == null ? null : Math.round(Number(p.avg_days_overdue)), unit: ' days' },
    { label: 'Overdue 90+ Days', amount: oldest?.outstanding_amount == null ? null : Number(oldest.outstanding_amount), tone: Number(oldest?.outstanding_amount) > 0 ? 'neg' : undefined, sublabel: oldest ? `${formatCount(oldest.invoice_count ?? null)} bills` : undefined },
  ]
})
const cashflowStrip = computed<StatItem[]>(() => {
  const c = cashflowData.value
  const dso = c.overdue_days_trend?.at(-1)
  return [
    { label: 'Cash Position', amount: c.current_cash_position ?? null, tone: (c.current_cash_position ?? 0) < 0 ? 'neg' : undefined },
    { label: 'Working Capital Ratio', value: c.working_capital_ratio ?? null, unit: '×', sublabel: `${formatMoney(c.current_working_capital, baseCurrency.value)} working capital` },
    { label: 'Avg Days Overdue', value: dso?.avg_days_overdue ?? null, unit: ' days', sublabel: dso?.period },
    { label: 'Top Customer Share', percent: c.top_customer_share ?? null },
  ]
})
const operationalStrip = computed<StatItem[]>(() => {
  const o = operationalData.value
  // Totals across every item group; the first group alone read 65.2% against 56.2% overall.
  const groups = (o.inventory_risks ?? []) as InventoryRiskRow[]
  const items = groups.reduce((s, g) => s + (g.total_items ?? 0), 0)
  const out = groups.reduce((s, g) => s + g.stockout_items, 0)
  const suppliers = o.supplier_performance ?? []
  return [
    { label: 'Stockout Rate', percent: items ? (out / items) * 100 : null, sublabel: items ? `${formatCount(out)} of ${formatCount(items)} items` : undefined },
    { label: 'Remaining Stock Value', amount: items ? groups.reduce((s, g) => s + (g.stock_value ?? 0), 0) : null },
    { label: 'Suppliers Above Low Risk', value: suppliers.filter(s => s.risk_category !== 'Low').length, sublabel: `of ${formatCount(suppliers.length)} tracked` },
    { label: 'Invoice Error Rate', value: formatPercent(o.process_risks?.invoice_error_rate, 2) },
  ]
})
// Approval time and downtime ship as null (not instrumented); null renders "-", never 0.
const processIndicators = computed(() => {
  const p = operationalData.value.process_risks
  const row = (label: string, v: number | null | undefined, display: string, tracked: string) => {
    const value = v ?? null
    return { label, value, display, note: value === null ? 'Not tracked in ERP yet' : tracked }
  }
  const err = p?.invoice_error_rate ?? null
  const appr = p?.average_approval_time ?? null
  const down = p?.system_downtime_incidents ?? null
  return [
    row('Invoice error rate', err, formatPercent(err, 2), 'Computed from submitted invoices'),
    row('Avg approval time', appr, String(appr), 'Workflow approval time'),
    row('System downtime', down, String(down), 'Downtime incidents'),
  ]
})
const predictiveStrip = computed<StatItem[]>(() => {
  const p = predictiveData.value
  const fc = p.cash_flow_forecast?.forecast ?? []
  const last = fc.at(-1)
  const risky = p.payment_risk_forecast?.high_risk_customers ?? []
  const delay = p.payment_risk_forecast?.average_market_delay
  return [
    { label: `${fc.length}-Day Cash Forecast`, amount: last?.yhat ?? null, sublabel: last ? `${formatDate(last.ds)}${last.yhat_lower == null ? '' : ` · lower ${formatMoney(Math.min(last.yhat_lower, last.yhat_upper ?? last.yhat_lower), baseCurrency.value)}`}` : undefined },
    { label: 'Forecast Trend', value: p.cash_flow_forecast?.model_performance?.trend ?? null, sublabel: fc.length > 1 ? `${formatMoney(fc[0].yhat, baseCurrency.value)} to ${formatMoney(fc[fc.length - 1].yhat, baseCurrency.value)}` : undefined },
    { label: 'High-Risk Customers', value: risky.length, sublabel: delay == null ? undefined : `Avg market delay ${delay} days` },
    { label: 'Anomalies Detected', value: (p.anomalies ?? []).length, sublabel: 'Model scan' },
  ]
})

const revenueForecast = computed(() => {
  const r = predictiveData.value.revenue_forecast
  const fc = r?.forecast ?? []
  if (!r || r.status !== 'success' || !fc.length) return null
  const end = fc[fc.length - 1].ds
  const asOf = riskData.value?.generated_at
  return {
    method: r.model_performance?.method,
    window: `${formatDate(fc[0].ds)} to ${formatDate(end)}`,
    total: r.total_forecasted_revenue == null ? NO_VALUE : formatMoney(r.total_forecasted_revenue, baseCurrency.value),
    trend: r.model_performance?.trend ?? NO_VALUE,
    points: formatCount(r.model_performance?.data_points ?? null),
    stale: !!asOf && end < asOf.slice(0, 10),
  }
})

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
 *
 * The third series ("Net Exposure" = receivables − payables) fills as an area
 * so the crossover becomes spatially obvious: the shaded area is above zero
 * when receivables lead, and below zero when payables crossed over. No
 * hand-placed geometry is needed -- the shading is computed from the data,
 * and ECharts' area fill to y=0 is the crossover indicator.
 * yMin: 0 is deliberately absent (see Rule 3 exception: signed balances where
 * the sign is the message, same as ThirteenWeekChart).
 */
const exposureTrendConfig = computed(() => ({
  title: '',
  data: exposureTrend.value.map(r => ({
    period: r.period,
    Receivables: r.receivables,
    Payables: r.payables,
    'Net Exposure': r.receivables - r.payables,
  })),
  xAxis: { key: 'period', type: 'category' as const },
  yAxis: { title: baseCurrency.value },
  colors: [
    themeColor('--app-accent-strong'),
    themeColor('--app-muted-fill'),
    themeColor('--app-highlight'),
  ],
  series: [
    { name: 'Receivables', type: 'line' as const, showDataPoints: true },
    { name: 'Payables', type: 'line' as const, showDataPoints: true },
    { name: 'Net Exposure', type: 'area' as const, fillOpacity: 0.15, showDataPoints: false },
  ],
}))

/** Average days overdue by month, drawn as one line (mock: Overdue Days Trend chart). */
const overdueTrendConfig = computed(() => ({
  title: '',
  data: (cashflowData.value?.overdue_days_trend ?? []).map(p => ({
    period: p.period,
    'Avg days overdue': Number(p.avg_days_overdue),
  })),
  xAxis: { key: 'period', type: 'category' as const },
  yAxis: { title: 'Days' },
  colors: [themeColor('--app-accent-strong')],
  series: [{ name: 'Avg days overdue', type: 'line' as const, showDataPoints: true }],
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
/** Top items for the right rail: at most 6, critical-first (queue is already sorted). */
const topQueueItems = computed(() => actionQueue.value.slice(0, 6))


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
      :kpi-count="4"
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
      <div v-if="activeTab === 'overview'" class="p-6 grid grid-cols-2 lg:grid-cols-4 gap-4">
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
        <!-- Tab 1: Overview — Variant C: Hero chart (2/3) + attention rail (1/3) -->
        <div v-if="activeTab === 'overview'" class="grid grid-cols-1 lg:grid-cols-3 gap-5 items-start">

          <!-- ── Left: hero panel + component strip ── -->
          <div class="lg:col-span-2 flex flex-col gap-5">

            <!--
              Hero panel: blue-tinted background to signal "this is the
              primary diagnostic section". Holds the server-computed verdict
              headline, the annotated exposure trend chart, and the 4-column
              component strip.

              `risk_verdict` is the canonical hero title: server-computed from
              component scores + critical alert count (Rule 7). A fallback to
              the overall category label is shown only while an old cached
              payload (no `risk_verdict` field) is in flight — never a
              client-side inference sentence.
            -->
            <div class="bg-surface-blue-2 border border-outline-gray-1 rounded-lg p-5">
              <p class="text-xs font-semibold uppercase tracking-widest text-ink-blue-3 mb-1.5">
                Exposure Trend · Primary diagnostic
              </p>
              <h2 class="text-base font-bold text-ink-gray-9 leading-snug">
                {{ overviewData.risk_verdict ?? (summary.overallRisk ? `${summary.overallRisk} overall risk — see component breakdown below` : 'Overall risk assessment') }}
              </h2>
              <p class="text-xs text-ink-gray-6 mt-0.5 mb-4">{{ exposureTrendHint }}</p>

              <!--
                Annotated exposure chart: three series.
                • Receivables (line, blue) — GL AR balance each month end.
                • Payables (line, muted) — GL AP balance each month end.
                • Net Exposure (area, orange, fillOpacity 0.15) — R − P.
                  When R − P > 0 the shaded area is above zero (healthy buffer).
                  When R − P < 0 the area flips below zero (payables crossed).
                  The zero-crossing is the crossover event, computed from the
                  data — no hand-placed geometry. See exposureTrendConfig.
              -->
              <IntelligenceChart
                v-if="exposureTrend.length"
                :config="exposureTrendConfig"
                class="h-80"
              />
              <p v-else class="text-sm text-ink-gray-6 text-center py-8">
                No exposure trend data yet.
              </p>

              <!--
                Component strip: same four rows as the old "Risk Component
                Breakdown" section, now compact and directly below the chart
                they explain. Weight shown per column so 70.8 × 0.30 > 44.0
                × 0.30 is readable without scrolling to a separate panel.
              -->
              <div class="mt-4 pt-4 border-t border-outline-gray-1 grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div
                  v-for="row in riskComponentRows"
                  :key="row.label"
                >
                  <p class="text-xs uppercase tracking-wide text-ink-gray-6 mb-1.5 truncate">
                    {{ row.label.replace(' Risk', '') }}
                    <span class="font-normal">&times;{{ row.weight }}</span>
                  </p>
                  <div
                    class="h-1.5 bg-surface-gray-3 rounded-full mb-1.5"
                    :aria-label="severityAria(row.label, row.severity, row.display)"
                    role="img"
                  >
                    <div
                      v-if="row.width"
                      :class="[severityFill(row.severity), 'h-1.5 rounded-full transition-all motion-reduce:transition-none']"
                      :style="{ width: row.width }"
                    />
                  </div>
                  <p class="text-sm font-bold text-ink-gray-8 tnum">{{ row.display }}</p>
                  <Badge v-if="row.category" v-bind="severityBadge(row.category)" size="sm" class="mt-0.5" />
                </div>
              </div>
            </div>

          </div>

          <!-- ── Right rail: needs attention + compact matrix ── -->
          <div class="flex flex-col gap-3">

            <SectionHeader
              variant="caption"
              title="Needs attention"
              :hint="`${queueCritical} critical · ${actionQueue.length} total`"
              :level="3"
            />

            <!--
              Top queue items, critical-first (actionQueue is already sorted).
              Capped at 6 so the rail stays scannable without scrolling.
              The full unified queue (observed + forecasts + anomalies) scrolls
              in the Predictive Analytics tab.
            -->
            <div
              v-for="item in topQueueItems"
              :key="item.key"
              class="bg-surface-white border border-outline-gray-1 rounded-md p-3 flex gap-2.5"
            >
              <!--
                Left accent bar: non-text shape, severityFill() is correct
                here (bg-neg-fill / bg-warn-fill / bg-muted-fill). The
                Badge on the next line carries the accessible text label.
              -->
              <div
                :class="[severityFill(normaliseSeverity(item.severity)), 'w-1 self-stretch rounded-full shrink-0']"
                aria-hidden="true"
              />
              <div class="min-w-0 flex-1">
                <div class="flex items-center justify-between gap-1 mb-0.5">
                  <Badge v-bind="severityBadge(item.severity)" size="sm" />
                  <span class="text-xs text-ink-gray-6 shrink-0">{{ item.kind }}</span>
                </div>
                <p class="text-xs font-semibold text-ink-gray-8 leading-snug mt-1">{{ item.title }}</p>
                <p class="text-xs text-ink-gray-6 mt-0.5 line-clamp-2">{{ item.detail }}</p>
                <div class="flex items-center justify-between mt-1.5 gap-2">
                  <span
                    v-if="item.amount !== null && item.amount !== undefined"
                    class="text-xs font-bold text-ink-gray-8 tnum"
                  >
                    {{ formatMoney(item.amount, baseCurrency) }}
                  </span>
                  <span v-else class="flex-1" />
                  <Button
                    v-if="item.customer"
                    variant="ghost"
                    size="sm"
                    @click.stop="openQueueDrill(item)"
                  >
                    Invoices →
                  </Button>
                </div>
              </div>
            </div>

            <p
              v-if="!topQueueItems.length"
              class="text-sm text-ink-gray-6 text-center py-4 bg-surface-white border border-outline-gray-1 rounded-md"
            >
              No alerts
            </p>

            <!--
              Compact risk matrix: name, score, level badge.
              Already sorted by risk_score desc from the backend (_risk_matrix).
              The full table with probability/impact bars is gone from this tab
              — it had a 6-col layout too wide for the 1/3 rail and the columns
              added no signal beyond the final score.
            -->
            <div class="bg-surface-white border border-outline-gray-1 rounded-md p-3">
              <SectionHeader
                variant="caption"
                title="Risk matrix"
                hint="prob × impact ÷ 100"
                :level="4"
              />
              <div class="mt-2 space-y-2">
                <div
                  v-for="risk in overviewData.risk_matrix"
                  :key="risk.name"
                  class="flex items-center gap-2"
                >
                  <span class="flex-1 text-xs text-ink-gray-7 truncate">{{ risk.name }}</span>
                  <span class="text-xs font-bold text-ink-gray-8 tnum shrink-0">
                    {{ risk.risk_score != null ? risk.risk_score.toFixed(1) : NO_VALUE }}
                  </span>
                  <Badge v-bind="severityBadge(risk.risk_category)" size="sm" class="shrink-0" />
                </div>
              </div>
            </div>

          </div>

        </div>

        <!-- Tab 2: Credit Risk -->
        <div v-if="activeTab === 'credit'" class="space-y-6">
          <TabBrief :brief="tabBriefs.credit" :as-of="riskData?.generated_at" />
          <StatStrip :items="creditStrip" :currency="baseCurrency" />

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
                  @click="drillDown.open(RISK_ENDPOINT, bucket.aging_bucket === 'Current' ? 'Current, not yet due' : bucket.aging_bucket + ' Overdue', { metric: 'overdue_invoices', aging_bucket: bucket.aging_bucket })"
                />
              </div>
            </div>
          </div>

          <!-- Risk tiers (grouped from the scored customer rows) -->
          <div v-if="creditTiers.rows.length" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Risk Tiers" :hint="`Scored customers: ${creditTiers.scored}, by outstanding`" :level="3" />
            <div class="mt-4 overflow-x-auto">
              <table class="w-full">
                <thead>
                  <tr class="border-b border-outline-gray-1">
                    <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Tier</th>
                    <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Customers</th>
                    <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Outstanding</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="tier in creditTiers.rows" :key="tier.category" class="border-b border-outline-gray-1">
                    <td class="py-2"><Badge v-bind="severityBadge(tier.category)" size="sm" /></td>
                    <td class="py-2 text-right text-ink-gray-8">{{ formatCount(tier.count) }}</td>
                    <td class="py-2 text-right text-ink-gray-8">{{ formatCurrency(tier.outstanding) }}</td>
                  </tr>
                </tbody>
              </table>
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
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Max Overdue</th>
                      <th scope="col" class="text-center py-2 text-sm font-medium text-ink-gray-7">Risk Category</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Risk Score</th>
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Exposure × Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="customer in creditByExposure"
                      :key="customer.customer"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1"
                    >
                      <td class="py-2 text-ink-gray-8">{{ customer.customer_name }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ formatCurrency(customer.outstanding) }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ Math.round(customer.avg_overdue_days || 0) }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ customer.max_overdue_days == null ? NO_VALUE : Math.round(customer.max_overdue_days) }}</td>
                      <td class="py-2 text-center">
                        <Badge v-bind="severityBadge(customer.risk_category)" size="sm" />
                      </td>
                      <td class="py-2 text-right font-medium text-ink-gray-8">{{ customer.risk_score }}/100</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ formatCurrency(exposure(customer)) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
          </div>
          </div>
          <TabActions class="mt-6" :actions="tabBriefs.credit?.actions" />
        </div>

        <!-- Tab 3: Payables Risk -->
        <div v-if="activeTab === 'payables'" class="space-y-6">
          <TabBrief :brief="tabBriefs.payables" :as-of="riskData?.generated_at" />
          <StatStrip :items="payablesStrip" :currency="baseCurrency" />

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
                  @click="drillDown.open(RISK_ENDPOINT, bucket.aging_bucket === 'Current' ? 'Payables, not yet due' : bucket.aging_bucket + ' Overdue Payables', { metric: 'overdue_payables', aging_bucket: bucket.aging_bucket })"
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
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Exposure × Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="supplier in payablesByExposure"
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
                      <td class="py-2 text-right text-ink-gray-8">{{ formatCurrency(exposure(supplier)) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
          </div>
        </div>
          <div v-if="operationalData.supplier_performance?.length" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Supplier Delivery Reliability" hint="From Operational Risk" :level="3" />
            <div class="mt-4 overflow-x-auto">
              <table class="w-full">
                <thead>
                  <tr class="border-b border-outline-gray-1">
                    <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Supplier</th>
                    <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Orders</th>
                    <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Total Value</th>
                    <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Avg Delay</th>
                    <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Cancelled</th>
                    <th scope="col" class="text-center py-2 text-sm font-medium text-ink-gray-7">Delivery Risk</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="s in operationalData.supplier_performance" :key="s.supplier" class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
                    <td class="py-2 text-ink-gray-8">{{ s.supplier_name }}</td>
                    <td class="py-2 text-right text-ink-gray-8">{{ formatCount(s.total_orders ?? null) }}</td>
                    <td class="py-2 text-right text-ink-gray-8">{{ formatCurrency(s.total_value) }}</td>
                    <td class="py-2 text-right text-ink-gray-8">{{ s.avg_delay_days == null ? NO_VALUE : `${Math.abs(Math.round(s.avg_delay_days * 10) / 10)}d ${s.avg_delay_days < 0 ? 'early' : 'late'}` }}</td>
                    <td class="py-2 text-right text-ink-gray-8">{{ formatCount(s.cancelled_orders ?? null) }}</td>
                    <td class="py-2 text-center"><Badge v-bind="severityBadge(s.risk_category)" size="sm" /></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <TabActions class="mt-6" :actions="tabBriefs.payables?.actions" />
        </div>

        <!-- Tab 3: Cash Flow Risk -->
        <div v-if="activeTab === 'cashflow'" class="space-y-6">
          <TabBrief :brief="tabBriefs.cashflow" :as-of="riskData?.generated_at" />
          <StatStrip :items="cashflowStrip" :currency="baseCurrency" />

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          <!-- Overdue Days Trend -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Overdue Days Trend" hint="Average days overdue, by month" :level="3" />
            <div class="mt-4">
              <IntelligenceChart
                v-if="cashflowData.overdue_days_trend?.length"
                :config="overdueTrendConfig"
                class="h-64"
              />
              <p v-else class="text-sm text-ink-gray-6 text-center py-8">No overdue trend data yet.</p>
            </div>
          </div>

          <div v-if="cashForecastWeekly.length" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="30-day cash forecast" hint="One row a week" :level="3" />
            <table class="mt-4 w-full text-sm">
              <caption class="sr-only">Forecast cash position by week with its range</caption>
              <thead>
                <tr class="border-b border-outline-gray-1">
                  <th scope="col" class="pb-2 text-left font-medium text-ink-gray-6">Date</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Forecast</th>
                  <th scope="col" class="pb-2 text-right font-medium text-ink-gray-6">Range</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-outline-gray-1">
                <tr v-for="row in cashForecastWeekly" :key="row.ds">
                  <th scope="row" class="py-2 text-left font-normal text-ink-gray-8">{{ row.ds }}</th>
                  <td class="tnum py-2 text-right font-medium" :class="row.yhat < 0 ? 'text-ink-red-3' : 'text-ink-gray-9'">
                    {{ formatMoney(row.yhat, baseCurrency) }}
                  </td>
                  <td class="tnum py-2 text-right text-ink-gray-6">
                    {{ formatMoney(Math.min(row.yhat_lower, row.yhat_upper), baseCurrency) }} to {{ formatMoney(Math.max(row.yhat_lower, row.yhat_upper), baseCurrency) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          </div>
          <!-- Revenue Concentration -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
          <SectionHeader variant="caption" title="Revenue Concentration Analysis" hint="Top customers by revenue share" :level="3" />
          <div class="mt-4">
            <div class="space-y-3">
                <div
                  v-for="customer in cashflowData.customer_concentration"
                  :key="customer.customer"
                  class="p-3 bg-surface-gray-1 rounded"
                >
                  <div class="flex items-center justify-between">
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
                  <div class="mt-2 h-1.5 rounded-full bg-surface-gray-3">
                    <div class="h-1.5 rounded-full bg-surface-blue-3" :style="{ width: `${Math.min(100, Number(customer.revenue_share) || 0)}%` }" />
                  </div>
                </div>
              </div>
          </div>
        </div>

          <TabActions class="mt-6" :actions="tabBriefs.cashflow?.actions" />
        </div>

        <!-- Tab 4: Operational Risk -->
        <div v-if="activeTab === 'operational'" class="space-y-6">
          <TabBrief :brief="tabBriefs.operational" :as-of="riskData?.generated_at" />
          <StatStrip :items="operationalStrip" :currency="baseCurrency" />

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
          <TabActions class="mt-6" :actions="tabBriefs.operational?.actions" />
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
                      <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Cancelled</th>
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
                      <td class="py-2 text-right text-ink-gray-8">{{ supplier.avg_delay_days == null ? NO_VALUE : `${Math.abs(Math.round(supplier.avg_delay_days * 10) / 10)}d ${supplier.avg_delay_days < 0 ? 'early' : 'late'}` }}</td>
                      <td class="py-2 text-right text-ink-gray-8">{{ formatCount(supplier.cancelled_orders ?? null) }}</td>
                      <td class="py-2 text-center">
                        <Badge v-bind="severityBadge(supplier.risk_category)" size="sm" />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
          </div>
        </div>

          <!-- Process risk indicators: approval time and downtime are null in the payload (not instrumented) -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Process Risk Indicators" :level="3" />
            <div class="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
              <div v-for="p in processIndicators" :key="p.label" class="rounded-lg p-4" :class="p.value === null ? 'bg-surface-gray-2' : 'bg-surface-gray-1'">
                <div class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">{{ p.label }}</div>
                <div class="mt-1 text-xl font-semibold text-ink-gray-9 tnum">{{ p.value === null ? NO_VALUE : p.display }}</div>
                <div class="text-sm text-ink-gray-6">{{ p.note }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Tab 5: Compliance Risk -->
        <div v-if="activeTab === 'compliance'" class="space-y-6">
          <TabBrief :brief="tabBriefs.compliance" :as-of="riskData?.generated_at" />
          <!-- GST Status -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="GST Compliance Status" hint="GSTR-1 / GSTR-3B filing and e-Invoice coverage" :level="3" />
            <div class="mt-4">
              <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <KpiCard
                  label="GSTR-1 Status"
                  :value="complianceData.gst_status?.gstr1_status"
                  :sublabel="complianceData.gst_status?.gstr1_latest_period ? `Latest: ${formatReturnPeriod(complianceData.gst_status.gstr1_latest_period)}` : undefined"
                  :severity="gstStatusSeverity(complianceData.gst_status?.gstr1_status)"
                  variant="tile"
                  :loading="loading && !hasData"
                />
                <KpiCard
                  label="GSTR-3B Status"
                  :value="complianceData.gst_status?.gstr3b_status"
                  :sublabel="complianceData.gst_status?.gstr3b_latest_period ? `Latest: ${formatReturnPeriod(complianceData.gst_status.gstr3b_latest_period)}` : undefined"
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
                      <td class="py-2 text-right text-ink-gray-8">{{ formatCount(doc.total_docs) }}</td>
                      <td class="py-2 text-right">
                        <span :class="doc.incomplete_docs > 0 ? 'text-neg font-medium' : 'text-ink-gray-8'">
                          {{ formatCount(doc.incomplete_docs) }}
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
          <TabActions class="mt-6" :actions="tabBriefs.compliance?.actions" />
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

        <!-- Tab 7: Ledger Anomalies -->
        <div v-if="activeTab === 'ledger'" class="space-y-6">
          <TabBrief :brief="tabBriefs.ledger" :as-of="riskData?.generated_at" />

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

          <!-- Ledger scan: issued on mount, so it runs on request -->
          <div class="space-y-3">
            <SectionHeader variant="caption" title="Ledger scan" hint="Scans submitted invoices when run" :level="3" />
            <Button v-if="!showLedger" variant="outline" @click="showLedger = true">Run ledger scan</Button>
            <LedgerAnomalies v-else />
          </div>
          <TabActions class="mt-6" :actions="tabBriefs.ledger?.actions" />
        </div>

        <!-- Tab 6: Predictive Analytics -->
        <div v-if="activeTab === 'predictive'" class="space-y-6">
          <TabBrief :brief="tabBriefs.predictive" :as-of="riskData?.generated_at" />
          <StatStrip :items="predictiveStrip" :currency="baseCurrency" />

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

          <!-- Cash Forecast -->
          <div v-if="forecastSample.length" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Cash forecast" :hint="`${predictiveData.cash_flow_forecast?.forecast?.length ?? 0} daily points, weekly sample`" :level="3" />
            <table class="w-full mt-4">
              <thead>
                <tr class="border-b border-outline-gray-1">
                  <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Date</th>
                  <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Forecast cash</th>
                  <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Lower</th>
                  <th scope="col" class="text-right py-2 text-sm font-medium text-ink-gray-7">Upper</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="pt in forecastSample" :key="pt.ds" class="border-b border-outline-gray-1">
                  <td class="py-2 text-ink-gray-8">{{ formatDate(pt.ds) }}</td>
                  <td class="py-2 text-right font-medium" :class="pt.yhat < 0 ? 'text-ink-red-3' : 'text-ink-gray-8'">{{ formatCurrency(pt.yhat) }}</td>
                  <td class="py-2 text-right text-ink-gray-8">{{ pt.yhat_lower == null || pt.yhat_upper == null ? NO_VALUE : formatCurrency(Math.min(pt.yhat_lower, pt.yhat_upper)) }}</td>
                  <td class="py-2 text-right text-ink-gray-8">{{ pt.yhat_lower == null || pt.yhat_upper == null ? NO_VALUE : formatCurrency(Math.max(pt.yhat_lower, pt.yhat_upper)) }}</td>
                </tr>
              </tbody>
            </table>
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
                      <td class="py-2 text-ink-gray-8">
                        {{ customerNames.get(customer.customer) || customer.customer }}
                        <div v-if="customerNames.get(customer.customer)" class="text-xs text-ink-gray-5">{{ customer.customer }}</div>
                      </td>
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

          <!-- Revenue Forecast: window and total come from the payload; stale when the last forecast date is before the as-of date -->
          <div v-if="revenueForecast" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
            <SectionHeader variant="caption" title="Revenue Forecast" :hint="revenueForecast.method" :level="3" />
            <dl class="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div><dt class="text-ink-gray-6">Window</dt><dd class="text-ink-gray-9 tnum">{{ revenueForecast.window }}</dd></div>
              <div><dt class="text-ink-gray-6">Total forecasted</dt><dd class="text-ink-gray-9 tnum">{{ revenueForecast.total }}</dd></div>
              <div><dt class="text-ink-gray-6">Trend</dt><dd class="text-ink-gray-9 tnum">{{ revenueForecast.trend }}</dd></div>
              <div><dt class="text-ink-gray-6">Data points</dt><dd class="text-ink-gray-9 tnum">{{ revenueForecast.points }}</dd></div>
            </dl>
            <p v-if="revenueForecast.stale" class="mt-4 text-sm text-ink-amber-3">The forecast window ends before the as-of date, so no forward-looking revenue forecast is available. Re-run the model.</p>
          </div>
          <TabActions class="mt-6" :actions="tabBriefs.predictive?.actions" />
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
