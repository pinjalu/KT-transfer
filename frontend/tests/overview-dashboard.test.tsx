import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Overview } from '../src/pages/Overview'
import { get, post } from '../src/lib/api'
import type { Overview as Body, Section } from '../src/lib/overview'
import type { Status } from '../src/lib/types'

vi.mock('../src/lib/api', async original => ({
  ...await original<typeof import('../src/lib/api')>(), get: vi.fn(), post: vi.fn(),
}))

function topic(key: string, title: string, count = 1): Section {
  return { key, title, statements: Array.from({ length: count }, (_, i) => ({
    text: `${title} point ${i + 1}`, source_ids: ['source-1'], support: 'supported',
    support_share: 1, about_this_project: true,
  })), sources: [{ source_id: 'source-1', path: 'README.md', start: 1, end: 6,
    url: 'https://github.com/example/project/blob/abc/README.md#L1', text: 'Original source excerpt' }],
  missing_information: '', error: '', checks: { unsupported: 0, generic: 0, narrowed_citations: 0, dropped_repeats: 0 } }
}

let body: Body
let status: Status
let featuresError: boolean
let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

async function render() { await act(async () => root.render(<MemoryRouter><Overview /></MemoryRouter>)) }
function button(label: string) {
  const found = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.trim() === label)
  if (!found) throw new Error(`Button not found: ${label}`)
  return found
}
async function click(label: string) { await act(async () => button(label).click()) }
function panel() { return container.querySelector('#ov-panel')! }

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  Element.prototype.scrollIntoView = vi.fn()
  status = { knowledge_revision: 1, busy: false, overview_building: false, awaiting_project: false } as Status
  body = { repo: 'example/project', branch: 'main', commit: 'abcdefg', scan_id: 1, scanned_at: null,
    demo: false, sections: [topic('purpose', 'Project purpose', 5), topic('setup', 'Project setup'), topic('testing', 'Project tests')],
    facts: [{ key: 'commands', title: 'Commands', plain: 'Commands in the README', truncated: 0, note: '',
      items: [{ text: 'npm start', path: 'README.md', line: 4, url: '', detail: 'Start locally' }] }],
    reading_order: [{ path: 'README.md', why: 'Start with the documentation.', url: '' }], diagrams: [], roles: {}, steps: [],
    topics_done: 3, topics_total: 3, complete: true, files_indexed: 12, files_skipped: 2, scope_note: 'Saved imported excerpts only.' }
  featuresError = false
  vi.mocked(get).mockReset()
  vi.mocked(post).mockReset()
  vi.mocked(get).mockImplementation(async path => {
    if (path === '/api/status') return status
    if (path === '/api/overview') return { available: true, overview: body, building: status.overview_building, progress: null, reason: '' }
    if (path === '/api/features') {
      if (featuresError) throw new Error('Source read failed')
      return { available: true, features: [{ id: 'api', name: 'API', route_count: 2, file_count: 4, gap_count: 1 }], unclustered: { note: '' } }
    }
    throw new Error(`Unexpected read: ${path}`)
  })
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

