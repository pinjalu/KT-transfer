import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { GenerationDetails } from '../components/GenerationDetails'
import { Button, Card, Chip, Empty, Failed, Loading, NoProject, PageHead } from '../components/ui'
import { ApiError, post } from '../lib/api'
import { useApi } from '../lib/useApi'
import { useStatus } from '../lib/useStatus'
import { useRememberedParam } from '../lib/pageState'
import type { Status } from '../lib/types'
import './jira-tasks.css'
import './team-decisions.css'

const LABELS = { decision: 'Recorded agreement', proposal: 'Suggestion / proposal', historical: 'Historical context', conflict: 'Possible conflicting agreements', mixed: 'Mixed positions', unclear: 'Unclear decision status' }
type Kind = keyof typeof LABELS
type Source = { source_id: string; path: string; start: number; text: string; url: string; partial: boolean; message_ts?: string; thread_ts?: string; edited_ts?: string; author?: string }
type Point = { text: string; kind: Kind; reason?: string; source_ids: string[]; quotes: { source_id: string; text: string }[]; source_wording: boolean }
type Summary = { items: Point[]; model: string; generated_at: string; parts: number; passages_read: number; excerpts_read: number; demo: boolean; labels_rechecked?: boolean; generations?: import('../lib/ai').Generation[] }
type Position = { id: string; text: string; kind: Kind; reason: string; source_id: string }
type Review = { positions: Position[]; comparisons: { subject: string; kind: 'conflict' | 'alternatives' | 'recorded_update'; reason: string; position_ids: string[] }[]; passages_checked: number; partial_passages: number }
type Channel = { id: string; name: string; excerpts?: number }
type Detail = { channel: Channel; sources: Source[]; summary: Summary | null; review?: Review; read_at: string | null; coverage: { state?: string }; import_coverage: string }

function Evidence({ source }: { source: Source }) {
  return <div className="decision-evidence">
    <p className="jira-muted">{source.source_id} · #{source.path.slice(6)} · Imported excerpt {source.start}{source.partial && ' · Part of a long message'}</p>
    {source.author && <p className="jira-muted">Recorded author: {source.author}{source.message_ts && ` · Posted ${new Date(Number(source.message_ts) * 1000).toLocaleString()}`}</p>}
    {source.thread_ts && <p className="jira-muted">{source.thread_ts === source.message_ts ? 'Message posted' : 'Reply to message posted'} {new Date(Number(source.thread_ts) * 1000).toLocaleString()}{source.edited_ts && ` · Edited ${new Date(Number(source.edited_ts) * 1000).toLocaleString()}`}</p>}
    <pre className="jira-related-text">{source.text}</pre>
    {source.url ? <a href={source.url} target="_blank" rel="noreferrer">{source.message_ts ? 'Open message in Slack' : 'Open excerpt in Slack'} ↗</a>
      : <p className="jira-muted">No Slack permalink was stored for this excerpt.</p>}
  </div>
}

function PositionEvidence({ position, sources }: { position: Position; sources: Source[] }) {
  const source = sources.find(s => s.source_id === position.source_id)
  return <>
    <Chip tone={position.kind === 'decision' ? 'ok' : 'quiet'}>{LABELS[position.kind]}</Chip>
    <blockquote className="decision-text">{position.text}</blockquote>
    <p className="jira-muted">{position.reason}</p>
    {source && <details className="jira-quote"><summary>Read full message ({source.source_id})</summary><Evidence source={source} /></details>}
  </>
}

function ComparedPositions({ ids, positions, sources }: { ids: string[]; positions: Position[]; sources: Source[] }) {
  const grouped = new Map<string, Position>()
  for (const id of ids) {
    const position = positions.find(p => p.id === id)
    if (!position) continue
    const key = `${position.source_id}:${position.kind}`, previous = grouped.get(key)
    grouped.set(key, previous ? { ...previous, text: `${previous.text}\n${position.text}` } : position)
  }
  return <ol className="decision-points">{Array.from(grouped.values()).map(position => <li key={position.id}><PositionEvidence position={position} sources={sources} /></li>)}</ol>
}

