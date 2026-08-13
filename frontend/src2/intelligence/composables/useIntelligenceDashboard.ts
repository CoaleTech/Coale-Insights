import { createResource } from 'frappe-ui'
import { computed, onBeforeUnmount, ref, watch, type ComputedRef, type Ref } from 'vue'
import { readFrappeError, readInsightsEnvelope, ignoreRejection } from '../../helpers/api'

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
  /** True when the API returned `{status: "warming"}` — cache is cold, background job running. */
  warming: Ref<boolean>
  /** False until a response has landed. Gate summary cards on this, never on data alone. */
  hasData: ComputedRef<boolean>
  reload: () => void
  retry: () => void
}

/** The envelope can still carry `warming: true` if something is filling the
 * cache out of band. A dashboard that receives it must re-check on its own;
 * without this, "Preparing your dashboard" needed the user to click "Check
 * again" repeatedly and would sit there indefinitely otherwise. */
const WARMING_POLL_MS = 4000

/**
 * A 503 is backpressure, not failure. Dashboard payloads are computed off the
 * request now (see `insights/api/ml/utils.py`), so this no longer comes from
 * the ML path -- but anything else holding the line, an overloaded gunicorn or
 * a proxy shedding load, still answers 503, and the right response is the
 * same: come back shortly rather than show the user an error.
 *
 * Backed off and jittered so two dashboards on one page don't retry in
 * lockstep. Same contract as standard Insights' `scheduleQueryExecution`.
 */
const BUSY_MAX_ATTEMPTS = 8
const BUSY_BASE_DELAY_MS = 1000
const BUSY_MAX_DELAY_MS = 8000

function isServerBusyError(e: unknown) {
  const err = e as { status?: number; exc_type?: string } | null
  return err?.status === 503 && err?.exc_type === 'ServiceUnavailableError'
}

function busyRetryDelay(attempt: number) {
  const delay = Math.min(BUSY_BASE_DELAY_MS * 2 ** (attempt - 1), BUSY_MAX_DELAY_MS)
  return delay * (0.5 + Math.random())
}

export function useIntelligenceDashboard<T = Record<string, unknown>>(
  options: IntelligenceDashboardOptions<T>,
): IntelligenceDashboard<T> {
  const { url, params, cache, auto = true, initialData } = options

  const error = ref<string | null>(null)
  const isPermissionError = ref(false)
  const warming = ref(false)
  const fetched = ref(false)
  const refreshing = ref(false)
  // True between a busy rejection and its retry. Without it the gap reads as
  // "not loading, no error, no data" and the page flashes its empty state.
  const busyRetrying = ref(false)
  // Holds the UNWRAPPED payload. `createResource` exposes the raw `message`,
  // which for `insights.api.*` is the `{status, data}` envelope, so reading
  // `resource.data.<field>` directly renders zeros for every metric.
  const payload = ref<T | null>(null)

  // At most one pending auto-refetch, whether scheduled by a warming response
  // or by a busy rejection.
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let busyAttempt = 0
  function clearPollTimer() {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }
  function resetRetries() {
    clearPollTimer()
    busyAttempt = 0
    busyRetrying.value = false
  }
  function scheduleRefetch(delay: number) {
    clearPollTimer()
    pollTimer = setTimeout(() => {
      pollTimer = null
      ignoreRejection(resource.reload())
    }, delay)
  }

  const resource = createResource({
    url,
    cache,
    // frappe-ui's own `if (options.auto) out.fetch()` (resources.js) fires an
    // un-awaited fetch with no `.catch()`: on a gateway failure `out.fetch()`'s
    // promise rejects exactly like every other reload here, but nothing catches
    // *this* invocation, so it reached the console as an unhandled rejection
    // before `onError` below even ran. Trigger the initial fetch ourselves,
    // below, wrapped the same way every reload/retry already is.
    auto: false,
    initialData,
    makeParams: () => (params ? { ...params.value } : {}),
    onSuccess: (raw: unknown) => {
      const decoded = readInsightsEnvelope(raw)
      // A 200 carrying `{status: "error"}` is still a failure the user must see.
      isPermissionError.value = false
      warming.value = decoded.warming
      error.value = decoded.error
      payload.value = decoded.error || decoded.warming ? null : (decoded.data as T)
      fetched.value = true
      refreshing.value = false

      resetRetries()
      if (decoded.warming) {
        scheduleRefetch(WARMING_POLL_MS)
      }
    },
    onError: (e: unknown) => {
      // Load shedding, not failure: hold the current view and come back. Only
      // once the retries are spent does it become an error worth showing.
      if (isServerBusyError(e) && busyAttempt < BUSY_MAX_ATTEMPTS) {
        busyAttempt += 1
        busyRetrying.value = true
        scheduleRefetch(busyRetryDelay(busyAttempt))
        return
      }
      resetRetries()
      const { permission, message } = readFrappeError(e, 'Could not load this dashboard')
      isPermissionError.value = permission
      warming.value = false
      error.value = message
      payload.value = null
      fetched.value = true
      refreshing.value = false
    },
  })

  if (auto) {
    ignoreRejection(resource.fetch())
  }

  if (params) {
    watch(
      params,
      () => {
        resetRetries()
        ignoreRejection(resource.reload())
      },
      { deep: true },
    )
  }

  onBeforeUnmount(clearPollTimer)

  return {
    // The unwrapped payload, not `resource.data`, which is the raw envelope.
    data: computed(() => payload.value),
    // Distinguishing first load from refresh is what lets the caller show a
    // skeleton once instead of blanking the page on every filter change.
    loading: computed(
      () => (Boolean(resource.loading) || busyRetrying.value) && !fetched.value,
    ),
    refreshing,
    error,
    isPermissionError,
    warming,
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
      resetRetries()
      refreshing.value = true
      ignoreRejection(resource.reload())
    },
    retry: () => {
      resetRetries()
      error.value = null
      isPermissionError.value = false
      // Marked refreshing so the caller can show progress. Otherwise a retry
      // sits in a state that is neither loading, errored, nor populated, and the
      // page reads as empty until the response lands.
      refreshing.value = true
      ignoreRejection(resource.reload())
    },
  }
}
