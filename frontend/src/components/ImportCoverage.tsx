import { Chip } from './ui'

export type Coverage = {
  source: 'github' | 'local' | 'jira' | 'slack'
  state: string
  available: boolean
  read_at: string | null
  snapshot_read_at?: string | null
  summary: string
  counts: { label: string; value: number }[]
  notes: string[]
  details: { name: string; summary: string; notes: string[] }[]
  attempt?: { state: string; error: string; started_at: string; finished_at: string | null }
}
export type CoverageReply = { sources: Partial<Record<Coverage['source'], Coverage>> }

const LABELS: Record<string, string> = { complete: 'Read within scope', partial: 'Incomplete read',
  unknown: 'Coverage unknown', not_read: 'Not read', running: 'Reading', failed: 'Failed',
  cancelled: 'Cancelled', interrupted: 'Interrupted' }
const NAMES = { github: 'GitHub', local: 'Local folder', jira: 'Jira', slack: 'Slack' }

export function ImportCoverage({ coverage }: { coverage?: Coverage }) {
  if (!coverage) return null
  const { state, attempt } = coverage
  return <section className="import-coverage" aria-label={`${NAMES[coverage.source]} import coverage`}>
    <div className="coverage-heading">
      <strong>Import coverage</strong>
      <Chip tone={state === 'complete' ? 'ok' : state === 'failed' ? 'bad' : state === 'not_read' ? 'quiet' : 'warn'}>
        {LABELS[state] ?? state}
      </Chip>
      {coverage.read_at && <span>{['github', 'local'].includes(coverage.source) ? 'Last scan finished' : 'Saved read'}: {new Date(coverage.read_at).toLocaleString()}</span>}
    </div>
    <p>{coverage.summary}</p>
    {!coverage.available && coverage.read_at && <p className="coverage-warning">This saved read is unavailable for answers.</p>}
    {attempt && <p className="coverage-warning" role="status">
      Latest attempt: {attempt.state}. {attempt.error || (['github', 'local'].includes(coverage.source)
        ? 'Counts below describe this scan attempt.' : 'The coverage below describes the last saved read.')}
      {!['github', 'local'].includes(coverage.source) && coverage.read_at && ' The previous saved read is shown below.'}
    </p>}
    {coverage.counts.length > 0 && <dl className="coverage-counts">
      {coverage.counts.map(c => <div key={c.label}><dt>{c.label}</dt><dd>{c.value}</dd></div>)}
    </dl>}
    {(coverage.notes.length > 0 || coverage.details.length > 0) && <details>
      <summary>Coverage details and limits</summary>
      <ul>{coverage.notes.map((note, i) => <li key={i}>{note}</li>)}</ul>
      {coverage.details.length > 0 && <ul className="coverage-details">
        {coverage.details.map((detail, i) => <li key={i}>
          <strong>{detail.name}</strong><span>{detail.summary}</span>
          {detail.notes.map((note, j) => <p key={j}>{note}</p>)}
        </li>)}
      </ul>}
    </details>}
  </section>
}
