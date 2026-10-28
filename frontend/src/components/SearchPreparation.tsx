import { useState } from 'react'
import { ApiError, post } from '../lib/api'
import type { Status } from '../lib/types'
import { Button, Card, Chip } from './ui'

export function SearchPreparation({ status, onChanged }: { status: Status; onChanged: () => void }) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  if (!status.semantic_available) return null
  const basic = status.search_mode === 'basic'
  const change = async () => {
    setPending(true)
    setError('')
    try {
      await post('/api/search-mode', { mode: basic ? 'semantic' : 'basic' })
      onChanged()
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Search preference could not be saved. Try again.')
    } finally { setPending(false) }
  }
  return <Card>
    <h2>Search preparation <Chip tone="info">{basic ? 'Basic word search' : 'Meaning search'}</Chip></h2>
    <p>{basic
      ? 'Files become ready sooner because search uses matching words. It may miss results that use different words for the same idea. You can still ask questions and build the overview.'
      : 'Search can find related ideas even when the words are different. The first import takes longer; later reads reuse unchanged text when the same search model is used.'}</p>
    <p>This choice is saved for all sources in your workspace. Turning on meaning search prepares missing text during the next read, question or overview build.</p>
    <Button disabled={pending || status.busy} onClick={() => void change()}>
      {pending ? 'Saving…' : basic ? 'Use meaning search' : 'Use basic search'}
    </Button>
    {status.busy && <p className="conn-plain">Wait for the current job, or use its “Use basic search now” button during search preparation.</p>}
    {error && <p role="alert">{error}</p>}
  </Card>
}
