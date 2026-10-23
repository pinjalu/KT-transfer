// Every call to the backend goes through here. The application refuses any /api/ request that
// does not carry this header, which is what stops another page in the browser from driving it.
const HEADER = { 'x-pka-request': '1' }
export const JOB_CHANGED = 'pka:job-changed'
export const AUTH_REQUIRED = 'pka:auth-required'

export class ApiError extends Error {
  status: number
  code: string
  constructor(message: string, status: number, code = '') {
    super(message)
    this.status = status
    this.code = code
  }
}

/**
 * Turn whatever a failure carried into a sentence somebody can act on.
 *
 * Most of this application raises HTTPException with a written sentence, and `detail` is that
 * string. A request that fails validation never reaches that code: FastAPI answers first, and
 * its `detail` is a list of objects describing each field. Passing that to String() produced
 * the literal text "[object Object]" on screen, which told a reader nothing at all, and the
 * commonest way to see it was typing a two-letter greeting into the question box.
 */
function readDetail(detail: unknown, status: number): string {
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) {
    const said = detail
      .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
      .filter(Boolean)
    if (said.length) return said.join('. ') + '.'
  }
  return `Request failed with status ${status}.`
}

async function send(path: string, init: RequestInit = {}): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { ...HEADER, ...(init.body ? { 'content-type': 'application/json' } : {}), ...init.headers },
    })
  } catch {
    throw new ApiError('The application is not reachable. Check that it is still running.', 0, 'network')
  }
  const text = await response.text()
  let body: unknown = null
  if (text) {
    try { body = JSON.parse(text) } catch { body = null }
  }
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body
      ? readDetail((body as { detail: unknown }).detail, response.status)
      : `Request failed with status ${response.status}.`
    const code = body && typeof body === 'object' && 'code' in body
      ? String((body as { code: unknown }).code)
      : ''
    if (response.status === 401 && code === 'session_required') {
      window.dispatchEvent(new Event(AUTH_REQUIRED))
    }
    throw new ApiError(detail, response.status, code)
  }
  return body
}

export const get = (path: string) => send(path)
export const post = async (path: string, payload?: unknown) => {
  const body = await send(path, { method: 'POST', body: payload === undefined ? '{}' : JSON.stringify(payload) })
  // Refresh the shared controls as soon as a job starts or changes, even on another page.
  if (body && typeof body === 'object' && 'job_id' in body) {
    window.dispatchEvent(new Event(JOB_CHANGED))
  }
  return body
}
