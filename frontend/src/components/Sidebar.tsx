import { NavLink } from 'react-router-dom'
import { DESTINATIONS } from '../nav'
import { Icon } from './Icon'

export function Sidebar({ project }: { project: string }) {
  return (
    <nav className="sidebar" aria-label="Main">
      <div className="sidebar-brand">
        <span className="sidebar-mark" aria-hidden="true">K</span>
        <span className="sidebar-name">KT Assistant</span>
      </div>

      <div className="sidebar-project">
        <span className="sidebar-project-label">Project</span>
        <button className="project-pick" type="button">
          <span className="project-pick-name">{project || 'No project'}</span>
          <span className="project-pick-arrow"><Icon name="chevron" size={14} /></span>
        </button>
      </div>

      <ul className="sidebar-list">
        {DESTINATIONS.map((d) => (
          <li key={d.path}>
            <NavLink to={d.path} end={d.path === '/'}
                     className={({ isActive }) => 'sidebar-link' + (isActive ? ' is-active' : '')}>
              <Icon name={d.icon} />
              <span>{d.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>

      <div className="sidebar-foot">
        <a className="sidebar-link" href="/static/ui/help.html">
          <Icon name="search" /><span>Help</span>
        </a>
        <div className="sidebar-user">
          <span className="avatar" aria-hidden="true">P</span>
          <span className="sidebar-user-name">Local</span>
        </div>
      </div>
    </nav>
  )
}
