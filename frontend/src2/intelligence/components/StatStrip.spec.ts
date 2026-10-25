import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import StatStrip, { type StatItem } from './StatStrip.vue'

const mountIt = (items: StatItem[]) => mount(StatStrip, { props: { items, currency: 'INR' } })

describe('StatStrip', () => {
  it('formats money exactly with the payload currency', () => {
    expect(mountIt([{ label: 'Total AR', amount: 316871197 }]).text()).toContain('₹316,871,197')
  })

  it('shows a dash, never zero, for a missing figure', () => {
    const t = mountIt([
      { label: 'Runway', amount: null },
      { label: 'Rate', percent: null },
    ]).text()
    expect(t).not.toMatch(/₹0|0\.0%/)
    expect(t.match(/-/g)?.length).toBeGreaterThanOrEqual(2)
  })

  it('formats percent and appends unit to plain values', () => {
    const t = mountIt([
      { label: 'DSO', value: 42, unit: ' days' },
      { label: 'Match', percent: 91.25 },
    ]).text()
    expect(t).toContain('42 days')
    expect(t).toContain('91.3%')
  })

  it('renders one labelled cell per item', () => {
    expect(
      mountIt([
        { label: 'A', value: 1 },
        { label: 'B', value: 2 },
      ]).findAll('dt'),
    ).toHaveLength(2)
  })
})
