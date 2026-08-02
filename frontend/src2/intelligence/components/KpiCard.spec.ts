import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const isPhone = ref(false)
vi.mock('../../composables/useBreakpoint', () => ({
	useBreakpoint: () => ({
		isPhone,
		isBelowDesktop: ref(false),
		isShort: ref(false),
	}),
}))

// Imported after the mock so the component picks up the stubbed composable.
const { default: KpiCard } = await import('./KpiCard.vue')

/**
 * The KPI card carries every headline figure on all 21 dashboards, so its two
 * contracts are load-bearing:
 *
 * 1. `min-w-0` on the root. Grid items default to `min-width: auto` and refuse to
 *    shrink below their content, so an unbreakable ₹316,871,197 at text-2xl burst
 *    out of its track and visually overlapped the neighbouring card at 768px.
 *    Removing that class silently reintroduces overlapping cards.
 * 2. Compact display never costs precision. Sighted users get a figure that fits;
 *    assistive tech gets the exact one.
 */
describe('KpiCard', () => {
	beforeEach(() => {
		isPhone.value = false
	})

	it('keeps min-w-0 so it cannot overflow its grid track', () => {
		const w = mount(KpiCard, { props: { label: 'Net Profit', value: '1' } })
		expect(w.classes()).toContain('min-w-0')
	})

	it('shows exact money above phone widths', () => {
		const w = mount(KpiCard, {
			props: { label: 'Cash Position', amount: 316871197, currency: 'INR' },
		})
		expect(w.get('[aria-hidden="true"]').text()).toBe('₹316,871,197')
	})

	it('switches to compact money on a phone', () => {
		isPhone.value = true
		const w = mount(KpiCard, {
			props: { label: 'Cash Position', amount: 316871197, currency: 'INR' },
		})
		expect(w.get('[aria-hidden="true"]').text()).toBe('₹316.9M')
	})

	it('still exposes the exact figure to assistive tech when compact', () => {
		isPhone.value = true
		const w = mount(KpiCard, {
			props: { label: 'Cash Position', amount: 316871197, currency: 'INR' },
		})
		expect(w.get('.sr-only').text()).toBe('₹316,871,197')
	})

	it('uses the currency it is handed rather than a built-in default', () => {
		const w = mount(KpiCard, {
			props: { label: 'Payroll', amount: 1500, currency: 'KES' },
		})
		expect(w.get('[aria-hidden="true"]').text()).toBe('KES\u00a01,500')
	})

	it('leaves non-money values alone', () => {
		// Scores, percentages and ratios are pre-formatted by the caller and must
		// not be run through currency formatting.
		isPhone.value = true
		const w = mount(KpiCard, { props: { label: 'Risk Score', value: '70/100' } })
		expect(w.get('[aria-hidden="true"]').text()).toBe('70/100')
		expect(w.get('.sr-only').text()).toBe('70/100')
	})

	it('renders zero as a real figure, not a blank', () => {
		const w = mount(KpiCard, { props: { label: 'Forex', amount: 0, currency: 'INR' } })
		expect(w.get('[aria-hidden="true"]').text()).toBe('₹0')
	})

	it('exposes button semantics only when clickable, without a dynamic root', () => {
		// The root is deliberately always a div. `<component :is="'button'">`
		// resolved to frappe-ui's Button component and wrecked the layout, so the
		// interactive affordance is role + tabindex + key handlers instead.
		const plain = mount(KpiCard, { props: { label: 'A', value: '1' } })
		expect(plain.element.tagName).toBe('DIV')
		expect(plain.attributes('role')).toBeUndefined()
		expect(plain.attributes('tabindex')).toBeUndefined()

		const clickable = mount(KpiCard, { props: { label: 'A', value: '1', clickable: true } })
		expect(clickable.element.tagName).toBe('DIV')
		expect(clickable.attributes('role')).toBe('button')
		expect(clickable.attributes('tabindex')).toBe('0')
	})

	it('activates by keyboard, which a div does not get for free', () => {
		const w = mount(KpiCard, { props: { label: 'A', value: '1', clickable: true } })
		w.trigger('keydown', { key: 'Enter' })
		w.trigger('keydown', { key: ' ' })
		w.trigger('click')
		expect(w.emitted('click')).toHaveLength(3)
	})

	it('hides the value while loading so no false figure is shown', () => {
		// Asserted on rendered text, not a selector: SkeletonBlock is itself
		// aria-hidden, so querying that attribute matches the placeholder too.
		const w = mount(KpiCard, {
			props: { label: 'Cash', amount: 0, currency: 'INR', loading: true },
		})
		expect(w.text()).not.toContain('₹0')
		expect(w.find('.skeleton-block').exists()).toBe(true)
	})

	it('shows an explicit gap instead of a zero when the fetch failed', () => {
		// The defect this guards: the card had only `loading` and data-present, so
		// a rejected fetch left the parent ref empty, `|| 0` took over, and the
		// card stated "₹0" with full confidence. A zero and a failure are
		// opposite facts and must never render alike.
		const w = mount(KpiCard, {
			props: { label: 'Cash', amount: 0, currency: 'INR', error: 'Request failed' },
		})
		expect(w.text()).not.toContain('₹0')
		expect(w.text()).toContain('Unavailable')
	})

	it('carries the failure reason to assistive tech, not just a visual glyph', () => {
		const w = mount(KpiCard, {
			props: { label: 'Cash', amount: 0, currency: 'INR', error: 'Permission denied' },
		})
		expect(w.get('.sr-only').text()).toContain('Permission denied')
	})

	it('suppresses delta and sublabel while errored so no stale context survives', () => {
		// Showing "+8.2% vs last quarter" beside an unavailable figure would imply
		// the comparison still holds. It does not.
		const w = mount(KpiCard, {
			props: {
				label: 'Cash', amount: 0, currency: 'INR',
				delta: 8.2, sublabel: 'vs last quarter', error: 'boom',
			},
		})
		expect(w.text()).not.toContain('8.2')
		expect(w.text()).not.toContain('vs last quarter')
	})

	it('error outranks a present value', () => {
		const w = mount(KpiCard, {
			props: { label: 'DSO', value: '62 days', error: 'stale' },
		})
		expect(w.text()).not.toContain('62 days')
	})

	it('formats a money target in the same notation as the figure', () => {
		// A target rendered exact beneath a compact value ("Target KES 5,000,000"
		// under "KES 4.2M") makes the reader do unit conversion to compare.
		isPhone.value = true
		const w = mount(KpiCard, {
			props: { label: 'Revenue', amount: 4_200_000, currency: 'INR', target: 5_000_000 },
		})
		expect(w.text()).toContain('Target ₹5M')
	})

	it('passes a non-money target through verbatim', () => {
		const w = mount(KpiCard, {
			props: { label: 'Margin', value: '34%', target: '40%' },
		})
		expect(w.text()).toContain('Target 40%')
	})

	it('omits the target row entirely when no target is given', () => {
		const w = mount(KpiCard, { props: { label: 'Margin', value: '34%' } })
		expect(w.text()).not.toContain('Target')
	})

	it('hides the severity badge when errored, since severity came from a fallback', () => {
		// Callers derive severity from `value || 0`, so a failed AR fetch scored
		// `scoreSeverity(0, { good: 30, higherIsBetter: false })` and rendered a
		// green "Low" badge on a card whose value read "Unavailable".
		const w = mount(KpiCard, {
			props: { label: 'Outstanding AR', amount: 0, currency: 'INR', severity: 'low', error: 'boom' },
		})
		expect(w.findComponent({ name: 'Badge' }).exists()).toBe(false)
	})

	it('hides the severity badge while loading for the same reason', () => {
		const w = mount(KpiCard, {
			props: { label: 'Outstanding AR', amount: 0, currency: 'INR', severity: 'low', loading: true },
		})
		expect(w.findComponent({ name: 'Badge' }).exists()).toBe(false)
	})

	it('still shows the badge on a healthy card', () => {
		const w = mount(KpiCard, {
			props: { label: 'Outstanding AR', amount: 5000, currency: 'INR', severity: 'high' },
		})
		expect(w.findComponent({ name: 'Badge' }).exists()).toBe(true)
	})

	it('distinguishes an absent value from a zero', () => {
		// The whole point: callers used to write `x || 0`, so a payload missing
		// `new_hires` reported zero hires. Both facts must remain expressible.
		const absent = mount(KpiCard, { props: { label: 'New Hires' } })
		expect(absent.text()).toContain('-')
		expect(absent.text()).not.toContain('0')

		const zero = mount(KpiCard, { props: { label: 'New Hires', value: 0 } })
		expect(zero.text()).toContain('0')
	})

	it('reports a missing percentage as missing rather than 0.0%', () => {
		// `formatPercent` substitutes 0 for undefined, so pre-formatting at the
		// call site would print "0.0%" for an unmeasured attrition rate.
		const w = mount(KpiCard, { props: { label: 'Attrition Rate', percent: null } })
		expect(w.text()).not.toContain('0.0%')
		expect(w.text()).toContain('-')
	})

	it('formats a present percentage on the 0-100 scale the endpoints return', () => {
		const w = mount(KpiCard, { props: { label: 'Attrition Rate', percent: 12.34 } })
		expect(w.text()).toContain('12.3%')
	})

	it('keeps a zero percentage as a real measurement', () => {
		const w = mount(KpiCard, { props: { label: 'Attrition Rate', percent: 0 } })
		expect(w.text()).toContain('0.0%')
	})

	it('drops the card border in tile variant without losing the figure', () => {
		// A tile is the dense inner readout; it must still route through the same
		// value logic rather than being a bare div that can print `|| 0`.
		const tile = mount(KpiCard, { props: { label: 'Exits', value: 7, variant: 'tile' } })
		expect(tile.text()).toContain('7')
		expect(tile.element.className).not.toContain('border-outline-gray-1')

		const card = mount(KpiCard, { props: { label: 'Exits', value: 7 } })
		expect(card.element.className).toContain('border-outline-gray-1')
	})
})

