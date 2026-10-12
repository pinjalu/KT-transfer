import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Chip, Empty, Failed, Loading, Missing, PageHead, Segmented } from '../components/ui'
import { Statements } from '../components/Statements'
import { Icon } from '../components/Icon'
import { useApi } from '../lib/useApi'
import { ApiError, post } from '../lib/api'
import type { FactGroup, Overview as Body, OverviewReply, Section } from '../lib/overview'
import { factsOf, sectionOf } from '../lib/overview'
import './overview.css'

const MODES = ['Beginner', 'Developer', 'Architect'] as const
type Mode = (typeof MODES)[number]

/** Mirrors MODE_SHOWS in the original interface: who sees how much, never a different answer. */
const SHOWS: Record<Mode, { citations: boolean; statements: number; factKeys: string[] | null }> = {
  Beginner: { citations: false, statements: 3,
              factKeys: ['shape', 'documents', 'commands', 'routes', 'services', 'stores', 'gaps'] },
  Developer: { citations: true, statements: 8, factKeys: null },
  Architect: { citations: true, statements: 2,
               factKeys: ['shape', 'routes', 'services', 'stores', 'environment', 'delivery',
                          'dependencies', 'gaps'] },
}

type FeatureRow = { id: string; name: string; route_count: number; file_count: number; gap_count: number }
type FeatureReply = { available: boolean; features: FeatureRow[]; unclustered: { note: string } }

/**
 * Why a section has no prose.
 *
 * A section that failed and a section that found no evidence are different things, and showing
 * the second when the first happened blames the project for something that is not its fault.
 * With Ollama not running, "What does this project do?" read "Nothing in the scanned files
 * states what this project is for", with the real reason demoted to a Checked line underneath.
 */
function TopicGap({ section, fallback, checked }:
  { section?: Section | null; fallback: string; checked?: string }) {
  if (section?.error) {
    return <Failed message={`This section could not be written. ${section.error}`} />
  }
  return <Missing what={section?.missing_information || fallback} checked={checked} />
}

function Facts({ group }: { group: FactGroup }) {
  return (
    <div className="fg">
      <h3>{group.title}</h3>
      <p className="fg-plain">{group.plain}</p>
      <ul className="fg-list">
        {group.items.map((item, i) => (
          <li key={i}>
            <span className="fg-text">{item.text}</span>
            {item.detail && <span className="fg-detail">{item.detail}</span>}
            {item.url
              ? <a className="fg-at mono" href={item.url} target="_blank" rel="noreferrer">
                  {item.path}:{item.line}<Icon name="external" size={11} />
                </a>
              : item.path && <span className="fg-at mono">{item.path}:{item.line}</span>}
          </li>
        ))}
      </ul>
      {group.truncated > 0 && <p className="fg-more">{group.truncated} more not shown.</p>}
      {group.note && <p className="fg-note">{group.note}</p>}
    </div>
  )
}

