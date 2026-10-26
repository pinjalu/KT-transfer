import { useEffect, useRef } from 'react'
import { useApi } from './useApi'
import type { Load } from './useApi'
import type { OverviewReply } from './overview'
import type { Status } from './types'

export function useOverview(status: Load<Status>) {
  const enabled = !!status.data && !status.data.awaiting_project
  // Saved content stays in the page until an explicit update or a build changes it.
  const reply = useApi<OverviewReply>('/api/overview', status.data?.overview_building ? 4000 : 0,
    status.data?.knowledge_revision, enabled)
  const job = status.data?.job
  const change = job?.kind === 'overview' ? `${job.id}:${job.state}` : ''
  const previous = useRef<string | undefined>(undefined)
  useEffect(() => {
    if (!enabled) { previous.current = undefined; return }
    if (previous.current !== undefined && previous.current !== change) reply.reload()
    previous.current = change
  }, [change, enabled, reply.reload])
  return reply
}
