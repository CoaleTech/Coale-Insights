import { ref, type Ref } from 'vue'

/**
 * Reactive viewport class for the intelligence dashboards.
 *
 * CSS media queries cover styling. This exists for the decisions CSS cannot
 * make: which ECharts height to build, whether to format currency compactly,
 * and whether the sidebar is a rail or an overlay. Those are JS-side values
 * that have to change with the viewport, not just be restyled by it.
 *
 * The two width thresholds are content-driven, not device-driven, and were
 * measured on this surface:
 *
 * - `isBelowDesktop` (<1024px): below this the 224px sidebar leaves under
 *   560px of content, which is where the KPI grid and tab strips were measured
 *   breaking. The sidebar becomes an overlay here.
 * - `isPhone` (<768px): below this a 5-column KPI grid cannot hold exact
 *   currency, so values switch to compact notation and wide tables scroll.
 *
 * `isShort` catches landscape phones (~375px tall), where a chart sized for
 * portrait would fill the entire viewport.
 */
export interface Breakpoint {
	/** Under 768px. Phone portrait and small windows. */
	isPhone: Ref<boolean>
	/** Under 1024px. Phone plus tablet portrait; sidebar is an overlay. */
	isBelowDesktop: Ref<boolean>
	/** Viewport shorter than 480px, i.e. landscape phone. */
	isShort: Ref<boolean>
}

/**
 * No `onScopeDispose` on these listeners, deliberately.
 *
 * They belong to a module-level singleton, so they must outlive every
 * component. Registering disposal would bind them to whichever component called
 * `useBreakpoint()` first, and that component unmounting would silently freeze
 * the refs for every other caller while `shared` kept handing them out. Three
 * listeners for the app's lifetime is the correct trade.
 */
function track(query: string): Ref<boolean> {
	const state = ref(false)
	if (typeof window === 'undefined' || !window.matchMedia) return state

	const mql = window.matchMedia(query)
	state.value = mql.matches
	mql.addEventListener('change', (e) => {
		state.value = e.matches
	})

	return state
}

/** Shared across callers so one listener set serves every component. */
let shared: Breakpoint | null = null

export function useBreakpoint(): Breakpoint {
	if (shared) return shared
	shared = {
		isPhone: track('(max-width: 767px)'),
		isBelowDesktop: track('(max-width: 1023px)'),
		isShort: track('(max-height: 480px)'),
	}
	return shared
}
