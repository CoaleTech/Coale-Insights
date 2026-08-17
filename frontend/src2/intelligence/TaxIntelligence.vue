<script setup lang="ts">
import IntelligenceChart from './components/IntelligenceChart.vue'
defineOptions({ name: 'TaxIntelligence' })
import { Breadcrumbs, Button, Badge, Select, Tabs } from 'frappe-ui'
import {
  RefreshCcw, AlertTriangle, CheckCircle, FileText,
} from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useIntelligenceDashboard } from './composables/useIntelligenceDashboard'
import { severityBadge, severityFill, scoreSeverity, deltaInk, type Severity } from '../utils/status'
import { formatCount, formatMoney, formatPercent as sharedPercent } from '../utils/format'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import BaseChart from '../charts/components/BaseChart.vue'
import KpiCard from './components/KpiCard.vue'
import IntelligenceDashboardShell from './components/IntelligenceDashboardShell.vue'
import SectionHeader from './components/SectionHeader.vue'
import SkeletonBlock from './components/SkeletonBlock.vue'
import { useDrillDown } from './composables/useDrillDown'
import IntelligenceDrillDown from './components/IntelligenceDrillDown.vue'
import { chartPalette, themeColor } from '../utils/chartTheme'

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
  tax_forecast?: { forecast?: TaxForecastRow[]; note?: string; [k: string]: unknown }
  advance_tax_schedule?: Record<string, any>[]
  einvoice_compliance_info?: Record<string, unknown>
  counterparty_risk?: Record<string, unknown>
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

const tabs = [
  { label: 'GST Overview' },
  { label: 'Compliance Health' },
  { label: 'TDS' },
  { label: 'Tax Planning' },
]

const TAB_IDS = ['gst', 'compliance', 'tds', 'planning'] as const
const activeTab = computed(() => TAB_IDS[activeTabIndex.value] ?? 'gst')

const gstSummary = computed((): GstSummaryRow[] =>
  (data.value?.gst_summary ?? []) as unknown as GstSummaryRow[]
)
const itcHealth = computed((): Record<string, any> => (data.value?.itc_health ?? {}) as Record<string, any>)
const tdsSummary = computed((): Record<string, any> => (data.value?.tds_summary ?? {}) as Record<string, any>)
const einvoiceStatus = computed((): Record<string, any> => (data.value?.einvoice_status ?? {}) as Record<string, any>)
const ewaybillStatus = computed((): Record<string, any> => (data.value?.ewaybill_status ?? {}) as Record<string, any>)
const filingCompliance = computed((): Record<string, any> => (data.value?.filing_compliance ?? {}) as Record<string, any>)
const reconciliationScore = computed((): Record<string, any> => (data.value?.reconciliation_score ?? {}) as Record<string, any>)
const hsnSummary = computed((): Record<string, any>[] => (data.value?.hsn_summary ?? []) as Record<string, any>[])
const taxForecast = computed((): Record<string, any> => (data.value?.tax_forecast ?? {}) as Record<string, any>)
const advanceTaxSchedule = computed((): Record<string, any>[] => (data.value?.advance_tax_schedule ?? []) as Record<string, any>[])
const einvoiceInfo = computed((): Record<string, any> => (data.value?.einvoice_compliance_info ?? {}) as Record<string, any>)
const counterpartyRisk = computed((): Record<string, any> => (data.value?.counterparty_risk ?? {}) as Record<string, any>)

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
function filingSeverity(status: string | undefined | null): Severity {
  const s = String(status ?? '')
  if (s === 'Filed' || s === 'Compliant') return 'none'
  if (s === 'Pending' || s === 'Due') return 'medium'
  return 'high'
}

function rateSeverity(rate: number | undefined | null): Severity {
  return scoreSeverity(rate, { good: 18, warn: 25, higherIsBetter: false })
}

function complianceSeverity(score: number | undefined | null): Severity {
  return scoreSeverity(score, { good: 80, warn: 60, higherIsBetter: true })
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
  return formatMoney(value, baseCurrency.value, { compact: true })
}
function formatNumber(value: number | null | undefined): string { return formatCount(value) }
function formatPercent(value: number | null | undefined): string { return sharedPercent(value) }

