<script setup lang="ts">
defineOptions({ name: 'RiskIntelligence' })
import { ref, computed } from 'vue'
import { Badge, Button, Tabs } from 'frappe-ui'
import { useRouter } from 'vue-router'
import DashboardChatButton from '../components/DashboardChatButton.vue'
import { useDrillDown } from '../intelligence/composables/useDrillDown'
import IntelligenceDrillDown from '../intelligence/components/IntelligenceDrillDown.vue'
import { useIntelligenceDashboard } from '../intelligence/composables/useIntelligenceDashboard'
import KpiCard from '../intelligence/components/KpiCard.vue'
import SectionHeader from '../intelligence/components/SectionHeader.vue'
import {
  severityBadge, severityFill, severityAria, scoreSeverity, type Severity,
} from '../utils/status'
import { formatCount, formatDateTime, NO_VALUE } from '../utils/format'

const router = useRouter()
const drillDown = useDrillDown()
const RISK_ENDPOINT = 'insights.api.ml.risk.get_risk_detail'

// Minimal shapes that keep templates type-safe without casts
interface RiskAlert { severity: string; title: string; description: string; action: string }
interface RiskComponent { score: number; category: string }
interface RiskComponents { credit_risk?: RiskComponent; cashflow_risk?: RiskComponent; operational_risk?: RiskComponent; compliance_risk?: RiskComponent }

/** Risk assessment matrix row. */
interface RiskMatrixRow { name: string; category?: string; probability: number; impact: number; risk_score?: number; risk_category?: string }
/** Receivables aging bucket. */
interface AgingBucket { aging_bucket: string; outstanding_amount?: number; invoice_count?: number }
/** Customer credit risk score row. */
interface CustomerRiskScore { customer: string; customer_name?: string; outstanding?: number; avg_overdue_days?: number; risk_category?: string; risk_score?: number }
/** Revenue concentration customer row. */
interface ConcentrationCustomer { customer: string; customer_name?: string; revenue?: number; revenue_share: number }
/** Overdue days trend period row. */
interface DSOPeriod { period: string; avg_days_overdue?: number }
/** Inventory risk by item group row. */
interface InventoryRiskRow { item_group: string; total_items?: number; stockout_items: number; stock_value?: number; risk_category?: string }
/** Supplier reliability row from operational risk. */
interface SupplierReliabilityRow { supplier: string; supplier_name?: string; total_orders?: number; total_value?: number; avg_delay_days?: number; risk_category?: string }
/** KRA compliance status block. */
interface KraStatus { vat_filing_status?: string; last_filing_date?: string; next_filing_due?: string; outstanding_penalties?: number }
/** Document completeness audit row. */
interface DocumentAuditRow { document_type: string; total_docs: number; incomplete_docs: number }
/** License and permit row. */
interface LicenseRow { license_type: string; expiry_date?: string; status?: string; risk_level?: string }
/** Financial anomaly row. */
interface AnomalyRow { type: string; description?: string; date?: string; severity?: string }
/** Early warning alert row. */
interface EarlyWarningRow { title?: string; description?: string; timeframe?: string; severity?: string }
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
/** Typed cashflow risk sub-section. */
interface CashflowSection {
  current_cash_position?: number
  current_working_capital?: number
  working_capital_ratio?: number
  top_customer_share?: number
  customer_concentration?: ConcentrationCustomer[]
  overdue_days_trend?: DSOPeriod[]
}
/** Typed operational risk sub-section. */
interface OperationalSection {
  process_risks?: Record<string, number | undefined>
  inventory_risks?: InventoryRiskRow[]
  supplier_performance?: SupplierReliabilityRow[]
}
/** Typed compliance risk sub-section. */
interface ComplianceSection {
  kra_status?: KraStatus
  document_audit?: DocumentAuditRow[]
  licenses?: LicenseRow[]
}
/** Typed predictive analytics sub-section. */
interface PredictiveSection {
  cash_flow_forecast?: { status?: string }
  revenue_forecast?: { status?: string }
  forecast_confidence?: string
  anomalies?: AnomalyRow[]
  early_warnings?: EarlyWarningRow[]
  payment_risk_forecast?: { high_risk_customers?: PaymentRiskCustomer[] }
}

