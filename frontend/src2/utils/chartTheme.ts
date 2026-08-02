/**
 * Chart colour resolution for frappe-ui's chart components.
 *
 * `AxisChart`, `DonutChart` and `FunnelChart` wrap ECharts, which renders to a
 * canvas. Canvas cannot resolve CSS custom properties, so passing
 * `var(--app-accent)` into a chart `colors` array yields no colour at all: the
 * same silent-failure class as the dead `indigo-*` utilities.
 *
 * Reading the computed value at call time keeps one source of truth in
 * `src2/index.css` AND keeps the charts correct after a `[data-theme]` switch,
 * which a hardcoded hex array would not.
 *
 * Every colour below is drawn from the >= 3:1 non-text fill set, because a chart
 * series is a non-text graphic. Series must still be labelled: a legend or axis
 * label is what makes the chart readable without colour.
 */

/**
 * Theme tokens that are safe as chart series fills, ordered for distinguishability.
 *
 * `--app-info-fill` is deliberately absent: it resolves to the same `#0070cc` as
 * `--app-accent` in both the live theme and the fallback table below, so having
 * both here made `chartPalette(2)` return one colour twice and rendered a
 * two-series chart as a single indistinguishable pair. Hues alternate rather
 * than running blue-to-blue for the same reason.
 *
 * Status hues appear here because this set is also the >= 3:1 non-text fill set.
 * That is only acceptable while every series stays labelled: a legend or axis
 * label is what carries the meaning, never the colour.
 */
const SERIES_TOKENS = [
  '--app-accent',
  '--app-warn-fill',
  '--app-pos-fill',
  '--app-neg-fill',
  '--app-accent-strong',
  '--app-muted-fill',
] as const

/** Fallbacks matched to the light theme's default values (`:root` in
 *  index.css), used before mount or in tests. */
const FALLBACKS: Record<string, string> = {
  '--app-accent': '#0070cc',
  '--app-accent-strong': '#005ca3',
  '--app-info-fill': '#0070cc',
  '--app-pos-fill': '#278f5e',
  '--app-warn-fill': '#db7706',
  '--app-neg-fill': '#cc2929',
  '--app-muted-fill': '#7c7c7c',
}

/** Resolve one theme token to a literal colour ECharts can paint. */
export function themeColor(token: keyof typeof FALLBACKS | string): string {
  if (typeof document === 'undefined') return FALLBACKS[token] ?? '#0070cc'
  const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim()
  return value || FALLBACKS[token] || '#0070cc'
}

/**
 * Ordered palette for multi-series charts.
 *
 *   <AxisChart :config="{ ...cfg, colors: chartPalette() }" />
 *
 * Accent first, so a single-series chart matches the rest of the app chrome
 * rather than introducing a sixth hue.
 */
export function chartPalette(count?: number): string[] {
  const all = SERIES_TOKENS.map(themeColor)
  return count ? all.slice(0, count) : all
}

/** Semantic pair for charts where one series is good and the other is bad. */
export function signedPalette(): string[] {
  return [themeColor('--app-pos-fill'), themeColor('--app-neg-fill')]
}
