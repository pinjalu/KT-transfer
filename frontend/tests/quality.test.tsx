import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Quality } from '../src/pages/Quality'
import { ApiError, get, post } from '../src/lib/api'
import { ProjectStatus } from '../src/lib/useStatus'
import type { Status } from '../src/lib/types'

vi.mock('../src/lib/api', async original => ({ ...await original<typeof import('../src/lib/api')>(), get: vi.fn(), post: vi.fn() }))
let root: ReturnType<typeof createRoot>
let container: HTMLDivElement
let status: Status
let catalog: any
const reload = vi.fn()
const casePath = '/api/quality/runs/8/cases/boundary'
const result = { case_id: 'boundary', status: 'passed_checks', response_hash: 'a'.repeat(64), answer_id: 4,
  human_review: null, behavior_check: true, retrieval: { reference_excerpt_found: true },
  citations: { unknown_ids: 0, uncited_statements: 0, invalid_github_links: 0, external_links_not_checked: 0 }, reference_phrase_checks: [] }
const detail = { dataset_hash: 'b'.repeat(64), case: { id: 'boundary', question: 'Does 0.45 trigger handoff?', behavior: 'answer' }, result,
  answer: { statements: [{ text: 'The strict comparison is false.', source_ids: ['S1'], support: 'supported', about_this_project: true }],
    sources: [{ source_id: 'S1', path: 'main.py', start: 1, end: 2, text: 'score < 0.45', url: 'https://github.com/acme/shop/blob/abc/main.py#L1-L2' }],
    missing_information: '', error: null } }
async function render() {
  await act(async () => root.render(<MemoryRouter><ProjectStatus.Provider value={{ data: status, error: null, loading: false, reload }}><Quality /></ProjectStatus.Provider></MemoryRouter>))
}
const button = (text: string) => Array.from(container.querySelectorAll('button')).find(b => b.textContent === text)!
async function click(text: string) { await act(async () => button(text).click()) }
async function select(index: number, value: string) {
  await act(async () => {
    const element = container.querySelectorAll('select')[index]
    element.value = value; element.dispatchEvent(new Event('change', { bubbles: true }))
  })
}
beforeEach(() => {
  vi.useFakeTimers(); vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  vi.mocked(get).mockReset(); vi.mocked(post).mockReset(); reload.mockReset()
  status = { ready: true, awaiting_project: false, busy: false, knowledge_revision: 1 } as Status
  catalog = { sets: [{ id: 'bsa', title: 'Boundary questions', repo: 'acme/shop', commit: 'a'.repeat(40), cases: 1, available: true, reason: '' }],
    runs: [{ id: 8, title: 'Boundary questions', state: 'succeeded', model: 'local-model', started_at: '2026-10-26', scan_status: 'partial',
      cases_planned: 1, results: [result], summary: { automatic_checks_passed: 1, human_reviewed: 0, human_correctness: {}, human_source_sufficiency: {} } }] }
  vi.mocked(get).mockImplementation(async path => {
    if (path === '/api/quality') return catalog
    if (path === casePath) return detail
    throw new Error('Unexpected endpoint ' + path)
  })
  container = document.createElement('div'); document.body.append(container); root = createRoot(container)
})
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.useRealTimers(); vi.unstubAllGlobals() })

it('keeps mechanical checks separate from human ratings and inspects the saved answer', async () => {
  await render()
  expect(container.textContent).toContain('Automatic checks are not an accuracy score')
  expect(container.textContent).toContain('Not reviewed')
  expect(post).not.toHaveBeenCalled()
  await click('Inspect boundary')
  expect(container.textContent).toContain('The strict comparison is false.')
  expect(container.textContent).toContain('score < 0.45')
  expect(container.querySelector('.cite')?.getAttribute('href')).toBe('#src-quality-8-boundary-S1')
  expect(container.querySelector('#src-quality-8-boundary-S1')).not.toBeNull()
  expect(button('Save my review').disabled).toBe(true)
  await select(2, 'incorrect')
  expect(button('Save my review').disabled).toBe(true)
  await select(3, 'insufficient')
  vi.mocked(post).mockResolvedValue({ saved: true })
  await click('Save my review')
  expect(post).toHaveBeenCalledWith(casePath + '/review', { dataset_hash: 'b'.repeat(64), response_hash: 'a'.repeat(64), correctness: 'incorrect', source_sufficiency: 'insufficient' })
  expect(container.textContent).toContain('Review saved for this exact answer.')
})

it('starts a background job and prevents starts for mismatched scope or busy service', async () => {
  await render()
  vi.mocked(post).mockResolvedValue({ job_id: 9 })
  await click('Run evaluation')
  expect(post).toHaveBeenCalledWith('/api/quality/runs', { set_id: 'bsa' })
  status = { ...status, busy: true }; await render()
  expect(button('Run evaluation').disabled).toBe(true)
  status = { ...status, busy: false, knowledge_revision: 2 }
  catalog = { ...catalog, sets: [{ ...catalog.sets[0], available: false, reason: 'The commit does not match.' }] }
  await render()
  expect(button('Run evaluation').disabled).toBe(true)
  expect(container.textContent).toContain('The commit does not match.')
})

it('withholds saved excerpts when inspection access fails', async () => {
  vi.mocked(get).mockImplementation(async path => {
    if (path === '/api/quality') return catalog
    throw new ApiError('Source access could not be verified.', 409)
  })
  await render(); await click('Inspect boundary')
  expect(container.textContent).toContain('Source access could not be verified.')
  expect(container.textContent).not.toContain('score < 0.45')
  expect(container.querySelectorAll('select')).toHaveLength(2)
})

it('shows failed review writes without reporting a saved review', async () => {
  await render(); await click('Inspect boundary')
  await select(2, 'correct'); await select(3, 'sufficient')
  vi.mocked(post).mockRejectedValue(new Error('The sources changed.'))
  await click('Save my review')
  expect(container.textContent).toContain('The sources changed.')
  expect(container.textContent).not.toContain('Review saved')
})

it('requires project selection before reading evaluations', async () => {
  status = { ...status, awaiting_project: true }
  await render()
  expect(container.textContent).toContain('No project is selected.')
  expect(get).not.toHaveBeenCalled()
})
