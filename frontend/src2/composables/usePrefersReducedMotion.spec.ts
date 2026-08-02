import { effectScope } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { usePrefersReducedMotion } from './usePrefersReducedMotion'

/**
 * Guards the one motion path CSS cannot cover.
 *
 * Tailwind's `motion-reduce:` variant handles class-based transitions, but
 * ECharts runs its own animation loop and never reads the media query, so this
 * composable is what carries the preference into chart options. If it silently
 * returns false, every chart animates against an explicit accessibility
 * preference and nothing else catches it.
 */

type Listener = (e: MediaQueryListEvent) => void

function stubMatchMedia(matches: boolean) {
	const listeners: Listener[] = []
	const mql = {
		matches,
		media: '(prefers-reduced-motion: reduce)',
		addEventListener: vi.fn((_: string, fn: Listener) => listeners.push(fn)),
		removeEventListener: vi.fn((_: string, fn: Listener) => {
			const i = listeners.indexOf(fn)
			if (i >= 0) listeners.splice(i, 1)
		}),
	}
	vi.stubGlobal(
		'matchMedia',
		vi.fn(() => mql),
	)
	return {
		mql,
		emit(next: boolean) {
			mql.matches = next
			listeners.forEach((fn) => fn({ matches: next } as MediaQueryListEvent))
		},
		listenerCount: () => listeners.length,
	}
}

describe('usePrefersReducedMotion', () => {
	beforeEach(() => {
		vi.unstubAllGlobals()
	})

	it('reports the preference at creation', () => {
		stubMatchMedia(true)
		expect(usePrefersReducedMotion().value).toBe(true)
	})

	it('reports false when the user has no preference', () => {
		stubMatchMedia(false)
		expect(usePrefersReducedMotion().value).toBe(false)
	})

	it('tracks a change without needing a reload', () => {
		const media = stubMatchMedia(false)
		const prefers = usePrefersReducedMotion()
		expect(prefers.value).toBe(false)
		media.emit(true)
		expect(prefers.value).toBe(true)
		media.emit(false)
		expect(prefers.value).toBe(false)
	})

	it('removes its listener when the owning scope is disposed', () => {
		const media = stubMatchMedia(false)
		const scope = effectScope()
		scope.run(() => usePrefersReducedMotion())
		expect(media.listenerCount()).toBe(1)
		scope.stop()
		expect(media.listenerCount()).toBe(0)
	})

	it('degrades to false when matchMedia is unavailable', () => {
		vi.stubGlobal('matchMedia', undefined)
		expect(usePrefersReducedMotion().value).toBe(false)
	})
})
