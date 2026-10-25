import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TabBrief from './TabBrief.vue'

describe('TabBrief', () => {
  it('renders the server headline verbatim', () => {
    const w = mount(TabBrief, {
      props: { brief: { severity: 'high', headline: 'AR of ₹1,234 is overdue.' } },
    })
    expect(w.get('h2').text()).toBe('AR of ₹1,234 is overdue.')
  })

  it('renders nothing without a brief, so an old cached payload shows no client-made sentence', () => {
    expect(mount(TabBrief, { props: { brief: undefined } }).html()).toBe('<!--v-if-->')
    expect(mount(TabBrief, { props: { brief: { severity: 'low', headline: '' } } }).html()).toBe(
      '<!--v-if-->',
    )
  })

  it('tints by severity and never uses a side stripe', () => {
    const w = mount(TabBrief, { props: { brief: { severity: 'critical', headline: 'x' } } })
    expect(w.classes()).toContain('bg-surface-red-2')
    expect(w.classes().some((c) => /^border-[lrse]-/.test(c))).toBe(false)
  })

  it('shows as-of when given', () => {
    const w = mount(TabBrief, {
      props: { brief: { severity: 'none', headline: 'x' }, asOf: '2026-10-14' },
    })
    expect(w.text()).toContain('As of 14 Oct 2026')
  })

  it('renders server detail lines verbatim under the headline', () => {
    const w = mount(TabBrief, {
      props: {
        brief: { severity: 'medium', headline: 'x', details: [{ label: 'Impact', text: '₹10 is held.' }] },
      },
    })
    expect(w.get('dl').text()).toContain('Impact: ₹10 is held.')
  })

  it('formats a full timestamp, not the raw ISO string', () => {
    const w = mount(TabBrief, {
      props: { brief: { severity: 'none', headline: 'x' }, asOf: '2026-10-25T07:37:20.270939' },
    })
    expect(w.text()).toContain('25 Oct 2026, 07:37')
    expect(w.text()).not.toContain('T07:37')
  })
})
