import { useState } from 'react'
import { Button, Card, Chip, Empty, Failed, Loading } from './ui'
import { useApi } from '../lib/useApi'
import { ApiError, get } from '../lib/api'
import type { History } from '../lib/sources'
import { RUN_TONE } from '../lib/sources'

export function ImportHistory() {
  const history = useApi<History>('/api/import-history')
  const [openFile, setOpenFile] = useState('')
  const [text, setText] = useState('')
  const [failed, setFailed] = useState('')

  const show = async (file: string) => {
    if (openFile === file) { setOpenFile(''); return }
    setOpenFile(file); setText(''); setFailed('')
    try {
      const body = (await get('/api/import-history/' + encodeURIComponent(file))) as { text: string }
      setText(body.text)
    } catch (exc) {
      setFailed(exc instanceof ApiError ? exc.message : 'Could not read that report.')
    }
  }

  if (history.loading) return <Loading what="import history" />
  if (history.error) return <Failed message={history.error} onRetry={history.reload} />

  const runs = history.data?.runs ?? []

  return (
    <Card>
      {runs.length === 0 ? (
        <Empty title="No scan has been run yet."
               detail="Every repository scan writes a report here, including the ones that fail." />
      ) : (
        <>
          <table className="runs">
            <thead>
              <tr>
                <th>Run</th><th>Repository</th><th>Outcome</th>
                <th>Read</th><th>Skipped</th><th>Failed</th><th>Finished</th><th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.file} className={openFile === run.file ? 'is-open' : ''}>
                  <td className="mono">#{run.scan_id}</td>
                  <td>
                    <span className="run-repo">{run.repo || 'unknown'}</span>
                    {run.commit && run.commit !== 'None' && (
                      <span className="run-commit mono">{run.commit.slice(0, 7)}</span>
                    )}
                  </td>
                  <td><Chip tone={RUN_TONE[run.status] ?? 'quiet'}>{run.status}</Chip></td>
                  <td className="num">{run.read}</td>
                  <td className="num">{run.skipped}</td>
                  <td className="num">{run.failed}</td>
                  <td className="run-when">
                    {run.finished && run.finished !== 'None'
                      ? new Date(run.finished).toLocaleString()
                      : 'did not finish'}
                  </td>
                  <td>
                    <Button kind="ghost" onClick={() => void show(run.file)}>
                      {openFile === run.file ? 'Hide' : 'View log'}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {openFile && (
            <div className="run-log">
              <p className="run-log-name mono">{openFile}</p>
              {failed && <Failed message={failed} />}
              {!failed && !text && <Loading what="the report" />}
              {text && <pre>{text}</pre>}
            </div>
          )}
        </>
      )}

      <p className="fg-note">
        {history.data?.note} The most recent {history.data?.kept} reports are kept; older ones are
        deleted automatically.
      </p>
    </Card>
  )
}
