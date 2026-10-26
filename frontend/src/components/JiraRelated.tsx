import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Chip, Failed, Loading } from './ui'
import { useApi } from '../lib/useApi'

type Excerpt = { path: string; start: number; end: number; text: string; url: string; shortened: boolean }
type Related = Excerpt & {
  id: string; confidence: 'confirmed' | 'possible'; reason: string; shared_words: string[]; evidence: Excerpt | null
}
type Reply = {
  items: Related[]; total: number; confirmed: number; possible: number; searched: number
  next_offset: number | null; offset: number; limit: number; coverage: string; read_at: string | null
  repo: string; commit: string
}

function RelatedGroup({ issueKey, revision, kind }: {
  issueKey: string; revision: number; kind: 'files' | 'discussions'
}) {
  const [offset, setOffset] = useState(0)
  const reply = useApi<Reply>(`/api/jira/tasks/${encodeURIComponent(issueKey)}/links?kind=${kind}&offset=${offset}`, 0, revision)
  const reload = reply.reload
  const files = kind === 'files'
  const data = reply.data
  return <Card title={files ? 'Related project files' : 'Related Slack discussions'}
    sub={files ? 'Links to files at the scanned commit.' : 'Recorded excerpts from the selected Slack channels.'}
    aside={<Button kind="ghost" onClick={() => { setOffset(0); reload() }}>Refresh links</Button>}>
    {reply.loading && <Loading what={files ? 'related files' : 'related discussions'} />}
    {reply.error && <Failed message={reply.error} onRetry={reload} />}
    {data && <>
      <p className="jira-muted">{data.confirmed} confirmed {data.confirmed === 1 ? 'link' : 'links'} · {data.possible} possible {data.possible === 1 ? 'connection' : 'connections'}</p>
      <p className="jira-note">Checked {data.searched} imported {files ? 'files' : 'excerpts'}
        {files && <> in {data.repo} at <code>{data.commit.slice(0, 7)}</code></>}
        {data.read_at && <> · Read {new Date(data.read_at).toLocaleString()}</>}.</p>
      {data.coverage !== 'complete' && <p className="jira-note"><Chip tone="warn">{data.coverage === 'not_read' ? 'Slack not read' : `Coverage ${data.coverage}`}</Chip> Check <Link to="/connections">Connections</Link> for import scope and missing information.</p>}
      {!data.total && <p className="jira-note">{data.coverage === 'not_read'
        ? 'Select Slack channels and read messages in Connections to find discussion links.'
        : `No ${files ? 'file' : 'discussion'} links were found in the imported content. This does not establish that none exist.`}</p>}
      <ol className="jira-related-list">
        {data.items.map(item => <li key={item.id}>
          <div className="jira-related-title">
            {item.url ? <a href={item.url} target="_blank" rel="noreferrer"><strong>{files ? item.path : '#'+item.path.slice(6)}</strong> ↗</a>
              : <strong>{files ? item.path : '#'+item.path.slice(6)}</strong>}
            <Chip tone={item.confidence === 'confirmed' ? 'ok' : 'warn'}>{item.confidence === 'confirmed' ? 'Confirmed link' : 'Possible connection'}</Chip>
          </div>
          <p className="jira-note">{item.reason}</p>
          {!!item.shared_words.length && <p className="jira-muted">Shared words: {item.shared_words.join(', ')}.</p>}
          <details className="jira-quote"><summary>{files ? `Read file evidence · lines ${item.start}–${item.end}` : `Read discussion evidence · excerpt ${item.start}`}</summary>
            <pre className="jira-related-text">{item.text}</pre>
            {item.shortened && <p className="jira-muted">Showing the portion around the match.</p>}
          </details>
          {item.evidence && <details className="jira-quote"><summary>Reference recorded in the Jira task</summary>
            <blockquote>{item.evidence.text}</blockquote>
            <a href={item.evidence.url} target="_blank" rel="noreferrer">Open task reference ↗</a>
          </details>}
          {!files && <p className="jira-note">{item.url ? 'The Slack link opens the first message of the imported excerpt; the matching message may appear later.' : 'No message permalink was stored for this excerpt.'} Discussion text does not establish an agreed decision.</p>}
        </li>)}
      </ol>
      {data.total > 0 && <div className="jira-related-pages">
        <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset-data.limit))}>Previous</Button>
        <span className="jira-muted">{offset+1}–{Math.min(offset+data.items.length, data.total)} of {data.total}</span>
        <Button disabled={data.next_offset === null} onClick={() => setOffset(data.next_offset!)}>Next</Button>
      </div>}
    </>}
  </Card>
}

export function JiraRelated({ issueKey, revision }: { issueKey: string; revision: number }) {
  return <section id="task-related" className="jira-detail" aria-label="Related files and discussions">
    <div><h2>Related files and discussions</h2><p className="jira-note">Confirmed means an explicit reference was recorded. Possible means shared words only. Neither proves that the task was implemented.</p></div>
    <RelatedGroup issueKey={issueKey} revision={revision} kind="files" />
    <RelatedGroup issueKey={issueKey} revision={revision} kind="discussions" />
  </section>
}
