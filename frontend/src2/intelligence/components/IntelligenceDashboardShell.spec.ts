import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import IntelligenceDashboardShell from './IntelligenceDashboardShell.vue'

/**
 * Manufacturing, ESG and HR each carried their own copy of this state machine:
 * three byte-identical permission blocks, three structurally identical error
 * blocks, and a first-load skeleton identical in two of them.
 *
 * These assertions pin the two things consolidation was supposed to buy -- a
 * failure never hides behind a spinner, and the permission state tells the reader
 * what to ask for -- plus the precedence order, which is the part a future edit
 * is most likely to get wrong.
 */
const CONTENT = '<p>real content</p>'

function shell(props: Record<string, unknown>) {
	return mount(IntelligenceDashboardShell, {
		props: { subject: 'manufacturing data', ...props },
		slots: { default: CONTENT },
	})
}

describe('IntelligenceDashboardShell', () => {
	it('renders content only when there is a payload', () => {
		expect(shell({ hasData: true }).text()).toContain('real content')
	})

	it('states what access to ask for, not just that access is missing', () => {
		// The three copies this replaces said "You do not have permission" and
		// stopped, leaving the reader with no next step.
		const w = shell({
			isPermissionError: true,
			permissionHint: 'Ask an administrator for Work Order read access.',
		})
		expect(w.text()).toContain('Access restricted')
		expect(w.text()).toContain('permission to view manufacturing data')
		expect(w.text()).toContain('Ask an administrator for Work Order read access.')
		expect(w.text()).not.toContain('real content')
	})

	it('puts a failure above the skeleton, never behind it', () => {
		// `loading` is first-load only, so these are mutually exclusive today. The
		// ordering is asserted so a change to that definition cannot bury an error.
		const w = shell({ loading: true, error: 'Server exploded' })
		expect(w.text()).toContain('Server exploded')
		expect(w.find('.skeleton-block').exists()).toBe(false)
	})

	it('ranks a permission failure above a generic one', () => {
		// Both flags are set together by the composable's `onError`, and "no access"
		// is the more actionable of the two messages.
		const w = shell({ error: 'PermissionError: not allowed', isPermissionError: true })
		expect(w.text()).toContain('Access restricted')
		expect(w.text()).not.toContain('Could not load')
	})

	it('offers a retry on failure and reports it upward', async () => {
		const w = shell({ error: 'Timed out' })
		await w.find('button').trigger('click')
		expect(w.emitted('retry')).toHaveLength(1)
	})

	it('shows retry progress rather than looking inert on a second attempt', () => {
		// `retry()` sets `refreshing`, so the button must reflect it; otherwise a
		// slow retry reads as a dead control and gets clicked repeatedly. Asserted
		// against the idle case too, so this cannot pass by matching markup that is
		// present either way.
		const idle = shell({ error: 'Timed out', refreshing: false })
		const busy = shell({ error: 'Timed out', refreshing: true })
		expect(idle.find('button').attributes('disabled')).toBeUndefined()
		expect(busy.find('button').attributes('disabled')).toBeDefined()
	})

	it('never shows content while loading, errored, or unpopulated', () => {
		for (const props of [
			{ loading: true },
			{ error: 'boom' },
			{ isPermissionError: true },
			{},
			// The retry window: error cleared, payload not yet arrived. `hasData`
			// requires a payload precisely so this cannot render over empty refs.
			{ hasData: false, refreshing: true },
		]) {
			expect(shell(props).text(), JSON.stringify(props)).not.toContain('real content')
		}
	})

	it('falls back to an explicit empty state rather than a blank panel', () => {
		expect(shell({}).text()).toContain('No data available')
	})

	it('lets a dashboard describe its own first screen', () => {
		const w = mount(IntelligenceDashboardShell, {
			props: { subject: 'HR data', loading: true },
			slots: { default: CONTENT, skeleton: '<div class="four-up">four</div>' },
		})
		expect(w.find('.four-up').exists()).toBe(true)
	})
})
