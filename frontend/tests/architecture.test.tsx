import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Architecture } from '../src/pages/Architecture'
import { get, post } from '../src/lib/api'
import type { ArchitectureBody, ArchitectureSystem } from '../src/lib/useArchitecture'
import type { Status } from '../src/lib/types'

vi.mock('../src/lib/api', async original => ({ ...await original<typeof import('../src/lib/api')>(), get: vi.fn(), post: vi.fn() }))
let container: HTMLDivElement
let root: ReturnType<typeof createRoot>
let status: Status
let body: ArchitectureBody

function system(id: string, name: string, label: string): ArchitectureSystem {
  return { id, name, facts: [], roles: {}, diagrams: [{ key: 'modules', kind: 'graph', title: `${name} map`, plain: '', note: '', edges: [],
    nodes: [{ id: label, label, sublabel: '', path: `${label}.py`, line: 1, url: '', kind: 'file', column: 0, row: 0 }] }] }
}
async function render() { await act(async () => root.render(<MemoryRouter><Architecture /></MemoryRouter>)) }
async function click(label: string) {
  const button = [...container.querySelectorAll('button')].find(value => value.textContent === label)!
  expect(button).toBeTruthy()
  await act(async () => button.click())
}
beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  status = { knowledge_revision: 1, settings: { repo: 'acme/shop', branch: 'main', platforms: ['github'] },
    scan: { id: 1, repo: 'acme/shop', branch: 'main', commit: 'abcdefg', status: 'complete' },
    ready: true, busy: false, overview_building: false, awaiting_project: false } as Status
  body = { repo: 'acme/shop', branch: 'main', scan_id: 1, commit: 'abcdefg', knowledge_revision: 1,
    systems: [system('primary', 'Shop', 'old_handler')] }
  vi.mocked(get).mockReset(); vi.mocked(post).mockReset()
  vi.mocked(get).mockImplementation(async path => {
    if (path === '/api/status') return status
    if (path === '/api/architecture') return { available: true, architecture: body, reason: '' }
    throw new Error(`Unexpected read: ${path}`)
  })
  container = document.createElement('div'); document.body.append(container); root = createRoot(container)
})
afterEach(async () => {
  await act(async () => root.unmount()); container.remove()
  vi.useRealTimers(); vi.unstubAllGlobals()
})

it('refreshes current diagrams without loading a saved overview and hides the old map while drawing', async () => {
  await render()
  expect(container.textContent).toContain('old_handler')
  let finish!: (value: unknown) => void
  const normal = vi.mocked(get).getMockImplementation()!
  vi.mocked(get).mockImplementation((path, signal) => path === '/api/architecture'
    ? new Promise(resolve => { finish = resolve }) : normal(path, signal))
  await click('Refresh architecture')
  expect(container.textContent).not.toContain('old_handler')
  expect(container.textContent).toContain('Drawing current architecture')
  await act(async () => finish({ available: true, reason: '', architecture: {
    ...body, systems: [system('primary', 'Shop', 'fresh_handler')] } }))
  expect(container.textContent).toContain('fresh_handler')
  expect(container.textContent).not.toContain('old_handler')
  expect(vi.mocked(get).mock.calls.some(([path]) => path === '/api/overview')).toBe(false)
  expect(post).not.toHaveBeenCalled()
})

it('shows connected systems as separate maps', async () => {
  body.systems.push(system('local://snapshot/', 'Matching', 'investor_handler'))
  await render()
  expect(container.querySelector('.dg-node')?.textContent).toContain('old_handler')
  expect(container.querySelector('.dg-node')?.textContent).not.toContain('investor_handler')
  await click('Matching')
  expect(container.querySelector('.dg-node')?.textContent).toContain('investor_handler')
  expect(container.querySelector('.dg-node')?.textContent).not.toContain('old_handler')
  await click('Shop')
  expect(container.querySelector('.dg-node')?.textContent).toContain('old_handler')
})

it('rejects an old project response even when scan IDs and revisions match', async () => {
  await render()
  status = { ...status, settings: { ...status.settings!, repo: 'acme/new-project' },
    scan: { ...status.scan!, repo: 'acme/new-project' } }
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(container.textContent).not.toContain('old_handler')
  expect(container.textContent).toContain('do not match the current project files')
})

it('hides the previous architecture while new source files are being read', async () => {
  await render()
  status = { ...status, busy: true, job: { id: 2, kind: 'local', state: 'running' } as Status['job'] }
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(container.textContent).not.toContain('old_handler')
  expect(container.querySelector('svg')).toBeNull()
})
