import { useEffect } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { Failed, Loading, PageHead } from '../components/ui'
import { useApi } from '../lib/useApi'
import './local-source.css'

type SourceFile = { path: string; snapshot: string; note: string; lines: { number: number; text: string }[] }

export function LocalSource() {
  const [params] = useSearchParams()
  const { hash } = useLocation()
  const path = params.get('path') ?? ''
  const snapshot = params.get('snapshot') ?? ''
  const source = useApi<SourceFile>(`/api/local-source?path=${encodeURIComponent(path)}&snapshot=${encodeURIComponent(snapshot)}`, 30000)
  useEffect(() => {
    if (source.data && /^#L\d+$/.test(hash)) document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'center' })
  }, [source.data, hash])
  if (source.loading) return <Loading what="the saved local source" message="Checking local folder access…" />
  if (source.error) return <Failed message={source.error} onRetry={source.reload} />
  if (!source.data) return null
  return <>
    <PageHead title={source.data.path} lead={`Local folder · snapshot ${source.data.snapshot.slice(0, 7)}`}
      actions={<Link className="btn btn-secondary" to="/overview">Project overview</Link>} />
    <p className="local-source-note">{source.data.note}</p>
    <div className="local-source" aria-label="Saved source lines">
      {source.data.lines.map(line => <div id={`L${line.number}`} key={line.number} className="local-source-line">
        <a href={`#L${line.number}`} aria-label={`Line ${line.number}`}>{line.number}</a><code>{line.text || ' '}</code>
      </div>)}
    </div>
  </>
}
