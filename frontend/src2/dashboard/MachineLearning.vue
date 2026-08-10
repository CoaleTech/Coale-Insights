<script setup lang="ts">
defineOptions({ name: 'MachineLearning' })
/**
 * The Machine Learning dashboard.
 *
 * Deliberately not a copy of the domain charts. A forecast belongs beside the
 * revenue it forecasts; what has nowhere else to live is the state of the
 * models themselves, and two models whose output is not about one domain --
 * lead win probability and ledger anomalies.
 *
 * The health table exists because every model in this app degrades silently.
 * The forecasters fell back to a moving average for months because statsmodels
 * was never installed, and nothing on any page said so. A model that reports
 * its actual method, the rows it used and its measured quality cannot fail that
 * way unnoticed.
 */
import { computed, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import { createToast } from '../helpers/toasts'
import { apiCall, readFrappeError } from '../helpers/api'
import { useIntelligenceDashboard } from '../intelligence/composables/useIntelligenceDashboard'
import SectionHeader from '../intelligence/components/SectionHeader.vue'
import KpiCard from '../intelligence/components/KpiCard.vue'
import { formatCount, formatDateTime, formatMoney } from '../utils/format'

interface ModelRow {
  key: string
  label: string
  kind: string
  gate: string
  trained_at: string | null
  source: string | null
  state: 'trained' | 'never_trained' | 'blocked_on_data' | 'error'
  method: string | null
  rows: number | null
  quality: string | null
  detail: string | null
}
interface ScoredLead {
  lead: string
  lead_name: string
  status: string
  source: string
  territory: string
  age_days: number
  win_probability: number
  band: 'High' | 'Medium' | 'Low'
}
interface SourceRate { source: string; closed: number; won: number; win_rate: number }
interface AnomalyRow {
  gl_entry: string
  posting_date: string
  account: string
  voucher_type: string
  voucher_no: string
  debit: number
  credit: number
  score: number
}

const health = useIntelligenceDashboard<{ models: ModelRow[]; trained: number; total: number }>({
  url: 'insights.api.ml.model_health',
  cache: 'ml-model-health',
})
const leads = useIntelligenceDashboard<Record<string, unknown>>({
  url: 'insights.api.ml.lead_conversion',
  cache: 'ml-lead-conversion',
})
const anomalies = useIntelligenceDashboard<Record<string, unknown>>({
  url: 'insights.api.ml.gl_anomalies',
  cache: 'ml-gl-anomalies',
})

const models = computed<ModelRow[]>(() => health.data.value?.models ?? [])
const trainedCount = computed(() => health.data.value?.trained ?? 0)
const totalCount = computed(() => health.data.value?.total ?? 0)

const leadMetrics = computed(() => (leads.data.value?.metrics ?? {}) as Record<string, number>)
const leadTraining = computed(() => (leads.data.value?.training ?? {}) as Record<string, number>)
const topLeads = computed<ScoredLead[]>(() => (leads.data.value?.top_open_leads ?? []) as ScoredLead[])
const bySource = computed<SourceRate[]>(() => (leads.data.value?.by_source ?? []) as SourceRate[])
const leadState = computed(() => leads.data.value?.status as string | undefined)

/** GL debit/credit are in company currency; the scan reports which. */
const ledgerCurrency = computed(() => (anomalies.data.value?.base_currency as string) || null)
const anomalyRows = computed<AnomalyRow[]>(() => (anomalies.data.value?.entries ?? []) as AnomalyRow[])
const scanned = computed(() => anomalies.data.value?.scanned as number | undefined)
const flagged = computed(() => anomalies.data.value?.flagged as number | undefined)
const anomalyState = computed(() => anomalies.data.value?.status as string | undefined)

const retraining = ref<string | null>(null)

/** Queue one model's fit. The endpoint never trains in the request. */
async function retrain(model: ModelRow) {
  retraining.value = model.key
  try {
    const result = (await apiCall('insights.api.ml.retrain', { model: model.key })) as
      | Record<string, unknown>
      | null
    createToast({
      title: 'Training Queued',
      message: (result?.message as string) || `${model.label}: training queued`,
      variant: 'success',
    })
  } catch (e: unknown) {
    createToast({
      title: 'Could not queue training',
      message: readFrappeError(e, 'Unknown error').message,
      variant: 'error',
    })
  } finally {
    retraining.value = null
  }
}

type BadgeTheme = 'gray' | 'blue' | 'green' | 'red' | 'orange'

const STATE_THEME: Record<ModelRow['state'], BadgeTheme> = {
  trained: 'green',
  never_trained: 'gray',
  blocked_on_data: 'orange',
  error: 'red',
}
const STATE_LABEL: Record<ModelRow['state'], string> = {
  trained: 'Trained',
  never_trained: 'Never trained',
  blocked_on_data: 'Not enough data',
  error: 'Failed',
}
const BAND_THEME: Record<ScoredLead['band'], BadgeTheme> = {
  High: 'green',
  Medium: 'orange',
  Low: 'gray',
}
</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1 overflow-y-auto">
    <header
      class="bg-surface-white border-b border-outline-gray-1 px-6 py-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <div>
        <h1 class="text-2xl font-bold text-ink-gray-9">Machine Learning</h1>
        <p class="text-sm text-ink-gray-6 mt-1">
          Model health, lead win probability, and ledger anomalies
        </p>
      </div>
      <Button
        variant="solid"
        theme="gray"
        icon-left="refresh-cw"
        :loading="health.refreshing.value"
        @click="health.reload()"
      >
        Refresh
      </Button>
    </header>

    <div v-if="health.isPermissionError.value" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <p class="text-base font-medium text-ink-gray-9">Access Restricted</p>
        <p class="text-sm text-ink-gray-6 mt-2">
          You do not have permission to view model health.
        </p>
      </div>
    </div>

    <div v-else class="p-6 flex flex-col gap-8">
      <!-- ── Model health ─────────────────────────────────────────────── -->
      <section>
        <SectionHeader
          title="Model Health"
          :hint="`${trainedCount} of ${totalCount} trained`"
          :level="2"
        />

        <p v-if="health.error.value" class="text-sm text-ink-red-6 mt-2">
          {{ health.error.value }}
        </p>

        <div
          v-else
          class="mt-3 bg-surface-white border border-outline-gray-1 rounded-lg overflow-x-auto"
        >
          <table class="w-full text-sm">
            <thead class="border-b border-outline-gray-1 text-ink-gray-6">
              <tr>
                <th class="text-left font-medium px-4 py-3">Model</th>
                <th class="text-left font-medium px-4 py-3">State</th>
                <th class="text-left font-medium px-4 py-3">Method in use</th>
                <th class="text-right font-medium px-4 py-3">Rows</th>
                <th class="text-left font-medium px-4 py-3">Quality</th>
                <th class="text-left font-medium px-4 py-3">Last trained</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="model in models"
                :key="model.key"
                class="border-b border-outline-gray-1 last:border-0 align-top"
              >
                <td class="px-4 py-3">
                  <p class="font-medium text-ink-gray-9">{{ model.label }}</p>
                  <p class="text-xs text-ink-gray-5 mt-0.5">{{ model.kind }}</p>
                  <p class="text-xs text-ink-gray-5 mt-1">{{ model.gate }}</p>
                </td>
                <td class="px-4 py-3">
                  <Badge :theme="STATE_THEME[model.state]" variant="subtle">
                    {{ STATE_LABEL[model.state] }}
                  </Badge>
                  <p v-if="model.detail" class="text-xs text-ink-gray-6 mt-1 max-w-xs">
                    {{ model.detail }}
                  </p>
                </td>
                <td class="px-4 py-3 text-ink-gray-8">{{ model.method || '—' }}</td>
                <td class="px-4 py-3 text-right text-ink-gray-8 tabular-nums">
                  {{ model.rows === null ? '—' : formatCount(model.rows) }}
                </td>
                <td class="px-4 py-3 text-ink-gray-8">{{ model.quality || '—' }}</td>
                <td class="px-4 py-3 text-ink-gray-6 whitespace-nowrap">
                  {{ model.trained_at ? formatDateTime(model.trained_at) : 'Never' }}
                  <span v-if="model.source === 'snapshot'" class="text-xs text-ink-gray-5 block">
                    from disk snapshot
                  </span>
                </td>
                <td class="px-4 py-3 text-right">
                  <Button
                    variant="subtle"
                    :loading="retraining === model.key"
                    @click="retrain(model)"
                  >
                    Retrain
                  </Button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- ── Lead conversion ──────────────────────────────────────────── -->
      <section>
        <SectionHeader
          title="Lead Win Probability"
          hint="Learned from closed leads in ERPNext CRM"
          :level="2"
        />

        <p v-if="leads.error.value" class="text-sm text-ink-red-6 mt-2">{{ leads.error.value }}</p>
        <p
          v-else-if="leadState && leadState !== 'success'"
          class="text-sm text-ink-gray-6 mt-2"
        >
          {{ (leads.data.value?.message as string) || 'Not trained yet.' }}
        </p>

        <template v-else-if="leads.hasData.value">
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-3">
            <KpiCard label="Model quality" :value="leadMetrics.roc_auc" unit="% ROC-AUC" />
            <KpiCard label="Precision" :percent="leadMetrics.precision" />
            <KpiCard label="Closed leads learned from" :value="leadTraining.closed_total" />
            <KpiCard label="Open leads scored" :value="leadTraining.open_scored" />
          </div>

          <div class="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-4">
            <div class="bg-surface-white border border-outline-gray-1 rounded-lg overflow-hidden">
              <SectionHeader title="Highest-probability open leads" variant="caption" :level="3" />
              <table class="w-full text-sm">
                <thead class="border-y border-outline-gray-1 text-ink-gray-6">
                  <tr>
                    <th class="text-left font-medium px-4 py-2">Lead</th>
                    <th class="text-left font-medium px-4 py-2">Source</th>
                    <th class="text-right font-medium px-4 py-2">Win</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="lead in topLeads.slice(0, 12)"
                    :key="lead.lead"
                    class="border-b border-outline-gray-1 last:border-0"
                  >
                    <td class="px-4 py-2">
                      <p class="text-ink-gray-9">{{ lead.lead_name }}</p>
                      <p class="text-xs text-ink-gray-5">
                        {{ lead.territory }} · {{ lead.age_days }}d old
                      </p>
                    </td>
                    <td class="px-4 py-2 text-ink-gray-7">{{ lead.source }}</td>
                    <td class="px-4 py-2 text-right">
                      <Badge :theme="BAND_THEME[lead.band]" variant="subtle">
                        {{ lead.win_probability }}%
                      </Badge>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="bg-surface-white border border-outline-gray-1 rounded-lg overflow-hidden">
              <SectionHeader title="Historical win rate by source" variant="caption" :level="3" />
              <table class="w-full text-sm">
                <thead class="border-y border-outline-gray-1 text-ink-gray-6">
                  <tr>
                    <th class="text-left font-medium px-4 py-2">Source</th>
                    <th class="text-right font-medium px-4 py-2">Closed</th>
                    <th class="text-right font-medium px-4 py-2">Won</th>
                    <th class="text-right font-medium px-4 py-2">Rate</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in bySource"
                    :key="row.source"
                    class="border-b border-outline-gray-1 last:border-0"
                  >
                    <td class="px-4 py-2 text-ink-gray-9">{{ row.source }}</td>
                    <td class="px-4 py-2 text-right text-ink-gray-7 tabular-nums">
                      {{ formatCount(row.closed) }}
                    </td>
                    <td class="px-4 py-2 text-right text-ink-gray-7 tabular-nums">
                      {{ formatCount(row.won) }}
                    </td>
                    <td class="px-4 py-2 text-right font-medium text-ink-gray-9 tabular-nums">
                      {{ row.win_rate }}%
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </section>

      <!-- ── Ledger anomalies ─────────────────────────────────────────── -->
      <section>
        <SectionHeader
          title="Ledger Anomalies"
          hint="Review candidates, ranked by how unlike the rest of the ledger they are"
          :level="2"
        />

        <p v-if="anomalies.error.value" class="text-sm text-ink-red-6 mt-2">
          {{ anomalies.error.value }}
        </p>
        <p
          v-else-if="anomalyState && anomalyState !== 'success'"
          class="text-sm text-ink-gray-6 mt-2"
        >
          {{ (anomalies.data.value?.message as string) || 'Not scanned yet.' }}
        </p>

        <template v-else-if="anomalies.hasData.value">
          <p class="text-sm text-ink-gray-6 mt-2">
            {{ formatCount(flagged) }} of {{ formatCount(scanned) }} entries flagged. Unusual is not
            the same as wrong — a year-end adjustment is unusual by design.
          </p>
          <div
            class="mt-3 bg-surface-white border border-outline-gray-1 rounded-lg overflow-x-auto"
          >
            <table class="w-full text-sm">
              <thead class="border-b border-outline-gray-1 text-ink-gray-6">
                <tr>
                  <th class="text-left font-medium px-4 py-2">Date</th>
                  <th class="text-left font-medium px-4 py-2">Account</th>
                  <th class="text-left font-medium px-4 py-2">Voucher</th>
                  <th class="text-right font-medium px-4 py-2">Debit</th>
                  <th class="text-right font-medium px-4 py-2">Credit</th>
                  <th class="text-right font-medium px-4 py-2">Score</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in anomalyRows.slice(0, 25)"
                  :key="row.gl_entry"
                  class="border-b border-outline-gray-1 last:border-0"
                >
                  <td class="px-4 py-2 text-ink-gray-7 whitespace-nowrap">
                    {{ row.posting_date }}
                  </td>
                  <td class="px-4 py-2 text-ink-gray-9">{{ row.account }}</td>
                  <td class="px-4 py-2 text-ink-gray-7">
                    {{ row.voucher_type }}
                    <span class="text-xs text-ink-gray-5 block">{{ row.voucher_no }}</span>
                  </td>
                  <td class="px-4 py-2 text-right text-ink-gray-8 tabular-nums">
                    {{ row.debit ? formatMoney(row.debit, ledgerCurrency) : '—' }}
                  </td>
                  <td class="px-4 py-2 text-right text-ink-gray-8 tabular-nums">
                    {{ row.credit ? formatMoney(row.credit, ledgerCurrency) : '—' }}
                  </td>
                  <td class="px-4 py-2 text-right font-medium text-ink-gray-9 tabular-nums">
                    {{ row.score }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>
