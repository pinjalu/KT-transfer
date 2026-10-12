import { Chip } from './ui'
import type { Source, Statement } from '../lib/answer'
import { SUPPORT_SAYS, SUPPORT_TONE } from '../lib/answer'

/**
 * How a model-written sentence is shown anywhere in this interface.
 *
 * pka/overview.py already decides two things about every statement: whether the excerpt it
 * cites actually carries it, and whether it names anything belonging to this project. Both were
 * being computed and shown nowhere. A reader who cannot see which sentence to distrust is worse
 * off than one shown fewer sentences, so the marks are part of the sentence, not a footnote.
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

export function Said({ statement, sources, citations = true }:
  { statement: Statement; sources: Source[]; citations?: boolean }) {
  const tone = SUPPORT_TONE[statement.support]
  const generic = !statement.about_this_project
  // A sentence can pass the support check and still send a reader to a file that was never
  // read: "install using requirements.txt" matched an excerpt about installing, in a project
  // with no requirements.txt. Only the scan knows which files exist, so it marks them.
  const unread = statement.files_not_read ?? []
  return (
    <li className={'said' + (tone === 'bad' || unread.length ? ' said-bad' : '')}>
      <p className="said-text">
        {statement.text}
        {citations && <Cites ids={statement.source_ids} sources={sources} />}
      </p>
      {(tone === 'bad' || tone === 'warn' || generic || unread.length > 0) && (
        <p className="said-mark">
          {tone !== 'ok' && tone !== 'quiet' && <Chip tone={tone}>{statement.support}</Chip>}
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

export function Statements({ statements, sources, citations = true, limit }:
  { statements: Statement[]; sources: Source[]; citations?: boolean; limit?: number }) {
  const shown = limit ? statements.slice(0, limit) : statements
  return (
    <>
      <ol className="said-list">
        {shown.map((s, i) => <Said key={i} statement={s} sources={sources} citations={citations} />)}
      </ol>
      {limit && statements.length > limit && (
        <p className="said-more">{statements.length - limit} more not shown in this mode.</p>
      )}
    </>
  )
}
