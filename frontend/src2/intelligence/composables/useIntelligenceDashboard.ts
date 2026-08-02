import { createResource } from 'frappe-ui'
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { readFrappeError, readInsightsEnvelope } from '../../helpers/api'

/**
 * One data-loading contract for every intelligence dashboard.
 *
 * Replaces the `loadData(refresh) / isLoading / error / isRefreshing`
 * try-catch-finally block that was copy-pasted into 15 dashboards on top of the
 * raw `apiCall()` wrapper. `apiCall` returns a bare promise with no reactive
 * state, so each file rebuilt the same bookkeeping and none of them cached.
 *
 * Built on frappe-ui `createResource` so reload, caching, and reactive
 * error/loading come from the data layer instead of hand-rolled refs.
 *
 * Error handling mirrors `useDrillDown`, the existing house pattern: permission
 * failures are separated from generic ones so the caller can render a
 * "you don't have access" state instead of a retry button that will never work.
 *
 * ponytail: no per-dashboard subclassing. If one dashboard needs something
 * extra, it composes this and adds its own resource beside it.
 */

export interface IntelligenceDashboardOptions<T> {
  /** Dotted path to the whitelisted endpoint. */
  url: string
  /**
   * Reactive params. Re-fetches when they change, so a date-filter change needs
   * no explicit watcher in the dashboard.
   */
  params?: Ref<Record<string, unknown>>
  /**
   * Cache key. `createResource` caches globally, so this must be unique per
   * dashboard or two dashboards will share one response.
   */
  cache?: string
  /** Fetch on mount. Default true. */
  auto?: boolean
  initialData?: T
}

export interface IntelligenceDashboard<T> {
  data: ComputedRef<T | null>
  /** True only for the first load, so the caller can gate the initial skeleton. */
  loading: ComputedRef<boolean>
  /** True for a user-triggered refresh with data already on screen. */
  refreshing: Ref<boolean>
  error: Ref<string | null>
  isPermissionError: Ref<boolean>
  /** False until a response has landed. Gate summary cards on this, never on data alone. */
  hasData: ComputedRef<boolean>
  reload: () => void
  retry: () => void
}

export function useIntelligenceDashboard<T = Record<string, unknown>>(
  options: IntelligenceDashboardOptions<T>,
): IntelligenceDashboard<T> {
  const { url, params, cache, auto = true, initialData } = options

  const error = ref<string | null>(null)
  const isPermissionError = ref(false)
  const fetched = ref(false)
  const refreshing = ref(false)
  // Holds the UNWRAPPED payload. `createResource` exposes the raw `message`,
  // which for `insights.api.*` is the `{status, data}` envelope, so reading
  // `resource.data.<field>` directly renders zeros for every metric.
  const payload = ref<T | null>(null)

  const resource = createResource({
    url,
    cache,
    auto,
    initialData,
    makeParams: () => (params ? { ...params.value } : {}),
    onSuccess: (raw: unknown) => {
      const decoded = readInsightsEnvelope(raw)
      // A 200 carrying `{status: "error"}` is still a failure the user must see.
      isPermissionError.value = false
      error.value = decoded.error
      payload.value = decoded.error ? null : (decoded.data as T)
      fetched.value = true
      refreshing.value = false
    },
    onError: (e: unknown) => {
      const { permission, message } = readFrappeError(e, 'Could not load this dashboard')
      isPermissionError.value = permission
      error.value = message
      payload.value = null
      fetched.value = true
      refreshing.value = false
    },
  })

  if (params) {
    watch(
      params,
      () => {
        resource.reload()
      },
      { deep: true },
    )
  }

  return {
    // The unwrapped payload, not `resource.data`, which is the raw envelope.
    data: computed(() => payload.value),
    // Distinguishing first load from refresh is what lets the caller show a
    // skeleton once instead of blanking the page on every filter change.
    loading: computed(() => Boolean(resource.loading) && !fetched.value),
    refreshing,
    error,
    isPermissionError,
    /**
     * Requires a payload, not merely the absence of an error.
     *
     * `retry()` clears `error` before the refetch resolves, and `payload` is
     * still `null` from the failure at that moment. Without the payload check
     * `hasData` went true with nothing behind it, so the content branch rendered
     * over empty refs: the same "confident absence" defect as a KPI card showing
     * `0` for a fetch that never returned.
     */
    hasData: computed(() => fetched.value && !error.value && payload.value !== null),
    reload: () => {
      refreshing.value = true
      resource.reload()
    },
    retry: () => {
      error.value = null
      isPermissionError.value = false
      // Marked refreshing so the caller can show progress. Otherwise a retry
      // sits in a state that is neither loading, errored, nor populated, and the
      // page reads as empty until the response lands.
      refreshing.value = true
      resource.reload()
    },
  }
}
