import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { FeatureWalkthrough } from '../src/components/FeatureWalkthrough'
import { ApiError, post } from '../src/lib/api'

vi.mock('../src/lib/api', async original => ({...await original<typeof import('../src/lib/api')>(), post:vi.fn()}))

it('builds only on request, renders evidence, and clears it on denied access', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  const node = document.createElement('div')
  const root = createRoot(node)
  vi.mocked(post).mockResolvedValue({key:'purpose', title:'Purpose', knowledge_revision:1,
    generated_at:'2026-10-27T00:00:00Z', missing_information:'No live result was observed.',
    statements:[{text:'Orders request products.', source_ids:['kt-purpose-S1'], support:'supported',
      about_this_project:true, evidence:{kind:'documentation', reason:'Documented purpose.'}}],
    sources:[{source_id:'kt-purpose-S1', path:'README.md', start:1, end:3,
      text:'<script>not executed</script>', url:'https://github.com/acme/shop/blob/abc/README.md'}]})
  try {
    await act(async () => root.render(<FeatureWalkthrough featureId="orders" sections={[{key:'purpose',title:'Purpose'}]} revision={1} />))
    expect(post).not.toHaveBeenCalled()
    await act(async () => node.querySelector('button')!.click())
    expect(post).toHaveBeenCalledWith('/api/features/orders/walkthrough/purpose')
    expect(node.textContent).toContain('Orders request products.')
    expect(node.textContent).toContain('Knowledge gap: No live result')
    expect(node.querySelector('script')).toBeNull()
    expect(node.querySelector('.cite')?.getAttribute('href')).toBe('#src-kt-purpose-S1')
    expect(node.querySelector('#src-kt-purpose-S1')).not.toBeNull()
    vi.mocked(post).mockRejectedValue(new ApiError('Source permission changed.', 403, 'access_denied'))
    await act(async () => node.querySelector('button')!.click())
    expect(node.textContent).not.toContain('Orders request products.')
    expect(node.textContent).toContain('Source permission changed.')
  } finally { await act(async () => root.unmount()); vi.unstubAllGlobals(); vi.resetAllMocks() }
})
