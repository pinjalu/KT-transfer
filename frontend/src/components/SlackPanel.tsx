import { useEffect, useState } from 'react'
import { Button, Card, Chip, Dot, Missing } from './ui'
import { Icon } from './Icon'
import { useApi } from '../lib/useApi'
import { ApiError, get, post } from '../lib/api'
import type { SlackReply } from '../lib/sources'
import type { Status } from '../lib/types'

export function SlackPanel({ status, onChanged }: { status: Status | null; onChanged: () => void }) {
  const slack = useApi<SlackReply>('/api/slack/channels')
  const [note, setNote] = useState('')
  const [chosen, setChosen] = useState<Record<string, string> | null>(null)
  const [open, setOpen] = useState(false)
  const reading = status?.slack_reading ?? false
  const busy = status?.busy ?? false
  useEffect(() => { slack.reload() }, [status?.knowledge_revision, slack.reload])

  // Seed the selection from what is stored, once, so a click is not undone by the next poll.
  useEffect(() => {
    if (chosen !== null || !slack.data) return
    const seed: Record<string, string> = {}
    for (const c of slack.data.chosen) seed[c.id] = c.name
    setChosen(seed)
  }, [slack.data, chosen])

  const picked = chosen ?? {}
  const limit = slack.data?.limits?.channels ?? 20
  const connected = slack.data?.connected ?? false
  // Messages are stored against a scan, exactly as Jira issues are.
  const scanned = status?.ready ?? false

  const toggle = (id: string, name: string) => {
    setChosen((current) => {
      const next = { ...(current ?? {}) }
      if (next[id]) delete next[id]
      else if (Object.keys(next).length < limit) next[id] = name
      return next
    })
  }

  const saveChoice = async () => {
    setNote('')
    try {
      const channels = Object.entries(picked).map(([id, name]) => ({ id, name }))
      await post('/api/slack/channels', { workspace: slack.data?.workspace ?? '', channels })
      setNote(`${channels.length} channel(s) saved. Only these are ever read.`)
      slack.reload()
    } catch (exc) {
      setNote(exc instanceof ApiError ? exc.message : 'Could not save those channels.')
    }
  }

  const read = async () => {
    setNote('')
    try {
      await post('/api/slack/read')
      setNote('')
      onChanged()
    } catch (exc) {
      setNote(exc instanceof ApiError ? exc.message : 'Could not start reading.')
    }
  }

  const connect = async () => {
    try {
      const body = (await get('/api/connect/slack_user')) as { url: string }
      window.location.href = body.url
    } catch (exc) {
      setNote(exc instanceof ApiError ? exc.message : 'Could not start the Slack connection.')
    }
  }

  return (
    <Card>
      <div className="conn-row">
        <div className="conn-id">
          <span className="conn-logo" aria-hidden="true"><Icon name="chat" size={20} /></span>
          <div>
            <div className="conn-name">
              Slack
              <Chip tone={connected ? 'ok' : 'quiet'}>
                <Dot tone={connected ? 'ok' : 'quiet'} />
                {connected ? 'Connected' : 'Not connected'}
              </Chip>
            </div>
            <p className="conn-plain">
              Messages and thread replies from the channels you list, and no others.
            </p>
          </div>
        </div>

        <div className="conn-fields">
          <div className="field field-wide">
            <span className="field-label">
              Channels ({Object.keys(picked).length} of {limit} allowed)
            </span>
            <div className="chan-chosen">
              {Object.entries(picked).map(([id, name]) => (
                <button key={id} type="button" className="chan-tag" onClick={() => toggle(id, name)}>
                  #{name}<span aria-hidden="true">×</span>
                </button>
              ))}
              {!Object.keys(picked).length && (
                <span className="chan-none">None chosen. Nothing from Slack will be read.</span>
              )}
              {connected && (
                <button type="button" className="chan-add" onClick={() => setOpen((v) => !v)}>
                  {open ? 'Done' : 'Choose channels'}
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="conn-act">
          {connected ? (
            <>
              <Button kind="secondary" onClick={saveChoice} disabled={busy}>Save channels</Button>
              <Button kind="primary" onClick={read}
                      disabled={busy || reading || !scanned || !Object.keys(picked).length}>
                {reading ? 'Reading…' : 'Read messages'}
              </Button>
            </>
          ) : (
            <Button kind="primary" onClick={connect}>Connect Slack</Button>
          )}
          <p className="conn-last">
            {!scanned
              ? 'Scan the repository first'
              : slack.data?.read_at
              ? `Last read: ${new Date(slack.data.read_at).toLocaleString()}`
              : slack.data?.blocks ? `${slack.data.blocks} messages indexed` : 'Not read yet'}
          </p>
        </div>
      </div>

      {open && connected && (
        <div className="chan-list">
          {(slack.data?.channels ?? []).map((c) => (
            <label key={c.id} className="chan-opt">
              <input type="checkbox" checked={!!picked[c.id]} onChange={() => toggle(c.id, c.name)} />
              <span>#{c.name}</span>
            </label>
          ))}
          {!(slack.data?.channels ?? []).length && (
            <p className="chan-none">No channels came back for this account.</p>
          )}
        </div>
      )}

      {reading && status?.slack_progress && (
        <div className="conn-progress">
          <span className="spinner" aria-hidden="true" />
          <span className="bar-phase">{status.slack_progress.phase}</span>
        </div>
      )}

      {note && <p className="conn-sub-note">{note}</p>}

      {!scanned && connected && (
        <div className="conn-warn">
          <Missing what="Messages cannot be read until the repository has been scanned."
                   checked="Slack messages are stored alongside the code from one scan, so a scan has to exist to attach them to." />
        </div>
      )}

      {slack.data?.reason && (
        <div className="conn-warn">
          <Missing what={slack.data.reason} checked="SLACK_USER_TOKEN in your local .env file" />
        </div>
      )}

      <p className="conn-caveat">
        Who wrote a message is not resolved to a name, because that needs a permission this
        deliberately does not ask for. Reading again replaces what was read before, so a deleted
        message or a channel dropped from this list cannot linger in an answer.
        Previous answers and the overview are cleared. Build the overview again after reading.
      </p>
    </Card>
  )
}
