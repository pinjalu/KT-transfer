import type { FeatureList, FeatureSnapshot } from './features'
import { jobActive } from './jobProgress'
import type { Status } from './types'
import { useApi } from './useApi'
import type { Load } from './useApi'

export function sameFeatureSnapshot(actual: FeatureSnapshot, expected: FeatureSnapshot) {
  return !!expected.repo && expected.scan_id !== undefined && !!expected.commit
    && ['repo', 'branch', 'scan_id', 'commit', 'knowledge_revision'].every(key =>
      actual[key as keyof FeatureSnapshot] === expected[key as keyof FeatureSnapshot])
}

/** Features belong to a particular project and saved read, not just a page URL. */
export function useFeatures(status: Load<Status>, allowed = true): Load<FeatureList> {
  const state = status.data
  const snapshot: FeatureSnapshot = { repo: state?.settings?.repo, branch: state?.settings?.branch,
    scan_id: state?.scan?.id, commit: state?.scan?.commit ?? undefined, knowledge_revision: state?.knowledge_revision }
  const reading = !!state && ((jobActive(state.job) && ['scan', 'local', 'jira', 'slack'].includes(state.job!.kind))
    || state.scan?.status === 'running' || state.jira_reading || state.slack_reading)
  const enabled = allowed && !!state && !state.awaiting_project && state.ready && !reading
  // A new overview build also requests fresh features, including when its project
  // has the same feature names or the browser retained this page from an earlier visit.
  const build = state?.job?.kind === 'overview' ? state.job.id : !!state?.overview_building
  const reply = useApi<FeatureList>('/api/features', 0, JSON.stringify([snapshot, build]), enabled)
  if (reply.data?.available && !sameFeatureSnapshot(reply.data, snapshot)) {
    return { ...reply, data: null, loading: false,
      error: 'These feature results do not match the current project files. Refresh features to load the current project.' }
  }
  if (state && !state.awaiting_project && !state.ready && !reading) {
    return { ...reply, data: { available: false, features: [], reason: 'Read this project’s files to find its features.' }, loading: false }
  }
  return reply
}
