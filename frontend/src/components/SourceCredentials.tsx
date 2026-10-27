import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { get, post } from '../lib/api'
import { useAccount } from './AuthGate'
import { useApi } from '../lib/useApi'
import { usePageActive } from '../lib/pageState'
import { Button, Card, Chip } from './ui'
import './source-credentials.css'

export type CredentialSource = 'github' | 'jira' | 'slack'
const labels = {github:'GitHub', jira:'Jira', slack:'Slack'}
const fields = {
  github: [{key:'GITHUB_TOKEN',label:'GitHub token',type:'password',placeholder:'Paste your GitHub token'}],
  jira: [
    {key:'JIRA_SITE',label:'Jira site URL',type:'url',placeholder:'https://yourcompany.atlassian.net'},
    {key:'JIRA_EMAIL',label:'Atlassian email',type:'email',placeholder:'you@company.com'},
    {key:'JIRA_API_TOKEN',label:'Jira API token',type:'password',placeholder:'Paste your Jira API token'},
  ],
  slack: [{key:'SLACK_USER_TOKEN',label:'Slack user token',type:'password',placeholder:'Paste your Slack user token'}],
  slack_browser: [
    {key:'SLACK_CLIENT_ID',label:'Slack client ID',type:'text',placeholder:'Your Slack app client ID'},
    {key:'SLACK_CLIENT_SECRET',label:'Slack client secret',type:'password',placeholder:'Your Slack app client secret'},
  ],
}

