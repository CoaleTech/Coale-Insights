import { onScopeDispose, ref, type Ref } from 'vue'

/**
 * Reactive `prefers-reduced-motion` state.
 *
 * CSS handles this for class-based transitions via Tailwind's `motion-reduce:`
 * variant. Canvas and SVG chart libraries do not: ECharts runs its own animation
 * loop and never reads the media query, so the preference has to be plumbed into
 * chart options in JS.
 *
 * Tracks changes rather than reading once, so toggling the OS setting updates a
 * mounted chart without a reload.
 */
export function usePrefersReducedMotion(): Ref<boolean> {
	const prefers = ref(false)
	if (typeof window === 'undefined' || !window.matchMedia) return prefers

	const query = window.matchMedia('(prefers-reduced-motion: reduce)')
	prefers.value = query.matches

	const onChange = (e: MediaQueryListEvent) => {
		prefers.value = e.matches
	}
	query.addEventListener('change', onChange)
	onScopeDispose(() => query.removeEventListener('change', onChange))

	return prefers
}
