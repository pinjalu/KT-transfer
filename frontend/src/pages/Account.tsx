import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAccount } from '../components/AuthGate'
import { Button, Card, PageHead } from '../components/ui'
import { post } from '../lib/api'
import { SourceCredentials, TeamAccounts } from '../components/TeamAccounts'

export function Account() {
  const account = useAccount()
  const [current, setCurrent] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function change(event: FormEvent) {
    event.preventDefault(); setError(''); setMessage('')
    if (password !== confirm) { setError('New passwords do not match.'); return }
    setBusy(true)
    try {
      await post('/api/auth/password', { current_password: current, new_password: password })
      setCurrent(''); setPassword(''); setConfirm('')
      await account.refresh()
      setMessage('Password changed. Other sessions have been signed out.')
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return <div className="account-section">
    <PageHead title="Account" lead={`Signed in as ${account.user.username}. Your sources, answers and connections belong to your private workspace.`} />
    <Card title="Change password" sub="Changing your password signs out all other sessions.">
      <form className="auth-form" onSubmit={change}>
        <input type="text" autoComplete="username" value={account.user.username} readOnly hidden />
        <label>Current password<input type="password" value={current} onChange={e => setCurrent(e.target.value)} autoComplete="current-password" required maxLength={128} /></label>
        <label>New password<input aria-label="New password" aria-describedby="new-password-help" type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" required minLength={15} maxLength={128} /><span id="new-password-help">Use 15–128 characters.</span></label>
        <label>Confirm new password<input type="password" value={confirm} onChange={e => setConfirm(e.target.value)} autoComplete="new-password" required maxLength={128} /></label>
        {error && <p role="alert" className="auth-error">{error}</p>}
        {message && <p role="status">{message}</p>}
        <Button type="submit" kind="primary" disabled={busy}>{busy ? 'Updating…' : 'Change password'}</Button>
      </form>
    </Card>
    <div className="account-actions"><Button onClick={() => void account.logout(true).catch(e => setError(e.message))}>Sign out all sessions</Button></div>
    <p className="auth-footnote">Sessions expire after 30 minutes without interaction or 8 hours after sign-in. Background jobs continue after sign-out; sign in to view their results.</p>
    <SourceCredentials />
    {account.user.role === 'owner' && <TeamAccounts />}
  </div>
}
