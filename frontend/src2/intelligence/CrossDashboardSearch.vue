<template>
  <div class="cross-dashboard-search">
    <!-- Search Header -->
    <div class="search-header">
      <div class="search-title">
        <Search class="title-icon" />
        <h2>Global Intelligence Search</h2>
      </div>
      <p class="search-subtitle">
        Search across all your business intelligence dashboards and data
      </p>
    </div>

    <!-- Main Search Interface -->
    <div class="search-interface">
      <!-- Search Input with Suggestions -->
      <div class="search-input-container">
        <div class="search-input-wrapper" :class="{ 'focused': searchFocused }">
          <Search class="search-icon" />
          <input
            ref="searchInput"
            v-model="searchQuery"
            type="text"
            placeholder="Search across all dashboards... (e.g., 'budget variance alerts', 'employee metrics', 'sales trends')"
            class="search-input"
            @focus="searchFocused = true"
            @blur="handleSearchBlur"
            @input="handleSearchInput"
            @keydown.enter="performSearch"
            @keydown.down="navigateSuggestions(1)"
            @keydown.up="navigateSuggestions(-1)"
            @keydown.escape="clearSuggestions"
          />
          <div class="search-actions">
            <Button
              v-if="searchQuery"
              variant="ghost"
              size="sm"
              @click="clearSearch"
            >
              <X class="w-4 h-4" />
            </Button>
            <Button
              variant="solid"
              size="sm"
              @click="performSearch"
              :loading="isSearching"
            >
              Search
            </Button>
          </div>
        </div>

        <!-- Search Suggestions Dropdown -->
        <div
          v-show="showSuggestions && suggestions.length > 0"
          class="suggestions-dropdown"
        >
          <div
            v-for="(suggestion, index) in suggestions"
            :key="index"
            :class="[
              'suggestion-item', 
              { 'active': activeSuggestionIndex === index }
            ]"
            @click="selectSuggestion(suggestion)"
            @mouseenter="activeSuggestionIndex = index"
          >
            <div class="suggestion-content">
              <div class="suggestion-text">{{ suggestion.text }}</div>
              <div class="suggestion-meta">
                <Badge :variant="getSuggestionVariant(suggestion.type)" size="sm">
                  {{ getSuggestionLabel(suggestion.type) }}
                </Badge>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Search Filters -->
      <div v-show="showAdvancedFilters" class="search-filters">
        <div class="filters-grid">
          <!-- Dashboard Filter -->
          <div class="filter-group">
            <label class="filter-label">Dashboard</label>
            <select v-model="searchFilters.dashboard" class="filter-select">
              <option value="">All Dashboards</option>
              <option
                v-for="dashboard in availableDashboards"
                :key="dashboard.id"
                :value="dashboard.id"
              >
                {{ dashboard.name }}
              </option>
            </select>
          </div>

          <!-- Time Period Filter -->
          <div class="filter-group">
            <label class="filter-label">Time Period</label>
            <select v-model="searchFilters.time_period" class="filter-select">
              <option value="">All Time</option>
              <option value="today">Today</option>
              <option value="this_week">This Week</option>
              <option value="this_month">This Month</option>
              <option value="this_quarter">This Quarter</option>
              <option value="this_year">This Year</option>
            </select>
          </div>

          <!-- Category Filter -->
          <div class="filter-group">
            <label class="filter-label">Category</label>
            <select v-model="searchFilters.category" class="filter-select">
              <option value="">All Categories</option>
              <option value="metrics">Key Metrics</option>
              <option value="alerts">Alerts & Issues</option>
              <option value="recommendations">Recommendations</option>
              <option value="trends">Trends & Analysis</option>
              <option value="summary">Summaries</option>
              <option value="departmental">Departmental Data</option>
            </select>
          </div>

          <!-- Priority Filter -->
          <div class="filter-group">
            <label class="filter-label">Priority</label>
            <select v-model="searchFilters.priority" class="filter-select">
              <option value="">All Priorities</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>

        <div class="filter-actions">
          <Button variant="ghost" size="sm" @click="clearFilters">
            Clear Filters
          </Button>
          <Button variant="solid" size="sm" @click="applyFilters">
            Apply Filters
          </Button>
        </div>
      </div>

      <!-- Quick Filters Toggle -->
      <div class="search-controls">
        <Button
          variant="ghost"
          size="sm"
          @click="toggleAdvancedFilters"
        >
          <Filter class="w-4 h-4 mr-1" />
          {{ showAdvancedFilters ? 'Hide' : 'Show' }} Filters
        </Button>

        <Button
          variant="ghost"
          size="sm"
          @click="showSearchHistory = !showSearchHistory"
        >
          <Clock class="w-4 h-4 mr-1" />
          Search History
        </Button>

        <Button
          variant="ghost"
          size="sm"
          @click="showSearchHelp = true"
        >
          <HelpCircle class="w-4 h-4 mr-1" />
          Help
        </Button>
      </div>
    </div>

    <!-- Search Results -->
    <div v-if="hasSearched" class="search-results">
      <!-- Results Header -->
      <div class="results-header">
        <div class="results-info">
          <h3 class="results-title">
            Search Results
            <span v-if="searchResults?.total_results" class="results-count">
              ({{ searchResults.total_results }} found)
            </span>
          </h3>
          <p v-if="lastSearchQuery" class="results-query">
            Results for: "{{ lastSearchQuery }}"
          </p>
        </div>

        <div class="results-controls">
          <Button
            variant="ghost"
            size="sm"
            @click="exportSearchResults"
          >
            <Download class="w-4 h-4 mr-1" />
            Export
          </Button>
        </div>
      </div>

      <!-- Search Summary -->
      <div v-if="searchResults?.summary" class="search-summary">
        <Card class="summary-card">
          <div class="summary-content">
            <div class="summary-stats">
              <div class="stat-item">
                <Database class="stat-icon" />
                <div class="stat-details">
                  <span class="stat-value">{{ searchResults.summary.domains_searched }}</span>
                  <span class="stat-label">Dashboards Searched</span>
                </div>
              </div>
              
              <div class="stat-item">
                <Tag class="stat-icon" />
                <div class="stat-details">
                  <span class="stat-value">{{ searchResults.summary.categories_found }}</span>
                  <span class="stat-label">Categories Found</span>
                </div>
              </div>
              
              <div class="stat-item">
                <Zap class="stat-icon" />
                <div class="stat-details">
                  <span class="stat-value">{{ searchResults.summary.search_quality }}</span>
                  <span class="stat-label">Search Quality</span>
                </div>
              </div>
            </div>

            <!-- Agent Response -->
            <div v-if="agentResponse" class="agent-response">
              <div class="agent-header">
                <Bot class="w-4 h-4" />
                <span class="agent-label">Search Assistant</span>
              </div>
              <p class="agent-message">{{ agentResponse }}</p>
            </div>
          </div>
        </Card>
      </div>

      <!-- No Results -->
      <div v-if="searchResults?.total_results === 0" class="no-results">
        <div class="no-results-content">
          <SearchX class="no-results-icon" />
          <h3 class="no-results-title">No Results Found</h3>
          <p class="no-results-message">
            We couldn't find any results matching your search criteria.
          </p>
          
          <!-- Search Suggestions -->
          <div v-if="searchResults?.suggestions?.length" class="search-suggestions">
            <h4 class="suggestions-title">Try these suggestions:</h4>
            <div class="suggestions-list">
              <Button
                v-for="suggestion in searchResults.suggestions"
                :key="suggestion"
                variant="ghost"
                size="sm"
                @click="searchQuery = suggestion; performSearch()"
              >
                {{ suggestion }}
              </Button>
            </div>
          </div>

          <!-- Navigation Recommendations -->
          <div v-if="navigationRecommendations" class="navigation-recommendations">
            <h4 class="recommendations-title">{{ navigationRecommendations.message }}</h4>
            <div class="recommendations-list">
              <Card
                v-for="rec in navigationRecommendations.suggestions"
                :key="rec.dashboard_name"
                class="recommendation-card"
                @click="navigateToDashboard(rec.url)"
              >
                <div class="recommendation-content">
                  <ArrowRight class="recommendation-icon" />
                  <div class="recommendation-details">
                    <span class="recommendation-name">{{ rec.dashboard_name }}</span>
                    <span class="recommendation-reason">{{ rec.reason }}</span>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        </div>
      </div>

      <!-- Results Categories View -->
      <div v-else class="results-content">
        <!-- Category Tabs -->
        <div class="category-tabs">
          <Button
            :variant="activeResultView === 'all' ? 'solid' : 'ghost'"
            size="sm"
            @click="activeResultView = 'all'"
          >
            All Results
          </Button>
          
          <Button
            v-for="(category, categoryId) in resultCategories"
            :key="categoryId"
            :variant="activeResultView === categoryId ? 'solid' : 'ghost'"
            size="sm"
            @click="activeResultView = categoryId"
          >
            <component :is="getCategoryIcon(category.icon)" class="w-4 h-4 mr-1" />
            {{ category.label }}
            <Badge variant="secondary" size="sm" class="ml-1">
              {{ getCategoryCount(categoryId) }}
            </Badge>
          </Button>
        </div>

        <!-- Results List -->
        <div class="results-list">
          <div
            v-for="result in filteredResults"
            :key="result.id"
            class="result-item"
            @click="navigateToResult(result)"
          >
            <Card class="result-card">
              <div class="result-content">
                <!-- Result Header -->
                <div class="result-header">
                  <div class="result-title-section">
                    <h4 class="result-title">{{ result.title }}</h4>
                    <div class="result-meta">
                      <Badge :variant="getCategoryVariant(result.category)" size="sm">
                        {{ getCategoryLabel(result.category) }}
                      </Badge>
                      <Badge variant="outline" size="sm">
                        {{ getDomainLabel(result.metadata?.domain || '') }}
                      </Badge>
                      <span class="result-score">
                        {{ Math.round((result.relevance_score || 0) * 100) }}% match
                      </span>
                    </div>
                  </div>
                  
                  <div class="result-actions">
                    <Button variant="ghost" size="sm" @click.stop="saveToFavorites(result)">
                      <Star class="w-4 h-4" />
                    </Button>
                    <Button variant="ghost" size="sm" @click="navigateToResult(result)">
                      <ArrowRight class="w-4 h-4" />
                    </Button>
                  </div>
                </div>

                <!-- Result Preview -->
                <div class="result-preview">
                  <p class="preview-text">{{ result.preview }}</p>
                </div>

                <!-- Result Footer -->
                <div class="result-footer">
                  <div class="result-path">
                    <Folder class="w-3 h-3" />
                    <span class="path-text">{{ result.source_path }}</span>
                  </div>
                  
                  <div v-if="result.metadata?.last_updated" class="result-timestamp">
                    <Clock class="w-3 h-3" />
                    <span class="timestamp-text">
                      Updated {{ formatDate(result.metadata.last_updated) }}
                    </span>
                  </div>
                </div>
              </div>
            </Card>
          </div>
        </div>

        <!-- Load More Button -->
        <div v-if="hasMoreResults" class="load-more-section">
          <Button variant="outline" @click="loadMoreResults">
            Load More Results
          </Button>
        </div>
      </div>
    </div>

    <!-- Cross-Dashboard Navigation Panel -->
    <div v-if="navigationSuggestions?.related_dashboards?.length" class="navigation-panel">
      <h3 class="navigation-title">Explore Related Dashboards</h3>
      <div class="navigation-grid">
        <Card
          v-for="dashboard in navigationSuggestions.related_dashboards"
          :key="dashboard.id"
          class="dashboard-card"
          @click="navigateToDashboard(dashboard.url, dashboard.id)"
        >
          <div class="dashboard-content">
            <div class="dashboard-header">
              <component :is="getDashboardIcon(dashboard.id)" class="dashboard-icon" />
              <span class="dashboard-name">{{ dashboard.name }}</span>
            </div>
            <div class="dashboard-relevance">
              <div class="relevance-bar">
                <div 
                  class="relevance-fill" 
                  :style="{ width: `${dashboard.relevance * 100}%` }"
                ></div>
              </div>
              <span class="relevance-text">
                {{ Math.round(dashboard.relevance * 100) }}% relevant
              </span>
            </div>
          </div>
        </Card>
      </div>
    </div>

    <!-- Search History Sidebar -->
    <div v-show="showSearchHistory" class="search-history-sidebar">
      <Card class="history-card">
        <div class="history-header">
          <h3 class="history-title">
            <Clock class="w-4 h-4" />
            Search History
          </h3>
          <Button variant="ghost" size="sm" @click="showSearchHistory = false">
            <X class="w-4 h-4" />
          </Button>
        </div>
        
        <div class="history-content">
          <div
            v-for="item in searchHistory"
            :key="item.timestamp"
            class="history-item"
            @click="searchQuery = item.query; performSearch()"
          >
            <div class="history-query">{{ item.query }}</div>
            <div class="history-meta">
              <span class="history-results">{{ item.results_count }} results</span>
              <span class="history-time">{{ formatDate(item.timestamp) }}</span>
            </div>
          </div>
        </div>
      </Card>
    </div>

    <!-- Search Help Modal -->
    <Dialog v-model="showSearchHelp" :options="{ title: 'Search Help' }">
      <template #body-content>
      <div class="help-content">
        <div v-if="searchHelpContent" class="help-sections">
          <div class="help-section">
            <h4 class="help-section-title">What I Can Do</h4>
            <ul class="help-list">
              <li v-for="capability in searchHelpContent.capabilities" :key="capability">
                {{ capability }}
              </li>
            </ul>
          </div>

          <div class="help-section">
            <h4 class="help-section-title">Sample Queries</h4>
            <div class="sample-queries">
              <Button
                v-for="query in searchHelpContent.sample_queries"
                :key="query"
                variant="ghost"
                size="sm"
                @click="searchQuery = query; showSearchHelp = false; performSearch()"
              >
                {{ query }}
              </Button>
            </div>
          </div>

          <div class="help-section">
            <h4 class="help-section-title">Search Tips</h4>
            <ul class="help-list">
              <li v-for="tip in searchHelpContent.tips" :key="tip">
                {{ tip }}
              </li>
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
  Heart,
  Leaf,
  Building,
  AlertCircle,
  Lightbulb,
  FileText
} from 'lucide-vue-next'
import { Button, Card, Badge, Dialog } from 'frappe-ui'
import { apiCall } from '../helpers/api'

