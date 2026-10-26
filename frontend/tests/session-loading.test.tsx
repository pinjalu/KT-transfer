import { act, useEffect } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthGate } from '../src/components/AuthGate'
import { AUTH_REQUIRED, ApiError, get, post } from '../src/lib/api'
import { useApi } from '../src/lib/useApi'
import type { Load } from '../src/lib/useApi'
import { useOverview } from '../src/lib/useOverview'
import type { Status } from '../src/lib/types'

vi.mock('../src/lib/api', async original => ({
  ...await original<typeof import('../src/lib/api')>(), get: vi.fn(), post: vi.fn(),
}))

function deferred<T = unknown>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function session(id = 1) {
  return { authenticated: true, setup_required: false,
    user: { id, username: `user${id}`, role: id === 1 ? 'owner' : 'member',
      expires_at: Date.now() / 1000 + 3600, idle_expires_at: Date.now() / 1000 + 1800 } }
}
let container: HTMLDivElement
let root: ReturnType<typeof createRoot>
let mounts: number
class Channel {
  static current: Channel
  onmessage: (() => void) | null = null
  constructor() { Channel.current = this }
  postMessage() {}
  close() {}
}
function Draft() {
  useEffect(() => { mounts++ }, [])
  return <input aria-label="draft" defaultValue="" />
}
async function render(node: ReactNode) { await act(async () => root.render(node)) }
async function visible() {
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
}
beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  vi.stubGlobal('BroadcastChannel', Channel)
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  vi.mocked(get).mockReset()
  vi.mocked(post).mockReset()
  mounts = 0
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

