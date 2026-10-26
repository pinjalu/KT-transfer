import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Chip, Empty, Failed, Loading, Missing, NoProject, PageHead } from '../components/ui'
import { useApi } from '../lib/useApi'
import { useStatus } from '../lib/useStatus'
import { sourcePath } from '../lib/answer'
import './existing-tests.css'

type Check = { line: number; end: number; code: string; explanation: string; url: string }
type Definition = { name: string; line: number; end: number; url: string; description: string; why: string;
  framework: string; status: string; checks: Check[]; markers: Check[]; gaps: string[] }
export type TestInventory = { available: boolean; reason?: string; commit?: string; partial_scan?: boolean;
  candidate_files: number; definitions: number; omitted_files: number; note: string;
  files: { path: string; url: string; tests: Definition[]; gaps: string[] }[] }

export function ExistingTests() {
  const status = useStatus()
  const result = useApi<TestInventory>('/api/existing-tests', 30000, status.data?.knowledge_revision,
    !!status.data && !status.data.awaiting_project)
  const [search, setSearch] = useState('')
  const head = <PageHead title="Existing tests" lead="Read the checks defined in saved project files and see why each assertion matters."
    actions={<Button icon="refresh" onClick={result.reload}>Refresh test definitions</Button>} />
  if (status.error) return <>{head}<Failed message={status.error} onRetry={status.reload} /></>
  if (status.data?.awaiting_project) return <>{head}<NoProject what="test definitions" /></>
  if (result.error) return <>{head}<Failed message={result.error} onRetry={result.reload} /></>
  if (!result.data) return <>{head}<Loading what="test definitions" detail="Reading saved code and checking source access. No project tests are run." /></>
  const body = result.data
  if (!body.available) return <>{head}<Card><Empty title="Read a project first" detail={body.reason}
    action={<Link to="/connections">Go to Connections</Link>} /></Card></>
  const term = search.trim().toLowerCase()
  const shown = body.files.map(file => ({ ...file, tests: file.tests.filter(test =>
    `${file.path} ${test.name} ${test.description}`.toLowerCase().includes(term)) }))
    .filter(file => file.tests.length || file.path.toLowerCase().includes(term))
  return <>{head}<div className="existing-tests">
    <Card title="What was found" aside={<Chip tone="info">Definitions · Not run</Chip>}>
      <p>{body.definitions} test definitions shown across {body.files.length} of {body.candidate_files} candidate files. Saved revision {body.commit?.slice(0, 7)}.</p>
      <p>{body.note}</p>
      <p>Supported: Python assert, common unittest assertions and exception expectations. Helpers, fixtures, custom collectors and other languages may contain additional checks.</p>
      {body.partial_scan && <Missing what="This source scan is partial. Files or test definitions may be missing." />}
      {!!body.omitted_files && <Missing what={`${body.omitted_files} candidate files exceed this view's file limit.`} />}
      {!body.definitions && <Empty title="No supported test definitions found" detail="This does not mean the project has no tests. Review the candidate files and analysis gaps below." />}
      <label className="existing-test-search">Find a test or file<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Test name, file or docstring" /></label>
    </Card>
    {!shown.length && term && <Empty title="No matching tests or files" action={<Button onClick={() => setSearch('')}>Clear search</Button>} />}
    {shown.map(file => <Card key={file.path} title={sourcePath(file.path)} aside={<a href={file.url} target="_blank" rel="noreferrer">View file</a>}>
      {file.gaps.map(gap => <Missing key={gap} what={gap} />)}
      {file.tests.map(test => <details key={`${test.name}:${test.line}`} className="existing-test">
        <summary><strong>{test.name}</strong><span>{test.checks.length} recognized checks · Lines {test.line}–{test.end}</span></summary>
        <p><Chip tone="info">Definition · Not run</Chip> {test.framework}</p>
        {test.description && <div><h3>Purpose recorded in the test</h3><blockquote>{test.description}</blockquote></div>}
        <h3>Why these checks matter</h3><p>{test.why}</p>
        <a href={test.url} target="_blank" rel="noreferrer">View test definition</a>
        {test.markers.length > 0 && <><h3>Collection and execution conditions</h3>{test.markers.map((marker, i) => <CheckEvidence key={i} item={marker} />)}</>}
        <h3>Assertions and expected exceptions</h3>
        {test.checks.map((check, i) => <CheckEvidence key={i} item={check} />)}
        {test.gaps.map(gap => <Missing key={gap} what={gap} />)}
      </details>)}
    </Card>)}
    <p>For new test ideas, use <Link to={`/ask?q=${encodeURIComponent('Suggest two tests for this project with reasons and verification steps.')}`}>Ask assistant</Link>. Suggestions remain separate from these existing definitions.</p>
  </div></>
}

function CheckEvidence({ item }: { item: Check }) {
  return <article className="existing-check"><p>{item.explanation}</p><pre><code>{item.code}</code></pre>
    <a href={item.url} target="_blank" rel="noreferrer">Source lines {item.line}–{item.end}</a></article>
}
