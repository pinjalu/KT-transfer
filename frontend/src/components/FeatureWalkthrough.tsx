import { useEffect, useRef, useState } from 'react'
import { Button, Failed } from './ui'
import { Statements } from './Statements'
import { GenerationDetails } from './GenerationDetails'
import { ApiError, post } from '../lib/api'
import { sourcePath } from '../lib/answer'
import type { Source, Statement } from '../lib/answer'

type Section = { key: string; title: string; statements: Statement[]; sources: Source[];
  missing_information: string; generated_at: string; knowledge_revision: number; generation?: import('../lib/ai').Generation }

export function FeatureWalkthrough({ featureId, sections, revision }: {
  featureId: string; sections: {key: string; title: string}[]; revision: number
}) {
  const [built, setBuilt] = useState<Record<string, Section>>({})
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const active = useRef(true)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  const build = async (key: string) => {
    if (working) return
    setWorking(key); setError('')
    try {
      const reply = await post(`/api/features/${encodeURIComponent(featureId)}/walkthrough/${key}`) as Section
      if (!active.current) return
      if (reply.knowledge_revision !== revision) {
        setBuilt({}); setError('Project information changed. Refresh this feature before generating a section.'); return
      }
      setBuilt(previous => ({...previous, [key]:reply}))
    } catch (exc) {
      if (!active.current) return
      if (exc instanceof ApiError && ['access_denied','scope','stale','access','access_unverified'].includes(exc.code)) setBuilt({})
      setError(exc instanceof ApiError ? exc.message : 'The section could not be generated. Try again.')
    } finally { if (active.current) setWorking('') }
  }
  return <section aria-label="Feature KT walkthrough">
    <h3>Feature walkthrough</h3>
    <p className="feature-note">Build one section at a time from this feature's saved evidence. Each explanation shows its sources and missing information.
      Review generated claims before using them for handover. Sections stay in this view until the feature or source revision changes.</p>
    {error && <Failed message={error} />}
    {sections.map(item => {
      const section = built[item.key]
      return <article className="feature-kt-section" key={item.key}>
        <div className="feature-row-heading"><h4>{item.title}</h4><Button disabled={!!working}
          onClick={() => void build(item.key)}>{working === item.key ? 'Writing section…' : section ? `Rebuild ${item.title}` : `Build ${item.title}`}</Button></div>
        {section && <>
          <GenerationDetails value={section.generation}/>
          <Statements statements={section.statements} sources={section.sources} />
          {section.missing_information && <p className="feature-note"><strong>Knowledge gap: </strong>{section.missing_information}</p>}
          <p className="feature-muted">Generated <time dateTime={section.generated_at}>{new Date(section.generated_at).toLocaleString()}</time></p>
          <details><summary>Sources for {item.title}</summary><ol className="src-list">{section.sources.map(source =>
            <li className="src" id={`src-${source.source_id}`} key={source.source_id}>
              <strong>{sourcePath(source.path)}</strong><p>Lines {source.start} to {source.end}</p>
              <pre className="src-text">{source.text}</pre>
              {source.url && <a href={source.url} target="_blank" rel="noreferrer">View source</a>}
            </li>)}</ol></details>
        </>}
      </article>
    })}
  </section>
}
