/** Project destinations in sidebar order. */
export type Dest = {
  path: string
  label: string
  icon: string
  /** What the screen needs before it can show anything real. */
  needs: 'nothing' | 'scan' | 'jira' | 'slack'
}

export const DESTINATIONS: Dest[] = [
  { path: '/',                label: 'Home',             icon: 'home',       needs: 'nothing' },
  { path: '/connections',     label: 'Connections',      icon: 'link',       needs: 'nothing' },
  { path: '/overview',        label: 'Project overview', icon: 'doc',        needs: 'scan' },
  { path: '/ask',             label: 'Ask assistant',    icon: 'chat',       needs: 'scan' },
  { path: '/quality',         label: 'Answer quality',   icon: 'check',      needs: 'scan' },
  { path: '/features',        label: 'Feature explorer', icon: 'grid',       needs: 'scan' },
  { path: '/jira',            label: 'Jira tasks',       icon: 'ticket',     needs: 'jira' },
  { path: '/decisions',       label: 'Team decisions',   icon: 'people',     needs: 'slack' },
  { path: '/architecture',    label: 'Architecture',     icon: 'nodes',      needs: 'scan' },
  { path: '/troubleshooting', label: 'Troubleshooting',  icon: 'wrench',     needs: 'scan' },
  { path: '/settings',        label: 'Settings',         icon: 'gear',       needs: 'nothing' },
]
