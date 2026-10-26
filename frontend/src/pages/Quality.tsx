import { useState } from 'react'
import { Button, Card, Chip, Empty, Failed, Loading, Missing, NoProject, PageHead } from '../components/ui'
import { useStatus } from '../lib/useStatus'
import { useApi } from '../lib/useApi'
import { post } from '../lib/api'
import { Statements } from '../components/Statements'
import { TestSuggestions } from '../components/TestSuggestions'
import type { Answer } from '../lib/answer'
import './ask.css'
import './quality.css'

type Review = { reviewer: string; correctness: string; source_sufficiency: string; reviewed_at?: string }
type Result = { case_id: string; status: string; response_hash: string; answer_id?: number; human_review: Review | null;
  behavior_check: boolean; retrieval: { reference_excerpt_found: boolean | null };
  citations: { unknown_ids: number; uncited_statements: number; invalid_github_links: number; external_links_not_checked: number };
  reference_phrase_checks: { id: string; cited_reference_phrase_match: boolean }[] }
type Run = { id: number; title: string; state: string; model: string; started_at: string; scan_status: string;
  results: Result[]; cases_planned: number; summary: { automatic_checks_passed: number; human_reviewed: number;
    human_correctness: Record<string, number>; human_source_sufficiency: Record<string, number> } }
type Catalog = { sets: { id: string; title: string; repo: string; commit: string; cases: number; available: boolean; reason: string }[]; runs: Run[] }
type Detail = { dataset_hash: string; case: { id: string; question: string; behavior: string; review_note?: string;
  facts?: { id: string; references: { path: string; start: number; end: number }[] }[] }; result: Result; answer: Answer }
const running = (state: string) => ['queued', 'running', 'cancelling'].includes(state)
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'The request failed. Try again.'

function CaseReview({ run, caseId, onSaved }: { run: Run; caseId: string; onSaved: () => void }) {
  const path = `/api/quality/runs/${run.id}/cases/${encodeURIComponent(caseId)}`
  const detail = useApi<Detail>(path)
  const [correctness, setCorrectness] = useState('')
  const [sufficiency, setSufficiency] = useState('')
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const data = detail.data
  const save = async () => {
    if (!data || !correctness || !sufficiency || running(run.state)) return
    setSaving(true); setError(''); setNote('')
    try {
      await post(`${path}/review`, { dataset_hash: data.dataset_hash, response_hash: data.result.response_hash,
        correctness, source_sufficiency: sufficiency })
      setNote('Review saved for this exact answer.'); detail.reload(); onSaved()
    } catch (exc) { setError(errorMessage(exc)) }
    finally { setSaving(false) }
  }
  if (detail.error) return <Failed message={detail.error} onRetry={detail.reload} />
  if (!data) return <Loading what="the exact answer and source access" />
  const { answer, result } = data
  // Retained Ask/Overview pages can contain S1 too; review citations must target this case.
  const prefix = `quality-${run.id}-${caseId}-`
  const sources = answer.sources.map(source => ({ ...source, source_id: prefix + source.source_id }))
  const statements = answer.statements.map(statement => ({ ...statement, source_ids: statement.source_ids.map(id => prefix + id) }))
  const tests = answer.test_suggestions?.map(test => ({ ...test, evidence: test.evidence.map(item => ({ ...item, source_id: prefix + item.source_id })) }))
  return <Card title={data.case.question} sub={`Expected behaviour: ${data.case.behavior.replaceAll('_', ' ')}`}>
    {data.case.review_note && <Missing what={data.case.review_note} checked="Reference guidance for the reviewer" />}
    <h3>Exact generated answer</h3>
    {answer.error && <Failed message={answer.error} />}
    {tests?.length ? <TestSuggestions tests={tests} sources={sources} /> : <Statements statements={statements} sources={sources} />}
    {answer.missing_information && <Missing what={answer.missing_information} />}
    {answer.warning && <Missing what={answer.warning} />}
    <details className="quality-checks"><summary>Automatic check details</summary>
      <p>Expected behaviour: {result.behavior_check ? 'matched' : 'not matched'}. Reference excerpt retrieved: {result.retrieval.reference_excerpt_found === null ? 'not applicable' : result.retrieval.reference_excerpt_found ? 'yes' : 'no'}.</p>
      <p>{result.citations.unknown_ids} unknown citations; {result.citations.uncited_statements} uncited statements; {result.citations.invalid_github_links} invalid repository links. {result.citations.external_links_not_checked} external links need manual checking.</p>
      <ul>{result.reference_phrase_checks.map(check => <li key={check.id}>{check.id}: {check.cited_reference_phrase_match ? 'reference phrase matched' : 'reference phrase not matched'}</li>)}</ul>
      <p>Phrase matches do not establish meaning or factual correctness. Check negation, conditions and deployment scope yourself.</p>
    </details>
    <h3>Retrieved sources</h3>
    {!answer.sources.length && <p>No source excerpts were retrieved.</p>}
    <ol className="src-list">{sources.map((s, i) => <li className="src" id={`src-${s.source_id}`} key={s.source_id}>
      <div className="src-head"><span className="src-n">[{i + 1}]</span><span className="src-path mono">{s.path}</span></div>
      <p className="src-lines">Lines {s.start} to {s.end}</p><pre className="src-text">{s.text}</pre>
      {s.url && <a href={s.url} target="_blank" rel="noreferrer">View source</a>}
    </li>)}</ol>
    <h3>Your review</h3>
    <p>Judge every claim against the sources. Rate factual correctness and source sufficiency separately. Use “Partially correct” for mixed or incomplete answers.</p>
    {result.human_review && <p>Saved by {result.human_review.reviewer}: {result.human_review.correctness}; sources {result.human_review.source_sufficiency}.</p>}
    <div className="quality-review">
      <label>Correctness<select value={correctness} onChange={e => setCorrectness(e.target.value)}>
        <option value="">Choose a rating</option><option value="correct">Correct</option><option value="partially correct">Partially correct</option><option value="incorrect">Incorrect</option>
      </select></label>
      <label>Source sufficiency<select value={sufficiency} onChange={e => setSufficiency(e.target.value)}>
        <option value="">Choose a rating</option><option value="sufficient">Sufficient</option><option value="partly sufficient">Partly sufficient</option><option value="insufficient">Insufficient</option>
      </select></label>
      <Button kind="primary" disabled={saving || !correctness || !sufficiency || running(run.state)} onClick={() => void save()}>{saving ? 'Saving…' : 'Save my review'}</Button>
    </div>
    {running(run.state) && <p>Reviews can be saved when the evaluation finishes.</p>}
    {note && <p role="status">{note}</p>}{error && <Failed message={error} />}
  </Card>
}