interface RiskIntelligenceData {
  overview: OverviewSection
  credit_risk: CreditSection
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
  hasData,
  reload,
  retry,
} = useIntelligenceDashboard<RiskIntelligenceData>({
  url: 'insights.api.ml.risk_intelligence',
  cache: 'risk-intelligence',
})

const overviewData = computed(() => riskData.value?.overview ?? ({} as OverviewSection))
const creditData = computed(() => riskData.value?.credit_risk ?? ({} as CreditSection))
const cashflowData = computed(() => riskData.value?.cashflow_risk ?? ({} as CashflowSection))
const operationalData = computed(() => riskData.value?.operational_risk ?? ({} as OperationalSection))
const complianceData = computed(() => riskData.value?.compliance_risk ?? ({} as ComplianceSection))
const predictiveData = computed(() => riskData.value?.predictive_analytics ?? ({} as PredictiveSection))
const baseCurrency = computed(() => riskData.value?.base_currency ?? 'KES')
const lastUpdated = computed(() => riskData.value?.generated_at ?? null)

// Tabs - numeric index for frappe-ui Tabs component
const tabDefs = [
  { label: 'Overview', value: 'overview' },
  { label: 'Credit Risk', value: 'credit' },
  { label: 'Cash Flow Risk', value: 'cashflow' },
  { label: 'Operational Risk', value: 'operational' },
  { label: 'Compliance Risk', value: 'compliance' },
  { label: 'Predictive Analytics', value: 'predictive' },
]
const activeTabIndex = ref(0)
const activeTab = computed(() => tabDefs[activeTabIndex.value]?.value ?? 'overview')
const tabsForComponent = tabDefs.map(t => ({ label: t.label }))

// Summary derived from the overview sub-object
const summary = computed(() => {
  const overview = overviewData.value
  const components = (overview.risk_components ?? {}) as RiskComponents
  const alerts = (overview.alerts as RiskAlert[]) ?? []
  return {
    overallScore: (overview.aggregate_risk_score as number) || 0,
    overallRisk: (overview.aggregate_risk_category as string) || 'Low',
    creditScore: components.credit_risk?.score || 0,
    creditRisk: components.credit_risk?.category || 'Low',
    cashflowScore: components.cashflow_risk?.score || 0,
    cashflowRisk: components.cashflow_risk?.category || 'Low',
    operationalScore: components.operational_risk?.score || 0,
    operationalRisk: components.operational_risk?.category || 'Low',
    complianceScore: components.compliance_risk?.score || 0,
    complianceRisk: components.compliance_risk?.category || 'Low',
    activeAlerts: alerts.length,
    criticalAlerts: alerts.filter(a => a.severity === 'critical').length,
  }
})

