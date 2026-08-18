/* Service-worker registration + Web Push subscription helpers.
 * Push is optional: if the server has no VAPID keys, everything degrades
 * silently and the Settings toggle explains why. */
import { api, apiUrl } from './api'

export function registerServiceWorker(): void {
  if (!('serviceWorker' in navigator)) return
  // Vite dev server doesn't serve the built SW context reliably; register in prod only
  if (import.meta.env.DEV) return
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => { /* non-fatal */ })
  })
}

function b64ToUint8(base64: string): Uint8Array {
  const pad = '='.repeat((4 - (base64.length % 4)) % 4)
  const raw = atob((base64 + pad).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

export type PushState = 'unsupported' | 'server-disabled' | 'denied' | 'subscribed' | 'unsubscribed'

export async function getPushState(): Promise<PushState> {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return 'unsupported'
  try { await api.get('/api/push/vapid-public-key') } catch { return 'server-disabled' }
  if (Notification.permission === 'denied') return 'denied'
  const reg = await navigator.serviceWorker.getRegistration()
  const sub = reg && (await reg.pushManager.getSubscription())
  return sub ? 'subscribed' : 'unsubscribed'
}

export async function subscribePush(): Promise<void> {
  const { public_key } = await api.get('/api/push/vapid-public-key')
  const reg = (await navigator.serviceWorker.getRegistration())
    ?? (await navigator.serviceWorker.register('/sw.js'))
  await navigator.serviceWorker.ready
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: b64ToUint8(public_key) as BufferSource,
  })
  const json = sub.toJSON()
  await api.post('/api/push/subscribe', {
    endpoint: sub.endpoint,
    p256dh: json.keys?.p256dh ?? '',
    auth: json.keys?.auth ?? '',
  })
}

export async function unsubscribePush(): Promise<void> {
  const reg = await navigator.serviceWorker.getRegistration()
  const sub = reg && (await reg.pushManager.getSubscription())
  if (!sub) return
  const json = sub.toJSON()
  await api.delete2('/api/push/subscribe', {
    endpoint: sub.endpoint,
    p256dh: json.keys?.p256dh ?? '',
    auth: json.keys?.auth ?? '',
  })
  await sub.unsubscribe()
}

export async function sendTestPush(): Promise<number> {
  const r = await api.post('/api/push/test')
  return r.delivered as number
}

// keep TS happy for the fetch of apiUrl used indirectly in sw scope docs
void apiUrl
