import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Shell } from '../src/components/Shell'
import { Home } from '../src/pages/Home'
import { get, PROJECT_CHANGED } from '../src/lib/api'
import type { Settings } from '../src/lib/types'

vi.mock('../src/components/AuthGate', () => ({ useAccount: () => ({ user: { username: 'owner' }, logout: vi.fn() }) }))
vi.mock('../src/lib/api', async original => ({
  ...await original<typeof import('../src/lib/api')>(), get: vi.fn(),
}))
let container: HTMLDivElement
let root: ReturnType<typeof createRoot>
let settings: Settings

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  settings = { repo: 'acme/old-project', branch: 'main', platforms: ['github'] }
  vi.mocked(get).mockReset().mockImplementation(async path => path === '/api/status'
    ? { settings, knowledge_revision: 1 } : { platforms: [] })
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
})
afterEach(async () => {
  await act(async () => root.unmount())
  container.remove()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

it('updates sidebar, breadcrumb and browser title immediately after selecting a different project', async () => {
  await act(async () => root.render(<MemoryRouter><Shell /></MemoryRouter>))
  expect(container.querySelector('.project-pick-name')?.textContent).toBe('old-project')
  settings = { ...settings!, project_name: 'new-project', local: { path: 'D:\\Projects\\new-project' } }
  await act(async () => window.dispatchEvent(new Event(PROJECT_CHANGED)))
  expect(container.querySelector('.project-pick-name')?.textContent).toBe('new-project')
  expect(container.querySelector('.crumb')?.textContent).toBe('new-project')
  expect(document.title).toBe('new-project · KT Assistant')
  expect(container.textContent).not.toContain('old-project')
})

it('shows the added folder for an older mixed-source workspace and retains an explicit new repository name', async () => {
  settings = { ...settings!, local: { path: 'C:\\Projects\\functionalAI\\' } }
  await act(async () => root.render(<MemoryRouter><Shell /></MemoryRouter>))
  expect(container.querySelector('.project-pick-name')?.textContent).toBe('functionalAI')
  settings = { ...settings!, repo: 'acme/another-project', project_name: 'another-project' }
  await act(async () => window.dispatchEvent(new Event(PROJECT_CHANGED)))
  expect(container.querySelector('.project-pick-name')?.textContent).toBe('another-project')
  settings = null
  await act(async () => window.dispatchEvent(new Event(PROJECT_CHANGED)))
  expect(container.querySelector('.project-pick-name')?.textContent).toBe('No project')
  expect(document.title).toBe('KT Assistant')
})

it('uses the same project name in the Home welcome heading', async () => {
  settings = { ...settings!, project_name: 'functionalAI' }
  await act(async () => root.render(<MemoryRouter><Home /></MemoryRouter>))
  expect(container.querySelector('h1')?.textContent).toBe('Welcome to functionalAI')
  expect(container.textContent).not.toContain('old-project')
})
