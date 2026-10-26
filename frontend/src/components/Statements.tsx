import { Chip } from './ui'
import type { Source, Statement } from '../lib/answer'
import { EVIDENCE_LABELS, SUPPORT_LABELS, SUPPORT_SAYS, SUPPORT_TONE } from '../lib/answer'

/**
 * How a model-written sentence is shown anywhere in this interface.
 *
 * Provenance, word overlap and project specificity are separate signals. None of the
 * model-written prose is verified merely because its citation has matching words.
 * Keep the evidence label visible in every reader mode, including saved legacy answers.
 */
export function Cites({ ids, sources }: { ids: string[]; sources: Source[] }) {
  const order = new Map(sources.map((s, i) => [s.source_id, i + 1]))
  const known = ids.filter((id) => order.has(id))
  if (!known.length) return null
  return (
    <span className="cites">
      {known.map((id) => (
        <a key={id} className="cite" href={`#src-${id}`} title={sources.find((s) => s.source_id === id)?.path}>
          [{order.get(id)}]
        </a>
      ))}
    </span>
  )
}

export function Said({ statement, sources, citations = true, showContextMark = true }:
  { statement: Statement; sources: Source[]; citations?: boolean; showContextMark?: boolean }) {
  const tone = SUPPORT_TONE[statement.support]
  const generic = showContextMark && !statement.about_this_project
  // A sentence can pass the support check and still send a reader to a file that was never
  // read: "install using requirements.txt" matched an excerpt about installing, in a project
  // with no requirements.txt. Only the scan knows which files exist, so it marks them.
  const unread = statement.files_not_read ?? []
  const evidence = statement.evidence ?? { kind: 'unverified' as const,
    reason: 'This saved answer predates behaviour labels. Inspect its sources or generate a fresh answer.' }
  return (
    <li className={'said' + (tone === 'bad' || unread.length ? ' said-bad' : '')}>
      <p className="said-text">
        {statement.text.split(/(`[^`\n]+`)/g).map((part, i) =>
          part.startsWith('`') && part.endsWith('`')
            ? <code key={i}>{part.slice(1, -1)}</code> : part)}
        {citations && <Cites ids={statement.source_ids} sources={sources} />}
      </p>
      <div className="said-evidence">
        <Chip tone={evidence.kind === 'verified_code' ? 'ok' : ['suggestion', 'mixed', 'unverified'].includes(evidence.kind) ? 'warn' : 'info'}>
          {EVIDENCE_LABELS[evidence.kind] ?? EVIDENCE_LABELS.unverified}
        </Chip>
        <span className="said-says">{evidence.reason}</span>
      </div>
      {(tone === 'bad' || tone === 'warn' || generic || unread.length > 0) && (
        <p className="said-mark">
          {tone !== 'ok' && tone !== 'quiet' && <Chip tone={tone}>{SUPPORT_LABELS[statement.support]}</Chip>}
          {generic && <Chip tone="warn">Names nothing from this project</Chip>}
          {unread.length > 0 && (
            <Chip tone="bad">
              {unread.length === 1 ? 'No such file was read: ' : 'No such files were read: '}
              {unread.join(', ')}
            </Chip>
          )}
          <span className="said-says">{SUPPORT_SAYS[statement.support]}</span>
        </p>
      )}
    </li>
  )
}

export function Statements({ statements, sources, citations = true, limit, showContextMark = true }:
  { statements: Statement[]; sources: Source[]; citations?: boolean; limit?: number; showContextMark?: boolean }) {
  const shown = limit ? statements.slice(0, limit) : statements
  return (
    <>
      <ol className="said-list">
        {shown.map((s, i) => <Said key={i} statement={s} sources={sources} citations={citations}
                                 showContextMark={showContextMark} />)}
      </ol>
      {limit && statements.length > limit && (
        <p className="said-more">{statements.length - limit} more not shown in this mode.</p>
      )}
    </>
  )
}
