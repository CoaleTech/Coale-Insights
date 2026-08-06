import { call } from 'frappe-ui'

/**
 * The one place the Insights response envelope is decoded.
 *
 * Most `insights.api.*` endpoints wrap their payload via
 * `insights/api/response.py`, which returns `{"status": "success", "data": {...}}`
 * or `{"status": "error", "message": "..."}`. A few return a plain dict instead.
 * Both shapes must work, so an object without a `status` key is passed through
 * untouched.
 *
 * This exists because `apiCall` unwrapped the envelope inline while
 * `createResource` hands back the raw `message`. Dashboards migrated from one to
 * the other silently started reading one level too high and rendered zeros for
 * every metric. Keep exactly one decoder so the two paths cannot drift again.
 */
export function readInsightsEnvelope(payload: unknown): {
	data: unknown
	error: string | null
	queuedKey?: string
} {
	if (typeof payload !== 'object' || payload === null || !('status' in payload)) {
		return { data: payload, error: null }
	}
	/*
	 * Expensive dashboards are computed on a worker (see
	 * insights/api/ml/async_compute.py) and answer `{status: "queued", key}`
	 * until the result lands. Surface the key so `apiCall` can poll; without
	 * this the queued envelope fell through and dashboards rendered it as data.
	 */
	if (payload.status === 'queued') {
		const key = 'key' in payload && typeof payload.key === 'string' ? payload.key : ''
		return { data: null, error: null, queuedKey: key }
	}
	if (payload.status === 'error') {
		const message =
			'message' in payload && typeof payload.message === 'string'
				? payload.message
				: 'Request failed'
		return { data: null, error: message }
	}
	if (payload.status === 'success') {
		if ('data' in payload) return { data: payload.data, error: null }
		/*
		 * Some endpoints put `status` at the top level with the payload as its
		 * siblings rather than nested under `data` -- `risk_intelligence` returns
		 * `{status, generated_at, company, overview, credit_risk, ...}`.
		 *
		 * Returning null for that shape blanked the entire Risk dashboard: every
		 * card read an empty object and rendered "N/A" while the API was answering
		 * 200 with a Credit Risk score of 70.8 and a live overdue-customer alert.
		 * It went unnoticed for as long as `hasData` ignored a null payload,
		 * because the cards fell back to a plausible-looking zero instead.
		 */
		const { status: _status, ...rest } = payload as Record<string, unknown>
		return { data: rest, error: null }
	}
	return { data: payload, error: null }
}

/**
 * A gateway failure (502/504) answers with an HTML error page, not JSON, so
 * frappe-ui's `transformResponse` reads `exc_type` off `undefined` and throws
 * `TypeError: Cannot read properties of undefined`. That buried the real cause
 * and, on paths without a catch, surfaced as an unhandled rejection.
 *
 * Translate it once, here, into something a user can act on.
 */
export function normalizeTransportError(e: unknown, method: string): Error {
	if (e instanceof TypeError) {
		const detail = e.message.includes('exc_type')
			? 'the server returned a gateway error instead of a response'
			: e.message
		return new Error(
			`${method} did not complete — ${detail}. ` +
				'This usually means the dashboard is still being computed on the server; retry shortly.',
		)
	}
	return e instanceof Error ? e : new Error(String(e))
}

/** How long to keep polling a queued dashboard before giving up. */
const QUEUE_POLL_TIMEOUT_MS = 5 * 60 * 1000
const QUEUE_POLL_INTERVAL_MS = 2000

/*
 * `Promise.withResolvers()` would read better here, but it is ES2024 and this
 * project targets ES2020 (see tsconfig `target`/`lib`). It is a runtime
 * feature, not just a type, so adopting it would drop support for browsers
 * below Chrome 119 / Safari 17.4. Keep the executor form until the baseline
 * moves.
 */
const sleep = (ms: number): Promise<void> =>
	new Promise((resolve) => {
		setTimeout(resolve, ms)
	})

/**
 * Call an Insights endpoint, transparently waiting out a queued computation.
 *
 * Heavy dashboards no longer block a web worker; they queue and return
 * `{status: "queued"}`. Polling lives here so every caller benefits without
 * each dashboard growing its own retry loop.
 */
export async function apiCall<T>(
	method: string,
	params?: Record<string, unknown>,
): Promise<T> {
	const invoke = async (m: string, p?: Record<string, unknown>) => {
		try {
			return await call(m, p)
		} catch (e) {
			throw normalizeTransportError(e, m)
		}
	}

	let { data, error, queuedKey } = readInsightsEnvelope(await invoke(method, params))
	if (error) throw new Error(error)

	const deadline = Date.now() + QUEUE_POLL_TIMEOUT_MS
	while (queuedKey !== undefined) {
		if (Date.now() > deadline) {
			throw new Error(
				`${method} is still being computed after ${QUEUE_POLL_TIMEOUT_MS / 1000}s. ` +
					'If this persists, check that background workers are running on the server.',
			)
		}
		await sleep(QUEUE_POLL_INTERVAL_MS)
		;({ data, error, queuedKey } = readInsightsEnvelope(
			await invoke('insights.api.ml.async_compute.async_status', { key: queuedKey }),
		))
		if (error) throw new Error(error)
	}

	return data as T
}

/**
 * `createResource.submit()` / `.reload()` report failure through `onError` *and*
 * reject the promise they return. A call site that relies on `onError` therefore
 * still leaks an unhandled rejection, which reaches the console as
 * "Uncaught (in promise) TypeError" with no app frame to trace it to.
 *
 * Wrap those fire-and-forget calls so the rejection is explicitly accounted for.
 * The resource's own `onError` stays the single place that sets UI state.
 */
export function ignoreRejection(result: unknown): void {
	if (result && typeof (result as Promise<unknown>).catch === 'function') {
		void (result as Promise<unknown>).catch(() => {})
	}
}

/**
 * The one place the Frappe error shape is decoded.
 *
 * Frappe puts `exc_type` on the response body for a raised Python exception,
 * user-facing text in `messages`, and the HTTP code in `status`. Narrowed rather
 * than cast, so a changed shape degrades to the fallback message instead of
 * throwing inside the error handler itself.
 *
 * Use this in every `catch` instead of an untyped error binding, so permission failures
 * stay distinguishable from generic ones across the whole surface.
 */
export function readFrappeError(
	e: unknown,
	fallback = 'Something went wrong',
): { permission: boolean; message: string } {
	if (typeof e !== 'object' || e === null) {
		return { permission: false, message: typeof e === 'string' && e ? e : fallback }
	}
	// A gateway failure arrives as a TypeError from frappe-ui's response parser.
	// Report it as a server problem rather than the fallback, which reads like a
	// bug in the dashboard.
	if (e instanceof TypeError) {
		return {
			permission: false,
			message:
				'The server did not return a response (gateway error). ' +
				'The dashboard may still be computing — retry in a moment.',
		}
	}
	const excType = 'exc_type' in e ? e.exc_type : undefined
	const status = 'status' in e ? e.status : undefined
	const messages = 'messages' in e ? e.messages : undefined
	const message = 'message' in e ? e.message : undefined
	const first =
		Array.isArray(messages) && typeof messages[0] === 'string' ? messages[0] : undefined

	return {
		permission: excType === 'PermissionError' || status === 403,
		message: first ?? (typeof message === 'string' && message ? message : fallback),
	}
}