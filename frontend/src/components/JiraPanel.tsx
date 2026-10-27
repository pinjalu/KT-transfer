import { useEffect, useState } from 'react'
import { Button, Card, Chip, Dot, Missing } from './ui'
import { Icon } from './Icon'
import { useApi } from '../lib/useApi'
import { ApiError, post } from '../lib/api'
import type { JiraReply } from '../lib/sources'
import type { Status } from '../lib/types'
import { ImportCoverage } from './ImportCoverage'
import type { Coverage } from './ImportCoverage'

export function JiraPanel({ status, onChanged, coverage }: { status: Status | null; onChanged: () => void; coverage?: Coverage }) {
  const jira = useApi<JiraReply>('/api/jira/projects')
  const [note, setNote] = useState('')
  const [picked, setPicked] = useState<string | null>(null)
  const reading = status?.jira_reading ?? false
  const busy = status?.busy ?? false
  const chosen = picked ?? jira.data?.chosen ?? ''
  useEffect(() => { jira.reload() }, [status?.knowledge_revision, jira.reload])

  const save = async (key: string) => {
    setPicked(key)
    setNote('')
    try {
      await post('/api/jira/project', { project: key })
      jira.reload()
    } catch (exc) {
      setNote(exc instanceof ApiError ? exc.message : 'Could not save that project.')
    }
  }

  const read = async () => {
    setNote('')
    try {
      await post('/api/jira/read')
      onChanged()
    } catch (exc) {
      setNote(exc instanceof ApiError ? exc.message : 'Could not start reading.')
    }
  }

  const connected = !!jira.data?.connected && !jira.data?.reason && !jira.error
  // Jira issues are stored against a scan, so there is nowhere to put them until one exists.
  // Offering the button anyway failed in the background with nothing shown on the page.
  const scanned = status?.ready ?? false

  return (
    <Card>
      <div className="conn-row">
        <div className="conn-id">
          <span className="conn-logo" aria-hidden="true"><Icon name="ticket" size={20} /></span>
          <div>
            <div className="conn-name">
              Jira
              <Chip tone={connected ? 'ok' : 'quiet'}>
                <Dot tone={connected ? 'ok' : 'quiet'} />
                {connected ? 'Access checked' : 'Setup needed'}
              </Chip>
            </div>
            <p className="conn-plain">
              Issues, descriptions, acceptance criteria and comments from one project.
            </p>
          </div>
        </div>

        <div className="conn-fields">
          <label className="field field-wide">
            <span className="field-label">Project</span>
            <select value={chosen} disabled={!connected || busy}
                    onChange={(e) => void save(e.target.value)}>
              <option value="">Choose a project…</option>
              {(jira.data?.projects ?? []).map((p) => (
                <option key={p.key} value={p.key}>{p.key} — {p.name}</option>
              ))}
              {/* A project saved earlier stays selectable even if the list could not be fetched. */}
              {chosen && !(jira.data?.projects ?? []).some((p) => p.key === chosen) && (
                <option value={chosen}>{chosen}</option>
              )}
            </select>
          </label>
        </div>

        <div className="conn-act">
          <Button kind="primary" onClick={read} disabled={!connected || !chosen || !scanned || busy || reading}>
            {reading ? 'Reading…' : 'Read issues'}
          </Button>
          <p className="conn-last">
            {!scanned
              ? 'Scan the repository first'
              : jira.data?.read_at
              ? `Last read: ${new Date(jira.data.read_at).toLocaleString()}`
              : jira.data?.blocks ? `${jira.data.blocks} issue excerpts stored` : 'Not read yet'}
          </p>
        </div>
      </div>

      {reading && (
        <div className="conn-progress" role="status">
          <span className="spinner" aria-hidden="true" />
          <span className="bar-phase">{status?.jira_progress?.phase || 'Reading issues…'}</span>
        </div>
      )}

      {note && <p className="conn-sub-note">{note}</p>}

      {!scanned && connected && (
        <div className="conn-warn">
          <Missing what="Issues cannot be read until the repository has been scanned."
                   checked="Jira issues are stored alongside the code from one scan, so a scan has to exist to attach them to." />
        </div>
      )}

      {jira.data?.reason && (
        <div className="conn-warn">
          <Missing what={jira.data.reason}
                   checked="Your account's saved Jira connection details. Add or update them in step 1 above." />
        </div>
      )}

      {jira.error && <div className="conn-warn"><Missing what={jira.error} checked="Your account's Jira connection" /></div>}
      <ImportCoverage coverage={coverage} />
      <p className="conn-caveat">Reading again replaces saved issues, including edits and deletions,
        and clears previous answers and the overview. Build the overview again after reading.</p>

    </Card>
  )
}
