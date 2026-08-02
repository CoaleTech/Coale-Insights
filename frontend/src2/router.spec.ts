import { describe, expect, it } from 'vitest'
import { INTELLIGENCE_DASHBOARDS } from './helpers/dashboards'

/**
 * Regression lock for navigation reachability, not coverage.
 *
 * Three defects this pins:
 *
 * 1. `ExecutiveDashboard.vue` pushed `/executive-reports` from two buttons while
 *    no such route existed, so both landed on the catch-all NotFound.
 * 2. `CrossDashboardSearch.vue` had no route and no importer at all: 1,376 lines
 *    of a fully backed feature that no URL could reach.
 * 3. Every dashboard in the registry must stay routable. A registry entry whose
 *    route was renamed or dropped would leave a sidebar link pointing at nothing.
 *
 * Asserted against the route table rather than a running browser so it fails in
 * CI instead of during a manual click-through.
 */

// Imported lazily: router.ts pulls in `@/router.ts`-style aliases and a session
// guard, so the table is read from the module's default export directly.
const { default: router } = await import('./router')

function routeNames(): string[] {
	return router.getRoutes().map((r) => r.name as string).filter(Boolean)
}

function pathFor(name: string): string | undefined {
	return router.getRoutes().find((r) => r.name === name)?.path
}

describe('router', () => {
	it('routes /executive-reports, which two Executive buttons already navigate to', () => {
		expect(routeNames()).toContain('ExecutiveReports')
		expect(pathFor('ExecutiveReports')).toBe('/executive-reports')
	})

	it('routes the cross-dashboard search that was previously unreachable', () => {
		expect(routeNames()).toContain('CrossDashboardSearch')
		expect(pathFor('CrossDashboardSearch')).toBe('/search')
	})

	it('keeps every registered dashboard routable', () => {
		const names = routeNames()
		for (const d of INTELLIGENCE_DASHBOARDS) {
			expect(names, `${d.id} -> ${d.route}`).toContain(d.route)
		}
	})

	it('still redirects the legacy paths left behind by the two merges', () => {
		// These keep old bookmarks and cross-dashboard links alive.
		for (const legacy of [
			'/sales-intelligence',
			'/customer-intelligence',
			'/customer-360',
			'/strategic-finance-intelligence',
			'/budget-variance-intelligence',
		]) {
			const resolved = router.resolve(legacy)
			expect(resolved.matched.length, `${legacy} should resolve`).toBeGreaterThan(0)
		}
	})
})
