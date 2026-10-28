import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Connections } from '../src/pages/Connections'
import { LocalSource } from '../src/pages/LocalSource'
import { get, post, uploadZip } from '../src/lib/api'
import { originOf } from '../src/lib/answer'

const account = vi.hoisted(() => ({ user: { role: 'owner' } }))
vi.mock('../src/components/AuthGate', () => ({ useAccount: () => account }))
vi.mock('../src/components/JiraPanel', () => ({ JiraPanel: () => null }))
vi.mock('../src/components/SlackPanel', () => ({ SlackPanel: () => null }))
vi.mock('../src/lib/api', async original => ({
  ...await original<typeof import('../src/lib/api')>(), get: vi.fn(), post: vi.fn(), uploadZip: vi.fn(),
}))
let container: HTMLDivElement
let root: ReturnType<typeof createRoot>
let status: Record<string, unknown>
async function render() { await act(async () => root.render(<MemoryRouter><Connections /></MemoryRouter>)) }
function button(text: string) { return Array.from(container.querySelectorAll('button')).find(b => b.textContent?.trim() === text)! }
async function click(text: string) { await act(async () => button(text).click()) }
async function select(value: string) {
  await act(async () => {
    const field = container.querySelector<HTMLSelectElement>('select[aria-label="Connection"]')!
    field.value = value
    field.dispatchEvent(new Event('change', {bubbles:true}))
  })
}
async function input(value: string) {
  await act(async () => {
    const field = container.querySelector<HTMLInputElement>('.conn-fields input')!
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
  vi.mocked(post).mockReset().mockResolvedValue({reconnected:false})
  vi.mocked(uploadZip).mockReset().mockResolvedValue({job_id:1})
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
  expect(container.querySelector('.conn-fields input')!.value).toBe('file:///D:/Projects/my%20app')
  await click('Save and read files')
  expect(post).toHaveBeenCalledWith('/api/config', expect.objectContaining({ source_kind:'local', repo:'', local_path:'file:///D:/Projects/my%20app' }))
  expect(post).toHaveBeenCalledWith('/api/config', expect.objectContaining({ add_to_project:false, platforms:['local'] }))
  expect(post).toHaveBeenCalledWith('/api/scan')
  expect(post).not.toHaveBeenCalledWith('/api/local/read')
  await select('github')
  expect(container.querySelector('.conn-fields input')!.value).toBe('acme/shop')
  await select('local')
  expect(container.querySelector('.conn-fields input')!.value).toBe('file:///D:/Projects/my%20app')
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

it('requires an explicit choice to add a folder to an existing project', async () => {
  status = { ...status, ready: true }
  vi.mocked(post).mockResolvedValue({ reconnected: false, additional_local: true })
  await render()
  await select('local')
  await input('D:/Projects/extra')
  const add = container.querySelector<HTMLInputElement>('input[type="checkbox"]')!
  expect(add.checked).toBe(false)
  expect(container.textContent).toContain('starts a new project')
  await act(async () => add.click())
  await click('Save and read files')
  expect(post).toHaveBeenCalledWith('/api/config', expect.objectContaining({ add_to_project: true }))
  expect(post).toHaveBeenCalledWith('/api/local/read')
  expect(post).not.toHaveBeenCalledWith('/api/scan')
})

it('offers local folders only to the owner', async () => {
  account.user.role = 'member'
  await render()
  expect(container.querySelector('option[value="local"]')).toBeNull()
  expect(container.querySelector('option[value="zip"]')).not.toBeNull()
})

it('uploads a member ZIP without requesting GitHub credentials or a host folder', async () => {
  account.user.role = 'member'
  await render()
  await select('zip')
  expect(container.textContent).not.toContain('No GitHub token saved')
  const file = new File(['zip fixture'], 'project.zip', { type:'application/zip' })
  await act(async () => {
    const field = container.querySelector<HTMLInputElement>('input[type="file"]')!
    Object.defineProperty(field, 'files', { value:[file], configurable:true })
    field.dispatchEvent(new Event('change', { bubbles:true }))
  })
  await click('Upload and read files')
  expect(uploadZip).toHaveBeenCalledWith(file)
  expect(post).not.toHaveBeenCalled()
  expect(container.textContent).toContain('ZIP uploaded')
})

it('reopens a saved ZIP after restart without requiring another upload', async () => {
  status = {settings:null, awaiting_project:true, stored_project:{repo:'zip:D:/managed/source', branch:'uploaded-snapshot', source_kind:'zip', project_name:'shop'}}
  await render()
  expect(container.querySelector<HTMLSelectElement>('select[aria-label="Connection"]')!.value).toBe('zip')
  await click('Use saved ZIP')
  expect(post).toHaveBeenCalledWith('/api/zip/resume')
  expect(uploadZip).not.toHaveBeenCalled()
})

it('shows a rejected ZIP and keeps the file available for retry', async () => {
  vi.mocked(uploadZip).mockRejectedValue(new Error('The ZIP contains an unsafe filename or folder path.'))
  await render()
  await select('zip')
  await act(async () => {
    const field = container.querySelector<HTMLInputElement>('input[type="file"]')!
    Object.defineProperty(field, 'files', { value:[new File(['zip'], 'bad.zip')], configurable:true })
    field.dispatchEvent(new Event('change', { bubbles:true }))
  })
  await click('Upload and read files')
  expect(container.textContent).toContain('unsafe filename')
  expect(button('Upload and read files').disabled).toBe(false)
  expect(post).not.toHaveBeenCalled()
})

it('shows reused and fetched counts and limits resume guidance to file imports', async () => {
  status = { ...status, scan: { status:'complete', read:12, reused:10, fetched:2, skipped:1, failed:0 } }
  await render()
  expect(container.querySelector('.conn-counts')?.textContent).toContain('10 reused')
  expect(container.querySelector('.conn-counts')?.textContent).toContain('2 fetched')
  expect(container.textContent).toContain('Refresh reuses unchanged files')
  await select('jira')
  expect(container.textContent).not.toContain('Refresh reuses unchanged files')
})

it('offers the saved workspace name while reconnecting its actual repository', async () => {
  status = { settings:null, awaiting_project:true, stored_project:{repo:'acme/shop', branch:'main', project_name:'functionalAI'} }
  await render()
  expect(container.querySelector('.conn-resume-text')?.textContent).toContain('Saved project: functionalAI')
  await click('Use it again')
  expect(container.querySelector('.conn-fields input')!.value).toBe('acme/shop')
})

it.each([
  { repo:'local:D:/Projects/functionalAI', branch:'working-tree', local_path:'D:/Projects/functionalAI' },
  { repo:'acme/shop', branch:'main', local:{path:'D:/Projects/functionalAI'}, selected_source:'local' },
])('restores the saved local form on navigation without overwriting a later form choice', async saved => {
  status = { settings:{ ...saved, platforms:['local'] }, knowledge_revision:1 }
  await render()
  expect(container.querySelector('select[aria-label="Connection"]')!.value).toBe('local')
  expect(container.querySelector('.conn-fields input')!.value).toBe('D:/Projects/functionalAI')
  await select('github')
  await act(async () => vi.advanceTimersByTimeAsync(2000))
  expect(container.querySelector('select[aria-label="Connection"]')!.value).toBe('github')
  await act(async () => root.unmount())
  root = createRoot(container)
  await render()
  expect(container.querySelector('select[aria-label="Connection"]')!.value).toBe('local')
  expect(container.querySelector('.conn-fields input')!.value).toBe('D:/Projects/functionalAI')
})

it('restores and submits the saved folder when the workspace also has a GitHub repository', async () => {
  status = { settings:null, awaiting_project:true, stored_project:{
    repo:'acme/shop', branch:'main', project_name:'functionalAI',
    source_kind:'local', local_path:'D:/Projects/functionalAI',
  } }
  await render()
  await click('Use it again')
  expect(container.querySelector('select[aria-label="Connection"]')!.value).toBe('local')
  expect(container.querySelector('.conn-fields input')!.value).toBe('D:/Projects/functionalAI')
  await click('Save and read files')
  expect(post).toHaveBeenCalledWith('/api/config', expect.objectContaining({
    source_kind:'local', repo:'', local_path:'D:/Projects/functionalAI',
  }))
  expect(post).toHaveBeenCalledWith('/api/scan')
  expect(post).not.toHaveBeenCalledWith('/api/local/read')
})

it.each([
  { repo:'local:D:/Projects/functionalAI', branch:'working-tree', local_path:'D:/Projects/functionalAI' },
  { repo:'acme/shop', branch:'main', local:{path:'D:/Projects/functionalAI'}, selected_source:'local' },
])('restores the saved local form on navigation without overwriting a later form choice', async saved => {
  status = { settings:{ ...saved, platforms:['local'] }, knowledge_revision:1 }
  await render()
  expect(container.querySelector('select[aria-label="Connection"]')!.value).toBe('local')
  expect(container.querySelector('.conn-fields input')!.value).toBe('D:/Projects/functionalAI')
  await select('github')
  await act(async () => vi.advanceTimersByTimeAsync(2000))
  expect(container.querySelector('select[aria-label="Connection"]')!.value).toBe('github')
  await act(async () => root.unmount())
  root = createRoot(container)
  await render()
  expect(container.querySelector('select[aria-label="Connection"]')!.value).toBe('local')
  expect(container.querySelector('.conn-fields input')!.value).toBe('D:/Projects/functionalAI')
})

it('restores and submits the saved folder when the workspace also has a GitHub repository', async () => {
  status = { settings:null, awaiting_project:true, stored_project:{
    repo:'acme/shop', branch:'main', project_name:'functionalAI',
    source_kind:'local', local_path:'D:/Projects/functionalAI',
  } }
  await render()
  await click('Use it again')
  expect(container.querySelector('select[aria-label="Connection"]')!.value).toBe('local')
  expect(container.querySelector('.conn-fields input')!.value).toBe('D:/Projects/functionalAI')
  await click('Save and read files')
  expect(post).toHaveBeenCalledWith('/api/config', expect.objectContaining({
    source_kind:'local', repo:'', local_path:'D:/Projects/functionalAI',
  }))
  expect(post).toHaveBeenCalledWith('/api/scan')
  expect(post).not.toHaveBeenCalledWith('/api/local/read')
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
