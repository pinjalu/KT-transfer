import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { AUTH_REQUIRED, get, post } from '../lib/api'
import { Button } from './ui'
import './auth.css'

type User = { id: number; role: 'owner' | 'member'; username: string; expires_at: number; idle_expires_at: number }
type Session = { authenticated: boolean; setup_required: boolean; user: User | null }
const Account = createContext<{ user: User; refresh: () => Promise<void>; logout: (all?: boolean) => Promise<void> } | null>(null)
export function useAccount() { return useContext(Account)! }

export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(false)
  const channel = useRef<BroadcastChannel | null>(null)
  const sequence = useRef(0)
  const lastActivity = useRef(0)
  const refresh = useCallback(async () => {
    const request = ++sequence.current
    setChecking(true)
    try {
      const value = await get('/api/auth/status') as Session
      if (sequence.current === request) { setSession(value); setError('') }
    } catch (e) {
      if (sequence.current === request) { setSession(null); setError((e as Error).message) }
    } finally {
      if (sequence.current === request) setChecking(false)
    }
  }, [])
  const changed = useCallback(async () => {
    channel.current?.postMessage('changed')
    await refresh()
  }, [refresh])
  const logout = useCallback(async (all = false) => {
    await post(all ? '/api/auth/logout-all' : '/api/auth/logout')
    ++sequence.current
    setChecking(false)
    setSession({ authenticated: false, setup_required: false, user: null })
    channel.current?.postMessage('changed')
    // Discard mounted answer/source state, including the back-forward cache of this page.
    window.history.replaceState(null, '', '/login')
  }, [])

  useEffect(() => {
    void refresh()
    const required = () => {
      ++sequence.current
      setChecking(false)
      setSession({ authenticated: false, setup_required: false, user: null })
      setError('Your session ended. Sign in again to continue.')
    }
    // Keep the mounted workspace while checking the same session. Clearing it here
    // discarded drafts and restarted every source request each time a tab was shown.
    // The workspace stays hidden until verified; a logout/account change still wipes it.
    const verify = () => { void refresh() }
    const visible = () => { if (document.visibilityState === 'visible') verify() }
    const restored = (event: PageTransitionEvent) => { if (event.persisted) verify() }
    if ('BroadcastChannel' in window) {
      channel.current = new BroadcastChannel('pka-account')
      channel.current.onmessage = verify
    }
    document.addEventListener('visibilitychange', visible)
    window.addEventListener('pageshow', restored)
    window.addEventListener(AUTH_REQUIRED, required)
    return () => {
      ++sequence.current
      channel.current?.close()
      document.removeEventListener('visibilitychange', visible)
      window.removeEventListener('pageshow', restored)
      window.removeEventListener(AUTH_REQUIRED, required)
    }
  }, [refresh])

  useEffect(() => {
    if (!session?.authenticated || !session.user) return
    const activity = () => {
      if (Date.now() - lastActivity.current < 60000 || document.hidden) return
      lastActivity.current = Date.now()
      const request = sequence.current
      const userId = session.user!.id
      void post('/api/auth/activity').then(value => {
        const updated = value as { user: User }
        if (request === sequence.current && updated.user.id === userId) {
          setSession(current => current?.authenticated && current.user?.id === userId
            ? { ...current, user: updated.user } : current)
        }
      }).catch(() => {})
    }
    const timer = window.setInterval(() => {
      if (Date.now()/1000 >= Math.min(session.user!.expires_at, session.user!.idle_expires_at)) {
        setSession(null)
        void refresh()
      }
    }, 1000)
    window.addEventListener('pointerdown', activity)
    window.addEventListener('keydown', activity)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('pointerdown', activity)
      window.removeEventListener('keydown', activity)
    }
  }, [session?.authenticated, session?.user?.id, session?.user?.expires_at, session?.user?.idle_expires_at, refresh])

  if (session?.authenticated && session.user) {
    return <Account.Provider key={session.user.id} value={{ user: session.user, refresh: changed, logout }}>
      <div className="auth-workspace" hidden={checking} inert={checking}>{children}</div>
      {checking && <div className="auth-page" role="status">Checking sign-in…</div>}
    </Account.Provider>
  }
  return <div className="auth-page"><div className="auth-card">
    <div className="auth-brand"><span className="auth-mark">K</span> KT Assistant</div>
    {session ? <Login setup={session.setup_required} onSuccess={changed} notice={error} /> : <>
      <h1>{error ? 'Unable to check sign-in' : 'Checking sign-in…'}</h1>
      {error && <><p role="alert">{error}</p><Button onClick={() => void refresh()}>Try again</Button></>}
    </>}
  </div></div>
}

function Login({ setup, onSuccess, notice }: { setup: boolean; onSuccess: () => Promise<void>; notice: string }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (setup && password !== confirm) { setError('Passwords do not match.'); return }
    setBusy(true); setError('')
    try {
      await post(setup ? '/api/auth/setup' : '/api/auth/login', setup ? { username, password, code } : { username, password })
      setPassword(''); setConfirm(''); setCode('')
      if (window.location.pathname === '/login') window.history.replaceState(null, '', '/')
      await onSuccess()
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return <>
    <h1>{setup ? 'Create your owner account' : 'Welcome back'}</h1>
    <p>{setup ? 'Protect access to your saved projects, answers and connections on this computer.' : 'Sign in to your local KT Assistant account.'}</p>
    {notice && <p role="status" className="auth-notice">{notice}</p>}
    <form onSubmit={submit} className="auth-form">
      {setup && <label>One-time setup code<input aria-label="One-time setup code" aria-describedby="setup-help" value={code} onChange={e => setCode(e.target.value)} required maxLength={100} autoComplete="off" spellCheck={false} />
        <span id="setup-help">Open the setup-code file shown in the app’s startup terminal and paste its contents here.</span></label>}
      <label>Username<input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" required maxLength={80} minLength={setup ? 3 : 1} autoCapitalize="none" spellCheck={false} /></label>
      <label>Password<input aria-label="Password" aria-describedby={setup ? 'password-help' : undefined} type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete={setup ? 'new-password' : 'current-password'} required minLength={setup ? 15 : 1} maxLength={128} />
        {setup && <span id="password-help">Use 15–128 characters. Spaces and long passphrases are welcome.</span>}</label>
      {setup && <label>Confirm password<input type="password" value={confirm} onChange={e => setConfirm(e.target.value)} autoComplete="new-password" required maxLength={128} /></label>}
      {error && <p className="auth-error" role="alert">{error}</p>}
      <Button kind="primary" type="submit" disabled={busy}>{busy ? 'Please wait…' : setup ? 'Create account' : 'Sign in'}</Button>
    </form>
    <p className="auth-footnote">Your account has its own private workspace. Sessions end after 30 minutes of inactivity or 8 hours. Ask the installation owner to create a member account.</p>
    {!setup && <details><summary>Forgot your password?</summary><p>The installation owner can run <code>python -m pka --reset-password</code> in the app’s terminal to reset the owner password and end the owner’s sessions. For example mode, add <code>--demo</code>. Members should contact the installation owner.</p></details>}
  </>
}
