<script setup lang="ts">
import IntelligenceChart from './components/IntelligenceChart.vue'
defineOptions({ name: 'TaxIntelligence' })
import { Breadcrumbs, Button, Badge, Tabs } from 'frappe-ui'
import {
  RefreshCcw, AlertTriangle, CheckCircle,
} from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useIntelligenceDashboard } from './composables/useIntelligenceDashboard'
import { severityBadge, severityFill, scoreSeverity, deltaInk, prioritySeverity, readinessLabel, type Severity } from '../utils/status'
import { asNumber, formatCount, formatDate, formatMoney, formatPercent as sharedPercent, NO_VALUE } from '../utils/format'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import IntelligenceDateFilter from '../components/IntelligenceDateFilter.vue'
import KpiCard from './components/KpiCard.vue'
import IntelligenceDashboardShell from './components/IntelligenceDashboardShell.vue'
import SectionHeader from './components/SectionHeader.vue'
import TabBrief, { type Brief } from './components/TabBrief.vue'
import TabActions from './components/TabActions.vue'
import StatStrip, { type StatItem } from './components/StatStrip.vue'
import SkeletonBlock from './components/SkeletonBlock.vue'
import { useDrillDown } from './composables/useDrillDown'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'
import { chartPalette, themeColor } from '../utils/chartTheme'
import LaneTrack from './components/LaneTrack.vue'
import WaterfallRows from './components/WaterfallRows.vue'
import FlowSteps from './components/FlowSteps.vue'
import DateCalendar from './components/DateCalendar.vue'

/**
 * One open action on the tax control board (`JKM Action`, surfaced by
 * `insights.ml.india_tax_intelligence.control.get_action_queue`).
 *
 * `exposure` is the rupee figure the finding put at stake, not a provision.
 * `area` carries the *finding code* (`tax.missing_irn`), not a display name --
 * the same string the detector emits, which is why the matrix maps codes to
 * areas rather than comparing labels.
 */
interface QueueRow {
  name: string
  title: string
  action_key: string
  area: string
  priority: string
  status: string
  plan_state?: string
  owner_role?: string
  owner_type?: string
  exposure?: number
  due_date?: string
  due_in_days?: number
  overdue?: boolean
  age_days?: number
  assigned_to?: string
  rationale?: string
  steps?: string
}

/**
 * A matrix cell. `value` is `null` when the area has no data source on this
 * site, which the table renders as "not available" rather than as a zero --
 * an unmeasured reconciliation rate and a 0% one are opposite findings.
 */
interface MatrixCell {
  value: number | string | null
  note: string
  /** Which formatter the number needs. Absent on older payloads. */
  unit?: 'percent' | 'count' | 'currency' | 'text'
}

interface MatrixRow {
  area: string
  status: string
  reconciliation: MatrixCell
  filing: MatrixCell
  evidence: MatrixCell
  escalation: MatrixCell
  open_actions: number
  exposure: number | null
}

/** One week of the 13-week statutory outflow horizon. */
interface OutlookWeek {
  label: string
  week_start: string
  week_end: string
  gst: number
  tds: number
  legal: number
  total: number
  events?: { due_date: string; stream: string; label: string; amount: number }[]
}

/** Rows from insights.api.ml.tax.tax_intelligence gst_summary.
 * Only fields this view reads; the API may return more. */
interface GstSummaryRow {
  month: string
  cgst?: number
  sgst?: number
  igst?: number
  total_revenue?: number
}

/** Rows from tds_summary.payable_by_section. Only fields this view reads. */
interface TdsSectionRow {
  section: string
  amount: number
}

/** Rows from tax_forecast.forecast. Only fields this view reads. */
interface TaxForecastRow {
  month_offset: number
  projected_net_gst: number
}

/** Top-level shape of the tax_intelligence API response. */
interface TaxIntelligenceData {
  base_currency?: string
  generated_at?: string
  tab_briefs?: Record<string, Brief>
  net_gst?: number
  compliance_score?: number
  effective_tax_rate?: number
  total_tax?: number
  tax_revenue_ratio?: number
  itc_utilization?: number
  gst_summary?: GstSummaryRow[]
  itc_health?: Record<string, unknown>
  tds_summary?: { payable_by_section?: TdsSectionRow[]; total_payable?: number; receivable?: number; net_position?: number; [k: string]: unknown }
  einvoice_status?: Record<string, unknown>
  ewaybill_status?: Record<string, unknown>
  filing_compliance?: Record<string, unknown>
  reconciliation_score?: Record<string, unknown>
  hsn_summary?: Record<string, any>[]
  tax_forecast?: {
    forecast?: TaxForecastRow[]
    note?: string
    r_squared?: number | null
    months_used?: number
    [k: string]: unknown
  }
  advance_tax_schedule?: Record<string, any>[]
  einvoice_compliance_info?: Record<string, unknown>
  counterparty_risk?: Record<string, unknown>
  action_queue?: Record<string, unknown>
  legal_register?: Record<string, unknown>
  tax_cash_outlook?: Record<string, unknown>
  rcm_summary?: Record<string, unknown>
  pan_exceptions?: Record<string, unknown>
  customs_summary?: Record<string, unknown>
  /** A bare list of area rows, not an envelope. */
  compliance_matrix?: MatrixRow[]
  compliance_pulse?: Record<string, unknown>
  input_tax?: Record<string, unknown>[]
  [k: string]: unknown
}

const router = useRouter()

const drillDown = useDrillDown()
const TAX_ENDPOINT = 'insights.api.ml.tax.get_tax_detail'

const activeTabIndex = ref(0)
const dateFilter = ref('fy')

const dateRangeOptions = [
  { value: '3m', label: 'Last 3 Months' },
  { value: '6m', label: 'Last 6 Months' },
  { value: '12m', label: 'Last 12 Months' },
  { value: 'fy', label: 'Current FY' },
]

const dateParams = computed(() => ({ period: dateFilter.value }))

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
} =
  useIntelligenceDashboard<TaxIntelligenceData>({
    url: 'insights.api.ml.tax.tax_intelligence',
    params: dateParams,
    cache: 'tax-intelligence',
  })

/**
 * Eight control-tower views, ordered by how a review actually runs: what is
 * at stake (Overview), then the four tax streams, then the two registers
 * that hold unresolved matters, then the queue that owns them.
 *
 * `planning` kept its id when it became "Income Tax" so a bookmarked or
 * chat-linked tab index does not silently land somewhere else.
 */
const tabs = [
  { label: 'Overview' },
  { label: 'GST' },
  { label: 'Compliance' },
  { label: 'TDS & TCS' },
  { label: 'Income Tax' },
  { label: 'Notices & Legal' },
  { label: 'Customs' },
  { label: 'Action Queue' },
]

const TAB_IDS = [
  'overview', 'gst', 'compliance', 'tds', 'planning', 'legal', 'customs', 'actions',
] as const
const activeTab = computed(() => TAB_IDS[activeTabIndex.value] ?? 'overview')

const gstSummary = computed((): GstSummaryRow[] =>
  (data.value?.gst_summary ?? []) as unknown as GstSummaryRow[]
)
/** Output GST by month with its total and effective rate; the last row is the year to date. */
const gstTable = computed(() => {
  const row = (month: string, d: { cgst?: number; sgst?: number; igst?: number; total_revenue?: number }) => {
    const cgst = Number(d.cgst ?? 0)
    const sgst = Number(d.sgst ?? 0)
    const igst = Number(d.igst ?? 0)
    const total = cgst + sgst + igst
    const revenue = Number(d.total_revenue ?? 0)
    return { month, cgst, sgst, igst, total, rate: revenue > 0 ? `${((total / revenue) * 100).toFixed(1)}%` : NO_VALUE, revenue }
  }
  const rows = gstSummary.value.map((d) => row(d.month, d))
  const sum = (k: 'cgst' | 'sgst' | 'igst' | 'revenue') => rows.reduce((s, r) => s + r[k], 0)
  return { rows, ytd: row('YTD', { cgst: sum('cgst'), sgst: sum('sgst'), igst: sum('igst'), total_revenue: sum('revenue') }) }
})
const itcHealth = computed((): Record<string, any> => (data.value?.itc_health ?? {}) as Record<string, any>)
const tdsSummary = computed((): Record<string, any> => (data.value?.tds_summary ?? {}) as Record<string, any>)
/**
 * Section attribution is only possible when the GL account heads carry a
 * section number for `_TDS_SECTIONS` to match on. On a chart of accounts with
 * one undifferentiated `TDS Payable` head there is nothing to attribute, and
 * the Section / Rate columns rendered the account head a second time next to
 * a `-` rate. Drop those columns rather than print two empty ones; they come
 * back on their own the moment the heads are named per section.
 */
const tdsHasSections = computed(() =>
  ((tdsSummary.value.payable_by_section ?? []) as Record<string, any>[]).some((r) => !!r.section_code),
)
const einvoiceStatus = computed((): Record<string, any> => (data.value?.einvoice_status ?? {}) as Record<string, any>)
const ewaybillStatus = computed((): Record<string, any> => (data.value?.ewaybill_status ?? {}) as Record<string, any>)
const filingCompliance = computed((): Record<string, any> => (data.value?.filing_compliance ?? {}) as Record<string, any>)
const reconciliationScore = computed((): Record<string, any> => (data.value?.reconciliation_score ?? {}) as Record<string, any>)
const hsnSummary = computed((): Record<string, any>[] => (data.value?.hsn_summary ?? []) as Record<string, any>[])
const taxForecast = computed((): Record<string, any> => (data.value?.tax_forecast ?? {}) as Record<string, any>)
const advanceTaxSchedule = computed((): Record<string, any>[] => (data.value?.advance_tax_schedule ?? []) as Record<string, any>[])
const einvoiceInfo = computed((): Record<string, any> => (data.value?.einvoice_compliance_info ?? {}) as Record<string, any>)
const counterpartyRisk = computed((): Record<string, any> => (data.value?.counterparty_risk ?? {}) as Record<string, any>)

// --- control layer (see insights/ml/india_tax_intelligence/control.py) -------
// These answer "what do we owe, who owns it, and what closes it", as opposed
// to the measurement sections above.
const actionQueue = computed((): Record<string, any> => (data.value?.action_queue ?? {}) as Record<string, any>)
const queueRows = computed((): QueueRow[] => (actionQueue.value.rows ?? []) as QueueRow[])
const queueSummary = computed((): Record<string, any> => (actionQueue.value.summary ?? {}) as Record<string, any>)
/**
 * Queue breakdown rows, typed once here instead of cast inline in the
 * template. `v-for="x in (expr as { key: string; count: number }[])"` does not
 * parse: the compiler splits the v-for expression on its own before
 * TypeScript sees it, so each of the three inline casts reported five
 * TS1005 syntax errors -- 15 of them, the file's entire `vue-tsc` output.
 */
interface QueueBreakdownRow {
  key: string
  count: number
  exposure: number
}
const queueByOwnerRole = computed<QueueBreakdownRow[]>(
  () => (queueSummary.value.by_owner_role ?? []) as QueueBreakdownRow[],
)
const queueByPriority = computed<QueueBreakdownRow[]>(
  () => (queueSummary.value.by_priority ?? []) as QueueBreakdownRow[],
)
const legalRegister = computed((): Record<string, any> => (data.value?.legal_register ?? {}) as Record<string, any>)
const legalRows = computed((): Record<string, any>[] => (legalRegister.value.rows ?? []) as Record<string, any>[])
const legalSummary = computed((): Record<string, any> => (legalRegister.value.summary ?? {}) as Record<string, any>)
const cashOutlook = computed((): Record<string, any> => (data.value?.tax_cash_outlook ?? {}) as Record<string, any>)
const rcmSummary = computed((): Record<string, any> => (data.value?.rcm_summary ?? {}) as Record<string, any>)
/** Monthly TDS challans from the cash outlook; total is arithmetic on the rows. */
const tdsChallans = computed(() => {
  const rows = ((cashOutlook.value.tds_periods ?? []) as Record<string, any>[])
  return { rows, total: rows.reduce((s, r) => s + (asNumber(r.amount) ?? 0), 0) }
})
const panExceptions = computed((): Record<string, any> => (data.value?.pan_exceptions ?? {}) as Record<string, any>)
const panSummary = computed((): Record<string, any> => (panExceptions.value.summary ?? {}) as Record<string, any>)
const customsSummary = computed((): Record<string, any> => (data.value?.customs_summary ?? {}) as Record<string, any>)
const complianceMatrix = computed((): MatrixRow[] => (data.value?.compliance_matrix ?? []) as MatrixRow[])
const compliancePulse = computed((): Record<string, any> => (data.value?.compliance_pulse ?? {}) as Record<string, any>)

/**
 * Control-layer drill-downs. Each reads its own DocType rather than
 * re-deriving the section, so the panel and the tile cannot disagree.
 */
function openQueueDrillDown(area?: string) {
  drillDown.open(
    TAX_ENDPOINT,
    area ? `Open tax actions, ${area}` : 'Open tax actions',
    { metric: 'action_queue', area: area || undefined, period: dateFilter.value },
  )
}

function openLegalDrillDown() {
  drillDown.open(TAX_ENDPOINT, 'Notice, demand and legal cases', {
    metric: 'legal_cases',
    period: dateFilter.value,
  })
}

function openPanDrillDown() {
  drillDown.open(TAX_ENDPOINT, 'TDS suppliers with no PAN on file', {
    metric: 'tds_suppliers_no_pan',
    period: dateFilter.value,
  })
}

/**
 * Open the invoice drill-down scoped to one HSN code.
 *
 * The HSN has to go into the filters, not just the title. Passing only the
 * title listed all 825 taxed invoices under a heading naming a single HSN, so
 * the panel described something other than its contents.
 */
function openHsnDrillDown(hsn: { hsn_code?: string }) {
  const code = hsn.hsn_code || ''
  drillDown.open(TAX_ENDPOINT, code ? `Tax invoices, HSN ${code}` : 'Tax invoices', {
    metric: 'tax_invoices',
    hsn_code: code || undefined,
    // Same window as the dashboard, so the panel and the row it came from agree.
    period: dateFilter.value,
  })
}

// Status helpers routing through status vocabulary.
//
// Server vocabulary (`get_filing_compliance._status`): No Data | Not Due |
// Compliant | Overdue. `Filed` / `Pending` / `Not Tracked` are the older
// spellings from before the denominator became due-date aware, and still
// arrive here from payloads written by `cached_run` before that change.
function filingSeverity(status: string | undefined | null): Severity {
  const s = String(status ?? '')
  if (s === 'Filed' || s === 'Compliant' || s === 'Not Due') return 'none'
  if (s === 'Overdue') return 'high'
  if (s === 'Pending' || s === 'Due') return 'medium'
  return 'high'
}

/** Nothing is owed to the portal right now: filed, or not yet due. */
function filingClear(status: string | undefined | null): boolean {
  const s = String(status ?? '')
  return s === 'Filed' || s === 'Compliant' || s === 'Not Due'
}

function rateSeverity(rate: number | undefined | null): Severity {
  return scoreSeverity(rate, { good: 18, warn: 25, higherIsBetter: false })
}

function complianceSeverity(score: number | undefined | null): Severity {
  return scoreSeverity(score, { good: 80, warn: 60, higherIsBetter: true })
}

/**
 * A readiness figure wearing the severity colour, but not the severity word.
 * The word is shared vocabulary -- see `readinessLabel` for why the risk
 * words invert on a `higherIsBetter` score.
 *
 * Keep the risk words on genuinely risk-shaped figures (exposure at stake,
 * pending covers) and on the alert list, where "High" means high severity.
 */
function readinessBadge(score: number | undefined | null) {
  const severity = complianceSeverity(score)
  return { ...severityBadge(severity), label: readinessLabel(severity) }
}

function hsnRateSeverity(rate: number | undefined | null): Severity {
  return scoreSeverity(rate, { good: 18, warn: 25, higherIsBetter: false })
}


