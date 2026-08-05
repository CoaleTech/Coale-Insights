/**
 * Single status vocabulary for the intelligence dashboards.
 *
 * Replaces the 12+ per-file helpers (getRagColor, getAlertClass, getRiskColor,
 * getVarianceColor, getHealthScoreColor, ragDotClass, getTrendBadge, ...) that
 * each invented their own thresholds and return types.
 *
 * ---------------------------------------------------------------------------
 * Why theme tokens and not Espresso semantic tokens
 *
 * Espresso's SEMANTIC inks stop at a shade that fails WCAG AA as body text,
 * measured against the installed palette on a light surface:
 *
 *     ink-green-3  #278F5E  4.06:1   FAIL
 *     ink-blue-2   #0289F7  3.34:1   FAIL
 *     ink-amber-3  #DB7706  3.16:1   FAIL
 *
 * The RAW scale goes darker and clears the 4.5:1 bar, so the theme layer in
 * `src2/index.css` pins the status tokens to the `-700` steps and exposes them
 * as `text-pos` / `text-warn` / `text-neg`:
 *
 *     --app-pos   #137949  green-700  4.96 canvas / 5.44 card
 *     --app-warn  #B35309  amber-700  4.61 canvas / 5.05 card
 *     --app-neg   #B52A2A  red-700    5.75 canvas / 6.31 card
 *
 * That is what lets status carry real colour instead of collapsing to neutral.
 * Because the tokens are CSS custom properties, a `[data-theme="dark"]` switch
 * retints everything with no `dark:` variant on any call site.
 *
 * TEXT vs GRAPHICS. WCAG asks 4.5:1 of text but only 3:1 of non-text UI. The
 * `*-fill` tokens keep mid-scale saturation so charts and bars stay readable,
 * and are NEVER valid for text. Every fill must still sit beside a text label:
 * PRODUCT.md requires that risk states not rely on colour alone.
 *
 * ponytail: frappe-ui 0.1.142 Badge variant="solid" is unusable for
 * blue/orange/red (it pairs a near-white ink with a near-white surface:
 * solid/blue 1.05:1, solid/orange 1.03:1, solid/red 1.46:1). Its `subtle`
 * green/amber also land under 4.5:1. So `severityBadge` reuses Badge's geometry
 * and overrides only the colour pair via `class`, each pair measured >= 4.83:1.
 */

/** frappe-ui Badge themes available in 0.1.142. */
export type BadgeTheme = 'gray' | 'blue' | 'green' | 'orange' | 'red'
/** frappe-ui Badge variants available in 0.1.142. */
export type BadgeVariant = 'solid' | 'subtle' | 'outline'

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'none'

/** Ordered worst-first, so callers can sort or take a max. */
export const SEVERITY_ORDER: readonly Severity[] = [
  'critical',
  'high',
  'medium',
  'low',
  'none',
] as const

export interface BadgeSpec {
  theme: BadgeTheme
  variant: BadgeVariant
  /** Human label. Always render it; the badge must never be colour-only. */
  label: string
  /** Colour pair overriding Badge's own, each measured >= 4.83:1. */
  class: string
}

/**
 * Badge spec for a severity. Bind straight onto frappe-ui `<Badge>`:
 *
 *   <Badge v-bind="severityBadge(row.severity)" :label="severityBadge(row.severity).label" />
 *
 * `v-bind` carries theme, variant, label and class together, so the geometry
 * comes from Badge and the colour from the theme layer.
 */
