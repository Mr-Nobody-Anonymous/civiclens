// Central API client — by default all calls are same-origin (/api/*), proxied
// by Vite in dev and served by FastAPI (or a platform rewrite, e.g. Vercel/
// Netlify) in production. For SPLIT deployments where the API lives on another
// origin, set VITE_API_BASE at build time (e.g. https://api.civiclens.et) —
// every request, upload, media URL and SSE stream is prefixed with it.
// No keys or secrets live here.

/** Absolute base of the API ('' = same origin). Set VITE_API_BASE to split. */
export const API_BASE: string =
  ((import.meta.env.VITE_API_BASE as string | undefined) ?? '').replace(/\/+$/, '')

/** Prefix an /api/... path with the configured API base. */
export function apiUrl(path: string): string {
  return API_BASE ? API_BASE + path : path
}

const CROSS_ORIGIN = API_BASE !== ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

// In cross-origin mode the browser can't read the cl_csrf cookie (it belongs
// to the API's domain), so we bootstrap the token once from /api/auth/csrf
// and keep it in memory. Same-origin mode keeps the double-submit cookie.
let csrfMem = ''
export function setCsrfToken(t: string) { csrfMem = t }

/** Read the CSRF token from the (non-HttpOnly) double-submit cookie. */
function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)cl_csrf=([^;]+)/)
  if (m) return decodeURIComponent(m[1])
  return csrfMem
}

/** Public helper for raw fetch() callers: current CSRF token (cookie or memory). */
export async function getCsrfToken(): Promise<string> {
  await ensureCsrf()
  return csrfToken()
}

/** Cross-origin only: fetch the CSRF token for the current session once. */
async function ensureCsrf(): Promise<void> {
  if (!CROSS_ORIGIN || csrfToken()) return
  try {
    const r = await fetch(apiUrl('/api/auth/csrf'), { credentials: 'include' })
    if (r.ok) { const j = await r.json(); if (j?.csrf_token) csrfMem = j.csrf_token }
  } catch { /* no session yet — server treats anonymous requests as exempt */ }
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
async function req(method: string, url: string, body?: unknown): Promise<any> {
  if (method !== 'GET') await ensureCsrf()
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 30000)
  const headers: Record<string, string> = {}
  if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken()
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  return fetch(apiUrl(url), {
    method, credentials: 'include', headers, signal: controller.signal,
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(async res => {
      const out = await handle(res)
      // Cross-origin: a session was (re)created — refresh the in-memory CSRF token.
      if (CROSS_ORIGIN && method === 'POST' &&
          /^\/api\/auth\/(login|register|reset-password)/.test(url)) {
        csrfMem = ''
        await ensureCsrf()
      }
      return out
    })
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
  put: (url: string, body?: unknown) => req('PUT', url, body ?? {}),
  patch: (url: string, body?: unknown) => req('PATCH', url, body ?? {}),
  delete: (url: string) => req('DELETE', url),
  /** DELETE with a JSON body (e.g. push unsubscribe by endpoint). */
  delete2: (url: string, body?: unknown) => req('DELETE', url, body),
}

/** Upload with real progress events (XHR — fetch has no upload progress). */
export function uploadWithProgress(
  url: string, file: File, fields: Record<string, string>,
  onProgress: (pct: number) => void,
): Promise<unknown> {
  return ensureCsrf().then(() => new Promise((resolve, reject) => {
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
    xhr.open('POST', apiUrl(url))
    xhr.withCredentials = true
    xhr.setRequestHeader('X-CSRF-Token', csrfToken())
    xhr.send(fd)
  }))
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
