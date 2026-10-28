import { act, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Link, MemoryRouter, Route, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Shell } from '../src/components/Shell'
import { RetainedPages } from '../src/components/RetainedPages'
import { Overview } from '../src/pages/Overview'
import { Ask } from '../src/pages/Ask'
import { Architecture } from '../src/pages/Architecture'
import { get, post, PROJECT_CHANGED } from '../src/lib/api'
import { useApi } from '../src/lib/useApi'
import { useRememberedParam } from '../src/lib/pageState'
import type { Status } from '../src/lib/types'
import type { Overview as Body } from '../src/lib/overview'
import type { Answer } from '../src/lib/answer'

vi.mock('../src/lib/api', async original => ({
  ...await original<typeof import('../src/lib/api')>(), get: vi.fn(), post: vi.fn(),
}))
vi.mock('../src/components/AuthGate', () => ({ useAccount: () => ({ user: { username: 'tester', role: 'owner' }, logout: vi.fn() }) }))

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>
let status: Status
let body: Body
const reads = (path: string) => vi.mocked(get).mock.calls.filter(([value]) => value === path)
const page = (path: string) => container.querySelector<HTMLDivElement>(`[data-page="${path}"]`)!
async function click(element: HTMLElement) { await act(async () => element.click()) }
async function navigate(path: string) { await click(container.querySelector<HTMLAnchorElement>(`.sidebar a[href="${path}"]`)!) }
async function type(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
  await act(async () => {
    const proto = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(proto, 'value')!.set!.call(element, value)
    element.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
async function renderApp() {
  await act(async () => root.render(<MemoryRouter initialEntries={['/overview']}><Shell>
    <Route path="overview" element={<Overview />} />
    <Route path="ask" element={<Ask />} />
    <Route path="architecture" element={<Architecture />} />
  </Shell></MemoryRouter>))
}

function answer(): Answer {
  return { answer_id: 42, statements: [{ text: 'The project uses a local document index.', source_ids: ['readme'],
    support: 'supported', support_share: 1, about_this_project: true }], sources: body.sections[0].sources,
    missing_information: '', error: null, warning: '', search: {}, commit: 'abcdefg', repo: 'acme/project',
    scanned_at: null, access_checked_at: '2026-10-26T09:00:00Z', elapsed_seconds: 1, citation_check: 'Verified.' }
}

async function sendQuestion() {
  await type(page('/ask').querySelector('textarea')!, 'How are documents indexed?')
  await click(page('/ask').querySelector<HTMLButtonElement>('button[type="submit"]')!)
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  Element.prototype.scrollIntoView = vi.fn()
  status = { knowledge_revision: 1, settings: { repo: 'acme/project', branch: 'main', platforms: ['github'] },
    scan: { id: 1, repo: 'acme/project', branch: 'main', commit: 'abcdefg', status: 'complete' },
    ready: true, busy: false, overview_building: false, awaiting_project: false } as Status
  body = { repo: 'acme/project', branch: 'main', commit: 'abcdefg', scan_id: 1, scanned_at: null,
    demo: false, sections: [{ key: 'purpose', title: 'Project purpose', statements: [{ text: 'Saved project explanation',
      source_ids: ['readme'], support: 'supported', support_share: 1, about_this_project: true }],
      sources: [{ source_id: 'readme', path: 'README.md', start: 1, end: 3, url: '', text: 'Saved source' }],
      missing_information: '', error: '', checks: { unsupported: 0, generic: 0, narrowed_citations: 0, dropped_repeats: 0 } }],
    facts: [], reading_order: [], diagrams: [], roles: {}, steps: [], topics_done: 1, topics_total: 1,
    complete: true, files_indexed: 1, files_skipped: 0, scope_note: '' }
  vi.mocked(get).mockReset(); vi.mocked(post).mockReset()
  vi.mocked(get).mockImplementation(async path => {
    if (path === '/api/status') return status
    if (path === '/api/overview') return { available: true, overview: body, building: false, reason: '' }
    if (path === '/api/architecture') return { available: true, reason: '', architecture: {
      repo: status.settings?.repo, branch: status.settings?.branch, scan_id: status.scan?.id,
      commit: status.scan?.commit, knowledge_revision: status.knowledge_revision,
      systems: [{ id: 'primary', name: 'project', diagrams: [], facts: [], roles: {} }] } }
    if (path === '/api/features') return { available: true, repo: status.settings?.repo, branch: status.settings?.branch,
      scan_id: status.scan?.id, commit: status.scan?.commit, knowledge_revision: status.knowledge_revision,
      features: [], unclustered: { note: '' } }
    if (path === '/api/poll') return { value: 'saved' }
    throw new Error(`Unexpected read: ${path}`)
  })
  container = document.createElement('div'); document.body.append(container); root = createRoot(container)
})
afterEach(async () => {
  await act(async () => root.unmount()); container.remove()
  vi.useRealTimers(); vi.unstubAllGlobals()
})

it('returns to the same overview, mode, disclosure, scroll position and chat draft without reading again', async () => {
  await renderApp()
  const overview = page('/overview')
  await click(Array.from(overview.querySelectorAll('button')).find(x => x.textContent === 'Developer')!)
  const disclosure = overview.querySelector<HTMLDetailsElement>('#src-readme')!
  disclosure.open = true
  const scroller = container.querySelector<HTMLElement>('.page')!
  scroller.scrollTop = 220; scroller.dispatchEvent(new Event('scroll'))
  await navigate('/ask')
  expect(overview.hidden).toBe(true)
  expect(overview.hasAttribute('inert')).toBe(true)
  expect(scroller.scrollTop).toBe(0)
  const draft = page('/ask').querySelector('textarea')!
  await type(draft, 'Keep this unfinished question')
  await navigate('/overview')
  expect(page('/overview')).toBe(overview)
  expect(disclosure.open).toBe(true)
  expect(overview.querySelector('.segment.is-active')?.textContent).toBe('Developer')
  expect(scroller.scrollTop).toBe(220)
  expect(overview.textContent).not.toContain('Loading saved overview')
  await navigate('/ask')
  expect(page('/ask').querySelector('textarea')).toBe(draft)
  expect(draft.value).toBe('Keep this unfinished question')
  expect(reads('/api/overview')).toHaveLength(1)
  expect(reads('/api/features')).toHaveLength(1)
  expect(reads('/api/status')).toHaveLength(1)
  await act(async () => vi.advanceTimersByTimeAsync(60000))
  expect(reads('/api/overview')).toHaveLength(1)
  expect(reads('/api/features')).toHaveLength(1)
  expect(post).not.toHaveBeenCalled()
})

it('keeps an in-flight overview read alive across navigation instead of restarting it', async () => {
  let finish!: (value: unknown) => void
  const pending = new Promise(resolve => { finish = resolve })
  const normal = vi.mocked(get).getMockImplementation()!
  vi.mocked(get).mockImplementation((path, signal) => path === '/api/overview' ? pending : normal(path, signal))
  await renderApp()
  const signal = reads('/api/overview')[0][1]!
  await navigate('/ask'); await navigate('/overview')
  expect(signal.aborted).toBe(false)
  expect(reads('/api/overview')).toHaveLength(1)
  await act(async () => finish({ available: true, overview: body, building: false }))
  expect(page('/overview').textContent).toContain('Saved project explanation')
})

it('refreshes architecture independently of the saved overview and retains it through navigation', async () => {
  await renderApp(); await navigate('/architecture'); await navigate('/ask'); await navigate('/architecture')
  expect(reads('/api/overview')).toHaveLength(1)
  expect(reads('/api/architecture')).toHaveLength(1)
  const architecture = page('/architecture')
  const refresh = Array.from(architecture.querySelectorAll('button')).find(x => x.textContent?.includes('Refresh architecture'))!
  await click(refresh)
  expect(reads('/api/overview')).toHaveLength(1)
  expect(reads('/api/architecture')).toHaveLength(2)
  expect(architecture.textContent).toContain('Architecture')
  expect(post).not.toHaveBeenCalled()
})

it('keeps completed answers, feedback and a draft through navigation and tab changes, until browser reload', async () => {
  vi.mocked(post).mockImplementation(async path => path === '/api/ask' ? answer() : {})
  await renderApp(); await navigate('/ask'); await sendQuestion()
  await click(Array.from(page('/ask').querySelectorAll('button')).find(x => x.textContent === 'Correct')!)
  await type(page('/ask').querySelector('textarea')!, 'And how are they updated?')
  await navigate('/overview')
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  await navigate('/ask')
  expect(page('/ask').textContent).toContain('How are documents indexed?')
  expect(page('/ask').textContent).toContain('The project uses a local document index.')
  expect(page('/ask').textContent).toContain('Saved.')
  expect(page('/ask').querySelector('textarea')?.value).toBe('And how are they updated?')
  expect(vi.mocked(post).mock.calls.filter(([path]) => path === '/api/ask')).toHaveLength(1)

  // A browser refresh creates a fresh application tree, without restoring session storage.
  await act(async () => root.unmount())
  root = createRoot(container)
  await renderApp(); await navigate('/ask')
  expect(page('/ask').querySelector('.turn')).toBeNull()
  expect(page('/ask').querySelector('textarea')?.value).toBe('')
})

it('finishes an answer while away without scrolling the current page or sending it again', async () => {
  let finish!: (value: Answer) => void
  vi.mocked(post).mockReturnValue(new Promise(resolve => { finish = resolve }))
  await renderApp(); await navigate('/ask'); await sendQuestion()
  await navigate('/overview')
  vi.mocked(Element.prototype.scrollIntoView).mockClear()
  await act(async () => { finish(answer()); await vi.advanceTimersByTimeAsync(20) })
  expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled()
  await navigate('/ask')
  expect(page('/ask').textContent).toContain('The project uses a local document index.')
  expect(page('/ask').querySelector('button[type="submit"]')?.textContent).toContain('Send')
  expect(post).toHaveBeenCalledTimes(1)
})

it('keeps chat history when project sources update and marks the earlier answer', async () => {
  vi.mocked(post).mockResolvedValue(answer())
  await renderApp(); await navigate('/ask'); await sendQuestion()
  const draft = page('/ask').querySelector('textarea')!
  await type(draft, 'Follow up after the scan'); await navigate('/overview')
  status = { ...status, knowledge_revision: 2 }
  await act(async () => vi.advanceTimersByTimeAsync(2000))
  expect(reads('/api/overview')).toHaveLength(2)
  await navigate('/ask')
  expect(page('/ask').querySelector('textarea')).toBe(draft)
  expect(draft.value).toBe('Follow up after the scan')
  expect(page('/ask').textContent).toContain('The project uses a local document index.')
  expect(page('/ask').textContent).toContain('the project sources have been updated since this reply')
  await sendQuestion()
  expect(vi.mocked(post).mock.calls.filter(([path]) => path === '/api/ask').at(-1)?.[1]).toEqual({ question: 'How are documents indexed?' })
})

it('sends prior conversation when asking a follow-up after navigation', async () => {
  vi.mocked(post).mockResolvedValue(answer())
  await renderApp(); await navigate('/ask'); await sendQuestion()
  await navigate('/overview'); await navigate('/ask')
  await type(page('/ask').querySelector('textarea')!, 'How is it updated?')
  await click(page('/ask').querySelector<HTMLButtonElement>('button[type="submit"]')!)
  const payload = vi.mocked(post).mock.calls.filter(([path]) => path === '/api/ask').at(-1)?.[1]
  expect(payload).toEqual({ question: 'How is it updated?', conversation: {
    repo: 'acme/project', commit: 'abcdefg', knowledge_revision: 1,
    turns: [{ question: 'How are documents indexed?', answer: 'The project uses a local document index.' }],
  } })
})

it('retains the conversation through a temporary status failure and recovery', async () => {
  vi.mocked(post).mockResolvedValue(answer())
  await renderApp(); await navigate('/ask'); await sendQuestion()
  await type(page('/ask').querySelector('textarea')!, 'Keep my follow-up')
  vi.mocked(get).mockRejectedValueOnce(new Error('Connection interrupted'))
  await act(async () => vi.advanceTimersByTimeAsync(2000))
  expect(container.textContent).toContain('Something went wrong.')
  expect(page('/ask').closest('[hidden]')).not.toBeNull()
  await act(async () => vi.advanceTimersByTimeAsync(2000))
  expect(page('/ask').closest('[hidden]')).toBeNull()
  expect(page('/ask').textContent).toContain('The project uses a local document index.')
  expect(page('/ask').querySelector('textarea')?.value).toBe('Keep my follow-up')
})

it('discards old page state when switching projects and on workspace unmount', async () => {
  await renderApp(); await navigate('/ask')
  const draft = page('/ask').querySelector('textarea')!
  await type(draft, 'Old project question'); await navigate('/overview')
  status = { ...status, settings: { ...status.settings, repo: 'acme/another-project' }, knowledge_revision: 2 }
  await act(async () => vi.advanceTimersByTimeAsync(2000))
  expect(container.contains(draft)).toBe(false)
  expect(reads('/api/overview')).toHaveLength(2)
  await navigate('/ask')
  expect(page('/ask').querySelector('textarea')?.value).toBe('')
  await act(async () => root.render(<p>Signed out</p>))
  expect(container.querySelector('[data-page]')).toBeNull()
  await renderApp()
  expect(reads('/api/overview')).toHaveLength(3)
})

it('hides old views immediately after a project selection and ignores a late old status response', async () => {
  await renderApp()
  await navigate('/ask')
  const draft = page('/ask').querySelector('textarea')!
  await type(draft, 'Previous project question')
  await navigate('/overview')
  const oldOverview = page('/overview')
  const oldStatus = status
  let finishOld!: (value: Status) => void
  let finishNew!: (value: Status) => void
  const normal = vi.mocked(get).getMockImplementation()!
  let statusReads = 0
  vi.mocked(get).mockImplementation((path, signal) => {
    if (path === '/api/status') return new Promise<Status>(resolve => {
      if (++statusReads === 1) finishOld = resolve
      else finishNew = resolve
    })
    if (path === '/api/overview') return Promise.resolve({ available: false, overview: null, building: false })
    return normal(path, signal)
  })
  await act(async () => vi.advanceTimersByTimeAsync(2000))
  const oldSignal = reads('/api/status').at(-1)![1]!
  await act(async () => window.dispatchEvent(new Event(PROJECT_CHANGED)))
  expect(oldSignal.aborted).toBe(true)
  expect(oldOverview.closest('[hidden]')).not.toBeNull()
  expect(container.querySelector('.sidebar-project-name')?.textContent).toBe('No project')
  status = { ...status, settings: { repo: 'local:D:/new-folder', branch: 'working-tree', platforms: ['local'] },
    ready: false, knowledge_revision: 2 }
  await act(async () => finishNew(status))
  expect(container.contains(draft)).toBe(false)
  expect(container.contains(oldOverview)).toBe(false)
  expect(container.textContent).not.toContain('Saved project explanation')
  await act(async () => finishOld(oldStatus))
  expect(container.querySelector('.sidebar-project-name')?.textContent).toBe('new-folder')
  expect(container.textContent).not.toContain('Previous project question')
})

function Selection() {
  const [selected, setParams] = useRememberedParam('issue')
  const location = useLocation()
  const [draft, setDraft] = useState('')
  const data = useApi<{ value: string }>('/api/poll', 1000)
  return <><p>{selected || 'default'} {location.pathname} {data.data?.value}</p>
    <input value={draft} onChange={event => setDraft(event.target.value)} />
    <button onClick={() => setParams({ issue: 'SCRUM-25' })}>Choose ticket</button></>
}

it('freezes inactive route context, pauses hidden polling and remembers a query selection on sidebar return', async () => {
  await act(async () => root.render(<MemoryRouter initialEntries={['/jira?issue=SCRUM-23']}>
    <nav><Link to="/jira">Jira</Link><Link to="/ask">Ask</Link></nav>
    <RetainedPages scope="project-1"><Route path="jira" element={<Selection />} /><Route path="ask" element={<p>Ask page</p>} /></RetainedPages>
  </MemoryRouter>))
  await click(page('/jira').querySelector('button')!)
  await click(container.querySelector<HTMLAnchorElement>('nav a[href="/ask"]')!)
  expect(page('/jira').textContent).toContain('SCRUM-25 /jira')
  await act(async () => vi.advanceTimersByTimeAsync(10000))
  expect(reads('/api/poll')).toHaveLength(1)
  await click(container.querySelector<HTMLAnchorElement>('nav a[href="/jira"]')!)
  expect(page('/jira').textContent).toContain('SCRUM-25 /jira')
  expect(reads('/api/poll')).toHaveLength(1)
})

it('opens citation evidence in the active page when a retained page has the same ID', async () => {
  await act(async () => root.render(<MemoryRouter initialEntries={['/overview']}>
    <nav><Link to="/ask">Ask</Link></nav><RetainedPages scope="project-1">
      <Route path="overview" element={<details id="src-shared"><summary>Overview evidence</summary></details>} />
      <Route path="ask" element={<><a href="#src-shared">Citation</a><details id="src-shared"><summary>Answer evidence</summary></details></>} />
    </RetainedPages>
  </MemoryRouter>))
  const oldEvidence = page('/overview').querySelector('details')!
  await click(container.querySelector<HTMLAnchorElement>('nav a')!)
  await click(page('/ask').querySelector('a')!)
  expect(oldEvidence.open).toBe(false)
  expect(page('/ask').querySelector('details')?.open).toBe(true)
})

it('discards account form fields when leaving Account', async () => {
  await act(async () => root.render(<MemoryRouter initialEntries={['/account']}>
    <nav><Link to="/account">Account</Link><Link to="/ask">Ask</Link></nav><RetainedPages scope="project-1">
      <Route path="account" element={<input aria-label="Account secret" type="password" />} />
      <Route path="ask" element={<p>Ask page</p>} />
    </RetainedPages>
  </MemoryRouter>))
  const input = page('/account').querySelector('input')!
  input.value = 'unsaved test credential'
  await click(container.querySelector<HTMLAnchorElement>('nav a[href="/ask"]')!)
  expect(container.contains(input)).toBe(false)
  await click(container.querySelector<HTMLAnchorElement>('nav a[href="/account"]')!)
  expect(page('/account').querySelector('input')?.value).toBe('')
})
