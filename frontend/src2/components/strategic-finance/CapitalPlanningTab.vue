<!--
  Capital Planning: Asset Schedule & Forecasts: no drill-down.

  Capital expenditure, depreciation, and asset-age forecasts are modelled and
  planned figures without direct GL transaction rows. A drill-down to account
  detail would not resolve the planning logic.
-->
<template>
  <div class="space-y-6">

    <!-- CAPEX Overview Cards -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <KpiCard
        label="Net Book Value"
        :amount="data?.total_net_assets"
        :currency="currency"
        :sublabel="data?.asset_count != null ? `${data.asset_count} registered assets` : undefined"
        :loading="!data"
      />
      <KpiCard
        label="Gross Asset Value"
        :amount="data?.total_gross_assets"
        :currency="currency"
        :loading="!data"
      />
      <KpiCard
        label="Accumulated Depreciation"
        :amount="data?.total_accumulated_depreciation"
        :currency="currency"
        :loading="!data"
      />
      <KpiCard
        label="YTD CAPEX"
        :amount="data?.ytd_capex"
        :currency="currency"
        :delta="capexDelta"
        sublabel="vs prior year"
        :loading="!data"
      />
      <KpiCard
        label="Prior Year CAPEX"
        :amount="data?.prior_year_capex"
        :currency="currency"
        :loading="!data"
      />
    </div>
    <p v-if="registerNote" class="text-xs text-ink-gray-6">{{ registerNote }}</p>

    <!-- Assets by Category -->
    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <SectionHeader variant="caption" title="Assets by Category" :level="3">
        <template #actions>
          <PieChartIcon class="h-5 w-5 text-ink-gray-5" />
        </template>
      </SectionHeader>
      <div v-if="categories.length" class="space-y-4 mt-4">
        <div v-for="(category, index) in categories" :key="category.category">
          <div class="flex justify-between mb-1 gap-3">
            <span class="text-sm font-medium text-ink-gray-7">
              {{ category.category }}
              <span class="text-ink-gray-5 font-normal">({{ category.asset_count }})</span>
            </span>
            <span class="text-sm text-ink-gray-6 tnum">
              {{ formatMoney(category.net_value, currency) }} ({{ category.share.toFixed(1) }}%)
            </span>
          </div>
          <!-- Non-text fill bar; CSS var for series colour; aria-label makes it accessible -->
          <div
            class="h-3 bg-surface-gray-3 rounded-full overflow-hidden"
            :aria-label="`${category.category}: ${category.share.toFixed(1)}% of net book value`"
            role="img"
          >
            <div
              class="h-full rounded-full transition-all motion-reduce:transition-none"
              :style="{ width: `${category.share}%`, backgroundColor: categoryColors[index % categoryColors.length] }"
            ></div>
          </div>
        </div>
      </div>
      <div v-else class="text-center py-8 text-ink-gray-6 mt-4">No asset data available</div>
    </div>

    <!-- Top Assets -->
    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <SectionHeader variant="caption" title="Top Assets" :level="3">
        <template #actions>
          <Building2 class="h-5 w-5 text-ink-gray-5" />
        </template>
      </SectionHeader>
      <div v-if="data?.top_assets?.length" class="overflow-x-auto mt-4">
        <table class="min-w-full divide-y divide-outline-gray-1">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Asset</th>
              <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Category</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Gross Value</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Net Value</th>
              <th scope="col" class="px-4 py-3 text-center text-xs font-medium text-ink-gray-6 uppercase">Status</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-1">
            <tr v-for="asset in data.top_assets" :key="asset.name" class="hover:bg-surface-gray-1">
              <td class="px-4 py-3 text-sm font-medium text-ink-gray-9">{{ asset.asset_name || asset.name }}</td>
              <td class="px-4 py-3 text-sm text-ink-gray-6">{{ asset.category || NO_VALUE }}</td>
              <td class="px-4 py-3 text-sm text-right text-ink-gray-6 tnum">{{ formatMoney(asset.gross_value, currency) }}</td>
              <td class="px-4 py-3 text-sm text-right text-ink-gray-6 tnum">{{ formatMoney(asset.net_value, currency) }}</td>
              <td class="px-4 py-3 text-sm text-center text-ink-gray-6">{{ asset.status || NO_VALUE }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center py-8 text-ink-gray-6 mt-4">No assets recorded</div>
    </div>

    <!-- Upcoming Depreciation -->
    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-6">
      <SectionHeader variant="caption" title="Scheduled Depreciation (Next 12 Months)" :level="3">
        <template #actions>
          <TrendingDown class="h-5 w-5 text-ink-gray-5" />
        </template>
      </SectionHeader>
      <div v-if="data?.upcoming_depreciation?.length" class="overflow-x-auto mt-4">
        <table class="min-w-full divide-y divide-outline-gray-1">
          <thead class="bg-surface-gray-1">
            <tr>
              <th scope="col" class="px-4 py-3 text-left text-xs font-medium text-ink-gray-6 uppercase">Month</th>
              <th scope="col" class="px-4 py-3 text-right text-xs font-medium text-ink-gray-6 uppercase">Depreciation</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-1">
            <tr v-for="row in data.upcoming_depreciation" :key="row.period" class="hover:bg-surface-gray-1">
              <td class="px-4 py-3 text-sm font-medium text-ink-gray-9">{{ row.period }}</td>
              <td class="px-4 py-3 text-sm text-right text-ink-gray-6 tnum">{{ formatMoney(row.amount, currency) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center py-8 text-ink-gray-6 mt-4">No depreciation scheduled</div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { Building2, TrendingDown, PieChart as PieChartIcon } from 'lucide-vue-next'
import { computed } from 'vue'
import { useCurrency } from '../../composables/useCurrency'
import { formatMoney, NO_VALUE } from '../../utils/format'
import KpiCard from '../../intelligence/components/KpiCard.vue'
import SectionHeader from '../../intelligence/components/SectionHeader.vue'
import type { CapitalPlanningData } from './types'

const props = defineProps<{ data?: CapitalPlanningData }>()

const currency = useCurrency('INR')

// The server reports 0 (not null) when there is no prior-year base, so a delta
// is only meaningful when prior-year CAPEX is positive.
const capexDelta = computed(() =>
  (props.data?.prior_year_capex ?? 0) > 0 ? (props.data?.capex_change_pct ?? null) : null,
)

// Share of total net book value, for the category bars.
const categories = computed(() => {
  const rows = props.data?.category_summary ?? []
  const total = rows.reduce((sum, r) => sum + (r.net_value || 0), 0)
  return rows.map((r) => ({ ...r, share: total > 0 ? ((r.net_value || 0) / total) * 100 : 0 }))
})

// Headline figures are the GL book of record; categories and the table below
// come from the Asset register. Say so when the register covers less.
const registerNote = computed(() => {
  const gross = props.data?.total_gross_assets ?? 0
  const reg = props.data?.register_gross_assets ?? 0
  if (gross - reg <= 1) return null
  return `The Asset register covers ${formatMoney(reg, currency.value)} of ${formatMoney(gross, currency.value)} fixed assets on the books. Categories and the table below show registered assets only.`
})

// CSS var-based series colours for category bars (non-text fills, >=3:1 on white).
const categoryColors = [
  'var(--surface-blue-3)',
  'var(--surface-green-3)',
  'var(--surface-amber-3)',
  'var(--surface-red-5)',
  'var(--surface-gray-4)',
  'var(--surface-red-6)',
]
</script>
