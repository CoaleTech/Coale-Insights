import { computed, ref, watch, type Ref } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'insights:theme'

/**
 * Reactive light/dark theme, applied to `<html data-theme>`.
 *
 * Singleton, not per-call: theme is app-wide state (the sidebar toggle and
 * any future settings control must agree on one value), unlike
 * `usePrefersReducedMotion`, which each caller tracks independently.
 *
 * Precedence: an explicit user choice (persisted to `localStorage`) always
 * wins; otherwise the OS `prefers-color-scheme` media query decides, and
 * keeps tracking it live so an OS-level theme change updates the app without
 * a reload — same reasoning as `usePrefersReducedMotion`.
 *
 * `index.html` carries an inline script that reads the identical
 * `localStorage` key and sets `data-theme` before Vue mounts, so there is no
 * flash of the wrong theme on load. This module's own `watch(..., {
 * immediate: true })` re-applies the same attribute at import time, which is
 * redundant with that inline script but harmless — it is also what keeps the
 * attribute correct on every subsequent change.
 */

function systemPrefersDark(): boolean {
	return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-color-scheme: dark)').matches
}

function readStoredTheme(): ThemeMode | null {
	if (typeof localStorage === 'undefined') return null
	const raw = localStorage.getItem(STORAGE_KEY)
	return raw === 'light' || raw === 'dark' ? raw : null
}

const explicitTheme = ref<ThemeMode | null>(readStoredTheme())
const systemDark = ref(systemPrefersDark())

if (typeof window !== 'undefined' && window.matchMedia) {
	const query = window.matchMedia('(prefers-color-scheme: dark)')
	query.addEventListener('change', (e) => {
		systemDark.value = e.matches
	})
}

/** `computed`, not a `watch`-derived ref: derived state must be
 *  synchronously correct the instant `explicitTheme`/`systemDark` change,
 *  where a watcher callback only runs on the next reactive flush. */
const theme = computed<ThemeMode>(() => explicitTheme.value ?? (systemDark.value ? 'dark' : 'light'))

watch(
	theme,
	(mode) => {
		if (typeof document !== 'undefined') document.documentElement.setAttribute('data-theme', mode)
	},
	{ immediate: true, flush: 'sync' },
)

export function useTheme(): {
	theme: Ref<ThemeMode>
	/** Pins an explicit choice, persisted across sessions. */
	setTheme: (mode: ThemeMode) => void
	toggleTheme: () => void
} {
	function setTheme(mode: ThemeMode) {
		explicitTheme.value = mode
		if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, mode)
	}
	function toggleTheme() {
		setTheme(theme.value === 'dark' ? 'light' : 'dark')
	}
	return { theme, setTheme, toggleTheme }
}