/**
 * Currency and grouping come from the payload.
 *
 * This hardcoded `en-IN` + `INR` and returned the literal `₹0` for a missing
 * value, left over from before this surface was retargeted. The endpoint sends
 * `base_currency` (tax_intelligence.py:119), and the company on this site
 * reports in a currency the page never consulted, so every tax figure was
 * labelled by a constant rather than by the ledger.
 */
const baseCurrency = computed<string | null>(() => data.value?.base_currency ?? null)

function formatCurrency(value: number | null | undefined): string {
  return formatMoney(value, baseCurrency.value)
}
function formatNumber(value: number | null | undefined): string { return formatCount(value) }
function formatPercent(value: number | null | undefined): string { return sharedPercent(value) }

/**
 * GST return periods arrive as the portal's `MMYYYY` (`122026`), which is
 * what GSTR-1 and GSTR-3B are keyed by. Rendered verbatim it read "Latest
 * period on record: 122026" -- a six-digit number that looks like an ID, or
 * worse like a year. Anything that is not exactly `MMYYYY` is passed through
 * untouched rather than guessed at.
 */
function formatReturnPeriod(period: string | null | undefined): string {
  const s = String(period ?? '')
  let month = 0
  let year = 0
  if (/^\d{6}$/.test(s)) {
    // The portal's own spelling, as stored on GST Return Log.
    month = Number(s.slice(0, 2))
    year = Number(s.slice(2))
  } else if (/^\d{4}-\d{2}$/.test(s)) {
    // `due_through`, derived server-side from the statutory due day.
    year = Number(s.slice(0, 4))
    month = Number(s.slice(5))
  } else {
    return s
  }
  if (month < 1 || month > 12) return s
  return new Date(year, month - 1, 1).toLocaleDateString('en-KE', {
    month: 'short',
    year: 'numeric',
  })
}

/**
 * Coverage-matrix status vocabulary, mapped to the shared severity scale.
 *
 * `No Activity` and `Not Available` are deliberately `none`, not `low`: an
 * area with nothing in it is neither healthy nor failing, and colouring it
 * green would tell a reviewer that import tax is under control on a site
 * that has never recorded a Bill of Entry.
 */
const MATRIX_SEVERITY: Record<string, Severity> = {
  Clear: 'low',
  Healthy: 'low',
  'On Track': 'low',
  'Under Control': 'medium',
  Pending: 'medium',
  'Action Required': 'high',
  'At Risk': 'critical',
  'No Activity': 'none',
  'Not Available': 'none',
  Unknown: 'none',
}

function matrixSeverity(status: string | undefined | null): Severity {
  return MATRIX_SEVERITY[String(status ?? '')] ?? 'none'
}

/** One matrix cell. The server sends `{ value, note, unit }`, `value: null`
 * meaning "no measurement", which the template renders as text rather than a
 * zero. */
function matrixCell(row: MatrixRow, key: string): MatrixCell {
  const cell = (row as unknown as Record<string, MatrixCell>)[key]
  return cell ?? { value: null, note: '' }
}

/**
 * Cell text. The columns are deliberately heterogeneous -- the reconciliation
 * column is a match-rate percentage for GST, a row count for ITC and a rupee
 * amount for TDS -- so the unit travels with the value. Formatting every
 * number as a percentage read 1,838 unactioned rows as `1,838.0%`.
 *
 * Strings carry their own unit already (`3/12 GSTR-3B`, an owner role), so
 * they are passed through untouched.
 *
 * An unknown or missing unit falls back to a plain number, not a percentage:
 * a cached payload written before `unit` existed still has to render, and a
 * bare figure is merely less informative where a `%` on a rupee amount is
 * false.
 */
function matrixCellText(row: MatrixRow, key: string): string {
  const cell = matrixCell(row, key)
  if (typeof cell.value !== 'number') return String(cell.value ?? '')
  switch (cell.unit) {
    case 'percent':
      return formatPercent(cell.value)
    case 'currency':
      return formatCurrency(cell.value)
    default:
      return formatNumber(cell.value)
  }
}

/** Output GST to net GST, then the ITC at risk, one coloured bar each (the mock's GST Cash Bridge). */
const gstBridgeConfig = computed(() => {
  const steps = [
    { key: 'Output GST', row: gstWaterfall.value[0], color: themeColor('--app-accent-strong') },
    { key: 'Less ITC', row: gstWaterfall.value[1], color: themeColor('--app-pos-fill') },
    { key: 'Net GST', row: gstWaterfall.value[2], color: themeColor('--app-accent-strong') },
    { key: 'ITC at risk', row: gstWaterfall.value[3], color: themeColor('--app-neg-fill') },
  ]
  if (steps.every((s) => s.row.amount == null)) return null
  return {
    data: steps.map((s) => Object.fromEntries([['step', s.key], ...steps.map((o) => [o.key, o === s ? Number(s.row.amount ?? 0) : 0])])),
    title: '',
    xAxis: { key: 'step', type: 'category' as const },
    yAxis: { title: 'Amount (INR)' },
    stacked: true,
    series: steps.map((s) => ({ name: s.key, type: 'bar' as const, color: s.color })),
  }
})

const tdsBarConfig = computed(() => {
  // Cast once: payable_by_section is an untyped API payload array.
  const sections: TdsSectionRow[] = ((tdsSummary.value.payable_by_section ?? []) as unknown as TdsSectionRow[]).slice(0, 5)
  // A bar chart's whole job is comparison. One head means one bar restating
  // the `TDS Payable` KPI directly above it at chart size, so there is
  // nothing to compare and the panel is decoration.
  if (sections.length < 2) return null
  return {
    data: sections.map((s: TdsSectionRow) => ({ section: s.section, TDS: s.amount })),
    title: '',
    xAxis: { key: 'section', type: 'category' as const },
    yAxis: { title: 'TDS (INR)' },
    series: [
      { name: 'TDS', type: 'bar' as const, color: themeColor('--app-accent') },
    ],
  }
})

const effectiveRateTrendConfig = computed(() => {
  if (!gstSummary.value.length) return null
  return {
    data: gstSummary.value.map((d: GstSummaryRow) => {
      const totalTax = (d.cgst ?? 0) + (d.sgst ?? 0) + (d.igst ?? 0)
      return {
        month: d.month,
        'Rate %': (d.total_revenue ?? 0) > 0
          ? +(totalTax / d.total_revenue! * 100).toFixed(2)
          : 0,
      }
    }),
    title: '',
    xAxis: { key: 'month', type: 'category' as const },
    yAxis: { title: 'Rate %' },
    series: [
      { name: 'Rate %', type: 'area' as const, color: themeColor('--app-accent'), fillOpacity: 0.2 },
    ],
  }
})

const taxForecastConfig = computed(() => {
  // Cast once: forecast is an untyped API payload array.
  const forecast: TaxForecastRow[] = (taxForecast.value.forecast ?? []) as unknown as TaxForecastRow[]
  if (!forecast.length) return null
  return {
    data: forecast.map((f: TaxForecastRow) => ({
      period: `Month +${f.month_offset}`,
      'Net GST': f.projected_net_gst,
    })),
    title: '',
    xAxis: { key: 'period', type: 'category' as const },
    yAxis: { title: 'Predicted Net GST (INR)' },
    series: [
      { name: 'Net GST', type: 'line' as const, color: themeColor('--app-accent-strong') },
    ],
  }
})

/**
 * What the forecast line is worth, in words. Two things a dashed line through
 * three future points does not say on its own:
 *
 * - How well the fit describes the months it was built from. `r_squared` is
 *   the share of month-to-month variance the straight line accounts for; at
 *   0.4 the line is a shrug, and the reader should be told so rather than
 *   left to assume a trend exists.
 * - What a projection below zero means. Net GST is output tax less input
 *   credit, so a negative figure is credit carried forward, not a refund
 *   cheque. Left unexplained it reads as money coming back.
 */
const taxForecastCaveat = computed((): string | null => {
  const parts: string[] = []
  const r2 = taxForecast.value.r_squared
  if (Number.isFinite(r2)) {
    parts.push(
      `The line accounts for ${sharedPercent((r2 as number) * 100, 0)} of the month-to-month variation.`,
    )
  }
  const forecast = (taxForecast.value.forecast ?? []) as unknown as TaxForecastRow[]
  if (forecast.some((f) => f.projected_net_gst < 0)) {
    parts.push(
      'A projection below zero is an expected net credit position (input credit above output tax), carried forward, not a refund.',
    )
  }
  return parts.length ? parts.join(' ') : null
})

const ytdRevenue = computed(() =>
  gstSummary.value.reduce((s: number, d: GstSummaryRow) => s + (d.total_revenue || 0), 0)
)
const ytdOutputGst = computed(() =>
  gstSummary.value.reduce((s: number, d: GstSummaryRow) => s + (d.cgst || 0) + (d.sgst || 0) + (d.igst || 0), 0)
)

/**
 * 13-week statutory outflow. Stacked by stream rather than shown as one
 * total, because the three streams are paid on different dates to different
 * authorities and are funded from different approvals: a ₹0.3M week that is
 * all GST and a ₹0.3M week that is all a legal demand are not the same
 * problem, and the total alone hides which.
 */
const cashOutlookConfig = computed(() => {
  const weeks = (cashOutlook.value.weeks ?? []) as OutlookWeek[]
  if (!weeks.length) return null
  const palette = chartPalette(3)
  return {
    data: weeks.map((w) => ({
      week: w.label,
      GST: w.gst ?? 0,
      'TDS / TCS': w.tds ?? 0,
      Legal: w.legal ?? 0,
    })),
    title: '',
    xAxis: { key: 'week', type: 'category' as const },
    yAxis: { title: `Outflow (${baseCurrency.value ?? ''})` },
    stacked: true,
    series: [
      { name: 'GST', type: 'bar' as const, color: palette[0] },
      { name: 'TDS / TCS', type: 'bar' as const, color: palette[1] },
      { name: 'Legal', type: 'bar' as const, color: palette[2] },
    ],
  }
})

const outlookWeeks = computed((): OutlookWeek[] => (cashOutlook.value.weeks ?? []) as OutlookWeek[])
const outlookOverdue = computed((): Record<string, any> => (cashOutlook.value.overdue ?? {}) as Record<string, any>)

/**
 * Readiness breakdown beside the pulse ring.
 *
 * Percentages are of `open_items`, so the four rows describe the same
 * denominator the ring's score is about. `on_track` is what is neither
 * overdue nor due within the week -- the server's own split, not a
 * subtraction done here.
 */
const pulseBreakdown = computed(() => {
  const p = compliancePulse.value
  const open = asNumber(p.open_items) ?? 0
  const pct = (n: number) => (open > 0 ? (n / open) * 100 : undefined)
  const overdue = asNumber(p.overdue) ?? 0
  const dueSoon = asNumber(p.due_soon) ?? 0
  const onTrack = asNumber(p.on_track) ?? 0
  const unassigned = asNumber(p.unassigned) ?? 0
  return [
    { label: 'On track', value: formatNumber(onTrack), severity: 'low' as Severity, pct: pct(onTrack) },
    { label: 'Due within 7 days', value: formatNumber(dueSoon), severity: 'medium' as Severity, pct: pct(dueSoon) },
    { label: 'Overdue', value: formatNumber(overdue), severity: 'critical' as Severity, pct: pct(overdue) },
    {
      label: 'No owner assigned',
      value: formatNumber(unassigned),
      severity: (unassigned > 0 ? 'high' : 'none') as Severity,
      pct: pct(unassigned),
    },
  ]
})

/**
 * How the net GST cash number is arrived at.
 *
 * Input tax is derived as output minus the headline `net_gst` rather than
 * summed from `input_tax` independently. Two additions of the same ledger
 * that round differently would put a waterfall on screen that does not add
 * up to the KPI directly above it, and the reader has no way to tell which
 * of the two is the real number.
 */
const gstWaterfall = computed(() => {
  const output = ytdOutputGst.value
  const net = asNumber(data.value?.net_gst)
  const input = net === undefined ? null : output - net
  const atRisk = asNumber(itcHealth.value.at_risk_supplier_unfiled) ?? null
  return [
    { label: 'Output tax on sales', amount: output, direction: 'neutral' as const },
    { label: 'Less: input tax credit', amount: input, direction: 'negative' as const },
    { label: 'Net GST payable', amount: net ?? null, direction: 'neutral' as const },
    {
      label: 'Of which ITC is at risk (supplier unfiled)',
      amount: atRisk,
      direction: 'negative' as const,
    },
  ]
})

/**
 * Reconciliation lanes, all four on counts rather than amounts.
 *
 * `LaneTrack` legends its segments as row counts, so feeding it rupees would
 * print an unlabelled bare number where the reader expects a quantity. The
 * amounts for these same streams are on the tiles above and in the
 * waterfall.
 *
 * Denominators are passed explicitly where the stream has rows outside the
 * three states: e-Waybill counts 455 `Not Applicable` invoices below the
 * movement threshold, and including them would report coverage of 39% for a
 * stream that is actually 99% covered on the invoices that need one. Filing
 * is the same shape -- the window logs 12 GSTR-1 periods but only 4 have
 * reached their statutory due date, and the other 8 are not yet owed. Both
 * lanes must use the same denominator the compliance score uses, or the
 * track and the headline disagree on the same page.
 */
const reconciliationLanes = computed(() => {
  const g1 = (filingCompliance.value.gstr1 ?? {}) as Record<string, any>
  const r = reconciliationScore.value
  const ei = einvoiceStatus.value
  const ew = ewaybillStatus.value
  const ewApplicable = (asNumber(ew.total) ?? 0) - (asNumber(ew.not_applicable) ?? 0)
  return [
    {
      key: 'gstr1',
      label: 'GSTR-1 return periods filed',
      matched: asNumber(g1.filed_due) ?? 0,
      pending: asNumber(g1.pending) ?? 0,
      issue: asNumber(g1.overdue) ?? 0,
      total: asNumber(g1.due),
      note: g1.due_through
        ? `Periods due through ${formatReturnPeriod(g1.due_through)}; latest logged ${formatReturnPeriod(g1.latest_period)}`
        : undefined,
    },
    {
      key: 'recon',
      label: 'Purchase rows vs GSTR-2A/2B',
      matched: asNumber(r.matched_count) ?? 0,
      pending: asNumber(r.unactioned_count) ?? 0,
      issue: asNumber(r.mismatch_count) ?? 0,
      total: asNumber(r.total_count),
      note: r.data_through
        ? `Portal data imported through ${formatDate(r.data_through)}`
        : 'No 2A/2B data imported',
    },
    {
      key: 'irn',
      label: 'e-Invoice IRN, invoices that need one',
      matched: asNumber(ei.filed) ?? 0,
      pending: asNumber(ei.pending) ?? 0,
      issue: asNumber(ei.failed) ?? 0,
      total: asNumber(ei.total),
      note: `${formatNumber(ei.exempt)} exempt invoices excluded from the denominator`,
    },
    {
      key: 'ewaybill',
      label: 'e-Waybill, invoices above the movement threshold',
      matched: asNumber(ew.active) ?? 0,
      pending: asNumber(ew.pending) ?? 0,
      issue: asNumber(ew.failed) ?? 0,
      total: ewApplicable > 0 ? ewApplicable : 0,
      note: `${formatNumber(ew.not_applicable)} below-threshold invoices excluded`,
    },
  ]
})

/**
 * The statutory calendar: filing dates, challan dates and planning markers
 * on one timeline, sorted by date.
 *
 * A filed period stays on the calendar rather than being filtered out. The
 * question this screen answers is "is the period closed", and a filed
 * GSTR-3B with unreconciled credit is not closed -- dropping it would make
 * the gap invisible exactly where it is being looked for.
 */
