/**
 * Mockup 08. The shape of the project, drawn from what was read.
 *
 * Nothing here is new backend work. `pka/diagram.py` has derived three diagrams since the
 * overview was built, `pka/facts.py` has the exact routes, stores and services with their
 * line numbers, and `pka/roles.py` has a card per file saying what uses it and what it uses.
 * All of it already arrives in the GET /api/overview payload and had nowhere to appear.
 *
 * The tabs are split by whether a thing is worth drawing. A graph of imports is; a list of
 * four tables is not, and pretending otherwise would be decoration.
 */
import { useState } from 'react'
import { Card, Chip, Empty, Failed, Loading, NoProject, PageHead, SourceLink, Tabs } from '../components/ui'
import { Diagram } from '../components/Diagram'
import type { DiagramNode, DiagramPayload } from '../components/Diagram'
import { useApi } from '../lib/useApi'
import type { FactGroup, OverviewReply } from '../lib/overview'
import type { Status } from '../lib/types'
import './architecture.css'

type RoleLink = { path: string; name: string; line: number; url: string }
type RoleCard = {
  path: string; name: string; url: string
  purpose: string; purpose_line: number
  holds: string[]; used_by: RoleLink[]; calls: RoleLink[]
}

const DRAWN = ['modules', 'journey', 'stack']
const TAB_FOR: Record<string, string> = {
  modules: 'System map', journey: 'Request flow', stack: 'Layers',
}
/** Which fact group answers which tab. Each is a list with real lines, not a drawing. */
const FACT_TABS: [string, string][] = [
  ['APIs', 'routes'], ['Database', 'stores'],
  ['External services', 'services'], ['Deployment', 'delivery'],
]

function Facts({ group }: { group: FactGroup | undefined }) {
  if (!group || !group.items.length) {
    return <Empty title="Nothing of this kind was found in the files that were read."
                  detail="This is what the scan found, not a judgement that the project has none. A file that was skipped cannot contribute." />
  }
  return (
    <>
      <p className="arch-plain">{group.plain}</p>
      <ul className="arch-facts">
        {group.items.map((item, i) => (
          <li key={i}>
            <div className="arch-fact-main">
              <span className="arch-fact-text">{item.text}</span>
              {item.detail && <span className="arch-fact-detail">{item.detail}</span>}
            </div>
            {item.path && <SourceLink path={item.path} line={item.line} url={item.url} />}
          </li>
        ))}
      </ul>
      {group.truncated > 0 && <p className="arch-more">{group.truncated} more not shown.</p>}
      {group.note && <p className="dg-note">{group.note}</p>}
    </>
  )
}

/**
 * What one box stands for. Every line of it is read from import statements, so "Used by" and
 * "Uses" carry the line the import sits on rather than a claim that two files are related.
 */
function Detail({ card, picked, onClose }:
  { card: RoleCard | null; picked: string; onClose: () => void }) {
  if (!picked) {
    return (
      <Card title="Nothing selected">
        <p className="arch-hint">
          Pick a box to see what that file is for, what reaches it and what it reaches. Every
          arrow on the map is an import statement at a line you can open.
        </p>
      </Card>
    )
  }
  // A box can be drawn without having a card. pka/roles.py describes the files it can say
  // something exact about, so a stylesheet or a test file appears on the map and has no
  // entry. Saying so beats showing the empty panel that means "nothing is selected".
  if (!card) {
    return (
      <Card title={picked.split('/').pop()}
            sub={picked}
            aside={<button type="button" className="btn btn-ghost" onClick={onClose}>Clear</button>}>
        <p className="arch-hint">
          This file is on the map because something imports it or it sits in one of the layers,
          but no card was written for it. Cards are only made where the file's own contents say
          what it is for, so a stylesheet, a template or a test usually has none.
        </p>
      </Card>
    )
  }
  return (
    <Card title={card.name}
          sub={card.path}
          aside={<button type="button" className="btn btn-ghost" onClick={onClose}>Clear</button>}>
      {card.purpose
        ? <p className="arch-purpose">{card.purpose}</p>
        : <p className="arch-hint">No file in the project states what this one is for.</p>}
      {card.url && <SourceLink path={card.path} line={card.purpose_line || 1} url={card.url} />}

      {card.holds.length > 0 && (
        <div className="arch-block">
          <h4>What it declares</h4>
          <ul className="arch-plainlist">{card.holds.map((h, i) => <li key={i}>{h}</li>)}</ul>
        </div>
      )}

      <div className="arch-block">
        <h4>Used by <Chip tone="quiet">{card.used_by.length}</Chip></h4>
        {card.used_by.length
          ? <ul className="arch-links">
              {card.used_by.map((l, i) => (
                <li key={i}><SourceLink path={l.path} line={l.line} url={l.url} /></li>
              ))}
            </ul>
          : <p className="arch-hint">No file that was read imports this one.</p>}
      </div>

      <div className="arch-block">
        <h4>Uses <Chip tone="quiet">{card.calls.length}</Chip></h4>
        {card.calls.length
          ? <ul className="arch-links">
              {card.calls.map((l, i) => (
                <li key={i}><SourceLink path={l.path} line={l.line} url={l.url} /></li>
              ))}
            </ul>
          : <p className="arch-hint">This file imports nothing else that was read.</p>}
      </div>
    </Card>
  )
}

