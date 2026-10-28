import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Diagram } from '../src/components/Diagram'
import type { DiagramPayload } from '../src/components/Diagram'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  await act(async () => root.unmount())
  container.remove()
  vi.unstubAllGlobals()
})

it('reveals every file in a layer and can collapse it again', async () => {
  const nodes = Array.from({ length: 12 }, (_, n) => ({
    id: `b:src/file${n}.css`, label: `file${n}.css`, sublabel: 'src',
    path: `src/file${n}.css`, line: 1, url: '', kind: 'file', column: 0, row: n,
  }))
  const diagram: DiagramPayload = {
    key: 'stack', kind: 'bands', title: 'Layers', plain: '', note: '', edges: [], nodes,
    bands: [{ key: 'interface', title: 'Pages', plain: 'What a user sees.', column: 0, count: 12 }],
  }
  const pick = vi.fn()
  await act(async () => root.render(<Diagram d={diagram} onPick={pick} />))
  expect(container.querySelectorAll('.dg-band-box-name')).toHaveLength(7)
  const more = container.querySelector<HTMLButtonElement>('.dg-band-more')!
  expect(more.textContent).toBe('and 5 more')
  expect(more.getAttribute('aria-expanded')).toBe('false')
  await act(async () => more.click())
  expect(container.querySelectorAll('.dg-band-box-name')).toHaveLength(12)
  expect(more.textContent).toBe('Show fewer')
  expect(more.getAttribute('aria-expanded')).toBe('true')
  await act(async () => container.querySelectorAll<HTMLButtonElement>('.dg-band-box:not(.dg-band-more)')[11].click())
  expect(pick).toHaveBeenCalledWith(nodes[11])
  await act(async () => more.click())
  expect(container.querySelectorAll('.dg-band-box-name')).toHaveLength(7)
})
