<template>
  <div class="ink-fix flex h-full flex-col overflow-hidden">
    <!-- Header -->
    <header class="flex flex-shrink-0 flex-col items-start gap-3 border-b border-outline-gray-1 bg-surface-white px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-center gap-2">
        <Search class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
        <div>
          <h1 class="text-xl font-semibold text-ink-gray-9">Global Intelligence Search</h1>
          <p class="mt-0.5 text-sm text-ink-gray-6">Search across all business intelligence dashboards</p>
        </div>
      </div>
    </header>

    <!-- Scrollable content area -->
    <div class="flex-1 overflow-auto px-6 py-5 space-y-5">

      <!-- Search Interface -->
      <div class="space-y-4">
        <!-- Search Input -->
        <div class="relative">
          <div
            class="relative flex items-center bg-surface-white border rounded-lg shadow-sm transition-all duration-200 motion-reduce:transition-none"
            :class="searchFocused ? 'border-outline-gray-3 ring-1 ring-outline-gray-3' : 'border-outline-gray-2'"
          >
            <Search class="absolute left-3 w-5 h-5 text-ink-gray-5" aria-hidden="true" />
            <input
              ref="searchInput"
              v-model="searchQuery"
              type="text"
              placeholder="Search across all dashboards... (e.g., 'budget variance alerts', 'employee metrics', 'sales trends')"
              class="flex-1 pl-10 pr-32 py-3 border-0 rounded-lg bg-transparent focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 text-ink-gray-8 placeholder-ink-gray-5 text-sm sm:text-base"
              @focus="searchFocused = true"
              @blur="handleSearchBlur"
              @input="handleSearchInput"
              @keydown.enter="performSearch"
              @keydown.down="navigateSuggestions(1)"
              @keydown.up="navigateSuggestions(-1)"
              @keydown.escape="clearSuggestions"
            />
            <div class="absolute right-2 flex items-center space-x-2">
              <Button v-if="searchQuery" variant="ghost" size="sm" :icon="X" label="Clear search" @click="clearSearch" />
              <Button variant="solid" size="sm" :loading="isSearching" @click="performSearch">Search</Button>
            </div>
          </div>

          <!-- Suggestions Dropdown -->
          <div
            v-show="showSuggestions && suggestions.length > 0"
            class="absolute top-full mt-1 w-full bg-surface-white border border-outline-gray-1 rounded-lg shadow-lg z-50 max-h-64 overflow-y-auto"
          >
            <div
              v-for="(suggestion, index) in suggestions"
              :key="index"
              role="option"
              :aria-selected="activeSuggestionIndex === index"
              tabindex="0"
              class="px-4 py-3 cursor-pointer transition-colors duration-150 motion-reduce:transition-none"
              :class="activeSuggestionIndex === index ? 'bg-surface-gray-2' : 'hover:bg-surface-gray-1'"
              @click="selectSuggestion(suggestion)"
              @mouseenter="activeSuggestionIndex = index"
              @keydown.enter="selectSuggestion(suggestion)"
              @keydown.space.prevent="selectSuggestion(suggestion)"
            >
              <div class="flex items-center justify-between">
                <span class="text-ink-gray-8 text-sm">{{ suggestion.text }}</span>
                <Badge :theme="getSuggestionTheme(suggestion.type)" :label="getSuggestionLabel(suggestion.type)" size="sm" />
              </div>
            </div>
          </div>
        </div>

        <!-- Search Filters -->
        <div v-show="showAdvancedFilters" class="bg-surface-gray-1 rounded-lg p-4 space-y-4">
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="space-y-1">
              <label class="text-sm font-medium text-ink-gray-7" for="filter-dashboard">Dashboard</label>
              <Select id="filter-dashboard" v-model="searchFilters.dashboard" :options="dashboardOptions" class="text-sm" />
            </div>
            <div class="space-y-1">
              <label class="text-sm font-medium text-ink-gray-7" for="filter-time">Time Period</label>
              <Select id="filter-time" v-model="searchFilters.time_period" :options="timePeriodOptions" class="text-sm" />
            </div>
            <div class="space-y-1">
              <label class="text-sm font-medium text-ink-gray-7" for="filter-category">Category</label>
              <Select id="filter-category" v-model="searchFilters.category" :options="categoryOptions" class="text-sm" />
            </div>
            <div class="space-y-1">
              <label class="text-sm font-medium text-ink-gray-7" for="filter-priority">Priority</label>
              <Select id="filter-priority" v-model="searchFilters.priority" :options="priorityOptions" class="text-sm" />
            </div>
          </div>
          <div class="flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" @click="clearFilters">Clear Filters</Button>
            <Button variant="solid" theme="gray" size="sm" @click="applyFilters">Apply Filters</Button>
          </div>
        </div>

        <!-- Controls Row -->
        <div class="flex items-center flex-wrap gap-2">
          <Button variant="ghost" size="sm" @click="toggleAdvancedFilters">
            <template #prefix><Filter class="w-4 h-4" /></template>
            {{ showAdvancedFilters ? 'Hide' : 'Show' }} Filters
          </Button>
          <Button variant="ghost" size="sm" @click="showSearchHistory = !showSearchHistory">
            <template #prefix><Clock class="w-4 h-4" /></template>
            Search History
          </Button>
          <Button variant="ghost" size="sm" @click="showSearchHelp = true">
            <template #prefix><HelpCircle class="w-4 h-4" /></template>
            Help
          </Button>
        </div>
      </div>

      <!-- Search Results -->
      <div v-if="hasSearched" class="space-y-6">

        <!-- 1. Loading -->
        <div v-if="isSearching" class="space-y-3">
          <SkeletonBlock class="h-6 w-48 rounded" />
          <SkeletonBlock class="h-24 w-full rounded-lg" />
          <SkeletonBlock class="h-24 w-full rounded-lg" />
          <SkeletonBlock class="h-24 w-full rounded-lg" />
        </div>

        <!-- 2. Error -->
        <div v-else-if="searchError" class="rounded-lg border border-outline-gray-1 bg-surface-white p-4 space-y-3">
          <p class="text-sm text-ink-gray-7">{{ searchError }}</p>
          <Button variant="subtle" size="sm" @click="performSearch">Try Again</Button>
        </div>

        <!-- 3. Results -->
        <template v-else>
          <!-- Results Header -->
          <div class="flex items-center justify-between">
            <div>
              <p class="text-xl font-semibold text-ink-gray-9">
                Search Results
                <span v-if="searchResults?.total_results" class="text-base font-normal text-ink-gray-6">
                  ({{ searchResults.total_results }} found)
                </span>
              </p>
              <p v-if="lastSearchQuery" class="text-sm text-ink-gray-6">Results for: "{{ lastSearchQuery }}"</p>
            </div>
            <Button variant="ghost" size="sm" @click="exportSearchResults">
              <template #prefix><Download class="w-4 h-4" /></template>
              Export
            </Button>
          </div>

          <!-- Search Summary -->
          <div v-if="searchResults?.summary">
            <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
              <div class="space-y-4">
                <div class="flex items-center flex-wrap gap-x-6 gap-y-3">
                  <div class="flex items-center gap-2">
                    <Database class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                    <div class="flex flex-col">
                      <span class="text-lg font-semibold text-ink-gray-9">{{ searchResults.summary.domains_searched }}</span>
                      <span class="text-xs text-ink-gray-6 uppercase tracking-wide">Dashboards Searched</span>
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <Tag class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                    <div class="flex flex-col">
                      <span class="text-lg font-semibold text-ink-gray-9">{{ searchResults.summary.categories_found }}</span>
                      <span class="text-xs text-ink-gray-6 uppercase tracking-wide">Categories Found</span>
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <Zap class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                    <div class="flex flex-col">
                      <span class="text-lg font-semibold text-ink-gray-9">{{ searchResults.summary.search_quality }}</span>
                      <span class="text-xs text-ink-gray-6 uppercase tracking-wide">Search Quality</span>
                    </div>
                  </div>
                </div>
                <div v-if="agentResponse" class="flex flex-col gap-1">
                  <div class="flex items-center gap-2">
                    <Bot class="w-4 h-4 text-ink-gray-6" aria-hidden="true" />
                    <span class="text-sm font-medium text-ink-gray-7">Search Assistant</span>
                  </div>
                  <p class="text-ink-gray-7 text-sm leading-relaxed">{{ agentResponse }}</p>
                </div>
              </div>
            </div>
          </div>

          <!-- No Results -->
          <div v-if="searchResults?.total_results === 0" class="text-center py-12">
            <div class="space-y-6">
              <SearchX class="w-12 h-12 text-ink-gray-5 mx-auto" aria-hidden="true" />
              <p class="text-lg font-semibold text-ink-gray-9">No Results Found</p>
              <p class="text-ink-gray-6">We couldn't find any results matching your search criteria.</p>
              <div v-if="searchResults?.suggestions?.length" class="space-y-3">
                <p class="text-sm font-medium text-ink-gray-7">Try these suggestions:</p>
                <div class="flex flex-wrap gap-2 justify-center">
                  <Button
                    v-for="suggestion in searchResults.suggestions"
                    :key="suggestion"
                    variant="ghost"
                    size="sm"
                    @click="searchQuery = suggestion; performSearch()"
                  >{{ suggestion }}</Button>
                </div>
              </div>
              <div v-if="navigationRecommendations" class="space-y-3 text-left max-w-sm mx-auto">
                <p class="text-sm font-medium text-ink-gray-7">{{ navigationRecommendations.message }}</p>
                <div class="space-y-2">
                  <div
                    v-for="rec in navigationRecommendations.suggestions"
                    :key="rec.dashboard_name"
                    class="rounded-lg border border-outline-gray-1 bg-surface-white p-3 hover:bg-surface-gray-1 cursor-pointer transition-colors duration-150 motion-reduce:transition-none"
                    @click="navigateToDashboard(rec.url)"
                  >
                    <div class="flex items-center gap-3">
                      <ArrowRight class="w-4 h-4 text-ink-gray-6 flex-shrink-0" aria-hidden="true" />
                      <div class="flex flex-col">
                        <span class="text-sm font-medium text-ink-gray-9">{{ rec.dashboard_name }}</span>
                        <span class="text-xs text-ink-gray-6">{{ rec.reason }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Results List -->
          <div v-else class="space-y-4">
            <Tabs v-model="activeResultViewIndex" :tabs="resultTabItems" />
            <div class="space-y-3">
              <div
                v-for="result in filteredResults"
                :key="result.id"
                role="button"
                tabindex="0"
                class="cursor-pointer"
                @click="navigateToResult(result)"
                @keydown.enter="navigateToResult(result)"
              >
                <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4 hover:bg-surface-gray-1 transition-all duration-150 motion-reduce:transition-none">
                  <div class="space-y-3">
                    <div class="flex items-start justify-between gap-3">
                      <div class="flex-1 min-w-0 space-y-2">
                        <h4 class="text-base font-medium text-ink-gray-9 leading-tight">{{ result.title }}</h4>
                        <div class="flex items-center flex-wrap gap-2">
                          <Badge :theme="getCategoryTheme(result.category)" :label="getCategoryLabel(result.category)" size="sm" />
                          <Badge :label="getDomainLabel(result.metadata?.domain || '')" size="sm" />
                          <span class="text-xs text-ink-gray-6">{{ Math.round((result.relevance_score || 0) * 100) }}% match</span>
                        </div>
                      </div>
                      <div class="flex items-center gap-1 flex-shrink-0">
                        <Button variant="ghost" size="sm" :icon="Star" label="Save to favorites" @click.stop="saveToFavorites(result)" />
                        <Button variant="ghost" size="sm" :icon="ArrowRight" label="Go to result" @click="navigateToResult(result)" />
                      </div>
                    </div>
                    <p class="text-ink-gray-6 text-sm leading-relaxed">{{ result.preview }}</p>
                    <div class="flex items-center justify-between text-xs text-ink-gray-6">
                      <div class="flex items-center gap-1">
                        <Folder class="w-3 h-3" aria-hidden="true" />
                        <span class="truncate max-w-xs">{{ result.source_path }}</span>
                      </div>
                      <div v-if="result.metadata?.last_updated" class="flex items-center gap-1">
                        <Clock class="w-3 h-3" aria-hidden="true" />
                        <span>Updated {{ formatDateTime(result.metadata.last_updated) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <!-- Load more hidden until pagination is implemented -->
            <div v-if="false" class="text-center py-4">
              <Button variant="outline" @click="loadMoreResults">Load More Results</Button>
            </div>
          </div>
        </template>
      </div>

      <!-- Cross-Dashboard Navigation Panel -->
      <div v-if="navigationSuggestions?.related_dashboards?.length" class="space-y-4">
        <SectionHeader variant="caption" title="Explore Related Dashboards" />
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="dashboard in navigationSuggestions.related_dashboards"
            :key="dashboard.id"
            role="button"
            tabindex="0"
            class="rounded-lg border border-outline-gray-1 bg-surface-white p-4 hover:bg-surface-gray-1 cursor-pointer transition-all duration-150 motion-reduce:transition-none"
            @click="navigateToDashboard(dashboard.url, dashboard.id)"
            @keydown.enter="navigateToDashboard(dashboard.url, dashboard.id)"
          >
            <div class="space-y-3">
              <div class="flex items-center gap-2">
                <component :is="getDashboardIcon(dashboard.id)" class="w-5 h-5 text-ink-gray-6" aria-hidden="true" />
                <span class="text-sm font-medium text-ink-gray-9">{{ dashboard.name }}</span>
              </div>
              <div class="space-y-1">
                <div
                  class="w-full h-1.5 bg-surface-gray-2 rounded-full overflow-hidden"
                  role="img"
                  :aria-label="`${dashboard.name}: ${Math.round(dashboard.relevance * 100)}% relevant`"
                >
                  <div
                    class="h-full bg-surface-gray-4 transition-all duration-300 motion-reduce:transition-none"
                    :style="{ width: `${dashboard.relevance * 100}%` }"
                  ></div>
                </div>
                <span class="text-xs text-ink-gray-6">{{ Math.round(dashboard.relevance * 100) }}% relevant</span>
              </div>
            </div>
          </div>
        </div>
      </div>

    </div>

    <!-- Search History Sidebar (fixed overlay) -->
    <div
      v-show="showSearchHistory"
      class="fixed right-0 top-0 h-full w-80 bg-surface-white shadow-lg z-50 p-4 overflow-y-auto sm:w-80 w-full"
    >
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
        <div class="flex items-center justify-between mb-4">
          <p class="flex items-center gap-2 text-base font-semibold text-ink-gray-9">
            <Clock class="w-4 h-4" aria-hidden="true" />
            Search History
          </p>
          <Button variant="ghost" size="sm" :icon="X" label="Close search history" @click="showSearchHistory = false" />
        </div>
        <div class="space-y-2">
          <div
            v-for="item in searchHistory"
            :key="item.timestamp"
            role="button"
            tabindex="0"
            class="p-3 bg-surface-gray-1 rounded-lg cursor-pointer hover:bg-surface-gray-2 transition-colors duration-150 motion-reduce:transition-none"
            @click="searchQuery = item.query; performSearch()"
            @keydown.enter="searchQuery = item.query; performSearch()"
          >
            <div class="text-sm font-medium text-ink-gray-9">{{ item.query }}</div>
            <div class="flex items-center justify-between text-xs text-ink-gray-6 mt-1">
              <span>{{ item.results_count }} results</span>
              <span>{{ formatDateTime(item.timestamp) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Search Help Modal -->
    <Dialog v-model="showSearchHelp" :options="{ title: 'Search Help' }">
      <template #body-content>
        <div class="space-y-6">
          <div v-if="searchHelpContent" class="space-y-6">
            <div class="space-y-3">
              <p class="text-sm font-semibold text-ink-gray-9">What I Can Do</p>
              <ul class="space-y-2 text-sm text-ink-gray-6 list-disc list-inside">
                <li v-for="capability in searchHelpContent.capabilities" :key="capability">{{ capability }}</li>
              </ul>
            </div>
            <div class="space-y-3">
              <p class="text-sm font-semibold text-ink-gray-9">Sample Queries</p>
              <div class="flex flex-wrap gap-2">
                <Button
                  v-for="query in searchHelpContent.sample_queries"
                  :key="query"
                  variant="ghost"
                  size="sm"
                  @click="searchQuery = query; showSearchHelp = false; performSearch()"
                >{{ query }}</Button>
              </div>
            </div>
            <div class="space-y-3">
              <p class="text-sm font-semibold text-ink-gray-9">Search Tips</p>
              <ul class="space-y-2 text-sm text-ink-gray-6 list-disc list-inside">
                <li v-for="tip in searchHelpContent.tips" :key="tip">{{ tip }}</li>
              </ul>
            </div>
          </div>
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {
  Search,
  X,
  Filter,
  Clock,
  HelpCircle,
  Download,
  Database,
  Tag,
  Zap,
  Bot,
  SearchX,
  ArrowRight,
  Star,
  Folder,
  BarChart3,
  TrendingUp,
  PieChart,
  Users,
  DollarSign,
  Factory,
  Heart,
  Leaf,
  Building,
  AlertCircle,
  Lightbulb,
  FileText
} from 'lucide-vue-next'
import { Button, Badge, Dialog, Select, Tabs } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { DASHBOARD_ICONS, SEARCH_DASHBOARD_OPTIONS } from '../helpers/dashboards'
import { formatDateTime } from '../utils/format'
import SkeletonBlock from './components/SkeletonBlock.vue'
import SectionHeader from './components/SectionHeader.vue'

const router = useRouter()

// Component state
const searchQuery = ref('')
const lastSearchQuery = ref('')
const searchFocused = ref(false)
const isSearching = ref(false)
const hasSearched = ref(false)
const searchError = ref('')
const showSuggestions = ref(false)
const showAdvancedFilters = ref(false)
const showSearchHistory = ref(false)
const showSearchHelp = ref(false)
const activeSuggestionIndex = ref(-1)

// Search data
const searchResults = ref(null)
const suggestions = ref([])
const searchHistory = ref([])
const agentResponse = ref('')
const navigationRecommendations = ref(null)
const navigationSuggestions = ref(null)
const searchHelpContent = ref(null)

// Search filters
const searchFilters = ref({
  dashboard: '',
  time_period: '',
  category: '',
  priority: ''
})

// Configuration
//
// From `helpers/dashboards`. The previous hand-written list had eight entries
// for ten dashboards: Tax, Procurement, Inventory, Marketing and Risk were
// absent (unfilterable), while `budget`, `sales` and `customer` were ghosts left
// behind by two dashboard merges.
const availableDashboards = ref(SEARCH_DASHBOARD_OPTIONS)

/**
 * Search-result categories: display label and icon name per tab.
 *
 * Expressed as JSDoc, not a TS interface, because this component's
 * `<script setup>` has no `lang="ts"`. Converting the file surfaces 631
 * pre-existing type errors across its 1350 lines, which is its own task.
 *
 * @type {import('vue').Ref<Record<string, { label: string, icon: string }>>}
 */
const resultCategories = ref({
  metrics: { label: 'Key Metrics', icon: 'trending-up' },
  alerts: { label: 'Alerts & Issues', icon: 'alert-circle' },
  recommendations: { label: 'Recommendations', icon: 'lightbulb' },
  trends: { label: 'Trends & Analysis', icon: 'bar-chart' },
  summary: { label: 'Summaries', icon: 'file-text' },
  departmental: { label: 'Departmental Data', icon: 'building' }
})

// Result category tabs: 'all' + one per category key, in order.
const RESULT_VIEW_IDS = ['all', 'metrics', 'alerts', 'recommendations', 'trends', 'summary', 'departmental']
const activeResultViewIndex = ref(0)
const activeResultView = computed(() => RESULT_VIEW_IDS[activeResultViewIndex.value] ?? 'all')
const resultTabItems = computed(() => [
  { label: 'All Results' },
  ...Object.values(resultCategories.value).map((c) => ({ label: c.label })),
])

// Filter select options
const dashboardOptions = computed(() => [
  { value: '', label: 'All Dashboards' },
  ...availableDashboards.value.map(d => ({ value: d.id, label: d.name })),
])
const timePeriodOptions = [
  { value: '', label: 'All Time' },
  { value: 'today', label: 'Today' },
  { value: 'this_week', label: 'This Week' },
  { value: 'this_month', label: 'This Month' },
  { value: 'this_quarter', label: 'This Quarter' },
  { value: 'this_year', label: 'This Year' },
]
const categoryOptions = [
  { value: '', label: 'All Categories' },
  { value: 'metrics', label: 'Key Metrics' },
  { value: 'alerts', label: 'Alerts & Issues' },
  { value: 'recommendations', label: 'Recommendations' },
  { value: 'trends', label: 'Trends & Analysis' },
  { value: 'summary', label: 'Summaries' },
  { value: 'departmental', label: 'Departmental Data' },
]
const priorityOptions = [
  { value: '', label: 'All Priorities' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
]

// Debounce timer for suggestions
let suggestionTimer = null

// Computed properties
const filteredResults = computed(() => {
  if (!searchResults.value?.results?.top_results) return []
  
  if (activeResultView.value === 'all') {
    return searchResults.value.results.top_results
  }
  
  return searchResults.value.results.by_category?.[activeResultView.value] || []
})

const hasMoreResults = computed(() => {
  const currentResults = filteredResults.value?.length || 0
  const totalResults = searchResults.value?.total_results || 0
  return currentResults < totalResults && currentResults >= 20
})

// Methods
const handleSearchInput = () => {
  clearTimeout(suggestionTimer)
  
  if (searchQuery.value.length >= 2) {
    suggestionTimer = setTimeout(() => {
      fetchSuggestions()
    }, 300)
  } else {
    clearSuggestions()
  }
}

const handleSearchBlur = () => {
  // Delay hiding suggestions to allow clicks
  setTimeout(() => {
    searchFocused.value = false
    showSuggestions.value = false
  }, 150)
}

const clearSearch = () => {
  searchQuery.value = ''
  clearSuggestions()
}

const clearSuggestions = () => {
  showSuggestions.value = false
  suggestions.value = []
  activeSuggestionIndex.value = -1
}

const navigateSuggestions = (direction) => {
  if (!showSuggestions.value || suggestions.value.length === 0) return
  
  activeSuggestionIndex.value += direction
  
  if (activeSuggestionIndex.value < 0) {
    activeSuggestionIndex.value = suggestions.value.length - 1
  } else if (activeSuggestionIndex.value >= suggestions.value.length) {
    activeSuggestionIndex.value = 0
  }
}

const selectSuggestion = (suggestion) => {
  searchQuery.value = suggestion.text
  clearSuggestions()
  performSearch()
}

const fetchSuggestions = async () => {
  try {
    const result = await apiCall('insights.api.ml.get_search_suggestions', {
      partial_query: searchQuery.value,
      context: JSON.stringify({
        dashboard: 'cross_dashboard_search'
      })
    })

    suggestions.value = result
    showSuggestions.value = true
  } catch (error) {
    console.error('Error fetching suggestions:', error)
  }
}

const performSearch = async () => {
  if (!searchQuery.value.trim()) return

  isSearching.value = true
  hasSearched.value = true
  searchError.value = ''
  searchResults.value = null
  lastSearchQuery.value = searchQuery.value
  clearSuggestions()

  try {
    const response = await apiCall('insights.api.ml.perform_cross_dashboard_search', {
      query: searchQuery.value,
      filters: searchFilters.value,
      context: {
        current_dashboard: 'cross_dashboard_search',
        user_preferences: {}
      }
    })

    // perform_cross_dashboard_search puts total_results/summary at the
    // response top level (see api/ml/search.py docstring), not inside
    // search_results -- merge them in so the template's
    // searchResults.total_results / searchResults.summary reads (results
    // count badge, summary card, and the total_results === 0 "no results"
    // branch) see the real numbers instead of always-undefined.
    searchResults.value = {
      ...response.search_results,
      total_results: response.total_results,
      summary: response.summary,
    }
    agentResponse.value = response.agent_response || ''
    navigationSuggestions.value = response.search_results?.navigation
    navigationRecommendations.value = response.navigation_recommendations
  } catch (err) {
    searchError.value = (err instanceof Error ? err.message : null) || 'Search failed. Please try again.'
  } finally {
    isSearching.value = false
  }
}

const toggleAdvancedFilters = () => {
  showAdvancedFilters.value = !showAdvancedFilters.value
}

const clearFilters = () => {
  searchFilters.value = {
    dashboard: '',
    time_period: '',
    category: '',
    priority: ''
  }
}

const applyFilters = () => {
  if (hasSearched.value) {
    performSearch()
  }
}

const navigateToResult = (result) => {
  if (result.navigation_url) {
    router.push(result.navigation_url)
  }
}

const navigateToDashboard = (url, dashboardId = '') => {
  router.push(url + (searchQuery.value ? `?search=${encodeURIComponent(searchQuery.value)}` : ''))
}

const saveToFavorites = async (result) => {
  try {
    await apiCall('insights.api.ml.save_search_favorite', {
      query: lastSearchQuery.value,
      title: result.title
    })
    // Show success message
  } catch (error) {
    console.error('Error saving favorite:', error)
  }
}

const exportSearchResults = () => {
  // Implement export functionality
  const data = {
    query: lastSearchQuery.value,
    results: filteredResults.value,
    timestamp: new Date().toISOString()
  }
  
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `search-results-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}

const loadMoreResults = async () => {
  // Implement pagination
}

const loadSearchHistory = async () => {
  try {
    searchHistory.value = await apiCall('insights.api.ml.get_search_history')
  } catch (error) {
    console.error('Error loading search history:', error)
  }
}

const loadSearchHelp = async () => {
  try {
    const result = await apiCall('insights.api.ml.get_search_help')
    searchHelpContent.value = result.help_content
  } catch (error) {
    console.error('Error loading search help:', error)
  }
}

// Utility functions
const getSuggestionVariant = (type) => {
  const variants = {
    query_completion: 'solid',
    context_suggestion: 'outline',
    popular_search: 'subtle'
  }
  return variants[type] || 'outline'
}

const getSuggestionLabel = (type) => {
  const labels = {
    query_completion: 'Complete',
    context_suggestion: 'Suggested',
    popular_search: 'Popular'
  }
  return labels[type] || 'Suggestion'
}

const getCategoryCount = (categoryId) => {
  return searchResults.value?.results?.by_category?.[categoryId]?.length || 0
}

const getCategoryIcon = (iconName) => {
  const icons = {
    'trending-up': TrendingUp,
    'alert-circle': AlertCircle,
    'lightbulb': Lightbulb,
    'bar-chart': BarChart3,
    'file-text': FileText,
    'building': Building
  }
  return icons[iconName] || TrendingUp
}

const getCategoryVariant = (category) => {
  const variants = {
    alerts: 'solid',
    recommendations: 'solid',
    metrics: 'outline',
    trends: 'outline',
    summary: 'subtle',
    departmental: 'subtle'
  }
  return variants[category] || 'outline'
}

const getCategoryLabel = (category) => {
  return resultCategories.value[category]?.label || category
}

const getDomainLabel = (domainId) => {
  const domain = availableDashboards.value.find(d => d.id === domainId)
  return domain?.name || domainId
}

const getDashboardIcon = (dashboardId) => DASHBOARD_ICONS[dashboardId] || BarChart3

// Badge theme helpers — returns a valid frappe-ui Badge `theme` value.
const getSuggestionTheme = (type) => {
  const themes = { query_completion: 'blue', context_suggestion: 'gray', popular_search: 'green' }
  return themes[type] || 'gray'
}

const getCategoryTheme = (category) => {
  const themes = { alerts: 'red', recommendations: 'blue', metrics: 'gray', trends: 'gray', summary: 'gray', departmental: 'gray' }
  return themes[category] || 'gray'
}


const searchInput = ref(null)

// Lifecycle
onMounted(() => {
  loadSearchHistory()
  loadSearchHelp()
  
  // Focus search input
  nextTick(() => {
    if (searchInput.value) {
      searchInput.value.focus()
    }
  })
})

onUnmounted(() => { clearTimeout(suggestionTimer) })

// Watch for route changes to auto-search
watch(() => router.currentRoute.value.query.search, (newSearch) => {
  if (newSearch && newSearch !== searchQuery.value) {
    searchQuery.value = newSearch
    performSearch()
  }
})
</script>