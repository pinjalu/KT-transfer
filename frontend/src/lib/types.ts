/** Shapes returned by pka/web.py. Kept here so a screen never guesses at a field name. */

export type Settings = { repo: string; branch: string; platforms: string[] } | null

export type Scan = {
  id?: number
  status: 'running' | 'complete' | 'partial' | 'failed' | 'cancelled'
  repo: string
  branch: string
  commit: string | null
  read: number
  skipped: number
  failed: number
  total: number
  processed: number
  phase: string
  started: string | null
  finished: string | null
  error: string | null
  tree_incomplete: boolean
}

export type Status = {
  settings: Settings
  scan: Scan | null
  last_successful_scan: Scan | null
  busy: boolean
  demo: boolean
  model: string
  token_configured: boolean
  warning: string
  ready: boolean
  job_error: string
  job_name: string
  jira_reading: boolean
  jira_progress: Progress | null
  slack_reading: boolean
  slack_progress: Progress | null
  overview_building: boolean
  overview_progress: Progress | null
  limits: Record<string, number>
}

export type Progress = { phase?: string; read?: number; total?: number; done?: number } | null

export type Platform = {
  key: string
  name: string
  reads: string
  ready: boolean
  pending: string
  scope: string
  oauth?: unknown
  redirect_uri?: string
}

export type Platforms = {
  platforms: Platform[]
  credentials: Record<string, boolean | string>
  note: string
}
