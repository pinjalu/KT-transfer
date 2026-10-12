import { Card, PageHead } from '../components/ui'

/**
 * A screen in the plan that is not built yet. It says which step builds it and what it will
 * hold, rather than showing a convincing page made of nothing. Deleted as each screen lands.
 */
export function Pending({ step, title, lead, items }:
  { step: string; title: string; lead: string; items: string[] }) {
  return (
    <>
      <PageHead title={title} />
      <Card>
        <div className="not-built">
          <p className="not-built-step">{step}, not built yet</p>
          <h2>What this screen will hold</h2>
          <p>{lead}</p>
          <ul>{items.map((t) => <li key={t}>{t}</li>)}</ul>
        </div>
      </Card>
    </>
  )
}
