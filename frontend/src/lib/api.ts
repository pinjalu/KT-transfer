// Every call to the backend goes through here. The application refuses any /api/ request that
// does not carry this header, which is what stops another page in the browser from driving it.
const HEADER = { 'x-pka-request': '1' }

export class ApiError extends Error {
  status: number
  code: string
  constructor(message: string, status: number, code = '') {
    super(message)
    this.status = status
    this.code = code
  }
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
      ? String((body as { detail: unknown }).detail)
      : `Request failed with status ${response.status}.`
    const code = body && typeof body === 'object' && 'code' in body
      ? String((body as { code: unknown }).code)
      : ''
    throw new ApiError(detail, response.status, code)
  }
  return body
}

export const get = (path: string) => send(path)
export const post = (path: string, payload?: unknown) =>
  send(path, { method: 'POST', body: payload === undefined ? '{}' : JSON.stringify(payload) })
