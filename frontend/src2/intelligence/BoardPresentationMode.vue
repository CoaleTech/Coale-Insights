<template>
  <div class="board-presentation-mode">
    <!-- Header / Control Bar -->
    <div v-if="!isFullscreen" class="presentation-toggle-bar bg-surface-white shadow-sm border-b border-outline-gray-1 px-6 py-4">
      <div class="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="text-2xl font-bold text-ink-gray-9">Board Presentations</h1>
          <p class="text-sm text-ink-gray-6 mt-1">Generate board-ready presentations from intelligence dashboards</p>
        </div>

        <div class="flex items-center space-x-3">
          <!-- Dashboard Type Selector -->
          <div class="flex items-center space-x-2">
            <label class="text-sm font-medium text-ink-gray-7">Dashboard:</label>
            <Select
              v-model="selectedDashboardType"
              :options="dashboardTypeOptions"
            />
          </div>

          <!-- Presentation Type Selector -->
          <div class="flex items-center space-x-2">
            <label class="text-sm font-medium text-ink-gray-7">Type:</label>
            <Select
              v-model="presentationType"
              :options="presentationTypeOptions"
            />
          </div>

          <Button @click="generatePresentation" :loading="generating" variant="solid" theme="gray">
            <template #prefix><FileText class="w-4 h-4" /></template>
            Generate
          </Button>

          <template v-if="presentationEnabled">
            <Button @click="toggleFullscreen" variant="outline">
              <template #prefix><Maximize class="w-4 h-4" /></template>
              Fullscreen
            </Button>

            <Button @click="exportPresentation" variant="outline">
              <template #prefix><Download class="w-4 h-4" /></template>
              Export
            </Button>

            <Button @click="resetPresentation" variant="subtle">
              <template #prefix><X class="w-4 h-4" /></template>
              Reset
            </Button>
          </template>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="generating" class="flex items-center justify-center" style="min-height: 60vh">
      <div class="text-center">
        <LoadingIndicator class="h-12 w-12 mx-auto mb-4 text-ink-gray-6" />
        <p class="text-ink-gray-7 font-medium">Generating board-ready presentation...</p>
        <p class="text-sm text-ink-gray-6 mt-1">Analyzing {{ selectedDashboardType }} dashboard data</p>
      </div>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="flex items-center justify-center" style="min-height: 60vh">
      <div class="text-center">
        <AlertTriangle class="w-12 h-12 mx-auto text-ink-gray-5" />
        <p class="mt-4 text-ink-gray-9 font-medium">Failed to generate presentation</p>
        <p class="text-ink-gray-6 mt-1">{{ error }}</p>
        <Button @click="generatePresentation" class="mt-4" variant="solid" theme="gray">
          Try Again
        </Button>
      </div>
    </div>

    <!-- Empty State (no presentation generated yet) -->
    <div v-else-if="!presentationEnabled && !isFullscreen" class="flex items-center justify-center" style="min-height: 60vh">
      <div class="text-center max-w-md">
        <Presentation class="w-16 h-16 mx-auto text-ink-gray-5 mb-4" />
        <h2 class="text-xl font-semibold text-ink-gray-9 mb-2">No Presentation Generated</h2>
        <p class="text-ink-gray-6 mb-6">
          Select a dashboard type and click <strong>Generate</strong> to create a board-ready presentation with executive summaries, key insights, and strategic recommendations.
        </p>
        <Button @click="generatePresentation" variant="solid" theme="gray" size="lg">
          <template #prefix><FileText class="w-4 h-4" /></template>
          Generate Presentation
        </Button>
      </div>
    </div>

    <!-- Fullscreen Presentation Mode -->
    <div v-if="isFullscreen" class="fullscreen-presentation fixed inset-0 z-50 bg-surface-gray-7">
      <!-- Presentation Navigation -->
      <div class="absolute top-4 left-4 right-4 z-10">
        <div class="flex items-center justify-between">
          <div class="text-ink-white">
            <h2 class="text-xl font-semibold">{{ presentationData.metadata?.dashboard_type }} Intelligence</h2>
            <p class="text-sm opacity-75">Slide {{ currentSlide }} of {{ totalSlides }}</p>
          </div>

          <div class="flex items-center space-x-3">
            <Button
              @click="previousSlide"
              variant="ghost"
              class="text-ink-white hover:bg-surface-gray-6"
              aria-label="Previous slide"
            >
              <ChevronLeft class="w-5 h-5" />
            </Button>
            <Button
              @click="nextSlide"
              variant="ghost"
              class="text-ink-white hover:bg-surface-gray-6"
              aria-label="Next slide"
            >
              <ChevronRight class="w-5 h-5" />
            </Button>
            <Button
              @click="exitFullscreen"
              variant="ghost"
              class="text-ink-white hover:bg-surface-gray-6"
              aria-label="Exit fullscreen"
            >
              <X class="w-5 h-5" />
            </Button>
          </div>
        </div>
      </div>

      <!-- Slide Content -->
      <div class="h-full flex items-center justify-center p-8 pt-20">
        <div v-if="currentSlideData" class="w-full max-w-6xl">
          <PresentationSlide
            :slide="currentSlideData"
            :fullscreen="true"
            :colors="presentationData.metadata?.color_scheme || {}"
          />
        </div>
      </div>

      <!-- Slide Indicators -->
      <div class="absolute bottom-8 left-1/2 transform -translate-x-1/2">
        <div class="flex space-x-2" role="tablist" aria-label="Slide navigation">
          <button
            v-for="n in totalSlides"
            :key="n"
            role="tab"
            :aria-selected="n === currentSlide"
            :aria-label="`Go to slide ${n}`"
            @click="goToSlide(n)"
            class="w-3 h-3 rounded-full motion-reduce:transition-none transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-white"
            :class="n === currentSlide ? 'bg-surface-white' : 'bg-surface-gray-4 hover:bg-surface-gray-3'"
          ></button>
        </div>
      </div>
    </div>

    <!-- Regular Presentation View -->
    <div v-else-if="presentationEnabled" class="presentation-view bg-surface-gray-1 min-h-screen">
      <!-- Executive Summary -->
      <div v-if="presentationData.executive_summary" class="bg-surface-white shadow-sm mb-6 rounded-lg">
        <div class="px-6 py-8">
          <h2 class="text-2xl font-bold text-ink-gray-9 mb-4">Executive Summary</h2>
          <div class="prose prose-lg max-w-none">
            <p class="text-ink-gray-7 leading-relaxed">{{ presentationData.executive_summary.text }}</p>
          </div>

          <!-- Key Points -->
          <div v-if="presentationData.executive_summary.key_points?.length" class="mt-6">
            <h3 class="text-lg font-semibold text-ink-gray-9 mb-3">Key Points</h3>
            <ul class="space-y-2">
              <li
                v-for="point in presentationData.executive_summary.key_points"
                :key="point"
                class="flex items-start"
              >
                <CheckCircle class="w-5 h-5 text-ink-gray-5 mt-0.5 mr-3 flex-shrink-0" />
                <span class="text-ink-gray-7">{{ point }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Key Insights Grid -->
      <div v-if="presentationData.key_insights?.length" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        <Card v-for="insight in presentationData.key_insights" :key="insight.title" class="p-6">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-semibold text-ink-gray-9">{{ insight.title }}</h3>
            <Badge v-bind="severityBadge(priorityToSeverity(insight.impact))" size="sm" />
          </div>
          <div class="text-2xl font-bold text-ink-gray-9 mb-2">{{ insight.value }}</div>
          <p class="text-sm text-ink-gray-6">{{ insight.insight }}</p>
        </Card>
      </div>

      <!-- Presentation Slides -->
      <div class="space-y-8">
        <div
          v-for="slide in presentationData.slides"
          :key="slide.id"
          class="bg-surface-white shadow-lg rounded-lg overflow-hidden"
        >
          <PresentationSlide
            :slide="slide"
            :fullscreen="false"
            :colors="presentationData.metadata?.color_scheme || {}"
          />
        </div>
      </div>

      <!-- Recommendations Section -->
      <div v-if="presentationData.recommendations?.length" class="bg-surface-white shadow-sm mt-8 rounded-lg">
        <div class="px-6 py-8">
          <h2 class="text-2xl font-bold text-ink-gray-9 mb-6">Strategic Recommendations</h2>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div
              v-for="rec in presentationData.recommendations"
              :key="rec.title"
              class="border border-outline-gray-1 rounded-lg p-6"
            >
              <div class="flex items-start justify-between mb-4">
                <h3 class="font-semibold text-ink-gray-9">{{ rec.title }}</h3>
                <Badge v-bind="severityBadge(priorityToSeverity(rec.priority))" size="sm" />
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
      </div>
    </div>

    <!-- Export Modal -->
    <Dialog
      v-model="showExportModal"
      :options="{
        title: 'Export Presentation',
        actions: [
          { label: 'Cancel', variant: 'outline', onClick: () => showExportModal = false },
          { label: 'Export', variant: 'solid', loading: exporting, onClick: performExport }
        ]
      }"
    >
      <template #body-content>
        <div class="space-y-6">
          <div>
            <label class="block text-sm font-medium text-ink-gray-7 mb-2">Export Format</label>
            <div class="space-y-3">
              <label v-for="format in exportFormats" :key="format.value" class="flex items-center">
                <input
                  type="radio"
                  v-model="exportFormat"
                  :value="format.value"
                  class="h-4 w-4 border-outline-gray-2 focus-visible:ring-2 focus-visible:ring-outline-gray-3"
                />
                <span class="ml-3">
                  <span class="font-medium text-ink-gray-8">{{ format.label }}</span>
                  <span class="text-sm text-ink-gray-6 block">{{ format.description }}</span>
                </span>
              </label>
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-ink-gray-7 mb-2">Export Options</label>
            <div class="space-y-2">
              <label class="flex items-center">
                <input type="checkbox" v-model="exportOptions.includeCharts" class="rounded border-outline-gray-2" />
                <span class="ml-2 text-sm text-ink-gray-7">Include Charts and Visualizations</span>
              </label>
              <label class="flex items-center">
                <input type="checkbox" v-model="exportOptions.includeTables" class="rounded border-outline-gray-2" />
                <span class="ml-2 text-sm text-ink-gray-7">Include Data Tables</span>
              </label>
              <label class="flex items-center">
                <input type="checkbox" v-model="exportOptions.includeRecommendations" class="rounded border-outline-gray-2" />
                <span class="ml-2 text-sm text-ink-gray-7">Include Recommendations</span>
              </label>
              <label class="flex items-center">
                <input type="checkbox" v-model="exportOptions.companyBranding" class="rounded border-outline-gray-2" />
                <span class="ml-2 text-sm text-ink-gray-7">Include Company Branding</span>
              </label>
            </div>
          </div>

          <p v-if="exportFormat !== 'json'" class="text-xs text-ink-gray-5">
            Options above are recorded with the export request but not yet applied to its content.
          </p>

          <div v-if="exportError" class="rounded-lg bg-surface-red-1 border border-outline-red-2 px-3 py-2">
            <p class="text-sm text-ink-red-4">{{ exportError }}</p>
          </div>
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
defineOptions({ name: 'BoardPresentationMode' })
import { ref, computed, onMounted, onUnmounted } from 'vue'
import {
  Button,
  Card,
  Badge,
  Dialog,
  Select,
  LoadingIndicator,
} from 'frappe-ui'
import {
  FileText,
  Presentation,
  Maximize,
  Download,
  ChevronLeft,
  ChevronRight,
  X,
  CheckCircle,
  AlertTriangle
} from 'lucide-vue-next'
import PresentationSlide from './PresentationSlide.vue'
import { apiCall } from '../helpers/api'
import { BOARD_DASHBOARD_OPTIONS } from '../helpers/dashboards'
import { severityBadge } from '../utils/status'

