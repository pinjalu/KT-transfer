import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { get, post } from '../lib/api'
import { Button, Card } from './ui'

export { SourceCredentials } from './SourceCredentials'

type Member = { id: number; username: string; role: string; enabled: boolean }
type Audit = { id: number; actor: number | null; target: number | null; created: number; action: string; outcome: number }
export function TeamAccounts() {
  const [accounts, setAccounts] = useState<Member[]>([])
  const [audit, setAudit] = useState<Audit[]>([])
  const [before, setBefore] = useState<number | null>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function reload(cursor = 0) {
    const [members, records] = await Promise.all([get('/api/admin/accounts'), get('/api/admin/audit?before=' + cursor)])
    setAccounts((members as { accounts: Member[] }).accounts)
    setAudit((records as { records: Audit[] }).records)
    setBefore((records as { next_before: number | null }).next_before)
  }
  useEffect(() => { void reload().catch(e => setError(e.message)) }, [])
  async function create(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      await post('/api/admin/accounts', { username, password }); setUsername(''); setPassword('')
      setMessage('Member created with an empty private workspace. They can sign in and add their own sources.')
      await reload()
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  async function toggle(member: Member) {
    setBusy(true); setError('')
    try { await post(`/api/admin/accounts/${member.id}/enabled`, { enabled: !member.enabled }); await reload() }
    catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return <>
    <Card title="Members" sub="Each member connects their own sources. Accounts do not share imported content or credentials. Disabling a member ends their sessions.">
      <form className="auth-form" onSubmit={create}>
        <label>Member username<input value={username} onChange={e => setUsername(e.target.value)} minLength={3} maxLength={80} required autoComplete="off" /></label>
        <label>Initial member password<input type="password" value={password} onChange={e => setPassword(e.target.value)} minLength={15} maxLength={128} required autoComplete="new-password" /></label>
        <Button type="submit" disabled={busy}>Create member</Button>
      </form>
      {message && <p role="status">{message}</p>}{error && <p role="alert" className="auth-error">{error}</p>}
      <ul className="account-list">{accounts.map(member => <li key={member.id}><span>{member.username} · {member.role} · {member.enabled ? 'Enabled' : 'Disabled'}</span>
        {member.role === 'member' && <Button disabled={busy} onClick={() => void toggle(member)}>{member.enabled ? 'Disable' : 'Enable'} {member.username}</Button>}
      </li>)}</ul>
    </Card>
    <Card title="Audit records" sub="Account IDs, actions, times and outcomes are recorded. Passwords, source content and credential values are excluded.">
      <Button onClick={() => void reload().catch(e => setError(e.message))}>Refresh audit</Button>
      <ul className="account-list">{audit.map(row => <li key={row.id}><span>{new Date(row.created * 1000).toLocaleString()} · Account {row.actor ?? 'unsigned'} · {row.action} · HTTP {row.outcome}{row.target ? ` · Member ${row.target}` : ''}</span></li>)}</ul>
      {!audit.length && <p>No audit records yet.</p>}
      {before !== null && <Button onClick={() => void reload(before).catch(e => setError(e.message))}>Older records</Button>}
    </Card>
  </>
}
