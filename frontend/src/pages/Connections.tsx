import { useEffect, useState } from 'react'
import { Button, Card, Chip, Dot, Failed, Loading, Missing, PageHead, Tabs } from '../components/ui'
import { Icon } from '../components/Icon'
import { JiraPanel } from '../components/JiraPanel'
import { SlackPanel } from '../components/SlackPanel'
import { ImportHistory } from '../components/ImportHistory'
import { useApi } from '../lib/useApi'
import { ApiError, post } from '../lib/api'
import type { Platforms, Status } from '../lib/types'
import './connections.css'

function pct(scan: { processed?: number; total?: number } | null) {
  if (!scan?.total) return 0
  return Math.min(100, Math.round(((scan.processed ?? 0) / scan.total) * 100))
}

export function Connections() {
  const [tab, setTab] = useState('Connections')
  const status = useApi<Status>('/api/status', 2000)
  const platforms = useApi<Platforms>('/api/platforms')

  const settings = status.data?.settings
  const [repo, setRepo] = useState('')
  const [branch, setBranch] = useState('')
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState('')

  // Seed the fields from the selection confirmed in this run, once, so typing is not
  // overwritten by the poll. Before a project is picked `settings` is null and the fields stay
  // empty: the project from a previous run is offered just below, as something to click rather
  // than something already filled in.
  useEffect(() => {
    if (!settings) return
    setRepo((v) => v || settings.repo)
    setBranch((v) => v || settings.branch)
  }, [settings])

  const stored = status.data?.stored_project ?? null
  const awaiting = status.data?.awaiting_project ?? false

  const scan = status.data?.scan ?? null
  const busy = status.data?.busy ?? false
  const running = scan?.status === 'running'

  const act = async (what: () => Promise<unknown>, ok: string) => {
    setNote('')
    try {
      await what()
      setNote(ok)
      status.reload()
      platforms.reload()
    } catch (exc) {
      setNote(exc instanceof ApiError ? exc.message : 'Something went wrong.')
    }
  }

  /**
   * Save the selection and then actually read the files, which is what the button says.
   *
   * It only saved. The page then sat on "Not read yet" however many times it was pressed, and
   * because Jira and Slack store their content against a scan, their read buttons stayed locked
   * with no way to unlock them from this screen.
   */
  const save = async () => {
    setSaving(true)
    setNote('')
    try {
      const saved = (await post('/api/config',
        { repo, branch, platforms: settings?.platforms ?? ['github'] })) as { reconnected?: boolean }
      // Reading again is the point when the repository is new, and pure waste when it is the
      // one already stored: the snapshot survived the restart, so reconnecting to it costs
      // nothing and re-reading it would cost minutes before a single question could be asked.
      if (saved.reconnected) {
        setNote('Reconnected to what was already read for this repository. Nothing was read again.')
      } else {
        await post('/api/scan')
        setNote('Repository saved. Reading the files now.')
      }
    } catch (exc) {
      setNote(exc instanceof ApiError ? exc.message : 'Something went wrong.')
    } finally {
      setSaving(false)
      status.reload()
      platforms.reload()
    }
  }

  if (status.loading) return <Loading what="connections" />
  if (status.error) return <Failed message={status.error} onRetry={status.reload} />

  return (
    <>
      <PageHead
        title="Connections"
        lead="Choose the project information your assistant can read."
        actions={
          <Button kind="primary" icon="refresh" disabled={busy}
                  onClick={() => act(() => post('/api/scan'), 'Scan started.')}>
            {running ? 'Reading…' : 'Refresh selected sources'}
          </Button>
        } />

      <div className="conn-badge-row">
        <Chip tone="info"><Icon name="lock" size={14} /> Read-only access</Chip>
        {status.data?.demo && <Chip tone="violet">Example mode, fixture data</Chip>}
        {!status.data?.token_configured && !status.data?.demo && (
          <Chip tone="warn">No GitHub token in .env, unauthenticated rate limits apply</Chip>
        )}
      </div>

      <Tabs items={['Connections', 'Import history']} active={tab} onPick={setTab} />

      {note && <p className="conn-note">{note}</p>}

      {status.data?.job_error && (
        <div className="conn-job-error">
          <Failed message={`The last ${status.data.job_name || 'background'} read did not finish: `
                           + status.data.job_error} />
        </div>
      )}

      {tab === 'Connections' && (
        <div className="stack conn-stack">
          <Card>
            <div className="conn-row">
              <div className="conn-id">
                <span className="conn-logo" aria-hidden="true"><Icon name="doc" size={20} /></span>
                <div>
                  <div className="conn-name">
                    GitHub
                    <Chip tone={status.data?.token_configured || status.data?.demo ? 'ok' : 'quiet'}>
                      <Dot tone={status.data?.token_configured || status.data?.demo ? 'ok' : 'quiet'} />
                      {status.data?.token_configured || status.data?.demo ? 'Connected' : 'No credential'}
                    </Chip>
                  </div>
                  <p className="conn-plain">Source code repository.</p>
                </div>
              </div>

              {/* The previous run's project, offered rather than assumed. Everything read for
                  it is still stored, so this fills the fields and nothing is read again. */}
              {awaiting && stored && (
                <div className="conn-resume">
                  <span className="conn-resume-text">
                    Last time this read <span className="mono">{stored.repo}</span> on{' '}
                    <span className="mono">{stored.branch}</span>. What it read is still stored.
                  </span>
                  <Button kind="secondary"
                          onClick={() => { setRepo(stored.repo); setBranch(stored.branch) }}>
                    Use it again
                  </Button>
                </div>
              )}

              <div className="conn-fields">
                <label className="field">
                  <span className="field-label">Repository</span>
                  <input value={repo} onChange={(e) => setRepo(e.target.value)}
                         placeholder="owner/repository or URL" maxLength={400}
                         disabled={status.data?.demo} />
                </label>
                <label className="field">
                  <span className="field-label">Branch</span>
                  <input value={branch} onChange={(e) => setBranch(e.target.value)}
                         placeholder="main" maxLength={200} disabled={status.data?.demo} />
                </label>
              </div>

              <div className="conn-act">
                <Button kind="secondary" onClick={save}
                        disabled={saving || busy || !repo || !branch || status.data?.demo}>
                  Save and read files
                </Button>
                <p className="conn-last">
                  {scan?.finished ? `Last read: ${new Date(scan.finished).toLocaleString()}` : 'Not read yet'}
                </p>
              </div>
            </div>

            {running && (
              <div className="conn-progress">
                <div className="bar"><div className="bar-fill" style={{ width: `${pct(scan)}%` }} /></div>
                <span className="bar-pct">{pct(scan)}%</span>
                <span className="bar-phase">{scan?.phase}</span>
                <Button kind="secondary" onClick={() => act(() => post('/api/scan/cancel'), 'Cancelling.')}>
                  Cancel
                </Button>
              </div>
            )}

            {scan && !running && (
              <div className="conn-counts">
                <span><b>{scan.read}</b> read</span>
                <span><b>{scan.skipped}</b> skipped</span>
                <span><b>{scan.failed}</b> failed</span>
                {scan.commit && <span className="mono">commit {scan.commit.slice(0, 7)}</span>}
                <Chip tone={scan.status === 'complete' ? 'ok' : scan.status === 'failed' ? 'bad' : 'warn'}>
                  {scan.status}
                </Chip>
              </div>
            )}

            {scan?.tree_incomplete && (
              <div className="conn-warn">
                <Missing
                  what="Not every file in the repository was read."
                  checked="The file tree came back truncated, or the size limits stopped the read." />
              </div>
            )}
            {scan?.error && <div className="conn-warn"><Failed message={scan.error} /></div>}
          </Card>

          <JiraPanel status={status.data ?? null} onChanged={status.reload} />
          <SlackPanel status={status.data ?? null} onChanged={status.reload} />

          <Card title="More sources"
                sub="Connect additional project information. All read-only.">
            <div className="more-grid">
              {[
                ['Documentation', 'Product docs, internal wikis, APIs.', 'Step 13'],
                ['Database schema', 'Table and column structure, never row contents.', 'Step 13'],
                ['Logs and monitoring', 'Application logs and error tracking.', 'Step 13'],
                ['Pull requests', 'Reviews and change history.', 'Step 13'],
              ].map(([title, plain, step]) => (
                <div className="more-card" key={title}>
                  <span className="more-icon" aria-hidden="true"><Icon name="database" size={18} /></span>
                  <div>
                    <p className="more-title">{title}</p>
                    <p className="more-plain">{plain}</p>
                  </div>
                  <Chip tone="quiet">{step}</Chip>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {tab === 'Import history' && (
        <div className="conn-stack"><ImportHistory /></div>
      )}

    </>
  )
}
