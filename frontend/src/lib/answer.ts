/** The shape pka/service.py returns from POST /api/ask. */

export type Source = {
  source_id: string
  path: string
  start: number
  end: number
  text: string
  url: string | null
}

/** Set by pka/overview.py tidy(). 'check this' means the excerpt it cites does not carry it. */
export type Support = 'supported' | 'partly supported' | 'check this' | 'not measured'

export type Statement = {
  text: string
  source_ids: string[]
  support: Support
  support_share: number | null
  about_this_project: boolean
  /** File names the sentence used that this scan never read. */
  files_not_read?: string[]
}

export type Search = {
  asked?: string[]
  terms?: string[]
  unknown?: string[]
  corrections?: Record<string, string>
}

export type Answer = {
  answer_id: number
  statements: Statement[]
  sources: Source[]
  missing_information: string
  error: string | null
  warning: string
  search: Search
  commit: string
  repo: string
  scanned_at: string | null
  access_checked_at: string
  elapsed_seconds: number
  citation_check: string
  checks?: { dropped_repeats: number; narrowed_citations: number; unsupported: number; generic: number }
}

export type Turn = {
  question: string
  asked_at: string
  answer: Answer | null
  failed: string | null
  rating?: string
  sufficiency?: string
}

/** Where an excerpt came from. Slack and Jira blocks are stored under their own path prefix. */
export function originOf(path: string, url?: string | null): 'Slack' | 'Jira' | 'GitHub' | 'Local folder' {
  if (path.startsWith('local://') || url?.startsWith('/source?')) return 'Local folder'
  if (path.startsWith('slack/')) return 'Slack'
  if (path.startsWith('jira/')) return 'Jira'
  return 'GitHub'
}

export function sourcePath(path: string): string {
  return path.startsWith('local://') ? 'Local folder / ' + path.split('/').slice(3).join('/') : path
}

export const SUPPORT_TONE: Record<Support, 'ok' | 'warn' | 'bad' | 'quiet'> = {
  supported: 'ok',
  'partly supported': 'warn',
  'check this': 'bad',
  'not measured': 'quiet',
}

export const SUPPORT_SAYS: Record<Support, string> = {
  supported: 'The excerpt it cites carries this.',
  'partly supported': 'Only part of this is in the excerpt it cites.',
  'check this': 'This was not found in the excerpt it cites. Read the excerpt before believing it.',
  'not measured': 'Not checked against an excerpt.',
}
