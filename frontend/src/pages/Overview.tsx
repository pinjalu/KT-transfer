import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Chip, Empty, Failed, Loading, Missing, NoProject, PageHead, Segmented } from '../components/ui'
import { Statements } from '../components/Statements'
import { Icon } from '../components/Icon'
import { useApi } from '../lib/useApi'
import { useOverview } from '../lib/useOverview'
import { ApiError, post } from '../lib/api'
import type { FactGroup, Overview as Body, Section } from '../lib/overview'
import type { Status } from '../lib/types'
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
  const status = useApi<Status>('/api/status', 5000)
  const reply = useOverview(status)
  const features = useApi<FeatureReply>('/api/features', 0, status.data?.knowledge_revision,
    !!status.data && !status.data.awaiting_project)
  const [note, setNote] = useState('')
  const [blocked, setBlocked] = useState(false)
  const busy = status.data?.busy ?? false

  // What the application is actually doing, in its own words. "Reading the files" was printed
  // for the whole of a scan, including the minutes after every file had been read while the
  // text was being turned into vectors, which on a machine with no GPU is most of the wait.
  const scan = status.data?.scan ?? null
  const phase = scan?.phase && scan.status === 'running' ? scan.phase : ''
  const embedded = scan?.embed_total
    ? ` ${scan.embed_done ?? 0} of ${scan.embed_total}`
    : ''
  const doing = phase ? phase + embedded + '…' : 'Reading…'

  // A refusal because something else was running described the moment it was clicked, not a
  // state of the project, and it stayed on screen long after the scan it referred to had
  // finished. Reading "another scan or answer is in progress" above an empty overview, with
  // nothing in fact running, says the screen is broken when one more click would have worked.
  useEffect(() => {
    if (blocked && !busy) {
      setNote('')
      setBlocked(false)
    }
  }, [blocked, busy])

  const build = async () => {
    setNote('')
    setBlocked(false)
    try {
      await post('/api/overview')
      setNote('Overview build requested. Sections appear as each one finishes.')
      status.reload()
    } catch (exc) {
      const why = exc instanceof ApiError ? exc.message : 'Could not start the build.'
      setNote(why)
      setBlocked(exc instanceof ApiError && exc.status === 409)
    }
  }

  if (status.data?.awaiting_project) {
    return <><PageHead title="Project overview" /><NoProject what="the overview" /></>
  }
  if (status.error) return <Failed message={status.error} onRetry={status.reload} />
  if (reply.loading) return <>
    <PageHead title="Project overview" />
    <Loading what="the overview"
      message={status.loading ? 'Checking overview status…'
        : status.data?.overview_building ? 'Loading build progress…' : 'Loading saved overview…'}
      detail={status.loading ? 'Getting the current project and build status.'
        : status.data?.overview_building
        ? 'Your existing build is continuing. Checking source access before showing completed sections.'
        : 'Checking access to your connected sources. A page refresh loads saved content.'} />
  </>
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
            {/* Disabled while anything else is reading, because the request would be
                refused anyway and a refusal is a worse answer than a button that waits. */}
            <Button icon="refresh" onClick={build} disabled={building || busy}>
              {building ? 'Building…' : busy ? doing : body ? 'Rebuild overview' : 'Build overview'}
            </Button>
            <Segmented items={[...MODES]} active={mode} onPick={(m) => setMode(m as Mode)} />
          </>
        } />

      {note && <p className="ov-note">{note}</p>}
      <p className="ov-note">Rebuild overview generates it again from saved information. To get source changes,
        use <Link to="/connections">Connections</Link> first. Source refreshes clear previous answers and the overview.</p>

      {/* A scan running elsewhere is why every button here is disabled, so this screen says
          so rather than leaving a reader to guess at an inert page. */}
      {busy && !building && (
        <Card>
          <div className="loading">
            <span className="spinner" aria-hidden="true" />
            {phase || 'Reading'}
            {scan?.embed_total
              ? `. ${scan.embed_done ?? 0} of ${scan.embed_total} pieces of text done.`
              : scan?.total
              ? `. ${scan.processed ?? 0} of ${scan.total} files done.`
              : '.'}
            {' '}The overview is built from this, so it can start once this finishes.
          </div>
        </Card>
      )}

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
          {/* The backend's reason for having no overview is the same sentence as the title,
              so printing both said it twice. Only a reason that adds something is shown. */}
          <Empty title="No overview has been built for the current information yet."
                 detail={reply.data?.reason && !reply.data.reason.startsWith('No overview has been built')
                   ? reply.data.reason
                   : 'Build one to read a handover of this project, in the order it is worth reading.'}
                 action={<Button kind="primary" icon="refresh" onClick={build} disabled={busy}>
                           {busy ? doing : 'Build overview'}
                         </Button>} />
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
              {features.error && <Failed message={features.error} onRetry={features.reload} />}
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
              ) : !features.loading && !features.error ? (
                <Empty title="No features were derived."
                       detail={features.data?.unclustered?.note
                               || 'A feature starts at a route. This project declares none that cluster.'} />
              ) : null}
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