describe('session checks when returning to a browser tab', () => {
  it('keeps the workspace visible during tab verification and preserves the same account draft', async () => {
    vi.mocked(get).mockResolvedValue(session())
    await render(<AuthGate><Draft /></AuthGate>)
    const input = container.querySelector('input')!
    input.value = 'keep this question'
    const pending = deferred()
    vi.mocked(get).mockReturnValueOnce(pending.promise)
    await visible()
    expect(container.querySelector('.auth-workspace')?.hasAttribute('hidden')).toBe(false)
    expect(container.querySelector('.auth-workspace')?.hasAttribute('inert')).toBe(false)
    expect(container.textContent).not.toContain('Checking sign-in')
    expect(mounts).toBe(1)
    await act(async () => pending.resolve(session()))
    expect(container.querySelector('input')).toBe(input)
    expect(input.value).toBe('keep this question')
    expect(container.querySelector('.auth-workspace')?.hasAttribute('hidden')).toBe(false)
  })

  it('shares an in-flight check across rapid tab returns without reloading page data', async () => {
    vi.mocked(get).mockResolvedValueOnce(session()).mockResolvedValueOnce({ overview: 'saved' })
    await render(<AuthGate><Reader revision={4} /></AuthGate>)
    const pending = deferred()
    vi.mocked(get).mockReturnValueOnce(pending.promise)
    await visible()
    await visible()
    await visible()
    expect(vi.mocked(get).mock.calls.filter(([path]) => path === '/api/auth/status')).toHaveLength(2)
    expect(vi.mocked(get).mock.calls.filter(([path]) => path === '/api/overview')).toHaveLength(1)
    expect(container.textContent).toContain('saved')
    await act(async () => pending.resolve(session()))
    expect(vi.mocked(get).mock.calls.filter(([path]) => path === '/api/overview')).toHaveLength(1)
  })

  it('blocks a potentially changed account even while a quiet tab check is pending', async () => {
    vi.mocked(get).mockResolvedValueOnce(session())
    await render(<AuthGate><Draft /></AuthGate>)
    const quiet = deferred()
    const changed = deferred()
    vi.mocked(get).mockReturnValueOnce(quiet.promise).mockReturnValueOnce(changed.promise)
    await visible()
    await act(async () => Channel.current.onmessage?.())
    expect(container.querySelector('.auth-workspace')?.hasAttribute('hidden')).toBe(true)
    await act(async () => quiet.resolve(session()))
    expect(container.querySelector('.auth-workspace')?.hasAttribute('hidden')).toBe(true)
    await act(async () => changed.resolve({ authenticated: false, setup_required: false, user: null }))
    expect(container.querySelector('[aria-label="draft"]')).toBeNull()
    expect(container.textContent).toContain('Welcome back')
  })

  it('blocks verification after restoring a page from the back-forward cache', async () => {
    vi.mocked(get).mockResolvedValueOnce(session())
    await render(<AuthGate><Draft /></AuthGate>)
    const pending = deferred()
    vi.mocked(get).mockReturnValueOnce(pending.promise)
    const event = new Event('pageshow')
    Object.defineProperty(event, 'persisted', { value: true })
    await act(async () => window.dispatchEvent(event))
    expect(container.querySelector('.auth-workspace')?.hasAttribute('hidden')).toBe(true)
    await act(async () => pending.resolve(session()))
    expect(container.querySelector('.auth-workspace')?.hasAttribute('hidden')).toBe(false)
  })

  it('does not leave expired content visible or accept a check started before expiry', async () => {
    const expiring = session()
    expiring.user.idle_expires_at = Date.now() / 1000 + 1
    vi.mocked(get).mockResolvedValueOnce(expiring)
    await render(<AuthGate><Draft /></AuthGate>)
    const quiet = deferred()
    const expired = deferred()
    vi.mocked(get).mockReturnValueOnce(quiet.promise).mockReturnValueOnce(expired.promise)
    await visible()
    await act(async () => vi.advanceTimersByTime(1000))
    expect(container.querySelector('[aria-label="draft"]')).toBeNull()
    await act(async () => quiet.resolve(session()))
    expect(container.querySelector('[aria-label="draft"]')).toBeNull()
    await act(async () => expired.resolve({ authenticated: false, setup_required: false, user: null }))
    expect(container.textContent).toContain('Welcome back')
  })

  it('requires blocking verification if expiry passed while the tab was suspended', async () => {
    const expiring = session()
    expiring.user.idle_expires_at = Date.now() / 1000 + 1
    vi.mocked(get).mockResolvedValueOnce(expiring)
    await render(<AuthGate><Draft /></AuthGate>)
    vi.setSystemTime(Date.now() + 2000)
    const pending = deferred()
    vi.mocked(get).mockReturnValueOnce(pending.promise)
    await visible()
    expect(container.querySelector('.auth-workspace')?.hasAttribute('hidden')).toBe(true)
    await act(async () => pending.resolve({ authenticated: false, setup_required: false, user: null }))
    expect(container.querySelector('[aria-label="draft"]')).toBeNull()
  })

  it('discards private state when a different account becomes active', async () => {
    vi.mocked(get).mockResolvedValueOnce(session()).mockResolvedValueOnce(session(2))
    await render(<AuthGate><Draft /></AuthGate>)
    container.querySelector('input')!.value = 'owner draft'
    await visible()
    expect(container.querySelector('input')!.value).toBe('')
    expect(mounts).toBe(2)
  })

  it('removes private content on a cross-tab logout', async () => {
    vi.mocked(get).mockResolvedValueOnce(session()).mockResolvedValueOnce({ authenticated: false, setup_required: false, user: null })
    await render(<AuthGate><Draft /></AuthGate>)
    await act(async () => Channel.current.onmessage?.())
    expect(container.querySelector('[aria-label="draft"]')).toBeNull()
    expect(container.textContent).toContain('Welcome back')
  })

  it('fails closed when session verification cannot reach the server', async () => {
    vi.mocked(get).mockResolvedValueOnce(session()).mockRejectedValueOnce(new Error('Offline'))
    await render(<AuthGate><Draft /></AuthGate>)
    await visible()
    expect(container.querySelector('[aria-label="draft"]')).toBeNull()
    expect(container.textContent).toContain('Unable to check sign-in')
  })

  it('ignores an old verification response after a protected request reports logout', async () => {
    vi.mocked(get).mockResolvedValueOnce(session())
    await render(<AuthGate><Draft /></AuthGate>)
    const pending = deferred()
    vi.mocked(get).mockReturnValueOnce(pending.promise)
    await visible()
    await act(async () => window.dispatchEvent(new Event(AUTH_REQUIRED)))
    await act(async () => pending.resolve(session()))
    expect(container.querySelector('[aria-label="draft"]')).toBeNull()
    expect(container.textContent).toContain('Your session ended')
  })

  it('ignores activity responses that belong to the previous account', async () => {
    vi.mocked(get).mockResolvedValueOnce(session()).mockResolvedValueOnce(session(2))
    await render(<AuthGate><Draft /></AuthGate>)
    const pending = deferred()
    vi.mocked(post).mockReturnValueOnce(pending.promise)
    await act(async () => window.dispatchEvent(new Event('pointerdown')))
    await visible()
    const input = container.querySelector('input')!
    input.value = 'member draft'
    await act(async () => pending.resolve({ user: session().user }))
    expect(container.querySelector('input')).toBe(input)
    expect(input.value).toBe('member draft')
    expect(mounts).toBe(2)
  })
})

