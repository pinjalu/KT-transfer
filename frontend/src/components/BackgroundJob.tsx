import { useEffect, useState } from 'react'
import { ApiError, post } from '../lib/api'
import type { BackgroundJob as Job } from '../lib/types'
import { Button, Chip } from './ui'
import { JOB_NAMES, jobActive, progressText, useJobProgress } from '../lib/jobProgress'
import './background-job.css'

const STATES = { queued: 'Queued', running: 'Running', cancelling: 'Cancelling', succeeded: 'Completed',
  partial: 'Completed with gaps', failed: 'Failed', cancelled: 'Cancelled', interrupted: 'Interrupted' }

export function BackgroundJob({ job, onChanged }: { job: Job | null; onChanged: () => void }) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [hidden, setHidden] = useState<number | null>(null)
  const progress = useJobProgress(job)
  useEffect(() => { setError('') }, [job?.id])
  if (!job || hidden === job.id) return null
  const active = jobActive(job)
  const act = async (action: 'cancel' | 'retry') => {
    setPending(true)
    setError('')
    try {
      await post(`/api/jobs/${job.id}/${action}`)
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'The job could not be updated. Try again.')
    } finally {
      onChanged()
      setPending(false)
    }
  }
  return (
    <section className="background-job" aria-label="Background job">
      <div className="background-job-copy">
        <div className="background-job-title">
          <strong>{JOB_NAMES[job.kind]}{job.target ? ` · ${job.target}` : ''}</strong>
          <Chip tone={job.state === 'failed' ? 'bad' : job.state === 'succeeded' ? 'ok' : 'info'}>
            {STATES[job.state]}
          </Chip>
          {job.attempt > 1 && <span>Attempt {job.attempt}</span>}
        </div>
        <p role="status">
          {job.state === 'cancelling'
            ? 'Cancellation requested. Waiting for the current connector or model request to finish.'
            : active
            ? `${progressText(progress)}. You can keep browsing.`
            : job.error || (job.state === 'partial' ? 'Some information was not read. Check import coverage before retrying.' : 'The job has finished.')}
        </p>
        {job.can_retry && (job.kind === 'scan' || job.kind === 'local') && <p>Retry reuses completed files after checking access and changes.</p>}
        {job.can_retry && job.kind === 'evaluation' && <p>Retry starts a fresh evaluation; completed cases from this run remain available for review.</p>}
        {error && <p role="alert">{error}</p>}
      </div>
      <div className="background-job-actions">
        {job.can_cancel && <Button disabled={pending || job.state === 'cancelling'} onClick={() => void act('cancel')}>
          {job.state === 'cancelling' ? 'Cancelling…' : 'Cancel job'}
        </Button>}
        {job.can_retry && <Button kind="primary" disabled={pending} onClick={() => void act('retry')}>Retry job</Button>}
        {!active && <Button kind="ghost" onClick={() => setHidden(job.id)}>Dismiss</Button>}
      </div>
    </section>
  )
}
