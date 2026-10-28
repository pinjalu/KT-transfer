import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Empty, Failed, Loading, NoProject, PageHead, Segmented } from '../components/ui'
import { OverviewDashboard } from '../components/OverviewDashboard'
import type { OverviewMode } from '../components/OverviewDashboard'
import { useFeatures } from '../lib/useFeatures'
import { useOverview } from '../lib/useOverview'
import { projectName } from '../lib/project'
import { ApiError, post } from '../lib/api'
import { JOB_NAMES, jobActive, progressText, useJobProgress } from '../lib/jobProgress'
import type { Overview as Body } from '../lib/overview'
import { useStatus } from '../lib/useStatus'
import './overview.css'
const MODES = ['Beginner', 'Developer', 'Architect'] as const
export function Overview() {
  const [mode, setMode] = useState<OverviewMode>('Beginner')
  const status = useStatus()
  const reply = useOverview(status)
  const localSelection = status.data?.settings?.selected_source === 'local'
    && !status.data?.settings?.repo?.startsWith('local:')
  const features = useFeatures(status, !localSelection)
  const [note, setNote] = useState('')
  const [blocked, setBlocked] = useState(false)
  const busy = status.data?.busy ?? false

  // The last repository scan is historical. Only the active job describes today's wait.
  const job = jobActive(status.data?.job) ? status.data?.job : null
  const jobProgress = useJobProgress(job)
  const waiting = job?.kind === 'local' ? 'Waiting for local import…' : 'Waiting for current job…'

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
        lead="See the problem, the solution and one simple journey through the project."
        actions={
          <>
            {/* Disabled while anything else is reading, because the request would be
                refused anyway and a refusal is a worse answer than a button that waits. */}
            <Button icon="refresh" onClick={build} disabled={building || busy}>
              {building ? 'Building…' : busy ? waiting : body ? 'Rebuild overview' : 'Build overview'}
            </Button>
          </>
        } />

      {note && <p className="ov-note">{note}</p>}

      {/* A scan running elsewhere is why every button here is disabled, so this screen says
          so rather than leaving a reader to guess at an inert page. */}
      {busy && !building && (
        <Card>
          <div className="loading" role="status">
            <span className="spinner" aria-hidden="true" />
            <div><p>{job?.state === 'cancelling' ? 'Cancellation requested. Waiting for the current operation to stop.'
              : job ? `${JOB_NAMES[job.kind]}: ${progressText(jobProgress)}.` : 'Another operation is running.'}</p>
              <p className="loading-detail">The overview is not building. When this job finishes, select Build overview to generate it from the saved sources.</p></div>
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
          {reply.data?.progress?.topics && <ul>{Object.entries(reply.data.progress.topics).map(([key,topic])=><li key={key}>{topic.title}: {topic.state}</li>)}</ul>}
        </Card>
      )}

      {!body && !building && !busy && (
        <Card>
          {/* The backend's reason for having no overview is the same sentence as the title,
              so printing both said it twice. Only a reason that adds something is shown. */}
          <Empty title="No overview has been built for the current information yet."
                 detail={reply.data?.reason && !reply.data.reason.startsWith('No overview has been built')
                   ? reply.data.reason
                   : 'Build one to read a handover of this project, in the order it is worth reading.'}
                 action={<Button kind="primary" icon="refresh" onClick={build} disabled={busy}>
                           Build overview
                         </Button>} />
        </Card>
      )}

      {body && <>
        {body.scope_update_available && <p role="status">Showing only {body.project_name}, your selected local folder. Build its overview to generate explanations from these files.</p>}
        {body.plain_language_update_available && !building && <Card>
          <p role="status"><strong>Your saved explanation needs an update.</strong> Rebuild it to show source-linked graphs, an ER diagram where data relationships are declared, and every discovered main feature in Step by step. Source references will use names instead of numbers. Connected systems remain separate.</p>
          <Button kind="primary" icon="refresh" disabled={busy} onClick={build}>Update saved explanation</Button>
        </Card>}
        {body.routing_changed && <p role="status">AI routing or explanation settings changed since this overview was saved. Rebuild to apply the latest settings.</p>}
        {body.partial && <p role="status">Partial coverage: {body.successful_topics ?? body.topics_done} topics completed; {body.failed_topics ?? 0} failed. Review each topic's missing information. Rebuilding reuses saved topics and retries failures.</p>}
        {!!body.failed_topics&&<Button icon="refresh" disabled={building||busy} onClick={build}>Retry failed topics</Button>}
        <div className="ov-view-bar">
          <div><span className="ov-eyebrow">Choose your level of detail</span>
            <p>Start with the story. Open a deeper view when you want more detail.</p></div>
          <Segmented items={[...MODES]} active={mode} onPick={m => setMode(m as OverviewMode)} />
        </div>
        <OverviewDashboard key={`${body.repo}:${body.scan_id}:${status.data?.knowledge_revision}`}
          body={body} features={body.overview_features ? { data: body.overview_features, loading: false, error: null, reload: reply.reload } : features} mode={mode} building={building}
          project={body.project_name || projectName(status.data?.settings, body.repo)} />
      </>}
      <details className="ov-refresh-help">
        <summary>How refreshing works</summary>
        <p>Switching pages keeps your overview and reading position. Rebuild overview reuses validated topics for the same sources and routing configuration and retries failed topics.
          To get source changes, use <Link to="/connections">Connections</Link> first.
          Source refreshes clear the saved overview. Earlier chat replies remain visible and are marked as older.</p>
      </details>
    </div>
  )
}
