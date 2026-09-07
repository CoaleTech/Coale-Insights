/**
 * Single number and currency vocabulary for the intelligence dashboards.
 *
 * Replaces six divergent hand-rolled compact formatters that had four real
 * bugs between them:
 *
 * - `ExecutiveReports` hardcoded `$` on a company reporting INR.
 * - `customerUtils`, `HRIntelligence` and `StrategicFinanceIntelligence` all
 *   tested `value >= 1_000_000` without `Math.abs`, so negative money fell
 *   through every branch and rendered raw and ungrouped.
 * - `ExecutiveReports` used `>` not `>=`, so exactly 1,000,000 skipped the
 *   compact branch.
 * - Three of them defaulted the currency to a hardcoded literal, which lies
 *   whenever the site's company currency differs.
 *
 * `Intl.NumberFormat` handles all of it, and adds the currency symbol, which
 * matters on phones: `₹316.9M` is seven characters where `INR 316.9M` is ten.
 *
 * Locale is pinned to `en-US` numbering on purpose. `en-IN` would render
 * ₹316,871,197 as `₹31.7Cr` using crore, which is locale-correct for an Indian
 * audience but inconsistent with the M/K vocabulary already used across all 21
 * dashboards. One vocabulary everywhere beats per-locale correctness here.
 */

/**
 * `Intl.NumberFormat` construction is roughly three orders of magnitude slower
 * than reuse, and these run inside table row loops. Memoised by option key.
 */
const cache = new Map<string, Intl.NumberFormat>()

function formatter(key: string, build: () => Intl.NumberFormat): Intl.NumberFormat {
	const hit = cache.get(key)
	if (hit) return hit
	const made = build()
	cache.set(key, made)
	return made
}

/**
 * ISO 4217 is three letters. Anything else makes `Intl` throw a RangeError.
 *
 * Exported because components that hand-roll their own `Intl.NumberFormat` --
 * the 13-week cash flow surfaces do, deliberately, for `en-KE` grouping --
 * need the same guard. Without it a bad value reaches `Intl` and takes the
 * whole dashboard down with "Invalid currency code".
 */
export function safeCurrency(currency: string | undefined | null): string | null {
	if (!currency) return null
	const code = currency.trim().toUpperCase()
	return /^[A-Z]{3}$/.test(code) ? code : null
}

export interface MoneyOptions {
	/** Compact notation (₹316.9M). Use where width is constrained. */
	compact?: boolean
}

/**
 * Money for display. Returns compact or exact notation with the currency
 * symbol, handling negatives, zero and nullish input.
 *
 * `currency` is the company currency reported by the server. When it is missing
 * or not a valid ISO code the number is still formatted and the raw string is
 * prefixed, so an unexpected code degrades to `XYZ 316.9M` rather than throwing
 * or silently printing the wrong symbol.
 */
export function formatMoney(
	value: number | null | undefined,
	currency: string | null | undefined,
	options: MoneyOptions = {},
): string {
	if (!Number.isFinite(value)) return NO_VALUE
	const n = value as number
	const compact = options.compact ?? false
	const code = safeCurrency(currency)

	if (code) {
		const key = `m:${code}:${compact}`
		return formatter(key, () =>
			new Intl.NumberFormat('en-US', {
				style: 'currency',
				currency: code,
				notation: compact ? 'compact' : 'standard',
				maximumFractionDigits: compact ? 1 : 0,
			}),
		).format(n)
	}

	const raw = (currency ?? '').trim()
	const number = formatCount(n, { compact })
	// U+00A0, matching what Intl emits between a symbol-less code and its number,
	// so the degraded path wraps the same way the normal one does.
	return raw ? `${raw}\u00a0${number}` : number
}

export interface CountOptions {
	compact?: boolean
	decimals?: number
}

/** Plain numbers: headcount, lead counts, order counts. */
export function formatCount(value: number | null | undefined, options: CountOptions = {}): string {
	if (!Number.isFinite(value)) return NO_VALUE
	const n = value as number
	const compact = options.compact ?? false
	const decimals = options.decimals ?? (compact ? 1 : 0)
	const key = `c:${compact}:${decimals}`
	return formatter(key, () =>
		new Intl.NumberFormat('en-US', {
			notation: compact ? 'compact' : 'standard',
			maximumFractionDigits: decimals,
		}),
	).format(n)
}

/**
 * Cash-runway sublabel. `financial_intelligence.py` returns `999` months when
 * net burn is zero or negative -- a flag for "not consuming cash", not a
 * measurement. Naming that beats inventing an 82-year forecast to the day: a
 * caller that multiplied this by 30 and labelled it "days" once rendered
 * "29970 days runway" as fact. Single source of truth so every caller that
 * surfaces `runway_months` gets the same sentinel handling for free.
 */
