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
} {
	if (typeof payload !== 'object' || payload === null || !('status' in payload)) {
		return { data: payload, error: null }
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

export async function apiCall<T>(
	method: string,
	params?: Record<string, unknown>,
): Promise<T> {
	const { data, error } = readInsightsEnvelope(await call(method, params))
	if (error) throw new Error(error)
	return data as T
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