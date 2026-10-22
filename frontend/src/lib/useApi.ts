import { useCallback, useEffect, useState } from 'react'
import { ApiError, get } from './api'

export type Load<T> = {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/** Reads one endpoint. A failure is kept and shown, never swallowed into an empty screen. */
export function useApi<T>(path: string, poll = 0, revision?: number): Load<T> {
  const key = `${path}:${revision ?? ''}`
  const [result, setResult] = useState<{ key: string; data: T | null; error: string | null } | null>(null)
  const [tick, setTick] = useState(0)

  const reload = useCallback(() => setTick((n) => n + 1), [])

  useEffect(() => {
    let live = true
    let inFlight = false
    const run = async () => {
      if (inFlight) return
      inFlight = true
      try {
        const body = await get(path)
        if (!live) return
        setResult({ key, data: body as T, error: null })
      } catch (exc) {
        if (!live) return
        setResult({ key, data: null, error: exc instanceof ApiError ? exc.message : 'Something went wrong.' })
      } finally {
        inFlight = false
      }
    }
    void run()
    if (!poll) return () => { live = false }
    const timer = setInterval(run, poll)
    return () => { live = false; clearInterval(timer) }
  }, [path, poll, tick, key])

  // Hide the previous snapshot immediately, including while its replacement is loading.
  const current = result?.key === key ? result : null
  return { data: current?.data ?? null, error: current?.error ?? null, loading: !current, reload }
}