export function Overview() {
  const [mode, setMode] = useState<Mode>('Beginner')
  const reply = useApi<OverviewReply>('/api/overview', 4000)
  const features = useApi<FeatureReply>('/api/features')
  const [note, setNote] = useState('')

  const build = async () => {
    setNote('')
    try {
      await post('/api/overview')
      setNote('Building. Sections appear as each one finishes.')
      reply.reload()
    } catch (exc) {
      setNote(exc instanceof ApiError ? exc.message : 'Could not start the build.')
    }
  }

  if (reply.loading) return <Loading what="the overview" />
  if (reply.error) return <Failed message={reply.error} onRetry={reply.reload} />

  const body: Body | null = reply.data?.overview ?? null
  const building = reply.data?.building ?? false
  const shows = SHOWS[mode]
  const project = body?.repo?.split('/').pop() ?? 'this project'

  const purpose = body && sectionOf(body, 'purpose')
  const setup = body && sectionOf(body, 'setup')
  const deps = body && factsOf(body, 'dependencies')
  const commands = body && factsOf(body, 'commands')
  const gaps = body && factsOf(body, 'gaps')

  const otherFacts = (body?.facts ?? []).filter(
    (g) => !['dependencies', 'commands', 'gaps'].includes(g.key)
             && (shows.factKeys === null || shows.factKeys.includes(g.key)))

  return (
    <>
      <PageHead
        title="Project overview"
        lead={body ? `Everything below was read from ${body.repo} at commit ${body.commit?.slice(0, 7)}.` : undefined}
        actions={
          <>
            <Button icon="refresh" onClick={build} disabled={building}>
              {building ? 'Building…' : body ? 'Refresh overview' : 'Build overview'}
            </Button>
            <Segmented items={[...MODES]} active={mode} onPick={(m) => setMode(m as Mode)} />
          </>
        } />

      {note && <p className="ov-note">{note}</p>}

      {building && (
        <Card>
          <div className="loading">
            <span className="spinner" aria-hidden="true" />
            Explaining each topic separately. {reply.data?.progress?.done ?? 0} of{' '}
            {reply.data?.progress?.total ?? body?.topics_total ?? '?'} done. Finished sections are
            readable below while the rest are still being written.
          </div>
        </Card>
      )}

      {!body && !building && (
        <Card>
          <Empty title="No overview has been built for this commit yet."
                 detail={reply.data?.reason || 'Build one to read a handover of the project.'}
                 action={<Button kind="primary" icon="refresh" onClick={build}>Build overview</Button>} />
        </Card>
      )}

      {body && (
        <div className="grid-main ov-grid">
          <div className="stack">
            <Card title={`What does ${project} do?`}>
              {purpose && purpose.statements.length > 0 ? (
                <Statements statements={purpose.statements} sources={purpose.sources}
                            citations={shows.citations} limit={shows.statements} />
              ) : (
                <TopicGap section={purpose}
                          fallback="Nothing in the scanned files states what this project is for."
                          checked="The excerpts retrieved for this topic" />
              )}
            </Card>

            {/* Mockup 03 has a filled "Who uses it?" panel. Nothing derives it, and guessing a
                user from a file name is exactly what this product refuses to do. */}
            <Card title="Who uses it?">
              <Missing
                what="Who uses this project is not derived from anything."
                checked="Users are only knowable from a readme, a ticket or a discussion that names them. Deriving them from code would be a guess, so none is offered." />
            </Card>

            <Card title="Main features"
                  sub="Grouped from routes, the files they reach and the tickets that named them."
                  aside={<Link className="btn btn-ghost" to="/features">Open feature explorer</Link>}>
              {features.loading && <Loading what="features" />}
              {features.data?.features?.length ? (
                <ul className="feat-grid">
                  {features.data.features.map((f) => (
                    <li key={f.id}>
                      <Link className="feat" to="/features">
                        <span className="feat-name">{f.name}</span>
                        <span className="feat-meta">
                          {f.route_count} route{f.route_count === 1 ? '' : 's'}, {f.file_count} files
                        </span>
                        {f.gap_count > 0 && <Chip tone="warn">{f.gap_count} gap{f.gap_count === 1 ? '' : 's'}</Chip>}
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty title="No features were derived."
                       detail={features.data?.unclustered?.note
                               || 'A feature starts at a route. This project declares none that cluster.'} />
              )}
            </Card>

            {deps && (
              <Card title="What it is built with" sub={deps.plain}>
                <ul className="tech-row">
                  {deps.items.map((d, i) => (
                    <li key={i}>
                      {d.url
                        ? <a className="tech" href={d.url} target="_blank" rel="noreferrer">
                            <b>{d.text}</b><span>{d.detail}</span>
                          </a>
                        : <span className="tech"><b>{d.text}</b><span>{d.detail}</span></span>}
                    </li>
                  ))}
                </ul>
                {deps.truncated > 0 && <p className="fg-more">{deps.truncated} more not shown.</p>}
              </Card>
            )}

            <Card title="Getting started"
                  sub="Collected from the project's own documentation. Nothing here was run.">
              {setup && setup.statements.length > 0 ? (
                <Statements statements={setup.statements} sources={setup.sources}
                            citations={shows.citations} limit={shows.statements} />
              ) : (
                <TopicGap section={setup} fallback="No setup instructions were found."
                          checked="The readme, the documentation folder and the files that declare commands" />
              )}
              {commands && commands.items.length > 0 && (
                <ol className="cmd-list">
                  {commands.items.map((c, i) => (
                    <li key={i}>
                      <code>{c.text}</code>
                      {c.url
                        ? <a className="fg-at mono" href={c.url} target="_blank" rel="noreferrer">
                            {c.path}:{c.line}
                          </a>
                        : <span className="fg-at mono">{c.path}:{c.line}</span>}
                    </li>
                  ))}
                </ol>
              )}
            </Card>

            {body.sections
              .filter((s) => !['purpose', 'setup'].includes(s.key))
              .map((s) => (
                <Card key={s.key} title={s.title}>
                  {s.statements.length > 0 ? (
                    <Statements statements={s.statements} sources={s.sources}
                                citations={shows.citations} limit={shows.statements} />
                  ) : (
                    <TopicGap section={s} fallback="No evidence was found for this topic."
                              checked="The excerpts retrieved for this topic" />
                  )}
                </Card>
              ))}

            {otherFacts.length > 0 && (
              <Card title="Read straight out of the files" sub="No model wrote any of this.">
                <div className="fg-stack">
                  {otherFacts.map((g) => <Facts key={g.key} group={g} />)}
                </div>
              </Card>
            )}
          </div>

          <div className="stack">
            <Card title="Suggested reading order"
                  sub="Derived from the paths that were indexed, not written by a model.">
              {body.reading_order.length ? (
                <ol className="read-list">
                  {body.reading_order.map((r, i) => (
                    <li key={r.path}>
                      <span className="read-n">{i + 1}</span>
                      <span className="read-body">
                        {r.url
                          ? <a className="read-path mono" href={r.url} target="_blank" rel="noreferrer">{r.path}</a>
                          : <span className="read-path mono">{r.path}</span>}
                        <span className="read-why">{r.why}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              ) : <Empty title="Nothing was indexed to order." />}
            </Card>

            {gaps && gaps.items.length > 0 && (
              <Card title={gaps.title} sub={gaps.plain}>
                <ul className="gap-list">
                  {gaps.items.map((g, i) => (
                    <li key={i}>
                      <span className="gap-icon"><Icon name="warn" size={15} /></span>
                      <span>
                        <b>{g.text}</b>
                        {g.detail && <span className="gap-detail">{g.detail}</span>}
                      </span>
                    </li>
                  ))}
                </ul>
                {gaps.note && <p className="fg-note">{gaps.note}</p>}
              </Card>
            )}

            <Card title="What this was built from">
              <p className="scope">{body.scope_note}</p>
              <p className="scope scope-dim">
                {body.files_indexed} files indexed, {body.files_skipped} skipped. Commit{' '}
                <span className="mono">{body.commit?.slice(0, 7)}</span>
                {body.scanned_at && <> , read {new Date(body.scanned_at).toLocaleString()}</>}.
              </p>
              {!body.complete && (
                <p className="scope scope-dim">
                  {body.topics_done} of {body.topics_total} topics finished.
                </p>
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  )
}