function DiscussionReview({ review, sources }: { review: Review; sources: Source[] }) {
  const [filter, setFilter] = useState('all'), [page, setPage] = useState(0)
  const points = review.positions.filter(p => filter === 'all' || p.kind === filter)
  const lastPage = Math.max(0, Math.ceil(points.length / 10) - 1), currentPage = Math.min(page, lastPage)
  return <Card title="Suggestions, agreements and conflicts" sub="Source wording is checked across all imported passages, independently of the generated summary.">
    <p className="jira-note">A suggestion is an idea. A recorded agreement explicitly names a choice. Different agreements on the same named setting may conflict. The newest message does not automatically win, and agreement does not prove implementation.</p>
    <p className="jira-muted">Checked {review.passages_checked} passages. These wording checks recognise explicit English statements and named choices; they can miss indirect or implicit disagreement. Full messages remain below.{review.partial_passages > 0 && ` ${review.partial_passages} partial passages cannot establish agreement.`}</p>
    {review.comparisons.length > 0 ? <section aria-label="Compared positions" className="decision-comparisons">
      {review.comparisons.map((comparison, index) => <details key={index} className="decision-comparison" open>
        <summary><strong>{comparison.subject}</strong> · {comparison.kind === 'conflict' ? 'Possible conflicting agreements' : comparison.kind === 'recorded_update' ? 'Recorded correction' : 'Different proposed or recorded choices'}</summary>
        <p className="jira-note">{comparison.reason}</p>
        <ComparedPositions ids={comparison.position_ids} positions={review.positions} sources={sources} />
      </details>)}
    </section> : <p className="jira-muted">No differing named choices were identified by these checks. This does not establish that the discussion is conflict-free.</p>}
    <label className="decision-filter">Show source positions<select aria-label="Show source positions" value={filter} onChange={event => { setFilter(event.target.value); setPage(0) }}>
      <option value="all">All recognised positions ({review.positions.length})</option>
      {(['decision', 'proposal', 'historical'] as const).map(kind => <option key={kind} value={kind}>{LABELS[kind]} ({review.positions.filter(p => p.kind === kind).length})</option>)}
    </select></label>
    {!points.length && <p className="jira-muted">No explicit positions of this type were recognised. Inspect the imported messages for context.</p>}
    <ol className="decision-points" aria-label="Source positions">{points.slice(currentPage * 10, currentPage * 10 + 10).map(position => <li key={position.id}><PositionEvidence position={position} sources={sources} /></li>)}</ol>
    {points.length > 10 && <div className="jira-related-pages">
      <Button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous positions</Button>
      <span>{currentPage * 10 + 1}–{Math.min(currentPage * 10 + 10, points.length)} of {points.length}</span>
      <Button disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>Next positions</Button>
    </div>}
  </Card>
}

