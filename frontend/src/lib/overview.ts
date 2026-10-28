/** The shape pka/service.py build_overview() caches and GET /api/overview returns. */
import type { Source, Statement } from './answer'
import type { FeatureList } from './features'
import type { DiagramPayload } from '../components/Diagram'

export type OverviewFeatureFlow = {
  id: string; name: string; route_count: number; more_steps: number
  steps: { n: number; label: string; plain: string;
    component: { kind: string; name: string; path: string; line: number; url: string } }[]
}

export type Section = {
  system_id?: string
  system_name?: string
  system_sections?: Section[]
  generation?: import('./ai').Generation
  cache_hit?: boolean
  key: string
  title: string
  statements: Statement[]
  story?: Partial<Record<'problem' | 'solution' | 'input' | 'process' | 'output', number>>
  sources: Source[]
  missing_information: string
  error: string
  checks: { dropped_repeats: number; narrowed_citations: number; unsupported: number; generic: number }
}

export type FactItem = { text: string; path: string; line: number; url: string; detail: string }
export type FactGroup = {
  key: string
  title: string
  plain: string
  items: FactItem[]
  truncated: number
  note: string
}

export type Reading = { path: string; why: string; url: string }

export type Overview = {
  overview_scope?: string
  project_name?: string
  source_kind?: 'github' | 'local' | 'zip'
  scope_update_available?: boolean
  overview_features?: FeatureList
  systems?: { id: string; name: string }[]
  explanation_style?: string
  plain_language_update_available?: boolean
  routing_changed?: boolean
  partial?: boolean
  failed_topics?: number
  successful_topics?: number
  scan_id: number
  commit: string
  repo: string
  branch: string
  scanned_at: string | null
  demo: boolean
  sections: Section[]
  facts: FactGroup[]
  diagrams: DiagramPayload[]
  system_diagrams?: Record<string, DiagramPayload[]>
  system_feature_flows?: Record<string, OverviewFeatureFlow[]>
  roles: { cards?: unknown[] }
  steps: unknown[]
  reading_order: Reading[]
  files_indexed: number
  files_skipped: number
  topics_total: number
  topics_done: number
  complete: boolean
  scope_note: string
  elapsed_seconds?: number
}

export type OverviewReply = {
  available: boolean
  building: boolean
  progress: { done?: number; total?: number; topic?: string; topics?: Record<string,{title:string;state:string}> } | null
  overview: Overview | null
  reason: string
}

export function sectionOf(o: Overview, key: string): Section | undefined {
  return o.sections.find((s) => s.key === key)
}

export function factsOf(o: Overview, key: string): FactGroup | undefined {
  return o.facts.find((g) => g.key === key)
}
