import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { useAccount } from './AuthGate'
import { DESTINATIONS } from '../nav'
import { Sidebar } from './Sidebar'
import { Icon } from './Icon'
import { useApi } from '../lib/useApi'
import type { Status } from '../lib/types'
import { BackgroundJob } from './BackgroundJob'
import { JOB_CHANGED, PROJECT_CHANGED } from '../lib/api'
import { projectName } from '../lib/project'
import { ProjectStatus } from '../lib/useStatus'
import { RetainedPages } from './RetainedPages'
import { Failed, Loading } from './ui'

export function Shell({ children }: { children: ReactNode }) {
  const account = useAccount()
  const [logoutError, setLogoutError] = useState('')
  const location = useLocation()
  // Polled rather than read once: a scan changes this while the user is looking at another screen.
  const status = useApi<Status>('/api/status', 2000)
  const { data, reload } = status
  const savedStatus = useRef<Status | null>(null)
  if (data) savedStatus.current = data
  const workspace = data ?? savedStatus.current
  useEffect(() => {
    window.addEventListener(JOB_CHANGED, reload)
    window.addEventListener(PROJECT_CHANGED, reload)
    return () => {
      window.removeEventListener(JOB_CHANGED, reload)
      window.removeEventListener(PROJECT_CHANGED, reload)
    }
  }, [reload])
  const project = projectName(data?.settings)
  useEffect(() => {
    document.title = project ? `${project} · KT Assistant` : 'KT Assistant'
    return () => { document.title = 'KT Assistant' }
  }, [project])
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
          {workspace && <div hidden={!data} inert={!data}><ProjectStatus.Provider value={status}>
            <RetainedPages scope={JSON.stringify([workspace.settings?.repo ?? '', workspace.settings?.branch ?? ''])}
              revision={workspace.knowledge_revision}>
              {children}
            </RetainedPages>
          </ProjectStatus.Provider></div>}
          {!data && (status.error ? <Failed message={status.error} onRetry={reload} /> : <Loading what="the project" />)}
        </main>
      </div>
    </div>
  )
}
