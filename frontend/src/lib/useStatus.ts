import { createContext, useContext } from 'react'
import { useApi } from './useApi'
import type { Load } from './useApi'
import type { Status } from './types'

export const ProjectStatus = createContext<Load<Status> | null>(null)

/** The shell owns one lightweight status poll for every visited page. */
export function useStatus(poll = 5000) {
  const shared = useContext(ProjectStatus)
  const local = useApi<Status>('/api/status', poll, undefined, !shared)
  return shared ?? local
}