/** Map a priority / impact string to a Severity. */
function priorityToSeverity(priority) {
  const map = { high: 'high', medium: 'medium', low: 'low' }
  return map[priority?.toLowerCase()] ?? 'none'
}

// Props (optional - component works standalone or embedded)
const props = defineProps({
  dashboardType: {
    type: String,
    default: ''
  },
  dashboardData: {
    type: Object,
    default: () => ({})
  }
})

// From `helpers/dashboards`. The previous six-entry list both under- and
// over-shot: seven domains could not be presented at all, while `operations`
// named a dashboard that has never existed and `budget` named one that
// dissolved into Finance, so selecting either sent the server a dead identity.
const dashboardTypeOptions = BOARD_DASHBOARD_OPTIONS

const presentationTypeOptions = [
  { value: 'executive', label: 'Executive Summary' },
  { value: 'detailed', label: 'Detailed Analysis' },
  { value: 'comparison', label: 'Comparison View' },
]

// Reactive state
const selectedDashboardType = ref(props.dashboardType || 'executive')
const presentationEnabled = ref(false)
const presentationType = ref('executive')
const isFullscreen = ref(false)
const generating = ref(false)
const error = ref(null)
const exporting = ref(false)
const exportError = ref(null)
const showExportModal = ref(false)
const currentSlide = ref(1)
const presentationData = ref({})

