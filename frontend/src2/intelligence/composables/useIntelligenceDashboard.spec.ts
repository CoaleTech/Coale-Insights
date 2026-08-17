import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { ref } from 'vue'

// Mock frappe-ui's createResource. The mock captures the config object each
// call site passes in, so a test can invoke `onSuccess`/`onError` directly to
// simulate a resolved/rejected fetch — the same "drive the callback, not the
// transport" approach `useDrillDown.spec.ts` uses for `call`.
vi.mock('frappe-ui', () => ({
  createResource: vi.fn(),
}))

import { createResource } from 'frappe-ui'
import { useIntelligenceDashboard } from './useIntelligenceDashboard'

/** What this spec needs from the config `createResource` is invoked with. */
interface MockResourceConfig {
  onSuccess?: (raw: unknown) => void
  onError?: (e: unknown) => void
  makeParams?: () => Record<string, unknown>
}

/** The minimal resource surface `useIntelligenceDashboard` actually reads:
 * `loading`, and the `fetch`/`reload` methods it calls on mount/refetch. */
interface MockResource {
  loading: boolean
  fetch: () => Promise<unknown>
  reload: () => Promise<unknown>
}

// frappe-ui ships plain JS with no `.d.ts`, so its inferred TS shape comes
// from structural analysis of `resources.js` rather than a stable contract.
// Matching that inferred shape exactly in a mock is impractical and would
// break on unrelated internal frappe-ui changes; this file only needs to
// intercept the config object and hand back a resource stub.
const mockCreateResource = createResource as unknown as Mock

let capturedConfig: MockResourceConfig

describe('useIntelligenceDashboard — not_implemented stub handling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockCreateResource.mockImplementation((cfg: unknown) => {
      capturedConfig = cfg as MockResourceConfig
      const resource: MockResource = {
        loading: false,
        fetch: () => Promise.resolve(),
        reload: () => Promise.resolve(),
      }
      return resource
    })
  })

  it('flags a nested {status: "not_implemented"} payload distinctly from real data', () => {
    const dash = useIntelligenceDashboard({ url: 'insights.api.ml.get_esg_overview' })

    // The real envelope shape: outer success wrapper, inner honest stub.
    // See insights/api/ml/esg.py::get_esg_overview.
    capturedConfig.onSuccess?.({
      status: 'success',
      data: {
        status: 'not_implemented',
        message: 'ESG intelligence is not yet backed by real data',
      },
    })

    expect(dash.notImplemented.value).toBe(true)
    expect(dash.notImplementedMessage.value).toBe(
      'ESG intelligence is not yet backed by real data',
    )
  })

  it('does not treat a stub as real data: hasData stays false, data stays null', () => {
    const dash = useIntelligenceDashboard({ url: 'insights.api.ml.get_esg_overview' })

    capturedConfig.onSuccess?.({
      status: 'success',
      data: { status: 'not_implemented', message: 'Not built yet' },
    })

    // Before this fix, `payload.value` was set to the stub object itself, so
    // `hasData` (fetched && !error && payload !== null) went true and the
    // dashboard rendered its real template against undefined fields.
    expect(dash.hasData.value).toBe(false)
    expect(dash.data.value).toBe(null)
    expect(dash.error.value).toBe(null)
    expect(dash.warming.value).toBe(false)
  })

  it('does not mistake a real payload that merely has a "status" field for a stub', () => {
    const dash = useIntelligenceDashboard({ url: 'insights.api.ml.risk_intelligence' })

    // risk_intelligence's flat shape: status is a sibling of the real fields,
    // not `{status: "not_implemented"}` on its own. readInsightsEnvelope
    // strips `status` from this shape (see helpers/api.ts), so it must never
    // reach the stub check.
    capturedConfig.onSuccess?.({
      status: 'success',
      generated_at: '2026-08-16',
      overview: { credit_risk_score: 70.8 },
    })

    expect(dash.notImplemented.value).toBe(false)
    expect(dash.hasData.value).toBe(true)
    expect(dash.data.value).toEqual({
      generated_at: '2026-08-16',
      overview: { credit_risk_score: 70.8 },
    })
  })

  it('resets notImplemented on a later real response (feature shipped after a stale stub)', () => {
    const dash = useIntelligenceDashboard({ url: 'insights.api.ml.get_esg_overview' })

    capturedConfig.onSuccess?.({
      status: 'success',
      data: { status: 'not_implemented', message: 'Not built yet' },
    })
    expect(dash.notImplemented.value).toBe(true)

    capturedConfig.onSuccess?.({
      status: 'success',
      data: { environmental_metrics: { carbon_tons: 12 } },
    })
    expect(dash.notImplemented.value).toBe(false)
    expect(dash.notImplementedMessage.value).toBe(null)
    expect(dash.hasData.value).toBe(true)
  })

  it('clears notImplemented on a transport error rather than leaving it stale', () => {
    const dash = useIntelligenceDashboard({ url: 'insights.api.ml.get_esg_overview' })

    capturedConfig.onSuccess?.({
      status: 'success',
      data: { status: 'not_implemented', message: 'Not built yet' },
    })
    expect(dash.notImplemented.value).toBe(true)

    capturedConfig.onError?.(new Error('Network error'))
    expect(dash.notImplemented.value).toBe(false)
    expect(dash.notImplementedMessage.value).toBe(null)
    expect(dash.error.value).toBeTruthy()
  })
})

