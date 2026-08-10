<script setup lang="ts">
defineOptions({ name: 'LedgerAnomalies' })
/**
 * GL entries ranked by how unlike the rest of the ledger they are.
 *
 * Lives on Risk rather than the Machine Learning page: these are review
 * candidates, which is a risk workflow. The ML page keeps only what has
 * nowhere else to live -- the state of the models themselves.
 *
 * Self-fetching, so the host only has to mount it. Mount it behind `v-if` on
 * the tab: the scan should not be requested for a tab nobody opened.
 */
import { computed } from 'vue'
import { useIntelligenceDashboard } from '../composables/useIntelligenceDashboard'
import { formatCount, formatMoney } from '../../utils/format'

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

const anomalies = useIntelligenceDashboard<Record<string, unknown>>({
  url: 'insights.api.ml.gl_anomalies',
  cache: 'ml-gl-anomalies',
})

/** GL debit/credit are in company currency; the scan reports which. */
const ledgerCurrency = computed(() => (anomalies.data.value?.base_currency as string) || null)
const rows = computed<AnomalyRow[]>(() => (anomalies.data.value?.entries ?? []) as AnomalyRow[])
const scanned = computed(() => anomalies.data.value?.scanned as number | undefined)
const flagged = computed(() => anomalies.data.value?.flagged as number | undefined)
const state = computed(() => anomalies.data.value?.status as string | undefined)
</script>

<template>
  <section>
    <p v-if="anomalies.error.value" class="text-sm text-ink-red-6">
      {{ anomalies.error.value }}
    </p>
    <p v-else-if="state && state !== 'success'" class="text-sm text-ink-gray-6">
      {{ (anomalies.data.value?.message as string) || 'Not scanned yet.' }}
    </p>

    <template v-else-if="anomalies.hasData.value">
      <p class="text-sm text-ink-gray-6">
        {{ formatCount(flagged) }} of {{ formatCount(scanned) }} entries flagged. Unusual is not
        the same as wrong — a year-end adjustment is unusual by design.
      </p>
      <div class="mt-3 bg-surface-white border border-outline-gray-1 rounded-lg overflow-x-auto">
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
              v-for="row in rows.slice(0, 25)"
              :key="row.gl_entry"
              class="border-b border-outline-gray-1 last:border-0"
            >
              <td class="px-4 py-2 text-ink-gray-7 whitespace-nowrap">{{ row.posting_date }}</td>
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
</template>