// Export options
const exportFormat = ref('powerpoint')
const exportOptions = ref({
  includeCharts: true,
  includeTables: true,
  includeRecommendations: true,
  companyBranding: true
})

const exportFormats = [
  {
    value: 'powerpoint',
    label: 'PowerPoint (.pptx)',
    description: 'Structured slide data for PowerPoint (not yet a downloadable .pptx file)'
  },
  {
    value: 'pdf',
    label: 'PDF Document (.pdf)',
    description: 'Structured page data for PDF (not yet a downloadable .pdf file)'
  },
  {
    value: 'html',
    label: 'Web Page (.html)',
    description: 'Not yet available'
  },
  {
    value: 'json',
    label: 'JSON Data (.json)',
    description: 'Structured data for custom processing'
  }
]

// Computed properties
const totalSlides = computed(() => {
  return presentationData.value.slides?.length || 0
})

const currentSlideData = computed(() => {
  if (!presentationData.value.slides || currentSlide.value < 1 || currentSlide.value > totalSlides.value) {
    return null
  }
  return presentationData.value.slides[currentSlide.value - 1]
})

const activeDashboardData = computed(() => {
  return Object.keys(props.dashboardData).length > 0 ? props.dashboardData : {}
})

// Methods
const generatePresentation = async () => {
  generating.value = true
  error.value = null

  try {
    const result = await apiCall('insights.api.ml.generate_presentation_data', {
      dashboard_type: selectedDashboardType.value,
      dashboard_data: activeDashboardData.value,
      presentation_type: presentationType.value
    })

    if (result && !result.error) {
      presentationData.value = result
      presentationEnabled.value = true
      currentSlide.value = 1
    } else {
      throw new Error(result?.error || 'Failed to generate presentation')
    }
  } catch (err) {
    console.error('Error generating presentation:', err)
    error.value = err.message || 'Failed to generate presentation'
  } finally {
    generating.value = false
  }
}

