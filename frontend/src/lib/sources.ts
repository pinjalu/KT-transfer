/** Shapes returned by the Slack, Jira and import-history endpoints in pka/web.py. */

export type Channel = { id: string; name: string; chosen?: boolean; private?: boolean }

export type SlackReply = {
  connected: boolean
  channels: Channel[]
  chosen: { id: string; name: string }[]
  workspace: string
  reason: string
  read_at?: string
  blocks?: number
  limits?: { channels: number; messages: number }
}

export type JiraProject = { key: string; name: string }

export type JiraReply = {
  connected: boolean
  projects: JiraProject[]
  chosen: string
  reason: string
  read_at?: string
  blocks?: number
}

export type Run = {
  file: string
  scan_id: number
  status: string
  repo: string
  branch: string
  commit: string
  started: string
  finished: string
  read: string
  skipped: string
  failed: string
  error: string
}

export type History = {
  runs: Run[]
  kept: number
  slack_read_at: string
  jira_read_at: string
  note: string
}

export const RUN_TONE: Record<string, 'ok' | 'warn' | 'bad' | 'quiet'> = {
  complete: 'ok',
  partial: 'warn',
  interrupted: 'warn',
  cancelled: 'quiet',
  failed: 'bad',
}