export function Quality() {
  const status = useStatus()
  const ready = !!status.data?.ready && !status.data?.awaiting_project
  const catalog = useApi<Catalog>('/api/quality', 3000, status.data?.knowledge_revision, ready)
  const [setId, setSetId] = useState('')
  const [runId, setRunId] = useState<number | null>(null)
  const [caseId, setCaseId] = useState('')
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const data = catalog.data
  const selectedSet = data?.sets.find(s => s.id === setId) ?? data?.sets[0]
  const run = data?.runs.find(r => r.id === runId) ?? data?.runs[0]
  const selectedCase = run?.results.find(r => r.case_id === caseId)
  const start = async () => {
    if (!selectedSet || !selectedSet.available || starting || status.data?.busy) return
    setStarting(true); setError('')
    try {
      const result = await post('/api/quality/runs', { set_id: selectedSet.id }) as { job_id: number }
      setRunId(result.job_id); setCaseId(''); catalog.reload(); status.reload()
    } catch (exc) { setError(errorMessage(exc)) }
    finally { setStarting(false) }
  }
  return <div className="quality-page">
    <PageHead title="Answer quality" lead="Run saved questions, inspect the exact answers and review the evidence." />
    {!ready ? <NoProject what="answer evaluation" /> : <>
      <Missing what="Automatic checks are not an accuracy score. Human correctness and evidence reviews remain separate." />
      {catalog.error && <Failed message={catalog.error} onRetry={catalog.reload} />}
      {!data && !catalog.error && <Loading what="saved evaluations" />}
      {data && <>
        <Card title="Run a question set" sub="Each run uses the selected project's current sources and model. You can navigate away while it runs.">
          <div className="quality-review"><label>Question set<select value={selectedSet?.id ?? ''} onChange={e => setSetId(e.target.value)}>
            {data.sets.map(s => <option value={s.id} key={s.id}>{s.title} ({s.cases} questions)</option>)}
          </select></label>
          <Button kind="primary" disabled={!selectedSet?.available || starting || status.data?.busy} onClick={() => void start()}>{starting ? 'Starting…' : 'Run evaluation'}</Button></div>
          {selectedSet && <p className="quality-scope">{selectedSet.repo} · Commit {selectedSet.commit.slice(0, 7)}</p>}
          {selectedSet?.reason && <Missing what={selectedSet.reason} />}
          {error && <Failed message={error} />}
        </Card>
        {!data.runs.length ? <Empty title="No evaluations yet." detail="Start a matching question set. Recent runs remain available until the sources change." /> : <Card title="Saved runs" sub="Up to 20 recent evaluations. Refreshing sources clears their answers and reviews.">
          <label className="quality-run-select">Evaluation run<select value={run?.id ?? ''} onChange={e => { setRunId(Number(e.target.value)); setCaseId('') }}>
            {data.runs.map(r => <option key={r.id} value={r.id}>#{r.id} · {r.title} · {r.started_at}</option>)}
          </select></label>
          {run && <>
            <p><Chip>{run.state}</Chip> {run.model} · {run.results.length} of {run.cases_planned} cases run · {run.scan_status} source scan</p>
            <div className="quality-counts"><p><strong>{run.summary.automatic_checks_passed}/{run.cases_planned}</strong> passed automatic checks</p><p><strong>{run.summary.human_reviewed}/{run.cases_planned}</strong> reviewed by a person</p></div>
            {run.summary.human_reviewed > 0 && <p>Human correctness: {Object.entries(run.summary.human_correctness).map(([label, count]) => `${count} ${label}`).join(', ')}. Sources: {Object.entries(run.summary.human_source_sufficiency).map(([label, count]) => `${count} ${label}`).join(', ')}.</p>}
            <div className="quality-table-wrap"><table className="quality-table"><thead><tr><th>Case</th><th>Automatic checks</th><th>Human review</th><th>Answer</th></tr></thead>
              <tbody>{run.results.map(row => <tr key={row.case_id}><td>{row.case_id.replaceAll('_', ' ')}</td><td>{row.status === 'passed_checks' ? 'Passed checks' : 'Needs inspection'}</td><td>{row.human_review ? `${row.human_review.correctness}; ${row.human_review.source_sufficiency}` : 'Not reviewed'}</td><td><Button disabled={!row.answer_id} onClick={() => setCaseId(row.case_id)}>Inspect {row.case_id.replaceAll('_', ' ')}</Button></td></tr>)}</tbody>
            </table></div>
          </>}
        </Card>}
        {run && selectedCase && <CaseReview key={`${run.id}:${caseId}`} run={run} caseId={caseId} onSaved={catalog.reload} />}
      </>}
    </>}
  </div>
}
