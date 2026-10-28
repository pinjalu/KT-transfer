import { afterEach, expect, it, vi } from 'vitest'
import { JOB_CHANGED, PROJECT_CHANGED, uploadZip } from '../src/lib/api'
import { originOf } from '../src/lib/answer'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('sends the ZIP as binary with the application header and refreshes the workspace', async () => {
  const fetch = vi.fn().mockResolvedValue({ok:true, text:async () => '{"job_id":1}'})
  vi.stubGlobal('fetch', fetch)
  const dispatch = vi.spyOn(window, 'dispatchEvent')
  const file = new File(['contents'], 'my project.zip')
  await uploadZip(file)
  expect(fetch).toHaveBeenCalledWith('/api/zip/upload?filename=my%20project.zip', expect.objectContaining({
    method:'POST', body:file, headers:{'x-pka-request':'1', 'content-type':'application/zip'},
  }))
  expect(dispatch.mock.calls.map(([event]) => event.type)).toEqual([PROJECT_CHANGED, JOB_CHANGED])
  expect(originOf('app.py', '/source?snapshot=abc&path=app.py&source=zip#L2')).toBe('ZIP file')
})

it('does not announce a project change when uploading fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:false, status:413, text:async () => '{"detail":"ZIP uploads must be 25 MB or smaller."}'}))
  const dispatch = vi.spyOn(window, 'dispatchEvent')
  await expect(uploadZip(new File(['zip'], 'large.zip'))).rejects.toThrow('25 MB')
  expect(dispatch).not.toHaveBeenCalled()
})
