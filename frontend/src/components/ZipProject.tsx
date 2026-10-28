import { useRef, useState } from 'react'
import { Button, Card, Chip, Failed } from './ui'
import { ImportCoverage } from './ImportCoverage'
import type { Coverage } from './ImportCoverage'
import type { Status } from '../lib/types'
import { post, uploadZip } from '../lib/api'

export function ZipProject({ status, coverage, onChanged }: {
  status: Status | null; coverage?: Coverage; onChanged: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const selected = status?.settings?.source_kind === 'zip'
  const stored = status?.stored_project?.source_kind === 'zip'
  const disabled = uploading || !!status?.busy || !!status?.demo
  const run = async (action: 'upload' | 'resume' | 'scan') => {
    setError(''); setNote(''); setUploading(true)
    try {
      if (action === 'upload') {
        if (!file) return
        if (!file.name.toLowerCase().endsWith('.zip')) throw new Error('Choose a .zip project file.')
        if (file.size > 25 * 1024 * 1024) throw new Error('ZIP uploads must be 25 MB or smaller.')
        await uploadZip(file)
        setFile(null)
        if (input.current) input.current.value = ''
        setNote('ZIP uploaded. Reading the project files now. When the scan finishes, open Project overview or Ask assistant.')
      } else {
        await post(action === 'resume' ? '/api/zip/resume' : '/api/scan')
        setNote(action === 'resume' ? 'Saved ZIP project selected.' : 'Reading the saved ZIP files again.')
      }
    } catch (exc) { setError(exc instanceof Error ? exc.message : 'The ZIP could not be uploaded.') }
    finally { setUploading(false); onChanged() }
  }
  return <Card title="ZIP project" sub="Upload source code and documentation from this computer.">
    {(selected || stored) && <p>Saved ZIP: <strong>{status?.settings?.archive?.filename ?? status?.stored_project?.project_name}</strong>
      {stored && <Button disabled={disabled} onClick={() => void run('resume')}>Use saved ZIP</Button>}</p>}
    <label className="field"><span className="field-label">Project ZIP file</span>
      <input ref={input} type="file" accept=".zip,application/zip" disabled={disabled}
        onChange={event => { setFile(event.target.files?.[0] ?? null); setError(''); setNote('') }} />
    </label>
    <p className="conn-local-note">Up to 25 MB compressed and 100 MB expanded. Reads up to 500 supported files,
      256 KB per file and 5 MB of text. Dependencies, generated files and secret filenames are excluded.</p>
    <p className="conn-local-note">The ZIP becomes the current project. Upload a new ZIP when your code changes.
      Replacing the project clears its previous scan and generated answers. No GitHub token is needed.</p>
    <div className="conn-act">
      <Button kind="primary" disabled={disabled || !file} onClick={() => void run('upload')}>{uploading ? 'Please wait…' : 'Upload and read files'}</Button>
      {selected && <Button disabled={disabled} onClick={() => void run('scan')}>Read saved ZIP again</Button>}
    </div>
    {note && <p role="status">{note}</p>}{error && <Failed message={error} />}
    {selected && status?.scan && <div className="conn-counts"><span><b>{status.scan.read}</b> read</span>
      <span><b>{status.scan.skipped}</b> skipped</span><span><b>{status.scan.failed}</b> failed</span><Chip>{status.scan.status}</Chip></div>}
    <ImportCoverage coverage={coverage} />
  </Card>
}
