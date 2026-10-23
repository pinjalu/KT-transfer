/** Shapes returned by pka/web.py. Kept here so a screen never guesses at a field name. */

export type Settings = { repo: string; branch: string; platforms: string[]; source_kind?: 'github' | 'local'; local_path?: string; local?: { path: string }; jira?: { project?: string }; slack?: { channels?: unknown[] } } | null

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
  /** Set only while the text is being turned into vectors, so a long wait can show progress. */
  embed_done?: number
  embed_total?: number
  started: string | null
  finished: string | null
  error: string | null
  tree_incomplete: boolean
}

export type Status = {
  job?: BackgroundJob | null
  knowledge_revision: number
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
  /** True until a project is chosen in this run. Nothing on disk has been lost. */
  awaiting_project?: boolean
  /** The project the last run used, offered on Connections as a shortcut rather than
   *  adopted silently. Null when nothing has ever been saved. */
  stored_project?: { repo: string; branch: string; source_kind?: 'github' | 'local'; local_path?: string } | null
}

export type Progress = { phase?: string; read?: number; total?: number; done?: number } | null

export type BackgroundJob = {
  id: number
  kind: 'scan' | 'overview' | 'jira' | 'slack' | 'local' | 'jira_task' | 'decisions'
  target?: string
  state: 'queued' | 'running' | 'cancelling' | 'succeeded' | 'partial' | 'failed' | 'cancelled' | 'interrupted'
  attempt: number
  error: string
  started_at: string
  finished_at: string | null
  can_cancel: boolean
  can_retry: boolean
  progress: { phase?: string; done?: number; processed?: number; total?: number;
              embed_done?: number; embed_total?: number } | null
}

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
