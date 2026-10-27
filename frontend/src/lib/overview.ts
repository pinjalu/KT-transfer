/** The shape pka/service.py build_overview() caches and GET /api/overview returns. */
import type { Source, Statement } from './answer'

export type Section = {
  generation?: import('./ai').Generation
  cache_hit?: boolean
  key: string
  title: string
  statements: Statement[]
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
  diagrams: unknown[]
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
