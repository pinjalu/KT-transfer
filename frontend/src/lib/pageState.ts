import { createContext, useContext, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

export const PageActive = createContext(true)
export const usePageActive = () => useContext(PageActive)

/** A sidebar link has no query string; keep the last selection when returning to it. */
export function useRememberedParam(name: string) {
  const [params, setParams] = useSearchParams()
  const value = params.get(name) || ''
  const [previous, setPrevious] = useState(value)
  useEffect(() => { if (value) setPrevious(value) }, [value])
  return [value || previous, setParams] as const
}