function ChannelSummary({ channelId, status }: { channelId: string; status: Status }) {
  const reply = useApi<Detail>(`/api/decisions/channels/${encodeURIComponent(channelId)}`, 0, status.knowledge_revision)
  const job = status.job?.kind === 'decisions' && status.job.target === channelId ? status.job : null
  const running = !!job && ['queued', 'running', 'cancelling'].includes(job.state)
  const [pending, setPending] = useState(false), [started, setStarted] = useState(false), [error, setError] = useState('')
  const [filter, setFilter] = useState('all'), [page, setPage] = useState(0)
  const jobVersion = job ? `${job.id}:${job.state}` : ''
  const reload = reply.reload, previous = useRef(jobVersion)
  useEffect(() => {
    if (previous.current !== jobVersion && job && !running) reload()
    previous.current = jobVersion
    if (job) setStarted(false)
  }, [jobVersion, running, reload])
  const summarize = async () => {
    setPending(true); setError('')
    try { await post(`/api/decisions/channels/${encodeURIComponent(channelId)}/summarize`); setStarted(true) }
    catch (exc) { setError(exc instanceof ApiError ? exc.message : 'Could not start the summary.') }
    finally { setPending(false) }
  }
  if (reply.loading) return <Loading what="channel messages" />
  if (reply.error) return <Failed message={reply.error} onRetry={reload} />
  if (!reply.data) return null
  const { channel, sources, summary, review, coverage, read_at: readAt } = reply.data
  const points = (summary?.items ?? []).filter(point => filter === 'all' || point.kind === filter)
  const lastPage = Math.max(0, Math.ceil(points.length / 10) - 1), currentPage = Math.min(page, lastPage)
  const shown = points.slice(currentPage * 10, currentPage * 10 + 10)
  return <section className="decision-detail" aria-label="Selected Slack channel">
    <Card title={`#${channel.name}`} aside={<Button kind="ghost" onClick={reload}>Check saved summary</Button>}>
      <div className="jira-actions">
        <Button kind="primary" disabled={pending || started || status.busy} onClick={() => void summarize()}>
          {running || started ? 'Summarizing…' : summary ? 'Refresh summary' : 'Summarize decisions'}
        </Button>
        <span className="jira-muted">{sources.length} imported {sources.length === 1 ? 'passage' : 'passages'}</span>
      </div>
      {(running || started) && <p role="status">You can visit other screens. This summary will keep running in the background.</p>}
      {error && <Failed message={error} />}
      {job && ['failed', 'cancelled', 'interrupted'].includes(job.state) && <p className="jira-note">The latest attempt {job.state}. {job.error} {summary && 'The saved summary below is from the earlier successful attempt.'}</p>}
      <p className="jira-note">Labels describe wording in imported messages. Verify current agreement in Slack. Messages and replies are rechecked before saved content is used. If they changed, read Slack again in Connections. Import limits may omit older threads or later replies.</p>
      <p className="jira-muted">{readAt ? `Messages read ${new Date(readAt).toLocaleString()}. ` : ''}Import coverage: {coverage.state || 'unknown'}.</p>
      {coverage.state !== 'complete' && <p className="jira-note"><Chip tone="warn">Coverage {coverage.state || 'unknown'}</Chip> Check <Link to="/connections">Connections</Link> for missing messages and import limits.</p>}
    </Card>
    {review && <DiscussionReview review={review} sources={sources} />}
    {summary ? <Card title="Discussion summary" sub="Review each point with its supporting messages.">
      {summary.generations?.map((g,i)=><GenerationDetails key={i} value={g}/>)}
      <p className="jira-muted" aria-label="Summary details">Model: <strong>{summary.model}</strong> · Saved {new Date(summary.generated_at).toLocaleString()} · {summary.passages_read} passages read in {summary.parts} {summary.parts === 1 ? 'part' : 'parts'}{summary.demo && ' · Example data'}</p>
      {!summary.items.some(point => point.kind === 'decision') && <p className="jira-note">No explicit agreement was identified in this summary. The imported messages may contain additional context.</p>}
      {summary.labels_rechecked && <p className="jira-note">Labels on this saved summary were rechecked against its supporting quotes. No new model summary was generated.</p>}
      {summary.parts > 1 && <p className="jira-note">This summary was generated in separate parts. Named choices are compared across imported passages above; other cross-part disagreements may still be missed.</p>}
      <label className="decision-filter">Show points<select aria-label="Show points" value={filter} onChange={event => { setFilter(event.target.value); setPage(0) }}>
        <option value="all">All points ({summary.items.length})</option>
        {Object.entries(LABELS).map(([kind, label]) => <option key={kind} value={kind}>{label} ({summary.items.filter(point => point.kind === kind).length})</option>)}
      </select></label>
      {!points.length && <p className="jira-muted">No points of this type were summarized. Inspect the imported messages below.</p>}
      <ol className="decision-points">{shown.map((point, i) => <li key={`${currentPage}-${i}`}>
        <div className="jira-related-title"><Chip tone={point.kind === 'decision' ? 'ok' : point.kind === 'conflict' ? 'warn' : 'quiet'}>{LABELS[point.kind]}</Chip>{point.source_wording && <span className="jira-muted">Source wording</span>}</div>
        <p className="decision-text">{point.text}</p>
        {point.reason && <p className="jira-muted">{point.reason}</p>}
        {point.kind === 'conflict' && <p className="jira-note">Review both positions; this summary does not resolve the possible conflict.</p>}
        <details className="jira-quote"><summary>Supporting messages ({point.source_ids.length})</summary>
          {point.quotes.map((quote, q) => <blockquote key={q}><strong>{quote.source_id}: </strong>{quote.text}</blockquote>)}
          {point.source_ids.map(id => sources.find(source => source.source_id === id)).filter((source): source is Source => !!source).map(source => <Evidence key={source.source_id} source={source} />)}
        </details>
      </li>)}</ol>
      {points.length > 10 && <div className="jira-related-pages">
        <Button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous points</Button>
        <span>{currentPage * 10 + 1}–{Math.min(currentPage * 10 + 10, points.length)} of {points.length}</span>
        <Button disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>Next points</Button>
      </div>}
    </Card> : !running && !started && <Card><Empty title="Ready to summarize this channel" detail="Build a summary of recorded decisions, proposals, historical context and possible conflicts from its imported messages." /></Card>}
    <Card title="Imported messages" sub="Recorded author identifiers, timestamps and message text are preserved here.">
      <details><summary>Read all imported passages ({sources.length})</summary>{sources.map(source => <Evidence key={source.source_id} source={source} />)}</details>
    </Card>
  </section>
}