const complianceCalendar = computed(() => {
  const gst = (cashOutlook.value.gst_periods ?? []) as Record<string, any>[]
  const tds = (cashOutlook.value.tds_periods ?? []) as Record<string, any>[]
  const markers = (cashOutlook.value.markers ?? []) as Record<string, any>[]
  const rows: {
    date: string
    title: string
    meta?: string
    status?: string
    severity?: Severity
  }[] = []

  for (const p of gst) {
    const filed = String(p.filing_state ?? '') === 'filed'
    rows.push({
      date: String(p.due_date ?? ''),
      title: `GSTR-3B ${p.period}`,
      meta: `Net payable ${formatCurrency(asNumber(p.net_payable))}`,
      status: p.overdue ? 'Overdue' : filed ? 'Filed' : 'Due',
      severity: p.overdue ? 'critical' : filed ? 'low' : 'medium',
    })
  }
  for (const p of tds) {
    rows.push({
      date: String(p.due_date ?? ''),
      title: `TDS challan ${p.period}`,
      meta: `Deducted ${formatCurrency(asNumber(p.amount))}`,
      status: p.overdue ? 'Overdue' : 'Due',
      severity: p.overdue ? 'critical' : 'medium',
    })
  }
  for (const m of markers) {
    const amount = asNumber(m.amount)
    rows.push({
      date: String(m.due_date ?? ''),
      title: String(m.label ?? ''),
      // The server sends `reason` precisely when it could not price the
      // instalment. Showing the reason instead of a zero is the difference
      // between "nothing due" and "nobody has estimated it yet".
      meta: amount === undefined ? String(m.reason ?? 'Not estimated') : formatCurrency(amount),
      status: `${m.cumulative_pct}% cumulative`,
      severity: 'none',
    })
  }
  return rows.sort((a, b) => a.date.localeCompare(b.date))
})

/** Statutory reply and hearing dates from the legal register. */
const legalCalendar = computed(() =>
  legalRows.value
    .map((c) => ({
      date: String(c.statutory_reply_date ?? c.hearing_date ?? c.internal_target_date ?? ''),
      title: String(c.title ?? c.name ?? ''),
      meta: [c.case_type, c.authority, formatCurrency(asNumber(c.total_exposure))]
        .filter(Boolean)
        .join(' · '),
      status: String(c.status ?? ''),
      severity: prioritySeverity(c.risk_level as string) as Severity,
    }))
    .filter((r) => r.date)
    .sort((a, b) => a.date.localeCompare(b.date)),
)

const tdsControlFlow = [
  {
    label: '1. Source bill',
    title: 'Supplier or service expense',
    detail: 'Tax section, rate, PAN and supplier master checked before the bill is booked.',
  },
  {
    label: '2. Liability',
    title: 'Deducted and payable',
    detail: 'Payment schedule and challan reference planned against the deduction.',
  },
  {
    label: '3. Return and proof',
    title: 'Filed and reconciled',
    detail: 'Challan, return, certificate and exception closure linked to the deduction.',
  },
]

const importControlFlow = [
  {
    label: '1. Shipment',
    title: 'PO, supplier, item',
    detail: 'Commercial invoice, shipment reference and expected landed cost.',
  },
  {
    label: '2. Customs',
    title: 'Bill of Entry and duty',
    detail: 'Duty, surcharge, import IGST and proof of payment.',
  },
  {
    label: '3. ERPNext',
    title: 'Landed cost and ITC',
    detail: 'Purchase invoice, cost allocation and credit reconciliation.',
  },
]

/**
 * Chat context. The control layer is included because the questions this
 * dashboard now invites -- "what is overdue", "who owns the ITC gap" -- are
 * answerable only from the queue and the registers, and a chat that can see
 * the measurements but not the open actions confidently answers "nothing is
 * outstanding" while five actions sit on the board.
 */
const chatContext = computed(() => ({
  summary: { net_gst: data.value?.net_gst, effective_tax_rate: data.value?.effective_tax_rate, compliance_score: data.value?.compliance_score },
  gst_summary: gstSummary.value, itc_health: itcHealth.value, tds_summary: tdsSummary.value,
  einvoice_status: einvoiceStatus.value, ewaybill_status: ewaybillStatus.value,
  filing_compliance: filingCompliance.value, reconciliation_score: reconciliationScore.value,
  hsn_summary: hsnSummary.value, tax_forecast: taxForecast.value,
  action_queue: { summary: queueSummary.value, rows: queueRows.value },
  legal_register: { summary: legalSummary.value, rows: legalRows.value },
  compliance_pulse: compliancePulse.value,
  compliance_matrix: complianceMatrix.value,
  tax_cash_outlook: {
    total_horizon: cashOutlook.value.total_horizon,
    peak_week: cashOutlook.value.peak_week,
    peak_amount: cashOutlook.value.peak_amount,
    overdue: outlookOverdue.value,
    basis: cashOutlook.value.basis,
  },
  rcm_summary: rcmSummary.value,
  pan_exceptions: panSummary.value,
  customs_summary: customsSummary.value,
  activeTab: activeTab.value, date_filter: dateFilter.value,
}))

function handleDashboardRedirect(target: string) {
  const routes: Record<string, string> = {
    Sales: '/sales-intelligence', Risk: '/risk-intelligence', Inventory: '/inventory-intelligence',
    Financial: '/financial-intelligence', Customer: '/customer-intelligence',
    Procurement: '/procurement-intelligence', Tax: '/tax-intelligence',
  }
  if (routes[target]) router.push(routes[target])
}

// ── Variant B Overview helpers ────────────────────────────────────────────────

/** Amount due in W1 of the 13-week outlook (may be 0). */
const w1Amount = computed((): number => {
  const weeks = (cashOutlook.value.weeks ?? []) as OutlookWeek[]
  return weeks[0]?.total ?? 0
})

