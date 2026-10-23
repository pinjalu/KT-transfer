import { Link, NavLink } from 'react-router-dom'
import { DESTINATIONS } from '../nav'
import { Icon } from './Icon'

export function Sidebar({ project, username }: { project: string; username: string }) {
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
        <Link className="sidebar-user" to="/account" aria-label={`Account settings for ${username}`}>
          <span className="avatar" aria-hidden="true">{Array.from(username.trim())[0]?.toUpperCase() || '?'}</span>
          <span className="sidebar-user-name" title={username}>{username}</span>
        </Link>
      </div>
    </nav>
  )
}