export function TeamDecisions() {
  const status = useStatus(2000)
  const list = useApi<{ channels: Channel[]; reason: string; awaiting_project?: boolean }>('/api/decisions/channels', 0, status.data?.knowledge_revision,
    !!status.data && !status.data.awaiting_project)
  const [chosen, setParams] = useRememberedParam('channel')
  const channels = list.data?.channels ?? []
  const selected = chosen || (status.data?.job?.kind === 'decisions' ? status.data.job.target : '') || channels[0]?.id || ''
  const head = <PageHead title="Team decisions" lead="Understand what was discussed in your imported Slack channels, with sources for every summary point."
    actions={<Button icon="refresh" onClick={list.reload}>Refresh channels</Button>} />
  if (status.data?.awaiting_project || list.data?.awaiting_project) return <>{head}<NoProject what="Team decisions" /></>
  if (status.error) return <>{head}<Failed message={status.error} onRetry={status.reload} /></>
  if (list.error) return <>{head}<Failed message={list.error} onRetry={list.reload} /></>
  if (list.loading || !status.data) return <>{head}<Loading what="imported Slack channels" /></>
  if (!channels.length) return <>{head}{status.data.warning && <Failed message={status.data.warning} />}<Card><Empty title="No Slack messages have been read" detail={list.data?.reason} action={<Link className="btn btn-primary" to="/connections">Read Slack messages</Link>} /></Card></>
  return <>{head}<div className="decision-detail">
    <Card><label className="decision-filter">Slack channel<select aria-label="Slack channel" value={selected} onChange={event => setParams({ channel: event.target.value })}>
      {!channels.some(channel => channel.id === selected) && <option value={selected}>Choose an imported channel</option>}
      {channels.map(channel => <option key={channel.id} value={channel.id}>#{channel.name} · {channel.excerpts} excerpts</option>)}
    </select></label></Card>
    {channels.some(channel => channel.id === selected) ? <ChannelSummary key={`${selected}:${status.data.knowledge_revision}`} channelId={selected} status={status.data} />
      : <Card><Empty title="This channel is not in the current import" detail="Choose a channel from the list." /></Card>}
  </div></>
}