/** Short label for the W1 event (e.g. "GSTR-3B 2026-09 · 20 Oct"). */
const w1SublabelText = computed((): string | null => {
  const weeks = (cashOutlook.value.weeks ?? []) as OutlookWeek[]
  const events = (weeks[0]?.events ?? []) as { due_date: string; stream: string; label: string; amount: number }[]
  if (!events.length) return null
  const e = events[0]
  const d = e.due_date ? new Date(e.due_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : ''
  return [e.label, d].filter(Boolean).join(' · ')
})

/** "FY 2026-27 · Apr–Sep 2026 closed" context label for the header. */
const fyContextLabel = computed((): string => {
  const fy = (data.value as Record<string, any>)?.fiscal_year as Record<string, any> | undefined
  const fyName = fy?.start_date && fy?.end_date
    ? `FY ${String(fy.start_date).slice(0, 4)}-${String(fy.end_date).slice(2, 4)}`
    : fy?.name ? String(fy.name) : ''
  const months = gstSummary.value
  if (!months.length) return fyName
  const ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const fmt = (m: string) => { const [, mo] = m.split('-'); return ABBR[Number(mo) - 1] ?? '' }
  const first = months[0].month
  const last = months[months.length - 1].month
  const range = first === last ? fmt(first) : `${fmt(first)}–${fmt(last)}`
  return [fyName, `${range} closed`].filter(Boolean).join(' · ')
})

/** Month abbreviations (zero-indexed). */
const _MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** GSTR-3B 12-month dot calendar derived from gst_periods + FY start. */
const gstr3bDots = computed((): { key: string; label: string; status: 'filed' | 'overdue' | 'pending' | 'unknown' }[] => {
  const periodMap: Record<string, 'filed' | 'overdue' | 'pending' | 'unknown'> = {}
  for (const p of (cashOutlook.value.gst_periods ?? []) as Record<string, any>[]) {
    const period = String(p.period ?? '')
    if (p.filing_state === 'filed') periodMap[period] = 'filed'
    else if (p.overdue) periodMap[period] = 'overdue'
    else if (p.filing_state === 'not_filed' || p.filing_state === 'not_logged') periodMap[period] = 'pending'
    else periodMap[period] = 'unknown'
  }
  const fy = (data.value as Record<string, any>)?.fiscal_year as Record<string, any> | undefined
  const fyStartStr = fy?.year_start_date ? String(fy.year_start_date) : null
  if (!fyStartStr) return []
  const [fyY, fyM] = fyStartStr.split('-').map(Number)
  return Array.from({ length: 12 }, (_, i) => {
    let m = fyM + i; let y = fyY
    if (m > 12) { m -= 12; y++ }
    const key = `${y}-${String(m).padStart(2, '0')}`
    return { key, label: _MONTH_ABBR[m - 1] ?? '', status: periodMap[key] ?? 'unknown' }
  })
})

/**
 * CSS background class for a GSTR-3B dot. Returns a static string per
 * status so Tailwind's scanner sees every class as a literal.
 */
function dotStatusClass(status: string): string {
  if (status === 'filed') return 'bg-surface-green-2'
  if (status === 'overdue') return 'bg-surface-red-2'
  if (status === 'pending') return 'bg-surface-amber-2'
  return 'bg-surface-gray-2'
}

interface FilingStatusRow { label: string; value: string; status: string; severity: Severity }

/** Compact filing status rows for the Overview control-room panel (col 1). */
const overviewFilingRows = computed<FilingStatusRow[]>(() => {
  const g1 = (filingCompliance.value.gstr1 ?? {}) as Record<string, any>
  const g3 = (filingCompliance.value.gstr3b ?? {}) as Record<string, any>
  const loggedAll = (filingCompliance.value.logged_all_time ?? []) as Record<string, any>[]
  const gstr2b = loggedAll.find((r) => r.return_type === 'GSTR2b')
  const rows: FilingStatusRow[] = [
    {
      label: 'GSTR-1',
      value: `${g1.filed ?? '-'}/${g1.total ?? '-'}`,
      status: (g1.overdue ?? 0) > 0 ? `${g1.overdue} OVERDUE` : (g1.status ?? '-'),
      severity: filingSeverity(g1.status),
    },
    {
      label: 'GSTR-3B',
      value: `${g3.filed ?? '-'}/${g3.total ?? '-'}`,
      status: (g3.overdue ?? 0) > 0 ? `${g3.overdue} OVERDUE` : (g3.status ?? '-'),
      severity: filingSeverity(g3.status),
    },
  ]
  if (gstr2b) {
    rows.push({ label: 'GSTR-2B', value: `${gstr2b.count ?? '-'} logged`, status: 'Partial', severity: 'medium' })
  }
  rows.push(
    {
      label: 'e-Invoice',
      value: `${einvoiceStatus.value.filed ?? '-'}/${einvoiceStatus.value.total ?? '-'}`,
      status: (einvoiceStatus.value.coverage_pct ?? 0) >= 100 ? '100%' : `${Math.round(einvoiceStatus.value.coverage_pct ?? 0)}%`,
      severity: filingSeverity((einvoiceStatus.value.coverage_pct ?? 0) >= 100 ? 'Compliant' : 'Pending'),
    },
    {
      label: 'e-Waybill',
      value: `${formatNumber(ewaybillStatus.value.active)} active`,
      status: (ewaybillStatus.value.pending ?? 0) > 0 ? `${ewaybillStatus.value.pending} Pending` : 'Active',
      severity: (ewaybillStatus.value.pending ?? 0) > 0 ? 'medium' : 'none',
    },
    {
      label: 'TDS Challan',
      value: formatCurrency(asNumber(tdsSummary.value.total_payable)),
      status: 'Payable',
      severity: 'none',
    },
  )
  return rows
})

/** 2A/2B reconciliation table for the GST tab; counts and amounts straight from the payload. */
const reconTable = computed(() => {
  const r = reconciliationScore.value
  const row = (label: string, k: string) => ({ label, count: asNumber(r[`${k}_count`]), amount: asNumber(r[`${k}_amount`]) })
  return [
    { ...row('Matched', 'matched'), severity: 'low' as Severity },
    { ...row('Suggested', 'suggested'), severity: 'medium' as Severity },
    { ...row('Mismatch', 'mismatch'), severity: 'high' as Severity },
    { ...row('Unmatched', 'unmatched'), severity: 'none' as Severity },
  ]
})

/** Reconciliation breakdown for col 3 score panel. */
const reconRows = computed(() => [
  { label: 'Matched', count: reconciliationScore.value.matched_count as number | undefined },
  { label: 'Suggested', count: reconciliationScore.value.suggested_count as number | undefined },
  { label: 'Unmatched', count: reconciliationScore.value.unmatched_count as number | undefined },
  { label: 'Unactioned', count: reconciliationScore.value.unactioned_count as number | undefined },
])

/** Counterparty risk rows for col 3. */
const counterpartyRows = computed(() => [
  { label: 'Active in registry', value: formatNumber(counterpartyRisk.value.active), ink: '' },
  { label: 'Cancelled', value: formatNumber(counterpartyRisk.value.cancelled), ink: (counterpartyRisk.value.cancelled ?? 0) > 0 ? 'text-ink-red-4' : '' },
  { label: 'Suspended', value: formatNumber(counterpartyRisk.value.suspended), ink: '' },
  { label: 'Blocked', value: formatNumber(counterpartyRisk.value.blocked), ink: (counterpartyRisk.value.blocked ?? 0) > 0 ? 'text-ink-red-4' : '' },
])

/** ITC utilisation rows for col 2. */
const itcRows = computed(() => [
  { label: 'Accrued', amount: asNumber(itcHealth.value.accrued), ink: '' },
  { label: 'Utilised', amount: asNumber(itcHealth.value.utilised), ink: '' },
  { label: 'Balance', amount: asNumber(itcHealth.value.balance), ink: '' },
  { label: 'At risk (unfiled supplier)', amount: asNumber(itcHealth.value.at_risk_supplier_unfiled), ink: (asNumber(itcHealth.value.at_risk_supplier_unfiled) ?? 0) > 0 ? 'text-ink-red-4' : '' },
])

/** % of accrued ITC that is at risk (unfiled supplier). */
const itcAtRiskPct = computed((): number => {
  const accrued = asNumber(itcHealth.value.accrued) ?? 0
  const atRisk = asNumber(itcHealth.value.at_risk_supplier_unfiled) ?? 0
  return accrued > 0 ? Math.round((atRisk / accrued) * 100 * 10) / 10 : 0
})

const tabBriefs = computed(() => data.value?.tab_briefs ?? {})
const withCount = (n: unknown, text: string) => (typeof n === 'number' ? `${n.toLocaleString('en-US')} ${text}` : undefined)
const monthLabel = (m: string) => new Date(`${m}-01T00:00:00`).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
/** Months the Output GST table covers, straight from the payload rows. */
const gstPeriod = computed(() => {
  const r = gstSummary.value
  return r.length ? `${monthLabel(r[0].month)} to ${monthLabel(r[r.length - 1].month)}` : null
})

/** GSTR-1, GSTR-3B, e-Invoice IRN and e-Waybill as one progress list; every figure is a payload field or a ratio of two. */
const gstFilingRows = computed(() => {
  const returnRow = (key: string, name: string, r: Record<string, any> = {}) => {
    const due = asNumber(r.due) ?? 0
    const filed = asNumber(r.filed_due) ?? 0
    const overdue = asNumber(r.overdue) ?? 0
    return {
      key,
      title: `${name} (periods due through ${r.due_through ? monthLabel(String(r.due_through)) : NO_VALUE})`,
      chip: overdue > 0 ? `${overdue} overdue` : String(r.status || 'No Data'),
      severity: filingSeverity(r.status),
      pct: due > 0 ? (filed / due) * 100 : null,
      note: due > 0 ? `${filed} of ${due} filed.` : 'No periods due in this window.',
    }
  }
  const ei = einvoiceStatus.value
  const ew = ewaybillStatus.value
  const applicable = (asNumber(ew.total) ?? 0) - (asNumber(ew.not_applicable) ?? 0)
  const issues = (asNumber(ew.pending) ?? 0) + (asNumber(ew.failed) ?? 0)
  return [
    returnRow('gstr1', 'GSTR-1', filingCompliance.value.gstr1),
    returnRow('gstr3b', 'GSTR-3B', filingCompliance.value.gstr3b),
    {
      key: 'einvoice',
      title: `e-Invoice IRN (${formatNumber(ei.total)} eligible invoices)`,
      chip: (ei.coverage_pct ?? 0) >= 100 ? 'Covered' : 'Gap',
      severity: ((ei.coverage_pct ?? 0) >= 100 ? 'none' : 'medium') as Severity,
      pct: asNumber(ei.coverage_pct),
      note: `${formatNumber(ei.exempt)} exempt invoices excluded. ${formatNumber(ei.pending)} pending, ${formatNumber(ei.failed)} failed.`,
    },
    {
      key: 'ewaybill',
      title: `e-Waybill (${formatNumber(applicable)} applicable)`,
      chip: issues > 0 ? `${issues} to resolve` : 'Clear',
      severity: (issues > 0 ? 'medium' : 'none') as Severity,
      pct: applicable > 0 ? ((asNumber(ew.active) ?? 0) / applicable) * 100 : null,
      note: `${formatNumber(ew.not_applicable)} not applicable. ${formatNumber(ew.pending)} pending, ${formatNumber(ew.failed)} failed.`,
    },
  ]
})

/** Footnote under the cash bridge: the ITC balance and what is left once the at-risk credit is set aside. */
const gstBridgeNote = computed(() => {
  const bal = asNumber(itcHealth.value.balance)
  if (bal == null) return null
  const risk = asNumber(itcHealth.value.at_risk_supplier_unfiled) ?? 0
  return `ITC balance ${formatCurrency(bal)} after utilisation (${formatPercent(itcHealth.value.utilization_pct)} used). Balance less ITC at risk: ${formatCurrency(bal - risk)}.`
})
const SCORE_TONE: Record<string, StatItem['tone']> = { none: 'pos', low: 'pos', medium: 'warn', high: 'neg', critical: 'neg' }
const scoreTone = (score: number | null | undefined): StatItem['tone'] =>
  score == null ? undefined : SCORE_TONE[complianceSeverity(score)]
const gstStrip = computed<StatItem[]>(() => [
  { label: 'Net GST', amount: data.value?.net_gst ?? null, sublabel: gstPeriod.value ? `Net payable, ${gstPeriod.value}` : undefined },
  { label: 'ITC At Risk', amount: itcHealth.value.at_risk_supplier_unfiled ?? null, sublabel: withCount(itcHealth.value.at_risk_invoice_count, 'invoices'), tone: (asNumber(itcHealth.value.at_risk_supplier_unfiled) ?? 0) > 0 ? 'neg' : undefined },
  { label: 'e-Invoice Coverage', percent: einvoiceStatus.value.coverage_pct ?? null, sublabel: `${einvoiceStatus.value.filed ?? '-'} of ${einvoiceStatus.value.total ?? '-'} with IRN`, tone: scoreTone(einvoiceStatus.value.coverage_pct) },
  { label: 'Recon Match Rate', percent: reconciliationScore.value.match_rate_pct ?? null, sublabel: withCount(reconciliationScore.value.unactioned_count, 'rows unactioned'), tone: scoreTone(reconciliationScore.value.match_rate_pct) },
])
const complianceStrip = computed<StatItem[]>(() => {
  const score = data.value?.compliance_score
  return [
    { label: 'Compliance Score', value: score == null ? null : Math.round(score * 10) / 10, unit: '/100' },
    { label: 'Open Actions', value: compliancePulse.value.open_items ?? null },
    { label: 'Overdue Actions', value: compliancePulse.value.overdue ?? null },
    { label: 'Total Exposure', amount: compliancePulse.value.exposure ?? null, sublabel: 'all open action items' },
  ]
})
const tdsStrip = computed<StatItem[]>(() => [
  { label: 'TDS Payable', amount: tdsSummary.value.total_payable ?? null },
  { label: 'RCM Gap', amount: rcmSummary.value.gap ?? null, sublabel: 'books vs portal' },
  { label: 'TDS Receivable', amount: tdsSummary.value.receivable ?? null },
  { label: 'PAN Exceptions', value: panSummary.value.suppliers_missing_pan ?? null },
])
const nextInstalment = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  for (const s of advanceTaxSchedule.value) {
    const d = new Date(s.due_date)
    if (d >= today) return { s, days: Math.round((d.getTime() - today.getTime()) / 86400000) }
  }
  return null
})
const planningStrip = computed<StatItem[]>(() => {
  const r2 = taxForecast.value.r_squared
  return [
    { label: 'Next Instalment', value: nextInstalment.value?.s.due_date ?? null, sublabel: nextInstalment.value ? `${nextInstalment.value.s.label}, cumulative ${nextInstalment.value.s.cumulative_pct}%` : undefined },
    { label: 'Days Remaining', value: nextInstalment.value?.days ?? null },
    { label: 'GST Forecast R²', value: typeof r2 === 'number' ? Math.round(r2 * 100) / 100 : null, sublabel: 'trend fit' },
  ]
})
const actionsStrip = computed<StatItem[]>(() => [
  { label: 'Open Actions', value: queueSummary.value.open ?? null },
  { label: 'Total Exposure', amount: queueSummary.value.exposure ?? null, sublabel: 'from open items' },
  { label: 'Overdue', value: queueSummary.value.overdue ?? null },
  { label: 'Unassigned', value: queueSummary.value.unassigned ?? null, sublabel: 'no owner set' },
])
</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <div class="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between px-6 py-4 bg-surface-white border-b border-outline-gray-1">
      <div>
        <Breadcrumbs :items="[{ label: 'Dashboards', route: '/dashboards' }, { label: 'Tax Intelligence' }]" />
        <h1 class="text-2xl font-bold text-ink-gray-9 mt-1">Tax Intelligence</h1>
        <p class="text-sm text-ink-gray-6">
          {{ fyContextLabel || 'India GST, TDS, ITC analytics, compliance monitoring, and tax planning' }}
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <Badge
          v-if="hasData && (asNumber(queueSummary.overdue) ?? 0) > 0"
          v-bind="severityBadge('critical')"
          :label="`${formatNumber(queueSummary.overdue)} OVERDUE ACTION${(asNumber(queueSummary.overdue) ?? 0) !== 1 ? 'S' : ''}`"
        />
        <IntelligenceDateFilter v-model="dateFilter" :options="dateRangeOptions" />

        <Button
          :loading="refreshing"
          variant="solid"
          theme="gray"
          @click="reload"
        >
          <template #prefix><RefreshCcw class="w-4 h-4" /></template>
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
      <!-- Kept: this surface's first screen is a six-up tile grid with a status
           line, not the default KPI strip. -->
      <template #skeleton>
        <div class="flex items-center justify-center flex-1 gap-4 py-16">
          <div class="flex flex-col items-center gap-4">
            <div class="grid grid-cols-3 gap-3 w-96">
              <SkeletonBlock v-for="n in 6" :key="n" class="h-24 rounded-xl" />
            </div>
            <p class="text-sm text-ink-gray-6">Loading tax intelligence...</p>
          </div>
        </div>
      </template>

      <div class="p-6">

      <!-- Variant B KPI ribbon: 6 headline metrics, control-room compact. -->
      <div v-if="activeTab === 'overview'" class="grid grid-cols-2 md:grid-cols-3 wide:grid-cols-6 gap-3 mb-5">
        <KpiCard
          label="Compliance Health"
          :value="data?.compliance_score" unit="/100"
          :severity="complianceSeverity(data?.compliance_score)"
          sublabel="e-Invoice, e-Waybill, filing, recon"
        />
        <KpiCard
          label="Net GST (YTD)"
          :amount="asNumber(data?.net_gst)"
          :currency="baseCurrency"
          sublabel="Output minus ITC utilised"
        />
        <KpiCard
          label="ITC at Risk"
          :amount="asNumber(itcHealth.at_risk_supplier_unfiled)"
          :currency="baseCurrency"
          :severity="(asNumber(itcHealth.at_risk_supplier_unfiled) ?? 0) > 0 ? 'high' : 'none'"
          :sublabel="`Supplier unfiled · ${formatNumber(itcHealth.at_risk_invoice_count)} inv.`"
        />
        <KpiCard
          label="Cash Due W1"
          :amount="w1Amount"
          :currency="baseCurrency"
          :sublabel="w1SublabelText ?? 'No statutory payments this week'"
        />
        <KpiCard
          label="Overdue Tax"
          :amount="asNumber(outlookOverdue.total)"
          :currency="baseCurrency"
          :severity="(asNumber(outlookOverdue.total) ?? 0) > 0 ? 'critical' : 'none'"
          sublabel="Interest accruing"
        />
        <KpiCard
          label="Open Actions"
          :value="asNumber(queueSummary.open)"
          :severity="(asNumber(queueSummary.overdue) ?? 0) > 0 ? 'critical' : (asNumber(queueSummary.open) ?? 0) > 0 ? 'medium' : 'none'"
          :sublabel="`${formatNumber(queueSummary.overdue)} overdue · ${formatCurrency(asNumber(queueSummary.exposure))} at stake`"
        />
      </div>

      <!-- Tabs -->
      <div class="bg-surface-white rounded-lg border border-outline-gray-1 mb-6">
        <Tabs v-model="activeTabIndex" :tabs="tabs" />

        <div class="p-6">

          <!-- Variant B — Control Room Overview: 3-col analytical body → queue → matrix -->
          <div v-if="activeTab === 'overview'" class="space-y-4">

            <!-- 3-column analytical body -->
            <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">

              <!-- Col 1: Filing Status + GSTR-3B dot calendar -->
              <div class="bg-surface-gray-2 rounded-lg border border-outline-gray-1 p-4 space-y-4">
                <SectionHeader variant="caption" title="Filing Status" :level="3" />
                <table class="w-full text-sm">
                  <caption class="sr-only">Current filing status by return type</caption>
                  <tbody class="divide-y divide-outline-gray-1">
                    <tr v-for="row in overviewFilingRows" :key="row.label">
                      <th scope="row" class="py-2 pr-3 text-left text-xs font-medium text-ink-gray-7 w-24">
                        {{ row.label }}
                      </th>
                      <td class="py-2 pr-3 tnum text-xs text-ink-gray-8">{{ row.value }}</td>
                      <td class="py-2 text-right">
                        <Badge v-bind="severityBadge(row.severity)" :label="row.status" size="sm" />
                      </td>
                    </tr>
                  </tbody>
                </table>

                <!-- GSTR-3B 12-month dot calendar -->
                <div v-if="gstr3bDots.length">
                  <p class="text-xs font-medium text-ink-gray-6 mb-2">GSTR-3B (12 months)</p>
                  <div class="flex flex-wrap gap-1.5" role="list" aria-label="GSTR-3B filing status by month">
                    <div
                      v-for="dot in gstr3bDots"
                      :key="dot.key"
                      class="flex flex-col items-center gap-0.5"
                      role="listitem"
                    >
                      <div
                        class="w-7 h-4 rounded-sm"
                        :class="dotStatusClass(dot.status)"
                        :aria-label="`${dot.label}: ${dot.status}`"
                      />
                      <span class="text-xs leading-none text-ink-gray-5" aria-hidden="true">{{ dot.label }}</span>
                    </div>
                  </div>
                  <div class="mt-2 flex items-center gap-3 text-xs text-ink-gray-5" aria-hidden="true">
                    <span class="flex items-center gap-1">
                      <span class="inline-block w-3 h-2 rounded-sm bg-surface-green-2" />
                      Filed
                    </span>
                    <span class="flex items-center gap-1">
                      <span class="inline-block w-3 h-2 rounded-sm bg-surface-red-2" />
                      Overdue
                    </span>
                    <span class="flex items-center gap-1">
                      <span class="inline-block w-3 h-2 rounded-sm bg-surface-gray-2 border border-outline-gray-1" />
                      Unknown
                    </span>
                  </div>
                </div>
              </div>

              <!-- Col 2: 13-week micro-bars + ITC utilisation -->
              <div class="bg-surface-gray-2 rounded-lg border border-outline-gray-1 p-4 space-y-4">
                <SectionHeader
                  variant="caption"
                  title="13-Week Tax Cash Outlook"
                  hint="Statutory due dates · no projection"
                  :level="3"
                />

                <!-- Micro-bars: proportional height from peak_amount -->
                <div>
                  <div class="flex items-end gap-px h-14" aria-hidden="true">
                    <div
                      v-for="week in outlookWeeks"
                      :key="week.label"
                      class="flex-1 flex flex-col items-center justify-end"
                    >
                      <div
                        class="w-full rounded-t-sm motion-reduce:transition-none"
                        :class="week.total > 0 ? 'bg-surface-gray-5' : 'bg-surface-gray-3'"
                        :style="{
                          height: week.total > 0 && (cashOutlook.peak_amount as number) > 0
                            ? `${Math.max((week.total / (cashOutlook.peak_amount as number)) * 100, 10)}%`
                            : '2px',
                        }"
                      />
                    </div>
                  </div>
                  <!-- Axis labels: W1, W4, W7, W10, W13 -->
                  <div class="flex mt-0.5" aria-hidden="true">
                    <div v-for="(week, idx) in outlookWeeks" :key="week.label + '-ax'" class="flex-1 text-center">
                      <span v-if="[0, 3, 6, 9, 12].includes(idx)" class="text-xs text-ink-gray-5">{{ week.label }}</span>
                    </div>
                  </div>
                  <p
                    v-if="outlookWeeks.filter(w => w.total > 0).length <= 1"
                    class="mt-1.5 text-xs text-ink-gray-5"
                  >
                    No further accrued tax falls due in the remaining
                    {{ outlookWeeks.length - outlookWeeks.filter(w => w.total > 0).length }} weeks.
                  </p>
                </div>

                <!-- Already overdue alert -->
                <div
                  v-if="(asNumber(outlookOverdue.total) ?? 0) > 0"
                  class="rounded-lg border border-outline-red-2 bg-surface-red-1 px-3 py-2"
                >
                  <div class="flex items-baseline gap-2 flex-wrap">
                    <Badge v-bind="severityBadge('critical')" label="Already overdue" size="sm" />
                    <span class="tnum text-sm font-semibold text-ink-gray-9">
                      {{ formatCurrency(asNumber(outlookOverdue.total)) }}
                    </span>
                  </div>
                  <p class="mt-0.5 text-xs text-ink-gray-6">
                    GST {{ formatCurrency(asNumber(outlookOverdue.gst)) }} ·
                    TDS {{ formatCurrency(asNumber(outlookOverdue.tds)) }} ·
                    interest accruing
                  </p>
                </div>

                <!-- ITC utilisation -->
                <div>
                  <p class="text-xs font-medium text-ink-gray-6 mb-2 uppercase tracking-wide">ITC Utilisation</p>
                  <dl class="space-y-1.5">
                    <div v-for="row in itcRows" :key="row.label" class="flex items-baseline justify-between gap-2">
                      <dt class="text-xs text-ink-gray-6 min-w-0 truncate">{{ row.label }}</dt>
                      <dd
                        class="tnum text-xs font-semibold shrink-0"
                        :class="row.ink || 'text-ink-gray-8'"
                      >
                        {{ row.amount !== undefined ? formatCurrency(row.amount) : NO_VALUE }}
                      </dd>
                    </div>
                  </dl>
                  <!-- Utilised + at-risk stacked progress bar -->
                  <div
                    v-if="(asNumber(itcHealth.accrued) ?? 0) > 0"
                    class="mt-2 h-2 bg-surface-gray-3 rounded-full overflow-hidden flex"
                    :aria-label="`ITC utilised ${formatPercent(itcHealth.utilization_pct)}, at risk ${formatPercent(itcAtRiskPct)}`"
                    role="img"
                  >
                    <div
                      class="h-full bg-surface-green-2 motion-reduce:transition-none"
                      :style="{ width: `${Math.min(itcHealth.utilization_pct ?? 0, 100)}%` }"
                    />
                    <div
                      class="h-full bg-surface-amber-2 motion-reduce:transition-none"
                      :style="{ width: `${Math.min(itcAtRiskPct, Math.max(0, 100 - (itcHealth.utilization_pct ?? 0)))}%` }"
                    />
                  </div>
                  <p
                    v-if="(asNumber(itcHealth.accrued) ?? 0) > 0"
                    class="mt-1 text-xs text-ink-gray-5"
                  >
                    Utilised {{ formatPercent(itcHealth.utilization_pct) }} ·
                    At risk {{ formatPercent(itcAtRiskPct) }}
                  </p>
                </div>
              </div>

              <!-- Col 3: Reconciliation score + counterparty risk + TDS & TCS -->
              <div class="bg-surface-gray-2 rounded-lg border border-outline-gray-1 p-4 space-y-4">
                <!-- Reconciliation score -->
                <div>
                  <SectionHeader variant="caption" title="Reconciliation Score" :level="3" />
                  <div class="mt-2 flex items-start gap-4">
                    <div class="shrink-0">
                      <p class="text-3xl font-bold tnum text-ink-gray-9 leading-none">
                        {{ reconciliationScore.match_rate_pct !== undefined ? reconciliationScore.match_rate_pct : NO_VALUE }}%
                      </p>
                      <p class="text-xs text-ink-gray-5 mt-1">2A/2B match rate</p>
                      <Badge
                        v-bind="readinessBadge(reconciliationScore.match_rate_pct as number | undefined)"
                        :label="readinessBadge(reconciliationScore.match_rate_pct as number | undefined).label"
                        size="sm"
                        class="mt-1"
                      />
                    </div>
                    <dl class="flex-1 space-y-1 min-w-0">
                      <div v-for="row in reconRows" :key="row.label" class="flex justify-between gap-2 text-xs">
                        <dt class="text-ink-gray-5 truncate">{{ row.label }}</dt>
                        <dd class="tnum font-semibold text-ink-gray-8 shrink-0">{{ formatNumber(row.count) }}</dd>
                      </div>
                    </dl>
                  </div>
                  <div
                    v-if="(asNumber(reconciliationScore.unmatched_count) ?? 0) > 0"
                    class="mt-2 rounded-lg bg-surface-amber-2 px-3 py-2"
                  >
                    <p class="text-xs font-semibold text-ink-gray-8">
                      Unmatched value: {{ formatCurrency(asNumber(reconciliationScore.unmatched_amount)) }}
                    </p>
                    <p class="text-xs text-ink-gray-6">
                      {{ formatNumber(reconciliationScore.unmatched_count) }} rows ·
                      data from {{ formatDate(String(reconciliationScore.data_from ?? '')) }}
                    </p>
                  </div>
                </div>

                <!-- Counterparty risk -->
                <div>
                  <p class="text-xs font-medium text-ink-gray-6 mb-2 uppercase tracking-wide">Counterparty Risk</p>
                  <dl class="space-y-1.5">
                    <div v-for="row in counterpartyRows" :key="row.label" class="flex justify-between gap-2 text-xs">
                      <dt class="text-ink-gray-6">{{ row.label }}</dt>
                      <dd class="tnum font-semibold shrink-0" :class="row.ink || 'text-ink-gray-8'">{{ row.value }}</dd>
                    </div>
                  </dl>
                  <p
                    v-if="(counterpartyRisk.transacted_at_risk_parties ?? 0) > 0"
                    class="mt-1.5 text-xs text-ink-gray-5"
                  >
                    Transacted at-risk:
                    {{ formatNumber(counterpartyRisk.transacted_at_risk_parties) }} parties ·
                    {{ formatCurrency(asNumber(counterpartyRisk.transacted_at_risk_value)) }}
                  </p>
                </div>

                <!-- TDS & TCS position -->
                <div>
                  <p class="text-xs font-medium text-ink-gray-6 mb-2 uppercase tracking-wide">TDS &amp; TCS Position</p>
                  <dl class="space-y-1">
                    <div class="flex justify-between gap-2 text-xs">
                      <dt class="text-ink-gray-6">Payable</dt>
                      <dd class="tnum font-semibold text-ink-gray-8">{{ formatCurrency(asNumber(tdsSummary.total_payable)) }}</dd>
                    </div>
                    <div class="flex justify-between gap-2 text-xs">
                      <dt class="text-ink-gray-6">Receivable</dt>
                      <dd class="tnum font-semibold text-ink-gray-8">{{ formatCurrency(asNumber(tdsSummary.receivable)) }}</dd>
                    </div>
                    <div class="flex justify-between gap-2 text-xs border-t border-outline-gray-1 pt-1">
                      <dt class="text-ink-gray-6">Net (payable)</dt>
                      <dd
                        class="tnum font-semibold shrink-0"
                        :class="(asNumber(tdsSummary.net_position) ?? 0) < 0 ? 'text-ink-red-4' : 'text-ink-gray-8'"
                      >
                        {{ formatCurrency(Math.abs(asNumber(tdsSummary.net_position) ?? 0)) }}
                      </dd>
                    </div>
                  </dl>
                </div>
              </div>
            </div>

            <!-- Priority action queue: dense, red left-border on overdue rows -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
              <div class="flex flex-wrap items-center gap-3 justify-between">
                <div class="flex items-center gap-2">
                  <SectionHeader
                    variant="caption"
                    title="Priority action queue"
                    hint="Owner, due date and money at stake"
                    :level="3"
                  />
                  <Badge
                    v-if="(asNumber(queueSummary.overdue) ?? 0) > 0"
                    v-bind="severityBadge('critical')"
                    :label="`${formatNumber(queueSummary.overdue)} overdue`"
                    size="sm"
                  />
                </div>
                <Button
                  v-if="queueRows.length"
                  variant="subtle"
                  size="sm"
                  @click="openQueueDrillDown()"
                >
                  View all {{ formatNumber(queueSummary.open) }}
                </Button>
              </div>

              <div v-if="queueRows.length" class="mt-3 overflow-x-auto">
                <table class="w-full text-sm">
                  <caption class="sr-only">Open tax control actions, highest exposure first</caption>
                  <thead class="bg-surface-gray-1 text-left text-xs uppercase tracking-wide text-ink-gray-6">
                    <tr>
                      <th scope="col" class="px-3 py-2 font-medium">Exception</th>
                      <th scope="col" class="px-3 py-2 font-medium">Area</th>
                      <th scope="col" class="px-3 py-2 font-medium text-right">At stake</th>
                      <th scope="col" class="px-3 py-2 font-medium">Owner</th>
                      <th scope="col" class="px-3 py-2 font-medium">Due</th>
                      <th scope="col" class="px-3 py-2 font-medium">Plan state</th>
                      <th scope="col" class="px-3 py-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-outline-gray-1">
                    <tr
                      v-for="row in queueRows"
                      :key="row.name"
                      class="align-top"
                    >
                      <td class="px-3 py-2.5">
                        <p class="font-medium text-xs text-ink-gray-8 leading-snug">{{ row.title }}</p>
                        <p class="mt-0.5 text-xs text-ink-gray-5">{{ row.name }}</p>
                      </td>
                      <td class="px-3 py-2.5 text-xs text-ink-gray-6">{{ row.area }}</td>
                      <td class="px-3 py-2.5 text-right tnum text-xs font-semibold text-ink-gray-8">
                        {{ formatCurrency(asNumber(row.exposure)) }}
                      </td>
                      <td class="px-3 py-2.5 text-xs">
                        <span class="text-ink-gray-8">{{ row.owner_role || 'Unassigned' }}</span>
                        <p v-if="!row.assigned_to" class="mt-0.5 text-ink-gray-5">No person assigned</p>
                      </td>
                      <td class="px-3 py-2.5 whitespace-nowrap text-xs text-ink-gray-7">
                        {{ formatDate(row.due_date) }}
                        <p
                          v-if="row.due_in_days !== undefined && row.due_in_days !== null"
                          class="mt-0.5"
                          :class="row.overdue ? 'text-ink-red-4' : 'text-ink-gray-5'"
                        >
                          {{ row.overdue ? `${Math.abs(row.due_in_days)} days late` : `in ${row.due_in_days} days` }}
                        </p>
                      </td>
                      <td class="px-3 py-2.5 text-xs text-ink-gray-6">{{ row.plan_state || '-' }}</td>
                      <td class="px-3 py-2.5">
                        <Badge
                          v-bind="severityBadge(row.overdue ? 'critical' : prioritySeverity(row.priority))"
                          :label="row.overdue ? 'Escalate' : (row.status || 'Open')"
                          size="sm"
                        />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <p v-else class="mt-3 text-sm text-ink-gray-6">
                No open tax exception on the control board. The detectors run
                weekly against the whole ledger, not a rolling window.
              </p>
            </div>
          </div>

          <!-- GST Overview -->
          <div v-if="activeTab === 'gst'" class="space-y-6">
            <TabBrief :brief="tabBriefs.gst" :as-of="data?.generated_at" />
            <StatStrip :items="gstStrip" :currency="baseCurrency" />
            <div class="grid grid-cols-1 items-start gap-6 lg:grid-cols-2">
              <div class="min-w-0 space-y-6">
                <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                  <SectionHeader variant="caption" :title="gstPeriod ? `Output GST: ${gstPeriod}` : 'Output GST'" :level="3" />
                  <div v-if="gstSummary.length" class="mt-4 overflow-x-auto">
                    <table class="w-full text-xs whitespace-nowrap [&_td]:!px-1.5 [&_th]:!px-1.5">
                      <caption class="sr-only">Monthly GST: CGST, SGST, IGST, total and effective rate on revenue</caption>
                      <thead class="bg-surface-gray-1">
                        <tr>
                          <th scope="col" class="px-3 py-2 text-left text-ink-gray-6">Month</th>
                          <th scope="col" class="px-3 py-2 text-right text-ink-gray-6">CGST</th>
                          <th scope="col" class="px-3 py-2 text-right text-ink-gray-6">SGST</th>
                          <th scope="col" class="px-3 py-2 text-right text-ink-gray-6">IGST</th>
                          <th scope="col" class="px-3 py-2 text-right text-ink-gray-6">Total</th>
                          <th scope="col" class="px-3 py-2 text-right text-ink-gray-6">Rate</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="d in gstTable.rows" :key="d.month" class="border-b border-outline-gray-1">
                          <th scope="row" class="px-3 py-2 text-left font-normal text-ink-gray-8">{{ monthLabel(d.month) }}</th>
                          <td class="tnum px-3 py-2 text-right text-ink-gray-7">{{ formatCurrency(d.cgst) }}</td>
                          <td class="tnum px-3 py-2 text-right text-ink-gray-7">{{ formatCurrency(d.sgst) }}</td>
                          <td class="tnum px-3 py-2 text-right text-ink-gray-7">{{ formatCurrency(d.igst) }}</td>
                          <td class="tnum px-3 py-2 text-right font-medium text-ink-gray-9">{{ formatCurrency(d.total) }}</td>
                          <td class="tnum px-3 py-2 text-right text-ink-gray-7">{{ d.rate }}</td>
                        </tr>
                        <tr class="bg-surface-gray-1 font-medium">
                          <th scope="row" class="px-3 py-2 text-left text-ink-gray-9">{{ gstTable.ytd.month }}</th>
                          <td class="tnum px-3 py-2 text-right text-ink-gray-9">{{ formatCurrency(gstTable.ytd.cgst) }}</td>
                          <td class="tnum px-3 py-2 text-right text-ink-gray-9">{{ formatCurrency(gstTable.ytd.sgst) }}</td>
                          <td class="tnum px-3 py-2 text-right text-ink-gray-9">{{ formatCurrency(gstTable.ytd.igst) }}</td>
                          <td class="tnum px-3 py-2 text-right text-ink-gray-9">{{ formatCurrency(gstTable.ytd.total) }}</td>
                          <td class="tnum px-3 py-2 text-right text-ink-gray-9">{{ gstTable.ytd.rate }}</td>
                        </tr>
                      </tbody>
                    </table>
                    <p class="mt-3 text-xs text-ink-gray-6">
                      Effective rate {{ gstTable.ytd.rate }} on revenue of {{ formatCurrency(gstTable.ytd.revenue) }}.
                    </p>
                  </div>
                  <div v-else class="mt-4 py-6 text-center text-ink-gray-6">No GST data available</div>
                </div>

                <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                  <SectionHeader variant="caption" title="GSTR Filing Status" hint="Returns due, e-Invoice IRN and e-Waybill" :level="3" />
                  <ul class="mt-4 space-y-4">
                    <li v-for="f in gstFilingRows" :key="f.key">
                      <div class="flex items-center justify-between gap-3">
                        <p class="text-sm font-medium text-ink-gray-9">{{ f.title }}</p>
                        <Badge v-bind="severityBadge(f.severity)" :label="f.chip" size="sm" />
                      </div>
                      <div
                        v-if="f.pct != null"
                        class="mt-2 flex h-2 overflow-hidden rounded-full bg-surface-red-3"
                        role="img"
                        :aria-label="`${f.title}: ${formatPercent(f.pct)}`"
                      >
                        <div class="h-2 bg-surface-green-3" :style="{ width: `${Math.min(100, Math.max(0, f.pct))}%` }" />
                      </div>
                      <p class="mt-1 flex justify-between gap-3 text-xs text-ink-gray-6">
                        <span>{{ f.note }}</span>
                        <span class="tnum shrink-0">{{ formatPercent(f.pct) }}</span>
                      </p>
                    </li>
                  </ul>
                </div>
              </div>

              <div class="min-w-0 space-y-6">
                <div v-if="gstBridgeConfig" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                  <SectionHeader variant="caption" title="GST Cash Bridge" hint="Output GST less input tax credit, and the credit at risk" :level="3" />
                  <IntelligenceChart :config="gstBridgeConfig" class="mt-4 h-52 sm:h-64" />
                  <p v-if="gstBridgeNote" class="mt-3 text-xs text-ink-gray-6">{{ gstBridgeNote }}</p>
                </div>

                <div v-if="asNumber(reconciliationScore.total_count)" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                  <SectionHeader
                    variant="caption"
                    title="2A/2B Reconciliation"
                    :hint="`Data runs ${reconciliationScore.data_from ? formatDate(String(reconciliationScore.data_from)) + ' to ' : 'to '}${formatDate(String(reconciliationScore.data_through ?? ''))}`"
                    :level="3"
                  />
                  <div class="overflow-x-auto mt-4">
                    <table class="w-full text-sm">
                      <thead class="bg-surface-gray-1">
                        <tr>
                          <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Status</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Rows</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="r in reconTable" :key="r.label" class="border-b border-outline-gray-1">
                          <td class="px-4 py-2 text-ink-gray-8">
                            <span class="mr-2 inline-block h-2 w-2 rounded-full align-middle" :class="severityFill(r.severity)" aria-hidden="true" />{{ r.label }}
                          </td>
                          <td class="tnum px-4 py-2 text-right text-ink-gray-7">{{ formatNumber(r.count) }}</td>
                          <td class="tnum px-4 py-2 text-right text-ink-gray-8">{{ formatCurrency(r.amount) }}</td>
                        </tr>
                        <tr class="font-medium">
                          <td class="px-4 py-2 text-ink-gray-8">Total rows</td>
                          <td class="tnum px-4 py-2 text-right text-ink-gray-8">{{ formatNumber(reconciliationScore.total_count) }}</td>
                          <td class="px-4 py-2 text-right text-ink-gray-7">{{ formatNumber(reconciliationScore.unactioned_count) }} unactioned</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- HSN Summary -->
                <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                  <!-- Row count comes from the server cap (`HSN_TOP_N`), so the
                       title counts what rendered rather than restating a
                       constant the payload could stop honouring. -->
                  <SectionHeader
                    variant="caption"
                    :title="hsnSummary.length ? `HSN Summary (Top ${hsnSummary.length} by Revenue)` : 'HSN Summary'"
                    :level="3"
                  />
                  <div class="overflow-x-auto mt-4">
                    <table class="w-full text-sm">
                      <thead class="bg-surface-gray-1">
                        <tr>
                          <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">HSN Code</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Revenue (Pre-GST)</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Actual GST</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Eff. Rate</th>
                          <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Invoices</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="hsn in hsnSummary"
                          :key="hsn.hsn_code"
                          class="border-b border-outline-gray-1 hover:bg-surface-gray-1 cursor-pointer transition-colors motion-reduce:transition-none"
                          tabindex="0"
                          @click="openHsnDrillDown(hsn)"
                          @keydown.enter="openHsnDrillDown(hsn)"
                        >
                          <td class="px-4 py-2 font-medium text-ink-gray-8">{{ hsn.hsn_code || NO_VALUE }}</td>
                          <td class="tnum px-4 py-2 text-right text-ink-gray-7">{{ formatCurrency(hsn.revenue) }}</td>
                          <td class="tnum px-4 py-2 text-right text-ink-gray-7">{{ formatCurrency(hsn.actual_gst) }}</td>
                          <td class="px-4 py-2 text-right">
                            <Badge
                              v-bind="severityBadge(hsnRateSeverity(hsn.effective_gst_rate))"
                              :label="formatPercent(hsn.effective_gst_rate)"
                              size="sm"
                            />
                          </td>
                          <td class="tnum px-4 py-2 text-right text-ink-gray-7">{{ formatNumber(hsn.invoice_count) }}</td>
                        </tr>
                        <tr v-if="!hsnSummary.length">
                          <td colspan="5" class="px-4 py-6 text-center text-ink-gray-6">No HSN data available</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
            <TabActions class="mt-6" :actions="tabBriefs.gst?.actions" />
          </div>

          <!-- Compliance Health -->
          <div v-if="activeTab === 'compliance'" class="space-y-6">
            <TabBrief :brief="tabBriefs.compliance" :as-of="data?.generated_at" />
            <StatStrip :items="complianceStrip" :currency="baseCurrency" />

            <!-- Compliance coverage matrix -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
              <SectionHeader
                variant="caption"
                title="Compliance coverage matrix"
                hint="Reconciliation, filing, evidence and escalation per tax area"
                :level="3"
              />
              <div class="mt-3 overflow-x-auto">
                <table class="w-full text-sm">
                  <caption class="sr-only">Control status by tax area</caption>
                  <thead class="bg-surface-gray-1 text-left text-xs uppercase tracking-wide text-ink-gray-6">
                    <tr>
                      <th scope="col" class="px-3 py-2 font-medium">Area</th>
                      <th scope="col" class="px-3 py-2 font-medium">Status</th>
                      <th scope="col" class="px-3 py-2 font-medium">Reconciliation</th>
                      <th scope="col" class="px-3 py-2 font-medium">Filing</th>
                      <th scope="col" class="px-3 py-2 font-medium">Evidence</th>
                      <th scope="col" class="px-3 py-2 font-medium">Escalates to</th>
                      <th scope="col" class="px-3 py-2 font-medium text-right">Open</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-outline-gray-1">
                    <tr v-for="row in complianceMatrix" :key="row.area">
                      <th scope="row" class="px-3 py-2.5 text-left text-xs font-medium text-ink-gray-8">
                        {{ row.area }}
                      </th>
                      <td class="px-3 py-2.5">
                        <Badge v-bind="severityBadge(matrixSeverity(row.status))" :label="row.status" size="sm" />
                      </td>
                      <td
                        v-for="cell in ['reconciliation', 'filing', 'evidence', 'escalation']"
                        :key="cell"
                        class="px-3 py-2.5 text-xs"
                      >
                        <template v-if="matrixCell(row, cell).value === null">
                          <span class="text-ink-gray-5">—</span>
                        </template>
                        <template v-else>
                          <span class="text-ink-gray-8">{{ matrixCellText(row, cell) }}</span>
                        </template>
                        <p class="mt-0.5 text-ink-gray-5">{{ matrixCell(row, cell).note }}</p>
                      </td>
                      <td class="px-3 py-2.5 text-right tnum text-xs text-ink-gray-8">
                        {{ formatNumber(row.open_actions) }}
                        <p v-if="(asNumber(row.exposure) ?? 0) > 0" class="mt-0.5 text-ink-gray-5">
                          {{ formatCurrency(asNumber(row.exposure)) }}
                        </p>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <!--
              Exposure in rupees, above the coverage percentages.
              A coverage figure tells you a ratio; a CFO needs the amount at
              stake and the provision that puts it there.
            -->
            <section aria-labelledby="exposure-heading">
              <SectionHeader
                id="exposure-heading"
                variant="caption"
                title="Quantified exposure"
                hint="Amounts at stake, with the provision each one arises under"
                :level="3"
              />
              <div class="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                <KpiCard
                  label="Invoices missing a required IRN"
                  :value="`${einvoiceStatus.pending ?? 0} of ${einvoiceStatus.total ?? 0}`"
                  :severity="(einvoiceStatus.pending ?? 0) > 0 ? 'critical' : 'none'"
                  :sublabel="`${formatCurrency(einvoiceStatus.pending_value ?? 0)} · Sec 122(1)`"
                  :clickable="true"
                  @click="drillDown.open(TAX_ENDPOINT, 'Invoices missing a required IRN', { metric: 'irn_missing', period: dateFilter })"
                />
                <KpiCard
                  label="e-Waybills pending"
                  :value="String(ewaybillStatus.pending ?? 0)"
                  :severity="(ewaybillStatus.pending ?? 0) > 0 ? 'high' : 'none'"
                  :sublabel="`Threshold ₹${(einvoiceInfo.eway_bill_threshold_inr ?? 50000).toLocaleString('en-IN')}`"
                  :clickable="true"
                  @click="drillDown.open(TAX_ENDPOINT, 'e-Waybills pending', { metric: 'ewaybill_pending', period: dateFilter })"
                />
                <KpiCard
                  label="ITC at risk, supplier has not filed"
                  :value="formatCurrency(itcHealth.at_risk_supplier_unfiled ?? 0)"
                  :severity="(itcHealth.at_risk_supplier_unfiled ?? 0) > 0 ? 'high' : 'none'"
                  sublabel="Sec 16(2)(aa)"
                  :clickable="true"
                  @click="drillDown.open(TAX_ENDPOINT, 'ITC at risk, supplier has not filed', { metric: 'itc_at_risk', period: dateFilter })"
                />
                <KpiCard
                  label="2A/2B rows awaiting action"
                  :value="formatNumber(reconciliationScore.unactioned_count ?? 0)"
                  :severity="(reconciliationScore.unactioned_count ?? 0) > 0 ? 'medium' : 'none'"
                  :sublabel="
                    reconciliationScore.data_through
                      ? `Reconciled only to ${formatDate(reconciliationScore.data_through)}`
                      : 'No 2A/2B data imported'
                  "
                  :clickable="true"
                  @click="drillDown.open(TAX_ENDPOINT, '2A/2B rows awaiting action', { metric: 'reconciliation_unactioned', period: dateFilter })"
                />
              </div>

              <!--
                Counterparty registration health. Credit taken against a
                cancelled or suspended GSTIN is challenged regardless of how
                clean our own books are.
              -->
              <div class="mt-4 rounded-lg border border-outline-gray-1 bg-card p-4">
                <div class="flex flex-wrap items-baseline justify-between gap-2">
                  <p class="text-sm font-medium text-ink-gray-8">
                    Counterparty GSTIN registry
                  </p>
                  <p class="text-sm text-ink-gray-6">
                    {{ formatNumber(counterpartyRisk.registry_total ?? 0) }} tracked
                  </p>
                </div>
                <dl class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div>
                    <dt class="text-sm text-ink-gray-6">Active</dt>
                    <dd class="tnum text-lg font-semibold text-ink-gray-9">
                      {{ formatNumber(counterpartyRisk.active ?? 0) }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-sm text-ink-gray-6">Cancelled</dt>
                    <dd class="tnum text-lg font-semibold" :class="deltaInk(-(counterpartyRisk.cancelled ?? 0))">
                      {{ formatNumber(counterpartyRisk.cancelled ?? 0) }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-sm text-ink-gray-6">Suspended</dt>
                    <dd class="tnum text-lg font-semibold text-ink-gray-9">
                      {{ formatNumber(counterpartyRisk.suspended ?? 0) }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-sm text-ink-gray-6">Blocked, Rule 86A</dt>
                    <dd class="tnum text-lg font-semibold" :class="deltaInk(-(counterpartyRisk.blocked ?? 0))">
                      {{ formatNumber(counterpartyRisk.blocked ?? 0) }}
                    </dd>
                  </div>
                </dl>
                <p class="mt-3 text-sm text-ink-gray-6">
                  <template v-if="(counterpartyRisk.transacted_at_risk_parties ?? 0) > 0">
                    {{ formatNumber(counterpartyRisk.transacted_at_risk_parties ?? 0) }} of these were
                    transacted with this period, worth
                    {{ formatCurrency(counterpartyRisk.transacted_at_risk_value ?? 0) }}.
                  </template>
                  <template v-else>
                    None of the cancelled, suspended or blocked registrations were
                    transacted with this period.
                  </template>
                </p>
              </div>
            </section>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <!-- e-Invoice -->
              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
                <div class="flex items-center justify-between mb-1">
                  <p class="text-sm text-ink-gray-6">e-Invoice Coverage</p>
                  <Badge
                    theme="gray"
                    variant="subtle"
                    :label="'Mandatory: ₹' + (einvoiceInfo.mandatory_threshold_crore || 5) + ' Cr AATO'"
                    size="sm"
                  />
                </div>
                <p class="text-2xl font-bold text-ink-gray-9">
                  {{ formatPercent(einvoiceStatus.coverage_pct) }}
                </p>
                <Badge
                  v-bind="readinessBadge(einvoiceStatus.coverage_pct)"
                  :label="readinessBadge(einvoiceStatus.coverage_pct).label"
                  size="sm"
                  class="mt-1"
                />
                <div
                  class="w-full bg-surface-gray-2 rounded-full h-2 mt-3"
                  role="img"
                  :aria-label="'e-Invoice coverage ' + formatPercent(einvoiceStatus.coverage_pct)"
                >
                  <div
                    class="h-2 rounded-full transition-all motion-reduce:transition-none"
                    :class="severityFill(complianceSeverity(einvoiceStatus.coverage_pct))"
                    :style="{ width: `${Math.min(einvoiceStatus.coverage_pct || 0, 100)}%` }"
                  />
                </div>
                <div class="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                  <div><p class="text-ink-gray-6">Filed</p><p class="font-bold text-ink-gray-8">{{ formatNumber(einvoiceStatus.filed) }}</p></div>
                  <div><p class="text-ink-gray-6">Pending</p><p class="font-bold text-ink-gray-7">{{ formatNumber(einvoiceStatus.pending) }}</p></div>
                  <div><p class="text-ink-gray-6">Failed</p><p class="font-bold text-ink-gray-7">{{ formatNumber(einvoiceStatus.failed) }}</p></div>
                </div>
                <p v-if="einvoiceInfo.upload_30day_threshold_crore" class="mt-2 text-xs text-ink-gray-6">
                  ₹{{ einvoiceInfo.upload_30day_threshold_crore }} Cr: upload within
                  {{ einvoiceInfo.upload_within_days }} days (from {{ einvoiceInfo.upload_30day_mandatory_from }})
                </p>
              </div>

              <!-- e-Waybill -->
              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
                <p class="text-sm text-ink-gray-6">e-Waybill Status</p>
                <div class="mt-3 grid grid-cols-3 gap-2 text-center">
                  <div class="p-2 bg-surface-gray-1 rounded-lg">
                    <p class="text-xs text-ink-gray-6">Total</p>
                    <p class="text-lg font-bold text-ink-gray-9">{{ formatNumber(ewaybillStatus.total) }}</p>
                  </div>
                  <div class="p-2 bg-surface-gray-1 rounded-lg">
                    <p class="text-xs text-ink-gray-6">Active</p>
                    <p class="text-lg font-bold text-ink-gray-8">{{ formatNumber(ewaybillStatus.active) }}</p>
                  </div>
                  <div class="p-2 bg-surface-gray-1 rounded-lg">
                    <p class="text-xs text-ink-gray-6">Cancelled</p>
                    <p class="text-lg font-bold text-ink-gray-8">{{ formatNumber(ewaybillStatus.cancelled) }}</p>
                  </div>
                </div>
              </div>

              <!-- Reconciliation -->
              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-4">
                <p class="text-sm text-ink-gray-6">Purchase Reconciliation Score</p>
                <p class="text-2xl font-bold text-ink-gray-9">
                  {{ reconciliationScore.match_rate_pct ?? 0 }}/100
                </p>
                <Badge
                  v-bind="readinessBadge(reconciliationScore.match_rate_pct as number | undefined)"
                  :label="readinessBadge(reconciliationScore.match_rate_pct as number | undefined).label"
                  size="sm"
                  class="mt-1"
                />
                <div class="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                  <div><p class="text-ink-gray-6">Matched</p><p class="font-bold text-ink-gray-8">{{ formatNumber(reconciliationScore.matched_count) }}</p></div>
                  <div><p class="text-ink-gray-6">Unmatched</p><p class="font-bold text-ink-gray-7">{{ formatNumber(reconciliationScore.unmatched_count) }}</p></div>
                  <div><p class="text-ink-gray-6">Mismatch</p><p class="font-bold text-ink-gray-7">{{ formatNumber(reconciliationScore.mismatch_count) }}</p></div>
                </div>
              </div>
            </div>

            <!-- Alerts -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div
                v-if="!filingClear(filingCompliance.gstr1?.status) || !filingClear(filingCompliance.gstr3b?.status)"
                class="p-4 bg-surface-white border border-outline-gray-1 rounded-lg"
              >
                <div class="flex items-start gap-3">
                  <AlertTriangle class="w-5 h-5 text-ink-gray-6 flex-shrink-0 mt-0.5" aria-hidden="true" />
                  <div>
                    <div class="flex items-center gap-2 mb-1">
                      <p class="font-medium text-ink-gray-9">Overdue Filings</p>
                      <Badge v-bind="severityBadge('high')" :label="severityBadge('high').label" size="sm" />
                    </div>
                    <p class="text-sm text-ink-gray-7">
                      <span v-if="!filingClear(filingCompliance.gstr1?.status)">
                        GSTR-1: {{ filingCompliance.gstr1?.overdue ?? 0 }} of
                        {{ filingCompliance.gstr1?.due ?? 0 }} periods due through
                        {{ formatReturnPeriod(filingCompliance.gstr1?.due_through) }} not filed.
                      </span>
                      <span v-if="!filingClear(filingCompliance.gstr3b?.status)">
                        GSTR-3B: {{ filingCompliance.gstr3b?.overdue ?? 0 }} of
                        {{ filingCompliance.gstr3b?.due ?? 0 }} periods due through
                        {{ formatReturnPeriod(filingCompliance.gstr3b?.due_through) }} not filed.
                      </span>
                    </p>
                  </div>
                </div>
              </div>

              <div
                v-if="(einvoiceStatus.coverage_pct || 0) < 80"
                class="p-4 bg-surface-white border border-outline-gray-1 rounded-lg"
              >
                <div class="flex items-start gap-3">
                  <AlertTriangle class="w-5 h-5 text-ink-gray-6 flex-shrink-0 mt-0.5" aria-hidden="true" />
                  <div>
                    <div class="flex items-center gap-2 mb-1">
                      <p class="font-medium text-ink-gray-9">Low e-Invoice Coverage</p>
                      <Badge v-bind="severityBadge(complianceSeverity(einvoiceStatus.coverage_pct))" :label="severityBadge(complianceSeverity(einvoiceStatus.coverage_pct)).label" size="sm" />
                    </div>
                    <p class="text-sm text-ink-gray-7">Coverage is {{ formatPercent(einvoiceStatus.coverage_pct) }}. Enable e-Invoicing for B2B invoices above the threshold.</p>
                  </div>
                </div>
              </div>

              <div
                v-if="(reconciliationScore.mismatch_count || 0) > 0"
                class="p-4 bg-surface-white border border-outline-gray-1 rounded-lg"
              >
                <div class="flex items-start gap-3">
                  <AlertTriangle class="w-5 h-5 text-ink-gray-6 flex-shrink-0 mt-0.5" aria-hidden="true" />
                  <div>
                    <div class="flex items-center gap-2 mb-1">
                      <p class="font-medium text-ink-gray-9">Reconciliation Mismatches</p>
                      <Badge v-bind="severityBadge('high')" :label="severityBadge('high').label" size="sm" />
                    </div>
                    <p class="text-sm text-ink-gray-7">{{ formatNumber(reconciliationScore.mismatch_count) }} invoices have GST mismatches with GSTR-2A/2B.</p>
                  </div>
                </div>
              </div>

              <div
                v-if="(itcHealth.balance || 0) > 0 && (itcHealth.utilization_pct || 0) < 70"
                class="p-4 bg-surface-white border border-outline-gray-1 rounded-lg"
              >
                <div class="flex items-start gap-3">
                  <AlertTriangle class="w-5 h-5 text-ink-gray-6 flex-shrink-0 mt-0.5" aria-hidden="true" />
                  <div>
                    <div class="flex items-center gap-2 mb-1">
                      <p class="font-medium text-ink-gray-9">Unutilised ITC</p>
                      <Badge v-bind="severityBadge('medium')" :label="severityBadge('medium').label" size="sm" />
                    </div>
                    <p class="text-sm text-ink-gray-7">{{ formatCurrency(itcHealth.balance) }} of input credit is accrued but not set off. Review blocked/ineligible credits.</p>
                  </div>
                </div>
              </div>

              <div
                v-if="filingClear(filingCompliance.gstr1?.status)
                    && filingClear(filingCompliance.gstr3b?.status)
                    && (einvoiceStatus.coverage_pct || 0) >= 80
                    && (reconciliationScore.mismatch_count || 0) === 0"
                class="p-4 bg-surface-white border border-outline-gray-1 rounded-lg"
              >
                <div class="flex items-start gap-3">
                  <CheckCircle class="w-5 h-5 text-ink-gray-6 flex-shrink-0 mt-0.5" aria-hidden="true" />
                  <div>
                    <div class="flex items-center gap-2 mb-1">
                      <p class="font-medium text-ink-gray-9">All Clear</p>
                      <Badge v-bind="severityBadge('none')" :label="severityBadge('none').label" size="sm" />
                    </div>
                    <p class="text-sm text-ink-gray-7">No major compliance issues detected.</p>
                  </div>
                </div>
              </div>
            </div>

            <!--
              Reconciliation lanes.

              Four streams that each have to be matched before a period can
              be called closed, on counts so the three states of each stream
              add up to a denominator the reader can check. Coverage
              percentages for the same streams are in the tiles above; these
              lanes say *how many rows* are still unmatched, which is the
              number the person clearing them works from.
            -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader
                variant="caption"
                title="Reconciliation control"
                hint="Each stream must be matched before the return period closes"
                :level="3"
              />
              <div class="mt-4 space-y-4">
                <LaneTrack
                  v-for="lane in reconciliationLanes"
                  :key="lane.key"
                  :label="lane.label"
                  :matched="lane.matched"
                  :pending="lane.pending"
                  :issue="lane.issue"
                  :total="lane.total"
                  :note="lane.note"
                />
              </div>
              <p class="mt-4 text-sm text-ink-gray-7">
                <strong class="font-medium text-ink-gray-8">Closure rule.</strong>
                A GST period is not clear because the return was filed. It is
                clear when the stream is reconciled, the payment is made where
                one is due, and the evidence is attached.
              </p>
            </div>

            <div v-if="complianceCalendar.length" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader
                variant="caption"
                title="Tax compliance calendar"
                hint="Statutory dates from the ledger, not a typed checklist"
                :level="3"
              />
              <div class="mt-4">
                <DateCalendar :rows="complianceCalendar" />
              </div>
            </div>

            <div v-if="compliancePulse.available" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader variant="caption" title="Compliance pulse" hint="Counts from the action board and legal register" :level="3" />
              <dl class="mt-4 grid grid-cols-1 gap-x-8 gap-y-2 text-sm md:grid-cols-2">
                <div
                  v-for="r in [
                    ['Open action items', formatNumber(compliancePulse.open_items)],
                    ['Overdue items', formatNumber(compliancePulse.overdue)],
                    ['Due soon', formatNumber(compliancePulse.due_soon)],
                    ['On track', formatNumber(compliancePulse.on_track)],
                    ['Total exposure', formatCurrency(asNumber(compliancePulse.exposure))],
                    ['Unassigned items', formatNumber(compliancePulse.unassigned)],
                    ['Without evidence', formatNumber(compliancePulse.without_evidence)],
                  ]"
                  :key="r[0]"
                  class="flex justify-between gap-3 border-b border-outline-gray-1 py-1"
                >
                  <dt class="text-ink-gray-7">{{ r[0] }}</dt>
                  <dd class="tnum font-semibold text-ink-gray-8">{{ r[1] }}</dd>
                </div>
              </dl>
            </div>
            <TabActions class="mt-6" :actions="tabBriefs.compliance?.actions" />
          </div>

          <!-- TDS -->
          <div v-if="activeTab === 'tds'" class="space-y-6">
            <TabBrief :brief="tabBriefs.tds" :as-of="data?.generated_at" />
            <StatStrip :items="tdsStrip" :currency="baseCurrency" />

            <!-- Without a second bar to compare, the chart card drops out and
                 the table takes the full row rather than leaving dead space. -->
            <div class="grid grid-cols-1 gap-6" :class="tdsBarConfig ? 'lg:grid-cols-2' : ''">
              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader
                  variant="caption"
                  :title="tdsHasSections ? 'TDS Payable by Section' : 'TDS Payable by Account Head'"
                  :hint="tdsHasSections ? undefined : 'Name the GL heads per section (194C, 194J, ...) to attribute rates and thresholds'"
                  :level="3"
                />
                <div class="overflow-x-auto mt-4">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th v-if="tdsHasSections" scope="col" class="px-4 py-2 text-left text-ink-gray-6">Section</th>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">{{ tdsHasSections ? 'Nature of Payment' : 'Account Head' }}</th>
                        <th v-if="tdsHasSections" scope="col" class="px-4 py-2 text-right text-ink-gray-6">Rate</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">TDS Amount</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">% of Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="sec in (tdsSummary.payable_by_section || [])" :key="sec.section" class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
                        <td v-if="tdsHasSections" class="px-4 py-2 font-medium text-ink-gray-8">
                          <Badge v-if="sec.section_code" theme="gray" variant="subtle" :label="sec.section_code" size="sm" class="mr-1" />
                          <span v-else class="text-ink-gray-7 text-xs">{{ NO_VALUE }}</span>
                        </td>
                        <td class="px-4 py-2 text-ink-gray-7">{{ sec.description || sec.section }}</td>
                        <td v-if="tdsHasSections" class="px-4 py-2 text-right text-ink-gray-7">
                          {{ formatPercent(sec.rate_pct) }}
                        </td>
                        <td class="px-4 py-2 text-right text-ink-gray-8">{{ formatCurrency(sec.amount) }}</td>
                        <td class="px-4 py-2 text-right">
                          <Badge
                            theme="gray"
                            variant="subtle"
                            :label="formatPercent(tdsSummary.total_payable > 0 ? (sec.amount / tdsSummary.total_payable) * 100 : 0)"
                            size="sm"
                          />
                        </td>
                      </tr>
                      <tr v-if="!(tdsSummary.payable_by_section || []).length">
                        <td :colspan="tdsHasSections ? 5 : 3" class="px-4 py-6 text-center text-ink-gray-6">No TDS data available</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div v-if="tdsBarConfig" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader variant="caption" title="Top 5 TDS Sections" :level="3" />
                <div class="h-80 mt-4">
                  <IntelligenceChart :config="tdsBarConfig" class="h-52 sm:h-64 lg:h-72" />
                </div>
              </div>
            </div>

            <div v-if="tdsChallans.rows.length" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader variant="caption" title="TDS challans by period" :level="3" />
              <div class="overflow-x-auto mt-4">
                <table class="w-full text-sm">
                  <thead class="bg-surface-gray-1">
                    <tr>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Period</th>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Due date</th>
                      <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Amount</th>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="p in tdsChallans.rows" :key="p.period" class="border-b border-outline-gray-1">
                      <td class="px-4 py-2 text-ink-gray-8">{{ p.period }}</td>
                      <td class="px-4 py-2 text-ink-gray-7">{{ formatDate(p.due_date) }}</td>
                      <td class="px-4 py-2 text-right text-ink-gray-8">{{ formatCurrency(p.amount) }}</td>
                      <td class="px-4 py-2">
                        <Badge :theme="p.overdue ? 'red' : 'gray'" variant="subtle" :label="p.overdue ? 'Overdue' : 'Upcoming'" size="sm" />
                      </td>
                    </tr>
                    <tr class="font-medium">
                      <td class="px-4 py-2 text-ink-gray-8" colspan="2">Total</td>
                      <td class="px-4 py-2 text-right text-ink-gray-8">{{ formatCurrency(tdsChallans.total) }}</td>
                      <td></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader
                variant="caption"
                title="TDS control flow"
                hint="No amount should move without a complete chain"
                :level="3"
              />
              <div class="mt-4">
                <FlowSteps :steps="tdsControlFlow" />
              </div>
            </div>

            <!--
              Receivable is credit customers deducted from us. It is only
              recoverable with the deductor's certificate, so the unmatched
              part is called out as tax credit at risk rather than folded into
              the net position above.
            -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader
                variant="caption"
                title="Customer TDS receivable"
                hint="Tax credit already earned, pending the deductor's certificate"
                :level="3"
              />
              <div class="mt-4">
                <WaterfallRows
                  :currency="baseCurrency"
                  :rows="[
                    { label: 'Deducted by customers, per our books', amount: asNumber(tdsSummary.receivable) ?? null, direction: 'neutral' },
                    { label: 'TDS we owe on supplier bills', amount: asNumber(tdsSummary.total_payable) ?? null, direction: 'negative' },
                    { label: 'Net position', amount: asNumber(tdsSummary.net_position) ?? null, direction: 'neutral' },
                  ]"
                />
              </div>
            </div>

            <div v-if="rcmSummary.available" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader variant="caption" title="RCM reconciliation" hint="Books against the GST portal" :level="3" />
              <div class="overflow-x-auto mt-4">
                <table class="w-full text-sm">
                  <thead class="bg-surface-gray-1">
                    <tr>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Source</th>
                      <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Rows</th>
                      <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Tax</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr class="border-b border-outline-gray-1">
                      <td class="px-4 py-2 text-ink-gray-8">Books (invoices)</td>
                      <td class="px-4 py-2 text-right text-ink-gray-7">{{ formatNumber((rcmSummary.books ?? {}).invoices) }}</td>
                      <td class="px-4 py-2 text-right text-ink-gray-8">{{ formatCurrency(asNumber((rcmSummary.books ?? {}).tax)) }}</td>
                    </tr>
                    <tr class="border-b border-outline-gray-1">
                      <td class="px-4 py-2 text-ink-gray-8">Portal (GSTR-2A/2B)</td>
                      <td class="px-4 py-2 text-right text-ink-gray-7">{{ (rcmSummary.portal ?? {}).available ? formatNumber((rcmSummary.portal ?? {}).rows) : NO_VALUE }}</td>
                      <td class="px-4 py-2 text-right text-ink-gray-8">{{ (rcmSummary.portal ?? {}).available ? formatCurrency(asNumber((rcmSummary.portal ?? {}).tax)) : NO_VALUE }}</td>
                    </tr>
                    <tr class="font-medium">
                      <td class="px-4 py-2 text-ink-gray-8" colspan="2">Gap</td>
                      <td class="px-4 py-2 text-right text-ink-gray-8">{{ formatCurrency(asNumber(rcmSummary.gap)) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div v-if="panExceptions.available" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader variant="caption" title="PAN exceptions" :hint="String(panSummary.statutory_basis ?? '')" :level="3" />
              <dl class="mt-4 space-y-2 text-sm">
                <div class="flex justify-between gap-3">
                  <dt class="text-ink-gray-7">Suppliers missing PAN</dt>
                  <dd class="tnum font-semibold text-ink-gray-8">{{ formatNumber(panSummary.suppliers_missing_pan) }}</dd>
                </div>
                <div class="flex justify-between gap-3">
                  <dt class="text-ink-gray-7">Transacted in window</dt>
                  <dd class="tnum font-semibold text-ink-gray-8">{{ formatNumber(panSummary.transacted_in_window) }}</dd>
                </div>
                <div class="flex justify-between gap-3">
                  <dt class="text-ink-gray-7">Exposure</dt>
                  <dd class="tnum font-semibold text-ink-gray-8">{{ formatCurrency(asNumber(panSummary.exposure)) }}</dd>
                </div>
              </dl>
            </div>
            <TabActions class="mt-6" :actions="tabBriefs.tds?.actions" />
          </div>

          <!-- Tax Planning -->
          <div v-if="activeTab === 'planning'" class="space-y-6">
            <TabBrief :brief="tabBriefs.planning" :as-of="data?.generated_at" />
            <StatStrip :items="planningStrip" />
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader variant="caption" title="Effective Tax Rate Trend" :level="3" />
                <div class="h-80 mt-4">
                  <IntelligenceChart v-if="effectiveRateTrendConfig" :config="effectiveRateTrendConfig" class="h-52 sm:h-64 lg:h-72" />
                  <div v-else class="h-full flex items-center justify-center text-ink-gray-6">No trend data available</div>
                </div>
                <table v-if="effectiveRateTrendConfig" class="sr-only">
                  <caption>Effective GST rate by month</caption>
                  <thead>
                    <tr>
                      <th scope="col">Month</th>
                      <th scope="col">Effective Rate (%)</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="d in gstSummary" :key="d.month">
                      <th scope="row">{{ d.month }}</th>
                      <td>{{ (d.total_revenue ?? 0) > 0 ? (((d.cgst ?? 0) + (d.sgst ?? 0) + (d.igst ?? 0)) / d.total_revenue! * 100).toFixed(2) + '%' : '0%' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader variant="caption" title="GST Forecast (Next 3 Months)" :level="3" />
                <div class="h-80 mt-4">
                  <IntelligenceChart v-if="taxForecastConfig" :config="taxForecastConfig" class="h-52 sm:h-64 lg:h-72" />
                  <div v-else class="h-full flex items-center justify-center text-ink-gray-6">No forecast data available</div>
                </div>
                <table v-if="taxForecastConfig" class="sr-only">
                  <caption>GST forecast: predicted net GST by period</caption>
                  <thead>
                    <tr>
                      <th scope="col">Period</th>
                      <th scope="col">Predicted Net GST (INR)</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="f in ((taxForecast.forecast ?? []) as TaxForecastRow[])" :key="f.month_offset">
                      <th scope="row">Month +{{ f.month_offset }}</th>
                      <td>{{ formatCurrency(f.projected_net_gst) }}</td>
                    </tr>
                  </tbody>
                </table>
                <p v-if="taxForecast.note" class="text-xs text-ink-gray-6 mt-2">{{ taxForecast.note }}</p>
                <p v-if="taxForecastCaveat" class="text-xs text-ink-gray-7 mt-1">{{ taxForecastCaveat }}</p>
              </div>
            </div>

            <!-- YTD Summary -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <KpiCard
                label="Total Revenue (YTD)"
                :amount="ytdRevenue"
                :currency="baseCurrency"
              />
              <KpiCard
                label="Total Output GST (YTD)"
                :amount="ytdOutputGst"
                :currency="baseCurrency"
              />
              <KpiCard
                label="ITC Set Off (Tax Saved)"
                :amount="itcHealth.utilised"
                :currency="baseCurrency"
              />
            </div>

            <!-- Advance Tax Schedule -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <div class="flex items-center justify-between mb-4">
                <SectionHeader variant="caption" title="Advance Tax Schedule" :level="3" />
                <Badge theme="gray" variant="subtle" label="Sec 207/208: Mandatory if liability >= Rs.10,000" size="sm" />
              </div>
              <div class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead class="bg-surface-gray-1">
                    <tr>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Instalment</th>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Due Date</th>
                      <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Cumulative %</th>
                      <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="inst in advanceTaxSchedule" :key="inst.label" class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
                      <td class="px-4 py-2 font-medium text-ink-gray-8">{{ inst.label }}</td>
                      <td class="px-4 py-2 font-medium text-ink-gray-7">{{ inst.due_date }}</td>
                      <td class="px-4 py-2 text-right">
                        <Badge theme="gray" variant="subtle" :label="inst.cumulative_pct + '%'" size="sm" />
                      </td>
                      <td class="px-4 py-2 text-ink-gray-6 text-xs">{{ inst.note }}</td>
                    </tr>
                    <tr v-if="!advanceTaxSchedule.length">
                      <td colspan="4" class="px-4 py-6 text-center text-ink-gray-6">No schedule available</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p class="mt-3 text-xs text-ink-gray-6">
                Late payment: 1% p.m. interest (Sec 234B/234C). Presumptive taxpayers (44AD/44ADA): entire tax due 15 Mar only.
              </p>
            </div>
            <TabActions class="mt-6" :actions="tabBriefs.planning?.actions" />
          </div>

          <!--
            Notices, Demands & Legal.

            Backed by the `JKM Tax Legal Case` register, which is empty on a
            site that has never recorded a matter. That empty state is stated
            as such rather than rendered as a healthy zero: "no notice on the
            register" and "no notice received" are different claims, and only
            the first one is true here.
          -->
          <div v-if="activeTab === 'legal'" class="space-y-6">
            <TabBrief :brief="tabBriefs.legal" :as-of="data?.generated_at" />
            <div class="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-5 gap-4">
              <KpiCard
                label="Open Matters"
                :value="asNumber(legalSummary.open)"
                :severity="(asNumber(legalSummary.open) ?? 0) > 0 ? 'high' : 'none'"
                sublabel="GST, income tax, TDS, customs"
              />
              <KpiCard
                label="Demand Under Review"
                :amount="asNumber(legalSummary.exposure)"
                :currency="baseCurrency"
                sublabel="Tax, interest and penalty claimed"
              />
              <KpiCard
                label="Provision Held"
                :amount="asNumber(legalSummary.provision)"
                :currency="baseCurrency"
                sublabel="Recognised against the demand"
              />
              <KpiCard
                label="Paid Under Protest"
                :amount="asNumber(legalSummary.paid_under_protest)"
                :currency="baseCurrency"
                sublabel="Recoverable on a favourable order"
              />
              <KpiCard
                label="Replies Due"
                :value="asNumber(legalSummary.due_soon)"
                :severity="(asNumber(legalSummary.overdue) ?? 0) > 0 ? 'critical' : (asNumber(legalSummary.due_soon) ?? 0) > 0 ? 'medium' : 'none'"
                :sublabel="`${formatNumber(legalSummary.overdue)} past the statutory date`"
              />
            </div>

            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <SectionHeader
                  variant="caption"
                  title="Notice, demand and legal case register"
                  hint="One controlled record per matter, with authority, exposure and closure"
                  :level="3"
                />
                <Button v-if="legalRows.length" variant="subtle" size="sm" @click="openLegalDrillDown()">
                  Open register
                </Button>
              </div>

              <div v-if="legalRows.length" class="mt-4 overflow-x-auto">
                <table class="w-full text-sm">
                  <caption class="sr-only">Legal and statutory matters on the register</caption>
                  <thead class="bg-surface-gray-1 text-left text-xs uppercase tracking-wide text-ink-gray-6">
                    <tr>
                      <th scope="col" class="px-4 py-2 font-medium">Matter</th>
                      <th scope="col" class="px-4 py-2 font-medium">Authority</th>
                      <th scope="col" class="px-4 py-2 font-medium text-right">Exposure</th>
                      <th scope="col" class="px-4 py-2 font-medium">Stage</th>
                      <th scope="col" class="px-4 py-2 font-medium">Reply due</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-outline-gray-1">
                    <tr v-for="c in legalRows" :key="c.name">
                      <td class="px-4 py-3">
                        <p class="font-medium text-ink-gray-8">{{ c.title }}</p>
                        <p class="mt-0.5 text-xs text-ink-gray-6">{{ c.case_type }}</p>
                      </td>
                      <td class="px-4 py-3 text-ink-gray-7">{{ c.authority || '-' }}</td>
                      <td class="px-4 py-3 text-right tnum text-ink-gray-8">
                        {{ formatCurrency(asNumber(c.total_exposure)) }}
                      </td>
                      <td class="px-4 py-3">
                        <Badge v-bind="severityBadge(prioritySeverity(c.risk_level))" :label="c.stage || c.status" size="sm" />
                      </td>
                      <td class="px-4 py-3 whitespace-nowrap text-ink-gray-7">
                        {{ formatDate(c.statutory_reply_date) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div v-else class="mt-4 rounded-lg border border-dashed border-outline-gray-2 px-4 py-6">
                <p class="text-sm font-medium text-ink-gray-8">No matter on the register</p>
                <p class="mt-1 text-sm text-ink-gray-6">
                  This reports the JKM Tax Legal Case register, not an absence of
                  correspondence. A notice, demand, assessment or hearing becomes
                  visible here once it is entered with its authority reference,
                  statutory reply date, exposure and owner.
                </p>
              </div>
            </div>

            <div v-if="legalCalendar.length" class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader
                variant="caption"
                title="Response and hearing calendar"
                hint="Legal dates carry the same discipline as filing dates"
                :level="3"
              />
              <div class="mt-4">
                <DateCalendar :rows="legalCalendar" />
              </div>
            </div>

            <div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-4">
              <p class="text-sm text-ink-gray-7">
                <strong class="font-medium text-ink-gray-8">Scope rule.</strong>
                A departmental demand does not become a payable here. Its amount,
                stage, advisor view, payment or stay status and the management
                decision are recorded separately, so a disputed claim is never
                silently booked as a liability.
              </p>
            </div>
            <TabActions class="mt-6" :actions="tabBriefs.legal?.actions" />
          </div>

          <!-- Customs: its own tab; the Bills of Entry register and the RCM comparison are not a legal matter. -->
          <div v-if="activeTab === 'customs'" class="space-y-6">
            <TabBrief :brief="tabBriefs.customs" :as-of="data?.generated_at" />
            <section class="space-y-6" aria-label="Customs and import duty">
              <SectionHeader variant="caption" title="Customs & Import Duty" :level="3" />
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
              <KpiCard
                label="Customs Duty Paid"
                :amount="asNumber(customsSummary.documents) ? asNumber(customsSummary.customs_duty) : null"
                :currency="baseCurrency"
                :sublabel="`${formatNumber(customsSummary.documents)} Bills of Entry`"
              />
              <KpiCard
                label="Unreconciled"
                :value="asNumber(customsSummary.unreconciled)"
                :severity="(asNumber(customsSummary.unreconciled) ?? 0) > 0 ? 'medium' : 'none'"
                sublabel="Not linked to a purchase invoice"
              />
              <KpiCard
                label="Reverse Charge Liability"
                :amount="asNumber((rcmSummary.books ?? {}).liability)"
                :currency="baseCurrency"
                :sublabel="`${formatNumber((rcmSummary.books ?? {}).invoices)} invoices self-assessed`"
              />
              <KpiCard
                label="RCM Net Cash"
                :amount="asNumber((rcmSummary.books ?? {}).net_cash)"
                :currency="baseCurrency"
                :severity="(asNumber((rcmSummary.books ?? {}).net_cash) ?? 0) > 0 ? 'medium' : 'none'"
                sublabel="Liability less the matching credit"
              />
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader
                  variant="caption"
                  title="Import tax reconciliation chain"
                  hint="Every shipment needs a complete operational and tax link"
                  :level="3"
                />
                <div class="mt-4">
                  <FlowSteps :steps="importControlFlow" orientation="vertical" />
                </div>
                <p v-if="customsSummary.note" class="mt-4 text-sm text-ink-gray-6">
                  {{ customsSummary.note }}
                </p>
              </div>

              <!--
                Reverse charge is shown as liability *and* credit rather than
                netted, because they are two separate ledger facts: the cash
                leaves on the liability and comes back as credit only if the
                input is eligible. A single net figure hides an ineligible
                self-assessment entirely.
              -->
              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader
                  variant="caption"
                  title="Reverse charge, books against portal"
                  hint="What we self-assessed, against what suppliers reported"
                  :level="3"
                />
                <div class="mt-4">
                  <WaterfallRows
                    :currency="baseCurrency"
                    :rows="[
                      { label: 'Self-assessed liability (books)', amount: asNumber((rcmSummary.books ?? {}).liability) ?? null, direction: 'neutral' },
                      { label: 'Matching input credit claimed', amount: asNumber((rcmSummary.books ?? {}).credit) ?? null, direction: 'negative' },
                      { label: 'Net cash impact', amount: asNumber((rcmSummary.books ?? {}).net_cash) ?? null, direction: 'neutral' },
                      { label: 'Reported as RCM by suppliers (GSTR-2A/2B)', amount: (rcmSummary.portal ?? {}).available ? asNumber((rcmSummary.portal ?? {}).tax) ?? null : null, direction: 'neutral' },
                    ]"
                  />
                </div>
                <p v-if="asNumber(rcmSummary.gap)" class="mt-4 text-sm text-ink-gray-7">
                  {{ formatCurrency(asNumber(rcmSummary.gap)) }} difference between our
                  self-assessment and supplier reporting. This is a reconciliation
                  finding, not an accounting error: it is their filing, not our
                  liability.
                </p>
              </div>
            </div>
            </section>
            <TabActions class="mt-6" :actions="tabBriefs.customs?.actions" />
          </div>
          <!--
            Action Queue: the operational engine. No exception, notice or
            deadline should sit here as an unread report row, so every row
            carries owner, date and the money at stake, and the filters are
            the ones a review actually sorts by.
          -->
          <div v-if="activeTab === 'actions'" class="space-y-6">
            <TabBrief :brief="tabBriefs.actions" :as-of="data?.generated_at" />
            <StatStrip :items="actionsStrip" :currency="baseCurrency" />

            <div v-if="queueByPriority.length || queueByOwnerRole.length" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader variant="caption" title="By monetary impact" :level="3" />
                <dl class="mt-4 space-y-3">
                  <div
                    v-for="p in queueByPriority"
                    :key="p.key"
                    class="flex items-baseline justify-between gap-4"
                  >
                    <dt class="flex items-center gap-2 text-sm text-ink-gray-7">
                      <span class="h-2 w-2 shrink-0 rounded-full" :class="severityFill(prioritySeverity(p.key))" aria-hidden="true" />
                      {{ p.key }}
                      <span class="text-ink-gray-6">· {{ p.count }}</span>
                    </dt>
                    <dd class="tnum text-sm font-medium text-ink-gray-8">
                      {{ formatCurrency(asNumber(p.exposure)) }}
                    </dd>
                  </div>
                </dl>
              </div>

              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader variant="caption" title="By responsible function" :level="3" />
                <dl class="mt-4 space-y-3">
                  <div
                    v-for="o in queueByOwnerRole"
                    :key="o.key"
                    class="flex items-baseline justify-between gap-4"
                  >
                    <dt class="text-sm text-ink-gray-7">
                      {{ o.key }}
                      <span class="text-ink-gray-6">· {{ o.count }}</span>
                    </dt>
                    <dd class="tnum text-sm font-medium text-ink-gray-8">
                      {{ formatCurrency(asNumber(o.exposure)) }}
                    </dd>
                  </div>
                </dl>
              </div>
            </div>

            <div v-if="queueRows.length" class="space-y-4">
              <!--
                Cards, not a table. Each row has to answer four questions the
                reader asks in sequence -- what happened, what it costs, what
                closes it, who owes the answer -- and the corrective steps are
                prose from the detector, which a table cell cannot hold
                without truncating the one part that says what to do.
              -->
              <article
                v-for="row in queueRows"
                :key="row.name"
                class="rounded-lg border border-outline-gray-1 bg-surface-white p-5"
              >
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                      <Badge
                        v-bind="severityBadge(row.overdue ? 'critical' : prioritySeverity(row.priority))"
                        :label="row.overdue ? 'Overdue' : row.priority"
                        size="sm"
                      />
                      <span class="text-xs uppercase tracking-wide text-ink-gray-6">{{ row.area }}</span>
                    </div>
                    <h4 class="mt-2 text-base font-medium text-ink-gray-9">{{ row.title }}</h4>
                  </div>
                  <div class="text-right">
                    <p class="tnum text-lg font-semibold text-ink-gray-9">
                      {{ formatCurrency(asNumber(row.exposure)) }}
                    </p>
                    <p class="text-xs text-ink-gray-6">at stake</p>
                  </div>
                </div>

                <p v-if="row.rationale" class="mt-3 text-sm text-ink-gray-7">{{ row.rationale }}</p>

                <p v-if="row.steps" class="mt-3 whitespace-pre-line rounded-lg bg-surface-gray-1 p-3 text-sm text-ink-gray-7">
                  {{ row.steps }}
                </p>

                <dl class="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <div class="min-w-0">
                    <dt class="text-xs text-ink-gray-6">Owner</dt>
                    <dd class="mt-0.5 text-sm text-ink-gray-8">{{ row.owner_role || 'Unassigned' }}</dd>
                  </div>
                  <div class="min-w-0">
                    <dt class="text-xs text-ink-gray-6">Assigned to</dt>
                    <dd class="mt-0.5 text-sm" :class="row.assigned_to ? 'text-ink-gray-8' : 'text-ink-gray-5'">
                      {{ row.assigned_to || 'Nobody' }}
                    </dd>
                  </div>
                  <div class="min-w-0">
                    <dt class="text-xs text-ink-gray-6">Due</dt>
                    <dd class="mt-0.5 text-sm" :class="row.overdue ? 'text-ink-red-4' : 'text-ink-gray-8'">
                      {{ formatDate(row.due_date) }}
                    </dd>
                  </div>
                  <div class="min-w-0">
                    <dt class="text-xs text-ink-gray-6">Age</dt>
                    <dd class="mt-0.5 text-sm text-ink-gray-8">
                      {{ row.age_days !== undefined && row.age_days !== null ? `${row.age_days} days` : '-' }}
                    </dd>
                  </div>
                </dl>
              </article>
            </div>

            <div v-else class="rounded-lg border border-dashed border-outline-gray-2 bg-surface-white px-4 py-8 text-center">
              <CheckCircle class="mx-auto h-6 w-6 text-ink-green-3" aria-hidden="true" />
              <p class="mt-2 text-sm font-medium text-ink-gray-8">No open tax exception</p>
              <p class="mt-1 text-sm text-ink-gray-6">
                The detectors scan the whole ledger weekly, so this is a clear
                board rather than an empty window.
              </p>
            </div>

            <!--
              PAN control sits on the queue rather than under TDS: a missing
              PAN is not a measurement of TDS, it is a master-data exception
              that has to be fixed before the next challan is paid.
            -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <SectionHeader
                  variant="caption"
                  title="PAN exceptions on deducted suppliers"
                  :hint="panSummary.statutory_basis"
                  :level="3"
                />
                <Button v-if="asNumber(panSummary.suppliers_missing_pan)" variant="subtle" size="sm" @click="openPanDrillDown()">
                  View suppliers
                </Button>
              </div>
              <p class="mt-3 text-sm" :class="asNumber(panSummary.suppliers_missing_pan) ? 'text-ink-gray-7' : 'text-ink-gray-6'">
                <template v-if="asNumber(panSummary.suppliers_missing_pan)">
                  {{ formatNumber(panSummary.suppliers_missing_pan) }} suppliers we
                  deduct from have no PAN on file, carrying
                  {{ formatCurrency(asNumber(panSummary.exposure)) }} already deducted
                  at the ordinary rate. Collect the PAN before the next challan.
                </template>
                <template v-else>
                  Every supplier we deduct TDS from has a PAN on file.
                </template>
              </p>
            </div>
            <TabActions class="mt-6" :actions="tabBriefs.actions?.actions" />
          </div>
        </div>
      </div>
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
