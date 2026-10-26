import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Chip, Empty, Failed, Missing, NoProject, PageHead, Segmented } from '../components/ui'
import { Icon } from '../components/Icon'
import { useStatus } from '../lib/useStatus'
import { usePageActive } from '../lib/pageState'
import { ApiError, post } from '../lib/api'
import { Said, Statements } from '../components/Statements'
import { TestSuggestions } from '../components/TestSuggestions'
import type { Answer, Turn } from '../lib/answer'
import { originOf, sourcePath, conversationContext } from '../lib/answer'
import './ask.css'

const MODES = ['Beginner', 'Developer', 'Architect'] as const
type Mode = (typeof MODES)[number]

/** What each reader sees. The answer itself is identical; this only decides how much is shown. */
const SHOWS: Record<Mode, { citations: boolean; excerpts: boolean; terms: boolean; checks: boolean }> = {
  Beginner: { citations: false, excerpts: false, terms: false, checks: false },
  Developer: { citations: true, excerpts: true, terms: true, checks: true },
  Architect: { citations: true, excerpts: false, terms: true, checks: true },
}

function Sources({ answer, mode }: { answer: Answer; mode: Mode }) {
  if (!answer.sources.length) {
    return <Empty title="No excerpt matched this question."
                  detail="Nothing was retrieved, so nothing below is standing behind an answer." />
  }
  return (
    <ol className="src-list">
      {answer.sources.map((s, i) => (
        <li className="src" id={`src-${s.source_id}`} key={s.source_id}>
          <div className="src-head">
            <span className="src-n">[{i + 1}]</span>
            <span className="src-path mono">{sourcePath(s.path)}</span>
            <Chip tone="quiet">{originOf(s.path, s.url)}</Chip>
          </div>
          <p className="src-lines">Lines {s.start} to {s.end}</p>
          {SHOWS[mode].excerpts && <pre className="src-text">{s.text}</pre>}
          {s.url && (
            <a className="src-open" href={s.url} target="_blank" rel="noreferrer">
              View source <Icon name="external" size={13} />
            </a>
          )}
        </li>
      ))}
    </ol>
  )
}

function Feedback({ turn, onSaved }: { turn: Turn; onSaved: (r: string, s: string) => void }) {
  const [note, setNote] = useState('')
  const save = async (rating: string, sufficiency: string) => {
    try {
      await post('/api/feedback', { answer_id: turn.answer!.answer_id, rating, sufficiency })
      onSaved(rating, sufficiency)
      setNote('Saved.')
    } catch (exc) {
      setNote(exc instanceof ApiError ? exc.message : 'Could not save that.')
    }
  }
  const rating = turn.rating ?? 'not assessed'
  const sufficiency = turn.sufficiency ?? 'not assessed'
  return (
    <div className="fb">
      <span className="fb-q">Was this correct?</span>
      <Button kind={rating === 'correct' ? 'primary' : 'secondary'}
              onClick={() => save('correct', sufficiency)}>Correct</Button>
      <Button kind={rating === 'partially correct' ? 'primary' : 'secondary'}
              onClick={() => save('partially correct', sufficiency)}>Partly</Button>
      <Button kind={rating === 'incorrect' ? 'primary' : 'secondary'}
              onClick={() => save('incorrect', sufficiency)}>Incorrect</Button>
      <span className="fb-q fb-q2">Were the sources enough?</span>
      <Button kind={sufficiency === 'sufficient' ? 'primary' : 'secondary'}
              onClick={() => save(rating, 'sufficient')}>Yes</Button>
      <Button kind={sufficiency === 'insufficient' ? 'primary' : 'secondary'}
              onClick={() => save(rating, 'insufficient')}>No</Button>
      {note && <span className="fb-note">{note}</span>}
    </div>
  )
}

