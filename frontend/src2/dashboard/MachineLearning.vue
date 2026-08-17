<script setup lang="ts">
defineOptions({ name: 'MachineLearning' })
/**
 * The Machine Learning dashboard.
 *
 * Deliberately not a copy of the domain charts, and deliberately small. A model
 * belongs beside the thing it predicts: lead win probability is a tab on
 * Marketing & CRM, ledger anomalies a tab on Risk. What has nowhere else to
 * live is the state of the models themselves, and the runtime they depend on.
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
import IntelligenceDashboardShell from '../intelligence/components/IntelligenceDashboardShell.vue'
import { formatCount, formatDateTime } from '../utils/format'

interface ModelRow {
  key: string
  label: string
  kind: string
  gate: string
  trained_at: string | null
  state: 'trained' | 'never_trained' | 'blocked_on_data' | 'error'
  method: string | null
  rows: number | null
  quality: string | null
  detail: string | null
}

type DataRow = {
  doctype: string
  used_by: string
  rows: number | null
  state: 'populated' | 'empty' | 'absent'
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
} = useIntelligenceDashboard<{
  models: ModelRow[]
  trained: number
  total: number
  libraries: Record<string, string | null>
  libraries_missing: string[]
  data: DataRow[]
}>({
  url: 'insights.api.ml.model_health',
  cache: 'ml-model-health',
})

const models = computed<ModelRow[]>(() => data.value?.models ?? [])
const trainedCount = computed(() => data.value?.trained ?? 0)
const totalCount = computed(() => data.value?.total ?? 0)

/** The runtime the models actually got, rather than the one requirements-ml.txt
 * asks for. A version mismatch between two benches is what silently changes a
 * model's behaviour, so the version is the value worth showing, not a tick. */
const libraries = computed(() =>
  Object.entries(data.value?.libraries ?? {}).map(([name, version]) => ({
    name,
    version,
  })),
)
const librariesMissing = computed(() => data.value?.libraries_missing ?? [])

/** Row counts behind each module. An empty table and an uninstalled app look
 * the same on a chart of zeros and call for opposite responses, so `absent` is
 * kept distinct from `empty`. */
const dataRows = computed<DataRow[]>(() => data.value?.data ?? [])

const emptySources = computed(() => dataRows.value.filter((row) => row.state !== 'populated'))

const retraining = ref<string | null>(null)

/** Recompute one model against current data. The endpoint runs synchronously
 * and answers with the fresh payload -- there is no queue behind this. */
async function retrain(model: ModelRow) {
  retraining.value = model.key
  try {
    const result = (await apiCall('insights.api.ml.retrain', { model: model.key })) as
      | Record<string, unknown>
      | null
    const innerStatus = result?.status as string | undefined
    if (innerStatus === 'error') {
      createToast({
        title: 'Recompute failed',
        message: (result?.message as string) || `${model.label}: recompute failed`,
        variant: 'error',
      })
    } else if (innerStatus === 'insufficient_data') {
      createToast({
        title: 'Not enough data',
        message: (result?.message as string) || `${model.label}: not enough data yet`,
        variant: 'warning',
      })
    } else {
      createToast({
        title: 'Recomputed',
        message: `${model.label}: recomputed from current data`,
        variant: 'success',
      })
    }
    reload()
  } catch (e: unknown) {
    createToast({
      title: 'Could not recompute',
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
</script>

<template>
  <div class="flex flex-col h-full bg-surface-gray-1 overflow-y-auto">
    <header
      class="bg-surface-white border-b border-outline-gray-1 px-6 py-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <div>
        <h1 class="text-2xl font-bold text-ink-gray-9">Machine Learning</h1>
        <p class="text-sm text-ink-gray-6 mt-1">
          Every model the app trains, and the runtime it depends on
        </p>
      </div>
      <Button
        variant="solid"
        theme="gray"
        icon-left="refresh-cw"
        :loading="refreshing"
        @click="reload()"
      >
        Refresh
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
      subject="model health"
      permission-hint="Ask an administrator for model health read access."
      @retry="retry"
    >
    <div class="p-6 flex flex-col gap-8">
      <!-- ── Model health ─────────────────────────────────────────────── -->
      <section>
        <SectionHeader
          title="Model Health"
          :hint="`${trainedCount} of ${totalCount} trained`"
          :level="2"
        />


        <div
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
                <th class="text-left font-medium px-4 py-3">Verified</th>
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

      <!-- ── Environment ──────────────────────────────────────────────── -->
      <section>
        <SectionHeader
          title="Environment"
          hint="What this site can run, and what it has to run on"
          :level="2"
        />

        <div class="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <!-- Libraries -->
          <div class="bg-surface-white border border-outline-gray-1 rounded-lg p-4">
            <SectionHeader title="ML libraries" variant="caption" :level="3" />
            <div v-if="librariesMissing.length" class="text-sm text-ink-red-6 mt-2">
              <p>
                Not importable on this host: {{ librariesMissing.join(', ') }}. Models needing
                them cannot train.
              </p>
              <!-- Deliberately not a button. Installing packages is a deploy-time
                   action: it writes to the bench virtualenv, takes minutes, and
                   on an image-based host like Frappe Cloud a runtime install is
                   discarded on the next container start. The page reports; the
                   operator deploys. -->
              <p class="mt-1 text-ink-gray-6">
                Managed host (Frappe Cloud): redeploy the bench group — the image build
                installs them. Self-hosted:
                <span class="font-mono">bench setup requirements</span>, then restart.
              </p>
            </div>
            <p v-else class="text-sm text-ink-gray-6 mt-2">
              All five present. Versions are what the models actually ran against.
            </p>
            <dl class="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5">
              <template v-for="lib in libraries" :key="lib.name">
                <dt class="text-sm text-ink-gray-7">{{ lib.name }}</dt>
                <dd
                  class="text-sm text-right tabular-nums"
                  :class="lib.version ? 'text-ink-gray-9' : 'text-ink-red-6 font-medium'"
                >
                  {{ lib.version ?? 'missing' }}
                </dd>
              </template>
            </dl>
          </div>

          <!-- Source data -->
          <div class="bg-surface-white border border-outline-gray-1 rounded-lg p-4">
            <SectionHeader title="Source data" variant="caption" :level="3" />
            <p class="text-sm mt-2 text-ink-gray-6">
              <template v-if="emptySources.length">
                {{ emptySources.length }} of {{ dataRows.length }} tables have nothing to
                analyse. Dashboards over them report zeros, not findings.
              </template>
              <template v-else>Every module has data behind it.</template>
            </p>
            <dl class="mt-3 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5">
              <template v-for="row in dataRows" :key="row.doctype">
                <dt class="text-sm text-ink-gray-7 truncate" :title="row.used_by">
                  {{ row.doctype }}
                </dt>
                <dd
                  class="text-sm text-right tabular-nums"
                  :class="row.state === 'populated' ? 'text-ink-gray-9' : 'text-ink-gray-5'"
                >
                  {{ row.state === 'absent' ? 'no doctype' : formatCount(row.rows ?? 0) }}
                </dd>
              </template>
            </dl>
          </div>
        </div>
      </section>
    </div>
    </IntelligenceDashboardShell>
  </div>
</template>
