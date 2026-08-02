<template>
  <div class="flex items-center gap-3">
    <!-- Company Selector -->
    <div class="flex items-center gap-2">
      <label class="text-sm font-medium text-ink-gray-6">Company:</label>
      <select
        v-model="selectedCompany"
        @change="onCompanyChange"
        class="px-3 py-1.5 text-sm border border-outline-gray-2 rounded-lg bg-surface-white focus:ring-2 focus:ring-accent focus:border-accent"
      >
        <option v-for="company in companies" :key="company.name" :value="company.name">
          {{ company.name }}
        </option>
      </select>
    </div>

    <!-- From Period Selector -->
    <div class="flex items-center gap-2">
      <label class="text-sm font-medium text-ink-gray-6">From:</label>
      <select
        v-model="fromFiscalYear"
        @change="onPeriodChange"
        class="px-3 py-1.5 text-sm border border-outline-gray-2 rounded-lg bg-surface-white focus:ring-2 focus:ring-accent focus:border-accent"
      >
        <option v-for="fy in fiscalYears" :key="fy.name" :value="fy.name">
          {{ fy.name }}
        </option>
      </select>
    </div>

    <!-- To Period Selector -->
    <div class="flex items-center gap-2">
      <label class="text-sm font-medium text-ink-gray-6">To:</label>
      <select
        v-model="toFiscalYear"
        @change="onPeriodChange"
        class="px-3 py-1.5 text-sm border border-outline-gray-2 rounded-lg bg-surface-white focus:ring-2 focus:ring-accent focus:border-accent"
      >
        <option v-for="fy in fiscalYears" :key="fy.name" :value="fy.name">
          {{ fy.name }}
        </option>
      </select>
    </div>

    <!-- Loading indicator -->
    <Loader2 v-if="isLoading" class="w-4 h-4 text-ink-gray-3 animate-spin motion-reduce:animate-none" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { call } from 'frappe-ui'
import { Loader2 } from 'lucide-vue-next'

// Props
const props = defineProps<{
  dashboardName: string
  defaultCompany?: string
}>()

// Emits
const emit = defineEmits<{
  (e: 'update:filters', filters: {
    company: string
    start_date: string
    end_date: string
    from_fiscal_year: string
    to_fiscal_year: string
  }): void
}>()

// State
const isLoading = ref(false)
const companies = ref<Array<{ name: string }>>([])
const fiscalYears = ref<Array<{
  name: string
  year_start_date: string
  year_end_date: string
}>>([])
const selectedCompany = ref('')
const fromFiscalYear = ref('')
const toFiscalYear = ref('')

// LocalStorage key
const storageKey = computed(() => `insights_fiscal_filter_${props.dashboardName}`)

// Load saved preferences from localStorage
function loadSavedPreferences() {
  try {
    const saved = localStorage.getItem(storageKey.value)
    if (saved) {
      const parsed = JSON.parse(saved)
      return parsed
    }
  } catch (e) {
    console.error('Failed to load saved preferences:', e)
  }
  return null
}

// Save preferences to localStorage
function savePreferences() {
  try {
    const prefs = {
      company: selectedCompany.value,
      fromFiscalYear: fromFiscalYear.value,
      toFiscalYear: toFiscalYear.value
    }
    localStorage.setItem(storageKey.value, JSON.stringify(prefs))
  } catch (e) {
    console.error('Failed to save preferences:', e)
  }
}

// Load companies
async function loadCompanies() {
  try {
    const response = await call('insights.api.ml.get_companies')
    if (response?.status === 'success' && response.companies) {
      companies.value = response.companies
      
      // Set default company
      const saved = loadSavedPreferences()
      if (saved?.company && companies.value.find(c => c.name === saved.company)) {
        selectedCompany.value = saved.company
      } else if (props.defaultCompany && companies.value.find(c => c.name === props.defaultCompany)) {
        selectedCompany.value = props.defaultCompany
      } else if (response.default_company) {
        selectedCompany.value = response.default_company
      } else if (companies.value.length > 0) {
        selectedCompany.value = companies.value[0].name
      }
    }
  } catch (e) {
    console.error('Failed to load companies:', e)
  }
}

// Load fiscal years for selected company
async function loadFiscalYears() {
  if (!selectedCompany.value) return
  
  isLoading.value = true
  try {
    const response = await call('insights.api.ml.get_fiscal_years', {
      company: selectedCompany.value
    })
    
    if (response?.status === 'success' && response.fiscal_years) {
      fiscalYears.value = response.fiscal_years
      
      // Set default fiscal years
      const saved = loadSavedPreferences()
      const currentFY = response.current_fiscal_year
      
      if (saved?.fromFiscalYear && fiscalYears.value.find(fy => fy.name === saved.fromFiscalYear)) {
        fromFiscalYear.value = saved.fromFiscalYear
      } else if (currentFY) {
        fromFiscalYear.value = currentFY
      } else if (fiscalYears.value.length > 0) {
        fromFiscalYear.value = fiscalYears.value[0].name
      }
      
      if (saved?.toFiscalYear && fiscalYears.value.find(fy => fy.name === saved.toFiscalYear)) {
        toFiscalYear.value = saved.toFiscalYear
      } else if (currentFY) {
        toFiscalYear.value = currentFY
      } else if (fiscalYears.value.length > 0) {
        toFiscalYear.value = fiscalYears.value[0].name
      }
      
      // Emit initial values
      emitFilters()
    }
  } catch (e) {
    console.error('Failed to load fiscal years:', e)
  } finally {
    isLoading.value = false
  }
}

// Get date range from selected fiscal years
function getDateRange(): { start_date: string; end_date: string } {
  const fromFY = fiscalYears.value.find(fy => fy.name === fromFiscalYear.value)
  const toFY = fiscalYears.value.find(fy => fy.name === toFiscalYear.value)
  
  return {
    start_date: fromFY?.year_start_date || '',
    end_date: toFY?.year_end_date || ''
  }
}

// Emit filter values
function emitFilters() {
  const { start_date, end_date } = getDateRange()
  emit('update:filters', {
    company: selectedCompany.value,
    start_date,
    end_date,
    from_fiscal_year: fromFiscalYear.value,
    to_fiscal_year: toFiscalYear.value
  })
  savePreferences()
}

// Event handlers
function onCompanyChange() {
  loadFiscalYears()
}

function onPeriodChange() {
  // Ensure from is not after to
  const fromIndex = fiscalYears.value.findIndex(fy => fy.name === fromFiscalYear.value)
  const toIndex = fiscalYears.value.findIndex(fy => fy.name === toFiscalYear.value)
  
  if (fromIndex < toIndex) {
    // From is after To (list is sorted descending), swap them
    const temp = fromFiscalYear.value
    fromFiscalYear.value = toFiscalYear.value
    toFiscalYear.value = temp
  }
  
  emitFilters()
}

// Initialize on mount
onMounted(async () => {
  await loadCompanies()
  await loadFiscalYears()
})

// Watch for company changes
watch(selectedCompany, () => {
  loadFiscalYears()
})
</script>