const resetPresentation = () => {
  presentationEnabled.value = false
  isFullscreen.value = false
  presentationData.value = {}
  currentSlide.value = 1
  error.value = null
}

const toggleFullscreen = () => {
  isFullscreen.value = !isFullscreen.value
}

const exitFullscreen = () => {
  isFullscreen.value = false
}

const nextSlide = () => {
  if (currentSlide.value < totalSlides.value) {
    currentSlide.value++
  }
}

const previousSlide = () => {
  if (currentSlide.value > 1) {
    currentSlide.value--
  }
}

const goToSlide = (slideNumber) => {
  if (slideNumber >= 1 && slideNumber <= totalSlides.value) {
    currentSlide.value = slideNumber
  }
}

const exportPresentation = () => {
  exportError.value = null
  showExportModal.value = true
}

const performExport = async () => {
  exporting.value = true
  exportError.value = null

  try {
    if (exportFormat.value === 'json') {
      // The full presentation payload is already in memory -- no backend
      // round-trip needed, and no fabrication risk (it's the real data).
      downloadJson(presentationData.value)
      showExportModal.value = false
      return
    }

    if (exportFormat.value === 'html') {
      // No HTML document renderer exists yet -- be honest instead of
      // downloading the JSON payload mislabeled as an .html file.
      exportError.value = 'HTML export is not available yet. Use JSON to get the underlying presentation data.'
      return
    }

    const endpoint = exportFormat.value === 'powerpoint'
      ? 'insights.api.ml.export_presentation_powerpoint'
      : 'insights.api.ml.export_presentation_pdf'

    const result = await apiCall(endpoint, {
      presentation_data: presentationData.value,
      export_options: exportOptions.value
    })

    if (!result || result.status !== 'success') {
      throw new Error(result?.message || 'Export failed')
    }

    if (result.data?.download_ready === false) {
      // Backend is honest: this format has no real document generator yet.
      exportError.value = result.message || 'This export format is not yet available as a downloadable file.'
      return
    }

    downloadExportedFile(result.data, exportFormat.value)
    showExportModal.value = false
  } catch (err) {
    console.error('Error exporting presentation:', err)
    exportError.value = 'Failed to export: ' + (err.message || 'Unknown error')
  } finally {
    exporting.value = false
  }
}