let load: Load<unknown>
function Reader({ revision, enabled = true, poll = 0 }: { revision?: number; enabled?: boolean; poll?: number }) {
  load = useApi('/api/overview', poll, revision, enabled)
  return <div>{load.loading ? 'Loading' : load.error || JSON.stringify(load.data)}</div>
}
describe('source requests', () => {
  it('waits for the revision before making one initial read', async () => {
    vi.mocked(get).mockResolvedValue({ overview: 'saved' })
    await render(<Reader enabled={false} />)
    expect(get).not.toHaveBeenCalled()
    await render(<Reader enabled revision={4} />)
    expect(get).toHaveBeenCalledTimes(1)
    expect(load.data).toEqual({ overview: 'saved' })
  })

  it('does not restart or overlap a slow request when the polling rate changes', async () => {
    const pending = deferred()
    vi.mocked(get).mockReturnValue(pending.promise)
    await render(<Reader revision={4} poll={30000} />)
    const signal = vi.mocked(get).mock.calls[0][1]!
    await render(<Reader revision={4} poll={4000} />)
    await act(async () => vi.advanceTimersByTime(12000))
    expect(get).toHaveBeenCalledTimes(1)
    expect(signal.aborted).toBe(false)
    await act(async () => pending.resolve({ overview: 'finished' }))
    expect(load.loading).toBe(false)
  })

  it('aborts old reads and prevents stale content returning after a revision change', async () => {
    const old = deferred()
    const current = deferred()
    vi.mocked(get).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
    await render(<Reader revision={4} />)
    const signal = vi.mocked(get).mock.calls[0][1]!
    await render(<Reader revision={5} />)
    expect(signal.aborted).toBe(true)
    await act(async () => old.resolve({ private: 'obsolete' }))
    expect(load.loading).toBe(true)
    expect(load.data).toBeNull()
    await act(async () => current.resolve({ current: true }))
    expect(load.data).toEqual({ current: true })
  })

  it('clears saved content when a later permission check is denied', async () => {
    vi.mocked(get).mockResolvedValueOnce({ private: true }).mockRejectedValueOnce(new ApiError('Access denied', 403))
    await render(<Reader revision={4} poll={30000} />)
    expect(load.data).toEqual({ private: true })
    await act(async () => vi.advanceTimersByTime(30000))
    expect(load.data).toBeNull()
    expect(load.error).toBe('Access denied')
  })

  it('requires a new successful read after status temporarily becomes unavailable', async () => {
    vi.mocked(get).mockResolvedValueOnce({ private: true })
    await render(<Reader revision={4} />)
    await render(<Reader revision={4} enabled={false} />)
    const pending = deferred()
    vi.mocked(get).mockReturnValueOnce(pending.promise)
    await render(<Reader revision={4} />)
    expect(load.data).toBeNull()
    expect(load.loading).toBe(true)
    await act(async () => pending.resolve({ checked: true }))
    expect(load.data).toEqual({ checked: true })
  })
})

function OverviewReader({ state = 'succeeded' }: { state?: 'running' | 'succeeded' }) {
  load = useOverview({ data: { knowledge_revision: 4, overview_building: state === 'running',
    job: { id: 2, kind: 'overview', state } } as Status, error: null, loading: false, reload: () => {} })
  return <div>{JSON.stringify(load.data)}</div>
}
describe('overview updates', () => {
  it('keeps idle content until explicitly refreshed without starting a model build', async () => {
    vi.mocked(get).mockResolvedValue({ available: true })
    await render(<OverviewReader />)
    await act(async () => vi.advanceTimersByTime(60000))
    expect(get).toHaveBeenCalledTimes(1)
    await act(async () => load.reload())
    expect(get).toHaveBeenCalledTimes(2)
    expect(post).not.toHaveBeenCalled()
  })

  it('loads the final overview when the background build completes', async () => {
    vi.mocked(get).mockResolvedValueOnce({ building: true }).mockResolvedValueOnce({ building: false, complete: true })
    await render(<OverviewReader state="running" />)
    await render(<OverviewReader state="succeeded" />)
    expect(get).toHaveBeenCalledTimes(2)
    expect(load.data).toEqual({ building: false, complete: true })
  })
})