const gstStackedBarConfig = computed(() => {
  if (!gstSummary.value.length) return null
  const palette = chartPalette(3)
  return {
    data: gstSummary.value.map((d: GstSummaryRow) => ({
      month: d.month,
      CGST: d.cgst ?? 0,
      SGST: d.sgst ?? 0,
      IGST: d.igst ?? 0,
    })),
    title: '',
    xAxis: { key: 'month', type: 'category' as const },
    yAxis: { title: 'Amount (INR)' },
    stacked: true,
    series: [
      { name: 'CGST', type: 'bar' as const, color: palette[0] },
      { name: 'SGST', type: 'bar' as const, color: palette[1] },
      { name: 'IGST', type: 'bar' as const, color: palette[2] },
    ],
  }
})

const itcGaugeOptions = computed(() => {
  const pct = itcHealth.value.utilization_pct || 0
  return {
    series: [{
      type: 'gauge', startAngle: 180, endAngle: 0, min: 0, max: 100,
      axisLine: { lineStyle: { width: 10, color: [[0.3, themeColor('--app-neg-fill')], [0.7, themeColor('--app-warn-fill')], [1, themeColor('--app-pos-fill')]] } },
      pointer: { itemStyle: { color: 'auto' } },
      axisTick: { distance: -10, length: 6, lineStyle: { color: '#fff', width: 1 } },
      splitLine: { distance: -10, length: 14, lineStyle: { color: '#fff', width: 2 } },
      axisLabel: { color: 'inherit', distance: 18, fontSize: 10 },
      detail: { valueAnimation: true, formatter: '{value}%', color: 'inherit', fontSize: 24, offsetCenter: [0, '30%'] },
      data: [{ value: pct, name: 'Utilization' }],
    }],
  }
})

const tdsBarConfig = computed(() => {
  // Cast once: payable_by_section is an untyped API payload array.
  const sections: TdsSectionRow[] = ((tdsSummary.value.payable_by_section ?? []) as unknown as TdsSectionRow[]).slice(0, 5)
  if (!sections.length) return null
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
      { name: 'Net GST', type: 'line' as const, lineType: 'dashed' as const, color: themeColor('--app-accent-strong') },
    ],
  }
})

const ytdRevenue = computed(() =>
  gstSummary.value.reduce((s: number, d: GstSummaryRow) => s + (d.total_revenue || 0), 0)
)
const ytdOutputGst = computed(() =>
  gstSummary.value.reduce((s: number, d: GstSummaryRow) => s + (d.cgst || 0) + (d.sgst || 0) + (d.igst || 0), 0)
)

