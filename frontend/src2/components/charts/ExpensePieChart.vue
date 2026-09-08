<!--
Ranked share-of-total bar list, largest expense first.

A donut was the wrong encoding here: on the JKM ledger Cost of Goods Sold is
~96% of spend, so the other nine categories collapsed into invisible slivers and
the legend truncated the tail away entirely. A ranked bar list keeps every
category's real amount and its share of total on one scannable axis, and the
dominant category reads as a full bar instead of a mystery wedge.

The list is the content, not a caption: a screen reader reads category, amount
and percentage in order. The bars are decorative (length duplicates the
percentage already stated in text).
-->
<template>
  <div class="w-full">
    <template v-if="rows.length">
      <!-- Total, so each row's share has an anchor -->
      <div class="flex items-baseline justify-between mb-4">
        <span class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">
          Total
        </span>
        <span class="text-base font-semibold text-ink-gray-9 tnum">
          {{ formatCurrency(total) }}
        </span>
      </div>

      <ul class="space-y-3">
        <li v-for="(item, index) in rows" :key="index">
          <div class="flex items-center justify-between gap-3 mb-1">
            <span class="text-sm text-ink-gray-7 truncate" :title="item.category">
              {{ item.category }}
            </span>
            <span class="text-sm whitespace-nowrap shrink-0">
              <span class="font-medium text-ink-gray-9 tnum">{{ formatCurrency(item.value) }}</span>
              <span class="text-ink-gray-5 tnum ml-1.5">{{ formatPercent(item.pct) }}</span>
            </span>
          </div>
          <!-- Track is 100% of spend; fill is this category's share. A 3px floor
               keeps a real-but-tiny expense from vanishing to nothing. -->
          <div class="h-1.5 w-full rounded-full bg-surface-gray-3 overflow-hidden" aria-hidden="true">
            <div
              class="h-full rounded-full transition-all"
              :style="{
                width: barWidth(item.pct),
                minWidth: item.value > 0 ? '3px' : '0',
                backgroundColor: barColor,
              }"
            ></div>
          </div>
        </li>
      </ul>
    </template>

    <div v-else class="h-full flex items-center justify-center text-ink-gray-6">
      No expense data available
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { themeColor } from '../../utils/chartTheme'

/** Rows accept category/name/label + value/amount/percentage keys, all optional upstream. */
type PieRow = Record<string, number | string | boolean | null | undefined>

interface Props {
  data: PieRow[]
  currency?: string
}

const props = withDefaults(defineProps<Props>(), { currency: 'KES' })

const total = computed(() =>
  (props.data || []).reduce((sum, item) => sum + Number(item.value || item.amount || 0), 0),
)

const getPercentage = (value: number): number =>
  total.value === 0 ? 0 : (value / total.value) * 100

/**
 * Normalised rows, largest first. Percentages are recomputed from value/total
 * rather than trusting the upstream `percentage`, which arrives integer-rounded
 * so every sub-1% category came through as 0.
 */
const rows = computed(() =>
  (props.data || [])
    .map((item) => {
      const value = Number(item.value || item.amount || 0)
      return {
        category: String(item.category || item.name || item.label || 'Other'),
        value,
        pct: getPercentage(value),
      }
    })
    .sort((a, b) => b.value - a.value),
)

/**
 * One neutral accent for every bar. Bar length already encodes magnitude and
 * the label carries the meaning, so a per-category rainbow would only add noise.
 * Resolved at call time because ECharts-style CSS-var reading is what keeps a
 * `[data-theme]` switch correct.
 */
const barColor = computed(() => themeColor('--app-accent'))

/** Proportional fill; a category's share of total spend. */
const barWidth = (pct: number): string => `${Math.max(0, Math.min(100, pct))}%`

const formatCurrency = (value: number): string => {
  if (value >= 1_000_000) return `${props.currency} ${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${props.currency} ${(value / 1_000).toFixed(0)}K`
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: props.currency,
    minimumFractionDigits: 0,
  }).format(value)
}

/** Sub-0.1% amounts still carry a real value, so show `<0.1%` rather than a
 *  misleading rounded `0.0%`. */
const formatPercent = (value: number): string =>
  value > 0 && value < 0.1 ? '<0.1%' : `${value.toFixed(1)}%`
</script>
