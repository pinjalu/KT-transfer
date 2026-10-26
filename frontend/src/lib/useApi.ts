import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, get } from './api'
import { usePageActive } from './pageState'

export type Load<T> = {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/** Reads one endpoint. A failure is kept and shown, never swallowed into an empty screen. */
export function useApi<T>(path: string, poll = 0, revision?: number, enabled = true): Load<T> {
  const active = usePageActive()
  const key = `${path}:${revision ?? ''}`
  const [result, setResult] = useState<{ key: string; data: T | null; error: string | null } | null>(null)
  const [tick, setTick] = useState(0)
  const runCurrent = useRef<(() => void) | null>(null)

  const reload = useCallback(() => setTick((n) => n + 1), [])

  useEffect(() => {
    if (!enabled) { setResult(null); return }
    let live = true
    let inFlight = false
    const controller = new AbortController()
    const run = async () => {
      if (inFlight) return
      inFlight = true
      try {
        const body = await get(path, controller.signal)
        if (!live) return
        setResult({ key, data: body as T, error: null })
      } catch (exc) {
        if (!live) return
        setResult({ key, data: null, error: exc instanceof ApiError ? exc.message : 'Something went wrong.' })
      } finally {
        inFlight = false
      }
    }
    runCurrent.current = run
    void run()
    return () => {
      live = false
      controller.abort()
      runCurrent.current = null
    }
  }, [path, tick, key, enabled])

  // Changing the polling rate must not abandon a slow request and start it again.
  useEffect(() => {
    if (!enabled || !poll || !active) return
    const timer = setInterval(() => runCurrent.current?.(), poll)
    return () => clearInterval(timer)
  }, [poll, enabled, active])

  // Hide the previous snapshot immediately, including while its replacement is loading.
  const current = enabled && result?.key === key ? result : null
  return { data: current?.data ?? null, error: current?.error ?? null, loading: !current, reload }
}