const chatContext = computed(() => ({
  summary: { net_gst: data.value?.net_gst, effective_tax_rate: data.value?.effective_tax_rate, compliance_score: data.value?.compliance_score },
  gst_summary: gstSummary.value, itc_health: itcHealth.value, tds_summary: tdsSummary.value,
  einvoice_status: einvoiceStatus.value, ewaybill_status: ewaybillStatus.value,
  filing_compliance: filingCompliance.value, reconciliation_score: reconciliationScore.value,
  hsn_summary: hsnSummary.value, tax_forecast: taxForecast.value,
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
</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <div class="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between px-6 py-4 bg-surface-white border-b border-outline-gray-1">
      <div>
        <Breadcrumbs :items="[{ label: 'Dashboards', route: '/dashboards' }, { label: 'Tax Intelligence' }]" />
        <h1 class="text-2xl font-bold text-ink-gray-9 mt-1">Tax Intelligence</h1>
        <p class="text-sm text-ink-gray-6">India GST, TDS, ITC analytics, compliance monitoring, and tax planning</p>
      </div>
      <div class="flex items-center gap-3">
        <Select
          v-model="dateFilter"
          :options="dateRangeOptions"
          class="text-sm"
        />

        <Button
          :loading="refreshing"
          variant="solid"
          theme="gray"
          @click="reload"
        >
          <RefreshCcw class="w-4 h-4 mr-2" />
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

      <!-- Summary Cards -->
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
        <KpiCard
          label="Net GST Payable"
          :value="formatCurrency(data?.net_gst)"
          sublabel="Output - Input Tax Credit"
        />
        <KpiCard
          label="Effective Tax Rate"
          :value="formatPercent(data?.effective_tax_rate)"
          :severity="rateSeverity(data?.effective_tax_rate)"
          :sublabel="(data?.effective_tax_rate ?? 0) > 25 ? 'High' : (data?.effective_tax_rate ?? 0) > 18 ? 'Moderate' : 'Optimal'"
        />
        <KpiCard
          label="ITC Utilisation"
          :value="formatPercent(itcHealth.utilization_pct)"
          :severity="complianceSeverity(itcHealth.utilization_pct)"
          sublabel="Input Tax Credit"
        />
        <KpiCard
          label="TDS Payable"
          :value="formatCurrency(tdsSummary.total_payable)"
          sublabel="Tax Deducted at Source"
        />
        <KpiCard
          label="e-Invoice Coverage"
          :value="formatPercent(einvoiceStatus.coverage_pct)"
          :severity="complianceSeverity(einvoiceStatus.coverage_pct)"
          sublabel="IRN filing rate"
        />
        <KpiCard
          label="Compliance Score"
          :value="data?.compliance_score" unit="/100"
          :severity="complianceSeverity(data?.compliance_score)"
          sublabel="e-Invoice, Filing, Recon"
        />
      </div>

      <!-- Tabs -->
      <div class="bg-surface-white rounded-lg border border-outline-gray-1 mb-6">
        <Tabs v-model="activeTabIndex" :tabs="tabs" />

        <div class="p-6">

          <!-- GST Overview -->
          <div v-if="activeTab === 'gst'" class="space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader variant="caption" title="Monthly GST Breakdown (CGST / SGST / IGST)" :level="3" />
                <div class="h-52 sm:h-64 lg:h-72 mt-4">
                  <IntelligenceChart v-if="gstStackedBarConfig" :config="gstStackedBarConfig" class="h-52 sm:h-64 lg:h-72" />
                  <div v-else class="h-full flex items-center justify-center text-ink-gray-6">No GST data available</div>
                </div>
                <table v-if="gstStackedBarConfig" class="sr-only">
                  <caption>Monthly GST breakdown: CGST, SGST, and IGST by month</caption>
                  <thead>
                    <tr>
                      <th scope="col">Month</th>
                      <th scope="col">CGST (INR)</th>
                      <th scope="col">SGST (INR)</th>
                      <th scope="col">IGST (INR)</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="d in gstSummary" :key="d.month">
                      <th scope="row">{{ d.month }}</th>
                      <td>{{ formatCurrency(d.cgst ?? 0) }}</td>
                      <td>{{ formatCurrency(d.sgst ?? 0) }}</td>
                      <td>{{ formatCurrency(d.igst ?? 0) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader variant="caption" title="ITC Utilisation" :level="3" />
                <div class="h-52 sm:h-64 lg:h-72 mt-4">
                  <BaseChart :options="itcGaugeOptions" />
                </div>
                <div class="grid grid-cols-2 gap-4 mt-4">
                  <KpiCard
                    label="Available"
                    :amount="itcHealth.available"
                    :currency="baseCurrency"
                    variant="tile"
                  />
                  <KpiCard
                    label="Claimed"
                    :amount="itcHealth.claimed"
                    :currency="baseCurrency"
                    variant="tile"
                  />
                </div>
              </div>
            </div>

            <!-- Filing Status -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div class="p-4 rounded-lg border border-outline-gray-1 bg-surface-white">
                <div class="flex items-center justify-between">
                  <div>
                    <p class="text-sm font-medium text-ink-gray-9">GSTR-1</p>
                    <Badge
                      v-bind="severityBadge(filingSeverity(filingCompliance.gstr1?.status))"
                      :label="filingCompliance.gstr1?.status || 'No Data'"
                      size="sm"
                      class="mt-1"
                    />
                  </div>
                  <FileText class="w-8 h-8 text-ink-gray-5" aria-hidden="true" />
                </div>
                <p class="text-sm mt-2 text-ink-gray-6">
                  Filed: <span class="font-medium text-ink-gray-8">{{ filingCompliance.gstr1?.filed || 0 }}</span>
                </p>
              </div>
              <div class="p-4 rounded-lg border border-outline-gray-1 bg-surface-white">
                <div class="flex items-center justify-between">
                  <div>
                    <p class="text-sm font-medium text-ink-gray-9">GSTR-3B</p>
                    <Badge
                      v-bind="severityBadge(filingSeverity(filingCompliance.gstr3b?.status))"
                      :label="filingCompliance.gstr3b?.status || 'No Data'"
                      size="sm"
                      class="mt-1"
                    />
                  </div>
                  <FileText class="w-8 h-8 text-ink-gray-5" aria-hidden="true" />
                </div>
                <p class="text-sm mt-2 text-ink-gray-6">
                  Filed: <span class="font-medium text-ink-gray-8">{{ filingCompliance.gstr3b?.filed || 0 }}</span>
                </p>
              </div>
            </div>

            <!-- HSN Summary -->
            <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
              <SectionHeader variant="caption" title="HSN Summary (Top 10 by Revenue)" :level="3" />
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
                      v-for="hsn in hsnSummary.slice(0, 10)"
                      :key="hsn.hsn_code"
                      class="border-b border-outline-gray-1 hover:bg-surface-gray-1 cursor-pointer transition-colors motion-reduce:transition-none"
                      tabindex="0"
                      @click="openHsnDrillDown(hsn)"
                      @keydown.enter="openHsnDrillDown(hsn)"
                    >
                      <td class="px-4 py-2 font-medium text-ink-gray-8">{{ hsn.hsn_code || '—' }}</td>
                      <td class="px-4 py-2 text-right text-ink-gray-7">{{ formatCurrency(hsn.revenue) }}</td>
                      <td class="px-4 py-2 text-right text-ink-gray-7">{{ formatCurrency(hsn.actual_gst) }}</td>
                      <td class="px-4 py-2 text-right">
                        <Badge
                          v-bind="severityBadge(hsnRateSeverity(hsn.effective_gst_rate))"
                          :label="formatPercent(hsn.effective_gst_rate)"
                          size="sm"
                        />
                      </td>
                      <td class="px-4 py-2 text-right text-ink-gray-7">{{ formatNumber(hsn.invoice_count) }}</td>
                    </tr>
                    <tr v-if="!hsnSummary.length">
                      <td colspan="5" class="px-4 py-6 text-center text-ink-gray-6">No HSN data available</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- Compliance Health -->
          <div v-if="activeTab === 'compliance'" class="space-y-6">
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
                  :value="String(reconciliationScore.unactioned_count ?? 0)"
                  :severity="(reconciliationScore.unactioned_count ?? 0) > 0 ? 'medium' : 'none'"
                  :sublabel="
                    reconciliationScore.data_through
                      ? `Reconciled only to ${reconciliationScore.data_through}`
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
                    {{ counterpartyRisk.registry_total ?? 0 }} tracked
                  </p>
                </div>
                <dl class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div>
                    <dt class="text-sm text-ink-gray-6">Active</dt>
                    <dd class="tnum text-lg font-semibold text-ink-gray-9">
                      {{ counterpartyRisk.active ?? 0 }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-sm text-ink-gray-6">Cancelled</dt>
                    <dd class="tnum text-lg font-semibold" :class="deltaInk(-(counterpartyRisk.cancelled ?? 0))">
                      {{ counterpartyRisk.cancelled ?? 0 }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-sm text-ink-gray-6">Suspended</dt>
                    <dd class="tnum text-lg font-semibold text-ink-gray-9">
                      {{ counterpartyRisk.suspended ?? 0 }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-sm text-ink-gray-6">Blocked, Rule 86A</dt>
                    <dd class="tnum text-lg font-semibold" :class="deltaInk(-(counterpartyRisk.blocked ?? 0))">
                      {{ counterpartyRisk.blocked ?? 0 }}
                    </dd>
                  </div>
                </dl>
                <p class="mt-3 text-sm text-ink-gray-6">
                  <template v-if="(counterpartyRisk.transacted_at_risk_parties ?? 0) > 0">
                    {{ counterpartyRisk.transacted_at_risk_parties }} of these were
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
                  v-bind="severityBadge(complianceSeverity(einvoiceStatus.coverage_pct))"
                  :label="severityBadge(complianceSeverity(einvoiceStatus.coverage_pct)).label"
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
                  {{ reconciliationScore.reconciliation_score || 0 }}/100
                </p>
                <Badge
                  v-bind="severityBadge(complianceSeverity(reconciliationScore.reconciliation_score))"
                  :label="severityBadge(complianceSeverity(reconciliationScore.reconciliation_score)).label"
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
                v-if="filingCompliance.gstr1?.status !== 'Filed' && filingCompliance.gstr1?.status !== 'Compliant'"
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
                      <span v-if="filingCompliance.gstr1?.status !== 'Filed' && filingCompliance.gstr1?.status !== 'Compliant'">GSTR-1 is pending. </span>
                      <span v-if="filingCompliance.gstr3b?.status !== 'Filed' && filingCompliance.gstr3b?.status !== 'Compliant'">GSTR-3B is pending.</span>
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
                v-if="(itcHealth.utilizable || 0) > 0 && (itcHealth.utilization_pct || 0) < 70"
                class="p-4 bg-surface-white border border-outline-gray-1 rounded-lg"
              >
                <div class="flex items-start gap-3">
                  <CheckCircle class="w-5 h-5 text-ink-gray-6 flex-shrink-0 mt-0.5" aria-hidden="true" />
                  <div>
                    <div class="flex items-center gap-2 mb-1">
                      <p class="font-medium text-ink-gray-9">Unutilised ITC</p>
                      <Badge v-bind="severityBadge('medium')" :label="severityBadge('medium').label" size="sm" />
                    </div>
                    <p class="text-sm text-ink-gray-7">{{ formatCurrency(itcHealth.utilizable) }} of ITC is still utilisable. Review blocked/ineligible credits.</p>
                  </div>
                </div>
              </div>

              <div
                v-if="(filingCompliance.gstr1?.status === 'Filed' || filingCompliance.gstr1?.status === 'Compliant')
                    && (filingCompliance.gstr3b?.status === 'Filed' || filingCompliance.gstr3b?.status === 'Compliant')
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
          </div>

          <!-- TDS -->
          <div v-if="activeTab === 'tds'" class="space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <KpiCard
                label="TDS Payable"
                :amount="tdsSummary.total_payable"
                :currency="baseCurrency"
              />
              <KpiCard
                label="TDS Receivable"
                :amount="tdsSummary.receivable"
                :currency="baseCurrency"
              />
              <KpiCard
                label="Net Position"
                :amount="tdsSummary.net_position"
                :currency="baseCurrency"
                :severity="(tdsSummary.net_position ?? 0) < 0 ? 'medium' : 'none'"
              />
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader variant="caption" title="TDS Payable by Section" :level="3" />
                <div class="overflow-x-auto mt-4">
                  <table class="w-full text-sm">
                    <thead class="bg-surface-gray-1">
                      <tr>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Section</th>
                        <th scope="col" class="px-4 py-2 text-left text-ink-gray-6">Nature of Payment</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">Rate</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">TDS Amount</th>
                        <th scope="col" class="px-4 py-2 text-right text-ink-gray-6">% of Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="sec in (tdsSummary.payable_by_section || [])" :key="sec.section" class="border-b border-outline-gray-1 hover:bg-surface-gray-1">
                        <td class="px-4 py-2 font-medium text-ink-gray-8">
                          <Badge v-if="sec.section_code" theme="gray" variant="subtle" :label="sec.section_code" size="sm" class="mr-1" />
                          <span v-else class="text-ink-gray-7 text-xs">{{ sec.section }}</span>
                        </td>
                        <td class="px-4 py-2 text-ink-gray-7">{{ sec.description || sec.section }}</td>
                        <td class="px-4 py-2 text-right text-ink-gray-7">
                          {{ sec.rate_pct != null ? `${sec.rate_pct}%` : '—' }}
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
                        <td colspan="5" class="px-4 py-6 text-center text-ink-gray-6">No TDS data available</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader variant="caption" title="Top 5 TDS Sections" :level="3" />
                <div class="h-52 sm:h-64 lg:h-72 mt-4">
                  <IntelligenceChart v-if="tdsBarConfig" :config="tdsBarConfig" class="h-52 sm:h-64 lg:h-72" />
                  <div v-else class="h-full flex items-center justify-center text-ink-gray-6">No TDS section data available</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Tax Planning -->
          <div v-if="activeTab === 'planning'" class="space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div class="bg-surface-white rounded-lg border border-outline-gray-1 p-6">
                <SectionHeader variant="caption" title="Effective Tax Rate Trend" :level="3" />
                <div class="h-52 sm:h-64 lg:h-72 mt-4">
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
                <div class="h-52 sm:h-64 lg:h-72 mt-4">
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
                label="ITC Claimed (Tax Saved)"
                :amount="itcHealth.claimed"
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