export function Ask() {
  const status = useStatus()
  const [mode, setMode] = useState<Mode>('Beginner')
  const [turns, setTurns] = useState<Turn[]>([])
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const foot = useRef<HTMLDivElement>(null)
  const active = usePageActive()
  const activePage = useRef(active)
  activePage.current = active

  const ready = status.data?.ready ?? false
  const busy = status.data?.busy ?? false
  const awaiting = status.data?.awaiting_project ?? false

  const ask = async () => {
    const text = question.trim()
    if (!text || asking || busy || !ready || awaiting) return
    setAsking(true)
    setQuestion('')
    const turn: Turn = { question: text, asked_at: new Date().toISOString(), answer: null, failed: null,
      knowledge_revision: status.data?.knowledge_revision }
    setTurns((t) => [...t, turn])
    try {
      const conversation = conversationContext(turns, status.data?.settings?.repo, status.data?.knowledge_revision)
      const body = (await post('/api/ask', { question: text, ...(conversation ? { conversation } : {}) })) as Answer
      setTurns((t) => t.map((x) => (x === turn ? { ...x, answer: body } : x)))
    } catch (exc) {
      const why = exc instanceof ApiError ? exc.message : 'The answer could not be generated.'
      const denied = exc instanceof ApiError && ['access_denied', 'scope', 'access', 'access_unverified', 'stale'].includes(exc.code)
      setTurns((t) => t.map((x) => x === turn ? { ...x, failed: why }
        : denied ? { ...x, answer: null, failed: 'Source access could not be verified. Retry after checking the connection.' } : x))
    } finally {
      setAsking(false)
      requestAnimationFrame(() => { if (activePage.current) foot.current?.scrollIntoView({ block: 'end' }) })
    }
  }

  const latest = [...turns].reverse().find((t) => t.answer)?.answer ?? null

  return (
    <>
      <PageHead title="Ask your project"
                lead="Answers come only from what was read, and every one shows the excerpt behind it." />
      <p className="ask-mode-note">Recent replies help with follow-up questions. Your conversation stays here when you switch pages or tabs. Refreshing this browser page clears it.</p>

      <div className="ask-modes">
        <Segmented items={[...MODES]} active={mode} onPick={(m) => setMode(m as Mode)} />
        <span className="ask-mode-note">
          The answer is the same either way. The mode decides how much of the working is shown.
        </span>
      </div>

      {awaiting && <NoProject what="the answers" />}

      {!awaiting && !ready && (
        <Card>
          <Empty title="Nothing has been read yet."
                 detail="A question is answered from the scanned files, so there is nothing to answer from until a scan finishes."
                 action={<Link className="btn btn-primary" to="/connections">Go to Connections</Link>} />
        </Card>
      )}

      {(ready || turns.length > 0) && (
        <div className="grid-main ask-grid">
          <div className="stack">
            <Card pad={false}>
              <div className="thread">
                {turns.length === 0 && (
                  <Empty title="Ask anything about this project."
                         detail="How does login work? Where are the database models defined? What does this route touch?" />
                )}
                {turns.map((turn, i) => (
                  <div className="turn" key={i}>
                    <div className="mine"><p>{turn.question}</p></div>
                    {turn.answer && turn.knowledge_revision !== undefined && status.data
                      && turn.knowledge_revision !== status.data.knowledge_revision &&
                      <p className="ask-mode-note">Earlier answer: the project sources have been updated since this reply.</p>}

                    {!turn.answer && !turn.failed && (
                      <div className="theirs">
                        <div className="loading">
                          <span className="spinner" aria-hidden="true" />
                          Reading the files and writing an answer. On a small local model this takes a while.
                        </div>
                      </div>
                    )}

                    {turn.failed && <div className="theirs"><Failed message={turn.failed} /></div>}

                    {turn.answer && (
                      <div className="theirs">
                        {turn.answer.warning && (
                          <div className="ans-warn"><Chip tone="warn">{turn.answer.warning}</Chip></div>
                        )}

                        {turn.answer.test_suggestions?.length ? <TestSuggestions tests={turn.answer.test_suggestions} sources={turn.answer.sources} /> : turn.answer.statements.length > 0 ? (
                          <>
                            <div className="answer-lead">
                              <p className="answer-label">Answer</p>
                              <ol className="said-list">
                                <Said statement={turn.answer.statements[0]} sources={turn.answer.sources}
                                      citations={SHOWS[mode].citations} showContextMark={false} />
                              </ol>
                            </div>
                            {turn.answer.statements.length > 1 && (
                              <div className="answer-details">
                                <p className="answer-label">Details</p>
                                <Statements statements={turn.answer.statements.slice(1)}
                                            sources={turn.answer.sources}
                                            citations={SHOWS[mode].citations} showContextMark={false} />
                              </div>
                            )}
                          </>
                        ) : (
                          <Missing what={turn.answer.missing_information || 'No answer was produced.'}
                                   checked={turn.answer.error ?? undefined} />
                        )}

                        {turn.answer.statements.length > 0 && turn.answer.missing_information && (
                          <Missing what={turn.answer.missing_information} />
                        )}

                        {SHOWS[mode].terms && turn.answer.search?.unknown?.length ? (
                          <p className="ans-terms">
                            Not found in the indexed content:{' '}
                            <span className="mono">{turn.answer.search.unknown.join(', ')}</span>
                          </p>
                        ) : null}

                        {SHOWS[mode].checks && turn.answer.checks && (
                          <p className="ans-checks">
                            {turn.answer.checks.dropped_repeats} repeated statement(s) dropped,{' '}
                            {turn.answer.checks.narrowed_citations} citation(s) narrowed,{' '}
                            {turn.answer.checks.unsupported} not found in the excerpt cited.
                            Answered in {turn.answer.elapsed_seconds}s.
                          </p>
                        )}

                        {/* A greeting is answered without reading anything and is never
                            recorded, so it carries answer_id 0 and there is nothing to rate. */}
                        {turn.answer.answer_id > 0 && (
                          <Feedback turn={turn}
                                    onSaved={(r, s) => setTurns((t) =>
                                      t.map((x) => (x === turn ? { ...x, rating: r, sufficiency: s } : x)))} />
                        )}
                      </div>
                    )}
                  </div>
                ))}
                <div ref={foot} />
              </div>

              <form className="ask-bar" onSubmit={(e) => { e.preventDefault(); void ask() }}>
                <span className="ask-icon"><Icon name="chat" /></span>
                <textarea rows={1} maxLength={600} value={question}
                          placeholder={turns.length ? 'Ask a follow-up question…' : 'What would you like to understand?'}
                          onChange={(e) => setQuestion(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void ask() }
                          }} />
                <Button kind="primary" icon="send" type="submit"
                        disabled={!ready || awaiting || asking || busy || !question.trim()}>
                  {asking ? 'Asking…' : 'Send'}
                </Button>
              </form>
              {busy && !asking && (
                <p className="ask-busy">Another task is running. You can send your question when it finishes.</p>
              )}
            </Card>
          </div>

          <div className="stack">
            <Card title="Sources used" sub="Excerpts from your connected sources. All read-only.">
              {latest ? <Sources answer={latest} mode={mode} />
                      : <Empty title="Ask something to see the excerpts behind the answer." />}
            </Card>
            {latest && (
              <Card>
                <p className="src-foot">
                  Checked against the repository at {latest.repo?.startsWith('local:') ? 'snapshot' : 'commit'}{' '}
                  <span className="mono">{latest.commit?.slice(0, 7)}</span>{' '}
                  at {new Date(latest.access_checked_at).toLocaleTimeString()}.
                </p>
                <p className="src-foot src-foot-dim">{latest.citation_check}</p>
              </Card>
            )}
          </div>
        </div>
      )}
    </>
  )
}
