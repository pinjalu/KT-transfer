import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { useAccount } from './AuthGate'
import { DESTINATIONS } from '../nav'
import { Sidebar } from './Sidebar'
import { Icon } from './Icon'
import { useApi } from '../lib/useApi'
import type { Status } from '../lib/types'
import { BackgroundJob } from './BackgroundJob'
import { JOB_CHANGED } from '../lib/api'

export function Shell() {
  const account = useAccount()
  const [logoutError, setLogoutError] = useState('')
  const location = useLocation()
  // Polled rather than read once: a scan changes this while the user is looking at another screen.
  const { data, reload } = useApi<Status>('/api/status', 2000)
  useEffect(() => {
    window.addEventListener(JOB_CHANGED, reload)
    return () => window.removeEventListener(JOB_CHANGED, reload)
  }, [reload])
  const repo = data?.settings?.repo ?? ''
  const project = repo ? repo.split('/').pop()! : ''
  const here = DESTINATIONS.find((d) => d.path === location.pathname)

  return (
    <div className="shell">
      <Sidebar project={project} username={account.user.username}
               onSignOut={() => void account.logout().catch(e => setLogoutError(e.message))} />
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
          {logoutError && <p role="alert" className="auth-error">{logoutError}</p>}
          <BackgroundJob job={data?.awaiting_project ? null : data?.job ?? null} onChanged={reload} />
          <Outlet />
        </main>
      </div>
    </div>
  )
}
