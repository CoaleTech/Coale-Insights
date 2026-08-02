import { describe, expect, it } from 'vitest'
import { groupButtons, useGroupedTabs, type GroupedTab } from './useGroupedTabs'

/**
 * Finance and Revenue shipped fourteen and thirteen peer tabs in one flat strip
 * while already declaring a `group` on every tab. Promoting the group to a
 * control is what this covers. The risks worth pinning are that no tab becomes
 * unreachable, and that a group switch never silently moves the selection into
 * the group the user just left.
 */

type FinanceGroup = 'actuals' | 'planning'

const FINANCE_GROUPS: readonly FinanceGroup[] = ['actuals', 'planning']

/** The real Finance tab table, copied from `FinancialIntelligence.vue`. */
const FINANCE: GroupedTab<FinanceGroup>[] = [
	{ id: 'overview', label: 'Overview', group: 'actuals' },
	{ id: 'cashflow', label: 'Cash', group: 'actuals' },
	{ id: 'receivables', label: 'Receivables', group: 'actuals' },
	{ id: 'payables', label: 'Payables', group: 'actuals' },
	{ id: 'working', label: 'Working Capital', group: 'actuals' },
	{ id: 'ratios', label: 'Ratios & Trends', group: 'actuals' },
	{ id: 'forex', label: 'Forex Exposure', group: 'actuals' },
	{ id: 'cashforecast', label: 'Cash Forecast', group: 'planning' },
	{ id: 'cashflow13', label: '13-Week Cash Flow', group: 'planning' },
	{ id: 'capital', label: 'Capital Planning', group: 'planning' },
	{ id: 'scenarios', label: 'Scenario Analysis', group: 'planning' },
	{ id: 'comparison', label: 'Period Comparison', group: 'planning' },
	{ id: 'budget', label: 'Budget Variance', group: 'planning' },
	{ id: 'beOverview', label: 'Break-Even Overview', group: 'planning' },
]

describe('useGroupedTabs', () => {
	it('shows one group at a time instead of fourteen peers in a row', () => {
		const nav = useGroupedTabs(FINANCE, FINANCE_GROUPS)
		expect(FINANCE).toHaveLength(14)
		expect(nav.groupTabs.value).toHaveLength(7)
		expect(nav.tabItems.value).toHaveLength(7)
		nav.activeGroup.value = 'planning'
		expect(nav.groupTabs.value).toHaveLength(7)
	})

	it('opens on the first group, not on whatever was last in the array', () => {
		const nav = useGroupedTabs(FINANCE, FINANCE_GROUPS)
		expect(nav.activeGroup.value).toBe('actuals')
		expect(nav.activeTab.value.id).toBe('overview')
	})

	it('leaves every tab reachable', () => {
		// Guards a tab whose group is renamed or misspelled: it would vanish from
		// every strip rather than raise anything.
		const nav = useGroupedTabs(FINANCE, FINANCE_GROUPS)
		const reachable = new Set<string>()
		for (const group of FINANCE_GROUPS) {
			nav.activeGroup.value = group
			for (let i = 0; i < nav.groupTabs.value.length; i++) {
				nav.activeTabIndex.value = i
				reachable.add(nav.activeTab.value.id)
			}
		}
		expect(reachable.size).toBe(FINANCE.length)
		for (const tab of FINANCE) expect(reachable.has(tab.id), `${tab.id} unreachable`).toBe(true)
	})

	it('remembers position per group so a switch back is not a reset', () => {
		const nav = useGroupedTabs(FINANCE, FINANCE_GROUPS)
		nav.activeTabIndex.value = 6
		expect(nav.activeTab.value.id).toBe('forex')

		nav.activeGroup.value = 'planning'
		expect(nav.activeTab.value.id).toBe('cashforecast')
		nav.activeTabIndex.value = 1
		expect(nav.activeTab.value.id).toBe('cashflow13')

		nav.activeGroup.value = 'actuals'
		expect(nav.activeTab.value.id, 'Actuals should land where it left').toBe('forex')
		nav.activeGroup.value = 'planning'
		expect(nav.activeTab.value.id, 'Planning should keep its own last tab').toBe('cashflow13')
	})

	it('never resolves to a tab from the other group', () => {
		// The bug this guards: an index carried across a switch that indexes the
		// full list, so selecting Planning renders an Actuals panel.
		const nav = useGroupedTabs(FINANCE, FINANCE_GROUPS)
		for (const group of ['planning', 'actuals', 'planning'] as FinanceGroup[]) {
			nav.activeGroup.value = group
			for (let i = 0; i < 7; i++) {
				nav.activeTabIndex.value = i
				expect(nav.activeTab.value.group).toBe(group)
			}
		}
	})

	it('falls back to the group first tab rather than rendering nothing', () => {
		const nav = useGroupedTabs(FINANCE, FINANCE_GROUPS)
		nav.activeTabIndex.value = 99
		expect(nav.activeTab.value.id).toBe('overview')
		expect(nav.activeTab.value.group).toBe('actuals')
	})

	it('holds for the Revenue and Customers split', () => {
		type RevGroup = 'revenue' | 'customers'
		const groups: readonly RevGroup[] = ['revenue', 'customers']
		const defs: GroupedTab<RevGroup>[] = [
			{ id: 'rev-overview', label: 'Revenue Overview', group: 'revenue' },
			{ id: 'rev-payment', label: 'Cash vs Credit', group: 'revenue' },
			{ id: 'cust-overview', label: 'Customer Overview', group: 'customers' },
			{ id: 'cust-list', label: 'Customers', group: 'customers' },
			{ id: 'cust-cohorts', label: 'Cohorts', group: 'customers' },
		]
		const nav = useGroupedTabs(defs, groups)
		expect(nav.groupTabs.value.map((t) => t.id)).toEqual(['rev-overview', 'rev-payment'])
		nav.activeGroup.value = 'customers'
		expect(nav.groupTabs.value).toHaveLength(3)
		nav.activeTabIndex.value = 2
		expect(nav.activeTab.value.id).toBe('cust-cohorts')
		nav.activeGroup.value = 'revenue'
		expect(nav.activeTab.value.id).toBe('rev-overview')
	})
})

describe('groupButtons', () => {
	it('title-cases the group key for the control label', () => {
		expect(groupButtons(FINANCE_GROUPS)).toEqual([
			{ label: 'Actuals', value: 'actuals' },
			{ label: 'Planning', value: 'planning' },
		])
	})

	it('preserves group order, which is the order the control renders', () => {
		expect(groupButtons(['planning', 'actuals'] as const).map((b) => b.value)).toEqual(['planning', 'actuals'])
	})

	it('accepts an override where the key is not what a reader should see', () => {
		expect(groupButtons(['customers'] as const, { customers: 'Customer base' })[0].label).toBe('Customer base')
	})
})
