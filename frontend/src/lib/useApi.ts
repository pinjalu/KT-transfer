import { useCallback, useEffect, useState } from 'react'
import { ApiError, get } from './api'

export type Load<T> = {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/** Reads one endpoint. A failure is kept and shown, never swallowed into an empty screen. */
export function useApi<T>(path: string, poll = 0): Load<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)

  const reload = useCallback(() => setTick((n) => n + 1), [])

  useEffect(() => {
    let live = true
    const run = async () => {
      try {
        const body = await get(path)
        if (!live) return
        setData(body as T)
        setError(null)
      } catch (exc) {
        if (!live) return
        setError(exc instanceof ApiError ? exc.message : 'Something went wrong.')
      } finally {
        if (live) setLoading(false)
      }
    }
    void run()
    if (!poll) return () => { live = false }
    const timer = setInterval(run, poll)
    return () => { live = false; clearInterval(timer) }
  }, [path, poll, tick])

  return { data, error, loading, reload }
}
