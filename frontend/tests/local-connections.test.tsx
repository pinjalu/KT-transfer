import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Connections } from '../src/pages/Connections'
import { LocalSource } from '../src/pages/LocalSource'
import { get, post } from '../src/lib/api'
import { originOf } from '../src/lib/answer'

const account = vi.hoisted(() => ({ user: { role: 'owner' } }))
vi.mock('../src/components/AuthGate', () => ({ useAccount: () => account }))
vi.mock('../src/components/JiraPanel', () => ({ JiraPanel: () => null }))
vi.mock('../src/components/SlackPanel', () => ({ SlackPanel: () => null }))
vi.mock('../src/lib/api', async original => ({
  ...await original<typeof import('../src/lib/api')>(), get: vi.fn(), post: vi.fn(),
}))
let container: HTMLDivElement
let root: ReturnType<typeof createRoot>
let status: Record<string, unknown>
async function render() { await act(async () => root.render(<MemoryRouter><Connections /></MemoryRouter>)) }
function button(text: string) { return Array.from(container.querySelectorAll('button')).find(b => b.textContent?.trim() === text)! }
async function click(text: string) { await act(async () => button(text).click()) }
async function select(value: string) {
  await act(async () => {
    const field = container.querySelector<HTMLSelectElement>('select')!
    field.value = value
    field.dispatchEvent(new Event('change', {bubbles:true}))
  })
}
async function input(value: string) {
  await act(async () => {
    const field = container.querySelector<HTMLInputElement>('input')!
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field, value)
    field.dispatchEvent(new Event('input', { bubbles:true }))
  })
}
beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  account.user.role = 'owner'
  status = { settings: { repo:'acme/shop', branch:'main', platforms:['github'] }, knowledge_revision:1 }
  vi.mocked(get).mockReset()
  vi.mocked(post).mockReset().mockResolvedValue({reconnected:false, additional_local:true})
  vi.mocked(get).mockImplementation(async path => path === '/api/status' ? status
    : path === '/api/platforms' ? { platforms:[], credentials:{} } : { sources:{} })
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

it('keeps a typed local path across polls and saves the folder without a branch or token', async () => {
  await render()
  await select('local')
  expect(container.textContent).not.toContain('No GitHub token saved')
  expect(container.querySelectorAll('input')).toHaveLength(1)
  await input('file:///D:/Projects/my%20app')
  status = { ...status, settings: { repo:'acme/shop', branch:'main', platforms:['github'] } }
  await act(async () => vi.advanceTimersByTimeAsync(2000))
  expect(container.querySelector('input')!.value).toBe('file:///D:/Projects/my%20app')
  await click('Save and read files')
  expect(post).toHaveBeenCalledWith('/api/config', expect.objectContaining({ source_kind:'local', repo:'', local_path:'file:///D:/Projects/my%20app' }))
  expect(post).toHaveBeenCalledWith('/api/local/read')
  expect(post).not.toHaveBeenCalledWith('/api/scan')
  await select('github')
  expect(container.querySelector('input')!.value).toBe('acme/shop')
  await select('local')
  expect(container.querySelector('input')!.value).toBe('file:///D:/Projects/my%20app')
})

it('does not scan when folder validation fails and shows the API error', async () => {
  const { ApiError } = await import('../src/lib/api')
  vi.mocked(post).mockRejectedValue(new ApiError('Folder is unavailable.', 422))
  await render()
  await select('local')
  await input('D:\\missing')
  await click('Save and read files')
  expect(container.textContent).toContain('Folder is unavailable.')
  expect(post).toHaveBeenCalledTimes(1)
})

it('offers local folders only to the owner', async () => {
  account.user.role = 'member'
  await render()
  expect(container.querySelector('option[value="local"]')).toBeNull()
})

it('offers the saved workspace name while reconnecting its actual repository', async () => {
  status = { settings:null, awaiting_project:true, stored_project:{repo:'acme/shop', branch:'main', project_name:'functionalAI'} }
  await render()
  expect(container.querySelector('.conn-resume-text')?.textContent).toContain('Saved project: functionalAI')
  await click('Use it again')
  expect(container.querySelector('input')!.value).toBe('acme/shop')
})

