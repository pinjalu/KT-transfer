import { Link } from 'react-router-dom'
import { Card, Chip, Dot, Empty, Failed, Loading, NoProject, PageHead } from '../components/ui'
import { Icon } from '../components/Icon'
import { useApi } from '../lib/useApi'
import type { Platforms, Status } from '../lib/types'
import './home.css'

const LEARN = [
  { to: '/overview', title: 'Project purpose',
    plain: 'What this project does, who it is for and the main goals.' },
  { to: '/features', title: 'How the main features work',
    plain: 'Follow a feature from the first click through to what it stores.' },
  { to: '/overview', title: 'Your first files to read',
    plain: 'A reading order derived from what was actually scanned.' },
]

function sourceState(ready: boolean, pending: string) {
  if (ready) return { tone: 'ok' as const, label: 'Connected' }
  if (pending) return { tone: 'warn' as const, label: pending }
  return { tone: 'quiet' as const, label: 'Not connected' }
}

export function Home() {
  const status = useApi<Status>('/api/status', 4000)
  const platforms = useApi<Platforms>('/api/platforms')

  if (status.loading) return <Loading what="the project" />
  if (status.error) return <Failed message={status.error} onRetry={status.reload} />
  if (status.data?.awaiting_project) {
    return <><PageHead title="KT Assistant" /><NoProject what="everything this project knows" /></>
  }

  const repo = status.data?.settings?.repo ?? ''
  const project = repo ? repo.split('/').pop()! : ''
  const scan = status.data?.last_successful_scan ?? status.data?.scan ?? null
  const rows = platforms.data?.platforms ?? []

  return (
    <>
      <PageHead
        title={project ? `Welcome to ${project}` : 'Welcome'}
        lead="Understand the project, one question at a time." />

      <form className="home-ask" action="/ask">
        <span className="home-ask-icon"><Icon name="chat" /></span>
        <input className="home-ask-input" name="q" placeholder="What would you like to understand?" />
        <Link className="btn btn-primary" to="/ask"><Icon name="send" size={16} /> Ask assistant</Link>
      </form>

      <div className="grid-main home-grid">
        <div className="stack">
          <Card title="Start learning" sub={project ? `Get up to speed with the key parts of ${project}.` : 'Connect a source to begin.'}>
            <ol className="learn-list">
              {LEARN.map((item, i) => (
                <li key={item.title}>
                  <Link className="learn-row" to={item.to}>
                    <span className="learn-n">{i + 1}</span>
                    <span className="learn-text">
                      <span className="learn-title">{item.title}</span>
                      <span className="learn-plain">{item.plain}</span>
                    </span>
                    <span className="learn-arrow"><Icon name="chevron" size={16} /></span>
                  </Link>
                </li>
              ))}
            </ol>
          </Card>

          <Card title="Explore key features"
                sub="Look at how important parts of the project are implemented.">
            {/* Deliberately empty until step 5 derives features. Inventing three plausible
                feature names here would be exactly the thing this product is built not to do. */}
            <Empty
              title="No features have been derived yet."
              detail="Features are grouped from routes, the files they reach, the tables they touch and the tickets that asked for them. That derivation is step 5 and is not built."
              action={<Link className="btn btn-secondary" to="/features">See what this will hold</Link>} />
          </Card>
        </div>

        <div className="stack">
          <Card title="Your project sources" sub="These connections are read-only."
                aside={<Link className="btn btn-ghost" to="/connections">View connections</Link>}>
            {platforms.loading && <Loading what="connections" />}
            {platforms.error && <Failed message={platforms.error} onRetry={platforms.reload} />}
            {rows.length > 0 && (
              <ul className="source-list">
                {rows.map((p) => {
                  const s = sourceState(p.ready, p.pending)
                  return (
                    <li key={p.key} className="source-row">
                      <div className="source-id">
                        <span className="source-name">{p.name}</span>
                        <span className="source-scope">{p.scope || p.reads}</span>
                      </div>
                      <Chip tone={s.tone}><Dot tone={s.tone} />{s.label}</Chip>
                    </li>
                  )
                })}
              </ul>
            )}
            {!platforms.loading && !platforms.error && rows.length === 0 && (
              <Empty title="No sources are selected yet."
                     action={<Link className="btn btn-primary" to="/connections">Connect a source</Link>} />
            )}
          </Card>

          <Card title="Recent project changes"
                sub="Stay up to date with what has changed across your sources.">
            {/* Mockup 01 shows a change feed. Nothing records change yet: scans replace rather
                than compare. Step 11 builds that, and this says so instead of faking it. */}
            {scan?.commit ? (
              <ul className="change-list">
                <li className="change-row">
                  <span className="change-icon"><Icon name="clock" size={16} /></span>
                  <div>
                    <p className="change-title">Last read at commit <code>{scan.commit.slice(0, 7)}</code></p>
                    <p className="change-plain">
                      {scan.read} files read, {scan.skipped} skipped, {scan.failed} failed.
                    </p>
                  </div>
                </li>
              </ul>
            ) : (
              <Empty title="Nothing has been read yet."
                     detail="Run a scan from Connections to fill this." />
            )}
            <p className="change-note">
              A change feed needs a comparison between two reads. Scans currently replace rather
              than compare, so only the latest read is shown. Step 11 adds the comparison.
            </p>
          </Card>
        </div>
      </div>
    </>
  )
}
