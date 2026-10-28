export type Evidence = { path: string; line: number; url: string }
export type FeatureSnapshot = { repo?: string; branch?: string; scan_id?: number; commit?: string; knowledge_revision?: number }
export type FeatureSummary = {
  id: string; name: string; plain: string; ticket_name: string
  route_count: number; file_count: number; issue_count: number; has_tests: boolean; gap_count: number
}
export type FeatureList = FeatureSnapshot & {
  available: boolean; reason?: string; scan_id?: number; commit?: string
  features: FeatureSummary[]; unclustered?: { routes: number; files: number; note: string }
}
export type FeatureDetail = FeatureSnapshot & {
  id: string; name: string; ticket_name: string
  walkthrough_sections?: { key: string; title: string }[]
  flow: { title: string; steps: { n: number; label: string; plain: string; component: Evidence & { kind: string; name: string } }[] }
  apis_and_data: {
    routes: { method: string; path: string; declared_at: Evidence }[]
    tables: { name: string; plain: string; declared_at: Evidence }[]
    services: { name: string; plain: string; called_at: Evidence }[]
  }
  tests: { existing: (Evidence & { name: string; covers: string })[] }
  known_problems: { items: unknown[]; note: string }
  related: (Evidence & { name: string; kind: string })[]
  issues: (Evidence & { key: string; summary: string; confidence: 'confirmed' | 'possible' })[]
  gaps: { what: string; checked: string; why_missing: string }[]
}