describe('useIntelligenceDashboard — forced refresh param', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockCreateResource.mockImplementation((cfg: unknown) => {
      capturedConfig = cfg as MockResourceConfig
      const resource: MockResource = {
        loading: false,
        fetch: () => Promise.resolve(),
        reload: () => Promise.resolve(),
      }
      return resource
    })
  })

  // `cached_run` on the backend only recomputes-while-still-serving-cache
  // when the request carries `refresh=1` (`insights.api.ml.utils
  // ._refresh_requested`). Without this, `reload()`/`retry()` were
  // observably indistinguishable from the params-change auto-refetch: both
  // just called `resource.reload()`, so a click on "Refresh" with a healthy
  // cache entry already present did nothing at all.
  it('reload() adds refresh=1 to the next request without dropping existing params', () => {
    const dash = useIntelligenceDashboard({ url: 'insights.api.ml.marketing.get_marketing_overview', params: ref({ period: 'YTD' }) })

    expect(capturedConfig.makeParams?.()).toEqual({ period: 'YTD' })

    dash.reload()

    expect(capturedConfig.makeParams?.()).toEqual({ period: 'YTD', refresh: 1 })
  })

  // The "Check again" button is the only UI path that can clear a tripped
  // `cached_run` circuit breaker once a background job has failed 3 times —
  // it must actually ask for a recompute, not silently replay the same
  // failing cache read.
  it('retry() adds refresh=1 to the next request', () => {
    const dash = useIntelligenceDashboard({ url: 'insights.api.ml.get_esg_overview' })

    dash.retry()

    expect(capturedConfig.makeParams?.()).toEqual({ refresh: 1 })
  })

  it('clears the forced refresh once the request succeeds, so the next natural reload is unforced', () => {
    const dash = useIntelligenceDashboard({ url: 'insights.api.ml.get_esg_overview' })

    dash.reload()
    expect(capturedConfig.makeParams?.()).toEqual({ refresh: 1 })

    capturedConfig.onSuccess?.({ status: 'success', data: { total: 1 } })

    expect(capturedConfig.makeParams?.()).toEqual({})
  })

  it('clears the forced refresh once the request errors, so a second retry is not silently skipped', () => {
    const dash = useIntelligenceDashboard({ url: 'insights.api.ml.get_esg_overview' })

    dash.retry()
    expect(capturedConfig.makeParams?.()).toEqual({ refresh: 1 })

    capturedConfig.onError?.(new Error('boom'))

    expect(capturedConfig.makeParams?.()).toEqual({})
  })
})
