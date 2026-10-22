import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button, Card, Chip, Empty, Failed, Loading, NoProject, PageHead } from '../components/ui'
import { Said } from '../components/Statements'
import { JiraRelated } from '../components/JiraRelated'
import { ApiError, post } from '../lib/api'
import { useApi } from '../lib/useApi'
import type { Source, Statement } from '../lib/answer'
import type { Status } from '../lib/types'
import './jira-tasks.css'

type Issue = { key: string; title: string; url: string; excerpts: number }
type Point = Statement & { quote: string }
type Explanation = {
  issue_key: string; summary: Point[]; requirements: Point[]; acceptance_criteria: Point[]; questions: Point[]
  sources: Source[]; generated_at: string; model: string; demo: boolean; excerpts_read: number; parts: number
}
type Detail = {
  issue: Issue; sources: Source[]; explanation: Explanation | null; access_checked_at: string
  coverage: { state?: string; notes?: string[] } | null
}

function Points({ title, points, sources, empty, sub }: {
  title: string; points: Point[]; sources: Source[]; empty: string; sub?: string
}) {
  return <Card title={title} sub={sub}>
    {points.length ? <ol className="jira-points">
      {points.map((point, i) => <li key={i}>
        <ol className="said-list"><Said statement={point} sources={sources} showContextMark={false} /></ol>
        <details className="jira-quote"><summary>Supporting quote</summary><blockquote>{point.quote}</blockquote></details>
      </li>)}
    </ol> : <p className="jira-muted">{empty}</p>}
  </Card>
}

function Task({ issueKey, status }: { issueKey: string; status: Status }) {
  const job = status.job?.kind === 'jira_task' && status.job.target === issueKey ? status.job : null
  const running = !!job && ['queued', 'running', 'cancelling'].includes(job.state)
  const reply = useApi<Detail>(`/api/jira/tasks/${encodeURIComponent(issueKey)}`, 0, status.knowledge_revision)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [started, setStarted] = useState(false)
  const reload = reply.reload
  const previousJob = useRef(job?.state)
  useEffect(() => {
    if (previousJob.current !== job?.state && job && !running) reload()
    previousJob.current = job?.state
    if (job) setStarted(false)
  }, [job?.id, job?.state, running, reload])
  // Recheck access when returning to a tab, without repeatedly fetching whole Jira issues.
  useEffect(() => {
    const visible = () => { if (document.visibilityState === 'visible') reload() }
    document.addEventListener('visibilitychange', visible)
    return () => document.removeEventListener('visibilitychange', visible)
  }, [reload])

  const explain = async () => {
    setPending(true); setError('')
    try {
      await post(`/api/jira/tasks/${encodeURIComponent(issueKey)}/explain`)
      setStarted(true)
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Could not start the explanation.')
    } finally { setPending(false) }
  }
  if (reply.loading) return <Loading what={issueKey} />
  if (reply.error) return <Failed message={reply.error} onRetry={reload} />
  if (!reply.data) return null
  const { issue, sources, explanation: answer, coverage } = reply.data
  return <div className="jira-detail" aria-label="Selected Jira task">
    <Card title={`${issue.key} — ${issue.title}`} aside={<a href={issue.url} target="_blank" rel="noreferrer">Open in Jira ↗</a>}>
      <div className="jira-actions">
        <Button kind="primary" onClick={() => void explain()} disabled={pending || started || status.busy}>
          {running || started ? 'Explaining task…' : answer ? 'Refresh explanation' : 'Explain task'}
        </Button>
        <span className="jira-muted">{sources.length} imported {sources.length === 1 ? 'excerpt' : 'excerpts'}</span>
        <a className="btn btn-secondary" href="#task-related">Related files and discussions</a>
      </div>
      {(running || started) && <p role="status" className="jira-note">You can visit other screens. This explanation will keep running in the background.</p>}
      {error && <Failed message={error} />}
      {job && ['failed', 'cancelled', 'interrupted'].includes(job.state) &&
        <p className="jira-note">The latest attempt {job.state}. {job.error} {answer ? 'The saved explanation below is from the earlier successful attempt.' : ''}</p>}
      <p className="jira-note">Based on the imported Jira text. An explanation does not confirm that the requested work is implemented.</p>
      {coverage?.state !== 'complete' && <p className="jira-note"><Chip tone="warn">Import coverage {coverage?.state || 'unknown'}</Chip> Some task details may not have been read. Check <Link to="/connections">Connections</Link>.</p>}
      {!!coverage?.notes?.length && <details className="jira-quote"><summary>Import limits and notes</summary><ul>{coverage.notes.map((note, i) => <li key={i}>{note}</li>)}</ul></details>}
    </Card>
    {answer ? <>
      <p className="jira-muted" aria-label="Explanation details">
        Model: <strong>{answer.model}</strong> · Saved {new Date(answer.generated_at).toLocaleString()} · {answer.excerpts_read} excerpts read in {answer.parts} {answer.parts === 1 ? 'part' : 'parts'}
        {answer.demo && ' · Example data and deterministic explanation'}
      </p>
      <Points title="What this task means" points={answer.summary} sources={sources} empty="No summary was extracted. Read the imported text below." />
      <Points title="Requested work" points={answer.requirements} sources={sources} empty="No requested work was extracted. Check the original task for details." />
      <Points title="Acceptance criteria" points={answer.acceptance_criteria} sources={sources} empty="No explicit acceptance criteria were extracted. Confirm completion checks with the task owner." />
      <Points title="Questions to clarify" points={answer.questions} sources={sources}
        sub="Suggested questions for the task owner. These are not agreed requirements."
        empty={answer.parts > 1 ? 'No questions were generated because this task was read in multiple parts. Review the combined excerpts for unresolved details.' : 'No clarification questions were generated.'} />
    </> : !running && !started && <Card><Empty title="Ready to explain this task" detail="Generate a summary, requested work and acceptance criteria with links to the imported evidence." /></Card>}
    <JiraRelated issueKey={issueKey} revision={status.knowledge_revision} />
    <Card title="Imported evidence" sub="Citations refer to these excerpts. Check the original wording when a statement needs review.">
      <div className="jira-sources">{sources.map((source, i) => <section id={`src-${source.source_id}`} key={source.source_id} className="jira-source" tabIndex={-1}>
        <div><strong>[{i + 1}] {issue.key}</strong> <span className="jira-muted">Lines {source.start}–{source.end}</span></div>
        <details><summary>Read excerpt {i + 1}</summary><pre>{source.text}</pre></details>
      </section>)}</div>
    </Card>
  </div>
}