export function severityBadge(severity: Severity | string | null | undefined): BadgeSpec {
  switch (normaliseSeverity(severity)) {
    case 'critical':
      // Heaviest step: red ink on the deeper red tint, 4.93:1.
      return {
        theme: 'red',
        variant: 'subtle',
        label: 'Critical',
        class: 'text-neg bg-surface-red-2',
      }
    case 'high':
      return { theme: 'red', variant: 'subtle', label: 'High', class: 'text-neg bg-surface-red-1' }
    case 'medium':
      return {
        theme: 'orange',
        variant: 'subtle',
        label: 'Medium',
        class: 'text-warn bg-surface-amber-1',
      }
    case 'low':
      return {
        theme: 'green',
        variant: 'subtle',
        label: 'Low',
        class: 'text-pos bg-surface-green-2',
      }
    default:
      return {
        theme: 'gray',
        variant: 'subtle',
        label: 'Not rated',
        class: 'text-ink-gray-7 bg-surface-gray-2',
      }
  }
}

/**
 * Non-text fill for a bar, chart series, or indicator. >= 3:1 on a light
 * surface. MUST be rendered next to a text label or an accessible name.
 */
export function severityFill(severity: Severity | string | null | undefined): string {
  switch (normaliseSeverity(severity)) {
    case 'critical':
    case 'high':
      return 'bg-neg-fill'
    case 'medium':
      return 'bg-warn-fill'
    case 'low':
      return 'bg-pos-fill'
    default:
      return 'bg-muted-fill'
  }
}

/**
 * Accessible name for a status graphic, so a bar or indicator is never a bare
 * colour to assistive tech.
 *
 *   <div :class="severityFill(s)" :aria-label="severityAria('Credit risk', s, 72)" role="img" />
 */
export function severityAria(
  metric: string,
  severity: Severity | string | null | undefined,
  value?: number | string | null,
): string {
  const { label } = severityBadge(severity)
  return value === null || value === undefined || value === ''
    ? `${metric}: ${label}`
    : `${metric}: ${label} (${value})`
}

/**
 * Badge band for a 0-100 composite health score that the server also labels
 * with an Excellent / Good / Fair / Poor style word.
 *
 * The server uses four bands; `scoreSeverity` has three outcomes. There is
 * exactly one cut-point where the badge colour never contradicts the word:
 *
 * | score | server word | `{60,40}` | `{80,60}` | `{75,50}` |
 * |-------|-------------|-----------|-----------|-----------|
 * | 90    | Excellent   | low    ok | low    ok | low    ok |
 * | 70    | Good        | low    ok | medium -- | medium -- |
 * | 50    | Fair        | medium ok | high   -- | medium ok |
 * | 30    | Poor        | high   ok | high   ok | high   ok |
 *
 * So 60/40 it is. The two values shipped before this constant existed both
 * contradicted the server: 75/50 painted "Good" amber, and 80/60 would have
 * painted "Good" amber *and* "Fair" red. `liquidity_score` is only ever
 * 90/70/50/30 (`summary.py:202-209`), so the 70 -> "Good" + amber case was not
 * an edge case, it was the common one.
 *
 * Server bands, verified:
 * - `ml/strategic_finance/summary.py:217,238,259,269` -- liquidity /
 *   profitability / efficiency / overall: `>=80 Excellent, >=60 Good,
 *   >=40 Fair, else Poor`.
 * - `ml/customer_intelligence/analytics.py:452` -- customer health:
 *   `bins=[-inf, 40, 60, 80, inf] -> Critical, At Risk, Healthy, Excellent`.
 *
 * Only use this where the server emits that four-band vocabulary. Scores with
 * their own vocabulary keep their own explicit literals -- forcing an
 * unverified metric onto this band would silently move users' green/amber line
 * with no evidence, which is the same class of defect in the other direction.
 */
export const HEALTH_SCORE_THRESHOLDS = { good: 60, warn: 40 } as const

/**
 * The one place a numeric score becomes a severity.
 *
 * Callers pass thresholds explicitly so the numbers are visible at the call
 * site. For a 0-100 composite health score, pass `HEALTH_SCORE_THRESHOLDS`
 * rather than fresh literals -- visibility alone does not make two screens
 * agree, which is how the 80/60-vs-75/50 split survived being documented.
 *
 * `higherIsBetter: false` inverts for metrics where a big number is bad
 * (DSO, debt ratio, defect rate).
 */