describe('interactive overview', () => {
  it('uses the current project title while retaining the actual repository in source metadata', async () => {
    status.settings = { repo: body.repo, branch: 'main', platforms: ['github', 'local'], project_name: 'functionalAI' }
    await render()
    expect(container.querySelector('.ov-hero h2')?.textContent).toBe('functionalAI')
    expect(container.querySelector('.ov-hero-meta')?.textContent).toContain('example/project')
    status = { ...status, settings: { ...status.settings!, project_name: 'new-local-project' } }
    await act(async () => vi.advanceTimersByTimeAsync(5000))
    expect(container.querySelector('.ov-hero h2')?.textContent).toBe('new-local-project')
    expect(post).not.toHaveBeenCalled()
  })

  it('navigates topics and exposes all points without requesting a build or fetching again', async () => {
    await render()
    expect(panel().textContent).toContain('Project purpose point 3')
    expect(panel().textContent).toContain('Project purpose point 4')
    expect(panel().textContent).toContain('Project purpose point 5')
    await click('Getting started')
    expect(panel().textContent).toContain('Project setup point 1')
    expect(panel().textContent).toContain('npm start')
    await click('Next: Testing')
    expect(container.querySelector('#ov-topic-heading')?.textContent).toBe('Project tests')
    expect(document.activeElement).toBe(container.querySelector('#ov-topic-heading'))
    expect(get).toHaveBeenCalledTimes(3)
    expect(post).not.toHaveBeenCalled()
  })

  it('opens the exact evidence excerpt from its citation even in Beginner mode', async () => {
    await render()
    const source = container.querySelector<HTMLDetailsElement>('#src-source-1')!
    expect(source.open).toBe(false)
    await act(async () => container.querySelector<HTMLAnchorElement>('a.cite')!.click())
    expect(source.open).toBe(true)
    expect(source.textContent).toContain('Original source excerpt')
    expect(container.querySelectorAll('#src-source-1')).toHaveLength(1)
  })

  it('filters topic navigation and can recover from no results', async () => {
    await render()
    const input = container.querySelector<HTMLInputElement>('[aria-label="Find a topic"]')!
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, 'no-such-topic')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(container.textContent).toContain('No matching topics.')
    expect(container.querySelectorAll('.ov-topic')).toHaveLength(0)
    await click('Clear search')
    expect(container.querySelectorAll('.ov-topic')).toHaveLength(7)
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, 'setup')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(container.querySelectorAll('.ov-topic')).toHaveLength(1)
    expect(container.querySelector('.ov-topic')?.textContent).toBe('Getting started')
  })

  it('keeps the reading checklist through topic changes and background reads, then resets it for new source data', async () => {
    await render()
    await click('Reading checklist')
    await act(async () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click())
    await click('Start here')
    await act(async () => vi.advanceTimersByTimeAsync(30000))
    await click('Reading checklist')
    expect(container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked).toBe(true)
    status = { ...status, knowledge_revision: 2 }
    body = { ...body, scan_id: 2 }
    await act(async () => vi.advanceTimersByTimeAsync(5000))
    await click('Reading checklist')
    expect(container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked).toBe(false)
    expect(post).not.toHaveBeenCalled()
  })

  it('keeps failures, partial support, missing information and extracted gaps reachable', async () => {
    body.sections[0].statements[4].support = 'check this'
    body.sections[1].error = 'Model unavailable'
    body.sections[1].statements = []
    body.sections[2].missing_information = 'No CI configuration was read.'
    body.facts.push({ key: 'gaps', title: 'Known gaps', plain: '', note: '', truncated: 0,
      items: [{ text: 'No deployment guide', detail: '', path: '', line: 0, url: '' }] })
    await render()
    const metric = Array.from(container.querySelectorAll('.ov-metric')).find(el => el.textContent?.includes('Review items'))!
    const written = Array.from(container.querySelectorAll('.ov-metric')).find(el => el.textContent?.includes('Topics written'))!
    expect(written.querySelector('strong')!.textContent).toBe('2/3')
    expect(metric.querySelector('strong')!.textContent).toBe('4')
    await act(async () => (metric as HTMLButtonElement).click())
    expect(panel().textContent).toContain('Build failed: Model unavailable')
    expect(panel().textContent).toContain('No CI configuration was read.')
    expect(panel().textContent).toContain('No deployment guide')
    expect(panel().querySelector('.ov-coverage')?.textContent).toContain('Topics written2 of 3')
    await click('Getting started')
    expect(panel().querySelector('[role="alert"]')?.textContent).toContain('Model unavailable')
    expect(panel().textContent).not.toContain('No evidence was found')
  })

  it('does not report zero features when a source read fails', async () => {
    featuresError = true
    await render()
    const metric = Array.from(container.querySelectorAll('.ov-metric')).find(el => el.textContent?.includes('Feature groups'))!
    expect(metric.querySelector('strong')!.textContent).toBe('—')
    await click('Main features')
    expect(panel().querySelector('[role="alert"]')).not.toBeNull()
    expect(panel().textContent).not.toContain('No features were derived.')
  })

  it('offers retry beside partial coverage and prevents duplicate builds', async () => {
    body.failed_topics = 1
    body.successful_topics = 2
    vi.mocked(post).mockResolvedValue({})
    await render()
    await click('Retry failed topics')
    expect(post).toHaveBeenCalledExactlyOnceWith('/api/overview')
    status = { ...status, busy: true, overview_building: true }
    await act(async () => vi.advanceTimersByTimeAsync(5000))
    expect(button('Retry failed topics').disabled).toBe(true)
    await click('Retry failed topics')
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('offers partial topics during a build without starting a second one', async () => {
    body.complete = false
    body.topics_done = 1
    body.sections = [body.sections[0]]
    status.overview_building = true
    await render()
    expect(button('Building…').disabled).toBe(true)
    expect(container.textContent).toContain('Build in progress')
    await click('Facts from files')
    expect(panel().textContent).toContain('npm start')
    expect(post).not.toHaveBeenCalled()
  })
})