export function Architecture() {
  const status = useApi<Status>('/api/status', 5000)
  const reply = useApi<OverviewReply>('/api/overview', 6000, status.data?.knowledge_revision)
  const [tab, setTab] = useState('')
  const [picked, setPicked] = useState('')

  if (status.data?.awaiting_project) {
    return <><PageHead title="Architecture" /><NoProject what="the system map" /></>
  }
  if (reply.loading) return <Loading what="the architecture" />
  if (reply.error) return <Failed message={reply.error} onRetry={reply.reload} />

  const body = reply.data?.overview ?? null
  if (!body) {
    return (
      <>
        <PageHead title="Architecture" />
        <Card>
          <Empty title="The diagrams are built with the overview."
                 detail="Every box and arrow here is derived from the files that were read, and that derivation runs as part of building the overview. Build one and this screen fills in."
                 action={<a className="btn btn-primary" href="/overview">Go to Project overview</a>} />
        </Card>
      </>
    )
  }

  const diagrams = ((body.diagrams ?? []) as DiagramPayload[])
    .filter((d) => d && d.nodes?.length)
  const ordered = DRAWN.map((k) => diagrams.find((d) => d.key === k)).filter(Boolean) as DiagramPayload[]
  const facts = body.facts ?? []
  const cards = ((body.roles?.cards ?? []) as RoleCard[])

  const tabs = [...ordered.map((d) => TAB_FOR[d.key] ?? d.title), ...FACT_TABS.map(([name]) => name)]
  const active = tab && tabs.includes(tab) ? tab : tabs[0] ?? ''
  const drawn = ordered.find((d) => (TAB_FOR[d.key] ?? d.title) === active)
  const factKey = FACT_TABS.find(([name]) => name === active)?.[1]
  const card = cards.find((c) => c.path === picked) ?? null

  const pick = (n: DiagramNode) => setPicked((p) => (p === n.path ? '' : n.path))

  return (
    <>
      <PageHead title="Architecture"
                lead={`Drawn from ${body.repo} at commit ${body.commit?.slice(0, 7)}. No model decided any of it.`} />

      {!tabs.length ? (
        <Card>
          <Empty title="Nothing could be drawn from this scan."
                 detail="A diagram needs import statements between files that were read. A scan of documents alone, or one where most files were skipped, produces no shape to draw." />
        </Card>
      ) : (
        <>
          <Tabs items={tabs} active={active} onPick={(t) => setTab(t)} />
          <div className="grid-main arch-grid">
            <div className="stack">
              <Card title={drawn ? drawn.title : active}
                    aside={drawn ? <Chip tone="ok">Drawn from the files</Chip> : undefined}>
                {drawn
                  ? <Diagram d={drawn} selected={picked} onPick={pick} />
                  : <Facts group={facts.find((g) => g.key === factKey)} />}
              </Card>
            </div>
            <div className="stack">
              <Detail card={card} picked={picked} onClose={() => setPicked('')} />
            </div>
          </div>
        </>
      )}
    </>
  )
}
