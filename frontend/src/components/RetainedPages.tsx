import { useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Routes, useLocation } from 'react-router-dom'
import type { Location } from 'react-router-dom'
import { PageActive } from '../lib/pageState'

function Page({ active, location, children }: { active: boolean; location: Location; children: ReactNode }) {
  const element = useRef<HTMLDivElement>(null)
  const position = useRef(0)
  useLayoutEffect(() => {
    if (!active) return
    const scroller = element.current?.closest('.page')
    if (!scroller) return
    scroller.scrollTop = position.current
    const remember = () => { position.current = scroller.scrollTop }
    scroller.addEventListener('scroll', remember)
    return () => scroller.removeEventListener('scroll', remember)
  }, [active])
  return <div ref={element} hidden={!active} inert={!active} data-page={location.pathname} onClick={event => {
    // A retained page may have the same citation IDs. Resolve anchors inside this page.
    const link = event.target instanceof Element ? event.target.closest('a[href^="#"]') : null
    const id = link?.getAttribute('href')?.slice(1)
    const target = id ? Array.from(element.current?.querySelectorAll<HTMLElement>('[id]') ?? []).find(node => node.id === id) : null
    if (!active || !target) return
    event.preventDefault()
    if (target instanceof HTMLDetailsElement) target.open = true
    target.scrollIntoView({ block: 'nearest' })
  }}>
    <PageActive.Provider value={active}><Routes location={location}>{children}</Routes></PageActive.Provider>
  </div>
}

/** Mount a page on its first visit, then retain its content and controls in this session. */
export function RetainedPages({ children, scope, revision }: { children: ReactNode; scope: string; revision?: number }) {
  const location = useLocation()
  const [saved, setSaved] = useState<{ scope: string; revision?: number; pages: Record<string, Location> }>({ scope, revision, pages: {} })
  const pages = saved.scope === scope ? saved.pages : {}
  // Account forms contain credentials, so they are discarded when leaving Account.
  // A source refresh resets data views, but the conversation is a record of earlier replies.
  const retained = Object.fromEntries(Object.entries(pages).filter(([path]) =>
    (path !== '/account' || path === location.pathname)
    && (saved.revision === revision || path === '/ask' || path === location.pathname)))
  if (saved.scope !== scope || saved.revision !== revision || retained[location.pathname] !== location
    || Object.keys(retained).length !== Object.keys(pages).length) {
    setSaved({ scope, revision, pages: { ...retained, [location.pathname]: location } })
  }
  return <>{Object.entries({ ...retained, [location.pathname]: location }).map(([path, page]) =>
    <Page key={JSON.stringify([scope, path, path === '/ask' ? null : revision])}
      active={path === location.pathname} location={page}>{children}</Page>)}</>
}