describe('KpiCard unit', () => {
	it('appends the unit to a present value', () => {
		const w = mount(KpiCard, { props: { label: 'DSO', value: 42, unit: ' days' } })
		expect(w.text()).toContain('42 days')
	})

	it('renders a bare dash for an absent value rather than a unit on nothing', () => {
		// The shape this replaces was `${x || 0} days`, which reported "0 days" for a
		// metric the server never sent. "- days" would be no better.
		const w = mount(KpiCard, { props: { label: 'DSO', unit: ' days' } })
		expect(w.text()).toContain('-')
		expect(w.text()).not.toContain('days')
		expect(w.text()).not.toContain('0')
	})

	it('keeps a real zero with its unit', () => {
		const w = mount(KpiCard, { props: { label: 'DSO', value: 0, unit: ' days' } })
		expect(w.text()).toContain('0 days')
	})

	it('treats an empty string as absent, since that was the old no-data sentinel', () => {
		// Several dashboards passed `hasData ? String(x) : ''`, so an empty string
		// reached the card meaning "nothing yet" and rendered as a blank figure.
		const w = mount(KpiCard, { props: { label: 'Score', value: '' } })
		expect(w.text()).toContain('-')
	})

	it('leaves money and percentages alone, which carry their own notation', () => {
		const money = mount(KpiCard, { props: { label: 'Cash', amount: 5000, currency: 'INR', unit: ' days' } })
		expect(money.text()).not.toContain('days')
		const pct = mount(KpiCard, { props: { label: 'Rate', percent: 12.3, unit: ' days' } })
		expect(pct.text()).toContain('12.3%')
		expect(pct.text()).not.toContain('days')
	})
})

