/** The shape pka/service.py returns from POST /api/ask. */

export type Source = {
  system_id?: string
  system_name?: string
  source_id: string
  path: string
  start: number
  end: number
  text: string
  url: string | null
}

/** Lexical overlap from pka/overview.py tidy(); not a factual correctness verdict. */
export type Support = 'supported' | 'partly supported' | 'check this' | 'not measured'
export type EvidenceKind = 'verified_code' | 'suggestion' | 'code' | 'test' | 'documentation' | 'discussion' | 'mixed' | 'unverified' | 'example'

export const EVIDENCE_LABELS: Record<EvidenceKind, string> = {
  verified_code: 'Verified from code', suggestion: 'Suggested behaviour', code: 'Code-based explanation',
  test: 'Test definition, not a test result', documentation: 'Documentation or configuration',
  discussion: 'Recorded requirement or discussion', mixed: 'Mixed evidence — needs verification',
  unverified: 'Behaviour not verified', example: 'Example data',
}

export type Statement = {
  text: string
  source_ids: string[]
  function_refs?: { name: string; path: string; line: number; url: string }[]
  support: Support
  support_share: number | null
  about_this_project: boolean
  /** File names the sentence used that this scan never read. */
  files_not_read?: string[]
  /** Evidence provenance is separate from lexical overlap and never model self-attestation. */
  evidence?: { kind: EvidenceKind; reason: string }
}

export type Search = {
  asked?: string[]
  terms?: string[]
  unknown?: string[]
  corrections?: Record<string, string>
}

export type TestSuggestion = {
  title: string
  reason: string
  setup: string[]
  steps: string[]
  expected_result: string
  verification: string[]
  assumptions: string[]
  evidence: { source_id: string; quote: string; kind: string }[]
  status: 'suggested_not_run'
}

export type Answer = {
  generation?: import('./ai').Generation
  knowledge_revision?: number
  answer_id: number
  statements: Statement[]
  test_suggestions?: TestSuggestion[]
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
  /** The source version used when asking; older replies remain part of the conversation. */
  knowledge_revision?: number
  rating?: string
  sufficiency?: string
}

/** Send only this browser session's recent replies from the current source revision. */
export function conversationContext(turns: Turn[], repo: string | undefined, revision: number | undefined) {
  const eligible = turns.filter(t => t.answer && !t.answer.error && !t.failed
    && t.rating !== 'incorrect' && t.answer.repo === repo
    && (t.answer.knowledge_revision ?? t.knowledge_revision) === revision)
  const latest = eligible.at(-1)?.answer
  if (!latest?.commit || revision === undefined) return undefined
  const recent = eligible.filter(t => t.answer!.commit === latest.commit).slice(-4)
  return { repo: latest.repo, commit: latest.commit, knowledge_revision: revision,
    turns: recent.map(t => ({ question: t.question,
      answer: [...t.answer!.statements.map(s => s.text),
        ...(t.answer!.test_suggestions ?? []).map(s => `Suggested test, not run: ${s.title}. Steps: ${s.steps.join(' ')} Verification: ${s.verification.join(' ')}`),
        t.answer!.missing_information].filter(Boolean).join('\n').slice(0, 1800) })) }
}

/** Where an excerpt came from. Slack and Jira blocks are stored under their own path prefix. */
export function originOf(path: string, url?: string | null): 'Slack' | 'Jira' | 'GitHub' | 'Local folder' | 'ZIP file' {
  if (url?.startsWith('/source?') && new URLSearchParams(url.split('?')[1].split('#')[0]).get('source') === 'zip') return 'ZIP file'
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
  supported: 'High word overlap with the citation; this is not a factual correctness check.',
  'partly supported': 'Some words match the citation. Check the claim and its conditions in the source.',
  'check this': 'Low word overlap with the citation. Inspect the source before relying on this claim.',
  'not measured': 'Not checked against an excerpt.',
}

export const SUPPORT_LABELS: Record<Support, string> = {
  supported: 'High text overlap', 'partly supported': 'Some text overlap',
  'check this': 'Low text overlap', 'not measured': 'Not measured',
}
