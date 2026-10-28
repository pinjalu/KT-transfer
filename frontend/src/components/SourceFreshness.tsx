import { Card, Chip } from './ui'
import type { CoverageReply } from './ImportCoverage'

const NAMES = { github: 'GitHub', local: 'Local folder', zip: 'ZIP file', jira: 'Jira', slack: 'Slack' }

export function SourceFreshness({ coverage, warning }: { coverage?: CoverageReply; warning?: string }) {
  const sources = Object.values(coverage?.sources ?? {})
  if (!sources.length) return null
  return <Card title="Knowledge refresh" sub="Saved information available to answers, by source.">
    {warning && <p role="status" className="coverage-warning">{warning}</p>}
    <dl className="source-freshness">{sources.map(source => {
      const stamp = source.available ? source.snapshot_read_at : null
      const valid = stamp && Number.isFinite(Date.parse(stamp))
      return <div key={source.source}>
        <dt>{NAMES[source.source]}</dt>
        <dd><Chip tone={source.available ? 'ok' : 'quiet'}>{source.available ? 'Saved snapshot' : 'Needs reading'}</Chip>
          <span>{valid ? <>Read on <time dateTime={stamp}>{new Date(stamp).toLocaleString()}</time></>
            : source.available ? 'Read time was not recorded' : 'No snapshot available to answers'}</span>
          {source.state === 'partial' && <span className="coverage-warning">Incomplete read: check coverage below.</span>}
          {source.attempt && <span className="coverage-warning">Latest attempt: {source.attempt.state}.
            {source.available && ' Answers still use the earlier saved snapshot.'}</span>}
        </dd>
      </div>
    })}</dl>
    <p className="conn-local-note">These are import times. Source access and saved content are checked when you use them.
      Refresh each source after changes, then rebuild the project overview. Automatic scheduled refresh is not enabled.</p>
  </Card>
}
