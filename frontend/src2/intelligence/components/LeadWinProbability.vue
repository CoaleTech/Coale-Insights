<script setup lang="ts">
defineOptions({ name: 'LeadWinProbability' })
/**
 * Win probability for open leads, and historical win rate by source.
 *
 * Lives on Marketing & CRM rather than the Machine Learning page. A lead score
 * is only useful next to the pipeline it scores; the ML page keeps what has
 * nowhere else to live -- whether each model is trained, on what, and how well.
 *
 * Self-fetching, so the host only has to mount it. Mount it behind `v-if` on
 * the tab: the request should not go out for a tab nobody opened.
 */
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import { useIntelligenceDashboard } from '../composables/useIntelligenceDashboard'
import SectionHeader from './SectionHeader.vue'
import KpiCard from './KpiCard.vue'
import { formatCount } from '../../utils/format'

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
interface SourceRate {
  source: string
  closed: number
  won: number
  win_rate: number
}

const leads = useIntelligenceDashboard<Record<string, unknown>>({
  url: 'insights.api.ml.lead_conversion',
  cache: 'ml-lead-conversion',
})

const metrics = computed(() => (leads.data.value?.metrics ?? {}) as Record<string, number>)
const training = computed(() => (leads.data.value?.training ?? {}) as Record<string, number>)
const topLeads = computed<ScoredLead[]>(
  () => (leads.data.value?.top_open_leads ?? []) as ScoredLead[],
)
const bySource = computed<SourceRate[]>(() => (leads.data.value?.by_source ?? []) as SourceRate[])
const state = computed(() => leads.data.value?.status as string | undefined)

const BAND_THEME: Record<ScoredLead['band'], 'green' | 'orange' | 'gray'> = {
  High: 'green',
  Medium: 'orange',
  Low: 'gray',
}
</script>

<template>
  <section>
    <p v-if="leads.error.value" class="text-sm text-ink-red-6">{{ leads.error.value }}</p>
    <p v-else-if="state && state !== 'success'" class="text-sm text-ink-gray-6">
      {{ (leads.data.value?.message as string) || 'Not trained yet.' }}
    </p>

    <template v-else-if="leads.hasData.value">
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Model quality" :value="metrics.roc_auc" unit="% ROC-AUC" />
        <KpiCard label="Precision" :percent="metrics.precision" />
        <KpiCard label="Closed leads learned from" :value="training.closed_total" />
        <KpiCard label="Open leads scored" :value="training.open_scored" />
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
</template>