it.each([
  { repo:'local:D:/Projects/functionalAI', branch:'working-tree', local_path:'D:/Projects/functionalAI' },
  { repo:'acme/shop', branch:'main', local:{path:'D:/Projects/functionalAI'}, selected_source:'local' },
])('restores the saved local form on navigation without overwriting a later form choice', async saved => {
  status = { settings:{ ...saved, platforms:['local'] }, knowledge_revision:1 }
  await render()
  expect(container.querySelector('select')!.value).toBe('local')
  expect(container.querySelector('input')!.value).toBe('D:/Projects/functionalAI')
  await select('github')
  await act(async () => vi.advanceTimersByTimeAsync(2000))
  expect(container.querySelector('select')!.value).toBe('github')
  await act(async () => root.unmount())
  root = createRoot(container)
  await render()
  expect(container.querySelector('select')!.value).toBe('local')
  expect(container.querySelector('input')!.value).toBe('D:/Projects/functionalAI')
})

it('restores and submits the saved folder when the workspace also has a GitHub repository', async () => {
  status = { settings:null, awaiting_project:true, stored_project:{
    repo:'acme/shop', branch:'main', project_name:'functionalAI',
    source_kind:'local', local_path:'D:/Projects/functionalAI',
  } }
  await render()
  await click('Use it again')
  expect(container.querySelector('select')!.value).toBe('local')
  expect(container.querySelector('input')!.value).toBe('D:/Projects/functionalAI')
  await click('Save and read files')
  expect(post).toHaveBeenCalledWith('/api/config', expect.objectContaining({
    source_kind:'local', repo:'', local_path:'D:/Projects/functionalAI',
  }))
  expect(post).toHaveBeenCalledWith('/api/local/read')
  expect(post).not.toHaveBeenCalledWith('/api/scan')
})

it.each([
  { repo:'local:D:/Projects/functionalAI', branch:'working-tree', local_path:'D:/Projects/functionalAI' },
  { repo:'acme/shop', branch:'main', local:{path:'D:/Projects/functionalAI'}, selected_source:'local' },
])('restores the saved local form on navigation without overwriting a later form choice', async saved => {
  status = { settings:{ ...saved, platforms:['local'] }, knowledge_revision:1 }
  await render()
  expect(container.querySelector('select')!.value).toBe('local')
  expect(container.querySelector('input')!.value).toBe('D:/Projects/functionalAI')
  await select('github')
  await act(async () => vi.advanceTimersByTimeAsync(2000))
  expect(container.querySelector('select')!.value).toBe('github')
  await act(async () => root.unmount())
  root = createRoot(container)
  await render()
  expect(container.querySelector('select')!.value).toBe('local')
  expect(container.querySelector('input')!.value).toBe('D:/Projects/functionalAI')
})

it('restores and submits the saved folder when the workspace also has a GitHub repository', async () => {
  status = { settings:null, awaiting_project:true, stored_project:{
    repo:'acme/shop', branch:'main', project_name:'functionalAI',
    source_kind:'local', local_path:'D:/Projects/functionalAI',
  } }
  await render()
  await click('Use it again')
  expect(container.querySelector('select')!.value).toBe('local')
  expect(container.querySelector('input')!.value).toBe('D:/Projects/functionalAI')
  await click('Save and read files')
  expect(post).toHaveBeenCalledWith('/api/config', expect.objectContaining({
    source_kind:'local', repo:'', local_path:'D:/Projects/functionalAI',
  }))
  expect(post).toHaveBeenCalledWith('/api/local/read')
  expect(post).not.toHaveBeenCalledWith('/api/scan')
})

it('renders local source text safely and labels local citations correctly', async () => {
  vi.mocked(get).mockResolvedValue({path:'README.md', snapshot:'abc', note:'Saved lines',
    lines:[{number:3, text:'<script>alert("no")</script>'}]})
  await act(async () => root.render(<MemoryRouter initialEntries={['/source?path=README.md&snapshot=abc']}><LocalSource /></MemoryRouter>))
  expect(container.querySelector('#L3')?.textContent).toContain('<script>')
  expect(container.querySelector('script')).toBeNull()
  expect(originOf('README.md', '/source?snapshot=abc')).toBe('Local folder')
  expect(originOf('jira/ENG-1', 'https://acme.atlassian.net/ENG-1')).toBe('Jira')
})