const router = useRouter()

// Component state
const searchQuery = ref('')
const lastSearchQuery = ref('')
const searchFocused = ref(false)
const isSearching = ref(false)
const hasSearched = ref(false)
const showSuggestions = ref(false)
const showAdvancedFilters = ref(false)
const showSearchHistory = ref(false)
const showSearchHelp = ref(false)
const activeSuggestionIndex = ref(-1)
const activeResultView = ref('all')

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
const availableDashboards = ref([
  { id: 'executive', name: 'Executive Intelligence' },
  { id: 'financial', name: 'Financial Intelligence' },
  { id: 'budget', name: 'Budget Variance Intelligence' },
  { id: 'hr', name: 'HR Intelligence' },
  { id: 'sales', name: 'Sales Intelligence' },
  { id: 'customer', name: 'Customer Intelligence' },
  { id: 'esg', name: 'ESG Intelligence' }
])

const resultCategories = ref({
  metrics: { label: 'Key Metrics', icon: 'trending-up' },
  alerts: { label: 'Alerts & Issues', icon: 'alert-circle' },
  recommendations: { label: 'Recommendations', icon: 'lightbulb' },
  trends: { label: 'Trends & Analysis', icon: 'bar-chart' },
  summary: { label: 'Summaries', icon: 'file-text' },
  departmental: { label: 'Departmental Data', icon: 'building' }
})

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
  lastSearchQuery.value = searchQuery.value
  clearSuggestions()
  
  try {
    // Call search API
    const response = await apiCall('insights.api.ml.perform_cross_dashboard_search', {
      query: searchQuery.value,
      filters: searchFilters.value,
      context: {
        current_dashboard: 'cross_dashboard_search',
        user_preferences: {}
      }
    })

    searchResults.value = response.search_results
    agentResponse.value = response.agent_response || ''
    navigationSuggestions.value = response.search_results?.navigation
    navigationRecommendations.value = response.navigation_recommendations
  } catch (error) {
    console.error('Error performing search:', error)
    // Handle error
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

const getDashboardIcon = (dashboardId) => {
  const icons = {
    executive: BarChart3,
    financial: DollarSign,
    budget: PieChart,
    hr: Users,
    sales: TrendingUp,
    customer: Heart,
    esg: Leaf
  }
  return icons[dashboardId] || BarChart3
}

const formatDate = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
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

// Watch for route changes to auto-search
watch(() => router.currentRoute.value.query.search, (newSearch) => {
  if (newSearch && newSearch !== searchQuery.value) {
    searchQuery.value = newSearch
    performSearch()
  }
})
</script>

<style scoped>
.cross-dashboard-search {
  @apply flex flex-col space-y-6 p-6 max-w-7xl mx-auto;
}

.search-header {
  @apply text-center space-y-2;
}

.search-title {
  @apply flex items-center justify-center space-x-2;
}

.title-icon {
  @apply w-6 h-6 text-blue-600;
}

.search-title h2 {
  @apply text-2xl font-semibold text-gray-900;
}

.search-subtitle {
  @apply text-gray-600 text-sm;
}

.search-interface {
  @apply space-y-4;
}

.search-input-container {
  @apply relative;
}

.search-input-wrapper {
  @apply relative flex items-center bg-white border border-gray-300 rounded-lg shadow-sm transition-all duration-200;
}

.search-input-wrapper.focused {
  @apply border-blue-500 ring-1 ring-blue-500 shadow-md;
}

.search-icon {
  @apply absolute left-3 w-5 h-5 text-gray-400;
}

.search-input {
  @apply flex-1 pl-10 pr-32 py-3 border-0 rounded-lg focus:outline-none text-gray-900 placeholder-gray-500;
}

.search-actions {
  @apply absolute right-2 flex items-center space-x-2;
}

.suggestions-dropdown {
  @apply absolute top-full mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-64 overflow-y-auto;
}

.suggestion-item {
  @apply px-4 py-3 hover:bg-gray-50 cursor-pointer transition-colors duration-150;
}

.suggestion-item.active {
  @apply bg-blue-50;
}

.suggestion-content {
  @apply flex items-center justify-between;
}

.suggestion-text {
  @apply text-gray-900 text-sm;
}

.suggestion-meta {
  @apply flex items-center space-x-2;
}

.search-filters {
  @apply bg-gray-50 rounded-lg p-4 space-y-4;
}

.filters-grid {
  @apply grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4;
}

.filter-group {
  @apply space-y-1;
}

.filter-label {
  @apply text-sm font-medium text-gray-700;
}

.filter-select {
  @apply w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500;
}

.filter-actions {
  @apply flex items-center justify-end space-x-2;
}

.search-controls {
  @apply flex items-center space-x-3;
}

.search-results {
  @apply space-y-6;
}

.results-header {
  @apply flex items-center justify-between;
}

.results-title {
  @apply text-xl font-semibold text-gray-900;
}

.results-count {
  @apply text-gray-500 text-base font-normal;
}

.results-query {
  @apply text-gray-600 text-sm;
}

.search-summary {
  @apply w-full;
}

.summary-card {
  @apply p-4;
}

.summary-content {
  @apply space-y-4;
}

.summary-stats {
  @apply flex items-center space-x-6;
}

.stat-item {
  @apply flex items-center space-x-2;
}

.stat-icon {
  @apply w-5 h-5 text-blue-600;
}

.stat-details {
  @apply flex flex-col;
}

.stat-value {
  @apply text-lg font-semibold text-gray-900;
}

.stat-label {
  @apply text-xs text-gray-500 uppercase tracking-wide;
}

.agent-response {
  @apply space-y-2;
}

.agent-header {
  @apply flex items-center space-x-2;
}

.agent-label {
  @apply text-sm font-medium text-blue-600;
}

.agent-message {
  @apply text-gray-700 text-sm leading-relaxed;
}

.no-results {
  @apply text-center py-12;
}

.no-results-content {
  @apply space-y-6;
}

.no-results-icon {
  @apply w-12 h-12 text-gray-400 mx-auto;
}

.no-results-title {
  @apply text-lg font-semibold text-gray-900;
}

.no-results-message {
  @apply text-gray-600;
}

.search-suggestions {
  @apply space-y-3;
}

.suggestions-title {
  @apply text-sm font-medium text-gray-700;
}

.suggestions-list {
  @apply flex flex-wrap gap-2;
}

.navigation-recommendations {
  @apply space-y-3;
}

.recommendations-title {
  @apply text-sm font-medium text-gray-700;
}

.recommendations-list {
  @apply space-y-2;
}

.recommendation-card {
  @apply p-3 hover:bg-gray-50 cursor-pointer transition-colors duration-150;
}

.recommendation-content {
  @apply flex items-center space-x-3;
}

.recommendation-icon {
  @apply w-4 h-4 text-blue-600;
}

.recommendation-details {
  @apply flex flex-col;
}

.recommendation-name {
  @apply text-sm font-medium text-gray-900;
}

.recommendation-reason {
  @apply text-xs text-gray-500;
}

.results-content {
  @apply space-y-4;
}

.category-tabs {
  @apply flex items-center space-x-2 overflow-x-auto pb-2;
}

.results-list {
  @apply space-y-3;
}

.result-item {
  @apply cursor-pointer;
}

.result-card {
  @apply p-4 hover:bg-gray-50 transition-all duration-150;
}

.result-content {
  @apply space-y-3;
}

.result-header {
  @apply flex items-start justify-between;
}

.result-title-section {
  @apply flex-1 space-y-2;
}

.result-title {
  @apply text-lg font-medium text-gray-900 leading-tight;
}

.result-meta {
  @apply flex items-center space-x-2 flex-wrap;
}

.result-score {
  @apply text-xs text-gray-500;
}

.result-actions {
  @apply flex items-center space-x-1 flex-shrink-0;
}

.result-preview {
  @apply mt-2;
}

.preview-text {
  @apply text-gray-600 text-sm leading-relaxed;
}

.result-footer {
  @apply flex items-center justify-between text-xs text-gray-500;
}

.result-path {
  @apply flex items-center space-x-1;
}

.path-text {
  @apply truncate max-w-xs;
}

.result-timestamp {
  @apply flex items-center space-x-1;
}

.load-more-section {
  @apply text-center py-4;
}

.navigation-panel {
  @apply space-y-4;
}

.navigation-title {
  @apply text-lg font-semibold text-gray-900;
}

.navigation-grid {
  @apply grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4;
}

.dashboard-card {
  @apply p-4 hover:bg-gray-50 cursor-pointer transition-all duration-150;
}

.dashboard-content {
  @apply space-y-3;
}

.dashboard-header {
  @apply flex items-center space-x-2;
}

.dashboard-icon {
  @apply w-5 h-5 text-blue-600;
}

.dashboard-name {
  @apply text-sm font-medium text-gray-900;
}

.dashboard-relevance {
  @apply space-y-1;
}

.relevance-bar {
  @apply w-full h-1.5 bg-gray-200 rounded-full overflow-hidden;
}

.relevance-fill {
  @apply h-full bg-blue-600 transition-all duration-300;
}

.relevance-text {
  @apply text-xs text-gray-500;
}

.search-history-sidebar {
  @apply fixed right-0 top-0 h-full w-80 bg-white shadow-lg z-50 p-4 overflow-y-auto;
}

.history-card {
  @apply p-4;
}

.history-header {
  @apply flex items-center justify-between mb-4;
}

.history-title {
  @apply flex items-center space-x-2 text-lg font-semibold text-gray-900;
}

.history-content {
  @apply space-y-2;
}

.history-item {
  @apply p-3 bg-gray-50 rounded-lg cursor-pointer hover:bg-gray-100 transition-colors duration-150;
}

.history-query {
  @apply text-sm font-medium text-gray-900;
}

.history-meta {
  @apply flex items-center justify-between text-xs text-gray-500 mt-1;
}

.help-content {
  @apply space-y-6;
}

.help-sections {
  @apply space-y-6;
}

.help-section {
  @apply space-y-3;
}

.help-section-title {
  @apply text-sm font-semibold text-gray-900;
}

.help-list {
  @apply space-y-2 text-sm text-gray-600;
}

.help-list li {
  @apply flex items-start space-x-2;
}

.help-list li::before {
  content: "•";
  @apply text-blue-600 font-bold flex-shrink-0;
}

.sample-queries {
  @apply flex flex-wrap gap-2;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .cross-dashboard-search {
    @apply p-4 space-y-4;
  }
  
  .search-input {
    @apply pr-20 text-sm;
  }
  
  .summary-stats {
    @apply flex-col space-x-0 space-y-4;
  }
  
  .category-tabs {
    @apply space-x-1;
  }
  
  .result-header {
    @apply flex-col space-y-2;
  }
  
  .result-actions {
    @apply self-end;
  }
  
  .navigation-grid {
    @apply grid-cols-1;
  }
  
  .search-history-sidebar {
    @apply w-full;
  }
}
</style>