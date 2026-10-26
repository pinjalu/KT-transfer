import { useApi } from './useApi'
import type { BackgroundJob } from './types'
import type { CoverageReply } from '../components/ImportCoverage'

export const JOB_NAMES = { scan: 'Repository scan', overview: 'Project overview', jira: 'Jira read', slack: 'Slack read', local: 'Local folder read', jira_task: 'Jira task explanation', decisions: 'Team decision summary', evaluation: 'Answer evaluation' }
export const jobActive = (job?: BackgroundJob | null) => !!job && ['queued', 'running', 'cancelling'].includes(job.state)

export function useJobProgress(job?: BackgroundJob | null) {
  const progress = job?.progress
  // A server already importing a folder cannot be restarted to pick up new stage labels.
  // Its saved coverage proves file reading finished; it does not provide embedding counts.
  const legacyLocal = job?.kind === 'local' && job.state === 'running'
    && !!progress?.phase?.startsWith('Reading ') && !progress.embed_total
    && !!progress.total && (progress.done ?? 0) >= progress.total - 1
  const coverage = useApi<CoverageReply>('/api/import-coverage', 5000, job?.id, legacyLocal)
  const saved = coverage.data?.sources.local
  if (legacyLocal && saved?.available && saved.read_at && job?.started_at
    && saved.attempt?.started_at === job.started_at
    && Date.parse(saved.read_at) >= Date.parse(job.started_at)) {
    return { phase: 'Files imported; preparing search index' }
  }
  return progress
}

export function progressText(progress?: BackgroundJob['progress']) {
  const embedding = !!progress?.embed_total
  const done = embedding ? progress?.embed_done : progress?.done ?? progress?.processed
  const total = embedding ? progress?.embed_total : progress?.total
  return `${progress?.phase || 'Preparing the job'}${total && done !== undefined
    ? ` — ${done} of ${total}${embedding ? ' text sections' : ''}` : ''}`
}
