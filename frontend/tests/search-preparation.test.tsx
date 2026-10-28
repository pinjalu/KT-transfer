import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { BackgroundJob } from '../src/components/BackgroundJob'
import { SearchPreparation } from '../src/components/SearchPreparation'
import { ApiError, post } from '../src/lib/api'
import type { BackgroundJob as Job, Status } from '../src/lib/types'

vi.mock('../src/lib/api', async original => ({
  ...await original<typeof import('../src/lib/api')>(), post: vi.fn(),
}))

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>
const changed = vi.fn()
beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  vi.mocked(post).mockReset().mockResolvedValue({ ok: true })
  changed.mockReset()
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
})
afterEach(async () => {
  await act(async () => root.unmount())
  container.remove()
  vi.unstubAllGlobals()
})
const job: Job = { id: 7, kind: 'local', state: 'running', attempt: 1, error: '',
  started_at: '', finished_at: null, can_cancel: true, can_retry: false, can_skip_index: true,
  progress: { phase: 'Preparing search index', embed_done: 1, embed_total: 2, embed_reused: 992 } }
function button(label: string) {
  const result = [...container.querySelectorAll('button')].find(item => item.textContent === label)
  if (!result) throw new Error(`Button missing: ${label}`)
  return result
}

it('shows reused text and switches a running import to basic search without cancelling it', async () => {
  await act(async () => root.render(<BackgroundJob job={job} onChanged={changed} />))
  expect(container.textContent).toContain('1 of 2 new or changed text sections')
  expect(container.textContent).toContain('992 sections already indexed')
  expect(container.textContent).toContain('may miss results')
  await act(async () => button('Use basic search now').click())
  expect(post).toHaveBeenCalledExactlyOnceWith('/api/jobs/7/basic-search')
  expect(changed).toHaveBeenCalledOnce()
})

it('keeps errors visible and does not offer the shortcut after completion', async () => {
  vi.mocked(post).mockRejectedValue(new ApiError('Refresh its status.', 409))
  await act(async () => root.render(<BackgroundJob job={job} onChanged={changed} />))
  await act(async () => button('Use basic search now').click())
  expect(container.querySelector('[role="alert"]')?.textContent).toContain('Refresh its status.')
  await act(async () => root.render(<BackgroundJob job={{ ...job, state: 'succeeded', can_cancel: false,
    can_skip_index: false, search_mode: 'basic', progress: null }} onChanged={changed} />))
  expect(container.textContent).toContain('Ready with basic word search')
  expect(container.textContent).not.toContain('Use basic search now')
})

it('lets the user choose basic search before import and turn meaning search back on', async () => {
  const status = { semantic_available: true, search_mode: 'semantic', busy: false } as Status
  await act(async () => root.render(<SearchPreparation status={status} onChanged={changed} />))
  await act(async () => button('Use basic search').click())
  expect(post).toHaveBeenLastCalledWith('/api/search-mode', { mode: 'basic' })
  await act(async () => root.render(<SearchPreparation status={{ ...status, search_mode: 'basic' }} onChanged={changed} />))
  await act(async () => button('Use meaning search').click())
  expect(post).toHaveBeenLastCalledWith('/api/search-mode', { mode: 'semantic' })
  await act(async () => root.render(<SearchPreparation status={{ ...status, busy: true }} onChanged={changed} />))
  expect(button('Use basic search').disabled).toBe(true)
})
