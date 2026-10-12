import { Outlet, useLocation } from 'react-router-dom'
import { DESTINATIONS } from '../nav'
import { Sidebar } from './Sidebar'
import { Icon } from './Icon'
import { useApi } from '../lib/useApi'

type Status = {
  demo?: boolean
  settings?: { repo?: string; branch?: string } | null
  scan?: { status?: string; commit?: string } | null
}

export function Shell() {
  const location = useLocation()
  // Polled rather than read once: a scan changes this while the user is looking at another screen.
  const { data } = useApi<Status>('/api/status', 4000)
  const repo = data?.settings?.repo ?? ''
  const project = repo ? repo.split('/').pop()! : ''
  const here = DESTINATIONS.find((d) => d.path === location.pathname)

  return (
    <div className="shell">
      <Sidebar project={project} />
      <div className="main">
        <header className="topbar">
          <nav className="crumbs" aria-label="Breadcrumb">
            <span className="crumb">{project || 'KT Assistant'}</span>
            {here && here.path !== '/' && (
              <>
                <span className="crumb-sep" aria-hidden="true"><Icon name="chevron" size={13} /></span>
                <span className="crumb is-here">{here.label}</span>
              </>
            )}
          </nav>
          <div className="topbar-right">
            {data?.demo && (
              <span className="chip chip-info"><Icon name="database" size={14} /> Sample data</span>
            )}
            <span className="chip chip-quiet"><Icon name="lock" size={14} /> All connections are read-only</span>
          </div>
        </header>
        <main className="page">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
