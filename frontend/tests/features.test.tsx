import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Features } from '../src/pages/Features'
import { ApiError, get, post } from '../src/lib/api'
import type { Status } from '../src/lib/types'
import type { FeatureDetail, FeatureList } from '../src/lib/features'

vi.mock('../src/lib/api', async original => ({
  ...await original<typeof import('../src/lib/api')>(), get: vi.fn(), post: vi.fn(),
}))

let status: Status
let list: FeatureList
let body: FeatureDetail
let failList = false
let failDetail = false
let container: HTMLDivElement
let root: ReturnType<typeof createRoot>
const file = { path: 'app.py', line: 4, url: 'https://github.com/acme/shop/blob/abc/app.py#L4' }
async function render(path = '/features') { await act(async () => root.render(<MemoryRouter initialEntries={[path]}><Features /></MemoryRouter>)) }
function button(label: string) {
  const found = Array.from(container.querySelectorAll('button')).find(el => el.textContent?.trim() === label)
  if (!found) throw new Error(`Button missing: ${label}`)
  return found
}
async function click(label: string) { await act(async () => button(label).click()) }
function panel() { return container.querySelector('#feature-panel')! }

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  status = { knowledge_revision: 1, awaiting_project: false, ready: true,
    settings: { repo: 'acme/shop', branch: 'main', platforms: ['github'] },
    scan: { id: 1, repo: 'acme/shop', branch: 'main', commit: 'abcdefg', status: 'complete' } } as Status
  list = { available: true, repo: 'acme/shop', branch: 'main', scan_id: 1, knowledge_revision: 1, commit: 'abcdefg', features: ['orders', 'users'].map(id => ({
    id, name: id === 'orders' ? 'Orders' : 'Users', plain: '', ticket_name: '',
    route_count: 1, file_count: 1, issue_count: 1, gap_count: 1, has_tests: true,
  })), unclustered: { files: 0, routes: 0, note: 'A feature starts at a route.' } }
  body = { id: 'orders', name: 'Orders', ticket_name: '', repo: 'acme/shop', branch: 'main', scan_id: 1,
    knowledge_revision: 1, commit: 'abcdefg',
    flow: { title: 'Static code map for Orders.', steps: [{ n: 1, label: 'POST /orders', plain: 'Route declaration.', component: { ...file, name: 'app.py', kind: 'route' } }] },
    apis_and_data: { routes: [{ method: 'POST', path: '/orders', declared_at: file }], tables: [], services: [] },
    tests: { existing: [{ ...file, name: 'test_orders.py', covers: 'Imports app.py' }] },
    known_problems: { items: [], note: 'No monitoring is connected.' },
    related: [{ ...file, name: 'app.py', kind: 'file' }],
    issues: [{ ...file, key: 'SHOP-1', summary: 'Request orders', confidence: 'possible' }],
    gaps: [{ what: 'Missing store evidence', checked: 'Related files', why_missing: 'No declarations.' }],
  }
  failList = false; failDetail = false
  vi.mocked(get).mockReset(); vi.mocked(post).mockReset()
  vi.mocked(get).mockImplementation(async path => {
    if (path === '/api/status') return status
    if (path === '/api/features') {
      if (failList) throw new ApiError('Source access was revoked.', 403)
      return list
    }
    if (path.startsWith('/api/features/')) {
      if (failDetail) throw new ApiError('Feature access was revoked.', 403)
      return path.endsWith('/users') ? { ...body, id: 'users', name: 'Users' } : body
    }
    throw new Error(`Unexpected path: ${path}`)
  })
  container = document.createElement('div'); document.body.append(container); root = createRoot(container)
})
afterEach(async () => {
  await act(async () => root.unmount()); container.remove()
  vi.useRealTimers(); vi.unstubAllGlobals()
})

it('opens a deep-linked feature and changes tabs without generating or rereading data', async () => {
  await render('/features?feature=users')
  expect(container.querySelector('.feature-hero h2')?.textContent).toBe('Users')
  await click('Code flow')
  expect(panel().textContent).toContain('does not represent an observed request')
  expect(panel().querySelector('a')?.getAttribute('href')).toBe(file.url)
  await click('APIs and data')
  expect(panel().textContent).toContain('/orders')
  await click('Tests')
  expect(panel().textContent).toContain('not been executed here')
  await click('Known problems')
  expect(panel().textContent).toContain('not confirmed defects')
  expect(panel().querySelector('summary')?.textContent).toContain('Missing store evidence')
  expect(get).toHaveBeenCalledTimes(3)
  expect(post).not.toHaveBeenCalled()
})

it('returns to Admin instantly without requesting its details again', async () => {
  list = { ...list, features: [{ ...list.features[0], id: 'admin', name: 'Admin' }, list.features[1]] }
  body = { ...body, id: 'admin', name: 'Admin' }
  await render('/features?feature=admin')
  expect(container.querySelector('.feature-hero h2')?.textContent).toBe('Admin')
  const pick = async (name: string) => act(async () => {
    const target = Array.from(container.querySelectorAll<HTMLButtonElement>('.feature-list > button'))
      .find(item => item.querySelector('.feature-list-name')?.textContent?.includes(name))
    if (!target) throw new Error(`Feature missing: ${name}`)
    target.click()
  })
  await pick('Users')
  expect(container.querySelector('.feature-hero h2')?.textContent).toBe('Users')
  await pick('Admin')
  expect(container.querySelector('.feature-hero h2')?.textContent).toBe('Admin')
  expect(container.textContent).not.toContain('Checking source access and reading the saved scan')
  expect(vi.mocked(get).mock.calls.filter(([path]) => path === '/api/features/admin')).toHaveLength(1)
  await click('Refresh feature')
  expect(vi.mocked(get).mock.calls.filter(([path]) => path === '/api/features/admin')).toHaveLength(2)
})

