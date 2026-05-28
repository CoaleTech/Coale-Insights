import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import IntelligenceDrillDown from './IntelligenceDrillDown.vue'

// Stub globally-registered frappe-ui components
const stubs = {
  Dialog: {
    template: '<div><slot name="body-content" /></div>',
    props: ['modelValue', 'options'],
  },
  LoadingIndicator: { template: '<div data-testid="spinner" />' },
  Button: { template: '<button @click="$emit(\'click\')" :disabled="$props.disabled"><slot /></button>', emits: ['click'], props: ['disabled', 'variant', 'size'] },
}

const baseProps = {
  show: true,
  title: 'Test',
  columns: [{ label: 'Name', fieldname: 'name', fieldtype: 'Data' as const }],
  rows: [{ name: 'EMP-001' }],
  loading: false,
  error: null,
  isPermissionError: false,
  total: 1,
  page: 1,
}

describe('IntelligenceDrillDown', () => {
  it('shows loading spinner when loading=true', () => {
    const wrapper = mount(IntelligenceDrillDown, {
      global: { stubs },
      props: { ...baseProps, loading: true, rows: [] },
    })
    expect(wrapper.find('[data-testid="spinner"]').exists()).toBe(true)
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('shows no-permission message when isPermissionError=true', () => {
    const wrapper = mount(IntelligenceDrillDown, {
      global: { stubs },
      props: { ...baseProps, isPermissionError: true, error: 'err', loading: false, rows: [] },
    })
    expect(wrapper.text()).toContain("don't have permission")
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('shows error banner with retry button when error is set', async () => {
    const wrapper = mount(IntelligenceDrillDown, {
      global: { stubs },
      props: { ...baseProps, error: 'Something went wrong', loading: false, rows: [] },
    })
    expect(wrapper.text()).toContain('Something went wrong')
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toBeTruthy()
  })

  it('shows empty state when rows is empty and no error', () => {
    const wrapper = mount(IntelligenceDrillDown, {
      global: { stubs },
      props: { ...baseProps, rows: [], total: 0 },
    })
    expect(wrapper.text()).toContain('No records found')
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('renders data table with rows in success state', () => {
    const wrapper = mount(IntelligenceDrillDown, { global: { stubs }, props: baseProps })
    expect(wrapper.find('table').exists()).toBe(true)
    expect(wrapper.find('tbody tr').exists()).toBe(true)
    expect(wrapper.text()).toContain('EMP-001')
  })

  it('renders Link fieldtype columns as ERPNext links', () => {
    const wrapper = mount(IntelligenceDrillDown, {
      global: { stubs },
      props: {
        ...baseProps,
        columns: [{ label: 'Employee', fieldname: 'name', fieldtype: 'Link' as const, options: 'Employee' }],
        rows: [{ name: 'HR-EMP-00001' }],
      },
    })
    const link = wrapper.find('a')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toContain('/app/employee/HR-EMP-00001')
    expect(link.attributes('target')).toBe('_blank')
  })

  it('Link href handles multi-word DocType with spaces', () => {
    const wrapper = mount(IntelligenceDrillDown, {
      global: { stubs },
      props: {
        ...baseProps,
        columns: [{ label: 'Invoice', fieldname: 'name', fieldtype: 'Link' as const, options: 'Sales Invoice' }],
        rows: [{ name: 'SINV-001' }],
      },
    })
    const href = wrapper.find('a').attributes('href')
    expect(href).toContain('/app/sales-invoice/SINV-001')
  })

  it('Prev button is disabled on page 1', () => {
    const wrapper = mount(IntelligenceDrillDown, { global: { stubs }, props: { ...baseProps, page: 1, total: 100 } })
    const buttons = wrapper.findAll('button')
    const prevBtn = buttons[0]
    expect(prevBtn.attributes('disabled')).toBeDefined()
  })

  it('Next button is disabled on last page', () => {
    const wrapper = mount(IntelligenceDrillDown, { global: { stubs }, props: { ...baseProps, page: 1, total: 50 } })
    const buttons = wrapper.findAll('button')
    const nextBtn = buttons[buttons.length - 1]
    expect(nextBtn.attributes('disabled')).toBeDefined()
  })

  it('shows correct Showing X-Y of Z text', () => {
    const wrapper = mount(IntelligenceDrillDown, {
      global: { stubs },
      props: { ...baseProps, page: 2, total: 234, rows: new Array(50).fill({ name: 'x' }) },
    })
    expect(wrapper.text()).toContain('Showing 51–100 of 234 records')
  })
})
