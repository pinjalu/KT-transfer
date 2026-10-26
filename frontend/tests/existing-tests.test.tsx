import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ExistingTests } from '../src/pages/ExistingTests'
import type { TestInventory } from '../src/pages/ExistingTests'
import { ApiError, get, post } from '../src/lib/api'
import { ProjectStatus } from '../src/lib/useStatus'
import type { Status } from '../src/lib/types'

vi.mock('../src/lib/api', async original => ({ ...await original<typeof import('../src/lib/api')>(), get: vi.fn(), post: vi.fn() }))
let root: ReturnType<typeof createRoot>, container: HTMLDivElement
let payload: TestInventory
let revision: number
let failure: boolean
async function render() { await act(async () => root.render(<MemoryRouter><ProjectStatus.Provider value={{ data: { knowledge_revision: revision } as Status, error: null, loading: false, reload: vi.fn() }}><ExistingTests /></ProjectStatus.Provider></MemoryRouter>)) }
beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  vi.useFakeTimers(); revision = 1; failure = false
  payload = { available: true, candidate_files: 1, definitions: 1, omitted_files: 0, commit: 'abc123', partial_scan: true,
    note: 'No project code was imported, collected or executed.', files: [{ path: 'tests/test_login.py', url: '/source?path=test_login.py', gaps: [], tests: [{
      name: 'test_rejected_login', line: 3, end: 6, url: '/source?path=test_login.py#L3', description: '<script>not executed</script>',
      framework: 'Python test convention', status: 'definition_not_run', why: 'Documents the expected response.',
      checks: [{ line: 6, end: 6, code: 'assert response.status_code == 401', explanation: 'Checks equality with 401.', url: '/source?path=test_login.py#L6' }],
      markers: [], gaps: ['Helpers may contain additional checks.'],
    }] }] }
  vi.mocked(get).mockReset(); vi.mocked(post).mockReset()
  vi.mocked(get).mockImplementation(async () => { if (failure) throw new ApiError('Source access revoked.', 403); return payload })
  container = document.createElement('div'); document.body.append(container); root = createRoot(container)
})
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.useRealTimers(); vi.unstubAllGlobals() })

it('shows real checks, pinned source links, limits and not-run labels without executing code', async () => {
  await render()
  expect(container.textContent).toContain('Definitions · Not run')
  expect(container.textContent).toContain('Checks equality with 401.')
  expect(container.textContent).toContain('scan is partial')
  expect(container.querySelector('script')).toBeNull()
  expect(container.querySelector('a[href$="#L6"]')).not.toBeNull()
  expect(post).not.toHaveBeenCalled()
})

it('distinguishes unsupported files from a claim that no tests exist', async () => {
  payload.definitions = 0
  payload.files[0].tests = []
  payload.files[0].gaps = ['Only Python assertion explanations are supported.']
  await render()
  expect(container.textContent).toContain('No supported test definitions found')
  expect(container.textContent).toContain('does not mean the project has no tests')
  expect(container.textContent).toContain('Only Python assertion explanations')
})

it('keeps expanded details during refresh and hides them when access fails', async () => {
  await render()
  const detail = container.querySelector('details')!
  detail.open = true
  await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
  expect(container.querySelector('details')?.open).toBe(true)
  failure = true
  await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
  expect(container.textContent).toContain('Source access revoked.')
  expect(container.textContent).not.toContain('test_rejected_login')
})

it('drops the previous source revision while waiting for replacement data', async () => {
  await render()
  vi.mocked(get).mockImplementation(() => new Promise(() => {}))
  revision = 2
  await render()
  expect(container.textContent).not.toContain('test_rejected_login')
  expect(container.textContent).toContain('Reading test definitions')
})

it('filters by test name without another API request', async () => {
  await render()
  const input = container.querySelector('input')!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, 'missing'); input.dispatchEvent(new Event('input', { bubbles: true })) })
  expect(container.textContent).toContain('No matching tests or files')
  expect(get).toHaveBeenCalledTimes(1)
})
