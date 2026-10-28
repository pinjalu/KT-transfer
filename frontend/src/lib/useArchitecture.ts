import { useCallback, useState } from 'react'
import type { DiagramPayload } from '../components/Diagram'
import type { FactGroup } from './overview'
import { jobActive } from './jobProgress'
import type { Status } from './types'
import { useApi } from './useApi'
import type { Load } from './useApi'

export type ArchitectureSystem = { id: string; name: string; diagrams: DiagramPayload[]; facts: FactGroup[]; roles: { cards?: unknown[] } }
export type ArchitectureBody = { repo: string; branch: string; scan_id: number; commit: string; knowledge_revision: number; systems: ArchitectureSystem[] }
type Reply = { available: boolean; architecture: ArchitectureBody | null; reason: string }

export function useArchitecture(status: Load<Status>): Load<Reply> {
  const [refresh, setRefresh] = useState(0)
  const reload = useCallback(() => setRefresh(value => value + 1), [])
  const state = status.data
  const snapshot = { repo: state?.settings?.repo, branch: state?.settings?.branch,
    scan_id: state?.scan?.id, commit: state?.scan?.commit, knowledge_revision: state?.knowledge_revision }
  const reading = !!state && ((jobActive(state.job) && ['scan', 'local', 'jira', 'slack'].includes(state.job!.kind))
    || state.scan?.status === 'running' || state.jira_reading || state.slack_reading)
  const enabled = !!state && !state.awaiting_project && state.ready && !reading
  // A manual refresh gets a new key, immediately hiding the old diagrams and preventing
  // a late response for the prior read/project from replacing the fresh result.
  const reply = useApi<Reply>('/api/architecture', 0, JSON.stringify([snapshot, refresh]), enabled)
  const actual = reply.data?.architecture
  if (actual && Object.keys(snapshot).some(key => actual[key as keyof typeof snapshot] !== snapshot[key as keyof typeof snapshot])) {
    return { ...reply, reload, data: null, loading: false, error: 'These diagrams do not match the current project files. Refresh architecture.' }
  }
  if (state && !state.awaiting_project && !state.ready && !reading) {
    return { ...reply, reload, data: { available: false, architecture: null, reason: 'Read this project’s files to build its architecture.' }, loading: false }
  }
  return { ...reply, reload }
}