export function scoreSeverity(
  score: number | null | undefined,
  thresholds: { good: number; warn: number; higherIsBetter?: boolean },
): Severity {
  if (score === null || score === undefined || Number.isNaN(score)) return 'none'
  const { good, warn, higherIsBetter = true } = thresholds
  if (higherIsBetter) {
    if (score >= good) return 'low'
    if (score >= warn) return 'medium'
    return 'high'
  }
  if (score <= good) return 'low'
  if (score <= warn) return 'medium'
  return 'high'
}

/** Normalise a server-supplied RAG string to a Severity. */
export function ragSeverity(rag: string | null | undefined): Severity {
  switch ((rag ?? '').trim().toLowerCase()) {
    case 'green':
    case 'ok':
    case 'healthy':
    case 'on track':
      return 'low'
    case 'amber':
    case 'yellow':
    case 'warning':
    case 'at risk':
      return 'medium'
    case 'red':
    case 'critical':
    case 'off track':
      return 'critical'
    default:
      return 'none'
  }
}

/**
 * Recommendation / initiative / alert priority word to a Severity.
 *
 * Three copies of this existed: two byte-identical ones defaulting unknown
 * priorities to `medium`, and a third in `CustomerSections` with no `critical`
 * case at all, so a critical customer action rendered at the same weight as a
 * medium one.
 *
 * Unknown maps to `none`, not `medium`. Inventing a middling priority for a
 * word the server did not send is the same over-reporting problem as a health
 * badge that reads "Good" next to a warning.
 */
export function prioritySeverity(priority: string | null | undefined): Severity {
  switch (String(priority ?? '').trim().toLowerCase()) {
    case 'critical':
    case 'urgent':
      return 'critical'
    case 'high':
      return 'high'
    case 'medium':
      return 'medium'
    case 'low':
      return 'low'
    default:
      return 'none'
  }
}

/**
 * Ink class for a signed delta (growth, variance, trend).
 *
 * Now genuinely bidirectional: `text-pos` is green-700 at 4.96:1 on canvas, so
 * an improving metric can read green without failing AA. Direction is still
 * carried by `deltaGlyph` as well, because colour alone is not an accessible
 * signal. `higherIsBetter: false` flips which sign counts as bad (expenses,
 * DSO, churn, scrap rate).
 */
export function deltaInk(
  value: number | null | undefined,
  opts: { higherIsBetter?: boolean } = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) {
    return 'text-ink-gray-6'
  }
  const { higherIsBetter = true } = opts
  const good = higherIsBetter ? value > 0 : value < 0
  return good ? 'text-pos' : 'text-neg'
}

/**
 * Ink class for a trend sparkline.
 *
 * Like `deltaInk` but routes the "good" direction through the app's primary
 * accent so the tiny graph feels part of the dashboard's identity, while the
 * "bad" direction still uses the status red. Neutral / flat lines recede with
 * the muted fill so they do not compete for attention.
 */
export function sparklineInk(
  value: number | null | undefined,
  opts: { higherIsBetter?: boolean } = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) {
    return 'text-muted-fill'
  }
  const { higherIsBetter = true } = opts
  const good = higherIsBetter ? value > 0 : value < 0
  return good ? 'text-accent' : 'text-neg'
}

/** Direction glyph so a delta is readable without colour. */
export function deltaGlyph(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) return ''
  return value > 0 ? '\u2191' : '\u2193'
}

function normaliseSeverity(input: Severity | string | null | undefined): Severity {
  const s = (input ?? '').toString().trim().toLowerCase()
  if (s === 'critical' || s === 'high' || s === 'medium' || s === 'low') return s
  // Common server spellings seen across the intelligence APIs.
  if (s === 'severe' || s === 'urgent') return 'critical'
  if (s === 'warning' || s === 'moderate') return 'medium'
  if (s === 'info' || s === 'ok' || s === 'normal') return 'low'
  return 'none'
}
