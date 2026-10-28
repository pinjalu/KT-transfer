import { useEffect, useState } from 'react'
import { Button, Card, Chip, Failed, Loading, PageHead, Tabs } from '../components/ui'
import { useAccount } from '../components/AuthGate'
import { Icon } from '../components/Icon'
import { JiraPanel } from '../components/JiraPanel'
import { SlackPanel } from '../components/SlackPanel'
import { ImportHistory } from '../components/ImportHistory'
import { ImportCoverage } from '../components/ImportCoverage'
import { SourceFreshness } from '../components/SourceFreshness'
import { ZipProject } from '../components/ZipProject'
import { SearchPreparation } from '../components/SearchPreparation'
import { SourceCredentials } from '../components/SourceCredentials'
import type { CredentialSource } from '../components/SourceCredentials'
import type { CoverageReply } from '../components/ImportCoverage'
import { useApi } from '../lib/useApi'
import { projectName } from '../lib/project'
import { ApiError, post } from '../lib/api'
import { useStatus } from '../lib/useStatus'
import './connections.css'

type Connection = 'github' | 'local' | 'zip' | 'jira' | 'slack'
const names = { github:'GitHub', local:'Local folder', zip:'ZIP file', jira:'Jira', slack:'Slack' }

export function Connections() {
  const account = useAccount()
  const canReadLocal = account?.user.role === 'owner'
  const [tab, setTab] = useState('Connections')
  const [connection, setConnection] = useState<Connection>('github')
  const status = useStatus(2000)
  const coverage = useApi<CoverageReply>('/api/import-coverage', 2000, status.data?.knowledge_revision)
  const settings = status.data?.settings
  const [repo, setRepo] = useState('')
  const [branch, setBranch] = useState('main')
  const [localPath, setLocalPath] = useState('')
  const [addToProject, setAddToProject] = useState(false)
  const [seeded, setSeeded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState('')
  const [credentialRevision,setCredentialRevision] = useState({github:0,jira:0,slack:0})
  const credentialsSaved = (source:CredentialSource) => {
    setCredentialRevision(previous=>({...previous,[source]:previous[source]+1}))
    status.reload(); coverage.reload()
  }
  useEffect(() => {
    if (!seeded && !settings && status.data?.stored_project?.source_kind === 'zip') {
      setConnection('zip'); setSeeded(true); return
    }
    if (!settings || seeded) return
    setRepo(/^(local|zip):/.test(settings.repo) ? '' : settings.repo)
    setBranch(/^(local|zip):/.test(settings.repo) ? 'main' : settings.branch)
    setLocalPath(settings.local?.path ?? settings.local_path ?? '')
    if (canReadLocal && (settings.repo.startsWith('local:') || settings.source_kind === 'local'
      || settings.selected_source === 'local')) setConnection('local')
    if (settings.source_kind === 'zip') setConnection('zip')
    setSeeded(true)
  }, [settings, seeded, canReadLocal, status.data?.stored_project])
  const stored = status.data?.stored_project
  const awaiting = status.data?.awaiting_project ?? false
  const busy = status.data?.busy ?? false
  const scan = status.data?.scan
  const primaryLocal = settings?.repo.startsWith('local:') ?? false
  const primaryZip = settings?.source_kind === 'zip'
  const canAddFolder = !awaiting && !!settings && !primaryLocal && !primaryZip && !!status.data?.ready
  const primaryForm = connection === (primaryZip ? 'zip' : primaryLocal ? 'local' : 'github')
  const refresh = async () => {
    setNote('')
    try {
      await post(connection === 'local' && !primaryLocal ? '/api/local/read' : '/api/scan')
      setNote(connection === 'local' ? 'Local folder read requested.' : 'Repository scan requested.')
    } catch (exc) { setNote(exc instanceof ApiError ? exc.message : 'The read could not start.') }
    status.reload()
  }
  const save = async () => {
    setSaving(true); setNote('')
    try {
      const saved = await post('/api/config', {
        source_kind:connection, repo:connection === 'github' ? repo : '',
        branch:connection === 'github' ? branch : 'working-tree',
        local_path:connection === 'local' ? localPath : '',
        add_to_project:connection === 'local' && canAddFolder && addToProject,
        platforms:[connection],
      }) as { reconnected?: boolean; additional_local?: boolean }
      if (saved.additional_local) {
        await post('/api/local/read')
        setNote('Reading the local folder. Your GitHub, Jira and Slack connections are kept.')
      } else if (saved.reconnected) {
        setNote('Reconnected to the saved project. Nothing was read again.')
      } else {
        await post('/api/scan')
        setNote('Project saved. Reading the files now.')
      }
    } catch (exc) { setNote(exc instanceof ApiError ? exc.message : 'The connection could not be saved.') }
    finally { setSaving(false); status.reload(); coverage.reload() }
  }
  if (status.loading) return <Loading what="connections" />
  if (status.error) return <Failed message={status.error} onRetry={status.reload} />
  const choices: Connection[] = status.data?.demo ? ['github','jira','slack'] : canReadLocal ? ['github','local','zip','jira','slack'] : ['github','zip','jira','slack']
  return <>
    <PageHead title="Connections" lead="Connect the code and conversations that explain your project." />
    <div className="conn-badge-row"><Chip tone="info"><Icon name="lock" size={14} /> Read-only access</Chip>
      {status.data?.demo && <Chip tone="violet">Example mode, fixture data</Chip>}</div>
    <Tabs items={['Connections','Import history']} active={tab} onPick={setTab} />
    {tab === 'Connections' ? <div className="stack conn-stack">
      {connection !== 'local' && connection !== 'zip' && <SourceCredentials source={connection} onSourceChange={setConnection}
        onSaved={credentialsSaved} disabled={busy||!!status.data?.demo} title="1. Add your connection tokens" />}
      <Card>
        <div className="conn-picker">
          <div><h2>{connection==='local'||connection==='zip'?'Your project sources':'2. Choose what to read'}</h2><p>Read a GitHub repository, local folder or ZIP project, then add Jira issues and Slack messages.</p></div>
          <label className="field"><span className="field-label">Connection</span>
            <select aria-label="Connection" value={connection} onChange={e => { setConnection(e.target.value as Connection); setAddToProject(false); setNote('') }}>
              {choices.map(key => <option key={key} value={key}>{names[key]}</option>)}
            </select></label>
        </div>
        <div className="conn-saved" aria-label="Saved source status">{choices.map(key => {
          const read = coverage.data?.sources[key]?.available
          const selected = key === 'github' ? settings && !primaryLocal && !primaryZip
            : key === 'zip' ? primaryZip
            : key === 'local' ? primaryLocal || settings?.local?.path
            : key === 'jira' ? settings?.jira?.project : settings?.slack?.channels?.length
          return <span key={key}><Chip tone={read ? 'ok' : 'quiet'}>{names[key]} · {read ? 'Read' : selected ? 'Not read yet' : 'Not connected'}</Chip></span>
        })}</div>
        <p className="conn-picker-help">Switching this dropdown only changes the form below. It does not disconnect other sources.</p>
      </Card>
      {note && <p className="conn-note" role="status">{note}</p>}
      {status.data && <SearchPreparation status={status.data} onChanged={status.reload} />}
      {coverage.error && <Failed message={coverage.error} onRetry={coverage.reload} />}
      {!awaiting && <SourceFreshness coverage={coverage.data ?? undefined} warning={status.data?.warning} />}
      {connection === 'zip' && <ZipProject status={status.data ?? null} coverage={coverage.data?.sources.zip}
        onChanged={() => { status.reload(); coverage.reload() }} />}
      {(connection === 'github' || connection === 'local') && <Card>
        <div className="conn-row">
          <div className="conn-id"><span className="conn-logo"><Icon name="doc" size={20} /></span><div>
            <div className="conn-name">{names[connection]} <Chip tone="info">{connection === 'local' ? 'Read-only · Owner' : 'Read-only'}</Chip></div>
            <p className="conn-plain">{connection === 'local' ? 'Add files from this computer.' : 'Connect a repository and branch.'}</p>
          </div></div>
          {awaiting && stored && <div className="conn-resume">
            <span className="conn-resume-text">Saved project: <span className="mono">{stored.project_name || projectName(null, stored.repo)}</span>. Its imported content is still stored.</span>
            <Button kind="secondary" onClick={() => {
              if (stored.source_kind === 'zip') { setConnection('zip'); return }
              const local = stored.source_kind === 'local'
              setConnection(local ? 'local' : 'github'); setRepo(local ? '' : stored.repo)
              setBranch(local ? 'main' : stored.branch); setLocalPath(stored.local_path ?? '')
            }}>Use it again</Button>
          </div>}
          <div className={'conn-fields ' + (connection === 'local' ? 'conn-local-fields' : '')}>
            {connection === 'local' ? <label className="field">
              <span className="field-label">Local folder path or file link</span>
              <input value={localPath} onChange={e => setLocalPath(e.target.value)} maxLength={1000} placeholder="D:\Projects\my-app or file:///D:/Projects/my-app" />
              <span className="conn-plain">Includes current uncommitted files. No GitHub token needed.</span>
            </label> : <>
              <label className="field"><span className="field-label">Repository</span><input value={repo} onChange={e => setRepo(e.target.value)} placeholder="owner/repository or URL" maxLength={400} disabled={status.data?.demo} /></label>
              <label className="field"><span className="field-label">Branch</span><input value={branch} onChange={e => setBranch(e.target.value)} placeholder="main" maxLength={200} disabled={status.data?.demo} /></label>
            </>}
          {connection === 'local' && canAddFolder && <label className="conn-add-folder">
            <input type="checkbox" checked={addToProject} disabled={busy || saving}
              onChange={e => setAddToProject(e.target.checked)} />
            <span>Add this folder to the current project ({projectName(settings)})</span>
          </label>}
          <p className="conn-plain conn-selection-help">{connection === 'local' && canAddFolder && addToProject
            ? 'The folder will be read together with the current project’s code and conversations.'
            : 'Choosing a different repository or folder starts a new project. Its overview, files and conversations replace the previous project in this workspace.'}</p>
          </div>
          <div className="conn-act">
            <Button kind="primary" onClick={save} disabled={saving || busy || status.data?.demo || (connection === 'local' ? !localPath || !canReadLocal : !repo || !branch)}>{saving ? 'Saving…' : 'Save and read files'}</Button>
            <Button kind="secondary" icon="refresh" onClick={() => void refresh()} disabled={busy || awaiting || !settings || (connection === 'local' && !primaryLocal && !settings.local?.path)}>{connection === 'local' ? 'Read local folder again' : 'Refresh repository'}</Button>
          </div>
        </div>
        <p className="conn-local-note">Refresh reuses unchanged files. After an interrupted read, choose Retry job to continue with saved files. Access and file changes are checked each time.</p>
        {connection === 'local' ? <p className="conn-local-note">Choose a folder on the computer running KT Assistant. A Git clone is optional.
          A folder starts its own project unless you choose to add it to the current project. Read this folder again after editing files.
          Built-in rules exclude secret filenames, dependencies, generated files and linked folders; custom .gitignore rules are not applied.</p>
          : <><p className="conn-local-note">Refreshing the repository replaces the project scan. Read the local folder, Jira issues and Slack messages again afterward, then rebuild the overview.</p>
            {!status.data?.token_configured && !status.data?.demo && <p className="conn-local-note">No GitHub token saved for your account. Add it in step 1 above for a private repository.</p>}</>}
        {primaryForm && scan && <div className="conn-counts"><span><b>{scan.read}</b> read</span>{scan.reused !== undefined && <span><b>{scan.reused}</b> reused</span>}{scan.fetched !== undefined && <span><b>{scan.fetched}</b> fetched</span>}<span><b>{scan.skipped}</b> skipped</span><span><b>{scan.failed}</b> failed</span><Chip tone={scan.status === 'complete' ? 'ok' : 'quiet'}>{scan.status}</Chip></div>}
        {primaryForm && scan?.error && <Failed message={scan.error} />}
        <ImportCoverage coverage={coverage.data?.sources[connection]} />
      </Card>}
      <div hidden={connection !== 'jira'}><JiraPanel key={credentialRevision.jira} status={status.data ?? null} onChanged={status.reload} coverage={coverage.data?.sources.jira} /></div>
      <div hidden={connection !== 'slack'}><SlackPanel key={credentialRevision.slack} status={status.data ?? null} onChanged={status.reload} coverage={coverage.data?.sources.slack} /></div>
    </div> : <div className="conn-stack"><ImportHistory /></div>}
  </>
}