it('searches feature names and recovers from no matches', async () => {
  await render()
  const input = container.querySelector<HTMLInputElement>('input[type=search]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, 'nothing')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  expect(container.querySelectorAll('.feature-list > button')).toHaveLength(0)
  expect(container.textContent).toContain('No matching features')
  await click('Clear search')
  expect(container.querySelectorAll('.feature-list > button')).toHaveLength(2)
})

it('hides old feature lists and details as soon as a file read is queued', async () => {
  await render()
  expect(container.querySelector('.feature-hero h2')?.textContent).toBe('Orders')
  status = { ...status, busy: true, job: { id: 5, kind: 'scan', state: 'queued' } as Status['job'] }
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(container.querySelector('.feature-list')).toBeNull()
  expect(container.querySelector('.feature-detail')).toBeNull()
  expect(container.textContent).toContain('Finding features in this project')
  status = { ...status, busy: false, job: { ...status.job!, state: 'succeeded' } }
  list = { ...list, features: [] }
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(container.textContent).toContain('No route-based features were found')
  expect(container.textContent).not.toContain('Orders')
})

it('rejects details from another project instead of showing the same-named old feature', async () => {
  body.repo = 'acme/old-project'
  await render()
  expect(container.querySelector('.feature-detail')).toBeNull()
  expect(container.querySelector('[role="alert"]')?.textContent).toContain('do not match the current project')
})

it('ignores a slow old feature list after switching project without changing the revision number', async () => {
  const oldList = list
  let finishOld!: (value: FeatureList) => void
  const normal = vi.mocked(get).getMockImplementation()!
  let first = true
  vi.mocked(get).mockImplementation((path, signal) => {
    if (path === '/api/features' && first) {
      first = false
      return new Promise(resolve => { finishOld = resolve })
    }
    return normal(path, signal)
  })
  await render()
  status = { ...status, settings: { ...status.settings!, repo: 'acme/new-project' },
    scan: { ...status.scan!, repo: 'acme/new-project' } }
  list = { ...list, repo: 'acme/new-project', features: [] }
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(container.textContent).toContain('No route-based features were found')
  await act(async () => finishOld(oldList))
  expect(container.textContent).not.toContain('Orders')
  expect(container.querySelector('.feature-list')).toBeNull()
})

it('supports keyboard tabs and preserves the view across background reads', async () => {
  await render()
  await act(async () => button('Overview').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })))
  expect(document.activeElement).toBe(button('Code flow'))
  expect(button('Code flow').getAttribute('aria-selected')).toBe('true')
  await click('Refresh feature')
  expect(button('Code flow').getAttribute('aria-selected')).toBe('true')
  expect(post).not.toHaveBeenCalled()
})

it('distinguishes possible Jira matches and preserves local source links', async () => {
  const local = { ...file, path: `local://${'a'.repeat(64)}/app.py`, url: '/source?snapshot=abc&path=app.py#L4', name: 'app.py', kind: 'file' }
  body.related = [local]
  await render()
  expect(panel().textContent).toContain('Possible, needs checking')
  expect(panel().querySelector('a[href="/jira?issue=SHOP-1"]')).not.toBeNull()
  expect(panel().querySelector('a')?.getAttribute('href')).toBe(local.url)
  expect(panel().textContent).toContain('Local folder / app.py:4')
})

it('shows source failures and discards protected details after access is revoked', async () => {
  await render()
  failDetail = true
  await click('Refresh feature')
  expect(container.textContent).toContain('Feature access was revoked.')
  expect(container.querySelector('.feature-hero')).toBeNull()
  failList = true
  await click('Refresh features')
  expect(container.textContent).toContain('Source access was revoked.')
  expect(container.querySelector('.feature-list')).toBeNull()
  expect(container.textContent).not.toContain('No route-based features')
})

it('does not reuse a removed feature after the source revision changes', async () => {
  await render('/features?feature=orders')
  list = { ...list, knowledge_revision: 2, features: [list.features[1]] }
  status = { ...status, knowledge_revision: 2 }
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(container.textContent).toContain('This feature is not in the current scan')
  expect(container.querySelector('.feature-hero')).toBeNull()
})

it('does not read feature data until a project is selected', async () => {
  status = { ...status, awaiting_project: true }
  await render()
  expect(container.textContent).toContain('No project is selected.')
  expect(vi.mocked(get).mock.calls.map(call => call[0])).toEqual(['/api/status'])
})

it('explains a valid scan without routes instead of showing an integration placeholder', async () => {
  list = { ...list, features: [] }
  await render()
  expect(container.textContent).toContain('No route-based features were found')
  expect(container.textContent).toContain('A feature starts at a route.')
  expect(get).toHaveBeenCalledTimes(2)
})

it('ignores a late detail response after choosing a different feature', async () => {
  const normal = vi.mocked(get).getMockImplementation()!
  let finish!: (value: unknown) => void
  vi.mocked(get).mockImplementation((path, signal) => path.endsWith('/orders')
    ? new Promise(resolve => { finish = resolve }) : normal(path, signal))
  await render()
  await act(async () => container.querySelectorAll<HTMLButtonElement>('.feature-list > button')[1].click())
  expect(container.querySelector('.feature-hero h2')?.textContent).toBe('Users')
  await act(async () => finish(body))
  expect(container.querySelector('.feature-hero h2')?.textContent).toBe('Users')
})
