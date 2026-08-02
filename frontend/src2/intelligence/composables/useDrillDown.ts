import { call } from 'frappe-ui'
import { ref, type Ref } from 'vue'
import { readFrappeError } from '../../helpers/api'

export interface DrillDownColumn {
  label: string
  fieldname: string
  fieldtype: 'Data' | 'Link' | 'Date' | 'Currency' | 'Int' | 'Float' | 'Percent'
  options?: string // DocType name — required when fieldtype === 'Link'
}

export interface DrillDownParams {
  metric: string
  /** Arbitrary context filters: period, company, department, supplier, and so on. */
  [key: string]: unknown
}

export interface DrillDownState {
  show: Ref<boolean>
  loading: Ref<boolean>
  error: Ref<string | null>
  isPermissionError: Ref<boolean>
  title: Ref<string>
  columns: Ref<DrillDownColumn[]>
  rows: Ref<Record<string, unknown>[]>
  total: Ref<number>
  page: Ref<number>
  readonly pageSize: number
  open: (endpoint: string, title: string, params: DrillDownParams) => void
  close: () => void
  retry: () => void   // re-fetches current endpoint+params+page after error
  nextPage: () => void
  prevPage: () => void
}

export function useDrillDown(): DrillDownState {
  const show = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const isPermissionError = ref(false)
  const title = ref('')
  const columns = ref<DrillDownColumn[]>([])
  const rows = ref<Record<string, unknown>[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = 50

  // Internal — monotonic counter for stale-response guard
  let requestId = 0
  // Internal — saved for pagination + retry
  let lastEndpoint = ''
  let lastParams: DrillDownParams = { metric: '' }

  async function _fetch(endpoint: string, params: DrillDownParams, pageNum: number) {
    const thisRequest = ++requestId
    loading.value = true
    error.value = null
    isPermissionError.value = false

    const { metric, ...contextFilters } = params
    try {
      const result = (await call(endpoint, {
        metric,
        // Backend signature: (metric: str, filters: str)
        // Frappe unpacks POST body as kwargs: metric=string, filters=json-string
        filters: JSON.stringify({ page: pageNum, ...contextFilters }),
      })) as { columns: DrillDownColumn[]; rows: Record<string, unknown>[]; total: number }

      if (thisRequest !== requestId) return // stale — discard
      columns.value = result.columns
      rows.value = result.rows
      total.value = result.total
      page.value = pageNum
    } catch (e: unknown) {
      if (thisRequest !== requestId) return
      const decoded = readFrappeError(e, 'An error occurred')
      isPermissionError.value = decoded.permission
      error.value = decoded.message
    } finally {
      if (thisRequest === requestId) {
        loading.value = false
      }
    }
  }

  // Debounce: only the _fetch network call is debounced (100ms).
  // show + loading are set immediately so the modal opens without delay.
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  function open(endpoint: string, titleStr: string, params: DrillDownParams) {
    lastEndpoint = endpoint
    lastParams = params
    title.value = titleStr
    // Open modal and show spinner immediately — no waiting for debounce
    show.value = true
    loading.value = true
    error.value = null
    isPermissionError.value = false
    page.value = 1  // always reset to page 1 on new open()

    // Debounce only the network call — if two clicks fire within 100ms,
    // only the last one sends a request
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => _fetch(endpoint, params, 1), 100)
  }

  function close() {
    show.value = false
    requestId++ // invalidate any in-flight request
    error.value = null
    isPermissionError.value = false
  }

  // retry() re-fetches the same endpoint, params, and current page.
  // The modal emits 'retry' → dashboard calls drillDown.retry().
  function retry() {
    _fetch(lastEndpoint, lastParams, page.value)
  }

  function nextPage() {
    if (page.value * pageSize >= total.value) return
    _fetch(lastEndpoint, lastParams, page.value + 1)
  }

  function prevPage() {
    if (page.value === 1) return
    _fetch(lastEndpoint, lastParams, page.value - 1)
  }

  return {
    show,
    loading,
    error,
    isPermissionError,
    title,
    columns,
    rows,
    total,
    page,
    pageSize,
    open,
    close,
    retry,
    nextPage,
    prevPage,
  }
}