export function JiraTasks() {
  const status = useApi<Status>('/api/status', 2000)
  const list = useApi<{ issues: Issue[]; reason: string; awaiting_project?: boolean }>('/api/jira/tasks', 0, status.data?.knowledge_revision)
  const [params, setParams] = useSearchParams()
  const [filter, setFilter] = useState('')
  const issues = list.data?.issues ?? []
  const selected = params.get('issue') || (status.data?.job?.kind === 'jira_task' ? status.data.job.target : '') || issues[0]?.key || ''
  const shown = issues.filter(issue => `${issue.key} ${issue.title}`.toLowerCase().includes(filter.toLowerCase()))
  const head = <PageHead title="Jira tasks" lead="Choose an imported task to understand its purpose, requested work and completion checks." />
  if (status.data?.awaiting_project || list.data?.awaiting_project) return <>{head}<NoProject what="Jira tasks" /></>
  if (status.error) return <>{head}<Failed message={status.error} onRetry={status.reload} /></>
  if (list.loading || !status.data) return <>{head}<Loading what="Jira tasks" /></>
  if (list.error) return <>{head}<Failed message={list.error} onRetry={list.reload} /></>
  if (!issues.length) return <>{head}{status.data.warning && <Failed message={status.data.warning} />}<Card><Empty title="No Jira tasks have been read" detail={list.data?.reason} action={<Link className="btn btn-primary" to="/connections">Read Jira issues</Link>} /></Card></>
  return <>{head}<div className="jira-layout">
    <Card title="Imported tasks" sub={`${issues.length} tasks`}>
      <label className="jira-search">Find a task<input type="search" value={filter} onChange={e => setFilter(e.target.value)} placeholder="Key or title" /></label>
      <div className="jira-task-list" role="group" aria-label="Choose Jira task">
        {shown.map(issue => <button type="button" key={issue.key} aria-pressed={selected === issue.key} onClick={() => setParams({ issue: issue.key })}>
          <strong>{issue.key}</strong><span>{issue.title}</span>
        </button>)}
        {!shown.length && <p className="jira-muted">No tasks match this search.</p>}
      </div>
    </Card>
    {issues.some(issue => issue.key === selected)
      ? <Task key={`${selected}:${status.data.knowledge_revision}`} issueKey={selected} status={status.data} />
      : <Card><Empty title="This task is not in the current import" detail="Select a task from the list." /></Card>}
  </div></>
}
