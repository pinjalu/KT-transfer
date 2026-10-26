import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TeamDecisions } from '../src/pages/TeamDecisions'
import { ApiError, get, post } from '../src/lib/api'
import { ProjectStatus } from '../src/lib/useStatus'
import type { Status } from '../src/lib/types'

vi.mock('../src/lib/api', async original => ({ ...await original<typeof import('../src/lib/api')>(), get: vi.fn(), post: vi.fn() }))
let root: ReturnType<typeof createRoot>
let container: HTMLDivElement
let detail: any
const status = { ready: true, busy: false, awaiting_project: false, knowledge_revision: 1 } as Status
const endpoint = '/api/decisions/channels/C1'
async function render() {
  await act(async () => root.render(<MemoryRouter><ProjectStatus.Provider value={{ data: status, error: null, loading: false, reload: vi.fn() }}><TeamDecisions /></ProjectStatus.Provider></MemoryRouter>))
}
beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  vi.mocked(get).mockReset(); vi.mocked(post).mockReset()
  detail = { channel: { id: 'C1', name: 'team' }, summary: null, read_at: null, coverage: { state: 'complete' },
    sources: [{ source_id: 'S1', path: 'slack/team', start: 1, text: 'I propose CONFIDENCE_THRESHOLD at 0.60.', url: '', partial: false, author: 'U1', message_ts: '1792993324.0' },
              { source_id: 'S2', path: 'slack/team', start: 2, text: 'Decision: keep CONFIDENCE_THRESHOLD at 0.45.', url: '', partial: false }],
    review: { passages_checked: 2, partial_passages: 0, positions: [
      { id: 'P1', source_id: 'S1', kind: 'proposal', text: 'I propose CONFIDENCE_THRESHOLD at 0.60.', reason: 'No adoption is established.' },
      { id: 'P2', source_id: 'S2', kind: 'decision', text: 'Decision: keep CONFIDENCE_THRESHOLD at 0.45.', reason: 'Agreement does not prove implementation.' }],
      comparisons: [{ subject: 'CONFIDENCE_THRESHOLD', kind: 'alternatives', reason: 'A proposal is not a conflicting agreement.', position_ids: ['P1', 'P2'] }] } }
  vi.mocked(get).mockImplementation(async path => {
    if (path === '/api/decisions/channels') return { channels: [{ id: 'C1', name: 'team', excerpts: 2 }] }
    if (path === endpoint) return detail
    throw new Error('Unexpected endpoint ' + path)
  })
  container = document.createElement('div'); document.body.append(container); root = createRoot(container)
})
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals() })

it('compares source positions without generating a summary and distinguishes a proposal from agreement', async () => {
  await render()
  const compared = container.querySelector('[aria-label="Compared positions"]')!
  expect(compared.textContent).toContain('Different proposed or recorded choices')
  expect(compared.textContent).toContain('Suggestion / proposal')
  expect(compared.textContent).toContain('Recorded agreement')
  expect(compared.textContent).toContain('0.60')
  expect(compared.textContent).toContain('0.45')
  expect(compared.textContent).not.toContain('Possible conflicting agreements')
  expect(container.textContent).toContain('newest message does not automatically win')
  expect(container.textContent).toContain('Recorded author: U1')
  expect(post).not.toHaveBeenCalled()
})

it('keeps both sides of a possible conflict and filters positions without additional reads', async () => {
  detail.review.comparisons[0].kind = 'conflict'
  detail.review.comparisons[0].reason = 'Review both; no winner is inferred.'
  await render()
  expect(container.querySelector('[aria-label="Compared positions"]')?.textContent).toContain('Possible conflicting agreements')
  const reads = vi.mocked(get).mock.calls.length
  const filter = container.querySelector<HTMLSelectElement>('[aria-label="Show source positions"]')!
  await act(async () => { filter.value = 'proposal'; filter.dispatchEvent(new Event('change', { bubbles: true })) })
  const positions = container.querySelector('[aria-label="Source positions"]')!
  expect(positions.textContent).toContain('0.60')
  expect(positions.textContent).not.toContain('0.45')
  expect(vi.mocked(get).mock.calls.length).toBe(reads)
  expect(post).not.toHaveBeenCalled()
})

it('shows rechecked legacy labels, incomplete coverage and inert source text', async () => {
  detail.review.positions[0].text = 'I propose <script>alert(1)</script>.'
  detail.review.partial_passages = 1
  detail.coverage.state = 'partial'
  detail.summary = { items: [], model: 'local-model', generated_at: '2026-10-26', parts: 2, passages_read: 2, labels_rechecked: true }
  await render()
  expect(container.textContent).toContain('Labels on this saved summary were rechecked')
  expect(container.textContent).toContain('partial passages cannot establish agreement')
  expect(container.textContent).toContain('<script>alert(1)</script>')
  expect(container.querySelector('script')).toBeNull()
  expect(container.textContent).toContain('Coverage partial')
})

it('withholds comparison evidence when source access fails', async () => {
  const original = vi.mocked(get).getMockImplementation()!
  vi.mocked(get).mockImplementation((path, signal) => {
    if (path === endpoint) return Promise.reject(new ApiError('Source access could not be verified.', 409))
    return original(path, signal)
  })
  await render()
  expect(container.textContent).toContain('Source access could not be verified.')
  expect(container.textContent).not.toContain('0.60')
  expect(container.querySelector('[aria-label="Source positions"]')).toBeNull()
})

it('distinguishes an explicitly recorded correction from an unresolved conflict', async () => {
  detail.review.comparisons[0].kind = 'recorded_update'
  detail.review.comparisons[0].reason = 'This thread reply explicitly replaces the earlier proposal.'
  await render()
  const compared = container.querySelector('[aria-label="Compared positions"]')!
  expect(compared.textContent).toContain('Recorded correction')
  expect(compared.textContent).toContain('0.60')
  expect(compared.textContent).toContain('0.45')
  expect(compared.textContent).not.toContain('Possible conflicting agreements')
})
