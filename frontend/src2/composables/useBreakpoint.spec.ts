import { effectScope } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * Guards the viewport thresholds the dashboards branch on in JS: which chart
 * height to build, whether currency is compact, and whether the sidebar is a
 * rail or an overlay.
 *
 * The disposal test is the important one. An earlier draft registered
 * `onScopeDispose` inside this module-level singleton, which bound the listeners
 * to whichever component happened to call first. That component unmounting
 * froze the refs for every other caller while the singleton kept handing them
 * out, so KPI cards would silently stop switching notation on rotation.
 */

type Listener = (e: MediaQueryListEvent) => void

function stubMatchMedia(initial: Record<string, boolean>) {
	const byQuery = new Map<string, { matches: boolean; listeners: Listener[] }>()
	vi.stubGlobal(
		'matchMedia',
		vi.fn((query: string) => {
			let entry = byQuery.get(query)
			if (!entry) {
				entry = { matches: initial[query] ?? false, listeners: [] }
				byQuery.set(query, entry)
			}
			const state = entry
			return {
				get matches() {
					return state.matches
				},
				media: query,
				addEventListener: vi.fn((_: string, fn: Listener) => state.listeners.push(fn)),
				removeEventListener: vi.fn((_: string, fn: Listener) => {
					const i = state.listeners.indexOf(fn)
					if (i >= 0) state.listeners.splice(i, 1)
				}),
			}
		}),
	)
	return {
		emit(query: string, next: boolean) {
			const entry = byQuery.get(query)
			if (!entry) throw new Error(`nothing is watching ${query}`)
			entry.matches = next
			entry.listeners.forEach((fn) => fn({ matches: next } as MediaQueryListEvent))
		},
		listenerCount: (query: string) => byQuery.get(query)?.listeners.length ?? 0,
		queries: () => [...byQuery.keys()],
	}
}

const PHONE = '(max-width: 767px)'
const BELOW_DESKTOP = '(max-width: 1023px)'
const SHORT = '(max-height: 480px)'

/**
 * Dynamic import is required here, not a preference.
 *
 * `useBreakpoint` caches a module-level singleton on first call. A static import
 * would bind this file to one cached instance, so every test after the first
 * would observe the previous test's listeners and stubbed viewport. Resetting
 * the module registry and re-importing is the only way to exercise creation,
 * which is exactly what the threshold and disposal assertions test.
 */
async function freshBreakpoint() {
	vi.resetModules()
	return (await import('./useBreakpoint')).useBreakpoint
}

describe('useBreakpoint', () => {
	beforeEach(() => {
		vi.unstubAllGlobals()
	})

	it('reports each threshold at creation', async () => {
		stubMatchMedia({ [PHONE]: true, [BELOW_DESKTOP]: true, [SHORT]: false })
		const useBreakpoint = await freshBreakpoint()
		const { isPhone, isBelowDesktop, isShort } = useBreakpoint()
		expect(isPhone.value).toBe(true)
		expect(isBelowDesktop.value).toBe(true)
		expect(isShort.value).toBe(false)
	})

	it('separates tablet portrait from phone', async () => {
		// 768-1023px: the sidebar becomes an overlay but currency stays exact.
		stubMatchMedia({ [PHONE]: false, [BELOW_DESKTOP]: true, [SHORT]: false })
		const useBreakpoint = await freshBreakpoint()
		const { isPhone, isBelowDesktop } = useBreakpoint()
		expect(isPhone.value).toBe(false)
		expect(isBelowDesktop.value).toBe(true)
	})

	it('tracks a resize across a threshold', async () => {
		const media = stubMatchMedia({ [PHONE]: false, [BELOW_DESKTOP]: false, [SHORT]: false })
		const useBreakpoint = await freshBreakpoint()
		const { isPhone } = useBreakpoint()
		expect(isPhone.value).toBe(false)
		media.emit(PHONE, true)
		expect(isPhone.value).toBe(true)
	})

	it('tracks rotation into a short viewport', async () => {
		const media = stubMatchMedia({ [PHONE]: true, [BELOW_DESKTOP]: true, [SHORT]: false })
		const useBreakpoint = await freshBreakpoint()
		const { isShort } = useBreakpoint()
		media.emit(SHORT, true)
		expect(isShort.value).toBe(true)
	})

	it('hands every caller the same refs so one listener set serves all', async () => {
		const media = stubMatchMedia({ [PHONE]: false, [BELOW_DESKTOP]: false, [SHORT]: false })
		const useBreakpoint = await freshBreakpoint()
		const first = useBreakpoint()
		const second = useBreakpoint()
		expect(second.isPhone).toBe(first.isPhone)
		expect(media.listenerCount(PHONE)).toBe(1)
	})

	it('keeps listening after the creating component is torn down', async () => {
		// The regression this file exists for: a scope-bound listener would be
		// removed here, silently freezing the value for every surviving caller.
		const media = stubMatchMedia({ [PHONE]: false, [BELOW_DESKTOP]: false, [SHORT]: false })
		const useBreakpoint = await freshBreakpoint()
		const scope = effectScope()
		const bp = scope.run(() => useBreakpoint())!
		expect(media.listenerCount(PHONE)).toBe(1)

		scope.stop()

		expect(media.listenerCount(PHONE)).toBe(1)
		media.emit(PHONE, true)
		expect(bp.isPhone.value).toBe(true)
	})

	it('degrades to false everywhere when matchMedia is unavailable', async () => {
		vi.stubGlobal('matchMedia', undefined)
		const useBreakpoint = await freshBreakpoint()
		const { isPhone, isBelowDesktop, isShort } = useBreakpoint()
		expect(isPhone.value).toBe(false)
		expect(isBelowDesktop.value).toBe(false)
		expect(isShort.value).toBe(false)
	})
})
