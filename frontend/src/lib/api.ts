// Central API client — all calls are same-origin (/api/*), proxied by Vite in
// dev and served by FastAPI in production. No keys or secrets live here.

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

/** Read the CSRF token from the (non-HttpOnly) double-submit cookie. */
function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)cl_csrf=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

const FRIENDLY: Record<number, string> = {
  401: 'Please sign in to continue.',
  403: 'You do not have permission to do that.',
  404: 'Not found.',
  409: 'This action conflicts with the current state.',
  429: 'Too many requests — please wait a moment and try again.',
  500: 'Something went wrong on the server. Please try again.',
}

async function handle(res: Response) {
  if (res.ok) return res.status === 204 ? null : res.json()
  let msg = ''
  try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : '' } catch { /* noop */ }
  throw new ApiError(res.status, msg || FRIENDLY[res.status] || res.statusText)
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function req(method: string, url: string, body?: unknown): Promise<any> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 30000)
  const headers: Record<string, string> = {}
  if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken()
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  return fetch(url, {
    method, credentials: 'include', headers, signal: controller.signal,
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(handle)
    .catch(e => {
      if (e instanceof ApiError) throw e
      if (e?.name === 'AbortError') throw new ApiError(0, 'Request timed out — check your connection and retry.')
      throw new ApiError(0, 'Network error — check your connection.')
    })
    .finally(() => clearTimeout(timer))
}

export const api = {
  get: (url: string) => req('GET', url),
  post: (url: string, body?: unknown) => req('POST', url, body),
  patch: (url: string, body?: unknown) => req('PATCH', url, body ?? {}),
  delete: (url: string) => req('DELETE', url),
}

/** Upload with real progress events (XHR — fetch has no upload progress). */
export function uploadWithProgress(
  url: string, file: File, fields: Record<string, string>,
  onProgress: (pct: number) => void,
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const fd = new FormData()
    fd.append('file', file)
    Object.entries(fields).forEach(([k, v]) => fd.append(k, v))
    xhr.upload.onprogress = e => { if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100)) }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText || '{}'))
      else {
        let msg = `Upload failed (${xhr.status})`
        try { msg = JSON.parse(xhr.responseText).detail || msg } catch { /* noop */ }
        reject(new ApiError(xhr.status, msg))
      }
    }
    xhr.onerror = () => reject(new ApiError(0, 'Network error during upload'))
    xhr.open('POST', url)
    xhr.withCredentials = true
    xhr.setRequestHeader('X-CSRF-Token', csrfToken())
    xhr.send(fd)
  })
}

/** Reverse geocode via OpenStreetMap Nominatim (best-effort, public endpoint). */
export async function reverseGeocode(lat: number, lng: number): Promise<string | null> {
  try {
    const r = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}&zoom=17`,
      { headers: { Accept: 'application/json' } })
    if (!r.ok) return null
    const j = await r.json()
    return j.display_name?.split(',').slice(0, 4).join(',') ?? null
  } catch { return null }
}
