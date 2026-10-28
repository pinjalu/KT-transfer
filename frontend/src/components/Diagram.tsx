/**
 * The diagrams pka/diagram.py derives, drawn.
 *
 * The layout arithmetic is a port of the one in pka/static/app.js rather than a rewrite. That
 * version's geometry was checked against a real scan, no two boxes overlapping, every box
 * inside the canvas and every arrow that is not marked as looping running left to right, and
 * there is nothing to gain by inventing a second set of rules that has not been.
 *
 * Columns and rows are decided on the server. Only pixels are decided here.
 */
import type { ReactNode } from 'react'

export type DiagramNode = {
  id: string
  label: string
  sublabel: string
  path: string
  line: number
  url: string
  kind: string
  fields?: string[]
  column: number
  row: number
}

export type DiagramEdge = { from: string; to: string; line: number; count: number; back: boolean; reason?: string }

/** A band holds no node list. Its members are the nodes carrying the same `column`. */
export type Band = { key: string; title: string; plain: string; column: number; count: number }

export type DiagramPayload = {
  key: string
  kind: 'graph' | 'bands'
  title: string
  plain: string
  note: string
  nodes: DiagramNode[]
  edges: DiagramEdge[]
  bands?: Band[]
  circular?: unknown[]
}

const BOX_W = 168, BOX_H = 48, GAP_X = 56, GAP_Y = 14, PAD = 14
const LABEL_MAX = 24

function clipped(text: string) {
  return text.length > LABEL_MAX ? text.slice(0, LABEL_MAX - 1) + '…' : text
}

/** What the browser puts in the hover bubble, and what a reader is told an arrow means. */
function edgeReason(edge: DiagramEdge) {
  if (edge.reason) return edge.reason + (edge.line ? ` (line ${edge.line})` : '')
  if (edge.back) return 'these two files import each other' + (edge.line ? ', at line ' + edge.line : '')
  if (edge.count > 1) return `${edge.count} imports cross here`
  return edge.line ? 'declared at line ' + edge.line : 'a request arrives here'
}

function Box({ item, x, y, selected, onPick }:
  { item: DiagramNode; x: number; y: number; selected: boolean; onPick?: (n: DiagramNode) => void }) {
  const title = [item.label, item.sublabel, item.path && (item.path + (item.line ? ':' + item.line : ''))]
    .filter(Boolean).join(' · ')
  const pickable = Boolean(onPick && item.path)
  const inner: ReactNode = (
    <>
      <rect x={x} y={y} width={BOX_W} height={BOX_H} rx={7}
            className={'dg-box' + (selected ? ' dg-box-on' : '')} />
      <text x={x + BOX_W / 2} y={y + (item.sublabel ? 20 : 28)} className="dg-label">
        {clipped(item.label)}
      </text>
      {item.sublabel && (
        <text x={x + BOX_W / 2} y={y + 34} className="dg-sub">{clipped(item.sublabel)}</text>
      )}
      <title>{title}</title>
    </>
  )
  return (
    <g className={'dg-node dg-' + item.kind + (pickable ? ' dg-pick' : '')}
       onClick={pickable ? () => onPick!(item) : undefined}
       role={pickable ? 'button' : undefined}
       tabIndex={pickable ? 0 : undefined}
       onKeyDown={pickable ? (e) => { if (e.key === 'Enter' || e.key === ' ') onPick!(item) } : undefined}>
      {inner}
    </g>
  )
}

