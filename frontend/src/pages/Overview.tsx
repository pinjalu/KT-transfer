import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Empty, Failed, Loading, NoProject, PageHead, Segmented } from '../components/ui'
import { OverviewDashboard } from '../components/OverviewDashboard'
import type { FeatureReply, OverviewMode } from '../components/OverviewDashboard'
import { useApi } from '../lib/useApi'
import { useOverview } from '../lib/useOverview'
import { ApiError, post } from '../lib/api'
import type { Overview as Body } from '../lib/overview'
import type { Status } from '../lib/types'
import './overview.css'
const MODES = ['Beginner', 'Developer', 'Architect'] as const
export function Overview() {
  const [mode, setMode] = useState<OverviewMode>('Beginner')
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
  return (
    <div className="ov-page">
      <PageHead
        title="Project overview"
        lead="Get oriented, then explore what matters to you."
        actions={
          <>
            {/* Disabled while anything else is reading, because the request would be
                refused anyway and a refusal is a worse answer than a button that waits. */}
            <Button icon="refresh" onClick={build} disabled={building || busy}>
              {building ? 'Building…' : busy ? doing : body ? 'Rebuild overview' : 'Build overview'}
            </Button>
          </>
        } />

      {note && <p className="ov-note">{note}</p>}

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

      {body && <>
        <div className="ov-view-bar">
          <div><span className="ov-eyebrow">Choose your level of detail</span>
            <p>Every view uses the same saved evidence.</p></div>
          <Segmented items={[...MODES]} active={mode} onPick={m => setMode(m as OverviewMode)} />
        </div>
        <OverviewDashboard key={`${body.repo}:${body.scan_id}:${status.data?.knowledge_revision}`}
          body={body} features={features} mode={mode} building={building} />
      </>}
      <details className="ov-refresh-help">
        <summary>How refreshing works</summary>
        <p>A page refresh loads the saved overview. Rebuild overview generates it again from saved information.
          To get source changes, use <Link to="/connections">Connections</Link> first.
          Source refreshes clear previous answers and the overview.</p>
      </details>
    </div>
  )
}