export function SourceCredentials({ source, onSourceChange, onSaved, disabled = false, title = 'Your connection tokens' }: {
  source?: CredentialSource; onSourceChange?: (source:CredentialSource)=>void;
  onSaved?: (source:CredentialSource)=>void; disabled?: boolean; title?: string;
}) {
  const account = useAccount()
  const active = usePageActive()
  const stored = useApi<{credentials:Record<string,boolean>}>('/api/platforms')
  const [selected,setSelected] = useState<CredentialSource>('github')
  const current = source ?? selected
  const [browserApproval,setBrowserApproval] = useState(false)
  const [values,setValues] = useState<Record<string,string>>({})
  const [saved,setSaved] = useState<Record<string,boolean>>({})
  const [message,setMessage] = useState('')
  const [error,setError] = useState('')
  const [busy,setBusy] = useState(false)
  const shown = current === 'slack' && browserApproval ? fields.slack_browser : fields[current]
  useEffect(()=>{ if(stored.data) setSaved(stored.data.credentials) },[stored.data])
  useEffect(()=>{ setValues({});setMessage('');setError('');setBrowserApproval(false) },[current])
  // Connections is retained across navigation. Typed secrets must not be.
  useEffect(()=>{ if(!active) setValues({}) },[active])
  const pick = (next:CredentialSource) => { setSelected(next);onSourceChange?.(next) }
  async function save(event:FormEvent) {
    event.preventDefault()
    if(busy || disabled) return
    const changed = Object.fromEntries(shown.filter(f=>Object.hasOwn(values,f.key)).map(f=>[f.key,values[f.key].trim()]))
    if(!Object.keys(changed).length) return
    setBusy(true);setMessage('');setError('')
    let persisted = false
    try {
      const response = await post('/api/credentials',{values:changed}) as {status:Record<string,boolean>}
      setSaved(response.status);setValues({});persisted=true
      onSaved?.(current)
      if(!shown.every(f=>response.status[f.key])) {
        setMessage('Changes saved. Add the missing fields above to finish this connection.')
      } else if(current === 'github') {
        setMessage('GitHub token saved for your account. Choose a repository below and read its files to verify access.')
      } else if(browserApproval) {
        setMessage('Slack app credentials saved. Use Connect Slack in browser below to approve your account.')
      } else {
        const check = await get(current==='jira'?'/api/jira/projects':'/api/slack/channels') as {connected:boolean;reason?:string}
        if(!check.connected || check.reason) setError(`Credentials saved, but access could not be confirmed. ${check.reason||'Check the token and permissions.'}`)
        else setMessage(`${labels[current]} access checked successfully. Choose ${current==='jira'?'a project':'channels'} below, then read ${current==='jira'?'issues':'messages'}.`)
      }
    } catch(exc) {
      setError(`${persisted?'Credentials saved, but the access check failed. ':''}${exc instanceof Error?exc.message:'Could not save your credentials.'}`)
    } finally {setBusy(false)}
  }
  return <Card title={title} sub={`Saved only for ${account?.user.username||'your signed-in account'}. Each team member adds their own tokens; the owner's tokens are not shared.`}>
    <div className="source-token-choices" role="group" aria-label="Token provider">
      {(Object.keys(labels) as CredentialSource[]).map(key=><Button key={key} kind={current===key?'primary':'secondary'} aria-pressed={current===key} disabled={busy}
        onClick={()=>pick(key)}>{labels[key]} <Chip>{fields[key].every(f=>saved[f.key])?'Token saved':'Setup needed'}</Chip></Button>)}
    </div>
    <p className="source-token-help">First save your access details here. Then choose the repository, Jira project or Slack channels to read below. Saving a token alone does not import content.</p>
    {current==='github'&&<p className="source-token-help">Use your GitHub account's fine-grained token with Contents read access to the selected repository. Public repositories can also be read without a token. <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noreferrer">Create a GitHub token</a></p>}
    {current==='jira'&&<p className="source-token-help">Use the email of the Atlassian account that created the token. You must have access to the Jira project. <a href="https://id.atlassian.com/manage-profile/security/api-tokens" target="_blank" rel="noreferrer">Manage Jira API tokens</a></p>}
    {current==='slack'&&<><p className="source-token-help">Use a Slack user token for your own workspace account. This reader uses channels:read, channels:history, groups:read and groups:history. Select only the channels you want to import. <a href="https://api.slack.com/apps" target="_blank" rel="noreferrer">Open your Slack apps</a></p>
      <label className="source-token-method">Slack connection method<select value={browserApproval?'browser':'token'} disabled={busy} onChange={e=>{setBrowserApproval(e.target.value==='browser');setValues({});setMessage('');setError('')}}>
        <option value="token">Paste a user token</option><option value="browser">Browser approval (advanced)</option></select></label>
      {browserApproval&&<p className="source-token-help">Browser approval currently requires the localhost address and your Slack app's configured callback. For an office-network URL, use your user token.</p>}</>}
    {stored.loading?<p role="status">Checking your saved credential status…</p>:stored.error?<p role="alert">{stored.error} <Button onClick={stored.reload}>Retry credential status</Button></p>:null}
    <form className="source-token-form" aria-label={`${labels[current]} connection tokens`} onSubmit={save} autoComplete="off">
      <div className="source-token-fields">{shown.map(field=><label className="field" key={field.key}>
        <span className="field-label">{field.label} <span>{saved[field.key]?'(saved)':'(not saved)'}</span></span>
        <input aria-label={field.label} type={field.type} value={values[field.key]??''} placeholder={field.placeholder} autoComplete={field.type==='password'?'new-password':'off'}
          maxLength={500} disabled={disabled||busy||stored.loading||!!stored.error} onChange={e=>setValues(previous=>({...previous,[field.key]:e.target.value}))}/>
      </label>)}</div>
      <p className="source-token-help">Saved values stay hidden. Unedited fields keep their existing values. To remove a value, edit its field and clear it before saving.</p>
      <Button kind="primary" type="submit" disabled={disabled||busy||stored.loading||!!stored.error||!shown.some(f=>Object.hasOwn(values,f.key))}>
        {busy?'Saving and checking…':current==='github'?'Save GitHub token':browserApproval?'Save Slack app credentials':`Save and check ${labels[current]}`}</Button>
      {disabled&&<p className="source-token-help">Credential changes are unavailable during a running job or in example mode.</p>}
      {message&&<p role="status" className="source-token-result">{message}</p>}{error&&<p role="alert" className="auth-error">{error}</p>}
    </form>
  </Card>
}
