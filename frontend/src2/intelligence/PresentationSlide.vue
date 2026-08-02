<template>
  <div class="presentation-slide" :class="slideClasses" :style="slideStyles">
    <!-- Title Slide Layout -->
    <div v-if="slide.type === 'title'" class="title-slide text-center py-16">
      <div class="max-w-4xl mx-auto">
        <div v-if="slide.content.logo_placeholder" class="mb-8">
          <div class="w-24 h-24 bg-surface-gray-3 rounded-lg mx-auto flex items-center justify-center">
            <Building class="w-12 h-12 text-ink-gray-5" />
          </div>
        </div>

        <h1 class="text-5xl font-bold mb-4" :class="headingClass">
          {{ slide.content.title }}
        </h1>

        <h2 class="text-2xl mb-6" :class="bodyClass">
          {{ slide.content.subtitle }}
        </h2>

        <div class="text-lg" :class="mutedClass">
          {{ slide.content.company }}
        </div>
      </div>
    </div>

    <!-- Overview Slide Layout -->
    <div v-else-if="slide.type === 'overview'" class="overview-slide p-8">
      <h2 class="text-3xl font-bold mb-8" :class="headingClass">
        {{ slide.content.title }}
      </h2>

      <!-- Metrics Grid Layout -->
      <div v-if="slide.content.layout === 'metrics_grid'" class="metrics-grid grid grid-cols-2 lg:grid-cols-3 gap-6">
        <div
          v-for="metric in slide.content.metrics"
          :key="metric.label"
          class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1"
        >
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-ink-gray-6 uppercase tracking-wide">{{ metric.label }}</p>
              <p class="text-2xl font-bold mt-2 text-ink-gray-9">
                {{ metric.formatted_value }}
              </p>
            </div>
            <div class="p-3 rounded-lg bg-surface-gray-2 text-ink-gray-5">
              <TrendingUp v-if="metric.trend === 'up'" class="w-6 h-6" />
              <TrendingDown v-else-if="metric.trend === 'down'" class="w-6 h-6" />
              <Minus v-else class="w-6 h-6" />
            </div>
          </div>
        </div>
      </div>

      <!-- Insights List Layout -->
      <div v-else-if="slide.content.layout === 'insights_list'" class="space-y-4">
        <div
          v-for="insight in slide.content.insights"
          :key="insight.title"
          class="bg-surface-white rounded-lg shadow-sm p-6"
        >
          <div class="flex items-start space-x-4">
            <div class="p-2 rounded-lg bg-surface-gray-2 text-ink-gray-5">
              <AlertCircle class="w-6 h-6" />
            </div>
            <div class="flex-1">
              <div class="flex items-center gap-2 mb-2">
                <h3 class="text-lg font-semibold text-ink-gray-9">{{ insight.title }}</h3>
                <Badge v-bind="severityBadge(priorityToSeverity(insight.impact))" size="sm" />
              </div>
              <p class="text-ink-gray-7 mb-2">{{ insight.insight }}</p>
              <div class="text-2xl font-bold text-ink-gray-9">{{ insight.value }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Recommendations Grid Layout -->
      <div v-else-if="slide.content.layout === 'recommendations_grid'" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div
          v-for="rec in slide.content.recommendations"
          :key="rec.title"
          class="bg-surface-white rounded-lg shadow-sm p-6 border border-outline-gray-1"
        >
          <div class="flex items-start justify-between mb-4">
            <h3 class="text-lg font-semibold text-ink-gray-9">{{ rec.title }}</h3>
            <Badge v-bind="severityBadge(priorityToSeverity(rec.priority))" size="sm" class="ml-2" />
          </div>
          <p class="text-ink-gray-7 mb-4">{{ rec.description }}</p>
          <div class="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span class="text-ink-gray-6">Impact:</span>
              <span class="ml-2 font-medium text-ink-gray-8">{{ rec.impact }}</span>
            </div>
            <div>
              <span class="text-ink-gray-6">Effort:</span>
              <span class="ml-2 font-medium text-ink-gray-8">{{ rec.effort }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Chart Slide Layout -->
    <div v-else-if="slide.type === 'chart'" class="chart-slide p-8">
      <h2 class="text-3xl font-bold mb-8" :class="headingClass">
        {{ slide.content.title }}
      </h2>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <!-- Chart Container -->
        <div class="lg:col-span-2">
          <div class="bg-surface-white rounded-lg shadow-sm p-6 h-80">
            <!--
              The server has been sending real `chart_data` all along
              (`presentation_service.py:175,239`): labels plus Chart.js-shaped
              datasets. This slot rendered a lucide icon and the words "Chart
              Visualization" instead, so a board deck presented a placeholder
              where the trend was supposed to be.
            -->
            <IntelligenceChart v-if="chartConfig" kind="axis" :config="chartConfig" class="h-full" />
            <!--
              An axis chart handed an empty series draws bare gridlines, which
              reads as "the value is flat" rather than "there is no data".
            -->
            <div v-else class="h-full flex items-center justify-center">
              <div class="text-center">
                <BarChart class="w-8 h-8 mx-auto mb-2 text-ink-gray-4" aria-hidden="true" />
                <p class="text-sm text-ink-gray-6">No trend data for this period</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Chart Insights -->
        <div class="space-y-4">
          <h3 class="text-xl font-semibold text-ink-gray-9">Key Insights</h3>
          <div
            v-for="insight in slide.content.insights"
            :key="insight"
            class="bg-surface-white rounded-lg shadow-sm p-4"
          >
            <div class="flex items-center space-x-3">
              <div class="w-2 h-2 rounded-full bg-surface-gray-5 flex-shrink-0"></div>
              <span class="text-ink-gray-7">{{ insight }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Table Slide Layout -->
    <div v-else-if="slide.type === 'table'" class="table-slide p-8">
      <h2 class="text-3xl font-bold mb-8" :class="headingClass">
        {{ slide.content.title }}
      </h2>

      <div v-if="slide.content.table_data" class="bg-surface-white rounded-lg shadow-sm overflow-hidden">
        <table class="min-w-full divide-y divide-outline-gray-1">
          <thead class="bg-surface-gray-1">
            <tr>
              <th
                v-for="header in slide.content.table_data.headers"
                :key="header"
                scope="col"
                class="px-6 py-4 text-left text-sm font-semibold text-ink-gray-9 uppercase tracking-wider"
              >
                {{ header }}
              </th>
            </tr>
          </thead>
          <tbody class="bg-surface-white divide-y divide-outline-gray-1">
            <tr
              v-for="(row, index) in slide.content.table_data.rows"
              :key="index"
              class="hover:bg-surface-gray-1"
            >
              <td
                v-for="(cell, cellIndex) in row"
                :key="cellIndex"
                class="px-6 py-4 whitespace-nowrap text-sm text-ink-gray-9"
              >
                <span v-if="cellIndex === row.length - 1" class="font-medium">{{ cell }}</span>
                <span v-else>{{ cell }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Default/Unknown Layout -->
    <div v-else class="default-slide p-8">
      <div class="text-center py-16">
        <h2 class="text-3xl font-bold text-ink-gray-9 mb-4">{{ slide.content.title || 'Slide Content' }}</h2>
        <p class="text-ink-gray-6">Slide type: {{ slide.type }}</p>
      </div>
    </div>

    <!-- Slide Footer -->
    <div v-if="fullscreen" class="slide-footer absolute bottom-4 left-8 right-8">
      <div class="flex items-center justify-between text-ink-white text-sm">
        <div>{{ slide.content.company || 'Company Name' }}</div>
        <div>{{ new Date().toLocaleDateString() }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import {
  Building,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertCircle,
  BarChart
} from 'lucide-vue-next'
import { severityBadge, type Severity } from '../utils/status'
import { presentationChartConfig } from './presentationChart'
import IntelligenceChart from './components/IntelligenceChart.vue'

const props = defineProps({
  slide: {
    type: Object,
    required: true
  },
  fullscreen: {
    type: Boolean,
    default: false
  },
  /**
   * Deck color scheme from the backend. Values are not used inline (banned hex);
   * kept for backward compatibility with consumers passing the prop.
   */
  colors: {
    type: Object,
    default: () => ({})
  }
})

/** Transposition lives in `presentationChart.ts`, where it is unit-tested. */
const chartConfig = computed(() =>
  presentationChartConfig(props.slide?.content?.chart_data, props.slide?.content?.chart_type),
)

const slideClasses = computed(() => [
  'presentation-slide',
  `slide-${props.slide.type}`,
  props.fullscreen
    ? 'fullscreen-slide text-ink-white'
    : 'embedded-slide bg-surface-gray-1',
])

const slideStyles = computed(() => ({
  minHeight: props.fullscreen ? '100vh' : '400px',
  position: 'relative' as const,
}))

/** Token classes for headings — white on fullscreen dark bg, dark on embedded light bg. */
const headingClass = computed(() =>
  props.fullscreen ? 'text-ink-white' : 'text-ink-gray-9'
)
const bodyClass = computed(() =>
  props.fullscreen ? 'text-ink-white' : 'text-ink-gray-7'
)
const mutedClass = computed(() =>
  props.fullscreen ? 'text-ink-white' : 'text-ink-gray-6'
)

/** Map a priority / impact string to a Severity for Badge rendering. */
function priorityToSeverity(priority: string | undefined | null): Severity {
  const map: Record<string, Severity> = { high: 'high', medium: 'medium', low: 'low' }
  return map[priority?.toLowerCase() ?? ''] ?? 'none'
}
</script>

<style scoped>
.presentation-slide {
  transition: all 0.3s ease;
}

@media (prefers-reduced-motion: reduce) {
  .presentation-slide {
    transition: none;
  }

  .metrics-grid > div {
    animation: none;
  }
}

.fullscreen-slide {
  padding: 2rem;
}

.embedded-slide {
  padding: 1.5rem;
  border-radius: 0.5rem;
}

.title-slide h1 {
  line-height: 1.1;
  letter-spacing: -0.02em;
}

.title-slide h2 {
  line-height: 1.3;
}

/* Staggered entry animation for metrics grid */
.metrics-grid > div {
  animation: slideInUp 0.6s ease-out both;
}

.metrics-grid > div:nth-child(2) { animation-delay: 0.1s; }
.metrics-grid > div:nth-child(3) { animation-delay: 0.2s; }
.metrics-grid > div:nth-child(4) { animation-delay: 0.3s; }
.metrics-grid > div:nth-child(5) { animation-delay: 0.4s; }
.metrics-grid > div:nth-child(6) { animation-delay: 0.5s; }

@keyframes slideInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Responsive text scaling */
@media (max-width: 768px) {
  .title-slide h1 { font-size: 2.5rem; }
  .title-slide h2 { font-size: 1.5rem; }
  .overview-slide h2,
  .chart-slide h2,
  .table-slide h2 { font-size: 2rem; }
}

/* Print optimizations */
@media print {
  .presentation-slide {
    background: white !important;
    color: black !important;
    page-break-inside: avoid;
    margin-bottom: 2rem;
  }

  .fullscreen-slide {
    min-height: auto;
  }

  .slide-footer {
    position: static;
    border-top: 1px solid #e5e7eb;
    padding-top: 1rem;
    margin-top: 2rem;
    color: black !important;
  }
}
</style>