describe('KpiCard delta absence', () => {
	it('treats a null delta as nothing to compare, not as flat', () => {
		// The server withholds `revenue_growth` when the prior-period base is too
		// small for the ratio to mean anything. An earlier `!== undefined` check let
		// `null` through and rendered "0.0%", asserting flat performance -- the
		// opposite of what withholding it was meant to convey.
		const w = mount(KpiCard, { props: { label: 'YTD Revenue', amount: 451855824, currency: 'INR', delta: null } })
		expect(w.text()).not.toContain('0.0%')
		expect(w.text()).not.toContain('%')
	})

	it('still shows a real zero delta, which is a measured flat result', () => {
		const w = mount(KpiCard, { props: { label: 'YTD Revenue', amount: 100, currency: 'INR', delta: 0 } })
		expect(w.text()).toContain('0.0%')
	})

	it('keeps the sublabel when the delta is absent', () => {
		// Naming the comparison base is how a suppressed ratio stays disclosed.
		const w = mount(KpiCard, {
			props: { label: 'YTD Revenue', amount: 1, currency: 'INR', delta: null, sublabel: 'vs ₹27.3M last year' },
		})
		expect(w.text()).toContain('vs ₹27.3M last year')
		expect(w.text()).not.toContain('0.0%')
	})

	it('ignores a NaN delta', () => {
		const w = mount(KpiCard, { props: { label: 'X', value: 1, delta: Number.NaN } })
		expect(w.text()).not.toContain('NaN')
	})
})
