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
  status = { knowledge_revision: 1, busy: false, overview_building: false, awaiting_project: false, ready: true,
    settings: { repo: 'example/project', branch: 'main', platforms: ['github'] },
    scan: { id: 1, repo: 'example/project', branch: 'main', commit: 'abcdefg', status: 'complete' } } as Status
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
      return { available: true, repo: body.repo, branch: body.branch, scan_id: body.scan_id,
        commit: body.commit, knowledge_revision: status.knowledge_revision,
        features: [{ id: 'api', name: 'API', route_count: 2, file_count: 4, gap_count: 1 }], unclustered: { note: '' } }
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
  it('shows named sources, exact function links, every feature flow, and the ER map', async () => {
    const purpose = topic('purpose', 'Purpose')
    purpose.statements[0].text = 'The `match` function compares profiles.'
    purpose.statements[0].function_refs = [{ name: 'match', path: 'matching.py', line: 18,
      url: 'https://github.com/example/project/blob/abcdefg/matching.py#L18' }]
    body.sections = [purpose, topic('flows', 'Step by step'), topic('data', 'Data & settings')]
    body.systems = [{ id: 'primary', name: 'project' }]
    body.system_feature_flows = { primary: [
      { id: 'match', name: 'Matching', route_count: 2, more_steps: 0, steps: [
        { n: 1, label: 'POST /match', plain: 'Receives the request.',
          component: { kind: 'route', name: 'matching.py', path: 'matching.py', line: 8,
            url: 'https://github.com/example/project/blob/abcdefg/matching.py#L8' } }] },
      { id: 'accounts', name: 'Accounts', route_count: 1, more_steps: 0, steps: [
        { n: 1, label: 'GET /accounts', plain: 'Returns accounts.',
          component: { kind: 'route', name: 'accounts.py', path: 'accounts.py', line: 4,
            url: 'https://github.com/example/project/blob/abcdefg/accounts.py#L4' } }] },
    ] }
    body.system_diagrams = { primary: [{ key: 'er', kind: 'graph', title: 'How saved information connects',
      plain: 'Entities from files.', note: 'Declarations only.', circular: 0,
      nodes: [{ id: 'er:users', label: 'users', sublabel: 'id, name', fields: ['id', 'name'],
        path: 'schema.sql', line: 1, url: 'https://github.com/example/project/blob/abcdefg/schema.sql#L1',
        kind: 'entity', column: 0, row: 0 }], edges: [] }] }
    await render()
    expect(panel().textContent).toContain('Open function:')
    expect(panel().querySelector<HTMLAnchorElement>('.said-functions a')?.href).toContain('matching.py#L18')
    expect(panel().querySelector('.cite')?.textContent).toBe('View source: README.md')
    expect(panel().textContent).not.toContain('[1]')
    await click('Step by step')
    expect(panel().querySelectorAll('.ov-main-flow-list details')).toHaveLength(2)
    expect(panel().textContent).toContain('Matching')
    expect(panel().textContent).toContain('Accounts')
    await act(async () => { panel().querySelector<HTMLDetailsElement>('.ov-main-flow-list details')!.open = true })
    expect(panel().querySelector<HTMLAnchorElement>('.ov-main-flow-list .source-link')?.href).toContain('matching.py#L8')
    await click('Data & settings')
    expect(panel().querySelector('svg[aria-label="How saved information connects"]')).not.toBeNull()
    expect(panel().textContent).toContain('Entities from files.')
    expect(post).not.toHaveBeenCalled()
  })

  it('puts the problem and solution before technical shortcuts and opens each step of the user flow', async () => {
    const purpose = topic('purpose', 'The problem, the solution and what happens', 5)
    const lines = [
      '**Problem:** Customers need to find their parcel.',
      '**Solution:** Parcel desk lets them look up a parcel number.',
      '**You do (illustrative):** Enter a sample parcel number; this was not run.',
      '**Project does:** Parcel desk looks up the saved status.',
      '**You get:** The customer sees the parcel status.',
    ]
    purpose.statements.forEach((statement, index) => { statement.text = lines[index] })
    purpose.story = { problem: 0, solution: 1, input: 2, process: 3, output: 4 }
    body.sections[0] = purpose
    await render()
    const cards = container.querySelector('.ov-story-cards')!
    expect(cards.textContent).toContain('Customers need to find their parcel')
    expect(cards.textContent).toContain('Parcel desk lets them look up')
    expect(cards.textContent).toContain('customer sees the parcel status')
    expect(container.querySelector('.ov-story')!.compareDocumentPosition(container.querySelector('.ov-project-details')!)
      & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    const flow = container.querySelector('.ov-story-flow')!
    expect(flow.querySelectorAll('button')).toHaveLength(3)
    expect(flow.textContent).toContain('this was not run')
    await act(async () => flow.querySelectorAll('button')[1].click())
    expect(container.querySelector('[role="region"][aria-label="Project does details"]')?.textContent)
      .toContain('looks up the saved status')
    const source = container.querySelector<HTMLDetailsElement>('#src-source-1')!
    expect(source.open).toBe(false)
    await act(async () => container.querySelector('.ov-story-card a.cite')!.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect(source.open).toBe(true)
    expect(post).not.toHaveBeenCalled()
  })

  it('keeps separate project stories separate and makes missing flow steps visible', async () => {
    const first = { ...topic('purpose', 'Purpose', 1), system_id: 'github', system_name: 'BSA_chatbot',
      story: { problem: 0 } }
    first.statements[0].text = '**Problem:** A dealer needs an answer about a motorcycle.'
    const second = { ...topic('purpose', 'Purpose', 1), system_id: 'local', system_name: 'famas_matching_square',
      story: { solution: 0 } }
    second.statements[0].text = '**Solution:** A matching tool compares saved profiles.'
    body.sections = [{ ...first, system_sections: [first, second],
      statements: [...first.statements, ...second.statements], sources: [...first.sources, ...second.sources] }]
    await render()
    const systems = panel().querySelectorAll('.ov-system')
    expect(systems).toHaveLength(2)
    expect(systems[0].querySelector('.ov-story')?.textContent).toContain('motorcycle')
    expect(systems[0].querySelector('.ov-story')?.textContent).not.toContain('matching tool')
    expect(systems[1].querySelector('.ov-story')?.textContent).toContain('matching tool')
    expect(systems[1].querySelector('.ov-story')?.textContent).not.toContain('motorcycle')
    expect(systems[1].querySelector('.ov-story-flow')?.textContent).toContain('A user action was not confirmed')
    expect(panel().querySelectorAll('[id^="ov-story-step-detail-"]')).toHaveLength(2)
  })

  it.each(['example/project', 'local:D:/Projects/shop', 'zip:D:/managed/source'])('shows simple reading help for every topic and source: %s', async repo => {
    body.repo = repo
    status.settings!.repo = repo
    status.scan!.repo = repo
    body.sections = ['purpose','technologies','architecture','setup','flows','interfaces','data','testing','decisions'].map(key => topic(key, key))
    body.topics_total = body.topics_done = 9
    await render()
    for (const label of ['Start here','Technology','Code structure','Getting started','Step by step','Ways to use it','Data & settings','Testing','Team context','Main features','Facts from files','Reading checklist','Gaps & coverage']) {
      await click(label)
      expect(panel().querySelector('[aria-label="Help for new readers"]')).not.toBeNull()
      expect(panel().textContent).toContain('Words made simple')
    }
    await click('Developer')
    expect(panel().querySelector('[aria-label="Help for new readers"]')).toBeNull()
    await click('Architect')
    expect(panel().querySelector('[aria-label="Help for new readers"]')).toBeNull()
    expect(post).not.toHaveBeenCalled()
  })

  it('offers a rebuild for an older explanation without quietly generating new content', async () => {
    body.plain_language_update_available = true
    await render()
    expect(container.textContent).toContain('project-specific problem and solution')
    expect(container.textContent).toContain('Unsupported or instruction-like claims are hidden')
    expect(container.textContent).toContain('named source links remain available')
    expect(container.querySelector('.ov-saved-state')?.textContent).toContain('Explanation update available')
    expect(post).not.toHaveBeenCalled()
    await click('Update saved explanation')
    expect(post).toHaveBeenCalledExactlyOnceWith('/api/overview')
  })
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

  it('shows only local-folder metadata and current local cards for an older mixed workspace', async () => {
    status.settings = { ...status.settings!, selected_source: 'local', project_name: 'famas_matching_square',
      local: { repo: 'local:D:/famas_matching_square', path: 'D:/famas_matching_square' } }
    body = { ...body, project_name: 'famas_matching_square', source_kind: 'local', overview_scope: 'local://snapshot/',
      repo: 'local:D:/famas_matching_square', files_indexed: 105, files_skipped: 29,
      overview_features: { available: true, repo: 'local:D:/famas_matching_square', branch: body.branch,
        scan_id: body.scan_id, commit: body.commit, knowledge_revision: 1,
        features: [{ id: 'matching', name: 'Matching', route_count: 1, file_count: 2, gap_count: 0 }], unclustered: { note: '' } } }
    await render()
    expect(container.querySelector('.ov-hero h2')?.textContent).toBe('famas_matching_square')
    expect(container.querySelector('.ov-hero-meta')?.textContent).toBe('Local folder')
    expect(container.querySelector('.ov-hero')?.textContent).not.toContain('abcdefg')
    expect(container.querySelector('.ov-hero')?.textContent).not.toContain('example/project')
    const files = [...container.querySelectorAll('.ov-metric')].find(value => value.textContent?.includes('Files indexed'))!
    expect(files.querySelector('strong')?.textContent).toBe('105')
    expect(files.textContent).toContain('29 files skipped')
    await click('Main features')
    expect(panel().textContent).toContain('Matching')
    expect(panel().textContent).not.toContain('Explore API')
    expect(vi.mocked(get).mock.calls.some(([path]) => path === '/api/features')).toBe(false)
    await click('Gaps & coverage')
    expect(panel().querySelector('.ov-coverage')?.textContent).not.toContain('Commit')
    expect(panel().querySelector('.ov-coverage')?.textContent).not.toContain('abcdefg')
  })

  it('keeps the two systems’ explanations and failures separate in the same topic', async () => {
    const first = { ...topic('flows', 'Flow'), system_id: 'primary', system_name: 'BSA_chatbot' }
    first.statements[0].text = 'A dealer asks a motorcycle question.'
    const second = { ...topic('flows', 'Flow'), system_id: 'local://snapshot/', system_name: 'famas_matching_square',
      statements: [], sources: [], error: 'Local model unavailable' }
    body.systems = [{ id: first.system_id, name: first.system_name }, { id: second.system_id, name: second.system_name }]
    body.sections = [{ ...first, system_sections: [first, second] }]
    await render()
    const groups = panel().querySelectorAll('.ov-system')
    expect(groups).toHaveLength(2)
    expect(groups[0].textContent).toContain('A dealer asks a motorcycle question')
    expect(groups[0].textContent).not.toContain('Local model unavailable')
    expect(groups[1].textContent).toContain('famas_matching_square')
    expect(groups[1].textContent).toContain('Local model unavailable')
    expect(groups[1].textContent).not.toContain('motorcycle')
  })

  it('navigates topics and exposes all points without requesting a build or fetching again', async () => {
    await render()
    expect(panel().textContent).toContain('Project purpose point 3')
    expect(panel().textContent).toContain('Project purpose point 4')
    expect(panel().textContent).toContain('Project purpose point 5')
    const guide = panel().querySelector('[aria-label="Help for new readers"]')!
    expect(guide.querySelector('details')?.open).toBe(false)
    const statements = panel().querySelector('a.cite')!
    expect(statements.compareDocumentPosition(guide) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
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

  it('clears Main features at overview start and waits for features from the current project', async () => {
    await render()
    await click('Main features')
    expect(panel().querySelector('.ov-feature h3')?.textContent).toBe('API')
    let finish!: (value: unknown) => void
    const normal = vi.mocked(get).getMockImplementation()!
    vi.mocked(get).mockImplementation((path, signal) => path === '/api/features'
      ? new Promise(resolve => { finish = resolve }) : normal(path, signal))
    status = { ...status, overview_building: true, busy: true }
    await act(async () => vi.advanceTimersByTimeAsync(5000))
    expect(panel().querySelector('.ov-feature')).toBeNull()
    expect(panel().textContent).toContain('Finding features in this project')
    const metric = [...container.querySelectorAll('.ov-metric')].find(el => el.textContent?.includes('Feature groups'))!
    expect(metric.querySelector('strong')?.textContent).toBe('…')
    await act(async () => finish({ available: true, repo: body.repo, branch: body.branch,
      scan_id: body.scan_id, commit: body.commit, knowledge_revision: status.knowledge_revision,
      features: [{ id: 'inventory', name: 'Inventory', route_count: 1, file_count: 2, gap_count: 0 }] }))
    expect(panel().querySelector('.ov-feature h3')?.textContent).toBe('Inventory')
    expect(panel().textContent).not.toContain('Explore API')
  })

  it('never displays features returned for a different project, even with the same scan number', async () => {
    const normal = vi.mocked(get).getMockImplementation()!
    vi.mocked(get).mockImplementation(async (path, signal) => path === '/api/features'
      ? { ...(await normal(path, signal) as object), repo: 'acme/old-project' } : normal(path, signal))
    await render()
    await click('Main features')
    expect(panel().querySelector('.ov-feature')).toBeNull()
    expect(panel().querySelector('[role="alert"]')?.textContent).toContain('do not match the current project')
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
