import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { get, post } from '../lib/api'
import { Button, Card } from './ui'

const sources = {
  GitHub: [['GITHUB_TOKEN', 'GitHub token']],
  Jira: [['JIRA_SITE', 'Jira site URL'], ['JIRA_EMAIL', 'Atlassian email'], ['JIRA_API_TOKEN', 'Jira API token']],
  Slack: [['SLACK_USER_TOKEN', 'Slack user token']],
  'Slack browser approval': [['SLACK_CLIENT_ID', 'Slack client ID'], ['SLACK_CLIENT_SECRET', 'Slack client secret']],
} as const

export function SourceCredentials() {
  const [source, setSource] = useState<keyof typeof sources>('GitHub')
  const [values, setValues] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState<Record<string, boolean>>({})
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { void get('/api/platforms').then(result => setSaved((result as { credentials: Record<string, boolean> }).credentials)).catch(e => setError(e.message)) }, [])
  async function save(event: FormEvent) {
    event.preventDefault(); setError(''); setMessage(''); setBusy(true)
    try {
      const result = await post('/api/credentials', { values }) as { status: Record<string, boolean> }
      setSaved(result.status); setValues({}); setMessage('Your credentials were saved. Re-read any affected sources in Connections.')
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return <Card title="Your source credentials" sub="Only your account uses these connections. Credentials are encrypted for this Windows installation and are never shown again.">
    <form className="auth-form" onSubmit={save}>
      <label>Source<select value={source} onChange={e => { setSource(e.target.value as keyof typeof sources); setValues({}); setMessage(''); setError('') }}>
        {Object.keys(sources).map(name => <option key={name}>{name}</option>)}
      </select></label>
      {source === 'GitHub' && <p className="auth-footnote">Use a fine-grained token for your selected repository with Contents read-only. <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noreferrer">Create a GitHub token</a></p>}
      {sources[source].map(([name, label]) => <label key={name}>{label} {saved[name] ? '(saved)' : '(not saved)'}
        <input aria-label={label} type="password" autoComplete="off" value={values[name] ?? ''} maxLength={500}
          onChange={e => setValues(current => ({ ...current, [name]: e.target.value }))} />
      </label>)}
      <p className="auth-footnote">Unedited fields stay unchanged. To remove a saved value, edit its field and then clear it before saving.</p>
      {message && <p role="status">{message}</p>}{error && <p role="alert" className="auth-error">{error}</p>}
      <Button type="submit" disabled={busy || !Object.keys(values).length}>{busy ? 'Saving…' : 'Save source credentials'}</Button>
    </form>
  </Card>
}

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
