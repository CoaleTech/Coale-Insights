import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * Guards the one thing a broken theme composable can silently get wrong: an
 * explicit user choice must survive a reload, an unset choice must follow the
 * OS preference live, and either way `<html data-theme>` must always match
 * what `useTheme().theme` reports — that attribute, not the ref, is what
 * every CSS custom property in `index.css` actually keys off.
 */

type Listener = (e: MediaQueryListEvent) => void

function stubMatchMedia(matches: boolean) {
	const listeners: Listener[] = []
	const mql = {
		matches,
		media: '(prefers-color-scheme: dark)',
		addEventListener: vi.fn((_: string, fn: Listener) => listeners.push(fn)),
		removeEventListener: vi.fn(),
	}
	vi.stubGlobal(
		'matchMedia',
		vi.fn(() => mql),
	)
	return {
		emit(next: boolean) {
			mql.matches = next
			listeners.forEach((fn) => fn({ matches: next } as MediaQueryListEvent))
		},
	}
}

/** Each test needs a fresh module instance: theme state is a module-level
 *  singleton, and it reads localStorage/matchMedia once at import time. */
async function freshUseTheme() {
	vi.resetModules()
	const mod = await import('./useTheme')
	return mod.useTheme
}

describe('useTheme', () => {
	beforeEach(() => {
		vi.unstubAllGlobals()
		localStorage.clear()
		document.documentElement.removeAttribute('data-theme')
	})

	it('follows the OS preference when nothing is stored', async () => {
		stubMatchMedia(true)
		const useTheme = await freshUseTheme()
		expect(useTheme().theme.value).toBe('dark')
		expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
	})

	it('defaults to light when the OS has no dark preference', async () => {
		stubMatchMedia(false)
		const useTheme = await freshUseTheme()
		expect(useTheme().theme.value).toBe('light')
		expect(document.documentElement.getAttribute('data-theme')).toBe('light')
	})

	it('an explicit choice overrides the OS preference and persists', async () => {
		stubMatchMedia(true)
		const useTheme = await freshUseTheme()
		const { setTheme } = useTheme()
		setTheme('light')
		expect(useTheme().theme.value).toBe('light')
		expect(document.documentElement.getAttribute('data-theme')).toBe('light')
		expect(localStorage.getItem('insights:theme')).toBe('light')
	})

	it('a stored explicit choice survives a fresh module load', async () => {
		localStorage.setItem('insights:theme', 'dark')
		stubMatchMedia(false)
		const useTheme = await freshUseTheme()
		expect(useTheme().theme.value).toBe('dark')
	})

	it('toggleTheme flips and pins the opposite mode', async () => {
		stubMatchMedia(false)
		const useTheme = await freshUseTheme()
		const { theme, toggleTheme } = useTheme()
		expect(theme.value).toBe('light')
		toggleTheme()
		expect(theme.value).toBe('dark')
		toggleTheme()
		expect(theme.value).toBe('light')
	})

	it('tracks a live OS preference change while unset', async () => {
		const media = stubMatchMedia(false)
		const useTheme = await freshUseTheme()
		expect(useTheme().theme.value).toBe('light')
		media.emit(true)
		expect(useTheme().theme.value).toBe('dark')
		expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
	})

	it('ignores a live OS preference change once an explicit choice is set', async () => {
		const media = stubMatchMedia(false)
		const useTheme = await freshUseTheme()
		useTheme().setTheme('light')
		media.emit(true)
		expect(useTheme().theme.value).toBe('light')
	})

	it('degrades to light when matchMedia is unavailable', async () => {
		vi.stubGlobal('matchMedia', undefined)
		const useTheme = await freshUseTheme()
		expect(useTheme().theme.value).toBe('light')
	})
})