export function cashRunwayLabel(months: number | null | undefined): string | undefined {
	if (months === null || months === undefined || !Number.isFinite(months)) return undefined
	if (months >= 999) return 'no net cash burn'
	return `${formatCount(months, { decimals: 1 })} months runway`
}

/**
 * Percentages already expressed on a 0-100 scale, which is how every endpoint
 * on this surface returns them.
 */
export function formatPercent(value: number | null | undefined, decimals = 1): string {
	if (!Number.isFinite(value)) return NO_VALUE
	const n = value as number
	const key = `p:${decimals}`
	return `${formatter(key, () =>
		new Intl.NumberFormat('en-US', {
			minimumFractionDigits: decimals,
			maximumFractionDigits: decimals,
		}),
	).format(n)}%`
}

/**
 * Dates, for the same reason as the numbers above: there were thirteen
 * hand-rolled `formatDate` helpers on this surface diverging on three axes at
 * once, so one timestamp rendered three different ways depending on which
 * dashboard you were looking at.
 *
 * - Locale: `en-KE` in five files, `en-US` in three, browser default in two.
 * - Missing value: `'-'`, `''`, `'N/A'`, `'TBD'` and `'Never'` were all in use.
 * - Time: four included it, the rest did not, with no pattern to which.
 *
 * Pinned to `en-KE` because the deployment reports in KES and the majority of
 * the dashboard chrome already used it. The numeric pin above stays `en-US`
 * deliberately: that one is about grouping vocabulary (M/K vs crore), which is
 * a different axis from date field order.
 *
 * Day-month-name-year is unambiguous for any reader, which matters more here
 * than in most products: an auditor and a CFO read the same finding, and
 * `3/2/2026` means two different days depending on who is looking.
 */
const DATE_LOCALE = 'en-KE'

/**
 * One absence marker for the whole vocabulary.
 *
 * Every formatter here returns this for `null`, `undefined` and non-finite
 * input. A real `0` is still rendered as `0`; only the absence of a measurement
 * becomes a dash.
 *
 * This module used to be split against itself: dates returned a dash while
 * money and counts coerced to zero, so `formatCount(undefined)` printed "0" and
 * a payload missing a field reported a confident measurement. That is the exact
 * defect the shared vocabulary was introduced to remove, sitting inside the
 * shared vocabulary.
 */
export const NO_VALUE = '-'

function parse(value: string | null | undefined): Date | null {
	if (!value) return null
	const d = new Date(value)
	// `new Date('not a date')` yields Invalid Date, whose `toLocaleDateString`
	// returns the literal string "Invalid Date". That is worse than a dash.
	return Number.isNaN(d.getTime()) ? null : d
}

/** Full date: `3 Feb 2026`. The default for table cells and detail rows. */
export function formatDate(value: string | null | undefined): string {
	const d = parse(value)
	if (!d) return NO_VALUE
	return d.toLocaleDateString(DATE_LOCALE, { year: 'numeric', month: 'short', day: 'numeric' })
}

/**
 * Date and time: `3 Feb 2026, 14:30`. Only where the clock time carries
 * meaning, such as a "last updated" stamp on live figures.
 */
export function formatDateTime(value: string | null | undefined): string {
	const d = parse(value)
	if (!d) return NO_VALUE
	return d.toLocaleDateString(DATE_LOCALE, {
		year: 'numeric',
		month: 'short',
		day: 'numeric',
		hour: '2-digit',
		minute: '2-digit',
	})
}

/**
 * Axis labels: `3 Feb`. Drops the year because chart axes repeat it on every
 * tick, where it costs width and tells the reader nothing.
 */
export function formatDateShort(value: string | null | undefined): string {
	const d = parse(value)
	if (!d) return NO_VALUE
	return d.toLocaleDateString(DATE_LOCALE, { month: 'short', day: 'numeric' })
}

/**
 * Relative age for recency lists such as chat history, where "2h ago" is what
 * the reader actually wants. Falls back to the absolute form once relative
 * stops being useful.
 */
export function formatRelative(value: string | null | undefined): string {
	const d = parse(value)
	if (!d) return NO_VALUE
	const diff = Date.now() - d.getTime()
	if (diff < 0) return formatDate(value)
	if (diff < 60_000) return 'Just now'
	if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
	if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
	if (diff < 604_800_000) return `${Math.floor(diff / 86_400_000)}d ago`
	return formatDate(value)
}

/**
 * Narrow an untyped payload field to a number, or to absent.
 *
 * Many endpoints are consumed as `Record<string, unknown>`, so their fields
 * arrive as `unknown`. Removing the `|| 0` guards at the call sites exposed
 * that: the raw field could no longer be handed straight to a component
 * expecting `string | number`.
 *
 * A guard rather than a cast, so a string or an object in the payload becomes
 * absent instead of being asserted into a number the value never was. `NaN` and
 * the infinities are absent too, since none of them is a measurement.
 */
export function asNumber(value: unknown): number | undefined {
	return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}