// Risk score: higher = worse, so higherIsBetter: false.
// Thresholds mirror the original bar colouring: <=20 low, <=40 medium, else high.
function riskScoreSeverity(score: number): Severity {
  return scoreSeverity(score, { good: 20, warn: 40, higherIsBetter: false })
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

const formatCurrency = (value: number | null | undefined) => {
  if (!value) return NO_VALUE
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: baseCurrency.value,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}


</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1">
    <!-- Header -->
    <header class="bg-surface-white border-b border-outline-gray-1 px-6 py-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-ink-gray-9">Risk Intelligence & Analytics</h1>
        <p v-if="lastUpdated" class="text-sm text-ink-gray-6 mt-1">
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

    <!-- Permission Error -->
    <div v-if="isPermissionError" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <p class="text-base font-medium text-ink-gray-9">Access Restricted</p>
        <p class="text-sm text-ink-gray-6 mt-2">You do not have permission to view this dashboard.</p>
      </div>
    </div>

    <!-- Generic Error -->
    <div v-else-if="error" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <p class="text-base font-medium text-ink-gray-9">Failed to load risk data</p>
        <p class="text-sm text-ink-gray-6 mt-1">{{ error }}</p>
        <Button variant="subtle" theme="gray" class="mt-4" @click="retry">Try Again</Button>
      </div>
    </div>

    <template v-else>
      <!-- Summary Cards -->
      <div class="p-6 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard
          label="Overall Risk Score"
          :value="hasData ? `${summary.overallScore}/100` : 'N/A'"
          :severity="hasData ? riskScoreSeverity(summary.overallScore) : undefined"
          :loading="loading"
        />
        <KpiCard
          label="Credit Risk"
          :value="hasData ? `${summary.creditScore}/100` : 'N/A'"
          :severity="hasData ? riskScoreSeverity(summary.creditScore) : undefined"
          :loading="loading"
        />
        <KpiCard
          label="Cash Flow Risk"
          :value="hasData ? `${summary.cashflowScore}/100` : 'N/A'"
          :severity="hasData ? riskScoreSeverity(summary.cashflowScore) : undefined"
          :loading="loading"
        />
        <KpiCard
          label="Operational Risk"
          :value="hasData ? `${summary.operationalScore}/100` : 'N/A'"
          :severity="hasData ? riskScoreSeverity(summary.operationalScore) : undefined"
          :loading="loading"
        />
        <KpiCard
          label="Compliance Risk"
          :value="hasData ? `${summary.complianceScore}/100` : 'N/A'"
          :severity="hasData ? riskScoreSeverity(summary.complianceScore) : undefined"
          :loading="loading"
        />
        <KpiCard
          label="Active Alerts"
          :value="hasData ? String(summary.activeAlerts) : 'N/A'"
          :sublabel="hasData ? `${summary.criticalAlerts} critical` : undefined"
          :severity="hasData && summary.criticalAlerts > 0 ? 'high' : undefined"
          :loading="loading"
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
          <!-- Active Alerts -->
          <div v-if="overviewData.alerts?.length" class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Active Risk Alerts" :hint="`${overviewData.alerts?.length} requiring attention`" :level="3" />
            </div>
            <div class="p-6">
              <div class="space-y-3">
                <div
                  v-for="(alert, index) in overviewData.alerts"
                  :key="index"
                  class="flex items-start gap-4 p-4 rounded-lg border border-outline-gray-1 bg-surface-white"
                >
                  <div class="flex-1">
                    <div class="font-medium text-ink-gray-9">{{ alert.title }}</div>
                    <div class="text-sm text-ink-gray-6 mt-1">{{ alert.description }}</div>
                    <div class="text-xs text-ink-gray-6 mt-2">Action: {{ alert.action }}</div>
                  </div>
                  <Badge v-bind="severityBadge(alert.severity)" size="sm" />
                </div>
              </div>
            </div>
          </div>

          <!-- Risk Assessment Matrix Table -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Risk Assessment Matrix" hint="Impact vs Probability" :level="3" />
            </div>
            <div class="p-6">
              <div class="overflow-x-auto">
                <table class="w-full">
                  <thead>
                    <tr class="border-b border-outline-gray-1">
                      <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Risk</th>
                      <th scope="col" class="text-left py-2 text-sm font-medium text-ink-gray-7">Category</th>
                      <th scope="col" class="text-center py-2 text-sm font-medium text-ink-gray-7">Probability</th>
                      <th scope="col" class="text-center py-2 text-sm font-medium text-ink-gray-7">Impact</th>
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
                      <td class="py-3 text-center">
                        <div class="flex items-center justify-center gap-2">
                          <div
                            class="w-16 bg-surface-gray-3 rounded-full h-2"
                            :aria-label="severityAria('Probability', riskScoreSeverity(risk.probability), `${risk.probability}%`)"
                            role="img"
                          >
                            <div
                              :class="severityFill(riskScoreSeverity(risk.probability))"
                              class="h-2 rounded-full motion-reduce:transition-none transition-all"
                              :style="{ width: risk.probability + '%' }"
                            />
                          </div>
                          <span class="text-sm text-ink-gray-7">{{ risk.probability }}%</span>
                        </div>
                      </td>
                      <td class="py-3 text-center">
                        <div class="flex items-center justify-center gap-2">
                          <div
                            class="w-16 bg-surface-gray-3 rounded-full h-2"
                            :aria-label="severityAria('Impact', riskScoreSeverity(risk.impact), `${risk.impact}%`)"
                            role="img"
                          >
                            <div
                              :class="severityFill(riskScoreSeverity(risk.impact))"
                              class="h-2 rounded-full motion-reduce:transition-none transition-all"
                              :style="{ width: risk.impact + '%' }"
                            />
                          </div>
                          <span class="text-sm text-ink-gray-7">{{ risk.impact }}%</span>
                        </div>
                      </td>
                      <td class="py-3 text-center font-bold text-ink-gray-8">{{ risk.risk_score?.toFixed(1) }}</td>
                      <td class="py-3 text-center">
                        <Badge v-bind="severityBadge(risk.risk_category)" size="sm" />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- Key Business Metrics -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Key Business Metrics" :level="3" />
            </div>
            <div class="p-6">
              <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div class="text-center p-6 bg-surface-gray-1 rounded-lg">
                  <div class="text-4xl font-bold text-ink-gray-9">{{ formatCount(overviewData.total_customers as number) }}</div>
                  <div class="text-sm text-ink-gray-6 mt-2">Total Customers</div>
                </div>
                <div class="text-center p-6 bg-surface-gray-1 rounded-lg">
                  <div class="text-4xl font-bold text-ink-gray-9">{{ formatCount(overviewData.total_suppliers as number) }}</div>
                  <div class="text-sm text-ink-gray-6 mt-2">Total Suppliers</div>
                </div>
                <div class="text-center p-6 bg-surface-gray-1 rounded-lg">
                  <div class="text-4xl font-bold text-ink-gray-9">{{ formatCount(overviewData.total_items as number) }}</div>
                  <div class="text-sm text-ink-gray-6 mt-2">Inventory Items</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Risk Breakdown Chart -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Risk Component Breakdown" hint="Visual breakdown by category" :level="3" />
            </div>
            <div class="p-6">
              <div class="space-y-4">
                <div class="flex items-center gap-4">
                  <div class="w-32 text-sm font-medium text-ink-gray-7">Credit Risk</div>
                  <div
                    class="flex-1 bg-surface-gray-3 rounded-full h-4"
                    :aria-label="severityAria('Credit Risk', riskScoreSeverity(summary.creditScore), `${summary.creditScore}/100`)"
                    role="img"
                  >
                    <div
                      :class="[severityFill(riskScoreSeverity(summary.creditScore)), 'h-4 rounded-full motion-reduce:transition-none transition-all']"
                      :style="{ width: summary.creditScore + '%' }"
                    />
                  </div>
                  <div class="w-24 text-right flex items-center gap-2 justify-end">
                    <span class="font-bold text-ink-gray-8">{{ summary.creditScore }}/100</span>
                    <Badge v-bind="severityBadge(summary.creditRisk)" size="sm" />
                  </div>
                </div>
                <div class="flex items-center gap-4">
                  <div class="w-32 text-sm font-medium text-ink-gray-7">Cash Flow Risk</div>
                  <div
                    class="flex-1 bg-surface-gray-3 rounded-full h-4"
                    :aria-label="severityAria('Cash Flow Risk', riskScoreSeverity(summary.cashflowScore), `${summary.cashflowScore}/100`)"
                    role="img"
                  >
                    <div
                      :class="[severityFill(riskScoreSeverity(summary.cashflowScore)), 'h-4 rounded-full motion-reduce:transition-none transition-all']"
                      :style="{ width: summary.cashflowScore + '%' }"
                    />
                  </div>
                  <div class="w-24 text-right flex items-center gap-2 justify-end">
                    <span class="font-bold text-ink-gray-8">{{ summary.cashflowScore }}/100</span>
                    <Badge v-bind="severityBadge(summary.cashflowRisk)" size="sm" />
                  </div>
                </div>
                <div class="flex items-center gap-4">
                  <div class="w-32 text-sm font-medium text-ink-gray-7">Operational Risk</div>
                  <div
                    class="flex-1 bg-surface-gray-3 rounded-full h-4"
                    :aria-label="severityAria('Operational Risk', riskScoreSeverity(summary.operationalScore), `${summary.operationalScore}/100`)"
                    role="img"
                  >
                    <div
                      :class="[severityFill(riskScoreSeverity(summary.operationalScore)), 'h-4 rounded-full motion-reduce:transition-none transition-all']"
                      :style="{ width: summary.operationalScore + '%' }"
                    />
                  </div>
                  <div class="w-24 text-right flex items-center gap-2 justify-end">
                    <span class="font-bold text-ink-gray-8">{{ summary.operationalScore }}/100</span>
                    <Badge v-bind="severityBadge(summary.operationalRisk)" size="sm" />
                  </div>
                </div>
                <div class="flex items-center gap-4">
                  <div class="w-32 text-sm font-medium text-ink-gray-7">Compliance Risk</div>
                  <div
                    class="flex-1 bg-surface-gray-3 rounded-full h-4"
                    :aria-label="severityAria('Compliance Risk', riskScoreSeverity(summary.complianceScore), `${summary.complianceScore}/100`)"
                    role="img"
                  >
                    <div
                      :class="[severityFill(riskScoreSeverity(summary.complianceScore)), 'h-4 rounded-full motion-reduce:transition-none transition-all']"
                      :style="{ width: summary.complianceScore + '%' }"
                    />
                  </div>
                  <div class="w-24 text-right flex items-center gap-2 justify-end">
                    <span class="font-bold text-ink-gray-8">{{ summary.complianceScore }}/100</span>
                    <Badge v-bind="severityBadge(summary.complianceRisk)" size="sm" />
                  </div>
                </div>
              </div>
            </div>
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
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Receivables Aging Analysis" :level="3" />
            </div>
            <div class="p-6">
              <div class="grid grid-cols-5 gap-4">
                <div
                  v-for="bucket in creditData.aging_analysis"
                  :key="bucket.aging_bucket"
                  class="text-center p-4 border border-outline-gray-1 rounded-lg cursor-pointer hover:bg-surface-gray-1 focus-visible:ring-2 focus-visible:ring-outline-gray-3 focus-visible:outline-none"
                  tabindex="0"
                  role="button"
                  :aria-label="`Drill down: ${bucket.aging_bucket} overdue`"
                  @click="drillDown.open(RISK_ENDPOINT, bucket.aging_bucket + ' Overdue', { metric: 'overdue_invoices' })"
                  @keydown.enter="drillDown.open(RISK_ENDPOINT, bucket.aging_bucket + ' Overdue', { metric: 'overdue_invoices' })"
                >
                  <div class="text-sm font-medium text-ink-gray-6">{{ bucket.aging_bucket }}</div>
                  <div class="text-xl font-bold text-ink-gray-9 mt-1">{{ formatCurrency(bucket.outstanding_amount) }}</div>
                  <div class="text-xs text-ink-gray-6 mt-1">{{ bucket.invoice_count }} invoices</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Customer Risk Scores -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Customer Risk Scores" hint="Payment behaviour and default probability" :level="3" />
            </div>
            <div class="p-6">
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
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Revenue Concentration Analysis" hint="Top customers by revenue share" :level="3" />
            </div>
            <div class="p-6">
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
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Overdue Days Trend" :level="3" />
            </div>
            <div class="p-6">
              <div class="grid grid-cols-5 gap-4">
                <div
                  v-for="period in cashflowData.overdue_days_trend"
                  :key="period.period"
                  class="text-center p-4 border border-outline-gray-1 rounded-lg"
                >
                  <div class="text-sm font-medium text-ink-gray-6">{{ period.period }}</div>
                  <div class="text-xl font-bold text-ink-gray-9 mt-1">{{ Math.round(period.avg_days_overdue || 0) }}</div>
                  <div class="text-xs text-ink-gray-6 mt-1">days overdue</div>
                </div>
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
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Inventory Risk by Item Group" :level="3" />
            </div>
            <div class="p-6">
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
                        <span :class="risk.stockout_items > 0 ? 'text-ink-red-4 font-medium' : 'text-ink-gray-8'">
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
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Supplier Reliability Analysis" :level="3" />
            </div>
            <div class="p-6">
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
          <!-- KRA Status -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="KRA Compliance Status" :level="3" />
            </div>
            <div class="p-6">
              <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div class="text-center p-4 border border-outline-gray-1 rounded-lg">
                  <div class="text-2xl font-bold text-ink-gray-9">{{ complianceData.kra_status?.vat_filing_status || 'N/A' }}</div>
                  <div class="text-sm text-ink-gray-6 mt-1">VAT Filing Status</div>
                </div>
                <div class="text-center p-4 border border-outline-gray-1 rounded-lg">
                  <div class="text-lg font-bold text-ink-gray-8">{{ complianceData.kra_status?.last_filing_date || 'N/A' }}</div>
                  <div class="text-sm text-ink-gray-6 mt-1">Last Filing Date</div>
                </div>
                <div class="text-center p-4 border border-outline-gray-1 rounded-lg">
                  <div class="text-lg font-bold text-ink-gray-8">{{ complianceData.kra_status?.next_filing_due || 'N/A' }}</div>
                  <div class="text-sm text-ink-gray-6 mt-1">Next Filing Due</div>
                </div>
                <div class="text-center p-4 border border-outline-gray-1 rounded-lg">
                  <div
                    class="text-2xl font-bold"
                    :class="(complianceData.kra_status?.outstanding_penalties || 0) > 0 ? 'text-ink-red-4' : 'text-ink-gray-9'"
                  >
                    {{ formatCurrency(complianceData.kra_status?.outstanding_penalties || 0) }}
                  </div>
                  <div class="text-sm text-ink-gray-6 mt-1">Outstanding Penalties</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Document Audit -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Document Completeness Audit" :level="3" />
            </div>
            <div class="p-6">
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
                        <span :class="doc.incomplete_docs > 0 ? 'text-ink-red-4 font-medium' : 'text-ink-gray-8'">
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

          <!-- Licenses & Permits -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Licenses & Permits" :level="3" />
            </div>
            <div class="p-6">
              <div class="space-y-3">
                <div
                  v-for="license in complianceData.licenses"
                  :key="license.license_type"
                  class="flex items-center justify-between p-4 border border-outline-gray-1 rounded-lg"
                >
                  <div>
                    <div class="font-medium text-ink-gray-9">{{ license.license_type }}</div>
                    <div class="text-sm text-ink-gray-6">Expires: {{ license.expiry_date }}</div>
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
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
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
            <KpiCard
              label="Forecast Confidence"
              :value="(predictiveData.forecast_confidence as string) || 'Medium'"
            />
          </div>

          <!-- Anomaly Detection -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Detected Anomalies" hint="Unusual patterns in financial data" :level="3" />
            </div>
            <div class="p-6">
              <div v-if="predictiveData.anomalies?.length" class="space-y-3">
                <div
                  v-for="(anomaly, index) in predictiveData.anomalies"
                  :key="index"
                  class="flex items-center justify-between p-4 rounded-lg border border-outline-gray-1"
                >
                  <div>
                    <div class="font-medium text-ink-gray-9">{{ anomaly.type.replace(/_/g, ' ').toUpperCase() }}</div>
                    <div class="text-sm text-ink-gray-6">{{ anomaly.description }}</div>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-sm text-ink-gray-6">{{ anomaly.date }}</span>
                    <Badge v-bind="severityBadge(anomaly.severity)" size="sm" />
                  </div>
                </div>
              </div>
              <div v-else class="text-center text-ink-gray-6 py-8">
                No anomalies detected in recent data
              </div>
            </div>
          </div>

          <!-- Early Warning Alerts -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Early Warning System" :level="3" />
            </div>
            <div class="p-6">
              <div v-if="predictiveData.early_warnings?.length" class="space-y-4">
                <div
                  v-for="(warning, index) in predictiveData.early_warnings"
                  :key="index"
                  class="flex items-center justify-between p-4 rounded-lg border border-outline-gray-1"
                >
                  <div>
                    <div class="font-medium text-ink-gray-9">{{ warning.title }}</div>
                    <div class="text-sm text-ink-gray-6">{{ warning.description }}</div>
                    <div class="text-xs text-ink-gray-6 mt-1">Timeframe: {{ warning.timeframe }}</div>
                  </div>
                  <Badge v-bind="severityBadge(warning.severity)" size="sm" />
                </div>
              </div>
              <div v-else class="text-center text-ink-gray-6 py-8">
                No early warnings at this time
              </div>
            </div>
          </div>

          <!-- Payment Risk Forecast -->
          <div class="bg-surface-white rounded-lg border border-outline-gray-1">
            <div class="p-6 border-b border-outline-gray-1">
              <SectionHeader title="Payment Delay Risk Forecast" :level="3" />
            </div>
            <div class="p-6">
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
      </div>
    </template>

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
