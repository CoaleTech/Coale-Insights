import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useDrillDown } from './useDrillDown'

// Mock frappe-ui call
vi.mock('frappe-ui', () => ({
  call: vi.fn(),
}))

import { call } from 'frappe-ui'
const mockCall = call as ReturnType<typeof vi.fn>

describe('useDrillDown', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  it('starts with closed, non-loading state', () => {
    const dd = useDrillDown()
    expect(dd.show.value).toBe(false)
    expect(dd.loading.value).toBe(false)
    expect(dd.error.value).toBeNull()
    expect(dd.rows.value).toEqual([])
    expect(dd.total.value).toBe(0)
    expect(dd.page.value).toBe(1)
  })

  it('open() shows modal immediately and sets loading', async () => {
    mockCall.mockResolvedValue({ columns: [], rows: [], total: 0 })
    const dd = useDrillDown()
    dd.open('method', 'Title', { metric: 'total' })
    // modal opens immediately, before debounce fires
    expect(dd.show.value).toBe(true)
    expect(dd.loading.value).toBe(true)
    // run debounce + async fetch
    vi.runAllTimers()
    await Promise.resolve()
    await Promise.resolve()
    expect(dd.loading.value).toBe(false)
  })

  it('open() populates columns, rows, total on success', async () => {
    const mockResult = {
      columns: [{ label: 'Name', fieldname: 'name', fieldtype: 'Data' }],
      rows: [{ name: 'EMP-001' }],
      total: 1,
    }
    mockCall.mockResolvedValue(mockResult)
    const dd = useDrillDown()
    dd.open('method', 'Title', { metric: 'total' })
    vi.runAllTimers()
    await Promise.resolve()
    await Promise.resolve()
    expect(dd.columns.value).toEqual(mockResult.columns)
    expect(dd.rows.value).toEqual(mockResult.rows)
    expect(dd.total.value).toBe(1)
  })

  it('open() resets page to 1', async () => {
    mockCall.mockResolvedValue({ columns: [], rows: [], total: 200 })
    const dd = useDrillDown()
    // simulate being on page 3
    dd.open('method', 'Title', { metric: 'a' })
    vi.runAllTimers()
    await Promise.resolve(); await Promise.resolve()
    // manually advance to page 3
    dd.nextPage(); vi.runAllTimers(); await Promise.resolve(); await Promise.resolve()
    dd.nextPage(); vi.runAllTimers(); await Promise.resolve(); await Promise.resolve()
    expect(dd.page.value).toBe(3)
    // open with different metric — must reset to page 1
    dd.open('method', 'New Title', { metric: 'b' })
    vi.runAllTimers()
    await Promise.resolve(); await Promise.resolve()
    expect(dd.page.value).toBe(1)
  })

  it('open() maps PermissionError correctly', async () => {
    const err: any = new Error('PermissionError: not permitted')
    err.exc_type = 'PermissionError'
    err.status = 403
    err.messages = ['You do not have permission']
    mockCall.mockRejectedValue(err)
    const dd = useDrillDown()
    dd.open('method', 'Title', { metric: 'total' })
    vi.runAllTimers()
    await Promise.resolve(); await Promise.resolve()
    expect(dd.isPermissionError.value).toBe(true)
    expect(dd.error.value).toBe('You do not have permission')
    expect(dd.loading.value).toBe(false)
  })

  it('open() maps generic errors correctly', async () => {
    const err: any = new Error('Server Error')
    err.exc_type = 'ValidationError'
    err.messages = ['Unknown metric']
    mockCall.mockRejectedValue(err)
    const dd = useDrillDown()
    dd.open('method', 'Title', { metric: 'bad' })
    vi.runAllTimers()
    await Promise.resolve(); await Promise.resolve()
    expect(dd.isPermissionError.value).toBe(false)
    expect(dd.error.value).toBe('Unknown metric')
  })

  it('stale responses are discarded', async () => {
    let resolveFirst!: (v: any) => void
    const firstCall = new Promise(r => { resolveFirst = r })
    const secondResult = { columns: [{ label: 'B', fieldname: 'b', fieldtype: 'Data' }], rows: [{ b: 2 }], total: 2 }
    mockCall
      .mockReturnValueOnce(firstCall)
      .mockResolvedValueOnce(secondResult)
    const dd = useDrillDown()
    dd.open('method', 'First', { metric: 'a' })
    vi.runAllTimers()
    dd.open('method', 'Second', { metric: 'b' })
    vi.runAllTimers()
    await Promise.resolve(); await Promise.resolve()
    resolveFirst({ columns: [], rows: [], total: 99 }) // stale
    await Promise.resolve(); await Promise.resolve()
    // second result wins
    expect(dd.total.value).toBe(2)
    expect(dd.rows.value).toEqual(secondResult.rows)
  })

  it('retry() re-fetches the same endpoint and params', async () => {
    mockCall
      .mockRejectedValueOnce(Object.assign(new Error('err'), { messages: ['fail'] }))
      .mockResolvedValueOnce({ columns: [], rows: [{ name: 'ok' }], total: 1 })
    const dd = useDrillDown()
    dd.open('method', 'Title', { metric: 'total' })
    vi.runAllTimers()
    await Promise.resolve(); await Promise.resolve()
    expect(dd.error.value).toBe('fail')
    dd.retry()
    vi.runAllTimers()
    await Promise.resolve(); await Promise.resolve()
    expect(dd.rows.value).toEqual([{ name: 'ok' }])
    expect(dd.error.value).toBeNull()
  })

  it('nextPage() is a no-op at last page', async () => {
    mockCall.mockResolvedValue({ columns: [], rows: new Array(50).fill({}), total: 50 })
    const dd = useDrillDown()
    dd.open('method', 'T', { metric: 'm' })
    vi.runAllTimers()
    await Promise.resolve(); await Promise.resolve()
    expect(dd.page.value).toBe(1)
    dd.nextPage() // page * 50 === total → no-op
    expect(mockCall).toHaveBeenCalledTimes(1)
  })

  it('close() cancels in-flight request', async () => {
    let resolve!: (v: any) => void
    mockCall.mockReturnValue(new Promise(r => { resolve = r }))
    const dd = useDrillDown()
    dd.open('method', 'T', { metric: 'm' })
    vi.runAllTimers()
    dd.close()
    resolve({ columns: [], rows: [{ name: 'late' }], total: 1 })
    await Promise.resolve(); await Promise.resolve()
    expect(dd.rows.value).toEqual([]) // stale response discarded
    expect(dd.show.value).toBe(false)
  })
})
