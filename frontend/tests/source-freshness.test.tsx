import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { SourceFreshness } from '../src/components/SourceFreshness'
import type { Coverage } from '../src/components/ImportCoverage'

it('keeps snapshot timestamps distinct from attempts and hides unavailable timestamps', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  const node = document.createElement('div')
  const root = createRoot(node)
  const source = { source:'github', state:'complete', available:true,
    snapshot_read_at:'2026-10-26T10:00:00Z', read_at:'2026-10-27T10:00:00Z',
    attempt:{state:'failed'} } as Coverage
  try {
    await act(async () => root.render(<SourceFreshness coverage={{sources:{github:source}}} />))
    expect(node.querySelector('time')?.dateTime).toBe(source.snapshot_read_at)
    expect(node.textContent).toContain('Latest attempt: failed')
    expect(node.textContent).toContain('earlier saved snapshot')
    await act(async () => root.render(<SourceFreshness warning="Source permission changed."
      coverage={{sources:{github:{...source, available:false}}}} />))
    expect(node.querySelector('time')).toBeNull()
    expect(node.textContent).toContain('No snapshot available')
    expect(node.textContent).not.toContain('earlier saved snapshot')
    expect(node.querySelector('[role=status]')?.textContent).toBe('Source permission changed.')
  } finally { await act(async () => root.unmount()); vi.unstubAllGlobals() }
})