const downloadJson = (data) => {
  const timestamp = new Date().getTime()
  const filename = `presentation_${selectedDashboardType.value}_${timestamp}.json`
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

const downloadExportedFile = (exportData, format) => {
  // Reachable only once a backend export genuinely sets
  // `download_ready: true` for `format` (currently never, for both
  // powerpoint and pdf -- see presentation_service.py). Kept as the
  // landing pad for when real binary generation is implemented.
  const timestamp = new Date().getTime()
  const ext = format === 'powerpoint' ? 'pptx' : format
  const filename = `presentation_${selectedDashboardType.value}_${timestamp}.${ext}`
  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/octet-stream' })

  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// Keyboard navigation — leave the addEventListener/onUnmounted pair intact
const handleKeyNavigation = (event) => {
  if (!isFullscreen.value) return

  switch (event.code) {
    case 'ArrowLeft':
    case 'ArrowUp':
      event.preventDefault()
      previousSlide()
      break
    case 'ArrowRight':
    case 'ArrowDown':
    case 'Space':
      event.preventDefault()
      nextSlide()
      break
    case 'Escape':
      event.preventDefault()
      exitFullscreen()
      break
    case 'Home':
      event.preventDefault()
      goToSlide(1)
      break
    case 'End':
      event.preventDefault()
      goToSlide(totalSlides.value)
      break
  }
}

// Lifecycle hooks
onMounted(() => {
  document.addEventListener('keydown', handleKeyNavigation)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyNavigation)
})
</script>

<style scoped>
.board-presentation-mode {
  min-height: 100vh;
  background: var(--surface-gray-1, #f9fafb);
}

.presentation-view {
  padding: 2rem;
}

/* Smooth transitions with reduced-motion opt-out */
.presentation-view > * {
  transition: all 0.3s ease;
}

@media (prefers-reduced-motion: reduce) {
  .presentation-view > * {
    transition: none;
  }
}

/* Print styles for PDF export */
@media print {
  .presentation-toggle-bar {
    display: none !important;
  }

  .presentation-view {
    padding: 0;
    background: white !important;
  }

  .bg-surface-gray-1 {
    background: white !important;
  }
}
</style>
