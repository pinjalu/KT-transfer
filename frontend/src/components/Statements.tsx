import { Chip } from './ui'
import type { Source, Statement } from '../lib/answer'
import { EVIDENCE_LABELS, SUPPORT_LABELS, SUPPORT_SAYS, SUPPORT_TONE } from '../lib/answer'

/**
 * How a model-written sentence is shown anywhere in this interface.
 *
 * Provenance, word overlap and project specificity are separate signals. None of the
 * model-written prose is verified merely because its citation has matching words.
 * Keep citations available; explanatory provenance belongs in an optional disclosure.
 * Suggestions, unverified answers and concrete source warnings stay visibly labelled.
 */
export function Cites({ ids, sources, style = 'number' }: { ids: string[]; sources: Source[]; style?: 'number' | 'named' }) {
  const order = new Map(sources.map((s, i) => [s.source_id, i + 1]))
  const known = ids.filter((id) => order.has(id))
  if (!known.length) return null
  return (
    <span className="cites">
      {known.map((id) => (
        <a key={id} className="cite" href={`#src-${id}`} title={sources.find((s) => s.source_id === id)?.path}>
          {style === 'named' ? `View source: ${sources.find((s) => s.source_id === id)?.path?.split('/').pop() || 'file'}` : `[${order.get(id)}]`}
        </a>
      ))}
    </span>
  )
}

/** Render a small, safe text format; generated HTML is never interpreted. */
function StatementText({ text }: { text: string }) {
  const clean = text.replace(/&#(x[\da-f]+|\d+);|&nbsp;/gi, (entity, value: string | undefined) => {
    if (!value) return ' '
    const point = value[0].toLowerCase() === 'x' ? parseInt(value.slice(1), 16) : parseInt(value, 10)
    return point > 0 && point <= 0x10ffff && !(point >= 0xd800 && point <= 0xdfff)
      ? String.fromCodePoint(point) : entity
  }).replace(/^\s*(?:\d+[.)]|[-*])\s*$/gm, '').trim()
  return <>{clean.split(/\n\s*\n/).filter(Boolean).map((paragraph, index) => <p key={index}>
    {paragraph.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g).map((part, i) =>
      part.startsWith('`') && part.endsWith('`') ? <code key={i}>{part.slice(1, -1)}</code>
        : part.startsWith('**') && part.endsWith('**') ? <strong key={i}>{part.slice(2, -2)} </strong>
        : part)}
  </p>)}</>
}

export function Said({ statement, sources, citations = true, showContextMark = true, citationStyle = 'number' }:
  { statement: Statement; sources: Source[]; citations?: boolean; showContextMark?: boolean; citationStyle?: 'number' | 'named' }) {
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
      <div className="said-text">
        <StatementText text={statement.text} />
        {citations && <Cites ids={statement.source_ids} sources={sources} style={citationStyle} />}
      </div>
      {!!statement.function_refs?.length && <div className="said-functions"><span>Open function:</span>{statement.function_refs.map(ref =>
        <a key={`${ref.path}:${ref.line}:${ref.name}`} href={ref.url} target="_blank" rel="noreferrer"
          title={`${ref.path}:${ref.line}`}><code>{ref.name}()</code></a>)}</div>}
      {!['code', 'mixed', 'documentation', 'discussion'].includes(evidence.kind) &&
        <div className="said-evidence"><Chip tone={evidence.kind === 'verified_code' ? 'ok' : 'warn'}>
          {EVIDENCE_LABELS[evidence.kind] ?? EVIDENCE_LABELS.unverified}
        </Chip></div>}
      <details className="said-source-details">
        <summary>Source details</summary>
        <p>{EVIDENCE_LABELS[evidence.kind] ?? EVIDENCE_LABELS.unverified}: {evidence.reason}</p>
        {(tone === 'bad' || tone === 'warn') && <p>{SUPPORT_SAYS[statement.support]}</p>}
      </details>
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
        </p>
      )}
    </li>
  )
}

export function Statements({ statements, sources, citations = true, limit, showContextMark = true, citationStyle = 'number' }:
  { statements: Statement[]; sources: Source[]; citations?: boolean; limit?: number; showContextMark?: boolean; citationStyle?: 'number' | 'named' }) {
  const shown = limit ? statements.slice(0, limit) : statements
  return (
    <>
      <ol className="said-list">
        {shown.map((s, i) => <Said key={i} statement={s} sources={sources} citations={citations} citationStyle={citationStyle}
                                 showContextMark={showContextMark} />)}
      </ol>
      {limit && statements.length > limit && (
        <p className="said-more">{statements.length - limit} more not shown in this mode.</p>
      )}
    </>
  )
}