function Graph({ d, selected, onPick }:
  { d: DiagramPayload; selected: string; onPick?: (n: DiagramNode) => void }) {
  const columns = Math.max(...d.nodes.map((n) => n.column)) + 1
  const tall: number[] = []
  for (let c = 0; c < columns; c++) tall.push(d.nodes.filter((n) => n.column === c).length)
  const rows = Math.max(...tall, 1)
  const loops = d.edges.some((e) => e.back)
  const width = PAD * 2 + columns * BOX_W + (columns - 1) * GAP_X
  const height = PAD * 2 + rows * (BOX_H + GAP_Y) - GAP_Y + (loops ? 46 : 0)

  const where: Record<string, { x: number; y: number }> = {}
  for (const item of d.nodes) {
    // Each column is centred against the tallest one, so a chain of single boxes reads as a
    // straight line rather than hugging the top edge.
    const offset = (rows - tall[item.column]) * (BOX_H + GAP_Y) / 2
    where[item.id] = {
      x: PAD + item.column * (BOX_W + GAP_X),
      y: PAD + offset + item.row * (BOX_H + GAP_Y),
    }
  }

  return (
    <div className="dg-holder">
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height}
           className="dg" role="img" aria-label={d.title}>
        <defs>
          <marker id={'dg-arrow-' + d.key} viewBox="0 0 8 8" refX={7} refY={4}
                  markerWidth={6} markerHeight={6} orient="auto-start-reverse">
            <path d="M 0 0 L 8 4 L 0 8 z" className="dg-head" />
          </marker>
        </defs>

        {d.edges.map((edge, i) => {
          const from = where[edge.from], to = where[edge.to]
          if (!from || !to) return null
          let path: string
          let cls = 'dg-edge'
          if (edge.back) {
            // Two files importing each other cannot sit left of one another, so this arrow
            // travels under every box instead of back through them. Dashed, as the odd one out.
            const x1 = from.x + BOX_W / 2, x2 = to.x + BOX_W / 2
            const floor = height - PAD - 8
            path = `M ${x1} ${from.y + BOX_H} C ${x1} ${floor}, ${x2} ${floor}, ${x2} ${to.y + BOX_H}`
            cls += ' dg-edge-back'
          } else {
            const x1 = from.x + BOX_W, y1 = from.y + BOX_H / 2
            const x2 = to.x, y2 = to.y + BOX_H / 2
            const bend = Math.max(22, (x2 - x1) / 2)
            path = `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`
          }
          return (
            <g key={i}>
              <path d={path} className={cls} markerEnd={`url(#dg-arrow-${d.key})`}>
                <title>{edgeReason(edge)}</title>
              </path>
              {edge.count > 1 && !edge.back && (
                <text x={(from.x + BOX_W + to.x) / 2}
                      y={(from.y + to.y) / 2 + BOX_H / 2 - 5} className="dg-count">
                  {edge.count}
                </text>
              )}
            </g>
          )
        })}

        {d.nodes.map((item) => (
          <Box key={item.id} item={item} x={where[item.id].x} y={where[item.id].y}
               selected={selected === item.path} onPick={onPick} />
        ))}
      </svg>
    </div>
  )
}

/**
 * Bands have no arrows, so they are ordinary elements rather than a drawing. That keeps the
 * text selectable and lets the layout wrap on a narrow screen, which a fixed canvas cannot.
 */
function Bands({ d, selected, onPick }:
  { d: DiagramPayload; selected: string; onPick?: (n: DiagramNode) => void }) {
  // A band names no members. It carries a column, and the files in it are the nodes sitting
  // in that column, which is the same arrangement the graph layout uses.
  const inColumn = (c: number) => d.nodes.filter((n) => n.column === c)
  return (
    <div className="dg-bands">
      {(d.bands ?? []).map((band) => {
        const members = inColumn(band.column)
        return (
          <div className="dg-band" key={band.key}>
            <div className="dg-band-head">
              <span className="dg-band-number">{band.column + 1}</span>
              <div className="dg-band-names">
                <h5 className="dg-band-title">{band.title}</h5>
                <p className="dg-band-plain">{band.plain}</p>
              </div>
              <span className="badge">{band.count} {band.count === 1 ? 'file' : 'files'}</span>
            </div>
            <div className="dg-band-boxes">
              {members.map((item) => (
                <button type="button" key={item.id}
                        className={'dg-band-box' + (selected === item.path ? ' dg-band-box-on' : '')}
                        onClick={onPick && item.path ? () => onPick(item) : undefined}
                        title={item.path || item.label}>
                  <span className="dg-band-box-name">{item.label}</span>
                  {item.sublabel && <span className="dg-band-box-sub">{item.sublabel}</span>}
                </button>
              ))}
              {/* No "and N more" is added here. The server already puts a node of kind `more`
                  in the column when it caps one, and counting the remainder again from this
                  side double-counted that node and printed a second, different number. */}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function Diagram({ d, selected = '', onPick }:
  { d: DiagramPayload; selected?: string; onPick?: (n: DiagramNode) => void }) {
  if (!d.nodes.length) return null
  return (
    <div className="dg-wrap">
      {d.plain && <p className="dg-plain">{d.plain}</p>}
      {d.kind === 'bands'
        ? <Bands d={d} selected={selected} onPick={onPick} />
        : <Graph d={d} selected={selected} onPick={onPick} />}
      {/* The note is where a diagram says what it did not draw and why. It is the part that
          keeps a picture honest, so it is never dropped to save space. */}
      {d.note && <p className="dg-note">{d.note}</p>}
    </div>
  )
}
