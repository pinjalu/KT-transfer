import type { Settings } from './types'

export function projectName(settings?: Settings, fallbackRepo = '') {
  if (settings?.project_name) return settings.project_name
  const source = settings?.local?.path || settings?.local_path || settings?.repo || fallbackRepo
  return source.replace(/^local:/, '').replace(/\\/g, '/').replace(/\/+$/, '').split('/').pop() || ''
}
